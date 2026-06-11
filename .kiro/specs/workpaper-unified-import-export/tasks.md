# Implementation Plan: 底稿统一导入导出

## Overview

按 Phase 递进实施：基础设施（DDL+ORM+DTO）→ 导出引擎 → 导入引擎 → 冲突与校验 → 批量与模板 → 前端 → 收尾。每个 Phase 内部含 PBT 必做子任务，确保增量可验证。

> **🔴 复用铁律（2026-06-11 codegraph 复盘）**：本 spec 大部分能力已存在，见 design.md「现状复用与真实空白」章节。任务中标 **【复用】** 的必须扩展现有服务，**禁止重建**；标 **【新建】** 的才是真实空白。现有产物：`wp_xlsx_export_service.export_workpaper_xlsx`（单底稿 xlsx 导出）/ `WpDownloadService.download_pack`（批量 ZIP）/ `WpUploadService.upload_file`+`check_version_conflict`（导入+版本冲突）/ `offline_conflict_service`（字段级冲突）/ `wp_download.py` 路由 / `test_xlsx_export_roundtrip.py`。

## Tasks

### Phase 1: 基础设施

- [ ] 1. 数据库迁移与 ORM 模型
  - [ ] 1.1 创建 V069__wp_export_import_tables.sql
    - CREATE TABLE IF NOT EXISTS wp_export_snapshot（全部列+索引）
    - CREATE TABLE IF NOT EXISTS wp_version_archive（全部列+UNIQUE约束）
    - 两表均含 created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    - _Requirements: 1.5, 4.1, 6.1, 6.2, 6.3_
  - [ ] 1.2 创建 R069__wp_export_import_tables.sql 回滚脚本
    - DROP TABLE IF EXISTS wp_version_archive; DROP TABLE IF EXISTS wp_export_snapshot;
    - _Requirements: 1.5, 6.1_
  - [ ] 1.3 创建 ORM 模型 WpExportSnapshot + WpVersionArchive
    - 文件: backend/app/models/wp_export_models.py
    - Mapped 列与 DDL 一一对应（三层一致铁律）
    - 在 audit_platform_models.py 中 import 注册
    - _Requirements: 1.5, 4.1, 6.1, 6.2_
  - [ ] 1.4 创建 DTO/Schema 定义
    - 文件: backend/app/schemas/wp_export_schemas.py
    - MetadataBundle, ExportResult, ConflictResolution, ConflictResult, ValidationLevel, ValidationItem, ValidationReport, ImportResult, BatchExportResult, CopyResult
    - _Requirements: 3.1, 3.2, 4.3, 4.4, 5.6, 6.2_

- [ ] 2. Checkpoint - 三层一致性验证
  - 确保 DDL 列、ORM Mapped 列、DTO 字段三层对齐，运行 schema drift 检测无 critical。如有问题停下询问用户。


### Phase 2: 导出引擎

- [ ] 3. MetadataCodec 元数据编解码器
  - [ ] 3.1 实现 MetadataCodec 类
    - 文件: backend/app/services/wp_export/metadata_codec.py
    - embed_xlsx: 写入 xlsx Custom Properties (wp_code, project_id, file_version, export_timestamp, preparer, reviewer, review_status)
    - embed_docx: 写入 docx core properties + custom properties
    - extract_xlsx / extract_docx: 提取元数据返回 MetadataBundle | None
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ] 3.2 Property 2: Metadata Embed-Extract Round-Trip
    - **Property 2: 对任意有效 MetadataBundle，embed→extract 返回相同值**
    - hypothesis max_examples=5, 策略 st_metadata_bundle()
    - **Validates: Requirements 1.4, 3.1, 3.2, 3.3**

- [ ] 4. 确定性序列化与快照哈希
  - [ ] 4.1 实现 serialize_cell_value + compute_snapshot_hash
    - 文件: backend/app/services/wp_export/serialization.py
    - 固定列顺序、Decimal(20,4)、ISO-8601 日期、None 处理
    - SHA-256 哈希：sheet 按名称字母序、row 按原始序
    - _Requirements: 10.2, 1.5, 4.1_
  - [ ] 4.2 Property 3: Snapshot Hash Determinism
    - **Property 3: 同内容多次哈希结果相同；不同内容哈希不同**
    - hypothesis max_examples=5
    - **Validates: Requirements 1.5, 4.1**
  - [ ] 4.3 Property 5: Deterministic Serialization
    - **Property 5: 同内容两次独立序列化产生 byte-identical 单元格值**
    - hypothesis max_examples=5
    - **Validates: Requirements 10.2**

