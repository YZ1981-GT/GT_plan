# Requirements Document

## Introduction

本 spec 是 H 循环三份 lane spec 之一，覆盖 **H2 在建工程 / H6 固定资产清理 / H10 资产处置损益** 三条 entry。

**共同前置**：`h-cycle-sync-foundation-and-first-canary`（承载 **HC-1 ~ HC-16**）。
🔴 **本 spec 只引用 HC-x，不复述其正文**。

**聚类依据**（为什么这三条在一起）：
1. 🔴 **三条全部被已注册 adapter 的 H1 pilot 跨引用**（golden digest 已锁）⇒
   主表键冻结规则与回归口径必须一次裁决；
2. **H2/H6 是 HD-2 的 `snapshot 透传` 读族**（全 H 仅这两条）；
3. **BP-12 猜键回退链的两端都在本 lane**（H10 是发起方、H6 是被害方）；
4. **HC-10 第三处客户端存储在 H10**；
5. 🔴 **TB 发布链首例在本 lane**（三条都有发布门；canary H9 与 H8 都没有）。

🔴 **Property 编号 spec-scoped**：本 spec `Property N` 读作 **`HX-P{N}`**（H Cross-reference）。

### 三条 entry 实测底账

| entry_id | 宿主 | 幻影码 | 模板 sha256 前 16 / 字节 | 写族 | 读族 | TB 门位置 |
|---|---|---|---|---|---|---|
| `xlsx/gt-h2-construction-in-progress` | `GtH2ConstructionInProgress.vue` | H2C | `de9426a33e8d51e9` / 162,616 | `host_inline`（宿主 `checklist_put`=1） | `props.htmlData.responses_snapshot`（父级 render-config 透传） | `useH2Adjudication.ts` + `H2TabAdjudication.vue` |
| `xlsx/gt-h6-asset-disposal-clearing` | `GtH6AssetDisposalClearing.vue` | H6A | `c7d0d78a798ce9c3` / **48,865（次小）** | `host_inline`（宿主 `checklist_put`=2） | `props.htmlData.responses_snapshot` | `useH6Adjudication.ts` + `H6TabAdjudication.vue` |
| `xlsx/gt-h10-asset-disposal-income` | `GtH10AssetDisposalIncome.vue` | H10A | `9f0d2a64dab1fd76` / **42,334（最小）** | `formdata_composable`（`useH10FormData`） | **两者都有**（checklist GET + snapshot） | `useH10Adjudication.ts` + `H10TabAdjudication.vue` + 宿主 1 处 |

三条共同：`capability=single_onlyoffice` / 无 `capability_target` 字段 / `adapter_id=None` /
`mounts=2` / 0 契约 / 0 representation / 宿主 `bridge=0` `legacyOO=4` `notice=3` `ocr=0` /
`useAdjustmentCentralSync` 在各自 `H*TabAdjustment.vue` 命中 3 处。

🔴 **H10 是全 9 条里唯一宿主层有 `publishToTb` 的**（命中 1 处）；H2/H6 的门在 composable/Tab 层。

### 主表几何（openpyxl 逐格实测）

| entry | 主表 sheet | 表头 | 数据区 | footer | 有效列/max_col | 公式数 | 裸 IF |
|---|---|---|---|---|---|---|---|
| H2 | `明细表H2-2` | **四级 R9/R10/R11/R12** | R13-20 | R21 `SUM(J13:J20)` 纯 SUM | 50/50 | 226 | 138 |
| H6 | `明细表H6-2` | 两级 R9/R10 | R11-15（5 行） | R16 🔴 **「　合计」全角空格前缀** | **16/25（有效列最少）** | 42 | **12（全 H 最少）** |
| H10 | `明细表H10-2` | 🔴 **单级 R7** | R8-16（**9 个模板项目行作种子**） | R17 合计 + 🔴 **R18「各月比例」第二 footer** | 26/26 | 96 | 56 |

**H6-2 公式列**：E/I/J/K/L（`E=SUM(B:C)-D` · `I=B+F` · `L=I+J-K`）。

