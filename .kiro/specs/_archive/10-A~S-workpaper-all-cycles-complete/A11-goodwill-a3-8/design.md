# 商誉减值+可收回金额测试 Design

## Overview

P0 阶段：A3-8/A3-8-1 走 Univer 渲染（保留 xlsx 原始公式+格式），编制说明以侧栏面板展示。P1 阶段：结构化渲染+WACC 自动计算引擎。

## P0 设计（Univer + 编制说明面板）

### componentType 路由
- A3-8 当前走 class_code 匹配（可能是 F-审定表 → audit-sheet 或 univer）
- 不需要新建 componentType，保持 Univer 渲染
- 编制说明通过底稿编辑器的侧栏 guidance 面板展示

### 编制说明数据
存储在 `wp_templates/A/` 目录下的模板文件中（已有）。后端在 render-config 中提取编制说明 sheet 内容返回给前端。

### 前端展示
在 WorkpaperEditor 的侧栏（已有 guidance 机制）展示 A3-8-1 的编制说明：
- 6 条规则 + WACC/CAPM 公式 + 参数定义
- 折叠面板形式，用户可展开查阅

## P1 设计（结构化渲染，未来实施）

### 新建 componentType: `goodwill-impairment`
- A3-8 → 减值测试表组件
- A3-8-1 → 可收回金额计算组件（含 DCF 引擎）

### WACC 计算引擎
```python
def calculate_wacc(d, e, kd, ke, tax_rate):
    return (d * kd * (1 - tax_rate) + e * ke) / (d + e)

def calculate_ke(rf, beta, rm):
    return rf + beta * (rm - rf)

def calculate_dcf(cash_flows, wacc, terminal_growth_rate):
    pv_sum = sum(cf / (1 + wacc)**n for n, cf in enumerate(cash_flows, 1))
    tv = cash_flows[-1] * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    pv_tv = tv / (1 + wacc)**len(cash_flows)
    return pv_sum + pv_tv
```

## Testing Strategy
- P0：确认 Univer 渲染正常 + 编制说明面板显示
- P1：WACC/DCF 计算引擎单测 + 前端组件渲染
