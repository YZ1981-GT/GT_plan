# C 类底稿（控制测试）— 需求文档

## 1. 概述

C 类底稿覆盖"控制测试"阶段（审计循环代号 C），是 B 类（了解控制）的后续——B23 穿行测试确认设计有效后，C 类执行实际控制测试验证执行有效性。包含 **5 大功能组、36 个模板文件**。
本 spec 目标：将 C 类底稿全部接入平台渲染/编辑/联动体系，实现 B23→C→D~N 完整的"风险识别→控制测试→实质性程序"审计链条。

## 2. 术语表（Glossary）

- **控制测试系统（Control_Test_System）**：平台中负责 C 类底稿渲染、编辑、联动的子系统
- **循环控制测试底稿（Cycle_Control_Test_WP）**：C2~C15 系列，按审计循环分组的控制测试工作底稿
- **控制偏差评价底稿（Deviation_Eval_WP）**：C2-2~C15-2 系列，评价控制测试中发现的偏差
- **企业层面控制测试底稿（Entity_Level_Control_WP）**：C1，测试企业层面内部控制
- **IT一般控制测试底稿（ITGC_WP）**：C22，测试IT一般控制（安全管理/程序变更/程序开发/网络安全）
- **会计分录测试底稿（JE_Test_WP）**：C23/C24，测试会计分录控制及实施细节测试
- **穿行测试结论（Walkthrough_Conclusion）**：B23 穿行测试写入 field_overrides 的设计有效性结论
- **控制测试结论（Control_Test_Conclusion）**：C 类测试写入 field_overrides 的执行有效性结论
- **样本量（Sample_Size）**：基于控制频率和测试方法确定的测试样本数量
- **控制偏差（Control_Deviation）**：控制测试中发现的控制未按设计执行的情况

## 3. C 类底稿分组结构

| 组 | 编号范围 | 功能 | 文件数 | componentType |
|----|---------|------|--------|---------------|
| G1 | C2~C15 | 循环控制测试（14组） | 14 xlsx | `d-form-table`（C-generic.yaml） |
| G2 | C2-2~C15-2 | 评价控制偏差（14组） | 14 xlsx | `d-form-table`（C-deviation-generic.yaml） |
| G3 | C1 | 企业层面控制测试 | 1 xlsx | `a-program-console` |
| G4 | C21/C21-1/C22/C26 | IT控制测试 | 4 xlsx | C22=`audit-sheet`，其余=`d-form-table` |
| G5 | C23/C24/C25 | 会计分录测试+利用内审 | 3 xlsx | `d-form-table` |


## 4. 各组详细需求

### G1: 循环控制测试 (C2~C15)

**模板文件清单（14 个 xlsx）：**

| wp_code | 文件名 | 对应审计循环 |
|---------|--------|-------------|
| C2 | C2 销售循环控制测试.xlsx | D 销售收入 |
| C3 | C3 货币资金循环业务层面控制测试.xlsx | E 货币资金 |
| C4 | C4 存货循环控制测试.xlsx | F 采购存货 |
| C5 | C5 投资循环控制测试.xlsx | G 投资 |
| C6 | C6 固定资产循环控制测试.xlsx | H 固定资产 |
| C7 | C7 在建工程循环控制测试.xlsx | H 固定资产(在建) |
| C8 | C8 无形资产及其他长期资产循环控制测试.xlsx | I 无形资产 |
| C9 | C9 研发循环控制测试.xlsx | I 无形资产(研发) |
| C10 | C10 职工薪酬循环控制测试.xlsx | J 职工薪酬 |
| C11 | C11 管理循环控制测试.xlsx | K 管理 |
| C12 | C12 税金循环控制测试.xlsx | N 税费 |
| C13 | C13 债务循环业务层面控制测试.xlsx | L 筹资 |
| C14 | C14 租赁循环控制测试.xlsx | L 筹资(租赁) |
| C15 | C15 关联方循环控制测试.xlsx | D~N 关联方 |

