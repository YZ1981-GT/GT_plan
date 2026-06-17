# Implementation Plan

> **分期**：audit-xlsx(深读) → lite → core → plus  
> **计数**：audit 26 + lite 16 + core 25 + plus 10 = **77 项**（PRE/infra 见 completion-phase-infra）

---

## audit-xlsx：26 文件逐格深读（26 任务，与 lite 并行）

> 产出 `backend/data/a7_a15_xlsx_audit.json`；深读结论已回写 requirements 底稿清单与设计文档。

- [x] **X-A7** A7 关联交易程序表.xlsx
- [x] **X-A7-1** A7-1 汇总关联方交易及关联往来.xlsx
- [x] **X-A7-2** A7-2 关联方交易附注披露信息.xlsx
- [x] **X-A8** A8 其他信息程序表.xlsx
- [x] **X-A8-1** A8-1 书面声明.docx（docx 占位符扫描）
- [x] **X-A8-2** A8-2 其他信息比对记录.docx
- [x] **X-A9** A9 内部控制建议程序表.xlsx
- [x] **X-A9-1** A9-1 致管理层沟通函.docx
- [x] **X-A9-2** A9-2 致治理层沟通函.docx
- [x] **X-A10** A10 与治理层沟通程序表.xlsx
- [x] **X-A10-1** A10-1 与治理层沟通函.docx
- [x] **X-A10-2** A10-2 与治理层的沟通记录.xlsx
- [x] **X-A11** A11 期后事项程序表.xlsx（6 sheet：程序+审定表A11-1+问卷A11-2/3）
- [x] **X-A11-1** A11-1 期后事项问询函.docx
- [x] **X-A12** A12 律师回复程序表.xlsx
- [x] **X-A12-1** A12-1 法律事务确认函.docx
- [x] **X-A13** A13 错报（程序表及底稿）.xlsx（8 sheet 全读）
- [x] **X-A14** A14 内部控制缺陷程序表.xlsx
- [x] **X-A14-1** A14-1 内部控制缺陷汇总表.xlsx
- [x] **X-A14-2** A14-2 企业层面控制缺陷评价.xlsx
- [x] **X-A14-3** A14-3 IT缺陷汇总及评价.xlsx
- [x] **X-A14-4** A14-4 业务流程层面控制缺陷评价.xlsx
- [x] **X-A14-5** A14-5 与其他缺陷一同进行评价.xlsx
- [x] **X-A14-6** A14-6 非财务报告内部控制缺陷评价.xlsx
- [x] **X-A15** A15 持续经营程序表.xlsx
- [x] **X-A15-1** A15-1 持续经营调查表.xlsx

**audit DoD**：26/26 写入 audit JSON ✅；requirements 底稿清单已更新；procedure_table JSON diff 全部对齐（A8 ●/5.x 已处理）。

---

## 前置

> [completion-phase-infra/tasks.md](../completion-phase-infra/tasks.md)（PRE-1/3/4-3~4、PRE-2 plus）。本 spec **不重复勾选** PRE。

---

## lite：程序表 HTML + docx 弹窗（16 任务）

- [ ] 1. 确认 A7–A15 打开为 `GtAProgramConsole` HTML
- [x] 2. procedure_table JSON vs xlsx diff（**A8–A15 ✅** 全部对齐）
- [ ] 3. ref_index：A9/A10/A11/A12 补全；A11 增加 **A11-2**
- [ ] 4. A8/A7/A14/A15 ref_index 验证
- [ ] 5. **A14** 程序表 `applicable_categories` A/B 验证（chip 灰显，**不等到 plus**）
- [ ] 6. **A8-1** 弹窗 E2E（PRE-1/3）：A8 seq2 chip → guidance → prefilled-download 可打开；含 client_name/年度替换
- [ ] 7. **A8-2** 弹窗 E2E：A8 seq3 chip → 下载 docx；封面 index=A8-2
- [ ] 8. **A9-1** 弹窗 E2E：无空格文件名 prefilled-download（PRE-1 边界）
- [ ] 9. **A9-2** 弹窗 E2E
- [ ] 10. **A10-1** 弹窗 E2E：大文件下载 + guidance 按节锚点可见
- [ ] 11. **A11-1** 弹窗 E2E
- [ ] 12. **A12-1** 弹窗 E2E
- [ ] 13. A13-1 `misstatement-summary` 验收（有错报/无错报）
- [ ] 14. A7-1 Univer 跳转 smoke
- [ ] 15. Playwright lite：**E1**（见 [e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)）
- [x] 16. 文档：A11-1 docx vs xlsx 审定表路由（requirements §7 + design §Sheet 路由）

**lite DoD**：程序表 HTML 可操作；**smoke 三件套**（A8-1 + A9-1 + A10-1）docx 下载成功；A13-1 汇总非空（有数据时）；A14 chip 适用性正确。

