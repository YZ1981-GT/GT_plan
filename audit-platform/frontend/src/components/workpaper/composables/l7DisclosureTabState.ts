/**
 * L7 其他非流动负债披露表：表单初值、读回与同步快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `L7TabDisclosureListed` / `L7TabDisclosureSoe` 原先在组件里内联「默认行 → onMounted / 审定事件时 restoreRows 读回已存的整表
 * （兼容旧版逐格键）→ 同步时去掉空行名、投影成载荷行」；原样抽到这里，Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节
 * 相同的载荷。只做计算：读回结果由调用方赋值（`null` = 保持原值，与原 restoreRows「没有已存就不改」一致）；持久化、提示、事件、
 * AI 留在 Tab。
 *
 * 🔴 原样保留的现有行为（未改，见报告疑点）：整表键读回成功就直接返回，结论（国企另有专项说明）不再读回。
 */
import type { L7SyncSnapshot } from './l7NoteSectionMap'

/** 底稿回复（Tab 的 `useL7FormData().allResponses` / 离屏框架读回的回复，同口径：只含 L7- 条目） */
export type L7DisclosureResponses = ReadonlyMap<string, { remark: string | null }>

/** 整表 JSON 持久化键（旧版是逐格 `L7-disclosure-{listed|soe}-{i}-{field}`，读回时兼容） */
export const L7_DISCLOSURE_ROWS_ITEM_ID = {
  listed: 'L7-disclosure-listed-rows',
  soe: 'L7-disclosure-soe-rows',
} as const

function savedText(responses: L7DisclosureResponses, itemId: string): string | null {
  const saved = responses.get(itemId)?.remark
  return saved ? String(saved) : null
}

// ═══ 上市（五、52：项目 | 期末数 | 上年年末数）═══

export interface L7ListedDisclosureRow { item: string; endAmount: number; priorYearEnd: number }

/**
 * 源模板 五、52 是**空行骨架**（r7~r11 五个空行，无固定行名）→ 默认给 5 个
 * 常见项目名作示例、行名可编辑可增删，避免把示例名当披露内容写死。
 */
export function createL7ListedDisclosureRows(): L7ListedDisclosureRow[] {
  return [
    { item: '递延收益', endAmount: 0, priorYearEnd: 0 },
    { item: '长期保证金/押金', endAmount: 0, priorYearEnd: 0 },
    { item: '政府补助（非流动）', endAmount: 0, priorYearEnd: 0 },
    { item: '预收款项（非流动）', endAmount: 0, priorYearEnd: 0 },
    { item: '其他', endAmount: 0, priorYearEnd: 0 },
  ]
}

export interface L7ListedRestored {
  /** 读回的行（null = 没有已存，保持原值） */
  rows: L7ListedDisclosureRow[] | null
  /** 核对结论（null = 不改） */
  conclusion: string | null
}

/** 上市读回（Tab onMounted / 审定事件的 restoreRows）：整表键优先，其次旧版逐格键 */
export function restoreL7ListedDisclosure(responses: L7DisclosureResponses): L7ListedRestored {
  const packed = responses.get(L7_DISCLOSURE_ROWS_ITEM_ID.listed)?.remark
  if (packed) {
    try {
      const parsed = JSON.parse(packed)
      if (Array.isArray(parsed) && parsed.length) {
        return {
          rows: parsed.map((r: any) => ({
            item: String(r?.item ?? ''),
            endAmount: Number(r?.endAmount) || 0,
            priorYearEnd: Number(r?.priorYearEnd) || 0,
          })),
          conclusion: null,
        }
      }
    } catch { /* 落到旧格式兼容 */ }
  }
  // 旧格式：逐格 `L7-disclosure-listed-{index}-{field}`（含被当数据行的第 6 行合计，丢弃）
  const rows = createL7ListedDisclosureRows()
  let touched = false
  rows.forEach((row, i) => {
    for (const field of ['endAmount', 'priorYearEnd'] as const) {
      const raw = responses.get(`L7-disclosure-listed-${i}-${field}`)?.remark
      if (raw != null && raw !== '') {
        const n = Number(raw)
        if (Number.isFinite(n)) { row[field] = n; touched = true }
      }
    }
  })
  return { rows: touched ? rows : null, conclusion: savedText(responses, 'L7-disc-listed-conclusion') }
}

