# Implementation Plan: 合伙人与经理的编辑权限（partner-manager-edit-permission）

## Overview

落地两条用户指令：附注编辑器写端点改走统一的附注编辑门禁（本项目 review 及以上成员可写，EQCR 只读，操作矩阵照常判定，原判合并锁的端点继续判）；`ROLE_MAP` 把合伙人（含签字合伙人）与经理升为 edit 级，全平台生效。需求 Q1–Q7 与细化口径一律按默认；design 裁定 D1–D13 全部采纳（含 D3 移除权限缓存、§4.8 表 B 两处更严的角色限定、D4 委派同步跳过已删除人员库记录）。风险 R1 / R2 / R3 本 spec 不修，收尾时登记另立 spec（任务 20.2）。

顺序：实施环境 → 后端底座（角色映射、EQCR 判定、测试夹具、移除权限缓存、委派同步、附注编辑门禁、级别回填迁移、两份清单与守卫）→ 端点改造（表 A、表 B、交付中心、判定查询、连续审计）→ 跨门禁性质测试与守卫收口 → 前端 → 验收 → 收尾提交。每个任务完成即跑相关测试，保持可构建、可测试；所有任务均为必做。

### 执行约定（全部任务适用）

- 只在实施 worktree（任务 1.1）内改动与运行；命令用 cwd 参数，不 `Set-Location`；Python 用 `D:\GT_plan\.venv\Scripts\python.exe` 绝对路径；shell 命令按 rtk 规则加前缀。不触碰主工作树的文件与暂存区（例外：本 spec 目录 `tasks.md` 的勾选，见 20.4）；不在共享终端设置 git 环境变量；不用 `--no-verify`。
- 计数一律现算。需求 / 设计中的数字只作对账参照，差异记入 `acceptance.md`，不写进判据。
- 性质测试：hypothesis 每个测试显式 `@settings(max_examples=5)`，fast-check 显式 `{ numRuns: 5 }`；所属需求列出的固定样例以 `@example` 或显式用例带上，应红断言只依赖固定样例；模型独立计算，不调用被测生产判定函数（性质 1、2 以 `ROLE_MAP` 对拍，属需求 12.6 明文例外）；运行中发现的反例先固化为固定样例再修实现；测试函数头注释 `# Feature: partner-manager-edit-permission, Property N: <标题>`。
- 端点级测试按 design §8.2「权限世界」：只替换当前用户、RLS 设置、归档守卫（仅不观测归档的用例）、委派查询（仅不观测 EQCR 的用例）与业务 service（打桩计数）；不以 `dependency_overrides` / monkeypatch 替换 `require_project_access`、`assert_project_permission`、附注编辑门禁各形态、`is_project_eqcr`、`_guard_action`；故障注入只注在下一层；每个端点级测试文件至少一条放行用例（业务桩恰 1 次且响应成功）。
- 改写既有测试：断言强度不降、逐值比较、不新增 `skip` / `xfail`，逐函数新旧对照记入 `acceptance.md`（需求 12.8）。
- 改动生产文件后核对 design §10 行数门。任务 8 的清单脚本落地后，凡改动附注路由、门禁或前端写调用，都重生成两份清单并跑检查模式守卫。
- 任务 19.10 之前不得以实施 worktree 的代码启动后端（启动流程会把回填迁移落到本地库）。

## Tasks

- [ ] 1. 实施环境准备
  - [ ] 1.1 建实施分支与 worktree
    - `git fetch --prune origin`，取 `origin/spec/disclosure-note-doc-upload-and-batch-fill` 尖端为基线提交 B。
    - 从 B 新建临时分支（如 `pm-edit-permission`）与 worktree，目录不用 `D:\_gt_*` 前缀（如 `D:\wt_pm_impl`），建好即 `git worktree lock --reason "partner-manager-edit-permission 实施"`。
    - 运行环境：核对 worktree 内 `import app` 解析到 worktree 的 `backend/app`（打印 `app.__file__`，防 venv 把导入指回主工作树）；前端在 worktree 内按 lockfile `npm ci`，不链接主工作树的 `node_modules`；需要 `.env` 时从主工作树复制到 worktree 本地使用（已被 gitignore，不提交、不回显其中的值）。
    - _Requirements: 12.9_
  - [ ] 1.2 验收记录骨架、spec 文件入树与迁移号
    - 把主工作树本 spec 目录的 `requirements.md`、`design.md`、`tasks.md`、`.config.kiro` 逐字节复制进 worktree 同路径；requirements / design 不做任何修改。
    - 在 worktree 新建 `.kiro/specs/partner-manager-edit-permission/acceptance.md`，分节：基线信息、迁移号、现算计数对账、既有测试改写对照、变异证明、性质测试汇总、预存失败登记、真库迁移验收、浏览器实测与清理对账、后续 spec 登记、闭合检查。
    - 按需求 4.1 现扫「主工作树磁盘（含未跟踪）∪ B」的最高 `V*.sql` 版本号，+1 得 n（写作时 198），连同 B 的 SHA 记入 `acceptance.md`。
    - _Requirements: 4.1, 12.14_
  - [ ] 1.3 准备改动前的基线树
    - 把只读参考 worktree `D:\wt_pm_ref` 切到 B（detached，须干净）作为「改动前的树」，全程只读；不干净或无法切换时另建 `D:\wt_pm_base` 于 B 并 lock。
    - 用途：6.6 合并锁适用集合、8.4 / 9.7 两树对比、9.5 职责分离期望实测、12.8 / 12.13 改写对照与扫描清单、12.9 预存失败归因。路径与 HEAD 记入 `acceptance.md`。
    - _Requirements: 6.6, 8.4, 9.5, 9.7, 12.8, 12.13_

- [ ] 2. 角色映射单一真源与 EQCR 判定底座
  - [ ] 2.1 `ROLE_MAP` 升级与推导常量（`backend/app/services/assignment_service.py`）
    - 按 design §4.1：`signing_partner` / `partner` / `合伙人` → (partner, edit)，`manager` / `项目经理` → (manager, edit)，其余键原值不变；查表精确匹配（`dict.get`，不 strip / lower）。
    - 紧随 `ROLE_MAP` 新增 `UNMAPPED_ROLE`、`EQCR_ROLE_ALIASES`、`PARTNER_MANAGER_ROLE_ALIASES`（均由 `ROLE_MAP` 推导，不写别名字面量副本）、`_ROLE_TIEBREAK`、`_LEVEL_RANK`、`map_assignment_role`、`resolve_member_mapping`。
    - 单元测试（新增 `backend/tests/test_role_map_and_context.py`）：`resolve_member_mapping` 的 EQCR 优先、取最高级别、项目角色按固定先后、与顺序无关、空输入抛 `ValueError`；`_ROLE_TIEBREAK` 的集合等于 `ROLE_MAP` 取值与 `UNMAPPED_ROLE` 中项目角色的集合。
    - _Requirements: 2.1, 2.2, 3.3, 3.8, 7.2_
  - [ ] 2.2 改写两处前提测试
    - `test_phase8_endpoint_role_levels.py::test_premise_reviewer_roles_are_review_level`、`test_deliverable_generation_membership_auth.py::test_premise_reviewers_are_review_level`：按需求 2.5 期望表（四个别名集合的全部键，含中文别名；另加 `ROLE_MAP` 中现有、取值为 (readonly, readonly) 的键）逐键断言项目角色与级别，键集合与取值和期望表完全相等；断言取值为 (partner, review) 的键集合等于 EQCR 别名集合。可按新口径改名，新旧名对照记入 `acceptance.md`。
    - 两文件的模块 docstring 与断言失败信息按需求 2.6 改写，不再称合伙人 / 经理为 review 级。
    - _Requirements: 2.5, 2.6, 12.8_
  - [ ] 2.3 角色上下文服务改用角色映射（`backend/app/services/role_context_service.py`）
    - 删除 `_ASSIGNMENT_ROLE_MAP`；单项目角色查询与全局上下文的委派兜底，改为按用户全部未删除人员库记录 JOIN 现行委派（修 N3）→ `resolve_member_mapping` → 以 `.value` 字符串返回；`scope_cycles` 按 design §4.2。
    - _Requirements: 2.3, 2.4, 2.8_
  - [ ] 2.4 角色上下文兜底的性质测试
    - **Property 1: 角色上下文兜底与角色映射对拍**
    - **Validates: Requirements 2.2, 2.3, 2.4**
    - 写在 `backend/tests/test_role_map_and_context.py`：`ROLE_MAP` 每个键逐个断言；固定样例空串、`Manager`、首尾带空格的 `manager`、`readonly`、`观察员`；hypothesis 另生成长度 0~30 的任意字符串。
    - 需求 2.8 样例：全局 auditor、只参与一个项目、没有成员行、只有一条 `signing_partner` 现行委派 → 两处兜底 (partner, edit)、全局最高角色 partner、审计日志哈希链校验放行。
    - 多人员库记录用例：经用户第二条人员库记录持有的委派同样被兜底识别（N3）。
    - _Requirements: 2.3, 2.4, 2.8_
  - [ ] 2.5 委派角色映射单一来源扫描测试
    - 新增 `backend/tests/test_role_map_single_source.py`：后端生产代码（AST）与前端源码（`typescript` 解析），均不含测试文件；以四个别名集合中 2 个及以上委派角色为键、取值给出项目级别的映射只有 `ROLE_MAP` 一份，委派通知与页面显示名映射不计；失败信息含「映射不唯一」并列出位置。现算份数（写作时 2，改后 1）记入 `acceptance.md`。
    - _Requirements: 2.7_
  - [ ] 2.6 单一 EQCR 判定（新增 `backend/app/services/eqcr_resolver.py`）
    - 按 design §4.5 实现 `is_project_eqcr`（全局角色 eqcr ∨ 本项目 EQCR 别名现行委派；不经任何缓存；不 `try/except`）、下层取数点 `_count_project_eqcr_assignments`、`project_eqcr_user_ids`；两者共用一个私有条件构造函数，别名取 `EQCR_ROLE_ALIASES`，不 JOIN projects / users / project_users。
    - _Requirements: 7.1, 7.2, 7.6, 11.1_
  - [ ] 2.7 EQCR 判定的性质测试
    - **Property 9: EQCR 判定等于模型**
    - **Validates: Requirements 7.1, 7.5**
    - 写在 `backend/tests/test_eqcr_resolver_property.py`：维度按需求 7.5（全局角色 7 个取值；1~2 条人员库记录持有 0~4 条委派；项目取 P 或另一项目；委派与记录各自删 / 未删；别名、变体与任意串；遵守 F4；干扰数据）；模型的别名集合取需求 2.5 期望表中取值为 (partner, review) 的键，不读生产代码；固定样例 ①~⑩。
    - 同文件补 `project_eqcr_user_ids` 与 `is_project_eqcr` 同口径的用例。
    - _Requirements: 7.1, 7.5, 11.1_
  - [ ] 2.8 EQCR 别名单一来源扫描测试
    - 新增 `backend/tests/test_eqcr_alias_single_source.py`（AST，注释与 docstring 不计）：后端生产代码中以 EQCR 别名集合全部成员为元素或键的字面量集合 / 列表 / 元组 / 映射只有 `ROLE_MAP` 一处；`独立复核合伙人` 作为委派角色取值（集合元素、映射键、比较操作数）只出现在 `ROLE_MAP`，显示名映射的取值与用户可见文案不计；失败信息含「别名集合来源不唯一」。
    - _Requirements: 7.2_
  - [ ] 2.9 职责分离与兼任校验不变量
    - 在基线树（1.3）上用一次性探针（放仓库外，用完即删）实测 `SoDGuardService.check`、`EqcrIndependenceRule` 单条与批量模式、`validate_eqcr_sod_in_batch` 的固定样例期望：互斥矩阵每个键；`eqcr` 与每个冲突角色双向组合；`独立复核合伙人` 与 `manager` 同批（兼任校验放行）；`eqcr` 与 `qc` 同批（批内预检拒绝，单条与批量放行）。期望写入新增的 `backend/tests/test_sod_unchanged.py`，探针输出摘要记入 `acceptance.md`。
    - **Property 11: 职责分离判定与成员行无关**
    - **Validates: Requirements 9.5**
    - 任意成员行级别与项目角色（含无成员行）下结论不变且等于样例表；断言互斥矩阵、`CONFLICT_ROLES` 与批内预检冲突角色集合的内容不变。
    - _Requirements: 9.5_

