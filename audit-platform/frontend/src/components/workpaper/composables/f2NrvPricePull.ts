/**
 * F2 存货可变现净值（NRV）售价参考取数
 *
 * 审计意义：CAS1 存货期末按成本与可变现净值孰低计量。NRV = 估计售价 − 至完工成本
 * − 销售费用及税金。本 composable 从收入侧序时账（6001 主营业务收入贷方）提取近期
 * 销售单价，作为 NRV 估计售价的客观参考（近期成交价优于管理层单方估计）。
 *
 * 数据源：GET /api/projects/{pid}/ledger/entries/6001?year=&limit=1000
 *   贷方 credit_amount = 收入确认额；单价 = 贷方金额 / 数量。
 *
 * 优雅降级：无 projectId/年度 → error；无收入分录 / 无有效单价 → 空数组 + status='empty'（不抛错）。
 */
import { api } from '@/services/apiProxy'

/** 主营业务收入科目（默认 6001） */
export const OPERATING_REVENUE_ACCOUNT = '6001'

/** 售价参考来源标签 */
export const SALES_PRICE_SOURCE_LEDGER = '序时账6001'

export interface SalesPriceRef {
  /** 存货 / 商品名称 */
  name: string
  /** 销售单价 = 贷方金额 / 数量 */
  unitPrice: number
  /** 取数来源标签（如「序时账6001」/「D4明细」） */
  source: string
}

export interface RecentSalesPriceResult {
  status: 'ok' | 'empty' | 'error'
  prices: SalesPriceRef[]
  message: string
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 名称规范化（去空白/全角空格 + 小写），供模糊匹配 */
function normalizeName(v: unknown): string {
  return String(v ?? '')
    .replace(/[\s\u3000]+/g, '')
    .toLowerCase()
}

function resolveItemName(entry: any): string {
  const candidates = [
    entry?.aux_name, entry?.auxName,
    entry?.item_name, entry?.itemName,
    entry?.product_name, entry?.productName,
    entry?.goods_name, entry?.goodsName,
    entry?.name, entry?.summary,
    entry?.counterpart_account, entry?.counterpartAccount,
  ]
  for (const c of candidates) {
    const s = String(c ?? '').trim()
    if (s) return s
  }
  return ''
}

/**
 * 纯函数：从收入侧序时账 / D4 明细行提取销售单价参考。
 *
 * 规则：
 * - 单价 = 贷方金额(credit) / 数量(quantity)，数量 ≤ 0 或 贷方 ≤ 0 的行跳过（无法算单价）
 * - itemName 提供时按规范化名称包含匹配过滤
 *
 * @param entries 序时账分录 / 明细行数组
 * @param itemName 可选：仅返回匹配该存货名称的单价
 * @param source 来源标签（默认「序时账6001」）
 */
export function parseSalesPriceEntries(
  entries: unknown,
  itemName?: string,
  source: string = SALES_PRICE_SOURCE_LEDGER,
): SalesPriceRef[] {
  const list = Array.isArray(entries) ? entries : []
  const wanted = itemName ? normalizeName(itemName) : ''
  const out: SalesPriceRef[] = []

  for (const e of list) {
    const qty = parseNum(e?.credit_quantity ?? e?.creditQuantity ?? e?.quantity ?? e?.qty)
    if (qty <= 0) continue
    const credit = parseNum(e?.credit_amount ?? e?.creditAmount ?? e?.credit)
    if (credit <= 0) continue
    const rawName = resolveItemName(e)
    if (wanted && !normalizeName(rawName).includes(wanted)) continue
    out.push({
      name: rawName || '未命名商品',
      unitPrice: credit / qty,
      source,
    })
  }

  return out
}

/**
 * 拉取近期销售单价参考（NRV 估计售价参考）。
 *
 * @param projectId 项目 ID
 * @param year 审计年度
 * @param itemName 可选：仅取指定存货的销售单价
 */
export async function pullRecentSalesPrice(
  projectId: string,
  year: number,
  itemName?: string,
): Promise<RecentSalesPriceResult> {
  const empty: RecentSalesPriceResult = { status: 'error', prices: [], message: '' }
  if (!projectId) return { ...empty, message: '缺少 projectId' }
  if (!year || !Number.isFinite(Number(year))) return { ...empty, message: '缺少有效审计年度' }

  try {
    const res = await api.get<any>(`/api/projects/${projectId}/ledger/entries/${OPERATING_REVENUE_ACCOUNT}`, {
      params: { year, limit: 1000 },
      _silent: true,
    } as any)
    const payload = res?.data ?? res
    const items: any[] = Array.isArray(payload)
      ? payload
      : Array.isArray(payload?.items)
        ? payload.items
        : Array.isArray(payload?.ledger?.items)
          ? payload.ledger.items
          : []

    const prices = parseSalesPriceEntries(items, itemName)
    if (prices.length === 0) {
      return {
        status: 'empty',
        prices: [],
        message: itemName
          ? `未找到「${itemName}」的近期销售单价，请手工确定 NRV 估计售价`
          : '收入序时账无可算单价的分录（缺数量），请手工确定 NRV 估计售价',
      }
    }
    return {
      status: 'ok',
      prices,
      message: `已取 ${prices.length} 条近期销售单价参考`,
    }
  } catch (e: any) {
    return { ...empty, status: 'error', message: e?.message || '销售单价取数失败' }
  }
}
