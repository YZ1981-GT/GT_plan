# 任务清单：环境卫生（依赖对齐、加密 fail-closed、泄漏 scratch schema）

> 需求：#[[file:.kiro/specs/environment-hygiene-deps-and-scratch-schemas/requirements.md]]
> 设计：#[[file:.kiro/specs/environment-hygiene-deps-and-scratch-schemas/design.md]]

- [x] 1. 依赖对齐
  - [x] 1.1 dry-run 复核只新增不升降级后安装 jieba / pyzipper / PyMuPDF / audit-data-mcp requirements
    - 证据：装前 / 装后 `pip freeze --all` 逐行对比只多 7 行（httpx-sse 0.4.3 / jieba 0.42.1 / mcp 1.30.0 / pycryptodomex 3.23.0 /
      pymupdf 1.28.2 / pyzipper 0.3.6 / sse-starlette 3.5.0），无任何已装包变版本；`pip check` 无冲突
  - [x] 1.2 装后复跑原缺包红的套件 + 知识库检索相关套件；jieba 首载耗时实测
    - 证据：`test_zh_tokenize_pbt` / `test_audit_data_mcp_server` / `test_content_extractor` 合跑 **56 passed**（装前 17 + 17 红）。
      知识库检索 22 个文件 263 例：253 过 / 10 红，10 红全在 `test_semantic_search_scope.py`（7）与 `…_pbt.py`（3）——
      屏蔽 jieba 复跑同 10 红、把 `knowledge_index_service` 换回 HEAD 字节复跑 9 红（只是失败形态不同）⇒ **与装包无关**，
      是知识库 spec 改检索内核时漏改的两个 mock 测试文件，见任务 1.3
    - jieba 实测：模块 import 0.20s，首次 `query_terms` 0.34s（加载词典，一次性），之后 0.02ms/次 ⇒ 不移出事件循环。
      分词口径变化：「应收账款坏账准备如何计提」→ `应收账款 / 坏账准备 / 计提`（降级实现是 10 个二元组）；知识库表不持久化分词结果，无需重建
  - [x] 1.3 `test_semantic_search_scope.py` / `…_pbt.py` 按现契约改写（归因见 design §一「实测补」）
    - 证据：两文件 14 例全绿（原 10 红）；docstring 写明两处契约反转（`user=None` 以「无主体」判定、知识文档兜底改走文档词法层）。
      新增判据：scope 条件真的下推到 SQL（编译语句断言 `source_type !=` / `=`）、knowledge_doc 范围向量失败时不再读索引分块、
      未知 scope 抛错、BM25 开 / 关两条兜底路径。变异 S1–S5（`user=None` 不过滤 / project_data 不排除知识文档 /
      knowledge_doc 范围仍读分块 / 忽略判定面结果 / 未知 scope 静默当 all）**5/5 RED**；变异经 `sys.modules` 注入、
      不改磁盘，事后生产文件 sha256 不变
  - _需求：1.1–1.3_
- [x] 2. PDF 兜底改用 pypdf + `requirements.txt` pin
  - 证据：`knowledge_folders._extract_text_with_ocr` 改 `from pypdf import PdfReader`，docstring / 两处注释 / 日志同步，第二个「降级 2」更正为「降级 3」；
    `markitdown_service` docstring 同步；`requirements.txt` 加 `pypdf==6.13.0` 并注明原因。全仓 grep `PyPDF2`：生产代码 0 处
  - _需求：2.1–2.2_
- [x] 3. 重写 `test_knowledge_content_text.py`
  - 证据：14 例全绿（原 4 红 3 绿）。夹具为真字节（手工 PDF + 夹具自检「文本层真能被 pypdf 读出、空白 PDF 读不出」）；anydoc 结果用真 `AnydocResult`；
    「链路在某处停下」用本可成功的后续引擎证明（permanent 失败时喂 pypdf 能读的 PDF，结果仍须为 None）
  - _需求：3.1–3.2_
