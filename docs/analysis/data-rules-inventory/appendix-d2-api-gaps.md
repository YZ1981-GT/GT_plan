# 附录 D2：接口缺口清单

> 由脚本生成，配合 [四、接口清单](04-api-inventory.md) 第 4.4、4.5 节阅读。

## D2.1 依赖链里没有鉴权依赖的接口（全部）

平台没有全局登录中间件（中间件只为记日志、限流解析令牌，不拦请求），所以这里的接口**不带令牌也能调用**，除非函数体内自己校验。分类与需关注的条目见正文 4.4。

| 方法 | 路径 | 处理函数 | 说明 |
|---|---|---|---|
| GET | `/api/accounting-standards` | `routers/accounting_standards.py:34` | 准则列表 |
| POST | `/api/accounting-standards/seed` | `routers/accounting_standards.py:51` | 加载种子数据（幂等） |
| GET | `/api/accounting-standards/{standard_code}/chart` | `routers/accounting_standards.py:77` | 获取准则对应的标准科目表 |
| GET | `/api/accounting-standards/{standard_code}/note-templates` | `routers/accounting_standards.py:91` | 获取准则对应的附注模版配置 |
| GET | `/api/accounting-standards/{standard_code}/report-formats` | `routers/accounting_standards.py:84` | 获取准则对应的报表格式配置 |
| GET | `/api/accounting-standards/{standard_id}` | `routers/accounting_standards.py:41` | 准则详情 |
| GET | `/api/admin/event-health` | `routers/admin_event_health.py:24` | 返回最近 100 条级联记录 + 健康统计。 |
| POST | `/api/ai-chat/dsh-llm/v1/chat/completions` | `routers/dsh_model_forward.py:62` |  |
| GET | `/api/ai/health` | `routers/ai_unified.py:23` | 统一AI+OCR+缓存健康检查 |
| GET | `/api/audit-types` | `routers/audit_types.py:20` | 审计类型列表 |
| GET | `/api/audit-types/{audit_type}/recommendation` | `routers/audit_types.py:27` | 审计类型推荐配置 |
| POST | `/api/auth/login` | `api/auth.py:18` | 用户登录，返回 access_token + refresh_token。 |
| POST | `/api/auth/logout` | `api/auth.py:60` | 登出，将 refresh_token 加入黑名单使其失效。 |
| POST | `/api/auth/refresh` | `api/auth.py:36` | 使用 refresh_token 获取新的 token 对（Token Rotation）。 |
| POST | `/api/auth/register` | `api/auth.py:76` | 用户注册（公开接口，不需要认证）。 |
| GET | `/api/cache/stats` | `routers/ai_unified.py:44` | 缓存统计 |
| GET | `/api/consol-note-sections/{standard}` | `routers/consol_note_sections.py:194` | 获取所有章节（按父章节分组的树形结构） |
| GET | `/api/consol-note-sections/{standard}/{section_id}` | `routers/consol_note_sections.py:226` | 获取单个表格节点详情（含表头和模板行） |
| POST | `/api/consolidation/minority-interest/calculate` | `routers/minority_interest.py:33` | 计算少数股东权益（仅计算，不存储） |
| POST | `/api/custom-query/cell-writeback` | `routers/custom_query.py:1540` | 高级查询不再提供写入口；保留路径让旧客户端得到可诊断的 410。 |
| POST | `/api/custom-query/writeback-confirm` | `routers/custom_query_writeback.py:51` |  |
| POST | `/api/custom-query/writeback-preview` | `routers/custom_query_writeback.py:46` |  |
| POST | `/api/custom-templates` | `routers/custom_templates.py:64` |  |
| POST | `/api/custom-templates/validate` | `routers/custom_templates.py:160` |  |
| GET | `/api/custom-templates/{template_id}` | `routers/custom_templates.py:90` |  |
| DELETE | `/api/custom-templates/{template_id}` | `routers/custom_templates.py:113` |  |
| POST | `/api/custom-templates/{template_id}/publish` | `routers/custom_templates.py:124` |  |
| POST | `/api/custom-templates/{template_id}/unpublish` | `routers/custom_templates.py:135` |  |
| POST | `/api/disclosure-notes/{project_id}/upload-history` | `routers/disclosure_notes.py:1223` | 历史附注文件（Word/PDF）上传与解析 —— **尚未实现**，恒返回机器可读 501。 |
| GET | `/api/eqcr/constants` | `routers/eqcr/constants.py:8` | 返回 EQCR 模块使用的枚举常量，供前端下拉/校验使用。 |
| GET | `/api/feature-flags` | `routers/feature_flags.py:21` | 获取所有功能开关状态（已废弃，请迁移到 /api/feature-flags-v2） |
| GET | `/api/feature-flags/check/{flag}` | `routers/feature_flags.py:31` | 检查单个功能是否启用（已废弃，请迁移到 /api/feature-flags-v2） |
| GET | `/api/feature-flags/maturity` | `routers/feature_flags.py:38` | 获取所有功能成熟度分级（已废弃，请迁移到 /api/feature-flags-v2） |
| GET | `/api/forum/posts` | `routers/forum.py:31` |  |
| DELETE | `/api/forum/posts/{post_id}` | `routers/forum.py:64` |  |
| GET | `/api/forum/posts/{post_id}/comments` | `routers/forum.py:39` |  |
| POST | `/api/forum/posts/{post_id}/like` | `routers/forum.py:54` |  |
| GET | `/api/gt-coding/linkage` | `routers/gt_coding.py:77` | 三测联动关系 |
| POST | `/api/gt-coding/seed` | `routers/gt_coding.py:104` | 加载种子数据（幂等） |
| GET | `/api/gt-coding/template-library` | `routers/gt_coding.py:84` | 获取致同标准底稿模板库目录 |
| GET | `/api/gt-coding/tree` | `routers/gt_coding.py:70` | 编码树形结构 |
| GET | `/api/gt-coding/{coding_id}` | `routers/gt_coding.py:94` | 编码详情 |
| GET | `/api/health` | `api/health.py:46` | 检查 PostgreSQL / Redis / 迁移状态 / schema 漂移。 |
| GET | `/api/health/ledger-import` | `routers/ledger_import_health.py:133` | Sprint 10.46-10.48: ledger-import 子系统健康检查。 |
| GET | `/api/health/redis` | `routers/health_redis.py:112` | Redis 健康检查端点。 |
| GET | `/api/i18n/audit-terms/{lang}` | `routers/i18n.py:48` | 审计术语翻译 |
| GET | `/api/i18n/languages` | `routers/i18n.py:31` | 支持的语言列表 |
| GET | `/api/i18n/translations/{lang}` | `routers/i18n.py:38` | 翻译字典 |
| GET | `/api/metabase/dashboards` | `routers/metabase.py:36` | 预置仪表板列表 |
| GET | `/api/metabase/drilldown-config` | `routers/metabase.py:93` | 获取下钻路径配置 |
| GET | `/api/metabase/sql-templates` | `routers/metabase.py:73` | SQL 查询模板 |
| POST | `/api/projects/{project_id}/deliverables/onlyoffice/callback/{task_id}` | `routers/deliverable.py:1784` |  |
| GET | `/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/signed-download` | `routers/deliverable.py:1908` | OnlyOffice 专用免认证下载（通过 HMAC 签名验证，10 分钟有效） |
| PUT | `/api/projects/{project_id}/procedures/assign` | `routers/procedures.py:530` | 已下线：底稿主编写入口统一为 PUT /api/projects/{pid}/workpaper-l |
| PUT | `/api/projects/{project_id}/procedures/instance/{procedure_id}/execution` | `routers/procedures.py:558` | 已下线：执行进度是程序行任务真源，只走 ProcedureRowTask 状态机 transitio |
| POST | `/api/projects/{project_id}/procedures/{cycle}/apply-scheme` | `routers/procedures.py:546` | 已下线：参照项目必须读源项目当前 wp_code/status 构造 canonical entri |
| POST | `/api/projects/{project_id}/procedures/{cycle}/batch-apply` | `routers/procedures.py:552` | 已下线：批量套用改为逐目标项目调用 canonical preview/apply（真实 appli |
| PUT | `/api/projects/{project_id}/procedures/{cycle}/trim` | `routers/procedures.py:181` | 已下线：粗裁写入口统一为 procedure-trim/preview\|apply（canonic |
| POST | `/api/projects/{project_id}/wp-mapping/assign/{wp_code}` | `routers/wp_mapping.py:219` | 已下线（410）：按姓名写 ``working_paper.assigned_to``（用户 id  |
| POST | `/api/system/dicts/{dict_key}/items` | `routers/system_dicts.py:684` | 拒绝新增枚举项 — value 由代码硬编码（DT-3 / D13 ADR）。 |
| DELETE | `/api/system/dicts/{dict_key}/items/{item_value}` | `routers/system_dicts.py:697` | 拒绝物理删除枚举值 — 已被代码引用不可删（DT-3 / D13 ADR）。 |
| GET | `/api/t-account-templates` | `routers/t_accounts.py:175` | 静态模版清单（不含任何项目数据，无需项目鉴权）。 |
| PUT | `/api/template-library-mgmt/cross-wp-references/{ref_id}` | `routers/template_library_mgmt.py:306` | 拒绝对 JSON 类资源的直接编辑（D13 ADR + Property 17）。 |
| PUT | `/api/template-library-mgmt/prefill-formulas/{wp_code}` | `routers/template_library_mgmt.py:258` | 拒绝对 JSON 类资源的直接编辑（D13 ADR + Property 17）。 |
| DELETE | `/api/template-library-mgmt/prefill-formulas/{wp_code}` | `routers/template_library_mgmt.py:271` | 拒绝删除（D13 ADR + Property 17）。 |
| GET | `/api/version` | `main.py:163` |  |
| GET | `/api/workpaper-sync/rooms/{room_id}/contents` | `routers/wp_sync_router.py:1503` | OO `document.url` 消费方：短 TTL token → representation |
| POST | `/api/workpaper-sync/rooms/{room_id}/onlyoffice-callback` | `routers/wp_sync_router.py:2988` | DocServer 回调。**只**委派 Task 22 的 `CallbackDeliverySe |
| GET | `/api/workpapers/onlyoffice/health` | `routers/wp_onlyoffice_router.py:528` | 底稿模块 OnlyOffice 健康预检。 |
| GET | `/api/workpapers/render-registry` | `routers/wp_render_registry.py:31` | 返回完整注册表（含 render_types + entries） |
| GET | `/api/workpapers/render-registry/{wp_code}` | `routers/wp_render_registry.py:40` | 查找单个 wp_code 的注册信息 — 转发至 ACNR resolve 统一出口。 |
| POST | `/api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-callback` | `routers/wp_onlyoffice_router.py:1232` | OnlyOffice 编辑回调端点。 |
| GET | `/api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents` | `routers/wp_onlyoffice_router.py:1004` | WOPI GetFile — JWT 鉴权后返回 xlsx 内容。 |
| GET | `/api/wp-template-metadata` | `routers/wp_template_metadata.py:28` | 查询模板元数据（支持按阶段/组件类型/循环筛选） |
| POST | `/api/wp-template-metadata/seed` | `routers/wp_template_metadata.py:68` | 加载种子数据到 wp_template_metadata 表（幂等） |
| GET | `/api/wp-template-metadata/{wp_code}` | `routers/wp_template_metadata.py:53` | 获取单个底稿的模板元数据 |
| POST | `/api/wp-template-overrides/edit-sessions/{session_id}/callback` | `routers/wp_template_override_router.py:404` | OnlyOffice 保存回调 —— 把编辑结果落成新的覆盖版本。 |
| GET | `/api/wp-template-overrides/edit-sessions/{session_id}/contents` | `routers/wp_template_override_router.py:383` | DocServer 拉取工作副本。**机对机，不带 Bearer。** |
| GET | `/docs` | `core/openapi_runtime.py:94` |  |
| GET | `/livez` | `api/probes.py:86` | 存活探针：只要事件循环能响应即 200。不查 DB/依赖。 |
| GET | `/metrics` | `main.py:174` | Prometheus /metrics 端点（F16 / Sprint 4.10）。 |
| GET | `/openapi.json` | `core/openapi_runtime.py:83` |  |
| GET | `/readyz` | `api/probes.py:92` | 就绪探针：draining→503 / unhealthy 或迁移未完成→503 / 否则 200。 |
| GET | `/redoc` | `core/openapi_runtime.py:97` |  |
| POST | `/wopi/ds-callback/{file_id}` | `api/wopi.py:430` | Document Server 保存回调端点（向后兼容）。 |
| GET | `/wopi/files/{file_id}` | `api/wopi.py:115` | CheckFileInfo — 返回文件元信息 JSON。 |
| POST | `/wopi/files/{file_id}` | `api/wopi.py:238` | Lock/Unlock/RefreshLock — 通过 X-WOPI-Override 头区分操作 |
| GET | `/wopi/files/{file_id}/contents` | `api/wopi.py:161` | GetFile — 返回文件二进制内容。 |
| POST | `/wopi/files/{file_id}/contents` | `api/wopi.py:192` | PutFile — 接收原始字节并保存文件内容。 |
| GET | `/wopi/health` | `api/wopi.py:363` | WOPI 服务健康检查 — 前端用于探测在线编辑可用性 |

## D2.2 前端源码里写了、后端找不到同形接口的路径

按路径形状匹配（模板变量记 `{}`）。可能是废弃的路径常量，也可能是调用就 404；拼接出来的路径也会落到这里，需要逐条确认。

| 前端路径（模板变量记 `{}`） | 出现的文件 |
|---|---|
| `/api/...` | `composables/useFormSubmit.ts` |
| `/api/_debug/a51-content-revision` | `components/workpaper/GtA51CashflowAudit.vue` |
| `/api/ai-chat/attachments/{}/status` | `components/ai/ChatAttachmentPicker.vue` |
| `/api/ai-chat/doc/{}/{}/history{}` | `composables/useDocAiChat.ts`、`composables/usePlatformAiChat.ts` |
| `/api/ai/analytical-review` | `services/apiPaths/system.ts` |
| `/api/ai/chat/file-analysis` | `services/apiPaths/system.ts` |
| `/api/ai/chat/folder-analysis` | `services/apiPaths/system.ts` |
| `/api/ai/chat/knowledge` | `services/apiPaths/system.ts` |
| `/api/ai/chat/knowledge/search` | `services/apiPaths/system.ts` |
| `/api/ai/chat/knowledge/{}` | `services/apiPaths/system.ts` |
| `/api/ai/chat/message` | `services/apiPaths/system.ts` |
| `/api/ai/chat/message/stream` | `services/apiPaths/system.ts` |
| `/api/ai/chat/sessions` | `services/apiPaths/system.ts` |
| `/api/ai/chat/sessions/{}` | `services/apiPaths/system.ts` |
| `/api/ai/evaluate` | `services/apiPaths/system.ts` |
| `/api/ai/models` | `services/apiPaths/system.ts` |
| `/api/ai/models/{}/activate` | `services/apiPaths/system.ts` |
| `/api/ai/nl/analyze-file` | `services/apiPaths/system.ts` |
| `/api/ai/nl/analyze-folder` | `services/apiPaths/system.ts` |
| `/api/ai/nl/analyze-folder/{}` | `services/apiPaths/system.ts` |
| `/api/ai/nl/compare-pbc` | `services/apiPaths/system.ts` |
| `/api/ai/nl/execute` | `services/apiPaths/system.ts` |
| `/api/ai/nl/parse` | `services/apiPaths/system.ts` |
| `/api/ai/note-draft` | `services/apiPaths/system.ts` |
| `/api/ai/ocr/batch-upload` | `services/apiPaths/system.ts` |
| `/api/ai/ocr/task/{}` | `services/apiPaths/system.ts` |
| `/api/ai/workpaper-review` | `services/apiPaths/system.ts` |
| `/api/audit-log/event` | `components/workpaper/PriorYearCompareDrawer.vue` |
| `/api/audit-logs` | `services/apiPaths/system.ts` |
| `/api/audit-programs/programs/{}/coverage-report` | `services/apiPaths/system.ts` |
| `/api/audit-programs/programs/{}/procedures/{}` | `services/apiPaths/system.ts` |
| `/api/audit-programs/programs/{}/procedures/{}/link-workpaper` | `services/apiPaths/system.ts` |
| `/api/audit-programs/projects/{}/audit-programs` | `services/apiPaths/system.ts` |
| `/api/audit-programs/projects/{}/procedures` | `services/apiPaths/system.ts` |
| `/api/audit-report` | `components/workpaper/WorkpaperWordEditor.vue` |
| `/api/auth/me` | `services/apiPaths/system.ts` |
| `/api/auto-data/d7_ledger_analysis` | `components/workpaper/composables/useD7Analysis.ts` |
| `/api/b50/risk-rows` | `services/commonApi.ts` |
| `/api/confirmations/{}/confirmations` | `services/apiPaths/collaboration.ts` |
| `/api/confirmations/{}/confirmations/{}` | `services/apiPaths/collaboration.ts` |
| `/api/confirmations/{}/confirmations/{}/letter` | `services/apiPaths/collaboration.ts` |
| `/api/confirmations/{}/confirmations/{}/result` | `services/apiPaths/collaboration.ts` |
| `/api/confirmations/{}/summary` | `services/apiPaths/collaboration.ts` |
| `/api/custom-templates/{}/copy` | `services/apiPaths/workpaper.ts` |
| `/api/custom-templates/{}/validate` | `services/apiPaths/workpaper.ts` |
| `/api/d4/contract-ocr` | `components/workpaper/composables/useD1PledgeCheck.ts`、`components/workpaper/composables/useK1VoucherOcr.ts` 等 |
| `/api/disclosure-notes/{}/{}/ai/check-consistency` | `components/notes/NoteAiSuggestionPanel.vue` |
| `/api/disclosure-notes/{}/{}/sections/{}/diff` | `components/notes/NoteVersionTreePanel.vue` |
| `/api/disclosure-notes/{}/{}/sections/{}/fork` | `components/notes/NoteVersionTreePanel.vue` |
| `/api/disclosure-notes/{}/{}/sections/{}/move` | `views/composables/noteEdit/noteEditCoverage.ts`、`views/composables/useNoteTree.ts` |
| `/api/disclosure-notes/{}/{}/sections/{}/preview-text` | `components/notes/NoteParagraphVarsEditor.vue` |
| `/api/disclosure-notes/{}/{}/sections/{}/text-template-vars` | `components/notes/NoteParagraphVarsEditor.vue` |
| `/api/disclosure-notes/{}/{}/sections/{}/version-tree` | `components/notes/NoteVersionTreePanel.vue` |
| `/api/disclosure-notes/{}/{}/template-conversion/execute` | `components/notes/NoteTemplateSwitch.vue`、`composables/useNoteTemplateConversion.ts` |
| `/api/disclosure-notes/{}/{}/template-conversion/preview` | `components/notes/NoteTemplateSwitch.vue`、`composables/useNoteTemplateConversion.ts` |
| `/api/event-bus/publish` | `components/workpaper/composables/useG6MainAdjudication.ts` |
| `/api/findings/projects/{}/findings` | `services/apiPaths/system.ts` |
| `/api/findings/{}/link-adjustment` | `services/apiPaths/system.ts` |
| `/api/formula-management/import-export` | `services/apiPaths/formula.ts` |
| `/api/formula-settings` | `services/apiPaths/formulaSettings.ts` |
| `/api/going-concern/{}/evaluation` | `services/apiPaths/system.ts` |
| `/api/going-concern/{}/evaluation/{}` | `services/apiPaths/system.ts` |
| `/api/going-concern/{}/evaluation/{}/indicators` | `services/apiPaths/system.ts` |
| `/api/going-concern/{}/evaluation/{}/indicators/{}` | `services/apiPaths/system.ts` |
| `/api/going-concern/{}/init` | `services/apiPaths/system.ts` |
| `/api/group-note-baselines/diff` | `components/notes/NoteGroupBaselineDialog.vue` |
| `/api/h5/*` | `components/workpaper/h5/core/H5TabAdjustment.vue` |
| `/api/knowledge/search` | `composables/useKnowledge.ts` |
| `/api/knowledge/{分类}/{id}` | `composables/useKnowledge.ts` |
| `/api/l3-long-term-loans` | `components/workpaper/composables/useL3ImportExport.ts` |
| `/api/l4-bonds-payable` | `components/workpaper/composables/useL4ImportExport.ts` |
| `/api/l6-special-payables` | `components/workpaper/composables/useL6ImportExport.ts` |
| `/api/l7-other-noncurrent-liabilities` | `components/workpaper/composables/useL7ImportExport.ts` |
| `/api/l8-financial-expenses` | `components/workpaper/composables/useL8ImportExport.ts` |
| `/api/m1-dividends-payable` | `components/workpaper/composables/useM1ImportExport.ts` |
| `/api/m10/export-data` | `components/workpaper/composables/useM10ImportExport.ts` |
| `/api/m10/export-template` | `components/workpaper/composables/useM10ImportExport.ts` |
| `/api/m10/import-data` | `components/workpaper/composables/useM10ImportExport.ts` |
| `/api/m2-paid-in-capital` | `components/workpaper/composables/useM2ImportExport.ts` |
| `/api/m5-surplus-reserve/{}/m6-net-profit` | `components/workpaper/composables/useM5AccrualTest.ts` |
| `/api/management-letter/items/{}/follow-up` | `services/apiPaths/system.ts` |
| `/api/management-letter/projects/{}/carry-forward` | `services/apiPaths/system.ts` |
| `/api/management-letter/projects/{}/management-letter-items` | `services/apiPaths/system.ts` |
| `/api/materiality` | `components/workpaper/GtB50RiskAssessment.vue` |
| `/api/my/reminders` | `services/apiPaths/collaboration.ts` |
| `/api/my/unread-annotations/count` | `services/apiPaths/collaboration.ts` |
| `/api/n1-deferred-tax-assets` | `components/workpaper/composables/useN1ImportExport.ts` |
| `/api/n2-taxes-payable` | `components/workpaper/composables/useN2ImportExport.ts` |
| `/api/n3-deferred-tax-liabilities` | `components/workpaper/composables/useN3ImportExport.ts` |
| `/api/n4` | `components/workpaper/composables/useN4ImportExport.ts` |
| `/api/n5-income-tax-expense` | `components/workpaper/composables/useN5ImportExport.ts` |
| `/api/onlyoffice/health` | `components/workpaper/composables/useK10DualMode.ts`、`components/workpaper/composables/useK11DualMode.ts` 等 |
| `/api/pbc/{}/items` | `services/apiPaths/collaboration.ts` |
| `/api/pbc/{}/items/{}/status` | `services/apiPaths/collaboration.ts` |
| `/api/pbc/{}/pending-reminders` | `services/apiPaths/collaboration.ts` |
| `/api/projects/contracts/links/{}` | `services/apiPaths/system.ts` |
| `/api/projects/contracts/task/{}` | `services/apiPaths/system.ts` |
| `/api/projects/upload-contracts/batch` | `services/apiPaths/system.ts` |
| `/api/projects/{pid}/formula-settings` | `services/apiPaths/formulaSettings.ts` |
| `/api/projects/{pid}/formula-templates` | `services/apiPaths/formulaSettings.ts` |
| `/api/projects/{pid}/workpapers/{wpId}/formulas` | `services/apiPaths/formula.ts` |
| `/api/projects/{pid}/wp-index/by-code/N2` | `components/workpaper/composables/useN4CrossSheet.ts` |
| `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}` | `components/workpaper/sync/workpaperSyncContract.generated.ts` |
| `/api/projects/{}/account-packages/{}/confirmation-summary` | `composables/useAccountPackage.ts` |
| `/api/projects/{}/account-packages/{}/program-status` | `composables/useAccountPackage.ts` |
| `/api/projects/{}/account-packages/{}/program-status/{}` | `composables/useAccountPackage.ts` |
| `/api/projects/{}/account-packages/{}/summary` | `composables/useAccountPackage.ts` |
| `/api/projects/{}/ai-content/pending-count` | `services/apiPaths/system.ts` |
| `/api/projects/{}/ai-content/summary` | `services/apiPaths/system.ts` |
| `/api/projects/{}/ai-content/{}/confirm` | `services/apiPaths/system.ts` |
| `/api/projects/{}/archive/checklist` | `services/apiPaths/system.ts` |
| `/api/projects/{}/archive/checklist/init` | `services/apiPaths/system.ts` |
| `/api/projects/{}/archive/checklist/{}/complete` | `services/apiPaths/system.ts` |
| `/api/projects/{}/archive/export-pdf` | `services/apiPaths/system.ts` |
| `/api/projects/{}/archive/modifications` | `services/apiPaths/system.ts` |
| `/api/projects/{}/archive/modifications/{}/approve` | `services/apiPaths/system.ts` |
| `/api/projects/{}/archive/modifications/{}/reject` | `services/apiPaths/system.ts` |
| `/api/projects/{}/chat/history` | `services/apiPaths/system.ts` |
| `/api/projects/{}/confirmations/ai/address-verify` | `services/apiPaths/system.ts` |
| `/api/projects/{}/confirmations/ai/address/{}/confirm` | `services/apiPaths/system.ts` |
| `/api/projects/{}/confirmations/ai/checks` | `services/apiPaths/system.ts` |
| `/api/projects/{}/confirmations/ai/checks/{}/confirm` | `services/apiPaths/system.ts` |
| `/api/projects/{}/confirmations/ai/mismatch-analysis` | `services/apiPaths/system.ts` |
| `/api/projects/{}/confirmations/{}/ai/ocr-reply` | `services/apiPaths/system.ts` |
| `/api/projects/{}/confirmations/{}/ai/run` | `services/apiPaths/system.ts` |
| `/api/projects/{}/consol-note-mapping/rules{}` | `services/consolidationApi.ts` |
| `/api/projects/{}/contracts/summary` | `services/apiPaths/system.ts` |
| `/api/projects/{}/contracts/upload` | `services/apiPaths/system.ts` |
| `/api/projects/{}/contracts/{}/analyze` | `services/apiPaths/system.ts` |
| `/api/projects/{}/contracts/{}/cross-reference` | `services/apiPaths/system.ts` |
| `/api/projects/{}/cross-check/results{}` | `composables/useCrossCheck.ts` |
| `/api/projects/{}/documents/upload` | `services/apiPaths/system.ts` |
| `/api/projects/{}/documents/{}/extracted` | `services/apiPaths/system.ts` |
| `/api/projects/{}/documents/{}/extracted/{}` | `services/apiPaths/system.ts` |
| `/api/projects/{}/documents/{}/match` | `services/apiPaths/system.ts` |
| `/api/projects/{}/events/publish` | `components/workpaper/h2/inspection/H2TabTransferCheck.vue`、`components/workpaper/h2/interest/H2TabInterestCapNoBorrow.vue` 等 |
| `/api/projects/{}/evidence-chain/bank-analysis` | `services/apiPaths/system.ts` |
| `/api/projects/{}/evidence-chain/summary/{}` | `services/apiPaths/system.ts` |
| `/api/projects/{}/knowledge/index/build` | `services/apiPaths/system.ts` |
| `/api/projects/{}/knowledge/index/status` | `services/apiPaths/system.ts` |
| `/api/projects/{}/ledger-import/datasets/{}/force-unbind` | `services/apiPaths/accounting.ts` |
| `/api/projects/{}/ledger/cutoff-sample` | `components/workpaper/dialogs/E1CutoffDialog.vue` |
| `/api/projects/{}/ledger/entries` | `components/workpaper/composables/useD5Detail.ts` |
| `/api/projects/{}/notifications/remind-overdue` | `components/workpaper/WorkpaperLifecycleView.vue` |
| `/api/projects/{}/timeline/{}/complete` | `services/apiPaths/project.ts` |
| `/api/projects/{}/workflow/status` | `components/WorkflowDashboard.vue` |
| `/api/projects/{}/workpapers/create-from-template` | `components/workpaper/WorkpaperWordEditor.vue` |
| `/api/projects/{}/workpapers/health-dashboard` | `composables/useQualityGate.ts` |
| `/api/projects/{}/workpapers/quality-scores` | `composables/useQualityGate.ts` |
| `/api/projects/{}/workpapers/{}/ai-fill` | `services/apiPaths/workpaper.ts` |
| `/api/projects/{}/workpapers/{}/completion-rate` | `composables/useQualityGate.ts` |
| `/api/projects/{}/workpapers/{}/quality-score` | `composables/useQualityGate.ts` |
| `/api/projects/{}/workpapers/{}/upload` | `views/ProcedureTrimming.vue` |
| `/api/projects/{}/years/{}/evidence` | `composables/useReviewEvidenceDisplay.ts` |
| `/api/projects/{}/years/{}/evidence/ai` | `composables/useAiEvidenceGate.ts` |
| `/api/projects/{}/years/{}/evidence/archive` | `composables/useArchiveGovernance.ts` |
| `/api/projects/{}/years/{}/evidence/ocr` | `composables/useOcrGovernance.ts` |
| `/api/projects/{}/years/{}/evidence/refs` | `composables/useEvidenceRefs.ts` |
| `/api/projects/{}/years/{}/evidence/reviews` | `composables/useReviewGovernance.ts` |
| `/api/qc/archive-readiness` | `services/apiPaths/system.ts` |
| `/api/qc/rules/{}/versions` | `services/apiPaths/system.ts` |
| `/api/query/{preview,execute,export-excel}` | `components/custom-query/queryPayloads.ts` |
| `/api/reviews` | `services/apiPaths/workpaper.ts` |
| `/api/reviews/pending` | `services/apiPaths/workpaper.ts` |
| `/api/reviews/{}/approve` | `services/apiPaths/workpaper.ts` |
| `/api/reviews/{}/reject` | `services/apiPaths/workpaper.ts` |
| `/api/reviews/{}/start` | `services/apiPaths/workpaper.ts` |
| `/api/risk-assessments/projects/{}/overall-risk` | `services/apiPaths/system.ts` |
| `/api/risk-assessments/projects/{}/risk-assessments` | `services/apiPaths/system.ts` |
| `/api/risk-assessments/projects/{}/risk-assessments/{}` | `services/apiPaths/system.ts` |
| `/api/risk-assessments/projects/{}/risk-assessments/{}/response` | `services/apiPaths/system.ts` |
| `/api/risk-assessments/projects/{}/risk-assessments/{}/verify-coverage` | `services/apiPaths/system.ts` |
| `/api/risk-assessments/projects/{}/risk-matrix` | `services/apiPaths/system.ts` |
| `/api/sse/projects/{pid}` | `views/AttachmentManagement.vue` |
| `/api/staff/me/todos` | `services/apiPaths/collaboration.ts` |
| `/api/subsequent-events/{}/checklist` | `services/apiPaths/system.ts` |
| `/api/subsequent-events/{}/checklist/init` | `services/apiPaths/system.ts` |
| `/api/subsequent-events/{}/checklist/{}/complete` | `services/apiPaths/system.ts` |
| `/api/subsequent-events/{}/events` | `services/apiPaths/system.ts` |
| `/api/sync-conflicts/{}/detect` | `services/apiPaths/collaboration.ts` |
| `/api/sync-conflicts/{}/history` | `services/apiPaths/collaboration.ts` |
| `/api/sync-conflicts/{}/resolve` | `services/apiPaths/collaboration.ts` |
| `/api/system/dicts/version` | `utils/dictVersionCheck.ts` |
| `/api/trial-balance` | `components/formula/FormulaBar.vue`、`components/formula/StructureEditor.vue` |
| `/api/trial-balance/query` | `components/workpaper/composables/g6AdjudicationItems.ts`、`components/workpaper/composables/useG6MainAdjudication.ts` 等 |
| `/api/users/{}/private-storage/{}/download` | `services/apiPaths/system.ts` |
| `/api/workhours/batch` | `components/workhour/WorkHourExternalEntryDialog.vue`、`components/workhour/WorkHourNlpInput.vue` |
| `/api/working-papers` | `components/formula/FormulaBar.vue`、`components/formula/FormulaEditDialog.vue` |
| `/api/workpapers` | `components/workpaper/composables/useH8Impairment.ts`、`components/workpaper/composables/useI1Impairment.ts` 等 |
| `/api/workpapers/d4/contract-ocr` | `components/workpaper/confirmation/alternativeL05/GtConfirmationAlternativeL05.vue` |
| `/api/workpapers/{wpId}/{g8,g9,g10,g11,h10,l4,l5}/validate-formulas` | `services/apiPaths/formula.ts` |
| `/api/workpapers/{wp_id}/h5/*` | `components/workpaper/h5/core/H5TabAdjustment.vue`、`components/workpaper/h5/core/H5TabDetail.vue` |
| `/api/workpapers/{wp_id}/j1/export-template\|export-data\|import-data` | `components/workpaper/shared/cycleImportExportRegistry.ts` |
| `/api/workpapers/{wp_id}/{prefix}/export-data` | `components/workpaper/h5/core/H5TabDetail.vue` |
| `/api/workpapers/{}/ai/generate` | `components/workpaper/composables/useSEstimateDisclosureEventBus.ts` |
| `/api/workpapers/{}/comments/{}/replies` | `components/workpaper/GtA171ReviewPanel.vue` |
| `/api/workpapers/{}/g12/ai/adjudication-analysis` | `components/workpaper/composables/useG12Adjudication.ts` |
| `/api/workpapers/{}/g12/ai/hedge-effectiveness-conclusion` | `components/workpaper/composables/useG12FairValueTest.ts` |
| `/api/workpapers/{}/g12/ai/net-position-conclusion` | `components/workpaper/composables/useG12NetExposure.ts` |
| `/api/workpapers/{}/g12/ai/voucher-conclusion` | `components/workpaper/composables/useG12VoucherCheck.ts` |
| `/api/workpapers/{}/g13/ai/adjudication-analysis` | `components/workpaper/composables/useG13Adjudication.ts` |
| `/api/workpapers/{}/g13/ai/fv-change-conclusion` | `components/workpaper/composables/useG13Disclosure.ts` |
| `/api/workpapers/{}/g14/ai/adjudication-analysis` | `components/workpaper/composables/useG14Adjudication.ts` |
| `/api/workpapers/{}/g14/ai/impairment-conclusion` | `components/workpaper/composables/useG14Disclosure.ts` |
| `/api/workpapers/{}/h5/...` | `components/workpaper/h5/core/H5TabDetail.vue` |
| `/api/workpapers/{}/import-export/data` | `components/workpaper/s34-ipo-bundle/useS34ImportExport.ts` |
| `/api/workpapers/{}/l0/opening-balance` | `components/workpaper/confirmation/alternativeL05/GtConfirmationAlternativeL05.vue` |
| `/api/workpapers/{}/ledger/entries` | `components/workpaper/composables/useD6Detail.ts` |
| `/api/workpapers/{}/sheets/{}/lock{}` | `composables/useSheetLock.ts` |
| `/api/workpapers/{}/sheets/{}/onlyoffice-config{}` | `components/workpaper/composables/useF3DualMode.ts`、`components/workpaper/composables/useF4DualMode.ts` |
