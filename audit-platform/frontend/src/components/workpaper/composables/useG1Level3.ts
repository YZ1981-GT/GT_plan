/**
 * useG1Level3 — G1-7 第三层次公允价值计量的调节表
 *
 * 列结构对齐致同纸质底稿 / CAS 39 披露：
 * 期初 → 转入/转出第三层次 → 当期利得或损失(公允变动损益|投资收益)
 * → 购买/发行/出售/结算 → 期末(公式) → 仍持有资产计入损益的未实现变动
 * 另附「企业报告期末」与差异勾稽；按品种拆分同步附注⑤。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ── Types ──────────────────────────────────────────────────────────────────

/** 与附注⑤叶子对应的品种 */
export type G1Level3AssetClass = 'debt' | 'equity' | 'derivative' | 'other'

export const G1_LEVEL3_ASSET_CLASS_OPTIONS: { value: G1Level3AssetClass; label: string }[] = [
  { value: 'debt', label: '债务工具' },
  { value: 'equity', label: '权益工具' },
  { value: 'derivative', label: '衍生金融资产' },
  { value: 'other', label: '其他' },
]

/** 品种 → 附注⑤ rowKey（other 归入权益工具叶子） */
export const DISCLOSURE_L3_LEAF_BY_CLASS: Record<G1Level3AssetClass, string> = {
  debt: 'l3-trading-debt',
  equity: 'l3-trading-equity',
  derivative: 'l3-derivative',
  other: 'l3-trading-equity',
}

/** G1-7 调节行（对齐纸质底稿 + 企业报告勾稽） */
export interface Level3ReconRow {
  id: string
  seq: number
  /** 投资项目 */
  itemName: string
  /** 品种（附注拆分用） */
  assetClass: G1Level3AssetClass
  openingBalance: number
  transferIn: number
  transferOut: number
  gainPl: number
  investmentIncome: number
  purchase: number
  issue: number
  sale: number
  settlement: number
  closingBalance: number
  unrealizedHeld: number
  reportedClosing: number
  variance: number
  remark: string
}

export interface Level3Column {
  prop: keyof Level3ReconRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'assetClass'
  group?: string
}

export interface UnrealizedHeldWarning {
  id: string
  itemName: string
  reason: string
}

export type Level3DisclosureSummary = {
  opening: number
  transferIn: number
  transferOut: number
  gainPl: number
  gainOci: number
  purchase: number
  issue: number
  sale: number
  settlement: number
  closing: number
  unrealizedHeld: number
}

export const G1_LEVEL3_COLUMNS: Level3Column[] = [
  { prop: 'seq', label: '序号', width: 52, type: 'number' },
  { prop: 'itemName', label: '投资项目', width: 140, type: 'text' },
  { prop: 'assetClass', label: '品种', width: 110, type: 'assetClass' },
  { prop: 'openingBalance', label: '期初余额', width: 100, type: 'number' },
  { prop: 'transferIn', label: '转入第三层次', width: 110, type: 'number', group: '层次转移' },
  { prop: 'transferOut', label: '转出第三层次', width: 110, type: 'number', group: '层次转移' },
  { prop: 'gainPl', label: '公允价值变动损益', width: 120, type: 'number', group: '当期利得或损失总额' },
  { prop: 'investmentIncome', label: '投资收益', width: 100, type: 'number', group: '当期利得或损失总额' },
  { prop: 'purchase', label: '购买', width: 88, type: 'number', group: '购买、发行、出售和结算' },
  { prop: 'issue', label: '发行', width: 80, type: 'number', group: '购买、发行、出售和结算' },
  { prop: 'sale', label: '出售', width: 80, type: 'number', group: '购买、发行、出售和结算' },
  { prop: 'settlement', label: '结算', width: 80, type: 'number', group: '购买、发行、出售和结算' },
  { prop: 'closingBalance', label: '期末余额', width: 100, type: 'number', formula: true },
  { prop: 'unrealizedHeld', label: '仍持有未实现损益变动', width: 140, type: 'number' },
  { prop: 'reportedClosing', label: '企业报告期末', width: 110, type: 'number' },
  { prop: 'variance', label: '差异', width: 88, type: 'number', formula: true },
  { prop: 'remark', label: '备注', width: 120, type: 'text' },
]

