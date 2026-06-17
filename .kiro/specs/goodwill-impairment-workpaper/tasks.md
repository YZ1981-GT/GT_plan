# Implementation Plan

## P0: Univer 渲染 + 编制说明

- [ ] 1. 确认 A3-8/A3-8-1 当前 classification 路由（应走 univer 或 audit-sheet）
- [ ] 2. 编制说明数据提取：从模板 xlsx "编制说明"sheet 提取 guidance 文本 + WACC/CAPM 公式
- [ ] 3. 前端：底稿编辑器增加"编制说明"tab/面板展示 guidance（复用现有 guidance 机制）
- [ ] 4. 验证：打开 A3-8 能正常编辑 + 查看编制说明

## P1: 结构化 DCF 组件（后续）

- [ ]* 5. 新建 `dcf-valuation` componentType
- [ ]* 6. WACC 计算面板（Kd/Rf/β/Rm/D/E 参数输入 → 自动算 WACC+Ke）
- [ ]* 7. 5年 DCF 表格（现金流预测×折现系数→现值）
- [ ]* 8. 减值判定面板（账面 vs 可收回 → 差额 → 分摊规则）
- [ ]* 9. 数据联动：资产组账面从合并报表取
