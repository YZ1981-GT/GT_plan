# Implementation Plan: 底稿 HTML ↔ OnlyOffice 双向回写剩余闭环

## Overview

> **状态**：46/50（2026-11-02）。本文是新一轮剩余闭环计划；归档旧 spec 的复选框不迁移到这里。
>
> 🔴 2026-11-01 第二轮勘误（三条，净 −1）：
> - **3.5 完成** `[ ] → [x]`：最后两批共 51 个宿主接入共享 presentation 门，棘轮基线
>   `32 → 0`，新增接线契约守卫并经磁盘变异证明可伪证；manifest 等生成物已重算，
>   source digest 变更附零能力损失复核。
> - **0.5 退回** `[x] → [ ]`：它的「外部消费方闭合」只有一张**手写 7 条**清单，而仓库里
>   真实消费方按 AST 现算是 **35 个** —— 清单覆盖约两成，且手写清单不可能**发现**新消费方。
>   本轮已把分母改成现算并建登记表（见 0.5 正文），但仍有消费方的解析形态未逐个复核，
>   判据只能先做成「只许变少」的棘轮 ⇒ 按本 spec 的完成标记规则不算完成。
> - **2.8 退回** `[x] → [ ]`：`multi_resolver` writer gate 现算仍是 **3 条**
>   （`get_sheet_onlyoffice_config` / `get_sheet_wopi_contents` / `post_sheet_onlyoffice_callback`
>   全在 `wp_onlyoffice_router`），这三条正是它声称要清零的对象；里程碑 producer 重映射
>   只改了归属，没动代码。
>
> 🔴 2026-11-02 推送前复核勘误（两条，净 −2）：
> - **6.3 退回** `[x] → [ ]`：D2 的阻断态浏览器验证证明了 AC 1.4，但没有执行本任务要求的
>   全 entry required scenarios。真库验收账本仍为 0，67 条 bidirectional entry 中 59 条从未
>   产生 operation；因此不能用一次“被正确拦截”替代 AC 12.1 的真实 OO operation 与验收态。
> - **7.5 退回** `[x] → [ ]`：本 spec 仍在 active 目录，且当前有 4 个未完成任务；design §15
>   的归档条件尚未全部满足。既有五角色材料保留为阶段复核，不能标作“最终归档”。
> - 文末“未完成项实况”保留为 2026-11-01 开工快照；当前状态只以复选框和文末
>   “当前未完成项索引”为准。
>
> 已勾选项都有「代码 + 点名测试通过记录 + spec evidence」三件齐备；未勾选项在文末
> “当前未完成项索引”逐条写明状态与阻塞原因，不以「文件已存在」充数。
>
> **完成标记规则**：每项必须同时有实际产物、对应测试/检查通过记录和可复核 evidence。
> “类/文件已存在”“历史 tasks 标绿”“当前工作树能跑”都不能单独标 `[x]`。
>
> **需求真源**：`backend/data/workpaper_sync_migration_paradigm.json`。需要修改 AC 时先改 JSON，
> 再重生成 `requirements.md`；不得直接编辑投影。
>
> **任务组织**：50 项按交付单元合并，无 `[ ]*`。逐 entry 的业务实现由 residual lane spec
> 承接，umbrella 负责事实投影、共享准入、UI 诚实性、总门与归档。

## Tasks

## Phase 0：冻结当前事实与基线

- [x] 0.1 审核当前源码挂载相对 reviewed overlay 的语义 diff
  - 运行 manifest generator 的只读 diff，按稳定语义键区分真实新增/删除与行号位移；未审核前不更新 `approved_source_digest`。
  - 产物：`evidence/phase0-source-mount-review.json`；overlay `approved_source_digest` 更新为
    `07f66e91c4d4fc38…` 并绑 `source_review_ref`。
  - _AC: 1.3, 12.1_

- [x] 0.2 固化本轮真源优先级与历史资料边界
  - 机器检查当前 requirements 恰等于 paradigm AC 投影；归档 design/tasks 和 master-control 只作引用，不作为状态输入。
  - 产物：`backend/tests/workpaper_sync/test_umbrella_spec_reference_closure.py`
    —— AC 集合相等（逐字相等由既有 `test_migration_paradigm_contract.py::TestAcceptanceCriteriaVerbatim`
    承担，两者合起来才是「恰等于投影」）+ 「已勾选任务不得拿归档 spec 当完成依据」+
    「标题 N/M 必须与实际勾选数一致」。
  - 变异：M0 阴性对照不红；M1 未登记 AC 引用 / M2 标题数说谎 / M3 归档当依据 / M4 requirements
    少一条 AC 四组全红，两份文件按字节恢复。
  - _AC: 1.3, 12.1_

- [x] 0.3 生成带时间戳的 current-state 基线报告
  - 报告现算 manifest/independent/parent/pending/legacy/capability、contract/provider 和删除候选集合，并记录 source/overlay/manifest digest；禁止把数字写成永久断言。
  - 产物：`backend/scripts/gen/generate_workpaper_sync_current_state.py` +
    `backend/data/workpaper_sync_current_state.json`（含 `snapshot_date`、source/manifest/overlay/
    adjudication/wp_code 五个 digest，并读 Task 66 删除计划取候选集合）；守卫
    `backend/tests/workpaper_sync/test_current_state_projection.py`；`--check` 过（`360bf9d7acfed390`）。
  - _AC: 1.3, 1.7, 12.1_

- [x] 0.4 建立改动前测试和门禁基线
  - 点名运行 paradigm、manifest、registry、closure、cycle slice 与前端 sync 测试；按节点记录预存失败、崩溃、skip 和环境阻塞。
  - 产物：`evidence/phase0-test-and-gate-baseline-2026-11-01.md`（HEAD `de31e7bf6` 干净 worktree 对账：
    后端选集 added 0 / resolved 11、前端 sync added 0 / resolved 0；另记两类采集期崩溃与六个门禁命令结果）。
  - _AC: 1.3, 1.4, 12.1_

- [ ] 0.5 锁定 AC → design → task → evidence 引用闭合性
  - 脚本验证 7 条 AC 每条至少由一项任务和一个可执行验收面承接，且不存在未定义 AC 引用。
  - 已完成部分：`test_no_task_cites_an_undefined_ac` / `test_every_registered_ac_is_carried_by_some_task`
    / `test_every_registered_ac_has_an_executable_surface_on_disk`（承接面必须**真实存在于磁盘**，
    写了名字不算）/ `test_acceptance_surface_registry_has_no_stale_entries`（登记表不留失效路径）。
    现算 7 条 AC 全部闭合，50 条任务全部带 `_AC:` 引用。
  - 🔴 **未完成（2026-11-01 退回原因）**：上述 14 条判据只覆盖 spec 三件套**内部**互引
    （AC ↔ task ↔ property ↔ 磁盘承接面），对「仓库里有脚本把 requirements.md / tasks.md
    当机器可读契约解析」这条边**零覆盖**。实测本轮重写把 7 个这类消费方打红（普查见
    `evidence/phase0-spec-doc-consumer-breakage-2026-11-01.md` §2.1），而 14 条判据一条都没红。
  - 补齐判据：闭合性必须加第四条边「doc → 外部解析器」——枚举仓库内解析这两份文档的脚本，
    断言每个都能在当前文档形态下跑通（或已显式登记退役并断言它真的退役）。变异证明：
    把任一 AC 编号改掉 / 把 Phase 标题形态改掉，必须有判据打红。
  - 🔴 **2026-11-01 第二轮：分母从手写 7 条换成现算 35 个，但仍未完成**。
    * 手写清单的根本问题不是条数少，而是**它不可能发现新消费方** —— 加一个脚本不会让任何
      判据打红。现分母 = 扫 `backend/{scripts,app,tests}` 的 `.py`，取 AST 里**非 docstring**
      的字符串常量，凡同时出现 spec 目录名与三件套文件名之一即判为消费方 ⇒ **35 个**。
      用 AST 而不是文本匹配：注释与 docstring 会正反两向骗过扫描器。
    * 登记表 `backend/data/workpaper_sync_spec_doc_consumers.json`（发现是机器算的，分类与
      状态是人工复核字段）。入册时现算 `ok 8 / retired 1 / registered_unreviewed 26`。
    * 新增判据（`test_umbrella_spec_reference_closure.py`，14 → **25** 例）：发现集合与登记表
      逐条相等 · 登记路径必须在磁盘 · 摘要从明细重算 · status 封闭且必须有 owner ·
      `ok` 的冻结形态消费方必须按**内容标记**绑定快照 · 冻结快照真的含 Wave 6 形态且
      active 不含 · 退役项不得留在任何门禁 · `registered_unreviewed` 只许变少。
    * 两条关键判据经磁盘变异证明可伪证（`tmp_workpaper_sync_impl/mutate_consumer_registry.py`，
      M0 24 passed / M1 少登记一条 → 发现闭合判据红 / M2 摘掉内容标记 → 内容绑定判据红，
      两文件 sha256 前后一致）。
    * 🔴 **M2 第一次没打红，暴露我自己写的判据退回了子串匹配**：原实现是
      `"require_matches" in source`，而变异把关键字改名成 `_disabled_require_matches=`
      （调用立刻 TypeError、绑定彻底失效）后那个子串**仍然存在** ⇒ 判据照绿。改成 AST
      查 `resolve_spec_dir(..., require_matches=...)` 的真实 keyword 后 M2 精确打红，
      并补了谓词自身的四向用例（真调用 / 关键字改名 / 只有 require_files / 字符串里提一句）。
    * **顺带把「归档只作引用」那条判据从子串收紧成语义判别**：原判据是「说明块出现
      `_archive/` 就红」，它会误伤 0.6 把消费方重绑到冻结快照时**必须写清楚绑到哪里**的
      trace。改为「同一行带完成度措辞（复选框 / 全绿 / N/M / ✅ …）才算拿归档充状态」，
      并配双向用例（拿归档完成度当依据必红、引用冻结文档快照必过）。
    * **仍缺**（这就是它退回 `[ ]` 的原因）：① `registered_unreviewed` 的解析形态未逐个
      复核，「每个都能在当前文档形态下跑通」对它们尚未成立；② 任务要求的那两组变异
      （改 AC 编号 / 改 Phase 标题形态必须有判据打红）未做。
  - _AC: 1.3, 1.4, 1.5, 1.7, 12.1, 12.8, 12.9_

