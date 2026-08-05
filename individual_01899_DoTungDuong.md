# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Đỗ Tùng Dương |
| MSSV | 2A202601899 |
| Khóa/Lớp | K3 |
| Vai trò chính | Member C — Payment Agent, Policy Agent, Verifier Agent |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Payment Agent | `src/agents/payment.py` - `run_payment_agent()` | Item row, payment row của 1 order | `{payments, payment_total, item_total, freight_total, reconciled, split_payment}` | Hoàn thành |
| Policy Agent | `src/agents/policy.py` - `run_policy_agent()` | 3 contract từ Order&Seller, Delivery, Payment | `primary_issue`, `responsible_parties`, `financial_resolution`, `resolution_actions` theo `EC_POLICY_V1` | Hoàn thành |
| Verifier Agent | `src/agents/verifier.py` - `run_verifier_agent()` | Kết quả Policy Agent + contract order_seller/payment | `(is_valid, errors, final_case_dict)` đúng schema output | Hoàn thành |
| Unit test | `tests/test_payment.py`, `test_policy.py`, `test_verifier.py` | Mock data tự tạo | 18/18 test pass | Hoàn thành |

Chỉ nhận ownership 3 agent trên, không sở hữu Order & Seller, Delivery, Coordinator hay data loader (thuộc Member A/B).

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây rule engine áp `EC_POLICY_V1` đúng thứ tự ưu tiên | `src/agents/policy.py` | 50/50 case verify pass | `python run.py` |
| Đối soát payment vs item+freight (sai số ±0.10) | `src/agents/payment.py` | 0 sai lệch số tiền so với CSV gốc | Script đối chiếu bằng `pandas` |
| Verifier chặn evidence không kiểm chứng được | `src/agents/verifier.py` | 0 evidence fabrication trên 50 case | Script đối chiếu `evidence_ids` với CSV |

Artifact cụ thể: `output/EC_001.json` (case `late_delivery_seller`, refund đúng bằng freight của item vi phạm, evidence khớp CSV gốc).

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Từ fact do Order & Seller/Delivery Agent trả về, tôi đối soát payment, áp đúng 6 rule `EC_POLICY_V1` theo thứ tự ưu tiên, và đảm bảo mọi evidence/số tiền trong output dựng được từ CSV thật.

### Cách triển khai

`payment.py` cộng dồn payment/item/freight, tính `reconciled`/`split_payment`. `policy.py` chạy chuỗi `if/elif` đúng thứ tự 6 rule, trả `primary_issue`, trách nhiệm, refund (2dp), action. `verifier.py` đối chiếu từng ID trong output với contract data, loại ID không khớp, enforce cap theo README. Cả 3 file deterministic, không gọi LLM.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `order_seller`, `delivery` (JSON contract), `items`/`payments` (list[dict]) |
| Output | JSON đúng schema README mục 6 |
| Module phụ thuộc | Không import `core/data.py` hay module A/B nào, chỉ nhận dữ liệu qua tham số |
| Module sử dụng output | Coordinator - chỉ ghi file khi verifier trả `is_valid = True` |
| Điều kiện lỗi cần xử lý | Evidence không tồn tại trong contract, order không có item row, confidence/case_status/refund không hợp lệ, vượt cap |

### Cách xác minh

```bash
python -m pytest tests/test_payment.py tests/test_policy.py tests/test_verifier.py -v
python run.py
```

- Kết quả mong đợi: 18/18 test pass, 50 file output, 0 case fail verify.
- Kết quả thực tế: đúng như mong đợi.
- Artifact/log: `output/EC_*.json`, `logging/trace.jsonl`.

## 5. Một quyết định kỹ thuật quan trọng

- Bối cảnh: phần Payment/Policy/Verifier quyết định chiếm phần lớn trọng số điểm, cần chọn giữa để LLM tự suy luận hay code deterministic.
- Các phương án đã cân nhắc: LLM tự chọn rule và tính refund; hoặc rule engine deterministic thuần Python.
- Phương án đã chọn: deterministic hoàn toàn, không gọi LLM.
- Lý do: 6 rule đều là so sánh ngày tháng/số tiền tính đúng 100% bằng code, LLM chỉ thêm rủi ro sai số không cần thiết.
- Bằng chứng quyết định phù hợp: 50/50 case verify pass mọi lần chạy, 0 sai lệch tài chính đối chiếu CSV gốc, tiêu chí Tài chính ổn định 95.75/100 qua 2 lần chấm.

## 6. Một lỗi hoặc blocker đã xử lý

- Triệu chứng/lỗi nguyên văn: chấm điểm lần 1 tổng 94.3713, tiêu chí Bằng chứng chỉ 86.2875, thấp hơn hẳn 5 tiêu chí còn lại.
- Lệnh hoặc bước tái hiện: đối chiếu `evidence_ids` của từng case với `responsible_parties` tương ứng.
- Nguyên nhân gốc: `verifier.py` gắn seller evidence vào mọi rule kể cả khi seller không phải bên chịu trách nhiệm, ảnh hưởng 34/50 case.
- Cách xử lý: chỉ thêm seller evidence khi seller nằm trong `responsible_parties` của quyết định.
- Cách xác minh sau khi sửa: 18/18 test pass, 0 fabrication, chấm lại Bằng chứng 86.29 → 96.17, tổng điểm 94.37 → 95.85, khớp đúng trọng số 15%.
- Điều học được: evidence có thật vẫn có thể sai nếu không liên quan tới quyết định, verifier cần kiểm cả tính liên quan chứ không chỉ tồn tại.

## 7. Hiểu biết về luồng end-to-end

Dữ liệu đi từ `input/EC_xxx.json` với `claimed_order_id`, qua data loader dựng order bundle từ CSV, tới Order&Seller/Delivery Agent trả fact, Payment Agent (phần tôi) đối soát tiền, Policy Agent (phần tôi) áp `EC_POLICY_V1` ra quyết định, Verifier Agent (phần tôi) đối chiếu ngược mọi ID với contract data thật rồi mới cho Coordinator ghi output. Evidence chỉ được coi là hợp lệ khi trace được về CSV qua contract, không dựng từ suy diễn. Ngoài verifier gate, chất lượng còn được kiểm bằng unit test theo mock data và script đối chiếu độc lập output với CSV gốc trước khi nộp. Payment/Policy/Verifier phải deterministic vì đây là phần trọng số điểm cao nhất và tính đúng được 100% bằng code, để LLM quyết định chỉ thêm rủi ro không cần thiết. Lần sửa evidence được xem là thành công dựa trên điểm chấm thật: tiêu chí Bằng chứng tăng đúng bằng mức tăng tổng điểm chia cho trọng số 15%, chứng minh bằng số học chứ không phải suy đoán.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đỗ Tùng Dương
**Ngày xác nhận:** 2026-08-05
