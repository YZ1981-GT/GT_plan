# C1 簇：能力翻转失效的「冻结负向快照」（29 节点）

> 采集日 2026-09-07（会话内实测）。`cwd=backend`，解释器 `..\.venv\Scripts\python.exe`，
> 每文件单独 `-q --tb=short -rf -p no:randomly`。**未**跑整个 `tests/workpaper_sync`。

## 一、根事件（已确立，不在本文重新推导）

已推送 commit `cd9592ff5` + `ebc6e1b92`（D4 → `useD4SyncMode`）与 `42d2f6e6f`（D2 pilot → 统一路径）。
活体实测（`backend/scripts/_c1_probe.py`，用完即删）：

```
total 155                     # 176 → 155，减 21 条，全是 xlsx/d4/**，0 新增
Counter({'single_onlyoffice': 145, 'single_html': 5, 'bidirectional': 4, 'unreachable': 1})
xlsx/gt-d2-accounts-receivable    |cap= bidirectional |adapter= d2.receivable_detail        |mig= adapter_registered
xlsx/gt-h1-fixed-assets           |cap= bidirectional |adapter= h1.disposal_check           |mig= adapter_registered
xlsx/gt-g7-long-term-equity-main  |cap= bidirectional |adapter= g7.soe_subsidiary_disclosure|mig= adapter_registered
```

`registry.DELIVERED_PER_ENTRY_CONTRACTS` 三条 pilot 行已是 `adapter_registered: True`，
且 `reason` 逐字记载「顺序门仍然成立且未被绕过：capability 裁决是 finalize **之后**的
reviewed overlay 动作」。**判读**："今天没有 bidirectional entry" / "capability 未启用" /
"四个 pilot 都被 finalize 挡住" 这些负向快照已到期；`test_registration_is_refused_while_
manifest_says_single_onlyoffice` 的前提被 manifest 直接否证。

## 二、分类口径

| 类 | 含义 | 处理 |
|----|------|------|
| **A** | 快照到期，不变量仍成立 | 把断言从「冻结的population/计数」改成**活体派生**，牙齿不丢 |
| **B** | 断言的全部用途就是记录一个临时前置条件，而它今天真被满足了 | **反转成后置条件**（断言已启用 **且** 启用经由必需的门），不是删 |
| **C** | 真正的顺序/fail-closed 守卫，红是别的原因 | 修那个原因，不动守卫 |

**贯穿全簇的承重属性 = 顺序不可交换（ordering is not commutable）**：finalize 之前不得注册
adapter。所有改动后必须仍能被变异打红。

## 三、29 行分类表

