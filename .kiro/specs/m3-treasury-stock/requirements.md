# Requirements Document: M3 库存股底稿专属HTML精美组件

## 开发方法论（可复制到后续循环spec）

### 双源输入流程

1. **源xlsx实读**（openpyxl脚本）：获取真实sheet结构。列头命名和公式逻辑的权威来源。
2. **底稿模板库md**（`BCD类底稿md/M股东权益循环底稿模板库.md`）：获取业务语义。业务逻辑和联动设计的权威来源。

冲突解决：列名/公式以xlsx为准；联动方向/认定映射以md为准。

### 功能方向

- **联动性**：跨sheet computed链 + **回购/注销核对 + 外币投资汇率折算** + TB回写
- **美观性**：分组配色 + 统计仪表板 + 进度条
- **跳转溯源**：GtIndexChip跳转 + tooltip + 公式列虚线
- **易操作**：引导步骤 + 方法论上下文 + 编制提示
- **导入导出**：el-dropdown三级 + useM3ImportExport
- **AI辅助**：多section AI
- **双模式**：el-segmented + OO降级

### 三件套产出规范

- requirements.md / design.md / tasks.md 按Phase0~7

## Introduction

M3库存股底稿的专属HTML精美组件构建。将现有通用渲染升级为独立专属组件 `m3-treasury-stock`，覆盖来自 `M3 库存股.xlsx` 的有效sheet（含1个会计规定辅助sheet跳过）。科目覆盖4002库存股（**借方/权益备抵类！**）。所有sheet合并到一个大Tab页签下（sheetName prop v-if分发）。

**M3核心特殊铁律**：①**库存股是权益的备抵科目，借方余额！**（期末=期初+借方-贷方，回购股份增加库存股在**借方**，注销/再售减少在**贷方**，与其他M权益类方向相反）②**回购股份+注销业务**（回购价核对、注销冲减实收资本/资本公积）。关键公式总数约90+（审定表73公式）。

## Glossary

- **Tab_Index**: 底稿目录
- **Procedure_Table_M3A**: 库存股实质性程序表M3A（复用a-program-console）
- **Adjudication_M3_1**: 审定表M3-1，33×12，73公式，科目4002库存股(借方/权益备抵)
- **Disclosure_Listed**: 附注披露信息（上市公司），16×11
- **Detail_M3_2**: 明细表M3-2，59×19，按回购批次列示库存股
- **Adjustment_M3_3**: 库存股调整分录汇总M3-3
- **FX_Invest_M3_4**: 外币投资汇率测算表M3-4，外币回购折算
- **Treasury_Check_M3_5**: 库存股检查表M3-5（回购/注销核对）
- **Cross_Sheet_Engine**: 跨sheet引擎
- **Formula_Engine**: 前端公式引擎composable（**权益备抵类！借方科目**）
- **FX_Engine**: 外币折算引擎（纯函数）
- **Treasury_Engine**: 库存股回购/注销引擎（纯函数）
- **Trial_Balance_Writeback**: 审定数回写（科目4002）
- **EventBus**: 进程内事件总线
- **GtIndexChip**: 交叉索引跳转

## Requirements

### Requirement 1: 组件架构与sheetName分发

**User Story:** As a 开发者, I want to M3库存股底稿按sheetName分发, so that 各sheet在统一入口有序组织。

#### Acceptance Criteria

1. THE M3 组件 SHALL 注册新componentType: `m3-treasury-stock`，主入口为 GtM3TreasuryStock.vue
2. THE GtM3TreasuryStock.vue SHALL 接收 `sheetName` prop，正则提取编码(M3-1)，v-if分发
3. THE M3 组件 SHALL 使用 defineAsyncComponent 懒加载
4. THE M3 组件 SHALL 拆为：m3/core/（审定+明细+调整+附注）、m3/calc/（外币汇率）、m3/inspection/（检查表）
5. THE M3 组件 SHALL composable分层：useM3FormData + useM3FormulaEngine + useM3FxEngine(纯函数) + useM3TreasuryEngine(纯函数) + useM3CrossSheet + useM3DualMode + useM3ImportExport
6. THE M3 组件 SHALL 在htmlRendererRegistry中注册'm3-treasury-stock'
7. THE M3 组件 SHALL 在wp_code_overrides.json中将M3/M3-1~M3-5/M3A映射为'm3-treasury-stock'
8. THE M3 组件 SHALL 在VALID_COMPONENT_TYPES中注册'm3-treasury-stock'
9. THE GtM3TreasuryStock.vue SHALL 支持selfLoad
10. THE M3 组件 SHALL 使用 checklist_responses 表存储，item_id前缀"M3-{sheet}-{field}"
11. THE 未迁移sheet及会计规定辅助sheet SHALL 走 OnlyOffice fallback或跳过

### Requirement 2: 审定表M3-1（权益备抵类借方科目！）

**User Story:** As a 审计助理, I want to 在精美审定表中查看库存股数据, so that 我能验证权益备抵类科目的借方期末余额。

#### Acceptance Criteria