const DATA_KEY = 'G1-7-rows'
const CONCLUSION_KEY = 'G1-7-conclusion'
const FV_DATA_KEY = 'G1-6-rows'
const DETAIL_DATA_KEY = 'G1-2-rows'

export const G1_LEVEL3_FORMULA_HINT =
  '期末 = 期初 + 转入 − 转出 + 公允变动损益 + 投资收益 + 购买 + 发行 − 出售 − 结算'

// ── Helpers ────────────────────────────────────────────────────────────────

export function normalizeAssetClass(v: unknown): G1Level3AssetClass {
  const s = String(v ?? '').trim().toLowerCase()
  if (s === 'debt' || s === 'bond' || s === '债务' || s === '债务工具') return 'debt'
  if (s === 'derivative' || s === '衍生' || s === '衍生金融资产') return 'derivative'
  if (s === 'other' || s === '其他') return 'other'
  if (s === 'equity' || s === 'stock' || s === 'fund' || s === '权益' || s === '权益工具') return 'equity'
  return 'equity'
}

/** G1-2 investType → 品种 */
export function mapInvestTypeToAssetClass(investType: unknown): G1Level3AssetClass {
  const t = String(investType ?? '').toLowerCase()
  if (t === 'bond') return 'debt'
  if (t === 'derivative') return 'derivative'
  if (t === 'stock' || t === 'fund') return 'equity'
  return 'other'
}

/** CAS 39 / 致同底稿调节公式 */
export function calcG1Level3Closing(r: Pick<
  Level3ReconRow,
  | 'openingBalance'
  | 'transferIn'
  | 'transferOut'
  | 'gainPl'
  | 'investmentIncome'
  | 'purchase'
  | 'issue'
  | 'sale'
  | 'settlement'
>): number {
  return (
    parseNum(r.openingBalance)
    + parseNum(r.transferIn)
    - parseNum(r.transferOut)
    + parseNum(r.gainPl)
    + parseNum(r.investmentIncome)
    + parseNum(r.purchase)
    + parseNum(r.issue)
    - parseNum(r.sale)
    - parseNum(r.settlement)
  )
}

/** 仍持有未实现合理性软校验（返回原因；无问题返回 null） */
export function checkUnrealizedHeld(r: Level3ReconRow): string | null {
  const uh = parseNum(r.unrealizedHeld)
  const gainPl = parseNum(r.gainPl)
  const closing = parseNum(r.closingBalance)
  if (Math.abs(uh) < 0.01) {
    if (Math.abs(closing) > 0.01 && Math.abs(gainPl) > 0.01) {
      return '有期末余额及公允变动，但未填仍持有未实现（请确认是否均为已实现）'
    }
    return null
  }
  if (Math.abs(closing) < 0.01) {
    return '期末余额为0但仍填有未实现损益变动'
  }
  if (Math.abs(uh) > Math.abs(gainPl) + 0.01) {
    return '仍持有未实现绝对值大于本期公允变动损益'
  }
  return null
}

function emptyRow(id: string, seq: number): Level3ReconRow {
  return {
    id,
    seq,
    itemName: '',
    assetClass: 'equity',
    openingBalance: 0,
    transferIn: 0,
    transferOut: 0,
    gainPl: 0,
    investmentIncome: 0,
    purchase: 0,
    issue: 0,
    sale: 0,
    settlement: 0,
    closingBalance: 0,
    unrealizedHeld: 0,
    reportedClosing: 0,
    variance: 0,
    remark: '',
  }
}

function enrich(r: Level3ReconRow): Level3ReconRow {
  const closingBalance = calcG1Level3Closing(r)
  const reportedClosing = parseNum(r.reportedClosing)
  const variance = Math.round((closingBalance - reportedClosing) * 100) / 100
  return {
    ...r,
    assetClass: normalizeAssetClass(r.assetClass),
    closingBalance,
    variance,
  }
}

