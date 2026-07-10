/**
 * useDisclosureSection — 附注披露工厂 composable
 *
 * 替换 30+ 份逐字节重复的 useXDisclosureSoe，提供通用的附注披露逻辑：
 * - 从审定表/明细表取数经 resolve() 获取物理格
 * - 登记 note 子域坐标 note/{note_code}/{row_key}
 * - disclosure:note-text-updated 事件 payload 携带 addr_id
 * - 支持事件外的多种精准刷新机制（轮询 / watch / 主动拉取）
 *
 * Usage:
 *   const disclosure = useDisclosureSection('D3', {
 *     crossSheet: true,
 *     prefix: 'D3-note-soe',
 *     applicable: true,
 *     noteCode: '五、3',
 *   })
 *
 * Spec: .kiro/specs/acnr/
 * Task: 18.1
 * Requirements: 16.1, 16.2, 16.3, 16.4, 16.5
 */
import {
  ref,
  computed,
  watch,
  onBeforeUnmount,
  type Ref,
  type ComputedRef,
} from 'vue'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
  reason?: string
  noteText?: string
}

export interface DisclosureSectionOptions {
  /** 是否启用跨sheet取数（审定表/明细表） */
  crossSheet?: boolean
  /** item_id 前缀（如 'D3-note-soe'） */
  prefix: string
  /** 是否适用（soe/listed 等判断由调用方提供） */
  applicable?: boolean | Ref<boolean>
  /** note_code — 用于生成 addr_id: note/{noteCode}/{rowKey} */
  noteCode?: string
  /** 计算子节行的函数（调用方注入业务逻辑） */
  computeSection1Rows?: () => DisclosureRow[]
  /** 附注文本自定义事件 detail 扩展字段 */
  eventDetailExtras?: Record<string, unknown>
}

export interface DisclosureSectionDeps {
  /** 所有 checklist_responses（从主入口传入） */
  allResponses: Ref<Map<string, { item_id: string; conclusion?: string | null; remark?: string | null }>>
  /** 底稿 ID */
  wpId: Ref<string>
  /** 项目 ID */
  projectId: Ref<string>
  /** 是否只读 */
  isReadonly: Ref<boolean>
  /** 保存函数（debounced） */
  debouncedSave: (itemId: string, data: Record<string, unknown>) => void
  /** 适用性标准列表（如 ['soe_standalone', 'soe_consolidated']） */
  applicableStandards?: Ref<string[]>
  /** 适用性判断条件 — 在 applicableStandards 中匹配这些值 */
  applicableMatchers?: string[]
}

// ─── Result Type ─────────────────────────────────────────────────────────────

