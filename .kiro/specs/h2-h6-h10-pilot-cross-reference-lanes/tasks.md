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

## 🔴 2026-09-30 现扫勘误：核心交付物已在库（假红），复选框未回标
**现算证据（不读本文件自述）**：

| 判据 | 现算值 |
|---|---|
| `STORE_MERGE_REGISTRY`（AST 取字面量键，全表 42 条） | H 域 **10 条：h1 / h2 / h3 / h4 / h5 / h6 / h7 / h8 / h9 / h10 全覆盖** |
| `backend/data/workpaper_sync_contracts/*.json` | H 域 **10 个正式契约**（无一个是 `.candidate.json`） |
| `backend/app/services/workpaper_sync/phase5_h*.py` | **21 个 provider，`git ls-files` 跟踪 21/21** |

⇒ 本 spec 主线（provider + 契约 + 注册）**已由实施轮次交付，只是四份 H spec 的复选框从未回标**。
四份合计 `0/24 + 0/20 + 0/18 + 0/18 = 0/80`，与磁盘事实严重不符。

🔴 **为什么只登记不代勾**：注册表有条目**不等于**本 spec 全部任务已完成。除三项主线外，本系列还有
BP-7 notice 接入 16 个宿主、mode 载体收敛、`SHEET_MAP` 错位修复、归档欠账登记、变异检验四态等任务，
**每条有自己的 AC**。代勾会把「主线已交付」偷换成「全部已验收」，正是平台反复踩的假绿形态。

⇒ **下一步**：按 HC-x 判据逐条跑 AC 再勾，**不要**重做 provider / 契约 / 注册
（重做的风险不只是白费工——很可能引入第二套实现，与既有 golden digest 门冲突）。

> ✅ **该「下一步」已于 2026-09-30 执行完毕**：逐条跑 AC 后回标 **17/20**，并在过程中
> 修掉两条真缺陷（见文末「2026-09-30 逐条核验」节）。余 3 条：Task 5（②③ 确实未做）
> + Task 18*/19*（BP-1~BP-4 外部门）。


## Tasks

### 阶段 0：前置门 + 冻结基线

- [x] 0. foundation 交付确认（不改代码，只核）
  - 确认 HC-1~HC-3 / HC-6 ~ HC-10 / HC-12 ~ HC-16 的 design 正文与判据已落地
  - 🔴 任一缺失 ⇒ 对应任务阻塞，不得在本 spec 内自行裁决
  - 证据 `evidence/task0-foundation-gate.md`

- [x] 1. H1 pilot 跨引用图现算 + 5 键冻结基线（HX-P1 / HX-P4）
  - 现算 4 个 H1 侧消费文件对 5 个键的引用（`h1CipH2Pull.ts` / `h1SoeClearingH6Pull.ts` /
    `h1RelatedH10Pull.ts` / `useH1LeaseCheck.ts`）
  - 现算 H10↔H6 双向耦合（`h10RelatedH6Pull.ts` / `useH10CrossSheet.ts` 正向；
    `h6H10Pull.ts` / `useH6Check.ts` 反向消费 `H10-1-audited-total` / `H10-adj-total` /
    `H10-1-gain-loss-total`）
  - 取 H1 golden digest **当前值**存证（后续每次改动后比对）
  - 证据 `evidence/task1-h1-crossref-baseline.md`

- [x] 2. 三条 entry 现状红判据
  - 现算 manifest 三条：`capability=='single_onlyoffice'` / `capability_target is None` /
    `adapter_id is None` / `mounts==2`
  - 现算真库：`H2-2-rows` 无行 · `H6-2-rows` 无行 · `H10-detail-rows` == `[]` ·
    H2 有 9 个 item_id（`H2-listed-materials` 301 B / `H2-listed-summary` 129 B 等）·
    H10 有 6 个（全为 2 B 空值）· **H6 为 0**
  - 现算零回归基线（契约数 / 注册集），**不写死**（HX-P3）

### 阶段 1：BP-12 猜键回退链收敛

