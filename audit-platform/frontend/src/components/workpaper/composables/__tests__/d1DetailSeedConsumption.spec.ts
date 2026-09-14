/**
 * D1 四表库 seed 消费契约 — useD1DetailCategory / useD1BadDebt
 *
 * Spec: .kiro/specs/d1-four-table-extraction-formula-wiring/
 * Task: 2.3
 * Requirements: 7.3
 * Properties: Property 2（手工优先）
 *
 * 背景链路（三段，缺一段 seed 就静默不生效）：
 *   后端 `d1_detail_seed.seed_d1_detail_rows` transient 写入 render-config 的
 *   `responses_snapshot`（不落库）
 *     → 宿主 `GtD1NotesReceivable.selfLoad()` 把 snapshot 整体灌进 `allResponses` Map
 *     → 本文件被测的两个 composable 从 `allResponses.get(锚点)?.remark` 反序列化
 *
 * 本文件的两层断言（缺第 2 层就退化为「自己造 fixture 自己解析」的镜像测试）：
 *   1. **消费层**：以后端真实输出形态作 fixture，断言 composable 正确加载 + roll-forward
 *      守恒（期末未审 = 期初 + 增 − 减），且已有持久化时不被 seed 顶掉（Property 2）。
 *   2. **跨语言字段契约层**：直接读后端 `d1_detail_seed.py` 源码，断言其锚点常量与行
 *      dict 键集 **逐字等于** 前端反序列化读取的字段集。字段名跨 Python/TS 边界漂移
 *      时 mypy、vue-tsc、vitest 全都查不出 —— 只会表现为「seed 跑了但界面全 0」。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { useD1DetailCategory } from '../useD1DetailCategory'
import { useD1BadDebt } from '../useD1BadDebt'
import type { ChecklistResponse } from '../useD1FormData'

// 在组件外实例化 composable 时屏蔽 onBeforeUnmount 生命周期告警（仓库既有约定）
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return { ...actual, onBeforeUnmount: vi.fn() }
})

// ─── 锚点（与后端 d1_detail_seed.py 的 *_ANCHOR 常量对应，由 Group C 逐字锁死）───

const CAT_ROWS_KEY = 'D1-cat-rows'
const BD_INDIVIDUAL_KEY = 'D1-bd-individual-rows'
const BD_PORTFOLIO_KEY = 'D1-bd-portfolio-rows'

// ─── 前端反序列化实际读取的字段集（改 composable 必须同步改这里 + 后端）──────────

/** `useD1DetailCategory.loadFromResponses` 逐字读取的字段 */
const FE_CATEGORY_ROW_FIELDS = [
  'rowId', 'category', 'isFixed',
  'priorUnadjusted', 'priorAje', 'priorRje',
  'currentIncrease', 'currentDecrease',
  'currentAje', 'currentRje',
] as const

/** `useD1BadDebt.loadRows` 逐字读取的字段 */
const FE_BAD_DEBT_ROW_FIELDS = [
  'rowId', 'category', 'label', 'isSubRow',
  'priorUnadjusted', 'priorAje', 'priorRje',
  'currentProvision', 'currentRecovery', 'currentReversal',
  'currentWriteOff', 'currentOther',
  'currentAje', 'currentRje',
] as const

// ─── 后端真实 seed 输出 fixture ───────────────────────────────────────────────
//
// 取自 spec Wave 4.4 对真实项目（0ec33ac9…/2025，wp 68c7740e…）跑 render 的实测值：
// tb 1121 叶子 银行承兑 12,460,611.29 / 商业承兑 7,748,586.89 / 信用证 0，
// 合计 = tb 1121 期末 20,209,198.18；1231.01 坏账 期初 3,037,132.25 → 期末 1,162,288.03。
// 映射口径见后端 build_d1_category_rows_from_tb：
//   priorUnadjusted=opening / currentIncrease=debit / currentDecrease=credit

const TB_BANK = { opening: 3_000_000, debit: 12_460_611.29, credit: 3_000_000 }
const TB_COMMERCIAL = { opening: 1_000_000, debit: 7_748_586.89, credit: 1_000_000 }
/** 信用证：本期有发生额但期末为 0 —— 后端只在 期初/借/贷 三者全零时才跳过，故此行保留 */
const TB_LC = { opening: 0, debit: 500_000, credit: 500_000 }

const TB_1121_CLOSING_TOTAL = 20_209_198.18