- [ ] 3. 端点级测试夹具与权限缓存移除
  - [ ] 3.1 权限世界夹具 `backend/tests/authz_world.py`
    - 按 design §8.2：SQLite 内存库建 `users`、`projects`（含 `status`、`consol_lock`、`is_deleted`）、`project_users`、`staff_members`、`project_assignments`、`disclosure_notes`；提供 PG 同构版本供 `pg_only` 用例（参照 `test_v197_route_migration_pg.py`：同一事务内建临时 schema，`SET LOCAL search_path` 只含该 schema，结束回滚，不留对象）。
    - 身份工厂：`member(level, role)`、`eqcr_assignment(alias)`、`non_member_with_other_project()`，需求 12.2 五种标准身份与 12.4 三种补充情形各一个函数。
    - 可替换点与禁止项按执行约定；提供自检断言「请求经过的门禁 is 生产对象」。
    - 夹具自测：五种身份经真实 `assert_project_permission` 按所测级别得出预期结论，至少一条放行用例。
    - _Requirements: 12.1_
  - [ ] 3.2 借缓存注入级别的 4 个测试文件改用真成员行
    - `test_phase8_endpoint_role_levels.py`（Phase 8 六个端点 × 身份，需求 9.4：合伙人 / 经理 / 审计员别名 (edit) 与质控 / EQCR 别名 (review) 放行，未登记角色 (readonly) 与非成员 403「权限不足」）、`test_deliverable_generation_membership_auth.py`（EQCR 由真实 `eqcr` 委派给出）、`ledger_import/test_sign_convention_api.py`、`test_wp_disclosure_sync.py`：去掉 `_get_cached_permission` 替身，身份改由权限世界成员行（取 `ROLE_MAP` 值）给出；原「readonly 被 edit 门禁拒绝」断言保留。
    - 缓存读路径现状恒未命中（N1），改写后在当前代码上即应全绿；逐函数改写对照记入 `acceptance.md`。
    - _Requirements: 9.4, 12.1, 12.8_
  - [ ] 3.3 删除缓存前实测读路径
    - 在 `deps.py` 仍为改动前代码时，把 `test_phase8.py::TestPermissionCache::test_set_and_get_cache` 临时收紧为「取回值 == "edit"」运行一次：预期红在取回值断言（与 N1 互证）；不属实则如实记录实测结论。命令、输出摘要与结论记入 `acceptance.md`；收紧版本不提交，运行后恢复原文件并核对哈希一致。
    - _Requirements: 5.7, 12.8_
  - [ ] 3.4 移除权限缓存（`backend/app/deps.py`、`backend/app/services/custom_query/ownership_guard.py`）
    - 删除 `_get_cached_permission`、`_set_cached_permission`、`invalidate_permission_cache`、`PERM_CACHE_TTL`；新增 `_load_member_level`（只取 `permission_level` 一列）；`assert_project_permission`、`authorize_wp_edit`、`authorize_wp_read` 改用它，免查名单、`WORKPAPER_WRITE` 能力判定与拒绝文案原样；`require_project_access`、`require_wp_edit_permission` 的 docstring 删去缓存描述；`OwnershipGuard._can_access_project` 删除缓存快路径与对 `_get_cached_permission` 的导入。
    - 同步既有测试（design §8.6）：11 个只放「缓存未命中」空替身的文件只删替身行；`test_phase8.py::TestPermissionCache` 三例删除（接替测试见 3.5）；`test_phase4_endpoints.py` ≤ 1177 行；全仓（含测试）检索三个函数名与常量无残留引用。
    - 行数门：`deps.py` ≤ 800。
    - _Requirements: 5.1, 5.2, 5.7, 12.8_
  - [ ] 3.5 缓存移除守卫与 Redis 不可用用例
    - 新增 `backend/tests/test_permission_cache_removed.py`（AST）：`deps` 与 `ownership_guard` 不定义、不引用三个缓存函数与 `PERM_CACHE_TTL`；`_load_member_level`、`assert_project_permission`、`authorize_wp_edit`、`authorize_wp_read` 函数体不引用 Redis 客户端。
    - 需求 5.3：替身 Redis 抛连接错误、阻塞 5 秒两种情形下，级别判定结论与正常时相同、不返回 5xx、判定耗时不受影响。
    - _Requirements: 5.3, 5.7_

- [ ] 4. 委派同步按映射精确写入
  - [ ] 4.1 改写 `AssignmentService._sync_project_users`
    - 按 design §4.3：已删除或未关联用户的人员库记录跳过（D4、需求 3.9）；同一用户的多条委派合并后经 `resolve_member_mapping` 得到一组取值；没有未删除成员行则新建，有则改写项目角色与级别（可升可降），循环范围、科目范围、有效期不动；批次外与其他项目的成员行不查不改；返回 `MemberChange` 列表（只用于 info 日志与测试）；不读写任何 `perm:*` 键；`save_assignments` 仍只 flush。
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.8, 3.9_
  - [ ] 4.2 委派同步的性质测试
    - **Property 2: 委派同步按映射精确写入，且与委派顺序无关**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 3.9**
    - 写在 `backend/tests/test_assignment_sync_property.py`：生成器按需求 3.5 与 design §8.3（含人员库记录已删除视同未关联、打乱委派顺序）；固定样例：edit 改派为 EQCR、edit 改派为未登记角色、同一用户 manager 与 eqcr 各一条。
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 3.9_
  - [ ] 4.3 委派保存的失败语义与真 PG 用例
    - 新增 `backend/tests/test_assignment_save_semantics.py`。需求 3.7：兼任校验拒绝、写库报错、提交报错三种注入 → 失败响应，委派与全部成员行保持保存前的值，替身 Redis 记录到的 `perm:*` 读写删为 0（D12）。
    - 需求 3.1（`pg_only`，权限世界 PG 版）：用户只有已删除成员行时新建成功，已删除行保持删除状态与原值。
    - _Requirements: 3.1, 3.6, 3.7, 9.5_

- [ ] 5. 检查点：后端底座
  - 跑任务 2~4 新增与改写的测试，以及引用 `assignment_service`、`role_context_service`、`deps`、`ownership_guard` 的既有测试（按 import 现算）；同一批测试在基线树上对照，确认没有新增失败。有疑问先问用户。

- [ ] 6. 附注编辑门禁模块
  - [ ] 6.1 新增 `backend/app/services/note_edit_gate.py`：判定实现与三种挂载形态
    - 按 design §4.6：模块常量（D13）；`assert_note_edit_access(db, current_user, project_id, *, consol_lock)` 依次执行 `assert_project_permission(..., NOTE_EDIT_MIN_LEVEL)` → `is_project_eqcr` → 操作矩阵并集判 `note:edit` → 仅 `consol_lock=True` 时 `check_consol_lock`；`require_note_edit_access(*, consol_lock)` 路径依赖；`assert_note_edit_access_for_object(...)` 先一列最小投影、不存在返回 404、再判定，不读调用方另附的项目标识；`note_edit_rejection_reason`；`_resolve_project_role`。
    - `consol_lock` 为必填关键字参数；各形态对判定实现的调用位于函数体顶层语句序列（不在 if / try / 循环内）。
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.12_
  - [ ] 6.2 门禁函数级单元测试
    - 新增 `backend/tests/test_note_edit_gate_unit.py`，用权限世界直接调用三种形态：判定顺序（归档 → 成员 → EQCR → 矩阵 → 合并锁，前一步拒绝即不再往下判）；admin 跳过成员与矩阵但不豁免 EQCR；`consol_lock=False` 不判合并锁；对象反查不存在返回 404，门禁之前只有一次投影读；另附项目标识不改变目标项目；拒绝文案逐字（「权限不足」、EQCR 只读、操作矩阵不放行，以及沿用的归档与合并锁文案）；EQCR 判定下层查询抛错时异常冒泡、不放行。
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.11, 6.12, 7.6_
  - [ ] 6.3 design 定级形态：多项目与角色限定
    - 同模块新增 `assert_note_edit_access_on_projects`（去重保序、逐项目判定；任一失败整单拒绝：有 403 即 403，否则 423；`NOTE_EDIT_MULTI_PROJECT_DENIED` + `project_ids` + 中文列出未通过的项目；其他异常原样冒泡；全部通过后 RLS 重设为首个项目）与 `assert_note_role_access`（先调判定实现；admin 放行；否则成员行项目角色须属于 `project_roles`，不属于返回 403 `NOTE_ROLE_REQUIRED` + 声明的中文文案；空集表示仅 admin）。
    - 单元测试写入 `test_note_edit_gate_unit.py`：经理 / 合伙人角色集合、空集仅 admin、EQCR 先被排除、readonly 成员先得「权限不足」。
    - _Requirements: 8.3, 8.5_
  - [ ] 6.4 多项目判定的性质测试
    - **Property 8: 多项目判定整单拒绝**
    - **Validates: Requirements 8.5**
    - 写在 `backend/tests/test_note_multi_project_gate.py`：1~4 个项目，各项目上调用者身份随机（含归档、EQCR、非成员）；固定样例：全部通过；一个 403 + 一个 423 ⇒ 403；只有 423 ⇒ 423；断言任何项目都没有数据写入。
    - _Requirements: 8.5_
  - [ ] 6.5 两处守卫登记附注编辑门禁并加可伪证断言
    - `test_project_endpoint_authorization_baseline.py`：`_PROJECT_LEVEL_TOKENS` 登记 `require_note_edit_access`、`assert_note_edit_access`（前缀匹配覆盖 `_for_object` / `_on_projects`）、`assert_note_role_access`；新增需求 6.10 可伪证断言（AST：`assert_note_edit_access` 在顶层语句中调用 `assert_project_permission`，级别实参是值为 review 的同文件常量或字面量；函数体调用 `is_project_eqcr`），以及「`assert_note_role_access` 必调判定实现」断言。
    - `test_disclosure_notes_project_gate_contract.py`：先加入同一组 6.10 可伪证断言（`CASES` 等的改造在 10.1）。
    - _Requirements: 6.10_