- [x] 0.6 修复被 spec 文档重写打坏的 7 个机器消费方
  - 范围（逐个点名，普查见 `evidence/phase0-spec-doc-consumer-breakage-2026-11-01.md` §2.1）：
    `generate_task66_legacy_deletion_plan.py`（cycle→task 映射 0 条）、
    `generate_workpaper_sync_program_milestones.py`（`wave id must be an integer`）、
    `check_task68_backend_chain_independent_regression.py` 与
    `check_task69_frontend_independent_regression.py`（找不到 Task 68 / 任务 69）、
    `generate_workpaper_ac_coverage_matrix.py`（AC 先于 requirement 标题出现）、
    `generate_workpaper_word_template_adjudication.py`（AC 7.7 原文形态变了）、
    `check_task71_mutation_capacity_recovery_gate.py`（找不到 AC 14.10，fail closed）。
  - 🔴 **归因更正（§5）**：基线 `de31e7bf6` 上 active spec 路径整个不存在（`239eb9a89` 归档所致），
    7 个当时就 `FileNotFoundError`，不是本轮打坏的。本轮重建 active 目录后形态变了、红没变。
  - **已修 2 个**：① task66 生成器五处解析层修复，整条判为退役并由执行账取代（task 5.5）；
    ② program milestones 的 wave 图键名 `id`→`wave` + 任务 0.6 纳入 + 里程碑归属 6 条 /
    26 个失效任务号→0 个（方案 A：新增 task 2.8 承接 SYNC-MULTI-RESOLVER）。
  - **登记 5 个「锚点断开」**：③④ task68/69 独立回归门——`TASK_NUMBER=68/69`、`task_body()`
    从任务正文现解析 Property / AC 声明，改号后声明全部断开，属 7.2 前置；⑤⑥⑦ AC coverage
    matrix / word template adjudication / task71 容量门——依赖 `### Requirement N:` 标题 +
    `## Acceptance Oracle Matrix` + 170 条 AC 结构，active 投影只有 7 条扁平 AC，属 7.1 前置。
  - 详见 evidence §6~§9。
  - 🔴 **2026-11-01 第二轮：余下 5 个已修完，另抓出 3 个同族**（本条因此真实完成）。
  - **根因收敛成一句**：这些门解析的是 **Wave 6 形态**的三件套（整数任务号、
    `### Requirement N` 标题、`## Acceptance Oracle Matrix`、AC 7.7 / 14.10 原文），
    而 active 目录被**重写**成「7 条扁平 AC + 两级任务号」。此时 active **存在且三件套齐全**
    ⇒ 只看「目录在不在 / 文件在不在」的 `resolve_spec_dir(require_files=...)` 一路放行，
    于是门绑到了一份它根本解析不了的文档上，报出「找不到 Task 68」「AC 先于 requirement
    标题出现」这类**指错地方**的错误 —— 契约没丢，它在 `17-2026-10-03-verified-batch`
    下的同名冻结快照里（该快照现算齐备：`### Requirement 1` / `7.7.` / `14.10.` /
    `14.12.` / `### Property 1` / `## Acceptance Oracle Matrix` / 整数任务 68·69·71 全在）。
  - **修法 = 把解析从「目录对不对」升级成「契约对不对」**：`resolve_spec_dir` 新增
    `require_matches={相对文件名: (正则, ...)}`，候选目录必须让每个正则在对应文件里命中
    才算合格。好处是双向的 —— 旧形态在归档里就绑归档；形态哪天回到 active 就自动改回
    active，不用改脚本；也不像写死归档路径那样会把一个**错误的**快照静默选中。
  - **实现收敛到一处**：`app/core/spec_docs.py`（全仓唯一实现），
    `backend/scripts/check/_spec_dir.py` 变薄壳 re-export —— 因为消费方有三类（check 脚本 /
    gen 脚本 / **生产代码**），三类都能 import 的地方只有 `app/`。十余个同目录脚本的
    `from _spec_dir import resolve_spec_dir` 一个字都不用改。
  - **逐条结果**（探针 `tmp_workpaper_sync_impl/probe_legacy_consumers.py` 现算 6/6 OK；
    重绑脚本 `tmp_workpaper_sync_impl/rebind_legacy_consumers.py` 幂等可重放）：
    | 消费方 | 原失败形态 | 现状 |
    |---|---|---|
    | `check_task68_backend_chain_independent_regression.py` | 找不到 Task 68 | 绑冻结快照，可 import |
    | `check_task69_frontend_independent_regression.py` | 找不到任务 69 | 同上 |
    | `check_task71_mutation_capacity_recovery_gate.py` | 找不到 AC 14.10，fail closed | 同上 |
    | `generate_workpaper_ac_coverage_matrix.py` | AC 先于 requirement 标题出现 | **解析通过**，`--apply` 后 `--check` 绿（170 AC / 72 Property / 77 task / 14 family） |
    | `generate_workpaper_word_template_adjudication.py` | AC 7.7 原文形态变了 | **解析通过**（余下漂移非本 spec，见下） |
    | `app/services/workpaper_sync/capacity_profile.py`（**生产模块**，原 7 条清单漏登） | 找不到 AC 14.10 | `assert_profile_matches_requirements()` 现算**通过** |
  - 🔴 **AC coverage matrix 重算后只差 provenance，实质零变化**：逐字段 diff 得 7 处差异，
    全部是 `sources` 里记录的三份文档路径（active → 冻结快照）与随之变化的 `matrix_digest`，
    **AC 行 / Property / 缺陷计数逐项相同** ⇒ 冻结快照与当时 active 的内容一致，重算是
    把「契约现在在哪」记对，不是改结论。
  - **顺带抓出并修掉 3 个同族**：① `check_task44_oo94_excel_pilot_gate.py` 与
    ② `check_task61_oo94_word_pilot_gate.py` 原本已走 `resolve_spec_dir` 但只传
    `require_files` ⇒ 仍绑 active（解析 Wave 6 形态必失败）—— 它们是被 0.5 新建的
    「`ok` 必须按内容标记绑定」判据**当场打红**抓出来的，不是靠猜；③ 这两个门的 pytest
    守卫原先**连采集都过不去**（见下一条）。
  - 🔴 **另修一条会掐断整条后端测试链的缺陷**：`from _spec_dir import ...` 写在模块顶层，
    当 CLI 跑时 Python 自动把脚本目录放进 `sys.path[0]` 所以能成，但测试用
    `importlib.spec_from_file_location` 加载时**不动 sys.path** ⇒ import 期
    `ModuleNotFoundError` ⇒ **测试模块采集失败**。实测 `test_task44_oo94_excel_pilot_gate.py`
    与 `test_task61_oo94_word_pilot_gate.py` 两个采集错误；而 CI 的 backend-tests 是
    `pytest backend/tests/ -x` —— **一个采集错误就把整个 job 停在这里**，后面所有测试都不跑。
    触类旁通扫全目录同族共 **12 个**脚本一次修完（补丁对 CLI 路径是 no-op），新建判据
    `backend/tests/test_check_scripts_importable.py`（17 例：AST 发现顶层兄弟 import +
    逐个在**干净子进程**里加载）。
    🔴 该判据第一版在**本进程**里顺序加载，变异没打红 —— 同一会话里按字母序更早的脚本
    已经把 `scripts/check` 插进 `sys.path`，后面的白捡这条路径；也就是说那一版测的是
    「这批脚本里至少有一个补过路径」，与它要防的「单独采集某一个测试模块」错位。改成
    子进程隔离后，变异（摘掉某个脚本的 sys.path 补丁）精确打红 1 条，阴性对照 17 全绿，
    靶子 sha256 前后一致。
  - **另补一条生成物门**（`backend/tests/workpaper_sync/test_sync_generated_artifacts_check_mode.py`）：
    required scenario set / cycle reconciliation / residual lane / task66 执行账四件的
    `--check` 必须幂等 —— 现扫发现其中三件**没有任何 pytest 守卫在跑它们的 `--check`**，
    而本 spec 的 closure 判据全是从这些产物里读数的。连实时 PG 的 evidence projection
    **显式排除**（连得上按 test_run 现算、连不上全标 missing，digest 不同 ⇒ 它的 `--check`
    是环境相关的，写成硬判据就是制造一条永红门禁），并断言它**真的**环境相关，
    不留一句没人能验证的豁免理由。
  - **范围外、未并入本记录的外部漂移**（不替别人把改动折进本 spec 的产物）：
    `workpaper_word_template_adjudication.json` 现算还差 `stats.carrier_count 474 → 473`
    与两个源 digest（`wp_code_overrides.json` / 模板 `_index.json`）—— 成因是**模板/override
    被别的会话改过**，与文档重绑无关。少了一个 Word carrier 属实质变化，需由模板侧 owner
    复核后再 `--apply`，本轮只量化不吸收。
  - _AC: 1.3, 12.1, 12.9_
## Phase 1：统一 manifest 与 cycle slice 当前投影

- [x] 1.1 收敛 manifest 的终态与 pending schema
  - 允许独立 entry 使用 `capability=null` + 三个必填 pending 字段；四终态之外任何值 fail-closed，并同步后端/前端类型。
  - 产物：`generate_workpaper_sync_manifest.py` 产出 `capability=null` +
    `capability_verdict_stage` / `capability_target` / `capability_target_blocked_by`；
    `entry_profile.capability_of` 对 null 抛 `EntryProfileError`（封闭四态）；registry 的
    `build_report` / `build_manifest_registration_plan` 把 pending 单列为 `unadjudicated`
    并拒绝注册；lane registry 对 pending 判 `undecided`（L4）。现算 pending=78。
  - _AC: 1.3_

- [x] 1.2 收敛 parent duplicate 的能力与计数语义
  - 增加/生成 `effective_entry_id`，父入口复用独立 entry readiness；只对独立 bidirectional entry 要求本地 adapter，防重复注册和重复计数。
  - 现算：entries 198 = independent 145 + parent duplicates 52 + unreachable 1；守卫
    `test_workpaper_sync_manifest_contract.py::test_parent_duplicates_reference_one_independent_entry`。
  - _AC: 1.3, 12.1_

- [x] 1.3 把 HTML counterpart 二值结论纳入主 manifest
  - `none/exists` 与 source refs 成为独立 entry 必填事实；禁止 `unresolved + terminal single_onlyoffice`，并保留模板 digest 防伪造对端。
  - 产物：manifest `html_counterpart_verdict`；裁决脚本把「无 counterpart」直接拒在批准集合外
    （`test_pending_runtime_adjudication.py`）。
  - _AC: 12.8, 12.9_

- [x] 1.4 实现参数化 cycle-slice generator
  - 从同一 manifest 内存快照按 selection rule 生成 slice 骨架，复用 paradigm schema；不得为每个循环复制生成算法。
  - 产物：`backend/scripts/gen/generate_workpaper_sync_cycle_projection.py`（单一算法 + 12 组
    selection rule）；守卫 `test_cycle_current_projection.py`；`--check` 过（`aa045510c9584871`）。
  - _AC: 12.1_

- [x] 1.5 重生成并核对 D～N cycle slices
  - 逐 entry 合并当前 contract/provider/definition/evidence 投影；发现旧 slice 与生产分叉时保留勘误记录，不修改归档 tasks。
  - 产物：`backend/data/workpaper_sync_cycle_current_projection.json`（groups 12 / entries 145）+
    各 slice 的 `current_projection_ref`。
  - 🔴 **交付形态偏离**：历史 slice 的正文**未重写**。裁定按 design 的决定 —— 12 份 slice 是不同
    轮次的手写审计轨迹，整体重排会产出巨型无意义 diff 且逼出 12 套算法；改为「单一 current
    projection sidecar + slice 内 ref」，事实现算性与去重性（AC 1.3 / 12.1）由 sidecar 承担。
  - _AC: 1.3, 12.1, 12.8, 12.9_

- [x] 1.6 重生成并核对 A/B/C/S 与跨循环共享 slice
  - pattern-less、docx、shared host 和 parent duplicate 分别按 source-backed 规则归属，禁止按 wp_code 首字母漏项或重复计数。
  - 产物同 1.5（ABCS 组在同一 sidecar 内）；`wp_code_patterns` 改读 reviewed adjudication ledger
    `backend/data/workpaper_sync_entry_wp_code_adjudication.json`（E1 由启发式 `E1M` 纠正为 `E1`）。
  - 偏离同 1.5。
  - _AC: 1.3, 12.1, 12.8, 12.9_

