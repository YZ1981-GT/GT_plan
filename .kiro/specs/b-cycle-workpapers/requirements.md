# B 类底稿（承接与计划）— 需求文档

## 1. 概述

B 类底稿覆盖"承接与计划"阶段（审计循环代号 B），包含 **7 大功能组、约 115 个模板文件**。
本 spec 目标：将 B 类底稿全部接入平台渲染/编辑/联动体系，实现与 A/D~N 类同等的结构化支持。

## 2. B 类底稿分组结构

| 组 | 编号范围 | 功能 | 文件数 | componentType 建议 |
|----|---------|------|--------|-------------------|
| G1 | B1/B1A/B1B | 业务承接与保持 | 9 xlsx+docx | a-program-console + word-template |
| G2 | B2 | 与前任注册会计师沟通 | 9 xlsx+docx | a-program-console + word-template |
| G3 | B3/B5 | 独立性确认 + 业务约定书 | 15 xlsx+docx | checklist-table + word-template |
| G4 | B10~B19 | 了解被审计单位及环境 | 7 xlsx | a-program-console / d-form-table |
| G5 | B22~B23 | 企业层面控制 + 业务层面控制(穿行测试) | 33 xlsx/xlsm+docx | control-matrix + d-form-table |
| G6 | B30 | 集团审计 | 19 xlsx/xlsm+docx | a-program-console + word-template |
| G7 | B40~B60 | 项目组讨论 + 风险评估汇总 + 审计策略 | 23 xlsx+docx | risk-matrix + word-template |

## 3. 各组详细需求

### G1: 业务承接与保持 (B1/B1A/B1B)

**模板文件：**
- B1-1 风险评估表（适用于承接）.xlsx — 多 sheet 评估矩阵
- B1-2 风险评估表（适用于保持）.xlsx — 同结构，保持场景
- B1-3 业务评价表.docx — Word 文档（富文本）
- B1-4 业务承接阶段尽职调查报告.docx — 标准版/简化版
- B1-5 KAA检查程序表.xlsx — 核对表式
- B1-7 质量控制委员会会议记录.docx — Word 文档
- B1A 业务承接程序表（适用于首次承接）.xlsx — 程序表 + 结论
- B1B 业务保持程序表.xlsx — 程序表 + 结论

**需求：**
1. B1A/B1B 作为程序表，使用 `a-program-console` 渲染（同 A1 模式）
2. B1-1/B1-2 作为风险评估矩阵，使用 `d-form-table` 渲染（评分+结论）
3. B1-3/B1-4/B1-7 docx 文件使用 `word-template` 渲染（OnlyOffice/降级）
4. B1-5 KAA检查表使用 `checklist-table` 渲染
5. B1A seq1 结论 = "是否承接"→联动项目状态（accepted/rejected）
6. B1-1/B1-2 的风险评分（低/中/高）→联动 B50 风险汇总

### G2: 与前任注册会计师沟通 (B2)

**模板文件：**
- B2 与前任注册会计师的沟通程序表.xlsx — 程序表
- B2-1/B2-3/B2-6/B2-8/B2-11 沟通函副本.docx — Word 函件
- B2-5 与前任注册会计师沟通后的评价.xlsx — 评价表
- B2-12 对前任注册会计师的评价底稿.docx — Word 文档

**需求：**
1. B2 程序表使用 `a-program-console` 渲染
2. B2-5 评价表使用 `d-form-table` 渲染（结论字段+关联 ref_index 跳转）
3. 所有 docx 使用 `word-template`
4. B2 程序完成后联动 B1A/B1B 的"前任沟通"步骤自动标完成

### G3: 独立性确认 + 业务约定书 (B3/B5)

**模板文件：**
- B3 独立性确认程序表.xlsx — 核对表式程序表
- B3-1 独立性声明书.docx — 团队成员签署
- B5 业务约定书控制表.docx — 控制表
- B5-1~B5-9 各类业务约定书.docx — 9 种约定书模板

