# 设计：底稿双向回写保存安全与镜像一致性收口

## 1. 现状与基线

基线提交：`de31e7bf6fbb0a2403054c611a90028262e66ba7`，与远端当前分支一致。相关生产文件在主工作区无本地 diff；实施放在仓库根锁定的分离头工作树，避免覆盖并发会话。

现算事实：

- generated manifest：155 个 entry，122 个缺 adapter、142 个无 durable forcesave ack、124 个无 forcesave command。它们不纳入本轮 adapter 迁移。
- pendingWrites 旧棘轮 108 条。逐文件调用链复核：2 个 composable 无生产消费者；其余 106 个都没有形成“清 timer + 等真实 PUT”的完整屏障。26 个自管 D4 bridge 即使清了 timer，`dispatchEvent()` 也不会 await 异步 listener。
- 父写入链共 10 条：`d4`、`f2` 主/估值/特殊/盘点、`f3`、`f4`、`f5`、`g2`、`g4`。当前都没有把完整保存 Promise 交给 `trackPendingWrite`。
- `checklist_responses` 已支持可选 `if_match`，但通用持久化和多数循环 formData 丢掉 GET 返回的 version；无版本仍按 LWW 并只在回执标 `overwritten=true`。
- OO→HTML 当前先提交 canonical content，再调用 `store_mirror`。多 item 路径按块/按 item commit，后段失败会留下 canonical 新、HTML store 部分新部分旧。
- 前端相关基线 18 passed。后端 provider surface 81 passed、D2 store equivalence 24 passed；完整 app 路由测试在干净 HEAD 采集期因 `project_creation_grant_service` 未入库而失败，属于基线阻断，不把它算成本轮回归。
- 磁盘最高迁移 V234，共享库最高已应用 V232。本设计复用现有表与事务，不新增迁移。

## 2. 决策

### 2.1 镜像方案

比较两种方案：

| 方案 | 一致性 | 锁时长 | 恢复复杂度 | 改动面 |
|---|---|---:|---:|---:|
| A. canonical commit 后写 durable mirror job | 最终一致；UI 需新增 pending 状态 | 短 | 高：需冻结 provider/contract/payload、worker、状态迁移和重放 | 大 |
| B. 在 content commit hook 内 `commit=False` 镜像 | 单事务强一致 | 增加 store SQL/JSON merge 时间 | 低：失败沿既有 durable incoming retry | 小 |

选择 B。xlsx 提取、materialize、roundtrip 等 CPU 重段已经在事务外；事务内新增的是 checklist 读取、provider 纯 merge 和 SQL 写入。正确性收益高于增加的短事务成本。若后续压测证明镜像临界区超预算，再以本次原子行为为契约拆成“冻结最终 store payload + CAS job”，不能退回无状态的 post-commit best effort。

### 2.2 CAS 兼容策略

`BatchSaveRequest` 新增 `require_if_match=false`。已迁移客户端固定传 true：

- 行不存在：允许创建；
- 行存在且无 `if_match`：428 `version_required`；
- 行存在且版本不同：409 `version_conflict`；
- 兼容客户端不传该开关：维持原 LWW，并继续回 `overwritten=true`。

前端新增单一 helper，维护 `item_id → version`。加载完整 checklist 时记版本；保存时按 map 发送 `if_match` 和 `require_if_match=true`；成功回执推进 map。版本未知而服务端已有行时宁可 428 保脏，不自动 GET 后覆盖本地快照。

### 2.3 pending barrier

`trackPendingWrite` 内部保存 settled outcome，而不是把 rejection 抹成 `undefined`。`flushPendingWrites`：

1. 并发调用所有 flusher并收集异常；
2. 循环等待 flusher 新加入的 in-flight；
3. 等全部结算后抛 `PendingWritesFlushError(failures)`；
4. 下一次用户重试从新的失败窗口开始，不永久粘住已经成功重试的旧错误。
父 handler 以一个 Promise 覆盖完整批次或顺序循环。子 writer 的 flusher必须是 pending-only：timer 为空直接返回；有 timer才 clear、置空并调用立即保存。这样自身 bridge 后续再次调用相同函数也是 no-op，不会双写。

特例单独处理：