| # | 节点 | 类 | 活体事实 | 动作 |
|---|------|----|---------|------|
| 1 | `test_task39_pilot_harness.py::TestPilotClassCoverage::test_no_class_is_verified_today_because_there_is_no_bidirectional_entry` | A | d2/h1/g7 各 1 条 bidirectional；但 `verified_entry_ids` 仍全空 ⇒ 四类仍 unverifiable | 去掉 `bidirectional_entry_ids == ()` 的钉死，改断言「capability 旗标本身不产生 verified」：逐类 `verified_entry_ids == ()` + 活体 bidirectional 集合与 manifest 派生一致 |
| 2 | `test_task41_...::TestUpstreamDebtsAreVisibleFacts::test_dynamic_family_is_structurally_unreachable_for_every_xlsx_entry` | A | `total=155`（钉死 186） | `total` 改为活体 `len(manifest["entries"])`；保留 `xlsx_dynamic == ()` 与 `dynamic == ("docx/gt-wp-renderer",)` |
| 3 | `test_task41_...::TestOrderingGate::test_capability_is_not_enabled_before_finalize` | B | 活体 `capability=bidirectional` + `adapter_id=d2.receivable_detail` | 反转成后置条件：断言已启用 + 顺序门放行；并保留否证臂（替换成 single_onlyoffice 的 manifest ⇒ 门必抛） |
| 4 | `test_task41_...::TestOrderingGate::test_capability_predicate_agrees_with_the_ordering_gate` | A | `manifest_capability_enabled()` 活体为 True | 双向对齐改成「活体 ⇒ 两侧都 True；替换 manifest ⇒ 两侧都 False/抛」 |
| 5 | `test_task41_...::TestOrderingGate::test_attach_is_a_no_op_before_enablement_and_never_raises` | A | 已启用 ⇒ attach 会真读库，`session=None` 触 AttributeError | 用 monkeypatch 把 pilot 模块的 `load_entry_manifest` 换成**未启用** manifest，property 原样保留（返回 `()` 且一次库都不读） |
| 6 | `test_task41_...::TestOrderingGate::test_ledger_records_adapter_not_registered_yet` | B | 登记表该行 `adapter_registered=True` | 反转成后置条件：`is True` + `reason` 必须记载 finalize 在前的顺序证据 |
| 7 | `test_task41_...::TestOrderingGate::test_registration_is_refused_while_manifest_says_single_onlyoffice` | A | 前提被 manifest 否证；现失败于 `object()` 无 `.state`（走到了 bundle 判据） | registry 用**替换后的** single_onlyoffice manifest 构造，capability 拒绝重新成为被测判据 |
| 8–12 | `test_task42_h1_...` 同名 5 条（4×TestOrderingGate + dynamic-family） | 同 3/4/5/6 + 2 | 同上（entry=`xlsx/gt-h1-fixed-assets`, adapter=`h1.disposal_check`） | 同上 |
| 13–17 | `test_task43_g7_...` 同名 5 条 | 同 3/4/5/6 + 2 | 同上（entry=`xlsx/gt-g7-long-term-equity-main`, adapter=`g7.soe_subsidiary_disclosure`） | 同上；attach 一条本就用 `ExplodingSession()`，替换 manifest 后该哨兵重新生效 |
| 18 | `test_task44_...::TestFinalizeStateIsReadFromProduction::test_all_four_pilots_are_blocked_before_task_36_finalize` | **B** | 三个 pilot `capability_enabled=True`、`admitted=True` | 见 §四 |
| 19–21 | `test_task44_...::test_each_signal_flips_independently_under_substitution[d2_large_json / g7_two_level_dynamic / h1_grouped_dynamic]` | **A** | `baseline.admitted` 活体为 True | 见 §四 |
| 22 | `test_task44_...::test_the_four_pilots_short_circuit_at_different_gates` | **A** | `reads[simple_checklist]=0`（其余 3 个=1） | 见 §四 |
| 23 | `test_task44_...::test_the_stub_session_is_the_only_substituted_part` | **A** | `session.calls == 0` | 见 §四 |
| 24 | `test_task44_...::test_gate_probe_admission_is_state_sensitive_passes_for_all_four` | **A** | `real_admitted` 活体为 True | 见 §四 |
| 25 | `test_task44_...::TestOrderingIsNotCommutable::test_upstream_gap_is_failed_not_unverifiable` | **A** | `len(rows)=16`（钉死 28） | 见 §四 |
| 26 | `test_task44_...::TestValidatorsAreBidirectionallyReachable::test_no_probe_can_pass_on_the_real_unadmitted_pilots` | **A** | d2 的 `scenario.identity_retention` 已 `passed` | 见 §四 |
| 27 | `test_task44_...::TestReportIsClosedAndMeasured::test_blocking_conditions_keep_the_black_box_fact_visible` | **A** | `finalize_blocked=4`（钉死 16） | 见 §四 |
| 28 | `test_task61_...::TestAdmissionIsRealReadback::test_no_f2_entry_is_admitted_today` | **A** | 红在 `stale_reasons=('source_commit 变化: 记录 d330d7cea6bb 现读 fb7a0ace211f',)` | 见 §5.2（**判 A，非 C**：只有环境指纹轴到期，载体裁决逐字未变） |
| 29 | `test_task75_...::TestRealRun::test_three_pilots_are_all_verified_or_environment_unavailable` | **C** | 红在 `ImportError: cannot import name 'neutralize_oo_crash_if_formulas'` | 见 §5.1（**确认 C，已修**：函数体从未随任何 commit 落地） |

## 四、task44 门（10 节点）

> 采集日 2026-09-07（续采）。`cwd=backend`，`..\.venv\Scripts\python.exe -m pytest
> tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py -q --tb=short -rf -p no:randomly`。
> **BEFORE（实测，不采信上文表格的数字）：`12 failed, 99 passed`（303.30s）**。
> 12 红里 10 条正是本簇第 18–27 行；另 2 条属 §六（见该节末两行补记）。

### 4.1 活体派生值（本节所有改写的取数依据）

`collect_pilot_facts` × 4 pilot 实测：

| pilot | entry | capability_enabled | admitted | adapter_registered | request_path 注册 | attach_session_reads |
|---|---|---|---|---|---|---|
| simple_checklist | `xlsx/b60/gt-b60-bundle` | **False**（`single_onlyoffice`） | **False** | False | d2/d4/g7/h1 | **0** |
| d2_large_json | `xlsx/gt-d2-accounts-receivable` | True | **True** | False | 同上 | **1** |
| h1_grouped_dynamic | `xlsx/gt-h1-fixed-assets` | True | True | False | 同上 | 1 |
| g7_two_level_dynamic | `xlsx/gt-g7-long-term-equity-main` | True | True | False | 同上 | 1 |