- [ ] 7. 级别回填迁移
  - [ ] 7.1 新增 `backend/migrations/V{n}__partner_manager_edit_level_backfill.sql` 与 `R{n}__rollback_partner_manager_edit_level_backfill.sql`
    - n 取任务 1.2 的现扫值；内容按 design §5.2（回填记录表 + 单条数据修改型 CTE；回滚只恢复仍等于目标值的行，随后删表）；`CREATE ... IF NOT EXISTS`；不用 `EXCEPTION` 吞错；注释只用全角标点、不写半角分号。
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.9, 4.10_
  - [ ] 7.2 回填结果的性质测试（真 PG）
    - 新增 `backend/tests/test_level_backfill_migration_pg.py`（`pg_only`），隔离用权限世界 PG 版（临时 schema、事务回滚）；正向经运行时迁移执行器的执行路径（与启动同一路径；实施时现读 `MigrationRunner`，确认可在隔离 schema 内驱动的入口；只能整库运行时改用用后即删的临时测试库）。
    - **Property 3: 回填结果等于逐行推导，改动行即记录行**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.11**
    - 数据集维度按需求 4.6；固定样例含被需求 4.2、4.3 改动的行，以及只持有质控 / 审计员 / 未登记委派的行。
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.11_
  - [ ] 7.3 回填幂等的性质测试（真 PG）
    - **Property 4: 回填幂等**
    - **Validates: Requirements 4.5, 4.7**
    - 同文件：执行两次与执行一次后的成员行与回填记录完全相同，第二次不改行、不加记录、不覆盖迁移前值；固定样例含被改动的行。
    - _Requirements: 4.5, 4.7_
  - [ ] 7.4 回填往返的性质测试（真 PG）
    - **Property 5: 回填往返**
    - **Validates: Requirements 4.6, 4.9**
    - 同文件：正向执行一次或两次后，随机挑若干行改成非目标值，再执行回滚：未被改动的行回到迁移前值，被改动的行保持现值，回填记录表不存在。
    - _Requirements: 4.6, 4.9_
  - [ ] 7.5 迁移执行语义与角色映射对账（真 PG）
    - 同文件。需求 4.1：两个脚本在同一库上重复执行不报错；回滚在没有回填记录、正向从未执行两种情况下都成功且不改动成员行。
    - 需求 4.10：预建冲突对象使正向失败 ⇒ 版本 n 未登记、失败表有记录、成员行与回填记录无改动；回滚脚本出错时 n 保持已应用。
    - 需求 12.7 对账：对合伙人 / 经理与 EQCR 别名集合的每个别名（取自需求 2.5 期望表），「只持有该别名一条现行委派、迁移前为 (auditor, readonly)」的成员行经正向迁移所得级别等于 `ROLE_MAP`（生产代码）给出的级别，合伙人 / 经理别名的项目角色也相等。
    - _Requirements: 4.1, 4.10, 12.7_

- [ ] 8. 两份清单的生成脚本与检查模式守卫
  - [ ] 8.1 共享包 `backend/scripts/gen/authz_inventory/` 的路由、识别与输出模块
    - 按 design §4.12：`routes.py`（把 `--root` 的 backend 放到 `sys.path[0]`，并断言导入的 `app` 位于 `--root` 之下；五个 `register_*_routers` 各建一个空 `FastAPI()` 收集 `APIRoute`；扫描文件里有路由装饰器但不在路由表中的端点标「未注册」）。
    - `gates.py`（门禁登记表；识别签名参数默认值（含参数名 `_`）、装饰器与路由器的 `dependencies`、注册附加依赖、函数体调用（含同文件辅助函数）；标注「条件执行」；级别取字面量或同文件常量；注释 / docstring / 字符串不计；未登记依赖报错）。
    - `render.py`（确定性 JSON：键与条目排序、`ensure_ascii=False`、`indent=2`、末尾换行，不含时间 / 机器名 / 绝对路径 / 行号）、`selfcheck.py`（合成样例框架）。单文件 ≤ 500 行。
    - _Requirements: 1.1, 1.7, 1.8, 9.1_
  - [ ] 8.2 附注写端点清册：归类、目标门禁声明、校验与检查模式
    - `classify.py`（S → C → G → E → R → X → I 取第一个满足的类别）与 `backend/scripts/gen/gen_note_write_inventory.py`（CLI `[--check] [--out PATH] [--root REPO]`；声明文件与已提交产物按脚本所在仓库定位，不随 `--root` 变化；每次生成 / 检查前先跑需求 1.6 的九个合成样例；需求 1.5 四项校验；需求 1.7 失败条件退出码 1、中文逐项原因、不写文件；检查模式不写文件，漂移退出码 2 并列出新增 / 消失 / 变化条目，一致时打印「附注写端点清册与仓库现状一致」并以 0 退出）。
    - 新增 `backend/data/authz/note_write_target_declarations.json`（design §5.4）：表 B 26 个端点按 design §4.8 逐条声明（17 个 `note_edit_gate`；9 个 `design_gate`，含 `gate`、`params`、`project_from`、`eqcr`）；`note_templates.py` 5 个与 `account_note_mapping.py` 3 个声明 `keep_current`（理由指向范围外 R3 / R10）；每条带 `reason`，不留 `pending_design_review`；`design_gate` 声明与代码实际挂载不一致时标「现门禁未等于目标门禁」。
    - _Requirements: 1.2, 1.5, 1.6, 1.7, 1.9, 1.10, 8.1, 8.2, 8.3_
  - [ ] 8.3 前端调用点扫描与匹配（`authz_inventory/frontend.py`）
    - 按 design §4.12 第 6 步：`DisclosureEditor.vue` 的 import 传递闭包（静态、`export … from`、字面量动态 `import()`；`@/` → `src/`；补扩展名；排除测试文件；`.vue` 只扫 `<script>`）；写方法调用形态（字面量、模板串、`apiPaths` 路径常量、`+` 拼接、封装函数）；匹配规则（方法相同、去查询串后逐段对应，插值段对任一段，`{x:path}` 对一段及以上，取字面段最多者，并列标「歧义」）；表 C / 表 D / 未解析三项；E、I 类端点在编辑器范围外的源码里是否有调用点；调用点键不含行号。接入 `gen_note_write_inventory.py`。
    - _Requirements: 1.3, 1.4, 1.5_
  - [ ] 8.4 edit 级影响清单脚本 `backend/scripts/gen/gen_edit_level_impact_inventory.py`
    - 按 design §4.12 与 §5.5：门禁调用点（每处调用或依赖挂载计一处；门禁定义不计；级别固定的门禁内部调用记「门禁内部」；级别经同文件辅助函数参数传入的按调用方逐个记录）、直接比较位置（属性访问与 `getattr` 字面量两种读法，按调用方记录实际级别，只有 edit 计入合计）、附录（展示 / 同步 / 复制用途的读取）、所门禁端点、业务域（五个注册分组 / 未注册 / 门禁内部）、叠加判定、是否属覆盖集合（读清册产物）、小计与合计。
    - 每次生成 / 检查前先自检需求 9.8 的十个样例；失败条件、检查模式与退出码同清册。
    - _Requirements: 9.1, 9.8_
  - [ ] 8.5 识别结果的性质测试
    - **Property 16: 识别结果不受注释与字符串影响**
    - **Validates: Requirements 1.8, 9.1**
    - 写在 `backend/tests/test_authz_inventory_recognition.py`：合成端点源码的注释、docstring、字符串中插入任意门禁名后，两份清单的识别结果（形态、级别、类别、所门禁端点）不变；门禁调用移入 if / try / 循环后只多出「条件执行」；固定样例为需求 1.6、9.8 的自检样例。
    - _Requirements: 1.8, 9.1_
  - [ ] 8.6 清册归类的性质测试
    - **Property 17: 清册归类唯一且计数守恒**
    - **Validates: Requirements 1.2, 1.5**
    - 同文件：由登记门禁形态随机组合的合成写端点集合，每个端点恰归一类且等于「S → C → G → E → R → X → I 取第一个满足」的模型，各类计数之和等于总数，（方法，完整路径）各出现一次；每类一个固定样例。
    - _Requirements: 1.2, 1.5_
  - [ ] 8.7 前端调用匹配的性质测试
    - **Property 18: 前端调用匹配取字面段最多者**
    - **Validates: Requirements 1.3**
    - 写在 `backend/tests/test_authz_inventory_matching.py`：固定样例含插值段、`{x:path}`、并列歧义、附加或改变查询串。
    - _Requirements: 1.3_
  - [ ] 8.8 两份清单的失败条件测试
    - 新增 `backend/tests/test_authz_inventory_failures.py`：需求 1.4、1.5、1.7、1.9、1.10 与 9.8 列出的每种失败条件各一个合成输入，断言退出码、中文原因（含文件 / 函数 / 未识别名称或样例名）、不写出文件、已提交产物不变；另以合成清册与声明验证目标门禁合并与「现门禁已等于目标门禁」标注。
    - _Requirements: 1.4, 1.5, 1.7, 1.9, 1.10, 9.8_
  - [ ] 8.9 生成改造前清册、冻结合并锁适用集合并纳入产物
    - 以 `--root` 指向基线树、`--out` 指向临时位置，生成改造前的附注写端点清册与 edit 级影响清单（后者留作 19.1 两树对比）。现算扫描文件数、写端点总数与各类计数（对账 F10、N12）、edit 级判定点与文件数（对账 F12）、覆盖集合（写作时 41）与「覆盖集合 ∩ 现门禁含合并锁」（写作时 13 个：A1~A5、A9~A12、A14~A17），逐项记入 `acceptance.md`。
    - 在 worktree 以生成模式写出 `backend/data/authz/note_write_inventory.json` 与 `edit_level_impact_inventory.json`（此时现门禁 ≠ 目标门禁的条目如实标注）。
    - _Requirements: 1.1, 1.9, 6.6, 9.1, 9.7_
  - [ ] 8.10 检查模式守卫测试 `backend/tests/test_authz_inventories_check_mode.py`
    - 子进程分别跑两脚本 `--check`（`env` 传 `PYTHONIOENCODING=utf-8`，以 `errors="replace"` 解码后断言输出非空、无替换字符）：同时断言退出码 0 与中文结论；两脚本各以 `--out` 写两次临时文件，与已提交产物逐字节相同；不加任何跳过或慢测排除标记。
    - 以 `-W error::pytest.PytestUnhandledThreadExceptionWarning` 复跑一次并通过，结果记入 `acceptance.md`。
    - _Requirements: 1.10, 9.1, 12.12_