**代表性结构（C2 为例，C3~C15 结构相同）：**
- Sheet 1: 底稿目录（C2=汇总表, C2-1=测试过程记录, C2-2=评价偏差）
- Sheet 2: C2 控制测试汇总表（子流程/控制编号/控制名称/控制描述/受影响科目/认定/控制属性/频率/测试方法/样本量/测试结论）
- Sheet 3: C2-1-X 控制测试过程记录（逐控制点测试，含样本选择+测试记录）
- Sheet 4-5: 选项清单列表（不归档，VBA 下拉数据源→平台用 enum 字段替代）

**需求点：**

#### Requirement G1-1: 通用 Schema 渲染

**User Story:** 作为审计项目组成员，我想在平台中编辑循环控制测试底稿，以便结构化记录控制测试过程和结论。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用统一的 `C-generic.yaml` schema 渲染 C2~C15 全部 14 个循环控制测试底稿
2. THE Control_Test_System SHALL 通过 pattern matching `^C(\d{1,2})$`（where 2≤n≤15）匹配 wp_code 到通用 schema
3. WHEN 用户打开任一 C2~C15 底稿时，THE Control_Test_System SHALL 渲染包含以下核心 sheet 的多 Tab 界面：
   - 控制测试汇总表（主 sheet）
   - 控制测试过程记录（逐控制点动态 sheet）
4. THE Control_Test_System SHALL 在控制测试汇总表中包含以下字段列：子流程、控制编号、控制名称、控制描述、受影响科目、认定（存在/完整性/准确性等 enum）、控制属性（预防/检查 enum）、频率（每次/每日/每周/每月/每季/每年 enum）、测试方法（检查/观察/重新执行/询问 enum）、样本量（数字）、测试结论（有效/无效/不适用 enum）
5. THE Control_Test_System SHALL 在控制测试过程记录 sheet 中支持逐控制点展开的测试记录，每个控制点包含：样本编号、样本描述、测试步骤、测试结果（通过/偏差 enum）、偏差说明
6. WHILE 底稿的"选项清单列表"sheet 在 xlsx 原件中存在时，THE Control_Test_System SHALL 使用 enum 字段配置替代 VBA 宏下拉选项（不渲染原始选项 sheet）

#### Requirement G1-2: 样本量自动计算

**User Story:** 作为审计项目组成员，我想根据控制频率和测试方法自动推荐样本量，以便提高测试效率并符合准则要求。

**Acceptance Criteria:**

1. WHEN 用户选定控制频率和测试方法时，THE Control_Test_System SHALL 按照致同审计方法论自动推荐样本量：
   - 每次发生（≥25件→25件测试）
   - 每日（≥250件→25件测试）
   - 每周（52件→5件测试）
   - 每月（12件→2件测试）
   - 每季（4件→1件测试）
   - 每年（1件→1件测试）
2. THE Control_Test_System SHALL 允许用户手动覆盖推荐样本量并记录覆盖原因

#### Requirement G1-3: B23 穿行测试联动

**User Story:** 作为审计项目组成员，我想在控制测试底稿中自动看到穿行测试的设计有效性结论，以便确认该控制点已通过设计测试可以进行执行测试。

**Acceptance Criteria:**

1. WHEN 用户打开 C 类循环控制测试底稿时，THE Control_Test_System SHALL 通过 `auto_data_source: "b23_walkthrough_for_cycle"` 读取对应循环 B23 穿行测试的设计有效性结论
2. WHILE B23 穿行测试结论为"设计有效"时，THE Control_Test_System SHALL 在底稿顶部显示"✓ 穿行测试已确认设计有效"标识
3. WHILE B23 穿行测试结论为"设计无效"时，THE Control_Test_System SHALL 在底稿顶部显示"⚠️ 穿行测试发现设计缺陷，请评估是否继续控制测试"警告
4. IF B23 穿行测试尚未完成（无结论数据），THEN THE Control_Test_System SHALL 在底稿顶部显示"⏳ 穿行测试未完成"提示

#### Requirement G1-4: 控制测试结论输出

**User Story:** 作为审计项目经理，我想把控制测试结论自动传递给 D~N 实质性程序底稿，以便后续程序参考控制测试结果调整审计范围。

**Acceptance Criteria:**

