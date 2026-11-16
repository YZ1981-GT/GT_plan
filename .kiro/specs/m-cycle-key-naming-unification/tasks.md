# Tasks — M 循环键名统一（占位，未开工）

> **状态：实施中（2026-11-16）**。Phase 0 现算完成（推翻 design §2 的三条前提）、
> 路径已拍板（A' = 逐行 JSON 单一来源）、任务 4 已实施并通过守卫 + 变异。
> 剩余：任务 5.2（M1 的 12 条 R2 结构差异，需业务裁决）+ 5.3（M2 28 条）+ 任务 6 收尾。
> 棘轮已从 65 条降到 40 条（M1 偿还 25 条）。
> 来源：`oo-writeback-template-parity-closure` 任务 9.2 的键名层（该 spec 已归档，
> 投影层已修完）。

- [x] 1. 开工前置现算（不改代码）—— **2026-11-16 完成，结论推翻 design §2 的核心假设**
  - [x] 1.1 现算 M 循环真库行数
    **结论：M 组共 34 行，明细表整表 JSON 形态 = 0 行。**
    现算（正确 JOIN = `working_paper.wp_index_id -> wp_index.id`，`checklist_responses.wp_id` 指向 `working_paper.id`）：
    | 形态 | 行数 |
    |---|---:|
    | M 组总行数 | 34 |
    | **明细表整表 JSON**（`*-full-data` / `*-detail-rows` / `M{n}-M{n}-{n}-*`） | **0** |
    | flat 形态 | 34（**全是 `M{n}-1-tb-amount` 审定表 TB 取数**，非明细表） |
    | `item_id` 含 `placeholder` | **0** |
    逐码：M1/M2/M3/M4/M6/M8/M9/M10 各 3 行、M5 6 行、M7 4 行，全部是 `M{n}-1-tb-amount`
    （外加 M5 三个小计键、M7 一个 `M7-disclosure-soe-row-0-policy`）。
    ⇒ **「明细表整表 JSON 有存量数据、改前端要迁移」这一前提不成立**：明细表从未写入过任何数据，
    路径 A 的存量迁移成本 = **0**。
  - [x] 1.2 现读 10 个 `useM{n}Detail.ts` 存储形态
    **结论：不是「flat vs 整表 JSON」二选一，而是三种形态。**
    | 表 | 形态 |
    |---|---|
    | M1 / M2 / M3 / M7 / M9 / M10 | **整表 JSON（`*-full-data`）+ 逐行 JSON（`*-row-N-data`）并存** |
    | M4 / M5 / M6 / M8 | **只有逐行 JSON（`*-row-N-data`）**，无 full-data |
    `getField` / `saveField` 调用面：10 个文件里只有 `useM9Detail.ts` 有 1 处 `getField`，
    其余 **0 处** ⇒ 「另有 flat `getField` 通路并存」这一 design 描述**不成立**。
    逐行 JSON 的键形状（`{key, ...}`）与契约 `column_key` 的对应关系是**下一层的真问题**。
  - [x] 1.3 现读契约 `m*.json`
    **结论：10 份契约完全一致 —— `review.html_store.shape = flat_key_value`、
    `row_identity_kind = template_row_key`、`store_item_id = None`（不是 `placeholder`）。**
    memory / 原 spec 记的「`store_item_id` 写成 `placeholder`」**已过期**（现算 0 处 `placeholder`）。
    契约 sheet/table：m1→m101-managed/m1_detail_rows、m2→m201-unlisted-managed、
    m3→m301、m4→m401、m5→m501、m6→m601、m7→m701、m8→m801、m9→m901、m10→m1001。
  - [x] 1.4 现读棘轮基线
    **结论：棘轮只覆盖 M1 / M2 两张表（不是 10 张），基线 65 条真实，当前 8 passed 全绿。**
    `_BASELINE_PROVIDER_ONLY`：M1 18 条 / M2 19 条；
    `_BASELINE_FRONTEND_ONLY`：M1 19 条 / M2 9 条。
    四条判据齐备：①provider-only 禁增 ②frontend-only 禁增 ③基线自证（已对齐却没删会红）④总量单向棘轮。
  - [x] 1.5 现算扫描器 `{sheet}` 拼键缺口
    **结论：`contract_field_names_scan.py` 不在 `backend/scripts/`，实际在
    `backend/tests/workpaper_sync/contract_field_names_scan.py`（是测试辅助模块，不是 check 脚本）。**
    M 循环 10 个 composable 的模板串现算共 33 处，**没有一处是 `{sheet}-{field}` 形态**：
    全是 `M{n}-2-row-${index}-data`（逐行数据键）与 `m{n}-det-${Date.now()}`（前端本地行 id）。
    ⇒ design §14.3 备查的「`{sheet}` 参数拼键识别缺口」**在 M 循环不适用**；
    它是 G7 那类（`MINORITY_FS_SLOT`）的问题，本 spec 不需要修扫描器。

