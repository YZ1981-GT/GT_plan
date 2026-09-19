# Requirements Document

## Introduction

本 spec 为**项目级底稿批量导入导出（ZIP）**功能：在一个审计项目内，一键导出全部可离线填写的底稿 Tab 模板（ZIP）→ 线下 Excel 填写 → 一键导入全部已填数据（ZIP）→ 一键导出全部已填数据（ZIP），用于外勤批量填表、项目归档与跨人协作。

需求来源为需求对齐文档 `docs/proposals/workpaper-bulk-tab-import-export-requirements.md`（v1.4）。该文档已明确：**终局纳入全部底稿（A~S 全循环），首期 D 循环试点**；命名规则 normative 真源为其 §8.6。

**前置条件（已满足）**：本功能是 **ACNR（地址坐标名称注册中心）** 的消费者之一。ACNR spec（`.kiro/specs/acnr/`）已完成——含 L1 `global_catalog.json`、`resolve_instance`、bulk manifest 服务 `app/services/acnr/manifest.list_import_export`（D 循环 + 扩 K/F/G/H），以及编排预备层 `app/services/wp_bulk_tab_export.py`（`list_export_sheets` / `list_import_sheets` / `_topological_sort`，已带单测与 PBT）。因此本 spec 的门禁（ACNR Phase 0 G1–G8 + Phase 1）已通过，可正式开发。

**范围原则（复用而非新建）**：
- **不新造 xlsx 列契约**：ZIP 内每个 Tab 的 Excel 格式 100% 复用现有单表 I/E 端点（`POST /api/workpapers/{wp_id}/{prefix}/{export-template|export-data|import-data}?sheet={sheet_code}`）。
- **不新造 manifest 真源**：路由元数据只认 ACNR catalog 的 `api_prefix + item_id`（经 `manifest.list_import_export`）。
- **不新造排序逻辑**：导入/导出顺序复用 `wp_bulk_tab_export._topological_sort`（按 `depends_on_sheets` 拓扑 + `import_order` tiebreaker）。
- **快照/回滚复用版本链**：导入前快照复用 workpaper version-trail（`POST /versions`），失败可回滚。
- 本 spec 只做**编排层 + 端点 + 前端 + 导入报告 + dry-run + 异步/SSE + 权限/工作流门禁**，不重写执行层。

## 已确认决策（对齐文档 Q1–Q9 / N-Q / P-Q）

| 项 | 决议 | 依据 |
|----|------|------|
| **Q1 范围** | 终局全部底稿；**首期 D 循环试点**（~96 可 I/E Tab） | 对齐文档已确认 |
| **Q2 「全部底稿」定义** | **A**：仅本项目**已实例化**底稿（`wp_index ⋈ working_paper` 有 `wp_id`）。未实例化/不适用底稿在 manifest 标 `skip_reason`，**不自动创建实例**（首期） | 首期收敛，避免副作用 |
| **Q3 模板/数据边界** | 导出模板**预填项目基础信息**（被审计单位/年度/编制人写入 manifest + README，首期不强制写入每个 xlsx 单元格）；**允许部分文件导入**（manifest 驱动，ZIP 中缺失文件跳过并报告）；**支持仅导入某一循环**（cycle 过滤） | 灵活性与安全兼顾 |
| **Q4 冲突策略** | 可配置，**默认覆盖（overwrite）**；提供 **仅填空（fill-empty）** 与 **拒绝（reject-on-conflict）**；**合并（merge by 主键）延后至后续 Phase**，首期不做 | merge 需稳定主键，复杂度高 |
| **Q5 工作流状态门禁** | `review_passed`/`archived`/锁定 底稿**禁止导入**；`under_review` 底稿导入前**回退为编制中**并记审计日志；**不设独立导入审批门**（首期），依赖快照+回滚+审计日志 | 保护复核结论 |
| **Q6 与现有批量导出关系** | **并存**：Tab 结构化数据包（本功能）vs 整份底稿文件（现有 `batch-export`），UI 明确区分 | 粒度不同 |
| **Q7 离线填写** | ZIP 内含 `README.txt`（每 Tab 链编制提示）；Mac Excel/WPS 兼容复用单表 I/E 现有列头编码/日期兼容，不额外处理 | 复用既有 |
| **Q8 归档与交付** | 「导出全部数据」**可作归档格式**（纳入交付物清单，optional）；**密码保护 ZIP 延后**（optional） | 非首期核心 |
| **Q9 验收** | 见本文末 MVP 验收场景（4 条） | — |

## Glossary