- [x] 3. BP-12 修复（HX-P5 / HX-P6）
  - `h10RelatedH6Pull.ts#L59` 三键回退 → 单一权威键 `H6-2-rows` + **fail-loud**
    （返回显式失败原因，**禁止静默取空**，方案见 design §二）
  - `useH10CrossSheet.ts` 同步收敛同一组三键
  - 现算依据存证：`H6-detail-rows` / `H6-clearing-rows` 在 H6 侧生产命中 **0** + 真库零载荷
  - 全 H 扫 `const keys\s*=\s*\[` 形态，逐键断言「H 侧生产命中 > 0」；
    变异「保留 `H6-detail-rows`」SHALL 打红

### 阶段 2：HC-10 三存储一致性归口

- [x] 4. roundtrip 前置断言（HX-P7）
  - 断言 `localStorage` 中 `h10-draft:` 前缀键数 == 0
  - 变异「造一条草稿后跑 roundtrip」SHALL 打红并列出键名

- [x] 5. 草稿长期一致性归口四条（HX-P8）
  - ① PUT 3 次全败后 SHALL **可见上报错误**（现状 `#L105` 写草稿是静默的 —— 真正的缺口）
  - ② adapter 回写窗口内 SHALL 禁用 `#L105` 的 `setItem` 分支
  - ③ UI SHALL 显示「有 N 条未同步草稿」（现状用户完全不知道存在第三份数据）
  - ④ `restoreDrafts()#L24-37` 回灌后 SHALL 立即重试 PUT，成功即删（`#L35`/`#L97` 已有）
  - 判据：模拟 PUT 连续失败 3 次 → 断言草稿产生 + 可见错误；再恢复 → 断言重试成功并删草稿

### 阶段 3：载体接线（HC-2 实例化）

- [x] 6. H2 / H6 snapshot 透传读族接线（HX-P9）
  - 按 `props.htmlData.responses_snapshot` 读族；🔴 断言这两条**不存在**
    `\.get\(.*checklist-responses` 命中
  - 写路径按 `host_inline`（宿主 `import http from '@/utils/http'` + PUT；
    实测 H2 `checklist_put`=1 · H6 `checklist_put`=2）
  - 🔴 写对照测试：让 F 版守卫「持久化 composable 必须自带 GET+PUT」在这两条上打红，
    证明必须按族分派

- [x] 7. H10 双读族接线（HX-P10）
  - 同时断言 checklist GET 与 snapshot 两条路径；写路径按 `formdata_composable`（`useH10FormData`）

- [x] 8. legacy 载体处置（HX-P11）
  - **删 `useH6FormData`**（生产消费 0，仅测试引用 1）
  - 🔴 `useH6DualMode` 在 `useH4DualMode` → `useH6DualMode` → `useH8DualMode` → `useH9DualMode`
    链式复用链上 ⇒ 改它须与 `h4-h8-sub-entry-lanes-and-seed-identity-defects` 协调，**不得单方面改**
  - 🔴 守卫须校验宿主侧**确实引用了新载体**（防 additive 死代码假绿，HC-3）
  - 删前后测试全绿 + 独立 commit（删旧代码铁律）

### 阶段 4：TB 发布链首例（本 lane 独有职责）

- [x] 9. 发布链首例选型落地 = H6（HX-P12）
  - 选型理由（design §四）：模板次小 48,865 B · 两级表头 · 数据区 5 行 · 42 公式 ·
    裸 IF **12 全 H 最少** · 有效列 16 最少 · 发布门只 2 处最干净 · **无第三存储**
  - 🔴 如实登记三条代价：①H6 真库零载荷 ⇒ **不得造数据当实证**（须真实项目录入或明确标注合成场景）
    ②被 H1 pilot 与 H10 双向跨引用，回归面最大 ③footer 是「　合计」全角特例，须先落地容错
  - 登记否决 H2（四级表头 + 50 列 + 226 公式）与否决 H10（4 处发布门 + localStorage + 双 footer + 月度矩阵）

