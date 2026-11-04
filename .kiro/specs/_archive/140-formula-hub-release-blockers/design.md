# 设计：公式管理阻断缺陷收口（formula-hub-release-blockers）

> 本 spec 只修当前工作树中"界面返回成功但数据实际未落库/已过期/必失败"的阻断级缺陷。
> 不引入新迁移、不改公式求值内核、不新增域。

## §1　R1 冲突确认事务完整性

### 1.1 后端修复

文件 `backend/app/routers/formula_settings.py`，函数 `resolve()`。

当前代码在 `_run(db, ...)` 之后直接 return。`_run` 只做了 try/except 不做 commit。
同一文件的 `save_overrides` / `restore_global` / `apply` 都经由 `_emit(db, result, ...)` 调用
`record_changes → db.commit() → publish_pending(db)`。

修法：在 `resolve()` 最后加：

```python
await _emit(db, {"events": events}, domain=events[0]["domain"] if events else "report", source="project_resolve")
```

其中 `events = result.get("events") or []`。原代码已逐域 `record_changes`，只需把
commit 和 publish_pending 补上。不能直接用 `_emit` 因为 events 按域拆了——
改为在 for 循环之后一次 `db.commit()` + `publish_pending(db)`。

### 1.2 前端错误态

文件 `audit-platform/frontend/src/components/formula/settings/FormulaPendingSyncDialog.vue`，
约行 204 的 `catch` 块。

当前：
```typescript
} catch {
  if (seq === loadSeq) items.value = []
}
```

改为：
```typescript
} catch (e: any) {
  if (seq === loadSeq) {
    items.value = []
    loadError.value = formulaErrorText(e, '待确认事项加载失败')
  }
}
```

模板中在 `v-loading` 之后加 `<el-alert v-if="loadError" ... />`，当 `items` 为空
且 `loadError` 非空时展示错误而非隐藏角标。

## §2　R2 共享库 schema 对齐

### 2.1 执行策略

不在本 spec 的代码改动范围——写一份操作步骤交用户放行，由用户或 DBA 执行：

1. `pg_dump -Fc -t financial_report -t formula_push_state > backup_$(date +%Y%m%d).dump`
2. `GT_BOOTSTRAP_DONE=1` 之下启动后端（不跑迁移），手动：
   ```python
   from app.core.migration_runner import MigrationRunner
   runner = MigrationRunner(DATABASE_URL)
   await runner.run_pending()   # V235~V251 按顺序
   ```
3. 核验 `inspect_readiness().is_complete == True`。
4. **不**批量回填 `calc_version`——存量行在下次项目报表生成/stale 重算时自动填入。

### 2.2 V246 与 V251 幂等

两份 DDL 都用 `CREATE TABLE IF NOT EXISTS report_generation_run` +
`ALTER TABLE financial_report ADD COLUMN IF NOT EXISTS`，先到先建，后到跳过。
V246 另有 `consol_artifact` 和更多 `report_generation_run` 列（ORM 也有）。
因此二者**按磁盘版本号顺序执行即可**。

## §3　R3 主模板比对修复

文件 `audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue`。

根因是第 ~795 行附近有一段未闭合的 `/**` 注释块：

```javascript
// masterDiff 筛选/标签/颜色已移到 FormulaGlobalScopeDialog 内部
}
```

这行紧接上一个函数的闭括号，后面是：

```javascript
async function loadMasterDiff() {
```

`/**` 在更靠前几行（`onlyFormula` 注释），一直吞到这里。

修法：找到未闭合的 `/**`，在它应结束的位置加 `*/`，使 `loadMasterDiff` 恢复为可执行函数。

守卫 `formulaManagerMasterDiff.spec.ts` 断言 `typeof state(w).loadMasterDiff === 'function'`，修复后即通过。

## §4　R4 报表过期判据修复

文件 `backend/app/services/report_freshness.py`，函数 `row_status()`。

当前代码（约行 87-108）：

```python
stale = is_effectively_stale(row, effective_formula)
if not stale and definition_hash is not None:
    provenance = _get(row, "provenance")
    if isinstance(provenance, Mapping):
        applied = provenance.get("applied_attempt")
        if isinstance(applied, Mapping):
            old_hash = applied.get("definition_hash")
            if old_hash and old_hash != definition_hash:
                stale = True
return {
    "is_stale": is_effectively_stale(row, effective_formula),  # ← BUG：重新计算，丢了 hash 分支
    ...
}
```

修法：返回值改为 `"is_stale": stale`。

