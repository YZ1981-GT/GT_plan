# Requirements — Ledger Import 四表上传解析入库整体重构

## 前言

### 业务背景
审计师日常工作流：每个审计项目需要导入客户账套（余额表 + 序时账 + 辅助表）。
9 家真实样本实测：单企业账套规模 0.8MB ~ 500MB，行数 4k ~ 260万，文件数 1 ~ 13 个。

**两个核心痛点**：
1. **导入太慢**：YG2101 样本（128MB / 200万行）当前需 400-482s，其中 `activate` 阶段 127s 纯粹浪费在 UPDATE 200万行 `is_deleted` 字段上
2. **系统会膨胀**：每次 activate 产生 200万 dead tuple，autovacuum 追不上，长期磁盘爆炸

### 技术根因
可见性状态（`is_deleted=false` vs `true`）**存在每一行数据里**，而不是在元数据层。
→ 200万行的可见性切换就要改 200万行物理数据 + 更新所有索引 + 产生 dead tuple

### 本 spec 定位
**"B' 视图重构"为主 + "9 家识别引擎强化"为辅**，一次性根本解决可见性架构缺陷，
并把 9 家真实样本实测暴露的识别引擎漏洞补齐。

---

## 一、范围边界（决策一目了然）

### 1.1 本 spec 核心交付

| 需求编号 | 主题 | 核心动作 | 验收标准 |
|---------|------|---------|---------|
| **F1** | 可见性视图化 | activate 只改 metadata，不 UPDATE Tb* 表 | YG2101 activate <1s |
| **F2** | 业务查询统一入口 | 40+ 处 `TbX.is_deleted==False` 迁移到 `get_active_filter` | grep 命中 = 0 |
| **F3** | purge 定期清理 | 保留 N=3 最近 superseded，旧 dataset 物理 DELETE | 10 次导入后表大小线性 |
| **F4** | 审计轨迹完整 | activate/rollback 记录操作人/耗时/前后摘要 | 前端可查历史时间轴 |
| **F5** | 跨年度同项目 | 同 project 可并存多 year active dataset | 集成测试通过 |
| **F6** | 文件名识别补强 | sheet 内容置信度低时走文件名关键字 +20 | 辽宁卫生 sheet1 识别 balance |
| **F7** | 方括号表头支持 | `[凭证号码]#[日期]` 剥壳 + 组合字段拆分 | 和平物流识别置信度 ≥85 |
| **F8** | 表类型鲁棒性 | 同 workbook 2 个余额表按"有 aux_type 列"分流 | YG36/安徽骨科/辽宁卫生 分流正确 |
| **F9** | 多 sheet unknown 原因 | detect 返回跳过原因，UI 展示灰色卡片 | YG2101 Sheet1 提示"行数太少" |
| **F10** | CSV 大文件保障 | 392MB 流式读 detect <5s / parse 内存 <200MB | 集成测试覆盖 |
| **F11** | 9 家 header 快照测试 | 参数化覆盖 9 家 `data_start_row` 和 `header_cells` | 快照全绿 |
| **F12** | `_set_dataset_visibility` 废弃 | no-op + logger.warning | grep 外部调用 = 0 |
| **F13** | 进度回调精度 | 每 5% 或 10k 行至少更新一次 + 消息含当前位置 | UI 30s 无更新才判"卡住" |
| **F14** | 分阶段 checkpoint | staged 写完即 checkpoint，支持 resume | 模拟 activate 失败可从检查点恢复 |
| **F15** | cancel 的清理保证 | 30s 内停 worker + cleanup staged 行 + 清 artifact 文件 | 取消后磁盘/DB 零残留 |
| **F16** | 可观测性指标 | Prometheus 最小埋点 + `/metrics` 端点 | 3 个核心指标可采集 |
| **F17** | 导入前耗时预估 | detect 返回 `estimated_duration_seconds` | 500MB 样本误差 ±30% |
| **F18** | 迁移策略三阶段 | Day 0 deploy / Day 7 一次性 UPDATE / Day 30 DROP 废弃索引 | ADR 文档化 + 执行剧本 |
| **F19** | 灰度与回滚 | feature flag + 项目级开关支持回退 | flag off 时走老逻辑 |
| **F20** | 激活广播（云协同）| WebSocket 推送 `dataset:activated` 给项目组所有成员 | A 激活后 B 前端 3s 内自动感知并刷新 |
| **F21** | 锁透明（云协同）| 导入中其他成员查看时显示 holder / 进度 / 预计剩余 | 抢占失败有明确 UI 提示 |
| **F22** | 导入接管（云协同）| heartbeat 超 5min 允许其他成员接管，`created_by` 扩展为数组链 | 模拟 A 掉线后 B 可续跑 |
| **F23** | rollback 走 ImportQueue 锁 | rollback 与 activate 互斥，防止并发 | 集成测试覆盖 rollback vs activate 竞争 |
| **F24** | 只读旁观（云协同）| 项目组非 holder 成员可 `GET /jobs/{id}` 看实时进度 | 权限测试：只读用户访问 200 + 写操作 403 |
| **F25** | 审计溯源完整 | activate/rollback 记录 actor/ip/reason/duration_ms | `/datasets/history` 时间轴可查 |
| **F26** | staged 孤儿扫描 | 定时任务每小时扫 >24h 无 job 关联的 staged dataset → 自动清理 | 主动产生孤儿 → 1h 内被清 |
| **F27** | 激活前 integrity check | metadata 切换前 COUNT(*) 校验 staged 行数符合 `record_summary` | 不符 → 阻断激活 + 告警 |
| **F28** | 恢复剧本文档 | ADR-003 故障场景剧本（activate 失败/孤儿/connection leak/索引膨胀）| runbook 含命令序列可执行 |
| **F29** | 事务隔离 ADR | 明确 activate 走 `REPEATABLE READ` 隔离级别 + 幂等键 | ADR-004 文档化 |
| **F31** | 激活意图确认（UX）| 前端 ElMessageBox 二次确认 + 可选"理由"字段 → 进 `ActivationRecord.reason` | UI 有确认对话框 |
| **F32** | 错误友好化（UX）| 31 个错误码每个提供「原因+修复建议」文案映射 | 错误详情页展示可操作建议 |
| **F40** | 上传文件安全校验 | MIME + 扩展名 + 大小上限 + zip bomb 防护 | 恶意文件被拒 + 审计日志记录 |
| **F41** | 项目权限与 tenant 预留 | 所有 4 表查询强制 project_id 校验 + Tb* 预留 tenant_id 字段（默认 `'default'`）| 跨项目越权测试 100% 拦截 |
| **F42** | 零行/异常规模拦截 | detect 阶段 `total_rows < 10` 警告；新 dataset 规模比历史均值 ±5σ 告警 | UAT 空文件被挡；异常样本触发告警 |
| **F43** | 健康检查端点 | `/health/ledger-import` 返回 queue 深度 / worker 存活 / P95 耗时 / PG 连接数 | Kubernetes liveness/readiness probe 可用 |
| **F44** | graceful shutdown | worker 收 SIGTERM 后完成当前 chunk 再退出（≤30s）| 重启时无 staged 断裂 |
| **F45** | 事件广播可靠性 | F20 WS 广播失败走 event_outbox 重投（3 次 + DLQ 告警）| 模拟 WS 抖动后 B 仍能收到事件 |
| **F46** | rollback 下游联动 | rollback 发 `DATASET_ROLLED_BACK` event，触发 Workpaper/report `is_stale=true` | 集成测试覆盖下游失效标记 |
| **F47** | 校验过程透明化 | 每条 finding 附公式+代入值+中间步骤+差异来源分解 | 用户不看代码即能复现并解释差异 |
| **F48** | 校验规则说明文档 | 前端"数据校验"入口展示全部 L1/L2/L3 规则列表+公式+容差+示例 | 用户点规则可看可执行示例 |
| **F49** | 差异下钻到明细行 | 余额=序时账累计不一致时可一键展开该科目全部凭证行 | 3 次点击内定位到差异源凭证 |
| **F50** | 下游对象快照绑定 | Workpaper/AuditReport/Note 引用 dataset_id；签字后引用"锁定"不受 rollback 影响 | 已签字报表 rollback 后数字不变 |
| **F51** | 全局并发限流与资源隔离 | 平台级 worker 并发上限（默认 3）+ 超额入队列 | 100 人同时上传不打爆 PG |
| **F52** | 列映射历史智能复用 | 同 project+file_fingerprint 二次导入自动应用历史 mapping | 用户跳过映射步骤一键进下一步 |
| **F53** | 留档合规保留期差异化 | artifact 分 transient(90d) vs archived(10y)；active dataset 永不 purge | 审计底稿可追溯 10 年原始账套 |

### 1.2 本 spec 明确排除（独立 Sprint）

| 编号 | 主题 | 排除理由 | 过渡方案 |
|------|------|---------|---------|
| O1 | 多文件拼接为 1 dataset | 涉及 FileDetection 聚合 + UI 批量上传，工期 2 周+ | 用户逐文件 apply_incremental |
| O2 | 分片上传（chunked upload） | 前端改造 3 天+，独立 Sprint R6 | nginx/uvicorn 调大 body size |
| O3 | 月度增量导入 UX 引导 | 后端就绪缺前端 | 用户手动选 overwrite/skip |
| O4 | Tb* 表 year 分区 | B' 后 activate 不再是瓶颈，分区收益有限 | autovacuum + purge 已够用 |
| O5 | 导入配额限制（次数/大小） | 运维策略，非架构问题 | feature_flags 未来加 |
| O6 | 激活/回滚权限细粒度 | 需要先统一全平台 RBAC | current_user 鉴权已有 |
| O7 | 企业级 UX 完整版（预检报告 UI / S-M-L 档位 / adapter 模板） | 增量价值不影响正确性 | F17 已拆出"耗时预估"核心能力 |
| O8 | 数据备份 | 运维层处理 | 按项目规划做 pg_dump |
| O9 | Worker 资源隔离（大导入独立进程） | 当前共用 event loop 但 ImportQueue 已串行化 | 保持现状 |
| O10 | CRC 校验 staged 数据 | 成本高收益低，F27 COUNT 校验已能抓 90% 问题 | F27 兜底 |
| O11 | 超大导入前端内存警告 | 前端 UX 调优，非架构核心 | F17 耗时预估已给预期 |
| O12 | 导入前 diff 预览 | 产品侧需求，涉及 UI 设计迭代 | detect 阶段已给 row_count |
| O13 | REST API 版本化 | 当前单版本够用，无外部集成方 | 内部 API 保持向后兼容 |
| O14 | CLI 运维工具 | 独立工具链工作量，运维可用 psql 临时处理 | 手工 SQL 应急 |
| O15 | 完整多租户（tenant_id 全链贯通）| 当前单租户场景，全平台 RBAC 需统一规划 | F41 先预留字段不启用 |
| O16 | 性能基线自动化 CI 门禁 | 需要稳定 PG 环境专用 runner，独立 infra 工作 | 手动跑 `b3_diag_yg2101.py` 对比 |
| O17 | 告警通知渠道适配（邮件/钉钉/企微）| 全平台通知中心已有基建，本 spec 只埋点不接渠道 | F16 指标 + F45 event 已够 |
| O18 | 审批链可配置化（谁审批/几级审批）| 涉及平台 RBAC 和审批引擎，独立模块 | F47 暂用固定 partner 角色审批 |
| O19 | 账套差异对比视图（V2 vs V3 新旧值并列）| 独立 UI 组件，产品侧规划 | F4 历史时间轴可查单份 |
| O20 | 审计底稿回滚时的连带快照回退 | 涉及 WopiEditor 版本树打通，独立模块 | F50 已防止"数据错乱"是核心 |
| O21 | 导入模板市场（社区共享 adapter JSON）| 社区运营模块 | adapter JSON 已支持 hot-reload |
| O22 | 自动化周期性导入（定时抓取客户 ERP）| 对接客户系统 ETL 工作 | 用户手动每月上传 |

