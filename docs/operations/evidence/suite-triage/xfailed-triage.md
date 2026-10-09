# `tests/workpaper_sync` xfail 全量盘点与处置

- 盘点日期：2026-06-01
- 范围：`backend/tests/workpaper_sync/**`（含 `backend/tests/conftest.py` 交叉核对）
- 执行环境：`cwd=d:\GT_plan\backend`，解释器 `..\.venv\Scripts\python.exe`
- 盘点方式：**不跑全量套件**（≈34 min 且会截断）。先 grep 标记点 → 再只跑含标记的文件，
  以 `-q --tb=no -rf -rx -p no:randomly` 拿到真实 `XFAIL` node id 与 `reason`。

## 0. 枚举方法与分母核对

grep 口径 `pytest\.mark\.xfail|pytest\.xfail\(` 命中 7 个文件 21 处，逐处核对后：

| 文件 | grep 命中 | 其中 docstring 散文（非标记） | 真实标记点 | 实测 XFAIL 数 |
|---|---|---|---|---|
| `test_downstream_base_reliability_gate.py` | 2 | 0 | 2 | 2 |
| `test_migration_paradigm_contract.py` | 2 | 1（L38） | 1（L1762，参数化） | 1 |
| `test_slice_schema_validator_coverage.py` | 3 | 1（L49） | 2（L119 参数化、L272） | 1 |
| `test_task53_k_cycle_migration.py` | 1 | 1（L28） | 0 | 0 |
| `test_task56_n_cycle_migration.py` | 1 | 1（L46） | 0 | 0 |
| `test_task60_f2_word_adapter.py` | 5 | 0 | 5 | 5 |
| `test_task64_dedicated_word_chain.py` | 7 | 0 | 7 | 7 |
| **合计** | **21** | **4** | **17** | **16** |

- `test_slice_schema_validator_coverage.py:119` 是参数化动态标记，当前 `_UNJUDGED_SLICES`
  恰为空集 ⇒ 0 个 XFAIL 实例（标记点存在但分母为 0）。因此 17 个标记点 → 16 个实测 XFAIL。
- `backend/tests/conftest.py` 及 `tests/workpaper_sync/` 下**无** conftest 级 xfail；
  `backend/pytest.ini` **无** `xfail_strict`，因此逐条 `strict=` 才是唯一开关。
- `pytest.xfail(` 命令式调用：全树 0 处。

## 1. 16 条 XFAIL 枚举表（node id / reason 摘要 / strict / 裁定）

