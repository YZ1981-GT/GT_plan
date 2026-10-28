# 设计文档：附件安全底线（attachment-security-baseline）

需求见 `requirements.md`，此处不复述。

## 1. 边界

| 不做 | 归属 |
|---|---|
| 附件溯源三端点（`/api/attachments/{id}/link`、`/links`、`/link/{link_id}`）、`attachment_lineage` 模型与 V206 | `formula-hub-integrity-closure` 任务 3/4（其 worktree 已实现） |
| 旁路存储文件转入附件表、`ItemAttachment` 改造、关联权限矩阵（编制人 assignee 不能 associate） | Spec B 证据采集单入口 |
| 函证底稿内挂附件、替代程序留档（函证附件抽屉的预览已在任务 12 改走已鉴权预览抽屉，见 ADR-09） | Spec C |
| 治理链路切换、媒体类型白名单与治理侧对齐、永久删除时清理物理文件 | Spec G |

## 2. 决策

- **ADR-ASB-01 上传白名单以前端为单一事实。** 治理侧 `ATTACHMENT_ALLOWED_MEDIA_TYPES` 比平台实际支持的格式窄（缺 eml / msg / ofd / dwg / dxf / rar / 7z / heic / webp / md），套用会让现有格式上传失败。后端新增 `ALLOWED_EXTENSIONS`，守卫逐项比对 `AttachmentManagement.vue` 的 `ACCEPT_TYPES`；恶意内容门直接复用 `build_malware_scanner()`（尊重 `ATTACHMENT_SIGNATURE_SCAN_ENABLED` / `CLAMAV_ENABLED`）。
- **ADR-ASB-02 `attachment_type` 枚举 + 落盘根校验。** 枚举放 `services/attachment_upload_policy.py`；`upload_attachment_file` 与 `create_attachment` 入口校验，`_write_local_file` 再做 resolve-in-root（两层，任一被绕过另一层仍拦）。守卫：前端写入的 `attachment_type` 字面量、证据声明 JSON 的 `type` 都必须在枚举内。
- **ADR-ASB-03 函证路由用路由级门。** `confirmations.py` 已 788 行，逐端点加校验会超行数门，也容易漏。新增 `services/confirmation_scope_gate.py::confirmation_project_gate`，挂在 `APIRouter(dependencies=[...])`：按方法定级（GET readonly，其余 edit），再核对路径参数（`confirmation_id`、`attachment_id`、`link_id`）与 JSON 请求体字段（`attachment_id`、`confirmation_id`、`paired_outbound_id`、`wp_id`、`items[*].wp_id`）都属于路径项目。FastAPI 在解依赖前已读过请求体，门里 `await request.json()` 取的是缓存。删除不含审计员的 `_EDIT_ROLES`（改由门判 edit）；`_MANAGER_PLUS_ROLES` 两处保留。
- **ADR-ASB-04 OCR 确认状态存 `attachments` 列（V211）。** 新增 `ocr_confirmed_sha256`、`ocr_confirmed_by`、`ocr_confirmed_at`、`ocr_confirmed_edited`。有效性 = `ocr_confirmed_sha256 == sha256(ocr_text)`，写入方改写文本时无需清理（不依赖所有写入方记得清）。不放 `ocr_fields_cache`：它被三个写入方整体覆盖。历史由 `AuditLogMiddleware` 的请求审计留存。
- **ADR-ASB-05 破坏性操作一个守卫模块。** `services/attachment_destructive_guard.py`：`assert_not_under_legal_hold`（节点 `attachment` + 该附件全部 `attachment_version`，复用 `RetentionLegalHoldService.authorize_destructive`，423 文案中文）、`count_references`（`attachment_working_paper`、`confirmation_attachment_link`、`evidence_links`、`attachment_lineage`、reference 指向底稿或函证）、`filter_purgeable`（批量 / 清空用，返回可删 id 与按原因计数）。归档判定复用 `deps._check_project_not_archived`（与项目权限同一实现）。
- **ADR-ASB-06 版本端点委托服务层。** 路由里的版本列表按「文件名 + reference_id（非空时）」归链、不区分 reference 类型与空值；回滚另写一份、不取链锁、不发失效信号。改为调用 `AttachmentService.list_versions(attachment_id)` / `rollback_to_version(attachment_id, version_id, created_by=…)`（服务层的「契约 1」：按附件 id 定位链）。
  - 实施勘误：前端回滚按钮请求 `POST /api/attachments/{id}/versions/{version_id}/rollback`，这条路由从未注册，按钮恒 404；路由里另有 `POST /api/attachments/{id}/rollback`，全仓零调用方。处置：删掉零调用方的旧路由，按前端路径注册新路由并委托服务层；版本列表补 `uploaded_at` / `uploaded_by` / `is_current`（弹窗读这三个字段）。
