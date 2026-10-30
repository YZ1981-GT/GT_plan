# 设计文档：凭证身份、底稿回写与预审/年审阶段

需求编号见 requirements.md（需求 X.Y）；现状事实只在 requirements 的 F 表，这里只列设计期新发现（N 编号）。

## 0. 前提

- 迁移号写 `V{n}` / `R{n}`，实施第一步现扫 `backend/migrations/V*.sql` 取 MAX+1（写作时最高 V205）。
- `backend/app/services/voucher_identity.py` 与前端 `src/utils/voucherIdentity.ts` 由本 spec 阶段 A 建立；`ledger-incremental-append-true-merge`（凭证差异报告）与 `adjustment-client-booking-status`（入账凭证、疑似入账匹配）直接 import，不另写。若另两个 spec 先实施，按本节 §2 的定义建立同一文件。
- 项目「当前审计阶段」由本 spec 阶段 C 建立，`adjustment-client-booking-status` 读取它。

设计期新发现：

| 编号 | 发现 | 影响 |
|---|---|---|
| N1 | `d2_bidirectional_bridge` 合并时保留 store 行的非受管键；其余带在线编辑的凭证检查 sheet（`phase5_d1_13_sampling`、`phase5_d2_07`、`d3_07`、`f1_07`、`f3_07`、`f4_08` 等 provider）是否保留未核实 | 行元数据在线编辑往返须逐个验证（任务 13） |
| N2 | `_ledger_row_to_item` 已返回 `voucher_type` / `accounting_period` / `company_code`；TS `SampledVoucher` 也有 `voucherType`；是宿主行结构把它丢了 | 凭证字不用新增取数，只需一路带到行元数据 |
| N3 | `uq_sampled_vouchers_batch` 不含日期与凭证字，`register_sampled_vouchers` 又按凭证号 `dict.fromkeys` 去重 ⇒ 一个批次里两张同号不同日的凭证只登记一张 | 迁移重建索引（§8） |
| N4 | `get_voucher_entries` 注释用「(date,no) 借贷 100% 平衡」证明唯一，两张平衡凭证合并后也平衡，推理不成立 | 改注释并以 F1 数据为依据 |
| N5 | 行数门余量：`ledger_penetration.py` ≈ 0 行、`GtVoucherSamplingEngine.vue` ≈ 17 行、`voucher_sampling.py` ≈ 66 行、`useVoucherSampling.ts` ≈ 73 行 | 新端点放新路由文件；引擎弹窗与配对展示放新组件；删引擎里失效的「仅预审/仅年审」视图条腾行 |
| N6 | 引擎内 `applyFillMode` 只对本批 `sampledVouchers` 生效，而宿主从不传前态（F6）；真正的合并都在宿主里各写一套 | 合并逻辑移到共享回填函数，引擎只负责抽样与留痕 |

## 1. 架构决策

**ADR-VK-01 凭证键 = (年度, 主体, 日期, 凭证字, 凭证号)。** 否决 (期间, 凭证字, 号)：医疗器械按期间只有 6,520 组，按日期 13,384 组且每组各自借贷平衡，说明同一期间同号在不同日期是不同凭证。否决 (日期, 号)：F1 的三套金蝶类账混凭证字。

**ADR-VK-02 规范字符串用紧凑 JSON 数组。** `vk = ["2025","001","2025-01-07","ZZ","0003"]` 序列化（Python `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`、TS `JSON.stringify`，年度也写成字符串），避免分隔符转义；分录指纹 `lfp` = vk 五元素后接 `科目, 借贷栏(D/C/X), 金额字符串(两位小数带符号), 同组序号(整数)`。跨语言一致性测试用同一份样例文件比对两边输出。

**ADR-VK-03 借贷栏按栏位判定。** D：借方非零且贷方为零；C：反之；X：两栏都非零或都为零（辽宁卫生借贷双填即 X）。X 行照样有指纹（金额取非零那栏，都非零取借方），用于去重与排除；不参与配对，配对状态记 `unknown_side`（需求 1.2）。

**ADR-VK-04 同组序号按 (摘要, 行 id) 排序。** 同组分录科目、借贷栏、金额都相同，经济上可互换；按摘要排序让重导后序号稳定，摘要改动最多让两条等额分录互换序号，不影响排除与去重结论。

**ADR-VK-05 配对只在后端实现（`voucher_pairing.py`，纯函数）。** 输入一张凭证的全部分录（已带借贷栏与指纹），输出每条分录的配对结果：`status ∈ {paired, multi, large, unknown_side}`、`counterparts[{account_code, account_name, amount, line_fp}]`、`counterpart_summary`（multi/large 时按对方科目汇总，标「非配对」）。算法见 §3。

**ADR-VK-06 行元数据收在一个键 `_gt`。** `{vk, lfp, ph, b, src, pr, sv}`：阶段 `ph ∈ {preliminary, final, null}`、批次 `b`、来源 `src`（engine / attach / manual 的集合）、配对状态 `pr`、存续核对 `sv`。一个键降低与宿主字段冲突的可能；宿主解析函数统一经 `withRowMeta(row, raw)` 透传。

**ADR-VK-07 回填两模式，合并逻辑归共享函数。** 「追加」按 lfp 去重；「替换本阶段抽凭行」只删 `ph` 相同且 `src` 只含 engine 的行。旧 `merge` 映射为追加。引擎不再计算合并结果，`existing-samples` prop 与 `before_data` 快照废弃（撤销改按批次删行，ADR-VK-08）。

**ADR-VK-08 撤销按批次删行。** 引擎发 `undo-request {logId, batchId}` → 宿主共享函数找出 `_gt.b === batchId` 的行，用宿主提供的 `hasUserContent(row)` 判断已填内容，有则确认 → 确认后引擎调后端撤销，成功再删行并保存；后端失败不删行。提示语写实际删除行数。

**ADR-VK-09 项目阶段存 `projects` 两列。** `current_audit_phase`（preliminary / final，缺省 final）、`interim_cutoff_date`。不放 JSONB：要在 SQL 里过滤、要三层一致（迁移 + ORM + schema）。修改限经理、合伙人（含签字合伙人）、admin，按项目角色判定，写审计日志。

**ADR-VK-10 年审口径与合并评价公式。** 记号：`P` 推断错报，`U` 错报上限，`E` 样本实际错报合计。

| 口径 | 年审抽样框 | 全年推断错报 | 全年错报上限 |
|---|---|---|---|
| a 剩余期间 | 预审截止日次日至审计期末 | `ΣP_预审 + P_年审` | `ΣU_预审 + U_年审` |
| b 全年扣除 | 全年 − 本底稿预审已抽分录 | `ΣE_预审 + P_年审` | `ΣE_预审 + U_年审` |

口径 a 两段总体不重叠，直接相加。口径 b 的年审总体已含 1~预审截止月中未被抽到的分录，若再加预审推断就重复外推；预审抽到的分录是从总体里整体拿出来逐笔检查的，按实际错报计。未检查样本按预审评价里登记的处置计入 `E_预审`（视同偏差按账面金额计）。预审批次缺 `sample_error_total` 时不给口径 b 的合并结果，提示「预审批次缺少实际错报合计，请在预审批次重新保存评价」，不以 0 代替。

**ADR-VK-11 存续核对只用行元数据。** 旧版本账套多半已清空（F2），核对拿行上的 lfp 与凭证键对当前 active 数据集现算，不读旧账套。

**ADR-VK-12 存量兼容。** 真库抽凭日志与登记表 0 行（F11），不做数据回填。底稿里没有 `_gt` 的旧行视为来源 manual、阶段未标；共享回填函数遇到「凭证号 + 日期 + 金额」都相同的旧行，视为同一分录：不再插入，并给旧行补写 `_gt`（触碰即迁移）。

## 2. 凭证身份实现

后端 `voucher_identity.py`：

