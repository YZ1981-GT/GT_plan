/**
 * G1R-P2：G1 / G3 的行身份铸造（BP-7 下标派生 + Req 1.3 timestamp 无随机后缀）。
 *
 * spec: g-cycle-single-region-detail-lanes · Task 3（红判据）/ Task 7（修复）
 *       · Requirements 1.3 · Property 2
 *
 * 🔴 **只修 G1/G3 两条**：slice 给六条标了 BP-7，Task 2 按值实测只有 G1/G3 真命中
 * （G10/G11/G12/G13 的 `i+1` 只喂 `seq`、id 生成均带 `Math.random()`）。
 * 四条误标的反证见 `evidence/task2-geometry-and-field-probes.md` §3.2 —— 未伪造缺陷。
 *
 * 判据六组：
 *   ① 缺 id / 纯数字 id（`String(i+1)` 与 `emptyRow('1',1)` 的共同形态）⇒ 重铸
 *   ② `row-<ts>` 形态**保留**（无条件重铸会让每次载入都换身份，比原缺陷更糟）
 *   ③ 同载荷内 id 重复 ⇒ 后来者重铸（`row-${Date.now()}` 同毫秒撞 id 的实证形态）
 *   ④ 铸造后**立即回写** store
 *   ⑤ 新增行 id 带随机后缀：同毫秒连加两行不撞
 *   ⑥ 源码形态防护：两文件不得退回旧写法
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  createMintStats,
  isBareTimestampRowId,
  isOrdinalRowId,
  mintRowIdSuffix,
  resolveStableRowIds,
} from '../g1g3RowIdentity'
import { useG1Detail } from '../useG1Detail'
import { useG3Detail } from '../useG3Detail'

/** 与 `useG1Detail.genRowId` / `useG3Detail.genRowId` 同构的本地铸造器。
 *
 * 🔴 前缀（`g1d`/`g3d`）不再由 `g1g3RowIdentity` 的常量表提供 —— 它必须内联在声明
 * `id: string` 行模型的那个消费方文件里，否则行身份形态无法逐字回源核对。判据侧
 * 照抄同一形态，既验证铸造器契约，也不把前缀重新集中回共享模块。 */
const mintG1 = (): string => `g1d-${mintRowIdSuffix()}`
const mintG3 = (): string => `g3d-${mintRowIdSuffix()}`
import type { ChecklistResponse } from '../useF1FormData'

const G1_KEY = 'G1-2-rows'
const G3_KEY = 'G3-2-detail-rows'

function mkResponses(seed?: Record<string, string>) {
  const map = ref(new Map<string, ChecklistResponse>())
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      // 🔴 G1/G3 的 payload 走 `conclusion` 列（不是 remark）—— Req 1.4 / P3
      map.value.set(k, { item_id: k, conclusion: v, remark: null } as ChecklistResponse)
    }
  }
  return map
}

// ═══════════════════════════════════════════════════════════════════════════
// 组 ①：缺 id / 纯数字 id ⇒ 重铸
// ═══════════════════════════════════════════════════════════════════════════

