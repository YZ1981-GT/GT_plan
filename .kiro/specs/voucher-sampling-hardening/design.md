# Design Document

## Overview

本设计将抽凭引擎的第二 / 三批改造落地为**分层、可分步、可回退**的行为保持式重构。总体策略：先建 characterization 安全网锁定既有行为，再逐项收敛，每步保持既有测试全绿。改造分四条独立轴：

- **抽样正确性轴**（Req1/2/3/4/10/11）：全量抽样框、独立总体核对、抽样单位、原子回填、方法学正确性、关键词转义。
- **数据治理轴**（Req5/9）：抽样批次状态机 + 完整性约束 + 真实操作者（迁移 `V{n}`）。
- **架构收敛轴**（Req6/7）：后端方法学单一真源、`voucher-extract` / `sampling-execute` 收敛。
- **安全轴**（Req8）：服务端授权校验。

四轴互不阻塞，可并行推进但各自内部有序。可选轴（Req13/14）末位。

### 现状锚点（本仓实测，改造起点）

| 组件 | 现状 | 目标 |
|------|------|------|
| `voucher_sampling.py::voucher_extract` | `execute_with_stats(max_total=10000)` 取 items → `execute_sampling(population=items)` 仅从前 1 万条抽 | 全量抽样框（Req1） |
| `LedgerSamplingService.execute_with_stats` | 已返回全量 `StatsResult`（含 `amount_total`），P0 已修统计口径 | 复用；新增全量单位标识取回（Req1） |
| `voucher_extract` 返回 `book_amount` | = 序时账全量金额（自身比对） | 独立数据源（Req2） |
| `LedgerQueryFilters` | 已有 `amount_max` / `months`（P0 新增）；`summary_keyword` 用 `ilike(f"%{kw}%")` 不转义 | LIKE 元字符转义（Req11） |
| `WorkpaperExtractionLog` | 有 project/wp FK + 非空 + 索引；无 `batch_id`/幂等键/乐观版本/撤销唯一约束/枚举 CHECK；`user_id` 无 FK | 状态机 + 约束（Req5） |
| `useVoucherSampling` / 后端 | 间隔 / 高值前后端双算 | 后端单一真源（Req6） |
| `voucher-extract` vs `sampling-execute`(`WpSamplingEngine`) | 两套端点 + 两套算法 | 收敛 canonical（Req7） |
| `voucher_extract` | 无 wp 归属 / 年度 / 编辑权校验 | 服务端授权（Req8） |
| `recordActualMisstatement` / `updateField` / `batchMarkChecked` | `userId: 'current_user'` 硬编码 | 真实 actor（Req9） |
| `useSamplingAlgorithms` 核心纯函数 | 经集成层间接测试，无直接权威向量 PBT | 直接 PBT + 固定向量（Req10） |

## Architecture

### 决策 1：全量抽样框——两阶段"标识抽样 + 按标识取回"（Req1）

**问题**：`execute_sampling` 在内存中对 `items`（≤10000）抽样。总体 >10000 时超出部分永不可抽 → 随机 / 分层 / 系统 / MUS 选择偏差；高值必选也仅在前 1 万条内识别。

**方案**（不引入数据库扩展，复用现有查询）：将抽样拆为两阶段——
1. **阶段 A（全量定位）**：对满足过滤的**全部**总体，用轻量投影查询（只取 `id, voucher_no, voucher_date, greatest_amount`）拉取抽样所需的最小字段全集（远小于完整行，规避 `max_total` 限制的是"完整行内存"而非"标识内存"）；或对 MUS / 系统抽样用 DB 层累计和 / 行号定位命中单位。
2. **阶段 B（按标识取回）**：对阶段 A 命中的抽样单位标识集合，按 `id`（或 `voucher_no`，视抽样单位）取回完整样本行。

**高值必选**（Req1.3）：在阶段 A 的全量投影上用 `greatest_amount >= interval` 识别，100% 纳入，独立于任何 `max_total`。

**零回归护栏**（Req1.4）：当 `total_count <= 内存上限` 时，走**现状内存路径**（`execute_sampling(population=items)` 原样），保证相同种子 / 参数 / 总体下样本逐字节等价。仅当 `total_count > 上限` 时启用两阶段路径。

