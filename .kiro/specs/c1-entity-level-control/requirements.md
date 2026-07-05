# Requirements Document

> C1 企业层面控制测试专属组件

## Introduction

C1 企业层面控制测试（整合审计适用）是内部控制审计中评价被审计单位 COSO 五要素（控制环境、风险评估、控制活动、信息与沟通、监督）层面控制的核心底稿，共 12 个 sheet：C1 主程序表（137 行，按五要素分组的询问/观察/调查程序）+ C1-1~C1-3 三个测试示例 + C1-4 财务报告内部控制（C1-4-1~C1-4-6 六个过程记录子表，其中 C1-4-4 含 19 公式的会计分录人工授权测试样本表）。

当前以通用 `d-form-table` 渲染，缺乏企业层面控制专属交互（五要素分组导航、程序适用性裁剪、过程记录表样本测试）。本需求将其升级为专属精美组件 `c1-entity-level-control`，对齐 D4 标准（sheetName v-if 分发 + composable + GtIndexChip + 只读透传），提供五要素分组的程序中控台 + 财报内控过程记录子表。

## Glossary

- **C1_Component**：企业层面控制测试专属组件，componentType `c1-entity-level-control`
- **COSO 五要素**：控制环境 / 风险评估 / 控制活动 / 信息与沟通 / 监督
- **企业层面控制程序表**：C1 主 sheet，按五要素分组的询问/观察/调查测试程序（是否适用/执行人/测试结果说明/索引号）
- **过程记录表**：C1-4-x 财务报告内部控制过程记录（活动/流程/控制/客户控制描述/测试方法/测试结果样本）
- **示例 sheet**：C1-1~C1-3 企业层面控制测试示例（只读参考）
- **wp_code_overrides**：底稿编码 → componentType 精确映射 JSON
- **htmlRendererRegistry**：前端 componentType → Vue 组件单一来源注册表
- **GtAProgramConsole**：审计程序表通用渲染中控台组件（可复用于程序表分组渲染）
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **checklist_responses**：数据持久化表，item_id 前缀 `C1-`
- **适用性裁剪**：程序步骤标记「是否适用」，不适用需填理由

## Requirements

### Requirement 1: 组件注册与路由

**User Story:** 作为开发者，我希望 C1 打开时渲染专属组件而非通用表格。

#### Acceptance Criteria

1. THE C1_Component SHALL 在 htmlRendererRegistry 注册为 componentType `c1-entity-level-control`（defineAsyncComponent, contextProps standard）
2. THE wp_code_overrides SHALL 将 C1 映射为 `c1-entity-level-control`
3. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 注册 `c1-entity-level-control`，后端 validate_overrides 校验通过
4. THE C1_Component SHALL 具备后端 RENDERER_DISPATCH 注册，避免被 onlyoffice-sheet 兜底吞掉
5. THE C1_Component SHALL 接收标准 props：wpId、projectId、wpCode、year、readonly，并以 sheetName prop v-if 分发内部各 sheet（不含内部 el-tabs）

### Requirement 2: 五要素分组程序中控台

**User Story:** 作为审计助理，我希望 C1 主程序表按 COSO 五要素分组呈现，快速定位测试程序。

#### Acceptance Criteria

1. THE C1_Component SHALL 将主程序表按源模板九段（控制环境/风险评估/监督/监控业务单元/信息与沟通/财务报告/对业务层面控制的影响/年终程序/关联方相关内容）分组展示；COSO 五要素作为方法论叙述保留（Phase0 实测：源模板为九段而非五段）
2. THE C1_Component SHALL 复用 GtAProgramConsole 渲染程序步骤（序号/程序/是否适用/执行人/测试结果说明/索引号）
3. THE C1_Component SHALL 支持展开/收起各要素分组，顶部显示各组完成进度
4. WHEN 程序步骤为空但存在网格数据时，THE C1_Component SHALL 以 GtGridSheet 只读兜底渲染

### Requirement 3: 程序适用性裁剪

**User Story:** 作为现场经理，我希望标记不适用的程序步骤并填写理由，聚焦本项目实际执行的测试。

#### Acceptance Criteria

1. THE C1_Component SHALL 为每个程序步骤提供「是否适用」标记
2. WHEN 标记为不适用时，THE C1_Component SHALL 要求填写不适用理由
3. THE C1_Component SHALL 在分组进度统计中排除不适用的步骤
4. THE 适用性标记 SHALL 即时保存

### Requirement 4: 财务报告内部控制过程记录子表

**User Story:** 作为审计助理，我希望 C1-4 财报内控的过程记录表能填写控制描述、测试方法与样本测试结果。

#### Acceptance Criteria

1. THE C1_Component SHALL 以 sheetName v-if 分发 C1-4 及 C1-4-1~C1-4-6 各过程记录子表
2. THE 过程记录表 SHALL 呈现字段：活动名/流程名/控制/客户控制描述/控制编码/控制频率/执行日期/测试方法/如何测试/测试结果
3. WHERE 过程记录表含样本测试（如 C1-4-4 会计分录授权测试），THE C1_Component SHALL 提供样本明细行（日期/账户编码/引用/交易描述/借方/贷方）并保留源模板公式
4. WHEN 样本明细变更时，THE 汇总/勾稽公式单元格 SHALL 实时重算且不可手工覆盖

### Requirement 5: 示例参考 sheet

