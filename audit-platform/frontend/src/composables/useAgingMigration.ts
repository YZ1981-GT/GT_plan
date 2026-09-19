/**
 * useAgingMigration — 往来款账龄旧数据迁移工具
 *
 * 提供 D2 flat→nested 格式迁移、D3/F1 key 对齐、配置变更时数据保留逻辑。
 *
 * 核心能力：
 * - D2 旧 flat 字段 (priorAging1Year 等) → nested keyed (agingPrior.within1 等)
 * - D3/F1 旧固定 key (within1/y1to2/y2to3/over3) → 动态 segments 对齐
 * - 配置变更时已有段保留 / 新增段零初始化 / 旧段丢弃
 * - 序列化时确保仅输出 nested 格式，剔除所有 flat 字段
 *
 * Requirements: 4.3, 5.3, 5.4, 10.2, 10.3, 10.4
 */
import type { AgingSegment } from './useAgingConfig'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

/** nested keyed 账龄数据 */
export interface AgingData {
  [segmentKey: string]: number
}

/** D2 新格式行（3 period） */
export interface D2DetailRowV2 {
  agingPrior: AgingData
  agingCurrent: AgingData
  agingAudited: AgingData
  [key: string]: any
}

/** D3/F1 新格式行（D3 为 2 period；F1-2 Excel 含期末未审 agingCurrent 为 3 period） */
export interface D3F1DetailRowV2 {
  agingPrior: AgingData
  agingCurrent?: AgingData
  agingAudited: AgingData
  [key: string]: any
}

// ─── D2 FLAT→NESTED 映射常量（18 个字段） ────────────────────────────────────

/**
 * D2 旧 flat 字段名 → { period, segmentKey } 的完整映射
 *
 * 3 个 period (prior/current/audited) × 6 个 segment (FIVE_YEAR) = 18 个字段
 */
export const D2_FLAT_TO_SEGMENT: Record<string, { period: 'prior' | 'current' | 'audited'; segmentKey: string }> = {
  // ── prior (期初) ──
  priorAging1Year: { period: 'prior', segmentKey: 'within1' },
  priorAging1to2: { period: 'prior', segmentKey: 'y1to2' },
  priorAging2to3: { period: 'prior', segmentKey: 'y2to3' },
  priorAging3to4: { period: 'prior', segmentKey: 'y3to4' },
  priorAging4to5: { period: 'prior', segmentKey: 'y4to5' },
  priorAgingOver5: { period: 'prior', segmentKey: 'over5' },
  // ── current (期末未审) ──
  currentAging1Year: { period: 'current', segmentKey: 'within1' },
  currentAging1to2: { period: 'current', segmentKey: 'y1to2' },
  currentAging2to3: { period: 'current', segmentKey: 'y2to3' },
  currentAging3to4: { period: 'current', segmentKey: 'y3to4' },
  currentAging4to5: { period: 'current', segmentKey: 'y4to5' },
  currentAgingOver5: { period: 'current', segmentKey: 'over5' },
  // ── audited (期末审定) ──
  auditedAging1Year: { period: 'audited', segmentKey: 'within1' },
  auditedAging1to2: { period: 'audited', segmentKey: 'y1to2' },
  auditedAging2to3: { period: 'audited', segmentKey: 'y2to3' },
  auditedAging3to4: { period: 'audited', segmentKey: 'y3to4' },
  auditedAging4to5: { period: 'audited', segmentKey: 'y4to5' },
  auditedAgingOver5: { period: 'audited', segmentKey: 'over5' },
}

/** 所有 D2 旧 flat 字段名集合（用于检测和清理） */
export const D2_FLAT_KEYS = new Set(Object.keys(D2_FLAT_TO_SEGMENT))

// ─── 检测函数 ─────────────────────────────────────────────────────────────────

/**
 * 检测一行数据是否为 D2 旧 flat 格式
 *
 * 判定标准：存在任意一个 flat 字段名 (priorAging1Year 等)
 */
export function isLegacyD2Format(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false
  for (const key of D2_FLAT_KEYS) {
    if (key in raw) return true
  }
  return false
}

// ─── D2 迁移函数 ──────────────────────────────────────────────────────────────

