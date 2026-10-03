# Task 10 第 2a 段：D3-5 footer 锚点阻塞只读调查

> 纯调查：未改任何生产代码 / 测试 / 契约 JSON / tasks.md。临时探针脚本用完即删。
> 每完成一步即追加命令与关键输出。

## §1 端到端坐实（D3-5 单 binding，2 行 / 6 行 materialize）

命令：临时探针 `backend/_probe_2a_materialize.py`（驱动手法照抄 `test_d3_04_dual_zone_shift_and_verify.py`
的 `_synthetic_definitions` + `build_excel_adapter(direction="html_to_oo")` + `adapter.materialize` +
`adapter.verify_unmanaged_regions`；substrate = 真实权威模板经 `instrument_workbook_bytes_multi`
注入 D3-2 单数 spec + `P._instrumentation_of(s)` 的 4 个扩容 spec；契约 = `assert_contract_file_matches_source()`），
`..\.venv\Scripts\python.exe _probe_2a_materialize.py _probe_2a_materialize.json`（cwd=backend）。

前提实测：契约 D3-5 `FooterAnchorSpec(marker='合计', search_column='A', carries_total_formula=True)`；
`_GT_SYNC` 冻结 `GT_FOOTER_ROW_D35=14`；注入种子 UUID `I11..I13 = GTROW-D35-0011..0013`。
2 行 = 复用 `GTROW-D35-0011/0012`（无 orphan，不插行）；6 行 = 3 个种子 + 3 个新 id（orphan=3，需插行）。

| 场景 | 结果 |
|---|---|
| D3-5 单 binding · 2 行 | **抛** `excel_materialize.FooterAnchorDriftError`（`excel_materialize_footer_anchor_drift`）：「契约声明的 footer marker '合计' 在列 A 上一处都找不到 —— … 定位不到即结构漂移，不得按固定行号继续写」 |
| D3-5 单 binding · 6 行 | **同上，同一异常同一消息** |

抛出点（两例相同）：`materialize_projection:3195 → _plan_materialize_step:3109 → plan_managed_writes:1724 → assert_footer_anchor_stable:1367`。
计划期、写任何格之前抛出，staged 文件不存在（零产物）。插行与否无关：`assert_footer_anchor_stable`
在 `plan_managed_writes` 里对每次 materialize 都执行。6 行场景下 `_plan_row_shift` 排在它之前且能通过（它取冻结值
`GT_FOOTER_ROW_D35=14`，不搜 marker），随后 footer 锚点门在可见侧按文本搜 marker 时抛出。
⇒ **第 1 段推断成立**，不是误判。

## §2 影响面（真实流程 sibling 集合 + D3-5 失败是否连带中止整个 D3 entry）

### 2.1 真实流程带哪些 binding（读码 + 内核离线实调）

- attach 路径 `phase5_d3_prepaid_receipts.attach_adapters`（:872 起）：`build_excel_adapter(definitions=…, binding=observation.identity_binding, direction="html_to_oo")`，**不传 `sibling_bindings`**（D4 `phase5_d4_revenue_detail.attach_adapters` 才调 `_attach_sibling_bindings`；D3/D1 都不调）。
- 首发布路径 `projection_first_publication`：`_provider_for(entry_id)` 取 registry 登记的 `provider_module = phase5_d3_prepaid_receipts`（entry 模块本身，不是伴生 `phase5_d3_expansion`）；`_sibling_identity_bindings` / `_align_specs_to_sibling_tables` / `_static_region_bindings` 都先 `getattr(provider, "instrumentation_specs")`，entry 模块**没有**这个属性（探针 `callable(getattr(ENTRY,"instrumentation_specs",None)) == False`）⇒ sibling 恒为 `()`。
- 同理 `stage_substrate`（:397）在 provider 无 `instrumentation_specs` 时走单数 `instrument_workbook_bytes(provider.instrumentation_spec())` ⇒ **真实发布的 substrate 只注入 D3-2**，D3-6/D3-4/D3-5 的 Table/UUID 列/`GT_FOOTER_ROW_D3x` 都不会出现（契约里有这几张 sheet，但真实 representation 上没有载体；这个组合在真实观测器/extract 上的表现本次**未验证**）。
- `oo_to_html.py:2154` 重建 adapter 时透传 `adapter.sibling_bindings`，对 D3 即 `()`。
- 内核离线实调（只读）：`attach_sibling_bindings(provider=ENTRY, primary=D3-2, contract=现状契约)` → `[]`；`attach_sibling_bindings(provider=phase5_d3_expansion, …)` → **抛** `ProviderCapabilityError`「instrumentation_specs 数 (4) 与契约行 table 总数 (5) 不一致」（伴生模块的复数清单不含 D3-2）。