/**
 * 兼容旧版列（增加·新确认/转入、减少·终止确认/转出、本期公允变动、估值方法等）
 */
export function migrateLegacyLevel3Row(raw: Record<string, unknown>, seq: number): Level3ReconRow {
  const base = emptyRow(String(raw.id ?? `row-${seq}`), seq)
  const assetClass = normalizeAssetClass(raw.assetClass ?? raw.investType)
  const hasNewShape =
    raw.transferIn != null
    || raw.gainPl != null
    || raw.purchase != null
    || raw.investmentIncome != null

  if (hasNewShape) {
    return enrich({
      ...base,
      itemName: String(raw.itemName ?? ''),
      assetClass,
      openingBalance: parseNum(raw.openingBalance),
      transferIn: parseNum(raw.transferIn),
      transferOut: parseNum(raw.transferOut),
      gainPl: parseNum(raw.gainPl ?? raw.fairValueChange),
      investmentIncome: parseNum(raw.investmentIncome),
      purchase: parseNum(raw.purchase ?? raw.addNewRecognition),
      issue: parseNum(raw.issue),
      sale: parseNum(raw.sale ?? raw.reduceDerecognition),
      settlement: parseNum(raw.settlement),
      unrealizedHeld: parseNum(raw.unrealizedHeld),
      reportedClosing: parseNum(raw.reportedClosing),
      remark: String(raw.remark ?? ''),
    })
  }

  const legacyBits = [
    raw.valuationMethod ? `估值方法：${raw.valuationMethod}` : '',
    raw.keyAssumption ? `关键假设：${raw.keyAssumption}` : '',
    raw.sensitivity ? `敏感性：${raw.sensitivity}` : '',
    raw.auditEval ? `审计评价：${raw.auditEval}` : '',
  ].filter(Boolean)

  return enrich({
    ...base,
    itemName: String(raw.itemName ?? ''),
    assetClass,
    openingBalance: parseNum(raw.openingBalance),
    transferIn: parseNum(raw.addTransferIn),
    transferOut: parseNum(raw.reduceTransferOut),
    gainPl: parseNum(raw.fairValueChange),
    investmentIncome: 0,
    purchase: parseNum(raw.addNewRecognition),
    issue: 0,
    sale: parseNum(raw.reduceDerecognition),
    settlement: 0,
    unrealizedHeld: 0,
    reportedClosing: parseNum(raw.closingBalance),
    remark: [String(raw.remark ?? ''), ...legacyBits].filter(Boolean).join('；'),
  })
}

function loadRows(map: Map<string, ChecklistResponse>): Level3ReconRow[] {
  const raw = map.get(DATA_KEY)?.conclusion ?? map.get(DATA_KEY)?.remark
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => migrateLegacyLevel3Row(p, i + 1))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

const SUM_FIELDS = [
  'openingBalance',
  'transferIn',
  'transferOut',
  'gainPl',
  'investmentIncome',
  'purchase',
  'issue',
  'sale',
  'settlement',
  'closingBalance',
  'unrealizedHeld',
  'reportedClosing',
  'variance',
] as const

export type G1Level3Totals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: Level3ReconRow[]): G1Level3Totals {
  const out = {} as G1Level3Totals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f])))
  }
  return out
}

/** 附注⑤ L3 调节带入用汇总（计入损益 = 公允变动 + 投资收益） */
export function summarizeLevel3ForDisclosure(list: Level3ReconRow[]): Level3DisclosureSummary {
  return {
    opening: calcSubtotal(list.map((r) => parseNum(r.openingBalance))),
    transferIn: calcSubtotal(list.map((r) => parseNum(r.transferIn))),
    transferOut: calcSubtotal(list.map((r) => parseNum(r.transferOut))),
    gainPl: calcSubtotal(list.map((r) => parseNum(r.gainPl) + parseNum(r.investmentIncome))),
    gainOci: 0,
    purchase: calcSubtotal(list.map((r) => parseNum(r.purchase))),
    issue: calcSubtotal(list.map((r) => parseNum(r.issue))),
    sale: calcSubtotal(list.map((r) => parseNum(r.sale))),
    settlement: calcSubtotal(list.map((r) => parseNum(r.settlement))),
    closing: calcSubtotal(list.map((r) => parseNum(r.closingBalance))),
    unrealizedHeld: calcSubtotal(list.map((r) => parseNum(r.unrealizedHeld))),
  }
}