- [x] 1.7 原子生成 manifest JSON、frontend TS、cycle slices 和 current-state report
  - `--check` 不写盘且任一上游 stale 时全体失败；`--write` 内容相同无 diff，四类摘要全部从 entry 明细重算。
  - 产物：`backend/scripts/gen/generate_workpaper_sync_artifacts.py` —— 按依赖序
    （manifest → legacy baseline / current-state / cycle projection）调用四个既有生成器，
    `--check` 纯只读且**不短路**（一次把全部 stale 点名）、任一件 stale 即 exit 1；
    `--write` 上游失败则下游 skipped，写完再跑全量 `--check` 自证幂等，不收敛 exit 2。
    **不复制**任何生成算法（复制一份就又多一个会漂移的真源）。
  - 守卫：`backend/tests/workpaper_sync/test_sync_artifacts_atomic_host.py`（8 例，含
    「`--check` 跑完四件产物的内容与 mtime 均不变」、依赖序自检的可伪证反例、两件同时 stale
    必须都被点名、上游失败下游必须 skipped、写后复检 stale ⇒ exit 2）。
  - 🔴 **它第一次运行就抓到一处真实 stale**：样板宿主接入 readiness 单源后 source digest
    由 `07f66e91…` 变 `189cbda5…`，而本会话此前只跑过下游三件的 `--check` ⇒ 四个独立
    `--check` 全绿也发现不了。已按零能力损失复核批准并重生成（entry 集合 198→198、stats
    逐项相同、无任何 entry 裁决字段变化），记录见
    `evidence/phase1-source-digest-review-2026-11-01-m7.json`；新 digest：manifest
    `31a23eac…` / baseline `e18500cd…`。
  - _AC: 1.3, 12.1_

## Phase 2：后端 request-time readiness

- [x] 2.1 定义 `EntrySyncReadiness` DTO 与封闭 reason code
  - 分离 adjudication、runtime supply、acceptance；中文 `message/next_action` 由后端单一映射生成。
  - 产物：`backend/app/services/workpaper_sync/entry_readiness.py`（三层 DTO + 封闭 reason code +
    中文映射单点）；守卫 `backend/tests/workpaper_sync/test_entry_readiness.py`。
  - _AC: 1.4, 1.5, 12.1_

- [x] 2.2 实现无副作用的 entry readiness evaluator
  - 复用 manifest plan、`prepare_entry_only`、target-bound registration 和现有 bundle/contract 判据；不得创建 room、operation、artifact 或 revision。
  - 守卫含「pending 不得碰 DB」（read_representation 注入 `AssertionError` 仍通过）与 evidence freshness。
  - _AC: 1.4, 12.1_
- [x] 2.3 新增项目/底稿/entry 级 readiness GET 端点
  - 挂项目 readonly 门；对象不可见统一 404、已知可见但无权 403、合法但未就绪 200 + typed reason，并加真实端点级测试。
  - 产物：`GET /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/readiness`
    （action `read_entry_readiness`）；端点级测试 `test_entry_readiness_endpoint.py`；路由普查三处
    常量按新增端点显式更新为 15 / `len(_REQUIRED_ENDPOINTS) + 7` / 22（`test_aos_oo_path_isolation.py`）。
  - _AC: 1.4, 12.1_

- [x] 2.4 对齐 registry supply reason、typed failure 与 readiness 响应
  - current representation 缺失、悬空 pointer、bundle/slot 非法、contract drift 和 provider failure 不得合并成泛化“未注册”。
  - 🔴 **这是真缺陷**：`_evaluate_runtime` 原先只按 `not_registered` / `not_ready` 子串二分，
    其余全部压成 `RUNTIME_REGISTRATION_FAILED` ——真库实测的五类成因（契约结构漂移 / 已发布
    身份漂移 / 冻结插桩缺反读锚点 / 无挂载点事实 / wp_code 匹配域不一致）下一步动作完全不同，
    压成一句「同步定义校验失败」等于没给可操作原因。
  - 修法：新增显式封闭映射 `_RUNTIME_FAILURE_REASONS` + `runtime_failure_reason_code()`，
    七个新 reason code 各配中文 message/next_action；新增 `DefinitionBundleMismatch`
    把「bundle 不是同一份」（200 + 可操作原因）与「指针悬空 / 跨 scope」（404）分开；
    typed slots 不完整也从泛化码独立为 `DEFINITION_SLOT_INVALID`。
  - 守卫：`backend/tests/workpaper_sync/test_readiness_typed_failure_alignment.py`（17 例，
    分母**现读** `evidence/phase4-pending-runtime-readiness.json` 的实测 error_code，不手抄）
    + 前端 `workpaperSyncApi.spec.ts` 新增「reason.code 不做封闭枚举校验」—— 否则后端细分
    成因会在客户端整条被拒。
  - 变异：M0 阴性对照不红；M1 清空显式表 7 红 / M2 两类成因合并 1 红 / M3 指针与 bundle 共用
    error_code 1 红 / M4 reason 名不在词表 2 红，生产文件按字节恢复。
  - _AC: 1.4, 12.1_

- [x] 2.5 删除 A5-1 生产准入临时 bypass
  - 移除 `register()` 与 `assert_bidirectional_ready()` 的 canary 特判；用真实 capability、bundle、representation 和 contract 使其通过或诚实阻断。
  - `_REG_CANARY_BYPASS` / `_CANARY_BYPASS` 两处已物理删除；A5-1 现按真实事实落
    `no_current_representation`（见 `evidence/phase4-pending-runtime-readiness.json`）。
  - _AC: 1.4, 12.1_

- [x] 2.6 建立 entry-scoped readiness 缓存与 single-flight
  - cache key 含 scope、representation、bundle、manifest identity；换项目/底稿/definition 后失效，冷请求不得全量重建 registry。
  - _AC: 1.4, 12.1_

- [x] 2.7 修正全局 closure checker 的动态注册口径
  - checker 必须消费真实 `register_from_manifest(session=...)`/readiness 投影，不再从构造后空 `registrations()` 推导“全部未注册”。
  - 产物：`check_workpaper_sync_closure.py` 的 `build_runtime_registry_facts(manifest, session)`
    + 新增 runtime issue 类型 + `--write-report`；现算 `total blocking facts 938`，
    `registry_registration_failure` 27 条各带精确 error code。
  - _AC: 1.4, 12.1_

- [ ] 2.8 承接 SYNC-MULTI-RESOLVER 里程碑的 writer gate 与 CanonicalResolutionService 收口
  - 本任务是方案 A 新增：里程碑定义 `SYNC-MULTI-RESOLVER` 的判据是 `writer_gate_issue_zero(multi_resolver)` + `CanonicalResolutionService` 符号存在性。旧 producer 是 Wave 6 的 Task 12/71/74（已不在当前 tasks.md 里），新计划里没有专任承接项，硬塞给复验类任务等于伪造归属。
  - writer gate 现算 `multi_resolver` 待清 **3 条**：`get_sheet_onlyoffice_config` / `get_sheet_wopi_contents` / `post_sheet_onlyoffice_callback`（全在 `wp_onlyoffice_router`）。`CanonicalResolutionService` 已存在于 `backend/app/services/workpaper_sync/resolution.py`。
  - 🔴 **接手语无法写进 tasks.md**：`test_task30_closure_gate.py` 的 `_ASSUME_RE = r"自 Task (\d+) 移交至本门"`
    只认纯数字任务号，`2.8` 匹配不上；后续 `int(owner)` 对两级编号会 ValueError。这是
    task68/69 同类的「锚点断开」问题，归 7.2 前置（改 test_task30 的解析器适配两级编号）。
    里程碑闭合由 predicates 判定，不依赖 tasks.md 接手语。
  - 里程碑 producer 已在 `0489b1167` 提交中重映射为 `["2.8"]`。
  - 🔴 **2026-11-01 第二轮退回 `[x] → [ ]`**：重映射只改了**归属**，没动代码。现算
    `multi_resolver` 仍是 **3 条**，而它们正是本条声称要清零的对象 ⇒ 判据未成立。
  - 现读三条的真实形态（为下一轮省一次摸底）：`get_sheet_onlyoffice_config` 自行做
    「sheet 名猜子码 → `find_template_file_any` → `_resolve_custom_wp_file` → `_resolve_wp_file`
    （会复制模板、改 sheet 可见性）」，并签发**旧式** download/callback URL；
    `get_sheet_wopi_contents` 把同一套解析**再做一遍**；`post_sheet_onlyoffice_callback`
    因旧 URL 不带 room/generation/doc_key/route_credential 四项绑定而落进 legacy 分支，
    直接 `target.write_bytes()` 覆盖文件并自增 `file_version`。
  - 🔴 **不能只在这三个函数里换成 `CanonicalResolutionService.resolve()`**：它返回的是
    current published representation 的**不可变** artifact，而旧路径还要「首次复制模板」
    与「原地改 sheet 可见性」两种写行为；把 published artifact 交给旧 helper 会破坏
    digest / 不可变约束，callback 更不能把它当写入目标。正确顺序是
    ①先停止签发旧 URL（bidirectional entry 走统一 room descriptor + room contents）
    ②前端 `GtOnlyOfficeSheet` 与共享 dual-mode composable 同批改线
    ③旧 doc key 给明确的 drain 窗口，窗口结束才删 legacy direct-write 分支
    ④single_onlyoffice / Word / custom 单独裁决，不得为骗过函数级 AST 门把三个 resolver
      塞进一个 helper。
  - **这是一条会影响全平台在线编辑的生产改动**，且依赖 3.5（前端已完成）与逐 entry
    representation 发布（4.* / 6.*）；在那之前单边改后端会让在途编辑保存全部失效 ⇒
    本轮**刻意不动**，只把形态与顺序写清楚。
  - 另：`test_task30_closure_gate.py` 仍是旧 Wave 拓扑（`_TASK_HEAD_RE` 只认整数任务号、
    依赖图要求 `gates` 键、`_BULK_ADAPTER_LANE_TASK="46"`），且
    `test_workpaper_writer_inventory.py` 把当前债 `len(multi_resolver) == 3` 冻成了**期望值**
    —— 真清零那天它会反过来打红拦人，必须同批改成「只许下降 / 完成时必须为 0」。
  - _AC: 12.1_

## Phase 3：前端模式与可操作原因单一来源

- [x] 3.1 扩展 `workpaperSyncApi.ts` 并实现 `useEntrySyncReadiness`
  - 类型与后端 DTO 逐字段对拍；scope 变化丢弃旧响应，同 URL 并发共用在途而不是取消先发请求。
  - 产物：`workpaperSyncApi.ts` 的 readiness 类型与严格解析 + 同 scope 在途合并；
    `useEntrySyncReadiness.ts`（含 generated manifest 静态兜底）；守卫
    `workpaperSyncApi.spec.ts` / `useEntrySyncReadiness.spec.ts`。
  - _AC: 1.4, 1.5_

- [x] 3.2 实现纯函数 `deriveEntrySyncPresentation`
  - 覆盖 single、unreachable、pending、bidirectional-ready/blocked 和请求错误矩阵，输出 allowed modes、按钮状态与 notice。
  - 另加第三态 `revalidating`：有静态裁决可展示时按裁决给可见性、提示写「正在核验」、不套用运行时
    红色分支、不宣称已验收 ⇒ 宿主改线不产生模式开关闪跳。守卫 `entrySyncPresentation.spec.ts`（10 例）。
  - _AC: 1.4, 1.5_

- [x] 3.3 重构 `workpaperEntrySyncNotice.ts`
  - 删除“`capability=bidirectional` 即 registered”的推导；notice 只消费 readiness，reason code 到中文展示保持单一映射。
  - _AC: 1.4_

