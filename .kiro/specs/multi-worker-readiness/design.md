# Design Document

## Overview

三组改动使系统具备多 worker 水平扩展能力：(1) 导入锁改用 Redis 分布式锁 + DB 状态校验；(2) 地址坐标库加 asyncio.Lock single-flight + wp 域增量失效；(3) OCR 抽为独立 HTTP 服务（或 Celery worker）。

## Architecture

### 1. 导入分布式锁（§7.1）

- **Redis 锁**：`import_lock:{project_id}` key，TTL=30min（自动过期兜底），SET NX EX 获取
- **DB 校验兜底**：`SELECT ... FROM import_jobs WHERE status='running' AND project_id=:pid FOR UPDATE` 作为 Redis 不可用时的降级路径
- **取消信号**：`import_jobs.cancel_requested` bool 列 + worker 轮询（每 5s 检查一次）
- **全局并发上限**：`SCARD import_lock:active_set` ≤ MAX（Redis Set 记录活跃项目 ID）

### 2. 地址坐标库 single-flight + 增量失效（§3.7/§3.12）

- **single-flight**：`_get_domain` 内 per-slot_key `asyncio.Lock`，同一 key 并发 miss 只构建一次
- **增量失效**：`invalidate_async(pid, domain='wp', wp_id=changed_id)` — wp 域 slot 内按 wp_id 分桶，仅删被改动的 wp_id 条目并补重建
- **validate 定点检查**：新增 `exists(domain, uri)` 方法，WP 域只查目标 wp_code 的 cell 是否存在，不全域物化

### 3. OCR 服务化（§18.1）

- 新增 `docker-compose.ocr.yml` 定义 OCR 容器（PaddleOCR + Tesseract + MinerU）
- `unified_ocr_service.recognize` 改为 HTTP 调用 `OCR_SERVICE_URL/recognize`（env 配置）
- 降级：HTTP 超时 / 连接失败 → 503 + warning 日志
- web worker 不再 `from paddleocr import PaddleOCR`（import 延迟到 OCR 服务内部）

## Components and Interfaces

- **Redis 分布式锁** — `import_lock:{project_id}` key（SET NX EX），`import_lock:active_set` 全局并发计数
- **OCR HTTP 服务** — 独立容器 `docker-compose.ocr.yml`，`POST /recognize` 接口
- **single-flight asyncio.Lock** — `AddressRegistryService` 内 per-slot_key Lock dict，防缓存踩踏

## Data Models

- **`import_jobs.cancel_requested`** — `BOOLEAN DEFAULT FALSE`，新增列（migration V092），用于跨 worker 取消信号

## Correctness Properties

Property 1: 多 worker 同项目并发导入 → 恰好一个获取锁

Property 2: N 并发 miss → DB 查询仅 1 次 + N 个请求拿到相同结果

Property 3: web worker 内存不含 PaddleOCR 模型（<100MB baseline）

## Testing Strategy

- **压测先行**：本 spec 所有 Requirement 实施前须先用 Locust 压测确认瓶颈量级
- Unit：mock Redis lock acquire/release → verify concurrent reject
- Integration：2 个 worker process 同时导入 → 一个成功一个拒绝
- Memory：OCR 服务化前后 web worker RSS 对比
