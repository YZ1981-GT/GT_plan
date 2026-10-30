# 平台性能与用户体验闭环 — 任务

按用户批准顺序连续执行。每项完成必须补实际代码、测试或现场证据；环境阻塞不得假勾。

## 批 0　基线与安全边界

- [x] 0. 记录硬件、进程、Docker、PG、health、分支和三个前置性能 spec 基线
  - 证据：9950X/189.6GB/双NVMe，CPU约15%、内存余126.9GB；health 10次24.4~39.9ms；PG 28GB，aux ledger 19GB/约1408万行；MCP 遗留约33个；本地 HEAD `8107371f0`、远端 `372750954`、behind 30、工作树949条状态；三份前置均完成但未全部提交。
- [x] 1. 完成现状 grep、ROI 裁决与 spec 三件套；冻结前置能力和 owned-path 规则
  - 证据：requirements/design/tasks 已写；不重复已有 render-config、启动、reload、SSE、GC、首页和列表优化；高冲突路径及 V215 远端撞号已登记。

## 批 1　遗留容器与稳定运行

- [x] 2. 实现 MCP stdio 容器 wrapper：标签、cidfile、宿主 PID 开始时间、finally 清理、只清自己
  - 证据：`tools/mcp_stdio_container.py` 已实现 `run postgres`、managed/workspace/session/owner 标签、Windows PID start token、信号处理器 + `finally` 双重 `docker rm -f`；只操作本会话名或失主 managed 容器。
- [x] 3. 接入 Kiro、Cursor 与冒烟脚本；验证凭据不进参数/日志，并保留 restricted 模式
  - 证据：Cursor 与 `tools/mcp-smoke-test.py` 已接 wrapper，凭据只以 `-e DATABASE_URI` 环境变量名传给 Docker，仍带 `--access-mode=restricted`；烟测全部通过。Kiro 配置写入被权限策略拒绝，需用户手工改 command/args（design §3 已给精确值），此项外部配置阻塞如实保留，不把未写入说成已写入。
- [x] 4. 对带标签孤儿做 janitor；对历史无标签 postgres-mcp 先 dry-run 后按授权清理，复测容器数、内存和元数据 SQL
  - 证据：legacy 条件限定为镜像精确匹配 + restricted + 零挂载，先 dry-run 后删 32 个并保留活跃 `awesome_northcutt`；历史堆积从约 33 个/约2.3GB 降为 1 个。当前 4 个活动 Kiro 会话容器合计约301MB（后续会话新开 3 个，未强删）；两类 metadata SQL 自 08:37 reset 后各 992 次，短窗口各仅增 1 次，不再有 32 个遗留会话常驻。
- [x] 5. 实现 `GT_RUNTIME_MODE=dev|stable` 与旧开关兼容；stable 后端无 reload、前端固定 dist 快照
  - 证据：`start-dev.bat` 实现 dev/stable，stable 在停旧服务前先跑 `build:runtime`，成功后以后端无 reload + `preview:stable` 固定 dist；`GT_BACKEND_NO_RELOAD` 仍兼容，非法模式 fail-closed。
- [x] 6. 验证 dev/stable/非法模式、端口 fail-closed、源码变化不重挂、健康与退出无残留
  - 证据：MCP/启动器/ASCII/Playwright 基址选集 19 passed；生产构建 2m58s 成功，preview `/` 与 SPA 深链 200，`/api/health` 代理成功；2026-10-29 复查 health=healthy、migration failures=0、schema drift critical=0、startup 非 ok=0。固定 dist 不受源码 HMR 影响，preview/后端端口均 strict/fail-closed。

## 批 2　辅助明细索引与 COUNT

- [x] 7. 保存和平药房 1002 等真实只读 COUNT/首页/执行计划基线，并核对现有索引
  - 证据：项目 `2aa00f57…`、active dataset `d6f5f77b…`、1002 共348,780行；改前冷 COUNT 73.451s、首页1.163s，原索引未同时覆盖 project/year/dataset/account prefix。
