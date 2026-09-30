# Implementation Plan

## Overview

**spec**：`h3-h5-h7-variant-axis-and-dynamic-column-paradigm`　**创建**：2026-09-26　
**状态**：0/15（Task 0~14），Design-First 未实施

**共同前置**：`h-cycle-sync-foundation-and-first-canary`（HC-1~HC-16）。
🔴 **本 spec 只引用 HC-x，不复述正文**。foundation 未交付的 HC-x ⇒ 依赖它的任务阻塞。

**覆盖 entry**：H3 投资性房地产 / H5 油气资产 / H7 生产性生物资产（3 条）。
🔴 **本 lane 无 canary**（三条真库主表键全部零载荷，canary 由 foundation 的 H9 承担）。

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

## Tasks

### 阶段 0：前置门

- [ ] 0. foundation 交付确认（不改代码，只核）
  - 确认 HC-2 / HC-3 / HC-4 / HC-5 / HC-6 / HC-7 / HC-8 / HC-10 / HC-11 / HC-12 / HC-13 /
    HC-14 / HC-16 的 design 正文与判据已在 foundation 落地
  - 🔴 任一缺失 ⇒ 本 spec 对应任务阻塞，**不得**在本 spec 内自行裁决
  - 证据 `evidence/task0-foundation-gate.md`

- [ ] 1. 三条 entry 现状红判据（先打红）
  - 现算 manifest 三条：`capability=='single_onlyoffice'` / `capability_target is None` /
    `adapter_id is None` / `mounts==2`
  - 现算真库：三条主表键零载荷（`H3-2-cost-rows` / `H3-2-fair-rows` / `H5-2-rows` /
    `H7-2-cost-rows` 均无行）；H3 有 5 个披露 item_id、H5 有 7 个、**H7 为 0**
  - 现算 `H5-1-cost-rows` 1059 B 含 `"rowId":"row-c-油井资产"` ⇒ 族 C 真库实证（HV-P11 依据）

### 阶段 1：变体轴（HC-5 实例化）

- [ ] 2. 五组轴落表 + 契约坐标写法（HV-P1）
  - 三条 entry 的 `sheet_coordinates` 全量落表（含 H3-7 交叉轴、H7-11 `-直线法` 隐含轴）
  - 🔴 裁决落地：**优先 `sheet_name` 全名**，`variant_axis` 仅作查询索引（避免交叉轴组合爆炸）
  - 变异「只声明 `(measurement_model, sheet_code)` 两维」SHALL 打红并指出 H3-7/H5-12/H7-11 无处安放

- [ ] 3. `sheet_code` 定位消歧守卫（HV-P2）
  - 按 `sheet_code` 定位命中 2 张时 SHALL 要求补 `variant_value`，**不得静默取首张**
  - 断言 H3/H7 两套计量模式**各有独立键**；登记与 E1-3 `currency_variant` 的差异

### 阶段 2：SK-1 ~ SK-4 守卫（HV-P3 / HV-P4）

- [ ] 4. SK-1 / SK-2 守卫
  - SK-1：`h7ListedDisclosureModel.ts#L50-57` 三字段分离 + `createDefaultH7Categories()#L60` `${ind.key}_1`
  - SK-2：`nextH7CategoryKey#L74-86` 出现 `${prefix}${max+1}`；
    `h7SoeDisclosureModel.ts#L104-115` 国企侧同形
  - 🔴 反向断言：全 H 不得出现 `length+1` / `${i}` / `${idx}` 作动态列序号

- [ ] 5. SK-3 / SK-4 守卫
  - SK-3：`h7TotalCellValue#L295` 用 `reduce`；🔴 全 H `公司1..公司N` 横向展开字面量 == 0
  - SK-4：`H7_COST_MOVEMENT_ROWS` 34 行对应 R11-44 · `H7_FAIR_MOVEMENT_ROWS` 11 行对应 R53-64；
    🔴 `blankRows(x, <整数>)` == 0
  - 登记范式来源（四个产业叶子列名同为 `类别`）与下游 5 处逐字引用

- [ ] 6. 本 lane 背离点 == 0 断言（HV-P4）
  - 扫描本 lane 三条源码，断言背离 H7 范式的地方 **0 处**
  - 登记唯一背离点 BP-7 在 H8（归 `h4-h8-sub-entry-lanes-and-seed-identity-defects`）

### 阶段 3：三条载体接线（HC-2 实例化）

- [ ] 7. H3 接线（`formdata_composable`）
  - 载体 `useH3FormData`（现算生产消费，实测 37 处）；读 `GET /checklist-responses`
  - TB 门断言在 `H3TabAdjudicationCost.vue`（`publishToTb`×2）
  - 🔴 守卫须校验宿主/Tab 侧**确实引用了新载体**（防 additive 死代码假绿，HC-3）

- [ ] 8. H5 接线（`per_tab_formdata_instance`，🔴 接线点 N 个）（HV-P5）
  - **先现算** `useH5FormData` 实例化点个数，落表后逐点接线
  - 漏任一点 SHALL 打红（该 Tab 双向不通但文件已改 ⇒ 假绿）
  - TB 门在 `useH5FormData.ts`（每实例各带一份）⇒ roundtrip 须确认不会多实例重复发布
  - 落表 16 个 PREFIX 常量实值（`H5-1`..`H5-19`）