- **Bulk_ZIP**：项目级底稿批量导入导出的 ZIP 包（模板包或数据包）。
- **Manifest**：ZIP 内的 `manifest.json`，记录每个文件的 `addr_id`/`wp_code`/`sheet_code`/`sheet_name`/`api_prefix`/`item_id`/`wp_id`/`zip_path`/`sha256`/`origin`/`skip_reason` 等路由元数据（字段遵循对齐文档 §8.6.6）。
- **BulkExport_Service**：批量导出编排服务，基于 `wp_bulk_tab_export.list_export_sheets` 组装 ZIP。
- **BulkImport_Service**：批量导入编排服务，基于 `wp_bulk_tab_export.list_import_sheets` 按拓扑顺序路由到单表 import。
- **ACNR_Manifest**：ACNR 的 `app/services/acnr/manifest.list_import_export(db, project_id, cycle?)`，manifest 路由元数据的唯一真源。
- **单表 I/E 端点**：现有 `POST /api/workpapers/{wp_id}/{prefix}/{export-template|export-data|import-data}?sheet={sheet_code}`，Excel 格式的唯一执行层。
- **DryRun（预检）**：导入正式写库前的校验模式，校验表头/文件完整性/工作流状态，不写库，返回逐文件报告。
- **Snapshot（快照）**：导入前经 version-trail 创建的底稿快照，用于失败回滚。
- **ConflictStrategy（冲突策略）**：`overwrite`（默认）/ `fill-empty` / `reject`，见 Q4。
- **ImportReport（导入报告）**：逐 sheet 的 `success`/`partial`/`failed` + 导入行数 + 错误信息汇总。
- **skip_reason**：manifest 中标注某 Tab 不纳入 bulk 的原因（无 I/E / Univer / OnlyOffice / Word / 只读目录 / custom）。
- **row_limit**：单表 I/E 已有的行数上限（如 500 行），bulk 超限时 per-sheet 告警而非整包失败。
- **wp_code / sheet_code / addr_id**：见对齐文档 §8.6 三层寻址（L1/L2/L3）。
- **异步任务 + SSE**：大项目导出/导入复用现有 `batch-export-async` / SSE 进度模式。

---

## Requirements

### Requirement 1: 一键导出全部模板（ZIP）

**User Story:** 作为审计助理，我希望按项目一键下载所有可离线填写的 Tab 空白模板，以便在外勤统一填表，无需逐 Tab 点击。

#### Acceptance Criteria

1. WHEN 用户请求导出模板并选择一个或多个审计循环时，THE BulkExport_Service SHALL 仅纳入该项目**已实例化**（`wp_index ⋈ working_paper` 有 `wp_id`）的底稿。
2. THE BulkExport_Service SHALL 支持按审计循环多选（如仅 D、或 D+K），并 WHERE 未指定循环时导出全部已启用循环。
3. WHEN 为每个可 I/E 的 Tab 生成 xlsx 时，THE BulkExport_Service SHALL 调用该 Tab 对应的单表 `export-template` 端点（api_prefix + sheet_code 源自 ACNR_Manifest），使列头与当前项目配置（含账龄段口径）一致。
4. THE Bulk_ZIP SHALL 按目录结构 `{cycle}/{parent_wp_code}/{sheet_code}_{short_label}_模板.xlsx` 组织文件（命名遵循对齐文档 §8.6.6）。
5. THE Bulk_ZIP SHALL 包含 `manifest.json`，为每个文件列出 §8.6.6 规定的路由元数据（addr_id/wp_code/sheet_code/sheet_name/api_prefix/item_id/wp_id/zip_path/origin），并含 `exported_at`/`exported_by`/`platform_version`。
6. WHERE 一个 Tab 无 I/E 能力或不可纳入，THE BulkExport_Service SHALL 跳过该 Tab 并在 manifest 中以 `skip_reason` 标注原因，SHALL NOT 因此使整包失败。
7. THE Bulk_ZIP SHALL 包含 `README.txt`，说明使用方法并逐 Tab 链接到编制提示。
8. IF 某 Tab 的 `wp_id` 未解析（resolve_instance miss），THEN THE BulkExport_Service SHALL 跳过该 Tab 并记录警告，SHALL NOT 使整包失败。

---

### Requirement 2: 一键导入全部已填数据（ZIP）

**User Story:** 作为审计助理，我希望将线下填好的 ZIP 一次性导回项目，以便避免逐 Tab 导入，并在出错时安全回滚。

#### Acceptance Criteria

