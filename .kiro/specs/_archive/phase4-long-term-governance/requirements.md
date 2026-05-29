# Requirements Document — Phase 4 长期治理

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始起草，基于《平台全局建议书》Phase 4 五项 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| Phase 1~3 specs | 前置 | 🔲 需先完成 |
| PostgreSQL 16 (RLS 支持) | 数据库 | ✅ 已有 |
| migration_runner.py | 后端 | ✅ 已有 |
| Redis 7 | 缓存 | ✅ 已有（单实例） |
| displayPrefs store | 前端 | ✅ 已有 |
| ReportView.vue | 前端 | ✅ 已有 |

---

## 一、为什么做（业务痛点）

### 1.1 数据隔离依赖应用层（SC-5）
- **痛点**：跨项目数据隔离完全依赖应用层 `require_project_access`，一旦代码漏洞或新端点遗漏权限检查，可能泄露其他项目数据
- **影响**：数据安全（审计项目数据高度敏感）
- **技术根因**：无数据库级别行级安全（RLS），所有查询依赖 WHERE project_id = X 条件

### 1.2 多年度对比分析缺失（Y-3）
- **痛点**：合伙人无法在同一视图对比 3 年数据趋势，需手动切换年度逐个查看
- **影响角色**：合伙人（趋势判断）、质控（异常识别）
- **技术根因**：报表视图仅支持单年度显示，无多年度并列模式

### 1.3 EQCR 快照机制缺失（E-1）
- **痛点**：EQCR 独立复核合伙人看到的是实时数据，项目团队可能在 EQCR 复核期间修改底稿
- **影响角色**：EQCR 合伙人（独立性受损）
- **技术根因**：无"提交 EQCR 复核时冻结版本"机制

### 1.4 数据库迁移无回滚（MT-7）
- **痛点**：migration_runner.py 仅支持前进执行 V*.sql，无法回滚错误迁移
- **影响**：运维安全（生产环境迁移失败时无法快速恢复）
- **技术根因**：无 R*.sql 回滚脚本配套机制

### 1.5 Redis 单点风险（PF-4）
- **痛点**：Redis 6379 单实例宕机影响认证+权限缓存+编辑锁+SSE
- **影响**：系统可用性（6000 并发目标下单点是致命风险）
- **技术根因**：未部署 Redis Sentinel 或 Cluster

---

## 二、范围边界

### 必做（In Scope）

**F1 PG RLS 行级安全：**
- 关键表启用 RLS：working_papers / adjustments / tb_balance / reports / review_comments
- RLS 策略：基于 session 变量 `current_project_id`（由应用层在每次请求开始时 SET）
- 保留应用层权限检查（RLS 是第二道防线，非替代）
- 提供 bypass 机制（admin 角色 / 跨项目聚合查询）
- 迁移脚本 + 回滚脚本

**F2 多年度对比分析：**
- ReportView 新增"多年度对比"模式（最多 5 年并列）
- 对比维度：资产负债表 / 利润表 / 现金流量表
- 显示：各年度金额 + 同比变动率 + 变动趋势箭头
- 后端 API：一次查询多年度数据（避免前端多次请求）
- 导出：支持多年度对比表 Excel 导出

**F3 EQCR 快照机制：**
- 提交 EQCR 复核时创建项目快照（底稿状态+报表数据+调整分录）
- EQCR 工作台仅展示快照数据（非实时数据）
- 快照不可修改（只读）
- 项目团队修改后，EQCR 可选择"刷新快照"查看最新版本
- 快照存储：独立表 `eqcr_snapshots`（JSON 格式存储关键数据）

**F4 数据库迁移回滚机制：**
- 每个 V*.sql 配套 R*.sql 回滚脚本
- migration_runner.py 新增 `--rollback` 参数（回滚到指定版本）
- 回滚前自动备份当前状态
- 回滚日志记录（谁在什么时候回滚了什么）
- 生产环境回滚需二次确认

**F5 Redis 高可用：**
- 部署 Redis Sentinel（1 master + 2 replica + 3 sentinel）
- 应用层改用 Sentinel 连接（自动故障转移）
- 降级策略：Redis 全部不可用时，关键功能（认证/保存）不阻断
- 监控：Redis 健康检查 + 故障转移告警

