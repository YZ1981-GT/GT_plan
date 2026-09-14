/**
 * 账龄档位标签「配置口径 → 披露口径」映射（方案 A：同步层映射）
 *
 * 背景：底稿账龄行 label 直接取自 `useAgingConfig` 的**项目账龄配置**（`1-2年`），
 * 同步到附注后原样呈现，与附注模板/源模板字面（`1至2年`）不一致。
 * 用户 2026-07-29 决策走**方案 A**：项目配置继续只服务底稿内部（底稿页仍显示
 * `1-2年`，审计师日常操作口径不变），只在**构建同步载荷时**做映射。
 *
 * 全模板用词实证（`note_template_{listed,soe}.json`）：
 * `1至2年` 31 次 / `2至3年` 29 次 / `3年以上` 16 次 / `1年以内（含1年）` 13 次 /
 * `5年以上` 11 次；而 `1-2年`~`4-5年` 各 5 次 —— 后者正是配置口径经同步漏进模板的痕迹。
 *
 * ⚠️ 首档口径按循环/变体不同（上市多为 `1年以内`，国企多为 `1年以内（含1年）`），
 * 故**不进共享表**，由各循环通过 `overrides` 声明（R6.3）；国企口径已收敛为
 * 本模块导出的 `SOE_AGING_OVERRIDES`（D2 soe / F1 soe / F4 / D3 soe 共用）。
 *
 * spec: .kiro/specs/disclosure-columns-coverage-rollout/ R6（Task 13.1）
 */

/** 段 key → 披露口径标签（8 个预设段；首档差异走 overrides） */
export const DISCLOSURE_AGING_LABELS: Readonly<Record<string, string>> = Object.freeze({
  within1: '1年以内',
  y1to2: '1至2年',
  y2to3: '2至3年',
  y3to4: '3至4年',
  y4to5: '4至5年',
  // 「1年以内 / 1年以上」两桶口径（D3 八、38 预收款项按账龄表实测行名）
  over1: '1年以上',
  over3: '3年以上',
  over5: '5年以上',
})

/** 披露口径值域（守卫用：不得含连字符 —— 含则说明仍是配置口径） */
export const DISCLOSURE_AGING_LABEL_VALUES: readonly string[] = Object.freeze(
  Object.values(DISCLOSURE_AGING_LABELS),
)

/** 预设段 key 集合（不在此集合内 = 自定义段，原样透传，禁止杜撰） */
export const PRESET_AGING_KEYS: ReadonlySet<string> = new Set(Object.keys(DISCLOSURE_AGING_LABELS))

export function isPresetAgingKey(key: string): boolean {
  return PRESET_AGING_KEYS.has(String(key))
}

/**
 * 结构行标签（非账龄段行）：底稿字面 → 附注模板字面。
 *
 * 实证：D2 上市 §五、5 与国企 §八、5 的账龄表结构行带空格（`小 计` / `合 计`），
 * 底稿侧是无空格 `小计` / `合计`；`减：坏账准备` 两侧一致故不入表（未命中即原样透传）。
 */
export const DISCLOSURE_STRUCT_ROW_LABELS: Readonly<Record<string, string>> = Object.freeze({
  小计: '小 计',
  合计: '合 计',
  '1年以内小计': '1年以内小计：',
})

/** 「合计」行的披露口径字面（载荷里直接构造合计行时用，避免各处写字面量） */
export const DISCLOSURE_TOTAL_LABEL = DISCLOSURE_STRUCT_ROW_LABELS['合计']

/** 「小计」行的披露口径字面 */
export const DISCLOSURE_SUBTOTAL_LABEL = DISCLOSURE_STRUCT_ROW_LABELS['小计']

/** 段最小形状（兼容 `AgingSegment` / 审定表 `AgingRowDef` / 披露行） */
export interface AgingSegmentLike {
  key?: string
  rowKey?: string
  label?: string
}

/** per-section 覆盖：`{ [segKey]: 披露标签 }`（如国企 `within1: '1年以内（含1年）'`） */
export type AgingLabelOverrides = Readonly<Record<string, string>>

/**
 * 国企版首档账龄字面。
 *
 * 实证：`note_template_soe.json` 全模板 `1年以内（含1年）` 13 次（D2 八、5 / F1 八、7 /
 * F4 八、37 / D3 八、38 …），上市版对应位置为 `1年以内`（24 次）。
 */
