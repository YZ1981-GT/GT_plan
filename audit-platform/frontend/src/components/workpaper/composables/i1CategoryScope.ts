/**
 * I1 无形资产类别配置（前端单一真源）。
 *
 * 上市披露表：类别作**列**（列转置，列头 = 类别 label）
 * 国企披露表：类别作**行**（四层 × 类别序列）
 * 两侧共用同一份 categories，改一处两侧同步（R7.2）。
 *
 * 运行态优先取 render 下发的 `category_defs`（项目可自定义类别），常量只作兜底。
 */

export interface I1CategorySlot {
  key: string      // 稳定键（英文），用作列 key / 行 key（不用中文 label 作键 → 改名不丢数据）
  label: string    // 中文标签（可改名）
  seq: number      // 排序序号
  removable: boolean  // 是否可删除（other 不可删）
}

/** 默认 11 类（来自 category_defs_payload，与源模板 `底稿目录!A9:A19` 一致） */
export const I1_DEFAULT_CATEGORIES: I1CategorySlot[] = [
  { key: 'land_use_right', label: '土地使用权', seq: 1, removable: true },
  { key: 'housing_use_right', label: '住房使用权', seq: 2, removable: true },
  { key: 'patent', label: '专利权', seq: 3, removable: true },
  { key: 'patent_free_tech', label: '非专利技术', seq: 4, removable: true },
  { key: 'trademark', label: '商标权', seq: 5, removable: true },
  { key: 'copyright', label: '著作权', seq: 6, removable: true },
  { key: 'franchise', label: '特许经营权', seq: 7, removable: true },
  { key: 'software', label: '软件', seq: 8, removable: true },
  { key: 'mining_right', label: '矿产权', seq: 9, removable: true },
  { key: 'data_resource', label: '数据资源', seq: 10, removable: true },
  { key: 'other', label: '其他', seq: 11, removable: false },
]

/** 上市披露表列 key 生成（稳定 key = `{slot.key}_{slot.seq}`，禁用 label 作 key → 会撞键） */
export function i1CategoryColumnKey(slot: I1CategorySlot): string {
  return `${slot.key}_${slot.seq}`
}

/**
 * 从 render 下发的 `category_defs` 构建类别序列（项目可自定义）。
 * 兜底回退 I1_DEFAULT_CATEGORIES。
 */
export function resolveI1Categories(
  categoryDefs?: Array<{ key: string; label: string; seq: number }> | null,
): I1CategorySlot[] {
  if (!categoryDefs?.length) return [...I1_DEFAULT_CATEGORIES]
  return categoryDefs.map((d) => ({
    key: d.key,
    label: d.label,
    seq: d.seq,
    removable: d.key !== 'other',
  }))
}

/** 新增类别（撞名拒绝 → 返回 null） */
export function addI1Category(
  list: I1CategorySlot[],
  label: string,
): I1CategorySlot[] | null {
  const trimmed = label.trim()
  if (!trimmed) return null
  if (list.some((c) => c.label === trimmed)) return null // 撞名拒绝
  const maxSeq = Math.max(0, ...list.map((c) => c.seq))
  const key = `custom_${Date.now()}`
  return [...list, { key, label: trimmed, seq: maxSeq + 1, removable: true }]
}

/** 改名类别（撞名拒绝 → 返回 null） */
export function renameI1Category(
  list: I1CategorySlot[],
  key: string,
  newLabel: string,
): I1CategorySlot[] | null {
  const trimmed = newLabel.trim()
  if (!trimmed) return null
  if (list.some((c) => c.key !== key && c.label === trimmed)) return null
  return list.map((c) => (c.key === key ? { ...c, label: trimmed } : c))
}

/** 删除类别（other 不可删） */
export function removeI1Category(
  list: I1CategorySlot[],
  key: string,
): I1CategorySlot[] | null {
  const target = list.find((c) => c.key === key)
  if (!target || !target.removable) return null
  return list.filter((c) => c.key !== key)
}

/** 默认类别键序列（按 seq 排序） */
export function defaultI1CategoryKeys(): string[] {
  return I1_DEFAULT_CATEGORIES.map((c) => c.key)
}

/**
 * 历史 key 映射：listed/soe 模型用的短 key → categoryScope 标准 key。
 * 已持久化的 checklist_responses 里用的是短 key，消费时需通过此表翻译。
 */
export const I1_LEGACY_KEY_MAP: Record<string, string> = {
  land: 'land_use_right',
  housing: 'housing_use_right',
  knowhow: 'patent_free_tech',
  mining: 'mining_right',
  franchise: 'franchise',
  patent: 'patent',
  trademark: 'trademark',
  copyright: 'copyright',
  software: 'software',
  data: 'data_resource',
  other: 'other',
  // SOE 额外
  exploration: 'mining_right',  // 探矿权并入矿产权
}

/** 标准 key → 历史短 key（反向映射，用于写入兼容） */
export const I1_STANDARD_TO_LEGACY: Record<string, string> = {
  land_use_right: 'land',
  housing_use_right: 'housing',
  patent_free_tech: 'knowhow',
  mining_right: 'mining',
  franchise: 'franchise',
  patent: 'patent',
  trademark: 'trademark',
  copyright: 'copyright',
  software: 'software',
  data_resource: 'data',
  other: 'other',
}

/** 归一化任意 key 到标准 key（不认识的原样返回） */
export function normalizeI1CategoryKey(key: string): string {
  return I1_LEGACY_KEY_MAP[key] ?? key
}