`build_report()` 实测：`total_rows=173`（42×4 + 5 条 gate 行）、
`result_counts={failed:16, unverifiable:152, passed:5}`、
`blocking_condition_distribution={finalize_blocked:4, pilot_not_admitted:38,
real_black_box_not_executed:56, oracle_upstream_debt:8, schema_unrepresentable:4,
enumerated_scenario_not_in_required_set:4, execution_record_missing:168,
evidence_input_missing:168}`、`upstream_gap` 行 **16** 且 `{result}=={"failed"}`
（逐 pilot：simple 7 / d2 3 / h1 3 / g7 3）。
`PER_PILOT_PROBES=42`（其中 `probe_class=="admission"` **4** 条）。

🔴 **本节最重要的一条新事实**：`attach_session_reads` 与上文 §三 第 22 行记载的
**恰好相反**。§三 记「reads[simple_checklist]=0，其余=1」，而**判据本身**断言的是
`simple_checklist >= 1` 且其余 `== 0`。两者对照说明：capability 翻转把「谁在
capability 门短路」这件事**整体调了个头** —— 今天是未启用的 simple_checklist 在门上
`return ()` 零读库，已启用的三个过门后继续查 `entry_state`（各 1 次）。属性没变，
population 换了边，是标准 (A)。

### 4.2 逐节点分类与动作

| # | 节点 | 类 | 到期的是什么 | 改写后的判据（承重部分） |
|---|------|----|-------------|------------------------|
| 18 | `test_all_four_pilots_are_blocked_before_task_36_finalize` | **B** | 「四个都还被 finalize 挡着」这个**临时前置条件**，对 d2/h1/g7 真被满足 | 反转成后置条件：启用/未启用的划分**从活体 manifest 派生**（不写死 pilot 名）；对已启用的逐个断言 `capability_enabled ⇔ capability_of(entry) is bidirectional` + `adapter_id` 已写回 + `migration_state=="adapter_registered"`（三者缺一即"跳过顺序"）；**否证臂**：退回 finalize 之前的 manifest ⇒ `assert_manifest_capability_enabled` 必抛 `manifest capability` 且谓词必为 False。与 Task 43 第 3 行同口径 |
| 19–21 | `test_each_signal_flips_independently_under_substitution[d2 / g7 / h1]` | **A** | `baseline.admitted is False` 这个前提 | 用第 5/13–17 行验证过的形状：`monkeypatch` pilot 模块的 `load_entry_manifest` 换成退回未启用的 manifest ⇒ 四个 pilot 的 baseline 重新统一为未准入，**下面整段逐信号翻转判据一字未改**；另加一条 `baseline.capability_enabled is False` 自检（取证输入若失效则当场打红，不让它静默退化） |
| 22 | `test_the_four_pilots_short_circuit_at_different_gates` | **A** | 「谁在哪道门短路」的 population（两边角色互换，见 4.1） | 划分从活体 `capability_enabled` 派生：未启用 ⇒ `reads == 0`（capability 门 `return ()`，Task 41 那次 500 之后的形态）；已启用 ⇒ `reads >= 1`（过门后必须继续查 `entry_state`）。两臂各加"样本非空"断言，防止哪天全启用/全未启用时本条静默变空 |
| 23 | `test_the_stub_session_is_the_only_substituted_part` | **A** | 取证对象选错了边（`session.calls>=1` 只在已启用时可得） | 改取一个**活体已启用**的 pilot；`attach_pilot_adapters.__module__ == ref.module_path`（函数体是生产的）与 `session.calls >= 1`（真跑到读库那步）两条承重判据一字未改 |
| 24 | `test_gate_probe_admission_is_state_sensitive_passes_for_all_four` | **A** | `real_admitted is False` 当成四个 pilot 的共同快照 | `real_admitted` 改与活体 capability 对齐；承重改由探针**自己做的两条反事实**承担：`substituted_admitted is True`（喂满 ⇒ 准入）+ `starved_admitted is False`（饿掉 ⇒ 不准入）+ `flipped is True`。比原来的单向快照更难装饰 |
| 25 | `test_upstream_gap_is_failed_not_unverifiable` | **A** | 只有 `len(rows)==28` 这个钉死值；`{result}=={"failed"}` **今天仍成立** | `{"failed"}` 原样保留；行数改成活体派生：`len(rows) == finalize_blocked + oracle_upstream_debt + enumerated_scenario_not_in_required_set`（`debt is not None` 分支只有这三个来源，而 `schema_unrepresentable` 在它**之前**裁决 ⇒ 三者之和恰等于行数，谁把两个分支对调本条当场红）；另逐行断言必带 debt 来源且 `notes` 非空。历史 28→16 写进注释（precedent：`>=175` → `>= len(entries)*9//10`） |
| 26 | `test_no_probe_can_pass_on_the_real_unadmitted_pilots` | **A** | 分母：d2/h1/g7 已准入，它们给齐记录后判 `passed` 是**设计行为** | 臂一收窄到活体真未准入的那批（原判据一字未改）；臂二把**每个** pilot 用 `replace()` 构造回未准入态（`capability_enabled=False`，与顺序门被拒时的真实信号同形）再跑一遍 ⇒「未准入 ⇒ 一条都不许 passed」仍覆盖四个 pilot，不因分母收窄而变薄 |
| 27 | `test_blocking_conditions_keep_the_black_box_fact_visible` | **A** | `finalize_blocked` 16→4、`pilot_not_admitted` 152→38（只对**仍未准入**的 pilot 生效）；`real_black_box_not_executed==56` / `enumerated==4` **未变** | ①分布不是第二份统计：逐 condition 断言「带它的行数 == 分布里的计数」；②承重原话：黑盒行里**必须存在** `error_code` 被别的码占走的行（否则"事实不丢"这条压根没被考验）；③两条随准入态变化的计数按 `未准入 pilot 数 × 每类 probe 条数` 现推（`4×1=4`、`38×1=38`） |

