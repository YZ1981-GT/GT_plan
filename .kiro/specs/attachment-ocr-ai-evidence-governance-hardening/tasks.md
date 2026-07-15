# Implementation Plan: 附件、OCR、AI 与证据链治理加固

## Overview

本计划以 `requirements.md` 与 `design.md` 为唯一基线，采用 additive strangler 路径，只新增治理 facade、持久模型、typed adapter、状态机、统一门禁、统一依赖图输入、manifest、迁移与验证体系；复用 `AttachmentService`、`UnifiedOCRService`、`KnowledgeIndexService`、`AiContentLog`、ACNR、`StalePropagationEngine`、deliverable center、`ArchiveOrchestrator`，不得复制、分叉或影子实现。共 55 个必做叶子任务、11 个 wave；没有 optional 或仅询问用户的 checkpoint。

常规 PBT 统一使用 `backend/tests/conftest.py` 全局 `fast` profile（默认 `max_examples=5`，可由 `HYPOTHESIS_MAX_EXAMPLES` 覆盖）；nightly/release 通过独立 profile/env 提高样本数。不得在测试正文固定 100 例。PG enum/check/partial unique/复合 FK/deferrable/immutable trigger、`FOR UPDATE`、并发去重、事务回滚、`SKIP LOCKED` 必须在真实 PostgreSQL 16 验证。

## Tasks

- [x] 1. Wave 0 — 冻结 P0 契约与既有引擎边界
  - [x] 1.1 实测并冻结七值 `SystemRole`、DB/JWT/ProjectAssignment 映射和 capability 矩阵，优先锁定 `retry-ocr` 权限、EQCR 独立角色、Service Identity 禁止人工确认以及任何角色均不能绕过 Legal Hold。
    - _Requirements: R1, R5, R6, R10, R13_
  - [x] 1.2 盘点所有 `file_path` 读写、下载、预览、导出和归档调用，冻结 Storage Boundary 先鉴权、opaque locator 兼容及“边界/权限失败时 open/stat/read=0”契约。
    - _Requirements: R1, R14_
  - [x] 1.3 实证并冻结 `created_by`/actor XOR、OCR enum/state、持久 EvidenceRef 物理模型和 legacy ID 解析契约，禁止匿名记录、DTO-only 引用和 old ID=新聚合根假设。
    - _Requirements: R1, R3, R5, R14_
  - [x] 1.4 建立跨项目 working-paper/attachment 关联否决基线，锁定同 project/year、双端权限、脱敏错误和失败零部分写入；四项校验只在创建关联时按需执行。
    - _Requirements: R3, R4_
  - [x] 1.5 为八项既有引擎建立 adapter contract 与禁止分叉 CI 清单，并冻结 API、幂等键、expected-version、错误码、ActorContext、canonical JSON/hash 契约。
    - _Requirements: R1, R5, R7, R8, R9, R11, R12, R15_

- [x] 2. Wave 1 — 动态迁移与 PostgreSQL 治理模型
  - [x] 2.1 通过现有 migration status 与目录扫描动态分配下一可用 V；状态不一致即停止，迁移保持 additive、可重复检测且不删除 legacy 列。
    - _Requirements: R14_
  - [x] 2.2 创建 `UploadAttempt`、Attachment/AttachmentVersion、quarantine/staging、ServiceIdentity 与 actor 模型；实现失败尝试最小审计、复合 scope FK、循环 FK 分阶段添加及 immutable trigger。
    - _Requirements: R1, R2, R12, R13_
  - [x] 2.3 创建 `legacy_attachment_alias`、持久 EvidenceRef/EvidenceDependency、活动 intent partial unique、canonical edge hash 与双向索引。
    - _Requirements: R3, R4, R9, R14_
  - [x] 2.4 创建 OCR Job/Transition/Result/Confirmation/Writeback、Citation/AI 扩展、Review snapshot、audit/outbox/inbox、Archive Manifest、Legal Hold、checkpoint/quality snapshot 模型。
    - _Requirements: R5, R6, R7, R8, R10, R11, R12, R13, R16_
  - [x] 2.5 同步 ORM/Pydantic/enum，执行真实 PG16 空库、历史库、中断重跑、schema drift、actor/人工 FK、复合约束和 trigger 契约测试。
    - _Requirements: R1, R2, R3, R5, R6, R11, R13, R14_

