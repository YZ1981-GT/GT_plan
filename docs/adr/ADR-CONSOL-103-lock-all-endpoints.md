# ADR-CONSOL-103: 锁定按子公司写端点全覆盖 + 前端 banner + 423 拦截

## 状态
已接受 (2026-05-31)

## 背景

Phase 0 让 `consol_lock` 真实生效（三层一致 + 去静默 pass）。Phase 1 实证发现锁定覆盖已较 proposal 旧认知（"仅 trial+adjustments 5 端点"）更广（Phase 0 已扩展到 adjustments/disclosure_notes/ledger_data/report_mapping/report_line_mapping/trial_balance/working_paper 部分端点），但仍有遗漏：底稿的 parse/assign/submit-review/review-status/sync-procedure、报表 generate、附注 update/generate、序时账 restore 等子公司写端点未挂锁。且部分端点仅含资源 id（wp_id/note_id）无 project_id，原 `check_consol_lock` 无法反查。

## 决策

1. **check_consol_lock 增强**（deps.py）：`project_id` / `wp_id` / `note_id` 均改为可选；端点含 project_id 直接判锁；仅含资源 id 时反查所属 project_id（WorkingPaper / DisclosureNote）再判锁。
2. **EH4 放行**：资源 id 反查不到所属项目 → 放行不误拦 + warning（不阻断合法操作）；既无 project_id 也无资源 id → 放行。
3. **全端点覆盖**（grep 子公司写端点逐一挂 `Depends(check_consol_lock)`）：
   - 底稿：parse / assign / submit-review / review-status / sync-procedure（补充既有 univer-save/upload/status/prefill）。
   - 附注：`PUT /{note_id}`（经 note_id 反查）+ `POST /generate`（project_id 在 body，inline 调用）。
   - 报表：`POST /api/reports/generate`（project_id 在 body，inline 调用）。
   - 序时账：restore（补充既有 delete/incremental-apply）。
4. **前端闭环（F2/F4）**：
   - 新建 `ConsolLockedBanner.vue`（仿 ArchivedBanner，无 props，内部 `checkLockStatus` 拉锁定态，橙色横幅）；挂到 7 个子公司编辑视图（ReportView/TrialBalance/WorkpaperList/Misstatements/DisclosureEditor/Adjustments/EditorBanners）。
   - http 拦截器：检测 423 + detail 含"合并锁定" → ElMessage「项目已被合并锁定，无法修改」+ emit `consol-lock:detected` 事件触发 banner 刷新。

## 后果

- 锁定真正覆盖子公司全部数据修改入口（F2 闭环）。
- body/资源 id 端点统一可判锁（5.2/5.3）。
- 代价：反查开销（写端点低频，主键索引，可接受，R4）+ 覆盖遗漏风险（grep + Q5 参数化集成测试守门，R5）。
- 真实 UI 闭环须 Playwright 实测（`e2e/consol-phase1-lock-banner.spec.ts`，待 start-dev.bat 环境）。
