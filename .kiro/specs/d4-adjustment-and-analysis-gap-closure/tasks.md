# Tasks — D4-4/8/12 gap closure

- [ ] 1. C0模板/identity：只读核定D4-4/8/12真实sheet、区域、wp_id稳定身份并反向去重owner；记录已有能力，不重做。
  - _Requirements: 1.1, 1.2, 8.1_
- [ ] 2. C1sync：为确认纳管表接入共享服务、字段合并、同字段冲突和applied确认。
  - _Requirements: 2.1, 2.2_
- [ ] 3. C2formula：冻结wp_id公式key、preset/custom、F-SHELL、真实DAG及缺失/损坏/stale/blocked。
  - _Requirements: 2.3_
- [ ] 4. C3linkage：保留已有A13/调整、产品计算、合同OCR/AI，只补真实联动接收端；公式同步不发布TB/A13。
  - _Requirements: 2.4, 3.2_
- [ ] 5. C4逐表验收与变异：roundtrip、权限、Playwright、owner去重、公式/冲突和发布确认；只门控本spec相关产物。
  - _Requirements: 3.1, 3.2_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"C0先核定模板与owner"},{"wave":2,"tasks":["2","3"],"rationale":"sync与formula并行"},{"wave":3,"tasks":["4"],"rationale":"linkage依赖前序契约"},{"wave":4,"tasks":["5"],"rationale":"C4最后"}],"blocking":{"1":"未核定不得新增owner","2":"sync未冻结不得roundtrip","3":"formula未冻结不得接入公式"}}
```
