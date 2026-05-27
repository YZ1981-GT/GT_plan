# 附注模块 v2.0 UAT 验收报告（F-1）

**日期**：2026-05-27
**spec**：disclosure-note-full-revamp（44/47 → 45/47）
**测试项目**：首汽租车_2025（df5b8403-abbb-48af-b6a4-6fd44dfae5c9）
**模板类型**：国企版 SOE

## 数据规模

| 维度 | 计数 |
|------|------|
| tb_balance（科目余额） | 1,654 |
| tb_ledger（明细账） | 30,324 |
| trial_balance（试算表，重算后） | 166 |
| disclosure_notes（生成后） | 173 |

## 测试链路

直接调 service 跑全链路（agent 调 service 优于 Playwright UI 铁律）：

| 步骤 | Service | 结果 |
|------|---------|------|
| Step 1 | `TrialBalanceService.full_recalc(project_id, year, "001")` | 166 行 trial_balance |
| Step 2 | financial_report_service | 模块名不一致，跳过（不阻塞附注） |
| Step 3 | `DisclosureEngine.generate_notes(project_id, year, "soe")` | **173 章节** |
| Step 4 | PG `disclosure_notes` 表实测 | 173 条入库（is_deleted=false） |
| Step 5 | `NoteWordExporter.export(project_id, year, "soe")` | **138,839 bytes docx** |

## 抽样章节标题

```
一、1: 公司基本情况
二、1: 财务报表编制基础
三、1: 遵循企业会计准则的声明
四、会计期间: 会计期间
四、记账本位币: 记账本位币
四、记账基础和计价原则: 记账基础和计价原则
四、企业合并: 企业合并
四、合并财务报表编制: 合并财务报表编制方法
四、合营安排的分类及: 合营安排的分类及共同经营的会计处理方法
四、现金及现金等价物: 现金及现金等价物
...（共 173 章节）
```

## 输出文件

`docs/uat/disclosure-note-uat-shouqi-zuche-2025.docx` (138.8 KB)

## 修复清单（UAT 期间发现）

| 问题 | 根因 | 修复 |
|------|------|------|
| 多个 API 500 | 本地 PG schema 漂移（alembic chain 未跑齐） | V017 + V018 SQL 补丁，0 漂移确认 |
| `phase17_001` migration 失败 | `CREATE TYPE IF NOT EXISTS` PG 不支持 | 改 `DO $$ ... EXCEPTION WHEN duplicate_object` |
| `job_status` vs `job_status_enum` | ORM 与 migration 命名不一致 | V017 中 RENAME + 补 `interrupted` 值 |
| `import_jobs` 缺 3 列 | 后续 spec 加列未跑 | V017 补 `version` / `force_submit` / `creator_chain` |
| 65 列 + 10 表缺失 | 跨多 spec 累积 | V018 自动从 ORM 反推补齐 |
| 首汽租车_2025 默认 is_deleted=True | 测试遗留 | UPDATE 恢复 |

## 备注

- **不阻塞附注 spec 收口**：3 真实项目 UAT 中目前仅首汽租车_2025 数据完整，重庆和平药房_2025（774 tb_balance / 52060 tb_ledger）也可跑同链路
- **financial_report_service 模块名不一致**：另立 issue，不阻塞附注
- **format-config 端点 405**：spec 自带 bug，FastAPI 同 prefix router 路由顺序问题，待修

## 验收结论

✅ **F-1 核心链路通过**：TB → trial_balance → 附注生成 → Word 导出全程跑通，173 章节 + 138.8KB docx 实证。

详细 UAT 数据 + Word 文件留存于 `docs/uat/`。