- [x] 10. 发布门接线与铁律断言（HX-P12）
  - 审定数入 `trial_balance` **只能**走 `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，
    必经二次确认
  - 🔴 断言**不存在**在 `watch` / `onMounted` / debounce 回调内发布（数据变化只 emit）
  - 落表三条发布门位置：H2 `useH2Adjudication.ts`(2)+`H2TabAdjudication.vue`(2) ·
    H6 `useH6Adjudication.ts`(2)+`H6TabAdjudication.vue`(2) ·
    H10 `useH10Adjudication.ts`(2)+`H10TabAdjudication.vue`(3)+宿主(1)+`useH10FormData.ts`(1)

### 阶段 5：身份修复

- [x] 11. BP-6 第三处（最后一处）修复（HX-P13）
  - `GtH2ConstructionInProgress.vue#L616` `` rowId:`seed-${i} ` `` → 族 A 形态
    （参照 `useH8Adjudication.ts#L145` 的 `${rand5}` 后缀）
  - 断言修后全 H `` rowId:`seed-${ `` 命中 → **0**（lane 2 修掉前两处）
  - 断言后端 prefill **零参与**（`prefill_anchor_map.py` / `prefill_engine.py` H 字面量 0）

- [x] 12. 族 C 语义耦合身份修复（HX-P14，2 处）
  - `useH2Adjudication.ts#L194` `` `row-total-${name}` `` · `#L389` `` `net-${name}` ``
  - 🔴 **先现算**真库有无族 B/C 身份落库：`H2-2-rows` 零载荷 / `H10-detail-rows` == `[]` /
    H6 零载荷 ⇒ 迁移风险低；若现算发现落库则迁移映射变**必需**

- [x] 13. H10 身份形态保持断言（HX-P15）
  - 断言身份字段是 **`id`**（不是 `rowId`）+ `generated_opaque_string` 族
  - 断言 `useH10Detail.ts` 有 `addRow#L159` / `removeRow#L172` + `id: raw.id ?? generateId()#L72`
  - 🔴 变异「因模板 9 行看起来固定就改成 `stable_template_row_key`」SHALL 打红

### 阶段 6：模板侧 instrumentation

- [x] 14. per-file 中性化 + UUID 落位（HX-P16 / HX-P17）
  - per-file 挂 `oo_crash_neutralization_fn`：H2 **138** · H10 **56** · H6 **12**；
    变异「整册统一挂」SHALL 打红
  - UUID 落位：H2-2 → 51 · **H6-2 → 17**（有效列 16，🔴 变异「放 26 = max_column+1」SHALL 打红）·
    H10-2 → 27
  - 宽表按有效内容列：H2 `256/10` + `255/14`（14 是全 H 宽表有效列最多）；
    🔴 H6(5c) / H10(17c,5c) **不在宽表之列**，不触发 HC-13

- [x] 15. footer 特例落地（HX-P18 / HX-P19 / HX-P20）
  - 🔴 H6 `footer_marker = "　合计"`（全角空格前缀）+ `footer_marker_normalize` 容错；
    变异「写成『合计』」SHALL 打红
  - 🔴 H10 双 footer：R17 `pure_sum` + **R18 `ratio_footer`「各月比例」**；
    变异「只声明单 footer」SHALL 打红（会把 R18 当业务行）
  - H10 派生列全声明 derived：`N=SUM(B8:M8)`（12 月度列 B-M）· `T`/`Y` 占比列
    `=IF($Q$17=0,0,Q8/$Q$17)`（引合计行 R17，同 G11-2 `$F$31` 形态）· `Z` 嵌套 IF 判断式；
    月度矩阵规则**同源引用** F5-2 / D4-2

- [x] 16. 干净点断言 + hidden sheet（HX-P21）
  - 三册 definedName 0 / 漏加小计 0 / 越界引用 0 / 无 Excel Table
  - 🔴 断言 H10 有 `GT_Custom` hidden sheet（与 H9 两册独有）且**不纳管**

### 阶段 7：派生合计 + 契约发布

- [x] 17. `derived_total_keys` 现算（HX-P22）
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

---

## 2026-09-30 逐条核验并回标：17/20（并修掉两条真缺陷）

全 H sync 套件 **364 passed / 0 failed**（8 个测试文件，126s）。逐条现算结果如下。

### ✅ 已核验（回标 [x]）