- `VoucherKey(year, company_code, voucher_date, voucher_type, voucher_no)`，`to_str()` / `from_str()`；`side_of(debit, credit) -> 'D'|'C'|'X'`；`signed_amount(debit, credit, side) -> Decimal`。
- `fingerprint_lines(lines) -> list[str]`：按 ADR-VK-04 分组编号，输入同一凭证全部分录。
- `voucher_key_sql(table)`：返回 `(company_code, voucher_date, COALESCE(voucher_type,''), voucher_no)` 四列表达式，供 group by / 行值 IN 使用（PG 与 SQLite 3.15+ 都支持行值比较）。（实施勘误：原写三列漏了主体，真库 4 个 active 数据集一套账有两个主体编码；空串须为 SQL 字面量，绑定参数会让 PG 判 SELECT 与 GROUP BY 不是同一表达式。）
- `resolve_line_fps(db, project_id, year, fps) -> dict[fp, UUID]`：按 fps 里的 (日期, 凭证字, 号, 科目) 小范围取 active 数据集分录，Python 端分组编号后匹配，返回当前数据集行 id。排除、存续核对、去重都走它；账套重导后自动映射到新 id。

前端 `utils/voucherIdentity.ts`：`voucherKeyString`、`sideOf`、`lineFingerprint`，只做格式化与比较，不在前端分组编号（编号由后端给出）。

全链路替换（需求 2）：

| 位置 | 现状 | 改为 |
|---|---|---|
| `ledger_penetration_service.get_voucher_entries`、`drilldown_service.get_voucher_detail` 及两个路由 | (号, 可选日期) | 增 `voucher_type`；只给日期与号且命中多个凭证字时返回 409 `VOUCHER_KEY_AMBIGUOUS` + 候选；每行带 `side`、`line_fp`、`pairing` |
| `ledger_sampling_service.enrich_counterpart_accounts` | 按号取全年、按 (号, 日期) 分组 | 改名 `enrich_voucher_context`：按样本凭证键取分录（日期收窄），算指纹与配对，样本行补 `voucher_key` / `line_fp` / `side` / `pairing` |
| `_build_locate_projection` / `fetch_by_unit_ids` / 内存 `voucher_map` | 按号聚合 | 按凭证键聚合，`unit_id` = vk 字符串 |
| `LedgerQueryFilters` | `exclude_voucher_nos` / `exclude_unit_ids` | 增 `exclude_voucher_keys`（行值 NOT IN）与 `exclude_line_ids`（由 `resolve_line_fps` 得到）；旧两个字段只用于旧日志兼容 |
| `voucher_sampling._get_voucher_sampling_exclusions` 等三处、`cutoff_sampling._get_extracted_voucher_nos` | 行 id / 凭证号 | 读 `filled_line_fps` / `filled_voucher_keys`；旧日志兼容并在历史返回 `legacy_exclusion: true` |
| `sampling_registry_service` 登记、项目级排除、重复提示、概览 | 凭证号 | 凭证键；登记写日期与凭证字（批次行恒有日期，凭证字空写 ''） |
| `derive_idempotency_key` | 凭证号集合 | 分录指纹集合 + 阶段 + 年审口径 |
| `/ledger/sample-voucher` 与回拉 `fetchVoucherLines` | (号, 日期) | 凭证键；新增 `phase`（缺省取项目阶段） |

守卫（需求 2.7）：`test_voucher_identity_single_source.py` 用 AST 扫上述模块，禁止 `voucher_no.in_(`、`group_by(...voucher_no)` 且不含凭证键表达式的写法；基线文件只许变短，交付时为空。

（实施勘误，任务 5：①幂等键用分录指纹，没有指纹时用凭证键 —— 截止测试按整张凭证回填，只按号会把同号的两张凭证判成同一批；只有凭证号的旧日志派生出的键与改造前逐字相同。②守卫另判 `distinct(voucher_no)`、按号相等比较（走 `single_voucher_lines` 的穿透与登记的筛选框除外）与旧口径入口 `legacy_voucher_nos_condition` 的调用点。③行值 IN / NOT IN 一条语句最多 7,000 个凭证键，超过报 400 说明原因。④排除口径收在 `voucher_sampling_exclusion.collect_exclusions`，登记表查询迁到 `sampled_voucher_queries.py`。）

## 3. 配对算法（`voucher_pairing.pair_voucher`）

```
输入：一张凭证的分录 L（含 side、signed amount、lfp），按 (side, 科目, 金额, 序号) 规范排序
1. X 行 → unknown_side，移出
2. len(L) > LIMIT(200) → 全部 large，附对方科目汇总，结束
3. D = 借方行，C = 贷方行
   |D| == 1：D0 与每个 C 行配对（D0 的对方 = 全部 C 行各自金额；每个 C 行的对方 = D0、金额 = 本行金额）；|C| == 1 对称
4. 多对多，迭代直到无进展：
   a. 等额一对一：x 的候选 = 对侧未配对且金额相等的行，先只看不同科目，为空再看同科目；
      x 只有一个候选 y，且 y 的候选也只有 x → 配对
   b. 子集等额：x 在对侧未配对行里找和等于 x 的子集（2..K=6 行）；或在同侧找含 x、和等于对侧某一行的子集；
      子集各行须与 x 同号（红字只与红字凑，需求 3.5）；
      x 的解集恰好一个 → 配对（一对多时 x 的对方 = 子集各行金额；多对一时子集各行的对方 = 那一行、金额 = 各自金额）
   c. 组合数累计超过 50,000 → 停止搜索
5. 剩余 → multi，附整张凭证分录与对方科目汇总
6. 校验：每行至多配对一次、paired 行对方金额合计 = 本行金额；违反则把涉事行全部降为 multi
```

性质测试（hypothesis，max_examples=5）：随机平衡凭证上 paired 行金额守恒、从不出现凭证外金额、输出与输入顺序无关。固定向量：FY-0012（需求 3.8）、1 对多、多对 1、红蓝混合、等额多解（应为 multi）、201 行（应为 large）。

（实施勘误，任务 7：①第 4b 步「x 的解集恰好一个」收紧为「组里每一行的解都恰好是这一个组」，一行的解 = 含它的组 + 它剩余的等额一对一可能（不论科目）。只看发起行不够：借 300 = 贷 100 + 200 = 贷 150 + 150 时，贷方 100 只出现在一个组里，但借方 300 有两个解，答案并不唯一。②预算在某一轮中途耗尽时这一轮一个都不接受（没枚举完，解集数不出唯一性）。③需求 3.1 后半「对方只有一个科目」做成兜底：没配上的行（含超过 200 行的凭证）若对侧只有一个科目，给科目级结果 `basis = single_account`（对方金额 = 本行金额、`line_fp` 为空），与改造前「对方栏只有一个科目时直填」一致；其余 multi / large。④穿透与下钻响应本就是整张凭证，超限凭证每行同一份对侧汇总不逐行重复，标 `summary_omitted`（华氏一张凭证 19,546 行，逐行带汇总约多 20 MB）；抽凭样本照带。⑤旧字段 `counterpart_account` 由配对结果给（`counterpart_label`）：对方只有一个科目填该科目，否则「多科目」。⑥6 套真实账 205 万行、10.8 万张凭证逐张配对，守恒与对称两条不变式 0 违反，单张最慢 232 ms（19,546 行）；对侧汇总改为整张凭证只算一次之前，这张凭证要 104 秒。）

## 4. 回写契约

前端 `components/workpaper/composables/shared/voucherCheckFill.ts`（纯函数 + 一个 composable）：

- `prepareSamples(samples, policy)`：按后端 `pairing` 生成待写入项；`policy = 'expand'`（一行一个对方科目，用于凭证检查表）或 `'join'`（一行一个样本、对方科目用「/」拼接，用于资产类明细表）；multi / large 行一律一行，对方科目写「多科目」，挂整张凭证分录（large 只挂汇总与查看入口）。取代 `expandMultiAccountVouchers` 与 H1 等宿主内联的拼接。
- `mergeVoucherCheckRows(existing, incoming, { mode, phase, source })` → `{ rows, added, existed, replaced, needConfirm }`，规则见 ADR-VK-07、ADR-VK-12。
- `useVoucherCheckFill({ tables, mapSampleToRow, persist, hasUserContent, tableOf? })`：返回 `onEngineFilled`、`onAttachImported`、`onUndoRequest`、`rowClass`（年审阶段给预审行加 `gt-row-locked`）、`guardPersist`（年审阶段保存时预审行用上次读入的版本写回，作为只读的兜底）。`tableOf` 给双区宿主（D2 本期 / 期后等）按日期或自定分区。
- `withRowMeta(row, raw)`：宿主解析函数透传 `_gt`。
- 组件 `VoucherRowMetaTag.vue`（阶段、来源、存续状态标签）、`VoucherPairingCell.vue`（多科目展开整张凭证）。

