# 环境卫生：依赖对齐、加密 fail-closed 与泄漏 scratch schema — 设计

> 需求：#[[file:.kiro/specs/environment-hygiene-deps-and-scratch-schemas/requirements.md]]

## 一、依赖对齐（Requirement 1）

dry-run（`pip install --dry-run --report`）结果只有新增、无升降级：jieba 0.42.1 / pyzipper 0.3.6 / pymupdf 1.28.2 /
mcp 1.30.0，外加传递依赖 pycryptodomex 3.23.0 / httpx-sse 0.4.3 / sse-starlette 3.5.0。`mcp` 按 CI 的做法装
`-r tools/audit-data-mcp/requirements.txt`，不进 `backend/requirements.txt`（后端生产代码不 import 它）。

psycopg2-binary / pgvector 的版本偏差只报告：运行中的后端与并行会话共用这个 `.venv`，降级有打断风险，且两者都向后兼容。

jieba 装上后分词从二元组切换为词典分词。`query_terms` 在检索协程里同步调用，首次调用会加载词典；装后实测首载耗时再决定
是否要移到工作线程（结论记入本节「实测补」）。

### 实测补：装包后暴露的 10 红（与装包无关）

`test_semantic_search_scope.py`（7）与 `test_semantic_search_scope_pbt.py`（3）。归因三步：屏蔽 jieba 复跑同 10 红；
把 `knowledge_index_service` 换成 HEAD 字节（不改磁盘，`sys.modules` 注入）复跑 9 红 ⇒ 装包未引入。根因是知识库 spec
（`knowledge-base-retrieval-and-authz-closure` 任务 4.6）改检索内核时，只把同类 mock 测试 `test_retrieval_phase2_pbt.py` /
`test_knowledge_index_service.py` 迁到 `tests/_kb_mock_session.py`，漏了这两个文件：

- 形状：夹具是裸 `AsyncMock()`，`begin_nested()` 返回协程，`async with` 抛 `TypeError`，三层检索全部失败返回空 ⇒ `0 == 1`。
- 契约：部分断言钉的是已被反转的旧契约 —— 「`user=None` 不过滤」（设计 §十 C1 已反转）、「向量失败时知识文档走 ILIKE、
  score 恒 0」（现为文档词法层）、「权限按第二次 `execute` 的行判定」（现为 `visible_documents`）。

处置沿用该 spec 任务 4.6 的做法：夹具换 `make_retrieval_session()` / `attach_retrieval_session_shape()`；契约已反转的断言
按现契约改写并在 docstring 写明反转；知识文档可见性改为 patch `_doc_search.visible_documents` / `search`，判定本身由
`test_knowledge_retrieval_visibility_pbt` 与真库 `test_knowledge_doc_search_pg` 覆盖。

### 其它

仅报告、不在本 spec 修：AI Agent 的 MCP 子进程用字面量 `"python"` 启动（`dsh_engine.spawn_mcp_process`），在本机解析到
**全局** Python（自带 mcp 1.28.1），而不是后端所用的 `.venv`；打包环境下两者都不成立，属 DSH 引擎的部署设计问题。

## 二、PDF 兜底改用 pypdf（Requirement 2）

```python
from pypdf import PdfReader
reader = PdfReader(io.BytesIO(content))
```

pypdf 是 PyPDF2 的延续（同一维护者，PyPDF2 已停更），`PdfReader` / `pages` / `extract_text()` 接口相同，只改 import 与日志文案。
`requirements.txt` 显式 pin `pypdf==6.13.0`：它现在只是 mineru 的传递依赖，mineru 一旦换依赖，兜底会第二次静默失效。

## 三、抽取链测试（Requirement 3）

