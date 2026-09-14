# Implementation Plan

## Tasks
- [ ] 1. 源模板核定与稳定 ID gate：逐 sheet 读取源 xlsx，核定 D4-13/14/15/16 列头、嵌套结构、item_id、动态 id、未知映射、日期/空零未知三态与文本 N/A。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1_
- [ ] 2. 共享公式与双模式 gate：接入 F-SHELL preset/custom expression/refs/params/scope；后端权威执行、前端同定义预览；接入统一 mutation、sync、三方合并、contract、representation 与 durable ack，解析失败保留原值。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.2_
- [ ] 3. 实现 D4-13/15/16 IO：专用 parser/exporter、嵌套/英文 key 对齐、D4-13 双 item 文本锚点、D4-15 `D4-15-items`、D4-16 差异重算与动态 id 保留。
  - _Requirements: 1.2, 1.3, 1.4, 1.5_
- [ ] 4. 实现发现到人工认定的业务链：四表发现记录、方向/金额/证据确认 UI、来源追溯；确认前不得构造 A13 写入金额。
  - _Requirements: 3.1, 3.2, 3.4_
- [ ] 5. 接入 A13 与 D4-1 独立持久链：复用 `useD4InspectionWriteback` 和白名单事件，实现 durable ack、source identity 幂等、D4-1 去重追加、独立重试与防回环。
  - _Requirements: 3.3, 3.4_
- [ ] 6. 行为守卫与变异检验：覆盖 item_id/结构/未知映射/三态/方向互斥、后端与前端同定义执行及四态变异结果。
  - _Requirements: 4.1, 4.2, 5.1_
- [ ] 7. 真栈验收与收口：Playwright 真实 HTML/Excel 双向往返、三方合并、ack 成功/失败恢复、A13 与 D4-1 独立重试；最后完成 spec 校验与产物登记。
  - _Requirements: 2.3, 5.1, 5.2

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"未完成源核定不得实现 IO","2":"未完成共享公式/双模式 gate 不得宣称完成","4":"未人工认定不得进入 A13","5":"无 durable ack 不得视为写入成功"}}
```