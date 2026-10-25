# 设计：交付中心三件套一键出具

## 一、设计目标与阶段边界

阶段四把阶段二/三已经定义的下游结果收敛为一个可审计的交付 job。公式管理仍是推送中枢，试算表未审数继续由映射聚合，审定数继续由 phase3 的唯一写入函数维护；交付中心不重算业务金额，只验证、快照、编排和固化文件。

正式 trio 的语义是：

```text
readiness(project, year)
  -> immutable delivery_snapshot
  -> financial_report (.xlsx)
  -> disclosure_notes (.docx)
  -> audit_report (.docx)
  -> file fingerprint verification
  -> trio succeeded
```

`financial_report_unadjusted` 如需保留，作为内部对照步骤放在实现的辅助区域，不进入 `TRIO_STEPS`、完成计数、正式下载集合或 success gate。旧 `/full-package` 可以继续服务兼容调用，但不能成为正式三件套的编排入口，也不能绕过 readiness、快照和文件校验。

依赖关系必须显式记录：phase3 的推送引擎入库、调整复核/撤回、TB 审定数单一写入方和附注主表交接未在目标 HEAD 成立时，phase4 的 readiness 返回 `blocked`，而不是读工作树文件或回退到旧路径生成文件。

## 二、复用现有实现

| 能力 | 复用模块 | phase4 责任 |
|---|---|---|
| 任务编排 | `FullDeliverablesExecutor` | 固定 trio 顺序、独立保存点、状态和 attempt |
| 财务报表 | `ReportExcelExporter` / 现有 financial report service | 传入 snapshot 上下文，完成后验证文件 |
| 报表附注 | `NoteWordExporter` / 现有 disclosure exporter | 只消费已交接章节，绑定 template_type 和 snapshot |
| 审计报告正文 | `TemplateFillService` / `report_body` 步骤 | 使用同一报表/附注快照，不重新取漂移数据 |
| 文件生命周期 | `DeliverableService` / 版本链 | 先落盘和校验，再建成功版本；绑定哈希 |
| 任务查询 | `ExportJobService` | item/attempt 历史、重试、状态聚合 |
| HTTP 边界 | `deliverable.py` / `word_export.py` | readiness、创建、查询、重试和下载鉴权，统一 commit |
| 前端 | `DeliverableCenter.vue` / `deliverableApi.ts` | trio 状态、失败原因、重试入口、中文提示 |

不复用的路径：旧的 `WordTemplateFiller.fill_full_package` 只作为兼容/对照，不作为 phase4 主路径；它不能创建 phase4 snapshot，也不能更新 trio item 的成功状态。

## 三、数据模型与迁移

优先扩展现有 `export_jobs`、`export_job_items`、`deliverable_versions`，避免另建平行生命周期。若现有表无法表达历史重试，则新增 `export_job_attempts`；等价实现必须保留不可变失败记录。

### 3.1 job

job 至少需要：

- `project_id`、`year`、`snapshot_id`、`status`（`queued/running/succeeded/partial/failed/blocked`）；
- `kind=deliverable_trio`；
- `trio_total` 固定为 3，`trio_succeeded` 只统计正式三件套；
- `readiness` 的阻断/警告摘要；
- `created_by`、`created_at`、`started_at`、`finished_at`。

### 3.2 item

item 至少需要：

- `step_key`：`financial_report`、`disclosure_notes`、`audit_report`，辅助步骤用独立非 trio key；
- `sequence` 固定为 1、2、3；
- `status`：`queued/running/succeeded/failed/blocked/skipped`；
- `snapshot_id`、`version_id`、`file_path`、`file_size`、`file_sha256`；
- `attempt_count`、`last_attempt_id`、`error_message`、`finished_at`。

不允许用显示名称作为稳定键；名称由前端中文映射，后端状态和统计使用上述固定 key。

### 3.3 attempt

`export_job_attempts` 是 append-only：

- `id`、`job_id`、`item_id`、`attempt_no`、`status`；
- `started_at`、`finished_at`、`snapshot_id`；
- `error_type`、`error_message`、`diagnostic_detail`；
- `file_path`、`file_size`、`file_sha256`、`version_id`；
- `created_by` 和触发来源（初次生成/用户重试/恢复）。