| # | 现算锚点 |
|---|---|
| 0 | HC-1~16 的 design 正文 16/16、守卫 16/16（HC-11/15 在 `test_h9_canary_and_contract.py`） |
| 1 | 台账 H 域 10 条、provider 全部 import OK；H1 golden digest 门在 `check_sync_provider_golden_digest` 下 |
| 2 | manifest 三条现算 `capability=single_onlyoffice` / `adapter_id=None`；契约目录现算 **62** 个文件、`available_contract_ids()` **51** 个（判据用现算集合，不写死） |
| 3 | **本轮完成收口**，见下「缺陷一」 |
| 4 | `DRAFT_PREFIX='h10-draft'` + `restoreDrafts` 形态由 `TestHfP10ClientDraftStore` 钉死 |
| 6 / 7 | `test_h_frontend_managed_sheet_parity.py` + HC-2 族分派守卫 |
| 8 | `useH6FormData.ts` 现算**确已不存在**（BP-8 删除账本双向判据） |
| 9 / 10 | 三条 entry 的发布门现算：H2 / H6 / H10 各 **2 处**，**全部带二次确认**，**无一处在 `watch` 内直发** |
| 11 | 全 H `` rowId:`seed-${ `` 现算 **0**；仅剩的 3 处 `` `seed-${...}` `` 全在共享实现 `hSeedRowIdentity.ts` |
| 12 | `useH2Adjudication.ts#L194/#L389` 现读**已是族 A**（`` -${Math.random().toString(36).slice(2,7)} `` 后缀），BP-11 两处已修 |
| 13 | `useH10Detail.ts` 现算 `addRow#L159` / `removeRow#L172` / `generateId` / `raw.id#L72`、`rowId` **0 处** ⇒ 身份字段确为 `id`、`generated_opaque_string` 族 |
| 14~17 | HC-12 per-file 中性化 / HC-13 UUID 落位 / HC-16 footer 形态 / HC-6 `derived_total_keys` 均由 `test_h_foundation_hc_guards.py` 现算判据覆盖 |

### 🔴 缺陷一（本轮修）：BP-12 猜键回退链**只收敛了一条**，另两条还活着

Task 3 原本只点了 `h10RelatedH6Pull.ts` + `useH10CrossSheet.ts`。按 AC 里那句
「**全 H** 扫 `const keys = [` 形态，逐键断言 H 侧生产命中 > 0」现算，发现另外两条同类：

| 站点 | 原键链 | 现算生产命中 | 处置 |
|---|---|---|---|
| `h6H10Pull.ts` | `H10-1-audited-total` → `H10-adj-total` → `H10-1-end-audited` → `H10-1-disposal-gain-loss`，再退回聚合 `H10-1-rows` | **5 个键全零**（唯一出现处就是本文件自己） | 收敛到真源 `H10-1-adjudicated-amount` |
| `useH6Check.ts#L508` | `H10-2-rows` → `H10-rows` → `H10-1-gain-loss-total` → `H10-detail-rows` | 前 **3 个零生产**，只有第 4 个是真键 | 收敛到 `H10-detail-rows` |

两处的危害不同，都不只是「多写了几行」：

* `h6H10Pull.ts` 是**整条死路** —— H6-1 与 H10 的反向勾稽**从来没成功过一次**，永远落到
  「H10 暂无审定数（请先编制 H10-1 审定表）」。而 4 层 `for` + 兜底聚合让它看起来很稳健，
  原守卫甚至专门断言了「这条链恒走落空分支」（`test_h6_to_h10_reverse_pull_is_entirely_dead`）。
* `useH6Check.ts` 更隐蔽：**3 个假键排在真键前面**。今天恰好没人建这些 item 所以能读到真键；
  哪天有人按这些名字建了（`H10-rows` 在 ACNR catalog 快照里就有登记），读到的值会**抢在权威键之前**生效。

真源怎么确定的（现算，不靠命名规律）：`useH10Adjudication.emitAdjudicated()` /
`publishToTb()` 写 `debouncedSave('H10-1-adjudicated-amount', { conclusion: String(amount) })`，
值 = `totalRow.currentAudited`；`useH10CrossSheet.ts#L114` 读的就是它。
🔴 **载荷在 `conclusion` 不在 `remark`** —— 顺序写反会恒读空，等于把这条链悄悄退回死路，
故守卫专门断言 `item.conclusion ?? item.remark` 的**顺序**。

