# 治理闸门 + 生成物陈旧 残留收口

目标：关闭 3 组共 8 个残留失败节点（80 failed 全量 run 中的最大残留簇）。
约束：不得把 `tasks.md` 的 `[ ]` 改成 `[x]` 来让闸门变绿；不得削弱闸门。

## 裁定表（8 行）

| node | group | verdict | action |
|---|---|---|---|
| `test_workpaper_sync_program_milestones.py::test_generated_projection_is_current_and_self_digest_bound` | 1 milestones | **STALE ARTIFACT** | 待 Group 2 清账后 `--apply` 重算 projection |
| `…::test_eight_spec_task_and_dependency_denominators_are_exact` | 1 milestones | **GENUINELY BLOCKED** | 保持红；owner `…closure:program-governance`（G0-3） |
| `…::test_g0_3_archive_dependency_is_closed_and_mutation_reopens_debt` | 1 milestones | **GENUINELY BLOCKED** | 保持红；`archive_bypasses_writer_debt` 是真 blocker |
| `…::test_g0_3_wave_order_is_valid_and_same_wave_forward_dependency_is_rejected` | 1 milestones | **GENUINELY BLOCKED** | 保持红；Wave 8 从未建 |
| `…::test_g0_3_does_not_promote_tasks_milestones_or_g0_4` | 1 milestones | **GENUINELY BLOCKED** | 保持红；BLOCKED=5 全部 producer_tasks_incomplete |
| `test_task44_oo94_excel_pilot_gate.py::TestGateAddsNoProductionModule::test_writer_inventory_is_still_fresh` | 2 stale artifact | **STALE ARTIFACT** | `--apply` 重算清册（差异=2 行号）→ 绿 |
| `tests/workpaper_sync_frontend/test_task69_frontend_regression.py::TestReportIsFreshAndByteLocked::test_gate_check_passes` | 2 stale artifact | **LAUNDERING RISK**（兼真阻塞） | 拒绝重算：现算 verdict=`failed`，重算=把 failed 焊进冻结基线 |
| `test_task44_oo94_excel_pilot_gate.py::TestGateAddsNoProductionModule::test_no_workpaper_sync_production_module_references_task_44` | 3 adjudication | **STALE DETECTOR** | 探测器改为忽略注释/docstring（保留普通字符串）→ 绿 |

裁定口径：
- **STALE ARTIFACT** — 生成物落后于已命名的真实来源变化，重新生成即可，需变异验证闸门仍有牙。
- **STALE DETECTOR** — 探测器口径过宽/过窄，修探测器而非修被测对象，需重新引入真实违规确认变红。
- **GENUINELY BLOCKED** — 真实未完成工作，保持红色，写明 owner + 解阻条件。
- **LAUNDERING RISK** — 拒绝修改，说明为什么「修好」等于洗白。

---

## BEFORE 计数（逐文件，verbatim）

命令：`cwd=backend`，`..\.venv\Scripts\python.exe -m pytest <file> -q --tb=short -rf -p no:randomly`

```
tests/workpaper_sync/test_workpaper_sync_program_milestones.py
  5 failed, 17 passed, 3 warnings in 87.59s (0:01:27)

tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py
  2 failed, 109 passed, 24 warnings in 361.17s (0:06:01)

tests/workpaper_sync_frontend/test_task69_frontend_regression.py
  1 failed, 78 passed, 1 warning in 11.13s
```

Group 1 的 5 个失败与任务书预列的 4 个**不完全一致**：第 5 个是
`test_generated_projection_is_current_and_self_digest_bound`，且
`test_g0_3_does_not_promote_tasks_milestones_or_g0_4` 现在首先炸在
`task_state_counts` 而不是 `BLOCKED <= 3`（两者都不成立，只是前者先断）。

---

## Group 1 · program milestones：**先前 triage 的 `producer_tasks_incomplete` 结论成立，但根因比记录的更重**

### 关键否证：这些 pin **不是** stale denominator

任务书提示「可能是 stale denominators 而非 incomplete producers」。实测**否**。
决定性测量——三条独立证据链指向同一结论：

**① 被测源文件自 `0bedc5e1a`（引入该测试与该 snapshot 的同一个 commit）起逐字未变**

`_probe_graph_history.py` 逐 rev 解析核心 spec `tasks.md` 的依赖图与 checkbox：

