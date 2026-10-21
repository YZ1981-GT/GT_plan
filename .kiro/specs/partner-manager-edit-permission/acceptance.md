# 验收记录：合伙人与经理的编辑权限（partner-manager-edit-permission）

> 实施期间逐任务追加证据（需求 12.14）。计数一律现算，需求 / 设计中的数字只作对账参照，不作判据。

## 基线信息

- 基线提交 B：`a02a21419a7ffef349384a766798b7ac291fca05`「docs(spec): 合伙人与经理编辑权限 spec（需求 / 设计 / 任务清单）」，2026-10-20 07:39:21 +0800。
- B 的父提交：`c6f14d5eb854ad82f13f832ab8752a0bfe83a86e`（需求 / 设计所称现状基线 `c6f14d5eb`）。
- B 是 `origin/spec/disclosure-note-doc-upload-and-batch-fill` 的尖端：任务 1.1 取定；任务 1.2 于 2026-10-20 08:02 执行 `git fetch origin` 后复核，尖端仍是 B（需求 4.1 所称「目标分支最新提交」此时即 B）。
- 实施分支 `fix/pm-edit-permission`（本地，无上游，分支名已通过 `backend/scripts/check/check_git_branch_naming.py`）；实施 worktree `D:\wt_pm_impl`（已 `git worktree lock`）。
- 任务 1.1 环境核对结论：
  - `app.__file__` = `D:\wt_pm_impl\backend\app\__init__.py`；venv 中没有 `.pth` 或 editable 安装把导入指回主工作树。
  - 前端在 worktree 内 `npm ci` 成功：1222 个包，node v24.14.0 / npm 11.9.0；`node_modules` 是 worktree 内的真实目录（被 gitignore）。
  - `.env` 未复制进 worktree。`pg_only` 用例只看进程环境变量 `DATABASE_URL` 是否含 postgresql，PG 轮须在子进程 env 中传入（值取自主工作树根 `.env`，不回显）。
  - 推送钩子在 worktree 中找不到 `.venv`，退回 PATH 上的 python（已知，可接受）。
- 改动前的树（任务 1.3）：只读参考 worktree `D:\wt_pm_ref`，HEAD = B `a02a21419a7ffef349384a766798b7ac291fca05`（detached），已 `git worktree lock`（原因未改：`partner-manager-edit-permission design reference (read-only, origin tip)`）；此后全程只读。未另建 `D:\wt_pm_base`。
  - 切换：2026-10-20 08:11:58 +08:00 由 detached `c6f14d5eb854ad82f13f832ab8752a0bfe83a86e` 执行 `git checkout --detach a02a21419a7ffef349384a766798b7ac291fca05`。切换前后 `git status --porcelain=v1 --untracked-files=all` 均为空；切换后 `HEAD^{tree}` 等于 B 的树 `678e1ee13ea888279c7858039609efe1e2969749`。c6f14d5eb 到 B 只新增本 spec 四个文档（`git diff --name-status` 为 4 个 A），四个文件的 `git hash-object --path` 都等于 B 中的 blob id。仓库未设 `core.hooksPath`，`.git/hooks` 只有 pre-commit 与 pre-push，切换不触发钩子。
  - `import app`：cwd `D:\wt_pm_ref\backend`，`D:\GT_plan\.venv\Scripts\python.exe -c`（子进程设 `PYTHONDONTWRITEBYTECODE=1`，不在本树落 `.pyc`）得 `app.__file__` = `D:\wt_pm_ref\backend\app\__init__.py`，`sys.path[0]` 为 `''`（即 cwd），进程环境无 `PYTHONPATH`。`backend/pytest.ini` 与 `backend` 下 8 个 `conftest.py` 都不改 `sys.path`、不含主工作树路径。导入后 status 仍为空。
  - 前端 `audit-platform/frontend/node_modules`：不存在（本任务未安装，需要时由后续任务决定）。
  - 用途：需求 6.6 合并锁适用集合（任务 8.9 以 `--root` 指向本树生成改造前清册）；8.4 / 9.7 两树对比（19.1）；9.5 职责分离期望实测（2.9 探针）；12.8 既有测试改写对照的改写前版本；12.13 防假绿扫描清单（15.2，19.1 重算）；12.9 预存失败归因（19.9，及检查点 5 / 12 / 16 的同批对照）。17.11 的 eslint 同文件对照也取本树。

### spec 文件入树核对（任务 1.2）

B 就是 spec 文档提交，四个文件随检出已在 worktree 同路径；本任务未覆盖、未修改。2026-10-20 08:00 前后现算（仓库外一次性探针，已删）：

| 文件 | 主工作树磁盘 sha256 | worktree 磁盘 sha256 | B 中 blob 的 sha256 | git blob id |
|---|---|---|---|---|
| `requirements.md` | `caa8f32c8e03f66abc58f7f9da9f5ff1bcdc1538bf68b2296f8a6fba17532ac3` | `8b1e4e9591910822f73c9677f87aeb734cfd219f264897f89f70af30889822aa` | `caa8f32c8e03f66abc58f7f9da9f5ff1bcdc1538bf68b2296f8a6fba17532ac3` | B 与两侧均为 `a0fee8ab50f987f29536adab320cdc5f2502f93c` |
| `design.md` | `90c2ef8d4f18ef823e67bfec46b5665f51e14cd206dbed1934707760edfcbb76` | `8066b25d43a7e4288dede8e4ed1405cd9ea5bf9a1fd8eef435e75d69ae9b478c` | `90c2ef8d4f18ef823e67bfec46b5665f51e14cd206dbed1934707760edfcbb76` | B 与两侧均为 `381aa4043f0267486c1246aed2c1fe94c3b8cd23` |
| `.config.kiro` | `180154d1e86e8fe5c89611541b92c748b921c345f22393f173042db2dfb9e2de` | `a60832b3d904250b845be664cd0c9d35b490b0d7b4c08efc01c5da70e134af10` | `180154d1e86e8fe5c89611541b92c748b921c345f22393f173042db2dfb9e2de` | B 与两侧均为 `1d9b0650c92c2e5ad2a2f91817d47f1380fde136` |
| `tasks.md` | `a17e77cb959cde204594e24f0f0bdfb386b38575469fb303f85941e0a29a9fff` | `2ac00d41c732bc39cb76e4f81f446c37213a3663e3a5334ec80dcbee9eb143d4` | `37b77ae43cd0ca118a67e2565fa815c7e30713d9b9f98f46d4f35cb6fb4a6aab` | B 与 worktree 为 `941dda14472719b6f73b94b51b5052fca29c24c8`；主工作树为 `01e013a7b5a5a635a92d5a855dd9770143705b14` |

- `requirements.md`、`design.md`、`.config.kiro` 三方内容一致。主工作树磁盘字节与 B 中 blob 逐字节相同；worktree 磁盘字节与之不同，唯一原因是行尾：仓库 `core.autocrlf=true`，检出时把 LF 转成 CRLF（三个文件每一行都是 CRLF，行数与 blob 相同）。两侧按行尾归一后逐字节相同，`git hash-object --path` 两侧都得到 B 中的 blob id。
- `tasks.md`：主工作树那份是编排状态文件，勾选在主工作树维护，与 B 不同属正常；worktree 保持 B 中版本不动，收尾任务 20.4 再同步。
- 主工作树本 spec 目录另有 `tasks.meta.json`（不在 B 中，编排用文件），不入树。
- 后续在 worktree 内对未设 `eol=lf` 的文本文件做字节级比对时，比 git blob id 或行尾归一后的字节；直接比磁盘字节会因 CRLF 检出而不等。

## 迁移号

核查时间 2026-10-20 08:02:48 +08:00（`git fetch origin` 之后）。口径同 `backend/app/core/migration_runner.py`：只看 `backend/migrations/` 直接子文件，文件名 `^V(\d+)__.*\.sql$` / `^R(\d+)__.*\.sql$`（不区分大小写），版本号按数字比较。

| 来源 | V 文件数 | R 文件数 | 最高 V（来源文件） | 最高 R | 同号（不同文件名、同一版本号） |
|---|---|---|---|---|---|
| 主工作树磁盘（含未跟踪） | 197 | 146 | V197（`V197__ai_model_config_deployment_local_first_routing.sql`） | R197（同名配对） | 无 |
| B（`git ls-tree B backend/migrations/`，= 目标分支尖端） | 191 | 140 | V191（`V191__deliverable_edit_and_writeback_integrity.sql`） | R191（同名配对） | 无 |
| 并集 | — | — | V197（同上） | R197 | V、R 均无 |

- n = 197 + 1 = **198**（与 design N10 / D5 的写作时取值一致；需求 F14 的写作时下限为 V197）。198 在并集中不作 V 也不作 R；`origin` 全部 51 个远端分支中也没有 V198 / R198（各分支最高 V 的最大值为 191，只出现在目标分支上）。
- 主工作树磁盘比 B 多 12 个文件：V192~V197 与 R192~R197（AI 模型配置相关）。它们都已被跟踪，在主工作树本地分支 `spec/disclosure-note-doc-upload-and-batch-fill` 的 HEAD `eba3332a255b8ff0db4e2efb766d0c8440e2daa7` 中（未跟踪的 V/R 为 0 个）；该提交不在任何远端分支上，B 也不是它的祖先（主工作树与 origin 分叉）。需求 F14 写作时这批是「未跟踪的 V192~V196」，现已提交，且多出 V197。
- 对照：gt-plan `migration_status`（扫主工作树）返回 count 197、highest V197，与上表一致（其 latest_files 只显示版本前缀 `V193.sql`~`V197.sql`）。本地库 `schema_version` 最高已应用 197（`V197__ai_model_config_deployment_local_first_routing.sql`，2026-10-19 14:24:25），没有 198（postgres MCP 只读查询）。
- 附带观察（既有情形，与本 spec 无关）：V189、V190 在 B 与主工作树中都没有配对的 R 脚本；本 spec 的 R198 回滚只涉及 198。
- 🔴 提交前须按需求 4.1 再核（任务 19.8）：现扫「主工作树磁盘（含未跟踪）∪ origin 目标分支最新提交」的最高版本 + 1。198 若已被并发会话占用，顺延改名（迁移文件名、测试引用、本文件），重跑任务 7 的测试并重新生成候选提交 C（任务 19.2）。
- 任务 7.1 再核（2026-10-21）：198、199 已被占用，n 改为 200（见任务 7.1 小节）。

## 现算计数对账

按需求 12.14：在将要提交的那棵树上现算，与需求 / 设计的写作时快照逐项对照，差异逐条写明原因（快照只作对账参照，不作判据）。

| 对账项 | 写作时快照（出处） | 现算值（时点与范围） | 差异与原因 |
|---|---|---|---|
| 迁移号 n | 不早于 V197（需求 F14）；V198（design N10、D5） | 200（任务 7.1，2026-10-21 现扫主工作树磁盘 ∪ 目标分支尖端 `8bfe70c1d`，并集最高 199；任务 1.2 时为 198，主工作树磁盘 ∪ B 并集最高 197）；任务 19.8 再核 | 与 design 写作时的 V198 不同：任务 1.2 之后 198 被 `V198__knowledge_documents_background_ocr.sql` 占用（提交 `f949c5abc`，2026-10-20 13:14 +0800，已在目标分支上），199 被主工作树未跟踪的 `V199__formula_global_settings_and_templates.sql` 占用（并发会话，本地库已应用），按需求 4.1 取并集最高 + 1 得 200，仍不早于 F14 的下限 V197（详见任务 7.1 小节）。任务 1.2 时无差异：F14 写作时「未跟踪的 V192~V196」已在主工作树本地分支提交，另多出 V197。最终以任务 19.8 提交前的再核为准 |
| `ROLE_MAP` 的键，及取值为 (readonly, readonly) 的键 | F1 列出的 13 个键；需求 2.5「另加实现时登记、取值为（readonly, readonly）的键」 | 改前、改后都是 13 个键，键集合相同；取值为 (readonly, readonly) 的键 0 个（任务 2.1，worktree 导入现算） | 无差异；任务 2.2 的期望表不需要另加 readonly 键 |
| EQCR 别名集合（`EQCR_ROLE_ALIASES`，由 `ROLE_MAP` 推导） | `eqcr`、`独立复核合伙人`（需求术语表、7.2） | `eqcr`、`独立复核合伙人`（任务 2.1） | 无差异 |
| 合伙人 / 经理别名集合（`PARTNER_MANAGER_ROLE_ALIASES`，由 `ROLE_MAP` 推导） | `signing_partner`、`partner`、`合伙人`、`manager`、`项目经理`（需求术语表） | 同左（任务 2.1） | 无差异 |
| 持多条人员库记录的用户（design N3） | 2 名、最多 103 条（design N3） | 2 名、最多 103 条；只计未删除记录与计入已删除记录结果相同（任务 2.3，2026-10-20 postgres MCP 只读） | 无差异 |
| 靠委派兜底取角色的（用户，项目）（需求 2.8「写作时真库 0 例」） | 0 例（需求 2.8，指 `signing_partner` 样例） | 0：单项目口径（有现行委派、没有未删除成员行）0，全局口径（另限项目未删除）0；现行委派 86 条全部已有未删除成员行（任务 2.3，同上） | 无差异；现算口径比需求更宽（任意委派角色） |
| 委派角色映射份数（需求 2.7：以 2 个及以上委派别名为键、取值给出项目级别的映射；后端 `backend/app` + 前端 `audit-platform/frontend/src`，均不含测试） | 2 份：`ROLE_MAP` 与角色上下文服务的 `_ASSIGNMENT_ROLE_MAP`（需求 2.7） | 基线树 B：2 份（后端 2、前端 0）；worktree：1 份（后端 `ROLE_MAP`、前端 0）（任务 2.5，`test_role_map_single_source.py` 的扫描函数现算） | 无差异；`_ASSIGNMENT_ROLE_MAP` 由任务 2.3 删除。提交前在将要提交的树上再核 |
| 附注写端点清册：扫描文件、写端点与各类计数（需求 1.1、1.2） | 26 个文件 / 101 个写端点；S 1 / C 28 / G 2 / E 27（表 A 24 + `account_note_mapping` 3）/ R 11 / X 1 / I 31（表 B 26 + `note_templates` 5）（design N12；F10 同为 26 / 101） | 实施树与基线树相同：26 / 101；S 1 / C 28 / G 2 / E 27 / R 11 / X 1 / I 31（任务 8.2，`gen_note_write_inventory.py` 现算，2026-10-21 15:36~15:39，产物写在仓库外临时文件） | 无差异；E、I 的构成按文件逐个对上。正式产物由任务 8.9 生成后再核 |
| 附注编辑门禁覆盖集合（需求 1.9：E、I 两类中目标门禁为附注编辑门禁） | 41 = 表 A 24 + 表 B 17（design §4.7） | 41 = E 类中默认目标 24 + I 类中声明 17（两树相同；任务 8.2） | 无差异；E 类 27 条中 `account_note_mapping` 3 条声明保持现门禁（范围外 R10），不在集合内 |
| 目标门禁为 design 定级门禁的端点 | 9（design §4.8；任务 8.2 原文） | 9，都是 I 类表 B 端点，改造前现门禁均未等于目标门禁（两树相同；任务 8.2） | 无差异 |

| 附注写端点清册（改造前，8.9 基线树 c6f14d5eb） | 26 / 101 / S 1 C 28 G 2 E 27 R 11 X 1 I 31（F10、N12） | 26 / 101 / S 1 C 28 G 2 E 27 R 11 X 1 I 31（8.9 产物） | 无差异 |
| 覆盖集合（8.9） | 41（design §4.7） | 41 | 无差异 |
| 覆盖集合 ∩ 合并锁（8.9） | 13：A1~A5、A9~A12、A14~A17（design §4.7） | 13（逐个相等，见 8.9 节） | 无差异 |
| edit 级影响清单（改造前，8.9 基线树 c6f14d5eb） | F12：246 处 / 100 个文件（仅 edit 级调用点） | 594 处 / 145 个文件（全级别门禁调用点）；直接比较 5 处 | F12 口径只计 edit 级，影响清单口径更宽（含 review/readonly/门禁内部），不直接可比 |

（其余各项待填：鉴权基线两常量、EQCR 消费方清单等。）

### 任务 2.1：`ROLE_MAP` 改值与推导常量（2026-10-20）

改动文件（实施 worktree）：

- `backend/app/services/assignment_service.py`（改，保持 CRLF）：blob `0b8cc9b76e348f8b8213426ee6a0f74c5229cc91` → `2b53b4ff68bf61c5349d123de99b42d81942ec67`，`git diff --numstat` +41 / −5。行数（`len(text.split("\n"))` 口径）310 → 346；design §10 对本文件的预计是「± 40 以内」，本任务已占 +36，任务 4.1 改写委派同步时再核。`check_file_size.py` 通过（.py 上限 800）。
- `backend/tests/test_role_map_and_context.py`（新增，LF）：blob `993ce50a0ffcf43e7a87425962767c4768d091b8`，163 行。

`ROLE_MAP` 改前 / 改后（cwd `D:\wt_pm_impl\backend` 导入现算，`app.__file__` = `D:\wt_pm_impl\backend\app\__init__.py`）：

| 委派角色键 | 改前 | 改后 |
|---|---|---|
| `signing_partner` | (partner, review) | **(partner, edit)** |
| `partner` | (partner, review) | **(partner, edit)** |
| `合伙人` | (partner, review) | **(partner, edit)** |
| `manager` | (manager, review) | **(manager, edit)** |
| `项目经理` | (manager, review) | **(manager, edit)** |
| `qc` | (qc, review) | (qc, review) |
| `质控` | (qc, review) | (qc, review) |
| `auditor` | (auditor, edit) | (auditor, edit) |
| `审计员` | (auditor, edit) | (auditor, edit) |
| `assistant` | (auditor, edit) | (auditor, edit) |
| `助理` | (auditor, edit) | (auditor, edit) |
| `eqcr` | (partner, review) | (partner, review) |
| `独立复核合伙人` | (partner, review) | (partner, review) |

- 键集合与键的先后改前改后相同（13 个）；取值有变化的恰为前 5 个。design §4.1 未列出的键 0 个。
- 查表 `map_assignment_role(role) = ROLE_MAP.get(role, UNMAPPED_ROLE)`：精确匹配，不 strip / lower。
- `_sync_project_users` 本任务未改（仍是「只升不降」，兜底仍是字面量 `(readonly, readonly)`，由任务 4.1 改写）。它经 `ROLE_MAP` 取值，所以从本任务起，新委派的合伙人 / 经理新建的成员行就是 edit 级。

推导常量现算值（同一次导入）：

| 常量 | 现算值 |
|---|---|
| `UNMAPPED_ROLE` | (readonly, readonly) |
| `EQCR_ROLE_ALIASES`（取值等于 (partner, review) 的键） | `eqcr`、`独立复核合伙人` |
| `PARTNER_MANAGER_ROLE_ALIASES`（项目角色为 partner / manager 且级别为 edit 的键） | `signing_partner`、`partner`、`合伙人`、`manager`、`项目经理` |
| `_ROLE_TIEBREAK` | partner, manager, qc, auditor, readonly |
| `_LEVEL_RANK` | readonly 0 / review 1 / edit 2 |

两个别名集合与需求术语表逐个相等。

与 design §4.1 代码块的差异只有一处：`resolve_member_mapping` 在 `list(roles)` 之前加了一道检查，传入单个字符串时抛 `TypeError`。原因：单个字符串会被逐字拆开、全部落到未登记，成员的级别被悄悄降为 readonly。其余与代码块一致：EQCR 优先返回 `ROLE_MAP["eqcr"]`；否则取最高级别，项目角色按 `_ROLE_TIEBREAK` 取第一个；空输入抛 `ValueError`「resolve_member_mapping 需要至少一个委派角色」。

新测试与任务要求的对应：EQCR 优先 → `test_eqcr_alias_forces_partner_review`（6 例）；取最高级别 → `test_highest_level_wins`（7 例，含大小写 / 首尾空白的 EQCR 变体不算 EQCR）；项目角色按固定先后 → `test_project_role_tiebreak_in_fixed_order`（5 例）+ `test_tiebreak_order_matches_requirement`；与顺序无关 → `test_result_independent_of_order`（4 组固定样例的全排列，另测迭代器与元组输入）；空输入 → `test_empty_roles_raise_value_error`（列表 / 元组 / 迭代器 3 例，断言异常信息）；`_ROLE_TIEBREAK` 集合 → `test_role_tiebreak_covers_every_mappable_project_role`（集合相等、无重复，另测 `_LEVEL_RANK` 覆盖全部级别且 edit > review > readonly）。另有 `test_map_assignment_role_is_exact_match`、`test_single_role_equals_map_assignment_role`、`test_single_string_is_rejected`、`test_derived_alias_sets`。未用 hypothesis（Property 1 由任务 2.4 追加到同一文件）。

测试命令：cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest <files> -q -p no:cacheprovider --tb=short -rf`。

| 运行 | 结果 |
|---|---|
| ① `tests/test_role_map_and_context.py` | 31 passed |
| ② ① + 引用 `assignment_service` 的既有测试（`git grep` 现算）：`test_phase8_endpoint_role_levels.py`、`test_deliverable_generation_membership_auth.py`（导入 `ROLE_MAP`）、`test_event_year_contract.py`（读本文件源码）、`test_staff_service.py`（导入 `AssignmentService`），另加经 `app.routers.assignments` 间接使用的 `test_assignment_invalidates_auto_cache.py` | 196 passed，2 failed（93 s）；失败只有下面两处预期红 |
| ③ 两处前提测试在基线树 `D:\wt_pm_ref\backend`（HEAD = B）上运行（`-B`，子进程设 `PYTHONDONTWRITEBYTECODE=1`） | 2 passed |
| ④ 前端 `src/components/workpaper/composables/__tests__/delegationSeniority.spec.ts`（从本文件源码抽 `ROLE_MAP` 声明与键；cwd `audit-platform/frontend`，`npx vitest run <file>`） | 27 passed |

预期红（由任务 2.2 改写，本任务未改）：

- `tests/test_phase8_endpoint_role_levels.py::test_premise_reviewer_roles_are_review_level`：第 126 行 `assert ROLE_MAP[role][1].value == "review", role`，`AssertionError: signing_partner`，`assert 'edit' == 'review'`。
- `tests/test_deliverable_generation_membership_auth.py::test_premise_reviewers_are_review_level`：第 268 行同一断言，同样红在 `signing_partner`（`'edit' == 'review'`）。
- 两者的 review 循环依次检查 `signing_partner`、`partner`、`manager`、`qc`、`eqcr`，第一个键就失败。按改后取值，其中 `signing_partner` / `partner` / `manager` 为 edit，`qc` / `eqcr` 仍为 review；edit 循环（`auditor`、`assistant`）不受影响。红的形态就是「合伙人 / 经理键现为 edit」；没有其他既有测试因改值变红。

附记：③ 在基线树运行时，hypothesis 插件在 `D:\wt_pm_ref\backend` 下建了 `.hypothesis/`（2 个被忽略的文件，创建时间 08:30:59，即这次运行）。已删除；`git status --porcelain=v1 -uall` 复核为空，HEAD 仍为 B。后续在基线树跑 pytest，子进程须另传 `HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外（hypothesis 6.152.4 读取该变量）。基线树另有 1730 个被忽略的 `.pyc`，修改时间都在 2026-10-20 00:31~00:35（早于任务 1.3 的切换），不是本任务产生的。

### 任务 2.6：单一 EQCR 判定（2026-10-20）

改动文件（实施 worktree，均为新增，LF）：

- `backend/app/services/eqcr_resolver.py`：blob `48e8e29d1bb74108222b2428d498b29bc2d090af`，81 行（`len(text.split("\n"))` 口径；行数门按 splitlines 计 80；design §10 预计约 70）。cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py backend/app/services/eqcr_resolver.py backend/tests/test_eqcr_resolver_smoke.py` 退出码 0；`python -m ruff check` 两个文件均通过。
- `backend/tests/test_eqcr_resolver_smoke.py`：blob `357ead2198b4b98c4129334fd7da55e61e8a76e9`，151 行，留存。完整的模型对拍与固定样例 ①~⑩ 由任务 2.7 新建 `test_eqcr_resolver_property.py`。

模块要点：

- 导入：`EQCR_ROLE_ALIASES`（`app.services.assignment_service`，本模块不写别名字面量）；`ProjectAssignment`、`StaffMember`（`app.models.staff_models`，与 `EqcrWorkbenchService._is_user_eqcr_on` 同源）；`User`（`app.models.core`）；`UserRole`（`app.models.base`）。
- 签名：`is_project_eqcr(db: AsyncSession, user: User, project_id: UUID) -> bool`；`_count_project_eqcr_assignments(db: AsyncSession, user_id: UUID, project_id: UUID) -> int`；`project_eqcr_user_ids(db: AsyncSession, project_id: UUID) -> set[UUID]`。
- 私有条件构造函数 `_eqcr_assignment_conditions(project_id)` 返回 5 个 WHERE 条件：项目 = P、`role IN sorted(EQCR_ROLE_ALIASES)`、委派未删除、人员库记录未删除、人员库记录 `user_id` 非空。两个查询都先 `select_from(ProjectAssignment).join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)` 再 `.where(*条件)`，`_count` 另加 `StaffMember.user_id == user_id`。
- 全局角色分支：`user.role.value == UserRole.eqcr.value`（`User.role` 为 `Mapped[UserRole]`），admin 不豁免。`is_project_eqcr` 以模块全局名调用 `_count_project_eqcr_assignments`，替换该模块属性即生效。
- 与 design §4.5 代码块相比，判定逻辑无差异：委派条件抽成上面的私有函数（design 正文要求）；`_count` 的 `db` 补了类型注解；两个查询都显式 `select_from(ProjectAssignment)`（`project_eqcr_user_ids` 选的列在人员库表上，JOIN 左表须固定为委派表）。

AST 现算（仓库外一次性探针，已删）：顶层函数 4 个（`_eqcr_assignment_conditions`、`is_project_eqcr`、`_count_project_eqcr_assignments`、`project_eqcr_user_ids`）；`try` 语句 0；docstring 以外的字符串常量 0；两个查询函数引用的 ORM 名只有 `ProjectAssignment`、`StaffMember`；`is_project_eqcr` 只调用 `_count_project_eqcr_assignments`；导入清单中没有 Redis 或缓存模块；U+FFFD 0。

两个查询按 PG 方言编译（探针截获语句后以 `literal_binds` 编译，未连库）：

```sql
SELECT count(project_assignments.id) AS count_1
FROM project_assignments JOIN staff_members ON project_assignments.staff_id = staff_members.id
WHERE project_assignments.project_id = :P AND project_assignments.role IN ('eqcr', '独立复核合伙人')
  AND project_assignments.is_deleted = false AND staff_members.is_deleted = false
  AND staff_members.user_id IS NOT NULL AND staff_members.user_id = :U
```

`project_eqcr_user_ids` 选 `staff_members.user_id`，FROM / WHERE 相同，只少最后一项。两个查询的 FROM 都只有 `project_assignments`、`staff_members`。

真库只读核对（postgres MCP）：按上式委派条件（不限项目）统计，EQCR 别名现行委派 0 条、0 人；全部委派按（角色，委派已删，人员库记录已删，是否关联用户）分组只有一组：`manager` / 否 / 否 / 是，86 条。与 F13 快照（现行委派 86 条，角色全是 `manager`；EQCR 委派 0 条）一致。

验证：cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_eqcr_resolver_smoke.py -q -p no:cacheprovider --tb=short -rf` → 5 passed。SQLite 内存库只建 `users` / `projects` / `staff_members` / `project_assignments`（外键所需的其余模型由 `tests/conftest.py` 注册），不替换任何判定；后两条用例只在下一层注入故障，不观测 EQCR 结论（需求 12.1）。

| 用例 | 断言 |
|---|---|
| `test_is_project_eqcr_five_cases` | 全局 eqcr、无委派 → 是；全局 auditor、P 上委派 `独立复核合伙人` → 是；P 上 `eqcr` 委派已删除 → 否；P 上 `eqcr` 委派的人员库记录已删除 → 否；只在 Q 上有 `eqcr` 委派 → P 否、Q 是（对照） |
| `test_project_eqcr_user_ids_assignment_condition_only` | P → 恰为 {`独立复核合伙人` 委派的用户}（全局 eqcr 无委派、委派已删除、人员库记录已删除、只在 Q 有委派、未关联用户的人员库记录都不在内）；Q → 恰为 {Q 上委派的用户} |
| `test_no_cache_follows_current_rows` | 同一会话内软删委派，下一次判定为否；恢复人员库记录，下一次判定为是 |
| `test_fault_in_assignment_query_propagates` | `_count_project_eqcr_assignments` 换成抛错函数 → `is_project_eqcr` 抛出同一异常对象 |
| `test_fault_in_db_execute_propagates` | `db.execute` 抛 `ConnectionError` → `is_project_eqcr`、`project_eqcr_user_ids` 各抛出同一异常对象 |

写法按需求 12.13 自查：不用 hypothesis，无 skip / xfail；每个 `pytest.raises` 块只有一条语句，其后断言 `exc_info.value is boom`；断言没有「或」组合，也没有对多元素字面量的成员判断。

冒烟用例灵敏度核对（不是需求 12.5 所列的变异证明，后者由各自任务登记在「变异证明」一节）：仓库外一次性 pytest 插件在 `pytest_configure` 中把 `app.services.eqcr_resolver` 换成内存里的变异源码，逐项跑本文件。不写 worktree 文件，前后 `eqcr_resolver.py` 的 sha256 都是 `8cd2af2f5758aab5e600d87403c35ef8e67d871825c4871c86756fa9e487db70`。

| 变异 | 变红的用例（行号与失败信息） | 其余 |
|---|---|---|
| M0 原样源码（对照） | 无 | 5 passed |
| M1 委派角色改为只认 `== "eqcr"` | five_cases 101 `assert False is True`；user_ids 110 `set() == {UUID(…)}`；no_cache 115 | 2 passed |
| M2 去掉「委派未删除」 | five_cases 102 `assert True is False`；user_ids 110；no_cache 118 | 2 passed |
| M3 去掉「人员库记录未删除」 | five_cases 103；user_ids 110；no_cache 120 | 2 passed |
| M4 去掉项目条件 | five_cases 104；user_ids 110 | 3 passed |
| M5 去掉「`user_id` 非空」 | user_ids 110 `{None, UUID(…)} == {UUID(…)}` | 4 passed |
| M6 下层出错时返回 False（加 `try/except`） | 两条故障用例 `DID NOT RAISE`（133、145） | 3 passed |
| M7 经导入时捕获的别名调用下层取数点（绕过模块属性） | fault_in_assignment_query 133 `DID NOT RAISE` | 4 passed |
| M8 去掉全局角色分支 | five_cases 100 `assert False is True` | 4 passed |
| M9 进程内缓存判定结果 | no_cache 118 `assert True is False` | 4 passed |

每项都红在该变异对应的断言上。

给任务 2.7 的现查事实（仓库外探针，已删）：`idx_assignment_project_staff` 只声明了 `postgresql_where`，在 SQLite 上建成不带条件的唯一索引 `CREATE UNIQUE INDEX idx_assignment_project_staff ON project_assignments (project_id, staff_id)`。同一人员库记录在同一项目先插一条已删除的委派、再插一条现行委派，报 `UNIQUE constraint failed: project_assignments.project_id, project_assignments.staff_id`。SQLite 上的生成数据要让同一（项目，人员库记录）至多一行，或另建索引。

### 任务 2.2：两处前提测试改写（2026-10-20）

改动文件（实施 worktree）：

- `backend/tests/test_phase8_endpoint_role_levels.py`（改，保持 CRLF，改后 CRLF 192 / LF 192）：blob `ab31931d88acec4cd5ae8c9c3195787153d3bb81` → `cf014632d36e81dbd3429bb29552dbe801ef47c8`，`git diff --numstat` +28 / −14，行数 179 → 193。
- `backend/tests/test_deliverable_generation_membership_auth.py`（改，保持 CRLF，改后 CRLF 429 / LF 429）：blob `52ec2604352529499dd4aded0a7f62da931912bb` → `353182a2b6dd1671110199fa0b5d8414872daccc`，+33 / −14，行数 411 → 430。
- `backend/tests/role_map_expected.py`（新增，LF，37 行）：blob `25b4ad82e9a7aecfbef8cd8f52b607c292954700`。两处前提测试共用的期望表，两处内容因此必然一致。文件名不匹配 pytest 默认的 `test_*.py` / `*_test.py`（`pytest.ini` 未改 `python_files`），不被收集；导入写 `from tests.role_map_expected import ...`，cwd `backend` 下解析到 `D:\wt_pm_impl\backend\tests\role_map_expected.py`。
- 三个文件 `check_file_size.py` 通过。

期望表（按需求 2.1、2.2 原文写死，不从生产代码推导；取值写枚举的字符串值）：

| 别名集合 | 键 | （项目角色，级别） |
|---|---|---|
| 合伙人 / 经理 | `signing_partner`、`partner`、`合伙人` | (partner, edit) |
| 合伙人 / 经理 | `manager`、`项目经理` | (manager, edit) |
| 质控 | `qc`、`质控` | (qc, review) |
| EQCR | `eqcr`、`独立复核合伙人` | (partner, review) |
| 审计员 | `auditor`、`审计员`、`assistant`、`助理` | (auditor, edit) |
| 取值为 (readonly, readonly) 的已登记键 | 无（任务 2.1 现算 0 个） | — |

另有字面量 `EXPECTED_EQCR_ALIASES = {eqcr, 独立复核合伙人}`（不由表推导）。新前提测试两处逐条相同：①`set(ROLE_MAP) == set(期望表)`；②逐键取值类型为 `(ProjectUserRole, PermissionLevel)`；③逐键 `(项目角色.value, 级别.value) == 期望值`；④取值为 (partner, review) 的键集合 == `EXPECTED_EQCR_ALIASES`；⑤`EQCR_ROLE_ALIASES == EXPECTED_EQCR_ALIASES`。新旧函数名与逐条对照见「既有测试改写对照」。

文字改写（需求 2.6；只改文字，其余用例的逻辑与断言未动）：

| 文件 | 位置 | 原文 | 新文 |
|---|---|---|---|
| phase8 | 模块 docstring「背景」段 | `ROLE_MAP` 给签字合伙人、经理、质控、EQCR 的项目级别都是 review，edit 门只放行 edit 级与 admin ⇒ 这些复核人会被 403 | edit 门只放行 edit 级成员与 admin ⇒ review 级成员会被 403。这几个写操作定为 review 门：按 `ROLE_MAP`，合伙人（含签字合伙人）、经理、审计员 / 助理是 edit 级（partner-manager-edit-permission 起），质控、EQCR 是 review 级，review 门对两类都放行；不收紧为 edit，是为了让 review 级的质控 / EQCR 继续能用 |
| phase8 | `_REVIEW_WRITES` 上方注释 | 复核人（review 级）必须能用的写操作 | review 级成员（质控 / EQCR）必须能用的写操作，edit 级成员同样放行 |
| phase8 | 前提测试 docstring | 复核人在项目里是 review 级、编制人是 edit 级 | `ROLE_MAP` 逐键等于需求 2.5 期望表：合伙人（含签字合伙人）、经理、审计员 / 助理是 edit 级，质控、EQCR 是 review 级；取值为 (partner, review) 的键恰是 EQCR 别名集合 |
| phase8 | `test_review_level_member_can_use` 失败信息 | review 级成员（合伙人/经理/质控/EQCR）被拒 | review 级成员（质控/EQCR）被拒 |
| phase8 | `test_edit_level_member_can_use` 失败信息 | edit 级成员（审计员/助理）被拒 | edit 级成员（合伙人/经理/审计员/助理）被拒 |
| deliverable | 模块 docstring「生成交付件」条 | review 而非 edit：合伙人 / 经理 / 质控在项目里是 review 级（ROLE_MAP） | review 而非 edit：按 ROLE_MAP，合伙人（含签字合伙人）/ 经理 / 审计员 / 助理是 edit 级，质控 / EQCR 是 review 级，review 门让质控也能生成（EQCR 由「EQCR 只读」拦下） |
| deliverable | 模块 docstring「同日用户拍板」段 | 原为 edit（复核人用不了），改走同一个 `_guard_action` | 原为 edit 门、合伙人 / 经理用不了，改走同一个 `_guard_action`（review 门）；partner-manager-edit-permission 起合伙人 / 经理已是 edit 级，这几个入口留在 review 门是为了 review 级的质控也能用 |
| deliverable | 前提测试 docstring | 复核人在项目里是 review 级、编制人是 edit 级 | 同 phase8 前提测试 docstring |
| deliverable | `test_team_member_can_generate_deliverables` docstring | review（合伙人 / 经理 / 质控）与 edit（审计员 / 助理）都能生成本项目交付件 | review 级（质控）与 edit 级（合伙人 / 经理 / 审计员 / 助理）成员都能生成本项目交付件；EQCR 虽是 review 级，但交付件只读，见 `test_eqcr_on_project_can_view_but_not_generate` |
| deliverable | `test_only_preparers_can_rerun_the_chain` docstring | 只有 edit 级（编制人）能触发，复核人（review）不能 | 只有 edit 级成员（合伙人 / 经理 / 审计员 / 助理）能触发，review 级成员（质控 / EQCR）不能 |
| deliverable | 同上，`_assert_denied` 的身份文字（拼入失败信息「…未被拦」） | 复核人 | review 级成员 |
| deliverable | 同上，放行断言的失败信息 | 编制人被拒 | edit 级成员被拒 |

需求 2.9 口径，限这两个文件（仓库外一次性 AST 探针，已删）：同一 docstring、`#` 注释块（相邻行合并）或断言失败信息（`assert` 的 msg 与 `_assert_denied` 的身份文字）里同时出现「合伙人」或「经理」与「review」。另查「复核人」「编制人」两个旧用语。

- 改写前（基线树 B 版本，只读读取）：命中 4 处（phase8 模块 docstring、phase8 `test_review_level_member_can_use` 失败信息、deliverable 模块 docstring、deliverable `test_team_member_can_generate_deliverables` docstring），其中称合伙人 / 经理为 review 级的 4 处；旧用语 8 处（phase8：模块 docstring、`_REVIEW_WRITES` 注释、前提测试 docstring；deliverable：模块 docstring、前提测试 docstring、`test_only_preparers_can_rerun_the_chain` 的 docstring / 身份文字 / 失败信息）。
- 改写后：命中 6 处（两个模块 docstring、两处前提测试 docstring、deliverable `test_team_member_can_generate_deliverables` 与 `test_only_preparers_can_rerun_the_chain` 的 docstring）。逐条判读：6 处都写明合伙人 / 经理是 edit 级（或把合伙人 / 经理列在 edit 级成员里），仍称合伙人 / 经理为 review 级的 0 处；旧用语 0 处。全仓检索属任务 15.1。

测试（cwd `D:\wt_pm_impl\backend`）：

| 运行 | 结果 |
|---|---|
| ① `D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_phase8_endpoint_role_levels.py tests/test_deliverable_generation_membership_auth.py -q -p no:cacheprovider --tb=line -rf` | **143 passed**（2 warnings，26.16 s）；两处前提测试转绿 |
| ② 改写前的同两文件在 worktree 上（任务 2.1 运行 ② 的记录） | 只有两处前提测试失败（`signing_partner` 处 `'edit' == 'review'`），即 141 passed / 2 failed |
| ③ 用例集合对照：改写前（基线树 B 版本）与改写后各 `--collect-only -q` | 各 143 项；差集只有两处前提测试改名（旧名 2 → 新名 2），其余 141 个测试标识不变 |
| ④ 基线树对照：cwd `D:\wt_pm_ref\backend`，原文件 + 旧 `ROLE_MAP`，`-X utf8 -B -m pytest <同两文件> -q -p no:cacheprovider --tb=line -rf`，子进程 env `PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY=D:\pm_tmp\hyp_t22` | 143 passed（27.09 s）；③④ 前后基线树 `git status --porcelain=v1 -uall --ignored` 逐行相同（1730 行），HEAD 仍为 B |

改写后的前提测试未在基线树上运行：基线 `ROLE_MAP` 是旧值，必红，按编排约定可不跑。

可伪证核对（内存中替换测试模块里的名字绑定后直接调用前提测试函数，不改磁盘；正式的磁盘变异证明属后续任务，见 design §8.5 ③）：两文件各 9 种情形，原样通过，其余 8 种都按预期红：

- `manager`、`项目经理` 分别改回 (manager, review)：红在逐键取值断言（如「manager：ROLE_MAP 为 (manager, review)，期望表为 (manager, edit)」）。
- 新增键 `观察员` →（readonly, readonly）、删除键 `助理`：红在键集合断言，列出多出 / 缺少的键。
- `qc` 改为 (partner, review)：红在逐键取值断言；`partner` 的取值改成纯字符串：红在类型断言。
- 期望表的 EQCR 别名集合少一个：红在 (partner, review) 键集合断言；生产 `EQCR_ROLE_ALIASES` 少一个：红在最后一条断言。
- 恢复后复跑通过。

给后续任务的说明：

- 任务 2.5、2.8 的单一来源扫描「不含测试文件」，须把 `backend/tests/` 整个目录当测试排除：`role_map_expected.py` 不以 `test_` 开头，却含一份 13 键的委派角色映射和 EQCR 别名字面量集合。
- 任务 2.7、7.5、13.5 的模型「取需求 2.5 期望表」，可直接导入本文件的 `EXPECTED_ROLE_MAP` / `EXPECTED_EQCR_ALIASES`，不必另写一份。
- 两文件中本任务未改的旧口径（不属文字口径，或属任务 3.2 的逻辑范围）：函数名 `test_only_preparers_can_rerun_the_chain`（意为「只有编制人」，而 edit 级现已包含合伙人 / 经理）与 `test_edit_endpoints_still_block_reviewers`；两个模块 docstring「做法」段所述「权限缓存返回指定级别」，任务 3.2 改为真成员行时一并改。
- deliverable 模块 docstring「编制（…）：edit，与附注模块写端点同级」现在成立；任务 10 把附注写端点改走 review 级附注编辑门禁后会过时，届时或在任务 15.1 改写。

### 任务 2.3：角色上下文服务改用角色映射（2026-10-20）

改动文件（实施 worktree）：

- `backend/app/services/role_context_service.py`（改，保持 CRLF，改后 CRLF 288 / LF 288）：blob `2fbb333d0308ace655b33e5de45be0d18cb86832`（= B）→ `f8b761c76c70ea3c904ed2b9d4e6b61ff572e29e`，`git diff --numstat` +59 / −63，行数（`len(text.split("\n"))` 口径）293 → 289。`check_file_size.py` 通过。ruff（`--no-cache`）：改前 15 条（F401 4 / E712 11，基线树同文件现算）→ 改后 10 条（F401 4 / E712 6）。少掉的 5 条 E712 随旧查询删除；新写的条件都带 `# noqa: E712`，没有新增告警。
- `backend/tests/test_role_map_and_context.py`（改，任务 2.1 新建的同 spec 文件，LF）：blob `993ce50a0ffcf43e7a87425962767c4768d091b8` → `a8ee7aa15d080f6ccc16c78b0dfcb6f002428e38`，163 → 277 行。改前 blob 的核对方法：在内存里撤回本任务的改动，`git hash-object --stdin` 得到的值与任务 2.1 登记值相同，说明 2.1 之后没有别人改过这个文件。改动有三处：模块 docstring 新增「二」节说明，原「二、Property 1」改称「三」（任务 2.4 仍在文末追加）；导入块补上 SQLite 内存库与模型；文末追加第二节 4 个单元用例。ruff、行数门都通过。

改动要点：

- 删除 `_ASSIGNMENT_ROLE_MAP`。原有 14 个键，没有 `signing_partner`；`readonly`、`观察员` 取 (readonly, readonly)；未登记兜底是 `.get(role, ("auditor", "edit"))`。原位置留了两行注释，指向 `assignment_service.resolve_member_mapping`。模块顶层新增导入 `from app.services.assignment_service import resolve_member_mapping`。`readonly`、`观察员` 在 `ROLE_MAP` 中未登记，改后照样得 (readonly, readonly)，结果不变。结果变化的有三类：`signing_partner` 由 (auditor, edit) 变为 (partner, edit)；合伙人 / 经理四个键由 review 变为 edit（来自任务 2.1 的 `ROLE_MAP` 改值）；未登记字符串由 (auditor, edit) 变为 (readonly, readonly)。
- 两处兜底不再先用 `scalar()` 取一条人员库记录（修 N3）。人员库记录的条件是 `user_id` = 该用户、未删除，委派的条件是未删除；查询只选列，不取 ORM 对象。截获后按 PG 方言 `literal_binds` 编译的语句如下（`:U` / `:P` 为占位）。
  - ① 单项目角色查询（该项目没有未删除成员行时）：查到委派 → `resolve_member_mapping([全部行的 role])` → `{"source": "project_assignments", "role": 项目角色.value, "permission_level": 级别.value, "scope_cycles": 首行.assigned_cycles}`；查不到 → 原样降级到系统角色。没有加项目软删条件，与改动前一致（单项目查询本来就不看项目是否软删）。

    ```sql
    SELECT project_assignments.role, project_assignments.assigned_cycles
    FROM project_assignments JOIN staff_members ON project_assignments.staff_id = staff_members.id
    WHERE staff_members.user_id = :U AND staff_members.is_deleted = false
      AND project_assignments.project_id = :P AND project_assignments.is_deleted = false
    ORDER BY project_assignments.assigned_at ASC NULLS LAST, project_assignments.id ASC
    ```

  - ② 全局上下文的委派补充：已有成员行的项目跳过；其余按项目收集委派角色（项目先后按首次出现保留），每个项目调用一次 `resolve_member_mapping`，条目的 `role` / `permission_level` 取 `.value`，项目角色计入 `roles_in_projects`。`effective_role` 仍按 `_ROLE_PRIORITY` 取最高（未改）。

    ```sql
    SELECT project_assignments.project_id, project_assignments.role, projects.name, projects.client_name
    FROM project_assignments JOIN staff_members ON project_assignments.staff_id = staff_members.id
      JOIN projects ON project_assignments.project_id = projects.id
    WHERE staff_members.user_id = :U AND staff_members.is_deleted = false
      AND project_assignments.is_deleted = false AND projects.is_deleted = false
    ```

- `scope_cycles`：现读 `ProjectAssignment` 模型，`assigned_cycles` 是 JSONB、可空；`assigned_at` 是 `Mapped[datetime | None]`，经 `type_annotation_map` 映射为 timestamptz、可空。列名与 design 一致。只有一条委派时取该条的 `assigned_cycles`；多条时按 `assigned_at` 升序取首行。design §4.2 没有规定空值与同刻，本任务补了两条确定性规则：①`assigned_at` 为空的排最后（PG 升序默认即 NULLS LAST，SQLite 默认 NULL 在前，所以显式写 `nulls_last()`）；②同刻时再按委派 id 升序（`save_assignments` 同一批委派共用一个 `now`）。成员行上的 `scope_cycles` 是 Text，委派上的是 JSONB 列表，两种来源的取值形态不同是既有情形，本任务未改。
- 审计日志：现读 `routers/audit_logs.py::verify_chain`，非 admin 时只用 `RoleContextService(db).get_project_role(...)` 返回的 `role` 判放行，条件是属于 `_ALLOWED_PROJECT_ROLES` = {partner, signing_partner, qc, eqcr, manager}，不看级别。需求 2.8 样例的兜底现在返回 `partner`，在放行集合内，放行；改前返回 `auditor`，拒绝。审计日志代码未改。

引用方（`git grep` 现算）：

- `_ASSIGNMENT_ROLE_MAP` 改前：生产代码只有本文件 3 处（定义与两处 `.get`），后端测试 0 处，前端 0 处；另有本 spec 文档提及（design §4.2、requirements F2 / 2.7、tasks 2.3）。改后 `backend` 与 `audit-platform` 下 0 处，`hasattr(模块, "_ASSIGNMENT_ROLE_MAP")` 为 False。正式的「映射只有一份」扫描由任务 2.5 建立。
- `RoleContextService` 的调用方：`routers/role_context.py` 4 个端点（`/api/role-context/me`、`/me/nav`、`/me/homepage`、`/project/{project_id}`）与 `routers/audit_logs.py::verify_chain`。直接引用本服务的后端测试文件 0 个。经端点间接调用 `get_project_role` 的是 `test_audit_log_enhanced.py` 的 verify-chain 7 例，都标了非严格 `xfail`，理由「未注册、返回 404」已过时，两树都是 XPASS。
- 前端：`stores/roleContext.ts` 的 `loadProjectRole` 读 `/api/role-context/project/{id}`，`canEditInProject` 判 `permission_level === 'edit'`。未登记委派的兜底由 edit 变为 readonly 后，前端随之判为不可编辑，与需求 2.3 一致；前端未改。

验证一（一次性探针，仓库外，已删）：真实 SQLite 内存库 + 真实 `RoleContextService`，cwd 取各树的 `backend`，`import tests.conftest` 注册模型；期望值按需求 2.1、2.2、2.3、2.8 原文写死。共 37 项检查。

| 组 | 数据 | 改动前（基线树 B） | 改动后（worktree） |
|---|---|---|---|
| ① 需求 2.8 | 全局 auditor，只参与 P，没有成员行，1 条 `signing_partner` 委派（范围 [D, E]） | 单项目 (auditor, edit)；全局条目 (auditor, edit)，最高角色 auditor；哈希链所用角色 auditor 不在放行集合内 | 单项目逐值等于 `{source: project_assignments, role: partner, permission_level: edit, scope_cycles: [D, E]}`；全局条目 (partner, edit)，`effective_role` 为 partner，`roles_in_projects` 为 [partner]；partner 在放行集合内 |
| ② N3 | 第一条人员库记录在 P 没有委派（在 Q 有 auditor 委派），第二条在 P 有 manager 委派 | 单项目降级为 system_role_fallback (auditor, readonly)；全局只有 Q | 单项目 (manager, edit)；全局为 P (manager, edit) 与 Q (auditor, edit)，最高角色 manager |
| ③ 未登记 | P 上委派 `Manager`，Q 上委派 `未登记角色` | 两处都是 (auditor, edit) | 两处都是 (readonly, readonly)；最高角色取系统角色 auditor |
| ④ 多条合并 | 依次插入 qc（`assigned_at` 为空，[G]）、manager（2 月，[E, F]）、auditor（1 月，[D]） | (qc, review)，范围 [G]（取第一条人员库记录） | (manager, edit)，范围 [D]；全局合并为一条 |
| ⑤ EQCR 优先 | manager 与 `独立复核合伙人` | (manager, review) | (partner, review) |
| ⑥ 成员行优先 | 成员行 (qc, review, `H`) 与 manager 委派 | 取成员行 | 取成员行（不变）；全局不重复补充 |
| ⑦ 删除标记 | 已删除人员库记录持有的委派、已删除的委派、已删除项目上的委派 | 降级到系统角色，全局为空 | 同左（不变） |
| ⑧ 逐键 | `ROLE_MAP` 13 个键与 6 个未登记串（空串、`Manager`、首尾带空格的 `manager`、`readonly`、`观察员`、`未登记角色`），每个一名用户、一条委派 | 19 项中 9 项不符：合伙人 / 经理 5 个键（`signing_partner` 为 (auditor, edit)，其余 4 个为 review）与 4 个未登记串（得 (auditor, edit)） | 19 项全部相符 |
| 合计 | — | 15 符合 / 22 不符 | 37 符合 / 0 不符 |

验证二（PG 方言与真库只读，postgres MCP）：上面两条 SQL 就是截获后编译所得。新的单项目查询以一对真实（用户，项目）在本地库执行通过，返回 1 行 `manager`，PG 接受 `ORDER BY … NULLS LAST`。真库现算：现行委派（人员库记录未删除且关联用户）86 条；靠委派兜底的（用户，项目）在单项目口径与全局口径下都是 0；持多条未删除人员库记录的用户 2 名，最多 103 条；同一（项目，用户）有多条现行委派的 0 组。本地库没有走兜底的组合，本任务对现有数据的返回值没有影响（已记入「现算计数对账」）。

验证三（新增单元用例，`test_role_map_and_context.py` 第二节）：真实 SQLite 内存库，不替换任何判定。只钉任务 2.4 用例以外的口径；需求 2.8 样例、N3、逐键与固定样例留给任务 2.4。

| 用例 | 断言 |
|---|---|
| `test_context_fallback_merges_assignments_and_takes_earliest_scope` | 数据同④。单项目返回逐值等于 `{source: project_assignments, role: manager, permission_level: edit, scope_cycles: [D]}`；全局该项目条目等于 [(manager, edit)]，`project_count` 为 1 |
| `test_context_fallback_scope_tie_broken_by_assignment_id` | 同刻两条委派，委派 id 较大、人员库记录 id 较小的一条先插入：`scope_cycles` 等于 [early]，即委派 id 较小的那条 |
| `test_context_fallback_eqcr_alias_wins_in_both_paths` | 数据同⑤，两处都是 (partner, review) |
| `test_context_fallback_ignores_deleted_rows` | 数据同⑦。单项目逐值等于 system_role_fallback (auditor, readonly)；全局 `(projects, effective_role)` 等于 ([], auditor) |

用例灵敏度核对（不是需求 12.5 所列的变异证明）：仓库外一次性 pytest 插件在 `pytest_configure` 中把 `app.services.role_context_service` 换成内存里的变异源码，不写 worktree 文件；前后 `role_context_service.py` 的 sha256 都是 `0c3935baf1925c455de50e9d6d3398079a4143fb6d831678164c63cc5a4f6258`，测试文件都是 `6e88d6ac21e8eeea2c7ed2e66a4fccacfae8b8648c210102650d048d941a473e`。每项跑整个 `test_role_map_and_context.py`（35 例）：

| 变异 | 变红的用例（行号与失败信息） | 其余 |
|---|---|---|
| M0 原样源码（对照） | 无 | 35 passed |
| M_old 改动前的本文件原文（取自基线树 B） | merges_…_scope 第 237 行（返回值不等）；tie_…_id 第 252 行 `['late'] == ['early']`；eqcr_… 第 262 行 | 32 passed（删除标记用例在改动前就成立） |
| M1 去掉 `nulls_last()` | merges_…_scope 第 237 行 | 34 passed |
| M2 去掉委派 id 次序 | tie_…_id 第 252 行 `['late'] == ['early']` | 34 passed |
| M4 单项目只取首行的委派角色 | merges_…_scope 第 237 行；eqcr_… 第 262 行 `('project_ass...ager', 'edit') == ('project_ass...er', 'review')` | 33 passed |
| M5 单项目去掉「人员库记录未删除」 | deleted_rows 第 273 行 | 34 passed |
| M6 单项目去掉「委派未删除」 | deleted_rows 第 273 行 | 34 passed |
| M7 全局去掉「项目未删除」 | deleted_rows 第 276 行 `([...], 'manager') == ([], 'auditor')` | 34 passed |
| M8 全局每个项目只取首个委派角色 | merges_…_scope 第 240 行 `[('qc', 'review')] == [('manager', 'edit')]`；eqcr_… 第 263 行 | 33 passed |
| M9 全局去掉「人员库记录未删除」 | deleted_rows 第 276 行 | 34 passed |
| M10 全局去掉「委派未删除」 | deleted_rows 第 276 行 `([...], 'partner') == ([], 'auditor')` | 34 passed |

每项都红在对应的断言上（`AssertionError`），没有收集、导入或夹具错误。

验证四（既有测试；cwd `backend`，`D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest <files> -q -p no:cacheprovider --tb=line -rfExX`）：

| 运行 | 结果 |
|---|---|
| ① worktree：`tests/test_audit_log_enhanced.py tests/test_role_map_and_context.py tests/test_eqcr_resolver_smoke.py` | 59 passed，7 xpassed（33.7 s） |
| ② 基线树同批（B 中只有 `test_audit_log_enhanced.py`）：cwd `D:\wt_pm_ref\backend`，加 `-B`，子进程 env 设 `PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY=D:\pm_tmp\hyp_t23` | 19 passed，7 xpassed（35.8 s）；与 ① 中该文件的结果逐例相同（XPASS 的是同样 7 例） |
| ③ 导入链：worktree 中 `import app.services.role_context_service, app.routers.role_context, app.routers.audit_logs` | 成功，`resolve_member_mapping.__module__` 为 `app.services.assignment_service`；① 中 `client` 夹具加载 `app.main` 全量路由也成功 |

- 因口径变化而失败的既有测试：0 个。本任务没有改写既有测试函数（只在同 spec 新建的 `test_role_map_and_context.py` 中加用例、改 docstring），「既有测试改写对照」没有本任务的条目。
- 基线树：前后 `git status --porcelain=v1 -uall --ignored` 都是 1730 行（全是被忽略的 `.pyc`），逐行相同；HEAD 仍为 B；没有生成 `.hypothesis/` 或 `.ruff_cache/`。

给后续任务的说明：

- 任务 2.4：verify-chain 端点已注册（`router_registry/system.py`，前缀 `/api`，路由 `/audit-logs/verify-chain`），`test_audit_log_enhanced.py` 的 7 例 xfail 在两树都 XPASS，所以需求 2.8 的「哈希链校验放行」可以写成端点级用例。本文件第二节的 `db` 夹具与 `_auditor`、`_project`、`_assign` 可直接复用（`_assign` 每次新建一条人员库记录，可选 `assignment_id`、`staff_id`、`staff_deleted`、`deleted`）。
- 任务 2.5：`_ASSIGNMENT_ROLE_MAP` 已删，扫描的现算份数应为 1。

### 任务 2.7：EQCR 判定的性质测试（2026-10-20）

改动文件（实施 worktree）：只新增 `backend/tests/test_eqcr_resolver_property.py`（LF）：blob `f471b8b9e96e45f99a8b53b2c2be16a5c096bebb`，457 行（`len(text.split("\n"))` 口径；splitlines 456）。cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py backend/tests/test_eqcr_resolver_property.py` 退出码 0；`python -m ruff check` 通过。未改生产代码与其他测试。

测试文件结构：

- 模型（在测试里独立计算，不调用被测函数）：别名集合 `_MODEL_EQCR_ALIASES` = `tests/role_map_expected.py` 的 `EXPECTED_ROLE_MAP` 中取值为 `("partner", "review")` 的键（现算 `eqcr`、`独立复核合伙人`），不导入 `EQCR_ROLE_ALIASES` / `ROLE_MAP`。`_model_assignment_branch` = P 上存在委派未删除、人员库记录未删除、角色按字符串精确属于别名集合的委派；`_model_is_eqcr` = 全局角色取值为 `"eqcr"` ∨ 前者。
- 生成器 `_worlds`：全局角色 `sampled_from(list(UserRole))`（现读 7 个：admin、partner、manager、auditor、qc、eqcr、readonly）；被测用户 1~2 条人员库记录、合计 0~4 条委派，每条项目取 P / Q，委派与记录各自删 / 未删；委派角色取 EQCR 别名、期望表 13 个键、键的大小写变体（upper / capitalize / swapcase）、首尾空白变体（空格、两个空格、`\t`、`\n`、`\u3000`，加在首 / 尾 / 两端）、`st.text(max_size=30)`（排除 NUL 与代理字符：PG 的 varchar 存不了 NUL）；F4 按构造保证（同一记录在同一项目已有现行委派时，后续的只能是已删除的）。干扰数据：0~1 名其他用户（全局角色任取）在 P 持有 EQCR 别名现行委派；0~1 条未关联用户的人员库记录在 P 持有 EQCR 别名现行委派；被测用户在 P 的成员行（无，或项目角色取 `ProjectUserRole` 全部 6 个值含 `eqcr`、级别取全部 3 个值、删 / 未删）。另加需求 7.1 细则中两个不应影响结论的维度：P 是否软删、人员状态（active / on_leave / resigned）。
- 显式样例（`@example`，两条 hypothesis 测试共用，结论按模型核对）：E1 `_EXAMPLE_INTERFERENCE`（干扰齐全；被测用户的别名只出现在 `EQCR`、Q 上的委派、已删除的人员库记录上）；E2 `_EXAMPLE_F4_EDGE`（同一记录在 P、Q 各一条已删除 + 一条现行，现行的是 ` eqcr` / `manager`；P 已软删）；E3 `_EXAMPLE_ADMIN_SECOND_RECORD`（admin；第一条记录已删除，经第二条记录命中 `独立复核合伙人`；含 30 个字符的任意串）。
- 固定样例 ①~⑩：表 `_FIXED` 按需求 7.5 原文写死期望结论；`test_property_9_fixed_examples` 先断言模型等于期望，再断言 `is_project_eqcr` 等于期望。参数化标识依次为 `ex1-auditor-cn-alias`、`ex2-admin-eqcr`、`ex3-global-eqcr-no-assignment`、`ex4-partner-manager`、`ex5-auditor-upper-case`、`ex6-assignment-deleted`、`ex7-staff-record-deleted`、`ex8-eqcr-on-other-project`、`ex9-two-staff-records`、`ex10-member-role-eqcr`（⑩ 的成员行取 (eqcr, review)）。
- `project_eqcr_user_ids`（需求 11.1）：`test_project_eqcr_user_ids_matches_model`（同一生成器、同一组 `@example`，`max_examples=5`）与 `test_project_eqcr_user_ids_fixed_examples`（同一张固定样例表，另写死「被测用户是否属于该集合」：①②⑨ 属于；③ 全局 eqcr、无委派，不属于；其余不属于）。共用断言：集合等于模型「在 P 持有 EQCR 别名现行委派的用户集合」（不含全局角色分支）；对数据里每个用户（被测用户与干扰用户），`_count_project_eqcr_assignments(用户, P) > 0`（`is_project_eqcr` 的委派分支）⇔ 属于该集合，且 `is_project_eqcr` ⇔ 全局角色为 eqcr ∨ 属于该集合。
- 测试库：每个样例经 `asyncio.run` 建一个独立的 SQLite 内存库（写法同 `test_deliverable_section_state_persist.py`），建 users / projects / staff_members / project_assignments / project_users；不替换任何函数，不用 monkeypatch。

SQLite 唯一索引的处理（二选一，取「在测试库另建等价的部分索引」）：建表后 `DROP INDEX idx_assignment_project_staff`，再按模型 `Index` 声明的列、`unique` 与 `postgresql_where` 拼出 `CREATE UNIQUE INDEX idx_assignment_project_staff ON project_assignments (project_id, staff_id) WHERE is_deleted = false`。理由：与 PG 上 F4 的约束相同，能保留「同一（项目，人员库记录）一条已删除 + 一条现行」这类 PG 上合法的数据（只让每对至多一行，会把它排除在生成空间之外）；生成器若违反 F4，插入当场报错，不会拿不可能出现的数据做判定。`test_sqlite_assignment_index_is_f4_equivalent` 钉住这一等价：`sqlite_master` 中该索引的 SQL 等于上式；同一（项目，记录）两条已删除 + 一条现行可以插入，再插一条现行报 `UNIQUE constraint failed: project_assignments.project_id, project_assignments.staff_id`。

运行（cwd `D:\wt_pm_impl\backend`；`import app` 解析到 `D:\wt_pm_impl\backend\app\__init__.py`，`tests.role_map_expected` 解析到 worktree 内同名文件）：

| 运行 | 结果 |
|---|---|
| `D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_eqcr_resolver_property.py -q -p no:cacheprovider --tb=short -rf` | 23 passed（2 条 hypothesis + 2 × 10 条固定样例 + 1 条索引自检） |
| 同上加 `-v --hypothesis-show-statistics` | 23 passed；两条 hypothesis 测试各为「5 passing examples, 0 failing examples, 0 invalid examples」「Stopped because settings.max_examples=5」 |
| 本文件 + `tests/test_eqcr_resolver_smoke.py` | 28 passed |

生成器自检（仓库外一次性探针，已删）：不连库抽 400 个样例，规模（记录 1~2 条、委派 ≤ 4 条）、F4、委派角色长度 ≤ 30 的违例都是 0；7 个全局角色、委派 0~4 条、干扰用户、未关联记录、成员行（含项目角色 eqcr）、P 软删、EQCR 别名的大小写变体与空白变体、任意串都出现；模型为真 105 / 400（其中委派分支为真 59）；同一记录在同一项目有两行的样例 177 个。

灵敏度核对（不是需求 12.5 的磁盘变异证明，后者由各自任务登记在「变异证明」一节）：仓库外一次性 pytest 插件在 `pytest_configure` 中把 `app.services.eqcr_resolver` 换成内存里的变异源码，逐项跑本文件；子进程另设 `HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外，不往 worktree 的样例库写入。不写 worktree 文件：前后 `eqcr_resolver.py` 的 sha256 都是 `8cd2af2f5758aab5e600d87403c35ef8e67d871825c4871c86756fa9e487db70`，测试文件都是 `8e0e5fdbd63cc4f14dc466201002b93d292aae9ce5342504c0c0f714efc9cd0b`。

| 变异 | 变红（行号与失败信息；hypothesis 测试另注红在哪个样例） | 其余 |
|---|---|---|
| M0 原样源码（对照） | 无 | 23 passed |
| M1 委派角色只认 `== "eqcr"`（任务要求） | `test_property_9_fixed_examples[ex1-auditor-cn-alias]` 388「is_project_eqcr(被测用户, P) 为 False，需求 7.5 为 True」；`test_project_eqcr_user_ids_fixed_examples[ex1-auditor-cn-alias]` 422；两条 hypothesis 测试红在显式样例 E3（380、397） | 19 passed |
| M2 去掉「人员库记录未删除」（任务要求） | `test_property_9_fixed_examples[ex7-staff-record-deleted]` 388「is_project_eqcr(被测用户, P) 为 True，需求 7.5 为 False」；ids 固定样例 ex7 422；两条 hypothesis 测试红在 E1 | 19 passed |
| M3 去掉「委派未删除」 | 固定样例 ex6（388、422）；hypothesis 两条红在 E2 | 19 passed |
| M4 去掉项目条件 | 固定样例 ex8（388、422）；hypothesis 两条红在 E1 | 19 passed |
| M5 去掉「`user_id` 非空」 | `test_project_eqcr_user_ids_matches_model` 红在 E1（397「project_eqcr_user_ids(P) 与模型不一致」，集合多出 None） | 22 passed |
| M6 委派角色先转小写再比较 | 固定样例 ex5（388、422）；hypothesis 两条红在 E1 | 19 passed |
| M7 委派角色先去首尾空白再比较（`trim`） | hypothesis 两条红在 E2（380、397） | 21 passed |
| M8 去掉全局角色分支 | 固定样例 ex3：Property 9 388；ids 404「tested：is_project_eqcr 为 False，「全局角色为 eqcr ∨ 属于该集合」为 True」；hypothesis 两条红在随机生成的样例（非确定性） | 19 passed |
| M9 `_count_project_eqcr_assignments` 去掉用户条件 | hypothesis 两条红在 E1（380；401「tested：委派分支为 True，属于 project_eqcr_user_ids(P) 为 False」） | 21 passed |

任务要求的两项都按预期红：M1 红在固定样例 ①，M2 红在固定样例 ⑦。M5、M7、M9 由显式样例 E1 / E2 确定性地打红（固定样例 ①~⑩ 不含未关联记录、空白变体与他人委派）；M8 由固定样例 ③ 确定性地打红。

写法按需求 12.13 自查：未用 monkeypatch 与 `dependency_overrides`；两条 hypothesis 测试都显式声明 `@settings(max_examples=5, deadline=None)`；唯一的 `pytest.raises` 块只有一条语句，其后断言异常信息；断言里没有「或」组合，也没有对多元素字面量的成员判断；没有 skip / xfail。

### 任务 2.8：EQCR 别名单一来源扫描测试（2026-10-20）

改动文件（实施 worktree）：只新增 `backend/tests/test_eqcr_alias_single_source.py`（LF）：blob `fbece0e64de9461a66b558dbd9269d6e18186ec8`，172 行（`len(text.split("\n"))` 口径；splitlines 171），最长行 107 字符。cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py backend/tests/test_eqcr_alias_single_source.py` 退出码 0；`python -m ruff check --no-cache` 通过。未改生产代码与其他测试。

扫描口径：

- 范围：`backend/app` 下全部 `.py`（`rglob` 递归）；`backend/tests` 整体不在范围（含 `role_map_expected.py`）。逐文件 `ast.parse(read_bytes())`；读不出 AST 的文件记入 `parse_errors`，不静默跳过，由「扫描器不空转」用例打红。
- EQCR 别名全集取 `tests/role_map_expected.EXPECTED_EQCR_ALIASES`（不从 `ROLE_MAP` 现推，理由写在测试文件注释）：判据不该随 `ROLE_MAP` 的取值浮动。若现推，任务 19.4 ⑥ 的第二项变异（`独立复核合伙人` 改为 (partner, edit)）会把全集缩成 {eqcr}，判据①随之把所有含 `"eqcr"` 的容器都算成违规（现算 37 个容器、28 个文件），红在与该变异无关的地方；「取值为 (partner, review) 的键恰是这两个」已由任务 2.2 的两处前提测试钉住。
- 判据①：`ast.Set` / `ast.List` / `ast.Tuple` 的元素、`ast.Dict` 的键中，`str` 常量集合包含别名全集的容器。
- 判据②：值恰等于 `独立复核合伙人` 的 `ast.Constant`，按直接父节点归类：Set / List / Tuple 的元素 → 集合元素；Dict 的键 → 映射键（Dict 的值不计）；`ast.Compare` 的操作数（左右两侧、全部比较运算）→ 比较操作数。另把 `match` 语句的值模式 `ast.MatchValue` 也计为比较操作数（与 `==` 同义）：任务原文只列 `ast.Compare`，这条是我补的口径；现状 `backend/app` 中 `match` 语句 0 个，不影响现算结果。其余位置（函数实参、f-string 片段、下标、`return`、赋值右值、docstring 所在的 `Expr`）不计；注释不进 AST。
- 位置：「相对 backend 的路径::外层类.函数.同一作用域内最近的赋值目标」，都没有时为 `<module>`；不用行号。
- 口径边界（需求 7.2 只数字面量）：先把别名赋给变量、再把变量放进集合的写法不计；下标取值（如 `ROLE_MAP["独立复核合伙人"]`）不计。

现算（worktree，2026-10-20）：

| 项 | 现算值 |
|---|---|
| 扫描文件数 | 2638，`parse_errors` 0 |
| 判据①命中 | 1 处：`app/services/assignment_service.py::ROLE_MAP`（映射） |
| 判据②命中 | 1 处：`app/services/assignment_service.py::ROLE_MAP`（映射键） |
| 独立复核：值等于 `独立复核合伙人` 的字符串常量（不经被测分类函数，列出全部位置） | 2 个：`ROLE_MAP` 的键；`AssignmentService._send_assignment_notifications.role_map` 的值（委派通知的显示名映射 `{"eqcr": "独立复核合伙人", …}`）。后者是显示名映射的值，判据②不计 |
| 含该字样为子串的字符串常量 | 4 个，都不计：`models/eqcr_models.py` 模块 docstring、`models/staff_models.py` 中 `AssignmentRole` 的 docstring、`services/sod_guard_service.py` 两处 `SodViolation` 文案（f-string 隐式拼接，`JoinedStr`）。另 `assignment_service.py` 中 `ROLE_MAP` 字面量内、`eqcr` 键上方的一行注释不进 AST |
| 字节中含 `独立复核合伙人`（UTF-8）的文件 | 4 个，与 `Select-String` 文本检索的 7 行、4 个文件对得上 |

结论：现状满足两条判据，没有违规；本测试钉住现状。

基线树对照（`D:\wt_pm_ref`，HEAD = B；只读读取，前后 `git status --porcelain=v1 -uall --ignored` 逐行相同）：扫描 2637 个文件，判据①②各多出一处 `app/services/role_context_service.py::_ASSIGNMENT_ROLE_MAP`（映射 / 映射键）。两条判据用例在基线上都红在「别名集合来源不唯一」并点名该位置；任务 2.3 删除该映射后，worktree 上转绿。

运行：cwd `D:\wt_pm_impl\backend`（`import app` → `D:\wt_pm_impl\backend\app\__init__.py`，`tests.role_map_expected` → worktree 同名文件），`D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_eqcr_alias_single_source.py -v -p no:cacheprovider --tb=short -rf` → **3 passed**（9.39 s，含 1 条第三方 schemathesis 导入期 DeprecationWarning；扫描本身约 7 s，模块级夹具只扫一次）。

| 用例 | 断言 |
|---|---|
| `test_scanner_is_not_idle` | 期望表别名含 `独立复核合伙人`；文件数 > 0；`parse_errors` 为空；判据①在 `ROLE_MAP` 处恰 1 次（映射）；判据②在 `ROLE_MAP` 处恰 1 次（映射键） |
| `test_full_alias_set_literal_only_in_role_map` | 判据①命中位置列表 == [`ROLE_MAP`]；失败信息以「别名集合来源不唯一（判据①…）」开头，逐条列出其他位置 |
| `test_cn_alias_role_value_only_in_role_map` | 判据②命中位置列表 == [`ROLE_MAP`]；失败信息以「别名集合来源不唯一（判据②…）」开头，同上 |

灵敏度核对（仓库外一次性探针 + 临时目录 `D:\pm_tmp\t28_sens`，均已删；不写 worktree；直接调用测试模块的 `scan_eqcr_alias_sources` 与三个用例函数）：

| 合成树 | 内容 | 结果 |
|---|---|---|
| A | `ROLE_MAP` 与显示名映射；`services/eqcr_resolver.py` 写回 `_LOCAL_COPY = frozenset({"eqcr", "独立复核合伙人"})`（19.4 ⑥ 第一项变异的形态）；应报样本：集合、列表、元组、映射键、`frozenset([...])` 里的列表、`\u` 转义写法、隐式拼接 `"独立复核" "合伙人"`、只含中文别名的集合、`==` 右侧、`!=` 左侧、`in` 左侧、`match` 值模式、`role in (...)`、类属性、方法内局部变量；不该报样本：模块 / 类 / 函数 docstring、注释、显示名映射的值、`[{"value": "eqcr", "label": "独立复核合伙人"}]`、只含 `eqcr` 的集合、日志与异常实参、f-string 拼接、下标、条件表达式、赋值右值；另一个语法错误文件 | 判据① 12 处、判据② 17 处，与预先写出的期望逐条相等；不该报样本与显示名映射 0 处；语法错误文件进 `parse_errors`，不计入文件数（4）。三个用例：不空转红在「以下文件读不出 AST」；①②都红在「别名集合来源不唯一」，分别列出其他 11 / 16 处（含 `app/services/eqcr_resolver.py::_LOCAL_COPY`） |
| B | 只有 `ROLE_MAP`（含显示名映射）与不该报样本 | ①②各恰为 [`ROLE_MAP`]；三个用例通过 |
| C | 空目录 | 文件数 0；不空转红在「下没有扫到 .py 文件」 |
| D | `ROLE_MAP` 改名为 `ROLE_TABLE` | 不空转红在「判据①应在 ROLE_MAP 处恰命中 1 次」；①②列出 `ROLE_TABLE` |
| E | `ROLE_MAP` 中 `独立复核合伙人` 改为 (partner, edit)（19.4 ⑥ 第二项变异的形态） | 三个用例通过：扫描不读取值，⑥ 第二项应只红在需求 7.4 的用例上 |
| — | 别名集合传空 | 抛 `ValueError`「别名集合为空：判据①会把每个容器都算作命中」 |

写法按需求 12.13 自查：无 monkeypatch / `dependency_overrides`、无 `pytest.raises`、无子进程、无 hypothesis；断言没有「或」组合，也没有对多元素字面量的成员判断（唯一的成员判断对象是名字 `_EQCR_ALIASES`）；无 skip / xfail。

给任务 19.4 ⑥ 的说明：第一项变异应红的是 `test_full_alias_set_literal_only_in_role_map` 与 `test_cn_alias_role_value_only_in_role_map`，失败信息都以「别名集合来源不唯一」开头，并点名 `app/services/eqcr_resolver.py::<赋值目标或函数名>`；`test_scanner_is_not_idle` 应保持通过。第二项变异下本扫描保持通过（合成树 E 已验证）。

### 任务 2.4：角色上下文兜底的性质测试（2026-10-20）

改动文件（实施 worktree）：只改 `backend/tests/test_role_map_and_context.py`（同 spec 新建的文件，LF）：blob `a8ee7aa15d080f6ccc16c78b0dfcb6f002428e38`（= 任务 2.3 登记的改后值，本任务开始时 `git hash-object` 复核一致）→ `f64ff85ffcdf42a8df8cc8166fe631b065bfb358`，277 → 516 行（`len(text.split("\n"))` 口径；splitlines 515），sha256 `f37d73161ba2bb22605aec259f2518043722d385a22bc1e5047b5e4515da30ff`。改动三处：模块 docstring 的「三」节说明；导入块补 hypothesis、FastAPI / httpx、审计日志模型与路由、写入端哈希函数；文末追加第三节。cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py backend/tests/test_role_map_and_context.py` 退出码 0，`python -m ruff check --no-cache` 通过。生产代码未改：`role_context_service.py` 的 blob 仍为 `f8b761c76c70ea3c904ed2b9d4e6b61ff572e29e`，sha256 仍为 `0c3935baf1925c455de50e9d6d3398079a4143fb6d831678164c63cc5a4f6258`（与任务 2.3 登记值相同）。

新增用例（第三节，真实 SQLite 内存库 + 真实 `RoleContextService`，不替换任何判定）：

| 用例 | 数据与断言 |
|---|---|
| `test_property_1_fallback_matches_role_map`（Property 1，hypothesis） | `@settings(max_examples=5, deadline=None)`。生成：委派角色取 `ROLE_MAP` 13 个键、键的大小写变体（upper / capitalize / swapcase / title）、首尾空白变体（空格、两个空格、`\t`、`\n`、`\u3000`，加在首 / 尾 / 两端）、`st.text(min_size=0, max_size=30)`（排除 NUL 与代理码位：VARCHAR(30)，PG 不存 NUL）；全局角色取 `UserRole` 全部 7 个；该项目上可另有一条已删除成员行（项目角色与级别任取），「没有未删除成员行」仍成立。7 个 `@example`：空串、`Manager`、首尾带空格的 `manager`、`readonly`、`观察员`、`signing_partner`（以上六个为全局 auditor、无已删除成员行），以及 `项目经理` + 全局 admin + 一条已删除的 (qc, review) 成员行。每个样例经 `asyncio.run` 建独立的 SQLite 内存库：一个未删除项目、一名用户、一条人员库记录、一条角色为 r 的现行委派 |
| `test_property_1_every_role_map_key[<键>]` × 13 | `ROLE_MAP` 每个键（参数化，含需求 2.8 的 `signing_partner`），期望 = 该键的取值。中文键的测试标识被 pytest 转义（如 `[\u5408\u4f19\u4eba]`） |
| `test_property_1_unregistered_fixed_examples[empty / Manager / spaced-manager / readonly / observer-cn]` × 5 | 先断言该串不是 `ROLE_MAP` 的键，期望写死为 (readonly, readonly)（需求 2.2、2.3） |
| `test_fallback_finds_delegation_on_second_staff_record`（N3） | 第一条人员库记录（先插入，id 为 `UUID(int=1)`）只在另一项目 Q 有 `qc` 委派，第二条（id 为 `UUID(int=2)`）在 P 有 `manager` 委派（范围 [E]）：单项目查询逐值等于 `{source: project_assignments, role: manager, permission_level: edit, scope_cycles: [E]}`；全局上下文 P 为 [(manager, edit)]、Q 为 [(qc, review)]，`project_count` 为 2 |
| `test_requirement_2_8_fallbacks_and_effective_role` | 需求 2.8 的用户（全局 auditor、只参与 P、在 P 没有成员行、一条 `signing_partner` 现行委派，范围 [D, E]）：单项目查询逐值等于 `{source: project_assignments, role: partner, permission_level: edit, scope_cycles: [D, E]}`；全局 `projects` 逐值等于 P 的一条 (partner, edit)；`(system_role, effective_role, project_count)` = (auditor, partner, 1) |
| `test_requirement_2_8_audit_chain_verification_allowed`（端点级） | 同一用户；P 上按写入端算法写 2 条哈希链条目：`GET /api/audit-logs/verify-chain?project_id=P` → 200，响应逐值等于 `{"valid": true, "entries_checked": 2}`。对照：同一项目上只持有 `观察员` 委派的另一名全局 auditor → 403，`detail.error_code` 为 `FORBIDDEN_AUDIT_CHAIN`，`detail.message` 为「当前用户无权查询该项目的审计哈希链」 |

Property 1 的三个用例共用断言函数 `_assert_fallbacks_equal`：单项目查询的 `source` 为 `project_assignments`（确认走的是委派兜底）；单项目与全局条目的（项目角色，项目级别）类型都是 `str` 且等于期望（`ProjectUserRole` / `PermissionLevel` 是 str 子类枚举，与其取值相等，只比相等测不出需求 2.3 的「以字符串取值返回」）；全局上下文中该项目恰一条；`project_count` 为 1。模型 `_model_pair(r)` 取 `ROLE_MAP.get(r, READONLY)` 的 `.value`：以生产 `ROLE_MAP` 为对拍对象属需求 12.6 明文例外（`ROLE_MAP` 由任务 2.2 的期望表钉住）；默认值用测试文件里的字面量 `READONLY`，不读 `UNMAPPED_ROLE`，它若被改坏，固定样例仍按需求 2.2 打红。

需求 2.8「哈希链校验放行」的实现方式：端点级。新建 `FastAPI()`，以 `prefix="/api"`（与 `router_registry/system.py` 相同）挂真实的 `app.routers.audit_logs.router`，经 httpx `AsyncClient(transport=ASGITransport(app))` 真发请求。它与 TestClient 一样走完整的 ASGI 路由、依赖注入与参数校验；不用 TestClient 是因为它在另一线程的事件循环里跑应用，用不了夹具里的 SQLite 异步会话，而 `ASGITransport` 在测试自己的事件循环内执行。只 override `get_current_user`（返回库中的 `User` 行）与 `get_db`（测试会话），属需求 12.1 的可替换点；判定由真实的 `verify_chain` → `RoleContextService.get_project_role` → `_ALLOWED_PROJECT_ROLES` 作出。哈希用写入端 `audit_log_writer_worker._compute_entry_hash` 计算（与校验端 `audit_logs._compute_entry_hash` 是两份实现），由端点逐条重算。未用 `app.main.app`：只需这一个路由，也不触发 lifespan。本文件不是附注门禁的端点级测试文件，校验端点没有可打桩的业务 service；「放行」以 200 与 `entries_checked` 为 2（两条链条目都被逐条校验）判定。

运行（cwd `D:\wt_pm_impl\backend`；`import app` 解析到 worktree）：

| 运行 | 结果 |
|---|---|
| ① `D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_role_map_and_context.py -q -p no:cacheprovider --tb=short -rf` | **57 passed**（2.82 s）：原 35 例 + 本任务 22 例 |
| ② 同上加 `-v --hypothesis-show-statistics -k "property_1 or second_staff_record or requirement_2_8"` | 22 passed；`test_property_1_fallback_matches_role_map` 为「5 passing examples, 0 failing examples, 0 invalid examples」「Stopped because settings.max_examples=5」。统计只列生成阶段；7 个显式样例在显式阶段执行，见下方 M1：显式样例失败时报「Falsifying explicit example」与「4 other explicit examples also failed」 |
| ③ `tests/test_audit_log_enhanced.py tests/test_role_map_and_context.py tests/test_eqcr_resolver_property.py tests/test_eqcr_resolver_smoke.py` 同批（`-rfExX`） | 104 passed，7 xpassed（38.45 s）；7 个 XPASS 即 `test_audit_log_enhanced.py` 中理由已过时的 xfail（见文末登记），与任务 2.3 的记录相同 |

灵敏度核对（不是需求 12.5 的磁盘变异证明，后者由各自任务登记在「变异证明」一节）：仓库外一次性 pytest 插件（`-p` 加载，`PYTHONPATH` 指向 `D:\pm_tmp`）在 `pytest_configure` 中把 `app.services.role_context_service` 换成内存里的变异源码。替换前断言该模块尚未被导入；收集完成后核对测试模块拿到的 `RoleContextService` 就是替换后的类，四次都为 True。子进程另设 `HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外。不写 worktree 文件：前后 `role_context_service.py` 的 sha256 都是 `0c3935baf1925c455de50e9d6d3398079a4143fb6d831678164c63cc5a4f6258`，测试文件都是 `f37d73161ba2bb22605aec259f2518043722d385a22bc1e5047b5e4515da30ff`。每项跑整个文件（57 例），命令为 ① 加 `-p <插件>`：

| 变异 | 变红（行号与失败信息） | 其余 |
|---|---|---|
| M0 原样源码（对照） | 无 | 57 passed |
| M1 未登记的委派角色兜底改回 (auditor, edit)（任务要求） | 五个未登记固定样例 `empty` / `Manager` / `spaced-manager` / `readonly` / `observer-cn` 都红在第 367 行 `('auditor', 'edit') == ('readonly', 'readonly')`；hypothesis 测试红在显式样例 `role=''`（另有 4 个显式样例同样失败） | 51 passed：`ROLE_MAP` 13 键、N3、需求 2.8 两例不受影响 |
| M2 两处兜底都只看用户的第一条人员库记录（任务要求；N3 修复前的口径，查询加「人员库记录 id = 该用户首条未删除记录」的标量子查询） | N3 用例第 428 行：返回 `{source: system_role_fallback, role: auditor, permission_level: readonly, scope_cycles: None}`；另有第二节 3 例（第 252 / 267 / 277 行，同样依赖多条人员库记录） | 53 passed：Property 1 全部用例与需求 2.8 两例（都只有一条人员库记录）不受影响 |
| M_old 整个模块换成改动前的原文（基线树 B，只读读取） | 键 `signing_partner` 第 367 行 `('auditor', 'edit') == ('partner', 'edit')`；`partner`、`合伙人` 为 `('partner', 'review') == ('partner', 'edit')`；`manager`、`项目经理` 为 `('manager', 'review') == ('manager', 'edit')`；未登记样例 `empty` / `Manager` / `spaced-manager` 为 `('auditor', 'edit') == ('readonly', 'readonly')`；hypothesis 测试红在显式样例 `role=''`；N3 第 428 行（system_role_fallback）；需求 2.8 服务层第 492 行（`role` 为 `auditor`）；需求 2.8 端点级第 507 行 `assert 403 == 200`，响应为 `FORBIDDEN_AUDIT_CHAIN`「当前用户无权查询该项目的审计哈希链」；另有第二节 3 例 | 42 passed：其余 8 个键，`readonly`、`观察员` 两个未登记样例（旧映射本来就把它们登记为 (readonly, readonly)）等 |

每项都红在对应断言上（`AssertionError`），没有收集、导入或夹具错误。任务要求的两项按预期红：M1 红在五个未登记固定样例，M2 红在 N3 用例。M_old 另证明需求 2.8 两例在改动前的代码上都红，端点级用例红在 403，即需求 2.8 所述现状「哈希链校验拒绝」。

写法按需求 12.13 自查：`dependency_overrides` 只替换 `get_current_user` 与 `get_db`（需求 12.1 的可替换点）；未用 monkeypatch；hypothesis 测试显式 `@settings(max_examples=5, deadline=None)`；没有 `pytest.raises`、子进程、skip / xfail；断言里没有「或」组合，也没有对多元素字面量的成员判断。

登记（不在本任务范围，未改）：`tests/test_audit_log_enhanced.py` 的 7 个 verify-chain 用例仍标非严格 `xfail`，理由「verify-chain endpoint not registered in router_registry, returns 404」已过时（端点已在 `router_registry/system.py` 注册），运行 ③ 中仍是 7 个 XPASS。

### 任务 2.5：委派角色映射单一来源扫描测试（2026-10-20）

改动文件（实施 worktree）：只新增 `backend/tests/test_role_map_single_source.py`（LF）：blob `43d6ecdc04d63bde359d039b19b6c826d5b97bad`，434 行（`len(text.split("\n"))` 口径；splitlines 433），最长行 120 字符。cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py backend/tests/test_role_map_single_source.py` 退出码 0；`python -m ruff check --no-cache` 通过。未改生产代码与其他测试。

扫描口径（测试文件 docstring 有全文）：

- 后端范围：`backend/app` 下全部 `.py`（`rglob`），逐文件 `ast.parse(read_bytes())`，读不出 AST 记入 `parse_errors`；`backend/tests` 整体不在范围（含 `role_map_expected.py`）。级别回填迁移的 SQL 不在 AST 范围，由需求 12.7 的对账测试钉住。
- 前端范围：`audit-platform/frontend/src` 下 `.ts .tsx .mts .cts .js .jsx .mjs .cjs .vue`，排除 `__tests__` 目录、文件名含 `.spec.` / `.test.` 的文件、vitest setupFiles 目录 `src/test/`。最后一项是我补的口径（任务原文只列前三项）：`src/test/setup.ts` 是 `vitest.config.ts` 的 `setupFiles`，属测试基座；现算把它纳入时候选 0、命中 0（两棵树相同），不影响结果。`.vue` 只扫 `<script>` / `<script setup>` 块，模板不在范围。
- 前端解析：node 子进程（v24.14.0）执行嵌在测试文件里的脚本（运行时写到系统临时目录，仓库外），加载前端依赖里的 `typescript`（5.6.3，`createSourceFile`）与 `@vue/compiler-sfc`（3.5.32，`parse(..., { ignoreEmpty: false })` 取脚本块）。依赖目录可传参，基线树对照时指向 worktree 的 `node_modules`。输出是纯 ASCII 的 JSON（非 ASCII 字符转义成 `\uXXXX`）；读取端按 UTF-8 解码，断言退出码 0、输出非空、无替换字符，再解析 JSON。
- 没扫到的判定（记入 `problems`，由不空转用例打红）：读不出或不是 UTF-8（`TextDecoder` fatal）；`.vue` 行首 `<script` 标签数多于取出的脚本块数。TS 语法诊断与 SFC 解析告警只登记：TS 解析器带错误恢复，这些文件照样产出语法树并被扫描。
- 映射字面量：Python 的 `ast.Dict`、`dict(k=v, ...)`、`dict([(k, v), ...])`；前端的对象字面量、`new Map([[k, v], ...])`、`Object.fromEntries([[k, v], ...])`。
- 键：字符串常量（前端另含标识符键与 `['…']` 计算键；`dict()` 取关键字参数名），按字符串精确比对四个别名集合。集合取 `tests/role_map_expected.EXPECTED_ROLE_MAP` 中取值不是 (readonly, readonly) 的键，现为 13 个，即需求术语表的四个集合。以枚举成员为键的不计；委派角色只作记录里的字段取值（如 `[{value: 'manager', level: 'edit'}]`）的也不计。记录式写法现算两棵树后端、前端都是 0 处（仓库外探针：同一字典 / 对象字面量里既有别名取值、又有级别取值）。
- 取值给出项目级别：取值本身是级别（字符串 `edit` / `review` / `readonly`；`PermissionLevel.<级别>`，可带 `.value`；`PermissionLevel("…")` / `PermissionLevel["…"]`），或取值是元组 / 列表 / 集合 / 字典 / 对象字面量、其直接元素（字典取直接的值）里有级别。两端的取值规整成同一结构后，由同一个 Python 函数 `_gives_level` 判定。
- 计数：一个映射字面量里「键属别名集合、取值给出级别」的不同键有 2 个及以上，计一份。
- 不计：中文显示名、只给项目角色、数字、操作权限集合（级别字样嵌在更深一层，或包在 `Set(...)` / `frozenset(...)` 里）；注释、docstring、字符串；先把级别赋给变量再引用的写法（只数字面量，同任务 2.8）。
- 位置：「相对路径::类.函数.赋值目标」，后端相对 `backend/`、前端相对 `audit-platform/`（形如 `frontend/src/...`）；前端的匿名函数越过 `computed(() => …)` 这类调用，取所赋给的变量名。不用行号。

现算（2026-10-20；直接调用测试模块的 `scan_backend` / `scan_frontend` 与两个用例函数，前端解析器都取 worktree 的 `node_modules`）：

| 项 | 基线树 B（`D:\wt_pm_ref`） | worktree |
|---|---|---|
| 后端扫描文件 / `parse_errors` | 2637 / 0 | 2638 / 0 |
| 后端命中 | 2：`app/services/assignment_service.py::ROLE_MAP`（13 键）、`app/services/role_context_service.py::_ASSIGNMENT_ROLE_MAP`（12 键：缺 `signing_partner`；另两个键 `readonly`、`观察员` 不属别名集合） | 1：`ROLE_MAP`（13 键） |
| 前端列出 / 读到 / 脚本块 / `problems` | 5307 / 5307 / 5319 / 0 | 同左 |
| 前端候选（≥2 个别名键，不论取值）/ 命中 | 39 / 0 | 39 / 0 |
| 份数 | **2** | **1** |
| `test_scanner_is_not_idle` | 通过 | 通过 |
| `test_role_map_is_the_only_role_level_mapping` | 红在「映射不唯一：…现算 2 份（ROLE_MAP 处 1 份），其他位置 1 处：- app/services/role_context_service.py::_ASSIGNMENT_ROLE_MAP（键 assistant、auditor、eqcr、manager、partner、qc、助理、合伙人、审计员、独立复核合伙人、质控、项目经理）…」 | 通过 |

基线树只读：本任务只读取文件，没有在基线树里导入 Python 或运行 pytest；事后 `git status --porcelain=v1 -uall --ignored` 为 1730 行，全是被忽略的 `.pyc`（与任务 2.2 的记录相同），HEAD 仍为 B。

未计的候选（逐个判读，确认没有误计也没有漏计）：

- 后端另有 20 个以 ≥2 个别名为键的映射（仓库外探针现算，两棵树相同），都不给项目级别：中文显示名（`review_dialog._ROLE_MAP`、委派通知的 `role_map`、`role_capability_contract` 的显示名表）；角色名（`permissions/permission_matrix.py` 的角色归一、`cost_overview_service` 的中文别名 → 角色、`role_context_service` 的另一个角色名映射）；数字（`_ROLE_PRIORITY`、`wp_cell_lock_service` 的 `role_hierarchy`、`DEFAULT_HOURLY_RATES`、`ROLE_MAX_COMPLEXITY`）；脱敏级别 `McpMaskLevel.*`（`mcp_token`）；操作 / 权限 / 能力 / 字段 / 组件清单（`permission_matrix_service` 两个、`permission_service`、`project_permissions` 两个、`custom_template_ingestion/authorization`、`export_mask_service`、`role_workbench_facade`、`role_capability_contract` 的能力表）。
- 前端 39 个候选也都不给项目级别：以显示名为主；`delegationSeniority.ts::ROLE_SENIORITY`（13 个别名键，取值是资历数字）、`ProcedureTrimming.vue::ROLE_PRIORITY` 与 `BatchAssignDialog.vue` 的排序表（数字）；`usePermissionMatrix.ts::SYSTEM_ROLE_TO_MATRIX_ROLE`、`viewPresetConfig.ts::ROLE_DEFAULT_MAP`（角色名）；`permissions/permission-matrix.ts::PERMISSION_TABLE`（`edit` / `review` 是各资源 `new Set([...])` 里的操作名，不是项目级别）与 `usePermission` / `usePermissionMatrix` 的操作集合。
- 现状违规：无。前端没有 `ROLE_MAP` 的抄录，也没有「委派角色 → 级别」映射。

灵敏度核对（仓库外一次性探针 + 临时目录 `D:\pm_tmp\t25_syn`，均已删；不写 worktree；直接调用测试模块的扫描函数与两个用例函数）：

| 合成树 | 内容 | 结果 |
|---|---|---|
| 后端 | worktree 的 `assignment_service.py` 原样；worktree 的 `role_context_service.py` 末尾写回基线树原样的 `_ASSIGNMENT_ROLE_MAP`（19.4 ⑤ 的形态）。应报：`dict(manager="edit", partner="edit")`、`dict([(…), (…)])`、`PermissionLevel.edit.value` 与 `PermissionLevel("review")`、`PermissionLevel["edit"]`、`{"role": …, "level": "edit"}` 作取值、类方法内的局部映射（取值为 `("auditor", "edit")`）。不该报：docstring、注释、字符串里的映射文本，显示名映射 `{"eqcr": "独立复核合伙人", "manager": "项目经理"}`，只给项目角色（枚举与字符串两种），数字，嵌套更深的 `{"workpaper": ["edit"]}`，`frozenset({"edit"})`，只有 1 个级别条目，枚举成员作键，非别名键 `readonly` / `观察员`，经变量引用的级别 | 命中 8 处，与预先写出的期望逐个相等：`ROLE_MAP`、`app/services/role_context_service.py::_ASSIGNMENT_ROLE_MAP` 与 6 个应报样本（含 `C.f.m`）；不该报样本 0 处 |
| 前端 | 应报：`.ts` 的 `{ manager: 'edit', partner: 'edit' }`、`.vue` `<script setup>` 里的 `{ 'signing_partner': 'edit', manager: 'edit' }`、`.js` 的 `export default`（元组取值）、`new Map`、`Object.fromEntries`、`as const` 的记录取值、`['manager']` 计算键加 `satisfies`、`computed(() => ({ 助理: 'edit', 审计员: 'edit' }))`、语法错误文件里的映射。不该报：`.vue` 模板绑定里的映射、`//` 与 `/* */` 注释、字符串与模板字符串、显示名映射 `{ eqcr: '独立复核合伙人', manager: '项目经理' }`、只给角色、数字、`new Set(['edit'])`、嵌套更深、只有 1 个级别条目、`[Role.MANAGER]` 计算键。排除：`__tests__/`、`*.spec.ts`、`*.test.ts`、`test/setup.ts`、`*.pbt.spec.ts`（内容都是应报写法）。另有一个只含空 `<script setup>` 的 `.vue` | 命中 9 处，与期望逐个相等（位置如 `frontend/src/hits/d.ts::useX.inner`）；列出 7 个文件且全部读到，排除的 5 个不在其中；`problems` 为空（空脚本块不误报）；语法错误文件只多 1 条诊断，映射照样命中 |
| 两棵合起来跑用例 | — | `test_scanner_is_not_idle` 通过；主用例红在「映射不唯一：…现算 17 份（ROLE_MAP 处 1 份），其他位置 16 处」，第一条即 `app/services/role_context_service.py::_ASSIGNMENT_ROLE_MAP` |
| 反向 | 前端放一个非 UTF-8 文件；后端放一个语法错误文件 | 非 UTF-8 文件记入 `problems`；不空转用例分别红在「以下文件读不出 AST」「以下前端文件没有扫全」；前端漏读时主用例红在「前端源码没有扫全，不能判定映射唯一」，不放行 |

开发中修过一处扫描器误报：首次运行时不空转用例红在 `components/qc/QcClientTrendEmbed.vue`、`views/NotFound.vue`「有 1 个 <script> 块，只取出 0 个」。这两个文件的 `<script setup lang="ts">` 是空块，`@vue/compiler-sfc` 默认 `ignoreEmpty: true` 会丢掉它们；改为 `ignoreEmpty: false` 后都能取出（脚本块 5317 → 5319），命中结果不变。

运行：cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_role_map_single_source.py tests/test_eqcr_alias_single_source.py -v -p no:cacheprovider --tb=short -rf` → **5 passed**（25.41 s）。本文件 2 例，单独运行 17.15 s（2 passed），其中前端子进程约 7 s。

| 用例 | 断言 |
|---|---|
| `test_scanner_is_not_idle` | 别名集合不少于 2 个；后端文件数 > 0、`parse_errors` 为空、`ROLE_MAP` 处恰命中 1 次；前端文件数 > 0、`problems` 为空、读到数 = 列出数、候选 > 0 |
| `test_role_map_is_the_only_role_level_mapping` | 前端 `problems` 为空（否则不能判定）；后端与前端的命中位置列表 == [`app/services/assignment_service.py::ROLE_MAP`]；失败信息以「映射不唯一：」开头，写明现算份数，逐条列出其他位置及其键 |

写法按需求 12.13 自查：无 monkeypatch / `dependency_overrides`、无 `pytest.raises`、无 hypothesis；子进程同时断言了退出码与输出内容（非空、无替换字符，解析出的内容再由用例断言）；断言没有「或」组合，也没有对多元素字面量的成员判断；无 skip / xfail。

给任务 19.4 ⑤ 的说明：在 `role_context_service.py` 写回一份等价映射后，应红的是 `test_role_map_is_the_only_role_level_mapping`，失败信息以「映射不唯一：」开头并点名 `app/services/role_context_service.py::<赋值目标>`；`test_scanner_is_not_idle` 保持通过（合成树与基线树都已验证）。

登记（不在本任务范围，未改）：

- 运行环境：本测试需要 `node` 与 `audit-platform/frontend/node_modules` 里的 `typescript`、`@vue/compiler-sfc`。缺任一项时夹具内的断言失败（「前端扫描跑不起来：…先在 audit-platform/frontend 跑 npm ci」），两个用例都报 ERROR，不 skip（需求 12.13）。CI 的 `backend-tests` job（`.github/workflows/ci.yml`）不装前端依赖，本测试在该 job 上会 ERROR，`-x` 会在此中断；任务 15.2 的前端扫描同样依赖 node 与 `typescript`。是否给该 job 补 `setup-node` 与 `npm ci`，由编排者决定。
- 前端预存问题（B 中已入库，两棵树相同）：`components/workpaper/composables/g7VoucherSample.ts` 的 `mergeVoucherSamples` 末尾多一个 `}`，TS 报「Declaration or statement expected.」；该文件被 `g7-shared/G7VoucherSampleSection.vue` 导入，在生产路径上。`components/consolidation/ConsolNoteMappingDialog.vue` 的模板有 2 条属性名告警，脚本块照常取出。本扫描照样扫到这两个文件。

### 任务 2.9：职责分离与兼任校验不变量（2026-10-20）

被测对象（基线 B 现读；`backend/app/services/sod_guard_service.py` 两棵树 blob 相同 `f77189f3e`，`trace_event_service.py`、`models/workpaper_models.py`、`models/staff_models.py`、`models/core.py`、`models/base.py`、`models/phase14_models.py`、`models/phase14_enums.py`、`tests/conftest.py` 两棵树 blob 也逐个相同）：

| 对象 | 签名 | 是否读库 | 判定依据 |
|---|---|---|---|
| `SoDGuardService.check` | `(db, project_id, wp_id, actor_id, target_role) -> SoDCheckResult(allowed, conflict_type, policy_code, trace_id)` | 读 `working_paper` 一行；写一条 `trace_events`（底稿不存在时不写） | 用 `hasattr(wp, "preparer_id" / "reviewer_id" / "partner_reviewed_by")` 收集操作人已有角色，按（已有角色，目标角色）查 `CONFLICT_MATRIX` / `POLICY_CODES`；不读成员行，也不读委派 |
| `EqcrIndependenceRule.check` | `(db, project_id, staff_id, new_role, *, proposed_roles=None) -> None`，冲突抛 `SodViolation`（`message`、`policy_code`；委派保存端点取这两项作 409） | 单条模式读 `project_assignments`（同项目、同人员库记录、未删除、角色不等于本次角色）；批量模式不读库 | 本次角色既不是 `eqcr`、也不在 `CONFLICT_ROLES` 里时直接返回 |
| `validate_eqcr_sod_in_batch` | `(assignments: list[dict]) -> None`，冲突抛 `SodViolation` | 纯函数，没有 db 参数 | 函数内局部的 `CONFLICT_ROLES \| {"qc"}`；生产代码没有调用方（只有 `tests/test_eqcr_sod.py` 调用） |

「成员行无关」的构造：三者都不读 `project_users`。测试在 SQLite 内存库里给被判定的人在项目 P 造一条成员行（或不造），再对比结论：职责分离判定是操作人；兼任校验是人员库记录 S 关联到的用户（另一条人员库记录 T 不关联用户）。底稿职位用真实列表达：编制人 = `working_paper.assigned_to`（同时写 `wp_index.assigned_to`），复核人 = `working_paper.reviewer`（同时写 `wp_index.reviewer`），合伙人审批人 = `working_paper.partner_reviewed_by`。

基线实测探针（`D:\pm_tmp\t29_probe.py`，仓库外，用完已删）：cwd = `D:\wt_pm_ref\backend`，子进程设 `PYTHONDONTWRITEBYTECODE=1` 并加 `-B`，`HYPOTHESIS_STORAGE_DIRECTORY` 指向 `D:\pm_tmp\`；导入 `tests.conftest` 取得与测试相同的环境；`app` 解析到 `D:\wt_pm_ref\backend\app\__init__.py`。每条样例在 20 种成员行状态下各测一次：无成员行，`ProjectUserRole` 6 个取值 × `PermissionLevel` 3 个取值，外加一条已删除的 (partner, edit)。运行前后 `git -C D:\wt_pm_ref status --porcelain --ignored --untracked-files=all` 都是 1730 行且逐行相同，HEAD 仍为 B。

探针输出摘要：

- `hasattr(WorkingPaper(), …)`：`preparer_id` 为假，`reviewer_id` 为假，`partner_reviewed_by` 为真。编制人、复核人实际存在 `assigned_to`、`reviewer` 列。
- 104 条样例 × 20 种成员行状态：每条样例在 20 种状态下结论相同（随成员行变化的样例 0 条）；拒绝 25 条，放行 79 条，其他异常 0 条。
- 常量：`CONFLICT_MATRIX`、`POLICY_CODES` 各 6 个键，键类型为 `SoDRole`；`CONFLICT_ROLES = frozenset({"signing_partner", "manager", "auditor"})`；`POLICY_CODE = "SOD_EQCR_INDEPENDENCE_CONFLICT"`。
- 按行为逐个角色测出的冲突角色集合。角色全集 22 个：需求 2.5 期望表的 13 个键，加 `EQCR`、`Eqcr`、` eqcr`、`Manager`、` manager`、`QC`、`观察员`、`readonly`、`preparer`。批内预检为 {auditor, manager, qc, signing_partner}；批量模式与单条模式各两个方向都是 {auditor, manager, signing_partner}。
- 同一探针在 worktree（cwd = `D:\wt_pm_impl\backend`）上运行，输出除文件路径外与基线逐键相同。
- 逐样例实测结论（样例编号同测试参数化标识；`cn_eqcr` / `cn_partner` / `cn_manager` / `cn_auditor` / `cn_assistant` / `cn_qc` 分别指 `独立复核合伙人` / `合伙人` / `项目经理` / `审计员` / `助理` / `质控`）：
  - 职责分离判定 `SoDGuardService.check`：21 条，拒绝 2、放行 19。
    - 拒绝 `sod-key-partner_approver-preparer`：「同人编制+终审同一底稿」，`SOD_PREPARER_APPROVER_CONFLICT`
    - 拒绝 `sod-all3-preparer`：「同人编制+终审同一底稿」，`SOD_PREPARER_APPROVER_CONFLICT`
    - 放行（是否允许为是，冲突描述与策略码为空）：`sod-key-preparer-partner_approver`、`sod-key-preparer-reviewer`、`sod-key-reviewer-preparer`、`sod-key-qc_reviewer-preparer`、`sod-key-preparer-qc_reviewer`、`sod-all3-partner_approver`、`sod-all3-reviewer`、`sod-all3-qc_reviewer`、`sod-preparer+reviewer-partner_approver`、`sod-partner_approver-reviewer`、`sod-partner_approver-partner_approver`、`sod-partner_approver-qc_reviewer`、`sod-reviewer-partner_approver`、`sod-reviewer-reviewer`、`sod-preparer-preparer`、`sod-unrelated-reviewer`、`sod-partner_approver-unknown-eqcr`、`sod-partner_approver-case-Preparer`、`sod-wp-missing-preparer`
  - 兼任校验单条模式（读库）：31 条，拒绝 6、放行 25。
    - 拒绝 `single-eqcr-after-signing_partner`：「同项目内该人员已是 signing_partner 角色，不能再担任 EQCR（独立复核合伙人）」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `single-signing_partner-after-eqcr`：「同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 signing_partner」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `single-eqcr-after-manager`：「同项目内该人员已是 manager 角色，不能再担任 EQCR（独立复核合伙人）」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `single-manager-after-eqcr`：「同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 manager」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `single-eqcr-after-auditor`：「同项目内该人员已是 auditor 角色，不能再担任 EQCR（独立复核合伙人）」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `single-auditor-after-eqcr`：「同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 auditor」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 放行（是否允许为是，冲突描述与策略码为空）：`single-eqcr-after-qc`、`single-qc-after-eqcr`、`single-cn_eqcr-after-manager`、`single-manager-after-cn_eqcr`、`single-cn_eqcr-after-eqcr`、`single-eqcr-after-cn_eqcr`、`single-partner-after-eqcr`、`single-eqcr-after-partner`、`single-cn_partner-after-eqcr`、`single-eqcr-after-cn_partner`、`single-cn_manager-after-eqcr`、`single-eqcr-after-cn_manager`、`single-cn_auditor-after-eqcr`、`single-eqcr-after-cn_auditor`、`single-assistant-after-eqcr`、`single-eqcr-after-assistant`、`single-cn_assistant-after-eqcr`、`single-eqcr-after-cn_assistant`、`single-cn_qc-after-eqcr`、`single-eqcr-after-cn_qc`、`single-eqcr-no-assignment`、`single-eqcr-after-deleted-manager`、`single-eqcr-after-manager-on-other-project`、`single-manager-after-deleted-eqcr`、`single-eqcr-after-eqcr`
  - 兼任校验批量模式（`proposed_roles`）：30 条，拒绝 7、放行 23。
    - 拒绝 `batch-eqcr-with-signing_partner`：「同项目内该人员已是 signing_partner 角色，不能再担任 EQCR（独立复核合伙人）」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `batch-signing_partner-with-eqcr`：「同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 signing_partner」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `batch-eqcr-with-manager`：「同项目内该人员已是 manager 角色，不能再担任 EQCR（独立复核合伙人）」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `batch-manager-with-eqcr`：「同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 manager」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `batch-eqcr-with-auditor`：「同项目内该人员已是 auditor 角色，不能再担任 EQCR（独立复核合伙人）」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `batch-auditor-with-eqcr`：「同项目内该人员已是 EQCR（独立复核合伙人），不能再担任 auditor」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `batch-eqcr-first-conflict-wins`：「同项目内该人员已是 auditor 角色，不能再担任 EQCR（独立复核合伙人）」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 放行（是否允许为是，冲突描述与策略码为空）：`batch-eqcr-with-qc`、`batch-qc-with-eqcr`、`batch-cn_eqcr-with-manager`、`batch-manager-with-cn_eqcr`、`batch-eqcr-other-staff-manager`、`batch-eqcr-ignores-db-manager`、`batch-manager-ignores-db-eqcr`、`batch-cn_eqcr-with-eqcr`、`batch-eqcr-with-cn_eqcr`、`batch-partner-with-eqcr`、`batch-eqcr-with-partner`、`batch-cn_partner-with-eqcr`、`batch-eqcr-with-cn_partner`、`batch-cn_manager-with-eqcr`、`batch-eqcr-with-cn_manager`、`batch-cn_auditor-with-eqcr`、`batch-eqcr-with-cn_auditor`、`batch-assistant-with-eqcr`、`batch-eqcr-with-assistant`、`batch-cn_assistant-with-eqcr`、`batch-eqcr-with-cn_assistant`、`batch-cn_qc-with-eqcr`、`batch-eqcr-with-cn_qc`
  - 批内预检 `validate_eqcr_sod_in_batch`：22 条，拒绝 10、放行 12。
    - 拒绝 `pre-eqcr-signing_partner`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['signing_partner'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-signing_partner-eqcr`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['signing_partner'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-eqcr-manager`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['manager'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-manager-eqcr`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['manager'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-eqcr-auditor`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['auditor'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-auditor-eqcr`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['auditor'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-eqcr-qc`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['qc'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-qc-eqcr`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['qc'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-eqcr-manager-auditor`：「人员 11111111-1111-4111-8111-111111111111 在同批次中同时持有 eqcr 与 ['auditor', 'manager'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 拒绝 `pre-first-staff-wins`：「人员 22222222-2222-4222-8222-222222222222 在同批次中同时持有 eqcr 与 ['auditor'] 角色，违反独立性」，`SOD_EQCR_INDEPENDENCE_CONFLICT`
    - 放行（是否允许为是，冲突描述与策略码为空）：`pre-empty`、`pre-cn_eqcr-manager`、`pre-eqcr-other-staff-manager`、`pre-skip-missing-fields`、`pre-eqcr-cn_eqcr`、`pre-eqcr-partner`、`pre-eqcr-cn_partner`、`pre-eqcr-cn_manager`、`pre-eqcr-cn_auditor`、`pre-eqcr-assistant`、`pre-eqcr-cn_assistant`、`pre-eqcr-cn_qc`

测试文件 `backend/tests/test_sod_unchanged.py`（新增，LF，470 行，blob `ce6aa7060`）。样例表 104 条：职责分离判定 21、单条模式 31、批量模式 30、批内预检 22，期望逐条字面写入上面的基线实测值。用例（共 109 个）：

| 用例 | 断言 |
|---|---|
| `test_fixed_table_without_member_row[<样例编号>]`（104 个） | 无成员行时（是否允许，冲突描述 / 消息，策略码）== 样例表 |
| `test_property_11_sod_conclusion_independent_of_member_row` | Property 11：`@settings(max_examples=5, deadline=None)`；成员行取「无」或（任意项目角色，任意级别，是否已删除）；随机抽样只从收 db 参数的 82 条样例里取（批内预检是纯函数）；显式样例为样例表全部 104 条，各配一条成员行（项目角色 × 级别 18 种轮换，外加一条已删除行）；结论 == 样例表 |
| `test_conflict_matrix_and_policy_codes_unchanged` | 互斥矩阵与策略码逐键逐值等于基线实测（键取枚举值比较，并断言取值后键不重复） |
| `test_eqcr_conflict_roles_unchanged` | `CONFLICT_ROLES` 是 `frozenset` 且等于 {signing_partner, manager, auditor}；`POLICY_CODE` 不变 |
| `test_conflict_role_sets_unchanged` | 在 22 个角色上逐个测：批内预检冲突角色集合 == {signing_partner, manager, auditor, qc}；兼任校验批量、单条模式两个方向 == {signing_partner, manager, auditor} |
| `test_fixed_table_covers_mandated_samples` | 样例编号不重复且共 104 条，收 db 参数的 82 条；需求 9.5 点名的样例都在表中 |

运行：

- worktree：cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_sod_unchanged.py -q -p no:cacheprovider --tb=short -rf --hypothesis-show-statistics` → 109 passed（10.01s）；Property 11 生成阶段 5 passing / 0 failing / 0 invalid。
- 基线树：测试文件复制到仓库外 `D:\pm_tmp\t29_base\`（sha256 与 worktree 相同），cwd `D:\wt_pm_ref\backend`，`python -B -m pytest D:\pm_tmp\t29_base\test_sod_unchanged.py -p tests.conftest -p no:cacheprovider -c D:\wt_pm_ref\backend\pytest.ini --rootdir D:\pm_tmp\t29_base -q --tb=short -rf --hypothesis-show-statistics`，子进程设 `PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY=D:\pm_tmp\t29_hyp` → 109 passed（9.45s），生成阶段 5 passing。同 cwd 与环境下 `app`、`sod_guard_service`、`tests.conftest` 都解析到 `D:\wt_pm_ref\backend`（`PYTHONPATH` 未设置）。运行后基线树状态与运行前逐行相同（1730 行，含忽略文件），HEAD = B。

进程内敏感性核验（不属于 design §8.5 的磁盘变异）：用仓库外的 pytest 插件，在测试进程内改测试与生产代码共同持有的对象（类属性、字典本体、类上的方法），不改任何文件；worktree 上逐项运行全文件：

| 变异 | 结果 |
|---|---|
| M1：`CONFLICT_ROLES` 加入 `qc` | 7 failed：`test_eqcr_conflict_roles_unchanged`、`test_conflict_role_sets_unchanged`、`[single-eqcr-after-qc]`、`[single-qc-after-eqcr]`、`[batch-eqcr-with-qc]`、`[batch-qc-with-eqcr]`、Property 11 |
| M2：职责分离判定改为看成员行（操作人在 P 有 edit 级成员行且目标为 reviewer 即判冲突） | 1 failed：只有 Property 11 红（固定样例表无成员行，104 条全绿），反例为 `sod-reviewer-reviewer` + 成员行 (readonly, edit) |
| M3：`CONFLICT_ROLES` 去掉 `auditor` | 12 failed：两条常量 / 集合用例、9 条样例（含 4 条批内预检：`pre-eqcr-auditor`、`pre-auditor-eqcr`、`pre-eqcr-manager-auditor`、`pre-first-staff-wins`）、Property 11 |
| M4：互斥矩阵 (partner_approver, preparer) 的冲突描述末尾加「（改）」（原地改字典） | 4 failed：`test_conflict_matrix_and_policy_codes_unchanged`、`[sod-key-partner_approver-preparer]`、`[sod-all3-preparer]`、Property 11 |

登记（基线现状，按需求 9.5 保持，本任务未改；是否另立 spec 由编排者决定）：

- 职责分离判定按 `preparer_id`、`reviewer_id` 取编制人、复核人，而 `WorkingPaper` 没有这两个属性，互斥矩阵 6 个键中只有 (partner_approver, preparer) 能命中。连带后果：提交复核端点（`wp_review_router`，`target_role="reviewer"`）上的职责分离校验对真实数据恒放行；`POST /api/sod/check` 只在操作人是底稿的 `partner_reviewed_by`、目标角色为 `preparer` 时拒绝。
- 留痕 `trace_events.action` 写成 `sod_check:SoDRole.partner_approver->preparer`：f-string 取到的是枚举的 `str()`，不是枚举值。
- `validate_eqcr_sod_in_batch` 在生产代码中没有调用方；委派保存走 `EqcrIndependenceRule` 批量模式，因此 `eqcr` 与 `qc` 同批照常保存。
- 运行环境：本测试只用 SQLite 与后端依赖，不需要 node，CI 的 `backend-tests` job 可直接运行。

### 任务 3.1：权限世界夹具（2026-10-20）

改动文件（实施 worktree，均为新增，LF，无 CRLF，U+FFFD 0）：

- `backend/tests/authz_world.py`：夹具模块（文件名不匹配 `test_*.py`，不被收集），blob `d035b28bf37f38fbd1ae0ea84c26ae2be8b044b0`，755 行（`len(text.split("\n"))` 口径）。
- `backend/tests/test_authz_world.py`：夹具自测，blob `30d954d5d42ef75e1eba52ae65f460fd0827925f`，480 行。
- cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py <两个文件>` 退出码 0；`python -m ruff check --no-cache` 两个文件通过。`authz_world.py` 距 800 行上限余 45 行，后续任务登记新门禁时注意。

写夹具前的现读（worktree，B + 任务 2.x 改动）：

- `assert_project_permission`：先 `_check_project_not_archived`（`min_permission == "readonly"` 直接返回；否则 `db.get(Project)`，`status == ProjectStatus.archived` 抛 423，detail 为 `{error_code: PROJECT_ARCHIVED, message: 项目已归档，无法编辑, message_en: Project archived (read-only)}`）→ admin 跳过成员判定 → 读权限缓存（现状恒未命中，N1）→ 查 `project_users` 未删除行 → 级别不足 403「权限不足」。归档守卫、RLS 设置、缓存读写都经 `app.deps` 的模块全局名调用。
- RLS：实际被调用的是 `app.deps.set_rls_context`（`from app.core.database import get_db, set_rls_context` 导入的名字，`assert_project_permission` 内 3 处）；定义在 `app.core.database`，SQLite 方言下自身直接返回。另有 `ownership_guard` 与两个 `_f2_stocktake_*_sync` 路由各自导入（不在权限世界的请求路径上）。
- 委派查询：`is_project_eqcr` 经模块全局名调用 `_count_project_eqcr_assignments`。合并锁：`projects.consol_lock`（Boolean，server_default false）。
- 权限缓存的存储：`app.core.redis.redis_client` 在导入时按 `settings.REDIS_URL` 以 `decode_responses=True` 建成，测试进程里连真实本机 Redis；`_redis_client`（`get_redis()` 用）首次调用时同样建出。`tests/conftest.py` 只导入 `fakeredis.aioredis`，没有替换它们。因此改动前的代码在测试里会把 `perm:*` 写进共享 Redis（TTL 300 秒）；读路径对 `str` 调 `.decode()` 抛错后返回 None，与 N1 一致。
- 生产注册：`router_registry` 的注册函数只调用 `app.include_router`（注册完整性校验另读 `app.routes`），注册时可能附加依赖（如 `dedicated_wp_gate`）。
- `test_v197_route_migration_pg.py` 不在 B，只在主工作树本地分支；PG 临时 schema 写法按主工作树该文件现读。
- 主工作树根 `.env` 没有 `DATABASE_URL` 键（只有 `PG_*` 等）。后端连接串取 `app.core.config.Settings.DATABASE_URL`（默认值 + 进程环境），`DB_DISABLE_SSL` 默认 True。PG 轮的子进程 env 由仓库外一次性启动器从该 settings 取值传入，不打印（落盘输出里替换为占位）。
- 一次性探针（仓库外，已删）：FastAPI 0.135.3 的 `HTTPBearer` 缺凭据返回 401 `{"detail": "Not authenticated"}`；Python 3.12.8 的 `sys.monitoring` 对协程代码对象的 `PY_START` 在协程开始执行时触发；fakeredis 2.35.1 每个 `FakeServer` 互相隔离，`decode_responses=True` 时取回 `str`。

夹具能力（`tests/authz_world.py`）：

| 名称 | 用途 |
|---|---|
| `sqlite_world(monkeypatch)` | 异步上下文管理器：SQLite 内存库（`StaticPool`）建六张表，产出 `AuthzWorld`。用法：测试文件里写 3 行 `pytest_asyncio.fixture` 包一层 |
| `pg_world(monkeypatch)` / `pg_engine()` | PG 同构版：同一事务内 `CREATE SCHEMA authz_world_<随机>`、`SET LOCAL search_path` 只含它、同一建表函数；会话 `join_transaction_mode="create_savepoint"`（端点里的 `commit` 只释放保存点）；结束整体回滚。连接串只取进程环境变量 `DATABASE_URL`，不是 PG 即抛错；SSL 参数与 `app.core.database` 同口径 |
| `create_world_schema(conn)` | 两种方言共用：PG 先按 ORM 声明的取值建 8 个枚举类型；逐表 `CreateTable`，只保留指向六张表的外键（现算保留 19 个、滤掉 3 个：`projects.accounting_standard_id`、`disclosure_notes.bound_dataset_id`、`disclosure_notes.last_sync_wp_id`）；SQLite 上把 `postgresql_where` 索引按同样的列与条件重建为部分索引（现算 10 个索引：部分唯一 3 个 `idx_project_users_project_user` / `idx_assignment_project_staff` / `uq_disclosure_notes_active`，部分非唯一 5 个，普通 2 个） |
| `TARGET_PROJECT_ID` / `OTHER_PROJECT_ID` / `TARGET_NOTE_ID` | 固定 id：目标项目（建世界时建好，执行中、未合并锁定、未删除）、身份④有权的另一项目、目标项目上的附注。五种身份各在独立的世界里也能发同一路径的同一请求 |
| `world.member(level, role, *, project, user, global_role)` | 在目标项目（默认）建一条未删除成员行；省略 `user` 时新建全局角色为 `global_role`（默认 auditor）的用户 |
| `world.eqcr_assignment(alias="eqcr", *, user, project)` | 给用户建一条人员库记录 + 目标项目上一条该角色的现行委派 |
| `world.non_member_with_other_project()` | 身份④：目标项目无成员行，另一项目一条（manager, edit） |
| `world.edit_member()` … `world.admin_non_member()`、`world.identity(key)` | 八种身份各一个方法，键见 `IDENTITY_LABELS`（`STANDARD_IDENTITIES` ①~⑤、`SUPPLEMENTARY_IDENTITIES` ⑥~⑧），返回 `Identity`（真实 `User` 行、目标项目、成员行、委派、另一项目及其成员行）。⑥ 把目标项目置为已归档 |
| `world.user()`、`world.project()`、`world.other_project()`、`world.add_note()` | 基本工厂 |
| `world.client(*routers, user, replace_rls=True)` | 按生产注册只挂这些 router（`build_app`），override `get_current_user`（`user=None` 为未登录，真实 `get_current_user` 判定）与 `get_db`，默认置空 RLS；httpx `AsyncClient(transport=ASGITransport)` 真发请求，产出 `GateClient` |
| `world.client_for_app(api, *, user)` | 同上，但用给定应用（只供反向对照等非生产端点） |
| `build_app(*routers)` / `production_registrations()` | 用记录器跑一遍生产 `register_all_routers`，得到每次 `include_router` 的参数（前缀、注册时附加的依赖、标签），按原参数挂；未注册的 router 抛 `LookupError` |
| `world.stub(owner, attr, returns, *, awaitable=True)` → `ServiceStub` | 业务 service 计数桩（`count`、`calls`）；门禁、`_GUARDED_MODULES`（`app.deps`、`app.services.eqcr_resolver`、`app.core.database`、`app.core.redis`）里的对象、值为门禁的属性、可替换点名一律拒绝打桩 |
| `world.replace_rls()` / `replace_archive_guard()` / `replace_eqcr_query(count)` / `assert_not_replaced(*points)` | 可替换点；每次替换记入 `world.replaced`，观测该判定的用例用 `assert_not_replaced` 自证；`world.rls_calls` 记录 RLS 设置时传入的项目 id |
| `world.redis` | 本世界独占的 fakeredis（权限缓存的存储替身） |
| `PRODUCTION_GATES` / `PRODUCTION_GATE_OBJECTS` / `TRACED_GATES` / `assert_gates_are_production()` / `assert_world_overrides(app)` / `GateTrace` / `GateClient.assert_passed(gate, times)` | 「门禁 is 生产对象」自检，口径见下 |

可替换点的实现（需求 12.1 第一项，且只有这些）：当前用户 = `dependency_overrides[get_current_user]` 返回世界里的真实 `User` 行（override 函数不带参数）；数据库会话 = `dependency_overrides[get_db]` 产出世界的会话（只提供数据）；权限缓存的存储 = 建世界时 monkeypatch `app.core.redis.redis_client` 与 `_redis_client` 为独立 `FakeServer` 的 fakeredis（`decode_responses=True`，初始为空 ⇒ 不预置缓存条目），缓存读写函数不替换、本夹具也不引用它们的名字（任务 3.4 移除缓存后无需改夹具）；RLS = monkeypatch `app.deps.set_rls_context` 与 `app.core.database.set_rls_context` 为只记录项目 id 的空操作；归档守卫 = `app.deps._check_project_not_archived`；委派查询 = `app.services.eqcr_resolver._count_project_eqcr_assignments`；业务 service = `stub`。门禁本身没有任何替换入口。

「请求经过的门禁 is 生产对象」自检的口径（四层）：

1. 快照：导入夹具时取 `PRODUCTION_GATES`（`app.deps.require_project_access`、`app.deps.assert_project_permission`、`app.services.eqcr_resolver.is_project_eqcr`、`app.routers.deliverable._guard_action`）的模块属性，逐个核对是函数、`__module__` / `__qualname__` 与登记名相同、源文件就是该模块文件且在被测 `app` 包内，不成立即导入失败（导入前就被换掉的情形）。
2. `assert_gates_are_production()`：每个请求前、每次直接判定前核对模块属性仍 `is` 快照（导入后被 monkeypatch 换掉的情形，包括透传包装）。
3. `assert_world_overrides(app)`：每个请求前核对 `dependency_overrides` 只含 `get_current_user` 与 `get_db`，多出的逐个列出并标明是否门禁或门禁工厂产出的闭包。
4. `GateTrace`：每个请求都在其中发出，用 `sys.monitoring`（PEP 669，工具号优先 4 / 3 / 2）只观测快照函数及工厂内 `dependency` 闭包的代码对象开始执行的次数，不替换、不包装任何对象；`GateClient.gate_runs` 记录上一个请求的次数，`assert_passed` 断言生产门禁的代码确实执行过（及次数）。观测名单 `TRACED_GATES` 现为 5 个（4 个门禁 + `require_project_access.<locals>.dependency`）。新增门禁形态（如附注编辑门禁）时在 `PRODUCTION_GATES` 登记、所在模块加进 `_GUARDED_MODULES`，工厂型门禁的 `dependency` 闭包自动纳入观测。

自测（`tests/test_authz_world.py`，期望按需求原文写死，不由被测函数推出）：

| 组 | 用例 | 断言 |
|---|---|---|
| 世界本身 | `test_identity_registry_matches_requirements`；`test_world_has_exactly_the_six_tables`；`test_partial_unique_indexes_follow_pg_semantics[project_users / project_assignments / disclosure_notes]`；`test_cache_storage_is_this_worlds_empty_fakeredis` | 八个身份方法齐全；`sqlite_master` 恰为六张表，目标项目（execution, 未锁, 未删）；两条已删除 + 一条现行同键可建、第二条现行行报 `UNIQUE constraint failed: <表>.<列>`；`redis_client`、`get_redis()` 都是本世界的 fakeredis，初始 0 键，取回 `str` |
| 身份数据 | `test_identity_data_matches_requirement_definition[8 个身份]` | 读库核对全局角色、目标项目与另一项目上的成员行（逐值）、全世界 EQCR 别名现行委派条数（别名取 `tests/role_map_expected.py`，只有 ⑤ 为 1）、目标项目状态（只有 ⑥ 为 archived）；真实 `is_project_eqcr` 只对 ⑤ 为是；fakeredis 仍为 0 键 |
| 真实门禁判定 | `test_identity_verdicts_from_real_gate[<身份>-<级别>]`，8 × 3 = 24 例，每例独立世界 | edit 级：① ⑧ 放行，② ③ ④ ⑤ ⑦ 403「权限不足」，⑥ 423；review 级：① ② ⑤ ⑦ ⑧ 放行，③ ④ 403，⑥ 423；readonly 级：除 ④ 403 外全部放行（⑥ 只读不判归档）。放行时返回同一 `User` 对象；拒绝比对状态码与 detail 全文。归档守卫、委派查询、RLS 都未替换（`assert_not_replaced`） |
| HTTP 真发请求 | 生产注册的 `POST /api/projects/{project_id}/cross-check/rules/custom`（路由级 `require_project_access("readonly")` + 端点级 `("edit")`，`CrossCheckService.add_custom_rule` 打桩）：`test_http_edit_member_is_allowed_through_production_gates`、`test_http_review_member_is_denied_before_business`、`test_http_archived_project_is_423`、`test_http_admin_non_member_is_allowed`、`test_http_anonymous_request_is_401_and_never_reaches_the_gate` | ① 200 + 桩恰 1 次（参数为目标项目 id 与请求体）+ 生产 `assert_project_permission` 与 `dependency` 闭包各执行 2 次 + override 恰为 {`get_current_user`, `get_db`} + RLS 记录两次目标项目；② 403 `{"detail": "权限不足"}`、桩 0 次、门禁执行 2 次；⑥ 423 + 归档 detail、桩 0 次、归档守卫未替换；⑧ 200、桩 1 次；未登录 401 `{"detail": "Not authenticated"}`、桩 0 次、门禁 0 次。选这个端点是因为本 spec 不改它的门禁级别 |
| 自检 | `test_gate_snapshot_is_the_production_code_of_this_tree`；`test_gate_check_names_a_lookalike`；`test_trace_flags_a_request_that_skips_the_gate`；`test_build_app_mounts_the_production_registration`；`test_build_app_refuses_an_unregistered_router`；`test_stub_refuses_gates_and_replaceable_points[5 例]` | 快照即本树 `app` 包内的生产函数，`app` 包与测试同一棵树；注入同名替身（只换查找函数，不动模块属性）自检指名失败；不经门禁的探针端点 200 但观测次数全 0、`assert_passed` 指名失败；`build_app` 挂出的路径集合与生产一致（cross-check 4 条）、未注册 router 抛错；对门禁、归档守卫、委派查询、路由模块导入的门禁工厂打桩被拒且原属性不变 |
| PG 同构 | `test_pg_world_is_isomorphic_and_leaves_no_objects`（`pg_only`） | `current_schemas(false)` 恰为临时 schema；其中恰为六张表；五种标准身份同一世界上 3 个级别的结论与 SQLite 版逐个相同；只有 ⑤ 是 EQCR；成员行部分唯一索引 PG 原生带删除条件（第二条现行行报 `duplicate key … "idx_project_users_project_user"`，在 SAVEPOINT 内）；附注可建；HTTP ① 200 + 桩 1 次、② 403 + 桩 0 次；⑥ 423；`public.projects` 无目标项目 id；退出后该 schema 不存在 |

写法按需求 12.13 自查：测试文件里没有 `monkeypatch` 与 `dependency_overrides` 赋值（替换只发生在夹具的允许点）；每个 `pytest.raises` 块一条语句、其后断言异常信息；断言没有「或」组合，也没有对多元素字面量的成员判断；不用 hypothesis；没有 skip / xfail，只有 `pg_only`。夹具与自测文件全文不出现权限缓存三个读写函数名与 TTL 常量名。

测试命令与结果（cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest <files> -q -p no:cacheprovider --tb=short -rfs`；`import app` 解析到 `D:\wt_pm_impl\backend\app\__init__.py`）：

| 运行 | 结果 |
|---|---|
| ① `tests/test_authz_world.py`（无 `DATABASE_URL`；中间版本，与终版只差 `assert_passed` 对未登记门禁名的判断与模块 docstring 一句） | 53 passed，1 skipped（`pg_only`：requires PostgreSQL），12.77 s |
| ② 终版：① + `test_role_map_and_context.py`、`test_eqcr_resolver_property.py`、`test_eqcr_resolver_smoke.py` 同一进程（与 hypothesis 用例共存、`sys.monitoring` 工具号不冲突） | 138 passed，1 skipped（同上），15.22 s |
| ③ PG 实跑（中间版本）：子进程 env 传 `DATABASE_URL`，`-k pg_world` | 1 passed，53 deselected，8.12 s |
| ④ PG 实跑：同上，整文件 | 54 passed，0 skipped，9.09 s（终版文件） |
| ⑤ 真库只读核对（postgres MCP，③④ 之后） | `pg_namespace` 中 `authz_world_%` 0 个；`public.projects` 中两个固定 id 0 行；`public.users` 中 `@authz-world.test` 0 行 |

PG 版已实跑（③④）；任务 19.9 的 PG 轮按同一方式（子进程 env 传 `DATABASE_URL`）即可执行，本用例跳过数应为 0。

夹具灵敏度核对（不是需求 12.5 所列的磁盘变异证明，不改任何文件）：仓库外一次性 pytest 插件在测试进程内存里施加变异，逐项跑整个自测文件（SQLite，终版文件）。

| 变异 | 结果 | 失败形态 |
|---|---|---|
| M0 无变异（对照） | 54 项：0 failed，1 skipped | — |
| M1 `deps.assert_project_permission` 换成透传包装（仍调用原函数） | 31 failed | 24 条判定、5 条 HTTP、门禁观测反向对照红在「请求经过的门禁不是生产对象（需求 12.1）：app.deps.assert_project_permission 已被替换为 …wrapper」；快照用例红在 `fn is getattr(module, attr)` |
| M3 换成恒放行替身，并关掉夹具内 `GateClient` 用的属性自检（只剩执行观测） | 29 failed | 24 条判定红在测试模块自己持有的属性自检；HTTP 放行两条（①⑧）红在「上一个请求执行生产门禁 app.deps.assert_project_permission 0 次，期望 2 次」，拒绝两条（②⑥）红在状态码（得到 200 与桩的返回体）；快照用例红在 `is`；未登录用例不观测门禁、保持通过 |
| M4 给路由级门禁闭包加一条 `dependency_overrides` | 5 failed | 5 条 HTTP 红在「dependency_overrides 只允许 get_current_user 与 get_db（需求 12.1），多出：app.deps.require_project_access.<locals>.dependency（门禁）」 |

给后续任务的说明：

- 端点级测试文件里定义 `world` 夹具（`async with sqlite_world(monkeypatch) as w: yield w`），用 `world.identity(key)` 建身份、`world.stub(...)` 打桩、`world.client(router, user=identity.user)` 发请求，`client.assert_passed(...)` 证明请求经过生产门禁；不观测归档 / EQCR 的用例才调 `replace_archive_guard` / `replace_eqcr_query`。
- 夹具用 httpx `AsyncClient(transport=ASGITransport(app))` 真发请求，不用 `TestClient`：`TestClient` 在另一线程跑事件循环，用不了夹具的异步 SQLite / PG 会话（与 `test_role_map_and_context.py` 同口径）。两者都走完整的 ASGI 与依赖解析。design §8.1 与需求 12.1 写的是「TestClient 真发请求」，此处按编排口径登记差异。
- 应用是只挂指定 router 的裸 FastAPI（与既有端点级测试同口径）：2xx 响应不经 `ResponseWrapperMiddleware` 包成 `{code, message, data}`，错误响应为 `{"detail": …}`。
- 运行环境：只需 SQLite 与后端依赖，不需要 node；`pg_only` 用例在没有指向 PostgreSQL 的 `DATABASE_URL` 时按 conftest 规则跳过。

### 任务 3.2：借缓存注入级别的 4 个测试文件改用真成员行（2026-10-20）

改动文件（实施 worktree，均保持 CRLF，改后每个文件 CRLF 数 = LF 数；四个文件都不在 `file_size_whitelist.txt`，按默认上限 800）：

| 文件 | blob 改前 → 改后 | 行数（`split("\n")` 口径）改前 → 改后 | 用例数 改前 → 改后 |
|---|---|---|---|
| `backend/tests/test_phase8_endpoint_role_levels.py` | `cf014632d36e81dbd3429bb29552dbe801ef47c8`（任务 2.2 后）→ `27ed793daa014605a024fd0534a4b26fd44b0284` | 193 → 272 | 23 → 99 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `353182a2b6dd1671110199fa0b5d8414872daccc`（任务 2.2 后）→ `12c418af6660df12e4048e1eee0d1ad3d0d7d3c3` | 430 → 500 | 120 → 140（其中 1 个 `pg_only`） |
| `backend/tests/ledger_import/test_sign_convention_api.py` | `54ccee580a918f6accfc0d6d2524c006da6ee86e`（= B）→ `836b70a943f0a895e8c90ba8533bfce74e731e08` | 283 → 243 | 8 → 8 |
| `backend/tests/test_wp_disclosure_sync.py` | `b7c74677a699d0272120049c5d7b66f7131a8a04`（= B）→ `72f5e538b50bb7a2086b0b1b99eba491fc0eba8d` | 553 → 545 | 22 → 22 |

改前用例数取基线树 `--collect-only`（173 项；任务 2.2 只改名两处前提测试，项数不变）；改后 269 项。每个原用例的去向见「既有测试改写对照」中任务 3.2 各行。

身份怎么给（四个文件都不再引用 `_get_cached_permission` / `_set_cached_permission` / `invalidate_permission_cache` / `PERM_CACHE_TTL`）：

- 成员：`map_assignment_role(委派角色)`（= `ROLE_MAP.get(角色, UNMAPPED_ROLE)`）的取值经 `world.member(level, role)` 写成目标项目上的真实成员行。phase8 与交付件两个文件另以 `world.eqcr_assignment(委派角色, user=…)` 给同一用户建人员库记录与同角色的现行委派（该方法按任意委派角色建）。未登记角色取 `观察员` → (readonly, readonly)。非成员用身份④ `world.non_member()`（目标项目无成员行、另一项目上 (manager, edit)），admin 用身份⑧ `world.admin_non_member()`。
- 选哪些别名：phase8 按需求 9.4 逐别名——别名取自期望表 `EXPECTED_ROLE_MAP`（不读生产代码），edit 级 9 个（合伙人 / 经理 / 审计员别名）、review 级 4 个（质控 / EQCR 别名）各测六个端点；交付件文件按成员行取值各取一个别名：`qc`（qc, review）、`partner`（partner, edit）、`manager`（manager, edit）、`auditor`（auditor, edit），EQCR 用 `eqcr`。每个用例先断言成员行等于期望表取值。
- EQCR 由真实委派给出：`_guard_action` 调 `deliverable._is_project_eqcr` → `EqcrWorkbenchService._is_user_eqcr_on`，现读其查询为 `project_assignments` JOIN `staff_members`，条件为项目 = P、`role == 'eqcr'`、两表都未删除、`staff_members.user_id` = 用户。两张表都在权限世界的六张表内，不需补建；`world.eqcr_assignment("eqcr", user=…)` 建出的正是这两行。用例先断言 `is_project_eqcr` 为真，再断言生成 10 个入口全部 403、查看 12 个入口全部 200。`_is_project_eqcr`、`_guard_action` 都未替换。
- 替换范围：只有世界的可替换点——当前用户与数据库会话（`world.client` / `world.client_for_app` 的 override）、RLS（默认置空）、业务 service（`world.stub` 计数）。归档守卫、委派查询、门禁与权限缓存读写函数都未替换；权限缓存的存储是世界的 fakeredis。每个请求都由 `GateClient` 核对生产门禁的代码执行次数（如 phase8 放行用例 `assert_project_permission` 执行 2 次 = 路由级 readonly + 端点级 review）。
- 业务桩：phase8 10 个；交付件 27 个（打桩的业务对象与改写前相同：改写前多数是整类替换，现在替换方法，构造函数照常执行；含交付件能力门控 `_require_capability`，它判 doc_type 能否回填 / 刷新，不是权限判定，改写前同样打桩；`audit_logger.log_action` 与 `chain_orchestrator` 的方法桩打在类上，避免在单例实例上留下遮蔽类属性的实例属性）；wp_disclosure_sync 2 个（同步本身与同步后的 `run_validation_best_effort`。后者若真跑，SQLite 世界缺校验表会报错并 `db.rollback()`，把世界里只 flush、未提交的用户与成员行一起回滚）；sign_convention 0 个（三个端点是 stub，不调业务 service：放行用例断言 200 + 响应体 + 生产门禁执行 1 次）。
- 交付件文件补建三张表：端点另读 `word_export_task`（交付件归属与门控）、`chain_executions` 与 `financial_report`（版本对比）。测试里以 `CreateTable` 建，外键只留指向已建表的，PG 上先在临时 schema 内建枚举 `financial_report_type`；夹具 `authz_world.py` 未改。

发现与处置：

1. 🔴 `wp_procedures.router`（程序裁剪、标记程序完成）在生产注册时另挂底稿可见性门 `dedicated_wp_gate`（`router_registry/workpaper.py`，先于项目级门禁执行）。首轮按生产注册跑时，它在世界里查不到 `working_paper` 表、判 not_found，返回 404「资源不存在或不可访问」；拒绝路径还经独立会话（`app.core.database.async_session`）向配置的数据库（本地开发库）写 `wp_access_security_outbox`。那一次写入被外键拒绝（世界里的用户不在真库 `users` 表）。postgres MCP 只读复核：该表与本次路由、actor 相关的行为 0，近 3 小时新增 0。处置：phase8 的四个 router 按生产注册挂；`wp_procedures.router` 按自身声明挂，不带这道门（与改写前相同）。新增 `test_wp_procedures_registration_adds_only_the_visibility_gate`，钉住生产注册对它只多 `dependencies=[dedicated_wp_gate]`。⚠️ 两条推论都未实测：①生产上非成员 / readonly 成员访问这两个端点时，先由可见性门下结论（可能是 404，不是 403），需求 9.4 所说「403 权限不足」只对项目级门禁成立，留待 design 判读；②权限世界没有隔离 `app.core.database.async_session`，凡走到用独立会话写库的路径（如可见性门拒绝），端点级测试都会连开发库写。
2. 版本对比 `GET …/workflow/compare/{execution_id}` 的路径参数是 `str`，查询以字符串绑定 uuid 列。SQLite 上 SQLAlchemy 2.0.49 的 Uuid 绑定处理器报 `'str' object has no attribute 'hex'`（仓库外探针实测），这条查询只能在 PG 上真跑（需求 12.9）。因此 `test_compare_only_reads_this_projects_execution` 改在 `pg_world` 上运行并加 `pg_only`（需求 12.13 所列例外）；SQLite 默认运行中它显示为跳过。改写前它在假会话上只核对 SQL 文本，现在真库数据与 SQL 文本两种断言都有。
3. `deliverable_lineage._load_task_gate_fields` 的原生 SQL 以 `str(uuid)` 绑定，SQLite 上恒查不到（库里存 32 位十六进制）⇒ 终态检查在 SQLite 上恒为「非终态」。本文件不观测终态与能力门控，`_require_capability` 保持改写前的打桩。
4. `test_wp_disclosure_sync.py` 中未改的三条 admin 用例（`test_sync_happy_path_admin`、`test_sync_year_optional`、`test_sync_batch_happy_path`）运行时有 `coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` 的 RuntimeWarning（同步后的自动校验在 MagicMock 会话上运行）。基线树同文件实跑同样出现，且改写前的 `test_sync_with_edit_user_succeeds` 也有；不是本任务引入。

运行（cwd `D:\wt_pm_impl\backend`，当前代码，权限缓存尚未移除）：

| 运行 | 结果 |
|---|---|
| ① `D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_phase8_endpoint_role_levels.py tests/test_deliverable_generation_membership_auth.py tests/ledger_import/test_sign_convention_api.py tests/test_wp_disclosure_sync.py tests/test_authz_world.py -q -p no:cacheprovider --tb=line -rfs` | **321 passed，2 skipped**（54.64 s）；跳过的只有两个 `pg_only`（本任务的 compare 用例与 `test_authz_world.py` 的 PG 用例，原因 requires PostgreSQL） |
| ② PG 轮：仓库外一次性启动器读 `settings.DATABASE_URL`，只放进子进程 env（输出中替换为占位），同 ① 的交付件文件与 `test_authz_world.py`，`-m pg_only` | **2 passed**，192 deselected（9.36 s） |
| ③ governance 单独运行（`applicable-standards-runtime-guard` 的同一组文件）：cwd 仓库根 `python -m pytest backend/tests/test_wp_disclosure_sync.py backend/tests/test_wp_disclosure_sync_revive.py backend/tests/test_manual_override_hook.py -q -p no:cacheprovider` | **35 passed**；`app` 解析到 worktree，未用 node |
| ④ 基线树 `D:\wt_pm_ref\backend` 上同四个文件 `--collect-only`（`-B`，子进程 `PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY` 指向 `D:\pm_tmp`） | 173 项（23 / 120 / 8 / 22）；另实跑原版 `test_wp_disclosure_sync.py` 与 `test_sign_convention_api.py`：30 passed。前后基线树 `git status` 不变（1730 个 `.pyc` 修改时间都在 00:31~00:35，非本任务产生），HEAD 仍为 B |
| ⑤ 缓存函数名残留（四个文件，AST 名字 / 属性 / 字符串常量 + 原文） | 0 处 |
| ⑥ 写法自查（需求 12.13 口径，四个文件全文）：断言中对 ≥2 元素字面量的成员判断、「或」组合、`pytest.raises`；新增标记 | 均 0；新增标记只有 compare 用例的 `pg_only`；改写前的 `status_code in (401, 403)` 两处已改为逐值 `(401, {"detail": "Not authenticated"})` |
| ⑦ `python -m ruff check --no-cache`（四个文件） | 通过；`test_sign_convention_api.py` 改写前就有的 2 条 F401（`BatchConfirmRequest`、`DirectionOverrideRequest` 导入未用）随改写删去 |
| ⑧ 行数门：cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py <四个文件>` | 退出码 0 |

本任务没有做磁盘变异（本任务不要求；实施 worktree 有并行任务在跑测试，不改生产代码）。用例的灵敏度来自逐值断言、业务桩逐键计数与生产门禁执行次数。

### 任务 3.3：删除缓存前实测读路径（2026-10-20）

本任务不留文件改动：收紧版只在运行期间存在，运行后逐字节恢复；驱动脚本、探针与 Redis 快照工具都放在仓库外（`D:\pm_tmp\`），用完已删。

改动前代码核对（运行前、运行后各一次，`git hash-object --path`）：`backend/app/deps.py` = `1b8daed81029669fdf3f0534413ee39f74b3743e`、`backend/app/core/redis.py` = `9aa1239e511413a15f3f1deb358f365eab5fc3c5`，与 `git ls-tree a02a21419a7ffef349384a766798b7ac291fca05` 中的 blob 相同；HEAD = B。`tests/conftest.py` 只导入 `fakeredis.aioredis`，不替换 `app.core.redis.redis_client`；worktree 内没有 `.env`，进程环境没有 `REDIS_URL` / `REDIS_MODE` ⇒ 测试进程按默认值 `redis://localhost:6379/0`（无口令）、`REDIS_MODE=single` 连本机 Redis（服务端 7.4.8，redis-py 7.4.0，运行前 ping 通）。

收紧：只改第 1048 行，保持 CRLF；逐行比对确认只有这一行不同。

| 状态 | blob（`git hash-object --path`） | sha256（磁盘实际字节，CRLF） | 字节数 | 行尾 |
|---|---|---|---|---|
| 收紧前 | `70aad96f8722175a328d1daa75ac81e3bcec283f`（= B） | `fd4a3b03577e5e5c60ce825dd3fd1cfe78c149fcb2cc93549baf1e4ecc325225` | 40661 | CRLF 1116，LF 1116，无单独 CR |
| 收紧版（不提交） | `cf8a4b6a9cb5eea7016192b4774f3b7f4613c7e4` | `98f179fb46777c5120b4f44bb175232efeb09630da40b6cb5cd4bbf20084ba49` | 40643 | 同上 |
| 恢复后 | `70aad96f8722175a328d1daa75ac81e3bcec283f` | `fd4a3b03577e5e5c60ce825dd3fd1cfe78c149fcb2cc93549baf1e4ecc325225`（`certutil -hashfile` 复核相同） | 40661 | 同收紧前 |

改的一行：`assert result is None or result == "edit"` → `assert result == "edit"`。恢复后与收紧前逐字节相等；`git diff --stat -- backend/tests/test_phase8.py backend/app/deps.py` 为空；`git status --porcelain` 与本任务开始前完全相同（17 项，均为此前任务的改动）。

命令（cwd `D:\wt_pm_impl\backend`）：`D:\GT_plan\.venv\Scripts\python.exe -m pytest "tests/test_phase8.py::TestPermissionCache::test_set_and_get_cache" -q -p no:cacheprovider --tb=short -rf`。由仓库外一次性驱动脚本按这一 argv 起子进程执行，环境原样继承，stdout 与 stderr 的原始字节落盘到 `D:\pm_tmp\`；驱动在 finally 中先确认磁盘内容仍是收紧版，再写回原字节。

结果（13:00:48 开始，6.01 s，退出码 1）：**1 failed**，红在取回值断言：

```
tests\test_phase8.py:1048: in test_set_and_get_cache
    assert result == "edit"
E   AssertionError: assert None == 'edit'
FAILED tests/test_phase8.py::TestPermissionCache::test_set_and_get_cache - As...
1 failed, 1 warning in 1.71s
```

唯一的警告是 venv 内第三方包 schemathesis 的 `DeprecationWarning`，与本用例无关。

这次失败属于「客户端可用、读路径未命中」，不是「Redis 不可用」：运行前 db 0 的 `perm:*` 为 0 个，运行后恰 1 个 `perm:aac1b92f-c4f7-4a5d-9466-0a171a8baf22:21713520-e558-49ae-8bf8-8720062bb36b`，值 `edit`、TTL 300；按 PTTL 推算写入时刻约 13:00:54.1，落在本次运行末尾（会话 1.71 s，该用例在会话最后执行）；键里两个 id 在真库 `users`、`projects` 中都是 0 行（postgres MCP 只读查询）。也就是说本次运行的 `_set_cached_permission` 写入成功、Redis 里有值，`_get_cached_permission` 仍返回 None。Redis 不可用时写入会被吞掉，库里不会出现这个键。

探针（仓库外，cwd 同上，`app` 解析到 worktree 的 `backend/app`；不替换、不包装任何生产对象，只用 `sys.settrace` 观测 `_get_cached_permission` 帧内抛出的异常）：

| 项 | 结果 |
|---|---|
| 生产 `redis_client` | `redis://localhost:6379/0`，`decode_responses=True`，ping 为真 |
| 生产 `_set_cached_permission(u, p, "edit")` 后用 `redis_client` 原始 GET | `'edit'`，类型 `str`；TTL 300 |
| 生产 `_get_cached_permission(u, p)` | `None` |
| 该函数帧内的异常事件 | ① 第 521 行 `StopIteration('edit')`：`await redis_client.get(...)` 完成时的事件（Python 3.12 对 await 完成发出 STOP_ITERATION 监控事件，settrace 以 exception 事件报告；同一解释器上的最小复现：settrace 观测 `v = await inner()`，`inner` 返回 `'edit'` 时同样报 `StopIteration('edit')`，外层照常返回 `'edit'`），携带的值就是 GET 结果；之后执行到了第 522 行，没有进入 except；② 第 522 行 `AttributeError: 'str' object has no attribute 'decode'`，被 `except Exception: return None` 吞掉 |
| 对照：bytes 客户端（`decode_responses=False`）取同一键 | `b'edit'`，`.decode()` 得 `'edit'` |
| 探针自己的键 `perm:63ca38c1-0bbb-4a5a-8a30-23a761bb989b:76c80b37-5984-4ef3-8b5d-bcb15e929ecc` | 写入前不存在；探针结束前自行删除（DEL 返回 1），之后 EXISTS 为 0 |

根因：`redis_client` 以 `decode_responses=True` 创建，GET 取回 `str`；`_get_cached_permission` 按 bytes 写成 `cached.decode()`，对 `str` 抛 `AttributeError`，被 `except Exception` 吞掉后返回 None ⇒ 缓存里有值时读路径也恒按未命中处理（缓存里没有值时 `cached` 为 None，同样返回 None），每次判定都查库。

恢复后对照（同一命令跑原版文件）：**1 passed**（1.40 s）。这次运行同样写进一个键 `perm:9f58c7db-c0ee-4454-80f2-ad5b5d0ca9fa:98298fb7-8787-4d24-ba05-6c3cc34eb1c7`（值 `edit`、TTL 298，两个 id 真库 0 行）⇒ 缓存已写入、读路径未命中时，原断言「None 或 edit」照样通过，即需求 5.7 所说宽松断言掩盖的情形。这次运行也把 `tests/__pycache__/test_phase8.cpython-312-pytest-8.4.2.pyc` 重写为原版源文件的字节码（头部记录的源文件大小 40661、mtime 与恢复后的文件一致；`__pycache__/` 被 `.gitignore` 忽略）。

共享 Redis 测试键清理（db 0，只删本任务生成的键；先列出、核对值与 TTL，再按完整键名逐个删除）：

| 键 | 来源 | 删前 | DEL 返回 | 删后 EXISTS |
|---|---|---|---|---|
| `perm:aac1b92f-c4f7-4a5d-9466-0a171a8baf22:21713520-e558-49ae-8bf8-8720062bb36b` | 收紧版运行 | `edit`，TTL 183 | 1 | 0 |
| `perm:63ca38c1-0bbb-4a5a-8a30-23a761bb989b:76c80b37-5984-4ef3-8b5d-bcb15e929ecc` | 探针 | `edit`（探针内自删） | 1 | 0 |
| `perm:9f58c7db-c0ee-4454-80f2-ad5b5d0ca9fa:98298fb7-8787-4d24-ba05-6c3cc34eb1c7` | 恢复后对照运行 | `edit`，TTL 280 | 1 | 0 |

本任务共扫描 `perm:*` 6 次，出现过的只有上表收紧版与对照运行的两个键（探针的键在探针内写入并删除）；清理后再扫为 0 个。没有删除或改动其他键。

结论：需求 5.7 的推断属实，与 design N1 互证——Redis 可用、缓存条目确已写入，改动前的读路径仍返回 None；收紧后的用例红在取回值断言上（`assert None == 'edit'`）。按 design D3、§2.2（12.8 行），`TestPermissionCache` 三例在任务 3.4 随缓存删除，接替测试见任务 3.5。

### 任务 3.4：移除权限缓存（2026-10-20）

派发经过：本任务第三次派发开工时（17:30）发现实施 worktree 里已有本任务的改动——`backend/app/deps.py`、`backend/app/services/custom_query/ownership_guard.py` 与 12 个测试文件在 17:27:43–44 被前次派发的一次性脚本（`D:\pm_tmp\t34_edit_*.py`）写入；该派发的进程已不在运行，17:28 之后没有新产出。逐文件核对：这 14 个文件的改前 blob 都等于 B（`git rev-parse HEAD:<path>`），磁盘 blob 等于该脚本日志记录的改后 blob，worktree 里没有其他由它产生的改动。本次没有回退重做，而是逐段复核其 diff（下文逐段列出），确认与 design §4.4、§8.6 一致后沿用；另补改了它遗漏的 1 个测试（`test_d4_import_permission_gate.py`，见「非空替身改写」）。下文的检索、运行、行数门与 ruff 都是本次重做的结果。

生产改动要点（`backend/app/deps.py`，blob `1b8daed81029669fdf3f0534413ee39f74b3743e` → `f02846af04f3806096fe5f7d99a192299e609ecf`，728 → 662 行（`split("\n")` 口径），CRLF 661 = LF 661）：

- `require_project_access`：docstring 的「Redis 缓存权限查询结果（TTL=5min）」「Redis 不可用时降级为直接查库」两条改为「其余用户按本项目未删除成员行的级别判定（每次直接查库）」；工厂体内的注释「`PERM_CACHE_TTL` 使用模块级常量（见下方），此处不重复定义」删除。
- `require_wp_edit_permission`：现读 B，它的 docstring 本就不含缓存描述（只讲 `WORKPAPER_WRITE` 能力与成员 edit 权），无可删；缓存描述实际在 `authorize_wp_edit` 第④步的注释里（「复用权限缓存」），已改为「每次直接查库」。任务原文与 design §4.4 此处与现状不符，登记为现算差异。
- `assert_project_permission`：删去缓存命中分支（读缓存 → 比较 → 设 RLS → 返回）与写缓存两行，`select(ProjectUser)` 整行查询改为 `_load_member_level`。执行顺序：级别名校验 → 归档守卫（不变）→ admin 设 RLS 后返回（不变）→ `_load_member_level` → 无成员行 403「权限不足」→ 级别不足 403「权限不足」→ 设 RLS → 返回。
- `authorize_wp_edit` / `authorize_wp_read`：①`WORKPAPER_WRITE` 能力判定（只在 edit 版）、③查底稿所属项目（不存在 404「底稿不存在」）、② admin / partner 免查，三步逐字未动；④「读缓存 → 未命中再查整行 → 写缓存」并为一次 `_load_member_level`。拒绝文案「无底稿编辑权限」/「无底稿访问权限」、状态码与门槛（edit / readonly）原样。
- 原「Permission cache helpers」整段（B 第 508–548 行：`PERM_CACHE_TTL`、`_get_cached_permission`、`_set_cached_permission`、`invalidate_permission_cache`）删除，原位置新增 `_load_member_level(db, user_id, project_id)`：`select(ProjectUser.permission_level)` 加三个条件（`project_id`、`user_id`、`is_deleted == False`），`scalar_one_or_none()`，返回 `.value` 或 None，与 design §4.4 的代码逐行一致（另加一段 docstring）。
- 未动：顶部的 `from app.core.redis import get_redis` 在 B 里就没有被本模块使用（ruff F401 两棵树相同），与缓存无关，不在本任务范围。

`backend/app/services/custom_query/ownership_guard.py`（blob `4636a5b0e76cb0c3dc71c33bb2facbc7cee41947` → `d6672338a7cf2a50b6ff6326e6999388ee8ac014`，291 → 281 行，CRLF 280 = LF 280）：模块 docstring 删去「+ Redis 权限缓存（`deps._get_cached_permission`）」；删除 `from app.deps import _get_cached_permission`（本模块从此不再导入 `app.deps`）；`_can_access_project` 的 docstring「含 Redis 权限缓存快路径」改为「每次按 project_users 成员 ∪ project_assignments 有效分派直接查库」，删去缓存快路径（try / 命中即返回 True / except 吞掉，共 8 行）；admin / partner 直接放行与 `user_id` 为空返回 False 两步原样，随后直接走既有的 `_accessible_project_ids`。

行为不变的依据：

1. 改动前缓存读路径恒返回 None：任务 3.3 实测 Redis 可用、条目已写入时 `_get_cached_permission` 仍为 None（`str.decode` 抛 `AttributeError` 被吞）；客户端为 None、键不存在、Redis 报错三种情形代码上同样返回 None ⇒ 三个判定点的「缓存命中」分支与 OwnershipGuard 快路径在生产上从未执行，删除不改变任何结论。
2. 写缓存只写 Redis、异常全吞、不触达数据库会话 ⇒ 删除后只少了 `perm:*` 的 SETEX，接口上不可观测。
3. 未命中路径逐步对照：查询条件、`scalar_one_or_none()`（多行时同样抛 `MultipleResultsFound`；真库唯一部分索引保证至多一行）、无成员行 403、比较式 `PERMISSION_HIERARCHY.get(level, 0) < 门槛`、拒绝文案与状态码、RLS 只在放行时设置、返回值，全部相同；查库异常两版都不吞。唯一差异是只取 `permission_level` 一列（design §2.1 / §4.4 的有意改动）：B 版若同一会话早已加载该成员行对象，取回的是身份映射里的内存值；新版取本次查询返回的值。请求入口处会话是新的，这一差异只在同一会话内先改成员行、再判定时出现。
4. 运行佐证：实施树一轮加载仓库外探针插件（`-p t34b_level_probe`，透明包裹 `deps._load_member_level`：原样调用、原样返回或抛出，只记录异常返回），全批 773 次调用（414 个用例、30 个文件）返回值都是 None 或 `PERMISSION_HIERARCHY` 的键，0 次异常；下面「非空替身改写」那一处就是它在改写前抓到的。

测试改动 · 删空替身的 11 个文件（全仓现算：B 中引用四个名字的文件共 18 个 = `deps.py`、`ownership_guard.py`、下表 11 个、任务 3.2 的 4 个、`test_phase8.py`；下表 11 个逐个判读都是「返回未命中 / 无操作」的空替身，B 上缓存读路径本就恒未命中，替身不改变行为）。11 个文件的用例函数与断言逐字未动，只改夹具 / `with` 语句 / 导入 / docstring；均保持 CRLF（改后 CRLF 数 = LF 数）。

| 文件（`backend/tests/`） | 删除（B 行号） | 连带改动 | 行数 B → 改后（`split` 口径） | 用例 基线 → 实施 |
|---|---|---|---|---|
| `test_consol_scope_confirmation.py` | L106–108：`with patch("app.deps._get_cached_permission", …(return_value=None)), patch("app.deps._set_cached_permission", …):` | L11 `from unittest.mock import AsyncMock, patch`（只有替身用）删除；`async with` 块体（原 L109–111）减一级缩进 | 387 → 383 | 15 passed → 15 passed |
| `test_disclosure_note_edit_stamp.py` | L77–78：多行 `with` 里的两个缓存替身 | 原 L79 的 `_assert_project_edit` 替身成为 `with` 的第一项；导入不变（其余替身仍用） | 422 → 420 | 45 → 45 |
| `test_note_ai_knowledge_context.py` | L117–118：追加在既有 `with` 后的两个缓存替身 | L14 docstring「权限缓存打桩为「未命中 / 不写」：既不写共享 Redis，也避免用例间缓存串味。」删除 | 227 → 224 | 12 → 12 |
| `test_note_content_template_endpoints.py` | L83–84：两个缓存替身 | L3 docstring 删「；权限缓存打桩为未命中」；L10 导入删除；块体（原 L85–87）减一级缩进 | 226 → 223 | 13 → 13 |
| `test_note_edit_stamp_writers.py` | L99–100：两个缓存替身 | L3 docstring 删「，只替换 Redis 权限缓存」；L12 导入 `AsyncMock, patch` → `patch`（`patch` 在 L235 仍用）；块体（原 L101–102）减一级缩进 | 326 → 324 | 12 → 12 |
| `test_note_prior_year_import_stamp.py` | L104–105：两个缓存替身 | L5 docstring 删「（只替换 Redis 权限缓存）」；L13 导入删除；块体（原 L106–107）减一级缩进 | 196 → 193 | 6 → 6 |
| `test_note_text_batch_endpoints.py` | L137–138：两个缓存替身 | 原 L139 的协调器 `_redis` 替身成为 `with` 的第一项；L4 docstring 删「权限缓存打桩为未命中、」 | 782 → 780 | 46 → 46 |
| `test_ownership_guard_pbt.py` | L43：常量 `_CACHED_PERM = "app.services.custom_query.ownership_guard._get_cached_permission"`；L150 `with` 里的 `patch(_CACHED_PERM, new=AsyncMock(return_value=None))` | 该行变为 `with patch(`，其余两个替身（RLS、审计）原样 | 302 → 301 | 5 → 5 |
| `test_phase4_endpoints.py` | L125–135：autouse 夹具 `_no_permission_cache`（把两个缓存函数 monkeypatch 成返回 None 的 `_miss`，含 docstring 与前置空行） | L27 `import app.deps as deps`（只有该夹具用）删除 | 1167 → 1155（≤ 1177） | 28 → 28 |
| `test_signoff_checklist_service.py` | L337–338：两个缓存替身 | L305 docstring 删「（只替换 Redis 权限缓存）」；L13 导入删除；块体（原 L339–340）减一级缩进 | 384 → 381 | 12 → 12 |
| `test_wp_trace.py` | L413：两项 `with` 里的 `patch("app.deps._get_cached_permission", new=AsyncMock(return_value=None))` | L412 变为单项 `with patch("app.deps.set_rls_context", new=AsyncMock()):` | 456 → 455 | 20 → 20 |

`backend/tests/test_phase8.py`（1117 → 1088，blob `70aad96f8722175a328d1daa75ac81e3bcec283f` → `c581766c0cc3855cc46c254f32aff1c69eb5a039`）：删除 `TestPermissionCache` 的三例（B L1025–1056：`test_cache_miss_returns_none`、`test_set_and_get_cache`、`test_invalidate_cache`），接替测试为任务 3.5 的 `test_permission_cache_removed.py`，改写对照见「既有测试改写对照」。类本身保留（还含 `test_permission_hierarchy`，类名不改以保持其测试标识不变，便于按标识归因），类 docstring「Task 10.5: 权限查询缓存」改为说明缓存已移除、三例删除与接替测试。结果 67 passed + 5 failed → 64 passed + 5 failed（少的 3 例即删除的三例；5 例失败为预存的 `TestReportEngineCache`，两棵树信息逐字相同）。

非空替身改写（本次补改，前次派发遗漏）：`backend/tests/test_d4_import_permission_gate.py::test_authorize_wp_read_allows_readonly_member`。它的假会话对成员级别查询返回「成员行形状」的 MagicMock（`pu.permission_level = MagicMock(value="readonly")`），借它注入 readonly 级别；查询改为只取一列后，`level.value` 取到 MagicMock 的自动属性，`PERMISSION_HIERARCHY.get(...)` 得 0 ⇒ 403。实测：基线树原文件 10 passed；改动后的代码配原测试 1 failed（`HTTPException: 403: 无底稿访问权限`，探针同时记到 `non_level_value: MagicMock`）；改为返回 `PermissionLevel.readonly`（即 `select(ProjectUser.permission_level)` 的标量形状）后 10 passed，探针 0 次异常。改动只有两处：L31 导入补 `PermissionLevel`；L136–138 三行替身改为一行返回加一行注释。断言 `pid == _PROJECT_ID` 原样（blob `ac624bd3e4e09f33f511218877dcd86dd6ba2988`（= B）→ `6e953b2a9c4ec3a8932cd565421a12b9f7a494a5`，227 → 226 行，CRLF）。全仓同类写法（假会话返回带 `permission_level` 属性的替身）另有 `test_advanced_query_hardening_wave012.py` 4 处、`test_custom_query_auth_bug_condition.py` 1 处：现读它们走的是 `custom_query` 路由自己的 `select(ProjectUser)` 内联判定（`_assert_writeback_authorized`、`cell_writeback`），不经三个级别判定点，不受影响（71 / 4 例两棵树都通过，探针对这两个文件 0 次调用）。

残留检索（四个名字 `_get_cached_permission`、`_set_cached_permission`、`invalidate_permission_cache`、`PERM_CACHE_TTL`，仓库外一次性脚本逐行正则）：

- 实施 worktree 全树（跳过 `.kiro`、`node_modules`、`.git`、`__pycache__`、`.hypothesis`、`dist`、`.pytest_cache`，二进制文件跳过）：**0 处**。对照 B：52 处 / 18 个文件。
- 主工作树只读检索（`backend`、`audit-platform/frontend/src`、`scripts`、`tools`、`docs`、`.github`）：52 处，与 B 逐行相同 ⇒ 并发会话没有新增引用。
- 远端目标分支已前进到 `71d0c04b5`（B 之后 5 个提交）：这 5 个提交不改本任务 15 个文件，`git grep` 结果与 B 相同（52 处）⇒ 将来合并不会带入新引用。
- 相关字样（`权限缓存`、`perm:`、`permission cache`、`cached_level`、`_no_permission_cache`、`_CACHED_PERM`）在实施 worktree 的剩余命中逐条判读：`deps._load_member_level` 的 docstring（陈述缓存已移除，准确）；`services/wp_visibility/epoch_cache.py`、`perf_metrics.py`（底稿可见性的 epoch 缓存，另一套缓存，与本任务无关）；`tests/authz_world.py`、`tests/test_authz_world.py`（任务 3.1，把 fakeredis 称作「权限缓存的存储」，并已注明「权限缓存移除后照样可用」）；任务 3.2 的 4 个文件 docstring「门禁与权限缓存读写函数都不替换」——这两组是其他任务的文件，本任务未改，措辞是否随缓存移除更新已在回报中提给编排者；`test_phase8.py` 的类名与 docstring（本任务所改，见上）；其余是以 `perm` 作变量名的无关命中。

运行对照（批次现算：实施 worktree `backend/tests` 下 220 个文件 = A 引用 `app.deps`（AST 导入，或以 `app.deps` 开头的字符串常量）210 个 ∪ B 引用 `ownership_guard` 13 个 ∪ C 假会话返回成员行形状替身的启发式 11 个 ∪ D 显式列入 18 个（本任务改动的 13 个、任务 3.2 的 4 个、`test_authz_world.py`）；基线树中存在其中 218 个，缺 `test_authz_world.py`、`test_role_map_and_context.py`（均为本 spec 新增）。与前次派发现算的清单逐项相同）：

| 运行 | 命令要点 | 结果 |
|---|---|---|
| ① 基线树 | cwd `D:\wt_pm_ref\backend`，`D:\GT_plan\.venv\Scripts\python.exe -B -m pytest <218 个文件> -q -p no:cacheprovider --tb=short -rfE --junitxml=… --deselect tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestExplainAndQueryCount::test_explain_plans_and_no_n1_artifact`；子进程 `PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY=D:\pm_tmp\hyp_t34b_ref`。不选的这 1 例会改写已跟踪的 `explain_plans.txt`，基线树只读 | 111 failed，3397 passed，1064 skipped，1 deselected，7 xpassed（22:55）；运行前后 `git status` 均为空，HEAD = B |
| ② 实施树 | cwd `D:\wt_pm_impl\backend`，同上 argv（不加 `-B`、不 deselect，220 个文件）+ `-p t34b_level_probe`（子进程 PYTHONPATH 追加 `D:\pm_tmp`）；`HYPOTHESIS_STORAGE_DIRECTORY=D:\pm_tmp\hyp_t34b_impl` | 111 failed，3599 passed，1067 skipped，7 xpassed（23:13）；`app` 解析到 worktree。上面那 1 例通过并改写了 `explain_plans.txt`，已按基线树里的干净副本逐字节恢复（blob `f7c541a709284dc2179bd8cb0755d6f31584f3f3` = HEAD，该路径 `git status` 为空） |
| ③ 实施树复跑 | cwd 与环境同 ②（不加探针），只跑 `tests/dsh_agent_panel/test_task5_run_coordinator.py`，两次 | 53 passed、53 passed |
| ④ 实施树单文件 | `tests/test_d4_import_permission_gate.py`：改写前 / 改写后（均带探针）；基线树原文件 | 1 failed + 9 passed → 10 passed；基线 10 passed |

①② 并行运行；子进程都不设 `DATABASE_URL`（`pg_only` 用例跳过），但按 `settings.DATABASE_URL` 默认值连本地库的既有 PG 用例照常执行（副作用见下）。

对照结论（逐测试标识比较两份 junit）：

- 两边都失败 110 例：同一测试标识、同一异常类型与断言信息（107 例逐字相同，3 例只差路径 `D:\wt_pm_ref` / `D:\wt_pm_impl` 或随机 uuid）⇒ 预存失败，按文件分组逐例登记于「预存失败登记」（基线提交 B；本 spec 的最终归因以任务 19.9 干净检出全量运行为准）。
- 实施树失败、基线树通过 1 例：`tests/dsh_agent_panel/test_task5_run_coordinator.py::TestHappyPathAndNoRowPerToken::test_lease_is_released_after_terminal`（`AssertionError: 终态后租约未释放`，`assert 'test-4f860e' is None`）。判读：该文件不经三个级别判定点（探针 0 次调用），也不涉及 `ownership_guard`，只在一处 AST 断言里引用 `app.deps.get_current_user_sse`；用例断言的是协调器跑完后 PG 行的 `lease_owner`，模块级夹具轮询到终态即取快照，两轮并行时 CPU 争用下快照可能早于租约释放。在改动后的实施树上单独复跑该文件两次均 53 passed；同一用例在本次基线轮、前次派发的基线轮与实施树改动前一轮都通过 ⇒ 判为并行负载下的时序抖动，不属本任务引入；基线未复现，也不登记为预存失败。
- 基线树失败、实施树非失败 1 例：`tests/workpaper_sync/test_template_override_lossless.py::TestProperty20OnlyOfficeConversionPreservesPageSetup::test_conversion_roundtrip_keeps_page_setup_semantics`，基线树 `OSError: [WinError 10048]`（端口占用，两轮并行所致），实施树按 OnlyOffice 转换报错跳过；与本任务无关。
- 只在基线树的 40 例：任务 2.2 / 3.2 改名、改参数化前的用例，以及本任务删除的 `TestPermissionCache` 三例；只在实施树的 245 例：任务 2.x / 3.1 / 3.2 新增或改名后的用例，以及基线轮不选的那 1 例，其中失败 0 例。
- 本任务改动的 13 个测试文件逐文件计数见上两节（11 个空替身文件两边全部通过且例数相同；`test_phase8.py` 少 3 例；`test_d4_import_permission_gate.py` 10 → 10）；任务 3.2 的 4 个文件与 `test_authz_world.py` 在实施树全部通过（交付件文件与世界自测各有 1 例 `pg_only` 跳过）。

副作用登记：

- 共享 Redis db0：运行中快照（18:02:47）有 23 个 `perm:*` 键（值 edit / readonly，TTL ≤ 137），键里 23 个用户 id、21 个项目 id 在真库都是 0 行 ⇒ 是基线树一轮（B 代码仍写缓存）的用例写入；实施树代码已没有写入点。未删除，等 TTL 到期：运行结束约 8 分钟后（18:20:17）再扫为 0 个。
- 本地开发库（postgres MCP 只读核对，窗口 17:48–18:20）：`logs` 新增 224 行（`user_id` 全为 NULL；对象类型 workpaper 160 / project 56 / adjustment 3 / dataset 2 / disclosure-note 2 / working_paper 1；project 那 56 行里 32 行的 `object_id` 是真库现存项目「重药控股安徽有限公司_2025」「重庆医药集团医疗器械有限公司_2025」）；`evidence_outbox` 新增 10 行（状态 pending，`project_id` 为「重药控股安徽有限公司_2025」，payload 里引用的附件、附件版本、证据引用在库里都不存在，原因文本含「wave9 citation it」）；`projects`、`users`、`project_users`、`working_paper`、`disclosure_notes` 同一窗口新增 0 行；`wp_access_security_outbox` 近 6 小时 0 行。前次派发两轮运行窗口（16:50–17:20）`logs` 254 行、`evidence_outbox` 10 行，分布同型 ⇒ 是这批既有 PG 用例经独立提交写入的既有行为（B 上同样发生），与本任务改动无关。按约定只登记、不删除；pending 的 outbox 行是否清理由编排者决定。

行数门（cwd `D:\wt_pm_impl`，`D:\GT_plan\.venv\Scripts\python.exe -B backend/scripts/check/check_file_size.py <本任务改动的 15 个文件>`，另逐文件单独跑；脚本按 `splitlines` 计数，比 `split("\n")` 少 1）：

| 文件 | 行数 基线 → 实施 | 门槛 | 退出码 基线 / 实施 |
|---|---|---|---|
| `backend/app/deps.py` | 727 → 661 | 800 | 0 / 0 |
| `backend/app/services/custom_query/ownership_guard.py` | 290 → 280 | 800 | 0 / 0 |
| `backend/tests/test_phase4_endpoints.py` | 1166 → 1154 | whitelist 基线 1121 × 1.05 = 1177 | 0 / 0 |
| `backend/tests/test_phase8.py` | 1116 → 1087 | 800（不在 whitelist） | **1 / 1** |
| 其余 11 个测试文件 | 均 ≤ 781 → ≤ 779 | 800 | 0 / 0 |

`test_phase8.py` 的超限在基线树就存在（预存）；本任务使它减 29 行，但仍超 800。pre-commit 钩子对暂存的每个 `.py` 都跑 `check_file_size.py --staged`，提交含该文件时会被拦（退出码 1）；design §10 的行数门清单没有列它，须在任务 19.8 按 whitelist 规则登记（基线 1087 + 拆分轴）或拆分——已在回报中提给编排者。

ruff（`python -B -m ruff check --no-cache --output-format concise`，同 15 个文件，两棵树各一次）：两边都是同样的 17 条（`deps.py` F401 `get_redis` 与 E402 ×2、`test_phase4_endpoints.py` 7 条、`test_phase8.py` 5 条、`test_consol_scope_confirmation.py` F841、`test_signoff_checklist_service.py` F401 `pytest`），只有行号随删行平移；本任务没有新增任何条目（删替身后同步删掉了只被替身使用的导入）。

本任务不做磁盘变异（任务未要求）；缓存移除的接替守卫 `test_permission_cache_removed.py` 与 Redis 不可用用例由任务 3.5 新增。

#### 任务 3.4 复核（第四次派发，2026-10-20 18:34 起）

派发说明称「worktree 没有本任务的半成品（`deps.py` 与 `ownership_guard.py` 的 blob 都等于 HEAD）」，与磁盘不符。开工时 `git hash-object --path` 现算：`deps.py` = `f02846af04f3806096fe5f7d99a192299e609ecf`（HEAD `1b8daed81029669fdf3f0534413ee39f74b3743e`），`ownership_guard.py` = `d6672338a7cf2a50b6ff6326e6999388ee8ac014`（HEAD `4636a5b0e76cb0c3dc71c33bb2facbc7cee41947`），`test_phase8.py` = `c581766c0cc3855cc46c254f32aff1c69eb5a039`，`test_d4_import_permission_gate.py` = `6e953b2a9c4ec3a8932cd565421a12b9f7a494a5`，都等于上一节登记的改后 blob。上一节由第三次派发写入（本文件修改时间 18:31:47，`D:\pm_tmp\t34b_*` 最后一次写入 18:32:48），之后没有新产出；开工时没有 pytest 进程在跑。本次没有回退重做：逐段复核 `git diff`，结论与上一节一致——`_load_member_level` 与 design §4.4 代码块逐行相同；三个判定点的归档守卫、admin 跳过与 RLS 设置时机、admin / partner 免查、`WORKPAPER_WRITE` 判定、拒绝文案与状态码逐字未动；`OwnershipGuard._can_access_project` 只删缓存快路径与 `from app.deps import _get_cached_permission`。11 个文件删除的替身逐行复核：`_get_cached_permission` 全是 `return_value=None` / `_miss`（返回 None），`_set_cached_permission` 全是空 `AsyncMock()`，没有借缓存注入级别的替身（注入型的 4 个文件已由任务 3.2 改为权限世界成员行）。`test_d4_import_permission_gate.py` 不引用四个名字，属「查询改为只取一列后假会话返回形状不符」，单列于上一节。

本次新增改动：6 个测试文件的 docstring / 注释仍把已删除的缓存读写函数或「权限缓存的存储」当作现存对象描述，按「提及一并改写或删除」处理。只改行内文字，行数与行尾不变，用例函数与断言未动；`ruff check --no-cache` 六个文件通过。

| 文件 | 原文 → 新文 | blob 改前 → 改后 |
|---|---|---|
| `backend/tests/test_phase8_endpoint_role_levels.py` L12（模块 docstring） | 「门禁、归档守卫与权限缓存读写函数都不替换」→「门禁、归档守卫都不替换」 | `27ed793daa014605a024fd0534a4b26fd44b0284` → `57d7be97f4a65866d9cfcbefff94dc1a104b5fbc` |
| `backend/tests/test_deliverable_generation_membership_auth.py` L22（模块 docstring） | 「门禁、归档守卫、EQCR 判定与权限缓存读写函数都不替换」→「门禁、归档守卫与 EQCR 判定都不替换」 | `12c418af6660df12e4048e1eee0d1ad3d0d7d3c3` → `48a4da70b76a6fde3e5017598f76d5b8134e3fa0` |
| `backend/tests/test_wp_disclosure_sync.py` L11（模块 docstring） | 「不替换门禁与权限缓存读写函数」→「不替换门禁」 | `72f5e538b50bb7a2086b0b1b99eba491fc0eba8d` → `f8534ed2b21289f2db053b689395bb1ebf63c6eb` |
| `backend/tests/ledger_import/test_sign_convention_api.py` L48（夹具 docstring） | 「门禁与权限缓存读写函数都不替换」→「门禁不替换」 | `836b70a943f0a895e8c90ba8533bfce74e731e08` → `5c7fcd4da2156943113b6bbf92aac897a5a8fef0` |
| `backend/tests/authz_world.py` L24、L29–31、L489 | 「不预置任何权限缓存条目」→「Redis 替身里不预置任何键」；可替换点「权限缓存的存储：……缓存读写函数本身不替换，本模块也不引用它们的名字（权限缓存移除后照样可用）」→「Redis 客户端（不是判定）：……权限缓存已由任务 3.4 移除（design D3），级别判定点不读写 Redis，这里只让测试进程不连真实 Redis」；`create` 内注释同步 | `d035b28bf37f38fbd1ae0ea84c26ae2be8b044b0` → `a6e5a303d77c583bcc461f7b5842876a20726af3` |
| `backend/tests/test_authz_world.py` L3、L190、L205 | 「权限缓存的存储」→「Redis 客户端」（两处）；「不预置权限缓存条目」→「Redis 替身里不预置任何键」（该用例 L231 断言 `dbsize() == 0`） | `30d954d5d42ef75e1eba52ae65f460fd0827925f` → `8ea4a00e180584645ff87fc902b71ccef9b2af61` |

行数（`split("\n")` 口径）与行尾改后：272 / 500 / 545 / 243（CRLF 271 / 499 / 544 / 242，CRLF 数 = LF 数）；`authz_world.py` 755、`test_authz_world.py` 480（均 LF，无 CRLF）。函数名 `test_cache_storage_is_this_worlds_empty_fakeredis` 未改（改名会改测试标识）。

残留检索（本次重做；仓库外一次性脚本按 UTF-8 逐行正则；范围 `backend`、`audit-platform`、`scripts`、`tools`、`docs`、`.github`，跳过 `.kiro`、`node_modules`、`.git`、`__pycache__`、`.hypothesis`、`dist`、`.pytest_cache`）：四个名字实施树 **0 处**，基线树 52 处。「权限缓存」字样在实施树只剩三类：`deps._load_member_level` docstring 与 `authz_world.py` L30（都陈述缓存已移除）；`test_phase8.py::TestPermissionCache` 类 docstring（「权限查询缓存已移除」）；`services/wp_visibility/epoch_cache.py`、`perf_metrics.py` 与 `procedure_delegation_visibility/test_task17_capacity_and_role_acceptance.py`（底稿可见性的 epoch 缓存，另一套机制，与本任务无关）。其余命中是 `perm` 变量名与其他缓存的「缓存未命中」。

运行对照：

- 全批（实施树 220 / 基线树 218 个文件）沿用上一节第三次派发 17:48:29–18:12:04 的运行产物：实施树代码文件最后修改 17:44:58，早于运行开始，本次之后只改 docstring。本次用独立脚本重新解析两份 junit（`D:\pm_tmp\t34b_ref.xml`、`t34b_impl.xml`）：基线 failed 111 / passed 3404（含 xpassed 7）/ skipped 1064；实施 failed 111 / passed 3606 / skipped 1067；两边都失败 110 例（107 例信息逐字相同，3 例只差树路径或随机 uuid）；实施失败而基线未失败 1 例（`dsh_agent_panel/test_task5_run_coordinator.py::TestHappyPathAndNoRowPerToken::test_lease_is_released_after_terminal`，上一节已判读并单独复跑 2 次通过）；基线失败而实施未失败 1 例（端口占用）；只在实施树的 245 个标识失败 0 例。与上一节逐项一致。
- 复核批次（本次实跑，docstring 改写之后）：35 个文件 = 本任务改动的 13 个测试文件 + 任务 3.2 的 4 个 + `test_authz_world.py` + `git grep -l -e ownership_guard -e OwnershipGuard -- backend/tests` 的其余 17 个（不含 `conftest.py`）。两树同 argv：`D:\GT_plan\.venv\Scripts\python.exe [-B] -m pytest <文件> -q -p no:cacheprovider --tb=line -rfE --junitxml=…`，cwd 各树 `backend`；子进程 env `PYTHONIOENCODING=utf-8`、`HYPOTHESIS_STORAGE_DIRECTORY=D:\pm_tmp\hyp_t34c_<树>`，基线另加 `-B` 与 `PYTHONDONTWRITEBYTECODE=1`；两树并行，18:45:55 / 18:46:06 开始。

| 树 | 结果 |
|---|---|
| 基线 `D:\wt_pm_ref`（34 个文件，缺本 spec 新增的 `test_authz_world.py`） | 6 failed，890 passed（204.65 s） |
| 实施 `D:\wt_pm_impl`（35 个文件） | 6 failed，1035 passed，2 skipped（224.47 s；跳过的是两个 `pg_only`） |

两边 6 例失败同一标识、同一信息：`test_phase8.py::TestReportEngineCache` 5 例与 `workpaper_sync/test_task21_room_service.py::TestDocKeyIsMtimeFree::test_rg17_is_clear_on_the_real_manifest`，均已在「预存失败登记」。实施失败而基线未失败 0 例；只在实施树的 187 个标识失败 0 例；只在基线树的 40 个标识即上一节所述改名前的用例与删除的 `TestPermissionCache` 三例。前后基线树 `git status --porcelain=v1 -uall` 为空、HEAD = B、没有 `backend/.hypothesis`；实施树 `git status` 与开工时相同（21 个 M、11 个 ??）。

行数门（本次重跑；cwd `D:\wt_pm_impl`，`check_file_size.py` 逐文件一次 + 21 个文件合并一次；21 个 = 上一节 15 个 + 本次改 docstring 的 6 个；脚本按 `splitlines` 计）：`deps.py` 661（≤ 800）、`ownership_guard.py` 280、`test_phase4_endpoints.py` 1154（≤ 1177）、`authz_world.py` 754，其余 ≤ 779，退出码均 0；只有 `test_phase8.py` 1087 > 800 退出码 1（基线 1116 同样超限，预存）。

待编排者决定：①`test_phase8.py` 行数门：pre-commit 对暂存的 `.py` 跑 `check_file_size.py --staged`，提交含该文件时会被拦，须登记白名单（写明拆分轴）或拆分；②`D:\pm_tmp` 下前两次派发留下的临时文件（`t34_*`、`t34b_*`、`hyp_t34*`；其中 `t34b_ref.xml` / `t34b_impl.xml` 是全批对照的原始产物）未删，本次只删自己的 `t34c_*`；③上一节登记的本地开发库 `evidence_outbox` 10 行 pending 是否清理。

### 任务 3.5：缓存移除守卫与 Redis 不可用用例（2026-10-20）

改动文件（实施 worktree）：只新增 `backend/tests/test_permission_cache_removed.py`（LF，blob `29417c26b75591c11a373ab9ab4aaf17aca734d5`，458 行（`check_file_size.py` 的 `splitlines` 口径，`split("\n")` 口径 459）；cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py` 退出码 0；`ruff check --no-cache` 通过）。生产代码未改：`deps.py`、`ownership_guard.py` 的 blob 仍是任务 3.4 登记的 `f02846af04f3806096fe5f7d99a192299e609ecf`、`d6672338a7cf2a50b6ff6326e6999388ee8ac014`；worktree `git status` 除本文件外与任务 3.4 收尾时相同（21 个 M，?? 由 11 个变为 12 个）。

- 接替关系：测试 docstring 写明本文件接替任务 3.4 删除的 `test_phase8.py::TestPermissionCache` 三例（改写对照见「既有测试改写对照」中任务 3.4 的三行）。
- 需求 5.7 的适用性（design D12、§2.2）：级别判定点不再有权限缓存，「经缓存读写函数跑用例并先跑命中对照」不适用；替代为本文件判据 ①②。

扫描口径（`ast.parse`；docstring 不计，注释不进语法树；扫描函数 `scan_module(path, judgment_functions)` 接受文件路径）：

- 计入的标识符：名字、属性名、函数 / 类定义名、形参名、关键字实参名、`global` / `nonlocal` 声明、`except … as` 绑定名、导入（模块路径、导入的名字与别名），以及 docstring 以外、整串为点分标识符的字符串常量（`getattr` / `importlib` 式动态引用）；点分的逐段判定。
- 判据 ①：`app.deps` 与 `app.services.custom_query.ownership_guard` 全模块不出现 `_get_cached_permission`、`_set_cached_permission`、`invalidate_permission_cache`、`PERM_CACHE_TTL`（不定义、不引用）。
- 判据 ②：`app.deps` 的 `_load_member_level`、`assert_project_permission`、`authorize_wp_edit`、`authorize_wp_read`（模块顶层定义；扫整个定义：签名、装饰器、函数体，含嵌套函数、lambda 与类）里没有一段含 `redis`（不分大小写，覆盖 `app.core.redis`、`redis_client`、`_redis_client`、`get_redis`、`redis.asyncio` 等），也没有本模块顶层从 redis 相关模块导入时绑定的名字（`import a.b.redis` 不带别名时绑定的是顶层包名，不计，经属性链的 `redis` 段认出）。模块顶层的导入语句本身不在判据 ② 的范围。
- 不空转：两个模块文件就是本树被导入运行的文件（与 `importlib.import_module(name).__file__` 逐一相等），且各扫到标识符；四个判定函数在模块顶层各恰定义 1 次；合成源码（pytest `tmp_path`，仓库外）上两条判据报出写回的定义、字符串式引用、函数体内的 Redis 导入与嵌套函数经顶层别名的访问，docstring（含整串恰为被禁名字的）与注释不报。

现算结果：`app.deps` 扫到标识符 787 个，判据 ① 0 处；四个函数各定义 1 次，判据 ② 各 0 处；顶层由 redis 相关模块导入绑定的名字只有 `get_redis`（`from app.core.redis import get_redis`，B 中即有、模块内未使用，任务 3.4 已登记为 ruff F401；它在模块顶层，不在判据 ② 的范围）。`ownership_guard` 扫到标识符 426 个，判据 ① 0 处。四个名字在实施树（`backend`、`audit-platform`、`scripts`、`tools`、`docs`、`.github`，跳过规则同任务 3.4）只出现在本文件，共 8 行（扫描数据、docstring、合成源码）。

灵敏度核对（不是需求 12.5 的磁盘变异证明）：仓库外一次性探针导入本文件的 `scan_module`，扫描写在 `D:\pm_tmp\t35_sens\` 的合成源码（由实施树真实文件复制后改写）与基线树的真实文件（只读）；四个真实文件的 sha256 前后不变；探针与合成源码已删。

| 编号 | 合成改动 | 判据 ① | 判据 ② |
|---|---|---|---|
| D0 / G0 | 实施树 `deps` / `ownership_guard` 原样（对照） | 0 / 0 | 四个函数各 0 |
| D1 | `deps` 末尾写回 `_get_cached_permission` 定义（函数体内导入 `redis_client`） | 1：定义 `_get_cached_permission` | 四个函数各 0（判据 ② 只看四个判定函数，写回的定义由判据 ① 报出） |
| D2 | `assert_project_permission` 函数体首句加 `from app.core.redis import redis_client` | 0 | `assert_project_permission` 2：导入 `app.core.redis`、`app.core.redis.redis_client` |
| D3 | 只在两处函数 docstring、函数体内两行注释、模块顶层一行注释里写入四个名字与 `redis_client`、`get_redis` | 0 | 四个函数各 0 |
| D4 | 模块顶层 `from app.core.redis import redis_client as _perm_store`，`authorize_wp_read` 内 `await _perm_store.get(...)` | 0 | `authorize_wp_read` 1：名字 `_perm_store` |
| D5 | `authorize_wp_edit` 内 `getattr(sys.modules["app.deps"], "PERM_CACHE_TTL", 300)` | 1：字符串 `PERM_CACHE_TTL` | 四个函数各 0 |
| D6 | `_load_member_level` 内嵌套函数 `await get_redis()` | 0 | `_load_member_level` 1：名字 `get_redis` |
| D7 | `assert_project_permission` 内 `_ttl = deps.PERM_CACHE_TTL` | 1：属性 `PERM_CACHE_TTL` | 四个函数各 0 |
| G1 | `ownership_guard` 写回 `from app.deps import _get_cached_permission` 与 `_can_access_project` 内的快路径调用 | 2：导入、名字 | — |
| G2 | `ownership_guard` 只在模块 docstring 与注释里写入 | 0 | — |
| R1 | 基线树 `deps.py`（只读，未改） | 11：三个缓存函数的定义 3、`PERM_CACHE_TTL` 的赋值与使用 2、三个判定点对读 / 写函数的调用 6 | `_load_member_level` 定义 0 次（「四个函数各恰定义 1 次」在基线上即红）；其余三个函数各 0（基线经缓存函数间接访问 Redis，由判据 ① 拦下） |
| R2 | 基线树 `ownership_guard.py`（只读，未改） | 2：导入、名字（模块 docstring 里的 `deps._get_cached_permission` 不计） | — |

D0~D7、G0~G2 共 11 个合成用例的命中与期望逐值相同。

Redis 不可用用例（需求 5.3）：

- 替身：把 `app.core.redis` 的 `redis_client`、`_redis_client` 两个名字（与权限世界换 fakeredis 是同一处）换成 `RedisOutage`：每次属性访问都记入 `touched`，取到的命令被调用时抛 `redis.exceptions.ConnectionError`，或 `asyncio.sleep(5)` 后返回 None。只换 Redis 客户端，不换任何判定函数（门禁、归档守卫、`_load_member_level`、委派查询都是生产代码）；直接判定用例自证 `archive_guard`、`eqcr_query`、`rls` 都未替换，HTTP 用例自证前两项未替换（RLS 按权限世界惯例置空）。
- 替身自测：连接错误替身的 `get` 抛错、信息逐字相等，生产 `get_redis()` 返回 None，`touched == ["get", "ping"]`；阻塞替身的命令 0.3 秒内不返回（取消后为 `CancelledError`），`touched == ["get"]`。
- `assert_project_permission`：八种身份 × review / edit 级 × 两种替身（16 例）。Redis 正常时结论等于写死的期望（edit 成员与 admin 放行；review / qc / EQCR 成员 review 放行、edit 403「权限不足」；readonly 成员与非成员 403；已归档 423），fakeredis 里 0 个键；换上替身后逐值相同，替身访问 0 次，单次判定 < 1 秒。
- 经 HTTP（`POST /api/projects/{pid}/cross-check/rules/custom`，5 种身份 × 两种替身，10 例）：（状态码，响应体，业务桩调用次数，`assert_project_permission` 执行次数）在 Redis 正常时为：edit 成员 (200, 桩返回值, 1, 2)、review 成员 (403「权限不足」, 0, 2)、非成员 (403「权限不足」, 0, 1)、已归档 (423 `PROJECT_ARCHIVED`, 0, 2)、admin (200, 桩返回值, 1, 2)；换上替身后逐值相同，状态码 < 500，替身访问 0 次，单个请求 < 1 秒。请求路径：`dependency_overrides` 恰为 {`get_current_user`, `get_db`}，真实 `get_current_user`（令牌黑名单与 SoD 撤销检查读 `redis_client`，不可用时自行降级跳过）不经过；测试应用是裸 FastAPI，没有中间件；该路由的生产注册不附加 `dedicated_wp_gate`；业务 service 打桩。
- 阈值 1 秒：需求 5.3 的上限是「单次判定因等待缓存而增加的耗时合计不超过 1 秒」；判定点不再访问 Redis，正常时毫秒级；阻塞替身每个命令 5 秒，判定路径上只要访问一次就会越过。
- 耗时（各用例写进 junit properties，下表取最大值）：

| 运行 | 直接判定：正常 / 替身 | HTTP 请求：正常 / 替身 |
|---|---|---|
| 本文件单跑 | 2.7 / 1.5 ms | 6.8 / 5.9 ms |
| 与 `test_authz_world.py` 同批 | 3.1 / 2.7 ms | 8.7 / 7.6 ms |

Redis 不可用用例的灵敏度核对（同样不是需求 12.5 的磁盘变异证明）：仓库外一次性 pytest 插件在内存里把 `app.deps._load_member_level` 换成「先 `redis_client.get(...)` 一次、出错吞掉、再查库」的版本（门禁本身仍是生产对象，不写文件），跑 `-k "redis_outage and (review_member or edit_member)"` 选中的 14 例：12 failed、2 passed（64.86 s）。12 例都红在「替身访问 0 次」断言（直接判定 `['get', 'get']`；HTTP `['get', 'get']`，已归档身份 `['get']`）；通过的 2 例是直接判定的已归档身份（归档守卫在读级别之前返回 423，该变异不在其路径上）。阻塞替身下记录的耗时为 5.0 秒（直接判定）、5.0~10.0 秒（HTTP），同样越过 1 秒阈值（耗时断言排在访问次数断言之后）。这一变异下结论断言仍绿（错误被吞），说明访问次数与耗时两条断言是本组用例的判别项。

运行（cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -m pytest <文件> -q -p no:cacheprovider --tb=short -rf`）：

| 运行 | 结果 |
|---|---|
| ① `tests/test_permission_cache_removed.py` | 36 passed（10.73 s） |
| ② `tests/test_authz_world.py tests/test_permission_cache_removed.py` | 89 passed，1 skipped（`test_authz_world.py` 的 `pg_only`），15.72 s |
| ③ 同 ②，两文件顺序对调 | 89 passed，1 skipped，13.23 s |

首版用 `record_property` 记耗时，在 `--junitxml`（默认 xunit2）下每例报一条 `PytestWarning`（共 26 条）；改为直接写 `request.node.user_properties`（junit 结果相同，不报告警）后得上表结果。

副作用核对（postgres MCP 只读，19:23:28–19:32:17）：`evidence_outbox`、`wp_access_security_outbox` 新增 0 行；`logs` 新增 9 行（19:30:42–19:30:58，`user_id` 为空，对象类型 workpaper 2 / project 4 / attachment 3，对象 id 都不是权限世界的固定项目 id，在 `projects` 中也不存在）。其中 3 行早于运行 ② 的会话开始（junit 时间戳 19:30:54.6）；两个文件的路径上没有底稿与附件写入；同两文件的运行 ③（19:31:37–19:31:57）窗口内 0 行 ⇒ 判为并发会话产生，与本任务无关，未处理。

写法自查（需求 12.13）：无 skip / xfail；`pytest.raises` 只有一处，只裹一条语句，其后断言异常信息逐字相等；断言没有「或」组合，也没有对多元素字面量的成员判断；monkeypatch 只换 Redis 客户端两个名字（基础设施，与权限世界同一处），未替换门禁与判定；不是性质测试。

待编排者知悉：①四个缓存名在实施树重新出现，只在本守卫文件（8 行，作扫描数据、docstring 与合成源码）；之后的全仓残留检索应把本文件作为唯一的预期命中（或排除它）。②`deps.py` 顶层未使用的 `from app.core.redis import get_redis` 不在本守卫的禁止范围（判据 ② 只看四个判定函数）。

### 任务 4.1：委派同步按映射精确写入（2026-10-20）

改动文件（实施 worktree）：

- `backend/app/services/assignment_service.py`（保持 CRLF；374 行（`check_file_size.py` 的 `splitlines` 口径，`split("\n")` 口径 375），改动前 345 行；blob `5b5af0388ac2e59b17bccd520e251063eebdd11b`；`check_file_size.py <本任务两文件>` 退出码 0；`ruff check --no-cache` 通过）：
  - `_sync_project_users` 按 design §4.3 改写：一次查询取批次内人员库记录 → 用户（`is_deleted = false` 且 `user_id` 非空，D4、需求 3.9）；同一用户的委派合并后经 `resolve_member_mapping` 得一组取值（3.3、3.8）；按用户 id 字符串排序处理；没有未删除成员行则新建，有则就地改写项目角色与级别（可升可降，不看全局角色；`scope_cycles` / `scope_accounts` / `valid_from` / `valid_to` 不碰）（3.1、3.2）；只按（本项目，批次内用户，未删除）查成员行（3.4）；返回 `MemberChange` 列表；只 flush。
  - 新增模块级 `MemberChange(NamedTuple)`：`user_id`、`before`（新建为 None）、`after`，`describe()` 供日志。
  - `save_assignments`：接住返回值，有改动时记一条 info 日志（`save_assignments: project=…, member rows changed (n): <用户>: <前> → <后>; …`）；返回值不变，仍只 flush；docstring 补两句。
  - `ProjectUser` 改为模块顶层导入（原在函数体内）；删除函数体内的 `PERM_ORDER` 与 `PermissionLevel as PL` 延迟导入；模块注释「同时保留原有 `_sync_project_users` 中的用法」一句改为「经 `resolve_member_mapping` 读取本常量」。
  - `resolve_member_mapping` 未改：传入单个字符串抛 `TypeError` 的现行为保持，同步只传列表。
- 新增 `backend/tests/test_assignment_sync_examples.py`（LF；276 行 `splitlines` 口径，`split("\n")` 口径 277；blob `789291ff306a91b7000ea60b7ad5d5013b21ec12`）：6 个示例，真实 SQLite 内存库，不替换任何生产函数；Redis 两个客户端名换成本文件独占的 fakeredis（与权限世界同一处），只为不写共享开发 Redis（`save_assignments` 末尾的 SSE 广播会异步写流），不观测它。期望值按需求原文写死。刻意不与 4.2 的三个固定样例（edit 改派为 EQCR、edit 改派为未登记、同一用户 manager 与 eqcr）重合。

| 用例 | 需求 | 内容 |
|---|---|---|
| `test_new_member_rows_take_role_map_values` | 3.1、2.2 | 三个用户无成员行：`partner` → (partner, edit)、`观察员` → (readonly, readonly)、`助理` → (auditor, edit)；返回的改动恰为三条新建 |
| `test_existing_rows_rewritten_in_place_up_and_down` | 3.2 | 四条已有成员行（都带循环 / 科目范围与有效期）：(auditor, edit) + `质控` → (qc, review)；全局 admin 的 (readonly, readonly) + `项目经理` → (manager, edit)；(qc, review) + `观察员` → (readonly, readonly)；(manager, edit) + `manager` 不变。行 id 集合不变，各行范围与有效期为原值，返回的改动只含前三条 |
| `test_eqcr_alias_writes_partner_review` | 3.3 | 无成员行 + `独立复核合伙人`、(readonly, readonly) + `eqcr`（全局 eqcr）→ 都写 (partner, review) |
| `test_same_user_via_two_staff_records_gets_one_merged_row` | 3.8 | 三个用户各两份人员库记录：`审计员` + `质控` → (auditor, edit)；`assistant` + `合伙人` → (partner, edit)；`观察员` + `qc` → (qc, review)。正序、倒序各在一个项目上跑，两项目结果逐值相同，每个用户只一条成员行、一条改动 |
| `test_rows_outside_the_batch_are_untouched` | 3.4 | 批次内用户在另一项目的成员行（带范围与有效期）、批次外（本次被移出团队）的成员行、已删除的成员行同步后逐值不变；只新增批次内用户在本项目的一条 (qc, review) |
| `test_save_assignments_skips_unlinked_and_deleted_staff_and_only_flushes` | 3.9、D4 | 经 `save_assignments`：未关联用户的人员库记录、已删除的人员库记录（其用户原有 (qc, review)，若不跳过会被改写为 (partner, edit)）都跳过；三条委派照常保存，返回值即这三条；本项目成员行只有原 (qc, review) 与新建的 (qc, review)；会话 `after_commit` 0 次且仍在事务中；该模块 info 日志恰 1 条且逐字相等 |

与设计的偏差（都不改变结果）：

1. 批次为空时直接返回 `[]`（不发人员库查询、不 flush）；设计代码会发一条空 `IN` 查询再 flush，结果相同。
2. `staff_id` 先 `UUID(str(...))` 归一再比对：设计代码按 `pa.staff_id` 直接查字典。旧实现由数据库比较，传入字符串形式的 id 也能匹配；归一后保持这一点，避免 PG（原生 UUID 接受字符串）上委派落库成功、同步却静默跳过。路由传入的始终是 UUID（`AssignmentCreate.staff_id: UUID`）。
3. 日志放在 `save_assignments`（设计只写「只用于 info 日志与测试」，未定位置）；`MemberChange` 多一个 `describe()`。

不读写 `perm:*`：`assignment_service.py` 的语法树里没有含 `redis` 的标识符或导入，没有以 `perm:` 开头的字符串常量；文本里 `redis` 1 处是 `save_assignments` 中 B 即有的注释（「地址库/报表 Redis/程序表缓存全清」），`perm:` 1 处是新 docstring。运行时的 `perm:*` 零读写删判据属 4.3（失败路径）与 14.3（性质 6），本任务未写。

测试命令（cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -m pytest <文件> -q -p no:cacheprovider --tb=short -rfE`，子进程环境不带 `DATABASE_URL`）：

| 运行 | 结果 |
|---|---|
| ① 改动前（实施树，本任务未动时），相关 12 个文件 | 382 passed，1 skipped（`test_deliverable_generation_membership_auth.py::test_compare_only_reads_this_projects_execution`，`pg_only`），199.3 s |
| ② 改动后，同 12 个文件 + 新文件 | 388 passed，1 skipped（同上），234.8 s |
| ③ 新文件单跑 | 6 passed，3.2 s |

相关文件按 import / 调用现算：调用 `save_assignments` / `_sync_project_users` / `POST /api/projects/{pid}/assignments` 的是 `test_staff_service.py`、`test_assignment_invalidates_auto_cache.py`；直接导入 `app.services.assignment_service` 的另有 `ledger_import/test_sign_convention_api.py`、`test_deliverable_generation_membership_auth.py`、`test_phase8_endpoint_role_levels.py`、`test_wp_disclosure_sync.py`、`test_role_map_and_context.py`；读该文件源码的扫描是 `test_event_year_contract.py`、`test_role_map_single_source.py`、`test_eqcr_alias_single_source.py`；经 `eqcr_resolver` 间接导入的是 `test_eqcr_resolver_property.py`、`test_eqcr_resolver_smoke.py`。补扫（委派端点的其他拼法、`"assignments"` 字面量）没有新的调用方：`test_batch_assign_enhanced_endpoint.py`（底稿批量分配）、`test_handover_service.py` / `test_handover_e2e.py`（人员交接，转移项目委派但不经 `save_assignments` / `_sync_project_users`）命中的都是响应字段。

既有测试改写：无。上述文件在新行为下原样通过：两处调用 `save_assignments` 的既有用例里人员库记录都不关联登录用户（改动前后都跳过），不观测成员行；没有既有用例断言「只升不降」或「不看人员库记录删除标记」。「既有测试改写对照」小节本任务不加行。

灵敏度核对（不是需求 12.5 的磁盘变异证明）：仓库外一次性 pytest 插件在内存里把 `_sync_project_users` 换回 B 的实现（逐行照抄，只把隐式返回的 `None` 改为 `[]`；`ROLE_MAP` 用实施树新值，只隔离同步逻辑），新文件 6 例全红。三例红在成员行断言：`test_existing_rows_rewritten_in_place_up_and_down`（降级未发生）、`test_same_user_via_two_staff_records_gets_one_merged_row`（正序项目上 `assistant` + `合伙人` 得 (auditor, edit)）、`test_save_assignments_…`（经已删除的人员库记录改写为 (partner, edit)）；另三例的成员行断言在旧实现下也成立，红在返回的改动断言（旧实现无返回值）。插件与输出已删。

副作用核对（postgres MCP 只读）：`evidence_outbox`、`wp_access_security_outbox`、`project_users`、`project_assignments`、`notifications` 在全部运行前后行数不变（738 / 705 / 88 / 86 / 778）。`logs` 在运行 ① 窗口内（19:51:25 起约 3 分 20 秒）新增 3 行（19:53:59，`user_id` 为空，project 1 / workpaper 2，对象 id 在 `projects` / `working_paper` 中都不存在）；同一批文件的运行 ②（20:12:32 起约 4 分钟）及 ③、灵敏度核对的窗口内 0 行，且同一形态的行在本任务开始运行之前（19:21、19:30、19:38）也出现 ⇒ 不是本任务的测试产生（来源未定，按既有口径记为并发会话），未处理。

写法自查（需求 12.13）：无 skip / xfail；无 `pytest.raises`；无子进程；断言无「或」组合，也没有对多元素字面量的成员判断；monkeypatch 只换 Redis 两个客户端名（基础设施）；不是性质测试。

待编排者知悉：① 新文件不含 4.2（Property 2 及其固定样例）与 4.3（失败语义、`perm:*` 零读写删、只有已删除成员行时新建）的内容。② SQLite 上 `idx_project_users_project_user` 不带删除条件，批次内用户「只有已删除成员行」时新建会被唯一索引误拒；4.2 若在 SQLite 上生成该情形，须仿照 `test_eqcr_resolver_property.py::_f4_index_ddl` 改建部分唯一索引，或留给 4.3 的真 PG 用例。

### 任务 4.2：委派同步的性质测试（2026-10-20）

改动文件（实施 worktree）：只新增 `backend/tests/test_assignment_sync_property.py`（LF；482 行 `splitlines` 口径，`split("\n")` 口径 483；blob `615e1f45e51be4bec2e2546f847ecdd626748353`）。cwd `D:\wt_pm_impl` 跑 `backend/scripts/check/check_file_size.py backend/tests/test_assignment_sync_property.py` 退出码 0；`ruff check --no-cache` 通过。未改生产代码，未改其他测试（4.1 的 `test_assignment_sync_examples.py` 未动）。

测试文件结构：

- 被测：`AssignmentService._sync_project_users`，直接调用（与 4.1 示例同口径）。每个样例跑两次，各用一个独立的 SQLite 内存库（`asyncio.run` + `StaticPool`）：造数相同（项目、用户、成员行、人员库记录的 id 由固定名字空间的 `uuid5` 生成，两次逐个相同），本批委派一次按原顺序、一次按打乱后的顺序落库并传入（同 `save_assignments`：先 flush 新委派再同步）。不替换任何函数，不用 monkeypatch；被测函数只用传入的会话，不碰 Redis。
- 断言（`_check_property`）：① 两次运行的观测相等（「打乱批次内委派顺序后结果不同」）；② 观测等于模型（「同步结果与模型不一致」）。观测 = 全部成员行（含已删除）+ 返回的 `MemberChange` 列表：造数时已有的行按标签（如 `P/u0/live`、`P/u0/deleted0`、`Q/u0/live`）逐项比较项目、用户、项目角色、级别、循环范围、科目范围、有效期起止、删除状态、删除时间；同步新建的行比较（项目，用户，项目角色，级别，删除状态）；改动列表每个用户至多一条（改写前 / 改写后，新建时改写前为 None）。由此同时钉住：批次内已关联用户在 P 恰一条未删除成员行且取值等于模型；已有未删除行就地改写（行 id、范围、有效期不变）；批次外用户、只经未关联或已删除人员库记录出现的用户、已删除的行、Q 上的行逐值不变；不删行、不多建行。
- 模型（在测试里独立计算，不导入 `ROLE_MAP` / `resolve_member_mapping`）：取值表用 `tests/role_map_expected.py` 的 `EXPECTED_ROLE_MAP` / `EXPECTED_EQCR_ALIASES`；任一委派角色属于 EQCR 别名集合 ⇒ (partner, review)（3.3）；否则取最高级别（readonly < review < edit），项目角色按 partner、manager、qc、auditor、readonly 的先后取第一个（3.8）；未登记 ⇒ (readonly, readonly)（3.1）；未关联登录用户或已删除的人员库记录上的委派跳过（3.9、D4）；全局角色不参与（3.2）。
- 生成器 `_worlds`（需求 3.5、design §8.3）：0~6 条委派（条数先抽再逐条生成），每条一份独立的人员库记录（F4 按构造成立）；委派角色取期望表 13 个键、两个 EQCR 别名、键的大写与首尾空格变体、`st.text(max_size=30)`（排除 NUL 与代理字符）；约三分之一未关联登录用户、约三分之一人员库记录已删除；同一用户可经两份及以上记录出现；1~4 名批次内候选用户，各自在 P 的未删除成员行为「无 / 有」（约 1:3；有则项目角色取 `ProjectUserRole` 全部 6 个值、级别取全部 3 个值），另带 0~1 条已删除成员行，在 Q 各一条成员行；另置 1~2 名批次外成员（P 上一条未删除成员行 + 0~1 条已删除，Q 上 0~1 条）；成员行范围取三种（全空 / 循环 + 科目 + 起止 / 只有循环与起日）；全局角色取 `UserRole` 全部 7 个值；委派另带循环范围（不应流入成员行）；打乱后的顺序为 `st.permutations`。
- 显式样例（`@example`，结论按模型核对）：E1 `E1-deleted-rows-and-skipped-staff`（u0 在 P 只有已删除成员行 → 新建 (qc, review)；u1 唯一记录已删除、持有 `eqcr` → 不动；未关联记录持有 `partner`；u2 已删除记录持有 `eqcr`、现行记录持有 `manager` → 新建 (manager, edit)；批次外 u3 有未删除与已删除行各一条；打乱为 (4, 2, 0, 3, 1)）；E2 `E2-merge-tiebreak-exact-match`（u0 `assistant` + `合伙人` 同为 edit → (partner, edit)，由 (readonly, readonly) 就地升级；u1 全局 admin，` manager`（首部空格，未登记）→ (qc, review) 降为 (readonly, readonly)；u2 `审计员` + `质控` → (auditor, edit)，原为 (partner, review)；u0、u2 各自两条委派的先后在打乱后都反过来）；E3 `E3-empty-batch`（空批次：成员行都不动，改动为空）。
- 固定样例（`test_property_2_fixed_examples`，被测用户都是 u0，另有一名批次外成员；先断言模型等于按需求原文写死的期望，再跑全部断言）：`F1-edit-to-eqcr`：(manager, edit) + `独立复核合伙人` → (partner, review)，就地改写，范围与有效期保持；`F2-edit-to-unregistered`：(auditor, edit) + `观察员` → (readonly, readonly)；`F3-manager-and-eqcr-same-user`：在 P 无成员行，两份人员库记录各持 `manager`、`eqcr` → 新建 (partner, review)，正序与倒序各跑一次。
- 测试库自检 `test_sqlite_member_index_is_pg_equivalent`：见下。

SQLite 唯一索引的处理（取「在测试库另建等价的部分索引」，覆盖需求 3.1「只有已删除成员行时新建」与「同一（项目，用户）已删除 + 未删除各一条」）：建表后 `DROP INDEX idx_project_users_project_user`，按模型 `Index` 声明的列、`unique` 与 `postgresql_where` 拼出 `CREATE UNIQUE INDEX idx_project_users_project_user ON project_users (project_id, user_id) WHERE is_deleted = false`（写法同 `test_eqcr_resolver_property.py::_f4_index_ddl`）。自检钉住：`sqlite_master` 中该索引的 SQL 等于上式；同一（项目，用户）两条已删除 + 一条未删除可以插入，再插一条未删除报 `UNIQUE constraint failed: project_users.project_id, project_users.user_id`。需求 3.1 要求的真 PG 验证仍归任务 4.3（`pg_only`），本文件不替代它。`idx_assignment_project_staff` 未改：本文件只插入批次内的现行委派，且每份人员库记录至多一条，不会撞到它。

运行（cwd `D:\wt_pm_impl\backend`；`import app` 解析到 `D:\wt_pm_impl\backend\app\__init__.py`；环境不带 `DATABASE_URL`）：

| 运行 | 结果 |
|---|---|
| `D:\GT_plan\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_assignment_sync_property.py -q -p no:cacheprovider --tb=short -rf` | 5 passed（1 条 hypothesis + 3 个固定样例 + 1 条索引自检），约 3 s |
| 同上加 `-v --hypothesis-show-statistics` | 5 passed；hypothesis「5 passing examples, 0 failing examples, 0 invalid examples」「Stopped because settings.max_examples=5」 |
| 本文件 + `tests/test_assignment_sync_examples.py` | 11 passed |

生成器自检（仓库外一次性探针，已删）：不连库抽 400 个样例：委派条数 0~6 各档都有（0 条 84 个、6 条 33 个），合计 917 条委派，未关联登录用户 313 条（34%），已关联但人员库记录已删除 151 条；含「同一用户经两份及以上记录出现」的样例 93 个；批次内已关联用户改写前「无 / readonly / review / edit」= 55 / 98 / 91 / 69，其中在 P 只有已删除成员行的 31 个；改写方向：降级 92、升级 74、只改项目角色 69、不变 23；触发 EQCR 优先 129 次（与其他角色同批 52）；混合级别合并 78 次；同一级别多个项目角色候选（用到固定先后）只 4 次，由显式样例 E2 确定性覆盖；只经已删除记录出现的用户 69 个；打乱后不是恒等排列的样例 181 个；委派角色长度全部 ≤ 30；7 个全局角色、成员行项目角色 6 个值（含 eqcr）、三种范围都出现。

灵敏度核对（不是需求 12.5 的磁盘变异证明；需求 12.5 的变异清单不含 Property 2）：仓库外一次性 pytest 插件（子进程 `PYTHONPATH` 指向 `D:\pm_tmp`，`-p` 加载）在 `pytest_configure` 中把 `AssignmentService._sync_project_users` 换成内存里编译的版本，逐个跑本文件；M0 为现行源码经同一编译路径（对照），M1 为基线树 B 的实现（只把隐式返回的 None 改为 `[]`），其余为对现行源码的单处文本替换（替换前断言该片段恰出现一次）。子进程另设 `HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外，不往 worktree 的样例库写入。不写 worktree 文件：前后 `assignment_service.py` 的 sha256 都是 `0e76769e8a4e2d759efaaba96ff292671f40656d7fab642aa1e25240938d0e6a`，测试文件都是 `48759f74ac944b3e818d046a208084aa0828617730f87695ea4c915ce4628800`。插件、驱动与输出已删。

| 变异 | 变红（hypothesis 测试另注红在哪个样例） | 其余 |
|---|---|---|
| M0 原样（对照） | 无 | 5 passed |
| M1 基线 B 的实现（逐条处理、只升不降、不看人员库记录删除标记、无返回值） | F1、F2、F3（「同步结果与模型不一致」）；hypothesis 红在 E1（模型不一致）与 E2（「打乱批次内委派顺序后结果不同」） | 1 passed |
| M2 人员库记录查询去掉 `is_deleted == False`（D4） | hypothesis 红在 E1 | 4 passed |
| M3 只升不降（取值不同改为「级别更高才改」） | F1、F2；hypothesis 红在 E2 | 2 passed |
| M4 不做 EQCR 优先（只取最高级别 + 固定先后） | F3；hypothesis 红在随机生成的样例（非确定性，收缩约 35 s） | 3 passed |
| M5 同一用户只留最后一条委派 | F3 与 hypothesis 的 E2，都红在「打乱批次内委派顺序后结果不同」 | 3 passed |
| M6 成员行查询去掉「未删除」条件 | hypothesis 红在 E1（已删除的行被改写，没有新建） | 4 passed |
| M7 成员行查询去掉项目条件 | F3 与 E1 红在模型断言（Q 上的行被改写）；F1、F2 与 E2 抛 `MultipleResultsFound`（未预期异常，不计为断言变红） | 1 passed |
| M8 改写时清空循环范围 | F1、F2；hypothesis 红在 E2 | 2 passed |
| M9 委派角色先去首尾空白再映射 | hypothesis 红在 E2（` manager` 被当成 `manager`） | 4 passed |
| M10 同步时把批次外用户在 P 的未删除成员行降为 readonly | F1、F2、F3；hypothesis 红在 E1（另一显式样例同错，hypothesis 合并报告） | 1 passed |

M1~M10 都由固定样例或显式样例确定性地打红（M4 的确定性红在 F3，M7 的断言红在 F3 与 E1）。

副作用核对（postgres MCP 只读）：本文件单跑前后 `project_users` / `staff_members` / `users` / `project_assignments` / `logs` 行数 88 / 215 / 94 / 86 / 94276 不变（只用内存库）。

与设计 / 需求的偏差（都不改变判据）：

1. 直接调 `_sync_project_users`，不经 `save_assignments`：Property 2 的对象是委派同步；`save_assignments` 的兼任校验会拒掉部分生成批次，其 epoch / 通知 / 广播写入与本性质无关。保存路径由 4.1 的示例、失败语义由 4.3 覆盖。
2. 「只有已删除成员行时新建」在 SQLite 上靠等价部分唯一索引覆盖（生成器 31 / 400 + 显式样例 E1）；需求 3.1 的真 PG 验证仍归 4.3。
3. 新建行只比（项目，用户，项目角色，级别，删除状态），不比其循环范围与有效期（需求未规定新建行的这些取值）。
4. 生成器比需求 3.5 多几个维度（需求 3.2、3.4 与 D4 涉及）：全局角色任取、成员行范围与有效期、已删除成员行、人员库记录已删除、委派的循环范围。「批次内候选用户」可能没有现行委派（没被抽中，或只经未关联 / 已删除记录出现），这类用户按批次外核对；「另置 1~2 名批次外成员」照需求另加。
5. 未发现生产缺陷。

写法按需求 12.13 自查：未用 monkeypatch 与 `dependency_overrides`；hypothesis 测试显式声明 `@settings(max_examples=5, deadline=None)`；唯一的 `pytest.raises` 块只有一条语句，其后断言异常信息；断言里没有「或」组合，也没有对多元素字面量的成员判断；没有 skip / xfail；没有子进程。

### 任务 4.3：委派保存的失败语义与真 PG 用例（2026-10-20）

新增 `backend/tests/test_assignment_save_semantics.py`（LF；592 行 `splitlines` 口径，`split("\n")` 口径 593；blob `88f2f36ee785ede27e0c03d3a174e668c892e37f`；`ruff check --no-cache` 通过；`check_file_size.py` 退出码 0）。未改生产代码、权限世界与其他测试。

被测调用链（现读）：`routers/assignments.py::save_assignments`（只依赖 `get_db`、`get_current_user`；`SodViolation` → `db.rollback()` + 409，否则 `db.commit()` 后 `invalidate_auto_cache`）→ `AssignmentService.save_assignments`（兼任校验批量模式 → 软删旧委派 → 插新委派 → `_sync_project_users` → `bump_policy_epoch` → 通知 → `event_bus.broadcast_raw`）。`routers/assignments.py`、`sod_guard_service.py`、`event_bus.py`、`wp_visibility/delegation_transaction.py`、`core/database.py`、`core/redis.py`、`middleware/error_handler.py` 与 B 无差异（`git diff B -- <这些文件>` 为空）⇒ 409 的形态与文案「照旧」（需求 9.5）。

测试方式：
- 按生产注册挂路由（`authz_world.build_app`），httpx `ASGITransport(raise_app_exceptions=False)` 真发请求，经 `GateClient`（每次请求前核对门禁为生产对象、override 只有当前用户）；另挂 `app/main.py` 的 `HTTPException`、`Exception` 两个处理器，失败响应与生产同形。
- 不 override `get_db`：生产 `get_db` 照常执行，只把它用的 `app.core.database.async_session` 换成开在权限世界库上的会话工厂（计数，每个请求恰 1 个）。没用 `world.client`：它的 `get_db` override 让请求复用世界的会话且不关闭，测不到「会话关闭即回滚」。
- 独立会话 / 引擎现读：路由、`assignment_service`、`sod_guard_service`、`delegation_transaction`（及其构造的 `StaffUserMappingService`、`ProcedureWpResolver`）、`procedure_table_auto_service` 均不引用 `async_session` / `engine` / `SyncSession` / `create_async_engine`，会话只来自 `get_db`。另有 autouse 守卫：`app.core.database.engine`（本地开发库）上挂 `before_cursor_execute`，有语句即记录并拦下，用例结束断言为空（两轮都为空）。
- 世界补建 `notifications`、`wp_visibility_policy_epoch`、`wp_visibility_invalidation_outbox`（外键只指向世界内的表）；造数提交后取快照：这三张表与委派、成员行共五张表的全部行（含已删除）逐列比较。

| 用例 | 触发方式 / 注入点 | 断言 |
|---|---|---|
| `test_sod_rejection_returns_409_and_keeps_everything` | 真实输入：u1 同批 `eqcr` + `manager`，不替换任何函数 | 409，`error_code` = `SOD_EQCR_INDEPENDENCE_CONFLICT`，message 逐字为「同项目内该人员已是 manager 角色，不能再担任 EQCR（独立复核合伙人）」（= 任务 2.9 基线实测 `batch-eqcr-with-manager`）；0 条写语句；快照不变 |
| `test_write_error_returns_500_and_keeps_everything[member-row-midway]` | 世界引擎 `before_cursor_execute`：第 2 条 `project_users` 写语句按 DBAPI `OperationalError` 失败 | 500 `{"code":500,"message":"服务器内部错误"}`；首条写语句为软删旧委派；失败前已发出成员行写语句 1 条；快照不变 |
| `test_write_error_returns_500_and_keeps_everything[after-member-rows]` | 同上，第 1 条 `wp_visibility_policy_epoch` 写语句失败 | 500；失败前 3 条成员行写语句全部已发出；快照不变 |
| `test_commit_error_returns_500_and_keeps_everything` | 世界引擎方言 `do_commit`：先 DBAPI 回滚再抛 `OperationalError`（按 PG 语义，见偏差 1） | 500；提交前五张表都已发出写语句（成员行 3 条）；快照不变 |
| `test_save_without_injection_succeeds`（对照） | 不注入 | 200 `{"message":"已委派 3 名成员","count":3}`；旧现行委派 3 条软删、已删的历史委派逐列不变、现行委派恰为本批 3 条；u1 (auditor, edit) + `eqcr` → (partner, review)、u2 (manager, edit) + `质控` → (qc, review) 就地改写（范围与有效期不动），u3 新建 (partner, edit)，其余成员行逐列不变 |

上表每个用例另断言：生产 `get_db` 恰开 1 个会话；`perm:*` 命令 0 条；发往替身以外客户端的 Redis 命令 0 条。期望值取需求原文与 `tests/role_map_expected.py`，不读 `ROLE_MAP`。

D12 `perm:*` 记录器（需求 3.6、3.7 的缓存条款）：
- 装在 redis-py 命令入口的类属性上（异步 `Redis.execute_command`、`Pipeline.execute`，同步 `Redis.execute_command`、`Pipeline.execute`），记录后委托原实现：本进程任何客户端（不论经哪个名字取到）都经过；fakeredis 2.35.1 的 `FakeRedis` 不覆盖 `execute_command`。记录全部命令（含读）；按连接池判定是否发往本世界替身，不是则记录后拦下（不连真实 Redis）；任一参数含 `perm:` 即计为读写删。PubSub 不读写键，未装。
- 客户端名现读：保存链路唯一的 Redis 使用是 `broadcast_raw` → `_persist_raw_to_stream` → `get_redis()` → `_get_client()` 读模块全局 `_redis_client`（PING + XADD）；另一名字 `redis_client` 在全仓多为函数体内延迟导入。权限世界已把两个名字都换成本世界 fakeredis，测试断言二者 `is world.redis`。
- 正向对照 `test_perm_recorder_positive_control`：经 `redis_client` 与 `get_redis()` 发出的 SET、GET、管道 TTL + DEL、`SCAN MATCH perm:*` 全部记到（入口与顺序逐项相等）；替身以外的异步客户端 GET、同步 fakeredis DEL 也记到并拦下（异常文案逐字）；非 perm 命令只有 `get_redis()` 的 PING。成功对照里还记到保存链路自身的 `XADD sse:project:<目标项目>`（发往替身）。
- 灵敏度核对（不是需求 12.5 的磁盘变异证明；仓库外 pytest 插件在测试进程内存里改，不改文件，插件已删）：①委派同步后按改动 DEL `perm:{用户}:{项目}` → 3 failed（对照、after-member-rows、提交报错，均红在 `perm_commands() == []`），兼任校验与 member-row-midway 不经该路径照绿；②委派同步改在另开的会话里执行并立即提交 → 4 failed（after-member-rows 红在快照逐列不变；对照与 member-row-midway 红在会话数 2 == 1；提交报错红在写语句表集合——注入落在另开会话的提交上），兼任校验照绿。

需求 3.1（`pg_only`）`test_pg_only_deleted_member_rows_then_new_live_row`：权限世界 PG 版 + 补建三张表；前置断言临时 schema 内 `idx_project_users_project_user` 的 `indexdef` 以 `WHERE (is_deleted = false)` 结尾。用户在目标项目只有两条已删除成员行（(manager, edit) 带范围与有效期、(qc, review)），经端点保存一条 `partner` 委派 → 200 `{"message":"已委派 1 名成员","count":1}`；两条已删除行逐列不变；新建一条 (partner, edit)、未删除、范围与有效期为空；会话 1 个，`perm:*` 0 条。世界结束后另开连接核对：临时 schema 已不存在；public 下该用户 / 人员 / 目标项目在 `project_users`、`staff_members`、`project_assignments`、`notifications`、`projects` 中各 0 行。

测试命令（cwd `D:\wt_pm_impl\backend`，仓库外一次性启动器起子进程）：`D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_assignment_save_semantics.py -q -p no:cacheprovider --tb=short -rfEs`

| 运行 | 子进程环境 | 结果 |
|---|---|---|
| SQLite 轮（20:56:01 起） | 无 `DATABASE_URL` | 6 passed，1 skipped（`pg_only`），8.76 s |
| PG 轮（21:00:49 起） | `DATABASE_URL` = `settings.DATABASE_URL` 默认值（本机 `audit_platform`，只放进子进程 env，落盘输出替换为占位） | 7 passed，0 skipped，9.56 s |

PG 轮前后行数（postgres MCP 只读，21:00:36 / 21:01:28）：project_users 88 / 88、project_assignments 86 / 86、staff_members 215 / 215、users 94 / 94、projects 85 / 85、logs 94276 / 94276、evidence_outbox 738 / 738、notifications 778 / 778、wp_visibility_policy_epoch 59 / 59、wp_visibility_invalidation_outbox 159 / 159、wp_access_security_outbox 705 / 705、`authz_world_%` schema 0 / 0；logs、evidence_outbox、notifications、失效发件箱的最大 `created_at` 与 project_users、project_assignments 的最大 `updated_at` 前后相同（logs 最新仍是 11:53:59 UTC，即任务 4.1 已登记的那批）。本任务的其余运行（首轮、灵敏度核对、探针）都在 20:52~20:59，早于前一次核对，且五张表计数与任务 4.1 登记值相同 ⇒ 未在本地库留下任何行。

偏差与发现：
1. 首版提交注入只抛错不回滚，提交报错用例红：快照里成员行与发件箱「已落库」（首轮 20:52:44：5 passed，1 failed，1 skipped）。定位：SQLAlchemy 2.0.49 提交失败后事务留在连接上（`RootTransaction._do_commit` 只在提交成功时摘除），`Connection.close` 以 `transaction_reset=True` 归还连接、跳过连接池的复位回滚 ⇒ 不发 ROLLBACK；权限世界 SQLite 只有一条连接（StaticPool），未提交的写入被下一个会话（取快照）的 commit 带进库。仓库外探针实证：请求结束后同一连接上仍看得到 1 条未提交的发件箱行，ROLLBACK 后为 0。生产库是 PG：服务端拒绝 COMMIT 时整笔事务随之作废，不会留下待提交的写入 ⇒ 注入改为「先 DBAPI 回滚再报错」模拟 PG 语义，不判为生产缺陷。附带：design §4.3「写库 / 提交报错由 get_db 会话关闭回滚」对提交报错不成立——提交失败后关闭会话并不回滚，保存前的值靠 PG 作废失败的事务；写库报错由 flush 失败时的会话回滚保证。后续凡在 SQLite 权限世界里注入提交失败的任务须同样处理。
2. 兼任校验拒绝由真实输入触发（tasks 写作「注入」）；校验先于任何写入，该用例的「不变」是平凡成立，写入后回滚由另两种注入覆盖。
3. 测试应用比权限世界的裸应用多挂两个生产异常处理器（为得到生产形态的失败响应），仍不经 `ResponseWrapperMiddleware`，成功响应体未包装。
4. D12：需求 3.6 / 3.7 的缓存条款改为 `perm:*` 零读写删，本任务覆盖成功与三种失败；预置键与剩余 TTL 不变属性质 6（任务 14.3），未做。
5. 委派端点只校验登录（F16 / R1，范围外）本任务不改；请求以批次外的项目经理身份发出。

写法自查（需求 12.13）：无 skip / xfail（只有 `pg_only`）；两处 `pytest.raises` 块内各 1 条语句，其后逐字断言异常文案；无子进程；断言无「或」组合、无对多元素字面量的成员判断；monkeypatch 只换 redis-py 命令入口（记录后委托原实现）、`app.core.database.async_session`（会话工厂，只提供数据）、世界引擎方言的 `do_commit`（只在注入用例里报错）与当前用户 override，不替换任何门禁或判定函数；不是性质测试。临时文件（`D:\pm_tmp\t43_*`，含 PG 启动器、插件与探针）已删除。

### 任务 6.1：附注编辑门禁模块（2026-10-20）

改动文件（实施 worktree，LF）：

- 新增 `backend/app/services/note_edit_gate.py`：blob `facf36ff81b8f96fd37ba4efa4957f220251f7a5`，162 行（`split("\n")` 口径；行数门 splitlines 161；design §10 预计约 180，门槛 ≤ 800）。未改任何既有生产文件。
- `backend/tests/authz_world.py`（任务 3.1 新建）：`PRODUCTION_GATES` 追加附注编辑门禁三项（判定实现、路径依赖工厂、对象反查），`_GUARDED_MODULES` 加入 `app.services.note_edit_gate`；755 → 759 行（距 800 余 41 行，未拆分），blob `a6e5a303d77c583bcc461f7b5842876a20726af3` → `81cea9b55d73028dada6d4293479077c4b3b042c`。
- `backend/tests/test_authz_world.py`（任务 3.1 新建）：`test_gate_snapshot_is_the_production_code_of_this_tree` 的两个期望元组随登记补齐（`PRODUCTION_GATES` 7 项、`TRACED_GATES` 9 项，仍逐项相等）；480 → 487 行，blob `8ea4a00e180584645ff87fc902b71ccef9b2af61` → `539b4262dacd6b9cb779c046f61b8a7f05d2615a`。这两个文件不在基线 B 中，不属需求 12.8 的既有测试改写，不进「既有测试改写对照」表。

归属判断：权限世界登记不在 design 正文里，由 `authz_world.py` 模块说明与编排公共上下文规定「新增门禁形态时在 `PRODUCTION_GATES` 与 `_GUARDED_MODULES` 登记」。本任务新增这些形态，故在本任务内登记：design §8.2「不得替换附注编辑门禁各形态」从现在起由世界自检兜住（`world.stub` 拒绝给门禁模块里的对象打桩；`GateClient` 每次请求前核对三项仍是生产对象；`assert_passed` 可观测 `app.services.note_edit_gate.require_note_edit_access.<locals>.dependency`）。任务 6.3 的两个 design 定级形态由 6.3 自行登记。

公开名字与签名（`inspect.signature` 现取；三种形态的 `consol_lock` 都是无默认值的仅关键字参数）：

| 名字 | 签名 / 取值 |
|---|---|
| 常量（D13，均为普通赋值语句） | `NOTE_EDIT_MIN_LEVEL = "review"`；`NOTE_EDIT_OPERATION = "note:edit"`；`REASON_FORBIDDEN = "权限不足"`；`REASON_EQCR_READONLY = "独立复核合伙人（EQCR）在本项目只读，不能编辑附注"`；`REASON_OPERATION_DENIED = "您在本项目的角色没有编辑附注的操作权限"` |
| 判定实现 / 函数体形态 | `assert_note_edit_access(db: AsyncSession, current_user: User, project_id: UUID, *, consol_lock: bool) -> User` |
| 路径依赖形态 | `require_note_edit_access(*, consol_lock: bool) -> Callable[..., Awaitable[User]]`；内层 `dependency(project_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User` |
| 对象反查形态 | `assert_note_edit_access_for_object(db, current_user, *, id_column, project_column, object_id: UUID, not_found_detail: str, consol_lock: bool) -> UUID`（返回对象所属项目；签名无项目参数） |
| 取原因 | `note_edit_rejection_reason(exc: HTTPException) -> str`：str 原样；dict 取 `message`（须为 str）；其他形态抛 `ValueError` |
| 私有 | `_resolve_project_role(db, user_id, project_id)`：经模块属性调 `app.deps._resolve_project_role`；`_require_bool_consol_lock(consol_lock, *, caller)` |

判定顺序与拒绝分支（前一步拒绝即不再往下判）：

| 步 | 条件 | 状态码与 detail | 抛出方 |
|---|---|---|---|
| 0 | 对象反查形态：`select(project_column).where(id_column == object_id)` 无行 | 404，`not_found_detail` 原样（如「附注章节不存在」） | 本模块 |
| ① | 项目 `status == archived`（含 admin） | 423，`{"error_code": "PROJECT_ARCHIVED", "message": "项目已归档，无法编辑", "message_en": "Project archived (read-only)"}` | `assert_project_permission` → `_check_project_not_archived`（不变） |
| ② | 非 admin，无未删除成员行或级别 readonly | 403，`"权限不足"` | `assert_project_permission`（不变） |
| ③ | `is_project_eqcr` 为真（admin 不豁免） | 403，`{"error_code": "NOTE_EDIT_EQCR_READONLY", "message": REASON_EQCR_READONLY}` | 本模块 |
| ④ | 非 admin，`can(全局角色, 成员行项目角色, "note:edit")` 为假 | 403，`{"error_code": "NOTE_EDIT_OPERATION_DENIED", "message": REASON_OPERATION_DENIED}` | 本模块 |
| ⑤ | `consol_lock=True` 且 `projects.consol_lock` 为真 | 423，`"项目已被合并锁定，无法修改"` | `check_consol_lock`（不变） |
| — | 都不成立 | 放行，返回当前用户 | — |

结构（AST，探针现算）：模块 `try` 语句 0；`assert_note_edit_access` 顶层语句中恰 1 处 `assert_project_permission` 调用，第 4 个位置实参为 `NOTE_EDIT_MIN_LEVEL`（同文件赋值，值 `"review"`）；`is_project_eqcr` 在顶层赋值语句里调用；路径依赖内层 `dependency` 与对象反查形态都以顶层表达式语句调用判定实现；对象反查形态先 `select` 后调判定实现。

与设计的偏差（都不改变结论）：
1. ④ 对 admin 显式跳过（不查项目角色、不调 `can`）。design §4.6 代码块对所有人调 `can`，靠 `ROLE_OPERATIONS["admin"]` 含全部操作恒真；判定表 ④ 写「非 admin」，需求 6.13 写「操作矩阵对 admin 恒放行」。按判定表落地，admin 少一次查询。
2. 新增 `consol_lock` 取值校验（design 未写）：不是 bool（None、0、字符串）即 `TypeError`。路径依赖在工厂调用期（模块导入期）报错，函数体与对象反查在任何读库之前报错；口径同 `deps._validate_permission_level` 的 fail-closed。
3. `_resolve_project_role` 不另写查询，委托 `require_operation("note:edit")` 所用的 `deps._resolve_project_role`，矩阵口径不分叉；替换本函数或 deps 那一层都生效。
4. `note_edit_rejection_reason` 对 str / dict 以外的 detail 报错（design 只规定这两种），判定查询随之失败，不会返回没有原因的「不能编辑」。
5. 行数 162，design 估计约 180。

自检（仓库外一次性探针，已删；cwd `D:\wt_pm_impl\backend`，权限世界 SQLite 版；不替换任何门禁或判定，故障只注在 `_count_project_eqcr_assignments`）：134 项全部符合，0 项不符。
- 18 种情形 × `consol_lock` True / False × 三种形态（函数体直调、对象反查直调、路径依赖经 HTTP 真发请求）= 108 项，期望按需求 6.4~6.7、6.12、6.13 手写。情形：身份 ①~⑧；admin 持 `eqcr` 委派 → EQCR 403；readonly 成员持 `独立复核合伙人` 委派 → 「权限不足」（② 先于 ③）；全局 qc、(qc, review) 持 `eqcr` 委派 → EQCR 403（③ 先于 ④）；edit 成员与 admin 在合并锁定项目 → `consol_lock=True` 423、False 放行；全局 qc 成员、本项目 EQCR、非成员在合并锁定项目 → 各自的 403（403 先于 423）；非成员、本项目 EQCR 在已归档项目 → 归档 423（① 先于 ②③）。路径依赖另核：放行时业务恰 1 次、拒绝时 0 次；每个请求门禁闭包与判定实现各执行 1 次（`GateClient.gate_runs`）。
- 顺序旁证（世界引擎 `before_cursor_execute` 记录语句；先把目标项目移出会话，使归档守卫的 `db.get` 真发查询）：edit 成员 `consol_lock=True` 放行依次为 `projects` 整行 → `project_users.permission_level` → `count(project_assignments.id)` → `project_users.role` → `projects.consol_lock`；admin 依次为 `projects` → `count(project_assignments.id)` → `projects.consol_lock`；对象反查在最前多一条 `SELECT disclosure_notes.project_id …`。
- 对象反查：对象不存在 → 404「附注章节不存在」，全程只发 1 条语句；身份④对目标项目的对象 → 403「权限不足」，对其有权项目上的对象 → 放行（目标项目只取自对象）。
- 故障：`_count_project_eqcr_assignments` 抛 `RuntimeError` → 三种形态都抛出原异常，路径依赖业务 0 次。`consol_lock` 取 None / 0 / "False"：函数体与对象反查 `TypeError` 且 0 条语句，工厂 `TypeError`；工厂缺 `consol_lock` → `TypeError`。取原因：str、dict 逐字取回，list 抛 `ValueError`。

验证：
- cwd `D:\wt_pm_impl`：`D:\GT_plan\.venv\Scripts\python.exe -m ruff check --no-cache backend/app/services/note_edit_gate.py backend/tests/authz_world.py backend/tests/test_authz_world.py` → All checks passed!；`backend/scripts/check/check_file_size.py` 同三个文件 → 退出码 0。
- cwd `backend`（进程环境无 `DATABASE_URL`）：`D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_authz_world.py -q -p no:cacheprovider --tb=short -rfEs` → 53 passed，1 skipped（`pg_only`），9.86 s。引用权限世界的其余 6 个测试文件 `--collect-only -q` → 312 tests collected，0 错误（只收集不执行，确认世界导入时对新登记三项取快照不报错）。
- 本地库只读核对（postgres MCP，13:30 UTC）：`logs` 94276 行、最大 `created_at` 11:53:59 UTC，`evidence_outbox` 738 行，与任务 4.3 登记值相同；`authz_world_%` schema 0。

发现（未改，供后续任务判断）：`_GUARDED_MODULES` 不含 `app.services.permission_matrix_service`，`world.stub(permission_matrix_service, "can", ...)` 会被放行，并影响 `deps.require_operation`（函数体内延迟导入 `can`）；对本门禁无效（本模块自带 `can` 绑定，且已在 `_GUARDED_MODULES`）。留给 15.2 防假绿扫描一并考虑。

留给后续任务：函数级单元测试（6.2）；多项目与角色限定形态及其世界登记（6.3）；两处守卫的令牌登记与需求 6.10 可伪证断言（6.5）；端点改挂（10.x / 11.x）。

### 任务 6.2：门禁函数级单元测试（2026-10-20）

改动文件（实施 worktree，LF）：

- 新增 `backend/tests/test_note_edit_gate_unit.py`：blob `165e8b611a882fd972547a8647fbdb49d8d1fefb`，589 行（`split("\n")` 口径；splitlines 588；门槛 ≤ 800）。只写测试：生产文件与夹具未改，`note_edit_gate.py`（`facf36ff81b8f96fd37ba4efa4957f220251f7a5`）、`authz_world.py`（`81cea9b55d73028dada6d4293479077c4b3b042c`）、`test_authz_world.py`（`539b4262dacd6b9cb779c046f61b8a7f05d2615a`）运行前后 blob 不变。

做法：

- 三种形态都在权限世界 SQLite 版里调用。函数体与对象反查直接调用；路径依赖挂在本文件的最小测试路由上：`PUT /api/projects/{project_id}/note-edit-gate-unit/with-consol-lock` 与 `.../without-consol-lock`，分别 `Depends(require_note_edit_access(consol_lock=True / False))`，经 `world.client_for_app` 用 httpx 真发请求。路由的业务处理经 `world.stub` 换成计数桩。
- 替换范围：RLS（`world.replace_rls`）与测试路由的业务桩。故障只注在 EQCR 判定的下一层：函数层 monkeypatch `eqcr_resolver._count_project_eqcr_assignments`；驱动层替换本世界引擎方言实例的 `do_execute`，只对委派条数语句抛 DBAPI 错误。不用 `dependency_overrides` 替换门禁或判定，不调 `replace_archive_guard` / `replace_eqcr_query`。
- 期望值（状态码、detail、`note_edit_rejection_reason` 取回的原因）按需求 6.4~6.8、6.12 与 design §4.6 原文写死，不读 `REASON_*` 常量。
- autouse 守卫（沿用任务 4.3 写法）：经 `app.core.database.engine`（本地开发库）发出的语句一律拦下并判失败。

SQL 记录器与正向对照：

- `StepRecorder` 在世界引擎上挂 `before_cursor_execute`，把空白归一后的整句按形态归为 projection / archive / member / eqcr / matrix / consol_lock，其余记 `other: <前 80 字>`，同时记下绑定参数中的 UUID（SQLite 按 32 位十六进制绑定）。语句形态取自现读探针：projection `SELECT disclosure_notes.project_id FROM disclosure_notes WHERE disclosure_notes.id = ?`；archive 为 `db.get` 取 projects 整行；member `SELECT project_users.permission_level …`；eqcr `SELECT count(project_assignments.id) … JOIN staff_members …`；matrix `SELECT project_users.role …`；consol_lock `SELECT projects.consol_lock …`。
- 归档守卫用 `db.get`，项目对象在会话身份映射里时不发语句。每次判定前 `_forget_projects` 把会话里的 Project 对象移出，判定读库里的现值（与生产里每个请求一个新会话相同），结论不受影响。
- 正向对照 `test_step_recorder_positive_control`：依次执行对象投影（与门禁同一写法）、`deps._check_project_not_archived(..., "review")`、`deps._load_member_level`、`eqcr_resolver._count_project_eqcr_assignments`、`deps._resolve_project_role`、`deps.check_consol_lock` 和一条无关的 `SELECT users.id`；记录逐值等于七条（类别 + 绑定的项目 / 用户 id），最后一条为 other。路径依赖形态的放行用例另证明经 HTTP 发出的语句同样记得到。
- 全局角色为 eqcr 时 `is_project_eqcr` 直接返回、不发语句，这一步改由 `GateTrace`（PEP 669）计数。每个判定用例都断言：`assert_note_edit_access`、`assert_project_permission` 各执行 1 次；`is_project_eqcr` 走到第 ③ 步时 1 次，否则 0 次；对象反查形态 `assert_note_edit_access_for_object` 1 次；路径依赖形态内层 `dependency` 1 次。

用例清单（111 例）：

| 测试 | 例数 | 内容 | 需求 |
|---|---|---|---|
| `test_step_recorder_positive_control` | 1 | 记录器正向对照 | 12.1（判定步骤的可观测证据） |
| `test_order_and_verdict[<情形>-<body/object/path>]` | 90（30 情形 × 3 形态） | 结论逐值（状态码、detail、取回的原因；路径依赖另核响应体与业务桩 1 / 0 次）；执行过的步骤序列逐项相等 | 6.2~6.7、6.11（业务 0 次）、6.12 |
| `test_object_missing_is_404_after_the_only_projection[<身份>-<active/archived>]` | 8 | 对象不存在 → 404「附注章节不存在」；全程只有那一条投影，判定实现 0 次；已归档项目也先 404 | 6.1 第三项、6.7 末句、6.8 |
| `test_object_form_target_is_the_objects_project` | 1 | 签名逐参数（名字与种类）无项目参数；身份④对目标项目上的对象 403「权限不足」，各步绑定目标项目；对其有权项目上的对象放行、返回该项目，各步绑定该项目，RLS 只对该项目设置一次 | 6.8 第三项 |
| `test_path_form_target_is_the_path_project` | 1 | 路径依赖形态以路径参数为目标项目（身份④对目标项目 403，对另一项目放行） | 6.1（确定目标项目） |
| `test_review_and_edit_level_get_the_same_processing` | 1 | 同一用户的成员行由 review 改为 edit，两次请求的响应、业务桩参数（项目，本人 id）、步骤序列逐值相同 | 6.2 |
| `test_consol_lock_is_a_required_keyword[<三种形态>]` | 3 | `consol_lock` 是无默认值的仅关键字参数 | 6.6、design D1 |
| `test_eqcr_query_failure_propagates[<形态>-<query-function/driver>]` | 6 | 调用者为不出错时会放行的 edit 级成员；下层注入后异常原样冒泡（函数层 `is` 注入对象；驱动层为 `sqlalchemy.exc.OperationalError`，`orig` 即注入的 DBAPI 错误）；矩阵与合并锁两步未执行；路径依赖业务 0 次 | 7.6、6.11 |

30 个判定情形（期望步骤：A 归档 / M 成员 / E EQCR / X 矩阵 / L 合并锁；对象反查形态在前面多一个 P 投影）：

- ① 归档 423（A）：admin、非成员、readonly 成员、本项目 EQCR，以及已归档且合并锁定的 edit 成员（`consol_lock=True`）。
- ② 403「权限不足」（AM）：非成员、合并锁定项目上的非成员、readonly 成员、只有已删除成员行、readonly 成员持 `eqcr` 委派、全局 eqcr 非成员。
- ③ EQCR 只读 403：本项目 EQCR（AME），合并锁定项目上的本项目 EQCR（AME），`独立复核合伙人` 委派（AME），全局 qc 的 (qc, review) 成员持 `eqcr` 委派（AME，③ 先于 ④），全局 eqcr 的 (partner, review) 成员（AM，全局分支不发语句），admin 持 `eqcr` 委派（AE）。
- ④ 操作矩阵 403（AMEX）：全局 qc 的 (qc, review) 成员（含合并锁定项目），全局 readonly 的 (auditor, edit) 成员。
- ⑤ 合并锁 423：edit 成员（AMEXL）、admin（AEL）。
- 放行：edit 成员、(qc, review) 成员、全局 qc 的 (manager, edit) 成员（AMEXL）；admin 非成员、admin 带 (readonly, readonly) 成员行（AEL）；`consol_lock=False` 时合并锁定项目上的 edit 成员、review 成员（AMEX）与 admin（AE）。
- 需求 6.13 的 7 个固定样例都在其中：`archived-admin`、`non-member-locked`、`project-eqcr-locked`、`admin-with-eqcr-assignment`、`qc-global-qc-role`、`review-member`、`review-member-locked-without-lock-check`。

测试命令与结果（cwd `D:\wt_pm_impl\backend`；经 Python 子进程启动，子进程 env 去掉 `DATABASE_URL`、设 `PYTHONIOENCODING=utf-8`）：

- `D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_note_edit_gate_unit.py tests/test_authz_world.py -q -p no:cacheprovider --tb=short -rfEs` → 164 passed，1 skipped（`test_authz_world.py` 的 `pg_only`），13.34 s。新文件单独运行 111 passed。
- cwd `D:\wt_pm_impl`：`D:\GT_plan\.venv\Scripts\python.exe -m ruff check --no-cache backend/tests/test_note_edit_gate_unit.py` → All checks passed!；`backend/scripts/check/check_file_size.py backend/tests/test_note_edit_gate_unit.py` → 退出码 0。
- 首轮 108 passed、3 failed（`test_eqcr_query_failure_propagates[*-driver]`）：驱动层注入最初写在 `before_cursor_execute` 里，SQLAlchemy 不包装该事件里抛出的异常，冒泡的是原始 `sqlite3.OperationalError`，与断言的类型不符。属测试写法问题，改为替换方言实例的 `do_execute`（真实库报错的位置，SQLAlchemy 包成 `OperationalError`）后全绿。

灵敏度核对（进程内，不是磁盘变异）：仓库外一次性 pytest 插件在 `pytest_configure` 里改写 `assert_note_edit_access.__code__`（函数对象不变、源文件不动，权限世界导入时快照的就是改写后的代码），每种变异在子进程里跑一次新测试文件，用 junit 结果核对变红集合；插件与探针已删。

| 变异 | 期望红 | 实际红 | 失败落点 |
|---|---|---|---|
| 无（插件空跑对照） | 0 | 0 / 111 | — |
| 合并锁判定挪到最前 | 90：`consol_lock=True` 的 27 个情形 × 3 形态，加两个目标项目用例、review / edit 用例、6 个故障用例 | 90，与期望集合相等 | 步骤序列与记录的断言（第 461、499、516、542、588 行） |
| admin 不再跳过操作矩阵 | 12：admin 的 4 个非归档、非 EQCR 情形 × 3 | 12，相等 | 第 461 行，序列多出 matrix |
| 吞掉 EQCR 判定的异常、按非 EQCR 继续 | 6 个故障用例 | 6，相等 | 第 576 / 581 行，DID NOT RAISE |
| 忽略 `consol_lock` 参数、一律判合并锁 | 9：`consol_lock=False` 的 3 个情形 × 3 | 9，相等 | 第 461 行 |

- 每轮 error 0 个（收集、夹具错误都不计为变红），失败都是断言失败或 DID NOT RAISE。`note_edit_gate.py` 变异前后 blob `facf36ff…`、sha256 `baf562ba1c35ec84…` 不变。
- design §8.5 / 需求 12.5 的磁盘变异 ①② 归任务 19.3，本任务没有做磁盘变异，「变异证明」节无本任务条目。

副作用核对（postgres MCP 只读）：13:45:20 UTC（运行前）与 14:04:26 UTC（全部运行后）两次，`logs` 94276 行（最大 `created_at` 11:53:59 UTC）、`evidence_outbox` 738 行、`authz_world_%` schema 0，前后相同。

防假绿自查（供 15.2 扫描参照）：只 override `get_current_user` / `get_db`（世界自身）；monkeypatch 只落在 `_count_project_eqcr_assignments` 与方言 `do_execute`（下层）及世界的 RLS / 业务桩；`pytest.raises` 块内各一条语句，其后断言异常对象与信息；没有子进程、`skip` / `xfail`、hypothesis，断言里没有「或」组合与多元素字面量成员判断。

偏差：

1. 路径依赖形态用 `world.client_for_app` 而不是 `world.client`：`world.client` 只挂经 `router_registry` 生产注册的 router（`build_app` 拒绝未注册的），本任务用的是测试路由。`client_for_app` 同样只 override 当前用户与会话，并做「门禁是生产对象」自检与 `GateTrace` 观测。
2. EQCR 下层故障经 HTTP 时，异常由 ASGITransport 原样抛到测试（`raise_app_exceptions` 默认为 True），拿不到 500 响应体；「返回失败响应」的端点级断言在任务 14.2。
3. 函数层故障直接 monkeypatch `_count_project_eqcr_assignments`：世界的 `replace_eqcr_query` 只能返回固定条数，不能抛错。
4. 对象反查只用 `DisclosureNote` 测，`NoteValidationResult` 不在权限世界的六张表里。函数级以「签名无项目参数 + 目标项目只取自对象」证明另附项目标识不改变目标项目；在查询参数 / 请求体里另附项目的端点级用例在任务 10.2。
5. 未覆盖：`consol_lock` 取非 bool 时的 `TypeError`（任务 6.1 新增的 fail-closed 校验，不在 6.2 清单内）；未登录 401（端点级，任务 10.2）。

### 任务 6.3：design 定级形态（多项目与角色限定）（2026-10-20）

改动文件（实施 worktree，LF；只改了本 spec 新建的生产文件 `note_edit_gate.py`，未动其他生产文件）：

- `backend/app/services/note_edit_gate.py`：新增 `assert_note_edit_access_on_projects`、`assert_note_role_access`、私有 `_require_role_parameters`，常量 `REASON_MULTI_PROJECT_DENIED_PREFIX`、`_MULTI_PROJECT_COLLECTED_STATUSES`（403、423）、`_PROJECT_ROLE_VALUES`（`ProjectUserRole` 的 6 个取值）；模块说明补上两种形态，改写「调用位于顶层语句序列」与「出错语义」两段（模块里现在有 1 个 `try`，见下文「结构」）。162 → 274 行（`split("\n")` 口径，splitlines 273；design §10 预计约 180 行，门槛 ≤ 800），blob `facf36ff…` → `81948b317226fda58a74682c608c3c1efe8bf79b`。
- `backend/tests/authz_world.py`：`PRODUCTION_GATES` 追加两项，现共 9 项。`_GUARDED_MODULES` 在 6.1 已加入 `app.services.note_edit_gate`，本任务未改。759 → 762 行（距 800 余 38 行），blob `81cea9b5…` → `89d38fd613f4083a4e2bf3fcf1f3167eea35e1ea`。
- `backend/tests/test_authz_world.py`：`test_gate_snapshot_is_the_production_code_of_this_tree` 的两个期望元组按登记补齐，仍逐项相等（`PRODUCTION_GATES` 9 项，`TRACED_GATES` 11 项，两种新形态都没有内层闭包）。487 → 491 行，blob `539b4262…` → `9de0815abd3c33655d5da3b7fbf7c76555bd87b6`。
- `backend/tests/test_note_edit_gate_unit.py`（任务 6.2 新建）：模块说明加上角色限定形态，文末新增第六节（35 例）。589 → 737 行，blob `165e8b61…` → `d7b1ea97787ef7af0499d9cc2292f23812bae546`。
- 新增 `backend/tests/test_note_edit_gate_multi_project_unit.py`：多项目形态的函数级用例，21 例，280 行，blob `f3f8bdd22f4e3e47ae03c1f70fb48151c8dfb419`。
- 上面四个测试文件都不在基线 B 中，不属需求 12.8 的既有测试改写，不进「既有测试改写对照」表。Property 8 的性质测试（`test_note_multi_project_gate.py`）属任务 6.4，本任务没有写。

签名（`inspect.signature` 现取，与 design §4.6 的参数名、仅关键字参数一致）：

| 形态 | 签名 |
|---|---|
| 多项目 | `assert_note_edit_access_on_projects(db: AsyncSession, current_user: User, project_ids: Iterable[UUID], *, consol_lock: bool) -> User` |
| 角色限定 | `assert_note_role_access(db: AsyncSession, current_user: User, project_id: UUID, *, project_roles: frozenset[str], denied_message: str) -> User` |

多项目形态：

1. 先校验参数，此时还没有读库：`consol_lock` 不是 bool 抛 `TypeError`（沿用 `_require_bool_consol_lock`）；去重保序（`list(dict.fromkeys(project_ids))`）后为空抛 `ValueError`；有元素不是 `UUID` 抛 `TypeError`。
2. 逐项目调 `assert_note_edit_access(db, current_user, project_id, consol_lock=consol_lock)`。只接住 `HTTPException`：状态码为 403 或 423 时记入未通过清单，接着判下一个项目；其他状态码原样 `raise`。其他异常不接住，后面的项目也不再判。
3. 有项目未通过时整单拒绝。状态码：未通过清单里有 403 即 403，否则 423。detail 为 `{"error_code": "NOTE_EDIT_MULTI_PROJECT_DENIED", "message": "以下项目未通过附注编辑权限判定：" + "、".join(f"{项目 id}（{该项目单独判定的原因}）"), "project_ids": [项目 id 字符串, …]}`，按判定先后排列。原因经 `note_edit_rejection_reason` 取得，例如「权限不足」「独立复核合伙人（EQCR）在本项目只读，不能编辑附注」「项目已归档，无法编辑」「项目已被合并锁定，无法修改」。项目 id 以字符串写入，JSON 编码 UUID 会报错。拒绝时不重设 RLS。
4. 全部通过时，把 RLS 重设为去重后的首个项目：`await deps.set_rls_context(db, ordered[0])`，然后返回当前用户。RLS 的现有设置方式（现读）：封装在 `app.core.database.set_rls_context(session, project_id)`，PG 上执行 `set_config('app.current_project_id', …, true)`，SQLite 上直接返回。`app.deps` 导入了这个名字，`assert_project_permission` 每放行一个项目就经 `deps` 的模块全局名设置一次，所以逐项目判完后 RLS 落在末个项目上。重设也经 `deps.set_rls_context` 调用，与逐项目设置走同一个名字，没有另写实现。权限世界的 `replace_rls` 同时替换 `deps` 与 `core.database` 上的这个名字，测试里两种调用都会被记录。

角色限定形态：

1. 先校验声明，此时还没有读库：`project_roles` 不是 `frozenset` 抛 `TypeError`；含 `ProjectUserRole` 以外的取值（如拼错的 `manger`，或只出现在操作矩阵里的 `preparer`）抛 `ValueError`；`denied_message` 不是字符串，或去掉空白后为空，抛 `ValueError`。
2. 在顶层语句调判定实现：`assert_note_edit_access(db, current_user, project_id, consol_lock=False)`。归档 423、「权限不足」、EQCR 只读（admin 不豁免）与操作矩阵的拒绝都在这一步给出。
3. admin 放行。其他用户取 `_resolve_project_role`（委托 `deps._resolve_project_role`，即未删除成员行的项目角色），不属于 `project_roles` 就返回 403 `{"error_code": "NOTE_ROLE_REQUIRED", "message": denied_message}`。空集即仅 admin。非 admin 放行时项目角色点查两次：矩阵一步一次，角色判定一次。

结构（AST，探针现算）：

- 模块 `try` 语句 1 处（6.1 时为 0），在多项目形态里。
- 角色限定形态的顶层调用语句依次为 `_require_role_parameters`、`assert_note_edit_access`、`_resolve_project_role`。判定实现位于函数体顶层语句序列，任务 6.5 的「`assert_note_role_access` 必调判定实现」断言扫的就是它。
- 多项目形态的顶层调用语句为 `_require_bool_consol_lock`、`list`、`deps.set_rls_context`。判定实现的调用位于 for → try 内：for 的循环体只有这个 try，没有 break / continue / if；except 只写 `HTTPException`，处理器对 403 / 423 以外的状态码原样 raise。
- 为什么多项目形态不放在顶层：design §4.6 规定它「去重保序后对每个项目调判定实现，收集 403 / 423」，要逐项目调用并接住拒绝，只能写在循环里。任务 6.1 的「顶层语句序列」约定针对三种挂载形态，本任务沿用到角色限定形态；多项目形态按 design 以「去重后每个项目必判、只接 403 / 423」满足要求。design 规定清册把两个 design 定级形态识别为独立门禁形态，端点调用它们是否条件执行由清册在端点处判定，与门禁内部写法无关。

用例清单与需求对应（新增 56 例：`test_note_edit_gate_unit.py` 35 例 + `test_note_edit_gate_multi_project_unit.py` 21 例）：

| 测试 | 例数 | 内容 | 需求 |
|---|---|---|---|
| `test_role_access_order_and_verdict[<情形>]` | 28 | 角色限定形态直调。结论逐值核对（状态码、detail、取回的原因）；执行过的步骤按先后与期望序列逐项相等；`GateTrace` 计数：角色限定形态、判定实现、`assert_project_permission` 各 1 次，`is_project_eqcr` 走到第 ③ 步时 1 次 | 8.3（design §4.6、§4.8 表 B） |
| `test_role_access_signature_matches_design` | 1 | 参数名与种类逐个核对，`project_roles` / `denied_message` 是无默认值的仅关键字参数 | design §4.6 |
| `test_role_access_rejects_bad_declarations_before_any_query[set/str/misspelt/matrix-only-role/empty-message/blank-message]` | 6 | 声明校验：调用者是声明正确时会放行的 (manager, edit) 成员；报错信息含预期片段；0 条语句，判定实现 0 次 | 本任务新增的 fail-closed（见偏差 2） |
| `test_multi_project_verdict_and_error_body[<情形>]` | 12 | 多项目形态直调。判定实现执行次数等于项目数，遇到拒绝也判完全部项目；归档一步按项目先后各发一次；放行时 RLS 记录为逐项目设置 + 末尾重设为首个项目；拒绝时状态码与 detail 逐值核对（错误码、message、`project_ids`），`note_edit_rejection_reason` 取回 message，且不重设 RLS | 8.5 |
| `test_multi_project_dedups_keeping_first_occurrence_order` | 1 | 入参是生成器 `[P2, P1, P2, P3, P1]`：判定实现 3 次，成员一步依次绑定 P2、P1、P3；RLS 末尾重设为 P2 | 8.5（design「去重保序」） |
| `test_multi_project_lists_a_repeated_denied_project_once` | 1 | 未通过的项目重复出现 3 次：只判一次，message 与 `project_ids` 只列一次 | 8.5 |
| `test_multi_project_other_exceptions_propagate_as_is[query-error/http-503]` | 2 | 项目 1 先判为 403 并记下；项目 2 的 EQCR 委派条数函数（下一层）抛 `RuntimeError` 或 503 的 `HTTPException`：冒泡的就是注入的那个对象（`is`），信息逐字相等；判定实现 2 次、`is_project_eqcr` 1 次；项目 3 没有判；RLS 只有项目 2 逐项目判定时设置的那一次 | design §4.6「其他异常原样冒泡」，7.6 的出错语义 |
| `test_multi_project_signature_matches_design` | 1 | 参数名与种类，`consol_lock` 是无默认值的仅关键字参数 | design §4.6、6.6 |
| `test_multi_project_rejects_bad_arguments_before_any_query[no-project/id-string-as-sequence/string-element/consol-lock-none]` | 4 | 调用者是参数正确时会放行的 admin。报错信息含预期片段；0 条语句，判定实现 0 次，没有设置 RLS | 本任务新增的 fail-closed（见偏差 2） |

角色限定的 28 个情形。步骤代码：A 归档、M 成员、E EQCR、X 矩阵、R 角色判定自己的项目角色查询（与 X 同一语句形态）。文案取 design §4.8 原文，在下列四条之间轮换：「仅本项目经理或合伙人可切换附注模板类型」「仅本项目经理或合伙人可强制释放章节锁」「仅本项目经理或合伙人可锁定报表附注数据」「仅管理员可解除报表附注数据锁定」。

- 经理 / 合伙人集合 `{partner, manager}`（21 个情形）：
  - 放行（AMEXR）：(manager, edit)、(partner, edit)、无 EQCR 委派的 (partner, review)、全局 qc 的 (manager, edit)，以及合并锁定项目上的 (manager, edit)（不判合并锁）。
  - 403 `NOTE_ROLE_REQUIRED`（AMEXR）：(qc, review)、(auditor, edit)。
  - EQCR 先被排除，403 EQCR 只读：本项目 EQCR，即 (partner, review) 持 `eqcr` 委派（AME，项目角色 partner 在集合内照样拒绝）；`独立复核合伙人` 委派（AME）；全局 eqcr 的 (partner, review)（AM，全局分支不发语句）；admin 持 `eqcr` 委派（AE）。
  - readonly 与非成员先得「权限不足」（AM）：(manager, readonly)（项目角色 manager 在集合内也一样）、(readonly, readonly)、非成员、只有已删除的 (manager, edit) 行。
  - 操作矩阵 403（AMEX）：全局 qc 的 (qc, review)。
  - 归档 423（A）：(manager, edit)、admin。
  - admin 放行（AE）：非成员，以及带 (readonly, readonly) 成员行的 admin。
- 空集，即仅 admin（7 个情形，文案「仅管理员可解除报表附注数据锁定」）：
  - 放行（AE）：admin 非成员；合并锁定项目上的 admin。
  - 403 `NOTE_ROLE_REQUIRED`（AMEXR）：(manager, edit)；全局 partner 的 (partner, edit)。
  - 403 EQCR 只读：本项目 EQCR（AME）；admin 持 `eqcr` 委派（AE）。
  - 「权限不足」（AM）：(readonly, readonly)。
  - 归档 423（A）：已归档项目上的 admin。

多项目的 12 个情形（各项目依次为 P1 目标项目、P2 另一项目、P3 第三个项目）。每个项目上的情形：none 无成员行；edit (manager, edit)；readonly；eqcr 指 (partner, review) 持 `eqcr` 委派；archived / locked 指 (manager, edit) 且项目已归档 / 合并锁定。

- 放行：all-pass（edit × 3）；locked-without-lock-check（edit + locked，`consol_lock=False`）；admin-all-pass（admin，none + edit）。
- design §8.3 性质 8 的三个固定样例：全部通过即 all-pass；一个 403 + 一个 423 ⇒ 403，即 `one-423-one-403-is-403`（archived + none，两个都列出）；只有 423 ⇒ 423，即 `only-423-is-423`（archived + locked）。
- 其余拒绝情形：
  - `one-403-one-423-is-403`（none + archived）：403 不论先后。
  - `eqcr-is-403`（edit + eqcr）：EQCR 只读计为 403，只列 P2。
  - `readonly-and-archived-around-a-pass`（readonly + edit + archived）：403，列 P1、P3，通过的项目不列出。
  - `single-423-among-passes`（edit + locked + edit）：423，列 P2。
  - `single-project-403`（none）：403。
  - `admin-eqcr-and-archived-is-403`（admin，eqcr + archived）：403。
  - `admin-archived-is-423`（admin，none + archived）：423，列 P2。

测试命令与结果：

- cwd `D:\wt_pm_impl\backend`，经 Python 子进程启动（子进程 env 去掉 `DATABASE_URL`，设 `PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`）：`D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_note_edit_gate_unit.py tests/test_note_edit_gate_multi_project_unit.py tests/test_authz_world.py -q -p no:cacheprovider --tb=short -rfEs` → 220 passed，1 skipped（`test_authz_world.py` 的 `pg_only`，requires PostgreSQL），20.54 s。三个文件分别为 146（6.2 的 111 + 本任务 35）、21、53 passed。首轮即全绿，无改测试重跑。
- cwd `D:\wt_pm_impl`：`D:\GT_plan\.venv\Scripts\python.exe -m ruff check --no-cache` 五个改动文件 → All checks passed!；`backend/scripts/check/check_file_size.py` 同五个文件 → 退出码 0。

灵敏度核对（进程内改写，不是磁盘变异）：

- 做法：仓库外的一次性 pytest 插件在 `pytest_configure` 里改写目标函数的 `__code__`。函数对象不变，源文件不动；改写后的代码按真实路径编译，权限世界导入时快照的、`GateTrace` 观测的都是改写后的代码。每轮记录 `authz_world_preloaded=False`，证明世界在改写之后才导入。
- 每种改写在子进程里跑两个单元测试文件（167 例），用 junit 结果核对变红集合。插件、驱动与 junit 文件都已删除。

| 改写 | 期望红 | 实际红 | 失败落点 |
|---|---|---|---|
| 无（插件空跑对照） | 0 | 0 / 167 | — |
| 多项目：状态码取首个未通过项目的结论（不按「有 403 即 403」） | 1：`one-423-one-403-is-403` | 1，与期望相等 | 状态码 423 != 403 |
| 多项目：遇到第一个未通过的项目即停（`break`） | 9：情形中未通过项目之后还有项目的 6 个，加上重复未通过用例、冒泡用例 2 个 | 9，与期望相等 | 判定次数（如 1 != 2）、detail，以及冒泡用例里抛出的是整单拒绝 |
| 多项目：接住任意状态码的 `HTTPException` | 1：冒泡用例 `[http-503]` | 1，与期望相等 | 冒泡的不是注入的那个对象 |
| 多项目：不去重 | 2：去重用例、重复未通过用例 | 2，与期望相等 | 判定次数 5 != 3、4 != 2 |
| 多项目：全部通过后不重设 RLS | 4：3 个放行情形 + 去重用例 | 4，与期望相等 | RLS 记录少了末尾一条 |
| 多项目：去掉空列表与 UUID 校验 | 3：`no-project`、`id-string-as-sequence`、`string-element` | 3，与期望相等 | 抛出的是 `IndexError` / `StatementError`，不是预期异常 |
| 角色限定：不调判定实现 | 28（全部角色情形） | 28，与期望相等 | 步骤序列 |
| 角色限定：admin 不提前放行 | 4（admin 放行的 4 例） | 4，与期望相等 | 序列多出一步 R |
| 角色限定：调判定实现时传 `consol_lock=True` | 13（走到第 ⑤ 步的 9 个放行情形 + 4 个角色不符情形） | 13，与期望相等 | 序列多出 consol_lock |
| 角色限定：删去「项目角色不属于集合 → 403」 | 我写的期望是 9，写错了 | 4，正好是 4 个角色不符的情形；期望里多写的 5 例都是非 admin 放行情形 | 返回 `User`，不是 `HTTPException` |
| 角色限定：去掉声明校验 | 6 | 6，与期望相等 | DID NOT RAISE / 抛出意外的 `HTTPException` |

- 「删去角色判定」一行：改写只删了 if / raise，项目角色查询仍在，所以非 admin 放行情形的步骤序列不变，本就应该保持绿。实际变红集合就是 4 个角色不符的情形，没有意外变红（unexpected 为空），测试本身没有缺口。
- 每轮 error 都是 0：收集错误、夹具错误不计为变红，失败都是断言失败、DID NOT RAISE 或抛出了非预期异常。
- `note_edit_gate.py` 在改写前后 blob 都是 `81948b31…`，sha256 都是 `5dd64a3a7bdd9c9e…`，没有变化。
- design §8.5 的磁盘变异清单里没有本任务的条目，所以「变异证明」节不写本任务。

副作用核对（postgres MCP，只读）：

- 运行前（14:26:58 UTC）：`logs` 94279 行，`evidence_outbox` 738 行，`authz_world_%` schema 0 个。`logs` 比 6.2 登记的 94276 多 3 行，是 14:24:31 UTC 的三条 create（object_type `m7-special-reserve`），早于本任务第一次运行，属并发会话。
- 全部运行后（14:35:36 UTC，含灵敏度核对的 12 轮）：仍为 94279 / 738 / 0，`logs` 最大 `created_at` 仍是 14:24:31 UTC。

防假绿自查（供任务 15.2 扫描参照）：

- 没有经 HTTP 的用例，没有 `dependency_overrides`。
- monkeypatch 只落在下一层的 `_count_project_eqcr_assignments` 和世界的 RLS 记录上，没有替换任何门禁或判定函数，也没用 `replace_archive_guard` / `replace_eqcr_query`。
- 每个 `pytest.raises` 块内只有一条语句，块后都断言了异常对象或信息。
- 没有子进程、`skip` / `xfail` 或 hypothesis。
- 断言里没有「或」组合，也没有对多元素字面量的成员判断。
- 期望值（错误码、文案、状态码、角色集合）都在测试里写死，不读 `REASON_*` 等生产常量。

偏差：

1. 多项目 message 的写法：design 只规定「中文 message 列出未通过的项目 id」，没给原文。实现取前缀「以下项目未通过附注编辑权限判定：」，后面逐个列「项目 id（该项目单独判定的原因）」，以「、」连接。原因都是固定中文，满足 6.11。测试按这个写法写死，任务 6.4 的模型可以照此对拍，也可以只比状态码与 `project_ids`。
2. 新增参数校验（design 未写），都在任何读库之前报错，口径同 6.1 的 `_require_bool_consol_lock`：
   - 多项目：空列表报 `ValueError`（不判任何项目就放行等于没有门禁）；元素不是 `UUID` 报 `TypeError`（去重按 UUID 取值，误把单个 id 字符串当序列传入也不会按字符逐个判定）。
   - 角色限定：`project_roles` 不是 frozenset 报 `TypeError`（误传字符串会按子串判定，`"qc" in "eqcr"` 为真）；含未登记的角色报 `ValueError`（拼错的角色名会让限定静默变成仅 admin）；`denied_message` 为空报 `ValueError`。
3. 多项目形态遇到状态码不是 403 / 423 的 `HTTPException`，按「其他异常」原样冒泡。design 原文是「收集 403 / 423」「其他异常原样冒泡」，本条按原文落地。
4. 角色限定形态调判定实现时传 `consol_lock=False`。design 签名里没有这个参数；表 B 用这一形态的端点（模板互转的执行与撤销、强制释放、锁定、解锁）改造前都只校验登录，按 6.6「新纳入的端点一律 `consol_lock=False`」处理。
5. 多项目的函数级用例没有写进 `test_note_edit_gate_unit.py`。加上角色限定用例后该文件已 737 行，再加约 280 行多项目用例就超过 800 行门槛，所以按「单项目形态 / 多项目形态」的边界放进新文件 `test_note_edit_gate_multi_project_unit.py`。它与任务 6.4 的性质测试文件 `test_note_multi_project_gate.py` 不同名，也不含性质测试。任务原文列出的四类角色限定用例（经理 / 合伙人集合、空集仅 admin、EQCR 先被排除、readonly 先得「权限不足」）都在 `test_note_edit_gate_unit.py` 里。新文件从 `test_note_edit_gate_unit.py` 导入 `StepRecorder`、`_forget_projects` 与观测名常量；autouse 开发库守卫和 `world` 夹具在新文件里按同样写法另写一份，没有跨模块导入夹具。
6. 行数：design §10 预计 `note_edit_gate.py` 约 180 行，实为 274 行，多出的是两种形态的说明与参数校验。

留给后续任务：

- 6.4 / 6.5 用到的名字与 design 一致：`assert_note_edit_access_on_projects`、`assert_note_role_access`、`NOTE_EDIT_MULTI_PROJECT_DENIED`、`NOTE_ROLE_REQUIRED`。
- 11.2 ~ 11.4 改端点时，调用写法按真实签名：`project_roles=frozenset({...})`、`denied_message="…"` 是仅关键字参数，传集合字面量会报 `TypeError`。design §4.8 表里的 `assert_note_role_access({manager, partner}, "…")` 是省略了参数名的简写。

### 任务 6.4：多项目判定的性质测试（2026-10-20）

改动文件（实施 worktree，LF；只新增一个测试文件，未改生产代码，也未改 6.2 / 6.3 的两个测试文件与 `authz_world.py`）：

- 新增 `backend/tests/test_note_multi_project_gate.py`：Property 8 的性质测试与三个固定样例，412 行（`split("\n")` 口径，splitlines 411；上限 800），blob `86e010866bb7b166a4ee0b9a73a63d4b14013030`。不在基线 B 中，不属需求 12.8 的既有测试改写。
- 只导入、不改：`test_note_edit_gate_unit.py` 的 `StepRecorder`、`_forget_projects`、观测名 `IMPL`，以及按需求原文写死的五个拒绝期望 `ARCHIVED` / `FORBIDDEN` / `EQCR_READONLY` / `OPERATION_DENIED` / `CONSOL_LOCKED`；`test_note_edit_gate_multi_project_unit.py` 的 `THIRD_PROJECT_ID`、`PREFIX`、`ERROR_CODE`、`MULTI`、`_judged`；`role_map_expected.EXPECTED_EQCR_ALIASES`；`authz_world` 的 `sqlite_world`、`WORLD_TABLES` 与固定 id。
- 6.3 的 `_arrange` 只支持 3 个项目、6 种合成情形，本任务另写造数函数，第 4 个项目 `5a1d0c3e-7b2f-4e61-9c84-2f0d6b9a1e12` 按同法另建。开发库守卫按 6.2 / 6.3 的写法另写一份，没有跨模块导入夹具。

测试标识：

| 测试 | 例数 | 内容 |
|---|---|---|
| `test_property_8_multi_project_gate_rejects_whole_request` | 1（hypothesis：5 个生成样例 + 2 个 `@example`） | `@settings(max_examples=5, deadline=None)`；函数头注释 `# Feature: partner-manager-edit-permission, Property 8: 多项目判定整单拒绝` |
| `test_property_8_fixed_examples[all-pass/one-403-one-423-is-403/only-423-is-423]` | 3 | design §8.3 的三个固定样例：先核对模型与手写的整单结论、未通过项目一致，再跑全部断言 |

做法：每个样例新建一个 SQLite 权限世界（`pytest.MonkeyPatch.context()` + `sqlite_world`，与 Property 2 / 9 一样用 `asyncio.run` 逐样例运行），经最小测试端点真发一次请求。端点在函数体顶层先调多项目形态（两条路由，`consol_lock` 各写一个字面量），通过后才执行业务：给请求涉及的每个项目各插一条附注，并记下调用。只替换当前用户、数据库会话（`client_for_app`）与 RLS 设置；门禁与各步判定都不替换，不打桩，`dependency_overrides` 只有 `get_current_user` 与 `get_db`。

生成器（design §8.3）：

- 项目数 1~4；调用者全局角色取全部 7 个取值。
- 每个项目上各自随机取：是否归档、是否合并锁定、成员行（无 / 已删除 / 未删除；级别 readonly / review / edit × 项目角色 partner / manager / qc / auditor / readonly）、本项目现行委派（无 / `eqcr` / `独立复核合伙人` / 不是 EQCR 别名的 `manager`）。
- 端点是否判合并锁随机；请求里的项目先随机排列，再在任意位置插入 0~2 个重复项。
- 本次运行的统计（`--hypothesis-show-statistics`）：5 passing / 0 failing / 0 invalid；整单 403 两例、423 两例、放行一例；涉及项目数 1 个一例、2 个三例、4 个一例。生成器每次运行随机，统计只代表这一次。
- 两个 `@example`（结论按模型核对）：E1 为全局 qc、`consol_lock=False`、4 个项目且请求重复，EQCR 中文别名、操作矩阵、只有已删除成员行三种 403 各一个，合并锁定的项目因不判锁照样通过 ⇒ 403；E2 为 admin、3 个项目，非成员 + 非 EQCR 委派通过，readonly 行 + 合并锁定得 423，归档 + `eqcr` 委派得 423（归档先于 EQCR）⇒ 423。

固定样例（项目依次为 P1 目标项目、P2 另一项目、P3 第三个项目、P4 第四个项目；全局 auditor，`consol_lock=True`）：

- `all-pass`：P1 (manager, edit)、P2 (qc, review)、P3 (partner, review) 持非 EQCR 的 `manager` 委派、P4 (auditor, edit)；请求为 [P4, P2, P1, P4, P3, P2] ⇒ 放行。同时是零写入观测的正向对照。
- `one-403-one-423-is-403`：P1 已归档（423）、P2 通过、P3 非成员（403）⇒ 403，列 P1、P3。423 排在前，中间夹一个通过的项目。
- `only-423-is-423`：P1 通过、P2 已归档、P3 合并锁定 ⇒ 423，列 P2、P3。

模型（不调用任何被测判定函数，也不读 `REASON_*` 等生产常量）：

- 单个项目：按需求 6.13 的先后取第一个成立的拒绝。依次是：归档 423（6.7，含 admin）；非 admin 且没有未删除成员行或级别为 readonly，403「权限不足」（6.4）；全局 eqcr 或持本项目 EQCR 别名委派，403 EQCR 只读（6.5、7.1，admin 不豁免）；非 admin 且全局角色不在 {partner, manager, auditor}、项目角色不在 {partner, manager}，403 操作矩阵（6.12）；`consol_lock` 为真且项目合并锁定，423（6.6）。
- 操作矩阵的两个集合按需求 6.12 与 Q1（矩阵内容不改）手写；EQCR 别名取需求 2.5 期望表。
- 整单（需求 8.5）：按首次出现去重保序后逐项目判定。全部通过即放行；否则有 403 即 403，否则 423。`project_ids` 为未通过的项目，按判定先后。message 用 6.3 钉住的写法（前缀 + 「项目 id（原因）」，以「、」连接）。断言逐值比较整个响应体。

断言（每个样例都跑）：

1. 多项目形态执行 1 次，判定实现执行次数等于去重后的项目数（`GateTrace`）；归档一步的语句按去重后的先后各发一次（`StepRecorder`，判定前把项目对象移出会话）。
2. 拒绝：请求前后六张表的全部行逐值相同；业务调用 0 次；`(状态码, 响应体) == (模型状态码, {"detail": 模型 detail})`。
3. 放行：业务恰 1 次，参数为请求原样的项目清单与调用者本人；响应 `(200, {"saved": True})`；附注表以外五张表、既有附注都逐值不变；新增附注恰为每个涉及的项目各一条，内容为业务写入的标记。

零写入观测及其正向对照：

- 观测：请求前后各取一次权限世界六张表的全部行（按主键排序、逐列取值）。快照在同一会话里取，业务 flush 后未提交的写入也看得到。拒绝时要求逐值相同，且业务调用 0 次。
- 正向对照：放行时同一观测看得到业务写入（`all-pass`，以及生成样例里的放行情形），所以拒绝时的「不变」不是看不见。
- 灵敏度核对的 M4 也证明这一点：把实现改成「全部项目都未通过才拒绝」后，`one-403-one-423-is-403`、`only-423-is-423` 都红在「拒绝后权限世界的数据变了」，差异项是 `disclosure_notes`。
- 开发库守卫（autouse）：不得经 `app.core.database.engine` 发任何语句，全部运行均未命中。

测试命令与结果：

- cwd `D:\wt_pm_impl\backend`，经 Python 子进程启动（子进程 env 去掉 `DATABASE_URL`，设 `PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`，`HYPOTHESIS_STORAGE_DIRECTORY` 指向 `D:\pm_tmp` 下的临时目录）：`D:\GT_plan\.venv\Scripts\python.exe -m pytest tests/test_note_multi_project_gate.py tests/test_note_edit_gate_unit.py tests/test_note_edit_gate_multi_project_unit.py -q -p no:cacheprovider --tb=short -rfEs --hypothesis-show-statistics` → 171 passed（4 + 146 + 21），9.75 s。新文件第一次单独运行即 4 passed；之后只在性质测试里加了两行 `hypothesis.event`（只进统计，不参与判定），再与两个单元测试文件同跑得到上述结果。没有因失败而改测试。
- cwd `D:\wt_pm_impl`：`D:\GT_plan\.venv\Scripts\python.exe -m ruff check --no-cache backend/tests/test_note_multi_project_gate.py` → All checks passed!；`backend/scripts/check/check_file_size.py` 同文件 → 退出码 0。

灵敏度核对（进程内改写，不是磁盘变异）：

- 做法同任务 6.3：仓库外一次性 pytest 插件在 `pytest_configure` 里改写 `assert_note_edit_access_on_projects` 的 `__code__`，函数对象不变，按真实源文件路径编译。每轮都记录 `authz_world_preloaded=False`，`app` 解析到 worktree。
- 每种改写在子进程里单独跑新文件（4 例，`--hypothesis-seed=0`），按 junit 结果核对。
- 任务 6.5 在并行运行导入 `note_edit_gate.py` 的测试，所以没有改磁盘：改写前后 blob 都是 `81948b31…`，sha256 都是 `5dd64a3a…`。

| 改写 | 期望红（固定样例） | 实际红（固定样例） | 失败落点 | 性质测试 |
|---|---|---|---|---|
| 无（插件空跑对照） | 0 | 0 / 4 | — | 绿 |
| M1 状态码取首个未通过项目的结论 | `one-403-one-423-is-403` | 与期望相等 | 状态码 423 != 403 | 红（生成样例） |
| M2 状态码恒为 403 | `only-423-is-423` | 与期望相等 | 状态码 403 != 423 | 红（E2） |
| M3 遇到首个未通过的项目即停 | 403+423、只有 423 两例 | 与期望相等 | 判定实现次数 1 != 3、2 != 3 | 红（E2） |
| M4 全部项目都未通过才拒绝 | 403+423、只有 423 两例 | 与期望相等 | 「拒绝后权限世界的数据变了」，`disclosure_notes` 多出业务写入的行 | 红（E2） |
| M5 `project_ids` 列出全部项目 | 403+423、只有 423 两例 | 与期望相等 | detail 不等 | 红（E2） |
| M6 `consol_lock` 不下传（恒 False） | `only-423-is-423` | 与期望相等 | detail 只列 P2 | 红（E2） |
| M7 不去重 | `all-pass` | 与期望相等 | 判定实现次数 6 != 4 | 红（E1，5 != 4） |
| M8 只收集 403（423 原样冒泡） | 403+423、只有 423 两例 | 与期望相等 | 判定实现次数 1 != 3、2 != 3 | 红（E2） |

- 每轮 error 都是 0：失败都是断言失败，没有收集、导入或夹具错误。
- 应红集合只按固定样例定。性质测试一栏是实际观察到的结果，括号里是 hypothesis 报告的样例：M1 靠固定种子下的生成样例，其余靠 `@example`。
- 插件、驱动、junit 与 hypothesis 临时目录都已删除。design §8.5 的磁盘变异清单里没有本任务的条目，「变异证明」节不写本任务。

副作用核对（postgres MCP，只读）：

- 运行前（14:55:28 UTC）：`logs` 94280 行，`evidence_outbox` 738 行，`authz_world_%` schema 0 个。比 6.3 登记的 94279 多 1 行，是 14:55:01 UTC 的 `editing-lock` create，早于本任务第一次运行（约 15:00 UTC）。
- 全部运行后（15:08:43 UTC）：94290 / 738 / 0。新增的 10 行（14:57:01 ~ 15:08:10 UTC）都来自共享开发服务：`ip_address` 127.0.0.1，同一真实用户 `b6f8e8d0…`；对象类型 `editing-lock` 8 行、`ai-chat` 1 行、`m7-special-reserve` 1 行，属并发会话。本任务的测试只连 SQLite 内存库，开发库守卫没有命中。

防假绿自查（供任务 15.2 扫描参照）：

- 没有替换门禁或判定函数，没有用 `replace_archive_guard` / `replace_eqcr_query`，没有 `world.stub`：业务是测试端点里自己写库的代码。
- 没有 `pytest.raises`、子进程、`skip` / `xfail`。
- 断言里没有「或」组合，也没有对多元素字面量的成员判断。
- 期望文案、状态码与角色集合都在测试里写死，或取自测试侧期望表。

偏差：

1. 期望 message 按 6.3 钉住的写法逐字比较。design 只规定「中文 message 列出未通过的项目 id」，以后改 message 写法，本测试会与 6.3 的单元测试一起红。
2. 生成器比任务原文多了四个维度：已删除成员行、非 EQCR 委派干扰项、操作矩阵拒绝、请求里项目重复。模型同步覆盖。
3. 「数据写入」的观测范围是权限世界的六张表。被测路径只用调用方传入的会话；经独立会话或正式引擎发出的语句由开发库守卫拦下，全部运行均未命中。
4. 零写入经最小测试端点观测，不是生产端点。表 B 的真实端点（任务 11.2、11.4 改造的集团基线保存与集团模板下发）由任务 11.x 的端点级测试覆盖。

### 任务 6.5：两处守卫登记附注编辑门禁并加可伪证断言（2026-10-20）

改动文件（实施 worktree；两个都是基线 B 里的既有测试文件，保持 CRLF；没有改生产代码，没有新建文件）：

- `backend/tests/test_project_endpoint_authorization_baseline.py`：`_PROJECT_LEVEL_TOKENS` 17 → 20 项（末尾追加 `require_note_edit_access`、`assert_note_edit_access`、`assert_note_role_access` 与来源注释）；文末新增一节（`_NOTE_GATE`、`_NOTE_GATE_FACTS`、`_note_gate_facts` 与 2 个测试函数，共 4 例）。737 → 778 行（行数门 splitlines 口径；不在白名单，上限 800，余 22），blob `abaf59b3…` → `dce02ca96c50984ab5773f06ec0cac4593eda7c0`。
- `backend/tests/test_disclosure_notes_project_gate_contract.py`：模块说明末尾补一段；文末新增一节（`NOTE_GATE_PATH`、AST 判定函数 `note_gate_ast_facts` 及 4 个私有辅助函数、`TestNoteEditGateIsFalsifiable` 2 例、合成样例自检 17 例）。326 → 528 行，blob `88404643…` → `bc10d8a603c90f2b41798b080eb560e39496aded`。`BODY_GATES` / `DEPENDS_GATES` / `CASES` / 「反查先于鉴权」未动（任务 10.1）。
- `note_edit_gate.py` 全程未改：blob `81948b317226fda58a74682c608c3c1efe8bf79b`、sha256 `5dd64a3a7bdd9c9e…`，运行前后相同。

登记口径（现读确认）：基线守卫三处判档都是前缀匹配 —— `_has_auth`（经 `_AUTH_TOKENS`）、`_scan_identity_only`、前缀维的 `_matches` 都写 `n == t or n.startswith(t)`。所以 `assert_note_edit_access` 一项同时覆盖 `assert_note_edit_access_for_object` 与 `assert_note_edit_access_on_projects`；`require_note_edit_access`、`assert_note_role_access` 不以它开头，各自登记。现算路由里引用这三个名字的端点为 0（端点改挂在 10.x / 11.x），所以这次登记不改变任何档位（见下文现算计数）。

新断言（全部按 AST：注释不进 AST，docstring 与其他字符串是 `Constant`，不产生调用节点）：

| 文件 | 测试标识 | 判定 | 需求 |
|---|---|---|---|
| 基线守卫 | `test_note_edit_gate_tokens_are_really_project_level[permission]` | 判定实现 `assert_note_edit_access` 无条件 await `assert_project_permission`，级别实参为 review | 6.10 ① |
| 基线守卫 | `test_note_edit_gate_tokens_are_really_project_level[eqcr]` | 判定实现无条件 await `is_project_eqcr` | 6.10 ② |
| 基线守卫 | `test_note_edit_gate_tokens_are_really_project_level[role]` | `assert_note_role_access` 在任何 return 之前无条件 await 判定实现 | 任务原文「必调判定实现」（8.3 形态的前提） |
| 基线守卫 | `test_note_gate_facts_can_fail` | 反向自检：不满足的合成源码三条 == 全 False | 本文件能独立打红 |
| 契约守卫 | `TestNoteEditGateIsFalsifiable::test_requires_review_membership_unconditionally` | 同 ① | 6.10 ① |
| 契约守卫 | `TestNoteEditGateIsFalsifiable::test_calls_eqcr_judgment` | 同 ② | 6.10 ② |
| 契约守卫 | `test_note_gate_ast_facts_on_samples[<样例名>]`（17 例） | 合成样例 (permission, eqcr, role) == 期望三元组 | 判定函数两个方向都给对 |

判定口径（`note_gate_ast_facts`，写在契约守卫里；基线守卫在测试函数内延迟导入复用。两个文件各读自己的路径常量，失败信息各自写明）：

- 「无条件」：函数体顶层、第一条含 `return` 的语句之前，形如 `await f(...)` / `x = await f(...)` / `x: T = await f(...)` 的按名调用。if / try / for / while / with 里的调用、排在可能提前 return 的语句之后的调用、没有 await 的调用都不算。
- ① 的级别实参：第 4 个位置实参或 `min_permission=`，恰好一个；是字面量 `"review"`，或同文件常量（模块级单目标赋值、值为字面量 `"review"`、全模块只有这一处绑定，再赋值、同名形参、`del` 都算另一处绑定）。省略级别（落到默认 readonly）即不成立。
- 被调的必须是真的那一个：`assert_project_permission` 全模块只绑定于 `from app.deps import …`；`is_project_eqcr` 只绑定于 `from app.services.eqcr_resolver import …`（需求 7.3 的唯一 EQCR 判定）；`assert_note_edit_access`、`assert_note_role_access` 都须是全模块唯一绑定的模块级 `async def`。被同名定义、赋值或导入覆盖即不成立。
- 现源码三条都成立：判定实现顶层依次为 `_require_bool_consol_lock(...)`（未 await，不计）、`await assert_project_permission(db, current_user, project_id, NOTE_EDIT_MIN_LEVEL)`、`is_eqcr = await is_project_eqcr(...)`，第一条含 return 的语句是末尾的 `return current_user`；角色限定形态的 `await assert_note_edit_access(..., consol_lock=False)` 在 `if admin: return` 之前。
- 合成样例 17 个：正向 `constant-level`、`keyword-literal-level`、`role-runs-judgment`；① 不成立 `edit-level`、`default-level`、`permission-inside-if`、`permission-inside-try`、`permission-not-awaited`、`permission-shadowed`、`level-rebound`；② 不成立 `eqcr-deleted`、`eqcr-inside-if`、`eqcr-redefined`；role 不成立 `role-skips-judgment`、`role-returns-before-judgment`；① ② 都不成立 `after-early-return`、`mentioned-only-in-docstring-and-comment`（调用只出现在 docstring 和注释里）。

变异实测（源码副本，不是磁盘变异）：

- 做法：仓库外的一次性驱动把 `note_edit_gate.py` 读进内存，按精确锚点改写（每个锚点先断言恰好出现 1 次），写成 `D:\pm_tmp\` 下的副本；仓库外的一次性 pytest 插件在 `pytest_collection_modifyitems` 里把两个守卫模块的路径常量 `_NOTE_GATE`、`NOTE_GATE_PATH` 指向该副本，并把实际改了哪些名字写进旁证文件（同时跑两个文件的每一轮都是这两项）。每轮在子进程里只跑 5 个读真实源码的用例（基线 3 例 + 契约 2 例），用 junit 结果核对变红集合。驱动、插件、副本与 junit 都已删除。
- 下表 B[x] = 基线守卫 `test_note_edit_gate_tokens_are_really_project_level[x]`，C① / C② = 契约守卫 `TestNoteEditGateIsFalsifiable` 的两例。

| 变异 | 期望红 | 实际红 | 失败落点 |
|---|---|---|---|
| M00 原样副本（插件对照） | 无 | 无（5 passed） | — |
| M01 `NOTE_EDIT_MIN_LEVEL = "edit"` | B[permission]、C① | 相同 | 两条 ① 的失败信息 |
| M02 删去 EQCR 判定调用（改为 `is_eqcr = False`） | B[eqcr]、C② | 相同 | 两条 ② 的失败信息 |
| M03 `assert_project_permission` 调用挪进 `if 非 admin:` | B[permission]、C① | 相同 | ① |
| M04 角色限定形态不调判定实现（该行换成 `pass`） | B[role] | 相同 | role |
| M05 调用包进 `try: … except HTTPException: raise` | B[permission]、C① | 相同 | ① |
| M06 去掉 await | B[permission]、C① | 相同 | ① |
| M07 省略级别实参（落到默认 readonly） | B[permission]、C① | 相同 | ① |
| M08 删去该调用，模块说明与函数注释里提到它的文字都保留 | B[permission]、C① | 相同 | ①（注释 / docstring 不计） |
| M09 文末同名 `async def assert_project_permission` 覆盖导入 | B[permission]、C① | 相同 | ① |
| M10 文末再赋值 `NOTE_EDIT_MIN_LEVEL = "edit"` | B[permission]、C① | 相同 | ① |
| M11 EQCR 判定挪进 `if 非 admin:`（admin 被豁免） | B[eqcr]、C② | 相同 | ② |
| M12 文末同名 `async def is_project_eqcr` 覆盖导入 | B[eqcr]、C② | 相同 | ② |
| M13 角色限定形态把 `if admin: return` 挪到判定实现之前 | B[role] | 相同 | role |
| M14 文末 `assert_note_edit_access = assert_note_role_access` | 5 例全红 | 相同 | ①、②、role |
| P01 级别写成 `min_permission=NOTE_EDIT_MIN_LEVEL` | 无（正向对照） | 无 | — |
| P02 级别写成字面量 `"review"` | 无（正向对照） | 无 | — |
| M01，只跑基线守卫 3 例 | B[permission] | 相同 | 基线守卫单独打红 |
| M01，只跑契约守卫 2 例 | C① | 相同 | 契约守卫单独打红 |

- 每轮 error 0，失败都是 `AssertionError`（信息为该断言自己的中文说明，后接 `assert False`）；没变红的用例都是 passed。
- `note_edit_gate.py` 变异前后 blob `81948b31…`、sha256 `5dd64a3a7bdd9c9e…` 相同。
- 「变异证明」节无本任务条目：本任务没有改磁盘上的生产代码。design §8.5 / 需求 12.5 的磁盘变异 ①②（应红含「6.10 断言①」「6.10 断言②」）归任务 19.3；届时 ① 应红 B[permission] 与 C①，② 应红 B[eqcr] 与 C②（上表 M01、M02 是同一改动在源码副本上的预演）。

测试命令与结果（cwd `<树>\backend`，经 Python 子进程启动；子进程 env 去掉 `DATABASE_URL`，设 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONIOENCODING=utf-8`、`HYPOTHESIS_STORAGE_DIRECTORY` 指向 `D:\pm_tmp\` 下目录；`import app` 分别解析到各自树的 `backend/app`）：

- `D:\GT_plan\.venv\Scripts\python.exe -B -m pytest tests/test_project_endpoint_authorization_baseline.py tests/test_disclosure_notes_project_gate_contract.py -q -p no:cacheprovider --tb=short -rfE --junitxml=<临时文件>`
  - 基线树 `D:\wt_pm_ref`：51 passed，47.25 s。
  - 实施 worktree 改动前：51 passed，43.76 s，测试标识与结果和基线树逐个相同。
  - 实施 worktree 改动后：74 passed，43.91 s。原 51 例标识不变、全部 passed；新增 23 例（基线守卫 4、契约守卫 19）。
- cwd `D:\wt_pm_impl`：`D:\GT_plan\.venv\Scripts\python.exe -m ruff check --no-cache` 两个文件 → All checks passed!；`backend/scripts/check/check_file_size.py` 两个文件 → 退出码 0。

现算计数（仓库外探针在两棵树上分别导入基线守卫模块、调用其扫描函数；两棵树的路由文件相同，差别只在令牌）：

| 项 | 基线树 | 实施 worktree（改动后） |
|---|---|---|
| `_PROJECT_LEVEL_TOKENS` | 17 | 20 |
| 含 `{project_id}` 的端点（分母） | 414 | 414 |
| 无鉴权（第一维） | 6，全是 `_STUB_ENDPOINTS` 桩端点 | 6，逐条相同 |
| 仅登录不校项目（第二维） | 214 | 214，逐条相同（= `_IDENTITY_ONLY_BASELINE`） |
| 前缀维 | 632：项目级 353 / 仅登录 277 / 无鉴权 2 | 逐条相同（仅登录 = `_PREFIXED_IDENTITY_ONLY_BASELINE`；无鉴权 2 个即 `_PREFIXED_SELF_AUTH`） |

快照对照：基线守卫说明里写的分母「编写时 381」与现算 414 不同，只是说明文字，判据是 `>= 300`，本任务不改。两个基线常量按需求 8.4 下调为将要提交的树上的现算值，在任务 19.1 / 19.8。

副作用核对（postgres MCP 只读）：运行前 `logs` 94279 行（最大 `created_at` 14:24:31 UTC）、`evidence_outbox` 738 行；全部运行后（15:07:39 UTC）`logs` 94289、`evidence_outbox` 738、`authz_world_%` schema 0。`logs` 多出的 10 行在 14:55:01 ~ 15:07:21 UTC，都是 `admin` 经 127.0.0.1（共享开发服务）写入：`editing-lock` 8 行（create / update / delete）、`ai-chat` 1 行、`m7-special-reserve` 1 行，属并发会话。本任务的用例只读源码文件，不连库。

防假绿自查（供 15.2 参照）：没有 `dependency_overrides`、monkeypatch、`pytest.raises`、子进程、`skip` / `xfail` 或 hypothesis；断言是布尔为真、三元组相等、字典相等，没有「或」组合，也没有对多元素字面量的成员判断。

偏差：

1. ② 比任务原文严：原文只要求「函数体调用 `is_project_eqcr`」，这里要求无条件 await（不在分支里，在任何 return 之前），且该名字只绑定于 `app.services.eqcr_resolver`。依据 design §4.6 判定顺序 ③「admin 不豁免」与需求 7.3「同一个 EQCR 判定」：调用挪进非 admin 分支（M11）或换成本地同名函数（M12）都会让 EQCR 判定失效，按原文口径守卫仍是绿的。
2. ① 在「条件分支与异常处理之外」之上另加两条：在第一条含 return 的语句之前（提前 return 之后的调用不是无条件执行），且须 await（不 await 的协程不会执行）。
3. 被调名字须绑定于指定的导入：改成属性调用（如 `deps.assert_project_permission(...)`）或带类型注解的常量（`NOTE_EDIT_MIN_LEVEL: str = "review"`）都会判为不成立。这是有意从严：守卫红了再按新写法放宽，不会静默放过。
4. 两个文件共用一份判定函数：放在契约守卫（`note_gate_ast_facts`），基线守卫在测试函数里延迟导入（基线守卫其余用例只读源码，不因 app 导入失败而无法收集）。两个文件各自能独立打红，由基线守卫自带的反向自检与变异表最后两行（只跑一个文件）证明。任务原文没要求合成样例自检，契约守卫加了 17 例，证明判定函数两个方向都给对。
5. 「`assert_note_role_access` 必调判定实现」按 ① 的同一口径判：无条件 await，且在 `if admin: return` 之前（M13）。

留给后续任务：

- 10.1 改写契约守卫时保留 `NOTE_GATE_PATH`、`note_gate_ast_facts`（及其三个键）与本节测试；基线守卫从 `tests.test_disclosure_notes_project_gate_contract` 导入它，改名或改键须同步。
- 19.3 磁盘变异 ①② 的应红测试标识见上文「变异证明节无本任务条目」一条。
- 前缀匹配的含义：任何以这三个令牌开头的名字都会被基线守卫记作项目级。现算路由里没有定义或引用这些名字；10.x / 11.x 改挂端点后，是否像 `test_guard_action_token_is_really_project_level` 那样再钉「复用方必须从 `app.services.note_edit_gate` 导入、路由不得自写同名函数」，留给 15.2 判断（本任务未加）。
- `require_note_edit_access`、`assert_note_edit_access_for_object`、`assert_note_edit_access_on_projects` 调用判定实现，由 6.2 / 6.3 单元测试按执行计数证明；本任务的 AST 断言不覆盖这三个形态。

### 任务 7.1：级别回填迁移 V200 / R200（2026-10-21）

迁移号再核（需求 4.1；本任务开始时执行 `git fetch --prune origin`，口径同 `migration_runner`：`backend/migrations/` 直接子文件、`^V(\d+)__.*\.sql$` / `^R(\d+)__.*\.sql$` 不区分大小写、按数字比较）：

| 来源 | V 文件数 | R 文件数 | 最高 V | 同号 |
|---|---|---|---|---|
| 主工作树磁盘（含未跟踪；HEAD `8bfe70c1d`，分支 `spec/disclosure-note-doc-upload-and-batch-fill`） | 199 | 148 | V199（`V199__formula_global_settings_and_templates.sql`，未跟踪） | 无 |
| 目标分支尖端 `8bfe70c1d066c5e4d0c996b6f4a693411d025845`（2026-10-21 00:11:08 +0800「chore(spec): 归档 dsh-kb-ocr-local-first-routing + preexisting-test-failures-closure」；该远端引用 00:13:06 由并发会话推送更新，任务 3.4 记录时为 `71d0c04b5`） | 198 | 147 | V198（`V198__knowledge_documents_background_ocr.sql`） | 无 |
| 并集 | — | — | V199 | 无 |

- 写作时取值 198 已被占用：`V198__knowledge_documents_background_ocr.sql` / `R198__…`（主工作树已跟踪，提交 `f949c5abc` 2026-10-20 13:14 +0800，也在目标分支上）；199 被主工作树未跟踪的 `V199__formula_global_settings_and_templates.sql` / `R199__…` 占用（并发会话在做）。本地库 `schema_version` 已登记 198（`applied_at` 2026-10-20 00:25:33 UTC）与 199（15:11:24 UTC），共 199 行（001~199），`schema_migration_failures` 0 行（postgres MCP 只读）。
- ⇒ **n = 199 + 1 = 200**。200 在并集中不作 V 也不作 R；origin 全部 51 个远端分支各自最高 V 的最大值为 198（只在目标分支上），没有 V/R200；本机 3 个 worktree 中只有主工作树有 ≥198 的迁移文件（写入 V200 / R200 之前）。
- 旧口径的处置（按本节末编排者裁定 ①）：本文件「迁移号」节末尾已追加本任务的再核结论，「现算计数对账」的迁移号一行已改为 200；design 正文仍写 V198 / R198 或 198（§1.1 要点 5、N10、D5、§5.2、Property 3~5、Error Handling 表、§8.4 测试表、§10 行数表），是写作时快照，不改；tasks.md 只有任务 1.2 写「写作时 198」，任务 7.1 原文是 `V{n}`，7.2~7.5 不写版本号，都不改。后续 7.2~7.5、19.8、19.10 按 200；19.8 提交前仍须按需求 4.1 再核。

本次（收尾）再核（2026-10-21 07:12~07:13 +08:00；`git fetch --prune origin` 于 07:12:06 完成，口径同上）：

| 来源 | V 文件数 | R 文件数 | 最高 V / R | 有无 V200 / R200 |
|---|---|---|---|---|
| 主工作树磁盘（含未跟踪；HEAD 仍为 `8bfe70c1d`，分支 `spec/disclosure-note-doc-upload-and-batch-fill`） | 199 | 148 | V199 / R199（未跟踪的 `V199__formula_global_settings_and_templates.sql` / `R199__…`，修改时间 2026-10-20 14:36:39 UTC） | 无 |
| 目标分支尖端（fetch 后仍为 `8bfe70c1d066c5e4d0c996b6f4a693411d025845`，2026-10-21 00:11:08 +0800） | 198 | 147 | V198 / R198 | 无 |
| 并集 | — | — | V199 / R199 | 无 |

- 本地库（postgres MCP 只读，2026-10-20 23:13:11 UTC）：`schema_version` 199 行，最高 `199`（按字符串与按数值取最大相同），没有 200；`schema_migration_failures` 0 行。
- 补充（不属需求 4.1 的口径，只看有无并发占用）：origin 全部 51 个远端分支各自最高 V / R 的最大值仍为 198（只在目标分支上），没有分支含 ≥ 199 的 V 或 R；本机 worktree 中，实施 worktree 只多出本任务的 V200 / R200（未跟踪），基线树最高 191。
- 结论：200 仍空闲，n 保持 200，两个文件不改名。两个文件未被改动：`git hash-object --path` 与 `--no-filters` 都得下表 blob，磁盘 sha256、字节数与两种口径的行数都与下表相同（修改时间 2026-10-20 16:27:37 / 16:27:41 UTC，即上一次派发写入时）。文件名与 SQL 都没变，下文 runner 扫描、分句、真 PG 冒烟与只读预演的结论不受影响，本次未重跑。

新增文件（实施 worktree，均未跟踪）：

| 文件 | git blob | 行数（`split("\n")` / splitlines） | 字节 | sha256 |
|---|---|---|---|---|
| `backend/migrations/V200__partner_manager_edit_level_backfill.sql` | `c9e1138f9aa3f2ecd20099de4e8a28f54cea73bb` | 57 / 56 | 4490 | `a7de9ae311bc753c73a3cd43b397d71a8cdd1db3d97cb4d028a95f28596bc677` |
| `backend/migrations/R200__rollback_partner_manager_edit_level_backfill.sql` | `5e21d438aebff0a12ccdd713e9c574cd0b5ff0ca` | 26 / 25 | 1845 | `c9dc53eec7ab4a09ad81322bc39d391b000d97fbb1bf4ce4d4b17055ce47d4f5` |

- 编码与行尾：UTF-8 无 BOM，只有 LF（CRLF 0），末尾有换行，无 tab、无行尾空白，U+FFFD 0。现有约定：`git ls-files --eol` 显示 331 个 SQL（V 191 + R 140）在索引里都是 LF、检出为 CRLF（`core.autocrlf=true`，`.gitattributes` 没有 `*.sql` 规则）。新文件按索引形态写 LF，`git hash-object --path` 与 `--no-filters` 得同一 blob，提交后与既有文件一致。runner 的 checksum 是 `read_text`（通用换行）后的 sha256，等于 LF 归一后字节的 sha256，与上表 sha256 相同（文件在别处检出成 CRLF 也是同一 checksum）。
- 注释标点（逐行取 `--` 之后的文字现算）：ASCII 非字母数字字符只有 spec 名里的连字符（第 1 行，3 个）、编号里的点（`§5.2`、`4.2` 等）与标识符里的下划线；没有半角分号、冒号、逗号、括号、竖线、引号、`$`、`%`。代码部分不含 `EXCEPTION`、`$` 引号块、`/* */`。

runner 现读要点（`backend/app/core/migration_runner.py`，worktree 与 B 无差异，本任务未改）：

- 发现：`scan_migrations()` 遍历迁移目录直接子文件，`_VERSION_RE` 匹配文件名，内容按 `read_text(utf-8)` 读取并算 sha256，按版本**字符串**查同号（重复即 `RuntimeError`，整轮迁移都不执行），再按数字排序。`scan_rollback_scripts()` 同口径但不查同号（`rollback_to` 建 dict，同号时靠后者覆盖）。
- 分句 `_split_sql_statements`：识别 `--` 行注释（行注释里的分号不切句）、`/* */` 与 `$tag$` 块；不识别单引号字符串（字符串里的 `;`、`--`、`$`、`/*` 会被误判）；按半角分号切句；分号之后到下一条语句之间的注释成为下一条语句的前缀；只含注释的片段丢弃。
- 正向：`run_pending()` 先在独立连接上取 PG advisory lock（`0x47544D4947`，全库共用）→ 建 `schema_version` / `schema_migration_failures` → 版本不在 `schema_version` 的为待执行 → `_apply_migration` 在一个 `engine.begin()` 事务里逐句 `exec_driver_sql`（不解析绑定参数）再插 `schema_version`；任一句报错即整文件回滚、版本不登记，失败在独立事务里写入 `schema_migration_failures`（`attempt_count` 递增），下次启动重试；分句后零语句且没写 `no-op` 抛 `EmptyMigrationError`。
- 回滚：`rollback_to(target)` → 生产环境要 `confirm` → `MAX(version)`（字符串比较）为当前版本，`target` 须小于它 → 待回滚版本都要有 R 脚本 → `_run_backup()` 对 `settings.DATABASE_URL` 跑 `pg_dump`、写到 `backend/backups/` → 每个 R 脚本一个事务，逐句 `conn.execute(text(stmt))`（**会解析 `:名字` 绑定参数**，语句里带着注释）→ 另一个事务删掉 `schema_version` 中大于 `target` 的行并写 `operator` / `rollback_note`。R 脚本报错时异常在删 `schema_version` 之前抛出，版本保持已应用（需求 4.10）。
- 对两个新文件的约束：注释里不写半角分号（防切句）与半角冒号（R 脚本经 `text()`，半角冒号后接字母会被当成绑定参数而报错）；SQL 字符串字面量里也没有 `;`、`--`、`$`。

runner 扫描与分句核对（直接调用 runner 的函数，不连库；`MigrationRunner(engine=SQLite 内存引擎, migrations_dir=worktree 迁移目录)`，扫描不碰引擎）：

- `scan_migrations()`：192 个 V（B 的 191 个 + V200），版本唯一、按数值有序；V200 的 `version` 为 `"200"`，checksum `a7de9ae3…`。`scan_rollback_scripts()`：141 个 R，无同号，R200 checksum `c9dc53ee…`；V200 有配对 R200（另有 51 个历史 V 没有 R，含 V189 / V190，既有情形）。两个文件名只匹配各自的正则。
- 分句：V200 切出 2 条 —— ① 文件头 13 行注释 + `CREATE TABLE IF NOT EXISTS project_user_level_backfill (…)`（7 列）；② `WITH live_assign AS (…) … UPDATE project_users pu SET role = c.target_role, permission_level = c.target_level FROM changed c WHERE pu.id = c.pu_id`（32 行，4 条行内注释留在语句内）。R200 切出 3 条 —— ① 文件头 7 行注释 + `CREATE TABLE IF NOT EXISTS …`；② `UPDATE project_users pu SET … AND pu.permission_level = b.target_permission_level`；③ `DROP TABLE IF EXISTS project_user_level_backfill`，其前缀是 ② 行尾分号之后的注释 `-- 4.9：已被他途改动的行保持现值`（注释被带到下一条语句开头，不影响执行）。逐条核对：每条语句代码部分括号配平，`_is_comment_only` 均为 False，5 条语句 `text()` 解析出的绑定参数均为空，`_declares_noop` 为 False，注释没有切断任何语句。
- `check_migration_compat.scan_migration(V200)` → 无违规；sqlglot 30.8.0 能解析 V200（Create + Update 两条），不是「解析失败即不报」的空结果。

真 PG 冒烟（仓库外一次性探针，收尾时删除，见本节末「探针清理」）：

- 隔离：`tests/authz_world.pg_world`（同一事务内建 `authz_world_<随机>`，`SET LOCAL search_path` 只含它，`create_world_schema` 建 8 个枚举类型与六张表，结束整体回滚）；探针断言 `current_schemas(false)` 只有该临时 schema。连接串由仓库外启动器从 worktree 的 `app.core.config.settings.DATABASE_URL` 取出、只放进子进程 env，落盘输出里替换为占位。
- 执行方式与 runner 相同：用 `MigrationRunner._split_sql_statements` 切句；正向逐句 `exec_driver_sql`（同 `_apply_migration`），回滚逐句 `execute(text(...))`（同 `_execute_rollback_script`）；每个脚本包在一个 SAVEPOINT 里，模拟「整文件一个事务」。期望由探针里的模型按需求 4.2 / 4.3 / 4.4 原文逐行推导，别名取 `tests/role_map_expected.py`（不读生产代码）。
- 主世界数据：35 个用例、36 条成员行（34 条未删除），项目 P（现行）、Q（另一现行项目）、D（已软删）。

| 组 | 用例（迁移前 → 执行一次后） |
|---|---|
| 需求 4.2 改动（13 行，记录 `partner_manager`） | `signing_partner` / `partner` / `合伙人` / `manager` / `项目经理` 各一条现行委派：auditor+readonly、auditor+readonly、readonly+readonly、auditor+readonly、qc+review → partner+edit ×3、manager+edit ×2；同一用户经两份人员库记录持 `manager` 与 `partner` → partner+edit；全局 admin 的 manager+review（持 `manager`）→ manager+edit；全局 eqcr、只持 `manager` → manager+edit（全局角色不参与）；auditor+edit 持 `partner` → partner+edit（只差项目角色也算改动）；已软删项目 D 上 auditor+readonly 持 `manager` → manager+edit；`manager` 现行 + `eqcr` 已删委派 → manager+edit；同一用户一条已删成员行（qc+review）+ 一条现行（auditor+readonly）持 `manager` → 只改现行行；P、Q 各有成员行、委派只在 Q → 只改 Q 行 |
| 需求 4.3 改动（4 行，记录 `eqcr`，项目角色不动） | `eqcr` + auditor+edit → auditor+review；`独立复核合伙人` + readonly+readonly → readonly+review；`manager` 与 `eqcr` 两条（两份人员库记录）+ manager+edit → manager+review；已软删项目 D 上 `eqcr` + manager+edit → manager+review |
| 不改动、无记录（19 行） | 已等于目标值 manager+edit（持 `manager`）、partner+edit（持 `signing_partner`）；`独立复核合伙人` + partner+review（已是 review）；`partner` 与 `独立复核合伙人` 同持 + partner+review（EQCR 优先，不升 edit）；`Manager`、` manager`、`manager `、`EQCR` 四个变体；只持 `qc` / `审计员` / `未登记角色`；已删除的成员行 2 条；委派已删、人员库记录已删、人员库记录未关联用户、EQCR 委派的人员库记录已删各 1；P 上有成员行但委派只在 Q；没有任何委派；另有「有现行委派、没有成员行」的用户（未补建） |

| 检查 | 结果 |
|---|---|
| 执行一次：改动行集合与取值 = 模型 | 17 行（4.2：13，4.3：4），逐行相等 |
| 回填记录 | 17 条，键集合 = 改动行集合；迁移前值 = 改动前快照；目标值与 `rule` = 模型；`recorded_at` 非空 |
| 只动两列、不增删 | 快照取成员行全部 13 列：改动行只有 role / permission_level 不同，其余 11 列（含 `updated_at`、`is_deleted`、范围与有效期）逐行不变；未改动行全列不变；成员行 id 集合不变 |
| 其他表 | `users`、`projects`、`staff_members`、`project_assignments` 全表逐行不变 |
| 执行第二次（幂等，需求 4.7） | 成员行与回填记录（含 `recorded_at`）与第一次后完全相同 |
| 再执行 R200（往返，需求 4.6） | 全部成员行全列等于迁移前，回填表不存在，其他四表不变，`public.project_user_level_backfill` 不存在 |

- 改动按「规则 × 项目」分组：`partner_manager`（现行）auditor+readonly→manager+edit 5、auditor+readonly→partner+edit 3、readonly+readonly→partner+edit 1、qc+review→manager+edit 1、manager+review→manager+edit 1、auditor+edit→partner+edit 1；`partner_manager`（已软删）auditor+readonly→manager+edit 1；`eqcr`（现行）auditor+edit→auditor+review 1、readonly+readonly→readonly+review 1、manager+edit→manager+review 1；`eqcr`（已软删）manager+edit→manager+review 1。
- 附加世界一（需求 4.1）：3 个用例，正向从未执行时 R200 成功、成员行全列不变、回填表不存在；再执行一次 R200 同样；随后 V200 记 2 条，再 R200 后回到迁移前。
- 附加世界二（需求 4.9 / 4.5）：4 个用例。V200 之后把 a（`manager`）改成 manager+review、c（`eqcr`）改成 auditor+readonly、d（`signing_partner`）改成 manager+review，再执行一次 V200：a、c、d 被改回目标值，回填记录（含 `recorded_at`）与第一次相同（不覆盖）；再把 a、c 改成非目标值后执行 R200：a 保持 manager+review、c 保持 auditor+readonly（已被他途改动，保持现值），b（`partner`，仍是目标值）与 d 都恢复为第一次记录的 auditor+readonly（d 证明第二次正向没有覆盖迁移前值），回填表不存在。
- 冒烟后（postgres MCP 只读，16:32:47 UTC）：`authz_world_%` schema 0；任一 schema 中 `project_user_level_backfill` 0 个；`schema_version` 199 行、最高 199、没有 200；`schema_migration_failures` 0 行；`logs` 94315（最大 `created_at` 16:08:58 UTC）、`evidence_outbox` 738、`project_users` 88（最大 `updated_at` 2026-10-07）、`project_assignments` 86、`staff_members` 215、`users` 94、`projects` 85，与运行前（16:30:59 UTC）相同。

只读预演（冒烟之后，postgres MCP 对本地库只读执行 V200 中 `live_assign` ~ `targets` 的 SELECT，不含 INSERT / UPDATE）：

| 规则 | 项目 | 迁移前 → 目标 | 全局角色 | 行数 | 项目数 | 用户数 |
|---|---|---|---|---|---|---|
| 需求 4.2（`partner_manager`） | 已软删项目 | auditor+readonly → manager+edit | auditor | 84 | 56 | 84 |
| 需求 4.2（`partner_manager`） | 现行项目 | manager+review → manager+edit | admin | 2 | 2 | 1 |
| 需求 4.3（`eqcr`） | — | — | — | 0 | — | — |

- `targets` 共 86 行，全部会被改动（已等于目标值的 0 行）；与 F13 写作时期望（现行项目 2 行 admin 由 manager + review 改为 manager + edit；已软删测试项目 84 行由 auditor + readonly 改为 manager + edit；需求 4.3 规则 0 行）逐项相同，无差异。
- 其余成员行：本地库 `project_users` 共 88 行，全部未删除；另 2 行 manager+edit 没有现行委派，不在 `targets` 内。现行委派 86 条全是 `manager`。
- 按 runner 口径离线推算：本地库已应用 001~199，worktree 迁移目录为 001~191 与 200，待执行只有 200。真库正向迁移在任务 19.10。

既有迁移相关测试与检查脚本：

- 选取：`git grep` 现扫 `migration_runner` / `scan_migrations` / `_split_sql_statements` / `backend/migrations` / 遍历迁移目录的 `glob("V*.sql")` 等，取「扫描整个迁移目录」或「测 runner 本身（扫描、分句、回滚、批量容错、advisory lock、注释剥离、checksum 漂移登记）」的测试：31 个文件 + 4 个节点（`test_evidence_governance_wave1_capstone_v2_5.py::test_checksum_drift_guard_detects_edited_migration`、`workpaper_sync/test_v151_schema_contract.py::test_migration_number_has_no_collision`、`workpaper_sync/test_task15_content_mutation.py::TestPlanAndMutationShape::test_source_vocabulary_matches_the_owning_migration`、`workpaper_sync/test_task29_timeline_evidence.py::TestScenarioKindIsLockedToV151`），共 527 例。
- 运行方式：cwd `<树>\backend`，经仓库外启动器起子进程 `D:\GT_plan\.venv\Scripts\python.exe -B -m pytest <上述> -q -p no:cacheprovider -p t71_block_pg --tb=short -rfEs --junitxml=<仓库外>`；子进程 env 去掉 `DATABASE_URL`，设 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONIOENCODING=utf-8`、`HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外。`t71_block_pg` 是仓库外的一次性插件，替换 `asyncpg.connect`、`asyncpg.connection.connect`、`psycopg2.connect`，任何 PG 连接都记录后拒绝 —— 这批里有 15 例不看 `DATABASE_URL`、会直接用 settings 默认连接串连本地开发库（`TestV113PgContract` 10 例、V106 / V107 / V108 三个「在真 PG 上应用」用例、`test_real_db_state_is_consistent`、上面的 checksum 漂移节点），两棵树各被拦 15 次、名单相同。
- 结果：实施 worktree 443 passed / 13 skipped / 10 failed / 61 errors（67.2 s）；基线树 B 同一批 443 / 13 / 10 / 61（72.9 s）。527 个测试标识两边相同，逐例状态相同，失败首行信息把树路径归一后逐例相同 ⇒ 71 个红全部预存，新文件没有引入任何失败，也没有改变任何一例的结论。

| 两棵树相同的红 | 例数 | 形态 |
|---|---|---|
| `test_migration_v017.py` | 54 errors | setup `FileNotFoundError`：`V017__v3_refinement_tables.sql` / `R017__v3_refinement_tables_rollback.sql` 不在目录里 |
| `test_migration_v092.py` | 7 errors + 1 failure | `V092__a13_misstatement_aggregation.sql` 不在目录里 |
| `test_consol_push_schema_contract.py::test_check_value_sets_match_across_layers` | 1 | `{'manual', 'seed'} == {'manual', 'seed', 'seed_sub'}` |
| `test_procedure_delegation_migration_contract.py::test_v105_is_canonical_and_only_variant_exists` | 1 | `'V112__…' == 'V105__…'` |
| `test_raw_sql_schema_contract.py::test_raw_sql_tables_are_known` | 1 | `json_populate_recordset`（`note_project_realign_apply.py`，已知幽灵表） |
| `test_zero_downtime_migration_compat.py::test_property9_vr_pairing_complete` | 1 | V060 以后缺 R 的历史迁移（V094 起，含 V189 / V190；V200 不在其中） |
| V106 / V107 / V108「在真 PG 上应用」、`test_real_db_state_is_consistent`、checksum 漂移节点 | 5 | 本次被插件拦下的 PG 连接（`T71PgBlocked`）；另 10 例 `TestV113PgContract` 因连不上而 skip |

- `test_real_db_state_is_consistent` 的判据离线复算（`analyze_migration_state`，已应用集合取自上面的 postgres MCP 只读结果）：两棵树都不一致，原因相同 —— 本地库已应用 V192~V199 而 B 系目录里没有（主工作树的迁移）；worktree 的目录最高为 200，V200 不在阻断原因里。
- 未跑：`test_migration_integrity_pg.py`。它不 skip、直接用 settings 连本地开发库，在最终回滚的事务里向 public 表写行；判据是库的现场状态（checksum 只比 `schema_version` 已登记的版本），未应用的 V200 不进入它的比较。
- 检查脚本：`backend/scripts/check/check_migration_versions.py` 两棵树都退出 0（worktree「V: 192 个, R: 141 个」，B「V: 191 个, R: 140 个」，各 51 个缺 R 的警告，V200 不在其中）；`check_migration_compat` 见上（CI 默认按 `git diff origin/main` 取新增文件，未跟踪文件不会进入该清单，所以直接调用判定函数）；sqlfluff 4.2.2（CI 中是 `|| true` 的仅告警步骤，仓库没有 `.sqlfluff` 配置）以 `--dialect postgres` 跑：V200 / R200 都能解析（无 PRS），只有排版类规则（AL01、CP04、CP05、LT01、LT02、LT05、LT08、LT09、LT14、RF04、ST09、AM05）；参照 V191 也有 LT02、LT05。未按 sqlfluff 改排版，与 design 代码块保持一致。
- 副作用核对：`test_migration_runner_rollback.py` 的 `_run_backup` 用例（只替换 `subprocess.run`）会在被测树里真建空目录 `backend/backups/`，这次在两棵树各建了一个空目录，已删除。基线树运行前后 `git status --porcelain=v1 -uall --ignored` 逐字相同（1748 行），HEAD 仍为 B；另按时间戳扫描，两棵树里本任务新建的只有这两个空目录与两个新迁移文件（worktree 里既有的 `.hypothesis/` 是之前任务留下的，本任务没有新建或改动其中文件）。本地库计数 16:47:26 UTC 复核仍与运行前相同。

schema 漂移检测器对 `project_user_level_backfill`（迁移建、ORM 不声明）的处理（现读 `app/core/schema_drift_detector.py` + 离线调用其 `_diff_tables` / `_diff_columns` / `_apply_suppressions` / `count_critical`，库表集合取 ORM 全集再加这张表）：

- 335 张 ORM 表中没有它，它不在 `KNOWN_ALLOWLIST`，也不命中外部租户前缀 ⇒ 产生恰好 1 条表级 `db_extra`（「DB 有表 … 但 ORM 未定义」），没有列级条目；`db_extra` 不在 `CRITICAL_DRIFT_TYPES`（orm_extra / enum_mismatch / checksum_drift），`count_critical` 为 0 ⇒ `/api/health` 不因此 degraded，启动日志的 critical 计数不变。
- 只要正向已执行、回滚未执行，这条 INFO 级漂移就会出现在 `schema_drift_log` 与 health 的总数里。是否登记进 `KNOWN_ALLOWLIST`（按惯例要配「已登记且无 ORM 模型」的双向断言）不影响正确性；本任务未改检测器，处置见本节末编排者裁定 ②。

给任务 7.2 的入口说明（现读，未在隔离 schema 里试跑）：

- 可用入口：`MigrationRunner(engine=<AsyncEngine>, migrations_dir=<目录>)`（`engine=` 时 runner 不持有、不关闭引擎）。正向 `run_pending()`（与启动同一路径：advisory lock → 建两张系统表 → pending → `_apply_migration` → 失败记录）；回滚 `rollback_to(target)`。也可直接调 `_apply_migration(mig)` / `_execute_rollback_script(mig)`（`mig` 取自 `scan_migrations()` / `scan_rollback_scripts()`），执行代码与启动 / 回滚相同，但跳过了 `_run_pending_inner` 的失败记录。
- runner 的每次库访问都经 `self._engine.begin()` / `connect()` 取新连接，不能传入已有连接或事务 ⇒ 权限世界 PG 版「同一事务 + `SET LOCAL search_path` + 整体回滚」不能直接驱动它（未提交的 schema 对其他连接不可见，`SET LOCAL` 只作用于那一条连接）。可行做法：先提交建好临时 schema 与六张表（`create_world_schema`），引擎用 `NullPool` + `connect_args={"server_settings": {"search_path": <临时 schema>}}`（asyncpg 的会话参数），`migrations_dir` 指向只含 V200 / R200 副本的临时目录（指向真目录则空 schema 里会去跑其余 199 个版本），结束 `DROP SCHEMA … CASCADE`；只能整库运行时才改用用后即删的临时测试库。
- 坑一：`ensure_schema_version_table()` 的 DO 块用 `information_schema.columns WHERE table_name = 'schema_version'` 判断回滚追踪列，没有限定 schema；public 的 `schema_version` 已有 `operator` / `rollback_note`（现查），临时 schema 里新建的 `schema_version` 因此不会补这两列，`rollback_to` 最后的 `UPDATE schema_version SET operator …, rollback_note …` 会报错（此时 R 脚本已在自己的事务里提交）⇒ 先在临时 schema 里按完整 7 列建好 `schema_version`。
- 坑二：`rollback_to` 无条件调用 `_run_backup()`，对 `settings.DATABASE_URL`（本地开发库，不是 runner 的引擎）跑 `pg_dump` 并写 `backend/backups/`；本机 PATH 上没有 `pg_dump`，`subprocess.run` 会抛 `FileNotFoundError`，回滚脚本一条都不会执行 ⇒ 测试须替换 `_run_backup`（既有 `test_migration_runner_rollback.py` 用 `patch.object(runner, "_run_backup", …)`）。
- 坑三：`run_pending()` 取的 advisory lock 是全库共用的同一个键，持锁期间会挡住并发启动的开发后端的迁移（反之亦然）；`rollback_to` 要求 `target` 小于 `MAX(version)`（字符串比较），且非生产环境（`APP_ENV`）或带 `confirm`。

与 design §5.2 代码块的差异（逐条；去掉注释、压缩空白后，两个文件的 SQL 代码与 design 两个代码块逐字相同）：

1. 版本号 198 → 200（文件名、文件头注释中的 V200 / R200、「schema_version 保留 200」）：198 / 199 已被占用，见上文迁移号再核。
2. 两个文件各加文件头注释（V200 13 行、R200 7 行）：按既有迁移惯例（如 V191）写明 spec、需求编号、改动范围、幂等与回滚、失败语义；只用全角标点，不写半角分号与冒号。
3. V200 建表语句的行内注释 `-- partner_manager | eqcr` 改为 `-- partner_manager（需求 4.2）或 eqcr（需求 4.3）`：去掉半角竖线（注释只用全角标点）。其余行内注释与 design 逐字相同。
4. R200 建表语句按 V200 的版式每列一行（design 中 7 列压在 3 行里），列名、类型、约束、默认值与先后不变；R200 三条语句之间加空行。只是排版。
5. 适配分句规则：design 代码块本身已满足（注释里没有半角分号、冒号；字符串字面量里没有 `;`、`--`、`$`），没有为分句改动任何语句。R200 第二条语句行尾的注释在分号之后，分句后成为第三条语句的前缀（见上），按 design 原样保留。

编排者裁定（2026-10-21 收尾时登记）：

- ① 迁移号 198 → 200：不改 requirements.md / design.md（spec 约定执行期不修改，design 里的 V198 是写作时快照）；tasks.md 7.1 原文是 `V{n}`，不需要改；本文件在「迁移号」节末尾追加再核结论，「现算计数对账」的迁移号一行改为 200。后续 7.2~7.5、19.8、19.10 一律按现行号，19.8 提交前仍按需求 4.1 再核。
- ② 回填记录表 `project_user_level_backfill` 是否登记进漂移检测器 `KNOWN_ALLOWLIST`：本任务不改检测器（design §5.2 未列此改动；它产生的是 INFO 级 `db_extra`，`count_critical` 为 0，不影响 health）；作为待用户确认事项登记，由编排者在检查点向用户提出。
- ③ 任务 7.2 的驱动方式：按 7.2 原文「在隔离 schema 内驱动、只能整库运行时改用临时测试库」，优先采用上文「给任务 7.2 的入口说明」中的方案（提交型临时 schema + `NullPool` 引擎，`server_settings` 设 search_path + 只含新迁移副本的临时 `migrations_dir` + 结束 `DROP SCHEMA … CASCADE`），具体由任务 7.2 实施时现读确认。

探针清理：上一次派发的一次性探针、插件、启动器与输出都在仓库外 `D:\pm_tmp`，以 `t71_` 为前缀，当时没有删除：文件 82 个、目录 2 个（`t71_hyp_impl`、`t71_hyp_ref`，两棵树运行时 `HYPOTHESIS_STORAGE_DIRECTORY` 所指的存储目录，内含 `constants` / `unicode_data` 等缓存文件共 498 个）。收尾时于 2026-10-21 07:19:10 +08:00 一并删除，删除后列目录 `t71_*` 为 0 项，其他前缀的文件未动。本次收尾的一次性探针 `D:\pm_tmp\t71b_*` 只做只读核对与本节写入，写入后删除。

### 检查点 5：后端底座（2026-10-21）

派发说明：任务依赖图里没有检查点，上一轮编排未调度本任务，任务 2~4、6.x、7.1 完成后补跑。本次只运行测试并做只读核对，没有改生产代码、测试与夹具。实施树改动仍未提交，`git status --porcelain=v1 -uall` 开工时与收尾时逐字相同（44 行：23 个 M、21 个 ??）。时间：运行时刻为北京时间，数据库与 Redis 的时间为 UTC。

批次口径（仓库外一次性脚本，`ast.parse` 现算）：

- 扫描范围：两棵树 `backend/tests` 下按 pytest 默认命名的测试文件（`test_*.py`、`*_test.py`；`pytest.ini` 未改 `python_files`），不含 `conftest.py` 与 `__pycache__`：实施树 3122 个、基线树 3108 个。
- 判据（口径同任务 3.4）：AST 导入（`import X`、`from X import …`；`from app import deps` 这类按完整点分名计），或 docstring 以外的字符串常量，等于某个模块路径或以「模块路径 + 点」开头。四个模块：`app.services.assignment_service`、`app.services.role_context_service`、`app.deps`、`app.services.custom_query.ownership_guard`。改为不要求点边界、或把 docstring 也计入，两种写法都不多出文件。
- 命中：实施树 223 个、基线树 215 个；基线有而实施没有的 0 个，实施独有的 8 个都是本 spec 新增的测试文件。分模块（实施 / 基线）：`app.deps` 215 / 208，`assignment_service` 8 / 3，`role_context_service` 1 / 0，`ownership_guard` 8 / 7。命中都来自导入，只经字符串常量命中的 0 个。
- 并上本 spec 新增 / 改动的测试文件 33 个（实施树 `git status` 现算：新增 14、改动 19；夹具 `authz_world.py` 与数据 `role_map_expected.py` 不是测试文件，不计），其中 7 个不在命中里：`test_eqcr_alias_single_source.py`、`test_eqcr_resolver_property.py`、`test_eqcr_resolver_smoke.py`、`test_note_edit_gate_multi_project_unit.py`、`test_project_endpoint_authorization_baseline.py`、`test_role_map_single_source.py`、`test_sod_unchanged.py`。
- 批次共 230 个文件：实施树 230 个都在，基线树有 216 个（缺本 spec 新增的 14 个）。
- 与任务 3.4 批次（实施 220 / 基线 218）的差别：3.4 另含「假会话返回成员行形状替身」的启发式 11 个，其 `ownership_guard` 一组为 13 个（本次按模块路径现算为实施 8 / 基线 7）。本次按派发口径只取导入与模块路径字符串；正文提到这四个模块、却不在本批次里的 9 个文件另跑一个补充批次（见下）。

两树命令（仓库外启动器 `D:\pm_tmp\t5_run.py`，两树并行，07:36:27 同时启动）：

- cwd 各树 `backend`：`D:\GT_plan\.venv\Scripts\python.exe [-B] -m pytest <文件> -q -p no:cacheprovider --tb=short -rfE --junitxml=D:\pm_tmp\t5_main_<树>.xml`。
- 子进程 env 去掉 `DATABASE_URL`（`pg_only` 跳过），设 `PYTHONIOENCODING=utf-8`、`HYPOTHESIS_STORAGE_DIRECTORY=D:\pm_tmp\t5_hyp_main_<树>`。基线树另加 `-B`、`PYTHONDONTWRITEBYTECODE=1` 与 `--deselect tests/procedure_delegation_visibility/test_task15_full_entry_integration.py::TestExplainAndQueryCount::test_explain_plans_and_no_n1_artifact`（该例会改写已跟踪的 `explain_plans.txt`）。
- cwd 为各树 `backend` 时，`import app` 分别解析到 `D:\wt_pm_ref\backend\app\__init__.py` 与 `D:\wt_pm_impl\backend\app\__init__.py`（`sys.path[0]` 为 `''`）。

| 树 | 文件 | pytest 汇总 | 耗时（pytest / 墙钟） |
|---|---|---|---|
| 基线 `D:\wt_pm_ref` | 216 | 110 failed，3302 passed，1064 skipped，1 deselected，7 xpassed | 990.11 s / 07:36:27–07:53:16 |
| 实施 `D:\wt_pm_impl` | 230 | 109 failed，3894 passed，1068 skipped，7 xpassed | 1057.31 s / 07:36:27–07:54:24 |

junit 逐例：基线 4483 个测试标识（passed 3309，含 xpassed 7；failed 110；skipped 1064），实施 5078 个（3901 / 109 / 1068）；两边都没有 error。

逐例比对（仓库外脚本解析两份 junit，`classname` 与 `name` 还原为测试标识；比较信息时把两棵树的路径、UUID、32 位十六进制 id、对象地址归一）：

- 共同标识 4443 个：passed → passed 3268，skipped → skipped 1064，failed → failed 109，failed → skipped 1，passed → skipped 1。
- 两边都失败 109 例，异常类型逐例相同：
  - 信息 104 例逐字相同。
  - 4 例只差树路径或随机 id：`test_archived_project_guard.py::test_adjustments_post_returns_423_for_archived`（SQL 参数里的 id）、`test_i2_integration.py::TestRenderStrategy::test_account_prefixes_include_1717` 与 `test_i6_render_and_export.py::test_i6_render_strategy_fetches_occurrence_amount`（路径）、`test_workhour_list.py::TestWorkhourList::test_manager_sees_only_managed_projects`（uuid）。
  - 1 例 `test_deliverable_onlyoffice.py::test_property_54_onlyoffice_unavailable_degradation`：断言与位置相同（`assert True is False`，`test_deliverable_onlyoffice.py:206`），只差 hypothesis 附带的 Explanation 行（对象地址与失败样例覆盖到的行，每次运行不同）。
  - 最后一帧位置 108 例相同。另 1 例 `test_c1_entity_control_pbt.py::test_c1_entity_control_pbt` 落在 `app/deps.py` 第 405 行（基线）/ 第 383 行（实施），两处是 `authorize_wp_edit` 里同一条语句 `role = current_user.role.value`；行号不同是因为任务 3.4 删去缓存段，后面的行前移，信息逐字相同。
  - 109 例按测试标识逐个核对，全部已在「预存失败登记」中。登记表 110 例里另 1 例（`workpaper_sync/test_task21_room_service.py::TestDocKeyIsMtimeFree::test_rg17_is_clear_on_the_real_manifest`）不在本批次，在补充批次里两边同样失败、信息逐字相同。没有需要补登的预存失败，登记表未改。
- 实施树失败、基线树通过（或基线树没有该标识）：0 例。
- 基线树失败、实施树非失败：1 例，`workpaper_sync/test_template_override_lossless.py::TestProperty20OnlyOfficeConversionPreservesPageSetup::test_conversion_roundtrip_keeps_page_setup_semantics`。基线 `OSError: [WinError 10048]`（端口已被占用），实施跳过（`OO 转换报错 error=-8`）。该用例在固定端口 18098（`_PROBE_PORT`）上起探针 HTTP 服务，两树并行时后绑定的一方失败。之后两树各单独跑一次（先后执行、不并行）：都是 1 skipped，原因都是 `OO 转换报错 error=-8`。与任务 3.4 记录的现象相同，与本 spec 无关，不登记为预存失败。
- passed → skipped 1 例：`test_deliverable_generation_membership_auth.py::test_compare_only_reads_this_projects_execution`。任务 3.2 把它改为 `pg_only`，在下面的 PG 轮里通过。
- 只在基线树的 40 个标识，全部 passed，与任务 3.4 记录的 40 个同口径：
  - `test_deliverable_generation_membership_auth.py` 23 个：两个 mutation 用例与 `test_premise_reviewers_are_review_level` 改名前的标识，以及 `test_team_member_can_generate_deliverables` 以 `-review` / `-edit` 结尾的 20 个参数化（任务 2.2 / 3.2）。
  - `test_phase8_endpoint_role_levels.py` 14 个：`test_premise_reviewer_roles_are_review_level`、`test_edit_endpoints_still_block_reviewers`，以及 `test_review_level_member_can_use`、`test_edit_level_member_can_use` 改参数化前的各 6 个（任务 2.2 / 3.2）。
  - `test_phase8.py::TestPermissionCache` 3 个（任务 3.4 删除）。
- 只在实施树的 635 个标识：633 passed、2 skipped，失败 0。
  - 本 spec 新增的 14 个文件共 478 个：`test_assignment_save_semantics.py` 7、`test_assignment_sync_examples.py` 6、`test_assignment_sync_property.py` 5、`test_authz_world.py` 54、`test_eqcr_alias_single_source.py` 3、`test_eqcr_resolver_property.py` 23、`test_eqcr_resolver_smoke.py` 5、`test_note_edit_gate_multi_project_unit.py` 21、`test_note_edit_gate_unit.py` 146、`test_note_multi_project_gate.py` 4、`test_permission_cache_removed.py` 36、`test_role_map_and_context.py` 57、`test_role_map_single_source.py` 2、`test_sod_unchanged.py` 109。
  - 改动文件中改名或新增后的 156 个：`test_phase8_endpoint_role_levels.py` 90、`test_deliverable_generation_membership_auth.py` 43、`test_disclosure_notes_project_gate_contract.py` 19、`test_project_endpoint_authorization_baseline.py` 4。
  - 基线轮不选的那 1 例，在实施树 passed。
  - 跳过的 2 个都是 `pg_only`：`test_assignment_save_semantics.py::test_pg_only_deleted_member_rows_then_new_live_row`、`test_authz_world.py::test_pg_world_is_isomorphic_and_leaves_no_objects`。
- 本 spec 的 33 个测试文件逐文件：
  - 改动的 19 个里，14 个两树例数相同且全部通过。
  - `test_phase8.py`：67 passed + 5 failed → 64 passed + 5 failed。少的 3 例是删除的 `TestPermissionCache`，5 例失败是预存的 `TestReportEngineCache`。
  - 另 4 个的例数变化来自改名、改参数化与新增，两树都全部通过：`test_deliverable_generation_membership_auth.py` 120 → 139 passed + 1 skipped（`pg_only`），`test_phase8_endpoint_role_levels.py` 23 → 99，`test_disclosure_notes_project_gate_contract.py` 22 → 41，`test_project_endpoint_authorization_baseline.py` 29 → 33。
  - 新增的 14 个在实施树全部通过，只有上面 2 个 `pg_only` 跳过。
- 任务 3.4 登记过的并行时序抖动（`dsh_agent_panel/test_task5_run_coordinator.py` 的租约用例）本次两树都通过。

补充批次：正文提到这四个模块、但不按导入或模块路径字符串命中的 9 个文件。其中 7 个只在注释或 docstring 里提到 `OwnershipGuard` / `ownership_guard`：`test_advanced_query_ddl_cross_lock.py`、`test_advanced_query_template_execution.py`、`test_custom_query_auth_preservation.py`、`test_query_orchestrator.py`、`test_template_service_pbt.py`、`test_wp_formula_three_type.py`、`workpaper_sync/test_task21_room_service.py`；另 2 个是 `test_event_year_contract.py`（读取 `assignment_service.py` 源码做扫描）与 `test_gen_service_deps.py`（正文含 `deps.py`）。两树同参数并行运行（08:15:41–08:16:43），两边各 185 个标识，标识集合相同；结果都是 184 passed、1 failed，失败的是上面 RG-17 那一例（已登记，信息逐字相同）。

PG 轮：

- 现算本 spec 新增的 `pg_only`：两棵树对本 spec 的测试文件跑 `--collect-only -q -m pg_only`（基线树用上面的只读参数）。实施树 33 个文件 1114 个用例中有 3 个，基线树 19 个改动文件 520 个用例中 0 个，所以新增 3 个：`test_assignment_save_semantics.py::test_pg_only_deleted_member_rows_then_new_live_row`、`test_authz_world.py::test_pg_world_is_isomorphic_and_leaves_no_objects`、`test_deliverable_generation_membership_auth.py::test_compare_only_reads_this_projects_execution`。另在这 33 个文件里检索 `skipif`、`DATABASE_URL`、`importorskip`，没有其他按库类型跳过的用例。
- 运行：仓库外一次性启动器起子进程，从实施树的 `app.core.config.settings.DATABASE_URL` 取连接串（`postgresql+asyncpg`，不打印），只放进 pytest 子进程的 env。cwd `D:\wt_pm_impl\backend`，命令 `D:\GT_plan\.venv\Scripts\python.exe -m pytest <3 个标识> -q -p no:cacheprovider --tb=short -rfEs --junitxml=…`。结果 3 passed、0 skipped，7.96 s（08:12:46–08:13:01）。落盘的输出与 junit 已把连接串和口令替换为占位，核对不含连接串。
- 运行后（postgres MCP 只读，00:13:12 UTC）：`authz_world_%` schema 0 个，任一 schema 中都没有 `project_user_level_backfill`；下表 8 张表与 `notifications`（778 行）的行数和最大时间戳，与运行前（00:12:40 UTC）相同。

副作用核对 · 两棵树：

- 基线树运行前后 `git status --porcelain=v1 -uall` 都为空，HEAD = B。
- 另看了 `--ignored`。主批次两轮各在 `backend/storage/` 下新建了 9 个被忽略的文件与 3 个目录，git status 不显示。9 个文件是交付件 docx 1 个和底稿附件 8 个，文件名为随机 uuid，创建于 07:42–07:46。已按路径逐个删除，之后基线树的 `--ignored` 清单与运行前逐字相同（1748 行）。
- `backend/storage/` 下另有 18 个同类文件和 2 个空目录，创建于 2026-10-20 17:05–18:02（任务 3.4 那几轮），不是本次产生，未动；实施树也有同样数量的这类文件与空目录。
- 实施树只有 `explain_plans.txt` 一个已跟踪文件被改写，已用基线树的干净副本逐字节恢复：sha256 `58379fb2…` 与运行前相同，`git hash-object --path` 等于 HEAD blob `f7c541a7…`，该路径 status 为空。实施树 `git status` 与开工时逐字相同；`--ignored` 里新增的只有 5 个 `.pyc`（不加 `-B` 运行的正常产物）。

副作用核对 · 本地开发库（postgres MCP 只读）：

| 表 | 运行前（23:34:45 UTC） | 主批次与误启动之后（00:08:32 UTC） | PG 轮前 / 后（00:12:40 / 00:13:12 UTC） |
|---|---|---|---|
| `logs` | 94321（最新 `created_at` 23:33:19） | 94544（+223，最新 23:50:03） | 94544 / 94544 |
| `evidence_outbox` | 738（最新 2026-10-20 09:51:06） | 748（+10，最新 23:38:39） | 748 / 748 |
| `project_users` | 88（最新 `updated_at` 2026-10-07 08:09:10） | 88，时间戳不变 | 88 / 88 |
| `project_assignments` | 86（2026-10-07 04:51:58） | 86，不变 | 86 / 86 |
| `staff_members` | 215（2026-10-15 06:19:08） | 215，不变 | 215 / 215 |
| `users` | 94（2026-10-07 04:51:58） | 94，不变 | 94 / 94 |
| `projects` | 85（最新 `updated_at` 2026-10-20 11:14:02） | 85，不变 | 85 / 85 |
| `wp_access_security_outbox` | 705（2026-10-13 15:58:10） | 705，不变 | 705 / 705 |
| `authz_world_%` schema | 0 | 0 | 0 / 0 |

- `logs` 新增 223 行，`user_id` 全为空，创建于 23:38:36–23:50:03 UTC，都在主批次窗口（23:36:27–23:54:24 UTC）内。按对象类型分：workpaper create 160；project create 52、delete 2、update 1；adjustment delete 3；disclosure-note create 2；dataset create 2；working_paper status_change 1。project 的 55 行里，32 行的 `object_id` 是真库现存项目：「重药控股安徽有限公司_2025」26 行，「重庆医药集团医疗器械有限公司_2025」6 行。
- `evidence_outbox` 新增 10 行，全部 pending，`project_id` 为「重药控股安徽有限公司_2025」，创建于 23:38:36–23:38:39 UTC。事件类型为 `attachment.version_replaced`、`evidence_ref.created`、`evidence_ref.deactivated`，停用原因 `source replaced (wave9 citation it)`。
- 这两组新增与任务 3.4 登记的同型：3.4 是 `logs` 224 行（workpaper 160 / project 56 / adjustment 3 / dataset 2 / disclosure-note 2 / working_paper 1，32 行指向这两个项目）和 `evidence_outbox` 10 行。判断为批次内不看 `DATABASE_URL`、按 settings 默认值连本地库的既有 PG 用例经独立提交写入，B 上同样发生，与本 spec 改动无关。按约定只登记，没有删除。
- 其余 6 张表在全部运行前后，行数与最大时间戳都不变。

副作用核对 · 共享 Redis db0 的 `perm:*`（`docker exec audit-redis redis-cli --scan`，只读；宿主与容器时钟差小于 1 秒）：

| 时刻（UTC） | 键数 | 说明 |
|---|---|---|
| 23:34:58（运行前） | 3 | 值 edit，TTL 124–130；键里的用户 / 项目 id 在真库 0 行 ⇒ 运行前就有的外部写入 |
| 23:39:16 | 22 | 值 edit / review / readonly。其中 9 个 TTL 127–128，按 TTL 300 反推写于 23:36:23–24，早于两轮启动（23:36:27）⇒ 外部写入；其余 13 个写于 23:38:43–23:39:02 |
| 23:45:09 | 50 | 涉及 49 个用户 id、47 个项目 id，在真库都是 0 行 |
| 23:50:22 | 1 | — |
| 00:09:21 | 0 | 已全部到期 |
| 00:13:20（PG 轮之后） | 0 | — |

实施树代码没有写入点：本批次里的 `test_permission_cache_removed.py` 36 例通过。运行中出现的键，与基线树一轮（B 仍写缓存，TTL 300 秒）以及运行前就存在的外部写入相符，无法逐键区分。按约定没有删除任何键。

运行偏差（本次失误，已终止并核对）：

- 经过：08:01:35 为了单独复跑上面端口冲突的那 1 例，我用 PowerShell 的 `Set-Content -Encoding utf8` 写清单文件，文件带了 BOM。启动器读回后路径对不上，清单为空，pytest 于是按 `testpaths = tests` 在基线树起了全量运行。只读参数照常（`-B`、`PYTHONDONTWRITEBYTECODE=1`、无 `DATABASE_URL`），但没有加 deselect。命令超时后命令链继续执行，又在实施树起了全量运行。
- 终止：基线树那一轮运行约 5 分 32 秒（08:01:35–08:07:07），实施树那一轮约 10 秒（08:07:07–08:07:17），发现后都已终止。两份输出都是 0 字节，没有生成 junit；`-q` 下收集阶段不输出，推断两轮都还在收集。
- 核对结果：
  - 基线树 `git status`（含 `--ignored`）与运行前逐字相同。按创建 / 修改时间扫描全树（排除 `.git`、`node_modules`），08:01:30 之后没有新建或修改的文件和目录。
  - 实施树只多出 82 个 `.pyc` 与 3 个新建的 `__pycache__` 目录（收集时导入模块所致），已按清单删除，之后 `--ignored` 清单与误启动前逐字相同。
  - 本地开发库：用只读会话扫描 public 下 641 个 `created_at` / `updated_at` 列。00:01:30–00:07:30 只有 Metabase 的搜索索引表有行（`search_index__mjiwaqehun9dqyghsyrgk` 52 行、`search_index_metadata` 1 / 2 行，是 00:05:04 的每小时重建），上表 8 张表在该窗口都是 0 行。
  - Redis：00:09:21 扫描 `perm:*` 为 0，说明 00:04:21 之后没有写入；在这之前若有写入，TTL 已到期，无法分辨。
- 处置：启动器改为用 `utf-8-sig` 读清单，清单为空即中止；之后按先后顺序单独复跑那 1 例（结果见上）。

清理：

- `D:\pm_tmp` 开工时只有 `t65_` 前缀的 52 项（49 个文件、3 个目录，目录内共 3 个文件）。`t34_`、`t34b_`、`t34c_`、`hyp_t34` 前缀的条目在开工时已经没有（0 项）。
- 已删除 `t65_` 的 52 项，之后这五个前缀都是 0 项。
- 本次的一次性文件都用 `t5_` 前缀（启动器、比对与扫描脚本、junit、输出、hypothesis 目录），写入本节后删除，删除后 `D:\pm_tmp` 为空。

待用户决定（不影响检查点结论：没有新增失败）：

1. 本地开发库里，既有 PG 用例每轮都会写入 `logs` 与 pending 的 `evidence_outbox`（本次分别 223 行、10 行，与任务 3.4 同型）。这些用例不看 `DATABASE_URL`，按 settings 默认值直连本地库。是否清理这些行，或另立事项让这些用例改连隔离库：沿用任务 3.4 的待决项，本次没有删除。
2. 两树并行同批对照时，`test_template_override_lossless.py` 的固定端口会让基线树必报 1 例 `OSError: [WinError 10048]`，检查点 12 / 16 与任务 19.9 还会遇到。建议这类对照把该例单独顺序执行；没有其他决定之前，按本节的方式单独复跑并记录。
3. 两棵树的 `backend/storage/` 下各有任务 3.4 那几轮留下的 18 个被忽略文件与 2 个空目录，是否清理（本次未动）。

用户裁定（2026-10-21，检查点 5 后，用户选择「按推荐处理（4 项全部采纳）」）：

1. CI 缺 node：本 spec 内给 `.github/workflows/ci.yml` 的 `backend-tests` job 加 `setup-node` 与 `audit-platform/frontend` 下 `npm ci`，在任务 19.x 生成候选提交前完成（任务 2.5 的前端扫描、15.2 的防假绿扫描都需要 node）。
2. 本地开发库被既有 PG 用例写入（`logs` 约 220 行、`evidence_outbox` 10 行 pending / 轮）：不删数据，登记为后续事项（任务 20.2），之后的两树对照照旧。
3. 回填记录表 `project_user_level_backfill` 登记进 schema 漂移检测器 `KNOWN_ALLOWLIST`（按惯例配双向断言），在任务 7.5 一并完成。
4. 需求 9.4 与生产注册的差异：接受「9.4 的 403 指项目级门禁本身」的口径；`wp_procedures` 两个端点在生产上先过 `dedicated_wp_gate`，非成员可能得 404；在任务 14.4 按生产注册补一条用例核对实际返回（隔离独立会话，不写开发库）。

编排者自行处理事项（同日登记）：

- 固定端口用例（`test_template_override_lossless.py`）在两树对照时单独顺序执行。
- 两棵树 `backend/storage` 下前序轮次的被忽略产物由任务 7.2 的前置步骤 B 清理（结果见下）。
- 任务 2.9 发现的职责分离预存缺陷与任务 2.5 发现的 B 中 `g7VoucherSample.ts` 多余 `}` 登记到任务 20.2 的后续事项。

前置步骤 B 清理结果（任务 7.2 开工时，2026-10-21 08:33:58–08:34:06 +08:00）：两棵树 `backend/storage/` 下各有 18 个文件（被 `.gitignore` 第 54 行 `storage/` 忽略、未跟踪，创建与修改时间都在 2026-10-20 17:05:43–17:58:58 +08:00 之间）和 16 个目录（2 个原本即空的 `projects/<uuid>`，14 个因删文件而变空、含 `backend/storage` 本身；创建时间都在 17:05–18:02 之间，其下没有已跟踪文件），全部删除，窗口外的文件与 `backend/storage` 之外的路径都没动。`git status --porcelain=v1 -uall --ignored`：基线树 1748 → 1730 行，全部是 `.pyc`（与任务 2.2~2.9 记录的状态相同）；实施树 74590 → 74572 行；两边减少的都恰是这 18 个文件、没有新增行，HEAD 仍为 B。

### 任务 7.2：回填结果的性质测试（真 PG）（2026-10-21）

开工前的两件收尾小事（用户裁定登记、两棵树 `backend/storage/` 清理）见上一节末尾。本任务只新增两个测试侧文件，没有改生产代码、迁移文件与既有测试。

新增文件（实施 worktree，均未跟踪）：

| 文件 | git blob（`--path` 与 `--no-filters` 相同） | 行数（`split("\n")` / splitlines） | 字节 | sha256 |
|---|---|---|---|---|
| `backend/tests/test_level_backfill_migration_pg.py` | `0af1abf58b28a488752572f9f6ad666434ef7160` | 429 / 428 | 27320 | `3facee5d5a5f011ffe7c5854855439445ab845397121ca7e86f557f847edeea1` |
| `backend/tests/level_backfill_world.py`（夹具模块，文件名不以 `test_` 开头，不被收集） | `505f2d94314cfc9b58a023c0f052e40c5de2af23` | 426 / 425 | 22808 | `3ff6c56285858c3851c6b0bb7780ed237e013e476c37d760d1c8cf05dad79f37` |

- UTF-8 无 BOM、只有 LF、末尾有换行。`ruff check --no-cache`（仓库没有 ruff 配置，默认规则，与 CI 的 `python -m ruff check backend/` 同口径）通过；仓库根执行 `backend/scripts/check/check_file_size.py <两个文件>` 退出 0（上限 800）。
- 拆分：迁移文件定位与复制、引擎、临时 schema 生命周期、造数、快照与执行器入口放在 `level_backfill_world.py`；测试文件只放模型、生成器、样例与断言，给 7.3~7.5 留出行数余量。

驱动方式（现读 `app/core/migration_runner.py`、`tests/authz_world.py`、`tests/conftest.py` 的 `pg_only` 规则与 V200 / R200 后确定，即编排者裁定 ③ 的方案）：

- 正向入口：`MigrationRunner(engine=<世界引擎>, migrations_dir=<临时目录>).run_pending()`。启动的两处（`startup_registry._task_run_migrations`、`run_uvicorn` 预引导）都是 `MigrationRunner(database_url=settings.DATABASE_URL).run_pending()`：同一个类、同一入口，差别只在引擎由测试给出（`engine=` 时执行器不持有、不关闭它）与迁移目录。另用 `-o log_cli=true --log-cli-level=INFO` 单跑 f9 一例看执行器日志：取 advisory lock(306357029191) → 执行 `V200__partner_manager_edit_level_backfill.sql`（2 条语句）→「执行成功 1 个: ['200']」→ 释放 advisory lock。
- 迁移文件：按后缀 `__partner_manager_edit_level_backfill.sql` / `__rollback_partner_manager_edit_level_backfill.sql` 在 `backend/migrations/` 现找（`V(\d+)` / `R(\d+)` + 后缀整名匹配，前缀大小写口径同执行器），各须恰好一个且版本号相同，否则 fixture 报错；现得 200，测试与夹具里都没有写死 200。module 级 fixture `backfill_migrations` 用 `tmp_path_factory` 建空目录，把两个文件逐字节复制进去（复制后逐字节比对）作 `migrations_dir`：执行器在空 schema 里只扫得到这两个文件，不会去跑其余版本。
- 隔离：执行器每次访问库都经 `engine.begin()` / `connect()` 取新连接，不接受外部连接或事务，所以 `pg_world` 的「同一事务 + `SET LOCAL search_path` + 整体回滚」驱动不了它。改为每个样例（生成样例、`@example`、固定样例各一个）一个提交型临时 schema `authz_world_bf_<12 位随机十六进制>`：管理引擎（`NullPool`、默认 search_path）只执行 `CREATE SCHEMA`、`DROP SCHEMA … CASCADE` 与 `pg_namespace` 计数；世界引擎 `NullPool` + asyncpg `server_settings={"search_path": <该 schema>}`，每例断言其连接的 `current_schemas(false)` 恰为该 schema。建表复用权限世界的 `create_world_schema`（8 个枚举类型在临时 schema 内新建，六张表与部分唯一索引同 ORM 声明）；另按开发库现状预建 7 列 `schema_version`（执行器的 `_SCHEMA_VERSION_DDL` 再加 `operator` / `rollback_note`，即坑一的处置：7.2 不回滚，预建是为了与开发库形态一致，7.4 / 7.5 直接可用），`schema_migration_failures` 由执行器自己建。退出（含失败）时 `DROP SCHEMA … CASCADE`，再查 `pg_namespace` 中该名为 0（否则报错），引擎全部 dispose。每例一个新 schema，样例之间的数据、`schema_version` 中本版本的登记与回填表互不影响。
- 与任务原文「事务回滚」的差异：上面的取连接方式决定了回滚式隔离驱动不了 `run_pending()`。提交型临时 schema 只在临时 schema 内写数据、结束整体删除，public 不建对象、不写任何表（含 `schema_version`），运行前后用 postgres MCP 只读核对（见「副作用核对」）。没有改用临时测试库：执行器只需在 search_path 指定的 schema 里工作，不必整库运行。
- 连接串只取进程环境变量 `DATABASE_URL`（不是 PG 即报错；用例先由 `pg_only` 跳过）；SSL 口径同 `authz_world.pg_engine`。
- 坑二（`_run_backup`）：7.2 不调 `rollback_to`；夹具建出的执行器实例上 `_run_backup` 设为「一调用即失败」的实例属性（不改模块，不在 `run_pending` 路径上）。
- 坑三（advisory lock）：每例 `run_pending` 在独立连接上持全库共用的锁，时长为单次迁移；开发后端的启动迁移若恰在此时取锁只会排队。本任务期间各固定样例耗时稳定在 0.81~0.86 s（含建 / 删 schema），没有锁等待的迹象。

模型（测试内独立计算，不读生产代码的 `ROLE_MAP` / `EQCR_ROLE_ALIASES`，也不读迁移 SQL）：

- 别名取 `tests/role_map_expected.py`：合伙人 / 经理别名 = `EXPECTED_ROLE_MAP` 中取值为 (partner, edit) 或 (manager, edit) 的键（`signing_partner` / `partner` / `合伙人` → partner，`manager` / `项目经理` → manager）；EQCR 别名 = `EXPECTED_EQCR_ALIASES`（`eqcr`、`独立复核合伙人`）。
- 现行委派 = 委派未删除 ∧ 人员库记录未删除 ∧ 记录已关联用户；不看项目是否软删、不看全局角色；委派角色精确字符串比对。
- 逐行：已删除成员行不动；持 EQCR 别名现行委派 ⇒ (原项目角色, review)、rule `eqcr`（不论是否另持其他委派）；否则持合伙人 / 经理别名现行委派 ⇒ (partner 或 manager, edit)、rule `partner_manager`，同时持映射为 partner 与 manager 的取 partner；其余行不动；目标（项目角色，级别）已等于现值的不改、不记。

生成器（需求 4.6；`@settings(max_examples=5, deadline=None)`）：1~3 个项目各自现行 / 已软删；1~4 名用户，全局角色取 `UserRole` 全部 7 个取值；每人 0~3 条随机人员库记录（各约三分之一已删除、未关联用户），每条记录在每个项目约三分之二概率持一条现行委派、约三分之一概率另带一条已删除委派（遵守 `idx_assignment_project_staff`），同一用户因此可经多条记录在同一项目持多条现行委派；委派角色取四个别名集合全部 13 个键（另单列会触发改动的 7 个合伙人 / 经理与 EQCR 别名以提高命中）、`upper` / `capitalize` / `swapcase` 变体、首尾空白（空格、两个空格、制表符、全角空格）变体、长度 0~30 的任意串（排除 NUL 与代理码位）；每人在每个项目约三分之二概率一条未删除成员行、约三分之一概率另带一条已删除行（遵守 `idx_project_users_project_user`），（项目角色，级别）在 6 × 3 中任取，约一半带循环 / 科目范围与有效期。用户 0 在第一个项目另有一个「焦点」：一条现行、已关联的人员库记录持一条合伙人 / 经理或 EQCR 别名委派，外加一条未删除成员行。加焦点的理由：第一次统计（08:56:53，没有焦点）5 个生成样例全部 0 行改动，只验证了「不动」一面；加焦点后两次统计 5 个样例都有改动行（见下）。

- `@example` 两个：E1 只有一个已软删项目、没有用户（回填记录表照建且为空、版本照登记）；E2 两名用户持合伙人 / 经理与 EQCR 现行委派（含已软删项目上的）但都没有成员行（不补建、无记录）。

固定样例（`test_property_3_fixed_examples[<id>]`；期望按需求原文逐行写死在 `Row.expect`，每例先断言模型与写死的期望逐行相等，再跑与 Property 3 相同的全部断言）：9 个世界共 58 名用户、67 条人员库记录、68 条委派、61 条成员行，其中需求 4.2 改动 19 行、需求 4.3 改动 7 行、不改不记 35 行。

| id | 覆盖 | 改动 4.2 / 4.3 / 不改 |
|---|---|---|
| `f1-pm-five-aliases` | 五个合伙人 / 经理别名各一条现行委派：`signing_partner` auditor+readonly、`partner` auditor+readonly、`合伙人` readonly+readonly → partner+edit，`manager` auditor+readonly、`项目经理` qc+review → manager+edit；全局角色 auditor / readonly / qc / auditor / partner；另一用户在 P 有现行 `manager` 委派、没有成员行（不补建），他在 Q 的成员行没有委派（不动） | 5 / 0 / 1 |
| `f2-pm-partner-wins-global-role-ignored` | 两份人员库记录持 `manager` + `partner` → partner+edit；`项目经理` + `合伙人` → partner+edit；全局 admin 的 manager+review（持 `manager`）→ manager+edit；全局 eqcr、只持 `manager` → manager+edit；auditor+edit 持 `partner` → partner+edit（只差项目角色）；partner+edit 只持 `manager` → manager+edit（项目角色按映射改） | 6 / 0 / 0 |
| `f3-pm-soft-deleted-project-and-project-scope` | 已软删项目 D 上 auditor+readonly 持 `manager` → manager+edit、manager+edit 持 `signing_partner` → partner+edit；同一用户在现行项目 P 的行没有委派（不动）；委派只在 Q 的用户只改 Q 行、P 行不动 | 3 / 0 / 2 |
| `f4-eqcr-aliases-to-review` | `eqcr` + auditor+edit → auditor+review；`独立复核合伙人` + readonly+readonly → readonly+review；`独立复核合伙人` + manager+edit → manager+review（项目角色不动）；`eqcr` + partner+review（已是 review，不改不记）；已软删项目 D 上 `eqcr` + qc+edit → qc+review | 0 / 4 / 1 |
| `f5-eqcr-priority-over-partner-manager` | 经两份人员库记录同持：`manager` + `eqcr`、manager+edit → manager+review；`partner` + `独立复核合伙人`、partner+review → 不改（不升 edit）；`signing_partner` + `eqcr`、auditor+readonly → auditor+review；`项目经理` + `独立复核合伙人`、readonly+readonly → readonly+review | 0 / 3 / 1 |
| `f6-only-qc-auditor-unregistered` | 只持 `qc`、`质控`、`auditor`、`审计员`、`assistant`、`助理`、`观察员`、空串、`qc` + `观察员`，以及没有任何委派（10 行，含 manager+review、partner+readonly） | 0 / 0 / 10 |
| `f7-case-and-whitespace-variants` | `Manager`、` manager`、`manager `、`PARTNER`、`Signing_Partner`、`EQCR`（manager+edit 不降为 review）、` eqcr`（partner+edit）、`独立复核合伙人 `、全角空格 + `项目经理` | 0 / 0 / 9 |
| `f8-deleted-and-unlinked` | 已删除成员行（持现行 `manager`）不动；同一用户已删除行 + 现行行，只改现行行；委派已删、人员库记录已删、人员库记录未关联用户：不动；EQCR 委派所在记录已删 / EQCR 委派已删、另持现行 `manager` → 按 4.2 改为 manager+edit；只有已删记录上的 `eqcr`（manager+edit）不动；同一人员库记录在 P 一条已删 `eqcr` + 一条现行 `manager` → manager+edit | 4 / 0 / 6 |
| `f9-already-at-target-not-recorded` | 已等于目标值、不改不记：manager+edit 持 `manager`、partner+edit 持 `signing_partner`、partner+edit 持 `partner` + `manager`、auditor+review 持 `eqcr`、partner+review 持 `独立复核合伙人`；对照：manager+edit 持 `合伙人` → partner+edit | 1 / 0 / 5 |

需求 4.6 各维度在固定样例中的落点：成员行已软删（f8）；委派已软删（f8）；四个别名集合（f1、f2、f4、f6）；未登记串与大小写 / 空白变体（f6、f7）；人员库记录已软删 / 未关联用户（f8）；同一用户经多条人员库记录在同一项目持多条现行委派（f2、f5、f8）；项目已软删（f3、f4）。

断言（生成样例、`@example` 与固定样例相同）：

1. 执行器路径与隔离：世界连接的 `current_schemas(false)` 恰为该临时 schema；执行前临时 schema 里没有回填记录表、`schema_version` 为空、没有失败表；`run_pending()` 返回 `executed == [<现找版本>]`、`failed == []`；回填记录表建在该临时 schema 里（按 schema 限定名 `to_regclass`）；`schema_version` 恰一行 `{version, filename = V 副本文件名, checksum = 与执行器扫描同口径的 sha256, operator: None, rollback_note: None}`；`schema_migration_failures` 为空。
2. 成员行：id 集合与造数相同、执行前后相同（不增删、不补建）；每行（项目角色，级别）== 模型（被改动行取目标值，其余取执行前值）；其余 11 列（`id`、`project_id`、`user_id`、循环 / 科目范围、有效期起止、`is_deleted`、`deleted_at`、`created_at`、`updated_at`）逐行全等。
3. 回填记录：被改动行集合（执行前后（项目角色，级别）不同的行）== 回填记录的 `project_user_id` 集合 == 模型给出的改动行集合；每条记录的（迁移前项目角色，迁移前级别）== 执行前快照，（目标项目角色，目标级别，`rule`）== 模型，`recorded_at` 非空。
4. 其余表：`users`、`projects`、`staff_members`、`project_assignments`、`disclosure_notes` 全表逐行全列不变。

灵敏度核对（不是需求 12.5 的磁盘变异）：仓库外一次性 pytest 插件 `t72_mutant`（`-p t72_mutant`，经 `PYTHONPATH` 指向 `D:\pm_tmp`）挂 `pytest_fixture_setup` 包装钩子，在 `backfill_migrations` 建好临时目录之后按环境变量改写其中的 V 副本：每个锚点按预期次数出现才改（否则报错），改后记下命中次数与改前改后 sha256；worktree 里的迁移文件不动。每项只跑固定样例（`-k fixed_examples`，9 例），按 junit 区分 failure / error。下表是最终版测试文件上的一轮（09:08:15–09:11:06 +08:00，跑前跑后两个测试文件 blob 都是上表的值）；较早一轮（08:59:46–09:02:32，测试文件只差两段文档字符串）结果逐项相同。

| 变异 | 对 V 副本的改动（锚点命中次数） | 红的固定样例（都是 failure，0 error；其余通过） | 首条失败信息 |
|---|---|---|---|
| m00 对照 | 不改（0） | 无，9 passed | — |
| m01 去掉 EQCR 优先 | 三处 `CASE WHEN e.user_id IS NOT NULL THEN` 加 `AND p.user_id IS NULL`（3） | f5 | 成员行取值不一致：manager+edit 迁移后仍为 (manager, edit)，推导 (manager, review) |
| m02 `has_partner` 恒假 | `bool_or(role IN (…)) AS has_partner` → `false AS has_partner`（1） | f1、f2、f3、f9 | auditor+readonly（持 `signing_partner`）迁移后 (manager, edit)，推导 (partner, edit) |
| m03 去掉 `pu.is_deleted = false` | `targets` 的 WHERE 去掉该条件（1） | f8 | 已删除的 auditor+readonly 行迁移后 (manager, edit)，推导不动 |
| m04 别名列表去掉 `合伙人` | 两处 `, '合伙人'` 删除（2） | f1、f2、f9 | readonly+readonly（持 `合伙人`）迁移后不动，推导 (partner, edit) |
| m05 去掉 `sm.is_deleted = false` | `live_assign` 的 WHERE 去掉该条件（1） | f8 | 人员库记录已删的 auditor+readonly 行迁移后 (manager, edit)，推导不动 |
| m06 `changed` 不过滤已等于目标值的行 | 去掉 `WHERE (prior_role, prior_level) IS DISTINCT FROM (target_role, target_level)`（1） | f4、f5、f9 | 被改动行与回填记录不一致：有记录而未改动 [持 `eqcr` 的 partner+review 行] |
| m07（另加）去掉 `pa.is_deleted = false` | `live_assign` 的 WHERE 去掉该条件（1） | f8 | 委派已删的 auditor+readonly 行迁移后 (manager, edit)，推导不动 |
| m08（另加）EQCR 行项目角色改为 partner | `THEN pu.role` → `THEN 'partner'::projectuserrole`（1） | f4、f5、f9 | auditor+edit（持 `eqcr`）迁移后 (partner, review)，推导 (auditor, review) |
| m09（另加）委派角色归一化 | `pa.role` → `lower(btrim(pa.role)) AS role`（1） | f7 | 持 `Manager` 的 auditor+readonly 行迁移后 (manager, edit)，推导不动 |
| m10（另加）只看现行项目 | `live_assign` 加 `JOIN projects pr ON pr.id = pa.project_id AND pr.is_deleted = false`（1） | f3、f4 | 已软删项目 D 上的 auditor+readonly 行迁移后不动，推导 (manager, edit) |
| m11（另加）`rule` 对调 | `THEN 'eqcr' ELSE 'partner_manager'` 两值对调（1） | f1、f2、f3、f4、f5、f8、f9 | 回填记录内容不对：rule 为 eqcr，应为 partner_manager |
| m12（另加）迁移前值记成目标值 | 插入回填记录的 `prior_role, prior_level` 换成 `target_role, target_level`（1） | f1、f2、f3、f4、f5、f8、f9 | 回填记录内容不对：迁移前值为 (partner, edit)，应为 (readonly, readonly) |

- 编排者列出的 6 项（m01~m06）都红在固定样例测试函数体内的断言上（`AssertionError`），不是收集、夹具或 SQL 错误：13 份 junit 的 errors 都是 0，变异后的 SQL 都合法、执行器照常执行成功，红出自成员行与回填记录的断言。另加的 6 项（m07~m12）核对委派删除条件、EQCR 行项目角色、精确比对、已软删项目与回填记录两组字段的断言，也都红。
- 迁移文件前后核对（两轮各在开始前与结束后取一次 `git hash-object --path`、`--no-filters` 与磁盘 sha256）：V200 `c9e1138f9aa3f2ecd20099de4e8a28f54cea73bb`（sha256 `a7de9ae3…`）、R200 `5e21d438aebff0a12ccdd713e9c574cd0b5ff0ca`（sha256 `c9dc53ee…`），四次都相同。

运行（仓库外一次性启动器 `D:\pm_tmp\t72_run.py`：cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -B -m pytest tests/test_level_backfill_migration_pg.py -q -p no:cacheprovider --tb=short -rfEs --junitxml=<仓库外> --basetemp=<仓库外>`；子进程 env 设 `PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外）：

| 轮次 | env | 结果 | 时刻（+08:00）/ 耗时 |
|---|---|---|---|
| SQLite 轮 | 去掉 `DATABASE_URL` | 10 skipped（性质测试 1 + 固定样例 9，原因 `requires PostgreSQL`），0 failed / 0 error | 09:03:48 / 1.87 s |
| PG 轮 | `DATABASE_URL` 由启动器从实施树 `app.core.config.settings.DATABASE_URL` 取出（`postgresql+asyncpg`，不打印），只放进子进程 env | 10 passed、0 skipped（性质测试 5.89 s，固定样例每例 0.81~0.86 s） | 09:04:00 / 15.32 s |
| PG 轮 + `--hypothesis-show-statistics` | 同上 | 10 passed、0 skipped | 09:04:19 / 15.47 s |

- 落盘的输出与 junit 已把连接串与口令替换为占位，核对不含 `postgresql` / `asyncpg` 字样。较早几轮（08:55~08:58：SQLite 10 skipped、PG 10 passed、两次只跑性质测试的统计）是加焦点前后的同一批用例，结论相同。

hypothesis 统计（最终版 `test_property_3_backfill_matches_row_model`）：生成阶段 4.25 s，每例约 830~872 ms（其中生成数据 0~9 ms），5 passing / 0 failing / 0 invalid，因 `max_examples=5` 停止；事件：「被改动行：需求 4.2 1 条，需求 4.3 0 条」60%，「需求 4.2 2 条，需求 4.3 0 条」20%，「需求 4.2 2 条，需求 4.3 1 条」20%；成员行 1 / 3 / 7 / 11 / 13 条各 20%。两个 `@example` 在显式阶段执行，不计入统计。加焦点之前那次统计（08:56:53）：5 个样例的事件都是「需求 4.2 0 条，需求 4.3 0 条」，成员行 0 / 2 / 6 / 7 / 9 条。

副作用核对：

- 本地开发库（postgres MCP 只读）：运行前（00:56:12 UTC）与全部运行之后（01:11:39 UTC；中间 00:56:45、01:03:50、01:05:12、01:07:54 也各查一次）结果相同：`authz_world%` schema 0 个，非系统 schema 0 个，任一 schema 中 `project_user_level_backfill` 0 个，`projectuserrole` 类型只有 public 的 1 个；public `schema_version` 199 行、最高 199（按数值与按字符串相同）、没有 200；`schema_migration_failures` 0 行；`project_users` 88（最大 `updated_at` 2026-10-07 08:09:10）、`project_assignments` 86（2026-10-07 04:51:58）、`staff_members` 215（2026-10-15 06:19:08）、`users` 94（2026-10-07 04:51:58）、`projects` 85（2026-10-20 11:14:02）、`logs` 94544（最大 `created_at` 2026-10-20 23:50:03）、`evidence_outbox` 748（2026-10-20 23:38:39），全部不变。
- 两棵树：基线树 `git status --porcelain=v1 -uall --ignored` 1730 行，与前置步骤 B 清理后逐字相同，HEAD 仍为 B；实施树与清理后相比只多出两个新文件（`?? backend/tests/level_backfill_world.py`、`?? backend/tests/test_level_backfill_migration_pg.py`），没有新增 `.pyc`、`.hypothesis` 或 `backend/storage` 产物。按创建 / 修改时间扫描两棵树（排除 `.git`、`node_modules`）：08:30 之后变动的只有两棵树的 `backend` 目录（删除 `backend/storage`）、实施树的本文件、`backend/tests` 目录与两个新文件；09:04 之后两棵树都是 0 项。
- 一次性文件都在 `D:\pm_tmp\t72_*`（启动器、插件、灵敏度驱动、探针、junit、输出、`--basetemp` 与 hypothesis 目录），写入本节后删除（见本节末）。

与任务原文 / design 的偏差：

1. 隔离：任务原文与 design §8.2 写「权限世界 PG 版（临时 schema、事务回滚）」；实际是提交型临时 schema、结束整体删除（理由见「驱动方式」，即编排者裁定 ③）。建表仍用权限世界同一份 `create_world_schema`。
2. 迁移号：design 写 V198；实际按文件名后缀现找，当前为 200（见「任务 7.1」）。
3. 生成器：覆盖需求 4.6 的全部维度；另加「焦点」与偏向命中的别名分支，只改变分布，不缩小取值空间。
4. 断言比 design Property 3 原文多三项：成员行其余 11 列逐行不变、`disclosure_notes` 也不变、执行器登记 / 失败表与 search_path 隔离。

给 7.3~7.5 的说明（同一测试文件，夹具在 `level_backfill_world.py`）：

- `backfill_world(world)` 是异步上下文：建 schema、造数后给出 `BackfillWorld`（`snapshot()`、`exists(table)`、`search_path()`、`runner(migrations)`、`run_pending(migrations)`），退出即删 schema；同步包装只有 `run_forward_once`。模型 `_model` 与断言 `_check_executor` / `_check_member_rows` / `_check_other_tables` 可直接复用；当前测试文件 429 行（上限 800）。
- 幂等（7.3）：同一个世界里第二次 `run_pending()` 不会再执行 V 副本（版本已登记，`executed == []`），验证不到 SQL 自身的幂等。可先删掉临时 schema `schema_version` 中本版本那一行再 `run_pending()`（仍走执行器路径），或按执行器同口径（`_split_sql_statements` + 一个事务内逐句 `exec_driver_sql`）直接执行 V 副本；不能直接再调 `_apply_migration`（它会再插一次同版本，撞 `schema_version.version` 的唯一约束）。用哪种须在验收记录写明。
- 往返（7.4）：`rollback_to(str(int(n) - 1))` 即可（临时 schema 里只登记了 n，不必另插登记；末尾按 `version = target` 的 UPDATE 匹配不到行也不报错；执行器按字符串比较 `version > :target`，n 与 n−1 位数相同时成立，200 / 199 成立）。夹具已把 `_run_backup` 换成一调用即失败，用 `rollback_to` 时须换成记录调用、不跑 `pg_dump` 的替身；回滚追踪列已在临时 `schema_version` 里，`rollback_to` 末尾的 UPDATE 不会缺列。
- 执行语义与对账（7.5）：`run_pending()` 捕获单文件异常并写临时 schema 的 `schema_migration_failures`（`attempt_count` 递增），版本不登记；需求 12.7 的对账要读生产 `ROLE_MAP`，与本文件只读期望表的模型分开写；漂移检测器 `KNOWN_ALLOWLIST` 的登记（用户裁定 3）也在 7.5。

清理：本任务的一次性文件（`D:\pm_tmp\t72_*` 共 125 项：启动器、插件、灵敏度驱动、探针、junit、输出、`--basetemp` 与 hypothesis 目录，目录内共 2298 个文件；另有导入插件时生成的 `D:\pm_tmp\__pycache__`）于 2026-10-21 09:16:55 +08:00 删除，删除后 `D:\pm_tmp` 为空。本行由仓库外一次性脚本 `t72b_cleanup_note.py` 写入，写入后删除。

### 任务 7.3：回填幂等的性质测试（真 PG）（2026-10-21）

本任务只改两个测试侧文件（7.2 新增、均未跟踪），没有改生产代码、迁移文件与既有测试。

| 文件 | 7.2 时 blob（行数 `split("\n")` / splitlines） | 现 blob（`--path` 与 `--no-filters` 相同） | 现行数（`split("\n")` / splitlines） | 字节 | sha256 |
|---|---|---|---|---|---|
| `backend/tests/test_level_backfill_migration_pg.py` | `0af1abf58b28a488752572f9f6ad666434ef7160`（429 / 428） | `d7436dfa0e657dd76a7ff19e5011c8d3d4a563ec` | 638 / 637 | 42588 | `94ab02120a78bc83a7ff8f25522012d04c03950e94859e83166ceda3ebed9fb1` |
| `backend/tests/level_backfill_world.py`（夹具模块） | `505f2d94314cfc9b58a023c0f052e40c5de2af23`（426 / 425） | `ee1e0a880a663e07f172e1a1756299f2e0ddf7eb` | 490 / 489 | 26866 | `65ec4786161febfbfed72be0af2127393602b22606d76e6d9039dbf2225ae852` |

- UTF-8 无 BOM、只有 LF、末尾有换行。`ruff check --no-cache`（ruff 0.11.12，仓库没有 ruff 配置，默认规则）通过；仓库根执行 `backend/scripts/check/check_file_size.py <两个文件>` 退出 0（上限 800，脚本按 splitlines 计）。
- 相对 7.2 的改动（7.2 的两个 blob 不在对象库中：从 Kiro 本地历史按 git blob 取回 7.2 原文，再 `git diff --no-index` 比对）：夹具模块只增不改——模块说明加「四、第二次执行」，`BackfillWorld` 加 `forget_version`、`override_member_rows`，新增 `RepeatRun`、`_forward_twice`、`run_forward_twice`；`_forward_once` 的五步（search_path → 快照 → `run_pending()` → 快照 → 回填表是否在临时 schema）原样移进 `_run_first` 供两处共用（新增 70 行、删除 6 行，删除的就是被移走的这几行）。测试文件 7.2 的第 1~428 行只改了模块文档字符串（标题补任务 7.3、需求 4.7、Property 4，另加两条说明）与导入（`Iterable`、`replace`、`RepeatRun`、`run_forward_twice`）；7.2 的模型、生成器、`@example`、固定样例、断言函数与两个测试函数逐行未变，7.3 的内容全部追加在其后。

第二次执行的方式与理由：

- 用的是首选方式：同一个世界正向执行一次（快照 A）后，`forget_version(n)` 在临时 schema 里执行 `DELETE FROM schema_version WHERE version = :n`（断言恰删 1 行），再调用同一个 `MigrationRunner(engine=<世界引擎>, migrations_dir=<临时目录>).run_pending()`（快照 B）。没有用备选的「按执行器同口径直接执行 V 副本」。
- 理由：不删登记时执行器判定本版本已应用，`executed == []`，V 副本根本不执行，验证不到 SQL 自身的幂等（7.2 已指出）。现读 `_run_pending_inner`：删登记后 `ensure_schema_version_table` 见表为空会去补登记 V001 基线，但临时目录只有 V200 / R200，`_find_v001()` 为空，不补登记；`get_applied_versions()` 为空 ⇒ 待执行 = [V200] ⇒ `_apply_migration` 整文件一个事务执行，再插一次本版本登记，随后 `_clear_failure`。所以第二次与第一次走同一条启动路径（advisory lock、两张系统表、扫描、执行、登记），差别只在执行时回填记录表与成员行已是第一次后的状态。灵敏度 m01（去掉回填表 `IF NOT EXISTS`）只在第二次执行时报 `DuplicateTableError`、Property 3 的固定样例照常通过，可证第二次确实重新执行了 V 副本。
- 两次之间除这一行登记外不写任何表（Property 4 断言他途改动为空、第二次执行前的快照 == 快照 A）。需求 4.5 用例另经 `override_member_rows` 用原生 UPDATE 只改指定成员行的（项目角色，级别）两列（不经 ORM，`updated_at` 不变）。

新增测试函数（均 `pg_only`；每个样例一个新的提交型临时 schema，隔离与 7.2 相同）：

- `test_property_4_backfill_is_idempotent`：`@settings(max_examples=5, deadline=None)`、`@given(world=_worlds())`（7.2 的生成器原样复用）、`@example(world=_E1)`、`@example(world=_E2)`；函数头注释 `# Feature: partner-manager-edit-permission, Property 4: 回填幂等`；`hypothesis.event` 只用于统计。
- `test_property_4_fixed_examples[f1-pm-five-aliases]` ~ `[f9-already-at-target-not-recorded]`（9 个）：复用 `_FIXED`，先断言模型 == `Row.expect`，再跑与 Property 4 相同的全部断言。第一次执行被需求 4.2 改动 19 行、4.3 改动 7 行（f1~f5、f8、f9 有改动行，f6、f7 没有）。
- `test_requirement_4_5_existing_records_not_overwritten`（需求 4.5「该行已有回填记录时保留原记录」；两次之间有他途改动，不是 Property 4 本体）：世界 `r4.5-existing-records-not-overwritten`，项目 P 现行、D 已软删，10 名用户各一条成员行。第一次改动 7 行（4.2 五行、4.3 两行）、3 行不改；随后用原生 UPDATE 改 8 行，再按 Property 4 的同一方式执行第二次。期望写死在 `_R45_STEPS`，后两列另由 `_r45_from_model`（对他途改动后的数据再跑一次模型）核对：

| 用户 | 委派与第一次结果 | 他途改成 | 第二次后 | 第二次后的回填记录 |
|---|---|---|---|---|
| 0 | `manager`：auditor+readonly → manager+edit（4.2） | manager+review | manager+edit | 第一次的记录不变 |
| 1 | `partner`：auditor+readonly → partner+edit | 不改 | partner+edit | 第一次的记录不变 |
| 2 | `eqcr`：auditor+edit → auditor+review（4.3） | auditor+readonly | auditor+review | 第一次的记录不变 |
| 3 | `独立复核合伙人`：qc+edit → qc+review | manager+readonly | manager+review（项目角色取第二次执行前的值） | 第一次的记录不变（目标值仍为 qc+review） |
| 4 | `signing_partner`（带范围与有效期）：auditor+readonly → partner+edit | manager+review | partner+edit | 第一次的记录不变 |
| 5 | `项目经理`：readonly+readonly → manager+edit | partner+edit | manager+edit | 第一次的记录不变 |
| 6 | 已软删项目 D 上 `manager`：auditor+readonly → manager+edit | auditor+readonly（改回迁移前值） | manager+edit | 第一次的记录不变 |
| 7 | `manager`：manager+edit 已等于目标值，不改不记 | manager+readonly | manager+edit | 第二次新增一条：迁移前 manager+readonly，目标 manager+edit，rule `partner_manager` |
| 8 | `manager` + `eqcr`（两份人员库记录）：partner+review 已等于目标值（EQCR 优先），不改不记 | 不改 | partner+review | 没有记录 |
| 9 | 只持 `qc`：auditor+readonly 不动 | manager+edit | manager+edit（第二次也不碰） | 没有记录 |

断言（Property 4 的生成样例、`@example` 与固定样例相同，见 `_check_twice`）：

1. 第一次执行仍满足 Property 3 的全部断言：直接调用 7.2 的 `_check_executor`、`_check_member_rows`、`_check_other_tables`（未改）。
2. 两次之间没有写入：他途改动为空，第二次执行前的快照 == 快照 A。
3. 第二次经执行器执行（`_check_second_run`）：删掉的本版本登记恰 1 行；`run_pending()` 返回 `executed == [n]`、`failed == []`；`schema_migration_failures` 为空；临时 `schema_version` 与第一次后逐值相同（version、filename、checksum、operator、rollback_note）。
4. 快照 B == 快照 A（`_check_idempotent`）：成员行 id 集合相同，每行全部列逐值相同（含 `updated_at`）；回填记录表存在，`project_user_id` 集合双向包含（不新增、不消失），每条记录全部列逐值相同（迁移前值、目标值、`rule`、`recorded_at`）；`users`、`projects`、`staff_members`、`project_assignments`、`disclosure_notes` 全表逐行全列相同。失败信息逐行列出被改的列（第一次后，第二次后）。

需求 4.5 用例的断言：第一次满足 Property 3；他途改动恰改到 8 行且只改两列（其余列、回填记录、版本登记与失败表都不变）；第二次经执行器执行（同第 3 条）；第二次后 10 行的（项目角色，级别）== `_R45_STEPS` 第二列，id 集合与其余列不变；回填记录覆盖的行 == 第三列非空的 8 行，其中 7 条与第一次逐值相同（含 `recorded_at`），1 条为第二次新增、内容等于期望且 `recorded_at` 非空；其余五张表与第一次后相同。

灵敏度核对（不是需求 12.5 的磁盘变异；做法同 7.2）：仓库外一次性 pytest 插件 `t73_mutant`（`-p t73_mutant`，经 `PYTHONPATH` 指向 `D:\pm_tmp`）挂 `pytest_fixture_setup` 包装钩子，在 `backfill_migrations` 建好临时目录之后按环境变量改写其中的 V 副本：每个锚点按预期次数出现才改（否则报错），改后记下命中次数与改前改后 sha256（改前均为 V200 原文的 `a7de9ae3…`，m00 外改后都不同）；worktree 里的迁移文件不动。每项只跑固定样例与需求 4.5 用例（`-k "fixed_examples or requirement_4_5"`：Property 3 固定样例 9 个、Property 4 固定样例 9 个、需求 4.5 用例 1 个，共 19 个），按 junit 区分 failure / error。运行于 10:01:41–10:06:44 +08:00（每项约 24~27 s），前后两个测试文件 blob 都是上表的现值，V200 / R200 的 blob 与 sha256 前后相同。

| 变异 | 对 V 副本的改动（锚点命中次数） | 红的用例（failures / errors，共 19） | 首条失败信息 |
|---|---|---|---|
| m00 对照 | 不改（0） | 无（0 / 0），19 passed | — |
| m01 回填表去掉 `IF NOT EXISTS`（必做①） | `CREATE TABLE IF NOT EXISTS project_user_level_backfill (` → `CREATE TABLE project_user_level_backfill (`（1） | Property 4 固定样例 f1~f9 与需求 4.5 用例（10 / 0）；Property 3 固定样例全通过 | `_check_second_run`：「f1-pm-five-aliases：第二次执行器应恰执行版本 200 且无失败，实际 executed=[]，failed=[FailureRecord(… error_type='ProgrammingError' … DuplicateTableError: relation "project_user_level_backfill" already exists …)]」 |
| m02 `DO NOTHING` → `DO UPDATE` 覆盖迁移前值（必做②a） | `ON CONFLICT (project_user_id) DO NOTHING` → `DO UPDATE SET prior_role = EXCLUDED.prior_role, prior_permission_level = EXCLUDED.prior_permission_level`（1） | 需求 4.5 用例（1 / 0） | 「回填记录不对（需求 4.5）：用户3（全局 partner）在 P 的成员行0（qc, edit）：第一次的记录被改写 {'prior_permission_level': ('edit', 'readonly'), 'prior_role': ('qc', 'manager')}」 |
| m03 `DO UPDATE` 覆盖目标值与 rule（必做②b） | 同一锚点 → `DO UPDATE SET target_role = …, target_permission_level = …, rule = EXCLUDED.rule`（1） | 需求 4.5 用例（1 / 0） | 「…用户3（全局 partner）在 P 的成员行0（qc, edit）：第一次的记录被改写 {'target_role': ('qc', 'manager')}」 |
| m04 `DO UPDATE` 刷新 `recorded_at`（必做②c） | 同一锚点 → `DO UPDATE SET recorded_at = now()`（1） | 需求 4.5 用例（1 / 0） | 「…用户2（全局 auditor）在 P 的成员行0（auditor, edit）：第一次的记录被改写 {'recorded_at': (…02:03:40.539427, …02:03:41.058495)}」 |
| m05 `changed` 去掉「已等于目标值」过滤（必做③） | `SELECT * FROM targets WHERE (prior_role, prior_level) IS DISTINCT FROM (target_role, target_level)` → `SELECT * FROM targets`（1） | Property 3 与 Property 4 的固定样例 f4、f5、f9，需求 4.5 用例（7 / 0） | `_check_member_rows`（第一次执行的 Property 3 断言）：「f4-eqcr-aliases-to-review：被改动行与回填记录不一致：改动而无记录 []，有记录而未改动 ['用户3（全局 eqcr）在 P 的成员行0（partner, review）']」 |
| m06（另加）每次执行先清空回填记录 | 建表语句后插入 `DELETE FROM project_user_level_backfill;`（1） | Property 4 固定样例 f1~f5、f8、f9，需求 4.5 用例（8 / 0） | `_check_idempotent`：「f1-pm-five-aliases：第二次执行后第一次的回填记录消失 [5 行]」 |
| m07（另加）表里已有任何记录就不再记 | 插入回填记录的 `SELECT … FROM changed` 加 `WHERE NOT EXISTS (SELECT 1 FROM project_user_level_backfill)`（1） | 需求 4.5 用例（1 / 0） | 「第二次执行后回填记录覆盖的行不对：缺少 ['用户7（全局 auditor）在 P 的成员行0（manager, edit）']」 |
| m08（另加）每次执行刷新全部记录的 `recorded_at` | 末尾 UPDATE 后追加 `UPDATE project_user_level_backfill SET recorded_at = now();`（1） | Property 4 固定样例 f1~f5、f8、f9，需求 4.5 用例（8 / 0） | `_check_idempotent`：「f1-pm-five-aliases：第二次执行覆盖了第一次的回填记录（列 →（第一次后，第二次后））：… {'recorded_at': (…)}」 |
| m09（另加）已有记录的行不再改 | `changed` 的过滤再加 `AND NOT EXISTS (SELECT 1 FROM project_user_level_backfill b WHERE b.project_user_id = targets.pu_id)`（1） | 需求 4.5 用例（1 / 0） | 「第二次执行后的成员行不对：{(0, 0): ('manager', 'review'), …}」（被他途改动的行没有再改回目标值） |
| m10（另加）经理分支目标角色取记录的迁移前角色 | `ELSE 'manager'::projectuserrole END AS target_role` → `ELSE COALESCE((SELECT b.prior_role FROM project_user_level_backfill b WHERE b.project_user_id = pu.id), 'manager'::projectuserrole) END AS target_role`（1） | Property 4 固定样例 f1、f2、f3、f8，需求 4.5 用例（5 / 0） | `_check_idempotent`：「f1-pm-five-aliases：第二次执行改动了成员行（列 →（第一次后，第二次后））：用户4（全局 partner）在 P 的成员行0（qc, review）：{'role': ('manager', 'qc')}」 |
| m11（另加）去掉 `ON CONFLICT` 子句 | 删除 `ON CONFLICT (project_user_id) DO NOTHING`（1） | 需求 4.5 用例（1 / 0） | `_check_second_run`：「r4.5-existing-records-not-overwritten：第二次执行器应恰执行版本 200 且无失败，实际 executed=[]，failed=[FailureRecord(… error_type='IntegrityError' … UniqueViolationError: duplicate key value violates unique constraint "project_user_level_backfill_pkey" …)]」 |

- 12 份 junit 的 errors 都是 0；红的用例都是 `AssertionError`，落在测试函数体或其调用的断言函数（`_check_second_run`、`_check_idempotent`、`_check_member_rows`、需求 4.5 用例本体）上，不是收集、夹具或 SQL 语法错误。m01、m11 的 SQL 错误由执行器捕获并记入临时失败表，红出自「`executed == [n]` 且 `failed == []`」的断言。
- 必做三项中，m01（第二次建表）与 m05 由 Property 4 固定样例直接打红（m05 红在第一次执行的 Property 3 断言上）；`DO UPDATE` 三种写法（m02~m04）只有需求 4.5 用例打红：没有他途改动时第二次执行的 `changed` 为空、不触发 `ON CONFLICT`，Property 4 本体按定义观测不到它们，这正是另设需求 4.5 用例的原因。m07、m09、m11 同理。

运行（仓库外一次性启动器：上一次派发的 `D:\pm_tmp\t73_run.py`，本次复核的 `t73b_run.py` 只改了输出文件前缀；cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -B -m pytest tests/test_level_backfill_migration_pg.py -q -p no:cacheprovider --tb=short -rfEs --junitxml=<仓库外> --basetemp=<仓库外>`；子进程 env 设 `PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外；PG 轮的 `DATABASE_URL` 由启动器经子进程从实施树 `app.core.config.settings.DATABASE_URL` 取出（`postgresql+asyncpg`，不打印），只放进 pytest 子进程 env）：

| 轮次 | 附加参数 | 结果 | 时刻（+08:00）/ 耗时 |
|---|---|---|---|
| SQLite 轮（上一次派发） | env 去掉 `DATABASE_URL` | 21 skipped（Property 3、4 各 1 + 固定样例 9 × 2 + 需求 4.5 用例 1，原因 `requires PostgreSQL`），0 failed / 0 error | 09:55:41 / 1.83 s |
| PG 轮（上一次派发） | — | 21 passed、0 skipped | 09:55:54 / 35.90 s |
| PG 轮 + 统计（上一次派发） | `--hypothesis-show-statistics` | 21 passed、0 skipped | 09:56:55 / 35.94 s |
| 灵敏度 m00~m11（上一次派发） | `-p t73_mutant -k "fixed_examples or requirement_4_5"`，env 另设 `T73_MUTANT`、`T73_MUTANT_LOG`、`PYTHONPATH` | 见上表 | 10:01:41–10:06:44 |
| PG 轮（本次复核，最终版文件） | — | 21 passed、0 failed、0 error、0 skipped（Property 3 生成 5.59 s、Property 4 生成 8.57 s；固定样例 Property 3 每例 0.78~0.81 s、Property 4 每例 1.19~1.26 s；需求 4.5 用例 1.27 s） | 10:15:58 / 35.45 s |

- 三轮与灵敏度都在现值文件上运行：两个测试文件最后修改于 09:50:04（夹具）与 09:54:50（测试），早于全部运行；灵敏度驱动在开始与结束各取一次 blob，均为上表现值。Property 3 原有的 10 个用例在三次 PG 轮中都通过，在 m00 对照与 m01~m04、m06~m11 中其固定样例也都通过（m05 红在 f4、f5、f9，同 7.2 的 m06）。
- 落盘的输出、junit 与汇总 JSON 由启动器把完整连接串、`用户:口令@主机:端口` 与 `用户:口令` 替换为占位；本次另把 `D:\pm_tmp` 下 47 个输出 / junit / JSON 文件逐个扫描：连接串各片段、独立出现的口令、`postgresql://` / `postgresql+asyncpg://` 前缀都是 0 处，占位也是 0 处（没有需要替换的内容）。灵敏度 junit 的失败信息里出现的 `sqlalchemy.dialects.postgresql.asyncpg` 是异常类所在的模块名，不是连接串。

hypothesis 统计（PG 轮 + 统计，09:56:55；两个 `@example` 在显式阶段执行，不计入）：

- `test_property_3_backfill_matches_row_model`：生成阶段 4.14 s，每例约 789~876 ms（其中生成数据 0~15 ms），5 passing / 0 failing / 0 invalid，因 `max_examples=5` 停止；事件：「被改动行：需求 4.2 1 条，需求 4.3 0 条」60%，「需求 4.2 2 条，需求 4.3 0 条」40%；成员行 4 条 40%，1 / 3 / 5 条各 20%。
- `test_property_4_backfill_is_idempotent`：生成阶段 6.29 s，每例约 1240~1274 ms（其中生成数据 0~6 ms），5 passing / 0 failing / 0 invalid，因 `max_examples=5` 停止；事件：「第一次被改动行 1 条（需求 4.2 1 条，需求 4.3 0 条）」80%，「2 条（需求 4.2 2 条，需求 4.3 0 条）」20%。
- 这一轮 5 个生成样例都没有命中需求 4.3 的改动行（7.2 的统计轮有一例命中）；4.3 的幂等由固定样例 f4、f5（第一次改动 7 行）与需求 4.5 用例的用户 2、3 覆盖。生成器沿用 7.2，没有为此调整分布。

副作用核对：

- 本地开发库（postgres MCP 只读）：本次 PG 轮之前（02:14:45 UTC）与之后（02:17:23 UTC）结果相同：`authz_world%` schema 0 个，非系统 schema 0 个，任一 schema 中 `project_user_level_backfill` 0 个，`projectuserrole` 类型 1 个（public）；public `schema_version` 199 行、最高 199（按数值与按字符串相同）、没有 200；`schema_migration_failures` 0 行；`project_users` 88（最大 `updated_at` 2026-10-07 08:09:10）、`project_assignments` 86（2026-10-07 04:51:58）、`staff_members` 215（2026-10-15 06:19:08）、`users` 94（2026-10-07 04:51:58）、`projects` 85（2026-10-20 11:14:02）、`logs` 94544（最大 `created_at` 2026-10-20 23:50:03）、`evidence_outbox` 748（`created_at` / `updated_at` 2026-10-20 23:38:39）。以上与 7.2 记录的值逐项相同，上一次派发的各轮运行也没有在开发库留下可见改动。
- 两棵树：本次 PG 轮、ruff 与行数门之前（10:15:47）与之后（10:17:29）各取一次：两棵树 HEAD 都是 B `a02a21419a7ffef349384a766798b7ac291fca05`；`git status --porcelain=v1 -uall --ignored` 逐字相同（实施树 74574 行：` M` 23、`??` 23、`!!` 74528；基线树 1730 行、全部 `!!`，与 7.2 记录相同）；按创建 / 修改时间扫描两棵树（排除 `.git`、`node_modules`），10:15:47 之后变动的条目 0 个；V200 / R200 与两个测试文件的 blob、sha256 前后相同（V200 `c9e1138f9aa3f2ecd20099de4e8a28f54cea73bb`、R200 `5e21d438aebff0a12ccdd713e9c574cd0b5ff0ca`，同「任务 7.1」）。

与任务原文 / design 的偏差：

1. 第二次执行的方式是编排者给出的首选（删临时登记后再 `run_pending()`），没有改用直接执行 V 副本；隔离沿用 7.2 的提交型临时 schema（同「任务 7.2」偏差 1）。
2. 断言比 design Property 4 原文多四项：第二次也经执行器执行（`executed == [n]`、`failed == []`）、重新登记的内容与第一次相同、失败表为空、其余五张表不变。
3. 需求 4.5「已有记录不覆盖」另写成单独用例：Property 4 本体两次之间没有写入，第二次 `changed` 为空，观测不到 `ON CONFLICT` 的行为（见灵敏度 m02~m04）。

上一次派发与本次复核：上一次派发写完代码、跑完三轮与 m00~m11 灵敏度之后、写验收记录之前中断（产物在 `D:\pm_tmp\t73_*`，没有残留进程）。本次没有推倒重来：从 Kiro 本地历史按 blob 取回 7.2 原文比对，确认实现符合要求、7.2 原有用例没有削弱，未改任何文件；据现有产物整理上表，并在最终版文件上补跑一次 PG 轮与副作用核对。

给 7.4~7.5 的说明（同一测试文件，夹具在 `level_backfill_world.py`）：

- 可复用：`run_forward_twice(world, migrations, overrides)` 返回 `RepeatRun`（`first` / `between` / `second` / `again`）；`BackfillWorld.override_member_rows` 按 id 只改两列，可直接用于 Property 5「回滚前随机挑行改成非目标值」；断言函数 `_check_second_run`、`_check_idempotent`、`_rest`、`_diff` 与 7.2 的 `_check_*` 都在测试文件里。
- 往返（7.4）：需在夹具里加「正向一次或两次 → 他途改动 → `rollback_to(str(int(n) - 1))`」的入口；`runner()` 建出的执行器 `_run_backup` 是一调用即失败（`_no_backup`），用 `rollback_to` 时须换成记录调用、不跑 `pg_dump` 的替身（7.2 已说明）。
- 失败语义（7.5）：灵敏度 m01、m11 实测执行器捕获单文件异常，`failed` 里给出 `FailureRecord(version, filename, error_type, error_message)`，版本不登记——需求 4.10 的「预建冲突对象使正向失败」可按同一口径断言。
- 行数余量：测试文件现 637 行（splitlines，上限 800），只剩 163 行；7.4、7.5 若放不下，可先把模型、生成器与固定样例挪到夹具模块或新的非测试模块（夹具现 489 行），测试函数仍留在本文件。

清理：上一次派发与本次复核的一次性文件——`D:\pm_tmp\t73_*` 63 项（启动器、插件、灵敏度驱动与整理脚本，三轮与 m00~m11 的 junit / 输出 / 变异日志、汇总，`--basetemp` 与 hypothesis 目录；目录内共 139 个文件）与 `D:\pm_tmp\t73b_*` 17 项（复核用启动器与核对脚本、取回的 7.2 原文副本、本节草稿，最终 PG 轮的 junit / 输出、`--basetemp` 与 hypothesis 目录；目录内共 112 个文件）——于 2026-10-21 10:25:34 +08:00 删除，删除后 `D:\pm_tmp` 为空，没有其他前缀的文件。本行在删除之后直接编辑写入。

### 任务 7.4：回填往返的性质测试（真 PG）（2026-10-21）

本任务只改两个测试侧文件、新增一个辅助模块（均未跟踪），没有改生产代码、迁移文件与既有测试。

| 文件 | 7.3 时 blob（行数 `split("\n")` / splitlines） | 现 blob（`--path` 与 `--no-filters` 相同） | 现行数（`split("\n")` / splitlines） | 字节 | sha256 |
|---|---|---|---|---|---|
| `backend/tests/test_level_backfill_migration_pg.py` | `d7436dfa0e657dd76a7ff19e5011c8d3d4a563ec`（638 / 637） | `76f6f0285d919082a86b35cf9945a64b9f1970c2` | 442 / 441 | 30069 | `c050ca4463ba41bee11df2aa85c5bcfd68e6864afd3a33f653e000db1dfe5b97` |
| `backend/tests/level_backfill_world.py`（夹具模块） | `ee1e0a880a663e07f172e1a1756299f2e0ddf7eb`（490 / 489） | `2a8db218de478575fb57d292c0b1173c2a4dde92` | 569 / 568 | 32226 | `6c3b022825f9076a98c79930df5c5996a4b35b88dd2063690f4a18c89ca93717` |
| `backend/tests/level_backfill_cases.py`（新增；辅助模块，文件名不以 `test_` 开头，不被收集） | — | `3b15ecfe837c64a4fa9a1f32a5e8c4ae11143f20` | 429 / 428 | 29609 | `340ec623f039db4b000c956ab519db4407576ff361eec6e07c4ef9d256a4b1af` |

- 三个文件都是 UTF-8 无 BOM、只有 LF、末尾有换行，最长行 129 字符（7.3 时两个文件最长 124 / 128）。`ruff check --no-cache`（ruff 0.11.12，仓库没有 ruff 配置，默认规则）通过；仓库根执行 `backend/scripts/check/check_file_size.py <三个文件>` 退出 0（`.py` 上限 800，按 splitlines 计）。
- V200 / R200 未改：`c9e1138f9aa3f2ecd20099de4e8a28f54cea73bb` / `5e21d438aebff0a12ccdd713e9c574cd0b5ff0ca`（sha256 `a7de9ae3…` / `c9dc53ee…`），开始前、灵敏度前后与收尾各核一次，`--path` 与 `--no-filters` 都相同。
- 相对 7.3 的改动（7.3 原文在开始前备份到仓库外，按 AST 逐条比对顶层语句与类成员，源码片段逐字比较）：测试文件与辅助模块合计，7.3 原有 64 条全部原样保留、新增 17 条（都属 7.4）；夹具模块 7.3 原有 107 条（含类成员）全部原样保留、新增 15 条（`BackfillWorld.rollback` 与「正向一次或两次，他途改动，再回滚」一节），另改模块说明（「三、执行」末条一句，新增「五、回滚」）。

文件拆分（7.3 后测试文件 637 行、只剩 163 行余量，放不下 7.4 与 7.5）：

- 做法：仓库外一次性脚本按行号整段搬移，不改任何一行代码：7.3 测试文件第 70~313 行（模型 `_PM_ROLE` … `_model`、生成器 `_ROLE_KEYS` … `_worlds`、`@example` 世界 `_E1` / `_E2`、固定样例构造函数 `_s` / `_a` / `_r` / `_u`、`_F1`~`_F9` 与 `_FIXED`，244 行）与第 533~583 行（需求 4.5 用例的 `_R45`、`_FIRST`、`Step`、`_R45_STEPS`、`_with_pairs`、`_r45_from_model`，51 行）原样写进新模块 `level_backfill_cases.py`；测试文件只删这两段（需求 4.5 小节标题后补 1 个空行），改为从新模块导入这些名字（下划线开头的照原名导入，不改名）。7.3 模块说明里「模型」「生成维度」两段随代码挪到新模块的模块说明，测试文件留一句指引。
- 搬移后、加 7.4 内容之前：AST 比对 7.3 原测试文件 64 条顶层语句（不含 docstring 与 import，带装饰器的连同装饰器）= 新测试文件 22 条 + 新模块 42 条，两边差集都为 0；ruff 通过；SQLite 轮 21 skipped（10:39:30，2.01 s），PG 轮 21 passed / 0 skipped / 0 failed / 0 error（10:39:50，34.82 s；Property 3 生成 5.56 s、Property 4 生成 8.41 s，固定样例 Property 3 每例 0.77~0.79 s、Property 4 每例 1.17~1.23 s，需求 4.5 用例 1.28 s），与 7.3 记录同量级。

回滚驱动方式（现读 `app/core/migration_runner.py` 的 `rollback_to`、`ensure_schema_version_table`、`get_current_version`、`get_applied_versions`、`scan_rollback_scripts`、`_run_backup`、`_execute_rollback_script` 与 CLI `_cli_main` 后确定）：

- 入口 `BackfillWorld.rollback`：用 `runner()` 建出的同一类执行器实例（引擎为世界引擎、迁移目录为只含 V / R 副本的临时目录）调 `rollback_to(target)`，`target = str(int(n) - 1)`（n 按文件名后缀现找，现为 200 ⇒ 199）；`confirm`、`operator` 取默认，与开发环境下 `python -m app.core.migration_runner --rollback 199`（不带 `--confirm` / `--operator`）是同一调用。
- 只替换 `_run_backup` 一项：实例属性换成记录 `(from_version, to_version)`、返回一个不创建的相对路径（只进执行器日志）的替身，不跑 `pg_dump`、不建 `backend/backups/`。R 副本由 `rollback_to` 自己经 `scan_rollback_scripts()` 查找、经 `_execute_rollback_script` 执行。
- 各分支在临时 schema 里的走向：① 测试进程 `settings.APP_ENV == "dev"`（仓库外探针现读；`app` 与 `migration_runner` 都解析到实施树），生产守卫不触发，不需要 `confirm`；② `ensure_schema_version_table()` 的建表命中临时 schema 里已有的表，补列 DO 块不限 schema、见 public 已有两列即跳过（临时表本就是 7 列，见「任务 7.2」坑一），表非空、不补登记 V001；③ 当前版本取 `MAX(version)`（字符串比较）= `"200"`，`int(目标) < int(当前)` 成立；④ 待回滚 = 已登记且大于目标的版本 = `["200"]`，临时目录有 R200 副本；⑤ `_run_backup("200", "199")` 进替身；⑥ R 副本切成 3 句，一个事务内逐句 `conn.execute(text(stmt))`；⑦ 另一个事务 `DELETE FROM schema_version WHERE version > '199'`（字符串比较，200 / 199 位数相同时成立）删掉本版本，`UPDATE schema_version SET operator …, rollback_note … WHERE version = '199'` 匹配 0 行、不报错——临时 schema 只登记了 n，所以 `operator` / `rollback_note` 在这里观测不到；⑧ 返回 `["200"]`。没有走不通的分支，不需要替代方式。`rollback_to` 本身不取 advisory lock（现读），持锁只在正向的 `run_pending`。
- 执行器日志（`-o log_cli=true --log-cli-level=INFO` 单跑 `test_requirement_4_9_rollback_branches[once]`，10:48:51）：正向「执行 V200…（2 条语句）」「执行成功 1 个: ['200']」之后依次为「备份完成: 未备份-级别回填测试替身」「执行回滚 R200__rollback_partner_manager_edit_level_backfill.sql (version=200) ...」「✅ 回滚 R200__… 执行成功（3 条语句）」「✅ 回滚完成: 200 → 199（回滚了 1 个版本: ['200']）」。
- `run_roundtrip(world, migrations, runs, steps)`：一个提交型临时 schema（隔离同「任务 7.2」）里正向执行一次；`runs == 2` 时先取快照、`forget_version(n)`、再 `run_pending()`（同 7.3 的 `run_forward_twice`，两次之间不写任何表）；随后按 `steps` 依次 `override_member_rows`（原生 UPDATE 只改两列）；最后 `rollback`，再取快照并按 schema 限定名查回填记录表。

新增测试（均 `pg_only`；每个样例一个新的提交型临时 schema）：

- `test_property_5_backfill_roundtrip`：`@settings(max_examples=5, deadline=None)`、`@given(case=_roundtrip_cases())`、`@example(case=RoundTripCase(_E1, 1, {}))`、`@example(case=RoundTripCase(_E2, 2, {}))`；函数头注释 `# Feature: partner-manager-edit-permission, Property 5: 回填往返`；`hypothesis.event` 只用于统计。
- `test_property_5_fixed_examples[f1-pm-five-aliases-once]` ~ `[f9-already-at-target-not-recorded-twice]`（18 个 = f1~f9 × 正向一次 / 两次）。
- `test_requirement_4_9_rollback_branches[once]`、`[twice]`（需求 4.9 各分支，Property 5 的显式样例）。

生成维度与模型：

- 世界：7.2 的 `_worlds()` 原样复用（需求 4.6 各维度，见「任务 7.2」）。`_roundtrip_cases` 另加两个维度：正向执行 1 或 2 次；回滚前一步他途改动——约三分之一的样例不改，其余从全部成员行（有回填记录的、没有记录的、已删除的）逐行约三分之二概率选中，改成的值在 6 × 3 种（项目角色，级别）中任取，另单列「迁移前值」与有记录行的「恰为目标值」「与目标值只差一列」两支以提高命中。第一次统计（10:51:33，逐行一半概率）5 个生成样例中 4 个没有他途改动，改为三分之二后重跑（见下文统计）。
- 模型 `_rollback_model`（按需求 4.9 原文独立推导，不读迁移 SQL、不读生产代码）：回填记录 = 第一次正向的被改动行及其（迁移前值，目标值），由 7.2 的模型 `_model` 给出；第二次正向不加、不改（需求 4.5、4.7）；回滚前的现值 = 正向后的值（被改动行取目标值，其余取迁移前值）依次套用他途改动；有记录且回滚前（项目角色，级别）== 记录的目标值 ⇒ 记录的迁移前值，否则保持回滚前的现值。

固定样例与期望：

- `test_property_5_fixed_examples`：f1~f9（第一次正向被需求 4.2 改动 19 行、4.3 改动 7 行，同「任务 7.2」）× 正向一次 / 两次、没有他途改动；先断言 `_model` == `Row.expect`、`_rollback_model(world, ())` == 世界里写死的迁移前（项目角色，级别），期望为全部成员行回到迁移前。
- `test_requirement_4_9_rollback_branches`：世界 `r4.9-rollback-branches`（项目 P 现行，10 名用户各一条成员行、一条人员库记录、一条委派；第一次正向改动 7 行：4.2 五行、4.3 两行，3 行不改不记）。他途改动分两步（第二步只改用户 2），期望写死在 `_R49_STEPS`，先与 `_rollback_model` 核对，再跑与 Property 5 相同的全部断言（参照「任务 7.1」附加世界二）：

| 用户 | 委派与第一次正向 | 回滚前的他途改动 | 回滚后（期望） | 需求 4.9 分支 |
|---|---|---|---|---|
| 0 | `manager`：auditor+readonly → manager+edit | 不改 | auditor+readonly | 有记录且仍为目标值：恢复 |
| 1 | `partner`：readonly+readonly → partner+edit | manager+review | manager+review | 有记录、被改成非目标值：保持 |
| 2 | `signing_partner`（带范围与有效期）：auditor+readonly → partner+edit | 先改 auditor+edit，再改回 partner+edit | auditor+readonly | 被改走后又改回目标值：恢复 |
| 3 | `manager`：qc+review → manager+edit | manager+review | manager+review | 项目角色同目标值、级别不同：保持 |
| 4 | `项目经理`（全局 partner）：auditor+readonly → manager+edit | partner+edit | partner+edit | 级别同目标值、项目角色不同：保持 |
| 5 | `manager`：manager+edit 已等于目标值，没有记录 | auditor+readonly | auditor+readonly | 没有记录、被他途改动：保持 |
| 6 | 只持 `qc`：auditor+readonly，没有记录 | manager+edit | manager+edit | 没有记录、被改成经理的目标形态：保持 |
| 7 | `eqcr`：auditor+edit → auditor+review（4.3） | 不改 | auditor+edit | 4.3 的行未被改动：恢复 |
| 8 | `独立复核合伙人`（全局 eqcr）：manager+readonly → manager+review（4.3） | manager+edit | manager+edit | 4.3 的行被改动：保持 |
| 9 | `manager`：已删除的成员行 auditor+readonly，没有记录 | partner+edit | partner+edit | 没有记录（已删除行）被他途改动：保持 |

断言（`_check_roundtrip`；生成样例、`@example`、固定样例与 4.9 用例相同）：

1. 正向：第一次正向满足 Property 3 的全部断言（直接调 7.2 的 `_check_executor`、`_check_member_rows`、`_check_other_tables`）；正向两次时两次之间没有写入，另满足 7.3 的 `_check_second_run` 与 `_check_idempotent`。
2. 他途改动本身：没有漏改的 id；改后每行（项目角色，级别）== 正向后的值依次套用各步；两列之外的列、回填记录、版本登记与失败表都不变。
3. 回滚经执行器：`rollback_to(n − 1)` 返回 `[n]`；`_run_backup` 替身恰被调用 1 次、参数为（n，n − 1）。
4. 回填记录表在临时 schema 里不存在（按 schema 限定名 `to_regclass` 查，快照里也是 None）；临时 `schema_version` 为空（不再含本版本，也没有其他登记）；失败表为空。
5. 成员行：id 集合同迁移前；每行（项目角色，级别）== 模型（失败信息逐行给出回滚前值、回滚后值与期望）；其余 11 列（含 `updated_at`）同迁移前。
6. 其余表：`users`、`projects`、`staff_members`、`project_assignments`、`disclosure_notes` 全表逐行全列同迁移前。
7. 没有他途改动时（需求 4.6 往返性质本体，不经模型）：六张表逐行全列 == 迁移前快照，失败信息逐行列出不同的列。

灵敏度核对（不是需求 12.5 的磁盘变异；做法同 7.2 / 7.3）：仓库外一次性 pytest 插件 `t74_mutant`（`-p t74_mutant`，经 `PYTHONPATH` 指向 `D:\pm_tmp`）挂 `pytest_fixture_setup` 包装钩子，在 `backfill_migrations` 建好临时目录之后按环境变量改写其中的 R 副本（V 副本不动）：每个锚点按预期次数出现才改（否则报错），改后记下命中次数与改前改后 sha256（改前都是 R200 原文的 `c9dc53ee…`，m00 外改后各不相同）；worktree 里的迁移文件不动。每项只跑 Property 5 固定样例与需求 4.9 用例（`-k "property_5_fixed_examples or requirement_4_9"`，共 20 个），按 junit 区分 failure / error。运行于 11:00:32–11:08:13 +08:00（每项 33~41 s），开始与结束各取一次 V200 / R200 与三个测试侧文件的 blob 与 sha256，都是上表的值。

| 变异 | 对 R 副本的改动（锚点命中次数） | 红的用例（failures / errors，共 20） | 首条失败信息 |
|---|---|---|---|
| m00 对照 | 不改（0） | 无（0 / 0），20 passed | — |
| m01 去掉恢复条件（必做①） | 删去 `AND pu.role = b.target_role AND pu.permission_level = b.target_permission_level`（1） | 4.9 用例 once、twice（2 / 0）；固定样例全过 | 「r4.9-rollback-branches：回滚后成员行取值不对：用户1（全局 auditor）在 P 的成员行0（readonly, readonly）：回滚前 ('manager', 'review')，回滚后 ('readonly', 'readonly')，按需求 4.9 应为 ('manager', 'review')」 |
| m02 只比较级别（必做②） | 上述条件 → `AND pu.permission_level = b.target_permission_level`（1） | 4.9 用例（2 / 0） | 「…用户4（全局 partner）在 P 的成员行0（auditor, readonly）：回滚前 ('partner', 'edit')，回滚后 ('auditor', 'readonly')，按需求 4.9 应为 ('partner', 'edit')」 |
| m03 去掉删表（必做③） | 删去 `DROP TABLE IF EXISTS project_user_level_backfill;`（1） | 全部 20 个（20 / 0） | 「f1-pm-five-aliases：回滚后回填记录表应不存在」（`(True, {…}) == (False, None)`） |
| m04 恢复时只写级别（必做④） | `SET role = b.prior_role, permission_level = b.prior_permission_level` → `SET permission_level = b.prior_permission_level`（1） | f1、f2、f3、f8、f9 各两次与 4.9 用例（12 / 0）；f4、f5（只有 4.3 行，项目角色本不变）、f6、f7（没有记录）通过 | 「f1-pm-five-aliases：…用户0（全局 auditor）在 P 的成员行0（auditor, readonly）：回滚前 ('partner', 'edit')，回滚后 ('partner', 'readonly')，按需求 4.9 应为 ('auditor', 'readonly')」 |
| m05（另加）只比较项目角色 | 恢复条件 → `AND pu.role = b.target_role`（1） | 4.9 用例（2 / 0） | 「…用户3（全局 auditor）在 P 的成员行0（qc, review）：回滚前 ('manager', 'review')，回滚后 ('qc', 'review')，按需求 4.9 应为 ('manager', 'review')」 |
| m06（另加）删表换成清空记录 | `DROP TABLE IF EXISTS …;` → `DELETE FROM project_user_level_backfill;`（1） | 全部 20 个（20 / 0） | 「f1-pm-five-aliases：回滚后回填记录表应不存在」（`(True, {}) == (False, None)`） |
| m07（另加）恢复不按 id 对应 | `WHERE pu.id = b.project_user_id` 与其后的 `AND` 删去，只剩按值匹配（1） | f1、f2、f8、f9 各两次与 4.9 用例（10 / 0）；f3（目标值相同的记录迁移前值也相同）、f4、f5（各记录目标值互不相同）都没有无记录的行恰在目标值上，与 f6、f7 一起通过 | 「f1-pm-five-aliases：…用户2（全局 qc）在 P 的成员行0（readonly, readonly）：回滚前 ('partner', 'edit')，回滚后 ('auditor', 'readonly')，按需求 4.9 应为 ('readonly', 'readonly')」（按值匹配到了别人的记录） |
| m08（另加）恢复条件比较迁移前值 | 恢复条件 → `AND pu.role = b.prior_role AND pu.permission_level = b.prior_permission_level`（1） | f1~f5、f8、f9 各两次与 4.9 用例（16 / 0）；f6、f7 通过 | 「f1-pm-five-aliases：…用户0…：回滚前 ('partner', 'edit')，回滚后 ('partner', 'edit')，按需求 4.9 应为 ('auditor', 'readonly')」 |
| m09（另加）恢复时只写项目角色 | `SET …` → `SET role = b.prior_role`（1） | f1~f5、f8 各两次与 4.9 用例（14 / 0）；f9（唯一一条记录只改了项目角色）、f6、f7 通过 | 「f1-pm-five-aliases：…用户0…：回滚前 ('partner', 'edit')，回滚后 ('auditor', 'edit')，按需求 4.9 应为 ('auditor', 'readonly')」 |
| m10（另加）恢复成目标值（空操作） | `SET …` → `SET role = b.target_role, permission_level = b.target_permission_level`（1） | 同 m08（16 / 0） | 同 m08 |
| m11（另加）不恢复需求 4.3 的行 | `WHERE pu.id = b.project_user_id` 后加 `AND b.rule = 'partner_manager'`（1） | f4、f5 各两次与 4.9 用例（6 / 0） | 「f4-eqcr-aliases-to-review：…用户0（全局 auditor）在 P 的成员行0（auditor, edit）：回滚前 ('auditor', 'review')，回滚后 ('auditor', 'review')，按需求 4.9 应为 ('auditor', 'edit')」 |
| m12（另加）恢复时顺带改 `updated_at` | `SET …` 末尾加 `, updated_at = now()`（1） | f1~f5、f8、f9 各两次与 4.9 用例（16 / 0）；f6、f7（没有要恢复的行）通过 | 「f1-pm-five-aliases：回滚改动了成员行的其余列 ['用户0（全局 auditor）在 P 的成员行0（auditor, readonly）', …]」 |

- 13 份 junit 的 errors 都是 0；红的用例都是 `AssertionError`，最内层的测试帧都在 `_check_roundtrip`，不是收集、夹具或 SQL 错误（变异后的 R 都合法，`rollback_to` 照常返回 `['200']`）。
- 必做的 m01、m02 只有 4.9 用例打红：没有他途改动时有记录的行都仍在目标值上，恢复条件比不比、比哪一列，结果都相同，f1~f9 按定义观测不到；这是另设 4.9 显式样例的原因（m05 同理）。m03、m06 由全部 20 个用例打红；m04、m09、m11 各由改动了对应列或对应规则的固定样例打红。

运行（仓库外一次性启动器 `D:\pm_tmp\t74_run.py`：cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -B -m pytest tests/test_level_backfill_migration_pg.py -q -p no:cacheprovider --tb=short -rfEs --junitxml=<仓库外> --basetemp=<仓库外>`；子进程 env 设 `PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外；PG 轮的 `DATABASE_URL` 由启动器经子进程从实施树 `app.core.config.settings.DATABASE_URL` 取出（`postgresql+asyncpg`，不打印），只放进 pytest 子进程 env；SQLite 轮去掉 `DATABASE_URL`）：

| 轮次 | 附加参数 | 结果 | 时刻（+08:00）/ 耗时 |
|---|---|---|---|
| 拆分后 SQLite 轮 | — | 21 skipped（原因 `requires PostgreSQL`），0 failed / 0 error | 10:39:30 / 2.01 s |
| 拆分后 PG 轮 | — | 21 passed、0 skipped | 10:39:50 / 34.82 s |
| SQLite 轮（最终版文件） | — | 42 skipped（7.2 / 7.3 的 21 个 + 7.4 的 21 个：Property 5 1、固定样例 18、4.9 用例 2），0 failed / 0 error | 10:54:25 / 1.90 s |
| PG 轮（最终版文件） | — | 42 passed、0 failed、0 error、0 skipped（生成：Property 3 5.62 s、Property 4 8.76 s、Property 5 10.37 s；固定样例每例：Property 3 0.78~0.87 s、Property 4 1.23~1.31 s、Property 5 正向一次 1.18~1.24 s / 两次 1.59~1.82 s；需求 4.5 用例 1.26 s；4.9 用例 once 1.25 s / twice 1.74 s） | 10:54:31 / 75.28 s |
| PG 轮 + 统计（最终版文件） | `--hypothesis-show-statistics` | 42 passed、0 skipped | 10:56:08 / 73.26 s |
| 灵敏度 m00~m12 | `-p t74_mutant -k "property_5_fixed_examples or requirement_4_9"`，env 另设 `T74_MUTANT`、`T74_MUTANT_LOG`、`PYTHONPATH` | 见上表 | 11:00:32–11:08:13 |

- 三个文件最后修改于 10:44:45（夹具）、10:47:30（测试）、10:53:49（辅助模块），早于「最终版文件」各轮与灵敏度。较早几轮（10:47:48 只跑 7.4 的 21 个用例 21 passed；10:48:51 单跑 4.9 用例看执行器日志；10:49:41 SQLite 42 skipped；10:49:52 PG 42 passed；10:51:33 统计轮 42 passed）在生成器调整之前，调整只改了 `_roundtrip_cases` 的逐行选中概率（一半 → 三分之二）与其文档字符串。
- 落盘的输出、junit 与汇总 JSON 由启动器替换连接串片段；收尾前把 `D:\pm_tmp` 下 80 个 t74 输出 / junit / JSON 文件逐个扫描：完整连接串、去掉 `+asyncpg` 的连接串、`用户:口令@主机:端口`、`用户:口令`、口令、`postgresql://` 与 `postgresql+asyncpg://` 前缀都是 0 处，占位也是 0 处（没有需要替换的内容）。

hypothesis 统计（PG 轮 + 统计，10:56:08；`@example` 在显式阶段执行，不计入）：

- `test_property_5_backfill_roundtrip`：生成阶段 7.46 s，每例约 1204~1746 ms（其中生成数据 0~3 ms），5 passing / 0 failing / 0 invalid，因 `max_examples=5` 停止；事件：「正向执行 2 次」60%、「1 次」40%；「他途改动 0 行，其中有回填记录 0 行」40%、「1 行，其中有回填记录 1 行」40%、「6 行，其中有回填记录 1 行」20%；「回填记录 1 条，回滚时仍为目标值（恢复）1 条」40%，「回填记录 0 条，恢复 0 条」「回填记录 1 条，恢复 0 条」「回填记录 2 条，恢复 1 条」各 20%。
- 同一轮的 Property 3：生成 4.32 s，5 passing / 0 failing / 0 invalid，事件「被改动行：需求 4.2 1 条，需求 4.3 0 条」100%，成员行 2 条 40%、1 / 4 / 8 条各 20%；Property 4：生成 5.96 s，5 passing / 0 failing / 0 invalid，「第一次被改动行 1 条（需求 4.2 1 条，需求 4.3 0 条）」80%、「（需求 4.2 0 条，需求 4.3 1 条）」20%。
- 生成器调整前那次统计（10:51:33）：Property 5 的 5 个生成样例中 4 个「他途改动 0 行」，只有 1 个改了 3 行（其中有记录 2 行）。

副作用核对：

- 本地开发库（postgres MCP 只读）：运行前（02:33:24 UTC）与全部运行之后（03:10:00 UTC）结果相同：`authz_world%` schema 0 个，非系统 schema 0 个，任一 schema 中 `project_user_level_backfill` 0 个，`projectuserrole` 类型 1 个（public）；public `schema_version` 199 行、最高 199（按数值与按字符串相同）、没有 200，运行后另查 `operator` 或 `rollback_note` 非空的行为 0（`rollback_to` 没有写到 public）；`schema_migration_failures` 0 行；`project_users` 88（最大 `updated_at` 2026-10-07 08:09:10）、`project_assignments` 86（2026-10-07 04:51:58）、`staff_members` 215（2026-10-15 06:19:08）、`users` 94（2026-10-07 04:51:58）、`projects` 85（2026-10-20 11:14:02）、`logs` 94544（最大 `created_at` 2026-10-20 23:50:03）、`evidence_outbox` 748（`created_at` / `updated_at` 2026-10-20 23:38:39），与「任务 7.3」记录的值逐项相同。
- 两棵树：开始前（10:33:49）与全部运行之后（11:10:13）各取一次：HEAD 都是 B `a02a21419a7ffef349384a766798b7ac291fca05`；基线树 `git status --porcelain=v1 -uall --ignored` 1730 行、逐字相同；实施树 74574 → 74575 行，差异只有 `?? backend/tests/level_backfill_cases.py`（` M` 23、`??` 23 → 24、`!!` 74528）。两棵树都没有 `backend/backups/`；主工作树既有的 `backend/backups/`（24 项，最新一项修改于 2026-10-18）清单的名称、大小与修改时间前后相同。按创建 / 修改时间扫描两棵树（排除 `.git`、`node_modules`），10:33:00 之后变动的只有实施树的 `backend/tests` 目录与上表三个文件，没有 `.pyc`、`.hypothesis`、`backend/storage` 或 `backend/backups` 产物；基线树 0 项。（本节写入后实施树另多一项本文件的修改。）

与任务原文 / design 的偏差：

1. 隔离沿用「任务 7.2」的提交型临时 schema（同其偏差 1）；回滚走执行器 `rollback_to`，只替换 `_run_backup`。
2. design Property 5 原文写「回滚前被他途改成非目标值」的行；按本次派发要求，他途改成的值任取（可恰为目标值、恰为迁移前值或只差一列），模型按需求 4.9 原文以回滚前的现值判定，取值空间包含原文的情形。
3. 断言比 design Property 5 原文多：正向部分复用 Property 3 / 4 的全部断言，他途改动本身的核对，`rollback_to` 的返回值与 `_run_backup` 替身的次数和参数，临时 `schema_version` 为空、失败表为空，成员行其余 11 列与其余五张表同迁移前。
4. 文件拆分：7.2 / 7.3 的模型、生成器与样例移到新辅助模块（理由与核对见上）；7.2 / 7.3 的测试函数与断言仍在原测试文件，逐行未改。

给 7.5 的说明：

- 回滚入口 `BackfillWorld.rollback(migrations)` 可直接复用（返回目标版本、`rollback_to` 返回值与 `_run_backup` 替身记下的调用）；`run_roundtrip` 的正向两次与他途改动也可复用。
- 需求 4.1「正向从未执行时回滚成功且不改动成员行」：执行器的运维入口走不到 R 脚本——临时 `schema_version` 为空时 `rollback_to` 在 `get_current_version()` 之后抛 `RuntimeError("schema_version 表为空，无法回滚")`；只登记了其他版本而没有 n 时，n 不在待回滚列表（目标取 n − 1 还会因「目标须小于当前版本」而报错）。7.5 须另定驱动方式（例如按执行器同口径直接调 `_execute_rollback_script`，或先登记本版本再调 `rollback_to`），并在验收记录写明理由。
- 需求 4.10「回滚脚本出错时 n 保持已应用」（现读）：`_execute_rollback_script` 抛出后，`rollback_to` 在删 `schema_version` 之前就退出，R 整个脚本在一个事务里回滚；可用本节同款插件改写临时 R 副本使其出错，断言临时 `schema_version` 仍含 n、成员行与回填记录不变。
- 行数余量：测试文件现 441 行（splitlines，上限 800），辅助模块 428 行，夹具模块 568 行。

清理：本任务的一次性文件——`D:\pm_tmp\t74_*` 146 项（启动器、7.3 原文两个备份、拆分 / AST 比对 / 行号 / 行宽 / 环境 / 耗时 / 状态 / 密文扫描等探针、变异插件与灵敏度驱动、本节与汇总行草稿与插入脚本，各轮的 junit / 输出 / 汇总 JSON 与变异日志，两次状态快照，以及 45 个 `--basetemp` 与 hypothesis 目录；目录内共 2638 个文件）——于 2026-10-21 11:18:06 +08:00 删除，删除后 `D:\pm_tmp` 为空，没有其他前缀的文件，也没有 `__pycache__`。本行在删除之后直接编辑写入。

### 任务 7.5：迁移执行语义与角色映射对账（真 PG）（2026-10-21）

本任务改三个测试侧文件（7.2~7.4 新增、均未跟踪），并按「检查点 5」用户裁定 3 在漂移检测器与其测试里各插入一段；没有改迁移文件、其余生产代码与其余既有测试。

改动文件（实施 worktree）：

| 文件 | 改前 blob（行数 `split("\n")` / splitlines） | 现 blob | 现行数（`split("\n")` / splitlines） | 字节 | sha256 |
|---|---|---|---|---|---|
| `backend/tests/test_level_backfill_migration_pg.py`（未跟踪） | `76f6f0285d919082a86b35cf9945a64b9f1970c2`（442 / 441） | `f000ccf1b4d666ad10f0e7d9852a29da822035be` | 624 / 623 | 45049 | `c463b033bece8e77b4f56697b90da6d14675f20ee0bd0fdd64452129209a692d` |
| `backend/tests/level_backfill_world.py`（夹具模块，未跟踪） | `2a8db218de478575fb57d292c0b1173c2a4dde92`（569 / 568） | `eec2c7f342e667361766cc8325f458a5f376ad4b` | 757 / 756 | 42053 | `c4ea15b4c02897bea3659ddf7b5b61087bcd8b4dc69fc7d7d7fff365d3ba3251` |
| `backend/tests/level_backfill_cases.py`（辅助模块，未跟踪） | `3b15ecfe837c64a4fa9a1f32a5e8c4ae11143f20`（429 / 428） | `94ba7b8196ad55a53757c51f1581a1095120af81` | 478 / 477 | 33695 | `4a5005f638bb33be3be45e7320ff7d79f1b144d51d9e02f34e9065e6a9daa279` |
| `backend/app/core/schema_drift_detector.py`（已跟踪，检出为 CRLF） | HEAD `2747c0fcf87342261ef8dea9dae658d508bd565b`（725 / 724） | `--path` `254fc4040c5661f1bf6ae3e0cf78c70e14e34463`（`--no-filters` `a8f6aa1ec6bd3c3f4f1932976e063cf16f582196`） | 733 / 732 | 37389 | `a0c164d9bf5c2ee72b64fcaf463f12e5df8e106b3cd27350e8534f334b545726` |
| `backend/tests/test_schema_drift_detector.py`（已跟踪，检出为 CRLF） | HEAD `0b17b2ac2c16d46c04a266e357828f128cc9a23a`（449 / 448） | `--path` `c7a01511fa384f7324708167dd457cb12366d76d`（`--no-filters` `c4f75f4ea064a802ffeb703758287094df5a405c`） | 498 / 497 | 24719 | `c502cc4d37bf58056e9f6f88ebb8f94260edf0e0eeb5859ad4d2be451c832a44` |

- 前三个 UTF-8 无 BOM、只有 LF、末尾有换行，`--path` 与 `--no-filters` 同 blob，最长行 129 字符。后两个按 HEAD 的检出形态保持 CRLF（`core.autocrlf=true`），由仓库外一次性脚本按字节插入、断言「去掉插入段 == 原文」；`git diff --stat` 为 +8 / +49、0 删除。
- `ruff check --no-cache`（ruff 0.11.12，默认规则）五个文件通过；仓库根执行 `backend/scripts/check/check_file_size.py <五个文件>` 退出 0（`.py` 上限 800，按 splitlines 计，最大的夹具模块 756）。
- V200 / R200 未改：`c9e1138f9aa3f2ecd20099de4e8a28f54cea73bb` / `5e21d438aebff0a12ccdd713e9c574cd0b5ff0ca`（sha256 `a7de9ae3…` / `c9dc53ee…`），开始前（11:31）、灵敏度之后（11:54）与收尾（11:58）各取一次，`--path` 与 `--no-filters` 都相同。
- 相对 7.4 只增不改：仓库外探针把本任务的编辑逐条撤回（测试文件：模块说明两处、导入块、末尾追加段；夹具模块：模块说明「六」、末尾追加段；辅助模块：模块说明一段、`BACKFILL_TABLE` 导入、末尾追加段），三个文件撤回后的 blob 分别等于 7.4 记录的 `76f6f028…`、`2a8db218…`、`3b15ecfe…`，即 7.2~7.4 的模型、样例、流程、测试函数与断言函数逐字未改。夹具模块新增 `RollbackAttempt`、`execute_sql`、`rollback_attempt`、`execute_rollback_script` 与四个流程（`run_rollback_twice`、`run_rollback_only`、`run_forward_failure`、`run_rollback_failure`），`BackfillWorld` 与既有函数没动；辅助模块新增两个世界、冲突语句与预期报错片段、对账别名清单与 `_reconcile_world`。

新增测试（均 `pg_only`，在 `backend/tests/test_level_backfill_migration_pg.py`；每个用例一个提交型临时 schema，隔离同「任务 7.2」）：

| 测试标识 | 需求 | 世界 | 驱动 |
|---|---|---|---|
| `test_requirement_4_1_rollback_twice` | 4.1 | `r4.1-changed-and-unchanged-rows` | 正向 `run_pending()` → `rollback_to(199)` → 再调 `rollback_to`（断言被拒绝）→ `_execute_rollback_script(R 副本)` |
| `test_requirement_4_1_rollback_without_backfill_records` | 4.1 | `r4.1-nothing-to-backfill` | 7.4 的 `run_roundtrip(…, 1)`：正向一次 → `rollback_to(199)`；断言复用 7.4 的 `_check_roundtrip` |
| `test_requirement_4_1_rollback_when_forward_never_ran` | 4.1 | `r4.1-changed-and-unchanged-rows` | 不正向；`rollback_to`（断言被拒绝）→ `_execute_rollback_script(R 副本)` |
| `test_requirement_4_10_forward_failure_is_not_registered` | 4.10 | 同上，执行前预建不兼容的同名表 | `run_pending()` 两次（第二次即下次启动的重试） |
| `test_requirement_4_10_rollback_failure_keeps_version_applied` | 4.10 | 同上，正向后给回填记录表建依赖视图 | 正向 `run_pending()` → 建视图 → `rollback_to(199)` |
| `test_requirement_12_7_backfill_matches_role_map[manager]`、`[partner]`、`[signing_partner]`、`[合伙人]`、`[项目经理]`、`[eqcr]`、`[独立复核合伙人]` | 12.7 | 每个别名一个 `r12.7-<别名>` | `run_pending()` 一次 |

- 节点标识里的中文按 pytest 默认转义，例如 `test_requirement_12_7_backfill_matches_role_map[\u9879\u76ee\u7ecf\u7406]`（`项目经理`）、`[\u5408\u4f19\u4eba]`（`合伙人`）、`[\u72ec\u7acb\u590d\u6838\u5408\u4f19\u4eba]`（`独立复核合伙人`）；本节写原文。
- 需求 4.1「两个脚本重复执行都不报错」的正向一半不另写：任务 7.3 的 `test_property_4_backfill_is_idempotent`、`test_property_4_fixed_examples[f1-pm-five-aliases]` ~ `[f9-already-at-target-not-recorded]` 与 `test_requirement_4_5_existing_records_not_overwritten` 都在同一个世界里经 `run_pending()` 执行第二次，断言 `executed == [n]`、`failed == []`、失败表为空（`_check_second_run`），本次两轮 PG 全文件运行仍通过。
- 世界 `r4.1-changed-and-unchanged-rows`（项目 P 现行、D 已软删，6 名用户各一条成员行）：`manager` + auditor+readonly（带范围）→ manager+edit、D 上 `合伙人` + readonly+readonly → partner+edit、`独立复核合伙人` + manager+edit → manager+review（需求 4.3）；另 3 行不改不记：`signing_partner` + partner+edit（已在目标值）、只持 `qc`、已删除的成员行持 `manager`。不含 `项目经理`，所以 m01 变异只影响 12.7 那一例。
- 世界 `r4.1-nothing-to-backfill`（7 行，正向一行都不改）：`manager` + manager+edit、D 上 `signing_partner` + partner+edit、`eqcr` + auditor+review、经两份人员库记录同持 `partner` 与 `独立复核合伙人` + partner+review（EQCR 优先、已是 review）——前 4 行持别名委派且已在目标值上；另有 `Manager` 变体、人员库记录已删、已删除的成员行各 1。
- 每个用例先核对前提：模型（7.2 的 `_model`）给出的改动行「有 / 无」符合该用例的设定，回滚两次、无回填记录、回滚失败三例另核对模型与写死在 `Row.expect` 的期望一致。

驱动方式与理由：

- 正向一律经 `MigrationRunner(engine=<世界引擎>, migrations_dir=<临时目录>).run_pending()`（同 7.2）；第一次回滚与回滚失败用例经 `rollback_to(n − 1)`（同 7.4，只把 `_run_backup` 换成记录调用的替身）。
- 「正向从未执行」与「已回滚过一次」两种状态下，临时 `schema_version` 为空，`rollback_to` 在 `get_current_version()` 之后即抛 `RuntimeError("schema_version 表为空，无法回滚")`，走不到 R 脚本（「任务 7.4」给 7.5 的说明）。两个用例都实测并断言这一点：异常类型与原文、无返回值、`_run_backup` 替身 0 次，前后六张表、回填记录、版本登记与失败表都不变。
- 因此这两种状态下按执行器同口径直接执行 R 副本：取执行器 `scan_rollback_scripts()` 在临时目录里扫到的本版本 R 脚本（断言恰为 R 副本），交给 `_execute_rollback_script`——`rollback_to` 执行每个 R 脚本所用的同一函数（执行器分句，一个 `engine.begin()` 事务内逐句 `text()`）。
- 没有改用「先在临时 `schema_version` 登记本版本再 `rollback_to`」：那样临时库处于「版本 n 已应用、却没有回填记录表」，不是需求 4.1 所说的「正向迁移从未执行」；`rollback_to` 随后还会删登记、写 `operator` / `rollback_note`，被观测的就不只是 R 脚本本身。
- 流程函数把 `rollback_to` 与 `_execute_rollback_script` 抛出的异常收下作为观测值，红都落在测试的断言上（灵敏度核对中 errors 均为 0）。

冲突一律由测试数据制造（夹具 `execute_sql` 在临时 schema 里执行），不改写迁移副本：

- 正向失败：执行前 `CREATE TABLE project_user_level_backfill (project_user_id UUID PRIMARY KEY, note TEXT NOT NULL)` 并插入一行（固定 id、`note` 为「预建的不兼容同名表」）。V 副本的建表语句因 `IF NOT EXISTS` 跳过，第二条语句（数据修改型 CTE）的 INSERT 列名解析失败。实测返回 `FailureRecord(version='200', filename='V200__partner_manager_edit_level_backfill.sql', error_type='ProgrammingError')`，信息含 `<class 'asyncpg.exceptions.UndefinedColumnError'>: column "prior_role" of relation "project_user_level_backfill" does not exist`。
- 正向失败的断言（第一次与重试各一遍）：`executed == []`，`failed` 恰为本版本、`error_type` 为 `ProgrammingError`、信息含 `UndefinedColumnError` 与上面那句原文；临时 `schema_version` 为空（版本不登记）；失败表恰一行，version、filename、error_type、error_message 与返回值逐字相同，`attempt_count` 第一次为 1、重试后为 2；预建表的内容与执行前逐值相同（没有被写入）；六张表逐行全列与执行前相同（世界里有 3 行是正向会改的）。
- 回滚失败：正向成功后 `CREATE VIEW project_user_level_backfill_dependent AS SELECT project_user_id FROM project_user_level_backfill`。R 副本三句依次为：建表（已存在，跳过）、UPDATE（在事务内恢复成员行）、`DROP TABLE IF EXISTS …`（不带 CASCADE，因依赖视图报错）。
- 选依赖视图、没用任务示例的「改动回填表结构」：改结构会让第二句 UPDATE 就报错，报错前没有任何改动，观测不到「R 整个脚本在一个事务里回滚」；依赖视图让报错落在已执行过 UPDATE 之后（灵敏度 m06 证明这一点被观测到了）。
- 回滚失败实测：异常类型 `sqlalchemy.exc.DBAPIError`（asyncpg 的 `DependentObjectsStillExistError` 不在 SQLAlchemy asyncpg 方言的细分映射里，落到基类），信息含 `cannot drop table project_user_level_backfill because other objects depend on it`，`[SQL: …]` 为 DROP 语句（前缀是上一句行尾的「4.9」注释，同「任务 7.1」分句结论）。
- 回滚失败的断言：正向满足 Property 3 的全部断言；建视图不改数据；`rollback_to` 无返回值、抛出的异常类型恰为 `DBAPIError` 且信息含 `DependentObjectsStillExistError` 与上面那句原文；`_run_backup` 替身恰被调用 1 次、参数 ('200', '199')（执行 R 之前）；六张表（成员行仍为正向后的值）、回填记录、临时 `schema_version`（仍含 200）与失败表都与回滚前相同；回填记录表与依赖视图都还在。

对账口径（需求 12.7）：

- 别名取 `tests/role_map_expected.py`：合伙人 / 经理 = `EXPECTED_ROLE_MAP` 中取值为 (partner, edit) 或 (manager, edit) 的 5 个键，EQCR = `EXPECTED_EQCR_ALIASES` 的 2 个；不从生产代码推导别名集合。
- 每个别名一个世界：一名用户（全局 auditor）、一条人员库记录、该别名一条现行委派、一条 (auditor, readonly) 成员行；经执行器正向执行一次，另跑 `_check_executor`。
- 断言先级别、后项目角色，失败信息可区分：所得级别 == 生产 `ROLE_MAP[别名]` 的级别（`.value`，在测试函数体内读取）；合伙人 / 经理别名所得项目角色 == `ROLE_MAP[别名]` 的项目角色；EQCR 别名所得项目角色 == auditor（需求 4.3 原文，不读 `ROLE_MAP`）。docstring 写明这是 SQL 别名字面量与 `ROLE_MAP` 之间的一致性约束（design §5.2、§8.5 变异③）。

漂移检测器（用户裁定 3）：

- `backend/app/core/schema_drift_detector.py`：`KNOWN_ALLOWLIST` 末尾（V155 那条之后）插入 `"project_user_level_backfill"` 与 7 行注释（+8 行）。登记理由：迁移建、ORM 不声明的回填记录表，级别回填迁移在改写成员行的同一条语句里写入它，只有配对回滚脚本读它、读完即删表，业务代码零读写；正向已执行、回滚脚本未执行期间一直留在库里，不登记则每次启动报一条 INFO 级 `db_extra`；表名单一真源是迁移脚本本身，与「无 ORM 模型」双向锁死。注释没有写建表语句原文（`test_cleanup_h4_lazy_table_scan.py` 按正则扫描 `app/` 下的 `CREATE TABLE IF NOT EXISTS`；写入本节后在实施树单独跑该文件，9 passed，SQLite 环境，带 `-B`、`-p no:cacheprovider`，没有产生文件）。
- `backend/tests/test_schema_drift_detector.py`：`TestKnownAllowlist` 新增 `test_level_backfill_record_table_allowlisted_and_unmapped`（+49 行），照同类的 `test_v154_override_version_table_allowlisted_and_unmapped` / `test_v155_oo_content_revision_table_allowlisted_and_unmapped` 写法：在 allowlist，且 `SchemaDriftDetector._import_all_models()` 之后不在 ORM metadata。那两条从服务层常量取表名，这张表没有服务层常量，改为从迁移脚本现取：按文件名后缀找 V / R 各恰一个，用执行器的 `_split_sql_statements` 切句、去掉行注释后取 V 建的表（须恰一张）与 R 删的表（须是同一张）。
- 双向断言的反证（仓库外一次性插件 `t75_driftmut` 在 `pytest_configure` 里进程内改写，不改文件；只跑该用例，SQLite 环境，11:50:21–11:50:39）：对照通过；allowlist 去掉该表 ⇒ 红在「project_user_level_backfill 不在 allowlist」；往 ORM metadata 注册同名表 ⇒ 红在「project_user_level_backfill 已被 ORM 映射，但仍留在 KNOWN_ALLOWLIST 里」；执行器分句结果里把表名换成 `project_user_level_backfill_v2`（模拟迁移改了表名而 allowlist 没跟着改）⇒ 红在「project_user_level_backfill_v2 不在 allowlist」。三项都是 failure、0 error。
- 离线现算（不连库；仓库外探针在各树 `backend` 下调用检测器的 `_collect_orm_tables`、`_diff_tables`、`_diff_columns`、`_apply_suppressions`、`count_critical`，库表集合 = ORM 全集 335 张再加这张表的 7 列）：两树原始比对都恰有 1 条表级 `db_extra`、0 条列级；过滤后实施树 0 条（allowlist 33 项，含它）、基线树 1 条（32 项）；`count_critical` 两树过滤前后都是 0，与「任务 7.1」的结论相同，health 判定不变。
- `backend/scripts/gen/gen_schema_sync_migration.py` 另有一份 5 项的 `KNOWN_ALLOWLIST` 副本，只用于遍历 ORM 表、补建 DB 缺失的表与列，DB 独有的表不进入它的比较，未改。
- 既有测试两树对照：AST 导入或 docstring 以外的模块路径字符串引用 `app.core.schema_drift_detector` 的测试文件，两树都是 5 个，命中都来自导入：`test_enum_drift_columns.py`、`test_evidence_governance_wave1_capstone_v2_5.py`、`test_health_endpoint_degraded.py`、`test_migration_integrity_pg.py`、`test_schema_drift_detector.py`。
- 运行（两树先后各一次，11:47:48 / 11:47:57）：env 去掉 `DATABASE_URL`，另加仓库外一次性插件 `t75_block_pg` 拦下 `asyncpg.connect`、`asyncpg.connection.connect`、`psycopg2.connect`——这批里有不看 `DATABASE_URL`、直连本地开发库的用例，`test_migration_integrity_pg.py` 还会在回滚事务里写 public 表（同「任务 7.1」的处置）。
- 结果：实施树 89 例（64 passed、24 failed、1 xfailed）、基线树 88 例（63 / 24 / 1）。只在实施树的 1 例是新增用例（passed）；其余 88 例逐例状态相同，失败首行信息按树路径归一后相同；24 个红两树相同、全由拦截引起（拦截日志两树都是 9 条、用例相同：capstone 8 例的调用阶段与 `test_migration_integrity_pg.py` 的模块级 harness，该文件 16 例随之报 `KeyError`）；xfail 是既有的 strict 用例 `test_main_startup_check_uses_the_single_source`。⇒ 新增失败 0。

灵敏度核对（不是需求 12.5 的磁盘变异；仓库外一次性插件，worktree 文件不动）：

- 迁移副本变异：插件 `t75_mutant` 挂 `pytest_fixture_setup` 包装钩子，在 `backfill_migrations` 建好临时目录之后按环境变量改写其中的 V / R 副本；锚点须按预期次数出现才改，改后记下命中次数与改前改后 sha256（改前都是原文的 `a7de9ae3…` / `c9dc53ee…`，m00 外改后各不相同）。
- `ROLE_MAP` 变异：插件 `t75_rolemap` 在 `pytest_configure`（`tests/conftest.py` 加载之后）改写生产 `ROLE_MAP` 字典的取值，日志记下改前改后的取值与模块文件（实施树的 `app/services/assignment_service.py`）。
- 每项都跑 7.5 的 12 个用例（`-k "requirement_4_1_ or requirement_4_10 or requirement_12_7"`），PG 环境，按 junit 区分 failure / error；运行于 11:50:54–11:54:14 +08:00（每项 15~17 s）。

| 变异 | 改动（锚点命中次数） | 红的用例（failures / errors，共 12） | 首条失败信息 |
|---|---|---|---|
| m00 副本对照 | 不改（0） | 无（0 / 0） | — |
| m01 V 去掉 `项目经理` | `'manager', '项目经理')` → `'manager')`（1） | 12.7 `[项目经理]`（1 / 0） | 「r12.7-项目经理：迁移所得级别 readonly 与 ROLE_MAP['项目经理'] 的级别 edit 不一致」 |
| m02 V 建表去掉 `IF NOT EXISTS` | `CREATE TABLE IF NOT EXISTS project_user_level_backfill (` → 不带 `IF NOT EXISTS`（1） | 4.10 正向失败（1 / 0） | 「…（预建不兼容的同名表）：第一次失败信息不是预期的列名解析错误：(…ProgrammingError) <class 'asyncpg.exceptions.DuplicateTableError'>: relation "project_user_level_backfill" already exists」（报错点前移到第一句，类型仍是 ProgrammingError，红在信息断言） |
| m03 V 吞错 | 第二句包进 `DO $t75$ BEGIN … EXCEPTION WHEN OTHERS THEN NULL; END $t75$;`（两处锚点各 1） | 4.10 正向失败（1 / 0） | 「…第一次正向执行应恰失败于版本 200，实际 executed=['200']，failed=[]」 |
| m04 R 去掉建表语句 | 删除第一句（1） | 4.1 回滚两次、4.1 正向从未执行（2 / 0） | 「r4.1-changed-and-unchanged-rows：第二次执行 R 副本报错：ProgrammingError(…UndefinedTableError'>: relation "project_user_level_backfill" does not exist')」；另一例同型（「执行 R 副本报错」） |
| m05 R 删表改成清空 | `DROP TABLE IF EXISTS project_user_level_backfill;` → `DELETE FROM project_user_level_backfill;`（1） | 4.1 三例与 4.10 回滚失败（4 / 0） | 「…第一次回滚后回填记录表应不存在、版本登记与失败表应为空」；「r4.1-nothing-to-backfill：回滚后回填记录表应不存在」；「…（正向从未执行）：执行 R 副本后回填记录表应不存在」；「…rollback_to 应在执行 R 副本时失败…实际 RollbackAttempt(target='199', rolled_back=['200'], error=None, …)」 |
| m06 R 在 UPDATE 之后插入 `COMMIT;` | （1） | 4.10 回滚失败（1 / 0） | 「…（回填记录表有依赖视图）：失败的回滚改动了 ['project_users']」（DROP 照旧报错、异常断言通过，但 UPDATE 已提交） |
| m07 R 删表加 `CASCADE` | （1） | 4.10 回滚失败（1 / 0） | 「…rollback_to 应在执行 R 副本时失败（_run_backup 替身先被调用 1 次），实际 RollbackAttempt(target='199', rolled_back=['200'], error=None, backups=(('200', '199'),))」 |
| m08 V 不过滤已在目标值的行 | 去掉 `changed` 的 `WHERE (prior_role, prior_level) IS DISTINCT FROM (target_role, target_level)`（1） | 4.1 无回填记录、4.1 回滚两次、4.10 回滚失败（3 / 0） | 「r4.1-nothing-to-backfill：正向执行后回填记录表应存在且为空，实际 {…}」；另两例红在 Property 3 的 `_check_member_rows`「被改动行与回填记录不一致：…有记录而未改动 ['用户3（全局 auditor）在 P 的成员行0（partner, edit）']」 |
| p00 `ROLE_MAP` 对照 | 不改 | 无（0 / 0） | — |
| p01 `manager` / `项目经理` 改回 (manager, review)（design §8.5 变异③） | 2 个键 | 12.7 `[manager]`、`[项目经理]`（2 / 0）；其余 5 个别名与 4.1 / 4.10 五例通过 | 「r12.7-manager：迁移所得级别 edit 与 ROLE_MAP['manager'] 的级别 review 不一致」；`[项目经理]` 同型 |
| p02 `signing_partner` 的项目角色改成 manager | 1 个键 | 12.7 `[signing_partner]`（1 / 0） | 「r12.7-signing_partner：迁移所得项目角色 partner 与 ROLE_MAP['signing_partner'] 的项目角色 manager 不一致」（级别断言通过，红在项目角色断言） |

- 12 份 junit 的 errors 都是 0；红都是 `AssertionError`，落在测试函数体的断言或其调用的断言函数上。变异后的 SQL 由执行器照常执行，m02、m03、m04 引起的 SQL 错误（或被吞掉的错误）由执行器或流程函数收下，红出自断言。
- 新增 5 个用例各至少被一项变异打红：回滚两次（m04、m05、m08）、无回填记录（m05、m08）、正向从未执行（m04、m05）、正向失败（m02、m03）、回滚失败（m05、m06、m07、m08）；12.7 的 7 例里，m01、p01、p02 都只红被改的那个别名。

运行（仓库外一次性启动器：cwd `D:\wt_pm_impl\backend`，`D:\GT_plan\.venv\Scripts\python.exe -B -m pytest tests/test_level_backfill_migration_pg.py -q -p no:cacheprovider --tb=short -rfEs --junitxml=<仓库外> --basetemp=<仓库外>`；子进程 env 设 `PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`、`HYPOTHESIS_STORAGE_DIRECTORY` 指向仓库外；PG 轮的 `DATABASE_URL` 由启动器经子进程从实施树 `app.core.config.settings.DATABASE_URL` 取出（`postgresql+asyncpg`，不打印），只放进 pytest 子进程 env；SQLite 轮去掉 `DATABASE_URL`）：

| 轮次 | 结果 | 时刻（+08:00）/ 耗时 |
|---|---|---|
| SQLite 轮 | 54 skipped（7.2~7.4 的 42 个 + 7.5 的 12 个，原因 `requires PostgreSQL`），0 failed / 0 error | 11:40:45 / 4.78 s（pytest 1.66 s） |
| PG 轮（只跑 7.5 的 12 个） | 12 passed | 11:41:04 / 14.94 s |
| PG 轮（全文件） | 54 passed、0 skipped | 11:42:45 / 79.47 s（pytest 76.40 s） |
| SQLite 轮（收尾） | 54 skipped，0 failed / 0 error | 11:55:39 / 4.86 s（pytest 1.70 s） |
| PG 轮（收尾） | 54 passed、0 failed、0 error、0 skipped | 11:55:45 / 80.55 s（pytest 77.46 s） |

- 收尾 PG 轮各例耗时：回滚两次 1.28 s、无回填记录 1.22 s、正向从未执行 0.76 s、正向失败 0.99 s、回滚失败 1.09 s、12.7 每例 0.71~0.74 s；7.2~7.4 的 42 例与「任务 7.4」同量级（Property 3 / 4 / 5 生成阶段 5.05 / 7.71 / 9.27 s）。
- 三个测试侧文件最后修改于 11:35:55（夹具）、11:37:26（辅助）、11:39:58（测试），检测器与其测试 11:45:35；收尾两轮、灵敏度与两树对照都在其后。首次全文件 PG 轮（11:42:45）早于检测器改动，被测的三个文件不导入检测器。
- 每轮输出都有 1 条环境告警：`schemathesis` 插件的 `DeprecationWarning`，与本 spec 无关。
- 落盘的输出、junit 与汇总 JSON 由启动器把连接串、`用户:口令@主机:端口`、`用户:口令` 与独立出现的口令替换为占位；收尾前扫描 `D:\pm_tmp` 下 81 个 t75 输出 / junit / JSON / 日志：上述片段与 `postgresql://`、`postgresql+asyncpg://` 前缀都是 0 处。
- 另有一个仓库外探针（11:41 前后）直接调夹具的三个流程，打印正向失败、回滚失败与被拒绝的 `rollback_to` 的实际异常类型与信息（上文「实测」即其结果），用后删除。

副作用核对：

- 本地开发库（postgres MCP 只读）：运行前（03:31:48 UTC）、首次全文件 PG 轮之后（03:44:19）、灵敏度之后（03:55:04）与收尾轮之后（03:58:24）结果相同：`authz_world%` schema 0 个、非系统 schema 0 个，任一 schema 中 `project_user_level_backfill` 与 `project_user_level_backfill_dependent` 都是 0 个，`projectuserrole` 类型 1 个（public）；public `schema_version` 199 行、最高 199（按数值与按字符串相同）、没有 200，`operator` 或 `rollback_note` 非空的行 0；`schema_migration_failures` 0 行；`project_users` 88（最大 `updated_at` 2026-10-07 08:09:10）、`project_assignments` 86（2026-10-07 04:51:58）、`staff_members` 215（2026-10-15 06:19:08）、`users` 94（2026-10-07 04:51:58）、`projects` 85（2026-10-20 11:14:02）、`logs` 94544（最大 `created_at` 2026-10-20 23:50:03）、`evidence_outbox` 748（`created_at` / `updated_at` 2026-10-20 23:38:39），与「任务 7.4」记录的值逐项相同。
- 两棵树：开始前（11:31）与收尾（11:58）各取一次。HEAD 都是 B `a02a21419a7ffef349384a766798b7ac291fca05`；基线树 `git status --porcelain=v1 -uall --ignored` 1730 行、逐字相同；实施树 74575 → 74577 行，差异只有 ` M backend/app/core/schema_drift_detector.py`、` M backend/tests/test_schema_drift_detector.py`（` M` 23 → 25，`??` 24、`!!` 74528 不变，没有新增 `.pyc`、`.hypothesis` 或 `backend/storage` 产物）。
- 两棵树都没有 `backend/backups/`；主工作树既有的 `backend/backups/`（24 项，最新修改于 2026-10-18 07:49:29，合计 28003668 字节）前后相同。按创建 / 修改时间扫描两棵树（排除 `.git`、`node_modules`），11:31 之后变动的只有实施树上表五个文件（本节写入后另多本文件）；基线树 0 项。

与任务原文 / design 的偏差：

1. 回滚失败的冲突对象用依赖视图，不是任务示例的「改动回填表结构」（理由见上）。
2. 「正向从未执行」「已回滚过一次」两种状态下经 `_execute_rollback_script` 驱动 R 副本，并另断言 `rollback_to` 在这两种状态下拒绝执行（理由见上）。
3. 隔离沿用「任务 7.2」的提交型临时 schema（同其偏差 1）。
4. 12.7 的中文别名在 pytest 节点标识里按默认转义（未开 `disable_test_id_escaping_and_forfeit_all_rights_to_community_support`），本节写原文并给出转义形式。

清理：本任务的一次性文件——`D:\pm_tmp\t75_*` 145 项（文件 106 个：启动器、四个插件（`t75_mutant`、`t75_rolemap`、`t75_driftmut`、`t75_block_pg`）、状态 / 导入扫描 / 离线比对 / 异常 / 撤回核对 / 密文扫描 / 表格核对等探针、三处插入的编辑脚本与草稿、各轮的 junit / 输出 / 汇总 JSON / 日志；目录 39 个：各轮的 `--basetemp` 与 hypothesis 目录，目录内共 1881 个文件）——于 2026-10-21 12:05:22 +08:00 删除，删除后 `D:\pm_tmp` 为空，没有其他前缀的文件，也没有 `__pycache__`。本行在删除之后直接编辑写入。

### 任务 8.1：清单共享包（2026-10-21）

经过：前两次派发都在中途断开（代码已基本写完，验证只做了一部分）；第三次派发只做复核、补验证、写本节与清理。旧探针产物凡早于对应模块最后修改时间的一律重跑；复核中对 `gates.py` 做了两处小改（见「复核结论」），改后（14:32:40）静态检查与全部探针又重跑一遍，本节数字均取自这一轮（14:34~14:37）及其后的核对。

本任务只新增共享包 `backend/scripts/gen/authz_inventory/` 的 7 个文件（未跟踪、未提交）；没有改生产代码与测试，没有写 `classify.py`、`frontend.py`、两个生成脚本、声明文件与产物，也没有新建 `backend/tests/` 下的文件（属 8.2~8.10）。

#### 新增文件

行数两种口径：A = `len(text.split("\n"))`，B = `splitlines()`。7 个文件均为 UTF-8、无 BOM、只有 LF、末尾有换行；blob 为 `git hash-object`。

| 文件 | blob | A / B | 职责 |
|------|------|-------|------|
| `__init__.py` | `387e1cfe5036c0ec5a54d927ddad20a2e5d8ed32` | 25 / 24 | 包说明：模块分工；只有 `routes` 起子进程导入被扫描树 |
| `astmodel.py` | `a0a85d433a55cdb5b8337936f5b3d91b80c15558` | 121 / 120 | 静态扫描的数据模型与问题种类常量 |
| `astscan.py` | `96fa0ddfba8441926206b3a488f21e12019ca444` | 442 / 441 | AST 扫描：导入别名（含函数体内延迟导入）、同文件常量、函数单元的签名依赖与函数体调用点、模块级路由器与路由装饰器 |
| `gates.py` | `51a81a1b44ecd6d854ba45e7da83466613499129` | 381 / 380 | 门禁登记表 + 端点 / 函数识别 + 与运行时路由表对账 |
| `render.py` | `c62ca791e49cdc344ac3b795991ccb1daf7277be` | 195 / 194 | 确定性 JSON、禁入内容检测、原子写、检查模式逐条比对 |
| `routes.py` | `3bd728defdbe785f5ea3b752bd1bc42e644eea44` | 470 / 469 | 运行时路由表（子进程）、附注扫描文件、源码声明与路由表对账 |
| `selfcheck.py` | `c1e2b53081f851f715ede4c78b5961989c16dcb7` | 172 / 171 | 合成样例框架、合成源码识别辅助、3 个演示样例与命令行入口 |

静态检查（14:32:40 之后现跑）：`ruff check --no-cache` 7 个文件 All checks passed；仓库根执行 `backend/scripts/check/check_file_size.py <7 个文件>` 退出 0；`py_compile.compile(..., doraise=True)` 7 个全过（cfile 写到仓库外，包目录与 `backend/scripts/gen/` 均无 `__pycache__`）；单文件最大 470 / 469 行，≤ 500。

#### 复核结论

通读 7 个文件，对照任务原文逐项确认：`routes.py` 把 `--root` 的 `backend` 插到 `sys.path[0]`，导入后断言 `app.__file__` 在 `<root>/backend/app` 之下（命名空间包另报）；按 `register_all_routers` 实际调用的 `register_*_routers` 逐个建空 `FastAPI()`（现为 5 个，函数名由入口函数体解析，不写死）；源码有路由装饰器而路由表里对不上的记「未注册」，表里有而对不上声明的单列 `unmatched_runtime`。`gates.py` 识别签名默认值（含参数名 `_` 与 `Annotated`、不带参数的 `Depends()` 取注解）、路由器与装饰器 `dependencies=`、注册附加依赖（取自路由表）、函数体调用（含逐层同文件辅助函数，实参逐层绑定）四处来源；条件执行、级别取字面量 / 同文件常量 / 登记默认值、注释与字符串不计、未登记依赖报错，均与原文一致。登记表含附注编辑门禁三形态与两个 design 定级形态；附注扫描文件里的依赖全部已登记（见下）。

改了两处（均在 `gates.py`）：

1. 精度修正：函数体里未直接 `await` 的异步辅助函数（如 `asyncio.gather(...)`、交给 `StreamingResponse` 的异步生成器）原先一律报「不支持的写法」，改为只在该函数（逐层同文件辅助函数）里有非中性门禁调用或本身有识别问题时才报（新增 `_Resolver.may_gate`）。全仓现算：改前已注册端点的「不支持的写法」8 条，其中 4 条正是这种误报（`doc_ai_chat._stream_chat`、`eqcr_trends` 两个查询函数、`ledger_import_v2._sse_generator_with_registry`，现读均无门禁）；改后 4 条。合成正反例 6 个：未 await 且无门禁的协程 / 异步生成器不报；未 await 且含门禁的协程、异步生成器、门禁在下一层辅助函数里的三种仍报；直接 await 的照常展开识别出 edit。附注扫描文件改前改后都是 0 条。
2. 登记表 `dedicated_wp_gate` 的来源依据原写「workpaper / cycle_engines 注册循环附加」，现扫路由表该依赖在 workpaper 758、cycle_engines 21、collaboration 15、system 9 条路由上注册附加，改为不列分组的「router_registry 在 include_router(dependencies=...) 时附加」。

未改、记入遗留的：见文末「遗留给 8.2~8.4 的问题」。

#### 模块接口摘要（供 8.2~8.4 使用）

- `routes`：`collect_route_table(root, *, timeout=900) -> RouteTable`（失败抛 `RouteCollectionError`，信息中文；子进程有副作用被拦下也抛）；`note_router_files(root) -> tuple[str, ...]`（需求 1.1 的扫描文件，相对仓库根、排序去重）；`match_declared_routes(table, declared, files) -> RouteMatch`（`registered` / `unregistered` / `unmatched_runtime`）；`routes_by_function(table)`（按（文件，`__qualname__`）归组，嵌套路由器与工厂建的路由也能归属）；`module_name(rel_file)`；常量 `WRITE_METHODS`、`NOTE_FILE_PATTERNS`、`SCHEMA`。数据结构：`RouteTable`（`groups`、`routes`、`api_route_counts`、`other_route_counts`、`app_file`、`blocked`、只供日志的 `elapsed_seconds`）、`RouteRecord`（方法、完整路径、分组、`registered`、端点文件与函数、`registration_prefix`、注册 / 路由器 / 装饰器 / 签名四组 `DependencyRef`）、`DependencyRef`（识别名、模块、qualname、种类、闭包字面量、参数名）、`DeclaredRoute`、`RouteMatch`。
- `gates`：`REGISTRY: dict[str, GateSpec]`（`GateSpec`：名称、类别、级别（固定 / `Arg` / 无）、静态参数 `Arg`、工厂、同文件具名、须 await、定义模块、叠加信息、来源依据）；`CATEGORIES`、`LEVELS`、`LEVEL_RANK`、`LEVELLED`；`analyze_module(file, source) -> ModuleInfo`（无法解析抛 `ParseFailure`）；`recognize_endpoint(info, declared, route=None) -> EndpointGates`（传路由表记录时识别注册附加依赖，并把路由器 / 装饰器 / 签名三处依赖与运行时逐项对账）；`recognize_function(info, qualname)`（任一函数单元，供影响清单）；`max_level(uses)`。结果：`EndpointGates`（`uses`、请求参数标记 `markers`、`signature_kinds`（db_session / upload_file / background_tasks）、桩 `stub`（各 raise 的错误，如 `HTTP 501`）、`issues`），`GateUse`（名称、类别、来源 `via`（registration / router / route / signature / body）、`conditional`、辅助函数链 `chain`、级别与来源 `level_origin`、静态参数 `params`、参数名 `param`、调用点 `site`）。
- `astmodel` / `astscan`：问题种类常量 `UNKNOWN_DEPENDENCY`「未识别依赖」、`LEVEL_UNDETERMINED`「级别无法静态确定」、`UNSUPPORTED`「不支持的写法」、`REGISTRY_MISMATCH`「登记表与实现不一致」；`Issue.message()` 给中文「文件::函数：种类「名称」——说明」；`ModuleInfo.declared_routes()`、`ModuleInfo.gate_definition(qualname)`（是否属某登记门禁自身实现，供「门禁内部」判定）。
- `render`：`dumps(payload, *, roots=())`（键排序、`ensure_ascii=False`、`indent=2`、末尾恰一个 LF；先 `find_forbidden`，有时间 / 机器名 / 绝对路径 / 行号 / 浮点数 / 非字符串键 / 禁用键名即抛 `RenderError`）；`sort_entries(entries, fields=ENTRY_FIELDS)`（默认 文件 → 完整路径 → 方法，同键再按规范化 JSON，与输入顺序无关）；`write_text(path, text)`（同目录临时文件 + 替换，按字节写）；`diff_entries(old, new, fields)` / `describe_diff(diff)`（检查模式的新增 / 消失 / 变化）。
- `selfcheck`：`Sample(name, expected, run)`；`run_samples` / `ensure_samples(samples, *, title)`（判错抛 `SelfCheckFailed`，信息为「样例 / 期望 / 实际」中文清单；空样例集与重名直接报错）；`recognize_source(source, function, *, file)` 与 `summarize(result)`（合成源码识别，不做运行时对账）；`DEMO_SAMPLES` 3 个；`python -B -m authz_inventory.selfcheck`（cwd `backend/scripts/gen`）。需求 1.6 的 9 个与 9.8 的 10 个样例由 8.2 / 8.4 各自定义。

#### 门禁登记表（`gates.REGISTRY`，29 项，由探针从代码现取生成）

「形态」里的「同文件具名」= 必须定义在调用方同一文件，按辅助函数展开后核对登记级别；「不要求 await」= 中性依赖在函数体里出现时不按协程核对。

| 名称 | 类别 | 级别来源 | 静态参数 | 叠加信息 | 形态 / 定义模块 | 来源依据 |
|---|---|---|---|---|---|---|
| `require_project_access` | 项目级 | 实参：位置 0 / 关键字 `min_permission`，缺省 `readonly`，字面量 | — | — | 工厂，`app.deps` | design §4.12 |
| `assert_project_permission` | 项目级 | 实参：位置 3 / 关键字 `min_permission`，缺省 `readonly`，字面量 | — | — | 函数，`app.deps` | design §4.12 |
| `require_project_permission` | 项目级 | 固定 review | `permission`：位置 0 / 关键字 `permission`，必填，字面量 | — | 工厂，`app.deps` | design §4.12 |
| `authorize_wp_edit` | 项目级（按底稿反查） | 固定 edit | — | 全局角色免查 admin / partner；全局能力 WORKPAPER_WRITE | 函数，`app.deps` | design §4.12 |
| `require_wp_edit_permission` | 项目级（按底稿反查） | 固定 edit | — | 全局角色免查 admin / partner；全局能力 WORKPAPER_WRITE | 工厂，`app.deps` | design §4.12 |
| `authorize_wp_read` | 项目级（按底稿反查） | 固定 readonly | — | 全局角色免查 admin / partner | 函数，`app.deps` | design §4.12 |
| `assert_target_accessible` | 项目级 | 固定 readonly | — | 全局角色免查 admin / partner；成员判定 成员行 ∪ 现行委派 | 函数，`app.services.custom_query.ownership_guard` | 现扫补全：disclosure_notes.trace_cell |
| `_assert_project_edit` | 项目级（对象反查） | 固定 edit | — | — | 函数，同文件具名，`app.routers.disclosure_notes` | design §4.12 |
| `_assert_object_project_access` | 项目级（对象反查） | 实参：关键字 `min_permission`，缺省 `readonly`，字面量 | — | — | 函数，同文件具名，`app.routers.disclosure_notes` | design §4.12 |
| `_assert_note_project_access` | 项目级（对象反查） | 实参：位置 3 / 关键字 `min_permission`，缺省 `readonly`，字面量 | — | — | 函数，同文件具名，`app.routers.disclosure_notes` | design §4.12 |
| `_assert_validation_project_access` | 项目级（对象反查） | 实参：位置 3 / 关键字 `min_permission`，缺省 `edit`，字面量 | — | — | 函数，同文件具名，`app.routers.disclosure_notes` | design §4.12 |
| `require_note_edit_access` | 附注编辑门禁 | 固定 review | `consol_lock`：关键字 `consol_lock`，必填，布尔字面量 | EQCR 排除；操作点 `note:edit` | 工厂，`app.services.note_edit_gate` | design §4.12 |
| `assert_note_edit_access` | 附注编辑门禁 | 固定 review | `consol_lock`：关键字 `consol_lock`，必填，布尔字面量 | EQCR 排除；操作点 `note:edit` | 函数，`app.services.note_edit_gate` | design §4.12 |
| `assert_note_edit_access_for_object` | 附注编辑门禁 | 固定 review | `consol_lock`：关键字 `consol_lock`，必填，布尔字面量 | EQCR 排除；操作点 `note:edit` | 函数，`app.services.note_edit_gate` | design §4.12 |
| `assert_note_edit_access_on_projects` | design 定级门禁 | 固定 review | `consol_lock`：关键字 `consol_lock`，必填，布尔字面量 | EQCR 排除；操作点 `note:edit`；多项目 | 函数，`app.services.note_edit_gate` | design §4.12 |
| `assert_note_role_access` | design 定级门禁 | 固定 review | `project_roles`：关键字 `project_roles`，必填，字符串集合（排序）；`denied_message`：关键字 `denied_message`，必填，字面量 | EQCR 排除；操作点 `note:edit` | 函数，`app.services.note_edit_gate` | design §4.12 |
| `_guard_action` | 交付中心门禁 | — | `action`：位置 3 / 关键字 `action`，必填，取成员名 | EQCR 排除；级别按动作 | 函数，`app.routers.deliverable` | design §4.12 |
| `require_operation` | 操作矩阵 | — | `operation`：位置 0 / 关键字 `operation`，必填，字面量 | — | 工厂，`app.deps` | design §4.12 |
| `check_consol_lock` | 合并锁 | — | — | — | 函数，`app.deps` | design §4.12 |
| `require_role` | 全局角色 | — | `roles`：位置 0 / 关键字 `allowed_roles`，必填，字符串集合（排序） | — | 工厂，`app.deps` | design §4.12 |
| `get_current_user` | 仅登录 | — | — | — | 函数，`app.deps` | design §4.12 |
| `get_current_user_sse` | 仅登录 | — | — | — | 函数，`app.deps` | design §4.12 |
| `dedicated_wp_gate` | 底稿可见性（注册附加） | — | — | — | 函数，`app.routers._wp_gate` | D6：router_registry 在 include_router(dependencies=...) 时附加 |
| `get_db` | 中性依赖 | — | — | 数据库会话（S 类判据） | 函数，不要求 await，`app.core.database` | design §4.12 |
| `get_sync_db` | 中性依赖 | — | — | 数据库会话（S 类判据） | 函数，不要求 await，`app.core.database` | design §4.12 |
| `get_redis` | 中性依赖 | — | — | — | 函数，不要求 await，`app.core.redis` | design §4.12 |
| `get_container` | 中性依赖 | — | — | — | 函数，不要求 await，`app.core.container` | 现扫补全（全仓） |
| `get_evidence_facade` | 中性依赖 | — | — | — | 函数，不要求 await，`app.routers.evidence_governance` | 现扫补全（全仓） |
| `PaginationParams` | 中性依赖 | — | — | — | 函数，不要求 await，`app.core.pagination` | 现扫补全（全仓）：请求参数类，经不带参数的 Depends() 取参数注解 |

- 与 design §4.12 登记表逐行对照：表里列出的门禁全部在册，`_assert_project_edit`（design 注「改造后消失」）现仍在 `disclosure_notes.py`，故保留；`require_project_permission` 固定 review 与 `deps.py` 实现（内部 `assert_project_permission(..., "review")`）一致。表外按现扫补全 `assert_target_accessible`（`disclosure_notes.trace_cell` 调用）、`dedicated_wp_gate`（注册附加）与 3 个中性依赖；请求参数类 `Query` / `Path` / `Body` / `Header` / `Cookie` / `File` / `Form` 不进登记表，作签名标记处理（`astmodel.PARAM_MARKERS`），`UploadFile` / `File` / `BackgroundTasks` 另记签名类别（S 类判据用）。
- 各门禁的级别参数位置、关键字名与缺省值逐个对照现行签名（`deps.py`、`note_edit_gate.py`、`disclosure_notes.py`、`deliverable.py`、`_wp_gate.py`、`ownership_guard.py`）一致；附注扫描文件里非中性门禁全部从登记的定义模块导入（`get_db` 另有 4 处经 `app.deps` 转导入，中性），属性调用只有 `ownership_guard.assert_target_accessible` 1 处，按名字识别没有误认同名函数。

#### 导入副作用的处置

收集路由必须导入被扫描树的 `app`，导入期副作用（连库、连 Redis、写日志文件、建目录、起子进程）由 `routes.collect_route_table` 统一处置，调用方不需另做：

- 子进程 `python -I -B -X utf8 routes.py --child <root> <结果文件>`：不带入父进程 `sys.path` 与 `PYTHON*` 环境、不写 `.pyc`；cwd 为临时目录（用后删除）；env 去掉含 `DATABASE_URL` / `REDIS_URL` / `_DSN` 与以 `PG` 开头的变量。
- 子进程先装审计钩子：网络（connect / bind / sendto / getaddrinfo / gethostbyname / gethostbyaddr）、写文件（结果文件除外）、增删改目录与文件、起子进程、磁盘 SQLite 一律拦下并记录；asyncpg / psycopg2 的 `connect` 另行替换为拒绝。被拦下任一项即判收集失败（`blocked` 非空抛错），不静默放过。
- 现跑：本次共收集 12 次（实施树 9 次：附注探针、全仓对账、四处来源取样各 3 轮；基线树 3 次），被拦下 0 项，导入的 `app` 均为该树的 `backend/app/__init__.py`。另用同一钩子导入 `app.main` 两树各一次（对账 N13 用），被拦下 0 项。
- 正向对照（14:33，仓库外合成树 + 钩子直测，均在 `routes.py` 最后修改之后）：连 PG / Redis 端口、DNS、写文件、追加写、`os.open` 新建、`mkdir`、删除文件、起子进程、磁盘 SQLite、`asyncpg.connect`、`psycopg2.connect`、Redis `ping` 共 13 种全部拦下并给出中文原因；`:memory:` SQLite 与读文件放行（按设计）；`backend/app` 缺 `__init__.py` 的合成树报「导入的 app 是命名空间包…不在 --root 之下」；导入期连 5432 端口的合成树报「子进程收集路由时有副作用被拦下…socket.getaddrinfo ('127.0.0.1', 5432)」；正常合成树收集到 1 条路由；三棵合成树都没留下 `__pycache__`，钩子要拦的文件与目录都没有产生。

#### 两树路由收集与附注扫描

探针在仓库外，以 `-B` / `PYTHONDONTWRITEBYTECODE=1` 运行，经 `routes.collect_route_table` 收集、`routes.note_router_files` 取扫描文件、`gates.recognize_endpoint`（带路由表记录）识别。基线树 = `D:\wt_pm_ref` @ `a02a21419a7ffef349384a766798b7ac291fca05`；实施树 = `D:\wt_pm_impl`（同一 HEAD + 未提交改动）。下表为 14:34~14:36 一轮，前两轮（14:17、14:27~14:29）除耗时外逐项相同。

| 项 | 实施树 | 基线树 |
|----|-------|-------|
| 注册分组（按 `register_all_routers` 调用顺序） | system / workpaper / report / collaboration / cycle_engines | 同左 |
| 各分组 `APIRoute` 数 | 750 / 1052 / 276 / 384 / 22 | 同左 |
| `APIRoute` 合计 | 2484 | 2484 |
| 路由表记录（按方法展开） | 2486（workpaper 1054：2 条路由各有 2 个方法） | 2486 |
| 经 `include_router` 加入的非 `APIRoute` | 0 | 0 |
| 子进程耗时 / 父进程墙钟 | 12.38 / 12.41 秒（三轮 12.12~14.70） | 12.64 / 12.69 秒（三轮 12.20~14.16） |
| 附注扫描文件 | 26 | 26（文件名逐个相同） |
| 源码声明路由 / 与路由表对上 | 168 / 168 | 168 / 168 |
| 「未注册」/ 表内对不上声明 | 0 / 0 | 0 / 0 |
| 写端点（POST / PUT / PATCH / DELETE） | 101（22 个文件；另 4 个文件无写端点） | 101（逐文件相同） |
| 识别问题：未识别依赖 / 级别无法静态确定 / 不支持的写法 / 登记表与实现不一致 / 模块级 | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |

两树 168 条端点的识别结果逐条相同（实施树尚未改附注路由）。

- 对账 N13（2489）：五个注册函数给出 2484 条。同一审计钩子下导入 `app.main` 现数（14:18，两树各一次）得 `APIRoute` 2489、非 API `Route` 4；差的 5 条是 `main.py` 直接挂在 `app` 上的 `/api/_debug/a51-capability`、`/api/_debug/a51-content-revision`、`/api/_debug/a51-registration`、`/api/version`、`/metrics`。即 N13 的 2489 是 `app.main` 的全量路由表，五个注册函数口径为 2484，两树一致，无偏差。耗时与 N13「约 15 秒」同量级。
- 对账 N12（26 个文件 / 101 个写端点）：逐项相等。探针按需求 1.2 的先后条件临时归类（只作对账，正式归类是 8.2 的 `classify.py`）：S 1 / C 28 / G 2 / E 27 / R 11 / X 1 / I 31，与 N12 逐类相等。

四处识别来源在真实路由上的取样（实施树全仓 2289 条已注册且对上声明的端点，带运行时对账识别）：注册附加依赖只有 `dedicated_wp_gate`（workpaper 758 / cycle_engines 21 / collaboration 15 / system 9 条），取样 `a171_ai_generate.a171_ai_generate` POST `/api/workpapers/{wp_id}/a171/ai-generate` 识别为 `dedicated_wp_gate`（registration）+ 签名 `get_db` / `get_current_user`、无问题；路由器 `dependencies=` 只有 `require_project_access`（workpaper 50 / system 1 条），取样 `analytical_review_save.save_industry_comparison_endpoint` POST `/api/projects/{project_id}/analytical-review/industry-comparison` 识别为 router 来源、级别 edit（字面量）、无问题；装饰器 `dependencies=` 全仓 0 条（只有合成样例覆盖）；签名与函数体见下文抽查。2289 条端点里源码声明与运行时依赖（路由器 / 装饰器 / 签名三处）对账不一致的 0 条。

#### 识别器报出的问题

附注扫描文件（26 个文件、168 条端点、101 个写端点）：未识别依赖 0、级别无法静态确定 0、不支持的写法 0、登记表与实现不一致 0、模块级问题 0，无需逐条判读。

全仓（`backend/app/` 递归 2639 个文件；供 8.4 参照，不属本任务验收）：

- 已注册端点带运行时对账识别：未识别依赖 67 条（15 个文件）、不支持的写法 4 条（`gt_coding` 2、`qc_cases` 1、`workpaper_remind` 1：签名参数默认值是请求模型实例之类的未登记调用；运行时对账显示这些参数不是依赖）。
- 未登记依赖名 12 个（附注扫描文件 0 个）：本文件依赖函数 `_services`（wp_sync_router，21 处）、`_validate_mcp_token`（4）、`require_query_builder_access`（4）、`_get_unified`（3）、`_require_admin`（feature_flags，3）、`_extract_mcp_token`（1）、`_require_manager_role`（1）、`resolve_user_actor`（1）；跨文件依赖 `require_project_delegator_pid`（20）、`require_project_delegator`（4）、`require_confirmation_token`（2）；`deps.get_current_user` 签名里的 `security`（`HTTPBearer()` 实例，在门禁自身定义内）。
- 模块级「不支持的写法」14 条 / 5 个文件：`main.py` 5 条（路由挂在 `app` 上）、`doc_ai_chat.py` 2 条（装饰器路径不是同文件静态字符串）、`wp_render_strategies` 3 个文件 7 条（工厂函数内建的路由器）。
- 声明对账：声明 2333 条，对上 2289；「未注册」45 条，其中 41 条是 `routers/eqcr/` 的子路由器（父路由器 `APIRouter(prefix="/api/eqcr")` 再 `include_router`，声明路径缺父前缀，运行时实为已注册），4 条在运行时路由表里确实没有（`wp_render_registry.py` 1、`wp_render_strategies/_e1_*_ocr.py` 3）；表内对不上声明 197 条（eqcr 41 + 工厂路由 156）。
- 静默漏识别风险面：门禁名裸引用（别名赋值 / 作回调传递）、模块级 `Annotated[..., Depends(...)]` 别名、只因 `with` 而标「条件执行」、lambda 内门禁调用、附注端点上的非路由装饰器这五种，在全仓现算均为 0 处，且各在仓库外合成文件里放一例做正向对照、都被探针检出（合成文件检出后删除）；嵌套函数内的门禁调用只有事件处理器里的中性 `get_redis` 1 处（鉴权门禁 0 处）、类方法内的鉴权门禁调用只有服务层 `QueryOrchestrator.execute` 的 `assert_target_accessible`（readonly）1 处，这两种在真实代码里命中非零。

#### 抽查（实施树，人工读源码判读 vs 识别结果）

| # | 端点 | 人工判读 | 识别结果 | 相等 |
|---|------|---------|---------|------|
| 1 | `note_wp_mapping.toggle_mode` POST `/api/disclosure-notes/{project_id}/{year}/{note_id}/toggle-mode` | 签名 `user=Depends(require_project_access("edit"))`；函数体无门禁 | `require_project_access` 签名、edit；最高 edit | 是 |
| 2 | `disclosure_notes.update_note` PUT `/api/disclosure-notes/{note_id}` | 签名只登录；函数体在 404 分支之后无条件调 `_assert_project_edit`，其内依次 `require_project_access("edit")(...)`、`require_operation("note:edit")(...)`、`check_consol_lock(...)`；嵌套 `_mutate` / `_event` 无门禁 | 登录（签名）+ 三项均经 `_assert_project_edit`、非条件执行：edit、`note:edit`、合并锁；登记级别核对无不一致 | 是 |
| 3 | `note_text_batch.apply_text_batch` POST `/api/projects/{project_id}/disclosure-note-text-batch/apply` | 签名 `current_user=Depends(require_project_access("edit"))`、`_operation=Depends(require_operation("note:edit"))`、`_lock=Depends(check_consol_lock)` | 三项均为签名依赖、参数名逐个对上；edit | 是 |
| 4 | `disclosure_notes.apply_formulas` POST `/api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas` | 签名 `require_project_access("edit")` + `_lock_check=Depends(check_consol_lock)`；函数体 try 内无门禁 | 签名 edit + 签名合并锁 | 是 |
| 5 | `note_section_lock.acquire_lock` POST `/api/projects/{project_id}/notes/locks/acquire` | 只 `get_current_user` | 仅登录；无项目级判定 | 是 |
| 6 | `disclosure_notes.upload_history` POST `/api/disclosure-notes/{project_id}/upload-history` | 签名无依赖；函数体（去 docstring）只 `raise HTTPException(status_code=501, ...)` | 无门禁；桩 `HTTP 501`；签名无数据库会话 / 上传 / 后台任务 | 是 |
| 7 | `disclosure_notes.confirm_finding` PUT `/api/disclosure-notes/findings/{validation_id}/confirm` | 函数体 `_assert_validation_project_access(db, user, validation_id, "edit")` → `_assert_object_project_access(..., min_permission=min_permission)` → 404 分支之后无条件 `assert_project_permission(..., min_permission)` | `assert_project_permission` 经两层辅助函数、级别 edit（实参逐层绑定）、非条件执行；两个同文件具名门禁的登记级别核对一致 | 是 |
| 8 | `note_export.export_word` POST `/api/projects/{project_id}/notes/export-word` | 签名只登录；函数体 `_guard_action(db, user, project_id, DeliverableAction.export)` | 登录 + `_guard_action`（动作取成员名 `export`） | 是 |
| 9 | `disclosure_notes.set_formula_gray` PUT `/api/disclosure-notes/{project_id}/formula-gray` | 签名 `require_role(["admin", "partner", "signing_partner", "manager"])` | `require_role` 签名，角色排序为 admin / manager / partner / signing_partner；无项目级判定 | 是 |
| 10 | `note_templates.create_custom_template` POST `/api/note-templates/custom` | 无任何鉴权依赖、无数据库会话 | 无门禁、无签名类别 | 是 |

覆盖任务要求的六种：签名 `require_project_access("edit")`（1、3、4）、函数体 `_assert_project_edit`（2）、`require_operation("note:edit")`（2 函数体、3 签名）、`check_consol_lock`（2、3、4）、只校验登录（5）、桩端点（6）；另含经两层辅助函数（7）、交付中心门禁（8）、全局角色（9）、无鉴权依赖（10）。

#### 其他验证

- 渲染：同一组条目按原顺序与打乱顺序各落盘一次，两份逐字节相同（sha256 前缀 `0b43752f`，83190 字节）；只有 LF、无 BOM、末尾恰一个换行；中文原样输出，没有 `\u` 转义。
- 禁入内容检测：时间、机器名、绝对路径、行号、浮点数、非字符串键、禁用键名等 11 项禁入内容全部报出，10 种合法取值 0 误报；检查模式比对的新增 / 消失 / 变化输出正常。
- 注释与条件执行：注释与 docstring 里写门禁名的合成源码不识别出门禁，写在代码里的照常识别（正反例均正确）；门禁调用放进 if / try / for / 布尔短路时只多出「条件执行」，其余识别结果不变。
- selfcheck：3 个演示样例全部通过；把一个期望故意改错后退出码为 1，并用中文列出样例名 / 期望 / 实际；命令行入口正常路径退出码 0。
- 四处识别来源在真实路由上的取样（明细见「两树路由收集与附注扫描」）：注册附加依赖取样 `dedicated_wp_gate`，路由器 `dependencies=` 取样 `require_project_access("edit")`；装饰器 `dependencies=` 全仓 0 条，只有合成样例覆盖。

#### 副作用核对

- 两棵树：`git status --porcelain=v1 -uall --ignored` 在 14:16 / 14:31 / 14:37 三次逐字相同：基线树 1730 行；实施树 74584 行，比「任务 7.5」收尾时多 7 行，即本任务新增的 7 个文件。
- 本地开发库（postgres MCP 只读）：`evidence_outbox` 752 行、最大时间 04:52:32Z，前后不变；`logs` 由 94656 行变为 94666 行，新增 10 行全是正在运行的共享开发服务的 editing-lock 续期心跳（127.0.0.1、同一用户、约每 2 分钟一条）。本任务的探针在审计钩子下运行、没有连过数据库（被拦下 0 项），这 10 行与本任务无关；但「`logs` 不变」这一条不成立，如实记录。

#### 遗留给 8.2~8.4 的问题

1. 8.2 应把这些一律判失败：任一识别问题、路由表内有对不上声明的路由、`ParseFailure`、`RouteCollectionError`、扫描文件数或写端点数为 0；S 类用识别结果的 `stub` 标签与 `signature_kinds` 判。
2. 装饰器 `dependencies=` 在全仓 0 条，8.5 / 8.8 需补合成样例；`with` 体按「条件执行」处理，目前全仓 0 处受影响。
3. 门禁被裸引用（别名赋值、作回调传递）时识别器会静默漏掉，目前全仓 0 处；若要堵上，在 `astscan` 里报「不支持的写法」，并在 8.8 加失败样例。
4. `render` 的机器名检测按本机主机名整词匹配（本机前缀 `BJ_`）；若某台机器的主机名恰好是产物里的常见词（如 `backend`、`app`），会拒绝输出。
5. 8.4 需处理：12 个未登记依赖名（见「识别器报出的问题」）；嵌套路由器 / 工厂函数建的路由，端点归属建议改用 `routes.routes_by_function`；`main.py` 直接挂在 `app` 上的 5 条路由；服务层签名默认值是未登记调用的那几条报错，建议只对端点与依赖函数计。
6. 登记表按名字匹配，不核对导入来源模块；附注扫描文件已核对没有误认，全仓范围由 8.4 视需要补核。

清理：本任务的一次性文件都在 `D:\pm_tmp\t81_*`（各轮探针脚本、探针输出与日志、两树 `git status` 快照、渲染产物、本节草稿），本次收尾用的脚本与核对输出在 `D:\pm_tmp\t81z_*`；写入本节后删除：共 85 个文件（`t81_*` 77 个、`t81z_*` 8 个，没有目录），于 2026-10-21 14:57:58 +08:00 删完，之后 `D:\pm_tmp` 为空，没有其他前缀的文件，也没有 `__pycache__`。本行在删除之后写入（写入脚本 `t81z_final.py` 开始运行即删除自身，计入上述 `t81z_*`）。

### 任务 8.2：附注写端点清册（2026-10-21）

本任务新增清册生成脚本、归类模块与目标门禁声明文件，并给共享包的 `selfcheck.py`、`render.py` 各加少量代码（均未跟踪、未提交）。没有改生产代码与测试，没有在 `backend/tests/` 下建文件（属 8.5~8.8），也没有写出清册产物 `backend/data/authz/note_write_inventory.json`（属 8.9；本任务生成的清册都写在仓库外临时文件）。前端调用点扫描属 8.3：本任务只留好接入点，清册里相应字段如实记为待接入。验证在 15:06~15:41 之间完成；最后一次改代码之后整轮重跑（15:36~15:39），本节数字都取自最终代码。

#### 新增 / 改动文件

行数两种口径：A = `len(text.split("\n"))`，B = `splitlines()`。均为 UTF-8、无 BOM、只有 LF、末尾有换行；blob 为 `git hash-object`（改后）。

| 文件 | 动作 | blob | A / B | 内容 |
|------|------|------|-------|------|
| `backend/scripts/gen/gen_note_write_inventory.py` | 新增 | `c1f9845ba9e6c938fefdf356f3339a5c2d0d8ecc` | 369 / 368 | 命令行、流程 1~8、需求 1.5 校验、检查模式；前端接入点 `FrontendScan` / `scan_frontend` |
| `backend/scripts/gen/authz_inventory/classify.py` | 新增 | `de2ccaedb64b0e70edbccc5e4ff2d7f2bb09538c` | 306 / 305 | 归类、现门禁视图、声明校验、目标门禁合并、「现门禁已等于目标门禁」判据、覆盖集合 |
| `backend/scripts/gen/authz_inventory/selfcheck.py` | 改（8.1 时 `c1e2b530…`，172 / 171） | `96cecc5e6213ce2b96b595e0f79d7edf37909ca6` | 288 / 287 | 加需求 1.6 的 9 个样例 `NOTE_INVENTORY_SAMPLES`；命令行入口依次跑演示样例与清册样例，控制台改 UTF-8 |
| `backend/scripts/gen/authz_inventory/render.py` | 改（8.1 时 `c62ca791…`，195 / 194） | `1b3f57719eba3d385f9778d5f1b0d1a0654a6f12` | 205 / 204 | 加 `utf8_console()` 与 `import sys`，供两个生成脚本与 `selfcheck` 命令行共用；原有函数未改 |
| `backend/data/authz/note_write_target_declarations.json` | 新增（目录 `backend/data/authz/` 随之新建） | `15f0d0d6c333b01ae56bc8d43b79b2da7862576c` | 263 / 262 | 34 条目标门禁声明（见下）；JSON 不受行数门约束 |

- 共享包其余 5 个文件（`__init__.py`、`astmodel.py`、`astscan.py`、`gates.py`、`routes.py`）blob 与任务 8.1 记录逐个相同。8.1 的结论不受影响：演示样例 3 个照常通过；`render.dumps` 未改，`utf8_console` 加入前后生成的清册逐字节相同。包内现为 8 个模块（design §10 写作时「7 个模块」：8.1 把识别器拆成 `astmodel` / `astscan` / `gates`，本任务加 `classify`，`frontend` 待 8.3）。
- 静态检查（最终代码）：`ruff check --no-cache`（生成脚本 + 包内 8 个文件）All checks passed；仓库根执行 `backend/scripts/check/check_file_size.py` 传入这 10 个文件（含声明 JSON）退出 0；新文件单个最大 369 行（≤ 500）。

#### 命令行与退出码

`python backend/scripts/gen/gen_note_write_inventory.py [--check] [--out PATH] [--root REPO]`

- `--root`：被扫描的仓库根，默认脚本所在仓库。源码只读取；路由表经 8.1 的 `routes` 子进程导入（`-I -B`、副作用拦截）。
- `--out`：清册文件。生成模式写到这里（`render.write_text` 原子写），检查模式拿它作比对基准；默认为脚本所在仓库的 `backend/data/authz/note_write_inventory.json`。「检查刚生成的临时产物」即 `--check --out <临时文件>`。
- 声明文件固定为脚本所在仓库（`Path(__file__).parents[3]`）的 `backend/data/authz/note_write_target_declarations.json`，默认产物路径同理，都不随 `--root` 变化。
- 退出码：0 = 生成完成 / 检查一致（打印「附注写端点清册与仓库现状一致」）；1 = 自检判错、需求 1.7 任一失败条件、参数错误（argparse 默认的 2 改为 1，免得与漂移混淆）；2 = 检查模式下产物与现算不一致或产物不存在。
- 检查模式不写任何文件：先按字节比较现算文本与 `--out`；不同则逐条比对条目（键 =（文件，完整路径，方法），列新增 / 消失 / 变化及变化的字段名）与其余顶层字段（`schema` / `scan` / `counts` / `editor_unmatched` / `editor_write_call_total`）；字段全同而文本不同（只改了格式）也判漂移并单独说明。
- 需求 1.7 的失败（退出 1）：stderr 先一行「附注写端点清册生成失败（N 项；不写出清册，已提交的清册保持不变）」（检查模式为「检查失败」），再逐项「- 原因」；原因带方法、完整路径、文件::函数，以及未识别的名称或不成立的校验项。自检判错（退出 1）：「附注写端点清册内置合成样例自检未通过：k / 9 个样例判错，不写出产物。」后逐个列样例名、期望、实际。
- 控制台一律按 UTF-8 输出（`render.utf8_console()`：stdout / stderr 不是 UTF-8 时 `reconfigure`），不随 `PYTHONIOENCODING` 变化。
- 可编程入口：`run(root=, out=, check=, declarations=, samples=)` 返回退出码；`build(root, declarations)` 只现算、不写文件。8.8 可直接传合成声明与样例（本任务的探针就是这样注入的）。
- 收集路由表的子进程把结果写在系统临时目录、用后删除（8.1 机制），这是检查模式里唯一的文件写入，不在任何仓库或 `--out` 位置。

#### 流程（design §4.12 第 1~8 步）

1. 自检：`selfcheck.ensure_samples(NOTE_INVENTORY_SAMPLES)`；判错即退出 1，不扫描。
2. 端点：`--root` 下没有 `backend/app/routers/`、或扫描文件数为 0 → 失败；逐个 AST 解析，任一 `ParseFailure` → 失败（此时不收集路由表，导入同样会失败）；模块级问题（路由声明写法）计入失败；`collect_route_table` 抛 `RouteCollectionError` → 失败；`match_declared_routes` 之后表内对不上源码声明的路由 →「不支持的写法」失败；取 POST / PUT / PATCH / DELETE，写端点数为 0 → 失败；未注册的照记（`registered: false`）。
3. 现门禁：`gates.recognize_endpoint`（已注册的带路由表记录做运行时对账）；任一识别问题 → 失败，该端点不归类。
4. 归类：`classify.classify`；无法归类 → 失败。
5. 目标门禁：`classify.resolve_target`；I 类没有声明 → 失败（I 类没有默认值）。
6. 前端：`scan_frontend` 现返回 None（见「留给 8.3 的接口」）。
7. 校验（需求 1.5）：① 各类计数之和 = 写端点总数；② 每个（方法，完整路径）恰好一次；③ 编辑器内写调用数守恒——前端未接入时记「待接入（任务 8.3），本次未校验」，不算成立；④ 每条声明都对应现存写端点（比需求「与默认值不同的声明」更严：全部声明都须对上）。①②④任一不成立 → 失败。
8. 输出：`render.dumps`（确定性 JSON）；生成模式写 `--out`，检查模式比对。

8.1 遗留第 1 条（任一识别问题、表内对不上声明的路由、`ParseFailure`、`RouteCollectionError`、扫描文件数或写端点数为 0 一律判失败；S 类用 `stub` 与 `signature_kinds` 判）按上述第 2~4 步全部落实。

#### 归类与目标门禁（`classify.py`）

按 S → C → G → E → R → X → I 取第一个满足的，只看非中性门禁（登记表类别「中性依赖」以外）：

| 类 | 判据 |
|----|------|
| S | 识别结果 `stub` 非空，其中的错误都在 {HTTP 410, HTTP 501, NotImplementedError} 之内（「已废弃」= 410；「未实现」= 501 或 `NotImplementedError`），且 `signature_kinds` 与 {db_session, upload_file, background_tasks} 不相交 |
| C | 文件名以 `consol_` 开头 |
| G | 有交付中心门禁 `_guard_action` |
| E | 有附注编辑门禁三形态之一，或项目级判定（`gates.LEVELLED` 各类别）的最高级别为 edit / review（design 定级两形态固定 review，也归这里） |
| R | 项目级判定的最高级别为 readonly |
| X | 有全局角色判定 `require_role`，没有项目级判定 |
| I | 非中性门禁只有仅登录，或一个都没有 |

- 识别结果带任何问题的不归类，由生成脚本逐项报错；以上都不满足的（例如只有操作矩阵、只有合并锁、只有底稿可见性）返回「无法按需求 1.2 归类：现门禁为 …」，生成脚本判失败。
- 现门禁视图 `current_gate`：`forms`（每处非中性门禁的名称、来源 `via`、条件执行、辅助函数链 `helper`、级别、静态参数，按来源 → 名称排序）、`max_level`、`operations`（`require_operation` 的权限点 ∪ 附注编辑 / design 定级门禁自带的 `note:edit`）、`consol_lock`（有 `check_consol_lock` 或 `consol_lock=True`）、`eqcr_exclusion`、`global_roles`、`identity_only`（有仅登录且只有仅登录）、`stub`。
- 目标门禁：E 默认附注编辑门禁，S / C / G / R / X 默认保持现门禁，I 没有默认值；有声明一律取声明（`declared: true`）。
- 「现门禁已等于目标门禁」：保持现门禁恒为是，待 design 核对恒为否。目标为附注编辑门禁时，除仅登录外的非中性判定至少一处、全部是附注编辑门禁三形态之一、都不是条件执行——改造后还留着原来的 `require_project_access` 等即判否（对应 design §4.7「同时删掉原有判定」）。目标为 design 定级门禁时同上，但全部须是声明的那个门禁，且静态参数（含实参给出的级别）与声明逐项相等。声明里的判定项目来源不能静态核对，不进判据；`eqcr` 只在声明校验里核对与门禁自身是否排除 EQCR 一致。
- 覆盖集合 = `in_coverage(category, target)`：E、I 两类中目标为附注编辑门禁的端点。
- 声明校验（design §5.4）：顶层恰为 `schema`（`note_write_target_declarations/v1`）与 `declarations`；每条 `method` 为大写写方法、`path` 以 `/` 开头、`reason` 非空；`target` 四选一，字段按目标限定（附注编辑门禁可选 `project_from`；design 定级必填 `gate` / `params` / `project_from` / `eqcr`；另两种只有四个公共字段），多余字段报错；`gate` 须是登记表里项目级或 design 定级类别的门禁，`params` 的键须恰为该门禁的静态参数键（级别由实参给出的门禁含 `level`），取值符合形态（级别 / 布尔 / 字符串集合 / 字面量）；`project_from` 为不重复的非空列表，取值限 path / query / body / object_id，含 path 时完整路径须有 `{project_id}`；`eqcr` 为 deny / allow，且 deny 当且仅当该门禁自身排除 EQCR；（方法，完整路径）重复报错。

#### 内置合成样例（需求 1.6，`selfcheck.NOTE_INVENTORY_SAMPLES`）

合成源码经 `gates.analyze_module` / `recognize_endpoint`（不带路由表）识别、`classify.classify` 归类；比对视图为（类别，最高级别，识别问题（种类，名称））。

| # | 样例 | 合成写法 | 期望 |
|---|------|---------|------|
| 1 | 无任何鉴权依赖 | 签名只有 `db=Depends(get_db)` | I，无级别 |
| 2 | 只依赖登录 | `user=Depends(get_current_user)` | I |
| 3 | 只在 docstring 与注释里写有 `require_project_access("edit")` | docstring 与注释各一处（注释另有一行 `await assert_project_permission(…, "edit")`）；签名只有登录，函数体无门禁 | I |
| 4 | 签名依赖 `require_project_access("edit")` | `_=Depends(require_project_access("edit"))` | E，edit |
| 5 | 函数体经同文件辅助函数以 edit 级判定 | `await _check_project(db, user, project_id, "edit")`，辅助函数内 `await assert_project_permission(db, user, project_id, level)` | E，edit |
| 6 | 调用附注编辑门禁 | `await assert_note_edit_access(db, user, project_id, consol_lock=False)` | E，review |
| 7 | 签名依赖 `require_project_access("readonly")` | 同 4，级别 readonly | R，readonly |
| 8 | 函数体只抛出「未实现」错误 | docstring + `raise HTTPException(status_code=501, ...)`，签名只有路径参数 | S |
| 9 | 挂载未登记的依赖 | `tenant=Depends(load_tenant)` | 不归类，问题（未识别依赖，load_tenant） |

`python -B -m authz_inventory.selfcheck`（cwd `backend/scripts/gen`）依次跑演示 3 个与清册 9 个，全部通过、退出 0。故意改错一个期望的验证见「检查模式与失败条件」。

#### 目标门禁声明（`note_write_target_declarations.json`，34 条）

表 B 26 条（附注编辑门禁 17、design 定级 9）+ 保持现门禁 8 条（`note_templates.py` 5、`account_note_mapping.py` 3）；每条都有 `reason`，没有 `pending_design_review`。「现类别」与「现门禁已等于目标」取自最终代码在实施树上现算的清册（改造前，表 B 26 个端点都只校验登录，故全部为否）。

| # | 组 | 方法 | 完整路径（文件::函数） | 现类别 | 目标 | 门禁与参数 | 判定项目 | EQCR | 现门禁已等于目标 | 理由 |
|---|----|------|------------------------|:-----:|------|-----------|---------|:----:|:---:|------|
| 1 | B1 | POST | `/api/projects/{project_id}/note-template/save`（`note_custom_template.py::save_custom_template`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.1（表 B B1）：写本项目自定义附注模板的新版本，属附注数据 |
| 2 | B1 | POST | `/api/projects/{project_id}/note-template/restore`（`note_custom_template.py::restore_custom_template`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.1（表 B B1）：回滚产生本项目自定义附注模板的新版本，属附注数据 |
| 3 | B1 | POST | `/api/disclosure-notes/{project_id}/{year}/refresh-from-workpapers`（`note_wp_mapping.py::refresh_from_workpapers`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.1（表 B B1）：从底稿刷新、写入附注表格数据 |
| 4 | B1 | POST | `/api/disclosure-notes/{project_id}/{year}/{note_section}/refresh-from-workpaper`（`note_wp_mapping.py::refresh_section_from_workpaper`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.1（表 B B1）：从底稿刷新、写入本章节表格数据 |
| 5 | B1 | POST | `/api/projects/{project_id}/apply-group-baseline`（`group_note_baseline.py::apply_group_baseline`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.1（表 B B1）：写入路径中子项目的附注章节；只判被写入的路径项目，不判基线所属的母公司项目（8.1 默认口径） |
| 6 | B2 | PUT | `/api/disclosure-notes/{project_id}/wp-mapping`（`note_wp_mapping.py::update_mapping`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.2（表 B B2）：写附注与底稿的取数映射，属附注数据 |
| 7 | B2 | POST | `/api/disclosure-notes/{project_id}/{year}/refresh-all-bindings`（`note_wp_mapping.py::refresh_all_bindings`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.2（表 B B2）：全量取数刷新，写附注表格（含公式二次求值），属附注数据 |
| 8 | B2 | PUT | `/api/disclosure-notes/{project_id}/sections/trim`（`note_trim.py::save_trim`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.2（表 B B2）：写章节裁剪状态，属附注数据 |
| 9 | B2 | POST | `/api/disclosure-notes/{project_id}/{year}/auto-trim`（`note_trim.py::auto_trim`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.2（表 B B2）：自动裁剪，写章节裁剪状态，属附注数据 |
| 10 | B2 | POST | `/api/projects/{project_id}/notes/custom-sections/create`（`note_custom_section.py::create_custom_section`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.2（表 B B2）：新增自定义附注章节，属附注数据 |
| 11 | B2 | POST | `/api/projects/{project_id}/notes/custom-sections/save-as-template`（`note_custom_section.py::save_as_template`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.2（表 B B2）design 定级（design §4.7、§4.8）：写共享章节模板库（非附注数据），发布模板的主体与编辑主体一致；门禁按路径项目判定之后再校验请求体里的章节属于路径项目，不属于返回 404，堵住跨项目读章节 |
| 12 | B2 | POST | `/api/projects/{project_id}/notes/custom-sections/apply-template`（`note_custom_section.py::apply_template`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.2（表 B B2）：把章节模板应用为本项目附注章节，属附注数据 |
| 13 | B2 | POST | `/api/projects/{project_id}/notes/conversion/preview`（`note_conversion.py::preview_conversion`） | I | `design_gate` | `require_project_access`（level="readonly"） | path | allow | 否 | 需求 8.2（表 B B2）design 定级（design §4.8）：只读计算、不落库（任务 8.2 现读 NoteConversionService.preview_conversion：只查询 projects 与读取预置映射，路由不提交事务），readonly 级、放行本项目 EQCR |
| 14 | B2 | POST | `/api/projects/{project_id}/notes/conversion/execute`（`note_conversion.py::execute_conversion`） | I | `design_gate` | `assert_note_role_access`（denied_message="仅本项目经理或合伙人可切换附注模板类型"，project_roles=["manager", "partner"]） | path | deny | 否 | 需求 8.2（表 B B2）允许更严（design §4.8）：同时改附注章节与 projects.template_type，模板类型影响报表口径，只放行本项目经理与合伙人 |
| 15 | B2 | POST | `/api/projects/{project_id}/notes/conversion/rollback`（`note_conversion.py::rollback_conversion`） | I | `design_gate` | `assert_note_role_access`（denied_message="仅本项目经理或合伙人可切换附注模板类型"，project_roles=["manager", "partner"]） | path | deny | 否 | 需求 8.2（表 B B2）允许更严（design §4.8）：撤销转换同样改回附注章节与 projects.template_type，与执行转换同级 |
| 16 | B2 | POST | `/api/group-note-baselines`（`group_note_baseline.py::save_baseline`） | I | `design_gate` | `assert_note_edit_access_on_projects`（consol_lock=false） | query | deny | 否 | 需求 8.2、8.5（表 B B2，design §4.8）：路径中没有项目，判定查询参数 project_id 所指的来源项目；读来源项目附注并发布为共享集团基线 |
| 17 | B3 | POST | `/api/projects/{project_id}/notes/locks/acquire`（`note_section_lock.py::acquire_lock`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.3（表 B B3，design §4.8）：持锁即编辑意图，不能编辑的人持锁会挡住真正的编辑者 |
| 18 | B3 | POST | `/api/projects/{project_id}/notes/locks/heartbeat`（`note_section_lock.py::heartbeat`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.3（表 B B3，design §4.8）：心跳续期即继续持锁编辑，与获取锁同级 |
| 19 | B3 | POST | `/api/projects/{project_id}/notes/locks/release`（`note_section_lock.py::release_lock`） | I | `design_gate` | `require_project_access`（level="readonly"） | path | allow | 否 | 需求 8.3（表 B B3，design §4.8）：只释放本人的锁（service 按 user_id 过滤），降级后仍须能释放自己遗留的锁，只影响本人 |
| 20 | B3 | POST | `/api/projects/{project_id}/notes/locks/force-release`（`note_section_lock.py::force_release_lock`） | I | `design_gate` | `assert_note_role_access`（denied_message="仅本项目经理或合伙人可强制释放章节锁"，project_roles=["manager", "partner"]） | path | deny | 否 | 需求 8.3（表 B B3，design §4.8）：释放他人的锁；落实函数说明「项目经理强制解锁」的角色限制，合伙人在项目内职级高于经理一并放行 |
| 21 | B3 | POST | `/api/projects/{project_id}/data-lock/lock`（`note_data_lock.py::lock_on_sign_off`） | I | `design_gate` | `assert_note_role_access`（denied_message="仅本项目经理或合伙人可锁定报表附注数据"，project_roles=["manager", "partner"]） | path | deny | 否 | 需求 8.3（表 B B3，design §4.8）：签字后锁定报表附注数据是签字收尾动作，只放行本项目经理与合伙人 |
| 22 | B3 | POST | `/api/projects/{project_id}/data-lock/unlock`（`note_data_lock.py::unlock_data`） | I | `design_gate` | `assert_note_role_access`（denied_message="仅管理员可解除报表附注数据锁定"，project_roles=[]） | path | deny | 否 | 需求 8.3（表 B B3，design §4.8）：落实函数说明「管理员解锁」的角色限制（项目角色集合为空，只有 admin 通过）；项目级判定照常（已归档返回 423） |
| 23 | B3 | POST | `/api/projects/{project_id}/data-lock/snapshot`（`note_data_lock.py::create_snapshot`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.3（表 B B3，design §4.8）：手动创建数据快照，属编辑过程的版本留存 |
| 24 | B3 | POST | `/api/projects/{project_id}/notes/group-template/save`（`note_group_template.py::save_as_group_template`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.3（表 B B3，design §4.8）：读本项目附注结构并保存为共享集团模板，与另存章节模板同理 |
| 25 | B3 | POST | `/api/projects/{project_id}/notes/group-template/distribute`（`note_group_template.py::distribute_template`） | I | `design_gate` | `assert_note_edit_access_on_projects`（consol_lock=false） | path、body | deny | 否 | 需求 8.3、8.5（表 B B3，design §4.8）：写入每个目标项目的附注；路径项目与请求体 target_project_ids 逐一判定，任一不通过整单拒绝，错误信息列出未通过的项目 |
| 26 | B3 | POST | `/api/projects/{project_id}/notes/group-template/detach`（`note_group_template.py::detach_from_group_template`） | I | `note_edit_gate` | — | path | — | 否 | 需求 8.3（表 B B3，design §4.8）：改本项目与集团模板的继承关系，即本项目附注结构的归属 |
| 27 | R3 | POST | `/api/note-templates/custom`（`note_templates.py::create_custom_template`） | I | `keep_current` | — | — | — | 是 | 范围外 R3（design §9）：note_templates.py 的全局附注模板写端点没有任何鉴权依赖，经核实也没有全局中间件或注册依赖兜底（design N8），本 spec 不改，另立 spec |
| 28 | R3 | PUT | `/api/note-templates/custom/{template_id}`（`note_templates.py::update_custom_template`） | I | `keep_current` | — | — | — | 是 | 范围外 R3（design §9）：note_templates.py 的全局附注模板写端点没有任何鉴权依赖，经核实也没有全局中间件或注册依赖兜底（design N8），本 spec 不改，另立 spec |
| 29 | R3 | DELETE | `/api/note-templates/custom/{template_id}`（`note_templates.py::delete_custom_template`） | I | `keep_current` | — | — | — | 是 | 范围外 R3（design §9）：note_templates.py 的全局附注模板写端点没有任何鉴权依赖，经核实也没有全局中间件或注册依赖兜底（design N8），本 spec 不改，另立 spec |
| 30 | R3 | POST | `/api/note-templates/custom/{template_id}/rollback`（`note_templates.py::rollback_template`） | I | `keep_current` | — | — | — | 是 | 范围外 R3（design §9）：note_templates.py 的全局附注模板写端点没有任何鉴权依赖，经核实也没有全局中间件或注册依赖兜底（design N8），本 spec 不改，另立 spec |
| 31 | R3 | POST | `/api/note-templates/validate`（`note_templates.py::validate_note_data`） | I | `keep_current` | — | — | — | 是 | 范围外 R3（design §9）：note_templates.py 的全局附注模板写端点（含校验）没有任何鉴权依赖，经核实也没有全局中间件或注册依赖兜底（design N8），本 spec 不改，另立 spec |
| 32 | R10 | PUT | `/api/account-note-mapping/{project_id}`（`account_note_mapping.py::save_mapping`） | E | `keep_current` | — | — | — | 是 | 范围外 R10（design §9）：account_note_mapping.py 的 3 个 edit 级写端点（写作时前端零调用点），本 spec 不改其门禁 |
| 33 | R10 | POST | `/api/account-note-mapping/{project_id}/auto-generate`（`account_note_mapping.py::auto_generate_mappings`） | E | `keep_current` | — | — | — | 是 | 范围外 R10（design §9）：account_note_mapping.py 的 3 个 edit 级写端点（写作时前端零调用点），本 spec 不改其门禁 |
| 34 | R10 | DELETE | `/api/account-note-mapping/{project_id}/{mapping_id}`（`account_note_mapping.py::delete_mapping`） | E | `keep_current` | — | — | — | 是 | 范围外 R10（design §9）：account_note_mapping.py 的 3 个 edit 级写端点（写作时前端零调用点），本 spec 不改其门禁 |

与 design §4.8 / §5.4 的对照：

- 表 B 26 个端点与 §4.8 逐行一一对应（方法 + 完整路径；§4.8 的 `{pid}` / `{sec}` / `...` 是简写，声明用代码里的完整路径与参数名），目标门禁、判定项目、EQCR 与 §4.8 逐条相同；附注编辑门禁 17 条 = §4.7 的 B1 ×5 + B2 ×7 + B3 ×5。
- `conversion/preview` 按 §4.8「实施时现读确认不落库」现读：`NoteConversionService.preview_conversion` 只查询 `projects` 并读预置映射 JSON，路由不提交事务 ⇒ 保持 readonly，不改为附注编辑门禁。
- 写法差异（不改结论）：① §4.8 的 `assert_note_role_access({manager, partner}, "…")` 是位置简写，现行门禁（任务 6.3）是仅关键字参数（`*, project_roles, denied_message`），声明按参数键写；四处角色集合都是 {manager, partner}，解锁为空集合。② `require_project_access("readonly")` 的参数键是登记表里的 `level`（不是关键字名 `min_permission`）。③ `assert_note_edit_access_on_projects` 两处声明 `consol_lock: false`（§4.8 未写，按需求 6.6「新纳入的端点一律 consol_lock=False」）。④ §5.4 示例里 `conversion/execute` 的 `params` 只写了 `project_roles`；本文件要求 `params` 恰含该门禁的全部静态参数，故另带 `denied_message`（文案取 §4.8）。⑤ §5.4 示例里 `account_note_mapping` 的路径（`/api/disclosure-notes/{project_id}/account-note-mapping/…`）是示意，实际三条为 `/api/account-note-mapping/{project_id}`（PUT）、`/api/account-note-mapping/{project_id}/auto-generate`（POST）、`/api/account-note-mapping/{project_id}/{mapping_id}`（DELETE）。⑥ 附注编辑门禁的声明另带可选的 `project_from: ["path"]`（记 §4.8「判定项目」一列），不带 `eqcr`（该门禁总是排除 EQCR）。
- §4.8 的「前端调用（初核）」一列本任务未核：调用点由 8.3 现算，差异届时记入。
- 保持现门禁的理由按任务原文指向 design §9 范围外登记：`note_templates.py` → R3，`account_note_mapping.py` → R10。

#### 清册产物格式（与 design §5.3 示例的差异）

顶层键与示例相同（`schema`、`scan`、`counts`、`endpoints`、`editor_unmatched`、`editor_write_call_total`）；条目按（文件名，完整路径，方法）排序；`file` 与 `scan.files` 为 `backend/app/routers/` 下的文件名。与示例不同处：

- `scan.frontend`：新增，现为「待接入（任务 8.3）」。E、I 两类条目带 `editor_call_points` / `outside_editor_files`，值为 null（其余类别不带这两个键，需求 1.3 只要求 E、I）；`editor_unmatched` 与 `editor_write_call_total` 为 null。没有用空列表或 0 冒充「无调用点」。
- `target_gate` 一律七个键：`kind`、`declared`、`reason`、`gate`、`params`、`project_from`、`eqcr`。`project_from` 只取声明，未声明条目为 null，不像示例那样从现门禁推出 `object_id`：判定项目要看门禁实参（同是函数体 `assert_note_edit_access`，A1 取请求体、A3~A5 取路径），静态识别不取这一项；端点级测试用的项目来源由 10.2 的配方表给出。
- `current_gate.forms[]` 除示例的 `name` / `via` / `conditional` / `helper` 外另有 `level` 与 `params`；`helper` 为辅助函数链（由外到内）的列表或 null。`current_gate` 另有 `stub`（桩端点的错误，如 `["HTTP 501"]`）。
- 现算产物：122752 字节、4508 行（A 口径），sha256 `8d23186a5c3ddbffae23c932bb6fc0c080fbd03f86f05bf01aa74e6fae13e046`。

#### 两树现算与对账

最终代码，`--out` 指向仓库外临时文件；每棵树以设 `PYTHONIOENCODING=utf-8` 与不设各生成一次，4 次都退出 0（各 12.6~14.7 秒）。四份产物逐字节相同（sha256 同上），也与首轮（15:21~15:23，加入 `utf8_console` 之前）的四份相同，即同一树生成两次逐字节相同、两树结果相同（实施树尚未改附注路由）。

| 项 | 实施树 | 基线树 | 写作时快照 | 差异 |
|----|-------|-------|----------|------|
| 扫描文件 / 写端点（其中未注册） | 26 / 101（0） | 同左 | 26 / 101（N12、F10） | 无 |
| 各类计数 | S 1 / C 28 / G 2 / E 27 / R 11 / X 1 / I 31 | 同左 | N12：S 1 / C 28 / G 2 / E 27（表 A 24 + `account_note_mapping` 3）/ R 11 / X 1 / I 31（表 B 26 + `note_templates` 5） | 无；构成按文件逐个对上：E 中 24 条即 design §4.7 的 A1~A24（`disclosure_notes` 12、`note_offline` 1、`note_text_batch` 4、`note_content_templates` 3、`note_advanced` 3、`note_wp_mapping.toggle_mode` 1），另 3 条为 `account_note_mapping`；I 中 26 条即 §4.8 表 B，另 5 条为 `note_templates` |
| 现门禁分布（F10 口径） | 最高 edit 41 / readonly 16 / `_guard_action` 2 / 仅登录或全局角色 36 / 无鉴权依赖 6 | 同左 | F10：项目级 59（edit 41、readonly 16、`_guard_action` 2）+ 仅校验登录 36 + 无任何鉴权依赖 6 | 无（F10 的「仅校验登录 36」含 5 个 `require_role` 端点：`consol_note_formulas.py` 4 个与 `set_formula_gray`） |
| 目标门禁 | 附注编辑门禁 41（其中声明 17）/ design 定级 9（声明 9）/ 保持现门禁 51（声明 8）/ 待 design 核对 0 | 同左 | — | — |
| 覆盖集合（E、I 两类中目标为附注编辑门禁） | 41 = E 24（E 27 − 声明保持现门禁的 `account_note_mapping` 3）+ I 17 | 同左 | 41（design §4.7：表 A 24 + 表 B 17） | 无 |
| 目标为 design 定级门禁 | 9（都是 I 类表 B 端点） | 同左 | 9（design §4.8、任务原文） | 无 |
| 现门禁已等于目标门禁 | 是 51（保持现门禁的 51 条）、否 50（附注编辑门禁 41 + design 定级 9） | 同左 | — | 符合改造前预期：只有保持现门禁的条目为是 |
| 覆盖集合 ∩ 现门禁含合并锁 | 13 | 同左 | 13（design §4.7：A1~A5、A9~A12、A14~A17） | 无（只作预览，正式冻结属 8.9） |
| 与类别默认值相同的声明 | 0 | 0 | — | — |

#### 检查模式与失败条件（最终代码整轮，21 个用例全部按期望）

| 用例 | 输入 | 退出码 | 输出要点 |
|------|------|:-----:|---------|
| 检查一致 ×2 | 实施树（不设编码变量）、基线树（设 utf-8）各一次，`--out` = 刚生成的临时产物 | 0 | 打印「附注写端点清册与仓库现状一致」 |
| 改一条 | 副本改 `update_mapping` 的 `target_gate.reason` | 2 | 「变化：note_wp_mapping.py /api/disclosure-notes/{project_id}/wp-mapping PUT（字段：target_gate）」 |
| 增 / 删 / 改 + 顶层 | 副本改 `toggle_mode` 的类别、删 `release_lock`、加一条虚构条目、改 `counts.I` | 2 | 新增 1（release_lock）、消失 1（虚构条目）、变化 1（字段：category）、「顶层字段变化：counts」 |
| 只改格式 | 同内容，缩进改为 4 | 2 | 「条目与顶层字段逐项相同，但文本不同（格式或换行被改动）」 |
| 产物缺失 | `--out` 指向不存在的文件 | 2 | 「已提交的清册不存在」；文件未被创建 |
| 参数错误 | `--bogus` | 1 | 「参数错误：unrecognized arguments: --bogus」 |
| 自检判错 | `run(samples=…)`：第 4 个样例的期望改为 R | 1 | 「自检未通过：1 / 9 个样例判错，不写出产物」，列出样例名、期望 `{'category': 'R', …}`、实际 `{'category': 'E', …}`；未扫描 |
| 声明对不上现存写端点 | `run(declarations=…)`：现行 34 条 + 1 条虚构路径 | 1 | 1 项：「需求 1.5 校验不成立（每条声明都对应现存写端点）：声明 POST /api/projects/{project_id}/notes/no-such-endpoint（目标 note_edit_gate）对不上现存的写端点」 |
| 未登记依赖 | 合成树（一个附注路由文件、一个写端点挂 `Depends(load_tenant)`，能正常导入注册）+ 空声明 | 1 | 2 项：「POST /api/sample/{project_id}/write：backend/app/routers/note_sample.py::write_endpoint：未识别依赖「load_tenant」」与计数守恒不成立（0 ≠ 1） |
| 同上走命令行 | 同一合成树 + 仓库的声明文件 | 1 | 36 项（再加 34 条「声明对不上现存的写端点」） |
| 无法解析 | 合成树的附注路由文件有语法错误（命令行） | 1 | 「文件无法解析：backend/app/routers/note_sample.py：无法解析（invalid syntax …）」与「有文件无法解析，未收集运行时路由表」 |
| 扫描文件数为 0 | 合成树没有匹配的附注路由文件（命令行） | 1 | 「扫描到的附注路由文件数为 0（…没有匹配 note* / *note* / disclosure* 的 .py）」 |
| 未注册 + 多路由 | 合成树：一个附注文件不注册；另一文件有两个装饰器的函数、`api_route` 两个方法，注册前缀 `/v2` | 0 | 5 条：未注册 1 条（`registered: false`、`registry_group: null`），两个装饰器、两个方法各成一条，完整路径带 `/v2` |
| 前端接入点 ×2 | 进程内把 `scan_frontend` 换成返回合成 `FrontendScan` | 0 / 1 | 守恒时第 3 项「成立」、E / I 58 条填入调用点；不守恒时「编辑器范围内写方法调用 4 ≠ 命中 1 + 表 C 1 + 表 D 0 + 未解析 1」 |
| selfcheck 命令行 | `python -B -m authz_inventory.selfcheck`（不设编码变量） | 0 | 演示 3 个、清册 9 个全部通过 |

- 退出 1 与 2 的用例都没有产生 `--out` 文件，被比对的产物 sha256 前后不变；首轮另做过目录快照（大小 / sha256 / mtime_ns），检查与失败用例前后 `D:\pm_tmp` 无新增、无删除、无变化。合成树、两棵树的 `backend/scripts/gen/` 与 `D:\pm_tmp` 下都没有 `__pycache__`。
- 自检判错、声明对不上、未登记依赖（第一行）、未注册 + 多路由与前端接入点经 `run()` 注入合成输入（仓库外包装脚本，以 `-B` 运行）；其余走真实命令行。
- 另以进程内探针核对判据（合成源码）：目标为附注编辑门禁时，只挂 `require_note_edit_access` ⇒ 已等于，旁边仍留 `require_project_access("edit")` ⇒ 未等于；目标为 `assert_note_role_access` 时，参数相同 ⇒ 已等于、文案不同 ⇒ 未等于、放进 if ⇒ 未等于；`require_project_access("readonly")` 声明 ⇒ 已等于，同一端点目标改为附注编辑门禁 ⇒ 未等于。声明校验 9 种错误逐条报出（空理由、小写方法、`eqcr` 与门禁不一致、`params` 键不全、路径无 `{project_id}` 却含 path、`keep_current` 带 `gate`、未知 `target`、`gate` 不是项目级门禁、重复声明），顶层格式不符整体报错。

#### 编码验证

整轮 21 个用例都以子进程运行、按字节捕获输出，UTF-8（`errors="replace"`）解码后替换字符全部为 0；生成与检查各有设 `PYTHONIOENCODING=utf-8` 与不设两种运行。整轮第一遍发现 `python -B -m authz_inventory.selfcheck` 在不设该变量时按本地代码页输出（没有报错，但 UTF-8 解码得 61 个替换字符；生成脚本本身没有这个问题），已改为与生成脚本共用 `render.utf8_console()`，第二遍为 0。

#### 留给 8.3 的接口

- `gen_note_write_inventory.scan_frontend(root, endpoints, table) -> FrontendScan | None`：现返回 None。8.3 写好 `authz_inventory/frontend.py` 后改为调用它；`endpoints` 是本次现算的条目（含 method / path / category），`table` 是运行时路由表（表 C / 表 D 与全部已注册路由比对用）。
- `FrontendScan`：`call_points` / `outside_files`（以（方法，完整路径）为键，只含 E、I 两类；没有调用点的给空序列）、`table_c` / `table_d` / `unresolved`（各项为 dict，宜带 design §4.12 的调用点键 `key`）、`write_call_total`、`matched_call_total`。
- 接上后：E、I 条目的 `editor_call_points` / `outside_editor_files` 由 `_apply_frontend` 填入，`editor_unmatched` = {table_c, table_d, unresolved}，`editor_write_call_total` = `write_call_total`，`scan.frontend` 由「待接入」变为「已扫描」，校验第 3 项按 `write_call_total == matched_call_total + 表 C + 表 D + 未解析` 判定，不成立即失败。这条接线本任务只用合成扫描结果走过一遍（见上表），没有真实数据。
- 检查模式对 `editor_unmatched` 目前按整体比对（只报「顶层字段变化：editor_unmatched」）；需求 1.10 要逐条列出表 C / 表 D / 未解析的新增 / 消失 / 变化，8.3 定下各项的键后在 `_drift` 里按键逐条比对。
- 「编辑器内无调用点」与范围外文件（需求 1.3）在条目里的取值形态由 8.3 定；本任务没有写任何前端相关数据。

#### 副作用核对

- 两棵树 `git status --porcelain=v1 -uall --ignored`（15:06 / 15:23 / 15:40 三次）：基线树三次逐字相同，1730 行；实施树 74584 → 74587 行，新增的 3 行是 `?? backend/data/authz/note_write_target_declarations.json`、`?? backend/scripts/gen/authz_inventory/classify.py`、`?? backend/scripts/gen/gen_note_write_inventory.py`（`selfcheck.py`、`render.py` 原已未跟踪，改动不增行），没有行消失。
- 本地开发库（postgres MCP 只读）：`evidence_outbox` 752 行、最大 `created_at` 04:52:32Z，前后不变；`logs` 由 94681 行（07:06:41Z）变为 94698 行（07:40:45Z），新增 17 行全是 `update` / `editing-lock` / 127.0.0.1 / 同一用户（07:08:02Z~07:40:01Z，约每 2 分钟一条），是正在运行的共享开发服务的编辑锁续期心跳。本任务的进程只读源码，收集路由表的子进程在审计钩子下运行，没有连库。07:48:47Z 复查：`evidence_outbox` 仍为 752 行；`logs` 94705 行，07:40:45Z 之后除心跳外另有 3 行 `create` / `report-config` / 127.0.0.1 / 无用户（07:44:38Z~07:44:42Z）。其时本任务已结束生成脚本的最后一次运行（15:39 +08:00），只在拼装与写入验收记录、不发任何请求，判为共享开发服务上其他会话的请求，与本任务无关（本句为清理后补记，补记脚本用后已删）。
- 未以实施树代码启动后端；未改主工作树文件与暂存区；未提交。

#### 其他说明

- 校验第 4 项比需求原文更严：全部声明（不只是与类别默认值不同的）都须对应现存写端点。改造后表 B 端点会变成 E / R 类，那时 17 条附注编辑门禁声明等于 E 的默认值，汇总行会报「与类别默认值相同的声明 N 条」，不判失败；是否删除这些声明（理由随之消失）留给改造任务决定。
- argparse 的用法行（`usage: …`）是英文，错误信息为中文。
- 生成脚本的「未注册」与「一个函数多条路由 / 多个方法」两条路径在真实附注文件里现算均为 0 处，只由合成树验证过。

清理：本任务的一次性文件都在 `D:\pm_tmp\t82_*`（探针与包装脚本、4 棵合成树与合成声明、生成的临时清册与改动副本、子进程输出、两树 git 状态与目录快照、本节草稿与拼装片段、acceptance.md 插入前的备份）；写入本节后删除：顶层 84 项，共 103 个文件、20 个目录（目录都在合成树里），于 2026-10-21 15:48:40 +08:00 删完，之后 `D:\pm_tmp` 为空，没有 `__pycache__`。删除前最后一次核对两树 `git status --porcelain=v1 -uall --ignored`：基线树 1730 行，与起始逐字相同；实施树 74587 行，比起始只多本任务的 3 个新文件（acceptance.md 原已未跟踪）。本行在删除之后写入（写入脚本 `t82_zz_cleanup.py` 计入上述文件数，运行中已删除自身）。

### 任务 8.9：生成改造前清册、冻结合并锁适用集合并纳入产物（2026-10-22）

#### 执行环境

- 基线树：`D:\wt_pm_ref`（detached HEAD = `c6f14d5eb`，即需求 / 设计的现状基线，B 的父提交）。运行前 `git status --porcelain` 为空。
- 生成脚本在实施 worktree（`D:\wt_pm_impl`）内执行，`--root` 指向基线树。声明文件与已提交产物按脚本所在仓库（即 worktree）定位，不随 `--root` 变化。
- Python：`D:\GT_plan\.venv\Scripts\python.exe`。

#### 附注写端点清册（改造前，基线树 c6f14d5eb）

命令：`gen_note_write_inventory.py --root D:\wt_pm_ref --out D:\wt_pm_impl\backend\data\authz\note_write_inventory.json`

| 指标 | 现算值 | 写作时快照（出处） | 对账 |
|------|-------|-------------------|------|
| 扫描文件 | 26 | 26（F10、N12） | 无差异 |
| 写端点总数 | 101 | 101（F10、N12） | 无差异 |
| S | 1 | 1（N12） | 无差异 |
| C | 28 | 28（N12） | 无差异 |
| G | 2 | 2（N12） | 无差异 |
| E | 27 | 27（N12：表 A 24 + `account_note_mapping` 3） | 无差异 |
| R | 11 | 11（N12） | 无差异 |
| X | 1 | 1（N12） | 无差异 |
| I | 31 | 31（N12：表 B 26 + `note_templates` 5） | 无差异 |
| 各类计数之和 | 101 = 总数 | — | 校验成立 |
| 覆盖集合 | 41 | 41（design §4.7） | 无差异 |
| 覆盖集合 ∩ 现门禁含合并锁 | 13 | 13（design §4.7：A1~A5、A9~A12、A14~A17） | 无差异 |
| 目标门禁分布 | note_edit_gate 41 / design_gate 9 / keep_current 51 | — | 41+9+51=101=总数 |
| 现门禁已等于目标门禁 | 51 | — | 均为 keep_current 类（S/C/G/R/X），改造前不动 |
| 现门禁未等于目标门禁 | 50 | — | 改造对象（E/I 类） |

覆盖集合 ∩ 合并锁的 13 个端点逐个列出：

| # | 方法 | 路径 | 对应表 A |
|---|------|------|---------|
| 1 | POST | /api/disclosure-notes/generate | A1 |
| 2 | PUT | /api/disclosure-notes/{note_id} | A2 |
| 3 | DELETE | /api/disclosure-notes/{project_id}/{year}/sections/{note_section:path} | A3 |
| 4 | PATCH | /api/disclosure-notes/{project_id}/{year}/sections/{note_section:path} | A4 |
| 5 | PATCH | /api/disclosure-notes/{project_id}/{year}/restore/{note_id} | A5 |
| 6 | POST | /api/disclosure-notes/{project_id}/{year}/{note_section}/apply-formulas | A11 |
| 7 | POST | /api/disclosure-notes/{project_id}/{year}/{note_section}/clear-formulas | A9 |
| 8 | PUT | /api/disclosure-notes/{project_id}/{year}/{note_section}/formulas | A12 |
| 9 | POST | /api/disclosure-notes/{project_id}/{year}/{note_section}/restore-auto | A10 |
| 10 | POST | /api/projects/{project_id}/disclosure-note-import/parse-knowledge | A15 |
| 11 | POST | /api/projects/{project_id}/disclosure-note-import/parse-upload | A14 |
| 12 | POST | /api/projects/{project_id}/disclosure-note-text-batch/apply | A17 |
| 13 | POST | /api/projects/{project_id}/disclosure-note-text-batch/preview | A16 |

与写作时快照逐个相等（A1~A5、A9~A12、A14~A17 = 13 个）。

自检：「附注写端点清册内置合成样例自检通过：9 个样例全部按期望」。
校验：需求 1.5 四项——各类计数之和成立，每个（方法，完整路径）恰好一次成立，编辑器内写调用数守恒待接入（任务 8.3），每条声明对应现存写端点成立。

#### edit 级影响清单（改造前，基线树 c6f14d5eb）

命令：`gen_edit_level_impact_inventory.py --root D:\wt_pm_ref --out D:\wt_pm_impl\backend\data\authz\edit_level_impact_inventory.json`

| 指标 | 现算值 | 写作时快照（出处） | 对账 |
|------|-------|-------------------|------|
| 扫描文件 | 2637 | — | — |
| 门禁调用点 | 594 | —（F12 口径不含门禁内部 / 免查 / 附录，不直接可比） | 见下 |
| 门禁调用文件数 | 145 | —（F12：100 个文件） | 差异因口径不同（F12 只看 edit 级调用点 246 处） |
| 直接比较位置 | 5 | — | — |
| 附录（展示/同步/复制用途的读取） | 3 | — | — |
| 端点（去重） | 586 | — | — |

自检：「edit 级影响清单内置合成样例自检通过：10 个样例全部按期望」。

门禁调用子项分域小计：

| 业务域 | 门禁调用点数 |
|--------|------------|
| collaboration | 44 |
| cycle_engines | 19 |
| gate_internal | 2 |
| report | 110 |
| system | 274 |
| unregistered | 3 |
| workpaper | 142 |

与 F12 的差异说明：F12 的 246 处 / 100 个文件只计「edit 级调用点」（`require_project_access("edit")` 224 + `assert_project_permission(..., "edit")` 5 + `authorize_wp_edit` 8 + `require_wp_edit_permission` 4 + `_assert_project_edit` 5 = 246）。影响清单的 594 处包含全部级别的门禁调用点（edit + review + readonly + 门禁内部 + 免查），口径更宽。

另生成一份基线版 `edit_level_impact_inventory_baseline.json`（同一参数，`--out` 改路径），留作任务 19.1 两树对比。两份文件逐字节相同（347,994 bytes）。

#### 检查模式

1. `gen_note_write_inventory.py --check`：退出码 0，输出「附注写端点清册与仓库现状一致」。  
   ✅ 通过：worktree 的附注路由文件与基线树相同（任务 2-8 未改附注路由），产物与现算一致。

2. `gen_edit_level_impact_inventory.py --check`：退出码 2（漂移）。  
   已知原因：`--check` 扫描 worktree 代码（已有任务 2-8 的改动：`deps.py` 新增 `_load_member_level`、删缓存函数；`review_workflow.py` 有重复条目键），而已提交的产物是从基线树生成的。漂移项：  
   - `[gate_points]` 重复条目键 `(review_workflow.py, initiate_signing, require_project_access)`  
   - `[direct_comparisons]` 新增 `app/deps.py _load_member_level`  
   - `subtotals` / `totals` 随之变化  
   此漂移属预期行为：改造前产物如实反映基线状态。端点改造（任务 10/11）完成后重生成并重跑 `--check`，产物将与 worktree 对齐。

#### 产物文件

| 文件 | 大小 | 有效 JSON |
|------|------|----------|
| `backend/data/authz/note_write_inventory.json` | 122,752 bytes | ✅ |
| `backend/data/authz/edit_level_impact_inventory.json` | 347,994 bytes | ✅ |
| `backend/data/authz/edit_level_impact_inventory_baseline.json` | 347,994 bytes | ✅ |

三个文件均在 worktree（`D:\wt_pm_impl`）的 `backend/data/authz/` 目录下。`note_write_inventory.json` 内现门禁 ≠ 目标门禁的 50 个条目如实标注（`current_equals_target: false`）。

#### 清理

一次性探针脚本 `D:\wt_pm_impl\_task89_counts.py` 待删。基线树运行后 `git status --porcelain` 为空。

### 任务 8.10：检查模式守卫测试（2026-10-22）

#### 前置修复

任务 8.9 生成的 `edit_level_impact_inventory.json` 与 worktree 当前代码已漂移（任务 3.4 移除权限缓存后 `deps.py` 变化：新增 `_load_member_level`，删除缓存函数，`review_workflow.py` 路由表有重复条目键）。运行 `--check` 退出码 1（非 2，因 `diff_entries` 遇重复键报错而非漂移）。以当前 worktree 代码重新生成：

```
D:\GT_plan\.venv\Scripts\python.exe backend/scripts/gen/gen_edit_level_impact_inventory.py --out backend/data/authz/edit_level_impact_inventory.json
```

重新生成后 `--check` 退出码 0。附注写端点清册 `--check` 未漂移（note 路由文件未变）。

#### 新增测试文件

`backend/tests/test_authz_inventories_check_mode.py`（4 个测试，无 skip / xfail 标记）：

| 测试 | 描述 |
|------|------|
| `TestCheckMode::test_note_write_inventory_check_mode` | 子进程 `--check`，断言退出码 0、stdout 含「附注写端点清册与仓库现状一致」、无替换字符 |
| `TestCheckMode::test_edit_level_impact_inventory_check_mode` | 子进程 `--check`，断言退出码 0、stdout 含「edit 级影响清单与仓库现状一致」、无替换字符 |
| `TestDoubleGenerateIdentical::test_note_write_inventory_double_generate` | 子进程两次 `--out` 写临时文件，两次结果逐字节相同，且与已提交产物逐字节相同 |
| `TestDoubleGenerateIdentical::test_edit_level_impact_inventory_double_generate` | 同上，对 edit 级影响清单 |

子进程环境 `PYTHONIOENCODING=utf-8`；stdout / stderr 以 `errors="replace"` 解码后断言无 `\ufffd` 替换字符。

#### 运行结果

常规运行（`pytest -v --tb=short`）：**4 passed**，172.39s。

以 `-W error::pytest.PytestUnhandledThreadExceptionWarning` 复跑：**4 passed**，170.68s。唯一 warning 为 schemathesis `DeprecationWarning`（无关）。

## 既有测试改写对照

按需求 12.8：逐个测试函数新旧对照，原有每条断言都有对应的新断言；不删除测试函数，因口径消失而不再成立的写明理由与接替它的测试。

| 测试文件 | 改写前函数 | 改写后函数 | 原断言 → 新断言（逐条） | 任务 |
|---|---|---|---|---|
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_premise_reviewer_roles_are_review_level` | `test_premise_role_map_matches_expected_table` | ① `ROLE_MAP[k][1].value == "review"`（k = `signing_partner` / `partner` / `manager` / `qc` / `eqcr`，只断言级别）→ 逐键 `(项目角色.value, 级别.value) == 期望值`：`signing_partner` / `partner` → (partner, edit)、`manager` → (manager, edit)（口径变化 review → edit，需求 2.1），`qc` → (qc, review)、`eqcr` → (partner, review)，另断言项目角色；② `ROLE_MAP[k][1].value == "edit"`（k = `auditor` / `assistant`）→ 同一逐键断言 (auditor, edit)；新增 ③ 键集合等于期望表（13 键，含原先未覆盖的 `合伙人`、`项目经理`、`质控`、`独立复核合伙人`、`审计员`、`助理`；增删任一键即红，失败信息列出多出 / 缺少的键）④ 逐键取值类型为 `(ProjectUserRole, PermissionLevel)` ⑤ 取值为 (partner, review) 的键集合 == `{eqcr, 独立复核合伙人}` ⑥ 生产 `EQCR_ROLE_ALIASES` == 同一集合。期望表共用 `backend/tests/role_map_expected.py`；docstring 按需求 2.6 改写 | 2.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_premise_reviewers_are_review_level` | `test_premise_role_map_matches_expected_table` | 原断言与上一行 ①② 逐条相同 → 新断言与上一行 ①~⑥ 逐条相同（同一期望表模块）；docstring 按需求 2.6 改写 | 2.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_review_level_member_can_use`（6 例，缓存替身返回 review） | 同名（24 例：质控 / EQCR 4 个别名 × 6 端点，成员行取 `ROLE_MAP` 值并带同角色现行委派） | `status_code == 200` → `(status_code, json) == (200, 该端点期望响应体)`；新增：成员行 == 期望表取值，业务桩调用次数逐键相等（放行恰 1 次，裁剪另含质量分重算 1 次），生产 `assert_project_permission` 执行 2 次 | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_edit_level_member_can_use`（6 例，缓存 edit） | 同名（54 例：合伙人 / 经理 / 审计员 9 个别名 × 6 端点） | 同上一行 | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_readonly_member_is_blocked`（6 例，缓存 readonly） | 同名（6 例：未登记委派角色 `观察员` → (readonly, readonly)） | `403 and "权限不足" in text` → `(403, {"detail": "权限不足"})`；新增：成员行 == (readonly, readonly)，业务 0 次，门禁执行 2 次（路由级放行、端点级拒绝） | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | （无） | `test_non_member_is_blocked`（新增，6 例：身份④） | 新增（需求 9.4 非成员）：`(403, {"detail": "权限不足"})`，业务 0 次，门禁执行 1 次（路由级 readonly 即拦下） | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_edit_endpoints_still_block_reviewers`（1 例：缓存 review 被拒、edit 放行） | 同名（4 例：质控 / EQCR 4 个别名被拒，经理放行） | ① 被拒 `403 and "权限不足"` → `(403, {"detail": "权限不足"})` + 业务 0 次；② 放行 `200` → `(200, {"id": PROC})` + `mark_complete` 1 次、质量分重算 1 次 + 门禁执行 2 次 | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_member_signs_only_for_self`（缓存 readonly） | 同名（`观察员` 成员） | ① 签本人 `200` → `(200, {"success": True})` + `sign` 桩恰 1 次、参数 == (项目, 本人, "A17-7") + 门禁执行 1 次；② 签他人 `403 and NOT_SELF in text` → `(403, {"detail": NOT_SELF})`；③ `undefined` `422` → `(422, {"detail": "user_id 不是合法的用户 ID"})`；新增：后两次业务 0 次 | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_non_member_cannot_sign`（缓存未命中 + 假会话查无此人） | 同名（身份④） | `403 and "权限不足" in text` → `(403, {"detail": "权限不足"})`；新增：业务 0 次，门禁执行 1 次 | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | `test_my_signing_tasks_requires_login_and_self` | 同名（身份④；未登录 = 不 override 当前用户） | ① 本人 `200` → `(200, [])` + `get_my_pending_tasks` 恰 1 次、参数 == (本人,) + 门禁执行 0 次；② 他人 `403 and NOT_SELF` → `(403, {"detail": NOT_SELF})`；③ 未登录 `status_code in (401, 403)` → `(401, {"detail": "Not authenticated"})`（逐值，不再容纳两种取值） | 3.2 |
| `backend/tests/test_phase8_endpoint_role_levels.py` | （无） | `test_wp_procedures_registration_adds_only_the_visibility_gate`（新增） | 新增：`wp_procedures.router` 生产注册恰 1 次，除 tags 外只有 `dependencies == [dedicated_wp_gate]`；另四个 router 生产注册不附加依赖（钉住本文件挂载口径只少了可见性门，见任务 3.2 小节发现 1） | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_non_member_is_blocked_before_any_business_call`（27 例，缓存未命中 + 假会话查无此人） | 同名（27 例，身份④） | ① `403 and "权限不足" in text` → `(403, {"detail": "权限不足"})`；② 记账 `calls == []` → 27 个业务桩计数全 0；新增：生产 `assert_project_permission` 执行 1 次 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_readonly_member_can_view`（12 例，缓存 readonly） | 同名（12 例，`观察员`） | `200` → `200` + 业务桩计数逐键 == 该端点期望（如任务进度 = `get_job` 1 + `get_job_items` 1；AI 表述规范检查端点本身不调业务 = 空）；新增：成员行 == (readonly, readonly) | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_readonly_member_cannot_generate`（14 例） | 同名（14 例，`观察员`） | `403 and "权限不足"` → `(403, {"detail": "权限不足"})`；`calls == []` → 业务计数全 0 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_team_member_can_generate_deliverables`（20 例：缓存 review / edit × 10 端点，参数 `level`） | 同名（40 例：`qc` / `partner` / `manager` / `auditor` × 10 端点；参数改为 `alias`，用例 id 后缀由 `-review` / `-edit` 改为别名） | ① `200` → `200`；② `calls` 非空 → 业务桩计数逐键 == 该端点期望（恰好调到该调的）；新增：成员行 == 期望表取值，`_guard_action` 执行 1 次 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_only_preparers_can_rerun_the_chain`（4 例：缓存 review 被拒、edit 放行） | 同名（4 例：每端点 `qc`、`eqcr` 被拒，`partner` / `manager` / `auditor` 放行） | ① 被拒 `403 and "权限不足"` → `(403, {"detail": "权限不足"})`（质控、EQCR 各一）+ 业务计数全 0；② 放行 `200 and calls` → 三个别名各 `200` + 业务计数逐键 == 期望 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_admin_bypasses_membership`（26 例，缓存未命中 + 全局 admin） | 同名（26 例，身份⑧） | `200` → `200` + 业务计数逐键 == 期望 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_eqcr_on_project_can_view_but_not_generate`（替身 `deliverable._is_project_eqcr` 返回 True + 缓存 review） | 同名（真实 `eqcr` 委派：成员行 (partner, review) + 人员库记录 + 现行委派，全局 partner；`_is_project_eqcr` 不替换） | ① 生成 10 入口 `403 and "权限不足"` + `calls == []` → `(403, {"detail": "权限不足"})` + 业务计数全 0 + `_guard_action` 执行 1 次；② 查看 12 入口 `200` → `200` + 业务计数逐键 == 期望；新增前提：成员行 == (partner, review)，`is_project_eqcr` 为真 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_role_matrix_applies_to_one_click_too`（缓存 edit + 全局 readonly） | 同名（经理成员行 (manager, edit) + 全局 readonly） | `403 and "权限不足"` → `(403, {"detail": "权限不足"})`；新增：成员行 == (manager, edit)，业务 0 次，`_guard_action` 与成员校验各执行 1 次（成员校验已过，拦人的是角色矩阵） | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_anonymous_is_rejected`（4 例） | 同名（4 例，不 override 当前用户） | `status_code in (401, 403)` → `(401, {"detail": "Not authenticated"})`；新增：业务 0 次，门禁执行 0 次 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_compare_only_reads_this_projects_execution`（假会话记录 SQL 文本） | 同名（加 `pg_only`，真 PG 权限世界，`观察员` 成员；理由见任务 3.2 小节发现 2） | ① `404 and "执行记录不存在" in text` → `(404, {"detail": "执行记录不存在"})`（另一项目下同 id 的执行记录真实存在）；② WHERE 之后含 `chain_executions.project_id` → 同一断言（会话 `do_orm_execute` 事件记录语句文本）；新增：门禁执行 1 次；对照：同一记录改属本项目后 `(200, {"execution_id": EXEC, "year": 2025, "changes": [], "total_changes": 0})` | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_batch_execute_skips_projects_without_edit`（缓存按项目返回 edit / None） | 同名（目标项目经理成员行 (manager, edit)，另一项目无成员行） | ① `200` → `200`；② `(success, skipped, failed) == (1, 1, 0)` → `(total, success, skipped, failed) == (2, 1, 1, 0)`；③ 跳过项 `status == "skipped" and "权限不足" in reason` → `results` 逐值 == [成功项, {"project_id": 另一项目, "status": "skipped", "reason": "无权执行：权限不足"}]；④ `calls.count("execute_full_chain") == 1` → 桩所收 `project_id` 列表 == [目标项目] 且业务计数 == {execute_full_chain: 1}；新增：成员校验执行 2 次 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_lineage_only_touches_deliverables_of_this_project`（5 例，假会话返回交付件归属） | 同名（5 例：`word_export_task` 真实行，先改属另一项目、再删除） | ① `403 and "交付物不属于该项目"` → `(403, {"detail": "交付物不属于该项目"})`；② `calls == []` → 业务计数全 0；③ `404 and "交付物不存在"` → `(404, {"detail": "交付物不存在"})`；新增：404 时业务计数全 0 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_mutation_guard_without_membership_lets_outsider_generate` | `test_guard_blocks_outsider_only_for_missing_membership`（改名） | 原：把 `deliverable.assert_project_permission` 换成空操作，外人在 10 个生成入口都 200。需求 12.1 禁止替换 `assert_project_permission`（需求 12.13 扫描会命中），改为数据对照：同一外人（身份④）先 `(403, {"detail": "权限不足"})`、业务 0 次、`_guard_action` 与成员校验各执行 1 次；补一条 (qc, review) 成员行后同一请求 200、业务计数逐键 == 期望。结论同原用例：拦外人的是 `_guard_action` 里的成员校验 | 3.2 |
| `backend/tests/test_deliverable_generation_membership_auth.py` | `test_mutation_dependency_without_membership_lets_outsider_in` | `test_dependency_blocks_outsider_only_for_missing_membership`（改名） | 原：把 `deps.assert_project_permission` 换成直通，外人在 15 个依赖门禁端点都 200。改为数据对照（理由同上）：同一外人先 `(403, …)`、业务 0 次、`require_project_access` 的依赖闭包执行 1 次、`_guard_action` 0 次；补一条 (manager, edit) 成员行后 200、业务计数逐键 == 期望 | 3.2 |
| `backend/tests/ledger_import/test_sign_convention_api.py` | 夹具 `_as_edit_level_member`（autouse：缓存替身返回 edit，改全局 `app.main.app` 的 overrides） | 夹具 `world` + `client`（成员行取 `ROLE_MAP["auditor"]` = (auditor, edit)；`world.client(sign_convention.router)`，前缀同生产注册，不经响应包装中间件）；`project_id` 夹具由随机 id 改为目标项目 | 夹具本身无断言 | 3.2 |
| `backend/tests/ledger_import/test_sign_convention_api.py` | `test_anomaly_list_returns_structured_response` | 同名 | `200` + 先 `body.get("data", body)` 解包再按模型逐字段 → `200` + 直接按 `SignAnomalyListResponse` 逐字段（不再容纳两种响应形态）；新增：门禁执行 1 次 | 3.2 |
| `backend/tests/ledger_import/test_sign_convention_api.py` | `test_anomaly_list_accepts_filters` | 同名 | `200` → `200` + 响应体逐值 == {"anomalies": [], "total": 0, "sign_convention_version": "v2_category_natural_positive"}；新增：门禁执行 1 次 | 3.2 |
| `backend/tests/ledger_import/test_sign_convention_api.py` | `test_direction_override_returns_structured_response` | 同名 | 同 `test_anomaly_list_returns_structured_response`（`DirectionOverrideResponse` 逐字段，四条原断言保留） | 3.2 |
| `backend/tests/ledger_import/test_sign_convention_api.py` | `test_direction_override_validates_reason` | 同名 | `422` → `422` + 校验错误（类型，位置）== [("string_too_short", ["body", "override_reason"])]；新增：门禁执行 1 次（edit 门禁先放行，再校验请求体） | 3.2 |
| `backend/tests/ledger_import/test_sign_convention_api.py` | `test_batch_confirm_returns_count` | 同名 | 同 `test_anomaly_list_returns_structured_response`（`BatchConfirmResponse` 逐字段，两条原断言保留） | 3.2 |
| `backend/tests/ledger_import/test_sign_convention_api.py` | `test_batch_confirm_validates_reason` | 同名 | `422` → `422` + [("string_too_short", ["body", "confirm_reason"])]；新增：门禁执行 1 次 | 3.2 |
| `backend/tests/test_wp_disclosure_sync.py` | `test_sync_403_for_non_admin_without_project_access`（缓存未命中 + MagicMock 会话查无此人） | 同名（身份④：另一项目上 (manager, edit)） | `status_code == 403` → `(403, {"detail": "权限不足"})`；新增：同步与自动校验桩 0 次，门禁执行 1 次 | 3.2 |
| `backend/tests/test_wp_disclosure_sync.py` | `test_sync_403_for_readonly_user`（缓存 readonly） | 同名（`观察员` → (readonly, readonly) 成员行） | 保留「readonly 被 edit 门禁拒绝」：`status_code == 403` → `(403, {"detail": "权限不足"})`；新增：成员行 == (readonly, readonly)，桩 0 次，门禁执行 1 次 | 3.2 |
| `backend/tests/test_wp_disclosure_sync.py` | `test_sync_with_edit_user_succeeds`（缓存 edit） | 同名（`ROLE_MAP["auditor"]` → (auditor, edit) 成员行） | ① `200` → `200`；② `body["created"] is True` → 保留，另断言响应体逐值 == 桩返回值 + `texts_synced: 0`；新增：同步桩恰 1 次且项目 / `wp_id` / `section_id` / 当前用户逐值相等，同步后自动校验恰 1 次，门禁执行 1 次 | 3.2 |
| `backend/tests/test_phase8.py` | `TestPermissionCache::test_cache_miss_returns_none` | 已删除，接替：3.5 `test_permission_cache_removed.py` | 原断言 `await _get_cached_permission(随机用户, 随机项目) is None`。删除理由：design D3、§2.2（12.8 行）裁定移除权限缓存，被测函数不复存在，口径消失；且任务 3.3 实测改动前读路径恒返回 None（Redis 可用、条目已写入时也是 None），本断言在改动前就恒真。接替：任务 3.5 的 AST 守卫断言 `deps` 与 `ownership_guard` 不再定义、不再引用三个缓存函数与 `PERM_CACHE_TTL`，`_load_member_level` 与三个级别判定点的函数体不引用 Redis 客户端 | 3.4 |
| `backend/tests/test_phase8.py` | `TestPermissionCache::test_set_and_get_cache` | 已删除，接替：3.5 `test_permission_cache_removed.py` | 原断言 `result is None or result == "edit"`（需求 5.7 所指的宽松断言）。删除前已按需求 12.8 在改动前的读路径上收紧为 `result == "edit"` 实跑：红在取回值断言 `assert None == 'edit'`（任务 3.3），与 design N1 互证。删除理由与接替同上一行 | 3.4 |
| `backend/tests/test_phase8.py` | `TestPermissionCache::test_invalidate_cache` | 已删除，接替：3.5 `test_permission_cache_removed.py` | 原用例没有 assert 语句，只验「调用 `invalidate_permission_cache(随机用户, 随机项目)` 不抛」。删除理由：该函数生产代码零调用（需求 F3）并随缓存删除；接替同上 | 3.4 |
| `backend/tests/test_d4_import_permission_gate.py` | `test_authorize_wp_read_allows_readonly_member` | 同名 | 断言 `pid == _PROJECT_ID` 原样保留。假会话对成员级别查询的返回值由「成员行形状的 MagicMock（`pu.permission_level = MagicMock(value="readonly")`）」改为 `PermissionLevel.readonly`：`_load_member_level` 只取 `permission_level` 一列，标量就是级别枚举本身。不改时在新代码上红为 `HTTPException 403 无底稿访问权限`（MagicMock 的 `.value` 是自动属性，级别按 0 计），属需求 12.8 所说「因口径变化而失败、需要改写」；改后 10 passed | 3.4 |
| `backend/tests/test_project_endpoint_authorization_baseline.py` | 模块常量 `_PROJECT_LEVEL_TOKENS`（17 项） | 同名常量（20 项：末尾追加 `require_note_edit_access`、`assert_note_edit_access`、`assert_note_role_access`） | 读取它的 17 个测试函数函数体与断言逐字未改：经 `_has_auth` / `_AUTH_TOKENS` 的 `test_no_new_unauthorized_project_endpoint`、`test_known_gaps_only_shrink`、`test_fixed_endpoint_stays_authorized`（6 例）与五个 `test_scanner_*`；经 `_scan_identity_only` 的 `test_identity_only_endpoints_do_not_grow`、`test_identity_only_baseline_is_not_stale`、`test_t_accounts_uses_project_level_auth`；经 `_matches` 的 `test_prefixed_scanner_sees_the_blind_spot`、`test_no_new_prefixed_unauthorized_endpoint`、`test_prefixed_known_gaps_only_shrink`、`test_self_auth_endpoints_really_verify`、`test_prefixed_identity_only_do_not_grow`、`test_prefixed_scanner_self_check`。本文件原 29 例改动前后全部 passed，三个维度的扫描结果在两棵树上逐条相同（见「任务 6.5」现算计数） | 6.5 |
| `backend/tests/test_project_endpoint_authorization_baseline.py` | （无） | `test_note_edit_gate_tokens_are_really_project_level[eqcr]` / `[permission]` / `[role]`（新增，3 例） | 新增（需求 6.10 ①②，与角色限定形态先调判定实现）：对真实 `note_edit_gate.py` 调 `note_gate_ast_facts`，逐键断言为真，失败信息逐键写明 | 6.5 |
| `backend/tests/test_project_endpoint_authorization_baseline.py` | （无） | `test_note_gate_facts_can_fail`（新增） | 新增：不满足的合成源码 → `{"permission": False, "eqcr": False, "role": False}`，逐值相等 | 6.5 |
| `backend/tests/test_disclosure_notes_project_gate_contract.py` | 模块说明 | 同（末尾补一段，说明文末的 6.10 断言与共用判定函数） | 无断言改动：原 10 个测试函数（22 例）与 `BODY_GATES` / `DEPENDS_GATES` / `BUSINESS_CALLS` / `NO_PROJECT_DATA` / `CASES` / `FUNCS` 逐字未改（`CASES` 等的改造在 10.1）；22 例改动前后全部 passed | 6.5 |
| `backend/tests/test_disclosure_notes_project_gate_contract.py` | （无） | `TestNoteEditGateIsFalsifiable::test_requires_review_membership_unconditionally`、`::test_calls_eqcr_judgment`（新增，2 例） | 新增（需求 6.10 ①②）：对真实门禁源码断言 `note_gate_ast_facts(...)["permission"]` / `["eqcr"]` 为真 | 6.5 |
| `backend/tests/test_disclosure_notes_project_gate_contract.py` | （无） | `test_note_gate_ast_facts_on_samples[<样例名>]`（新增，17 例） | 新增：合成样例 → `(permission, eqcr, role)` 三元组与期望逐值相等（样例名见「任务 6.5」小节） | 6.5 |
| `backend/tests/test_schema_drift_detector.py` | （无） | `TestKnownAllowlist::test_level_backfill_record_table_allowlisted_and_unmapped`（新增） | 新增（检查点 5 用户裁定 3，照同类 V154 / V155 两条的双向写法）：表名从级别回填迁移的 V / R 脚本现取（执行器分句、去行注释后，V 恰建一张、R 删同一张）→ 该表在 `KNOWN_ALLOWLIST`，且 `_import_all_models()` 之后不在 ORM metadata；本文件原有 37 例（36 passed + 1 xfailed）的函数体与断言逐字未改，改动前后结论相同（见「任务 7.5」两树对照） | 7.5 |

（待填）

## 变异证明

按需求 12.5、12.14 逐项登记。变异在临时 worktree 中进行；应红断言只依赖确定性用例；收集、导入、语法、夹具错误与超时都不算变红。每项按下列格式：

- 编号与所属需求：
- 被改文件与改动描述：
- 变异前哈希（sha256）：
- 运行命令：
- 变红的测试标识与断言信息：
- 应绿用例保持通过的证据：
- 恢复后哈希（须等于变异前）：
- 恢复后复跑结果：

（待填）

## 性质测试汇总

按需求 12.6：hypothesis 每个测试显式声明 `max_examples=5`，fast-check 显式声明 `numRuns: 5`；每个性质测试带上所属需求的固定样例。

| Property | 所属需求 | 测试标识 | 声明的样例数 | 附带的固定样例 | 结果 |
|---|---|---|---|---|---|
| Property 9 | 7.1、7.5 | `backend/tests/test_eqcr_resolver_property.py::test_property_9_eqcr_resolver_matches_model`（另带 3 个 `@example`：E1 / E2 / E3）；固定样例 `backend/tests/test_eqcr_resolver_property.py::test_property_9_fixed_examples[ex1-auditor-cn-alias]` ~ `[ex10-member-role-eqcr]` | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | 需求 7.5 的 ①~⑩（参数化标识 `ex1-…` ~ `ex10-…`，见「任务 2.7」） | 通过：全文件 23 passed；hypothesis 统计 5 passing / 0 failing / 0 invalid（2026-10-20） |
| Property 1 | 2.2、2.3、2.4 | `backend/tests/test_role_map_and_context.py::test_property_1_fallback_matches_role_map`（另带 7 个 `@example`）；固定样例 `backend/tests/test_role_map_and_context.py::test_property_1_every_role_map_key[<键>]`（`ROLE_MAP` 13 个键）与 `backend/tests/test_role_map_and_context.py::test_property_1_unregistered_fixed_examples[empty]` ~ `[observer-cn]`（5 个） | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | `ROLE_MAP` 每个键（含需求 2.8 的 `signing_partner`）；空串、`Manager`、首尾带空格的 `manager`、`readonly`、`观察员`（参数化标识 `empty` / `Manager` / `spaced-manager` / `readonly` / `observer-cn`）；`@example` 另有 `signing_partner` 与「`项目经理` + 全局 admin + 已删除的 (qc, review) 成员行」。需求 2.8 样例与 N3 见 `test_requirement_2_8_fallbacks_and_effective_role`、`test_requirement_2_8_audit_chain_verification_allowed`、`test_fallback_finds_delegation_on_second_staff_record`（见「任务 2.4」） | 通过：全文件 57 passed；hypothesis 统计 5 passing / 0 failing / 0 invalid（2026-10-20） |
| Property 11 | 9.5 | `backend/tests/test_sod_unchanged.py::test_property_11_sod_conclusion_independent_of_member_row`（显式样例 104 个：样例表每条一个，成员行按 19 种轮换）；固定样例 `backend/tests/test_sod_unchanged.py::test_fixed_table_without_member_row[sod-key-preparer-partner_approver]` ~ `[pre-eqcr-cn_qc]`（104 个，无成员行） | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | 改动前代码实测写入的样例表：互斥矩阵 6 个键（`sod-key-…`）；`eqcr` × 冲突角色双向（单条 `single-…`、批量 `batch-…`、批内预检 `pre-…` 各 6 个，批内预检另有 `pre-eqcr-qc` / `pre-qc-eqcr`）；`独立复核合伙人` + `manager` 同批（`batch-cn_eqcr-with-manager`、`batch-manager-with-cn_eqcr`、`pre-cn_eqcr-manager`，放行）；`eqcr` + `qc` 同批（批内预检两条拒绝，`batch-eqcr-with-qc`、`batch-qc-with-eqcr`、`single-eqcr-after-qc`、`single-qc-after-eqcr` 放行）；需求 9.5 的直接放行角色（见「任务 2.9」） | 通过：全文件 109 passed（worktree 与基线树各一次）；hypothesis 统计 5 passing / 0 failing / 0 invalid（2026-10-20） |
| Property 2 | 3.1、3.2、3.3、3.4、3.5、3.8、3.9 | `backend/tests/test_assignment_sync_property.py::test_property_2_sync_matches_model_and_is_order_independent`（另带 3 个 `@example`：E1 / E2 / E3）；固定样例 `backend/tests/test_assignment_sync_property.py::test_property_2_fixed_examples[F1-edit-to-eqcr]`、`[F2-edit-to-unregistered]`、`[F3-manager-and-eqcr-same-user]` | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | 需求 3.5 的三种情形：edit 改派为 EQCR（F1，`独立复核合伙人`）、edit 改派为未登记角色（F2，`观察员`）、同一用户 manager 与 eqcr 各一条（F3，正序与倒序各一次）；`@example` 另有 E1（只有已删除成员行、已删除与未关联的人员库记录）、E2（同级别固定先后、精确匹配、可升可降）、E3（空批次）（见「任务 4.2」） | 通过：全文件 5 passed；hypothesis 统计 5 passing / 0 failing / 0 invalid（2026-10-20） |
| Property 8 | 8.5 | `backend/tests/test_note_multi_project_gate.py::test_property_8_multi_project_gate_rejects_whole_request`（另带 2 个 `@example`：E1 / E2）；固定样例 `backend/tests/test_note_multi_project_gate.py::test_property_8_fixed_examples[all-pass]`、`[one-403-one-423-is-403]`、`[only-423-is-423]` | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | design §8.3 性质 8 的三个固定样例：全部通过（4 个项目、请求里重复出现，兼作零写入观测的正向对照）；一个 403 + 一个 423 ⇒ 403；只有 423 ⇒ 423（见「任务 6.4」） | 通过：全文件 4 passed；hypothesis 统计 5 passing / 0 failing / 0 invalid（2026-10-20） |
| Property 3 | 4.2、4.3、4.4、4.5、4.11 | `backend/tests/test_level_backfill_migration_pg.py::test_property_3_backfill_matches_row_model`（`pg_only`，另带 2 个 `@example`：E1 / E2）；固定样例 `backend/tests/test_level_backfill_migration_pg.py::test_property_3_fixed_examples[f1-pm-five-aliases]` ~ `[f9-already-at-target-not-recorded]`（9 个） | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | 被需求 4.2 改动的行（五个合伙人 / 经理别名各一、合伙人与经理同持取 partner、已软删项目、全局角色不参与：f1~f3）；被需求 4.3 改动的行（`eqcr` / `独立复核合伙人`、原级别 edit / readonly、与合伙人 / 经理委派同持时 EQCR 优先：f4、f5）；只持质控 / 审计员 / 未登记委派（f6）、大小写与首尾空白变体（f7）、已删除的成员行 / 委派 / 人员库记录与未关联用户（f8）、已等于目标值（f9）；`@example` E1（空数据集）、E2（有现行委派、没有成员行）（见「任务 7.2」） | 通过（真 PG，正向经 `MigrationRunner.run_pending()`）：全文件 10 passed / 0 skipped，SQLite 轮 10 skipped；hypothesis 统计 5 passing / 0 failing / 0 invalid；SQL 灵敏度核对 12 项均红在固定样例（2026-10-21） |
| Property 4 | 4.5、4.7 | `backend/tests/test_level_backfill_migration_pg.py::test_property_4_backfill_is_idempotent`（`pg_only`，另带 2 个 `@example`：E1 / E2）；固定样例 `backend/tests/test_level_backfill_migration_pg.py::test_property_4_fixed_examples[f1-pm-five-aliases]` ~ `[f9-already-at-target-not-recorded]`（9 个）；需求 4.5 另有 `backend/tests/test_level_backfill_migration_pg.py::test_requirement_4_5_existing_records_not_overwritten` | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | 复用 Property 3 的 f1~f9（第一次执行被需求 4.2 改动 19 行、4.3 改动 7 行，在 f1~f5、f8、f9 中；f6、f7 没有改动行）；`@example` E1（空数据集）、E2（有现行委派、没有成员行）；需求 4.5 用例：两次执行之间他途改动 8 行，第一次的 7 条回填记录逐值不变、第二次新增 1 条（见「任务 7.3」） | 通过（真 PG，两次都经 `MigrationRunner.run_pending()`，第二次前删掉临时 `schema_version` 中本版本的登记）：全文件 21 passed / 0 skipped，SQLite 轮 21 skipped；hypothesis 统计 5 passing / 0 failing / 0 invalid；SQL 灵敏度核对 11 项均红在固定样例或需求 4.5 用例的断言上（errors 0）（2026-10-21） |
| Property 5 | 4.6、4.9 | `backend/tests/test_level_backfill_migration_pg.py::test_property_5_backfill_roundtrip`（`pg_only`，另带 2 个 `@example`：E1 正向一次、E2 正向两次，都没有他途改动）；固定样例 `backend/tests/test_level_backfill_migration_pg.py::test_property_5_fixed_examples[f1-pm-five-aliases-once]` ~ `[f9-already-at-target-not-recorded-twice]`（18 个）；需求 4.9 另有 `backend/tests/test_level_backfill_migration_pg.py::test_requirement_4_9_rollback_branches[once]`、`[twice]` | `max_examples=5`（`@settings(max_examples=5, deadline=None)`） | 复用 Property 3 的 f1~f9 × 正向一次 / 两次，没有他途改动，期望全部成员行回到迁移前；需求 4.9 用例：有记录且仍为目标值、被改成非目标值、被改走后又改回目标值、只差一列（两种）、没有记录的行（含已删除行）被他途改动、需求 4.3 的行被改动与未被改动各一（见「任务 7.4」） | 通过（真 PG，正向经 `MigrationRunner.run_pending()`，回滚经 `MigrationRunner.rollback_to(n − 1)`，只把 `_run_backup` 换成记录调用的替身）：全文件 42 passed / 0 skipped，SQLite 轮 42 skipped；hypothesis 统计 5 passing / 0 failing / 0 invalid；R 副本灵敏度核对 12 项均红在固定样例或需求 4.9 用例的断言上（errors 0）（2026-10-21） |

（待填）

## 预存失败登记

按需求 12.9：同一批测试在目标分支最新提交的干净检出上运行，只有以同一测试标识、同类失败（同一异常类型、同一断言位置）复现的才登记为预存；其余都算本 spec 引入。

| 测试标识 | 失败摘要（异常类型 / 断言位置） | 基线提交 | 基线复现结论 |
|---|---|---|---|
| `backend/tests/test_account_package_summary.py` 3 例：`TestAccountPackageAPI::test_list_packages`、`TestRegistryReadingService::test_registry_get_packages_by_cycle`、`TestRegistryReadingService::test_registry_loads_packages` | pydantic_core._pydantic_core.ValidationError: 1 validation error for PackageListItem（1）；AssertionError: assert 7 == 3（1）；KeyError: 'account_package_id'（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_adjustments_convert_to_misstatement.py` 1 例：`test_convert_force_bypasses_idempotency` | AssertionError: {"detail":"ALREADY_CONVERTED"} | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_archive_deprecated.py` 2 例：`test_idempotent_returns_same_job_id`、`test_new_orchestrate_endpoint_reachable` | assert 503 == 200（1）；AssertionError: Expected 200, got 403: {"detail":"X-Confirmation-Token header required"}（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_archived_project_guard.py` 1 例：`test_adjustments_post_returns_423_for_archived` | sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: account_chart | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_c1_entity_control_pbt.py` 1 例：`test_c1_entity_control_pbt` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_checklist_responses.py` 1 例：`test_checklist_responses_crud` | AttributeError: 'NoneType' object has no attribute 'send' | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_consol_push.py` 1 例：`TestEndpoints::test_approve_push_revoke_roundtrip` | IndexError: list index out of range | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_d2_ai_generate.py` 3 例：`test_d2_ai_generate_adj_note`、`test_d2_ai_generate_rejects_unknown_section`、`test_d2_ai_generate_writeoff_analysis` | assert 503 == 200（2）；assert 503 == 400（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_data_lifecycle_router.py` 2 例：`TestImportQueueRouter::test_get_import_queue_lists_processing_job_from_db`、`TestImportQueueRouter::test_get_import_status_reads_completed_job_from_db` | pydantic_core._pydantic_core.ValidationError: 2 validation errors for BasicInfoSchema | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_deliverable_onlyoffice.py` 1 例：`test_property_54_onlyoffice_unavailable_degradation` | assert True is False | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_f2_ai_generate.py` 15 例：`test_f2_ai_generate_accepts_disclosure_sections[listed-note-amort]`、`test_f2_ai_generate_accepts_disclosure_sections[listed-note-borrow]`、`test_f2_ai_generate_accepts_disclosure_sections[listed-note-category]`、`test_f2_ai_generate_accepts_disclosure_sections[listed-note-nrv]`、`test_f2_ai_generate_accepts_disclosure_sections[listed-note-provision]`、`test_f2_ai_generate_accepts_disclosure_sections[listed-note-re]`、`test_f2_ai_generate_accepts_disclosure_sections[soe-note-amort]`、`test_f2_ai_generate_accepts_disclosure_sections[soe-note-borrow]`、`test_f2_ai_generate_accepts_disclosure_sections[soe-note-category]`、`test_f2_ai_generate_accepts_disclosure_sections[soe-note-land]`、`test_f2_ai_generate_accepts_disclosure_sections[soe-note]`、`test_f2_ai_generate_adj_note`、`test_f2_ai_generate_f2_18_note_a`、`test_f2_ai_generate_f2_20_abnormal`、`test_f2_ai_generate_rejects_unknown_section` | AssertionError: `<section>` 被拒绝：{"code":503,"message":"AI 服务未启用"}（11）；assert 503 == 200（3）；assert 503 == 400（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_f2_special_ai.py` 2 例：`test_f2_spe_ai_generate_price_analysis`、`test_f2_spe_ai_rejects_unknown_section` | assert 503 == 200（1）；assert 503 == 400（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_f2_stocktake_ocr_ai.py` 2 例：`test_f2_st_ai_generate_plan`、`test_f2_st_ai_generate_questionnaire_field` | assert 503 == 200 | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g10_trading_financial_liabilities_api.py` 1 例：`test_g10_specs_cover_eight_sheets` | AssertionError: assert {'G10-1', 'G1... 'G10-6', ...} == {'G10-1', 'G1... 'G10-7', ...} | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g11_investment_income_api.py` 1 例：`test_g11_specs_cover_five_sheets` | AssertionError: assert {'G11-1', 'G1..., '附注上市', ...} == {'G11-1', 'G1...1-4', 'G11-5'} | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g12_net_hedge_gains_api.py` 1 例：`test_g12_render_module_constants` | AttributeError: 'SemanticAccountSpec' object has no attribute 'fallback_gross' | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g6_ecl_integration.py` 6 例：`TestAiEndpoints::test_ai_ecl_measurement_conclusion`、`TestAiEndpoints::test_ai_impairment_conclusion`、`TestAiEndpoints::test_ai_invalid_section`、`TestAiEndpoints::test_ai_reversal_writeoff_conclusion`、`TestAiEndpoints::test_ai_stage_conclusion`、`TestAiEndpoints::test_ai_voucher_conclusion` | assert 503 == 200（5）；assert 503 == 400（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g6_other_bond_investment_main_api.py` 1 例：`test_g6_main_ai_sections` | AssertionError: adjudication-analysis | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g6_sppi_import_export_ai.py` 5 例：`test_ai_business_model_conclusion`、`test_ai_fair_value_conclusion`、`test_ai_interest_conclusion`、`test_ai_invalid_section`、`test_ai_sppi_conclusion` | assert 503 == 200（4）；assert 503 == 400（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g7_long_term_equity_main_integration.py` 3 例：`test_g7_main_ai_invalid_section`、`test_g7_main_ai_section[adjudication-analysis]`、`test_g7_main_ai_section[disclosure-text]` | assert 503 == 400（1）；AssertionError: section=adjudication-analysis failed: {"code":503,"message":"AI 服务未启用"}（1）；AssertionError: section=disclosure-text failed: {"code":503,"message":"AI 服务未启用"}（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g7_long_term_equity_method_integration.py` 2 例：`test_ai_invalid_section_returns_400`、`test_ai_unsupported_section_error_message` | assert 503 == 400 | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_g7_sub_integration.py` 6 例：`TestAiEndpoints::test_ai_control_judgment_conclusion_accepts_request`、`TestAiEndpoints::test_ai_disposal_conclusion`、`TestAiEndpoints::test_ai_initial_measurement_conclusion`、`TestAiEndpoints::test_ai_invalid_section_returns_400`、`TestAiEndpoints::test_ai_subsequent_conclusion`、`TestAiEndpoints::test_ai_voucher_conclusion` | assert 503 == 200（5）；assert 503 == 400（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_gin_index.py` 2 例：`TestDegradationPath::test_header_absent_when_not_building`、`TestDegradationPath::test_header_present_when_building` | assert 403 == 200 | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_handover_service.py` 4 例：`test_handover_all_scope`、`test_handover_by_project`、`test_handover_manager_cannot_use_all_scope`、`test_handover_resignation_supersedes_independence` | AssertionError: {"detail":"生效日期不能早于 30 天前"}（3）；assert 400 == 403（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_i2_integration.py` 1 例：`TestRenderStrategy::test_account_prefixes_include_1717` | ImportError: cannot import name '_I2_ACCOUNT_PREFIXES' from 'app.routers.wp_render_strategies._i2_development_ | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息；`TestRenderStrategy::test_account_prefixes_include_1717` 两边信息差异仅在 路径 |
| `backend/tests/test_i6_render_and_export.py` 1 例：`test_i6_render_strategy_fetches_occurrence_amount` | ImportError: cannot import name '_I6_ACCOUNT_PREFIX' from 'app.routers.wp_render_strategies._i6_research_devel | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息；`test_i6_render_strategy_fetches_occurrence_amount` 两边信息差异仅在 路径 |
| `backend/tests/test_l3_long_term_loans_integration.py` 1 例：`TestImportDataAPI::test_valid_xlsx_returns_imported_count` | assert 400 == 200 | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_ledger_penetration.py` 3 例：`TestGetAllLedgerEntriesStablePagination::test_paginated_sums_match_full_aggregate`、`TestLedgerPenetrationAPI::test_aux_entries_api`、`TestLedgerPenetrationAPI::test_entries_api` | assert 0 == 3（1）；KeyError: 'total'（1）；AssertionError: assert 50 == 10（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_n2_taxes_payable_integration.py` 2 例：`TestExportTemplateAPI::test_export_template_single_sheet`、`TestExportTemplateAPI::test_export_template_success` | assert 405 in (200, 404, 401) | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_p0_6_9_contract_and_lock.py` 1 例：`TestPermissionMatrix::test_publisher_can_publish_requires_confirmed_by` | RuntimeError: There is no current event loop in thread 'MainThread'. | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_phase8.py` 5 例：`TestReportEngineCache::test_cache_invalidation`、`TestReportEngineCache::test_cache_key_format`、`TestReportEngineCache::test_cache_miss_returns_none`、`TestReportEngineCache::test_cache_set_and_get`、`TestReportEngineCache::test_no_redis_graceful_degradation` | assert 0 == 1（1）；TypeError: ReportEngine._cache_key() missing 1 required positional argument: 'report_type'（1）；TypeError: ReportEngine._get_cached_report() missing 1 required positional argument: 'report_type'（2）；TypeError: ReportEngine._set_cached_report() missing 1 required positional argument: 'data'（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_pm_workflow_e2e.py` 1 例：`test_pm_full_workflow` | assert 404 in (200, 400) | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_property_archived_invariant.py` 1 例：`TestArchivedProjectMutationInvariant::test_archived_project_mutation_returns_423` | ExceptionGroup: Hypothesis found 2 distinct failures. (2 sub-exceptions) | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_workhour_list.py` 2 例：`TestWorkhourList::test_admin_sees_all`、`TestWorkhourList::test_manager_sees_only_managed_projects` | assert 0 >= 3（1）；AssertionError: assert 'a5ba82a4-fe5d-4201-8ac9-94435044e3f9' in set()（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息；`TestWorkhourList::test_manager_sees_only_managed_projects` 两边信息差异仅在 随机 id |
| `backend/tests/test_wp_index_resolve.py` 5 例：`test_loose_mode_sheet_ref`、`TestParseRef::test_loose_mode_case_normalization`、`TestParseRef::test_loose_mode_sheet_ref_dash`、`TestParseRef::test_loose_mode_sheet_ref_letter_suffix`、`TestParseRef::test_multi_level_sheet_ref` | AssertionError: assert 'wp' == 'sheet'（1）；AssertionError: assert ('wp', 3, 'D2-1') == ('sheet', 2, 'D2-1')（2）；AssertionError: assert ('wp', 3, 'D2A') == ('sheet', 2, 'D2A')（1）；AssertionError: assert ('wp', 3, 'D2-1-1') == ('sheet', 2, 'D2-1-1')（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_wp_onlyoffice_router.py` 4 例：`TestOnlyOfficeConfigEndpoint::test_config_contains_action_link_with_sheet_name`、`TestOnlyOfficeConfigEndpoint::test_edit_mode_acquires_seat_returns_429_when_full`、`TestOnlyOfficeConfigEndpoint::test_edit_mode_acquires_seat_success`、`TestOnlyOfficeConfigEndpoint::test_view_mode_does_not_acquire_seat` | assert 404 == 200（3）；assert 404 == 429（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/test_wp_template_files_lazy_load.py` 6 例：`test_get_sheet_by_name_404_when_sheet_not_exists`、`test_get_sheet_by_name_returns_full_data`、`test_xlsx_to_json_active_payload_smaller_than_full`、`test_xlsx_to_json_default_returns_full_for_all_sheets`、`test_xlsx_to_json_lazy_active_only_returns_active_full`、`test_xlsx_to_json_unknown_sheets_param_falls_back_to_full` | AssertionError: assert 'sheet 不存在' in '资源不存在或不可访问'（1）；AssertionError: {"code":404,"message":"资源不存在或不可访问"}（2）；assert 404 == 200（3） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/workpaper_sync/test_aos_adopt_endpoint_injection_and_atomicity.py` 3 例：`TestMultiItemPartialWriteIsRolledBack::test_all_five_items_were_seeded`、`TestMultiItemPartialWriteIsRolledBack::test_mid_deletion_injection_rolls_back_every_item`、`TestMultiItemPartialWriteIsRolledBack::test_positive_control_pruned_every_item` | AssertionError: ['F3-1-adj-seed-rows', 'F3-1-adj-slot-rows', 'F3-2-rows', 'F3-4-rows', 'F3-5-rows', 'F3-6-rows（1）；AssertionError: F3-1-adj-seed-rows（1）；AssertionError: {'changed_item_count': 9, 'changed_items': ['F3-1-adj-seed-rows', 'F3-1-adj-slot-rows', 'F3-2-（1） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/workpaper_sync/test_task21_room_service.py` 1 例：`TestDocKeyIsMtimeFree::test_rg17_is_clear_on_the_real_manifest` | AssertionError: RG-17 仍有 19 条红：['xlsx/gt-a101-governance-communication: entry xlsx/gt-a101-governance-communic | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |
| `backend/tests/workpaper_sync/test_task28_sync_router_pg.py` 6 例：`TestHarnessIntegrity::test_every_scenario_was_collected`、`TestHarnessIntegrity::test_no_phase_crashed_during_collection`、`TestServiceScopeCallbackRoute::test_a_pre_durable_rejection_returns_a_non_zero_ack`、`TestServiceScopeCallbackRoute::test_a_rejected_callback_creates_no_delivery_row`、`TestServiceScopeCallbackRoute::test_the_response_envelope_is_not_wrapped`、`TestServiceScopeCallbackRoute::test_the_route_is_mounted_and_not_a_user_404` | AssertionError: assert {'claim_room_..._oracle', ...} == {'claim_room_..._oracle', ...}（1）；AssertionError: {'service_callback_route': 'SyncDomainError: 缺少 ONLYOFFICE_JWT_SECRET —— 未签名的 Command Service （1）；KeyError: 'service_callback_route'（4） | B `a02a21419` | 任务 3.4 批次（218 / 220 个文件），基线树同批运行：同一标识、同一异常与断言信息（逐字相同） |

（待填）

## 真库迁移验收

（待填：需求 12.7 的真 PG 迁移往返测试结果；任务 19.10 的本地库迁移验收（需求 4.8）。）

需求 12.7 的真 PG 正向 / 回滚 / 对账测试见「任务 7.2」~「任务 7.5」小节，都在 `backend/tests/test_level_backfill_migration_pg.py`（全部 `pg_only`，正向经 `MigrationRunner.run_pending()`，回滚经 `rollback_to(n − 1)` 或其执行 R 脚本所用的 `_execute_rollback_script`）：正向逐行对账 `test_property_3_backfill_matches_row_model` 与 `test_property_3_fixed_examples[f1~f9]`（7.2）；幂等 `test_property_4_backfill_is_idempotent`、`test_property_4_fixed_examples[f1~f9]` 与 `test_requirement_4_5_existing_records_not_overwritten`（7.3）；往返 `test_property_5_backfill_roundtrip`、`test_property_5_fixed_examples[f1~f9 × once / twice]` 与 `test_requirement_4_9_rollback_branches[once]`、`[twice]`（7.4）；执行语义 `test_requirement_4_1_rollback_twice`、`test_requirement_4_1_rollback_without_backfill_records`、`test_requirement_4_1_rollback_when_forward_never_ran`、`test_requirement_4_10_forward_failure_is_not_registered`、`test_requirement_4_10_rollback_failure_keeps_version_applied` 与角色映射对账 `test_requirement_12_7_backfill_matches_role_map[<7 个别名>]`（7.5）。2026-10-21 11:55:45 收尾 PG 轮 54 passed、0 skipped，SQLite 轮 54 skipped（见「任务 7.5」）。本地开发库只执行正向、不执行回滚的真库验收在任务 19.10。

## 浏览器实测与清理对账

（待填：需求 12.10 五种身份的页面快照、请求与响应摘要；按写过的表逐项恢复到实测前状态并核对行数；只追加的留痕登记。）

## 后续 spec 登记

（待填：任务 20.2，R1 / R2 / R3。）

## 闭合检查

（待填：需求 12.14 的闭合检查结果——判据引用闭合、变异证明汇总、性质测试汇总、现算计数对账。）


## 任务 10.1：disclosure_notes.py A1~A12 端点改走附注编辑门禁

### disclosure_notes.py 改动摘要

- **A1 generate_notes**：`_assert_project_edit(project_id=data.project_id, ...)` → `assert_note_edit_access(db, current_user, data.project_id, consol_lock=True)`（函数体形态，请求体 project_id）
- **A2 update_note**：内联 `db.execute(select(project_id))` + `_assert_project_edit` → `assert_note_edit_access_for_object(db, current_user, id_column=DisclosureNote.id, project_column=DisclosureNote.project_id, object_id=note_id, not_found_detail="附注章节不存在", consol_lock=True)`（对象反查形态）
- **A3~A5 delete/patch/restore_section**：`_assert_project_edit(project_id=project_id, ...)` → `assert_note_edit_access(db, current_user, project_id, consol_lock=True)`（函数体形态，路径 project_id）
- **A6 pull_from_workpapers**：`require_project_access("edit")` → `require_note_edit_access(consol_lock=False)`（路径依赖形态）
- **A7 validate_notes**：同 A6
- **A8 confirm_finding**：`_assert_validation_project_access(db, current_user, validation_id, "edit")` → `assert_note_edit_access_for_object(..., id_column=NoteValidationResult.id, ..., not_found_detail="校验结果不存在", consol_lock=False)`
- **A9~A12 clear/restore_auto/apply/upsert_formulas**：`require_project_access("edit")` + `Depends(check_consol_lock)` → `require_note_edit_access(consol_lock=True)`（路径依赖形态，单个依赖替换两个）
- **删除**：`_assert_project_edit` 辅助函数、`_assert_validation_project_access` 辅助函数
- **删除导入**：`require_operation`、`check_consol_lock`
- **export_word docstring**：按需求 2.6 改写，不再称合伙人 / 经理为 review 级
- **行数**：1860 → 1805（限 1899）

### 既有测试改写对照

#### test_disclosure_notes_hardening.py（52 passed）

| 旧 | 新 | 说明 |
|---|---|---|
| `patch("app.routers.disclosure_notes._assert_project_edit", ...)` | `patch("app.routers.disclosure_notes.assert_note_edit_access", ...)` | A1/A3~A5 端点的门禁 mock 目标；update_note 改用 `assert_note_edit_access_for_object` |
| `test_p2_unified_edit_gate_orders_project_then_operation_then_lock` | `test_p2_note_edit_gate_orders_archived_member_eqcr_matrix_lock` | 改为验证 note_edit_gate 内部判定顺序（替身装在各步下一层取数点上） |
| `test_assert_project_edit_completes_before_any_db_write` | `test_note_edit_gate_completes_before_any_db_write` | 合并锁失败时零 flush/commit，mock 目标改为 `assert_note_edit_access` |
| `test_update_resolves_project_id_before_gate`（class 版） | `test_update_uses_object_reverse_lookup_gate` | 对象反查形态的门禁包含投影查询 |
| `test_delete_uses_path_project_id_for_gate` | 保留名称，mock 签名改为 `(db, user, project_id, *, consol_lock)` | 捕获 project_id 方式适配 |
| `test_readonly_user_cannot_execute_any_mutation` | 同时 patch `assert_note_edit_access` 与 `assert_note_edit_access_for_object` | update_note 走 for_object 形态 |
| 所有注释 / docstring 中的 `_assert_project_edit` | 改为 `assert_note_edit_access` 或 `附注编辑门禁` | 不再引用已删除的函数 |

#### test_disclosure_notes_project_gate_contract.py（41 passed）

| 旧 | 新 | 说明 |
|---|---|---|
| `BODY_GATES` 含 `_assert_project_edit`、`_assert_validation_project_access` | 改为 `assert_note_edit_access`、`assert_note_edit_access_for_object` | 新门禁名 |
| `DEPENDS_GATES` | 新增 `require_note_edit_access` | 路径依赖形态 |
| `CASES`：generate→`_assert_project_edit`、update→`_assert_project_edit`、confirm→`_assert_validation_project_access` | generate→`assert_note_edit_access`、update→`assert_note_edit_access_for_object`、confirm→`assert_note_edit_access_for_object` | 适配新门禁 |
| `test_helper_resolves_project_before_permission_check` | 扩展：同时验证 `assert_note_edit_access_for_object` 的 select → gate 顺序 | 四项判据强度不降 |

#### test_project_access_level_registry.py（7 passed）

| 旧 | 新 | 说明 |
|---|---|---|
| `UNIFIED_GATES = {"_assert_project_edit"}` | `NOTE_EDIT_GATES = {"assert_note_edit_access", "assert_note_edit_access_for_object", "require_note_edit_access"}` | 三种挂载形态 |
| `test_unified_note_gate_requires_edit`（检查 `_assert_project_edit` 含 `require_project_access("edit")` + `require_operation` + `check_consol_lock`） | `test_unified_note_gate_requires_review_eqcr_matrix_lock`（检查 `NOTE_EDIT_MIN_LEVEL=="review"` + `assert_project_permission` + `is_project_eqcr` + `NOTE_EDIT_OPERATION=="note:edit"` + `consol_lock`） | 需求 6.10 可伪证断言 |
| `wp_editor_router.update_sign_status` 仍须 edit | 不变 | 非附注端点保持 edit |

### 清册重生成

- 附注写端点清册：A1~A12 全部 `current_equals_target: True`，category=E，level=review
- edit 级影响清单：603 处门禁调用点 / 146 个文件
- 两份清单 `--check` 模式均以 0 退出
- disclosure_notes.py 行数：1805（限 1899）


### Task 10.3：note_offline / note_text_batch / note_content_templates / note_advanced 门禁改造

#### 路由改动

11 个写端点（A13~A23）已在先前任务中完成改造为 `require_note_edit_access`：

| 端点 | 改动前 | 改动后 | consol_lock |
|------|--------|--------|:-----------:|
| A13 `note_offline::execute_import` | `require_project_access("edit")` | `require_note_edit_access(consol_lock=False)` | False |
| A14 `note_text_batch::parse_upload` | edit + `note:edit` + 合并锁 | `require_note_edit_access(consol_lock=True)` | True |
| A15 `note_text_batch::parse_knowledge` | 同上 | `require_note_edit_access(consol_lock=True)` | True |
| A16 `note_text_batch::preview_text_batch` | 同上 | `require_note_edit_access(consol_lock=True)` | True |
| A17 `note_text_batch::apply_text_batch` | 同上 | `require_note_edit_access(consol_lock=True)` | True |
| A18 `note_content_templates::snapshot_preview_endpoint` | `require_project_access("edit")` | `require_note_edit_access(consol_lock=False)` | False |
| A19 `note_content_templates::save_template_endpoint` | `require_project_access("edit")` | `require_note_edit_access(consol_lock=False)` | False |
| A20 `note_content_templates::delete_template_endpoint` | `require_project_access("edit")` | `require_note_edit_access(consol_lock=False)` | False |
| A21 `note_advanced::import_prior_year_notes` | `require_project_access("edit")` | `require_note_edit_access(consol_lock=False)` | False |
| A22 `note_advanced::inherit_prior_year_notes` | `require_project_access("edit")` | `require_note_edit_access(consol_lock=False)` | False |
| A23 `note_advanced::update_cross_references` | `require_project_access("edit")` | `require_note_edit_access(consol_lock=False)` | False |

- 已删除：`require_operation("note:edit")`、`check_consol_lock` 依赖（A14~A17）；`require_project_access("edit")` 依赖（其余）。
- 保留：各文件的 `require_project_access("readonly")` 仅用于 GET 端点。
- 幂等键核对：A17 `apply_text_batch` 的 `mutation_id` / `DisclosureMutationCoordinator` 逻辑位于 `require_note_edit_access` 路径依赖之后的函数体内，符合「幂等记录读写位于门禁之后」。

#### 既有测试改写对照

| 文件 | 旧 | 新 | 说明 |
|------|----|----|------|
| `test_note_text_batch_endpoints.py` | `_TABLES` 不含 `ProjectAssignment.__table__` | 新增 `from app.models.staff_models import ProjectAssignment, StaffMember`（StaffMember 已有）；`_TABLES` 增加 `ProjectAssignment.__table__` | 附注编辑门禁内部的 EQCR 判定（`is_project_eqcr`）查询 `project_assignments`，缺此表导致 SQLite 报 `no such table`。46 passed |
| `test_note_prior_year_import_stamp.py` | `tables` 列表不含 `StaffMember.__table__` 和 `ProjectAssignment.__table__` | 新增 `from app.models.staff_models import ProjectAssignment, StaffMember`；`create_all` 增加两张表 | 同上理由。6 passed |
| `test_note_content_template_endpoints.py` | 已含 `StaffMember.__table__` 和 `ProjectAssignment.__table__` | 无改动 | 13 passed，无需修改 |

断言强度不降：三个文件中 readonly / outsider 拒绝断言保持 403、业务断言保持逐值比较。

#### 配方表

`note_edit_gate_recipes.py` 新增 11 条配方（`_A13`~`_A23`），`ALL_RECIPES` 由 12→23 条。

#### 清册重生成

- 附注写端点清册：11 个端点全部 `current_equals_target: True`，category=E
- edit 级影响清单：603 处门禁调用点 / 146 个文件
- 两份清单 `--check` 模式均以 0 退出