新增测试：构造 `row(calc_version=CALC_VERSION, formula_used=公式, provenance={applied_attempt:{definition_hash:"old"}})`，
调用 `row_status(row, 公式, "new")`，断言 `is_stale=True`。

## §5　R5 项目报表删除 CAS 修复

文件 `backend/app/services/formula_settings/legacy_report.py`，函数 `delete_row()`。

当前 `restore_global(..., expected_versions=None)`。

改为 `restore_global(..., expected_versions=[expected_version] if expected_version is not None else None)`。

`restore_global` 接受 `expected_versions: list[int] | None`，传单元素列表即可对应
单个 `slot_key`。

## §6　R6 底稿新增公式落库

文件 `audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue`，
函数 `onFormulaEditSave()`，`_isNew` 分支。

当前只在 `activeReportType` 存在时 POST，否则无条件 return。

改为在 return 前增加：

```typescript
if (dispatch === 'wp') {
  const targetLocation = gate.location
  if (!targetLocation) { ElMessage.warning('缺少底稿位置'); return }
  const saved = await api.put(wpFormula.upsert(targetLocation.wpId), {
    sheet_name: row.sheet_name || targetLocation.display.sheetName || '',
    target_cell: data.target_cell || row.target_cell || row.row_code || '',
    expression: data.formula || '',
    year: targetLocation.fiscalYear,
    template_type: fmTemplateType.value,
    category: data.category,
    description: data.description,
  })
  row._isNew = false
  showFormulaEdit.value = false
  ElMessage.success('底稿公式已保存')
  emit('saved')
  return
}
```

## §7　R7 旧 Excel 导入下线

文件 `audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue`，
模板中"📥 Excel导入"按钮行。

改为 `v-if="false"` 隐藏（完全删除按钮也可），或替换为调用已有的
`FormulaImportExportDropdown mode="preset"` / `mode="package"`。

## §8　R8 历史回滚角色对齐

选项 A（推荐）：后端 `formula_audit_log.py:rollback_formula` 的 `require_role` 加入
`"signing_partner"`——因为产品侧 signing_partner 是 partner 的细分，理应有权回滚。

选项 B：前端 `ROLLBACK_ROLES` 删去 `'signing_partner'`。

本 spec 采用选项 A。现有守卫 `formulaHistoryRollbackGate.spec.ts` 的
`extraInFe.filter(r => r !== 'signing_partner')` 逻辑在 A 实施后也能通过
（后端集合含 signing_partner 时前端多出项为空集）。

## §9　R9 只读页面能力传递

三个页面分别在 `<FormulaManagerDialog>` 上补 `:read-only="!canEdit"` 或等价逻辑：

- `TrialBalance.vue`：读项目权限或底稿编辑能力。
- `ReportView.vue`：同上。
- `DisclosureEditor.vue`：同上。

`FormulaManagerDialog` 已有 `readOnly` prop 和 `formulaReadOnly` computed。

## §10　R10 调试面板作用域

文件 `audit-platform/frontend/src/components/formula/FormulaEditDialog.vue`，约行 247：

```vue
<FormulaDebugPanel ... scope="report" />
```

改为：

```vue
<FormulaDebugPanel ... :scope="props.scope || 'report'" />
```

`FormulaEditDialog` 当前没有 scope prop，需从宿主 `FormulaManagerDialog` 透传。

## §11　R11 时间线年度过滤

文件 `backend/app/services/formula_timeline_service.py`，函数 `_audit_log_events()`。

当前 WHERE 只有 `action_type == 'formula.changed'` 和 `payload->>'project_id'`。

加：

```python
AuditLogEntry.payload["year"].astext == str(year),
```

不影响没有 `year` 字段的旧条目——旧条目 `payload->>'year'` 为 NULL，
`NULL == '2025'` 在 SQL 里是 UNKNOWN，被排除，符合预期
（旧条目在旧格式的历史页展示，不进时间线）。

## §12　变异与验证

每项修复必须至少一条变异或回归断言：

| 需求 | 验证方式 |
|------|---------|
| R1.1 | `test_pending_read_resolve_permissions` 恢复绿 |
| R1.3 | 新增前端测试断言 `loadError` 非空 |
| R2 | 操作步骤交付，由用户确认 |
| R3 | `formulaManagerMasterDiff.spec.ts` 恢复绿 |
| R4 | 新增后端单测 |
| R5 | 在既有 CAS 测试中增加项目行删除分支 |
| R6 | 新增前端测试 |
| R7 | 旧按钮不可见 |
| R8 | 守卫通过（后端加 signing_partner） |
| R9 | 三个页面传入 read-only |
| R10 | 调试面板接收真实 scope |
| R11 | 新增后端单测 |
