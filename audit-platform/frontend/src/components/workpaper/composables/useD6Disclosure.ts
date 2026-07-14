/**
 * useD6Disclosure — 附注披露（上市5子节163公式 / 国企3子节）
 *
 * 上市公司版5子节：
 *   (1) 分类（项目/期末(账面余额/减值准备/账面价值)/上年同结构）
 *   (2) 减值计提情况（类别/期末(余额/比例%/金额/损失率%)/上年同）
 *   (3) 按单项明细（名称/余额/准备/损失率%/理由）
 *   (4) 按组合明细（分组: 组合名 → 账龄/余额/准备/损失率%）
 *   (5) 本期计提/转回/核销（项目/计提/转回/核销/原因）
 *
 * 国企版3子节：
 *   (1) 合同资产情况
 *   (2) 减值准备（期初/计提/转回/核销/期末）
 *   (3) 本期账面价值重大变动
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 13.1
 * Requirements: 15.1-15.9, 16.1-16.7, 17.1-17.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { parseNum, calcPercentage, calcSubtotal } from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisclosureRow {
  rowId: string
  label: string
  [key: string]: any       // 动态列值（金额/比例/损失率等）
}

export interface DisclosureSection {
  sectionKey: string
  label: string
  rows: DisclosureRow[]
  totalRow?: DisclosureRow
}

export interface GroupedDetail {
  groupName: string
  rows: DisclosureRow[]
}

export interface UseD6DisclosureOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  crossSheet: {
    adjudicationForDisclosure: ComputedRef<any>
    eclForDisclosure: ComputedRef<any>
    impairmentChangesForDisclosure: ComputedRef<any>
  }
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseArray(jsonStr: string | null | undefined): any[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6Disclosure(options: UseD6DisclosureOptions) {
  const { allResponses, crossSheet, debouncedSave } = options

  // ─── Variant (上市/国企) ──────────────────────────────────────────────

  const activeVariant = ref<'listed' | 'soe'>('listed')

  /** 按适用准则判断显示哪个版本 */
  const showListed = computed(() => {
    const standards = allResponses.value.get('applicable_standards')?.remark || ''
    // 默认显示上市公司版，除非明确只有国企准则
    return !standards.includes('仅国企')
  })

  const showSoe = computed(() => {
    const standards = allResponses.value.get('applicable_standards')?.remark || ''
    return standards.includes('国企') || standards.includes('SOE')
  })

  // ─── Listed Sections (上市公司版5子节) ────────────────────────────────

  const listedSections: ComputedRef<DisclosureSection[]> = computed(() => {
    const adjData = crossSheet.adjudicationForDisclosure.value || {}
    const eclData = crossSheet.eclForDisclosure.value || {}
    const impData = crossSheet.impairmentChangesForDisclosure.value || {}

    // (1) 分类
    const section1Rows: DisclosureRow[] = (adjData.classificationRows || []).map((r: any, idx: number) => ({
      rowId: `s1-${idx}`,
      label: r.label || '',
      endBookBalance: parseNum(r.endOriginal),
      endImpairment: parseNum(r.endImpairment),
      endBookValue: parseNum(r.endOriginal) - parseNum(r.endImpairment),
      priorBookBalance: parseNum(r.priorOriginal),
      priorImpairment: parseNum(r.priorImpairment),
      priorBookValue: parseNum(r.priorOriginal) - parseNum(r.priorImpairment),
    }))

    // (2) 减值计提情况
    const section2Rows: DisclosureRow[] = (eclData.categories || []).map((r: any, idx: number) => {
      const total = parseNum(eclData.totalBalance)
      return {
        rowId: `s2-${idx}`,
        label: r.label || '',
        endBalance: parseNum(r.balance),
        endPercentage: calcPercentage(parseNum(r.balance), total),
        endAmount: parseNum(r.provision),
        endLossRate: parseNum(r.lossRate) * 100,
      }
    })

    // (3) 按单项明细
    const section3Rows: DisclosureRow[] = (eclData.singleItems || []).map((r: any, idx: number) => ({
      rowId: `s3-${idx}`,
      label: r.debtorName || '',
      balance: parseNum(r.auditedBalance),
      provision: parseNum(r.expectedProvision),
      lossRate: parseNum(r.lossRate) * 100,
      reason: r.basis || '',
    }))

    // (4) 按组合明细 — 从groupedDetails ref取（用户可编辑）
    const section4Rows: DisclosureRow[] = [] // 通过groupedDetails管理

    // (5) 本期计提/转回/核销
    const section5Rows: DisclosureRow[] = (impData.changes || []).map((r: any, idx: number) => ({
      rowId: `s5-${idx}`,
      label: r.itemName || '',
      provision: parseNum(r.provision),
      reversal: parseNum(r.reversal),
      writeOff: parseNum(r.writeOff),
      reason: r.reason || '',
    }))

    return [
      { sectionKey: 'listed-1', label: '1、合同资产', rows: section1Rows },
      { sectionKey: 'listed-major-change', label: '(1) 本期合同资产账面价值的重大变动', rows: majorChangeRows.value },
      { sectionKey: 'listed-2', label: '(2) 合同资产减值准备计提情况', rows: section2Rows },
      { sectionKey: 'listed-3', label: '　　按单项计提坏账准备的合同资产', rows: section3Rows },
      { sectionKey: 'listed-4', label: '　　按组合计提坏账准备的合同资产', rows: section4Rows },
      { sectionKey: 'listed-5', label: '(3) 本期计提、收回或转回的合同资产减值准备情况', rows: section5Rows },
    ]
  })

  // ─── SOE Sections (国企版3子节) ──────────────────────────────────────

  const soeSections: ComputedRef<DisclosureSection[]> = computed(() => {
    const adjData = crossSheet.adjudicationForDisclosure.value || {}
    const impData = crossSheet.impairmentChangesForDisclosure.value || {}

    // (1) 合同资产情况
    // (1) 合同资产情况：期末/期初 各含 账面余额/减值准备/账面价值（对齐源模板6列）
    const section1Rows: DisclosureRow[] = (adjData.classificationRows || []).map((r: any, idx: number) => ({
      rowId: `soe1-${idx}`,
      label: r.label || '',
      endBookBalance: parseNum(r.endOriginal),
      endImpairment: parseNum(r.endImpairment),
      endBookValue: parseNum(r.endOriginal) - parseNum(r.endImpairment),
      priorBookBalance: parseNum(r.priorOriginal),
      priorImpairment: parseNum(r.priorImpairment),
      priorBookValue: parseNum(r.priorOriginal) - parseNum(r.priorImpairment),
    }))

    // (2) 合同资产减值准备：项目/期初/计提/转回/转销核销/期末/原因
    const section2Rows: DisclosureRow[] = (impData.changes || []).map((r: any, idx: number) => ({
      rowId: `soe2-${idx}`,
      label: r.itemName || '',
      priorBalance: parseNum(r.priorAudited),
      provision: parseNum(r.provision),
      reversal: parseNum(r.reversal),
      writeOff: parseNum(r.writeOff),
      endBalance: parseNum(r.endAudited),
      reason: r.reason || '',
    }))

    return [
      { sectionKey: 'soe-1', label: '(1) 合同资产情况', rows: section1Rows },
      { sectionKey: 'soe-2', label: '(2) 合同资产减值准备', rows: section2Rows },
      { sectionKey: 'soe-3', label: '(1) 本期合同资产账面价值的重大变动【国资委格式未要求披露】', rows: [] },
    ]
  })

  // ─── Grouped Details (上市版第4子节按组合分组) ────────────────────────

  const groupedDetails = ref<GroupedDetail[]>([])

  // Load from allResponses
  watch(
    () => allResponses.value.get('D6-note-listed-section4-groups')?.remark,
    (jsonStr) => {
      const parsed = safeParseArray(jsonStr)
      groupedDetails.value = parsed.map((g: any) => ({
        groupName: g.groupName || '',
        rows: Array.isArray(g.rows) ? g.rows.map((r: any) => ({
          rowId: r.rowId || generateRowId(),
          label: r.label || r.agingBand || '',
          balance: parseNum(r.balance || r.auditedBalance),
          provision: parseNum(r.provision || r.expectedProvision),
          lossRate: parseNum(r.lossRate) * 100,
        })) : [],
      }))
    },
    { immediate: true },
  )

  function persistGroupedDetails(): void {
    debouncedSave('D6-note-listed-section4-groups', {
      remark: JSON.stringify(groupedDetails.value),
    })
  }

  function addGroup(): void {
    groupedDetails.value = [
      ...groupedDetails.value,
      { groupName: '', rows: [] },
    ]
    persistGroupedDetails()
  }

  function addGroupedDetailRow(groupName: string): void {
    groupedDetails.value = groupedDetails.value.map(g => {
      if (g.groupName !== groupName) return g
      return {
        ...g,
        rows: [...g.rows, {
          rowId: generateRowId(),
          label: '',
          balance: 0,
          provision: 0,
          lossRate: 0,
        }],
      }
    })
    persistGroupedDetails()
  }

  function updateGroupName(groupIndex: number, name: string): void {
    groupedDetails.value = groupedDetails.value.map((g, idx) =>
      idx === groupIndex ? { ...g, groupName: name } : g,
    )
    persistGroupedDetails()
  }

  function updateGroupedCell(groupIndex: number, rowId: string, field: string, value: any): void {
    const NUMERIC_FIELDS = ['balance', 'provision', 'lossRate']
    groupedDetails.value = groupedDetails.value.map((g, idx) => {
      if (idx !== groupIndex) return g
      return {
        ...g,
        rows: g.rows.map(r => {
          if (r.rowId !== rowId) return r
          const updated = { ...r }
          if (NUMERIC_FIELDS.includes(field)) {
            updated[field] = parseNum(value)
          } else {
            updated[field] = value
          }
          return updated
        }),
      }
    })
    persistGroupedDetails()
  }

  function removeGroupedRow(groupIndex: number, rowId: string): void {
    groupedDetails.value = groupedDetails.value.map((g, idx) => {
      if (idx !== groupIndex) return g
      return { ...g, rows: g.rows.filter(r => r.rowId !== rowId) }
    })
    persistGroupedDetails()
  }

  // ─── (1) 本期合同资产账面价值的重大变动 ──────────────────────────────

  const majorChangeRows = ref<DisclosureRow[]>([])

  watch(
    () => allResponses.value.get('D6-note-listed-major-change')?.remark,
    (jsonStr) => {
      const parsed = safeParseArray(jsonStr)
      majorChangeRows.value = parsed.map((r: any) => ({
        rowId: r.rowId || generateRowId(),
        label: r.label || r.item || '',
        amount: parseNum(r.amount),
        reason: r.reason || '',
      }))
    },
    { immediate: true },
  )

  function persistMajorChange(): void {
    debouncedSave('D6-note-listed-major-change', {
      remark: JSON.stringify(majorChangeRows.value),
    })
  }

  function addMajorChangeRow(): void {
    majorChangeRows.value = [
      ...majorChangeRows.value,
      { rowId: generateRowId(), label: '', amount: 0, reason: '' },
    ]
    persistMajorChange()
  }

  function updateMajorChangeCell(rowId: string, field: string, value: any): void {
    majorChangeRows.value = majorChangeRows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      updated[field] = field === 'amount' ? parseNum(value) : value
      return updated
    })
    persistMajorChange()
  }

  function removeMajorChangeRow(rowId: string): void {
    majorChangeRows.value = majorChangeRows.value.filter(r => r.rowId !== rowId)
    persistMajorChange()
  }

  // ─── Note Texts (说明文本 + EventBus) ────────────────────────────────

  const noteTexts = ref<Record<string, string>>({})

  // Load note texts
  const NOTE_TEXT_KEYS = [
    'D6-note-listed-text-1',
    'D6-note-listed-text-major-change',
    'D6-note-listed-text-2',
    'D6-note-listed-text-3',
    'D6-note-listed-text-4',
    'D6-note-listed-text-5',
    'D6-note-soe-text-1',
    'D6-note-soe-text-2',
    'D6-note-soe-text-3',
  ]

  watch(
    () => {
      const result: Record<string, string> = {}
      for (const key of NOTE_TEXT_KEYS) {
        result[key] = allResponses.value.get(key)?.remark || ''
      }
      return result
    },
    (texts) => {
      noteTexts.value = { ...texts }
    },
    { immediate: true },
  )

  // Watch for changes and save + emit EventBus
  watch(
    noteTexts,
    (newTexts, oldTexts) => {
      for (const key of NOTE_TEXT_KEYS) {
        if (newTexts[key] !== (oldTexts?.[key] || '')) {
          debouncedSave(key, { remark: newTexts[key] })
          // Emit EventBus for disclosure note text update
          eventBus.emit('disclosure:note-text-updated' as any, {
            wpCode: 'D6',
            section: key,
            text: newTexts[key],
          })
        }
      }
    },
    { deep: true },
  )

  // Listen for external note updates
  eventBus.on('note:section-updated' as any, (payload: any) => {
    if (payload?.wpCode === 'D6' && payload?.section && payload?.text != null) {
      const key = payload.section
      if (NOTE_TEXT_KEYS.includes(key)) {
        noteTexts.value[key] = payload.text
      }
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    listedSections,
    soeSections,
    showListed,
    showSoe,
    activeVariant,
    groupedDetails,
    addGroup,
    addGroupedDetailRow,
    updateGroupName,
    updateGroupedCell,
    removeGroupedRow,
    majorChangeRows,
    addMajorChangeRow,
    updateMajorChangeCell,
    removeMajorChangeRow,
    noteTexts,
  }
}

export default useD6Disclosure
