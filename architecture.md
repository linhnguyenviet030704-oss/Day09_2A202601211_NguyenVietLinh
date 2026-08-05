# Architecture - Enhanced Coordinator Agent

## 1. Chốt kiến trúc

Hệ thống giữ cấu trúc multi-agent theo domain dữ liệu như README gợi ý, nhưng cải tiến trọng tâm nằm ở **Coordinator Agent**.

Coordinator không chỉ gọi các agent con rồi gom kết quả. Coordinator được nâng cấp thành một **Case Orchestrator** có:

- State machine cho từng case.
- Chuẩn handoff giữa các agent.
- Kiểm tra dữ liệu còn thiếu trước khi áp policy.
- Cơ chế gọi lại agent con một lần nếu thiếu facts.
- Conflict resolver.
- Verifier gate trước khi ghi output.
- Trace writer duy nhất cho `trace.jsonl`.

## 2. Sơ đồ agent

```text
input/EC_xxx.json
      |
      v
Enhanced Coordinator Agent
      |
      +--> Order & Seller Agent
      |
      +--> Payment Agent
      |
      +--> Delivery Agent
      |
      +--> Policy Agent
      |
      +--> Verifier Agent
      |
      v
output/EC_xxx.json
trace.jsonl
```

## 3. Enhanced Coordinator Agent

### 3.1 Vai trò

Coordinator là agent điều phối chính cho từng case.

Nhiệm vụ:

- Đọc `case_id`, `opened_at`, `claimed_order_id`, `policy_version`.
- Tạo trạng thái xử lý nội bộ cho case.
- Giao việc cho các agent con.
- Nhận handoff từ agent con theo format thống nhất.
- Kiểm tra facts tối thiểu trước khi gọi Policy Agent.
- Gọi lại agent con một lần nếu facts bị thiếu.
- Resolve xung đột giữa dữ liệu và đề xuất của agent con.
- Gọi Verifier Agent trước khi ghi output.
- Ghi `trace.jsonl` cho toàn bộ quá trình xử lý case.

Coordinator không tự bịa facts, không suy diễn evidence ngoài CSV, không bỏ qua thứ tự policy.

### 3.2 State nội bộ

Mỗi case có một state riêng:

```json
{
  "case_id": "EC_001",
  "order_id": "<claimed_order_id>",
  "policy_version": "EC_POLICY_V1",
  "status": "load_case",
  "facts": {
    "order": null,
    "items": [],
    "sellers": [],
    "payments": [],
    "delivery": null
  },
  "handoffs": [],
  "warnings": [],
  "decision": null,
  "verified": false
}
```

### 3.3 State machine

```text
LOAD_CASE
  -> DISPATCH_FACT_AGENTS
  -> MERGE_HANDOFFS
  -> CHECK_COMPLETENESS
  -> REPAIR_ONCE_IF_NEEDED
  -> LOCK_FACTS
  -> POLICY_DECISION
  -> BUILD_FINAL_OUTPUT
  -> VERIFY_OUTPUT
  -> WRITE_OUTPUT_AND_TRACE
```

Ý nghĩa từng bước:

```text
LOAD_CASE
  Đọc input case, lấy claimed_order_id.

DISPATCH_FACT_AGENTS
  Gọi Order & Seller Agent, Payment Agent, Delivery Agent.

MERGE_HANDOFFS
  Gom facts, evidence thô, warnings từ các agent con.

CHECK_COMPLETENESS
  Kiểm tra facts cần thiết theo order_status và loại claim.

REPAIR_ONCE_IF_NEEDED
  Nếu thiếu dữ liệu do agent con trả thiếu, gọi lại đúng agent đó một lần.

LOCK_FACTS
  Khóa facts đã xác minh để Policy Agent chỉ đọc, không sửa.

POLICY_DECISION
  Gọi Policy Agent áp dụng EC_POLICY_V1 theo đúng thứ tự ưu tiên.

BUILD_FINAL_OUTPUT
  Coordinator dựng JSON cuối từ facts + policy decision.

VERIFY_OUTPUT
  Gọi Verifier Agent kiểm tra schema, evidence, số tiền, giới hạn field.

WRITE_OUTPUT_AND_TRACE
  Chỉ ghi output nếu Verifier pass.
```