- [x] 3. Wave 2 — Facade、上传审计、隔离与安全读取
  - [x] 3.1 实现 `EvidenceGovernanceFacade`、ProjectYearScopeGuard、CapabilityGuard、command-root/outbox/inbox；业务变化、审计根和 outbox 同事务，router 不提交、service 只 flush。
    - _Requirements: R1, R3, R4, R5, R8, R12_
  - [x] 3.2 实现每次上传先建最小 `UploadAttempt`，记录 project/year、清洗文件名、声明/安全识别实际类型、已得 bytes/hash、actor、时间与 validation outcome；验证失败更新同一 attempt。
    - _Requirements: R1, R12_
  - [x] 3.3 实现固定块流式 hash/MIME/大小/恶意内容检查、背压和 staged→finalize；无效或恶意内容不得创建可用 Attachment/Version，隔离内容不可访问并按策略删除或加密擦除。
    - _Requirements: R1, R2, R15_
  - [x] 3.4 实现读取拒绝链：scope/权限/边界先于字节 I/O；即使通过，也在存储不可用、integrity 失败、quarantined、malware/readability gate 失败时拒绝且脱敏审计。
    - _Requirements: R1, R12, R15_
  - [x] 3.5 实现父行 `FOR UPDATE` 版本递增、旧版本不可变、影响确认、legacy resolver 与旧路由 facade 委托；`file_path` 仅返回 opaque locator/受控 URL。
    - _Requirements: R2, R9, R13, R14_

- [x] 4. Wave 3 — EvidenceRef、按需关联与统一动态边
  - [x] 4.1 为底稿单元格、抽样项、凭证、函证、复核、附注、报告、AI、交付件和附件版本实现 typed adapter 的 resolve/read/edit/locate/lock 契约。
    - _Requirements: R3, R4, R6, R10_
  - [x] 4.2 实现 EvidenceRef 创建事务，在每次创建关联时按需校验源 scope、目标 scope、源端权限、目标端权限及目标版本/hash/状态；不得建立持续轮询，失败无 ref/edge/audit/outbox 半成品。
    - _Requirements: R3, R4, R12_
  - [x] 4.3 实现 intent 幂等、双向 cursor 查询、停用历史、活动 EvidenceDependency 与直接/传递影响 API；结果去重且仅含当前 scope/actor 可读对象。
    - _Requirements: R3, R4, R9, R15_
  - [x] 4.4 接入附件/底稿证据关系抽屉、元数据完整门禁、版本/hash/actor/locator/影响路径展示及跨项目脱敏错误。
    - _Requirements: R2, R3, R4_
  - [x] 4.5 完成 EvidenceRef 后端 unit/integration/API contract：重启持久、双向一致、并发 intent 唯一、跨项目 wp 关联零变化和 metadata 不完整阻断。
    - _Requirements: R2, R3, R4, R12_

- [x] 5. Wave 4 — OCR 持久状态、人工确认与原子写回
  - [x] 5.1 实现 OCRGovernanceOrchestrator：在调用 `UnifiedOCRService` 前持久/复用绑定版本/hash/config/idempotency 的 OCRJob，保存 lease、attempt 与 transition。
    - _Requirements: R5, R12, R15_
  - [x] 5.2 实现封闭 OCR enum/state CAS 与 `ocr.retry` 权限、有界退避、超限失败、重启恢复和重复调度抑制；越权重试零副作用。
    - _Requirements: R5, R12, R15_
  - [x] 5.3 实现 immutable OCRResult 与 append-only accepted/corrected/rejected revision；全部 required 字段先 decided，rejected 永不进入 mapping，Service Identity 不得确认。
    - _Requirements: R6, R7, R12_
  - [x] 5.4 实现 OCRWritebackService：transactional-local 全字段+记录同事务；staged-external 以 staging/幂等消费/回执推进，目标或附件版本冲突时零变化。
    - _Requirements: R6, R9, R12, R15_
  - [x] 5.5 完成 OCR API、时间线、差异确认、冲突提示、写回 UI 与后端 unit/integration/contract、前端 Vitest，覆盖七角色及 service actor。
    - _Requirements: R5, R6, R12, R14_

