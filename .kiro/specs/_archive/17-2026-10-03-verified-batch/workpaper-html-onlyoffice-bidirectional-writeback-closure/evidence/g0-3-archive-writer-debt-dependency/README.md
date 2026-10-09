# G0-3：archive 必须晚于 writer debt 归零

> 状态：CLOSED
> 日期：2026-09-09
> 输出 milestone：`G0-3-ARCHIVE-DEPENDS-ON-WRITER-DEBT`

## 执行卡

<!-- G0-3-WORK-PACKAGE-JSON:START -->
```json
{
  "id": "G0-3",
  "name": "补核心 Task 72 → Task 74 依赖并锁死合法 Wave 顺序",
  "status": "CLOSED",
  "owner": "workpaper-html-onlyoffice-bidirectional-writeback-closure:program-governance",
  "producer_spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
  "input_gates": [
    "G0-2-DENOMINATOR-DISCOVERY-STATE-CORRECTED 已 CLOSED",
    "当前 clean projection 为 261 nodes / 445 internal edges / 114 cross-spec edges",
    "archive_bypasses_writer_debt 当前仅因 Task 72 缺少 Task 74 依赖而存在",
    "G0-4 HOST-CONSUMES-UNIFIED-PATH definitions、生产宿主和八项谓词全面冻结"
  ],
  "output_milestone": "G0-3-ARCHIVE-DEPENDS-ON-WRITER-DEBT",
  "modified_files": [
    "docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md",
    "backend/scripts/gen/generate_workpaper_sync_program_milestones.py",
    "backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
    "backend/data/workpaper_sync_program_milestones.json",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-3-archive-writer-debt-dependency/README.md"
  ],
  "targeted_tests": [
    "python -m py_compile backend/scripts/gen/generate_workpaper_sync_program_milestones.py backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
    "python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --apply",
    "python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --check",
    "rtk python -m pytest backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py -q --tb=short"
  ],
  "real_scenarios": [
    "Task 74 留在 Wave 7，Task 72 单独进入 Wave 8，执行顺序固定为 Task 71 → Task 74 → Task 72",
    "Task 72 dependencies 增加 Task 74 后 internal edge 445→446，archive_bypasses_writer_debt 诊断消失",
    "删除 72→74 的行为变异必须恢复 445 edges 与 archive_bypasses_writer_debt",
    "把 Task 72 放回 Wave 7 的同 Wave 前向依赖变异必须被 dependency-order guard 拒绝",
    "HOST-CONSUMES-UNIFIED-PATH 仍 BLOCKED、producer tasks 仍为空且 G0-4 declared blocker 不变"
  ],
  "rollback": {
    "strategy": "只回退 G0-3 的 Task 72/74 Wave 与 dependency hunk、dependency-order guard、测试、projection 和 evidence；由 generator --apply 重建旧投影，不回退 G0-2 或其他 owner 内容",
    "data_migration": false,
    "reversible": true
  },
  "evidence_path": ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-3-archive-writer-debt-dependency/README.md"
}
```
<!-- G0-3-WORK-PACKAGE-JSON:END -->

## 开工基线

- G0-2 program digest：`76663be0d161b2d8504becbcc726aa5c0b55de63d50ff52904309bd5f5b3b178`。
- DAG：`node_count=261 / internal_edge_count=445 / cross_spec_edge_count=114 / acyclic=true`。
- diagnostics：7 条，其中 `archive_bypasses_writer_debt` 指向 core Task 72、缺失依赖 74。
- Task 72 当前依赖：`67/68/69/70/71`；Task 74 当前依赖：`20/71`；二者均为 `[-]`。
- 全任务状态：`completed=238 / partial=16 / blocked=7 / pending=0`。
- milestone：`BLOCKED=4 / IMPLEMENTED=3 / STALE=9`，无 verified/closed。

## Wave 规则裁决

core tasks 明文要求：每个依赖必须来自更早 Wave，或同 Wave 的更小任务号。因此不能只在同属 Wave 7 的 Task 72 上追加较大任务号 74；仅调整 Wave 7 数组顺序也不能改变该规则。

本包采用无例外裁决：

1. Wave 7 保留 Tasks 68/69/70/71/74，完成独立验证、逐 entry evidence 与 writer/version domain 归零；
2. 新增 Wave 8，仅含 Task 72，依赖 Wave 7；
3. Task 72 dependencies 增加 74，并在 Stage A 消费 Task 74 的 14 条 writer gate 全零结果；
4. generator 对所有 8 个 spec 执行“更早 Wave 或同 Wave 更小任务号”校验，不保留 G0-3 特例。