export const DISCLOSURE_AGING_WITHIN1_SOE = '1年以内（含1年）'

/**
 * 国企版 per-section 覆盖（唯一真源）。
 *
 * 收敛前 D2/F1/F4 各自写了一遍 `{ within1: '1年以内（含1年）' }` 字面量（R6.3 遗留），
 * 现统一引用本常量，字面量只在 `DISCLOSURE_AGING_WITHIN1_SOE` 维护一份。
 */
export const SOE_AGING_OVERRIDES: AgingLabelOverrides = Object.freeze({
  within1: DISCLOSURE_AGING_WITHIN1_SOE,
})

function segKey(seg: AgingSegmentLike): string {
  return String(seg.key ?? seg.rowKey ?? '')
}

function pick(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v : undefined
}

/**
 * 按段 key 查披露口径标签。
 *
 * 优先级：`overrides[key]` > `DISCLOSURE_AGING_LABELS[key]`。
 * **未命中返回 `undefined`**（而非空串），便于调用方 `|| 回退口径` 链式兜底。
 */
export function lookupDisclosureAgingLabel(
  key: string,
  overrides?: AgingLabelOverrides | null,
): string | undefined {
  const k = String(key ?? '')
  if (!k) return undefined
  return pick(overrides?.[k]) ?? pick(DISCLOSURE_AGING_LABELS[k])
}

/**
 * 结构行标签映射：命中 `DISCLOSURE_STRUCT_ROW_LABELS` 则返回附注字面，否则原样。
 *
 * 保守设计：未登记的结构行（如 `减：坏账准备`）原样透传，不擅自加空格。
 */
export function toDisclosureStructLabel(label: string): string {
  const raw = String(label ?? '')
  return pick(DISCLOSURE_STRUCT_ROW_LABELS[raw]) ?? raw
}

/**
 * 披露行（账龄段行 / 结构行）→ 披露口径标签。
 *
 * 判定顺序：
 * 1. 预设段 key → `overrides` > 共享表；
 * 2. **结构行按 `label` 兜底**查 `DISCLOSURE_STRUCT_ROW_LABELS`
 *    —— 覆盖两种来源：显式结构 key（`__subtotal` / `__total` / `__within1_subtotal`）
 *    与**无 key 的合计行**（D2 组合分表的合计行只有 `label: '合计'`，无段 key）；
 * 3. 自定义段 / 未登记结构行 → 原样透传 `label`（禁止杜撰；如 `减：坏账准备` 两侧本就一致）。
 *
 * 纯函数，不修改入参（Property 8：底稿显示口径不受影响）。
 */
export function toDisclosureAgingLabel(
  seg: AgingSegmentLike,
  overrides?: AgingLabelOverrides | null,
): string {
  const key = segKey(seg)
  const label = String(seg.label ?? '')
  const byKey = lookupDisclosureAgingLabel(key, overrides)
  if (byKey) return byKey
  const byLabel = pick(DISCLOSURE_STRUCT_ROW_LABELS[label])
  if (byLabel) return byLabel
  return label || key
}

/** 批量映射（保持入参顺序；不改原数组/原对象） */
export function toDisclosureAgingLabels(
  segments: readonly AgingSegmentLike[],
  overrides?: AgingLabelOverrides | null,
): string[] {
  return segments.map((s) => toDisclosureAgingLabel(s, overrides))
}

/**
 * 以共享表为基底叠加 per-section 覆盖，产出该循环的账龄标签表。
 *
 * 供**已有** `X_NOTE_AGING_LABEL` 导出常量的循环收敛：保留原常量名与形状
 * （下游调用与既有断言无需改动），但字面量只在 `DISCLOSURE_AGING_LABELS` 维护一份。
 *
 * K1 首档用通用 `1年以内` → 不传 overrides；
 * F4 按账龄表仅国企（八、37）有 → 传 `{ within1: '1年以内（含1年）' }`。
 */
export function buildDisclosureAgingLabelMap(
  overrides?: AgingLabelOverrides | null,
): Record<string, string> {
  return { ...DISCLOSURE_AGING_LABELS, ...(overrides ?? {}) }
}

/** 归一化比较：忽略空白差异（判断两个标签是否「同一结构行、仅空格不同」） */
export function isSameStructLabel(a: string, b: string): boolean {
  const norm = (s: string) => String(s ?? '').replace(/\s+/g, '')
  return norm(a) === norm(b) && norm(a) !== ''
}
