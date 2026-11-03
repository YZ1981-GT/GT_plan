/**
 * K7 递延收益披露表：表单状态与同步快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `K7TabDisclosureListed` / `K7TabDisclosureSoe` 原先在组件里内联「读已保存行（缺失回默认行）→ 从 K7-1 审定表自动取数 →
 * 拼载荷行」；抽成本模块的纯函数后，Tab（onMounted / 同步按钮）与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。
 *
 * 行身份是 Tab 的编辑关注点（值化身份工厂 `newRowIdentity`，K 循环身份守卫钉在 Tab 源码上），由调用方经 `K7RowIdentity`
 * 传入；载荷不含身份，离屏传 `K7_HEADLESS_ROW_IDENTITY`。
 */
import type { K7DisclosureRow, K7DisclosureVariant, K7GrantDetailRow } from './k7NoteSectionMap'

/** 披露表行（与资产相关 / 与收益相关两张底稿表同结构；`reason` 只有上市版有） */
export interface K7DisclosureFormRow {
  id: string
  project: string
  beginBalance: number
  increase: number
  decrease: number
  reason?: string
  isTotal?: boolean
  isAutoFill?: boolean
}

/** 国企 八、56 表2「其中：递延收益-政府补助情况」底稿行（10 列，期末余额读时推导） */
export interface K7GrantFormRow {
  id: string
  grantItem: string
  beginBalance: number
  newGrant: number
  toPl: number
  plLineItem: string
  refund: number
  otherChange: number
  grantKind: string
  refundReason: string
}

export interface K7DisclosureFormState {
  assetRows: K7DisclosureFormRow[]
  incomeRows: K7DisclosureFormRow[]
  /** 只有国企版有（上市恒空） */
  grantRows: K7GrantFormRow[]
  narrativeText: string
}

/** 行身份：默认行按类别取新身份；已保存的政府补助明细行由调用方决定（Tab 沿用已存 id）。上市版没有明细表，可省。 */
export interface K7RowIdentity {
  newRow: (kind: 'asset' | 'income') => string
  grantRow?: (raw: any) => string
}

/** 离屏同步：载荷不含行身份 */
export const K7_HEADLESS_ROW_IDENTITY: Required<K7RowIdentity> = { newRow: () => '', grantRow: () => '' }

/** 底稿回复（只读 `remark`，与 Tab / 离屏框架两种来源同口径） */
export type K7DisclosureResponses = ReadonlyMap<string, { remark?: string | null } | undefined>

/** 底稿回复条目（与 Tab 持久化同名） */
const ITEM = {
  listed: {
    asset: 'K7-disclosure-listed-asset-rows',
    income: 'K7-disclosure-listed-income-rows',
    narrative: 'K7-disclosure-listed-narrative',
  },
  soe: {
    asset: 'K7-disclosure-soe-asset-rows',
    income: 'K7-disclosure-soe-income-rows',
    narrative: 'K7-disclosure-soe-narrative',
  },
} as const satisfies Record<K7DisclosureVariant, { asset: string; income: string; narrative: string }>
const SOE_GRANT_ITEM = 'K7-disclosure-soe-grant-rows'
/** K7-1 审定表按类型的审定数：`{ assetRelated: {项目: {beginBalance, increase, decrease}}, incomeRelated: … }` */
const AUDITED_BY_TYPE_ITEM = 'K7-1-audited-by-type'

const ASSET_DEFAULTS = ['设备购置补助', '厂房建设补助', '技改项目补助', '环保设备补助', '其他与资产相关补助']
const INCOME_DEFAULTS = ['研发费用补助', '稳岗补贴', '产业扶持资金', '出口退税补贴', '其他与收益相关补助']

/** 默认行（两张表各 5 个常见补助项目、金额 0）；上市版带空 `reason`、国企版没有该字段（与 Tab 持久化 JSON 逐字段一致）。 */
export function k7DefaultDisclosureRows(
  variant: K7DisclosureVariant,
  ids: K7RowIdentity,
): Pick<K7DisclosureFormState, 'assetRows' | 'incomeRows'> {
  const row = (kind: 'asset' | 'income', project: string): K7DisclosureFormRow => (variant === 'listed'
    ? { id: ids.newRow(kind), project, beginBalance: 0, increase: 0, decrease: 0, reason: '' }
    : { id: ids.newRow(kind), project, beginBalance: 0, increase: 0, decrease: 0 })
  return {
    assetRows: ASSET_DEFAULTS.map((name) => row('asset', name)),
    incomeRows: INCOME_DEFAULTS.map((name) => row('income', name)),
  }
}

/** 反序列化补齐字段（旧载荷可能缺列），防 undefined 进公式变 NaN；`id` 由调用方给。 */
export function normalizeK7GrantRow(raw: any, id: string): K7GrantFormRow {
  const n = (v: any): number => (typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0)
  return {
    id,
    grantItem: String(raw?.grantItem ?? ''),
    beginBalance: n(raw?.beginBalance),
    newGrant: n(raw?.newGrant),
    toPl: n(raw?.toPl),
    plLineItem: String(raw?.plLineItem ?? ''),
    refund: n(raw?.refund),
    otherChange: n(raw?.otherChange),
    grantKind: String(raw?.grantKind ?? ''),
    refundReason: String(raw?.refundReason ?? ''),
  }
}

