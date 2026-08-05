# Báo Cáo Cá Nhân - Day 09: Multi-Agent E-commerce Dispute Resolution

## 1. Thông Tin Cá Nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Lê Trần Khương Duy |
| MSSV | 2A202601349 |
| Lớp/khóa | K3 |
| Vai trò chính | Member B - Order & Seller Agent, Delivery Agent |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai Trò Và Phạm Vi Công Việc

Phần việc chính của tôi là xây dựng hai fact agent điều tra: Order & Seller Agent và Delivery Agent. Đây là nửa "điều tra sự thật" của pipeline, cung cấp các facts để Policy Agent phân biệt được lỗi thuộc về người bán (`late_delivery_seller`) hay thuộc về logistics (`late_delivery_logistics`).

| Hạng mục | File liên quan | Kết quả |
| --- | --- | --- |
| Order & Seller Agent | `src/agents/order_seller.py` | Trích xuất order status, item/seller facts, phát hiện seller handoff trễ hạn |
| Delivery Agent | `src/agents/delivery.py` | So sánh ngày giao thực tế với ngày ước tính, xác định giao trễ |
| Contract fact | `architecture.md` | Định nghĩa schema output mà Policy và Verifier tiêu thụ |
| Kiểm chứng gián tiếp | `tests/test_policy.py`, `tests/test_verifier.py` | Mock dict đúng contract Member B để kiểm tra luồng phân loại issue |

## 3. Kết Quả Đã Thực Hiện

Tôi triển khai `run_order_seller_agent(bundle)` nhận `OrderBundle` từ Data Loader (Member A) và trả về facts theo contract chung:

```text
{order_status, items[{item_id, seller_id, price, freight_value, shipping_limit_date}],
 seller_ids[], delivered_carrier_date, seller_handoff_late,
 late_seller_ids[], late_item_ids[]}
```

Điểm cốt lõi là xác định `seller_handoff_late`: với mỗi item, tôi so sánh `order_delivered_carrier_date` (thời điểm người bán giao hàng cho đơn vị vận chuyển) với `shipping_limit_date` của chính item đó. Nếu carrier date muộn hơn hạn giao, seller đó bị đánh dấu trễ và được gom vào `late_seller_ids` / `late_item_ids`.

Song song, `run_delivery_agent(bundle, order_seller)` xác định `delivered_late` bằng cách so sánh `order_delivered_customer_date` với `order_estimated_delivery_date`. Delivery Agent cũng chuyển tiếp `carrier_after_limit` lấy từ output của Order & Seller Agent để Policy có đủ dữ kiện trong một chỗ.

Sự kết hợp hai facts này chính là cơ sở phân loại của Policy Agent:

| Tình huống | `delivered_late` | `seller_handoff_late` | Kết luận |
| --- | --- | --- | --- |
| Giao trễ do người bán chậm bàn giao | true | true | `late_delivery_seller` |
| Giao trễ nhưng người bán bàn giao đúng hạn | true | false | `late_delivery_logistics` |
| Giao đúng hạn | false | — | không phải khiếu nại giao trễ |

## 4. Phần Kỹ Thuật Quan Trọng

### 4.1 So Sánh Ngày An Toàn Với Dữ Liệu Thiếu

Với các order `canceled` hoặc `unavailable`, nhiều mốc thời gian trong Olist bị bỏ trống (NaN/NaT): không có `delivered_carrier_date`, không có `delivered_customer_date`. Nếu so sánh trực tiếp sẽ ra kết quả sai hoặc lỗi.

Tôi dùng `pd.notna()` bảo vệ trước mọi phép so sánh:

```python
if pd.notna(carrier_date) and pd.notna(limit) and carrier_date > limit:
    late_seller_ids.append(sid)
```

Nhờ vậy một order chưa từng được giao sẽ không bao giờ bị gán nhầm là "seller trễ" hay "giao trễ". Các field ngày trong output được trả về `None` một cách tường minh thay vì để lọt giá trị NaN vào JSON.

### 4.2 Facts Ở Cấp Từng Item

Một order có thể chứa nhiều item từ nhiều seller khác nhau, mỗi item có `shipping_limit_date` riêng. Tôi không đánh giá trễ ở cấp order mà ở cấp từng item, rồi mới gom `set` các seller/item trễ. Điều này cho phép trường hợp chỉ một seller trong đơn bị trễ vẫn được ghi nhận đúng, và `seller_handoff_late` trở thành `True` chỉ khi thực sự có ít nhất một item trễ hạn.

