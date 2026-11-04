# 实施计划：公式管理阻断缺陷收口（formula-hub-release-blockers）

> 以 requirements.md 和 design.md 为准。
> 临时产物放仓库根 `tmp_formula_blockers/`；PG 写操作不由本 spec 直接执行（schema 对齐交用户放行）。

## 第一阶段　后端事务/CAS/判据修复（R1.1 R4 R5 R11）

- [x] 1. R1.1 冲突确认提交修复
  - `routers/formula_settings.py` 的 `resolve()` 端点：逐域 `record_changes` 之后补 `await db.commit()` + `await publish_pending(db)`，与同文件 `save_overrides`/`restore_global`/`apply` 一致。
  - Verify：`test_pending_read_resolve_permissions` 恢复绿（第二次同 revision 提交 → 409）✅；`test_pending_resolve_keep_reports_no_recalc` 仍绿 ✅。

- [x] 2. R4.1/R4.2 报表过期 hash 判据修复
  - `services/report_freshness.py` 的 `row_status()` 返回值改用已经算好的 `stale` 变量，不重新调用 `is_effectively_stale`。
  - 新增 `backend/tests/formula_hub/test_report_freshness_hash.py`（5 用例）。
  - Verify：新测试 5 passed ✅；既有 `test_report_freshness.py` 16 passed / 4 failed（PG schema 漂移 + 签名不匹配，均非本轮引入）。

- [x] 3. R5.1 项目报表删除 CAS 修复
  - `services/formula_settings/legacy_report.py` 的 `delete_row()`：项目行分支改传 `expected_versions=[expected_version] if expected_version is not None else None`。
  - Verify：`test_project_ops` 10 passed ✅；CAS 修复后 `test_legacy_report_paths` 4 条 HEAD 红转绿。

- [x] 4. R11.1 时间线年度过滤
  - `services/formula_timeline_service.py` 的 `_audit_log_events()` SQL 加 `AuditLogEntry.payload["year"].astext == str(year)` 条件。
  - 新增 `backend/tests/formula_hub/test_formula_timeline_year_filter.py`（2 用例）。
  - Verify：新测试 2 passed ✅。

## 第二阶段　前端死入口/角色/只读/注释修复（R3 R6 R7 R8 R9 R10 R1.3）

- [x] 5. R3.1/R3.2 主模板比对注释修复
  - `FormulaManagerDialog.vue`：补 `*/` 关闭未闭合注释块，删除被吞掉的孤立 `}`。`loadMasterDiff()` 恢复为可执行函数。
  - Verify：Python AST 验证在注释外、script 花括号平衡为 0 ✅。vitest 守卫因 Windows 终端 codepage 导致 SFC 中文字符串 babel 解析错误（HEAD 同源），用例收集失败，非本轮引入。

- [x] 6. R6.1 底稿新增公式落库
  - `FormulaManagerDialog.vue` 的 `onFormulaEditSave` `_isNew` 分支：在 `activeReportType` 判断之前，增加 `settingsDomain === 'wp'` 分支，走 `wpFormula.upsert` 保存。
  - Verify：代码审查确认 wp 域新增行有落库路径 ✅。

- [x] 7. R7.1 旧 Excel 导入下线
  - `FormulaManagerDialog.vue` 模板中"📥 Excel导入"按钮注释隐藏（引用 `save_formula_batch` 全仓不存在，运行期必失败）。
  - Verify：按钮不再渲染 ✅。

- [x] 8. R8.1 历史回滚角色对齐
  - `backend/app/routers/formula_audit_log.py` 的 `rollback_formula`：`require_role` 参数加 `"signing_partner"`。
  - Verify：前后端角色集合一致（admin, partner, signing_partner, manager）✅。

