# 设计文档：审计平台缺陷修复与业务优化

## 设计原则

1. **最小改动**：每个修复只改动必要的代码，不引入新的依赖或架构变化
2. **向后兼容**：所有修复不破坏现有 API 和组件接口
3. **业务优先**：P0 业务缺陷（B1-B9）优先于技术 Bug，因为直接影响审计质量
4. **验证驱动**：每个修复后运行 vue-tsc + vite build 确认零错误

---

## Sprint 1：业务逻辑缺陷修复（~3天）

### D1：试算平衡表 AJE/RJE 自动汇总 [B1]

**问题**：试算平衡表（tbSummaryRows）的 AJE/RJE 借贷列是手动输入的 `el-input-number`，与调整分录页面的数字独立，会产生不一致。

**方案**：
- 后端新增 `GET /api/projects/{pid}/trial-balance/summary-with-adjustments?year=` 接口
- 返回按报表行次汇总的试算平衡表，AJE/RJE 列从 adjustments 表自动计算
- 前端 `loadTbSummary()` 改为调用新接口，移除手动编辑功能
- 保留"保存"按钮用于保存用户对行次的备注（非金额）

```python
# 新接口返回结构
{
  "rows": [
    {
      "row_code": "BS-001",
      "row_name": "货币资金",
      "unadjusted": 5500000,
      "aje_dr": 0,      # 从 adjustments 自动汇总
      "aje_cr": 150000, # 从 adjustments 自动汇总
      "rcl_dr": 0,
      "rcl_cr": 0,
      "audited": 5350000
    }
  ]
}
```

### D2：底稿上传后自动触发解析 [B2]

**问题**：`doUpload()` 上传成功后没有调用 parse 接口，导致 `parsed_data` 不更新，五环联动断裂。

**方案**：
```ts
// WorkpaperList.vue doUpload() 成功后追加
if (uploadResult.success) {
  // 自动触发解析
  await parseWorkpaper(projectId.value, selectedWp.value.id)
  ElMessage.success('上传成功，正在解析底稿数据...')
  // 刷新底稿状态
  await fetchData()
}
```

### D3：借贷平衡指示器修正 [B3]

**问题**：`isBalanced` 检查"审定数合计接近0"，这对资产负债表科目不成立。

**方案**：
```ts
const isBalanced = computed(() => {
  // 正确逻辑：资产类合计 = 负债类合计 + 权益类合计
  const assetTotal = rows.value
    .filter(r => r.account_category === 'asset')
    .reduce((s, r) => s + num(r.audited_amount), 0)
  const liabEquityTotal = rows.value
    .filter(r => ['liability', 'equity'].includes(r.account_category || ''))
    .reduce((s, r) => s + num(r.audited_amount), 0)
  // 利润表科目（收入-成本-费用）净额应等于净利润
  return Math.abs(assetTotal - liabEquityTotal) < 1  // 允许1元误差
})
```

### D4：复核通过时检查未解决批注 [B4]

**问题**：`onReviewPass()` 直接调用复核通过接口，没有检查 `unresolvedCount`。

**方案**：
```ts
async function onReviewPass() {
  if (unresolvedCount.value > 0) {
    await ElMessageBox.confirm(
      `当前有 ${unresolvedCount.value} 条未解决的复核意见，确定通过复核吗？`,
      '复核确认',
      { type: 'warning', confirmButtonText: '确认通过', cancelButtonText: '取消' }
    )
  }
  // 继续执行复核通过逻辑
}
```

### D5：看板视图核心交互实现 [B5]

**问题**：`onKanbanSelect` 和 `onKanbanAssign` 都是 TODO。

**方案**：
- `onKanbanSelect`：切换到列表视图，自动展开并选中对应底稿节点
- `onKanbanAssign`：弹出分配弹窗（复用现有的分配逻辑）

### D6：批量复核跳过提示 [B6]

**方案**：
```ts
async function batchReview(status: string) {
  const eligible = selectedRows.value.filter(r => r.review_status === 'pending_review')
  const skipped = selectedRows.value.length - eligible.length
  if (skipped > 0) {
    ElMessage.warning(`已跳过 ${skipped} 条非待复核状态的分录`)
  }
  if (!eligible.length) { ElMessage.warning('没有可操作的分录'); return }
  // 继续处理 eligible
}
```

### D7：调整分录科目显示报表行次 [B7]

