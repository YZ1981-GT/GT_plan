/**
 * useJ1Detail — J1-2 明细表 composable (对齐源模板)
 *
 * 源模板结构：3分区 × 14列宽表
 * 分区：(1)短期薪酬 (2)离职后福利/其他长期 (3)辞退福利
 * 14列：序号 | 项目名称 | 未审数(期初/本期增加/本期减少/期末) | 期初调整(账项调整) | 账项调整(本期增加/本期减少) | 审定数(期初/本期增加/本期减少/期末) | 备注
 *
 * 公式：期末数 = 期初数 + 本期增加 - 本期减少（负债贷方口径2211）
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcLiabilityEndBalance, calcSubtotal, parseNum } from './useJ1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface J1DetailRow {
  id: string
  seq: string              // 序号 (一/二/三... 或 1/2/3)
  label: string            // 项目名称
  indent: number           // 缩进层级 (0=大类, 1=子项)
  isSubItem: boolean       // 是否"其中"子项
  // 未审数段
  unadjBegin: number       // 未审-期初数
  unadjIncrease: number    // 未审-本期增加
  unadjDecrease: number    // 未审-本期减少
  unadjEnd: number         // 未审-期末数 (公式=期初+增加-减少)
  // 期初调整段
  openingAdj: number       // 期初调整-账项调整
  // 账项调整段
  ajeIncrease: number      // 账项调整-本期增加
  ajeDecrease: number      // 账项调整-本期减少
  // 审定数段
  auditedBegin: number     // 审定-期初数 (公式=未审期初+期初调整)
  auditedIncrease: number  // 审定-本期增加 (公式=未审增加+账项增加)
  auditedDecrease: number  // 审定-本期减少 (公式=未审减少+账项减少)
  auditedEnd: number       // 审定-期末数 (公式=审定期初+审定增加-审定减少)
  // 备注
  remark: string
}

export type J1DetailSection = 'shortTerm' | 'postEmployment' | 'severance'

export interface J1DetailSectionMeta {
  key: J1DetailSection
  title: string
  defaultRows: Array<{ seq: string; label: string; indent: number; isSubItem: boolean }>
  isDynamic: boolean  // 辞退福利分区允许动态增删行
}

// ─── 分区定义 ─────────────────────────────────────────────────────────────────

export const J1_SECTIONS: J1DetailSectionMeta[] = [
  {
    key: 'shortTerm',
    title: '（1）短期薪酬',
    isDynamic: false,
    defaultRows: [
      { seq: '一', label: '工资、奖金、津贴和补贴', indent: 0, isSubItem: false },
      { seq: '', label: '其中：1.工资', indent: 1, isSubItem: true },
      { seq: '', label: '2.奖金', indent: 1, isSubItem: true },
      { seq: '', label: '3.津贴', indent: 1, isSubItem: true },
      { seq: '', label: '4.补贴', indent: 1, isSubItem: true },
      { seq: '', label: '5.其他', indent: 1, isSubItem: true },
      { seq: '二', label: '职工福利费', indent: 0, isSubItem: false },
      { seq: '三', label: '社会保险费', indent: 0, isSubItem: false },
      { seq: '', label: '1.基本医疗保险费', indent: 1, isSubItem: true },
      { seq: '', label: '2.补充医疗保险费', indent: 1, isSubItem: true },
      { seq: '', label: '3.工伤保险费', indent: 1, isSubItem: true },
      { seq: '', label: '4.生育保险费', indent: 1, isSubItem: true },
      { seq: '四', label: '住房公积金', indent: 0, isSubItem: false },
      { seq: '五', label: '工会经费', indent: 0, isSubItem: false },
      { seq: '六', label: '职工教育经费', indent: 0, isSubItem: false },
      { seq: '七', label: '短期带薪缺勤', indent: 0, isSubItem: false },
      { seq: '八', label: '短期利润分享计划', indent: 0, isSubItem: false },
      { seq: '九', label: '非货币性福利', indent: 0, isSubItem: false },
      { seq: '十', label: '其他短期薪酬', indent: 0, isSubItem: false },
      { seq: '', label: '其中：以现金结算的股份支付', indent: 1, isSubItem: true },
    ],
  },
  {
    key: 'postEmployment',
    title: '（2）离职后福利中设定提存计划、其他长期福利中符合设定提存条件的负债',
    isDynamic: false,
    defaultRows: [
      { seq: '一', label: '离职后福利', indent: 0, isSubItem: false },
      { seq: '', label: '其中：1.基本养老保险', indent: 1, isSubItem: true },
      { seq: '', label: '2.失业保险费', indent: 1, isSubItem: true },
      { seq: '', label: '3.企业年金缴费', indent: 1, isSubItem: true },
      { seq: '', label: '4.其他', indent: 1, isSubItem: true },
      { seq: '二', label: '其他长期职工福利', indent: 0, isSubItem: false },
      { seq: '', label: '其中：1.xxx', indent: 1, isSubItem: true },
      { seq: '', label: '2.其他', indent: 1, isSubItem: true },
    ],
  },
  {
    key: 'severance',
    title: '（3）一年内支付的辞退福利',
    isDynamic: true,
    defaultRows: [
      { seq: '1', label: '', indent: 0, isSubItem: false },
    ],
  },
]

// ─── 存储键 ───────────────────────────────────────────────────────────────────

const STORAGE_KEY_PREFIX = 'J1-2-detail-'

function storageKey(section: J1DetailSection): string {
  return `${STORAGE_KEY_PREFIX}${section}`
}

// ─── 行公式计算 ──────────────────────────────────────────────────────────────

function recalcRow(row: J1DetailRow): J1DetailRow {
  const unadjEnd = calcLiabilityEndBalance(row.unadjBegin, row.unadjIncrease, row.unadjDecrease)
  const auditedBegin = row.unadjBegin + row.openingAdj
  const auditedIncrease = row.unadjIncrease + row.ajeIncrease
  const auditedDecrease = row.unadjDecrease + row.ajeDecrease
  const auditedEnd = calcLiabilityEndBalance(auditedBegin, auditedIncrease, auditedDecrease)
  return { ...row, unadjEnd, auditedBegin, auditedIncrease, auditedDecrease, auditedEnd }
}

function createEmptyRow(meta: { seq: string; label: string; indent: number; isSubItem: boolean }, idx: number): J1DetailRow {
  return {
    id: `j1d-${Date.now()}-${idx}-${Math.random().toString(36).slice(2, 6)}`,
    seq: meta.seq,
    label: meta.label,
    indent: meta.indent,
    isSubItem: meta.isSubItem,
    unadjBegin: 0, unadjIncrease: 0, unadjDecrease: 0, unadjEnd: 0,
    openingAdj: 0,
    ajeIncrease: 0, ajeDecrease: 0,
    auditedBegin: 0, auditedIncrease: 0, auditedDecrease: 0, auditedEnd: 0,
    remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseJ1DetailOptions {
  allResponses: Ref<Map<string, { item_id: string; conclusion: string | null; remark: string | null }>>
  saveImmediate: (items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>) => Promise<void>
  isReadonly: Ref<boolean>
}

export function useJ1Detail(options: UseJ1DetailOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State (3 sections) ──────────────────────────────────────────────
  const shortTermRows = ref<J1DetailRow[]>([])
  const postEmploymentRows = ref<J1DetailRow[]>([])
  const severanceRows = ref<J1DetailRow[]>([])

  function getRows(section: J1DetailSection): Ref<J1DetailRow[]> {
    if (section === 'shortTerm') return shortTermRows
    if (section === 'postEmployment') return postEmploymentRows
    return severanceRows
  }

  // ─── Load from allResponses ──────────────────────────────────────────
  function loadSection(section: J1DetailSection): void {
    const key = storageKey(section)
    const raw = allResponses.value.get(key)?.remark
    const meta = J1_SECTIONS.find(s => s.key === section)!
    if (!raw) {
      // Initialize with default rows
      const rows = meta.defaultRows.map((m, i) => recalcRow(createEmptyRow(m, i)))
      getRows(section).value = rows
      return
    }
    try {
      const parsed = JSON.parse(raw) as Array<Record<string, unknown>>
      if (!Array.isArray(parsed) || parsed.length === 0) {
        getRows(section).value = meta.defaultRows.map((m, i) => recalcRow(createEmptyRow(m, i)))
        return
      }
      getRows(section).value = parsed.map((r, i) => {
        const base: J1DetailRow = {
          id: String(r.id || `j1d-load-${i}-${Math.random().toString(36).slice(2, 6)}`),
          seq: String(r.seq || ''),
          label: String(r.label || ''),
          indent: Number(r.indent) || 0,
          isSubItem: Boolean(r.isSubItem),
          unadjBegin: parseNum(r.unadjBegin as number),
          unadjIncrease: parseNum(r.unadjIncrease as number),
          unadjDecrease: parseNum(r.unadjDecrease as number),
          unadjEnd: 0,
          openingAdj: parseNum(r.openingAdj as number),
          ajeIncrease: parseNum(r.ajeIncrease as number),
          ajeDecrease: parseNum(r.ajeDecrease as number),
          auditedBegin: 0, auditedIncrease: 0, auditedDecrease: 0, auditedEnd: 0,
          remark: String(r.remark || ''),
        }
        return recalcRow(base)
      })
    } catch {
      getRows(section).value = meta.defaultRows.map((m, i) => recalcRow(createEmptyRow(m, i)))
    }
  }

  function loadAll(): void {
    for (const sec of J1_SECTIONS) {
      loadSection(sec.key)
    }
  }

  loadAll()

  // ─── Serialize & Save ────────────────────────────────────────────────

  const USER_FIELDS: Array<keyof J1DetailRow> = [
    'id', 'seq', 'label', 'indent', 'isSubItem',
    'unadjBegin', 'unadjIncrease', 'unadjDecrease',
    'openingAdj', 'ajeIncrease', 'ajeDecrease', 'remark',
  ]

  function serializeSection(section: J1DetailSection): string {
    const rows = getRows(section).value
    const data = rows.map(row => {
      const obj: Record<string, unknown> = {}
      for (const field of USER_FIELDS) {
        obj[field] = row[field]
      }
      return obj
    })
    return JSON.stringify(data)
  }

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistAll()
    }, 1500)
  }

  function persistAll(): void {
    const items: Array<{ item_id: string; conclusion: string | null; remark: string | null }> = []
    for (const sec of J1_SECTIONS) {
      const key = storageKey(sec.key)
      const serialized = serializeSection(sec.key)
      allResponses.value.set(key, { item_id: key, conclusion: null, remark: serialized })
      items.push({ item_id: key, conclusion: null, remark: serialized })
    }
    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Cell Update ─────────────────────────────────────────────────────

  function updateCell(section: J1DetailSection, rowId: string, field: keyof J1DetailRow, value: number | string): void {
    if (isReadonly.value) return
    const rows = getRows(section)
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    const stringFields: Array<keyof J1DetailRow> = ['seq', 'label', 'remark']
    if (stringFields.includes(field)) {
      ;(row as any)[field] = String(value)
    } else {
      ;(row as any)[field] = parseNum(value as number)
    }
    const recalculated = recalcRow(row)
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows
    scheduleSave()
  }

  // ─── Row CRUD (辞退福利动态行) ────────────────────────────────────────

  function addRow(section: J1DetailSection): void {
    if (isReadonly.value) return
    const rows = getRows(section)
    const nextSeq = String(rows.value.length + 1)
    const newRow = recalcRow(createEmptyRow({ seq: nextSeq, label: '', indent: 0, isSubItem: false }, rows.value.length))
    rows.value = [...rows.value, newRow]
    scheduleSave()
  }

  function removeRow(section: J1DetailSection, rowId: string): void {
    if (isReadonly.value) return
    const rows = getRows(section)
    rows.value = rows.value.filter(r => r.id !== rowId)
    scheduleSave()
  }

  // ─── 分区合计 (computed) ─────────────────────────────────────────────

  function calcSectionTotal(section: J1DetailSection): J1DetailRow {
    const rows = getRows(section).value
    // 只对非子项(indent=0)求和，避免重复计算
    const topRows = rows.filter(r => !r.isSubItem)
    const total: J1DetailRow = {
      id: `total-${section}`,
      seq: '', label: '合计', indent: 0, isSubItem: false,
      unadjBegin: calcSubtotal(topRows.map(r => r.unadjBegin)),
      unadjIncrease: calcSubtotal(topRows.map(r => r.unadjIncrease)),
      unadjDecrease: calcSubtotal(topRows.map(r => r.unadjDecrease)),
      unadjEnd: 0,
      openingAdj: calcSubtotal(topRows.map(r => r.openingAdj)),
      ajeIncrease: calcSubtotal(topRows.map(r => r.ajeIncrease)),
      ajeDecrease: calcSubtotal(topRows.map(r => r.ajeDecrease)),
      auditedBegin: 0, auditedIncrease: 0, auditedDecrease: 0, auditedEnd: 0,
      remark: '',
    }
    return recalcRow(total)
  }

  const shortTermTotal: ComputedRef<J1DetailRow> = computed(() => calcSectionTotal('shortTerm'))
  const postEmploymentTotal: ComputedRef<J1DetailRow> = computed(() => calcSectionTotal('postEmployment'))
  const severanceTotal: ComputedRef<J1DetailRow> = computed(() => calcSectionTotal('severance'))

  // 全表合计
  const grandTotal = computed(() => {
    const sections = [shortTermTotal.value, postEmploymentTotal.value, severanceTotal.value]
    const grand: J1DetailRow = {
      id: 'grand-total',
      seq: '', label: '应付职工薪酬合计', indent: 0, isSubItem: false,
      unadjBegin: calcSubtotal(sections.map(s => s.unadjBegin)),
      unadjIncrease: calcSubtotal(sections.map(s => s.unadjIncrease)),
      unadjDecrease: calcSubtotal(sections.map(s => s.unadjDecrease)),
      unadjEnd: 0,
      openingAdj: calcSubtotal(sections.map(s => s.openingAdj)),
      ajeIncrease: calcSubtotal(sections.map(s => s.ajeIncrease)),
      ajeDecrease: calcSubtotal(sections.map(s => s.ajeDecrease)),
      auditedBegin: 0, auditedIncrease: 0, auditedDecrease: 0, auditedEnd: 0,
      remark: '',
    }
    return recalcRow(grand)
  })

  // ─── Audit text fields ───────────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')
  const AUDIT_NOTE_KEY = 'J1-2-audit-note'
  const AUDIT_CONCLUSION_KEY = 'J1-2-audit-conclusion'

  function loadAuditText(): void {
    auditNote.value = allResponses.value.get(AUDIT_NOTE_KEY)?.remark || ''
    auditConclusion.value = allResponses.value.get(AUDIT_CONCLUSION_KEY)?.remark || ''
  }
  loadAuditText()

  function saveAuditText(): void {
    if (isReadonly.value) return
    const items = [
      { item_id: AUDIT_NOTE_KEY, conclusion: null, remark: auditNote.value },
      { item_id: AUDIT_CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value },
    ]
    allResponses.value.set(AUDIT_NOTE_KEY, items[0])
    allResponses.value.set(AUDIT_CONCLUSION_KEY, items[1])
    saveImmediate(items).catch(() => {})
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    shortTermRows,
    postEmploymentRows,
    severanceRows,
    shortTermTotal,
    postEmploymentTotal,
    severanceTotal,
    grandTotal,
    auditNote,
    auditConclusion,
    loadAll,
    updateCell,
    addRow,
    removeRow,
    scheduleSave,
    saveAuditText,
    J1_SECTIONS,
  }
}
