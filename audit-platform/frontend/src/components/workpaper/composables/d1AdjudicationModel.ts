/**
 * d1AdjudicationModel — D1 审定表锚点与分类合计的**单一真源**（零依赖纯函数）
 *
 * Spec: .kiro/specs/d1-extraction-chain-completion/
 *       (Requirements 2.x / 3.x / Property 4, 5, 6, 7)
 *
 * ## 为什么必须收敛成一个模块
 *
 * 改造前 D1 有**四处**各自拼 `D1-adj-*` 锚点字符串，其中三处拼错、静默失效：
 *
 * | 消费方 | 读的锚点 | 实际写入方 | 结果 |
 * |--------|----------|------------|------|
 * | `useD1Adjudication`（写入方） | `D1-adj-gross-bank-current-unadj` | 自己 | ✅ |
 * | `useD1Disclosure`（披露①分类表） | `D1-adj-gross-bank-current-**audited**` / `D1-adj-**baddebt**-…` | **无** | ❌ 恒 0 |
 * | `useD1InventoryCount`（D1-10） | `D1-adj-**notes-receivable**-current-audited` | **无** | ❌ 恒 0 |
 * | `useD1RelatedPartyCheck`（D1-11） | 同上 | **无** | ❌ 恒 0 |
 *
 * 两类错因：① `-current-audited` 后缀**从不持久化**（审定数是 computed 列，
 * `serializeRows` 有意只存录入列）；② 前缀 `baddebt` / `notes-receivable` 与写入方的
 * `bd` / 分类 slug 不一致。三个消费方的单测都**镜像了同款错误锚点**播种 fixture，
 * 故测试恒绿而生产恒死 —— 只有把锚点构造收敛到本模块 + 源码守卫才能根治。
 *
 * ## 口径（源模板 `D1 应收票据.xlsx` 单元格公式为裁决者）
 *
 * - 审定数 `E8=B8+C8+D8` / `I8=F8+G8+H8` → `审定 = 未审 + 账项调整 + 重分类调整`
 * - 净值 `B16=B8-B12` / `F16=F8-F12` → `净值 = 原值 − 坏账准备`（逐列独立）
 * - D1-2 `H11=B11+F11-G11` → `期末未审 = 期初**未审** + 本期增加 − 本期减少`
 *   （🔴 注意是期初**未审**，不是期初审定）
 * - D1-1 原值行 ← D1-2（`B8='原值明细表（按类别）D1-2'!B14` 等）
 * - D1-1 坏账行 ← D1-4 **按票据种类小计**（`B12='坏账准备明细表D1-4'!B23`、`F12=!K23`）
 */

/** `checklist_responses` 行的最小读取形状（与各 composable 的 ChecklistResponse 兼容）。 */
export interface D1AnchorResponse {
  item_id?: string
  conclusion?: string | null
  remark?: string | null
}

export type D1ResponseMap = ReadonlyMap<string, D1AnchorResponse>

// ─── 持久化键（明细底稿侧）───────────────────────────────────────────────────

/** D1-2 原值明细表（按类别）行集。 */
export const D1_CAT_ROWS_KEY = 'D1-cat-rows'
/** D1-4 坏账准备明细表 —— 按单项计提行集。 */
export const D1_BD_INDIVIDUAL_KEY = 'D1-bd-individual-rows'
/** D1-4 坏账准备明细表 —— 按组合计提行集。 */
export const D1_BD_PORTFOLIO_KEY = 'D1-bd-portfolio-rows'
/**
 * D1-4「按票据种类小计」行集（源模板 D1-4 R23/R24）。
 *
 * 源模板里这两行是**专门喂 D1-1 坏账区块**的额外小计块（`D1-1!B12=D1-4!B23`），
 * 与「按单项/按组合」是两个维度：D1-4 主体按**计提方法**拆，本块按**票据种类**拆。
 * 四表库 1231 只有总额、无票据种类拆分 → 本块只手工录入（宁缺勿造，不做比例分摊）。
 */
export const D1_BD_NOTETYPE_KEY = 'D1-bd-notetype-rows'

// ─── 锚点 ────────────────────────────────────────────────────────────────────

/** 审定表三区块。 */
export type D1AdjSection = 'gross' | 'bd' | 'net'

/** 审定表可持久化字段（**不含**审定数/变动额/变动率 —— 那些是派生列）。 */
export const D1_ADJ_FIELDS = [
  'prior-unadj',
  'prior-aje',
  'prior-rje',
  'current-unadj',
  'current-aje',
  'current-rje',
  'reason',
] as const
export type D1AdjField = (typeof D1_ADJ_FIELDS)[number]