---

## core：Tab/表单/核对表 HTML（25 任务，编号 17–41）

### A13 Tab 套件

> 子 spec：[a13-misstatement-workpaper](../a13-misstatement-workpaper/requirements.md)

- [ ] 17. `GtMisstatementWorkpaper.vue` Tab 容器（程序表/汇总/A13-2~5）
- [ ] 18. `_WP_CODE_OVERRIDE["A13"]` → `misstatement-workpaper`
- [ ] 19–22. A13-2/3/4/5 `d-form-table` HTML + 持久化（**依赖 X-A13**）

### A11

- [ ] 23. A11 双轨路由 E2E：chip A11-1→docx 弹窗；目录 F=A11-1→审定表 sheet（**非** docx）
- [ ] 24. A11-2 问卷 checklist-table（**依赖 X-A11**）
- [ ] 25. xlsx 内「期后事项审定表A11-1」HTML grid

### A10 / A15 / A14-1~4 / A7-2

> A14 子 spec：[a14-control-deficiency](../a14-control-deficiency/requirements.md)

- [ ] 26–28. A10-2 d-form-confirmation 修正 + E2E
- [ ] 29–32. A15-1 checklist-table + EQCR 引用（**依赖 X-A15-1**）
- [ ] 33–34. A14-1 checklist-table（**依赖 X-A14-1**）
- [ ] 35–37. A14-2/4 d-form-table HTML（**依赖 X-A14-2/4**）
- [ ] 38. **A14-3** `a14-3-workbook` Tab 容器 + 各 sheet d-form（**依赖 X-A14-3**）
- [ ] 39. A7-2 `c-note-table` 注册 + chip 跳转
- [ ] 40. `GtRelatedPartySummary` + API

- [ ] 41. Playwright core：**E5**

**core DoD**：A13 至少 2 个 Tab 可保存；A15-1/A14-1 为 HTML；A10-2 非 Univer；A11 双轨不串路由。

---

## plus：A14-5/6 + 联动 + E2E（10 任务，编号 42–51）

- [ ] 42. A14-5 d-form-table HTML（**依赖 X-A14-5**）
- [ ] 43. A14-6 e-control-test HTML（**依赖 X-A14-6**）
- [ ] 44. A14 JSON seq5/6 + ref_index
- [ ] 45. A14→A9 弹窗 guidance；issue_tickets 映射修正
- [ ] 46. docx 弹窗 checkCompletion（见 design §checkCompletion）
- [ ] 47. 摘要 API A13/A15 downstream（就绪表见 requirements §8）
- [ ] 48. A13→A16；A7→A16-7；**A8→A18**（A18 议题3 引用 A8-2 状态提示）
- [ ] 49. A7-1 HTML 表格（可选，依赖 X-A7-1）
- [ ] 50. **A8-1/2 export-word**（infra PRE-2；**E15**）
- [ ] 51. Playwright plus：**E15**（+ 可选 E9 若 A14-1/A9 guidance 已落地）

---

## 模块→分期速查

| 模块 | audit | lite | core | plus |
|------|-------|------|------|------|
| A7 | X-A7~2 | 程序表+跳转 | 摘要+c-note-table | A7-1 HTML |
| A8 | X-A8~2 | 程序表+弹窗 | — | 联动 A18 |
| A9 | X-A9~2 | 程序表+弹窗 | — | A14 提示 |
| A10 | X-A10~2 | 程序表+弹窗 | A10-2 d-form | — |
| A11 | X-A11~1 | 程序表+弹窗 | 冲突分流+问卷+审定表 | — |
| A12 | X-A12~1 | 程序表+弹窗 | — | — |
| A13 | X-A13 | A13-1 验收 | Tab+A13-2~5 | 摘要 API |
| A14 | X-A14~6 | 程序表+适用性 | A14-1~4 HTML；**A14-3 workbook** | A14-5/6 |
| A15 | X-A15~1 | 程序表 | A15-1 checklist | 摘要 API |

---

## 实施顺序

```
audit-xlsx（26 文件，可与 lite 并行启动）
    ↓
PRE-1/3 → lite（A8-1/2 弹窗 E2E = 下载 docx 可打开）
    ↓
PRE-2（公共）→ plus（A8-1/2 export-word 无蓝【】残留）
    ↓
PRE-4 + core
    ↓
plus
```

**原则**：core 中 parser/核对表任务 **依赖对应 X-* audit 完成**；PRE-4-3/4 勾选见 infra/tasks.md。

---

## E2E

本 spec 用例 **E1–E7、E15** → [e2e-matrix.md](../completion-phase-infra/e2e-matrix.md)（不重复维护下表）。
