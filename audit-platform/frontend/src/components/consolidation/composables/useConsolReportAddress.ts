/**
 * useConsolReportAddress — 合并报表 报表行 / account 引用地址真源 (Req 20.1 / 20.2 / 20.7 / 20.9)
 *
 * 背景（第四轮复盘 P14 实证）：`ConsolidationIndex.vue` 的合并报表（Tab 5）报表行按
 * `row_code`（如 BS-001 / IS-019）展示为纯文本；`consolidation.reports.consolBreakdown(accountCode)`
 * 报表级穿透按 `standard_account_code`（如 1122）drill——两者均未经 ACNR 解析，无法 chip/trace/jump。
 *
 * 本 composable 把「报表行 / account 引用的地址真源」收敛到 ACNR-backed 地址 store
 * （Req 16，REPORT 域 + TB 域）与 `useAcnr()` resolver：
 *   - REPORT 域（`reportAddresses`）：确认报表行 `row_code` 是否为 canonical 已登记地址，
 *     并提供 `row_code → standard_account_code` 映射（若注册表条目携带 account_code）。
 *   - TB 域（`tbAddresses`）：account_code canonical 集合，供 GtIndexChip `TB:{code}` 渲染 gate。
 *   - `resolveAccountJump(accountCode)`：consolBreakdown drill 的 account_code 经 ACNR TB 域
 *     解析取 jump_route（`resolveIndex('TB:'+code)` → 回退 `resolveUri('tb://'+code)`）。
 *
 * 设计要点（Req 20.7 降级 / Req 20.9 数值不变）：
 *   - REPORT/TB 注册表为空/不可用 或 地址 miss → 返回 null / found=false，
 *     调用方回退纯文本展示（不可跳转），不空白（Req 20.7）。
 *   - 本 helper 只提供「地址/坐标名称来源 + 跳转路由」，不参与报表数值/生成/balance-check
 *     计算，故报表数字逐字节不变（Req 20.9）。
 *
 * 复用：GtIndexChip 的 `value` 需要索引 ns 语法（如 `TB:1122`），**不能**直接传含 `/`
 * 的裸 addr_id（会被 parseIndexRef 误判为多目标）。故 account 引用统一转为 `TB:{code}`。
 */
import { computed, type ComputedRef } from 'vue'
import { storeToRefs } from 'pinia'
import { useAddressRegistry } from '@/stores/addressRegistry'
import { useAcnr, type AcnrResolveResult } from '@/services/acnr/useAcnr'

/** 解析结果（consolBreakdown drill 用）。 */
export interface AccountJumpResult {
  found: boolean
  jumpRoute: string | null
  accountCode: string
}

export interface ConsolReportAddressApi {
  /** REPORT 域 canonical row_code 集合（供报表行地址确认 + 契约测试）。 */
  reportRowCodes: ComputedRef<Set<string>>
  /** TB 域 canonical account_code 集合（供 GtIndexChip TB chip gate + 契约测试）。 */
  tbAccountCodes: ComputedRef<Set<string>>
  /** 当前是否由 ACNR-backed REPORT/TB 注册表支撑（false = 降级纯文本）。 */
  isRegistryBacked: ComputedRef<boolean>
  /** 报表行 row_code 是否为 REPORT 域已登记 canonical 地址。 */
  isReportRowRegistered: (rowCode: string) => boolean
  /** 裁定某报表行对应的 standard_account_code（供 TB 域 chip / drill）。 */
  accountForRow: (row: Record<string, unknown> | null | undefined) => string | null
  /**
   * 构建 GtIndexChip 可解析的 TB 域索引 ns 语法 `TB:{accountCode}`。
   * accountCode 为空 → null；TB 注册表非空但 accountCode 未登记 → null（回退纯文本，Req 20.7）；
   * TB 注册表为空（未加载）→ null（降级，不做假 chip）。
   */
  accountIndexRef: (accountCode: string | null | undefined) => string | null
  /**
   * consolBreakdown drill：account_code 经 ACNR TB 域解析取 jump_route（Req 20.1）。
   * 先 `resolveIndex('TB:'+code)`，miss 再 `resolveUri('tb://'+code)`；均 miss → found=false。
   * ACNR 不可用/异常 → found=false（调用方回退纯文本/现有行为，Req 20.7）。
   */
  resolveAccountJump: (accountCode: string | null | undefined) => Promise<AccountJumpResult>
}

/** 名称/编码归一化：去首尾空白。 */
function norm(s: unknown): string {
  return typeof s === 'string' ? s.trim() : ''
}

