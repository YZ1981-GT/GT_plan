# Requirements Document

## Introduction

系统隐含"单 worker"假设——导入并发控制（进程内 dict + asyncio.Lock）、地址坐标库缓存（进程内 slot + 无 single-flight）、OCR 引擎（per-process ~500MB）在多 uvicorn worker 部署下全部失效或资源浪费。本 spec 将这些关键进程内状态外置到 PG/Redis，使系统在 6000 并发目标下可水平扩展。

覆盖条目：§7.1/§3.7/§3.12/§18.1。

## Glossary

- **single-flight**：同一 key 并发 miss 时仅触发一次重建，其余等待复用结果的模式
- **SET NX EX**：Redis 原子命令，key 不存在时设值并设过期时间（分布式锁原语）

**前置条件**：所有改动需**先压测确认瓶颈量级**再投入实施（标注为"推断需压测"的条目）。

## Requirements

### Requirement 1: 账表导入分布式并发控制（§7.1）

**User Story:** As a 运维, I want 多 worker 部署时导入并发控制仍有效, so that 同项目不会被并发双写。

#### Acceptance Criteria

1. WHEN 多 worker 部署时同一项目同时发起导入 THEN 仅第一个获取锁成功，后续返回"正在导入"
2. WHEN 导入完成/失败 THEN 锁自动释放，其他 worker 可发起新导入
3. WHEN 取消信号发出 THEN 不论请求落到哪个 worker，执行中的导入都能收到取消指令
4. WHEN Redis 不可用 THEN 降级为 DB 行锁（PG advisory lock 兜底），不完全失效

### Requirement 2: 地址坐标库缓存 single-flight + 增量失效（§3.7/§3.12）

**User Story:** As a 公式编辑器用户, I want 高并发下选址列表响应稳定, so that 不因缓存踩踏导致超时。

#### Acceptance Criteria

1. WHEN 某 slot 缓存失效后 N 个并发请求同时 miss THEN 仅 1 个请求触发重建，其余等待复用结果
2. WHEN 底稿保存触发 wp 域失效 THEN 仅失效被改动 wp_id 的条目（增量），不全域重建
3. WHEN validate_formula_refs 校验单个 WP 引用 THEN 定点查该 wp_code 的 cell 存在性，不加载全域

### Requirement 3: OCR 引擎服务化（§18.1）

**User Story:** As a 运维, I want OCR 引擎不随每个 web worker 加载, so that 内存可控。

#### Acceptance Criteria

1. WHEN OCR 请求到达 THEN web worker 经 HTTP/队列调用独立 OCR 服务，不在进程内加载 PaddleOCR
2. WHEN OCR 服务不可用 THEN 降级返回 503 "OCR 暂不可用" + 队列重试
3. WHEN 部署多 web worker THEN 总 OCR 内存占用 = 1 × 服务实例（而非 N × worker）