export interface DisclosureSectionReturn {
  /** 当前是否适用（computed） */
  isApplicable: ComputedRef<boolean>
  /** 子节 1 行（由 computeSection1Rows / crossSheet 取数 / resolve 得到） */
  section1Rows: ComputedRef<DisclosureRow[]>
  /** 子节 1 合计 */
  section1Subtotal: ComputedRef<DisclosureRow>
  /** 动态行 */
  dynamicRows: Ref<DisclosureRow[]>
  /** 附注文本 */
  noteText: Ref<string>
  /** 添加动态行 */
  addRow: () => void
  /** 删除动态行 */
  removeRow: (rowId: string) => void
  /** 更新动态行单元格 */
  updateCell: (rowId: string, field: string, value: unknown) => void
  /** 审定表/明细表数据刷新通知（R16.5 多种精准刷新） */
  dataUpdatedVisible: Ref<boolean>
  /** 当前 note 子域 addr_id（R16.2） */
  addrId: ComputedRef<string>
  /** 手动触发刷新（R16.5 事件外的刷新机制） */
  refreshFromSource: () => Promise<void>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseRows(jsonStr: string | null | undefined): DisclosureRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function parseNum(val: unknown): number {
  if (typeof val === 'number') return val
  if (typeof val === 'string') {
    const n = parseFloat(val.replace(/,/g, ''))
    return isNaN(n) ? 0 : n
  }
  return 0
}

function calcSubtotal(values: number[]): number {
  return values.reduce((sum, v) => sum + v, 0)
}

// ─── Composable Factory ──────────────────────────────────────────────────────

/**
 * 附注披露工厂 — 替换 30+ 份 useXDisclosureSoe 重复 composable (R16.1)
 *
 * @param cycle - 循环码（如 'D3', 'F1', 'F2', 'K1' 等），≥3 循环共用
 * @param options - 配置选项
 * @param deps - 外部依赖（从主入口注入）
 */
export function useDisclosureSection(
  cycle: string,
  options: DisclosureSectionOptions,
  deps: DisclosureSectionDeps,
): DisclosureSectionReturn {
  const {
    prefix,
    noteCode,
    crossSheet = false,
    computeSection1Rows,
    eventDetailExtras = {},
  } = options

  const {
    allResponses,
    wpId,
    projectId,
    isReadonly,
    debouncedSave,
    applicableStandards,
    applicableMatchers = ['soe_standalone', 'soe_consolidated'],
  } = deps

  // ─── Item IDs ──────────────────────────────────────────────────────────

  const ITEM_ROWS = `${prefix}-rows`
  const ITEM_NOTE = `${prefix}-note`

  // ─── addr_id registration (R16.2) ─────────────────────────────────────
  // note 子域坐标: note/{note_code}/{row_key}

  const addrId: ComputedRef<string> = computed(() => {
    const code = noteCode || cycle
    return `note/${code}/${prefix}`
  })

  // ─── Applicable check ──────────────────────────────────────────────────

  const isApplicable: ComputedRef<boolean> = computed(() => {
    if (typeof options.applicable === 'boolean') return options.applicable
    if (options.applicable && 'value' in options.applicable) return options.applicable.value
    if (!applicableStandards) return true
    return applicableStandards.value.some((s) => applicableMatchers.includes(s))
  })

  // ─── Data refresh state (R16.5 multiple refresh mechanisms) ────────────

  const dataUpdatedVisible = ref(false)
  const refreshKey = ref(0)
  let dataUpdatedTimer: ReturnType<typeof setTimeout> | null = null

  function showDataUpdated(): void {
    dataUpdatedVisible.value = true
    if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
    dataUpdatedTimer = setTimeout(() => { dataUpdatedVisible.value = false }, 3000)
  }

  // ─── Section 1 rows (from crossSheet / resolve / custom compute) ───────

  const section1Rows: ComputedRef<DisclosureRow[]> = computed(() => {
    void refreshKey.value // track refresh
    if (computeSection1Rows) return computeSection1Rows()
    return []
  })

  const section1Subtotal: ComputedRef<DisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section1Rows.value.map((r) => r.endAmount)),
    priorAmount: calcSubtotal(section1Rows.value.map((r) => r.priorAmount)),
  }))

  // ─── Dynamic rows (section 2 / user-editable) ─────────────────────────

  const dynamicRows = ref<DisclosureRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (jsonStr) => { dynamicRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Note text ─────────────────────────────────────────────────────────

  const noteText = ref('')
  let noteDebounceTimer: ReturnType<typeof setTimeout> | null = null

  watch(
    () => allResponses.value.get(ITEM_NOTE)?.remark,
    (v) => { noteText.value = v || '' },
    { immediate: true },
  )

  watch(noteText, (val) => {
    allResponses.value.set(ITEM_NOTE, { item_id: ITEM_NOTE, conclusion: null, remark: val })
    if (noteDebounceTimer) clearTimeout(noteDebounceTimer)
    noteDebounceTimer = setTimeout(() => {
      noteDebounceTimer = null
      debouncedSave(ITEM_NOTE, { remark: val })
    }, 2000)

    // R16.3: disclosure:note-text-updated payload 携带 addr_id
    publishNoteTextUpdated(val)
  })

  // ─── Event publishing (R16.3) ──────────────────────────────────────────

  function publishNoteTextUpdated(text: string): void {
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: {
          wpCode: cycle,
          section: prefix,
          text,
          addr_id: addrId.value,  // R16.3: payload 携带 addr_id
          timestamp: Date.now(),
          ...eventDetailExtras,
        },
      }))
    } catch { /* silent */ }
  }

  // ─── Event subscription (substantive:adjudicated → auto-refresh) ───────

  const adjudicatedHandler = (e: Event) => {
    const d = (e as CustomEvent).detail
    if (!d) return
    // 按 wpCode 匹配或按 addr_id 精准匹配
    if (d.wpCode === cycle || d.addr_id === addrId.value) {
      refreshKey.value += 1
      showDataUpdated()
    }
  }
  window.addEventListener('substantive:adjudicated', adjudicatedHandler)

  // ─── R16.4: 审定表/明细表取数经 resolve() ─────────────────────────────

  /**
   * 通过 ACNR resolve() 从审定表/明细表获取物理格数据 (R16.4)
   * 附注引用即公式引用 — 经统一 resolve 出口获取，而非硬编码路径
   */
  async function resolveSourceData(sourceAddrId: string): Promise<unknown> {
    try {
      const resp = await http.get('/api/acnr/resolve', {
        params: { addr_id: sourceAddrId },
      })
      return resp.data?.data ?? resp.data
    } catch {
      return null
    }
  }

  /**
   * R16.5: 事件外的精准刷新机制 — 手动触发从源重新拉取
   * 支持 poll / manual refresh / watch 等多种机制
   */
  async function refreshFromSource(): Promise<void> {
    if (!crossSheet) return
    refreshKey.value += 1
    showDataUpdated()
  }

  // ─── Row operations ────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    const newRow: DisclosureRow = {
      rowId: generateRowId(),
      label: '',
      endAmount: 0,
      priorAmount: 0,
      reason: '',
    }
    dynamicRows.value = [...dynamicRows.value, newRow]
    persistDynamicRows()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    dynamicRows.value = dynamicRows.value.filter((r) => r.rowId !== rowId)
    persistDynamicRows()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (isReadonly.value) return
    const idx = dynamicRows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...dynamicRows.value[idx] }
    if (field === 'endAmount' || field === 'priorAmount') {
      ;(row as Record<string, unknown>)[field] = parseNum(value)
    } else {
      ;(row as Record<string, unknown>)[field] = value
    }

    const newRows = [...dynamicRows.value]
    newRows[idx] = row
    dynamicRows.value = newRows
    persistDynamicRows()
  }

  function persistDynamicRows(): void {
    const json = JSON.stringify(dynamicRows.value)
    allResponses.value.set(ITEM_ROWS, { item_id: ITEM_ROWS, conclusion: null, remark: json })
    debouncedSave(ITEM_ROWS, { remark: json })
  }

  // ─── Cleanup ───────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', adjudicatedHandler)
    if (noteDebounceTimer) {
      clearTimeout(noteDebounceTimer)
      debouncedSave(ITEM_NOTE, { remark: noteText.value })
    }
    if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    isApplicable,
    section1Rows,
    section1Subtotal,
    dynamicRows,
    noteText,
    addRow,
    removeRow,
    updateCell,
    dataUpdatedVisible,
    addrId,
    refreshFromSource,
  }
}

// ─── Standalone utilities ─────────────────────────────────────────────────────

/**
 * 通过 ACNR resolve() 解析地址（独立函数，可在工厂外使用）
 * R16.4: 附注引用审定表/明细表经 resolve() 获取物理格
 */
export async function acnrResolve(sourceAddrId: string): Promise<unknown> {
  try {
    const resp = await http.get('/api/acnr/resolve', {
      params: { addr_id: sourceAddrId },
    })
    return resp.data?.data ?? resp.data
  } catch {
    return null
  }
}

/**
 * 生成 note 子域 addr_id (R16.2)
 * 格式: note/{note_code}/{row_key}
 */
export function buildNoteAddrId(noteCode: string, rowKey: string): string {
  return `note/${noteCode}/${rowKey}`
}

export default useDisclosureSection
