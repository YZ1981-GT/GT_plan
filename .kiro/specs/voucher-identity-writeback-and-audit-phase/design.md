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

## 5. 挂凭多底稿与已挂标识（需求 5）

新路由 `routers/voucher_links.py`（`ledger_penetration.py` 无行数余量）：

- `POST /api/projects/{pid}/ledger/sample-vouchers/batch`：`{vouchers:[{voucher_date, voucher_type, voucher_no, account_code}], working_paper_ids:[...], note}`；逐条 SAVEPOINT，返回每个 (凭证, 底稿) 的 `created / existed / failed + 原因`；edit 权限；阶段取项目当前阶段。
- `GET /api/projects/{pid}/ledger/voucher-links?keys=...`：凭证键 → `[{wp_code, source, phase}]`（手工与引擎登记合并）；readonly 权限；单次最多 500 个键。

前端：`AttachVoucherToWpDialog` 改多选（推荐组默认勾选），调批量接口并列出失败明细；序时账明细层与凭证层按当前页凭证键批量查已挂标识并显示标签。

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
