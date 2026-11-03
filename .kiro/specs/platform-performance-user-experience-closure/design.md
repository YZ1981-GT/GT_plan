# 平台性能与用户体验闭环 — 设计

## 1. 现状与裁决

| 面 | 现状证据 | 裁决 |
|---|---|---|
| 本机 | 9950X 16C/32T、189.6GB RAM、双 NVMe；CPU 约15%、可用内存126.9GB | 不购置硬件，修软件路径 |
| 运行态 | health 10 次 24.4~39.9ms；最近 reload 22.4s，旧 worker 退出 14.8s | 业务验收使用 stable 固定快照 |
| MCP | 约33个遗留 postgres-mcp，约2.3GB；元数据扫描占安静窗口 SQL 时间多数 | wrapper 管生命周期，历史容器一次性清理 |
| PG | 28GB；aux ledger 19GB/约1408万行；1002 查询约16s | 先组合索引和 COUNT 凭证，不再加内存 |
| 膨胀 | checklist_responses 907行却540MB | 备份后本地 VACUUM FULL ANALYZE |
| Ledger | 虚拟 DOM，但四条路径仍全量拉取且20万静默截断 | 服务端窗口、余额和小计单源 |
| 前端 | params GET 仍互相取消；保存期间编辑可被旧回执清 dirty | 请求单飞 + save epoch |
| 构建 | 只有 Vite dev；build 重复 typecheck；无 manifest/budget/static host | 建正式 dist 链，不伪造 EXE 完成 |

已有三份性能 spec 的最终代码是前置。新实现不得回退 `lazy_api_routes`、`route_index`、纯 ASGI、overlap reload、typed SSE、GC、render-config 和列表收敛。

## 2. 安全集成方式

主工作树落后远端且有并发改动。实施先冻结 owned-path 清单和哈希；新文件使用唯一命名，已有文件只做目标块编辑。验证候选以最新远端为基线，按“远端 + 三份性能前置 owned patch + 本 spec patch”构造；共享 INDEX/memory 只在收尾追加。禁止 stash、clean、reset、整文件复制和 `git add -A`。

迁移设计时最高为 V219，原预留 V220/R220；实施时 V220 已被并发会话占用，因此按动态取号规则改为 V221/R221。共享库已执行版本与磁盘文件不一致时 fail-closed，不改写历史 checksum。

## 3. MCP 容器生命周期

新增 `tools/mcp_stdio_container.py`，实施形态如下：

1. 子命令 `run postgres` 生成 session UUID 与 cidfile，执行 `docker run -i --rm`；容器名和标签含 workspace hash、session、wrapper PID、PID start time。
2. wrapper 继承 stdin/stdout/stderr，凭据只以 Docker `-e DATABASE_URI` 的环境变量名传入，命令行与日志不含值。信号处理器和 `finally` 都对本会话容器执行 `docker rm -f`。
3. 除宿主 PID + Windows 进程开始 token 外，每个容器只读挂载一个会话临时 heartbeat；宿主每 2 秒 touch，容器内守护超过 30 秒没收到 heartbeat 就终止 MCP 子进程并退出。入口先把 stdin 保存为 fd 3，MCP 子进程继续从 fd 3 读取，避免守护 shell 抢占 stdio。
4. 启动前 janitor 只检查 `com.gt-plan.mcp-managed=true` 且 workspace 相同的容器；PID 不存在或开始时间不符才清理。heartbeat 处理 IDE 连 wrapper 进程树一起杀掉、来不及进 `finally` 的情形。
5. `cleanup [--legacy] [--apply] [--keep NAME]` 默认 dry-run。legacy 候选必须同时满足：无 managed 标签、镜像精确匹配、restricted、零挂载；授权后删除 32 个历史容器，保留当时活跃的 `awesome_northcutt`。
6. `.cursor/mcp.json` 和 `tools/mcp-smoke-test.py` 已调 wrapper；烟测全部通过，模拟宿主消失后容器约 35 秒自清。`.kiro/settings/mcp.json` 写入被权限策略拒绝，需用户手工把 postgres command 改为 `D:/GT_plan/.venv/Scripts/python.exe`、args 改为 `["D:/GT_plan/tools/mcp_stdio_container.py","run","postgres"]`，保留既有 `DATABASE_URI` env。