- **ADR-ASB-07 旁路目录统一函数。** 新增 `services/workpaper_side_storage.py`：`parse_workpaper_id(wp_id) -> UUID`（非法 400）、`side_storage_dir(wp_id, subdir) -> Path`（`storage/workpapers/{UUID}/{subdir}`，subdir 只许小写字母数字与连字符）。26 个端点逐个替换（codemod 后人工核对），14 处 `UUID(int=0)` 兜底改为 `parse_workpaper_id`。Spec B 把这些端点改成先建附件时继续复用。
- **ADR-ASB-08 迁移号 V211（原 V209）。** 写设计时现扫：主树最高 V205；`git log --all` 有两个 V206；formula-hub 设计预留 V206~V208 ⇒ 取 V209。提交前 fetch 发现远端已推送 `V209__widen_business_category_varchar20.sql`（s-cycle），本地 V210 已被 `voucher_identity` 占用 ⇒ 改为 V211 / R211（全部 ref 与各 worktree 现扫无 V211）。共享库此前已按 V209 应用：删掉本 spec 那条 `schema_version` 记录（version 209）后经 `run_pending()` 以 V211 重新登记（DDL 全是 `IF NOT EXISTS`，四列不重建），远端的 V209 合入后可正常执行。
- **ADR-ASB-09 浏览器原生加载一律不指向 /api（任务 12，走查中发现）。** 平台鉴权只认 Authorization 头（`deps.HTTPBearer`，没有 cookie / 查询串令牌）；iframe / img 的 src、a / el-link 的 href、`window.open` 都不经 axios ⇒ 指向 /api 恒 401。走查实测：OCR 确认弹窗原件区显示 `{"code":401,"message":"Not authenticated"}`，核对时看不到原件。
  - 全仓同类 18 处：附件模块 12 处（确认弹窗 ×2、批量结果 ×2、预览抽屉 server 分支 ×2、`ItemAttachment`、C24 / C25 / C26 / 控制测试的 📎 ×4、函证附件抽屉——它 `window.open` 的还是一条不存在的路由）；其他模块 6 处（模板详情预览、模板下载、合并透视导出、批量导出 ZIP、交付件预览「下载」、上年底稿文件）。交付件预览的「下载」是 `<el-button :href>`，el-button 渲染 `<button>`，href 不生效，原本就是点了没反应。
  - 内嵌预览用新组合函数 `composables/useAuthedObjectUrl.ts`：`api.get` 取 blob 换成 `blob:` 地址；源变化 / 作用域销毁时中止请求并释放；晚到的旧响应不覆盖；JSON 响应按失败处理；iframe 显示 PDF 时强制 `application/pdf`。下载用 `utils/http.downloadFile`，附件下载收口到 `components/attachment/downloadAttachment.ts`。
  - 不改成查询串令牌：令牌进 URL 会落浏览器历史、代理日志和 Referer。
  - 守卫 `src/__tests__/NativeLoadBearerGuard.spec.ts`：模板 src / href 与 `window.open` / `location` 的目标不得含 /api；其余调用点逐条登记来源类别（object-url 类可伪证），未登记即红。`ArchiveWizard` 的 `output_url` 后端无写入方，登记为 dormant，Spec E 接归档打包时按是否 /api 选下载方式。
  - 同批修布局回归：改为加载全文后，3607 字的文本框 autosize 到 688px，溢出布局盖住「确认入库」（走查时按钮中心 `elementFromPoint` 落在 textarea 上）。两个弹窗的文本框封顶高度、内部滚动。这是本 spec 加载全文后才暴露的问题，原来只有 200 字。

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `services/attachment_upload_policy.py`（新） | 枚举、扩展名白名单、`validate_upload`、`scan_content`、`UploadRejected` |
| `services/attachment_service.py` | 两个入口校验；`_write_local_file` 根校验；`create_attachment` 写 actor / audit_year；`_to_dict` 加 `created_by` 与 OCR 摘要字段。登记行数白名单（HEAD 值 1391，现 1432，门限 1460；历史大文件，拆分轴：版本 / Paperless / 搜索，Spec G 拆）。`ocr-status` 的 base 校验放在路由、不放 `update_ocr_status`：服务层还被内部识别写入方（带文本）调用，加在服务层会让它们全部 409 |
| `services/attachment_ocr_text.py`（新） | sha256、确认状态、`confirm_ocr_text`、`assert_base_matches`、`OcrTextConflict`（`OCR_TEXT_CHANGED`）；列表预览 200 字 |
| `services/attachment_access.py`（新） | `load_attachment`（软删按 404）、`require_attachment_permission`：按附件真实项目鉴权，委托 `assert_project_permission`（顺带归档判定与 RLS 上下文）；`routers/attachments.py::_ensure_project_access` 同样改为委托 |
| `services/attachment_destructive_guard.py`（新） | 见 ADR-05 |
| `services/confirmation_scope_gate.py`（新） | 见 ADR-03 |
| `services/workpaper_side_storage.py`（新） | 见 ADR-07 |
| `routers/attachments.py` | 上传 / 创建传身份；删除、回滚、识别状态、重试识别按真实项目鉴权 + 守卫；关联 / 解除关联归档守卫；新增 `ocr-text`、`ocr-confirm`；版本端点委托服务层 |
| `routers/confirmations.py` | 挂路由级门；角色常量移到文件头；挂载 / 解绑 / 比对 / 自动匹配 / 人工指派改 `get_current_user` |
| `routers/ocr_fields.py` | 两个端点项目校验 |
| `routers/recycle_bin.py` | 附件的永久删除三路径接守卫 |
| 26 个底稿 OCR 端点（22 个文件） | 旁路目录与 wp_id 校验 |
| `models/attachment_models.py` + `migrations/V211__attachment_ocr_confirmation.sql` / `R211__…` | 四列 |
| 前端 `OcrConfirmDialog.vue`、`BatchUploadResultDialog.vue`、`ocrTextApi.ts`（新）、`AttachmentManagement.vue`、`apiPaths/system.ts` | 取全文、确认新接口、重试识别。批量上传结果弹窗是同类截断（「确认此文件 / 全部确认」原也写回 200 字预览），同法修 |
| 任务 12（ADR-09）：`composables/useAuthedObjectUrl.ts`（新）、`components/attachment/downloadAttachment.ts`（新）、`AttachmentPreviewCore.vue`、`ItemAttachment.vue`、`C24AnomalyEntrySheet.vue`、`CControlTestSubPage.vue`、`GtC25InternalAudit.vue`、`GtC26InfoControl.vue`、`ConfirmationAttachmentDrawer.vue`、`WpTemplateDetail.vue`、`consolidationApi.ts`、`ExportProgressBar.vue`、`DeliverablePreview.vue`、`PriorYearCompareDrawer.vue` | 内嵌预览走 blob: 地址、下载走 `downloadFile`；守卫 `NativeLoadBearerGuard.spec.ts`；更新钉住旧行为的两个用例（`AttachmentPreviewOfficeIframe.spec.ts`、`task1LegacyBaseline.spec.ts` 原断言 iframe src 就是 /api 路径） |

