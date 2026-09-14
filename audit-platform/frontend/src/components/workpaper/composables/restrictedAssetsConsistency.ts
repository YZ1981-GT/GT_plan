/**
 * 受限资产共享表（listed `五、32` 主表+续表 / soe `八、93`）**勾稽 + 段级溯源**（纯函数）。
 *
 * 这张表是八循环共享的多段表，没有任何单一循环能独立校验它 → 勾稽必须站在
 * 「附注侧现存行集」这一层做：
 *
 * 1. **合计勾稽**：合计行 = 全部数据行之和（含无主行「其他」）。
 *    soe 源模板**没有合计行**（9 行止于「其他」）→ 该变体 skip，不得凭空要求。
 * 2. **段级比对**：某段的附注金额 vs 该循环底稿受限金额。
 *    **未提供底稿金额的段一律 skip 不 error** —— 「附注有值而底稿没接」既可能是
 *    审计师在附注模块手填（合法），也可能是该 owner 还没接推送（D5/F2），
 *    报 error 会把两种正常情形一起打红。
 * 3. **`_seg` 泄漏**：行级合并写入时给行打 `_seg` 戳用于段定位，读时投影应剥离；
 *    泄漏到附注行里属平台缺陷（会渲染成一列垃圾）→ error。
 *
 * 段级溯源：`_last_sync_wp_id` 只记**最后一次**推送方，多 owner 共享表下无意义 →
 * 段归属由行内 `_seg` / 行标签反查 `RESTRICTED_ASSETS_OWNERS` 推导。
 *
 * spec: .kiro/specs/restricted-assets-note-row-scope-rollout/ Requirements 4.1~4.4
 */
import {
  isRestrictedAssetsOwnerApplicable,
  RESTRICTED_ASSETS_OWNERS,
  type RestrictedAssetsOwner,
  type RestrictedAssetsVariant,
} from './restrictedAssetsNoteSectionMap'

/** 附注侧一行（`sub_table_data` 里的业务键行）。 */
export interface RestrictedAssetsNoteRow {
  label?: string
  /** 行级合并写入时的段戳（**不应泄漏到附注**，见 Check 3） */
  _seg?: string
  /** listed 主表 */
  end_amount?: number | null
  /** listed 续表 */
  prior_amount?: number | null
  /** soe 单表 */
  end_carrying?: number | null
  reason?: string | null
  is_total?: boolean
  row_type?: string
}

export type RestrictedCheckLevel = 'ok' | 'warn' | 'error' | 'skip'

export interface RestrictedCheck {
  label: string
  /** 勾稽规则（给审计师看的口径说明） */
  rule: string
  left: number | null
  right: number | null
  diff: number | null
  level: RestrictedCheckLevel
  detail: string
  /** 追溯线索（段 owner code / 循环 wp_code） */
  refs: string[]
}

/** 金额容差（元）。 */
export const RESTRICTED_TOLERANCE = 0.01

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)

/** 段标签 → owner code（`RESTRICTED_ASSETS_OWNERS` 的反向表）。 */
const LABEL_TO_OWNER: Readonly<Record<string, RestrictedAssetsOwner>> = Object.freeze(
  Object.fromEntries(
    (Object.entries(RESTRICTED_ASSETS_OWNERS) as [RestrictedAssetsOwner, string][]).map(
      ([code, label]) => [label, code],
    ),
  ) as Record<string, RestrictedAssetsOwner>,
)

/**
 * 推导某行属于哪个段（`_seg` 优先，回退按行标签反查）。
 *
 * 取不到返 `null` —— 无主行（soe 末行「其他」）与合计行本就不属任何 owner。
 */
export function resolveRestrictedRowOwner(
  row: RestrictedAssetsNoteRow,
): RestrictedAssetsOwner | null {
  const seg = String(row?._seg ?? '').trim()
  if (seg && seg in RESTRICTED_ASSETS_OWNERS) return seg as RestrictedAssetsOwner
  const label = String(row?.label ?? '').trim()
  return LABEL_TO_OWNER[label] ?? null
}

