/**
 * K6 持有待售披露 Tab 的资产主表 + 附注说明 + 载荷组装（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 由 `K6TabDisclosureListed` / `K6TabDisclosureSoe` 原样抽出：挂载时读回已保存的资产主表（没有 / 解析失败用默认分类 + 合计行）
 * 与附注说明，再按 `K6-2-rows` 明细按类别聚合自动取数（先清零非合计行、找不到类别归「其他非流动资产 / 其他」、重算合计）；
 * 「同步到附注」把主表非合计行 + 附注 4 个录入区块（`useK6NoteBlocks`）组装成载荷 —— 上市 五、11 一条；国企 八、12 一条 +
 * 持有待售负债 八、43 一条（独立章节，空行也发清理载荷）。Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。
 * 负债汇总表、CAS42 减值损失 / 处置组损益（都不进载荷）、保存、提示、AI、事件留在 Tab。
 *
 * 行身份由调用方注入（`newRow`）：Tab 传共享工厂（上市 `newRowIdentity('asset')` / 国企 `newRowIdentity('soe-asset')`）；
 * 离屏 provider 的行只进载荷、不落库，传空串即可。
 */
import {
  buildK6SoeLiabilityPayload,
  buildK6SyncPayload,
  type K6DisclosureRow,
  type K6DisclosureVariant,
  type K6SyncPayload,
} from './k6NoteSectionMap'
import type { K6NoteBlocks } from './useK6NoteBlocks'

/** 上市资产主表行（整表存在 `K6-disclosure-listed-asset-table` 的 remark） */
export interface K6ListedAssetRow {
  id: string
  category: string
  originalCost: number
  accumulatedDep: number
  impairment: number
  bookValue: number       // 公式：原值 - 折旧 - 减值
  fairValue: number
  sellingCost: number
  fairValueNet: number    // 公式：公允 - 出售费用
  openingBalance: number
  closingBalance: number
  remark: string
  isTotal: boolean
  isAutoFill: boolean
}

/** 国企资产汇总表行（整表存在 `K6-disclosure-soe-asset-table` 的 remark） */
export interface K6SoeAssetRow {
  id: string
  category: string
  bookValue: number
  impairment: number
  fairValueNet: number
  openingBalance: number
  closingBalance: number
  disposalProgress: string
  approvalStatus: string
  isTotal: boolean
  isAutoFill: boolean
}

export type K6AssetRow = K6ListedAssetRow | K6SoeAssetRow

export type K6NewRowId = () => string

export const K6_DISCLOSURE_ITEM_KEYS = {
  listed: { assets: 'K6-disclosure-listed-asset-table', narrative: 'K6-disclosure-listed-narrative' },
  soe: { assets: 'K6-disclosure-soe-asset-table', narrative: 'K6-disclosure-soe-narrative' },
} as const satisfies Record<K6DisclosureVariant, { assets: string; narrative: string }>

/** 无保存表时的默认分类；明细里找不到类别的行归最后一类（上市「其他非流动资产」/ 国企「其他」） */
export const K6_DEFAULT_ASSET_CATEGORIES: Readonly<Record<K6DisclosureVariant, readonly string[]>> = {
  listed: ['固定资产', '在建工程', '无形资产', '长期股权投资', '投资性房地产', '其他非流动资产'],
  soe: ['固定资产', '在建工程', '无形资产', '长期股权投资', '其他'],
}

type Responses = ReadonlyMap<string, any>

export function k6DefaultAssetTable(variant: 'listed', newRow: K6NewRowId): K6ListedAssetRow[]
export function k6DefaultAssetTable(variant: 'soe', newRow: K6NewRowId): K6SoeAssetRow[]
export function k6DefaultAssetTable(variant: K6DisclosureVariant, newRow: K6NewRowId): K6AssetRow[]
export function k6DefaultAssetTable(variant: K6DisclosureVariant, newRow: K6NewRowId): K6AssetRow[] {
  if (variant === 'listed') {
    const blank = (id: string, category: string, isTotal: boolean): K6ListedAssetRow => ({
      id,
      category,
      originalCost: 0,
      accumulatedDep: 0,
      impairment: 0,
      bookValue: 0,
      fairValue: 0,
      sellingCost: 0,
      fairValueNet: 0,
      openingBalance: 0,
      closingBalance: 0,
      remark: '',
      isTotal,
      isAutoFill: false,
    })
    return [...K6_DEFAULT_ASSET_CATEGORIES.listed.map((cat) => blank(newRow(), cat, false)), blank('asset-total', '合计', true)]
  }
  const blank = (id: string, category: string, isTotal: boolean): K6SoeAssetRow => ({
    id,
    category,
    bookValue: 0,
    impairment: 0,
    fairValueNet: 0,
    openingBalance: 0,
    closingBalance: 0,
    disposalProgress: '',
    approvalStatus: '',
    isTotal,
    isAutoFill: false,
  })
  return [...K6_DEFAULT_ASSET_CATEGORIES.soe.map((cat) => blank(newRow(), cat, false)), blank('soe-asset-total', '合计', true)]
}