- 更上游：离线读 manifest，`capability_of(entry) = Capability.single_onlyoffice`，`manifest_capability_enabled() == False` ⇒ `attach_adapters` 第一道门就返回 `()`，D3 今天连 D3-2 的 adapter 都不注册（与 Task 5 结论一致）。

⇒ 今天的真实流程：D3 不注册 adapter；即便放开 capability，一次 materialize 也只带 **D3-2 一个 binding**。D3-5 不在 binding 集合里，
也不在真实 substrate 上，**当前不会拖垮 D3-2**。要让 D3-5 真正进入 materialize，至少还缺两步：entry provider 暴露包含 D3-2 的复数
`instrumentation_specs`，attach 路径接上 `attach_sibling_bindings`（D4 的做法）。
离线复现真实形态（D3-2 primary、无 sibling、substrate 为 5 区全注入）：`materialize OK`，`verify_unmanaged_regions equivalent=True`。

### 2.2 一旦接上 sibling：任一 binding 失败即整册中止（离线实测）

读码：`ExcelSyncAdapter._materialize_within_scope` 多 binding 时先走 `_try_single_pass_materialize`
（`materialize_projection_single_pass` 逐 binding `_plan_materialize_step`，只捕获 `SinglePassDeclined`），
回落的逐趟链式循环也没有逐 binding 的 try/except ⇒ 任何一个 binding 的计划期/apply 期异常都直接冒泡，零产物。

离线实测（D3-2 primary，其余作 sibling；每区 1~2 行、不插行）：

| 场景 | 结果 |
|---|---|
| D3-2 + {D3-6, D3-4借, D3-4贷, D3-5} | **抛** `FooterFormulaRangeError`（`excel_materialize_footer_formula_range_stale`）「footer 格 C17 的公式 'SUM(C12:C14)' 区间只到第 14 行，而受管行区间已到第 16 行 —— 合计漏算 2 行」；抛点 `materialize_projection_single_pass:3510 → … → plan_managed_writes:1738`；staged 不存在 |
| D3-2 + {D3-6, D3-4借, D3-4贷}（去掉 D3-5 binding，契约不变） | **同上异常** |
| 对照 D：契约删 `d35-managed` + 不注入 D3-5，D3-2 + {D3-6, D3-4借, D3-4贷} | **同上异常** |
| 隔离：D3-2 + {D3-5} | **抛** `FooterAnchorDriftError`（同 §1 消息），抛点 `materialize_projection_single_pass:3510 → plan_managed_writes:1724`；staged 不存在 ⇒ **D3-5 一个 sibling 就足以让 D3-2 也写不出来** |
| 隔离：D3-2 + {D3-4借, D3-4贷} | materialize OK，verify equivalent=True |
| 单独作 primary：D3-6 / D3-4借 / D3-4贷 / D3-5 | D3-6 抛 C17 `FooterFormulaRangeError`；D3-4 两区 OK（verify 等价）；D3-5 抛 `FooterAnchorDriftError` |