两个引擎都在函数体内 `from … import`，打补丁目标取定义处：`app.services.anydoc_service.convert_bytes_detailed`、
`app.services.markitdown_service.convert_bytes_to_markdown`、`app.services.mineru_service.MinerUService`。
anydoc 结果用真实的 `AnydocResult` 构造，不用 MagicMock（否则 `res.needs_ocr` 恒为真值，分支判据空转）。
pypdf 用例不打补丁，喂手工拼的真 PDF 字节（与 `_env_extract_probe.make_text_pdf` 同法，xref 偏移逐字节计算）。

## 四、批量导出密码 fail-closed（Requirement 4）

### 4.1 异常直接继承 `HTTPException`，路由不改

`backend/data/workpaper_writer_inventory.json` 把 `wp_bulk_router.py`、`bulk_async_runner.py` 里若干函数的**行号**
（`swallowed_exception_lines` / `artifact_write_targets` 等）算进 `source_digest`。在这两个文件的相关行上方插代码会让
清册失效 —— 与上一轮指纹门禁事故同型。故异常定义为 `HTTPException` 子类（本仓已有先例：`ExternalNotFound`、
`TrimSchemeError`、`DelegationConflictError`），FastAPI 直接转成响应，路由与 runner 一行不动：

```python
class BulkExportEncryptionUnavailableError(HTTPException):   # 503：缺 pyzipper
class BulkExportEncryptionFailedError(HTTPException):        # 500：加密异常 / 产物校验不通过
    def __str__(self) -> str: return str(self.detail)        # runner 用 str(exc) 写任务错误，不带「503: 」前缀
```

状态码沿用本仓「缺服务端组件」的惯例（`libreoffice_unavailable` 同为 503）。

### 4.2 服务层

- `export()` 开头：`if password: _require_zip_encryption()`。在建 manifest 之前失败 ⇒ 不做无用功，也不会先 flush 增量清单。
- 第 9 步改为 `return _encrypt_zip(zip_result, password)`：加密后用 `zipfile` 复核「条目名集合与明文包相同」且「每个条目
  `flag_bits & 0x1`」，任一不成立即抛 `BulkExportEncryptionFailedError`。只读中央目录，不解密，代价与包大小无关。
- 未要求密码时行为不变，也不需要 pyzipper。

### 4.3 异步导出

`_run_export` 的 `except Exception → bulk_progress_service.fail(task_id, str(exc))` 已覆盖；写盘在 `export()` 返回之后，
抛错即不落文件。只加测试，不改代码。

### 4.4 前端

- `exportTemplates(cycles, password?)` 请求体带 `password`；`WpBulkDialog` 模板导出传入密码框的值。
- 两个 blob 下载失败时，先从 blob 错误体解析 `detail ?? message`，解析不到再退回原 `extractError`。

## 五、同类 fail-open（Requirement 5）

`EncryptionService.__init__` 去掉 `try/except ImportError`，缺 `cryptography` 时抛 `RuntimeError`（中文原因）；删除
`encrypt/decrypt/*_bytes` 里的 base64 分支（`_key` 为真时 `_fernet` 必然存在）。`generate_key` 的回退与
`Fernet.generate_key()` 同算法（`urlsafe_b64encode(os.urandom(32))`），不是安全缺陷，保留。

`file_scan_service` 登记不改：它把「扫描服务不可用」设计成放行，且结果带 `scanned=False`。唯一调用方
`attachment_security_gates` 只看 `clean`，所以「开了 ClamAV 却没装 clamd」在上传侧不可见 —— 是否改为拒绝上传需要产品决策。

## 六、泄漏 scratch schema（Requirement 6）

### 6.1 机制与证据

- 7 个前缀逐一对应 harness 的 `_SCHEMA_PREFIX`，每个 harness 都在 `finally` 里 `DROP SCHEMA … CASCADE`；只有进程在
  `finally` 之前被终止才会泄漏。已知终止源：`_mutation_kit/runner.run_pytest` 的 `subprocess.run(timeout=1800)` 超时会杀子进程；
  手工结束进程 / 关终端同理。
