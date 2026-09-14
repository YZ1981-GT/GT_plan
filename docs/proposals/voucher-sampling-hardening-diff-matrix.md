# 抽凭引擎收敛差异矩阵（voucher-sampling-hardening Task 15）

本文档记录抽凭引擎第二/三批改造的各原实现 → canonical 映射、语义差异与保留决策，
作为等价迁移的凭据与防止未来再次漂移的参考。

_Validates: Requirements 12.6_

## 一、抽样框（Task 3）

| 维度 | 改造前 | canonical（改造后） | 决策 |
|------|--------|--------------------|------|
| 抽样框 | `execute_sampling(population=items[:10000])` 仅前 1 万条 | 总体 ≤ 上限走内存路径（逐字节等价）；> 上限两阶段全量框（locate_sampling_units 全量最小投影 → 同 seed execute_sampling → fetch_by_unit_ids 取回） | 内存路径零回归保留；仅超上限启用全量框，消除随机/分层/系统/MUS 选择偏差 |
| 高值必选 | 仅前 1 万条内识别 | 全量投影识别，100% 纳入 | — |
| 残留上限 | 静默截断 | `frame_capped` + `_SAMPLING_FRAME_MAX_UNITS` 如实透明 | — |

## 二、总体完整性核对（Task 4）

| 维度 | 改造前 | canonical | 决策 |
|------|--------|-----------|------|
| 账面来源 | `book_amount = 序时账全量金额`（自身比对，恒"一致"假绿） | `_resolve_independent_book_amount`（trial_balance 审定，独立于序时账）；取不到 → `book_amount=null` + `reconcile_available=false` | 消除自身比对；无独立源显式"未执行核对"；手工录入优先 |

## 三、抽样单位（Task 5）

| 维度 | 改造前 | canonical | 决策 |
|------|--------|-----------|------|
| 单位 | 隐式分录行 | `sampling_unit: ledger_line`（默认，零回归）/ `voucher`（按凭证号聚合、抽中带出完整分录） | 默认 ledger_line 保持现状；voucher 单位两阶段与内存路径口径一致 |

## 四、方法学单一真源（Task 9）

| 维度 | 改造前 | canonical | 决策 |
|------|--------|-----------|------|
| MUS 间隔 | 前端 `computeMusInterval`（CAS1314 可容忍/可信赖度）与后端 `_derive_sampling_interval`（总体/mus_sample_size）**两套公式漂移** | 后端 `sampling_methodology.py`（Python 精确移植 CAS1314）为权威；前端消费后端 `methodology` 快照，本地计算降级为即时预览 | 后端单一真源 + `ALGO_VERSION` 留痕；缺参回退 _derive |

## 五、关键词转义（Task 6）

| 维度 | 改造前 | canonical | 决策 |
|------|--------|-----------|------|
| `summary_keyword` | `ilike(f"%{kw}%")` 不转义（`%`/`_`/`\` 当通配） | `_escape_like_pattern` + `ilike(escape='\\')` | 字面量匹配；普通文本行为不变 |

## 六、批次治理（Task 7）

| 维度 | 改造前 | canonical | 决策 |
|------|--------|-----------|------|
| `WorkpaperExtractionLog` | 无 batch_id/幂等键/乐观锁/撤销唯一/枚举 CHECK/user FK | V123 补齐 + `sampling_batch_service` 状态机（draft→confirmed→filled→undone） | 迁移幂等 + NOT VALID（仅约束未来）+ 历史行兼容；DB 约束 apply 后强制 |

## 七、抽样 API / 算法收敛（Task 10）— 🔴 关键发现：语义分叉，全量收敛需 stakeholder 决策

实测两套抽样实现服务**不同功能、不同契约、不同审计语义**：

| 项 | `voucher_sampling_algorithms.execute_sampling`（canonical） | `WpSamplingEngine`（`sampling/execute`） |
|----|--------------------------|------------------|
| 消费方 | `voucher-extract`（D0 抽凭底稿引擎 GtVoucherSamplingEngine） | `wp_functional_actions` 通用操作台 + `sampling_enhanced.py` |
| 响应形状 | `{items, stats, methodology, seed_used}` | `{method, total_population, sample_size, entries}` |
| 回填目标 | checklist_responses（抽凭表） | `parsed_data.action_data.entries` |
| 数值 | Decimal + 随机种子（可复现） | float + 无种子（不可复现） |
| 方法命名 | random/stratified/specific_item/systematic/mus | random/stratified/top_n/mus |
| **分层算法** | 显式 `StratumConfig`（用户配置边界/每层样本量） | **自动 3 层**（max×0.33/0.66 分界 + 权重 0.2/0.3/0.5） |
| **MUS 算法** | interval = 总体/sample_size，Decimal 累积 | interval 由调用方传入，float 累积 |

**决策**：
- **canonical = `voucher_sampling_algorithms.execute_sampling`**（Decimal + seed + 全量框），D0 抽凭底稿路径已全部使用。
- **不强行合并** `WpSamplingEngine`：其 stratified（自动 3 层）与 mus（interval 语义）与 canonical **审计语义实质不同**，强制委托会改变 wp-functional-actions 通用操作台的抽样结果（违反零回归 Req12，且涉及审计正确性判断）。
- **`top_n` ≡ `specific_item`**、`random` 长度语义等价——可委托，但 stratified/mus 分叉使**整体委托不安全**。
- **收敛路径（后续，需 stakeholder 定分层/MUS 权威语义）**：迁移 wp-functional-actions 调用方到 canonical 契约后再废弃 `WpSamplingEngine`；在此之前二者并存，各自 characterization 测试（Task 1）锁定行为防漂移。
- Task 1 characterization 已锁定 `WpSamplingEngine` 当前确定性方法（top_n/长度界）作为未来收敛的安全网。

**结论**：Task 10 的"算法单一真源"在 D0 抽凭路径已达成（canonical 唯一）；跨功能全量端点合并因审计语义分叉暂缓，作为 spec 明示的 stakeholder 决策项（不假绿、不强改另一功能行为）。
