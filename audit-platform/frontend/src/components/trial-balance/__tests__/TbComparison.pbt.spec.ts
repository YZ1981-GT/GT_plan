/**
 * Trial Balance Cross Comparison — Property-Based + Unit Test Suite
 * Spec: .kiro/specs/trial-balance-cross-comparison/  (Task 5)
 *
 * Covers Correctness Properties P1–P7 (design.md):
 *   P1 Join by Account Code        — **Validates: Requirements 4**
 *   P2 Variance Calculation        — **Validates: Requirements 3**  (含 zero-division)
 *   P3 Permission Isolation (403)  — **Validates: Requirements 7**
 *   P4 Cache Consistency           — **Validates: Requirements 6**
 *   P5 Column Limit (max 5)        — **Validates: Requirements 5**
 *   P6 Export Correctness          — **Validates: Requirements 3**
 *   P7 Zero Regression             — **Validates: Requirements 8**
 *
 * 实施方案：vitest + @vue/test-utils mount + fast-check（numRuns: 20，对齐 workspace 规则）。
 *   P1–P4 在 composable 层（useTbComparison）做属性/单元测试；
 *   P5–P7 mount TbComparisonView 驱动组件内部 guard/export/opt-in 行为。
 *
 * ⚠️ 设计文档 P2 散文写 `variance_amount = target - current` / `/abs(current)`，
 *    但实现按审计惯例的同比口径 `变动额 = 本年(current) - 对比(target)`、
 *    `变动率 = 变动额 / abs(target)`（target=0 → rate=null）。二者对 Requirement 1
 *    「变动额/变动率 + |变动率|>30% 高亮」而言实现方向正确（本年-上年），design 散文的
 *    符号/分母基是笔误。本套测试按实现的审计正确口径断言，并对 P2 强断言核心 spec 意图
 *    「zero-division 安全」= rate 恒为 null 或有限数（绝不 NaN/±Infinity）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { ref, nextTick, type Ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mock 远程 service（复用已有 GET /trial-balance，不打真实网络） ────────────
const getTrialBalanceMock = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({
  getTrialBalance: (...a: any[]) => getTrialBalanceMock(...a),
}))

// ─── Mock http（TbComparisonView 加载可选对比项目清单用） ──────────────────────
const httpGetMock = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...a: any[]) => httpGetMock(...a) },
}))

// ─── Mock xlsx 动态 import（P6 导出，避免真实写盘） ───────────────────────────
const bookNewMock = vi.fn(() => ({}))
const aoaToSheetMock = vi.fn(() => ({}))
const bookAppendMock = vi.fn()
const writeFileMock = vi.fn()
vi.mock('xlsx', () => ({
  utils: {
    book_new: (...a: any[]) => bookNewMock(...a),
    aoa_to_sheet: (...a: any[]) => aoaToSheetMock(...a),
    book_append_sheet: (...a: any[]) => bookAppendMock(...a),
  },
  writeFile: (...a: any[]) => writeFileMock(...a),
}))

import { useTbComparison } from '@/composables/useTbComparison'
import TbComparisonView from '@/components/trial-balance/TbComparisonView.vue'

// ═══════════════════════════════════════════════════════════════════════════════
// Helpers & Generators
// ═══════════════════════════════════════════════════════════════════════════════

interface Row { standard_account_code: string; account_name: string; audited_amount: number }

function makeRow(code: string, amount: number, name = '科目'): Row {
  return { standard_account_code: code, account_name: name, audited_amount: amount }
}

/** 用当前行构造 composable 实例 */
function makeComp(currentRows: Row[] = []) {
  const projectId = ref('proj-current') as Ref<string>
  const year = ref(2025) as Ref<number>
  const rows = ref(currentRows) as Ref<any[]>
  const comp = useTbComparison(projectId, year, rows)
  return { comp, projectId, year, rows }
}

