# Task 1.2 冻结契约 — file_path 存储边界与调用方盘点

> Spec: `attachment-ocr-ai-evidence-governance-hardening` · Wave 0 · Requirements **R1, R14**
> 设计锚点: design.md §3.1 信任边界 / §5.1 流式上传与异步 finalize read path / §6.3 legacy 调用方盘点

本文件冻结三件套：机器可读调用方清单 + 契约 + 契约测试。**本任务不改业务代码**，只盘点与冻结，供 Wave 2（task 3.4/3.5）实现 `StorageBoundaryResolver` / `LocatorProjection` 遵循，并作为 CI 漂移守卫的基线。

## 1. 冻结的三条契约

| 契约 | 内容 | 依据 |
|---|---|---|
| **C1 scope-first** | scope/capability 校验先于目标名称、路径、`stat/open/read`；不存在与无权访问使用同一脱敏错误 `SCOPE_NOT_FOUND_OR_FORBIDDEN`。 | R1.3, design §3.1(2) |
| **C2 boundary-before-IO** | 本地读取只能经 `StorageBoundaryResolver`；规范化后真实路径不在 `Storage_Boundary` 内时，字节读取器 `open/stat/read` 调用计数**必须为 0**。 | R1.3, design §5.1, P2 |
| **C3 opaque-locator** | 兼容响应中的 `file_path` 只能是 opaque locator / 脱敏 locator / 受控下载 URL，**禁止**返回绝对路径、storage key 或 token。 | R14.1, design §4.2/§6.1/§6.3 |

辅助冻结：**C4** 旧 ID 经 `LegacyAttachmentResolver`(alias 优先) 解析为确定根+版本，不静默当作当前版本；**C5** 附件读写/关联使用当前用户或明确 Service_Identity，禁止匿名新记录。

## 2. 已实证的 P0 缺口（当前代码）

| 位置 | 缺口 | 违反 |
|---|---|---|
| `attachments.py::download_attachment` / `preview_attachment` | `Path(file_path)` + `open(local_path,'rb')`，回退 `Path('storage')/file_path.lstrip('/')`；**无边界 containment**（`../` traversal / 绝对逃逸可读）。scope 校验先行（✅ C1），但 C2 缺失。 | C2 |
| `office_preview.py::_resolve_local_path` | `Path(file_path).exists()` 直解析，无 containment。 | C2 |
| `attachment_service.py::_to_dict` | 所有 list/get/search 响应返回**原始绝对 file_path**。 | C3 |
| `attachments.py::create_attachment` (`AttachmentCreate.file_path`) | 接受**客户端提供**的 file_path（不可信）。 | C1/C3 |
| `attachment_service.py::associate_with_wp` | `AttachmentWorkingPaper` 裸写入，无双端 scope/权限校验，`created_by` 可 None。 | C5（R3/R4，交 task 4.2） |
| `attachments.py::retry_ocr` | 无 `ocr.retry` capability 门禁。 | R5（交 task 5.2） |

Storage_Boundary 根：`settings.ATTACHMENT_LOCAL_STORAGE_ROOT`（附件）、`settings.STORAGE_ROOT` / `storage/`（底稿、模板、交付件、归档）。当前**不存在** `StorageBoundaryResolver`（Wave 2 新建）。

## 3. 调用方清单

机器可读清单：[`file_path_caller_inventory.json`](./file_path_caller_inventory.json)（21 条，含 owner / call_path / io_type / target_adapter / migration_phase / verification_evidence / due_date）。

分布：
- 附件面 (BE-ATT-01..10)：write-locator / write-bytes / expose-locator / download / preview / associate / lineage。
- 底稿面 (BE-WP-01..04)：download / export（xlsx/模板/preview-pdf）。
- 归档面 (BE-ARC-01..03)：archive（tar.gz / 云推送）/ export（交付件）。
- 前端 (FE-01..03)：consume-locator（download/preview URL、file_path 存在性判定）。

CI 漂移守卫：`test_evidence_file_path_boundary_contract.py` 断言清单结构完整、id 唯一、P0 高危面（download/preview/expose-locator/write-locator/archive）与关键调用方均在册。新增未登记 file_path 调用应先补清单。

## 4. 契约测试

`backend/tests/test_evidence_file_path_boundary_contract.py`（31 用例全绿）：

- **C1/C2 spy 测试**：`resolve_for_read` 参考模型 + `ByteIOSpy`，冻结「边界/权限失败 → `open/stat/read` 计数 == 0」；越界（traversal/绝对逃逸/UNC/paperless）与无 scope 均零 I/O 且脱敏。
- **C3 测试**：`project_locator` 投影 + `_looks_like_absolute_path` 探测器（含自检），冻结「兼容 file_path 绝不返回绝对路径」。
- **PBT**（全局 fast profile，max_examples=5）：P2 边界闭合（含 traversal 恒拒零 I/O）、P1/C3 locator 恒非绝对路径。
- **inventory 冻结**：结构/字段/覆盖校验。

参考模型是可执行规范：Wave 2 的真实 `StorageBoundaryResolver` / `LocatorProjection` 必须满足同一契约测试（届时替换参考模型为真实实现导入即可）。

运行：`python -m pytest tests/test_evidence_file_path_boundary_contract.py -v`（cwd=backend）。
