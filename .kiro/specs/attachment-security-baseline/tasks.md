# 实施计划：附件安全底线（attachment-security-baseline）

> 每个任务是一个可独立测试的交付单元，引用 `需求 X.Y` / `ADR-ASB-NN` / 变异 `#N`（design §6），不复述。
> 通用纪律：后端测试 `rtk ..\.venv\Scripts\python.exe -m pytest <文件> -q -p no:playwright`（cwd = `backend`）；一次性脚本、变异备份、截图只放仓库根 `tmp_attachment_security_baseline/`；磁盘变异单独一条命令跑、逐字节恢复后 sha256 核对；不碰附件溯源三端点（design §1）；提交前核对暂存区只含本 spec 文件。
> 验证汇总见 design §8；变异结果见 design §6。

- [x] 1. 上传策略与服务层接线（需求 1.1–1.5，ADR-ASB-01/02）
  - 新建 `services/attachment_upload_policy.py`；`attachment_service.py` 两个入口校验、`_write_local_file` 根校验、`create_attachment` 写 actor 与 audit_year；`routers/attachments.py` 上传 / 创建传身份并把拒绝映射为 422
  - `backend/scripts/file_size_whitelist.txt` 登记 `attachment_service.py`（现值，写明拆分轴）
  - 测试 `tests/attachment_security_baseline/test_upload_policy.py`：穿越类型 422 且根外无文件、无行；扩展名白名单与 `ACCEPT_TYPES` 逐项一致；可执行签名 422；身份与年度写入；前端 `attachment_type` 字面量与证据声明类型都在枚举内
  - 记录：13 例绿；变异 #1 红在穿越与 422 用例；白名单登记 HEAD 值 1391，现 1432（门限 +5% 即 1460）

- [x] 2. 旁路目录统一函数（需求 1.6，ADR-ASB-07）
  - 新建 `services/workpaper_side_storage.py`；26 个端点替换（codemod 放 tmp 目录，替换后逐文件 diff 核对）
  - 测试 `test_side_storage_wp_id.py`：AST 守卫（无原始 wp_id 拼路径、无 `UUID(int=0)`）；`d4/contract-ocr` 与一个原「无校验」端点传非 UUID ⇒ 400、目录未创建、OCR 未被调用
  - 记录：25 个文件 26 处替换，24 个 OCR 策略文件去掉无用 `UUID` 导入；33 例绿；5 个旧用例改用 UUID 底稿 id（原用 `test-wp-id` 依赖全零兜底）；变异 #6、#6b 红

- [x] 3. 函证路由级门（需求 2.1、2.2，ADR-ASB-03）
  - 新建 `services/confirmation_scope_gate.py`；`routers/confirmations.py` 挂门、角色常量移到文件头、四个端点去掉坏角色集
  - 测试 `test_confirmation_scope_authz.py`：design §5 前四行逐格；跨项目函证 / 附件 / 挂载记录 404；请求体底稿跨项目 422；审计员 edit 成员挂载回函成功
  - 记录：169 例绿；函证既有用例 82 passed / 21 xfailed；删 `_EDIT_ROLES`（不含审计员）与零引用的 `_ASSIGN_ROLES`，`_MANAGER_PLUS_ROLES` 留给回填与终态撤回；鉴权守卫登记 `confirmation_project_gate` 并配可伪证用例，前缀维基线 270 → 243；变异 #2、#3 红

- [x] 4. OCR 字段与任务端点项目校验（需求 2.3）
  - `routers/ocr_fields.py`
  - 测试 `test_ocr_fields_authz.py`：非成员 403；readonly 读缓存 200、触发识别 403；edit 触发 202；任务查询非成员 403

- [x] 5. OCR 文本完整性（需求 3.1–3.4、3.6 后端，ADR-ASB-04）
  - 迁移 V209 + R209；模型四列；新建 `services/attachment_ocr_text.py`；`routers/attachments.py` 新增 `ocr-text` / `ocr-confirm`，`ocr-status` 加 base 校验，`retry-ocr` 改为触发识别；`_to_dict` 加字段
  - 测试 `test_ocr_text_integrity.py`：全文与 sha256；截断文本或旧 base 确认 ⇒ 409 且库内不变；确认后 `ocr_confirmed` 为真、文本改写后为假；`ocr-status` 带文本无 base ⇒ 409；重试识别会调度识别；迁移 SQL 可重放
  - 记录：base 校验放在路由（design §3）；`retry-ocr` 改经 `OcrFieldsService`（原引用不存在的 `TaskType.ocr_upload`，异常被吞）；5 个手写 `attachments` 镜像 DDL 的 PG 用例补四列；变异 #4 红

