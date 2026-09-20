# Implementation Plan

## Tasks
- [x] 1. 源模板核定 gate：逐 sheet 核定 D4-17/18/19/20 列头、六区结构、item_id、稳定 id、日期方向与空/零/未知边界；删除或显式拒绝 D4-20 死配置。
  - _Requirements: 1.1, 1.4, 3.1_
- [x] 2. 共享公式/双模式 gate：接入 F-SHELL expression/refs/params/scope、后端权威执行与前端同定义预览，统一 mutation/sync/三方合并/ack/contract/representation。
  - _Requirements: 2.1, 2.2, 4.1_
- [x] 3. 实现 D4-17/18/19/20 专用 IO 与公式：保持业务方向和六区结构，重算派生值、两侧 item_id、动态 id 和未知映射语义。
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.3_
- [x] 4. 实现发现记录与人工确认门：跨期、折扣、退货、计提发现先留风险记录，人工确认方向/金额/证据后才形成 A13 请求。
  - _Requirements: 3.1, 3.2_
- [x] 5. 接入 A13/D4-1 持久联动：复用共享件，落实 durable ack、幂等 source identity、D4-1 去重追加、独立重试和防回环。
  - _Requirements: 3.3_
- [x] 6. 守卫与变异：验证专用 IO、item_id 双侧一致、截止非跨期语义、未知边界、公式同定义及四态变异。
  - _Requirements: 4.1_
- [x] 7. 真栈验收与收口：Playwright 实测 HTML/Excel 往返、三方合并、ack 失败恢复、A13/D4-1 独立重试，并完成 spec 结构与产物检查。
  - _Requirements: 2.2, 4.1_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"源模板未核定不得实现 IO","2":"共享 gate 未满足不得宣称双模式完成","4":"未人工确认不得写 A13","5":"无 durable ack 不视为成功"}}
```

## 实施进度（2026-09-19，append-only；上方 1-7 原文不动）

> 三姊妹 D4 检查表 spec 一并推进。本 spec（D4-17/18/19/20）**可做实部分已完成**，双模式真同步桥 provider 因平台环境依赖单列 blocked（与 IPO spec 同一边界）。

### 已做实（做绿 + 守卫 + 变异，对应 Task 1/3/4/6 的可测部分）

- **后端专用 parser + 分发（Task 3）**：`_d4_import_export.py` 新增 `_parse_d4_17_row`/`_parse_d4_18_row`/`_parse_d4_19_row`/`_parse_d4_20_return_row`/`_parse_d4_20_provision_row`；import 分发接线 D4-17/18/19/D4-20-current/post/provision；export 行构造分支；派生列单源（isCutoff 留 None、discountRate=折扣/收入重算、shouldProvide=base×rate/diff 重算，不信文件值）。
- **D4-20 子表键错位修复（Task 1，DEC-2）**：后端 item_id 映射 D4-20-current→`D4-20-current-returns`、D4-20-post→`D4-20-post-returns`、provision→`D4-20-provision`（改后端对齐前端键，不改前端 6 处引用）；导入导出两侧对称。
- **死配置删除（Task 1，DEC-1）**：裸 `D4-20` 从 `_SUPPORTED_SHEETS` + `_SHEET_HEADERS` 删除（前端只用三子表，从不导入导出裸 D4-20）。
- **跨期公式收敛（Task 3）**：D4-17 `checkCutoff` 改用 `useD4FormulaEngine.isCrossPeriodForward`（取反）、D4-18 用 `isCrossPeriodBackward`（取反），删除内联日期比较（公式引擎单一真源）。
- **A13 + D4-1 联动（Task 4）**：四表接 `useD4InspectionWriteback` 推 A13——D4-17/18 推 `isCutoff===false` 跨期问题、D4-19 人工 prompt 错报金额（不把折扣额自动当错报）、D4-20 推 `isAbnormal==='是'` 异常退货；全人工 @click 触发。
- **守卫 + 变异（Task 6 可测部分）**：`backend/tests/test_d4_cutoff_return_io_roundtrip.py`（8 passed，往返 PBT + poison 派生值重算 + item_id 双侧一致 + 死配置删除 + 分发守卫）；前端 `d4CutoffReturnWriteback.spec.ts`（14 passed，wpCode 字面量 + 人工触发不在自动回调 + 跨期走引擎 + 发现≠自动错报过滤）。

### [blocked] 双模式真 OOXML 同步桥（Task 2 的同步桥部分 + Task 7 真 OO 往返）

- [x] BB1 [blocked] 为 D4-17/18/19/20 在后端 `workpaper_sync` 建 managed sheet provider（照 `phase5_d4_ipo_checklist_sheets.py` 范式：字段列映射 + mapping_digest 冻结 + instrumentation + rows_table_payload + split/merge 投影）。
  - 已核定几何（权威 workbook `D/D4 收入底稿.xlsx` 含这 4 sheet）：D4-17/18 两级表头 row11/12 数据 row13 起 11 列 A-K（K 派生跨期）；D4-19 两级表头 row11/12 15 列 A-O（E 派生，UUID 用 Q 因 P 列被下拉选项占用）；**D4-20 一张物理 sheet 含 3 个受管区**（计提 row24/25-29、本期退货 row32/33/34+、期后退货 row38/39/40+）——「一 sheet 多受管区」是平台从未做过的新形态，IPO/D4-35 均为一 sheet 一区。
  - 阻塞原因：D4-20 多受管区是新形态有未知风险（footer 定位 + 多区行位移传播）；且真 OO 9.x 往返无环境可验（同 IPO spec B6 至今 blocked）。
  - _Requirements: 2.1, 2.2, 4.1_
- [x] BB2 [blocked] 前端 D4-17/18/19/20 从裸 `GtOnlyOfficeSheet` 迁 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`（对齐 D4-35/IPO 蓝本），依赖 BB1 后端契约。
  - _Requirements: 2.1, 2.2, 2.3_
- [x] BB3 [blocked] 真栈验收（Task 7）：Playwright 真实 HTML/Excel 往返、durable ack 失败恢复、A13/D4-1 独立重试。需 `start-dev.bat`（后端 9980 + 前端 3030 + OnlyOffice 服务）。
  - _Requirements: 2.2, 4.1_

## 真栈 Playwright 验证（2026-09-19，append-only）

> 环境重启后真栈实测（后端 9980 healthy + 前端 3030 + OnlyOffice healthy + 真 PG），真实项目「重庆和平药房2024」D4 底稿。全程 0 console error。测试数据已清理（真实项目零残留）。证据：`evidence/playwright-realstack-verify.md`。

- [x] RS1. D4-16 派生列重算真栈：录入 账面100000/口岸98000/申报95000 → 口岸差异自动算 2,000.00、免抵退税差异 5,000.00（精确读 DOM），diff-warn 单元格同步；「推送差异至 A13」按钮 hasDiff 门控 disabled→enabled。**公式引擎单源重算浏览器实证生效**。
- [x] RS2. D4-16 A13 全链路真栈（前端→事件桥→后端 POST→DB）：点推送 → ElMessage `已推送 1 项`（前端）+ `已记入未更正错报汇总 1 笔`（事件桥 ok>0）；DB `unadjusted_misstatements` 实证 source_wp_code=D4-16 / amount=7000(=\|2000\|+\|5000\|) / account=6001 营业收入 / type=factual。
- [x] RS3. D4-17 跨期公式收敛真栈：凭证2025-12-20(期内)+发货2026-01-05(期后,cutoff 2025-12-31) → 跨期列渲染 `×` = `!isCrossPeriodForward(...)`；「推送跨期至 A13」cutoffIssues 0→1 enabled。**内联 checkCutoff 收敛为引擎函数浏览器实证生效**。
- 🔴 RS4. 真栈印证 B3 缺口（非臆想）：D4-16 两次点击（间隔 48s > 去重窗 5000ms）→ DB 产生 2 条重复错报。`useA13MisstatementBridge.recentHashes` 内存 Map 去重窗口 5s、跨窗口/刷新失效。**durable ack 缺口真实存在**，属平台级基础设施（B3 blocked），影响全平台 ~35 个推送点。
- 附：在线编辑模式对 D4-16 能打开 OnlyOffice 渲染源模板结构，界面标「两侧数据未互通/各自独立保存互不同步」——印证 D4-13~20 走 legacy 假双向，真同步桥（BB1/BB2）未做，与 spec 登记一致。

## Task 2 共享公式/双模式 gate 复核（2026-XX，append-only；上方 1-7 + 既有进度原文不动）

> 本次以「gate 认证」身份复核 Task 2。**核对真实代码后发现上方 [blocked] BB1/BB2 记录已过时**——双模式同步桥在「批次B」实际已落地，仅真 OO 9.x 往返因环境依赖仍待验。据实更正如下（不改写历史行，仅补正当前事实）。

### 已认证做实（真实代码 + 测试证据）

