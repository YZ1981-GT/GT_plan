/**
 * useA13MisstatementBridge — 底稿"推送错报至 A13 错报汇总"事件的唯一消费者
 *
 * 背景（2026-07-24 调整分录联动复盘）：全平台 ~35 个底稿的调整/截止/检查页
 * 都通过 `eventBus.emit('a13:push-misstatement', payload)` 推送错报，但**零消费者**
 * ——每个"推送错报至A13错报汇总"按钮点了都没落库（死事件）。
 *
 * 本桥挂载在 WorkpaperEditor Shell（拥有 projectId/year 上下文，且所有底稿子组件
 * 都在其内），监听 `a13:push-misstatement`，归一化两种 payload 形态后调用
 * `POST /api/projects/{pid}/misstatements` 写入 `unadjusted_misstatements` 表
 * （即 Misstatements.vue「未更正错报汇总」的数据源），并携带 source_wp_code 溯源。
 *
 * payload 形态（历史各异，本桥统一归一）：
 *  A. { items: [{ wpCode?, description, accountName?, debitAmount, creditAmount, indexRef? }] }
 *  B. { wpCode, accountCode, accountName?, entries: [{ description, debitAmount, creditAmount, ... }] }
 *  C. { wpCode, accountCode, source?, items: [{ voucherNo, amount, description, indexRef }] }
 *  D. { wpCode, accountCode, amount, description }   ← 扁平单行
 *
 * @see .kiro/steering/memory.md §调整分录模块复盘
 */
import { onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import { createMisstatement } from '@/services/auditPlatformApi'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * 错报类型（CAS 1251 三分类，与 PG enum `misstatement_type` 逐字对齐）。
 *
 * - `factual` 事实错报：已确认的具体错报（既有 ~35 个底稿推送点的语义）
 * - `judgmental` 判断错报：因会计估计/政策选择差异形成的错报
 * - `projected` 推断错报：抽样样本错报按抽样口径外推到总体的错报（CAS 1314 输出）
 *
 * 改造前本桥把类型硬编码为 `factual`，导致后两值在全库零使用 —— 抽样算出的
 * 推断错报无法进入错报汇总，「样本错报 → 总体错报 → 与重要性比较」这条准则主线断裂。
 */
export type MisstatementTypeValue = 'factual' | 'judgmental' | 'projected'

export const MISSTATEMENT_TYPES: readonly MisstatementTypeValue[] = [
  'factual',
  'judgmental',
  'projected',
] as const

export interface MisstatementDraft {
  /** 来源底稿编码（溯源，写入 source_wp_code；截断 ≤20 字符对齐 DB 列宽） */
  wpCode: string
  /** 错报描述（已内联凭证号/索引，便于溯源） */
  description: string
  /** 受影响科目编码（可空） */
  accountCode: string | null
  /** 受影响科目名称（可空） */
  accountName: string | null
  /** 错报金额（正数；借贷取绝对值较大者或显式 amount） */
  amount: number
  /** 原始索引号（保留供测试/后续使用） */
  indexRef: string
  /** 错报类型（缺省 `factual`，保既有推送点逐字节等价） */
  misstatementType: MisstatementTypeValue
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 错报类型归一：非法/缺失一律回退 `factual`。
 *
 * 回退而非透传的理由：透传非法值会让后端 enum 校验拒绝**整批**推送，
 * 一个字段拼错就把审计师这一批错报全打掉。
 */
export function normalizeMisstatementType(v: unknown): MisstatementTypeValue {
  const s = typeof v === 'string' ? v : ''
  return (MISSTATEMENT_TYPES as readonly string[]).includes(s)
    ? (s as MisstatementTypeValue)
    : 'factual'
}

/**
 * 归一化 `a13:push-misstatement` payload → 错报草稿列表（纯函数，可单测）。
 * 金额 ≤0 的行不生成错报（错报汇总必须有金额）。
 */
export function normalizeMisstatementPushPayload(payload: any): MisstatementDraft[] {
  if (!payload || typeof payload !== 'object') return []

  const topWpCode = String(payload.wpCode ?? payload.wp_code ?? '')
  const topAccountCode = payload.accountCode ?? payload.account_code ?? null
  const topAccountName = payload.accountName ?? payload.account_name ?? null
  const topSource = String(payload.source ?? '')
  const topAmount = toNum(payload.amount ?? payload.misstatement_amount)
  // 顶层错报类型（行级优先于顶层；两者皆缺 → factual，等价于改造前行为）
  const topTypeRaw = payload.misstatementType ?? payload.misstatement_type

  // 行集合优先级：items > entries > 扁平单行(payload 自身)
  let rawRows: any[]
  if (Array.isArray(payload.items) && payload.items.length) rawRows = payload.items
  else if (Array.isArray(payload.entries) && payload.entries.length) rawRows = payload.entries
  else rawRows = [payload]

  const drafts: MisstatementDraft[] = []
  for (const r of rawRows) {
    if (!r || typeof r !== 'object') continue

    const debit = toNum(r.debitAmount ?? r.debit_amount)
    const credit = toNum(r.creditAmount ?? r.credit_amount)
    const explicitAmt = toNum(r.amount ?? r.misstatement_amount)
    let amount = explicitAmt || Math.max(Math.abs(debit), Math.abs(credit))
    // 扁平单行金额可能只在顶层
    if (amount <= 0 && r === payload) amount = topAmount
    if (amount <= 0) continue

    const baseDesc = String(r.description ?? payload.description ?? '').trim() || '底稿推送错报'
    const indexRef = String(r.indexRef ?? r.index_ref ?? topSource).trim()
    const voucherNo = String(r.voucherNo ?? r.voucher_no ?? '').trim()

    let description = baseDesc
    if (voucherNo) description += `（凭证:${voucherNo}）`
    if (indexRef) description += `（索引:${indexRef}）`

    const accountCode = r.accountCode ?? r.affectedAccountCode ?? r.account_code ?? topAccountCode ?? null
    const accountName = r.accountName ?? r.affectedAccountName ?? r.account_name ?? topAccountName ?? null
    const wpCode = String(r.wpCode ?? r.wp_code ?? topWpCode ?? '')

    const rowTypeRaw = r.misstatementType ?? r.misstatement_type
    const misstatementType = normalizeMisstatementType(
      rowTypeRaw !== undefined && rowTypeRaw !== null ? rowTypeRaw : topTypeRaw,
    )

    drafts.push({
      wpCode,
      description,
      accountCode: accountCode ? String(accountCode) : null,
      accountName: accountName ? String(accountName) : null,
      amount,
      indexRef,
      misstatementType,
    })
  }
  return drafts
}

/** 去重窗口（ms）：防 crossWpEventBridge 双投（H3 同时 emit+dispatchEvent）与快速双击。 */
export const DEDUP_WINDOW_MS = 5000

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA13MisstatementBridge(): void {
  const { projectId, year } = useAuditContext()
  const recentHashes = new Map<string, number>()

  function draftHash(d: MisstatementDraft): string {
    // 类型入 hash：同金额同描述的事实错报与推断错报是两笔不同性质的错报
    // （CAS 1251 要求分类汇总），不得互相吞掉。
    return `${d.wpCode}|${d.description}|${d.amount}|${d.accountCode ?? ''}|${d.misstatementType}`
  }

  async function handler(payload: any): Promise<void> {
    const pid = projectId.value
    if (!pid) return

    const drafts = normalizeMisstatementPushPayload(payload)
    if (!drafts.length) return

    // 去重：清理过期 + 过滤本窗口内已推送的相同草稿
    const now = Date.now()
    for (const [h, t] of recentHashes) {
      if (now - t > DEDUP_WINDOW_MS) recentHashes.delete(h)
    }
    const fresh = drafts.filter((d) => {
      const h = draftHash(d)
      if (recentHashes.has(h)) return false
      recentHashes.set(h, now)
      return true
    })
    if (!fresh.length) return

    let ok = 0
    let fail = 0
    for (const d of fresh) {
      try {
        await createMisstatement(pid, {
          year: year.value,
          misstatement_description: d.description,
          affected_account_code: d.accountCode || null,
          affected_account_name: d.accountName || null,
          misstatement_amount: d.amount,
          misstatement_type: d.misstatementType,
          source_wp_code: (d.wpCode || '').slice(0, 20) || null,
        })
        ok += 1
      } catch {
        fail += 1
      }
    }

    if (ok > 0) {
      ElMessage.success(`已记入未更正错报汇总 ${ok} 笔${fail ? `（${fail} 笔失败）` : ''}`)
    } else if (fail > 0) {
      ElMessage.error('推送错报至未更正错报汇总失败')
    }
  }

  onMounted(() => {
    eventBus.on('a13:push-misstatement', handler as any)
  })
  onBeforeUnmount(() => {
    eventBus.off('a13:push-misstatement', handler as any)
  })
}

export default useA13MisstatementBridge
