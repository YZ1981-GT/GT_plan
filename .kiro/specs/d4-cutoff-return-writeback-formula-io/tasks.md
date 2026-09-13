# Implementation Plan

## Tasks
- [ ] 1. 源模板核定 gate：逐 sheet 核定 D4-17/18/19/20 列头、六区结构、item_id、稳定 id、日期方向与空/零/未知边界；删除或显式拒绝 D4-20 死配置。
  - _Requirements: 1.1, 1.4, 3.1_
- [ ] 2. 共享公式/双模式 gate：接入 F-SHELL expression/refs/params/scope、后端权威执行与前端同定义预览，统一 mutation/sync/三方合并/ack/contract/representation。
  - _Requirements: 2.1, 2.2, 4.1_
- [ ] 3. 实现 D4-17/18/19/20 专用 IO 与公式：保持业务方向和六区结构，重算派生值、两侧 item_id、动态 id 和未知映射语义。
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.3_
- [ ] 4. 实现发现记录与人工确认门：跨期、折扣、退货、计提发现先留风险记录，人工确认方向/金额/证据后才形成 A13 请求。
  - _Requirements: 3.1, 3.2_
- [ ] 5. 接入 A13/D4-1 持久联动：复用共享件，落实 durable ack、幂等 source identity、D4-1 去重追加、独立重试和防回环。
  - _Requirements: 3.3_
- [ ] 6. 守卫与变异：验证专用 IO、item_id 双侧一致、截止非跨期语义、未知边界、公式同定义及四态变异。
  - _Requirements: 4.1_
- [ ] 7. 真栈验收与收口：Playwright 实测 HTML/Excel 往返、三方合并、ack 失败恢复、A13/D4-1 独立重试，并完成 spec 结构与产物检查。
  - _Requirements: 2.2, 4.1_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"源模板未核定不得实现 IO","2":"共享 gate 未满足不得宣称双模式完成","4":"未人工确认不得写 A13","5":"无 durable ack 不视为成功"}}
```