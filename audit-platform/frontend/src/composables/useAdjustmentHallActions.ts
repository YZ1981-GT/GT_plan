/**
 * 调整大厅的写操作与按状态 / 权限的可用动作（spec adjustment-hall-entry-review-closure 需求 4 / 5.2）。
 *
 * - `rowActions` / `splitEligible`：纯函数，按分录状态 × 权限给出可做的动作（操作列与批量栏共用一套规则）；
 * - `useAdjustmentHallActions`：撤回提交、通过、驳回、撤回复核、删除（可撤销）、批量删除、转错报、
 *   导出汇总 / 模板；统一加载态、确认、中文失败原因，成功后回调刷新；
 * - `reportAdjustmentError`：调用方自管提示的请求都带 `_silent`，合并锁（423）的锁定态事件要在这里自己发。
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { parseApiError } from '@/composables/useApiError'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import { eventBus } from '@/utils/eventBus'
import { confirmConvert, confirmDangerous, confirmDelete } from '@/utils/confirm'
import { operationHistory } from '@/utils/operationHistory'
import * as P from '@/services/apiPaths'
import {
  batchDeleteAdjustments, convertAjeToMisstatement, createAdjustment, deleteAdjustment, reviewAdjustmentsBatch,
  revokeAdjustmentReview, withdrawAdjustmentSubmission, type AdjustmentFlowResult,
} from '@/services/auditPlatformApi'

export interface HallEntry {
  entry_group_id: string
  adjustment_no?: string | null
  adjustment_type?: string
  review_status?: string
  origin?: string | null
  description?: string | null
  line_items?: Array<{ standard_account_code: string; account_name?: string | null; debit_amount: unknown; credit_amount: unknown }>
  converted_to_misstatement_id?: string | null
}

export type HallAction = 'edit' | 'submit' | 'withdraw' | 'approve' | 'reject' | 'revoke' | 'delete' | 'convert'

export interface HallPerms {
  /** 项目可写（未归档 / 有编辑权） */
  writable: boolean
  /** adjustment:edit */
  edit: boolean
  /** adjustment:review */
  review: boolean
}

const isAje = (row: HallEntry) => String(row.adjustment_type || '').toLowerCase() === 'aje'

/** 一笔分录在当前权限下可做的动作。底稿来源的分录不在大厅改明细（以来源底稿为准）。 */
export function rowActions(row: HallEntry, perms: HallPerms): Set<HallAction> {
  const out = new Set<HallAction>()
  if (!perms.writable) return out
  const fromWorkpaper = row.origin === 'workpaper'
  switch (row.review_status) {
    case 'draft':
      if (perms.edit) {
        if (!fromWorkpaper) out.add('edit')
        out.add('submit').add('delete')
      }
      if (perms.review) out.add('approve')
      break
    case 'pending_review':
      if (perms.review) out.add('approve').add('reject')
      if (perms.edit) out.add('withdraw')
      break
    case 'rejected':
      if (perms.edit) {
        if (!fromWorkpaper) out.add('edit')
        out.add('submit').add('delete')
        if (isAje(row) && !row.converted_to_misstatement_id) out.add('convert')
      }
      break
    case 'approved':
      if (perms.review) out.add('revoke')
      break
  }
  return out
}

/**
 * 给只有编号的行（导入回执 / 保存回执）补上摘要，供提交复核弹窗列清单用。
 * 列表里找不到的保持原样（弹窗显示「（无摘要）」），不编造内容。
 */
export function withDescriptions<T extends { entry_group_id: string }>(
  rows: T[],
  entries: Array<{ entry_group_id: string; description?: string | null }>,
): Array<T & { description?: string | null }> {
  const byId = new Map(entries.map((e) => [e.entry_group_id, e.description]))
  return rows.map((r) => (byId.has(r.entry_group_id) ? { ...r, description: byId.get(r.entry_group_id) } : { ...r }))
}