全局样式 `.gt-row-locked td { pointer-events: none; opacity: .75 }`：预审行在年审阶段点不进编辑控件；`guardPersist` 防绕过（需求 6.3）。

宿主接入：每个宿主改三处——回填处理函数改调 `useVoucherCheckFill`、解析函数套 `withRowMeta`、表格加 `:row-class-name` 与标签列（已有 row-class-name 的用 `combineRowClass` 合并）。按循环分批（任务 10~13），守卫 `voucherCheckFillAdoption.spec.ts` 扫全部引擎宿主与挂凭导入宿主：未调用 `useVoucherCheckFill`、仍调用 `expandMultiAccountVouchers`、给引擎传字面量 `phase` 的宿主必须在冻结清单里，清单只许删，交付时为空。

引擎（`GtVoucherSamplingEngine.vue` / `useVoucherSampling.ts`）：emit `filled` 时样本带 `voucherKey`、`lineFp`、`pairing`、批次号；新增 emit `undo-request`；删除失效的「全量 / 仅预审 / 仅年审」视图条与 `existingSamples` 计算；回填日志写 `filled_line_fps`、`filled_voucher_keys`。

（任务 9 实施勘误）①共享函数另导出 `newEntriesOnly`（截止抽样等不写 `_gt` 的样本列表与底稿回填同一口径去重）、`counterpartLabelOf`（配对结果 → 旧字段对方科目，与后端 `counterpart_label` 同口径）、`combineRowClass`、`SURVIVAL_LABEL` / `SOURCE_LABEL`；`useVoucherCheckFill` 另返回 `ready()`，`onEngineFilled` / `onAttachImported` 收第二个参数 `{ tables }`：多张表且按「本期 / 期后」分别抽凭的宿主，替换只动本次的目标表（缺省全部表）。②同一分录的认法：有指纹按指纹；指纹没对上、旧行没有指纹而凭证号 + 日期 + 金额相同 ⇒ 触碰迁移；待写入行自己没有指纹（预览手工增补）⇒ 与任一已有行凭证号 + 日期 + 金额相同即算已有；同一次写入里重复的只进一行。③`guardPersist`：年审阶段预审行用读入版本写回，但行元数据（来源、存续核对）取当前的；按「指纹 + 对方科目」认行，旧行键只认读入时没有指纹的行（同号同日同金额的别的分录不会被当成预审行）；预审阶段每次保存刷新读入版本。④撤销：年审阶段不撤销预审批次（引擎、共享函数各拦一次，后端 `voucher-undo` 409 `PRELIMINARY_BATCH_LOCKED`）；`voucher-undo` 原来只校验登录，补「记录须属于 URL 项目（否则 404）+ 底稿编辑权」，回报 `batch_id`；引擎撤销流程拆到 `voucher-sampling/useEngineUndo.ts`，宿主没接 `undo-request` 时先确认、只撤销后端记录并如实提示「底稿行没有自动删除」。⑤超过配对上限的大凭证，抽凭样本不带整张分录（`voucher_entries` 空 + `voucher_entries_omitted` + `voucher_line_count`；同一凭证抽中几笔就会重复几份，医疗器械一次 30 个样本里 8 个是 221~509 行的凭证）。⑥挂凭回拉 `pullSamplesForWorkpaper` 的对方科目改取穿透给的 `pairing`，删掉前端按借贷分桶的推断。⑦预览：勾选按行本身认（原按凭证号，同凭证另一笔、同号别日一起被勾）；打开时表格勾选框按样本 `selected` 勾上（原来勾选框全空、统计却是全选）；人工增补按凭证号 + 日期 + 金额认同一笔，同号多笔请补日期或金额。⑧`expandMultiAccountVouchers` 过渡转调：只按 `pairing` 展开，没有配对结果的「多科目」一行、其余样本原样返回；宿主接入完成后删除。⑨引擎的 `phase` prop 保留为可选废弃别名，开发环境首次传入时告警一次。

（任务 10 实施勘误）①`FillSample` 去掉 `[key: string]: unknown` 索引签名（接口样本类型如 `SampledVoucher` 赋不进去）；`tableOf` 可返回 null / undefined，落到 `scope.tables[0]`。②替换只动范围内的表：`applyItems` 只对 `scope.tables` 里的表按替换合并，`tableOf` 路由到范围外表的分录按追加并入（原实现把范围外那张表的抽凭行一起删掉；D2 / D3 / D6 / D7 的两区表都靠它）。③接入守卫认宿主直接 import 的本地子组件里的标签列（D2 矩阵 / 卡片视图；抽凭共享组件目录 voucher-sampling/ 不算），认带泛型的调用（`withRowMeta<Row>(`）。④删掉的旧合并：D3 `applyVoucherFillMode`、E1-31 `mergeJournalLines` / `mergeJournalLineLists`（连同各自用例），D6 / D7 / E1-23 宿主内联的多科目展开（会把金额翻到对方栏）；宿主不再传 `phase`。⑤D7 客户名称改取 `partyNameForColumn`（原写成对方科目）；D2 已在某区的分录留在原区（`zoneHolding`，期末日改过也不在另一区重复插入），D3 / D6 挂凭导入按日期分区。⑥回填提示：引擎只报「已确认 N 笔抽凭样本」，底稿实际填入几行由共享函数报（「填入 N 行」，有去重 / 替换时「填入 N 行，已存在 M 行未重复填入」「…替换本阶段抽凭行 K 行」），宿主各自的「已回填 N 笔」提示删掉（多科目展开、去重后行数与样本数不同；原「成功填充 5 笔凭证」在 5 笔全重复时也照报）。⑦浏览器走查发现（已修）：el-input 只绑 `:model-value` + `@change` 时打的字立即被还原（Element Plus 每次输入后把原生值重置回 modelValue，失焦时 change 拿到旧值），本批 9 个文件 93 处（含引擎预览里的偏差原因、实际错报、替代程序说明 —— 偏差原因必填却输不进，CAS 1314 门控会一直挡住确认）换成新组件 `shared/WpCommitInput.vue`（输入中保管草稿，失焦 / 回车才提交，父组件拒收即还原）；全前端另有 481 个文件 1965 处同形写法（抽查 D2-8 政策检查的说明框：浏览器里同样输不进，2026-06-30 首次提交时就是这种写法），冻结在棘轮 `controlledInputCommitRatchet.spec.ts`（只许降），全量改需另立 spec。VTU 的 `setValue` 在 input 后同步补发 change、读到的是还没被重置的值，组件测试用它测这类框恒绿。