/**
 * 将 D2 旧 flat 格式行转换为 nested keyed 格式
 *
 * - 将 18 个 flat 字段分组到 agingPrior/agingCurrent/agingAudited
 * - 保留所有非 aging flat 字段 (rowId/seq/customerName 等)
 * - flat 字段转换后从结果中移除，确保序列化干净
 * - 值为 undefined/null 时默认为 0
 *
 * Requirements: 4.3, 10.2, 10.3
 */
export function migrateD2FlatToNested(raw: any): D2DetailRowV2 {
  const result: any = {}

  // 复制所有非 flat aging 字段
  for (const key of Object.keys(raw)) {
    if (!D2_FLAT_KEYS.has(key)) {
      result[key] = raw[key]
    }
  }

  // 如果已有 nested 结构，保留（兼容混合格式或已迁移的数据）
  const agingPrior: AgingData = (raw.agingPrior && typeof raw.agingPrior === 'object')
    ? { ...raw.agingPrior }
    : {}
  const agingCurrent: AgingData = (raw.agingCurrent && typeof raw.agingCurrent === 'object')
    ? { ...raw.agingCurrent }
    : {}
  const agingAudited: AgingData = (raw.agingAudited && typeof raw.agingAudited === 'object')
    ? { ...raw.agingAudited }
    : {}

  // 从 flat 字段填充 nested 结构
  for (const [flatKey, mapping] of Object.entries(D2_FLAT_TO_SEGMENT)) {
    const value = _toNumber(raw[flatKey])
    const { period, segmentKey } = mapping
    if (period === 'prior') {
      // flat 值覆盖（flat 字段存在时优先，因为 flat 是旧数据的权威来源）
      agingPrior[segmentKey] = value
    } else if (period === 'current') {
      agingCurrent[segmentKey] = value
    } else {
      agingAudited[segmentKey] = value
    }
  }

  result.agingPrior = agingPrior
  result.agingCurrent = agingCurrent
  result.agingAudited = agingAudited

  return result as D2DetailRowV2
}

// ─── D3/F1 迁移函数 ───────────────────────────────────────────────────────────

/**
 * 将 D3/F1 旧固定 key 格式行对齐到当前项目配置 segments
 *
 * D3/F1 旧格式已经是 nested 结构 { within1, y1to2, y2to3, over3 }，
 * 但 key 是固定 THREE_YEAR 的 4 个 key。当项目配置变更后需要：
 * - 匹配的 key 保留原值
 * - 新增的 key 初始化为 0
 * - 不在新配置中的旧 key 丢弃
 *
 * Requirements: 5.3, 5.4
 */
export function migrateD3F1Keys(raw: any, segments: AgingSegment[]): D3F1DetailRowV2 {
  const result: any = {}

  // 复制所有非 aging 字段
  for (const key of Object.keys(raw)) {
    if (key !== 'agingPrior' && key !== 'agingCurrent' && key !== 'agingAudited') {
      result[key] = raw[key]
    }
  }

  const oldPrior: AgingData = (raw.agingPrior && typeof raw.agingPrior === 'object')
    ? raw.agingPrior
    : {}
  const oldCurrent: AgingData = (raw.agingCurrent && typeof raw.agingCurrent === 'object')
    ? raw.agingCurrent
    : {}
  const oldAudited: AgingData = (raw.agingAudited && typeof raw.agingAudited === 'object')
    ? raw.agingAudited
    : {}

  // 按新 segments 构建 nested 对象：匹配 key 保留，不匹配初始化 0
  const newPrior: AgingData = {}
  const newCurrent: AgingData = {}
  const newAudited: AgingData = {}

  for (const seg of segments) {
    newPrior[seg.key] = _toNumber(oldPrior[seg.key])
    newCurrent[seg.key] = _toNumber(oldCurrent[seg.key])
    newAudited[seg.key] = _toNumber(oldAudited[seg.key])
  }

  result.agingPrior = newPrior
  result.agingCurrent = newCurrent
  result.agingAudited = newAudited

  return result as D3F1DetailRowV2
}

// ─── D7 扁平→nested 迁移函数（2-period，8 字段） ──────────────────────────────

