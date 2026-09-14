/**
 * 受限资产各 owner 的**数据来源声明表**（纯函数，零 Vue 依赖）。
 *
 * 🔴 核心洞察：各循环的受限金额都是**底稿事实**而非「披露变体产物」——
 * 它们持久化在 `checklist_responses` 里（`D2-pledge-rows` / `H1-listed-mortgage-rows`
 * / `H2-listed-mortgage-rows` / `I1-8-rows`），**与 listed/soe 变体无关**。
 * 变体只决定附注怎么呈现（listed 2 列双期拆两表 / soe 3 列含受限原因），
 * 不决定底稿有没有这个事实。
 *
 * 所以采集逻辑可以集中声明在这里，各披露 Tab 只需一行调用
 * `useRestrictedAssetsSync`。后续 owner 接入 = 在本表加一条声明。
 *
 * **只取期末口径**：这四个来源的受限表都只有期末数（质押金额 / 抵押价值 /
 * 抵押对应账面净值），没有上年年末列 → `priorAmount` **不声明**，共享件据此
 * 只推 listed 主表、不推「（续：上年年末）」（推 0 会覆盖审计师在续表手填的值）。
 * 用户口径：「有些表只有期末数，直接接期末数即可，不需要期初」。
 *
 * spec: .kiro/specs/restricted-assets-note-row-scope-rollout/ Requirement 3
 */
import type { RestrictedAssetsOwner } from './restrictedAssetsNoteSectionMap'

/** 一条受限明细（供 `summarizeRestrictedRows` 归纳成段内一行）。 */
export interface RestrictedDetail {
  endAmount?: number
  /** 仅当该循环**确实有**上年年末/期初数据时才声明（`undefined` ≠ 0） */
  priorAmount?: number
  reason?: string
}

/** `checklist_responses` 的最小读接口（`{item_id → {remark}}`）。 */
export type ResponseMap = Map<string, { remark?: string | null } | undefined>

export interface RestrictedAssetsSource {
  owner: RestrictedAssetsOwner
  /** 归属循环（wp_code），供事件广播与溯源展示 */
  wpCode: string
  /** 读取的 `checklist_responses.item_id` 清单（含 legacy 兼容键，按优先级） */
  itemIds: readonly string[]
  /** 该来源的中文说明 */
  note: string
  /** 从响应映射里抽出受限明细（纯函数，取不到返 `[]`） */
  collect: (responses: ResponseMap) => RestrictedDetail[]
}