（任务 11 实施勘误）①按借贷栏分表：分借方 / 贷方两张表（区）的宿主（F1-7、F3-7、F4-8、G2-8，以及 G4-13 的分区字段）一律按分录自己的借贷栏进表，共享函数新导出 `sideTableOf`（与分录指纹、配对同口径 `sideOf`：只有贷方栏有数进贷方、红字带符号照记，借贷栏不明进借方）。这推翻了原先「F1 / G2 沿用原规则」的决定：原规则「贷方有正数才进贷方」把贷方红字（贷方 -X）写进借方表成借方 -X，经济方向相反（浏览器：医疗器械 F3-7 凭证 0051「余额结转」贷方 -10,214.93 原进借方区）。真库这些键没有会被新规则分到另一张表的旧行（F1 只有 1 行且无凭证号，F3 / F4 / G2 0 行），换规则不会造成重复。另导出 `counterpartText`：单列「对方科目」的宿主统一写「编码 名称」（名称与编码相同只写一次，配不上为「多科目」）。②各宿主的表：多张表的宿主抽凭进当前（所选）的表、替换只动这张表，挂凭导入时已在某张表的分录留在原处 —— G1-13 两个区段、G10-7 两个口径、G5-12 本期发生额 / 期后两表（抽凭进所选的表，挂凭导入按凭证日期与期末日分表）、G6-15 本期 / 期后（期后表只收资产负债表日之后的凭证，截止日及以前的剔除）；F1-7 替换不动期后表，F3-7 替换不动日后区。③空白占位行：F2-33 / F2-34 / F2-56、F3-7、F4-8、F5-8（默认 16 行）、G1-14、G3-4 新建或表空时带的空白占位行，回填时去掉（有 `_gt` 或有内容的行保留），撤销到表空补回空白行；F3-7 原实现追加时留着那行空行（抽凭行接在它后面；它没有 `_gt`，按手工行保留，替换也删不掉）。F3 / F4 新行的附件位按区内现有最大位顺延。④G2-8 Excel 导入整区覆盖：年审阶段改了的预审行按读入版本写回、删了的补回；导入的行沿用导入前同一分录的 `_gt`（否则导入后全变成手工行，再抽凭就重复）；「异常行索引 → G2-4」跳过预审行。⑤G4-13 由父组件经 `toJSON` 保存，改走 `rowsToPersist`（按读入版本写回预审行）；G6-15 按对方科目展开的几行 `sourceId` 原来相同、被当成重复样本，改带对方科目；G7-18 的行函数从宿主拆到 `composables/g7VoucherCheckRows.ts`（原实现按凭证分录展开多科目凭证、行金额取对方分录的金额、不去重）；G7 凭证抽查区块原按凭证号去重（同一张凭证上两条本科目分录只留一行），改按分录指纹。⑥F2-33 / F2-34 对方科目原写进供应商列，改写对方科目 / 明细；材料领用优先取贷方金额；抽样方法记在行的样本来源上。⑦G3-4 期后收回（`G3TabCalcCheck.vue` + `useG3CalcCheck.ts`）不在任务清单里：它用 `defineAsyncComponent` 把引擎起别名 `SamplingEngine` 挂载，接入守卫只认 `<GtVoucherSamplingEngine` 标签，漏扫了（传 `phase="final"`、按对方科目展开、不去重）。守卫改为同时认引擎的别名（`import X from` 与 `defineAsyncComponent` 两种写法），G3-4 按同样三处改动接入：期后区剔除截止日及以前的凭证并提示「期后收回区只收资产负债表日（…）之后的凭证，已剔除截止日及以前 N 笔」，回填后切到期后区段；删 `fillFromSamples`。⑧静态标题：`title="…${samplingAccountCode}…"` 是普通属性，页面显示字面量 `${samplingAccountCode}`；本批 8 个文件（D1、D3、F1、F3、F4、G2、G3、G4）改成 `:title` 模板字符串，H1 / H2 / H4 / I1 另 8 处随任务 12 改。⑨顺带修：G1-14 结论按 `checkResult === 'pass'` 判，而核对结果只有 `'Y' | 'N' | '异常' | ''`，已核查样本的结论恒空 ⇒ 改判 `'Y'`；「多科目」单元格到序时账的年度先取凭证键上的年度（原用宿主传入的年度，宿主拿不到审计年度时是当年，会跳到没有账的年度）；G10 / G11 来源列的年度在审计年度为空时兜底当年。⑩受控文本框：本批 F / G 宿主再换 140 处 `WpCommitInput`，棘轮 1965 → 1825。⑪`F2ValuationTestSheet.vue` / `useF2ValuationTestSheet.ts` 全仓零挂载（死代码），本批不接入，留在冻结清单，任务 13 连同它在其他守卫里的登记一起删除。

（任务 12 实施勘误）①资产类明细表的映射收在 `composables/assetVoucherFill.ts`：`assetAmount(item, prefer)` 取样本自己那一栏的金额、带符号（增加类表先取借方、减少类表先取贷方，另一栏兜底）—— 原实现各宿主取绝对值，冲销（红字）的增加 / 减少被记成正常发生额；旧行身份 `assetLegacyKey` 仍按金额绝对值认（旧行存的就是绝对值）。另导出 `carryRowMeta`（整表替换导入时同一分录带回原行的 `_gt`，导出表里没有这一列）、`keepLockedRows`（批量带入 / 挂接之后把年审阶段的预审行按行主键换回原样）与针对性检查表用的三个函数（见⑨）。资产类表一个样本一行、对方科目按后端配对用「/」拼接（共享函数 `policy: 'join'`），原实现在前端按 `voucherEntries` 自拼（H4-4）或只写编码（H8-12）。②逐行抽凭：H4-4 / H4-5 的「抽凭」列走 `fillIntoSelectedRow`：第一笔写进所选行（已填的名称 / 备注保留），行带 `_gt`、来源记「手工 + 抽凭」（撤销该批次时保留这一行、只去掉抽凭来源），其余样本与整表抽凭同一去重并入；所选行已关联凭证（含年审阶段的预审行）时本次按整表抽凭填新行，第一笔的分录已在本表别的行时不写所选行。原实现只取第一笔、其余样本静默丢掉（抽凭登记里却记着本底稿抽了这些凭证）、不去重，还把摘要写进支持性文件；工具栏「抽凭引擎」整表抽凭时清掉上次逐行抽凭没用完的目标行。③撤销提示：保留下来的行可能来自挂凭，也可能是逐行抽凭写进的手工行，提示改为「…；N 行同时来自挂凭或手工录入，已保留」。④各 H 宿主：H2-8 凭证号原写进合同编号（证据缺口判断把它当成已查合同），改写凭证号列，旧行按合同编号里的凭证号认；H2-9 减少金额缺省记转入固定资产；H3-5 回填进当前计量模式那张表，原按凭证号去重（同号的另一条分录被丢掉）；H4-5 名称原取本科目名称（每行都是「工程物资」），不写对方科目与日期；H5-7 / H5-8 原把凭证号、金额作为第二个参数传给只收名称的 `addRow`，被丢掉，抽到的行只有摘要；H6-4 按分录自己的借贷栏写列（`sideTableOf`：借方转入清理记原值与期末余额，贷方结转记清理收入与转处置收益、期末余额 0），原实现只认正数，借方红字一列都不写；H8-12 原把摘要写进合同号（H8-2 带入、同步 H9 都按合同号匹配），H8-2 带入的合并行原来丢掉原行的 `_gt`（抽凭行再抽一次就重复），批量带入 / 填充之后预审行换回原样；H8 的读入侦听原在 `linkedDecrease` 之前声明、立即执行时读到暂时性死区（ReferenceError 被 Vue 的错误处理吞掉），打开底稿时总体自动带入从未生效，读入挪到其后；H10-4 原按顺序把第 i 个样本填进第 i 个还没挂凭证的明细行（凭证与资产对不上），改为样本各成一行、不挂明细，旧行按凭证索引「日期/凭证号」拆回两段认，抽凭 / 挂凭 / 撤销后已挂凭证索引的行数落到抽样元数据。⑤截止测试（I2-13 / I2-14 / I6-5 / I6-6，`useCycleCutoff.ts` 两张表各宿主只回填自己那张）：一个样本一行（记账日期、凭证号、账面金额、摘要，单据日期 / 金额留空，查原件后补填），按分录指纹去重，替换只动本方向的表；金额取样本自己那一栏（借方优先、带符号），原实现只取借方、贷方样本金额为 0；方法学先落库（回填 0 条也留痕）；样本表 `I2CutoffSampleTable.vue` 加来源列与只读行。另两条回填路径「截止模块取数」「序时账自动提取」未改（见 tasks 发现）。⑥I1-5 / I1-6 回填从未生效：原处理函数把引擎回填载荷（对象）当样本数组读 —— I1-5 一行不填，I1-6 遍历时抛 TypeError；挂凭导入读不存在的 `date` / `amount` 字段（日期为空、金额为 0）。改走共享函数，删 `appendFromSamples`；I1-5 整表 Excel 导入改为 `guardPersist(carryRowMeta(...))`（同一分录带回 `_gt`，年审阶段预审行按读入版本写回）；I1-2 同名带入跳过预审行（两张表）。⑦I2-8 / I2-11：回填改完即整页保存（与「保存」同一次写入）—— 原实现只改内存，不点保存就丢（抽凭登记里却记着），也不去重；整页保存而不只存行：父组件存一项就改一项 `allResponses`、本函数的 watch 随即整页重读，只存行会把未保存的抽样说明读回旧值。I2-11 受托方原写对方科目编码，改取辅助核算往来单位（`partyNameForColumn(item.sample, 'supplier')`，唯一命中才填）。⑧I2-9 / I2-10 的行读写与回填拆到 `composables/i2SheetRowsFill.ts`（`useI2SheetRowsFill`，`useI2StaffRowsFill` / `useI2WorkHourRowsFill`）。两表原来没有能认出同一分录的列（人员表姓名取摘要、凭证号只记在备注里），旧行身份为空（`legacy: () => null`，宿主用例 harness 加 `noLegacy`）；I2-10 附件索引记「凭证 X / 日期」（原只记凭证号），同人员同项目同月带入不改预审行。⑨针对性检查表（I2-12、I3-5、I4-5、I5-4、I6-4）：照旧一个对方科目一行（`'expand'`），沿用各自的 `mapSampledToI*TargetedRow`，样本经 `preparedAsSample` 换成本行的对方科目与金额（对方科目名称与编码相同时名称留空，「对方明细」不重复写「多科目」）；`hasTargetedCheckContent`（支持性文件、核对 1~5、索引号）判已填内容；回填期间 `holdPersist` 先不保存，`onEngineFilled(payload, onFilled)` 把底稿实际填入的行数交给宿主，`noteEngineSampling` 记进抽样说明（原实现记样本笔数，去重 / 展开前），行与说明同一次保存。I3~I6 的 `persistAll` 改为先全部序列化再逐项保存 —— 原实现存完行再序列化抽样说明 / 风险关注，父组件每存一项就改 `allResponses`、watch 随即整页重读，存进去的是重读出的旧值（未保存的修改丢失）；原实现回填只改内存（I6-4 回填后才保存），按「日期 + 凭证号」去重（同一凭证的其他分录被丢掉）。I4-5 选取原因逐行按测试原因标注（测试原因的高值规则可覆盖引擎缺省的「高值必选」，与原实现同一规则）；I4-2 / I6-2 挂接用 `keepLockedRows`，挂接数只数实际改了的行。⑩标题：任务 11 勘误⑧说的 H1 / H2 / H4 / I1 另 8 处普通属性 `title="…${samplingAccountCode}…"` 改成 `:title`；另 14 处写死科目码、与引擎实际用的映射码不一致（医疗器械 I2 标题 1717、实际抽 1704）—— I2-8~I2-12 五个、I2-13 / I2-14、I6-5 / I6-6、H6-4（1606）、H10-4（6115）、I3-5（1711）、I4-5（1801）、I6-4（6602）—— 改绑 `samplingAccountCode`。新守卫 `src/__tests__/templateStaticInterpolation.spec.ts`：模板 AST 里普通属性（type 6）的值不许含 `${`，指令与绑定属性不在此列（全仓现为 0 处）。⑪守卫与棘轮：接入守卫的组合式函数链原有三处漏洞 —— 只跟宿主直接 import 的一层（截止测试宿主经 useI2Cutoff / useI6Cutoff 包装 useCycleCutoff，第二层里的调用看不到：正面判据误红，反面判据「仍调用 expandMultiAccountVouchers」误绿）、不认 `@/` 别名导入（G6 宿主经 `@/composables/…` 引组合式函数，同样两头误判）、共享回填模块本身进链（它定义了 useVoucherCheckFill / withRowMeta，只 import 它的类型或工具函数的宿主被判为已接入）；改为跟两层、认 `@/`、排除共享模块。变异 m81（只跟一层）首轮存活：截止宿主的 `import type { CutoffRow }` 把 useCycleCutoff 拉进了第一层，「跟两层」的自检其实没测到第二层 ⇒ 链只跟值导入（`valueImportPaths` / `isTypeOnly`：类型导入编译后擦除、不执行），m81 改为 2 红，另加 m98（类型导入也算进链 ⇒ 1 红）。方法学覆盖守卫认 `assetAmount(` 调用为读了金额，并加自检钉住其函数体确实读借贷两栏（函数体改了这条判据即失效）；删 I2-10 的字段豁免（豁免基线 122 → 121），改写 I1-5 / I1-6 / I2-9 的豁免理由。受控文本框：本批 H / I 宿主再换 54 处 `WpCommitInput`，棘轮 1825 → 1771。