```
rev         | waves        | deps72                        | wave7                          | wave8
0bedc5e1a   | [0..7]       | ['67','68','69','70','71']    | ['68','69','70','71','72','74'] | []
a4c8d20cc   | [0..7]       | ['67','68','69','70','71']    | 同上                            | []
cd9592ff5   | [0..7]       | ['67','68','69','70','71']    | 同上                            | []
ebc6e1b92   | [0..7]       | ['67','68','69','70','71']    | 同上                            | []
HEAD        | [0..7]       | ['67','68','69','70','71']    | 同上                            | []
WORKTREE    | [0..7]       | ['67','68','69','70','71']    | 同上                            | []
六个 marker：{'1':'x','2':'x','20':'x','60':'x','62':'x','64':'x'} —— 全 rev 恒为 x
overview 含 '77 个主/全任务'：False（全 rev）；含 '74 个任务'：True（全 rev）
```

`git diff 0bedc5e1a HEAD -- <core tasks.md>` = 52 insertions / 2 deletions，**0 条 checkbox 行变更**
（`Select-String '^[+-]- \['` 空结果）。`ebc6e1b92` 对该文件只有 49 行纯新增。

⇒ 先前 evidence（`milestone-blocked-regression.md`）把这些字面量归因为「real drift from `ebc6e1b92`」**是误判**：
`ebc6e1b92` 一个 marker 都没动。

**② 已提交的 snapshot 与 live tasks.md 一致，唯独测试字面量是孤立值**

| 量 | 测试期望 | live 现算 | 已提交 snapshot |
|---|---|---|---|
| 六任务 `1/2/20/60/62/64` | `~` ×6 | `x` ×6 | `x` ×6 |
| core `state_counts` | completed 66 / partial 6 | 72 / 0 | 72 / 0 |
| `stats.task_state_counts` | 240 / 15 / 7 / 1 | 246 / 9 / 7 / 1 | 246 / 9 / 7 / 1 |
| `dag.internal_edge_count` | 448 | 447 | 447 |
| core waves | `range(9)` | `[0..7]` | — |

`backend/data/workpaper_sync_program_milestones.json` 的 `git log` **只有一个 commit**（`0bedc5e1a`），
即测试与 artifact 同 commit 落地却互相矛盾 ⇒ 测试**出生即红**，不是后来漂移。

**③ 差值恰好等于缺失的那一条治理边**

`internal_edge_count`：448（期望）− 447（实测）= **1**，缺的正是 `72 → 74`。
生产代码（生成器，未改动）独立判定这是 blocker：

```
{'code': 'archive_bypasses_writer_debt', 'severity': 'blocker',
 'spec': 'workpaper-html-onlyoffice-bidirectional-writeback-closure',
 'task': '72', 'missing_dependency': '74'}
```

所以 448 **不是手抄错的常量**，而是「归档必须依赖 writer 债清零」这条要求的数值影子。
把它改成 447 = 抹掉要求本身。

### 这是谁的活：G0-3 声称 CLOSED，交付物却不在树上

`.kiro/specs/…/evidence/g0-3-archive-writer-debt-dependency/README.md` 执行卡：

```json
"id": "G0-3",
"name": "补核心 Task 72 → Task 74 依赖并锁死合法 Wave 顺序",
"status": "CLOSED",
"owner": "workpaper-html-onlyoffice-bidirectional-writeback-closure:program-governance",
"output_milestone": "G0-3-ARCHIVE-DEPENDS-ON-WRITER-DEBT"
```

工作包名字就是这三条测试的内容，`status` 标 `CLOSED`，但 `tasks.md` 里
72→74 的边、Wave 8、六个 `~` 降级、overview 分母，**一条都没落**。
`test_g0_3_work_package_declares_every_required_execution_field` 之所以绿，是因为它只校验
`status in {"IN_PROGRESS","CLOSED"}` 这类**字段齐备性**，不校验交付；校验交付的正是那三条红测试。
⇒ **假闭环**：闸门正确地在报「工作包自称完工但产物缺失」。

### 为什么不能顺手把边加上

生成器 `normalize_dependency_graph` 会拒绝同 Wave 非前序依赖。live 中 72 与 74 同在 Wave 7，
且 `72 < 74`，故直接给 `deps["72"]` 加 `"74"` 会抛：

