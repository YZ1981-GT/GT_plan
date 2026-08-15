/**
 * I1 两版披露「新增/删除资产类别」的 **composable 层**守卫。
 *
 * ## 为什么必须单独测这一层（假绿根因）
 *
 * `iCycleDynamicRows.spec.ts` 已把 **model 层**（`i1SoeDisclosureModel.ts`）测得很足，
 * 且用法全部正确（`res!.layers` / `a.seq`）。但 `useI1Disclosure.ts` 这一层
 * **没有任何测试**，于是它把 `addI1SoeCategory` 的返回值 `{ layers, key, seq }`
 * 当成数组用：
 *
 * ```ts
 * const next = addI1SoeCategory(layers.value, label, catSeqCounter.value)
 * catSeqCounter.value = maxI1SoeCustomSeq(next)        // ← 对象喂给 for...of
 * layers.value = recomputeI1SoeDerivedLayers(next)     // ← 同上
 * ```
 *
 * `maxI1SoeCustomSeq` 内部 `for (const block of layers)` 对普通对象抛
 * `TypeError: layers is not iterable`，再被组件 `handleAddSoeCat` 的裸
 * `catch { /* cancelled *\/ }` 吞掉 ⇒ 浏览器实测表现为「点确认后**无提示、无新行、
 * 无库写入、控制台无 error**」，`checklist_responses` 里 `I1-soe%` 键数为 **0**。
 *
 * 四层守卫为何全绿：
 * - model 层 vitest：用的是正确写法，测不到 composable 的错用；
 * - vite transform：单文件编译不做跨模块类型检查；
 * - `get_diagnostics`：**对该类型不匹配漏报**（实测三个文件全报 No diagnostics）；
 * - 只有 `tsc --noEmit` 报出 TS2345（`useI1Disclosure.ts` 550/551 两行）。
 *
 * ⇒ 本文件锁死 composable 层的**行为**（不只是类型），并覆盖国企/上市两版。
 *
 * spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/ Task 24（补测 3/5）
 */
import { nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { useI1ListedDisclosure, useI1SoeDisclosure } from '../useI1Disclosure'
import { I1_SOE_CATEGORIES } from '../i1SoeDisclosureModel'

/** 造一个空的 `allResponses`（组件真实传入的形态是 `Map<itemId, response>`） */
function blankResponses() {
  return ref(new Map<string, any>())
}

/** onSave 收集器：只记录不回灌，避免 watch 立即 load 干扰被测行为 */
function collector() {
  const saved: Array<[string, any]> = []
  return { saved, onSave: (id: string, v: any) => { saved.push([id, v]) } }
}

describe('国企版 addCategory：四层同时加行 + 不抛异常', () => {
  it('新增自定义类别返回 true，四层各加一行（旧实现在此抛 TypeError）', async () => {
    const { saved, onSave } = collector()
    const soe = useI1SoeDisclosure({ allResponses: blankResponses(), onSave })
    await nextTick()

    const before = soe.layers.value.map((b) => b.categories.length)
    expect(before).toHaveLength(4)
    expect(new Set(before).size, '四层初始类别数应一致').toBe(1)

    // 🔴 关键断言：不抛异常。旧实现在这里抛 `layers is not iterable`
    let ok: boolean | undefined
    expect(() => { ok = soe.addCategory('碳排放权') }).not.toThrow()
    expect(ok).toBe(true)

    const after = soe.layers.value.map((b) => b.categories.length)
    expect(after).toEqual(before.map((n) => n + 1))
    for (const block of soe.layers.value) {
      expect(
        block.categories.some((c) => c.label === '碳排放权'),
        `${block.layer} 层缺少新增类别 ⇒ 四层不同步`,
      ).toBe(true)
    }
    // 持久化确实发生（旧实现异常导致 persist 永不执行 ⇒ 库里零 I1-soe 键）
    expect(saved.some(([id]) => id === 'I1-soe-layers')).toBe(true)
    expect(saved.some(([id]) => id === 'I1-soe-cat-seq')).toBe(true)
  })

  it('计数器取 addI1SoeCategory 返回的 seq，连续新增单调递增', async () => {
    const { saved, onSave } = collector()
    const soe = useI1SoeDisclosure({ allResponses: blankResponses(), onSave })
    await nextTick()

    expect(soe.addCategory('甲')).toBe(true)
    expect(soe.addCategory('乙')).toBe(true)
    expect(soe.addCategory('丙')).toBe(true)

    const keys = soe.layers.value[0].categories.map((c) => c.key)
    expect(keys).toContain('soe_custom_1')
    expect(keys).toContain('soe_custom_2')
    expect(keys).toContain('soe_custom_3')

    const seqSaves = saved.filter(([id]) => id === 'I1-soe-cat-seq').map(([, v]) => String(v))
    expect(seqSaves.at(-1)).toBe('3')
  })

  it('🔴 删掉最大号后再新增，seq 不复用（Property 23 在 composable 层仍成立）', async () => {
    const { saved, onSave } = collector()
    const soe = useI1SoeDisclosure({ allResponses: blankResponses(), onSave })
    await nextTick()

    soe.addCategory('甲') // soe_custom_1
    soe.addCategory('乙') // soe_custom_2
    expect(soe.removeCategory('soe_custom_2')).toBe(true)
    // 计数器留在 2 ⇒ 下一个必须是 3，不能复用已删的 2
    expect(soe.addCategory('丙')).toBe(true)

    const keys = soe.layers.value[0].categories.map((c) => c.key)
    expect(keys, '复用了已删序号 ⇒ 旧持久化数据串台').toContain('soe_custom_3')
    expect(keys).not.toContain('soe_custom_2')
    expect(saved.filter(([id]) => id === 'I1-soe-cat-seq').map(([, v]) => String(v)).at(-1)).toBe('3')
  })

  it('撞名（含默认 12 类）返回 false 且不加行', async () => {
    const soe = useI1SoeDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()

    const before = soe.layers.value[0].categories.length
    for (const c of I1_SOE_CATEGORIES) {
      expect(soe.addCategory(c.label), `${c.label} 竟可重名新增`).toBe(false)
    }
    expect(soe.addCategory('碳排放权')).toBe(true)
    expect(soe.addCategory('碳排放权')).toBe(false)
    expect(soe.addCategory('  碳排放权  ')).toBe(false)
    expect(soe.layers.value[0].categories.length).toBe(before + 1)
  })

  it('空名 / 纯空白返回 false（不产生无名行）', async () => {
    const soe = useI1SoeDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()
    const before = soe.layers.value[0].categories.length
    expect(soe.addCategory('')).toBe(false)
    expect(soe.addCategory('   ')).toBe(false)
    expect(soe.addCategory('\t\n')).toBe(false)
    expect(soe.layers.value[0].categories.length).toBe(before)
  })

  it('默认类别不可删（返回 false）', async () => {
    const soe = useI1SoeDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()
    expect(soe.removeCategory('patent')).toBe(false)
    expect(soe.removeCategory('other')).toBe(false)
    expect(soe.removeCategory('不存在的键')).toBe(false)
  })
})

describe('上市版 addCategory：与国企版同构的撞名/空名拒绝', () => {
  it('空名不再兜底成「其他」（旧实现 `label.trim() || \'其他\'` 会静默造重复列）', async () => {
    const listed = useI1ListedDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()

    const before = listed.categories.value.length
    expect(listed.addCategory('')).toBe(false)
    expect(listed.addCategory('   ')).toBe(false)
    expect(listed.categories.value.length).toBe(before)
    // 「其他」是源模板固定类别，兜底会与它撞名
    expect(
      listed.categories.value.filter((c) => String(c.label).trim() === '其他').length,
      '「其他」列重复 ⇒ 推附注与交叉核对的匹配键不再唯一',
    ).toBeLessThanOrEqual(1)
  })

  it('撞名返回 false，正常名返回 true 并加列', async () => {
    const listed = useI1ListedDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()

    const before = listed.categories.value.length
    const existing = listed.categories.value[0]?.label
    if (existing) expect(listed.addCategory(String(existing))).toBe(false)

    expect(listed.addCategory('域名')).toBe(true)
    expect(listed.categories.value.length).toBe(before + 1)
    expect(listed.addCategory('域名')).toBe(false)
    expect(listed.addCategory(' 域名 ')).toBe(false)
    expect(listed.categories.value.length).toBe(before + 1)
  })

  it('label 前后空白归一后入库（匹配键唯一性）', async () => {
    const listed = useI1ListedDisclosure({ allResponses: blankResponses(), onSave: () => {} })
    await nextTick()
    expect(listed.addCategory('  碳排放权  ')).toBe(true)
    expect(listed.categories.value.some((c) => c.label === '碳排放权')).toBe(true)
    expect(listed.categories.value.some((c) => c.label === '  碳排放权  ')).toBe(false)
  })
})
