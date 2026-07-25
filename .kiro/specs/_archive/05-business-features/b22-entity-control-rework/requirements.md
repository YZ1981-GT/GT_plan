# Requirements Document

## Introduction

本规格是对现有 **B22 企业层面控制（了解与评价）底稿组** 的系统性重做（rework），聚焦三项已对照代码与致同 2025 修订版源模板核实的结构性缺陷。**双模式（OnlyOffice）/ 版本链 / 复核入口 / 字号统一 / B22C 判断矩阵**已在前序快赢中直接落地，本规格不重复，仅将其作为回归保证纳入（Requirement 9）。

B22 位于风险导向审计内控评价链的最上游（企业层面），完整链路：

```
B22A 企业层面控制了解 → B22B 控制矩阵 → B22C 设计有效性评价 → B50 控制风险 → C 类控制测试 → D~N 实质性程序范围
                                                     ↘ A9-1/A9-2 内控缺陷沟通函（按严重程度分组）
```

### 现状映射（`wp_code_overrides.json`，已核实）

- `B22A` → `b22a-control-matrix`（单一 6-Tab 组件 `GtB22AControlMatrix.vue`）
- `B22A-1/2/3/4/4-1/4-2/4-3/4-4-1/4-4-2/4-5/5` → 全部 `skip`（合并进 B22A 6-Tab）
- `B22B` → `b22b-deficiency-evaluation`（**缺陷评价表** `GtB22BDeficiencyEvaluation.vue`）
- `B22C` → `b22c-design-effectiveness`（设计有效性缺陷汇总 `GtB22CDesignEffectiveness.vue`）

### 源模板真实结构（已逐 sheet 读取 xlsx 核实）

- **B22B 真实 = 控制矩阵登记册**，12 列：要素 / 子类别 / 编号 / 控制名称 / 详细控制描述 / 是否为反舞弊控制 / 控制频率 / 执行人 / 执行内部控制的人员的知识经验技能 / 与控制相关的风险 / 自动人工 / IT应用名称。
- **B22A-4-5 财务报告过程** 是信息与沟通下的独立 sheet，含 4 子过程：财务报表（期末）结账过程 / 合并过程 / 集团层面控制 / 财务报表编制过程，每子过程含「不适用」勾选 + 了解记录文本。
- **B22A-4-1~4-4-2 IT 详细** 是结构化多表：IT 概要（复杂度判断）/ 重大业务流程涉及的信息系统清单 / IT 环境（应用·基础设施·流程·信息处理 4 维）/ IT 一般控制 ITGC（安全与维护·作业调度与接口）/ IT 一般控制职责分离分析（角色 × 职责矩阵）。
- **B22C = 评价设计有效性缺陷汇总**：5 区块（要素）× 控制缺陷 / 值得关注的缺陷两级 + 区块小结，**当前实现已与源对齐**（不改结构）。

### 本次重做要解决的三项核心问题

1. **🔴 B22B 职能错位（P0，最大）**：源 B22B = 控制矩阵登记册，平台却把 wp_code `B22B` 映射成"缺陷评价表"；真正的控制矩阵反而以**只读导出**（`useB22AControlMatrix.controlMatrixRegister` + `exportControlMatrix`）藏在 B22A 内不可编辑；且 B22B(缺陷评价) 与 B22C(缺陷汇总) 职能重叠冗余。**关键约束**：后端 `_a91_deficiency_letter.py::_load_b22b_deficiencies` 读取 `checklist_responses` 中 `B22B-def-*` 键为 A9-1/A9-2 内控缺陷沟通函按严重程度分组，重命名/迁移不得破坏此下游联动。
2. **🟡 B22A-4-5 财务报告过程完全缺失（P1）**：当前 6-Tab 无此内容，审计师无处记录期末结账 / 合并 / 集团层面控制 / 编制过程的了解。
3. **🟡 IT 详细被压平（P1）**：源 B22A-4-1~4-4-2 的结构化内容被压成 Tab4 下 6 个同构通用"检查项表"（env/itgc/app/change/access/sod），丢失 IT 复杂度判断、系统清单、IT 环境 4 维、ITGC 分类、SoD 角色×职责矩阵。需先确定 IT 了解（归 B22A）与 ITGC 设计/运行测试（归 C22 `c22-itgc-bundle`）的边界。

### 目标

以致同源模板为基准恢复 B22B 控制矩阵的正确职能、补齐财务报告过程、结构化重建 IT 详细了解，同时**零回归地保全** B22B→A9 缺陷函联动与既有 B22A/B22C 数据。

## Glossary

