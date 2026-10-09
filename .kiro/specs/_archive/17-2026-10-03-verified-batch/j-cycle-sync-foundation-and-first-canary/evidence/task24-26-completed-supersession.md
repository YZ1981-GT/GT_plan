# Task 24/26 完成证据（取代 task24-26-blocked.md）

> `task24-26-blocked.md` 是 2026-09-27 的历史阻塞快照，保留不改；本文件是后续解除阻塞后的当前证据。

## Task 24 — 真 OnlyOffice 两轮往返

- 生产脚本：`backend/scripts/e2e/verify_j1_oo94_roundtrip.py`
- 必填目标：`--project-id` + `--wp-id`，精确命中 J1 current entry_state，禁止 `.first()` 随机选项目。
- 输入：前端单一来源 `j1AccrualSkeleton.json`；脚本逐字节对账模板 A17:A35，不再从模板自造必等输入。
- active 门：current representation → approved bundle → authority/template/instrumentation/contract digest 全等于当前 provider；权威与 active frozen template 均零 externalLinks。
- 两轮：真实前端 19 行骨架 + 带金额 19 行；OO ConvertService xlsx→xlsx；extract/G1/merge/公式/输入/DB 不变全部验证。
- 变异：`J1_RT_LEGACY_IDS=1` 必须在 merge 阶段复现 38 行失败。
- 机器证据：follow-up spec `evidence/oo94.json`，含 source commit、project/wp、generation、bundle/digest、OO 版本。

## Task 26 — reviewed contract 与 approved bundle

- contract 的 `review_status=reviewed` 是代码审阅状态；不再称“自动 provisioning 等于人工审核”。
- task76 产生 approved definition/bundle；first-publication 绑定 current representation。
- 真实 PG 运行后由 `oo94.json` 的 active digest 证明 current 指针使用当前 bundle，而非历史净化前 bundle。

## Supersession 规则

当 source digest、contract/instrumentation/template digest、active bundle、project/wp 或 OO 版本任一变化，旧 evidence 立即 stale，必须重跑；不得只改 status 文本。