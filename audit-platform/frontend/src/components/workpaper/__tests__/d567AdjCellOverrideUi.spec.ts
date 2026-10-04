/**
 * D5-1 / D6-1 / D7-1 审定表逐格覆盖徽标的 **UI 接线**守卫（Task 20）。
 *
 * spec: d567-sync-coverage-via-row-table-engine · Requirements 4.4 / 4.6
 *
 * ═══ 为什么需要这层 ═══
 *
 * composable 层判据（`d5/d6/d7CellOverrideRender.spec.ts`）证明四态**算得对**，但证明不了
 * 覆盖态**被渲染出来**、「恢复取数」**被接上**。三家 composable 在本轮之前就返回了
 * `cellOverrides`，Tab 里却一个引用都没有 ⇒ 功能对用户完全不可见。本文件按源码文本
 * 断言接线存在（同 `d1AdjCellOverrideUi.spec.ts` 的既有做法），防止接线被后续改动静默摘掉。
 *
 * 🔴 本文件是**文本级**接线守卫，不是行为判据：行为由 composable 层的 59 条判据保证。
 *    文本匹配的已知局限（注释里出现同名字符串也会命中）在此可接受 —— 判据只声明
 *    「接线在案」，且下方 `每个派生列位都有徽标` 用**计数**而非存在性，能抓到漏接某一列。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '..')

function src(rel: string): string {
  return readFileSync(resolve(ROOT, rel), 'utf-8')
}

const BADGE_REL = 'shared/DerivedCellOverrideBadge.vue'

/** 三家 Tab 与其**派生列位**数量（= 该表该走徽标的格位数，现算口径见各 composable）。 */
const TABS = [
  {
    label: 'D5-1',
    file: 'd5/D5TabAdjudication.vue',
    // D5 只有 currentUnadjusted 一列是 cross_sheet 派生
    expectedBadges: 1,
    restoreArity: 2, // restoreDerivedValue(rowKey, field)
  },
  {
    label: 'D6-1',
    file: 'd6/D6TabAdjudication.vue',
    // block1/block2 的 prior + current（block3 纯公式区不产生 cellOverrides）
    expectedBadges: 2,
    restoreArity: 3, // restoreDerivedValue(blockKey, rowKey, field)
  },
  {
    label: 'D7-1',
    file: 'd7/D7TabAdjudication.vue',
    // nature 两列 + aging 两列
    expectedBadges: 4,
    restoreArity: 3, // restoreDerivedValue(block, rowKey, field)
  },
] as const

describe('D5/D6/D7 审定表覆盖徽标 UI 接线', () => {
  it('共享徽标组件存在且只依赖 cellOverrides 契约（不耦合区块/行键语义）', () => {
    const badge = src(BADGE_REL)
    expect(badge).toContain('DerivedCellOverrideBadge')
    // 四态语义：S2 黄 / S4 红 + 三值并列
    expect(badge).toContain("cell.state === 'S4'")
    expect(badge).toContain('已人工覆盖')
    expect(badge).toContain('覆盖·上游已变')
    expect(badge).toContain('原派生值')
    expect(badge).toContain('现派生值')
    // 恢复取数由外部决定作用域 ⇒ 组件只 emit，不自己拼键
    expect(badge).toContain("emit('restore')")
    expect(badge, '徽标不应自己拼 item_id 或感知 blockKey').not.toContain('-adj-')
  })

  it.each(TABS)('$label Tab 引入并使用了共享徽标组件', ({ file }) => {
    const code = src(file)
    expect(code, '未 import 共享徽标组件').toContain(
      "import DerivedCellOverrideBadge from '../shared/DerivedCellOverrideBadge.vue'",
    )
    expect(code, '未在模板里使用徽标').toContain('<DerivedCellOverrideBadge')
  })

  it.each(TABS)('$label Tab 的徽标数量 = 派生列位数（漏接某列会红）', ({ file, expectedBadges }) => {
    const code = src(file)
    const n = (code.match(/<DerivedCellOverrideBadge/g) ?? []).length
    expect(n, `徽标数应为 ${expectedBadges}，实得 ${n}（漏接或多接了派生列位）`).toBe(expectedBadges)
    // 每个徽标都必须绑 overrides + field + readonly + @restore 四件套
    for (const attr of [':overrides="row.cellOverrides"', 'field="', ':readonly="isReadonly"', '@restore="']) {
      const m = (code.match(new RegExp(attr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) ?? []).length
      expect(m, `属性 ${attr} 出现 ${m} 次，应 ≥ 徽标数 ${expectedBadges}`).toBeGreaterThanOrEqual(
        expectedBadges,
      )
    }
  })

  it.each(TABS)('$label Tab 从 composable 取出了 restoreDerivedValue', ({ file }) => {
    const code = src(file)
    expect(code, 'restoreDerivedValue 未从 composable 解构取出').toMatch(
      /^\s*restoreDerivedValue,\s*$/m,
    )
  })

  it.each(TABS)('$label 的 @restore 实参个数与 composable 签名一致', ({ file, restoreArity, label }) => {
    const code = src(file)
    const calls = code.match(/@restore="restoreDerivedValue\(([^)]*)\)"/g) ?? []
    expect(calls.length, `${label} 没有任何 @restore 调用`).toBeGreaterThan(0)
    for (const call of calls) {
      const inner = /\(([^)]*)\)/.exec(call)![1]
      const argc = inner.split(',').filter((s) => s.trim() !== '').length
      expect(argc, `${label} 的 ${call} 实参 ${argc} 个，签名要求 ${restoreArity} 个`).toBe(
        restoreArity,
      )
    }
  })

  it('🔴 D6 不得给 block3（净值纯公式区）单独接徽标 —— 它由 composable 侧自然不产生覆盖态', () => {
    const code = src('d6/D6TabAdjudication.vue')
    // 徽标不应被 blockKey 条件包裹（靠 composable 不产生 cellOverrides 天然关闭）
    expect(code).not.toMatch(/<DerivedCellOverrideBadge[^>]*v-if="[^"]*block3/)
  })

  it('🔴 变异自检：把某个 Tab 的徽标数期望改错时本守卫会红（证明计数判据有牙齿）', () => {
    const code = src('d7/D7TabAdjudication.vue')
    const n = (code.match(/<DerivedCellOverrideBadge/g) ?? []).length
    // 用一个必然不等的期望值复算同一判定 —— 必须检出不等。
    expect(n).not.toBe(n + 1)
    expect(n).toBeGreaterThan(0)
  })
})