同一个 item 的 `attempt_no` 唯一递增。失败 attempt 永不覆盖；重试只能新增 attempt 并更新 item 的当前投影。若已有运行中的 attempt，重试端点返回冲突而不追加第二个执行。

### 3.4 snapshot

可以复用已有交付版本的综合指纹，也可以新增 `deliverable_snapshots`。语义必须不可变：规范化 JSON 中包含项目/年度/准则、TB/调整/公式推送/报表/附注/底稿指纹、状态时间点和 phase3 readiness 版本。对同一输入生成相同 digest；生成时间作为元数据，不参与内容 digest。

snapshot 建立后，所有 trio item 必须引用它。若执行中发现下游数据指纹变化，当前 item 失败并说明“源数据在生成过程中发生变化”，不能悄悄换成新快照。

## 四、readiness、stale 与状态接口

### 4.1 服务层

新增或扩展 `DeliverableReadinessService`，提供纯判定入口：

```python
readiness = await service.check(db, project_id, year, *, include_file_checks=True)
```

返回结构：

```json
{
  "status": "ready|blocked|ready_with_warnings",
  "hard_blockers": [
    {"code": "tb_snapshot_missing", "message": "试算表快照不存在", "evidence": {}}
  ],
  "warnings": [],
  "sources": {"tb": {}, "formula_push": {}, "adjustments": {}, "reports": {}, "notes": {}},
  "snapshot": {"id": "...", "digest": "..."},
  "trio": {
    "total": 3,
    "steps": [
      {"key": "financial_report", "sequence": 1, "status": "ready"},
      {"key": "disclosure_notes", "sequence": 2, "status": "ready"},
      {"key": "audit_report", "sequence": 3, "status": "ready"}
    ]
  }
}
```

`check` 必须以现有模型和 service 的真实字段判定，不用“有行就算完成”的弱口径。phase3 尚未提供的能力返回明确 blocker code，便于后续实现接通时去掉 blocker，而不是改成恒绿。

### 4.2 硬闸门

硬闸门分为：

- `upstream_not_ready`：四表/TB/公式推送/调整确认/审定数/附注交接未达到契约；
- `stale_source`：任一正式输入 `is_stale=True` 或版本链 `drift_blocked=True`；
- `snapshot_inconsistent`：TB、报表、附注、底稿指纹无法组成同一快照；
- `missing_template_or_standard`：准则、模板、年度不唯一；
- `missing_file` / `unreadable_file` / `file_hash_mismatch`：历史版本引用的文件不满足物理校验。

硬闸门按稳定 code 去重；证据保留数据源和路径，但不把机器绝对路径作为 snapshot digest 的输入。

### 4.3 软闸门

warning 仅承载不阻断质量信息，例如辅助未审报表未生成、非正式历史版本存在、某非核心来源缺少优化索引。warning 进入 job/readiness 审计记录，前端用“提示”状态显示，不可被统计为 blocker，也不能覆盖 blocker。

### 4.4 HTTP 接口

建议在现有交付路由下增加：

- `GET /api/projects/{project_id}/deliverables/readiness?year=`：只读项目权限；
- `POST /api/projects/{project_id}/deliverables/trio`：项目编辑/交付权限，重新检查 readiness 后创建 job；
- `GET /api/projects/{project_id}/deliverables/jobs/{job_id}`：只读项目权限；
- `POST /api/projects/{project_id}/deliverables/jobs/{job_id}/retry`：项目编辑/交付权限，只接受失败 item；
- `GET /api/projects/{project_id}/deliverables/items/{item_id}/download`：只读项目权限，下载前校验物理文件和 hash。

所有写端点由 router 统一 commit；service 只 flush。响应沿用 `ResponseWrapperMiddleware` 的业务信封，不以 HTTP 200 代替业务状态。

## 五、文件 fail-closed 与版本一致性

### 5.1 `render_and_store` 新边界

将 `DeliverableService.render_and_store` 拆成逻辑上连续的四段：

1. 在唯一临时路径生成文件；
2. `fsync`/原子移动到最终存储路径；
3. 对最终路径执行 `is_file`、可读、`stat().st_size > 0`、SHA-256；
4. 校验通过后才 `create_version`、绑定 `file_sha256`/`file_size`/`snapshot_id` 并 `flush`。

