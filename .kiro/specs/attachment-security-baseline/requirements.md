# 需求文档：附件安全底线（attachment-security-baseline）

来源：`.agents/tasks/attachment-linkage-assessment-2026-10-27.md` 第四节 P0 四项与 Spec A。用户 2026-10-27「按建议来」。
范围：旧附件链路（在用）的上传落盘、函证附件与函证接口的项目隔离、OCR 文本完整性与确认留痕、破坏性操作守卫。治理链路切换、证据采集单入口等不在本 spec（见 design §1 边界）。

## 实施前现查（2026-10-27，修正评估报告）

| 项 | 现查结果 | 对需求的影响 |
|---|---|---|
| 回收站 | `routers/recycle_bin.py` 已登记 `attachment`：软删附件可恢复、可永久删除。评估报告「DELETE 不进回收站」不成立 | 需求 4 改为守住回收站的永久删除 |
| 永久删除 | 单条 / 批量只校 `edit`（admin 直接放行，不判归档），清空（admin）整表删软删附件；三条路径都不查法定保全、不查引用 | 需求 4.3 |
| 函证角色集 | `_EDIT_ROLES = admin/manager/partner/signing_partner/field_staff`，后两者不是 `UserRole` 取值，**审计员（auditor）不在内** ⇒ 审计员挂函证附件、解绑、识别比对、自动匹配全部 403；人工指派定义了 `_ASSIGN_ROLES` 却没用 | 需求 2.1 改按项目权限判定 |
| 治理媒体类型白名单 | `ATTACHMENT_ALLOWED_MEDIA_TYPES` 不含 eml / msg / ofd / dwg / dxf / rar / 7z / heic / webp / md，平台前端允许这些格式 | 需求 1.3 用扩展名白名单（与前端单一事实），不套治理白名单 |
| `ocr_fields_cache` | 三个写入方整体覆盖（OCR 写回、OCR 字段服务、函证比对 `_write_ocr_cache`） | 确认状态不能放这里（需求 3） |
| 行数门 | `attachment_service.py` 1391 行、`confirmation_evidence_service.py` 972 行，均超 800 且未登记白名单 | 前者登记白名单后小改；后者不改 |
| 并发 spec | `formula-hub-integrity-closure` 任务 3/4 已在其 worktree 改附件溯源三端点、模型与 V206 | 本 spec 不碰附件溯源 |
| 迁移号 | V206 已有两处占用（formula-hub WIP、另一分支 `V206__consol_scope_version_auto_record.sql`），formula-hub 设计预留 V206~V208 | 本 spec 用 V209 |

## 需求 1　上传落盘安全

1.1 `attachment_type` 只接受登记清单（现用值 `general / evidence / support / workpaper_item / confirmation / bank_statement` ∪ 证据声明类型 `voucher / contract / stocktake / note`）；其他值 ⇒ 422「不支持的附件类型」，不落盘、不建行。覆盖上传、JSON 创建与服务层内部调用。
1.2 本地落盘目标路径 resolve 后必须位于存储根内，否则拒绝（纵深防御）。
1.3 文件扩展名必须在白名单内，白名单与附件管理页 `ACCEPT_TYPES` 一致（后端为单一事实，守卫比对两边）；否则 422「不支持的文件类型」。
1.4 内容命中可执行 / 脚本签名（复用治理侧 `build_malware_scanner`，含可选 ClamAV）⇒ 422「文件内容不安全」。
1.5 上传与 JSON 创建写入 `created_by`、`actor_type='user'`、`actor_user_id`、`audit_year`（项目审计年度，取不到留空）。
1.6 26 个底稿 OCR 端点：`wp_id` 必须是合法 UUID，否则 400「无效的底稿 ID」，且不写盘、不调用 OCR 与大模型；旁路目录一律经统一函数生成（目录段为规范化 UUID）。守卫：路由代码里不再出现原始 `wp_id` 拼 `storage/workpapers` 路径，也不再出现 `UUID(int=0)` 兜底。

