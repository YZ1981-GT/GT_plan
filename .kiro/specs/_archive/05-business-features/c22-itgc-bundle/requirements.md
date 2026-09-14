# Requirements Document

> C22 IT 一般控制测试聚合组件（含 C21 IT 专业成员 + C21-1 IT 发现汇总）

## Introduction

IT 一般控制（ITGC）是内部控制审计中评价信息技术环境可靠性的核心，本 spec 聚合三个相关底稿为单一 `c22-itgc-bundle` 组件（IT 控制大组件）：

- **C22 IT一般控制测试**（34 sheets）：主表为 ITGC 控制矩阵（4 大类：信息安全 SA / 运行维护 PE / 程序变更 PM / 新系统上线 NS；每条含风险编号 ITRxxx、控制编号、控制描述、相关应用系统、设计有效性结论、执行有效性结论、是否异常、缺陷编号），下辖 SA-3/4c/5/7/9/10/…、PE-3a/3d/5/6/7/8、PM-3/4/5/6、NS-1/3/4/5/6 等 33 个 IT 控制域测试子页（每页含设计有效性程序 + 执行有效性测试样本 + 样本记录 + 缺陷评估，并索引至 C21-1）
- **C21 具有信息技术专业技能的项目组成员**：评估项目组是否具备 IT 审计胜任能力
- **C21-1 IT 审计发现汇总表**：汇总所有 IT 控制测试发现的缺陷

当前零散呈现于目录。本需求将其聚合为一行分组页签的大组件，遵循已验证的 `s34-ipo-bundle` / `a17-bundle` 聚合模式，主矩阵作总览导航，子页缺陷自动汇总到 C21-1。

## Glossary

- **C22_Bundle**：聚合组件，componentType `c22-itgc-bundle`，分发渲染 C22 主矩阵 + 33 IT 控制域子页 + C21 + C21-1
- **ITGC 控制矩阵**：C22 主 sheet，IT 一般控制清单（4 大类 × 控制编号 × 控制描述 × 设计/执行有效性结论 × 缺陷编号）
- **IT 控制域**：SA（信息安全）/ PE（运行维护）/ PM（程序变更）/ NS（新系统上线）四大类，每个具体控制点如 SA-3、PE-3a
- **IT 控制测试子页**：单个控制点的测试 sheet（设计有效性程序 + 执行有效性测试 + 样本记录 + 缺陷评估）
- **IT 发现汇总表（C21-1）**：汇总各子页识别的缺陷（缺陷编号/描述/影响/整改建议）
- **wp_code_overrides**：底稿编码 → componentType 精确映射 JSON
- **htmlRendererRegistry**：前端 componentType → Vue 组件单一来源注册表
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **useC22BundleState**：轻量 composable，管理子页 wp_id/sheet 映射、缺陷汇总、完成状态
- **CompletionStatus**：`completed` / `in_progress` / `not_started`
- **缺陷联动**：子页「是否异常=是」的缺陷自动汇总到 C21-1

## Requirements

### Requirement 1: 聚合入口组件注册

**User Story:** 作为审计助理，我希望点击 C22 打开统一的 IT 控制大组件，在同一界面按 IT 控制域访问全部测试子页与发现汇总。

#### Acceptance Criteria

1. THE C22_Bundle SHALL 在 htmlRendererRegistry 注册为 componentType `c22-itgc-bundle`（defineAsyncComponent, contextProps standard）
2. THE wp_code_overrides SHALL 将 C22 映射为 `c22-itgc-bundle`
3. THE C22_Bundle SHALL 接收 props：wpId、sheetName（可选）、readonly（可选）
4. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 注册 `c22-itgc-bundle`，后端 validate_overrides 校验通过

### Requirement 2: 子底稿映射为 skip

**User Story:** 作为现场经理，我不希望 C22 子页与 C21/C21-1 在目录重复显示为独立条目。

#### Acceptance Criteria

