# 任务：程序链加固与 Java 迁移契约（procedure-chain-hardening-and-java-contracts）

> 证据口径：「变异 N 条全红」= 逐条磁盘变异、跑指定用例、红在预期断言上、逐字节恢复（sha256 校验）。
> 回归在 d0de87a6c（gt_push 推送）+ 本 spec 改动上跑；红的逐条回到 d0de87a6c 干净检出复跑归因。

## 0. 交付前提（R0）

- [x] 0.1 gt_push 推送 d0de87a6c（父 213f19816，13:10）后核对：本链模块在推送提交里（procedure_scope_retention / wp_visibility.delegation_guard / effective_scope / program_row_guard / workpaper_recycle_service / trim_subject_scope / procedure_row_trim_service / useProgramRowControl / useProgramRowDelegate）；本链回归见 1.8 / 2.6，红项全部在 d0de87a6c 干净检出复现（预存，非本 spec）

## 1. 批 1：P0

- [x] 1.1 R1 详情单一来源：workpaperApi.getWorkpaperSettled（自有在途表 + 静默 + 取消重取一次）/ useEditorMode / useEditorUniver（只读详情 + onDetailLoaded）/ useEditorSave（setWpDetail）/ UniverEditorCore（update:wpDetail、转发防重入、只摘自己的监听）/ Shell（modeResolved、@update:wp-detail）
- [x] 1.2 R1 测试：editorDetailRace（真实 utils/http + 假 adapter，修复前 2 发且先发被取消）+ 单元层只读 / 取消 / 404；变异 M1~M8、FR10a/b、FW1/FW2/FW5 全红
- [x] 1.3 R2 编辑锁后端：`_authorize_lock` + 动作矩阵登记（取锁 / 续期进内容写族，强制接管只给全权族）+ 续期被拒先放本人锁 + 强制接管 403 + 记窗口标识 + `/active` 仅 admin；变异 B1~B8 全红
- [x] 1.4 R2 编辑锁前端：`enabled` / `denied` / 静默 / 续期 403·404 停心跳重取 / 强制失败中文提示；WorkpaperEditor 传 `enabled: canEdit`；变异 FL1~FL6、FW3 全红
- [x] 1.5 R2 测试：`test_editing_lock_authz_pg.py` 表驱动（未委派审计员 / 被委派审计员 / 主编 / 经理 / admin / 非成员 × 取锁 / 续期 / 强制 / 附注锁 / 报告锁，18 例）；SQLite 锁语义用例经 `_editing_lock_helpers` 放行资源判定（与设计的偏差见 design §9.1），顺带修 4 例 d0de87a6c 上就红的过期用例
- [x] 1.6 R3 模板复制：中间 flush（外键）、单份底稿门 / 整循环来源成员 + 逐份可见、复制产物按模板落自己的文件（失败清理）、前端去「覆盖」与计数提示
- [x] 1.7 R3 测试：`test_template_copy_integrity.py`（SQLite 开外键）+ `test_template_copy_visibility_pg.py`（PG 回滚）+ `WpTemplateCopyDialog.result.spec.ts`；变异 C1~C6、FT1~FT3 全红
- [x] 1.8 批 1 回归、浏览器实测（H1A 首屏 5 次、无权底稿取锁、模板复制）、提交推送
  - 浏览器（chrome-devtools 独立上下文，admin）：重药安徽 I1A（HTML 程序表册）刷新 5 次，详情 GET 每次 1 发、0 次取消、无错误页；不存在的底稿 URL 只剩一句中性提示 + 「返回底稿列表」，取锁 404、不弹提示、不建锁行；【测试】公式同步甲 模板复制同码 ⇒ 「没有复制任何底稿：跳过 1 份」，库里不多行
  - 实测补修 3 处（见 design §9.4）：404 时步骤映射 / 侧栏渲染配置 / Univer 目录各弹一次英文感的全局提示、左侧页签导航显示「无匹配的 sheet」；模板复制跳过说明漏出 `overwrite=False`；变异 FA1~FA6、C7 全红
  - 无权底稿取锁未在浏览器测（没有可用的非 admin 测试账号：ptgd_auditor 停用待定），由 `test_editing_lock_authz_pg.py` 18 例覆盖
  - 回归：后端链路 65 文件 8 红、PG 30 文件 1 红 + 3 错误、守卫 18 文件 9 红、前端 137 文件见 2.6，全部在父提交干净检出逐条复现（design §9.2）；单区域 vue-tsc 候选 = 基线 1855 条、新增 0

