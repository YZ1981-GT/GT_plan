# Spec B (R10) — Linkage & Tokens

**编制人**：合伙人
**日期**：2026-05-16
**状态**：🟡 占位（待 v3 P0 全部完成 + Spec A 落地后再起草三件套）
**关联**：v3 §7（联动闭环）+ §8（显示治理三条线）

---

## 范围

3 周工时，分 3 Sprint：

### Sprint 1（1 周）— 联动闭环 + AJE→错报补全
> 注：useStaleStatus 推 6 视图 + AJE→错报已在 Spec A 完成，本 Sprint 只做剩余的：

- 报表行 / 附注 → 底稿穿透完整接入（v3 §7.6）
- usePenetrate composable 抽出 `penetrateToWorkpapers(rowCode)`
- ReportView / DisclosureEditor / Misstatements 右键菜单加"查看相关底稿"

### Sprint 2（1 周）— 字号变量化 4 批

按 v3 §8.1 规约：

- 批 1：编辑器（WorkpaperEditor / WorkpaperList / WorkpaperWorkbench / DisclosureEditor）
- 批 2：表格类（TrialBalance / ReportView / Adjustments / Misstatements / Materiality）
- 批 3：Dashboard 系列
- 批 4：剩余视图

**验收**：grep `font-size:\s*\d+px` Vue 文件 wc -l == 0

### Sprint 3（1 周）— 颜色 + 背景 + GtEditableTable 瘦身

- 颜色 1611 处迁移到 var(--gt-color-*) / var(--gt-text-*)
- 背景 712 处迁移到 var(--gt-bg-*)
- GtEditableTable 瘦身为 GtTableExtended + GtFormTable（v3 §9）
- CI 加 `<el-table` baseline 卡点

---

## 启动条件（Sprint 0 强制核验）

- [ ] v3 P0-1 到 P0-13 全部完成
- [ ] Spec A 实施完毕（useStaleStatus 已推到 11 视图）
- [ ] grep 当前 token 体系（gt-tokens.css）已就绪
- [ ] CI 已能跑 stylelint（如未装则 Sprint 0 先装）

**预期工时**：起草三件套 1 天 + 实施 3 周 = 22 个工作日。