---

## 二、功能需求详述

### 2.A 核心架构（F1-F5, F12）

#### F1 可见性从行级字段升级到 metadata 切换
**现状**：
- 4 张 Tb* 表每行 `is_deleted` 字段做 staged 隔离
- `DatasetService.activate` 调用 `_set_dataset_visibility`，UPDATE 200 万行
- YG2101 实测 activate 127-193s（含波动），根因是 PG WAL 串行写入

**目标**：
- `ledger_datasets.status='active'` 一行 UPDATE 决定可见性
- pipeline 写入直接 `is_deleted=False`（staged 隔离靠 dataset.status != active）
- `DatasetService.activate`/`rollback` 不再调 `_set_dataset_visibility` UPDATE Tb* 表

**四路径统一**：
| 路径 | 现状 | B' 后 |
|------|------|-------|
| activate | UPDATE 新旧两份各 200万行 | UPDATE 2 行元数据 |
| rollback | UPDATE 新旧两份 | UPDATE 2 行元数据 |
| failed | 物理 DELETE staged 行 | 保持不变 |
| purge（新） | 无 | 定期 DELETE 超过 N 代的 superseded 行 |

**验收**：YG2101 activate 阶段 `phase=activate_dataset_done` 增量 <1s（vs 127s）

#### F2 业务查询统一入口
**现状**：40+ 处 `TbX.is_deleted == False` + 6 处 raw SQL 散落在 15 个 service、2 个 router

**目标**：所有四表查询走 `dataset_query.get_active_filter(db, table, pid, year)`
- ORM 查询：`where(await get_active_filter(db, TbLedger.__table__, pid, year))`
- raw SQL：`WHERE ... AND EXISTS (SELECT 1 FROM ledger_datasets WHERE id=tb_x.dataset_id AND status='active')`

**N+1 优化**：新增 `get_filter_with_dataset_id(table, pid, year, dataset_id)` 同步版本，
caller 入口先查一次 active_id 再复用（重点改造 `import_intelligence.get_stats` 约 10 次查询）

**CI 卡点**（详见 §4 测试章节）：grep `TbX\.is_deleted\s*==` 命中 = 0

#### F3 superseded 数据 purge 定期清理
**目标**：保留最新 N=3 个 superseded（作为 rollback 备选），其余物理 DELETE

**实现**：
- `DatasetService.purge_old_datasets(project_id, keep_count=3)` 新增方法
- 每晚定时任务调用，对所有项目执行

**验收**：连续 10 次导入 YG2101 级数据后，同一 project+year 只有 `1 active + 3 superseded = 4` 个 dataset；总行数线性增长

#### F4 审计轨迹完整
**现状**：`ActivationRecord` 表已有 who/when 记录

**目标**：扩展记录内容 + 提供查询接口
- 新增字段：操作人 IP、耗时毫秒、before/after 行数摘要
- 新增路由：`GET /api/projects/{pid}/ledger-import/datasets/history`
  返回 `[{dataset_id, status, created_at, activated_at, activated_by, row_counts, activation_records: [...]}]`

**验收**：前端"账套导入历史时间轴"组件可用（UI 实现属独立 Sprint，本 spec 只交付后端接口）

#### F5 跨年度同项目支持
**现状**：`LedgerDataset` 模型有 `(project_id, year)` 字段，但从未验证双年度并存

**目标**：同一 project 可并存多个 year 的 active dataset
- activate 2025 时只切同 year 的 status，2024 保持 active
- 业务查询按 `project_id + year + dataset_id` 过滤，天然隔离

**验收**：`test_multi_year_coexist.py` 集成测试覆盖"先导 2024 active，再导 2025 activate，两份都可查"

#### F12 `_set_dataset_visibility` 彻底废弃
**动作**：
- 函数体改为 `logger.warning + pass`
- 保留签名兼容旧代码
- grep 确认 `backend/app/` 下无任何外部调用（活化/回滚的自己调用已清除）

**原子性保证**：activate 事务内 UPDATE 旧 superseded + 新 active + ActivationRecord + outbox 在同一事务；
失败自动回滚（vs 改造前事务需 127s 期间占用 DB 连接）

### 2.B 识别引擎强化（F6-F11）

#### F6 文件名元信息利用
**实测背景**：
- 辽宁卫生、医疗器械用文件名标识表类型（`-科目余额表.xlsx` / `-序时账.xlsx`）
- 陕西华氏月份信息在文件名（`24.1` / `25年10月`）
- 当前 detector 只看 sheet 内容，**忽略文件名元信息**

**实现**：
- `detector._detect_xlsx_from_path` 在 sheet 内容置信度 < 60 时，按文件名关键字匹配 +20 置信度
- 关键字配置（可扩展）：
  - balance: `科目余额表 / 余额表 / TB / 试算`
  - ledger: `序时账 / 凭证明细 / 总账 / GL`
- 文件名含年月信息提取到 `SheetDetection.detection_evidence["filename_hint"]`（`24.1` → `period=1`）

**验收**：
- 辽宁卫生 `辽宁卫生服务有限公司-科目余额表.xlsx` 内 sheet 名 `sheet1` 时识别为 balance（置信度 ≥60）
- 陕西华氏月度序时账文件名 `序时账-陕西华氏-24.10.xlsx` 提取 period=10

#### F7 方括号 + 组合表头支持
**实测背景**：和平物流首行列名形如 `[凭证号码]#[日期]` / `[日期]` / `[凭证号码]`（金蝶 KIS 或某特定软件导出格式）

**实现**：
- `detector` 新增 `_normalize_header(cell_str)` 预处理：`[xxx]` 剥壳得 `xxx`
- `A#B` 组合字段识别后放 `detection_evidence["compound_headers"]`，`identifier` 侧拆分
- 归一化后走 identifier 别名匹配（`凭证号码 → voucher_no`, `日期 → voucher_date`）

**验收**：和平物流样本识别 ledger 关键列（voucher_no / voucher_date / debit / credit / summary）置信度 ≥85

#### F8 表类型识别鲁棒性
**实测痛点**：
- `sheet1` / `列表数据` 通用 sheet 名占 4/9 样本 → 完全靠列内容判断 table_type
- `科目余额表（有维度）` / `科目余额表（无维度）` 同 workbook 并存（辽宁卫生、安徽骨科、陕西华氏）
- 当前 detector 可能把"有维度余额表"错分为"无维度"，导致辅助维度丢失

**实现**：
- `identifier` 对 `sheet1` / `列表数据` 等通用名不减分（当前可能降低置信度）
- 同一 workbook 内 2 个余额表并存时，按"含 aux_type 列"区分主表/辅助表

**验收**：
- YG36 `科目余额表（有核算维度）` 识别为 `aux_balance`（当前可能识为 `balance`）
- 9 家样本 balance vs aux_balance 分流正确率 100%

#### F9 多 sheet unknown 原因透明化
**实测背景**：YG2101 的 Sheet1 只有 105 行元信息，当前 pipeline 静默 skip，用户完全无感知

**实现**：
- `SheetDetection.warnings` 追加 `SKIPPED_UNKNOWN` + 原因字符串（"行数太少" / "表头无法识别" / "列内容不符合"）
- 前端 `DetectionPreview.vue` 显示被跳过的 sheet（灰色卡片 + 原因）
- pipeline 进度条排除 unknown sheet 的 row_count_estimate（已有实现，需要验证）

**验收**：YG2101 4 个 sheet 分流：Sheet1 unknown（原因"行数太少 (105 行)"）/ 2 个余额表按 F8 分流 / 序时账进 ledger+aux_ledger

#### F10 CSV 大文件性能保障
**实测背景**：和平药房序时账单 CSV 392MB 纯文本

**现状**：`iter_csv_rows_from_path` 已有流式读 + 64KB 编码探测（理论可处理）

**验收**：
- 新增 `test_large_csv_smoke.py`（默认用合成 100MB CSV，真实 392MB 可选跳过）
- 392MB CSV detect 阶段 <5s，parse 阶段内存峰值 <200MB

#### F11 9 家样本 header 快照测试
**实测痛点**：
- YG 系列文件前 1-2 行横幅（`科目余额表` 跨列合并），第 3 行才是真表头
- 陕西华氏余额表 4 行表头（2 行标题 + 2 行合并"年初余额.借方金额"）
- F7 方括号表头（和平物流）
- `detector._detect_header_row` 当前已处理，但改动易回归

**实现**：
- 新增 `test_9_samples_header_detection.py` 参数化测试
- 每家断言 `data_start_row` 和 `header_cells[:8]` 符合预期快照
- 任何 detector 改动必须跑此测试通过（列入 CI 必跑）

### 2.C 企业级治理（F3 / F4 见 §2.A，此处只列差异化的）

保留项（不改动）：
- **E3 并发导入隔离**：现有 `ImportQueueService.acquire_lock(project_id)` 已够用
- **E6 软删除与回收站**：`recycle_bin.py` 的 is_deleted=true 语义保留；B' 后 `is_deleted` 不再用于 staged 隔离，仅用于回收站
- **B4 增量导入路径**：`ledger_data_service.apply_incremental` overwrite 模式按 dataset_id + period 物理 DELETE，与 B' 兼容
- **B5 数据管理功能**：`LedgerDataManager` 的 delete/restore/list_trash 保留

### 2.D 大文档健壮性（F13-F17）

#### F13 进度回调精度
**痛点**：
- B' 后 activate 从 127s 降到 <1s，但 `parse_write_streaming` 仍占 60%+ 时长
- 用户盯进度条从 50% 到 85% 之间几分钟没反应，体感像"卡死"
- 当前每 chunk（50k 行）更新一次进度，大 sheet 单 chunk 可能 30-60s 无更新

**实现**：
- `ProgressCallback` 调用频率保证：每 5% 或每 10k 行至少更新一次（取更早）
- 进度消息结构化：`"解析中: YG2101 序时账 第 13/48 chunk (已处理 650000/3200000 行)"`
- 前端判定"卡住"改为 `last_heartbeat_at > 30s` 才告警（当前 10s 误报率高）

**验收**：
- YG2101 E2E 跑完后，perf 日志 `_n_progress_calls` >= `total_rows_parsed / 10000`
- 手动 UAT：YG2101 导入过程中前端进度条每 5-15s 可见更新，无>30s 空窗

