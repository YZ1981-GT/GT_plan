# Implementation Plan

## Overview

**spec**：`h2-h6-h10-pilot-cross-reference-lanes`　**创建**：2026-09-26　
**状态**：0/19（Task 0~18），Design-First 未实施

**共同前置**：`h-cycle-sync-foundation-and-first-canary`（HC-1~HC-16）。
🔴 **本 spec 只引用 HC-x，不复述正文**。

**覆盖**：H2 在建工程 / H6 固定资产清理 / H10 资产处置损益（3 条）。
🔴 **本 lane 无 canary**（三条主表键真库零载荷或 `[]`），但 🔴 **承担全 H 的 TB 发布链首例**
（canary H9 与 H8 均无发布门）。

`[ ]*` = 依赖外部供给（BP-1~BP-4 / OO 真栈 / 业务确认）。

## Tasks

### 阶段 0：前置门 + 冻结基线

- [ ] 0. foundation 交付确认（不改代码，只核）
  - 确认 HC-1~HC-3 / HC-6 ~ HC-10 / HC-12 ~ HC-16 的 design 正文与判据已落地
  - 🔴 任一缺失 ⇒ 对应任务阻塞，不得在本 spec 内自行裁决
  - 证据 `evidence/task0-foundation-gate.md`

- [ ] 1. H1 pilot 跨引用图现算 + 5 键冻结基线（HX-P1 / HX-P4）
  - 现算 4 个 H1 侧消费文件对 5 个键的引用（`h1CipH2Pull.ts` / `h1SoeClearingH6Pull.ts` /
    `h1RelatedH10Pull.ts` / `useH1LeaseCheck.ts`）
  - 现算 H10↔H6 双向耦合（`h10RelatedH6Pull.ts` / `useH10CrossSheet.ts` 正向；
    `h6H10Pull.ts` / `useH6Check.ts` 反向消费 `H10-1-audited-total` / `H10-adj-total` /
    `H10-1-gain-loss-total`）
  - 取 H1 golden digest **当前值**存证（后续每次改动后比对）
  - 证据 `evidence/task1-h1-crossref-baseline.md`

- [ ] 2. 三条 entry 现状红判据
  - 现算 manifest 三条：`capability=='single_onlyoffice'` / `capability_target is None` /
    `adapter_id is None` / `mounts==2`
  - 现算真库：`H2-2-rows` 无行 · `H6-2-rows` 无行 · `H10-detail-rows` == `[]` ·
    H2 有 9 个 item_id（`H2-listed-materials` 301 B / `H2-listed-summary` 129 B 等）·
    H10 有 6 个（全为 2 B 空值）· **H6 为 0**
  - 现算零回归基线（契约数 / 注册集），**不写死**（HX-P3）

### 阶段 1：BP-12 猜键回退链收敛

- [ ] 3. BP-12 修复（HX-P5 / HX-P6）
  - `h10RelatedH6Pull.ts#L59` 三键回退 → 单一权威键 `H6-2-rows` + **fail-loud**
    （返回显式失败原因，**禁止静默取空**，方案见 design §二）
  - `useH10CrossSheet.ts` 同步收敛同一组三键
  - 现算依据存证：`H6-detail-rows` / `H6-clearing-rows` 在 H6 侧生产命中 **0** + 真库零载荷
  - 全 H 扫 `const keys\s*=\s*\[` 形态，逐键断言「H 侧生产命中 > 0」；
    变异「保留 `H6-detail-rows`」SHALL 打红

### 阶段 2：HC-10 三存储一致性归口

- [ ] 4. roundtrip 前置断言（HX-P7）
  - 断言 `localStorage` 中 `h10-draft:` 前缀键数 == 0
  - 变异「造一条草稿后跑 roundtrip」SHALL 打红并列出键名

- [ ] 5. 草稿长期一致性归口四条（HX-P8）
  - ① PUT 3 次全败后 SHALL **可见上报错误**（现状 `#L105` 写草稿是静默的 —— 真正的缺口）
  - ② adapter 回写窗口内 SHALL 禁用 `#L105` 的 `setItem` 分支
  - ③ UI SHALL 显示「有 N 条未同步草稿」（现状用户完全不知道存在第三份数据）
  - ④ `restoreDrafts()#L24-37` 回灌后 SHALL 立即重试 PUT，成功即删（`#L35`/`#L97` 已有）
  - 判据：模拟 PUT 连续失败 3 次 → 断言草稿产生 + 可见错误；再恢复 → 断言重试成功并删草稿