1. WHEN 用户在控制测试汇总表中填写测试结论并保存时，THE Control_Test_System SHALL 将结论写入 `field_overrides` scope=`control_test_result:{cycle}`
2. THE Control_Test_System SHALL 支持 D~N 实质性程序底稿通过 `auto_data_source: "control_test_result_for_cycle"` 读取对应循环的控制测试结论
3. WHEN 控制测试结论为"有效"时，THE Control_Test_System SHALL 写入 `{cycle: "有效", deviation_count: 0, tested_controls: N}`
4. WHEN 控制测试结论存在偏差时，THE Control_Test_System SHALL 写入 `{cycle: "部分有效", deviation_count: X, deviation_refs: ["C{n}-2"]}`


### G2: 评价控制偏差 (C2-2~C15-2)

**模板文件清单（14 个 xlsx）：**

| wp_code | 文件名 | 对应循环 |
|---------|--------|---------|
| C2-2 | C2-2 销售循环评价控制偏差.xlsx | D 销售 |
| C3-2 | C3-2 货币资金循环评价控制偏差.xlsx | E 货币资金 |
| C4-2 | C4-2 存货循环评价控制偏差.xlsx | F 存货 |
| C5-2 | C5-2 投资循环评价控制偏差.xlsx | G 投资 |
| C6-2 | C6-2 固定资产循环评价控制偏差.xlsx | H 固定资产 |
| C7-2 | C7-2 在建工程循环评价控制偏差.xlsx | H 在建工程 |
| C8-2 | C8-2 无形资产及其他长期资产循环评价控制偏差.xlsx | I 无形资产 |
| C9-2 | C9-2 研发循环评价控制偏差.xlsx | I 研发 |
| C10-2 | C10-2 职工薪酬循环评价控制偏差.xlsx | J 薪酬 |
| C11-2 | C11-2 管理循环评价控制偏差.xlsx | K 管理 |
| C12-2 | C12-2 税金循环评价控制偏差.xlsx | N 税费 |
| C13-2 | C13-2 债务循环评价控制偏差.xlsx | L 筹资 |
| C14-2 | C14-2 租赁循环评价控制偏差.xlsx | L 租赁 |
| C15-2 | C15-2 关联方循环评价控制偏差.xlsx | 关联方 |

**代表性结构（C2-2 为例，C3-2~C15-2 结构相同）：**
- Sheet 1: 评价控制偏差（例外描述+评价步骤7项+结论）
- Sheet 2: 示例（不归档，参考用）

**需求点：**

#### Requirement G2-1: 偏差评价通用 Schema

**User Story:** 作为审计项目组成员，我想在发现控制偏差后结构化评价其影响，以便判断是否需要扩大实质性程序范围。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用统一的 `C-deviation-generic.yaml` schema 渲染 C2-2~C15-2 全部 14 个偏差评价底稿
2. THE Control_Test_System SHALL 通过 pattern matching `^C(\d{1,2})-2$`（where 2≤n≤15）匹配 wp_code 到偏差评价通用 schema
3. THE Control_Test_System SHALL 在偏差评价表中包含以下字段：
   - 控制编号（从 C{n} 关联读取）
   - 例外事项描述（textarea）
   - 评价步骤1：该偏差是否属于孤立事件（是/否 enum）
   - 评价步骤2：该偏差的原因是什么（textarea）
   - 评价步骤3：该偏差是否表明控制设计存在缺陷（是/否 enum）
   - 评价步骤4：已执行的补充审计程序（textarea）
   - 评价步骤5：该偏差对拟信赖程度的影响（无影响/降低信赖/不信赖 enum）
   - 评价步骤6：对实质性程序性质时间范围的影响（textarea）
   - 评价步骤7：是否构成控制缺陷需上报（是/否 enum）
   - 结论（有效但存在偏差/无效需扩大测试/无效且已放弃信赖 enum）
4. THE Control_Test_System SHALL 不渲染"示例"sheet（标记为不归档参考资料）

#### Requirement G2-2: 偏差与控制测试关联

**User Story:** 作为审计项目组成员，我想在偏差评价中自动关联控制测试发现的偏差项，以便确保所有偏差都已评价。

**Acceptance Criteria:**