#### F14 分阶段 checkpoint（可恢复性）
**痛点**：YG2101 跑到 180 秒突然网络抖动 / PG 重启，现在整个 fail，用户再上传 500MB 重跑

**实现**：
- pipeline 在关键阶段完成后立即持久化进度到 `ImportJob.current_phase`：
  - `parse_write_streaming_done`：staged 数据全部写完
  - `activation_gate_done`：校验完成
  - `activate_dataset_done`：metadata 切换完成
- 新增 `ImportJobRunner.resume_from_checkpoint(job_id)`：
  - 若 job 处于 `activating` 且 staged dataset 存在 → 只重跑 activate 一步（1s 内完成）
  - 若处于 `writing` 中途失败 → 清理 staged 后重跑整批（当前行为）
- 前端失败页提供"恢复导入"按钮而非只有"重新上传"

**验收**：
- `test_resume_from_activation_checkpoint.py`：模拟 activate 抛异常，resume 后数据集成功激活
- staged dataset 孤儿清理交给 `recover_jobs` 超时处理（已有）

#### F15 cancel 的清理保证
**痛点**：用户上传 500MB 后发现文件错了点取消 → 当前 ImportQueue cancel 只发信号，**不保证清理**
- staged Tb* 行残留 → 占 DB 空间 + 被 fallback 查询误看见
- Artifact 文件残留 → 占 500MB 磁盘

**实现**：
- cancel 触发 `cancel_check()` 回调，worker 在当前 chunk 结束后（<30s）退出
- cancel 后自动调用链：
  1. `DatasetService.cleanup_dataset_rows(dataset_id)` 物理删 staged 行
  2. `ImportArtifactService.mark_consumed` + 物理删磁盘文件
  3. `ImportJob.status = canceled` + `cancellation_summary` 记录清理结果
- `recover_jobs` 兜底：canceled 但 dataset 仍 staged 的，定期扫清

**验收**：
- `test_cancel_cleanup_guarantee.py`：cancel 后 30s 内 job status=canceled + Tb* 行数 0 + artifact 文件不存在
- 磁盘/DB 零残留（YG2101 级测试：cancel 前后表大小差 = 0）

#### F16 可观测性指标（Prometheus 最小埋点）
**痛点**：生产运维缺数据做决策
- "YG2101 导入慢了"—— 没法查历史 P95/P99
- "表要不要 vacuum"—— 没法查 dead tuple 累积速度
- "该 purge 了吗"—— 没法查 superseded 数量趋势

**实现**：
- 后端新增 `/metrics` 端点（prometheus_client lib）
- 3 个核心指标：
  - `ledger_import_duration_seconds{phase}` histogram（phase ∈ detect/parse/activate/total）
  - `ledger_import_jobs_total{status}` counter
  - `ledger_dataset_count{project_id, status}` gauge
- pipeline 的 `_mark(phase)` 同步写 histogram
- 文档化推荐告警规则：P95 > 10min / 失败率 > 5% / dead_tuple_ratio > 30%

**验收**：
- `curl /metrics` 返回标准 prometheus 格式
- 集成测试：跑一次 YG4001-30 后 `ledger_import_duration_seconds_bucket{phase="total"}` 有数据
- 生产可选消费（即使不接 Prometheus，埋点数据可被日志采集）

#### F17 导入前耗时预估
**痛点**：企业级用户上传 500MB 前希望知道"要多久"再决定是否继续

**实现**：
- `detect` 响应新增 `estimated_duration_seconds` 字段
- 估算公式（基于 9 家样本实测）：
  ```python
  # 按行数档位 P50 吞吐
  if total_rows < 10_000:    duration = 15
  elif total_rows < 100_000: duration = 30 + total_rows / 3000  # M 档 3k rows/s
  elif total_rows < 500_000: duration = 90 + total_rows / 5000  # L 档 5k rows/s
  else:                      duration = 180 + total_rows / 4500 # 超大档 4.5k rows/s（含 activate）
  ```
- 前端 `DetectionPreview.vue` 展示："预计耗时 8 分钟（仅供参考）"
- 误差可接受 ±30%（完整预检报告 UX 见 O7 独立 Sprint）

**验收**：
- YG4001-30 预估 < 30s vs 实测 9-12s（误差 <±50%）
- YG2101 预估 < 500s vs 实测 250-400s（误差 <±30%）

### 2.E 运维与上线（F18-F19）

#### F18 迁移策略三阶段
**痛点**：B' 上线那一刻数据库里仍有大量 `is_deleted=true` 的老数据（staged 隔离产物），怎么平滑过渡？

**三阶段方案**：

**Day 0: Deploy B' 代码**
- `DatasetService.activate` 不再 UPDATE Tb* 表（走 F1）
- 业务查询走 `get_active_filter`（走 F2），其兜底分支仍用 `is_deleted=false`
- pipeline 新写入 `is_deleted=False`（走 F1 目标）
- **老 is_deleted=true 数据仍然看不见（兜底条件依然过滤）**，新 is_deleted=false 数据也看不见（因为 dataset.status 不 active 时 get_active_filter 会按 status 过滤）
- **效果**：零风险 deploy，不动历史数据

**Day 7: 一次性数据 migration**
- 上线 7 天后（观察期，保证 B' 代码稳定），跑一次性 SQL：
  ```sql
  -- 把所有当前 active dataset 的 Tb* 行 is_deleted 设为 false
  UPDATE tb_balance SET is_deleted=false
  WHERE dataset_id IN (SELECT id FROM ledger_datasets WHERE status='active')
    AND is_deleted=true;
  -- 其他 3 张表同理
  ```
- 这是**最后一次大 UPDATE**（~200 万行，跑 127s 可接受，一次性痛苦换永远不再痛）
- 跑完后所有 active 数据 is_deleted=false 一致

**Day 30: 清理废弃索引**
- 稳定运行 30 天后：`DROP INDEX CONCURRENTLY idx_tb_*_activate_staged`（预计回收 55MB）
- `DROP INDEX` 前再跑一次 `SELECT n_dead_tup FROM pg_stat_user_tables` 确认 dead tuple 率 < 5%

**验收**：
- ADR-002 归档三阶段时间表 + 每阶段 rollback 操作说明
- Day 7 migration SQL 写成 Alembic 迁移 `view_refactor_cleanup_old_deleted.py`
- 发布剧本（runbook）可复用

#### F19 灰度与回滚
**痛点**：B' 改动面大（40+ 查询迁移），即使全测过也可能有运行时边界 case。需要快速回滚能力。

**实现**：
- 新增 feature flag `ledger_import_view_refactor_enabled`（默认 False 保守开）
- `DatasetService.activate` 检查 flag：
  - False → 走老逻辑（仍调 `_set_dataset_visibility` UPDATE 4 表）
  - True → 走 B' 新逻辑
- `get_active_filter` 检查 flag：True 用 dataset_id 过滤，False 降级 is_deleted=false
- 支持项目级 override：某项目出问题可单独关闭，其他项目继续 B'

**灰度计划**：
- Day 0：flag 默认 False，但代码 deploy
- Day 3：灰度开启 1 个内部测试项目（flag=True 项目级 override）
- Day 7：全局 flag 改 True（结合 F18 Day 7 migration 同步发生）
- 出问题：`set_project_flag(pid, "ledger_import_view_refactor_enabled", False)` 单项目回退

**验收**：
- `test_b_prime_feature_flag.py`：flag=False 时 activate 走老逻辑（UPDATE Tb*），flag=True 走新逻辑
- 灰度剧本（runbook）文档化

### 2.F 云平台协同（F20-F25）

**业务背景**：审计项目是团队协作场景，一个项目组常有 3-10 个成员，常见工作流：
1. PM 或审计助理 A 上传客户账套 → B/C/D/E 其他成员依赖这份数据做底稿、抽样、分析
2. A 正在导入时 B 要查报表 → 看不到新数据但也不知道"正在导入中"
3. A 网络掉线后 job 卡住 → B 没法接手
4. activate 完成后 B 打开的报表页仍显示旧数据（无自动刷新）

现有架构 80% 就绪（`ProjectAssignment` / outbox event / WebSocket 通道 / `get_active_dataset_id` 单一真源），缺的就是"推送到前端 + 锁透明 + 接管机制"。

#### F20 激活广播
**实现**：
- `DatasetService.activate` 事务提交后，向 outbox 写入 `DATASET_ACTIVATED` 事件，payload 含 `{project_id, year, dataset_id, activated_by, activated_at, row_counts}`
- WebSocket 通道 `/ws/project/{project_id}/events` 把事件推给该项目组所有在线成员
- 前端 `useProjectEvents(projectId)` composable 订阅后，对 dataset 相关事件触发局部 store 刷新（余额树形 / 报表 / 底稿预填充数据）

**验收**：
- `test_ws_dataset_broadcast.py`：A 激活 → B 的 WS client 3s 内收到事件
- UAT：A 激活后 B 打开的报表页自动刷新显示新数据

#### F21 锁透明
**痛点**：当前 A 在导入时，B 点"导入"按钮仅看到"有导入进行中"红字，不知道是谁/进度多少/还要多久

**实现**：
- `ImportQueueService.get_lock_info(project_id)` 新增，返回 `{holder_user_id, holder_name, job_id, current_phase, progress_pct, estimated_remaining_seconds, acquired_at}`
- 前端导入按钮 hover / 禁用态显示详情 tooltip
- A 的进度更新通过 F20 WS 通道广播给所有项目组成员（不只是 holder）

**验收**：
- UAT：B 鼠标悬停禁用的导入按钮 → 看到 `"A 正在导入中 / parse 阶段 45% / 预计剩余 6 分钟"`
- `GET /api/projects/{pid}/ledger-import/active-job` 返回的 job 字段含 holder 信息

#### F22 导入接管
**痛点**：A 网络掉线后 heartbeat 超 5min → 当前 `recover_jobs` 会把 job 重置，但锁仍卡在 A

**实现**：
- `ImportQueueService.acquire_lock` 允许 takeover：若当前 holder 的 `last_heartbeat > 5min`，允许其他成员抢占锁
- `ImportJob.created_by` 字段扩展为 `creator_chain: list[user_id]` 记录接管链路
- 接管后 job 从 checkpoint 恢复（复用 F14 机制）
- 前端"接管导入"按钮（仅 PM / admin 权限）

**验收**：
- `test_import_takeover.py`：模拟 A heartbeat 过期 → B 接管成功 → job 从 `activating` 阶段继续完成

#### F23 rollback 走 ImportQueue 锁
**痛点**：当前 `DatasetService.rollback` 不走 ImportQueue 锁，若 A 在 activate 同时 B 在 rollback，可能并发冲突

**实现**：
- `rollback` 调用前 `ImportQueueService.acquire_lock(project_id, action="rollback")`
- activate / rollback 互斥（同 project 同时只有一个操作）
- 操作完成后自动释放锁

**验收**：
- `test_activate_rollback_mutex.py`：并发触发 activate + rollback，断言二者互斥且无数据损坏

#### F24 只读旁观
**实现**：
- `GET /api/projects/{pid}/ledger-import/jobs/{job_id}` 放宽权限：项目组成员（ProjectAssignment 任一角色）可读
- 写操作（cancel / retry / rollback）仍需特定权限

