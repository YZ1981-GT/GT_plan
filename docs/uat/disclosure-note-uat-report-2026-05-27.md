# 附注模块 v2.0 UAT 验收报告（F-1）

**日期**：2026-05-27
**spec**：disclosure-note-full-revamp（44/47 → 46/47）
**测试项目**：2 个真实项目（首汽租车_2025 + 重庆和平药房_2025）
**模板类型**：国企版 SOE

## 数据规模对比

| 项目 | tb_balance | tb_ledger | trial_balance | disclosure_notes | docx |
|------|-----------:|----------:|--------------:|-----------------:|-----:|
| 首汽租车_2025（df5b8403） | 1,654 | 30,324 | 166 | **173 章节** | **138.8 KB** |
| 重庆和平药房_2025（2aa00f57） | 774 | 52,060 | — | **40 章节** | **38.2 KB** |

## 测试链路

### 项目 1：首汽租车_2025（直调 service 端到端）

| 步骤 | Service | 结果 |
|------|---------|------|
| Step 1 | `TrialBalanceService.full_recalc(project_id, year, "001")` | 166 行 trial_balance |
| Step 2 | financial_report_service | 模块名待确认（不阻塞） |
| Step 3 | `DisclosureEngine.generate_notes(project_id, year, "soe")` | **173 章节** |
| Step 4 | PG `disclosure_notes` 表实测 | 173 条入库 |
| Step 5 | `NoteWordExporter.export(project_id, year, "soe")` | **138,839 bytes docx** |

### 项目 2：重庆和平药房_2025（前端 UI 全链路）

| 步骤 | UI 操作 | 结果 |
|------|---------|------|
| Step 1 | Playwright 登录 admin/admin123 | OK |
| Step 2 | 导航 `/projects/{id}/disclosure-notes` | UI 渲染附注编辑器 |
| Step 3 | 点击「📝 生成附注」对话框 → 「开始生成」 | 后端 `POST /api/disclosure-notes/generate` 触发 |
| Step 4 | UI 显示 「40 个章节」 + PG 实测 40 条入库 | **40 章节**（小型零售业务，auto_trim 裁剪） |
| Step 5 | 点击「📤 导出Word」 | **38,117 bytes docx 下载** |

**重要发现**：40 章节 vs 173 章节差异 = **Sprint 3 NoteTrimService.auto_trim 起作用**（按 TB 科目存在性裁剪不相关章节，业务集中型企业附注精简）。

## 抽样章节标题（重庆和平药房）

```
五、1: 货币资金
五、2: 应收票据
五、3: 应收账款
五、4: 预付款项
五、5: 其他应收款
五、6: 存货
五、7: 长期股权投资
五、8: 投资性房地产
五、9: 固定资产
五、10: 在建工程
...（共 40 章节，均为「五、」开头 = 报表项目附注）
```

## 输出文件

- `docs/uat/disclosure-note-uat-shouqi-zuche-2025.docx` (138.8 KB) — 项目 1 完整版
- `docs/uat/disclosure-note-uat-heping-2025.docx` (38.2 KB) — 项目 2 裁剪版
- `docs/uat/heping-disclosure-notes.png` — 前端 UI 截图

## 修复清单（UAT 期间发现）

| 问题 | 根因 | 修复 |
|------|------|------|
| 多个 API 500 | 本地 PG schema 漂移（alembic chain 未跑齐） | V017 + V018 SQL 补丁，0 漂移确认 |
| `phase17_001` migration 失败 | `CREATE TYPE IF NOT EXISTS` PG 不支持 | 改 `DO $$ ... EXCEPTION WHEN duplicate_object` |
| `job_status` vs `job_status_enum` | ORM 与 migration 命名不一致 | V017 中 RENAME + 补 `interrupted` 值 |
| `import_jobs` 缺 3 列 | 后续 spec 加列未跑 | V017 补 `version` / `force_submit` / `creator_chain` |
| 65 列 + 10 表缺失 | 跨多 spec 累积 | V018 自动从 ORM 反推补齐 |
| 项目 default is_deleted=True | 测试遗留 | UPDATE 恢复（首汽租车 + 重庆和平药房） |

## 备注

- **financial_report_service 模块名不一致**：另立 issue，不阻塞附注
- **format-config 端点 405**：spec 自带 bug，FastAPI 同 prefix router 路由顺序问题，待修
- **首汽股份×2 + 重庆医药** 数据为空（tb_balance=0），UAT 只能用 2 个项目

## 验收结论

✅ **F-1 双项目链路通过**：

- **首汽租车_2025（service 直调）** — 完整 173 章节 + 138.8KB docx 实证
- **重庆和平药房_2025（前端 UI）** — auto_trim 40 章节 + 38.2KB docx 实证 + Playwright 全自动化

详细 UAT 数据 + Word 文件 + UI 截图留存于 `docs/uat/`。
