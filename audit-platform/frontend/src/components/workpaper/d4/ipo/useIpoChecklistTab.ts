/**
 * D4 IPO 检查表通用行逻辑 —— 四张表共享（列规格驱动、公式联动、rows 项持久化）。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 4/5 · Task 10-13
 *
 * 职责：
 *   - 从 allResponses 的 `{code}-rows` 项载入行（结构化字段对象，非散字段）
 *   - CRUD（新增先 prompt 命名字段；派生列手填锁定）
 *   - recalcDerivedColumns 联动（表内计算：占比/差异/总计）
 *   - persist：写回 allResponses + debounce 触发 `d4:save-items`（复用宿主约定）
 *   - flushPendingSave（切模式前 flush，供 sync bridge flushHtml 调用）
 *
 * 🔴 不持有 OO 字节；双模式回写由组件内联的 useWorkpaperSyncBridge 编排。
 * 🔴 rows 项 item_id 恒为 `{code}-rows`（与后端导入导出锚点一致）。
 * 🔴 初始不预置空占位行（初始行数 0，用户按需新增）；不种子源模板示例行。
 */
import { ref, computed, watch, onBeforeUnmount, inject, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  SHEET_SPECS,
  interSheetFetchPlans,
  type ChecklistRow,
  type ChecklistSheetSpec,
} from './ipoChecklistSchema'
import { recalcDerivedColumns } from './ipoChecklistFormulaEngine'

const DEBOUNCE_MS = 2000

export interface UseIpoChecklistTabOptions {
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28'
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}

