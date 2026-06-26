# A 类底稿逐项精细化打磨建议

> 参照 D0 函证模块的打磨标准，逐底稿分析当前实现状态、具体缺陷和针对性优化方案。
> 生成时间：2026-06-22 | 基于 `work/2026-05-30-wp-specs` 分支

---

## A1 — 财务报告程序表

| 维度 | 现状 |
|------|------|
| componentType | `a1-dashboard`（专属中控组件） |
| 前端组件 | GtA1Dashboard.vue — 7字段编制信息 + 5里程碑看板 |
| guidance | ✅ 已精细化（6 section + recommended_questions） |
| 自动取数 | ⚠️ 里程碑状态为静态展示，无实时计算 |
| 跨底稿联动 | ❌ 看板无法点击跳转到对应子底稿 |

**打磨建议：**
1. 里程碑看板接入实时数据：从 wp_index 统计各循环完成率（已编制/总数）
2. 看板卡片可点击跳转：点击"错报评价"→ 打开 A13，点击"期后事项"→ A11
3. 新增"待办区"：汇总所有标记「待跟进」的程序步骤（当前无此功能）
4. 编制信息的 `preparer` 字段应自动取 wp 级 assigned_to（已修复确认）

---

## A2 — 调整分录程序表

| 维度 | 现状 |
|------|------|
| componentType | `a2-adjustment-console`（专属中控） |
| 前端组件 | GtA2AdjustmentConsole.vue |
| guidance | ✅ 已精细化 |
| 自动取数 | ✅ AJE/RJE 自动回写 TB |
| 导入导出 | ✅ 完整 |

**打磨建议：**
1. AJE 录入时自动检查借贷平衡（当前仅保存时校验，录入时无即时提示）
2. 「未更正错报」累计金额接近重要性水平时增加可视化预警条（红/黄/绿）
3. 上年未更正错报本年转回的自动标注（当前需手动标记）
4. AJE 来源底稿 chip 可点击跳转（ref_index chip 接入）

---

## A3 — 合并流程程序表

| 维度 | 现状 |
|------|------|
| componentType | `a3-consolidation-console`（专属中控） |
| 前端组件 | GtA3ConsolidationConsole.vue |
| guidance | ✅ 已精细化 |
| 子底稿 | A3-1~A3-8（合并试算/附注/商誉等） |
| 自动取数 | ❌ 合并试算无自动从子公司 TB 汇总功能 |
| override 缺失 | A3-4/A3-5/A3-6/A3-7 未注册 |

**打磨建议：**
1. **注册缺失 override**：A3-5→c-note-table / A3-6→c-note-table / A3-4→onlyoffice-sheet / A3-7→onlyoffice-sheet
2. A3-1 合并试算表增加「一键从子公司 TB 汇总」功能（当前手动填写）
3. A3-7 内部往来核对增加自动配对算法（按科目+金额双向匹配，差异标红）
4. A3-8 商誉减值测试：当前模板有 DCF 公式但无在线计算引擎 → 接入 Univer 或 OnlyOffice
5. 合并抵销分录（CE-xxx）应有独立编号体系和管理界面

---

## A4 — 经营分部程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override（走默认 a-program-console） |
| 子底稿 A4-1 | 无 override（默认 onlyoffice-sheet） |
| guidance | ✅ 已精细化 |

**打磨建议：**
1. A4-1 注册 override 为 `audit-sheet`（结构化分部数据，非复杂公式）
2. 分部数据表支持与合并报表自动勾稽（各分部合计 vs 合并总额的调节差异自动计算）
3. 10% 量化标准测试和 75% 覆盖率测试可由系统自动执行并标注结果

---

## A5 — 财务报表支持程序表 / 现金流验证

| 维度 | 现状 |
|------|------|
| componentType | `cf-verification`（专属5 tab组件） |
| 前端组件 | CashFlowVerification.vue — 5 tab 全功能 |
| guidance | ✅ 已精细化（含 CAS 31 逻辑、终止经营公式） |
| 子底稿 | A5-1~A5-4 均有 guidance |