## 2. 批 2：程序表链路

- [x] 2.1 R4 后端：`program_row_status_sync`（控制台按行 / 任务级端点 / 裁剪方案行条目三条路径同事务对齐已有的状态覆盖值，不新建）、恢复回执带原执行人；变异 B2-1~B2-7 全红
- [x] 2.2 R4 前端：恢复执行独立按钮 + 提示原执行人 / 重新委派、下拉只给待执行 / 执行中 / 已完成、裁剪恢复后重读行归属与任务视图；变异 FC1~FC6、FR4a/b 全红
- [x] 2.3 R5 深链 `@program`（`programConsoleRoute`）；R6 无页名控制台落任务（后端三处放宽 + 前端照常请求、仅页面标记另行提示）；变异 FR5a~c、B2-8~B2-10、FR6a/b、FRpo 全红
- [x] 2.4 R7 行级权限读到之前 / 读不到整表只读 + 原因 + 重试；R8 覆盖值批量端点（≤200、每项保存点、一次提交、失败逐条回报）+ 前端分批；变异 FR7a~c、FS1~FS4、B2-11~B2-14 全红
- [x] 2.5 R9 前置横幅按编码 getter（后端清单补齐全部循环、复核通过算完成、粗裁掉的不阻断，见 design §9.3）；R10 无权 / 不存在中性文案、能力快照不叠加错误、原因码不进正文；变异 R9-1~R9-8、FP1~FP5、FR10a~e、FS1/FS2、FC1 全红
- [x] 2.6 批 2 回归、浏览器实测（裁剪 → 恢复 → 重新委派全流程）、提交推送
  - 浏览器：【测试】公式同步甲 E1 `?sheet=@program` 直达「货币资金实质性程序表E1A」；第 23 行裁剪 ⇒ 行显示已裁剪 + 「恢复执行」、任务 not_applicable / cancelled；恢复 ⇒ 提示「已恢复执行，原执行人已清除，请重新委派」、任务 execute / unassigned、下拉回到 待执行 / 执行中 / 已完成 / 裁剪；委派对话框可再打开（本测试项目没有团队成员，预览未执行，由 PG 用例覆盖）
  - 重药安徽：程序裁剪页「程序裁剪 ›」落到「函证程序表D0A」页签；H1 前置横幅按 `wp_code=H1` 请求，显示「前置部分完成，建议先完成 C6」；`POST /api/workpapers/field-overrides/batch` admin 200、未登录 401（路由已注册）
  - 实测补修：循环册的程序表页 componentType 是循环组件，`@program` 原先只认 a-program-console ⇒ E1 / H1 / D2 都落「底稿目录」，改为同时认 sheet_type = procedure（design §9.4）；变异 FR5d / FR5e 全红
  - 前端 137 文件回归：失败集合与父提交逐条相同（design §9.2）

## 3. 批 3：生成与人员

- [x] 3.1 R11 统一回执模块；链路编排逐码保存点 + plan_generation；IPO / B60 / D4；自定义单张表头；模板集未填表头计数
  - `wp_generation_receipt.GenerationReceipt`（七类 + 同一措辞）+ `wp_generate_file.create_template_workpaper`（链路 / IPO / B60 共用：单码保存点、落文件失败回滚该码删文件进 failures、不计新建）；链路：自定义程序与科目匹配码一起经 `plan_generation`、读失败只回滚这次读、子底稿只给在库主底稿建且同样判定；模板集 `header_unfilled`；按编码 / 准则转换 / 自定义单张与批量进回执；前端 `workpaperGenerateResult` + 链路步回执提示 + B60 保存提示 + 批量弹窗明细
  - 测试：`test_generation_receipt.py`（7）+ `test_generation_entries_retention.py` 新增 5 例；变异后端 B1~B21、前端 F1~F10 全红
- [x] 3.2 R12 删除人员 admin + 409 / 确认撤权 + 前端二次确认；委派 422 文案
  - `staff_removal_service.remove_staff`（409 列项目；确认后同事务软删分配、账号在该项目再无别的分配才撤成员行、逐项目递增策略版本）；`require_staff_active_user` 三种原因（档案已删 / 没关联账号 / 账号停用或删除，账号停用原先能委派）；前端 `useStaffDelete`（`_silent` + 确认 + 重试）、删除入口只对 admin 显示
  - 测试：`test_staff_removal_and_delegate_account.py`（5）+ `test_program_chain_hardening_batch3_pg.py`（真库策略版本 + 失效通知）+ `useStaffDelete.spec.ts`；变异 C1~C7、C12、G1~G4 全红
