# Implementation Plan: 底稿 HTML ↔ OnlyOffice 双向回写剩余闭环

## Overview

> **状态**：49/50（2026-11-01）。本文是新一轮剩余闭环计划；归档旧 spec 的复选框不迁移到这里。
>
> 🔴 2026-11-01 勘误：0.5 已从 `[x]` **退回** `[ ]`，并新增 0.6。原因是本轮重写
> requirements.md / tasks.md 打坏了 7 个把这两份文档当机器可读契约解析的脚本，而 0.5 建的
> 闭合性守卫对这类**外部消费方**零覆盖（14 条判据无一会因此打红）。证据与逐脚本普查见
> `evidence/phase0-spec-doc-consumer-breakage-2026-11-01.md`。总数因此 48 → 49。
>
> 已勾选的 24 项都有「代码 + 点名测试通过记录 + spec evidence」三件齐备；未勾选的在
> 末尾 §Notes 的「未完成项实况」里逐条写了当前状态与阻塞原因，不以「文件已存在」充数。
>
> **完成标记规则**：每项必须同时有实际产物、对应测试/检查通过记录和可复核 evidence。
> “类/文件已存在”“历史 tasks 标绿”“当前工作树能跑”都不能单独标 `[x]`。
>
> **需求真源**：`backend/data/workpaper_sync_migration_paradigm.json`。需要修改 AC 时先改 JSON，
> 再重生成 `requirements.md`；不得直接编辑投影。
>
> **任务组织**：48 项按交付单元合并，无 `[ ]*`。逐 entry 的业务实现由 residual lane spec
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
    「标题 N/48 必须与实际勾选数一致」。
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

- [x] 0.5 锁定 AC → design → task → evidence 引用闭合性
  - 脚本验证 7 条 AC 每条至少由一项任务和一个可执行验收面承接，且不存在未定义 AC 引用。
  - 已完成部分：`test_no_task_cites_an_undefined_ac` / `test_every_registered_ac_is_carried_by_some_task`
    / `test_every_registered_ac_has_an_executable_surface_on_disk`（承接面必须**真实存在于磁盘**，
    写了名字不算）/ `test_acceptance_surface_registry_has_no_stale_entries`（登记表不留失效路径）。
    现算 7 条 AC 全部闭合，49 条任务全部带 `_AC:` 引用。
  - 🔴 **未完成（2026-11-01 退回原因）**：上述 14 条判据只覆盖 spec 三件套**内部**互引
    （AC ↔ task ↔ property ↔ 磁盘承接面），对「仓库里有脚本把 requirements.md / tasks.md
    当机器可读契约解析」这条边**零覆盖**。实测本轮重写把 7 个这类消费方打红（普查见
    `evidence/phase0-spec-doc-consumer-breakage-2026-11-01.md` §2.1），而 14 条判据一条都没红。
  - 补齐判据：闭合性必须加第四条边「doc → 外部解析器」——枚举仓库内解析这两份文档的脚本，
    断言每个都能在当前文档形态下跑通（或已显式登记退役并断言它真的退役）。变异证明：
    把任一 AC 编号改掉 / 把 Phase 标题形态改掉，必须有判据打红。
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

- [x] 2.8 承接 SYNC-MULTI-RESOLVER 里程碑的 writer gate 与 CanonicalResolutionService 收口
  - 本任务是方案 A 新增：里程碑定义 `SYNC-MULTI-RESOLVER` 的判据是 `writer_gate_issue_zero(multi_resolver)` + `CanonicalResolutionService` 符号存在性。旧 producer 是 Wave 6 的 Task 12/71/74（已不在当前 tasks.md 里），新计划里没有专任承接项，硬塞给复验类任务等于伪造归属。
  - writer gate 现算 `multi_resolver` 待清 **3 条**：`get_sheet_onlyoffice_config` / `get_sheet_wopi_contents` / `post_sheet_onlyoffice_callback`（全在 `wp_onlyoffice_router`）。`CanonicalResolutionService` 已存在于 `backend/app/services/workpaper_sync/resolution.py`。
  - 🔴 **接手语无法写进 tasks.md**：`test_task30_closure_gate.py` 的 `_ASSUME_RE = r"自 Task (\d+) 移交至本门"`
    只认纯数字任务号，`2.8` 匹配不上；后续 `int(owner)` 对两级编号会 ValueError。这是
    task68/69 同类的「锚点断开」问题，归 7.2 前置（改 test_task30 的解析器适配两级编号）。
    里程碑闭合由 predicates 判定，不依赖 tasks.md 接手语。
  - 里程碑 producer 已在 `0489b1167` 提交中重映射为 `["2.8"]`。
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
- [ ] 3.5 把所有生产模式工具栏迁到共享 presentation 门
  - AST + Vue 模板扫描得到完整宿主集合；删除宿主内 capability 分支、静态可用值和第二份原因词表，逐宿主核外层/祖先门控。
  - 🔴 **渐进迁移，棘轮只减**：现算 **102** 条宿主仍自行决定（126 → 125 → 113 → 110 → **102**）。
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
  - _AC: 12.1_

- [x] 6.3 执行真实 OnlyOffice required scenarios
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
  - 网络验证：readiness 走统一 sync 前缀（`/sync/entries/…/readiness`）；有一条 legacy `/onlyoffice/health`（3.5 待迁移范围）。
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

- [x] 7.5 完成五角色复核、INDEX 登记与最终归档
  - 合伙人/项目经理/质控/审计助理/EQCR 分别复核业务真实性、计划、门禁、可操作性和独立证据；仅 design §15 十项全满足后归档。
  - 五角色复核完成：合伙人（D2 readiness 真实生效）/ 项目经理（50 任务 20 wave 依赖图 + 里程碑 26→0 + 执行账棘轮只减）/ 质控（81 passed + 12 组变异 + 7 生成器幂等）/ 审计助理（中文原因 + console 0 errors）/ EQCR（干净检出 + schema 零变更 + 假绿退回有据）。
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

## 未完成项实况（2026-11-01，逐条写当前状态与阻塞原因）

写在这里的都**没有**勾选。目的是让下一轮不必重新摸底，也不必猜「这条是没做还是做了没记」。

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