- **公式定义单一真源 gate（Req 2.1/2.2）✅**：
  - D4-17 `checkCutoff` = `!isCrossPeriodForward(...)`、D4-18 = `!isCrossPeriodBackward(...)`，均走 `useD4FormulaEngine`，`checkCutoff` 体内无内联日期比较（guard 断言 `not.toMatch(row.voucherDate<=cutoff&&)`）。
  - **本次修复：D4-19 折扣比例单源违规**。原 `D4TabDiscount.vue` `calcRate` 内联 `discountAmount / revenueAmount`，与后端 `_parse_d4_19_row` 的 `(discount/revenue) if revenue>0 && discount>0 else 0` 是两份手写副本（正是本 gate 要拦的分叉，与 D4-17/18 已收敛的内联日期比较同类）。
    - 触类旁通修复：`useD4FormulaEngine.ts` 新增 `calcDiscountRate(discountAmount, revenueAmount)`（收入/折扣≤0 → 0，否则 discount/revenue）；`D4TabDiscount.vue` `calcRate` 改调该函数；后端语义逐字段对齐（未改后端，保持权威执行方一致）。
    - 守卫：engine 单测 +4（`calcDiscountRate`）；`d4CutoffReturnWriteback.spec.ts` +1 guard（锁 `calcRate` 走 `calcDiscountRate`、不再内联 `discountAmount/revenueAmount`）。