**可复现**（Req1.6/6）：两阶段路径的随机 / 系统 / MUS 选择在阶段 A 用与内存算法**同一 seed 派生序列**，确保同种子可复现。

**残留上限透明**（Req1.5）：若阶段 A 的标识全集本身仍受某上限约束（极端超大总体），显式返回该限制标志，前端如实提示，不得声称覆盖全总体。

### 决策 2：独立总体完整性数据源（Req2）

`voucher_extract` 新增可选入参 `reconcile_source`（或后端按 account_codes 自动解析）：
- 资产负债表类科目 → 查 `trial_balance` 审定数 / 期末余额（复用 `get_active_filter`）。
- 损益类科目 → 权威发生额（`tb_ledger` 汇总或 `trial_balance`）。
- 无法解析 → 返回 `book_amount=null` + `reconcile_available=false`。

前端 `populationReconcile`：`reconcile_available=false` 时显示"未执行总体完整性核对"，不以序时账总体自身产生"一致"。审计师手工录入优先（保留手工来源标记）。

**注**：本 spec 提供后端独立来源 hook 与前端消费；具体科目 → 数据源映射的完备性以"能取到即用、取不到显式声明未核对"为准，不臆造映射。

### 决策 3：抽样单位显式化（Req3）

`SamplingConfig` 新增 `samplingUnit: 'ledger_line' | 'voucher'`（默认 `ledger_line`，零回归）。后端 `voucher-extract` 接收 `sampling_unit`：
- `ledger_line`：现状行为。
- `voucher`：总体聚合按 `voucher_no` GROUP BY（金额取凭证内 `greatest` 聚合），抽中一张凭证时取回其全部分录行；`exclude_voucher_nos` / `filled_voucher_nos` / 历史比较键与单位一致。

覆盖率与 MUS 间隔分母按所选单位口径（Req3.5）。

### 决策 4：回填与日志原子化（Req4）

现状：前端 `confirmFill` 先 fire-and-forget 版本快照 → POST 日志；底稿数据变更由父组件 emit `filled` 后另行保存。原子性缺口在于"底稿保存"与"日志写入"是两次独立请求。

**方案**：后端提供单一原子端点（或在现有 `cutoff-fill` 日志端点基础上），在同一 DB 事务内完成"日志写入"；底稿数据的持久化仍由各底稿 `saveImmediate`/`saveBatch` 负责，但设计上保证**日志写入失败时前端不提交底稿回填**（前端先 await 日志成功再 emit `filled`；已是现状顺序，本 spec 强化为：日志失败 → 不 emit → 底稿不变，并给出明确失败提示与可重试）。before_data / filled_voucher_nos 保持 P0 修复。

**边界**：真正的跨表 2PC 不做；以"日志成功是回填 emit 的前置条件"实现实用原子性（日志是可撤销真源，底稿回填以日志为准可追溯）。

### 决策 5：抽样批次状态机与约束（Req5，迁移 `V{n}`）

`WorkpaperExtractionLog` 扩展（迁移，幂等 + 向后兼容）：
- 新增列：`batch_id UUID`、`idempotency_key TEXT`、`row_version INT DEFAULT 1`、`status TEXT`（draft/confirmed/filled/undone）。
- 约束：`CHECK (fill_mode IN ('append','replace','merge'))`、`CHECK (extraction_type IN ('cutoff','voucher_sampling'))`、`CHECK (status IN ('draft','confirmed','filled','undone'))`。
- 撤销唯一性：部分唯一索引 `UNIQUE (batch_id) WHERE status='undone'`（同批次至多一条 undone），或等价触发器。
- `user_id` → `users(id)` FK（若现表无 FK）。
- 幂等：`UNIQUE (workpaper_id, idempotency_key)`。
- 历史行兼容：新列 nullable / 带默认；读取路径对 `batch_id IS NULL` 的历史行不报错（Req5.6）。

状态转移在服务层校验（filled/undone 为终态，不可非法回退）。乐观锁用 `row_version` CAS 更新。

**迁移安全铁律**：`IF NOT EXISTS` / information_schema 守护；同号冲突检查（查 `migration_status` 取下一可用 `V` 号）；`ADD VALUE IF NOT EXISTS`（若用 enum）。

### 决策 6：后端方法学单一真源（Req6）

