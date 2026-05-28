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
    { path: 'views/workpaper-list/WorkpaperWorkbenchView.vue', budget: 700, label: 'Workbench' },
    { path: 'views/workpaper-list/WorkpaperBoardView.vue', budget: 700, label: 'Board' },
    { path: 'views/workpaper-list/WorkpaperLifecycleView.vue', budget: 700, label: 'Lifecycle' },
    { path: 'views/workpaper-list/WorkpaperDependencyGraph.vue', budget: 700, label: 'DependencyGraph' },
    { path: 'views/workpaper-list/WorkpaperDelegationMatrix.vue', budget: 700, label: 'DelegationMatrix' },
  ]

  test.each(files)('$label ($path) ≤ $budget lines', ({ path, budget }) => {
    const lines = lineCount(path)
    expect(lines).toBeLessThanOrEqual(budget)
  })

  test('total lines ≤ 4156 (3463 × 1.2)', () => {
    const total = files.reduce((sum, f) => sum + lineCount(f.path), 0)
    expect(total).toBeLessThanOrEqual(4156)
  })
})
