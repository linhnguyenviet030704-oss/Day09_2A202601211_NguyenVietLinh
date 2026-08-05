# Member Role Report - Day 9: Multi Agent A2A

## 1. Thong tin ca nhan

| Thong tin | Noi dung |
| --- | --- |
| Ho va ten | Nguyen Viet Linh |
| MSSV | 2A202601211 |
| Khoa/Lop | K3 |
| Vai tro chinh | Member A - Data + Coordinator + Runner (Backbone) |
| Ngay hoan thanh | 2026-08-05 |

## 2. Vai tro va pham vi cong viec

### Phan viec so huu

| Module/deliverable | File/ham phu trach | Input nhan vao | Output ban giao | Trang thai |
| --- | --- | --- | --- | --- |
| Data loader va order lookup | `src/core/data.py` - `DataLoader`, `get_order_bundle()` | Thu muc `data/`, `claimed_order_id` | `OrderBundle` gom `order`, `items`, `payments`, `sellers` | Hoan thanh |
| Coordinator Agent | `src/core/coordinator.py` - `Coordinator.process_case()` | Input case JSON, facts tu 3 fact agents, policy result | Output JSON dung schema README, co cap ID/evidence va qua verifier gate | Hoan thanh |
| Architecture document | `architecture.md` | Yeu cau kien truc multi-agent trong de bai | Tai lieu mo ta vai tro agent, handoff flow, verifier gate | Hoan thanh |
| Batch runner 50 cases | `src/run.py` | 50 file `input/EC_*.json` | Ghi `output/EC_*.json` | Chua hoan thanh |
| Trace va metadata runtime | `logging/trace.jsonl`, `logging/metadata.json` | Qua trinh chay that, thong tin model/runtime | File trace va metadata de nop kem repo | Chua hoan thanh |

Phan viec chinh cua toi la phan "backbone": tao lop nap du lieu dung mot lan, dieu phoi cac agent con, lap output cuoi cung va mo ta kien truc de ca nhom co chung contract khi tich hop.

### Viec ho tro ngoai pham vi chinh

| Hoat dong | Thanh vien/module duoc ho tro | Ket qua |
| --- | --- | --- |
| Viet unit test cho backbone | `tests/test_data.py`, `tests/test_coordinator.py` | Co bai kiem tra cho DataLoader va Coordinator, giup xac minh filter dung row, retry 1 lan va cap output truoc verifier |

## 3. Ket qua theo vai tro

| Nhiem vu da thuc hien | File/ham/artifact lien quan | Ket qua ban giao | Cach xac minh |
| --- | --- | --- | --- |
| Nap 4 bang CSV can thiet va tra bundle theo `order_id` | `src/core/data.py` | `OrderBundle` tra ve 4 `DataFrame` da loc theo order | `python -m unittest tests.test_data` |
| Dieu phoi OrderSeller/Payment/Delivery, kiem tra thieu facts, retry 1 lan neu can | `src/core/coordinator.py` | Luong `LOAD_CASE -> CHECK_COMPLETENESS -> LOCK_FACTS -> POLICY -> VERIFY` | `python -m unittest tests.test_coordinator` |
| Gioi han output theo rubric | `src/core/coordinator.py` | Cap toi da 5 entity IDs, 10 evidence, 3 causes, 3 parties, 5 actions | `python -m unittest tests.test_coordinator` |
| Mo ta kien truc de tich hop nhom | `architecture.md` | Tai lieu hoa vai tro cac agent va verifier gate | Doc `architecture.md` doi chieu voi README |

Artifact cu the ma phan viec cua toi tao ra la `OrderBundle` cho mot case va output candidate do `Coordinator` lap truoc khi qua `VerifierAgent`. Hai artifact nay la diem noi giua phan data/fact agents va phan policy/verifier cua nhom.

## 4. Giai thich phan ky thuat da thuc hien

### Van de can giai quyet

Role A phai giai quyet hai bai toan nen tang:

1. Doc du lieu Olist mot cach gon va on dinh de cac agent khong phai mo CSV lap lai cho tung case.
2. Dieu phoi cac agent con theo chung contract, khong de Policy Agent ra quyet dinh khi facts con thieu hoac output vuot gioi han de bai.

### Cach trien khai

Toi tach backbone thanh hai phan:

- `DataLoader` doc 4 CSV can thiet (`orders`, `order_items`, `order_payments`, `sellers`) ngay khi khoi tao, kiem tra cot bat buoc, sau do dung `claimed_order_id` de loc va tao `OrderBundle`.
- `Coordinator` nhan input case, goi 3 fact agents, danh gia facts thieu bang `_missing_agents()`, retry dung agent bi thieu mot lan, khoa facts bang `deepcopy`, goi `PolicyAgent`, lap output cuoi cung bang `_assemble_output()`, roi moi dua qua `VerifierAgent`.

Trong luc lap output, toi chu dong cap cac tap ID va evidence theo dung gioi han rubric de tranh bi hard gate do vuot so luong phan tu.