## 4. Chi tiết cải tiến Coordinator

### 4.1 Completeness check

Coordinator kiểm tra facts tối thiểu trước khi gọi Policy Agent.

```text
Nếu order_status = canceled:
  Cần order_status.
  Cần payment_total_brl.
  Không cần delivery facts.

Nếu order_status = unavailable:
  Cần order_status.
  Cần payment_total_brl.
  Không cần delivery facts.

Nếu order_status = delivered:
  Cần order_delivered_customer_date.
  Cần order_estimated_delivery_date.
  Cần order_delivered_carrier_date.
  Cần shipping_limit_date của item.
  Cần item_total_brl và freight_total_brl.

Nếu payment_row_count >= 2:
  Cần payment_total_brl.
  Cần item_total_brl + freight_total_brl.
  Cần payment_matches_order_total.
```

Nếu facts thiếu, Coordinator không để Policy Agent đoán.

### 4.2 Repair once

Coordinator chỉ retry một lần cho agent thiếu dữ liệu.

```text
Thiếu order_status
  -> gọi lại Order & Seller Agent.

Thiếu item hoặc seller facts
  -> gọi lại Order & Seller Agent.

Thiếu payment_total_brl
  -> gọi lại Payment Agent.

Thiếu delivery comparison
  -> gọi lại Delivery Agent.
```

Nếu retry vẫn thiếu, Coordinator ghi warning vào trace và chỉ dùng dữ liệu thật đang có.

Không retry vô hạn vì bài chỉ có 50 case và dữ liệu CSV ổn định.

### 4.3 Conflict resolver

Coordinator xử lý xung đột theo rule cố định:

```text
1. CSV data thắng customer_request.message.
2. EC_POLICY_V1 priority thắng mọi suggestion của agent con.
3. canceled_order_paid xét trước unavailable_order_paid.
4. canceled/unavailable paid xét trước late delivery.
5. Evidence không dựng được từ CSV thì loại bỏ.
6. Refund chỉ tính từ payment/item/freight facts.
7. Không dùng review, geolocation hoặc product metadata để suy diễn issue.
```

Ví dụ:

```text
Khách nói giao trễ,
nhưng CSV cho thấy order_status = canceled và payment_total_brl > 0
=> primary_issue = canceled_order_paid.
```

### 4.4 Verifier gate

Coordinator không ghi output ngay sau Policy Agent. Output phải qua Verifier Agent.

Verifier kiểm tra:

```text
- Đúng JSON schema.
- case_id khớp input.
- primary_issue thuộc danh sách hợp lệ.
- case_status chỉ là action_required hoặc no_action.
- confidence nằm trong [0, 1].
- affected_entities không vượt 5 ID mỗi loại.
- evidence_ids không vượt 10 ID.
- root causes không vượt 3.
- responsible parties không vượt 3.
- actions không vượt 5.
- evidence ID đúng format.
- evidence ID tồn tại trong dữ liệu đã đọc.
- Các giá trị tiền làm tròn 2 chữ số.
- refund > 0 thì case_status = action_required.
- refund = 0 thì case_status = no_action.
```

Nếu Verifier fail, Coordinator sửa lỗi format/evidence có thể sửa được từ facts. Nếu lỗi do facts thiếu, Coordinator ghi warning vào trace.

### 4.5 Trace ownership

Chỉ Coordinator ghi `trace.jsonl`.

Mỗi case ghi một dòng JSON:

```json
{
  "case_id": "EC_001",
  "order_id": "<order_id>",
  "steps": [
    {"agent": "CoordinatorAgent", "step": "LOAD_CASE", "status": "ok"},
    {"agent": "OrderSellerAgent", "status": "ok"},
    {"agent": "PaymentAgent", "status": "ok"},
    {"agent": "DeliveryAgent", "status": "ok"},
    {"agent": "CoordinatorAgent", "step": "CHECK_COMPLETENESS", "status": "ok"},
    {"agent": "PolicyAgent", "primary_issue": "late_delivery_seller"},
    {"agent": "VerifierAgent", "status": "passed"}
  ],
  "final_primary_issue": "late_delivery_seller",
  "final_refund_brl": 15.0
}
```

