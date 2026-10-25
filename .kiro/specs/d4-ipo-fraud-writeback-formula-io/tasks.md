# Implementation Plan

## Tasks
- [ ] 1. 源模板与粒度 gate：逐 sheet 核定 D4-29/30/31/32 源 xlsx、稳定 row/column ids、客户真实来源、问卷结构、六组分组列和未知映射；确认 D4-29 不再读取 D2-detail-rows，不以产品汇总冒充客户。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
- [ ] 2. 共享公式/双模式 gate：接入 F-SHELL expression/refs/params/scope 与后端权威执行；统一 mutation/sync/三方合并/contract/representation/durable ack，覆盖 0/0、prior=0、空零未知。
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [ ] 3. 实现 D4-29/30/31/32 IO：专用 parser/exporter、item_id 双侧映射、客户转置/customDimensions 合并、问卷单行与 q1_relation 数组、六组显式分组恢复和解析失败保留原数据。
  - _Requirements: 1.3, 1.4, 1.5_
- [ ] 4. 实现风险发现与人工认定：高风险客户、访谈红旗、异常流水先保留发现；D4-31 findings/q5_otherMatters 留痕；人工确认方向/金额/证据后才产生 A13 请求。
  - _Requirements: 3.1, 3.2_
- [ ] 5. 接入 A13/D4-1 独立持久链：复用共享件和白名单事件，实现 durable ack、幂等 source identity、说明去重、独立重试、防回环与只读门控。
  - _Requirements: 3.3, 3.4_
- [ ] 6. 行为守卫与四态变异：覆盖真实客户来源、item_id、矩阵/问卷/分组结构、未知映射、公式三态、A13 人工门和双模式同定义执行。
  - _Requirements: 4.1_
- [ ] 7. 真栈验收与收口：Playwright 实测 HTML/Excel 双向往返、三方合并、ack 成功/失败恢复、D4-1 独立重试；完成 spec 结构与产物检查。
  - _Requirements: 2.3, 4.1

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"未完成源核定与客户粒度 gate 不得实现 IO","2":"未完成共享公式/双模式 gate 不得宣称完成","4":"未人工确认方向金额证据不得写 A13","5":"emit 无 durable ack 不视为成功"}}
```