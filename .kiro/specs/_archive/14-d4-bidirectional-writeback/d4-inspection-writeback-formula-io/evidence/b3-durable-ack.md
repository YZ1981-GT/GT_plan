# B3 durable ack — 未更正错报推送 durable 幂等（V164）

> 起因：真栈 Playwright 实测印证 A13 推送去重仅靠前端 5s 内存 Map（`recentHashes`），跨窗口/刷新/长间隔失效 —— D4-16 两次点击（间隔 48s）产生 2 条重复错报（见 cutoff spec `evidence/playwright-realstack-verify.md` RS4）。本次把去重升级为**服务端 durable 幂等**。

## 设计（source_identity 部分唯一索引）

| 层 | 改动 |
|---|---|
| 迁移 | `V164__misstatement_source_identity.sql`（+ R164 回滚）：`unadjusted_misstatements` 加 `source_identity VARCHAR(200)` + 部分唯一索引 `uq_misstatement_source_identity (project_id, source_identity) WHERE source_identity IS NOT NULL AND is_deleted=false` |
| 模型 | `UnadjustedMisstatement.source_identity` + `__table_args__` 部分唯一 Index（`postgresql_where`） |
| schema | `MisstatementCreate.source_identity`（入参）+ `MisstatementResponse.source_identity` + `deduplicated: bool`（出参） |
| service | `create_misstatement`：携带 identity 时先 pre-check 既有（同项目+同 identity+未软删）→ 命中返回既有记录 `deduplicated=True` 不新增；插入路径用 `begin_nested()` savepoint + 捕获 `IntegrityError` 兜 TOCTOU 并发（DB 唯一索引为最终保证）；identity 为空走原直插路径（兼容手工/AJE） |
| 前端 | `useA13MisstatementBridge` POST 体加 `source_identity = draftHash(d).slice(0,200)`（与内存 draftHash 同字段：wpCode\|desc\|amount\|account\|type）；内存 5s 窗口保留作快速双击防抖，durable 幂等作跨会话最终保证 |

## 语义要点

- **identity 含 misstatementType 维度**：同金额同描述的 factual 与 projected 是两笔（CAS 1251 分类汇总），不互吞。
- **软删除后可重推**：部分唯一索引带 `is_deleted=false`，删除的错报其 identity 释放，可重新推送。
- **NULL 不参与幂等**：手工新建、AJE 转错报（走 source_adjustment_id 独立幂等）不受约束。

## 验证

- **服务级守卫**：`backend/tests/test_misstatement_source_identity_dedup.py` **4 passed**
  - 同 identity 跨调用只落 1 条、第二次 `deduplicated=True` 同 id（真栈曾 2 条现恒 1）
  - 不同 identity 两笔独立
  - NULL identity 每次新增（兼容）
  - type 维度：factual/projected 同款描述金额是两笔
- **无回归**：`test_misstatements.py`(18) + dedup(4) = **22 passed**；前端 `useA13MisstatementBridge.spec.ts`(8)+`a13MisstatementType.spec.ts`(21) = **29 passed**
- **变异**：`scripts/diagnose/mutate_misstatement_dedup_guards.py` 3 锚点全 **RED**（pre-check 恒不命中 / 命中不 return / identity 不落库），green_count=0，restored_ok=true，pass=true
- **🔴 真栈实测（运行后端 9980 + 真 PG，隔离项目 2099）**：同 `source_identity` 两次 POST（间隔 24s > 旧 5s 窗口）→ DB **恰 1 行**（`SELECT ... GROUP BY source_identity` 实证 rows=1）。旧 5s 窗口下必产 2 行的场景现被 durable 去重。探测数据已清理（2 行 deleted）。

## 覆盖面

`useA13MisstatementBridge` 是全平台 A13 推送的唯一消费者（挂 WorkpaperEditor），~35 个底稿推送点全部经它。本次 durable 幂等对**所有循环的推送点**统一生效，非仅 D4。

## 结论

B3 durable ack 从 spec 登记的 `[blocked]`（平台级待建）**转为已做实**：服务端 DB 层 durable 幂等 + 并发硬化 + 真栈实测 + 变异守卫。剩余的「失败重试队列/持久 outbox」属更重的异步基础设施，本次未做（A13 写入是同步 POST，失败即时返回由前端 try/catch 计 fail；durable 幂等已消除重复这一主要痛点）。