export function useIpoChecklistTab(opts: UseIpoChecklistTabOptions) {
  const spec: ChecklistSheetSpec = SHEET_SPECS[opts.sheetCode]
  // 宿主 GtD4OperatingRevenue provide 的 reload（导入后/OO 回写后重载 allResponses）。
  const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)
  const rowsItemId = `${opts.sheetCode}-rows`
  const noteItemId = `${opts.sheetCode}-note`
  const conclusionItemId = `${opts.sheetCode}-conclusion`

  const rows = ref<ChecklistRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  /** 手填锁定的派生列：`${rowId}:${columnKey}`。 */
  const manualLocks = ref<Set<string>>(new Set())
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  function newRow(nameValue: string): ChecklistRow {
    const rowId = `${opts.sheetCode}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
    const row: ChecklistRow = { rowId, seq: rows.value.length + 1 }
    for (const col of spec.columns) {
      if (col.seqColumn) continue
      if (col.key === spec.nameColumnKey) row[col.key] = nameValue
      else if (col.type === 'checkbox') row[col.key] = false
      else if (col.type === 'number' || col.type === 'amount' || col.type === 'percent') row[col.key] = null
      else row[col.key] = ''
    }
    return row
  }

  function loadData(): void {
    const r = opts.allResponses.value.get(rowsItemId)
    if (r?.remark) {
      try {
        const parsed = JSON.parse(r.remark)
        if (Array.isArray(parsed)) {
          // 归一：确保每行有 rowId/seq，缺失补上
          const normalized: ChecklistRow[] = parsed.map((row: any, i: number) => ({
            ...row,
            rowId: row.rowId ?? `${opts.sheetCode}-legacy-${i}`,
            seq: Number(row.seq) || i + 1,
          }))
          // 🔴 过滤纯占位空行（除 seqColumn/rowId/seq 外所有列皆空）——防源模板占位序号
          // 被推成占位披露行（AC 5.7 / Property 22）。这是**表格视图渲染侧**的过滤；
          // OO 侧的行身份由后端 provider 按 rowId 判定（缺 rowId 直接拒绝），两者各管一段。
          const dataKeys = spec.columns.filter((c) => !c.seqColumn).map((c) => c.key)
          rows.value = normalized.filter((row) =>
            dataKeys.some((k) => {
              const v = row[k]
              return v != null && String(v).trim() !== '' && v !== false
            }),
          )
          // seq 重排为连续 1..N（过滤后不留空洞）
          rows.value.forEach((row, i) => (row.seq = i + 1))
          recalcDerivedColumns(opts.sheetCode, rows.value, manualLocks.value)
          return
        }
      } catch {
        /* 解析失败保留空态，不吞成脏数据 */
      }
    }
    rows.value = []
  }

  function loadNote(): void {
    auditNote.value = opts.allResponses.value.get(noteItemId)?.remark || ''
    auditConclusion.value = opts.allResponses.value.get(conclusionItemId)?.remark || ''
  }

  // Excel 侧回写后 allResponses 整体替换 → 跟随刷新（否则切回结构化视图看到旧值）。
  watch(() => opts.allResponses.value.get(rowsItemId)?.remark, loadData, { immediate: true })
  watch(
    () => [
      opts.allResponses.value.get(noteItemId)?.remark,
      opts.allResponses.value.get(conclusionItemId)?.remark,
    ],
    loadNote,
    { immediate: true },
  )

  function _dispatchSave(): void {
    const keys = [rowsItemId, noteItemId, conclusionItemId]
    window.dispatchEvent(
      new CustomEvent('d4:save-items', {
        detail: { items: keys.map((k) => opts.allResponses.value.get(k)).filter(Boolean) },
      }),
    )
  }

  function _writeItems(): void {
    opts.allResponses.value.set(rowsItemId, {
      item_id: rowsItemId,
      conclusion: null,
      remark: JSON.stringify(rows.value),
    })
    opts.allResponses.value.set(noteItemId, { item_id: noteItemId, conclusion: null, remark: auditNote.value })
    opts.allResponses.value.set(conclusionItemId, {
      item_id: conclusionItemId,
      conclusion: null,
      remark: auditConclusion.value,
    })
  }

  function persist(): void {
    _writeItems()
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      _dispatchSave()
    }, DEBOUNCE_MS)
  }

  /** 切模式前 flush：立即落库 debounce 中的编辑（防投影旧值）。 */
  function flushPendingSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    _writeItems()
    _dispatchSave()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    const nameLabel = spec.columns.find((c) => c.key === spec.nameColumnKey)?.label ?? '名称'
    try {
      const { value } = await ElMessageBox.prompt(`请输入${nameLabel}`, `添加记录`, {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '不能为空',
      })
      if (value?.trim()) {
        const created = newRow(value.trim())
        rows.value.push(created)
        recalcDerivedColumns(opts.sheetCode, rows.value, manualLocks.value)
        persist()
        // AC 3.4「表间提取首次进入即预填」：新增行落定后按名称自动取数（只填空列）。
        // 不 await —— 行已可见可编辑，取数是后续补值；失败只记 fetchError 不回滚行。
        void refreshInterSheet({ rowIds: [String(created.rowId)] })
      }
    } catch {
      /* 用户取消：不创建行（Property 34） */
    }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    // 删除行时清掉它遗留的手填锁（design「派生列手填锁定」：删除该行即解锁），
    // 防 manualLocks 随删行累积成僵尸键。
    for (const k of [...manualLocks.value]) {
      if (k.startsWith(`${rowId}:`)) manualLocks.value.delete(k)
    }
    // 重排 seq
    rows.value.forEach((r, i) => (r.seq = i + 1))
    recalcDerivedColumns(opts.sheetCode, rows.value, manualLocks.value)
    persist()
  }

  function updateCell(rowId: string, key: string, value: unknown): void {
    if (opts.isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const col = spec.columns.find((c) => c.key === key)
    // 派生列：手填 → 锁定为手填值不再重算（Property 15/7）；清空手填 → 解锁回落预设重算
    // （Property 15 后半句「清空手填即解锁回落预设重算」/ design「派生列手填锁定」小节）。
    // 🔴 只 add 不 delete 会让用户清空后该列永久停算，即使依赖列变化也不再更新。
    if (col?.derived) {
      const lockKey = `${rowId}:${key}`
      const isBlank = value == null || value === '' || (typeof value === 'string' && value.trim() === '')
      if (isBlank) manualLocks.value.delete(lockKey)
      else manualLocks.value.add(lockKey)
    }
    row[key] = value as never
    recalcDerivedColumns(opts.sheetCode, rows.value, manualLocks.value)
    persist()
  }

  function updateNote(v: string): void {
    if (opts.isReadonly.value) return
    auditNote.value = v
    persist()
  }
  function updateConclusion(v: string): void {
    if (opts.isReadonly.value) return
    auditConclusion.value = v
    persist()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushPendingSave()
    }
  })

  const columns = computed(() => spec.columns)

  // ═══════════════════════════════════════════════════════════════════════
  // 表间提取（inter_sheet）：按 IPO_FORMULA_PRESETS 的 resolver 声明真实取数回填
  //
  // 🔴 这一段补的是 AC 3.4「表间提取首次进入即预填」的落地：此前 `IPO_FORMULA_PRESETS`
  //    只**声明**了 resolver 名（且守卫仅校验名字存在于后端注册表），运行时从无任何调用
  //    ⇒ 金额列永远是 `newRow` 里硬置的 null，「不填也有值」从未发生。
  // ═══════════════════════════════════════════════════════════════════════

  /** 取数进行中（供工具栏按钮 loading）。 */
  const fetching = ref(false)
  /** 最近一次取数的失败原因（空串 = 无失败）。fail-visible：不吞成静默。 */
  const fetchError = ref('')

  const plans = interSheetFetchPlans(opts.sheetCode)
  /** 审计年度由宿主 provide（禁在此硬编码「当前年-1」）。 */
  const auditYear = inject<Ref<number> | number | null>('d4AuditYear', null)

  function resolvedYear(): number | null {
    const y = auditYear && typeof auditYear === 'object' ? (auditYear as Ref<number>).value : auditYear
    const n = Number(y)
    return Number.isFinite(n) && n > 0 ? n : null
  }

  function isBlankValue(v: unknown): boolean {
    return v == null || v === '' || (typeof v === 'string' && v.trim() === '')
  }

  /**
   * 按声明的 resolver 取数并回填 inter_sheet 列。
   *
   * @param overwrite `false`（默认，新增行后自动调用）= 只填空列，不动用户已录入的值；
   *                  `true`（工具栏「刷新取数」）= 以账面值覆盖。
   * @param rowIds 限定行（缺省 = 全部行）。
   *
   * 约定：
   * - resolver 返回 `null` 的字段**保持空**，绝不写 0（0 会被误读成「已核对为零」）；
   * - 同 `(resolver, 名称)` 只发一次请求（多行同名 / 一 resolver 供多列都不重复打）；
   * - 失败不抛、不清空已有值，只记 `fetchError` 由组件显式展示。
   */
  async function refreshInterSheet(
    { overwrite = false, rowIds }: { overwrite?: boolean; rowIds?: readonly string[] } = {},
  ): Promise<{ filled: number; failed: number }> {
    fetchError.value = ''
    if (opts.isReadonly.value || plans.length === 0) return { filled: 0, failed: 0 }
    const year = resolvedYear()
    if (year == null) {
      fetchError.value = '缺少审计年度，无法取数'
      return { filled: 0, failed: 0 }
    }
    const targetRows = rowIds
      ? rows.value.filter((r) => rowIds.includes(String(r.rowId)))
      : rows.value
    if (targetRows.length === 0) return { filled: 0, failed: 0 }

    fetching.value = true
    let filled = 0
    let failed = 0
    // 同 (resolver, 名称) 的返回体复用：避免多行同名重复打后端，也避开 http.ts
    // 去重层对同 URL 在飞请求的 abort。
    const cache = new Map<string, Record<string, unknown> | null>()
    try {
      for (const plan of plans) {
        for (const row of targetRows) {
          const name = String(row[plan.nameColumnKey] ?? '').trim()
          if (!name) continue // 没名称无从匹配（resolver 也会短路），不发请求
          const cacheKey = `${plan.resolver}::${name}`
          let payload = cache.get(cacheKey)
          if (payload === undefined) {
            try {
              payload = (await api.get(
                `/api/projects/${opts.projectId.value}/auto-data/${plan.resolver}`,
                { params: { year, customer_name: name }, _silent: true } as never,
              )) as Record<string, unknown>
              // resolver 内部异常时平台返 `_error: true`（非抛异常）——按失败计，不回填。
              if (payload && (payload as { _error?: boolean })._error) {
                failed += 1
                payload = null
              }
            } catch {
              failed += 1
              payload = null
            }
            cache.set(cacheKey, payload ?? null)
          }
          if (!payload) continue
          for (const t of plan.targets) {
            const raw = payload[t.resolverField]
            if (raw == null) continue // 账面无匹配 → 保持空，绝不写 0
            if (!overwrite && !isBlankValue(row[t.columnKey])) continue // 不覆盖已录入
            const n = Number(raw)
            if (!Number.isFinite(n)) continue
            row[t.columnKey] = Number(n.toFixed(t.precision))
            filled += 1
          }
        }
      }
    } finally {
      fetching.value = false
    }
    if (failed > 0 && filled === 0) {
      fetchError.value = `取数失败 ${failed} 项（已保留原值，未写入 0）`
    }
    if (filled > 0) {
      // 表间提取值变了 → 依赖它的表内派生列（占比/差异）跟着重算，再落盘。
      recalcDerivedColumns(opts.sheetCode, rows.value, manualLocks.value)
      persist()
    }
    return { filled, failed }
  }

  /** 导入成功 / OO 回写后重载宿主 allResponses（AC 4.2：表格视图立即显示导入的行）。 */
  async function reloadHost(): Promise<void> {
    if (reloadWorkpaperData) await reloadWorkpaperData()
  }

  return {
    spec,
    columns,
    rows,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateCell,
    updateNote,
    updateConclusion,
    persist,
    flushPendingSave,
    reloadHost,
    // 表间提取（inter_sheet）
    refreshInterSheet,
    fetching,
    fetchError,
    /** 该表是否有表间提取列（无则组件不渲染「刷新取数」按钮）。 */
    hasInterSheet: computed(() => plans.length > 0),
  }
}