/** 批量动作：选中行按可做 / 不可做拆开（不可做的只计数提示，不发请求）。 */
export function splitEligible(rows: HallEntry[], action: HallAction, perms: HallPerms) {
  const eligible = rows.filter((r) => rowActions(r, perms).has(action))
  return { eligible, skipped: rows.length - eligible.length }
}

const SKIP_HINT: Partial<Record<HallAction, string>> = {
  submit: '只有草稿或已驳回的分录可以提交复核',
  approve: '只有草稿或待复核的分录可以通过',
  reject: '只有待复核的分录可以驳回',
  revoke: '只有已批准的分录可以撤回复核',
  delete: '已提交或已批准的分录不能删除',
}

export function skipMessage(action: HallAction, skipped: number): string {
  return skipped ? `已跳过 ${skipped} 笔（${SKIP_HINT[action] || '状态不符'}）` : ''
}

/** 批量结果 → 一句提示（成功数、逐笔失败原因、通知了谁）。 */
export function flowResultMessage(result: AdjustmentFlowResult, verb: string): { type: 'success' | 'warning' | 'error'; message: string } {
  const ok = result.succeeded?.length || 0
  const failed = result.failed || []
  const parts: string[] = [ok ? `已${verb} ${ok} 笔` : `没有分录${verb}成功`]
  if (failed.length) {
    const head = failed.slice(0, 3).map((f) => `${f.adjustment_no || '分录'}：${f.reason}`).join('；')
    parts.push(`${failed.length} 笔未处理（${head}${failed.length > 3 ? ' 等' : ''}）`)
  }
  const names = [...new Set((result.notified || []).map((n) => n.name).filter(Boolean))]
  if (names.length) parts.push(`已通知 ${names.slice(0, 5).join('、')}${names.length > 5 ? ` 等 ${names.length} 人` : ''}`)
  if (result.warning) parts.push(result.warning)
  return { type: failed.length ? (ok ? 'warning' : 'error') : 'success', message: parts.join('；') }
}

export function showFlowResult(result: AdjustmentFlowResult, verb: string): void {
  const { type, message } = flowResultMessage(result, verb)
  ElMessage({ type, message, duration: type === 'success' ? 4000 : 8000, showClose: true })
}

/** 后端错误 → 中文原因（权限码转成人话）。 */
export function adjustmentErrorMessage(err: unknown): string {
  const parsed = parseApiError(err)
  if (parsed.code === 'PROJECT_PERMISSION_REQUIRED') {
    return parsed.detail?.permission === 'adjustment:review' ? '没有复核调整分录的权限' : '没有编辑调整分录的权限'
  }
  return parsed.message
}

export function reportAdjustmentError(err: unknown, action: string): void {
  const status = (err as { response?: { status?: number } })?.response?.status
  const message = adjustmentErrorMessage(err)
  if (status === 423 && message.includes('合并锁定')) {
    eventBus.emit('consol-lock:detected', {})
    ElMessage.warning({ message: '项目已被合并锁定，无法修改调整分录', duration: 5000, showClose: true })
    return
  }
  ElMessage.error({ message: `${action}失败：${message}`, duration: 6000, showClose: true })
}

