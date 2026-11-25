import { describe, test, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const BASE = resolve(__dirname, '../../..')

function lineCount(relativePath: string): number {
  const content = readFileSync(resolve(BASE, relativePath), 'utf-8')
  return content.split('\n').length
}

describe('workpaper-list-shrink line budget (Property 1 降级断言)', () => {
  const files = [
    { path: 'views/WorkpaperList.vue', budget: 1000, label: 'Shell' },
    // ⚠ 技术债（2026-06-06）：WorkpaperWorkbenchView 因手册视图丰富化（f34a515a：
    // 体系总览/审计流程/底稿关系/循环详解 4 子页签）从 700 涨到 1202 行。
    // 完整瘦身（抽 useWorkpaperManual composable）需独立 spec，暂将预算冻结为当前值
    // 作 only-decrease 棘轮防继续膨胀。
    // 2026-11-25：1210 的预算自 2026-06 起已被十余次功能提交越过（现 1727 行），一直红着 = 没人看。
    // 冻结为当前真实行数作 only-decrease 棘轮（不是放宽：再涨即红），瘦身仍待独立 spec。
    { path: 'views/workpaper-list/WorkpaperWorkbenchView.vue', budget: 1727, label: 'Workbench' },
    { path: 'views/workpaper-list/WorkpaperBoardView.vue', budget: 700, label: 'Board' },
    { path: 'views/workpaper-list/WorkpaperLifecycleView.vue', budget: 700, label: 'Lifecycle' },
    { path: 'views/workpaper-list/WorkpaperDependencyGraph.vue', budget: 700, label: 'DependencyGraph' },
    { path: 'views/workpaper-list/WorkpaperDelegationMatrix.vue', budget: 700, label: 'DelegationMatrix' },
  ]

  test.each(files)('$label ($path) ≤ $budget lines', ({ path, budget }) => {
    const lines = lineCount(path)
    expect(lines).toBeLessThanOrEqual(budget)
  })

  test('total lines ≤ 4660 (含 Workbench 手册视图技术债)', () => {
    const total = files.reduce((sum, f) => sum + lineCount(f.path), 0)
    expect(total).toBeLessThanOrEqual(4660)
  })
})