- [x] 6. Wave 5 — RAG/AI、FormalOutput、stale 与复核闭环
  - [x] 6.1 适配 `KnowledgeIndexService` 并实现 immutable CitationSnapshot/locate：结果取同 scope、可读、active ref、版本/hash/locator 有效交集，保留 page/region，打开时重鉴权。
    - _Requirements: R7, R9, R15_
  - [x] 6.2 扩展 `AiContentLog` 与 AIEvidenceGate，统一登记所有生成/改写/摘要/补全入口；人工 confirm/revise/reject，coverage scanner 差集非空即阻断。
    - _Requirements: R8, R12, R15_
  - [x] 6.3 实现 FormalOutput preflight/finalize 双门禁，证据集合仅为策略必需证据与已有依赖；历史无附件不自动违规，外部依赖降级时 fail-closed。
    - _Requirements: R8, R9, R10, R11, R15_
  - [x] 6.4 实现唯一 UnifiedGraphBuilder 和 cursor 闭包 worker，合并活动 EvidenceDependency 与规范化 ACNR/legacy 边；复用 StalePropagationEngine，支持全入边清除和 degraded 阻断。
    - _Requirements: R4, R9, R11, R13, R15_
  - [x] 6.5 实现 ReviewEvidenceSnapshot/关闭门禁/自动重开及 QC/EQCR/partner 阻断，完成版本/hash/OCR-AI确认/stale path/locator UI 和相关 unit/integration/Vitest。
    - _Requirements: R9, R10, R12_

- [ ] 7. Wave 6 — Archive、离线验签、Legal Hold 与审计告警
  - [ ] 7.1 实现 ArchiveManifest 两阶段 watermark 与版本化 sealed 包；只有验证失败并阻断归档时生成完整 blocking difference report，成功归档不得生成阻断报告。
    - _Requirements: R11, R15_
  - [ ] 7.2 通过 adapter 接入 deliverable center/ArchiveOrchestrator，并实现不连接业务库的离线 manifest 成员/hash/签名验签器及机器可读差异。
    - _Requirements: R11_
  - [ ] 7.3 实现 Legal Hold 统一图闭包与新增边监听；删除、清理、覆盖对任何角色/管理员/紧急授权均零效果，只有 hold 解除且 retention 届满后才可授权 purge。
    - _Requirements: R2, R12, R13_
  - [ ] 7.4 实现不可变墓碑、审计保留、低基数指标、trace 与告警，覆盖 upload/ref/OCR/AI/citation/stale/review/archive/hold/outbox 且不记录原文或凭据。
    - _Requirements: R12, R13, R15, R16_
  - [ ] 7.5 完成 archive/hold 后端 unit/integration/contract 与 UI/Vitest，验证失败报告、成功无阻断报告、sealed 防覆盖、hold 无绕过及 purge 四条件。
    - _Requirements: R11, R12, R13_

- [ ] 8. Wave 7 — M0–M4、质量快照、真实 PG 与容量基础验证
  - [ ] 8.1 执行 M0 dark-read、M1 checkpoint backfill、M2 dual-write、M3 cutover、M4 retirement；未知 creator 用 migration identity，只补可证明字段，重跑幂等且 legacy 列保留。
    - _Requirements: R14, R16_
  - [ ] 8.2 建立 6000 VU 容量与 chaos 场景：30 分钟稳态+10 分钟突发、70/20/7/3 流量、PgBouncer/PG 配额、独立队列背压和 storage/OCR/retrieval/AI 故障。
    - _Requirements: R12, R15_
  - [ ] 8.3 汇总后端 unit/integration/API/component 测试，覆盖 scope、事务、幂等、worker crash/dead-letter、watermark 竞争、迁移中断与 fail-closed。
    - _Requirements: R1, R3, R5, R6, R8, R9, R11, R12, R14, R15_
  - [ ] 8.4 汇总前端 Vitest/component 与静态守卫，覆盖 capability 仅展示、上传/OCR/证据/stale/review/archive/hold 状态、AI coverage 和大列表错误恢复。
    - _Requirements: R1, R4, R5, R6, R7, R8, R9, R10, R11, R13, R15_
  - [ ] 8.5 运行真实 PG16 约束/并发/trigger/rollback/SKIP LOCKED、八引擎 adapter contract、迁移/ORM drift、离线验签和容量机器报告；SQLite/Playwright 不替代这些证据。
    - _Requirements: R1, R2, R3, R5, R6, R7, R8, R9, R11, R12, R13, R14, R15_