**H10-2 三处特殊**（实测）：
1. R8-16 是 **9 个模板固定项目行**（持有待售 / 固定资产 / 在建工程 / 生产性生物资产 / 无形资产 /
   债务重组 / 非货币性资产交换 / 使用权资产 / 油气资产处置利得），R 列逐行写「与 H1/H2/H5/H7/H8 勾稽」。
   🔴 但实测 `useH10Detail.ts` **有 `addRow#L159` / `removeRow#L172`** + `id: raw.id ?? generateId()#L72`
   ⇒ 这 9 行**只是种子、用户可增删** ⇒ 身份是 `generated_opaque_string`/`id` **正确**，
   **不是** `stable_template_row_key` 族。
2. **12 个月度列 B-M** + `N=SUM(B8:M8)` 年度合计 ⇒ 月度矩阵（同族 F5-2 / D4-2，规则同源引用）。
3. **T/Y 占比列引合计行** `=IF($Q$17=0,0,Q8/$Q$17)`（同 G11-2 `$F$31` 形态）+
   **Z 列嵌套 IF 判断式** `=IF(AND(X8=0,Q8>0),1,IF(AND(X8…`。

### 主表键与真库（实测）

| 键 | 生产命中 | 真库 | 身份字段 | 定位 | 冻结 |
|---|---|---|---|---|---|
| `H2-2-rows` | 16 | **零载荷** | `rowId` | `useH2Detail.ts#L260` | 🔴 **冻结**（`h1CipH2Pull.ts` 消费） |
| `H6-2-rows` | 8 | **零载荷** | `rowId` | `useH6Detail.ts#L294` | 🔴 **冻结**（`h1SoeClearingH6Pull.ts` + H10 消费） |
| `H6-1-rows` / `H6-1-end-balance-audited` | 3 / 4 | 零载荷 | — | `useH6Adjudication.ts` 等 | 🔴 **冻结**（`h1SoeClearingH6Pull.ts` 消费） |
| `H10-detail-rows` | 9 | **`[]` 空数组**（2 B） | **`id`** | `useH10Detail.ts#L48` | 🔴 **冻结**（`h1RelatedH10Pull.ts` + `useH1LeaseCheck.ts` 消费） |

**真库其他**：H2 有 9 个 item_id（`H2-listed-materials` 301 B · `H2-listed-summary` 129 B 等）·
H10 有 6 个（全部 2 B 空数组或空串）· **H6 真库零载荷（0 个 item_id）**。

---

## Requirements

### Requirement 1: 引用而不复述 foundation 的 HC-1 ~ HC-16

#### Acceptance Criteria

1. WHEN 本 spec 需要任一 HC-x 裁决 THEN SHALL 只写引用 + 本 lane 实例化参数，**不得**复述正文。
2. WHEN foundation 的某条 HC-x 尚未交付 THEN 依赖它的本 lane 任务 SHALL 阻塞，不得自行裁决绕过。
3. WHEN 跨 spec 复盘 THEN 发现复述 HC 正文 SHALL 判为缺陷。

### Requirement 2: H1 pilot 跨引用回归与 5 键冻结（本 spec 头号约束）

**User Story:** 作为维护者，我不要因为改 H2/H6/H10 的键名而静默打断已注册 adapter 的 H1 pilot。

#### Acceptance Criteria

1. 🔴 WHEN 本 lane 触及以下键 THEN SHALL **冻结键名不改**（HC-8）：
   `H2-2-rows` · `H6-1-rows` · `H6-2-rows` · `H6-1-end-balance-audited` · `H10-detail-rows`。
   判据 SHALL 对每个键断言 H1 侧消费方文件仍能解析到它。
2. WHEN 登记消费方 THEN SHALL 按实测：
   `h1CipH2Pull.ts` → `H2-2-rows` ·
   `h1SoeClearingH6Pull.ts` → `H6-1-end-balance-audited` / `H6-1-rows` / `H6-2-rows` ·
   `h1RelatedH10Pull.ts` → `H10-detail-rows` ·
   `useH1LeaseCheck.ts` → `H10-detail-rows`（+ 一批 H1 自有键）。
3. 🔴 WHEN 本 lane 任何改动完成 THEN SHALL 回归 **H1 契约 golden digest**
   （`h1.disposal_check.json`，pilot_class `h1_grouped_dynamic`，已注册 adapter）；
   **不得修改 H1 的契约 / adapter / golden digest 本身**。
4. WHEN 必须改上述任一键 THEN SHALL 另立 spec，且在同一变更内改 H1 侧取数文件 + 回归 golden。
5. WHEN 声明零回归基线 THEN SHALL **现算**（GC-10），不得写死契约数或注册集
   （当前现算：契约 13 个 · 注册集 `{d2,d4,g7,h1}`）。
