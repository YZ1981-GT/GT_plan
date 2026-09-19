/**
 * useDiffChecklistData.pbt.spec.ts — A-I 公式链恒等式 PBT 守卫
 *
 * 🔴 立项依据（f0-confirmation-linkage-and-structural-enhancement Task 24）：
 * 上一轮为 F0 另写了一份 `f0DiffChecklistEngine.ts` 做同样的九段公式，
 * 复盘发现既有 `useDiffChecklistData.computeFormula` 已完整实现 → 删重复件，
 * **把真正缺的恒等式 PBT 补给既有实现**（原测试只有固定样例，无随机验证、无 NaN 防御断言）。
 *
 * 覆盖：
 * - Property A: D = A + B − C 恒等（随机输入，精度 ≤ 0.01）
 * - Property B: H = E + F − G 恒等
 * - Property C: I = H − D 恒等
 * - Property D: NaN/Infinity 脏数据不污染公式链（既有实现原 `?? 0` 会穿透，本轮已修）
 * - Property E: 子表增删后合计重算正确
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useDiffChecklistData } from '../useDiffChecklistData'
import type { DiffChecklistCompany, SubTableRow } from '../../diffChecklistTypes'

// ─── 测试桩 ───────────────────────────────────────────────────────────────────

function createInstance(initial?: any) {
  const htmlDataRef = ref<any>(initial ?? { _format: 'diff-checklist-v1', companies: [] })
  return useDiffChecklistData({
    htmlData: () => htmlDataRef.value,
    readonly: false,
  } as any)
}

/** 构造一个已填公式输入的 company payload */
function makeCompanyPayload(spec: {
  A?: unknown
  E?: unknown
  b?: unknown[]
  c?: unknown[]
  f?: unknown[]
  g?: unknown[]
}): Partial<DiffChecklistCompany> {
  const rows = (amounts?: unknown[]): SubTableRow[] =>
    (amounts ?? []).map((amount, i) => ({ _row_id: `r${i}`, seq: i + 1, amount } as SubTableRow))
  return {
    _row_id: 'c1',
    entity_name: 'X',
    a_reply_amount: spec.A as any,
    e_book_amount: spec.E as any,
    b_rows: rows(spec.b),
    c_rows: rows(spec.c),
    f_rows: rows(spec.f),
    g_rows: rows(spec.g),
  }
}

function computeVia(spec: Parameters<typeof makeCompanyPayload>[0]) {
  const data = createInstance({
    _format: 'diff-checklist-v1',
    companies: [makeCompanyPayload(spec)],
  })
  return data.companies.value[0]
}

/** 只累加有限值（期望值计算侧的参照实现） */
function finiteSum(values?: unknown[]): number {
  return (values ?? []).reduce<number>((s, v) => {
    const n = Number(v)
    return Number.isFinite(n) ? s + n : s
  }, 0)
}

function finiteNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 随机数生成 ───────────────────────────────────────────────────────────────

function randomAmount(): number {
  return Math.round((Math.random() * 2_000_000 - 1_000_000) * 100) / 100
}

function randomAmounts(count: number): number[] {
  return Array.from({ length: count }, randomAmount)
}

// ─── Property A/B/C: 恒等式（50 次随机输入） ─────────────────────────────────

describe('Property A/B/C: A-I 公式链恒等式（PBT 50 次）', () => {
  for (let i = 0; i < 50; i++) {
    it(`随机输入 #${i + 1}: D=A+B−C / H=E+F−G / I=H−D`, () => {
      const spec = {
        A: randomAmount(),
        E: randomAmount(),
        b: randomAmounts(Math.floor(Math.random() * 5)),
        c: randomAmounts(Math.floor(Math.random() * 5)),
        f: randomAmounts(Math.floor(Math.random() * 5)),
        g: randomAmounts(Math.floor(Math.random() * 5)),
      }
      const c = computeVia(spec)

      const expB = finiteSum(spec.b)
      const expC = finiteSum(spec.c)
      const expF = finiteSum(spec.f)
      const expG = finiteSum(spec.g)
      const expD = finiteNum(spec.A) + expB - expC
      const expH = finiteNum(spec.E) + expF - expG
      const expI = expH - expD

      expect(Math.abs((c.b_total ?? 0) - expB)).toBeLessThan(0.01)
      expect(Math.abs((c.c_total ?? 0) - expC)).toBeLessThan(0.01)
      expect(Math.abs((c.f_total ?? 0) - expF)).toBeLessThan(0.01)
      expect(Math.abs((c.g_total ?? 0) - expG)).toBeLessThan(0.01)
      expect(Math.abs((c.d_adjusted_reply ?? 0) - expD)).toBeLessThan(0.01)
      expect(Math.abs((c.h_adjusted_book ?? 0) - expH)).toBeLessThan(0.01)
      expect(Math.abs((c.i_final_diff ?? 0) - expI)).toBeLessThan(0.01)
    })
  }
})

// ─── Property D: 脏数据不污染公式链 ─────────────────────────────────────────