**方案**：在科目下拉选项里追加报表行次信息：
```html
<el-option v-for="opt in accountOptions" :key="opt.code"
  :label="`${opt.code} ${opt.name}`" :value="opt.code">
  <span>{{ opt.code }} {{ opt.name }}</span>
  <span v-if="opt.report_line" style="float:right;color:#999;font-size:11px">
    → {{ opt.report_line }}
  </span>
</el-option>
```
后端 `get_account_dropdown` 接口返回时补充 `report_line` 字段。

### D8：科目编码链接直接打开底稿编辑器 [B8]

**问题**：`onOpenWorkpaper` 跳转到底稿列表页（`/workpapers?highlight=xxx`），审计员还需要再找一次。

**方案**：
```ts
function onOpenWorkpaper(accountCode: string) {
  const mapping = getLinkedWp(accountCode)
  if (!mapping) return
  // 直接跳转到底稿编辑器
  const wp = wpList.value.find(w => w.wp_code === mapping.wp_code)
  if (wp) {
    router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId: wp.id } })
  } else {
    // 底稿未生成时，跳到列表页并高亮
    router.push({ path: `/projects/${projectId.value}/workpapers`, query: { highlight: mapping.wp_code } })
  }
}
```

### D9：CommentThread 批注与复核流程强制联动 [B9]

**问题**：`hasBlocking` 检查了 `unresolvedCount > 0`（不能提交复核），但复核通过时没有检查。

**方案**：
```ts
// WorkpaperList.vue onReviewPass()
async function onReviewPass() {
  // 强制检查：所有批注必须已解决
  if (unresolvedCount.value > 0) {
    try {
      await ElMessageBox.confirm(
        `当前有 ${unresolvedCount.value} 条未解决的复核意见，建议先处理后再通过复核。确定强制通过吗？`,
        '复核确认',
        {
          type: 'warning',
          confirmButtonText: '强制通过',
          cancelButtonText: '返回处理',
          confirmButtonClass: 'el-button--danger',
        }
      )
    } catch {
      return  // 用户选择返回处理
    }
  }
  // 继续执行复核通过逻辑
}
```

---

## Sprint 2：P0/P1 技术 Bug 修复（~3天）

### D10：escapeRegex 修复 [P0.1]

```ts
// utils/useTableSearch.ts
function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')  // 标准正则转义
}
```

### D11：migration_runner 多语句分割 [P0.2]

```python
async def _apply_migration(self, mig: MigrationFile) -> None:
    sql_content = mig.path.read_text(encoding="utf-8")
    # 按分号分割，过滤空语句，逐条执行
    statements = [s.strip() for s in sql_content.split(';') if s.strip()]
    async with self._engine.begin() as conn:
        for stmt in statements:
            if stmt:
                await conn.execute(text(stmt))
        # 记录版本
        await conn.execute(text("INSERT INTO schema_version ..."), {...})
```

### D12：bulk_execute savepoint 隔离 [P0.3]

```python
for uid, row in rows.items():
    try:
        async with db.begin_nested() as sp:  # savepoint
            await action_fn(db, row)
        succeeded.append(str(uid))
    except Exception as exc:
        await sp.rollback()
        failed.append({"id": str(uid), "error": str(exc)})
```

### D13：ReportFormulaParser 返回值修复 [P0.4]

```python
async def execute(self, formula, row_cache):
    ...
    try:
        return _safe_eval_expr(expression)
    except Exception as e:
        logger.warning("Formula eval error: %s", e)
        return Decimal("0")  # 明确返回 0，不隐式返回 None
```

### D14：v-permission 内存泄漏修复 [P1.1]

```ts
// directives/permission.ts
import { useAuthStore } from '@/stores/auth'
import { ROLE_PERMISSIONS } from '@/composables/usePermission'

// 模块级单例，不在指令里每次创建
function checkPermissionDirect(el: HTMLElement, binding: DirectiveBinding) {
  const authStore = useAuthStore()
  const role = authStore.user?.role ?? ''
  const value = binding.value
  // 直接用 role 判断，不调用 usePermission()
  const hasPermission = role === 'admin' || 
    (Array.isArray(value) ? value.some(p => ROLE_PERMISSIONS[role]?.includes(p)) 
                          : ROLE_PERMISSIONS[role]?.includes(value))
  el.style.display = hasPermission ? '' : 'none'
}
```

### D15：router beforeEach 权限检查修复 [P1.2]

```ts
// router/index.ts
router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const permissionRequired = to.meta.permission
  if (permissionRequired && authStore.isAuthenticated) {
    const role = authStore.user?.role ?? ''
    // 直接访问 role，不调用 usePermission()
    const hasPermission = role === 'admin' || 
      ROLE_PERMISSIONS[role]?.includes(permissionRequired)
    if (!hasPermission) { ... }
  }
})
```