- [ ] 9. Wave 8 — 六领域合并 PBT（逐项覆盖 P1–P30）
  - [ ] 9.1 安全/附件引用属性组：逐项实现 P1 项目隔离、P2 存储边界、P3 actor 完备、P4 版本不可变、P5 哈希绑定、P6 Ref 完整性、P7 Ref 幂等、P8 双向一致，并保留失败 counterexample。
    - _Requirements: R1, R2, R3, R4, R11, R14_
  - [ ] 9.2 OCR 属性组：逐项实现 P9 状态机封闭、P10 重试授权、P11 原始结果不可变、P12 未确认不可写回、P13 写回原子性、P14 写回幂等性。
    - _Requirements: R5, R6_
  - [ ] 9.3 RAG-AI 属性组：逐项实现 P15 引用可定位、P16 权限不扩张、P17 AI 状态门禁、P18 入口覆盖、P19 已确认内容变更失效。
    - _Requirements: R7, R8, R9_
  - [ ] 9.4 stale-review 属性组：逐项实现 P20 统一图精确闭包、P21 Blocking Review 关闭门禁、P22 证据失效自动重开与 QC/EQCR 阻断。
    - _Requirements: R9, R10_
  - [ ] 9.5 archive-hold 属性组：逐项实现 P23 manifest 精确完备、P24 防覆盖、P25 command-root 唯一/transition 多条、P26 hold 三类操作无绕过、P27 hold 解除+retention 到期清理边界。
    - _Requirements: R11, R12, R13_
  - [ ] 9.6 migration-quality 属性组：逐项实现 P28 迁移幂等守恒、P29 降级安全、P30 固定快照质量指标可复算；P30 独立于 UAT-15。
    - _Requirements: R14, R15, R16_

- [ ] 10. Wave 9 — 五领域 Playwright UAT suite（逐项覆盖 UAT-01～15）
  - [ ] 10.1 安全接收 suite：逐项运行 UAT-01 上传先审计/无可用恶意文件、UAT-02 越界读取否决、UAT-03 跨项目关联否决；02/03 一票否决。
    - _Requirements: R1, R3, R4, R12_
  - [ ] 10.2 附件与引用 suite：逐项运行 UAT-04 版本/影响/stale、UAT-05 EvidenceRef 重启持久与双向查询。
    - _Requirements: R2, R3, R4, R9_
  - [ ] 10.3 OCR 与 RAG suite：逐项运行 UAT-06 Job 重启恢复、UAT-07 人工确认/原子写回、UAT-08 重试权限否决、UAT-09 精确引用/失效；08 一票否决。
    - _Requirements: R5, R6, R7, R9_
  - [ ] 10.4 AI、复核、归档与 Hold suite：逐项运行 UAT-10 AI 全入口门禁、UAT-11 QC/EQCR 再复核、UAT-12 失败才有 blocking report/成功离线验签、UAT-13 删除清理覆盖无绕过；13 一票否决。
    - _Requirements: R8, R9, R10, R11, R13_
  - [ ] 10.5 迁移与容量 suite：逐项运行 UAT-14 中断重跑/legacy alias/opaque locator、UAT-15 用户可见背压降级并关联 6000 VU chaos 报告；15 一票否决且不承接 P30。
    - _Requirements: R14, R15_