`seller_ids`, `late_seller_ids`, `late_item_ids` đều được `sorted(set(...))` để output ổn định, không phụ thuộc thứ tự đọc row.

## 5. Một Quyết Định Thiết Kế

Tôi chọn triển khai cả hai agent theo hướng **deterministic, không gọi LLM**.

Lý do:

- Công việc ở đây là so sánh ngày và trích xuất field từ CSV, không phải phán đoán ngữ nghĩa. Một phép so sánh `date > date` không nên giao cho LLM.
- Gọi LLM sẽ thêm rủi ro đọc sai ngày và tạo ra kết quả không lặp lại được, trong khi phần phân loại `late_delivery_seller` vs `late_delivery_logistics` ảnh hưởng trực tiếp tới điểm root cause và financial resolution.
- Facts deterministic giúp Verifier Agent và Policy Agent phía sau kiểm tra được, và giúp batch 50 case cho ra output ổn định giữa các lần chạy.

Đây cũng là nguyên tắc thống nhất với các investigation agent khác trong nhóm (xem `architecture.md`).

## 6. Một Lỗi Đã Xử Lý

Vấn đề đáng chú ý là ranh giới giữa "giao trễ" và "không đủ căn cứ trễ" khi dữ liệu ngày bị thiếu. Ban đầu nếu chỉ so sánh `delivered_customer_date > estimated_date` mà không kiểm tra tồn tại, một order chưa giao (customer date rỗng) có thể tạo ra so sánh với giá trị NaN và làm nhiễu kết luận của Policy.

Cách xử lý:

- Bọc mọi phép so sánh bằng `pd.notna()` cho cả estimated date, customer date, carrier date và shipping limit.
- Ép các field ngày trả ra `None` khi thiếu, thay vì để chuỗi "NaT".
- Đảm bảo `delivered_late` và `seller_handoff_late` chỉ `True` khi có đủ hai mốc thời gian hợp lệ để so sánh.

Kết quả này được kiểm chứng gián tiếp qua `tests/test_policy.py`, nơi các case `canceled` / `unavailable` được mock đúng contract của tôi và Policy vẫn phân loại đúng mà không rơi vào nhánh giao trễ.

## 7. Hiểu Biết Về Luồng End-to-End

Luồng bắt đầu từ `input/EC_xxx.json`. Coordinator (Member A) đọc `claimed_order_id`, dùng Data Loader lấy `OrderBundle`, rồi gọi các fact agent.

Trong đó hai agent của tôi đóng vai điều tra:

- **Order & Seller Agent** trả lời: đơn ở trạng thái nào, gồm những item/seller nào, và có seller nào bàn giao cho carrier sau hạn không.
- **Delivery Agent** trả lời: khách có nhận hàng trễ so với ngày ước tính không, và mang theo tín hiệu `carrier_after_limit`.

Hai facts này được đưa vào Policy Agent (Member C) cùng output của Payment Agent. Policy áp `EC_POLICY_V1` theo thứ tự ưu tiên: các rule như `canceled_order_paid` được ưu tiên trước, và chỉ khi đơn thực sự giao trễ thì mới dùng `seller_handoff_late` để chọn giữa lỗi seller hay lỗi logistics. Cuối cùng Coordinator dựng output và Verifier Agent kiểm tra trước khi ghi ra `output/EC_*.json`.

Điều tôi rút ra là chất lượng của toàn hệ thống phụ thuộc vào độ chính xác của facts đầu vào: nếu Order & Seller Agent hoặc Delivery Agent gán sai một mốc thời gian, quyết định phân loại và số tiền hoàn phía sau sẽ sai theo, dù Policy hoàn toàn đúng logic.

## 8. Cam Kết Cá Nhân

- [x] Báo cáo phản ánh đúng phần việc tôi đã thực hiện.
- [x] Tôi có thể giải thích luồng end-to-end của hệ thống.
- [x] Tôi không đưa `.env`, API key, token hoặc secret vào báo cáo.
- [x] Tôi đã kiểm chứng bằng test phân loại và batch output.
- [x] Báo cáo không sao chép nguyên văn báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Lê Trần Khương Duy  
**MSSV:** 2A202601349  
**Ngày xác nhận:** 2026-08-05