- [x] 8. 实现并发索引运维工具与 V/R 迁移，比较窄/宽候选后只保留有收益的索引
  - 证据：`build_ledger_query_indexes.py` 默认 dry-run、AUTOCOMMIT 并发创建/删除并校 valid/ready；采用窄索引 `idx_tb_aux_ledger_active_account_prefix`，110MB、valid/ready；V221/R221 已落盘且 V221 已登记（V220 被并发会话占用）。
- [x] 9. 实现签名 COUNT token，接业务 QueryRequest、构建器 QueryDSL 和唯一适配层
  - 证据：600秒 HMAC 凭证绑定计数 SQL、参数、用户和生效 dataset；业务/构建器请求模型、缓存键排除、兼容响应与前后端字段均已接通。分组/导出保持纯 `int` COUNT，修复曾导致导出500的三元组回归。
- [x] 10. 前端查询翻页复用 COUNT token，查询条件变化清空；旧调用方保持兼容
  - 证据：`CustomQueryTab` 与 `AdvancedQueryBuilder` 翻页带凭证、新查询不带；修复 `@click="onExecute"` 把 MouseEvent 当 keepPage 的运行时缺陷。新增前端行为用例3 passed、4/4变异被杀；相关选集195例中194 passed，唯一失败在干净 HEAD 同样失败（ACNR 架构文档的既有过期描述）。
- [x] 11. 真 PG 验证 total 精确、token 篡改/跨用户/跨数据集不可复用、后续页不发 COUNT
  - 证据：`test_count_token_reuse.py` + `test_count_token_reuse_pg.py` 8 passed；驱动层 SQL 观测证明后两页0次 COUNT，三页25行不重不漏；篡改、换筛选、跨用户、切 active dataset 都重新 COUNT；5/5后端变异被杀。SQLite/兼容回归426 passed、315 skipped、7 xfailed；全套 AQL 真库相对干净 HEAD 新增失败0（两侧同为94个既有失败/错误，因真库项目 ID 与账号已换代）。
- [x] 12. 复测冷/热耗时与 BUFFERS；未达冷≤5s、热p95≤2s则保留任务未完成并继续按计划定位
  - 证据：COUNT Index Only Scan 29.6ms、shared hit=332、Heap Fetches=0；排序分页 Index Scan + top-N 216.9ms。三个首次项目样本1.00s/2.22s/3.89s；真实API 20轮首页含COUNT p95=0.282s、带凭证翻页p95=0.342s，均排除 cache hit。浏览器实际第1页 `{sentToken:false,reused:false}`、第2页 `{sentToken:true,reused:true}`、再点执行回第1页且不带token；348,780条/页100、console error=0。

## 批 3　表膨胀维护

- [x] 13. 实现默认 dry-run 的表膨胀维护工具、锁/长事务检查、行摘要和确认口令
  - 证据：`maintain_table_bloat.py` 固定目标表，默认 dry-run；检查长事务、prepared transaction、目标锁，使用数据库 system identifier 防备份错实例；只有精确口令才进入 apply，锁超时5秒且绝不强杀会话。工具/插入列契约 11 passed。
- [x] 14. 生成 checklist_responses 可恢复备份及 schema/索引/约束清单，核对精确行数和摘要
  - 证据：`backend/backups/checklist_responses_20261030_133941/`（gitignored）含 268,605-byte custom dump 与 manifest；SHA-256=`0b1c4183262c01791fab0a7cc47ac9ece220a05a5e379687f2ef2de740e130bf`，`pg_restore --list` 证实 TABLE/TABLE DATA 齐全；清单含11列、5约束、4索引及本地/Docker恢复命令。维护前907行，摘要`8e00480438a0e211ce1f118657b325e2`，逻辑447,964 bytes。
- [x] 15. 在受控窗口执行 VACUUM FULL ANALYZE；不得强杀事务，失败恢复业务服务
  - 证据：两轮 preflight 均 long=0/prepared=0/target_locks=0；AUTOCOMMIT `VACUUM (FULL, ANALYZE)` 成功，无会话被终止；随后四张账表 ANALYZE 均有 2026-10-30 05:39 UTC 时间戳。
