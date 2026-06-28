# Requirements — A3-8 商誉减值测试专属组件

## Introduction

A3-8（商誉减值准备测试表）+ A3-8-1（可收回金额测试）是合并报表层面的商誉减值测试底稿，与 I 类单体层商誉底稿（I3-6 减值测试 / I3-7 可收回金额）构成"合并层↔单体层"核对关系。

当前 A3-8/A3-8-1 在 `wp_code_overrides.json` 映射为 `audit-sheet`（静态 OnlyOffice 模板），仅能编辑原始 xlsx，无结构化录入、无公式自动计算、无跨底稿联动。本 spec 新增专属 componentType `a3-8-goodwill-impairment`，实现：
- 资产组商誉减值测试结构化录入 + 减值准备自动计算
- 可收回金额双路径测算（公允价值减处置费用净额 / 预计未来现金流量现值 DCF + WACC）
- 与 I3-2/I3-6/I3-7 的 GtIndexChip 跳转核对
- OnlyOffice 双模式（结构化视图 / Word 在线编辑）

来源模板（已逐 sheet 读取）：`backend/wp_templates/A/A3-7内部往来核对表、A3-8商誉减值测试.xlsx`，sheet `A3-8商誉减值测试`(61×11) 与 `A3-8-1可收回金额测试`(82×15)。

## Requirements

### Requirement 1 — 商誉减值测试主表（资产组维度）

**User Story:** 作为审计助理，我希望按资产组录入账面价值与可收回金额，系统自动计算减值准备，以便快速完成合并层商誉减值测试。

#### Acceptance Criteria
1. WHEN 进入 A3-8 结构化视图 THEN 系统 SHALL 渲染资产组减值测试表，列含：项目名称、对应资产组账面价值(A)、应分配的商誉账面价值(B1)、未确认的归属于少数股东权益的商誉价值(B2)、合计(A+B1+B2)、可收回金额(2)、差额(3)=(1)-(2)、计提的减值准备[(3)>0]、导致资产减值的原因、备注。
2. WHEN 用户录入 A/B1/B2 THEN 系统 SHALL 自动计算 合计=A+B1+B2。
3. WHEN 合计与可收回金额均有值 THEN 系统 SHALL 自动计算 差额=合计-可收回金额。
4. WHEN 差额>0 THEN 系统 SHALL 自动填充 计提的减值准备=差额；WHEN 差额≤0 THEN 减值准备 SHALL 为 0（审计惯例零值显示横杠）。
5. WHEN 存在多个资产组行 THEN 系统 SHALL 提供合计行，对各金额列求和。
6. WHEN 用户增删资产组行 THEN 合计行 SHALL 实时重算。

### Requirement 2 — 减值损失在资产组内的二次分摊

**User Story:** 作为审计助理，我希望减值损失先冲减商誉再按比例分摊到其他资产，符合 CAS 8 资产减值准则。

#### Acceptance Criteria
1. WHEN 资产组确认减值损失 THEN 系统 SHALL 渲染分摊表，行含：流动资产、固定资产、无形资产、……（可增行）、商誉、合计；列含：账面价值、未确认的少数股东权益、调整后的名义账面价值、可收回金额、减值损失、减值损失第一分配、减值损失第二分配。
2. WHEN 分摊减值损失 THEN 系统 SHALL 先全额冲减商誉（第一分配优先冲商誉），剩余减值损失再按其他资产账面价值比例分摊（第二分配）。
3. WHEN 分摊后某资产账面价值将低于其可收回金额 THEN 系统 SHALL 给出提示（不得减记至低于可收回金额，CAS 8 第二十三条）。
4. WHEN 分摊完成 THEN 合计行减值损失 SHALL 等于主表该资产组的减值准备。

### Requirement 3 — 可收回金额测试（A3-8-1，双路径）

**User Story:** 作为审计助理，我希望按"公允价值减处置费用净额"和"未来现金流量现值"两条路径测算可收回金额，取孰高者。

#### Acceptance Criteria
1. WHEN 进入可收回金额测试 THEN 系统 SHALL 提供三个区块：（一）公允价值减处置费用净额、（二）预计未来现金流量的现值、（三）可收回金额结论。
2. WHEN 录入公允价值与处置费用 THEN 系统 SHALL 自动计算 公允价值-处置费用净额，并对多行求合计。
3. WHEN 录入预测期（最多 5 年）现金净流量、增长率、折现率 THEN 系统 SHALL 计算各年折现系数=1/(1+折现率)^n 与现值，并汇总现值合计。
4. WHEN 录入基数现金流与永续增长率 THEN 系统 SHALL 计算终值现值（以后年度）。
5. WHEN 两条路径均有结果 THEN （三）可收回金额 SHALL 自动取两者孰高，并标注采用路径。
6. IF 预测期超过 5 年 THEN 系统 SHALL 给出提示（建立在预算基础上的预计现金流量最多涵盖 5 年，超出需证明合理性）。

