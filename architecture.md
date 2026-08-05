# Architecture — K3 Day 09 Multi-Agent E-commerce Dispute Resolution

## 1. Sơ đồ agent và luồng handoff

```
input/EC_xxx.json
        |
        v
+--------------------+
|  Coordinator Agent  |  agents/coordinator.py
|  (dispatch/collect) |
+----------+---------+
           |
           |  order_id = customer_request.claimed_order_id
           v
+----------------------+
|  core/data.py         |  load 9 CSV 1 lần, index theo order_id
|  get_order_bundle()   |  -> order row + items + payments + seller rows
+----------+-----------+
           |
   --------+-------------------------------------
   |                  |                          |
   v                  v                          v
+-------------+  +-------------------------+   +----------------+
| Order &     |  | Delivery Agent          |   | Payment Agent  |
| Seller      |  | agents/delivery.py      |   | agents/        |
| Agent       |  | -> {estimated_date,     |   | payment.py     |
| agents/     |  |     delivered_customer_ |   | -> {payments[],|
| order_      |  |     date, delivered_    |   |   payment_     |
| seller.py   |  |     late,               |   |   total,       |
| -> {order_  |  |     carrier_after_limit}|   |   item_total,  |
| status,     |  +------------+-------------+   |   freight_    |
| items[],    |               |                  |   total,      |
| seller_ids[]|               |                  |   reconciled, |
| , seller_   |               |                  |   split_      |
| handoff_    |               |                  |   payment}    |
| late, ...}  |               |                  +-------+-------+
+------+------+               |                          |
       |                      |                          |
       +----------------------+--------------------------+
                               |
                               v  (3 JSON theo contract chung)
                    +----------------------+
                    |   Policy Agent        |  agents/policy.py
                    |   apply EC_POLICY_V1  |  6 rule, đúng thứ tự ưu tiên
                    |   -> primary_issue,   |
                    |   responsible_party,  |
                    |   cause_code, refund, |
                    |   actions             |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |   Verifier Agent      |  agents/verifier.py
                    |   - evidence ID có    |
                    |     thật trong data   |
                    |   - cap số lượng      |
                    |   - rounding 2dp      |
                    |   - schema hợp lệ     |
                    +----------+-----------+
                               |
                    ok? -------+------- không ok?
                     |                        |
                     v                        v
          Coordinator ghi              Coordinator log lỗi,
          output/EC_xxx.json           KHÔNG ghi file (hard gate)
                     |
                     v
          Coordinator gọi gpt-4o-mini (triage, best-effort,
          không override quyết định) -> ghi vào logging/trace.jsonl
```

Handoff là JSON theo **1 contract chung**, không phải một prompt LLM duy nhất xử lý mọi thứ:

```
order_seller: {order_status, items[{item_id,seller_id,price,freight_value,shipping_limit_date}],
               seller_ids[], delivered_carrier_date, seller_handoff_late,
               late_seller_ids[], late_item_ids[]}
delivery:     {estimated_date, delivered_customer_date, delivered_late, carrier_after_limit}
payment:      {payments[{sequential,value}], payment_total, item_total, freight_total,
               num_rows, reconciled, split_payment}
```

## 2. Vai trò và quyền truy cập