（任务 13 实施勘误）①凭证检查表共用的 `useK1VoucherCheck`（J1 / K1 / K2 / K3-7 / K4 / K5-7 / K7 / K8-8 / K9 / M1 / M2 / N2）接入共享回填函数并导出 `mapPreparedToK1VoucherRow` / `hasK1VoucherContent`；新选项 `projectId` / `readonly` / `persist` / `periodEnd` / `extraTables`（宿主自管的表，J1 的期后支付）/ `attachTableOf`；挂凭导入的分表：已在某张表的分录留在原处，其余有 `periodEnd` 的按凭证日期分（期末之后进期后表）、没有的一律进本期发生额，J1 按日期与借贷栏分三区；`load()` 在 finally 里 `markLoaded`；删行 / 改行跳过年审阶段的预审行；导出 `guardPersist`（宿主自管的表保存前同样过一遍）；删 `fillFromSamples` 与 `expandMultiAccountVouchers` 的引用。②宿主不再传 `phase`：J1 用自己的 `samplingTable`（贷方 → 本期、借方 → 期后收款表、期后 → 期后支付），K1 / K3 / K5 用 `samplingTarget`。③接入时顺带修的：K1 / K3 / K7 / K8 / K9 / M1 / M2 把计算属性 `year`（对象）传给 `pullSamplesForWorkpaper` / `listAttachedVouchers`，挂凭导入与已挂计数从来没取对 ⇒ 改传 `year.value`；K4-4 把方法学（对象）当字符串调 `includes` 抛 TypeError，其后关弹窗与保存都没执行，且连手工、挂凭行一起标选取原因 ⇒ 只标本次抽凭填入的行；K8-8 回填后把方法学写进抽样参数；N2 去掉自己的成功提示。④K3-5 长期挂账 / K3-6 关联方的行级抽凭原是空操作（读 `payload.voucherNo`，引擎回填载荷没有这个字段）：新模块 `composables/k3RowVoucherFill.ts`（`useK3RowVoucherFill`）+ 明细表 `k3/inspection/K3RowVoucherTable.vue`，明细单独存 `<表号>-row-vouchers`（不动往来对象行的结构）；行上「📋」抽凭的样本挂到发起行，挂凭导入按辅助核算往来单位（`partyNameForColumn(sample, 'supplier')`）对上同名往来对象、对不上的留在明细里显示「未对应」；K3-5 的 `voucherRef` 与 K3-6 的备注不再改写（原设计是把凭证号写进行上一个字段，一行只能记一笔、多笔互相覆盖）。⑤一行一个样本的宿主（`policy: 'join'`）：K5-6 未决诉讼金额取贷方（`assetAmount(item, 'credit')`），旧行身份按凭证号 + 日期 + 金额，Excel 导入经 `carryRowMeta` 带回 `_gt`；K8-6 / K8-7 截止测试只填记账凭证一侧，支出凭单编号 / 日期 / 金额留空待查原件（原实现把记账凭证的号、日期、金额同时抄进支出凭单三列，双侧证据「齐全」、结论恒为正常），对方科目取 `counterpartText`，两张分段子表的文本框换 `WpCommitInput`；K8-5 合同摊销一个样本一行合同，凭证索引「凭证 X / 日期」、往来单位取辅助核算，原实现只写项目名、认不出是哪张凭证 ⇒ 旧行身份为空；K10-6 备注记「抽凭：凭证号」，旧行身份从备注解析，金额取贷方。K8 截止 / K8-5 / K10 也返回 `onAttachImported`（宿主目前没有挂凭导入按钮，接口与其他宿主一致）。⑥K12-4 / K13-4（状态在组件里）：行号计数器原在读入侦听之后声明，侦听立即执行时 `normalizeRow → createRow` 落进暂时性死区，被 catch 吞掉 ⇒ 打开底稿一行都读不出（保存时又按空表覆盖）；计数器挪到侦听之前。14 处文本框换 `WpCommitInput`。⑦在线编辑往返（N1）：逐个受管凭证检查 item 验证合并（`backend/tests/test_voucher_row_meta_online_edit_roundtrip.py`）。回方向接通的只有 D1-13（多 item 镜像，整册合并按表切片后走框架层行表引擎）、D4-14（手写合并按表前缀过滤）、F5-8（单 item，正好是 provider 的 `STORE_ITEM_ID`）；三者与框架层引擎都是浅拷贝基线行再写受管列，`_gt` 与其他非受管键原样保留 ⇒ 「丢失的在合并处透传」没有要改的。D3-7 / D6-6 / D7-7 / F3-7 / F4-8、D2-7、F1-7 / F2-56 的现状见 tasks 发现②（strict xfail 与守卫钉住，接通即转红、提示补用例）。⑧接入守卫冻结清单清空；`F2ValuationTestSheet.vue` 不删（F 循环冻结 slice 与后端路由基线快照引用其文件与行号），改登记「未挂载」，守卫核实它确实无人挂载（import 路径或模板标签，排除 `components.d.ts`）且仍未接入，挂载判据另有自检（用真实被挂载的 G5-12 验证不是恒空）；守卫跟 `defineAsyncComponent(() => import('./X.vue'))` 引入的子组件（K8-6 / K8-7 的分段表格这样引入，原只认静态 import，来源列判据误红）。`expandMultiAccountVouchers.ts` 与其单测删除（全仓 0 调用方，任务 9 勘误⑧「宿主接入完成后删除」）；引擎的 `phase` 废弃别名照任务 9 勘误⑨保留（死代码 `F2ValuationTestSheet.vue` 仍传 `phase="final"`）。⑨标题：K3-7 / K7-5 / K9-8 / M1-6 / M2-5 / N2 的抽凭弹窗标题写死科目码、引擎实际用映射码 ⇒ 改绑 `samplingAccountCode`（同任务 12 勘误⑩）；医疗器械 K3-7 因此显示 2205，配置错能被看见（见 tasks 发现①）。⑩类型：`readonly` 选项是 `MaybeRefOrGetter<boolean | undefined>`，在交给共享函数的边界上转成布尔；K3-5 / K3-6 模板里 `rows.map((r) => r.rowId)` 的 `r` 推断成 any，挪到脚本里的 computed。⑪守卫与棘轮：k3Integration 不再要求引擎写死 `phase="final"`，改要求接 `@undo-request` 与 `useK3RowVoucherFill(`；方法学覆盖守卫删他会话留下的 K12 字段豁免（K12 早已满足，任务 11 起是既有红）；错码棘轮 I2 基线 60 → 53（任务 12 标题改绑去掉 7 处写死的 1717）；受控文本框棘轮 1771 → 1738。

