# 需求文档：审计报告模板正文集成

## 简介

将致同年度审计的全套出品物模板（审计报告正文 Word + 财务报表 Excel + 附注 Word）作为程序内置资产，通过占位符替换 + 数据填充 + 可选段落确认 + 指引注释清理的流水线，生成干净、格式合规的出品物，供 OnlyOffice 在线预览/编辑和最终导出。最大程度保留模板原始格式。

本需求是对现有交付件中心（`DeliverableService`）、报表导出（`ReportExcelExporter`）、附注导出（`NoteWordExporter`）的**统一升级**，而非并行新建第三套导出体系。

> **Supersedes**：`.kiro/specs/audit-report-deliverable-center/` 中「JSON 段落主源」决策。实施后 Word 模板为唯一正文生成源；`audit_report_templates_seed.json` 仅迁移期只读参考。

## 模板资产清单

| 来源目录 | 内容 | 文件类型 | 维度 |
|---------|------|---------|------|
| `审计报告模板正文/` | 审计报告正文（4意见×4企业=17个） | docx | opinion_type × company_subtype |
| `数据/审计报告模板/国企版/单体/` | 国企单体：报表xlsx + 附注docx + 报告docx | xlsx+docx | soe × standalone |
| `数据/审计报告模板/国企版/合并/` | 国企合并：报表xlsx + 附注docx + 报告docx | xlsx+docx | soe × consolidated |
| `数据/审计报告模板/上市版/单体_上市/` | 上市单体：报表xlsx + 附注docx + 报告docx | xlsx+docx | listed × standalone |
| `数据/审计报告模板/上市版/合并_上市/` | 上市合并：报表xlsx + 附注docx + 报告docx | xlsx+docx | listed × consolidated |

> **格式约束**：入库前所有 `.doc` 源文件 SHALL 转换为 `.docx`（见需求 2.7）。运行时仅接受 `.docx` / `.xlsx`。

## 核心设计思路

```
template_manifest.json（唯一模板索引入口）
    ↓ TemplateManifestLoader 解析路径 + 版本号
    ↓ 项目生成出品物时 copy 到 storage/deliverables/{project_id}/{task_id}/
    ↓ 报告正文：python-docx 替换占位符 + 可选段落确认 + 注释清理
    ↓ 财务报表：openpyxl 按 cell_mapping 填入 financial_report 审定数据（保留格式/公式/样式）
    ↓ 附注：模板模式填充 + 裁剪重编号 + 表格渲染
    ↓ DeliverableService.render_and_store → OnlyOffice 预览/编辑 → 导出最终版
```

## 现有代码基线（Codegraph 分析摘要）

实施前须对齐以下现状，避免双轨长期并存：

| 模块 | 当前生产路径 | 与本需求关系 |
|------|-------------|-------------|
| 报告交付 | `deliverable.py` → `DeliverableService`（版本链/OnlyOffice/哈希校验） | **保留**，作为唯一入库出口 |
| 报告正文 | `ReportBodyService`：DB `audit_report_template` JSON 段落 → 程序化 `render_docx` | **迁移替换**为 Word 模板填充主路径 |
| 财务报表 | `ReportExcelExporter`：openpyxl 模板填充（方向正确） | **扩展**：切换 manifest 路径 + cell_mapping |
| 附注 | `NoteWordExporter`：程序化拼装 docx | **扩展**：增加 `mode='template'` 分支 |
| 遗留路径 | `WordTemplateFiller` → `storage/projects/{id}/reports/` | **下线**，统一到 deliverable 存储 |
| 附注裁剪 | `NoteTrimService.auto_trim_v2()` 三级判定 | **复用**，导出时读取最新状态 |
| 章节编号 | `get_section_numbers` 端点分组规则 | **提取共享模块**，与 `{{seq:N}}` 对齐 |
| 占位符 | `ReportPlaceholderService` 使用 `entity_name` 等旧键名 | **兼容映射**到 `{{company_full_name}}` 等新键名 |
| 模板路径 | `ReportExcelExporter.TEMPLATE_MAP` 硬编码旧目录 | **废弃**，改读 manifest |
| 全套导出 | `word_export.py` + `export_jobs_v2` | **接入**交付件中心 UI |

## 术语表

- **Template_Asset**：程序内置模板文件（`backend/data/audit_report_templates/` 下 `.docx` / `.xlsx`）
- **Template_Manifest**：`template_manifest.json`，三类模板的唯一索引（含全局版本号）
- **TemplateManifestLoader**：启动时加载 manifest、校验文件存在、解析模板路径的服务（各 Fill 引擎共用）
- **Placeholder**：模板占位符，格式 `{{field_name}}`；附注另有 `{{section:code}}` / `{{table:code}}` / `{{seq:prefix}}`
- **PlaceholderRegistry**：新旧占位符键名映射表（`entity_name` ↔ `{{company_full_name}}` 等），供迁移期兼容
- **Optional_Section**：可选段落，格式 `##OPT:section_id:描述##...##/OPT:section_id##`
- **Guidance_Note**：指引注释，格式 `##NOTE:xxx##`
- **Fill_Service**（`TemplateFillService`）：统一模板填充服务，负责 copy→替换→确认→清理→交付件入库；**重构** `WordTemplateFiller`，非与 `ReportBodyService` 并行的新服务
- **Company_Subtype**：企业子类型 A/B/C/D（`type_a`/`type_b`/`type_c`/`type_d`），不改动 `company_type` 枚举
- **Template_Variant**：报告正文详简版（`simple` / `detailed`）
- **NoteSectionNumbering**：附注章节编号共享模块，`get_section_numbers` 端点与附注导出共用
- **NoteSectionCatalog**（`note_section_catalog.py`）：附注**唯一对齐层** — `section_code` / `variant_key` / `scope` 过滤 / 国企 `五、N→八、N` 归一；JSON、DB、bindings、导出**禁止**绕过
- **Generated_Deliverable**：写入 `storage/deliverables/{project_id}/{task_id}/` 的出品物文件

