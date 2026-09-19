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
import { SHEET_SPECS, type ChecklistRow, type ChecklistSheetSpec } from './ipoChecklistSchema'
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
          // 被推成占位披露行（AC 5.7 / Property 22），与投影侧 sheetToRows 全空行跳过同口径。
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
        rows.value.push(newRow(value.trim()))
        recalcDerivedColumns(opts.sheetCode, rows.value, manualLocks.value)
        persist()
      }
    } catch {
      /* 用户取消：不创建行（Property 34） */
    }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
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
    // 派生列手填 → 锁定为手填值，不再重算（Property 15/7）
    if (col?.derived) manualLocks.value.add(`${rowId}:${key}`)
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
  }
}