- [ ] 11. Wave 10 — 可执行最终发布门
  - [ ] 11.1 运行三件套追溯与完成守卫，确认 R1–R16、P1–P30、UAT-01～15、55 叶子任务、11 waves、dependency graph 无 missing/extra/duplicate，且无 optional/ask-user checkpoint。
    - _Requirements: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16_
  - [ ] 11.2 在预生产执行 migration health gate 与完整回滚演练：阻止失败迁移/无锁降级切 flag，验证停止新写、drain worker、暂停 backfill、兼容读回退且不删除治理对象。
    - _Requirements: R11, R12, R13, R14, R15_
  - [ ] 11.3 在历史增强启用前对固定不可变 snapshot 单独运行 P30，确认原始字节与业务结论不变，不以在线容量数据替代。
    - _Requirements: R16_
  - [ ] 11.4 执行最终发布门脚本并生成机器可读 release evidence：R1–R15、P1–P29、UAT-01～15、PG16、adapter contracts、AI coverage、offline manifest 验签、6000 VU、health/rollback 全绿后才更新实施状态并发起归档评审；否则保持待执行且阻断发布。
    - _Requirements: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16_

## Task Dependency Graph

下列 JSON 是唯一执行图。`tasks` 中每个未完成叶子恰好出现一次；wave 间依赖以前一 wave 的全部叶子完成为准，wave 内可并行。

```json
{
  "waves": [
    {"wave": 0, "tasks": ["1.1","1.2","1.3","1.4","1.5"], "depends_on": []},
    {"wave": 1, "tasks": ["2.1","2.2","2.3","2.4","2.5"], "depends_on": ["1.1","1.2","1.3","1.4","1.5"]},
    {"wave": 2, "tasks": ["3.1","3.2","3.3","3.4","3.5"], "depends_on": ["2.1","2.2","2.3","2.4","2.5"]},
    {"wave": 3, "tasks": ["4.1","4.2","4.3","4.4","4.5"], "depends_on": ["3.1","3.2","3.3","3.4","3.5"]},
    {"wave": 4, "tasks": ["5.1","5.2","5.3","5.4","5.5"], "depends_on": ["4.1","4.2","4.3","4.4","4.5"]},
    {"wave": 5, "tasks": ["6.1","6.2","6.3","6.4","6.5"], "depends_on": ["5.1","5.2","5.3","5.4","5.5"]},
    {"wave": 6, "tasks": ["7.1","7.2","7.3","7.4","7.5"], "depends_on": ["6.1","6.2","6.3","6.4","6.5"]},
    {"wave": 7, "tasks": ["8.1","8.2","8.3","8.4","8.5"], "depends_on": ["7.1","7.2","7.3","7.4","7.5"]},
    {"wave": 8, "tasks": ["9.1","9.2","9.3","9.4","9.5","9.6"], "depends_on": ["8.1","8.2","8.3","8.4","8.5"]},
    {"wave": 9, "tasks": ["10.1","10.2","10.3","10.4","10.5"], "depends_on": ["9.1","9.2","9.3","9.4","9.5","9.6"]},
    {"wave": 10, "tasks": ["11.1","11.2","11.3","11.4"], "depends_on": ["10.1","10.2","10.3","10.4","10.5"]}
  ]
}
```

## Notes

### 执行规则

1. 所有叶子任务都是必做项并保持 `[ ]`；禁止 optional、waiver、ask-user checkpoint 或假绿。
2. 普通合并门只加载 `backend/tests/conftest.py` 的全局 fast profile；nightly/release 仅通过独立 profile/env 提高样本数，测试代码不分叉。
3. UAT-02/03/08/13/15 为一票否决；Playwright 只证明用户边界，不替代 PG、PBT、offline verifier 或 6000 VU。
4. 实施迁移时动态取下一可用 V；回滚不删除 AttachmentVersion、EvidenceRef、OCR 决策、审计、Manifest 或 Hold。
5. FormalOutput、archive、stale、hold、impact 共用统一依赖图；外部依赖失败、队列 pending/dead-letter、integrity 失败或 quarantined 均 fail-closed。
