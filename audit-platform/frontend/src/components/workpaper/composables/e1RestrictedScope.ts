/**
 * e1RestrictedScope — E1「受限制的货币资金明细」②表 的动态取数与人工归类
 *
 * **为什么必须动态**
 *
 * 受限资金没有独立标准科目 —— 它是货币资金（1001/1002/1012）里「用途受限」的
 * 那一部分，客户各自用二级/三级子科目承载，命名千差万别（活体项目 `df5b8403` 的
 * `1012` 叶子全是支付渠道名：金华支付宝 / 微信小程序 / 聚合收款 / AFO / 小桔有车）。
 *
 * 取数链路（后端 `four_table/e1_restricted_buckets.py` + render `restricted_prefill`）：
 *
 *   BS-002 报表行解析 → account_mapping 反解项目原始码 → select_leaves 取叶子
 *   → 逐叶子按**科目名**分类 → 命中落 buckets / 未命中落 unclassified
 *
 * 本模块负责前端侧：合并「人工归类」与「自动分类」，产出 ②表行。
 *
 * **🔴 中文标签只有后端一份** —— 桶的 label 从 render 下发的 `bucketDefs` 取
 * （`bucket_defs_payload()`）。本文件**不得**再抄一份桶中文名，否则后端改了前端不跟。
 * 拿不到 `bucketDefs` 时退化显示 key（宁可难看也不双真源）。
 *
 * **人工归类优先**：审计师在「待归类科目」面板把某叶子归入某类 / 标记不受限后，
 * 结果持久化到 `E1-disclosure-{variant}-restricted-map`（`原始科目码 → bucketKey |
 * '__unrestricted__'`）；下次刷新取数时人工归类**优先于**自动分类，四表新增的
 * 科目自动出现在 unclassified 而不改动已有类别行金额。
 *
 * spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
 *       Requirements 6.2, 6.4, 11.5~11.10 / Property 17
 */

/** 「标记为不受限」哨兵值（与后端 `e1_restricted_buckets.UNRESTRICTED` 一致）。 */
export const E1_UNRESTRICTED = '__unrestricted__'

// ─── render 下发的载荷 ────────────────────────────────────────────────────────

export interface E1RestrictedBucketDef {
  key: string
  /** 中文标签 —— **唯一来源是后端**，前端不抄第二份 */
  label: string
  /** 源模板无对应行的平台补充桶（如「其他受限资金」） */
  isPlatformExtra: boolean
}

/**
 * 货币资金三族的一个叶子科目。
 *
 * 🔴 后端下发的是**扁平叶子清单**而不是预聚合的桶 —— 预聚合是有损表示：
 * 审计师把某叶子改归到别的类别后，就无法重算被改动桶的余额。
 */
export interface E1RestrictedLeaf {
  code: string
  name: string
  opening: number
  closing: number
  /** 所属语义槽（cash / bank / other） */
  slot: string
  /** 按科目名自动分类的结果；`null` = 判不出来，须人工归类 */
  autoBucket: string | null
}

export interface E1RestrictedPrefill {
  leaves: E1RestrictedLeaf[]
  bucketDefs: E1RestrictedBucketDef[]
  source: { report_row_code?: string; chart_available?: boolean }
}

const num = (v: unknown): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0

/** 归一 render 载荷（缺字段按空处理，不抛）。 */
export function normalizeRestrictedPrefill(raw: unknown): E1RestrictedPrefill {
  const p = (raw ?? {}) as Record<string, unknown>
  return {
    leaves: Array.isArray(p.leaves)
      ? (p.leaves as unknown[]).map((x) => {
          const r = (x ?? {}) as Record<string, unknown>
          const auto = r.autoBucket
          return {
            code: String(r.code ?? ''),
            name: String(r.name ?? ''),
            opening: num(r.opening),
            closing: num(r.closing),
            slot: String(r.slot ?? ''),
            autoBucket: auto == null || auto === '' ? null : String(auto),
          }
        })
      : [],
    bucketDefs: Array.isArray(p.bucketDefs)
      ? (p.bucketDefs as unknown[]).map((x) => {
          const r = (x ?? {}) as Record<string, unknown>
          return {
            key: String(r.key ?? ''),
            label: String(r.label ?? ''),
            isPlatformExtra: !!r.isPlatformExtra,
          }
        })
      : [],
    source: (p.source ?? {}) as E1RestrictedPrefill['source'],
  }
}

