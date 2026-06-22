/**
 * useDiffChecklistData.test.ts — D0-4b 公式链 + CRUD + 状态 + D0-4 去重 + buildPayload
 *
 * 覆盖属性 P1(A-I 公式链正确) / P2(子表增删→合计→公式联动) / P3(差异状态) / P4(D0-4 去重) / P5(buildPayload round-trip)
 */
import { describe, it, expect } from 'vitest'
import { useDiffChecklistData } from '../composables/useDiffChecklistData'
import type { DiffChecklistCompany, SubTableRow } from '../diffChecklistTypes'

// ─── 辅助：创建 composable 实例 ──────────────────────────────────────────────

function createInstance(initialData?: any) {
  const htmlData = initialData ?? { _format: 'diff-checklist-v1', companies: [] }
  return useDiffChecklistData({
    htmlData: () => htmlData,
    readonly: false,
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// P1: A-I 公式链正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('P1: A-I 公式链', () => {
  it('D = A + B - C（精确小数）', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    // Add B row (amount=200)
    inst.addSubTableRow(company._row_id!, 'b')
    const bRow = inst.companies.value[0].b_rows![0]
    inst.updateSubTableRow(company._row_id!, 'b', bRow._row_id!, 'amount', 200)
    // Add C row (amount=50)
    inst.addSubTableRow(company._row_id!, 'c')
    const cRow = inst.companies.value[0].c_rows![0]
    inst.updateSubTableRow(company._row_id!, 'c', cRow._row_id!, 'amount', 50)

    const c = inst.companies.value[0]
    expect(c.b_total).toBe(200)
    expect(c.c_total).toBe(50)
    expect(c.d_adjusted_reply).toBe(1150) // 1000 + 200 - 50
  })

  it('H = E + F - G（精确小数）', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'e_book_amount', 2000)
    // Add F row (amount=300)
    inst.addSubTableRow(company._row_id!, 'f')
    const fRow = inst.companies.value[0].f_rows![0]
    inst.updateSubTableRow(company._row_id!, 'f', fRow._row_id!, 'amount', 300)
    // Add G row (amount=100)
    inst.addSubTableRow(company._row_id!, 'g')
    const gRow = inst.companies.value[0].g_rows![0]
    inst.updateSubTableRow(company._row_id!, 'g', gRow._row_id!, 'amount', 100)

    const c = inst.companies.value[0]
    expect(c.f_total).toBe(300)
    expect(c.g_total).toBe(100)
    expect(c.h_adjusted_book).toBe(2200) // 2000 + 300 - 100
  })

  it('I = H - D（最终差异）', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    inst.updateCompany(company._row_id!, 'e_book_amount', 1000)

    // D = 1000 + 0 - 0 = 1000; H = 1000 + 0 - 0 = 1000; I = 0
    const c = inst.companies.value[0]
    expect(c.d_adjusted_reply).toBe(1000)
    expect(c.h_adjusted_book).toBe(1000)
    expect(c.i_final_diff).toBe(0)
  })

  it('I≠0 时反映正确差异', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    inst.updateCompany(company._row_id!, 'e_book_amount', 800)

    // D = 1000; H = 800; I = 800 - 1000 = -200
    const c = inst.companies.value[0]
    expect(c.i_final_diff).toBe(-200)
  })

  it('浮点精度：0.1 + 0.2 场景', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 0.1)
    inst.addSubTableRow(company._row_id!, 'b')
    const bRow = inst.companies.value[0].b_rows![0]
    inst.updateSubTableRow(company._row_id!, 'b', bRow._row_id!, 'amount', 0.2)

    const c = inst.companies.value[0]
    // D = 0.1 + 0.2 - 0 = 0.3（不是 0.30000000000000004）
    expect(c.d_adjusted_reply).toBe(0.3)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P2: 子表增删→合计→公式联动
// ═══════════════════════════════════════════════════════════════════════════════