**分类小计（§四）**：A × 9、B × 1、C × 0。

### 4.3 变异验证：顺序不可交换仍然有牙（本轮最重要的一项）

三次变异，逐次改生产/门源码 → 实测打红 → **逐字还原**（还原后 `git diff` 只剩本树原有的
未提交改动，无 `MUTATION` 残留）。**未**用 `git stash` / `checkout --` / `reset`。

| 变异 | 改了什么 | 期望 | 实测打红节点 |
|---|---|---|---|
| **M1** | `pilot_g7.assert_manifest_capability_enabled`：`if False and capability is not bidirectional` —— 摘掉 **capability 那颗牙** | 顺序门被绕 ⇒ 红 | **2 红**：第 18 行（本轮改写）+ Task 43 `test_capability_is_not_enabled_before_finalize`（第 13 行）。<br>🔴 顺带量出一件好事：第 19–21 行**没红**，因为顺序门有**两颗独立的牙**，`adapter_id` 那颗还在（退回形态把 `adapter_id` 置 None，它照样抛）—— 这正是「两条独立判据」的设计在起作用 |
| **M1b** | 在 M1 之上再摘掉 `adapter_id` 那颗牙 ⇒ **finalize 之前真的注册得上了** | 全线红 | **5 红**：第 18 行、第 19–21 行的 `[g7_two_level_dynamic]`、Task 43 的 `test_capability_is_not_enabled_before_finalize` / `test_capability_predicate_agrees_with_the_ordering_gate` / `test_attach_is_a_no_op_before_enablement_and_never_raises`（attach 不再短路 ⇒ `ExplodingSession` 如实炸） |
| **M2** | 门的 `evaluate_probe`：把 `finalize_blocked` 与 `pilot_not_admitted` 两条 blocking 同时短路 ⇒ **未准入的 pilot 能让 probe 通过** | 红 | **2 红**：第 26 行（未准入却有 probe 判 passed）+ 第 27 行（派生计数对不上）。<br>第 25 行**未**红 —— 它的恒等式在此变异下自洽（`0+8+4=12` 仍等于剩余 upstream_gap 行数），故补做 M3 证明它不是同义反复 |
| **M3** | 门的 debt 分支返回值 `RESULT_FAILED` → `RESULT_UNVERIFIABLE` | 红 | **1 红**：第 25 行 —— 承重那句「upstream_gap 必须是 failed，不得降级成 unverifiable」确有牙 |

**结论**：「finalize 之前不得注册 adapter」这条承重属性在改写之后**仍可被变异打红**，
且打红点分布在 task44 与 task43 两层（门 + pilot 守卫），不是单点。第 18 行的否证臂
（退回 single_onlyoffice 的 manifest ⇒ 门必抛）是它在 capability 翻转之后仍可测的原因。

### 4.4 §四 AFTER

`12 failed, 99 passed` → **`2 failed, 109 passed`**（418.88s）。10 条全绿。
残留 2 红均**不属**本簇 29 行（详见 §六 补记）。

## 五、疑 C 两节点

### 5.1 第 29 行 `test_task75_...::TestRealRun` —— 确认 **C**，真实代码缺陷，已修