```
ProgramMilestoneError: task 72 depends on same-wave non-earlier tasks ['74']
```

真正的解阻是**三步联动的 program-plan 变更**（拆 Wave 8 → 把 72 移出 Wave 7 → 再加边），
外加六个已宣称 `[x]` 的任务降级为 `[~]`。这属于 program-governance 的审计裁决，
不是测试维护，本 session **拒绝代做**。

### 5 个 BLOCKED milestone 的 producer 实测（`BLOCKED <= 3` 不可达）

```
PUBLISHED-ENTRY-READY      producer closure:75 = '-'          → producer_tasks_incomplete
                                                              + per_entry_request_path_evidence_missing
ROW-MUTATION-READY         producer excel-structural-row…:20 = '~' → producer_tasks_incomplete
SYNC-ENTRY-NAMESPACE       producer closure:75 = '-'          → producer_tasks_incomplete
                                                              + request_path_registry_evidence_missing
TEMPLATE-OVERRIDE-CHANGED  producer excel-template-override… = <NO TASKS DECLARED>
                                                              → producer_tasks_missing + producer_contract_missing
X-RUNTIME-EVIDENCE         producer custom-workpaper…:19 = '~' → producer_tasks_incomplete
```

`milestone_state_counts` = `{BLOCKED 5, IMPLEMENTED 3, STALE 8}`（fresh 与 snapshot **相同**），
`diagnostic_count` = 6（测试期望 5，第 6 条正是 `archive_bypasses_writer_debt`）。
注：`SYNC-MULTI-RESOLVER` 已**不再** BLOCKED（`multi_resolver` 4 → 3 且未归零但该 milestone 现由别的谓词决定），
先前 evidence 里「BLOCKED=4 且由 SYNC-MULTI-RESOLVER 撑起」的读数已被本次实测取代。

### 逐节点裁定（Group 1）

| node | 失败判据 | 裁定 |
|---|---|---|
| `test_generated_projection_is_current_and_self_digest_bound` | `on_disk == registry` | **STALE ARTIFACT** |
| `test_eight_spec_task_and_dependency_denominators_are_exact` | 六 `~` pin + 66/6 + 240/15 + overview 分母 | **GENUINELY BLOCKED** |
| `test_g0_3_archive_dependency_is_closed_and_mutation_reopens_debt` | `internal_edge_count == 448` + 无 archive 诊断 | **GENUINELY BLOCKED** |
| `test_g0_3_wave_order_is_valid_and_same_wave_forward_dependency_is_rejected` | `sorted(waves) == range(9)` + `waves[8] == ['72']` | **GENUINELY BLOCKED** |
| `test_g0_3_does_not_promote_tasks_milestones_or_g0_4` | 240/15 + `BLOCKED<=3`（实 5）+ `diagnostic_count==5`（实 6） | **GENUINELY BLOCKED** |

**owner**：`workpaper-html-onlyoffice-bidirectional-writeback-closure:program-governance`（G0-3 执行卡自署）

**解阻条件**（四条全满足才可能转绿）：
1. 核心 `tasks.md` 依赖图拆出 Wave 8（仅 `72`，`depends_on: [7]`），把 `72` 移出 Wave 7，再给 `deps["72"]` 加 `"74"`；
2. 任务 `1/2/20/60/62/64` 按 Task 20 自述语义（「门可信 ≠ 债清零」）由 `[x]` 降级 `[~]`；
3. overview 韵文分母改为「77 个主/全任务、9 个 Wave」并删掉陈旧的「74 个任务」；
4. 5 个 BLOCKED milestone 的 producer（`closure:75`、`excel-structural-row…:20`、
   `custom-workpaper…:19`、`excel-template-override…` 的 producer 契约）做完，才能谈 `BLOCKED <= 3`。

**未做的事**：没有改任何 `tasks.md`、没有动 `BLOCKED <= 3` / `448` / `range(9)` / 六个 `~` 任一字面量。

---

## Group 2 · 生成物陈旧

### 2a. writer inventory → **STALE ARTIFACT，已重算**

`generate_workpaper_writer_inventory.py --check` 是**逐字节**新鲜度门：现算 render 与磁盘比对，
不等就 `return 2`。现算 source facts = `rows=371 writers=312 resolvers=84`。

