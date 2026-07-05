# Requirements Document: K7 递延收益底稿专属HTML精美组件

## 开发方法论（可复制到后续D~N循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列名/公式以此为准。
2. **底稿模板库md**（`BCD类底稿md/K递延收益循环底稿模板库.md`）：获取业务语义。联动方向/认定映射以此为准。

### 功能方向

- **联动性**：跨sheet computed链 + TB回写(2401) + 政府补助分摊联动其他收益/营业外收入
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useK7ImportExport
- **AI辅助**：多section AI（分摊结论）
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7排序

## Introduction

K7递延收益底稿的专属HTML精美组件构建。覆盖来自 `K7 递延收益.xlsx` 的10个有效sheet（含1个会计提示辅助sheet，跳过不组件化，实际功能sheet 9个）。科目覆盖2401递延收益（**贷方/负债类**）。

**K7核心特殊**：①**负债类科目**（期末=期初+贷方-借方）②**政府补助分摊测算引擎**（与资产相关：按资产使用寿命分期计入其他收益；与收益相关：分期或一次性计入）③分摊金额联动其他收益(K10)/营业外收入(K12)。审定表K7-1（49公式）+ 明细表K7-2（21公式）+ 测算表K7-4（23公式）。关键公式总数约100+。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_K7A**: 递延收益实质性程序表K7A（复用a-program-console）
- **Adjudication_K7_1**: 审定表K7-1，54行13列49公式，负债类2401审定
- **Disclosure_Listed**: 附注披露信息（上市公司），18行11列
- **Disclosure_SOE**: 附注披露信息（国企），18行10列
- **Detail_K7_2**: 明细表K7-2，41行32列21公式，按补助项目的递延收益明细
- **Adjustment_K7_3**: 调整分录汇总K7-3
- **Amortization_Calc_K7_4**: 测算表K7-4，26行27列23公式，政府补助分摊测算
- **Deferred_Check_K7_5**: 递延收益检查表K7-5
- **Grant_Amort_Engine**: 政府补助分摊引擎（与资产相关/与收益相关）
- **Formula_Engine**: 前端公式引擎（负债类）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转
- **Trial_Balance_Writeback**: 审定数回写（2401）

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to K7递延收益按sheetName分发, so that 9个功能sheet有序组织。

#### Acceptance Criteria

1. THE K7 组件 SHALL 注册componentType: `k7-deferred-income`，主入口GtK7DeferredIncome.vue
2. THE GtK7DeferredIncome.vue SHALL 接收sheetName prop，正则提取编码后v-if分发
3. THE K7 组件 SHALL defineAsyncComponent懒加载
4. THE K7 组件 SHALL 子目录：k7/core/（审定/明细/调整/附注） + k7/amortization/（测算） + k7/inspection/（检查）
5. THE K7 组件 SHALL composable分层：useK7FormData + useK7FormulaEngine(纯函数) + useK7GrantAmortEngine(纯函数) + useK7CrossSheet + useK7DualMode + useK7ImportExport
6. THE K7 组件 SHALL htmlRendererRegistry注册'k7-deferred-income'
7. THE K7 组件 SHALL wp_code_overrides: K7/K7-1~K7-5/K7A → 'k7-deferred-income'（会计提示辅助sheet走OO fallback）
8. THE K7 组件 SHALL VALID_COMPONENT_TYPES注册
9. THE K7 组件 SHALL selfLoad支持
10. THE K7 组件 SHALL checklist_responses存储，前缀"K7-{sheet}-{field}"

### Requirement 2: 审定表K7-1（49公式，负债类！）

**User Story:** As a 审计助理, I want to 在审定表中查看递延收益, so that 我能验证各补助项目余额正确。

#### Acceptance Criteria

1. THE Adjudication_K7_1 SHALL 显示：项目(与资产相关/与收益相关分组)|期初|本期增加(收到)|本期减少(分摊)|期末|未审|AJE|RJE|审定数|备注
2. THE Formula_Engine SHALL 计算期末=期初+增加-分摊（负债类2401）
3. THE Formula_Engine SHALL 计算审定=未审+AJE+RJE
4. THE Adjudication_K7_1 SHALL 三角勾稽校验+红色高亮
5. THE Adjudication_K7_1 SHALL 与K7-2明细/K7-4测算交叉验证
6. WHEN 审定数变化时 SHALL 回写trial_balance(2401)+发布'substantive:adjudicated'
7. THE Adjudication_K7_1 SHALL 底部审计说明+结论+复核入口，54行虚拟滚动