6. WHEN 登记 H 内部耦合 THEN SHALL 覆盖 H10 → H6 方向（`h10RelatedH6Pull.ts` / `useH10CrossSheet.ts`
   消费 `H6-2-rows`）与 `h6H10Pull.ts` / `useH6Check.ts` 反向消费 H10 的 total 键
   （`H10-1-audited-total` / `H10-adj-total` / `H10-1-gain-loss-total`）⇒ **双向耦合**。

### Requirement 3: BP-12 猜键回退链修复（发起方与被害方都在本 lane）

**User Story:** 作为维护者，我要 H10 对 H6 的取数在 H6 改键后**报错**而不是静默变 0。

#### Acceptance Criteria

1. 🔴 WHEN 修 BP-12 THEN SHALL 把 `h10RelatedH6Pull.ts#L59`
   `const keys = ['H6-2-rows', 'H6-detail-rows', 'H6-clearing-rows']`
   收敛为**单一权威键** `H6-2-rows` + **fail-loud**（拉不到则显式报错/空态，**禁止静默取空**）。
2. WHEN 判定后两键是猜测键 THEN SHALL 用实测依据：`H6-detail-rows` / `H6-clearing-rows`
   在 **H6 侧生产命中 0**（只被 H10 侧两个文件引用：`h10RelatedH6Pull.ts` + `useH10CrossSheet.ts`）
   且**真库零载荷** ⇒ 是猜测键不是别名。
   同文件 `#L4` 注释已写明真源：「H6 明细在 H6 WP 的 checklist『H6-2-rows』，不在 H10 allResponses」。
3. WHEN 修 `useH10CrossSheet.ts` THEN SHALL 同步收敛同一组三键。
4. WHEN 断言修复 THEN 全 H `const keys\s*=\s*\[` 形态的多键回退 SHALL 逐键满足「H 侧生产命中 > 0」；
   变异「保留 `H6-detail-rows`」SHALL 打红。

### Requirement 4: HC-10 第三处客户端存储（H10 localStorage 草稿）

**User Story:** 作为实施者，我要 roundtrip 的前提真的成立 ——
有未同步草稿时「HTML 侧内容 == `checklist_responses`」是假的。

#### Acceptance Criteria

1. 🔴 WHEN roundtrip 前 THEN SHALL 先 flush 草稿（触发重试成功）**或**断言草稿键集合为空；
   判据 SHALL 断言 `localStorage` 中 `h10-draft:` 前缀键数 == 0。
2. WHEN 登记实现细节 THEN SHALL 按实测 `useH10FormData.ts`（228 行）：
   `#L11 DRAFT_PREFIX='h10-draft'` · `#L13-14 draftKey = ${DRAFT_PREFIX}:${wpId}:${itemId}` ·
   `#L105 setItem`（PUT 重试 **3 次全败**时写整条 item）· `#L97 removeItem`（PUT 成功时）·
   `#L24-37 restoreDrafts()` 前缀匹配 + `JSON.parse` 回灌 + `#L35 removeItem` ·
   `#L54` 在初始化时调用 `restoreDrafts()`。
3. 🔴 WHEN 草稿非空而仍跑 roundtrip THEN SHALL 打红并指出草稿键名 ——
   否则 roundtrip 会把草稿里的改动**判成 OO 侧删除**。
4. WHEN 设计长期方案 THEN SHALL 在 design 给出「草稿与 `checklist_responses` 的一致性归口」，
   不得只加一个前置断言就算处置完（前置断言只防误判，不解决三存储并存）。

### Requirement 5: H2/H6 的 snapshot 透传读族接线（HD-2 第二族）

#### Acceptance Criteria

1. WHEN 接 H2 / H6 THEN SHALL 按 `props.htmlData.responses_snapshot` 读族（父级 render-config 透传）——
   🔴 **这两条的载体里没有 checklist GET**；判据 SHALL 断言不存在 `\.get\(.*checklist-responses` 命中。
2. WHEN 沿用 F 循环守卫「持久化 composable 必须自带 GET+PUT」THEN SHALL 判为**对这两条假红**（HC-2），
   守卫 SHALL 按族分派。
3. WHEN 接写路径 THEN SHALL 按 `host_inline` 族：宿主自己 `import http from '@/utils/http'` 并 PUT
   （实测 H2 `checklist_put`=1 · H6 `checklist_put`=2）。