**重算前先量差异形状**（判断是真陈旧还是洗白）：

```
stats identical fresh==disk: True          ← 17 个统计量逐个相同
stats identical disk==HEAD : True
FRESH vs DISK: entries A=371 B=371 added=0 removed=0 changed=2
   changed-field histogram: {'line': 1, 'facts': 1}
```

两条改动逐字列出：

```
oo_to_html::OoToHtmlCoordinator._mirror_d2_store_if_needed
    line: fresh=3307  disk=3294
oo_to_html::OoToHtmlCoordinator._mirror_d4_dual_stores
    facts.swallowed_exception_lines:
        fresh = [2788, 2954, 3008, 3062, 3115, 3168, 3221]
        disk  = [2775, 2941, 2995, 3049, 3102, 3155, 3208]
```

**全部差异 = `oo_to_html.py` 里整体 +13 的行号偏移**，外加 `inventory_digest` / `source_digest` 两个摘要。
0 新增 / 0 删除 / 0 债务数字变化——`bypass_unified_commit=303`、`direct_commit=124`、
`multi_resolver=3`、`non_canonical_resolver_only=76`、`writer_without_test=239` 全部原封不动。

**named reason**：`backend/app/services/workpaper_sync/oo_to_html.py` 在工作树处于 ` M`
（另一 agent 在飞行中），在 2775 行之上插了 13 行。这正是任务书描述的「简单陈旧」形状；
若重算动了几百条不相关行，就该判为**不是**简单陈旧——实测不是那种形状。

```
[APPLIED] backend\data\workpaper_writer_inventory.json sha256=a8a77cb0686aa386
[OK] inventory digest 6ed7718885b9391a238853cce715bb00244da2c24e2c436f6114a7748276495e
```

**变异验证（闸门仍有牙）**——扰动一个行号，闸门必须变红，再用 `--apply` 确定性复原
（不用 `git checkout`）：

```
STEP 1 baseline --check   rc=0 ['[OK] inventory digest 6ed77188…']
STEP 2 perturb "line": 3307 -> 3308
STEP 3 --check (perturbed) rc=2 ['[FAIL] stale generated inventory: … no longer matches source facts']
STEP 4 restore via --apply rc=0 ['[APPLIED] … sha256=a8a77cb0686aa386']
STEP 5 --check             rc=0
byte-identical to pre-mutation: True
MUTATION GUARD HAS TEETH: True
```

### 2b. Task 69 前端回归报告 → **拒绝重算（LAUNDERING RISK + 真阻塞）**

同样先量，不先写。用门自己的 `build_report()`（复用磁盘上昂贵的 `vitest_run` /
`frontend_baseline` 块，与 `--write` 不带 `--run-vitest` 时的行为一致）现算后比对：

```
DISK  verdict: blockers=[]                                  → passed
FRESH verdict: {"result": "failed", "blockers": [
    "反事实多臂里有臂不改变结论 ⇒ 对应判据度量的是别的东西",
    "与上游 deletion plan 的可达性登记不一致：[10 个模块]" ]}
disk == HEAD: True        ← 磁盘报告本身没被手改，就是已提交版本
=== 145 differing paths ===
```

**这不是行号级陈旧，是结论级变化**。摘要：

| 量 | 磁盘（冻结） | 现算 |
|---|---|---|
| `radiation_surface.frontend_files_scanned` | 7188 | **7415**（+227） |
| `radiation_surface.spec_file_count` | 18 | **21**（新增 3 个 spec） |
| `replacement_reachability.modules` | 22 | **25** |
| `recomputed_unreachable_count` | 19 | **10**（9 个模块转为可达） |
| `reachability_cross_check.agrees` | True | **False**（10 个模块与上游 deletion plan 打架） |
| `counterfactual_arms.all_arms_change_conclusion` | True | **False** |

典型翻转：`sync/useWorkpaperSyncBridge.ts`、`sync/usePilotBridgeAdapter.ts` 的
`reachable_from_production_host` 由 `False` → `True`，`production_importer_outside_count`
由 4 → 45（新 importer 是 `GtD1NotesReceivable.vue` / `GtD2AccountsReceivable.vue` /
`GtD3PrepaidAccounts.vue` / `GtD4OperatingRevenue.vue` 等）。
**这正是已推送的 D2/D4/G7/H1 统一路径改造的结果**——生产宿主真的开始 import 统一 bridge 了。