### 阶段 3：载体接线（HC-2 实例化）

- [ ] 6. H2 / H6 snapshot 透传读族接线（HX-P9）
  - 按 `props.htmlData.responses_snapshot` 读族；🔴 断言这两条**不存在**
    `\.get\(.*checklist-responses` 命中
  - 写路径按 `host_inline`（宿主 `import http from '@/utils/http'` + PUT；
    实测 H2 `checklist_put`=1 · H6 `checklist_put`=2）
  - 🔴 写对照测试：让 F 版守卫「持久化 composable 必须自带 GET+PUT」在这两条上打红，
    证明必须按族分派

- [ ] 7. H10 双读族接线（HX-P10）
  - 同时断言 checklist GET 与 snapshot 两条路径；写路径按 `formdata_composable`（`useH10FormData`）

- [ ] 8. legacy 载体处置（HX-P11）
  - **删 `useH6FormData`**（生产消费 0，仅测试引用 1）
  - 🔴 `useH6DualMode` 在 `useH4DualMode` → `useH6DualMode` → `useH8DualMode` → `useH9DualMode`
    链式复用链上 ⇒ 改它须与 `h4-h8-sub-entry-lanes-and-seed-identity-defects` 协调，**不得单方面改**
  - 🔴 守卫须校验宿主侧**确实引用了新载体**（防 additive 死代码假绿，HC-3）
  - 删前后测试全绿 + 独立 commit（删旧代码铁律）

### 阶段 4：TB 发布链首例（本 lane 独有职责）

- [ ] 9. 发布链首例选型落地 = H6（HX-P12）
  - 选型理由（design §四）：模板次小 48,865 B · 两级表头 · 数据区 5 行 · 42 公式 ·
    裸 IF **12 全 H 最少** · 有效列 16 最少 · 发布门只 2 处最干净 · **无第三存储**
  - 🔴 如实登记三条代价：①H6 真库零载荷 ⇒ **不得造数据当实证**（须真实项目录入或明确标注合成场景）
    ②被 H1 pilot 与 H10 双向跨引用，回归面最大 ③footer 是「　合计」全角特例，须先落地容错
  - 登记否决 H2（四级表头 + 50 列 + 226 公式）与否决 H10（4 处发布门 + localStorage + 双 footer + 月度矩阵）

- [ ] 10. 发布门接线与铁律断言（HX-P12）
  - 审定数入 `trial_balance` **只能**走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，
    必经二次确认
  - 🔴 断言**不存在**在 `watch` / `onMounted` / debounce 回调内发布（数据变化只 emit）
  - 落表三条发布门位置：H2 `useH2Adjudication.ts`(2)+`H2TabAdjudication.vue`(2) ·
    H6 `useH6Adjudication.ts`(2)+`H6TabAdjudication.vue`(2) ·
    H10 `useH10Adjudication.ts`(2)+`H10TabAdjudication.vue`(3)+宿主(1)+`useH10FormData.ts`(1)

### 阶段 5：身份修复

- [ ] 11. BP-6 第三处（最后一处）修复（HX-P13）
  - `GtH2ConstructionInProgress.vue#L616` `` rowId:`seed-${i} ` `` → 族 A 形态
    （参照 `useH8Adjudication.ts#L145` 的 `${rand5}` 后缀）
  - 断言修后全 H `` rowId:`seed-${ `` 命中 → **0**（lane 2 修掉前两处）
  - 断言后端 prefill **零参与**（`prefill_anchor_map.py` / `prefill_engine.py` H 字面量 0）

- [ ] 12. 族 C 语义耦合身份修复（HX-P14，2 处）
  - `useH2Adjudication.ts#L194` `` `row-total-${name}` `` · `#L389` `` `net-${name}` ``
  - 🔴 **先现算**真库有无族 B/C 身份落库：`H2-2-rows` 零载荷 / `H10-detail-rows` == `[]` /
    H6 零载荷 ⇒ 迁移风险低；若现算发现落库则迁移映射变**必需**

- [ ] 13. H10 身份形态保持断言（HX-P15）
  - 断言身份字段是 **`id`**（不是 `rowId`）+ `generated_opaque_string` 族
  - 断言 `useH10Detail.ts` 有 `addRow#L159` / `removeRow#L172` + `id: raw.id ?? generateId()#L72`
  - 🔴 变异「因模板 9 行看起来固定就改成 `stable_template_row_key`」SHALL 打红

### 阶段 6：模板侧 instrumentation

