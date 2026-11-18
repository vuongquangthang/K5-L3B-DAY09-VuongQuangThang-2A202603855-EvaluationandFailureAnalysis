# Judge audit

Chạy: `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5`
Chạy: `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt cả 3 chỉ số (0.757 ≥ 0.6, 0.857 ≥ 0.8, 0.800 ≥ 0.7) | Dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (κ=0.375 < 0.6, R=0.300 < 0.7, bỏ lọt 21 lỗi) | Loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008: "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người đúng | Xưng hô "anh - em", từ "nha" quá suồng sã, thiếu tính chuyên nghiệp B2C. Sửa rubric: cấm dùng đại từ nhân xưng thân mật gia đình, bắt buộc dùng "quý khách" hoặc "anh/chị". |
| 2 | H-017: "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người đúng | Sử dụng khẩu ngữ "bạn ơi", "rồi nha" làm giảm độ tin cậy của dịch vụ tài chính. Sửa rubric: bổ sung quy định từ cấm (khẩu ngữ chat cá nhân). |
| 3 | H-029: "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người đúng | Văn phong thô lỗ, mệnh lệnh tiêu cực ("không cần nhắn thêm") gây ức chế cho khách hàng. Sửa rubric: cấm mệnh lệnh từ chối tiếp nhận giao tiếp từ người dùng. |
| 4 | H-042: "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người đúng | Câu trả lời lịch sự, thông tin thời gian tiền về rõ ràng, đúng ngữ cảnh. Judge phạt nhầm vì đòi hỏi lời chào hoa mỹ. Sửa rubric: câu trả lời súc tích, lịch sự ("Dạ... ạ") có giá trị và thời hạn rõ ràng được tính là PASS. |
| 5 | H-051: "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người đúng | Dùng từ mượn phổ thông ("refund") trong bối cảnh thanh toán online, có kính ngữ. Judge quá khắt khe về từ vựng. Sửa rubric: cho phép các thuật ngữ chuẩn ngành thương mại điện tử / fintech đã được chấp nhận rộng rãi. |
| 6 | HL-016: "Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của..." | PASS | FAIL | Người đúng | Câu bị ngắt quãng giữa chừng, không đưa ra bất kỳ thông tin giải quyết nào cho khiếu nại, hoàn toàn vô ích nhưng judge helpful đánh giá PASS chỉ vì có lời xin lỗi lịch sự. Sửa rubric: câu cụt, câu không có hành động cụ thể (actionable) phải bị chấm FAIL. |

## Kết luận
- **Tiêu chí bị loại và lý do**: `helpful` bị loại hoàn toàn vì không đạt ngưỡng tin cậy tối thiểu (Cohen's Kappa κ = 0.375 < 0.6, Recall R = 0.300 < 0.7). Ma trận nhầm lẫn `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}` cho thấy judge bỏ lọt tới 21 trên tổng số 30 trường hợp câu trả lời không hữu ích (tỉ lệ bỏ sót 70%). Judge bị đánh lừa bởi những câu xin lỗi khách sáo dù không giải quyết được vấn đề của khách hàng.
- **Tiêu chí được chấp nhận**: `tone_ok` đạt chuẩn hiệu chuẩn (κ = 0.757, Precision = 0.857, Recall = 0.800) với tỉ lệ lỗi quan sát 28% tương ứng tỉ lệ lỗi hiệu chỉnh (Rogan-Gladen) là 30%. Có thể dùng để giám sát văn phong.
- **Rủi ro còn lại**: Judge chỉ mới được kiểm tra trên tập dữ liệu replay công khai (100 câu cố định). Khi đưa vào sản xuất với các biến thể prompt mới hoặc mô hình ngôn ngữ khác, judge có thể xuất hiện độ lệch (drift) hoặc bias vị trí/độ dài. Cần định kỳ gắn nhãn người trên tập held-out mới để tái hiệu chuẩn.