## 实施阶段（迁移策略）

### Phase 0 — 模板资产整理（最先，阻塞代码）

详见 [`template-preparation.md`](./template-preparation.md)、[`note-template-gap-analysis.md`](./note-template-gap-analysis.md)：报告 OPT/占位符、附注四方变体 `##SECTION:`/`{{table:}}`/`##STYLE_REF:`、报表表头与 `{{row:BS-xxx:current/prior}}` 内联占位。

### Phase 1 — 基础设施（P0）

1. `.doc` → `.docx` 批量转换 + CI 拒绝 `.doc`
2. 实现 `TemplateManifestLoader`，废弃各服务硬编码 `TEMPLATE_MAP`
3. 实现 `merge_runs_for_replace()` + `PlaceholderRegistry`
4. 统一存储路径到 `storage/deliverables/{project_id}/{task_id}/`
5. `projects` / `audit_report` 新增 `company_subtype`、`template_variant`、`template_version` 字段

### Phase 2 — 三类填充 + 两阶段 API（P1）

1. 报告正文：`preview` / `confirm` 两阶段 API，替代 `ReportBodyService` 主生成路径
2. 财务报表：`ReportExcelExporter` 改读 manifest + `cell_mapping.json`
3. 附注：`NoteWordExporter` 增加模板模式，复用裁剪/编号/空表逻辑
4. 提取 `note_section_numbering.py` 共享模块

### Phase 3 — 规则推荐 + 全套生成 + 遗留下线（P2）

1. `matching_rules.json` 导入 + wizard 推荐
2. `ExportJob(job_type='full_deliverables')` 接入交付件中心
3. 下线 `WordTemplateFiller` 旧存储路径；`ReportBodyService` 降级为预览/校验辅助（或废弃）

---

## 需求

### 需求 1：企业子类型扩展（向后兼容）

**用户故事：** 作为审计项目经理，我希望为项目标注精确的企业子类型（A/B/C/D），以便系统自动匹配致同规定的正确报告模板。

#### 验收标准

1. THE `projects` 表 SHALL 新增 `company_subtype` 字段（VARCHAR，可选值：`type_a`/`type_b`/`type_c`/`type_d`，nullable）
2. THE `audit_report` 表 SHALL 新增 `company_subtype` 字段，记录报告生成时使用的企业子类型
3. THE `company_type` 枚举（listed/non_listed）SHALL 保持不变，不影响现有功能
4. WHEN `company_subtype` 未填写且 `matching_rules.json` 无法匹配时，THE Fill_Service SHALL 按 fallback 推断：`listed` → `type_a`，`non_listed` → `type_d`（**仅作兜底，银行/保险/证券等项目须由规则 7 推荐 type_b**）
5. WHEN 前端项目创建/编辑表单中选择企业子类型时，SHALL 提供 4 个选项及中文说明：
   - A：上市公司、三板创新层及公开发债
   - B：三板基础层、银行、保险、期货、证券
   - C：其他公众利益实体
   - D：非公众利益实体
6. THE DB 种子 `audit_report_template`（JSON 段落）SHALL 在迁移期标注对应 `company_subtype` 映射关系，避免二维 `company_type` 与四维 Word 模板长期分裂
7. WHEN 存量项目 `company_subtype` 为空时，THE 系统 SHALL 按以下顺序回填（不阻断打开项目）：
   ① `matching_rules.json` 按项目属性推荐
   ② `company_type=listed` → `type_a`，`non_listed` → `type_d`
   ③ 项目编辑页 / ProjectWizard 展示「待确认企业子类型」横幅，引导用户确认
8. THE 回填结果 SHALL 写入 `projects.company_subtype`；用户手动修改后优先于自动推断

### 需求 2：Word 模板作为程序内置资产

**用户故事：** 作为系统管理员，我希望 17 个 Word 模板作为程序的一部分，存放在固定路径下，系统可按条件自动选择对应模板。

#### 验收标准