- [x] 2. 用户拍板 design §2 的路径 —— **2026-11-16 用户选「按建议来」= 走 design §3 的建议（路径 A 的修正版）**
  现算后路径 A 需要修正：不是「统一到 flat 逐字段」，而是**统一到「逐行 JSON 单一来源」**
  （M4/M5/M6/M8 已是这个形态，M1/M2/M3/M7/M9/M10 需要把 `*-full-data` 这条并行写入删掉）。
  详见 design §2.1（本轮更正）。

- [x] 3. 按拍板结果写完整 requirements / design / tasks
  本轮**不替换占位三件套**，而是就地补 `design §2.1 现算更正`（三条过期前提逐条更正 +
  修正后的路径 A'）+ 本 tasks 的现算结论。理由：工作量因现算大幅缩小（见任务 4 交付），
  重写三件套的成本高于收益；占位文档的「状态」已改为实施中。

- [x] 4. 实施：路径 A' = 逐行 JSON 单一来源
  **改动面 8 个文件**（5 个 composable 删整表写入 + 3 个 TabDetail 补逐行降级）：
  | 文件 | 改动 |
  |---|---|
  | `useM1Detail.ts` | 删 `_syncFullData()` 函数 + 调用（写 `M1-M1-2-full-data`） |
  | `useM2Detail.ts` | 删两处 `debouncedSave('M2-M2-2-{listed,unlisted}-full-data')` |
  | `useM3Detail.ts` | 删 `_syncFullData()` 函数 + 调用（写 `M3-M3-2-full-data`） |
  | `useM7Detail.ts` | 删 `_syncFullData()` 函数 + 调用（写 `M7-2-full-data`） |
  | `useM10Detail.ts` | 删 `_syncFullData()` 函数 + 调用（写 `M10-2-full-data`） |
  | `M1TabDetail.vue` | `_restoreRows` 补「逐行 per-row keys」降级分支（原**只读整表** ⇒ 删整表后刷新会丢） |
  | `M2TabDetail.vue` | listed / unlisted 两处各补降级分支 |
  | `M10TabDetail.vue` | `_restoreRows` 补降级分支 |

  **M9 刻意不动**：它的 `_syncFullData` 写的是 `M9-2-detail-rows`（**不是** `full-data`），
  且那是 `M9TabDetail._initDefaultRows` 的唯一读取来源 —— 删了 M9 就真没有明细存储。

  **为什么必须先补降级分支再删写入**：现读发现 M1/M2/M10 的 `_restoreRows` 原本**只读整表**
  （M3/M7 已有降级）。若只删写入不补降级，刷新后明细全丢 —— 这是比原缺陷更严重的行为变更。
  降级分支照 M3 的已验证写法（`key.startsWith('M{n}-...-row-') && key.endsWith('-data')`）。

  **新守卫** `backend/tests/test_m_detail_single_storage_source.py`（11 例）：
  ①5 个 composable 不得再写 `*-full-data`（含 `_syncFullData` 函数名残留）
  ②逐行写入必须仍在（删了整表却没写逐行 = 数据存不下来）
  ③反向断言 M9 的 `M9-2-detail-rows` 不得被「统一」掉。

  **变异验证**：把整表写入加回 `useM1Detail.ts` ⇒ 守卫 RED 且精确点名
  `useM1Detail.ts 又写了整表 full-data: ['M1-M1-2-full-data']`；逐字节还原后 11 passed。

  **验证**：
  - `test_m_detail_single_storage_source.py` **11 passed**
  - `test_m_detail_keys_match_provider.py`（棘轮）**8 passed**（65 条基线未动）
  - `m9-detail-import-refresh.spec.ts` **2 passed**（M9 未动，确认没误伤）
  - 前端全量 vitest 现算 45 failed / 15306 passed —— **已用 A/B 对照证实预存**：
    把我的 8 个文件临时换成 HEAD 版后 `useF5Integration.spec.ts` 同样 1 failed
    （8 文件逐字节还原确认）

