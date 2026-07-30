/**
 * 动态子表名的孤儿表清理（跨循环共享纯函数）
 *
 * 背景：披露同步按 key **浅合并**（为支持 H4 只推自己那张表而不清空 H2 的明细），
 * 删除必须显式上报 `_removed_table_keys`。平台机制齐全（后端 `_drop_removed_tables`，
 * 且保证「本次推送的 key 绝不删」），但既有实现有两个缺口：
 *
 * 1. 只有上市分支上报，国企分支未接；
 * 2. 上市侧用**静态**常量（`D2_LISTED_OBSOLETE_TABLE_KEYS`），而组合分表名是
 *    **动态**的（随审计师命名）→ 静态列表覆盖不了。实测：把组合分表
 *    「应收中央企业客户」改名为「应收政府客户」后再同步，附注 `sub_table_data`
 *    与 `_sub_table_columns` **同时残留两个 key** → 附注永久多一个空 TAB。
 *
 * 解法：底稿持久化「上次推送的数据子表名清单」，下次构建载荷时做差集。
 *
 * spec: .kiro/specs/disclosure-columns-coverage-rollout/ R7（Task 14.1）
 */

/** 元数据键前缀：`_note_texts` / `_removed_table_keys` / `_source` 等不是数据子表 */
const META_PREFIX = '_'

function isMetaKey(key: string): boolean {
  return String(key).startsWith(META_PREFIX)
}

function normalize(name: unknown): string {
  return String(name ?? '').trim()
}

/**
 * 从同步载荷的 `sub_table_data` 取出**数据子表名**（排除 `_` 前缀元数据键）。
 *
 * 用于两处：
 * - 构建 `_removed_table_keys` 时算「本次推送集合」（推送优先，绝不删）；
 * - 同步**成功后** `markSynced()` 持久化，供下次做差集。
 */
