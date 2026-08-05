/**
 * A13 错报类型通路守卫（sampling-compliance-closure Wave 1 Task 9）
 *
 * 背景：`useA13MisstatementBridge` 此前把 `misstatement_type` 硬编码为 `'factual'`，
 * PG enum 的 `judgmental` / `projected` 两值全库零使用 → CAS 1314 算出的推断错报
 * 无法进入错报汇总，CAS 1251 要求的三类分别汇总评价无从做起。
 *
 * 本文件锁定：新增类型维度后既有 ~35 个推送点行为**逐字节不变**（缺省 factual），
 * 且非法取值不会把整批推送打掉。
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4
 * Properties: Property 6, Property 9
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  normalizeMisstatementPushPayload,
  normalizeMisstatementType,
  MISSTATEMENT_TYPES,
  type MisstatementTypeValue,
} from '@/composables/useA13MisstatementBridge'

// ─── REPO_ROOT：哨兵文件向上查找（禁写死回退级数） ──────────────────────────

function findRepoRoot(): string {
  // 哨兵必须是**具体文件**：目录名在多层同时存在时会提前停下（平台已有踩坑）
  const SENTINEL = join('backend', 'app', 'routers', 'voucher_sampling.py')
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i++) {
    try {
      readFileSync(join(dir, SENTINEL))
      return dir
    } catch {
      const parent = resolve(dir, '..')
      if (parent === dir) break
      dir = parent
    }
  }
  throw new Error('未找到仓库根（哨兵 backend/app/routers/voucher_sampling.py）')
}

const REPO_ROOT = findRepoRoot()

// ─── normalizeMisstatementType ───────────────────────────────────────────────

describe('normalizeMisstatementType', () => {
  it('三个合法值原样返回', () => {
    for (const t of MISSTATEMENT_TYPES) {
      expect(normalizeMisstatementType(t)).toBe(t)
    }
  })

  it('缺失 / 非法 / 非字符串一律回退 factual（不透传，避免后端 enum 拒绝整批）', () => {
    const bad: unknown[] = [
      undefined, null, '', 'FACTUAL', 'factual ', 'unknown', 0, 1, true, {}, [], NaN,
    ]
    for (const v of bad) {
      expect(normalizeMisstatementType(v)).toBe('factual')
    }
  })

  it('PBT：输出恒在取值域内', () => {
    fc.assert(
      fc.property(fc.anything(), (v) => {
        const out = normalizeMisstatementType(v)
        expect(MISSTATEMENT_TYPES).toContain(out)
      }),
      { numRuns: 200 },
    )
  })
})

// ─── Property 6：缺省等价性（既有四形态零回归） ──────────────────────────────

describe('Property 6 — 既有载荷形态缺省 factual', () => {
  it('形态A items[]', () => {
    const drafts = normalizeMisstatementPushPayload({
      items: [
        { wpCode: 'D4', description: '收入跨期', accountName: '营业收入', debitAmount: 0, creditAmount: 5000 },
        { wpCode: 'D4', description: '成本跨期', debitAmount: 3000, creditAmount: 0 },
      ],
    })
    expect(drafts).toHaveLength(2)
    expect(drafts.every((d) => d.misstatementType === 'factual')).toBe(true)
  })

  it('形态B wpCode+entries[]', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'K9', accountCode: '6602',
      entries: [{ description: '费用跨期', debitAmount: 1200, creditAmount: 0 }],
    })
    expect(drafts[0].misstatementType).toBe('factual')
  })

  it('形态C items[{voucherNo, amount}]', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'I2', accountCode: '1301', source: 'I2-9',
      items: [{ voucherNo: 'V-77', amount: 800, description: '在建工程' }],
    })
    expect(drafts[0].misstatementType).toBe('factual')
  })

  it('形态D 扁平单行', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'K13', accountCode: '6711', amount: 500, description: '营业外支出',
    })
    expect(drafts[0].misstatementType).toBe('factual')
  })

  it('PBT：任意不含类型字段的载荷，输出恒为 factual', () => {
    const rowArb = fc.record({
      wpCode: fc.string({ maxLength: 6 }),
      description: fc.string({ maxLength: 12 }),
      amount: fc.integer({ min: 1, max: 10 ** 6 }),
    })
    fc.assert(
      fc.property(fc.array(rowArb, { minLength: 1, maxLength: 5 }), (items) => {
        const drafts = normalizeMisstatementPushPayload({ items })
        expect(drafts.every((d) => d.misstatementType === 'factual')).toBe(true)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── 类型优先级：行级 > 顶层 > factual ───────────────────────────────────────

describe('类型优先级', () => {
  it('行级 misstatementType 生效', () => {
    const drafts = normalizeMisstatementPushPayload({
      items: [{ wpCode: 'D2', description: 'x', amount: 100, misstatementType: 'projected' }],
    })
    expect(drafts[0].misstatementType).toBe('projected')
  })

  it('行级 snake_case 别名生效', () => {
    const drafts = normalizeMisstatementPushPayload({
      items: [{ wpCode: 'D2', description: 'x', amount: 100, misstatement_type: 'judgmental' }],
    })
    expect(drafts[0].misstatementType).toBe('judgmental')
  })

  it('顶层类型下沉到行', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'D2', misstatementType: 'projected',
      items: [{ description: 'a', amount: 100 }, { description: 'b', amount: 200 }],
    })
    expect(drafts.map((d) => d.misstatementType)).toEqual(['projected', 'projected'])
  })

  it('行级覆盖顶层', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'D2', misstatementType: 'projected',
      items: [
        { description: 'a', amount: 100, misstatementType: 'factual' },
        { description: 'b', amount: 200 },
      ],
    })
    expect(drafts.map((d) => d.misstatementType)).toEqual(['factual', 'projected'])
  })

  it('扁平单行 + 顶层类型', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'D0', amount: 300, description: '函证差异', misstatement_type: 'projected',
    })
    expect(drafts[0].misstatementType).toBe('projected')
  })

  it('非法类型不污染其他字段', () => {
    const drafts = normalizeMisstatementPushPayload({
      items: [{ wpCode: 'D2', description: 'x', amount: 100, misstatementType: 'made-up' }],
    })
    expect(drafts[0].misstatementType).toBe('factual')
    expect(drafts[0].amount).toBe(100)
    expect(drafts[0].description).toBe('x')
  })
})

// ─── Property 9：去重不跨类型互吞 ───────────────────────────────────────────

describe('Property 9 — 去重 hash 含类型维度', () => {
  it('同 wpCode/描述/金额的 factual 与 projected 是两笔不同错报', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'D2', accountCode: '1122',
      items: [
        { description: '同款描述', amount: 1000, misstatementType: 'factual' },
        { description: '同款描述', amount: 1000, misstatementType: 'projected' },
      ],
    })
    expect(drafts).toHaveLength(2)
    // 去重键必须能区分二者（bridge 内 draftHash 的字段集）
    const hash = (d: typeof drafts[number]) =>
      `${d.wpCode}|${d.description}|${d.amount}|${d.accountCode ?? ''}|${d.misstatementType}`
    expect(new Set(drafts.map(hash)).size).toBe(2)
  })

  it('反向自检：不含类型的旧 hash 会把两者判为同一笔（证明类型维度必要）', () => {
    const drafts = normalizeMisstatementPushPayload({
      wpCode: 'D2', accountCode: '1122',
      items: [
        { description: '同款描述', amount: 1000, misstatementType: 'factual' },
        { description: '同款描述', amount: 1000, misstatementType: 'projected' },
      ],
    })
    const legacyHash = (d: typeof drafts[number]) =>
      `${d.wpCode}|${d.description}|${d.amount}|${d.accountCode ?? ''}`
    expect(new Set(drafts.map(legacyHash)).size).toBe(1) // 旧实现会吞掉一笔
  })
})

// ─── 源码级：桥不得再硬编码 factual；类型域与 PG enum 对齐 ──────────────────

describe('源码级守卫', () => {
  const bridgeSrc = readFileSync(
    join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'composables', 'useA13MisstatementBridge.ts'),
    'utf-8',
  )

  function stripComments(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
  }

  it('stripComments 自检（原文确实含被禁字样的说明注释）', () => {
    expect(bridgeSrc).toContain("硬编码")
    expect(stripComments(bridgeSrc)).not.toContain('硬编码')
  })

  it('createMisstatement 不得再传字面量 factual', () => {
    const code = stripComments(bridgeSrc)
    expect(code).not.toMatch(/misstatement_type:\s*'factual'/)
    expect(code).toMatch(/misstatement_type:\s*d\.misstatementType/)
  })

  it('类型取值域与 PG enum misstatement_type 逐字对齐', () => {
    // PG: CREATE TYPE misstatement_type AS ENUM ('factual','judgmental','projected')
    expect([...MISSTATEMENT_TYPES]).toEqual(['factual', 'judgmental', 'projected'])
  })

  it('A13 错报汇总页的类型下拉已含推断错报（否则手工无法录入该类型）', () => {
    const viewSrc = readFileSync(
      join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'views', 'Misstatements.vue'),
      'utf-8',
    )
    for (const t of MISSTATEMENT_TYPES) {
      expect(viewSrc).toContain(`value="${t}"`)
    }
  })

  it('抽凭引擎推送的类型是 projected（源码级，防日后被改回 factual）', () => {
    const src = readFileSync(
      join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
        'composables', 'useVoucherSampling.ts'),
      'utf-8',
    )
    const code = stripComments(src)
    expect(code).toMatch(/misstatementType:\s*'projected'/)
  })
})

// 类型断言（编译期）：确保导出类型可用
const _t: MisstatementTypeValue = 'projected'
void _t
