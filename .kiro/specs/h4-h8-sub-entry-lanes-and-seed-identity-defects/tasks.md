# Implementation Plan

## Overview

**spec**：`h4-h8-sub-entry-lanes-and-seed-identity-defects`　**创建**：2026-09-26　
**状态**：0/18（Task 0~17），Design-First 未实施

**共同前置**：`h-cycle-sync-foundation-and-first-canary`（HC-1~HC-16）。
🔴 **本 spec 只引用 HC-x，不复述正文**。

**覆盖**：H4 工程物资 / H8 使用权资产（2 条独立 entry）+ **5 条 parent_duplicate 子入口**。
🔴 **本 lane 无 canary**（H4 真库零载荷、`H8-2-rows` 是 `[]`）。
🔴 **H8 无 TB 发布门**，本 spec 只登记缺口，补门归 `h2-h6-h10-pilot-cross-reference-lanes`。

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

## Tasks

### 阶段 0：前置门 + 链式复用图锁定

- [ ] 0. foundation 交付确认（不改代码，只核）
  - 确认 HC-1~HC-3 / HC-5 / HC-6 / HC-7 / HC-8 / HC-11 ~ HC-16 的 design 正文与判据已落地
  - 🔴 任一缺失 ⇒ 对应任务阻塞，不得在本 spec 内自行裁决
  - 证据 `evidence/task0-foundation-gate.md`

- [ ] 1. 链式复用图现算 + 「一并改」清单锁定（HS-P1）
  - 现算 `useH4DualMode` 生产消费点（期望 5）· `useH8DualMode`（期望 2）
  - 落 design §一 的 9 行清单；标注第 8/9 行跨 spec（lane 3 / foundation）
  - 🔴 变异「只改父宿主与 composable、不改子 Tab」SHALL 打红

- [ ] 2. 两条 entry + 5 条子入口现状红判据
  - 现算 manifest：2 条独立 + 5 条子入口全部 `capability=='single_onlyoffice'`、
    `capability_target is None`、`relationship is None`、`adapter_id is None`
  - 现算真库：`H4-2-rows` 无行 · `H8-2-rows` == `[]` · `H8-2-detail-prefill` 无行 ·
    H8 有 28 个 item_id（全 H 最多）· H4 为 0
  - 现算 `H8-1-rows` 3656 B 含 `"rowId":"h81-cost-房屋及建筑物-ya2jc"` ⇒ 族 A 安全形态实证

### 阶段 1：子入口改线（本 spec 头号风险）

- [ ] 3. 5 条子入口的 entry_id 全名落表 + representation pointer（HS-P3）
  - 用 manifest 现算全名（含补齐的 `xlsx/h8/measurement/h8-tab-measurement-monthly`）
  - 🔴 pointer 按 **GC-1** 用 `entry_id`；变异「用 wp_code」SHALL 打红
    （5 条共用父级 wp_code_pattern `H4T` / `H8T`，必撞）

- [ ] 4. H4 两条子入口改线（HS-P2）
  - `h4/impairment/H4TabImpairment.vue` + `h4/impairment/H4TabRecoverable.vue`
  - 🔴 与父宿主**共用** `useH4DualMode` ⇒ 父宿主改动必须同步子 Tab，否则打断子入口
  - 逐条断言子入口双向链路独立可验

