/**
 * useG1Classification — G1-9 分类的适当性检查表
 *
 * 对齐 Excel「分类的适当性检查表G1-9」：
 * 验证以 FVTPL 计量的金融资产，其分类依据是否符合 CAS 22：
 *   ①「交易性」三选一（近期出售/组合短期获利/衍生工具）
 *   ② 债务工具未通过 SPPI → 须 FVTPL
 *   ③ 权益工具（通常 FVTPL，除非指定 FVOCI）
 *   ④ 初始确认时指定以消除会计错配
 *
 * 与 G1-8（业务模式）/ G1-10（SPPI 逐项）分工：本表做分类结论矩阵，不重复展开测试细节。
 * 投资项目 / 期末账面价值默认从 G1-2 明细取数。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ChecklistResponse } from './useF1FormData'
import { parseNum } from './useG1TraFinFormulaEngine'

export type G1Yn = 'yes' | 'no' | 'na' | ''

export const G1_YN_OPTIONS = [
  { value: 'yes', label: '是 / √' },
  { value: 'no', label: '否' },
  { value: 'na', label: '不适用' },
] as const

export interface G1ClassificationRow {
  id: string
  seq: number
  /** 投资项目（勾稽 G1-2） */
  investItem: string
  /** 期末账面价值 / 公允价值 */
  closingBookValue: number
  /** 交易性①：近期出售或回购 */
  tradingNearTermSale: G1Yn
  /** 交易性②：组合短期获利模式 */
  tradingPortfolioShortTerm: G1Yn
  /** 交易性③：衍生工具（非有效套期） */
  tradingDerivative: G1Yn
  /** 债务工具：合同现金流并非仅为本金和利息（SPPI 不通过） */
  debtSppiFail: G1Yn
  /** 权益工具投资 */
  equityInstrument: G1Yn
  /** 初始确认时指定以消除/显著减少会计错配 */
  designatedMismatch: G1Yn
  /** 其他说明 */
  other: string
  /** 书面文件索引号 */
  indexRef: string
  /** 来自 G1-2 的行 id（同步用） */
  detailRowId?: string
}

const DATA_KEY = 'G1-9-rows'
const CONCLUSION_KEY = 'G1-9-conclusion'
const DETAIL_KEY = 'G1-2-rows'

export function emptyClassificationRow(id: string, seq: number): G1ClassificationRow {
  return {
    id,
    seq,
    investItem: '',
    closingBookValue: 0,
    tradingNearTermSale: '',
    tradingPortfolioShortTerm: '',
    tradingDerivative: '',
    debtSppiFail: '',
    equityInstrument: '',
    designatedMismatch: '',
    other: '',
    indexRef: '',
  }
}

/** 是否具备至少一项 FVTPL 分类依据 */
export function hasFvtplBasis(row: G1ClassificationRow): boolean {
  return (
    row.tradingNearTermSale === 'yes'
    || row.tradingPortfolioShortTerm === 'yes'
    || row.tradingDerivative === 'yes'
    || row.debtSppiFail === 'yes'
    || row.equityInstrument === 'yes'
    || row.designatedMismatch === 'yes'
    || !!String(row.other || '').trim()
  )
}

/** 自动归纳分类依据文案 */
export function classifyBasisLabel(row: G1ClassificationRow): string {
  const parts: string[] = []
  if (row.tradingNearTermSale === 'yes' || row.tradingPortfolioShortTerm === 'yes' || row.tradingDerivative === 'yes') {
    const t: string[] = []
    if (row.tradingNearTermSale === 'yes') t.push('近期出售/回购')
    if (row.tradingPortfolioShortTerm === 'yes') t.push('组合短期获利')
    if (row.tradingDerivative === 'yes') t.push('衍生工具')
    parts.push(`交易性（${t.join('、')}）`)
  }
  if (row.debtSppiFail === 'yes') parts.push('债务工具未通过SPPI→FVTPL')
  if (row.equityInstrument === 'yes') parts.push('权益工具')
  if (row.designatedMismatch === 'yes') parts.push('初始指定消除会计错配')
  if (String(row.other || '').trim()) parts.push(`其他：${String(row.other).trim()}`)
  return parts.length ? parts.join('；') : '未勾选分类依据'
}