/** 后端 seed 的 D1-cat-rows JSON（字段名与顺序即后端 dict 字面量） */
function backendSeededCategoryRows() {
  const mk = (
    rowId: string,
    category: string,
    isFixed: boolean,
    tb: { opening: number; debit: number; credit: number },
  ) => ({
    rowId,
    category,
    isFixed,
    priorUnadjusted: tb.opening,
    priorAje: 0,
    priorRje: 0,
    currentIncrease: tb.debit,
    currentDecrease: tb.credit,
    currentAje: 0,
    currentRje: 0,
  })
  return [
    mk('fixed-bank', '银行承兑汇票', true, TB_BANK),
    mk('fixed-commercial', '商业承兑汇票', true, TB_COMMERCIAL),
    mk('dynamic-tb-1', '信用证', false, TB_LC),
  ]
}

/** 后端 seed 的 D1-bd-portfolio-rows JSON（净减 → 记入 currentReversal） */
function backendSeededPortfolioRows(opening: number, closing: number) {
  const net = closing - opening
  return [{
    rowId: 'fixed-portfolio',
    category: 'portfolio',
    label: '按组合计提',
    isSubRow: false,
    priorUnadjusted: opening,
    priorAje: 0,
    priorRje: 0,
    currentProvision: net >= 0 ? net : 0,
    currentRecovery: 0,
    currentReversal: net < 0 ? -net : 0,
    currentWriteOff: 0,
    currentOther: 0,
    currentAje: 0,
    currentRje: 0,
  }]
}

// ─── 实例化辅助 ───────────────────────────────────────────────────────────────

function makeResponses(seed: Record<string, unknown> = {}) {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  for (const [key, value] of Object.entries(seed)) {
    allResponses.value.set(key, {
      item_id: key,
      conclusion: null,
      remark: typeof value === 'string' ? value : JSON.stringify(value),
    })
  }
  return allResponses
}

function mountCategory(seed: Record<string, unknown> = {}) {
  const allResponses = makeResponses(seed)
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const api = useD1DetailCategory({
    allResponses,
    wpId: ref('test-wp'),
    projectId: ref('test-proj'),
    saveImmediate,
    isReadonly: ref(false),
  } as any)
  return { api, allResponses, saveImmediate }
}