单趟路径里 `_try_single_pass_materialize` 只捕获 `SinglePassDeclined`，计划期抛出的 footer 异常不会回落到逐趟链式，而是直接冒泡（抛点都在 `:3510`）。

🔴 意外发现（超出 D3-5 本身，如实登记）：多 binding 路径里**最先**失败的是 **D3-6**，不是 D3-5。
D3-6 数据区 12-16、footer 17，模板 `C17=SUM(C12:C14)` 只覆盖 3/5 行；`plan_managed_writes:1738` 的
无位移覆盖门对**每次** materialize 都跑，与行数无关 ⇒ D3-6 只要进 binding 集合就恒失败。
（D3-6 的 Task 7 离线判据只做了注入 + `verify_unmanaged_regions(before=after)`，从未跑过 materialize。）

## §3 候选修法 A 可行性（内存改 footer_row=15 / marker=A15 精确文本 / carries_total_formula=False）

做法（全内存，不改文件）：`spec_a = dataclasses.replace(SPEC_D305, footer_row=15, footer_marker=A15, footer_carries_total_formula=False)`；
A15 精确值 `'三、审计说明'`（codepoints `4e09 3001 5ba1 8ba1 8bf4 660e`，无空格）；契约 = `build_contract_payload()` 深拷贝后把 D3-5 table
换成 `_expansion_sheet_row_table_payload(spec_a)` 再 `parse_contract`；substrate 用 `P._instrumentation_of(spec_a)` 重新注入（冻结 `GT_FOOTER_ROW_D35=15`）。
探针：`_probe_2a_materialize.py` / `_probe_2a_supplement.py` / `_probe_2a_counts.py` / `_probe_2a_cache.py`（均已删除）。

| 场景（D3-5 单 binding） | materialize | verify | B/F 合计格 |
|---|---|---|---|
| 2 行（不插行） | OK | equivalent=True | `B14=SUM(B11:B13)` 不变 |
| 3 种子 + 3 新（插 3 行，本段"6 行"口径） | **抛** `excel_workbook_row_change.PropagationDriftError`「xl/worksheets/sheet4.xml：声明 5 处传播，实际只改了 6 处」（`apply_plan_zip_with_report:2356 → _apply_workbook_propagation:2439`） | — | — |
| 6 个全新 rowId（插 6 行） | OK | equivalent=True（清缓存后） | `B20=SUM(B11:B13)`、`F20=SUM(F11:F13)`：**没有扩张**；数据落在 14-19，11-13 是种子空行 ⇒ 合计 6 行全漏 |
| 3 种子 + 4 新（插 4 行） | OK | equivalent=True | `B18=SUM(B11:B13)`：数据在 11-17 ⇒ **漏算 14-17 四行** |
| 同上 + D3-2 primary、D3-5 sibling | OK（`per_table_shift={long_term_rows: +4}`） | equivalent=True | 同上漏算 |

门禁逐项（纯函数同参复刻，插 3 行）：计划期第六类拒绝理由 `assert_footer_formula_covers_managed_rows(footer_row=15, row_shift)` → PASS、checked=[]；
apply 后 `assert_footer_anchor_stable`(→18) + `assert_footer_formula_covers_managed_rows(carries=False)` → PASS、checked=[]；
`shift_sheet_rows(total_formula_rows=())` 下 B17=`SUM(B11:B13)`（只位移不扩张）。⇒ **没有任何门禁拦下"合计漏算新行"**：footer 两道门只看第 15 行，
那一行没有公式；`carries=False` ⇒ `total_formula_rows=()`，不扩张；verify 对照的是冻结的声明，漏算这件事本身就合规。另外读码可见：插行后 verify
按 after 侧 region 行跨度（11..13+c）排除受管列坐标，所以 B14/F14 在 c≥1 时根本不在比对面里（读码结论，没有单独做变异实测）。
读码补充：若 A 改成 `carries=True`，计划期会被 Requirement 5.4 那道门拦下（「声明携带合计公式但第 15 行没有公式」，excel_materialize.py:1547），走不通。