### 排除（Out of Scope）

- 不涉及全表 RLS（仅 5 张关键表）
- 不涉及 EQCR 快照的增量更新（全量快照）
- 不涉及 Redis Cluster（Sentinel 足够当前规模）
- 不涉及跨数据中心部署

---

## 三、功能需求（EARS 范式）

### F1 PG RLS

- **F1.1** THE 系统 SHALL 在 working_paper / adjustments / tb_balance / reports / review_records 表启用 RLS
- **F1.2** THE RLS 策略 SHALL 基于 session 变量 `app.current_project_id` 过滤行
- **F1.3** THE 应用层 SHALL 在每次数据库请求开始时执行 `SET LOCAL app.current_project_id = '{project_id}'`
- **F1.4** IF 用户角色为 admin 或查询为跨项目聚合，THE 系统 SHALL bypass RLS（使用 SECURITY DEFINER 函数）
- **F1.5** THE RLS 启用后 SHALL 不影响现有 API 的正确性（所有现有测试通过）

### F2 多年度对比

- **F2.1** WHEN 用户在 ReportView 切换到"多年度对比"模式，THE 系统 SHALL 并列显示最多 5 年数据
- **F2.2** THE 对比表 SHALL 显示：年度列标题 + 各年金额 + 同比变动率(%) + 趋势箭头(↑↓→)
- **F2.3** IF 某年度无数据，THE 系统 SHALL 显示 "-"（不报错）
- **F2.4** THE 用户 SHALL 可选择对比年度范围（如 2023~2025）
- **F2.5** THE 系统 SHALL 支持多年度对比表 Excel 导出

### F3 EQCR 快照

- **F3.1** WHEN 项目经理提交 EQCR 复核时，THE 系统 SHALL 创建项目快照
- **F3.2** THE 快照 SHALL 包含：所有底稿状态 + 报表数据 + 调整分录 + VR 检查结果
- **F3.3** THE EQCR 工作台 SHALL 仅展示快照数据（非实时数据）
- **F3.4** WHEN EQCR 合伙人点击"刷新快照"，THE 系统 SHALL 创建新快照并替换旧快照
- **F3.5** THE 快照 SHALL 不可被项目团队修改（只读）

### F4 迁移回滚

- **F4.1** THE 每个 V*.sql 迁移脚本 SHALL 配套 R*.sql 回滚脚本
- **F4.2** WHEN 运维人员执行 `migration_runner.py --rollback V003`，THE 系统 SHALL 按逆序执行 R004→R003 回滚
- **F4.3** THE 回滚前 SHALL 自动执行 `pg_dump` 备份当前数据库
- **F4.4** THE 回滚操作 SHALL 记录到 schema_version 表（谁/何时/回滚到哪个版本）

### F5 Redis 高可用

- **F5.1** THE 系统 SHALL 支持 Redis Sentinel 连接模式
- **F5.2** WHEN Redis master 宕机，THE Sentinel SHALL 在 30s 内完成故障转移
- **F5.3** THE 应用层 SHALL 在 Redis 全部不可用时降级运行（认证走 DB / 锁跳过 / 缓存穿透）
- **F5.4** THE 系统 SHALL 提供 Redis 健康检查端点（`/api/health/redis`）

---

## 四、非功能需求

| 维度 | 要求 |
|------|------|
| 性能 | F1 RLS 不增加查询延迟 > 5ms；F2 多年度查询 ≤ 2s |
| 安全 | F1 RLS 通过渗透测试（跨项目数据不可访问）|
| 可用性 | F5 Redis 故障转移 ≤ 30s；降级模式下核心功能可用 |
| 可回滚 | F4 回滚操作 ≤ 5min（含备份） |

---

## 五、成功判据

| 指标 | 目标 |
|------|------|
| F1 RLS 覆盖表数 | 5 张关键表 |
| F2 对比年度数 | 最多 5 年并列 |
| F3 快照完整性 | 包含底稿+报表+AJE+VR 四类数据 |
| F4 回滚脚本覆盖 | 所有 V*.sql 均有配套 R*.sql |
| F5 故障转移时间 | ≤ 30s |
| 现有测试回归 | 零新增失败 |