**BEFORE**：`2 failed`（与第 28 行同批测量）；红在
`ImportError: cannot import name 'neutralize_oo_crash_if_formulas' from
'app.services.workpaper_sync.pilot_g7_two_level_dynamic'`。

**根因（不是改名、不是搬家、不是删除 —— 是从未落地）**：

* `adapters/excel.py` 在 `materialize` 与 `verify_unmanaged_regions` 两处、共 **4 个**
  引用点 import 它（`adapter_id == "g7.soe_subsidiary_disclosure"` 分支内的延迟 import）。
* `git show HEAD:...pilot_g7_two_level_dynamic.py | Select-String neutralize` → **零命中**；
  `git log -S "def neutralize_oo_crash_if_formulas" --all -- ":(glob)backend/**/*.py"`
  → **零命中**；`git log -S "def neutralize" --all -- ":(glob)backend/**/*.py"` → 同样零命中。
  ⇒ **函数体从未随任何 commit 落地**。
* 引用点来自 commit `82f58ea44`（`feat(d4-ipo)`，2026-09-13），该 commit 在这两个文件里
  **只改了 `excel.py`**（`1 file changed, 295 insertions`），父提交两侧都无此符号。
  `git status --porcelain` 对这三个文件全空 ⇒ 这是**已提交**的坏 import，不是谁的工作树脏数据。
* ⇒ HEAD 上 G7 整条 materialize / verify 路径带着一个 `ImportError` 在跑。

**修法（按已被真实 OO 栈验收过的口径补齐生产函数，不是 stub）**：
口径真源 = `.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
evidence/g4-1-g7-host-unified-path/README.md` §「本轮修复」第 2 条 —— **zip 级剥离裸
`IF()` + 丢 `calcChain`；检测用 OOXML 词界 IF（忽略 SUMIF/COUNTIF）；verify_unmanaged
对比前同样 neutralize**（该目录 2026-09-11 记录 Playwright `1 passed` + `cs_error=0`）。
成因诊断见 `docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md`：
OO 9.4 在文档加载**完成之前**就跑依赖图计算，`cIF.Calculate` 读 `tocBool` 抛 TypeError
⇒ 前端收 `editor_error_-82`（容器 healthy、sdk 已加载 ⇒ 不是"OO 不可用"，是这份文档的
内容让 OO 崩了）。

在 `pilot_g7_two_level_dynamic.py` 落地 `neutralize_oo_crash_if_formulas(path) ->
tuple[str, ...]`（+ `_strip_bare_if_cells` / `_repack_dropping` 两个私有件）：

1. 每张 `xl/worksheets/*.xml` 里含**词界** `IF(` 的 `<f>` 整个摘掉，`<v>` 缓存值留着
   （摘的是让 OO 崩的**计算**，不是格子里的**数**）；
2. 丢 `xl/calcChain.xml`，并把 `[Content_Types].xml` 的 Override 与
   `xl/_rels/workbook.xml.rels` 的 Relationship 一并摘干净（悬空引用会让 Excel 报需修复）；
3. 共享公式主格命中 ⇒ 同 `si` 的从格一起摘（防御：实测本册 shared 计数为 0）；
4. **幂等**：第二遍返回 `()` 且一个字节都不写 —— 这是 verify 侧能用同一口径比
   before/after 的前提（否则"清 IF"会被判成 unmanaged 公式漂移，commit 永远进不去，
   OO 继续吃带 IF 的 published 表示 → 又是 -82）；
5. zip 重写保留每个部件的 `date_time` / `compress_type` / 属性位，**不过 openpyxl**
   （openpyxl 全量重写会丢部件、把共享公式展平、把缓存值写成 `<v></v>` ——
   `excel_sheet_visibility` 模块头记着这笔实测账）。

**实测依据（写函数前先量的真实模板）**：`wp_templates/G/G7 长期股权投资.xlsx`
（263,335 字节）里裸 IF 格 **1065** 个、分布在 13 张 sheet、**全部带 `<v>`**、
`shared` 计数 **0**、`calcChain` 本来就**不存在**。

**防御测试**：新增 `backend/tests/workpaper_sync/test_g7_oo_crash_if_neutralize.py`
（**19 passed**）—— 4 个引用点仍在 + 延迟 import 真能解析（就是本行红的那条）；
词界检测 12 个 parametrize 例（`IF(` / `IF (` / `SUM(IF(` / `IFERROR(IF(` 命中；
`SUMIF` / `COUNTIF` / `AVERAGEIF` / `IFERROR` / `IFS` / `IFNA` / `_xlfn.IFS` 不命中）；
共享组只摘同 `si`；真实模板上裸 IF 清零 + 部件集只许少 `calcChain` + openpyxl 仍可打开
22 张 sheet + **逐字节幂等**；`calcChain` 现造一个出来验「丢部件 + 清悬空引用」。