- task24 两个残留分别建于 08-26 与 09-19，都**恰好**停在 4 个单人场景（generation 100–103，intent 全部 `promoted`）之后、
  第一个双人场景建房之前，说明是同一处确定性卡住后被外部终止，而不是随机中断；具体是哪条变异导致卡住未能确认。
- `asyncio.Barrier` 无超时等待（task23 / task24 / task30）在某个 racer 于 `wait()` 前退出时会永久挂起，是同类风险，但与
  上面两个残留的停止位置不符，不作为它们的成因。

### 6.2 清理与不做清扫器

一次性脚本按精确名单逐个删：名称在名单内、匹配 `^tmp_[a-z0-9_]+_[0-9a-f]{12}$` 且以已知前缀开头、`pg_locks` 为 0、
除 `pg_toast` 外无跨 schema 依赖，满足才 `DROP SCHEMA … CASCADE`，每个一个事务；删后复查名单内 0 残留。

不做自动清扫器：PG 不记录 schema 创建时间，harness 用随机十六进制命名，无法判断「多旧」；并行会话随时在跑 PG harness，
按前缀清扫可能删掉正在运行的 schema。

## 七、测试与变异

| 文件 | 覆盖 |
|------|------|
| `tests/test_knowledge_content_text.py`（重写） | 需求 3.1 全部分支 |
| `tests/services/test_bulk_export_password_fail_closed.py` | 缺 pyzipper ⇒ 503 且未建 manifest；加密成功 ⇒ 每条目带加密标志、同名集合、用密码可读、无密码读抛错；加密异常 / 条目未加密 ⇒ 500；不要密码时缺 pyzipper 也正常；端点真发请求 ⇒ 503 JSON 中文原因；异步路径任务失败、错误无状态码前缀、不落文件 |
| `tests/test_encryption_service_fail_closed.py` | 缺 cryptography ⇒ 构造即抛；无密钥仍可构造 |
| `src/composables/__tests__/useBulkTabImportExport.password.spec.ts` | 两个导出都带 password；blob 错误体中文原因被展示 |
| `WpBulkImportExport.spec.ts` 追加 | 模板导出把密码框的值传给 `exportTemplates` |

变异（一次性 `_env_mutation_check.py`）：pypdf 改回 PyPDF2 / 去掉兜底截断 / 扫描件仍跑 MarkItDown / 缺 pyzipper 退回明文 /
预检挪到 manifest 之后 / 去掉产物复核 / 加密异常退回明文 / 异常去掉 `__str__` / `EncryptionService` 恢复 base64 回退 /
composable 丢密码 / 不解析 blob 错误体 / 对话框模板导出不传密码。

## 八、批量导出可用性（Requirement 8）

### 8.0 共用：异常基类

`bulk_tab/exceptions.py` 抽出 `BulkTabUserError(HTTPException)`（`__str__` 只返回中文原因），加密两类改为继承它，
新增两个 422：`BulkExportPasswordInvalidError`、`BulkExportNothingToExportError`。仍是「异常直接继承
`HTTPException`、路由与 runner 零改动」这一条路（§4.1）：`wp_bulk_router.py` / `bulk_async_runner.py` 的行号被
writer 清册钉扎。选 422 而非 400/409：是用户可纠正的请求问题；且前端拦截器对 5xx 自动重试两遍，422 不会触发。

### 8.1 零 Tab 即拒绝导出

判定点：第 4 步把未导出条目移出 `manifest.files` 之后、第 3b 步写附加文件之前 —— `if not manifest.files: raise`。
不在 manifest 刚建完时判：可见集过滤、缺适配器、导出失败、无数据、未变更这五种跳过都发生在逐 Tab 循环里，
只有这一个点能看到「最终一张都没有」。抛在附加文件与增量清单之前 ⇒ 不做无用功、不留痕迹。

