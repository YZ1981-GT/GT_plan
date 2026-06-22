/**
 * useDiffChecklistData — D0-4b 函证差异检查表数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化 companies（_format: diff-checklist-v1）
 * - 多公司 CRUD（addCompany / deleteCompany / updateCompany / importCompanies）
 * - A-I 公式链自动计算（B_total / C_total / D / F_total / G_total / H / I）
 * - 差异状态派生（balanced / diff / over_materiality）
 * - 看板指标（metrics）
 * - D0-4 带入映射
 * - buildPayload 持久化
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  DiffChecklistCompany,
  SubTableRow,
  DiffChecklistMetrics,
  ChecklistMaterialityConfig,
  ChecklistConclusion,
  DiffChecklistPayload,
} from '../diffChecklistTypes'

// ─── ID 生成工具 ─────────────────────────────────────────────────────────────

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

/** 精确小数：乘 100 整数运算后除回（避免浮点漂移） */
function precise2(val: number): number {
  return Math.round(val * 100) / 100
}

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseDiffChecklistDataProps {
  /** 响应式数据源（来自底稿的 htmlData） */
  htmlData: () => any
  /** 是否只读 */
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseDiffChecklistDataReturn {
  companies: Ref<DiffChecklistCompany[]>
  globalNote: Ref<string>
  conclusion: Ref<ChecklistConclusion>
  materialityConfig: Ref<ChecklistMaterialityConfig>
  isDirty: Ref<boolean>

  // CRUD
  addCompany: () => DiffChecklistCompany
  deleteCompany: (ids: string[]) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: DiffChecklistCompany[]) => void

  // 子表 CRUD
  addSubTableRow: (companyId: string, section: 'b' | 'c' | 'f' | 'g') => SubTableRow | null
  deleteSubTableRow: (companyId: string, section: 'b' | 'c' | 'f' | 'g', rowId: string) => void
  updateSubTableRow: (companyId: string, section: 'b' | 'c' | 'f' | 'g', rowId: string, field: string, value: any) => void

  // 公式链
  computeFormula: (company: DiffChecklistCompany) => DiffChecklistCompany
  recomputeAll: () => void

  // 状态 + 看板
  getCompanyStatus: (company: DiffChecklistCompany) => 'balanced' | 'diff' | 'over_materiality'
  metrics: ComputedRef<DiffChecklistMetrics>

  // 重要性
  isOverMateriality: (company: DiffChecklistCompany) => boolean

  // 持久化
  buildPayload: () => DiffChecklistPayload
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useDiffChecklistData(props: UseDiffChecklistDataProps): UseDiffChecklistDataReturn {
  const companies = ref<DiffChecklistCompany[]>([])
  const globalNote = ref<string>('')
  const conclusion = ref<ChecklistConclusion>({})
  const materialityConfig = ref<ChecklistMaterialityConfig>({})
  const isDirty = ref(false)

  // ─── 从 htmlData 初始化 ────────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'diff-checklist-v1') {
      companies.value = []
      globalNote.value = ''
      conclusion.value = {}
      materialityConfig.value = {}
      return
    }
    companies.value = Array.isArray(data.companies)
      ? data.companies.map(ensureCompanyId)
      : []
    globalNote.value = data.global_note ?? ''
    conclusion.value = data.conclusion ?? {}
    materialityConfig.value = data.materiality_config ?? {}
    isDirty.value = false
  }

  function ensureCompanyId(company: DiffChecklistCompany): DiffChecklistCompany {
    if (!company._row_id) {
      company = { ...company, _row_id: generateRowId() }
    }
    // 确保子表行也有 ID
    company.b_rows = (company.b_rows ?? []).map(ensureSubRowId)
    company.c_rows = (company.c_rows ?? []).map(ensureSubRowId)
    company.f_rows = (company.f_rows ?? []).map(ensureSubRowId)
    company.g_rows = (company.g_rows ?? []).map(ensureSubRowId)
    return computeFormula(company)
  }

  function ensureSubRowId(row: SubTableRow): SubTableRow {
    if (!row._row_id) return { ...row, _row_id: generateRowId() }
    return row
  }

  // 初始加载
  initFromHtmlData(props.htmlData())

  // 监听 htmlData 变化
  watch(
    () => props.htmlData(),
    (newData) => { initFromHtmlData(newData) },
    { deep: true }
  )

  // ─── A-I 公式链计算 ───────────────────────────────────────────────────────

  function sumSubTable(rows?: SubTableRow[]): number {
    if (!rows || !rows.length) return 0
    return rows.reduce((s, r) => s + (r.amount ?? 0), 0)
  }

  function computeFormula(company: DiffChecklistCompany): DiffChecklistCompany {
    const A = company.a_reply_amount ?? 0
    const B = sumSubTable(company.b_rows)
    const C = sumSubTable(company.c_rows)
    const D = precise2(A + B - C)

    const E = company.e_book_amount ?? 0
    const F = sumSubTable(company.f_rows)
    const G = sumSubTable(company.g_rows)
    const H = precise2(E + F - G)

    const I = precise2(H - D)

    company.b_total = precise2(B)
    company.c_total = precise2(C)
    company.d_adjusted_reply = D
    company.f_total = precise2(F)
    company.g_total = precise2(G)
    company.h_adjusted_book = H
    company.i_final_diff = I
    company.status = getCompanyStatus(company)

    return company
  }

  function recomputeAll() {
    companies.value = companies.value.map((c) => computeFormula({ ...c }))
  }

  // ─── 状态派生 ──────────────────────────────────────────────────────────────

  function getCompanyStatus(company: DiffChecklistCompany): 'balanced' | 'diff' | 'over_materiality' {
    const diff = company.i_final_diff ?? 0
    if (diff === 0) return 'balanced'
    if (isOverMateriality(company)) return 'over_materiality'
    return 'diff'
  }

  function isOverMateriality(company: DiffChecklistCompany): boolean {
    const pm = materialityConfig.value.performance_materiality
    if (pm == null || pm <= 0) return false
    const diff = Math.abs(company.i_final_diff ?? 0)
    return diff >= pm
  }

  // ─── 公司 CRUD ────────────────────────────────────────────────────────────

  function addCompany(): DiffChecklistCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: DiffChecklistCompany = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
      b_rows: [],
      c_rows: [],
      f_rows: [],
      g_rows: [],
      b_total: 0,
      c_total: 0,
      d_adjusted_reply: 0,
      f_total: 0,
      g_total: 0,
      h_adjusted_book: 0,
      i_final_diff: 0,
      status: 'balanced',
      _source: 'manual',
    }
    companies.value.push(newCompany)
    isDirty.value = true
    return newCompany
  }

  function deleteCompany(ids: string[]) {
    if (!ids.length) return
    const idSet = new Set(ids)
    companies.value = companies.value.filter((c) => !idSet.has(c._row_id!))
    isDirty.value = true
  }

  function updateCompany(companyId: string, field: string, value: any) {
    const company = companies.value.find((c) => c._row_id === companyId)
    if (!company) return
    ;(company as any)[field] = value
    // 金额字段变更时重算公式链
    if (['a_reply_amount', 'e_book_amount'].includes(field)) {
      computeFormula(company)
    }
    isDirty.value = true
  }

  function importCompanies(items: DiffChecklistCompany[]) {
    // 按 entity_name + subject 去重
    const existingKeys = new Set(
      companies.value.map((c) => `${c.entity_name}||${c.subject}`).filter((k) => k !== '||')
    )
    const deduped = items.filter(
      (item) => {
        const key = `${item.entity_name}||${item.subject}`
        return key === '||' || !existingKeys.has(key)
      }
    )
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    deduped.forEach((item, i) => {
      item._row_id = generateRowId()
      item.seq = maxSeq + i + 1
      item.b_rows = item.b_rows ?? []
      item.c_rows = item.c_rows ?? []
      item.f_rows = item.f_rows ?? []
      item.g_rows = item.g_rows ?? []
      item._source = item._source || 'auto'
      computeFormula(item)
    })
    companies.value.push(...deduped)
    isDirty.value = true
  }

  // ─── 子表 CRUD ─────────────────────────────────────────────────────────────

  function getSubTableRows(company: DiffChecklistCompany, section: 'b' | 'c' | 'f' | 'g'): SubTableRow[] {
    const key = `${section}_rows` as keyof DiffChecklistCompany
    return (company[key] as SubTableRow[]) ?? []
  }

  function setSubTableRows(company: DiffChecklistCompany, section: 'b' | 'c' | 'f' | 'g', rows: SubTableRow[]) {
    const key = `${section}_rows` as keyof DiffChecklistCompany
    ;(company as any)[key] = rows
  }

  function addSubTableRow(companyId: string, section: 'b' | 'c' | 'f' | 'g'): SubTableRow | null {
    const company = companies.value.find((c) => c._row_id === companyId)
    if (!company) return null
    const rows = getSubTableRows(company, section)
    const maxSeq = rows.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow: SubTableRow = {
      _row_id: generateRowId(),
      seq: maxSeq + 1,
      amount: 0,
    }
    rows.push(newRow)
    setSubTableRows(company, section, rows)
    computeFormula(company)
    isDirty.value = true
    return newRow
  }

  function deleteSubTableRow(companyId: string, section: 'b' | 'c' | 'f' | 'g', rowId: string) {
    const company = companies.value.find((c) => c._row_id === companyId)
    if (!company) return
    const rows = getSubTableRows(company, section).filter((r) => r._row_id !== rowId)
    setSubTableRows(company, section, rows)
    computeFormula(company)
    isDirty.value = true
  }

  function updateSubTableRow(
    companyId: string,
    section: 'b' | 'c' | 'f' | 'g',
    rowId: string,
    field: string,
    value: any
  ) {
    const company = companies.value.find((c) => c._row_id === companyId)
    if (!company) return
    const rows = getSubTableRows(company, section)
    const row = rows.find((r) => r._row_id === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 金额变更时重算公式链
    if (field === 'amount') {
      computeFormula(company)
    }
    isDirty.value = true
  }

  // ─── 看板指标 ──────────────────────────────────────────────────────────────

  const metrics = computed<DiffChecklistMetrics>(() => {
    const total = companies.value.length
    const balanced = companies.value.filter((c) => (c.i_final_diff ?? 0) === 0).length
    const diff = total - balanced
    const overMat = companies.value.filter((c) => isOverMateriality(c)).length
    const diffNet = companies.value.reduce((s, c) => s + (c.i_final_diff ?? 0), 0)
    const diffAbs = companies.value.reduce((s, c) => s + Math.abs(c.i_final_diff ?? 0), 0)

    return {
      total_count: total,
      balanced_count: balanced,
      diff_count: diff,
      over_materiality_count: overMat,
      completion_rate: total > 0 ? precise2((balanced / total) * 100) : 0,
      diff_net_total: precise2(diffNet),
      diff_abs_total: precise2(diffAbs),
    }
  })

  // ─── buildPayload ──────────────────────────────────────────────────────────

  function buildPayload(): DiffChecklistPayload {
    return {
      _format: 'diff-checklist-v1',
      companies: companies.value.map((c) => computeFormula({ ...c })),
      global_note: globalNote.value || undefined,
      conclusion: conclusion.value,
      materiality_config: materialityConfig.value,
    }
  }

  return {
    companies,
    globalNote,
    conclusion,
    materialityConfig,
    isDirty,

    addCompany,
    deleteCompany,
    updateCompany,
    importCompanies,

    addSubTableRow,
    deleteSubTableRow,
    updateSubTableRow,

    computeFormula,
    recomputeAll,

    getCompanyStatus,
    metrics,
    isOverMateriality,

    buildPayload,
  }
}