- [ ] 5. H8 三条子入口改线（HS-P2，🔴 含最易漏的一条）
  - `h8/impairment/h8-tab-recoverable`：🔴 **父宿主内联自己的实现、只有子 Tab 用 `useH8DualMode`**
    ⇒ 按「删 composable + 改宿主」常规套路走会**完全漏掉它**；判据必须单独覆盖
  - `h8/measurement/h8-tab-measurement-annual`（H8-6 按年 61r×17c/263f）
  - `h8/measurement/h8-tab-measurement-monthly`（H8-6 按月 361r×16c/**3626f**）

- [ ] 6. 跨 spec 协调登记（不改代码，只登记）
  - `composables/useH6DualMode.ts` → `h2-h6-h10-pilot-cross-reference-lanes`
  - `composables/useH9DualMode.ts` → foundation（canary 链路，🔴 实测消费 1，**不得删**）
  - 证据 `evidence/task6-cross-spec-coordination.md`

### 阶段 2：BP-5 / BP-6 / BP-7 三条专属缺陷

- [ ] 7. BP-5 修复（HS-P4 / HS-P5）
  - `GtH8RightOfUseAssets.vue#L588` 写入目标 `H8-2-detail-prefill` → **`H8-2-rows`**
  - 断言修后 `H8-2-detail-prefill` 字面量全仓命中 **0**
  - 🔴 区分判据（design §二 表）：BP-5 **无 total 键 + 无读取方**；
    H7 的 `H7-2-cost-rows` **有 `H7-2-cost-total` + 有读取方** ⇒ H7 不得被误判
  - 🔴 与 Task 8 **一次改完**（`#L578` 在同一段种子代码里），不留中间态

- [ ] 8. BP-6 修复（HS-P6 / HS-P7，本 lane 2 处）
  - `h4DetailPrefill.ts#L50` `seed-${idx}` · `GtH8RightOfUseAssets.vue#L578` `seed-${idx}`
  - 目标形态对齐 HC-7 族 A，参照 `useH8Adjudication.ts#L145`
    `h81-${block}-${category}-${Math.random().toString(36).slice(2,7)}`
  - 🔴 **先现算**真库有无 `seed-` 前缀落库：若无（当前实测无）则可省迁移映射；
    若有则迁移映射变**必需**
  - 断言全 H `` rowId:`seed-${ `` 命中 3 → **1**（剩 H2，归 lane 3）
  - 断言后端 prefill 侧**无需改动**（`prefill_anchor_map.py` / `prefill_engine.py` H 字面量 0）

- [ ] 9. BP-7 修复（HS-P8 / HS-P9）
  - `h8DisclosureSyncPayload.ts#L51` `cats.map(c=>({key:c.label,…}))` → 稳定 key（`{prefix}{seq}`）
  - `#L110` `row[c.label]=…` → `row[c.key]=…`
  - 断言满足 lane 1 的 **SK-1 判据**；断言全 H 背离 H7 范式处 **1 → 0**
  - 🔴 先解析真库 `H8-listed-categories`（137 B）判定 label→key 迁移映射需求；
    `H8-listed-movement` 实测 `[]`（无迁移负担）

### 阶段 3：H4 footer 第三形态 + H8 重负载

- [ ] 10. H4 footer 与列边界（HS-P10 / HS-P11 / HS-P12）
  - `footer_kind: "derived_unit_price"`；派生列 `["F","I","L","O"]`（`F=G28/E28` 等）
  - 行内同型 `F=G12/E12` 族加**除零守卫**（分母 0 → 空/0，不产 `#DIV/0!`；先例 F4-7）
  - UUID 放 **50**（有效列 49 + 1）；🔴 变异「放 68（max_column+1）」SHALL 打红
  - 变异「按 `pure_sum` 校验」SHALL 打红

- [ ] 11. H8-6 双 sheet 声明 + wp_index 冲突登记（HS-P14）
  - 按 `period_granularity`（`annual`/`monthly`）或 sheet 全名声明（HC-5）
  - 🔴 登记 HC-15 风险 ③：wp_index 记 H8-6 =「使用权资产调整分录」，
    模板实测 =「使用权资产 租赁负债初始及后续计量（按年/按月）」⇒ 契约用模板 sheet 全名消歧；
    冲突**待平台侧修正**，本 spec 不修 wp_index

- [ ] 12. per-file 中性化 + 宽表列边界（HS-P13 / HS-P12）
  - per-file 挂 `oo_crash_neutralization_fn`：H8 **3710** · H4 **48**（差 77 倍）；
    变异「整册统一挂」SHALL 打红
  - 宽表按有效内容列：H8 国企侧 `255/6` · H4 两张 `254/6` + `254/8`
  - H8-2 主表 58/58 ⇒ UUID 59

### 阶段 4：载体接线 + 身份 + 派生合计

- [ ] 13. 载体接线（HS-P16）
  - H4 按 `formdata_composable`；TB 门在 `useH4Adjudication.ts` + `H4TabAdjudication.vue`
  - H8 按 `host_inline`（宿主 `import http from '@/utils/http'` + PUT，`checklist_put`=1）
    + 读 `render-config?force_component_type`（宿主命中 1）
  - **删 `useH8FormData`**（生产消费 0）；🔴 `useH8DualMode`（2）/ `useH4DualMode`（5）**禁删**
  - 🔴 守卫须校验宿主/Tab 侧**确实引用了新载体**（防 additive 死代码假绿，HC-3）
  - 断言 H8 `tb_publish_gate == null`（HS-P15，缺口登记）

- [ ] 14. 族 C 语义耦合身份修复（HS-P17，2 处）
  - `useH4Adjudication.ts#L436` `net-${name}` · `useH8Adjudication.ts#L572` `h81-net-${cat}`
  - 🔴 `useH8Adjudication.ts#L145` **属族 A 不得改**（有 `${rand5}`，真库实证安全）
  - 带旧身份迁移映射（H8 真库 `H8-1-rows` 3656 B 已落库族 A 身份，族 C 键须逐个核）

- [ ] 15. `derived_total_keys` 现算（HC-6）
  - 当前现算 🔴 **H8 21 个（全 H 最多）** · **H4 15 个**，**现算补全不写死个数**
  - 断言排除在 roundtrip 业务比对之外 + 指定重算责任方（adapter 回写阶段重算）
  - H8 常量/派生字段按 HC-11 声明（`H8-1-rows` 14 字段，`block` 是分组键）

### 阶段 5：契约发布

- [ ] 16.* 两份契约 + provider 发布（依赖 BP-1~BP-3）
  - `h4.engineering_material_detail.json` + `phase5_engineering_material_detail`
  - `h8.right_of_use_asset_detail.json` + `phase5_right_of_use_asset_detail`
    （含 `forbidden_keys: ["H8-2-detail-prefill"]` · `frozen_cross_ref: ["H9-2-rows"]`）
  - 走 `register_from_manifest()` 注册（HC-1）；零回归基线**现算**（HC-8 / GC-10）
  - 5 条子入口的 representation pointer 用 `entry_id`（GC-1）

- [ ] 17.* roundtrip 实证（依赖 BP-4 真 OO 9.4 场景集）
  - 🔴 前置：H4 真库零载荷、`H8-2-rows` 是 `[]` ⇒ **不得造数据当实证**；
    须等真实项目录入，或明确标注为合成场景并在报告里写明
  - 5 条子入口须各自跑一遍 roundtrip（不能只跑父 entry）

## 阻塞项对齐

| BP | 本 lane 处置 |
|---|---|
| BP-1 ~ BP-4 | 平台级，Task 16/17 标 `[ ]*` |
| **BP-5** | Task 7 修 |
| **BP-6** | Task 8 修（本 lane 2 处；第三处在 H2 归 lane 3） |
| **BP-7** | Task 9 修（修完全 H 背离处 → 0） |
| BP-8 | 成员按 HC-3 重算：删 `useH8FormData`；🔴 `useH8DualMode`/`useH4DualMode` 禁删 |
| BP-11（新） | 族 C 2 处，Task 14 |
| HD-7 缺口 | H8 无发布门，Task 13 只登记；补门归 lane 3 |