- [ ] 14. per-file 中性化 + UUID 落位（HX-P16 / HX-P17）
  - per-file 挂 `oo_crash_neutralization_fn`：H2 **138** · H10 **56** · H6 **12**；
    变异「整册统一挂」SHALL 打红
  - UUID 落位：H2-2 → 51 · **H6-2 → 17**（有效列 16，🔴 变异「放 26 = max_column+1」SHALL 打红）·
    H10-2 → 27
  - 宽表按有效内容列：H2 `256/10` + `255/14`（14 是全 H 宽表有效列最多）；
    🔴 H6(5c) / H10(17c,5c) **不在宽表之列**，不触发 HC-13

- [ ] 15. footer 特例落地（HX-P18 / HX-P19 / HX-P20）
  - 🔴 H6 `footer_marker = "　合计"`（全角空格前缀）+ `footer_marker_normalize` 容错；
    变异「写成『合计』」SHALL 打红
  - 🔴 H10 双 footer：R17 `pure_sum` + **R18 `ratio_footer`「各月比例」**；
    变异「只声明单 footer」SHALL 打红（会把 R18 当业务行）
  - H10 派生列全声明 derived：`N=SUM(B8:M8)`（12 月度列 B-M）· `T`/`Y` 占比列
    `=IF($Q$17=0,0,Q8/$Q$17)`（引合计行 R17，同 G11-2 `$F$31` 形态）· `Z` 嵌套 IF 判断式；
    月度矩阵规则**同源引用** F5-2 / D4-2

- [ ] 16. 干净点断言 + hidden sheet（HX-P21）
  - 三册 definedName 0 / 漏加小计 0 / 越界引用 0 / 无 Excel Table
  - 🔴 断言 H10 有 `GT_Custom` hidden sheet（与 H9 两册独有）且**不纳管**

### 阶段 7：派生合计 + 契约发布

- [ ] 17. `derived_total_keys` 现算（HX-P22）
  - H2 约 4 个 · H6 约 8 个 · H10 约 3 个，**现算补全不写死**
  - 🔴 `H6-2-subtotal-*` 六键被跨 entry 消费（`useH6CrossSheet.ts` / `useH6Adjudication.ts` /
    `h6DisclosureModel.ts`）⇒ 断言**重算时机在跨表勾稽读取之前**，否则勾稽读到陈旧值
  - 断言全部排除在 roundtrip 业务比对之外 + 指定重算责任方

- [ ] 18.* 三份契约 + provider 发布（依赖 BP-1~BP-3）
  - `h2.construction_in_progress_detail.json` + `phase5_construction_in_progress_detail`
  - `h6.asset_disposal_clearing_detail.json` + `phase5_asset_disposal_clearing_detail`
    （含 `tb_publish_first_case: true` · `footer_marker: "　合计"` · `frozen_keys`）
  - `h10.asset_disposal_income_detail.json` + `phase5_asset_disposal_income_detail`
    （含 `client_draft_store` · `hidden_sheets_unmanaged: ["GT_Custom"]` · 双 footer · 月度列）
  - 三份 `primary_table` 全部带 `frozen_key: true` + `frozen_reason`（HC-8）
  - 走 `register_from_manifest()` 注册（HC-1）；零回归基线**现算**
  - 🔴 发布后重跑 **H1 golden digest** 断言不变（HX-P2）

- [ ] 19.* roundtrip + 发布链实证（依赖 BP-4 真 OO 9.4 场景集）
  - 前置四条：草稿键 0 · 冻结调整分录中央同步（`H*TabAdjustment.vue` 各 3 处）·
    排除 `derived_total_keys` · 5 个冻结键未改
  - 🔴 发布链实证走 H6；**不得造数据当实证**，须真实项目录入或明确标注合成场景并在报告写明
  - 断言 OO 侧改审定数后走同一显式发布门，不绕道直写 `trial_balance`

## 阻塞项对齐

| BP | 本 lane 处置 |
|---|---|
| BP-1 ~ BP-4 | 平台级，Task 18/19 标 `[ ]*` |
| BP-6 第三处 | Task 11 修（修完全 H 归零） |
| BP-8 | 成员按 HC-3 重算：删 `useH6FormData`；🔴 `useH6DualMode` 须与 lane 2 协调 |
| **BP-11**（新） | 族 C 2 处，Task 12 |
| **BP-12**（新） | Task 3 修（发起方与被害方都在本 lane） |
| **HC-10** | Task 4（前置断言）+ Task 5（长期归口四条） |
| **HD-7 发布链首例** | Task 9/10（H6），并登记 H8/H9 缺口不在本 spec 补 |