const CODE_POOL = ['1001', '1002', '1122', '2202', '6001', '1601', '2211'] as const
const codeArb = fc.constantFrom(...CODE_POOL)
// 金额生成器：含 0（覆盖 zero-division）+ 正/负整数（精确算术，避免浮点噪声）
const amtArb = fc.oneof(fc.constant(0), fc.integer({ min: -1_000_000, max: 1_000_000 }))
const rowArb = fc.record({
  standard_account_code: codeArb,
  account_name: fc.constantFrom('现金', '银行存款', '应收账款'),
  audited_amount: amtArb,
})
/** 数组去重（同 code 保留首个，模拟 currentMap.set 覆盖后的唯一集） */
const rowsArb = fc.array(rowArb, { maxLength: 8 }).map((arr) => {
  const seen = new Set<string>()
  const out: Row[] = []
  for (const r of arr) {
    if (!seen.has(r.standard_account_code)) { seen.add(r.standard_account_code); out.push(r) }
  }
  return out
})

const NUM_RUNS = 20

beforeEach(() => {
  getTrialBalanceMock.mockReset()
  getTrialBalanceMock.mockResolvedValue([])
  httpGetMock.mockReset()
  httpGetMock.mockResolvedValue({ data: { items: [] } })
  bookNewMock.mockClear(); aoaToSheetMock.mockClear(); bookAppendMock.mockClear(); writeFileMock.mockClear()
})