1. WHEN 用户上传数据 ZIP 时，THE BulkImport_Service SHALL 依据 `manifest.json` 将每个 xlsx 按 `wp_id` + `api_prefix` + `sheet_code` 路由到对应的单表 `import-data` 逻辑。
2. THE BulkImport_Service SHALL 按 `wp_bulk_tab_export.list_import_sheets` 的拓扑顺序（`depends_on_sheets` 优先，`import_order` tiebreaker）逐 sheet 导入，使被依赖 sheet 先于依赖它的 sheet。
3. WHEN 用户以 DryRun 模式提交时，THE BulkImport_Service SHALL 校验表头、文件完整性与工作流状态但**不写库**，并返回逐文件预检报告。
4. WHEN 正式导入前，THE BulkImport_Service SHALL 为待写入的每个底稿创建 Snapshot（复用 version-trail），且 IF 导入过程中任一 sheet 失败，THEN THE BulkImport_Service SHALL 依所选原子性策略回滚到导入前快照。
5. THE BulkImport_Service SHALL 返回 ImportReport，逐 sheet 给出 `success`/`partial`/`failed`、导入行数与错误信息。
6. THE BulkImport_Service SHALL 支持可配置的 ConflictStrategy（`overwrite` 默认 / `fill-empty` / `reject`），并按所选策略处理库中已有数据。
7. WHERE 某 sheet 导入行数超过其单表 `row_limit`（如 500），THE BulkImport_Service SHALL 对该 sheet 告警并记入报告，SHALL NOT 使整包失败。
8. IF ZIP 中缺少 manifest 所列的某个文件（用户删改），THEN THE BulkImport_Service SHALL 跳过该文件并在报告中标注 `missing`，继续导入其余文件。
9. IF ZIP 中存在 manifest 未登记的文件，THEN THE BulkImport_Service SHALL 忽略该文件并在报告中标注 `unlisted`。

---

### Requirement 3: 一键导出全部已填数据（ZIP）

**User Story:** 作为项目经理，我希望一键打包本项目全部已填 Tab 数据，以便归档或发给复核人离线查看。

#### Acceptance Criteria

1. THE BulkExport_Service SHALL 以与 Requirement 1 相同的目录结构与 manifest 导出已填数据，仅将模式设为 `data`（文件名后缀 `_数据.xlsx`）。
2. WHEN 模式为 `data` 时，THE BulkExport_Service SHALL 调用各 Tab 的单表 `export-data` 端点，导出内容为当前库内数据而非空白模板。
3. WHERE 用户勾选「仅导出有数据的 Tab」，THE BulkExport_Service SHALL 跳过无数据的 Tab 以减少空文件，并在 manifest 中标注被跳过的 Tab。

---

### Requirement 4: 导入后系统内行为

**User Story:** 作为审计助理与复核人，我希望导入后底稿联动正确、复核状态规则不被破坏、且操作可追溯。

#### Acceptance Criteria

1. WHEN 一次导入成功写入数据后，THE BulkImport_Service SHALL 触发相关底稿的公式重算/跨表联动（如 D2-2 明细 → D2-1 审定 SUMIF），复用现有单表 import 的 `WORKPAPER_SAVED` 事件链。
2. THE BulkImport_Service SHALL 将每次导入记入审计日志，含操作人、时间、导入文件数、成功/失败 sheet 数。
3. WHEN 导入目标底稿处于 `under_review` 状态时，THE BulkImport_Service SHALL 在写入前将该底稿状态回退为编制中并记审计日志。
4. IF 导入目标底稿处于 `review_passed`/`archived`/锁定 状态，THEN THE BulkImport_Service SHALL 拒绝该底稿的导入并在报告中标注 `blocked_by_status`（见 Requirement 9）。

---

### Requirement 5: 入口与权限

**User Story:** 作为不同角色用户，我希望批量导入导出入口清晰、权限受控，以便安全使用。

#### Acceptance Criteria

1. THE 前端 SHALL 在项目底稿列表/批量操作区提供「导出全部模板」「导入全部数据」「导出全部数据」三个入口，与现有整份底稿文件批量导出（`WpBatchExportDialog`）并列且明确区分。
2. WHEN 用户请求导出（模板或数据）时，THE 后端 SHALL 要求至少只读权限。
3. WHEN 用户请求导入时，THE 后端 SHALL 要求编制权限（复用 `require_wp_edit_permission`），作为安全边界强制校验。
4. WHEN 用户请求回滚时，THE 后端 SHALL 要求项目经理或同等角色权限。
5. IF 项目为只读或已锁定，THEN THE 后端 SHALL 拒绝导入请求。

---

### Requirement 6: 非功能——性能、可靠性、异步

**User Story:** 作为处理大项目的审计助理，我希望批量操作在 Tab 数量很多时仍稳定、不超时、可回滚。

#### Acceptance Criteria