1. WHEN 用户在 C{n} 控制测试过程记录中标记某样本结果为"偏差"时，THE Control_Test_System SHALL 自动在对应的 C{n}-2 偏差评价底稿中创建一条待评价记录
2. THE Control_Test_System SHALL 在 C{n}-2 偏差评价底稿中显示从 C{n} 汇总的偏差总数及各控制点偏差明细
3. WHILE C{n} 存在未评价的偏差记录时，THE Control_Test_System SHALL 在 C{n}-2 底稿状态栏显示"有 X 项偏差待评价"提示

#### Requirement G2-3: 偏差评价结论联动

**User Story:** 作为审计项目经理，我想把偏差评价结论反馈到整体控制测试结论和后续程序中，以便体现完整的风险应对链条。

**Acceptance Criteria:**

1. WHEN 偏差评价结论为"无效需扩大测试"或"无效且已放弃信赖"时，THE Control_Test_System SHALL 将对应循环的 `field_overrides` scope=`control_test_result:{cycle}` 更新为"部分有效"或"无效"
2. WHEN 偏差评价步骤7结论为"是"（构成控制缺陷需上报）时，THE Control_Test_System SHALL 自动在 issue_tickets 创建一条缺陷记录（category='control_deficiency', severity 由结论推断）
3. THE Control_Test_System SHALL 支持从偏差评价底稿通过 ref_index chip 跳转到关联的 C{n} 控制测试底稿对应偏差行


### G3: 企业层面控制测试 (C1)

**模板文件：**
- C1 企业层面控制测试.xlsx — 1 个文件，12 sheet

**Sheet 结构（12 sheet）：**
- Sheet 1: 程序表（136行，序号/程序/是否适用/执行人/测试结果说明/索引号）
- Sheet 2~12: 示例 sheet（C1-1 ~ C1-4-6）— 具体控制点测试记录模板

**需求点：**

#### Requirement G3-1: 程序表渲染

**User Story:** 作为审计项目组成员，我想使用程序表方式编辑企业层面控制测试，以便逐步执行136项测试程序。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `a-program-console` componentType 渲染 C1 底稿的主程序表 sheet
2. THE Control_Test_System SHALL 从 xlsx 模板提取全部 136 行程序步骤，注册到 `procedure_table_templates.json`
3. THE Control_Test_System SHALL 支持程序表的以下字段：序号、程序内容、是否适用（是/否/不适用 enum）、执行人（选择项目组成员）、测试结果说明（textarea）、索引号（ref_index chip，可跳转到对应子底稿）
4. WHEN 程序步骤标记为"不适用"时，THE Control_Test_System SHALL 折叠该步骤并灰显

#### Requirement G3-2: 示例 Sheet 处理策略

**User Story:** 作为审计项目组成员，我想参考示例了解如何填写企业层面控制测试，但示例不应占用归档空间。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 对 C1 的示例 sheet（C1-1 ~ C1-4-6 共 11 个）采取"参考不开发"策略——不在平台中渲染或编辑
2. THE Control_Test_System SHALL 在程序表对应步骤的 ref_index 中保留对示例编号的引用，标注为"参考示例"
3. IF 用户需要查看示例，THEN THE Control_Test_System SHALL 提供原始 xlsx 模板下载功能

#### Requirement G3-3: B22 企业层面控制联动

**User Story:** 作为审计项目经理，我想在 C1 企业层面控制测试中引用 B22 企业层面控制了解的结果，以便确保测试覆盖了已识别的控制。

**Acceptance Criteria:**

1. WHEN 用户打开 C1 底稿时，THE Control_Test_System SHALL 通过 `auto_data_source: "b22_entity_control_list"` 读取 B22A-1~5 + B22B 已识别的企业层面控制清单
2. THE Control_Test_System SHALL 在程序表顶部显示"企业层面控制已识别 X 项，B22 评价完成率 Y%"摘要信息
3. WHEN C1 程序表所有适用步骤均完成时，THE Control_Test_System SHALL 将企业层面控制测试结论写入 `field_overrides` scope=`entity_level_control_test`


### G4: IT 控制测试 (C21/C21-1/C22/C26)

**模板文件：**

| wp_code | 文件名 | 说明 |
|---------|--------|------|
| C21 | C21 具有信息技术专业技能的项目组成员.xlsx | IT专业人员资质及分工 |
| C21-1 | C21-1 IT审计发现汇总表.xlsx | IT审计发现问题汇总 |
| C22 | C22 IT一般控制测试.xlsx | **34 sheet**！含 SA/PE/PM/NS 各步骤 |
| C26 | C26 信息处理控制测试.xlsx | 信息处理（自动化）控制测试 |