1. THE Template_Asset SHALL 存储在 `backend/data/audit_report_templates/` 目录下
2. THE Template_Manifest SHALL 定义 opinion_type + company_subtype + variant(simple/detailed) → 文件路径，存储为 `template_manifest.json`
3. THE `TemplateManifestLoader` SHALL 为三类模板（report_body / financial_statements / disclosure_notes）的**唯一**路径解析入口；各服务 SHALL NOT 硬编码模板路径（废弃 `ReportExcelExporter.TEMPLATE_MAP` 等）
4. WHEN 系统启动时，SHALL 校验 manifest 中引用的所有模板文件是否存在，缺失时 log warning 不阻断启动
5. FOR ALL 模板文件，SHALL 使用统一标记格式（`##` 前缀，非中文标点），避免与正文内容冲突
6. THE Template_Asset SHALL 保留致同原始格式（页眉/页脚/字体/段落样式/缩进），标记不得破坏 Word 格式
7. WHEN opinion_type = `disclaimer`（无法表示意见）时，THE Template_Manifest SHALL 映射到单一通用模板（不区分企业子类型，键 `_all`）
8. **所有运行时模板资产 SHALL 为 `.docx`**；源 `.doc` 文件 SHALL 在入库前批量转换为 docx 并人工 spot check；CI 启动校验 SHALL 拒绝 manifest 中引用 `.doc` 扩展名
9. THE `audit_report` 表 SHALL 新增 `template_variant` 字段（`simple`/`detailed`，nullable，默认 `simple`）

### 需求 3：占位符自动替换

**用户故事：** 作为审计项目经理，我希望生成报告时系统自动将模板中的公司名、年度等占位符替换为项目实际数据，减少手工编辑。

#### 验收标准

1. THE Fill_Service SHALL 支持以下占位符字段：
   - `{{company_full_name}}`：被审计单位全称
   - `{{company_short_name}}`：被审计单位简称
   - `{{audit_year}}`：审计年度（如 2025）
   - `{{prior_year}}`：上年年度（如 2024）
   - `{{audit_period_start}}`：审计期间起始日（如 2025年1月1日）
   - `{{audit_period_end}}`：审计期间截止日（如 2025年12月31日）
   - `{{report_date}}`：报告日期
   - `{{signing_partner}}`：签字合伙人
   - `{{signing_cpa}}`：签字注册会计师
   - `{{firm_name}}`：事务所名称（致同会计师事务所）
   - `{{firm_address}}`：事务所地址
   - `{{financial_statements_list}}`：被审计报表清单
   - `{{responsibility_organ}}`：治理层机构名称（如"董事会"/"管理层"）
2. WHEN 占位符的数据来源为项目基本信息时，THE Fill_Service SHALL 从 `projects` 表和 `wizard_state` 自动提取
3. THE `PlaceholderRegistry` SHALL 提供新旧键名双向映射，迁移期同时兼容 `ReportPlaceholderService` 旧键（`entity_name`、`cpa_name_1` 等）与新 `{{...}}` 格式
4. IF 某个占位符找不到对应数据，THEN THE Fill_Service SHALL 保留占位符原文（高亮标记为待补充），并在返回结果中列出 `missing_fields` 清单
5. THE Fill_Service SHALL 遍历 Word 文档的所有 paragraphs、tables、headers、footers 执行替换
6. THE Fill_Service SHALL 实现 `merge_runs_for_replace(doc)` 工具函数，在遍历前合并被 Word runs 分割的占位符（如 `{{company` + `_full_name}}`）；报告正文与附注模板填充 SHALL 共用此底层
7. THE 附注与报告正文通用占位符替换 SHALL 调用同一 `replace_placeholders_in_doc()` 实现

### 需求 4：可选段落确认

**用户故事：** 作为审计项目经理，我希望系统识别模板中的可选段落（如强调事项段、持续经营段、关键审计事项段），弹窗让我确认该项目是否适用，不适用的自动删除。

#### 验收标准

1. THE Fill_Service SHALL 扫描模板中所有 `##OPT:section_id:描述##...##/OPT:section_id##` 标记，提取可选段落清单
2. WHEN 用户触发"生成审计报告正文"第一步（preview）时，THE Fill_Service SHALL 返回可选段落清单，包含：section_id、描述、段落预览（前 50 字）、默认建议（保留/删除）、所属分组（如"报告正文段落"/"补充信息段落"）
3. 前端弹窗 SHALL 按分组展示可选段落，每项有勾选框 + 说明文字 + 展开预览
4. WHEN 用户确认后（confirm 步骤），THE Fill_Service SHALL 删除用户取消勾选的段落（含标记），保留用户勾选的段落（仅删除标记，保留正文）
5. IF 用户跳过确认（直接关闭弹窗），THEN THE Fill_Service SHALL 按默认建议处理
6. THE Fill_Service SHALL 将用户的勾选结果持久化到 `audit_report.report_body_json`（见需求 6.8 schema），重新生成时恢复上次选择
7. 常见可选段落包括但不限于：强调事项段(`emphasis`)、其他事项段(`other_matter`)、持续经营重大不确定性(`going_concern`)、关键审计事项段(`key_audit_matters`)、比较数据段(`comparative`)、其他信息段(`other_information`)
8. THE `OptionalSectionDialog` SHALL 按 `placeholder_registry.opt_groups` 分组展示（报告正文段落 / 补充信息段落），每项含勾选框 + 描述 + 可展开 preview 文本（前 50 字）
9. THE `missing_fields` 警告 SHALL 在弹窗顶部以非阻断警告条展示；**不得**阻止用户点击「确认生成」
10. WHEN 用户关闭弹窗未 confirm 时，THE preview session SHALL 保留至 TTL 过期，允许再次打开继续确认
11. THE 默认勾选 SHALL 优先读 `placeholder_registry.opt_defaults[company_subtype]`；无配置时用 preview 响应的 `default_keep`

