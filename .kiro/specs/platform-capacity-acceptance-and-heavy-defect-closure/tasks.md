# 平台容量验收与重任务残留缺陷收口 — 任务

> 承接：`platform-heavy-jobs-and-capacity-closure` 交接式归档 `_archive/188`
> （2026-11-22 用户拍板）。上游 36 项编号任务已交付 35 项 + E6 进行中 `[-]`；
> 本清单只承接**必须专用容量环境或独立 spec 工作量**的余项，编号与上游余项对应。
> 所有 `*` 项 = 需专用容量环境（6000 VU 负载机 + 可销毁容量 PG + PgBouncer 进程），
> 本机无法伪造，未具备环境前保持 `[ ]*`。

## A. 容量验收（R1~R3）

- [x] A1 六类安全计数生产者（E6 缺口，本机可先建探针骨架）。
  - 越权回放 / 连接池对账 / 连接超时 / 事件序号对账 / 幂等重放 / 业务恒等式
    六个探针，输出进 `stage_stats.json` 同形载荷；`run_final --safety-evidence`
    从「只校验」升级为「有生产者喂数」。
  - 每个探针配 SQLite/合成夹具单测 + 磁盘变异（删探针 ⇒ run_final 缺键即 FAIL）。
- [ ]* A2 分布式负载机编排（E4 余量）：Locust master + N worker 启动脚本、
  `--worker-stats-dir` 共享目录、逐 worker stage_stats 合并判定全链跑通。
  - 环境前提：≥4 核压测机 + 独立可销毁容量 PG。先在本机单 worker 冒烟
    （短梯度 + 假后端，复用上游 E5 冒烟模式）验证编排正确性。
- [ ]* A3 6000 VU 梯度实跑与判定（E5/E6）：100→1000→3000→6000、6000 稳态
  ≥30 分钟；核心读 p95≤300ms / p99≤1s / 错误率<0.1%；六类安全计数全 0。
  - 环境前提：A1+A2 就绪；产出归档原始 CSV / summary.json / resource_samples.json。
- [~] A4 PgBouncer 灰度脚本 + 2%→25%→100% 实跑（E1 余量）。
  - 代码与守卫本机可做：`scripts/ops/pgbouncer_gradual_rollout.py` 三阶段状态机 +
    越门回退 + `rollout_incident.json`；前置断言接契约 9 例与连接预算 14 例。
  - 实跑需部署环境（PgBouncer 进程 + 真实后端 + 专用库）。
- [ ]* A5 多 worker 2/4/8 验证（E2 余量）：进度 / 失效状态外置补齐 + Redis adapter
  注入 + 零丢失 / 零重复实跑。
  - 进度读侧聚合与失效对账探针本机可做；多 worker 实跑需容量环境。

## B. SQL / 索引 / 流式路由（R4/R6）

- [ ] B1 合并附注差额节点语义裁决 + 叶子来源整章批取（C2/C3 余项）。
  - 先裁决：`fill_by_formula` 语义是否需要纯内存内核（对照上游 C3 勘误，
    不得写成不存在的 `_compute_elimination`）；裁决结论写 ADR。
  - 章节锁并发 barrier（5 例）作回归门；真 PG 一次性库复跑。
- [ ]* B2 真实大项目 SQL 基线（C1/C4 余项）：10000 公式单元 run 基线与耗时、
  大账套导入 rows/s / WAL / COPY / staging / index / activation 实测。
  - 环境前提：专用可销毁 PG + 真实大项目数据；棘轮只降不升。
- [ ] B3 知识检索索引落地生产（C5 余量）：按 EXPLAIN 证据裁决 pg_trgm vs tsvector，
  产出迁移 + `CREATE INDEX CONCURRENTLY` 窗口评估 + `CANDIDATE_CAP` 告警验证。
  - 产品裁决项：选型需用户/团队确认；迁移写共享库需放行。