4. WHEN 接 H10 THEN SHALL 按 `formdata_composable` 写族 + **两读族都有**；
   判据 SHALL 同时断言 checklist GET 与 snapshot 两条路径。
5. WHEN 处置本 lane legacy 载体 THEN SHALL 按 HC-3 实测：**删 `useH6FormData`**（生产消费 0，仅测试引用 1）；
   🔴 `useH6DualMode` 在 `useH4DualMode` 链式复用链上 ⇒ 改它须与
   `h4-h8-sub-entry-lanes-and-seed-identity-defects` 协调，**不得单方面改**。
6. WHEN 守卫校验接线 THEN SHALL 断言宿主侧**确实引用了新载体**（防 additive 死代码假绿，HC-3）。

### Requirement 6: TB 发布链首例（本 lane 承担）

**User Story:** 作为实施者，我要在本 lane 打通第一条完整的 TB 发布链 ——
canary H9 与 H8 都没有发布门，这条链在全 H 无处验证。

#### Acceptance Criteria

1. 🔴 WHEN 选发布链首例 THEN SHALL 在本 lane 三条中选（三条**都有**发布门）；
   design SHALL 给出选型与理由，并登记 H8/H9 是 HD-7 的两条缺口（不在本 spec 补）。
2. WHEN 接发布链 THEN SHALL 按平台铁律：审定数入 `trial_balance` **只能**走
   `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，必经二次确认；
   🔴 **禁止**在 `watch` / `onMounted` / debounce 回调内发布（数据变化只 emit）。
3. WHEN 登记发布门位置 THEN SHALL 按实测：
   H2 → `useH2Adjudication.ts`（`publishToTb`×2）+ `H2TabAdjudication.vue`（×2）·
   H6 → `useH6Adjudication.ts`（×2）+ `H6TabAdjudication.vue`（×2）·
   H10 → `useH10Adjudication.ts`（×2）+ `H10TabAdjudication.vue`（×3）+ **宿主 1 处** + `useH10FormData.ts` 1 处。
4. WHEN roundtrip 覆盖发布链 THEN SHALL 断言 OO 侧改审定数后走同一显式发布门，不得绕道直写。

### Requirement 7: BP-6 第三处 + 族 C 身份修复

#### Acceptance Criteria

1. 🔴 WHEN 修 BP-6 THEN 本 lane SHALL 覆盖**第三处（最后一处）**：
   `GtH2ConstructionInProgress.vue#L616` `` rowId:`seed-${i}` ``；
   目标形态对齐 HC-7 **族 A**（参照 `useH8Adjudication.ts#L145` 的 `${rand5}` 后缀形态）。
   断言修后全 H `` rowId:`seed-${ `` 命中 → **0**（lane 2 修掉前两处）。
2. WHEN 修族 C（HC-7）THEN 本 lane SHALL 覆盖 **2 处**：
   `useH2Adjudication.ts#L194` `` `row-total-${name}` `` · `#L389` `` `net-${name}` ``。
3. 🔴 WHEN 替换身份 THEN SHALL 带**旧身份迁移映射**；判据 SHALL 现算真库确认：
   `H2-2-rows` 零载荷、`H10-detail-rows` 为 `[]`、H6 零载荷 ⇒ 本 lane 迁移风险**低**，
   若现算发现任何族 B/C 身份落库 THEN 迁移映射变**必需**。
4. WHEN 处置 H10 身份 THEN SHALL 按实测保持 `id` 字段（**不是** `rowId`）
   + `generated_opaque_string` 族；🔴 **不得**因模板 9 行「看起来固定」就改成 `stable_template_row_key`
   （实测 `addRow`/`removeRow` 存在，用户可增删）。
5. WHEN 登记 prefill 归属 THEN SHALL 断言后端 prefill **零参与**，修复只在前端（同 lane 2）。

### Requirement 8: 模板侧实例化（HC-12 / HC-13 / HC-14 / HC-16）

#### Acceptance Criteria

1. WHEN 挂中性化 THEN SHALL per-file（HC-12），本 lane 实测裸 IF：
   H2 **138** · H10 **56** · H6 **12（全 H 最少）**；变异「整册统一挂」SHALL 打红。
2. WHEN 扫描披露宽表列 THEN SHALL 按有效内容列（HC-13），本 lane 实测：
   H2 `256c/有效10` + `255c/14`（**14 是全 H 宽表里有效列最多的**）；
   🔴 H6（5c）· H10（17c / 5c）**不在宽表之列**，不触发 HC-13。
