/**
 * JN-4 行身份修复守卫。
 *
 * spec: `j2-j3-non-entry-hosts-and-orphan-cleanup` · Task 11（JN-P19）/ Task 12（JN-P20）
 *
 * 四组判据：
 * ① **grandfather**：已落库 `id: 1..N` 一律不重写（改它等于换身份）
 * ② **复现原缺陷**：删中间一行再新增 ⇒ 旧写法后续行 id 左移、备注串行（修复后不再发生）
 * ③ **安全生成器**：含随机、不含下标、严格大于现存 id、仍是 number
 * ④ **真实回落情形**：render-config 种子派生行未保存 / 旧数据无 id
 */
import { describe, it, expect } from 'vitest'
import {
  mintJRowId,
  resolveJRowId,
  withJRowIds,
  type JRowIdentityMintStats,
} from '../jRowIdentity'

// ═══════════════════════════════════════════════════════════════════
// ① grandfather：已落库的 1..N 不得被重写
// ═══════════════════════════════════════════════════════════════════

describe('grandfather 已落库的下标身份', () => {
  it('J2-3-entries 真库载荷的 id:1 原样保留', () => {
    // 真库实证载荷（171 B）的第一行
    const live = [
      {
        id: 1,
        description: '重分类一年内到期辞退福利',
        category: '账项调整',
        reportItem: '长期应付职工薪酬',
      },
    ]
    const out = withJRowIds(live)
    expect(out[0].id).toBe(1)
    expect(out[0].description).toBe('重分类一年内到期辞退福利')
  })

  it('J3-2-variation 真库载荷的 id:1 原样保留（family_b 回落产生的，同样不得重写）', () => {
    const live = [{ id: 1, category: '', time: '2024年度', calcSalary: 100000, bookSalary: 95000 }]
    expect(withJRowIds(live)[0].id).toBe(1)
  })

  it('整批历史 id 1..5 逐个保留、顺序不变', () => {
    const rows = [1, 2, 3, 4, 5].map(id => ({ id, tag: `row-${id}` }))
    const out = withJRowIds(rows)
    expect(out.map(r => r.id)).toEqual([1, 2, 3, 4, 5])
    expect(out.map(r => r.tag)).toEqual(['row-1', 'row-2', 'row-3', 'row-4', 'row-5'])
  })

  it('反向自检：造一条 id:1 的历史行，"重读"后仍是 1（被重写成新格式即打红）', () => {
    let rows: Array<{ id: number; note: string }> = [{ id: 1, note: '历史备注' }]
    // 模拟三轮「载入 → 保存 → 再载入」
    for (let round = 0; round < 3; round += 1) {
      rows = withJRowIds(rows) as Array<{ id: number; note: string }>
    }
    expect(rows[0].id).toBe(1)
    expect(rows[0].note).toBe('历史备注')
  })
})

// ═══════════════════════════════════════════════════════════════════
// ② 复现原缺陷：删中间一行再新增
// ═══════════════════════════════════════════════════════════════════

describe('原缺陷复现：删中间一行再新增', () => {
  /** 改造前的写法（下标派生 + 游标自增），仅用于证明缺陷真实存在。 */
  function legacyLoad(raw: Array<{ id?: number; note: string }>) {
    return raw.map((e, i) => ({ ...e, id: e.id ?? i + 1 }))
  }

  it('旧写法：删中间行后重载 ⇒ 后续行 id 左移、备注串到别的 id 上', () => {
    // 三行都还没有 id（render-config 种子派生，尚未保存）
    const seeded = [{ note: 'A' }, { note: 'B' }, { note: 'C' }]
    const first = legacyLoad(seeded as Array<{ id?: number; note: string }>)
    expect(first.map(r => r.id)).toEqual([1, 2, 3])

    // 删掉中间那行（B），剩下 A / C，且仍未保存 id
    const afterDelete = [{ note: 'A' }, { note: 'C' }]
    const second = legacyLoad(afterDelete as Array<{ id?: number; note: string }>)

    // 🔴 缺陷：C 原本身份是 3，重载后变成 2 —— 而 2 在上一轮属于 B
    expect(second[1].id).toBe(2)
    expect(first.find(r => r.id === 2)?.note).toBe('B')
    expect(second.find(r => r.id === 2)?.note).toBe('C')
  })

  it('修复后：同一序列的行身份互不相同，且删行不改变其余行的身份', () => {
    const seeded = [{ note: 'A' }, { note: 'B' }, { note: 'C' }]
    const first = withJRowIds(seeded)
    const ids = first.map(r => r.id)
    expect(new Set(ids).size).toBe(3)

    // 保存后删掉中间行（此时 id 已落库，再次载入走 grandfather）
    const afterDelete = first.filter(r => r.note !== 'B')
    const second = withJRowIds(afterDelete)
    expect(second.map(r => r.note)).toEqual(['A', 'C'])
    expect(second[0].id).toBe(first[0].id)
    expect(second[1].id).toBe(first[2].id) // C 的身份没变
  })
})