| # | node id | reason（摘要，原文见 §2） | strict | 裁定 |
|---|---|---|---|---|
| 1 | `test_downstream_base_reliability_gate.py::test_downstream_completed_tasks_do_not_outrun_the_owner_of_the_open_debt` | 门现算 916 条 blocking facts，912 归 Task 74、4 归 Task 71（Wave 7），而 Tasks 25–47/58/59 已标 `[x]` | ✅ | B |
| 2 | `test_downstream_base_reliability_gate.py::test_no_task_behind_the_bulk_adapter_gate_is_completed_while_the_door_is_blocked` | Task 20 把守 `bulk_adapters` 闸，闸后 Tasks 45/46/47 已 `[x]` 而门 `[BLOCKED]` | ✅ | B |
| 3 | `test_migration_paradigm_contract.py::TestAntiPatternCircularJustification::test_single_onlyoffice_entry_states_its_html_counterpart[workpaper_sync_e_cycle_manifest_slice\|xlsx/gt-e1-monetary-fund]` | AP-1 已登记存量欠账，责任方 = E 循环回填任务（待立项） | ✅ | B |
| 4 | `test_slice_schema_validator_coverage.py::test_every_registered_debt_entry_still_has_a_carrier` | 8 条登记里 7 条改裁 `capability: null` 后退出 AP-1 分母 ⇒ 成哑登记 | ✅ | B |
| 5 | `test_task60_f2_word_adapter.py::test_bp10_the_lane_contracts_are_installed_into_the_production_inventory` | BP-10：本 lane 在 source-backed manifest 里没有 entry | ✅ | B |
| 6 | `test_task60_f2_word_adapter.py::test_bp11_the_planned_bundle_slots_pass_the_production_gate` | BP-11：approved bundle 需 DB 侧 definition 行，离线产不出 | ✅ | B |
| 7 | `test_task60_f2_word_adapter.py::test_bp12_the_lane_mount_consumes_a_descriptor` | BP-12/15：OO 挂载点自行请求 config、零 descriptor prop | ✅ | B |
| 8 | `test_task60_f2_word_adapter.py::test_bp13_each_entry_has_a_server_side_evidence_summary` | BP-13：服务端 evidence summary 与逐 scenario 产物级测试一条都没有 | ✅ | B |
| 9 | `test_task60_f2_word_adapter.py::test_bp14_the_lane_extract_no_longer_depends_on_chinese_headings` | BP-14：`f2_stocktake_plan_sync` 仍用中文章节标题正则切分 | ✅ | B |
| 10 | `test_task64_dedicated_word_chain.py::test_bp16_a16_chain_gains_html_field_surface` | BP-16 未解除：A16 链 HTML 字段面仍为 0 | ✅ | B |
| 11 | `test_task64_dedicated_word_chain.py::test_bp17_production_locator_no_longer_uses_cjk_regex` | BP-17 未解除：生产字段定位仍靠 legacy 中文正则 | ✅ | B |
| 12 | `test_task64_dedicated_word_chain.py::test_bp18_a17_word_kind_is_now_used` | BP-18 未解除：A17 word 分支仍不可达 | ✅ | **C→判据已修** |
| 13 | `test_task64_dedicated_word_chain.py::test_bp19_word_hosts_become_descriptor_consumers` | BP-19 未解除：Word 宿主仍非 descriptor consumer | ✅ | B |
| 14 | `test_task64_dedicated_word_chain.py::test_bp20_authority_model_published_to_db` | BP-20 未解除：opaque authority 通道未落库 | ✅ | B |
| 15 | `test_task64_dedicated_word_chain.py::test_bp21_contract_can_express_multiple_templates` | BP-21 未解除：`SyncContract.template` 仍是单 `TemplateRef` | ✅ | B |
| 16 | `test_task64_dedicated_word_chain.py::test_bp22_a17_subcode_entries_become_docx` | BP-22 未解除：A17 子码 entry 仍是 `document_type=xlsx` | ✅ | B |

裁定列说明：`strict` 列已实测全部为 `strict=True` ⇒ **class D 分母为 0**。
第 12 行（bp18）是全 16 条里唯一的 class C，判据已修、标记保留，详见 §3.3。
其余 15 条为 class B，逐条论证见 §3.4。上表 reason 为摘要，逐字原文见 §2 / §3。

## 1.1 基线：本次盘点前已存在的 3 条 FAILED（非 xfail，不在本次处置范围）

为避免后续误判为回归，先固化基线：

| node id | 现象 |
|---|---|
| `test_downstream_base_reliability_gate.py::test_no_evidence_artifact_asserts_a_verified_base_while_the_door_is_blocked` | FAILED（盘点前即红） |
| `test_task64_dedicated_word_chain.py::TestGeneratorContract::test_generator_check_is_idempotent` | FAILED（盘点前即红） |
| `test_task56_n_cycle_migration.py::TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed` | FAILED（`找不到 SYNC_ADAPTER_REGISTERED_ENTRY_IDS 的声明`，盘点前即红） |

## 2. 判据方法：先证明「失败原因 = 所述契约」

对全部 16 条跑 `--runxfail`（让标记失效、看真实失败），逐条核对**失败原因是否就是 reason
所述的那件事**。这是区分「B/C 类待办」与「A 类被遮住的生产缺陷」的关键动作 —— 若某条其实是
`ImportError` / `AttributeError` / 查不存在的列，那就是 xfail 把真 bug 遮住了。

实测结论：**16 条全部在其所述契约上诚实失败**，无一条是偶发/无关异常伪装成 xfail。

摘录（`--runxfail -q --tb=line`）：