- `useF2Adjudication` 使用 `metaDebounceTimer/flushMetaSave`；
- `useF2Impairment` 的 `adjudicatedTimer` 只发业务事件，不登记为写盘 timer；
- `useF2Adjustment` 先消除注入保存成功后仍派 window event 的双写；
- `F4TabAdjustment`、`F5TabAdjustment` 卸载不能调用会重新建 timer 的 `persist()`；
- `useD4WalkthroughTest`、`D4TabMarginMonthly`、`D4TabCustomerStructure` 的自身 bridge先改为清 timer；
- `useIpoChecklistTab` 按每个 Vue effect scope 注册，不能建模块单例。

## 3. 事务与调用顺序

### 3.1 HTML → OO

```text
用户编辑
  → pending-only flusher 清私有 timer
  → 父 handler track 完整 PUT
  → PUT 使用严格 CAS
  → flushPendingWrites 确认全部成功
  → 宿主 flushHtml / readStoreProjection
  → pending mutation / materialize
```

失败边界：任一 PUT reject，bridge 的 `fail('flush')` 进入 sticky error，后续 projection/materialize 调用次数必须为 0。

### 3.2 OO → HTML

```text
incoming durable
  → base/current/incoming 三方合并
  → 锁外 rematerialize 与等值校验
  → ContentMutationService._commit_once
      → per-wp advisory + working_paper row lock
      → revision / version / representation / pointer
      → CommitFenceHook.after_pointers
          → store_view 补显式 null与可信公式重算值
          → mirror_projection_into_store(commit=False)
          → application / operation / room canonical fence
      → pending mutation / outbox
      → 唯一 commit
  → settle client baseline
```

`_apply_committed` 不再做第二次 mirror。镜像抛错时 `_commit_once` rollback；外层既有 `_record_post_durable_failure` 把同一 application/operation 记为 error，incoming 保留，用户 retry 重新走同一协调器。

## 4. 生产文件规划与 ROI

核心改动：

- 后端：`checklist_responses.py`、`oo_to_html.py`、`store_mirror.py`。
- 前端核心：`checklistCas.ts`、`pendingWrites.ts`、`useWorkpaperSyncBridge.ts`、现有对应单测。
- 保存入口：通用 `useChecklistPersistence`、10 个父宿主、相关循环 formData。
- writer 接线：106 个活路径做机械的 pending-only 登记；2 个死 composable不改生产代码，只从债务表删除并由零消费者守卫钉住。

收益：覆盖当前所有已识别的 2 秒私有防抖写入面；任何保存失败都从“静默打开旧 OO”变成显式阻断；任何 store mirror 失败都从“部分提交”变成整个业务提交回滚。

风险：文件数多但每个 writer 只加一个 import和一个局部注册点。用生成清单、逐文件语义检查、TS 编译、变异和代表性浏览器链控制风险；不顺手改业务公式、表头或 adapter。

## 5. 测试设计

| 层 | 关键断言 |
|---|---|
| TS 单元 | CAS 带版本、成功推进版本、409/428 保脏；pending 多失败聚合且等到全部完成 |
| bridge | pending 失败后 store projection/pending/materialize/mount 均 0 |
| 静态守卫 | 106 个 writer 都有 pending-only 注册；10 个父 handler完整 Promise 被 track；2 个死项仍零消费者 |
| Python 单元 | strict CAS 的 428/409/新建/legacy LWW 四态 |
| mirror 单元 | dedicated 缺门面抛域错误；`commit=False` 下任何分支零 commit |
| 协调器 | mirror 在 hook 内、早于唯一 commit；post-commit 路径无 mirror调用 |
| PG | mirror 第 N 项失败时 revision/version/pointer/application/operation/outbox/store 全保持原值；retry 只推进一次 |
| 浏览器 | 【测试】项目快速切换、失败阻断、OO 往返刷新一致 |

## 6. 非目标与交接

- 不扩大 155 entry 中的 adapter/capability 覆盖；继续由 `oo-writeback-template-parity-closure` 和逐循环 spec处理。
- 不把 Univer 纳入 content/application 协议。
- 不在本轮把 callback apply 改成异步 worker，也不做 room/recovery 历史账面清理。
- 后续顺序：callback durable 后异步化与生命周期 reaper → adapter/template 覆盖 → Univer 统一 → 6000 人容量验收。
