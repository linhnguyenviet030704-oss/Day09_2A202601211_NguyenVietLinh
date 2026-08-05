# Báo Cáo Cá Nhân - Day 09: Multi-Agent E-commerce Dispute Resolution

## 1. Thông Tin Cá Nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Việt Linh |
| MSSV | 2A202601211 |
| Lớp/khóa | K3 |
| Vai trò chính | Member A - Data Loader, Coordinator, Batch Runner |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai Trò Và Phạm Vi Công Việc

Phần việc chính của tôi là xây dựng phần backbone cho hệ thống: nạp dữ liệu Olist, điều phối các agent con, lắp output cuối cùng theo schema đề bài, ghi log chạy thật và tạo tài liệu kiến trúc nhóm.

| Hạng mục | File liên quan | Kết quả |
| --- | --- | --- |
| Data loader | `src/core/data.py` | Đọc CSV, lọc order/items/payments/sellers theo `claimed_order_id` |
| Coordinator | `src/core/coordinator.py` | Gọi các fact agents, kiểm tra thiếu facts, retry một lần, lock facts, gọi policy và verifier |
| Batch runner | `src/run.py` | Chạy 50 case từ `input/` và ghi JSON ra `output/` hoặc `output2/` |
| Trace/metadata | `logging/`, `logging2/` | Ghi trace từng case và metadata runtime/model |
| Kiểm thử | `tests/test_data.py`, `tests/test_coordinator.py`, `tests/test_run.py` | Test data loader, coordinator, runner, evidence selection |
| Tài liệu kiến trúc | `architecture.md` | Mô tả agent diagram, handoff flow, verifier gate |

## 3. Kết Quả Đã Thực Hiện

Tôi đã triển khai `DataLoader` để load dữ liệu một lần, kiểm tra cột bắt buộc và trả về `OrderBundle` gồm order, items, payments và sellers. Cách này giúp các agent không phải tự đọc CSV rời rạc, giảm lỗi lệch contract.

Trong `Coordinator`, tôi triển khai luồng xử lý:

```text
LOAD_CASE -> CALL_FACT_AGENTS -> CHECK_COMPLETENESS -> LOCK_FACTS
          -> POLICY -> ASSEMBLE_OUTPUT -> VERIFY -> WRITE_OUTPUT
```

Coordinator có `_missing_agents()` để phát hiện facts còn thiếu theo ngữ cảnh. Ví dụ order `delivered` cần delivery dates, shipping limit và payment totals; order `canceled` hoặc `unavailable` chỉ cần status và payment total. Nếu agent trả thiếu dữ liệu, Coordinator retry đúng agent đó một lần.

Tôi cũng xử lý giới hạn output theo rubric: tối đa 5 entity IDs, 10 evidence IDs, 3 root causes, 3 responsible parties và 5 actions.

## 4. Phần Kỹ Thuật Quan Trọng

### 4.1 Evidence Selection

Một phần quan trọng là chọn `evidence_ids` đúng và không đưa bằng chứng thừa. Ban đầu source có nguy cơ thêm `seller:<seller_id>` vào mọi rule có item, kể cả khi seller không phải bên chịu trách nhiệm. Điều này có thể làm giảm điểm vì evidence thật nhưng không liên quan root cause.

Tôi đã sửa logic để `seller:` chỉ xuất hiện khi `responsible_parties` có `party_type == "seller"`.

Quy tắc evidence hiện tại:

| Primary issue | Evidence chính |
| --- | --- |
| `late_delivery_seller` | `order`, `item`, `payment`, `seller`, `policy` |
| `late_delivery_logistics` | `order`, `item`, `payment`, `policy` |
| `unsupported_late_claim` | `order`, `item`, `payment`, `policy` |
| `canceled_order_paid` | `order`, `payment`, `policy` |
| `unavailable_order_paid` | `order`, `payment`, `policy` |
| `valid_split_payment` | `order`, `payment`, `policy` |

Tôi cũng sắp xếp `payment_ids` theo `payment_sequential` để output ổn định hơn, nhất là các case split payment.

### 4.2 Verifier Gate

Coordinator không ghi output ngay sau Policy Agent. Output candidate phải qua Verifier Agent để kiểm tra schema, evidence format, evidence tồn tại trong CSV, số tiền và các giới hạn field.

Nếu Verifier reject, Coordinator không trả output sai. Cơ chế này giúp tránh hard gate 0 điểm cho case lỗi schema hoặc evidence bịa.

## 5. Một Quyết Định Thiết Kế

Tôi chọn retry agent thiếu facts đúng một lần thay vì retry vô hạn hoặc bỏ qua dữ liệu thiếu.

Lý do:

- Dữ liệu CSV ổn định, nếu agent deterministic trả thiếu thì retry một lần là đủ để xử lý lỗi handoff tạm thời.
- Retry vô hạn làm trace khó đọc và có thể che lỗi contract.
- Không retry thì Policy Agent có thể ra quyết định trên facts thiếu.

Test liên quan: `tests/test_coordinator.py` có case Payment Agent lần đầu trả thiếu payment totals, lần hai trả đủ; test xác nhận Coordinator gọi lại đúng một lần.

## 6. Một Lỗi Đã Xử Lý

Lỗi đáng chú ý nằm ở phần evidence: nếu thêm seller evidence cho mọi rule, các case platform/logistics/no-action có thể bị xem là có bằng chứng không liên quan. Tôi đã phân tích output theo issue và thấy seller chỉ nên đi với `late_delivery_seller`.

Cách xử lý:

- Thêm test `test_evidence_only_includes_seller_for_seller_responsibility`.
- Sửa `_assemble_output()` để seller evidence phụ thuộc vào `responsible_parties`.
- Chạy lại batch ra `output2/`.

Kết quả kiểm tra:

```bash
python -m unittest discover -s tests
```

Kết quả hiện tại: 8/8 tests pass. `output2/` có đủ 50 file và `seller:` chỉ xuất hiện trong 8 case `late_delivery_seller`.

## 7. Hiểu Biết Về Luồng End-to-End

Luồng hệ thống bắt đầu từ `input/EC_xxx.json`. Coordinator đọc `case_id` và `customer_request.claimed_order_id`, sau đó dùng `DataLoader` để lấy dữ liệu tương ứng từ Olist CSV.

Các fact agents phân tích từng domain:

- Order & Seller Agent kiểm tra status, item, seller và seller handoff.
- Delivery Agent so sánh ngày giao thực tế với ngày ước tính.
- Payment Agent đối soát payment rows với item total và freight total.

Policy Agent áp dụng `EC_POLICY_V1` theo đúng thứ tự ưu tiên. Sau đó Coordinator dựng output cuối gồm assessment, affected entities, root cause, evidence, financial resolution và actions. Verifier Agent là cổng cuối để đảm bảo output có thể nộp.

Điểm quan trọng nhất tôi rút ra là evidence không chỉ cần tồn tại trong CSV, mà còn phải liên quan trực tiếp đến quyết định. Một ID đúng format nhưng không hỗ trợ root cause vẫn có thể làm điểm bằng chứng thấp.

## 8. Cam Kết Cá Nhân

- [x] Báo cáo phản ánh đúng phần việc tôi đã thực hiện.
- [x] Tôi có thể giải thích luồng end-to-end của hệ thống.
- [x] Tôi không đưa `.env`, API key, token hoặc secret vào báo cáo.
- [x] Tôi đã kiểm chứng bằng unit tests và batch output.
- [x] Báo cáo không sao chép nguyên văn báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Việt Linh  
**MSSV:** 2A202601211  
**Ngày xác nhận:** 2026-08-05