### 需求 5：指引注释清理

**用户故事：** 作为审计项目经理，我希望生成最终报告时自动删除模板中的指引注释和格式说明，得到一份干净的正式报告正文。

#### 验收标准

1. THE Fill_Service SHALL 识别并删除 `##NOTE:xxx##` 格式的指引注释（`##` 前缀保证不与正文方括号/圆括号冲突）
2. WHEN 指引注释占据整个段落时，THE Fill_Service SHALL 删除该段落（含段落标记），不留空行
3. WHEN 指引注释嵌在正文段落中间时，THE Fill_Service SHALL 仅删除 `##NOTE:...##` 标记文字，保留其余正文
4. THE Fill_Service SHALL 在清理前保留一份"带注释版"副本（`with_notes_v{n}.docx`），路径写入 `report_body_json.guidance_version_path`；该版本**不进入**正式版本链，OnlyOffice 默认 SHALL 仅打开清理后的正式版
5. WHILE 用户在 OnlyOffice 编辑时，SHALL 看到清理后的正式版（不含注释）
6. THE Fill_Service SHALL 不删除正文中的合法方括号（如"[注1]"脚注引用、"[金额单位: 元]"），仅删除 `##NOTE:` 格式标记
7. WHEN 用户已在 OnlyOffice 编辑过报告且再次生成时，SHALL 与需求 6.4 合并提示"将覆盖当前编辑内容"
8. THE 交付件中心「审计报告正文」卡片 SHALL 提供次要操作「下载编制参考版（含内部提示）」，权限与正式版下载相同（`project:read`）
9. THE 参考版下载文案 SHALL 注明「仅供项目组编制参考，不可对外出具」；列表主行仅展示正式版

### 需求 6：生成报告正文完整流程与交付件中心集成

**用户故事：** 作为审计项目经理，我希望点击"生成审计报告"后经历模板选择→占位符替换→可选段落确认→注释清理的完整流程，最终报告自动进入交付件中心可供预览/编辑/导出。

#### 验收标准

1. THE 报告正文生成 SHALL 采用**两阶段 API**（替代现有 `render_report_body` 单次同步调用）：
   - `POST /deliverables/report-body/preview`：选取模板 → copy → 替换占位符 → 扫描 OPT → 返回 `optional_sections` + `missing_fields` + `preview_session_id`（**不落库、不写 deliverable**）
   - `POST /deliverables/report-body/confirm`：携带 `preview_session_id` + 用户勾选 → 删除不适用段落 → 清理 NOTE → 保存 docx → `DeliverableService.render_and_store`
2. WHEN preview 执行时，THE Fill_Service SHALL：
   ① 根据 opinion_type + company_subtype + template_variant 从 manifest 选取模板
   ② copy 模板到 `storage/deliverables/{project_id}/{task_id}/`（confirm 阶段确定 task_id）
   ③ 替换占位符
   ④ 返回可选段落清单 + 待补充字段清单
3. WHEN confirm 执行时，THE Fill_Service SHALL 创建 `word_export_task` + `deliverable_version`（version_no 递增），复用现有 `DeliverableService`、`DeliverableHashService`、OnlyOffice 回调
4. THE Generated_Report SHALL 在交付件中心的"审计报告正文"分组下展示
5. WHEN 已有报告需要重新生成时，THE Fill_Service SHALL 提示"将覆盖当前编辑内容"，确认后创建新版本（version_no +1），旧版本保留可回溯
6. THE Generated_Report SHALL 可通过 OnlyOffice 直接打开编辑，编辑保存后的文件即为最终导出版本
7. FOR ALL 生成的报告正文，格式 SHALL 与致同原始模板完全一致（字体/样式/间距不变）
8. THE `audit_report.report_body_json` SHALL 采用以下 schema（示例）：

```json
{
  "optional_sections": {"emphasis": true, "going_concern": false},
  "guidance_version_path": "storage/deliverables/{project_id}/{task_id}/with_notes_v1.docx",
  "template_version": "2025-v1",
  "company_subtype": "type_a",
  "template_variant": "simple",
  "missing_fields": ["signing_partner"]
}
```

9. THE 原 `ReportBodyService.load_body_template` + `render_docx` 主生成路径 SHALL 在 Phase 2 完成后标记 deprecated，最终下线；迁移期可保留为 HTML 预览辅助
10. THE confirm 步骤 SHALL 调用 `validate_kam_word_mode`（设计 §4.2）：基于 OPT 勾选 `key_audit_matters` + `kam_required()` 判定，返回 `validation_warning`（Toast 展示，**不阻断**入库）
11. THE `validate_kam_word_mode` SHALL **不**在 confirm 后扫描 docx 正文判空；KAM 段落内容完整性由 EQCR 复核负责

### 需求 7：对照表规则集成

