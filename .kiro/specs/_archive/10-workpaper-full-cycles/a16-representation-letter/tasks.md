# Implementation Plan

> **分期**：lite(矩阵+弹窗+完成态) → core(跳转页+按版本签回) → plus(报告+E2E)  
> **计数**：前置 2 + lite 10 + core 10 + plus 4 = **24 实现任务**（含 3 条分期 E2E）

---

## 前置：公共阻塞项

> 勾选状态以 [completion-phase-infra/tasks.md](../completion-phase-infra/tasks.md) 为准（PRE-1 ✅、PRE-3 ✅）。

---

## A16-lite：版本矩阵 + 程序表 + 弹窗 + 完成态（10 任务）

- [x] 1. 新建 `backend/data/a16_version_matrix.json`（business_category 子码 A2/B1/B2 + 默认 A16-1）
- [x] 2. `a16_version_service.py` + `GET /api/projects/{pid}/a16/recommended-version`（禁止用不存在 Project 字段）
- [x] 3. `procedure_table_auto_service.a16_template_recommend` 接入 version service（替换桩）
- [x] 4. A16 程序表扩充 4 步（seq2 全量 ref_index、seq3 A16-7、seq4 ref A16 跳转签回）
- [x] 5. seq2 chip UI：推荐版本置顶 + badge +「其他版本▼」折叠（非推荐不禁用）
- [x] 6. seq3 适用性：`applicable_default: no` + A7 交易计数 auto 建议（JSON 已有 default no；auto 已有 related_party）
- [x] 7. A16-1~6 弹窗 E2E（PRE-1/3：chip→弹窗→prefilled-download docx 可打开）
- [x] 8. A16-7 弹窗 E2E + relatedLinks→A7
- [x] 9. `GtAProgramConsole.checkCompletion` 新增 A16-1~7 case（sign_status=signed → completed；经 checklist `{code}-sign-status`）
- [x] 10. Playwright lite E2E：**E8**（见 [e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)）

**lite DoD**：seq1 显示「推荐 A16-x（请确认）」✅；seq2 推荐 chip 弹窗下载成功（prefilled-download 既有）；signed 后 chip 显示完成 badge ✅（弹窗签回 UI 已加）。

---

## A16-core：跳转页 + 主/补分离 + 按版本签回（10 任务）

- [x] 11. `WorkpaperWordEditor` 拆分：主版本区 A16-1~6 + 补充区 A16-7 toggle（移除 A16-7 混入主 radio）
- [x] 12. 版本推荐接 `recommended-version` API（删除 forCategory 硬编码 fallback）
- [x] 13. `selected_version` 持久化 + 按版本 sign_status scope（`word_template:A16:{version}`）
- [x] 14. sign-status API 扩展 optional `version` 参数；切换版本不继承 signed
- [x] 15. 虚拟子码：索引 A16-1~7 直达 → 重定向 A16 + `?version=`
- [x] 16. 弹窗「完整编辑」→ 跳转页同步 version
- [x] 17. OnlyOffice / 降级下载 upload 端到端（至少 1 个主版本）
- [x] 18. A13 alert：`GET /api/projects/{pid}/misstatements/for-letter` 有/无错报两路径
- [x] 19. prefilled-download 占位符验证（对照 `docx_placeholder_registry.json` A16-1；错报写入 docx 为可选）
- [x] 20. Playwright core E2E：**E9**

**core DoD**：A16-2 signed 后切 A16-1 显示 pending；A16-7 独立 toggle 签回不影响主版本。

---

## A16-plus：报告联动 + QC + E2E（4 任务）

- [x] 21. CW-76：signed 时必填 sign_date → push `representation_letter_date`（禁止读 docx 元数据）
- [x] 22. QC wizard_state「管理层声明」与主版本 sign_status 对齐
- [x] 23. A1 seq9 可选增强：主版本 signed 时 auto 建议 step completed
- [x] 24. Playwright plus E2E：**E16**

---

## 与 A17/A18 实施顺序

见 [linkage.md §全局实施顺序](../completion-phase-infra/linkage.md#全局实施顺序)。

**Out of scope（可独立 spec）**：
- 程序表 4 步 ↔ xlsx 7 行对齐（plus 后可选）
- A8-1 纳入主声明书提示
- docx 红/蓝字未完成检测（复用 PRE-2 filler，optional）