**打磨建议：**
1. 主表逆算中增值税扣除逻辑当前仅有 alert 提示未实现 → 需接入税率配置自动扣除
2. 附表间接法与 TB 损益科目自动勾稽（当前为手动核对）
3. CF 调整分录支持从 A2 AJE 中按类型筛选导入（当前无联动）
4. 逆算差异超阈值时自动生成「待核实事项」标签并联动 A17-1

---

## A6 — 组成部分会计师报告（集团审计）

| 维度 | 现状 |
|------|------|
| componentType | 无 override（走默认 a-program-console） |
| A6-1 | 无 override（默认 onlyoffice-sheet） |
| guidance | ✅ 已精细化 |

**打磨建议：**
1. A6-1 注册 override 为 `onlyoffice-sheet`（明确声明，复杂多 sheet 汇总）
2. 组成部分审计师指令函模板应在线化（当前无 docx 在线编辑）
3. 各组成部分的重要性水平应从系统中自动计算（集团 PM × 比例因子）

---

## A7 — 关联交易程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override（走默认 a-program-console） |
| A7-1 | 无 override |
| A7-2 | `c-note-table`（已注册） |
| guidance | ✅ A7/A7-1/A7-2 均已精细化 |

**打磨建议：**
1. A7-1 汇总表注册 override 为 `audit-sheet`（关联方交易汇总，结构化数据表）
2. 关联方识别支持「天眼查」等外部数据源对接（远期，当前手动）
3. 期末关联方余额占比自动计算并与重要性水平对比预警
4. 关联交易附注披露（A7-2）与 A3-5 合并附注自动交叉核对

---

## A8 — 其他信息程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override（走默认 a-program-console） |
| A8-1/A8-2 | 无 override（docx 模板） |
| guidance | ✅ A8/A8-1/A8-2 已精细化 |

**打磨建议：**
1. A8-1/A8-2 注册 override 为 `word-template`（在线编辑 docx）
2. A8-2 比对记录可考虑结构化方案（表格式：年报引用 vs 审定数 vs 差异）替代纯 docx

---

## A9 — 内部控制建议程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override（走默认 a-program-console） |
| A9-1/A9-2 | 无 override（docx 模板） |
| guidance | ✅ A9/A9-2 已精细化 |

**打磨建议：**
1. A9-1/A9-2 注册 override 为 `word-template`
2. 沟通函内容可从 A14-1 缺陷汇总表自动生成（选择缺陷 → 自动填入函件模板）
3. 管理层回应字段应在 A14-1 中填写后自动同步到沟通函

---

## A10 — 与治理层沟通程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override |
| A10-1 | 无 override（docx） |
| A10-2 | `d-form-confirmation`（已注册） |
| guidance | ✅ A10/A10-2 已精细化 |

**打磨建议：**
1. A10 程序表注册 override 为 `a-program-console`
2. A10-1 注册 override 为 `word-template`
3. 沟通记录（A10-2）增加「沟通主题标签」分类（计划/发现/意见/独立性）便于筛选

---

## A11 — 期后事项程序表（Bundle）

| 维度 | 现状 |
|------|------|
| componentType | `a11-bundle`（Tab 套件） |
| 前端组件 | GtA11Bundle.vue — 4 tab（程序/审定/A11-2/A11-3） |
| guidance | ✅ 已精细化 |
| 子底稿 | A11-2/A11-3 = checklist-table（已注册） |

**打磨建议：**
1. A11-1 期后事项问询函（docx）注册 override 为 `word-template` → 实现在线编辑
2. 期后事项识别增加「截止日更新」提醒：临近报告签发日时自动弹窗提示需重新检查
3. A11-2 调查问卷的检查项与 A15-1 持续经营指标交叉标注（同一事项影响两个底稿）
4. bundle 内的 route.query.sheet 深链接已验证可用

---

## A12 — 律师回复程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override |
| A12-1 | 无 override（docx） |
| guidance | ✅ 已精细化 |

**打磨建议：**
1. A12 注册 override 为 `a-program-console`
2. A12-1 注册 override 为 `word-template`
3. 律师函跟踪增加「发函/回函状态管理」（类似 D0 函证的发函跟踪逻辑）
4. 回函结果（胜/败概率+金额范围）自动联动 A5-3 或有事项的三条件判断

---

## A13 — 错报评价（Bundle）