/**
 * 段 owner → 归属循环（wp_code）。
 *
 * 🔴 这是**段级溯源的真源**：`disclosure_notes._last_sync_wp_id` 只记最后一次推送方，
 * 8 段共享一张表时它对其余 7 段是错的 → 溯源必须按段推导。
 *
 * 与 `restrictedAssetsSources.RESTRICTED_ASSETS_SOURCES[].wpCode` 交叉锁死
 * （守卫断言两处对同一 owner 给出相同 wp_code）；E1/D1 走披露 Tab 内存行模型
 * 不在声明表里，故这里必须是**全 8 段**的完整映射。
 */
export const RESTRICTED_ASSETS_OWNER_WP = Object.freeze({
  'BS-002': 'E1',
  'BS-005': 'D1',
  'BS-006': 'D2',
  'BS-007': 'D5',
  'BS-010': 'F2',
  'BS-028': 'H1',
  'BS-029': 'H2',
  'BS-032': 'I1',
} as const satisfies Record<RestrictedAssetsOwner, string>)

export interface RestrictedRowProvenance {
  owner: RestrictedAssetsOwner | null
  /** 段标签（附注行标签） */
  segment: string
  /** 归属循环 wp_code；无主行/合计行为 null */
  wpCode: string | null
  /** 给用户看的一句话 */
  text: string
}

/**
 * 单行溯源：这一行是哪个循环推来的。
 *
 * 无主行（soe 末行「其他」）与合计行返回 `owner: null` + 明确文案
 * —— 它们**不属任何 owner 的可写区**（平台 `Segment.data_end` 与
 * `row_type: "unowned"` 保住），由附注侧自行维护。
 */
export function describeRestrictedRowProvenance(
  row: RestrictedAssetsNoteRow,
): RestrictedRowProvenance {
  const owner = resolveRestrictedRowOwner(row)
  const label = String(row?.label ?? '').trim()
  if (!owner) {
    return {
      owner: null,
      segment: label,
      wpCode: null,
      text: isRestrictedTotalRow(row)
        ? '合计行由附注侧维护（不属任何底稿的可写区）'
        : '无主行：不属任何循环，由附注侧自行维护',
    }
  }
  const wpCode = RESTRICTED_ASSETS_OWNER_WP[owner]
  return {
    owner,
    segment: RESTRICTED_ASSETS_OWNERS[owner],
    wpCode,
    text: `本行由 ${wpCode} 循环推送（段 ${owner} ${RESTRICTED_ASSETS_OWNERS[owner]}）`,
  }
}

/** 该行的期末金额（按变体取列）。 */
function endOf(variant: RestrictedAssetsVariant, row: RestrictedAssetsNoteRow): number {
  return variant === 'soe' ? num(row.end_carrying) : num(row.end_amount)
}

/** 是否合计行（`is_total` 优先，回退按标签去空白判定）。 */
export function isRestrictedTotalRow(row: RestrictedAssetsNoteRow): boolean {
  if (row?.is_total) return true
  const label = String(row?.label ?? '').replace(/\s+/g, '')
  return label === '合计' || label === '小计'
}

export interface RestrictedConsistencyInput {
  variant: RestrictedAssetsVariant
  /** 附注侧现存行（主表 / soe 单表；listed 续表另传一次，列会自动切换） */
  rows: readonly RestrictedAssetsNoteRow[]
  /**
   * 各 owner 循环底稿侧的受限金额（期末）。
   * **只传已接入且真有数据的 owner**；缺的段 skip 不 error。
   */
  ownerAmounts?: Partial<Record<RestrictedAssetsOwner, number>>
  /** 续表口径（listed 「（续：上年年末）」）→ 取 `prior_amount` 列 */
  usePriorColumn?: boolean
}

/**
 * 计算勾稽结论。返回顺序稳定：合计勾稽 → 各段比对（按 owner 声明顺序）→ `_seg` 泄漏。
 */