### Requirement 4 — WACC 折现率计算器

**User Story:** 作为审计助理，我希望用 WACC 模型推算税前折现率，并校验现金流与折现率口径一致。

#### Acceptance Criteria
1. WHEN 录入 所得税率、债务总额(D)、资本总额(E)、债务成本(Kd)、无风险报酬率(Rf)、β系数、市场平均收益率(Rm) THEN 系统 SHALL 计算 权益成本 Ke=Rf+β×(Rm-Rf)（CAPM）。
2. WHEN D/E/Kd/Ke/税率齐备 THEN 系统 SHALL 计算 税后 WACC = E/(D+E)×Ke + D/(D+E)×Kd×(1-税率)。
3. WHEN 现金流为税前 THEN 系统 SHALL 提示折现率应取税前口径并提供税前折现率换算字段。
4. IF D+E=0 THEN 系统 SHALL 显示横杠而非除零错误。

### Requirement 5 — 与 I 类单体商誉底稿的核对联动

**User Story:** 作为质量控制复核合伙人，我希望从 A3-8 一键跳转到 I3 单体商誉底稿，核对合并层与单体层减值结论是否一致。

#### Acceptance Criteria
1. WHEN 渲染 A3-8 表头 THEN 系统 SHALL 提供 GtIndexChip 指向 I3-2（商誉明细）、I3-6（单体减值测试）、I3-7（单体可收回金额）。
2. WHEN 用户点击 GtIndexChip THEN 系统 SHALL 触发跳转到对应底稿（jump-to-workpaper）。
3. WHEN A3-8 与 I3-6 对同一资产组的减值结论存在矛盾（一方计提一方未计提） THEN 系统 SHALL 在核对区给出非阻断提示（仅展示，不自动改数）。
4. 联动策略遵循项目铁律：只做 GtIndexChip 跳转 + 核对提示，不做 EventBus 数据自动同步。

### Requirement 6 — 双模式与持久化

**User Story:** 作为审计助理，我希望在结构化视图与 Word 在线编辑间切换，数据自动保存不丢失。

#### Acceptance Criteria
1. WHEN 组件加载 THEN 系统 SHALL 默认显示结构化视图，并提供 el-segmented 切换到 OnlyOffice Word 编辑。
2. WHEN 用户修改任意字段 THEN 系统 SHALL 在 2 秒 debounce 后通过 field-overrides 自动保存（scope=`a3_8_goodwill:{wp_id}`）。
3. WHEN 切回结构化视图且 OnlyOffice 曾编辑 THEN 系统 SHALL 重新加载 render-config 获取最新数据。
4. WHEN bundle 内嵌（htmlData 为 null） THEN 组件 SHALL 自行调 `render-config?force_component_type=a3-8-goodwill-impairment` 自加载。
5. WHEN OnlyOffice 健康检查失败 THEN 系统 SHALL 降级并提示，不崩溃。

### Requirement 7 — 编制说明与准则提示

**User Story:** 作为审计助理，我希望查看 CAS 8 资产减值准则要点与商誉减值测试编制说明。

#### Acceptance Criteria
1. WHEN 用户展开"编制说明"折叠区 THEN 系统 SHALL 显示模板内置的减值原因清单（9 项）、资产组认定要点、商誉分摊方法、WACC 各参数定义（来自 A3-8-1 编制说明）。
2. 编制说明为静态只读内容，不参与保存。

### Requirement 8 — 注册契约与渲染策略

#### Acceptance Criteria
1. WHEN 系统启动 THEN `a3-8-goodwill-impairment` SHALL 注册于前端 htmlRendererRegistry、后端 VALID_COMPONENT_TYPES、RENDERER_DISPATCH。
2. WHEN `wp_code_overrides.json` 中 A3-8/A3-8-1 映射更新为 `a3-8-goodwill-impairment` THEN 打开 A3-8 SHALL 渲染专属组件而非 audit-sheet。
3. WHEN 后端渲染策略执行 THEN SHALL 解析 A3-8/A3-8-1 模板结构 + 合并 field_overrides，返回 `{ impairmentData, recoverableData, responses }`。