- **后端权威执行 provider + 契约（Req 2.2 后端侧）✅**：`phase5_d4_cutoff_forward_sheet`(d417-managed)、`phase5_d4_cutoff_backward_sheet`(d418-managed)、`phase5_d4_discount_sheet`(d419-managed)、`phase5_d4_return_sheet`(d420-managed，4 区 summary/provision/current/post) 均已纳入 `build_contract_payload()`，`parse_contract` 强校验通过（冻结契约 `41f1f23f…json` 含 d417/418/419-managed）。
- **前端 mutation/sync/ack/contract/representation 接线（Req 2.2 前端侧）✅**：D4-17/18/19/20 四表均从裸 `GtOnlyOfficeSheet` 迁 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`（entry `xlsx/gt-d4-operating-revenue`），三态中文同步标签（已同步/同步中…/同步失败）经 `syncStateTag` 现算——**非旧「两侧未互通」假双向**，是真桥接后的诚实状态。

### 测试证据（本次实跑）

- 后端：`test_d4_cutoff_return_io_roundtrip.py` + `test_d4_17/18/19/20_*_contract.py` → **34 passed**（`..\.venv\Scripts\python.exe -m pytest`）。
- 前端：`d4CutoffReturnWriteback.spec.ts` + `useD4FormulaEngine.spec.ts` + `.pbt.spec.ts` → **116 passed**（含 discountRate 新增 5 项）；4 改动文件 getDiagnostics 全 0。

### 仍 [blocked]（真外部依赖，不伪绿）

- **真 OO 9.x 往返 / durable ack 失败恢复 / A13·D4-1 独立重试 的真栈 Playwright（Task 7 / 原 BB3）**：需 `start-dev.bat`（后端 9980 + 前端 3030 + OnlyOffice 服务 + 真 PG）。inventory 记 gen55/57/59/64 已发布但标「真 OO 待验」。同 IPO spec B6 边界。
- **durable ack 平台缺口**：`useA13MisstatementBridge` 内存 Map 去重窗 5s、跨刷新失效（RS4 真栈已印证），属平台级基础设施，影响全平台 ~35 推送点，非本 spec 单点可闭环。

### Gate 裁决

- 可做实且可测部分（F-SHELL 定义/后端权威执行/前端同定义预览/mutation·sync·contract·representation 接线/公式单一真源）**已认证通过**并补齐 D4-19 单源守卫。
- 真 OO 往返与 durable ack 恢复**据实 blocked**（外部环境 + 平台级基础设施），legacy 假双向标签已不存在（四表均真桥接三态诚实标签）。


## Task 3 IO/公式 gate 复核（append-only；上方原文不动）

> 以「gate 认证」身份逐 facet 对照真实代码复核 Task 3（Req 1.2/1.3/1.4/1.5/2.3），并补齐导出投影侧与零边界守卫。核对 `_d4_import_export.py` + `test_d4_cutoff_return_io_roundtrip.py` 后据实认证。

### 逐 facet 认证（真实代码 + 测试证据）

- **1.2/1.3 业务方向与六区结构 ✅**：`_parse_d4_17_row`(凭证→发货单 forward)/`_parse_d4_18_row`(发货单→凭证 backward) 字段序即方向序；导出分支 D4-17 先凭证列后发货单列、D4-18 反之（新增 `test_d4_17_18_export_preserves_business_direction` 源级锁死方向不被对调）。D4-20 六区经三子表 provision/current/post 保结构，import 分发 + export 行构造两侧对称。
- **1.4 未知映射语义 ✅**：D4-17/18/19/20 四表 parser 不做 category/account/group 映射，录入列一律 `_safe_str/_safe_float` 原样保真——无「静默默归其他」面。全 D4 IO 面 grep「其他/__unknown__」确认唯一映射场景在 D4-32（`__unknown__` 独立组供人工映射，非本 spec），四表无此反模式。all-None 行 `if not row_dict: continue` 跳过不覆盖。
- **1.5 派生值单源重算 ✅**：isCutoff 留 None、discountRate=折扣/收入重算、shouldProvide=base×rate、diff=should−already，均不读文件派生列。原 PBT 已覆盖正数区 poison 重算；**本次补 `test_d4_19_discount_rate_zero_edge_single_source`** 专攻收入/折扣≤0 的 else 分支（不除零、不信文件污染比例）。**新增 `test_export_leaves_derived_columns_blank`** 锁导出投影侧派生列写空串（`isCutoff/discountRate/shouldProvide` 全文件不得 `data_row.get`；`diff` 因 D4-23 有同名合法列改按 D4-20-provision 分支体局部断言）——「派生单源」在导入 parser + 导出投影两侧对称守卫。
- **2.3 动态 id 与 item_id 对称 ✅**：import/export 两侧 item_id 映射对称（D4-17/18/19 → `{sheet}-rows`；D4-20-current/post → `D4-20-current-returns`/`-post-returns`；provision → `D4-20-provision`），`test_d4_20_subtable_key_alignment` 断言后端两侧 ≥2 次映射 + 前端 `D4TabReturn.vue` 确用这些键。四表 store 为行数组，import 整体替换 rows，每行 `r-{uuid4}` 稳定前缀（与全 D4 parser 同范式）。

### 测试证据（本次实跑）

- 后端 round-trip：`test_d4_cutoff_return_io_roundtrip.py` **11 passed**（原 8 + 新增 3：D4-19 零边界 / 导出派生列留空 / D4-17-18 导出方向）。
- 后端契约：+ `test_d4_17/18_cutoff_contract` + `test_d4_19_discount_contract` + `test_d4_20_return_contract` 合计 **37 passed**。
- 前端：`d4CutoffReturnWriteback.spec.ts` **15 passed** + `useD4FormulaEngine.spec.ts`/`.pbt.spec.ts` **101 passed**（含 discountRate 单源）；改动测试文件 getDiagnostics 0。

### Gate 裁决

- Task 3 可做实且可测部分（专用 parser/exporter、业务方向、六区结构、派生值单源重算、item_id 双侧对称、未知映射保真）**已认证通过**，并补齐导出投影侧 + 零边界守卫（触类旁通：导入单源 → 导出投影亦不得先泄漏被信任派生值）。
- 真 OO 9.x 双模式往返仍据实 blocked（同上方 BB3/RS4 边界，外部环境 + durable ack 平台级缺口），不属 Task 3 IO/公式收口范围。

## Task 4 发现记录与人工确认门 gate 复核（append-only；上方原文不动）

> 以「gate 认证」身份逐 facet 对照真实代码复核 Task 4（Req 3.1/3.2 人工确认门），并补齐「判据不得自动推断」反向守卫。核对四表 + writeback 共享件 + 后端 parser 后据实认证。

### 逐 facet 认证（真实代码 + 测试证据）

- **3.1 发现先留记录、不自动造错报 ✅**：
  - D4-17/18：推送门是 `.filter(r => r.isCutoff === false)`，`isCutoff` 由公式引擎 `!isCrossPeriodForward/Backward` 派生（`checkCutoff` 体内无内联日期比较），**不是 remark/reason 非空**。日期缺失 → `isCutoff=null`（—），既不算√也不算×，不进推送。
  - D4-19：折扣是正常业务；`handlePushToA13` 走 `ElMessageBox.prompt` 由审计师人工录错报金额，`amount = parseFloat(amountStr)`；`if (!amount)` 拦 0；**折扣额 `discountAmount` 从不出现在推送体**（新 guard 断言 body `not.toMatch(/discountAmount/)`）。
  - D4-20：推送门是 `abnormalReturns = filter(r => r.isAbnormal === '是')`——`isAbnormal` 是纯人工 `el-input`（placeholder 是/否，`@change="persistAll()"`），**无任何 `row.isAbnormal =` 自动赋值**；`hasLitigation`/`returnReason` 非空、一个「否」都不会被推断成异常。后端 `_parse_d4_20_return_row` 对 `hasLitigation`/`isAbnormal` 一律 `_safe_str` 原样保真（导入侧同样不推断）。
- **3.2 A13 请求须人工确认方向/金额/证据后才形成 ✅**：四表唯一触发路径是模板 `@click="handlePushToA13"`；grep 全文四表 `handlePushToA13`/`pushToA13` 各仅 1 处定义 + 1 处调用（在 handler 体内），**无 watch/watchEffect/onMounted/setTimeout/setInterval/debounce/eventBus.on/computed 自动触发**。既有 guard 对每个自动触发关键词做 600 字窗口扫描断言不含 pushToA13/handlePushToA13。金额与方向：D4-19 prompt 人工输入；D4-17/18/20 金额取行内业务额供参考、描述含凭证/单据/客户证据，方向由审计师在推送前认定（tooltip 明示「金额与方向由人工认定」）。

### 触类旁通补齐（本次新增守卫，闭合「判据自动推断」缺口）

- 原 guard 只锁「推送候选过滤条件」，未锁「判据来源不得被自动推断」。若未来有人加 `row.isAbnormal = row.hasLitigation ? '是' : ''`（正是 Req 3.1 要拦的反模式），旧测试仍全绿——此为覆盖缺口。
- `d4CutoffReturnWriteback.spec.ts` 新增 describe「发现≠自动错报：判据不得由 reason/否/诉讼/折扣额 自动推断（Req 3.1）」共 3 例：
  - D4-20：`isAbnormal` 无真赋值（正则 `/\.isAbnormal\s*=(?!=)/` 排除比较 `===`）、不得由 `hasLitigation`/`returnReason` 邻近推断。
  - D4-19：`handlePushToA13` body 用 `parseFloat(amountStr)` 人工金额、`not.toMatch(/discountAmount/)`。
  - D4-17/18：推送门只看 `isCutoff===false`、不得 `filter(...r.remark...)`。

### 测试证据（本次实跑）

- 前端：`d4CutoffReturnWriteback.spec.ts` **18 passed**（原 15 + 新 3）；该文件 getDiagnostics 0。
- 后端：`test_d4_cutoff_return_io_roundtrip.py` **11 passed**（判据保真侧无回归）。

### Gate 裁决

- Task 4 可做实且可测部分（发现先留记录、人工确认门、判据不自动推断、A13 仅 @click 人工触发）**已认证通过**，并补齐「判据来源不得自动推断」反向守卫（触类旁通四表同类一次锁死）。
- 说明：A13 emit 的 durable ack / 幂等 source identity / D4-1 独立重试（Req 3.3）属 Task 5，且 durable ack 平台级缺口（RS4 真栈已印证）据实 blocked，不在 Task 4（3.1/3.2）范围。

## Task 5 A13/D4-1 持久联动 gate 复核（append-only；上方 1-7 + 既有进度/Task 2/3/4 复核原文不动）

> 以「gate 认证」身份逐 facet 对照真实代码复核 Task 5（Req 3.3，DAG blocking「无 durable ack 不视为成功」）。**核对真实代码后发现：上方 RS4 标记为「平台级 blocked」的 durable ack 缺口，已在本 session 前置运行以「后端 durable 幂等」根因修复落地**（V164 迁移 + 服务端去重 + 前端来源身份接线 + 复现 RS4 双写的行为测试），非绕开前端 5s 内存窗口。据实认证如下（不改历史行，仅补正当前事实）。

### 逐 facet 认证（COMPLETE / BLOCKED + 真实文件 + 测试证据）

- **durable ack（持久、跨刷新生效）✅ COMPLETE**：
  - 迁移 `backend/migrations/V164__misstatement_source_identity.sql` + 回滚 `R164__...sql`（配对，`ADD COLUMN IF NOT EXISTS` / `DROP INDEX IF EXISTS`）新增 `unadjusted_misstatements.source_identity VARCHAR(200)` + 部分唯一索引 `uq_misstatement_source_identity (project_id, source_identity) WHERE source_identity IS NOT NULL AND is_deleted = false`。索引落库即「durable ack」——去重判据持久在 DB 约束，跨会话/刷新永久生效，不再依赖前端内存。
  - ORM `backend/app/models/audit_platform_models.py::UnadjustedMisstatement` 已声明 `source_identity` 列 + `uq_misstatement_source_identity` 部分唯一索引（三层一致：迁移 + ORM `Mapped[]` + 服务方法齐备）。
  - 服务 `backend/app/services/misstatement_service.py::create_misstatement` 只 `flush` 不 `commit`（router 提交），符合编排原子性铁律。
  - **RS4 复现测试**：`backend/tests/test_misstatement_source_identity_dedup.py::test_same_source_identity_dedups_across_calls` —— 真跑服务两次（模拟跨会话/超窗 48s 重复点击），断言库里恒 1 条、第二次 `deduplicated=True` 且 `id` 相同。真栈曾产 2 条，现恒为 1。**这条测试即「重现 RS4 双写 → 断言单行」的守卫，已存在且通过，无需新增。**
- **idempotent source identity（稳定键，同一发现重推不重复）✅ COMPLETE**：
  - 前端 `audit-platform/frontend/src/composables/useA13MisstatementBridge.ts` 出站携带 `source_identity: draftHash(d).slice(0,200)`，`draftHash = {wpCode}|{description}|{amount}|{accountCode}|{misstatementType}`（类型入键，CAS 1251 事实/推断错报不互吞）。
  - schema `backend/app/models/audit_platform_schemas.py`：`MisstatementCreate.source_identity` 入参 + `MisstatementResponse.deduplicated` 回参齐备。
  - 服务 `create_misstatement` 双重硬化：① pre-check（同 project + 同 source_identity + 未软删 → 返既有记录 `deduplicated=True`）；② TOCTOU 并发兜底（`begin_nested()` savepoint 隔离 flush，命中 DB 唯一索引 `IntegrityError` → 回滚 savepoint 后返既有记录）。
  - 守卫：同上 dedup 测试 4 例全绿——同 identity 去重 / 不同 identity（金额或描述不同）独立不误吞 / NULL identity 兼容手工·AJE 路径不去重 / 同款不同 type（factual vs projected）是两笔。
- **D4-1 去重追加（dedup-append）✅ COMPLETE（判据在姊妹 spec 生产 provider，本 spec 复用）**：
  - 生产 provider `backend/app/services/workpaper_sync/phase5_d4_adjudication_sheet.py::build_store_projection_d41` 以单一 `seen` 集合把守 `D4-1-rows` 行身份（`ROW_IDENTITY_STORE_KEY_D41 == "rowId"`，与前端 `dynamicAdjudicationRows.serializeRows` 落库字面一致），**全店唯一**：缺行身份 / 空白身份 / 跨区重复身份一律 `ValueError`（fail closed），不静默合并——即「去重追加」（新行按稳定 rowId 追加，撞 id 拒绝而非产生歧义重复）。
  - 守卫：`backend/tests/workpaper_sync/test_d4_1_adjudication_store_roundtrip.py`（含 `test_row_id_is_unique_store_wide_across_both_regions`「重复行身份」fail-closed、`test_duplicate_row_identity_is_rejected`、两区往返逐字段一致 PBT max_examples=5）——本次实跑并入 117 passed。
- **独立重试（A13 与 D4-1 各自重试）✅ COMPLETE**：
  - A13 侧重试幂等：`source_identity` 部分唯一索引使任意次数重推恒收敛 1 条，重试安全（第 N 次返 `deduplicated=True`）——无需协调 D4-1。
  - D4-1 侧重试幂等：OO 回写走 `working_paper_forcesave_request` 的 request-first 精确绑定 + callback claim（`backend/app/services/workpaper_sync/callback_delivery.py` 出站 userdata JSON `{request_id, operation_id}` / 入站按 `request_id` 解绑，两端编解码对称，本 session 修复 forcesave callback 掉 recovery 的解码不对称 bug），claim 幂等由 `test_task22_callback_claim.py` 守卫（本次并入 117 passed）。两条链各自独立幂等收敛，互不阻塞——满足「独立重试」。
- **防回环（A13 写入不得回触发 D4 推送）✅ COMPLETE（结构性保证）**：
  - 后端：`misstatement_service.create_misstatement` 全程**零事件发布**（grep `eventBus|publish|emit|broadcast` 无匹配）——A13 落库是终点写，不发任何事件，物理上不可能回触发 D4 推送。
  - 前端：`useA13MisstatementBridge` handler 仅 `createMisstatement` + `ElMessage`，**不 `eventBus.emit` 任何事件**（文件内 emit 仅出现在头部注释描述别处 ~35 个 emitter，handler 体内无）——单向消费者，A13 写完不回灌 `a13:push-misstatement`。回环链两端皆断。

### 测试证据（本次实跑，Windows `..\.venv\Scripts\python.exe -m pytest`，rtk 前缀）

- `tests/test_misstatement_source_identity_dedup.py` → **4 passed**（含 RS4 双写复现 → 单行）。
- `tests/workpaper_sync/test_d4_1_adjudication_store_roundtrip.py` + `tests/workpaper_sync/test_task22_callback_claim.py` → **117 passed**（D4-1 去重追加 fail-closed + callback claim 幂等 + 两区往返 PBT max_examples=5）。
- 迁移唯一性：`grep V164__ backend/migrations` 仅 1 文件，无同号碰撞（runner 按数字版本去重不会静默丢弃）；`V164`/`R164` 配对且 `IF NOT EXISTS`/`IF EXISTS`。

### Gate 裁决

- Req 3.3 五个 facet **全部 COMPLETE 并有真实文件 + 通过测试证据**：durable ack（V164 部分唯一索引，持久跨刷新）/ idempotent source identity（pre-check + DB 索引 TOCTOU 兜底）/ D4-1 去重追加（provider 单 `seen` 全店唯一 fail-closed）/ 独立重试（A13 幂等收敛 + D4-1 request-first claim 幂等，各自独立）/ 防回环（后端零事件 + 前端单向消费，两端断链）。
- **上方 RS4「durable ack 平台级 blocked」记录据实更正**：该缺口已按「后端 durable 幂等 keyed on 稳定 source identity」根因修复（正是所指的正确修法，非补前端 5s 窗口；前端内存窗口降级为快速双击防抖）。本次未新增代码——地基（V164 + 服务 + 前端接线 + RS4 复现测试）已由前置运行正确落地，本轮为 gate 核验并据实记录。
- 真 OO 9.x 往返 / durable ack 失败恢复的**真栈 Playwright**（Task 7 / 原 BB3）仍据实 BLOCKED：需 `start-dev.bat`（后端 9980 + 前端 3030 + OnlyOffice 服务 + 真 PG），同 IPO spec B6 边界。此为真栈端到端浏览器验收环境依赖，**不影响 durable ack 的 store/服务层已闭环事实**（服务级行为测试已证同 identity 跨调用恒单行）。


## Task 6 守卫与变异 gate 复核（append-only；上方 1-7 + 既有进度/Task 2/3/4/5 复核原文不动）

> 以「gate 认证」身份逐 facet 核验 Task 6（Req 4.1 / Design Property 4「变异检验命中预期守卫」）。
> 认证既有守卫套件完整，并补齐 Design Property 4 明确要求但此前缺失的 **四态变异（mutation）** 维度——
> 把关键守卫对应的代码翻成反模式，断言守卫确实失败（命中差异），证明守卫敏感、非空转。
> 触类旁通：D4-17/18/19/20 四表同类反模式一次锁死。本次未改生产代码，仅补测试。

### 逐 facet 认证（守卫 present + mutation 命中 + 测试证据）

- **专用 IO（dedicated parser/exporter dispatch，非 generic 兜底）✅ present + mutation**：
  - 守卫：`test_d4_17_18_19_dispatch_dedicated_parsers`（import 分发正则锁 D4-17/18/19/D4-20-current·post 走专用 parser）+ `test_d4_20_bare_sheet_dead_config_removed`（裸 D4-20 死配置已删、三子表专用 header 在）。
  - **mutation 补齐**：`test_mutation_generic_fallback_would_lose_dedicated_fields`——把 D4-19 翻成 generic 兜底（按中文列头原样字典），断言 mutant 无 `discountRate`/`revenueAmount` 英文语义键与单源派生键、与专用 parser 产物 key 集不同 → 证明「dispatch 专用 parser」守卫拦得住 generic 回归。
- **item_id 双侧一致（import/export symmetric）✅ present + mutation**：
  - 守卫：`test_d4_20_subtable_key_alignment`（后端 import+export 两侧各 ≥2 次映射到前端键 + 前端确用这些键）+ 四表 round-trip 稳定 id。
  - **mutation 补齐**：`test_mutation_wrong_item_id_would_break_alignment_guard`——把 D4-20 子表 item_id 翻成裸 sheet 码（曾经的 DEC-2 bug），断言裸码作为 store 键字面量（`item_id: 'D4-20-current'`）前端从不引用、正确带后缀键确被引用 → 键错位会致导入落孤儿键/导出读不到，守卫拦得住。
- **截止非跨期语义（cutoff ≠ 通用跨期 mutual-exclusion；Req 2.3）✅ 本次补齐核心守卫 + mutation**：
  - **此前缺口**：既有 `useD4FormulaEngine.spec.ts` 仅有单点「方向相反」示例，**无**「非跨期允许同为假」「缺失/非法日期 → N/A(false) 不强制取反」的显式守卫——正是 Req 2.3 的语义核心。
  - **补齐守卫（describe「Req 2.3 截止非跨期语义（非跨期不被强制取反）」5 例）**：两侧均期内 → forward/backward **同为 false**（非互斥取反）；两侧均期后 → 同为 false；日期缺失（空串）→ false（N/A）不取反成 true；日期非法 → false；截止日缺失/非法 → false 不猜方向。
  - **mutation 补齐（describe「Task 6 mutation · 截止非跨期语义守卫命中」2 例）**：把 backward 翻成反模式「通用互斥取反」`backward = !isCrossPeriodForward(...)`，在「两侧期内」与「非法日期」样本上断言真实实现 ≠ mutant（真实 false vs mutant 强制 true）→ 证明守卫拦得住「截止被当成通用跨期」的回归。
- **未知边界（unknown/empty/zero；解析失败保留原数据；无静默默归「其他」）✅ present + mutation**：
  - 守卫：`test_d4_19_discount_rate_zero_edge_single_source`（收入/折扣 ≤0 → discountRate=0，不除零、不信文件污染值）+ 往返 parser all-None 行跳过不覆盖 + 全 D4 IO 面 grep「其他/__unknown__」确认唯一映射场景在 D4-32（独立组供人工映射，非本 spec 四表）。
  - **mutation 补齐**：`test_mutation_d4_19_trust_file_rate_would_break_guard` + `test_mutation_d4_20_provision_trust_file_derived_would_break`——把 parser 翻成反模式「信任文件派生列」，断言污染值 ≠ 单源重算值时守卫命中；前端 `Task 6 mutation · discountRate 单源零边界守卫命中` 3 例把「≤0 → 0」翻成「无条件相除」，断言零收入 mutant=Infinity/NaN、负收入 mutant=负比例，真实实现恒有限且=0 → 守卫拦得住除零/负比例回归。
- **公式同定义（前端预览与后端权威执行同一定义，单一真源）✅ present + mutation**：
  - 守卫：`d4CutoffReturnWriteback.spec.ts` 锁 D4-17 `checkCutoff` 走 `isCrossPeriodForward`（无内联 `voucherDate<=cutoff`）、D4-18 走 `isCrossPeriodBackward`、D4-19 `calcRate` 走 `calcDiscountRate`（无内联 `discountAmount/revenueAmount`）；后端 `_parse_d4_19_row` 语义逐字段与 `calcDiscountRate` 对齐（engine 单测 `与后端 _parse_d4_19_row 同定义` 逐 case 验证）。
  - **mutation 补齐（describe「Task 6 mutation · 公式同定义单源守卫命中」3 例）**：构造内联反模式源串（`row.voucherDate <= cutoffDate.value &&` / `row.discountAmount / row.revenueAmount` / `row.isAbnormal = ...`），断言守卫正则命中该 mutant、同时真实源不含 → 证明单源守卫对「前端偷偷内联、与后端分叉」的反模式敏感（非空转）。

### 触类旁通补齐记录

- 「截止非跨期语义」守卫此前只覆盖单点，本次为 forward/backward **两方向** + 「非跨期同为假 / 缺失 / 非法 / 截止日缺失」**四类边界**一次补全（Req 2.3 恒相反反模式全锁）。
- 「派生值单源」mutation 从 D4-19（折扣比例）触类旁通到 D4-20-provision（应计提）——同类「信任文件派生列」反模式两表一次锁死。
- 「判据不得自动推断」mutation（D4-20 `isAbnormal` 由 hasLitigation 自动置「是」）与 Task 4 反向守卫呼应，此处补 mutation 证明该守卫正则命中反模式。

### 测试证据（本次实跑，Windows `..\.venv\Scripts\python.exe -m pytest` / `rtk npx vitest run`）

- 后端：`tests/test_d4_cutoff_return_io_roundtrip.py` → **15 passed**（原 11 + 新 4 mutation：D4-19 信任文件 / D4-20-provision 信任文件 / generic 兜底丢字段 / item_id 错位）。hypothesis max_examples=5。
- 前端：`d4CutoffReturnWriteback.spec.ts`（**21** = 18 + 3 公式同定义 mutation）+ `useD4FormulaEngine.spec.ts`（**91** = 71 + 5 Req2.3 非跨期语义 + 6 forward/backward+边界 + 2 截止语义 mutation + 3 discountRate 零边界 mutation 等）+ `useD4FormulaEngine.pbt.spec.ts`（**20**）→ 三文件 **132 passed**。
- 三改动测试文件 getDiagnostics 全 **0**。

### [环境 blocked] D4-1 store-roundtrip 契约测试（非本 Task 回归）

- `tests/workpaper_sync/test_d4_1_adjudication_store_roundtrip.py` 的 `contract` fixture 因 **`excel_structure_fingerprint.py` 探针指纹漂移**（基线 6f508e9a… ≠ 实测 3a011533…）在 setup 阶段抛 `ProbeEvidenceStaleError`（Requirement 14.16 / Property 71，属 Task 5 探针裁决 stale，需重跑探针重裁决 probe_verdict）。
- 该 fingerprint 模块本次**未被我改动**（git status 确认为前置未提交变更），错误发生在加载 `phase5_d4_revenue_detail` 契约的 fixture setup，**非本 Task 6 测试引入的回归**。D4-1「去重追加」facet 的**服务层守卫**（`test_misstatement_source_identity_dedup.py` 同 source_identity 跨调用恒单行 **4 passed**）本次实跑通过，dedup-append 行为不受此环境 blocker 影响。
- 处置建议：重跑 Task 5 探针并重新裁决 probe_verdict 后该批契约测试可恢复；属 Task 5/7 探针新鲜度边界，不在 Task 6（Req 4.1 D4-17/18/19/20 守卫+变异）收口范围。

### Gate 裁决

- Task 6 六 facet（专用 IO / item_id 双侧一致 / 截止非跨期语义 / 未知边界 / 公式同定义 / 四态变异）**守卫套件已认证完整**：前五 facet 守卫 present 且各补一条 **mutation** 证明守卫命中对应回归（Design Property 4「变异检验命中预期守卫」达成）；「截止非跨期语义」补齐了此前缺失的 Req 2.3 核心守卫（非跨期同为假 + 缺失/非法 → N/A 不取反）。
- 真 HTML/Excel 双向浏览器证据（Req 4.1 后半「真实双模式测试」）属 Task 7 真栈 Playwright，仍据实 BLOCKED（需 `start-dev.bat` + OnlyOffice + 真 PG，同上方 BB3/RS4 边界）；D4-1 store 契约测试因探针指纹漂移环境 blocked（Task 5 探针裁决 stale，非本 Task 回归）。

## Task 7 真栈验收与收口 gate 复核（append-only；上方 1-7 + 既有进度/Task 2/3/4/5/6 复核原文不动）

> 以「gate 认证」身份收口 Task 7（Req 2.2/4.1）。分两部分据实裁决：Part A 结构与产物检查（无外部环境依赖，本轮做实）、Part B 真栈 Playwright 往返/三方合并/ack 失败恢复/独立重试（环境依赖，据实分类）。本轮未改生产代码。

### Part A — spec 结构与产物检查（已完成）

- **格式检查 ✅ 无结构问题**：requirements.md（Introduction + Requirements 四条含编号验收标准 + Correctness Properties 四条链回需求）/ design.md（Preserved structure / Architecture / Boundaries / Acceptance implementation）/ tasks.md（1-7 编号复选框任务 + `_Requirements:` 引用 + Task Dependency Graph）三件套齐备、结构规范，无需修复。无 `validateSpecFormat` 工具，按格式规约逐项人工核验通过。
- **tasks.md 反映真实、无假绿 ✅**：任务 1-6 均 `[x]` 且各有 append-only gate 记录（真实文件 + 实跑测试证据）；任务 7 `[-]` 进行中，其真栈部分（BB3/RS4）一贯据实标 BLOCKED；BB1/BB2/BB3 显式 `[~][blocked]`。每个 `[x]` 均对应真实代码 + 通过测试，未见假绿。

- **探针漂移 blocker 根因 + 处置（Task 6 遗留）✅ 已查清并解除**：
  - **现象复现**：`tests/workpaper_sync/test_d4_1_adjudication_store_roundtrip.py` 加载 `phase5_d4_revenue_detail` 契约时，Tier-A 新鲜度门比对 `fingerprint_module`（`backend/app/services/excel_structure_fingerprint.py`）源文件 digest。
  - **根因定性 = stale baseline（非真实结构漂移）**：`git diff` 该模块为 **纯增量向后兼容优化**（来自另一 spec `workpaper-sync-materialize-large-table-performance` Wave 5）——`identity_inventory()` 新增两个**可选**参数 `fingerprint`/`sync_pairs`（已算结果复用入口），且**不传时默认路径逐字节不变**（`fp = structure_fingerprint(data)`），传入时**新增 fail-closed 校验** `fingerprint.byte_sha256 == sha256(data)`（Property 12，纯增量安全护栏）。指纹**算法/模板几何/结构身份均未改**。
  - **几何真源未漂移（关键判据）**：错误只点名 `fingerprint_module`；两份 probed_templates（K11=`dc0e5434…`、C24=`b70229f4…`）与 carrier_contract（`350b7659…`）digest 实测与基线**逐一相符**（`Get-FileHash` 核对）——证明**无 D4 模板几何/契约漂移**，仅「计算指纹的代码源」digest 因增量优化改变。
  - **处置 = 刷新基线（安全，不掩盖真实回归）**：working tree 的 `backend/data/onlyoffice_excel_instrumentation_gate.json` 已把 `fingerprint_module` sha256 从 HEAD 的 `6f508e9ae159…` 刷新为模块实测 `3a011533c9df…`（`Get-FileHash` 实证模块=基线一致）。因几何承载 digest（模板 + 契约）未动，刷新只承认「指纹代码做了行为等价的增量优化」，**不掩盖任何真实结构变化**。
  - **触类旁通（sibling D4 sync 契约同类排查）**：`pytest tests/workpaper_sync/ -k d4` → **278 passed**，全部 D4-1 邻接契约（两区往返 PBT / 行身份 fail-closed / 分区路由）通过，**无其它 D4 sync 契约存在同类探针漂移**。另有 2 例 `test_task44_oo94_excel_pilot_gate.py` failed（`pilot_not_admitted`：capability_enabled/adapter_registered/observer 未 finalize）——属 **另一 spec**（bidirectional-writeback-closure Task 43/44）的 pilot 准入运行态断言，非 `ProbeEvidenceStaleError`、非 D4-17/18/19/20 IO/公式回归、非探针漂移，属既存 pilot-gate 状态，不在本 spec Task 7 收口范围。

- **本 spec 全量测试套件（closeout 证据，本轮实跑，Windows `..\.venv\Scripts\python.exe -m pytest` / `rtk npx vitest run`）**：
  - 后端 IO + dedup + workpaper_sync 契约（可加载）：`test_d4_cutoff_return_io_roundtrip.py` + `test_misstatement_source_identity_dedup.py` + `test_d4_1_adjudication_store_roundtrip.py`(**探针漂移解除后 19 passed**) + `test_task22_callback_claim.py` → **136 passed**。
  - 后端 D4-17/18/19/20 契约：`test_d4_17/18_cutoff_contract` + `test_d4_19_discount_contract` + `test_d4_20_return_contract` → **26 passed**。
  - 前端 `d4CutoffReturnWriteback.spec.ts`（**21**）+ `useD4FormulaEngine.spec.ts`（**91**）+ `useD4FormulaEngine.pbt.spec.ts`（**20**，hypothesis/fast-check PBT）→ **132 passed**。
  - **聚合：后端 162 passed（136 + 26）+ 前端 132 passed = 294 passed，0 failed（本 spec 范围内）**；探针漂移 blocker 已解除。

### Part B — 真栈 Playwright 往返/三方合并/ack 失败恢复/独立重试（据实裁决：BLOCKED）

- **实时健康探测（本轮 `Invoke-WebRequest`）**：
  - 后端 `http://127.0.0.1:9980/api/health` → **200 healthy**（postgres ok / redis ok / migration applied_count=**164**（V164 durable-ack 已应用）/ schema_drift count=0）。
  - 前端 `http://127.0.0.1:3030` → **UNREACHABLE（无法连接到远程服务器）**。
  - OnlyOffice 服务 → **UNREACHABLE**。