/**
 * 合并报表 报表行 / account 引用地址真源 composable。
 *
 * 读取全局 `useAddressRegistry` store 的 `reportAddresses`（REPORT 域）/ `tbAddresses`（TB 域），
 * 均为 ACNR-backed（Req 16）。store 由应用其他部分在切项目/年度时 `refresh()` 填充；
 * 未填充时自然走降级（Req 20.7 无回归）。
 */
export function useConsolReportAddress(): ConsolReportAddressApi {
  const { resolveIndex, resolveUri } = useAcnr()

  // 无活跃 Pinia（纯函数单测环境）时降级为 null → 全部走 miss 回退。
  let store: ReturnType<typeof useAddressRegistry> | null = null
  try {
    store = useAddressRegistry()
  } catch {
    store = null
  }

  const reportAddresses = store ? storeToRefs(store).reportAddresses : computed(() => [])
  const tbAddresses = store ? storeToRefs(store).tbAddresses : computed(() => [])

  // REPORT 域：row_code → 是否登记；row_code → account_code 映射（条目携带时）
  const reportRowCodes = computed<Set<string>>(() => {
    const set = new Set<string>()
    for (const a of reportAddresses.value as Array<{ row_code?: string }>) {
      const code = norm(a?.row_code)
      if (code) set.add(code)
    }
    return set
  })

  const rowToAccount = computed<Map<string, string>>(() => {
    const map = new Map<string, string>()
    for (const a of reportAddresses.value as Array<{ row_code?: string; account_code?: string }>) {
      const rc = norm(a?.row_code)
      const ac = norm(a?.account_code)
      if (rc && ac && !map.has(rc)) map.set(rc, ac)
    }
    return map
  })

  // TB 域：canonical account_code 集合
  const tbAccountCodes = computed<Set<string>>(() => {
    const set = new Set<string>()
    for (const a of tbAddresses.value as Array<{ account_code?: string; code?: string }>) {
      const code = norm(a?.account_code) || norm((a as { code?: string })?.code)
      if (code) set.add(code)
    }
    return set
  })

  const isRegistryBacked = computed(
    () => reportRowCodes.value.size > 0 || tbAccountCodes.value.size > 0,
  )

  function isReportRowRegistered(rowCode: string): boolean {
    return reportRowCodes.value.has(norm(rowCode))
  }

  function accountForRow(row: Record<string, unknown> | null | undefined): string | null {
    if (!row || typeof row !== 'object') return null
    // 优先行自带的标准科目码，其次经 REPORT 注册表 row_code → account_code 映射
    const direct =
      norm((row as { standard_account_code?: unknown }).standard_account_code) ||
      norm((row as { account_code?: unknown }).account_code)
    if (direct) return direct
    const rc = norm((row as { row_code?: unknown }).row_code)
    if (rc) {
      const mapped = rowToAccount.value.get(rc)
      if (mapped) return mapped
    }
    return null
  }

  function accountIndexRef(accountCode: string | null | undefined): string | null {
    const code = norm(accountCode)
    if (!code) return null
    // TB 注册表已加载：仅对已登记 account_code 渲染 chip（否则回退纯文本，Req 20.7）
    if (tbAccountCodes.value.size > 0) {
      return tbAccountCodes.value.has(code) ? `TB:${code}` : null
    }
    // TB 注册表未加载：不做假 chip，降级纯文本
    return null
  }

  async function resolveAccountJump(
    accountCode: string | null | undefined,
  ): Promise<AccountJumpResult> {
    const code = norm(accountCode)
    if (!code) return { found: false, jumpRoute: null, accountCode: '' }
    try {
      // 1) 索引 ns 语法解析（TB 域）
      let res: AcnrResolveResult = await resolveIndex(`TB:${code}`)
      // 2) miss → 回退 tb:// URI 形态
      if (!res.found) {
        res = await resolveUri(`tb://${code}`)
      }
      if (res.found && res.jump_route) {
        return { found: true, jumpRoute: res.jump_route, accountCode: code }
      }
      return { found: false, jumpRoute: null, accountCode: code }
    } catch {
      // ACNR 不可用/异常 → 回退（Req 20.7）
      return { found: false, jumpRoute: null, accountCode: code }
    }
  }

  return {
    reportRowCodes,
    tbAccountCodes,
    isRegistryBacked,
    isReportRowRegistered,
    accountForRow,
    accountIndexRef,
    resolveAccountJump,
  }
}