- **B22A_Component**：componentType `b22a-control-matrix`（`GtB22AControlMatrix.vue`），企业层面控制了解主组件。
- **B22B_Matrix_Component**：本规格新建的控制矩阵专属组件 componentType `b22b-control-matrix`（源对齐后的 B22B）。
- **B22C_Component**：componentType `b22c-design-effectiveness`（`GtB22CDesignEffectiveness.vue`），设计有效性缺陷汇总，本规格将其确立为缺陷严重程度评价的**单一真源**。
- **Control_Matrix（控制矩阵）**：B22B 源模板的 12 列控制登记册。
- **Control_Point（控制点）**：控制矩阵中的一行，携带 12 列属性。
- **Deficiency（控制缺陷）**：识别的控制缺陷。
- **Deficiency_Severity（缺陷严重程度）**：企业内控审计三级（重大 / 重要 / 一般）；在 CAS 1152 财报审计口径映射为两级（值得关注 / 一般）。
- **A9_Deficiency_Loader**：`_a91_deficiency_letter.py::_load_b22b_deficiencies`，A9-1/A9-2 缺陷沟通函读取缺陷并分组的后端函数。
- **Financial_Reporting_Process（财务报告过程）**：B22A-4-5，含 4 子过程的信息与沟通子表。
- **IT_Understanding（IT 详细了解）**：B22A-4-1~4-4-2 的结构化 IT 了解内容。
- **ITGC_Boundary（IT 边界）**：IT 了解归 B22A、ITGC 设计/运行测试归 C22 的职责划分。
- **Management_Override（管理层凌驾）**：B22A-2，管理层和治理层凌驾于控制之上（CAS 1141 特别风险）。
- **Persistence_Store**：`checklist_responses` 表，item_id 前缀 `B22A-` / `B22B-` / `B22C-`。
- **Cross_Ref_Chip**：GtIndexChip 跨底稿跳转芯片。
- **Dual_Mode**：HTML ↔ OnlyOffice 双模式（已落地，见 Requirement 9）。
- **Registration_Set（注册集合）**：componentType 需一致更新的六处（`wp_code_overrides.json` / `dedicated_component_types.py` DEDICATED / `wp_render_config.py` self-contained + whitelist / `wp_classification_service.py` VALID / 前端 `htmlRendererRegistry.ts` / checklist_responses 白名单前缀）。

## Requirements

### Requirement 1: B22B 恢复为控制矩阵（源对齐，P0 决策）

**User Story:** As a 审计助理, I want wp_code B22B 打开的是可编辑的控制矩阵登记册（对齐致同源模板）, so that 我能在正确的底稿位置登记企业层面控制点及其完整属性，而不是面对一张与源模板不符的缺陷评价表。

#### Acceptance Criteria

1. THE B22B_Matrix_Component SHALL 以 componentType `b22b-control-matrix` 渲染控制矩阵登记册，作为 wp_code `B22B` 的唯一渲染组件。
2. THE Registration_Set SHALL 将 `B22B` 映射至 `b22b-control-matrix`，并在全部六处注册点保持一致。
3. WHEN B22A_Component 当前以只读导出形式展示 `controlMatrixRegister`, THE B22A_Component SHALL 保留该只读汇总视图作为跨要素总览（数据源仍为 B22A 各要素控制点），但不再是控制矩阵的唯一编辑入口。
4. THE B22B_Matrix_Component SHALL 支持从 B22A 各要素已登记的控制点带入初始行（仅填空，不覆盖已编辑行），并允许审计师在 B22B 独立增删改控制点。
5. WHERE 决策为方案 A（B22B 恢复控制矩阵）, THE 缺陷严重程度评价 SHALL 按 Requirement 3 收敛至 B22C_Component；WHERE 决策为方案 B（保留现状缺陷评价、B22A 登记册转可编辑）, THE spec SHALL 在 design 阶段据用户选择调整 Requirement 1/3/4 —— 本规格默认采用方案 A（源对齐 + 迁移），并在 design 明确列出方案 B 的回退路径。

### Requirement 2: 控制矩阵 12 列结构对齐源模板

**User Story:** As a 现场经理, I want 控制矩阵包含致同源模板的全部 12 列, so that 每个企业层面控制点的关键属性（反舞弊 / 频率 / 执行人 / 胜任能力 / 相关风险 / 自动人工 / IT应用）齐全，可流转到 C 类控制测试。

#### Acceptance Criteria

1. THE B22B_Matrix_Component SHALL 提供 12 列：要素、子类别、编号、控制名称、详细控制描述、是否为反舞弊控制、控制频率、执行人、执行人知识经验技能、与控制相关的风险、自动/人工、IT应用名称。
2. THE B22B_Matrix_Component SHALL 对枚举型列（要素 / 反舞弊 / 频率 / 自动人工 / 相关风险）提供下拉点选，减少手工输入。
3. THE B22B_Matrix_Component SHALL 持久化每行至 `checklist_responses`，item_id 前缀 `B22B-`，且不传 project_id（避免 422 project_mismatch）。
4. THE B22B_Matrix_Component SHALL 支持客户端 xlsx 导出，列顺序与源模板 12 列一致。