🔴 与修法无关的引擎缺陷（插行时必然遇到）：`附注披露信息(上市公司)`（sheet4）引用 `D3-5!B14/C14/B19/B21/B22`；
`_apply_workbook_propagation` 按声明对做**顺序字符串替换**，前一对的 after 恰好等于后一对的 before 时就会重复命中（如插 3 行：B19→B22，
接着 B22→B25 命中 2 处）⇒ `PropagationDriftError`。插入行数扫描 c=1..9：**c∈{1,2,3,5,7,8} 失败，c∈{4,6,9} 通过**，与撞车条件
（14+c∈{19,21,22}、19+c∈{21,22}、21+c=22）完全吻合。修法 B 在同一处以同一异常失败（c=3），修法 C 也绕不开。这是 fail-closed（零产物），不会静默出错。

探针自身的问题（已排除）：同一进程里对同一份 substrate 先后跑不同插入行数，第二次 verify 报 `managed_sheet_unmanaged_cells` 漂移（41↔40 项）；
清掉 `parse_cache.clear_all_parse_caches()` 后全部 `equivalent=True`。根因：`BEFORE_DIGEST_CACHE` 的键（before_sha|contract|sheet_part|table_key|extra）
不含 region 行跨度，而 before 侧 digest 依赖 after 侧解析出的 region。生产里是否会出现"同一 base 在同一进程里以不同行数连续 verify"没有验证，只登记这一事实。

## §4 先例（last_data_row 与 footer_row 之间隔行的已交付 provider）

命令：临时探针 `_probe_2a_precedent.py`（读 D4 provider 冻结常量 + `D/D4 收入底稿.xlsx` 夹层行 A..T 逐格）与
`_probe_2a_allcontracts.py`（`backend/data/workpaper_sync_contracts/*.json` 全部 11 份 × 各自模板：对每张带 `footer_anchor`
的动态行 table，按 `strip()==marker` 找 marker 行，再找"位于数据首行与 marker 行之间、SUM 区间覆盖数据首行、且区间止于本行之上"的行），均已删除。

指定的两个候选：

| provider | 声明 | 夹层实测 | 专门处理 |
|---|---|---|---|
| D4-25 `phase5_d4_ipo_checklist_sheets.py` | 12..21 / footer 23 / `'三、审计说明：'` / carries=False | R22 **全空**（R21 只有 A 列序号 10），全表无任何 SUM 触及数据区 | 无；契约 note 只写「受管区下边界（插行须下移）」 |
| D4-17 `phase5_d4_cutoff_forward_sheet.py` | 13..23 / footer 36 / `'三、审计说明'` / carries=False | R24 `A24='截止日期：202X年12月31日'`，R25..35 全空，全表无 SUM 触及数据区 | 无 |

D4 契约里全部 gap>1 的 spec（10 个）逐一核对夹层：D4-26/D4-27/D4-18 为空行；D4-32 夹层 `A47='……'`（占位文字，无公式）；D4-20PROV 夹层 R30 空；
D4-5/D4-31 是说明/问卷型大段文字（marker 是后续小标题）；**D4-3（18/20）夹层行 19 是一条数据行**（`A19='……'` + 逐行公式），
合计行 20 自己带 `A20='合计'` + `B20=SUM(B13:B19)`，marker 就在合计行上、`carries=True`——这是"合计 marker 与合计公式同行"的常规形态，不是夹层。

全量扫描结果（数据首行取各字段 `source_ref` 的最小行号；判据放宽为「marker 行之上存在 SUM 区间末行落在 [数据首行, 本行) 的行」，两轮一致）：
53 张带 footer_anchor 的动态行 table，**夹层合计行命中 0**；marker 在模板上找不到的只有 1 张 = D3-5 `long_term_rows`。