/**
 * D7 旧固定 4 段扁平字段 → { period, segmentKey } 映射（2-period，8 字段）。
 *
 * D7 合同负债明细历史数据以 priorAging1~4 / endAging1~4 扁平字段存储，
 * 映射到 THREE_YEAR 默认段 key（within1/y1to2/y2to3/over3）。
 */
export const D7_FLAT_TO_SEGMENT: Record<string, { period: 'prior' | 'audited'; segmentKey: string }> = {
  // ── prior (期初审定账龄) ──
  priorAging1: { period: 'prior', segmentKey: 'within1' },
  priorAging2: { period: 'prior', segmentKey: 'y1to2' },
  priorAging3: { period: 'prior', segmentKey: 'y2to3' },
  priorAging4: { period: 'prior', segmentKey: 'over3' },
  // ── audited (期末审定账龄) ──
  endAging1: { period: 'audited', segmentKey: 'within1' },
  endAging2: { period: 'audited', segmentKey: 'y1to2' },
  endAging3: { period: 'audited', segmentKey: 'y2to3' },
  endAging4: { period: 'audited', segmentKey: 'over3' },
}

/** 所有 D7 旧扁平字段名集合（用于检测与清理） */
export const D7_FLAT_KEYS = new Set(Object.keys(D7_FLAT_TO_SEGMENT))

/**
 * 检测一行是否为 D7 旧扁平格式（存在任意 priorAging1~4 / endAging1~4 字段）。
 */
export function isLegacyD7Format(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false
  for (const key of D7_FLAT_KEYS) {
    if (key in raw) return true
  }
  return false
}

/**
 * 将 D7 旧扁平格式行迁移为 nested keyed 结构（agingPrior / agingAudited）。
 *
 * 规则（Requirements 8.1-8.4）：
 * - 行已含 nested agingPrior/agingAudited（非空对象）→ 以 nested 为准，忽略扁平字段（8.4）
 * - 仅含扁平字段 → 映射到 THREE_YEAR 默认段 key（priorAging1→agingPrior.within1 等，8.1/8.2）
 * - 输出不再含扁平字段 key（8.3）
 *
 * 迁移后应再经 migrateD3F1Keys(_, segments) 对齐当前项目账龄配置段。
 */
export function migrateD7FlatToNested(raw: any): D3F1DetailRowV2 {
  const result: any = {}

  // 复制所有非扁平 aging 字段
  for (const key of Object.keys(raw)) {
    if (!D7_FLAT_KEYS.has(key)) {
      result[key] = raw[key]
    }
  }

  const nestedPrior = (raw.agingPrior && typeof raw.agingPrior === 'object') ? raw.agingPrior : null
  const nestedAudited = (raw.agingAudited && typeof raw.agingAudited === 'object') ? raw.agingAudited : null
  const hasNested = (nestedPrior && Object.keys(nestedPrior).length > 0)
    || (nestedAudited && Object.keys(nestedAudited).length > 0)

  const agingPrior: AgingData = {}
  const agingAudited: AgingData = {}

  if (hasNested) {
    // 以 nested 为准，忽略扁平字段（Req 8.4）
    if (nestedPrior) {
      for (const [k, v] of Object.entries(nestedPrior)) agingPrior[k] = _toNumber(v)
    }
    if (nestedAudited) {
      for (const [k, v] of Object.entries(nestedAudited)) agingAudited[k] = _toNumber(v)
    }
  } else {
    // 从扁平字段迁移（Req 8.1/8.2）
    for (const [flatKey, mapping] of Object.entries(D7_FLAT_TO_SEGMENT)) {
      const value = _toNumber(raw[flatKey])
      if (mapping.period === 'prior') {
        agingPrior[mapping.segmentKey] = value
      } else {
        agingAudited[mapping.segmentKey] = value
      }
    }
  }

  result.agingPrior = agingPrior
  result.agingAudited = agingAudited

  return result as D3F1DetailRowV2
}

// ─── F4 扁平→nested 迁移函数（2-period：期末未审 + 期末审定，8 字段） ─────────