- [x] 6. 破坏性操作守卫（需求 4，ADR-ASB-05/06）
  - 新建 `services/attachment_destructive_guard.py`；`routers/attachments.py` 删除 / 回滚 / 识别状态 / 重试识别 / 关联 / 解除关联；版本端点委托服务层；`routers/recycle_bin.py` 附件三条永久删除路径
  - 测试 `test_attachment_destructive_guard.py`：design §5 第五、六行；保全 423、引用 409、归档 423（含 admin 永久删除）、伪造查询参数无效；批量与清空跳过计数；回滚走服务层（版本号连续、写回滚人）
  - 记录：新建 `services/attachment_access.py`（按附件真实项目鉴权）；回滚路由按前端路径注册、删零调用方旧路由（ADR-06 勘误）；保全原生 SQL 在 SQLite 上绑定 `str(uuid)` 恒不命中，3 例只在真 PG 跑（3 passed）；变异 #5、#7 红

- [x] 7. 前端（需求 3.5、3.6）
  - `OcrConfirmDialog.vue` 打开取全文、确认走新接口、409 提示；`AttachmentManagement.vue` 重试识别；`apiPaths/system.ts`
  - vitest：弹窗显示接口返回的全文而非预览、确认请求带 base；单区域 vue-tsc 只查改动文件并配一条类型错误变异
  - 记录：新增 `ocrTextApi.ts`；`BatchUploadResultDialog.vue` 同类截断一并修；变异 #8 红

- [x] 8. 变异证明（需求 5.2）
  - design §6 的 8 条逐条跑，记录红在哪条断言、恢复后 sha256
  - 记录：13 条（含 6b 与任务 12 的 9–12）全红在预期断言，恢复后 sha256 一致

- [x] 9. 全仓守卫与棘轮（需求 5.3）
  - 鉴权三维守卫、行数门、lazy import、函数全局名棘轮、证据边界、底稿关联波次、函证与回收站既有用例；`scripts/fix/resync_data_line_anchors.py --check`；棘轮常量按现算调整并写入本条
  - 记录：前缀维基线 `_PREFIXED_IDENTITY_ONLY_BASELINE` 270 → 243；`routers/attachments.py::_ensure_project_access` 的请求体维证明链改为要求 `assert_project_permission`；`test_project_endpoint_authorization_baseline.py` 现 857 行（白名单 821 未改，门限 862）；锚点「均无需平移」；扩大回归 856 passed，失败与错误在纯 HEAD 上逐条复现（design §8）

- [x] 10. 共享库迁移与走查（需求 5.4）
  - `MigrationRunner(...).run_pending()` 应用 V209；【测试】项目上接口走查 + 浏览器走查（附件管理页上传、写入长识别文本、弹窗全文、确认、刷新）；走查数据走平台路径清理并逐表对账
  - 记录：私有实例 9987 / 3037，未动共享 9980 / 3030；走查发现原件区 401 与文本框盖住按钮 ⇒ 新增任务 12；修复后全流程通过，库内全文 3607 字、确认 sha256 与全文一致；清理后附件 / 版本 / 关联 0 行，项目软删（design §8）

- [x] 11. 收尾
  - 评估报告追加勘误节；`.kiro/specs/INDEX.md` 登记；按工作区规则提交并推送（fetch 先行、只暂存本 spec 文件）

- [x] 12. 浏览器原生加载带不上令牌一类收口（走查中发现，ADR-ASB-09）
  - 新建 `composables/useAuthedObjectUrl.ts`、`components/attachment/downloadAttachment.ts`；18 处原生加载改走 blob: 地址或 `downloadFile`；两个弹窗文本框封顶高度
  - 测试：`useAuthedObjectUrl.spec.ts`（9 例：取数参数、竞态、释放、403 / 404 / 失败、JSON 响应、强制类型）；`OcrConfirmDialog.spec.ts` 加原件预览与布局 5 例；改写钉住旧行为的 `AttachmentPreviewOfficeIframe.spec.ts`、`task1LegacyBaseline.spec.ts`；守卫 `NativeLoadBearerGuard.spec.ts`（7 例，含扫描器自检）
  - 记录：纯 HEAD 上守卫 4 条红（13 个文件）；变异 #9–#12 红；ESLint 新增告警 0；浏览器复验原件显示与「确认入库」可点