**C22 内部结构（34 sheet）：**
- Sheet 1: 主程序表（IT一般控制测试总览：领域/控制目标/测试步骤/结论）
- Sheet 2~34: 具体步骤 sheet（SA-3/SA-4/SA-5/.../PE-3/.../PM-3/.../NS-3/NS-4/.../NS-6.2）
  - 每个步骤 sheet 结构：设计有效性标准审计程序 / 执行的审计程序 / 审计证据 / 结论
  - SA = Security Administration（安全管理）
  - PE = Program Change（程序变更）
  - PM = Program Development（程序开发）
  - NS = Network Security（网络安全/计算机运行）

**需求点：**

#### Requirement G4-1: C22 IT一般控制 OnlyOffice 渲染

**User Story:** 作为 IT 审计人员，我想用类 Excel 方式编辑 IT 一般控制测试底稿，因为 34 个 sheet 结构复杂且 IT 审计人员习惯 Excel 操作。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `audit-sheet` componentType 渲染 C22 底稿（OnlyOffice/Univer）
2. THE Control_Test_System SHALL 保留 C22 全部 34 个 sheet 的原始 Tab 结构
3. THE Control_Test_System SHALL 在 `address_registry` 中注册 C22 的关键单元格坐标，至少包括：
   - 主程序表的结论列（每个 SA/PE/PM/NS 领域的汇总结论）
   - 每个步骤 sheet 的"结论"单元格
4. THE Control_Test_System SHALL 支持通过 `custom_query` 查询 C22 中各领域的测试结论

#### Requirement G4-2: C21 IT 人员资质

**User Story:** 作为审计项目经理，我想记录具有IT专业技能的项目组成员信息，以便证明 IT 审计由胜任人员执行。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `d-form-table` componentType 渲染 C21 底稿
2. THE Control_Test_System SHALL 在 C21 中包含以下字段：姓名（从项目组成员列表选择）、专业资质/认证、负责领域（SA/PE/PM/NS 多选 enum）、参与起止时间、工作说明
3. WHEN 项目组成员列表变更时，THE Control_Test_System SHALL 自动更新 C21 的可选人员清单

#### Requirement G4-3: C21-1 IT 审计发现汇总

**User Story:** 作为 IT 审计人员，我想汇总所有 IT 审计发现，以便统一管理和跟踪 IT 控制缺陷。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `d-form-table` componentType 渲染 C21-1 底稿
2. THE Control_Test_System SHALL 在 C21-1 中包含以下字段：发现编号（自动递增）、来源底稿（C22/C26 ref_index chip）、控制领域（SA/PE/PM/NS enum）、发现描述（textarea）、风险等级（高/中/低 enum）、管理层回复（textarea）、整改状态（已整改/整改中/未整改 enum）
3. WHEN C22 步骤 sheet 结论为"无效"时，THE Control_Test_System SHALL 自动在 C21-1 创建一条待填写的发现记录
4. THE Control_Test_System SHALL 支持从 C21-1 的来源底稿列通过 ref_index chip 跳转到 C22 对应步骤 sheet

#### Requirement G4-4: C26 信息处理控制测试

**User Story:** 作为审计项目组成员，我想测试信息处理（自动化）控制，以便评估系统自动控制的有效性。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `d-form-table` componentType 渲染 C26 底稿
2. THE Control_Test_System SHALL 在 C26 中包含以下字段：应用系统名称、控制编号、控制描述、控制类型（自动/手动+IT enum）、依赖的IT一般控制（C22 ref_index chip）、测试方法、测试结果、结论（有效/无效 enum）
3. WHEN C22 IT一般控制对应领域结论为"无效"时，THE Control_Test_System SHALL 在 C26 对应依赖行显示"⚠️ 底层 ITGC 无效，需评估对应用控制的影响"警告

#### Requirement G4-5: IT 控制测试结论汇总

**User Story:** 作为审计项目经理，我想看到 IT 控制测试的整体结论，以便判断对财务报表审计的影响。