describe('Property D: NaN/Infinity 不污染公式链', () => {
  it('子表含 NaN 行时其余行仍正确求和（原 `?? 0` 会穿透）', () => {
    const c = computeVia({ A: 1000, E: 1000, b: [100, NaN, 200] })
    expect(c.b_total).toBe(300)
    expect(Number.isFinite(c.d_adjusted_reply!)).toBe(true)
    expect(c.d_adjusted_reply).toBe(1300)
  })

  it('子表含 Infinity 行时跳过该行', () => {
    const c = computeVia({ A: 0, E: 0, b: [Infinity, 50, -Infinity] })
    expect(c.b_total).toBe(50)
    expect(Number.isFinite(c.i_final_diff!)).toBe(true)
  })

  it('子表含非数字字符串时跳过该行', () => {
    const c = computeVia({ A: 0, E: 0, c: ['abc', 100, ''] })
    // '' → Number('') === 0（有限）→ 计入；'abc' → NaN → 跳过
    expect(c.c_total).toBe(100)
  })

  it('A 为 NaN 时视为 0，不产出 NaN', () => {
    const c = computeVia({ A: NaN, E: 500, b: [100] })
    expect(c.d_adjusted_reply).toBe(100)
    expect(Number.isFinite(c.i_final_diff!)).toBe(true)
  })

  it('E 为 undefined 时视为 0', () => {
    const c = computeVia({ A: 100, E: undefined, f: [200] })
    expect(c.h_adjusted_book).toBe(200)
  })

  it('A/E 均为字符串数字时正确解析', () => {
    const c = computeVia({ A: '1000' as any, E: '2000' as any })
    expect(c.d_adjusted_reply).toBe(1000)
    expect(c.h_adjusted_book).toBe(2000)
    expect(c.i_final_diff).toBe(1000)
  })

  it('全脏数据 → 全 0，i_final_diff 为 0 且 status=balanced', () => {
    const c = computeVia({ A: NaN, E: 'x', b: [NaN], c: ['y'], f: [Infinity], g: [null] })
    expect(c.d_adjusted_reply).toBe(0)
    expect(c.h_adjusted_book).toBe(0)
    expect(c.i_final_diff).toBe(0)
    expect(c.status).toBe('balanced')
  })
})

// ─── Property E: 增删子表行后重算 ───────────────────────────────────────────

describe('Property E: 子表 CRUD 后公式重算', () => {
  it('addSubTableRow 后合计包含新行（初值 0 → 合计不变）', () => {
    const data = createInstance()
    const company = data.addCompany()
    data.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    const before = data.companies.value[0].d_adjusted_reply
    data.addSubTableRow(company._row_id!, 'b')
    expect(data.companies.value[0].b_rows).toHaveLength(1)
    expect(data.companies.value[0].d_adjusted_reply).toBe(before)
  })

  it('updateSubTableRow 金额后 D 随之变化', () => {
    const data = createInstance()
    const company = data.addCompany()
    data.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    const row = data.addSubTableRow(company._row_id!, 'b')!
    data.updateSubTableRow(company._row_id!, 'b', row._row_id!, 'amount', 250)
    expect(data.companies.value[0].b_total).toBe(250)
    expect(data.companies.value[0].d_adjusted_reply).toBe(1250)
  })

  it('deleteSubTableRow 后合计扣除该行', () => {
    const data = createInstance()
    const company = data.addCompany()
    const r1 = data.addSubTableRow(company._row_id!, 'c')!
    const r2 = data.addSubTableRow(company._row_id!, 'c')!
    data.updateSubTableRow(company._row_id!, 'c', r1._row_id!, 'amount', 100)
    data.updateSubTableRow(company._row_id!, 'c', r2._row_id!, 'amount', 200)
    expect(data.companies.value[0].c_total).toBe(300)
    data.deleteSubTableRow(company._row_id!, 'c', r1._row_id!)
    expect(data.companies.value[0].c_total).toBe(200)
  })

  it('删空所有行后合计归 0', () => {
    const data = createInstance()
    const company = data.addCompany()
    const r = data.addSubTableRow(company._row_id!, 'f')!
    data.updateSubTableRow(company._row_id!, 'f', r._row_id!, 'amount', 999)
    expect(data.companies.value[0].f_total).toBe(999)
    data.deleteSubTableRow(company._row_id!, 'f', r._row_id!)
    expect(data.companies.value[0].f_total).toBe(0)
  })
})

// ─── 反向自检：证明测试确实在验真实实现 ─────────────────────────────────────

describe('反向自检', () => {
  it('固定样例结果与手算一致（证明 computeVia 真的跑了公式）', () => {
    // A=100000, B=8000, C=2000 → D=106000
    // E=95000,  F=5000, G=3000 → H=97000
    // I = 97000 - 106000 = -9000
    const c = computeVia({
      A: 100000,
      E: 95000,
      b: [5000, 3000],
      c: [2000],
      f: [4000, 1000],
      g: [3000],
    })
    expect(c.d_adjusted_reply).toBe(106000)
    expect(c.h_adjusted_book).toBe(97000)
    expect(c.i_final_diff).toBe(-9000)
    expect(c.status).not.toBe('balanced')
  })

  it('差异为 0 时 status=balanced', () => {
    const c = computeVia({ A: 50000, E: 50000 })
    expect(c.i_final_diff).toBe(0)
    expect(c.status).toBe('balanced')
  })
})