- [ ] 5. WpExportEngine 核心导出 **【复用】wp_xlsx_export_service**
  - [ ] 5.1 实现 WpExportEngine.export_single（薄封装层）
    - 文件: backend/app/services/wp_export/export_engine.py
    - **xlsx 导出直接调用现有 `wp_xlsx_export_service.export_workpaper_xlsx`**（已实现 4 路径写入+公式保留+Semaphore10），禁止重写填值逻辑
    - 本层只做：① 调用现有导出拿 BytesIO → ② 调用 MetadataCodec 嵌入元数据 → ③ 计算 snapshot_hash 存 wp_export_snapshot 表
    - 文字底稿走 **【新建】docx 路径**（python-docx，现有 service 仅 xlsx）
    - file_path 不存在时回退模板库（现有 `_resolve_template_path` 已有此逻辑，复用）
    - service 只 flush 不 commit
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [ ] 5.2 Property 4: Export Format Matches Workpaper Type
    - **Property 4: 表格/审定表/程序表→xlsx，文字→docx，映射确定且穷尽**
    - hypothesis max_examples=5, st.sampled_from(WP_TYPES)
    - **Validates: Requirements 1.1**

- [ ] 6. 程序表导出
  - [ ] 6.1 实现 WpExportEngine.export_program_sheet
    - 程序步骤独立 sheet：程序编号、程序描述、执行状态、执行结论、执行人
    - 标记只读列（程序编号、描述）和可编辑列（状态、结论）
    - _Requirements: 8.1, 8.2_
  - [ ] 6.2 Property 23: Program Sheet Export Contains Required Columns
    - **Property 23: 程序表导出包含 procedure_code/description/status/conclusion/executor 五列**
    - hypothesis max_examples=5
    - **Validates: Requirements 8.1**

- [ ] 7. 审定表导出
  - [ ] 7.1 实现 WpExportEngine.export_audit_sheet
    - 科目明细行：科目编码、科目名称、未审数、调整数、审定数
    - 调整分录来源引用作只读批注
    - 末尾汇总行（合计、借贷平衡校验）
    - _Requirements: 9.1, 9.2, 9.4_
  - [ ] 7.2 Property 25: Audit Sheet Export Completeness
    - **Property 25: 审定表导出含5列+末尾汇总行**
    - hypothesis max_examples=5
    - **Validates: Requirements 9.1, 9.4**


### Phase 3: 导入引擎

- [ ] 8. FormatValidator 格式校验器
  - [ ] 8.1 实现 FormatValidator 类
    - 文件: backend/app/services/wp_export/format_validator.py
    - _check_mime_type: 扩展名与 MIME 类型一致性
    - _check_sheet_structure: sheet 页签名称与 render_schema 匹配
    - _check_required_cells: 必填单元格检查
    - _check_numeric_types: 数值型字段类型校验
    - 返回结构化 ValidationReport (passed/warnings/errors)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - [ ] 8.2 Property 14: MIME Type Validation
    - **Property 14: 扩展名与 MIME 不匹配时报 error 级**
    - hypothesis max_examples=5
    - **Validates: Requirements 5.1**
  - [ ] 8.3 Property 15: Sheet Structure Validation
    - **Property 15: sheet 名与 render_schema 不匹配时报 error 级**
    - hypothesis max_examples=5
    - **Validates: Requirements 5.2**
  - [ ] 8.4 Property 16: Required Cell Validation
    - **Property 16: required 字段为空时报 error 级**
    - hypothesis max_examples=5
    - **Validates: Requirements 5.3**
  - [ ] 8.5 Property 17: Numeric Type Validation
    - **Property 17: 数值列非数值内容报 warning 级**
    - hypothesis max_examples=5
    - **Validates: Requirements 5.5**
  - [ ] 8.6 Property 18: Validation Report Structure
    - **Property 18: overall=最差级别，三类计数=len(items)正确分区**
    - hypothesis max_examples=5
    - **Validates: Requirements 5.6**

