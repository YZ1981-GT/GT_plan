# 四、接口清单

> 口径：后端接口从**运行时的应用对象**抽取（`backend/app/main.py` 的 `app.routes`，含所有路由前缀），不是按源码猜的路径；只导入应用、不启动服务、不连数据库。仓库 `.venv` 的 FastAPI 0.162.2 会把路由包在 `_IncludedRouter` 里，抽取时逐层展开（见 [03 F15](03-findings.md)）；用旧版 FastAPI 抽取的结果与之对比，总数、分域数量、鉴权分布、前端引用数全部相同。
> 前端调用情况：扫描 `audit-platform/frontend/src` 里写出的 `/api/...` 路径字面量（含模板字符串），按路径形状和后端接口匹配。
> 全部接口逐条见 [附录 D](appendix-d-api-list.md)（Excel 版 `appendix-d-api-list.csv`）；缺口清单见 [附录 D2](appendix-d2-api-gaps.md)。
> 现算日期 2026-11-18，代码基线 `dev1.0` `3a9c0db4f`。

## 4.1 总数与分布

后端共 **2676 个接口**，分布在 621 个代码文件里：GET 1147、POST 1298、PUT 117、DELETE 89、PATCH 25。（之前按源码装饰器静态数出的 2495 偏少，因为有一批接口是在注册时按循环批量挂上的。）

| 业务域 | 接口数 | 前端能找到直接引用 |
|---|---:|---:|
| D01 用户、组织与权限 | 95 | 92 |
| D02 项目与项目管理 | 141 | 126 |
| D03 账表导入与数据集 | 96 | 76 |
| D04 科目映射与试算表 | 109 | 75 |
| D05 调整分录与错报 | 112 | 64 |
| D06 报表、审计报告与交付件 | 169 | 139 |
| D07 附注 | 135 | 125 |
| D08 公式、取数与查询 | 173 | 140 |
| D09 底稿（含各循环底稿的专用接口） | 804 | 515 |
| D10 底稿在线编辑同步 | 52 | 15 |
| D11 合并 | 177 | 160 |
| D12 附件、证据、函证与归档 | 130 | 94 |
| D13 复核、质控与签字门禁 | 186 | 160 |
| D14 AI 与知识库 | 191 | 116 |
| D15 后台任务与基础设施 | 106 | 82 |
| **合计** | **2676** | **1979** |

- 业务域按接口所在的路由文件名和路径归类，个别接口的归属可以商榷。
- 「前端能找到直接引用」= 前端源码里能找到同形路径。剩下 697 个找不到，原因有三种：路径是拼接出来的；由 OnlyOffice 等外部服务回调（D10 大部分属于这种）；确实没人调用。
- 底稿占 804 个，大头是各循环底稿（D1~N5 等）各自的导入导出、计算、校验、AI 生成接口，例如 `_cycle_import_export_common.py` 一个文件就挂了 105 个。

## 4.2 鉴权方式

| 鉴权依赖 | 接口数 | 含义 |
|---|---:|---|
| `get_current_user` | 2566 | 只要求登录 |
| `dedicated_wp_gate` | 813 | 底稿专用门：校验该底稿所属项目的权限 |
| `require_project_access(级别)` | 723 | 项目级权限（readonly / edit / review） |
| `require_role` | 118 | 系统角色（如只许 admin / partner） |
| `get_current_user_stream` / `require_project_access_stream` | 93 / 16 | 流式接口（SSE）的登录与项目权限 |
| `check_consol_lock` | 65 | 合并锁定期间禁止写 |
| `require_note_edit_access` | 36 | 附注编辑权限 |
| 其他（`require_project_permission`、`confirmation_project_gate`、`require_project_delegator` 等） | 少量 | — |

一个接口可以同时带几种依赖，所以合计大于 2676。另有 **90 个接口依赖链里没有任何鉴权依赖**，见 4.4。

## 4.3 主链路的关键接口

按 [02 规则清单](02-rules.md) 的链路顺序列出，路径都已对照应用对象核实。