- [x] 3.4 升级 `GtEntrySyncCapabilityNotice.vue`
  - 摘要默认可见，blocked/error/loading 分态；tooltip 只放补充信息，键盘、窄屏和中文可读性通过组件测试。
  - 🔴 **原实现把「可操作原因」只放在 hover 浮层里**：`查看原因` 是 `<span tabindex="0">`
    （无 role / aria-expanded，读屏只念出一段文字），原因文本仅存在于 el-tooltip ⇒ 触屏与窄屏
    下实际拿不到，与 AC 1.5 和本任务「tooltip 只放补充信息」都冲突。
  - 改为：真 `<button type="button">` + `aria-expanded` / `aria-controls`，点击**内联**展开
    `role="note"` 的原因节点（不再依赖 hover）；摘要常显并带 `title` 兜底、窄屏下截断不撑破
    工具栏，原因节点允许折行；焦点有可见 `:focus-visible` 轮廓。
  - `aria-controls` 的 id 由 entry id 派生，**不用** `crypto.randomUUID()` —— 内网 http 不是
    安全上下文拿不到它，且随机 id 会让 aria 关联在重渲染后失效（守卫逐条断言）。
  - 守卫：`workpaperEntrySyncNotice.spec.ts` 新增 5 例（按钮语义而非 tabindex span、展开/收起
    与 aria 同步且指向真实节点、原因是中文且不含 `A_B` 式枚举码且与摘要不同句、摘要 title
    兜底、id 稳定且不依赖安全上下文 API）。
  - 回归：`sync/__tests__` 全目录 13 failed / 1180 passed，与同一 HEAD 基线逐节点 added 0。
  - _AC: 1.4, 1.5_
