# Spec C (R10) — Editor Resilience（编辑器三件套 + 容灾）

**编制人**：合伙人
**日期**：2026-05-16
**状态**：🟡 占位（待 v3 P0 全部完成 + Spec A 落地后再起草三件套）
**关联**：v3 §10（错误处理与容灾）

---

## 范围

2 周工时，分 2 Sprint：

### Sprint 1（1 周）— 三个编辑器 confirmLeave + WorkpaperSidePanel

- WorkpaperEditor / DisclosureEditor / AuditReportEditor 统一接入 `confirmLeave`
- 加 `beforeunload` 监听
- WorkpaperSidePanel 7 Tab 落地（v2 P2 未做）

### Sprint 2（1 周）— DegradedBanner 扩展 + 后端聚合端点

- DegradedBanner 扩展（5xx 比率 / 离线提示）v3 §10.2.B
- 后端 `/api/projects/{pid}/event-cascade/health` 端点（v3 §7.4）
- 危险操作二次确认补漏（LedgerDataManager 清理账套 / EqcrMemoEditor 定稿）

---

## 启动条件

- [ ] v3 P0 全部完成
- [ ] Spec A 实施完毕
- [ ] grep 当前 confirmLeave 接入情况（应 ≥ 0 视图）

**预期工时**：起草三件套 0.5 天 + 实施 2 周 = 11 个工作日。

可与 Spec B 并行（依赖面不重叠）。