**验收**：
- `test_job_readonly_access.py`：auditor 角色可 GET jobs/{id}，不可 POST cancel（403）

#### F25 审计溯源完整
**现状**：`ActivationRecord` 已记录 who/when（F4）

**扩展**：
- 新增字段：`ip_address`、`duration_ms`、`before_row_counts` / `after_row_counts`、`reason`（可选，F31 提供 UI 输入）
- `rollback` 同步创建 `ActivationRecord` with `action="rollback"`（当前只有 activate 记录）

**验收**：
- `GET /datasets/history` 接口返回的时间轴含 IP / 耗时 / 行数快照 / 操作理由
- 符合 F4 + F25 联合验收

### 2.G 数据正确性保障（F26-F29）

#### F26 staged 孤儿扫描
**痛点**：某些边缘场景会留下 "staged dataset 但无 ImportJob 关联" 的孤儿：
- Worker 启动时 crash（dataset 已建但 job 未创建）
- `recover_jobs` 把 job 标 failed 但忘了清 dataset
- 手工在 DB 改 status 产生的脏数据

**实现**：
- 新增 `scan_staged_orphans()` 定时任务（每 1h 跑一次）
- 逻辑：`SELECT d FROM ledger_datasets d WHERE d.status='staged' AND d.created_at < NOW()-INTERVAL '24 hours' AND NOT EXISTS (SELECT 1 FROM import_jobs j WHERE j.dataset_id=d.id AND j.status IN ('running','queued','activating'))`
- 扫到的孤儿自动调 `cleanup_dataset_rows(dataset_id)` + `mark_superseded`
- 清理记录写 `ActivationRecord` with `action="orphan_cleanup"`

**验收**：
- `test_staged_orphan_cleanup.py`：手工建孤儿 dataset → 1h 内被自动清

#### F27 激活前 integrity check
**痛点**：metadata 切换 <1s 很爽，但万一 staged 写入过程中有行丢失（崩溃后部分 commit / 磁盘错误 / race condition）？
当前 activate 只看 gate rules，不校验实际行数

**实现**：
- `DatasetService.activate` 在 metadata 切换前新增：
  ```python
  for table in [TbBalance, TbLedger, TbAuxBalance, TbAuxLedger]:
      actual = await db.scalar(select(func.count()).where(table.dataset_id == dataset_id))
      expected = record_summary[table.__tablename__]
      if actual != expected:
          raise IntegrityError(f"{table}: expected {expected} got {actual}")
  ```
- 失败 → 阻断激活 + 标 `ImportJob.status='integrity_check_failed'` + 告警
- <1s 成本换防静默损坏

**验收**：
- `test_activate_integrity_check.py`：手动删除 staged 的部分行 → activate 被拒绝 + 触发告警

#### F28 恢复剧本文档
**实现**：新增 `docs/adr/ADR-003-ledger-import-recovery-playbook.md`，覆盖常见故障：

| 场景 | 症状 | 恢复命令 |
|------|------|---------|
| activate 中 PG 重启 | job 卡在 activating | `resume_from_checkpoint(job_id)` |
| staged 孤儿 | `ledger_datasets.status='staged'` 很多 | 手动触发 `scan_staged_orphans()` |
| 索引膨胀 | index size > 2× table size | `REINDEX CONCURRENTLY idx_tb_*_active_queries` |
| connection leak | pg_stat_activity 连接数持续上涨 | 排查 pipeline 未释放连接 → 重启 worker |
| 诡异的可见性错误 | B 看不到 A 激活的数据 | 查 `ledger_datasets.status` + WS 是否推送成功 |

每场景含诊断命令序列 + 验证步骤 + 回滚操作。

**验收**：runbook 可执行（实际走一遍验证命令无误）

#### F29 事务隔离 ADR
**实现**：新增 `docs/adr/ADR-004-ledger-activate-isolation.md`
- 明确 `DatasetService.activate` 事务隔离级别为 `REPEATABLE READ`（防并发 activate 产生双 active）
- 幂等键：同 `(project_id, year, dataset_id)` 二次 activate 应返回成功（而非报错）
- 记录选择依据 + 可能的边界 case

**验收**：文档审查通过 + 代码注释引用该 ADR

### 2.H 用户体验补强（F31-F32）

#### F31 激活意图确认
**现状**：当前前端点"激活"按钮后直接调 API，无二次确认
**痛点**：激活是不可逆操作（会把旧 active 标 superseded，B/C/D 立即看到新数据），误点代价大

**实现**：
- 前端 `DatasetActivationButton.vue` 点击后弹 ElMessageBox：
  ```
  即将激活数据集：YG2101-2025-V3
  影响：所有项目组成员立即看到新数据
  旧版本：V2（2025-05-09 10:30 激活）将标记为 superseded
  
  激活理由（可选）：____________________
  [取消]  [确认激活]
  ```
- "激活理由"进 `ActivationRecord.reason`（F25 扩展字段）

**验收**：
- UAT：点激活按钮 → 出现确认对话框
- reason 非空时存入 DB 可查

#### F32 错误友好化
**现状**：`errors.py` 定义了 31 个错误码（L1_* / L2_* / L3_* / HEADER_* / ENCODING_*）
**痛点**：用户看到 `L2_LEDGER_YEAR_OUT_OF_RANGE` 完全不知道怎么解决

**实现**：
- 新增 `backend/app/services/ledger_import/error_messages.py`：
  ```python
  ERROR_HINTS = {
      "L2_LEDGER_YEAR_OUT_OF_RANGE": {
          "title": "序时账年度超出范围",
          "description": "序时账中的凭证日期年份与导入年度不符",
          "suggestions": [
              "检查文件是否包含跨年数据（如 2024 年年底凭证）",
              "在高级选项中启用'允许跨年数据'",
              "删除不属于本年度的凭证行后重新上传",
          ],
          "severity": "blocking",
      },
      # 其他 30 个错误码...
  }
  ```
- `/diagnostics` 端点响应增强 `findings` 数组每条加 `hint` 字段
- 前端 `ErrorDialog.vue` 显示标题 / 描述 / 建议列表

**验收**：
- 31 个错误码全部有 hint 映射（test 断言）
- UAT：触发 `L2_LEDGER_YEAR_OUT_OF_RANGE` → 前端显示"建议：启用'允许跨年数据'或删除不属于本年度的凭证"

### 2.I 安全与健壮性（F40-F46）

#### F40 上传文件安全校验
**痛点**：当前 `/detect` 和 `/submit` 端点对上传文件仅做简单扩展名检查
- 攻击面 1：恶意 xlsx 内嵌宏/公式注入（=cmd|'/c calc'!A1）
- 攻击面 2：zip bomb（42KB 压缩包解压 42GB，打爆磁盘）
- 攻击面 3：上传非预期类型（.exe 改扩展名为 .xlsx）

**实现**：
- 上传时校验：MIME type（`python-magic` 库）+ 扩展名 + 文件头 magic number 三者一致
- 大小上限：xlsx ≤ 500MB / csv ≤ 1GB / zip ≤ 200MB（超限直接 413）
- zip bomb 防护：解压前读 central directory 检查总未压缩大小，比值 > 100× 拒绝
- xlsx 检查：拒绝含 `xl/vbaProject.bin`（宏）或 `xl/externalLinks/` 的文件
- 所有拒绝记录 `audit_log` with `action="upload_rejected"` + 文件名 + 拒绝原因 + 上传者 IP

**验收**：
- `test_upload_security.py`：(a) .exe 改名 xlsx 被拒 (b) zip bomb 被拒 (c) 含宏 xlsx 被拒
- UAT：上传 501MB xlsx 返回 413 + 友好错误消息

#### F41 项目权限与 tenant 预留
**痛点**：
- 当前业务查询依赖"前端传对 project_id"，后端未做强制校验（grep 发现部分路由仅按 path param 查询不验 user 权限）
- 未来接入多租户（如 SaaS 部署）时，缺 tenant_id 导致全平台重构

**实现**：
- `get_active_filter` 签名增加强制 `current_user` 参数：
  ```python
  async def get_active_filter(db, table, project_id, year, current_user):
      # 先校验 current_user 对 project_id 有 ProjectAssignment
      await verify_project_access(db, current_user.id, project_id)
      # 再返回 filter 条件
  ```
- Tb* 四表 Alembic 迁移新增 `tenant_id VARCHAR(64) NOT NULL DEFAULT 'default'` + 联合索引 `(tenant_id, project_id, year)`
- 当前单租户场景所有行 `tenant_id='default'`，完整多租户走 O15 独立 Sprint
- `ledger_datasets` 同步加 tenant_id 字段

**验收**：
- `test_cross_project_isolation.py`：user_a 查 user_b 项目的 tb_balance → 返回空（而非抛 403 暴露"存在但无权")
- Alembic 迁移可重入（downgrade + upgrade 循环）

#### F42 零行/异常规模拦截
**痛点**：
- 用户误上传空表 → 当前 pipeline 跑完 0 行，dataset 激活后覆盖旧数据，用户才发现报表全空
- 或上传错误的年度文件（期望 2025 但传了 2024 全量）→ 规模异常但 pipeline 不拦截

**实现**：
- detect 阶段新增规则：
  - `total_rows_estimate < 10` → 返回警告 `EMPTY_LEDGER_WARNING`，前端需二次确认
  - 对比同 project 历史 activate 的 dataset 行数均值，若新 dataset < 0.1× 或 > 10× → 警告 `SUSPICIOUS_DATASET_SIZE`
- 用户在前端点"继续"后才能 submit（`force_submit=True` 标记写入 ImportJob）
- activate 阶段再次 integrity check（F27）兜底

**验收**：
- `test_empty_ledger_rejection.py`：0 行文件 detect 返回 warning + force_submit=False 时 submit 被拒
- 连续导入 5 次 YG2101（均 650k 行）后，第 6 次导入 6.5k 行文件 → 触发 SUSPICIOUS 警告

#### F43 健康检查端点
**痛点**：Kubernetes / Docker liveness probe 只能打 `/` 返 200，无法判断 ledger-import 子系统是否健康

**实现**：
- 新增 `GET /api/health/ledger-import` 返回：
  ```json
  {
    "status": "healthy|degraded|unhealthy",
    "queue_depth": 3,
    "active_workers": 2,
    "expected_workers": 2,
    "p95_duration_seconds": 180,
    "pg_connection_pool_used": 12,
    "pg_connection_pool_max": 20,
    "last_successful_activate_at": "2026-05-10T14:20:00Z"
  }
  ```
- 状态判定：
  - healthy：workers 全存活 + P95 < 10min + pool 占用 < 80%
  - degraded：P95 > 10min 或 pool > 80%
  - unhealthy：worker 挂了 或 pool 满
- Kubernetes liveness probe 打这个端点，degraded 不触发重启，unhealthy 触发

**验收**：
- `test_health_endpoint.py`：手动 kill worker → 端点返回 unhealthy
- Prometheus 可从 `/metrics` 读到 `ledger_import_health_status` gauge（与 `/health` 联动）

#### F44 graceful shutdown
**痛点**：当前 worker 收 SIGTERM 立即退出，正在处理的 chunk 丢失 → staged dataset 断裂 → 需要 `recover_jobs` 兜底