describe('P2: 子表增删→公式联动', () => {
  it('新增子表行后合计和公式链自动更新', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 500)

    inst.addSubTableRow(company._row_id!, 'b')
    inst.addSubTableRow(company._row_id!, 'b')

    const rows = inst.companies.value[0].b_rows!
    inst.updateSubTableRow(company._row_id!, 'b', rows[0]._row_id!, 'amount', 100)
    inst.updateSubTableRow(company._row_id!, 'b', rows[1]._row_id!, 'amount', 200)

    expect(inst.companies.value[0].b_total).toBe(300)
    expect(inst.companies.value[0].d_adjusted_reply).toBe(800) // 500 + 300 - 0
  })

  it('删除子表行后合计和公式链自动更新', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 500)

    inst.addSubTableRow(company._row_id!, 'b')
    inst.addSubTableRow(company._row_id!, 'b')

    const rows = inst.companies.value[0].b_rows!
    inst.updateSubTableRow(company._row_id!, 'b', rows[0]._row_id!, 'amount', 100)
    inst.updateSubTableRow(company._row_id!, 'b', rows[1]._row_id!, 'amount', 200)

    // 删第一行
    inst.deleteSubTableRow(company._row_id!, 'b', rows[0]._row_id!)

    expect(inst.companies.value[0].b_total).toBe(200)
    expect(inst.companies.value[0].d_adjusted_reply).toBe(700) // 500 + 200 - 0
  })

  it('修改子表行金额后公式链实时重算', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 1000)

    inst.addSubTableRow(company._row_id!, 'c')
    const cRow = inst.companies.value[0].c_rows![0]
    inst.updateSubTableRow(company._row_id!, 'c', cRow._row_id!, 'amount', 100)
    expect(inst.companies.value[0].d_adjusted_reply).toBe(900) // 1000 + 0 - 100

    // 修改
    inst.updateSubTableRow(company._row_id!, 'c', cRow._row_id!, 'amount', 300)
    expect(inst.companies.value[0].d_adjusted_reply).toBe(700) // 1000 + 0 - 300
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P3: 差异状态
// ═══════════════════════════════════════════════════════════════════════════════