3. WHEN 放 UUID 列 THEN SHALL 放有效列+1：H2-2 → **51** · H6-2 → **17**（有效列 16，非 `max_column` 25+1）·
   H10-2 → **27**。🔴 H6 的 `max_column`(25) 与有效列(16) 不等，变异「放 26」SHALL 打红。
4. 🔴 WHEN 声明 H6 footer THEN SHALL 按 HC-16 容错**全角空格前缀**：标签实测是 **「　合计」**
   （同族先例 F3 的「合␠␠计」）；变异「`footer_marker` 写成不含全角空格的『合计』」SHALL 打红。
5. 🔴 WHEN 声明 H10 footer THEN SHALL 按 HC-16 **多 footer**：R17 合计 +
   **R18「各月比例」第二 footer 行**；变异「只声明单 footer」SHALL 打红（会把 R18 当业务行）。
6. WHEN 声明 H10 派生列 THEN SHALL 覆盖：`N=SUM(B8:M8)`（12 月度列 B-M 的年度合计）·
   `T/Y` 占比列 `=IF($Q$17=0,0,Q8/$Q$17)`（引合计行，同 G11-2 `$F$31` 形态）·
   `Z` 列嵌套 IF 判断式 `=IF(AND(X8=0,Q8>0),1,IF(AND(X8…`；三者全部声明为 `derived`。
   月度矩阵规则**同源引用** F5-2 / D4-2，不重复裁决。
7. WHEN 断言干净点（HC-14）THEN 本 lane 三册 SHALL 全部命中：definedName 0 · 漏加小计 0 ·
   越界引用 0 · 无 Excel Table；🔴 **H10 有 `GT_Custom` hidden sheet**（与 H9 两册独有，其余 7 册无）⇒
   判据 SHALL 断言该 hidden sheet 存在且**不纳管**。
8. WHEN 声明 H2 表头 THEN SHALL 按实测**四级 R9/R10/R11/R12**；
   H6 两级 R9/R10；🔴 H10 **单级 R7**（全 H 最浅）。

### Requirement 9: 派生合计副本（HC-6 实例化）

#### Acceptance Criteria

1. WHEN 声明 `derived_total_keys` THEN SHALL **现算**：
   H2 约 4 个（`H2-14-summary` / `H2-16-dcf-assumptions` / `H2-listed-summary` / `H2-soe-summary`）·
   H6 约 8 个（`H6-1-aje-total` / `H6-1-rje-total` / `H6-2-subtotal-begin-audited` /
   `H6-2-subtotal-begin-unadjusted` / `H6-2-subtotal-end-audited` / `H6-2-subtotal-end-unadjusted` /
   `H6-2-subtotal-gain-loss`（4 处消费）/ `H6-2-subtotal-net-book-value`）·
   H10 约 3 个（`H10-1-audited-total` / `H10-1-gain-loss-total` / `H10-adj-total`）。
2. WHEN 断言这些键 THEN SHALL 排除在 roundtrip 业务比对之外 + 指定重算责任方。
3. 🔴 WHEN 处置 `H6-2-subtotal-*` 六键 THEN SHALL 登记它们**被跨 entry 消费**
   （`useH6CrossSheet.ts` / `useH6Adjudication.ts` / `h6DisclosureModel.ts`）⇒
   重算时机必须在跨表勾稽读取**之前**，否则勾稽读到陈旧值。

---

## 阻塞项

- **BP-1 ~ BP-4**：平台级供给，相关任务标 `[ ]*`
- **BP-6 第三处**：本 spec 修（Req 7.1），修完全 H 归零
- **BP-8**：本 lane 成员按 HC-3 重算 = 删 `useH6FormData`；
  🔴 `useH6DualMode` 在链式复用链上，须与 lane 2 协调
- **BP-11**（新）：本 lane 族 C 2 处（Req 7.2）
- **BP-12**（新）：本 spec 修（Req 3），发起方与被害方都在本 lane
- **HC-10**：本 spec 处置（Req 4），并须给长期一致性归口而非只加前置断言
- 🔴 **无 canary**：三条主表键真库零载荷或 `[]` ⇒ canary 由 foundation 的 H9 承担
- 🔴 **TB 发布链首例**：本 lane 承担（Req 6）—— canary H9 与 H8 均无发布门
