# Implementation Plan

## Tasks
- [x] 1. 源模板与粒度 gate：逐 sheet 核定 D4-29/30/31/32 源 xlsx、稳定 row/column ids、客户真实来源、问卷结构、六组分组列和未知映射；确认 D4-29 不再读取 D2-detail-rows，不以产品汇总冒充客户。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
- [x] 2. 共享公式/双模式 gate：接入 F-SHELL expression/refs/params/scope 与后端权威执行；统一 mutation/sync/三方合并/contract/representation/durable ack，覆盖 0/0、prior=0、空零未知。
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [x] 3. 实现 D4-29/30/31/32 IO：专用 parser/exporter、item_id 双侧映射、客户转置/customDimensions 合并、问卷单行与 q1_relation 数组、六组显式分组恢复和解析失败保留原数据。
  - _Requirements: 1.3, 1.4, 1.5_
- [x] 4. 实现风险发现与人工认定：高风险客户、访谈红旗、异常流水先保留发现；D4-31 findings/q5_otherMatters 留痕；人工确认方向/金额/证据后才产生 A13 请求。
  - _Requirements: 3.1, 3.2_
- [x] 5. 接入 A13/D4-1 独立持久链：复用共享件和白名单事件，实现 durable ack、幂等 source identity、说明去重、独立重试、防回环与只读门控。
  - _Requirements: 3.3, 3.4_
- [x] 6. 行为守卫与四态变异：覆盖真实客户来源、item_id、矩阵/问卷/分组结构、未知映射、公式三态、A13 人工门和双模式同定义执行。
  - _Requirements: 4.1_
- [~] 7. 真栈验收与收口：Playwright 实测 HTML/Excel 双向往返、三方合并、ack 成功/失败恢复、D4-1 独立重试；完成 spec 结构与产物检查。
  - _Requirements: 2.3, 4.1_
  - D4-29 生命周期修复重开：已补真实组件挂载测试 5 项（保存等待、保存失败与重试、oo_editing 切回矩阵、回读失败保留编辑器、结论独立刷新）；与同步桥/API 合跑 122 passed。移除 flush await 后，保存时序测试按预期 RED，恢复后全绿。
  - 浏览器验收未完成：已登录并打开重庆和平药房项目 D4-29；点击内部在线编辑后 store-projection 请求尚未取得响应，未进入实际 Excel 往返。页面同时存在内外两套模式入口及「两侧数据未互通」提示，仍需继续排查。浏览器验收由本任务继续负责，不交由用户代验。

- [ ] 8. D4-30/31/32 接入统一同步桥与受管 provider；未注册能力保持阻塞态，不修改 D4-29。
  - Requirements: 5.1, 6.1, 6.2
- [ ] 9. D4-32 unknown 组保真与人工映射：保留 label/id/金额三态/账号中文，非法 JSON 和保存失败保留旧数据并显示错误。
  - Requirements: 5.2, 5.3

## Task Dependency Graph```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"未完成源核定与客户粒度 gate 不得实现 IO","2":"未完成共享公式/双模式 gate 不得宣称完成","4":"未人工确认方向金额证据不得写 A13","5":"emit 无 durable ack 不视为成功"}}
```

## D4-29 根因修复续作
- [ ] 10. 冻结稳定转置 sheet 锚、编译注入、发布/请求共享物理观测及完整性门禁；空客户、缺失/重复/公式身份防御测试。
- [ ] 11. 合法升级 representation 后完成真实 HTML -> OO -> callback -> HTML 往返，记录 revision 和 operation；不得用模拟 callback 验收。
- 复现记录：专用测试 1 failed / 6 passed，当前 provider 关闭 D429 导致 instrumentation digest 与磁盘 contract 不一致。尚未修改冻结记录，真实 OO 验收未完成。

### Task 3 live preflight (2026-09-13)
Blocked, not accepted: see task3-live-blocker.md. D429 source switch is False and Task76 contract differs from task-2 handoff. Template candidate rejects 2051B nonempty store; authenticated store-projection returns HTTP500. No legal upgrade or actual OO callback achieved. Task 11 remains unchecked.