describe('G1R-P2 ① 纯数字与缺失 id 一律重铸', () => {
  it('识别纯数字 id 为下标派生形态', () => {
    for (const v of ['1', '2', '10', '999']) expect(isOrdinalRowId(v)).toBe(true)
    for (const v of ['g1d-abc', 'row-1727000000000', '', 'a1']) {
      expect(isOrdinalRowId(v)).toBe(false)
    }
  })

  it('缺 id 与纯数字 id 都被重铸，且计数回传', () => {
    const stats = createMintStats()
    const ids = resolveStableRowIds(
      [{}, { id: '1' }, { id: '2' }, { id: 'g1d-keep-me' }],
      mintG1,
      stats,
    )
    expect(stats.minted).toBe(3)
    expect(stats.deduped).toBe(0)
    expect(ids[3]).toBe('g1d-keep-me')
    for (const id of ids.slice(0, 3)) {
      expect(isOrdinalRowId(id)).toBe(false)
      expect(id.startsWith('g1d-')).toBe(true)
    }
    expect(new Set(ids).size).toBe(4)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ②：`row-<ts>` 保留（不无条件重铸）
// ═══════════════════════════════════════════════════════════════════════════

describe('G1R-P2 ② row-<ts> 形态保留', () => {
  it('识别 row-<ts> 形态但不重铸它', () => {
    expect(isBareTimestampRowId('row-1727000000000')).toBe(true)
    expect(isBareTimestampRowId('row-abc')).toBe(false)
    const stats = createMintStats()
    const ids = resolveStableRowIds(
      [{ id: 'row-1727000000000' }, { id: 'row-1727000000001' }],
      mintG3,
      stats,
    )
    expect(stats.minted).toBe(0)
    expect(ids).toEqual(['row-1727000000000', 'row-1727000000001'])
  })

  it('两次载入同一份载荷得到同一批身份（身份稳定性）', () => {
    const payload = [{ id: 'row-1727000000000' }, { id: 'g3d-xyz' }]
    const a = resolveStableRowIds(payload, mintG3)
    const b = resolveStableRowIds(payload, mintG3)
    expect(a).toEqual(b)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ③：同载荷内 id 重复 ⇒ 后来者重铸
// ═══════════════════════════════════════════════════════════════════════════

describe('G1R-P2 ③ 同载荷内撞 id 去重', () => {
  it('两行同 id 时第二行重铸，并计入 deduped', () => {
    const stats = createMintStats()
    const ids = resolveStableRowIds(
      [{ id: 'row-1727000000000' }, { id: 'row-1727000000000' }],
      mintG1,
      stats,
    )
    expect(ids[0]).toBe('row-1727000000000')
    expect(ids[1]).not.toBe(ids[0])
    expect(stats.minted).toBe(1)
    expect(stats.deduped).toBe(1)
  })

  it('产出身份两两不同（无论输入多脏）', () => {
    const dirty = [{}, { id: '1' }, { id: '1' }, { id: 'row-1' }, { id: 'row-1' }, {}]
    const ids = resolveStableRowIds(dirty, mintG1)
    expect(ids).toHaveLength(dirty.length)
    expect(new Set(ids).size).toBe(dirty.length)
    expect(ids.every((v) => v.trim().length > 0)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ⑤：新增行 id 带随机后缀 —— 同毫秒连加不撞
// ═══════════════════════════════════════════════════════════════════════════

describe('G1R-P2 ⑤ 新增行 id 同毫秒不撞', () => {
  it('冻结时钟后连铸 200 个身份仍两两不同', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-27T00:00:00.000Z'))
    try {
      const ids = new Set<string>()
      for (let i = 0; i < 200; i += 1) ids.add(mintG1())
      expect(ids.size).toBe(200)
    } finally {
      vi.useRealTimers()
    }
  })

  it('旧写法 `row-${Date.now()}` 在同毫秒下必然撞 —— 反面样本', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-27T00:00:00.000Z'))
    try {
      const legacy = new Set<string>()
      for (let i = 0; i < 5; i += 1) legacy.add(`row-${Date.now()}`)
      expect(legacy.size).toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('mintRowIdSuffix 在无 crypto.randomUUID 时退到时间戳+随机', () => {
    const original = globalThis.crypto
    try {
      Object.defineProperty(globalThis, 'crypto', { value: {}, configurable: true })
      const ids = new Set<string>()
      for (let i = 0; i < 50; i += 1) ids.add(mintG3())
      expect(ids.size).toBe(50)
    } finally {
      Object.defineProperty(globalThis, 'crypto', { value: original, configurable: true })
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ④：铸造后立即回写 store
// ═══════════════════════════════════════════════════════════════════════════

describe('G1R-P2 ④ 铸造后立即回写', () => {
  it('G1 载入含纯数字 id 的存量载荷后立即 debouncedSave', () => {
    const allResponses = mkResponses({
      [G1_KEY]: JSON.stringify([{ id: '1', securityName: '甲' }, { id: '2', securityName: '乙' }]),
    })
    const debouncedSave = vi.fn()
    const g1 = useG1Detail({ allResponses, debouncedSave, isReadonly: ref(false) })
    expect(debouncedSave).toHaveBeenCalled()
    const [itemId, payload] = debouncedSave.mock.calls.find((c) => c[0] === G1_KEY)!
    expect(itemId).toBe(G1_KEY)
    const written = JSON.parse((payload as { conclusion: string }).conclusion)
    expect(written).toHaveLength(2)
    for (const r of written) expect(isOrdinalRowId(r.id)).toBe(false)
    // 内存里的行身份与回写内容一致 ⇒ 下次载入不会再铸
    expect(g1.rows.value.map((r) => r.id)).toEqual(written.map((r: { id: string }) => r.id))
  })

  it('G3 同型：纯数字 id 被重铸并回写', () => {
    const allResponses = mkResponses({
      [G3_KEY]: JSON.stringify([{ id: '1', investeeName: '甲' }]),
    })
    const debouncedSave = vi.fn()
    useG3Detail({ allResponses, debouncedSave, isReadonly: ref(false) })
    const call = debouncedSave.mock.calls.find((c) => c[0] === G3_KEY)
    expect(call).toBeDefined()
    const written = JSON.parse((call![1] as { conclusion: string }).conclusion)
    expect(written).toHaveLength(1)
    expect(isOrdinalRowId(written[0].id)).toBe(false)
    expect(String(written[0].id).startsWith('g3d-')).toBe(true)
  })

  it('已是稳定 id 的载荷不触发回写（不做无谓写入）', () => {
    const allResponses = mkResponses({
      [G3_KEY]: JSON.stringify([{ id: 'g3d-stable-1', investeeName: '甲' }]),
    })
    const debouncedSave = vi.fn()
    useG3Detail({ allResponses, debouncedSave, isReadonly: ref(false) })
    expect(debouncedSave.mock.calls.filter((c) => c[0] === G3_KEY)).toHaveLength(0)
  })

  it('只读模式下不回写（persistAll 内部短路）', () => {
    const allResponses = mkResponses({
      [G3_KEY]: JSON.stringify([{ id: '1', investeeName: '甲' }]),
    })
    const debouncedSave = vi.fn()
    useG3Detail({ allResponses, debouncedSave, isReadonly: ref(true) })
    expect(debouncedSave.mock.calls.filter((c) => c[0] === G3_KEY)).toHaveLength(0)
  })

  it('空载荷兜底行也拿到铸造身份（不是字面量 "1"）', () => {
    const g3 = useG3Detail({
      allResponses: mkResponses(),
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(g3.rows.value).toHaveLength(1)
    expect(isOrdinalRowId(g3.rows.value[0].id)).toBe(false)
    expect(g3.rows.value[0].id).not.toBe('1')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ⑥：源码形态防护 —— 两文件不得退回旧写法
// ═══════════════════════════════════════════════════════════════════════════

describe('G1R-P2 ⑥ 源码形态防护', () => {
  const FILES = ['useG1Detail.ts', 'useG3Detail.ts'] as const

  /**
   * 剥离注释行后的源码。
   *
   * 🔴 首版判据直接扫全文 ⇒ 被**修复说明注释里逐字引用的旧写法**打红
   * （注释写「原写法 `p.id ?? String(i + 1)` …」是有意的文档价值，不该因此失败）。
   * ⇒ 判据语义修正为「旧写法不得出现在**代码行**里」。
   * 局限：只按行首标记过滤（`//` / `*` / `/*`），不解析行尾注释与字符串字面量 ——
   * 对本判据足够（三处旧写法都在独立代码行上），若将来有人把旧写法写进行尾注释会假红。
   */
  function stripCommentLines(src: string): string {
    return src
      .split('\n')
      .filter((line) => {
        const t = line.trim()
        return !(t.startsWith('//') || t.startsWith('*') || t.startsWith('/*'))
      })
      .join('\n')
  }

  it.each(FILES)('%s 的代码行不含下标派生 id 与裸时间戳 id 的旧写法', async (file) => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const raw = fs.readFileSync(path.resolve(__dirname, '..', file), 'utf-8')
    const code = stripCommentLines(raw)
    // 旧写法①：`?? String(i + 1)` / `|| String(i + 1)`
    expect(code).not.toMatch(/\?\?\s*String\(\s*i\s*\+\s*1\s*\)/)
    expect(code).not.toMatch(/\|\|\s*String\(\s*i\s*\+\s*1\s*\)/)
    // 旧写法②：`` `row-${Date.now()}` ``（无随机后缀）
    expect(code).not.toMatch(/`row-\$\{Date\.now\(\)\}`/)
    // 旧写法③：空表兜底的字面量 '1'
    expect(code).not.toMatch(/emptyRow\(\s*'1'\s*,\s*1\s*\)/)
    // 正面：必须走单点铸造
    expect(code).toContain('g1g3RowIdentity')
    expect(code).toContain('resolveStableRowIds')
    // 🔴 前缀内联在消费方的铸造点 —— 行身份形态要能在本文件里逐字回源
    expect(code).toContain('mintRowIdSuffix')
    expect(code).toMatch(
      /function genRowId\(\): string \{\s*return `g[13]d-\$\{mintRowIdSuffix\(\)\}`/,
    )
    expect(code).not.toContain('G_ROW_ID_PREFIX')
    // 🔴 自检：注释里**确实**留着旧写法的逐字记录（修复说明的文档价值）
    expect(raw).toMatch(/String\(\s*i\s*\+\s*1\s*\)/)
    expect(raw.length).toBeGreaterThan(code.length)
  })

  it('四条 slice 误标的 entry 源码保持原样（未被顺手改动）', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    // G10/G11/G12/G13 的 id 生成本就带 Math.random()，本 spec 不动它们
    const cases: Array<[string, RegExp]> = [
      ['useG10Detail.ts', /Math\.random\(\)/],
      ['useG11DetailAnalysis.ts', /Math\.random\(\)/],
      ['useG12HedgeDetail.ts', /Math\.random\(\)/],
      ['useG13Detail.ts', /Math\.random\(\)/],
    ]
    for (const [file, pattern] of cases) {
      const src = fs.readFileSync(path.resolve(__dirname, '..', file), 'utf-8')
      expect(src, `${file} 的 id 生成应本就带随机后缀`).toMatch(pattern)
      expect(src, `${file} 不该被本 spec 改动（未引入 g1g3RowIdentity）`).not.toContain(
        'g1g3RowIdentity',
      )
    }
  })
})