const num = (v: unknown): number => {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

const text = (v: unknown): string => String(v ?? '').trim()

/** 读第一个能解析出**非空数组**的 item（支持 legacy 键回退）。 */
export function readRestrictedRows(responses: ResponseMap, itemIds: readonly string[]): any[] {
  for (const id of itemIds) {
    const raw = responses?.get?.(id)?.remark
    if (!raw) continue
    try {
      const parsed = JSON.parse(String(raw))
      if (Array.isArray(parsed) && parsed.length) return parsed
    } catch {
      // 非 JSON（自由文本）→ 跳过，试下一个键
    }
  }
  return []
}

/** 限定词最长字数（超出视为「长串数据倾倒」丢弃）。 */
const REASON_PART_MAX = 16
/** 去重后最多列举几条原因（防一行塞几十个质权人）。 */
export const REASON_CAP = 3
/** 超出 `REASON_CAP` 后的概括词。 */
export const REASON_ELLIPSIS = '等'

/**
 * 「抵押/担保（限制性质，…）」式原因文案。
 *
 * 🔴 **只收短限定词**（≤16 字）：底稿里的 `description` 是拼接出来的长串
 * （`权利限制:抵押；性质:…；抵押/账面金额:1,234,567`），塞进附注「受限原因」列
 * 会变成不可读的数据倾倒 → 一律不用它，只用 `质权人 / 质押目的 / 抵押性质`
 * 这类审计师手填的短字段。
 */
function reasonOf(action: string, ...parts: unknown[]): string {
  const extra = parts.map(text).filter((s) => !!s && s.length <= REASON_PART_MAX)
  return extra.length ? `${action}（${extra.join('，')}）` : action
}

/**
 * 原因收敛：去重后最多保留 `REASON_CAP` 条，其余统一写成「等」。
 *
 * 金额**一律不动**（受限金额必须完整求和）；只压缩原因文案。
 */
export function condenseReasons(details: readonly RestrictedDetail[]): RestrictedDetail[] {
  const kept: string[] = []
  return (details || []).map((d) => {
    const reason = text(d.reason)
    if (!reason) return { ...d, reason: '' }
    if (kept.includes(reason)) return { ...d, reason }
    if (kept.length < REASON_CAP) {
      kept.push(reason)
      return { ...d, reason }
    }
    return { ...d, reason: REASON_ELLIPSIS }
  })
}

/**
 * D2 应收账款（`BS-006`）—— 数据源 `D2-pledge-rows`（D2-12 质押/保理检查）。
 * 行字段 `PledgeRow`：`{ debtorName, pledgeAmount, pledgee, pledgePurpose, status }`。
 */
const D2_PLEDGE: RestrictedAssetsSource = {
  owner: 'BS-006',
  wpCode: 'D2',
  itemIds: ['D2-pledge-rows'],
  note: 'D2-12 质押检查表：已质押应收账款明细（质押金额 / 质权人 / 质押目的）',
  collect: (responses) =>
    condenseReasons(
      readRestrictedRows(responses, D2_PLEDGE.itemIds).map((r) => ({
        endAmount: num(r?.pledgeAmount),
        reason: reasonOf('已质押', r?.pledgee, r?.pledgePurpose),
      })),
    ),
}

/**
 * H1 固定资产（`BS-028`）—— 数据源 `H1-listed-mortgage-rows` /
 * `H1-soe-restricted-rows`（H1-16 房屋 + H1-17 车辆的抵押行，
 * 由 `useH1TitleCheck.syncMortgagedToDisclosure` **同时写入两个键**）。
 *
 * 行字段 `DisclosureRestrictedRow`：`{ name, amount, description, remark }`
 * （`amount` = 抵押金额，无则取账面净值 / 账面价值）。
 *
 * 🔴 两个键内容相同（同一次 merge 写入）→ 变体无关，任一有数据即用。
 */
const H1_MORTGAGE: RestrictedAssetsSource = {
  owner: 'BS-028',
  wpCode: 'H1',
  itemIds: [
    'H1-listed-mortgage-rows',
    'H1-soe-restricted-rows',
    // legacy：上市旧键，仅 hydrate 读取
    'H1-disc-listed-restricted-rows',
  ],
  note: 'H1-16/H1-17 权属检查带入的抵押固定资产明细（抵押金额，无则账面净值）',
  collect: (responses) =>
    condenseReasons(
      readRestrictedRows(responses, H1_MORTGAGE.itemIds).map((r) => ({
        endAmount: num(r?.amount ?? r?.mortgageAmount ?? r?.netValue ?? r?.bookValue),
        reason: reasonOf('抵押/担保', r?.mortgageNature),
      })),
    ),
}

/**
 * H2 在建工程（`BS-029`，**段仅 soe**）—— 数据源 `H2-listed-mortgage-rows`
 * （由 H2-2 明细 `isMortgaged='Y'` 经 `mapMortgagedDetailToRows` 带入）。
 *
 * 行字段 `ListedMortgageRow`：`{ name, amount, description }`
 * （`amount` = 审定净值 / 审定余额 / 在建工程期末，优先审定净值）。
 *
 * 🔴 键名带 `listed` 是**历史命名**，内容是底稿事实（哪些在建工程被抵押）；
 * 而本表的在建工程段**只在 soe `八、93`** 有落点（listed `五、32` 无该行）
 * → 只有 soe Tab 会调用它，共享件的 `isRestrictedAssetsOwnerApplicable`
 * 亦对 listed 返 false 双重保险。
 */
const H2_MORTGAGE: RestrictedAssetsSource = {
  owner: 'BS-029',
  wpCode: 'H2',
  itemIds: ['H2-listed-mortgage-rows'],
  note: 'H2-2 明细 isMortgaged=Y 带入的抵押在建工程（金额优先取审定净值）',
  collect: (responses) =>
    condenseReasons(
      readRestrictedRows(responses, H2_MORTGAGE.itemIds).map((r) => ({
        endAmount: num(r?.amount ?? r?.netEndAud ?? r?.endAudited),
        reason: '抵押/担保',
      })),
    ),
}

/**
 * I1 无形资产（`BS-032`）—— 数据源 `I1-8-rows`（无形资产权属检查表）。
 *
 * 行字段 `I1TitleRow`：`{ name, mortgageRestricted: 'Y'|'N'|'', mortgageValue, mortgageNature }`。
 * 只取 `mortgageRestricted === 'Y'` 的行，金额取「抵押价值」`mortgageValue`
 * （与 `useI1TitleCheck.totalMortgage` 同口径）。
 */
const I1_TITLE_CHECK: RestrictedAssetsSource = {
  owner: 'BS-032',
  wpCode: 'I1',
  itemIds: ['I1-8-rows'],
  note: 'I1-8 权属检查表：mortgageRestricted=Y 的行，金额取「抵押价值」mortgageValue',
  collect: (responses) =>
    condenseReasons(
      readRestrictedRows(responses, I1_TITLE_CHECK.itemIds)
        .filter((r) => text(r?.mortgageRestricted).toUpperCase() === 'Y')
        .map((r) => ({
          endAmount: num(r?.mortgageValue ?? r?.pledgeAmount),
          reason: reasonOf('抵押/受限', r?.mortgageNature),
        })),
    ),
}

/**
 * 声明表 —— **owner → 来源**。
 *
 * E1（`BS-002`）与 D1（`BS-005`）不在此表：它们的受限数据是披露 Tab 的**内存行模型**
 * （E1 ②表 `restrictedRows` / D1 `pledgedRows`），已在各自 Tab 内直接接线；
 * 本表专供「数据在 `checklist_responses` 里、可跨 Tab 读」的 owner。
 */
export const RESTRICTED_ASSETS_SOURCES: readonly RestrictedAssetsSource[] = Object.freeze([
  D2_PLEDGE,
  H1_MORTGAGE,
  H2_MORTGAGE,
  I1_TITLE_CHECK,
])

export function findRestrictedAssetsSource(
  owner: RestrictedAssetsOwner,
): RestrictedAssetsSource | undefined {
  return RESTRICTED_ASSETS_SOURCES.find((s) => s.owner === owner)
}

/**
 * 未接入的 owner + 理由（**只许缩不许扩**，守卫据此断言完备性）。
 *
 * 这两个是**真的没有数据**（不是「只有期末数」也不是「数据在别的 Tab」）：
 * 全量扫过各自循环的披露组件 / 映射 / composable / 底稿 Tab，对
 * 质押·抵押·受限·冻结·查封 零命中，没有任何结构化受限金额可推。
 */
export const RESTRICTED_ASSETS_UNSOURCED: Readonly<Record<string, string>> = Object.freeze({
  'BS-007':
    'D5 应收款项融资：披露 Tab 与底稿均无受限资产录入位置（该段为 soe 专有），无结构化受限金额可推',
  'BS-010':
    'F2 存货：披露侧对 质押/抵押/受限/冻结/查封 零命中，底稿侧亦无受限金额字段，无数据可推',
})