- [x] 4. 批量导出密码 fail-closed
  - [x] 4.1 异常类 + 服务层预检 / 加密复核
    - 证据：`bulk_tab/exceptions.py` 新增 `BulkExportEncryptionError`（`HTTPException` 子类，`__str__` 只返回中文原因）及 503 / 500 两个子类；
      `export()` 开头预检、第 9 步 `_encrypt_zip` 加密后复核中央目录。`wp_bulk_router.py` / `bulk_async_runner.py` **零改动**（writer 清册按行号钉扎这两个文件）
  - [x] 4.2 前端模板导出透传密码 + blob 错误体解析
    - 证据：`exportTemplates(cycles, password?)`；两个导出失败都先解析 blob 错误体（`detail ?? message`），非 JSON 退回中文兜底；`WpBulkDialog` 模板导出传密码框的值
  - [x] 4.3 后端 / 前端用例
    - 证据：`tests/services/test_bulk_export_password_fail_closed.py` 10 例（端点层经 ASGI 真发请求，503 JSON 中文原因 + 正向对照 200 加密 ZIP）；
      异步层用例追加在 `tests/test_bulk_async_runner.py`（`_run_export` 是 writer 清册的一行、按调用它的测试文件记证据，放新文件会让清册过期）；
      vitest `useBulkTabImportExport.password.spec.ts` 8 例 + `WpBulkImportExport.spec.ts` 追加 2 例，两文件 23 passed。
      🔴 首版两处判据空转被自己抓到：①「产物复核」用 `AESZipFile(encryption=None)` 模拟 —— 实测 pyzipper 在 `writestr` 抛 `AttributeError`，
      测到的是「加密抛错」路径，删掉复核照样绿 ⇒ 改为「接受加密参数却写明文」与「静默少写一个条目」两个替身，并断言 `__cause__` 是复核的 RuntimeError；
      ② 组件测试的 `el-button` 替身未声明 `emits`，父组件 `@click` 被透传到根元素又被 `$emit` 一次 ⇒ 一次点击执行两次
    - 既有 `tests/services/test_bulk_export_service.py` 3 红为**预存**：把 `bulk_export_service` 换成 HEAD 字节（`sys.modules` 注入）复跑同 3 红
      （README 文案断言与 `_底稿目录.xlsx` 计数过期），与本任务无关
  - _需求：4.1–4.4_
- [x] 5. `EncryptionService` fail-closed + 用例；`file_scan_service` 登记待决策
  - 证据：配置了密钥却缺 cryptography ⇒ 构造即抛 `RuntimeError`，删除 4 处 base64 分支；`tests/test_encryption_service_fail_closed.py` 4 例 +
    `test_phase8::TestEncryptionService` + `test_phase8_smoke` 合跑 25 passed。`file_scan_service` 未改（design §五）
  - _需求：5.1–5.2_
- [x] 6. 删 7 个泄漏 scratch schema
  - 证据：一次性脚本逐个现查后删除（名字形态 + 已知前缀、`pg_locks` 为 0、跨 schema 依赖为 0 —— 依赖判定解析约束 / 默认值 / 触发器 / 规则 / 策略的归属，
    无法判定归属的一律算阻塞），7 个全部 `DROP`（143 / 142 / 142 / 150 / 150 / 150 / 142 个关系），删后名单内 0 残留、库内 `tmp_*` 0 个；
    public 486 张表、`projects` 58 行不变；`/api/health` healthy、schema drift 0
  - _需求：6.1–6.2_