**User Story:** 作为审计助理，我希望查看 C1-1~C1-3 测试示例作为编制参考。

#### Acceptance Criteria

1. THE C1_Component SHALL 以 sheetName v-if 分发 C1-1/C1-2/C1-3 示例 sheet
2. THE 示例 sheet SHALL 以只读方式原样渲染，标注「示例（供参考）」
3. THE 示例 sheet SHALL 不参与完成进度统计

### Requirement 6: 跨底稿引用 chip

**User Story:** 作为审计助理，我希望程序索引列引用的其他底稿以可点击 chip 呈现并跳转。

#### Acceptance Criteria

1. WHERE 程序表/过程记录表的索引列包含其他底稿编码，THE C1_Component SHALL 以 GtIndexChip 呈现（prop 名 `value`）
2. WHEN 用户点击 chip 时，THE C1_Component SHALL 触发全局底稿跳转导航
3. IF 引用底稿在 wp_index 中不存在，THEN THE GtIndexChip SHALL 显示灰态并提示「底稿不存在」

### Requirement 7: 数据持久化

**User Story:** 作为审计助理，我希望所有测试数据自动保存。

#### Acceptance Criteria

1. THE C1_Component SHALL 将数据存储到 checklist_responses，使用 item_id 前缀 `C1-`（如 `C1-env-{n}-applicable`、`C1-4-4-sample-{s}-amount`）
2. WHEN 文本字段编辑停止 2 秒时，THE C1_Component SHALL debounce 保存
3. WHEN 适用性标记/测试方法/结论变更时，THE C1_Component SHALL 立即保存
4. THE C1_Component SHALL 通过 GET/PUT `/api/workpapers/{wp_id}/checklist-responses` 加载/保存
5. WHEN 保存失败时，THE C1_Component SHALL 提示错误并保留本地编辑内容

### Requirement 8: 只读模式与 UI 规范

**User Story:** 作为复核合伙人，我希望只读模式下不可编辑；作为审计助理，我希望 UI 统一美观。

#### Acceptance Criteria

1. WHEN readonly 为 true 时，THE C1_Component SHALL 禁止所有输入编辑与样本行增删，仅浏览与跳转
2. THE 表格 SHALL 使用 13px 字体；公式列以虚线下划线 + cursor:help + tooltip 展示来源
3. THE 测试结果说明区 SHALL 以 el-card 包裹，section 标题行右侧提供 AI 辅助按钮
4. THE 金额显示 SHALL 默认以「元」为单位并经统一格式化出口（fmt）

### Requirement 9: 点选交互与操作提示

**User Story:** 作为审计助理，我希望尽量通过点选（下拉/单选/多选）完成填报，减少手工输入，并在关键处看到操作提示。

#### Acceptance Criteria

1. THE C1_Component SHALL 将判断/枚举字段（是否适用、测试方法、测试结论、控制频率）实现为下拉/单选/多选 tag 点选控件，而非自由文本输入
2. WHERE 字段仅需长文本叙述（如测试结果说明、不适用理由），THE C1_Component SHALL 使用 autosize textarea 并提供 AI 辅助生成按钮
3. THE C1_Component SHALL 在顶部提供蓝色渐变引导区（2 列 grid 序号步骤：填写项目信息 → 逐要素测试 → 财报内控过程记录 → 结论）
4. THE C1_Component SHALL 将源模板红字提示以「方法论上下文」样式（琥珀色左边线区块）嵌入对应要素分组上方
5. THE C1_Component SHALL 为公式列/判断列提供 tooltip 说明来源与判断依据
6. WHEN 用户完成某要素全部适用步骤的点选时，THE C1_Component SHALL 自动更新该组完成进度指示

### Requirement 10: 附件上传与 OCR

**User Story:** 作为审计助理，我希望在过程记录与样本测试处上传证据附件并通过 OCR 自动识别填充，减少手工转录。

#### Acceptance Criteria

1. THE C1_Component SHALL 在 C1-4-x 过程记录表与样本明细行提供 📎 附件上传列
2. WHEN 用户上传凭证/记录图片或 PDF 时，THE C1_Component SHALL 调用 OCR 端点识别关键字段（日期/账户编码/金额/摘要）
3. WHEN OCR 返回结果时，THE C1_Component SHALL 弹出确认弹窗（ElMessageBox）供用户核对后 merge 填入样本行，不直接覆盖
4. IF OCR 服务不可用或识别失败，THEN THE C1_Component SHALL 提示「识别失败，请手动填写」且保留已上传附件
5. THE 上传的附件 SHALL 与对应 item_id 关联持久化，只读模式下仅可查看不可删除

### Requirement 11: 结论回写与联动

**User Story:** 作为现场经理，我希望 C1 企业层面控制结论与识别的缺陷能联动到风险评估与缺陷评价底稿，形成闭环。

#### Acceptance Criteria

1. WHEN C1 整体测试结论变更时，THE C1_Component SHALL 通过 EventBus 发布企业层面控制结论事件供 B50 风险评估订阅
2. WHERE 测试识别出企业层面控制缺陷，THE C1_Component SHALL 提供 GtIndexChip 一键跳转 A14 缺陷评价底稿并带入缺陷摘要
3. THE C1_Component SHALL 汇总各要素测试结论生成企业层面控制整体结论（点选 + 自动建议）
4. THE C1_Component SHALL 仅在结论实际变更（新旧值不同）时发布事件