| 业务 | 方法 | 路径 | 代码位置 |
|---|---|---|---|
| 登录 | POST | `/api/auth/login` | `api/auth.py:18` |
| 账表识别 | POST | `/api/projects/{project_id}/ledger-import/detect` | `routers/ledger_import_v2.py:104` |
| 提交导入 | POST | `/api/projects/{project_id}/ledger-import/submit` | `routers/ledger_import_v2.py:228` |
| 导入作业状态 | GET | `/api/projects/{project_id}/ledger-import/jobs/{job_id}` | `routers/ledger_datasets.py:293` |
| 数据集回滚 | POST | `/api/projects/{project_id}/ledger-import/datasets/{dataset_id}/rollback` | `routers/ledger_datasets.py:162` |
| 科目自动匹配 | POST | `/api/projects/{project_id}/mapping/auto-match` | `routers/mapping.py:46` |
| 保存 / 批量确认映射 | POST | `/api/projects/{project_id}/mapping`、`.../mapping/batch-confirm` | `routers/mapping.py:93`、`:132` |
| 查看试算表 | GET | `/api/projects/{project_id}/trial-balance` | `routers/trial_balance.py:34` |
| 手动全量重算试算表 | POST | `/api/projects/{project_id}/trial-balance/recalc` | `routers/trial_balance.py:181` |
| 调整分录列表 / 新建 | GET / POST | `/api/projects/{project_id}/adjustments` | `routers/adjustments.py:110`、`:190` |
| 提交复核 | POST | `/api/projects/{project_id}/adjustments/submit-review` | `routers/adjustment_review.py:133` |
| 批量通过 / 驳回 | POST | `/api/projects/{project_id}/adjustments/review-batch` | `routers/adjustment_review.py:172` |
| 撤回复核 | POST | `/api/projects/{project_id}/adjustments/{entry_group_id}/revoke-review` | `routers/adjustments.py:678` |
| 底稿推送调整分录 | POST | `/api/projects/{project_id}/adjustments/sync-from-workpaper` | `routers/adjustments.py:209` |
| 审定表发布到试算表 | POST | `/api/workpapers/{wp_id}/audit-determination/publish-to-tb` | `routers/wp_html_save.py:695` |
| 生成报表 | POST | `/api/reports/generate` | `routers/reports.py:85` |
| 报表公式审核 | GET | `/api/reports/{project_id}/{year}/consistency-check` | `routers/reports.py:154` |
| 报表公式种子（仅 admin） | POST | `/api/report-config/seed` | `routers/report_config.py:413` |
| 全局公式发布 | POST | `/api/formula-settings/{domain}/global/publish` | `routers/formula_settings.py:278` |
| 公式推送 | POST | `/api/projects/{project_id}/formula-push/run` | `routers/formula_push.py:130` |
| 生成底稿（模板集 / 按编码） | POST | `/api/projects/{project_id}/working-papers/generate`、`.../generate-from-codes` | `routers/wp_template.py:271`、`:360` |
| 底稿预填 | POST | `/api/projects/{project_id}/working-papers/{wp_id}/prefill` | `routers/wp_editor_router.py:1021` |
| 底稿表单读 / 存 | GET / PUT | `/api/workpapers/{wp_id}/checklist-responses` | `routers/checklist_responses.py:92`、`:140` |
| 在线编辑保存回调 | POST | `/api/workpaper-sync/rooms/{room_id}/onlyoffice-callback` | `routers/wp_sync_router.py:2988` |
| 生成附注 | POST | `/api/disclosure-notes/generate` | `routers/disclosure_notes.py:229` |
| 附注从底稿取数 | POST | `/api/disclosure-notes/{project_id}/{year}/pull-from-workpapers` | `routers/disclosure_notes.py:457` |
| 附注离屏刷新 | POST | `/api/disclosure-notes/{project_id}/{year}/headless-refresh` | `routers/note_headless_refresh.py:34` |
| 附注校验 | POST | `/api/disclosure-notes/{project_id}/{year}/validate` | `routers/disclosure_notes.py:1118` |
| 合并推送 | POST | `/api/consolidation/{project_id}/{year}/push` | `routers/consol_push.py:56` |
| 生成合并报表 | POST | `/api/consolidation/reports/generate` | `routers/consol_report.py:46` |
| 签字前一致性门禁 | GET / POST | `/api/projects/{project_id}/consistency-check`、`.../consistency-check/run` | `routers/consistency.py:20`、`:33` |

## 4.4 没有鉴权依赖的 90 个接口

平台**没有全局登录中间件**（`backend/app/middleware/` 里的中间件只为记日志、限流解析令牌，不拦请求），所以依赖链里没有鉴权依赖的接口，不带令牌也能调用，除非函数体内自己校验。90 个分三类：

**合理的公开接口（51 个）**：登录 / 刷新 / 登出、健康检查与存活探针（`/api/health*`、`/livez`、`/readyz`）、版本号；OnlyOffice 与 WOPI 的机对机回调和取文件（`/wopi/*`、`.../onlyoffice-callback`、`.../contents`、带 HMAC 签名的下载），它们用自己的令牌或签名校验；本机 DSH 进程的模型转发；只返回静态配置的目录类接口（准则列表、编码树、模板元数据、渲染注册表、多语言词典等）。

**已下线、只返回 410 / 501 / 拒绝的桩（15 个）**：程序裁剪旧写入口、高级查询旧写回入口、按姓名分派底稿、系统字典新增 / 删除、模板库 JSON 资源编辑、上年附注文件上传等。