后端 `voucher-extract` 已返回 `sampling_interval` / `high_value`。强化为完整**方法学快照**：`{interval, high_value_flags, suggested_sample_size, reliability_factor, algo_version}`。前端 `useVoucherSampling` 的 `markHighValueItems` / `computeSuggestedSampleSize` 保留为**即时预览**（配置弹窗内），但抽样执行后以后端返回值覆盖展示；`confirmFill` 回填的 methodology 以后端快照为准并记 `algo_version`（Req6.3）。契约测试断言前后端同输入结果一致（Req6.4 / Req10.8）。

### 决策 7：抽样 API 收敛（Req7）

以 `voucher-extract`（`voucher_sampling_algorithms.execute_sampling`）为 canonical。`sampling-execute`（`WpSamplingEngine`）：
1. 先补 characterization 测试锁定其当前行为与调用方。
2. 将其重写为对 `execute_sampling` 的**薄委托**（同签名 / 同响应形状），或在调用方全部迁移后按序废弃路由。
3. 两套算法实现收敛为 `voucher_sampling_algorithms` 单一真源，删除 `WpSamplingEngine` 内重复算法。

**不触碰** `cutoff-extract` / `cutoff-test`（截止 spec 负责）。

### 决策 8：服务端授权校验（Req8）

`voucher_extract` 端点入口新增校验（复用平台既有 wp 可见性 / 编辑权服务）：
- `workpaper_id` 属于 `pid`（查 `working_paper.project_id == pid`）。
- `year` ∈ 项目审计期（查 `projects.audit_year` 或审计期范围）。
- 当前用户对该 wp 有编辑权（复用 `wp_visibility` / 权限矩阵服务）。
失败返回明确授权错误（403 / 400），不依赖前端隐藏按钮。

### 决策 9：真实操作者（Req9）

后端在 `cutoff-fill` / 日志写入时以 `current_user.id` 记 actor。前端 `updateField` / `batchMarkChecked` / `recordActualMisstatement` 的 `editTrail` `userId` 改为由注入的当前用户上下文提供（或前端仅记本地占位、以后端 actor 为权威）。方案：edit_trail 的可信 actor 由后端在持久化时补全 / 覆盖，前端本地值仅作乐观展示。

### 决策 10：关键词 LIKE 转义（Req11）

