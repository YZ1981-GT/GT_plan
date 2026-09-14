# Task 12 辐射面实测记录

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
采集日期：2026-08-25（同日收口复核见文末「收口复核」一节）

辐射面按**引用关系反查**得出（不跑无边界全量：`backend/tests` 根目录 1522 个测试文件）：
扫 `backend/tests/**` 里对 `wp_file_resolver` / `resolve_wp_file` / `wopi_service` /
`WOPIHostService` / `wp_storage_service` / `WpStorageService` / `find_template_file_any` /
`_hide_non_target_sheets` / `workpaper_sync` 的实际引用，得 22 个相关文件。

## 结果

| 测试文件 | 结果 | 说明 |
|---|---|---|
| `backend/tests/workpaper_sync/**`（6 文件） | 264 passed | 含 Task 12 新建 127 例 |
| `backend/tests/wp_export/test_wp_file_resolver.py` | passed | verdict 取值域断言已同步（新增 2 档） |
| `backend/tests/services/test_wp_download_manifest.py` | passed | `_VERDICT_ADVICE` 补齐 2 档中文处置建议 |
| `backend/tests/services/test_wp_export_self_evidence.py` | passed | verdict 取值域断言已同步 |
| `backend/tests/test_workpaper_writer_inventory.py` | 26 passed | 清册重生成 + Wave 0 特征守卫改允许清单 |
| `backend/tests/test_custom_workpaper_oo_file_resolution.py` | passed | — |
| `backend/tests/test_onlyoffice_single_file_dockey.py` | passed | — |
| `backend/tests/test_wopi_working_paper_qc_review.py` | 42 例由 ERROR→可执行 | 见下「顺带修复」 |
| `backend/tests/test_archive_orchestrator.py` / `test_archive_deprecated.py` | 18 例由 ERROR→可执行 | 同上 |
| `backend/tests/test_wp_onlyoffice_router.py` | **26 failed（先前已存在，与 Task 12 无关）** | 见下「已排除」 |

合计：418 passed / 26 failed，26 failed 全部为先前已存在且与本任务无关。

## 顺带修复（阻塞辐射面验证的 Task 9 ORM 缺陷）

`backend/app/models/workpaper_sync_models.py` 的
`WorkpaperEntryEvidenceScenario` 五个 JSONB 列写了
`server_default=sa.text("'[]'::jsonb")`。`::jsonb` 是 PG 专属语法，被 SQLAlchemy 原样
塞进 `CREATE TABLE`；SQLite 解析到 `:` 直接 `unrecognized token: ":"` ⇒
**任何用 `Base.metadata.create_all(sqlite)` 的测试在 setup 阶段就 ERROR**。

实测辐射面 60 例（`test_wopi_working_paper_qc_review` 42 + `test_archive_orchestrator` 15
+ `test_archive_deprecated` 3）。改为 `sa.text("'[]'")`（PG 对 jsonb 列的 `DEFAULT '[]'`
会隐式转型，真实表由 V151 SQL 创建，ORM 的 server_default 只影响 DDL 生成）。

已用只读探针证明该缺陷与 Task 12 无关：只 import `app.models.workpaper_sync_models`
（`sys.modules` 里零 Task 12 模块）即可复现 DDL 渲染失败。

## 已排除：`test_wp_onlyoffice_router.py` 的 26 例 404

判据（探针实测）：

1. 该测试文件对 `wopi_service` / `wp_storage_service` / `wp_file_resolver` /
   `workpaper_sync` / `canonical_paths` 的引用数 **全部为 0**
   （文件里的 `_resolve_wp_file` 是 router 自己的私有函数，同名不同物）；
2. 每个用例自建 `FastAPI() + include_router(router)`，而
   `wp_onlyoffice_router.router` 只挂 4 条路由；被断言 404 的
   `/api/workpapers/onlyoffice/health`、`/wopi/files/{file_id}` **都不在这个 router 上**
   （真实 `app.main` 里两者均已注册，共 2175 条路由）；
3. `import app.routers.wp_onlyoffice_router` 成功，无循环导入。

⇒ 404 由测试自建 app 未包含对应 router 造成，属先前已存在问题，不在 Task 12 范围内。

## 未修复但已登记

`test_phase8.py::TestReportEngineCache`（5 例，Redis 相关）、
`test_wopi_working_paper_qc_review` 剩余 16 例（QC 规则表为空 / 响应信封形态变化）、
`test_archive_deprecated` 2 例（`X-Confirmation-Token` 中间件）——
均为其他 spec 的先前已存在失败，与 Task 12 改动无引用关系。

## 收口复核（2026-08-25 第二轮，独立会话）

上一轮被中断在「任务未标完成」处，本轮**实跑**复核而不读旧结论，并补齐两处真实缺口。

### 实跑结果（仓库根，`.venv\Scripts\python.exe`）

| 命令 | 结果 |
|---|---|
| `pytest backend/tests/workpaper_sync/test_task12_canonical_resolver.py` | **99 passed**（收口前 94，+5） |
| `pytest backend/tests/workpaper_sync/test_task12_resolution_pg.py` | **37 passed**（收口前 33，+4） |
| `pytest backend/tests/workpaper_sync/`（含 Task 9/10/11） | **264 → 273 passed** |
| `mutate_task12_canonical_resolver_guards.py --check-anchors` | **52/52 OK，0 MISS**；只读性核验通过（md5 全未变、无 `.mutbak`） |
| `mutate_task12_canonical_resolver_guards.py --list` | 通过（52 条声明、2 个分母文件全部可定位） |
| `mutate_task12_canonical_resolver_guards.py --run all` | **52/52 RED**，覆盖面 2/2，基线 136 passed / 失败集合空集 |
| 辐射面 11 个文件（见下） | **441 passed / 0 failed** |