- [ ] 9. 检查点：清单工具
  - 两脚本检查模式通过，任务 8 的测试全绿，两次生成逐字节相同；改造前计数与写作时快照的差异已逐条记入 `acceptance.md`。有疑问先问用户。

- [ ] 10. 表 A 端点改走附注编辑门禁
  - [ ] 10.1 `backend/app/routers/disclosure_notes.py` 的 A1~A12
    - 按 design §4.7：A1 函数体（请求体 `project_id`，`consol_lock=True`）；A2 对象反查（`DisclosureNote.id`，「附注章节不存在」，True）；A3~A5 函数体（True）；A6 / A7 路径依赖（False）；A8 对象反查（`NoteValidationResult.id`，「校验结果不存在」，False）；A9~A12 路径依赖（True）。删除这些端点原有的 `require_project_access` / `require_operation` / `check_consol_lock` / `_assert_project_edit` / `_assert_validation_project_access`，删除这两个帮助函数与不再使用的导入；`export_word` 的 docstring 按需求 2.6 改写。
    - 同步改写（design §8.6）：`test_disclosure_notes_hardening.py`（业务路径改用权限世界里的 admin 真跑门禁；两个调用序列用例改为逐项断言「归档 → 成员 review → EQCR → 矩阵 → 合并锁」，替身只装在各步下一层取数点上记录顺序）；`test_disclosure_notes_project_gate_contract.py`（`BODY_GATES` / `DEPENDS_GATES` / `CASES` 与「反查先于鉴权」改看 `assert_note_edit_access_for_object`，四项判据强度不降）；`test_project_access_level_registry.py`（附注两例须挂附注编辑门禁且门禁满足 6.10 断言；`wp_editor_router.update_sign_status` 仍须 edit；统一门禁改为要求 review + EQCR + `note:edit` + `consol_lock` 字面量）。改写对照记入 `acceptance.md`。
    - 重生成两份清单，A1~A12 标注「现门禁已等于目标门禁」；行数门 `disclosure_notes.py` ≤ 1899。
    - _Requirements: 2.6, 6.1, 6.6, 6.8, 6.10, 12.8_
  - [ ] 10.2 覆盖集合五身份端点测试（先覆盖 A1~A12）
    - 新增 `backend/tests/note_edit_gate_recipes.py`（每端点：方法、填好参数的路径、请求体、业务桩目标）与 `backend/tests/test_note_edit_gate_endpoints.py`（读清册产物取覆盖集合，与配方表求交后参数化）。
    - 每个端点：需求 12.2 的五种身份各在独立初始数据上发同一请求（一次性字段各取新值）；放行 = 业务桩恰 1 次且响应成功，拒绝 = 0 次且原因逐字相等；未登录 401 且业务 0 次；对象 id 端点另测身份④附带其有权项目的标识仍得 403「权限不足」、对象不存在得 404 且业务 0 次。
    - _Requirements: 6.2, 6.4, 6.5, 6.8, 12.1, 12.2_
  - [ ] 10.3 `note_offline` A13、`note_text_batch` A14~A17、`note_content_templates` A18~A20、`note_advanced` A21~A23
    - 全部改为路径依赖：A14~A17 `consol_lock=True`，其余 False；删除原有的项目级、操作矩阵与合并锁依赖；核对带幂等键的端点（实施时现读，如正文批量写入 apply）的幂等记录读写位于门禁之后。
    - 同步修正因门禁改造而失败的既有测试（以实际运行结果为准，如 `test_note_text_batch_endpoints`、`test_note_content_template_endpoints`、`test_note_prior_year_import_stamp`），断言强度不降，改写对照记入 `acceptance.md`；配方表补齐这 11 个端点。
    - 重生成两份清单，这些条目标注「现门禁已等于目标门禁」。
    - _Requirements: 6.1, 6.6, 6.11, 6.12, 12.2, 12.8_

- [ ] 11. 表 B 端点逐个定门禁（同文件的表 A 端点一并改）
  - [ ] 11.1 `note_wp_mapping.py`：A24、B1 两个刷新、B2 取数映射保存与全量取数刷新
    - 五个端点改为路径依赖 `require_note_edit_access(consol_lock=False)`；读方法端点不动。
    - 配方表补齐五个端点；补用例：B1 刷新被拒时附注表格数据保持请求前状态。
    - 重生成两份清单；按现算值下调鉴权基线两常量 `_IDENTITY_ONLY_BASELINE`、`_PREFIXED_IDENTITY_ONLY_BASELINE`（与现算值相等）。
    - _Requirements: 6.1, 8.1, 8.2, 8.4, 12.2_
  - [ ] 11.2 `note_custom_template.py`（B1 保存 / 回滚）与 `group_note_baseline.py`（B1 应用 + B2 保存集团基线）
    - 三个 B1 端点改为路径依赖附注编辑门禁（False）：集团基线应用只判路径中的项目，不判基线所属母公司项目；门禁先于「版本不存在」「基线不存在」的处理。`POST /api/group-note-baselines` 改为 `assert_note_edit_access_on_projects([project_id])`（查询参数中的来源项目）。
    - 测试：配方表补三个 B1 端点；非成员请求不存在的版本 / 基线得 403 而非 404；被拒时附注章节、自定义模板当前版本与全部历史版本、校验结果保持请求前状态。新增 `backend/tests/test_note_design_gated_endpoints.py`，先写保存集团基线端点的用例（非成员 / 本项目 readonly / 本项目 EQCR 得 403，至少一种身份放行，错误信息列出未通过的项目）。
    - 重生成两份清单，下调基线两常量至现算值。
    - _Requirements: 8.1, 8.2, 8.4, 8.5, 8.6_
  - [ ] 11.3 `note_trim.py`（2）、`note_custom_section.py`（3）、`note_conversion.py`（3）
    - 裁剪保存、自动裁剪、自定义章节新建、应用模板改为附注编辑门禁（False）；另存为模板在门禁之后校验章节属于路径中的项目，不属于返回 404「附注章节不存在」；模板互转预览改为 `require_project_access("readonly")`（实施时现读确认不落库，落库则改附注编辑门禁并改声明）；执行与撤销改为 `assert_note_role_access(project_roles={partner, manager}, denied_message="仅本项目经理或合伙人可切换附注模板类型")`。
    - 测试：配方表补五个附注编辑门禁端点；`test_note_design_gated_endpoints.py` 补三个模板互转端点（非成员 403；执行 / 撤销对 readonly、EQCR、质控、审计员 403，对经理、合伙人、admin 放行；预览对 readonly 与 EQCR 放行）。
    - 重生成两份清单，下调基线两常量至现算值。
    - _Requirements: 8.2, 8.4, 8.6_
  - [ ] 11.4 `note_section_lock.py`（4）、`note_data_lock.py`（3）、`note_group_template.py`（3）
    - 章节锁获取 / 心跳、数据快照、集团模板保存 / 脱离改为附注编辑门禁（False）；释放本人锁改为 `require_project_access("readonly")`；强制释放 `assert_note_role_access({manager, partner}, "仅本项目经理或合伙人可强制释放章节锁")`；锁定 `assert_note_role_access({partner, manager}, "仅本项目经理或合伙人可锁定报表附注数据")`；解锁 `assert_note_role_access(frozenset(), "仅管理员可解除报表附注数据锁定")`；集团模板下发 `assert_note_edit_access_on_projects([project_id, *target_project_ids])`。
    - 测试：配方表补五个附注编辑门禁端点；`test_note_design_gated_endpoints.py` 补其余六个端点（释放对 EQCR 与 readonly 本人放行；强制释放、锁定只放经理、合伙人与 admin；解锁只放 admin；下发任一目标项目未通过即整单拒绝、任何项目都不写入、信息列出未通过的项目）。
    - 重生成两份清单，下调基线两常量至现算值。
    - _Requirements: 8.3, 8.4, 8.5, 8.6_
  - [ ] 11.5 design 定级端点集合收口
    - `test_note_design_gated_endpoints.py` 增加断言：参数化端点集合等于清册中目标门禁为 design 定级门禁的端点集合（写作时 9 个，含两维守卫看不见的查询参数 / 请求体项目端点），双向比较并逐个列出差异；每个端点满足需求 8.6 的各项（各判定项目的非成员 403 且业务 0 次；写附注数据的端点对该项目 readonly 与 EQCR 也 403；EQCR 结论与清册声明一致；至少一种身份放行）。
    - _Requirements: 8.6_
  - [ ] 11.6 覆盖集合收口与鉴权基线终值
    - `test_note_edit_gate_endpoints.py` 增加：配方键集合等于覆盖集合（需求 12.3，按（方法，完整路径）双向比较、逐个列出，集合非空，五种身份用例全部被收集执行、无跳过）；改造后清册中「覆盖集合 ∩ 合并锁」等于 8.9 冻结的 13 个；读清册断言覆盖集合端点的项目级判定只有附注编辑门禁一种形态、不另挂操作矩阵与合并锁、门禁不处于条件执行；复用识别器扫描全部后端路由，挂载附注编辑门禁三种形态的写端点集合等于覆盖集合，两个 design 定级形态只出现在清册声明的端点上。
    - 鉴权基线两常量与将要提交的树上的现算值相等；表 B 写端点不在任一维仅登录清单与无鉴权清单中。
    - _Requirements: 6.1, 6.6, 8.4, 12.3_