`build_ledger_query` 的 `summary_keyword` 分支：预转义 `\` → `\\`、`%` → `\%`、`_` → `\_`，并用 `ilike(pattern, escape='\\')`（SQLAlchemy `.ilike(..., escape='\\')`）。普通文本行为不变（Req11.2）。截止 spec 共享此查询构建器 → 收益共享，须保持其测试全绿（Req11.3）。

## Components and Interfaces

### 后端

- **`LedgerSamplingService`（共享，抽凭/截止共用）**
  - `build_ledger_query(...)`：新增 `summary_keyword` LIKE 元字符转义（`.ilike(pattern, escape='\\')`）。保留 `amount_max`/`months`（P0）。
  - 新增 `locate_sampling_units(query, unit, ...)`：阶段 A 全量定位——返回抽样单位标识 + `greatest_amount` 最小投影（供全量框与高值识别），不受 `max_total` 完整行限制。
  - 新增 `fetch_by_unit_ids(ids, unit)`：阶段 B 按标识取回完整样本行。
  - `execute_with_stats`：保持现状全量 `StatsResult`（P0 已修）。
- **`voucher_sampling.py::voucher_extract`（canonical 抽凭端点）**
  - 入口新增授权校验（wp 归属 / 年度 / 编辑权）。
  - 抽样路径分流：`total_count ≤ 上限` → 现状内存路径（零回归）；`> 上限` → 两阶段全量框路径。
  - 入参新增 `sampling_unit`（默认 ledger_line）；`reconcile_source` 解析独立账面。
  - 返回：完整方法学快照（interval/high_value/suggested/reliability/algo_version）+ `book_amount`（独立源，取不到为 null + `reconcile_available=false`）+ `truncated`/残留上限标志。
  - 日志写入（`cutoff-fill` 或新原子端点）：同事务写 `batch_id`/`idempotency_key`/`status`/`row_version`/真实 `user_id`。
- **`voucher_sampling_algorithms`（canonical 算法真源）**：吸收 `WpSamplingEngine` 重复算法；`WpSamplingEngine`/`sampling-execute` 改薄委托或废弃。
- **`WorkpaperExtractionLog` ORM + 迁移 `V{n}`**：新列 + CHECK + FK + 唯一索引（见 Data Models）。

### 前端

- **`useSamplingAlgorithms.ts`（纯函数真源）**：`computeMusInterval`/`computeSampleSize`/`projectMisstatement`/`computeUpperMisstatementLimit`/`deriveSamplingConclusion`/`markHighValueItems` 保留即时预览；新增直接权威向量 + PBT 测试。
- **`useVoucherSampling.ts`**：`config` 加 `samplingUnit`；抽样后以后端方法学快照覆盖展示；`confirmFill` 记 `algo_version` + 日志失败不 emit；edit_trail actor 由注入用户上下文（后端权威覆盖）；保留 `filled_voucher_nos`/未检查过滤（P0）。
- **`GtVoucherSamplingEngine.vue`**：总体完整性区消费 `reconcile_available`（false → "未执行核对"）；抽样单位选择器；残留上限如实提示；保留结论确认门禁/existingSamples（P0）。

### 契约与守卫

- 前后端方法学一致性契约测试（P13）。
- 绕过 canonical 抽样端点的调用扫描 / 测试（防回退多轨）。

## Data Models

### SamplingConfig（前端，附加字段）

```
samplingUnit?: 'ledger_line' | 'voucher'   // 默认 ledger_line
```

### 方法学快照（后端返回 → 前端消费 → 回填留痕）

```
methodology = {
  sampling_method, sampling_interval, high_value_count,
  suggested_sample_size, reliability_factor, confidence_level,
  tolerable_misstatement, expected_misstatement, algo_version
}
```

### WorkpaperExtractionLog（迁移后）

```
+ batch_id: UUID (nullable, 历史行为 NULL)
+ idempotency_key: TEXT (nullable)
+ row_version: INT DEFAULT 1
+ status: TEXT DEFAULT 'filled'  CHECK in (draft,confirmed,filled,undone)
  CHECK fill_mode in (append,replace,merge)
  CHECK extraction_type in (cutoff,voucher_sampling)
  FK user_id -> users(id)
  UNIQUE (workpaper_id, idempotency_key)
  UNIQUE (batch_id) WHERE status='undone'