## 4. 关键流程

- **上传**：路由读文件 → `validate_upload(file_name, attachment_type, content)`（类型、扩展名、恶意内容）→ 服务层再校验类型 → 本地落盘前根校验 → 建行（actor / audit_year）。任何拒绝在落盘与建行之前。
- **确认识别结果**：弹窗打开 `GET ocr-text` 得全文与 `sha256` → 用户核对 / 修订 → `POST ocr-confirm {base_sha256, ocr_text?}` → 服务端比对 base 与当前全文，一致才写；409 时提示「识别文本已更新，请重新打开核对」。
- **删除**：查附件（含软删判 404）→ 真实项目 edit + 归档 → 法定保全 → 引用计数 → 软删。回收站永久删除走同一组守卫。

## 5. 权限表（测试表驱动，`tests/attachment_security_baseline/`）

身份：未登录、非成员（auditor）、readonly 成员、review 成员（qc）、edit 成员（auditor）、经理（manager，edit 成员）、admin；另有项目 B 的 edit 成员与 B 的对象用于跨项目用例。

| 端点组 | 未登录 | 非成员 | readonly | review | edit 审计员 | 经理 | admin | 归档项目写 |
|---|---|---|---|---|---|---|---|---|
| 函证 GET（列表、详情、候选、匹配队列、附件列表） | 401 | 403 | 200 | 200 | 200 | 200 | 200 | — |
| 函证写（创建、更新、删除、推进、批量同步） | 401 | 403 | 403 | 403 | 200 | 200 | 200 | 423 |
| 函证附件（挂载、解绑、识别比对、自动匹配、人工指派） | 401 | 403 | 403 | 403 | 200（原 403） | 200 | 200 | 423 |
| 回填结论 | 401 | 403 | 403 | 403 | 403 | 200 | 200 | 423 |
| 附件删除 / 回滚 / 识别状态 / 重试识别 / 确认识别 | 401 | 403 | 403 | 403 | 200 | 200 | 200 | 423 |
| 附件 `ocr-text`、版本列表 | 401 | 403 | 200 | 200 | 200 | 200 | 200 | — |