## 5. Agent con và quyền truy cập

### 5.1 Order & Seller Agent

Đọc:

```text
data/olist_orders_dataset.csv
data/olist_order_items_dataset.csv
data/olist_sellers_dataset.csv
```

Trả về:

```json
{
  "order_status": "delivered",
  "order_purchase_timestamp": "...",
  "order_delivered_carrier_date": "...",
  "order_delivered_customer_date": "...",
  "order_estimated_delivery_date": "...",
  "item_total_brl": 100.0,
  "freight_total_brl": 15.0,
  "item_ids": ["<order_id>:1"],
  "seller_ids": ["<seller_id>"],
  "late_seller_ids": ["<seller_id>"],
  "evidence_ids": [
    "order:<order_id>",
    "item:<order_id>:1",
    "seller:<seller_id>"
  ]
}
```

### 5.2 Payment Agent

Đọc:

```text
data/olist_order_payments_dataset.csv
```

Trả về:

```json
{
  "payment_total_brl": 115.0,
  "payment_row_count": 2,
  "payment_ids": ["<order_id>:1", "<order_id>:2"],
  "payment_matches_order_total": true,
  "evidence_ids": [
    "payment:<order_id>:1",
    "payment:<order_id>:2"
  ]
}
```

### 5.3 Delivery Agent

Đọc:

```text
data/olist_orders_dataset.csv
data/olist_order_items_dataset.csv
```

Trả về:

```json
{
  "delivered_after_estimate": true,
  "carrier_received_after_shipping_limit": true,
  "delivery_root_cause": "SELLER_HANDOFF_AFTER_LIMIT"
}
```

### 5.4 Policy Agent

Không đọc CSV trực tiếp. Chỉ nhận facts đã khóa từ Coordinator.

Áp dụng policy theo thứ tự:

```text
1. canceled_order_paid
2. unavailable_order_paid
3. late_delivery_seller
4. late_delivery_logistics
5. valid_split_payment
6. unsupported_late_claim
```

Trả về:

```json
{
  "primary_issue": "late_delivery_seller",
  "case_status": "action_required",
  "confidence": 0.92,
  "ranked_causes": [
    {"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1}
  ],
  "responsible_parties": [
    {"party_type": "seller", "party_id": "<seller_id>"}
  ],
  "recommended_refund_brl": 15.0,
  "resolution_actions": ["refund_freight"]
}
```

### 5.5 Verifier Agent

Không ra quyết định nghiệp vụ. Chỉ kiểm tra output candidate trước khi Coordinator ghi file.

Trả về:

```json
{
  "status": "passed",
  "errors": [],
  "warnings": []
}
```

## 6. Output final do Coordinator ghi

Coordinator ghi đúng schema README:

```json
{
  "case_id": "EC_001",
  "assessment": {
    "primary_issue": "late_delivery_seller",
    "case_status": "action_required",
    "confidence": 0.92
  },
  "affected_entities": {
    "order_ids": ["<order_id>"],
    "item_ids": ["<order_id>:1"],
    "seller_ids": ["<seller_id>"],
    "payment_ids": ["<order_id>:1"]
  },
  "root_cause_analysis": {
    "ranked_causes": [
      {"cause_code": "SELLER_HANDOFF_AFTER_LIMIT", "rank": 1}
    ],
    "responsible_parties": [
      {"party_type": "seller", "party_id": "<seller_id>"}
    ]
  },
  "evidence_ids": [
    "order:<order_id>",
    "item:<order_id>:1",
    "payment:<order_id>:1",
    "seller:<seller_id>",
    "policy:SELLER_HANDOFF_AFTER_LIMIT"
  ],
  "financial_resolution": {
    "currency": "BRL",
    "item_total_brl": 100.0,
    "freight_total_brl": 15.0,
    "payment_total_brl": 115.0,
    "recommended_refund_brl": 15.0
  },
  "resolution_actions": ["refund_freight"]
}
```
