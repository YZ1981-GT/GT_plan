# Task 4 文件指纹与版本 fail-closed（交付证据）

> spec: `chain-closure-phase4-deliverable-center-trio` / 任务 4。append-only。
> 基线：HEAD `19c65589d`，分支 `work/2026-10-01-i-cycle-classification-convergence`。
> 需求：3.1–3.6, 7.3。

## 一、改了什么

### 1.1 统一指纹模块（单一真源）

新增 `backend/app/services/deliverable_file_fingerprint.py`：

- `compute_file_fingerprint(path, *, enforce_root=True) -> FileFingerprint(size, sha256)`：
  分块（64 KiB）读取算 SHA-256 + 大小；校验 is_file / size>0 / 可读；
  路径限制在交付根目录 `STORAGE_ROOT` 或系统临时目录下（防路径遍历/符号链接逃逸，
  `enforce_root=False` 用于历史落盘路径已迁移的 readiness 校验）。
- `verify_file_fingerprint(path, *, expected_sha256, expected_size, enforce_root)`：
  在 compute 基础上比对记录的大小/哈希，不一致抛 `file_hash_mismatch`。
- `FileFingerprintError(code, message, evidence)`：稳定 code（`missing_file` /
  `unreadable_file` / `file_hash_mismatch` / `path_escape`）+ 中文 message，
  与 readiness 硬闸门 code 对齐。

**三条路径共享此模块**（需求 3.3/3.4/3.5）：

1. `render_and_store` 落盘后 `compute_file_fingerprint` 校验通过才建版本；
2. readiness `_check_existing_version_files` 改用 `verify_file_fingerprint`
   （删掉原 `DeliverableReadinessService._sha256` 与 `hashlib` import，消除重复实现）；
3. 下载接口（Task 9 负责接线）将复用同一 `verify_file_fingerprint`。

### 1.2 `render_and_store` fail-closed 分段（需求 3.1/3.2/3.3）

`backend/app/services/deliverable_service.py`：

旧实现 fail-OPEN：写盘失败 `file_path=None` 后**仍 `create_version`**，留下
`file_path IS NULL` 的「成功」版本行（需求 8.2 明令反转的 blob 降级语义）。

新实现四段：① 落盘最终文件 → ② `compute_file_fingerprint` 校验（is_file/可读/size>0/
SHA-256）→ ③ 校验通过才 `create_version` 并绑定 `file_sha256`/`file_size`
（`snapshot_id` 若在 `source_snapshot_refs` 内）→ ④ 回填 task + flush。

任一段失败：

- `_cleanup_attempt_files(...)` 删本 attempt 落盘的临时/最终文件（**不**遍历目录、
  **不**删历史有效版本的文件）；
- `_purge_empty_placeholder_versions(task_id)` 删 `file_path IS NULL` 的占位版本
  （`create_task` 预建的空 v1），使 fail-closed 后该 task **零**「成功」版本行；
- 返回 `StoreResult(version=None, platform_persist_failed=True)`，**不**调用
  `create_version`。

`StoreResult.version` 改为 `Optional`，新增 `file_sha256` / `file_size`。

### 1.3 调用方 None 守卫（契约变更的连带防御）

`store.version` 可能为 None（落盘失败），逐一守卫，避免旧 fail-open 下
「返回指向不存在文件的成功版本」：

- `deliverable_center_integration.py`（export + reexport_terminal 两处）→ 返回失败字典；
- `onlyoffice_callback_service.py` → 返回 `{"error": 1}`（让 OnlyOffice 认定保存失败）；
- `deliverable_refresh_service.py`（refresh_section + refresh_all 两处）→ 抛 ValueError；
- `template_fill_service.py` → 抛 ValueError；
- `full_deliverables_executor.py`（disclosure 步骤）→ 抛 ValueError；
- `routers/deliverable.py` → 新增 `_ensure_store_succeeded(store)`，在报告正文/附注/
  财务报表三处生成端点落盘后调用，失败抛 HTTP 500 中文「文件未落盘或校验失败，无法出具」。
  （readiness/retry/download 端点与权限属 Task 9，本任务未动。）

## 二、修复前红 / 修复后绿

### RED-1（Task 1 基线）转绿

`tests/test_phase4_trio_baseline_red.py::TestRenderAndStoreFailClosed::test_write_failure_must_not_create_version`

- 修复前（HEAD）：`AssertionError: 写盘失败后不应创建版本，但发现 2 个版本行：
  [(1, None), (2, None)]`（create_task 占位 v1 + fail-open v2）。
- 修复后：**PASS**（0 版本行）。

### 旧 fail-open 测试已按新语义反转

`tests/test_deliverable_center_p0.py`：
`test_dual_path_downgrade_returns_blob_on_platform_failure`（断言写盘失败「版本记录仍留存」）
→ 改为 `test_platform_write_failure_is_fail_closed_no_version`（断言 `version is None` 且
版本链为空）。此为需求 8.2/3.1 明令反转的 blob 降级语义，非功能回归。
`test_deliverable_center_p0.py` 全文件 **17 passed**。

## 三、五类文件故障注入（需求 7.3）

