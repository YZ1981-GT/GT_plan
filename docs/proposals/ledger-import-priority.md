# 账表导入智能优先落地实施方案（权威整合版）

## 1. 文档目的

本文档为账表导入域**唯一权威说明**：合并原《智能优先落地实施方案》、原《生产运行手册》、原《企业级平台下一阶段改造建议》三份材料，并按**当前仓库代码**校对口径。

文中明确：

- 当前真实落地情况（以代码能力为准）
- 目标模式：智能处理为主，人工确认/映射为兜底
- 分阶段实施路径、验收指标、风险控制与回滚策略
- **生产配置、Worker、SLO、故障演练与巡检命令**（原独立运行手册内容见第 14 章）

本方案用于研发排期、联调、发布验收与运维值班，不替代 OpenAPI/ADR 细则。

---

## 2. 目标与范围

### 2.1 目标模式

采用“**智能辅助 + 人工确认/映射**”可控模式：

- 默认自动识别和映射，系统先给出建议与置信度
- 人工仅介入低置信、冲突或阻断项
- 导入过程可审计、可回滚、可追踪

### 2.2 覆盖范围

- 上传：大文件、Excel、CSV、多文件、单文件多 sheet
- 解析与校验：结构校验、业务校验、激活门禁
- 入库与激活：staged 写入、版本切换、失败回退
- 下游联动：四表关联、试算重算、事件驱动
- 企业级治理：作业可靠性、安全、审计、观测

---

## 3. 当前落地现状（整合评估）

| 能力域 | 当前状态（2026-04-29 代码快照） | 说明 |
|---|---|---|
| 上传与大文件处理 | 已落地（S3 可选） | 支持分块落盘、上传复用、产物记录（artifact）；默认 local/sharedfs，已支持 S3-compatible 对象存储配置 |
| Excel/CSV 与多文件多 sheet | 已落地 | 支持 csv/xlsx、多文件、多 sheet 编排；`.xls` 不支持 |
| 智能映射与自动识别 | 已落地（v1 契约） | `suggested_mapping/confidence_by_field/reasons/rule_version/needs_confirmation` 已在 preview/import 双入口统一，并有回归测试覆盖 |
| 导入异步与可靠性 | 已落地（外置 worker + 进程内兼容） | ImportJob 状态机、恢复、取消、重试、超时已接入；已提供独立 worker 入口，默认仍可开启进程内 runner |
| 入库与激活安全性 | 已落地（P0 核心） | 已实现“校验阻断激活”“激活失败即失败”“失败不污染 `active dataset`” |
| 四表联动与下游事件 | 已落地（outbox 补偿） | `dataset_activated` / `dataset_rolled_back` 已接入主要订阅方；激活/回滚事件已通过 DB outbox 支持提交后重放补偿 |
| 数据集版本治理 | 已落地（主链） | dataset_id 已进入核心账表与科目表写入；读路径迁移进行中（部分服务仍沿用 `is_deleted=false`） |
| 企业级治理（审计/监控/安全） | 部分落地（增强） | 已有历史查询、操作入口、基础留痕、导入 SLO JSON 与事件健康检查；外部告警平台接入仍按运维体系配置 |

### 3.1 关键结论（本轮更新后）

系统已从“平台化雏形”进入“主链可用阶段”，但尚未达到“企业级稳态”。  
本轮已完成的关键提升：

1. ImportJob durable 状态机 + 恢复/取消/重试/超时闭环
2. 激活门禁收紧（校验阻断与失败显式失败）
3. dataset_id 版本语义进入写入链路与部分读路径
4. 回滚事件与导入历史中心（前后端）上线

当前最核心短板收敛为：

1. 对象存储后端已具备 S3-compatible 实现，仍需生产凭据联调与故障演练记录
2. 事件 replay、DB outbox 与一致性健康检查已有 JSON 证据，仍需绑定外部告警与值班流程
3. 导入 SLO/告警 JSON 已提供，仍需接入现有运维平台或定时巡检
4. 项目级权限在导入域已收口，跨域安全审计基线仍待统一签收

### 3.2 本轮代码核对结论（可追踪）

已在代码中确认：

- 新增导入执行器：`backend/app/services/import_job_runner.py`
- 新增独立 worker 入口：`backend/app/workers/import_worker.py`
- 新增产物服务：`backend/app/services/import_artifact_service.py`
- 新增数据集/作业历史前端页：`audit-platform/frontend/src/views/LedgerImportHistory.vue`
- 新增统一导入历史 API：`audit-platform/frontend/src/services/ledgerImportApi.ts`
- 新增 dataset_id 迁移：`backend/alembic/versions/phase17_002_dataset_id_columns.py`
- 新增项目级并发唯一索引迁移：`backend/alembic/versions/phase17_003_import_queue_project_lock.py`
- 新增 S3 artifact 存储抽象：`backend/app/services/import_artifact_storage.py`
- 新增导入 SLO 与事件健康接口：`/api/admin/import-slo`、`/api/admin/import-alerts`、`/api/admin/import-event-health`、`/api/admin/import-event-replay`
- 新增导入事件 outbox：`backend/app/services/import_event_outbox_service.py`、`backend/alembic/versions/phase17_004_import_event_outbox.py`
- 生产运维命令与灰度步骤：见本文 **第 14 章**
- 新增覆盖测试：`backend/tests/test_dataset_import_platform.py`（当前通过）
- 新增协议统一测试：`backend/tests/test_ledger_import_application_service.py`

---

## 4. 目标架构原则（智能优先）

### 4.1 五项原则

- **默认自动**：上传后自动识别文件、sheet 角色、字段映射
- **可解释智能**：每条建议包含 `reasons` + `confidence_by_field`
- **分级门禁**：`fatal/error/warning/info` 明确阻断规则
- **最小人工介入**：仅处理低置信与冲突项
- **全链路可治理**：可审计、可观测、可回滚

### 4.2 推荐处理流

```text
上传文件/产物
  -> 智能识别（文件类型、sheet 类型、字段映射）
  -> 结构化校验报告（severity + blocking）
  -> 人工确认低置信/冲突项（可选）
  -> 创建导入作业（job）
  -> staged 写入 + validation gate
  -> 数据集激活（`active dataset` 切换）
  -> 发布事件（重算/缓存/下游刷新）
  -> 历史留存（`import_job` / `ledger_dataset` / `validation_report` / `audit_log`）
```