| 维度 | 现状 |
|------|------|
| componentType | `misstatement-workpaper`（6 tab 套件） |
| 前端组件 | GtMisstatementWorkpaper.vue |
| guidance | ✅ 已精细化（含审计结论模板） |
| 子底稿 | A13-2~5 = d-form-table（已注册） |
| 自动取数 | ❌ A13-1 汇总为手动填写 |

**打磨建议：**
1. **A13-1 汇总自动聚合**（核心缺口）：新增 resolver `a13_misstatement_summary`，从 A13-2~5 汇聚错报条目数/金额/性质分布 → 保存 A13-2 时 EventBus 触发 A13-1 重算
2. 错报录入时自动关联 B50 风险评估（哪个认定相关）→ ref_chip 可跳转
3. 金额超过重要性水平时自动标红 + el-alert 预警
4. A13-5 沟通 tab 增加「生成沟通函草稿」按钮（汇总本年错报清单自动填入 A10-1 模板）
5. 上年未更正错报的本年转回/延续状态追踪

---

## A14 — 内部控制缺陷程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override（走 a-program-console） |
| A14-1 | `checklist-table`（已注册） |
| A14-2/A14-4/A14-5 | `d-form-table`（已注册） |
| A14-3 | `a14-3-workbook`（专属 5 tab） |
| A14-6 | `e-control-test`（已注册） |
| guidance | ✅ A14/A14-1~6 全部精细化 |

**打磨建议：**
1. A14-1 缺陷汇总表增加「缺陷来源底稿」ref_chip 跳转（从 C 循环追溯）
2. 缺陷评级自动建议：基于影响金额 vs 重要性水平自动推荐级别（人工可覆盖）
3. A14-3 IT 缺陷 workbook 增加 sheetName 路由支持（当前无法从外部指定 tab 打开）
4. 上年缺陷整改跟踪：自动从上年项目导入未整改缺陷（需跨年度数据访问）
5. A14-5 组合评价增加可视化（缺陷关联图谱：哪些缺陷影响同一认定）

---

## A15 — 持续经营（Bundle）

| 维度 | 现状 |
|------|------|
| componentType | `a15-bundle`（2 tab：程序表 + A15-1） |
| 前端组件 | GtA15Bundle.vue（最简单的 bundle） |
| guidance | ✅ A15/A15-1 已精细化 |
| 自动取数 | ❌ 无财务指标自动计算 |

**打磨建议：**
1. **新增财务指标自动取数**（高优先级）：从 TB 自动计算流动比率/速动比率/资产负债率/净资产/累计未分配利润 → 显示在 A15-1 调查表顶部
2. A15-1 调查表的每个「是」项增加严重程度下拉（轻微/中等/严重）
3. 与 A11 期后事项交叉标注：期后出现持续经营风险时两个底稿联动提醒
4. 管理层现金流预测评价工具：录入预测数据后自动计算12个月覆盖率
5. bundle 考虑增加第三个 tab「管理层应对计划评价」

---

## A16 — 管理层声明书程序表

| 维度 | 现状 |
|------|------|
| componentType | `word-template`（已注册，仅 A16 程序表本身） |
| A16-1~7 | ❌ 均无 override（7个 docx 模板无在线编辑） |
| guidance | ✅ A16/A16-2~7 全部精细化 |

**打磨建议：**
1. **批量注册 A16-1~7 为 `word-template`**（最高优先级，零代码配置）
2. 声明书模板预填：项目名称/日期/签署人从项目信息自动填入
3. 定制条款管理：根据审计发现（A13错报/A14缺陷/A7关联交易）自动建议追加条款
4. 签署状态跟踪：标记「已签署/待签署/拒签」

---

## A17 — 重大事项概要程序表

| 维度 | 现状 |
|------|------|
| componentType | 无 override（走 a-program-console） |
| A17-1 | `a17-summary`（专属16章组件，含AI+pull） |
| A17-5-1~5 | `checklist-table`（已注册） |
| A17-7 | `independence-signing`（已注册） |
| A17-2/A17-4/A17-6 | ❌ 无 override（docx） |
| guidance | ✅ A17/A17-1/A17-2/A17-4/A17-5 全部精细化 |