- [x] 7. 验证
  - [x] 7.1 新增 / 改写用例 + 相关套件全绿，预存红归因
    - 证据：bulk 16 个 + 知识库 / 检索 18 个 + 装包相关 5 个 + 加密 3 个 + 其它 2 个测试文件合跑 **582 passed / 10 failed**，10 红全部预存：
      `test_bulk_export_service` 3（HEAD 字节复跑同 3 红，见任务 4.3）、`test_knowledge_index` 2（`knowledge_index_service` 换 HEAD 字节复跑同 2 红；
      测试文件自 2026-04-12 未改，断言不存在的 `.db` / `_chunk_text`）、`test_phase8::TestReportEngineCache` 5（`ReportEngine._cache_key` 等签名早已变更，
      `report_engine.py` 本轮未动）。前端 2 个 spec 文件 23 passed
  - [x] 7.2 变异全 RED、sha256 还原一致
    - 证据：`_env_mutation_check.py` E1–E12 **12/12 RED**（design §七清单逐条对应）；后端 9 条经 `sys.modules` 注入不改磁盘，前端 3 条改磁盘后立即还原，
      6 个生产文件变异前后 sha256 逐一相同。另：任务 1.3 的 S1–S5 5/5 RED
  - [x] 7.3 真栈：模板导出 + 密码
    - 证据（Playwright MCP 当时被并行会话占用，改用 Chrome DevTools 独立上下文）：界面「Tab 数据包 → 导出空白模板」输入密码后导出，
      请求体实测为 `{"cycles":[11 个循环],"password":"KbE2e-密码9"}`，响应 200 `application/zip`；下载文件 7 个条目**全部**带加密标志，
      UTF-8 密码可读、GBK 编码的同一密码报 Bad password。另经 API 对有底稿的项目（和平药房_2025，D+E）对照：不设密码 14 条目 / 7 张 Tab 模板，
      设密码后条目名逐一相同且全部加密，解密出的 xlsx 以 `PK` 开头
    - 🔴 如实：界面实测选的是底稿最少的「和平物流_2025」，它只有 3 份 T26 测试遗留的自定义底稿，353 张 Tab 全部 `resolve_instance_miss`，
      导出包里**一张底稿都没有**，界面仍提示「模板 ZIP 已导出」—— 见任务 8
  - _需求：7.1–7.4_