- [ ] 9. WpVersionManager 版本管理器 **【新建】归档能力（现有 upload 仅 +1 无归档）**
  - [ ] 9.1 实现 WpVersionManager 类
    - 文件: backend/app/services/wp_export/version_manager.py
    - **现有 `WpUploadService.upload_file` 已做 file_version+1、WORKPAPER_SAVED 事件、云同步、version_line——复用其流程**，本类只补"归档旧文件 + wp_version_archive 记录 + 保留10版"这一真实空白
    - create_version: 归档前调现有 upload 逻辑（或重构 upload 内联调本类），创建 wp_version_archive 记录
    - archive_old_version: 移至 storage/projects/{pid}/archive/{wp_id}/v{n}/
    - cleanup_excess_versions: 保留最近 10 个版本文件，超出置 file_retained=false
    - 归档失败记录日志不阻塞（复用现有非阻塞副作用模式）
    - service 只 flush 不 commit
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  - [ ] 9.2 Property 8: Version Increment Invariant
    - **Property 8: 导入成功后 file_version=prev+1，archive 记录 source=import**
    - hypothesis max_examples=5
    - **Validates: Requirements 6.1, 6.2**
  - [ ] 9.3 Property 9: Version Archive Path Format
    - **Property 9: archive_path 格式 storage/projects/{pid}/archive/{wp_id}/v{n}/**
    - hypothesis max_examples=5
    - **Validates: Requirements 6.3**
  - [ ] 9.4 Property 10: Maximum 10 Retained Version Files
    - **Property 10: N>10 时最多 10 条 file_retained=true，为最近 10 个版本**
    - hypothesis max_examples=5
    - **Validates: Requirements 6.4**

- [ ] 10. WpImportEngine 核心导入 **【复用】WpUploadService.upload_file + 增强**
  - [ ] 10.1 实现 WpImportEngine.import_file（编排层）
    - 文件: backend/app/services/wp_export/import_engine.py
    - **不重写 upload 逻辑**，编排流程：提取元数据 → FormatValidator 校验 → 快照哈希冲突检测 → 调用现有 `WpUploadService.upload_file` 完成实际写入+事件+解析+版本链 → 额外调 WpVersionManager 归档旧版
    - 缺少必要元数据(wp_code/project_id)时拒绝导入
    - service 只 flush 不 commit
    - _Requirements: 3.3, 3.4, 5.1, 6.1_
  - [ ] 10.2 实现程序表导入 import_program_sheet
    - 按程序编号匹配行，仅更新可编辑列
    - 不可匹配的新增行报告给用户
    - _Requirements: 8.3, 8.4_
  - [ ] 10.3 实现审定表导入 import_audit_sheet
    - 忽略审定数列（系统自动计算）
    - 仅接受备注和工作结论字段更新
    - _Requirements: 9.3_
  - [ ] 10.4 Property 22: Program Sheet Editable Column Isolation
    - **Property 22: 程序表导入仅更新可编辑列，只读列不变**
    - hypothesis max_examples=5
    - **Validates: Requirements 8.2, 8.3**
  - [ ] 10.5 Property 24: Audit Sheet Import Ignores Computed Columns
    - **Property 24: 审定表导入不写 audited_amount 列**
    - hypothesis max_examples=5
    - **Validates: Requirements 9.3**


### Phase 4: 冲突与校验

- [ ] 11. ConflictDetector 冲突检测器 **【复用】check_version_conflict + 新增哈希层**
  - [ ] 11.1 扩展冲突检测（非全新 class）
    - 文件: backend/app/services/wp_export/conflict_detector.py
    - **版本号比对复用现有 `WpUploadService.check_version_conflict`**，本模块只新增"内容哈希实质冲突"层
    - 逻辑：版本号冲突时查 wp_export_snapshot 的 snapshot_hash 与当前内容 hash 比对 → 判断是否为实质冲突
    - 字段级冲突继续由现有 `offline_conflict_service.detect` 负责（上传后自动触发，不重建）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [ ] 11.2 Property 6: Version Conflict Detection
    - **Property 6: file_version < server_version → 冲突; >= → 无冲突**
    - hypothesis max_examples=5
    - **Validates: Requirements 4.2, 4.3**
  - [ ] 11.3 Property 7: Substantive Conflict via Hash
    - **Property 7: 导出时 hash == 当前 hash → 非实质冲突; 不同 → 实质冲突**
    - hypothesis max_examples=5
    - **Validates: Requirements 4.5**

- [ ] 12. 强制覆盖审计日志
  - [ ] 12.1 实现强制覆盖时写 app_audit_log
    - 记录: 操作人、时间、被覆盖版本号、wp_id、project_id
    - 集成到 ImportEngine 的 force_overwrite 分支
    - _Requirements: 4.6_

- [ ] 13. Round-Trip 一致性集成
  - [ ] 13.1 实现导入解析 parse_sheet_data（与导出相同列映射）
    - 文件: backend/app/services/wp_export/serialization.py（追加）
    - deserialize_cell_value 与 serialize_cell_value 对称
    - _Requirements: 10.3_
  - [ ] 13.2 Property 1: Export-Import Round-Trip
    - **Property 1: 导出后未修改直接导入，逐 sheet 逐单元格一致**
    - hypothesis max_examples=5, 策略 st_workpaper_content()
    - **Validates: Requirements 10.1, 10.3**

- [ ] 14. Checkpoint - 导出→导入全链路
  - 确保 export_single → import_file 闭环无 crash，所有 PBT 通过。如有问题停下询问用户。

### Phase 5: 批量与模板

- [ ] 15. BatchPackager 批量打包器 **【复用】WpDownloadService.download_pack + 增强**
  - [ ] 15.1 扩展 WpDownloadService.download_pack（或新建薄封装）
    - **现有 download_pack 已实现 ZIP + {audit_cycle}/{wp_code}_{wp_name}.xlsx 目录结构——不重写**
    - 本任务新增：① 加 manifest.json（文件清单+SHA-256+导出时间+项目元数据）② 状态过滤参数 ③ 单文件失败跳过+manifest 标注 ④ 空循环报错而非空 ZIP ⑤ 导出带元数据嵌入（调 export_single）
    - 可选方案：在 download_pack 内部改调 export_single（含元数据）替代直接 write 文件，或新建 `batch_packager.py` 薄封装委托 download_pack
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - [ ] 15.2 Property 11: Batch Export Completeness
    - **Property 11: 打包包含指定循环+状态筛选的全部底稿，无遗漏无重复**
    - hypothesis max_examples=5
    - **Validates: Requirements 2.1, 2.6**
  - [ ] 15.3 Property 12: ZIP Directory Structure
    - **Property 12: ZIP 内每文件路径匹配 {cycle}/{wp_code}_{wp_name}.{ext}**
    - hypothesis max_examples=5
    - **Validates: Requirements 2.2**
  - [ ] 15.4 Property 13: Manifest Contains All Required Fields
    - **Property 13: manifest 含 files(path+sha256)/export_timestamp/project 元数据/failed 项**
    - hypothesis max_examples=5
    - **Validates: Requirements 2.3, 2.5**

- [ ] 16. TemplateCopier 模板复制器
  - [ ] 16.1 实现 TemplateCopier 类
    - 文件: backend/app/services/wp_export/template_copier.py
    - copy_single: 复制底稿文件+索引记录到目标项目
    - _strip_business_data: 清除金额/日期/描述，保留结构和程序步骤
    - 重新生成 wp_index 记录（新 UUID、目标 project_id）
    - 目标已存在同 wp_code 时 overwrite=false 提示跳过
    - copy_cycle: 批量复制整个审计循环
    - 复制后状态设为 draft、清除复核状态
    - service 只 flush 不 commit
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - [ ] 16.2 Property 19: Template Copy Produces Valid Draft
    - **Property 19: 复制后目标底稿 UUID≠源、project_id=目标、status=draft、review_status=not_submitted**
    - hypothesis max_examples=5
    - **Validates: Requirements 7.1, 7.3, 7.6**
  - [ ] 16.3 Property 20: Business Data Cleared on Copy
    - **Property 20: 复制后动态表区域数值/日期/文本列为空，结构/公式/只读列保留**
    - hypothesis max_examples=5
    - **Validates: Requirements 7.2**
  - [ ] 16.4 Property 21: Batch Copy Covers Entire Cycle
    - **Property 21: 批量复制数量=源循环非删除底稿数**
    - hypothesis max_examples=5
    - **Validates: Requirements 7.5**

- [ ] 17. Checkpoint - 批量导出与模板复制
  - 确保 batch_export + template_copy 全链路无 crash，所有 PBT 通过。如有问题停下询问用户。


### Phase 6: API 路由层

- [ ] 18. 导出路由 **【复用】现有 wp_download.py 已有 download-file/download-pack + 扩展**
  - [ ] 18.1 在现有 `wp_download.py` 或新文件增加端点
    - **现有路由已有**：download-file(单下载)/download-pack(批量ZIP)/check-version/upload-file——复用不改
    - **新增端点**（在同一 router 或 `wp_export_router.py` 注册）：
      - POST .../workpapers/{wp_id}/export-with-metadata → StreamingResponse（区别于 download-file：嵌入元数据+记快照）
      - POST .../workpapers/batch-export-enhanced → StreamingResponse (ZIP + manifest.json)
      - GET .../workpapers/{wp_id}/export-history → list[WpExportSnapshot]
    - Content-Disposition: attachment; filename*=UTF-8''{encoded_name}（复用现有 RFC5987 模式）
    - _Requirements: 1.1, 2.1_
  - [ ] 18.2 在 router_registry 注册（若新文件）
    - 在对应 group 文件中注册，确保路由顺序不被通配截获
    - _Requirements: 1.1_

- [ ] 19. 导入路由 **【复用】现有 upload-file + 新增校验/解冲/版本端点**
  - [ ] 19.1 在现有 `wp_download.py` 或新文件增加端点
    - **现有已有**：upload-file(导入+版本冲突+force_overwrite)——保留原端点不动
    - **新增端点**：
      - POST .../workpapers/{wp_id}/import-validate → ValidationReport（仅校验不执行）
      - POST .../workpapers/import-enhanced → ImportResult（完整流程：元数据提取+校验+哈希冲突+归档+上传，编排层调 WpImportEngine）
      - POST .../workpapers/import/resolve → ImportResult（冲突解决：force/parallel/cancel）
      - GET .../workpapers/{wp_id}/versions → list[WpVersionArchive]
    - router 层统一 commit（service 只 flush）
    - _Requirements: 3.3, 4.4, 5.6, 6.1_
  - [ ] 19.2 在 router_registry 注册（若新文件）
    - _Requirements: 3.3_

- [ ] 20. 模板复制路由
  - [ ] 20.1 创建模板复制 router
    - 文件: backend/app/routers/wp_template_copy_router.py
    - POST /api/projects/{project_id}/workpapers/template-copy → CopyResult | list[CopyResult]
    - 参数: source_wp_id / source_project_id + audit_cycle / overwrite
    - _Requirements: 7.1, 7.4, 7.5_
  - [ ] 20.2 在 router_registry 注册模板复制路由
    - _Requirements: 7.1_

- [ ] 21. Checkpoint - API 端点联通
  - 确保所有端点在 in-process ASGI httpx 下可调通（200/409/422），router 注册无遗漏。如有问题停下询问用户。

### Phase 7: 前端

- [ ] 22. 导出功能前端
  - [ ] 22.1 实现导出按钮与下载逻辑
    - 底稿列表页/底稿编辑页添加"导出"按钮
    - 使用 downloadFile（axios blob + Bearer header）下载，禁止 window.open
    - 文件名从 Content-Disposition 解析
    - _Requirements: 1.1_
  - [ ] 22.2 实现批量导出配置弹窗
    - 选择审计循环（多选）+ 状态过滤
    - 调用 batch-export 端点下载 ZIP
    - _Requirements: 2.1, 2.6_

- [ ] 23. 导入功能前端
  - [ ] 23.1 实现导入上传弹窗
    - 文件上传 (el-upload) + 格式限制 (.xlsx/.docx)
    - 调用 import 端点 multipart/form-data
    - _Requirements: 3.3, 5.1_
  - [ ] 23.2 实现校验报告展示组件
    - 三级分类 (passed/warnings/errors) 表格展示
    - 每项显示位置 + 描述
    - _Requirements: 5.6_
  - [ ] 23.3 实现冲突处理面板
    - 409 时弹出冲突详情（版本号、最后修改人、时间）
    - 三选项按钮: 强制覆盖 / 创建并行版本 / 取消导入
    - 调用 import/resolve 端点
    - _Requirements: 4.3, 4.4_

- [ ] 24. 模板复制前端
  - [ ] 24.1 实现模板复制弹窗
    - 选择源底稿/源项目+循环
    - 显示目标冲突提示（同 wp_code 已存在）
    - _Requirements: 7.1, 7.4, 7.5_

- [ ] 25. 版本历史前端
  - [ ] 25.1 实现版本历史面板
    - 底稿详情区域展示版本列表
    - 显示版本号、来源、创建时间、创建人
    - _Requirements: 6.1, 6.2_

### Phase 8: 收尾

- [ ] 26. Round-Trip 集成测试
  - [ ] 26.1 编写 E2E round-trip 测试
    - 覆盖全部底稿类型: 表格/文字/程序表/审定表
    - 真实 openpyxl/python-docx 读写 + SHA-256 验证
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 27. Final Checkpoint
  - 确保所有测试通过（含 25 条 PBT），无 schema drift，router 注册完整。如有问题停下询问用户。

## Notes

- **🔴 复用铁律**：task 5/9/10/11/15/18/19 标【复用】的必须基于现有服务扩展，禁止重写；标【新建】的 task 3/4/8/9(归档部分)/16 才是真空白
- 所有 PBT 子任务为必做（非可选），hypothesis max_examples=5
- service 层只 flush 不 commit，router 层统一 commit
- DDL + ORM + service 三层一致铁律贯穿全 spec
- 新增 router 必须在 router_registry 注册
- 当前最高迁移 V068，本 spec 使用 V069
- 前端下载统一用 downloadFile（axios blob），禁止 window.open
- 现有 `wp_download.py` 已有 download-file/download-pack/check-version/upload-file 四端点可直接复用
