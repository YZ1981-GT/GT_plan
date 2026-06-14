# Requirements: 报表模块完善（TB完整视图/比率分析/趋势分析/期初核对）

## Introduction

参照 A2-1/A2-2 单体报表试算底稿（22 sheet），当前报表模块缺失：TB 完整视图（含调整分列）、财务比率分析、未审/已审趋势分析增强、期初核对。需要补充这些功能使报表模块覆盖 A2 底稿的全部核查需求。

## Requirements

### Requirement 1: TB 完整视图（含调整中间列）

**User Story:** 作为审计人员，我需要在试算平衡表中看到完整的调整过程（企业原报数→账项调整→报表调整→其他调整→审定数），而不是只看到头尾两列。

#### Acceptance Criteria
1. THE 试算表视图 SHALL 增加中间列：账项调整(AJE)借方/贷方、报表调整(RJE)借方/贷方、其他调整借方/贷方
2. EACH 调整列 SHALL 从 adjustments 表按类型(AJE/RJE/其他)分别汇总到科目
3. THE 验证公式 SHALL 成立：审定数 = 原报数 + AJE净额 + RJE净额 + 其他净额
4. IF 公式不平，THE 系统 SHALL 高亮差异行并提示
5. THE 用户 SHALL 可以选择"简洁视图"（只看原报+审定）和"完整视图"（含全部调整列）切换

### Requirement 2: 期初核对

**User Story:** 作为审计人员，我需要验证本年期初数 = 上年审定数，差异需要说明原因。

#### Acceptance Criteria
1. THE 系统 SHALL 自动对比：本年 trial_balance.opening_balance vs 上年 trial_balance.audited_amount
2. IF 差异≠0 的科目，THE 系统 SHALL 列出差异清单（科目/本年期初/上年审定/差额）
3. THE 用户 SHALL 可对差异项填写原因说明（如会计政策变更追溯调整）
4. THE 期初核对完成状态 SHALL 联动 A1 程序表

### Requirement 3: 未审/已审资产负债表趋势分析（BS 分析）

**User Story:** 作为审计人员，我需要对资产负债表进行横向（变动额/变动%）和纵向（比重差异）趋势分析。

#### Acceptance Criteria
1. THE BS 分析 SHALL 展示：上年已审数+比重% | 本年数+比重% | 变动额 | 变动% | 比重变动
2. THE 系统 SHALL 自动标记"显著变动"（变动%超过阈值，默认20%）和"关注"（比重变动超阈值）
3. THE 用户 SHALL 可对显著变动项填写原因分析
4. THE 分析 SHALL 支持"未审报表"和"已审报表"两个版本（未审分析在审计前、已审分析在审计后）
5. THE MultiYearCompare 组件 SHALL 增强以满足上述需求（而非新建组件）

### Requirement 4: 未审/已审利润表趋势分析（PL 分析）

**User Story:** 同 BS 分析，对利润表各行做横向纵向分析。

#### Acceptance Criteria
1. THE PL 分析 SHALL 展示与 BS 分析相同的列结构
2. THE 系统 SHALL 额外计算毛利率变动（营业收入-营业成本/营业收入）
3. THE 显著变动标记规则 SHALL 与 BS 一致

### Requirement 5: 财务比率分析

**User Story:** 作为审计人员，我需要系统自动计算关键财务比率，并与上年对比（注：行业对比因无本地行业数据库暂不实现）。

#### Acceptance Criteria
1. THE 系统 SHALL 自动计算以下比率：流动比率、速动比率、资产负债率、应收周转率、存货周转率、毛利率、净利率、ROE、ROA
2. EACH 比率 SHALL 显示：本年值 | 上年值 | 变动 | 变动方向（仅同比，不做行业对比）
3. THE 系统 SHALL 标记异常比率（如流动比率<1、资产负债率>70%等）
4. THE 用户 SHALL 可对异常比率填写分析说明
5. THE 比率分析 SHALL 支持未审/已审两版

### Requirement 6: 分析结果与程序表联动

#### Acceptance Criteria
1. A1 第9项（分析性复核）SHALL 自动链接到 BS/PL/比率分析结果
2. THE 分析中标记为"显著"且无原因说明的项 SHALL 在 A1 中提示"待完成"
3. ALL 分析结果 SHALL 支持导出为 Excel（按 A2-1 模板格式）