// ═══════════════════════════════════════════════════════════════════
// ③ 安全生成器的性质
// ═══════════════════════════════════════════════════════════════════

describe('mintJRowId 性质', () => {
  it('返回有限 number 且在安全整数范围内', () => {
    const id = mintJRowId()
    expect(typeof id).toBe('number')
    expect(Number.isFinite(id)).toBe(true)
    expect(Number.isSafeInteger(id)).toBe(true)
  })

  it('连续铸 200 个互不相同（含随机分量，同毫秒也不撞）', () => {
    const used: number[] = []
    for (let i = 0; i < 200; i += 1) used.push(mintJRowId(used))
    expect(new Set(used).size).toBe(200)
  })

  it('严格大于传入的所有现存 id（保持游标单调不变式）', () => {
    expect(mintJRowId([1, 2, 3])).toBeGreaterThan(3)
    // 现存 id 已经很大时也必须更大
    const huge = Number.MAX_SAFE_INTEGER - 10
    expect(mintJRowId([huge])).toBeGreaterThan(huge)
  })

  it('不是数组下标：对空数组铸出的 id 远大于任何合理行数', () => {
    expect(mintJRowId([])).toBeGreaterThan(1e12)
  })
})

// ═══════════════════════════════════════════════════════════════════
// ④ 真实回落情形
// ═══════════════════════════════════════════════════════════════════

describe('resolveJRowId 回落分支', () => {
  it('render-config 种子派生的行尚未保存（无 id 字段）⇒ 铸新身份并计数', () => {
    const stats: JRowIdentityMintStats = { minted: 0 }
    const id = resolveJRowId({ note: '种子行' }, [], stats)
    expect(stats.minted).toBe(1)
    expect(id).toBeGreaterThan(1e12)
  })

  it('旧数据 id 为 null / undefined / 空串 ⇒ 都算缺失', () => {
    for (const bad of [null, undefined, '']) {
      const stats: JRowIdentityMintStats = { minted: 0 }
      resolveJRowId({ id: bad }, [], stats)
      expect(stats.minted).toBe(1)
    }
  })

  it('id 是数字字符串 "7" ⇒ 归一化为 7 且**不**计入铸造（仍是 grandfather）', () => {
    const stats: JRowIdentityMintStats = { minted: 0 }
    expect(resolveJRowId({ id: '7' }, [], stats)).toBe(7)
    expect(stats.minted).toBe(0)
  })

  it('同一批内多行缺 id 时逐行累积、互不相撞', () => {
    const stats: JRowIdentityMintStats = { minted: 0 }
    const out = withJRowIds([{ a: 1 }, { a: 2 }, { a: 3 }], [], stats)
    expect(stats.minted).toBe(3)
    expect(new Set(out.map(r => r.id)).size).toBe(3)
  })

  it('混合批（部分有 id 部分没有）⇒ 有的保留、没的铸新且不与保留者冲突', () => {
    const stats: JRowIdentityMintStats = { minted: 0 }
    const out = withJRowIds([{ id: 1, t: 'old' }, { t: 'new' }, { id: 2, t: 'old2' }], [], stats)
    expect(stats.minted).toBe(1)
    expect(out[0].id).toBe(1)
    expect(out[2].id).toBe(2)
    expect(out[1].id).not.toBe(1)
    expect(out[1].id).not.toBe(2)
    expect(new Set(out.map(r => r.id)).size).toBe(3)
  })
})