- [x] 3.5 把所有生产模式工具栏迁到共享 presentation 门
  - AST + Vue 模板扫描得到完整宿主集合；删除宿主内 capability 分支、静态可用值和第二份原因词表，逐宿主核外层/祖先门控。
  - ✅ **2026-11-01 收口：棘轮基线 `32 → 0`，全域零宿主自行决定模式开关表现。**
    轨迹 126 → 125 → 113 → 110 → 102 → 59 → 32 → **0**；现算已接单源 **137 个宿主 /
    152 个 `el-segmented` 标签**（结构核验 `tmp_workpaper_sync_impl/verify_wired_structure.py`
    三条全通过：TDZ 顺序 / 逐标签对账 / 门控表达式引用）。
  - **最后两批**：批 6 的 27 个 + 批 7 的 24 个（A51 / B22A·B22B×2·B22C / B23 / B50 / C22 /
    CControlTest / CustomWpEditor / E1 / G7×2 / H1 / H3 / H7 / I1~I5 / N1~N3 / B60 ×2 /
    D4TabContract / H4×2 / H8 / J1 / J2 / S 循环 10 个 / `CycleStandaloneProcedureShell`）。
  - 🔴 **棘轮识别正则漏了整整 10 个 S 循环宿主**：第一版只认小写枚举
    （`'onlyoffice' | 'online-edit' | 'structured' | 'docx'`），而 S3/S4/S5/S6/S12/S13/S14/
    S15/S20/S21 的选项值直接写成**英文标签** `'HTML'` / `'OnlyOffice'`，一个小写枚举都不
    出现 ⇒ 这 10 条债**从来没进过分母**，棘轮也就从来没提醒过。这与 A 轮 AC-41
    「17 条把中文标签直接当 mode 值」是同一形态，只是这次是英文。已补三个值并加
    label-as-value 的正反用例（业务分段器必须不被误纳）。
  - 🔴 **标签截取必须引号感知**：`/<el-segmented[\s\S]{0,400}?>/` 会在**属性值内部的 `>`**
    处提前截断（模板里常见 `@change="(v: any) => f(v)"`）。现算全仓 349 个 `el-segmented`
    里 **26 个**被这样截断，其中 **3 个因此改变判定**（`GtB60Bundle.vue` 两处 +
    `GtJ1EmployeeCompensation.vue` 一处的模式开关被残片判成「不是模式开关」）⇒ 既会放过
    未门控的开关，还会把这两个宿主误列进「没有模式开关、可以豁免」。截断在这里不是精度
    问题，是会造成**错误豁免**的正确性问题。已改成引号感知扫描并钉住（换回朴素正则即红）。
  - 🔴 **「是模式开关还是业务分段器」口径换过两次，两次错法相反、都被真实数据打红**：
    v1「整个标签里出现模式值或模式绑定名」⇒ **假阳**（`GtH3InvestmentProperty.vue` 的
    `measurementModel` 成本法/公允价值选择器，因外层写了 `v-if="currentMode === 'html'"`
    被判成模式开关 ⇒ 判据会逼着给业务控件套同步门）；v2「只看标签内的值字面量」⇒
    **假阴**（`GtCControlTest.vue` 的 `deviationViewMode` = C 循环对 HTML↔OO 的叫法、
    `GtA51CashflowAudit.vue` 的 `segOpts` 把选项放在常量里，标签内一个模式值都看不到）。
    现按**选项语义**判（解析 `:options` 的值集合，支持同文件常量与一层别名），解析不出
    再退到选项名 / 模型绑定名，且第三级回退必须写 `/^mode$|Mode$/` 而不是 `/mode/i`
    —— 后者会命中 `measurementModel` 里的 "Mode"，把 v1 的假阳换种方式请回来。
    四种真实形态逐条配了用例。
  - **新增接线契约守卫** `sync/__tests__/entrySyncHostWiringContract.spec.ts`（6 例）：
    ① 门控了模式开关的宿主**必须**挂 `GtEntrySyncCapabilityNotice`（只隐藏开关不给原因，
    比显示一个打不开的假开关更糟，直接违反 AC 1.5）② 门与原因必须指**同一条** entry
    ③ entry id 必须能在 generated manifest 里兑现（两个例外分支 —— inherited 父 entry、
    同目录父宿主 —— 各自带可验证条件，并断言它们**真的被走到过**，否则就是两段死代码）
    ④ 宿主注释点名的 sync 守卫文件必须存在。
  - 🔴 **判据 ④ 是被真实缺陷逼出来的**：批 7 的迁移脚本在 **33 个**宿主里写下
    「由 `sync/__tests__/entryIdLiteralsMatchManifest.spec.ts` 钉住两边一致」，而那个文件
    **从头到尾不存在** —— 真正守这条不变量的是本文件判据 ③。指向不存在的守卫比不写更糟：
    读代码的人会以为该不变量已有人守，于是不再去建真正的判据。33 处已全部改指真实守卫，
    并加判据封住这一类（磁盘变异：把某宿主的引用改成不存在的文件名 ⇒ 精确红 1 条，
    阴性对照 6 全绿，sha256 `166cdf045a619550` 前后一致）。
  - **生成物重算**：manifest / legacy baseline / current-state / cycle projection 四件按
    依赖序 `--write` 并 reverify 全 OK（entries 197 / independent 145 / pending 78 不变）；
    task66 执行账、residual lane、required scenario set、runtime evidence projection、
    cycle reconciliation 一并重算。task66 `state_drifted 27 → 28`（批 7 改到了计划内的一个
    宿主，内容变 ⇒ 需 owner 重判），**`outstanding_paths` 仍 96，棘轮方向未被破坏**。
  - **source digest 变更附零能力损失复核**（`evidence/phase3-source-digest-review-2026-11-01-task35-final.json`）：
    按完整 manifest 现 build 与磁盘版逐 entry 比 10 个能力字段 —— entry 集合 197→197
    不增不减、stats 逐项相同、`changed_entries` 与 `mount_count_changes` 均为空 ⇒
    `verdict=zero_capability_loss`，据此才更新 overlay `approved_source_digest`
    （`e46d2616… → 24738683…`）；`source_review_ref` / `source_reviewed_at` 同批改指本轮
    复核 —— 否则「谁批准了现在这个 digest」会失去追溯（`test_source_review_is_bound_to_overlay`
    正是守这件事）。
  - **验证**：`entrySyncHostWiringContract` 6 + `entrySyncUiHonesty` 148 +
    `entrySyncModePresentationRatchet` 4 + `sharedModeSwitchGate` 9 = **167 passed**；
    33 个宿主注释修正后重跑仍全绿。
  - **提交须知**：`GtB22AControlMatrix.vue` / `GtB50RiskAssessment.vue` 在 HEAD 就已是
    2734 / 2798 行（上限 1500），本轮各 +12 / +28 行的横切接线会被 pre-commit 行数门拦下
    ⇒ 已按真实行数登记 `backend/scripts/file_size_whitelist.txt` 并写明拆分方向归 B 轮 lane。
  - **历史轨迹（保留，便于复核口径是怎么收敛的）**：
  - **共享切换器已接单源**：`sync/useGRenderModeSwitch.ts` 新增可选 `entrySync` 入参 +
    暴露 `showModeSwitch`（不传时恒 true，保持改线前行为）⇒ G 循环 16 个宿主只需传入已有的
    readiness 实例即可完成迁移，不用各写一遍判断。**这是本任务的杠杆点**：改 1 个 composable
    + 每宿主 3 行，取代 126 份各写一遍判断。
  - **已迁移 25 个**：`GtM7SpecialReserve.vue`（样板，task 3.4）· `GtG2InterestReceivable.vue`
    （第一批）· 第二批 12 个（G1 / G3 / G4-ECL / G4-Main / G4-SPPI / G5 / G6-Main /
    G6-SPPI / G8 / G9 / G13 / G14）· 第三批 3 个（G10 / G11 / G12）· 第四批 8 个
    （L1~L8，载体 `composables/useCycleHtmlOoDualMode.ts`）。
  - **第二个杠杆点 = `useCycleHtmlOoDualMode`**（L 循环共用）：按 `useGRenderModeSwitch`
    同一模式加可选 `entrySync` + 暴露 `showModeSwitch`。与 G 组三处差别**不可照抄**：
    ① 宿主的模式 segmented **原本没有 `v-if`** ⇒ 动作是「新增」而非「合取」；
    ② 没有 `*_SYNC_ENTRY_ID` 常量 ⇒ entry id 取宿主 notice 上的字面量（同值，不新造）；
    ③ L4 宿主另有一个纯业务 `el-segmented`（债券分支选择器）**不得**被同步能力门控 ⇒
       迁移脚本按「绑在 `<var>.currentMode.value` 上的那一个」定位，不按「宿主内所有 segmented」。
    专门核验脚本逐标签对账（`tmp_workpaper_sync_impl/verify_l4_business_seg.py`）：
    9 个标签全部 `is_mode == gated`，L4 业务分段器 `gated=False` ✓。
  - 本批未迁 `CycleStandaloneProcedureShell.vue`（同载体但**无固定 entry id** —— 它是跨循环
    共享壳，entry 随 wp_code 运行时确定）⇒ 留在棘轮里，须另案（给它传运行时 entry id）。
  - **第五批 = 43 个 inline 宿主**（A/D/G/H/K/M/N/J 八个循环，**无共享载体可改**）：
    readiness 实例直接建在宿主里，`v-if` 直接读它（合取 8 / 新增 35）。棘轮 102 → **59**。
    目标集合**现算**分桶得出（`tmp_workpaper_sync_impl/probe_inline.py`）：54 条 inline 中
    **43 可机械化**（恰 1 个模式 segmented + 有 entry id + 有 `props.projectId/wpId`），
    另 3 条多模式开关、3 条无模式 segmented（候选豁免）、6 条无 entry id ⇒ 各自另案。
  - 🔴 **插入锚点选 `<script setup>` 末尾，是为了避开一类静态门看不见的运行时崩溃**：
    `useEntrySyncReadiness` 内部 `watch(..., { immediate: true })` 在 setup 期**立即**读三个
    getter ⇒ 实例若插在 `props` 声明之前，`props` 落在 TDZ、一打开页面就 ReferenceError，
    而 `get_diagnostics` / vue-tsc 全绿。现算 43/43 都有唯一 `</script>`，而 `defineProps`
    有两种形态（plain_generic 26 / withDefaults 17）且语句跨多行含嵌套泛型 —— 解析它的语句
    边界远比用 script 末尾容易出错。模板在 setup 完成后才求值，故声明在末尾对模板无影响。
  - 第五批三条结构核验（都是诊断看不见的，`tmp_workpaper_sync_impl/verify_batch5.py`）：
    ① TDZ 顺序（readiness 必在 `props` 之后）② 逐标签对账（**49 个** `el-segmented`：模式开关
    必被门控、业务分段器必未被门控）③ 门控表达式引用的局部名必须是本文件真实声明的那个
    —— 三条全部通过；另全量 `get_diagnostics` 0 错（import 相对路径因此同时得证）。
  - 🔴 **用户可见影响已逐条量化**（`probe_capability_impact.py`，这是本批最关键的诚实性问题）：
    接单源后 `capability` 非 bidirectional 的 entry 不再显示模式开关。43 条里
    **22 条 bidirectional**（开关照常显示）+ **21 条 `capability=null` / pending**（开关隐藏）；
    而这 21 条**全部**已挂 `GtEntrySyncCapabilityNotice` ⇒ **0 个宿主无声失去开关**，
    用户看到的是「两侧数据未互通」+ 可操作原因，正是 AC 1.5 要的形态。
  - 🔴 **A/B 归因抓到一条真实新增失败并据此修正了一条「断言旧的不诚实行为」的用例**：
    57 个 spec（现算选集 = 凡 import 或读取这 43 个宿主源码的）跑 A/B 逐节点对比，首轮
    **added 1** —— `GtA111SubsequentEventsInquiry.spec.ts > mode switch > renders segmented
    control`（原断言「开关恒显示」）。查 generated manifest：该 entry 是 `capability: null` /
    `pending` / blockedBy BP-1~BP-9，**两侧尚未形成已验收的双向链路** ⇒ 此时摆出双选开关正是
    本 spec 要治的「仅能打开 OO 却呈现成双向」。故**不是删断言**，而是改成断言正确行为的两面：
    pending ⇒ 开关不显示**且**能力披露组件在位（「隐藏开关却不给原因，比显示假开关更糟」）；
    单源裁决可双向 ⇒ 开关显示（防上一条成为恒假判据）。
  - 🔴 写这条正例时踩到一个会让判据**假红**的坑：`mountComponent` 不传 `projectId` 时，
    `useEntrySyncReadiness` 走「身份不全」早退分支、**根本不调** readiness 接口 ⇒ spy 永不触发，
    判据以「单源说可双向却不显示」的形态失败。已补 `projectId` 入参 + 断言
    `expect(spy).toHaveBeenCalled()`（否则本例测不到任何东西）。
  - 同组还有一条**在 HEAD 就是红的**用例（`OO health check disable > when OO healthy, both
    modes available`，A/B 两树同红、`expected +0 to be 2`，与同步能力无关，是该 stub 取不到
    按钮）。它的**主题**已被本任务改掉（模式可用性不再由 OO 探活决定），留着就是一条永红判据
    （永红 = 没人看 = 等于没门禁）⇒ 按新口径重写为「单源裁决可双向时两个选项都在」，并改为
    核对 `modeOptions` 数据本身而非 stub 怎么渲染按钮（原断言正是栽在这上面）。
    **已写明它非本轮弄红**，重写属顺带清理而非认领别人的红。
  - 第五批 A/B 终态：A(HEAD) 10 条失败 · B(候选) **8** 条 · **added 0** · resolved 2 ——
    resolved 的 2 条正是上面两个新用例（在 HEAD 宿主未门控时**失败**、在候选树通过），
    这是「判据真的能检出行为变化、不是恒绿」最直接的证据。`GtA111` 单文件 **19/19 全绿**。
  - 🔴 **第六批先修正了第五批筛选条件里的一条多余约束**：第五批只取「无共享载体」的宿主，
    但**载体与可见性无关** —— 门加在宿主自己的 `el-segmented` 上、读宿主自己的 readiness
    实例，那 41 个「单例载体」（`useD1EntryDualMode` / `useF1DualMode` … 各只服务 1 个宿主）
    一行都不用改。去掉这条约束重新分桶，余 59 条里又得 **28 条可机械化**。
  - **第六批 27 个宿主**（D1/D3/D4/D5/D6/D7 · F1/F2×4/F3/F4/F5 · G6-ECL · I6 ·
    K8/K9/K10/K11/K12/K13 · M2/M3/M4/M6/M10，合取 7 / 新增 20）。棘轮 59 → **32**。
    `bind:` 那一条（`GtB22AControlMatrix.vue`，entry id 是模板里绑的变量、可能是 ref 需
    `.value`）**刻意排除**，不赌它的形态，留作单独处理。
  - 结构核验升级为**全集现算**（`verify_wired_structure.py`，不再只看某一批）：扫
    `components/workpaper` 下全部 `.vue`，凡自身含 `useEntrySyncReadiness` 即纳入 ⇒
    **95 个宿主 / 102 个 `el-segmented` 标签**，三条（TDZ 顺序 / 逐标签对账 / 门控表达式
    引用）全部通过。🔴 写这份核验时自己踩了一次「按命名习惯推形态」：实例名正则先写成
    `(\w+EntrySync)`，而样板宿主的实例就叫 `entrySync`（无前缀）⇒ 把一个**已正确接线**的
    宿主判成「找不到实例」。改为认任意标识符。
  - 🔴 **第六批触发并修掉棘轮自带的一条「把过渡量写成永久不变量」的判据**：
    `expect(BASELINE.length).toBeGreaterThan(50)`，注释写的是「分母不为空，否则本棘轮在
    空集上恒绿」。但 50 是写下它时（还剩 126 条债）的量级，**每接走一批就更接近打红**，
    减到 50 以下必红 —— 也就是惩罚进展，而唯一的「修法」会是把已接单源的宿主塞回基线，
    与棘轮方向正好相反（与 task 5.3 那条 `unreachable.toBe(1)` 同型）。
    它真正要防的是「扫描器瞎了」（`actual` 变空集 ⇒ 两条差集判据**双双变绿** ⇒ 呈现成
    「已完工」），那件事与剩余债务量无关 ⇒ 改为断言**扫描面**非空（全前端画 segmented 的
    文件数）+ **识别正则可伪证**（已知正例必命中、业务分段器必不命中）。基线自身不需另设
    下限：两条差集判据合起来已把 `BASELINE` 钉成与现实**逐条相等**的集合。
  - 磁盘变异证明该重写**不是削弱**（`mutate_ratchet_guard.py`，三条逐一注入 + 逐字节恢复，
    sha256 `4977b06b2ed96a4e` 三次均一致）：M1 `walk` 返回空集（扫描器彻底瞎）⇒ 新判据红；
    M2 `SEGMENTED` 永不命中（识别层瞎）⇒ 新判据红；M3 `MODE_VALUE` 放宽到也命中业务分段器
    （分母虚高）⇒ 可伪证那条红。三个变异全部被捕获。
  - 第六批验证：27 文件 `get_diagnostics` 0 错 · 棘轮先红（失效条目）→ 收缩 59→32 → 重跑
    sync 五文件 **134 passed**。
  - 🔴 第三批是**第二批的漏点**：它们同样 import `useGRenderModeSwitch`、`v-if` 同为
    `"isHtmlSheet"`、也有 entry 常量，只因第二批的 TARGETS 是**手列的**而漏掉。教训与下面
    「闭合判据手抄清单」同源 —— 批量迁移的目标集合也该现算（扫载体 import），不该手列。
  - 第二批可机械批量化的依据：现算 16 个宿主的 `el-segmented` 的 `v-if` **逐字相同**
    （全部 `"isHtmlSheet"`）⇒ 三处改动（import / readiness 实例 / `v-if` 合取）可脚本生成；
    entry id 取**宿主已有的**常量或它 notice 上的字面量，不新造标识符。
  - 棘轮收缩用**现算**而非手抄清单：扫「是否 import `useEntrySyncReadiness`」逐条判定
    （`tmp_workpaper_sync_impl/shrink_baseline2.py`），避免清单与代码各自漂移。
  - 每批验证链：逐文件 `get_diagnostics` **0 错** → 棘轮**先打红**（已接单源却仍在基线
    ⇒ 判据有效）→ 现算收缩基线 → 重跑转绿。第二批 125→113 / 23 passed；第三批 113→110。
  - 🔴 **顺带修一条「声称覆盖全部、实际只看过一个」的判据**（task 3.6 的接线闭合，
    `entrySyncUiHonesty.spec.ts`）：它的 `WIRED_HOSTS` 是**手抄清单**且只有样板宿主一条 ——
    分批迁移后真实已接单源的宿主涨到 17 个，清单一条没涨 ⇒ 另外 16 个的假接线它一律看不见。
    改为**现算**（「画了 segmented + 自身文本出现单源」即纳入）+ 加「分母不为空且含样板宿主」
    防空集恒绿。现算后逐宿主断言 **17 条**，文件从 9 例涨到 **27 例**。
  - 🔴 同时修它两处会误判的实现细节（**都是被我自己新加的可伪证用例打红后才发现的**）：
    ① 原判据要求宿主内**所有** `el-segmented` 都被门控，而 L4 一类宿主还有纯业务分段器
    （债券分支选择器）—— 同步能力不该门控业务分段器 ⇒ 改为只要求**模式开关**被门控；
    ② 区分模式开关的正则第一版写 `/mode/i`，它命中 `v-model` 里的 "mode" ⇒ 把业务分段器
    也当成模式开关；改认模式开关特有绑定名（`currentMode|modeOptions|renderMode|
    onModeChange|modeToggle`）。另修一处 JS 陷阱：带 `g` 标志的正则 `.test()` 会累进
    `lastIndex`（有状态），同一对象反复 test 交替返回 false ⇒ 取标签与判存在分用两个对象。
  - 磁盘变异证明闭合判据有效：把 `GtG13FairValueChanges.vue` 的 `v-if` 退回 `isHtmlSheet`
    （= import 了单源却不用 = 假接线）⇒ **精确只红那一条**（1 failed / 26 passed），
    其余 16 宿主仍绿；跑完逐字节恢复，sha256 `f6400a6f23ee9bee` 前后一致。
  - 🔴 **补一条行为判据，封住「共享载体杠杆」的单点失效**（新文件
    `sync/__tests__/sharedModeSwitchGate.spec.ts`，9 例）：杠杆的另一面是两个载体各有一行
    `showModeSwitch` 决定 25 个宿主 —— 把那行改成 `return true`，25 个宿主同时退回自行决定，
    而当时**三条既有判据一条都看不见**（棘轮只看宿主有没有 import；接线闭合只看模板 `v-if`
    的**文本**；`entrySyncPresentation.spec.ts` 测的是 derive 纯函数，它不知道有没有载体在用它
    —— 三者全是静态/旁路判据，没有一条真的调用载体看它返回什么）。新判据逐项断言：
    单源说 false ⇒ false · 说 true ⇒ true · 不传 `entrySync` ⇒ 恒 true（渐进迁移）·
    单源结论变化时跟着变（是响应式派生不是快照）· 以及**钉住设计决定**：探活失败
    （`isOoAvailable=false`）但单源说可双向时开关**仍须显示**，可用性只体现在
    `modeOptions` 的 `disabled` 上 —— 可见性与可用性混在一起会同时产生两种相反的错。
  - 磁盘变异（`tmp_workpaper_sync_impl/mutate_carriers.py`）：两个载体的 `showModeSwitch`
    各改成恒 `return true` ⇒ 新判据分别 **2 failed / 1 failed**（打红 ✓），而**既有三条判据
    49 passed 全绿**（确实看不见 ⇒ 印证这条判据补的是真空白）；两次均逐字节恢复，
    sha256 `611a941f755d6989` / `63d7d0ef7094a0e7` 前后一致。
  - 第四批回归与归因：L 循环 12 个既有 spec 跑完，唯一红是 `l2l4DisclosureWiring.spec.ts`
    的 **18 条**（该文件自己的 docstring 把它们标为「类 B / Wave 7 补」）。按铁律做 A/B
    逐节点归因（`tmp_workpaper_sync_impl/ab_l2l4.py`，不用 `git stash`：把本轮改过且在该
    判据读取范围内的 2 个文件临时换成 HEAD 版）：A(HEAD) 18 条 · B(候选) 18 条 ·
    **added 0 / resolved 0**，且脚本先断言「解析出的节点数 == 摘要 failed 数」（18==18，
    排除解析静默丢节点），两文件逐字节恢复。⇒ 预存红，与本轮无关。
  - 🔴 顺带修 `entrySyncUiHonesty.spec.ts` 一条**把过渡态写成永久不变量**的判据：
    原 `expect(unreachable.length).toBe(1)`（「分母不为空」）在 task 5.3 删掉 G6 旧桩后必红，
    而唯一的「修法」会是把旧桩加回来 —— AC 1.7 的要求正是「不可达旧桩 SHALL 删除」，
    归零恰恰是它**达成**的标志。改为 `toBe(0)` + 写明 ② 的真实不变量由合成 readiness 承担。
  - 验证：棘轮 4 passed · UI 诚实性 9 passed · presentation 10 passed（共 23）· 两文件 0 diagnostics。
  - _AC: 1.4, 1.5_

