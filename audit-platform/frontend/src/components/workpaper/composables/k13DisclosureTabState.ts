/**
 * K13 营业外支出披露 Tab 的表格行 + 附注说明（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 由 `K13TabDisclosureListed` / `K13TabDisclosureSoe` 原样抽出（两版分类不同、条目键按口径分）：挂载时按固定去向分类逐行读回
 * `K13-disc-{variant}-row-{i}` 与附注说明、追加已保存的动态去向行 `K13-disc-{variant}-dyn-*`，再从 K13-1 审定表取数（固定分类
 * 先精确后包含匹配；未匹配的审定表去向追加为动态行）；「同步到附注」把行映射成 builder 行（含第 4 列）。Tab 与离屏 provider
 * 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。取数后的逐行 / 动态行保存、提示、事件留在 Tab（经回调）。
 */
import type { K13DisclosureRow, K13DisclosureVariant } from './k13NoteSectionMap'

/** 营业外支出标准去向分类（与 K13-1 审定表行对应；国企版为精简分类） */
export const K13_DISCLOSURE_CATEGORIES: Readonly<Record<K13DisclosureVariant, readonly string[]>> = {
  listed: [
    '非流动资产毁损报废损失',
    '其中：固定资产处置损失',
    '其中：无形资产处置损失',
    '捐赠支出',
    '其中：公益性捐赠支出',
    '其中：非公益性捐赠支出',
    '债务重组损失',
    '罚款滞纳金支出',
    '其中：税务罚款',
    '其中：工商罚款',
    '其中：其他行政罚款',
    '资产盘亏损失',
    '非常损失',
    '其他',
  ],
  soe: [
    '非流动资产处置损失',
    '捐赠支出',
    '债务重组损失',
    '罚款滞纳金支出',
    '资产盘亏损失',
    '国有资产处置损失',
    '非常损失',
    '其他',
  ],
}

export interface K13DisclosureTabRow {
  category: string
  currentAmount: number
  priorAmount: number
  nonRecurring: number
  remark: string
}

/** 动态去向行（K13-1 中未匹配固定分类的去向）的条目前缀 */
export const K13_DISCLOSURE_DYN_PREFIX = {
  listed: 'K13-disc-listed-dyn-',
  soe: 'K13-disc-soe-dyn-',
} as const satisfies Record<K13DisclosureVariant, string>

export const K13_DISCLOSURE_NARRATIVE_ITEM = {
  listed: 'K13-disclosure-listed-narrative',
  soe: 'K13-disclosure-soe-narrative',
} as const satisfies Record<K13DisclosureVariant, string>

/**
 * 固定分类行逐行读回的条目。Tab 逐行保存写同形字面量 `K13-disc-{listed|soe}-row-${idx}`（原样留在 Tab）；两版各写一个
 * 字面量模板，不合成 `${variant}` —— K 循环键守卫（KF-P16 宽口径）按字面量模板计数。
 */
const K13_ROW_ITEM_ID: Record<K13DisclosureVariant, (i: number) => string> = {
  listed: (i) => `K13-disc-listed-row-${i}`,
  soe: (i) => `K13-disc-soe-row-${i}`,
}

type Responses = ReadonlyMap<string, any>

export function k13DefaultDisclosureRows(variant: K13DisclosureVariant): K13DisclosureTabRow[] {
  return K13_DISCLOSURE_CATEGORIES[variant].map((c) => ({
    category: c, currentAmount: 0, priorAmount: 0, nonRecurring: 0, remark: '',
  }))
}

/** 挂载时读回：按固定分类逐行读回（解析不了 / 空的行保持默认 0）；附注说明没有该条目时为 null（Tab 保持原值） */
export function loadK13DisclosureState(
  responses: Responses,
  variant: K13DisclosureVariant,
): { rows: K13DisclosureTabRow[]; narrative: string | null } {
  const categories = K13_DISCLOSURE_CATEGORIES[variant]
  const rows = k13DefaultDisclosureRows(variant)
  for (let i = 0; i < categories.length; i++) {
    const saved = responses.get(K13_ROW_ITEM_ID[variant](i))
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          rows[i] = {
            category: categories[i],
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            nonRecurring: Number(parsed.nonRecurring || 0),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore parse errors */ }
    }
  }
  const narrativeSaved = responses.get(K13_DISCLOSURE_NARRATIVE_ITEM[variant])
  return { rows, narrative: narrativeSaved ? (narrativeSaved.remark || narrativeSaved.conclusion || '') : null }
}