**需要关注（24 个，匿名就能写、删或看管理信息）**：

| 接口 | 问题 |
|---|---|
| `POST /api/auth/register` | 公开注册账号。生产环境是否应该关闭，需要确认 |
| `POST /api/accounting-standards/seed`、`POST /api/gt-coding/seed`、`POST /api/wp-template-metadata/seed` | 匿名可以往库里灌种子数据 |
| `POST /api/custom-templates`、`POST .../validate`、`GET /api/custom-templates/{id}`、`DELETE /api/custom-templates/{id}`、`.../publish`、`.../unpublish` | 匿名可以新建、删除、发布自定义模板；代码里写死了一个临时用户 ID（注释「正式环境从 JWT 获取」） |
| `DELETE /api/forum/posts/{post_id}`、`POST .../like`、`GET /api/forum/posts`、`GET .../comments` | 匿名可以删帖、点赞、看帖 |
| `GET /api/admin/event-health` | 管理类接口，匿名可看最近 100 条联动记录 |
| `GET /metrics`、`GET /api/cache/stats`、`GET /api/ai/health`、`GET /api/metabase/*` | 运行指标、缓存统计、仪表板配置匿名可看 |
| `GET /docs`、`/openapi.json`、`/redoc` | 全部接口文档匿名可看。按项目记录，生产模式会关闭这三个地址，上线前需要在生产实例上确认 |

完整 90 条见 [附录 D2](appendix-d2-api-gaps.md) D2.1。

## 4.5 前端写了、后端找不到的路径（210 个）

前端源码里共有 1989 种 `/api/...` 路径写法，其中 **210 种在后端找不到同形接口**。集中在两处：

- `services/apiPaths/system.ts` 里成批的 `/api/ai/chat/*`、`/api/ai/nl/*`、`/api/ai/ocr/*`、`/api/audit-programs/*`、`/api/findings/*`、`/api/auth/me` 等，后端没有这些地址；
- 附注编辑器的版本树、模板转换（如 `/api/disclosure-notes/{}/{}/sections/{}/version-tree`、`.../template-conversion/preview`），以及 `/api/_debug/a51-content-revision`、`/api/event-bus/publish` 等零散路径。

它们要么是没人用的旧常量，要么是点了就 404 的功能，需要逐条确认。按路径形状匹配会把拼接出来的路径误算进来，所以这个数字偏大。完整清单见 [附录 D2](appendix-d2-api-gaps.md) D2.2。

## 4.6 后端调用的外部接口

| 外部服务 | 用途 | 配置项 | 调用代码 |
|---|---|---|---|
| OnlyOffice 文档服务 | 在线编辑、强制保存（Command Service）、回调后下载文件 | `ONLYOFFICE_URL`、`ONLYOFFICE_CALLBACK_BASE`、`ONLYOFFICE_JWT_SECRET` | `routers/wp_onlyoffice_router.py`、`routers/d2_sync_router.py`、`services/onlyoffice_callback_service.py`、`services/workpaper_sync/command_service.py`、`services/workpaper_sync/callback_download.py` |
| 大模型（OpenAI 兼容接口） | 对话、结构化输出、向量、重排 | `LLM_BASE_URL`、`LLM_EMBEDDING_BASE_URL`、`OLLAMA_BASE_URL`；库表 `ai_model_config` 登记的模型地址 | `services/llm_runtime.py`、`services/ai_service.py`、`services/structured_llm_service.py`、`services/availability_fallback_service.py` |
| OCR | 扫描件识别（MinerU、远程 OCR） | MinerU 默认 `http://localhost:8000`；`ai_model_config` 的 OCR 槽 | `services/mineru_service.py`、`services/remote_ocr_runtime.py`、`services/unified_ocr_service.py` |
| Paperless-ngx | 附件主存储、预览、下载 | `PAPERLESS_URL`（默认 `http://localhost:8010`）、`PAPERLESS_TOKEN` | `services/attachment_service.py`、`routers/attachments.py` |
| ChromaDB | 旧的向量库地址 | `CHROMADB_URL` | `services/ai_service.py` |
| 归档包取件 | 打归档包时逐项下载附件 | 来自附件地址 | `services/archive_package_builder.py` |
| PostgreSQL / Redis | 主库、缓存、事件流 | `DATABASE_URL`、`REDIS_URL` | 全局 |
| LibreOffice、DSH | 本机进程：Office 转 PDF、智能体 | 本机路径配置 | `services/libreoffice_pool.py`、`services/dsh_*` |

以上从 `backend/app` 里直接创建 HTTP 客户端的 18 个文件整理；经通用封装发出的调用可能没有全部列到。