1. WHERE 单项目待处理 Tab 数量超过阈值（如 100），THE BulkExport_Service 与 BulkImport_Service SHALL 以异步任务执行并通过 SSE 上报进度，复用现有 `batch-export-async` / SSE 模式。
2. THE BulkImport_Service SHALL 通过快照支持回滚，避免「导入一半项目数据不一致」。
3. THE Bulk_ZIP SHALL NOT 包含任何密钥或 Token。
4. THE Manifest SHALL 携带 `exported_at`、`exported_by`、`platform_version` 以保证可追溯。
5. WHEN 组装或解析 ZIP 时，THE 服务 SHALL 对单文件大小与 ZIP 总大小施加上限，且 IF 超限，THEN SHALL 拒绝并返回明确错误。

---

### Requirement 7: Manifest 契约与 ACNR 依赖

**User Story:** 作为平台维护者，我希望 bulk 的路由元数据 100% 来自 ACNR，杜绝名称漂移与手写清单。

#### Acceptance Criteria

1. THE BulkExport_Service 与 BulkImport_Service SHALL 仅从 ACNR_Manifest（`manifest.list_import_export`）获取每个 Tab 的 `api_prefix` + `item_id` + `storage_field` + `depends_on_sheets` + `import_order` + `wp_id`，SHALL NOT 手写 sheet 清单或从 `d*_import_export.py` 动态提取。
2. THE Manifest SHALL 使用 ACNR 的 `addr_id` 作为每个文件的稳定主键。
3. WHEN ACNR_Manifest 对某 sheet 返回 `skip_reason` 时，THE BulkExport_Service SHALL 将该 sheet 以 `skip_reason` 标注并排除出可填文件集。
4. IF ACNR catalog 加载失败，THEN THE 服务 SHALL 返回明确错误并拒绝生成 manifest，SHALL NOT 静默退回分散的 JSON 源。

---

### Requirement 8: 冲突策略（导入时库中已有数据）

**User Story:** 作为审计助理，我希望在导入到已有数据的底稿时能选择如何处理冲突，以免误覆盖已编制内容。

#### Acceptance Criteria

1. WHEN ConflictStrategy 为 `overwrite`（默认）时，THE BulkImport_Service SHALL 以 ZIP 为准，全量替换该 `item_id` 的行数据。
2. WHEN ConflictStrategy 为 `fill-empty` 时，THE BulkImport_Service SHALL 仅写入库中为空的字段/行，SHALL NOT 覆盖已有编制内容。
3. WHEN ConflictStrategy 为 `reject` 时，IF 某 sheet 的目标 `item_id` 库中已有非空数据，THEN THE BulkImport_Service SHALL 使该 sheet 导入失败且不部分写入，并在报告中标注 `conflict_rejected`。
4. THE ConflictStrategy SHALL 对整包导入统一适用，并在 ImportReport 中回显所用策略。

---

### Requirement 9: 工作流与状态门禁

**User Story:** 作为复核人，我希望批量导入不破坏已完成的复核结论。

#### Acceptance Criteria

1. IF 导入目标底稿处于 `review_passed`/`archived`/锁定 状态，THEN THE BulkImport_Service SHALL 拒绝该底稿导入并在报告中标注 `blocked_by_status`，且继续处理其余底稿。
2. WHEN 导入目标底稿处于 `under_review` 状态且用户有编制权限时，THE BulkImport_Service SHALL 将其状态回退为编制中后再写入，并记审计日志。
3. THE BulkImport_Service SHALL NOT 在无编制权限时改变任何底稿状态或写入任何数据。

---

## MVP 验收场景（Q9）

1. 选定测试项目，一键导出 D 循环全部模板 ZIP，线下填 3 张代表表（审定 D2-1 / 明细 D2-2 / 检查表），一键导入后系统内数据与手工录入一致。
2. 导入后 D2-1 审定表与 D2-2 明细表 SUMIF 联动正确。
3. 导入过程某 sheet 失败时整包可回滚到导入前快照，项目数据不出现半写入不一致。
4. （可选）500+ Tab 项目异步导出在 10 分钟内完成，SSE 进度可见。

## 范围外（首期不做）

- 合并（merge by 主键）冲突策略（Q4 延后）。
- 未实例化/不适用底稿导入时自动建实例（Q2 = A）。
- 密码保护 ZIP / 加密 manifest（Q8 延后）。
- OnlyOffice / Univer 在线表、Word 模板、程序表、函证流程态、OCR 附件、AI 生成字段的 bulk（对齐文档 §4.3 skip 类型；manifest 中以 `skip_reason` 标注）。
- 自定义底稿（`CUST-*`）bulk 导出（首期 `skip_reason=custom_univer_only`，二期评估）。