function money(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function useAdjustmentHallActions(opts: {
  projectId: Ref<string>
  year: Ref<number | null>
  onChanged: () => unknown
}) {
  /** 进行中的操作键：`动作:分录组 id` 或 `动作:batch` */
  const busy = ref('')
  const isBusy = (action: HallAction, gid = 'batch') => busy.value === `${action}:${gid}`

  async function run<T>(key: string, label: string, fn: () => Promise<T>): Promise<T | undefined> {
    if (busy.value) return undefined
    busy.value = key
    try {
      return await fn()
    } catch (err) {
      reportAdjustmentError(err, label)
      return undefined
    } finally {
      busy.value = ''
    }
  }

  async function afterChange() {
    await opts.onChanged()
  }

  async function withdraw(row: HallEntry): Promise<boolean> {
    const done = await run(`withdraw:${row.entry_group_id}`, '撤回提交', async () => {
      await withdrawAdjustmentSubmission(opts.projectId.value, row.entry_group_id)
      ElMessage.success(`${row.adjustment_no || '分录'} 已撤回提交，回到草稿`)
      return true
    })
    if (done) await afterChange()
    return !!done
  }

  async function review(rows: HallEntry[], status: 'approved' | 'rejected', payload: { reason?: string; reasons?: Record<string, string> } = {}): Promise<boolean> {
    const verb = status === 'approved' ? '通过' : '驳回'
    const key = `${status === 'approved' ? 'approve' : 'reject'}:${rows.length === 1 ? rows[0].entry_group_id : 'batch'}`
    const result = await run(key, verb, () => reviewAdjustmentsBatch(opts.projectId.value, {
      entry_group_ids: rows.map((r) => r.entry_group_id), status, ...payload,
    }))
    if (!result) return false
    showFlowResult(result, verb)
    await afterChange()
    return (result.succeeded?.length || 0) > 0
  }

  async function approve(rows: HallEntry[]): Promise<boolean> {
    if (rows.length > 1) {
      try {
        await confirmDangerous({
          title: '批量通过', confirmText: `通过 ${rows.length} 笔`,
          message: `确认通过选中的 ${rows.length} 笔调整分录？通过后计入试算表审定数，报表与附注随之更新，并通知编制人。`,
        })
      } catch { return false }
    }
    return review(rows, 'approved')
  }

  const reject = (rows: HallEntry[], reason: string, reasons?: Record<string, string>) =>
    review(rows, 'rejected', { reason, reasons })

  /** 撤回复核（已批准 → 草稿）：后端没有批量端点，逐笔调；一笔失败不影响其余。 */
  async function revoke(rows: HallEntry[], reason?: string): Promise<boolean> {
    const result = await run(`revoke:${rows.length === 1 ? rows[0].entry_group_id : 'batch'}`, '撤回复核', async () => {
      const out: AdjustmentFlowResult = { succeeded: [], failed: [], notified: [] }
      for (const row of rows) {
        try {
          const res: any = await revokeAdjustmentReview(opts.projectId.value, row.entry_group_id, { reason: reason || undefined })
          out.succeeded.push({ entry_group_id: row.entry_group_id, adjustment_no: row.adjustment_no })
          out.notified.push(...(res?.notified || []))
        } catch (err) {
          out.failed.push({ entry_group_id: row.entry_group_id, adjustment_no: row.adjustment_no || null, reason: adjustmentErrorMessage(err) })
        }
      }
      return out
    })
    if (!result) return false
    showFlowResult(result, '撤回复核')
    await afterChange()
    return result.succeeded.length > 0
  }

  async function remove(row: HallEntry): Promise<void> {
    const y = opts.year.value
    if (y == null) { ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE); return }
    try {
      await confirmDelete({ name: `分录 ${row.adjustment_no || ''}`.trim(), impact: '草稿与已驳回的分录不计入试算表，删除不影响审定数' })
    } catch { return }
    const cached = JSON.parse(JSON.stringify(row)) as HallEntry
    await run(`delete:${row.entry_group_id}`, '删除', () => operationHistory.execute({
      description: `删除分录 ${row.adjustment_no || ''}`.trim(),
      execute: async () => {
        await deleteAdjustment(opts.projectId.value, row.entry_group_id)
        await afterChange()
      },
      // 撤销 = 按原编号重建为草稿（原分录是软删，编号已空出）
      undo: async () => {
        await createAdjustment(opts.projectId.value, {
          adjustment_type: String(cached.adjustment_type || 'aje').toLowerCase(),
          year: y,
          adjustment_no: cached.adjustment_no || undefined,
          description: cached.description || '',
          line_items: (cached.line_items || []).map((li) => ({
            standard_account_code: li.standard_account_code,
            account_name: li.account_name || undefined,
            debit_amount: money(li.debit_amount),
            credit_amount: money(li.credit_amount),
          })),
        })
        await afterChange()
      },
    }))
  }

  async function removeMany(rows: HallEntry[]): Promise<void> {
    try {
      await confirmDelete({ name: `选中的 ${rows.length} 笔分录`, impact: '草稿与已驳回的分录不计入试算表，删除不影响审定数' })
    } catch { return }
    const res = await run('delete:batch', '批量删除', () => batchDeleteAdjustments(opts.projectId.value, rows.map((r) => r.entry_group_id)))
    if (!res) return
    const failed = res.failed || []
    const msg = `已删除 ${res.succeeded?.length || 0} 笔` + (failed.length ? `；${failed.length} 笔未删除（${failed[0].error}）` : '')
    ElMessage({ type: failed.length ? 'warning' : 'success', message: msg, showClose: true, duration: failed.length ? 8000 : 4000 })
    await afterChange()
  }

  /** 已驳回的 AJE 转为未更正错报；已转过的提示跳转查看。返回需跳转错报汇总表时为 true。 */
  async function convert(row: HallEntry): Promise<boolean> {
    try { await confirmConvert(`分录 ${row.adjustment_no || ''}`.trim(), '未更正错报') } catch { return false }
    busy.value = `convert:${row.entry_group_id}`
    try {
      const res = await convertAjeToMisstatement(opts.projectId.value, row.entry_group_id)
      ElMessage.success(`已转为未更正错报（净额 ${res.net_amount}）`)
      await afterChange()
      return await askJump('是否立即查看《未更正错报汇总表》？', '转换成功')
    } catch (err) {
      if (parseApiError(err).code === 'ALREADY_CONVERTED') return askJump('该分录已转为未更正错报，是否跳转查看？', '已转换')
      reportAdjustmentError(err, '转为错报')
      return false
    } finally {
      busy.value = ''
    }
  }

  async function askJump(message: string, title: string): Promise<boolean> {
    try {
      await confirmDangerous({ title, message, confirmText: '去查看', cancelText: '稍后' })
      return true
    } catch { return false }
  }

  async function download(url: string, filename: string, label: string): Promise<void> {
    try {
      const { downloadFileAsBlob } = await import('@/services/commonApi')
      await downloadFileAsBlob(url, filename)
    } catch (err) {
      reportAdjustmentError(err, label)
    }
  }

  /** 导出调整汇总（全部分录 + 复核状态 / 编制人列） */
  async function exportSummary(): Promise<void> {
    const y = opts.year.value
    if (y == null) { ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE); return }
    await download(`${P.adjustments.exportSummary(opts.projectId.value)}?year=${y}&format=excel&include_collaboration=true`,
      `审计调整汇总_${y}.xlsx`, '导出汇总')
  }

  /** 导出导入模板；所选版本与项目版本不一致时先提醒。 */
  async function exportTemplate(templateType: 'soe' | 'listed', currentType: string): Promise<void> {
    const y = opts.year.value
    if (y == null) { ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE); return }
    const label = templateType === 'soe' ? '国企版' : '上市版'
    if (currentType && currentType !== templateType) {
      const projLabel = currentType === 'soe' ? '国企版' : '上市版'
      try {
        await confirmDangerous({
          title: '版本与项目不匹配', confirmText: `仍导出${label}`, cancelText: '取消',
          message: `当前项目是【${projLabel}】，所选是【${label}】模板，模板里的报表项目按版本生成，建议导出${projLabel}。是否仍导出${label}？`,
        })
      } catch { return }
    }
    await download(`${P.adjustments.exportTemplate(opts.projectId.value)}?year=${y}&template_type=${templateType}`,
      `调整分录导入模板_${label}_${y}.xlsx`, '导出模板')
  }

  return { busy, isBusy, withdraw, approve, reject, revoke, remove, removeMany, convert, exportSummary, exportTemplate }
}