**AFTER**：`test_task75_entry_adapter_roundtrip.py` 整文件 **10 passed, 0 failed**。

### 5.2 第 28 行 `test_task61_...::test_no_f2_entry_is_admitted_today` —— 判 **A**，不是 C

**BEFORE**：红在 `assert signals.carrier.really_passed is True`，
`stale_reasons=('source_commit 变化: 记录 d330d7cea6bb 现读 fb7a0ace211f',)`。

**活体实测（`probe_carrier_gate()`）**：

| 轴 | 记录 | 现测 | 判定 |
|---|---|---|---|
| probe 模板 digest（3 份） | — | — | **零漂移** |
| `oo_build` | `9.4.0-129` | `9.4.0-129` | **相等** |
| `source_commit` | `d330d7cea6bb…` | `fb7a0ace211f…` | **唯一一条 stale** |
| `carriers_allowed` | — | `field_sdt_inline` / `field_sdt_block` / `sdt_external_body` | 未变 |
| `carriers_blocked` | — | `row_sdt` | 未变 |
| `anchors_allowed` | — | `("w_tag",)` | 未变 |

**裁决**：`really_passed` 是「**新鲜** ∧ 裁决通过」的合取，而它的新鲜度轴之一是
「记录的 `source_commit` == 当前 HEAD」—— 那条轴**每提交一次就失效一次**。
本节点测的命题是「F2 未准入的原因是**供给**，不是 Task 6 载体门」，所以：

* **不是 C**：没有"别的原因"要修 —— 载体裁决的实体结论一个字没变。
* **不重新记录**：`backend/data/onlyoffice_word_sdt_carrier_contract.json` 记的是一次
  **真实 OO 9.4 + 真实浏览器**的 probe run（`runner: scripts/diagnose/probe_oo94_word_sdt.py`、
  `runner_run_id: task6-r1`、captured 2026-08-24）。不重跑 probe 而只把 `source_commit`
  改成 HEAD，等于**编造**"这份载体证据是在 HEAD 上取的" —— 这正是本仓库铁律里的假绿；
  且该文件属治理数据，按本轮规则不得手改。
* **判 A**：到期的是**冻结的环境指纹**，命题本身仍成立且可重新表达。

**改写后的判据**（替掉那一行，三条都带否证力）：

1. 三类载体 + `row_sdt` 阻断 + `anchors_allowed == ("w_tag",)` **逐字未变**（改任一项即红）；
2. 3 份 probe 模板 digest **零漂移**，且 `recorded_oo_build == observed_oo_build`；
3. `stale_reasons` 里**除**「`source_commit 变化`」之外必须**一条都没有** —— 模板丢失 /
   digest 漂移 / OO build 变化任一出现即真实失效，照旧打红。

**"stale 这件事"没有被吞掉**：门自己在 `evaluate_probe` 里把它记成阻断项
`carrier_gate_not_really_passed`，并把 `stale_reasons` 原文写进 `notes`
（`check_task61_oo94_word_pilot_gate.py`）⇒ 黑盒事实仍可见、仍非零退出。

**残留真实欠账（带 owner）**：重采 Task 6 载体证据至当前 HEAD —— 需**真实 OO 9.4 容器 +
真实浏览器**跑 `backend/scripts/diagnose/probe_oo94_word_sdt.py`，属**外部依赖**；
owner = Task 6 载体门（F2 word pilot 线）。本轮不做，也不假装做了。

**AFTER**：`TestAdmissionIsRealReadback` **24 passed, 0 failed**。同文件的
`TestBindingConstraintIsMeasured::test_the_three_arms_really_run_against_the_database`
属真实库簇，按指令**未触碰**；本轮全程未跑任何 `*_pg.py`。

## 六、同文件其它簇的失败（记录以免重复计数，本次不追）