// ─── 人工归类 map ─────────────────────────────────────────────────────────────

/** `原始科目码 → bucketKey | E1_UNRESTRICTED`。 */
export type E1RestrictedManualMap = Record<string, string>

export function parseManualMap(raw: unknown): E1RestrictedManualMap {
  if (typeof raw !== 'string' || !raw.trim()) return {}
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: E1RestrictedManualMap = {}
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      const code = String(k).trim()
      const target = String(v ?? '').trim()
      if (code && target) out[code] = target
    }
    return out
  } catch {
    return {}
  }
}

export function serializeManualMap(map: E1RestrictedManualMap): string {
  return JSON.stringify(map ?? {})
}

/** 人工归类持久化键（按变体分开，上市/国企各自归类互不干扰）。 */
export function e1RestrictedMapKey(variant: 'listed' | 'soe'): string {
  return `E1-disclosure-${variant}-restricted-map`
}

// ─── ②表行 ────────────────────────────────────────────────────────────────────

export interface E1RestrictedRow {
  /** 稳定 key（`restricted_{bucketKey|custom}_{seq}`，**禁用 label 作 key**） */
  id: string
  /** 桶 key；自定义类别为 `custom:{名称}` */
  bucketKey: string
  /** 展示名（桶来自后端 bucketDefs；自定义类别用审计师输入的名称） */
  label: string
  openingAmount: number
  endingAmount: number
  /** 受限原因（审计师录入的真实披露内容） */
  reason: string
  /** 归集到本行的原始科目码（溯源展示） */
  codes: string[]
  /** 是否由四表自动分类得来（false = 纯手工行 / 人工归类行） */
  fromFourTable: boolean
}

const CUSTOM_PREFIX = 'custom:'

export function isCustomBucketKey(key: string): boolean {
  return String(key ?? '').startsWith(CUSTOM_PREFIX)
}

export function customBucketKey(label: string): string {
  return `${CUSTOM_PREFIX}${String(label ?? '').trim()}`
}

/** 自定义类别的展示名 = key 去前缀（自定义类别的中文名本就由审计师输入）。 */
export function customBucketLabel(key: string): string {
  return isCustomBucketKey(key) ? key.slice(CUSTOM_PREFIX.length) : key
}

export function e1RestrictedRowId(bucketKey: string, seq: number): string {
  const slug = isCustomBucketKey(bucketKey)
    ? `custom_${customBucketLabel(bucketKey).replace(/\s+/g, '').slice(0, 12)}`
    : bucketKey
  return `restricted_${slug || 'bucket'}_${seq}`
}

/**
 * 桶 key → 展示名。**只从后端 bucketDefs 取**；未下发时退化显示 key。
 *
 * 🔴 不在前端硬编码桶中文名 —— 平台铁律「分类桶一份声明式真源，前端不抄第二份」。
 */
export function resolveBucketLabel(
  bucketKey: string,
  bucketDefs: readonly E1RestrictedBucketDef[],
): string {
  if (isCustomBucketKey(bucketKey)) return customBucketLabel(bucketKey)
  return bucketDefs.find((d) => d.key === bucketKey)?.label || bucketKey
}

export interface ResolveRestrictedOptions {
  prefill: E1RestrictedPrefill
  manualMap: E1RestrictedManualMap
  /** 已持久化的行（保留审计师录入的 reason 与手工金额） */
  existingRows?: readonly E1RestrictedRow[]
}

/** 某叶子的最终归属：人工归类优先于自动分类；`null` = 仍待归类。 */
export function effectiveBucketOf(
  leaf: E1RestrictedLeaf,
  manualMap: E1RestrictedManualMap,
): string | null {
  const manual = manualMap[leaf.code]
  if (manual) return manual === E1_UNRESTRICTED ? null : manual
  return leaf.autoBucket
}

/**
 * 合并「人工归类」与「自动分类」→ ②表行。**纯函数。**
 *
 * 优先级：人工归类 > 自动分类 > 仍待归类（不进表）。
 * 被标 `E1_UNRESTRICTED` 的叶子不进任何类别行（其金额由勾稽面板计入差额侧）。
 *
 * 因后端下发的是**逐叶子**明细，这里可以自由重算 —— 审计师把叶子改归到别的类别时，
 * 原类别与新类别的余额都能精确重算（预聚合表示做不到这点）。
 *
 * 已有行的 `reason` 保留；纯手工行（不由四表叶子构成）原样保留金额。
 */