### Requirement 3: 缺陷严重程度评价收敛至 B22C（单一真源）

**User Story:** As a 质量控制复核合伙人, I want 控制缺陷的严重程度评价只在一个底稿维护, so that 不再出现 B22B(缺陷评价) 与 B22C(缺陷汇总) 职能重叠、口径分裂。

#### Acceptance Criteria

1. THE B22C_Component SHALL 作为控制缺陷及其严重程度的单一评价真源，承载缺陷描述、控制缺陷/值得关注缺陷判定与严重程度。
2. THE B22C_Component SHALL 继续从 B22A（识别出的设计无效/未实施控制）与（迁移后的）缺陷来源带入缺陷，仅填空不覆盖已编辑。
3. WHERE 现有 `B22B-def-*` 缺陷严重程度数据存在, THE 迁移逻辑 SHALL 将其映射并合并至 B22C 的持久化结构，且不重复、不丢失。
4. THE 缺陷严重程度 SHALL 保留企业内控口径（重大/重要/一般）与 CAS 1152 财报口径（值得关注/一般）的映射关系，供 A9 分组使用。

### Requirement 4: A9-1/A9-2 缺陷沟通函联动零回归

**User Story:** As a 业务合伙人, I want B22 重做后，A9-1/A9-2 内控缺陷沟通函仍能按严重程度自动分组缺陷, so that 现有缺陷沟通链路不因 B22B 职能调整而断裂。

#### Acceptance Criteria

1. THE A9_Deficiency_Loader SHALL 在重做后从缺陷单一真源（B22C，按 Requirement 3）读取缺陷并按严重程度（major/significant/general）分组。
2. THE A9_Deficiency_Loader SHALL 保持对既有 `B22B-def-*` / `b22b-deficiency-*` 持久化格式的向后兼容读取，直到迁移完成。
3. WHEN A9-1 加载缺陷, THE 分组结果（重大→major、重要→significant、一般→general）SHALL 与重做前对同一批缺陷数据的分组结果保持等价。
4. THE A9-2 治理层沟通函 SHALL 继续仅取 major/significant 两级，排除 general。

### Requirement 5: 补齐财务报告过程（B22A-4-5）

**User Story:** As a 审计助理, I want B22A 有财务报告过程的了解记录区, so that 我能按源模板记录期末结账、合并、集团层面控制、财务报表编制过程的了解。

#### Acceptance Criteria

1. THE B22A_Component SHALL 在信息与沟通要素下提供 Financial_Reporting_Process 记录区，含 4 子过程：财务报表结账过程、合并过程、集团层面控制、财务报表编制过程。
2. THE Financial_Reporting_Process SHALL 为每个子过程提供「不适用」勾选与了解记录文本框。
3. THE Financial_Reporting_Process SHALL 持久化至 `checklist_responses`，item_id 前缀 `B22A-frp-`。
4. WHERE 子过程被标记为不适用, THE B22A_Component SHALL 允许该子过程了解记录为空且不计入完成度缺口告警。

### Requirement 6: 结构化重建 IT 详细了解（B22A-4-1~4-4-2）

**User Story:** As a EQCR 技术复核人, I want B22A 的 IT 了解按源模板结构化呈现（复杂度 / 系统清单 / IT 环境 4 维 / ITGC 分类 / SoD 矩阵）, so that IT 了解内容完整可追溯，且与 C22 ITGC 测试边界清晰。

#### Acceptance Criteria

1. THE B22A_Component SHALL 将 Tab4 的 IT 区从 6 个同构通用检查表重建为结构化子区：IT 概要（复杂度判断）、重大业务流程涉及的信息系统清单、IT 环境（应用·基础设施·流程·信息处理 4 维）、IT 一般控制（安全与维护·作业调度与接口）、IT 职责分离分析（角色 × 职责矩阵）。
2. THE ITGC_Boundary SHALL 明确 IT 了解归 B22A，ITGC 设计有效性与运行有效性测试归 C22（`c22-itgc-bundle`），并通过 Cross_Ref_Chip 交叉引用 C22。
3. WHERE 现有 `B22A-T4-IT-*` 持久化数据存在, THE 迁移逻辑 SHALL 将旧的通用检查项数据映射至新结构对应槽位或明确标注为待复核，不静默丢弃。
4. THE IT 复杂度判断 SHALL 提供高/中/低点选，并保留现有「IT 依赖程度高 + ITGC 无效 → 告警」的业务规则。

### Requirement 7: 管理层凌驾（B22A-2）保持并强化联动

**User Story:** As a 现场经理, I want 管理层凌驾于控制之上的识别结果真正联动到 B50/C23/C24, so that CAS 1141 特别风险的应对在下游底稿可追溯。

#### Acceptance Criteria