**用户故事：** 作为审计项目经理，我希望系统根据对照表的规则自动推荐该项目适用哪类模板（A/B/C/D），减少人为判断失误。

#### 验收标准

1. THE Fill_Service SHALL 解析 `年度审计报告模板使用对照表.xlsx` 中的适用条件，编码为推荐规则
2. WHEN 项目属性满足对照表某一行的全部条件时，SHALL 自动设置推荐的 `company_subtype` 并在前端高亮建议
3. THE 推荐规则 SHALL 持久化为 `backend/data/audit_report_templates/matching_rules.json`（可编辑，非硬编码）
4. WHEN 推荐规则更新时，SHALL 支持重新导入 xlsx 刷新 `matching_rules.json` 而无需修改代码
5. IF 项目属性无法唯一匹配某一行规则（存在歧义），THEN SHALL 返回所有候选模板供用户手动选择
6. THE 推荐结果 SHALL 在项目创建 wizard 的**企业子类型选择步骤**显示为"系统建议：模板X"标签；wizard 第一步 SHALL 尝试运行推荐（不仅高亮，须预填建议值）
7. THE 推荐规则 SHALL 优先于需求 1.4 的 `listed`/`non_listed` fallback 推断

### 需求 8：模板版本管理

**用户故事：** 作为系统管理员，我希望模板文件支持版本更新，新项目使用新版模板，已有项目不受影响。

#### 验收标准

1. THE Template_Manifest SHALL 记录全局模板版本号（如 `2025-v1`）
2. THE `audit_report` 表 SHALL 新增 `template_version` 字段，记录该报告生成时使用的 manifest 版本
3. WHEN 模板更新时，SHALL 替换 `backend/data/audit_report_templates/` 中的文件并递增 manifest 版本号
4. WHEN 模板更新后，已生成的项目报告 SHALL 继续使用其 `storage/deliverables/` 中的副本，不受新版影响
5. THE Fill_Service SHALL 支持"使用新版模板重新生成"操作（需用户明确触发，走 confirm 流程并 version_no +1）

### 需求 9：财务报表 Excel 模板数据填充

**用户故事：** 作为审计项目经理，我希望系统将审定后的试算表数据自动填入财务报表 Excel 模板中对应的单元格，保留模板原始格式（行高/列宽/字体/边框/合并单元格/公式），生成可直接出品的报表文件。

> 模板整理前置见 [`template-preparation.md`](./template-preparation.md) §三（表头占位符 + 数据格 `{{row:BS-xxx:current/prior}}`）。

#### 验收标准

1. THE 财务报表模板 xlsx SHALL 存储在 `financial_statements/` 下（4 个文件），路径仅通过 manifest 解析
2. THE 报表模板整理阶段 SHALL 在 xlsx 写入：**表头** `{{company_full_name}}`、`{{period_end_date}}`、`{{audit_year}}`、`{{currency_unit}}`；**数据格** `{{row:BS-002:current}}` / `{{row:BS-002:prior}}`；附注列可选 `{{note_ref:BS-002}}`
3. THE `row_code` SHALL 与 `report_config` / `financial_report` 对齐；`cell_mapping.json` 为内联占位的导出产物或回退映射（含 `sheet_aliases`、`headers`、`rows`）
4. THE manifest SHALL 含 `sheet_aliases`，将实际 sheet 名映射到 `report_type`；`GT_Custom` 等非出品 sheet SHALL 删除或 `hidden_in_export`
5. WHEN 生成财务报表，`ReportExcelExporter` SHALL：copy 模板 → 替换表头 `{{}}` → 优先读内联 `{{row:…}}` 填数 → 回退 cell_mapping → 跳过公式格
6. THE 主表 sheet：资产负债表、利润表、现金流量表、所有者权益变动表；减值明细等 manifest 单独标注
7. IF row_code 无数据，按 `fill_empty_as`（blank/zero）填入
8. THE Generated xlsx SHALL 提交交付件中心；格式与模板一致
9. WHEN 模板不存在，fallback 从零生成并 log warning

### 需求 10：附注 Word 模板数据填充

**用户故事：** 作为审计项目经理，我希望系统将附注章节内容填入附注 Word 模板，保留致同规定的格式（章节标题/缩进/表格样式），生成可直接出品的附注文件。

> 模板整理前置见 [`template-preparation.md`](./template-preparation.md) §二（`section_code` = 种子 `section_number`，`##SECTION:` 块，`##STYLE_REF:`）。

#### 验收标准