| 文件 | 节点 | 归属线索 |
|------|------|---------|
| test_task42 | `TestFrozenEntrySelection::test_entry_is_the_only_h1_candidate_in_the_harness_assessment` | 同形冻结快照，但不在本簇 29 行清单 |
| test_task42 | `TestFrozenEntrySelection::test_required_set_digest_is_this_entry_own` | digest 漂移 |
| test_task42 | `TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger` | 同形（`adapter_registered is False`），不在清单 |
| test_task42 | `TestUpstreamRelsAndNamespaceDefectsAreFixed::test_ten_of_the_authoritative_workbooks_share_this_shape` | 模板盘点计数 375 vs 369 |
| test_task42 | `TestPilotIntroducesNoResolverDebt::test_no_function_in_this_module_is_classified_as_writer_or_resolver` | writer 盘点计数 371 vs 327 |
| test_task43 | `TestFrozenEntrySelection::test_class_really_has_three_candidates` | 同形冻结快照，不在清单 |
| test_task43 | `TestContractIsGroundedInTheTemplate::test_contract_is_registered_in_the_delivery_ledger` | 同形，不在清单 |
| test_task43 | `TestUpstreamRelsAndNamespaceShapesStillHold::test_ten_authoritative_workbooks_share_this_shape` | 模板盘点 `.xlsx` 352 vs 351 |
| test_task44 | `TestScenarioDenominatorIsBidirectional::test_close_predicate_is_cross_checked_against_the_raw_manifest` | 同形（`capability != "bidirectional"`），不在清单 |
| test_task44 | `TestGateAddsNoProductionModule::test_writer_inventory_is_still_fresh` | generated artifact drift（`workpaper_writer_inventory.json` stale） |
| test_task61 | `TestBindingConstraintIsMeasured::test_the_three_arms_really_run_against_the_database` | 同形（`registered_adapter_ids == []`），不在清单 |

> 另有三处硬钉 `observed["total"] == 186` 位于 test_task41/42/43，**正是本簇第 2/8–12/13–17 行**，已在范围内。

**本轮（§四/§五）补记的 task44 残留 2 红**，两条都**不属**本簇 29 行，未追：

| 节点 | 实测 | 归属线索 / 交接 |
|------|------|----------------|
| `TestGateAddsNoProductionModule::test_writer_inventory_is_still_fresh` | `generator.main(["--check"]) == 2`；`[FAIL] stale generated inventory: backend\data\workpaper_writer_inventory.json no longer matches source facts`（source 侧现测 `rows=371 writers=312 resolvers=84`） | 已在上表登记的 generated artifact drift。产物文件按本轮规则**不得手改**，重生成属清册线，交 **Task 20 收口门 / writer 清册** owner |
| `TestGateAddsNoProductionModule::test_no_workpaper_sync_production_module_references_task_44` | `offenders == ['word_instrumentation.py']` | **上表原先没有这一行，本轮新登记**。查明是**文档字符串交叉引用**而非 task44 接线：`word_instrumentation.py` 的 `_normalize_eol` 注释里把 `scripts/gen/generate_workpaper_task44_pilot_probe_registry.py` 与 `scripts/check/check_task44_oo94_excel_pilot_gate.py` 当作同形修法的**先例**来引。判据用的是 `"task44" in file_bytes.lower()` 这种整文件子串扫描，所以把注释里的引用也算成"接线"。需要裁决的是「判据要不要排除注释/字符串」还是「注释换个说法」——两种改法影响面不同，**不在本簇**，交 **task44 门 / 清册 source_digest** owner。注：该文件里那条 EOL 归一修法本身是本树**已有的未提交改动**（`check_task44...read_task_body` 的 +8 行），与本轮无关 |

## 结论

### 1. A/B/C 计数（29 行全簇）

逐段计数（§三 的 8–12 / 13–17 各按「同 3/4/5/6 + 2」展开，即各 B×2 + A×3）：

| 段 | 行 | A | B | C |
|----|----|---|---|---|
| §三 单列行 | 1–7 | 5（1/2/4/5/7） | 2（3/6） | 0 |
| §三 h1 同名 5 条 | 8–12 | 3 | 2 | 0 |
| §三 g7 同名 5 条 | 13–17 | 3 | 2 | 0 |
| **§四 task44 门** | 18–27 | **9**（19–27） | **1**（18） | 0 |
| **§五** | 28–29 | **1**（28） | 0 | **1**（29） |
| **合计** | **29** | **21** | **7** | **1** |

* **A** = 快照到期、不变量仍成立 ⇒ 断言改**活体派生**，牙齿不丢。
* **B** = 断言的全部用途就是记录一个临时前置条件，而它今天真被满足 ⇒ **反转成后置条件**
  （断言已启用 **且** 启用经由必需的门）并**保留否证臂**，不是删。
* **C** = 真实缺陷 ⇒ 修那个原因。全簇仅 1 条：§五 第 29 行
  （`neutralize_oo_crash_if_formulas` 从未落地的坏 import，已修）。
* 本轮（§四 10 条 + §五 2 条）的分类是 **A × 10、B × 1、C × 1**。

### 2. 关闭情况

