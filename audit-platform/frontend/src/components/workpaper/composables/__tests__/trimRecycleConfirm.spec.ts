/**
 * 粗裁保存前确认已生成底稿的去向（spec procedure-trim-generation-delegation-chain 需求 3.2）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ confirm: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: mocks.confirm } }))

import {
  confirmTrimRecycle,
  describeRecycleResult,
  recycleSummaryLines,
  trimApplyConflictMessage,
} from '../trimRecycleConfirm'

beforeEach(() => {
  mocks.confirm.mockReset()
})

const PREVIEW = {
  recycle_preview: {
    to_recycle: ['H3', 'H3-1', 'H3A'],
    substantive: [{ wp_code: 'H3-1', wp_name: '投资性房地产审定表', substantive_reasons: ['已保存过 3 次', '人工填写 1 项'] }],
    to_restore: ['M4'],
  },
}

describe('recycleSummaryLines', () => {
  it('列出移入回收站的编码、有编制内容的底稿与原因、从回收站恢复的编码', () => {
    expect(recycleSummaryLines(PREVIEW.recycle_preview)).toEqual([
      '3 张已生成的底稿将移入回收站（可从回收站恢复）：H3、H3-1、H3A',
      '其中 1 张已有编制内容：',
      '· H3-1 投资性房地产审定表（已保存过 3 次、人工填写 1 项）',
      '1 张底稿将从回收站恢复：M4',
    ])
    expect(recycleSummaryLines(undefined)).toEqual([])
    const many = recycleSummaryLines({ to_recycle: Array.from({ length: 12 }, (_, i) => `C${i}`) })
    expect(many[0]).toMatch(/12 张.*C9 等$/)
  })
})

describe('confirmTrimRecycle', () => {
  it('没有要移入回收站的底稿 ⇒ 不弹框', async () => {
    expect(await confirmTrimRecycle({ recycle_preview: { to_recycle: [], to_restore: ['M4'] } })).toBe('none')
    expect(await confirmTrimRecycle({})).toBe('none')
    expect(mocks.confirm).not.toHaveBeenCalled()
  })

  it('有要移入的 ⇒ 弹框；确认返回 confirmed，取消返回 cancel', async () => {
    mocks.confirm.mockResolvedValueOnce('confirm')
    expect(await confirmTrimRecycle(PREVIEW)).toBe('confirmed')
    const [, title, opts] = mocks.confirm.mock.calls[0]
    expect(title).toBe('已生成的底稿将移入回收站')
    expect(opts).toMatchObject({ type: 'warning', confirmButtonText: '确认保存' })
    mocks.confirm.mockRejectedValueOnce('cancel')
    expect(await confirmTrimRecycle(PREVIEW)).toBe('cancel')
  })

  it('onlySubstantive：没有编制内容的不问（批量路径）', async () => {
    const plain = { recycle_preview: { to_recycle: ['H3'], substantive: [] } }
    expect(await confirmTrimRecycle(plain, { onlySubstantive: true })).toBe('none')
    expect(mocks.confirm).not.toHaveBeenCalled()
    mocks.confirm.mockResolvedValueOnce('confirm')
    expect(await confirmTrimRecycle(PREVIEW, { onlySubstantive: true })).toBe('confirmed')
  })
})

describe('结果与冲突提示', () => {
  it('describeRecycleResult', () => {
    expect(describeRecycleResult({ recycled_codes: ['H3', 'H3-1'], restored_codes: ['M4'] }))
      .toBe('；2 张已生成底稿已移入回收站；1 张底稿已从回收站恢复')
    expect(describeRecycleResult({ applied: 1 } as any)).toBe('')
  })

  it('trimApplyConflictMessage 只认「有编制内容未确认」', () => {
    const e = { response: { status: 409, data: { detail: { error: 'substantive_recycle_unconfirmed', message: '1 张底稿已有编制内容' } } } }
    expect(trimApplyConflictMessage(e)).toBe('1 张底稿已有编制内容')
    expect(trimApplyConflictMessage({ response: { status: 409, data: { detail: '目标任务版本已变化，请重新预览' } } })).toBeNull()
  })
})