/** 旧版 SPPI/业务模式行 → 新矩阵（尽力迁移） */
function migrateLegacyRow(p: Record<string, any>, i: number): G1ClassificationRow {
  const base = emptyClassificationRow(String(p.id ?? `row-${i + 1}`), Number(p.seq) || i + 1)
  base.investItem = String(p.investItem ?? '')
  if (p.sppiResult === 'fail') base.debtSppiFail = 'yes'
  if (p.sppiResult === 'pass') base.debtSppiFail = 'no'
  if (p.finalClassification === 'FVTPL' && !base.debtSppiFail) {
    base.tradingNearTermSale = 'yes'
  }
  if (p.finalClassification && p.finalClassification !== 'FVTPL') {
    base.other = `原分类结论：${p.finalClassification}`
  }
  const note = [p.sppiAuditEval, p.bizAuditEval, p.sppiRemark].filter(Boolean).join('；')
  if (note) base.other = base.other ? `${base.other}；${note}` : note
  return base
}

function normalizeRow(p: Partial<G1ClassificationRow> & Record<string, any>, i: number): G1ClassificationRow {
  // 旧字段特征
  if ('sppiResult' in p || 'finalClassification' in p || 'contractTerms' in p) {
    if (!('tradingNearTermSale' in p) && !('debtSppiFail' in p) && !('closingBookValue' in p)) {
      return migrateLegacyRow(p, i)
    }
  }
  const base = emptyClassificationRow(String(p.id ?? `row-${i + 1}`), Number(p.seq) || i + 1)
  return {
    ...base,
    ...p,
    id: String(p.id ?? base.id),
    seq: Number(p.seq) || i + 1,
    closingBookValue: parseNum(p.closingBookValue),
    investItem: String(p.investItem ?? ''),
    other: String(p.other ?? ''),
    indexRef: String(p.indexRef ?? ''),
    detailRowId: p.detailRowId ? String(p.detailRowId) : undefined,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): G1ClassificationRow[] {
  const raw = map.get(DATA_KEY)?.conclusion ?? map.get(DATA_KEY)?.remark
  if (!raw) return [emptyClassificationRow('1', 1)]
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyClassificationRow('1', 1)]
    return parsed.map((p, i) => normalizeRow(p, i))
  } catch {
    return [emptyClassificationRow('1', 1)]
  }
}

function parseDetailRows(map: Map<string, ChecklistResponse>): Array<{
  id: string
  securityName: string
  closingBookValue: number
  acctClass: string
  investType: string
}> {
  const raw = map.get(DETAIL_KEY)?.conclusion ?? map.get(DETAIL_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => ({
      id: String(r.id ?? `d-${i}`),
      securityName: String(r.securityName ?? ''),
      closingBookValue: parseNum(
        r.auditedClosingFvTotal ?? r.closingFairValue ?? r.closingReported ?? 0,
      ),
      acctClass: String(r.acctClass ?? 'trading'),
      investType: String(r.investType ?? 'other'),
    })).filter((r) => r.securityName.trim())
  } catch {
    return []
  }
}