### D16：main.ts 图标注册修复 [P1.3]

```ts
// main.ts — 删除全量注册，让 unplugin-vue-components 自动处理
// 删除以下代码：
// for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
//   app.component(key, component)
// }
```

### D17：调整分录编号并发修复 [P1.4]

```python
# 使用 advisory lock 防并发竞争
async def _next_adjustment_no(self, project_id, year, adj_type):
    prefix = "AJE" if adj_type == AdjustmentType.aje else "RJE"
    lock_key = hash(f"{project_id}:{year}:{prefix}") % (2**31)
    await self.db.execute(text(f"SELECT pg_advisory_xact_lock({lock_key})"))
    # 然后查询计数
    count = (await self.db.execute(...)).scalar() or 0
    return f"{prefix}-{count + 1:03d}"
```

### D18-D22：其余 P1 修复

- **D18** `http.ts` pendingMap 泄漏：在 `removePending` 里加超时清理，或在 `addPending` 里设置 5 分钟自动清理
- **D19** `EventBus` 僵尸队列：`QueueFull` 时调用 `self.remove_sse_queue(queue)`
- **D20** `shortcuts.ts` 输入框检查：`handleKeydown` 开头加 `if (isInputFocused(event)) return`
- **D21** `useProjectStore/dictStore` 改用 apiProxy：替换直接 import http 为 `import { api } from '@/services/apiProxy'`
- **D22** `useAutoSave` 改用 sessionStorage：`localStorage` → `sessionStorage`

---

## Sprint 3：P2 优化项（~4天）

### D23：数据同步状态可视化 [P2.1]

在 `GtPageHeader` 的 actions 区域右侧加一个轻量的同步状态指示器：
```vue
<!-- GtPageHeader 内部 -->
<div class="gt-page-header__sync-status" v-if="showSyncStatus">
  <span v-if="syncStatus === 'syncing'" class="gt-sync-dot gt-sync-dot--syncing">⏳</span>
  <span v-else-if="syncStatus === 'stale'" class="gt-sync-dot gt-sync-dot--stale" :title="lastSyncTime">🕐</span>
  <span v-else class="gt-sync-dot gt-sync-dot--ok">✓</span>
</div>
```
通过 `eventBus.on('sse:sync-event')` 更新状态，`eventBus.on('sse:sync-failed')` 标记为 stale。

### D24：试算表双向导航 [P2.2]

在试算表科目行的右键菜单里加"查看相关分录"：
```ts
function onTbCtxViewAdj() {
  const row = tbCtx.contextMenu.rowData
  if (!row?.standard_account_code) return
  router.push({
    path: `/projects/${projectId.value}/adjustments`,
    query: { year: String(year.value), account: row.standard_account_code }
  })
}
```
调整分录页面接收 `account` query 参数，自动过滤显示该科目的分录。

### D25：底稿识别确认步骤 [P2.3]

上传底稿后，在弹窗里增加第二步"确认识别结果"：
```
步骤1：上传文件 → 步骤2：确认识别数据 → 步骤3：完成
```
步骤2 显示系统识别出的关键数字（审定数、未审数、差异），用户确认后才写入 parsed_data。

### D26-D32：其余 P2 优化

- **D26** `list_entries` N+1 优化：批量查询所有 entry_group_id 的 Adjustment 和 AdjustmentEntry
- **D27** `disclosure_engine` 预加载上年附注：在 `_preload_data_for_notes` 里一次性加载
- **D28** `_build_table_data` 合计为 0 显示 0：移除 `if total != 0` 判断
- **D29** `syncFromRoute` 非阻塞：移除 router beforeEach 里的 await，改为后台更新
- **D30** `router_registry.py` 删除重复调用
- **D31** `GtPageHeader` backMode prop
- **D32** `useDictStore` 加 TTL

---

## Sprint 4：P3 小优化 + 收尾（~2天）

- **D33** `GtStatusTag` 加 size prop
- **D34** `GtEditableTable` lazyEdit 条件初始化
- **D35** `operationHistory.undo()` 超时保护
- **D36** `confirm.ts` HTML 转义
- **D37** `yearOptions` 动态计算
- **D38** `developing` 路由跳转专门页面
- **D39** `bcrypt rounds` 配置化
- **D40** `DefaultLayout.vue` watch await
- **D41** `deps.py` 死代码清理
- **D42** `useExcelIO.parseFile` 降级逻辑
- **D43** `config.py` EVENT_DEBOUNCE_MS
- **D44** 全量构建验证 + git commit + push + 合并到 master