* **29 / 29 全部关闭（判据层面）**，无一条靠删断言或放宽口径关闭。
* 本轮 12 条：**12 关闭**。
  * `test_task44_oo94_excel_pilot_gate.py`：**12 failed, 99 passed → 2 failed, 109 passed**
    （残留 2 红不属本簇，见 §六 补记）。
  * `test_task61_oo94_word_pilot_gate.py::TestAdmissionIsRealReadback`：**24 passed, 0 failed**。
  * `test_task75_entry_adapter_roundtrip.py`：**10 passed, 0 failed**（整文件）。
  * 新增防御测试 `test_g7_oo_crash_if_neutralize.py`：**19 passed**。
  * 收官复跑（§四 10 节点 + §五 2 节点 + 新测 + Task 43 `TestOrderingGate`）：**85 passed, 0 failed**。
* 先前已完成的 1–17 行未回归：`test_task41` / `test_task43` 仍 0 failed，
  `test_task42` 仍 1 failed（其残留项在 §六，不属本簇）。

### 3. 仍被正当阻断的项（带 owner，本轮不假装关闭）

| 项 | 为什么仍阻断 | owner |
|----|-------------|-------|
| Task 6 载体证据相对 HEAD 已 stale（`source_commit d330d7cea6bb` vs `fb7a0ace211f`） | 重采需**真实 OO 9.4 容器 + 真实浏览器**跑 `backend/scripts/diagnose/probe_oo94_word_sdt.py`；只改 JSON 里的 commit 字段就是编造证据 | **Task 6 载体门（F2 word pilot 线）** |
| 四类 pilot 仍全部 `unverifiable`（`upstream_gap` 16 行 / `finalize_blocked` 4） | 缺 approved bundle → published representation 的**供给**（生产侧 provisioner）；属实现缺口而非环境缺口，故判 `failed` 而不降级 | **Task 76（projection definition provisioner）** |
| 真实 OO 黑盒 56 行未执行（`real_black_box_not_executed`） | 需真实 OO 9.4 + 真浏览器执行记录，环境依赖 | **Task 44 门的执行记录供给方** |
| `workpaper_writer_inventory.json` stale | generated 产物，本轮规则禁止手改 | **Task 20 收口门 / writer 清册** |
| `word_instrumentation.py` 被 task44 反向锁判为 offender | 需裁决「判据排除注释」还是「注释改写」，两种改法影响面不同 | **task44 门 / 清册 source_digest** |

### 4. 「顺序不可交换」仍然有牙 —— 明确结论

**是。承重属性「finalize 之前不得注册 adapter」在本轮改写之后仍可被变异打红，已实测：**

* **M1**（摘掉 capability 那颗牙）→ **2 红**；顺带量出顺序门有**两颗独立的牙**
  （capability + `adapter_id`），M1 只摘一颗时 `adapter_id` 那颗仍然接住。
* **M1b**（两颗牙全摘 ⇒ finalize 之前真的注册得上）→ **5 红**，跨 task44 门与 task43
  pilot 守卫**两层**，不是单点。
* **M2**（让未准入的 pilot 能让 probe 通过）→ **2 红**。
* **M3**（`upstream_gap` 从 `failed` 降级成 `unverifiable`）→ **1 红**，证明本轮把
  `len(rows)==28` 换成活体恒等式后**没有**变成同义反复。
* 三次变异全部**逐字还原**，还原后源码无 `MUTATION` 残留；全程未用
  `git stash` / `git checkout --` / `git reset`。

牙齿之所以还在，关键是两条被贯彻的形状：**(B) 反转成后置条件时一律保留否证臂**
（退回 `single_onlyoffice` 的 manifest ⇒ 门必抛），**(A) 计数一律改活体派生而不是抬字面量**
（`28→16`、`16→4`、`152→38` 全部现推，历史值写进注释）。

### 5. 本轮改动清单

* `backend/app/services/workpaper_sync/pilot_g7_two_level_dynamic.py`
  —— 补齐从未落地的生产函数 `neutralize_oo_crash_if_formulas`（+ 2 个私有件、`io`/`zipfile`
  import、`__all__` 登记）。**这是本轮唯一一处生产代码改动。**
* `backend/tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py` —— 10 节点改写
  + 2 个取证 helper（`_manifest_before_enablement` / `_pilot_module_before_enablement`）。
* `backend/tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py` —— 1 节点改写。
* `backend/tests/workpaper_sync/test_g7_oo_crash_if_neutralize.py` —— **新增**防御测试。
* 未改：`backend/data/workpaper_sync_entry_manifest.json`、overlay、任何 `*.generated.ts`、
  任何 `*_pg.py`、任何 generated 产物。
