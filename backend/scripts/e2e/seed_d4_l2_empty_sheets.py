#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 D4 空载荷 sheet 灌入可定位 L2 样本（PUT checklist-responses）。"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9980"
PROJECT_ID = "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49"
WP_ID = "b3ab3c46-828f-4f48-950e-aee9bbdc923f"
SEED_AMT = 77888.25


def http_json(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {e.code}: {detail[:800]}") from e


def login() -> str:
    body = http_json("POST", "/api/auth/login", {"username": "admin", "password": "admin123"})
    token = (body.get("data") or {}).get("access_token") or body.get("access_token")
    if not token:
        raise RuntimeError(f"login failed: {body}")
    return token


def get_items(token: str) -> dict[str, dict]:
    body = http_json(
        "GET",
        f"/api/workpapers/{WP_ID}/checklist-responses?project_id={PROJECT_ID}",
        token=token,
    )
    rows = body.get("data") or body
    out: dict[str, dict] = {}
    for r in rows:
        out[str(r["item_id"])] = r
    return out


def parse_remark(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def build_seeds(existing: dict[str, dict]) -> list[tuple[str, object]]:
    seeds: list[tuple[str, object]] = []

    # D4-6 fixed indicators
    seeds.append((
        "D4-6-indicators-v2",
        [{
            "key": "ar-to-assets",
            "name": "应收账款/总资产",
            "formula": "",
            "source": "L2seed",
            "current": SEED_AMT,
            "prior": 1000,
            "analysis1": "L2seed",
            "industryAvg": 0.12,
            "analysis2": "",
        }],
    ))

    # D4-7 products — mutate existing zeros if present
    d47 = parse_remark((existing.get("D4-7-products") or {}).get("remark"))
    if isinstance(d47, list) and d47:
        row = dict(d47[0])
        row["name"] = row.get("name") or "L2种子产品"
        row["curQty"] = SEED_AMT
        row["curRevenue"] = SEED_AMT * 10
        row["curCost"] = SEED_AMT * 6
        d47[0] = row
        seeds.append(("D4-7-products", d47))
    else:
        seeds.append((
            "D4-7-products",
            [{"rowId": "l2-seed-p1", "name": "L2种子产品", "curQty": SEED_AMT,
              "curRevenue": SEED_AMT * 10, "curCost": SEED_AMT * 6,
              "priorQty": 0, "priorRevenue": 0, "priorCost": 0, "remark": ""}],
        ))

    # D4-8 matrix product[0].months[0]
    d48 = parse_remark((existing.get("D4-8-products") or {}).get("remark"))
    if isinstance(d48, list) and d48:
        p0 = dict(d48[0])
        p0["name"] = p0.get("name") or "L2种子品"
        months = list(p0.get("months") or [])
        while len(months) < 12:
            months.append({"revQty": 0, "revPrice": 0, "revAmt": 0, "costQty": 0, "costPrice": 0, "costAmt": 0})
        m0 = dict(months[0]) if isinstance(months[0], dict) else {}
        m0["revQty"] = SEED_AMT
        m0["revPrice"] = 12.5
        m0["revAmt"] = SEED_AMT * 12.5
        months[0] = m0
        p0["months"] = months
        d48[0] = p0
        seeds.append(("D4-8-products", d48))
    else:
        month = {"revQty": SEED_AMT, "revPrice": 12.5, "revAmt": SEED_AMT * 12.5,
                 "costQty": 0, "costPrice": 0, "costAmt": 0}
        seeds.append((
            "D4-8-products",
            [{"name": "L2种子品",
              "months": [month] + [{"revQty": 0, "revPrice": 0, "revAmt": 0, "costQty": 0, "costPrice": 0, "costAmt": 0}] * 11,
              "priorMonths": [{"revQty": 0, "revPrice": 0, "revAmt": 0, "costQty": 0, "costPrice": 0, "costAmt": 0}] * 12,
              "industry": [{"revQty": 0, "revPrice": 0, "revAmt": 0}] * 3}],
        ))

    # D4-9：必须用 substrate 已有 UUID（GTROW-D49C-0013…），禁止自造 rowId（会触发插行 fail-closed）
    seeds.append((
        "D4-9-data",
        {
            "current": {
                "rows": [{
                    "rowId": "GTROW-D49C-0013",
                    "name": "L2种子客户",
                    "amount": SEED_AMT,
                    "quantity": 100,
                    "priorRank": 1,
                }],
                "totalAmount": SEED_AMT,
                "totalQuantity": 100,
            },
            "prior": {"rows": [], "totalAmount": 0, "totalQuantity": 0},
        },
    ))

    # D4-11 product price
    seeds.append((
        "D4-11-data",
        [{
            "rowId": "l2-seed-pp1",
            "customer": "L2客户",
            "product": "规格A",
            "unitPrice": SEED_AMT,
            "quantity": 10,
            "invoiceDate": "2025-06-01",
            "orderNo": "SO-L2",
            "orderDate": "2025-05-01",
            "listPrice": SEED_AMT,
            "marketPrice": SEED_AMT,
            "reason": "L2seed",
            "priceSource": "市场",
            "remark": "",
        }],
    ))

    # D4-12 contracts (array)
    seeds.append((
        "D4-12-contracts-v2",
        [{
            "id": "c-l2seed1",
            "indexNo": "D4-12-1",
            "label": "L2种子合同",
            "contractNo": "CT-L2-001",
            "counterparty": "L2对手方",
            "signDate": "2025-01-15",
            "serviceContent": "销售",
            "contractAmount": SEED_AMT,
            "deliveryTime": "",
            "deliveryMethod": "",
            "settlementMethod": "",
            "settlementTime": "",
            "warrantyClause": "",
            "returnClause": "",
            "breachClause": "",
            "specialTerms": "",
            "isSigned": "是",
            "isSealed": "是",
            "recognitionMethod": "时点",
            "acceptanceClause": "",
            "recognitionTime": "",
            "controlTransferDoc": "",
            "specialTransaction": "",
            "conclusion": "合理",
        }],
    ))

    # D4-14 nested transaction
    seeds.append((
        "D4-14-transactions",
        [{
            "id": "tx-l2seed1",
            "voucher": {
                "customerName": "L2客户",
                "date": "2025-12-20",
                "number": "记-001",
                "productName": "产品A",
                "quantity": "10",
                "amount": SEED_AMT,
            },
            "contract": {"date": "2025-12-01", "number": "HT-1"},
            "delivery": {
                "date": "2025-12-18", "number": "CK-1", "productName": "产品A",
                "quantity": "10", "warehouseKeeper": "仓管", "shippingApprover": "审批",
            },
            "shipping": {
                "date": "2025-12-19", "number": "YS-1", "quantity": "10",
                "company": "物流", "address": "地址",
            },
            "receipt": {
                "date": "2025-12-21", "productName": "产品A", "quantity": "10",
                "amount": SEED_AMT, "signer": "签收人", "sealType": "公章", "sealEntity": "客户",
            },
            "invoice": {
                "date": "2025-12-22", "number": "INV-1", "productName": "产品A",
                "quantity": "10", "amount": SEED_AMT,
            },
        }],
    ))

    # D4-15 completeness nested
    seeds.append((
        "D4-15-items",
        [{
            "id": "cmp-l2seed1",
            "delivery": {
                "date": "2025-11-01", "number": "FH-1", "productName": "品A",
                "quantity": "5", "amount": SEED_AMT,
            },
            "invoice": {
                "date": "2025-11-02", "number": "FP-1", "productName": "品A",
                "quantity": "5", "amount": SEED_AMT,
            },
            "voucher": {
                "date": "2025-11-03", "number": "JZ-1", "productName": "品A",
                "quantity": "5", "amount": SEED_AMT,
            },
        }],
    ))

    # D4-16 export
    seeds.append((
        "D4-16-rows",
        [{
            "id": "exp-l2seed1",
            "bookAmount": SEED_AMT,
            "portsPeriod": "2025Q4",
            "portsAmount": SEED_AMT,
            "portsReason": "",
            "taxReportAmount": SEED_AMT,
            "taxReason": "",
            "taxIndex": "IDX-1",
        }],
    ))

    # D4-17 / 18 cutoff
    seeds.append((
        "D4-17-rows",
        [{
            "id": "cf-l2seed1",
            "voucherDate": "2025-12-28",
            "voucherNo": "记-L2",
            "voucherProduct": "品A",
            "voucherQty": "3",
            "voucherAmount": SEED_AMT,
            "deliveryDate": "2025-12-29",
            "deliveryNo": "FH-L2",
            "deliveryProduct": "品A",
            "deliveryQty": "3",
            "deliveryAmount": SEED_AMT,
        }],
    ))
    seeds.append((
        "D4-18-rows",
        [{
            "id": "cb-l2seed1",
            "deliveryDate": "2025-12-28",
            "deliveryNo": "FH-L2b",
            "deliveryProduct": "品A",
            "deliveryQty": "3",
            "deliveryAmount": SEED_AMT,
            "voucherDate": "2025-12-30",
            "voucherNo": "记-L2b",
            "voucherProduct": "品A",
            "voucherQty": "3",
            "voucherAmount": SEED_AMT,
        }],
    ))

    # D4-19 discount
    seeds.append((
        "D4-19-rows",
        [{
            "id": "dc-l2seed1",
            "customerName": "L2客户",
            "discountType": "销售折扣",
            "revenueAmount": SEED_AMT,
            "discountAmount": 1000,
            "reason": "L2seed",
            "voucherDate": "2025-10-01",
            "voucherNo": "记-DC",
            "accountSubject": "6001",
            "detailSubject": "",
            "debitAmount": 1000,
            "creditAmount": 0,
            "approvalDate": "2025-09-30",
            "approver": "审批人",
        }],
    ))

    # D4-20 summary — mutate existing array of 2
    d20 = parse_remark((existing.get("D4-20-summary") or {}).get("remark"))
    if isinstance(d20, list) and d20:
        row0 = dict(d20[0])
        row0["currentReturn"] = SEED_AMT
        row0["currentRevenue"] = SEED_AMT * 20
        d20[0] = row0
        if len(d20) > 1:
            row1 = dict(d20[1])
            row1["currentReturn"] = SEED_AMT / 2
            row1["currentRevenue"] = SEED_AMT * 10
            d20[1] = row1
        seeds.append(("D4-20-summary", d20))
    else:
        seeds.append((
            "D4-20-summary",
            [
                {"currentReturn": SEED_AMT, "currentRevenue": SEED_AMT * 20, "priorReturn": 0, "priorRevenue": 0},
                {"currentReturn": SEED_AMT / 2, "currentRevenue": SEED_AMT * 10, "priorReturn": 0, "priorRevenue": 0},
            ],
        ))

    # D4-21 related party
    seeds.append((
        "D4-21-rows",
        [{
            "rowId": "rp-l2seed1",
            "partyName": "L2关联方",
            "relationship": "联营企业",
            "product": "产品A",
            "qty": 100,
            "salesAmount": SEED_AMT,
            "salesRatio": 0.1,
            "avgPrice": SEED_AMT / 100,
            "nonrelatedAvgPrice": SEED_AMT / 90,
            "fairPrice": SEED_AMT / 95,
            "priorSalesRatio": 0.08,
            "priorAvgPrice": SEED_AMT / 110,
            "remark": "L2seed",
        }],
    ))

    # D4-23 invoice compare — fill mainRevenue on existing months
    d23 = parse_remark((existing.get("D4-23-rows") or {}).get("remark"))
    if isinstance(d23, list) and d23:
        for i, row in enumerate(d23):
            r = dict(row)
            if i == 0:
                r["mainRevenue"] = SEED_AMT
                r["otherRevenue"] = 1000
                r["invoiceAmount"] = SEED_AMT + 1000
            d23[i] = r
        seeds.append(("D4-23-rows", d23))
    else:
        seeds.append((
            "D4-23-rows",
            [{"month": f"{m}月", "mainRevenue": SEED_AMT if m == 1 else 0,
              "otherRevenue": 0, "invoiceAmount": SEED_AMT if m == 1 else 0} for m in range(1, 13)],
        ))

    # D4-24 third party
    seeds.append((
        "D4-24-rows",
        [{
            "rowId": "tp-l2seed1",
            "seq": "1",
            "customerName": "L2客户",
            "annualSales": SEED_AMT,
            "endingAr": 5000,
            "thirdPartyAmount": SEED_AMT / 2,
            "payerName": "第三方付款人",
            "reason": "代付",
            "payerCustomerRelation": "关联",
            "payerEntityRelation": "无",
            "hasPaymentAgreement": "是",
            "isConfirmed": "是",
            "rationality": "合理",
            "indexNo": "IDX-TP",
        }],
    ))

    # D4-33 other margin matrix
    biz_id = "biz-l2seed1"
    month0 = {"revenue": SEED_AMT, "cost": SEED_AMT * 0.6}
    months_arr = [month0] + [{"revenue": 0, "cost": 0} for _ in range(11)]
    seeds.append((
        "D4-33-data",
        {
            "bizTypes": [
                {"id": biz_id, "name": "出租固定资产"},
                {"id": "biz-l2seed2", "name": "出租无形资产"},
                {"id": "biz-l2seed3", "name": "销售材料"},
            ],
            "months": {
                biz_id: months_arr,
                "biz-l2seed2": [{"revenue": 0, "cost": 0} for _ in range(12)],
                "biz-l2seed3": [{"revenue": 0, "cost": 0} for _ in range(12)],
            },
            "priorYear": {},
        },
    ))

    # D4-34 rentals
    seeds.append((
        "D4-34-data",
        {
            "rentals": [{
                "id": "rt-l2seed1",
                "tenant": "L2承租方",
                "period": "2025全年",
                "area": "100㎡",
                "unitPrice": SEED_AMT,
                "contractRef": "CT-R1",
                "actualMonths": 12,
                "expectedRevenue": SEED_AMT * 12,
                "actualRevenue": SEED_AMT * 12,
                "indexRef": "IDX-R",
            }],
            "consults": [],
        },
    ))

    # D4-36 cutoff
    seeds.append((
        "D4-36-data",
        {
            "forward": [{
                "id": "ct-l2seed1",
                "voucherDate": "2025-12-28",
                "voucherNo": "记-OC",
                "voucherProduct": "其他业务",
                "voucherQty": "1",
                "voucherAmount": SEED_AMT,
                "docDate": "2025-12-29",
                "docNo": "DJ-1",
                "docProduct": "其他业务",
                "docQty": "1",
                "docAmount": SEED_AMT,
                "isCrossing": "×",
            }],
            "backward": [],
        },
    ))

    return seeds


def put_seeds(token: str, seeds: list[tuple[str, object]]) -> None:
    items = [
        {"item_id": item_id, "conclusion": None, "remark": dumps(payload)}
        for item_id, payload in seeds
    ]
    # batch in chunks of 8
    for i in range(0, len(items), 8):
        chunk = items[i:i + 8]
        http_json(
            "PUT",
            f"/api/workpapers/{WP_ID}/checklist-responses",
            {"project_id": PROJECT_ID, "items": chunk},
            token=token,
        )
        print(f"PUT ok items={len(chunk)}: {[x['item_id'] for x in chunk]}")


def verify_projection(token: str) -> dict[str, float | str | None]:
    body = http_json(
        "GET",
        f"/api/projects/{PROJECT_ID}/workpapers/{WP_ID}/sync/entries/"
        f"xlsx%2Fgt-d4-operating-revenue/store-projection",
        token=token,
    )
    values = ((body.get("data") or {}).get("projection") or {}).get("values") or {}
    table_keys = {
        "D4-6": "d4_6_indicators",
        "D4-7": "d4_7_products",
        "D4-8": "d4_8_matrix",
        "D4-9": "customer_current_rows",
        "D4-11": "d4_11_rows",
        "D4-12": "contract_inspection_transposed",
        "D4-14": "walkthrough_transactions",
        "D4-15": "completeness_check_rows",
        "D4-16": "export_customs_check_rows",
        "D4-17": "d4_17_rows",
        "D4-18": "d4_18_rows",
        "D4-19": "d4_19_rows",
        "D4-20": "d4_20_summary",
        "D4-21": "related_party_price_rows",
        "D4-23": "invoice_compare_rows",
        "D4-24": "third_party_receipt_rows",
        "D4-33": "d4_33_matrix",
        "D4-34": "d4_34_rentals",
        "D4-36": "d4_36_forward",
    }
    report: dict[str, float | str | None] = {}
    for code, tk in table_keys.items():
        sample = None
        for k, field in values.items():
            if not str(k).startswith(tk + "/"):
                continue
            v = field.get("value") if isinstance(field, dict) else None
            try:
                n = float(v)
            except (TypeError, ValueError):
                if isinstance(v, str) and v.strip():
                    sample = v[:40]
                    break
                continue
            if abs(n) > 1:
                sample = n
                break
        report[code] = sample
    return report


def main() -> int:
    token = login()
    existing = get_items(token)
    seeds = build_seeds(existing)
    put_seeds(token, seeds)
    report = verify_projection(token)
    ok = sum(1 for v in report.values() if v is not None)
    print(json.dumps({"seeded_items": len(seeds), "projection_hits": ok, "report": report}, ensure_ascii=False, indent=2))
    return 0 if ok >= 15 else 1


if __name__ == "__main__":
    sys.exit(main())
