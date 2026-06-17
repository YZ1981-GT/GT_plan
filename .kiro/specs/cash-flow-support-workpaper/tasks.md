# Implementation Plan

## P0: 确认路由 + 基本渲染

- [ ] 1. 确认 A5-1~A5-4 当前 classification 路由（应走 audit-sheet 或 univer）
- [ ] 2. A5-4 公式验证：确认 xlsx 原生公式在 Univer 中正常计算
- [ ] 3. 准则说明 guidance 数据准备（A5-2 承诺/A5-3 或有/A5-4 持续终止经营）
- [ ] 4. 验证：4个子底稿均能正常打开和编辑

## P1: 数据取数联动

- [ ] 5. A5-4 本年净利润从 trial_balance IS-027 取
- [ ] 6. A5-4 现金流量净额从 financial_report CFS 行取
- [ ] 7. A5-1 现金流量表核查与报表数据对比

## P2: 结构化增强（可选）

- [ ]* 8. A5-4 计算表公式改为前端自动计算（C=A-B, E=C-D, I=G-H, J=E+F+I）
- [ ]* 9. A5-2/A5-3 承诺/或有事项与附注联动