⇒ **没有先例**是"合计公式行夹在数据区与文字 marker 之间"。所有 `carries=False` 的隔行先例，夹层里都没有公式合计，
"插行后合计不漏算"这个问题在它们身上根本不存在，所以也没有任何可以照搬的处理办法。所有 `carries=True` 的表，marker 都和合计公式在同一行
（D3-2 A24 / D3-6 A17 / D3-4 借 A17 / D4-3 A20 等）。

## §5 D3-7 预检（合计行 27 / 39 的 A~R 精确文本 + 下方最近文字标签）

命令：临时探针 `backend/_probe_2a_templates.py`（openpyxl `data_only=False`，逐格 A..R），
`..\.venv\Scripts\python.exe _probe_2a_templates.py _probe_2a_templates.json`（cwd=backend）。

sheet「预收账款检查表D3-7」（max_row=48）实测：

| 行 | A~R 非空格（精确 repr） |
|---|---|
| 27 | `A27='合计'`、`G27='=SUM(G17:G26)'`、`H27='=SUM(H17:H26)'`（其余 None） |
| 28 | `A28='（2）期后结转检查'` ← 区①合计行下方最近文字标签 |
| 39 | `A39='合计'`、`G39='=SUM(G31:G38)'`（其余 None；H39:I39 为合并格，值 None） |
| 40 | `A40='三、审计说明：'` ← 区②合计行下方最近文字标签 |

- 两个合计行 A 列都是精确的 `'合计'`（纯两字，与 `text.strip()=="合计"` 可匹配）⇒ D3-7 **不存在** D3-5 的"A 列无 marker"问题。
- 区①合计行还有 `H27=SUM(H17:H26)`（不止 G27）。
- 顺带登记（Task 11 相关，只报告）：`F42='=G27'`、`F43='=H27'`、`F44='=G39'` 引用两个合计行；`E42/E43/E44` 跨 sheet 引用 `'预收账款明细表D3-2'!M24/N24/T24`（D3-2 footer 行）。区②数据行 31-38 的 H:I 逐行合并（`H31:I31`…`H38:I38`），表头 `H29:I30` 合并。

## §6 D7-5 交叉检查（合同负债 D7 模板合计行 A 列）

模板 `backend/wp_templates/D/D7 合同负债.xlsx`，sheet「账龄1年以上合同负债检查表D7-5」（max_row=20），同一探针实测：

- 几何与 D3-5 逐格同型：表头 R10（`A10='客户名称'`，D3-5 是 `'对方单位名称'`，B10..H10 相同），`B14='=SUM(B11:B13)'`、`F14='=SUM(F11:F13)'`，**A14 为空**。
- A 列非空只有行 1~8、10（'客户名称'）、15（`'三、审计说明'`）、19（`'四、审计结论'`），**整列没有「合计」**。
- 结论：D7-5 与 D3-5 同样没有可供 `_find_marker_row` 命中的「合计」文字，同一阻塞同样成立。

## §7 修法可行性对照（只列事实，不做裁决）

"实测"指离线 adapter 端到端跑过（本文 §1/§3）；"读码"指只读了代码没跑。所有插行场景都会碰到 §3 的 sheet4 传播撞车
（`PropagationDriftError`，插入行数 c∈{1,2,3,5,7,8} 失败），这个缺陷与选哪种修法无关，下表"插行后"一栏取 c∈{4,6} 的实测结果。

