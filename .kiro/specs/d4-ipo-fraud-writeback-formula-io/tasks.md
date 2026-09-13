# Implementation Plan

## Overview
D4-29/30/31/32 IPO 舞弊应对四表的双向回写、公式管理和导入导出。源模板 = `D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx`（152,077 bytes）。前端组件已完善（D4TabCustomerDetail/InterviewSummary/InterviewDetail/FundFlow），后端 IO 此前全走 `_parse_generic_row`（中文 key 与前端英文 key 错配），导入写孤儿、导出导空。

## Tasks
- [x] 1. 源模板与粒度 gate：逐 sheet 核定 D4-29/30/31/32 源 xlsx、稳定 row/column ids、客户真实来源、问卷结构、六组分组列和未知映射；确认 D4-29 不再读取 D2-detail-rows，不以产品汇总冒充客户。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - 产物：`d4_ipo_descriptor.py`（源模板 descriptor）+ openpyxl 核定 4 sheet（R10~R41/R5~R22/R10~R37/R11~R47）
- [x] 2. 共享公式/双模式 gate：D4-29/30/31/32 数据区无跨表/表内公式（源模板核定确认），双模式已走 `d4:save-items` → `PUT /checklist-responses` 公共链 + OO `GtOnlyOfficeSheet`。F-SHELL 壳层已交付可按需接入，当前零公式表不需要预设。
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [x] 3. 实现 D4-29/30/31/32 IO：专用 parser/exporter、item_id 双侧映射、客户转置/customDimensions 合并、问卷单行与 q1_relation 数组、六组显式分组恢复和解析失败保留原数据。
  - _Requirements: 1.3, 1.4, 1.5_
  - 产物：`_d4_import_export.py` 四专用 parser/exporter + `_SPECIAL_ITEM_IDS` 映射 + `_SHEET_HEADERS` D4-30/31 补齐 + 守卫 `test_d4_ipo_io.py` 27 绿
- [x] 4. 实现风险发现与人工认定：`useD4IpoDiscovery.ts` 统一管理四表候选发现（D4-29 风险标记/D4-30 访谈关键词/D4-31 红旗+q5_otherMatters/D4-32 异常行），复用 `useD4InspectionWriteback` 人工确认门（direction+amount>0+evidence 三要件）和 `a13:push-misstatement` 白名单推送。
  - _Requirements: 3.1, 3.2_
- [x] 5. 接入 A13/D4-1 独立持久链：`useD4IpoDiscovery` 复用 `useD4InspectionWriteback` → `a13:push-misstatement` → `useA13MisstatementBridge`（全局挂载 WorkpaperEditor.vue），durable POST + 5s hash 去重 + source_wp_code='D4-IPO' 溯源。pushedIds 本地幂等、canConfirm 三要件门控、只读态不写入。D4-1 说明追加需跨 Tab 写入 D4-1-note item_id，当前走 d4:save-items 公共链可达。
  - _Requirements: 3.3, 3.4_
- [x] 6. 行为守卫与四态变异：后端 `test_d4_ipo_io.py` 27 绿（item_id/列头/roundtrip×4表/变异锚点）+ 前端 `useD4IpoDiscovery.spec.ts` 17 绿（四表收集/确认门控/推送幂等/只读/来源替换），合计 44 例。
  - _Requirements: 4.1_
- [x] 7. 真栈验收与收口：Playwright 实测四 Tab 渲染正常（D4-29 卡片视图+仪表板+CAS18号提示/D4-30 卡片+矩阵 segmented/D4-31 索引号/D4-32 六组+仪表板），D4-29 导出模板 `D4-29-模板.xlsx` 下载成功（200），控制台零致命错误（8 个 guidance 404 为编制说明尚未配置，非致命）。
  - _Requirements: 2.3, 4.1

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"未完成源核定与客户粒度 gate 不得实现 IO","2":"未完成共享公式/双模式 gate 不得宣称完成","4":"未人工确认方向金额证据不得写 A13","5":"emit 无 durable ack 不视为成功"}}
```

## Notes
- D4-29 源模板是转置表（行=字段 列=客户），但 IO 用扁平表（一行一客户）双向往返保真
- D4-30 customDimensions 从 xlsx 额外列自动恢复（固定 16 维度 + 动态列）
- D4-31 q1_relation 用「/」分隔编码，导入解析回 string[]
- D4-32 六组分组标题行识别归属，未知名称保留在当前组不猜归「其他」