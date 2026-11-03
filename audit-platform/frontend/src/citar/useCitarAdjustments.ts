/**
 * 调整分录的读写（CITAR 调整分录页用）。全部走平台既有端点：
 * GET/POST /adjustments、PUT/DELETE /adjustments/{group}、POST /{group}/review、POST /{group}/revoke-review。
 * 平台规则不变：只有草稿 / 驳回能改删；只有已批准的分录进入试算表。
 *
 * 所有请求带 _silent：错误由调用方经 handleApiError 提示一次（否则全局拦截器会再弹一遍）。
 */
import { ref } from 'vue'
import { api } from '@/services/apiProxy'
import { adjustments as P_adj } from '@/services/apiPaths'
import { ADJUSTMENT_STATUS } from '@/constants/statusEnum'
import { useDecimalCalc } from '@/composables/useDecimalCalc'

export type Side = 'debit' | 'credit'
export type AdjType = 'aje' | 'rje'
/** 复核动作的目标状态 */
export type ReviewTarget =
  | typeof ADJUSTMENT_STATUS.PENDING_REVIEW
  | typeof ADJUSTMENT_STATUS.APPROVED
  | typeof ADJUSTMENT_STATUS.REJECTED

const { sum } = useDecimalCalc()

export interface AdjLine {
  /** 行内唯一键（计数器，删中间行下标不错位） */
  key: string
  side: Side
  code: string
  name: string
  /** 输入框原文，失焦后格式化成千分位 */
  amount: string
}

export interface AdjEntry {
  /** 已保存的分录组 id；新建未保存为 '' */
  groupId: string
  no: string
  type: AdjType
  description: string
  status: string
  rejectionReason: string
  lines: AdjLine[]
}

const SILENT = { _silent: true } as any
const LIST_PAGE_SIZE = 200

let seq = 0
export const lineKey = () => `l${(seq += 1)}`

export function emptyLine(side: Side): AdjLine {
  return { key: lineKey(), side, code: '', name: '', amount: '' }
}

export function newEntry(): AdjEntry {
  return {
    groupId: '',
    no: '',
    type: 'aje',
    description: '',
    status: ADJUSTMENT_STATUS.DRAFT,
    rejectionReason: '',
    lines: [emptyLine('debit'), emptyLine('credit')],
  }
}

/** 借 / 贷合计（两位小数字符串，十进制精确求和；非法金额按 0） */
export function lineTotals(entry: AdjEntry): { debit: string; credit: string } {
  const pick = (side: Side) =>
    entry.lines.filter(l => l.side === side).map(l => {
      const v = parseAmount(l.amount)
      return Number.isNaN(v) ? 0 : v
    })
  return { debit: sum(0, ...pick('debit')), credit: sum(0, ...pick('credit')) }
}

/** 输入框文本 → 数字（去千分位）；非法返回 NaN */
export function parseAmount(raw: string): number {
  const t = raw.replace(/,/g, '').trim()
  return t === '' ? 0 : Number(t)
}

/** 千分位两位小数；只在失焦后套用，键入过程不插逗号（光标会跳） */
export function formatAmountInput(raw: string): string {
  const t = raw.trim()
  if (t === '') return ''
  const v = parseAmount(t)
  if (Number.isNaN(v)) return raw
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 平台分录组 → 页面分录 */
function fromApi(item: any): AdjEntry {
  const lines: AdjLine[] = (item.line_items || []).map((li: any) => {
    const debit = Number(li.debit_amount) || 0
    const credit = Number(li.credit_amount) || 0
    const side: Side = debit !== 0 || credit === 0 ? 'debit' : 'credit'
    return {
      key: lineKey(),
      side,
      code: li.standard_account_code || '',
      name: li.account_name || '',
      amount: formatAmountInput(String(side === 'debit' ? debit : credit)),
    }
  })
  return {
    groupId: item.entry_group_id,
    no: item.adjustment_no || '',
    type: String(item.adjustment_type || 'aje').toLowerCase() === 'rje' ? 'rje' : 'aje',
    description: item.description || '',
    status: item.review_status || ADJUSTMENT_STATUS.DRAFT,
    rejectionReason: item.rejection_reason || '',
    lines: lines.length ? lines : [emptyLine('debit'), emptyLine('credit')],
  }
}

/** 页面分录 → 平台请求体 line_items（空行不提交） */
export function toLineItems(entry: AdjEntry) {
  return entry.lines
    .filter(l => l.code.trim() || parseAmount(l.amount))
    .map(l => {
      const amount = parseAmount(l.amount) || 0
      return {
        standard_account_code: l.code.trim(),
        account_name: l.name.trim() || undefined,
        debit_amount: l.side === 'debit' ? amount : 0,
        credit_amount: l.side === 'credit' ? amount : 0,
      }
    })
}

/** 保存前校验：返回错误文案，空串表示可保存 */
export function validateEntry(entry: AdjEntry): string {
  const items = toLineItems(entry)
  if (!items.length) return '请至少录入一行借方和一行贷方'
  if (entry.lines.some(l => Number.isNaN(parseAmount(l.amount)))) return '金额只能填数字'
  if (items.some(i => !i.standard_account_code)) return '有金额的行必须填科目编号'
  if (items.some(i => i.debit_amount + i.credit_amount <= 0)) return '每行金额必须大于 0'
  if (!items.some(i => i.debit_amount > 0) || !items.some(i => i.credit_amount > 0)) return '借方和贷方各至少一行'
  const totals = lineTotals(entry)
  if (totals.debit !== totals.credit) {
    return `借贷不平：借方 ${formatAmountInput(totals.debit)}，贷方 ${formatAmountInput(totals.credit)}`
  }
  return ''
}

export function useCitarAdjustments(projectId: () => string, year: () => number | null) {
  const entries = ref<AdjEntry[]>([])
  const loading = ref(false)
  const error = ref('')

  async function load() {
    const y = year()
    if (!y) return
    loading.value = true
    error.value = ''
    try {
      const all: any[] = []
      for (let page = 1; page < 100; page += 1) {
        const res: any = await api.get(P_adj.list(projectId()), {
          params: { year: y, page, page_size: LIST_PAGE_SIZE },
          ...SILENT,
        })
        const items = res?.items || []
        all.push(...items)
        if (items.length < LIST_PAGE_SIZE || all.length >= (res?.total ?? 0)) break
      }
      entries.value = all.map(fromApi)
    } catch (e: any) {
      error.value = e?.response?.data?.detail || e?.message || '读取调整分录失败'
    } finally {
      loading.value = false
    }
  }

  async function save(entry: AdjEntry) {
    const body = { description: entry.description.trim() || undefined, line_items: toLineItems(entry) }
    if (entry.groupId) {
      await api.put(P_adj.detail(projectId(), entry.groupId), body, SILENT)
    } else {
      await api.post(P_adj.create(projectId()), { ...body, adjustment_type: entry.type, year: year() }, SILENT)
    }
  }

  async function remove(entry: AdjEntry) {
    await api.delete(P_adj.detail(projectId(), entry.groupId), SILENT)
  }

  async function review(entry: AdjEntry, status: ReviewTarget, reason?: string) {
    await api.post(P_adj.review(projectId(), entry.groupId), { status, reason }, SILENT)
  }

  async function revoke(entry: AdjEntry) {
    await api.post(P_adj.revokeReview(projectId(), entry.groupId), {}, SILENT)
  }

  return { entries, loading, error, load, save, remove, review, revoke }
}