- [ ] 12. 检查点：端点改造
  - 附注相关全部测试、两处守卫、`test_project_access_level_registry.py`、清单检查模式守卫，以及引用改动路由的既有测试；与基线树同批对照，确认没有新增失败。有疑问先问用户。

- [ ] 13. 交付中心门禁、判定查询端点与连续审计
  - [ ] 13.1 交付中心门禁改用单一 EQCR 判定（`backend/app/routers/deliverable.py`）
    - `_guard_action` 改调 `is_project_eqcr`，删除 `_is_project_eqcr`；docstring 按需求 2.6 改写；行数门 ≤ 1979。
    - 同步改写（design §8.6）：`test_export_endpoints_acceptance.py`、`test_full_deliverables_notes_gate.py` 改为替换 `_count_project_eqcr_assignments`（这些用例不观测 EQCR）；`test_deliverable_generation_membership_auth.py` 补 `独立复核合伙人` 委派用例（生成类写操作 403，列表 / 预览 / 下载放行）。改写对照记入 `acceptance.md`。
    - AST 断言：`_guard_action` 调用 `is_project_eqcr`，且不含与字面量 `"eqcr"` 的比较（7.3）；清册 G 类两个导出 Word 端点只调 `_guard_action`、不调附注编辑门禁（6.9）；全局 eqcr 无委派的用户在交付中心各操作的结论与改动前相同。
    - _Requirements: 2.6, 6.9, 7.3, 7.4, 9.4, 12.8_
  - [ ] 13.2 判定查询端点（新增 `backend/app/routers/note_edit_permission.py`）
    - 按 design §4.10 实现 `GET /api/projects/{project_id}/disclosure-notes/edit-permission`，在 `router_registry/report.py` 注册；自身 readonly 级鉴权，已归档项目返回「不能编辑 + 归档原因」而非 423；`is_eqcr` 一律给出；判定走 `assert_note_edit_access(..., consol_lock=False)`；其他异常冒泡为失败响应；不改任何业务数据。
    - 可伪证断言（AST，需求 10.1）：端点函数体调用 `assert_note_edit_access` 与 `is_project_eqcr`；除签名中的 readonly 鉴权外，不调用 `assert_project_permission`、不查委派表、不与 `"eqcr"` 比较。
    - _Requirements: 10.1_
  - [ ] 13.3 判定查询与写端点一致的性质测试
    - **Property 10: 判定查询与写端点结论一致**
    - **Validates: Requirements 10.1, 12.4**
    - 写在 `backend/tests/test_note_edit_permission_query.py`：需求 12.4 的八种身份情形 × 覆盖集合全部端点（参数化穷举）；不能编辑时查询原因与写请求拒绝原因逐字相同；查询前后业务数据不变；EQCR 判定出错时查询返回失败响应，不返回「能编辑」。
    - _Requirements: 10.1, 12.4_
  - [ ] 13.4 连续审计复制团队跳过上年 EQCR（`backend/app/services/continuous_audit_service.py`）
    - 按 design §4.11：开启复制团队时在同一事务内先 `project_eqcr_user_ids(上年项目)` 再复制成员行；写入 `items_copied.team_skipped_eqcr` 与顶层 `notices`；关闭复制团队时不判定，响应不含跳过人数与该提示；判定出错不吞（路由未提交即整单回滚）。
    - _Requirements: 11.1, 11.2, 11.3, 11.5_
  - [ ] 13.5 连续审计的性质测试与端到端样例
    - **Property 13: 连续审计复制等于模型**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.6**
    - 写在 `backend/tests/test_continuous_audit_eqcr_skip.py`：维度按需求 11.6；模型的别名集合取需求 2.5 期望表；固定样例 ①~⑨。
    - 样例 ⑩：用 ① 的数据真发创建下年项目请求，再以该用户调用覆盖集合中任一端点，得 403「权限不足」。
    - 需求 11.5：在判定的下层查询注入异常 → 非成功响应，库中不存在新项目及其成员行，随后重试成功。
    - _Requirements: 11.1, 11.2, 11.3, 11.5, 11.6_

- [ ] 14. 跨门禁的性质测试与端到端测试
  - [ ] 14.1 附注编辑门禁模型对拍（端点级）
    - **Property 7: 附注编辑门禁结论等于模型，拒绝零业务效果**
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.11, 6.12, 6.13**
    - 写在 `backend/tests/test_note_edit_gate_model.py`：维度按需求 6.13；端点覆盖路径 / 请求体 / 对象 id 三种项目确定方式，以及属于 / 不属于合并锁适用集合两种情形；固定样例为需求 6.13 列出的 7 个。
    - 拒绝时断言：业务桩 0 次；目标项目与其他项目数据不变；EventBus 替身计数为 0；带他人用过的幂等键只得拒绝响应，幂等记录不被读写；原因为固定中文且不含业务内容。
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.11, 6.12, 6.13_
  - [ ] 14.2 EQCR 别名拒绝、判定出错拒绝与改派即时生效
    - 新增 `backend/tests/test_eqcr_gate_consistency.py`。需求 7.4：覆盖集合每个端点 × 全局角色 partner / auditor / admin × `独立复核合伙人` 与 `eqcr` 委派（成员行 (partner, review)）→ 403，信息按需求 6.5；交付中心读以外的全部操作 403、读操作放行；两种委派逐端点结论相同。
    - 需求 7.6：委派查询注入异常，附注编辑门禁与交付中心门禁各至少一个写操作：非成功响应、业务 0 次、无残留改动。
    - 需求 7.9：全局 auditor、在 P 委派 `manager` 的用户改派 `eqcr` 并保存后，附注写与交付中心写都 403；改回 `manager` 后不再因 EQCR 被拒；预置与成员行矛盾的旧 `perm:*` 键（edit）不影响结论。
    - _Requirements: 7.3, 7.4, 7.6, 7.9_
  - [ ] 14.3 生效时效的性质测试
    - **Property 6: 变更提交后开始的判定即时按新数据**
    - **Validates: Requirements 3.6, 5.1, 5.2, 5.4, 5.5, 5.6, 7.9**
    - 写在 `backend/tests/test_permission_effect_timing.py`：交错时序用 `asyncio.Event` 把在途判定停在「读成员行之后」；变更类型与预置 `perm:*` 键按 design §8.3；固定样例 ①~④（④ 走覆盖集合中的一个端点）；断言委派保存对 `perm:*` 零读写删，键集合与剩余 TTL 不变。
    - _Requirements: 3.6, 5.1, 5.2, 5.4, 5.5, 5.6, 7.9_
  - [ ] 14.4 合伙人 / 经理升 edit 的全平台端到端
    - 新增 `backend/tests/test_partner_manager_edit_end_to_end.py`：委派保存 → 委派同步 → 鉴权全走生产代码，不预置成员行；代表端点至少两个（经 `require_project_access("edit")` 的调整分录写端点、经 `authorize_wp_edit` 的底稿保存端点）。
    - 需求 9.2：五个合伙人 / 经理别名各至少经一个代表端点放行，全局 auditor、manager 各测一次；全局 qc 或 eqcr、委派为合伙人 / 经理别名的用户成员行同为 edit，`require_project_access` 与 `assert_project_permission` 判定点放行、`authorize_wp_edit` 按全局能力拒绝。
    - 需求 9.3：`qc`、`质控`、`eqcr`、`独立复核合伙人`、`观察员` 各一次拒绝（沿用现有文案、业务 0 次）；改派前为 (manager, edit) 的用户改派为 `eqcr`、`质控`、未登记角色各一次拒绝。
    - 需求 9.6：全局 partner、没有成员行的用户经 `authorize_wp_edit` 放行；全局 qc、成员行 (manager, edit) 的用户得「无底稿编辑权限」。
    - _Requirements: 9.2, 9.3, 9.6_
  - [ ] 14.5 edit 级判定点的性质测试
    - **Property 12: edit 级判定点结论等于模型**
    - **Validates: Requirements 9.9**
    - 写在 `backend/tests/test_edit_level_gate_forms.py`：参数化的门禁形态集合从影响清单读取，并断言等于清单中出现的形态集合（含每个直接比较位置）；每种形态一个代表端点（有叠加判定时替换其下层取数点使其放行，并在测试中注明）；固定样例每种形态 7 个（质控 / EQCR / 未登记 / 无成员行拒绝；合伙人 / 经理 / 审计员放行）。
    - _Requirements: 9.9_
  - [ ] 14.6 EQCR 消费方清单与正向授权不变
    - 新增 `backend/tests/test_eqcr_consumer_inventory.py`（design §4.14）：登记表（`文件::函数` → 用途 / 是否识别 `独立复核合伙人` / 处置 / 理由）+ AST 三种检索口径；扫描结果与登记表键集合相等，新增未登记或登记已消失都打红；现算结果与 design 快照的差异逐条记入 `acceptance.md`，口径存疑的位置逐个判读后登记。
    - 需求 7.7：全局 eqcr、在该项目没有 `eqcr` 现行委派的用户，访问 EQCR 审批、意见解锁、备忘录定稿与版本历史、工时开始与结束、结构化判断提交、A25 复核表、项目权限的 EQCR 专属权限仍被拒，本人 EQCR 项目列表不含该项目，「本人已确认为 EQCR」为否；`独立复核合伙人` 委派在这些位置结论保持现状；结构化判断提交对 admin 的放行照旧。
    - _Requirements: 7.7, 7.8_

- [ ] 15. 注释口径改写与防假绿扫描
  - [ ] 15.1 按需求 2.6 改写后端、测试与前端注释
    - 写作时已知位置：`review_workflow.py`、`wp_procedures.py`、`wp_cross_check.py` 的模块注释（`_guard_action`、`export_word`、两处前提测试已在 13.1 / 10.1 / 2.2 改）。另按需求 2.9 的检索口径现扫后端生产代码与测试的注释、docstring、断言失败信息以及前端源码注释，逐条判读改写：不再称合伙人 / 经理为 review 级，所述理由与该端点现行判定一致。命中清单与判读结论记入 `acceptance.md`（steering 记忆条目在 20.1 改）。
    - _Requirements: 2.6_
  - [ ] 15.2 防假绿扫描测试
    - 新增 `backend/tests/test_no_false_green_scan.py`，按语法树扫描需求 12.13 的六条写法：替换不可替换的判定或权限缓存读写函数；`pytest.raises` 块内多于一条语句或其后未断言异常信息；子进程只断言退出码；「或」组合多个取值或对多元素字面量的成员判断；hypothesis 未显式 `max_examples=5`、fast-check 未显式 `numRuns: 5`；新增 `skip` / `skipif` / `xfail`（`pg_only` 与需求明文要求的 `xfail(strict=True)` 除外）。命中列出文件与位置；前端测试文件经 node 调 `typescript` 解析。
    - 扫描清单 = 基线树与 worktree 之间本 spec 新增的测试文件及新增 / 改动的测试函数，由仓库外一次性脚本现算后提交为测试数据（与扫描测试同目录的 JSON）；19.1 终版时重算。
    - _Requirements: 12.1, 12.13_

