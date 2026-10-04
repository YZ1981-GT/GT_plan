# D4-4/8/12调整与分析遗漏闭环

## Introduction
本spec仅承接总纲矩阵明确owner为本spec的D4-4、D4-8、D4-12。三者已有结构化能力不重做：D4-4保留调整/A13/集中调整，D4-8保留产品×月计算与持久化，D4-12保留合同卡片、OCR、AI和导入导出；本spec只补双向identity、公式/DAG、冲突和逐表验收。

## Requirements
### Requirement 1 — owner与源核定
1. SHALL 通过wp_template_finder/索引及权威D4模板逐表确认D4-4/8/12的sheet、区域和目标；无法核定记UNVERIFIABLE。
2. 若任一表已有明确owner，必须从本spec移除，不得重复立项。
### Requirement 2 — 集成契约
1. 经总纲协议接入ContentMutationService/useWorkpaperSyncBridge；不同字段自动合并，同字段保留三方冲突轨迹。
2. durable ack不等于applied；只有canonical rematerialize和content version确认才算应用。
3. 公式key使用`wp_id + stable_sheet_key + row_key + field_key + custom`；preset升级保留custom，删除custom恢复preset；缺失/损坏/stale/blocked分态，schema白名单禁eval和外链。
4. 公式同步不是TB/A13；TB/A13需显式确认。
### Requirement 3 — 验收
1. 每个确认纳管wp_code必须具备source evidence、contract、roundtrip、DAG、权限和Playwright证据。
2. 风险发现不自动发布；TB/A13需显式幂等durable ack，模式切换不发布。