/** 追加已保存的动态去向行（按回复顺序；同名去向已在表里则跳过） */
export function loadK13DynamicRows(rows: K13DisclosureTabRow[], responses: Responses, variant: K13DisclosureVariant): void {
  const prefix = K13_DISCLOSURE_DYN_PREFIX[variant]
  for (const [key, val] of responses) {
    if (!key.startsWith(prefix)) continue
    try {
      const parsed = typeof val.remark === 'string' ? JSON.parse(val.remark) : val.remark
      if (parsed && parsed.category && !rows.some((r) => r.category === parsed.category)) {
        rows.push({
          category: parsed.category,
          currentAmount: Number(parsed.currentAmount || 0),
          priorAmount: Number(parsed.priorAmount || 0),
          nonRecurring: Number(parsed.nonRecurring || 0),
          remark: parsed.remark || '',
        })
      }
    } catch { /* ignore */ }
  }
}

/**
 * 从审定表 K13-1-rows 构建 名称→审定数 映射（P0 修复：原读 `K13-1-row-${i}-audited` 死键，useK13Adjudication 从不写
 * → 恒 no-op；改读 `K13-1-rows` 按 name 匹配）。
 */
export function k13AuditedByName(responses: Responses): Map<string, number> {
  const map = new Map<string, number>()
  const raw = responses.get('K13-1-rows')
  if (!raw) return map
  try {
    const parsed = typeof raw.remark === 'string' ? JSON.parse(raw.remark) : (raw.remark ?? raw.conclusion)
    if (Array.isArray(parsed)) {
      for (const r of parsed) {
        const name = String(r?.name ?? '').trim()
        if (!name) continue
        const audited = Number(r?.audited ?? 0)
          || (Number(r?.unadjusted ?? 0) + Number(r?.aje ?? 0) + Number(r?.rje ?? 0))
        map.set(name, audited)
      }
    }
  } catch { /* ignore */ }
  return map
}

export interface K13AutoFillHooks {
  /** 固定分类行被审定数覆盖后（Tab：逐行保存 + 排程自动同步） */
  onFixedFilled?: (row: K13DisclosureTabRow) => void
  /** 动态去向行被审定数覆盖 / 追加后（Tab：保存该动态行） */
  onDynamicFilled?: (row: K13DisclosureTabRow) => void
}

/**
 * 从审定表取数：固定分类先精确、后包含匹配，非零才写本期发生额；再追加已保存的动态行，K13-1 中未匹配任何固定分类的
 * 非零去向写进动态行（没有则新建）。回 null = 没有 K13-1 审定表数据（Tab 非静默时提示）。离屏不传回调 ⇒ 只改内存。
 */
export function applyK13AutoFill(
  rows: K13DisclosureTabRow[],
  responses: Responses,
  variant: K13DisclosureVariant,
  hooks: K13AutoFillHooks = {},
): { matched: number; totalAudited: number } | null {
  const adjMap = k13AuditedByName(responses)
  if (adjMap.size === 0) return null
  const categories = K13_DISCLOSURE_CATEGORIES[variant]
  const matchedNames = new Set<string>()
  let matched = 0
  for (let i = 0; i < categories.length; i++) {
    let val = adjMap.get(categories[i])
    let hitName = categories[i]
    if (val == null) {
      for (const [name, amt] of adjMap) {
        if (categories[i].includes(name) || name.includes(categories[i])) { val = amt; hitName = name; break }
      }
    }
    if (val != null && val !== 0) {
      rows[i].currentAmount = val
      hooks.onFixedFilled?.(rows[i])
      matchedNames.add(hitName)
      matched++
    }
  }
  const totalAudited = Array.from(adjMap.values()).reduce((s, v) => s + v, 0)

  // 追加：K13-1 中未匹配任何固定分类的去向 → 动态披露行
  loadK13DynamicRows(rows, responses, variant)
  for (const [name, amt] of adjMap) {
    if (matchedNames.has(name) || amt === 0) continue
    const existing = rows.find((r) => r.category === name)
    if (existing) {
      existing.currentAmount = amt
      hooks.onDynamicFilled?.(existing)
    } else {
      const row: K13DisclosureTabRow = { category: name, currentAmount: amt, priorAmount: 0, nonRecurring: 0, remark: '' }
      rows.push(row)
      hooks.onDynamicFilled?.(row)
    }
    matched++
  }
  return { matched, totalAudited }
}

/** 「同步到附注」的 builder 行（第 4 列「计入当期非经常性损益的金额」是源模板必填列，旧载荷从未推送） */
export function k13DisclosureSyncRows(rows: readonly K13DisclosureTabRow[]): K13DisclosureRow[] {
  return rows.map((r) => ({
    project: r.category,
    currentAmount: r.currentAmount,
    priorAmount: r.priorAmount,
    nonRecurringAmount: r.nonRecurring,
  }))
}