- [ ] 16. 检查点：后端全部改动
  - 后端新增与改写的全部测试、两处守卫、两份清单检查模式、防假绿扫描；与基线树同批对照，确认没有新增失败；核对 design §10 后端行数门。有疑问先问用户。

- [ ] 17. 前端：附注编辑器可写态单一来源
  - [ ] 17.1 判定查询 composable `useNoteEditPermission.ts`（新目录 `audit-platform/frontend/src/views/composables/noteEdit/`）
    - 按 design §4.13：对当前项目发判定查询（路径常量按现有约定登记到 `services/apiPaths`），请求带 `_silent: true`、`_dedupe: false`、`timeout: 15000`、`signal`；`watch(projectId, refresh, { immediate: true })`，每次先 abort 上一次并递增序号，只采用「当前项目 + 最新序号」的结论；状态 pending / ok / failed。
    - 六种失败（403、其他失败响应、网络错误、超时、缺 `can_edit` 或 `is_eqcr`、不能编辑却无原因）各恰好一条中文提示「无法确认编辑权限，已按只读打开」（403 附后端原因）；取消（去重、卸载、换项目）不算失败、不提示。派生 `canWrite`、`canWriteLocked`、`showReadonlyBadge`、`showNonEqcrEntries`、`disabledReason`（原因优先级按 design），以及 `ready()`、`markRejected()`、`refresh()`。
    - vitest：晚到响应样例（挂起 A → 切到 B 得到结论 → 放行 A，可写态仍按 B）、六种失败、三种取消、归档覆盖查询结论、原因优先级。
    - _Requirements: 10.1, 10.2, 10.6_
  - [ ] 17.2 呈现模型 `noteEditPresentation.ts` 与性质测试
    - 纯函数 `presentEntry(state, entry)` → `{ operable, rendered, disabled, tooltip }`，组件与测试共用。
    - **Property 14: 编辑器呈现等于模型**
    - **Validates: Requirements 10.3, 10.4, 10.5, 10.11**
    - 写在 `noteEditPresentation.property.spec.ts`（fast-check `{ numRuns: 5 }`）：输入只生成需求 10.1 可能出现的组合；固定样例 P / Q 项目、五种身份、尚未得到结论、查询失败、项目已归档、多窗口锁强制只读。
    - _Requirements: 10.3, 10.4, 10.5, 10.11_
  - [ ] 17.3 覆盖集合抄录与写入口清单
    - `noteEditCoverage.ts`（覆盖集合的方法 + 路径模板，以及章节拖拽排序路径）+ vitest 读 `backend/data/authz/note_write_inventory.json` 逐条相等（多一条、少一条都打红）。
    - `noteEditWriteEntries.ts`（design §5.7 接口）+ 对账 vitest：清册中编辑器范围内、目标属覆盖集合的每个调用点至少归属一个 `coverage: true` 入口；每个入口的 `callPoints` 都在清册中（无失效条目）；入口 `id` 唯一。
    - _Requirements: 10.3, 10.10_
  - [ ] 17.4 请求级守卫、`http.ts` 通用钩子与自动保存重试开关
    - `noteEditRequestGuard.ts`：编辑器挂载时在共享 `http` 实例上装拦截器、卸载时卸下；非可写态（含 `markRejected` 之后）命中覆盖集合的写请求以 `axios.Cancel('note-edit-readonly')` 拒绝，请求不发出、不进去重表；可写时在 config 上挂 `_forbiddenHandler`（同步 `markRejected` → 一条 `ElMessage.error(后端原因)` → `refresh`）；423 分支 `markRejected` + `refresh`，沿用现有提示、不另弹。
    - `utils/http.ts` 只加一处：403 且 config 带 `_forbiddenHandler` 时调用它，并跳过「权限不足，无法执行此操作」通用提示。
    - `useWorkpaperAutoSave` 增可选 `shouldRetry(err)`（缺省恒真，其他页面行为不变）。
    - vitest：拦截且不发出；403 恰好一条后端原因提示、无通用提示；423 沿用提示；不自动重发；同一操作的后续写请求被拦；未传新选项的调用方行为不变。
    - _Requirements: 10.7, 10.10_
  - [ ] 17.5 `DisclosureEditor.vue` 接线
    - 删除 `isEqcrRole`、未使用的 `canOp` / `whyCannot` 与 `useAuditContext` 的 `canEdit` 解构；`effectiveCanEdit` → `noteEdit.canWriteLocked`，原 `canEdit` 的用处 → `noteEdit.canWrite`；「📋 只读副本」改用 `showReadonlyBadge`；`v-if="!isEqcrRole"` → `v-if="noteEdit.showNonEqcrEntries"`；写入口加 `data-note-write="<id>"`，`:disabled` / `:title` 取 `presentEntry`；挂载 / 卸载请求级守卫。
    - vitest：模板中出现的 `data-note-write` 集合等于写入口清单的 `id` 集合。
    - 行数门 ≤ 3445（净增 < 20 行）。
    - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.8_
  - [ ] 17.6 子组件与 composable 的开关同源
    - `useNoteTree` 新增 `canWrite` 选项，`isEqcrRole` 选项改传 `!showNonEqcrEntries`，章节树 `:draggable` 取 `canWrite`；`DisclosureNoteContentTools` 接收 `:can-write="canWriteLocked"` 并删除组件内的 `can('note:edit')`（保留合并锁隐藏）；`NoteMappingDialog` 接收 `:can-edit="canWrite"`；`useNoteRefresh` 新增 `canWrite` 选项，底稿保存事件只在可写时刷新，被 403 拒绝时不置 `syncError`、不显示底稿同步失败提示；与编辑器以外页面共用的子组件在新开关缺省时沿用原行为。
    - _Requirements: 8.7, 10.8_
  - [ ] 17.7 自动触发门控与被拒后保留本地状态
    - 挂载 / 切年度后的「无章节自动生成」与切模板重新生成改为 `await noteEdit.ready()` 后仅在 `canWrite` 时执行；定时自动保存回调与快捷键保存先判 `canWriteLocked`；编辑器传给 `useWorkpaperAutoSave` 的 `shouldRetry` 对 403、423 与守卫取消返回否。
    - 被拒处理：`onClearAllFormulas` 区分门禁拒绝 / 守卫取消与其他失败，前者不做本地手动模式降级；批量删除、批量恢复、导出设置的逐章循环每轮先判 `canWrite`，一次拒绝即停止；拒绝路径不 `fetchDetailFresh`、不关闭弹窗、不清除未保存标记，编辑模式保持，离开页面仍按未保存拦截确认。
    - vitest：保存、一键清除公式、批量删除首条、定时自动保存各遇 403 的样例。
    - _Requirements: 10.7, 10.10_
  - [ ] 17.8 不可编辑态零写请求的性质测试
    - **Property 15: 不可编辑态不发出写请求**
    - **Validates: Requirements 8.7, 10.10**
    - 写在 `noteEditNoWriteWhenReadonly.spec.ts`：需求 12.2 五种身份加「尚未得到结论」「查询失败」两种状态 × 写入口清单 × 自动触发（定时保存、快捷键保存、无章节自动生成、切模板重新生成、底稿保存事件刷新、程序派发点击），枚举参数化并拦截网络：不可编辑态下覆盖集合写请求与拖拽排序请求为 0；可编辑身份下每个有调用点的入口，在满足业务前置条件并完成确认后都发出其调用点的请求。
    - _Requirements: 8.7, 10.10_
  - [ ] 17.9 开关同源的扫描与取值断言
    - vitest 扫描（TS AST，注释与字符串不计）：`DisclosureEditor.vue`，以及附注编辑器范围内不被范围外页面引用的组件与 composable，不再把全局角色与 `'eqcr'` 比较，不读 `useAuditContext` 的 `canEdit`，不调 `canDo` / `can`。
    - 五种身份与「尚未得到结论」「查询失败」两种状态下，逐一断言传给子组件与 composable 的写开关、EQCR 开关与编辑器两份值一致（按 EQCR 隐藏的入口在未得结论或失败时按 EQCR 处理）；共用子组件在编辑器以外页面的缺省行为不变。
    - _Requirements: 10.8_
  - [ ] 17.10 连续审计「创建下年」跳过提示（`DetailProjectPanel.vue`）
    - `items_copied.team_skipped_eqcr >= 1` 时 `ElNotification({ type: 'warning', title: '团队复制提示', message: notices[0], duration: 0 })`（纯字符串，不用 `h()`）；跳过人数为 0 或响应不含该字段时不提示；现有成功提示与跳转保持不变。
    - vitest 覆盖上述三种响应。
    - _Requirements: 11.4_
  - [ ] 17.11 前端文案与静态检查
    - 本 spec 改动的前端文件在 `npx eslint` 的 `gt-audit/no-english-ui-text` 下零新增告警（与基线树同文件对照）；新增与改动的用户可见文案逐条列入 `acceptance.md`。
    - _Requirements: 10.9_

- [ ] 18. 检查点：前端
  - 新增与改动的 vitest 全绿；本 spec 新增与改动的前端测试文件以 `GT_TEST_NETWORK_AUDIT=1` 跑一次，无真实网络连接、不新增泄漏清单条目；重生成附注写端点清册（编辑器调用点会变），同步 `noteEditCoverage.ts` 与写入口 `callPoints`，检查模式通过。有疑问先问用户。

