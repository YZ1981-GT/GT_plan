/**
 * 凭证身份前后端一致性（前端侧）—— spec voucher-identity-writeback-and-audit-phase 任务 2 / 需求 1.4
 *
 * 读后端测试同用的样例 backend/tests/fixtures/voucher_identity_vectors.json，断言 voucherIdentity.ts 的输出
 * 与样例逐字相同；后端 backend/tests/test_voucher_identity.py 对同一份样例断言 voucher_identity.py 逐字相同。
 * 任一侧改口径，另一侧必红。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import Decimal from 'decimal.js'
import { afterEach, describe, expect, it } from 'vitest'

import {
  amountString,
  describeLine,
  exclusionCaveats,
  lineFingerprint,
  normText,
  sideOf,
  signedAmount,
  voucherKeyAmbiguityOf,
  voucherKeyParts,
  voucherKeyString,
  voucherLabel,
  type VoucherSide,
} from '../voucherIdentity'

// __tests__ → utils → src → frontend → audit-platform → 仓库根：向上 5 级
const here = path.dirname(fileURLToPath(import.meta.url))
const VECTORS_PATH = path.resolve(here, '../../../../../backend/tests/fixtures/voucher_identity_vectors.json')

interface LineCase {
  name: string
  input: Record<string, unknown> & { occ: number; debit_amount: unknown; credit_amount: unknown; account_code: unknown }
  expect: { vk: string; side: VoucherSide; amount: string; lfp: string }
}
const VECTORS = JSON.parse(readFileSync(VECTORS_PATH, 'utf-8')) as { lines: LineCase[] }

describe('voucherIdentity 与后端同一份样例逐字相同', () => {
  it('样例非空', () => {
    expect(VECTORS.lines.length).toBeGreaterThanOrEqual(10)
  })

  for (const c of VECTORS.lines) {
    it(c.name, () => {
      const { input, expect: exp } = c
      expect(voucherKeyString(input)).toBe(exp.vk)
      expect(sideOf(input.debit_amount, input.credit_amount)).toBe(exp.side)
      expect(amountString(signedAmount(input.debit_amount, input.credit_amount))).toBe(exp.amount)
      const line = describeLine(input)
      expect([JSON.stringify(line.vk), line.side, line.amount]).toEqual([exp.vk, exp.side, exp.amount])
      expect(lineFingerprint(voucherKeyParts(input), input.account_code, line.side, line.amount, input.occ)).toBe(exp.lfp)
      expect(lineFingerprint(exp.vk, input.account_code, exp.side, exp.amount, input.occ)).toBe(exp.lfp)
    })
  }
})

describe('voucherIdentity 边界', () => {
  const saved = Decimal.rounding
  afterEach(() => {
    Decimal.set({ rounding: saved })
  })

  it('舍入不受全局 Decimal.set 影响（ledgerDisplay / useDecimalCalc 会把全局改成银行家舍入）', () => {
    Decimal.set({ rounding: Decimal.ROUND_HALF_EVEN })
    expect(amountString('-0.005')).toBe('-0.01')
    expect(amountString('0.125')).toBe('0.13')
  })

  it('不用浮点：2.675 → 2.68，-0.004 → 0.00', () => {
    expect(amountString(2.675)).toBe('2.68')
    expect(amountString('-0.004')).toBe('0.00')
    expect(amountString(null)).toBe('0.00')
    expect(amountString('')).toBe('0.00')
  })

  it('非法金额报错', () => {
    expect(() => amountString('abc')).toThrow('金额无法解析')
  })

  it('驼峰行结构与下划线行结构得到同一个键，行上没有年度用参数补', () => {
    const snake = { company_code: '001', voucher_date: '2025-01-07', voucher_type: 'ZZ', voucher_no: '0003' }
    const camel = { companyCode: '001', voucherDate: '2025-01-07', voucherType: 'ZZ', voucherNo: '0003' }
    expect(voucherKeyString(camel, 2025)).toBe(voucherKeyString(snake, '2025'))
    expect(voucherKeyString(snake, 2025)).toBe('["2025","001","2025-01-07","ZZ","0003"]')
    expect(voucherKeyString({ ...snake, year: 2024 }, 2025)).toBe('["2024","001","2025-01-07","ZZ","0003"]')
  })

  it('空白口径与 Python str.strip 相同', () => {
    expect(normText('\u3000转\u001f')).toBe('转')
    expect(normText('\x1c0003\x85')).toBe('0003')
    expect(normText('\ufeff001')).toBe('\ufeff001')
    expect(normText(null)).toBe('')
  })

  it('日期对象按本地日期取年月日', () => {
    expect(voucherKeyParts({ voucherDate: new Date(2025, 0, 7, 23, 30), voucherNo: '1' }, 2025)[2]).toBe('2025-01-07')
  })
})

describe('凭证穿透 409 候选与凭证称呼', () => {
  const body = {
    error_code: 'VOUCHER_KEY_AMBIGUOUS',
    message: '该凭证号对应 2 张凭证',
    candidates: [{ voucher_key: 'k1', voucher_type: 'FY' }, { voucher_key: 'k2', voucher_type: 'ZZ' }],
    truncated: false,
  }

  it('从业务信封的 message 或拦截器补的 detail 取候选', () => {
    for (const data of [{ code: 409, message: body }, { code: 409, message: body, detail: body }]) {
      const got = voucherKeyAmbiguityOf({ response: { status: 409, data } })
      expect(got?.candidates.map(c => c.voucher_type)).toEqual(['FY', 'ZZ'])
      expect(got?.message).toBe('该凭证号对应 2 张凭证')
      expect(got?.truncated).toBe(false)
    }
  })

  it('不是凭证键歧义的错误返回 null', () => {
    expect(voucherKeyAmbiguityOf({ response: { status: 409, data: { message: { error_code: 'APPROVED_LOCKED' } } } })).toBeNull()
    expect(voucherKeyAmbiguityOf({ response: { status: 500, data: { message: body } } })).toBeNull()
    expect(voucherKeyAmbiguityOf({ response: { status: 409, data: { message: '冲突' } } })).toBeNull()
    expect(voucherKeyAmbiguityOf(new Error('网络错误'))).toBeNull()
    expect(voucherKeyAmbiguityOf(null)).toBeNull()
  })

  it('有凭证字写「字-号」，没有写号', () => {
    expect(voucherLabel('FY', '0003')).toBe('FY-0003')
    expect(voucherLabel('', '0003')).toBe('0003')
    expect(voucherLabel(null, ' 7 ')).toBe('7')
  })
})

describe('已抽排除的提示（后端 stats）', () => {
  it('旧记录按凭证号排除与找不到的已抽分录各给一条', () => {
    const msgs = exclusionCaveats({ legacy_exclusion: true, unresolved_excluded_lines: 3 })
    expect(msgs).toHaveLength(2)
    expect(msgs[0]).toContain('按凭证号整张排除')
    expect(msgs[1]).toContain('有 3 笔已抽分录')
  })

  it('没有这两种情形、字段缺失或空 stats 都不提示', () => {
    expect(exclusionCaveats({ legacy_exclusion: false, unresolved_excluded_lines: 0 })).toEqual([])
    expect(exclusionCaveats({})).toEqual([])
    expect(exclusionCaveats(null)).toEqual([])
    expect(exclusionCaveats({ legacy_exclusion: 'true' })).toEqual([]) // 只认布尔 true
  })
})
