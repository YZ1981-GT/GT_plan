# 设计文档：合并运行与底稿生命周期收口

## 0. 设计结论

本轮以 `consol_operation` 作为一次正式合并运行的根身份，扩展而不替换已有 `ConsolContext`。`elimination_entries` 继续是唯一调整/抵销来源，`consol_calc_basis` 继续是金额内核，V186 映射链继续是单体附注明细来源。页面、导出、工作底稿包和签字快照全部引用同一 operation；通用报表来源信封、附注写入方与附件 readiness 复用其 owner spec，禁止建立平行真源。

## 1. 现状复核与取舍

| 事项 | 当前证据 | 裁定 |
|---|---|---|
| 假转换 | `ConsolidationIndex.applyConsolConversion` 不消费编辑规则、不写后端，报表 GET 不收模板口径 | 删除“应用转换”；项目口径只读，真正变更走项目设置 |
| 假节点刷新 | `consol-refresh-entity` 只清缓存/GET，`worksheet` 未消费 | 改名“重新读取”；计算统一走 operation |
| dirty | 附注有局部保护，worksheet 无统一 dirty；首次加载可编辑并整体 reset | 新建工作区 draft registry，父页统一 guard |
| 四张抵销后表 | 仍读 `elimEquity/elimIncome` 默认骨架 | 服务端 projection 只读 canonical entries |
| 草稿生成 | 浏览器上传计算后 groups，无 sheet version | 服务端按 version vector 现读重算 |
| 报表双时点 | 页面读时算，导出读 `financial_report` | 正式视图与导出读同一 report run；实时预览显式分栏 |
| 快照不完整 | 未抓 worksheet JSON/ConsolNoteData，单源失败仍可 sign | 诊断可 partial，签字 fail-closed |
| 运行记录分裂 | 内存 refresh job + `ConsolPushRun` | operation 为根；旧记录作为兼容子记录 |
| 上下文 | 已有 frozen `ConsolContext` | 扩展 version vector，不新建同义 RunContext |
| 工作底稿身份 | `ConsolWorksheetData` 无 wp_id，证据只认 WorkingPaper | 每项目年度一个薄壳，不复制业务数据 |
| 迁移 | 2026-11-01 实施时重扫主树未提交文件最高 V239、origin 最高 V234；共享库连接被拒 | 本批取 V240；共享库恢复后执行前必须再查 `schema_version`，若已占用则重编号未推送一侧 |

## 2. 核心数据模型

### ADR-CRW-001 `ConsolOperation`

新增 `consol_operation`：`id/project_id/year/operation_type/idempotency_key/request_hash/context_json/version_vector/status/revision/lease_owner/lease_expires_at/heartbeat_at/steps/errors/result_refs/metrics/trigger_source/triggered_by/queued_at/started_at/finished_at/superseded_by`。状态为 `queued/running/succeeded/partial/failed/stale/cancelled`；唯一索引约束同项目年度 active operation，服务层用 advisory lock + revision CAS 处理兼容数据库。新触发若 active 存在，只更新一个 pending revision；worker 用短事务 claim/heartbeat，不长期占数据库连接。

### ADR-CRW-002 `ConsolVersionVector`

`version_vector` 规范键：`tree_revision/tree_fingerprint/worksheet_versions/tb_digest/elimination_digest/formula_digest/note_mapping_digest/template_digest`。构建时批量读取，规范 JSON 后 SHA-256。每阶段写入前及最终发布前重算相关键；不一致则 operation=`stale`，不得发布旧结果。`ConsolContext.run_id=operation.id`，现有 `source_version/formula_version/template_version` 写对应 digest；完整向量保存在 operation，不把 frozen schema 膨胀成任意 JSON。

### ADR-CRW-003 报表运行与 artifact

