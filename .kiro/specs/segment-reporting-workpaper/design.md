# 经营分部审定表 Design

## Overview

A4-1 经营分部审定表使用 `audit-sheet` componentType 渲染，扩展支持动态列 + 准则说明 tooltip。

## componentType

A4-1 当前走 class_code `F-审定表` → `audit-sheet`。不新增 componentType，复用现有 audit-sheet 框架。

## 扩展设计

### 动态分部列
audit-sheet 现有列结构是固定的（从模板解析）。A4-1 需要动态列：
- 用 `parsed_data.segment_columns` 存用户自定义分部名称
- 前端 audit-sheet 组件检测到 `segment_columns` 时渲染动态列

```json
// working_paper.parsed_data
{
  "segment_columns": ["软件分部", "电子器件分部"],
  "segment_data": {
    "current": {
      "revenue": {"软件分部": 5000000, "电子器件分部": 3000000, "other": 200000, "elimination": -100000},
      "cost": {...},
      "profit": {...}
    },
    "prior": {...}
  }
}
```

### 准则说明 Guidance
在 render-config 返回的 html_data 中附带 guidance：
```json
{
  "guidance_items": [
    {
      "section": "分部利润",
      "reference": "解释3号\"八(三)\"2",
      "content": "每一报告分部的利润(亏损)总额相关信息，包括利润(亏损)总额组成项目及计量的相关会计政策；"
    },
    {
      "section": "分部资产负债",
      "reference": "解释3号\"八(三)\"3",
      "content": "每一报告分部的资产总额、负债总额相关信息，包括资产总额组成项目的信息，以及有关资产、负债计量的相关会计政策。"
    },
    {
      "section": "产品劳务收入",
      "reference": "解释3号\"八(四)\"1",
      "content": "每一产品和劳务或每一类似产品和劳务组合的对外交易收入；"
    },
    {
      "section": "地区信息",
      "reference": "解释3号\"八(四)\"2",
      "content": "企业取得的来自于本国的对外交易收入总额以及位于本国的非流动资产总额，企业从其他国家取得的对外交易收入总额及位于其他国家的非流动资产总额"
    },
    {
      "section": "主要客户",
      "reference": "解释3号\"八(四)\"3",
      "content": "企业对主要客户的依赖程度。"
    }
  ]
}
```

前端在每个 section 标题旁渲染 ⓘ tooltip 展示 guidance。

## Testing Strategy
- A4-1 正常打开为 audit-sheet
- guidance tooltip 正确展示准则引用
- 动态列增删+数据保存
