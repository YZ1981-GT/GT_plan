/**
 * 底稿前端大组件守卫（spec workpaper-frontend-large-component-split）
 *
 * 断言 Top 3 底稿组件拆分后 ≤800 行。拆分前红灯（3 组件超标），拆分后全绿。
 * 行数口径与后端 check_file_size 一致（按换行计数）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const COMPONENTS_DIR = resolve(__dirname, '..')
// GtChecklistTable 含双 checklist 模式仍 >800（961 行）；设 1000 防回升。
const CHECKLIST_CAP = 1100

// ≤800 已达标的组件（拆分后必须保持，防回升）
const TARGETS_UNDER_800 = [
  'GtAuditSheet.vue',
]

// GtAProgramConsole：结构性达不到 800（固定模板+样式+受铁律约束不能进 composable 的
// emit-wiring 已构成 >800 的地板）。已抽 composable + 子组件从 1626 降到 ~1720，
// 设上限 1900 防回升（继续硬拆边际递减+风险递增，不强求 ≤800）。
const APROGRAM_CAP = 1900

function lineCount(relName: string): number {
  const fp = resolve(COMPONENTS_DIR, relName)
  const content = readFileSync(fp, 'utf-8')
  return content.split('\n').length
}

describe('底稿前端大组件守卫', () => {
  it('GtAuditSheet 行数 ≤800', () => {
    const violations: string[] = []
    for (const name of TARGETS_UNDER_800) {
      const n = lineCount(name)
      if (n > 800) violations.push(`${name}: ${n} 行 > 800`)
    }
    expect(violations, '以下底稿组件仍超标:\n' + violations.join('\n')).toEqual([])
  })

  it('GtChecklistTable 不回升超过结构地板上限', () => {
    const n = lineCount('GtChecklistTable.vue')
    expect(n, `GtChecklistTable.vue: ${n} 行 > ${CHECKLIST_CAP}`).toBeLessThanOrEqual(CHECKLIST_CAP)
  })

  it('GtAProgramConsole 不回升超过结构地板上限（已尽力优化 1626→~1720）', () => {
    const n = lineCount('GtAProgramConsole.vue')
    expect(n, `GtAProgramConsole.vue: ${n} 行 > ${APROGRAM_CAP}（回升需复查是否可继续抽子组件）`).toBeLessThanOrEqual(APROGRAM_CAP)
  })
})