复用 `formula-provenance-envelope` 规划的 `report_generation_run`、`financial_report.run_id/provenance`；本轮实现其报表域最小闭环并让 `ConsolOperation.result_refs.report_run_id` 指向它。根节点正式报表物化到 `financial_report` 并带 run_id；页面正式模式按 run_id 读取，实时预览仍调用当前 read-time view 且显式标“未发布”。导出先校验 requested run 是最近成功 operation 的 report run，再读取同一批行。新增 `consol_artifact` 保存工作底稿包路径、hash、size、run_id 和生成状态；POST 生成一次，GET 只下载已生成文件。

### ADR-CRW-004 四表 projection 与草稿来源

新增 `consol_post_elimination_projection` 服务，不新增事实表。输入为同一 `CalcBasis`、approved entries、工作表 manual overrides，输出资本公积、抵销后长投、抵销后投资收益、少数股东权益损益 DTO；自动列只读。`generate-from-worksheet` 新契约 `{year, source_sheet_keys, expected_versions, preview_token, dry_run}`；服务端批量 `SELECT ... FOR UPDATE` 工作表、校验 version、调用与前端现有 `elimSourceGroups` 对拍的 Python canonical builder。预览 token HMAC/摘要绑定 project/year/versions/groups；写入前二次校验。`EliminationEntry` 增 `source_version/source_digest`，已提交/已审批不覆盖。

### ADR-CRW-005 附注来源投影

`ConsolNoteData` 墘 `source_mode/source_operation_id/source_revision/source_digest`；`source_mode` 为 `detail_mapping/subtree_aggregate/formula/manual/mixed`。整章字段只是快速投影，格级所有权仍以已有 `manual_cells/locked_cells/_detail_provenance/_subtree_provenance/last_formula_value` 为准。写入器通过共享 helper 更新投影；`reaggregate_subtree` 对 confirmed + 非 stale 映射自动执行，未确认/stale 进入 readiness 待办。公式与映射写入按 owned cell 集合交集检查，手工/锁定永远优先。

### ADR-CRW-006 薄底稿壳

新增 `consol_workpaper_instance(project_id,year,working_paper_id,latest_operation_id,latest_artifact_id,version)`；创建时幂等生成保留编码 `A3-CONSOL` 的 `WpIndex` 与 `WorkingPaper`，`file_path` 指最近 immutable artifact，业务 JSON 不写 `parsed_data`。通用证据使用 `EvidenceLink.wp_id/sheet_name/cell_ref`，其中 cell_ref 采用稳定 `node:<key>/row:<identity>/col:<identity>`，禁止仅用行号。复核、负责人、回收站和归档复用 WorkingPaper；archive inventory 增合并 provider，只读取成功 operation/artifact。

### ADR-CRW-007 快照 manifest

扩展现有 `ConsolSnapshot.snapshot_data` 格式为 v2 manifest，不另建快照表。分片：tree、worksheet_data、entries、worksheet_calc、trial、report、consol_notes、mappings、formulas、lifecycle、artifact；每片 canonical JSON + hash，根 manifest 再 hash。`reason in sign/lock` 时 required capturer 任一失败、operation 非 succeeded、readiness 有 blocker、artifact hash 不符均拒绝；manual snapshot 可记录 partial。snapshot 创建只 flush，签字路由统一提交并设置 `projects.consol_lock`。

## 3. 统一运行顺序

```text
claim operation → build tree/context/version vector once
→ validate readiness before compute
→ load CalcBasis once
→ write derived node-account worksheet
→ write consol trial
→ reconcile
→ materialize root report + report run
→ refresh formula-owned note cells
→ reaggregate confirmed detail-owned note sections bottom-up
→ build readiness after compute
→ publish operation/result refs/SSE
```

审批事件、手工“一键更新”和模板公式变化进入同一入口。上层合并项目按拓扑自下而上建立子 operation；`push_targets` 改递归 CTE/一次预载。关键阶段失败终止；报表/附注失败可形成 partial，但不能成为正式导出或签字来源。

## 4. API 与兼容