1. WHEN C22_Bundle 启用后，THE wp_code_overrides SHALL 将 C21、C21-1 映射为 `skip`（并入本 bundle 的 IT 专业成员/发现汇总 Tab）
2. THE wp_code_overrides SHALL 将 C22 映射为 `c22-itgc-bundle`；C22 内部 33 子页为同一工作簿的 sheet，由组件内部分发
3. WHEN 底稿目录加载时，THE 系统 SHALL 对 componentType 为 `skip` 的底稿不渲染为独立条目

### Requirement 3: ITGC 控制矩阵总览面板

**User Story:** 作为现场经理，我希望进入 C22 时首先看到 ITGC 控制矩阵总览，一屏掌握 4 大类各控制点的设计/执行有效性结论与缺陷。

#### Acceptance Criteria

1. THE C22_Bundle SHALL 默认展示 `matrix` 总览面板，渲染 C22 主矩阵
2. THE matrix 面板 SHALL 呈现每个控制点：IT 控制类别、风险编号（ITRxxx）、控制编号（SA/PE/PM/NS）、控制描述、相关应用系统、设计有效性结论、执行有效性结论、是否异常、缺陷编号
3. WHEN 用户点击矩阵中某控制点行时，THE C22_Bundle SHALL 切换到对应控制域测试子页 Tab
4. THE matrix 面板 SHALL 显示整体完成进度（按控制点：已完成/进行中/未开始）与缺陷统计

### Requirement 4: 分组页签结构与渲染分发

**User Story:** 作为审计助理，我希望 33 个 IT 控制域子页按 4 大类分组呈现于一行可滚动页签，每个 Tab 渲染对应控制点测试。

#### Acceptance Criteria

1. THE C22_Bundle SHALL 以一行页签展示：matrix 总览 + 4 大类分组（信息安全 SA / 运行维护 PE / 程序变更 PM / 新系统 NS）子页 + C21 IT专业成员 + C21-1 发现汇总
2. WHERE Tab 数量超过单行可视宽度，THE C22_Bundle SHALL 提供可滚动/分组切换
3. WHEN 某 IT 控制域子页 Tab 被选中时，THE C22_Bundle SHALL 渲染该子页（设计有效性程序 + 执行有效性测试样本 + 样本记录 + 缺陷评估）
4. THE 子页 SHALL 保留源模板对主矩阵的公式引用（控制编号/活动引用主表单元格）

### Requirement 5: 缺陷汇总联动 C21-1

**User Story:** 作为现场经理，我希望各 IT 控制域子页识别的缺陷自动汇总到 C21-1 IT 发现汇总表，避免手工转录。

#### Acceptance Criteria

1. THE useC22BundleState SHALL 收集所有子页「是否异常=是」的缺陷（缺陷编号/所属控制点/缺陷描述）
2. WHEN 某子页缺陷评估变更时，THE C22_Bundle SHALL 更新 C21-1 汇总视图
3. THE C21-1 Tab SHALL 展示汇总的缺陷列表并允许补充影响分析与整改建议
4. THE 子页缺陷评估区 SHALL 提供 GtIndexChip 跳转到 C21-1

### Requirement 6: Tab 路由与外部跳转

**User Story:** 作为审计助理，我希望从外部 RefChip / URL 直接定位到指定 IT 控制域子页或矩阵。

#### Acceptance Criteria

1. WHEN 外部通过 `navigate('C22', { sheet: 'SA-3' })` 跳转时，THE C22_Bundle SHALL 直接激活 `SA-3` Tab
2. WHEN URL query 含 `?sheet=SA-3` 时，THE C22_Bundle SHALL 解析并激活对应 Tab
3. WHEN props.sheetName 变更时，THE C22_Bundle SHALL 响应切换 Tab
4. IF sheetName 不在可见 Tab 列表中，THEN THE C22_Bundle SHALL 保持当前 Tab（默认 matrix）

### Requirement 7: 完成进度与缺陷仪表盘

**User Story:** 作为现场经理，我希望看到 IT 控制测试的整体完成进度与缺陷数量。

#### Acceptance Criteria