---

## 5. 分阶段实施计划（当前实际进度版）

> 状态口径：`已完成` = 已在主链落地并可用；`进行中` = 已有代码落点但未达目标态；`待开始` = 尚未进入实装阶段。

## 5.1 迭代一（P0）：智能主链可用且稳定

### P0-1 智能预览与映射主链收口（状态：已完成）

当前进展：

- 智能预览/导入主链已统一到作业化流程，前端可按 `job_id` 轮询状态
- `suggested_mapping/confidence_by_field/reasons/rule_version/needs_confirmation` 已在 ledger/account_chart 双入口统一
- 高置信自动应用阈值已配置化（`LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD`）

后续保持项：

- 按版本维护建议契约（字段新增/弃用走版本化兼容窗口）
- 持续校准自动应用阈值与误判率（按周观测）

### P0-2 人工兜底交互最小化（状态：进行中）

当前进展：

- 已新增导入历史页，支持回滚、重试、取消、历史查询，人工干预入口更集中
- 低置信字段已通过 `needs_confirmation` 统一输出，并在前端统一校验摘要组件展示
- 人工修正复用已具备项目级映射保存/引用能力（column mapping 保存 + reference copy）

下一步：

- 收口人工动作为三类：字段修正、冲突策略、阻断确认
- 增加人工修正持久化与复用策略

### P0-3 激活门禁与失败语义加固（状态：已完成）

当前进展：

- 已实现“校验不通过阻断激活”
- 已实现“激活失败显式失败”，并将 dataset 标记为 failed
- 已实现“导入失败不污染当前 `active dataset`”

后续保持项：

- 门禁规则配置化清单持续维护（规则版本、阻断策略、回退策略）
- 对阻断准确率持续抽样复核

### P0-4 端到端质量基线（状态：进行中）

当前进展：

- 已补充 `backend/tests/test_dataset_import_platform.py`，覆盖作业状态机、激活回滚、恢复路径等核心场景
- 日志主键与全链路观测字段已有基础，但看板和告警阈值尚未完全接入
- 文档要求的大文件与多场景 E2E 仍未全部补齐

下一步：

- 补齐 E2E：大 CSV、大 Excel、多文件多 sheet、低置信人工介入、激活失败回退
- 建立统一指标看板：成功率、耗时、阻断率、恢复率、回滚触发率

---

## 5.2 迭代二（P1）：企业级运行能力补齐

### P1-1 durable job 外置化（状态：进行中）

当前进展：

- ImportJob 持久化状态机、恢复、取消、重试、超时能力已落地
- 已提供独立 worker 进程入口（`python -m app.workers.import_worker`）并支持轮询参数化
- 仍保留进程内 runner 兼容模式，生产默认关闭策略与切换演练未完全固化

下一步：

- 完成 worker 外置化（队列/执行器解耦、部署与运维手册）
- 验证 Web 重启不影响作业连续性

### P1-2 多实例一致性治理（状态：进行中）

当前进展：

- 已新增 artifact 服务与 `sharedfs://` 存储语义，产物治理有基础
- 已引入 DB 唯一索引 `uq_import_batches_one_processing_smart_job` 作为项目级串行主约束
- 内存锁仅用于单进程进度缓存；对象存储后端与跨实例存储演练仍待完成

下一步：

- 引入分布式锁或队列串行作为唯一并发控制机制
- 完成对象存储后端接入并验证跨实例可读

### P1-3 四表联动与回滚事件闭环（状态：进行中）

当前进展：

- `dataset_activated` / `dataset_rolled_back` 事件已发布并接入主要订阅方
- 回滚触发重算与缓存失效主链可用
- 失败补偿与重放、订阅一致性校验仍待加强

下一步：

- 建立事件消费幂等键与补偿重放机制
- 增加“发布成功但未消费”的告警和自动修复流程

### P1-4 智能能力增强（可学习）（状态：待开始）

目标保持不变：

- 项目级历史映射偏好学习
- 同名列歧义消解（按样本值模式）
- 多文件一致性校验增强（年度、主体、期间覆盖）

启动前置条件：

- 先完成智能建议协议字段冻结与人工修正留痕
- 先建立命中率/改写率/错判率的周度指标口径

---

## 6. 产品与交互规范（智能主导，人工兜底）

### 6.1 页面行为规范

- 高置信建议默认勾选并可一键通过
- 低置信项集中展示，支持批量处理
- 阻断项单独分组显示，清晰说明阻断原因
- 导入完成页展示：自动处理比例、人工修正项、最终生效 `dataset`

### 6.2 结果解释规范

对每个建议项必须可查看：

- 命中规则（rule_code）
- 置信度（confidence）
- 推荐理由（reason）
- 示例数据（sample_rows）

---

## 7. 风险控制与发布回滚

### 7.1 发布策略

采用灰度和开关，不做一次性大切换：

1. 内核统一（外部路由兼容保留）
2. 前端切换至智能优先交互
3. job durable/共享存储灰度
4. 旧链路清理

### 7.2 回滚策略

- 路由回滚：保留旧路由兼容开关
- 数据回滚：dataset 新旧语义短期并存
- 作业回滚：worker 切换前保留旧轮询接口
- 事件回滚：新旧事件并行发布一段窗口期

### 7.3 重点风险

1. 激活失败语义不一致导致“假成功”
2. 多实例下并发导入冲突
3. 回滚事件未触发完整下游重算
4. 大文件解析内存峰值超限
5. 智能建议误判导致人工负担反升

---

## 8. 验收标准（阶段门槛）

### 8.1 架构口径

- 所有导入入口收口到统一应用服务
- 无入口层整块大文件 `read()` 主链路
- durable job 不依赖单一 Web 进程生命周期

### 8.2 数据口径

- 同一 `project-year` 仅一个业务可见 `active dataset`
- 导入失败不破坏当前有效账套
- 可追溯每次导入对应文件、规则、报告、激活结果

### 8.3 产品口径

- 用户能明确识别当前阶段：预览/待确认/导入中/已激活/可回滚
- 高置信场景无需人工逐项确认
- 人工介入仅发生于低置信、冲突、阻断项

### 8.4 运维口径

- 可查询 `job` 历史、`dataset` 历史、`validation` 报告
- 提供成功率、耗时、错误分布、回滚触发等核心指标

---

## 9. 非功能目标与 SLO（NFR）