跨项目：路径用项目 A、对象属于 B（函证、附件、挂载记录）⇒ 404；请求体底稿属于 B ⇒ 422。删除：保全 423、有引用 409、伪造查询参数无效。

## 6. 变异计划（磁盘变异，备份放 `tmp_attachment_security_baseline/mutations/`）

| # | 变异 | 应红用例 |
|---|---|---|
| 1 | 去掉 `_write_local_file` 根校验与入口类型校验 | 穿越用例：文件落到根外 |
| 2 | 门不核对路径对象归属 | 跨项目函证 404 用例 |
| 3 | 门对写方法也只要 readonly | readonly 写 403 用例 |
| 4 | `confirm_ocr_text` 不比对 base | 409 用例 |
| 5 | 删除不查保全 | 423 用例 |
| 6 | `parse_workpaper_id` 放行非 UUID | OCR 端点 400 用例 |
| 6b | D4 合同识别改回原始 wp_id 拼旁路目录 | AST 守卫两条 |
| 7 | 回收站永久删除不查引用 | 409 用例 |
| 8 | 前端弹窗改回用列表里的预览文本 | vitest 全文用例 |
| 9 | 确认弹窗原件区改回直接用 /api 路径当 src | vitest「blob: 地址」用例 |
| 10 | `useAuthedObjectUrl` 去掉序号判定 | vitest「源地址变化」「作用域销毁」 |
| 11 | 预览抽屉 server 分支改回 `serverPreviewUrl` 当 src | `AttachmentPreviewOfficeIframe.spec.ts` |
| 12 | C24 📎 改回 `<a :href="/api/…/download">` | 守卫 A 两条 |

实测：13 条（后端 1–7、6b，前端 8–12）全部红在预期断言上，恢复后 sha256 一致（后端 `tmp_…/mutations/report.txt`，前端 `report_frontend.txt` / `report_frontend_t12.txt`）。另把守卫单独放到纯 HEAD 上跑：4 条红、点名 13 个文件，修复后全绿（先红后绿）。

## 7. 验证

- 新测试 + 受影响既有测试（附件、函证、回收站、OCR 字段、底稿关联波次、证据边界、鉴权三维守卫、行数门、lazy import、函数全局名棘轮、line anchor 校验）。
- 前端：vitest（弹窗）、单区域 vue-tsc（改动文件）。
- 共享库：`MigrationRunner(...).run_pending()` 应用本 spec 迁移（与启动同一路径）；开发服 9980 上用【测试】项目走查接口与页面，数据走平台路径清理并对账。

## 8. 实施记录（2026-10-27）

**测试**

| 范围 | 结果 |
|---|---|
| 本 spec 后端用例 `tests/attachment_security_baseline/` | 276 passed / 3 skipped（SQLite）；跳过的 3 条（法定保全原生 SQL）在真 PG 上 3 passed |
| 函证既有用例 | 82 passed / 21 xfailed |
| 后端扩大回归（附件、回收站、OCR 字段、底稿关联波次、证据边界、鉴权三维、lazy import、函数全局名棘轮等） | 856 passed；11 failed + 8 errors 在纯 HEAD 上逐条复现（见下） |
| 前端：验证 worktree（HEAD `2fa460957` + 本 spec 84 个文件），附件 / 预览 / 合并 / 交付件 / 模板库 / 函证 / C 循环 / views 等 199 个用例文件 | 3528 passed / 14 failed；14 条在纯 HEAD 上逐条复现（见下）。`ExtendedFormatPreview` 的 CID 用例在主树并发跑时偶发红，单跑与 worktree 均绿 |
| 单区域 vue-tsc（23 个改动文件） | 改动文件 0 错误；另有 1 条 `FormulaRefPicker.vue` TS2339 不在改动范围；注入一条类型错误能报 TS2322 |
| ESLint（19 个改动源文件） | 0 error；与纯 HEAD 逐文件逐规则比，新增告警 0 |
| 行数门 / 数据锚点 / ruff | 通过 / 「锚点均无需平移」/ 改动文件 0 问题 |

