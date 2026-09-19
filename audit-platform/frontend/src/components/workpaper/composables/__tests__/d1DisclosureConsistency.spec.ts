/**
 * D1 披露勾稽引擎 + 派生列推导测试
 *
 * 重点锁死两个**浏览器实测暴露过**的缺陷（回归即红）：
 * - 比例(%) 跨行相加漂移（实测「按组合计提坏账准备」显示 162.50%，应 100.00%）
 * - 预期信用损失率硬编码 0（附注里显示 `-`）
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ R5 / R10
 */
import { describe, expect, it } from 'vitest'
import { deriveClassRow, deriveClassRows, ratioOf } from '../useD1FormulaEngine'
import { runD1DisclosureChecks, type D1ConsistencyInput } from '../d1DisclosureConsistency'

// ─── R5 派生列推导 ───────────────────────────────────────────────────────────

describe('deriveClassRows — 派生列读时推导（F4-11 / F4-12 / F4-25）', () => {
  const raw = [
    { balance: 300000, provision: 9000, ratio: 999, lossRate: 999, bookValue: 999 },
    { balance: 500000, provision: 4000, ratio: 999, lossRate: 999, bookValue: 999 },
  ]

  it('比例分母统一用传入的合计，与录入顺序无关', () => {
    const total = 800000
    const out = deriveClassRows(raw, total)
    expect(out[0].ratio).toBeCloseTo(300000 / 800000, 10)
    expect(out[1].ratio).toBeCloseTo(500000 / 800000, 10)
    // 🔴 各行比例之和 = 1（旧实现把不同分母的比率相加 → 1.625 → 162.50%）
    expect(out.reduce((s, r) => s + r.ratio, 0)).toBeCloseTo(1, 10)
  })

  it('覆盖持久化的过期派生值（导入路径写进来的旧值同样被推导覆盖）', () => {
    const out = deriveClassRows(raw, 800000)
    expect(out.every(r => r.ratio !== 999 && r.lossRate !== 999 && r.bookValue !== 999)).toBe(true)
  })

  it('预期信用损失率 = 坏账准备 ÷ 账面余额（F4-12）', () => {
    const out = deriveClassRow(raw[0], 800000)
    expect(out.lossRate).toBeCloseTo(9000 / 300000, 10)
  })

  it('账面价值 = 账面余额 − 坏账准备（F4-11）', () => {
    expect(deriveClassRow(raw[1], 800000).bookValue).toBe(500000 - 4000)
  })

  it('分母为 0 时返回 0，不产生 NaN / Infinity', () => {
    const out = deriveClassRow({ balance: 0, provision: 0, ratio: 0, lossRate: 0, bookValue: 0 }, 0)
    expect(out.ratio).toBe(0)
    expect(out.lossRate).toBe(0)
    expect(Number.isFinite(out.bookValue)).toBe(true)
  })

  it('ratioOf 聚合行按聚合后金额算（禁止成员比率相加）', () => {
    const comboBalance = 300000 + 500000
    const comboProvision = 9000 + 4000
    expect(ratioOf(comboBalance, 800000)).toBe(1)
    expect(ratioOf(comboProvision, comboBalance)).toBeCloseTo(13000 / 800000, 10)
    expect(ratioOf(1, 0)).toBe(0)
  })
})

// ─── R10 勾稽引擎 ────────────────────────────────────────────────────────────

function baseInput(over: Partial<D1ConsistencyInput> = {}): D1ConsistencyInput {
  const zeroSummary = {
    category: '', endBalance: 0, endProvision: 0, endBookValue: 0,
    priorBalance: 0, priorProvision: 0, priorBookValue: 0,
  }
  const zeroClass = { label: '合计', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 }
  const zeroMv = {
    priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0,
  }
  return {
    variant: 'soe',
    summaryRows: [], summaryTotal: { ...zeroSummary, category: '合计' },
    classEndRows: [], classPriorRows: [],
    classEndTotal: { ...zeroClass }, classPriorTotal: { ...zeroClass },
    individualEndRows: [], portfolioEndRows: [],
    classEndIndividual: { balance: 0, provision: 0 },
    classEndPortfolio: { balance: 0, provision: 0 },
    movementRows: [], movementDetailRows: [],
    movementEndTotal: 0, movementWriteOffTotal: 0,
    pledgedRows: [], pledgedTotal: 0,
    endorsedRows: [], endorsedTotal: { derecognized: 0, notDerecognized: 0 },
    transferRows: [], transferTotal: 0,
    writeOffAmount: 0, writeOffDetailRows: [],
    ...over,
  }
}