/**
 * F4 旧固定 4 档扁平字段 → { period, segmentKey } 映射。
 *
 * F4 应付账款明细（F4-2）历史数据以 `unadjustedAging*`（期末未审账龄，N:Q 列）与
 * `auditedAging*`（期末审定账龄，U:X 列）扁平字段存储，**没有期初账龄**，
 * 故 period 只有 current（期末未审）/ audited（期末审定），映射到 THREE_YEAR 段 key。
 */
export const F4_FLAT_TO_SEGMENT: Record<string, { period: 'current' | 'audited'; segmentKey: string }> = {
  // ── current (期末未审账龄 N:Q) ──
  unadjustedAgingLt1: { period: 'current', segmentKey: 'within1' },
  unadjustedAging1to2: { period: 'current', segmentKey: 'y1to2' },
  unadjustedAging2to3: { period: 'current', segmentKey: 'y2to3' },
  unadjustedAgingGt3: { period: 'current', segmentKey: 'over3' },
  // ── audited (期末审定账龄 U:X) ──
  auditedAgingLt1: { period: 'audited', segmentKey: 'within1' },
  auditedAging1to2: { period: 'audited', segmentKey: 'y1to2' },
  auditedAging2to3: { period: 'audited', segmentKey: 'y2to3' },
  auditedAgingGt3: { period: 'audited', segmentKey: 'over3' },
}

/** 所有 F4 旧扁平字段名集合（含更早别名，用于检测与清理） */
export const F4_FLAT_KEYS = new Set(Object.keys(F4_FLAT_TO_SEGMENT))

/**
 * F4 更早期别名（迁移前 `migrateF4DetailRows` 已兼容的历史字段名）。
 * 仅在对应规范字段缺失时作为回退，不参与输出清理集合以外的行为。
 */
const F4_LEGACY_ALIASES: Record<string, string[]> = {
  unadjustedAgingLt1: ['aging1Year', 'agingLt1'],
  unadjustedAging1to2: ['aging1to2Year', 'aging1to2'],
  unadjustedAging2to3: ['aging2to3Year', 'aging2to3'],
  unadjustedAgingGt3: ['aging3YearPlus', 'agingGt3'],
  auditedAgingLt1: ['adjustedAging1'],
  auditedAging1to2: ['adjustedAging2'],
  auditedAging2to3: ['adjustedAging3'],
  auditedAgingGt3: ['adjustedAging4'],
}

/** 检测一行是否为 F4 旧扁平格式（存在任意规范扁平字段或其历史别名）。 */
export function isLegacyF4Format(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false
  for (const key of F4_FLAT_KEYS) {
    if (key in raw) return true
  }
  for (const aliases of Object.values(F4_LEGACY_ALIASES)) {
    for (const alias of aliases) {
      if (alias in raw) return true
    }
  }
  return false
}

/**
 * 将 F4 旧扁平格式行迁移为 nested keyed 结构（agingCurrent / agingAudited）。
 *
 * 规则（对齐 D7 同款薄封装）：
 * - 行已含非空 nested agingCurrent/agingAudited → **以 nested 为准，忽略扁平字段**
 * - 仅含扁平字段（含历史别名）→ 映射到 THREE_YEAR 段 key
 * - 输出不再含 F4 扁平字段 key 与历史别名 key（序列化干净）
 *
 * 迁移后应再经 `remapRowAgingData(_, segments, false)` 对齐当前项目账龄配置段。
 */