| node | 真实失败 |
|---|---|
| bp16 | `assert 0 > 0`（占位符数） |
| bp17 | `assert not [('××公司', …), …]`（`_LEGACY_PATTERNS` 非空） |
| bp18 | `assert 'word' in {'a17-summary','checklist','closing-meeting',…}` |
| bp19 | `assert 'defineExpose' in '<!-- WorkpaperWordEditor.vue …'` |
| bp20 | `assert False`（无 entry 的 `definition_bundle` 非 null） |
| bp21 | `assert False`（无 list/tuple 型 template 注解） |
| bp22 | `document_type` 实为 `xlsx` |
| bp10 | `'f2.stocktake.plan' not in (…可用契约…)` |
| bp11 | `BundleSlotNullFieldError`（**生产闸按设计拒 null slot_ref**，非缺陷） |
| bp12 | `挂载点没有 descriptor prop` |
| bp13 | `assert None is not None`（`sync_test_run_id`） |
| bp14 | `service 里仍有中文章节标题定位` |
| 下游①| `282 条跨 wave 宣称，涉及 47 个任务` |
| 下游②| `23 条越门宣称（门现算 750 条 blocking facts）` |
| AP-1 | entry 裁 `single_onlyoffice` 却无 `html_counterpart_verdict` 二值结论 |
| 承载者| `known_debt_inventory 有 7 条哑登记` |

## 3. 逐条裁定与处置

### 3.1 class A（隐藏生产缺陷）—— 0 条

没有一条 reason 写「production code bug」或等价措辞，且 §2 已证明 16 条全部在所述契约上失败。
逐条核过三个最像 A 的候选，全部否决，理由落在可复算的实测上：

**BP-16（`parse_template` 对 A16 七份模板返回 0 占位符）** —— 最像 parser bug，实测**不是**：

- `parse_template` 对七份各返回 70~125 段落 / 3~19 表格 ⇒ 文件读得开、解析正常；
- 段落与表格单元格**两条**路径都调 `_extract_placeholders_from_text`（读源码确认，非推测）；
- 把 `_LEGACY_COMPILED` + `_NEW_PLACEHOLDER_RE` 直接喂 `paragraph.text + cell.text` 拼串 ⇒ 命中 0；
- 再解包 docx 对 `word/*.xml` **原始字节**复扫（覆盖页眉页脚/文本框/SDT）⇒ 仍命中 0。

结论：模板里确实一个标记都没有，parser 无过。改 parser 不可能、也不应该让它转绿。

**BP-17（`_LEGACY_PATTERNS` 非空）** —— reason 确实在指控生产代码违反 Requirement 7.1，
但**不能靠删它转绿**：该表是 25 个 word-template wp_code 当前唯一的字段识别通道
（`wp_docx_template_parser` 模块 docstring 明写）。先删即让生产识别能力归零、无替代品 ——
那是把判据做绿，不是让契约成立，直接违反本轮「不得靠削弱判据/破坏生产摘标记」的约束。
正解是 Task 61 的 tagged SDT 替换，属未建能力而非缺陷。

**BP-22（A17 子码 `document_type` 清册裁 docx / manifest 是 xlsx）** —— 这**是**一条真实的
数据不一致（同一 wp_code 两个坐标系类型相反，按 manifest 迁移会漏掉整条 A17 Word 链）。
但 BP-22 登记末条明写「改 manifest 属 Task 67 structural pre-reconcile，本任务无权改写」，
且改动会与 Task 57 的 Excel entry 撞车。**不属本次盘点的授权范围**，裁 B 并在 reason 里把
「这是真实数据不一致、不是功能没做」写明，避免下一个读者再次误判为「等功能」。

### 3.2 class D（strict 缺失）—— 0 条

`backend/pytest.ini` 无 `xfail_strict`，因此逐条 `strict=` 是唯一开关。程序化核对 17 个标记点
（标记行起 12 行窗口内检索 `strict=True`）：**17/17 全部带 `strict=True`**。无 XPASS 静默风险，
实跑亦为 `16 xfailed / 0 xpassed`。无需改动。
### 3.3 class C（判据过时）—— 1 条：BP-18，**已修**

这是本轮唯一的实质缺陷，而且它不在生产代码里，在**探测器**里 —— 一条永远不可能打红的 strict
xfail，等于「这个标记不存在」。

原判据：

```python
@pytest.mark.xfail(strict=True, reason="BP-18 未解除：A17 word 分支仍不可达")
def test_bp18_a17_word_kind_is_now_used() -> None:
    text = A17_BUNDLE_VUE.read_text(encoding="utf-8")
    assert "word" in set(re.findall(r"kind:\s*'([^']+)'", text))
```

矛盾：BP-18 在 `workpaper_sync_a16_a17_word_chain_adjudication.json` 里登记的处置方向是
**删除** —— `observable_consequences` 末条逐字写着「删除动作归 Task 66 计划 + Task 72
Stage B；本任务只裁决与登记」。而实测 `GtA17Bundle.vue`：