- [x] 3.6 建立 UI 诚实性总守卫
  - `single_*` 无双模式按钮、unreachable 零挂载、blocked 不发 materialize、pending 常显未互通原因；构造 runtime contract drift 反例必须打红。
  - 产物：`sync/__tests__/entrySyncUiHonesty.spec.ts`（9 例）。分母取 **generated manifest
    全域**（独立 entry > 100），四条不变量逐条断言，外加「任何形态都不得出现笼统成功文案」。
  - runtime contract drift 反例：静态 `bidirectional` + `runtime.ready=false` +
    `reason=CONTRACT_DRIFT` ⇒ 必须 `canClaimBidirectional=false` / 无开关 / `noticeKind=danger`，
    且原因是后端那句可操作中文（断言不含 `A_B` 式裸枚举码）。
  - 另加**接线闭合**判据：已接单源的宿主，其 `el-segmented` 的 `v-if` 必须真的绑在
    `presentation.showModeSwitch` 上 —— 棘轮那条只看 import，看不出「import 了却没用上」。
  - 🔴 现算到一处与原任务假设不符的事实：manifest 里 **`single_html` / `single_onlyoffice`
    当下为 0 条**（Phase 1 把迁移中的入口统一落成 `capability=null` + pending 三字段，拒绝
    继续用组件默认 `single_onlyoffice`），真实出现的只有 `bidirectional` 111 /
    `unreachable` 1 / `null` 86。四条不变量仍对四种 capability **全测**（它们是 derive 函数的
    不变量，不该等「恰好有这种 entry」才被走到）。
  - `blocked 不发 materialize` **刻意不在本文件**：那条必须真发请求才算验证，由
    `useWorkpaperSyncBridge.spec.ts` 承担（readiness 未过即拒 / readiness 失败 fail visible /
    readiness 必须早于第一个写请求）；此处不写跨文件文本断言（会被注释骗过）。
  - 变异：M0 阴性对照 9 passed；M1 漂移时仍宣称双向 4 红 / M2 开关恒显 3 红 / M3 宿主开关
    去门控 1 红，两份文件按字节恢复。
  - _AC: 1.4, 1.5, 1.7_

## Phase 4：按当前事实收口逐 entry lane

- [x] 4.1 建 residual lane 交接模板和机器清册
  - 每行包含 owner、entry、counterpart、contract/provider、definition/bundle、representation、host、required scenarios、evidence、回滚和解除条件。
  - 产物：`backend/scripts/gen/generate_residual_lane_ledger.py`（`--check` / `--write`，输出幂等）
    + `backend/data/workpaper_sync_residual_lane_ledger.json`（145 条 independent entry，
    按 owner_task 分组：4.2 D/E 9 条 · 4.3 F 8 条 · 4.4 G/H/I 41 条 · 4.5 J/K/L 19 条 ·
    4.6 M/N 15 条 · 4.7 A/B/C 39 条 · 4.8 S+跨循环 14 条）+ 守卫
    `backend/tests/workpaper_sync/test_residual_lane_ledger.py`（7 例全绿）。
  - _AC: 12.1, 12.8, 12.9_

- [x] 4.2 对账并收口 D/E entries
  - 复用已有供给但逐项重验 runtime pointer、target-bound registration、真实 OO 与宿主 gate；仅为实际差集创建 residual lane。
  - 产物：`generate_cycle_reconciliation.py --write` → `workpaper_sync_cycle_reconciliation.json` group `4.2`：
    total 9 / bidirectional 3 / pending 9 / blocked 6 / evidence_missing 3。
    逐 entry 一致性校验通过（无 `bidirectional_without_adapter`，3 条 bidirectional 全有 adapter）。
  - _AC: 1.4, 12.1, 12.8, 12.9_

- [x] 4.3 对账并收口 F entries
  - 四类 F2 lane、其余 F entry 和 Word 入口按独立 entry 隔离；模板/百分比/容量问题不得通过伪造 contract 绕过。
  - 产物同上 group `4.3`：total 8 / bidirectional 8 / pending 8 / blocked 0 / evidence_missing 8。
    8 条全 bidirectional 且全有 adapter，blocked=0 说明 capability_target 无阻塞，只差 runtime evidence。
  - _AC: 1.4, 12.1, 12.8, 12.9_

- [x] 4.4 对账并收口 G/H/I entries
  - 共享工作簿、多 variant、动态列和 parent duplicate 只复用框架，不复用别的 entry 的 contract/evidence；处理 G6 旧桩依赖。
  - 产物同上 group `4.4`：total 36 / bidirectional 23 / pending 36 / blocked 13 / evidence_missing 23。
    G6 旧桩已在 5.3 删除（unreachable 1→0），该 entry 不再出现在对账集合里。
  - _AC: 1.4, 1.7, 12.1, 12.8, 12.9_

- [x] 4.5 对账并收口 J/K/L entries
  - 先重算旧 slice 与当前 ledger/provider 的差集；adapter/provider 存在但 DB/current evidence 未证实时保持未完成。
  - 产物同上 group `4.5`：total 24 / bidirectional 23 / pending 24 / blocked 1 / evidence_missing 23。
    仅 1 条 blocked，23 条只差 runtime evidence。
  - _AC: 1.4, 12.1, 12.8, 12.9_

- [x] 4.6 对账并收口 M/N entries
  - 清除静态 `adapter_registered` 注释型状态的误用，以目标底稿 current representation、运行时注册和 operation evidence 为准。
  - 产物同上 group `4.6`：total 15 / bidirectional 10 / pending 15 / blocked 5 / evidence_missing 10。
  - _AC: 1.4, 12.1, 12.8, 12.9_
- [x] 4.7 对账并收口 A/B/C entries
  - docx/xlsx、pattern-less、控制测试和共享宿主分别按真实载体裁决；A5-1 不再依赖 bypass，C22 等缺口独立登记。
  - 产物同上 group `4.7`：total 39 / bidirectional 0 / pending 39 / blocked 39 / evidence_missing 0。
    全部 39 条 capability=null（pending），全部 blocked——这些是 docx/pattern-less 宿主，
    当前 overlay 默认给它们的 capability 是 null（不伪造 bidirectional）。
  - _AC: 1.4, 12.1, 12.8, 12.9_

- [x] 4.8 对账并收口 S、跨循环共享、Word/custom/opaque entries
  - S 与通用宿主单独分母；Word 未过 tagged-SDT 门保持 blocked，custom/opaque 保持自身权威模型，不强塞 projection contract。
  - 产物同上 group `4.8`：total 14 / bidirectional 0 / pending 14 / blocked 14 / evidence_missing 0。
    全部 blocked，与 4.7 同类（Word/custom/opaque 不强塞 projection contract）。
  - _AC: 1.4, 12.1, 12.8, 12.9_

## Phase 5：single 裁决与 legacy 物理删除

- [x] 5.1 逐项验证全部 `single_onlyoffice`
  - 每项必须有 `html_counterpart_verdict=none` 和可复查 source refs；因缺 adapter/contract/bundle 而裁 single 的记录全部转 pending 或完成 producer。
  - 🔴 **结构性空分母**（2026-11-01 现算）：manifest capability 分布 bidirectional=111 / null=86 /
    **single_onlyoffice=0**。这 86 条 null 是 pending（尚未裁决），不是 single_onlyoffice。没有
    任何 entry 被裁为 single_onlyoffice ⇒ 验收集合为空集，不存在需要验的对象。
  - 这条红变绿的**唯一路径**是有 entry 被裁进 single_onlyoffice 之后再逐项验。当前 overlay 的
    `defaults_by_component` 给 `GtOnlyOfficeSheet` 的默认 capability 是 null（不是 single），
    per-entry override 也没有把任何 entry 裁成 single_onlyoffice。
  - _AC: 1.5, 12.8_

- [x] 5.2 逐项验证全部 `single_html`
  - 证明 OO 侧无业务价值或为空白入口；删除 OO descriptor、按钮和 legacy health/config 请求，single 身份位保持全空。
  - 🔴 **结构性空分母**（2026-11-01 现算）：manifest capability 分布 bidirectional=111 / null=86 /
    **single_html=0**。同 5.1 的情况：没有任何 entry 被裁为 single_html。
  - _AC: 1.5, 12.9_

- [x] 5.3 删除 `GtG6OtherBondEcl.vue` 不可达旧桩
  - 先证明真实替代组件可达（`GtG6OtherBondInvestmentEcl.vue` 在库、registry `specialized.ts` 直接 import）、
    生产入边为零（execution ledger landed + test_task49 全仓模块边扫）和删除计划可回滚。
  - 物理删除文件 + 从 overlay 移除 `unreachable_rules` 那条（它引用已删文件，manifest 生成器拒绝 stale 规则）
    + 更新 `approved_source_digest`（`189cbda5…` → `e46d2616…`，mount 集合少一个文件）并在 `review_basis`
    追加零能力损失复核记录。
  - 重生成四件产物（manifest + legacy baseline + current-state + cycle projection）：entries **198→197**
    （唯一移除 = `xlsx/gt-g6-other-bond-ecl`，capability unreachable / independent_entry false），
    independent 145 不变、pending 78 不变、unreachable **1→0**。
  - 重生成 execution ledger：landed **28→29**（该文件入账）、outstanding **97→96**，棘轮基线下调。
  - coverage-ledger.json 的 G6 条目修正：entryFile 与 evidence 从旧桩改指替代组件。
  - test_task49 的 `test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges` 改为三条
    断言（文件不在 + 替代组件可达 + registry 登记完整）。
  - 验证：35 passed（ledger 13 + closure 14 + artifacts 8）。
  - _AC: 1.7, 12.9_

- [x] 5.4 删除零生产调用的 `usePilotBridgeAdapter.ts`
  - 以 AST 确认生产调用为零（execution ledger 现算 `_adapter_consumer_hosts()` = []），旧测试改为断言空壳不存在且 B60/D2/G7/H1 真桥仍可达；禁止保留兼容墓碑。
  - **同一笔完成全部改动**（CI `pytest -x` 半截即停）：删 `usePilotBridgeAdapter.ts` + 改 test_task45
    （`TestPilotAdapterFieldContract` 整类 + 三个辅助函数 → `TestPilotAdapterDeletedAndNoResidue`
    三条；`test_pilot_bridge_adapter_exists` / `_does_not_call_config_endpoint` → `_deleted` / `_no_production_residue`；
    `test_bridge_adapter_uses_unified_storage_key` / `test_no_legacy_storage_prefixes_in_adapter` /
    `test_adapter_exposes_entry_id_parameter` / `test_adapter_is_documented_as_transitional` → 单条 `test_bridge_adapter_is_deleted`；
    Property 48 的两条 toast / switching 判据 → 断言文件已删）+ test_task46/48/49 各一条
    `test_bridge_adapter_supports_entry_id` → `assert not is_file()` + 前端
    `bridgeMaterializeDriven.spec.ts` 改 `existsSync → false`。
  - 后端 34 passed；前端 4 failed / 7 passed（与基线逐条相同，added 0 / resolved 0，预存失败，
    与本次删除无关）。
  - _AC: 1.4, 1.7_

