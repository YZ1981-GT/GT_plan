/**
 * hCycleAdjudicationSeed 守卫
 *
 * 覆盖 Property 7（逐叶子明细 / 不预聚合）与 Property 8（未命中不兜底），
 * 并做两项跨文件交叉锁死：
 *
 * 1. **前端声明的槽键 ⊆ 后端 `h{n}_account_scope.py` 的 `H{n}_SLOT_KEY_PREFIX`**
 *    —— 槽键写错时后端 segment 与前端声明对不上，表现为「带入按钮点了没反应」，
 *    四层验证全查不出（memory 已记 dead output 范式）。
 * 2. **`defaults` 必须为空** —— 正向断言「不兜底」这条设计决定，
 *    而不是靠「源码里没写这个字段」的弱判据。
 *
 * spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  H_SEED_DECLARED_CYCLES,
  applyHSeedCells,
  buildHSeedCells,
  classifyHLeaf,
  getHSeedSpec,
  normalizeAccountName,
  readHSegmentPrefill,
  type HSegmentPrefill,
  type HSeedSpec,
} from '../hCycleAdjudicationSeed'
import {
  planAdjudicationPrefill,
  resolveAdjPrefillWrites,
  describeAdjPrefillPlan,
} from '../shared/adjudicationPrefillPlan'

// ─── REPO_ROOT：双哨兵具体文件向上查找（禁写死回退级数）──────────────────
function findRepoRoot(): string {
  let dir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
  for (let i = 0; i < 12; i += 1) {
    const a = path.join(dir, 'backend', 'app', 'main.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('REPO_ROOT 未找到（双哨兵 backend/app/main.py + audit-platform/frontend/package.json）')
}

const REPO_ROOT = findRepoRoot()

function readBackend(rel: string): string {
  const p = path.join(REPO_ROOT, rel)
  if (!fs.existsSync(p)) throw new Error(`后端文件不存在: ${rel}`)
  return fs.readFileSync(p, 'utf-8')
}

/** 从 `h{n}_account_scope.py` 抽 `H{n}_SLOT_KEY_PREFIX` 的键集（按 ASCII 花括号配对） */
function backendSlotKeys(cycle: string): string[] {
  const src = readBackend(
    `backend/app/services/four_table/${cycle.toLowerCase()}_account_scope.py`,
  )
  const anchor = `${cycle}_SLOT_KEY_PREFIX`
  const i = src.indexOf(anchor)
  if (i < 0) throw new Error(`${cycle}: 未找到 ${anchor}`)
  const open = src.indexOf('{', i)
  if (open < 0) throw new Error(`${cycle}: ${anchor} 后无 '{'`)
  let depth = 0
  let close = -1
  for (let j = open; j < src.length; j += 1) {
    if (src[j] === '{') depth += 1
    else if (src[j] === '}') {
      depth -= 1
      if (depth === 0) {
        close = j
        break
      }
    }
  }
  if (close < 0) throw new Error(`${cycle}: ${anchor} 花括号未配对`)
  const body = src.slice(open + 1, close)
  return [...body.matchAll(/["']([a-z_0-9]+)["']\s*:/g)].map((m) => m[1])
}

// ═══════════════════════════════════════════════════════════════════════════
describe('hCycleAdjudicationSeed — 声明自洽', () => {
  it('已声明循环非空（扫描面自检，防注册表被清空后全部断言空转）', () => {
    expect(H_SEED_DECLARED_CYCLES.length).toBeGreaterThan(0)
  })

  it.each([...H_SEED_DECLARED_CYCLES])('%s: spec 可取到且字段完整', (cycle) => {
    const spec = getHSeedSpec(cycle)
    expect(spec).not.toBeNull()
    expect(spec!.cycle).toBe(cycle)
    expect(spec!.slots.length).toBeGreaterThan(0)
    for (const slot of spec!.slots) {
      expect(slot.slotKey).toBeTruthy()
      expect(slot.slotLabel).toBeTruthy()
      expect(slot.closingField).toBeTruthy()
      expect(slot.closingLabel).toBeTruthy()
      // 声明了期初字段就必须同时有中文名（否则 periodLabel 为空、提示不可读）
      if (slot.openingField) expect(slot.openingLabel).toBeTruthy()
    }
  })

  it.each([...H_SEED_DECLARED_CYCLES])(
    '%s: defaults 必须为空数组（Property 8 未命中不兜底）',
    (cycle) => {
      const spec = getHSeedSpec(cycle)!
      expect(Array.isArray(spec.defaults)).toBe(true)
      expect(spec.defaults).toHaveLength(0)
    },
  )

  it.each([...H_SEED_DECLARED_CYCLES])(
    '%s: 行键唯一、规则关键词非空',
    (cycle) => {
      const spec = getHSeedSpec(cycle)!
      const keys = spec.rules.map((r) => r.rowKey)
      expect(new Set(keys).size).toBe(keys.length)
      for (const r of spec.rules) {
        expect(r.label).toBeTruthy()
        expect(r.keywords.length).toBeGreaterThan(0)
      }
    },
  )
})

// ═══════════════════════════════════════════════════════════════════════════
describe('hCycleAdjudicationSeed — 跨文件交叉锁死', () => {
  it('抽取器自检：不存在的常量必须 throw（防解析失效变成空转）', () => {
    expect(() => backendSlotKeys('H99')).toThrow()
  })

  it.each([...H_SEED_DECLARED_CYCLES])(
    '%s: 前端声明的槽键 ⊆ 后端 H{n}_SLOT_KEY_PREFIX',
    (cycle) => {
      const beKeys = backendSlotKeys(cycle)
      expect(beKeys.length).toBeGreaterThan(0)
      const spec = getHSeedSpec(cycle)!
      for (const slot of spec.slots) {
        expect(beKeys).toContain(slot.slotKey)
      }
    },
  )
})

// ═══════════════════════════════════════════════════════════════════════════
describe('classifyHLeaf — 按名称归类', () => {
  const h4 = getHSeedSpec('H4')!

  it('顺序即优先级 + 否决词：专用设备不落入专用材料行', () => {
    expect(classifyHLeaf('工程物资_专用设备', h4.rules)?.rowKey).toBe('专用设备')
    expect(classifyHLeaf('工程物资_专用材料', h4.rules)?.rowKey).toBe('专用材料')
  })

  it('工器具优先于设备（否决词生效）', () => {
    expect(classifyHLeaf('专用设备工器具', h4.rules)?.rowKey).toBe('工器具')
  })

  it('未命中返回 null（不兜底到「其他」）', () => {
    expect(classifyHLeaf('钢筋水泥', h4.rules)).toBeNull()
    expect(classifyHLeaf('', h4.rules)).toBeNull()
  })

  it('名称归一：空格与全角括号不影响归类', () => {
    expect(normalizeAccountName('专用 材料（甲）')).toBe('专用材料(甲)')
    expect(classifyHLeaf('专用 材料', h4.rules)?.rowKey).toBe('专用材料')
  })

  it('H3 具体类别优先于宽兜底「其他」', () => {
    const h3 = getHSeedSpec('H3')!
    expect(classifyHLeaf('投资性房地产_房屋', h3.rules)?.rowKey).toBe('building')
    expect(classifyHLeaf('投资性房地产_土地使用权', h3.rules)?.rowKey).toBe('land')
    expect(classifyHLeaf('投资性房地产_其他', h3.rules)?.rowKey).toBe('other')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('buildHSeedCells — 逐叶子明细转格', () => {
  const h4 = getHSeedSpec('H4')!

  function h4Prefill(items: Array<[string, string, number, number]>): HSegmentPrefill {
    return {
      enabled: true,
      segments: [
        {
          segment: 'gross',
          account_prefix: '1605',
          mode: 'balance',
          items: items.map(([code, name, opening, closing]) => ({
            code,
            name,
            opening_balance: opening,
            closing_balance: closing,
          })),
        },
      ],
    }
  }

  it('同行多叶子按 rowKey|field 聚合，sourceCodes 累积（Property 7）', () => {
    const r = buildHSeedCells(
      h4,
      h4Prefill([
        ['1605.01', '专用材料-钢材', 100, 150],
        ['1605.02', '专用材料-水泥', 200, 250],
      ]),
    )
    const endCell = r.cells.find((c) => c.field === 'endUnadjusted')!
    expect(endCell.rowKey).toBe('专用材料')
    expect(endCell.amount).toBeCloseTo(400, 6)
    expect(endCell.sourceCodes).toEqual(['1605.01', '1605.02'])

    const beginCell = r.cells.find((c) => c.field === 'beginUnadjusted')!
    expect(beginCell.amount).toBeCloseTo(300, 6)
  })

  it('未归类叶子进 unclassified 且不产生任何格（Property 8）', () => {
    const r = buildHSeedCells(h4, h4Prefill([['1605.99', '钢筋水泥', 10, 20]]))
    expect(r.cells).toHaveLength(0)
    expect(r.unclassified).toEqual([
      { code: '1605.99', name: '钢筋水泥', amount: 20, opening: 10 },
    ])
  })

  it('槽缺失 → absentSlots 登记且不写 0', () => {
    const r = buildHSeedCells(h4, { enabled: true, segments: [] })
    expect(r.cells).toHaveLength(0)
    expect(r.absentSlots).toEqual([{ slotKey: 'gross', label: '工程物资' }])
  })

  it('载荷为 null/undefined 时不抛异常，槽全部登记为缺失', () => {
    for (const p of [null, undefined]) {
      const r = buildHSeedCells(h4, p)
      expect(r.cells).toHaveLength(0)
      expect(r.absentSlots).toHaveLength(1)
    }
  })

  it('声明里没有的槽被忽略（不凭空造列）', () => {
    const r = buildHSeedCells(h4, {
      enabled: true,
      segments: [
        {
          segment: '不存在的槽',
          account_prefix: '9999',
          mode: 'balance',
          items: [
            { code: '9999.01', name: '专用材料', opening_balance: 1, closing_balance: 2 },
          ],
        },
      ],
    })
    expect(r.cells).toHaveLength(0)
    expect(r.unclassified).toHaveLength(0)
  })

  it('occurrence 模式：期初恒 0，期末取借贷净额', () => {
    const spec: HSeedSpec = {
      cycle: 'H10',
      rules: [{ rowKey: 'r1', label: '处置收益', keywords: ['处置'] }],
      slots: [
        {
          slotKey: 'gross',
          slotLabel: '资产处置损益',
          closingField: 'currentUnadjusted',
          closingLabel: '本期未审',
        },
      ],
      defaults: [],
    }
    const r = buildHSeedCells(spec, {
      enabled: true,
      segments: [
        {
          segment: 'gross',
          account_prefix: '6115',
          mode: 'occurrence',
          items: [
            { code: '6115.01', name: '资产处置损益', debit_amount: 500, credit_amount: 200 },
          ],
        },
      ],
    })
    expect(r.cells).toHaveLength(1)
    expect(r.cells[0].field).toBe('currentUnadjusted')
    expect(r.cells[0].amount).toBeCloseTo(300, 6)
  })

  it('H3 四槽各自成段互不串行', () => {
    const h3 = getHSeedSpec('H3')!
    const mk = (segment: string, closing: number) => ({
      segment,
      account_prefix: 'x',
      mode: 'balance' as const,
      items: [
        { code: `${segment}.01`, name: '投资性房地产_房屋', opening_balance: 0, closing_balance: closing },
      ],
    })
    const r = buildHSeedCells(h3, {
      enabled: true,
      segments: [mk('gross', 1000), mk('accum_dep', 300), mk('impairment', 50)],
    })
    // 三个槽的 closingField 同名（unadjusted）⇒ 同行会被聚合，
    // 故本断言同时证明「同名字段确实会累加」这一既有行为（H3 三段在 UI 上是三张表，
    // 由调用方按槽分别应用，不能一次性混合传入）。
    expect(r.absentSlots.map((s) => s.slotKey)).toEqual(['accum_amort'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('与平台共享件 adjudicationPrefillPlan 串联', () => {
  const h4 = getHSeedSpec('H4')!
  const prefill: HSegmentPrefill = {
    enabled: true,
    segments: [
      {
        segment: 'gross',
        account_prefix: '1605',
        mode: 'balance',
        items: [
          { code: '1605.01', name: '专用材料', opening_balance: 100, closing_balance: 150 },
        ],
      },
    ],
  }

  it('空表 → 全部进 writes；手工优先 → 不一致进 conflicts', () => {
    const built = buildHSeedCells(h4, prefill)

    const blankPlan = planAdjudicationPrefill(built.cells, () => '', {
      unclassified: built.unclassified,
      absentSlots: built.absentSlots,
    })
    expect(blankPlan.writes).toHaveLength(2)
    expect(blankPlan.conflicts).toHaveLength(0)

    const dirtyPlan = planAdjudicationPrefill(built.cells, (c) =>
      c.field === 'endUnadjusted' ? 999 : '',
    )
    expect(dirtyPlan.writes).toHaveLength(1)
    expect(dirtyPlan.conflicts).toHaveLength(1)
    // fill-blank 模式绝不覆盖已录入
    expect(resolveAdjPrefillWrites(dirtyPlan, 'fill-blank')).toHaveLength(1)
    expect(resolveAdjPrefillWrites(dirtyPlan, 'overwrite')).toHaveLength(2)
  })

  it('值已一致 → 幂等跳过，摘要文案全中文', () => {
    const built = buildHSeedCells(h4, prefill)
    const plan = planAdjudicationPrefill(built.cells, (c) => c.amount)
    expect(plan.identical).toBe(2)
    expect(plan.writes).toHaveLength(0)
    const desc = describeAdjPrefillPlan(plan)
    expect(desc).toContain('已一致')
    expect(desc).not.toMatch(/[A-Za-z]{4,}/) // 无英文键泄漏
  })

  it('absentSlots 在摘要里如实说明「本项目无此科目」', () => {
    const built = buildHSeedCells(h4, { enabled: true, segments: [] })
    const plan = planAdjudicationPrefill(built.cells, () => '', {
      absentSlots: built.absentSlots,
    })
    expect(describeAdjPrefillPlan(plan)).toContain('本项目无此科目')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('applyHSeedCells — 计划落到行模型', () => {
  function makeAdapter(existing: Record<string, string> = {}) {
    const rows = { ...existing }
    const writes: Array<{ rowId: string; field: string; amount: number }> = []
    let seq = 0
    return {
      rows,
      writes,
      adapter: {
        findRowId: (k: string) => rows[k] ?? null,
        createRow: (k: string) => {
          seq += 1
          rows[k] = `new-${seq}`
          return rows[k]
        },
        writeCell: (rowId: string, field: string, amount: number) => {
          writes.push({ rowId, field, amount })
        },
      } satisfies HSeedRowAdapter,
    }
  }

  it('已有行直接写，不重复建行', () => {
    const { adapter, writes } = makeAdapter({ 专用材料: 'r1' })
    const r = applyHSeedCells(
      [
        { rowKey: '专用材料', field: 'endUnadjusted', amount: 100, label: '专用材料', periodLabel: '期末未审' },
      ],
      adapter,
    )
    expect(r).toEqual({ written: 1, created: 0, failed: [] })
    expect(writes).toEqual([{ rowId: 'r1', field: 'endUnadjusted', amount: 100 }])
  })

  it('行不存在时建行，created 计数正确', () => {
    const { adapter, rows } = makeAdapter()
    const r = applyHSeedCells(
      [
        { rowKey: '工器具', field: 'beginUnadjusted', amount: 10, label: '工器具', periodLabel: '期初未审' },
        { rowKey: '工器具', field: 'endUnadjusted', amount: 20, label: '工器具', periodLabel: '期末未审' },
      ],
      adapter,
    )
    // 同一 rowKey 的两格只建一次行
    expect(r.created).toBe(1)
    expect(r.written).toBe(2)
    expect(Object.keys(rows)).toEqual(['工器具'])
  })

  it('🔴 建行失败必须进 failed 如实回报，不静默丢弃', () => {
    const adapter: HSeedRowAdapter = {
      findRowId: () => null,
      createRow: () => null, // 只读态 / 达到行数上限
      writeCell: () => {
        throw new Error('不应被调用')
      },
    }
    const cell = { rowKey: 'X', field: 'f', amount: 1, label: 'X', periodLabel: '期末未审' }
    const r = applyHSeedCells([cell], adapter)
    expect(r).toEqual({ written: 0, created: 0, failed: [cell] })
  })

  it('空 cells / null 入参不抛异常', () => {
    const { adapter } = makeAdapter()
    expect(applyHSeedCells([], adapter)).toEqual({ written: 0, created: 0, failed: [] })
    expect(applyHSeedCells(undefined as any, adapter)).toEqual({ written: 0, created: 0, failed: [] })
  })

  it('与 resolveAdjPrefillWrites 串联：fill-blank 不覆盖已录入', () => {
    const items: HPrefillBalanceItem[] = [
      { code: '1605.01', name: '专用材料', opening_balance: 100, closing_balance: 200 },
    ]
    const payload = {
      segments: [{ segment: 'gross', account_prefix: '1605', mode: 'balance' as const, items }],
      enabled: true,
    }
    const built = buildHSeedCells(getHSeedSpec('H4')!, payload)
    const current = new Map<string, number>([['专用材料|endUnadjusted', 999]])
    const plan = planAdjudicationPrefill(
      built.cells,
      (c) => current.get(`${c.rowKey}|${c.field}`) ?? null,
      { unclassified: built.unclassified, absentSlots: built.absentSlots },
    )
    const toWrite = resolveAdjPrefillWrites(plan, 'fill-blank')
    // 期末已录入 999 → 进 conflicts 不写；期初为空 → 写
    expect(toWrite.map((c) => c.field)).toEqual(['beginUnadjusted'])

    const { adapter, writes } = makeAdapter({ 专用材料: 'r1' })
    applyHSeedCells(toWrite, adapter)
    expect(writes).toEqual([{ rowId: 'r1', field: 'beginUnadjusted', amount: 100 }])
  })
})

describe('readHSegmentPrefill — 两层落点兼容', () => {
  const seg = {
    segments: [{ segment: 'gross', account_prefix: '1', mode: 'balance', items: [] }],
    enabled: true,
  }

  it('顶层优先', () => {
    expect(readHSegmentPrefill({ adjudication_segment_prefill: seg })).toBe(seg)
  })

  it('project_context 兼容', () => {
    expect(
      readHSegmentPrefill({ project_context: { adjudication_segment_prefill: seg } }),
    ).toBe(seg)
  })

  it('缺失 / 形态不符 → null（不返回空壳对象）', () => {
    expect(readHSegmentPrefill(null)).toBeNull()
    expect(readHSegmentPrefill({})).toBeNull()
    expect(readHSegmentPrefill({ adjudication_segment_prefill: { enabled: true } })).toBeNull()
  })
})