| Agent | File | Input | Output | Truy cập dữ liệu |
| --- | --- | --- | --- | --- |
| Coordinator | `agents/coordinator.py` | 1 case JSON từ `input/` | dispatch tới các agent, tổng hợp & ghi `output/EC_xxx.json`, ghi `logging/trace.jsonl` | Gọi `core/data.py`, gọi tất cả agent khác |
| Order & Seller | `agents/order_seller.py` | `OrderBundle` (order + items + sellers) | contract `order_seller` | Chỉ đọc `OrderBundle` được Coordinator truyền vào |
| Delivery | `agents/delivery.py` | `OrderBundle` + output của Order & Seller (`seller_handoff_late`) | contract `delivery` | Chỉ đọc `OrderBundle` |
| Payment | `agents/payment.py` | `order_id`, danh sách item rows, danh sách payment rows | contract `payment` | Không import module nào khác trong repo — nhận data thuần qua tham số |
| Policy | `agents/policy.py` | contract `order_seller` + `delivery` + `payment` | `assessment`, `affected_entities`, `root_cause_analysis`, `financial_resolution`, `resolution_actions` (+ `_cause_code` nội bộ) | Không truy cập CSV trực tiếp, chỉ nhận JSON từ 3 agent trên |
| Verifier | `agents/verifier.py` | output của Policy + contract `order_seller`/`payment` (để đối chiếu ID) | `(is_valid, errors, final_case_dict)` | Không import `core/data.py`; chỉ tin dữ liệu được truyền vào — mọi evidence ID phải khớp với `order_seller.items`/`seller_ids` hoặc `payment.payments` |
| Data loader | `core/data.py` | 9 CSV trong `data/` | `get_order_bundle(order_id)` | Nguồn dữ liệu gốc duy nhất, load 1 lần |
| LLM client | `core/llm_client.py` | system/user prompt | JSON hoặc text | Gọi OpenAI API (`gpt-4o-mini`), key từ `.env` |

## 3. Vì sao các agent nghiệp vụ là deterministic (không gọi LLM để ra quyết định)

`payment.py`, `policy.py`, `verifier.py`, `order_seller.py`, `delivery.py` đều là hàm Python thuần, không gọi LLM. Lý do:

- Các thành phần này quyết định trực tiếp `primary_issue`, `responsible_party`, `financial_resolution`, `evidence_ids` — chiếm ~70% trọng số chấm điểm (root cause 15% + evidence 15% + financial 20% + một phần primary issue 20%). Đây là phép so sánh ngày tháng và cộng trừ tiền có thể tính chính xác 100% bằng code, để LLM quyết định chỉ thêm rủi ro sai số/không nhất quán mà không tăng độ chính xác.
- README mục 9 yêu cầu ưu tiên dữ liệu kiểm chứng được, không tự suy diễn — rule-based deterministic là cách đảm bảo điều này tuyệt đối.
- Việc chia thành 6 module riêng biệt (Order/Seller, Delivery, Payment, Policy, Verifier, Coordinator) với handoff JSON theo đúng contract vẫn thể hiện đúng tinh thần multi-agent (phân công, handoff, kiểm chứng chéo — không phải một prompt xử lý hết), dù không mỗi agent đều gọi LLM.

**Nơi LLM (`gpt-4o-mini`) thực sự được dùng:** Coordinator gọi 1 lần/case tới `gpt-4o-mini` (khai trong `core/llm_client.py`) để đối chiếu nội dung khiếu nại tự nhiên của khách với `primary_issue` đã quyết định theo rule — mang tính triage/log, best-effort (lỗi gọi API không làm fail case), **không bao giờ override** quyết định deterministic. Kết quả được ghi vào `logging/trace.jsonl`, không đưa vào `output/EC_xxx.json`.

> Lưu ý rủi ro: OpenAI không công bố số tham số của `gpt-4o-mini` nên không thể chứng minh tuyệt đối tuân thủ ràng buộc "≤10B parameters" (README mục 9.1). Nhóm đã cân nhắc và chọn model này theo quyết định chung; vì phần dùng LLM chỉ là triage phụ trợ (không quyết định output), rủi ro với điểm số được giảm thiểu tối đa.

## 4. Hard gate và cách tránh bị 0 điểm

Verifier chặn trước khi ghi file nếu:
- `order_id` không tồn tại trong `orders.csv`.
- Bất kỳ `item_id`/`seller_id`/`payment_id` nào không khớp với dữ liệu thật (bị loại khỏi `affected_entities`/`evidence_ids` và ghi lỗi).
- `cause_code` không nằm trong 6 mã hợp lệ.
- `confidence` ngoài `[0,1]`, `case_status` không hợp lệ, hoặc refund không nhất quán với `case_status`.
- Vượt cap: >5 ID/entity set, >10 evidence, >3 causes, >3 responsible parties, >5 actions.

Coordinator chỉ ghi `output/EC_xxx.json` khi Verifier trả `is_valid = True`.