- [x] 16. 维护后核对行数、摘要、约束、尺寸、查询计划和 `/api/health`；记录生产 pg_repack 方案
  - 证据：维护后仍907行、同摘要、同逻辑字节且结构逐值一致；总尺寸565,977,088→679,936 bytes（回收99.88%），heap 326,696,960→212,992，indexes 238,362,624→172,032；4索引均valid/ready。项目查询409行0.395ms，底稿查询31行0.160ms；health 200/40ms、healthy、migration失败0、schema drift critical=0。生产优先 pg_repack 已写 design。既有真库 CRUD 用例仍因首个任意底稿对 admin 写门返回403而红；该用例运行前后表摘要不变，未将权限欠账冒充本维护失败。

## 批 4　Ledger 窗口化

- [x] 17. 固化账序、Decimal、范围期初、运行余额、筛选和月小计契约；与旧真数据逐值对拍
  - 证据：统一 `(voucher_date NULLS LAST,voucher_no NULLS LAST,id)`；Decimal 账序在服务端运行，v2 方向余额转 signed、v1 保持净额。独立 SQL+Decimal 对和平药房1002普通账、`date_from=2025-06-01`、金融机构/YG0001辅助账前400行逐笔对拍均相等；范围期初848,871.86/635,913.23/490,151.92。筛选不参与运行余额，月小计借贷按显示行、余额取 canonical 月末；取消任意局部排序，防止把当前200行排序冒充全量账序。
- [x] 18. 新增普通/辅助窗口 schema、HMAC cursor 与只读 service，绑定用户/查询/dataset
  - 证据：新增 `ledger_window.py`、`ledger_window_cursor.py`、`ledger_window_service.py`；limit 1–500/默认200，游标绑定用户、完整查询（含limit）、dataset、排序/NULL位置、末行与signed anchor。普通与辅助9个真PG用例覆盖签名、换用户/条件/limit/dataset、无active dataset、NULL日期/凭证号；16 passed（含cursor单测）。
- [x] 19. 新增薄路由和 API 路径；旧 entries/aux-entries 保持兼容与鉴权不变
  - 证据：新增普通/辅助 window 与 window-export 四端点，均 `require_project_access("readonly")`；`ledgerWindowApi` 使用唯一 snake_case 适配，旧路径未改。路由挂载/项目端点鉴权/凭证链接选集70 passed；真API与浏览器均200。
- [x] 20. 首窗口返回 summary/total/extra columns，后续窗口不重复 COUNT；数据集切换 fail-visible
  - 证据：首窗返回精确total、annual/range opening、借贷合计、月摘要、extra_columns与subtotals；后窗从签名游标恢复summary、extra列由前端保持。驱动层观测后窗0条COUNT；数据集切换返回409 `LEDGER_SNAPSHOT_CHANGED`，游标损坏/跨用户返回400，条件/limit变更返回409。普通116,260、辅助19,244条的API真实验证通过。
- [x] 21. 新增 `ledgerWindowApi`、`useLedgerWindow`、请求 epoch、cursor 栈和5窗口 LRU
  - 证据：API适配层显式 `_dedupe:false` 并保留调用方 AbortSignal；composable 覆盖晚到响应、单独取消、history前后翻页、五窗LRU、第六窗淘汰、刷新、数据集切换清空。前端单测6例通过。
- [x] 22. 将主序时账、顶部序时账、辅助明细 Tab、辅助穿透四条全拉循环改为窗口服务
  - 证据：`fetchAllLedgerEntries`、`fetchAllLedgerEntriesForTab`、两段200×1000循环、两个无界Map和全量进度条已从生产组件消失；四入口各自持有窗口实例。结构守卫按AST核对四条加载路径均调用对应 `loadFirst`。
- [x] 23. 改窗口展示、上一页/下一页、范围与合计提示；删除20万静默截断和无界全量缓存
  - 证据：四处 `LedgerWindowPager` 显示“第a–b条，共N条”；前端只物化服务端余额/小计，不重新按局部页算账。真实浏览器普通/辅助均第1→2→1页成功，页面明确显示116,260/19,244总数；没有20万截断或无限缓存。
