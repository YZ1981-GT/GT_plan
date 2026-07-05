# Requirements Document

> C23/C24 会计分录测试专属组件（C23 控制测试 + C24 细节测试）

## Introduction

会计分录测试是应对管理层凌驾于控制之上（舞弊）风险的核心程序（CAS 1141），本 spec 覆盖两个底稿，各开发为专属组件（对齐 D4 标准）：

- **C23 会计分录-控制测试**（5 sheets）：C23A 程序表 + C23-1 会计人员清单完整性测试 + C23-2 会计分录控制测试（抽取 25 笔日记账样本，核对编制人/过账人/审核人与授权清单，判断偏差）+ 2 个示例
- **C24 会计分录-细节测试**（11 sheets）：C24A + C24-0 汇总表（审计目标 + 数据来源 + 测试工具 IDEA/IAS + 测试项目索引）+ C24-1 完整性借贷方发生额 + C24-2 完整性分录余额表对比 + C24-3 跳号测试 + C24-4 异常账户测试 + C24-5 异常分录测试（假期/夜间/频繁调整/大额/约整数/刚好低于审批限额）+ 参考-本福特定律测试（406 公式 + 虚拟分录 10541 行 21079 公式）

C24 是数据分析密集型底稿（借贷平衡、跳号识别、本福特首位数分布），需要专属计算引擎。当前以通用渲染无法支撑，本需求将两者升级为专属组件。

## Glossary

- **C23_Component**：会计分录控制测试组件，componentType `c23-journal-entry-control`
- **C24_Component**：会计分录细节测试组件，componentType `c24-journal-entry-detail`
- **人员清单完整性**：C23 核对样本分录的编制/过账/审核人是否在授权清单内
- **借贷发生额完整性**：C24-1 全部分录借方发生额合计 = 贷方发生额合计
- **分录余额对比**：C24-2 分录按科目汇总与试算平衡表对比
- **跳号测试**：C24-3 识别凭证号缺号区间，判断是否异常跳号
- **异常分录测试**：C24-5 按规则（假期/夜间/频繁调整/大额/约整数/临界审批限额）筛异常分录
- **本福特定律**：C24 参考 sheet，检验分录金额首位数分布是否符合 Benford 分布以识别舞弊迹象
- **componentType**：本 spec 新增 2 个 —— `c23-journal-entry-control` / `c24-journal-entry-detail`
- **useC24AnalyticsEngine**：C24 纯函数分析引擎（借贷平衡/跳号/本福特/异常筛选）
- **GtIndexChip**：跨底稿引用跳转 chip（prop 名 `value`）
- **导入导出三级**：导出模板 / 导出数据 / 导入数据

## Requirements

### Requirement 1: 组件注册

**User Story:** 作为开发者，我希望 C23/C24 打开时渲染各自专属组件。

#### Acceptance Criteria

1. THE 系统 SHALL 在 htmlRendererRegistry 注册 `c23-journal-entry-control` 与 `c24-journal-entry-detail`（defineAsyncComponent, contextProps standard）
2. THE wp_code_overrides SHALL 将 C23→`c23-journal-entry-control`、C24→`c24-journal-entry-detail`
3. THE 系统 SHALL 在 VALID_COMPONENT_TYPES 注册两类，后端 validate_overrides 校验通过
4. THE 两组件 SHALL 具备后端 RENDERER_DISPATCH 注册
5. THE 两组件 SHALL 接收 sheetName prop 以 v-if 分发内部各 sheet（不含内部 el-tabs）

### Requirement 2: C23 会计人员清单完整性测试

**User Story:** 作为审计助理，我希望 C23-1 维护授权人员清单，C23-2 抽样核对分录人员是否授权。

#### Acceptance Criteria

1. THE C23_Component SHALL 以 sheetName v-if 分发 C23A 程序表 + C23-1 人员清单 + C23-2 控制测试 + 示例
2. THE C23-1 SHALL 维护授权人员清单（姓名/权限：创建/授权/记录）
3. THE C23-2 SHALL 支持录入 25 笔日记账样本（编制人/过账人/审核人 + 支持性文件 + 批准过程）
4. THE C23_Component SHALL 自动核对每笔样本的编制/过账/审核人是否在 C23-1 授权清单内，标记偏差
5. THE C23_Component SHALL 统计偏差数并给出人员清单完整性结论

### Requirement 3: C24 完整性测试（借贷发生额 + 分录余额对比 + 跳号）

**User Story:** 作为审计助理，我希望 C24 自动完成分录完整性测试。

#### Acceptance Criteria

1. THE useC24AnalyticsEngine SHALL 计算全部分录借方发生额合计与贷方发生额合计，并判断是否相等（完整性）
2. THE useC24AnalyticsEngine SHALL 将分录按科目编码汇总并与试算平衡表对比，标记差异科目（C24-2，保留 47 公式语义）
3. THE useC24AnalyticsEngine SHALL 对凭证号执行跳号测试，识别缺号区间并标记是否异常跳号（C24-3）
4. WHEN 分录数据变更时，THE 完整性/对比/跳号结果 SHALL 实时重算，公式单元格不可手工覆盖

### Requirement 4: C24 异常分录与账户测试

**User Story:** 作为审计助理，我希望 C24 按规则自动筛选异常分录与异常账户。

#### Acceptance Criteria

1. THE useC24AnalyticsEngine SHALL 按规则筛选异常分录（C24-5）：假期录入/夜间录入/频繁调整/大额超正常范围/金额约整数/刚好低于审批限额
2. THE useC24AnalyticsEngine SHALL 筛选异常账户（C24-4）：未授权职员录入等
3. THE C24_Component SHALL 对每条筛出的异常分录提供异常事项说明、核查内容、结论列
4. THE 异常筛选规则 SHALL 参数可配置（如审批限额阈值、大额阈值、假期清单）