1. THE 附注模板 docx SHALL 在 `disclosure_notes/` 下（4 文件），章节清单与 `note_template_{soe|listed}.json` 一致
2. THE **section_code** SHALL 等于对应种子 JSON 的 `section_number`（国企如 `八、1`、上市如 `五、1`），等于 DB `note_section`；`section_id` slug 写入 `section_code_index.json` 而非 Word
3. THE 每章节 SHALL 用 `##SECTION:section_code##…##/SECTION:…##` 包裹，内含：`{{seq:}}` 标题、`{{section:code}}`（文字）、`{{table:code:N}}`（表格）、`##STYLE_REF:table:code##`（样式参考）
4. THE 整理阶段 SHALL 删除「使用说明」及【…】/（…删除）提示；封面用通用 `{{field}}`
5. THE `NoteWordExporter` SHALL 支持 `mode=template|programmatic`；模板整理完成前可暂用 programmatic
6. WHEN 生成（template）：copy → 通用占位符 → 按 section_code 填 text/table → 克隆 STYLE_REF → 裁剪章节块（需求 12）
7. THE 多表章节 SHALL 与 `note_template_bindings.json` 的 `table_index` 及 `{{table:code:N}}` 对齐
8. THE 国企/上市序号差异 SHALL 遵循 `note_template_variant_matrix.json`
9. THE Generated docx SHALL 提交交付件中心；重新生成 version_no+1
10. THE `section_code_index.json` SHALL 为每章节记录 `legacy_aliases`（历史旧编号，如国企 `五、1` ↔ 种子 `八、1`）；`NoteWordExporter` join 时 SHALL 支持 `note_section IN (section_code, *legacy_aliases)`
11. THE `build_section_code_index.py` SHALL 从种子 JSON 生成索引主体；`validate_note_template.py` SHALL 校验 Word `##SECTION:` 块与索引一一对应
12. THE 四套附注 Word 模板 SHALL 分别整理（不可交叉复制）；单体变体 SHALL 排除 JSON 中 `scope=consolidated_only` 章节（SOE 27 节、上市 22 节），合并变体 SHALL 保留
13. THE Word 中账户标题（如「货币资金」）通常**无** `八、1` 字样；`section_code` 仅出现在 `##SECTION:` 标记与 `section_code_index.json`，显示编号由 `{{seq:}}` 生成
14. THE `note_template_variant_matrix.json` SHALL 扩充并在附注初始化/导出主路径接入，解析 `template_type` + `report_scope` → 正确 `section_number`
15. THE `note_template_bindings_loader.get_binding_for_section` SHALL 经 `note_section_catalog.resolve_binding_key` 查表（国企 `五、N` 兜底 `八、N`）
16. THE `TemplateManifestLoader.resolve_disclosure_notes` SHALL 使用 `note_section_catalog.build_variant_key`，不得仅用 `template_type` 忽略 `report_scope`
17. THE 附注**显示编号**（`{{seq:prefix}}`、`get_section_numbers`）与**政策树编号**（`NoteSectionNumberingService`、`section_id`）SHALL 分工并存；模板填充只调用前者填 `{{seq:}}`

### 需求 11：统一模板资产管理与全套生成

**用户故事：** 作为系统管理员，我希望所有出品物模板（报告正文/财务报表/附注）统一管理在一个目录下，有清晰的清单和版本控制；作为项目经理，我希望一键生成全套出品物。

#### 验收标准

1. THE 所有模板资产 SHALL 统一存储在 `backend/data/audit_report_templates/` 下，子目录结构：
   ```
   audit_report_templates/
   ├── report_body/           # 审计报告正文（17个 docx）
   ├── financial_statements/  # 财务报表（4个 xlsx）
   ├── disclosure_notes/      # 附注（4个 docx）
   ├── template_manifest.json      # 清单 + sheet_aliases
   ├── matching_rules.json
   ├── cell_mapping.json           # 报表映射（内联导出/回退）
   ├── section_code_index.json     # 附注 section_code 索引
   └── placeholder_registry.json
   ```
2. THE `template_manifest.json` SHALL 包含三类模板的完整索引：
   - report_body：opinion_type + company_subtype + variant → 文件路径
   - financial_statements：template_type + scope → 文件路径
   - disclosure_notes：template_type + scope → 文件路径
3. WHEN 用户在交付件中心点击"一键生成全套出品物"时，SHALL 创建 `ExportJob(job_type='full_deliverables')`，按顺序异步执行：**财务报表 → 附注 → 报告正文**（与 `generateGuard.ts` 数据依赖链一致：试算表 → 报表 → 附注/报告），全部进入交付件中心；前端展示 `export_jobs_v2` 进度
4. EACH 生成的出品物 SHALL 独立版本管理（重新生成某一项不影响其他项）；失败项可单独重试
5. THE `template_manifest.json` SHALL 记录全局版本号，更新任一模板时版本号递增
6. THE 全套生成 SHALL 复用现有 `DeliverableService`、`export_jobs_v2`（扩展 `word_export.py` 逻辑接入 deliverable UI），非新建并行 job 系统
7. WHEN `full_deliverables` job 生成报告正文且无用户弹窗时，THE OPT 默认 SHALL 按以下优先级：
   ① payload 显式 `optional_sections`
   ② `audit_report.report_body_json.optional_sections`（上次人工选择）
   ③ `placeholder_registry.opt_defaults[company_subtype]`
   ④ 兜底：`key_audit_matters` = `kam_required()`；`comparative` = True；其余 False
8. THE job 内 report_body 步骤 SHALL 自动执行 preview → confirm（跳过 `OptionalSectionDialog`）；KAM 警告写入 job metadata 并在完成时 Toast

### 需求 12：附注模板与附注模块联动裁剪