- L695 `<template v-else-if="tab.kind === 'word'">`、L696 `<WorkpaperWordEditor`（挂载点在）；
- `kind: 'word'` 只出现在 L52 的 `TabDef.kind` 联合类型里，TABS 十行没有一行用它（分支恒假）。

于是：**一旦 Task 72 按计划把挂载点删掉，`kind: 'word'` 依然不会出现** ⇒ 本条永远停在 XFAIL，
`strict=True` 再也不可能 XPASS 打红。债还完了却没人被提醒回来删标记 —— 探测器对计划内的那条
解除路径**完全失明**。

处置：把判据从「只判启用」扩成登记在案的**两条解除路径**（删除 **或** 启用）。
判据没有被放宽 —— 分母从 1 条扩到 2 条，XFAIL 的成立条件反而更严（今天两条都不成立才 XFAIL）。
标记**保留**（契约仍未成立，删标记会打红），修的是它的可触发性。

#### 变异验证（MUTATION-VERIFY）

对 `GtA17Bundle.vue` 做「读原字节 → 变异 → 跑单条 → `finally` 无条件还原 → SHA-256 校验」：

| 场景 | 旧判据 | 新判据 | 实跑结果 |
|---|---|---|---|
| baseline（未变异） | XFAIL | XFAIL | `XFAIL` ✅ 标记仍应保留 |
| M1 挂载点被删除（Task 66/72 的处置方向） | `False` ⇒ 永远 XFAIL，**失明** | `True` | `XPASS-RED` ✅ 盲区已修 |
| M2 `kind: 'word'` 被启用 | `True` | `True` | `XPASS-RED` ✅ 原能力无退化 |

还原校验：**字节一致**（SHA-256 比对通过），工作树无残留。一次性脚本
`backend/scripts/diagnose/_mutate_bp18_detector.py` 用后即删（`_` 前缀约定）。

### 3.4 class B（外部/前置依赖未就绪）—— 15 条，全部保留并收紧 reason

15 条的共同形态：判据正确、`strict=True` 正确、失败原因诚实，缺的是**未建能力或他人名下的
前置产出**。按本轮规则只收紧 reason 文本（必须点名确切解除条件），不动判据。

两个文件的探测器架构均已配非 xfail 的**前提守卫**，所以「判据对象被改名/删除」不会让标记静默
失效（这是此前最担心的失明形态，实测已被覆盖）：

- `test_task60_f2_word_adapter.py`：L521 断言全部判据对象路径存在；L1683 断言
  `oo_mount_site_count == len(mount_lines) == 1`；L1705 断言 `GtOnlyOfficeSheet` 仍自取 config；
  L1915 断言 plan service 里的中文标签仍在（附言「BP-14 已被处置，请更新登记」）。
- `test_task64_dedicated_word_chain.py`：`TestBlockingPreconditions::test_all_bps_are_registered_and_open`
  断言每条 BP 仍 `status == "open"` 且 `source_refs` 全部存在；
  `test_property_47_denominator_is_not_zero` 反向守卫 BP-19；
  `test_a17_word_mount_is_gated_by_a_kind_never_used` 守卫 BP-18 的前提。
#### B-1 ～ B-2：下游 base 可靠性门（2 条）—— reason 里的计数**已烂**，已修

盘点前 reason 写死「门现算 916 条 blocking facts，912 条归 Task 74、4 条归 Task 71，而
Tasks 25–47 / 58 / 59 已全部标 [x]」。现跑 `check_workpaper_writer_revision_gate.py` 与
`evaluate_gate()` + Task 20 归属解析器：

```
total blocking facts = 750
by owner = {'74': 747, '71': 3}
nonzero = {bypasses_unified_commit: 303, writes_legacy_version_field: 5,
           owns_direct_commit: 124, multi_resolver: 3,
           non_canonical_resolver_only: 76, writer_without_characterization_test: 239}
归属 Task 20 自有的六条准则：全部为 0（与 docstring 的裁决一致）
本条现算：282 条跨 wave 宣称、涉及 47 个任务（已扩到 60/62–70/76/77，不再是 25–47/58/59）
```

⇒ `916 / 912 / 4` 与任务清单**三处全部失真**。这不是判据问题（判据一直现算），是 reason 与
docstring 里写死的数字随门收敛而腐烂 —— 读者据此判断「还差 916 条」会得到错误的进度认知。