- [ ] 19. 验收
  - [ ] 19.1 清单终版与两树对比
    - 重生成两份清单与防假绿扫描清单；生成模式连续两次逐字节相同，检查模式通过。
    - 需求 9.7：8.9 留存的改动前影响清单与终版逐条对比：消失或形态 / 级别改变的判定点，只能是覆盖集合端点上被附注编辑门禁替换的；新增的只能是清册声明、目标为 edit 级的 design 定级门禁（按 design §4.8 应为 0）；其余各字段逐条相同（含所门禁端点：判定查询端点不落入已有 edit 级判定点的范围）。逐条差异与归因记入 `acceptance.md`。
    - 需求 8.4：用仓库外一次性探针调用鉴权基线守卫的扫描函数，在基线树与 worktree 上各现算两维仅登录清单与无鉴权清单并逐条对比：移出的只能是本 spec 改造的端点；没有新进入的端点（含表 A 端点）；表 B 所在文件的读方法端点档位不变。
    - _Requirements: 8.4, 9.7, 12.12, 12.13_
  - [ ] 19.2 候选树与临时 worktree
    - 在实施 worktree 中逐个 `git add` 本 spec 的全部文件（新增模块、迁移、清单产物、测试、`.kiro/specs/partner-manager-edit-permission/` 目录等；不用 `git add -A`），以 `git write-tree` + `git commit-tree -p HEAD` 生成候选提交对象 C（不移动分支、不设 git 环境变量；实施 worktree 的暂存区独立于主工作树）。
    - 以 `git worktree add --detach` 从 C 检出验证 worktree（如 `D:\wt_pm_verify`）与变异 worktree（如 `D:\wt_pm_mutate`），不用 `D:\_gt_*` 前缀，建好即 lock；C 的 SHA 记入 `acceptance.md`。此后实施 worktree 若有代码改动，重新生成 C，并重跑受影响的变异与验证。
    - _Requirements: 12.5, 12.9_
  - [ ] 19.3 磁盘变异：门禁级别、EQCR 调用、角色映射、缓存替代（design §8.5 ①~④）
    - 在变异 worktree 内逐项执行：① `NOTE_EDIT_MIN_LEVEL` 改回 `"edit"`；② 删除门禁对 `is_project_eqcr` 的调用；③ `ROLE_MAP` 的 `manager` / `项目经理` 改回 (manager, review)；④（D12 替代）在 `assert_project_permission` 前插入「读到 `perm:*` 键即按其级别放行」。应红 / 应绿断言按需求 12.5 与 design §8.5；需求 12.5④ 的原变异按 D12 不适用，在 `acceptance.md` 写明裁定。
    - 规则（19.3~19.7 通用）：应红断言是确定性用例；失败落在指定断言且信息可辨认（收集 / 导入 / 语法 / 夹具错误与超时都不算变红）；应绿保持通过；变异前记文件哈希，运行后逐字节恢复、哈希一致、复跑全绿；记录（文件与改动、命令、变红测试标识与断言信息、应绿证据、恢复前后哈希、复跑结果）写入 `acceptance.md`。
    - _Requirements: 6.10, 12.5_
  - [ ] 19.4 磁盘变异：单一来源、EQCR 判定、连续审计（⑤~⑧）
    - ⑤ 角色上下文服务写回一份等价映射 → 2.5 扫描红在「映射不唯一」；⑥ EQCR 判定模块写回别名字面量集合 → 2.8 扫描红在「来源不唯一」，`ROLE_MAP` 的 `独立复核合伙人` 改为 (partner, edit) → 7.4 该别名用例红在「应拒绝」；⑦ EQCR 判定的委派条件改回只认 `eqcr` → 7.4 与性质 13 样例②红；⑧ 删除连续审计的跳过判定 → 性质 13 样例①红在「新项目不应有该用户的成员行」，样例⑨保持通过。
    - _Requirements: 2.7, 7.2, 7.4, 11.6, 12.5_
  - [ ] 19.5 磁盘变异：两份清单（⑨~⑪ 与两脚本自检判错）
    - ⑨ 一个覆盖集合端点的附注编辑门禁换回 `require_project_access("edit")` → 清册检查模式非零退出并列为变化条目；⑩ 新增一个挂附注编辑门禁的写端点并重生成清册 → 11.6 的集合断言红在「集合不等」并点名该端点（路由文件与清册都逐字节恢复）；⑪ 一个非覆盖集合端点的 edit 门禁改为 review、一个读端点新挂 edit 门禁 → 影响清单检查模式分别列为消失 / 新增条目。
    - 两脚本各使识别逻辑判错一个合成样例（如不识别签名参数默认值里的依赖）→ 生成与检查模式都非零退出、列出样例名、不写出文件、已提交产物不变。
    - _Requirements: 1.6, 9.7, 9.8, 12.3, 12.5, 12.12_
  - [ ] 19.6 磁盘变异：级别比较位置与 design 定级端点（⑫ 与需求 8.6）
    - ⑫ `assert_project_permission`、`authorize_wp_edit` 与每个直接比较位置对 edit 的比较逐个改为 review → 性质 12 的质控固定样例红在「应拒绝」。
    - 需求 8.6：9 个 design 定级端点逐个把项目级判定换回只校验登录 → 红在该端点的 403 断言。
    - _Requirements: 8.6, 9.9, 12.5_
  - [ ] 19.7 磁盘变异：前端、防假绿扫描与可伪证断言（⑬~⑮）
    - ⑬ 前端一处开关改回按全局角色判定 → 17.9 扫描红在该处、受影响身份的取值断言红在该开关；任一写入口改为忽略可写态 → 性质 14 红在该入口。
    - ⑭ 在一个被扫描的测试文件写入一处 override 附注编辑门禁的语句 → 防假绿扫描红在该条。
    - ⑮ 判定查询改为直接判 edit 级、`_guard_action` 删去 EQCR 判定调用 → 需求 10.1 / 7.3 的可伪证断言各红在该断言。
    - _Requirements: 7.3, 10.1, 10.8, 10.11, 12.5, 12.13_
  - [ ] 19.8 改写对照、计数对账、行数门与迁移号复核
    - 汇总 `acceptance.md` 的既有测试改写对照（design §8.6 全部文件，加上 19.9 运行中因口径变化失败而改写的测试，逐函数新旧对照）；现算计数（清册各类、影响清单合计、鉴权基线两常量、合并锁适用集合、EQCR 消费方清单）与需求 / 设计快照逐项对账，差异写明原因。
    - 行数门（design §10）：`disclosure_notes.py` ≤ 1899、`deliverable.py` ≤ 1979、`deps.py` ≤ 800、`test_phase4_endpoints.py` ≤ 1177、`DisclosureEditor.vue` ≤ 3445、新增后端文件 ≤ 800（清单脚本单文件 ≤ 500）、`noteEdit/` 各模块 ≤ 300；超限按 `backend/scripts/file_size_whitelist.txt` 的规则登记拆分轴。
    - 按需求 4.1 再核迁移号：现扫「主工作树磁盘 ∪ origin 目标分支最新提交」，n 被占用则顺延改名（文件名、测试引用、`acceptance.md`），重跑任务 7 的测试并重新生成 C。
    - _Requirements: 4.1, 12.8, 12.14_
  - [ ] 19.9 干净检出全量验证（需求 12.9）
    - 在验证 worktree（C 的干净检出）运行：后端全量 `python -m pytest backend/tests/`（不加 `-x`）；PG 轮以子进程级 `DATABASE_URL`（值取自主工作树 `.env`，不回显、不在共享终端持久设置）运行本 spec 新增的全部 `pg_only` 用例与引用本 spec 改动模块的既有 `pg_only` 用例，本 spec 新增 `pg_only` 用例跳过数为 0；前端 `npx vitest run` 全量；本 spec 新增 / 改动的前端测试再以 `GT_TEST_NETWORK_AUDIT=1` 跑一次。
    - 前端类型检查：单区域临时 tsconfig 只查改动文件；先注入一处 `number = string` 确认报 TS2322，恢复后确认通过；输出含内存耗尽等崩溃信息不算通过。
    - 检查模式守卫另以 `-W error::pytest.PytestUnhandledThreadExceptionWarning` 复跑一次并通过。
    - 预存失败归因：同一批测试在基线树上运行；只有以同一测试标识、同类失败（同一异常类型与断言位置）复现的才登记为预存（测试标识、失败摘要、基线提交）；其余算本 spec 引入，修复后重新生成 C 并重跑。
    - _Requirements: 12.6, 12.7, 12.9_
  - [ ] 19.10 本地真库迁移验收（需求 4.8，依赖外部环境）
    - 前置条件：用户确认重启时机（本地开发服务与数据库由并发会话共用）；后端以将要提交的树全量启动——在实施 worktree 运行其 `start-dev.bat`（会停掉 9980 / 3030 上的共享开发服务），或以同一启动流程 `run_uvicorn.py` 在独立端口启动，`acceptance.md` 写明执行方式；热重载不跑迁移。
    - 步骤：重启前按 F13 口径现查迁移前快照 → 全量启动 → 现查版本 n 已登记为已应用、且没有该版本的失败记录 → 被改动行数与回填记录数相等，按「需求 4.2 / 4.3」和「现行项目 / 已软删项目」分组 → 与迁移前快照逐行对账，再与 F13 对账（写作时期望：现行项目 2 行 admin 由 manager + review 改为 manager + edit；已软删测试项目 84 行由 auditor + readonly 改为 manager + edit；需求 4.3 规则 0 行），差异逐条说明。本地库只执行正向迁移，不执行回滚。
    - 前置条件不满足时按需求 12.11 标 `[ ]*`，写明「代码已改但未实测」与所缺环境。
    - _Requirements: 4.8_
  - [ ] 19.11 浏览器实测（需求 12.10，依赖外部环境）
    - 前置条件：19.10 的后端与对应前端以将要提交的树运行（本 spec 改动的文件与 C 逐字节相同，核对哈希）；用 chrome-devtools，不用 Playwright；实测期间不改附注编辑器及其子组件源码、不做变异。
    - 数据：名称带「【测试】」、未归档、未合并锁定的项目；新建五个全局角色为 auditor 的临时账号与人员库记录，经委派保存端点分别委派为 `manager`、`partner`、`qc`、`eqcr`、`观察员`，成员行由委派同步写出。
    - 断言：经理、合伙人、质控的写入口可操作、不显示「📋 只读副本」，各改一处正文并保存，刷新后内容保持、「最近一次编辑」为本人；EQCR 写入口不可操作且显示该标识；readonly 成员写入口可见且禁用、悬停原因「权限不足」、不显示该标识；EQCR 与 readonly 成员用页面脚本发出与保存按钮相同的请求，分别得到需求 6.5 / 6.4 的 403 原因、附注内容不变；页面不出现英文报错文案。每种身份的页面快照与请求 / 响应摘要记入 `acceptance.md`。
    - 清理：按写过的表逐项恢复到实测前并核对行数（临时账号、人员库记录、委派、成员行、附注改动）；审计日志等只追加留痕不删，在 `acceptance.md` 登记；实测结束后按用户安排恢复主工作树的开发服务。
    - 前置条件不满足时按需求 12.11 标 `[ ]*` 并写明所缺环境。
    - _Requirements: 12.10_