describe('runD1DisclosureChecks', () => {
  it('空数据全部 skip，不刷屏 error（allPass）', () => {
    const s = runD1DisclosureChecks(baseInput())
    expect(s.errorCount).toBe(0)
    expect(s.allPass).toBe(true)
    expect(s.skipCount).toBeGreaterThan(0)
  })

  it('F4-3：主表明细行之和 ≠ 合计 → error', () => {
    const s = runD1DisclosureChecks(baseInput({
      summaryRows: [{
        category: '银行承兑汇票', endBalance: 100, endProvision: 0, endBookValue: 100,
        priorBalance: 0, priorProvision: 0, priorBookValue: 0,
      }],
      summaryTotal: {
        category: '合计', endBalance: 150, endProvision: 0, endBookValue: 150,
        priorBalance: 0, priorProvision: 0, priorBookValue: 0,
      },
    }))
    const c = s.checks.find(x => x.id === 'F4-3:endBalance')!
    expect(c.level).toBe('error')
    expect(c.diff).toBe(-50)
  })

  it('F4-3a：账面余额 − 坏账准备 ≠ 账面价值 → error', () => {
    const s = runD1DisclosureChecks(baseInput({
      summaryTotal: {
        category: '合计', endBalance: 1000, endProvision: 100, endBookValue: 950,
        priorBalance: 0, priorProvision: 0, priorBookValue: 0,
      },
    }))
    expect(s.checks.find(x => x.id === 'F4-3a:endBookValue')!.level).toBe('error')
  })

  it('F4-8/9/10：①合计 = ②分类表合计（一致时 ok）', () => {
    const s = runD1DisclosureChecks(baseInput({
      summaryTotal: {
        category: '合计', endBalance: 800000, endProvision: 13000, endBookValue: 787000,
        priorBalance: 0, priorProvision: 0, priorBookValue: 0,
      },
      classEndTotal: {
        label: '合计', balance: 800000, ratio: 1, provision: 13000,
        lossRate: 13000 / 800000, bookValue: 787000,
      },
    }))
    for (const id of ['F4-8:end', 'F4-9:end', 'F4-10:end']) {
      expect(s.checks.find(x => x.id === id)!.level, id).toBe('ok')
    }
  })

  it('F4-25：合计行比例不是 100% → error（实测 162.50% 的回归锁）', () => {
    const s = runD1DisclosureChecks(baseInput({
      classEndTotal: {
        label: '合计', balance: 800000, ratio: 1.625, provision: 13000,
        lossRate: 13000 / 800000, bookValue: 787000,
      },
    }))
    expect(s.checks.find(x => x.id === 'F4-25:期末')!.level).toBe('error')
  })

  it('F4-12：某行损失率被写成 0 → error（硬编码 lossRate:0 的回归锁）', () => {
    const s = runD1DisclosureChecks(baseInput({
      classEndRows: [{
        label: '按组合计提坏账准备', balance: 800000, ratio: 1,
        provision: 13000, lossRate: 0, bookValue: 787000,
      }],
      classEndTotal: {
        label: '合计', balance: 800000, ratio: 1, provision: 13000,
        lossRate: 13000 / 800000, bookValue: 787000,
      },
    }))
    expect(s.checks.find(x => x.id === 'F4-12:期末:0')!.level).toBe('error')
  })

  it('F4-4/F4-5：②组合行 = ④明细小计', () => {
    const s = runD1DisclosureChecks(baseInput({
      classEndPortfolio: { balance: 800000, provision: 13000 },
      portfolioEndRows: [
        { balance: 500000, provision: 4000 },
        { balance: 300000, provision: 9000 },
      ],
    }))
    expect(s.checks.find(x => x.id === 'F4-4:portfolio')!.level).toBe('ok')
    expect(s.checks.find(x => x.id === 'F4-5:portfolio')!.level).toBe('ok')
  })

  it('F4-7：变动表逐行平衡（其他变动是减项，源模板 G48）', () => {
    const s = runD1DisclosureChecks(baseInput({
      movementRows: [{
        label: '合计', priorBalance: 100, provision: 50, reversal: 10,
        writeOff: 5, transfer: 0, other: 0, endBalance: 135,
      }],
    }))
    expect(s.checks.find(x => x.id === 'F4-7:0')!.level).toBe('ok')
  })

  it('F4-20：「其中：」明细之和 ≠ 按组合计提行 → error（仅国企且有明细）', () => {
    const s = runD1DisclosureChecks(baseInput({
      variant: 'soe',
      movementDetailRows: [{
        label: '银行承兑汇票', priorBalance: 100, provision: 50, reversal: 0,
        writeOff: 0, transfer: 0, other: 0, endBalance: 150,
      }],
      movementPortfolio: {
        label: '按组合计提', priorBalance: 200, provision: 50, reversal: 0,
        writeOff: 0, transfer: 0, other: 0, endBalance: 250,
      },
    }))
    expect(s.checks.find(x => x.id === 'F4-20:priorBalance')!.level).toBe('error')
    expect(s.checks.find(x => x.id === 'F4-20:provision')!.level).toBe('ok')
  })

  it('F4-20 在上市变体下不产出（上市变动表无「其中：」明细）', () => {
    const s = runD1DisclosureChecks(baseInput({ variant: 'listed' }))
    expect(s.checks.some(x => x.id.startsWith('F4-20'))).toBe(false)
  })

  it('F4-6：①坏账准备期末 ≠ ⑤变动表期末 → error', () => {
    const s = runD1DisclosureChecks(baseInput({
      summaryTotal: {
        category: '合计', endBalance: 800000, endProvision: 13000, endBookValue: 787000,
        priorBalance: 0, priorProvision: 0, priorBookValue: 0,
      },
      movementEndTotal: 12000,
    }))
    const c = s.checks.find(x => x.id === 'F4-6')!
    expect(c.level).toBe('error')
    expect(c.diff).toBe(1000)
  })

  it('F4-21/22/23：质押 / 背书 / 转应收明细和 = 合计', () => {
    const s = runD1DisclosureChecks(baseInput({
      pledgedRows: [{ amount: 80000 }], pledgedTotal: 80000,
      endorsedRows: [{ derecognized: 10, notDerecognized: 20 }],
      endorsedTotal: { derecognized: 10, notDerecognized: 20 },
      transferRows: [{ amount: 12000 }], transferTotal: 12000,
    }))
    for (const id of ['F4-21', 'F4-22:derecognized', 'F4-22:notDerecognized', 'F4-23']) {
      expect(s.checks.find(x => x.id === id)!.level, id).toBe('ok')
    }
  })

  it('核销逐项之和小于总额 → warn（逐项只覆盖重要者，不是硬错）', () => {
    const s = runD1DisclosureChecks(baseInput({
      writeOffAmount: 5000, writeOffDetailRows: [{ amount: 3000 }],
      movementWriteOffTotal: 5000,
    }))
    expect(s.checks.find(x => x.id === 'F4-24:detail')!.level).toBe('warn')
    expect(s.checks.find(x => x.id === 'F4-24:movement')!.level).toBe('ok')
  })

  it('核销总额 ≠ 变动表本期核销 → error', () => {
    const s = runD1DisclosureChecks(baseInput({
      writeOffAmount: 5000, movementWriteOffTotal: 4000,
    }))
    expect(s.checks.find(x => x.id === 'F4-24:movement')!.level).toBe('error')
  })

  it('容差 0.01 元内视为一致', () => {
    const s = runD1DisclosureChecks(baseInput({
      pledgedRows: [{ amount: 100.004 }], pledgedTotal: 100,
    }))
    expect(s.checks.find(x => x.id === 'F4-21')!.level).toBe('ok')
  })

  it('每条 check 都带规则文字与追溯索引（面板 tooltip / chip 依赖）', () => {
    const s = runD1DisclosureChecks(baseInput({
      pledgedRows: [{ amount: 1 }], pledgedTotal: 1,
    }))
    for (const c of s.checks) {
      expect(c.rule.trim().length, c.id).toBeGreaterThan(5)
      expect(Array.isArray(c.refs) && c.refs.length > 0, c.id).toBe(true)
    }
  })

  it('纯函数：同输入同输出', () => {
    const input = baseInput({ pledgedRows: [{ amount: 7 }], pledgedTotal: 7 })
    expect(runD1DisclosureChecks(input)).toEqual(runD1DisclosureChecks(input))
  })
})