测试文件：`backend/tests/test_phase4_file_fingerprint_fail_closed.py`。
命令：`..\.venv\Scripts\python.exe -m pytest tests/test_phase4_file_fingerprint_fail_closed.py -q`
（cwd=backend）。结果：**6 passed**。

故障注入纪律：注入在**被测函数下一层**（文件系统原语 / `deliverable_file_fingerprint`
指纹模块），**不替换** `render_and_store` 本身；每个用例先 `_assert_production_render_and_store()`
断言被测路径是生产实现。`render_and_store` 函数体内 `from ... import compute_file_fingerprint`
在每次调用时按模块属性重新绑定 ⇒ 对 `fp_module.compute_file_fingerprint` monkeypatch 生效。

| # | 故障 | 注入点（下一层） | 正向断言（fail-closed） |
|---|---|---|---|
| 1 | 文件写失败 | `Path.write_bytes` 抛 OSError | version=None、0 版本行 |
| 2 | 文件被删除 | 包装 `compute_file_fingerprint`：真实 `os.remove` 后走真实校验 → missing_file | version=None、0 版本行 |
| 3 | 文件被截断 | 包装 `compute_file_fingerprint`：截断为 0 字节后走真实校验 → unreadable_file | version=None、0 版本行 |
| 4 | 哈希不匹配 | 磁盘内容篡改 → `verify_file_fingerprint` 比对 SHA-256（+ readiness 既有版本校验） | 抛 `file_hash_mismatch` / readiness 产出 `file_hash_mismatch` 硬闸门 |
| 5 | 版本先写后校验 | 指纹校验抛错 + spy `create_version` | `create_version` 调用数=0、version=None、0 版本行 |

## 四、变异证明（revert-to-red，均已实跑）

### 变异 M1：render_and_store 回退 fail-open

在 `render_and_store` 的 except 分支去掉「清理 + 早返回 version=None」，改为伪造
`FileFingerprint(size=0, sha256="")` 继续 `create_version`（即旧 fail-open）。

实跑结果：**6 failed, 2 passed**——
`TestFault1/2/3/5` + `test_phase4_trio_baseline_red...test_write_failure_must_not_create_version`
+ `test_platform_write_failure_is_fail_closed_no_version` **全部转红**；
仅 `TestFault4`（哈希比对，与落盘顺序无关）保持绿。已 revert，复跑全绿。

### 变异 M2：verify_file_fingerprint 去掉 SHA-256 比对

把 `verify_file_fingerprint` 的哈希比对条件改为 `if False and ...`。

实跑结果：`TestFault4HashMismatch` 两条**全部转红**
（`test_verify_detects_content_change` + `test_readiness_surfaces_hash_mismatch`：
篡改后 `set()` 无 `file_hash_mismatch`）。已 revert，复跑全绿。

两个变异互补覆盖：M1 证明「校验先于建版本 + 失败不留版本」，M2 证明「哈希比对真生效」。

## 五、回归与归因

- phase4 定向：`test_phase4_file_fingerprint_fail_closed`（6）+ `test_phase4_readiness_gates`
  + `test_phase4_trio_snapshot_schema` + `test_deliverable_center_p0`（17）+
  `test_deliverable_refresh_inplace` + `test_deliverable_oo_edit_provenance` +
  `test_template_fill_service` = **87 passed**。
- StoreResult 契约连带：`test_deliverable_hash_pbt` + `test_deliverable_snapshot_pbt` +
  `test_deliverable_center_integration` + `test_deliverable_lineage_properties` +
  `test_deliverable_lineage_e2e` + `test_phase13_word_export` = **全绿**（119 passed/1 skipped 等）。
- `test_phase4_trio_baseline_red.py` 余 **4 red** 为**预期的 Task 5/7/8 范围**（TRIO_STEPS
  常量、retry attempt、保留失败原因），与本任务无关（见 baseline-task1.md §五、task3-snapshot-schema.md §七）。
- `test_onlyoffice_word_template_callback.py`（5 red）+ `test_deliverable_center_p1.py::
  test_onlyoffice_disabled_without_secret`（1 red）：以 `git stash` 把本任务改动全部移除后
  在**同一 HEAD** 复跑**同样 6 red** ⇒ **HEAD 预存红**（前者是 wp_onlyoffice_router 的
  404 路由装配问题，该文件 docstring 自述；后者是本机设了 ONLYOFFICE 密钥的环境依赖，
  task3-snapshot-schema.md §六已记）。本任务**未**触碰 `wp_onlyoffice_router`。

## 六、范围说明

- 本任务只做文件指纹统一校验 + `render_and_store` fail-closed + 调用方 None 守卫 +
  五类故障注入；**未**改 TRIO_STEPS（Task 5）、retry_failed（Task 8）、readiness/retry/
  download 端点与权限（Task 9）。
- 下载接口的物理哈希校验**接线**属 Task 9；本任务已把共享函数 `verify_file_fingerprint`
  备好，Task 9 直接复用即可（需求 3.5）。
- 一次性变异（M1/M2）已全部 revert，工作树只保留生产 fail-closed 实现。