describe('P3: 差异状态派生', () => {
  it('I=0 → balanced', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    inst.updateCompany(company._row_id!, 'e_book_amount', 1000)

    expect(inst.companies.value[0].status).toBe('balanced')
  })

  it('I≠0 无重要性配置 → diff', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    inst.updateCompany(company._row_id!, 'e_book_amount', 800)

    expect(inst.companies.value[0].status).toBe('diff')
  })

  it('|I|≥重要性 → over_materiality', () => {
    const inst = createInstance({
      _format: 'diff-checklist-v1',
      companies: [],
      materiality_config: { performance_materiality: 100 },
    })
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 1000)
    inst.updateCompany(company._row_id!, 'e_book_amount', 800)
    // I = 800 - 1000 = -200, |I| = 200 >= 100

    expect(inst.companies.value[0].status).toBe('over_materiality')
  })

  it('重要性未配置不误报', () => {
    const inst = createInstance()
    const company = inst.addCompany()
    inst.updateCompany(company._row_id!, 'a_reply_amount', 99999)
    inst.updateCompany(company._row_id!, 'e_book_amount', 0)

    expect(inst.companies.value[0].status).toBe('diff')
    expect(inst.isOverMateriality(inst.companies.value[0])).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P4: D0-4 带入去重
// ═══════════════════════════════════════════════════════════════════════════════

describe('P4: D0-4 带入去重', () => {
  it('entity_name + subject 去重，不重复导入', () => {
    const inst = createInstance()
    // 先手动加一家
    const c1 = inst.addCompany()
    inst.updateCompany(c1._row_id!, 'entity_name', '甲公司')
    inst.updateCompany(c1._row_id!, 'subject', '应收账款')

    // 导入含相同公司
    inst.importCompanies([
      { entity_name: '甲公司', subject: '应收账款', a_reply_amount: 100 } as DiffChecklistCompany,
      { entity_name: '乙公司', subject: '应收账款', a_reply_amount: 200 } as DiffChecklistCompany,
    ])

    // 只新增了乙公司
    expect(inst.companies.value.length).toBe(2)
    expect(inst.companies.value[1].entity_name).toBe('乙公司')
  })

  it('导入时 _source 标识为 auto', () => {
    const inst = createInstance()
    inst.importCompanies([
      { entity_name: '丙公司', subject: '合同负债', a_reply_amount: 500 } as DiffChecklistCompany,
    ])
    expect(inst.companies.value[0]._source).toBe('auto')
  })

  it('导入时自动计算公式链', () => {
    const inst = createInstance()
    inst.importCompanies([
      {
        entity_name: '丁公司',
        subject: '应收账款',
        a_reply_amount: 1000,
        e_book_amount: 800,
        b_rows: [{ amount: 100, _row_id: 'x1' }],
      } as DiffChecklistCompany,
    ])
    const c = inst.companies.value[0]
    expect(c.b_total).toBe(100)
    expect(c.d_adjusted_reply).toBe(1100) // 1000 + 100 - 0
    expect(c.h_adjusted_book).toBe(800) // 800 + 0 - 0
    expect(c.i_final_diff).toBe(-300) // 800 - 1100
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P5: buildPayload round-trip
// ═══════════════════════════════════════════════════════════════════════════════

describe('P5: buildPayload', () => {
  it('格式版本和数据结构正确', () => {
    const inst = createInstance()
    const c = inst.addCompany()
    inst.updateCompany(c._row_id!, 'entity_name', '测试公司')
    inst.updateCompany(c._row_id!, 'a_reply_amount', 1000)
    inst.updateCompany(c._row_id!, 'e_book_amount', 1000)

    const payload = inst.buildPayload()
    expect(payload._format).toBe('diff-checklist-v1')
    expect(payload.companies).toHaveLength(1)
    expect(payload.companies[0].entity_name).toBe('测试公司')
    expect(payload.companies[0].i_final_diff).toBe(0)
  })

  it('round-trip：buildPayload → 重新初始化 → 数据一致', () => {
    const inst1 = createInstance()
    const c = inst1.addCompany()
    inst1.updateCompany(c._row_id!, 'entity_name', '戊公司')
    inst1.updateCompany(c._row_id!, 'a_reply_amount', 500)
    inst1.updateCompany(c._row_id!, 'e_book_amount', 600)
    inst1.addSubTableRow(c._row_id!, 'b')
    const bRow = inst1.companies.value[0].b_rows![0]
    inst1.updateSubTableRow(c._row_id!, 'b', bRow._row_id!, 'amount', 50)

    inst1.globalNote.value = '测试说明'
    inst1.conclusion.value = { conclusion_type: 'A', conclusion_text: '全部平衡' }

    const payload = inst1.buildPayload()

    // 用 payload 初始化新实例
    const inst2 = createInstance(payload)
    expect(inst2.companies.value.length).toBe(1)
    expect(inst2.companies.value[0].entity_name).toBe('戊公司')
    expect(inst2.companies.value[0].b_total).toBe(50)
    expect(inst2.companies.value[0].d_adjusted_reply).toBe(550) // 500 + 50 - 0
    expect(inst2.companies.value[0].h_adjusted_book).toBe(600)
    expect(inst2.companies.value[0].i_final_diff).toBe(50) // 600 - 550
    expect(inst2.globalNote.value).toBe('测试说明')
    expect(inst2.conclusion.value.conclusion_type).toBe('A')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// CRUD 基础
// ═══════════════════════════════════════════════════════════════════════════════

describe('CRUD 基础', () => {
  it('addCompany 生成唯一 ID 和递增序号', () => {
    const inst = createInstance()
    const c1 = inst.addCompany()
    const c2 = inst.addCompany()
    expect(c1._row_id).toBeTruthy()
    expect(c2._row_id).toBeTruthy()
    expect(c1._row_id).not.toBe(c2._row_id)
    expect(c1.seq).toBe(1)
    expect(c2.seq).toBe(2)
  })

  it('deleteCompany 正确删除', () => {
    const inst = createInstance()
    const c1 = inst.addCompany()
    const c2 = inst.addCompany()
    inst.deleteCompany([c1._row_id!])
    expect(inst.companies.value.length).toBe(1)
    expect(inst.companies.value[0]._row_id).toBe(c2._row_id)
  })

  it('isDirty 在操作后变为 true', () => {
    const inst = createInstance()
    expect(inst.isDirty.value).toBe(false)
    inst.addCompany()
    expect(inst.isDirty.value).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 看板指标
// ═══════════════════════════════════════════════════════════════════════════════

describe('看板指标', () => {
  it('正确计算总/已平/有差异/完成率', () => {
    const inst = createInstance({
      _format: 'diff-checklist-v1',
      companies: [],
      materiality_config: { performance_materiality: 500 },
    })
    // 公司1：平衡
    const c1 = inst.addCompany()
    inst.updateCompany(c1._row_id!, 'a_reply_amount', 100)
    inst.updateCompany(c1._row_id!, 'e_book_amount', 100)
    // 公司2：有差异
    const c2 = inst.addCompany()
    inst.updateCompany(c2._row_id!, 'a_reply_amount', 100)
    inst.updateCompany(c2._row_id!, 'e_book_amount', 200)
    // 公司3：超重要性(|I|=900 >= 500)
    const c3 = inst.addCompany()
    inst.updateCompany(c3._row_id!, 'a_reply_amount', 1000)
    inst.updateCompany(c3._row_id!, 'e_book_amount', 100)

    const m = inst.metrics.value
    expect(m.total_count).toBe(3)
    expect(m.balanced_count).toBe(1)
    expect(m.diff_count).toBe(2) // 有差异+超重要性
    expect(m.over_materiality_count).toBe(1)
    expect(m.completion_rate).toBeCloseTo(33.33, 1)
  })
})