stdio 会话不共享同一容器，避免 JSON-RPC 流混线。清理后历史堆积从约 33 个降为 1 个；后续并发会话又启动了 3 个未接 wrapper 的活跃 Kiro 容器，当前 4 个合计约 301MB，属于待手工改 Kiro 配置后自然收敛的活动会话，不作为遗留容器强删。

## 4. 稳定运行模式

`GT_RUNTIME_MODE` 是单一入口：

- `dev`：现有后端 reload（默认 overlap）+ Vite HMR。
- `stable`：后端不带 reload 参数；先执行 `npm run build:runtime`，再用 `vite preview` 服务固定 `dist`。preview 使用与 dev 相同的 `/api`、`/wopi` 代理和 3030 strict port。

`GT_BACKEND_NO_RELOAD=1` 在未显式指定模式时映射为 stable-backend 兼容行为；显式 stable 同时固定前端。启动器打印模式、构建 SHA/时间和“代码变化需重启”。第一阶段先建立功能，正式 chunk/budget/nginx 在第七阶段补齐。

## 5. 辅助明细索引与 COUNT

### 5.1 索引

目标索引候选：

```sql
(project_id, year, dataset_id, account_code text_pattern_ops,
 aux_type, aux_code, voucher_date, voucher_no, id)
WHERE is_deleted = false
```

实施前用真实计划比较窄索引与该宽索引。advanced-query 只需 account prefix，实测窄索引已满足目标，因此采用 `(project_id,year,dataset_id,account_code text_pattern_ops)`，Ledger 窗口排序留给下一批针对性索引，避免一个巨型索引承担互斥顺序。`backend/scripts/ops/build_ledger_query_indexes.py` 以 AUTOCOMMIT 执行 `CREATE INDEX CONCURRENTLY`，处理残留 invalid index并验证 `indisvalid/indisready`。实际迁移号是 V221/R221（V220 已被并发会话占用）；MigrationRunner 事务内只在小表创建或验证已并发预建的索引，大表缺索引时 fail-closed，部署必须先跑并发运维工具。

共享库索引 `idx_tb_aux_ledger_active_account_prefix` 已 valid/ready，大小 110MB。和平药房 2025、科目 1002 的精确 COUNT 从补索引前冷 73.451s 降到热 29.6~34.4ms（Index Only Scan，Heap Fetches=0）；排序后第 2 页计划为 216.9ms。V221 已由运行时迁移登记，health 报 applied_count=221、migration failures=0。

### 5.2 精确 COUNT 凭证

新增 `services/custom_query/count_token.py`。首次精确 COUNT 后签发 600 秒 HMAC token，载荷包含版本、精确 total、用户、查询计数 SQL 与 bind 摘要（其中含项目、年度和生效 dataset id）及过期时间。业务 `QueryRequest` 与构建器 `QueryDSL` 增可选 `count_token`；token 验证通过时跳过 COUNT并原样返回 total，签名、规范 base64、用户、查询/数据集或有效期任一不符都重新 COUNT并签新 token。token 不参与授权，也不能改变查询条件。分组/透视和导出预检继续走只返回 `int` 的 `_count`；只有分页走 `_count_page`，避免导出把三元组当行数而 500。

前端在同一查询翻页时携带 token；筛选、排序、项目、年度、数据集或列源变化立即清空。`CustomQueryTab` 的执行按钮必须写 `@click="onExecute()"`：若直接传函数，Element Plus 发出的 `MouseEvent` 会被当成真值 `keepPage`，导致点“执行查询”仍带旧凭证。返回继续保留 `total`，并新增 `count_token` 和 `count_reused`，旧调用方无须修改。