**实现**：
- worker 注册 `signal.SIGTERM` handler：
  - 设 `stop_event.set()` 通知 pipeline
  - pipeline 在 `cancel_check()` 回调中读取 stop_event，当前 chunk 结束后退出
  - 超时保护：若 30s 内未退出，强制 SIGKILL（避免死循环）
- job 状态标记为 `interrupted`（新增状态），与 `canceled` 区分
- 重启后 `recover_jobs` 优先处理 `interrupted` job（从 checkpoint 恢复）

**验收**：
- `test_worker_graceful_shutdown.py`：启动 job → 发 SIGTERM → 断言 30s 内退出 + job status=interrupted
- 重启后 `resume_from_checkpoint` 成功续跑

#### F45 事件广播可靠性
**痛点**：F20 WS 广播失败（网络抖动/client 掉线）会丢事件 → B 永远看不到激活
- 当前 outbox event 已有 retry 机制，但 WS push 不走 outbox

**实现**：
- `DatasetService.activate` 提交事务时，同步写 `event_outbox` 一条 `DATASET_ACTIVATED` 记录（status=pending）
- `outbox_replay_worker`（已有）轮询 pending event，调 WebSocket push
- push 失败递增 `retry_count`，最多 3 次
- 超过 3 次 → 移入 DLQ（`event_outbox_dlq` 表），触发告警 `alert_event_broadcast_failed`
- 运维手动检查 DLQ 后决定重投或丢弃

**验收**：
- `test_broadcast_retry_with_outbox.py`：模拟 WS push 失败 → event 留在 outbox / 重试 3 次后进 DLQ
- DLQ 监控告警接入 F43 健康检查

#### F46 rollback 下游联动
**痛点**：
- 用户 rollback 数据集后，基于旧数据已生成的 Workpaper/Report 实际已过时
- 当前 rollback 只切 metadata，**不通知下游** → 底稿仍显示旧数据的错报/调整，用户不知已失效

**实现**：
- `DatasetService.rollback` 提交事务时，写 outbox 事件 `DATASET_ROLLED_BACK` + payload `{project_id, year, old_dataset_id, new_active_dataset_id}`
- `event_handlers.py` 新增订阅：
  - `WorkingPaper` 找所有 `project_id=X + year=Y + source_type='ledger'` → `is_stale=True`
  - `AuditReport` / `DisclosureNote` 同理 → `is_stale=True`（复用 R1 事件联动链路）
- 前端打开这些对象时显示"数据已过时"横幅 + "立即刷新"按钮（复用 R7-S3 stale banner 机制）

**验收**：
- `test_rollback_downstream_stale.py`：activate V2 → 生成 Workpaper → rollback → Workpaper.is_stale=True
- UAT：前端打开底稿看到 stale banner

### 2.J 数据校验透明化（F47-F49）

**业务背景**：用户在「数据校验」入口看到差异（如 *"1002 银行存款 期末应 -148,268 但实际 110.30"*），当前只看到一个数字差异，不知道：
- 这个期末是怎么算出来的？用了哪个公式？
- 为什么差这么多？差的 148,378 元是从哪里来的？
- 哪些凭证行参与了计算？
- 是本期发生额算错了、还是期初余额就错了？

现有 validator 已计算出差异（见 `validator.py:548` `tolerance` + `diff`），但 finding 里**只返回一条中文 message**，没有把公式、代入值、中间步骤、差异来源暴露给用户。审计人员需要手工翻凭证逐条核对，体验非常痛。

**核心原则**："校验不是黑盒，每个差异都能被用户独立复现"

#### F47 校验过程透明化（每条 finding 附公式 + 代入 + 分解）
**现状**：
- L2/L3 finding 仅有 `message` 字符串（如 `"余额表期末余额与序时账累计不一致（动态容差），差异超出容差范围"`）
- 用户无法从前端 API 响应中得知：用了什么公式、代入的数字、差异来源、容差阈值

**实现**：
- `ValidationFinding` 模型扩展 `explanation` 字段（dict，可选，L2/L3 必填）：
  ```json
  {
    "formula": "closing_balance = opening_balance + sum(debit_amount) - sum(credit_amount)",
    "formula_cn": "期末余额 = 期初余额 + 借方累计 - 贷方累计",
    "inputs": {
      "account_code": "1002",
      "account_name": "银行存款",
      "opening_balance": 148151.74,
      "sum_debit_amount": 20801494.24,
      "sum_credit_amount": 20949535.68,
      "ledger_rows_count": 458
    },
    "computed": {
      "expected_closing_balance": -148.70,
      "actual_closing_balance": 110.30,
      "diff_absolute": 259.00,
      "tolerance_threshold": 210.00,
      "tolerance_formula": "min(1.0 + max(|opening|,|sum_debit|,|sum_credit|) × 0.00001, 100.0)"
    },
    "diff_breakdown": [
      {"source": "opening_balance", "value": 148151.74, "weight": "+"},
      {"source": "sum_debit_amount", "value": 20801494.24, "weight": "+"},
      {"source": "sum_credit_amount", "value": 20949535.68, "weight": "-"},
      {"source": "expected_closing", "value": -148.70, "computed": true},
      {"source": "actual_closing", "value": 110.30, "source_row_id": "<tb_balance.id>"}
    ],
    "hint": "期末余额与序时账累计差异 259 元。请检查: (1) 是否有凭证未过账 (2) 期初余额是否填错"
  }
  ```
- 适用范围：
  - **L2 BALANCE_UNBALANCED**（借贷不平）：公式 `sum_debit = sum_credit`，输入含两边累计值 + 差额 + 样本凭证号
  - **L2 LEDGER_YEAR_OUT_OF_RANGE**（年度越界）：输入含年度边界 + 越界凭证样本（前 10 条）
  - **L3 BALANCE_LEDGER_MISMATCH**（余额 vs 序时不一致）：上述 JSON 结构完整示例
  - **L3 AUX_ACCOUNT_MISMATCH**（辅助科目主表缺失）：输入含 aux 侧有/主侧无 的科目列表
  - **L1 类型错误**（金额非数/日期非法）：输入含原值字符串 + 解析失败原因 + 所在行号
- validator.py 每条 finding 产出时同步填充（重构 `validate_l3_cross_table` 返回 explanation 对象）
- 前端 `DiagnosticPanel.vue` 新增「展开过程」按钮，以折叠卡片展示公式+代入值+分解表格

**验收**：
- 每个 finding code 的 explanation schema 有专属 Pydantic model（`BalanceMismatchExplanation` / `UnbalancedExplanation` / `YearOutOfRangeExplanation` 等）
- `test_finding_explanation.py`：每种 finding code 生成的 explanation 字段齐全、公式可验证（手算对照）
- UAT：用户点开"差异 259 元"卡片 → 看到公式 + 代入值 + 差异贡献拆解，5 秒内理解差异来源

#### F48 校验规则说明文档（前端入口 + API）
**痛点**：用户根本不知道系统会校验什么规则，只有触发失败时才"事后看到"

**实现**：
- 后端新增 `GET /api/ledger-import/validation-rules` 返回规则清单：
  ```json
  [
    {
      "code": "L3_BALANCE_LEDGER_MISMATCH",
      "level": "L3",
      "severity": "blocking",
      "title": "余额表期末余额 vs 序时账累计核对",
      "formula": "closing_balance = opening_balance + sum(debit_amount) - sum(credit_amount)",
      "formula_cn": "期末余额 = 期初余额 + 借方累计 - 贷方累计",
      "tolerance": "动态：1 元 + 最大金额 × 0.001%，上限 100 元",
      "scope": "按 account_code 逐科目检查",
      "why": "确保余额表和序时账数据一致性，发现漏记凭证/金额错误",
      "example": {
        "inputs": {"opening": 100000, "debit": 50000, "credit": 30000},
        "expected": 120000,
        "pass": "actual ∈ [119999, 120001]",
        "fail": "actual = 130000 → diff=10000 > tolerance=1"
      },
      "can_force": true
    },
    {...}
  ]
  ```
- 前端新增"校验规则说明"页面（`/ledger-import/validation-rules`），按 L1/L2/L3 分组展示
- 导入前用户可预览规则；导入后 finding 的 `code` 点击直达该规则详情页
- 规则清单来源：`validator.py` 模块级字典 `VALIDATION_RULES_CATALOG`（单一真源，finding.code 必须在 catalog 中）

**验收**：
- `test_validation_rules_catalog.py`：catalog 中的每个 code 都能在 validator.py 中找到产生位置；反之亦然（双向一致性）
- UAT：用户打开"校验规则说明"页面能看完 31+ 条规则，带公式和示例

#### F49 差异下钻到明细行
**痛点**：用户知道"1002 银行存款差异 259"后，下一步必然想看"哪些凭证参与了这个科目？哪条可能错？"

**实现**：
- `ValidationFinding.location` 扩展 `drill_down` 字段：
  ```json
  {
    "file": "YG2101.xlsx",
    "sheet": "序时账",
    "row": null,
    "column": null,
    "drill_down": {
      "target": "tb_ledger",
      "filter": {"account_code": "1002", "year": 2025},
      "expected_count": 458,
      "sample_ids": ["<id1>", "<id2>", "<id3>"]
    }
  }
  ```
- 前端 `DiagnosticPanel.vue` 每条差异 finding 加「查看明细 (458 行)」按钮，点击打开侧边抽屉展示该科目所有 ledger 行
- 侧边抽屉复用现有 `LedgerPenetration.vue` 穿透组件（按 account_code 过滤 tb_ledger）
- 余额表侧也可下钻（`tb_balance` WHERE account_code=X，一行展示期初/期末/发生额原始数据）

**验收**：
- `test_finding_drill_down.py`：drill_down 字段在 L3_BALANCE_LEDGER_MISMATCH / AUX_ACCOUNT_MISMATCH 上正确填充
- UAT：用户点"查看明细" → 抽屉打开 → 显示 458 条凭证，可排序/导出/复制；3 次点击内定位到疑似错账行

### 2.K 业务闭环与合规（F50-F53）

**业务背景**：审计平台不是"独立数据库"，而是"底稿/报表/结论"链条的源头。前面所有需求解决"导入本身怎么做好"，这一章解决"导入如何和上游下游业务正确衔接"。

#### F50 下游对象快照绑定（审计合规关键）
**痛点**：
- 当前 Workpaper/AuditReport/DisclosureNote **不记录它们引用的是哪个 dataset_id**，只按"当前 active"取数
- 场景：PM 3 月激活 V2 数据 → 审计助理做底稿引用 V2 → 6 月签字合伙人签字完成 → 8 月 PM rollback 到 V2 之前的 V1 → **已签字报表的数字突然变了** → 严重违反审计留痕原则
- 场景：底稿用 V2 做的，但 rollback 到 V1 后，底稿显示 `is_stale` 但点进去还是用 `get_active_filter` 跑出 V1 的数，历史状态丢失

**实现**：
- Workpaper / AuditReport / DisclosureNote / UnadjustedMisstatement 等下游模型新增：
  - `bound_dataset_id UUID NULL`：引用时绑定的 dataset_id
  - `dataset_bound_at TIMESTAMPTZ NULL`：绑定时间