1. THE B22A_Component SHALL 保留管理层凌驾专区（现 Tab2 子区 'mo'）的控制点录入、关键判断与缺陷识别。
2. WHEN 管理层凌驾专区识别出设计无效/未实施缺陷, THE B22A_Component SHALL 通过 EventBus 发布真实风险因素至 B50（`b50:push-risk-factor`）。
3. THE B22A_Component SHALL 提供指向 C23/C24 会计分录测试的 Cross_Ref_Chip 与范围提示。

### Requirement 8: 注册与渲染一致性

**User Story:** As a 开发者, I want B22B_Matrix_Component 的 componentType 在全部注册点一致, so that 不会被 onlyoffice-sheet 或 grid 兜底吞掉、也不会出现契约测试失败。

#### Acceptance Criteria

1. THE Registration_Set SHALL 在六处同步注册 `b22b-control-matrix`：wp_code_overrides、dedicated_component_types（若为整册专属）、wp_render_config（self-contained + whitelist）、wp_classification_service VALID、前端 htmlRendererRegistry、checklist_responses 白名单前缀 `B22B-`。
2. THE 契约测试 SHALL 验证 `b22b-control-matrix` 满足 DEDICATED⊆VALID∩FE、WHOLE−DISPATCH⊆WHITELIST∪CONFIRMATION 等既有注册契约。
3. WHERE B22B_Matrix_Component 为纯前端自加载（无 RENDERER_DISPATCH）, THE render-config SHALL 折叠为单 sheet 并清空 html_data.cells，避免 grid 兜底覆盖专属组件。

### Requirement 9: 已落地能力的回归保证（双模式/版本链/复核/B22C 判断矩阵）

**User Story:** As a 审计助理, I want 前序快赢已落地的双模式、版本链、复核入口、B22C 判断矩阵在本次重做后仍然可用, so that 重做不引入回归。

#### Acceptance Criteria

1. THE B22A_Component、B22B_Matrix_Component、B22C_Component SHALL 各自具备 Dual_Mode 工具栏，OnlyOffice 选项仅在健康检查通过（拉取成功）时可选，否则禁用并提示不可用。
2. THE 三个组件 SHALL 各自具备版本链（GtWpVersionTrail + 保存后 scheduleAutoSnapshot）与复核入口（GtReviewTrigger）。
3. THE B22C_Component SHALL 保留可勾选的值得关注缺陷判断矩阵（5 迹象 + 9 因素），任一迹象勾选时给出「存在值得关注的缺陷」建议。
4. THE 重做 SHALL NOT 移除或降级上述已落地能力。

### Requirement 10: 数据迁移与向后兼容

**User Story:** As a 现场经理, I want 已在旧 B22 底稿录入的数据在重做后不丢失, so that 已完成的工作不需要重录。

#### Acceptance Criteria

1. WHEN 重做后首次加载已有 B22B 数据, THE 系统 SHALL 兼容读取旧 `B22B-def-*` 缺陷数据（供 A9 与迁移使用），且不因新控制矩阵结构报错。
2. THE 迁移 SHALL 为幂等操作，重复执行不产生重复行或数据漂移。
3. WHERE 旧数据无法确定映射目标, THE 系统 SHALL 保留原始数据并标注为待人工复核，而非静默丢弃。
4. THE 既有 B22A（含 `B22A-T4-IT-*`、`B22A-frp-` 之前不存在的键除外）与 B22C 持久化数据 SHALL 在重做后正常加载回显。

### Requirement 11: 只读 / 复核态一致性

**User Story:** As a 质量控制复核合伙人, I want 三个组件在只读/已复核态下禁用全部编辑控件, so that 锁定后的底稿不可被误改。

#### Acceptance Criteria

1. WHERE 底稿处于只读或已复核态, THE 三个组件 SHALL 禁用全部输入、下拉、勾选、增删行、导入与带入操作。
2. WHERE 底稿处于修订（amendment）态, THE 编辑控件 SHALL 恢复可用。
3. THE OnlyOffice 视图 SHALL 依据组件只读态传递 readonly 标志。

### Requirement 12: 跨底稿 EventBus 联动契约

**User Story:** As a 开发者, I want B22 的跨底稿事件契约明确且有消费者, so that 不产生"发了没人收"的死联动。

#### Acceptance Criteria

1. THE B22A_Component SHALL 通过 EventBus 发布控制结论变更、控制环境薄弱、拟测试控制清单等事件，且每个事件至少有一个已实现的消费者（B50 / C1 / B23 之一）。
2. WHEN B22C 缺陷严重程度变更, THE 系统 SHALL 使 A9 缺陷函在下次加载时反映最新分组。
3. THE 新增/调整的事件 SHALL 纳入 `crossWpEventBridge` 双向桥（如需 window ↔ eventBus 互通），并附再入守卫。
