/**
 * B60 适用性矩阵保存 · 自动补缺附件的回执提示（spec procedure-chain-hardening-and-java-contracts R11.4）。
 *
 * 原先只报 generated_wp_codes（复制模板失败也算已生成）；现读后端统一回执 generation_receipt，
 * 失败 / 已裁 / 在回收站写进提示并用警告级别。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const put = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { put: (...a: any[]) => put(...a), get: vi.fn(async () => ({ findings: [] })) },
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import { ElMessage } from 'element-plus'
import { useB60AttachmentMatrix } from '../useB60AttachmentMatrix'

function baseState(extra: Record<string, unknown> = {}) {
  return {
    flags: { integrated_audit: true },
    flag_defs: {},
    missing_attachments: [],
    always_required_missing: [],
    materiality_reference: null,
    plan_version: 1,
    ...extra,
  }
}

async function saveWith(response: Record<string, unknown>) {
  put.mockResolvedValueOnce(response)
  const m = useB60AttachmentMatrix(() => 'p1')
  m.state.value = baseState() as any
  await m.save()
}

beforeEach(() => {
  put.mockReset()
  for (const fn of [ElMessage.success, ElMessage.warning, ElMessage.error]) vi.mocked(fn).mockClear()
})

describe('useB60AttachmentMatrix.save 回执提示', () => {
  it('复制模板失败：警告，写明失败编码与原因（不再算已生成）', async () => {
    await saveWith(baseState({
      generated_wp_codes: ['B60-1'],
      generation_receipt: { created: 1, created_codes: ['B60-1'], failures: [{ wp_code: 'B60A', error: '模板文件被占用' }] },
    }))
    expect(ElMessage.warning).toHaveBeenCalledTimes(1)
    const msg = vi.mocked(ElMessage.warning).mock.calls[0][0] as string
    expect(msg).toContain('适用性矩阵已保存；底稿生成完成，共创建 1 份底稿')
    expect(msg).toContain('1 个编码生成失败：B60A（模板文件被占用）')
  })

  it('全部生成成功：成功提示带回执', async () => {
    await saveWith(baseState({ generation_receipt: { created: 2, created_codes: ['B60', 'B60-1'] } }))
    expect(ElMessage.success).toHaveBeenCalledWith('适用性矩阵已保存；底稿生成完成，共创建 2 份底稿')
  })

  it('没有生成（未开自动生成或无缺附件）：只报已保存', async () => {
    await saveWith(baseState({ generation_receipt: null }))
    expect(ElMessage.success).toHaveBeenCalledWith('适用性矩阵已保存')
    await saveWith(baseState({ generation_receipt: { created: 0 } }))
    expect(vi.mocked(ElMessage.success).mock.calls.at(-1)?.[0]).toBe('适用性矩阵已保存')
  })
})
