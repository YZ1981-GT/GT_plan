/**
 * F2 存货族 — 科目码单一真源（K2 范式）。
 *
 * spec: voucher-attach-account-mapping-closure（批次 3b，任务 8）
 *
 * ## 兜底码 1401~1412
 *
 * 存货科目区间与 `f2NoteSectionMap.F2_INVENTORY_ACCOUNT_CODES` 一致（12 个标准码）。
 * 运行态取 render 下发的 `tb_source_codes`，三层降级：
 *   1. `gross` 非空 → 客户原始码前缀（最精确）
 *   2. `gross_standard` 非空 → 标准码
 *   3. 均空 → 兜底 1401~1412
 *
 * 🔴 本模块与 `f2ContractCostAccountScope.ts` 互不干涉：
 * - 存货主表（购入检查 / 用量检查 / 估值 / 截止测试）→ 本模块（1401~1412）
 * - 合同履约成本检查 → `f2ContractCostAccountScope`（宁缺勿造，兜底空串）
 */

import type { TbSourceCodes } from './shared/tbSourceCodes'

/**
 * 兜底标准码：存货科目 1401~1412（与审定取数口径一致）。
 *
 * 🔴 与 `f2NoteSectionMap.F2_INVENTORY_ACCOUNT_CODES` 同口径，
 * 此处独立声明避免循环引用（`f2NoteSectionMap` 含附注映射逻辑，
 * AccountScope 不应依赖它）。
 */
export const F2_INVENTORY_FALLBACK_CODES: readonly string[] = Array.from(
  { length: 12 },
  (_, i) => String(1401 + i),
)

/** 科目中文名（展示与提示文案用） */
export const F2_INVENTORY_ACCOUNT_NAME = '存货'

/**
 * 查询口径科目码集。三层降级：
 *
 * 1. `src.gross` 非空 → 客户原始码前缀（企业自定义编码映射后的结果）
 * 2. `src.gross_standard` 非空 → 标准码
 * 3. 均空或 src 为 null → 兜底 1401~1412（向后兼容）
 *
 * 🔴 字段名与共享 `TbSourceCodes` 对齐：`gross` = 客户原始码，
 * `gross_standard` = 标准码。E1/F2ContractCost 等用独立接口的
 * `gross_raw` 对应此处的 `gross`。
 */
export function f2InventoryQueryCodes(
  src?: TbSourceCodes | null,
): string[] {
  // 优先取客户原始码（gross = 客户码前缀集）
  const raw = normalize(src?.gross)
  if (raw.length) return raw

  // 次选标准码
  const std = normalize(src?.gross_standard)
  if (std.length) return std

  // 兜底
  return [...F2_INVENTORY_FALLBACK_CODES]
}

/**
 * 单一科目码（account-code prop / EventBus 载荷用）。
 *
 * 取 `f2InventoryQueryCodes` 首码；解析不出时退 `'1401'`。
 */
export function f2InventoryAccountCode(
  src?: TbSourceCodes | null,
): string {
  return f2InventoryQueryCodes(src)[0] || '1401'
}

/**
 * 从 render-config 返回的 `htmlData` 中提取 F2 存货族的 `tb_source_codes`。
 *
 * 与 F1 `pickF1TbSourceCodes` / F3 `pickF3TbSourceCodes` 同构：
 * 顶层优先、`project_context` 兼容。
 * 后端 `get_render_config` 把映射结果放 `html_data.tb_source_codes`；
 * 部分旧路径可能放在 `html_data.project_context.tb_source_codes`。
 * 两处都读、不做假设，返回 null 时调用方退到兜底码。
 */
export function pickF2InventoryTbSourceCodes(
  htmlData: unknown,
): TbSourceCodes | null {
  if (!htmlData || typeof htmlData !== 'object') return null
  const hd = htmlData as Record<string, any>
  const fromTop = hd.tb_source_codes
  if (fromTop && typeof fromTop === 'object') return fromTop as TbSourceCodes
  const pc = hd.project_context
  if (pc && typeof pc === 'object') {
    const fromPc = (pc as Record<string, any>).tb_source_codes
    if (fromPc && typeof fromPc === 'object') return fromPc as TbSourceCodes
  }
  return null
}

// ── 内部工具 ──────────────────────────────────────────────

/** 去重 + 去空白（与 f2ContractCostAccountScope 的 normalize 同逻辑） */
function normalize(list?: string[] | null): string[] {
  const out: string[] = []
  for (const x of list ?? []) {
    const s = String(x ?? '').trim()
    if (s && !out.includes(s)) out.push(s)
  }
  return out
}
