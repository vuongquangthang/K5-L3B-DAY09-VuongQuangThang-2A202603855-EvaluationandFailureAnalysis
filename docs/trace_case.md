# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID: `E-seeded_regression-20261118-4bfb` |
| Triệu chứng | Grader Lab 8 fail: `status resolved != denied`. Kết quả trả về `resolved`, đề xuất hoàn 20.000đ, ledger ghi nhận bồi hoàn `refund_vnd = 20000`, trong khi nhãn kỳ vọng `status = denied, refund_vnd = 0`. |
| Bước sai đầu tiên | Event số 3, kind: `model_override`, payload: `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | - Event 1 (`handoff`): Ủy quyền các công cụ tra cứu hoàn toàn chuẩn xác.<br>- Event 2 (`investigator`): Tra cứu DB `lookup_order` lấy thông tin chính thức của đơn `O-202` chính xác: `delay_days = 2` (giao trễ 2 ngày, không đủ điều kiện bồi thường theo quy định trễ ≥ 3 ngày).<br>- Đến Event 3: Agent đã tự ý dùng lời khai của khách trong ticket ("Đơn giao trễ 5 ngày") để ghi đè số ngày trễ trong DB, từ đó Event 4 (`quote`) tính sai mức tiền 20.000đ theo clause `SHIP-LATE-03`. |
| Failure mode | FM-03 (`ticket_trust` — tin ticket hơn DB) |
| Đối chứng | Cùng claim `C-002@11` trên shape `fixed` (run ID: `E-fixed-20261118-4bfb`): Agent bảo lưu thông tin DB (`delay_days = 2`), không xuất hiện event `model_override`. Event 3 trực tiếp tính ra `quote` 0đ (`no_entitlement`), trạng thái từ chối `denied`, ledger `refund_vnd = 0`, đạt `lab8 grader: PASS (ok)`. |
| Regression test | Grader `DbFactKept` kiểm tra sự vắng mặt của event `model_override`, đo bằng metric `db_fact_kept` trong `config/metric_spec.yaml`. Test unit `test_override_event_breaks_db_fact` trong `tests/test_lab9_graders.py`. Khi chạy eval, metric `db_fact_kept` đạt 1.0 trên `fixed` nhưng sụt giảm xuống 0.9286 trên `seeded_regression`. |
| Chưa chắc chắn | Trace chỉ ghi nhận hành vi mô hình can thiệp ghi đè dữ liệu (`model_override`), không chứng minh được cơ chế chú ý (attention weight) bên trong LLM đã bị chi phối bởi từ khóa nào trong ticket của người dùng. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