**需求：**
1. B3 使用 `checklist-table`（独立性确认=逐项勾选+签字）
2. B3-1 使用 `word-template`（需预填项目组成员名单）
3. B5 控制表使用 `word-template`
4. B5-x 约定书按 `business_category` 自动推荐适用版本
5. B3 完成→联动 A17-7 独立性声明书签署状态

### G4: 了解被审计单位及环境 (B10~B19)

**模板文件：**
- B10 了解被审计单位及其环境.xlsx — 大型多 sheet(行业/经营/治理/会计政策等)
- B11 检查相关信息或文件记录程序表.xlsx
- B12 与相关人员访谈程序及记录.xlsx
- B13 初步分析程序表.xlsx
- B13-2~5 未审报表初步分析.xlsx — 从 trial_balance 取数
- B15 重要性计算表.xlsx — 公式计算（已有独立 Materiality 模块）
- B18 了解内部审计程序表.xlsx
- B18-3-1/B18-3-2 利用内部审计人员书面协议.docx
- B19 识别关联方程序表.xlsx — 联动关联方模块
- B19-1 识别未披露的关联方关系及异常关联交易.xlsx

**需求：**
1. B10 大型底稿使用 `d-form-table`（多 sheet Tab 切换，每 sheet 一组表单字段）
2. B11/B12 程序表使用 `a-program-console`
3. B13 初步分析程序表使用 `a-program-console`
4. B13-2~5 未审报表分析 = `analytical-review` 复用 A1-13/A1-14 的分析组件（但数据源是未审数 unadjusted_amount）
5. B15 重要性 = **已有 Materiality 模块**，B15 底稿渲染重定向到 `/materiality` 页面
6. B18 使用 `a-program-console`
7. B19 联动关联方模块（`related_party_registry` + `related_party_transactions`）
8. B10 的"行业理解"字段→联动 B51 舞弊风险评估的行业因素

### G5: 企业层面控制 + 业务层面控制 (B22~B23)

**模板文件：**
- B22A-1~5 企业层面控制（控制环境/管理层凌驾/风险评估/信息与沟通/监督）.xlsx
- B22A-4-1~5 IT 相关控制.xlsx/xlsm
- B22B 控制矩阵.xlsx — 企业层面控制汇总矩阵
- B22C 评价设计有效性 - 企业层面.xlsx
- B23-1~14 各循环业务层面控制.xlsm (14 组)
- B23-XX-5 职责分离通用模板.xlsx
- B23-{n}-2 流程图及描述.docx (14 份)
- B23-15 了解信息处理控制.xlsx

**需求：**
1. B22A 系列使用 `d-form-table`（每项控制=一行，结论列+引用依据列）
2. B22B 控制矩阵 = 新 componentType `control-matrix`（行=控制目标，列=5要素评价，交叉单元格=评价结论）
3. B22C 评价表使用 `d-form-table`
4. B23 系列(xlsm)是最复杂的底稿——每份含 4-6 sheet：
   - 穿行测试记录表（程序+控制点+测试结果）
   - 评价设计有效性
   - 控制偏差记录
   - 控制点汇总
   - 职责分离分析
5. B23 系列使用 `d-form-table` + 多 sheet Tab
6. B23 各循环与 C 类底稿(控制测试)联动：B23 评价"设计有效"→ C 类底稿自动关联
7. B23-{n}-2 docx 流程图使用 `word-template`
8. B22/B23 完成状态→联动 B50 汇总风险评估结果

### G6: 集团审计 (B30)

**模板文件：**
- B30 集团审计程序表.xlsx — 主程序表
- B30-1 了解组成部分.xlsx
- B30-2A/2B 组成部分重要性及审计范围.xlsm
- B30-3~B30-15 集团审计指令/服务协议/备忘录等.docx/.xlsx

**需求：**
1. B30 程序表使用 `a-program-console`
2. B30-2A/2B 使用 `audit-sheet`（含公式计算）
3. 其余 docx 使用 `word-template`
4. **仅合并项目（consolidated）适用**——standalone 项目 B30 全组标"不适用"
5. B30 完成→联动合并模块（ConsolScope 子公司清单）

