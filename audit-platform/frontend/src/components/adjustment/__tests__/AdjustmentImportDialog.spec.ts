/**
 * Excel 导入弹窗（spec adjustment-hall-entry-review-closure 需求 2.3~2.5）：选文件 → 预检（逐笔结果，不写库）→ 导入 →
 * 结果停留在弹窗，可一键把本次导入的分录交给提交复核。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({ previewAdjustmentImport: vi.fn(), importAdjustmentsFile: vi.fn() }))
vi.mock('@/services/auditPlatformApi', () => api)

import AdjustmentImportDialog from '../AdjustmentImportDialog.vue'

const mounted: VueWrapper[] = []
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.trim() === text)!

const PREVIEW = {
  mode: 'append', warnings: ['第 9 行借贷金额均为 0，已忽略'], structure_errors: [], example_skipped: 0,
  summary: { total: 2, ok: 1, error: 1, skip: 0, replace: 0 },
  groups: [
    { key: 'A-1', adjustment_no: 'A-1', adjustment_type: 'AJE', description: '补提坏账', rows: [5, 6], action: 'create', skip_reason: null,
      errors: [], ok: true, total_debit: '100.00', total_credit: '100.00',
      lines: [{ label: '审计调整 第 5 行', account_code: '6702', account_name: '信用减值损失', debit: '100.00', credit: '0.00' }] },
    { key: '__auto_1', adjustment_no: '(无编号)', adjustment_type: 'AJE', description: '', rows: [7], action: 'create', skip_reason: null,
      errors: ['审计调整 第 7 行科目「不存在的科目」在项目科目库中找不到'], ok: false, total_debit: '5.00', total_credit: '0.00',
      lines: [{ label: '审计调整 第 7 行', account_code: '', account_name: '不存在的科目', debit: '5.00', credit: '0.00' }] },
  ],
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  document.body.innerHTML = ''
})

async function openWithFile() {
  const w = mount(AdjustmentImportDialog, {
    props: { projectId: 'p1', year: 2025, templateType: 'soe' },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  mounted.push(w)
  ;(w.vm as any).open()
  await flushPromises()
  const file = new File(['x'], '调整分录.xlsx')
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!
  Object.defineProperty(input, 'files', { value: [file] })
  input.dispatchEvent(new Event('change'))
  await flushPromises()
  return { w, file }
}

describe('AdjustmentImportDialog', () => {
  it('模板按钮回传版本；预检逐笔列出结果与原因', async () => {
    api.previewAdjustmentImport.mockResolvedValue(PREVIEW)
    const { w, file } = await openWithFile()
    button('📘 国企版模板（当前项目）').click()
    expect(w.emitted('download-template')?.[0]).toEqual(['soe'])
    button('预检').click()
    await flushPromises()
    expect(api.previewAdjustmentImport).toHaveBeenCalledWith('p1', 2025, 'append', file)
    const text = document.body.textContent || ''
    expect(text).toContain('共 2 笔：1 笔可导入')
    expect(text).toContain('在项目科目库中找不到')
    expect(text).toContain('第 9 行借贷金额均为 0，已忽略')
    expect(button('导入 1 笔').disabled).toBe(false)
  })

  it('导入后结果留在弹窗，回传 imported，并可把本次导入的分录交给提交复核', async () => {
    api.previewAdjustmentImport.mockResolvedValue(PREVIEW)
    const result = {
      imported: 1, skipped: 0, failed: 1, message: '成功导入 1 笔，1 笔失败', warnings: [],
      failed_rows: [{ row: 7, adj_no: '(无编号)', rows_in_group: [7], error: '科目找不到' }],
      created: [{ key: 'A-1', entry_group_id: 'g1', adjustment_no: 'AJE-001' }],
    }
    api.importAdjustmentsFile.mockResolvedValue(result)
    const { w } = await openWithFile()
    button('预检').click()
    await flushPromises()
    button('导入 1 笔').click()
    await flushPromises()
    expect(w.emitted('imported')?.[0]).toEqual([result])
    expect(document.body.textContent).toContain('成功导入 1 笔，1 笔失败')
    expect(document.body.textContent).toContain('(无编号)（第 7 行）：科目找不到')
    button('提交复核（本次 1 笔）').click()
    await flushPromises()
    expect(w.emitted('submit-review')?.[0]).toEqual([[{ entry_group_id: 'g1', adjustment_no: 'AJE-001' }]])
  })
})
