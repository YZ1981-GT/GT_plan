/**
 * 消费后端下发的列分层（业务列 / 技术列 / PII 列）。
 *
 * **真源在后端** `backend/app/services/custom_query/table_whitelist.py` 的
 * `derive_field_tiers`，经 `GET /api/query/schema` 下发。本模块只做分组与判定，
 * **不硬编码任何列名** —— 列名在前端复制第二份必然与后端漂移（R7.5）。
 *
 * 存在理由：改造前 schema 把 `fields` 原样下发，前端字段下拉里
 * `is_deleted` / `created_at` 与业务字段混排；而 `dsl.fields = []` 是默认值，
 * 用户不选字段时结果表第一列就是 UUID 主键。
 *
 * _Requirements: 7.2, 7.3, 7.5, 11.3_
 */

/** 后端 schema 中单张表的字段分层（缺失时按「全部视作业务列」降级） */
export interface FieldTierMeta {
  fields?: string[]
  default_fields?: string[]
  technical_fields?: string[]
  pii_fields?: string[]
}

export interface FieldGroup {
  label: string
  fields: string[]
}

/** 技术列分组的显示名（供 el-option-group 使用） */
export const BUSINESS_GROUP_LABEL = '业务字段'
export const TECHNICAL_GROUP_LABEL = '技术字段（排查用）'
export const PII_GROUP_LABEL = '个人信息字段'

/**
 * 把一张表的字段按层分组，业务列在前。
 *
 * 后端未下发分层时（旧版本 / 缓存的旧 schema）退化为单个业务组，保证不因缺字段
 * 而渲染空下拉。
 */
export function groupFieldsByTier(meta: FieldTierMeta | null | undefined): FieldGroup[] {
  if (!meta) return []
  const all = meta.fields ?? []
  const technical = new Set(meta.technical_fields ?? [])
  const pii = new Set(meta.pii_fields ?? [])

  if (!technical.size && !pii.size) {
    return all.length ? [{ label: BUSINESS_GROUP_LABEL, fields: [...all] }] : []
  }

  const groups: FieldGroup[] = []
  const business = all.filter((f) => !technical.has(f) && !pii.has(f))
  if (business.length) groups.push({ label: BUSINESS_GROUP_LABEL, fields: business })
  const piiPresent = all.filter((f) => pii.has(f))
  if (piiPresent.length) groups.push({ label: PII_GROUP_LABEL, fields: piiPresent })
  const techPresent = all.filter((f) => technical.has(f))
  if (techPresent.length) groups.push({ label: TECHNICAL_GROUP_LABEL, fields: techPresent })
  return groups
}

/** 该表的业务默认列集（用户未显式选字段时后端会返回这些列） */
export function defaultFieldsOf(meta: FieldTierMeta | null | undefined): string[] {
  if (!meta) return []
  const declared = meta.default_fields
  if (declared && declared.length) return [...declared]
  // 后端未下发时按技术列/PII 列推导，仍不硬编码列名
  const technical = new Set(meta.technical_fields ?? [])
  const pii = new Set(meta.pii_fields ?? [])
  return (meta.fields ?? []).filter((f) => !technical.has(f) && !pii.has(f))
}

/** 判断某个结果列是否属于技术列（用于结果表默认隐藏） */
export function isTechnicalColumn(
  key: string,
  meta: FieldTierMeta | null | undefined
): boolean {
  if (!meta) return false
  // 支持 `table.field` 双段列名：只比较列名段
  const bare = String(key).split('.').pop() ?? key
  return new Set(meta.technical_fields ?? []).has(bare)
}

/**
 * 过滤结果列：默认剔除技术列，`showTechnical` 为真时全部保留。
 *
 * 只在**展示层**过滤 —— 数据仍然完整返回，用户打开开关即可看到，不必重查。
 */
export function filterVisibleColumns<T extends { key: string }>(
  columns: T[],
  meta: FieldTierMeta | null | undefined,
  showTechnical: boolean
): T[] {
  if (showTechnical) return [...columns]
  const filtered = columns.filter((c) => !isTechnicalColumn(c.key, meta))
  // 全是技术列时不要把表渲染成空 —— 那会让用户以为查询失败
  return filtered.length ? filtered : [...columns]
}
