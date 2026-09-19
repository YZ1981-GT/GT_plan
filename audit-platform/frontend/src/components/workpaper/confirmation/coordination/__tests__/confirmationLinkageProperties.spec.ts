/**
 * confirmationLinkageProperties.spec.ts — 联动属性测试（fast-check）
 *
 * Property 5  Sync_To_Center 幂等：同批行重复同步不增记录（按 hubId 去重语义）
 * Property 8  Reply_Backflow 手工优先：已有手工回函金额时金额补丁为 undefined（不覆盖）
 * Property 10 Unreplied_Pull 去重：重复带入同一被函证单位只保留一行
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { dedupeSummaryRows } from '../importE0ListsToSummary'
import { hubStatusToRowPatch } from '../syncHubFromSummary'
import type { ConfirmationRow } from '../../confirmationTypes'

describe('Unreplied_Pull 去重 (Property 10)', () => {
  it('去重后无重复 (entity_name, account_type)', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            entity_name: fc.constantFrom('工行', '中行', '建行', 'A公司', 'B公司'),
            account_type: fc.constantFrom('银行存款', '短期借款', '应付票据'),
          }),
        ),
        (candidates) => {
          const out = dedupeSummaryRows(candidates, [])
          const keys = out.map((r) => `${r.entity_name}||${r.account_type}`)
          expect(new Set(keys).size).toBe(keys.length) // 无重复
        },
      ),
    )
  })

  it('相对已存在行去重：结果不含已存在 key', () => {
    fc.assert(
      fc.property(
        fc.array(fc.record({ entity_name: fc.constantFrom('工行', '中行'), account_type: fc.constant('银行存款') })),
        fc.array(fc.record({ entity_name: fc.constantFrom('工行', '建行'), account_type: fc.constant('银行存款') })),
        (existingRaw, candidates) => {
          const existing = existingRaw.map((r, i) => ({ ...r, _row_id: String(i) })) as ConfirmationRow[]
          const out = dedupeSummaryRows(candidates, existing)
          const existingKeys = new Set(existing.map((r) => `${r.entity_name}||${r.account_type}`))
          for (const r of out) {
            expect(existingKeys.has(`${r.entity_name}||${r.account_type}`)).toBe(false)
          }
        },
      ),
    )
  })

  it('幂等：对同一候选集去重两次结果一致 (Property 5 幂等语义)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.record({ entity_name: fc.constantFrom('工行', '中行', '建行'), account_type: fc.constant('银行存款') })),
        (candidates) => {
          const once = dedupeSummaryRows(candidates, [])
          // 把首次结果作为 existing 再带入同一候选集 → 应无新增（幂等）
          const twice = dedupeSummaryRows(candidates, once as ConfirmationRow[])
          expect(twice).toHaveLength(0)
        },
      ),
    )
  })
})

describe('Reply_Backflow 手工优先 (Property 8)', () => {
  it('金额为 null/undefined 时补丁不含金额字段（手工值不被覆盖）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('returned', 'matched', 'discrepancy'),
        (status) => {
          // 模拟"手工优先"分支：hasManualReply → 不传 amounts
          const patch = hubStatusToRowPatch(status, undefined)
          expect(patch.reply_amount).toBeUndefined()
          expect(patch.amount).toBeUndefined()
          expect(patch.difference).toBeUndefined()
          // 但状态标记仍应写入
          expect(patch.is_replied).toBe(true)
        },
      ),
    )
  })

  it('无手工值时金额从台账透传', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(0.01), max: 1e6, noNaN: true }),
        (amt) => {
          const patch = hubStatusToRowPatch('matched', { confirmed_amount: amt })
          expect(patch.reply_amount).toBe(amt)
        },
      ),
    )
  })
})
