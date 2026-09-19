/**
 * useF4DisclosureSOE — F4 附注披露信息（国企）
 *
 * 对齐源表两个区块：
 * 1. 按账龄披露期末余额/期初余额：账龄行联动审定表F4-1按账龄分类
 *    （期末=F4-1期末审定数、期初=F4-1期初审定数），合计自动求和；
 * 2. 账龄超过1年的重要应付账款：联动长期挂账检查表F4-5
 *    （债权单位名称/期末余额/未偿还原因），支持同步与手工行。
 * 披露文字通过 disclosure:note-text-updated(type='soe') 联动国企附注模块。
 */
import { computed, inject, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { parseNum, calcSubtotal } from './useF4AccPayFormulaEngine'
import {
  F4_ACCOUNT_CODE,
  F4_NOTE_SECTION,
  buildF4SoeSyncPayload,
  f4NoteAgingLabelByRowKey,
} from './f4NoteSectionMap'
import {
  aggregateF4Detail,
  buildF4AgingDefaults,
  computeF4AdjudicationRow,
  migrateF4AdjRows,
  F4_NATURE_DEFAULTS,
} from './useF4Adjudication'
import { extractOverOneYearRows } from './useF4DisclosureListed'
import type { ChecklistResponse } from './useF4FormData'
import {
  PRESET_SEGMENTS,
  useAgingConfig,
  DEFAULT_SUBJECT_PRESETS,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import { overOneYearRowKeys } from './f4AgingModel'

export interface UseF4DisclosureSOEOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  /** 项目适用准则（用于 current_standard 分流）；未提供时按 soe_standalone */
  applicableStandards?: Ref<readonly string[] | null | undefined>
}

export interface F4SOEAgingDisclosureRow {
  rowKey: string
  /** 底稿用词（源 xlsx：1年以内（含1年）/1至2年（含2年）/…） */
  label: string
  /** 附注模版用词（推送到附注模块的行名，如「1至2年」） */
  noteLabel: string
  closingBalance: number
  openingBalance: number
}

export interface F4SOEImportantRow {
  rowId: string
  /** F4-5 行 rowId；空字符串表示手工行 */
  sourceRowId: string
  creditor: string
  amount: number
  reason: string
  linked: boolean
}

interface StoredImportantRow {
  rowId: string
  sourceRowId: string
  creditor: string
  amount: number
  reason: string
}

const IMPORTANT_ROWS_KEY = 'F4-disclosure-soe-important-rows'
const TEXT_KEY = 'F4-disclosure-soe'
const ADJ_AGING_KEY = 'F4-1-adj-aging-rows'
const ADJ_NATURE_KEY = 'F4-1-adj-nature-rows'
const DETAIL_KEY = 'F4-2-rows'
const LONG_OUTSTANDING_KEY = 'F4-5-rows'
const TOLERANCE = 0.005

function generateRowId(): string {
  return `f4ds-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function parseImportantRows(value: string | null | undefined): StoredImportantRow[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: String(raw?.rowId || generateRowId()),
      sourceRowId: String(raw?.sourceRowId ?? ''),
      creditor: String(raw?.creditor ?? ''),
      amount: parseNum(raw?.amount),
      reason: String(raw?.reason ?? ''),
    }))
  } catch {
    return []
  }
}

export function useF4DisclosureSOE(options: UseF4DisclosureSOEOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const importantStored = ref<StoredImportantRow[]>([])
  const disclosureText = ref('')

  // ─── 账龄段（主入口 provide 优先） ──────────────────────────────────────────
  const injectedSegments = inject<Ref<AgingSegment[]> | null>('f4AgingSegments', null)
  const ownAgingConfig = injectedSegments ? null : useAgingConfig(options.projectId, 'F4')
  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    const raw = injectedSegments?.value ?? ownAgingConfig?.segments.value ?? []
    return raw.length
      ? raw
      : (PRESET_SEGMENTS[DEFAULT_SUBJECT_PRESETS.F4 ?? 'THREE_YEAR'] as AgingSegment[])
  })

  watch(
    () => allResponses.value.get(IMPORTANT_ROWS_KEY)?.remark,
    (value) => {
      if (!importantStored.value.length) {
        importantStored.value = parseImportantRows(value)
      }
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(TEXT_KEY)?.remark,
    (value) => { disclosureText.value = value || '' },
    { immediate: true },
  )

  // ─── 按账龄披露：全联动F4-1按账龄分类 ────────────────────────────────────
  const agingRows: ComputedRef<F4SOEAgingDisclosureRow[]> = computed(() => {
    const detail = aggregateF4Detail(allResponses.value.get(DETAIL_KEY)?.remark, segments.value)
    const stored = migrateF4AdjRows(
      allResponses.value.get(ADJ_AGING_KEY)?.remark,
      buildF4AgingDefaults(segments.value),
    )
    return stored.map((row) => {
      const computed_ = computeF4AdjudicationRow(
        row,
        detail.hasData ? detail.aging[row.rowKey] : undefined,
      )
      return {
        rowKey: row.rowKey,
        label: row.label,
        noteLabel: f4NoteAgingLabelByRowKey(row.rowKey, row.label),
        closingBalance: computed_.closingAdjusted,
        openingBalance: computed_.openingAdjusted,
      }
    })
  })

  const agingClosingTotal = computed(() => calcSubtotal(agingRows.value.map((row) => row.closingBalance)))
  const agingOpeningTotal = computed(() => calcSubtotal(agingRows.value.map((row) => row.openingBalance)))

  // 与F4-1按性质合计交叉核对（双口径应一致）
  const natureTotals = computed(() => {
    const detail = aggregateF4Detail(allResponses.value.get(DETAIL_KEY)?.remark)
    const rows = migrateF4AdjRows(allResponses.value.get(ADJ_NATURE_KEY)?.remark, F4_NATURE_DEFAULTS)
      .map((row) => computeF4AdjudicationRow(
        row,
        detail.hasData ? detail.nature[row.rowKey] : undefined,
      ))
    return {
      closing: calcSubtotal(rows.map((row) => row.closingAdjusted)),
      opening: calcSubtotal(rows.map((row) => row.openingAdjusted)),
    }
  })
  const closingMatchesNature = computed(() =>
    Math.abs(agingClosingTotal.value - natureTotals.value.closing) < TOLERANCE,
  )
  const openingMatchesNature = computed(() =>
    Math.abs(agingOpeningTotal.value - natureTotals.value.opening) < TOLERANCE,
  )

  // ─── 账龄超过1年的重要应付账款：联动F4-5 ─────────────────────────────────
  const overOneYearSource = computed(() =>
    extractOverOneYearRows(
      allResponses.value.get(LONG_OUTSTANDING_KEY)?.remark,
      segments.value,
    ),
  )

  const importantRows: ComputedRef<F4SOEImportantRow[]> = computed(() =>
    importantStored.value.map((stored) => {
      const source = stored.sourceRowId
        ? overOneYearSource.value.find((row) => row.rowId === stored.sourceRowId)
        : undefined
      return {
        ...stored,
        creditor: source ? source.creditor : stored.creditor,
        amount: source ? source.amount : stored.amount,
        // 披露表中补充的原因优先；未填写时默认取F4-5挂账原因
        reason: stored.reason || source?.reason || '',
        linked: !!source,
      }
    }),
  )

  const importantTotal = computed(() => calcSubtotal(importantRows.value.map((row) => row.amount)))

  const pendingSyncCount = computed(() => {
    const usedIds = new Set(importantStored.value.map((row) => row.sourceRowId).filter(Boolean))
    return overOneYearSource.value.filter((row) => !usedIds.has(row.rowId)).length
  })

  /**
   * 披露的1年以上账龄合计（来自按账龄区），用于与重要应付账款核对。
   * 「1 年以上」段由 `dayFrom >= 366` 派生（Property 4），**残差行 aging-other 不计入**（Property 5）。
   */
  const overOneYearAgingTotal = computed(() => {
    const keys = new Set(overOneYearRowKeys(segments.value))
    return calcSubtotal(
      agingRows.value
        .filter((row) => keys.has(row.rowKey))
        .map((row) => row.closingBalance),
    )
  })

  function syncFromLongOutstanding(): number {
    if (readonly.value) return 0
    const usedIds = new Set(importantStored.value.map((row) => row.sourceRowId).filter(Boolean))
    const pending = overOneYearSource.value.filter((row) => !usedIds.has(row.rowId))
    for (const source of pending) {
      importantStored.value.push({
        rowId: generateRowId(),
        sourceRowId: source.rowId,
        creditor: source.creditor,
        amount: source.amount,
        // 原因留空表示实时跟随F4-5；用户填写后以披露表为准
        reason: '',
      })
    }
    if (pending.length) persistImportant()
    return pending.length
  }

  function addImportantRow(): void {
    if (readonly.value) return
    importantStored.value.push({
      rowId: generateRowId(),
      sourceRowId: '',
      creditor: '',
      amount: 0,
      reason: '',
    })
    persistImportant()
  }

  function removeImportantRow(rowId: string): void {
    if (readonly.value) return
    const index = importantStored.value.findIndex((row) => row.rowId === rowId)
    if (index === -1) return
    importantStored.value.splice(index, 1)
    persistImportant()
  }

  function updateImportantCell(
    rowId: string,
    field: 'creditor' | 'amount' | 'reason',
    value: unknown,
  ): void {
    if (readonly.value) return
    const row = importantStored.value.find((item) => item.rowId === rowId)
    if (!row) return
    if (field === 'amount') row.amount = parseNum(value as string | number | null | undefined)
    else row[field] = String(value ?? '')
    persistImportant()
  }

  // ─── 持久化 ────────────────────────────────────────────────────────────────
  function setItem(key: string, remark: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark })
    debounceSave()
  }

  function persistImportant(): void {
    setItem(IMPORTANT_ROWS_KEY, JSON.stringify(importantStored.value))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1500)
  }

  function flushSave(): void {
    const items = [IMPORTANT_ROWS_KEY, TEXT_KEY]
      .map((key) => allResponses.value.get(key))
      .filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  function publishNoteTextUpdated(value: string): void {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'F4',
        accountCode: F4_ACCOUNT_CODE,
        projectId: options.projectId.value,
        section: 'soe',
        sectionIds: [F4_NOTE_SECTION.soe],
        text: value,
      },
    }))
  }

  watch(disclosureText, (value) => {
    setItem(TEXT_KEY, value)
    // 联动国企附注模块
    publishNoteTextUpdated(value)
  })

  // ─── 结构化同步到附注（国企 八、37） ──────────────────────────────────────
  const isSyncing = ref(false)

  function buildSyncPayload() {
    return buildF4SoeSyncPayload(
      options.wpId.value,
      options.applicableStandards?.value,
      agingRows.value.map((row) => ({
        rowKey: row.rowKey,
        label: row.label,
        endAmount: row.closingBalance,
        openingAmount: row.openingBalance,
      })),
      importantRows.value.map((row) => ({
        creditor: row.creditor,
        amount: row.amount,
        reason: row.reason,
      })),
      disclosureText.value,
    )
  }

  async function syncToNotes(): Promise<void> {
    if (isSyncing.value || readonly.value) return
    if (!options.projectId.value || !options.wpId.value) {
      ElMessage.warning('缺少项目或底稿标识，无法同步附注')
      return
    }
    isSyncing.value = true
    try {
      const result: any = await api.post(
        `/api/projects/${options.projectId.value}/disclosure-notes/sync-from-workpaper`,
        buildSyncPayload(),
      )
      const data = result?.data ?? result
      ElMessage.success(
        `已同步 ${Number(data?.rows_synced ?? 0)} 行到附注「${F4_NOTE_SECTION.soe} 应付账款」`,
      )
      publishNoteTextUpdated(disclosureText.value)
    } catch {
      ElMessage.warning('同步附注失败，请稍后重试')
    } finally {
      isSyncing.value = false
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    segments,
    agingRows,
    agingClosingTotal,
    agingOpeningTotal,
    natureTotals,
    closingMatchesNature,
    openingMatchesNature,
    importantRows,
    importantTotal,
    overOneYearSource,
    overOneYearAgingTotal,
    pendingSyncCount,
    syncFromLongOutstanding,
    addImportantRow,
    removeImportantRow,
    updateImportantCell,
    disclosureText,
    isSyncing,
    buildSyncPayload,
    syncToNotes,
    noteSection: F4_NOTE_SECTION.soe,
  }
}

export default useF4DisclosureSOE
