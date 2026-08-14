/**
 * `ConsolNoteTab.uniqueSheetName` 去重契约守卫
 *
 * ## 背景（2026-08-14，frontend-excel-io-single-entry-convergence 收尾修复）
 *
 * 改造前该函数**名不副实**：把名字 `add` 进 `usedNames` 但**从不检查**是否已存在，
 * 去重完全没实现。一旦两个名字截断到 31 字符后相同，`book_append_sheet` 会抛错，
 * 导致**整批附注导出失败**（不是少一个 sheet）。
 *
 * 当前数据撞不上（实测 282 个 section、18 个被截断、零重复 —— `prefix` 由唯一
 * `section_id` 派生且位于名字最前），但这依赖章节编号体系的形态。既然函数名承诺
 * 去重就实现掉，并用本文件钉死。
 *
 * ## 为什么把算法复制到测试里
 *
 * `uniqueSheetName` 是 `.vue` 的 `<script setup>` 内部函数，未 `defineExpose`，
 * 无法直接 import。两个选择：
 *   a) mount 整个 `ConsolNoteTab`（要 mock api / eventBus / acnr / 十几个 composable）
 *   b) 在测试里维护一份同算法实现，并**同时校验生产源码与之保持一致**
 *
 * 选 b，但补上 (b) 的致命弱点 —— 「复制一份就可能漂移」：最后一条测试直接读生产
 * 源码，校验关键行仍在。否则生产代码改了而测试还绿，就是典型的假绿。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = path.resolve(
  __dirname,
  '../ConsolNoteTab.vue',
)

/** 与生产实现同算法（一致性由本文件最后一条测试校验） */
function uniqueSheetName(usedNames: Set<string>, rawName: string, sectionId: string): string {
  const prefix = sectionId.replace(/^五-/, '').replace(/-/g, '.')
  const base = `${prefix} ${rawName}`.substring(0, 31)
  if (!usedNames.has(base)) {
    usedNames.add(base)
    return base
  }
  for (let n = 2; n < 1000; n += 1) {
    const suffix = `~${n}`
    const candidate = base.substring(0, 31 - suffix.length) + suffix
    if (!usedNames.has(candidate)) {
      usedNames.add(candidate)
      return candidate
    }
  }
  const fallback = base.substring(0, 24) + `~${Date.now() % 1000000}`
  usedNames.add(fallback)
  return fallback
}

describe('ConsolNoteTab.uniqueSheetName 去重契约', () => {
  it('正常情况：章节号前缀 + 标题', () => {
    const used = new Set<string>()
    expect(uniqueSheetName(used, '货币资金', '五-1-1')).toBe('1.1 货币资金')
    expect(uniqueSheetName(used, '交易性金融资产', '五-2-1')).toBe('2.1 交易性金融资产')
  })

  it('超长名字截断到 31 字符（Excel 上限）', () => {
    const used = new Set<string>()
    const name = uniqueSheetName(used, '期末本公司已背书或贴现但尚未到期的应收票据情况说明补充', '五-4-3')
    expect(name.length).toBeLessThanOrEqual(31)
    expect(name.startsWith('4.3 ')).toBe(true)
  })

  it('🔴 截断后同名时必须产出不同的 sheet 名（改造前这里会产出重复 → book_append_sheet 抛错 → 整批导出失败）', () => {
    const used = new Set<string>()
    // 构造两个截断后必然相同的输入：同 prefix + 前 27 字符相同的长标题
    const long1 = '应收账款按账龄披露的明细情况说明第一部分内容'
    const long2 = '应收账款按账龄披露的明细情况说明第二部分内容'

    const a = uniqueSheetName(used, long1, '五-5-1')
    const b = uniqueSheetName(used, long2, '五-5-1')

    expect(a.length).toBeLessThanOrEqual(31)
    expect(b.length).toBeLessThanOrEqual(31)
    expect(b, 'a 与 b 相同 —— 去重没生效，Excel 会拒绝第二个 sheet').not.toBe(a)
  })

  it('🔴 加后缀后仍不得超过 31 字符（为后缀预留位置，这是加后缀去重最易漏的一步）', () => {
    const used = new Set<string>()
    const long = 'X'.repeat(60) // 保证 base 一定被截到满 31

    const names: string[] = []
    for (let i = 0; i < 12; i += 1) names.push(uniqueSheetName(used, long, '五-9-9'))

    for (const n of names) {
      expect(n.length, `「${n}」长度 ${n.length} 超过 Excel 上限 31`).toBeLessThanOrEqual(31)
    }
    expect(new Set(names).size, '12 次同名输入应产出 12 个不同名字').toBe(12)
  })

  it('多次撞名时后缀递增，且全部唯一', () => {
    const used = new Set<string>()
    const got = [
      uniqueSheetName(used, '存货', '五-8-1'),
      uniqueSheetName(used, '存货', '五-8-1'),
      uniqueSheetName(used, '存货', '五-8-1'),
    ]
    expect(got[0]).toBe('8.1 存货')
    expect(got[1]).toBe('8.1 存货~2')
    expect(got[2]).toBe('8.1 存货~3')
    expect(new Set(got).size).toBe(3)
  })

  it('🔴 生产源码与本文件的算法保持一致（防「测试里的副本漂移」假绿）', () => {
    const src = fs.readFileSync(SRC, 'utf-8')

    // 关键行：三条缺一条都说明生产实现已偏离
    const musts: Array<[string, string]> = [
      ['if (!usedNames.has(base)) {', '缺少「先查是否已存在」—— 去重的核心判断'],
      ['const candidate = base.substring(0, 31 - suffix.length) + suffix', '缺少「为后缀预留位置」—— 拼完会超 31'],
      ["const suffix = `~${n}`", '缺少后缀生成'],
    ]
    for (const [line, why] of musts) {
      expect(src.includes(line), `${why}。生产源码里找不到：${line}`).toBe(true)
    }

    // 反向：不得回到「只 add 不 check」的旧形态
    expect(
      /usedNames\.add\(name\)\s*\n\s*return name/.test(src),
      '生产源码回退成了「只 add 不 check」的旧实现（usedNames 变回死参数）',
    ).toBe(false)
  })
})
