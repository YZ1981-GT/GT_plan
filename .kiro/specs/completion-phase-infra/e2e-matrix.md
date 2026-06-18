# 完成阶段 E2E 用例矩阵（跨 spec）

> 各 spec tasks 中的 Playwright 项须覆盖下表对应 ID；**不重复维护**第二套用例表。

---

## E2E 夹具项目

| 夹具 ID | business_category | 用途 |
|---------|-------------------|------|
| **FIX-A** | A 类（如 A1/A2） | A17 适用性、A17-5、A18 |
| **FIX-B** | B 类默认财报 | A7–A15、A16-1、A18 |
| **FIX-INT** | 整合审计信号（B60 或 audit_type） | A16-2、A11-3 |
| **FIX-RP** | A7 有关联交易 | A16-7 推荐 |

测试数据：至少 1 个 FIX-B 项目 + 1 个 FIX-A 项目；PRE-1 smoke 可在 FIX-B 上跑。

> **🔴 前置风险（实施前确认）**：真实 PG 数据多为 standalone，**A 类项目夹具（FIX-A）是否存在未经确认**——这正是合并模块「代码全绿、UAT 全 data-blocked」的同款风险。A17 全系列 E2E（E10–E12、E17）+ A18 部分用例均依赖 FIX-A。**E-FIX 前置任务**：确认或构造 FIX-A / FIX-B / FIX-INT / FIX-RP 种子项目，否则相关 E2E 无法标绿（只能标 `[ ]*` 代码已改未实测）。

> **行动项**：需编写 `scripts/e2e/seed_fix_projects.py` 构造最小种子数据（或确认现有项目 df5b8403 等可复用）。此任务为纯数据准备，不阻塞代码实施但阻塞 E2E 标绿。

---

## 用例矩阵

| ID | 分期 | Spec | 步骤 | 断言 |
|----|------|------|------|------|
| **E-PRE-1** | infra | 公共 | 五件套 prefilled-download | 200；docx 可开（A8-1/A9-1/A16-1/A17-3/A18-1） |
| E1 | lite | A7–A15 | A8 seq2 → A8-1 弹窗 → 下载 | client_name 已替换 |
| E2 | lite | A7–A15 | A9 → A9-1 下载 | 无空格文件名 fallback |
| E3 | lite | A7–A15 | A10 seq7 → A10-1 | 大文件可下；guidance 节锚点 |
| E4 | lite | A7–A15 | FIX-B 打开 A14 程序表 | chip 灰显符合 applicable |
| E5 | core | A7–A15 | A15-1 填 1 项 → 刷新 | checklist_responses 仍在 |
| E6 | core | A7–A15 | A11 目录 F=A11-1 | 审定表 sheet，非 docx |
| E7 | lite | A7–A15 | A11 chip A11-1 | docx 弹窗 |
| E8 | lite | A16 | 推荐 chip → 弹窗 → 下载 | A16-x docx 可开 |
| E9 | core | A16 | 跳转页 A16-2 signed → 切 A16-1 | 签回状态独立 |
| E10 | lite | A17 | FIX-A：A17-3 chip 弹窗 | docx 下载 |
| E11 | lite | A17 | A17-5-1 填 1 条 → 刷新 | 不丢 |
| E12 | core | A17 | A17-1 写 ch01 → export-word | 无蓝【】；无 XX |
| E13 | lite | A18 | A18-1 弹窗下载 | docx 可开 |
| E14 | core | A18 | A18-2 填 4 议题（1 不适用）→ 导出 | 不适用段删除 |
| E15 | plus | A7–A15 | A8-1 export-word | PRE-2 质量 |
| E16 | plus | A16 | signed → 填 sign_date | CW-76 报告字段 |
| E17 | plus | A17 | KAM 1 条 → push | 报告 KAM 段落 |
| E18 | plus | A18 | A18-1 小结生成 | 依赖 A17-1 有内容 |

---

## Spec → 用例映射

| Spec | 必覆盖 ID |
|------|-----------|
| completion-phase-infra | E-PRE-1 |
| a7-a15 | E1–E7, E15 |
| a16 | E8, E9, E16 |
| a17 | E10–E12, E17 |
| a18 | E13, E14, E18 |
| a13 / a14 | E5、E6 中与 A13/A14/A15 相关子集 |