/** 按附注叶子拆分汇总（债务 / 权益 / 衍生） */
export function summarizeLevel3ByDisclosureLeaf(
  list: Level3ReconRow[],
): Record<string, Level3DisclosureSummary> {
  const buckets: Record<string, Level3ReconRow[]> = {
    'l3-trading-debt': [],
    'l3-trading-equity': [],
    'l3-derivative': [],
  }
  for (const r of list) {
    const leaf = DISCLOSURE_L3_LEAF_BY_CLASS[normalizeAssetClass(r.assetClass)]
    buckets[leaf].push(r)
  }
  const out: Record<string, Level3DisclosureSummary> = {}
  for (const [leaf, rows] of Object.entries(buckets)) {
    if (rows.length) out[leaf] = summarizeLevel3ForDisclosure(rows)
  }
  return out
}

/** 从 G1-2 明细行映射为调节行字段 */
export function mapDetailRowToLevel3Patch(src: Record<string, unknown>): Partial<Level3ReconRow> {
  const opening =
    parseNum(src.auditedOpeningFvTotal) || parseNum(src.openingFairValue) || parseNum(src.openingBalance)
  const purchase = parseNum(src.addedCost)
  const sale = parseNum(src.reducedCost)
  const gainPl =
    parseNum(src.fvChangeInPL) || parseNum(src.periodFvChange) || parseNum(src.fairValueChange)
  const investmentIncome =
    parseNum(src.totalIncome) || (parseNum(src.dividendIncome) + parseNum(src.realizedGain))
  const reported =
    parseNum(src.auditedClosingFvTotal) || parseNum(src.closingFairValue) || parseNum(src.closingReported)
  const stillHeld = Math.abs(reported) > 0.01 || parseNum(src.closingQuantity) > 0
  return {
    itemName: String(src.securityName ?? src.itemName ?? '').trim(),
    assetClass: mapInvestTypeToAssetClass(src.investType),
    openingBalance: opening,
    purchase,
    sale,
    gainPl,
    investmentIncome,
    reportedClosing: reported,
    unrealizedHeld: stillHeld ? gainPl : 0,
    remark: '自 G1-2 Level3 带入',
  }
}

// ── Composable ─────────────────────────────────────────────────────────────