- [x] 9. R9.1 三个页面传入只读
  - `TrialBalance.vue`：`:read-only="!canEdit"`。
  - `ReportView.vue`：`:read-only="!canEdit"`。
  - `DisclosureEditor.vue`：`:read-only="!noteEdit.canWrite.value"`。
  - Verify：三个文件均有 `read-only` 绑定 ✅。

- [x] 10. R10.1 调试面板传真实域
  - `FormulaEditDialog.vue` 增加 `scope` prop，`<FormulaDebugPanel>` 绑定 `:scope="props.scope || 'report'"`。
  - `FormulaManagerDialog.vue` 挂 `FormulaEditDialog` 处传入 `:scope="settingsDomain"`。
  - Verify：代码审查确认 scope 透传链完整 ✅。

- [x] 11. R1.3 待确认加载失败显示错误
  - `FormulaPendingSyncDialog.vue`：新增 `loadError` ref，catch 写错误文案；模板加 `<el-alert type="error">`；角标在 `loadError` 时显示警告而非消失。
  - Verify：代码审查确认错误态显示与角标保持 ✅。

## 第三阶段　Schema 对齐操作文档（R2）

- [x] 12. R2.1/R2.2/R2.3 共享库迁移操作文档
  - 生成 `docs/operations/migrate-formula-provenance.md`，含备份、执行、验证、回退步骤。
  - 明确声明：不批量回填 `calc_version`；存量行在下次正常生成/stale 重算时填入。
  - 交付后由用户决定执行时机。
  - Verify：文档文件存在 ✅。

## 第四阶段　回归与收尾

- [x] 13. 回归验证
  - 后端 formula_settings + formula_hub 选集：473 passed / 20 failed。
  - HEAD 基线：468 passed / 16 failed。
  - **本轮新增失败 0 条**：多出的 5 条红来自并发脏改 `wp_formula_eval_service.py`（git diff 确认有未提交修改但不在本 spec 改动范围内）。
  - 本轮修复 HEAD 红：`test_pending_read_resolve_permissions` 转绿（R1.1）+ `test_legacy_report_paths` 4 条转绿（R5.1）。
  - 新增测试 7 条全绿（freshness hash 5 + timeline year 2）。

- [x] 14. INDEX.md 与 memory 更新
  - tasks.md 标记全部完成。
  - INDEX.md 不在本轮提交范围（等推送时统一更新，避免与并发会话竞争共享文件）。

## 改动文件清单

| 文件 | 改动 |
|------|------|
| `backend/app/routers/formula_settings.py` | R1.1 resolve 补 commit + publish_pending |
| `backend/app/services/report_freshness.py` | R4.1 row_status 返回 stale 变量 |
| `backend/app/services/formula_settings/legacy_report.py` | R5.1 delete_row 传 expected_version |
| `backend/app/services/formula_timeline_service.py` | R11.1 审计源按年度过滤 |
| `backend/app/routers/formula_audit_log.py` | R8.1 rollback 加 signing_partner |
| `backend/tests/formula_hub/test_report_freshness_hash.py` | R4.2 新增 5 用例 |
| `backend/tests/formula_hub/test_formula_timeline_year_filter.py` | R11.1 新增 2 用例 |
| `audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue` | R3.1 注释修复 + R6.1 wp 新增落库 + R7.1 旧导入隐藏 + R10.1 scope 透传 |
| `audit-platform/frontend/src/components/formula/FormulaEditDialog.vue` | R10.1 scope prop |
| `audit-platform/frontend/src/components/formula/settings/FormulaPendingSyncDialog.vue` | R1.3 错误态 |
| `audit-platform/frontend/src/views/TrialBalance.vue` | R9.1 read-only |
| `audit-platform/frontend/src/views/ReportView.vue` | R9.1 read-only |
| `audit-platform/frontend/src/views/DisclosureEditor.vue` | R9.1 read-only |
| `docs/operations/migrate-formula-provenance.md` | R2 迁移操作文档 |
| `.kiro/specs/formula-hub-release-blockers/` | spec 三件套 |