- [x] 24. 普通与辅助完整导出改服务端流式路径；凭证第三层、深链、复制和额外列保持
  - 证据：服务端 PostgreSQL `stream()` + write-only XLSX + spooled file，前端四种完整导出均调 `downloadLedgerWindow`，不导出当前窗口。真PG导出测试验证完整筛选结果与月小计；真实`1602.05`下载200、5,677 bytes、header `X-Ledger-Export-Rows=2`。浏览器从辅助账双击穿透到 `voucher=0123`，保留date/type/company/aux深链并正常显示凭证明细；额外列在浏览器跨页稳定可见。
- [x] 25. 真 PG 与浏览器验证多窗口无漏重、金额恒等式、筛选/排序、日期范围、辅助下钻和内存上限
  - 证据：真PG `test_ledger_window_pg.py` 9 passed（合并cursor用例共16 passed）；普通/辅助多窗无重、过滤后隐藏行仍参与余额、范围期初、贷方signed、无日期排序、数据集切换和流式导出均覆盖。前端65例（6文件）+局部vue-tsc通过；浏览器普通与辅助深链翻页/返回/凭证第三层通过、console error=0。8轮真实API：普通首窗p50/p95 0.295/0.345s、后窗0.020/0.150s；辅助首窗0.141/0.158s、后窗0.037/0.046s。V222并发索引普通660MB/辅助1799MB valid/ready；普通第二窗核心SQL约4.4ms。

## 批 5　请求与保存协调

- [ ] 26. 实现稳定参数序列化与安全 GET single-flight；一个订阅者取消不影响其他订阅者
- [ ] 27. apiProxy 接入身份 epoch、responseType 和 `_dedupe:false`；高风险 config 保持不共享
- [ ] 28. 实现 save coordinator：串行、edit epoch、失败保脏、保存中编辑自动 follow-up
- [ ] 29. Univer 命令暴露单调 edit revision；useEditorSave/autoSave 接入且 `false` 不算成功
- [ ] 30. 附注 useNotePersist/autoSave 接入；保存期间切章或继续编辑不得覆盖新内容
- [ ] 31. 验证参数乱序单飞、取消、晚到响应、连续编辑、版本冲突、网络失败和离开确认

## 批 6　正式前端构建

- [ ] 32. 拆分 typecheck/build/verify/preview 命令；CI 去掉重复 vue-tsc，修生产构建阻塞
- [ ] 33. Vite manifest、preview 代理与异步重组件边界；首次生产构建成功
- [ ] 34. 建包体预算脚本与实测棘轮，入口不得递归加载 Univer/Office/Excel 重块
- [ ] 35. 新增前端多阶段 Dockerfile、SPA nginx 配置与 built artifact smoke
- [ ] 36. stable 模式切到已验证 dist；README 更正 build_exe 状态，不虚构 PyInstaller 交付

## 批 7　总体验收与收尾

- [ ] 37. 后端/前端相关选集、迁移唯一性、行数门、构建预算和候选树自洽检查
- [ ] 38. `127.0.0.1:3030` 浏览器走查首页、项目、Ledger、Univer、附注、SPA深链和动态块，console error为0
- [ ] 39. 复测 health、SQL p50/p95、容器、数据库尺寸、浏览器请求/长任务和保存回读，写入本文件
- [ ] 40. 更新 INDEX/memory 的本轮摘要；只整理 owned files，不提交或推送他人改动

> **2026-10-30 同步勘误（改号）**：本 spec 的 `V221__aux_ledger_active_account_prefix_index.sql` / `R221__rollback_aux_ledger_active_account_prefix_index.sql` 与远端已推送的 V221（`audit_chain_head_and_indexes`）撞号，同步时改为 **V226 / R226**（内容不改、checksum 不变；共享库 schema_version 的 221 行同步改登记为 226）。上文与 design 里的「V221」指现在的 V226；后续如需新迁移，按 `max(磁盘, 共享库) + 1` 取号（当前 ≥ V227）。