原因按 `skipped` 的类别计数汇总，一类一句、用「；」连接（ElMessage 会吞掉换行）：
找不到底稿（`resolve_instance_miss`，含「未生成」与「多份同编号」两种）⇒「请先在「底稿列表」点「生成底稿」」；
`no_data` ⇒ 提示可取消「仅导出有数据的 Tab」；`unchanged` ⇒ 提示可取消「增量导出」；`export_failed` /
`no_adapter` / `unknown` 各一句；`unsupported_cycles` ⇒ 循环名 + §8.4 的原因。被可见集过滤掉的条目按 Task 10 设计
**不进** `skipped`（不泄露存在性），全部被过滤时只剩通用句「所选循环中没有您可导出的底稿」。

契约反转：`test_export_all_tabs_fail_still_produces_zip` 钉的是「全部失败仍产出 ZIP」，改写为「全部失败 ⇒ 422 且
原因写明导出失败」，docstring 注明用户裁决。单张失败继续 fail-soft —— 归档 spec 的 Req 1.6 / 1.8 只规定单 Tab
跳过不使整包失败，没有规定零 Tab 也要出包。

README：跳过原因改中文（先按类别给张数，再列前 20 条明细），「各循环状态」改为逐个所选循环列出（原实现只列
有导出的循环，0 张的循环整个消失）。`_底稿目录.xlsx` 的状态列同一套中文。

### 8.2 模板模式不附带项目数据

第 3b 步（报表 / 未审报表 / 附注 / 试算表）包进 `if mode == "data":`；进度总数的 `+3` 同样只在数据模式计入。
README 的「附加文件」段改为按实际写入的文件生成 —— 原文案固定列 5 个文件，再用「缺失即该项暂无数据」一句带过，
模板包里也照列。模板模式在使用说明里加一句「本模板包只含表格骨架与表头，不附带报表、附注、试算表」。
`_底稿目录.xlsx` 两种模式都保留：只有底稿编码、名称、路径、状态。

判据不能只看「包里没有这些文件」：单测里 `db` 是 `AsyncMock`，四个导出器本就会抛错被 fail-soft 吞掉 ⇒ 条目
天然不存在，删掉 `if mode == "data"` 照样绿。故用例把三个导出器替换成必定成功的替身，断言模板模式**未调用**、
数据模式调用且 README 列出（正向对照）。

### 8.3 密码限定可打印 ASCII

服务端无法知道用户用什么软件解压，只能限定两端编码必然一致的字符集：`[\x21-\x7E]{1,128}`（不含空格：前后空格
在输入框里看不见，是最常见的「密码明明对却打不开」）。校验在 `export()` 第 0 步、加密可用性预检之前 —— 用户可
纠正的问题先报。异步导出同样经过 `export()`，后台任务以中文原因失败。

前端对话框同规则即时校验，密码框下方常驻规则提示、违规时换成错误原因，执行按钮置灰。规则两份：
后端 `PASSWORD_MAX_LENGTH` + 字符集是权威，前端是体验预检；守卫读 `WpBulkDialog.vue` 的两个常量与后端逐值比对。

### 8.4 循环清单由后端下发

`scenario_registry.cycle_options_for_ui()`：候选 = `dashboard_aggregator_service.CYCLES`（D~N）∪ catalog 中有导入
导出 Tab 的循环（catalog 以后新增循环时自动出现）；`supported` = 该循环在 catalog 中至少一张 Tab 启用导入导出
（`manifest_builder.supported_cycles()`，即原 `_get_all_cycles` 改为公开名）；名称取 `CYCLE_NAMES`（驾驶舱同一份，
故对话框里「D 销售循环」会变成「D 销售收入」，并去掉原来「D - D 销售循环」的编码重复）；原因文案常量
`UNSUPPORTED_CYCLE_REASON` 同在 `scenario_registry`（文案单一真源），导出拦截提示与 README 共用。
场景端点返回体加 `"cycles"`，同行编辑，不增行。