- [~] 5. 棘轮逐条偿还（原 65 条 → 现 40 条；M1 已完成、M2 未动）
  - [x] 5.1 **M1 已偿还 25 条**（18+19 → 7+5），且发现真缺口不是「键名不一致」
    **直读模板「明细表M1-2」（openpyxl，R12 组头 + R13 列头 + merges）确认真实结构**：
    `A1:U` 共 **21 列**，与 provider `DETAIL_SHEET.fields` 21 条**逐列一致**：
    | 组头（R12） | 列（R13） |
    |---|---|
    | （无组头） | A 股东名称 / B 公司代码 / C 股东类型 |
    | D12:G12 未审数 | D 期初数 / E 本期增加 / F 本期减少 / G 期末数(formula) |
    | H12:I12 期初调整 | H 账项调整 / I 重分类调整 |
    | J12:K12 账项调整 | J 本期增加 / K 本期减少 |
    | L12:M12 重分类调整 | L 本期增加 / M 本期减少 |
    | N12:Q12 审定数 | N 期初数 / O 本期增加 / P 本期减少 / Q 期末数（后三 formula） |
    | （无组头） | R 期末账龄 / S 超过1年未支付的原因 / T 相关文件索引号 / U 备注 |

    **真实缺口 = 前端只接了 3 列（A/C/U），10 列完全没接**：
    B 公司代码 / H 期初账项调整 / I 期初重分类 / J~M 四个本期调整 / R 期末账龄 /
    S 超1年原因 / T 相关文件索引号。**不是键名拼写问题。**

    偿还动作（两步，均不需业务裁决）：
    ①`M1DetailRow` 补 10 个字段，键名用 provider `json_key` 真名（不按中文表头反推）：
    `companyCode` / `priorAdjAje` / `priorAdjRje` / `currentAjeIncrease` /
    `currentAjeDecrease` / `currentRjeIncrease` / `currentRjeDecrease` / `aging` /
    `overdueReason` / `refIndex`（`priorOpening` 归到 R2，见下）
    ⇒ **provider-only 18 → 7**；
    ②14 个「模板无此列」的纯 UI 派生键登记进 `_UI_ONLY_KEYS` 并在 `_M1_UI_ONLY_CLAIM`
    逐项声明：`shareholdingRatio` / `currency` / `declaredDate` / `resolutionRef` /
    `distributionRatio` / `distributionBase` / `expectedDeclared` / `declareDiff` /
    `paidDate` / `paymentMethod` / `withholdingTax` / `netPaidAmount` / `crossRefDiff` /
    `periodChange` ⇒ **frontend-only 19 → 5**。

    **新增 3 条可伪证断言**（防 `_UI_ONLY_KEYS` 变成「夹带私货」的后门）：
    ①`test_m1_ui_only_claims_have_no_provider_column` —— 14 个豁免键必须**真的不在**
    provider 声明里（若 provider 新增同名字段 = 模板补了列 ⇒ 豁免错，必须挪回对账）；
    ②`test_m1_ui_only_claim_matches_registered_ui_only_both_ways` —— 声明与
    `_UI_ONLY_KEYS` **双向**一致（单向会漏「多出来的豁免」）；
    ③`test_m1_ui_only_claim_covers_every_frontend_only_key` —— 前端每个键必须有归属
    （接真名 / UI 豁免 / 进基线），**无人管的键会静默消失**。

    **变异 3/3 全 RED**：往 `_UI_ONLY_KEYS` 夹带 `priorOpening`（有模板列）⇒ RED；
    从 `_M1_UI_ONLY_CLAIM` 删 `crossRefDiff`（漂移）⇒ RED；
    把 `endBalance`（R2 基线键）塞进豁免 ⇒ 两道判据同时 RED（基线自证 + 方向 2）。
    逐字节还原后 11 passed。

    守卫 `test_m_detail_keys_match_provider.py` **11 passed**（8 原 + 3 新）；
    `test_m_detail_single_storage_source.py` **11 passed**（任务 4）；
    `m9-detail-import-refresh.spec.ts` **2 passed**（M9 未动）。

  - [ ] 5.2 **M1 余 12 条是 R2 结构差异，需业务裁决**（不能用键名对齐解决）
    provider 侧 7 条：`priorOpening`（D 期初数）/ `increaseAmount`（E 本期增加）/
    `decreaseAmount`（F 本期减少）/ `closingBalance`（G 期末数公式）/
    `auditedOpening`（N）/ `auditedIncrease`（O）/ `auditedDecrease`（P）/
    `auditedClosing`（Q，↔ 前端 `endAudited`）。
    前端侧 5 条：`beginBalance` / `declaredAmount` / `paidAmount` / `endBalance` /
    `endAudited`。
    **语义对照（需业务裁决）**：
    | 模板 | 前端 | 是否同一含义？ |
    |---|---|---|
    | D 期初数（未审） | `beginBalance` 期初应付余额 | 很可能是 |
    | E 本期增加（未审） | `declaredAmount` 本期宣告股利 | **不一定**（宣告≠全部增加） |
    | F 本期减少（未审） | `paidAmount` 本期支付 | **不一定**（支付≠全部减少） |
    | G 期末数（=D+E−F 公式） | `endBalance` 期末应付余额 | 若是 D+E−F 则等价 |
    | Q 期末数（审定，公式） | `endAudited` 期末应付（审定数） | 很可能是 |
    | N/O/P 审定期初/增/减 | 前端**无对应** | 前端缺 3 个审定列 |

    ⇒ 这一层要么改前端行模型（宣告/支付 → 期初/增/减），要么在契约侧加字段映射。
    两者都要动已发布 representation 或 10 个宿主的读写语义 ⇒ **需用户裁决后再做**。

  - [ ] 5.3 M2 未动（19+9 = 28 条）：照 M1 的方法做（直读模板定列 → 补字段 → 豁免声明 → 变异）

- [ ] 6. 收尾：干净 worktree 跑守卫、推送、登记 INDEX