**为什么拒绝重算**：

1. **重算也关不掉这个测试**。`main()` 的收尾是 `if verdict == RESULT_PASSED: return 0`，
   否则 `return 1`。现算 verdict=`failed`，所以 `--write` 之后 `--check` 仍然 `rc=1`，
   `test_gate_check_passes` 照样红。付出代价却买不到绿。
2. **代价是销毁证据**。`--write` 会把 verdict=`failed` 焊进冻结基线，并覆盖当前这份
   verdict=passed 的已提交报告（`disk == HEAD: True`）。同文件另外 78 条测试都从磁盘
   `report()` 读数，改基线的爆炸半径是把 1 红换成一片未知红。
3. **门自己说判据失效了**。`all_arms_change_conclusion: False` 的含义是「某条反事实臂
   已经不再改变结论 ⇒ 它度量的是别的东西」。这要 owner 重新设计那条臂，不是重跑能解决的。

**owner**：Task 69「前端独立回归门」（spec `workpaper-html-onlyoffice-bidirectional-writeback-closure`
Wave 7 Task 69）。
**解阻条件**：①与上游 `legacy_deletion_plan` 的 unreachable 登记对账，把 10 个分歧模块
裁决清（替代面从 22 涨到 25、9 个模块转可达是**真实进展**，登记侧要跟上）；
②重新设计失效的那条反事实臂；③`--write --run-vitest` 真跑一次（分钟级）重采执行记录。
**本 session 未改动** `backend/data/workpaper_sync_task69_frontend_regression.json`。

---

## Group 3 · task44 探测器裁定 → **STALE DETECTOR，已修探测器**

### 事实

`offenders == ['word_instrumentation.py']`。命中点是
`backend/app/services/workpaper_sync/word_instrumentation.py` 第 274–277 行，位于
`_sha256_text_source()` 的 **docstring** 内：

```
    同形修法已在本仓库落地并转绿：`scripts/gen/generate_workpaper_task44_pilot_probe_registry.py`
    的 `_normalize_eol()` 与 `scripts/check/check_task44_oo94_excel_pilot_gate.py`
    的 `read_task_body()`。
```

一句出处说明：0 import、0 调用、0 符号。原探测器是整文件子串扫描
（`"task44" in path.read_bytes().decode("utf-8").lower()`），把散文算成接线。

### 两个选项的爆炸半径

| 选项 | 爆炸半径 | 对牙的影响 |
|---|---|---|
| **(ii) 改写那句注释** | 1 行，仅 `word_instrumentation.py`。但该文件此刻正被另一 agent 改 EOL 修复，编辑有冲突风险；且丢掉一条有用的先例出处；**探测器的错口径留在原地**，下一个引用 task44 先例的人再踩一次 | 不变（仍把散文当接线） |
| **(i) 修探测器忽略注释与 docstring** | 只动测试文件 `test_task44_oo94_excel_pilot_gate.py`；不碰任何生产文件，与另一 agent 的 EOL 修复零冲突 | **变精确**：注释/docstring 物理上无法构成接线，排除它们不丢任何真实检测能力 |

**选 (i)**，并把范围严格限定在「注释 + docstring」：
- 注释根本不进 AST，天然排除；
- docstring 只摘 module/class/function 的 `body[0]` 裸字符串（即 docstring 位）；
- **普通字符串字面量继续参与判定**——否则 `importlib.import_module("…task44…")`、
  `getattr(mod, "task44_probe")` 这类按名动态接线就能从判据里溜掉。把「忽略字符串字面量」
  一起做进去才是真正的削弱，本次刻意没做；
- `SyntaxError` 时 fail-closed 退回整文件原文扫描，绝不因解析不了就放行。

实现：`_wiring_text(source)` 用 `ast.parse` → 摘 docstring → `ast.dump()`。
`ast.dump` 保留全部 identifier（Name/Attribute/FunctionDef/ClassDef/alias/ImportFrom）
与非 docstring 字符串值，不含注释。

### 变异验证（两层）