为确保方案达到企业级稳态，除功能验收外，必须增加统一 NFR 基线。

### 9.1 可用性与连续性目标

- 导入核心 API 月度可用性目标：>= 99.9%
- 导入作业状态查询可用性目标：>= 99.95%
- 事件发布成功率目标：>= 99.99%

### 9.2 性能与容量目标（首版）

- 500MB CSV：在标准生产配置下可稳定完成导入
- 1GB Excel（含多 sheet）：在限定并发下可稳定完成导入
- 峰值内存控制：不得超过服务预设阈值（按环境配置）
- 导入耗时 P95/P99 进入指标看板持续跟踪

### 9.3 恢复目标

- 作业恢复 RTO：worker 重启后在目标窗口内恢复排队/执行
- 回滚恢复 RTO：触发回滚后在目标窗口内完成数据切换和下游刷新
- 数据一致性 RPO：导入失败不得污染 `active dataset`

---

## 10. 事务边界与一致性策略

### 10.1 导入事务边界

必须明确以下口径：

- “导入成功”以“写入成功 + 激活成功”为最终判定
- 若激活失败，则本次导入结果必须标记失败，不允许静默成功
- 分批写入场景需配套一致性补偿策略，防止半成功状态长期遗留

### 10.2 幂等与去重策略

- 作业幂等键建议：`project_id + year + artifact_hash + mapping_hash`
- 重试必须复用同一幂等键，避免重复写入
- 激活动作必须具备幂等保障，重复调用不改变最终正确状态

### 10.3 一致性守卫

- `active dataset` 变更必须可审计、可回放
- 导入失败后读路径仍只读取旧 `active dataset`
- 回滚后读路径与下游刷新状态必须一致

---

## 11. 权限、安全与合规基线

### 11.1 访问控制

- 导入、回滚、重试、取消作业必须进行项目级权限校验
- 区分最小权限角色：上传者、审核者、激活操作者、运维操作者

### 11.2 审计与留痕

- 记录“谁在何时确认了哪些人工映射”
- 记录导入、激活、回滚、重试、取消全链路操作日志
- 关键操作日志保留策略与审计查询能力需制度化

### 11.3 数据与日志合规

- 日志脱敏：账号、文件名敏感字段、业务敏感内容按规则脱敏
- 产物与报告保留周期（retention）分级管理
- 下载与导出行为可追踪（操作者、时间、对象）

---

## 12. 智能策略治理与可运营闭环

### 12.1 置信度分层策略

- 高置信：默认自动通过
- 中置信：进入人工快速确认
- 低置信：必须人工处理，不允许自动激活

### 12.2 错判反馈闭环

- 人工修正结果进入规则/模型反馈池
- 建立“建议命中率、人工改写率、错判率”周度报表
- 规则版本与效果变化需可追踪

### 12.3 可解释性最小集

每条智能建议至少包含：

- `rule_code`
- `confidence_by_field`
- `reasons`
- `sample_rows`
- `rule_version`

---

## 13. 数据集生命周期治理

### 13.1 生命周期状态机

建议标准状态：

- `staged`
- `validating`
- `active`
- `failed`
- `rolled_back`
- `archived`

### 13.2 生命周期约束

- 同一 `project-year` 任一时刻仅允许一个 `active`
- 回滚窗口需配置化（例如仅允许回滚最近 N 个版本）
- 历史 `dataset` 与 `artifact`、`validation report`、`job` 建立可追溯关联

### 13.3 归档与清理

- 超出保留期的历史版本进入 `archived` 策略
- 清理动作需保留审计轨迹
- 清理前必须做依赖检查，防止误删活跃引用

---

## 14. 生产运行与运维手册（Runbook）

### 14.1 灰度与开关矩阵

- 功能开关粒度：上传、智能映射、durable job、数据集激活、回滚
- 灰度顺序：内部项目 → 小流量项目 → 全量
- 每阶段需定义进入/退出条件与回退条件
- Web 与 Worker 拓扑、对象存储、SLO 阈值与巡检命令：见本章 **14.4～14.6**

### 14.2 故障分级与处置

- **P1**：导入全不可用、激活失败导致数据不可读
- **P2**：部分项目导入失败、回滚链路异常
- 每级故障必须具备标准排查路径与责任人

### 14.3 常见告警与诊断路径

- job 长时间卡在 `running` / `activating`
- 事件发布成功但下游未刷新（优先查 outbox、`import-event-health`、按需 `import-event-replay`）
- 大文件导入内存逼近阈值
- 回滚成功但读路径版本不一致

### 14.4 推荐生产配置、启动与切换

**推荐生产配置**

生产/预发建议关闭 Web 进程内 runner，由独立 worker 执行导入作业：

```bash
LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED=false
LEDGER_ARTIFACT_STORAGE_BACKEND=s3
LEDGER_ARTIFACT_S3_ENDPOINT_URL=https://s3.example.com
LEDGER_ARTIFACT_S3_BUCKET=audit-import-artifacts
LEDGER_ARTIFACT_S3_PREFIX=ledger-import
LEDGER_ARTIFACT_S3_REGION=us-east-1
```

本地或单实例开发可继续使用默认 `local` / `sharedfs` 模式。

**启动示例**

Web 进程：

```bash
LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED=false uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Worker 进程：

```bash
python -m app.workers.import_worker --poll-interval 5 --batch-size 3
```

**灰度步骤建议**

1. 预发启用 S3 artifact，并确认 `/api/admin/import-slo` 可查询。
2. 将 Web 设置为 `LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED=false`。
3. 启动 1 个 worker，完成小文件冒烟导入。
4. 扩容 worker，执行并发导入与 worker kill/restart 演练。
5. 生产按项目灰度，观察失败率、超时率、P95/P99。

**回滚策略**

1. 停止独立 worker。
2. 将 Web 配置恢复为 `LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED=true`。
3. 重启 Web，确认 queued/pending 作业被恢复。
4. 通过 `/api/admin/import-slo` 检查失败率和队列深度。

### 14.5 对象存储故障注入演练

用于验证 artifact 读写降级行为：

```bash
LEDGER_ARTIFACT_STORAGE_FAILURE_MODE=timeout      # 模拟超时
LEDGER_ARTIFACT_STORAGE_FAILURE_MODE=readonly     # 模拟只读
LEDGER_ARTIFACT_STORAGE_FAILURE_MODE=unavailable  # 模拟不可达
```

演练要求：

1. 上传阶段遇到只读/不可达时应返回明确错误，不产生不可用 artifact。
2. Worker 读取对象存储失败时，作业进入失败或可重试状态。
3. 演练后清空 `LEDGER_ARTIFACT_STORAGE_FAILURE_MODE` 并重试成功。

### 14.6 SLO、告警、Outbox 重放与健康巡检

**导入 SLO**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://host/api/admin/import-slo?hours=24"
```