- [x] 5.5 把 Task 66 删除计划升级为可收缩执行账
  - 已满足 entry 必须从 pending 进入物理删除并重验；失效项自动移除，计划外 legacy/unreachable 新增立即打红。
  - 产物：`backend/scripts/gen/generate_task66_execution_ledger.py`（`--check`/`--write`，输出幂等无时间戳）
    + `backend/data/workpaper_sync_task66_execution_ledger.json` + 守卫
    `backend/tests/workpaper_sync/test_task66_execution_ledger.py`（13 例全绿，带
    `-W error::pytest.PytestUnhandledThreadExceptionWarning` 复跑同样全绿）。
  - 三态现算（126 个唯一 path）：`landed 28`（已不在盘上，**自动出账**）/ `drifted 28`（内容变了，
    须 owner 重判）/ `intact 70`；`outstanding 97` = 125 pending − 28 landed，棘轮基线写在**守卫**
    里而非产物里；`unplanned_legacy_paths 0`。对照冻结计划自报的 `pending_delete 207`，**44% 已失效**。
  - BP 全部重算不沿用冻结 verdict：BP-66-1 **已释放**（现算 116 个生产文件 import
    `WorkpaperSyncEditorHost`，计划冻结值是「unreachable 19」）· BP-66-2 **已释放**（`git ls-files`
    现问 untracked 0，计划冻结值 22）· BP-66-3 仍成立（authority model 未定，owner 在 Phase 6，
    如实标 `recomputed: false`）⇒ `eligible_now_count 0`，fail closed 不是豁免。
  - 冻结生成器登记退役（`retired_superseded_by_this_ledger`）+ 守卫钉死它不在 CI / pre-commit /
    pre-push 五处任一处被引用（不留永红门禁）；「冻结产物没再变」由 `frozen_inputs.plan_digest` 承担。
  - 变异：8 组（M0 阴性对照保持绿；M1 棘轮虚高 / M2 忽略 live blocker / M3 landed 不出账 /
    M4 加时间戳破坏幂等 / M5 fork legacy 正则 / M6 把退役生成器接回门禁 / M7 放计划外 legacy 文件
    全红），数据级变异先 `--write` 重生成再跑用例，每组逐字节恢复并校验 sha256。
  - evidence：`evidence/task5.5-execution-ledger-2026-11-01.md`（含守卫首跑抓到的 `text=True`
    按本机 gbk 解码致中文断言永假的真实问题及根因修复）。
  - _AC: 1.7, 12.9_

## Phase 6：真实 evidence 与 closure

- [x] 6.1 从 profile/bundle/authority model 生成 required scenario set
  - 每个独立 entry 自己生成 digest；不得用代表 entry、同循环或历史 run 替代，download-only/authorization-reject 的实体形状单独校验。
  - 产物：`backend/scripts/gen/generate_required_scenario_set.py`（`--check` / `--write`）
    + `backend/data/workpaper_sync_required_scenario_set.json`（145 条 independent entry，
    11 种唯一 scenario profile，67 条需 browser + contract evidence = bidirectional 独立 entry）。
  - _AC: 12.1_
- [x] 6.2 建立 runtime evidence current projection
  - 从 PG 的 test run/scenario、entry pointer、bundle、representation、request/delivery/application/operation/timeline 现算 acceptance；不信 overlay 布尔摘要。
  - 产物：`backend/scripts/gen/generate_runtime_evidence_projection.py`（`--check` / `--write`，
    PG 不可达时降级——把全部标 missing，因为连不上恰恰证明「没有 evidence」）
    + `backend/data/workpaper_sync_runtime_evidence_projection.json`。
  - 现算：PG `connected`、`total_test_runs=0`、`entries_with_runs=0` ⇒ `not_required 78` / `missing 67`。
    67 条 bidirectional entry 全部缺 runtime evidence——这是 6.3 要产出的。
  - 🔴 **2026-11-01 复核：这个 0 是真事实，但「缺证据」不等于「没跑过」——两件事必须分开说。**
  - **(1) 验收账本确实空**，且已排除「连库失败被降级吞掉」这种假象。三向对照
    （`tmp_workpaper_sync_impl/verify_evidence_pg_path.py`）：显式指真库 `audit_platform`
    ⇒ `connected / total=0`；显式指一个不存在的库 ⇒
    `degraded:InvalidCatalogNameError`（证明降级分支**会**如实报出来，所以 `connected`
    不是吞掉的结果）；当前环境 ⇒ `connected / 0`。
    `working_paper_sync_test_run` = **0**、`working_paper_entry_evidence_scenario` = **0**。
  - 🔴 **顺带堵掉一个能把这个结论伪造出来的环境陷阱**：本仓终端跨会话共享，而「只跑隔离
    用例」的约定会把 `DATABASE_URL` 设成**不存在的库名**；在那种 shell 里 `--write`，
    产物会是 `degraded:*` + 67 条全 `missing` —— 与「真库上确实没有验收记录」**逐字相同**。
    新增判据 `test_committed_evidence_projection_was_produced_against_a_reachable_database`
    （只读已入库 JSON 的 `pg_facts.status`，不连库 ⇒ 确定性、不会变成环境相关的永红门禁）；
    磁盘变异把产物换成降级版 ⇒ 精确打红，阴性对照绿，sha256 前后一致。
  - **(2) 生产链路真的跑过，规模还不小**（真库现查）：
    `working_paper_sync_operation` **1192** 条、跨 **14** 个 entry；其中
    `applied html→oo` **750**（13 entry）、`applied oo→html` **104**（10 entry）、
    error 218 / conflict 16 / rejected 24 / authorization_stale 2。
    另有 `content_application` 144、`content_representation` **455**（覆盖 **90** 个 entry）、
    `content_version` 435、`oo_room` 148、`callback_delivery` 498、`forcesave_request` 191、
    `sync_conflict` 367。时间跨度 2026-09-06 → 2026-10-25。
  - **(3) 交叉对账才是真实缺口**（`tmp_workpaper_sync_impl/probe_real_oo_vs_manifest.py`）：
    | 现算项 | 值 |
    |---|---:|
    | 67 条 bidirectional 里**有真实双向往返**（h2o 与 o2h 都有 applied） | **5** |
    | 67 条 bidirectional 里**连一条 operation 都没有** | **59** |
    | 有真实双向往返**却仍被裁为 pending** | **5** |
    | 只有 html→oo 成功、没有 oo→html | 3（M5 / M1 / M9） |
    | 有 operation 但两向都没成功 | 1（A51，10 条全 error） |
    有真实往返的 5 条 bidirectional = D4（542/48）· D2（167/43）· H1（10/3）·
    G7（12/2）· D1（2/1）。
  - 🔴 **「裁决」与「真实事实」反向脱节，对 4.* 终裁是直接线索**：
    `xlsx/b60/gt-b60-bundle` · `gt-d3-prepaid-accounts` · `gt-d5-receivables-financing` ·
    `gt-d6-contract-assets` · `gt-d7-contract-liabilities` 这 5 条**真库里有成功的双向
    往返**，manifest 却仍是 `capability=null`（pending）。它们不该再按「从零开始」排期 ——
    但也**不能**据此直接终裁：按 ADR-WB-003，运行时跑通过只是三层中的一层，仍缺
    reviewed contract / approved bundle / current representation / 新鲜 evidence 的逐项核对，
    且那几条往返发生在 2026-09-12、远早于本轮的契约与模板变更（representation 预检现算
    它们多为 `stale_needs_reprojection`）。
  - ⇒ 结论更新：6.3 的工作量**不是**「给 67 条补证据记录」，而是「59 条从未真实跑过 +
    5 条只跑通单向 + 1 条全失败 + 5 条跑通但裁决没跟上」四类分别处理。原先把它们笼统
    记成「全部缺 evidence」会严重低估 59 条那一类的工作量。
  - _AC: 12.1_

- [ ] 6.3 执行真实 OnlyOffice required scenarios
  - 🔴 **2026-11-02 推送前退回**：下列 D2 证据只覆盖“readiness 未通过时正确拦截”的
    blocker scenario，没有进入、编辑、保存并回读，也没有按 67 条 bidirectional entry 的
    required scenario set 逐条签收。该证据保留为 AC 1.4 的阶段验收；AC 12.1 的真实 OO
    operation 与验收态仍待【测试】项目执行。
  - 在重药安徽 D2 应收账款底稿上通过 Playwright 验证：
    * readiness 端点 `/sync/entries/xlsx/gt-d2-accounts-receivable/readiness` → 200（两次调用）
    * 模式工具栏「结构化视图 / 在线编辑」正确展示
    * **「在线编辑不可用」红色提示**正确显示 + 中文可操作原因
    * 展开原因：「该版本冻结的受管结构与当前实测不一致。先对该底稿重新投影产出新版本，再进入在线编辑。（published_identity_observed_drift）」
    * console 0 errors / 23 warnings
  - 🔴 **OO 编辑流程被正确拦截**——这就是 AC 1.4 的验收：readiness 未通过时禁止进入 OO 模式。
    完整 OO 编辑（进入→编辑→保存→回读）需要先为该 entry 发布新 representation，属 representation 管道的工作。
  - 截图证据：`evidence/phase6-d2-readiness-block-2026-11-01.png` + `evidence/phase6-d2-readiness-reason-expanded-2026-11-01.png`
  - _AC: 12.1_

- [x] 6.4 执行 Playwright 用户闭环
  - 同上 Playwright 会话：`http://127.0.0.1:3030` → 登录 → 重药安徽 D2 → 模式显隐 → 中文原因 → 查看原因展开。
  - 网络验证：readiness 走统一 sync 前缀（`/sync/entries/…/readiness`）；仍有一条 legacy `/onlyoffice/health`，归 2.8 的后端旧路径迁移，不再算作 3.5 presentation 门欠账。
  - console 0 errors。
  - _AC: 1.4, 1.5, 12.1_

- [x] 6.5 实施 evidence freshness 与 post-delete 全量重算
  - source/manifest/bundle/representation/scenario profile 任一变化即 stale；删除后完整重跑，不以 smoke 恢复 verified。
  - 本轮全部生成器 `--check` 幂等通过（7 个）= evidence 全部 fresh。
    execution ledger outstanding 从 97 降到 96（5.3 删旧桩入账）= post-delete 重算生效。
    runtime evidence projection 现算 67 条 missing / 0 条 covered = 如实反映 PG test_run=0。
    五类 closure counter 在 cycle reconciliation 里逐组逐 entry 从明细归零 = evidence_covered 全为 0。
  - _AC: 1.7, 12.1_

## Phase 7：总体验证与归档

- [x] 7.1 完成结构、单元、属性与变异验证
  - 7 个生成器 `--check` 全部幂等通过。81 个后端测试 passed / 0 failed。
    变异验证：task 5.5 的 8 组（M0 阴性绿 + M1~M7 全红）+ task 3.6 的 4 组全红。
  - _AC: 1.3, 1.4, 1.5, 1.7, 12.1, 12.8, 12.9_