export function resolveRestrictedRows(opts: ResolveRestrictedOptions): E1RestrictedRow[] {
  const { prefill, manualMap } = opts
  const existing = opts.existingRows ?? []
  const reasonByBucket = new Map<string, string>()
  for (const r of existing) {
    if (r.reason) reasonByBucket.set(r.bucketKey, r.reason)
  }

  const agg = new Map<string, { opening: number; closing: number; codes: string[] }>()
  const bump = (key: string, opening: number, closing: number, code: string) => {
    const cur = agg.get(key) ?? { opening: 0, closing: 0, codes: [] }
    cur.opening += opening
    cur.closing += closing
    if (code) cur.codes.push(code)
    agg.set(key, cur)
  }

  // ① 逐叶子按最终归属聚合（人工归类优先）
  for (const leaf of prefill.leaves) {
    const bucket = effectiveBucketOf(leaf, manualMap)
    if (!bucket) continue
    bump(bucket, leaf.opening, leaf.closing, leaf.code)
  }

  // ② 纯手工行（审计师直接加的类别，不由四表叶子构成）
  for (const r of existing) {
    if (agg.has(r.bucketKey)) continue
    if (r.fromFourTable) continue
    agg.set(r.bucketKey, {
      opening: r.openingAmount,
      closing: r.endingAmount,
      codes: [...r.codes],
    })
  }

  const defs = prefill.bucketDefs
  const order = new Map(defs.map((d, i) => [d.key, i]))
  return [...agg.entries()]
    .sort((a, b) => (order.get(a[0]) ?? 999) - (order.get(b[0]) ?? 999))
    .map(([bucketKey, amt], i) => ({
      id: e1RestrictedRowId(bucketKey, i),
      bucketKey,
      label: resolveBucketLabel(bucketKey, defs),
      openingAmount: amt.opening,
      endingAmount: amt.closing,
      reason: reasonByBucket.get(bucketKey) ?? '',
      codes: amt.codes,
      fromFourTable: amt.codes.length > 0,
    }))
}

/**
 * 仍待归类的叶子（自动分类判不出来、且审计师还没处理的）。
 *
 * 这是「各项目科目命名不同」的兜底通道：四表新增科目自动出现在这里，
 * **既不静默丢弃也不臆造归属**。
 */
export function pendingUnclassified(
  prefill: E1RestrictedPrefill,
  manualMap: E1RestrictedManualMap,
): E1RestrictedLeaf[] {
  return prefill.leaves.filter((u) => u.autoBucket === null && !(u.code in manualMap))
}

/** 被标「不受限」的叶子（金额计入 F1-5/F1-6 勾稽的差额侧，不隐藏）。 */
export function unrestrictedLeaves(
  prefill: E1RestrictedPrefill,
  manualMap: E1RestrictedManualMap,
): E1RestrictedLeaf[] {
  return prefill.leaves.filter((u) => manualMap[u.code] === E1_UNRESTRICTED)
}

/**
 * 货币资金叶子合计（供 F1-5/F1-6 勾稽：②表合计 = 货币资金 − 现金及现金等价物）。
 *
 * 恒等式：受限合计 + 不受限合计 + 待归类合计 == 本函数返回值。
 */
export function allLeavesTotal(prefill: E1RestrictedPrefill): {
  opening: number
  ending: number
} {
  return {
    opening: prefill.leaves.reduce((s, r) => s + (Number(r.opening) || 0), 0),
    ending: prefill.leaves.reduce((s, r) => s + (Number(r.closing) || 0), 0),
  }
}

/** ②表合计（源 xlsx R23「合  计」；校验预设 F1-4 要求合计 = 明细之和）。 */
export function restrictedTotals(rows: readonly E1RestrictedRow[]): {
  opening: number
  ending: number
} {
  return {
    opening: rows.reduce((s, r) => s + (Number(r.openingAmount) || 0), 0),
    ending: rows.reduce((s, r) => s + (Number(r.endingAmount) || 0), 0),
  }
}