| 修法 | 能不能跑通 | 插行后合计会不会漏算 | 改动面 |
|---|---|---|---|
| A footer 下移到 A15「三、审计说明」+ carries=False | 实测：2 行 OK；插 4/6 行 OK、verify 等价；插 3 行抛 `PropagationDriftError`（与 A 无关） | **会漏算，而且没有门禁拦**：`B/F` 合计保持 `SUM(B11:B13)`，只跟着行位移，不扩张；footer 两道门看的是 15 行（无公式），`total_formula_rows=()` | 最小：只改 `phase5_d3_05_long_term.py` 的 3 个常量 + 重生成契约 JSON；不改模板、不改框架。代价：把一张会静默漏算的底稿当成合规产出（D3-4 借方区已有同类已知边界，见 `test_d3_04`） |
| B 改模板，在 A14 补「合计」 | 实测（内存补 inlineStr，契约不变）：2 行 OK；插 4/6 行 OK、verify 等价；插 3 行同样抛 `PropagationDriftError` | **不漏算**：插 6 行后 `B20=SUM(B11:B19)` / `F20=SUM(F11:F19)`；插 4 行后 `SUM(B11:B17)`。反例：不扩张时 apply 后门禁会抛 `FooterFormulaRangeError`（实测），说明门禁在守 | 模板哨兵 `TEMPLATE_SHA256`（entry 模块 + 契约 JSON `template_sha256` / `normalized_structure_hash` / `template_definition_sha256`）要更新；`tests/_snapshots/wp_templates_baseline.json`、`workbook_row_change_zero_regression_baseline.json`、golden digest 基线、manifest slice 的 sha 都要重取（读码，没逐一验证是否都会红）；另外要确认修改 `backend/wp_templates/` 权威模板是否被允许（入口 docstring 写明运行时只读，离线更新属另一回事）。D7-5 同样缺「合计」，对称处理时要再改一份模板 |
| C 扩展框架：支持没有文字的合计行锚点 | 读码：`FooterAnchorSpec` 只有 marker/search_column/carries；解析层 CS-12 明令禁止 `row`/`row_index`/`row_number` 键（`contracts.py:1038`）；`_find_marker_row` 只按文本匹配。需要新增一种不写死行号的定位方式（例如"search_column 上第一个含 SUM 且覆盖数据区的行"），并同步到 `assert_footer_anchor_stable`、`_plan_row_shift`、两相门禁 | 读码推断：只要冻结行仍是 14 且 `carries=True`，扩张逻辑（`total_formula_rows=(14,)`）与 B 相同；纯函数实测 `shift_sheet_rows(total_formula_rows=(14,))` 得到 `SUM(B11:B16)` | 最大：共享内核（contracts 解析 + excel_materialize 两处定位 + CS-12 规则说明）+ 回归面覆盖 11 份契约 53 张 footer 表；还要新写判据。D7-5 可以直接复用 |
| D D3-5 暂不接入（`_INCLUDE_D305_LONG_TERM=False`） | 实测（契约删 `d35-managed` + 不注入 D3-5）：D3-2 + {D3-6, D3-4借, D3-4贷} 仍抛 `FooterFormulaRangeError`（C17，来自 D3-6，与 D3-5 无关）。D3-2 单 binding OK 是在**现状契约**下实测的（§2.1），D 契约下没有单独跑；D3-2 + D3-4 双区 OK 也是现状契约下的结果 | 不适用（D3-5 不受管） | 小：翻开关 + 重生成契约 JSON；`test_d3_expansion.py`（`managed_row_table_specs` 断言、`_STAGE2_STORE_ITEMS` 含 `D3-lt-rows`、`d35-managed` 对齐守卫用例）和 `test_d3_property3_4_dual_zone_baseline.py`（`"d35-managed": 1`）要跟着改 |

另外两条与 A~D 选择无关、但会影响后续决策的事实：

1. D3-6 进入任何 materialize 都会失败（§2.2），原因是模板 `C17=SUM(C12:C14)` 只覆盖 5 行数据区中的 3 行。这个阻塞独立于 D3-5，D3-2 + D3-4 双区作 sibling 时实测可以跑通。
2. 真实流程今天既不注册 D3 adapter，也不会带 sibling、不会注入扩容面（§2.1），所以以上结论都是离线驱动得出的；真栈端到端仍如实标注为不可测。