- [x] 3.3 R13 prepare_row_tasks 窄化与就绪标记；公开 load_wp_indexes
  - 只接 `SQLAlchemyError / HTTPException / ValueError / LookupError`，失败 `ready=False` 且计数清零；预览回执 `preparation_ready`；`load_wp_indexes` 公开（保留私有别名）；前端预览未就绪提示
  - 测试：`test_delegation_prepare_readiness.py`（10）+ PG 2 例（真库保存点回滚后计数为 0 / 程序错误抛出）；变异 C8~C11、C10b、C13、G5 全红
- [x] 3.4 R14 存量文件 dry-run 报告工具（只跑 dry-run，报告给用户）
  - `workpaper_file_backlog`（分类 / 汇总 / 处理）+ `scripts/fix/report_workpaper_file_backlog.py`（默认只读；`--apply` 须 `--confirm` 且一次一个项目）；测试 4 例，变异 D1~D7 全红
  - 真库 dry-run（主树代码）：在用底稿 3451 = 自己的文件 1056 / 没有路径 2075 / 旧占位 171 / 指向模板 81 / 文件缺失 68 / 越界 0；可处理 2327（5 份只需回写路径）；`--apply` 未执行，待用户放行
  - 🔴 事故（已恢复）：变异 D6 去掉 `--confirm` 校验时，用例的子进程按默认配置连上真库跑了 `--apply`，3364 份底稿 `file_path` 被改成 worktree 存储路径；按脚本自己写的备份逐行条件恢复（3364 / 0 残留 / 0 不符），落到 worktree 的 3364 个文件已删，备份与恢复快照留档；用例改为子进程指向临时空库（design §10.3）
- [x] 3.5 批 3 测试 + 变异、回归、浏览器实测、提交推送
  - 基线前移：远端在本批期间多了 2 个提交（97b3534c2，139 个文件），与本批 44 个文件零重叠，worktree 带着改动前移后全部重跑
  - 回归（97b3534c2 干净检出对照）：后端链路 105 文件 12 红 = 基线 101 文件 12 红逐条相同（2414 / 2384 passed）；PG 32 文件 1 红 + 3 错误 = 基线 31 文件逐条相同（378 / 375 passed）；守卫 18 文件 9 红 = 基线逐条相同；前端 142 文件 24 红 = 基线 139 文件 24 红逐条相同；单区域 vue-tsc 本批 17 个前端文件 0 条（补修 `useStaffDelete.spec` 两处类型）
  - 浏览器（chrome-devtools 独立上下文，admin）：【测试】公式同步甲 E1 第 23 行委派给没关联账号的【测试】人员 ⇒ 只弹一次「委派预览：所选人员「【测试】删除确认人员」没有关联登录账号…」；人员档案删除该人员 ⇒ 确认 → 409 二次确认写明项目与撤销范围 → 「撤销分配并删除」⇒「已删除」，项目团队分配为空，库里档案与分配均已软删；实测补修 2 处见 design §10.5（变异 S1~S3、H1 / H2 全红）
  - 未在浏览器测：模板集 / 按编码生成的回执提示 —— 测试项目只有 1 份底稿，模板集 1025 个编码会真实建约千份底稿，平台没有底稿删除端点；由 `test_generation_receipt` / `test_generation_entries_retention` / PG 用例与前端回执用例覆盖
  - 对账：PG 回归前后真库没有新增测试工厂数据（`proj_` / `staff_` 最晚仍是 10-25）

## 4. 批 4：请求收敛与工程化

- [x] 4.1 R15 chip 批量解析；R16 项目 / 详情共享在途；R17 轮询降频
  - R15：`useAcnr.resolveIndexBatched`（微任务末尾合并、去重、每批 ≤50 调 `/resolve-batch`、同键在途共享、缓存纪元变了不回写）；`GtIndexChip` 改用它，`disabled` 不解析，批量失败显示「暂时无法校验，仍可点击尝试跳转」；测试 `GtIndexChip.batch.spec.ts`（7）+ `GtIndexChip.spec.ts`；变异 R15a~j 全红
  - R16：apiProxy 对只带 `_silent` / `_dedupe` 的 GET 也共享在途（静默的可并入任何在途请求，有提示的只并入同类）；`auditPlatformApi.getProject` 经 apiProxy；`stores/project.syncFromRoute` 只取一次详情；测试 `apiProxy.inflightShare.spec.ts`（9）+ `project.syncFromRoute.fetchOnce.spec.ts`（4）；变异 R16a~g 全红
  - R17：`composables/useAdaptivePoll`（处理中 5 秒 / 空闲 30 秒 / 页面隐藏暂停 / `poke` / 作用域销毁即停）供 ThreeColumnLayout 与 DetailProjectPanel 共用；提交导入后经 `ledger-import:submitted` 立即刷新；测试 `useAdaptivePoll.spec.ts`（8，含源码守卫）+ `DetailProjectPanel.importPoll.spec.ts`（3）；变异 R17a~i 全红
