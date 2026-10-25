# Task 20 — canary 真库前置实证

**日期**：2026-09-27　**真库**：audit-postgres (Docker, healthy)

## D~I 硬标准在 J 不成立

primary managed table 三键 + 审定表 + 调整分录：
`J1-2-detail-shortTerm` / `J1-2-detail-postEmployment` / `J1-2-detail-severance` /
`J1-1-rows` / `J1-3-adjustment-rows` → **全部 0 行**（真库无数据）

## canary J1-6-short-term 非空确认

- `J1-6-short-term`: **3473 B**, conclusion NULL ✅
- J 循环全貌: **83** 个 item_id, conclusion **83/83 全 NULL**, remark 空串 **31** 个
- `J1-6-short-term` 是全 J 最大载荷 ✅

## 四候选裁决

| 候选 | 真库 | 裁决 |
|---|---|---|
| ✅ **J1-6-short-term** | 3473 B | entry 内 / 非 parent_dup / 单 sheet 单键组 / 安全 id |
| ❌ J1-disc-soe-short-term | 1325 B | 披露层叠 5 个最难形态 |
| ❌ J1-8-voucher-check | 911 B | 属 parent_duplicate |
| ❌ J1-2-detail-* | 0 B | 真库空 |