### Requirement 3: 明细表K7-2（32列21公式）

**User Story:** As a 审计助理, I want to 管理递延收益明细, so that 每笔政府补助可追溯。

#### Acceptance Criteria

1. THE Detail_K7_2 SHALL 将32列拆为3区段Tab：基础(序号/补助项目/批文号/补助类型/与资产或收益相关/收到金额/收到日期) | 分摊(分摊方法/分摊期/期初/本期分摊/期末) | 检查(计入科目/凭证/结论/备注)
2. THE Formula_Engine SHALL 期末=期初+收到-分摊，合计行联动审定表
3. THE Detail_K7_2 SHALL 动态行新增（ElMessageBox.prompt输入补助项目）+导入导出
4. THE Detail_K7_2 SHALL 与K7-4测算交叉验证（企业分摊 vs 测算分摊）
5. THE Detail_K7_2 SHALL 41行虚拟滚动

### Requirement 4: 政府补助分摊测算表K7-4（23公式，分摊引擎）

**User Story:** As a 审计助理, I want to 测算政府补助分摊, so that 我能复核分摊金额合理性。

#### Acceptance Criteria

1. THE Amortization_Calc_K7_4 SHALL 显示：补助项目/补助总额/相关类型/分摊方法/分摊期总期数/本期期数/本期应分摊(公式)/累计分摊/期末余额(公式)/企业分摊/差异(公式)/结论
2. THE Grant_Amort_Engine SHALL 与资产相关直线分摊=补助总额/分摊期总期数×本期期数
3. THE Grant_Amort_Engine SHALL 与收益相关：补偿以后期间→分期计入；补偿已发生→一次性计入当期损益
4. THE Grant_Amort_Engine SHALL 计算期末余额=补助总额-累计分摊
5. THE Grant_Amort_Engine SHALL 计算测算差异=测算分摊-企业分摊
6. WHEN 差异>重要性水平时 SHALL 红色标记提示调整
7. THE Amortization_Calc_K7_4 SHALL AI辅助生成分摊结论

### Requirement 5: 递延收益检查表K7-5

**User Story:** As a 审计助理, I want to 执行递延收益检查, so that 补助确认和分摊合规。

#### Acceptance Criteria

1. THE Deferred_Check_K7_5 SHALL 逐项检查：补助真实性/批文合规/相关类型判断正确性/分摊方法适当性/计入科目正确性(其他收益/营业外收入)
2. THE Deferred_Check_K7_5 SHALL 逐项"合规/不合规/不适用"+行级抽凭+行级OCR（批文）
3. WHEN 存在"不合规"项时 SHALL 红色摘要提示

### Requirement 6: 附注披露 + 调整分录 + 跨底稿联动

**User Story:** As a 审计助理, I want to 生成附注、管理调整分录并联动损益底稿, so that 披露完整、分摊去向可追溯。

#### Acceptance Criteria

1. THE Disclosure SHALL variant双版本（上市18×11/国企18×10）+按相关类型披露+自动取数+AI辅助+subscribe刷新
2. THE Adjustment_K7_3 SHALL 借贷平衡+双向同步K7-1+publish 'adjustment:created'→A13+导入导出
3. THE K7 SHALL 分摊金额通过GtIndexChip联动其他收益(K10)/营业外收入(K12)

### Requirement 7: 公式引擎与分摊引擎（纯函数）

**User Story:** As a 开发者, I want to 实现公式与分摊纯函数引擎, so that 核心公式可PBT验证。

#### Acceptance Criteria

1. THE Formula_Engine SHALL calcAuditedAmount(unadj, aje, rje): 审定=未审+AJE+RJE
2. THE Formula_Engine SHALL calcLiabilityEndBalance(begin, received, amortized): 期末=期初+收到-分摊
3. THE Grant_Amort_Engine SHALL calcStraightLineAmort(total, totalPeriods, currentPeriods): 直线分摊
4. THE Grant_Amort_Engine SHALL calcRemainingBalance(total, accumulated): 期末余额=总额-累计分摊
5. THE Grant_Amort_Engine SHALL calcAmortVariance(calculated, booked): 测算差异
6. THE Formula_Engine SHALL calcSubtotal(arr): 合计