- [x] 4.2 R18 生命周期事件表（迁移 + 模型 + 写入 + 回收站读取）
  - V207 / R207 `workpaper_lifecycle_events`（只对 projects 建外键、CHECK 事件类型、只追加触发器复用 V115 的 `wp_visibility_forbid_mutation()`）+ 模型 `WorkpaperLifecycleEvent`；移入 / 恢复同事务在保存点里写事件（只在表不存在时降级为警告，见 design §11.1）；回收站「删除人」先读事件，旧数据回退去向 JSON
  - 测试：`test_workpaper_lifecycle_events.py`（SQLite 开外键，6）+ `test_workpaper_lifecycle_events_pg.py`（事务里执行 V207 本身，3）；变异 E1~E12、E3pg 全红
  - 🔴 真库还没有这张表（开发服热重载不跑迁移）：下次全量重启 start-dev 才建；在那之前不记事件、回收站回退 JSON、`/api/health` 因 orm_extra 报 degraded（状态码 200，前端不读这一项）
- [x] 4.3 R19 显式门禁（✅ 随批 2：路由自带底稿门、注册表不重复挂，变异 B2-15/16 全红）；R20 PG 必跑开关
  - R20：`GT_REQUIRE_PG=1` 而地址不是 PG、又收集到 pg_only 用例 ⇒ `pytest.UsageError`；识别 `postgres://`（`tests/_pg_url.py`，`_factories.IS_PG` 同用）；本 spec 涉及外键的 4 个 SQLite 用例文件开外键（`tests/_sqlite_fk.py`）；测试 `test_pg_requirement_guard.py`（18，子进程收集）；变异 F1~F6 全红
- [x] 4.4 R21 跨角色接口级 PG 用例 + Playwright 可重放脚本
  - `tests/procedure_chain_e2e/test_cross_role_chain_pg.py`：真实应用 + 回滚事务，admin / 经理 / 审计员走「生成 → 粗裁（移入回收站 + 事件 + 删除人）→ 再生成跳过 → 审计员不能裁剪 / 委派 → 委派 → 可见（列表 / 详情 / 渲染配置）→ 编辑锁（409 带持有人、只有持有人能释放）→ 恢复执行 → 再生成按已存在 / 新建分流」；文件落临时目录，跑完真库无孤儿行；变异 11 条全红（生成 2 / 粗裁 3 / 可见 3 / 编辑锁 1 / 事件 2）
  - `e2e/procedure-chain-cross-role.spec.ts`：`GT_E2E_*` 指定【测试】项目与账号；未配置整组跳过（实测 6 skipped）；项目名不含【测试】在任何写入前拒绝（实测：admin 指向重药安徽）；中途失败收尾恢复粗裁；单文件 tsc 0 条（注入 TS2322 打红）
  - 未实跑完整重放：真库没有带团队（经理 + 审计员账号）的【测试】项目，可用账号只有 admin（ptgd_auditor 停用、无人员档案）；实跑需新建两个测试账号与团队分配，待用户放行
- [x] 4.5 批 4 测试 + 变异、回归、浏览器实测（请求数前后对比）、提交推送
  - 回归（e36cf246d 干净检出对照）：后端链路 110 文件 12 红 = 基线 108 文件逐条相同（2444 / 2420 passed）；PG 35 文件 1 红 + 3 错误 = 基线 33 文件逐条相同（399 / 395）；守卫 25 文件 13 红 = 基线逐条相同（新加 7 个迁移 / 模型守卫，其中红的 4 个基线同红）；前端 281 文件 32 红 = 基线 276 文件逐条相同，新增 5 个用例文件 31 例全绿；按引用补跑 321 个用例文件 21 红 = 基线逐条相同；单区域 vue-tsc 19 个文件 1845 条 = 基线 1845、新增 0（注入 TS2322 打红）
  - 浏览器（【测试】公式同步甲 E1 编辑页，15~20 秒窗口，前后对比）：ACNR 56 次单条解析（28 次被取消）→ 1 次批量（28 项）0 取消；误灰芯片 8 → 2（剩下 A1-15 / A1-16 真不存在）；项目详情 4 → 3；导入队列轮询 15 秒 5 次 → 20 秒 1 次；render-config 3 → 3（有提示的调用方不并入静默在途，设计如此）；无控制台错误

