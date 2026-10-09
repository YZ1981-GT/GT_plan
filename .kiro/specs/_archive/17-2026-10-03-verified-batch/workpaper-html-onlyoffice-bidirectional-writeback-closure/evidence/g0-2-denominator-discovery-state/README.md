# G0-2：8-spec 分母与 discovery-only 状态修正

> 状态：CLOSED
> 日期：2026-09-09
> 输出 milestone：`G0-2-DENOMINATOR-DISCOVERY-STATE-CORRECTED`

## 执行卡

<!-- G0-2-WORK-PACKAGE-JSON:START -->
```json
{
  "id": "G0-2",
  "name": "修正 8 个 spec 当前任务分母和 discovery-only 状态",
  "status": "CLOSED",
  "owner": "workpaper-html-onlyoffice-bidirectional-writeback-closure:program-governance",
  "producer_spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
  "input_gates": [
    "G0-1 clean-checkout generator/projection/guard 已通过",
    "8 个 tasks.md 的 checkbox 集合与 DAG waves/dependencies 集合一致",
    "五个待改 tasks.md 在开工前无工作树 diff",
    "范围锁死为 denominator/discovery-only；G0-3 与 G0-4 字节禁改"
  ],
  "output_milestone": "G0-2-DENOMINATOR-DISCOVERY-STATE-CORRECTED",
  "modified_files": [
    "docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md",
    ".kiro/specs/published-representation-production-path-and-lane-adjudication/tasks.md",
    ".kiro/specs/excel-structural-row-insertion-and-shift-aware-verification/tasks.md",
    ".kiro/specs/excel-workbook-wide-row-change-propagation/tasks.md",
    ".kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/tasks.md",
    "backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
    "backend/data/workpaper_sync_program_milestones.json",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-2-denominator-discovery-state/README.md"
  ],
  "targeted_tests": [
    "python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --apply",
    "python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --check",
    "rtk python -m pytest backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py -q --tb=short"
  ],
  "real_scenarios": [
    "真读 8 份 tasks.md，以生产 parser 与 DAG normalizer 重算全任务分母",
    "从 optional(*) 语法重算 Published 28/43 与 Structural 22/27 双口径",
    "把标题要求生产迁移但正文仅交付调查、门或裁决的 core Task 1/2/20/60/62/64 诚实降为 partial",
    "重生成 projection 后证明 DAG 未变、milestone 未提升且数据库探针仍为 read-only"
  ],
  "rollback": {
    "strategy": "只回退 G0-2 的精确文档、checkbox、守卫与 evidence hunks，再由 generator --apply 重建旧投影；禁止手改 generated JSON、reset 共享索引或回退其他 owner 内容",
    "data_migration": false,
    "reversible": true
  },
  "evidence_path": ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-2-denominator-discovery-state/README.md"
}
```
<!-- G0-2-WORK-PACKAGE-JSON:END -->

## 输入门实证

- G0-1 clean synthetic commit：`b4459a92c783b6335406a758ff38515d161a2392`。
- clean bootstrap：MigrationRunner 首次 `157 executed / 0 failed`，二次 `[] / []`。
- G0-1 clean projection digest：`efaa05eec717c89b743f2881a22cc035000eadb76643706db755ad79edb0dd1c`。
- G0-1 targeted guard：`16 passed, 2 warnings`。
- PostgreSQL 独立取证：V159 required constraints `23/23 present + validated`，V147 domain constraints `7/7 present + validated`。
- 开工前 Git 精确路径检查：五份待改 spec `tasks.md` 均无 staged/unstaged 状态；总控、program guard 与 generated projection 属本 program-governance 已 staged 输入。

主工作树直接运行 generator 的数据库探针因本机默认连接不可达而 fail-closed；本包未降级或 skip。最终 `--apply/--check/pytest` 使用 synthetic clean checkout + 一次性 PostgreSQL 执行。

## owner 裁决：discovery-only 范围

总控 §2.3 规定：调查/characterization 完成而生产能力未交付时必须用 `[~]`。core 下列六项均满足该条件：

| Task | 标题承诺 | 当前已交付事实 | 裁决 |
|---|---|---|---|
| 1 | 全量入口 manifest 与归一化清册 | discovery/characterization | `[x] → [~]` |
| 2 | 假双向红基线与能力态守卫 | characterization 红基线 | `[x] → [~]` |
| 20 | 关闭 writer/version domain gate | 门可信，但债未清零 | `[x] → [~]` |
| 60 | F2 迁成统一 Word adapter 并 finalize | 只交付勘查/欠账登记，adapter/finalize 未交付 | `[x] → [~]` |
| 62 | 迁移 18 个 generic DOCX entry | 只交付裁决与守卫，0 个 entry 迁移 | `[x] → [~]` |
| 64 | 迁移 A16/A17 Word 链与宿主 | 只交付裁决，未注册 adapter/finalize | `[x] → [~]` |