**打磨建议：**
1. A17-2/A17-4/A17-6 注册 override 为 `word-template`
2. A17-1 各章节的 `source_label` 解析为可点击 chip（正则匹配 wp_code 模式 → 跳转）
3. A17-1 ch 间一致性检查：ch10 持续经营结论 vs ch14 审计意见的逻辑校验
4. AI 生成功能（已有 POST /ai-generate）接入 vLLM 后增加多章节联合分析

---

## A18 — 向监管部门报送

| 维度 | 现状 |
|------|------|
| A18-2 | `regulatory-letter`（已注册专属组件） |
| A18-1 | 无 override（docx） |
| guidance | ✅ A18-1 已精细化 |

**打磨建议：**
1. A18-1 注册 override 为 `word-template`
2. 报送截止日提醒：项目设置中配置监管报送截止日 → 到期自动提醒

---

## A21~A25 — 五级复核表（10个底稿）

| 维度 | 现状 |
|------|------|
| componentType | `review-checklist`（全部已注册） |
| 前端组件 | GtReviewChecklist.vue（通用） |
| guidance | ✅ A21-1/A21-2/A22-1/A22-2/A23-1/A23-2/A24-1/A24-2/A25-1/A25-2 全部精细化 |
| 角色权限 | ❌ 无权限控制（任何人可填任何级别） |

**打磨建议：**
1. **角色权限绑定**（核心缺口）：后端 render-config 根据当前用户角色返回 `readonly` → 非本级角色只读
   - A21 → 现场负责人
   - A22 → 经理
   - A23 → 合伙人
   - A24 → 质控复核合伙人
   - A25 → EQCR
2. 复核流程前置检查：下级复核未完成时上级不可开始（A22 须 A21 先签字）
3. 复核意见清零统计：在 A1 dashboard 显示各级复核意见剩余数
4. 签字后锁定：复核表签字后自动变为 readonly（不可反复修改）

---

## A28 — 税务专家复核

| 维度 | 现状 |
|------|------|
| componentType | 无 override（默认 onlyoffice-sheet） |
| guidance | ✅ 已精细化 |

**打磨建议：**
1. 注册 override 为 `d-form-table`（结构化的专家复核记录表，非复杂 Excel）
2. 递延税自动取数：从 K 循环审定表拉取递延税资产/负债余额
3. 专家意见与 A2 AJE 联动：需调整时一键生成 AJE 草稿

---

## A30 — 电子底稿归档检查表

| 维度 | 现状 |
|------|------|
| componentType | 无 override（默认 onlyoffice-sheet） |
| guidance | ✅ 已精细化 |

**打磨建议：**
1. **注册 override 为 `checklist-table`**（标准检查清单，已有组件直接可用）
2. 底稿完整性自动检查：与 wp_index 对照，自动标注缺失的底稿
3. 复核签字完整性自动检查：扫描所有底稿的 reviewer 字段是否为空
4. 归档倒计时提醒：审计报告日 + 60天 = 归档截止日

---

## A31 — 审计标识一览表

| 维度 | 现状 |
|------|------|
| componentType | `audit-legend`（已注册专属组件） |
| 前端组件 | AuditLegendPanel.vue |
| guidance | ✅ 已精细化 |

**打磨建议：**
1. 支持项目自定义标识：除标准标识外允许项目组新增自定义符号和含义
2. 标识使用统计：显示各标识在全项目底稿中的使用频次
3. 与底稿编辑器联动：编辑底稿时可从标识面板拖拽插入

---

## A1-11 — 业务报告签字流转控制表

| 维度 | 现状 |
|------|------|
| componentType | `wp-popup-signing`（已注册） |
| guidance | ✅ 已精细化 |

**打磨建议：**
1. 签字流程状态机：草稿→各级签字→已签发（当前仅静态记录）
2. 签发前自动校验：A17-5 核对表是否全部打钩、复核意见是否清零
3. 审计报告文号自动编号（按事务所规则生成）

---

## A1-12~A1-16 — 核查表/核对表/分析性复核

| 维度 | 现状 |
|------|------|
| A1-12 | `checklist-table` ✅ |
| A1-13/A1-14 | `analytical-review` ✅ |
| A1-15/A1-16 | `checklist-table` ✅ |
| guidance | ✅ 全部精细化 |