**Acceptance Criteria:**

1. WHEN C22 全部领域测试完成时，THE Control_Test_System SHALL 将 IT 一般控制测试汇总结论写入 `field_overrides` scope=`itgc_test_result`
2. THE Control_Test_System SHALL 汇总格式为：`{sa: "有效/无效", pe: "有效/无效", pm: "有效/无效", ns: "有效/无效", overall: "有效/部分有效/无效", finding_count: X}`
3. THE Control_Test_System SHALL 支持 D~N 实质性程序底稿通过 `auto_data_source: "itgc_test_result"` 读取 IT 控制测试结论


### G5: 会计分录测试 + 利用内审 (C23/C24/C25)

**模板文件：**

| wp_code | 文件名 | 说明 |
|---------|--------|------|
| C23 | C23 会计分录 - 控制测试.xlsx | 程序表+人员清单测试+分录控制测试 |
| C24 | C24 会计分录 - 细节测试.xlsx | 分录筛选+细节测试记录 |
| C25 | C25 利用内审工作.xlsx | 评价内审工作可利用程度 |

**C23 内部结构：**
- Sheet 1: 会计分录控制测试程序表
- Sheet 2: 有权录入人员清单测试（人员列表+权限验证）
- Sheet 3: 分录控制测试记录（逐步骤测试）

**C24 内部结构：**
- Sheet 1: 分录筛选标准及结果
- Sheet 2: 会计分录细节测试记录（样本抽取+逐笔检查）

**需求点：**

#### Requirement G5-1: C23 会计分录控制测试

**User Story:** 作为审计项目组成员，我想测试会计分录录入和审批的控制，以便评估管理层凌驾风险的控制应对措施。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `d-form-table` componentType 渲染 C23 底稿，包含 3 个 sheet Tab
2. THE Control_Test_System SHALL 在"程序表" sheet 包含以下字段：程序步骤、执行人、执行日期、结果说明、索引号
3. THE Control_Test_System SHALL 在"有权录入人员清单测试" sheet 包含以下字段：姓名、职务、录入权限范围、审批权限、是否存在职责分离（是/否 enum）、测试结论
4. THE Control_Test_System SHALL 在"分录控制测试记录" sheet 包含以下字段：测试步骤编号、控制描述、测试方法、样本描述、测试结果（通过/偏差 enum）、偏差说明
5. WHEN C23 测试发现分录控制偏差时，THE Control_Test_System SHALL 联动 C24 扩大细节测试范围的建议

#### Requirement G5-2: C24 会计分录细节测试

**User Story:** 作为审计项目组成员，我想对筛选出的异常分录执行细节测试，以便识别管理层通过会计分录凌驾控制的风险。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `d-form-table` componentType 渲染 C24 底稿，包含 2 个 sheet Tab
2. THE Control_Test_System SHALL 在"分录筛选标准及结果" sheet 包含以下字段：筛选标准编号、筛选条件描述、筛选结果数量、抽样数量、抽样方法
3. THE Control_Test_System SHALL 在"细节测试记录" sheet 包含以下字段：样本编号、凭证号、凭证日期、摘要、借方金额、贷方金额、录入人、审批人、异常特征、检查结果（正常/异常 enum）、异常说明
4. THE Control_Test_System SHALL 支持从平台已导入的序时账（`tb_ledger`）中按筛选条件自动提取候选分录
5. WHEN 用户选择"从序时账筛选"时，THE Control_Test_System SHALL 调用 `auto_data_source: "je_filter_from_ledger"` 按条件（金额阈值/非工作时间/非常规科目/整数金额等）提取分录

#### Requirement G5-3: C24 与抽凭联动

**User Story:** 作为审计项目组成员，我想将细节测试中检查的分录标记为已抽中，以便与抽凭底稿联动。

**Acceptance Criteria:**

1. WHEN 用户在 C24 细节测试中检查某条分录时，THE Control_Test_System SHALL 支持一键将该分录添加到 `sampled_vouchers` 表（关联 C24 的 working_paper_id）
2. THE Control_Test_System SHALL 在 C24 细节测试记录中显示哪些分录已被抽中（来源=C24）
3. THE Control_Test_System SHALL 将 C24 测试结论写入 `field_overrides` scope=`je_detail_test_result`

