/**
 * syncHubFromSummary.pure.spec.ts — 汇总→Hub 投影纯函数 characterization 测试（G5）
 *
 * 背景（2026-07-17 函证第二轮复盘 G5）：syncHubFromSummary 的纯函数
 * accountTypeToHubType / rowToHubStatus / transitionPath / hubStatusToRowPatch
 * codegraph 标 no covering tests——状态判定/逐步推进链/金额差异/科目类型映射
 * 无回归守卫。本文件锁定其**当前行为**（characterization，非规格），为后续
 * alternative* 收敛/重构提供安全网。
 */
import { describe, it, expect } from 'vitest'
import {
  accountTypeToHubType,
  rowToHubStatus,
  transitionPath,
  hubStatusToRowPatch,
} from '../syncHubFromSummary'
import type { ConfirmationRow } from '../../confirmationTypes'

// ─── accountTypeToHubType：科目大类 → Hub confirm_type ──────────────────────

describe('accountTypeToHubType', () => {
  it.each([
    ['银行存款', 'bank'],
    ['货币资金', 'bank'],
    ['其他货币资金', 'bank'],
    ['短期借款', 'loan'],
    ['长期贷款', 'loan'],
    ['融资租赁', 'loan'],
    ['应付账款', 'payable'],
    ['其他应付款', 'payable'],
    ['应收账款', 'receivable'],
    ['其他应收款', 'receivable'],
    ['合同资产', 'receivable'],
  ])('%s → %s', (input, expected) => {
    expect(accountTypeToHubType(input)).toBe(expected)
  })

  it('undefined / 空 → receivable（兜底）', () => {
    expect(accountTypeToHubType(undefined)).toBe('receivable')
    expect(accountTypeToHubType('')).toBe('receivable')
  })

  it('优先级：银行关键词优先于其它（含"应付"也判 bank 若含银行词）', () => {
    // 当前实现按顺序 bank→loan→payable→receivable，先命中银行词即返回
    expect(accountTypeToHubType('银行应付')).toBe('bank')
  })
})

// ─── rowToHubStatus：汇总行 → 期望 Hub 状态 ─────────────────────────────────

function row(partial: Partial<ConfirmationRow>): ConfirmationRow {
  return { ...partial } as ConfirmationRow
}

describe('rowToHubStatus', () => {
  it('match_status=相符 → matched（最高优先）', () => {
    expect(rowToHubStatus(row({ match_status: '相符' }))).toBe('matched')
  })

  it('match_status=不符 → discrepancy', () => {
    expect(rowToHubStatus(row({ match_status: '不符' }))).toBe('discrepancy')
  })

  it('已回函（is_replied）→ returned', () => {
    expect(rowToHubStatus(row({ is_replied: true }))).toBe('returned')
  })

  it('有回函日期（reply_date）→ returned', () => {
    expect(rowToHubStatus(row({ reply_date: '2026-01-10' }))).toBe('returned')
  })

  it('有发函日期（send_date）→ sent', () => {
    expect(rowToHubStatus(row({ send_date: '2026-01-01' }))).toBe('sent')
  })

  it('有函证方式（confirmation_method）→ sent', () => {
    expect(rowToHubStatus(row({ confirmation_method: '积极式' }))).toBe('sent')
  })

  it('match_status=未回函 → sent', () => {
    expect(rowToHubStatus(row({ match_status: '未回函' }))).toBe('sent')
  })

  it('空行 → pending', () => {
    expect(rowToHubStatus(row({}))).toBe('pending')
  })

  it('相符优先于已回函/已发函（同时满足取 matched）', () => {
    expect(
      rowToHubStatus(row({ match_status: '相符', is_replied: true, send_date: '2026-01-01' })),
    ).toBe('matched')
  })

  it('已回函优先于已发函（同时满足取 returned）', () => {
    expect(rowToHubStatus(row({ is_replied: true, send_date: '2026-01-01' }))).toBe('returned')
  })
})

// ─── transitionPath：pending→…→target 的逐步推进路径 ─────────────────────────

describe('transitionPath', () => {
  it('pending → matched：经 sent→returned→matched', () => {
    expect(transitionPath('pending', 'matched')).toEqual(['sent', 'returned', 'matched'])
  })

  it('pending → discrepancy：经 sent→returned→discrepancy', () => {
    expect(transitionPath('pending', 'discrepancy')).toEqual(['sent', 'returned', 'discrepancy'])
  })

  it('pending → returned：经 sent→returned', () => {
    expect(transitionPath('pending', 'returned')).toEqual(['sent', 'returned'])
  })

  it('pending → sent：仅 sent', () => {
    expect(transitionPath('pending', 'sent')).toEqual(['sent'])
  })

  it('sent → matched：仅 returned→matched（不回退到 sent）', () => {
    expect(transitionPath('sent', 'matched')).toEqual(['returned', 'matched'])
  })

  it('returned → matched：仅 matched', () => {
    expect(transitionPath('returned', 'matched')).toEqual(['matched'])
  })

  it('目标不高于当前 → 空路径（不回退）', () => {
    expect(transitionPath('returned', 'sent')).toEqual([])
    expect(transitionPath('matched', 'pending')).toEqual([])
    expect(transitionPath('sent', 'sent')).toEqual([])
  })

  it('未知状态 → 空路径', () => {
    expect(transitionPath('unknown', 'matched')).toEqual([])
    expect(transitionPath('pending', 'unknown' as any)).toEqual([])
  })
})

// ─── hubStatusToRowPatch：Hub 状态 → 汇总行稀疏补丁 ──────────────────────────

describe('hubStatusToRowPatch', () => {
  it('sent → match_status=未回函', () => {
    expect(hubStatusToRowPatch('sent')).toEqual({ match_status: '未回函' })
  })

  it('returned → is_replied=true（match_status 不覆盖）', () => {
    const patch = hubStatusToRowPatch('returned')
    expect(patch.is_replied).toBe(true)
    expect(patch.match_status).toBeUndefined()
  })

  it('matched → is_replied=true + match_status=相符', () => {
    expect(hubStatusToRowPatch('matched')).toMatchObject({ is_replied: true, match_status: '相符' })
  })

  it('discrepancy → is_replied=true + match_status=不符', () => {
    expect(hubStatusToRowPatch('discrepancy')).toMatchObject({ is_replied: true, match_status: '不符' })
  })

  it('金额透传：book/confirmed/diff → amount/reply_amount/difference', () => {
    const patch = hubStatusToRowPatch('matched', {
      book_amount: 1000,
      confirmed_amount: 900,
      diff_amount: 100,
    })
    expect(patch.amount).toBe(1000)
    expect(patch.reply_amount).toBe(900)
    expect(patch.difference).toBe(100)
  })

  it('金额为 null → 不写入对应字段', () => {
    const patch = hubStatusToRowPatch('sent', { book_amount: null, confirmed_amount: null, diff_amount: null })
    expect(patch.amount).toBeUndefined()
    expect(patch.reply_amount).toBeUndefined()
    expect(patch.difference).toBeUndefined()
  })

  it('pending → 空补丁（无字段变更）', () => {
    expect(hubStatusToRowPatch('pending')).toEqual({})
  })
})
