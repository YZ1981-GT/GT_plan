# A21~A25 各角色复核底稿 — 任务



> **分期**：audit → lite → core → plus → E2E  

> **计数**：audit 10 + 前置 1 + lite 5 + core 7 + plus 3 + E2E 2 = **28 任务**  

> **进度（2026-06-18）**：**28/28** ✅



---



## audit-xlsx：10× 模板深读（与 lite 并行启动，**阻塞 definitions 标绿**）



> 产出 `backend/data/a21_a25_xlsx_audit.json`；脚本 `scripts/audit_a21_a25_xlsx.py`。



- [x] **X-A21-1** 项目现场负责人复核表（财报）— 19 条

- [x] **X-A21-2** 项目现场负责人复核表（内控）— 25 条

- [x] **X-A22-1** 项目负责经理复核（财报）— 13 条

- [x] **X-A22-2** 项目负责经理复核（内控）— 18 条

- [x] **X-A23-1** 项目合伙人复核（财报）— 12 条

- [x] **X-A23-2** 项目合伙人复核（内控）— 24 条

- [x] **X-A24-1** 质量复核合伙人（财报 × 国企/非国企）— 各 4 条

- [x] **X-A24-2** 质量复核合伙人（内控）— 5 条

- [x] **X-A25-1** 质量控制复核人（财报 × 国企/非国企）— 34 / 19 条

- [x] **X-A25-2** 质量控制复核人（内控）— 18 条



**DoD**：audit JSON ✅；`--write-definitions` → `a21_a25_review_definitions.json`（12 templates）✅



---



## 前置



- [x] **0. V087 迁移**：`V087__projects_audit_context.sql` + `Project.audit_type` / `is_large_soe` ORM



---



## lite：A21-1 单角色全链路（5 任务）



- [x] 1. audit → `a21_a25_review_definitions.json`（A21-1 含 19 条 ≥15）

- [x] 2. `review_checklist_service.py` + `get_review_context` / `get_review_definition_for_wp`

- [x] 3. `_WP_CODE_OVERRIDE` 显式子码 A21-1…A25-2 + `GtReviewChecklist.vue` 替换 `ReviewChecklistPanel.vue`

- [x] 4. checklist_responses 保存（`-chk-*`）+ debounce 1500ms

- [x] 5. pytest：`test_review_checklist_service.py` ✅（5 passed）



**lite DoD**：A21-1 打开 → 渲染 → 勾选刷新不丢 ✅ **E20** spec ✅



---



## core：多角色 + 签字 + A1（7 任务）



- [x] 6. definitions 扩全 10+ 模板（audit 已覆盖 12 variant entries）

- [x] 7. `a21_a25_version_selector.py` + `GET applicable-review-templates` + UI badge

- [x] 8. 复核记录区（`-record`）+ `POST review-sign`（`-sign`）

- [x] 9. A1 程序表步骤扩充（seq 15–17 现场/经理/合伙人 + 原 15→18 质控）+ procedure status 回写

- [x] 10. `GtAProgramConsole.checkCompletion` A21–A25 case

- [x] 11. `ReviewWorkflowService.get_review_progress` 收敛为 checklist_responses 薄读层

- [x] 12. vitest + pytest（签字 API + B 类 A24 不适用 + 版本选择）



**core DoD**：B 类 A24 不适用不渲染；签字 pass → A1 ✓ ✅ **E21** spec ✅



---



## plus：预填 + 导出（3 任务）



- [x] 13. 自动预填建议（底稿完成率 / 调整复核状态）

- [x] 14. xlsx 导出（PRE-2 + checklist 回填 √/N/A/签字）

- [x] 15. `seed_fix_projects.py` FIX 夹具补 A21-1~A25 子码



**plus DoD**：导出 xlsx 可开 ✅ **E22** spec ✅



---



## 集成验证



- [x] 16. Playwright **E20**（`e2e/a21-lite.spec.ts`）

- [x] 17. Playwright **E21 + E22**（`e2e/a21-core-plus.spec.ts`）



> 全量矩阵：[e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)



---



## 移出 / 依赖他 spec



| 项 | 处置 |

|----|------|

| PRE-2 filler | infra ✅；本 spec 只编排导出 |

| E-FIX 种子 | infra ✅；task 15 增子码清单 |

| A17-5 核对项 A22/A23 引用 | 读 `-sign`；`GET /api/a17/review-sign-hints` + GtChecklistTable 建议 ✅ |
| A1 seq15–17 父码 A21/A22/A23 | 动态解析子码 + chip 必做 badge + 灰显 ✅ |