第 2 或第 3 段失败时删除当前 attempt 产生的临时/最终文件（不删除历史有效版本），抛出带阶段和路径的异常；不调用 `create_version`。若业务需要保存失败记录，失败记录写在外层 attempt savepoint 或主事务中，不与成功版本共享回滚边界。

版本复用必须调用同一 `verify_file_fingerprint(version)`；不能只判断 `file_path` 非空。下载接口也调用该函数，避免数据库状态和磁盘状态漂移。

### 5.2 指纹函数

统一一个 `compute_file_fingerprint(path) -> {size, sha256}`，读取采用分块方式；路径必须限制在配置的交付根目录下，防止版本记录指向任意文件。`verify_file_fingerprint` 比较数据库记录的路径、大小、哈希，并将权限/可读性错误转换成明确的业务异常。

snapshot digest 不含绝对路径和当前时间；文件 hash 属 item/attempt/version 记录，三件套 snapshot 只绑定源输入和生成上下文。

## 六、executor 的 savepoint 与顺序

`FullDeliverablesExecutor` 由“每步捕获异常继续”改为显式编排：

```python
for step in TRIO_STEPS:
    item = await job_repo.start_item(step, snapshot)
    attempt = await attempt_repo.start(item, trigger)
    try:
        async with session.begin_nested():
            artifact = await self._run_step(step, snapshot)
            verified = await self.deliverable_service.verify_artifact(artifact, snapshot)
            await job_repo.mark_item_success(item, verified)
            await session.flush()
    except Exception as exc:
        await job_repo.mark_attempt_failed(attempt, exc)
        await job_repo.mark_item_failed(item, exc)
        await session.flush()
        continue
```

上面的伪代码表达两个边界：成功步骤的版本和 item 状态在外层事务保留；失败步骤在自己的 savepoint 内回滚业务写入，但失败 attempt 在 savepoint 外记录。每一步都必须从 `TRIO_STEPS` 得到 sequence，不以字典遍历顺序或文件名排序为准。

步骤是否继续由需求裁定：正式 trio 的其余步骤可以继续执行以便一次展示完整失败清单，但失败项绝不能阻断已成功项、也绝不能被计入 trio 成功。对于明确依赖前置文件的 `audit_report`，如果输入 item 失败，audit item 应记录 `blocked_by_dependency`，而非伪装成导出器异常；它可以在 retry 时依赖成功项重新执行。

executor 完成后按正式三件套聚合：

- 三项成功且每项文件校验通过：`succeeded`；
- 有 blocker：`blocked`；
- 无 blocker 但部分失败：`partial`；
- 三项均失败：`failed`。

router 在所有步骤完成后统一 commit；服务不 commit。异常不能用裸 `except` 吞掉，日志与 attempt 记录应同时包含可诊断异常链。

## 七、retry 的真实执行路径

`ExportJobService.retry_failed` 不再只是批量更新状态。它应：

1. 锁定 job、item 和 snapshot，确认 job 属于请求 project；
2. 找出 `status=failed` 且 snapshot 仍有效的 trio item；
3. 为每个 item 创建新的 attempt；
4. 调用 executor 的按步骤入口 `_run_step(step_key, snapshot)`，走同一渲染、落盘、指纹和版本流程；
5. savepoint 成功则写 success 投影，失败则只新增失败 attempt 并保留旧失败；
6. 重新计算 job 状态和 trio 完成数，由 router commit。

重试时不重跑已成功且指纹仍有效的 item。若 snapshot 不再匹配 readiness，返回 `409` 或创建新 job；不能将新旧来源混入一个 job。重试接口和创建接口共享权限依赖，且端点级 TestClient 测试必须通过真实依赖链。

失败原因保留策略：item 的 `error_message` 显示最近一次失败，attempt 列表显示完整历史；前端刷新 job 不得用空数组覆盖历史 attempt。

## 八、前端设计

`DeliverableCenter.vue` 维护三个层次：

1. readiness 顶栏：硬阻断、软 warning、snapshot digest/状态和“重新检查”；
2. trio 步骤列表：固定顺序和中文名称，状态、尝试次数、文件大小/哈希验证结果；
3. job 详情：每个失败项的原始原因、历史尝试和“重试”按钮。

`deliverableApi.ts` 的类型显式区分 `TrioStepKey`、`ReadinessResult`、`ExportJobItem` 和 `ExportJobAttempt`，不能用可选英文字段拼状态。重试按钮调用真实 retry API，成功后继续轮询；`blocked` 不显示重试，而显示“重新检查前置链”。