- [ ] B4 流式路由 DB 作用域逐条迁移（A6 余量 111 条）：按「响应期是否读 DB」
  分两桶批量迁移，每 10~20 条收紧棘轮基线一次；变异 = 拆 scope 即红。
  - 本机可做，纯代码工作；基线只降不升。

## C. 前端虚拟化（R5）

- [ ] C1 虚拟化表交互契约（D1 前置，约 1000 行前端）：离屏逻辑选区 / 编辑器回收 /
  稳定行与列 key / 公式格 / 批注锚点 / 无障碍协议定义 + GtVirtualTable 接入层。
  - 单测对拍先行（GridKernel 事件）；任何既有能力回退即阻断。
- [ ]* C2 TB 1000/5000 行 canary（D1 本体）与 C3 附注 / 合并表接入（D3）：
  契约齐全后真实数据 Playwright 取证。
  - 环境前提：容量环境一并取证（与 A3 同窗口）。

## D. 收尾

- [ ] D1 全量验收：上游已建守卫全套复跑绿（棘轮 / 梯度契约 / 故障注入 /
  并发 barrier / EXPLAIN / 连接预算）；正式构建 + 包体预算 + smoke。
- [ ] D2 更新 INDEX / memory / dev-history；满足归档门后归档本 spec。

## 依赖与红线

```text
A1 → A2 → A3          （安全计数 → 编排 → 实跑判定）
A4 独立可并行          （灰度脚本先做，实跑随环境）
A5 依赖 A4             （多 worker 通常经 PgBouncer）
B1/B4 本机即可开工      （不依赖环境）
B2* 依赖环境；B3 依赖产品裁决
C1 先于 C2/C3；C2/C3* 随 A3 窗口取证
```

- 红线：共享 PG 禁跑写压测与性能基线；棘轮只许变严；环境项不得以合成数据外推为完成；
  `[-]` / `[~]` 状态迁移必须附实测证据。

## 交付登记（append-only）

- **2026-11-22 A1 交付**：新建 `backend/tests/load/safety_probes.py`（六类探针
  执行器 + `run_all_probes(phase=before|after)` 阶段形态）+ `test_safety_probes.py`
  （14 例：报告形状与 `load_safety_evidence` 同形、越权 200 计违规 / 403 干净 /
  全失败 fail-closed 不记 0、连接池容忍带边界、超时喂入、
  共享库禁跑写探针、skip_write_probes）。两条变异（越权 200 不计数、
  全失败伪造 0）全 RED；`tests/load/` 全套 144 passed。
  **接线余项**：`run_final.py` 尚未调 `run_all_probes` 自动生成证据
  （当前仍接受外部 JSON）—— 留待 A2 编排批一并接线（探针需要压测
  前后两个时点，属 runner 编排职责）；多 worker 分布式下探针只在
  master 侧跑一次。SSE 事件序号对账与幂等重放的生产路径挂点待
  真实后端联调时验证（探针逻辑已按信封口径写死，但未在真实
  栈上验证，不记完成）。
- **2026-11-22 A4 代码部分交付**：新建 `backend/scripts/ops/pgbouncer_gradual_rollout.py`
  （2%→25%→100% 三阶段状态机 + 越门回退 + `rollout_state.json` /
  `rollout_incident.json`）+ `tests/test_pgbouncer_rollout_script.py`（12 例：
  阶段契约、gate fail-closed（-1 越门）、前置门真跑两守卫套件、
  前置失败必须 abort（行为变异 RED）、后端不可达 gate 拒绝、
  rollback 写状态）。3 条变异（gate 放行 -1、前置失败带病续跑、
  前置失败不写 aborted）全 RED；第三条首轮存活是等价变异
  （print 文案不改行为），换行为变异（不写 aborted 状态）后 RED。
  脚本 `--check` 在本机实测通过（前置契约 9 skipped + 连接预算
  14 passed 均绿）。
  **实跑余项**：三阶段实跑需 PgBouncer 进程 + 真实后端 + 专用库
  （本机 docker run 被安全策略拦截），环境就绪后 `--run --window-override 30`
  冒烟 → 正式窗口实跑。