- 绑定触发时机：
  - Workpaper 首次生成 → 记录当时的 active dataset_id
  - AuditReport 状态转 `eqcr_approved` 或 `final` → **自动锁定** `bound_dataset_id`（签字后不变）
- 查询扩展：`get_active_filter` 增加可选参数 `force_dataset_id`：
  - 如果传入（即下游已绑定），则忽略 `status='active'` 条件，强制查该 dataset_id
  - 下游 service 查数据时优先用 `bound_dataset_id`，未绑定才走 active
- rollback 保护：
  - rollback 前检查"有下游对象绑定到当前 active dataset"时：
    - 如果下游已 `final` 签字 → **禁止** rollback（返回 409 + 列出阻断对象）
    - 如果未签字 → 允许 rollback + 所有绑定对象标 `is_stale=True`（F46 已有）
- 前端提示：
  - rollback 对话框显示"本次回滚将影响 N 个底稿、M 个报表"，列出对象名
  - 已锁定的报表页面显示"数据版本：V2（已锁定，不随数据集变化）"徽章

**验收**：
- `test_workpaper_dataset_binding.py`：Workpaper 生成后查 `bound_dataset_id` 非空 + 查询数据走该 dataset
- `test_signed_report_rollback_protection.py`：报表 final 后尝试 rollback → 返 409 + 报表数字不变
- UAT：PM 误点 rollback 已签字报表的数据 → 前端弹"不允许：已有 1 份 final 报表绑定此数据集"
- 合规：审计合伙人签字后数据永远锁定，可法庭举证

#### F51 全局并发限流与资源隔离
**痛点**：
- 当前 `ImportQueueService` 只在**项目级**做串行（同项目同时只有 1 个导入），但同一时间**100 个项目**都可以并发导入
- YG2101 级导入峰值占用 PG 1-2 连接 + 1 worker 协程 + 2GB 内存；100 并发 = 200 PG 连接 × 2GB = 打爆 PG 连接池（默认 max_overflow=80）+ OOM
- 平台级别缺乏"全局 worker 上限"+"全局排队"机制

**实现**：
- 新增 `GlobalImportConcurrencyService`，基于 Redis semaphore：
  - 全局最多 3 个 pipeline 并行（可配置 `LEDGER_IMPORT_MAX_CONCURRENT=3`）
  - 超额 job 状态置 `queued`，FIFO 排队
  - 前端 `/active-job` 端点扩展显示 `queue_position: 5 (前面还有 4 个项目)`
- 资源保护：
  - 单 pipeline 最多占 3 个 PG 连接（parse/validate/write 各 1，B' 后 activate 瞬时归还）
  - 内存峰值超过 `MEMORY_LIMIT_MB=3000` → pipeline 主动降级（关闭 calamine 回到 openpyxl 流式，单 chunk 降到 10k 行）
- 动态配置：
  - 运维可通过 feature flag 临时调大并发（如半夜批量导入）
  - `/metrics` 暴露 `ledger_import_concurrent_jobs` gauge

**验收**：
- `test_global_concurrency_limit.py`：并发提交 10 个 job → 最多 3 个 running，其余 queued，完成后依次启动
- `test_memory_downgrade.py`：模拟内存逼近 3GB → pipeline 降级到 openpyxl + 10k chunk
- 压测：100 并发上传 YG4001（4k 行）→ 5 分钟内全部完成、PG 连接数峰值 < 50

#### F52 列映射历史智能复用
**痛点**：
- 用户 A 项目用户友 ERP，第一次导入手动配了列映射（"凭证号列 → voucher_no"等 15 个字段）
- 第二个月再导同一 ERP 的新月份数据 → **用户要重新配一遍同样的映射**
- 现有 `column_mapping_service` 已保存历史但 detect 阶段未自动应用

**实现**：
- detect 阶段对每个 sheet 计算 `file_fingerprint`（`hash(sheet_name + header_cells[:20] + software_hint)`）
- 查询 `ImportColumnMappingHistory` 表（S2 已建）WHERE `project_id=X AND file_fingerprint=Y AND created_at > 30 days`（最近 30 天内有复用价值）
- 命中时 detect 响应中每个 column 返回：
  - `auto_applied_from_history: true`
  - `history_mapping_id`: UUID
  - `confirmed_by`: 上次确认人
  - `confirmed_at`: 上次时间
- 前端 `ColumnMappingEditor.vue` 显示绿色 badge "🕒 上次映射（2 周前）" + 一键"应用全部历史"按钮
- 用户改动 → 新 fingerprint 或覆盖旧记录（带 `override_parent_id` 溯源链）
- 跨项目复用：同 `software_hint`（如 "用友 NC"）匹配时降级为"建议"而非"自动应用"

**验收**：
- `test_column_mapping_history_reuse.py`：第一次导入手动映射 → 第二次同文件 fingerprint → 自动应用历史
- UAT：同客户同 ERP 第二次导入直接点"下一步"跳过映射步骤
- 效率指标：9 家样本第二次导入平均节省映射时间 > 50%

#### F53 留档合规保留期差异化（中国《会计法》10 年）
**痛点**：
- 当前 `ImportArtifact.expires_at` 默认 90 天，对审计业务不够（审计底稿合规留档要求 10 年）
- purge 任务（F3）对 `superseded` 一视同仁物理 DELETE，如果某个 superseded dataset 被"已签字报表"引用（F50 场景）→ 不应该被删
- 中国《会计档案管理办法》：会计凭证、账簿保管期限 30 年；企业所得税法实施条例：账簿保管 10 年

**实现**：
- `ImportArtifact` 模型新增 `retention_class` 字段：
  - `transient`（默认）：90 天过期，purge 任务物理删
  - `archived`：10 年过期，仅删磁盘原始文件，元数据永久保留
  - `legal_hold`：法定保留（诉讼中），永不删除
- dataset 激活时自动决定 artifact 类别：
  - 有下游 `final` 报表绑定（F50） → `archived`
  - 有 `legal_hold_flag`（运维手动设）→ `legal_hold`
  - 否则 `transient`
- purge 任务（F3）逻辑扩展：
  - 同 project+year 保留 1 active + N=3 superseded **unreferenced**（无下游绑定）
  - `archived` 类别 superseded 数量不计入 N 限制
  - purge 前检查 F50 的 `bound_dataset_id`，被引用的永不删
- 前端"导入历史"页面展示每个 dataset 的 retention 类别（徽章 `📁 transient` / `🔒 archived` / `⚖️ legal_hold`）

**验收**：
- `test_retention_class_assignment.py`：final 报表绑定后 dataset 的 artifact 类别自动升级为 archived
- `test_purge_respects_bindings.py`：purge 任务不删 bound_dataset_id 被引用的 dataset
- 合规：抽查 5 个 final 项目 → 其账套原始文件均可溯源 10 年

---

## 三、非功能需求

### 3.1 性能

| 指标 | 当前 | 目标 | 验证方法 |
|------|------|------|---------|
| YG2101 activate 阶段 | 127-193s | < 1s | `b3_diag_yg2101.py` 的 `phase=activate_dataset_done` 增量 |
| YG2101 total 耗时 | 400-482s | < 250s | `b3_diag_yg2101.py` 的 `total=` 行 |
| YG36 total 耗时 | 12-25s | < 60s（保持） | `e2e_full_pipeline_validation.py` |
| YG4001-30 total 耗时 | 9s | < 15s（保持） | `e2e_yg4001_smoke.py` |
| **超大档基线**（陕西华氏 2025 或合成 500MB CSV）| N/A | < 1800s（30min） | `test_huge_ledger_smoke.py`（可选标记） |
| 关键查询 EXPLAIN 回归 | N/A | < 1.2× | 手测 `metabase_service` 4 SQL |
| F10 392MB CSV detect | - | < 5s | `test_large_csv_smoke.py` |
| F10 parse 内存峰值 | - | < 200MB | `test_large_csv_smoke.py` + 内存 profiling |
| **单 worker 进程峰值内存** | N/A | < 2GB（防 OOM killer） | YG2101 跑时 `ps -o rss` 采样 |
| **单 sheet parse 超时护栏** | N/A | > 10min 自动 timeout | `ImportJob.timeout_seconds` + heartbeat 机制 |
| F13 进度更新频率 | 每 chunk（50k 行）1 次 | 每 5% 或 10k 行 ≥ 1 次 | perf 日志 `_n_progress_calls` 统计 |
| F17 耗时预估误差 | N/A | ±30%（L 档）/ ±50%（S 档） | 9 家样本对照预估 vs 实测 |
| **连接池单 worker 占用** | 1 连接长持（activate 127s） | ≤ 3 连接（parse/write/activate 各 1，B' 后 activate <1s 立即释放） | `pg_stat_activity` 采样 |

### 3.2 数据库健康

| 指标 | 目标 | 验证方法 |
|------|------|---------|
| Tb* 表 dead tuple 率 | < 10% | `SELECT n_dead_tup, n_live_tup FROM pg_stat_user_tables` |
| **索引 dead tuple 率** | 索引大小 < 2× 表大小 | `pg_relation_size(idx) vs pg_relation_size(table)` |
| 连续 10 次导入后总行数 | 4 × dataset 行数（线性增长） | 实测 YG2101 级 10 次导入 |
| purge 任务运行 | 每晚自动跑 + 尊重下游绑定与 retention 类别 | cron + 日志（F3 + F53）|
| **purge 后 REINDEX** | 每次 purge 完成后自动 `REINDEX CONCURRENTLY` | purge 任务日志含 REINDEX 条目 |
| partial index 充分利用 | 关键查询走 `idx_tb_*_active_queries` | EXPLAIN ANALYZE |
| **autovacuum 不阻塞业务** | `autovacuum_vacuum_cost_delay=5ms`（让出 CPU） | Alembic 迁移 ALTER TABLE |

**PG 配置持久化**（运维必做）：
- 已调参数需写入 `docker-compose.yml` 或 init SQL
- 包括：`wal_compression=pglz` / `synchronous_commit=off` / `wal_buffers=64MB` / `checkpoint_timeout=30min` / `max_wal_size=8GB` / `shm_size=2g`
- Tb* 表 autovacuum 参数（`vacuum_scale_factor=0.05`, `vacuum_cost_limit=1000`, `vacuum_cost_delay=5ms`）用 Alembic 迁移 ALTER TABLE

**VACUUM 锁冲突规避**（运维文档）：
- autovacuum 跑时申请 `ShareUpdateExclusive` 锁，会阻塞 DDL（加列/加索引）
- 生产发布窗口避开 autovacuum 高峰（凌晨跑的话发布选白天）
- 紧急 DDL 前可 `SELECT pg_cancel_backend(pid)` 打断 autovacuum

### 3.3 可维护性

| 指标 | 目标 | 验证方法 |
|------|------|---------|
| CI grep 卡点 | `TbX\.is_deleted\s*==` 命中 = 0 | `.github/workflows/ci.yml` step |
| `_set_dataset_visibility` 外部调用 | grep 结果 = 0 | CI 检查 |
| 测试覆盖率 | `DatasetService` 核心方法 > 90% | pytest-cov |
| ADR 归档 | `docs/adr/ADR-002-ledger-view-refactor.md` 完整 | 文件存在 + 审查通过 |
| 开发者文档 | `docs/LEDGER_IMPORT_V2_ARCHITECTURE.md` 更新"可见性"章节 | 文档 review |
| perf 日志标准化 | JSON 格式可被 grep/jq 解析 | 实测日志采样 |