处置：两条 reason + 文件 docstring 三处 916/912/4 全部更新为 750/747/3，**并把数字显式标注为
「快照、不是判据」**，真源指回 `evaluate_gate()`，附上失真历史。这样下一轮腐烂时读者立刻知道
该现算而不是信数字。解除条件（Task 74 清准则 + Task 71 清 `multi_resolver`，或回退下游 `[x]`）
原本已写明，保留并加粗责任方。

#### B-3：AP-1 已登记欠账（`workpaper_sync_e_cycle_manifest_slice|xlsx/gt-e1-monetary-fund`）

实测：`known_debt_inventory` 登记 8 条（D 循环 7 + E 循环 1），但本参数化只收
`capability == "single_onlyoffice"` 的 entry，而 D 循环那 7 条已改裁成 `capability: null`
⇒ **实际挂得上标记的只剩 E 循环这 1 条**。reason 里照抄 JSON 的「全部 8 条债务兑现」会让读者
以为这一条 XPASS 就代表 8 条全清。

处置：reason 补明「分母实为 1、另 7 条已成哑登记，由 `test_slice_schema_validator_coverage.py::
test_every_registered_debt_entry_still_has_a_carrier` 单独盯着」，并显式声明
「『全部 8 条兑现』不能只靠本条 XPASS 证明」。解除条件 = E 循环回填任务（**待立项**）。

#### B-4：`test_every_registered_debt_entry_still_has_a_carrier`（7 条哑登记）

实测 D slice 那 7 条：`html_counterpart_verdict` 全部已填 `exists`、`capability` 全部已改裁为
`null` ⇒ 它们登记的那个 AP-1 违规**在磁盘上已不存在**，是纯粹的僵尸行。也就是说 reason 里的
解除条件 ①（「把 7 条登记从 known_debt_inventory 移除 + 在 Task 46 正文说明改裁已替代欠账」）
**现在已经数据就绪，不需要等任何新功能**。

**刻意不代为删除**，理由写进 reason：①范式 JSON 与两份 slice 是该文件的只读约束（文件头自述
「并发会话在改」，本轮实测确有并发会话正在改 `workpaper_sync_entry_manifest.json` 等 20+ 文件）；
②这 7 条的 owner 明写为「Task 46 D 循环回填（并发会话进行中）」。由第三方改别人名下的治理数据
来让判据转绿，正是这个文件要拦的形态。处置 = 只在 reason 里标注「条件 ① 已数据就绪」，
让 owner 能低成本收口。

#### B-5 ～ B-9：Task 60 F2 Word lane（BP-10 ～ BP-14）

5 条 reason **原本就带 `**解除条件**`**，且责任方明确（BP-10 → manifest 扫描器发现本 lane 后装载
契约；BP-11 → Task 15/36 发布 definition 行；BP-12 → Task 61 改 `<GtOnlyOfficeSheet>` 消费
descriptor；BP-13 → Task 61 跑完真实 OO 9.4 全场景；BP-14 → Task 61 用 tagged SDT 取代中文
章节正则）。**本轮不改这 5 条**，是全 16 条里唯一无需收紧的一组。

#### B-10 ～ B-15：Task 64 A16/A17 Word 链（BP-16、17、19、20、21、22）

6 条 reason 盘点前均为**单行、无解除条件**（如 `"BP-16 未解除：A16 链 HTML 字段面仍为 0"`），
违反该文件 §8 自述的「xfail strict + 解除条件」与项目铁律。已逐条据
`workpaper_sync_a16_a17_word_chain_adjudication.json` 的 `blocking_preconditions` 登记补全：