## 5. 挂凭多底稿与已挂标识（需求 5）

新路由 `routers/voucher_links.py`（`ledger_penetration.py` 无行数余量）：

- `POST /api/projects/{pid}/ledger/sample-vouchers/batch`：`{vouchers:[{voucher_date, voucher_type, voucher_no, account_code}], working_paper_ids:[...], note}`；逐条 SAVEPOINT，返回每个 (凭证, 底稿) 的 `created / existed / failed + 原因`；edit 权限；阶段取项目当前阶段。
- `GET /api/projects/{pid}/ledger/voucher-links?keys=...`：凭证键 → `[{wp_code, source, phase}]`（手工与引擎登记合并）；readonly 权限；单次最多 500 个键。

前端：`AttachVoucherToWpDialog` 改多选（推荐组默认勾选），调批量接口并列出失败明细；序时账明细层与凭证层按当前页凭证键批量查已挂标识并显示标签。

（实施勘误，任务 14：①已挂查询是 `POST /ledger/voucher-links/query`（不是 GET）：500 个凭证键（主体是中文公司名）放进查询串超过请求行长度。请求体 `{year, keys}`，多余字段 422，超过 500 个键 422 `TOO_MANY_VOUCHER_KEYS`；返回 `{links: {凭证键: [{working_paper_id, wp_code, wp_name, wp_missing, source, phase, count, legacy}]}}`，按（底稿, 来源, 阶段, 旧登记）合并计数；底稿限本项目且未删，否则标 `wp_missing`、不透出别的项目的底稿编码；V210 前的旧登记缺凭证字 / 主体时按通配匹配并标 `legacy`，没有日期的旧登记不出标识。②批量挂凭每张凭证可带 `company_code`，不收阶段（多余字段 422，阶段一律取项目当前阶段）；单次最多 500 个「凭证 × 底稿」组合，超出 422 `ATTACH_BATCH_TOO_LARGE` 且一条不写；凭证定位与每个组合的写入各一个 SAVEPOINT，单条被数据库拒绝只回滚那一条；失败原因 `VOUCHER_KEY_AMBIGUOUS`（附候选）/ `VOUCHER_NOT_FOUND` / `WP_NOT_IN_PROJECT` / `ATTACH_WRITE_FAILED`。③已挂的行再挂不改阶段（单张接口同此修正：年审重挂预审挂过的凭证若改成年审，口径 b 就排除不了它），只有软删后复活的行与阶段为空的旧行取当前阶段。④序时账明细层（游标 / 偏移分页、辅助明细两条查询）每行补 `voucher_type` 与 `company_code`，前端按行还原凭证键；凭证层用后端给的 `voucher_key`。⑤凭证穿透与下钻增加可选 `company_code`（`voucher_identity.company_code_condition`，空串 = 不限：四表主体非空，没映射记 `default`）：同日同号同凭证字只差主体时（真库现扫 3 个已软删的 B2Perf 性能测试项目各 92 组，在用项目 0 组），选候选不带主体会再次 409、永远打不开。⑥凭证层 URL 现场带 `voucherType`（空串也写：凭证字为空 ≠ 不知道）与 `voucherCompany`：页面每次写 URL 都按 fullPath 整页重挂载、从 URL 恢复，原来不带凭证字 ⇒ 从明细层穿透到同日同号多凭证字的凭证会立刻改列候选；选候选后也写 URL。⑦标识查询按 500 键分段顺序发，查过的（含空结果）缓存，同键晚到的旧响应不覆盖，切项目 / 年度清空，审计年度未知不查；挂凭后只重查这几张凭证。⑧弹窗底稿多选：推荐组置顶、默认勾选、每张底稿只列一次；提交前按 500 组合上限拦截；有失败时弹窗不关并列出原因；只选一张底稿且全部挂上才询问跳转。）

## 6. 阶段与年审口径（需求 6、7）

- 项目：迁移加两列（§8）；项目详情返回、项目设置「年度准则」页增「审计阶段」区块（阶段单选 + 预审截止日）；保存走项目更新接口并按 ADR-VK-09 判角色。前端 `useProjectAuditPhase(projectId)` 缓存读取，切换后经现有项目事件刷新。
- 引擎显示「当前阶段：年审（预审截止 2025-09-30）」；阶段不再是 prop（宿主传入的 `phase` prop 先保留为废弃别名并告警，守卫要求删除）。
- 新路由 `routers/sampling_phase.py`（`voucher_sampling.py` 余量不足）：
  - `GET /sampling/phase-context?wp_id=`：当前阶段、预审截止日、本底稿预审批次数 / 分录数 / 预审手工挂凭数、本底稿上次年审口径。
  - `GET /sampling/phase-evaluation?wp_id=&log_id=`：按 ADR-VK-10 计算全年合并评价，返回各分量、口径、科目范围是否一致。
  - `POST /sampling/interim-survival`：见 §7。
- `voucher-extract` 请求：`phase: Literal['preliminary','final']`（缺省取项目阶段，非法 422）；新增 `final_population_mode: Literal['remaining','full_minus_interim'] | None`（年审且存在预审时必填，否则 422 `FINAL_POPULATION_MODE_REQUIRED`）。口径 a 把日期窗口改为截止日次日至期末（与用户所选期间求交，求交为空则 400 说明）；口径 b 收集排除清单：预审批次 `filled_line_fps` ∪ 预审手工挂凭在本底稿科目范围内的分录指纹，经 `resolve_line_fps` 转成当前行 id。
- 弹窗 `FinalPopulationModeDialog.vue`：两个选项各一句话说明口径与评价方式（ADR-VK-10 表格的大白话版），显示预审批次数、样本数、截止日；缺省选上次口径，首次选 b。
- 评价：`_normalize_evaluation` 增 `sample_error_total`（金额型，缺省不写）与 `combined`（对象，由 phase-evaluation 结果写入，缺省不写）；`update_sampling_record_evaluation` 把合并结论拼进 `conclusion`。
- G5 / K1 / J1 / M1 / M2：「本期 / 期后」改宿主自己的 `samplingTarget` 状态，不再经 `phase` 传给引擎。

