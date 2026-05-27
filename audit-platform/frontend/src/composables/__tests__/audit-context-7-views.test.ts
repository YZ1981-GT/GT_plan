/**
 * V3 Req 5.3 — 7 核心视图静态扫描守门测试
 *
 * 形式化：∀ view V ∈ SEVEN_VIEWS:
 *   V's source code SHALL contain BOTH `useAuditContext` AND `onContextChange`
 *
 * 用途：
 * - 5.1 已确认 7 视图都通过 onContextChange 接入年度切换响应
 * - 本测试做静态保证：任何后续 PR 若意外删除 onContextChange 接入，会立即被卡住
 * - 与 property-year-switching-invariant.spec.ts 的 P5-d 互补（一个 PBT，一个直查）
 *
 * Validates: Requirements 5.1 + 5.3
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

const SEVEN_VIEWS = [
  'Adjustments.vue',
  'Misstatements.vue',
  'ReportView.vue',
  'DisclosureEditor.vue',
  'WorkpaperList.vue',
  'TrialBalance.vue',
  'LedgerPenetration.vue',
] as const

function resolveViewsDir(): string {
  const cwd = process.cwd()
  const candidates = [
    path.resolve(cwd, 'src/views'),
    path.resolve(cwd, 'audit-platform/frontend/src/views'),
    path.resolve(cwd, '../audit-platform/frontend/src/views'),
    path.resolve(__dirname, '../../views'),
  ]
  const found = candidates.find((p) => fs.existsSync(p))
  if (!found) {
    throw new Error(
      `无法定位 src/views 目录。已尝试: ${candidates.join(' | ')} (cwd=${cwd})`,
    )
  }
  return found
}

describe('V3 Req 5.3 — 7 核心视图 useAuditContext 接入静态守门', () => {
  const viewsDir = resolveViewsDir()

  describe.each(SEVEN_VIEWS)('视图 %s', (filename) => {
    const fullPath = path.join(viewsDir, filename)
    const src = fs.existsSync(fullPath) ? fs.readFileSync(fullPath, 'utf-8') : ''

    it('视图文件存在', () => {
      expect(fs.existsSync(fullPath), `期望存在: ${fullPath}`).toBe(true)
    })

    it('源码包含 import { useAuditContext } from ...', () => {
      // 同时容忍：解构导入 / namespace 导入
      const hasImport =
        /import\s*\{[^}]*\buseAuditContext\b[^}]*\}\s*from\s*['"][^'"]*useAuditContext['"]/.test(src) ||
        /import\s+\*\s+as\s+\w+\s+from\s+['"][^'"]*useAuditContext['"]/.test(src)
      expect(hasImport, `${filename} 未 import useAuditContext`).toBe(true)
    })

    it('源码调用 useAuditContext() 且解构 onContextChange', () => {
      // 容忍多种解构写法：
      // const { onContextChange } = useAuditContext()
      // const { canEdit, onContextChange } = useAuditContext()
      // const ctx = useAuditContext(); ctx.onContextChange(...)
      const callsHook = /useAuditContext\s*\(/.test(src)
      const usesOnContextChange = /\bonContextChange\s*\(/.test(src)
      expect(callsHook, `${filename} 未调用 useAuditContext()`).toBe(true)
      expect(usesOnContextChange, `${filename} 未调用 onContextChange()`).toBe(true)
    })
  })

  it('一次性汇总：7 视图 100% 同时含 useAuditContext + onContextChange', () => {
    const failures: string[] = []
    for (const filename of SEVEN_VIEWS) {
      const full = path.join(viewsDir, filename)
      if (!fs.existsSync(full)) {
        failures.push(`${filename} 缺失文件`)
        continue
      }
      const src = fs.readFileSync(full, 'utf-8')
      if (!src.includes('useAuditContext')) failures.push(`${filename} 缺 useAuditContext`)
      if (!/\bonContextChange\s*\(/.test(src)) failures.push(`${filename} 缺 onContextChange()`)
    }
    expect(failures, `失败视图清单:\n${failures.join('\n')}`).toEqual([])
  })
})