**打磨建议：**
1. A1-13/A1-14 分析性复核增加自动取数：从 TB 拉取审定数+上年数 → 自动计算变动率
2. 波动异常项自动标注（超阈值变红）
3. A1-15/A1-16 核对表支持「不适用」项批量标注（非逐条点击）
4. A1-16 上市公司核对表增加规则更新提醒（证监会/交易所规则变更时）

---

## 未注册 docx 底稿汇总（30个待在线化）

以下模板文件存在于 `backend/wp_templates/A/` 但未在 `wp_code_overrides.json` 中注册为 `word-template`，用户打开时只能下载离线编辑：

| wp_code | 模板文件 | 优先级 |
|---------|---------|--------|
| A10-1 | 与治理层沟通函.docx | P1（高频） |
| A11-1 | 期后事项问询函.docx | P1 |
| A12-1 | 法律事务确认函.docx | P1 |
| A16-1 | 管理层声明书（企业会计准则）.docx | P1（必备） |
| A16-2 | 管理层声明书（整合审计）.docx | P1 |
| A16-3 | 管理层声明书（IPO）.docx | P2 |
| A16-4 | 管理层声明书（IPO审阅）.docx | P3 |
| A16-5 | 管理层声明书（新三板）.docx | P3 |
| A16-6 | 管理层声明书（企业债）.docx | P3 |
| A16-7 | 管理层关联交易声明书.docx | P2 |
| A17-1 | 重大事项概要汇总.docx | — (已有 a17-summary) |
| A17-2-1 | KAM.docx | P2 |
| A17-3 | 业务咨询记录.docx | P2 |
| A17-3-1 | 咨询结果执行记录.docx | P3 |
| A17-4 | 重大分歧记录.docx | P2 |
| A17-6 | 总结会纪要.docx | P3 |
| A17-7 | 独立性声明书.doc | — (已有 independence-signing) |
| A18-1 | 向监管部门报送函.docx | P2 |
| A26-1 | 专技委提交资料清单.docx | P3 |
| A26-2 | 专技委审核记录.docx | P3 |
| A26-3 | 专技委会议记录.docx | P3 |
| A26-4 | 专技委分歧会议记录.docx | P3 |
| A27-1 | IT审计总结备忘录.docx | P2 |
| A8-1 | 管理层书面声明.docx | P2 |
| A8-2 | 其他信息比对记录.docx | P2 |
| A9-1 | 向管理层通报内控缺陷函.docx | P2 |
| A9-2 | 向治理层通报内控缺陷函.docx | P1 |

**批量操作方案**：在 `wp_code_overrides.json` 中一次性添加上述 wp_code → "word-template" 映射（排除已有专属组件的 A17-1/A17-7）。

---

## 优先级总结

### P0 — 零代码配置（1天内可完成）
- 补全 25 个 docx override 注册（word-template）
- A30 注册为 checklist-table
- A4-1 注册为 audit-sheet
- A28 注册为 d-form-table
- A7-1 注册为 audit-sheet

### P1 — 核心联动功能（3~5天）
- A13-1 汇总自动聚合（resolver + EventBus）
- A15 财务指标自动取数（从 TB 计算）
- A21~25 角色权限绑定（render-config readonly）
- A1-13/A1-14 分析性复核自动取数
- A17-1 source_label → chip 可点击

### P2 — 体验增强（1~2周）
- A1 dashboard 进度看板实时化
- A2 AJE 借贷即时校验 + 预警条
- A3-7 内部往来自动配对
- A14-3 增加 sheetName 路由
- A5 CF↔A2 AJE 联动
- A12 律师函发函/回函状态管理

### P3 — 远期深度打磨（需 spec 三件套）
- A3-8 商誉减值 DCF 在线计算
- A22~A25 复核流程状态机（下级完成→上级可开始→签字锁定）
- A14 缺陷→C循环双向导航
- A 类全面自动取数 resolver 注册（5个新 resolver）
- A4 分部数据量化测试自动化
- A16 声明书定制条款智能推荐

---

*文档生成时间：2026-06-22 | 基于代码库 work/2026-05-30-wp-specs 分支*
