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

- [ ] 3.1 R11 统一回执模块；链路编排逐码保存点 + plan_generation；IPO / B60 / D4；自定义单张表头；模板集未填表头计数
- [ ] 3.2 R12 删除人员 admin + 409 / 确认撤权 + 前端二次确认；委派 422 文案
- [ ] 3.3 R13 prepare_row_tasks 窄化与就绪标记；公开 load_wp_indexes
- [ ] 3.4 R14 存量文件 dry-run 报告工具（只跑 dry-run，报告给用户）
- [ ] 3.5 批 3 测试 + 变异、回归、浏览器实测、提交推送

## 4. 批 4：请求收敛与工程化

- [ ] 4.1 R15 chip 批量解析；R16 项目 / 详情共享在途；R17 轮询降频
- [ ] 4.2 R18 生命周期事件表（迁移 + 模型 + 写入 + 回收站读取）
- [ ] 4.3 R19 显式门禁（✅ 随批 2：路由自带底稿门、注册表不重复挂，变异 B2-15/16 全红）；R20 PG 必跑开关
- [ ] 4.4 R21 跨角色接口级 PG 用例 + Playwright 可重放脚本
- [ ] 4.5 批 4 测试 + 变异、回归、浏览器实测（请求数前后对比）、提交推送

## 5. 批 5：Java 契约

- [ ] 5.1 R22 十个 JSON Schema + README（状态机 / 错误码 / 事务边界 / 鉴权口径）
- [ ] 5.2 R23 契约测试（真实响应校验 + schema 自检 + 变异）；OpenAPI 子集导出 `--check`
- [ ] 5.3 批 5 回归、提交推送

## 6. 收尾

- [ ] 6.1 INDEX / memory / dev-history；清理探针、临时 worktree 与测试数据（对账）