// ═══════════════════════════════════════════════════════════════════════════════
// P1: Join by Account Code — **Validates: Requirements 4**
// ═══════════════════════════════════════════════════════════════════════════════
describe('P1 Join by Account Code (useTbComparison.joinedRows)', () => {
  it('P1: joinedRows = union(current, target) by standard_account_code，去重、有序、onlyCurrent 正确', async () => {
    await fc.assert(
      fc.asyncProperty(rowsArb, rowsArb, async (curr, tgt) => {
        getTrialBalanceMock.mockResolvedValue(tgt)
        const { comp } = makeComp(curr)
        await comp.loadComparisonYear(2024)

        const codes = comp.joinedRows.value.map((r) => r.standard_account_code)
        const currCodes = new Set(curr.map((r) => r.standard_account_code))
        const tgtCodes = new Set(tgt.map((r) => r.standard_account_code))
        const union = new Set<string>([...currCodes, ...tgtCodes])

        // 并集完整 + 无重复
        expect(new Set(codes)).toEqual(union)
        expect(codes.length).toBe(union.size)
        // 有序（按 code 升序）
        expect(codes).toEqual([...codes].sort())

        for (const jr of comp.joinedRows.value) {
          const code = jr.standard_account_code
          const inCurr = currCodes.has(code)
          const inTgt = tgtCodes.has(code)
          // 仅本方：在当前、不在任何对比目标
          expect(jr.onlyCurrent).toBe(inCurr && !inTgt)
          // 不在当前 → current_audited 归零
          if (!inCurr) expect(jr.current_audited).toBe(0)
          // 对比目标值：在对比中为数值、否则为 null
          expect(jr.targets['2024'] === null || typeof jr.targets['2024'] === 'number').toBe(true)
          if (inTgt) expect(typeof jr.targets['2024']).toBe('number')
          else expect(jr.targets['2024']).toBeNull()
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('P1(unit): 无对比目标 → joinedRows 为空', () => {
    const { comp } = makeComp([makeRow('1001', 100)])
    expect(comp.joinedRows.value).toEqual([])
  })

  it('P1(unit): 部分重叠 → 分别落入交集/仅本方/仅对方', async () => {
    getTrialBalanceMock.mockResolvedValue([makeRow('1002', 50), makeRow('2202', 30)])
    const { comp } = makeComp([makeRow('1001', 100), makeRow('1002', 60)])
    await comp.loadComparisonYear(2024)
    const byCode = Object.fromEntries(comp.joinedRows.value.map((r) => [r.standard_account_code, r]))
    // 1001 仅本方
    expect(byCode['1001'].onlyCurrent).toBe(true)
    expect(byCode['1001'].targets['2024']).toBeNull()
    // 1002 交集
    expect(byCode['1002'].onlyCurrent).toBe(false)
    expect(byCode['1002'].targets['2024']).toBe(50)
    // 2202 仅对方（当前不存在 → current_audited=0）
    expect(byCode['2202'].current_audited).toBe(0)
    expect(byCode['2202'].targets['2024']).toBe(30)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P2: Variance Calculation (含 zero-division) — **Validates: Requirements 3**
// ═══════════════════════════════════════════════════════════════════════════════
describe('P2 Variance Calculation (含 zero-division)', () => {
  it('P2: 交集科目 variance.amount=本年-对比；rate 恒 null 或有限数（zero-division 安全）', async () => {
    await fc.assert(
      fc.asyncProperty(codeArb, amtArb, amtArb, async (code, currentAmt, targetAmt) => {
        getTrialBalanceMock.mockResolvedValue([makeRow(code, targetAmt)])
        const { comp } = makeComp([makeRow(code, currentAmt)])
        await comp.loadComparisonYear(2024)
        const jr = comp.joinedRows.value.find((r) => r.standard_account_code === code)!
        const v = jr.variances['2024']

        // 核心 spec 意图：zero-division 绝不产生 NaN/±Infinity
        expect(v.rate === null || Number.isFinite(v.rate)).toBe(true)
        // 变动额 = 本年审定 - 对比审定（同比口径）
        expect(v.amount).toBeCloseTo(currentAmt - targetAmt, 6)
        // 分母为 0（对比审定=0）→ rate=null；否则 = 变动额/|对比审定|
        if (targetAmt === 0) {
          expect(v.rate).toBeNull()
        } else {
          expect(v.rate).not.toBeNull()
          expect(v.rate as number).toBeCloseTo((currentAmt - targetAmt) / Math.abs(targetAmt), 6)
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('P2(unit): 仅本方（对比缺失）→ 变动额=本年审定，rate=null（新增语义）', async () => {
    getTrialBalanceMock.mockResolvedValue([])
    const { comp } = makeComp([makeRow('1001', 100)])
    await comp.loadComparisonYear(2024)
    const jr = comp.joinedRows.value.find((r) => r.standard_account_code === '1001')!
    expect(jr.variances['2024'].amount).toBe(100)
    expect(jr.variances['2024'].rate).toBeNull()
  })

  it('P2(unit): 仅对方（本方缺失）→ 变动额=-对比审定，rate=对应符号（移除语义）', async () => {
    getTrialBalanceMock.mockResolvedValue([makeRow('2202', 40)])
    const { comp } = makeComp([])
    await comp.loadComparisonYear(2024)
    const jr = comp.joinedRows.value.find((r) => r.standard_account_code === '2202')!
    expect(jr.current_audited).toBe(0)
    expect(jr.variances['2024'].amount).toBe(-40)
    expect(jr.variances['2024'].rate).toBeCloseTo(-1, 6)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P3: Permission Isolation (403) — **Validates: Requirements 7**
// ═══════════════════════════════════════════════════════════════════════════════
describe('P3 Permission Isolation (403 不阻塞整体对比)', () => {
  it('P3: 目标项目 403 → 记录「无权限访问该项目」、不抛错、不泄露其数据；其余项目正常加载', async () => {
    getTrialBalanceMock
      .mockRejectedValueOnce({ response: { status: 403 } })   // 子公司 A 无权限
      .mockResolvedValueOnce([makeRow('1001', 200)])          // 子公司 B 正常
    const { comp } = makeComp([makeRow('1001', 100)])

    // 403 不应抛出（不阻塞）
    await expect(comp.loadComparisonProject('pA', '子A')).resolves.toBeUndefined()
    await comp.loadComparisonProject('pB', '子B')

    // A 记录无权限、未加入 targets（无数据泄露到 joinedRows）
    expect(comp.errors.value.get('pA')).toBe('无权限访问该项目')
    expect(comp.targets.value.some((t) => t.key === 'pA')).toBe(false)
    // B 正常加载、无 error、进入对比
    expect(comp.errors.value.has('pB')).toBe(false)
    expect(comp.targets.value.some((t) => t.key === 'pB')).toBe(true)
    // joinedRows 仅含可访问项目的数据
    const jr = comp.joinedRows.value.find((r) => r.standard_account_code === '1001')!
    expect(jr.targets['pB']).toBe(200)
    expect(jr.targets['pA']).toBeUndefined()
  })

  it('P3(unit): 非 403 网络错误 → 记「加载失败」，同样不阻塞', async () => {
    getTrialBalanceMock.mockRejectedValueOnce(new Error('network'))
    const { comp } = makeComp([])
    await expect(comp.loadComparisonProject('pX', '子X')).resolves.toBeUndefined()
    expect(comp.errors.value.get('pX')).toBe('加载失败')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P4: Cache Consistency — **Validates: Requirements 6**
// ═══════════════════════════════════════════════════════════════════════════════
describe('P4 Cache Consistency', () => {
  it('P4: 会话缓存命中避免重复请求；invalidateCache 后强制重取', async () => {
    getTrialBalanceMock.mockResolvedValue([makeRow('1001', 80)])
    const { comp } = makeComp([makeRow('1001', 100)])

    await comp.loadComparisonYear(2024)
    expect(getTrialBalanceMock).toHaveBeenCalledTimes(1)

    // 缓存命中 → 不重取
    await comp.loadComparisonYear(2024)
    expect(getTrialBalanceMock).toHaveBeenCalledTimes(1)

    // 失效缓存 → 重取
    comp.invalidateCache()
    await comp.loadComparisonYear(2024)
    expect(getTrialBalanceMock).toHaveBeenCalledTimes(2)
  })

  it('P4: 当前行变化 → joinedRows 变动额重算（recalc 一致性）', async () => {
    getTrialBalanceMock.mockResolvedValue([makeRow('1001', 80)])
    const { comp, rows } = makeComp([makeRow('1001', 100)])
    await comp.loadComparisonYear(2024)
    let jr = comp.joinedRows.value.find((r) => r.standard_account_code === '1001')!
    expect(jr.current_audited).toBe(100)
    expect(jr.variances['2024'].amount).toBe(20)

    // 模拟 recalc 后当前行改变
    rows.value = [makeRow('1001', 300)]
    await nextTick()
    jr = comp.joinedRows.value.find((r) => r.standard_account_code === '1001')!
    expect(jr.current_audited).toBe(300)
    expect(jr.variances['2024'].amount).toBe(220)
  })

  it('P4(unit): invalidateCache 同时清空 targetData 与缓存', async () => {
    getTrialBalanceMock.mockResolvedValue([makeRow('1001', 80)])
    const { comp } = makeComp([makeRow('1001', 100)])
    await comp.loadComparisonYear(2024)
    expect(comp.joinedRows.value.length).toBeGreaterThan(0)
    comp.invalidateCache()
    // targetData 清空 → 但 targets 仍在（column header 保留），无对比数据
    expect(comp.joinedRows.value.every((r) => r.targets['2024'] === null)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 组件层辅助
// ═══════════════════════════════════════════════════════════════════════════════
const EL_STUBS = {
  'el-button': { template: '<button class="el-btn-stub" @click="$emit(\'click\')"><slot/></button>' },
  'el-segmented': { template: '<div class="el-segmented-stub"><slot/></div>' },
  'el-select': { template: '<div class="el-select-stub"><slot/></div>' },
  'el-option': { template: '<div class="el-option-stub"><slot/></div>' },
  'el-tag': { template: '<span class="el-tag-stub"><slot/></span>' },
  'el-input': { template: '<div class="el-input-stub"></div>' },
  // el-table/column 不渲染 scoped 行插槽（真实 el-table 按 :data 逐行注入 row；
  // 朴素 <slot/> 会以 undefined row 触发列模板 → 渲染错误。测试断言走 vm + 工具栏/空态 HTML，
  // 不依赖表体 DOM，故 stub 为空节点。）
  'el-table': { template: '<div class="el-table-stub"></div>' },
  'el-table-column': { template: '<div class="el-tcol-stub"></div>' },
  'el-empty': { props: ['description'], template: '<div class="el-empty-stub">{{ description }}</div>' },
}

function mountView(props: Record<string, any>) {
  return mount(TbComparisonView as any, {
    props: { projectId: 'proj-current', year: 2025, currentRows: [], ...props },
    global: { stubs: EL_STUBS },
  })
}

// ═══════════════════════════════════════════════════════════════════════════════
// P5: Column Limit (max 5) — **Validates: Requirements 5**
// ═══════════════════════════════════════════════════════════════════════════════
describe('P5 Column Limit (跨项目最多 5 个对比目标)', () => {
  it('P5: 连续添加 6 个子公司 → targets 上限锁定为 5', async () => {
    getTrialBalanceMock.mockResolvedValue([makeRow('1001', 10)])
    const wrapper = mountView({ initialMode: 'cross_project' })
    await flushPromises()

    for (let i = 1; i <= 6; i++) {
      ;(wrapper.vm as any).selectedProject = { id: `p${i}`, name: `子${i}` }
      ;(wrapper.vm as any).onAddProject()
      await flushPromises()
    }

    expect((wrapper.vm as any).comparison.targets.value.length).toBe(5)
    // 第 6 个（p6）未被加入
    expect((wrapper.vm as any).comparison.targets.value.some((t: any) => t.key === 'p6')).toBe(false)
    // 达上限提示渲染
    expect(wrapper.html()).toContain('最多对比5个')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P6: Export Correctness — **Validates: Requirements 3**
// ═══════════════════════════════════════════════════════════════════════════════
describe('P6 Export Correctness (导出含全部对比列 + 变动列)', () => {
  it('P6: 导出表头包含 科目编码/科目名称/本年审定 + 每个目标的 审定/变动额/变动率(%)', async () => {
    getTrialBalanceMock.mockResolvedValue([makeRow('1001', 80, '现金')])
    const wrapper = mountView({ currentRows: [makeRow('1001', 100, '现金')], initialMode: 'cross_year' })
    await flushPromises()

    // 添加一个对比年度
    ;(wrapper.vm as any).selectedYear = 2024
    ;(wrapper.vm as any).onAddYear()
    await flushPromises()
    expect((wrapper.vm as any).comparison.targets.value.length).toBe(1)

    await (wrapper.vm as any).doExport()
    await flushPromises()

    expect(writeFileMock).toHaveBeenCalledTimes(1)
    expect(aoaToSheetMock).toHaveBeenCalledTimes(1)
    const aoa = aoaToSheetMock.mock.calls[0][0] as any[][]
    const headers = aoa[0]
    expect(headers).toContain('科目编码')
    expect(headers).toContain('科目名称')
    expect(headers).toContain('本年审定')
    expect(headers).toContain('2024年 审定')
    expect(headers).toContain('变动额')
    expect(headers).toContain('变动率(%)')
    // 数据区含该科目行
    const codes = aoa.slice(1).map((r) => r[0])
    expect(codes).toContain('1001')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P7: Zero Regression — **Validates: Requirements 8**
// ═══════════════════════════════════════════════════════════════════════════════
describe('P7 Zero Regression (对比为 opt-in，无目标时惰性无副作用)', () => {
  it('P7: 无对比目标 → 渲染空态、不触发任何 trial-balance 请求、可返回', async () => {
    const wrapper = mountView({ currentRows: [makeRow('1001', 100)] })
    await flushPromises()

    // opt-in：挂载后无对比目标时不加载任何对比数据
    expect(getTrialBalanceMock).not.toHaveBeenCalled()
    expect((wrapper.vm as any).comparison.joinedRows.value.length).toBe(0)
    // 空态提示
    expect(wrapper.html()).toContain('请选择对比目标')

    // 返回按钮 → emit close（现有工具栏动作可用）
    await wrapper.find('button.el-btn-stub').trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('P7(unit): composable 构造即惰性 — 不请求，joinedRows 为空', () => {
    const { comp } = makeComp([makeRow('1001', 100), makeRow('1002', 50)])
    expect(getTrialBalanceMock).not.toHaveBeenCalled()
    expect(comp.joinedRows.value).toEqual([])
  })
})