#### Requirement G5-4: C25 利用内审工作

**User Story:** 作为审计项目经理，我想评价内部审计工作的可利用程度，以便决定是否减少外部审计程序。

**Acceptance Criteria:**

1. THE Control_Test_System SHALL 使用 `d-form-table` componentType 渲染 C25 底稿
2. THE Control_Test_System SHALL 在 C25 中包含以下字段：
   - 评价维度（客观性/胜任能力/系统性方法/职业谨慎 enum）
   - 评价内容描述（textarea）
   - 评价结论（可利用/部分可利用/不可利用 enum）
   - 利用范围说明（textarea）
   - 对利用内审工作拟实施的审计程序（textarea）
3. WHEN C25 评价结论为"可利用"或"部分可利用"时，THE Control_Test_System SHALL 将结论写入 `field_overrides` scope=`internal_audit_reliance`
4. THE Control_Test_System SHALL 联动 B18（了解内部审计程序表）的评价结果作为 C25 的参考输入


## 5. 跨模块联动矩阵

| 源底稿 | 目标 | 联动数据 | 方向 |
|--------|------|---------|------|
| B23-1~14 穿行测试结论 | C2~C15 控制测试 | 设计有效性结论 | B→C（读取） |
| B22A-1~5 企业层面控制 | C1 企业层面控制测试 | 已识别控制清单 | B→C（读取） |
| B18 了解内审 | C25 利用内审 | 内审评价结果 | B→C（读取） |
| C2~C15 测试结论 | D~N 实质性程序 | 控制测试结论+偏差数 | C→D~N（写入） |
| C2~C15 偏差发现 | C2-2~C15-2 偏差评价 | 偏差明细自动创建 | C→C（内部联动） |
| C2-2~C15-2 偏差结论 | C2~C15 汇总结论 | 更新测试结论 | C→C（内部联动） |
| C2-2~C15-2 缺陷上报 | issue_tickets | 控制缺陷记录 | C→全局 |
| C22 ITGC 结论 | C26 信息处理控制 | 底层 ITGC 状态 | C→C（内部联动） |
| C22 ITGC 结论 | D~N 实质性程序 | ITGC 有效性 | C→D~N（写入） |
| C22 步骤无效 | C21-1 发现汇总 | 自动创建发现 | C→C（内部联动） |
| C23 控制偏差 | C24 细节测试 | 扩大测试建议 | C→C（内部联动） |
| C24 细节测试 | sampled_vouchers | 抽凭记录 | C→全局 |
| C24 结论 | A17-1 ch6 舞弊 | 管理层凌驾评价 | C→A（写入） |
| C1 企业层面结论 | A17-1 ch4 需关注事项 | 企业层面控制缺陷 | C→A（写入） |
| tb_ledger 序时账 | C24 分录筛选 | 按条件提取候选 | 全局→C（读取） |

## 6. 技术约束

### 6.1 wp_code 注册规则

1. C 类底稿 wp_code 以 `C` 开头，覆盖 C1~C26（不连续编号）
2. 全部 36 个文件的 wp_code 需一次性注册到 `wp_account_mapping.json`
3. 虚拟子码规则：
   - C{n}（2≤n≤15）：循环控制测试主体
   - C{n}-2（2≤n≤15）：对应偏差评价
   - C{n}-1-X：控制测试过程记录（动态子码，schema 内 sheet 而非独立 wp_code）
   - C1-1~C1-4-6：企业层面示例（参考不开发，不注册独立 wp_code）
   - C22 内部 SA/PE/PM/NS 步骤：OnlyOffice 内部 sheet（不注册独立 wp_code，但需注册 address_registry 坐标）

### 6.2 componentType 映射

在 `_WP_CODE_OVERRIDE` 中添加完整 C 类映射：