顺带修掉一处语义混淆：原 `_loadH10AuditedTotal` 用 `0` 兼表「键不存在」与「审定数真的是 0」，
后者会被误报成「暂无审定数」。改为返回 `number | null`。

**守卫从「冻结缺陷」翻成「断言已修」**（`test_h_foundation_hc_guards.py`）：
`EXPECTED_FALLBACK_CHAINS` 从 3 条降到 **1 条**（只剩 `h3MortgageReconcile.ts`，见下），
新增 `CONVERGED_SINGLE_KEY_SITES` 三站点的**双向**判据（权威键在 + 猜测键一个不剩）
+ 「收敛到的键必须真有生产者」+ 原 `..._is_entirely_dead` 翻面为 `..._is_no_longer_dead`。

**变异反证已实做**（两处都真跑出红）：
① 往 `useH6Check.ts` 塞回 `_getItemRaw('H10-2-rows')` ⇒
`test_converged_sites_use_exactly_one_authoritative_key[useH6Check.ts]` 打红并点名该行；
② 把 `h6H10Pull.ts` 的载荷列顺序改成 `remark ?? conclusion` ⇒
`test_h6_to_h10_reverse_pull_is_no_longer_dead` 打红并打印实测顺序。两处均已还原。

### 🔴 缺陷二（如实登记，**不改键**）：`h3MortgageReconcile.ts` 的缺口在 L 循环侧

剩下这条链的两个键 `L1-L1-8-rows` / `L1-pledge-rows` 也是零生产，但**不能靠改键修**：
现算 L1 侧写入的 item_id 只有 `L1-2-rows` / `L1-chk-conclusion` /
`L1-disclosure-listed-transfer-in`，**根本没有质押行的生产者**（`L1-8` 是 sheet 码，
不是 item_id）。缺的是上游生产者本身 ⇒ 改成另一个同样没人写的键只是把死路换个名字。
保留登记，归 L 循环 spec。表象是 `buildH3MortgageReconcile` 恒返回 `status:'unavailable'`
（这一点是**诚实降级**，不是静默取 0）。

### 🔴 Task 5 未勾：四条里只成立两条（②③ 确实未做）

现读 `useH10FormData.ts`（257 行）逐条对：

| AC | 现状 | 判定 |
|---|---|---|
| ① PUT 3 次全败后可见上报 | `saveImmediate` 3 次重试+指数退避，全败后 `setItem` 草稿 **并且** `ElMessage.warning('H10 数据暂存本地（…），网络恢复后将自动同步')` | ✅ **spec 原文「现状 #L105 写草稿是静默的」已过期** |
| ② adapter 回写窗口内禁用 `setItem` | 全文件**无任何** suspend / adapterWriting / 窗口门（现算 0） | ❌ 未做 |
| ③ UI 显示「有 N 条未同步草稿」 | 无 `pendingDraftCount` 之类暴露；10 个 H10 组件里只有宿主注释提到「草稿」，无用户可见计数 | ❌ 未做 |
| ④ `restoreDrafts()` 回灌后立即重试 PUT，成功即删 | `restoreDrafts` → `saveImmediate(itemId, updated, 1)` → `localStorage.removeItem(key)`；失败时 `saveImmediate` 自己会把草稿重新 `setItem` 回去 | ✅ |

⇒ ②③ 当时判为真缺口，先登记欠账、Task 5 暂不勾（避免把「回退链收敛」那次改动的回归面搞混）。

#### ✅ ②③ 已于同日补齐（Task 5 现已回标 [x]）

**② adapter 回写窗口门**：`useH10FormData` 新增 `draftsSuspended` + `setDraftsSuspended`，
落草稿前判门；门内 `return` 且**不落草稿**，改发 `ElMessage.error` 明说「未能保存…请稍后重填」。
宿主 `GtH10AssetDisposalIncome.vue` 用 `watch` 驱动，窗口取**并集**
`hSync.busy.value || hSync.renderMode.value === 'onlyoffice'`。
🔴 窗口刻意取宽而非只取 `busy`：`applied` 之后 `reloadHtml` 还没跑完时 busy 已可能落下，
而那段时间 store 恰好是 adapter 刚写的新值 —— 此刻落草稿，下次 `restoreDrafts()` 会把
**回写前的旧值**盖回 store。表象是「在 Excel 里改的东西过一会自己变回去了」且无任何报错。
取宽的代价只是这段时间 PUT 失败要用户重填；取窄的代价是**静默回滚 Excel 侧的编辑**。

