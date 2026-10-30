/**
 * L8 财务费用披露表：读回与同步快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `L8TabDisclosureListed` / `L8TabDisclosureSoe` 原先在组件里内联「onMounted / 审定事件时 _restoreData 读回 8 个录入键两期值
 * （新格式 `{current, prior}`；旧格式按自造行名映射）与说明 / 结论 → 同步时拼快照」；原样抽到这里，Tab 与离屏 provider 调同一份
 * 计算 ⇒ 两条路径发出逐字节相同的载荷。只做计算：读回结果由调用方赋值（`null` = 保持原值，与原 _restoreData「没有已存就不改」
 * 一致）；初值仍是 `createEmptyL8Period()`；持久化、提示、事件、AI 留在 Tab。
 */
import {
  createEmptyL8Period,
  type L8DisclosureVariant,
  type L8InputKey,
  type L8PeriodValues,
  type L8SyncSnapshot,
} from './l8NoteSectionMap'

/** 底稿回复（Tab 的 `useL8FormData().allResponses` / 离屏框架读回的回复，同口径：只含 L8- 条目） */
export type L8DisclosureResponses = ReadonlyMap<string, { remark: string | null }>

/** 录入行持久化键（只存 8 个录入键的两期值，派生行读时推导，派生值持久化会在编辑后错位） */
export const L8_DISCLOSURE_DATA_ITEM_ID = {
  listed: 'L8-disclosure-listed-data',
  soe: 'L8-disclosure-soe-data',
} as const satisfies Record<L8DisclosureVariant, string>

/**
 * 旧格式行名 → 源模板录入键。旧格式是自造行数组 `[{item, currentAmount, priorAmount}...]`（上市 7 行 / 国企 10 行），
 * 映射不到的行（如国企「其中：金融机构借款利息」）丢弃。
 */
const LEGACY_LABEL_TO_KEY: Record<L8DisclosureVariant, Record<string, L8InputKey>> = {
  listed: {
    '利息费用': 'interestTotal',
    '  其中：利息资本化金额': 'interestCapitalized',
    '减：利息资本化金额': 'interestCapitalized',
    '减：利息收入': 'interestIncome',
    '汇兑损益（净损失以"+"号列示）': 'exchangeLoss',
    '手续费': 'feeAndOther',
  },
  soe: {
    '利息费用': 'interestTotal',
    '减：利息资本化金额': 'interestCapitalized',
    '减：利息资本化': 'interestCapitalized',
    '减：利息收入': 'interestIncome',
    '汇兑损益（净损失以"+"号列示）': 'exchangeLoss',
    '手续费': 'feeAndOther',
  },
}

/** 说明 / 结论条目（Tab 保存同一组键） */
const TEXT_ITEM_ID = {
  listed: { note: 'L8-disclosure-listed-note', capitalization: 'L8-disclosure-listed-capitalization', conclusion: 'L8-disc-listed-conclusion' },
  soe: { note: 'L8-disclosure-soe-note', extra: 'L8-disclosure-soe-extra', conclusion: 'L8-disc-soe-conclusion' },
} as const

export interface L8RestoredDisclosure {
  /** 两期录入值（null = 没有已存 / 不认的格式，保持原值） */
  periods: { current: L8PeriodValues; prior: L8PeriodValues } | null
  /** 附注文本说明（null = 不改） */
  noteText: string | null
  /** 上市：利息资本化说明（进附注说明段）；国企恒 null */
  capitalizationNote: string | null
  /** 国企：国企专项披露事项（只作底稿分析留痕，不进附注）；上市恒 null */
  soeExtraNote: string | null
  /** 核对结论（null = 不改） */
  conclusion: string | null
}

function savedText(responses: L8DisclosureResponses, itemId: string): string | null {
  const saved = responses.get(itemId)
  return saved?.remark ? String(saved.remark) : null
}

function restorePeriods(
  variant: L8DisclosureVariant,
  responses: L8DisclosureResponses,
): L8RestoredDisclosure['periods'] {
  const data = responses.get(L8_DISCLOSURE_DATA_ITEM_ID[variant])
  if (data?.remark) {
    try {
      const parsed = JSON.parse(data.remark)
      if (parsed && !Array.isArray(parsed) && (parsed.current || parsed.prior)) {
        return {
          current: { ...createEmptyL8Period(), ...(parsed.current || {}) },
          prior: { ...createEmptyL8Period(), ...(parsed.prior || {}) },
        }
      } else if (Array.isArray(parsed)) {
        const legacy = LEGACY_LABEL_TO_KEY[variant]
        const c = createEmptyL8Period()
        const p = createEmptyL8Period()
        for (const r of parsed) {
          const key = legacy[String(r?.item ?? '')]
          if (!key) continue
          c[key] = Number(r?.currentAmount) || 0
          p[key] = Number(r?.priorAmount) || 0
        }
        return { current: c, prior: p }
      }
    } catch { /* ignore */ }
  }
  return null
}

/** 读回（Tab onMounted / 审定事件的 _restoreData）：两期录入值 + 说明 / 结论 */
export function restoreL8Disclosure(variant: L8DisclosureVariant, responses: L8DisclosureResponses): L8RestoredDisclosure {
  const periods = restorePeriods(variant, responses)
  if (variant === 'listed') {
    const keys = TEXT_ITEM_ID.listed
    return {
      periods,
      noteText: savedText(responses, keys.note),
      capitalizationNote: savedText(responses, keys.capitalization),
      soeExtraNote: null,
      conclusion: savedText(responses, keys.conclusion),
    }
  }
  const keys = TEXT_ITEM_ID.soe
  return {
    periods,
    noteText: savedText(responses, keys.note),
    capitalizationNote: null,
    soeExtraNote: savedText(responses, keys.extra),
    conclusion: savedText(responses, keys.conclusion),
  }
}

/**
 * 同步快照 → `buildL8SyncPayload(wpId, snapshot)`：两期录入值（派生行与合计由 builder 推导）；只有上市带利息资本化说明
 * （源 xlsx r19/r20，国企源模板无此段）。
 */
export function buildL8DisclosureSnapshot(
  variant: L8DisclosureVariant,
  state: { current: L8PeriodValues; prior: L8PeriodValues; capitalizationNote?: string },
): L8SyncSnapshot {
  return variant === 'listed'
    ? { variant: 'listed', current: state.current, prior: state.prior, capitalizationNote: state.capitalizationNote }
    : { variant: 'soe', current: state.current, prior: state.prior }
}