```

## Correctness Properties

以下属性用于 PBT / 契约测试，逐条映射需求。

Property 1: 全量可抽性 — 对任意总体规模 N，全量抽样框实现下总体中每个抽样单位被选中的概率 > 0（不存在因排序截断而恒不可抽的单位）。
**Validates: Requirements 1.1, 1.2**

Property 2: 内存路径零回归 — 当 N ≤ 内存上限时，两阶段实现的样本集合与现状 `execute_sampling(population=items)` 在相同 seed / 参数下逐元素相等。
**Validates: Requirements 1.4**

Property 3: 高值全量必选 — 金额 ≥ interval 的单位在任意 N 下 100% 纳入样本。
**Validates: Requirements 1.3, 10.5**

Property 4: 种子可复现 — 同 seed + 同总体 + 同参数 → 同样本（两阶段与内存路径各自幂等）。
**Validates: Requirements 1.6, 10.6**

Property 5: 独立核对真源 — `reconcile_available=false` 时不产生"一致"结论；`book_amount` 不等于抽样总体自身（除非独立源恰好等值且被显式标记为独立源）。
**Validates: Requirements 2.1, 2.2**

Property 6: 抽样单位一致键 — `voucher` 单位下排除 / 排重 / 比较键均为 `voucher_no`；`ledger_line` 单位下为行标识；跨科目不误排除。
**Validates: Requirements 3.3**

Property 7: 覆盖率单位一致 — 覆盖率与 MUS 间隔分母口径与所选 `samplingUnit` 一致。
**Validates: Requirements 3.5**

Property 8: 原子回填 — 日志写入失败 → 底稿不进入已回填状态（无孤儿回填）。
**Validates: Requirements 4.1, 4.2**

Property 9: 幂等批次 — 相同 `idempotency_key` 重复提交 → 日志行数不增。
**Validates: Requirements 5.1**

Property 10: 状态转移合法性 — 状态机不允许从 filled/undone 非法回退；非法转移被拒绝。
**Validates: Requirements 5.2**

Property 11: 撤销唯一性 — 同一 `batch_id` 至多一条 `status='undone'`；重复撤销被约束拒绝。
**Validates: Requirements 5.3**

Property 12: 枚举约束 — 非法 `fill_mode`/`extraction_type`/`status` 写入被 CHECK 拒绝。
**Validates: Requirements 5.4**

Property 13: 方法学单一真源 — 前后端对同一输入的 interval / 高值识别 / 建议样本量结果一致。
**Validates: Requirements 6.2, 6.4, 10.8**

Property 14: API 收敛等价 — 收敛后 `voucher-extract` 对既有调用方输入产生与迁移前等价的样本与统计；`sampling-execute` 薄委托响应形状不变。
**Validates: Requirements 7.4**

Property 15: 授权拒绝 — 跨项目 wp / 非审计期年度 / 无编辑权 → 端点拒绝。
**Validates: Requirements 8.1, 8.2, 8.3**

Property 16: 真实 actor — 持久化的 edit_trail / 错报记录 actor 不为 `current_user` 占位符。
**Validates: Requirements 9.1**

Property 17: UML 单调不降 — 错报增加 → UML 不下降。
**Validates: Requirements 10.2**

Property 18: 样本量单调不增 — 可容忍错报增加 → 建议样本量不增加。
**Validates: Requirements 10.3**

Property 19: UML 下界 — 恒有 UML ≥ 推断错报 ≥ 0。
**Validates: Requirements 10.4**

Property 20: 未检查不参与推断 — 未检查样本不按零错报计入推断（保持 P0）。
**Validates: Requirements 10.7**

Property 21: LIKE 字面量匹配 — 含 `%`/`_`/`\` 的关键词按字面量匹配，不作通配。
**Validates: Requirements 11.1**

Property 22: 权威向量 — `computeMusInterval`/`computeSampleSize`/`projectMisstatement`/`computeUpperMisstatementLimit`/`deriveSamplingConclusion` 对固定已知输入产出固定已知输出。
**Validates: Requirements 10.1**

## Testing Strategy

- **Characterization 先行**（Req12.5）：为 `WpSamplingEngine`(`sampling-execute`)、前端方法学双算路径、`WorkpaperExtractionLog` 现有读写补 characterization 测试锁定当前行为，再改造。
- **PBT**：P1-P4 / P9-P14 / P17-P22 用 Hypothesis（后端）/ fast-check（前端），遵循 `fast` profile（`max_examples` 收敛）。金额一律 Decimal 字符串。
- **权威向量**：P22 用手算 CAS 1314 泊松表固定用例。
- **迁移测试**：V{n} 幂等重放 + 历史行兼容 + 约束拒绝（P9-P12）+ rollback。
- **零回归门**（Req12.1）：每波结束跑既有 `test_voucher_sampling_integration` + `test_cutoff_sampling_pbt`/`integration` + 前端 `useVoucherSampling.spec`/`useSamplingAlgorithms.spec` 必须全绿。
- **契约守卫**（Req8 of 截止 spec 精神）：新增绕过 canonical 抽样端点的调用可被扫描 / 测试检测。
- **Playwright**（关键路径）：全量框大总体抽样、独立核对显示、批次幂等 / 撤销、授权拒绝，在实例化项目上实测（需 >10000 行总体的测试项目）。

## Error Handling

- 全量框阶段 A 查询失败 → 回退内存路径并记录（不静默返回偏差样本）。
- 独立数据源取数失败 → `reconcile_available=false` + 允许手工（不阻断）。
- 日志写入失败 → 前端不 emit filled + 明确提示 + 可重试（Req4.2）。
- 授权失败 → 明确 403/400（Req8.4）。
- 迁移在无 pgvector / 无目标表等环境 → 幂等守护 graceful（不崩启动）。

## Migration Plan

- 新增迁移 `V{n}__voucher_sampling_batch_governance.sql`（取号前查 `migration_status`）：扩展 `WorkpaperExtractionLog` + 约束 + FK + 索引，全部 `IF NOT EXISTS` / information_schema 守护 + rollback `R{n}`。ORM `WorkpaperExtractionLog` 同步新列，`SchemaDriftDetector.scan()` drift=0。