- [ ] 20. 收尾
  - [ ] 20.1 steering 记忆定级条改写与口径检索
    - 在 worktree 的 `.kiro/steering/memory.md`（基于上游版本，不碰主工作树那份）只改「项目级鉴权按『谁会用』定级」这一条，行级改动：合伙人（含签字合伙人）/ 经理为 edit 级，质控 / EQCR 为 review 级；附注写操作走附注编辑门禁（本项目 review 及以上 + EQCR 只读 + `note:edit`）；同条末尾一句指向 R1 / R2 / R3 待另立 spec；文件保持 ≤ 300 行。
    - 需求 2.9：在需求 2.6 范围内检索同一注释块、docstring、断言失败信息或记忆条目里同时出现「合伙人」或「经理」与「review」的文字，逐条判读，仍称合伙人 / 经理为 review 级的命中为 0；检索口径与命中清单（含判读结论）记入 `acceptance.md`。
    - _Requirements: 2.6, 2.9_
  - [ ] 20.2 R1 / R2 / R3 后续 spec 登记（只登记，不在本 spec 实施）
    - 在 `acceptance.md`「后续 spec 登记」节写明：R1（委派端点只校验登录，自封经理一次即得 edit 级与经理项目操作）与 R2（移出团队不撤销成员行，前 EQCR 由附注只读变为可编辑）建议合为一个 spec（先定「谁有权委派」，移除委派时撤销或降级成员行）；R3（`note_templates.py` 5 个全局附注模板写端点无任何鉴权，未登录即可增删改）单独一个 spec；各附证据（design §9、N8）与优先级（均为 🔴 高）。同一结论写进 20.3 的 INDEX 登记行。
    - _Requirements: 12.14_
  - [ ] 20.3 INDEX.md 行级登记
    - 在 worktree 的 `.kiro/specs/INDEX.md`（基于上游最新版本，不碰主工作树那份）按现有格式登记本 spec 一行：日期、完成度、要点、证据、R1 / R2 / R3 待另立 spec。文件为纯 CRLF：以 `read_bytes().decode('utf-8')` 读、`write_bytes()` 写；表格行每行恰 4 个未转义 pipe（按 `(?<!\\)\|` 计数）；统计数按现扫 `.kiro/specs/*/tasks.md`，不按增量推算；提交前看 diff，只动本 spec 行与统计行。
    - _Requirements: 12.14_
  - [ ] 20.4 闭合检查与任务勾选
    - 用仓库外一次性闭合检查脚本核对（用完即删，输出写入 `acceptance.md`）：需求 1~12 每条验收标准至少对应一个测试标识或验收记录条目，对应关系逐条列出；design §8.5 全部变异以及需求 8.6、12.12 的补充变异逐项有记录；design §8.3 每个性质测试的测试标识、声明的样例数与固定样例名；现算计数对账、改写对照、预存失败登记、真库迁移验收、浏览器实测与清理对账齐全；每个端点级测试文件至少一条放行用例。未闭合不得勾选最后一项。
    - 按需求 12.11 勾选：只勾「代码与测试已在将要提交的树中、19.9 干净检出运行通过（`pg_only` 实际执行）、涉及的变异记录已写入」的任务，并在任务下写完成证据（测试标识、验收记录条目）；外部环境未实测的标 `[ ]*` 并写明「代码已改但未实测」与所缺环境；不用 `[~]`。勾选在主工作树本 spec 的 `tasks.md` 上进行，随后逐字节同步进 worktree。
    - _Requirements: 12.11, 12.14_
  - [ ] 20.5 单 commit 提交与推送
    - 提交前：用 `git diff --stat` 核对最终树与 C 的差异只有 `.kiro/` 下的文档（`tasks.md`、`acceptance.md`、`INDEX.md`、`memory.md`）；按需求 4.1 再核一次迁移号。
    - 在实施 worktree 逐个 `git add` 本 spec 的全部文件，单个 commit 提交；不用 `--no-verify`；hook 失败时修复后重新提交，不用 `--amend`。
    - 推送前 `git fetch --prune origin`，确认 `origin/spec/disclosure-note-doc-upload-and-batch-fill` 尖端仍是本提交的父提交（可快进）；若已前移则停止推送：在新尖端上 rebase（逐文件裁决冲突）、重核迁移号、重跑 19.9 受影响的部分后再推，不强推。
    - 只推到该分支：`git push origin HEAD:spec/disclosure-note-doc-upload-and-batch-fill`；推送后 `git ls-remote origin spec/disclosure-note-doc-upload-and-batch-fill` 核对远端 SHA 等于本地提交（推送命令返回异常码时先核对，不盲目重推）。
    - 本任务在提交之后才算完成：勾选只更新主工作树副本，不为勾选另做提交。
    - _Requirements: 4.1, 12.11_
  - [ ] 20.6 清理 worktree 与临时分支
    - 实施、验证、变异 worktree，以及只读参考 worktree `D:\wt_pm_ref`（与可能另建的 `D:\wt_pm_base`）逐个 `git worktree unlock` → 删除目录（`git worktree remove` 会卡在确认提示，改用 `Remove-Item -Recurse`）→ `git worktree prune`；`git worktree list` 核对无残留。
    - 确认临时分支的提交已包含在 `origin/spec/disclosure-note-doc-upload-and-batch-fill` 之后删除该分支（`git branch -d`；因无上游被拒时，核实包含关系后用 `-D`，删除临时分支已获用户授权）。
    - 勾选本项前复跑 20.4 的闭合检查（需求 12.14：最后一项任务）。
    - _Requirements: 12.9, 12.14_

## Notes

- 所有任务均为必做（用户确认），清单中不使用 `*` 可选标记；依赖外部环境的 19.10、19.11 照常列出并写明前置条件，执行期未能实测时按需求 12.11 标 `[ ]*`。
- 需求与设计已确认：Q1–Q7 与细化口径按默认，design D1–D13 全部采纳；执行任务时不修改 `requirements.md`、`design.md`。
- R1 / R2 / R3 不在本 spec 修，20.2 登记另立 spec；R4–R14 按 design §9 的处置执行（登记、保持现行为或接受）。
- 依赖图大体串行：多数任务共用 `acceptance.md`、两份清单产物、端点配方表与鉴权基线常量，并行改写会互相覆盖；只有确知写入文件不重叠的任务放在同一波。
- gt-plan `spec_status` 不识别 `[~]`，会误报完成。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["2.1"] },
    { "id": 4, "tasks": ["2.2", "2.6"] },
    { "id": 5, "tasks": ["2.3", "2.7"] },
    { "id": 6, "tasks": ["2.4", "2.8"] },
    { "id": 7, "tasks": ["2.5"] },
    { "id": 8, "tasks": ["2.9"] },
    { "id": 9, "tasks": ["3.1"] },
    { "id": 10, "tasks": ["3.2"] },
    { "id": 11, "tasks": ["3.3"] },
    { "id": 12, "tasks": ["3.4"] },
    { "id": 13, "tasks": ["3.5"] },
    { "id": 14, "tasks": ["4.1"] },
    { "id": 15, "tasks": ["4.2", "4.3"] },
    { "id": 16, "tasks": ["6.1"] },
    { "id": 17, "tasks": ["6.2"] },
    { "id": 18, "tasks": ["6.3"] },
    { "id": 19, "tasks": ["6.4", "6.5"] },
    { "id": 20, "tasks": ["7.1"] },
    { "id": 21, "tasks": ["7.2"] },
    { "id": 22, "tasks": ["7.3"] },
    { "id": 23, "tasks": ["7.4"] },
    { "id": 24, "tasks": ["7.5"] },
    { "id": 25, "tasks": ["8.1"] },
    { "id": 26, "tasks": ["8.2"] },
    { "id": 27, "tasks": ["8.3"] },
    { "id": 28, "tasks": ["8.4"] },
    { "id": 29, "tasks": ["8.5", "8.7", "8.8"] },
    { "id": 30, "tasks": ["8.6"] },
    { "id": 31, "tasks": ["8.9"] },
    { "id": 32, "tasks": ["8.10"] },
    { "id": 33, "tasks": ["10.1"] },
    { "id": 34, "tasks": ["10.2"] },
    { "id": 35, "tasks": ["10.3"] },
    { "id": 36, "tasks": ["11.1"] },
    { "id": 37, "tasks": ["11.2"] },
    { "id": 38, "tasks": ["11.3"] },
    { "id": 39, "tasks": ["11.4"] },
    { "id": 40, "tasks": ["11.5"] },
    { "id": 41, "tasks": ["11.6"] },
    { "id": 42, "tasks": ["13.1"] },
    { "id": 43, "tasks": ["13.2"] },
    { "id": 44, "tasks": ["13.3", "13.4"] },
    { "id": 45, "tasks": ["13.5"] },
    { "id": 46, "tasks": ["14.1", "14.2"] },
    { "id": 47, "tasks": ["14.3", "14.4"] },
    { "id": 48, "tasks": ["14.5", "14.6"] },
    { "id": 49, "tasks": ["15.1"] },
    { "id": 50, "tasks": ["15.2"] },
    { "id": 51, "tasks": ["17.1", "17.2", "17.3"] },
    { "id": 52, "tasks": ["17.4"] },
    { "id": 53, "tasks": ["17.5"] },
    { "id": 54, "tasks": ["17.6"] },
    { "id": 55, "tasks": ["17.7"] },
    { "id": 56, "tasks": ["17.8", "17.9", "17.10"] },
    { "id": 57, "tasks": ["17.11"] },
    { "id": 58, "tasks": ["19.1"] },
    { "id": 59, "tasks": ["19.2"] },
    { "id": 60, "tasks": ["19.3"] },
    { "id": 61, "tasks": ["19.4"] },
    { "id": 62, "tasks": ["19.5"] },
    { "id": 63, "tasks": ["19.6"] },
    { "id": 64, "tasks": ["19.7"] },
    { "id": 65, "tasks": ["19.8"] },
    { "id": 66, "tasks": ["19.9"] },
    { "id": 67, "tasks": ["19.10"] },
    { "id": 68, "tasks": ["19.11"] },
    { "id": 69, "tasks": ["20.1"] },
    { "id": 70, "tasks": ["20.2"] },
    { "id": 71, "tasks": ["20.3"] },
    { "id": 72, "tasks": ["20.4"] },
    { "id": 73, "tasks": ["20.5"] },
    { "id": 74, "tasks": ["20.6"] }
  ]
}
```