**导入告警**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://host/api/admin/import-alerts?hours=24"
```

**导入事件 outbox 手工重放**

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "https://host/api/admin/import-event-replay?limit=100"
```

告警阈值已配置化（`backend/app/core/config.py`）：

- `LEDGER_IMPORT_SLO_FAILURE_RATE_WARN_THRESHOLD`
- `LEDGER_IMPORT_SLO_TIMEOUT_RATE_CRITICAL_THRESHOLD`
- `LEDGER_IMPORT_SLO_P95_DURATION_SECONDS_WARN_THRESHOLD`
- `LEDGER_IMPORT_SLO_QUEUE_DELAY_P95_SECONDS_WARN_THRESHOLD`
- `LEDGER_IMPORT_SLO_OUTBOX_BACKLOG_WARN_THRESHOLD`
- `LEDGER_IMPORT_SLO_ACTIVE_JOBS_WARN_THRESHOLD`

生产建议起始值（可按业务规模调优）：

```bash
LEDGER_IMPORT_SLO_FAILURE_RATE_WARN_THRESHOLD=0.05
LEDGER_IMPORT_SLO_TIMEOUT_RATE_CRITICAL_THRESHOLD=0.02
LEDGER_IMPORT_SLO_P95_DURATION_SECONDS_WARN_THRESHOLD=1800
LEDGER_IMPORT_SLO_QUEUE_DELAY_P95_SECONDS_WARN_THRESHOLD=300
LEDGER_IMPORT_SLO_OUTBOX_BACKLOG_WARN_THRESHOLD=20
LEDGER_IMPORT_SLO_ACTIVE_JOBS_WARN_THRESHOLD=10
```

预发可放宽一档，例如：

```bash
LEDGER_IMPORT_SLO_FAILURE_RATE_WARN_THRESHOLD=0.08
LEDGER_IMPORT_SLO_TIMEOUT_RATE_CRITICAL_THRESHOLD=0.03
LEDGER_IMPORT_SLO_P95_DURATION_SECONDS_WARN_THRESHOLD=2400
LEDGER_IMPORT_SLO_QUEUE_DELAY_P95_SECONDS_WARN_THRESHOLD=480
LEDGER_IMPORT_SLO_OUTBOX_BACKLOG_WARN_THRESHOLD=40
LEDGER_IMPORT_SLO_ACTIVE_JOBS_WARN_THRESHOLD=15
```

**事件一致性巡检**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://host/api/admin/import-event-health?project_id=$PROJECT_ID&year=$YEAR"
```

关注字段：

- `status`：`healthy` 或 `degraded`
- `replay_report.last_error`：最近 replay 错误
- `replay_report.acked_count`：已确认重放消息数量
- `outbox_summary.pending_count`：已提交但尚未发布的导入事件数量
- `outbox_summary.failed_count`：发布失败、需要重放或排障的数量
- `expected_event_evidence`：近期激活/回滚记录与预期事件证据

若 `pending_count` 或 `failed_count` 大于 0，先调用 `/api/admin/import-event-replay`；仍失败时查看 `recent_failed.last_error` 并检查事件处理器与下游重算。

### 14.7 压测脚本

```bash
python scripts/import_load_smoke.py \
  --base-url http://localhost:8000 \
  --token "$TOKEN" \
  --project-id "$PROJECT_ID" \
  --year 2026 \
  --file ./samples/ledger.csv \
  --concurrency 2
```

超大 CSV、超大 Excel 与并发场景由环境提供真实样本；脚本负责提交、轮询与输出 JSON 报告。

---

## 15. 成本与容量规划

### 15.1 存储成本

- artifact 分层保留：短期热数据 + 中长期冷数据
- 按项目规模定义容量配额与告警阈值

### 15.2 计算成本

- worker 规格按文件大小分级调度
- 导入并发上限按环境配置，避免争抢导致雪崩

### 15.3 峰值容量模型

- 按“项目数 x 导入频率 x 平均文件体积”估算峰值
- 高峰期预留弹性容量并设置自动扩缩策略

---

## 16. 组织协同与里程碑责任

### 16.1 RACI 建议

- 后端：导入内核、作业系统、数据一致性与事件语义
- 前端：智能优先交互、人工兜底流程、状态可视化
- 测试：E2E、故障注入、回归门禁
- 运维：监控、告警、容量、发布回滚
- 产品/业务：规则优先级、人工确认策略、验收口径

### 16.2 里程碑出入口（Go/No-Go）

- 进入 Beta 前：P0 验收口径全部达成
- 进入 GA 前：durable job + 分布式锁 + 共享存储 + 回滚闭环全部达成
- 任一关键门槛不达标时，禁止强推全量发布

---

## 17. ADR 决策索引（Architecture Decision Record）

为避免关键技术路线反复摇摆，建议对企业级落地关键决策建立 ADR 索引。每条 ADR 必须包含：

- 问题背景（为什么现在必须做决策）
- 备选方案（至少 2 个）
- 最终选择（含约束条件）
- 不选原因（成本、风险、复杂度、兼容性）
- 生效范围与生效时间

### 17.1 首批必须冻结的 ADR 主题

1. durable job 技术选型（队列/worker 框架）
2. 分布式锁选型（Redis/DB advisory lock/队列串行）
3. artifact 存储选型（共享卷/对象存储）
4. 事件总线语义收口（激活/回滚/失败事件）
5. 激活与回滚一致性策略（事务 + 幂等）
6. 智能规则引擎版本化策略（规则版本发布与回退）

### 17.2 ADR 建议模板

```text
ADR-00X: <标题>
状态: proposed / accepted / deprecated
背景: <业务与技术上下文>
备选方案:
  A. ...
  B. ...
  C. ...