- [x] 8. 真栈暴露的四个问题（2026-09-30 用户批准「按上面的建议改这 4 条」；需求 8，设计 §八）
  - 原始现象：①导出 0 张底稿时静默成功（界面提示「已导出」，README 跳过原因只写 `resolve_instance_miss`）②「导出空白模板」
    声称不含项目数据，包内却固定附带审定报表 / 未审报表 / 附注 / 试算表 ③服务端按 UTF-8 加密，按 GBK 处理密码的解压软件判密码错误
    ④E、J 在 Tab 导入导出目录里 0 条登记，对话框可勾选，导出时既不进 files 也不进 skipped（和平药房_2025：D+E 导出只有 D 的 7 张）
  - [x] 8.1 后端：异常基类 + 两个 422；零 Tab 拦截与中文原因；README / `_底稿目录.xlsx` 中文跳过原因；模板模式不写附加文件；
    密码校验；`unsupported_cycles`；`cycle_options_for_ui()` 接入场景端点（同行编辑）
    - 证据：🔴 **实施前现算发现异常基类三个类早已定义但从未被抛出**（`exceptions.py` 有 `BulkTabUserError` /
      `BulkExportPasswordInvalidError` / `BulkExportNothingToExportError`，全仓 grep 零引用 = 死代码）⇒ 本轮做的是接线。
      `bulk_export_service`：Step 0 `_validate_password` 先于 `_require_zip_encryption`（422 先于 503）；Step 4b
      `if not manifest.files: raise`（在附加文件与增量清单之前）；Step 3b 抽成 `_write_project_data_files()` 并由
      `if mode == "data"` 门控、返回**实际写入**清单供 README 用；`total_items` 的 `+3` 同样只在数据模式计入；
      新增 `SKIP_REASON_LABELS` / `SKIP_REASON_ADVICE` / `NOTHING_VISIBLE_MESSAGE` 文案单一真源（README /
      `_底稿目录.xlsx` / 拦截提示三处共用，`manifest.json` 仍写英文代码）。
      `manifest_builder`：`_get_all_cycles` → 公开名 `supported_cycles()`；`BulkManifest.unsupported_cycles` 字段 +
      `to_dict()` 输出；逐循环先读 catalog，空即登记并 `continue`（在两次 DB 查询之前短路）。
      `scenario_registry`：`cycle_options_for_ui()` + `UNSUPPORTED_CYCLE_REASON`。
      `wp_bulk_router` **零增行**（现算三个被 writer 清册钉扎的函数 `bulk_import` L662 / `bulk_import_async` L746 /
      `bulk_import_rollback` L829 行号逐一未漂移）：导入与返回体两处都同行编辑
    - 🔴 **实施中抓到一个真缺陷（本轮新引入的代码里）**：`^[\x21-\x7E]+$` 会放行 `"pass55\n"` ——
      Python 的 `$` 除字符串末尾**还匹配末尾换行之前**，而加密用的是含 `\n` 的字节 ⇒ 用户在解压软件里输
      `pass55` 必然打不开。参数化用例抓到后改用**否定字符类** `[^\x21-\x7E]`（无锚点），顺带让前端那份
      JS 正则与后端语义严格一致（JS 的 `$` 行为与 Python 不同）。另加 `_INVISIBLE_CHAR_NAMES`：
      直接把 `\n` / 空格塞进错误文案，用户只会看到「含不支持的字符「」」
  - [x] 8.2 前端：对话框循环清单改后端下发、不支持循环置灰并显示原因；密码即时校验与提示、违规时按钮不可用；
    composable 两个导出加 `_silent`、超时 / 断网中文原因
    - 证据：`WpBulkDialog.vue` 删掉写死的 11 项 `availableCycles`，改 `ref<BulkCycleOption[]>` 由
      `loadScenarios` 从 `payload.cycles` 填充；`cycles` 缺失 ⇒ 与场景缺失同样显式报错（不退回写死列表）；
      `supportedCycles` / `unsupportedCycles` / `unsupportedNote`（按原因分组）三个 computed；复选框
      `:disabled="!cycle.supported"` + `:title` 给原因、下方常驻原因说明；默认只勾 supported；「全选」只作用于
      supported；从 ZIP 识别循环时同样只保留 supported；`PASSWORD_MAX_LENGTH` / `PASSWORD_FORBIDDEN_RE` /
      `passwordError` + `el-form-item :error` + 规则常驻提示，`canExecute` 加密码分支。
      `useBulkTabImportExport.ts` 两个导出加 `_silent: true`，`extractBlobError` 补 `ECONNABORTED` 与
      `navigator.onLine === false` 两条中文原因（拦截器加 `_silent` 后不再为它们弹提示）
  - [x] 8.3 用例：新增 `test_bulk_export_usability.py`；改写 `test_bulk_export_service.py`（契约反转 + 3 条过期断言）；
    `test_bulk_async_runner.py` 追加零 Tab 用例；密码用例改 ASCII；vitest 两文件追加
    - 证据：新建 `tests/services/test_bulk_export_usability.py` **43 例**（6 个跳过类别各一条可操作中文原因 /
      可见集全滤只给通用句且不泄露数量与编号 / 422 在附加文件与增量清单之前（用导出器替身调用数与
      `wizard_state` 双向取证）/ 模板模式**未调用**三个导出器 + 数据模式调用的正向对照 / 11 种非法密码 422 且
      `build_manifest` 未被 await / 5 种边界合法值不被误拒 / 422 先于 503 / 前后端常量交叉锁 / 真 catalog 的
      E、J 不支持 / `unsupported_cycles` 进 manifest.json / **真读 `_底稿目录.xlsx` 单元格**断言状态列中文 /
      场景端点与零 Tab 端点真发请求）。
      `test_bulk_export_service.py`：契约反转 `test_export_all_tabs_fail_still_produces_zip` →
      `…_is_rejected_not_an_empty_zip`（docstring 注明用户裁决）+ 新增 `test_export_one_success_keeps_fail_soft`
      正向对照 + 4 条 README 新判据；**3 条过期断言**按 HEAD 字节复跑确认为预存红后逐条更正（`"归档" in readme`
      数据模式从来没有这两字 · `readme.split("## 文件清单")` 的 `## ` 前缀从来不存在会抛 IndexError ·
      `len(xlsx_files) == 2` 漏算无条件写入的 `_底稿目录.xlsx`），并补上原先缺失的负向断言。
      `test_bulk_export_password_fail_closed.py` 密码常量改 ASCII + 新增 `_visible_all()`
      （端点层 `make_bulk_visible_filter` 在 MagicMock db 上 fail-closed 会剔除全部条目，改造前零 Tab
      照样出包故不影响判据，现在必须显式放行否则测到的是零 Tab 拦截而非加密链路）。
      `test_bulk_async_runner.py` 密码改 ASCII。vitest：`WpBulkImportExport.spec.ts` 两处 mock 补 `cycles` +
      新增 5 例（置灰与原因来自后端 / **不支持的循环不进导出参数** / `cycles` 缺失显式报错且不出现硬写循环名 /
      中文密码报错且按钮置灰且点了不发请求 + 改回合法即恢复的正向对照 / 超长密码）；
      `useBulkTabImportExport.password.spec.ts` 新增 6 例（两个导出带 `_silent` + 导入回滚**不**带的反向对照 /
      两个导出的超时中文原因 / 断网中文原因 / 422 中文原因原样展示且只弹一次）
  - [x] 8.4 变异全 RED（design §8.6 清单）、生产文件 sha256 还原一致；相关套件复跑、预存红归因
    - 证据：`_env8_mutation_check.py` **M1–M18 全部 18/18 RED**，5 个生产文件变异前后 sha256 逐字节一致。
      🔴 **首轮 17/18 —— M6（`build_manifest` 不记 `unsupported_cycles`）仍绿**，因为全部 43 例都用 `_world()`
      把 `build_manifest` 换成替身 ⇒ 这条逻辑**从未被真正执行过**。补 3 例真实调用（真 catalog 下 E 记入
      unsupported 且在两次 DB 查询前短路 / 支持的循环不被误判的正向对照 / `cycles=None` 默认范围）后 18/18。
      回归：bulk + scenario + manifest + catalog 共 27 个测试文件 **176 + 208 = 384 passed，零预存红**；
      前端两个 spec **34 passed**
    - 🔴 两条工具坑：①`get_diagnostics` 对我引入的 `SyntaxError: 'await' outside function` **完全没报**
      （重构脚本 dedent 多减一层把 `try:` 掉到模块顶层），是 `ast.parse` 抓到的 ⇒ 改 Python 后一律 `ast.parse` 自检
      ②变异脚本打印 `✅` 在 Windows gbk 控制台抛 `UnicodeEncodeError`，且那行 print 在 finally **之后**
      ⇒ 变异虽已还原但结论丢失 ⇒ 加 `sys.stdout.reconfigure(encoding="utf-8")` + 结论同时落盘
  - [x] 8.5 真栈复测（需求 8.7）
    - 证据（`_env8_livecheck.py` 对运行中的 9980，**5/5 通过**；库内 16 个项目）：
      ① 场景端点下发 **11 个循环**，不支持 = `['E', 'J']`，原因 = 「该循环暂未接入批量导入导出（平台尚未为其
      登记可导入导出的表格）」—— 同时证明后端已加载新代码 ② 中文密码 **422**，原因点名「审、计」两个字
      ③ 零 Tab 项目（某测试集团有限公司_2098）**422**：「没有可导出的底稿，已取消导出：有 81 张表格找不到
      对应底稿（尚未生成，或同一编号存在多份无法确定用哪份），请先在「底稿列表」点「生成底稿」。」——
      改造前这里静默返回空包并提示「模板 ZIP 已导出」，正是 7.3 记录的原始现象 ④ 和平药房_2024 模板包
      90 个条目，`_报表/` `_附注/` `_试算表/` **违规 0**，`_底稿目录.xlsx` 在 ⑤ README 实测：各循环状态逐个列出
      （D 导出 18 / 未导出 63，F 导出 69 / 未导出 2）· 未导出原因按类别给张数（未生成底稿 56 张、导出失败 9 张）
      + 中文明细 · 附加文件只列实际写入的两项 + 「模板包不附带报表、附注、试算表 —— 它们属于项目数据」
    - 副作用如实记录：判据 ②③④ 各触发一次真实导出请求，成功的那次按**既有行为**（非本轮引入）写了
      `projects.wizard_state['_last_bulk_export_manifest']`（导出元数据，不涉业务数据）；Task 7.3 已有同类先例
  - _需求：8.1–8.7_