// ─── 勾稽差异 → A13 未更正错报汇总 ───────────────────────────────────────────

import {
  buildD1MisstatementPayload,
  D1_ACCOUNT_CODE,
  D1_ACCOUNT_NAME,
} from '../d1DisclosureConsistency'
import { normalizeMisstatementPushPayload } from '@/composables/useA13MisstatementBridge'

/** 造一份含 1 项 error（差异 1000）+ 1 项 warn + 其余 skip 的 summary */
function summaryWithOneError() {
  return runD1DisclosureChecks(baseInput({
    summaryTotal: {
      category: '合计', endBalance: 0, endProvision: 13000, endBookValue: 0,
      priorBalance: 0, priorProvision: 0, priorBookValue: 0,
    },
    movementEndTotal: 12000,
    writeOffAmount: 5000,
    writeOffDetailRows: [{ amount: 3000 }],
    movementWriteOffTotal: 5000,
  }))
}

describe('buildD1MisstatementPayload', () => {
  it('只推 error 级差异，warn（逐项只覆盖重要者）不推', () => {
    const s = summaryWithOneError()
    expect(s.warnCount).toBeGreaterThan(0)
    const p = buildD1MisstatementPayload(s)!
    expect(p).not.toBeNull()
    const ids = p.items.map(i => i.description)
    expect(ids.some(d => d.includes('F4-6'))).toBe(true)
    expect(ids.some(d => d.includes('F4-24:detail'))).toBe(false)
  })

  it('全通过时返回 null（不发空事件）', () => {
    expect(buildD1MisstatementPayload(runD1DisclosureChecks(baseInput()))).toBeNull()
  })

  it('金额取 |差异| 并四舍五入到分', () => {
    const s = runD1DisclosureChecks(baseInput({
      pledgedRows: [{ amount: 100.004 }], pledgedTotal: 90,
    }))
    const p = buildD1MisstatementPayload(s)!
    const item = p.items.find(i => i.description.includes('F4-21'))!
    expect(item.amount).toBe(10)
  })

  it('容差内差异不推（桥对 amount≤0 也会丢，这里提前过滤）', () => {
    const s = runD1DisclosureChecks(baseInput({
      pledgedRows: [{ amount: 100.004 }], pledgedTotal: 100,
    }))
    expect(buildD1MisstatementPayload(s)).toBeNull()
  })

  it('checkIds 指定时只推那几项（单行推送）', () => {
    const s = summaryWithOneError()
    const p = buildD1MisstatementPayload(s, { checkIds: ['F4-24:detail'] })!
    expect(p.items).toHaveLength(1)
    expect(p.items[0].description).toContain('F4-24:detail')
  })

  it('描述内联规则编号、两侧金额与规则文字（错报汇总里可直接溯源）', () => {
    const p = buildD1MisstatementPayload(summaryWithOneError())!
    const d = p.items[0].description
    expect(d).toContain('应收票据披露勾稽差异')
    expect(d).toContain('本表')
    expect(d).toContain('勾稽对象')
    expect(d).toContain('规则：')
  })

  it('科目编码 / 名称 / wpCode 齐备（写入 source_wp_code 溯源）', () => {
    const p = buildD1MisstatementPayload(summaryWithOneError())!
    expect(p.wpCode).toBe('D1')
    expect(p.accountCode).toBe(D1_ACCOUNT_CODE)
    expect(p.accountName).toBe(D1_ACCOUNT_NAME)
    for (const it of p.items) {
      expect(it.wpCode).toBe('D1')
      expect(it.accountCode).toBe(D1_ACCOUNT_CODE)
      expect(it.accountName).toBe(D1_ACCOUNT_NAME)
      expect(it.indexRef.length).toBeGreaterThan(0)
    }
  })

  it('🔴 载荷能被平台桥 normalizeMisstatementPushPayload 正确归一（形态 A）', () => {
    const p = buildD1MisstatementPayload(summaryWithOneError())!
    const drafts = normalizeMisstatementPushPayload(p)
    expect(drafts.length).toBe(p.items.length)
    for (const d of drafts) {
      expect(d.wpCode).toBe('D1')
      expect(d.amount).toBeGreaterThan(0)
      expect(d.accountCode).toBe(D1_ACCOUNT_CODE)
      expect(d.accountName).toBe(D1_ACCOUNT_NAME)
      // 桥会把索引拼进描述，便于错报汇总溯源
      expect(d.description).toContain('索引:')
    }
  })

  it('source_wp_code 截断后仍有效（桥截 20 字符）', () => {
    const p = buildD1MisstatementPayload(summaryWithOneError())!
    for (const it of p.items) {
      expect(it.wpCode.slice(0, 20)).toBe('D1')
    }
  })

  it('纯函数：同输入同输出', () => {
    const s = summaryWithOneError()
    expect(buildD1MisstatementPayload(s)).toEqual(buildD1MisstatementPayload(s))
  })
})
