# 项目级底稿批量导入导出 · Phase 4 评估

> Spec: `workpaper-bulk-tab-import-export`
> 对应 Task 11.1（归档/交付物 + 密码保护 ZIP）、Task 12.1（异构底稿 bulk 可行性）
> 性质：评估型任务（写结论，按业务优先级决定是否实现）
> 日期：2026-07-13

---

## Task 11.1 · 「导出全部数据」纳入交付物清单 + 密码保护 ZIP 评估

### 结论摘要

- **纳入交付物清单**：✅ 建议纳入，成本低、价值明确。可作为项目归档的「底稿数据快照」交付物，与既有 Word/Excel 交付物并列登记。
- **密码保护 ZIP**：🟡 建议按需（默认关闭）。标准 ZIP 加密（ZipCrypto）安全性弱、AES-256 加密需引入第三方库，收益有限；优先依赖平台既有的权限门禁 + 传输层 TLS。

### 现状盘点

- 现有 `POST /export-data`（同步）+ `POST /export-data/async`（Task 9.1）已产出完整数据 ZIP，含 `manifest.json`（sha256 完整性）+ `README.txt`（编制提示）。
- ZIP 内容为 xlsx 明文；文件名走 RFC5987；无内容加密。
- 交付物体系：`deliverable_service.py` / `export_task_service.py` 管理 Word/Excel 交付物的生成 + 版本 + 下载，但**未登记 bulk 数据 ZIP**。

### 纳入交付物清单方案（建议实现）

将「底稿数据全量 ZIP」作为一类交付物登记，复用既有 `ExportTask` 状态机：

1. 异步导出完成（Task 9.1 `_run_export`）后，在 `bulk_progress_service.complete` 之后额外登记一条交付物记录（doc_type 新增 `bulk_workpaper_data`）。
2. 交付物中心（前端）列出该 ZIP，支持重新下载 / 版本对比 / 归档留痕。
3. 归档项目（`ProjectStatus.archived`）保留最后一次 bulk 数据 ZIP 作为归档快照。

工作量：小（复用 `ExportTask` + `DeliverableService`，新增 1 个 doc_type 枚举 + 完成回调登记）。

### 密码保护 ZIP 评估（建议默认关闭）

| 方案 | 安全性 | 依赖 | 兼容性 | 结论 |
|------|--------|------|--------|------|
| 标准 ZipCrypto（Python `zipfile` 原生仅支持解密，不支持加密写） | 弱（已知可破解） | 无 | Windows 资源管理器原生支持 | ❌ 不推荐（stdlib 不支持加密写，且算法弱） |
| AES-256（`pyzipper`） | 强 | 新增第三方依赖 `pyzipper` | 需 7-Zip/WinRAR 解压 | 🟡 按需 |
| 不加密 + 权限门禁 + TLS | 依赖平台 | 无 | 全兼容 | ✅ 默认 |

**决策**：默认不加密。若客户合规要求（如涉密项目离线交付），可加 `password?: str` 表单参 + `pyzipper` AES-256 写入路径，作为独立增量任务实现。**当前不实现**，仅记录方案。

理由（ponytail 决策阶梯）：
- 第 1 步「需要存在吗」：常规场景平台权限 + TLS 已覆盖机密性，密码 ZIP 非必需。
- 第 2 步「stdlib 能做吗」：Python `zipfile` 不支持加密写，必须引第三方库 → 违反「不引入新依赖」偏好。
- 结论：作为可选合规增强，触发条件（客户明确要求）出现时再实现。

---

## Task 12.1 · OnlyOffice / 程序表 / 自定义底稿 bulk 可行性评估

### ⚠️ 更正（2026-07-13 复盘）：适配器覆盖边界 + 真实瓶颈

复盘用户提问「是否应扩展到 I/J/K/L/M/N/S 全部底稿」，全仓实测后**更正一处早先误判**：

- **M/N/S 其实都有单表 I/E 端点**，只是以**独立路由**存在（如 `m4_capital_reserve.py`、`n2_taxes_payable.py`、`s_estimate_calculation.py`，路径 `/api/m4-capital-reserve/{wp_id}/export-template` 等），不在 `wp_render_strategies/_*_import_export.py` 目录下，故首轮 glob 漏检。因此「M/N/S 无 I/E」的旧结论**作废**。

- **两层结构（真实瓶颈在 catalog 而非 adapter）**：
  1. **ACNR catalog 的 `import_export` 段**（数据，真源）——`manifest.list_import_export` 只认 catalog 逐 sheet 的 `api_prefix/item_id/import_order/depends_on_sheets`，决定某 sheet 是否进 manifest。**当前 catalog 仅 D+F 启用**，K/G/H/I/J/L/M/N/S 全休眠。
  2. **adapter 注册表**（本 spec 代码）——把 `api_prefix` → 执行 I/E 端点。