## 需求 2　函证附件与函证接口的项目隔离

2.1 函证路由全部端点要求本项目成员：读（GET）readonly，写（其余方法）edit（项目已归档 ⇒ 423）。挂载、解绑、识别比对、自动匹配、人工指派改按项目 edit 判定（修复审计员被拒）；回填结论与撤回终态保留「经理及以上」系统角色要求。
2.2 路径与请求体里的对象必须属于路径项目：函证 id、附件 id（挂载、识别比对、自动匹配、人工指派、回填、配对发函件）不属于 ⇒ 404；解绑的挂载记录不属于路径函证 ⇒ 404；创建 / 更新 / 批量同步里的底稿 id 不属于本项目 ⇒ 422。
2.3 `POST /api/attachments/{id}/ocr-fields`：读已有结果要求附件所属项目 readonly，会触发识别时要求 edit；`GET /api/ocr-jobs/{job_id}` 要求任务对应附件所属项目 readonly。

## 需求 3　OCR 文本完整性与确认留痕

3.1 `GET /api/attachments/{id}/ocr-text`（readonly）返回完整文本、sha256、长度与确认状态。
3.2 `POST /api/attachments/{id}/ocr-confirm`（edit）：请求带 `base_sha256`（打开核对时的全文 sha256），可带修订后的 `ocr_text`；`base_sha256` 与当前全文不一致 ⇒ 409，库内不变；一致 ⇒ 写入修订文本（若有）、状态 completed，并记录确认人、时间、确认时文本 sha256、是否修订。
3.3 `PUT /api/attachments/{id}/ocr-status` 带 `ocr_text` 时必须带一致的 `base_sha256`，否则 409；只改状态不受影响。
3.4 列表 / 详情 / 底稿反查返回 `ocr_text_length`、`ocr_text_truncated`、`ocr_confirmed`、`ocr_confirmed_at`、`ocr_confirmed_by`；`ocr_text` 仍是 200 字预览（兼容）。`ocr_confirmed` = 确认时 sha256 等于当前全文 sha256，文本被任何路径改写后自动失效。
3.5 前端识别结果确认弹窗打开时取全文、确认走 3.2；附件管理页「待确认」按 `ocr_confirmed` 显示，刷新后保持。
3.6 「重试识别」真正重新识别：`POST /api/attachments/{id}/retry-ocr` 重置状态并触发识别（不再引用不存在的任务类型）；附件管理页改调该端点。

## 需求 4　破坏性操作守卫

4.1 `DELETE /api/attachments/{id}`：按附件真实所属项目判 edit（归档 ⇒ 423），不再依赖查询参数 `project_id`；附件或其治理版本处于有效法定保全 ⇒ 423 `LEGAL_HOLD_ACTIVE`；仍被底稿、函证、证据链接、溯源引用 ⇒ 409 并列出各类引用数。三种拒绝都不改库。
4.2 附件写端点（识别状态、重试识别、版本回滚、关联、解除关联）对归档项目一律 423。
4.3 回收站永久删除附件（单条、批量、清空）：法定保全中、所属项目已归档、仍被引用的附件不删；单条返回 423 / 409，批量与清空跳过并在回执里按原因计数；对管理员同样生效。
4.4 版本列表与版本回滚委托服务层（链锁、失效信号、按 reference 类型与空值归链、写回滚人）。

## 需求 5　验收

5.1 端点级测试真发请求（只替换 `get_current_user` 与 `get_db`，判定链真实执行），按 design §5 权限表逐格断言，含「该放行的角色真能用」。
5.2 每类守卫至少一条磁盘变异打红，红在预期断言上；恢复后 sha256 核对。
5.3 鉴权与行数等全仓守卫跑通；棘轮常量按现算调整并写明。
5.4 共享库按启动同一路径执行 V209；在【测试】项目上经接口与浏览器走查：上传 → 写入长识别文本 → 弹窗显示全文 → 确认 → 刷新后不再「待确认」且库内全文未被截断。走查数据走平台路径清理并对账。
