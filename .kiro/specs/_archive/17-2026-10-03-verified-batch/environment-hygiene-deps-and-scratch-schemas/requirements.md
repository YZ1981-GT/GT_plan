# 环境卫生：依赖对齐、加密 fail-closed 与泄漏 scratch schema — 需求

> 2026-09-30 新建。来源：知识库收口「逐一修复」第 4 项（环境卫生）。只处理三类：①本机 `.venv` 与已声明依赖不一致
> ②因缺依赖而**静默失效**的代码路径（含触类旁通的同类 fail-open）③测试 harness 泄漏在真库的 scratch schema。

## 背景（全部为现场实测）

| # | 事实 | 后果 |
|---|------|------|
| F1 | `.venv`（Python 3.12.8）缺 4 个已声明包：`jieba>=0.42` / `pyzipper==0.3.6` / `PyMuPDF>=1.23`（`backend/requirements.txt`）、`mcp>=1.14.0,<2`（`tools/audit-data-mcp/requirements.txt`，CI 该 job 单独安装）；另 2 个与 pin 不符：`psycopg2-binary` 2.9.13 ≠ 2.9.11、`pgvector` 0.5.0 ≠ 0.4.2 | `test_zh_tokenize_pbt` 17 红、`test_audit_data_mcp_server` 17 红；知识库分词长期走二元组降级；`content_extractor._extract_pdf` 未加保护的 `import fitz` 必抛 |
| F2 | 知识库抽取最后兜底 `import PyPDF2`：未安装也未声明，且包在宽 `try` 里 ⇒ PDF 兜底**静默恒返回 None**。`pypdf 6.13.0` 已装（mineru 依赖 `pypdf>=5.6.0`），实测可从带文本层的 PDF 抽出正文（含 6 万字） | anydoc 与 MarkItDown 都失手的 PDF 永远抽不出正文，且无任何报错 |
| F3 | `test_knowledge_content_text.py` 4 红 3 绿：按 bb7ea6cfe 时的「MinerU 优先」链写成；现链路为 anydoc → MarkItDown →（仅 PDF）MinerU → PyPDF2 / python-docx；另 1 条直接 `import PyPDF2` | 守卫与实现脱节，红被当成常态 |
| F4 | `bulk_export_service.export` 要求密码时：`import pyzipper` 失败 ⇒ `logger.warning` 后**返回明文 ZIP**；加密过程任何异常同样退回明文 | 用户设了密码却拿到未加密压缩包，界面无任何提示 |
| F5 | 前端「导出全部模板」显示「密码保护（可选）」输入框，但 `exportTemplates(cycles)` 不传密码（后端 `ExportTemplatesRequest.password` 已支持） | 同 F4：设了密码仍得到明文包 |
| F6 | 批量导出以 blob 下载；失败时 composable 的 `extractError` 读不到 blob 里的 JSON，只显示 axios 英文 `Request failed with status code …` | 后端给了中文原因，界面看不到 |
| F7 | 触类旁通 grep `except ImportError`：`EncryptionService` 缺 `cryptography` 时 `encrypt()` 退化为 base64（生产调用方 0，仅测试引用）；`file_scan_service` 开启 ClamAV 却缺 `clamd` 时跳过扫描、返回 `clean=True, scanned=False`（模块注释明示为可用性取舍） | 前者是潜伏缺陷；后者属产品决策 |
| F8 | 真库 7 个 `tmp_*` schema 残留（每个 142–150 个关系；零锁；除 `pg_toast` 外无跨 schema 依赖）：`tmp_fp_pg_c445b0386189`、`tmp_task24_ci_76c29f8c7519`、`tmp_task24_ci_84aa1bff226d`、`tmp_task25_mc_ee1c15c00149`、`tmp_task26_oh_37607461dce0`、`tmp_task26_oh_87ac14f71eff`、`tmp_task38_pg_bc844f371a20` | schema 漂移 / 清册类扫描都要额外过滤；task71 gate 把它们列为 upstream 残留、等 owner 清理 |
| F9 | 7 个前缀都对应某个 harness 的 `_SCHEMA_PREFIX`，且各 harness 都在 `finally` 里 `DROP SCHEMA … CASCADE` | 只有进程在 `finally` 之前被终止才会漏 |