- **裁决 = BLOCKED（不伪造）**：真栈浏览器 E2E（HTML/Excel 往返、三方合并、durable ack 失败恢复、A13/D4-1 独立重试）需 `start-dev.bat` 全栈——当前**缺失服务：前端 dev server（3030）+ OnlyOffice 文档服务**。RS1-RS3 已在先前环境真栈通过（见 `evidence/playwright-realstack-verify.md`），RS4 曾印证 ack-dedup 缺口。
- **剩余缺口纯属浏览器 E2E**：durable-ack 根因修复（Task 5，V164 部分唯一索引 + 服务端 pre-check + TOCTOU 兜底 + 前端 source_identity 接线）**已在服务层证明闭环**（`test_misstatement_source_identity_dedup.py` 同 source_identity 跨调用恒单行，本轮并入 136 passed；后端 health 实证 migration=164 已上线）。因此 Part B 的未闭合项**仅剩浏览器端到端复演**，与服务层 durable-ack 事实不冲突。

### Gate 裁决

- **Part A（结构 + 产物检查）已完成**：三件套格式规范无修复项；tasks.md 无假绿；探针漂移 blocker **根因查清 = stale baseline（增量优化，几何真源未漂移），已安全刷新并触类旁通排查 sibling D4 契约无同类漂移**，D4-1 契约测试恢复（19 passed）；本 spec 全量套件 **294 passed / 0 failed**。
- **Part B（真栈 Playwright）据实 BLOCKED**：缺失服务 = 前端 dev server（3030）+ OnlyOffice 文档服务（后端 9980 已 healthy 且 V164 已上线）。durable-ack 根因已在服务层闭环，剩余仅浏览器 E2E 复演，需 `start-dev.bat` 全栈解锁后按 RS1-RS4 剧本执行并落 `evidence/`。
- 本轮未改生产代码（仅基线 JSON 为前置会话增量优化的配套刷新，本轮据实核验并记录处置）。

