# Tasks — D4双模式公式治理与36底稿覆盖

- [x] 1. C0模板/identity：建立D4-1..36 owner矩阵，逐项读取finder索引及权威源模板；D4-4/8/12按已有能力只收口缺口，不重复已有owner。
  - 产物：`backend/data/d4_owner_matrix.json`（36 行单一真源）+ `backend/scripts/check/check_d4_owner_matrix.py --check`（分母/owner/gap/own/模板证据/design 五向锁死 + 反向自检）+ `backend/tests/d4_governance/test_d4_owner_matrix.py`（12 例，含 5 条变异检验）。守卫与测试全绿。
  - _Requirements: 1.1, 1.2, 1.3, 8.1_
- [x] 2. C1sync：冻结共享协议、字段级自动合并、同字段冲突轨迹、durable ack/applied及canonical refresh。
  - 产物：`backend/data/d4_sync_contract_frozen.json`（引用真实 ContentMutationService + useWorkpaperSyncBridge，锁 durable-ack≠applied / 三方合并 / 模式切换不发布）+ `backend/scripts/check/check_d4_sync_contract.py --check`（反 fiction：所有引用符号命中源码 + applied 在 in-flight 集合的结构判据）+ 契约测试（含变异反向自检）。全绿。
  - _Requirements: 2.1, 2.2, 2.3_
- [x] 3. C2formula：冻结wp_id公式key、preset/custom、F-SHELL、schema白名单、CAS和缺失/损坏/stale/blocked。
  - 产物：`backend/data/d4_formula_contract_frozen.json`（五元键 wp_id+stable_sheet_key+row_key+field_key+custom；preset/custom/effective/missing/corrupted/stale/blocked 七态；引用 user_formula_v2 CAS+audit门 / workpaper_capability fail-closed / F-SHELL 白名单 / prefill preset；**如实登记 SSOT 持久化缺口 = in-memory，归属 D4-1 owner spec**）+ `backend/scripts/check/check_d4_formula_contract.py --check`（含「引擎仍是 in-memory 才允许 persisted=false」的双向缺口守卫）+ 契约测试。全绿。
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
- [x] 4. C3linkage：冻结真实DAG、单writer、联动接收端及TB/A13显式发布边界。
  - 产物：`backend/data/d4_linkage_platform_contract_frozen.json`（real_dag no-cycle 守卫 / 单 writer=render prefill / TB-A13 显式发布 publishAdjudicated 走独立 d4:writeback channel）+ `backend/scripts/check/check_d4_linkage_platform_contract.py --check`。全绿。
  - _Requirements: 4.1, 4.2, 5.1_
- [x] 5. C0-C3 platform contracts：冻结导入identity、四表复用、权限/CAS、幂等迁移；只覆盖相关产物。
  - 产物：同 `d4_linkage_platform_contract_frozen.json`（import_identity=D4 positional-array roundtrip + useD4ImportExport + per-field 稳定键；four_table_reuse=ReportLineAccountSpec + build_d4_tb_values 真 import four_table；permission_cas=workpaper_capability + baseVersion；idempotent_migration=MigrationRunner + IF NOT EXISTS）。守卫核对消费者真 import four_table（反「复制 SQL」）。全绿。
  - _Requirements: 5.2, 6.1, 7.1_
- [x] 6. C4逐表验收：登记36行source/contract/roundtrip/formula-conflict/permission/Playwright状态，UNVERIFIABLE不得假绿。
  - 产物：`backend/data/d4_c4_acceptance_registry.json`（36 行六维；GREEN=39/OWNER=173/UNVERIFIABLE=4）+ `backend/scripts/check/check_d4_c4_acceptance.py --check`（owner 与矩阵锁死 + playwright 禁 GREEN 假绿 + D4-1 own 四维必 GREEN/playwright 必 UNVERIFIABLE）。全绿。
  - _Requirements: 8.1_
- [x] 7. C4行为守卫和变异：验证矩阵、三方合并、公式边界、真实DAG和发布确认。
  - 产物：`backend/tests/d4_governance/test_d4_c4_and_behavior_guards.py`（五守卫全绿 + C4 登记 + 5 条行为变异：分母守恒/三方合并/公式白名单+危险token黑名单/真实DAG no-cycle/显式发布）。39 例全绿（连同前两组共 64 例）。
  - _Requirements: 2.2, 3.2, 4.2, 5.1_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"C0先核定矩阵与模板"},{"wave":2,"tasks":["2","3"],"rationale":"C1/C2可并行冻结"},{"wave":3,"tasks":["4","5"],"rationale":"C3与平台契约依赖C1/C2"},{"wave":4,"tasks":["6"],"rationale":"C4逐表验收依赖前序契约"},{"wave":5,"tasks":["7"],"rationale":"行为守卫最后执行"}],"blocking":{"1":"owner/template未核定不得冻结矩阵","2":"sync未冻结不得声明applied","3":"formula未冻结不得接入公式"}}
```