（实施勘误，任务 15：①「预审工作」= 本底稿未撤销的预审抽凭批次（`voucher_sampling` 日志、`extraction_criteria.phase='preliminary'`；截止测试批次不算）或预审手工挂凭（`sampled_vouchers` 中 `batch_id` 为空、`phase='preliminary'`、未删）；判定与执行在 `services/sampling_final_population.py`，`phase-context` 与 `voucher-extract` 用同一份上下文，弹窗看到的就是后端执行的。②手工挂凭只登记了凭证键，没有分录指纹：口径 b 在当前账套按（日期，号）粗取同日同号分录，再由 `_attach_matches` 逐张认领（凭证字 / 主体为空的旧登记按通配，凭证字空串只认凭证字为空的那张），只扣落在本次科目范围（与总体同一前缀匹配）里的分录，直接得到当前行 id —— 凭证键是值，账套重导后照样定位，等价于设计写的「指纹 → `resolve_line_fps`」；没有日期的旧登记定位不了，计 `unresolved_attach_count`，不按凭证号整张排除（会连带全年同号凭证）；挂凭的凭证重导后分录被改，按凭证键仍整张扣除（宁多排不漏排，存续核对会标出）。③口径 a 的截止日：项目设了用项目的；没设时取本底稿预审批次期间上限（`filters.date_to`，否则所选会计月份最大一月的月末），留痕 `interim_cutoff_source = interim_batches`；两者都没有 400 `INTERIM_CUTOFF_REQUIRED`；与所选期间求交为空 400 `REMAINING_PERIOD_EMPTY`。口径 a 照旧排除预审批次回填的分录（`collect_exclusions` 年审一律排除）。④预审阶段、或年审但本底稿没有预审工作：口径不适用，请求带了也不记，`stats` 不出 `final_population`。⑤留痕：抽凭响应 `stats.final_population`（口径、截止日与来源、实际窗口、预审批次数 / 样本数 / 分录指纹数、挂凭张数、扣除的挂凭分录数、定位不到的挂凭数），前端回填时写进 `extraction_criteria.final_population_mode` 与 `final_population`（口径参与批次幂等键）；抽样记录 `population_description` 追加「年审口径 a / b …」，旧记录输出不变；抽凭历史显示口径标签；上次口径取最近一次未撤销的年审批次。⑥`phase-context` 鉴权：底稿只读权（`authorize_wp_read`）且底稿属于路径项目。⑦`voucher-extract` 的 `except Exception` 会把口径的 422 / 400 吞成 500，加 `except HTTPException: raise`。⑧前端：引擎「执行抽样」先 `chooseFinalPopulationMode`，弹窗取消则不抽；读上下文失败按「不须选」继续，须选时由后端 422 拦下；重抽（不带参数）沿用上次口径；新一次抽样不带上一批的留痕。⑨收口任务 14 发现未修③：`DELETE /ledger/sampled-vouchers/{id}` 对引擎批次的登记 409 `ENGINE_REGISTRATION_LOCKED`（要撤销整个批次），项目在年审时对预审挂凭 409 `PRELIMINARY_ATTACH_LOCKED`，不属于本项目 404（原来恒 200），已删的再删照常返回。）

## 7. 预审样本存续核对（需求 8）

`POST /sampling/interim-survival {wp_id, rows:[{lfp, vk, account_code, side, amount}]}`（行在 `checklist_responses` 里，由前端提交元数据；后端只读账套），对当前 active 数据集逐条判定：

1. `resolve_line_fps` 命中 → 未变；
2. 凭证键仍在但指纹不在 → 分录已改（返回该凭证现有分录摘要）；
3. 凭证键不在，同日期、同科目、同借贷栏、同金额的分录存在 → 疑似重编号（返回候选凭证键，至多 5 个）；
4. 否则 → 凭证已删除。

前端：带预审行的宿主在账套版本变化后显示横幅「预审样本需在当前账套核对」，一键核对后写 `_gt.sv = {status, datasetId}`；逐行确认写 `ackBy / ackAt`。

后端读不到 `checklist_responses` 里各宿主的行结构，所以核对接口自己落一条汇总：新表 `interim_survival_checks`（项目、底稿、账套版本、四种状态计数、未确认数、核对人与时间，每底稿每账套版本一行，upsert）；逐行确认走 `PATCH /sampling/interim-survival/{check_id}` 更新未确认数。项目级概览 `voucher-coverage` 读这张表返回各底稿未确认的非「未变」行数。

## 8. 迁移 V{n} / R{n}

实施拆成两个迁移：`sampled_vouchers` 部分随任务 3，`projects` 两列与 `interim_survival_checks` 随任务 8；号码各自实施时现扫。

```sql
ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS voucher_type VARCHAR;
ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS phase VARCHAR(16);
-- phase 约束：NULL 或 preliminary/final（DO 块判重后 ADD CONSTRAINT）
DROP INDEX IF EXISTS uq_sampled_voucher_manual_project_year_no;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_voucher_manual_key_wp ON sampled_vouchers
  (project_id, year, voucher_no, COALESCE(voucher_date,'1900-01-01'::date), COALESCE(voucher_type,''),
   COALESCE(working_paper_id,'00000000-0000-0000-0000-000000000000'::uuid))
  WHERE is_deleted = false AND batch_id IS NULL;
DROP INDEX IF EXISTS uq_sampled_vouchers_batch;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_vouchers_batch_key ON sampled_vouchers
  (project_id, year, voucher_date, voucher_type, voucher_no, working_paper_id, batch_id)
  WHERE is_deleted = false AND batch_id IS NOT NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS current_audit_phase VARCHAR(16) NOT NULL DEFAULT 'final';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS interim_cutoff_date DATE;
-- current_audit_phase CHECK IN ('preliminary','final')
CREATE TABLE IF NOT EXISTS interim_survival_checks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id), working_paper_id UUID NOT NULL,
  dataset_id UUID NOT NULL, total INT NOT NULL, unchanged INT NOT NULL, changed INT NOT NULL,
  deleted INT NOT NULL, renumbered INT NOT NULL, unacked INT NOT NULL,
  checked_by UUID, checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (working_paper_id, dataset_id));
```

`register_sampled_vouchers` 的 `on_conflict_do_nothing` 按新批次索引列。R{n} 反向删表、删列删索引并恢复旧索引。ORM（`SampledVoucher`、`Project`、新 `InterimSurvivalCheck`）与 schema 同步加字段（三层一致）。

（实施勘误，任务 8：①迁移号 V212 —— 实施时现扫 V211 已被并发会话的 `attachment_ocr_confirmation` 占用并落库。②平台没有通用的项目更新接口（字段由向导分步保存或专用端点改），阶段单独一条 `GET / PUT /api/projects/{id}/audit-phase`（`routers/project_audit_phase.py`）；角色判定复用程序行委派人的 `ensure_project_delegator`（项目委派角色 manager / partner / signing_partner + admin），外加项目 edit 级：归档项目 423，EQCR 是 review 级不能改，审计员是 edit 级但委派角色不符 403。③向导新建的项目只填审计年度、没填期间，期间按该年度 1 月 1 日至 12 月 31 日，预审截止日按它校验。④审计日志写 `app_audit_log`（动作 `project.audit_phase.change`，old / new 原样；与改上级代码同一做法，放 SAVEPOINT，写失败不阻断）。⑤抽凭请求 `phase` 改 Literal、缺省按项目阶段；任务 10~13 改独立字段之前，G5 / K1 / J1 / M1 / M2 仍借 `phase` 传「本期 / 期后」，前端引擎只在值是预审 / 年审时才发，其余不发由后端按项目取，避免这几个宿主抽凭 422。⑥`schemas/core.py` 未改：其中 `ProjectUpdateExtended` / `ProjectResponseExtended` 全仓零引用，项目详情实际用 `audit_platform_schemas.ProjectCreateResponse`。）

## 9. 测试与验收

