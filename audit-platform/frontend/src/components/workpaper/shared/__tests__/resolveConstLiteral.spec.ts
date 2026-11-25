/**
 * `resolveConstLiteral` 的常量别名链判据（x3 探针的键解析底座）。
 *
 * 背景：K13 把单一真源键导出为 `export const K13_ADJ_ITEM_KEY = 'K13-3-adj-entries'`，
 * composable 内再 `const ITEM_KEY = K13_ADJ_ITEM_KEY`（d97ff2f0d）。只认字面量赋值时，
 * `debouncedSave(ITEM_KEY, { remark })` 的键解析为 null ⇒ x3 契约守卫实测 0 列而红。
 *
 * 判据没有放宽成「找不到也算过」：别名链必须**最终落到字面量**；环 / 超深 / 落到非字面量
 * 一律返回 null。下面每一条都是「该返回 null 的地方仍返回 null」的反向断言。
 */
import { describe, it, expect } from 'vitest'
import { resolveConstLiteral } from './helpers/x3KeyProbe'

describe('resolveConstLiteral — 字面量与别名链', () => {
  it('直接字面量（含 export / let / var / 三种引号）仍解析', () => {
    expect(resolveConstLiteral(`const A = 'x-1'`, 'A')).toBe('x-1')
    expect(resolveConstLiteral(`export const A = "x-2"`, 'A')).toBe('x-2')
    expect(resolveConstLiteral('let A = `x-3`', 'A')).toBe('x-3')
    expect(resolveConstLiteral(`var A = 'x-4'`, 'A')).toBe('x-4')
  })

  it('K13 真实形态：export const 真源 + const 别名', () => {
    const src = [
      `export const K13_ADJ_ITEM_KEY = 'K13-3-adj-entries'`,
      `const ITEM_KEY = K13_ADJ_ITEM_KEY`,
    ].join('\n')
    expect(resolveConstLiteral(src, 'ITEM_KEY')).toBe('K13-3-adj-entries')
    expect(resolveConstLiteral(src, 'K13_ADJ_ITEM_KEY')).toBe('K13-3-adj-entries')
  })

  it('多跳别名（A→B→C→字面量）与分号结尾', () => {
    const src = `const C = 'deep'\nconst B = C;\nconst A = B;`
    expect(resolveConstLiteral(src, 'A')).toBe('deep')
  })

  it('别名声明顺序不影响结果（先别名后真源）', () => {
    const src = `const ITEM_KEY = REAL_KEY\nconst REAL_KEY = 'late'`
    expect(resolveConstLiteral(src, 'ITEM_KEY')).toBe('late')
  })

  // ── 反向：该是 null 的地方仍是 null ──

  it('环：A→B→A 返回 null 且不死循环', () => {
    expect(resolveConstLiteral(`const A = B\nconst B = A`, 'A')).toBeNull()
    expect(resolveConstLiteral(`const A = A`, 'A')).toBeNull()
  })

  it('别名落到非字面量（函数调用 / 表达式 / 未声明标识符）⇒ null', () => {
    expect(resolveConstLiteral(`const A = makeKey()`, 'A')).toBeNull()
    expect(resolveConstLiteral(`const A = B + 'x'`, 'A')).toBeNull()
    expect(resolveConstLiteral(`const A = NOT_DECLARED`, 'A')).toBeNull()
  })

  it('超过深度上限的链 ⇒ null（防被超长链拖垮）', () => {
    const src = [
      `const L0 = 'end'`,
      ...Array.from({ length: 8 }, (_, i) => `const L${i + 1} = L${i}`),
    ].join('\n')
    expect(resolveConstLiteral(src, 'L1')).toBe('end') // 1 跳
    expect(resolveConstLiteral(src, 'L8')).toBeNull() // 8 跳 > 上限
  })

  it('名字不存在 ⇒ null；名字含 $ 不被当正则元字符', () => {
    expect(resolveConstLiteral(`const A = 'x'`, 'MISSING')).toBeNull()
    expect(resolveConstLiteral(`const $k = 'dollar'`, '$k')).toBe('dollar')
  })

  it('不把同前缀的别名名字误当目标（A 不命中 AB）', () => {
    expect(resolveConstLiteral(`const AB = 'wrong'`, 'A')).toBeNull()
  })
})