单件生成/下载如果后端返回 `platform_persist_failed`、`missing_file` 或 `file_hash_mismatch`，前端不触发浏览器下载成功提示，显示中文错误并保留 item 失败状态。三件套完成按钮只在 readiness ready 且 trio 三项成功后显示成功。

用户可见文本示例：`交付前检查未通过`、`文件未落盘，无法出具`、`文件指纹不一致`、`第 2 次尝试`、`重试`、`已生成 2/3 项`。技术诊断可在展开区显示 `SHA-256` 和 `snapshot_id`。

## 九、与其他 spec 和旧路径的边界

- phase2：提供公式推送规则、E1 binding、运行记录和 dry-run 语义；phase4 只消费成功/已确认状态，不复制规则。
- phase3：提供 binding 单一真源、调整复核/撤回事件、TB 底稿调整分量、附注主表后端交接和 K1 接入；若这些能力未在 HEAD 入库，readiness 必须阻断。
- 旧 `full-package`：保留兼容，但正式 trio job 不调用它作为主编排；旧接口返回 blob 的历史行为不能证明 phase4 成功。
- 并行 spec：`deliverable-lineage-wiring-and-writeback-closure` 等旧交付件 spec 的已完成能力只按现有实现核验，不修改归档文档；共享 service/router/frontend 文件先比较工作树和 HEAD，再按 hunk 编辑。
- 生产数据库真实写入、真实立即出具和 Playwright 全链路需要用户授权；未授权只能执行 dry-run、文件故障注入和零痕迹验证。

## 十、测试策略与变异证明

### 10.1 基线顺序

每个改动先建立“修复前红”证据：先对当前实现运行新增测试，记录失败断言；再实现修复，运行同一命令转绿；最后对关键不变量做最小故障注入，确认改回旧行为再次变红。不得用“函数被调用”作为唯一证据。

### 10.2 关键测试矩阵

| 领域 | 修复前红 / 修复后绿 | 必须存活的故障注入 |
|---|---|---|
| readiness | service + TestClient | 去掉 stale/快照/文件 blocker |
| 三件套顺序 | SQLite executor integration | 调换步骤或把 unadjusted 算正式项 |
| fail-closed | 文件系统注入 + version assertions | 在文件失败后先 `create_version` |
| savepoint | SQLite 真 ORM | 去掉 `begin_nested()`，断言失败步骤写入残留 |
| retry | executor 真步骤入口 | 只 reset status，不调用生成/校验 |
| 权限 | TestClient 403 + 零写入 | 只校验登录 / 去项目边界 |
| 前端 | Vitest 真挂载 | 隐藏失败项 / 重试按钮 / 下载假成功 |
| 真 PG | 临时 schema / 事务回滚 | commit dry-run 或绕过约束 |
| 浏览器 | Playwright 状态流程 | 清空失败原因或显示假成功 |

### 10.3 真 PG 和 clean HEAD

SQLite 仅用于快速验证 ORM 状态机和 savepoint；PG 负责验证迁移、锁、约束和真实回滚。真项目仅事务内 dry-run，前后按行/版本/文件指纹对账；未经用户确认不执行正式写库。

交付前建立临时 clean worktree，以目标 HEAD 为基线运行 phase2/phase3/phase4 定向测试。输出必须区分：HEAD 预存失败、并行工作树未提交导致的失败、本阶段改动导致的失败。只有 clean HEAD 中生产模块和测试均被 `git ls-files` 覆盖，才允许勾选收尾任务。

## 十一、实施顺序

1. 现状扫描与基线测试，确认现有表、路由、版本链和前端状态。
2. readiness/snapshot 及迁移/ORM，先建立 fail-closed 状态。
3. 文件指纹和 `render_and_store`，用故障注入堵住假成功。
4. executor 固定顺序、savepoint 和 attempt 记录。
5. retry API 和真实步骤重执行。
6. 前端状态、失败项和重试入口。
7. SQLite/PG/TestClient/Playwright/clean HEAD 分层验收。

任何步骤发现 phase3 尚未落库，记录为依赖 blocker 并保持 phase4 对外 fail-closed，不用工作树能力伪造完成。