/**
 * 读已保存的披露表（Tab onMounted 的 loadSavedData）：与资产相关行缺失 / 损坏 ⇒ 两张表都回默认行，
 * 与收益相关行另有保存时覆盖；明细表（国企）与说明各自缺失时为空。
 */
export function loadK7DisclosureState(
  responses: K7DisclosureResponses,
  variant: K7DisclosureVariant,
  ids: K7RowIdentity,
): K7DisclosureFormState {
  const keys = ITEM[variant]
  let assetRows: K7DisclosureFormRow[] = []
  let incomeRows: K7DisclosureFormRow[] = []
  const useDefaults = (): void => {
    ({ assetRows, incomeRows } = k7DefaultDisclosureRows(variant, ids))
  }
  const savedAsset = responses.get(keys.asset)
  if (savedAsset?.remark) {
    try {
      assetRows = JSON.parse(savedAsset.remark)
    } catch { useDefaults() }
  } else {
    useDefaults()
  }
  const savedIncome = responses.get(keys.income)
  if (savedIncome?.remark) {
    try {
      incomeRows = JSON.parse(savedIncome.remark)
    } catch { /* 保持上面的结果 */ }
  }
  let grantRows: K7GrantFormRow[] = []
  const savedGrant = variant === 'soe' ? responses.get(SOE_GRANT_ITEM) : undefined
  if (savedGrant?.remark) {
    try {
      const parsed = JSON.parse(savedGrant.remark)
      const grantId = ids.grantRow ?? ((raw: any) => String(raw?.id ?? ''))
      if (Array.isArray(parsed)) grantRows = parsed.map((raw) => normalizeK7GrantRow(raw, grantId(raw)))
    } catch { /* 保持空 */ }
  }
  const savedNarrative = responses.get(keys.narrative)
  return { assetRows, incomeRows, grantRows, narrativeText: savedNarrative?.remark ? savedNarrative.remark : '' }
}

function fillFromAudited(rows: K7DisclosureFormRow[], byProject: any): void {
  for (const row of rows) {
    const src = byProject[row.project]
    if (src) {
      row.beginBalance = Number(src.beginBalance ?? 0)
      row.increase = Number(src.increase ?? 0)
      row.decrease = Number(src.decrease ?? 0)
      row.isAutoFill = true
    }
  }
}

/**
 * 从 K7-1 审定表（`K7-1-audited-by-type`）按项目名回填期初 / 增加 / 减少（就地改行）。
 * 返回该条目是否存在（Tab 据此显示「已自动取数」提示；解析失败也算存在，与原实现一致）。
 */
export function applyK7AutoFill(
  responses: K7DisclosureResponses,
  assetRows: K7DisclosureFormRow[],
  incomeRows: K7DisclosureFormRow[],
): boolean {
  const adjData = responses.get(AUDITED_BY_TYPE_ITEM)
  if (!adjData?.remark) return false
  try {
    const data = JSON.parse(adjData.remark)
    if (data?.assetRelated) fillFromAudited(assetRows, data.assetRelated)
    if (data?.incomeRelated) fillFromAudited(incomeRows, data.incomeRelated)
  } catch { /* silent */ }
  return true
}

/** 明细表行 → 载荷行（去掉身份；期末余额由 builder 按 F51-7a~7d 推导） */
export function toK7GrantPayloadRow(row: K7GrantFormRow): K7GrantDetailRow {
  return {
    grantItem: row.grantItem,
    beginBalance: row.beginBalance,
    newGrant: row.newGrant,
    toPl: row.toPl,
    plLineItem: row.plLineItem,
    refund: row.refund,
    otherChange: row.otherChange,
    grantKind: row.grantKind,
    refundReason: row.refundReason,
  }
}

/**
 * 披露表 → `buildK7SyncPayload` 的入参：附注只有 1 张主表 ⇒ 两张底稿表的行拼成一个列表（上市带 `reason`，国企附注没有
 * 该列）；国企另带政府补助明细（有行才推由 builder 判）。
 */
export function buildK7DisclosureSnapshot(
  variant: K7DisclosureVariant,
  src: {
    assetRows: readonly K7DisclosureFormRow[]
    incomeRows: readonly K7DisclosureFormRow[]
    grantRows?: readonly K7GrantFormRow[]
  },
): { rows: K7DisclosureRow[]; grantRows: K7GrantDetailRow[] } {
  const rows = [...src.assetRows, ...src.incomeRows]
    .filter((r) => !r.isTotal)
    .map((r): K7DisclosureRow => (variant === 'listed'
      ? {
          project: r.project,
          beginBalance: r.beginBalance ?? 0,
          increase: r.increase ?? 0,
          decrease: r.decrease ?? 0,
          reason: r.reason ?? '',
        }
      : {
          project: r.project,
          beginBalance: r.beginBalance ?? 0,
          increase: r.increase ?? 0,
          decrease: r.decrease ?? 0,
        }))
  return { rows, grantRows: variant === 'soe' ? (src.grantRows ?? []).map(toK7GrantPayloadRow) : [] }
}