export function useG1Classification(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1ClassificationRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion
      ?? opts.allResponses.value.get(DATA_KEY)?.remark,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )
  watch(
    () => opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion,
    (v) => {
      if (v != null) auditConclusion.value = v
    },
  )

  const totalBookValue = computed(() =>
    rows.value.reduce((s, r) => s + (Number(r.closingBookValue) || 0), 0),
  )

  const stats = computed(() => {
    const withBasis = rows.value.filter(hasFvtplBasis).length
    const missingBasis = rows.value.filter(
      (r) => (r.closingBookValue || r.investItem) && !hasFvtplBasis(r),
    ).length
    const trading = rows.value.filter(
      (r) =>
        r.tradingNearTermSale === 'yes'
        || r.tradingPortfolioShortTerm === 'yes'
        || r.tradingDerivative === 'yes',
    ).length
    const debtFail = rows.value.filter((r) => r.debtSppiFail === 'yes').length
    const equity = rows.value.filter((r) => r.equityInstrument === 'yes').length
    const designated = rows.value.filter((r) => r.designatedMismatch === 'yes').length
    return { withBasis, missingBasis, trading, debtFail, equity, designated, total: rows.value.length }
  })

  function persistAll() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1ClassificationRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, ...patch }
      if ('closingBookValue' in patch) {
        next.closingBookValue = parseNum(patch.closingBookValue)
      }
      return next
    })
    persistAll()
  }

  function addRow() {
    if (opts.isReadonly.value) return
    const seq = rows.value.length + 1
    rows.value = [...rows.value, emptyClassificationRow(`row-${Date.now()}`, seq)]
    persistAll()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  /** 从 G1-2 明细同步投资项目与期末账面价值 */
  function syncFromDetail(force = false): number {
    if (opts.isReadonly.value) return 0
    const details = parseDetailRows(opts.allResponses.value)
    if (!details.length) {
      ElMessage.warning('G1-2 明细暂无数据，请先编制明细表')
      return 0
    }

    const byDetailId = new Map(rows.value.filter((r) => r.detailRowId).map((r) => [r.detailRowId!, r]))
    const byName = new Map(
      rows.value.filter((r) => r.investItem.trim()).map((r) => [r.investItem.trim(), r]),
    )

    const next: G1ClassificationRow[] = []
    let seq = 1
    for (const d of details) {
      const prev = byDetailId.get(d.id) ?? byName.get(d.securityName)
      if (prev && !force) {
        next.push({
          ...prev,
          seq: seq++,
          investItem: d.securityName,
          closingBookValue: d.closingBookValue,
          detailRowId: d.id,
        })
        continue
      }
      const row = emptyClassificationRow(prev?.id ?? `sync-${d.id}`, seq++)
      row.investItem = d.securityName
      row.closingBookValue = d.closingBookValue
      row.detailRowId = d.id
      // 按明细会计分类/品种预填依据（可改）
      if (d.acctClass === 'trading' || d.acctClass === 'classified_fvpl') {
        if (d.investType === 'derivative') row.tradingDerivative = 'yes'
        else row.tradingNearTermSale = prev?.tradingNearTermSale || 'yes'
      }
      if (d.acctClass === 'designated_fvpl') {
        row.designatedMismatch = prev?.designatedMismatch || 'yes'
      }
      if (d.investType === 'bond') {
        row.debtSppiFail = prev?.debtSppiFail || ''
      }
      if (d.investType === 'stock') {
        row.equityInstrument = prev?.equityInstrument || 'yes'
      }
      // 保留用户已填依据
      if (prev) {
        row.tradingNearTermSale = prev.tradingNearTermSale || row.tradingNearTermSale
        row.tradingPortfolioShortTerm = prev.tradingPortfolioShortTerm
        row.tradingDerivative = prev.tradingDerivative || row.tradingDerivative
        row.debtSppiFail = prev.debtSppiFail || row.debtSppiFail
        row.equityInstrument = prev.equityInstrument || row.equityInstrument
        row.designatedMismatch = prev.designatedMismatch || row.designatedMismatch
        row.other = prev.other
        row.indexRef = prev.indexRef
      }
      next.push(row)
    }

    // 保留手工行（无 detailRowId 且名称不在明细中）
    for (const r of rows.value) {
      if (r.detailRowId) continue
      if (details.some((d) => d.securityName === r.investItem.trim())) continue
      if (!r.investItem.trim() && !r.closingBookValue) continue
      next.push({ ...r, seq: seq++ })
    }

    rows.value = next.length ? next : [emptyClassificationRow('1', 1)]
    persistAll()
    ElMessage.success(`已从 G1-2 同步 ${details.length} 个投资项目`)
    return details.length
  }

/**
 * 将 G1-8 问卷结论映射到分类依据列：
 * 2.1→近期出售 · 2.2→组合短期获利 · 2.3→衍生工具；
 * 其他业务模式且无交易性勾选时，按频繁出售/FV管理回填「近期出售」。
 */
  function applyFromBusinessModel(): number {
    if (opts.isReadonly.value) return 0
    const resultCode = opts.allResponses.value.get('G1-8-model-result')?.remark || ''
    const resultLabel = opts.allResponses.value.get('G1-8-model-result')?.conclusion || ''
    if (!resultCode || resultCode === 'INCOMPLETE') {
      ElMessage.warning('请先完成 G1-8 业务模式问卷')
      return 0
    }

    const answers: Record<string, boolean | null> = {}
    try {
      const qs = JSON.parse(opts.allResponses.value.get('G1-8-questionnaire')?.remark || '[]')
      if (Array.isArray(qs)) {
        for (const q of qs) answers[String(q.id)] = q.answer ?? null
      }
    } catch {
      /* ignore */
    }

    let n = 0
    rows.value = rows.value.map((r) => {
      if (!r.investItem.trim() && !r.closingBookValue) return r
      const patch: Partial<G1ClassificationRow> = {
        indexRef: r.indexRef || 'G1-8',
      }
      if (answers.q2_1 === true) patch.tradingNearTermSale = 'yes'
      if (answers.q2_2 === true) patch.tradingPortfolioShortTerm = 'yes'
      if (answers.q2_3 === true) patch.tradingDerivative = 'yes'
      if (
        resultCode === 'OTHER'
        && patch.tradingNearTermSale !== 'yes'
        && patch.tradingPortfolioShortTerm !== 'yes'
        && patch.tradingDerivative !== 'yes'
        && (answers.q1 === true || answers.q2 === true || answers.q3 === true || answers.q5 === true)
      ) {
        patch.tradingNearTermSale = 'yes'
      }
      const note = `G1-8结论：${resultLabel || resultCode}`
      patch.other = String(r.other || '').includes('G1-8结论')
        ? r.other
        : [r.other, note].filter(Boolean).join('；')
      n += 1
      return { ...r, ...patch }
    })
    persistAll()
    if (n > 0) ElMessage.success(`已将 G1-8 结论写入 ${n} 行分类依据`)
    else ElMessage.info('无投资行可写入，请先从明细取数或新增项目')
    return n
  }

  /** 从 G1-10 各分区汇总 investItem → SPPI 结论 */
  function loadSppiConclusionMap(): Map<string, string> {
    const map = new Map<string, string>()
    const raw = opts.allResponses.value.get('G1-10-rows')?.conclusion
      || opts.allResponses.value.get('G1-10-rows')?.remark
    if (!raw) return map
    try {
      const store = JSON.parse(raw)
      const buckets = [
        store?.bondRows,
        store?.wealthStep1,
        store?.wealthStep2,
        store?.perpetualRows,
        store?.convertibleRows,
        store?.projectRows,
        store?.absRows,
      ]
      for (const list of buckets) {
        if (!Array.isArray(list)) continue
        for (const row of list) {
          const name = String(row.investItem || '').trim()
          const conclusion = String(row.conclusion || '').toUpperCase()
          if (!name || !conclusion) continue
          // FAIL 优先覆盖；同名多行取更严结论
          const prev = map.get(name)
          if (!prev || conclusion === 'FAIL' || (conclusion === 'FURTHER_ANALYSIS' && prev === 'PASS')) {
            map.set(name, conclusion)
          }
        }
      }
    } catch {
      /* ignore */
    }
    return map
  }

  /**
   * 将 G1-10 SPPI 结论写入 debtSppiFail：
   * FAIL → yes；PASS → no；FURTHER_ANALYSIS / 空 → 不覆盖已有勾选（仅写说明）
   */
  function applyFromSppi(): number {
    if (opts.isReadonly.value) return 0
    const sppiMap = loadSppiConclusionMap()
    if (!sppiMap.size) {
      ElMessage.warning('请先在 G1-10 完成 SPPI 测试并填写结论')
      return 0
    }
    let n = 0
    rows.value = rows.value.map((r) => {
      const name = r.investItem.trim()
      if (!name) return r
      const hit = sppiMap.get(name)
      if (!hit) return r
      const patch: Partial<G1ClassificationRow> = {
        indexRef: r.indexRef?.includes('G1-10') ? r.indexRef : [r.indexRef, 'G1-10'].filter(Boolean).join('+'),
      }
      if (hit === 'FAIL') patch.debtSppiFail = 'yes'
      else if (hit === 'PASS') patch.debtSppiFail = 'no'
      const note = `G1-10 SPPI：${hit}`
      patch.other = String(r.other || '').includes('G1-10 SPPI')
        ? r.other
        : [r.other, note].filter(Boolean).join('；')
      n += 1
      return { ...r, ...patch }
    })
    persistAll()
    if (n > 0) ElMessage.success(`已将 G1-10 SPPI 结论写入 ${n} 行`)
    else ElMessage.info('G1-9 投资名称与 G1-10 无匹配，请核对 investItem')
    return n
  }

  /** G1-8 业务模式 + G1-10 SPPI 联合写入分类矩阵 */
  function applyJointFromUpstream(): number {
    if (opts.isReadonly.value) return 0
    const from8 = applyFromBusinessModel()
    const from10 = applyFromSppi()
    return from8 + from10
  }

  return {
    rows,
    auditConclusion,
    stats,
    totalBookValue,
    ynOptions: G1_YN_OPTIONS,
    hasFvtplBasis,
    classifyBasisLabel,
    updateRow,
    addRow,
    removeRow,
    syncFromDetail,
    applyFromBusinessModel,
    applyFromSppi,
    applyJointFromUpstream,
    persistAll,
  }
}

export default useG1Classification
