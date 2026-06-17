# 经营分部审定表 Design

## Overview

P0：A4-1 走 Univer 渲染（保留动态列+公式），准则说明以侧栏/hover 展示。P1：结构化 audit-sheet 组件+动态分部列。

## P0 设计

### 路由
- A4 走 `a-program-console`（已有）
- A4-1 走 Univer（F-审定表 或默认 xlsx 渲染）
- 无需新建 componentType

### 准则说明展示
在 WorkpaperEditor 侧栏 guidance 面板展示 A4-1 的蓝色准则引用内容：
- 解释3号"八(三)"：分部利润/资产/负债的列报要求
- 解释3号"八(四)"：产品劳务/地区/客户信息的列报要求
- 以折叠面板形式组织，分 3 个折叠块

### 数据来源
准则说明内容从模板 xlsx 中提取（蓝色字体行）或硬编码为 JSON。

## P1 设计（结构化渲染）

### componentType: `segment-report`
- 动态列名管理（添加/删除/重命名分部）
- 合计列自动求和
- 本期/上期切换 Tab
- 地区信息交叉表
- 主要客户列表

## Testing Strategy
- P0：Univer 渲染正常 + guidance 面板显示准则说明
- P1：动态列增删 + 合计计算 + 准则 hover
