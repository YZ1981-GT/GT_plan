/**
 * B50 行身份与持久化键 —— BC-48「label 作 identity」的存储层修复。
 *
 * spec: b-class-shared-base-carrier-lanes（BC-48）
 *
 * ═══ 改造前的缺陷 ═══════════════════════════════════════════════════════════
 *
 * B50-T3 风险矩阵的全部持久化键都以**科目名称**作身份：
 *
 *     B50-T3-cycle-{科目名}          B50-T3-balance-{科目名}
 *     B50-T3-plan-{科目名}-reliance  B50-T3-matrix-{科目名}-{认定}-{层}
 *
 * 危害分两层：
 *   ① **接真双向必错**：OO 侧把「应收账款」改成「应收账款净额」，HTML 侧按新名字
 *      读不到任何数据 ⇒ 整行风险评估（6 认定 × 3 层 = 18 个格）静默孤立，
 *      而旧键仍留在库里占位。这不是丢数据，是**数据变成读不到的垃圾**。
 *   ② **同名科目撞键**：两笔「其他应收款」共用同一套键 ⇒ 后写覆盖先写。
 *
 * ═══ 改造口径：身份段换 rowKey，读取双路兼容 ═══════════════════════════════
 *
 * 写：一律用 `rowKey`（值化身份，见 `shared/rowIdentity.newRowIdentity`）。
 * 读：先按 `rowKey` 找；找不到再按**科目名**找（存量数据），命中即视为该行数据。
 *
 * 🔴 为什么不做"一次性重写全部旧键"：B50 的键散落 7 种形态 × 6 认定 × 3 层，
 * 单科目最多 23 个键。批量重写要在载入期发一个巨大的 PUT，失败即半迁移（部分键
 * 已改名、部分没改）⇒ 比不迁移更糟。改为**惰性迁移**：读时双路兼容，任一编辑
 * 触发该行落库时自然写成新键形态。旧键留库不影响读取（新键优先），
 * 由后续清理任务处置。
 */

/** B50-T3 行级键的字段类型。 */
export type B50RowField =
  | 'cycle'
  | 'balance'
  | 'category'
  | 'estimate'

/** B50-T3 应对方案（plan）子字段。 */
export type B50PlanField = 'reliance' | 'subonly' | 'approach'

/**
 * 行级键：`B50-T3-{field}-{identity}`。
 *
 * @param identity 权威身份（rowKey）；迁移回读时传科目名。
 */
export function b50RowItemId(field: B50RowField, identity: string): string {
  return `B50-T3-${field}-${identity}`
}

/** 应对方案键：`B50-T3-plan-{identity}-{field}`。 */
export function b50PlanItemId(identity: string, field: B50PlanField | string): string {
  return `B50-T3-plan-${identity}-${field}`
}

/** 矩阵单元格键：`B50-T3-matrix-{identity}-{认定}-{层后缀}`。 */
export function b50CellItemId(
  identity: string,
  assertion: string,
  suffix: string,
): string {
  return `B50-T3-matrix-${identity}-${assertion}-${suffix}`
}

/** 科目清单键（存 rowKey + name 配对，使身份可跨会话还原）。 */
export const B50_ACCOUNTS_ITEM_ID = 'B50-T3-accounts'

/**
 * 科目清单的持久化载荷。
 *
 * 🔴 形态演进（两种都要能读）：
 *   - legacy：`["应收账款","存货"]`（纯名字数组，身份即名字）
 *   - 新：`[{"rowKey":"B50-acct-…","name":"应收账款"}, …]`
 *
 * 写一律用新形态；读时按元素类型分流。
 */
export interface B50AccountRef {
  rowKey: string
  name: string
}

/** 解析科目清单（兼容 legacy 纯名字数组）。 */
export function parseAccountRefs(remark: string | null | undefined): B50AccountRef[] {
  if (!remark) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(remark)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []

  const out: B50AccountRef[] = []
  for (const raw of parsed) {
    if (typeof raw === 'string') {
      // legacy：身份即名字。rowKey 暂留空，由调用方铸造后回写。
      const name = raw.trim()
      if (name) out.push({ rowKey: '', name })
      continue
    }
    if (raw && typeof raw === 'object') {
      const obj = raw as Record<string, unknown>
      const name = String(obj.name ?? '').trim()
      if (!name) continue
      out.push({
        rowKey: String(obj.rowKey ?? '').trim(),
        name,
      })
    }
  }
  return out
}

/** 序列化科目清单（一律写新形态）。 */
export function serializeAccountRefs(refs: readonly B50AccountRef[]): string {
  return JSON.stringify(refs.map((r) => ({ rowKey: r.rowKey, name: r.name })))
}

/**
 * 双路读取：先按 rowKey 找，未命中再按科目名找（存量数据）。
 *
 * @param lookup 取值函数（通常是 `items.get`）
 * @param build  键构造函数，接收 identity 返回 item_id
 */
export function readWithLegacyFallback<T>(
  lookup: (itemId: string) => T | undefined,
  build: (identity: string) => string,
  rowKey: string,
  accountName: string,
): T | undefined {
  if (rowKey) {
    const byKey = lookup(build(rowKey))
    if (byKey !== undefined) return byKey
  }
  // 存量：身份即科目名
  if (accountName) return lookup(build(accountName))
  return undefined
}