**纯 HEAD 上同样失败、与本 spec 无关的用例**：后端 `test_evidence_file_path_boundary_contract` ×4（缺盘点 JSON）、`test_disclosure_note_edit_stamp`（1 failed + 8 errors）、`test_f2_stocktake_ocr_ai` AI ×2（503）、`test_g11_specs_cover_five_sheets`、K / L 底稿同步 ×3、`test_lazy_import_resolvability` ×2（引用了并发会话未入库的 5 个模块）、`test_recycle_bin_workpapers.py` 收集期 ImportError；前端 `FrontendReferenceIntegrity` ×2（11 条坏 import 全是并发会话的未入库模块）、`ConsolTrialBalanceTab` ×3 与 `ConsolReportBreakdownView` ×3（取数调用多了 `signal` 参数）、`DeliverableShortcut` ×1、`OnlyOfficeEditor` ×2、`orphanHostCoverage` ×2、`views/__tests__/composables.spec.ts` ×1。

**共享库与走查**

- 迁移经 `MigrationRunner(...).run_pending()` 落到 `audit_platform`：先按 V209 应用（待应用清单只有它），改号后删掉 version 209 记录、再以 V211 登记（ADR-08），四列已在库。
- 私有实例：后端 9987（验证 worktree 代码，`--lifespan off`）、前端 3037（独立 cacheDir、关 HMR）；没有重启共享 9980 / 3030。
- 接口走查（新建【测试】项目）：穿越类型上传 422 `ATTACHMENT_TYPE_NOT_ALLOWED`；`ocr-status` 无 base 409、带 base 200；列表预览 200 字、`ocr_text_length` 3607、`truncated` 为真；`ocr-text` 返回全文且 sha256 正确；`created_by` 为上传人；匿名请求预览 401、带令牌 200 `application/pdf`。
- 浏览器走查：修复前原件区显示 401 JSON、「确认入库」被文本框盖住点不到（`evidence/01_before_fix_preview_401.png`）；修复后原件区显示 PDF（blob: 地址）、右栏全文 3607 字、按钮可点（`evidence/02_after_fix_preview_and_full_text.png`）；确认后提示「识别结果已确认入库」，列表刷新后徽标消失，整页刷新后仍为「已完成」。库内 `ocr_text` 仍是 3607 字，`ocr_confirmed_sha256` 等于全文 sha256，`ocr_confirmed_by` 为 admin，`ocr_confirmed_edited` 为假。
- 清理走平台接口：删除附件 → 回收站永久删除 → 删除项目；对账：附件行 0、版本行 0、底稿关联 0、项目 `is_deleted` 为真（可经项目回收站恢复）。永久删除后两份物理文件仍在存储目录（Spec G 范围，已手工删除走查产物）。

**未在浏览器里验证的**：批量上传结果弹窗（本机无识别引擎，上传回执不带识别文本，弹窗不进入核对分支）；任务 12 的下载类改动（`ItemAttachment`、C24 / C25 / C26 / 控制测试 📎、函证附件抽屉、模板详情、合并透视导出、批量导出 ZIP、交付件下载、上年底稿文件）只有组件测试与守卫；版本回滚只有接口级测试。

**提交与推送**：本地分支与远端分支当时已分叉（本地领先 45、落后 29），本 spec 没有替别的会话合并两条线，而是两边各提交一份：本地分支 `16e2ee5ea`（主体）、`ddad8f8e7`（迁移改号）、`cf18e39c0`（令牌证明挪位、守卫前缀登记）；远端分支在远端头上合成一个提交 `978ba4521`，各自再加一个证据提交（本节与 `evidence/` 两张截图）。两条线上本 spec 的文件内容一致，日后合并时只有 INDEX、行数白名单、鉴权基线常量（本地 243、远端 239，差在远端另有 4 个端点改挂项目级）会碰到别人的改动。远端头上另有一条与本 spec 无关的预存红：`test_identity_only_endpoints_do_not_grow`（166 → 169，切到纯远端头同样红）。
