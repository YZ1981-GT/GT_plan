# 关注点（F4 应付账款）

## 1. 账龄口径未统一（全平台唯一）

D/E/G/H/I/J/K/L/M/N 各明细表账龄都已收敛到 `useAgingConfig`（3 年段 / 5 年段 / 自定义），
**只有 F4 还是自有 5 固定 rowKey**（`within1year` / `1to2year` / `2to3year` / `3yearplus` / `aging-other`）
**+ 明细表扁平 4 字段**（`unadjustedAgingLt1/1to2/2to3/Gt3` + `auditedAging*`）。

- 读写同源 → **当前不产生错数**，但切 5 年段/自定义段时 F4 不跟随项目口径
- `aging-other` 是**残差行不是账龄段**，不应计入"1 年以上"；国企披露"除 1 年内全部"的写法需修正
- 后端 `subject_aging_periods('F4')` 需新增分支返 `['current','audited']`（F4 无期初账龄），
  落默认 `['prior','audited']` 会产错列头
- 迁移跨 6+ 文件（明细/审定/关联方/长期挂账/披露/列偏好）→ 已立 spec `f4-aging-enum-unification`，红线是 3 年段逐字节零回归

## 2. 完整性是主认定，别只看余额

未入账应付搜索（`F4TabUnrecordedCheck`）是 F4 的核心程序：期后付款、未开票已收货、
供应商对账差异都可能指向未入账负债。只核对已入账余额不构成完整性证据。

## 3. 双通道事件（勿只发一条）

审定表回写同时发 `eventBus.emit('substantive:adjudicated')` 与 `window` 的 `f4:writeback-trial-balance`。
两通道经 `crossWpEventBridge` 双向桥接，新增消费者用 eventBus 即可，但改生产端时两条都要保留兼容。

## 4. 附注刷新依赖载荷字段

`disclosure:note-text-updated` 必须带 `accountCode:'2202'` + `sectionIds`（listed 为 `['五、37']`），
否则 `useNoteRefresh` 的定向刷新匹配不中，只能靠底稿保存后的全量刷新兜底。