决策: <选择 A/B/C>
决策原因: <核心理由>
代价与风险: <引入的新复杂度>
回退方案: <失败时如何回退>
生效版本: <迭代/发布日期>
```

---

## 18. 接口契约与兼容策略（冻结表）

### 18.1 契约冻结原则

- 导入主链路核心协议采用版本化管理（如 `v1`/`v2`）
- 任何破坏性变更必须提前公告并提供兼容窗口
- 兼容窗口内同时支持新旧字段，超窗后再移除旧字段

### 18.2 建议冻结的核心契约

1. 智能建议协议：`suggested_mapping`、`confidence_by_field`、`reasons`、`rule_version`、`needs_confirmation`
2. 校验报告协议：`rule_code`、`severity`、`blocking`、`sample_rows`、`validation_summary`
3. 作业状态协议：`pending/queued/running/validating/writing/activating/completed/failed/canceled/timed_out`
4. 数据集协议：`dataset_id`、`status`、`previous_dataset_id`、`activated_at`
5. 错误协议：统一错误码与可读错误消息结构

### 18.3 兼容策略与废弃计划

- `T0`：发布新协议并保留旧字段兼容
- `T0 + 1 迭代`：前端与调用方全部迁移到新协议
- `T0 + 2 迭代`：旧字段进入告警期（日志提示）
- `T0 + 3 迭代`：删除旧字段与旧入口（经变更评审批准）

### 18.4 环境分层 SLO（测试/预发/生产）

为避免上线口径不一致，建议按环境定义分层阈值：

- 测试环境：强调功能完整性与回归覆盖率
- 预发环境：强调性能阈值与恢复演练通过率
- 生产环境：强调可用性、P95/P99、错误预算与告警响应时效

导入 SLO 告警阈值已配置化（`backend/app/core/config.py`）；变量清单与 **生产/预发建议取值示例见 §14.6**，避免正文多处重复维护。

建议起始值（可按业务规模逐步调优）：

- 测试环境（偏宽松，减少噪声告警）
  - `FAILURE_RATE_WARN=0.20`
  - `TIMEOUT_RATE_CRITICAL=0.10`
  - `P95_DURATION_SECONDS_WARN=3600`
  - `QUEUE_DELAY_P95_SECONDS_WARN=900`
  - `OUTBOX_BACKLOG_WARN=100`
  - `ACTIVE_JOBS_WARN=30`
- 预发环境（贴近生产，关注回归风险）
  - `FAILURE_RATE_WARN=0.08`
  - `TIMEOUT_RATE_CRITICAL=0.03`
  - `P95_DURATION_SECONDS_WARN=2400`
  - `QUEUE_DELAY_P95_SECONDS_WARN=480`
  - `OUTBOX_BACKLOG_WARN=40`
  - `ACTIVE_JOBS_WARN=15`
- 生产环境（严格，优先稳定性与可用性）：与 **§14.6** 中 bash 示例一致（避免两处口径漂移时可只维护 §14.6）。

---

## 19. 故障演练与上线门禁表

> 状态口径：`已完成` = 已完成演练并有记录；`进行中` = 有能力或脚本但未形成稳定演练机制；`待开始` = 尚未进入执行。

### 19.1 必做故障演练清单（当前实际进度）

1. worker 进程中断（运行中作业恢复）  
   - 状态：进行中  
   - 现状：已具备作业恢复逻辑（pending/queued/running 超时与恢复），且已有独立 worker 入口；预发故障演练记录尚未固化  
   - 下一步：在预发执行“运行中 kill worker + 自动恢复”演练并固化脚本

2. 激活动作失败（确保不产生“假成功”）  
   - 状态：已完成  
   - 现状：激活失败已显式失败，且不会污染 `active dataset`；相关回归测试已覆盖核心语义  
   - 下一步：按版本持续抽样校验失败路径与错误码一致性

3. 事件发布成功但下游未消费（补偿与重放）  
   - 状态：进行中  
   - 现状：`dataset_activated` / `dataset_rolled_back` 事件已接入主要订阅方；补偿重放机制仍需完善  
   - 下一步：补齐幂等键、补偿重放任务与“发布成功未消费”告警

4. 对象存储/共享存储短时不可用（降级与重试）  
   - 状态：进行中  
   - 现状：已具备 artifact 服务、sharedfs 语义与 S3-compatible 后端；已提供 `LEDGER_ARTIFACT_STORAGE_FAILURE_MODE` 故障注入  
   - 下一步：在预发执行超时/只读/不可达演练并归档记录

5. 回滚链路异常（读路径一致性与重算补偿）  
   - 状态：进行中  
   - 现状：回滚事件、重算触发主链可用；全量消费一致性与补偿验证不充分  
   - 下一步：新增“回滚成功但下游未刷新”专项演练与修复SOP

### 19.2 演练结果记录模板

```text
演练编号: DRILL-00X
场景: <故障场景>
触发时间: <timestamp>
预期结果: <SLO/RTO/RPO>
实际结果: <通过/失败 + 数据>
根因: <问题分析>
修复动作: <立即修复 + 长期修复>
责任人: <owner>
复盘结论: <是否允许进入下一发布阶段>
```

### 19.3 Beta/GA 上线门禁（当前实际进度，可勾选）

> 门禁编号用于第 20 章任务关联，必须保持稳定；若调整需同步更新第 20 章“关联门禁”字段。

#### Beta 门禁

- [ ] **Beta-1** 自动映射覆盖率达到目标阈值（状态：进行中）
  - 证据路径：`backend/app/services/ledger_import_application_service.py`、`backend/tests/test_dataset_import_platform.py`
  - 责任人：`待指派`
  - 预计完成：`待排期`
- [ ] **Beta-2** 阻断误判率在阈值内（状态：进行中）
  - 证据路径：`backend/tests/test_ledger_import_application_service.py`
  - 责任人：`待指派`
  - 预计完成：`待排期`
- [ ] **Beta-3** 大文件导入压测达标（状态：进行中）
  - 证据路径：`backend/scripts/import_load_smoke.py`；`待补压测报告`
  - 责任人：`待指派`
  - 预计完成：`待排期`
- [ ] **Beta-4** 回滚链路演练通过（状态：进行中）
  - 证据路径：`backend/tests/test_dataset_import_platform.py`（语义回归）；`待补 DRILL 记录`
  - 责任人：`待指派`
  - 预计完成：`待排期`

#### GA 门禁

- [ ] **GA-1** durable worker 上线并稳定运行（状态：进行中）
  - 证据路径：`backend/app/workers/import_worker.py`、`backend/app/services/import_job_runner.py`
  - 责任人：`待指派`
  - 预计完成：`待排期`
- [ ] **GA-2** 分布式锁与共享存储落地（状态：进行中）
  - 证据路径：`backend/alembic/versions/phase17_003_import_queue_project_lock.py`、`backend/app/services/import_artifact_service.py`、`backend/app/services/import_artifact_storage.py`
  - 责任人：`待指派`
  - 预计完成：`待排期`
- [ ] **GA-3** 全链路观测与告警接入完成（状态：进行中）
  - 证据路径：`backend/app/middleware/observability.py`、`backend/app/services/performance_monitor.py`、`backend/app/services/import_slo_service.py`
  - 责任人：`待指派`
  - 预计完成：`待排期`
- [ ] **GA-4** 安全审计基线达标（状态：待开始）
  - 证据路径：`backend/tests/test_dataset_import_platform.py`（导入域权限断言）；`待补全局审计检查单`
  - 责任人：`待指派`
  - 预计完成：`待排期`

### 19.4 本阶段演练执行要求（新增）

- 所有演练必须至少在预发环境通过 1 次，且保留记录（编号、证据、责任人）
- 演练结论必须绑定发布批次；未通过项不得进入下一发布阶段
- 对“进行中/待开始”项建立周度燃尽清单，纳入迭代例会追踪

---

## 20. 下一步行动项（按优先级，已与第 19 章门禁对齐）

> 状态口径与第 19 章一致：`已完成/进行中/待开始`。  
> 本章只保留“要做什么”；演练与放行结论以第 19 章为准，避免重复口径。

### P0（必须先做，1-2 周）

1. 外置 durable worker 最小可用版（状态：进行中；关联门禁：GA-1）
   - 产出：worker 独立进程部署方式、任务领取协议、停机恢复策略
   - 验收：Web 进程重启不影响运行中作业（恢复率 100%）

2. 多实例一致性治理（锁 + 存储）（状态：进行中；关联门禁：GA-2）
   - 产出：项目级分布式锁（或队列串行）与共享存储/对象存储统一接口
   - 验收：同项目并发冲突率 0，跨实例可读取同一 upload artifact

3. 智能建议协议字段冻结（状态：已完成；关联门禁：Beta-1/Beta-2）
   - 产出：`suggested_mapping/confidence_by_field/reasons/rule_version/needs_confirmation` v1 契约
   - 验收：双入口（ledger/account_chart）返回结构一致（已由回归测试覆盖）；覆盖率/误判率看板仍需补齐

4. 大文件压测与容量基线（状态：待开始；关联门禁：Beta-3）
   - 产出：500MB CSV、1GB Excel、多并发场景压测报告与瓶颈清单（脚本：`backend/scripts/import_load_smoke.py`）
   - 验收：达成预设阈值并形成扩容与降级策略

5. 项目级权限收口（状态：进行中；关联门禁：GA-4）
   - 产出：导入/取消/重试/回滚/历史查询的项目角色校验矩阵
   - 验收：导入域 readonly/edit 已落地并有测试；跨域审计追溯口径待统一

### P1（并行推进，2-3 周）

6. 读路径全面迁移到 `dataset` 语义（状态：进行中）
   - 产出：四表查询服务逐项替换为 `get_active_filter`（或等价统一过滤器）
   - 验收：不再依赖 `is_deleted=false` 作为业务可见唯一条件

7. 下游事件闭环与补偿重放（状态：进行中；关联门禁：Beta-4）
   - 产出：`dataset_activated` / `dataset_rolled_back` 统一消费、失败补偿、幂等重放机制
   - 验收：回滚后重算/缓存刷新触发完整率 100%

8. 全链路观测与告警看板（状态：进行中；关联门禁：GA-3）
   - 产出：成功率、耗时 P95/P99、失败率、超时率、队列深度、最近失败原因
   - 验收：`/api/admin/import-slo` 与 `/api/admin/import-alerts` 可查询，外部告警平台完成阈值接入

9. 故障演练执行化与发布绑定（状态：进行中）
   - 产出：5 类必做演练脚本、演练记录实例、发布批次绑定清单
   - 验收：未通过演练项不得进入下一发布阶段

完成以上任务并满足第 19 章门禁后，再进入全量发布，可显著降低并发、回滚和运维风险。

---

## 21. 开发实施清单（按模块拆解）

本章节仅面向研发执行，不讨论管理决策。每项任务均要求对应 PR、测试用例和回归记录。

### 21.1 后端改造清单

1. 统一导入应用层编排
   - 目标文件：
     - `backend/app/services/ledger_import_application_service.py`
     - `backend/app/routers/account_chart.py`
     - `backend/app/routers/ledger_penetration.py`
   - 目标动作：
     - 新旧入口全部经统一应用服务编排
     - 路由层只保留参数校验和权限校验
     - 消除入口层重复预览/导入逻辑

2. 导入内核一致性加固
   - 目标文件：
     - `backend/app/services/smart_import_engine.py`
     - `backend/app/services/dataset_service.py`
     - `backend/app/services/import_validation_service.py`
   - 目标动作：
     - 显式定义“导入成功 = 写入成功 + 激活成功”
     - 激活失败立即失败并进入补偿/回滚路径
     - 所有失败路径写入结构化失败原因（rule/error_code/message）

3. 作业系统 durable 化改造
   - 目标文件：
     - `backend/app/services/import_job_service.py`
     - `backend/app/services/import_job_runner.py`
     - `backend/app/main.py`
   - 目标动作：
     - 抽象 job runner adapter（本地/队列）
     - 保留状态机，迁移执行器到 worker
     - 完成超时、取消、重试、恢复逻辑闭环

4. 上传产物与多实例一致性改造
   - 目标文件：
     - `backend/app/services/ledger_import_upload_service.py`
     - `backend/app/services/import_artifact_service.py`
     - `backend/app/services/import_queue_service.py`
   - 目标动作：
     - 抽象存储后端接口（local/shared/object）
     - 为项目级并发锁引入分布式实现
     - 补齐产物过期清理和失败重试日志

5. 四表联动与事件补偿
   - 目标文件：
     - `backend/app/services/event_handlers.py`
     - `backend/app/services/trial_balance_service.py`
     - `backend/app/services/ledger_penetration_service.py`
   - 目标动作：
     - 统一激活/回滚事件订阅语义
     - 保证回滚后触发重算与缓存刷新
     - 失败事件支持重放与幂等消费

### 21.2 前端改造清单

1. 智能建议优先交互
   - 目标文件：
     - `audit-platform/frontend/src/views/LedgerPenetration.vue`
     - `audit-platform/frontend/src/views/AccountImportStep.vue`
     - `audit-platform/frontend/src/components/`（导入相关组件）
   - 目标动作：
     - 高置信建议默认应用
     - 低置信项集中人工确认
     - 阻断项独立分组展示并解释原因

2. API 层统一与协议收口
   - 目标文件：
     - `audit-platform/frontend/src/services/ledgerImportApi.ts`
     - `audit-platform/frontend/src/utils/importJobRequest.ts`
   - 目标动作：
     - 统一 preview/import/job/dataset 请求构造
     - 统一错误结构解析（code/message/details）
     - 统一 job 状态轮询和超时表现

3. 状态机与复用层收口
   - 目标动作：
     - 收口上传 -> 预览 -> 映射 -> 导入 -> 完成状态机
     - 页面差异仅保留展示层，不保留协议差异
     - 提炼 composable 共享逻辑，避免双实现漂移

### 21.3 数据库与迁移清单

1. 迁移脚本规范
   - 目标目录：`backend/alembic/versions/`
   - 要求：
     - 每次 schema 变更提供 upgrade/downgrade
     - 提供迁移后校验 SQL（行数、索引、约束）
     - 回滚脚本经过预发演练

2. 数据回填与一致性校验
   - 要求：
     - 历史记录补齐 `dataset_id`（如存在缺口）
     - 构建 `active dataset` 一致性校验脚本
     - 对冲突数据提供人工修复脚本

---

## 22. 接口与数据结构（字段级契约）

本章节用于前后端联调，不替代 OpenAPI，但作为冻结口径执行。

### 22.1 智能建议返回结构（示例）

```json
{
  "suggested_mapping": {
    "balance_sheet.amount": "本期借方发生额"
  },
  "confidence_by_field": {
    "balance_sheet.amount": 0.94
  },
  "reasons": {
    "balance_sheet.amount": "header_similarity+value_pattern"
  },
  "rule_version": "import-rules-2026.04",
  "needs_confirmation": [
    "ledger.voucher_no"
  ]
}
```

字段约束：

- `suggested_mapping`：必填，键为标准字段，值为源列名
- `confidence_by_field`：必填，键与 `suggested_mapping` 对齐，值范围 `[0,1]`
- `reasons`：必填，键与 `suggested_mapping` 对齐，值为机器解释文本或规则标识
- `rule_version`：必填，用于追溯规则变更
- `needs_confirmation`：可选，低置信字段列表（字段名集合）

### 22.2 校验报告结构（示例）

```json
{
  "validation": [
    {
      "file": "ledger_2025.xlsx",
      "sheet": "序时账",
      "rule_code": "LEDGER_PERIOD_GAP",
      "severity": "error",
      "message": "期间存在断档",
      "sample_rows": [120, 121],
      "blocking": true
    }
  ],
  "validation_summary": {
    "total": 12,
    "blocking_count": 2,
    "has_blocking": true,
    "by_severity": {
      "fatal": 0,
      "error": 2,
      "warning": 7,
      "info": 3
    }
  }
}
```

字段约束：

- `severity`：`fatal|error|warning|info`
- `blocking`：布尔值，是否阻断导入/激活
- `validation_summary`：后端聚合，前端不重复计算

### 22.3 Job 状态结构（示例）

```json
{
  "job_id": "job_xxx",
  "status": "writing",
  "progress": 67,
  "phase": "tb_ledger",
  "started_at": "2026-04-29T14:00:00Z",
  "heartbeat_at": "2026-04-29T14:03:00Z",
  "error_code": null,
  "error_message": null
}
```

字段约束：

- `status`：`pending|queued|running|validating|writing|activating|completed|failed|canceled|timed_out`
- `progress`：`0-100`
- `phase`：可选，标识当前处理阶段
- `heartbeat_at`：长任务必须持续刷新

---

## 23. 测试与回归矩阵（可执行）

### 23.1 后端测试矩阵（pytest）

1. 上传与大文件
   - 分块上传后 `upload_token` 可复用
   - 超出总大小/文件数上限返回预期错误

2. 解析与映射
   - CSV、XLSX、多文件、多 sheet 正常导入
   - 低置信字段进入 `needs_confirmation`

3. 激活与回滚
- 激活失败时导入状态为 `failed`，`active dataset` 不变
- 回滚后读路径仅返回回滚后的 `active dataset`

4. 事件联动
   - `dataset_activated` 触发试算重算
   - `dataset_rolled_back` 同样触发重算

5. 幂等与重试
   - 同幂等键重复提交不重复写入
   - job 重试后状态一致且无脏数据

### 23.2 前端测试矩阵（组件/E2E）

1. 高置信自动通过路径
2. 低置信人工确认路径
3. 阻断项禁止导入路径
4. 轮询超时与失败提示路径
5. 导入成功与回滚后展示一致性路径

### 23.3 性能与压力测试矩阵

- 500MB CSV：内存峰值、耗时、成功率
- 1GB Excel（多 sheet）：内存峰值、耗时、失败恢复
- 并发导入：同项目互斥、跨项目吞吐
- 长时任务：心跳刷新、超时处理、恢复能力

### 23.4 测试通过门槛

- 功能回归：100% 通过
- 关键链路（上传、导入、激活、回滚）：100% 通过
- 性能阈值：不低于预设基线
- 缺陷门槛：P1/P2 未关闭不得进入下一阶段

---

## 24. 本地调试、联调与排障手册

### 24.1 本地最小联调流程

1. 启动后端服务并确认数据库连接
2. 准备一组标准样例文件（CSV/XLSX/多 sheet）
3. 通过前端执行上传 -> 预览 -> 导入 -> 激活
4. 通过 job 接口确认状态机完整流转
5. 检查导入后穿透查询与试算刷新结果

独立 durable worker 联调：

```bash
LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED=false uvicorn app.main:app --reload
python -m app.workers.import_worker --poll-interval 5 --batch-size 3
```

- 本地默认仍可使用 Web 进程内 runner，生产/预发建议关闭 `LEDGER_IMPORT_IN_PROCESS_RUNNER_ENABLED` 并单独部署 worker
- `LEDGER_IMPORT_WORKER_POLL_INTERVAL_SECONDS` 和 `LEDGER_IMPORT_WORKER_BATCH_SIZE` 可控制 worker 轮询频率与单轮领取数量
- `LEDGER_IMPORT_AUTO_APPLY_CONFIDENCE_THRESHOLD` 控制高置信映射自动应用阈值，默认 `0.85`
- 导入 SLO 阈值可通过以下环境变量按环境调优：
  - `LEDGER_IMPORT_SLO_FAILURE_RATE_WARN_THRESHOLD`
  - `LEDGER_IMPORT_SLO_TIMEOUT_RATE_CRITICAL_THRESHOLD`
  - `LEDGER_IMPORT_SLO_P95_DURATION_SECONDS_WARN_THRESHOLD`
  - `LEDGER_IMPORT_SLO_QUEUE_DELAY_P95_SECONDS_WARN_THRESHOLD`
  - `LEDGER_IMPORT_SLO_OUTBOX_BACKLOG_WARN_THRESHOLD`
  - `LEDGER_IMPORT_SLO_ACTIVE_JOBS_WARN_THRESHOLD`
- 同项目导入互斥以数据库唯一索引 `uq_import_batches_one_processing_smart_job` 为准；内存状态仅作为本进程进度缓存，不作为跨实例锁

### 24.2 必备调试数据集

- 小样本正确数据（用于冒烟）
- 大体积 CSV/XLSX（用于性能）
- 多文件同名 sheet 冲突样本（用于映射冲突）
- 故障注入样本（缺列、错列、期间断档、编码异常）

### 24.3 常见问题排障路径

1. 卡在 `running`/`writing`
   - 检查 `heartbeat_at` 是否更新
   - 检查 worker/runner 日志和锁状态

2. 导入成功但前端显示失败
   - 对比 job 终态与 error payload 结构
   - 校验前端错误解析是否仍依赖旧字段

3. 回滚后数据未刷新
   - 检查 `/api/admin/import-event-health` 的 `outbox_summary.pending_count` / `failed_count`
   - 必要时调用 `/api/admin/import-event-replay` 重放激活/回滚事件
   - 检查事件订阅方是否消费和重算成功

4. 大文件导入异常
   - 检查上传分块与存储可用性
   - 检查内存峰值与解析阶段日志

### 24.4 联调检查清单

- [x] 新旧入口返回结构一致
- [x] `validation_summary` 与详情一致
- [x] 低置信字段正确进入人工确认
- [x] 激活失败不出现“假成功”
- [x] 回滚后读路径与下游结果一致
- [x] 导入历史/数据集/job/artifact 查询需 `readonly`，回滚/重试/取消需 `edit`

---

## 25. 附录：企业级演进背景与残余 backlog

本章吸收原《企业级平台下一阶段改造建议》中与**现状仍可对照**的部分；凡已在主文第 3～5 章、第 19～21 章展开的条目此处仅作索引，避免重复。

### 25.1 主链事实核对（相对早期规划的增量）

下列能力在早期文档中为「建议」，在当前仓库中已进入主链或可配置启用：

| 主题 | 代码落点（代表性） |
|------|-------------------|
| 上传产物 artifact + 可选 S3 | `ledger_import_upload_service.py`、`import_artifact_service.py`、`import_artifact_storage.py` |
| LedgerDataset staged/active/superseded + 四表 `dataset_id` | `dataset_models.py`、`dataset_service.py`、`smart_import_streaming` |
| ImportJob 状态机 + 独立 worker | `import_job_service.py`、`import_job_runner.py`、`workers/import_worker.py` |
| 激活/回滚事件 DB Outbox + 重放 | `import_event_outbox_service.py`、`main.py` 重放循环、`ImportEventConsumption` 幂等 |
| 结构化 validation / activation gate | `import_validation_service.py`、`LedgerImportApplicationService` |
| 主导入事件 `LEDGER_DATASET_ACTIVATED` | `dataset_service.activate`、`event_handlers` 订阅试算重算等 |

### 25.2 目标分层架构（仍为演进北极星）

```text
前端 / 向导
  → 统一导入 API（ledger/* 与 account-chart/* 入口层收口）
  → LedgerImportApplicationService
       ├── ImportArtifactService
       ├── ImportJobService / ImportJobRunner
       ├── smart_import_engine（解析与写库）
       ├── DatasetService（版本 / 激活 / 回滚）
       └── ImportEventOutboxService → EventBus → 下游重算与缓存失效
  → Worker（可选外置）
```

### 25.3 仍为开放式结构性 backlog

1. **读路径全面 dataset 语义**：核心聚合（如试算）已使用 `get_active_filter`；其余散落 `is_deleted=false` 的查询需逐项收口（见第 20～21 章）。
2. **导入事件语义双轨**：流式主链以 `LEDGER_DATASET_ACTIVATED` + outbox 为准；极少数遗留路径若仍发 `DATA_IMPORTED`，应避免与激活事件叠加导致重复全量重算——以静态扫描调用栈为准持续收敛。
3. **分布式锁 vs DB 唯一约束**：当前项目级并发以 DB 约束为主；多实例下是否引入 Redis/advisory lock 见第 17～20 章门禁 **GA-2**。
4. **校验规则三层模型**：Schema / Business / Activation gate 在产品语义上已部分落地，`ImportValidationService` 需持续规则清单化与版本治理。
5. **统一 REST 命名空间**：中长期可将 `POST .../ledger-import/artifacts|previews|jobs` 等为权威 API，现有路由以内转发兼容（见原改造建议 §6.3，实施节奏绑定灰度）。
6. **测试矩阵**：E2E、多入口一致性、性能回归门槛维持第 19～23 章要求。

### 25.4 原「P0 条目」落地快照（沿革）

原改造建议 §7.1「当前落地状态（2026-04-27）」所述多条已由后续迭代覆盖：**统一应用服务门面**、**account-chart 转发**、**向导 upload_token**、**validation 结构化**、**write_four_tables fail-fast / 旧 upload 410** 等已在当前主链生效。未尽部分（前端双入口编排彻底抽象、后端 severity 单一体系等）已并入本文 **§5 P0-2 / P0-4** 与 **§21**。

### 25.5 推荐阅读路径

- **研发实施**：§5 → §20～§21 → §22～§23  
- **运维值班**：§14 → §19 → §24  
- **架构评审**：§4、§10～§13、本章 §25.2～25.3