/** 审定表锚点前缀。 */
export const D1_ADJ_PREFIX = 'D1-adj-'

/**
 * 唯一的审定表锚点构造器。
 *
 * 🔴 全平台禁止在本模块以外拼 `D1-adj-*` 字面量（守卫：`d1AnchorSingleSource.spec.ts`）。
 * 锚点形状必须与 `backend/data/d_cycle_extraction/d_cycle_anchor_registry.json` 的
 * D1 模式锚点一致，否则后端 `is_known_anchor` 会丢弃 seed。
 */
export function d1AdjAnchor(section: D1AdjSection, slug: string, field: D1AdjField): string {
  return `${D1_ADJ_PREFIX}${section}-${slug}-${field}`
}

/**
 * 按 `rowKey`（= `${section}-${slug}`，组件层的行标识）构造锚点。
 *
 * 供 `updateCell(rowKey, field, value)` 这类以行标识为入参的调用方使用，
 * 使它们也无需自己拼 `D1-adj-` 前缀（守卫要求）。
 */
export function d1AdjAnchorByRowKey(rowKey: string, field: D1AdjField | string): string {
  return `${D1_ADJ_PREFIX}${String(rowKey ?? '')}-${String(field ?? '')}`
}

/** 组合 rowKey。 */
export function d1AdjRowKey(section: D1AdjSection, slug: string): string {
  return `${section}-${slug}`
}

/** 审定表 TB↔审定净值核对行锚点（Tier A 公式 `TB('1121','期末余额')` 的落点）。 */
export const D1_ADJ_TB_AMOUNT_KEY = `${D1_ADJ_PREFIX}tb-amount`
/** 审定表审计说明 / 审计结论锚点。 */
export const D1_ADJ_NOTE_KEY = `${D1_ADJ_PREFIX}note`
export const D1_ADJ_CONCLUSION_KEY = `${D1_ADJ_PREFIX}conclusion`
/** 审定表锚点前缀判定（保存时按前缀批量收集 D1-adj-* 响应）。 */
export function isD1AdjAnchor(itemId: string): boolean {
  return String(itemId ?? '').startsWith(D1_ADJ_PREFIX)
}

/**
 * 审定表复核对话框 `section_id`（**与 checklist 锚点是不同命名空间**，但共用前缀，
 * 故一并在此收敛，防两处各写字面量后漂移）。
 *
 * 🔴 这两个值同时是后端 `_SECTION_PROMPTS` 的登记键，改字面量会让 AI 生成退回通用 prompt。
 */
export const D1_ADJ_REVIEW_SECTION = {
  auditNote: `${D1_ADJ_PREFIX}audit-note`,
  auditConclusion: `${D1_ADJ_PREFIX}audit-conclusion`,
} as const

/** 单元格级复核 `section_id`（形状与锚点一致，取同一构造器保证不漂移）。 */
export function d1AdjReviewSectionId(rowKey: string, field: string): string {
  return d1AdjAnchorByRowKey(rowKey, field)
}

// ─── 票据种类 ────────────────────────────────────────────────────────────────

export interface D1Category {
  /** 锚点 slug（ASCII、稳定）。固定行为 `bank` / `commercial`（与历史锚点兼容）。 */
  slug: string
  /** 展示名（源模板：银行承兑汇票 / 商业承兑汇票 / …）。 */
  label: string
  /** 是否源模板固定行（不可删除，恒排在前）。 */
  isFixed: boolean
  /** 对应 D1-2 行 id（动态行的 slug 由它派生）。 */
  rowId: string
}

/** 源模板 D1-1 固定的两个票据种类（与既有锚点 `gross-bank` / `gross-commercial` 兼容）。 */
export const D1_FIXED_CATEGORIES: readonly D1Category[] = [
  { slug: 'bank', label: '银行承兑汇票', isFixed: true, rowId: 'fixed-bank' },
  { slug: 'commercial', label: '商业承兑汇票', isFixed: true, rowId: 'fixed-commercial' },
] as const

/**
 * D1-2 行 → 锚点 slug。
 *
 * 用 **rowId** 而非票据种类名派生：rowId 是 ASCII 且稳定，改名不会让已录入的
 * AJE/RJE 变孤儿；票据种类名是中文且可编辑，用它做锚点必然产生孤儿数据。
 */