export function computeRestrictedAssetsConsistency(
  input: RestrictedConsistencyInput,
): RestrictedCheck[] {
  const { variant, rows: allRows, ownerAmounts, usePriorColumn } = input
  const rows = (allRows || []).filter((r) => !!r)
  const pick = (r: RestrictedAssetsNoteRow): number =>
    usePriorColumn ? num(r.prior_amount) : endOf(variant, r)

  const dataRows = rows.filter((r) => !isRestrictedTotalRow(r))
  const totalRow = rows.find((r) => isRestrictedTotalRow(r))
  const out: RestrictedCheck[] = []

  // ── Check 1：合计行 = 全部数据行之和（含无主行「其他」）─────────────────────
  const dataSum = dataRows.reduce((s, r) => s + pick(r), 0)
  if (!totalRow) {
    out.push({
      label: '合计勾稽',
      rule: '合计行 = 各资产类别行之和（含「其他」无主行）',
      left: null,
      right: dataSum,
      diff: null,
      level: 'skip',
      detail:
        variant === 'soe'
          ? '国企源模板本表无合计行（9 行止于「其他」）→ 不做合计勾稽，也不得凭空补合计行'
          : '本表暂无合计行，跳过合计勾稽',
      refs: [],
    })
  } else {
    const declared = pick(totalRow)
    const diff = declared - dataSum
    out.push({
      label: '合计勾稽',
      rule: '合计行 = 各资产类别行之和（含「其他」无主行）',
      left: declared,
      right: dataSum,
      diff,
      level: Math.abs(diff) <= RESTRICTED_TOLERANCE ? 'ok' : 'error',
      detail:
        Math.abs(diff) <= RESTRICTED_TOLERANCE
          ? '合计与各段之和一致'
          : `合计行与各段之和差 ${diff.toFixed(2)}（合计行由附注侧维护，不属任何 owner 的可写区）`,
      refs: [],
    })
  }

  // ── Check 2：逐段比对（未提供底稿金额的段 skip）───────────────────────────────
  for (const owner of Object.keys(RESTRICTED_ASSETS_OWNERS) as RestrictedAssetsOwner[]) {
    if (!isRestrictedAssetsOwnerApplicable(variant, owner)) continue
    const segRows = dataRows.filter((r) => resolveRestrictedRowOwner(r) === owner)
    const noteAmount = segRows.reduce((s, r) => s + pick(r), 0)
    const label = `${RESTRICTED_ASSETS_OWNERS[owner]}（${owner}）`
    const wpAmount = ownerAmounts?.[owner]
    if (wpAmount === undefined || wpAmount === null) {
      out.push({
        label,
        rule: '附注该段金额 = 该循环底稿受限金额',
        left: noteAmount,
        right: null,
        diff: null,
        level: 'skip',
        detail: '未提供该循环底稿受限金额（尚未接入推送 / 或由审计师在附注模块直接维护）',
        refs: [owner],
      })
      continue
    }
    const diff = noteAmount - num(wpAmount)
    out.push({
      label,
      rule: '附注该段金额 = 该循环底稿受限金额',
      left: noteAmount,
      right: num(wpAmount),
      diff,
      level: Math.abs(diff) <= RESTRICTED_TOLERANCE ? 'ok' : 'error',
      detail:
        Math.abs(diff) <= RESTRICTED_TOLERANCE
          ? '与底稿一致'
          : `差 ${diff.toFixed(2)} —— 附注侧可能被手工改过，或底稿改动后未重新同步`,
      refs: [owner],
    })
  }

  // ── Check 3：`_seg` 段戳不得泄漏到附注行 ─────────────────────────────────────
  const leaked = rows.filter((r) => '_seg' in (r as object)).length
  if (leaked) {
    out.push({
      label: '_seg 段戳泄漏',
      rule: '行级合并的 `_seg` 戳只用于服务端段定位，读时投影必须剥离',
      left: leaked,
      right: 0,
      diff: leaked,
      level: 'error',
      detail: `${leaked} 行带 _seg 段戳（属平台缺陷，会在附注渲染出一列垃圾）`,
      refs: [],
    })
  }

  return out
}

/** 汇总（供紧凑单行 bar 展示）。 */
export function summarizeRestrictedChecks(checks: readonly RestrictedCheck[]): {
  ok: number
  error: number
  skip: number
  total: number
} {
  let ok = 0
  let error = 0
  let skip = 0
  for (const c of checks || []) {
    if (c.level === 'ok') ok++
    else if (c.level === 'error') error++
    else if (c.level === 'skip') skip++
  }
  return { ok, error, skip, total: (checks || []).length }
}
