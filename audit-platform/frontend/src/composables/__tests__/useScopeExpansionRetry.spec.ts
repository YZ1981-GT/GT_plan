/**
 * spec procedure-trim-generation-delegation-chain 任务 13：委派被拒「被委派人看不到目标循环」时填写理由后带扩权参数重试。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const prompt = vi.hoisted(() => vi.fn())
vi.mock('element-plus', () => ({ ElMessageBox: { prompt } }))

import {
  delegationRejection,
  describeScopeGaps,
  isOutOfScopeRejection,
  promptScopeReason,
  scopeExpansionPromptText,
  withScopeExpansionRetry,
} from '../useScopeExpansionRetry'

function rejected(status: number, detail: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail } } })
}
const OUT_OF_SCOPE = (error = 'lead_delegation_rejected', cycles = ['E']) => rejected(400, {
  error, reason: 'out_of_scope', cycles, message: `被委派人的可见范围不含 ${cycles.join('、')} 循环，填写理由后可扩大其可见范围`,
})

beforeEach(() => {
  prompt.mockReset()
})

describe('delegationRejection', () => {
  it('认底稿主编 / 程序行两种委派拒绝体（含信封里的 data.data.detail）', () => {
    expect(delegationRejection(OUT_OF_SCOPE())).toEqual({
      error: 'lead_delegation_rejected', reason: 'out_of_scope', cycles: ['E'],
      message: '被委派人的可见范围不含 E 循环，填写理由后可扩大其可见范围',
    })
    const wrapped = { response: { status: 400, data: { data: { detail: {
      error: 'row_delegation_rejected', reason: 'out_of_scope', cycles: ['A', 'D'] } } } } }
    expect(delegationRejection(wrapped)?.cycles).toEqual(['A', 'D'])
    expect(isOutOfScopeRejection(OUT_OF_SCOPE('row_delegation_rejected'))).toBe(true)
  })

  it('其他错误不是委派拒绝：字符串 detail、别的 error、无响应', () => {
    expect(delegationRejection(rejected(400, '请求参数错误'))).toBeNull()
    expect(delegationRejection(rejected(409, { error: 'substantive_recycle_unconfirmed', reason: 'out_of_scope' }))).toBeNull()
    expect(delegationRejection(new Error('Network Error'))).toBeNull()
    expect(isOutOfScopeRejection(rejected(409, { error: 'lead_delegation_rejected', reason: 'trimmed' }))).toBe(false)
  })
})

describe('withScopeExpansionRetry', () => {
  it('首次成功：只调一次、不弹框', async () => {
    const attempt = vi.fn().mockResolvedValue({ updated: 1 })
    const out = await withScopeExpansionRetry(attempt, { prompt })
    expect(out).toEqual({ status: 'done', result: { updated: 1 }, expanded: false })
    expect(attempt.mock.calls).toEqual([[{}]])
    expect(prompt).not.toHaveBeenCalled()
  })

  it('out_of_scope ⇒ 要理由 ⇒ 带 expand_scope + scope_reason 重试，结果取第二次', async () => {
    const attempt = vi.fn().mockRejectedValueOnce(OUT_OF_SCOPE()).mockResolvedValueOnce({ updated: 2 })
    const ask = vi.fn().mockResolvedValue('跨循环支援')
    const out = await withScopeExpansionRetry(attempt, { prompt: ask })
    expect(out).toEqual({ status: 'done', result: { updated: 2 }, expanded: true })
    expect(attempt.mock.calls).toEqual([[{}], [{ expand_scope: true, scope_reason: '跨循环支援' }]])
    expect(ask.mock.calls[0][0].cycles).toEqual(['E'])
  })

  it('用户取消理由框 ⇒ cancelled，不重试', async () => {
    const attempt = vi.fn().mockRejectedValueOnce(OUT_OF_SCOPE())
    const out = await withScopeExpansionRetry(attempt, { prompt: vi.fn().mockResolvedValue(null) })
    expect(out).toEqual({ status: 'cancelled' })
    expect(attempt).toHaveBeenCalledTimes(1)
  })

  it('不是 out_of_scope 的拒绝（已裁剪 409）与普通错误原样抛出，不弹框', async () => {
    const trimmed = rejected(409, { error: 'lead_delegation_rejected', reason: 'trimmed', cycles: [] })
    const ask = vi.fn()
    await expect(withScopeExpansionRetry(vi.fn().mockRejectedValue(trimmed), { prompt: ask })).rejects.toBe(trimmed)
    const boom = new Error('Network Error')
    await expect(withScopeExpansionRetry(vi.fn().mockRejectedValue(boom), { prompt: ask })).rejects.toBe(boom)
    expect(ask).not.toHaveBeenCalled()
  })

  it('重试仍失败 ⇒ 抛出第二次的错误（交给调用方提示）', async () => {
    const second = rejected(409, { error: 'delegation_conflict', message: '存在已被他人分配的目标任务' })
    const attempt = vi.fn().mockRejectedValueOnce(OUT_OF_SCOPE()).mockRejectedValueOnce(second)
    await expect(withScopeExpansionRetry(attempt, { prompt: vi.fn().mockResolvedValue('理由') })).rejects.toBe(second)
  })
})

describe('promptScopeReason / 文案', () => {
  it('理由框：正文含缺少的循环，确认返回去空白的理由，空白不通过校验，取消返回 null', async () => {
    prompt.mockResolvedValueOnce({ value: '  跨循环支援  ' })
    const r = delegationRejection(OUT_OF_SCOPE('lead_delegation_rejected', ['A', 'E']))!
    expect(await promptScopeReason(r)).toBe('跨循环支援')
    const [text, title, opts] = prompt.mock.calls[0]
    expect(text).toContain('A、E 循环')
    expect(title).toBe('扩大可见范围')
    expect(opts.inputValidator('   ')).toBe('请填写扩大可见范围的理由')
    expect(opts.inputValidator('支援')).toBe(true)

    prompt.mockRejectedValueOnce('cancel')
    expect(await promptScopeReason(r)).toBeNull()
  })

  it('scopeExpansionPromptText：没有后端说明时用循环拼出说明', () => {
    expect(scopeExpansionPromptText({ error: 'x', reason: 'out_of_scope', message: '', cycles: ['D'] }))
      .toContain('被委派人的可见范围不含D 循环')
  })

  it('describeScopeGaps：执行人 / 复核人缺口，非成员单独说明', () => {
    expect(describeScopeGaps(undefined)).toBe('')
    expect(describeScopeGaps([])).toBe('')
    expect(describeScopeGaps([
      { role: 'assignee', name: '甲', cycles: ['E'], is_member: true },
      { role: 'reviewer', name: '乙', cycles: ['A', 'E'], is_member: true },
    ])).toBe('执行人 甲的可见范围不含 E 循环；复核人 乙的可见范围不含 A、E 循环；应用时需填写理由扩大其可见范围')
    expect(describeScopeGaps([{ role: 'assignee', name: '丙', cycles: ['E'], is_member: false }]))
      .toBe('执行人 丙不是本项目成员，不能委派')
  })
})