## 5. 批 5：Java 契约

- [x] 5.1 R22 十个 JSON Schema + README（状态机 / 错误码 / 事务边界 / 鉴权口径）
  - `docs/contracts/procedure-chain/`：11 份契约 + `common`（2020-12，`$id` 带 `v1`，不写 `$schema`）；`cases/` 6 份共享用例（粗裁判定 3 组、生成分流 2、程序行身份 29 条、成员范围 10 + 常量、任务状态机 31、存量分类 8）；`README.md`（文件、校验方式与 Java 侧前缀映射、粗裁判定、回执措辞、状态机表、委派、鉴权口径、事务边界、错误码、已知差异）；`docs/README.md` 目录加 `contracts/`
  - Python 侧序列化：`TrimmedScope.decide / to_payload`、`GenerationPlan / MemberScope / BacklogRow.to_payload`；转派历史 / outbox 的 `from_status` 改记转派前的真实状态（design §12.1）
- [x] 5.2 R23 契约测试（真实响应校验 + schema 自检 + 变异）；OpenAPI 子集导出 `--check`
  - `tests/contracts/test_procedure_chain_contracts.py`（65）：schema 集合固定、2020-12 自检、`$id` 与 `$ref` 可解析；共享用例逐条跑 Python 实现（状态机 31 条经真实转换服务，失败零副作用）；服务层产物（生成回执、生命周期事件与旧去向记录、任务历史与 outbox、存量分类与汇总）按 schema 校验
  - `tests/procedure_chain_e2e/test_procedure_chain_contracts_pg.py`（2，真库回滚事务）：按编码 / 模板集生成、粗裁预览与应用、委派预览与应用（原子 / best_effort / 冲突 409 / 跨循环 400 与带理由重试）、程序行归属、覆盖值批量、422 与信封，以及同事务落库的事件 / 定义 / 任务 / 历史 / outbox 按 schema 校验；跑完真库无孤儿行、无残留模板集
  - `scripts/gen/export_procedure_chain_openapi.py` → `openapi.procedure-chain.json`（8 个接口、10 个组件）；`tests/contracts/test_procedure_chain_openapi.py`（5）：重跑写回与仓库文件逐字节相同、`--check` 不写且逐处列出差异、结构与引用全可解析、请求模型 ⇔ 契约请求逐层一致（比对器自检三种漂移）、子集规则、只在内容变化时写（不计行尾）
  - 变异 28 条全红：契约实现 9（回执字段、同码多行、摘要位数、程序号、主管角色、转派前态、范围排序、单码判定、存量字段）、真实响应 9（预览前置标志、行归属、覆盖值失败项、扩权回执、拒绝体、422 体、事件 trim_codes、模板集 count、冲突体）、OpenAPI 10（路由改名、请求模型加字段 2、契约请求多字段、data 不挂契约、行尾、差异符号、闭包、命名、--check 写盘）
- [x] 5.3 批 5 回归、提交推送
  - 回归（709b21275 干净检出对照）：后端链路 112 文件 12 红 = 基线 108 文件逐条相同（2514 / 2420 passed，多出的 70 = 新契约用例）；PG 36 文件 3 红 + 3 错误 = 基线 33 文件逐条相同（399 / 393 passed）；守卫 25 文件 13 红 = 基线逐条相同；批 5 没有前端改动；行数门通过（转换服务登记白名单 919）

## 6. 收尾

- [x] 6.1 INDEX / memory / dev-history；清理探针、临时 worktree 与测试数据（对账）
  - 已做：INDEX / memory / dev-history（2026-10-27）；仓库内没有本 spec 的探针（一次性脚本都在仓库外 `C:\Users\Administrator\ptgd_deliver\`），临时 worktree 推送后删除
  - E1 第 23 行测试数据已清理（2026-10-27 验证：四张表全 0 行，`cleanup_e1_row23.py` dry-run 报「已清理过，无事可做」），备份在 `C:\Users\Administrator\ptgd_deliver\cleanup_20261027/backup.json`