function mountBadDebt(seed: Record<string, unknown> = {}, eclTestTotal = 0) {
  const allResponses = makeResponses(seed)
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const api = useD1BadDebt({
    allResponses,
    wpId: ref('test-wp'),
    projectId: ref('test-proj'),
    saveImmediate,
    isReadonly: ref(false),
    eclTestTotal: ref(eclTestTotal),
  } as any)
  return { api, allResponses, saveImmediate }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Group A — useD1DetailCategory 消费 D1-2 原值 seed
// ═══════════════════════════════════════════════════════════════════════════════

describe('D1 seed 消费: useD1DetailCategory（D1-2 原值明细）', () => {
  /** **Validates: Requirements 7.3** */
  it('无持久化时 seed 就位 → 三行全部加载且种类名正确', () => {
    const { api } = mountCategory({ [CAT_ROWS_KEY]: backendSeededCategoryRows() })

    expect(api.rows.value).toHaveLength(3)
    expect(api.rows.value.map(r => r.rowId)).toEqual([
      'fixed-bank', 'fixed-commercial', 'dynamic-tb-1',
    ])
    expect(api.rows.value.map(r => r.category)).toEqual([
      '银行承兑汇票', '商业承兑汇票', '信用证',
    ])
    // 固定行/动态行标记随 seed 保留（动态行可被审计师删除，固定行不可）
    expect(api.rows.value.map(r => r.isFixed)).toEqual([true, true, false])
  })

  it('每行 roll-forward 守恒：期末未审 = 期初 + 借 − 贷 = tb 期末', () => {
    const { api } = mountCategory({ [CAT_ROWS_KEY]: backendSeededCategoryRows() })
    const byId = new Map(api.rows.value.map(r => [r.rowId, r]))

    for (const [rowId, tb] of [
      ['fixed-bank', TB_BANK],
      ['fixed-commercial', TB_COMMERCIAL],
      ['dynamic-tb-1', TB_LC],
    ] as const) {
      const row = byId.get(rowId)!
      expect(row.priorAudited).toBeCloseTo(tb.opening, 2)
      expect(row.currentUnadjusted).toBeCloseTo(tb.opening + tb.debit - tb.credit, 2)
      // AJE/RJE 均为 0 → 审定数应等于未审数（seed 不预设调整）
      expect(row.currentAudited).toBeCloseTo(row.currentUnadjusted, 2)
    }
  })

  it('小计期末 = tb 1121 期末合计（审定表取数的上游口径）', () => {
    const { api } = mountCategory({ [CAT_ROWS_KEY]: backendSeededCategoryRows() })
    expect(api.subtotalRow.value.currentUnadjusted).toBeCloseTo(TB_1121_CLOSING_TOTAL, 2)
  })

  /**
   * **Validates: Property 2（手工优先）**
   *
   * 后端 `_has_persisted` 在锚点已有非空 remark 时跳过 seed，故运行态 Map 里只会
   * 是持久化值。这里断言「同一锚点」是唯一真源 —— 若哪天前端改成从 render-config
   * 另一个键读 seed，就会出现双真源、手工值被 seed 顶掉，此断言即失效告警。
   */
  it('已有持久化时加载持久化值，不被 seed 顶掉（同锚点单一真源）', () => {
    const manual = [{
      rowId: 'fixed-bank',
      category: '银行承兑汇票（审计师改名）',
      isFixed: true,
      priorUnadjusted: 111,
      priorAje: 0,
      priorRje: 0,
      currentIncrease: 222,
      currentDecrease: 0,
      currentAje: 0,
      currentRje: 0,
    }]
    const { api } = mountCategory({ [CAT_ROWS_KEY]: manual })

    const bank = api.rows.value.find(r => r.rowId === 'fixed-bank')!
    expect(bank.category).toBe('银行承兑汇票（审计师改名）')
    expect(bank.currentUnadjusted).toBeCloseTo(333, 2)
    // seed 的实测金额不得出现
    expect(api.subtotalRow.value.currentUnadjusted).not.toBeCloseTo(TB_1121_CLOSING_TOTAL, 2)
  })

  it('seed 只含动态行时前端补齐两个固定行且不破坏 seed 行', () => {
    // 全零固定叶子被后端跳过的情形（客户只用信用证科目记票据）
    const seedOnlyDynamic = backendSeededCategoryRows().filter(r => !r.isFixed)
    const { api } = mountCategory({ [CAT_ROWS_KEY]: seedOnlyDynamic })

    const ids = api.rows.value.map(r => r.rowId)
    expect(ids).toContain('fixed-bank')
    expect(ids).toContain('fixed-commercial')
    expect(ids).toContain('dynamic-tb-1')
    // 补齐的固定行为空行，不凭空造金额
    const bank = api.rows.value.find(r => r.rowId === 'fixed-bank')!
    expect(bank.currentUnadjusted).toBe(0)
    // seed 动态行金额完好
    const lc = api.rows.value.find(r => r.rowId === 'dynamic-tb-1')!
    expect(lc.currentUnadjusted).toBeCloseTo(TB_LC.opening + TB_LC.debit - TB_LC.credit, 2)
  })

  it('PBT: 任意 tb 叶子集 seed → 小计期末 = Σ 各叶子期末', () => {
    const leafArb = fc.record({
      opening: fc.double({ min: -1e7, max: 1e7, noNaN: true, noDefaultInfinity: true }),
      debit: fc.double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true }),
      credit: fc.double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true }),
    })

    fc.assert(
      fc.property(fc.array(leafArb, { minLength: 1, maxLength: 6 }), (leaves) => {
        const rows = leaves.map((tb, i) => ({
          rowId: `dynamic-tb-${i + 1}`,
          category: `叶子${i + 1}`,
          isFixed: false,
          priorUnadjusted: tb.opening,
          priorAje: 0,
          priorRje: 0,
          currentIncrease: tb.debit,
          currentDecrease: tb.credit,
          currentAje: 0,
          currentRje: 0,
        }))
        const { api } = mountCategory({ [CAT_ROWS_KEY]: rows })

        const expected = leaves.reduce((s, tb) => s + tb.opening + tb.debit - tb.credit, 0)
        // 前端会补两个全零固定行，不影响合计
        expect(api.subtotalRow.value.currentUnadjusted).toBeCloseTo(expected, 2)
      }),
      { numRuns: 50 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Group B — useD1BadDebt 消费 D1-4 坏账 seed
// ═══════════════════════════════════════════════════════════════════════════════

describe('D1 seed 消费: useD1BadDebt（D1-4 坏账准备）', () => {
  /** **Validates: Requirements 7.3** */
  it('净减少 seed 成本期转回 → 期末守恒 = tb 1231.01 期末', () => {
    const opening = 3_037_132.25
    const closing = 1_162_288.03
    const { api } = mountBadDebt({
      [BD_PORTFOLIO_KEY]: backendSeededPortfolioRows(opening, closing),
    })

    expect(api.portfolioRows.value).toHaveLength(1)
    const row = api.portfolioRows.value[0]
    expect(row.rowId).toBe('fixed-portfolio')
    expect(row.label).toBe('按组合计提')
    expect(row.priorUnadjusted).toBeCloseTo(opening, 2)
    expect(row.currentReversal).toBeCloseTo(opening - closing, 2)
    expect(row.currentProvision).toBe(0)
    expect(row.currentUnadjusted).toBeCloseTo(closing, 2)
  })

  it('净增加 seed 成本期计提 → 期末守恒', () => {
    const opening = 1_000_000
    const closing = 1_500_000
    const { api } = mountBadDebt({
      [BD_PORTFOLIO_KEY]: backendSeededPortfolioRows(opening, closing),
    })

    const row = api.portfolioRows.value[0]
    expect(row.currentProvision).toBeCloseTo(closing - opening, 2)
    expect(row.currentReversal).toBe(0)
    expect(row.currentUnadjusted).toBeCloseTo(closing, 2)
  })

  /**
   * 宁缺勿造（R2.3）：tb 不提供单项/组合拆分，后端只 seed 组合行、individual 返回空，
   * 故按单项区必须保持默认空行 —— 不得把组合金额挪到单项，也不得凭空拆分。
   */
  it('按单项区保持默认空行（后端不 seed individual）', () => {
    const { api } = mountBadDebt({
      [BD_PORTFOLIO_KEY]: backendSeededPortfolioRows(3_037_132.25, 1_162_288.03),
    })

    expect(api.individualRows.value).toHaveLength(1)
    expect(api.individualRows.value[0].rowId).toBe('fixed-individual')
    expect(api.individualRows.value[0].currentUnadjusted).toBe(0)
  })

  it('小计 = 单项 + 组合（seed 后可直接与 D1-15 ECL 比差异）', () => {
    const opening = 3_037_132.25
    const closing = 1_162_288.03
    const { api } = mountBadDebt(
      { [BD_PORTFOLIO_KEY]: backendSeededPortfolioRows(opening, closing) },
      closing,
    )

    expect(api.subtotalRow.value.currentAudited).toBeCloseTo(closing, 2)
    // eclTestTotal 传入等额 → 无差异告警
    expect(api.eclDifference.value).toBeCloseTo(0, 2)
  })

  /** **Validates: Property 2（手工优先）** */
  it('已有持久化时加载持久化值，不被 seed 顶掉', () => {
    const manual = [{
      rowId: 'fixed-portfolio',
      category: 'portfolio',
      label: '按组合计提',
      isSubRow: false,
      priorUnadjusted: 500,
      priorAje: 0,
      priorRje: 0,
      currentProvision: 100,
      currentRecovery: 0,
      currentReversal: 0,
      currentWriteOff: 0,
      currentOther: 0,
      currentAje: 0,
      currentRje: 0,
    }]
    const { api } = mountBadDebt({ [BD_PORTFOLIO_KEY]: manual })

    const row = api.portfolioRows.value[0]
    expect(row.priorUnadjusted).toBeCloseTo(500, 2)
    expect(row.currentUnadjusted).toBeCloseTo(600, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Group C — 跨语言字段契约（读后端 d1_detail_seed.py 源码）
// ═══════════════════════════════════════════════════════════════════════════════

describe('D1 seed 跨语言字段契约（后端 d1_detail_seed.py ↔ 前端反序列化）', () => {
  const SEED_PY_PATH = resolve(
    process.cwd(),
    '../../backend/app/services/d_cycle_extraction/d1_detail_seed.py',
  )
  const py = readFileSync(SEED_PY_PATH, 'utf-8')

  /** 抽取 `NAME = "value"` 形式的模块级字符串常量 */
  function pyConst(name: string): string | null {
    const m = py.match(new RegExp(`^${name}\\s*=\\s*"([^"]+)"`, 'm'))
    return m?.[1] ?? null
  }

  /**
   * 抽取某函数体内 dict 字面量的键（`"key":` 形式；`lf.get("x")` 与 docstring 里的
   * `{"code","name"}` 不带冒号故不误命中）。
   *
   * 函数体边界必须同时认 `def` 与 `async def` —— 只认 `\ndef ` 时 body 会溢出到下一个
   * `async def`，把它的 dict 键一并吞进来（本文件首版即因此把 `_fetch_leaves` 的
   * code/name/opening/closing/debit/credit 误算成坏账行字段，由下方自检钉死）。
   */
  function pyDictKeysIn(funcName: string): string[] {
    const start = py.indexOf(`def ${funcName}(`)
    if (start === -1) return []
    const rest = py.slice(start + 1)
    const nextDef = rest.search(/\n(?:async\s+)?def /)
    const body = nextDef === -1 ? rest : rest.slice(0, nextDef)
    return [...body.matchAll(/"(\w+)":/g)].map(m => m[1])
  }

  it('反向自检：后端源码已读到且抽取器有效（防正则失效导致断言空转）', () => {
    expect(py.length).toBeGreaterThan(1000)
    expect(py).toContain('def build_d1_category_rows_from_tb')
    expect(py).toContain('def build_d1_bad_debt_rows_from_tb')
    expect(pyDictKeysIn('build_d1_category_rows_from_tb').length).toBeGreaterThan(0)
    expect(pyDictKeysIn('build_d1_bad_debt_rows_from_tb').length).toBeGreaterThan(0)
    // 抽取器不得把 `lf.get("opening")` 这类非键字符串当成 dict 键
    expect(pyDictKeysIn('build_d1_category_rows_from_tb')).not.toContain('opening')
    // 函数体边界不得溢出到后续 `async def _fetch_leaves`（其 dict 键为 code/name/…）
    for (const leaked of ['code', 'name', 'opening', 'closing', 'debit', 'credit']) {
      expect(pyDictKeysIn('build_d1_bad_debt_rows_from_tb')).not.toContain(leaked)
    }
  })

  it('锚点常量与前端 storage key 逐字一致', () => {
    expect(pyConst('CAT_ROWS_ANCHOR')).toBe(CAT_ROWS_KEY)
    expect(pyConst('BD_INDIVIDUAL_ANCHOR')).toBe(BD_INDIVIDUAL_KEY)
    expect(pyConst('BD_PORTFOLIO_ANCHOR')).toBe(BD_PORTFOLIO_KEY)
  })

  it('取数科目前缀符合实证编码（1121 原值 / 1231 坏账·名称含应收票据）', () => {
    expect(pyConst('_GROSS_PREFIX')).toBe('1121')
    expect(pyConst('_BAD_DEBT_PREFIX')).toBe('1231')
    expect(pyConst('_BAD_DEBT_NAME_HINT')).toBe('应收票据')
  })

  it('原值行 dict 键集 === 前端 useD1DetailCategory 反序列化字段集', () => {
    const backend = new Set(pyDictKeysIn('build_d1_category_rows_from_tb'))
    const frontend = new Set<string>(FE_CATEGORY_ROW_FIELDS)

    expect([...backend].sort()).toEqual([...frontend].sort())
  })

  it('坏账行 dict 键集 === 前端 useD1BadDebt 反序列化字段集', () => {
    const backend = new Set(pyDictKeysIn('build_d1_bad_debt_rows_from_tb'))
    const frontend = new Set<string>(FE_BAD_DEBT_ROW_FIELDS)

    expect([...backend].sort()).toEqual([...frontend].sort())
  })

  it('固定行 rowId 与前端默认行一致（否则 seed 行会与前端补齐的固定行重复）', () => {
    expect(py).toContain('"fixed-bank"')
    expect(py).toContain('"fixed-commercial"')
    expect(py).toContain('"fixed-portfolio"')
    // 组合行标签须与前端 DEFAULT_PORTFOLIO_ROW.label 一致
    expect(py).toContain('"按组合计提"')
  })

  it('seed 为 transient（写 responses_snapshot，不落库）且手工优先', () => {
    // 手工优先判定必须在 seed 之前生效
    expect(py).toContain('def _has_persisted')
    expect(py).toMatch(/not _has_persisted\(\s*responses_snapshot,\s*CAT_ROWS_ANCHOR/)
    expect(py).toMatch(/not _has_persisted\(\s*responses_snapshot,\s*BD_PORTFOLIO_ANCHOR/)
    // 不得出现落库写入
    expect(py).not.toMatch(/db\.(add|commit)\(/)
  })
})