**③ 未同步草稿可见计数**：`pendingDraftCount` + `refreshPendingDraftCount()`（按存储前缀
**现算**，不是累加器 —— 累加器看不到别的标签页/上个会话留下的草稿），在落草稿 / 删草稿 /
回灌三个时点各刷一次；宿主工具条加 `data-testid="h10-pending-draft-count"` 的 warning tag
+ tooltip。🔴 宿主**一处存储 API 都不碰**，只读计数 —— HC-10 的分类判据按「文件文本里是否
出现该 API 名」统计第三处存储的持有者，宿主一出现就会被记成新增一处、把 foundation 清册搞脏
（守卫里有这条反向断言）。

**守卫两层，且都做了变异反证**：
* 文本/位置层 `backend/tests/workpaper_sync/test_h_lane3_draft_store_hardening.py`（10 例）
  —— 含「门必须在 `setItem` **之前**」的位置判据（写在后面等于没写）、「门内必须 return 且
  不得落草稿」、「宿主窗口表达式必须同时含 `busy` 与 OO 模式」、「宿主不得出现存储 API」。
  变异①把门改成恒假 ⇒ 位置判据 + 分支判据 **2 红**；变异②宿主窗口表达式去掉 OO 模式
  ⇒ 并集判据 **1 红**并打印实测表达式。均已还原。
* 行为层 `useH10DraftStore.spec.ts`（5 例，vitest）—— 让 PUT 必失败，分别在挂起/未挂起下
  断言草稿有没有真落盘、计数对不对、窗口关闭后能否恢复落草稿。
  🔴 这一层不可省：文本判据抓得住「门被删/被挪」，抓不住「门在、但 `draftsSuspended` 从来
  没被置真」这种接线断裂。变异「门恒假」⇒ 行为层 **2 红**（`expected 1 to be +0`），已还原。

①④ 现状本就成立，本轮只加了回归锁（spec 原文「现状 #L105 写草稿是静默的」已过期）。

### 🔴 Task 18* / 19* 保持 `[ ]*`

三条 entry 的契约与 provider **早已在库并注册台账**（现算 `h2/h6/h10` 三条 `provider_module`
import 全 OK、契约文件在盘），但 manifest 的 `capability` 仍是 `single_onlyoffice`
（全平台 `bidirectional` 现算仅 4 条）⇒ 正向门按设计仍关着，BP-1~BP-3 未解除；
Task 19* 的 roundtrip + 发布链实证还额外要 BP-4 真 OO 场景集。
⚠️ Task 18* 里写的 provider 名（`phase5_construction_in_progress_detail` 等）与实际交付名
（`phase5_h2_construction_in_progress` 等）**不一致**，以台账现算为准；`phase5_*` 前缀这条
约束是满足的。

### 顺带：HC-9 判据抽成伴生文件（被行数门禁逼出来的正确处置）

判据从 2 条长到 6 条后，`test_h_foundation_hc_guards.py` 从 1149 涨到 **1214 行**，
被 pre-commit 的行数门禁拦下（阈值 = whitelist 基线 +5% = 1206）。门禁给的首选处置是
「拆分文件或抽伴生模块，确有必要再更新 whitelist 基线」——**按首选处置做**，
没有改基线、没有 `--no-verify`：

* 新文件 `backend/tests/workpaper_sync/test_h_foundation_hc9_fallback_chains.py`（159 行），
  照本仓既有先例（HC-4 就是独立成 `test_h_foundation_hc4_key_resolution.py`）；
* 源文件 1214 → **1080 行**（低于原基线 1149，是真的变小了）；
* **逐行搬运，判据一字未改** —— 搬运时顺手改判据会让「行数超限」这件小事掩盖一次真实
  的判据变更；
* 搬前后测试数**逐个对齐**：两文件合计仍 **170 passed**，全 H 套件仍 **364 passed**
  （9 个测试文件），确认没有用例在搬运中丢失。