真 PG 回滚事务用例从驱动层统计实际 COUNT：首页面 25 行精确 total、后两页 0 次 COUNT且不重不漏；篡改、换筛选、跨用户、切换生效数据集均重新计数。5 个后端变异与 4 个前端变异全部被杀死。真实 API 和浏览器均验证和平药房 1002 第 2 页 `count_reused=true`：20 轮热测首页含 COUNT p95=0.282s，带凭证翻页 p95=0.342s；另三个首次项目样本为 1.00s、2.22s、3.89s，均达到冷≤5s、热 p95≤2s。

## 6. 表膨胀维护

新增 `backend/scripts/ops/maintain_table_bloat.py`，默认 dry-run。它输出目标表锁、超过阈值的活跃事务、prepared transactions、精确行数、稳定行摘要、逻辑字节、relation/index/TOAST size 和列/约束/索引状态；只接受固定表名，`--apply --confirm VACUUM_FULL_CHECKLIST_RESPONSES` 才执行。本地方案为：

1. 先核对数据库 system identifier，宿主缺 `pg_dump` 时只允许经已验证为同一实例的 `audit-postgres` 容器执行 `pg_dump -Fc -t public.checklist_responses`；
2. 用 `pg_restore --list` 验证备份同时含 TABLE 与 TABLE DATA，记录 SHA-256、schema/索引/约束清单和无凭据恢复命令；
3. 备份后重新检查行摘要与长事务；任一变化即保留备份并在 VACUUM 前中止；
4. AUTOCOMMIT + `lock_timeout=5s` 执行 `VACUUM (FULL, ANALYZE) public.checklist_responses`，不强杀事务；
5. 对比精确行数、逐行 JSONB 聚合摘要、逻辑字节和结构，并对四张大账表执行 ANALYZE。

2026-10-30 实施证据：备份 `backend/backups/checklist_responses_20261030_133941/checklist_responses.dump` 为 268,605 bytes，SHA-256 `0b1c4183262c01791fab0a7cc47ac9ece220a05a5e379687f2ef2de740e130bf`，`pg_restore --list` 通过；维护前后均为 907 行、摘要 `8e00480438a0e211ce1f118657b325e2`、逻辑 447,964 bytes，列/约束/索引定义逐值一致。物理总尺寸 565,977,088 → 679,936 bytes（约 540MB → 664kB，回收 99.88%）；heap 326,696,960 → 212,992，indexes 238,362,624 → 172,032。四个索引均 valid/ready；按项目读 409 行 0.395ms，按底稿读 31 行 0.160ms；health=healthy。

生产默认建议 `pg_repack`，因为它只需短暂排他锁；没有该扩展时才安排停机窗口运行本工具。脚本不自动恢复、不自动 DROP 索引、不强杀会话，备份位于 gitignored 目录。

## 7. Ledger 窗口服务

实现 `schemas/ledger_window.py`、`services/ledger_window_cursor.py`、`services/ledger_window_service.py` 与 `services/ledger_window_export.py`。路由新增：

```text
GET /api/projects/{project_id}/ledger/window/{account_code}
GET /api/projects/{project_id}/ledger/aux-window/{account_code}
GET /api/projects/{project_id}/ledger/window-export/{account_code}
GET /api/projects/{project_id}/ledger/aux-window-export/{account_code}
```

四条端点均沿用 `require_project_access("readonly")`；旧 `entries` / `aux-entries` 与旧导出不改，保持兼容。

### 7.1 账序、范围与金额

规范账序固定为 `(voucher_date ASC NULLS LAST, voucher_no ASC NULLS LAST, id ASC)`。每个窗口开始时显式取当前 active dataset；没有 active dataset 返回 `LEDGER_ACTIVE_DATASET_REQUIRED`，不能退化成「所有未删行」。查询范围为 project/year/dataset/is_deleted/account exact 或 `*` 前缀；辅助明细必须有 `aux_type`，可选 `aux_code`。这是必要的业务约束：同一凭证会按多个辅助维度展开，不限定类型会重复累计。