| BP | 解除条件（写进 reason，责任方加粗） | 额外写进 reason 的防误判信息 |
|---|---|---|
| 16 | A16 七份模板获得真实字段面（`${}` token 或 tagged SDT，**Task 61** SDT 注入）且存在消费方 | 三重实测证明**不是 parser bug**，不得靠改 parser 转绿 |
| 17 | **Task 61** 用 tagged SDT/`${}` 取代三种禁用锚点并迁移模板，`_LEGACY_PATTERNS` 随之清空 | ①不得为转绿单独删该表（生产识别唯一通道）②本条只盯 3 种锚点里的中文正则 1 种，XPASS ≠ 三种全清 |
| 19 | **Task 61** 把两个 Word 宿主改成消费 descriptor 并 `defineExpose` durable API | 指出反向守卫 `test_property_47_denominator_is_not_zero` 会先打红 ⇒ 本条不会静默失效 |
| 20 | **Task 65** 交付 opaque bundle 协议 **且** Task 15/36 发布 definition 行 | 绝不为凑 non-null 造假 uuid |
| 21 | 契约模型获得多模板表达力（`template` → `tuple[TemplateRef, ...]` 或新增列表字段）；已实证全仓无 `template_refs`/`templates: tuple` 承载者 | 本条只探测「模型变宽」一条路径；若改走「拆成多条 entry」则不会 XPASS，删标记前须回登记复核 |
| 22 | **Task 67** structural pre-reconcile 改 manifest 的 `document_type` | 明写「这是真实数据不一致、不是功能没做」，但改动会与 Task 57 撞车，不得在测试侧改数据转绿 |

BP-17 / BP-21 那两条「本探测器只覆盖解除路径之一」的告警，是本轮从 BP-18 的失明教训**触类旁通**
查出来的同类风险：登记的处置方向可能不止一条，而探测器只认一条。BP-18 是已经确定会失明（登记
明写删除）故修判据；BP-17/21 的登记方向与判据一致，故只在 reason 里留下「删标记前回登记复核」
的显式提醒，不改判据（改了会变成无根据地猜处置方向）。
## 4. 回归验证

### 4.1 改动清单（4 个文件，149 插入 / 19 删除，全部为 reason 文本 + docstring + BP-18 判据）

```
tests/workpaper_sync/test_downstream_base_reliability_gate.py    | 33 ++++--
tests/workpaper_sync/test_migration_paradigm_contract.py         |  7 ++
tests/workpaper_sync/test_slice_schema_validator_coverage.py     | 11 +-
tests/workpaper_sync/test_task64_dedicated_word_chain.py         | 117 ++++++++++++++--
```

### 4.2 四个被改文件（未跑全套件，逐文件点名）

```
..\.venv\Scripts\python.exe -m pytest \
  tests/workpaper_sync/test_task64_dedicated_word_chain.py \
  tests/workpaper_sync/test_downstream_base_reliability_gate.py \
  tests/workpaper_sync/test_migration_paradigm_contract.py \
  tests/workpaper_sync/test_slice_schema_validator_coverage.py \
  -q --tb=no -rf -p no:randomly

⇒ 2 failed, 266 passed, 11 xfailed
```

- `11 xfailed` = 2（下游门）+ 1（AP-1）+ 1（承载者）+ 7（Task 64）✓ 与盘点分母一致；
- `0 xpassed` ⇒ 没有任何标记因改动而变成假绿；
- 2 failed **与盘点前基线逐字相同**（§1.1 的前两条），无新增失败。

### 4.3 读这两个守卫源码的旁证文件

`test_task57_abcs_and_shared_migration.py` 与 `test_task60_f2_word_adapter.py` 会读
`test_migration_paradigm_contract.py` / `test_slice_schema_validator_coverage.py` 的源码文本
（`CONTRACT_GUARD` / `COVERAGE_GUARD`），故一并跑：

```
⇒ 2 failed, 203 passed, 5 xfailed
FAILED test_task57::TestSliceScopeIsRecomputable::test_parent_duplicate_section_is_absent_because_in_scope_count_is_zero
FAILED test_task57::TestAdjudicationLegality::test_ac14_notice_single_source_exists_and_is_consumed_out_of_scope
        AssertionError: 声明 42 现算 46
```

**这两条与本次改动无关**，三条独立证据：

1. 失败判据的输入是 `SLICE_PATH`（abcs slice JSON）与 `AC14_NOTICE_VUE` 的**前端**消费方；
   `_statement_edges_to` 只遍历 `_all_frontend()`，**根本不扫 backend**。本轮改的 4 个文件全在
   `backend/tests/` 下，落不进它的分母。
2. 本轮改的 4 个文件里 grep `GtEntrySyncCapabilityNotice|workpaperEntrySyncNotice|abcs_cycle`
   ⇒ **0 命中**。
3. `git status` 显示存在**并发会话**正在改 20+ 个非本轮文件，含
   `audit-platform/.../sync/workpaperSyncManifest.generated.ts`（-736 行）、
   `workpaperSyncLegacyBaseline.generated.ts`、`workpaper_sync_entry_manifest.json` 等；
   「声明 42 现算 46」= 前端新增了 4 个 notice 消费方，正是该会话的辐射面。
   本轮唯一动过的前端文件是 `GtA17Bundle.vue`，且已 SHA-256 校验**字节级还原**。