1. THE useC22BundleState SHALL 通过读取各子页设计/执行有效性结论推导每个控制点的 CompletionStatus
2. THE C22_Bundle SHALL 在页签栏上方显示完成进度仪表盘（已完成/进行中/未开始，三色）+ 缺陷总数
3. WHEN 某子页状态或缺陷变化时，THE 仪表盘 SHALL 实时更新
4. WHEN 用户从某子页切走时，THE useC22BundleState SHALL 刷新该子页状态

### Requirement 8: C21 IT 专业成员评估

**User Story:** 作为现场经理，我希望在 C22 组件内评估项目组 IT 审计胜任能力。

#### Acceptance Criteria

1. THE C22_Bundle SHALL 提供 C21 Tab 渲染 IT 专业成员评估表
2. THE C21 Tab SHALL 保留源模板的下拉选项（命名区域数据验证）
3. THE C21 评估 SHALL 与其余 Tab 一致地持久化与只读透传

### Requirement 9: 只读模式透传

**User Story:** 作为质量控制复核合伙人，我希望只读复核模式下所有子页、矩阵与汇总均不可编辑。

#### Acceptance Criteria

1. WHEN C22_Bundle 的 readonly 为 true 时，THE C22_Bundle SHALL 将 readonly 传递给所有子页与汇总渲染
2. WHILE 只读模式时，THE 子页测试 SHALL 禁止结论/样本/缺陷编辑
3. THE matrix 与 C21-1 汇总 SHALL 在只读模式下仍可浏览与跳转

### Requirement 10: 点选交互与操作提示

**User Story:** 作为审计助理，我希望 IT 控制测试尽量通过点选完成，减少手工输入，并在关键处看到操作提示。

#### Acceptance Criteria

1. THE C22_Bundle SHALL 将设计有效性结论、执行有效性结论、是否异常等判断字段实现为下拉/单选点选控件
2. THE C22_Bundle SHALL 将矩阵中的 IT 控制类别、相关应用系统实现为下拉/多选点选
3. WHERE 字段为长文本（执行的审计程序描述、缺陷描述），THE C22_Bundle SHALL 使用 autosize textarea + AI 辅助按钮
4. THE C22_Bundle SHALL 在 matrix 总览与子页顶部提供操作引导提示与源模板方法论上下文（琥珀色区块）
5. THE C22_Bundle SHALL 为控制编号/风险编号列提供 tooltip 展示完整控制描述与风险描述

### Requirement 11: 附件上传与 OCR

**User Story:** 作为审计助理，我希望在 IT 控制测试子页上传审计证据并自动关联证据索引编号。

#### Acceptance Criteria

1. THE C22_Bundle SHALL 在每个 IT 控制域子页的审计证据区与样本记录行提供 📎 附件上传
2. WHEN 用户上传证据文件时，THE C22_Bundle SHALL 按源模板编号规则自动建议证据索引号（如 `C22.SA-3-1`）
3. WHEN 上传制度/审批记录图片或 PDF 时，THE C22_Bundle SHALL 调用 OCR 识别关键信息（制度名称/更新时间/审批时间/审批人）并经确认弹窗 merge 填入样本记录
4. IF OCR 失败，THEN THE C22_Bundle SHALL 提示手动填写并保留附件
5. THE 附件 SHALL 与子页 item_id 关联持久化，只读模式仅可查看

### Requirement 12: 缺陷回写与联动强化

**User Story:** 作为现场经理，我希望 IT 控制缺陷一键汇总到 C21-1 并联动到 A14 缺陷评价。

#### Acceptance Criteria

1. WHEN 子页「是否异常=是」时，THE C22_Bundle SHALL 自动生成缺陷条目并回写 C21-1 IT 发现汇总表
2. THE C22_Bundle SHALL 在 C21-1 汇总条目提供 GtIndexChip 一键跳转 A14 缺陷评价底稿并带入缺陷摘要
3. THE C22_Bundle SHALL 在缺陷回写时保留来源控制点编号与子页索引，支持双向追溯
4. WHEN 子页缺陷评估被清除（是否异常=否）时，THE C22_Bundle SHALL 从 C21-1 汇总移除对应缺陷条目