`build_manifest` 逐循环本就调 `list_sheets(cycle, import_export_only=True)`：结果为空即记入 `unsupported_cycles`，
零额外 catalog 读取；`to_dict()` 输出该键（导入侧只读 `files` / `cycles` / `mode`，多一个键无影响）。

对话框：不支持的循环 disabled、不默认勾选，下方按原因分组显示「E 货币资金、J 薪酬：……」；「全选」只作用于
可用循环；从 ZIP 识别循环时同样只保留可用循环；`cycles` 缺失 ⇒ 与场景缺失同样显式报错（不退回写死列表）。

不在本 spec 为 E、J 登记 catalog：
- `fix_acnr_catalog_ie_gap.py` 的 `GAP_REGISTRY` 明确不登记 e1 / j1 / j2 / j3（「specs 抽取失败，需人工核 item_id」）；
- **数据位置不一致**：E1 数据存在父底稿 E1 上，而 bulk 按 `WpIndex.wp_code == sheet_code` 解析到子底稿。D 循环
  已实测同一问题：和平药房_2025 的 `D2-detail-rows`（550 KB）挂在父底稿 D2（`ef7f88e3…`）上，数据包里的 D2-2
  （`57742161…`）只有表头 —— 直接登记 E、J 会得到同样的空数据包；
- catalog 与其生成器输出已有漂移（`check_catalog_drift.py`），前端 registry 由生成器派生且有多条 vitest 守卫。
⇒ 另立 spec（同时修 D 循环的父 / 子底稿数据位置）。

### 8.5 前端错误提示单一出口

两个导出请求加 `_silent: true`。原因：全局拦截器对 4xx 会用同一句再弹一次（与 composable 的提示重复），对 5xx
会把整次导出（超时 5 分钟）自动重跑两遍 —— 加密失败这类确定性错误重跑无意义。`_silent` 在拦截器里位于 401
刷新令牌之后，令牌刷新不受影响。原本由拦截器提示的超时、断网两种情形改由 composable 给中文原因。

### 8.6 测试与变异

| 文件 | 覆盖 |
|------|------|
| `tests/services/test_bulk_export_usability.py`（新） | 8.1 各类别原因 / 可见集全滤不泄露 / 1 张成功仍出包 / 422 前不读正文不写附加文件；8.2 导出器替身调用次数（模板 0、数据正向对照）；8.3 各非法密码 422 且未建 manifest、边界合法值、前后端常量交叉锁；8.4 真 catalog 的 E、J 不支持、`unsupported_cycles` 入 manifest、场景端点带 `cycles`、前端 `BulkCycleOption` 字段 ⊆ 后端键；端点层真发请求 422 JSON |
| `tests/services/test_bulk_export_service.py`（改） | 全部失败改判 422（契约反转）；3 条过期断言按现实现改写 |
| `tests/test_bulk_async_runner.py`（追加） | 零 Tab ⇒ 后台任务失败、错误无状态码前缀、不落 ZIP |
| `tests/services/test_bulk_export_password_fail_closed.py`（改） | 密码改 ASCII（原中文密码按 8.3 属非法输入） |
| `WpBulkImportExport.spec.ts`（改 + 追加） | mock 带 `cycles`；不支持循环置灰且不入参；原因来自后端；中文密码报错且按钮不可用；`cycles` 缺失报错 |
| `useBulkTabImportExport.password.spec.ts`（追加） | 两个导出带 `_silent`；超时 / 断网中文原因 |

变异：去掉零 Tab 拦截 / 原因不写「生成底稿」/ 模板模式仍写附加文件 / 去掉密码校验 / 校验挪到 manifest 之后 /
`build_manifest` 不记 `unsupported_cycles` / 场景端点不带 `cycles` / 对话框写回死列表 / 不支持循环仍默认勾选 /
密码违规仍可执行 / 导出请求去掉 `_silent`。
