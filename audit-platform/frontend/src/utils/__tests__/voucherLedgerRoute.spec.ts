/**
 * 凭证 ↔ 底稿导航地址（spec voucher-workflow-linkage-lineage-closure R3.5 / R3.7）
 *
 * - 凭证键 + 科目 → 序时账凭证层地址，地址经序时账页 `readFromUrl` 读回同一张凭证（含凭证字为空、主体）；
 * - 凭证键不合法或没有科目 → null；
 * - 返回地址只认本站 `/projects/...`：外站、协议、`//`、反斜杠、控制字符都拒绝；
 * - 序时账 → 底稿：返回地址不安全时不带，挂凭结果打开时带 `from=voucher-attach`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockQuery: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useRoute: () => ({ query: mockQuery }),
}))

import { useLedgerUrlSync } from '@/composables/useLedgerUrlSync'
import {
  FROM_VOUCHER_ATTACH, ledgerRouteOfVoucherKey, parseVoucherKeyParts, returnLabelOf, safeReturnTo, workpaperRouteFromLedger,
} from '@/utils/voucherLedgerRoute'

const KEY = '["2025","重庆医药集团四川物流有限公司","2025-01-20","FY","0012"]'
const KEY_EMPTY_TYPE = '["2025","001","2025-03-05","","0046"]'

beforeEach(() => { Object.keys(mockQuery).forEach(k => delete mockQuery[k]) })

describe('ledgerRouteOfVoucherKey', () => {
  it('凭证层地址经 readFromUrl 读回同一张凭证', () => {
    const route = ledgerRouteOfVoucherKey('p-1', KEY, { accountCode: '1002' }) as any
    expect(route.name).toBe('LedgerPenetration')
    expect(route.params).toEqual({ projectId: 'p-1' })
    expect(route.query.year).toBe('2025')
    Object.assign(mockQuery, route.query)
    expect(useLedgerUrlSync().readFromUrl()).toMatchObject({
      level: 'voucher', account: '1002', voucherNo: '0012', voucherDate: '2025-01-20', voucherType: 'FY',
      voucherCompany: '重庆医药集团四川物流有限公司',
    })
  })

  it('凭证字为空写成空串（读回 "" 而不是「不知道」）', () => {
    const route = ledgerRouteOfVoucherKey('p-1', KEY_EMPTY_TYPE, { accountCode: '1122' }) as any
    expect(route.query.voucherType).toBe('')
    Object.assign(mockQuery, route.query)
    expect(useLedgerUrlSync().readFromUrl().voucherType).toBe('')
  })

  it.each([
    ['没有科目', KEY, undefined],
    ['科目为空白', KEY, '  '],
    ['凭证键不是 JSON', 'FY-0012', '1002'],
    ['凭证键少一段', '["2025","001","2025-01-20","FY"]', '1002'],
    ['日期格式不对', '["2025","001","20250120","FY","0012"]', '1002'],
    ['没有凭证号', '["2025","001","2025-01-20","FY",""]', '1002'],
    ['空', null, '1002'],
  ])('%s → null', (_label, key, account) => {
    expect(ledgerRouteOfVoucherKey('p-1', key as string | null, { accountCode: account as string | undefined })).toBeNull()
  })

  it('parseVoucherKeyParts 只认 5 段字符串', () => {
    expect(parseVoucherKeyParts(KEY)?.[4]).toBe('0012')
    expect(parseVoucherKeyParts('["2025",1,"2025-01-20","FY","0012"]')).toBeNull()
  })
})

describe('safeReturnTo', () => {
  it.each([
    ['/projects/p-1/ledger?level=voucher&voucher=0012', '/projects/p-1/ledger?level=voucher&voucher=0012'],
    [['/projects/p-1/ledger', '/x'], '/projects/p-1/ledger'],
    ['https://evil.example/projects/x', null],
    ['//evil.example/projects/x', null],
    ['/projects//evil.example', null],
    ['/projects/p-1\\..\\login', null],
    ['/login', null],
    ['/projects/p-1/ledger\u0000', null],
    [undefined, null],
    [42, null],
  ])('%j → %j', (raw, want) => {
    expect(safeReturnTo(raw)).toBe(want)
  })
})

describe('returnLabelOf（底稿页「返回」按钮按返回地址说回哪里）', () => {
  it.each([
    ['/projects/p-1/ledger?level=voucher&voucher=0012', '← 返回序时账'],
    ['/projects/p-1/ledger', '← 返回序时账'],
    ['/projects/p-1/workpapers/wp-9/edit?sheet=a', '← 返回上一张底稿'],
    ['/projects/p-1/sampling-enhanced', '← 返回'],
    ['https://evil.example/projects/p-1/ledger', '← 返回'],
    ['//evil.example/projects/p-1/ledger', '← 返回'],
    [undefined, '← 返回'],
  ])('%s → %s', (raw, label) => {
    expect(returnLabelOf(raw)).toBe(label)
  })
})

describe('workpaperRouteFromLedger', () => {
  it('带安全的返回地址与挂凭来源标记', () => {
    expect(workpaperRouteFromLedger('p-1', 'wp-1', { returnTo: '/projects/p-1/ledger?voucher=1', fromAttach: true })).toEqual({
      name: 'WorkpaperEditor', params: { projectId: 'p-1', wpId: 'wp-1' },
      query: { returnTo: '/projects/p-1/ledger?voucher=1', from: FROM_VOUCHER_ATTACH },
    })
  })

  it('返回地址不安全时不带；不是挂凭结果打开时不带来源标记', () => {
    expect(workpaperRouteFromLedger('p-1', 'wp-1', { returnTo: 'https://evil' })).toEqual({
      name: 'WorkpaperEditor', params: { projectId: 'p-1', wpId: 'wp-1' }, query: {},
    })
  })
})