### 3.4 兼容性 / 边界

| 场景 | 策略 |
|------|------|
| is_deleted 字段 | **保留**，仅写入默认值改 false；Alembic 不做 DROP COLUMN（回收站依赖）|
| 历史 dataset_id=NULL 数据 | `get_active_filter` 兜底分支 fallback `is_deleted=false`（当前测试环境无历史数据）|
| `ImportBatch` 旧引擎兼容 | 保持不变（smart_import_engine 旧路径仍可用，feature flag 控制）|
| 外部 event 消费者 | `LEDGER_DATASET_ACTIVATED` / `_ROLLED_BACK` event 结构保持，消费端无需改动 |
| **Artifact 保留期** | 默认 90 天 `expires_at`（`ImportArtifact` 模型已有字段）；运维定时清理过期 artifact 磁盘文件 |
| **取消后磁盘清理**（F15）| cancel 自动清 artifact 物理文件 + staged Tb* 行，零残留 |

### 3.5 可观测性（F16 对应）

| 指标 | 目标 | 实现 |
|------|------|------|
| `/metrics` 端点 | 返回 Prometheus 格式 | `prometheus_client` lib + FastAPI route |
| `/health/ledger-import` 端点 | 子系统健康状态 + K8s probe 可用 | F43 实现 |
| 导入耗时分布 | `ledger_import_duration_seconds{phase}` histogram | `pipeline._mark(phase)` 同步写 histogram |
| 作业状态计数 | `ledger_import_jobs_total{status}` counter | `ImportJobService.transition` 时递增 |
| dataset 数量趋势 | `ledger_dataset_count{project_id, status}` gauge | 定时任务刷新 |
| **WebSocket 通道** | `/ws/project/{pid}/events` 推 dataset/job 事件 | 复用现有 WebSocket 基建 |
| **项目组锁状态** | `GET /active-job` 返回 holder + progress + 预计剩余 | F21 实现 |
| **event_outbox DLQ 监控** | `event_outbox_dlq_depth` gauge | F45 实现 |
| **健康状态** | `ledger_import_health_status` gauge（0/1/2=healthy/degraded/unhealthy）| F43 实现 |
| 推荐告警规则 | P95 total > 10min / 失败率 > 5% / dead_tuple_ratio > 30% / DLQ 非空 | 文档化到运维 runbook |

### 3.6 安全（F40-F41 对应）

| 指标 | 目标 | 实现 |
|------|------|------|
| MIME + 魔数校验 | 上传文件三重校验一致 | `python-magic` + 文件头检查 |
| 大小上限 | xlsx ≤ 500MB / csv ≤ 1GB / zip ≤ 200MB | nginx + FastAPI 双层限制 |
| zip bomb 防护 | 解压前检查未压缩大小比 ≤ 100× | central directory 预读 |
| xlsx 宏拦截 | 拒绝含 vbaProject.bin / externalLinks | xlsx zip 内文件扫描 |
| 拒绝审计 | audit_log 记录所有被拒上传 | `action="upload_rejected"` |
| 项目权限强校验 | `get_active_filter` 必带 current_user + verify_project_access | 跨项目测试 100% 拦截 |
| tenant_id 预留 | Tb* 四表 + ledger_datasets 加 NOT NULL 默认 `'default'` | Alembic 迁移 |

### 3.7 健壮性（F44-F46 对应）

| 指标 | 目标 | 实现 |
|------|------|------|
| SIGTERM 响应 | ≤ 30s 完成当前 chunk 并退出 | worker signal handler + stop_event |
| 重启后恢复 | `interrupted` 状态 job 自动续跑 | `recover_jobs` + `resume_from_checkpoint` |
| 事件广播重试 | 失败 3 次后进 DLQ | `event_outbox_dlq` 表 + 告警 |
| rollback 下游失效 | Workpaper/Report/DisclosureNote 自动标 stale | `DATASET_ROLLED_BACK` 事件订阅 |
| 零行/异常规模拦截 | detect 阶段警告 + force_submit 门控 | F42 实现 |

---

## 四、测试矩阵

### 4.1 单元测试

| 文件 | 覆盖需求 | 关键断言 |
|------|---------|---------|
| `test_dataset_service_activate_view_refactor.py` | F1 | activate 后 `ledger_datasets.status` 切换，Tb* 表 UPDATE 计数 = 0 |
| `test_dataset_service_rollback_view_refactor.py` | F1 | rollback 后 metadata 正确切换 |
| `test_dataset_purge.py` | F3 | 跑 purge 后只剩最新 N=3 个 superseded |
| `test_b_prime_feature_flag.py` | F19 | flag=False 走老逻辑 / flag=True 走新逻辑 / 项目级 override |
| `test_progress_callback_granularity.py` | F13 | 模拟 50k 行 chunk，断言 progress_cb 被调用次数 ≥ 5 |
| `test_duration_estimator.py` | F17 | 4 档行数范围返回估算值 + 9 家样本误差 ±30% |

### 4.2 集成测试

| 文件 | 覆盖需求 | 关键断言 |
|------|---------|---------|
| `test_multi_year_coexist.py` | F5 | 同 project 2024+2025 双 active 不串 |
| `test_dataset_concurrent_isolation.py` | F1 | A 项目 staged + B 项目 active 业务查询不串 |
| `test_rollback_full_flow.py` | F1 | 导入 → activate → 再导入 → activate → rollback → 看到第一份数据 |
| `test_9_samples_header_detection.py` | F11 | 9 家样本 `data_start_row` + `header_cells` 符合快照 |
| `test_large_csv_smoke.py` | F10 | 合成/真实 CSV 的 detect 耗时 + parse 内存 |
| `test_table_type_robustness.py` | F8 | YG36/安徽骨科/辽宁卫生 双余额表分流正确 |
| `test_resume_from_activation_checkpoint.py` | F14 | activate 抛异常 → resume 后数据集成功激活 |
| `test_cancel_cleanup_guarantee.py` | F15 | cancel 后 30s 内 job=canceled + Tb* 行数 0 + artifact 文件不存在 |
| `test_metrics_endpoint.py` | F16 | `curl /metrics` 含 3 个核心指标且有数据点 |
| `test_migration_day7_update.py` | F18 | Day 7 一次性 UPDATE SQL 幂等、正确切换 active 行 is_deleted |
| `test_ws_dataset_broadcast.py` | F20 | A 激活 → B 的 WS client 3s 内收到 `DATASET_ACTIVATED` 事件 |
| `test_import_takeover.py` | F22 | A heartbeat 过期 → B 接管成功 + checkpoint 恢复 |
| `test_activate_rollback_mutex.py` | F23 | 并发触发 activate + rollback → 互斥成功，无数据损坏 |
| `test_staged_orphan_cleanup.py` | F26 | 手工建孤儿 dataset → 1h 内被 `scan_staged_orphans` 清理 |
| `test_activate_integrity_check.py` | F27 | 删除 staged 部分行 → activate 被拒绝 + 状态 `integrity_check_failed` |
| `test_job_readonly_access.py` | F24 | auditor 可 GET jobs/{id}，不可 POST cancel（403）|
| `test_upload_security.py` | F40 | .exe/zip bomb/含宏 xlsx 三类文件被拒 + audit_log 记录 |
| `test_cross_project_isolation.py` | F41 | user_a 查 user_b 项目的 tb_balance → 返回空 |
| `test_empty_ledger_rejection.py` | F42 | 0 行文件 detect 返 warning / force_submit=False 时 submit 被拒 |
| `test_health_endpoint.py` | F43 | kill worker → 端点返 unhealthy |
| `test_worker_graceful_shutdown.py` | F44 | SIGTERM → 30s 内退出 + job=interrupted + 重启后续跑 |
| `test_broadcast_retry_with_outbox.py` | F45 | WS push 失败 → 重试 3 次后进 DLQ + 告警触发 |
| `test_rollback_downstream_stale.py` | F46 | rollback 后 Workpaper/AuditReport.is_stale=true |
| `test_finding_explanation.py` | F47 | 每种 finding code 生成的 explanation 字段齐全、公式手算对照 |
| `test_validation_rules_catalog.py` | F48 | catalog 与 validator.py 产生位置双向一致（所有 code 可查） |
| `test_finding_drill_down.py` | F49 | L3 finding 的 drill_down 字段完整 + sample_ids 可查询到真实行 |
| `test_workpaper_dataset_binding.py` | F50 | Workpaper 生成后 bound_dataset_id 非空 + 查询走该 dataset |
| `test_signed_report_rollback_protection.py` | F50 | 报表 final 后尝试 rollback → 409 + 报表数字不变 |
| `test_global_concurrency_limit.py` | F51 | 并发 10 job → 最多 3 running，其余 queued FIFO 启动 |
| `test_memory_downgrade.py` | F51 | 内存逼近 3GB → pipeline 降级到 openpyxl + 10k chunk |
| `test_column_mapping_history_reuse.py` | F52 | 第二次同 fingerprint → 自动应用历史 mapping |
| `test_retention_class_assignment.py` | F53 | final 报表绑定 → artifact 类别自动升级 archived |
| `test_purge_respects_bindings.py` | F53 | purge 不删 bound_dataset_id 被引用的 dataset |

### 4.3 E2E 脚本

| 脚本 | 用途 | 本 spec 验收 |
|------|------|-------------|
| `e2e_yg4001_smoke.py` | CI 必跑快速回归（<30s）| 通过 |
| `e2e_full_pipeline_validation.py` | 11 阶段 E2E（本地/部署前）| 全绿 |
| `b3_diag_yg2101.py` | 大样本性能诊断（5-10 分钟）| activate <1s, total <250s |
| `test_huge_ledger_smoke.py`（新增）| 超大档验证（500MB 合成 CSV）| total < 1800s，单 worker 峰值内存 < 2GB |

### 4.4 CI 卡点

**grep 卡点脚本**（`.github/workflows/ci.yml` 新增 step）：
```bash
if grep -rE "Tb(Balance|Ledger|AuxBalance|AuxLedger)\.is_deleted\s*==" backend/app/; then
  echo "❌ 禁止直接用 is_deleted 过滤四表，请用 get_active_filter"
  exit 1
fi
if grep -rE "FROM tb_(balance|ledger|aux_balance|aux_ledger).*is_deleted = false" backend/app/ | grep -v recycle_bin; then
  echo "❌ raw SQL 禁止用 is_deleted 过滤四表（回收站除外）"
  exit 1
fi
```

### 4.5 回归清单（UAT）