### 本轮补齐的两处缺口

1. **Task 12 第 3 条后半句此前零判据**：「finalize 只创建新的 immutable
   representation，不改旧 row 或 business revision」。收口前的 candidate 用例
   (a)~(g) 只覆盖前半句（不可解析 / 不可 current / 前置不齐不可 finalize），
   **成功 finalize 之后的世界**没有任何断言。补 `_collect()` 第 ③bis 段：真把
   candidate 补成 ready、真发布 gen-4 artifact、真跑
   `repository.finalize_candidate()`，前后各拍 `to_jsonb` 快照逐项比对
   （`TestCandidateFinalizeIsAdditiveOnly`，4 例）。
   变异 **M51**（注入 `content_revision + 1`）与 **M52**（不绑定新 representation ⇒
   命中 `ck_wpruc_finalized_pointer`）证明它可 falsify。
   *否定式承诺（「不改 X」）只能靠注入反例证明判据有效 —— 短路式变异对它无效，
   因为生产代码里本来就没有那条语句可短路。*

2. **`resolve_template_docx` 是零消费方 + 零测试的新增能力**（假绿第①源）。
   收口前 P40/P41 的判据全部建立在 monkeypatch 过的 tmp 模板根上，证明「判据函数
   正确」；而 Requirement 9.4 点名的是真实库上的行为。实测真实库：
   `find_template_file_any("B12-1")` → `B\B12 与相关人员访谈程序及记录.xlsx`（父级
   XLSX），`find_template_file_any("A9-1")` → 自己的 DOCX —— 即 Requirement 9.4
   原文所指「只对 A 类特殊处理」的缺陷仍在（本体归 **Task 58**，矩阵已登记
   `blocking_task=58`）。补 `TestProperty40And41OnRealTemplateLibrary`（4 例）落在
   真实 `backend/wp_templates/` 上，并顺带修出一处真缺陷：该入口传了
   `blank=True`，缺模板时终态是 `empty`（文案「未配置底稿文件路径」）而它根本不读
   `file_path` ⇒ 把部署缺件误导成数据没填；改 `blank=False`（`missing`）。
   变异 **M49**（去掉类型门）/ **M50**（`blank` 退回 `True`）逐条 RED。
   同时补 `test_template_finder_deferral_names_94_and_the_bridge`：把「9.4 归谁 +
   Task 12 给了什么」锁进矩阵 reason（与既有 OO router 9.12 那条守卫对称）。

### 顺带的派生重生成（源码一动就必须重跑，否则 fail-closed 判据打红）

* `backend/data/workpaper_writer_inventory.json` —— `wp_file_resolver.py` 改了 2 行即
  触发 `test_inventory_on_disk_matches_the_ast` 的 source-digest 门（这是设计如此）。
  `generate_workpaper_writer_inventory.py --apply` 后 26 passed。
* `backend/data/workpaper_resolver_migration_matrix.json` —— 矩阵携带
  `inventory_digest`/`inventory_source_digest`，随上一步一起重生成
  （`--apply`）。核对：**79 行 / migrated 13 / regressed 0 / deferred 全带
  reason+blocking_task**，migrated 行集与收口前逐项相同（无新增、无丢失）。

### 已排除的既存失败（两处，均已用探针证明与 Task 12 无引用关系）

* `test_wp_onlyoffice_router.py` —— **26 failed**，与上一轮记录数字一致，成因见上文。
* `test_wp_template_finder_d4_prefix.py` —— **7 failed**。判据：失败是
  `AttributeError: module 'app.services.wp_template_finder' has no attribute
  '_wp_code_filename_prefix_ok' / 'find_whole_workbook_template'`，而
  `wp_template_finder.py` 与 `git show HEAD:` **逐字节相同**，且这两个函数在 HEAD
  与工作树里**都不存在** ⇒ 该测试文件是按另一版模块写的，属其他 spec 的既存失败。

### 本轮辐射面（按引用关系反查，11 个文件 / 441 passed）

`backend/tests/workpaper_sync/**`、`wp_export/test_wp_file_resolver.py`、
`services/test_wp_download_manifest.py`、`services/test_wp_export_self_evidence.py`、
`test_custom_workpaper_oo_file_resolution.py`、`test_onlyoffice_single_file_dockey.py`、
`test_workpaper_writer_inventory.py`、`test_a16_prefilled_download_placeholder.py`、
`test_word_template_structure_endpoint.py`、`test_wp_template_preview_pdf.py`、
`test_wp_program_extract.py`。

### 收口时踩到并记下的一条工具坑

用 `Get-Content -Raw … | Set-Content -Encoding UTF8` 改
`mutate_task12_canonical_resolver_guards.py`，PS 5.1 以 GBK 解码 UTF-8 源码，整份文件
中文变 mojibake 且部分换行被 best-fit 吞掉 ⇒ `IndentationError`。该文件是 untracked
（`??`），git 无法还原，最终靠 **Kiro local history**
（`%APPDATA%\Kiro\User\History\<hash>\entries.json`）取到上一版精确还原。
⇒ 改文件一律用编辑工具或 `Path.write_text(encoding='utf-8')`，**不要**走 PS 管道。
