# 现金流量表支持底稿 Design

## Overview

A5-1~A5-4 使用现有 audit-sheet/univer componentType 渲染。A5-4 的公式（C=A-B, E=C-D, I=G-H, J=E+F+I）由 xlsx 原生公式处理或 audit-sheet 内置计算。

## 路由设计

- A5: 已有 `cf-verification` componentType（不改）
- A5-1~A5-4: 走 class_code 派生（F-审定表 → audit-sheet 或默认 univer）

## 数据取数

### A5-4 持续/终止经营利润
- 本年净利润从 `trial_balance.audited_amount` 按 IS-027(净利润) 取
- 终止经营各项由用户手工填写（大多数企业无终止经营）
- 现金流量净额从 CFS 行取（CFS-009 经营/CFS-018 投资/CFS-027 筹资）

### A5-1 现金流量表核查
- 从 financial_report 的 cash_flow_statement 类型取各行数据
- 与序时账分类汇总对比

## audit-sheet 复用

A5-2(承诺)/A5-3(或有) 结构与现有 audit-sheet 完全一致：
- 行：项目明细
- 列：金额/说明/备注
- 无需额外 componentType

## 准则说明 Guidance

```json
{
  "A5-2": {
    "guidance": "CAS 13 相关：资本性支出承诺应披露已签合同但尚未执行的金额..."
  },
  "A5-3": {
    "guidance": "CAS 13 或有事项：未决诉讼/担保等潜在义务的披露要求..."
  },
  "A5-4": {
    "guidance": "CAS 42 持续经营：终止经营的认定标准及利润拆分规则..."
  }
}
```

## Testing Strategy
- 确认 A5-1~A5-4 正常打开（audit-sheet 或 univer）
- A5-4 公式计算正确
- guidance 展示