⇒ 记为并发会话基线，不在本次处置范围。

### 4.4 未执行的约束遵守情况

- 全程**未**一次性跑 `tests/workpaper_sync` 全套件；只按文件点名执行（单次最长 38s）。
- 读源码**未**用 `rtk`；命令用 `;` 分隔、一律传 `cwd` 未用 `cd`。
- 未碰任何 `_pg` 测试，未连 `audit_platform` 真实库，未增删改任何真实项目数据。
- 唯一的文件变异（BP-18 的 `GtA17Bundle.vue`）走 `try/finally` + SHA-256 还原校验。
- 未通过削弱断言摘掉任何标记：本轮**摘除标记数 = 0**（见 §5）。
## 结论

### 分类计数（分母 16 条，每条恰好归一类）

| 类别 | 条数 | 处置 |
|---|---|---|
| **A. 隐藏生产缺陷** | **0** | 无需修复。3 个最像 A 的候选（BP-16/17/22）逐条以实测否决，见 §3.1 |
| **B. 外部/前置依赖未就绪** | **15** | 全部保留；10 条收紧 reason（点名确切解除条件 + 责任方），5 条（Task 60 BP-10~14）原本已合规未改 |
| **C. 判据过时** | **1** | BP-18 **已修**：判据扩成登记在案的两条解除路径，标记保留（契约仍未成立），变异验证通过 |
| **D. strict 缺失** | **0** | 17/17 标记点全带 `strict=True`；`pytest.ini` 无 `xfail_strict`，实跑 `0 xpassed` |

### 消除的 xfail 数量

**0 条**。这是诚实的结论，不是未完成：16 条的契约**今天全都仍未成立**，摘掉任何一条标记都会
让测试变红。唯一能"消除"它们的方式是削弱断言或改别人名下的治理数据 —— 两者都被本轮明令禁止，
也正是这套守卫存在的目的。

本轮真正消除的是**1 个探测器盲区**（BP-18）：一条 `strict=True` 却永远不可能打红的 xfail，
在债务真的还完时不会提醒任何人，与「这个标记不存在」逐字等价 —— 那才是这批 xfail 里唯一的
false-green。修复后它在两条解除路径上都能打红（变异实测 M1/M2 双红）。

附带消除的是 **3 处已腐烂的 reason/docstring 计数**（916→750、912→747、4→3）与
**1 处分母误导**（AP-1「8 条」实际只挂 1 条），并把计数显式标注为快照、真源指回现算函数，
防止同类腐烂复发。

### 仍然合法存在的 16 条及其确切解除条件