### Input, output va contract

| Thanh phan | Mo ta |
| --- | --- |
| Input | 1 case JSON trong `input/EC_*.json`, dac biet la `case_id` va `customer_request.claimed_order_id` |
| Output | 1 dict dung schema output cua README, gom `assessment`, `affected_entities`, `root_cause_analysis`, `evidence_ids`, `financial_resolution`, `resolution_actions` |
| Module phu thuoc | `src/core/data.py`, 3 fact agents, `PolicyAgent`, `VerifierAgent` |
| Module su dung output | `run.py` khi batch runner hoan tat; nhom dung output nay de ghi `output/EC_*.json` |
| Dieu kien loi can xu ly | Thieu key bat buoc trong input, CSV thieu cot, fact agent tra thieu field, verifier reject output |

### Cach xac minh

```bash
python -m unittest tests.test_data tests.test_coordinator
```

- Ket qua mong doi: ca 2 test pass; DataLoader loc dung row; Coordinator retry 1 lan va khong tra output neu verifier reject.
- Ket qua thuc te: 2 test pass tren workspace hien tai.
- Artifact/log: `tests/test_data.py`, `tests/test_coordinator.py`.

## 5. Mot quyet dinh ky thuat quan trong

- Boi canh: fact agents co the tra ve thieu du lieu, nhung policy van can duoc goi theo thu tu nghiep vu dung.
- Cac phuong an da can nhac: goi policy ngay sau lan dau; retry vo han; retry co kiem soat 1 lan roi khoa facts.
- Phuong an da chon: Coordinator retry dung agent bi thieu facts mot lan, sau do khoa facts va dua qua policy/verifier.
- Ly do: retry 1 lan du de sua cac truong hop handoff thieu field ma khong bien coordinator thanh vong lap kho debug. Cach nay giu output reproducible va trace ro rang hon.
- Bang chung quyet dinh phu hop: `tests/test_coordinator.py` co case Payment Agent lan 1 tra thieu data, lan 2 du data; test xac nhan Coordinator goi lai dung 1 lan va van cap output theo rubric.

## 6. Mot loi hoac blocker da xu ly

- Trieu chung/loi nguyen van: fact agent co the tra ve mot phan ket qua, vi du chi co `num_rows` ma chua co `payment_total`, `item_total`, `freight_total`.
- Lenh hoac buoc tai hien: chay `python -m unittest tests.test_coordinator`.
- Nguyen nhan goc: contract giua cac agent can duoc kiem tra o tang coordinator, neu khong policy se danh gia tren du lieu thieu.
- Cach xu ly: them `_missing_agents()` de phat hien thieu facts theo `order_status`, sau do retry dung agent bi thieu mot lan truoc khi lock facts.
- Cach xac minh sau khi sua: test `test_retries_missing_agent_once_and_caps_output_before_verification` pass va bien dem `calls["payment"] == 2`.
- Dieu hoc duoc: trong multi-agent, coordinator phai la noi chiu trach nhiem cho completeness gate, khong nen dat ky vong moi agent con luon tra ve du ngay lan dau.

## 7. Hieu biet ve luong end-to-end

Trong bai lab nay, luong du lieu di theo huong: `input/EC_xxx.json` -> `Coordinator` doc `claimed_order_id` -> `DataLoader` lay bundle tu CSV -> cac fact agents phan tich theo domain (`order_seller`, `payment`, `delivery`) -> `PolicyAgent` ap dung `EC_POLICY_V1` -> `VerifierAgent` kiem tra schema/evidence/so tien -> ghi output JSON. Evidence IDs va entity IDs phai dung duoc truc tiep tu CSV thay vi tu suy dien, vi day la phan duoc cham diem va can kiem chung. Completeness check khac verifier gate o cho completeness check xay ra truoc policy de bao dam du facts, con verifier gate xay ra sau khi da co output candidate de chan schema sai, evidence sai dinh dang hoac vuot gioi han rubric. Can dung cung mot bo 50 case khi so sanh cac lan sua de biet chat luong thay doi do code, khong phai do bo input khac nhau. Mot lan sua duoc xem la thanh cong khi unit test pass, output dung schema, va khi runner hoan tat thi trace/metadata phai phan anh dung luot chay moi nhat.

## 8. Cam ket cua thanh vien

- [x] Noi dung bao cao phan anh dung phan viec va muc hieu cua toi.
- [x] Toi co the giai thich luong end-to-end, khong chi module minh phu trach.
- [x] Toi khong ghi "da chay thanh cong" cho phan chua duoc kiem chung.
- [x] Bao cao khong chua `.env`, API key, token hoac secret.
- [x] Bao cao nay khong phai ban sao nguyen van cua bao cao nhom hoac bao cao thanh vien khac.

**Ho va ten:** Nguyen Viet Linh  
**Ngay xac nhan:** 2026-08-05
