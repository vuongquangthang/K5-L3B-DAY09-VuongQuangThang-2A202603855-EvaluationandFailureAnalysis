"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    import math

    problems: list[str] = []

    # 1. Any metric value in pr["metrics"] that is NaN or inf
    for k, v in pr.get("metrics", {}).items():
        if isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is nan/inf ({v})")

    # 2. len(pr["rows"]) != manifest items x len(manifest seeds)
    manifest = pr.get("manifest", {})
    expected_rows = manifest.get("items", 0) * len(manifest.get("seeds", []))
    if len(pr.get("rows", [])) != expected_rows:
        problems.append(f"row count {len(pr.get('rows', []))} != manifest items x seeds {expected_rows}")

    # 3. the (item_id, seed) set of PR differs from the baseline's
    pr_pairs = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows", [])}
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base.get("rows", [])}
    if pr_pairs != base_pairs:
        problems.append("PR (item_id, seed) set differs from baseline")

    # 4. pr["evaluator_failures"] non-empty
    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])} failure(s))")

    # 5. a row whose value for a graded spec metric is None
    spec_metric_ids = [m["id"] for m in spec.get("metrics", [])]
    for r in pr.get("rows", []):
        found_none = False
        for m in spec_metric_ids:
            if m in r and r[m] is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for graded spec metric {m}")
                found_none = True
                break
        if found_none:
            break

    # 6. an item's slice tags in PR rows differ from the baseline's
    pr_slices = {r.get("item_id"): tuple(sorted(r.get("slices") or [])) for r in pr.get("rows", [])}
    base_slices = {r.get("item_id"): tuple(sorted(r.get("slices") or [])) for r in base.get("rows", [])}
    for item_id, bs in base_slices.items():
        if item_id in pr_slices and pr_slices[item_id] != bs:
            problems.append(f"item {item_id} slice tags differ from baseline")
            break

    # 7. Ratchet check when base_spec is provided
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        spec_m_map = {m["id"]: m for m in spec.get("metrics", [])}
        for bm in base_spec.get("metrics", []):
            mid = bm["id"]
            if mid not in spec_m_map:
                problems.append(f"metric {mid} removed (ratchet violation)")
                continue
            sm = spec_m_map[mid]
            if bm.get("blocking") and not sm.get("blocking"):
                problems.append(f"metric {mid} changed from blocking to non-blocking (ratchet violation)")
            b_th = bm.get("threshold", {})
            s_th = sm.get("threshold", {})
            if "min" in b_th:
                if "min" not in s_th or s_th["min"] < b_th["min"] - 1e-9:
                    problems.append(f"metric {mid} min threshold lowered (ratchet violation)")
            if "max" in b_th:
                if "max" not in s_th or s_th["max"] > b_th["max"] + 1e-9:
                    problems.append(f"metric {mid} max threshold raised (ratchet violation)")
            if "max_increase" in b_th:
                if "max_increase" not in s_th or s_th["max_increase"] > b_th["max_increase"] + 1e-9:
                    problems.append(f"metric {mid} max_increase raised (ratchet violation)")
            if b_th.get("no_significant_drop") and not s_th.get("no_significant_drop"):
                problems.append(f"metric {mid} dropped no_significant_drop (ratchet violation)")

        base_slices = base_spec.get("slices", [])
        spec_slices = spec.get("slices", [])
        spec_sl_map = {(sl["name"], sl["metric"]): sl for sl in spec_slices}
        for bsl in base_slices:
            key = (bsl["name"], bsl["metric"])
            if key not in spec_sl_map:
                problems.append(f"slice {key[0]}/{key[1]} removed (ratchet violation)")
                continue
            ssl = spec_sl_map[key]
            if bsl.get("blocking") and not ssl.get("blocking"):
                problems.append(f"slice {key[0]}/{key[1]} made non-blocking (ratchet violation)")
            if "min" in bsl:
                if "min" not in ssl or ssl["min"] < bsl["min"] - 1e-9:
                    problems.append(f"slice {key[0]}/{key[1]} min lowered (ratchet violation)")
            if bsl.get("no_significant_drop") and not ssl.get("no_significant_drop"):
                problems.append(f"slice {key[0]}/{key[1]} dropped no_significant_drop (ratchet violation)")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})

    for sl in spec.get("slices", []):
        name = sl["name"]
        metric = sl["metric"]
        min_th = sl.get("min")
        no_drop = sl.get("no_significant_drop", False)
        is_blocking = sl.get("blocking", False)

        pr_items = per_item(pr, metric, slice_name=name)
        base_items = per_item(base, metric, slice_name=name)
        if not pr_items:
            continue

        val = sum(pr_items.values()) / len(pr_items)
        verdict, note = "ok", ""

        if min_th is not None and val < min_th:
            verdict = "fail"

        if no_drop and base_items:
            keys = sorted(set(pr_items) & set(base_items))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [pr_items[k] for k in keys],
                    [base_items[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        slice_id = f"slice:{name}/{metric}"
        if verdict != "ok" and is_blocking:
            blocked.append(slice_id)

        label = "ok" if verdict == "ok" else ("BLOCK" if is_blocking else "warn")
        lines.append(f"  {slice_id:<22} {val!s:<8} min={min_th!s:<10} {note:<28} {label}")

    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
