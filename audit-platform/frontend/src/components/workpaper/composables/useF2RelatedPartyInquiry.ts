/** F2-65 关联方采购询价分组矩阵状态管理。 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  defaultRelatedPartyInquirySheet,
  emptyInquiryGroup,
  enrichInquiryGroup,
  migrateRelatedPartyInquirySheet,
  applyInquiryOcrToSheet,
  PRICING_JUDGMENTS,
  type InquiryLetterOcrFields,
  type InquiryMonthRow,
  type RelatedPartyInquirySheet,
  type RelatedPartyProductGroup,
} from './useF2RelatedPartyInquiryFormulas'

const ROWS_KEY = 'F2-65-rows'
const NOTE_KEY = 'F2-65-note'

export function useF2RelatedPartyInquiry(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const sheet = ref<RelatedPartyInquirySheet>(defaultRelatedPartyInquirySheet())
  const auditNote = ref('')

  function flushSave(): void {
    const items = [opts.allResponses.value.get(ROWS_KEY), opts.allResponses.value.get(NOTE_KEY)].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateRelatedPartyInquirySheet(parsed)
        sheet.value = migrated
        if (!readonly.value && (Array.isArray(parsed) || JSON.stringify(parsed) !== JSON.stringify(migrated))) {
          opts.allResponses.value.set(ROWS_KEY, {
            item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(migrated),
          })
          if (debounceTimer) clearTimeout(debounceTimer)
          debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 300)
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const groups = computed(() => sheet.value.groups.map(enrichInquiryGroup))
  const abnormalCount = computed(() => groups.value.reduce((sum, group) => sum + group.abnormalCount, 0))
  const filledGroupCount = computed(() => groups.value.filter((group) =>
    group.relatedParty.trim() || group.productName.trim() || group.filledMonthCount > 0,
  ).length)

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(sheet.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function addGroup(): void {
    if (readonly.value) return
    sheet.value = { groups: [...sheet.value.groups, emptyInquiryGroup()] }
    persist()
  }

  function removeGroup(groupId: string): void {
    if (readonly.value || sheet.value.groups.length <= 1) return
    sheet.value = { groups: sheet.value.groups.filter((group) => group.id !== groupId) }
    persist()
  }

  function updateGroup(groupId: string, patch: Partial<RelatedPartyProductGroup>): void {
    if (readonly.value) return
    sheet.value = {
      groups: sheet.value.groups.map((group) => group.id === groupId ? { ...group, ...patch } : group),
    }
    persist()
  }

  function updateRow(groupId: string, rowId: string, patch: Partial<InquiryMonthRow>): void {
    if (readonly.value) return
    sheet.value = {
      groups: sheet.value.groups.map((group) => group.id === groupId
        ? { ...group, rows: group.rows.map((row) => row.id === rowId ? { ...row, ...patch } : row) }
        : group),
    }
    persist()
  }

  function updateComparablePrice(
    groupId: string,
    rowId: string,
    priceIndex: number,
    value: number,
  ): void {
    if (readonly.value) return
    sheet.value = {
      groups: sheet.value.groups.map((group) => group.id === groupId
        ? {
            ...group,
            rows: group.rows.map((row) => {
              if (row.id !== rowId) return row
              const prices = [...row.comparablePrices] as InquiryMonthRow['comparablePrices']
              prices[priceIndex] = value
              return { ...row, comparablePrices: prices }
            }),
          }
        : group),
    }
    persist()
  }

  function applyOcrFields(
    fields: InquiryLetterOcrFields,
    opts?: { overwrite?: boolean; targetGroupId?: string },
  ): void {
    if (readonly.value) return
    sheet.value = applyInquiryOcrToSheet(sheet.value, fields, opts)
    persist()
  }

  watch(auditNote, (value) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: value })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheet,
    groups,
    abnormalCount,
    filledGroupCount,
    auditNote,
    addGroup,
    removeGroup,
    updateGroup,
    updateRow,
    updateComparablePrice,
    applyOcrFields,
    PRICING_JUDGMENTS,
  }
}

export default useF2RelatedPartyInquiry