**① 永久化的探测器牙测试**（新增 `test_the_task44_reference_detector_still_catches_real_wiring`）：
4 种散文形态必须豁免（module/function/class docstring + 注释），8 种接线形态必须命中
（`import` / `from … import` / 属性访问 / 裸名 / `import_module("…")` 按名 /
`getattr(m, "task44_probe")` 按名 / `def load_task44_probe` / 语法错误 fail-closed）。
没有这条，`_wiring_text()` 就是一个可被悄悄放宽成「永远返回空」的旁路。

**② 真目录端到端变异**：在 `app/services/workpaper_sync/` 下临时放一个**真接线**模块，
确认反向锁变红，随即删除并确认复原：

```
# 变异体在位
FAILED …::test_no_workpaper_sync_production_module_references_task_44
  - AssertionError: ['_mutcheck_task44_wiring.py']      ← 红，且点名真凶
# 删除变异体后
5 passed, 107 deselected
git status --porcelain -- app/services/workpaper_sync/_mutcheck_task44_wiring.py  → 空
```

---

## 副作用披露：重算清册**解除了一个被陈旧遮蔽的 blocker**

这条必须单独写，因为它改变了本文件上半部分的一处读数。

重算 writer inventory 让 `writer_gate_facts.source_current` 由 `False` → `True`
（陈旧的清册此前使 writer 门只能报 `stale`，渲染不出真实裁决）。于是投影重算时：

```
重算前 milestone_state_counts: {BLOCKED: 5, IMPLEMENTED: 3, STALE: 8}
重算后 milestone_state_counts: {BLOCKED: 6, IMPLEMENTED: 3, STALE: 7}
新增 BLOCKED = SYNC-MULTI-RESOLVER
  blockers: producer_tasks_incomplete + writer_gate_multi_resolver_nonzero
```

**方向是「债变多」不是「债变少」**：一个原先躲在「清册陈旧」后面的 blocker 变可见了
（`multi_resolver = 3`，owner 核心 spec Task 71）。这与 `milestone-blocked-regression.md`
预测的机制一致，只是那份 evidence 记的是「BLOCKED=4 且由 SYNC-MULTI-RESOLVER 撑起」，
本次实测是 **BLOCKED=6**（5 条 producer 不全 + SYNC-MULTI-RESOLVER）。
对 `BLOCKED <= 3` 的结论无影响：5、6 都远不可达。

**修正上文一处读数**：本文件 Group 1 段记录的「fresh `milestone_state_counts` 与 snapshot
相同（BLOCKED 5）」是**清册重算之前**的测量，现已被 BLOCKED=6 取代。Group 1 的裁定不变。

### 投影重算与变异验证

```
[APPLIED] backend/data/workpaper_sync_program_milestones.json sha256=44dbc6bc9697e25b
[GENERATED] program=STALE specs=8 tasks=263 milestones=16
            states={'BLOCKED': 6, 'IMPLEMENTED': 3, 'STALE': 7} diagnostics=6
落盘产物核对：db status=ok · writer_gate source_current=True · archive_diag=True
```

变异验证：把产物里 `"internal_edge_count": 447` 改成 `448`，`--check` 报
`[FAIL] stale: backend/data/workpaper_sync_program_milestones.json`（rc=2），
写回扰动前字节后复原（byte-identical=True）。

⚠️ **顺带发现一个真 bug（未修，本 session 范围外）**：在**同一进程内**反复调用
`build_program_registry()` 时，数据库探针会**隔次失败**：

```
[FAIL] mandatory database probe did not complete read-only:
       status=database_unavailable phase=connect code=AttributeError
```

失败那一轮 2 个 milestone 由 IMPLEMENTED 掉成 BLOCKED（`{BLOCKED: 8, IMPLEMENTED: 1}`），
即**同一棵树连算两次得到两份不同的投影**。`AttributeError` 发生在 `connect` 阶段，
不是「库不可用」而是探针自身的 engine/连接生命周期问题（首次调用后被 dispose，
再用就炸）。pytest 里 `source` fixture 每模块只建一次，所以测试侧看不到；
但任何「先 apply 再 check」的脚本化用法都会随机踩到。落盘产物已确认是
`db status=ok` 那一轮的结果。**建议另起工单给投影生成器的 owner。**

---

## AFTER 计数（逐文件，verbatim）

