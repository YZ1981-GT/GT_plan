# Tasks — D4双模式公式治理与36底稿覆盖

- [-] 1. C0模板/identity：建立D4-1..36 owner矩阵，逐项读取finder索引及权威源模板；D4-4/8/12按已有能力只收口缺口，不重复已有owner。
  - _Requirements: 1.1, 1.2, 1.3, 8.1_
- [~] 2. C1sync：冻结共享协议、字段级自动合并、同字段冲突轨迹、durable ack/applied及canonical refresh。
  - _Requirements: 2.1, 2.2, 2.3_
- [~] 3. C2formula：冻结wp_id公式key、preset/custom、F-SHELL、schema白名单、CAS和缺失/损坏/stale/blocked。
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
- [~] 4. C3linkage：冻结真实DAG、单writer、联动接收端及TB/A13显式发布边界。
  - _Requirements: 4.1, 4.2, 5.1_
- [~] 5. C0-C3 platform contracts：冻结导入identity、四表复用、权限/CAS、幂等迁移；只覆盖相关产物。
  - _Requirements: 5.2, 6.1, 7.1_
- [~] 6. C4逐表验收：登记36行source/contract/roundtrip/formula-conflict/permission/Playwright状态，UNVERIFIABLE不得假绿。
  - _Requirements: 8.1_
- [~] 7. C4行为守卫和变异：验证矩阵、三方合并、公式边界、真实DAG和发布确认。
  - _Requirements: 2.2, 3.2, 4.2, 5.1_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"C0先核定矩阵与模板"},{"wave":2,"tasks":["2","3"],"rationale":"C1/C2可并行冻结"},{"wave":3,"tasks":["4","5"],"rationale":"C3与平台契约依赖C1/C2"},{"wave":4,"tasks":["6"],"rationale":"C4逐表验收依赖前序契约"},{"wave":5,"tasks":["7"],"rationale":"行为守卫最后执行"}],"blocking":{"1":"owner/template未核定不得冻结矩阵","2":"sync未冻结不得声明applied","3":"formula未冻结不得接入公式"}}
```