Task 63、61、71、72、74、75 已为 `[-]`，保持不变。其他 spec 中已完成任务未发现同类“标题要求生产交付、正文承认仅调查”的显式冲突。

## 分母单一口径

| Spec | 主任务（非 optional） | 全任务（含 optional） | optional(*) |
|---|---:|---:|---:|
| core | 77 | 77 | 0 |
| Published | 28 | 43 | 15 |
| Structural | 22 | 27 | 5 |
| Workbook | 30 | 30 | 0 |
| Custom | 19 | 19 | 0 |
| Template | 27 | 27 | 0 |
| Guidance | 23 | 23 | 0 |
| Formula | 15 | 15 | 0 |
| **合计** | **241** | **261** | **20** |

G0-2 完成后全任务状态为：`completed=238 / partial=16 / blocked=7 / pending=0`；core 为 `66 / 6 / 5 / 0`。Published 为 `28/28 主任务、43/43 全任务`；Structural 为 `21/22 主任务、26/27 全任务`。

## 禁碰边界

- G0-3：core DAG 中 Task 72、Task 74、Wave 7 顺序与 `archive` gate 一个字节不改。
- G0-4：`HOST-CONSUMES-UNIFIED-PATH` producer、declared blocker 与任何 host/router/OnlyOffice 文件一个字节不改。
- 不修改 generator 的 checkbox parser 语义；generated JSON 只允许由 generator 原子生成。
- Custom、Guidance、Formula 三份 `tasks.md` 仅复核，无必要改动。

## 验收结果

- G0-2 synthetic commit：`822a280f117daf405dde7701f1ecb6d6bbd08fd6`；checkout 开始时工作树 clean。
- 隔离 PostgreSQL：`pgvector/pgvector:pg16`，数据库 `audit_platform`，host port `55432`；`vector` extension 成功创建。
- clean bootstrap：`init_tables.py` 加载 85 个模型并创建 313 张表；MigrationRunner 首次 `157 executed / 0 failed`，二次 `executed=[] / failed=[]`。
- 数据库探针：`status=ok`、`read_only_requested=true`、`read_only_verified=true`；关系/列/约束分别 `7/60/23`，全部 observed 等于 denominator；probe digest=`fac2c53b411d784ea21690d2a2077a7d9610fef9127682b9cec9b12d4391f405`。
- 新 source digest：`ae7c1ad401f2b94a8f1e76e5ea2fd933eb43a0c3347c8f3a65dcc332fa00dc2d`。
- 新 program digest：`76663be0d161b2d8504becbcc726aa5c0b55de63d50ff52904309bd5f5b3b178`。
- DAG 前后均为 `node_count=261 / internal_edge_count=445 / cross_spec_edge_count=114 / acyclic=true`；无 G0-3 边混入。
- milestone 前后均为 `BLOCKED=4 / IMPLEMENTED=3 / STALE=9 / REQUEST_PATH_VERIFIED=0 / ONLYOFFICE_VERIFIED=0 / CLOSED=0`，无任何提升。
- Task 72 依赖仍为 `67/68/69/70/71`，不含 Task 74；`archive_bypasses_writer_debt` 诊断仍存在，留给 G0-3。
- `HOST-CONSUMES-UNIFIED-PATH` 仍为 `BLOCKED`，producer tasks 仍为空，且 `host-consumes-unified-path.g0-4` 仍是唯一声明式实现包 blocker；未夹带 G0-4。
- generator `--apply` 与随后 `--check` 均通过；独立守卫结果：`17 passed, 2 warnings in 74.84s`。
- synthetic checkout 在生成后仅 `backend/data/workpaper_sync_program_milestones.json` 出现预期修改，目标文件 `git diff --check` 通过；clean source 与主工作树回写文件经 `git diff --no-index` 验证字节一致。
- 主工作树仅按精确路径暂存 generated projection 与本 evidence；未执行 `git add .`、未重置或覆盖其他 owner 内容。

结论：`G0-2-DENOMINATOR-DISCOVERY-STATE-CORRECTED` 已 CLOSED，可进入 G0-3；本结论不代表 G0-3 或 G0-4 已完成。