/** 上市同步快照 → `buildL7SyncPayload(wpId, snapshot)`（空行名不推；合计由 builder 重算） */
export function buildL7ListedDisclosureSnapshot(rows: readonly L7ListedDisclosureRow[]): L7SyncSnapshot {
  return {
    variant: 'listed',
    rows: rows
      .filter((r) => String(r.item ?? '').trim())
      .map((r) => ({
        label: r.item,
        endAmount: Number(r.endAmount) || 0,
        priorAmount: Number(r.priorYearEnd) || 0,
      })),
  }
}

// ═══ 国企（八、57：项目 | 年初余额 | 期末余额）═══

export interface L7SoeDisclosureRow { item: string; beginBalance: number; endBalance: number }

/** 源模板 八、57 数据行取模板 seed（待转销项税额 / 合同负债），行名可编辑可增删 */
export function createL7SoeDisclosureRows(): L7SoeDisclosureRow[] {
  return [
    { item: '待转销项税额', beginBalance: 0, endBalance: 0 },
    { item: '合同负债', beginBalance: 0, endBalance: 0 },
    { item: '', beginBalance: 0, endBalance: 0 },
  ]
}

export interface L7SoeRestored {
  /** 读回的行（null = 没有已存，保持原值） */
  rows: L7SoeDisclosureRow[] | null
  /** 国资体系专项说明（null = 不改；不进附注） */
  special: string | null
  /** 核对结论（null = 不改） */
  conclusion: string | null
}

/** 国企读回（Tab onMounted / 审定事件的 restoreRows）：整表键优先，其次旧版逐格键 */
export function restoreL7SoeDisclosure(responses: L7DisclosureResponses): L7SoeRestored {
  const packed = responses.get(L7_DISCLOSURE_ROWS_ITEM_ID.soe)?.remark
  if (packed) {
    try {
      const parsed = JSON.parse(packed)
      if (Array.isArray(parsed) && parsed.length) {
        return {
          rows: parsed.map((r: any) => ({
            item: String(r?.item ?? ''),
            beginBalance: Number(r?.beginBalance) || 0,
            endBalance: Number(r?.endBalance) || 0,
          })),
          special: null,
          conclusion: null,
        }
      }
    } catch { /* 落到旧格式兼容 */ }
  }
  // 旧格式：逐格 `L7-disclosure-soe-{index}-{field}`（旧默认 5 行 + 第 6 行合计，合计丢弃）
  const legacyDefaults = ['递延收益', '长期保证金/押金', '政府补助（非流动）', '预收款项（非流动）', '其他']
  const rows: L7SoeDisclosureRow[] = legacyDefaults.map((item) => ({ item, beginBalance: 0, endBalance: 0 }))
  let touched = false
  rows.forEach((row, i) => {
    for (const field of ['beginBalance', 'endBalance'] as const) {
      const raw = responses.get(`L7-disclosure-soe-${i}-${field}`)?.remark
      if (raw != null && raw !== '') {
        const n = Number(raw)
        if (Number.isFinite(n)) { row[field] = n; touched = true }
      }
    }
  })
  return {
    rows: touched ? rows : null,
    special: savedText(responses, 'L7-disclosure-soe-special'),
    conclusion: savedText(responses, 'L7-disc-soe-conclusion'),
  }
}

/**
 * 国企同步快照 → `buildL7SyncPayload(wpId, snapshot)`：底稿列序（年初 / 期末）投影成附注交付物口径
 * （期末 / 期初，与上市一致）；空行名不推，合计由 builder 重算。
 */
export function buildL7SoeDisclosureSnapshot(rows: readonly L7SoeDisclosureRow[]): L7SyncSnapshot {
  return {
    variant: 'soe',
    rows: rows
      .filter((r) => String(r.item ?? '').trim())
      .map((r) => ({
        label: r.item,
        endAmount: Number(r.endBalance) || 0,
        priorAmount: Number(r.beginBalance) || 0,
      })),
  }
}