- [ ] `pytest backend/tests/` 全绿
- [ ] 3 个 E2E 脚本全通过
- [ ] 超大档 `test_huge_ledger_smoke.py` 通过（500MB / <30min / 内存 <2GB）
- [ ] 9 家样本识别率 100%（F6/F7/F8/F11 联合验收）
- [ ] 前端 UI 流程：上传 → detect → 列映射 → submit → 激活 → 查看余额树形 → rollback
- [ ] rollback 集成测试通过
- [ ] EXPLAIN ANALYZE：关键查询改造前后 < 1.2× 回归
- [ ] **cancel 手动验收**：上传 500MB → 中途 cancel → 30s 内停 + 磁盘/DB 零残留
- [ ] **checkpoint 手动验收**：模拟 activate 失败 → 前端出现"恢复导入"按钮 → 点击恢复后 1s 内完成
- [ ] **灰度手动验收**：flag=True 导入一次 / 切 flag=False 再导入一次 / 两次都成功
- [ ] **/metrics 端点验收**：生产环境 curl 返回 3 个核心指标且有合理数据
- [ ] **云协同手动验收**：A 浏览器激活 → B 浏览器 3s 内报表自动刷新
- [ ] **锁透明验收**：A 导入过程中 B 鼠标悬停禁用的"导入"按钮 → tooltip 显示 holder / 进度 / 预计剩余
- [ ] **接管验收**：A 中途断网 5min → B 点"接管导入"按钮 → job 续跑完成
- [ ] **rollback 互斥验收**：A 在 activate 的同时 B 点 rollback → B 收到"有操作进行中"错误
- [ ] **激活确认 UX**：点"激活"按钮 → 弹 ElMessageBox + 可填理由 → reason 进 DB 可查
- [ ] **错误友好化验收**：构造 L2_LEDGER_YEAR_OUT_OF_RANGE → 前端显示中文原因 + 修复建议
- [ ] **上传安全验收**：传 .exe 改名 xlsx → 拒绝 + audit_log 有记录
- [ ] **零行拦截 UAT**：上传空表 → 前端弹 warning → 必须点"强制继续"才能 submit
- [ ] **健康端点 UAT**：`curl /api/health/ledger-import` 返回合理 JSON
- [ ] **graceful shutdown UAT**：YG2101 跑到一半 `docker restart backend` → 30s 退 + job=interrupted + 重启后自动续跑
- [ ] **DLQ 告警 UAT**：断开前端 WS → activate 后 outbox event 3 次重试失败 → DLQ 有记录
- [ ] **rollback stale UAT**：激活 V2 → 生成底稿 → rollback → 打开底稿看到"数据已过时"横幅
- [ ] **校验过程透明化 UAT**：构造 1002 科目余额差异 → 前端点"展开过程"看到公式+代入值+差异分解
- [ ] **校验规则说明 UAT**：打开"校验规则说明"页面 → 能看到所有 L1/L2/L3 规则的公式+示例
- [ ] **差异下钻 UAT**：L3 差异 finding → 点"查看明细" → 抽屉显示该科目全部凭证 → 可排序可导出
- [ ] **签字报表保护 UAT**：final 报表对应 dataset 尝试 rollback → 前端弹"不允许：已有 1 份 final 报表绑定"
- [ ] **并发限流 UAT**：10 个项目同时上传 → 最多 3 个进度条转，其他 queued 排队
- [ ] **映射历史复用 UAT**：同客户第二次导入 → 映射步骤自动填充 + 绿色"上次映射"提示
- [ ] **留档合规 UAT**：导入 → 签字 final → 查 dataset → retention_class=archived 徽章可见

---

## 五、成功判据（全局汇总）

| 类别 | 指标 | 目标值 | 对应需求 |
|------|------|--------|---------|
| 性能 | YG2101 activate | < 1s | F1 |
| 性能 | YG2101 total | < 250s | F1 |
| 性能 | **超大档 500MB total** | **< 1800s (30min)** | **F1 + F14** |
| 性能 | 关键查询 EXPLAIN | < 1.2× 回归 | F2 |
| 性能 | 392MB CSV detect | < 5s | F10 |
| 性能 | **单 worker 峰值内存** | **< 2GB** | **F10 + 超大档** |
| 大文档 | **进度更新频率** | **每 5% 或 10k 行 ≥ 1 次** | **F13** |
| 大文档 | **cancel 清理** | **30s 内停 + 零残留** | **F15** |
| 大文档 | **checkpoint 可恢复** | **activate 失败后 1s resume** | **F14** |
| 大文档 | **耗时预估误差** | **±30% (L 档) / ±50% (S 档)** | **F17** |
| 治理 | 表膨胀率 | < 10% dead tuple | F1 + F3 |
| 治理 | superseded 清理 | 自动跑 | F3 |
| 治理 | 跨年度双 active | 集成测试通过 | F5 |
| 治理 | **索引大小** | **< 2× 表大小** | **F3 + 索引膨胀治理** |
| 识别 | 9 家识别率 | 97.8% → 100% | F6/F7/F8/F11 |
| 识别 | 辽宁卫生文件名识别 | 置信度 ≥ 60 | F6 |
| 识别 | 和平物流方括号表头 | 置信度 ≥ 85 | F7 |
| 识别 | YG36 有核算维度余额表分流 | 100% 正确 | F8 |
| 运维 | **`/metrics` 端点** | **3 个核心指标可采集** | **F16** |
| 运维 | **迁移剧本** | **Day 0/7/30 三阶段 runbook** | **F18** |
| 运维 | **灰度与回滚** | **feature flag 可单项目开关** | **F19** |
| 运维 | **恢复剧本** | **ADR-003 故障场景 runbook 可执行** | **F28** |
| 运维 | **事务隔离 ADR** | **ADR-004 归档** | **F29** |
| 云协同 | **激活广播** | **A 激活后 B 前端 3s 内自动刷新** | **F20** |
| 云协同 | **锁透明** | **非 holder 成员可见 holder / 进度 / 预估剩余** | **F21** |
| 云协同 | **导入接管** | **heartbeat 过期 5min 后可被接管** | **F22** |
| 云协同 | **rollback 互斥** | **rollback 和 activate 互斥** | **F23** |
| 云协同 | **只读旁观** | **项目组成员可读 job，写操作受限** | **F24** |
| 正确性 | **审计溯源** | **含 IP/耗时/reason 完整字段** | **F25** |
| 正确性 | **孤儿扫描** | **1h 内自动清理 staged 孤儿** | **F26** |
| 正确性 | **integrity check** | **metadata 切换前 COUNT 校验** | **F27** |
| UX | **激活意图确认** | **二次确认 + reason 可填** | **F31** |
| UX | **错误友好化** | **31 个错误码含 hint 映射** | **F32** |
| 安全 | **上传文件三重校验** | **MIME + 扩展名 + 魔数一致 + 大小限制** | **F40** |
| 安全 | **项目权限强校验** | **跨项目越权 100% 拦截** | **F41** |
| 安全 | **zip bomb 防护** | **压缩比 > 100× 拒绝** | **F40** |
| 数据质量 | **零行拦截** | **< 10 行触发 EMPTY_LEDGER_WARNING** | **F42** |
| 数据质量 | **异常规模告警** | **±5σ 触发 SUSPICIOUS_DATASET_SIZE** | **F42** |
| 健壮性 | **健康端点** | **degraded / unhealthy 可区分** | **F43** |
| 健壮性 | **graceful shutdown** | **SIGTERM 30s 内退出 + 自动续跑** | **F44** |
| 健壮性 | **事件广播可靠** | **3 次重试 + DLQ + 告警** | **F45** |
| 健壮性 | **rollback 下游失效** | **Workpaper/Report/Note stale** | **F46** |
| 校验 | **finding 附公式+代入** | **每条 L2/L3 finding explanation 字段齐全** | **F47** |
| 校验 | **规则说明文档** | **前端规则列表页可访问 + catalog 双向一致** | **F48** |
| 校验 | **差异下钻到凭证** | **3 次点击内定位差异源行** | **F49** |
| 合规 | **签字报表数据锁定** | **final 后 rollback 被拒 + 数字永不变** | **F50** |
| 合规 | **留档合规保留期** | **archived 类别 10 年保留 + legal_hold 永久** | **F53** |
| 稳定 | **全局并发限流** | **默认 3 并行 + FIFO 排队** | **F51** |
| 效率 | **列映射历史复用** | **同 fingerprint 自动应用节省 > 50% 时间** | **F52** |
| 代码 | grep `TbX.is_deleted ==` | 命中 = 0 | F2 + CI 卡点 |
| 代码 | `_set_dataset_visibility` 外部调用 | 命中 = 0 | F12 |
| 测试 | pytest 全绿 | 100% | §4.5 UAT |
| 测试 | E2E 三件套 + 超大档 | YG4001/YG36/YG2101/500MB 全通过 | §4.3 |
| 文档 | ADR-002 | 归档完成（含三阶段迁移时间表）| F18 |
| 文档 | CI grep 卡点 | 已激活 | §4.4 |

---

## 六、术语表

| 术语 | 定义 |
|------|------|
| **dataset** | `ledger_datasets` 表的一条记录，代表一次完整导入的产物（一个 project+year 组合） |
| **staged** | dataset 已写入 Tb* 表但未激活，业务查询看不到 |
| **active** | 当前生效版本，同 project+year 唯一 |
| **superseded** | 被新版本替代的旧 active，保留作 rollback 备选 |
| **rolled_back** | 用户手动回滚的 dataset |
| **B' 视图重构** | 本 spec 代号，指"可见性靠 metadata 切换而非行级 UPDATE" |
| **legacy data** | `dataset_id=NULL` 的老数据（B' 改造前遗留） |
| **partial index** | PG 只对满足 WHERE 条件的行建索引（如 `WHERE is_deleted=false`） |
| **purge** | 定期物理 DELETE 超过保留期的 superseded dataset |

---

## 附录 A：9 家样本结构归档

| 企业 | 文件布局 | 规模 | 关键挑战 | 对应需求 |
|------|---------|------|---------|---------|
| YG4001-30 宜宾大药房 | 1 xlsx / 2 sheet | 0.8MB / 4k 行 | 最简场景 smoke 基线 | R2 |
| YG36 四川物流 | 1 xlsx / 2 sheet（含维度）| 3.5MB / 24k 行 | 有核算维度余额表分流 | F8 |
| YG2101 四川医药 | 1 xlsx / 4 sheet（含空 Sheet1）| 148MB / 650k 行 | 巨文件 + 多 sheet unknown | F1 / F9 |
| 和平物流 | 1 xlsx / 方括号表头 | 14MB / 118k 行 | 非标软件格式 | F7 |
| 和平药房 | 余额 xlsx + 2 CSV 按日期段切 | ~440MB | 跨文件拼接 | O1（独立 Sprint）|
| 辽宁卫生 | 2 xlsx 分文件 | 80MB / 420k 行 | 文件名标识表类型 | F6 |
| 安徽骨科 | 1 xlsx / 2 sheet（含维度）| 58MB / 370k 行 | 单文件大数据 | F8 |
| 医疗器械 | 2 xlsx 分文件 | 40MB / 260k 行 | 文件名标识 | F6 |
| 陕西华氏 | 1 余额 + 12 月度序时账 × 2 年度 | 500MB+ | 多文件 + 跨年度 | F5 + O1 |

**软件来源**：至少 3 种（用友 NC / 金蝶 KIS / 某方括号格式），同一客户同年度可能混用。