| # | node（简称） | 确切解除条件 | 卡点性质 |
|---|---|---|---|
| 1 | 下游①`…do_not_outrun_the_owner…` | **Task 74** 清其名下准则（现算 747 条）**+ Task 71** 清 `multi_resolver`（现算 3 条）；或把 60/62–70/76/77 等 47 个下游任务的 `[x]` 回退 | 他任务未完成 |
| 2 | 下游②`…behind_the_bulk_adapter_gate…` | 同上，门归零（现算 750 条 blocking facts）；或回退 `bulk_adapters` 闸后已 `[x]` 的任务 | 他任务未完成 |
| 3 | AP-1 `…e_cycle…xlsx/gt-e1-monetary-fund` | **E 循环回填任务（尚未立项）** 给该 entry 补 `html_counterpart_verdict` 二值结论 + `source_refs`，或改裁 bidirectional | 任务未立项 |
| 4 | `…debt_entry_still_has_a_carrier` | 任一：① **范式 owner / Task 46** 删掉 7 条僵尸登记并在 Task 46 正文说明改裁已替代欠账（**已数据就绪，可立即收口**）；② AP-1 分母覆盖「待裁决态」；③ D slice 的欠账内容真的进 `slice_schema.validator` 判据（`enforce_task48` 由任务号推导，现不施加） | 治理数据待 owner 收口 |
| 5 | bp10 lane 契约装入生产清册 | manifest 扫描器能发现本 lane（需 descriptor/adapter 形态挂载点，见 BP-12）后装入 `workpaper_sync_contracts/` 并补登记行 | 依赖 BP-12 |
| 6 | bp11 bundle slot 过生产闸 | **Task 15/36** 发布 DB definition 行，slot_ref 变 `definition:<uuid>` | **需真实 DB** |
| 7 | bp12 挂载点消费 descriptor | **Task 61** 把 `<GtOnlyOfficeSheet>` 改成消费 descriptor（含 approved bundle）并暴露 durable API | 他任务未完成 |
| 8 | bp13 服务端 evidence summary | **Task 61** 跑完真实 OO 9.4 全场景并落 `sync_test_run_id` / `required_scenario_set_digest` | **需真实 OnlyOffice 9.4 环境** |
| 9 | bp14 lane extract 脱离中文标题 | **Task 61** 用 tagged SDT 取代 `f2_stocktake_plan_sync` 的中文章节正则 | 他任务未完成 |
| 10 | bp16 A16 链 HTML 字段面 | A16-1~A16-7 七份模板获得真实字段面（`${}` token 或 tagged SDT，**Task 61** 注入）且存在消费方 | **模板内容待注入**（非代码） |
| 11 | bp17 生产定位脱离 CJK 正则 | **Task 61** 用 tagged SDT/`${}` 取代三种禁用锚点（中文正则 14 / `paragraph_index` 14 / 顺序编号 9）并迁移模板，`_LEGACY_PATTERNS` 随之清空 | 他任务未完成（不得先删） |
| 12 | bp18 A17 word 分支 | 任一：① **Task 66** 删除计划 + **Task 72 Stage B** 摘掉挂载点（登记的处置方向）；② 某 TAB 真裁成 `kind: 'word'` | 他任务未完成 |
| 13 | bp19 Word 宿主成 descriptor consumer | **Task 61** 把 `WorkpaperWordEditor.vue` 与 `OnlyOfficeWordDialog.vue` 改成消费 descriptor 并 `defineExpose` | 他任务未完成 |
| 14 | bp20 authority model 落库 | **Task 65** 交付 opaque bundle 协议 **且** Task 15/36 发布 definition 行 | **需真实 DB** + 他任务 |
| 15 | bp21 契约表达多模板 | `SyncContract.template` → `tuple[TemplateRef, ...]` 或新增列表型 template 字段（若改走「拆成多条 entry」本条不会 XPASS，须回登记复核） | 契约模型未扩展 |
| 16 | bp22 A17 子码 entry 转 docx | **Task 67** structural pre-reconcile 改 manifest `document_type`（本文件无权改写；改动会与 Task 57 Excel entry 撞车） | **真实数据不一致**，待 Task 67 |

### 卡点归并

- **需真实外部环境**：3 条 —— DB 侧 definition 行（#6、#14）、真实 OnlyOffice 9.4 全场景（#8）。
- **他任务未完成**：10 条 —— Task 61（#7、#9、#11、#13，兼 #10 的模板注入）、Task 74 + 71（#1、#2）、
  Task 65（#14 另一半）、Task 66 + 72（#12）、Task 67（#16）。
- **任务未立项 / 治理数据待 owner 收口**：2 条 —— #3（E 循环回填未立项）、#4（7 条僵尸登记已数据就绪）。
- **产物内容 / 模型未扩展**：2 条 —— #10（模板字段面）、#15（契约多模板表达力）。

其中**最低成本的一条是 #4**：D slice 那 7 条登记的 AP-1 违规在磁盘上已不存在
（`html_counterpart_verdict: exists` + `capability: null` 全部实测确认），owner 只需删登记 +
补一句正文说明即可解除，不需要等任何新功能。

### 遗留风险提示（非本轮授权范围）

- **#16 是一条真实的生产数据不一致**，不是「功能没做」：同一 wp_code 在 Task 58 清册里裁
  `resolved_docx`、在 entry manifest 里却是 `document_type=xlsx`。按 manifest 迁移会漏掉整条
  A17 Word 链。已在 reason 里写明性质与责任方（Task 67），建议优先排期。
- **#11 / #15 的探测器只覆盖各自解除路径之一**（BP-17 只盯 3 种禁用锚点里的中文正则；BP-21 只盯
  契约模型变宽）。已在 reason 里写入「删标记前须回 BP 登记复核实际处置方向」，未改判据 ——
  改了等于无根据地替 owner 猜处置方向。这是从 BP-18 失明教训触类旁通查出的同类风险。