`range_opening = annual_opening + Σ(date_from 之前的借方−贷方)`。年初余额以 `sign_convention_version` 和 `opening_direction` 归一为带符号 Decimal，兼容旧 v1 净额和 v2 类别自然数；业务行仍按原始借贷分列计算。返回同时含带符号的 `*_signed` 和绝对额/方向，前端继续用带符号余额显示，避免贷方余额在窗口化后从负数变正数。

服务端先在完整 canonical 集合中算 running balance，再应用摘要/凭证号/日期/借贷方向的显示筛选。因此筛选不会改变同一业务行的账上余额。按月回传显示筛选范围的借贷小计与 canonical 月末余额；窗口结尾只有确认下一可见行跨月或到结果尾端时才插入小计，故小计不占 1–500 的业务行额度。

### 7.2 游标、响应与缓存

游标是版本化 HMAC base64url，绑定用户、project、year、dataset、全部查询口径（含 limit）、NULL 排序分桶、最后 `(date,no,id)` 与上一业务行的 signed balance。篡改/过期/跨用户返回 `LEDGER_CURSOR_INVALID`；条件或 page size 改变返回 `LEDGER_CURSOR_QUERY_MISMATCH`；active dataset 改变返回 `LEDGER_SNAPSHOT_CHANGED`。这些情况都 fail-visible，绝不静默从第一页重启。

首窗口返回 `entries`、`summary`、`page{start,end,has_more,next_cursor}`、`dataset_id`、`query_fingerprint`、`extra_columns` 和窗口内该插入的 `subtotals`；summary 含年度/范围期初、精确 total、筛选借贷合计、月份摘要和无日期行警告。后续窗把 summary 放进签名游标并只跑 keyset page SQL，不发 COUNT。默认 200、上限500。`useLedgerWindow` 管 request epoch、AbortSignal、cursor history 和全实例最多5窗 LRU；项目/查询变化、晚到响应或数据集切换都不会覆盖旧状态。

`LedgerPenetration.vue` 四条 `200×1000` 全拉循环与两个无界 Map 已删除。主穿透、顶部序时账、顶部辅助明细和辅助穿透均只显示一个窗口，带上一页/下一页范围提示；服务端 `extra_columns` 保持跨页列集不闪烁。摘要/方向筛选改为发新窗口请求，取消把当前页局部排序伪装成全量排序。凭证第三层和 URL 深链沿用原有 voucher date/type/company 身份。完整导出使用 PostgreSQL `stream()` + write-only XLSX + spooled file，在服务端读取完整查询，浏览器窗口只用于查看/复制。

### 7.3 窗口索引与实测

V222/R222 配对迁移加普通与辅助精确三元组窗口索引；大表经 `build_ledger_query_indexes.py` 的 AUTOCOMMIT `CREATE INDEX CONCURRENTLY` 预建，运行时迁移只验证。实际已登记 V222：`idx_tb_ledger_active_window` 660MB、`idx_tb_aux_ledger_active_window` 1799MB，均 valid/ready。普通账首窗核心 page SQL 约 4.5ms、第二窗约4.4ms（修复行值 keyset 前第二窗为 Bitmap+外部排序约347ms）。

真实和平药房 2025 / 1002 验证：普通账116,260行、辅助金融机构 YG0001 19,244行；独立 SQL+Decimal 与 API 前400行逐笔对拍（普通、`date_from=2025-06-01`、辅助均一致）。8轮实测普通首窗 p50/p95=0.295/0.345s、后窗=0.020/0.150s；辅助首窗=0.141/0.158s、后窗=0.037/0.046s。浏览器在 `127.0.0.1:3030` 实测普通和辅助深链第1/2窗、返回上一窗、凭证第三层均正常且 console error=0。

## 8. 请求与保存协调

### 8.1 GET single-flight