### Requirement 5: C24 本福特定律分析

**User Story:** 作为审计助理，我希望 C24 对分录金额执行本福特定律首位数分布分析，识别舞弊迹象。

#### Acceptance Criteria

1. THE useC24AnalyticsEngine SHALL 计算分录金额首位数（1-9）实际分布频率
2. THE useC24AnalyticsEngine SHALL 与本福特理论分布（log10(1+1/d)）对比并计算偏离度
3. THE C24_Component SHALL 以图表呈现实际 vs 理论分布，高亮显著偏离的首位数
4. THE 本福特分析 SHALL 支持排除特定科目/金额范围后重新计算

### Requirement 6: C24-0 汇总与数据来源

**User Story:** 作为审计助理，我希望 C24-0 汇总测试基本信息与各测试项结论。

#### Acceptance Criteria

1. THE C24_Component SHALL 在 C24-0 汇总测试数据来源（导出应用/版本/时间/索引）与测试工具（IDEA/IAS 名称/版本）
2. THE C24-0 SHALL 汇总各测试项（C24-1~C24-5）的索引号与结论
3. WHEN 某测试项结论变更时，THE C24-0 汇总 SHALL 实时刷新

### Requirement 7: 导入导出

**User Story:** 作为审计助理，我希望导入被审计单位的分录数据执行测试，导出测试结果。

#### Acceptance Criteria

1. THE C24_Component SHALL 提供 el-dropdown「导入导出▾」（导出模板/导出数据/导入数据）
2. THE 导入 SHALL 支持导入分录明细（凭证号/日期/科目/借方/贷方/摘要/制单人等），作为完整性/跳号/异常/本福特分析的输入
3. THE 导入导出 SHALL 复用 useXImportExport composable + 后端三端点，使用 http(axios)，中文文件名 RFC5987
4. IF 导入数据格式错误，THEN THE C24_Component SHALL 提示错误行且不写入

### Requirement 8: 跨底稿引用、持久化与只读

**User Story:** 作为审计助理，我希望测试数据持久化、引用可跳转；作为复核合伙人，只读模式不可编辑。

#### Acceptance Criteria

1. THE 两组件 SHALL 将数据存储到 checklist_responses，使用 item_id 前缀 `C23-`/`C24-`
2. WHERE 索引列含其他底稿编码（如 B22A-4-3），THE 组件 SHALL 以 GtIndexChip 呈现（prop `value`）并可跳转
3. WHEN readonly 为 true 时，THE 组件 SHALL 禁止所有编辑与明细行增删，仅浏览与跳转
4. THE 表格 SHALL 使用 13px 字体；公式列虚线下划线 + tooltip 来源；金额默认「元」经 fmt 出口
5. WHEN 保存失败时，THE 组件 SHALL 提示错误并保留本地编辑内容

### Requirement 9: 点选交互与操作提示

**User Story:** 作为审计助理，我希望分录测试尽量点选完成，异常规则可勾选配置，并有操作提示。

#### Acceptance Criteria

1. THE C23_Component 与 C24_Component SHALL 将判断/枚举字段（是否偏差、测试结论、异常事项类型）实现为下拉/单选/多选点选控件
2. THE C24_Component SHALL 将异常分录筛选规则（假期/夜间/频繁调整/大额/约整数/临界审批限额）实现为可勾选启用的多选清单，并对阈值型规则提供数字输入
3. WHERE 字段为长文本（异常说明、核查内容、结论），THE 组件 SHALL 使用 autosize textarea + AI 辅助按钮
4. THE 两组件 SHALL 在顶部提供操作引导区（导入分录 → 完整性测试 → 异常/本福特 → 汇总结论）与方法论上下文
5. THE 两组件 SHALL 为分析结果列提供 tooltip 说明计算口径

### Requirement 10: 附件上传、OCR 与分录导入

**User Story:** 作为审计助理，我希望上传凭证附件 OCR 自动填样本，并导入被审单位分录数据跑测试。

#### Acceptance Criteria

1. THE C23_Component SHALL 在 C23-2 样本明细行提供 📎 附件上传，上传凭证图片/PDF 时调用 OCR 识别编制人/过账人/审核人/日期并经确认弹窗 merge 填入
2. THE C24_Component SHALL 在异常分录核查行提供 📎 附件上传（核查证据），并支持 OCR 识别辅助填充
3. THE C24_Component SHALL 支持导入被审计单位分录明细（凭证号/日期/科目/借方/贷方/摘要/制单人）作为分析输入
4. IF OCR 或导入失败，THEN THE 组件 SHALL 提示错误行/失败原因并保留已上传内容，不写入脏数据
5. THE 附件 SHALL 与对应 item_id 关联持久化，只读模式仅可查看

### Requirement 11: 异常回写与联动

**User Story:** 作为现场经理，我希望分录测试识别的异常/舞弊迹象能联动到错报汇总与相关循环。

#### Acceptance Criteria

1. WHERE C24 识别出需进一步核查的异常分录且确认为错报，THE C24_Component SHALL 提供 GtIndexChip 一键跳转 A13 错报汇总/相关循环底稿并带入分录摘要
2. WHEN C23/C24 测试结论变更时，THE 组件 SHALL 将结论回填 C24-0 汇总表对应测试项
3. THE 组件 SHALL 在本福特显著偏离或异常分录聚集时给出「建议扩大核查范围」提示
4. THE 回写 SHALL 保留来源测试项索引，支持双向追溯