开工前对当前 8-spec graphs 执行只读扫描，违反该规则的现存依赖为 `[]`，因此新增通用 guard 不会把既有合法 DAG 误伤。

## 禁碰边界

- 不改变 Task 72/74 的 `[-]` 状态，不伪造 writer debt 已归零或 archive 已完成。
- 不改变 `archive` gate owner（仍为 Task 72）。
- 不修改 definitions 中 `HOST-CONSUMES-UNIFIED-PATH` 的空 producer、consumer 集、required state 或 G0-4 declared blocker。
- 不修改任何 host/router/OnlyOffice/前端生产路径，不实施 G0-4 八项谓词。
- G0-1/G0-2 evidence 是历史快照，不回写其中的 445-edge 与 diagnostic 事实。

## 验收结果

- G0-3 synthetic commit：`d91fb0d475a141592fa050424ba8e742503d407d`；checkout 创建后工作树 clean。
- 隔离 PostgreSQL：`pgvector/pgvector:pg16`，数据库 `audit_platform`，host port `55432`；`vector` extension 创建成功。
- clean bootstrap：`init_tables.py` 加载 85 个模型并创建 313 张表；MigrationRunner 首次 `157 executed / 0 failed`，二次 `executed=[] / failed=[]`。
- 数据库探针继续为 `status=ok`、`read_only_requested=true`、`read_only_verified=true`；probe digest=`fac2c53b411d784ea21690d2a2077a7d9610fef9127682b9cec9b12d4391f405`，与 G0-2 相同。
- 新 core tasks source digest：`dd198d9ae473f69fae734f48225ac721f0422f3aac64c5f5e68c2163cb297f63`。
- 新 source digest：`1e395bff096b424807f5177abbc5b0978389a9110e6b13e83688d707a8576bce`。
- 新 program digest：`7df4d54371f9e4118105093f54fc39e2c3cc88f11b3a8fbd83f00ea52f48cf5b`。
- DAG：`node_count=261`、`internal_edge_count=446`、`cross_spec_edge_count=114`、`acyclic=true`；相对 G0-2 只新增 72→74 一条内部边。
- diagnostics：`7→6`，删除且只删除 `archive_bypasses_writer_debt`；其余 6 条 blocker 保持，program 仍为 `STALE`。
- Task 74 保持 Wave 7，Task 72 独立进入 Wave 8 并依赖 `67/68/69/70/71/74`；`archive` gate owner 仍为 Task 72，Task 72/74 状态均仍为 `[-]`。
- 行为变异一：从内存 facts 删除 72→74 后重算，internal edge 恢复 445，且精确恢复 `archive_bypasses_writer_debt(task=72, missing_dependency=74)`。
- 行为变异二：把 Task 72 放回 Wave 7 后重新 normalization，命中 `same-wave non-earlier tasks` 并抛 `ProgramMilestoneError`；当前 8-spec graphs 的同 Wave 非前序依赖为零。
- task 状态仍为 `238 completed / 16 partial / 7 blocked / 0 pending`；milestone 仍为 `4 BLOCKED / 3 IMPLEMENTED / 9 STALE / 0 verified / 0 CLOSED`，无提升。
- `HOST-CONSUMES-UNIFIED-PATH` 仍为 `BLOCKED`，producer tasks 仍为空，consumer、required state、evidence refs 与 `host-consumes-unified-path.g0-4 / implementation_package_pending` 均不变；未夹带 G0-4。
- 无数据库预检：generator/test `py_compile` 通过；直接解析 8-spec graph 得到 `9 Waves / 446 internal edges / 6 diagnostics`。
- clean checkout：generator `--apply`、随后 `--check` 均通过；独立守卫 `20 passed, 2 warnings in 76.42s`。
- synthetic checkout 生成后仅 projection 出现预期修改，目标 `git diff --check` 通过；clean source 与主工作树回写 projection 经 `git diff --no-index` 验证字节一致。
- 主工作树仅精确暂存本执行卡、core DAG/正文、通用 dependency-order guard、program 守卫、总控链接与 generated projection；未执行 `git add .`，未重置或覆盖其他 owner 内容。

结论：`G0-3-ARCHIVE-DEPENDS-ON-WRITER-DEBT` 已 CLOSED，可进入 G0-4；本结论不代表 writer debt、Task 72 archive 或 G0-4 八项谓词已完成。
