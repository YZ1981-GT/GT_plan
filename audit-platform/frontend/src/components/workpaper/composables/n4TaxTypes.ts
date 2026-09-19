/**
 * n4TaxTypes — N4 税金及附加统一税种词典（单一真源）
 *
 * 解决历史遗留：N4-1 审定表(rowKey=`row-中文`)、N4-2 明细表(城市维护建设税)、
 * useN4CrossSheet(城建税/土地使用税)、附注(英文 rowKey) 四处税种命名/rowKey 不一致
 * 导致跨表按 rowKey/名称 join 全部落空。此处统一为「英文稳定 key + 中文 label」。
 *
 * 所有 N4 子组件/composable 必须从此导入，禁止各自硬编码税种数组。
 */

export interface N4TaxType {
  /** 稳定英文 key（跨表 join 主键，永不随中文改名而变） */
  key: string
  /** 中文显示名 */
  label: string
}

/** N4 涵盖的税种（顺序对齐源模板 N4-1/N4-2） */
export const N4_TAX_TYPES: readonly N4TaxType[] = [
  { key: 'consumption-tax', label: '消费税' },
  { key: 'urban-construction', label: '城市维护建设税' },
  { key: 'education-surcharge', label: '教育费附加' },
  { key: 'local-education', label: '地方教育附加' },
  { key: 'property-tax', label: '房产税' },
  { key: 'land-use-tax', label: '城镇土地使用税' },
  { key: 'vehicle-vessel', label: '车船税' },
  { key: 'stamp-tax', label: '印花税' },
  { key: 'resource-tax', label: '资源税' },
  { key: 'other', label: '其他' },
] as const

/** 全部中文标签（顺序数组） */
export const N4_TAX_LABELS: readonly string[] = N4_TAX_TYPES.map((t) => t.label)

/** 全部英文 key（顺序数组） */
export const N4_TAX_KEYS: readonly string[] = N4_TAX_TYPES.map((t) => t.key)

/** 历史别名 → 规范 label 映射（兼容旧持久化数据的中文名差异） */
const _LABEL_ALIASES: Record<string, string> = {
  城建税: '城市维护建设税',
  城市维护建设税及教育费附加: '城市维护建设税',
  土地使用税: '城镇土地使用税',
  车船使用税: '车船税',
}

/** 中文 label → 稳定 key（兼容历史别名 + `row-中文` 形态） */
export function n4TaxLabelToKey(label: string | undefined | null): string {
  if (!label) return ''
  let name = String(label).trim()
  // 兼容旧 rowKey 形态 `row-消费税`
  if (name.startsWith('row-')) name = name.slice(4)
  const canonical = _LABEL_ALIASES[name] ?? name
  const hit = N4_TAX_TYPES.find((t) => t.label === canonical)
  return hit ? hit.key : ''
}

/** 稳定 key → 中文 label */
export function n4TaxKeyToLabel(key: string | undefined | null): string {
  if (!key) return ''
  const hit = N4_TAX_TYPES.find((t) => t.key === key)
  return hit ? hit.label : ''
}

/**
 * 把任意历史 rowKey/taxType 归一到稳定 key。
 * 优先按 key 命中；否则按 label（含别名/`row-` 前缀）命中。
 */
export function n4NormalizeKey(rawKeyOrLabel: string | undefined | null): string {
  if (!rawKeyOrLabel) return ''
  const raw = String(rawKeyOrLabel).trim()
  if (N4_TAX_KEYS.includes(raw)) return raw
  return n4TaxLabelToKey(raw)
}