export function d1CategorySlug(rowId: string, category?: string): string {
  const id = String(rowId ?? '').trim()
  if (id === 'fixed-bank') return 'bank'
  if (id === 'fixed-commercial') return 'commercial'
  // 兜底：无 rowId 时按名称关键字归到固定行（历史数据兼容）
  if (!id) {
    const name = String(category ?? '')
    if (name.includes('银行')) return 'bank'
    if (name.includes('商业')) return 'commercial'
    return ''
  }
  const stripped = id.replace(/^dynamic-/, '').replace(/^fixed-/, '')
  const safe = stripped.replace(/[^A-Za-z0-9_-]/g, '')
  return safe ? `c-${safe}` : ''
}

// ─── 金额 ────────────────────────────────────────────────────────────────────

export interface D1PeriodAmounts {
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
}

export const D1_ZERO_AMOUNTS: D1PeriodAmounts = {
  priorUnadjusted: 0,
  priorAje: 0,
  priorRje: 0,
  priorAudited: 0,
  currentUnadjusted: 0,
  currentAje: 0,
  currentRje: 0,
  currentAudited: 0,
}

function n(v: unknown): number {
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v ?? '').trim().replace(/,/g, '')
  if (!s) return 0
  const parsed = Number(s)
  return Number.isFinite(parsed) ? parsed : 0
}

/** 源模板 `E8=B8+C8+D8`：审定数 = 未审 + 账项调整 + 重分类调整。 */
export function d1Audited(unadj: number, aje: number, rje: number): number {
  return n(unadj) + n(aje) + n(rje)
}

/** 补齐派生列（审定数）。 */
export function d1WithAudited(a: Omit<D1PeriodAmounts, 'priorAudited' | 'currentAudited'>): D1PeriodAmounts {
  return {
    ...a,
    priorAudited: d1Audited(a.priorUnadjusted, a.priorAje, a.priorRje),
    currentAudited: d1Audited(a.currentUnadjusted, a.currentAje, a.currentRje),
  }
}

/** 逐列相加。 */
export function d1SumAmounts(list: readonly D1PeriodAmounts[]): D1PeriodAmounts {
  const s = (k: keyof D1PeriodAmounts) => list.reduce((acc, x) => acc + n(x[k]), 0)
  return {
    priorUnadjusted: s('priorUnadjusted'),
    priorAje: s('priorAje'),
    priorRje: s('priorRje'),
    priorAudited: s('priorAudited'),
    currentUnadjusted: s('currentUnadjusted'),
    currentAje: s('currentAje'),
    currentRje: s('currentRje'),
    currentAudited: s('currentAudited'),
  }
}

/** 源模板 `B16=B8-B12`：净值 = 原值 − 坏账准备（逐列独立）。 */
export function d1NetAmounts(gross: D1PeriodAmounts, provision: D1PeriodAmounts): D1PeriodAmounts {
  const d = (k: keyof D1PeriodAmounts) => n(gross[k]) - n(provision[k])
  return {
    priorUnadjusted: d('priorUnadjusted'),
    priorAje: d('priorAje'),
    priorRje: d('priorRje'),
    priorAudited: d('priorAudited'),
    currentUnadjusted: d('currentUnadjusted'),
    currentAje: d('currentAje'),
    currentRje: d('currentRje'),
    currentAudited: d('currentAudited'),
  }
}

// ─── 读取 ────────────────────────────────────────────────────────────────────