/** 挂载时读回：已保存资产表（remark 能解析就用，原样不校验）→ 默认分类；附注说明没有（remark 为空）时为 null（Tab 保持原值） */
export function loadK6DisclosureState(responses: Responses, variant: 'listed', newRow: K6NewRowId):
  { assets: K6ListedAssetRow[]; narrative: string | null }
export function loadK6DisclosureState(responses: Responses, variant: 'soe', newRow: K6NewRowId):
  { assets: K6SoeAssetRow[]; narrative: string | null }
export function loadK6DisclosureState(responses: Responses, variant: K6DisclosureVariant, newRow: K6NewRowId):
  { assets: K6AssetRow[]; narrative: string | null }
export function loadK6DisclosureState(
  responses: Responses,
  variant: K6DisclosureVariant,
  newRow: K6NewRowId,
): { assets: K6AssetRow[]; narrative: string | null } {
  const keys = K6_DISCLOSURE_ITEM_KEYS[variant]
  let assets: K6AssetRow[]
  const saved = responses.get(keys.assets)
  if (saved?.remark) {
    try { assets = JSON.parse(saved.remark) } catch { assets = k6DefaultAssetTable(variant, newRow) }
  } else {
    assets = k6DefaultAssetTable(variant, newRow)
  }
  const savedNarrative = responses.get(keys.narrative)
  return { assets, narrative: savedNarrative?.remark ? savedNarrative.remark : null }
}

function recalcAssetTotals(assets: K6AssetRow[], variant: K6DisclosureVariant): void {
  const totalRow = assets.find((r) => r.isTotal)
  if (!totalRow) return
  const dataRows = assets.filter((r) => !r.isTotal)
  if (variant === 'listed') {
    const t = totalRow as K6ListedAssetRow
    const rows = dataRows as K6ListedAssetRow[]
    t.originalCost = rows.reduce((s, r) => s + r.originalCost, 0)
    t.accumulatedDep = rows.reduce((s, r) => s + r.accumulatedDep, 0)
    t.impairment = rows.reduce((s, r) => s + r.impairment, 0)
    t.bookValue = rows.reduce((s, r) => s + r.bookValue, 0)
    t.fairValue = rows.reduce((s, r) => s + r.fairValue, 0)
    t.sellingCost = rows.reduce((s, r) => s + r.sellingCost, 0)
    t.fairValueNet = rows.reduce((s, r) => s + r.fairValueNet, 0)
    t.openingBalance = rows.reduce((s, r) => s + r.openingBalance, 0)
    t.closingBalance = rows.reduce((s, r) => s + r.closingBalance, 0)
    return
  }
  totalRow.bookValue = dataRows.reduce((s, r) => s + r.bookValue, 0)
  totalRow.impairment = dataRows.reduce((s, r) => s + r.impairment, 0)
  totalRow.fairValueNet = dataRows.reduce((s, r) => s + r.fairValueNet, 0)
  totalRow.openingBalance = dataRows.reduce((s, r) => s + r.openingBalance, 0)
  totalRow.closingBalance = dataRows.reduce((s, r) => s + r.closingBalance, 0)
}

/**
 * 从 K6-2 明细表按类别聚合自动填充（K6-2 useK6Detail 持久化键为 K6-2-rows）。明细非空时先清零非合计行的取数字段再累加、
 * 重算合计行；返回是否用上了明细（Tab 据此显示「跨sheet自动取数」）。期初（openingBalance）不由明细带出，保持读回值。
 */