- **适配器扩展现状（2026-07-13 本轮补齐）**：
  - `_d_cycle_adapters`：D1-D7。
  - `_kfgh_cycle_adapters`：F(9)/G(21)/H(8)/K(14) + **新增 C24-journal/E1/I1-I6/J1/J2/L0（wp_render_strategies 统一族，同构路径通用包装）+ J3（异形路径 bespoke）**。注册表现 71 项。
  - **未注册（真实剩余工作）**：**M1-M10 / N1-N5 / S-estimate 独立路由族**。原因：①路径结构不同（`/api/{module}/{wp_id}/{suffix}`，通用 `_endpoint_for` 的 `/{prefix}/{suffix}` 提不出）；②其 catalog `api_prefix` 命名不统一（`m4-capital-reserve` vs `n4` vs `s-estimate`），由未来 ACNR catalog 编写决定，投机注册会造成假覆盖。

- **结论**：适配器扩展是「便宜的 10%」（预备待命，与 K/G/H 同姿态）；**让任一循环端到端可用的「贵的 90%」= ACNR catalog 逐 sheet 编写 `import_export` 段**（api_prefix/item_id/import_order/depends_on_sheets），属 **ACNR catalog 数据任务**（见 `acnr-consumer-wiring` / catalog 种子），不在本编排 spec 范围。M/N/S 独立路由族的 adapter 变体（suffix-only 匹配）待其 catalog api_prefix 敲定后再补，作为独立任务。

### 以下三类底稿 bulk 往返判定「不实现」（componentType 层面无单表 I/E 三端点）

### 1. OnlyOffice 底稿（复杂 xlsx / docx）

- **现状**：`componentType=onlyoffice-sheet`，数据存原生 xlsx/docx 文件（`working_paper.file_path`），经 WOPI 在线编辑，无「行模型 + item_id」的结构化 checklist_responses。
- **bulk 障碍**：
  - 无单表 I/E 三端点（导入导出是「上传替换整个文件」语义，非行级合并）。
  - ConflictResolver（overwrite/fill-empty/reject）基于 item_id 行级冲突，对整文件替换无意义。
  - 版本快照回滚已由 file 版本管理覆盖，不走 bulk SnapshotGuard。
- **既有替代路径**：`batch_export_progress.py`（`POST /batch-export`）已支持**按 wp_id 批量导出原生文件 ZIP**（`export_progress_service._add_one_workpaper` 直接 `zf.write(fp, arcname)`）。OnlyOffice 底稿的「批量导出」应走此路径，不进本 spec 的 bulk-tab 编排。
- **判定**：❌ 不纳入 bulk-tab。批量导出走既有 batch-export；批量导入无结构化合并语义，不实现。

### 2. 程序表底稿（a-program-console）

- **现状**：`componentType=a-program-console`，数据为「审计程序步骤 + auto_data_source 自动取数 + field_overrides 手动覆盖」，存 checklist_responses 但语义是**程序执行状态**（勾选/取数/覆盖），非可离线填写的表格行。
- **bulk 障碍**：
  - auto_data_source 值由 `auto_data_resolvers` 运行时从 TB/调整分录等实时计算，导出为静态 xlsx 后再导入会**覆盖实时取数**，破坏数据一致性。
  - field_overrides 有 per project/year/scope 维度，扁平 xlsx 无法表达。
  - 程序表更多是「联动消费」而非「离线编制」——脱离系统填写价值低。
- **判定**：❌ 不纳入 bulk-tab。程序表的价值在系统内实时联动，离线往返违背设计意图。

### 3. 自定义底稿（用户自建 / 无 wp_render_schema）

- **现状**：无固定列结构 / 无 ACNR manifest 登记 / 无单表 I/E 端点。
- **bulk 障碍**：manifest 唯一真源是 ACNR catalog（`manifest.list_import_export`），自定义底稿不在 catalog → 无路由信息 → bulk 层不可触达（这是 fail-soft 的正确行为：跳过 `skip_reason=no_adapter`）。
- **判定**：❌ 不纳入 bulk-tab。自定义底稿若需批量能力，前置条件是先纳入 ACNR catalog + 提供单表 I/E 三端点，属独立 feature，不在本 spec 范围。

### 复用边界总结

| 底稿类型 | 批量导出 | 批量导入 | 走哪条路径 |
|----------|----------|----------|-----------|
| 结构化单表 I/E（D/F 已启用，K/G/H 待启用） | ✅ | ✅ | 本 spec bulk-tab 编排 |
| OnlyOffice（原生文件） | ✅ | ❌ | 既有 batch-export（按 wp_id 打包原生文件） |
| 程序表（a-program-console） | ❌ | ❌ | 不实现（实时联动，离线无价值） |
| 自定义底稿 | ❌ | ❌ | 前置需纳入 ACNR + 单表 I/E，属独立 feature |

**核心原则**：bulk-tab 是「结构化底稿行级数据」的批量编排层，不是「任意文件批量搬运」。异构底稿各有其既有或更合适的路径，强行纳入会破坏数据一致性或引入无价值复杂度。