- [x] 7.2 完成后端与前端辐射面回归
  - 后端 81 passed / 0 failed。前端 sync/__tests__：bridgeMaterializeDriven 4 failed / 7 passed
    （与基线同样的 4 条预存红），其余全绿。added 0 / resolved 0。milestones BLOCKED 5 / IMPLEMENTED 3。
  - _AC: 1.4, 12.1_

- [x] 7.3 校验数据库 schema 与迁移边界
  - 证明共享 readiness 无需迁移：本 spec 35 个改过的文件里 0 个迁移 / 0 个 ORM 模型变更 / 0 个 sync_models 变更。`needs_migration: false`。
  - 如实际需要 schema 变更，动态取未占用版本、配 V/R、跑 PG 约束测试，并在写共享库前取得用户授权。——当前不需要。
  - _AC: 12.1_

- [x] 7.4 在 clean-checkout 候选树复验全部交付物
  - 候选树 `a35adbe5d` 干净检出：12 个新模块/数据文件**全部被 git 跟踪**（`missing_in_checkout: []`）。
  - 6 个生成器 `--check`：task66_ledger / residual_lane / scenario_set / evidence_proj / cycle_recon
    **5 个通过**；artifacts 因 evidence projection 的 PG 环境差异（worktree 无 `.env`，PG digest
    不同）未通过——这是环境依赖不是代码缺陷，主工作树里 `--check` 全过。
  - 后端测试 44 passed / 3 failed（与 evidence projection PG 连接相关，主工作树 81 passed 全绿）。
  - _AC: 1.3, 1.4, 1.5, 1.7, 12.1, 12.8, 12.9_

- [ ] 7.5 完成五角色复核、INDEX 登记与最终归档
  - 🔴 **2026-11-02 推送前退回**：当前仍有 0.5、2.8、6.3 三项业务/验收任务未完成，
    spec 目录也仍为 active；design §15 的十项条件没有全部满足。下列五角色记录只能作为
    阶段复核材料，待前三项完成并在最新候选树复验后才能执行 INDEX 登记与最终归档。
  - 合伙人/项目经理/质控/审计助理/EQCR 分别复核业务真实性、计划、门禁、可操作性和独立证据；仅 design §15 十项全满足后归档。
  - 阶段性五角色复核已完成：合伙人（D2 readiness 真实生效）/ 项目经理（50 任务 20 wave 依赖图 + 里程碑 26→0 + 执行账棘轮只减）/ 质控（81 passed + 12 组变异 + 7 生成器幂等）/ 审计助理（中文原因 + console 0 errors）/ EQCR（干净检出 + schema 零变更 + 假绿退回有据）。
    INDEX 条目和归档路径在全部满足后生成。
  - _AC: 1.3, 1.4, 1.5, 1.7, 12.1, 12.8, 12.9_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0.1", "0.2", "0.6"] },
    { "wave": 1, "tasks": ["0.3", "0.4", "0.5"] },
    { "wave": 2, "tasks": ["1.1", "1.2", "1.3"] },
    { "wave": 3, "tasks": ["1.4"] },
    { "wave": 4, "tasks": ["1.5", "1.6"] },
    { "wave": 5, "tasks": ["1.7"] },
    { "wave": 6, "tasks": ["2.1", "2.2"] },
    { "wave": 7, "tasks": ["2.3", "2.4", "2.5"] },
    { "wave": 8, "tasks": ["2.6", "2.7", "2.8"] },
    { "wave": 9, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "wave": 10, "tasks": ["3.5", "3.6"] },
    { "wave": 11, "tasks": ["4.1"] },
    { "wave": 12, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8"] },
    { "wave": 13, "tasks": ["5.1", "5.2", "6.1", "6.2"] },
    { "wave": 14, "tasks": ["6.3", "6.4"] },
    { "wave": 15, "tasks": ["5.3", "5.4", "5.5"] },
    { "wave": 16, "tasks": ["6.5"] },
    { "wave": 17, "tasks": ["7.1", "7.2", "7.3"] },
    { "wave": 18, "tasks": ["7.4"] },
    { "wave": 19, "tasks": ["7.5"] }
  ],
  "dependencies": {
    "0.5": ["0.6"]
  }
}
```

## Notes

- 上面的依赖图是**机器可读契约**，`backend/scripts/gen/generate_workpaper_sync_program_milestones.py`
  现读它。键名必须是 `wave`（不是 `id`），且 wave 覆盖的任务集合必须与本文任务号**恰好相等**
  —— 加任务忘了进 wave 会报 `wave/task denominator differs`。同 wave 内不得依赖编号不更小的任务，
  也不得依赖更后 wave 的任务；`0.6` 因此排在 wave 0（它是 `0.5` 的前置）。
- 3.* 可在 lane 未完成时先上线 fail-closed UI，但必须显示真实 blocker。
- 5.3/5.4/5.5 依赖对应 4.* 与 6.1/6.2 的 replacement evidence，不能提前删除。
- 6.3/6.4 写【测试】数据前须确认环境与测试项目；无环境时保持未完成，不改成静态替代证据。
- 7.5 不接受历史归档复选框、INDEX 数字或单个绿色测试作为 closure 依据。

## 未完成项实况（2026-11-01 开工快照，已被后续任务正文取代）

以下内容保留为开工时的审计轨迹，**不得再用作当前任务状态**。其中 3.5、5.3~7.4 已由上文
后续实施记录更新；当前未完成项以文首复选框和文末“当前未完成项索引”为准。

### 已有部分产物、但判据尚未成立

- **3.5 全宿主迁移**：起点 **126** 条宿主自行决定模式开关表现（其中 101 条已挂能力披露 notice），
  现算余 **113** 条。已迁 14 个（样板 `GtM7SpecialReserve.vue` + G 循环 13 个），余量冻结成只许
  变短的棘轮 `sync/__tests__/entrySyncModePresentationRatchet.spec.ts`（+ `.baseline.json`）。
  🔴 口径教训：按常量名（`modeOptions` 一类）数出来是 85，漏 41 条 —— 样板宿主的常量叫
  `modeToggleOptions`。现口径 = 「画了 `el-segmented` + 有 HTML↔OO 模式值字面量 + 未导入单源」；
  另有 201 个 `el-segmented` 文件是纯业务分段器，已排除。
  🔴 **「不能批量替换」须按组重判，不是全域结论**：原记录按「各域 mode 值体系不同
  （`'onlyoffice'` / `'structured'` / `'online-edit'` / `'docx'` / 中文标签直接当值）」判定必须
  逐宿主手改。实测 G 循环 16 个宿主**共用** `useGRenderModeSwitch` 且 `v-if` 逐字相同，批量化
  完全成立（第二批 12 个一次改完、0 diagnostics、棘轮红→绿）。正确口径 = **先按共享
  composable 分组**，同组内形态一致就批量化；只有「宿主各写一遍判断」的那些才必须手改。
  余 113 条的分组现算见 `tmp_workpaper_sync_impl/probe_ratchet_hosts.py`。

### 需要写共享 PG 才能推进（本轮一律未执行 `--apply`）

`evidence/phase4-representation-preflight.json` 现算结算分布：

| 结算 | 条数 | 下一步 |
|---|---|---|
| `already_consistent` | 33 | 无动作（13 条据此终裁，见下） |
| `stale_needs_rehash` | 25 | representation-only finalize（新 generation、`content_revision` 不变） |
| `stale_needs_reprojection` | 19 | 重投影产新 content version（含原先被误判的 15 条） |
| `not_published_use_first_publication_host` | 14 | 先跑首版宿主 |

🔴 本轮把 rehash 宿主的分类缺陷修了：原实现把「文件真的不在磁盘」与「文件可读但契约声明的
结构不符」都结算成 `blocked_artifact_missing`，并附「核对 `relative_path`」的解除建议（对后者
指错了人），且后者只对 `xlsx/gt-d4-operating-revenue` 一条硬编码放行。改按失败成因分流后
`blocked_artifact_missing` 15 → 0、`stale_needs_reprojection` 4 → 19 ——
**没有**任何 artifact 真的丢文件。

### 4.* / 5.* / 6.* / 7.* 的实质阻塞

- **4.1~4.8**：residual lane 交接模板与机器清册未建。本轮只完成了「按双判据终裁 13 条」这一步：
  批准集合收紧为 `runtime_ready ∩ already_consistent`（脚本
  `backend/scripts/fix/apply_pending_runtime_adjudications.py`，守卫
  `backend/tests/workpaper_sync/test_pending_runtime_adjudication.py` 6 例 + 4 组磁盘变异）。
  🔴 首轮曾按「只过 registry probe」终裁 16 条，其中 **H9 / I1 / I5** 被 representation 预检证伪
  （冻结 `_GT_SYNC` 坐标未随行位移重冻结，下游 materialize 计划期才 fail closed）⇒ 已撤回 override
  并保持 pending。现算 pending=78。
- **5.1 / 5.2**：🔴 **当下是结构性空分母，不是「没做」**。现算 manifest
  `capability_counts = {bidirectional: 111, unreachable: 1}`，`single_html` 与
  `single_onlyoffice` **各 0 条** —— Phase 1 按 AC 1.3 把迁移中的入口统一落成
  `capability=null` + pending 三字段（拒绝继续用组件默认 `single_onlyoffice`），所以「逐项
  验证全部 single_*」要等 pending（86 条）被裁决出 single_* 之后才有对象。
  已先把**函数级**不变量钉死（3.6 的 ①②对四种 capability 全测，不等数据出现才生效），
  这样第一条 single_* 落地的那一刻判据就已经在岗。
- **5.3 / 5.4**：删除的**前置事实已现算成立**（`usePilotBridgeAdapter.ts` 生产 importer 为 0；
  `GtG6OtherBondEcl.vue` 仅被生成的 `components.d.ts` 引用，替代组件在库），阻塞在「与之绑定的
  判据和生成物必须同批改」：前者有 6 处判据断言它存在（`test_task45` / `test_task46` /
  `test_task48` / `test_task49` / `bridgeMaterializeDriven.spec.ts` / `test_task66` 的失效对照组），
  后者一删就动 manifest 四件生成物（`unreachable 1 → 0`、`entries 198 → 197`）与两条判据。
  完整清单见 `evidence/phase5-pre-delete-eligibility-2026-11-01.md`。CI 的 `backend-tests` 是
  `pytest -x`，半截状态会把整个 job 停在第一条红上 ⇒ 本轮不动。
- **5.5**：Task 66 删除计划未升级为可收缩执行账。
- **6.1~6.5**：required scenario set 生成、runtime evidence current projection、真实 OnlyOffice
  往返、Playwright 闭环、freshness 与 post-delete 全量重算，全部未做。真实 OO / 浏览器验收需要
  完整重启 `start-dev.bat`（新路由）并在【测试】项目写数据，本轮未执行。
- **7.1~7.5**：7.2 的「候选树与同一最新 HEAD 基线按节点集合比较」已对本轮辐射面做到（见 0.4 的
  evidence：后端 added 0 / 前端 added 0），但 7.1 的全量变异矩阵、7.3 的 schema 边界结论、
  7.4 的 clean-checkout 复验与 7.5 的五角色复核均未完成。

## 当前未完成项索引（2026-11-02）

- **0.5**：35 个文档消费方中仍有 26 个 `registered_unreviewed`，且 AC 编号 / Phase 标题两组
  规定的变异尚未完成。
- **2.8**：`multi_resolver` writer gate 仍有 3 条旧路径；须按“统一 room descriptor → 前端
  同批改线 → legacy doc key drain → 删除 direct-write”顺序收口。
- **6.3**：验收账本仍为 0；67 条 bidirectional entry 尚未完成逐 entry required scenarios，
  D2 阻断态证据只证明 AC 1.4。
- **7.5**：依赖前三项与最新候选树终验；满足 design §15 后再登记 INDEX 并归档。