## Requirement 1：依赖对齐

1.1 `.venv` SHALL 安装 `jieba==0.42.1`、`pyzipper==0.3.6`、`PyMuPDF==1.28.2`（满足声明 `>=1.23`）与 `-r tools/audit-data-mcp/requirements.txt`；安装前 dry-run 确认只新增、不升级 / 降级任何已装包。
1.2 与 pin 不符的 2 个包只报告、不降级（运行中的后端与并行会话共用这个 `.venv`）。
1.3 装后重跑：原先因缺包而红的套件转绿；jieba 改变分词 ⇒ 知识库检索相关套件全量复跑；实测 jieba 首次加载耗时，据此判断是否需要移出事件循环。

## Requirement 2：PDF 兜底改用 pypdf

2.1 `_extract_text_with_ocr` 的最后兜底 SHALL 用 `from pypdf import PdfReader`；docstring / 注释里的 PyPDF2 同步更正，重复的「降级 2」更正为「降级 3」。
2.2 `backend/requirements.txt` SHALL 显式声明 `pypdf==6.13.0`（此前只是 mineru 的传递依赖，mineru 换依赖即静默消失）。

## Requirement 3：抽取链测试按现链路重写

3.1 覆盖：anydoc 成功直接返回、不再调用其它引擎；扫描件（`needs_ocr`）跳过 MarkItDown 进 MinerU 并截断到 50000；扫描件且 MinerU 不可用 ⇒ ERROR 日志 + 结果 None；anydoc 未命中 + MarkItDown 为空 ⇒ pypdf 从真实文本层 PDF 抽出正文并截断到 50000；docx ⇒ python-docx 且不进 MinerU；anydoc `permanent` ⇒ 不再尝试任何引擎；MinerU 抛错 / 返回空文本 ⇒ 落到 pypdf。
3.2 PDF 夹具为真实字节（手工拼装、xref 偏移逐字节计算），不依赖 PyPDF2 / PyMuPDF / reportlab。

## Requirement 4：批量导出密码 fail-closed

4.1 请求了密码而服务器缺 `pyzipper` ⇒ SHALL 在任何导出工作之前失败（不建 manifest、不读正文、不写增量清单），HTTP 503 + 中文原因；绝不返回明文 ZIP。
4.2 加密过程任何异常、或产物中存在未加密条目 / 条目集合与明文包不一致 ⇒ HTTP 500 + 中文原因；不返回明文 ZIP。
4.3 异步导出同样失败并携带中文原因，且不落 ZIP 文件。
4.4 前端模板导出 SHALL 透传密码；blob 错误体里的中文原因 SHALL 展示给用户。

## Requirement 5：同类 fail-open

5.1 `EncryptionService` 配置了密钥却缺 `cryptography` ⇒ 构造即抛错；删除以 base64 冒充加密的分支。
5.2 `file_scan_service` 不改，登记为待用户决策。

## Requirement 6：泄漏 scratch schema

6.1 仅按 F8 的精确名单逐个删除：删前复核名称匹配 harness 前缀、零锁、无跨 schema 依赖；每个 schema 独立事务；删后复查名单内 0 残留。
6.2 记录泄漏机制与证据；不做自动清扫器。

## Requirement 7：验证

7.1 新增 / 改写用例全绿；相关套件的预存红逐条归因。
7.2 变异：回退任一修复必须打红，还原后 sha256 一致。
7.3 前端 vitest 覆盖密码透传与 blob 错误体。
7.4 真栈：Playwright 走「导出全部模板 + 密码」，下载的 ZIP 每个条目都带加密标志、用该密码可读出。

## Requirement 8：真栈暴露的批量导出可用性缺陷（2026-09-30 用户批准「按上面的建议改这 4 条」）