```
tests/workpaper_sync/test_workpaper_sync_program_milestones.py
  4 failed, 18 passed, 3 warnings in 78.98s (0:01:18)        ← was 5 failed, 17 passed

tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py
  112 passed, 24 warnings in 340.76s (0:05:40)               ← was 2 failed, 109 passed

tests/workpaper_sync_frontend/test_task69_frontend_regression.py
  1 failed, 78 passed, 1 warning in 10.71s                   ← 未变（拒绝重算）
```

112 = 109 原有 + 2 转绿 + 1 新增探测器牙测试。**三个文件均无新增失败。**

---

## 结论

**8 → 5**：关闭 3 条，拒绝 1 条，真阻塞 4 条。

| 处置 | 数量 | 节点 |
|---|---|---|
| **已关闭（closed）** | **3** | `test_writer_inventory_is_still_fresh`（重算清册）、`test_no_workpaper_sync_production_module_references_task_44`（修探测器）、`test_generated_projection_is_current_and_self_digest_bound`（重算投影） |
| **拒绝（refused）** | **1** | `test_task69_frontend_regression.py::test_gate_check_passes` —— 现算 verdict=`failed`，重算既关不掉测试又会把 failed 焊进冻结基线并威胁同文件 78 条绿 |
| **真阻塞保持红（blocked-with-owner）** | **4** | `test_eight_spec_task_and_dependency_denominators_are_exact`、`test_g0_3_archive_dependency_is_closed_and_mutation_reopens_debt`、`test_g0_3_wave_order_is_valid_and_same_wave_forward_dependency_is_rejected`、`test_g0_3_does_not_promote_tasks_milestones_or_g0_4` |

**named owners**

| 红节点 | owner | 解阻条件 |
|---|---|---|
| Group 1 的 4 条 | `workpaper-html-onlyoffice-bidirectional-writeback-closure:program-governance`（G0-3 执行卡自署） | 核心 `tasks.md` 落 Wave 8 + `72→74` 边 + 六任务 `[x]→[~]` + overview 分母；再清 5 个 BLOCKED milestone 的 producer |
| `SYNC-MULTI-RESOLVER`（新可见） | 核心 spec **Task 71** | `multi_resolver` 由 3 归零（三个 `wp_onlyoffice_router` writer 收敛到单一 canonical resolver） |
| Group 2b task69 | 核心 spec **Task 69** | 与上游 deletion plan 可达性登记对账 10 个分歧模块 + 重设失效反事实臂 + `--write --run-vitest` |

**没做也不会做的事**（红线自查）

- 没有把任何 `tasks.md` 的 `[ ]` 改成 `[x]`；**也没有**反方向把 `[x]` 改成 `[~]` 去凑
  `test_eight_spec…` 的六个 `~` pin —— 后者同样是「改源头去迁就 pin」，且属 program-governance 裁决。
- 没有动 `BLOCKED <= 3`、`internal_edge_count == 448`、`sorted(waves) == range(9)`、
  `diagnostic_count == 5` 任一字面量。`448 = 447 + 缺失的那条治理边`，改它等于抹掉要求。
- 探测器只豁免注释与 docstring，**保留**普通字符串字面量判定，按名动态接线仍被抓。
- 没碰任何 `*_pg.py`；没碰 `workpaper_sync_entry_manifest.json` / overlay / `*.generated.ts`；
  没跑 `setup_wp_templates_dir.py`；没用 `git stash` / `git checkout --` / `git reset`
  （复原一律用生成器 `--apply` 或写回保存的字节）。
- 没删任何非本 session 自建的 `_` 前缀文件；本 session 自建的 6 个探针脚本与 1 个变异体已删净。

**改动文件**

- `backend/data/workpaper_writer_inventory.json`（`--apply` 重算，差异=2 行号 + 2 摘要）
- `backend/data/workpaper_sync_program_milestones.json`（`--apply` 重算，BLOCKED 5→6 为解除遮蔽）
- `backend/tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py`（`_wiring_text()` /
  `_references_task44()` + 新增探测器牙测试）

**遗留观察**：`oo_to_html.py` 仍在另一 agent 手上；它再存一次盘，writer inventory 会再次
陈旧（差异形状仍会是行号级），重跑 `--apply` 即可。投影生成器的数据库探针隔次
`AttributeError` 是独立的真 bug，建议另起工单。