- [ ] 9. H7 接线（`per_tab_self_persisting`，🔴 载体是 Tab）（HV-P6）
  - 载体 `H7TabDetailCost.vue` 内联 `api`；主表键内联在 `#L215`
  - 🔴 断言**接到 `useH7DetailCost.ts`（26 行取值 stub）上 SHALL 打红** —— 假绿典型
  - TB 门在 `useH7FormData.ts`（`publishToTb`×2）

- [ ] 10. legacy 载体处置（HV-P7）
  - **删** `useH5DualMode`（生产消费 0；同时消除 HC-10 第四存储 `h5-dual-mode:` 风险）
  - **删** `useH7DualMode`（生产消费 0）
  - 🔴 **`useH7FormData` 移出删除清册并加禁删断言**（slice 名单错；它是 H7 唯一 TB 发布门）
  - 删前后测试全绿 + 独立 commit（删旧代码铁律）

### 阶段 4：主表键 / 身份 / 派生合计

- [ ] 11. 主表键解析与冻结（HV-P8 / HV-P9 / HV-P10）
  - `H5-2-rows` 用 HC-4 拼接解析（`prefix_const` 指向 `useH5Detail.ts#L53` 值 `H5-2`）；
    变异「去掉拼接分支」SHALL 打红
  - `H7-2-cost-rows` / `H7-2-fair-rows` 命中 1 判**正常**（有对应 `H7-2-*-total`，
    勾稽走 `useH7CrossSheet.ts#L52`）
  - 🔴 `H3-2-fair-rows` 加 `frozen_key: true` + 冻结原因（G 循环消费），变异改名 SHALL 使 G 侧打红

- [ ] 12. 族 C 语义耦合身份修复（HV-P11，**3 处**；全 H 7 = 本 lane 3 + lane 2 的 2 + lane 3 的 2）
  - `useH3Adjustment.ts#L311` `${kind}-${cat}` · `useH3RentalIncome.ts#L148` `subtotal-${cat}` ·
    `useH5Adjudication.ts#L136` `row-${prefix}-${cat}`
  - 🔴 **必须带旧身份迁移映射**（真库已落库 `row-c-油井资产` / `row-d-油井资产`），
    否则既有行全部变「新行」、历史金额串位
  - 改后形态对齐族 A（加随机/时间戳后缀，参照 `useH8Adjudication.ts#L145`）

- [ ] 13. H5 小计行与常量字段声明（HV-P12）
  - 断言小计行**不落库**（`useH5Adjudication.ts#L309-311` filter · `useH5Detail.ts#L138` computed）
    ⇒ 契约无需排除
  - `isSubtotal`（恒 false）/ `isEditable`（恒 true）按 HC-11 声明为常量/派生
  - 变异「契约把小计行写进业务行排除列表」SHALL 打红（无此需要，属误解）

- [ ] 14. `derived_total_keys` 现算（HC-6）
  - 当前现算 **H3 14 · H5 5 · H7 6**，**现算补全不写死个数**
  - 断言这些键排除在 roundtrip 业务比对之外 + 指定重算责任方（adapter 回写阶段重算）

### 阶段 5：模板侧 instrumentation + 契约发布

- [ ] 15. per-file 中性化 + 宽表列边界（HV-P13 / HV-P14 / HV-P15 / HV-P16）
  - per-file 挂 `oo_crash_neutralization_fn`：H7 1025 · H5 816 · H3 661（变异「整册统一」打红）
  - 6 张宽表按有效内容列扫描：H3 `250/6`+`252/9` · H5 `257/8`+`253/6` · H7 `257/11`+`256/6`
  - UUID 放有效列+1：H3 46 · H5 55 · H7 52
  - 三册干净点保持为无 + 断言**无 `GT_Custom` hidden sheet**（只在 H9/H10）
  - 三条 footer 全为纯 SUM（H3 R28 / H5 R33 / H7 R37）

- [ ] 16.* 三份契约 + provider 发布（依赖 BP-1~BP-3）
  - `h3.investment_property_detail.json` + `phase5_investment_property_detail`
  - `h5.oil_gas_asset_detail.json` + `phase5_oil_gas_asset_detail`
  - `h7.biological_asset_detail.json` + `phase5_biological_asset_detail`
  - 走 `register_from_manifest()` 注册（HC-1）；零回归基线**现算**（HC-8 / GC-10）

- [ ] 17.* roundtrip 实证（依赖 BP-4 真 OO 9.4 场景集）
  - 🔴 前置：三条真库主表键零载荷 ⇒ roundtrip 须先有真实数据；
    **不得造数据当实证**，须等真实项目录入或明确标注为合成场景（并在报告里写明）

## 阻塞项对齐

| BP | 本 lane 处置 |
|---|---|
| BP-1 ~ BP-4 | 平台级，Task 16/17 标 `[ ]*` |
| BP-8 | 成员按 HC-3 重算：删 `useH5DualMode`/`useH7DualMode`；🔴 `useH7FormData` 禁删 |
| BP-11（新） | 族 C **3 处**，Task 12 |
| HC-10 第四存储 | 删 `useH5DualMode` 即消除（Task 10） |