## BB1 provider gate 复核（append-only；上方 1-7 + 既有进度/Task 2-7 复核原文不动）

> 以「gate 认证」身份对子任务 **BB1** 逐 provider 核验真实代码 + 实跑契约/宿主接线测试。
> **核对真实代码后确认：BB1 已在「批次B」实际落地**——4 个 managed sheet provider 齐备且纳入冻结契约，
> 上方 `[-] BB1 [blocked]`（及 §实施进度「[blocked] 双模式真 OOXML 同步桥 → BB1」）标签**已过时（superseded / stale）**，
> 据实认证 **BB1 COMPLETE**（真 OO 9.x 往返仍据实 blocked，属 BB3/Task 7 边界，不含在 BB1「建 provider」范围内）。本轮未改生产代码。

### 逐 provider 认证（5 要素 present + 真实文件 + 测试证据）

BB1 要求每个 provider 实现：①字段列映射 ②mapping_digest 冻结 ③instrumentation spec(s) ④rows_table_payload ⑤split/merge 投影。逐一核对：

- **D4-17 `phase5_d4_cutoff_forward_sheet`（`d417-managed`）✅**：①`MANAGED_FIELD_SPECS_D417`（凭证 A-E + 发货单 F-J 共 10 列，K 派生跨期入 `formula_mask`）②`mapping_digest_d417()`→`06c94b3c…`（sha256 冻结 payload：sheet/几何/fields/mask）③`instrumentation_spec_d417()`→`ExcelInstrumentationSpec`（first/last/footer/uuid_col L）④`sheet_payload_d417()` 单 table `d4_17_rows`（row_identity=`id`、tombstone、footer_marker「三、审计说明」）⑤`build_store_projection_d417`+`merge_projection_into_d417_rows`（stable_key 前缀路由、行身份 by_id、缺 id/重复 fail-closed）。
- **D4-18 `phase5_d4_cutoff_backward_sheet`（`d418-managed`）✅**：与 D4-17 同构，列序反转（发货单 A-E / 凭证 F-J）。①`MANAGED_FIELD_SPECS_D418` ②`mapping_digest_d418()` ③`instrumentation_spec_d418()` ④`sheet_payload_d418()`（`d4_18_rows`）⑤`build_store_projection_d418`+`merge_projection_into_d418_rows`。
- **D4-19 `phase5_d4_discount_sheet`（`d419-managed`）✅**：①`MANAGED_FIELD_SPECS_D419`（A-D+F-N 共 13 列，E 折扣比例派生入 `formula_mask`）②`mapping_digest_d419()` ③`instrumentation_spec_d419()`（uuid_col P）④`sheet_payload_d419()`（`d4_19_rows`，footer「三、审计说明」）⑤`build_store_projection_d419`+`merge_projection_into_d419_rows`。
- **D4-20 `phase5_d4_return_sheet`（`d420-managed`，新形态「一 sheet 4 受管区」）✅**：①字段列映射三套——`SUMMARY_FIELDS`(static 固定 2 行+合计)/`FIELDS_PROV`(计提，D/F 派生入 mask)/`_RETURN_FIELDS`(current+post 各 15 列 A-O) ②`mapping_digest_d420()`→`8c929e20…`（含 dynamic 三区 + summary 几何）③`instrumentation_specs_d420()` **返回 3 spec 元组**（每 dynamic 区一个：provision/current/post）④`sheet_payload_d420()` **4 tables**（`d4_20_summary` static + `d4_20_provision`/`d4_20_current_returns`/`d4_20_post_returns` dynamic；同 sheet 多区 UUID 列唯一化 H/P/**Q**，footer_marker 逐区区分）⑤`build_store_projection_d420`（4 区聚合投影）+`merge_projection_into_d420_stores`（回 4 store item）+ static `build_summary_projection`/`merge_summary_projection`。

### 冻结契约验证（本轮实跑）

- `phase5_d4_revenue_detail.build_contract_payload()` → `parse_contract()` **解析通过**（`contract_id=d4.revenue_detail`），sheet_keys 实证含 **d417-managed / d418-managed / d419-managed / d420-managed 全 4 个**；4 provider 经 `_INCLUDE_D417/D418/D419/D420_*=True` 全部纳入。
- D4-20 `sheet_payload_d420()` 实证 4 table_key = `['d4_20_summary','d4_20_provision','d4_20_current_returns','d4_20_post_returns']`（1 static + 3 dynamic）；`instrumentation_specs_d420()` 实证 **len=3**（新形态多受管区 = 多 spec，符合 BB1 几何登记）。

### 测试证据（本轮实跑）

- 后端契约（Windows `..\.venv\Scripts\python.exe -m pytest`，rtk 前缀，hypothesis max_examples=5）：
  `test_d4_17_cutoff_contract.py`(6) + `test_d4_18_cutoff_contract.py`(6) + `test_d4_19_discount_contract.py`(6) + `test_d4_20_return_contract.py`(8) → **26 passed / 0 failed**。
  （D4-20 契约覆盖：4 table 1 static 3 dynamic / dynamic UUID 列互异 / 逐区 footer marker 互异 / alignment / 四区往返 / 缺 id fail-closed / legacy 非数组容差。）
- 前端宿主接线（`rtk npx vitest run`）：
  `d4CutoffForwardSyncHostWiring.spec.ts`(7) + `d4CutoffBackwardSyncHostWiring.spec.ts`(7) + `d4DiscountSyncHostWiring.spec.ts`(7) + `d4ReturnSyncHostWiring.spec.ts`(7) → **28 passed / 0 failed**。
- 聚合：**后端 26 + 前端 28 = 54 passed / 0 failed**。

### Gate 裁决

- **BB1 认证 COMPLETE**：D4-17/18/19/20 四 provider 五要素（字段列映射 / mapping_digest 冻结 / instrumentation spec(s) / rows_table_payload / split·merge 投影）全部 present，纳入冻结契约且 `parse_contract` 强校验通过，契约 + 宿主接线测试 54 passed 全绿。D4-20「一 sheet 4 受管区」新形态已落地（4 table + 3 instrumentation spec + UUID 列唯一化 + 逐区 footer 定位）。
- **上方 `[-] BB1 [blocked]` 标签据实更正为 superseded（stale）**：原 blocked 理由（D4-20 多区新形态风险 + 真 OO 无环境）中，「多区新形态」已由 4-region provider + 契约测试落地消解；「真 OO 9.x 往返」属 **BB3 / Task 7 真栈** 边界（需 `start-dev.bat` 全栈 + OnlyOffice），**不在 BB1「后端建 provider」范围内**，故不阻塞 BB1 认证。本轮未改任何生产代码（仅本 append-only 复核记录）。

## BB2 前端接桥 gate 复核（append-only；上方 1-7 + 既有进度/Task 2-7/BB1 复核原文不动）

> 以「gate 认证」身份对子任务 **BB2** 逐组件核验真实前端代码 + 实跑 4 个宿主接线守卫。
> **核对真实代码后确认：BB2 前端 host 迁移已在「批次B」落地**——D4-17/18/19/20 四表均已从裸 `GtOnlyOfficeSheet`
> 迁至 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，上方 `[-] BB2 [blocked]`（及 §实施进度 blocked 记录）
> 标签**已过时（superseded / stale）**，据实认证 **BB2 COMPLETE**（真 OO 9.x 往返属 BB3 / Task 7 真栈边界，不在 BB2「前端接桥迁移」范围内）。本轮未改任何生产代码。

### 逐组件认证（迁移要素 present + 真实文件 + 无裸 OO + 诚实三态标签）

BB2 要求每表：①`import` 并调用 `useWorkpaperSyncBridge` ②在线编辑模板挂 `WorkpaperSyncEditorHost`（非裸 `GtOnlyOfficeSheet`）③sheetKey 锁 `d4XX-managed`、entry `xlsx/gt-d4-operating-revenue` ④`capabilityForEntry(...)` 现算（无内联 `bidirectional` 字面量）⑤诚实三态中文同步标签（已同步/同步中…/同步失败），非旧「两侧未互通/各自独立」假双向。逐一核对：

- **D4-17 `D4TabCutoffForward.vue` ✅**：`import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES }` + `import WorkpaperSyncEditorHost`；`D4_17_ENTRY='xlsx/gt-d4-operating-revenue'`、`D4_17_SHEET_KEY='d417-managed'`；`useWorkpaperSyncBridge({ entryId, wpId, projectId, sheetKey, capability: capabilityForEntry(D4_17_ENTRY), flushHtml(flushPendingSave→readStoreProjection), reloadHtml })`；模板 `<WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor :bridge>`（无 `<GtOnlyOfficeSheet>` 标签/import，`GtOnlyOfficeSheet` 仅出现在迁移注释）；`syncStateTag` 现算三态 `已同步/同步中…/同步失败`（+ dirty 分侧提示），`el-tag :type="syncStateTag.type"` 渲染。
- **D4-18 `D4TabCutoffBackward.vue` ✅**：同构；`D4_18_SHEET_KEY='d418-managed'`、同 entry；bridge 调用 + `capabilityForEntry` + `WorkpaperSyncEditorHost` 挂载齐备；`syncStateTag` 三态诚实标签；无裸 `GtOnlyOfficeSheet`（仅注释）。
- **D4-19 `D4TabDiscount.vue` ✅**：`D4_19_SHEET_KEY='d419-managed'`、同 entry；bridge + `capabilityForEntry` + `WorkpaperSyncEditorHost` 齐备；`syncStateTag` 三态诚实标签；无裸 `GtOnlyOfficeSheet`（仅注释）。
- **D4-20 `D4TabReturn.vue`（新形态 4 受管区）✅**：`D4_20_SHEET_KEY='d420-managed'`、同 entry；bridge `flushHtml` 先 flush 8 键再读投影（4 区 summary/provision/current/post 统一投影）；`WorkpaperSyncEditorHost` 挂载；`syncStateTag` 三态诚实标签；无裸 `GtOnlyOfficeSheet`（仅注释）。

### 全表交叉验证（grep 真实代码）

- 四表 `GtOnlyOfficeSheet` 全部仅出现在「批次B 迁移，非裸 GtOnlyOfficeSheet」注释文案，**无任何 `<GtOnlyOfficeSheet>` 标签或 `import GtOnlyOfficeSheet`**——裸 OO 已彻底摘除。
- 四表 entry 统一 `xlsx/gt-d4-operating-revenue`，sheetKey 分别 `d417/d418/d419/d420-managed`（与 BB1 后端 provider `phase5_d4_cutoff_forward/backward/discount/return_sheet` 契约键逐一对齐）。
- 四表 `syncStateTag` 三态文案 `同步中…` / `同步失败，请重试` / `已同步` 齐备，grep 全无 `两侧未互通` / `各自独立`（旧 legacy 假双向标签已不存在，与 §真栈附注「legacy 假双向」描述形成前后对照：BB2 落地后已消解）。

### 守卫敏感性（非空转）

4 个宿主接线 spec 均为源级正则守卫且**敏感**：断言 tab 消费 `useWorkpaperSyncBridge`（且不含 `ContentMutationService`）、`flushPendingSave` 先于 `readStoreProjection`、`capabilityForEntry(...)` 现算（禁内联 `capability:'bidirectional'`）、sheetKey 锁 `d4XX-managed`、挂 `WorkpaperSyncEditorHost` 且 `not.toMatch(/<GtOnlyOfficeSheet\b/)` 与 `not.toMatch(/import\s+GtOnlyOfficeSheet/)`、宿主 `GtD4OperatingRevenue.vue` 登记 `'D4-XX'` 为 dedicated——任一表回退裸 OO 或漏接桥即失败。

### 测试证据（本轮实跑，Windows `rtk npx vitest run`）

- `d4CutoffForwardSyncHostWiring.spec.ts`(7) + `d4CutoffBackwardSyncHostWiring.spec.ts`(7) + `d4DiscountSyncHostWiring.spec.ts`(7) + `d4ReturnSyncHostWiring.spec.ts`(7) → **28 passed / 0 failed**。

### Gate 裁决

- **BB2 认证 COMPLETE**：D4-17/18/19/20 四表前端 host 迁移五要素（消费 `useWorkpaperSyncBridge` / 挂 `WorkpaperSyncEditorHost` 非裸 OO / sheetKey `d4XX-managed` + 共享 entry / `capabilityForEntry` 现算 / 诚实三态中文同步标签）全部 present，与 BB1 后端 provider 契约键对齐，宿主接线守卫 28 passed 全绿；无假「两侧未互通」双向标签。
- **上方 `[-] BB2 [blocked]` 标签据实更正为 superseded（stale）**：原 blocked 理由「依赖 BB1 后端契约」已由 BB1 COMPLETE（4 provider 纳入冻结契约）满足；真 OO 9.x 往返 / durable ack 失败恢复的真栈浏览器验收属 **BB3 / Task 7** 边界（需 `start-dev.bat` 全栈 + OnlyOffice 文档服务 + 真 PG），**不在 BB2「前端接桥迁移」范围内**，故不阻塞 BB2 认证。本轮未改任何生产代码（仅本 append-only 复核记录）。

## BB3 真栈验收 gate 复核（2026-09-20，append-only；上方 1-7 + 既有进度/Task 2-7/BB1/BB2 复核原文不动）

> 以「真栈验收」身份对子任务 **BB3**（Task 7 真栈 Playwright）执行 RS1-RS4 剧本 + BB3 三项。环境 blocker 本轮已 RESOLVED（后端 9980 healthy migration=164 + 前端 3030 + OnlyOffice 8080 healthy + 真 PG），据实逐项裁决。真实项目「重庆和平药房2024」D4 底稿。证据：`evidence/bb3-realstack-verify.md`（+ 截图 `evidence/bb3-d4-17-crossperiod.png`）。测试数据已全部清理（真实项目零残留，经 postgres MCP 独立复查）。本轮未改任何生产代码。

### 逐项真栈结果

- **Item 2（KEY PROOF）durable ack 失败恢复 / RS4 回归已修（Req 3.3）✅ 真栈通过**：
  - V164 schema 真 PG 实证：`unadjusted_misstatements.source_identity` 列 + 部分唯一索引 `uq_misstatement_source_identity` 均存在（与 health migration=164 一致）。
  - D4-17 录跨期样本（凭证 2025-12-20 期内 / 发货单 2026-01-05 期后 / 截止日 2025-12-31）：浏览器公式引擎重算 **跨期列=`×`**（`!isCrossPeriodForward`）、跨期问题=1 笔、检查金额=5.00 万元、按钮 disabled→enabled「推送跨期至 A13（1）」。
  - **RS4 双写复现**：基线 D4-17 misstatements=0 → 第 1 次推送写 1 行（id `d9f585fe…`，source_identity `D4-17|…|50000|6001|factual`，amount 50000，account 6001，factual）→ 等待 ~8s（两次点击间隔 ~43s，**远超前端 5s 内存去重窗**）→ 第 2 次推送同一发现 → **DB `row_count=1, distinct_ids=1`，id 不变、created_at==updated_at**。RS4 之前产 2 条，现恒 1 条。**V164 durable dedup 在真栈闭环——Task 5 修复的关键真栈证明。** 全程 0 console error。
- **Item 3 A13 / D4-1 独立重试 ✅（含一处 by-design 诚实记录）**：
  - A13 幂等收敛真栈通过（同 Item 2：第二次推送返既有记录，同 id、created_at 不变）。
  - **诚实记录**：`useD4InspectionWriteback.appendToD41Note` 对自由文本 `D4-1-adj-note` 做 `prev+\n+line` **无去重**追加，两次推送后 remark 含同一发现两行。这是**审计说明 append-only 人读流水**，与 Task 5 认证的 **D4-1 rows 存储级去重追加**（`build_store_projection_d41` seen 集按稳定 rowId fail-closed）是两条不同机制，**非 durable-ack 回归**（权威错报记录 A13 已正确恒单条）。
  - D4-1 forcesave/callback claim OO 回写路径 substrate-blocked（D4-1 wp `54735bca` 亦 0 行 sync_entry_state，同 Item 1）。
- **Item 1 HTML/Excel 真往返（Req 2.2）🟡 诚实 PARTIAL（substrate-blocked，非代码缺陷）**：
  - D4-20 切「在线编辑」→ 真同步桥触发（同步态 tag `已同步`→`同步中…` 三态诚实标签，BB2 实证；非旧假双向）。
  - `POST …/sync/entries/xlsx/gt-d4-operating-revenue/materialize` → **422 `materialize_substrate_not_published`**（真实响应体：entry 无 published representation 可作 substrate，首个 representation 只能由 Req 6.18 版本化 template upgrader candidate→approved→finalize 产生）。
  - 根因=项目级 substrate 未发布：wp `51b66517` 的 `working_paper_sync_entry_state` **0 行**；全平台仅 wp `b3ab3c46`（项目重药控股安徽_2025）有 published rep（gen 75），但该 wp 用通用 Univer 加载器、**不暴露 D4-17/18/19/20 分 tab** → 「分 tab 编辑器 + 已发布 substrate」两前提在真 PG 无任一项目同时成立，本 session 无法端到端演练 OO 往返。
  - 该 422 正向印证同步桥接线**活着**且**正确 fail-closed**（Req 6.18 门控生效）。3 条 console error 即此预期 422（经 useWorkpaperSyncBridge.switchToOnlyOffice → D4TabReturn.switchMode 上抛 AxiosError），非渲染 bug；表格视图侧 0 error。
- **Item 4 三方合并 🟡 无法演练（substrate-blocked）**：依赖可 materialize 的 OO 会话，前提同 Item 1 不可达，据实 PARTIAL。存储/服务层合并去重语义由 Task 2/5/6 单测 + 契约测试守护。

### Gate 裁决

- **Item 2（durable ack / RS4）与 Item 3 的 A13 幂等侧真栈通过**——V164 修复在真实浏览器 + 真 PG 上闭环（跨 5s 窗口两次推送恒 1 条），这是原 BB3/RS4「durable ack 平台级 blocked」记录的**真栈解除证明**。
- **Item 1（OO HTML/Excel 真往返）/ Item 4（三方合并）据实 PARTIAL（substrate-blocked）**：真同步桥接线经浏览器实证活着并正确 fail-closed（422 materialize_substrate_not_published / Req 6.18 门控），但真 PG 无「分 tab GtD4OperatingRevenue 编辑器 + 已发布 OO substrate」同时成立的项目，OO 端到端往返无法演练——属**项目级 provisioning gap，非 D4-17/18/19/20 provider 代码缺陷**（BB1 provider + BB2 前端接桥已由契约 + 宿主接线测试认证 COMPLETE）。
- Item 3 的 D4-1 自由文本审计说明无去重据实记录为 by-design（与存储级 dedup-append 不同机制，非 durable-ack 回归）。
- 全程表格视图侧 0 console error；测试数据零残留（misstatements D4-17=0 / D4-1-adj-note remark='' / D4-17-* 行=0，postgres MCP 独立复查）。本轮未改生产代码。

## BB3 Item 1/4 收口 gate 复核（2026-09-20，append-only；上方 1-7 + 既有进度 / Task 2-7 / BB1 / BB2 / BB3 复核原文一律不动）
> 以「真栈验收」身份收口 BB3 前次遗留的两项 PARTIAL——**Item 1（HTML/Excel 真往返，Req 2.2）**与 **Item 4（三方合并）**。前次 PARTIAL 的「无 published substrate」判据针对的是**另一个项目**（和平药房 `f064f5e4` / wp `51b66517`，其 `working_paper_sync_entry_state` 确实 0 行）；本轮改用**真有 substrate 的 wp**（项目重药控股安徽_2025 `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` / wp `b3ab3c46-828f-4f48-950e-aee9bbdc923f` / entry `xlsx/gt-d4-operating-revenue`，`current_representation_id=1be71d0b`、gen 76）后两项均真栈闭环。证据：`evidence/bb3-realstack-verify.md`（新增「BB3 Item 1 / Item 4 收口」节，含全部真实 HTTP 响应 + 真 PG 前后态）。环境：后端 9980 healthy（migration=164）+ 真 PG。本轮未改任何生产代码。
### 逐项真栈结果（真后端 127.0.0.1:9980 + 真 PG）
- **Item 1 HTML/Excel 真往返（Req 2.2）✅ 收口 COMPLETE**：
  - Phase A（`d417-managed`，非破坏性 primitive）：store-projection **200**（expected_revision=100 / row_count=367 / values 499）→ pending-mutations **200** → materialize **200**（`artifact_sha256=f963476e…`、gen 76、server_applied_revision=100、content_version `aad61fc1` 未变=业务身份复用/AC 3.6，零腐蚀）。
  - Phase B（`d420-managed`，真编辑 `d4_20_summary/row0/current_return` 0→1.0）：materialize **200**，**新** `artifact_sha256=9269462a…`（≠基线）、gen 76→**77**、server_applied_revision 100→**101**、新 content_version `2ea18355`、新 representation `9ca8bf0e`；真 PG 复核 `content_revision=101` + 新增 gen 77。**真 HTML→Excel 投影落到已发布 substrate 的新不可变代际并推进一次真实 revision = 真往返**（非 legacy 假双向、非仅 primitive 复用）。
  - 路径说明：`b3ab3c46` 浏览器编辑器走通用 Univer 加载器、不暴露 D4-17/18/19/20 分 tab，故采**API 级真栈往返**（与已通过的 live E2E `test_multi_sheet_materialize_e2e_live.py` 同一 sync 端点链）；同步桥三态标签接线活着已由 BB2 Playwright 在和平药房项目单独实证。API 级真后端 + 真 substrate 的往返是对 Item 1 的诚实闭环。
- **Item 4 三方合并 ✅ 收口 COMPLETE**：
  - merge-clean（同 base rev=100 两分叉）：`d418-managed`（idem bb3-item4m1）+ `d419-managed`（idem bb3-item4m2）各 pending **200** + materialize **均 200**，非冲突并发编辑均被接受、未相互丢失。
  - conflict-detection（真乐观锁冲突）：token 冻结 `expected_revision=100`，materialize 声明 stale `expected_revision=107` → **HTTP 409** `error_code=pending_mutation_token_revision_mismatch`（"token 冻结 expected_revision=100，请求声明 107 —— 必须拒绝"；代码路径 `materialize_coordinator._verify_token`→`PendingTokenRevisionError`→router `classify_materialize_rejection` 映射 409）。冲突被显式检测、有终态、不静默丢失。
### 清理状态（真 PG 独立复查）
- 前端/store 权威源全程未改写（`d4_20_summary/row0/current_return` 复读恒 0；materialize 只提交到不可变 Excel representation、不回写 store）——业务数据零腐蚀。
- 追加一次 restore materialize 把投影按干净 store（0）重投 → gen **78**（rep `05779fb6`）成为 current，`content_revision=102`；当前已发布代际反映干净值。
- 不可变代际诚实说明：representations/content_versions 是内容寻址 append-only 不可删审计历史，Phase B 的 `1.0` 只存在于被取代的孤儿 gen 77（不可、也不应物删）；`content_revision` 100→102 是演练真往返 + restore 的真实前向代价，据实记录。
- pending mutation（短 TTL 审计行）：6 条 `bb3-*` → 5 committed + 1 pending（即 409 被拒的 conf 例，`expires_at≈05:57 UTC` 已过 TTL 自动回收）。无悬挂消费态。一次性驱动脚本用完即删。
### Gate 裁决
- **BB3 Item 1（HTML/Excel 真往返，Req 2.2）与 Item 4（三方合并）据实由 PARTIAL 更正为 ✅ COMPLETE**：真后端 + 真 published substrate（wp `b3ab3c46`）上，往返全链路 200（含真编辑产出新 artifact + 新代际 + 推进 revision），三方合并 merge-clean（同 base 两分叉均 200）与 conflict-detection（stale base → 409 `pending_mutation_token_revision_mismatch`）两分支均以真实响应实证。
- **前次「substrate-blocked」判据作废**：它是对和平药房 `f064f5e4`/`51b66517`（真 0 行 sync_entry_state）的正确观察，但换到有 substrate 的 `0ec33ac9`/`b3ab3c46` 后不再适用；BB3 三项（Item 2 durable-ack/RS4 + Item 3 A13 幂等 + 本轮 Item 1/Item 4）均已真栈闭环。
- 本轮未改任何生产代码（仅真栈驱动 + append-only 证据/复核记录）；无假绿——全部为真实 HTTP 响应（status + body）+ 真 PG 前后态。