1. THE Adjudication_M3_1 SHALL 渲染为单区块：库存股(借方/权益备抵，按回购批次分类+小计)
2. THE Adjudication_M3_1 SHALL 显示列：项目 | 期初 | 借方发生(回购) | 贷方发生(注销/再售) | 期末 | 未审 | AJE | RJE | 审定
3. THE Formula_Engine SHALL 计算审定数=未审+AJE+RJE
4. THE Formula_Engine SHALL 校验权益备抵类：**期末=期初+借方-贷方**（回购在借方增加，注销在贷方减少，与其他M权益类方向相反！）
5. THE Adjudication_M3_1 SHALL 与M3-2明细合计交叉验证
6. WHEN 审定数变化时 SHALL 回写TB(4002)+发布'substantive:adjudicated'
7. THE Adjudication_M3_1 SHALL 在UI显著标注"库存股为权益备抵，借方余额"提示

### Requirement 3: 明细表M3-2（按回购批次列示）

**User Story:** As a 审计助理, I want to 管理库存股明细, so that 每笔回购/注销可追溯。

#### Acceptance Criteria

1. THE Detail_M3_2 SHALL 显示列：回购批次 | 回购日期 | 回购股数 | 回购单价 | 回购金额 | 注销股数 | 期末库存股数 | 期末金额
2. THE Detail_M3_2 SHALL 自动计算：期末库存股数=期初+回购-注销；期末金额=期初+回购金额-注销金额（备抵借方）
3. THE Detail_M3_2 SHALL 19列宽表拆分：按回购信息/注销情况/期末余额区段Tab（行同步）
4. THE Detail_M3_2 SHALL 支持动态行新增（先弹ElMessageBox.prompt输入批次名）+导入导出
5. THE Detail_M3_2 SHALL 与M3-1审定表交叉验证

### Requirement 4: 外币投资汇率测算表M3-4（外币回购折算）

**User Story:** As a 审计助理, I want to 对外币回购按汇率折算, so that 外币库存股折算准确。

#### Acceptance Criteria

1. THE FX_Invest_M3_4 SHALL 显示列：回购批次 | 原币回购额 | 币种 | 回购日汇率 | 折算本位币 | 账面本位币 | 折算差异
2. THE FX_Engine SHALL 计算折算本位币=原币回购额×回购日汇率
3. THE FX_Engine SHALL 计算折算差异=折算本位币-账面本位币
4. WHEN |折算差异|>阈值时 SHALL 红色高亮
5. THE FX_Invest_M3_4 SHALL 公式全部前端实时计算

### Requirement 5: 回购/注销核对（检查表M3-5）

**User Story:** As a 审计助理, I want to 核对回购与注销业务, so that 回购价格真实性、注销冲减合规性得到验证。

#### Acceptance Criteria

1. THE Treasury_Check_M3_5 SHALL 显示回购核对列：批次 | 回购决议 | 回购股数 | 回购单价 | 回购总额 | 核对结果
2. THE Treasury_Engine SHALL 计算回购金额=回购股数×回购单价
3. THE Treasury_Check_M3_5 SHALL 显示注销核对：注销股数 | 冲减实收资本(M2) | 冲减资本公积(M4) | 差额处理
4. THE Treasury_Engine SHALL 计算注销冲减差额=注销金额-冲减实收资本-冲减资本公积
5. THE Treasury_Check_M3_5 SHALL 提供核对清单+审计结论区（el-card包裹）+AI辅助按钮

### Requirement 6: 调整分录M3-3 + 附注

**User Story:** As a 审计助理, I want to 管理调整分录并生成附注, so that 审计结论完整。

#### Acceptance Criteria

1. THE Adjustment_M3_3 SHALL 借贷平衡校验+EventBus+双向同步M3-1
2. THE Disclosure_Listed SHALL 渲染上市公司库存股附注
3. THE 附注 SHALL subscribe 'substantive:adjudicated'刷新

### Requirement 7: 引擎（纯函数）+ 集成能力

**User Story:** As a 开发者, I want to 实现外币折算+回购注销纯函数引擎并集成标准能力, so that 差异可PBT验证且与D~N标准一致。

#### Acceptance Criteria

1. THE FX_Engine SHALL calcFxConverted(amount, rate)=amount×rate
2. THE FX_Engine SHALL calcFxDiff(converted, booked)=converted-booked
3. THE Treasury_Engine SHALL calcRepurchaseAmount(shares, price)=shares×price
4. THE Treasury_Engine SHALL calcCancelDiff(cancelAmount, deductCapital, deductReserve)=cancelAmount-deductCapital-deductReserve
5. THE Formula_Engine SHALL calcContraEquityEndBalance(begin, debit, credit)=begin+debit-credit（**备抵借方！**）
6. THE M3 SHALL 支持双模式（结构化 ↔ OnlyOffice）+ OO健康检查降级
7. THE M3 SHALL 支持导入导出三级（useM3ImportExport，http带Authorization）
8. THE M3 SHALL 集成useVersionTrail(autoSnapshot) + provide openReviewDialog
