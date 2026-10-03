# Task 5: 三家性能基线

**measured_at**: 2026-09-26
**method**: 合成 payload 5 行（adapter 未注册故非真栈）

## 基线数据

| 循环 | contract_build_ms | projection_5rows_ms | field_count | store_item_id | adapter_registered |
|---|---|---|---|---|---|
| D5 | 95.5 | 1.0 | 85 | D5-2-rows | False |
| D6 | 257.3 | 0.4 | 150 | D6-2-rows | False |
| D7 | 278.2 | 0.8 | 135 | D7-2-rows | False |

## 说明

- **三家 adapter_registered 全 False**（真库只注册 {d2,d4,g7,h1}）⇒ 真栈端到端整册 materialize 不可测
- 合成 payload 仅含 `rowId`/`customerName`/`priorUnadjusted` 三个基本字段
- `field_count` 差异来自 D6/D7 的 aging 字段（flat/nested 各自展开）
- 后续每批次接入后重测并与本基线对比，耗时增长超过 10% 须排查

## `[ ]*` 真栈卡点

- 三家均卡 `adapter_registered=False`（裁决 G6）
- 平台级供给缺口（umbrella BP-61-1）：186 个 planned entry 无一注册上
- 代码已改但未实测，卡 adapter 未注册，非本 spec 实现缺陷（`upstream_gap`）
