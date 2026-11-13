/**
 * 凭证检查行结论判定（spec voucher-workflow-linkage-lineage-closure design §8.2）
 *
 * - 前端取值表与后端 `backend/data/voucher_check_verdict_vocab.json` 逐字段、逐值相同（含布尔值的类型）；
 * - 判定规则与后端 `row_verdict` 相同：任一异常即异常、否则任一正常即正常、否则未判定；`conclusion` 不认；
 *   字符串 "true" 不等于布尔 true。
 */
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { rowVerdict, VOUCHER_VERDICT_VOCAB } from '@/utils/voucherVerdict'

function findRepoRoot(): string {
  // 哨兵是具体文件（目录名在多层同时存在时会提前停下）
  const sentinel = join('backend', 'data', 'voucher_check_verdict_vocab.json')
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i++) {
    try {
      readFileSync(join(dir, sentinel))
      return dir
    } catch {
      const parent = resolve(dir, '..')
      if (parent === dir) break
      dir = parent
    }
  }
  throw new Error('未找到仓库根（哨兵 backend/data/voucher_check_verdict_vocab.json）')
}

const BACKEND = JSON.parse(readFileSync(join(findRepoRoot(), 'backend', 'data', 'voucher_check_verdict_vocab.json'), 'utf-8'))
  .fields as Record<string, { abnormal: unknown[]; normal: unknown[] }>

describe('取值表与后端逐值相同', () => {
  it('字段集合相同且非空', () => {
    expect(Object.keys(BACKEND).length).toBeGreaterThan(0)
    expect(Object.keys(VOUCHER_VERDICT_VOCAB).sort()).toEqual(Object.keys(BACKEND).sort())
  })

  it.each(Object.keys(VOUCHER_VERDICT_VOCAB))('%s 的异常 / 正常取值（含类型）相同', (field) => {
    const typed = (vals: readonly unknown[]) => vals.map(v => `${typeof v}:${String(v)}`)
    expect(typed(VOUCHER_VERDICT_VOCAB[field].abnormal)).toEqual(typed(BACKEND[field].abnormal))
    expect(typed(VOUCHER_VERDICT_VOCAB[field].normal)).toEqual(typed(BACKEND[field].normal))
  })
})

describe('rowVerdict', () => {
  it.each([
    [{ isAbnormal: '是' }, 'abnormal'],
    [{ isAbnormal: ' 否 ' }, 'normal'],
    [{ abnormal: true }, 'abnormal'],
    [{ abnormal: false }, 'normal'],
    [{ checkResult: 'ERR' }, 'abnormal'],
    [{ checkResult: '√' }, 'normal'],
    [{ auditConclusion: '差异可接受' }, 'normal'],
    [{ auditConclusion: '存疑' }, 'unknown'],
    [{ isConsistent: '是' }, 'normal'],
    [{ isConsistent: '否' }, 'abnormal'],
    [{ conclusion: '异常' }, 'unknown'],
    [{ isAbnormal: 'true' }, 'unknown'],
    [{ checkResult: 'OK', isAbnormal: '是' }, 'abnormal'],
    [{}, 'unknown'],
    [null, 'unknown'],
  ])('%j → %s', (row, want) => {
    expect(rowVerdict(row)).toBe(want)
  })
})