export function applyK6AssetAutoFill(assets: K6AssetRow[], responses: Responses, variant: K6DisclosureVariant): boolean {
  const k6_2 = responses.get('K6-2-rows')
  const raw = k6_2?.remark ?? (typeof k6_2 === 'string' ? k6_2 : null)
  if (!raw) return false
  let used = false
  try {
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows) || rows.length === 0) return false
    used = true
    const fallback = variant === 'listed' ? '其他非流动资产' : '其他'
    for (const row of assets) {
      if (row.isTotal) continue
      if (variant === 'listed') {
        const r = row as K6ListedAssetRow
        r.originalCost = 0; r.accumulatedDep = 0; r.impairment = 0
        r.bookValue = 0; r.fairValue = 0; r.sellingCost = 0; r.fairValueNet = 0
        r.closingBalance = 0; r.isAutoFill = false
      } else {
        row.bookValue = 0; row.impairment = 0; row.fairValueNet = 0; row.closingBalance = 0; row.isAutoFill = false
      }
    }
    for (const r of rows) {
      const cat = r.category || fallback
      let target = assets.find((x) => !x.isTotal && x.category === cat)
      if (!target) target = assets.find((x) => !x.isTotal && x.category === fallback)
      if (!target) continue
      if (variant === 'listed') {
        const t = target as K6ListedAssetRow
        t.originalCost += Number(r.costValue) || 0
        t.accumulatedDep += Number(r.accumulatedDep) || 0
        t.impairment += Number(r.impairmentProvision) || 0
        t.bookValue += Number(r.bookValue) || 0
        t.fairValue += Number(r.fairValue) || 0
        t.sellingCost += Number(r.sellingCost) || 0
        t.fairValueNet += Number(r.fairValueNet) || 0
        t.closingBalance += Number(r.bookValue) || 0
      } else {
        target.bookValue += Number(r.bookValue) || 0
        target.impairment += Number(r.impairmentProvision) || 0
        target.fairValueNet += Number(r.fairValueNet) || 0
        target.closingBalance += Number(r.bookValue) || 0
      }
      target.isAutoFill = true
    }
    recalcAssetTotals(assets, variant)
  } catch { /* silent */ }
  return used
}

/**
 * 主表 builder 行：剔合计行。附注主表两行表头 7 列（期末 / 期初各 [账面余额, 减值准备, 账面价值]）：期末账面价值取 `bookValue`
 * （与 `impairment` 同源，满足 F11-4 勾稽），期初只有 `openingBalance`（账面价值）有来源，账面余额 / 减值准备推 null（禁造数）。
 */
export function k6DisclosureSyncRows(assets: readonly K6AssetRow[]): K6DisclosureRow[] {
  return assets.filter((r) => !r.isTotal).map((r) => ({
    project: r.category,
    bookValue: r.bookValue ?? 0,
    impairment: r.impairment ?? 0,
    openingBalance: r.openingBalance ?? 0,
  }))
}

type K6BlockRefs = Pick<K6NoteBlocks, 'impairment' | 'nonCurrent' | 'disposalGroup' | 'liabilities' | 'listedLiabilities'>

/**
 * 「同步到附注」的载荷：`main` = 上市 五、11 / 国企 八、12；`liability` = 国企持有待售负债 八、43（独立章节，
 * `sync_from_workpaper` 一个载荷只能写一节；空行也发清理载荷），上市恒 null（负债并入 五、11）。
 */
export function k6DisclosurePayloads(
  variant: K6DisclosureVariant,
  wpId: string,
  assets: readonly K6AssetRow[],
  blocks: K6BlockRefs,
  narrative: string,
): { main: K6SyncPayload; liability: K6SyncPayload | null } {
  const rows = k6DisclosureSyncRows(assets)
  if (variant === 'listed') {
    return {
      main: buildK6SyncPayload('listed', wpId, {
        assets: rows,
        impairment: blocks.impairment.value,
        nonCurrent: blocks.nonCurrent.value,
        disposalGroup: blocks.disposalGroup.value,
        listedLiabilities: blocks.listedLiabilities.value,
        narrativeText: narrative,
      }),
      liability: null,
    }
  }
  return {
    main: buildK6SyncPayload('soe', wpId, {
      assets: rows,
      impairment: blocks.impairment.value,
      nonCurrent: blocks.nonCurrent.value,
      disposalGroup: blocks.disposalGroup.value,
      narrativeText: narrative,
    }),
    liability: buildK6SoeLiabilityPayload(wpId, blocks.liabilities.value, narrative),
  }
}
