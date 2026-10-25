/**
 * D1-1 审定表逐格覆盖在 **UI 上真的可见/可操作**。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · Task 33（需求 6.3 / 6.4）
 *
 * ═══ 为什么需要这一层判据 ═══
 *
 * Task 33 把四态接进了 composable，但 `D1TabAdjudication.vue` 的模板里**每个金额格还各自**
 * 用 `v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"` 挡了一次编辑
 * ⇒ composable 层放开了 `isEditable`，UI 层又挡回去，**四态在界面上依旧不可达**。
 * 只测 composable 不会发现这一层（改一半的典型形态）。
 *
 * 本文件两层判据：
 *   1. **源码守卫**（零挂载成本、防回退）：金额格不得再出现 `!row.isFromCrossSheet`，
 *      且六个金额格都要挂上 `D1CellOverrideBadge`；
 *   2. **组件挂载**：badge 在 S1/S3 不显示、S2/S4 显示且文案区分，点击真的 emit `restore`。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import D1CellOverrideBadge from '../d1/D1CellOverrideBadge.vue'
import type { AdjudicationDetailRow } from '../composables/useD1Adjudication'

// ═══════════════════════════════════════════════════════════════════════════
// 1. 源码守卫 —— 钉住「UI 不再挡编辑」
// ═══════════════════════════════════════════════════════════════════════════

const TAB_SRC = readFileSync(
  resolve(__dirname, '../d1/D1TabAdjudication.vue'),
  'utf-8',
)

/** 六个金额格的 per-cell 字段后缀。 */
const AMOUNT_FIELDS = [
  'prior-unadj',
  'prior-aje',
  'prior-rje',
  'current-unadj',
  'current-aje',
  'current-rje',
] as const

describe('D1TabAdjudication 模板：金额格不再因 cross-sheet 只读', () => {
  it('🔴 `WpAmountInput` 的 v-if 里不得再出现 `!row.isFromCrossSheet`', () => {
    // 修前六处都是 `row.isEditable && !isReadonly && !row.isFromCrossSheet`。
    const guards = TAB_SRC.match(/v-if="row\.isEditable[^"]*"/g) ?? []
    expect(guards.length, '找不到金额格的 v-if ⇒ 模板结构变了，本守卫需要重写').toBeGreaterThanOrEqual(6)
    for (const g of guards) {
      expect(g, `金额格仍用 isFromCrossSheet 挡编辑：${g}`).not.toContain('isFromCrossSheet')
    }
  })

  it('🔴 六个金额格都挂了 D1CellOverrideBadge（否则该格的覆盖态不可见）', () => {
    expect(TAB_SRC).toContain('D1CellOverrideBadge')
    for (const field of AMOUNT_FIELDS) {
      expect(TAB_SRC, `字段 ${field} 缺覆盖标记`).toContain(`field="${field}"`)
    }
  })

  it('badge 的 @restore 接到了 composable 的 restoreDerivedValue', () => {
    expect(TAB_SRC).toContain('@restore="restoreDerivedValue"')
    expect(TAB_SRC, 'restoreDerivedValue 未从 composable 取出').toContain('restoreDerivedValue,')
  })

  it('🔴 变异反证：把 isFromCrossSheet 加回任一金额格的 v-if ⇒ 守卫必红', () => {
    const mutated = TAB_SRC.replace(
      'v-if="row.isEditable && !isReadonly"',
      'v-if="row.isEditable && !isReadonly && !row.isFromCrossSheet"',
    )
    const guards = mutated.match(/v-if="row\.isEditable[^"]*"/g) ?? []
    expect(guards.some((g) => g.includes('isFromCrossSheet'))).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. badge 组件挂载
// ═══════════════════════════════════════════════════════════════════════════

const STUBS = {
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-tag': { template: '<span class="stub-tag"><slot /></span>' },
  // 🔴 stub 里**不要**再 `$emit('click')`：Vue 会把父组件的 `@click` 自动绑到 stub 根元素，
  //    stub 再手动 emit 一次会让事件触发两遍（实测 emitted('restore') 收到 2 条）。
  'el-button': { template: '<button class="stub-btn"><slot /></button>' },
}

function rowWith(state: string | undefined): AdjudicationDetailRow {
  return {
    rowKey: 'gross-bank',
    label: '银行承兑汇票',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
    change: 0,
    changeRate: '',
    reasonAnalysis: '',
    isFromCrossSheet: true,
    isEditable: true,
    cellStates: state ? { 'prior-unadj': state as never } : {},
  } as AdjudicationDetailRow
}

function mountBadge(state: string | undefined, readonly = false) {
  return mount(D1CellOverrideBadge, {
    props: { row: rowWith(state), field: 'prior-unadj', readonly },
    global: { stubs: STUBS },
  })
}

describe('D1CellOverrideBadge', () => {
  it.each(['S1', 'S3', undefined])('%s 不显示标记（纯派生/自动跟随）', (state) => {
    expect(mountBadge(state as string | undefined).find('.stub-tag').exists()).toBe(false)
  })

  it('S2 显示「已人工覆盖」', () => {
    const w = mountBadge('S2')
    expect(w.find('.stub-tag').text()).toBe('已人工覆盖')
  })

  it('🔴 S4 文案要区别于 S2（覆盖 且 上游已变，审计师需要知道上游动过）', () => {
    const w = mountBadge('S4')
    expect(w.find('.stub-tag').text()).toBe('已覆盖·上游已变')
  })

  it('点击恢复按钮 emit restore(rowKey, field)', async () => {
    const w = mountBadge('S2')
    await w.find('.stub-btn').trigger('click')
    expect(w.emitted('restore')).toEqual([['gross-bank', 'prior-unadj']])
  })

  it('readonly 时不给恢复按钮（但标记仍可见）', () => {
    const w = mountBadge('S2', true)
    expect(w.find('.stub-tag').exists()).toBe(true)
    expect(w.find('.stub-btn').exists()).toBe(false)
  })
})