export function dataTableNames(
  subTableData: Record<string, unknown> | null | undefined,
): string[] {
  if (!subTableData || typeof subTableData !== 'object' || Array.isArray(subTableData)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const key of Object.keys(subTableData)) {
    if (isMetaKey(key)) continue
    const name = normalize(key)
    if (!name || seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return out
}

export interface BuildRemovedTableKeysInput {
  /** 上次同步成功时推送的数据子表名（持久化读出；首次启用为空） */
  previouslySynced?: readonly string[] | null
  /** 该变体历史遗留的静态旧表名（首次启用时唯一来源，保证清理能力不退化） */
  legacyObsolete?: readonly string[] | null
  /** 本次推送的数据子表名（`dataTableNames(subTableData)`） */
  pushed?: readonly string[] | null
}

/**
 * `_removed_table_keys` = (上次已同步 ∪ 历史遗留静态键) − 本次推送。
 *
 * 不变式：
 * - **推送优先**：出现在 `pushed` 的名字绝不进结果（与后端 `_drop_removed_tables` 同向双保险）；
 * - **去重且顺序稳定**：先 `previouslySynced` 顺序、再 `legacyObsolete` 顺序（便于 diff 复现）；
 * - **空白名剔除**：空串 / 纯空白不进结果（否则后端会拿空 key 去删）。
 */
export function buildRemovedTableKeys(input: BuildRemovedTableKeysInput): string[] {
  const pushed = new Set((input.pushed ?? []).map(normalize).filter(Boolean))
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of [...(input.previouslySynced ?? []), ...(input.legacyObsolete ?? [])]) {
    const name = normalize(raw)
    // 空白名剔除（否则后端拿空 key 去删）；元数据键剔除（`_note_texts` 不是数据子表，
    // 早期持久化清单可能误存了它）；本次推送的名字绝不删（推送优先）
    if (!name || isMetaKey(name) || pushed.has(name) || seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return out
}

/**
 * 把 `_removed_table_keys` 挂到载荷（空数组不挂键，保持载荷干净 / 与既有形态一致）。
 *
 * @returns 实际上报的键（供调用方日志/断言）
 */
export function attachRemovedTableKeys(
  subTableData: Record<string, unknown>,
  input: BuildRemovedTableKeysInput,
): string[] {
  const removed = buildRemovedTableKeys({ ...input, pushed: input.pushed ?? dataTableNames(subTableData) })
  if (removed.length) subTableData._removed_table_keys = removed
  return removed
}

/**
 * 该底稿在某章节的「表名命名空间」声明（R7.5 基线播种用）。
 *
 * 为什么需要：`buildRemovedTableKeys` 的差集基线来自底稿自己持久化的
 * `previouslySynced`，因此**基线建立之前**就残留在附注里的孤儿表永远进不了差集
 * （实测：某项目附注 §八、5 残留 `组合计提项目：应收中央企业客户`）。
 * 首次同步时用本谓词过滤附注**现存**表名来播种基线，即可一次性自愈。
 *
 * 🔴 谓词必须严格：同一附注章节可能被多张底稿推送（H2 明细 + H4 汇总），
 * 误判别人的表为「自己的孤儿」会把别的底稿数据删掉。因此只认
 * ① 本底稿固定表名全集；② 本底稿动态表名前缀；③ 本底稿续表后缀。
 */
export interface TableNamespaceSpec {
  /** 固定表名全集（`X_TABLE_NAMES[variant]` 的全部值） */
  known?: readonly string[]
  /** 动态表名前缀（如 D2 组合分表 `组合计提项目：`） */
  prefixes?: readonly string[]
  /** 续表后缀（如 `（续：期初数）` / `（续：上年年末余额）`），可叠加在 known 之上 */
  suffixes?: readonly string[]
}

/** 表名是否属于该底稿的命名空间（严格谓词，宁漏不误杀） */
export function isOwnedTableName(name: unknown, spec: TableNamespaceSpec): boolean {
  const n = normalize(name)
  if (!n || isMetaKey(n)) return false
  const known = (spec.known ?? []).map(normalize).filter(Boolean)
  if (known.includes(n)) return true
  for (const suffix of spec.suffixes ?? []) {
    const s = normalize(suffix)
    if (!s || !n.endsWith(s)) continue
    // 续表名 = 已知表名 + 后缀（不接受任意表名 + 后缀，避免吞掉别的底稿续表）
    if (known.includes(n.slice(0, n.length - s.length))) return true
  }
  for (const prefix of spec.prefixes ?? []) {
    const p = normalize(prefix)
    if (p && n.startsWith(p) && n.length > p.length) return true
  }
  return false
}

/**
 * 从附注 detail 的 `table_data` 取出**可被 `_removed_table_keys` 删除**的现存表名。
 *
 * 只取 `sub_table_data` 与 `_sub_table_columns` 的键 —— 后端 `_drop_removed_tables`
 * 只从这两处删；`_tables` 是读时投影/生成快照，不受 removed 键影响，纳入只会虚报。
 */
export function noteExistingTableNames(tableData: unknown): string[] {
  if (!tableData || typeof tableData !== 'object' || Array.isArray(tableData)) return []
  const td = tableData as Record<string, unknown>
  const out: string[] = []
  const seen = new Set<string>()
  for (const bucket of [td.sub_table_data, td._sub_table_columns]) {
    if (!bucket || typeof bucket !== 'object' || Array.isArray(bucket)) continue
    for (const key of Object.keys(bucket as Record<string, unknown>)) {
      const name = normalize(key)
      if (!name || isMetaKey(name) || seen.has(name)) continue
      seen.add(name)
      out.push(name)
    }
  }
  return out
}

/**
 * 首次同步的基线播种：附注现存表名 ∩ 本底稿命名空间。
 *
 * 结果作为 `previouslySynced` 参与差集 → 本轮推送不含的历史键立即被清理，
 * 而**别的底稿**推的表名（不在命名空间内）原样保留。
 */
export function seedSyncedTableBaseline(
  tableData: unknown,
  spec: TableNamespaceSpec,
): string[] {
  return noteExistingTableNames(tableData).filter((n) => isOwnedTableName(n, spec))
}

/** 持久化载荷（JSON 字符串）解析：非法 / 非数组 → 空数组 */
export function parseSyncedTableNames(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const out: string[] = []
    const seen = new Set<string>()
    for (const x of parsed) {
      const name = normalize(x)
      if (!name || seen.has(name)) continue
      seen.add(name)
      out.push(name)
    }
    return out
  } catch {
    return []
  }
}

/** 持久化序列化（去重 + 去空白，顺序稳定） */
export function serializeSyncedTableNames(names: readonly string[]): string {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of names) {
    const name = normalize(raw)
    if (!name || seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return JSON.stringify(out)
}