export function useG1Level3(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<Level3ReconRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion
      ?? opts.allResponses.value.get(DATA_KEY)?.remark,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const grandTotal = computed<G1Level3Totals>(() => sumRows(rows.value))

  const varianceRows = computed(() =>
    rows.value.filter((r) => Math.abs(r.variance) > 0.01 && (r.reportedClosing !== 0 || r.closingBalance !== 0)),
  )

  const unrealizedWarnings = computed<UnrealizedHeldWarning[]>(() =>
    rows.value
      .map((r) => {
        const reason = checkUnrealizedHeld(r)
        return reason ? { id: r.id, itemName: r.itemName || `第${r.seq}行`, reason } : null
      })
      .filter((x): x is UnrealizedHeldWarning => x != null),
  )

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<Level3ReconRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增调节行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '投资项目不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [...rows.value, enrich({ ...emptyRow(`row-${Date.now()}`, seq), itemName: value })]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  function replaceOrAppendRows(
    additions: Level3ReconRow[],
    sourceLabel: string,
    mode: 'merge-fill' | 'overwrite' = 'overwrite',
  ) {
    if (!additions.length) {
      ElMessage.info(`${sourceLabel}项目已在本表中或无可带入数据`)
      return
    }
    const byName = new Map(rows.value.map((r) => [r.itemName.trim(), r]))
    let added = 0
    let updated = 0
    for (const add of additions) {
      const name = add.itemName.trim()
      if (!name) continue
      const existing = byName.get(name)
      if (existing) {
        if (mode === 'merge-fill') {
          // 仅补空项目名已有时的勾稽字段（G1-6：企业报告期末）
          byName.set(
            name,
            enrich({
              ...existing,
              reportedClosing: existing.reportedClosing || add.reportedClosing,
              remark: existing.remark || add.remark,
              assetClass: existing.assetClass || add.assetClass,
            }),
          )
        } else {
          byName.set(name, enrich({ ...existing, ...add, id: existing.id, seq: existing.seq }))
        }
        updated += 1
      } else {
        byName.set(name, add)
        added += 1
      }
    }
    const merged = Array.from(byName.values())
      .filter((r) => r.itemName.trim() || r.closingBalance || r.openingBalance)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    rows.value = merged.length ? merged : [enrich(emptyRow('1', 1))]
    persistAll()
    ElMessage.success(`已从 ${sourceLabel} 更新 ${updated} 行、新增 ${added} 行`)
  }

  /** 从 G1-6 公允价值测试中 Level3 行带入项目名称与企业报告期末 */
  function pullFromFairValueTest() {
    if (opts.isReadonly.value) return
    const raw = opts.allResponses.value.get(FV_DATA_KEY)?.conclusion
    if (!raw) {
      ElMessage.warning('未找到 G1-6 公允价值测试数据')
      return
    }
    try {
      const list = JSON.parse(raw) as Array<Record<string, unknown>>
      const l3 = (Array.isArray(list) ? list : []).filter((r) => Number(r.fvLevel) === 3)
      if (!l3.length) {
        ElMessage.info('G1-6 中暂无 Level3 项目')
        return
      }
      let seq = rows.value.length
      const additions: Level3ReconRow[] = []
      for (const src of l3) {
        const name = String(src.securityName ?? '').trim()
        if (!name) continue
        seq += 1
        const reported = parseNum(src.level3Result) || parseNum(src.bookValue)
        additions.push(
          enrich({
            ...emptyRow(src.id ? `fv-${src.id}` : `row-${Date.now()}-${seq}`, seq),
            itemName: name,
            assetClass: 'equity',
            reportedClosing: reported,
            remark: '自 G1-6 Level3 带入',
          }),
        )
      }
      replaceOrAppendRows(additions, 'G1-6', 'merge-fill')
    } catch {
      ElMessage.error('解析 G1-6 数据失败')
    }
  }

  /** 从 G1-2 明细中 fairValueSource=3 的行带入变动因子 */
  function pullFromDetail() {
    if (opts.isReadonly.value) return
    const raw = opts.allResponses.value.get(DETAIL_DATA_KEY)?.conclusion
    if (!raw) {
      ElMessage.warning('未找到 G1-2 明细表数据')
      return
    }
    try {
      const list = JSON.parse(raw) as Array<Record<string, unknown>>
      const l3 = (Array.isArray(list) ? list : []).filter((r) => {
        const src = String(r.fairValueSource ?? '')
        return src === '3' || Number(src) === 3
      })
      if (!l3.length) {
        ElMessage.info('G1-2 中暂无公允层级为 Level3 的项目')
        return
      }
      let seq = rows.value.length
      const additions: Level3ReconRow[] = []
      for (const src of l3) {
        const patch = mapDetailRowToLevel3Patch(src)
        if (!patch.itemName) continue
        seq += 1
        additions.push(
          enrich({
            ...emptyRow(src.id ? `d2-${src.id}` : `row-${Date.now()}-${seq}`, seq),
            ...patch,
            assetClass: patch.assetClass ?? 'other',
          }),
        )
      }
      replaceOrAppendRows(additions, 'G1-2', 'overwrite')
    } catch {
      ElMessage.error('解析 G1-2 数据失败')
    }
  }

  return {
    columns: G1_LEVEL3_COLUMNS,
    rows,
    auditConclusion,
    grandTotal,
    varianceRows,
    unrealizedWarnings,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    pullFromFairValueTest,
    pullFromDetail,
  }
}

export default useG1Level3