function readJsonArray(map: D1ResponseMap, key: string): any[] {
  const raw = map.get(key)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function readAnchor(map: D1ResponseMap, anchor: string): string {
  const resp = map.get(anchor)
  return resp?.remark ?? resp?.conclusion ?? ''
}

/** 读某区块某分类的手工录入金额（审定数现算）。 */
export function readD1AnchorAmounts(
  map: D1ResponseMap,
  section: D1AdjSection,
  slug: string,
): D1PeriodAmounts {
  return d1WithAudited({
    priorUnadjusted: n(readAnchor(map, d1AdjAnchor(section, slug, 'prior-unadj'))),
    priorAje: n(readAnchor(map, d1AdjAnchor(section, slug, 'prior-aje'))),
    priorRje: n(readAnchor(map, d1AdjAnchor(section, slug, 'prior-rje'))),
    currentUnadjusted: n(readAnchor(map, d1AdjAnchor(section, slug, 'current-unadj'))),
    currentAje: n(readAnchor(map, d1AdjAnchor(section, slug, 'current-aje'))),
    currentRje: n(readAnchor(map, d1AdjAnchor(section, slug, 'current-rje'))),
  })
}

/** 读某区块某分类的原因分析文本。 */
export function readD1AnchorReason(map: D1ResponseMap, section: D1AdjSection, slug: string): string {
  return String(readAnchor(map, d1AdjAnchor(section, slug, 'reason')) || '')
}

/**
 * 从 D1-2 读实际票据种类（固定的银承/商承恒排在前，其余按 D1-2 顺序追加）。
 *
 * 🔴 必须支持动态种类：源模板 D1-2 固定行就有三个（银行承兑汇票 / **财务公司承兑汇票** /
 * 商业承兑汇票），四表库 seed 还会按客户科目表产出「信用证」等动态行（实测项目
 * 0ec33ac9 的 1121.03 信用证 期初 55,021,577.23）。改造前审定表只匹配「银行」/「商业」
 * → 这些金额在审定表**无落点**，净值与 TB 必然出现假差异。
 */
export function readD1Categories(map: D1ResponseMap): D1Category[] {
  const out: D1Category[] = D1_FIXED_CATEGORIES.map((c) => ({ ...c }))
  for (const raw of readJsonArray(map, D1_CAT_ROWS_KEY)) {
    const rowId = String(raw?.rowId ?? '').trim()
    const label = String(raw?.category ?? '').trim()
    const slug = d1CategorySlug(rowId, label)
    if (!slug) continue
    const existing = out.find((c) => c.slug === slug)
    if (existing) {
      // 固定行沿用源模板行名（用户改名也不覆盖固定语义）；非固定行同步最新名
      if (!existing.isFixed && label) existing.label = label
      continue
    }
    out.push({ slug, label: label || rowId, isFixed: false, rowId })
  }
  return out
}

/**
 * 从 D1-2 行集算各票据种类金额（供 D1-1 原值区块 cross-sheet 取数）。
 *
 * 🔴 `currentUnadjusted` 必须在此**现算**：`useD1DetailCategory.serializeRows()` 有意
 * 只持久化录入列（`priorUnadjusted`/`currentIncrease`/`currentDecrease`/aje/rje），
 * 派生列不落库。改造前审定表直接读 `catRow.currentUnadjusted` → 恒 `undefined` → 0，
 * 即「D1-2 填了数、审定表期末仍是 0」。
 *
 * 口径取源模板 D1-2 `H11=B11+F11-G11`：期末未审 = 期初**未审** + 本期增加 − 本期减少。
 */
export function readD1CategoryAmounts(map: D1ResponseMap): Record<string, D1PeriodAmounts> {
  const out: Record<string, D1PeriodAmounts> = {}
  for (const raw of readJsonArray(map, D1_CAT_ROWS_KEY)) {
    const slug = d1CategorySlug(String(raw?.rowId ?? ''), String(raw?.category ?? ''))
    if (!slug) continue
    const priorUnadjusted = n(raw?.priorUnadjusted)
    const increase = n(raw?.currentIncrease)
    const decrease = n(raw?.currentDecrease)
    const amounts = d1WithAudited({
      priorUnadjusted,
      priorAje: n(raw?.priorAje),
      priorRje: n(raw?.priorRje),
      currentUnadjusted: priorUnadjusted + increase - decrease,
      currentAje: n(raw?.currentAje),
      currentRje: n(raw?.currentRje),
    })
    out[slug] = out[slug] ? d1SumAmounts([out[slug], amounts]) : amounts
  }
  return out
}

/**
 * 从 D1-4「按票据种类小计」块读坏账准备（供 D1-1 坏账区块 cross-sheet 取数）。
 *
 * 源模板 `D1-1!B12='坏账准备明细表D1-4'!B23`（银行承兑汇票小计）/ `!B24`（商业承兑汇票小计），
 * 期末列 `F12=!K23`。D1-4 的「按单项/按组合」是**另一个维度**（计提方法），不能直接喂
 * 审定表的票据种类行，故源模板专门留了这两行小计。
 */
export function readD1BadDebtByNoteType(map: D1ResponseMap): Record<string, D1PeriodAmounts> {
  const out: Record<string, D1PeriodAmounts> = {}
  for (const raw of readJsonArray(map, D1_BD_NOTETYPE_KEY)) {
    const slug = d1CategorySlug(String(raw?.rowId ?? ''), String(raw?.noteType ?? raw?.category ?? ''))
    if (!slug) continue
    const priorUnadjusted = n(raw?.priorUnadjusted)
    const amounts = d1WithAudited({
      priorUnadjusted,
      priorAje: n(raw?.priorAje),
      priorRje: n(raw?.priorRje),
      currentUnadjusted: n(raw?.currentUnadjusted),
      currentAje: n(raw?.currentAje),
      currentRje: n(raw?.currentRje),
    })
    out[slug] = out[slug] ? d1SumAmounts([out[slug], amounts]) : amounts
  }
  return out
}

/**
 * D1-4 坏账准备**合计**（按单项 + 按组合），派生列现算。
 *
 * 🔴 不能直接读行里的 `currentAudited` / `priorAudited`：`useD1BadDebt.serializeRows()`
 * 与 `useD1DetailCategory.serializeRows()` 一样**有意只持久化录入列**，派生列不落库。
 * 改造前 `useD1CrossSheet.badDebtTotalAudited` 直接读 `currentAudited` → 恒 0 →
 * `eclVsBadDebtDiff` 把整个 ECL 应计提额当成差异常亮。
 *
 * 口径与 `useD1FormulaEngine.calcBadDebtEndBalance` 逐字一致
 * （期初审定 + 计提 − 收回 − 转回 − 核销 + 其他）。
 */
export function readD1BadDebtTotal(map: D1ResponseMap): D1PeriodAmounts {
  const rows: D1PeriodAmounts[] = []
  for (const key of [D1_BD_INDIVIDUAL_KEY, D1_BD_PORTFOLIO_KEY]) {
    for (const raw of readJsonArray(map, key)) {
      const priorUnadjusted = n(raw?.priorUnadjusted)
      const priorAje = n(raw?.priorAje)
      const priorRje = n(raw?.priorRje)
      const currentUnadjusted =
        d1Audited(priorUnadjusted, priorAje, priorRje) +
        n(raw?.currentProvision) -
        n(raw?.currentRecovery) -
        n(raw?.currentReversal) -
        n(raw?.currentWriteOff) +
        n(raw?.currentOther)
      rows.push(
        d1WithAudited({
          priorUnadjusted,
          priorAje,
          priorRje,
          currentUnadjusted,
          currentAje: n(raw?.currentAje),
          currentRje: n(raw?.currentRje),
        }),
      )
    }
  }
  return d1SumAmounts(rows)
}

/** D1-2 原值**合计**（派生列现算，理由同 `readD1BadDebtTotal`）。 */
export function readD1CategoryTotal(map: D1ResponseMap): D1PeriodAmounts {
  return d1SumAmounts(Object.values(readD1CategoryAmounts(map)))
}

/**
 * D1-4 坏账准备**变动列**合计（转回 / 核销），供 D1-16 转回核销检查表做跨表核对。
 *
 * 🔴 改造前 `useD1WriteoffCheck` 把「D1-4 转回变动合计」读成
 * `D1-adj-bad-debt-reversal` —— 而那个键**正是它自己**「同步到 D1-4」时写的，
 * D1-4（`useD1BadDebt`）从不读也从不写它 → 变成**自比自**（点过同步后差异恒 0），
 * 且「同步到 D1-4」按钮对 D1-4 毫无影响。现改为直接读 D1-4 真实行数据。
 */
export function readD1BadDebtChangeTotals(map: D1ResponseMap): {
  reversal: number
  writeOff: number
  /** D1-4 是否已有行数据（否则返回 null 语义由调用方决定） */
  present: boolean
} {
  let reversal = 0
  let writeOff = 0
  let present = false
  for (const key of [D1_BD_INDIVIDUAL_KEY, D1_BD_PORTFOLIO_KEY]) {
    const rows = readJsonArray(map, key)
    if (rows.length) present = true
    for (const raw of rows) {
      // 「转回」口径含「收回」（源模板 D1-4 H 列「转回」；前端另有 currentRecovery 列）
      reversal += n(raw?.currentReversal) + n(raw?.currentRecovery)
      writeOff += n(raw?.currentWriteOff)
    }
  }
  return { reversal, writeOff, present }
}

/**
 * 把转回 / 核销金额回写进 D1-4「按组合计提」父行（纯函数，返回新的 JSON 串）。
 *
 * 供 D1-16 的「同步到 D1-4」按钮真正生效：改造前它写的是 D1-4 从不读的
 * `D1-adj-bad-debt-*` 键。落点选「按组合计提」父行 —— D1-16 的合计不区分
 * 单项/组合，而组合是缺省归属；审计师可在 D1-4 内再拆到「其中：」明细行。
 *
 * 只覆盖传入的列，其余字段与其它行原样保留（缺行时补出固定父行）。
 */
export function patchD1PortfolioChangeColumns(
  map: D1ResponseMap,
  patch: { currentReversal?: number; currentWriteOff?: number },
): string {
  const rows = readJsonArray(map, D1_BD_PORTFOLIO_KEY)
  const list = rows.length
    ? rows.map((r) => ({ ...r }))
    : [
        {
          rowId: 'fixed-portfolio',
          category: 'portfolio',
          label: '按组合计提',
          isSubRow: false,
          priorUnadjusted: 0,
          priorAje: 0,
          priorRje: 0,
          currentProvision: 0,
          currentRecovery: 0,
          currentReversal: 0,
          currentWriteOff: 0,
          currentOther: 0,
          currentAje: 0,
          currentRje: 0,
        } as Record<string, unknown>,
      ]
  const target =
    list.find((r) => String(r?.rowId ?? '') === 'fixed-portfolio') ?? list[0]
  if (patch.currentReversal !== undefined) target.currentReversal = patch.currentReversal
  if (patch.currentWriteOff !== undefined) target.currentWriteOff = patch.currentWriteOff
  return JSON.stringify(list)
}

export interface D1AdjudicationTotals {
  categories: D1Category[]
  gross: Record<string, D1PeriodAmounts>
  provision: Record<string, D1PeriodAmounts>
  net: Record<string, D1PeriodAmounts>
  grossTotal: D1PeriodAmounts
  provisionTotal: D1PeriodAmounts
  netTotal: D1PeriodAmounts
  /** 原值行是否来自 D1-2 cross-sheet（逐 slug）。 */
  grossFromCrossSheet: Record<string, boolean>
  /** 坏账行是否来自 D1-4 按票据种类小计（逐 slug）。 */
  provisionFromCrossSheet: Record<string, boolean>
  /** 是否存在任何非零金额（披露表据此决定主表是否只读）。 */
  hasData: boolean
}

/**
 * 审定表三区块的**唯一**取数入口：D1-1 自身渲染、披露①分类表、D1-10 监盘、
 * D1-11 关联方全部消费本函数，保证「界面上看到的」== 「推给附注的」== 「跨表用的」。
 *
 * 取数优先级（逐分类逐列）：
 *   原值：D1-2 明细（cross-sheet）> 审定表手工锚点
 *   坏账：D1-4 按票据种类小计（cross-sheet）> 审定表手工锚点
 *   净值：恒 = 原值 − 坏账（不可手工）
 */
export function readD1AdjudicationTotals(map: D1ResponseMap): D1AdjudicationTotals {
  const categories = readD1Categories(map)
  const catAmounts = readD1CategoryAmounts(map)
  const bdAmounts = readD1BadDebtByNoteType(map)

  const gross: Record<string, D1PeriodAmounts> = {}
  const provision: Record<string, D1PeriodAmounts> = {}
  const net: Record<string, D1PeriodAmounts> = {}
  const grossFromCrossSheet: Record<string, boolean> = {}
  const provisionFromCrossSheet: Record<string, boolean> = {}

  for (const c of categories) {
    const fromCat = catAmounts[c.slug]
    const g = fromCat ?? readD1AnchorAmounts(map, 'gross', c.slug)
    grossFromCrossSheet[c.slug] = Boolean(fromCat)

    const fromBd = bdAmounts[c.slug]
    const p = fromBd ?? readD1AnchorAmounts(map, 'bd', c.slug)
    provisionFromCrossSheet[c.slug] = Boolean(fromBd)

    gross[c.slug] = g
    provision[c.slug] = p
    net[c.slug] = d1NetAmounts(g, p)
  }

  const grossTotal = d1SumAmounts(categories.map((c) => gross[c.slug]))
  const provisionTotal = d1SumAmounts(categories.map((c) => provision[c.slug]))
  const netTotal = d1NetAmounts(grossTotal, provisionTotal)
  const hasData =
    Math.abs(grossTotal.priorUnadjusted) > 0.005 ||
    Math.abs(grossTotal.currentUnadjusted) > 0.005 ||
    Math.abs(provisionTotal.priorUnadjusted) > 0.005 ||
    Math.abs(provisionTotal.currentUnadjusted) > 0.005 ||
    Math.abs(grossTotal.priorAudited) > 0.005 ||
    Math.abs(grossTotal.currentAudited) > 0.005

  return {
    categories,
    gross,
    provision,
    net,
    grossTotal,
    provisionTotal,
    netTotal,
    grossFromCrossSheet,
    provisionFromCrossSheet,
    hasData,
  }
}