- `POST /api/consolidation/{pid}/{year}/operations`：创建/合并请求，返回 operation_id、status、version vector 摘要。
- `GET /api/consolidation/{pid}/{year}/operations/{id}`：状态、步骤、metrics、错误和输出引用。
- `GET /api/consolidation/{pid}/{year}/readiness`：七域五态 readiness。
- `GET /api/consolidation/{pid}/{year}/post-elimination`：四表 canonical projection。
- `POST /api/consolidation/eliminations/worksheet-preview|worksheet-generate`：新版本化契约；旧入口兼容一轮并标 deprecated。
- `GET /api/consolidation/reports/{pid}/{year}` 增 `mode=published|preview`、`operation_id`；默认 published。
- `POST/GET /api/consolidation/reports/{pid}/{year}/workpaper` 改成 artifact create/download，不再 GET 时重算。
- 旧 refresh-all、push 返回原字段并附 operation_id；旧 job status 从 operation 适配。

## 5. 前端设计

主页面改“集团合并工作台”，口径栏只读；顶部 `ConsolReadinessBar` 展示树版本、输入版本、正式 run、待审批/待映射/失败。Tab 顺序改为集团架构、数据准备、抵销审批、试算、报表、附注。新 `useConsolWorkspaceGuard` 注册每张表的 loaded/saved/edit revision 和 save handler，父页切换/重载/离页统一三选一。工作底稿首次加载骨架且禁编辑；错误保留旧数据并标“可能不是最新”。报表有“正式结果/实时预览”切换，导出只对正式结果开放。附注工具栏分四组，默认“更新本章节”按 source_mode 分派。

## 6. 性能与观测

`refresh_all` 和 push 都接收预构建 tree/context/basis；`recalc_full/recalculate_trial/generate_consol_reports` 增可选 basis，保证每 target/run 一次 load。章节公式批量加载；单体附注按 sections×projects 一次或分块读取。metrics 记录阶段耗时、SQL/读写行摘要、N/A/S/D、queue/lock wait/retry。验收目标：tree build≤1、basis load≤1、上层目标与公式加载 SQL 对 D/S 斜率为 0；具体毫秒 SLO 在 10/100/500 节点基线后确定。

## 7. 安全、事务与降级

所有新路由挂项目级 readonly/edit/review、归档与合并锁检查；对象 id 必回查 project。service 只 flush，operation worker 用短事务逐阶段提交并用 revision CAS。Redis/worker 不可用时可以同步创建 queued operation，但不在请求内执行重任务；前端显示“等待工作进程”，不得降级为无版本旧计算。公式来源信封或附件 readiness owner spec尚未全部落地时，通过薄适配接口读取；切换点是对应 owner 模块可 import 且 schema 已迁移，禁止静默双写。

## 8. 依赖、ROI 与风险

| 批次 | 主要文件规模 | 收益 | 风险/策略 |
|---|---:|---|---|
| 真语义/dirty | 前端约 8~12 文件 | 立即消除假成功和丢编辑 | 中；复用附注 epoch/保存协调器 |
| projection/版本草稿 | 后端约 8、前端约 6 | 消除双源和不可追溯草稿 | 中；前后端 builder 对拍后切换 |
| operation/context | 后端约 12 | 重启恢复、并发正确性、统一状态 | 高；兼容壳渐进接入 |
| 报表/artifact | 后端约 10、前端约 4 | 页面、下载、签字同版 | 高；与来源信封共用 run |
| note/readiness | 后端约 8、前端约 5 | 降低附注误覆盖与操作复杂度 | 高；不改 V186 映射算法 |
| WorkingPaper/快照 | 后端约 10、前端约 4 | 正式复核、证据、归档、签字 | 高；只做薄壳，不复制业务数据 |

## 9. 验证设计

纯函数/SQLite验证状态机、version vector、builder 对拍和快照 hash；真实 PG 用两个独立会话验证 worksheet version、operation CAS、active unique、worker crash reclaim、签字 fail-closed；前端 vitest验证 dirty、五态、正式/预览、错误不变空态；Playwright 在完整【测试】集团验证单体 TB→工作底稿→草稿→审批→operation→报表/导出→附注→证据/复核→签字/锁定，并独立 GET/SQL/hash 对账。性能用 10/100/500 节点合成 fixture；6000 并发脚本交付，专用环境未授权时保持环境待测。