### G7: 项目组讨论 + 风险评估汇总 + 审计策略 (B40~B60)

**模板文件：**
- B40 项目组讨论程序表.xlsx
- B40-1 讨论备忘录.docx
- B40-2 对SCOT+完整性再评估.docx
- B50 汇总风险评估结果程序表.xlsx
- B50-1~4 各类风险汇总表.xlsx — 关键核心底稿
- B51 舞弊风险因素（三因素分析）.xlsx
- B51-3/B51-5 货币资金/收入确认警觉情形.xlsx
- B52 管理层凌驾风险.xlsx
- B60 总体审计策略及具体审计计划.docx — 顶层战略文档
- B60-1 工时预算.xlsx
- B60-2-1~3 IT 审计计划.docx
- B60-3 评估专家工作计划.docx
- B60A~D 特殊考虑.docx

**需求：**
1. B40 使用 `a-program-console`
2. B50 汇总程序表使用 `a-program-console`
3. B50-1~4 风险汇总表 = 新 componentType `risk-matrix`（或复用 `d-form-table` 加风险评级着色）
4. B51/B52 舞弊分析使用 `d-form-table`（三因素=动机/机会/态度 列+评分）
5. B60 审计策略使用 `word-template`（LLM 辅助生成，联动 TSJ 提示词）
6. B60-1 工时预算使用 `audit-sheet`（可编辑+公式）
7. B50 风险评估结论→联动全部 D~N 循环底稿程序表的"识别的重大错报风险"展示

## 4. 跨模块联动矩阵

| 源底稿 | 目标 | 联动数据 |
|--------|------|---------|
| B1A/B1B 结论 | Project.status | 承接/拒绝 |
| B1-1/B1-2 风险评分 | B50-2 财务报表层次风险 | 风险等级 |
| B3 独立性确认 | A17-7 独立性声明 | 确认状态 |
| B13-2~5 初步分析 | trial_balance.unadjusted_amount | 未审数取数 |
| B15 重要性 | Materiality 模块 | 重定向 |
| B19 关联方 | related_party_registry | 关联方清单 |
| B22/B23 控制评价 | B50 汇总 + C 类底稿 | 设计有效性结论 |
| B30 集团审计 | ConsolScope | 合并范围 |
| B50-3 认定层次风险 | D~N 程序表 | 已识别风险展示 |
| B51 舞弊风险 | A17-1 ch6/ch15 + 全局 | 舞弊因素 |
| B60 审计策略 | 全局（LLM 辅助） | 策略生成 |

## 5. 技术约束

1. B 类底稿 wp_code 以 `B` 开头（B1A/B1B/B2/B3/B5/B10~B60）
2. 已有 `wp_account_mapping.json` 中 B 类注册：B1A/B1B/B10/B40/B50/B60 等
3. B 类底稿属于"承接与计划"阶段，前端 4 阶段流程图第一阶段
4. xlsm 文件含 VBA 宏（平台不执行宏，需提取结构忽略宏）
5. B23 系列 14 组结构高度相似→应设计一套通用 schema 模板

## 6. 分期实施建议

| Phase | 范围 | 优先级 | 依赖 |
|-------|------|--------|------|
| P0 | 注册+分类：所有 B 类 wp_code 加入 wp_account_mapping + classification | 必做 | 无 |
| P1 | 程序表类：B1A/B1B/B2/B10~B13/B18/B19/B30/B40/B50(程序表) | 必做 | P0 |
| P2 | 表单类：B1-1/B1-2/B1-5/B2-5/B22A/B22C/B50-1~4/B51/B52 | 必做 | P0 |
| P3 | Word 类：B1-3/B1-4/B1-7/B2-x/B3-1/B5-x/B23-x-2/B30-x/B40-1/B60 | 必做 | P0 |
| P4 | 联动类：B→A/B→C/B→D~N 数据流 + auto_data_source 扩展 | 增强 | P1+P2 |
| P5 | LLM 辅助：B60 策略生成 + B10 行业理解 AI 填充 | 增强 | P3+vLLM |