**用户故事：** 作为审计项目经理，我希望导出附注时自动排除已删除/不适用/全空的章节，保留的章节自动重新编号，得到一份干净的、与附注编辑器内容完全一致的附注文档。

#### 验收标准

1. WHEN Fill_Service 处理附注模板时，SHALL 以 `disclosure_notes` 为内容源，`section_code` = `note_section` = 种子 `section_number`（国企如 `八、1`）；裁剪状态来自 `NoteSectionInstance` + `auto_trim_v2`；join 失败时查 `legacy_aliases`
2. THE 章节跳过判定 SHALL 按以下**优先级**（设计 §7.1）：
   - ① `is_deleted=True` → 删除整 SECTION 块
   - ② `status='not_applicable'`（`auto_trim_v2` 章节级）→ 删除整 SECTION 块
   - ③ `is_empty=True`（用户「不导出」）→ 删除整 SECTION 块
   - ④ `text_content` 空且所有表 `is_empty_table()` → 删除整 SECTION 块
   - ⑤ 单表全空但章节保留 → `no_business_paragraph` 替换
3. THE `should_skip_empty_section()` SHALL 扩展覆盖条件 ③④；与 `auto_trim_v2` 结果保持一致，不重复实现判定逻辑
4. WHEN 章节的 table_data 全部为 0/空（`is_empty_table()` 返回 True）但章节未被删除时，THE Fill_Service SHALL 将该表格替换为"本公司本期无此项业务"文字段落（与 `get_table_render_mode()` → `no_business_paragraph` 逻辑一致）
5. WHEN 删除章节后导致章节编号不连续时，THE Fill_Service SHALL 按实际保留的章节顺序重新编号（模板中使用 `{{seq:prefix}}` 占位符）
6. THE Fill_Service SHALL 复用 `should_skip_empty_section()`（含 `is_empty`）、`is_empty_table()`、`get_table_render_mode()`，不重复实现
7. WHEN 用户在附注编辑器中更改"不导出"状态后重新生成附注出品物时，SHALL 反映最新 DB 状态（实时联动，非缓存）
8. THE 附注裁剪 SHALL 与 `note_trim_service.auto_trim_v2()` 三级判定结果保持一致（**仅引用 v2，废弃 v1 `auto_trim`**）：
   - 章节级（section_skipped）：TB 科目全 0 → `status='not_applicable'`
   - 段落级（section_deleted）：`is_section_empty()` → `is_deleted=true`
   - 表格级（table_replaced）：`is_table_data_empty()` → `table_data._render_as='no_business_paragraph'`

### 需求 13：附注章节编号自动重算

**用户故事：** 作为审计项目经理，我希望附注导出时章节编号自动根据保留的章节顺序重新计算，不出现编号跳跃，且与附注编辑器预览一致。

#### 验收标准

1. THE 系统 SHALL 提取 `note_section_numbering.py` 共享模块，导出 `compute_section_numbers(tree) -> dict[str, str]`
2. THE `get_section_numbers` 端点与附注模板 `{{seq:prefix}}` 填充 SHALL 均调用 `compute_section_numbers()`，保证前后端编号一致
3. THE 附注模板 docx 中的章节编号位置 SHALL 使用 `{{seq:chapter_prefix}}` 占位符（如 `{{seq:八}}`），Fill_Service 填充时按保留章节顺序递增替换
4. WHEN 同一大章节下有部分子章节被删除时，保留章节的编号 SHALL 从 1 重新连续递增
5. THE 编号规则 SHALL 为：按章节前缀分组，组内连续编号；**组内仅 1 个条目时不编号**（与现有 `get_section_numbers` 端点行为一致）
6. WHEN 大章节下所有子章节都被删除时，THE Fill_Service SHALL 同时删除该大章节的标题行
7. THE 编号格式 SHALL 保持与致同附注格式一致：一级用中文数字（一、二、三…），二级用阿拉伯数字（1、2、3…）

### 需求 14：生成前置守卫与数据依赖链

**用户故事：** 作为审计项目经理，我希望三类出品物生成入口的前置检查一致，避免在无数据时生成空文件。

#### 验收标准

1. THE 三类生成入口（报表 / 附注 / 报告正文）SHALL 复用 `generateGuard.ts` 纯逻辑：
   - 生成报表：依赖 `trialBalanceReady`
   - 生成附注：依赖 `reportsReady`
   - 生成报告正文：依赖 `reportsReady`
2. THE 数据依赖链 SHALL 为：**试算表就绪 → 财务报表 → 附注 / 报告正文**（需求 11 全套生成顺序与此一致）
3. WHEN "一键生成全套"时，SHALL 在 job 级别校验前置条件，单项失败不阻断其他已完成项的重试
4. THE 前置守卫 SHALL 在交付件中心三个入口与审计报告编辑器入口保持一致提示文案

### 需求 15：遗留路径下线与兼容

**用户故事：** 作为开发人员，我希望迁移完成后不存在多套并行的导出/storage 路径，降低维护成本。

#### 验收标准