export function migrateF4FlatToNested(raw: any): D3F1DetailRowV2 {
  const result: any = {}
  const aliasKeys = new Set<string>()
  for (const aliases of Object.values(F4_LEGACY_ALIASES)) {
    for (const alias of aliases) aliasKeys.add(alias)
  }

  for (const key of Object.keys(raw ?? {})) {
    if (!F4_FLAT_KEYS.has(key) && !aliasKeys.has(key)) {
      result[key] = raw[key]
    }
  }

  const nestedCurrent = (raw?.agingCurrent && typeof raw.agingCurrent === 'object') ? raw.agingCurrent : null
  const nestedAudited = (raw?.agingAudited && typeof raw.agingAudited === 'object') ? raw.agingAudited : null
  const hasNested = (nestedCurrent && Object.keys(nestedCurrent).length > 0)
    || (nestedAudited && Object.keys(nestedAudited).length > 0)

  const agingCurrent: AgingData = {}
  const agingAudited: AgingData = {}

  if (hasNested) {
    if (nestedCurrent) {
      for (const [k, v] of Object.entries(nestedCurrent)) agingCurrent[k] = _toNumber(v)
    }
    if (nestedAudited) {
      for (const [k, v] of Object.entries(nestedAudited)) agingAudited[k] = _toNumber(v)
    }
  } else {
    for (const [flatKey, mapping] of Object.entries(F4_FLAT_TO_SEGMENT)) {
      let value = raw?.[flatKey]
      if (value == null) {
        for (const alias of F4_LEGACY_ALIASES[flatKey] ?? []) {
          if (raw?.[alias] != null) {
            value = raw[alias]
            break
          }
        }
      }
      const num = _toNumber(value)
      if (mapping.period === 'current') agingCurrent[mapping.segmentKey] = num
      else agingAudited[mapping.segmentKey] = num
    }
  }

  result.agingCurrent = agingCurrent
  result.agingAudited = agingAudited

  return result as D3F1DetailRowV2
}

// ─── 配置变更数据保留逻辑 ─────────────────────────────────────────────────────

/**
 * 配置变更时重新映射 aging 数据
 *
 * 规则：
 * - 新旧配置中都存在的 segment key → 保留原值
 * - 新配置有但旧配置没有的 segment key → 初始化为 0
 * - 旧配置有但新配置没有的 segment key → 丢弃（数据丢失，用户已被警告）
 *
 * @param agingData 当前 aging 数据对象 (如 agingPrior)
 * @param newSegments 新配置的 segments 列表
 * @returns 重新映射后的 aging 数据
 *
 * Requirements: 4.5 (Requirement 4 AC5)
 */
export function remapAgingData(agingData: AgingData, newSegments: AgingSegment[]): AgingData {
  const result: AgingData = {}
  for (const seg of newSegments) {
    // 保留已有段的值，新增段初始化 0
    result[seg.key] = (seg.key in agingData) ? _toNumber(agingData[seg.key]) : 0
  }
  return result
}

/**
 * 配置变更时重新映射整行的所有 aging period 数据
 *
 * 支持 3-period (D2/K1/K3/G5) 和 2-period (D3/F1) 行
 */
export function remapRowAgingData(
  row: any,
  newSegments: AgingSegment[],
  isThreePeriod: boolean,
): any {
  const result = { ...row }

  if (row.agingPrior && typeof row.agingPrior === 'object') {
    result.agingPrior = remapAgingData(row.agingPrior, newSegments)
  }
  // F1-2 等含期末未审账龄：有 agingCurrent 即重映射（isThreePeriod 或已有字段）
  if ((isThreePeriod || row.agingCurrent) && row.agingCurrent && typeof row.agingCurrent === 'object') {
    result.agingCurrent = remapAgingData(row.agingCurrent, newSegments)
  } else if (isThreePeriod) {
    result.agingCurrent = remapAgingData({}, newSegments)
  }
  if (row.agingAudited && typeof row.agingAudited === 'object') {
    result.agingAudited = remapAgingData(row.agingAudited, newSegments)
  }

  return result
}

// ─── 序列化清洗 ───────────────────────────────────────────────────────────────

/**
 * 清洗行数据，确保序列化时不含任何 D2 flat 字段 key
 *
 * 用于保存前的最终清洗，保证 Requirement 10.4：
 * "THE Detail_Composable SHALL serialize data exclusively in the new nested format
 *  after migration, eliminating the old flat-field keys from stored JSON"
 *
 * Requirements: 10.4
 */
export function stripLegacyFlatKeys(row: any): any {
  const result: any = {}
  for (const key of Object.keys(row)) {
    if (!D2_FLAT_KEYS.has(key)) {
      result[key] = row[key]
    }
  }
  return result
}

// ─── 内部工具 ─────────────────────────────────────────────────────────────────

/** 安全转换为数字，null/undefined/NaN → 0 */
function _toNumber(val: any): number {
  if (val == null) return 0
  const num = Number(val)
  return Number.isFinite(num) ? num : 0
}