来源：任务 7.3 真栈复测。以下事实均为现场实测。

| # | 事实 | 后果 |
|---|------|------|
| F10 | 和平物流_2025 只有 3 份自定义底稿，353 张 Tab 全部 `resolve_instance_miss`；导出仍返回 200 ZIP（0 张 Tab），界面提示「模板 ZIP 已导出」；README 的跳过原因只写代码 | 用户以为导出成功，拿到的是空包 |
| F11 | 模板模式固定附带 `_报表/财务报表.xlsx`、`_报表/财务报表_未审数.xlsx`、`_附注/财务报表附注.docx`、`_试算表/试算平衡表.xlsx`（下载包的试算表 37 行非零，如银行存款期初 980,941.75）；场景说明却写「不含任何项目数据，适合发给被审计单位」。Tab 模板本身（和平药房_2025 D 循环 7 张）除表头与行标签外无任何数字 | 「空白模板」外发即泄露项目财务数据 |
| F12 | pyzipper 按 UTF-8 编码密码；同一中文密码按 GBK 编码解密报 Bad password | 中文密码的包在按本地代码页处理密码的解压软件里打不开 |
| F13 | ACNR catalog 启用导入导出的 sheet：D 81 / F 71 / G 75 / H 34 / I 24 / K 42 / L 10 / M 10 / N 6，E、J 为 0；对话框写死 D~N 11 个循环且默认全选；E、J 导出时既不进 `files` 也不进 `skipped` | 用户看不到 E、J 为什么没导出 |

8.1 WHEN 导出结果不含任何 Tab 文件 THEN THE BulkExport_Service SHALL 拒绝导出（HTTP 422，不返回 ZIP，不写附加文件、不持久化增量清单），中文原因按跳过类别汇总：找不到底稿 ⇒ 提示先生成底稿；无数据 / 未变更 / 导出失败 / 循环未接入分别说明；全部被可见集过滤时只给不泄露存在性的通用说明。只要有 1 张 Tab 导出成功，其余跳过仍按原 fail-soft 规则只记入 manifest（归档 spec `workpaper-bulk-tab-import-export` Req 1.6 / 1.8 不变）。
8.2 README 与 `_底稿目录.xlsx` 的跳过原因 SHALL 为中文；`manifest.json` 保留原始代码（供程序读取）。
8.3 模板模式 SHALL NOT 附带报表 / 附注 / 试算表；README 的「附加文件」只列实际写入的文件；`_底稿目录.xlsx` 保留（只含底稿编码、名称、路径与状态）。
8.4 导出密码 SHALL 只允许可打印 ASCII（`0x21–0x7E`：英文字母、数字、英文符号，不含空格），长度 1–128；不合规 ⇒ HTTP 422 + 中文原因，且在任何导出工作之前。对话框 SHALL 按同一规则即时校验并给出提示，不合规时执行按钮不可用；两端规则 SHALL 由守卫交叉锁死。
8.5 对话框的循环清单 SHALL 来自后端（`GET …/bulk-tab/scenarios` 返回的 `cycles`：`code` / `name` / `supported` / `unsupportedReason`）；catalog 中没有可导入导出 Tab 的循环 SHALL 置灰、不默认勾选并显示原因；后端未返回循环清单时 SHALL 显式报错而不是退回写死的列表。manifest SHALL 记录 `unsupported_cycles`，README SHALL 列出未纳入的循环及原因。本 spec 不为 E、J 登记 catalog（理由见 design §八.4）。
8.6 前端两个导出请求的错误提示 SHALL 只有一个出口（composable），不与全局拦截器重复弹出；导出失败 SHALL NOT 被自动重试。
8.7 验证：新增 / 改写用例全绿，回退任一修复必打红；真栈复测：无底稿项目导出被拦且显示中文原因；有底稿项目的模板包不含 `_报表/` `_附注/` `_试算表/`；中文密码被拒；E、J 置灰并显示原因。