1. THE `WordTemplateFiller` 写入 `storage/projects/{id}/reports/` 的路径 SHALL 在 Phase 3 完成后废弃
2. THE 所有新品类物 SHALL 仅通过 `DeliverableService` 写入 `storage/deliverables/{project_id}/{task_id}/`
3. THE `ReportBodyService` JSON 段落主生成路径 SHALL 在 Phase 2 完成后标记 deprecated，并在 Phase 3 移除对应 API 默认行为
4. THE `ReportExcelExporter.TEMPLATE_MAP` 硬编码旧路径 SHALL 在 Phase 1 完成后删除
5. THE 迁移期 SHALL 提供 feature flag `USE_TEMPLATE_FILL_SERVICE`（默认 false → true），便于灰度切换

### 需求 16：测试与验收

**用户故事：** 作为 QA，我希望关键路径有自动化测试覆盖，避免格式回归。

#### 验收标准

1. THE 测试套件 SHALL 覆盖以下项：
   - manifest 缺失文件 → 启动 warning，不 crash
   - manifest 引用 `.doc` → CI 拒绝
   - `merge_runs_for_replace` 分割占位符替换
   - OPT 段落删除后段落样式/页码不变（snapshot 对比）
   - 附注裁剪后编号与 `compute_section_numbers()` 一致
   - 报表公式单元格不被 `_fill_template` 覆盖
   - 重新生成 → `version_no+1`，旧版可下载
   - `company_subtype` 未填 → matching_rules 优先，fallback 推断
   - `is_empty=True` 章节在附注导出中被移除
   - 两阶段 API：preview 不落库，confirm 才创建 deliverable_version
   - `validate_kam_word_mode`：OPT 未勾选 KAM + 上市 → validation_warning
   - `full_deliverables` job：无弹窗时 OPT 默认 + KAM 警告 metadata
   - `legacy_aliases` join：DB `note_section=五、1` 可匹配种子 `八、1` SECTION 块
   - `report_scope=standalone` 不初始化/不导出 `consolidated_only` 章节
   - `_detect_level`：`八、1` → level 2，非 level 1
2. THE 附注裁剪测试 SHALL 扩展现有 `test_note_auto_trim_v2.py`
3. THE 交付件版本测试 SHALL 复用 `test_deliverable_center_integration.py`
4. THE 格式保真度 SHALL 通过致同模板 spot check 清单人工验收（字体/页眉页脚/表格边框，每类模板至少 1 份）

### 需求 17：非功能需求

**用户故事：** 作为系统运维，我希望大批量生成稳定可控，不阻塞主 API。

#### 验收标准

1. WHEN 附注章节数 > 100 或全套生成时，THE 操作 SHALL 通过 `export_jobs_v2` 异步执行，并返回 job_id + 进度
2. THE 单次 preview 操作 SHALL 在 30s 内完成（不含用户确认等待时间）；超时返回明确错误
3. THE 模板资产总大小 SHALL 记录在 manifest metadata 中；Docker 镜像构建 SHALL 包含 `audit_report_templates/` 目录
4. THE OnlyOffice 回调保存 SHALL 继续走现有 `onlyoffice_callback_service`，不新增并行编辑通道

---

## 附录 A：服务职责对照（实施后目标态）

| 服务 | 职责 |
|------|------|
| `TemplateManifestLoader` | 唯一模板索引、版本号、启动校验 |
| `TemplateFillService` | 报告正文 Word 填充流水线（preview/confirm） |
| `ReportExcelExporter` | 财务报表 xlsx 填充（读 manifest + cell_mapping） |
| `NoteWordExporter` | 附注 docx 导出（`mode=template` 主路径 + `programmatic` 兼容） |
| `note_section_catalog` | 附注唯一对齐层（variant_key / scope / section_code 归一） |
| `note_section_numbering` | 显示编号：`compute_section_numbers` → `{{seq:}}` |
| `note_section_numbering_service` | 政策树编号：`section_id` / Jinja `ref()`（已有） |
| `DeliverableService` | 版本链、存储、OnlyOffice、哈希、权限（不变） |
| `ReportBodyService` | 迁移期 HTML 预览/校验辅助 → 最终 deprecated |
| `WordTemplateFiller` | 迁移期保留 → Phase 3 下线 |

## 附录 B：实施优先级

| 优先级 | 内容 |
|--------|------|
| P0 | `.doc→docx`、TemplateManifestLoader、统一存储路径、PlaceholderRegistry + merge_runs |
| P1 | 两阶段 API、ReportExcelExporter 切换 manifest、NoteWordExporter 模板模式、章节编号共享模块 |
| P2 | matching_rules wizard、ExportJob 全套生成 UI、遗留路径下线 |

## 附录 C：命名对照（避免混用）

| 名称 | 位置 | 角色 |
|------|------|------|
| 模板资产目录 | `backend/data/audit_report_templates/` | Word/xlsx 物理文件，**唯一生成源** |
| DB 段落种子 | `audit_report_templates_seed.json` | 旧 JSON 段落，迁移期只读 |
| docxtpl 壳 | `report_body_deliverable.docx` | 废弃 |
| 附注 JSON 种子 | `note_template_{soe\|listed}.json` | `section_number` 权威清单 |
| 附注 bindings | `note_template_bindings.json` | 表格取数语义 |
| section 索引 | `section_code_index.json` | section_code + legacy_aliases |