- 阶段 A：`test_voucher_identity.py`（键、借贷栏、指纹、行值 SQL；跨语言样例 `backend/tests/fixtures/voucher_identity_vectors.json` 前后端共读）、`test_voucher_identity_real_ledger_pg.py`（pg_only 只读：6 套账凭证键计数、FY-0003/ZZ-0003、医疗器械银行存款 8,592）、单一来源守卫。
- 阶段 B：`test_voucher_pairing.py`（向量 + 性质）、`voucherCheckFill.spec.ts`（两模式、旧行触碰迁移、撤销确认、只读兜底）、宿主接入守卫、带在线编辑的凭证检查 sheet 行元数据往返测试（每个 provider 一例）。
- 阶段 C：`test_sampling_phase_pg.py`（口径 a/b 的框与排除、重导后 lfp 仍排除、合并评价两公式、缺 `sample_error_total` 不给结果）、`test_interim_survival_pg.py`（四种状态在回滚事务内造数）、阶段字段三层一致与 422。
- 变异（每条记「变异 → 打红测试 → 还原核对」）：凭证键去掉凭证字、指纹加回摘要、配对去掉唯一解判断、追加去掉去重、替换不限阶段、口径 b 改为加预审推断、存续核对第 3 步删掉、宿主守卫清单加回一项。
- 浏览器（chrome-devtools，【测试】项目）：需求 9.3 全流程；关键点击前校验 `location.pathname`；写入清理走平台路径并对账。

## 10. 风险与回退

| 风险 | 处理 |
|---|---|
| 宿主文件被并发会话频繁修改 | 每批在私有 worktree 改，动手前重读；提交前 `git diff --cached --name-only` 核对只含本批文件 |
| 在线编辑往返丢 `_gt`（N1） | 任务 13 逐 provider 验证；丢失的 provider 在合并处补透传非受管键 |
| 指纹排除的查询开销 | `resolve_line_fps` 只按排除清单涉及的 (日期, 凭证字, 号, 科目) 取行；和平药房（114.7 万行）上实测抽凭接口 P95 不超过改造前 1.5 倍 |
| 行数门 | 新逻辑全进新模块；`GtVoucherSamplingEngine.vue` 删视图条腾行；超限即拆，不登记白名单 |
| 用户在年审改预审行 | `gt-row-locked` 阻止点击 + `guardPersist` 写回兜底 |

（实施勘误，任务 16：①`services/sampling_phase_evaluation.py` 是全年合并公式单一来源；只算目标年审批次**之前**、未撤销、同底稿的预审批次。口径 a 分别相加预审 P/U，口径 b 分别加预审 E；缺预审评价、缺 E、年审缺 P/U 都返回 `available=false`，不以 0 代替。`applicable=false` 明确表示预审批次 / 没有年审口径等「本来不需要」，与 `applicable=true, available=false` 的「需要但缺分量」分开，前端前者不显示、后者显示原因。②E = 未检查处置改写后、实际参与推断样本的 `actualMisstatement` **绝对值**之和，Decimal 四舍六入五成双到分；保守原因是高估与低估不应在错报上限里相互抵消。不可解析 / 非有限 / 负 E 不落库；旧载荷没有 E 时输出键集合逐字节不变。③`combined` 只允许服务端写：评价白名单丢客户端同名对象，`voucher-evaluation` 与回填随带评价的 `cutoff-fill` 都调用同一服务；后者必须先写 combined 再登记抽样记录，保证 `sampling_records.conclusion` 同时带 `【全年合并评价】`。科目范围不同标「仅供参考」；预审手工挂凭不参与推断，在结论里注明张数。④前端 `CombinedPhaseEvaluation.vue` 只解析 / 展示后端结果，不复制公式；显示预审分量、年审 P/U、全年 P/U、逐预审批次分量和结论，异步请求以序号防晚到旧响应覆盖新批次。⑤浏览器抓到引擎批量「填入」直接绑定带可选参数的 `applyBatchCheckResult`，Vue 自动传 `PointerEvent`，两行核查结果真实写成 `[object PointerEvent]`；按钮改显式 `() => applyBatchCheckResult()`，表头 `@change(val)` 仍传值。⑥浏览器还抓到跨批次数据破坏：新抽样清空 `loadedFromBatch`，未回填前实际错报自动保存发 `log_id=null`，后端默认定位最近的预审批次，年审 P/U/E 会覆盖预审评价。现改为当前会话未绑定日志时不发独立评价请求（评价随 `cutoff-fill` 写）；`cutoff-fill` 成功后同时读响应 `id` / `batch_id` 绑定精确批次，之后 `/voucher-evaluation` 只发显式 `log_id`。该防线是两阶段评价成立的前置，不是展示层补丁。）

（实施勘误，任务 17：①不新增迁移：`V212/R212` 与 `audit_phase_models.InterimSurvivalCheck` 已在任务 8 为本任务提前落地，实施时现扫最高 V213；本任务只接通服务、路由与消费方。②四步算法的单位是**源分录 lfp**，不是展示行：一对多配对会把一条源分录展开成多个底稿行，它们必须只计一次、同写状态、同确认；第三步严格同时匹配日期 + 科目 + 借贷栏 + 金额，且只在原凭证键不存在后运行，避免「原凭证分录已改、旁边恰有同额凭证」误判改号。请求的科目 / 栏位 / 金额由前端从 lfp 解析，后端再与 lfp 逐值校验；坏元数据整批拒绝，不猜。③同一 active dataset、同一 status 的重跑保留 ack；数据集或状态任一变化都清确认。`interim_survival_checks.changed` 是既有 DB 列，对外统一叫 `modified`。PATCH 带 checkId + datasetId + 剩余未确认数，幂等设值且旧数据集 409。④父 `GtWpRenderer` 与 62 个子宿主间用按 workpaperId 的内存 registry 桥接：子 `useVoucherCheckFill` 注册表 refs / apply / persist，父只挂一个横幅；缺 lfp 的预审旧行计入不可自动核对数。一键核对写 `_gt.sv={status,datasetId,checkId,checkedAt,detail,candidateVoucherKeys}`；非未变逐行 ack 写 `ackBy/ackAt`。ack 顺序为「先宿主 persist，后 PATCH 汇总」，后者失败只会保守多报；成功后再通知横幅回读。⑤项目抽样概览按当前 active dataset 合并汇总；与 sampling_records 做并集，避免只有手工挂凭 / 存续汇总的底稿消失。`voucher-coverage` 原来只有登录门禁，因本任务新增项目级数据而补 `assert_project_permission(readonly)`。⑥浏览器抓到 registry 连续 markLoaded / persist 会近同时发同一 status GET，平台 GET 去重取消先发请求；横幅改 single-flight，运行中变化只排队一次补跑。⑦`SamplingEnhanced` 年度不准新增 `new Date().getFullYear()-1` 兜底（初版因此打红 audit-year ratchet）：取项目 store，未定时省略 year 交后端按项目审计年度反解。）
（实施勘误，任务 18：①需求 9.3 的「重导全年账」没有在浏览器再次上传 114.7 万行文件：身份跨版本、排除与存续四态由真 PG 回滚事务复制并激活新数据集验证；浏览器在【测试】项目改一条 active 分录、核对 / 确认 / 恢复，再撤销真实年审批次并刷新验证预审行保留，组合覆盖而不伪称单一浏览器步骤。②性能基线固定为 44707a388，候选为 ae3bcb846 + 阶段 C；和平药房 1,147,414 行 active 账套、1122 总体 312,715 行，固定 30 样本与 seed，两边各 2 次预热、12 次交替、HTTP `trust_env=False` 避免本机代理；P95 150.49 → 144.64 秒，比值 0.9611。该 K1 没有历史抽凭日志，非零 lfp 排除不在此性能分母，另由真 PG 行为测试覆盖。③233 条逻辑磁盘变异按 A 32 / B 125 / C 76 汇总；补强重跑与同一变异的 PG 对照不重复计数。④最终提交树以最新 origin 为基线，阶段 C 50 个路径自 ae3bcb846 后与上游 0 重叠；后端 / 前端失败节点集合与最新 origin 完全相同，核心 tsc、ESLint、新组件 stylelint、行数门和 diff-check 通过；全阶段 C stylelint 的 25 条既有错误与 origin 同数同类，含 Renderer 的扩展 vue-tsc 在 8GB 仍 OOM，如实保留环境限制。⑤【测试】项目只走平台软删进入回收站；项目 404 / 不再列出 / 同名前缀现行项目为 0，子记录按审计留痕保留，不做物理清除。）