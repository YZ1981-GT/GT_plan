import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ default: { get }, api: { get } }))

import { downloadLedgerWindow, fetchLedgerWindow, ledgerWindowQueryKey } from '@/services/ledgerWindowApi'

beforeEach(() => get.mockReset())

describe('ledgerWindowApi', () => {
  it('普通窗口映射 snake_case 参数并保留调用方 signal，关闭旧 GET 去重', async () => {
    const controller = new AbortController()
    get.mockResolvedValue({ entries: [] })
    await fetchLedgerWindow({
      kind: 'ledger', projectId: 'p1', year: 2025, accountCode: '1002*',
      dateFrom: '2025-01-01', dateTo: '2025-12-31', keyword: '利息', amountDir: 'credit',
      cursor: 'signed', limit: 200,
    }, controller.signal)
    expect(get).toHaveBeenCalledWith('/api/projects/p1/ledger/window/1002*', {
      params: {
        year: 2025, limit: 200, amount_dir: 'credit', date_from: '2025-01-01',
        date_to: '2025-12-31', keyword: '利息', cursor: 'signed',
      },
      signal: controller.signal, _dedupe: false, _silent: true,
    })
  })

  it('辅助窗口必须把类型/编码发给专用端点', async () => {
    get.mockResolvedValue({ entries: [] })
    await fetchLedgerWindow({ kind: 'aux_ledger', projectId: 'p1', year: 2025, accountCode: '1002',
      auxType: '金融机构', auxCode: 'B01' })
    expect(get.mock.calls[0][0]).toBe('/api/projects/p1/ledger/aux-window/1002')
    expect(get.mock.calls[0][1].params).toMatchObject({ aux_type: '金融机构', aux_code: 'B01' })
  })

  it('完整导出不发送 cursor/limit，返回 Blob 且不走浏览器当前窗口', async () => {
    const blob = new Blob(['xlsx'])
    get.mockResolvedValue(blob)
    const result = await downloadLedgerWindow({
      kind: 'aux_ledger', projectId: 'p1', year: 2025, accountCode: '1002',
      auxType: '客户', auxCode: 'C1', cursor: 'old-page', limit: 500,
    })
    expect(result).toBe(blob)
    expect(get.mock.calls[0][0]).toBe('/api/projects/p1/ledger/aux-window-export/1002')
    expect(get.mock.calls[0][1]).toMatchObject({ responseType: 'blob', _dedupe: false, _silent: true })
    expect(get.mock.calls[0][1].params).not.toHaveProperty('cursor')
    expect(get.mock.calls[0][1].params).not.toHaveProperty('limit')
  })

  it('稳定查询键忽略 cursor，但区分数据口径', () => {
    const base = { kind: 'ledger' as const, projectId: 'p1', year: 2025, accountCode: '1002', limit: 200 }
    expect(ledgerWindowQueryKey({ ...base, cursor: 'a' })).toBe(ledgerWindowQueryKey({ ...base, cursor: 'b' }))
    expect(ledgerWindowQueryKey(base)).not.toBe(ledgerWindowQueryKey({ ...base, accountCode: '1003' }))
  })
})