| wp_code | componentType | 说明 |
|---------|---------------|------|
| C1 | `a-program-console` | 企业层面控制测试程序表 |
| C2~C15 | `d-form-table` | 循环控制测试（generic schema） |
| C2-2~C15-2 | `d-form-table` | 偏差评价（deviation generic schema） |
| C21 | `d-form-table` | IT专业人员 |
| C21-1 | `d-form-table` | IT发现汇总 |
| C22 | `audit-sheet` | IT一般控制（34 sheet，OnlyOffice） |
| C23 | `d-form-table` | 会计分录控制测试 |
| C24 | `d-form-table` | 会计分录细节测试 |
| C25 | `d-form-table` | 利用内审 |
| C26 | `d-form-table` | 信息处理控制测试 |

### 6.3 通用 Schema 复用

1. **C-generic.yaml**：C2~C15 共用，仅 `cycle_name` 参数化（参照 B23-generic.yaml 模式）
2. **C-deviation-generic.yaml**：C2-2~C15-2 共用，仅 `cycle_name` 参数化
3. pattern matching 在 `wp_render_schema_service.load_schema` 中实现（已有 B23 先例）

### 6.4 xlsm/VBA 处理

1. C 类模板中"选项清单列表"sheet（VBA 宏数据源）不渲染，用 schema 内 enum 字段替代
2. 平台不执行 VBA 宏代码，仅提取工作表结构
3. C22 的 34 sheet 保持原始 Tab 结构进入 OnlyOffice

### 6.5 address_registry 坐标注册

C22 IT一般控制测试（34 sheet）走 OnlyOffice 但必须注册地址坐标：
- 主程序表结论列坐标
- 每个步骤 sheet 的"结论"单元格坐标
- SA/PE/PM/NS 领域汇总结论坐标

### 6.6 导入导出

1. C2~C15 + C2-2~C15-2：支持导出为 Excel（d-form-table 通用导出）
2. C1：程序表标准导出
3. C22：OnlyOffice 原生导出（audit-sheet 通用）
4. C23/C24/C25/C26：d-form-table 通用导出
5. 支持从 Excel 导入填充已有结构化底稿（覆盖现有数据）
6. 批量导出：项目归档时 C 类全量打包 zip

## 7. 分期实施建议

| Phase | 范围 | 优先级 | 依赖 |
|-------|------|--------|------|
| P0 | 注册+分类：全部 36 个 wp_code 注册 wp_account_mapping + _WP_CODE_OVERRIDE 映射 | 必做 | 无 |
| P1 | 循环控制测试：C-generic.yaml + C-deviation-generic.yaml + pattern matching + 渲染 | 必做 | P0 |
| P2 | 企业层面：C1 程序表模板提取(136步) + 注册 procedure_table_templates | 必做 | P0 |
| P3 | IT 控制：C22 audit-sheet + address_registry 坐标 + C21/C21-1/C26 d-form schema | 必做 | P0 |
| P4 | 会计分录：C23/C24 d-form schema + C24 序时账筛选 auto_data_source + C25 | 必做 | P0 |
| P5 | 联动：B23→C 读取 + C→D~N 写入 + C偏差→issue_tickets + C24→sampled_vouchers | 增强 | P1+P4 |
| P6 | 导入导出 + 冒烟测试 + E2E | 必做 | P1~P4 |

## 8. B 类经验教训应用（防止重复踩坑）

| # | B类踩坑 | C类应对措施 |
|---|---------|------------|
| 1 | wp_code 注册不完整，后期补注册导致联动断裂 | P0 阶段一次性注册全部 36 个 wp_code + 所有 componentType 映射 |
| 2 | B23 generic schema 模式匹配仅 B23 先例 | C 类直接复用相同模式，新增 `^C(\d{1,2})$` 和 `^C(\d{1,2})-2$` 两个 pattern |
| 3 | xlsm VBA 选项清单 sheet 未处理导致前端渲染空白 | 从第一天起用 enum 字段替代，不渲染选项 sheet |
| 4 | B23-1~14 结构重复导致重复工作 | C-generic.yaml + C-deviation-generic.yaml 两套通用 schema 覆盖 28 个底稿 |
| 5 | B→C 联动写入端 handler 遗漏 | P5 明确设计 `_on_c_control_test_saved` handler 写入 field_overrides |
| 6 | 导入导出未同步规划 | P6 独立 Phase 专门处理，每个 componentType 同步规划 |
| 7 | OnlyOffice 底稿地址坐标未落位 | P3 阶段 C22 强制要求 address_registry 注册（34 sheet 结论坐标） |