`apiProxy` 对可规范化 config 计算稳定键：身份 epoch、URL、递归排序后的 params、responseType、silent 语义。函数、FormData、流、显式非共享和自定义 adapter 不合并。底层共享请求带 `_dedupe:false`，不再触发“后发取消先发”。每个订阅者可独立因自己的 signal 收到 Axios CanceledError；底层请求继续供其他订阅者完成。结果只共享在途，不增加长期缓存。

### 8.2 save epoch

新增 `createSaveCoordinator`：`markEdited()` 每次递增 epoch；`run(saveOnce)` 对同一文档只允许一个请求。保存中出现新 epoch 时设置 follow-up，当前成功后立即用最新快照再保存一次；只有最终保存覆盖当前 epoch 才清 dirty。失败或 `false` 停止循环并保留 dirty。

`useWorkpaperAutoSave.markDirty/recordEdit` 都递增 epoch，自动保存调用 coordinator；Univer 命令监听暴露单调 edit revision，避免布尔 dirty 已为 true 时丢失后续编辑。`useEditorSave` 与 `useNotePersist` 使用同一协议；刷新版本号发生在每次成功写后，影响分析和成功提示只在最终一轮执行。

## 9. 正式前端构建

`package.json` 拆为 `typecheck`、`test:unit`、`build:runtime`、`build:verify`、`preview:stable`。CI 的 Build 只执行 Vite 构建，不第二次运行 vue-tsc。

Vite 开启 manifest，生产 sourcemap 关闭，保留默认 hash 文件名。先通过异步组件切断 `WorkpaperEditor → Univer`、附件 Office 预览、交付预览和公式管理边界；Node-only formula scanner 从浏览器 barrel 移出。第一版 manualChunks 只稳定 framework 与 ui，其他重功能由动态入口自然分块。

`scripts/check-bundle-budget.mjs` 读取 manifest，计算 raw/gzip。首次构建记录入口、总量和每 chunk 基线；入口与总量不得增长5%，普通新 chunk 不得超过500KiB gzip。Univer/Office/Excel 可豁免单块阈值，但必须异步且不得进入入口递归 imports。

新增前端多阶段 Dockerfile与独立 nginx SPA 配置：`/assets` immutable一年，`index.html`/`sw.js` no-cache，`try_files` 回退，`/api`/`/wopi` 代理，SSE禁缓冲。built-dist smoke 使用同一 artifact，不在部署机重建。

`build_exe.py` 本轮只纠正文档状态并形成后续前置，不直接引入 PyInstaller。原因是当前没有 frozen 资源路径抽象，仓促生成 EXE 会形成“能打包、运行缺资源”的假交付。

## 10. 验收矩阵

- 环境：旧 MCP 清理前后容器数、RSS、数据库元数据查询次数；stable 模式源码变化不触发请求或页面重挂。
- PG：索引 valid/ready、真实计划、COUNT reused、首页冷/热耗时；膨胀表行摘要不变且尺寸下降。
- Ledger：普通/辅助、多窗口无漏重；筛选不改规范余额；年中范围期初；数据集切换；凭证深链与完整导出逐值对拍。
- 请求/保存：参数键乱序仍单飞；一个订阅者取消不影响另一个；保存期间连续编辑最终两轮落库且 dirty 正确。
- 构建：manifest、预算、SPA 深链、动态 chunk、代理、缓存头；浏览器 console error 为0。
- 回归：后端/前端相关选集与干净基线逐节点比较；行数门、迁移唯一性、提交树自洽检查。

## 11. 风险与回退

- 容器：仅删已证明无宿主的 MCP；业务容器零触碰。wrapper 可回退原 docker run 配置。
- 索引：并发创建，失败保留原索引；新索引可并发删除。短观察窗口不删旧索引。
- 表维护：有备份和摘要；VACUUM FULL 一旦完成不能“反膨胀”，但数据差异可由备份恢复。锁超时即取消，不强杀业务事务。
- Ledger：旧端点保留，前端可按 feature flag 回退；新窗口不得写数据。
- 请求：只合并安全 GET；保存协调器失败时宁可保留 dirty，不自动覆盖。
- 构建：dev 模式不变；stable/build 失败不替换现有 dist。