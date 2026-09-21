/**
 * D4-5 宿主接线守卫 —— 独立 sync host，不并入父级 isD4DetailSheet。
 *
 * spec: d-cycle-sheet-bidirectional-expansion · paragraph_block_bidirectional
 *
 * 2026-09-21 治本改造后更新：D4-5 的接桥不再直接调 `useWorkpaperSyncBridge`，而是通过
 * 共享 composable `useD4SyncMode`（entryId/capability/健康门禁/switchMode 已内聚到该
 * composable 内部，由 `useD4SyncMode.spec.ts` 单独守卫）。D4-5 destructure 时用了组件专属
 * 前缀命名（`d45SyncBridge`/`d45SyncOoDescriptor`/`d45SyncHostRef`），sheetKey 为内联字面量。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const TAB = resolve(__dirname, '..', 'd4', 'policy', 'D4TabPolicyCheck.vue')
const PARENT = resolve(__dirname, '..', 'GtD4OperatingRevenue.vue')

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function extractBridgeCallArgs(src: string): string {
  const marker = 'useD4SyncMode('
  const start = src.indexOf(marker)
  if (start < 0) return ''
  let depth = 0
  for (let i = start + marker.length - 1; i < src.length; i++) {
    const ch = src[i]
    if (ch === '(') depth++
    else if (ch === ')') {
      depth--
      if (depth === 0) return src.slice(start + marker.length, i)
    }
  }
  return ''
}

describe('D4-5 tab 必须消费共享 composable useD4SyncMode（独立宿主）', () => {
  const hostSrc = stripComments(read(TAB))
  const args = extractBridgeCallArgs(hostSrc)

  it('tab 确实调用了共享 composable useD4SyncMode（禁直连底层桥）', () => {
    expect(args.length).toBeGreaterThan(0)
    expect(hostSrc).not.toContain('useWorkpaperSyncBridge(')
  })

  it('flushHtml 必须先 flushPendingSave 再 readStoreProjection', () => {
    expect(args).toContain('flushHtml')
    expect(args).toMatch(/flushPendingSave\s*\(/)
    expect(args).toMatch(/readStoreProjection\s*\(/)
    const flushAt = args.indexOf('flushPendingSave')
    const readAt = args.indexOf('readStoreProjection')
    expect(flushAt).toBeGreaterThanOrEqual(0)
    expect(readAt).toBeGreaterThan(flushAt)
  })

  it('sheetKey 锁死 D4-5 managed 身份', () => {
    expect(args).toMatch(/sheetKey:\s*['"]d45-managed['"]/)
    expect(hostSrc).not.toContain('d45-policy')
  })

  it('模板挂载了 WorkpaperSyncEditorHost', () => {
    expect(hostSrc).toContain('<WorkpaperSyncEditorHost')
  })

  it('不得再挂裸 GtOnlyOfficeSheet', () => {
    expect(hostSrc).not.toMatch(/<GtOnlyOfficeSheet\b/)
  })
})

describe('守卫自检（防恒真）', () => {
  it('extractBridgeCallArgs 抓到真实调用体', () => {
    const stub = "const b = useD4SyncMode({ sheetKey: 'd45-managed', flushHtml: async () => {} })"
    expect(extractBridgeCallArgs(stub)).toContain('flushHtml')
    expect(extractBridgeCallArgs('no bridge here')).toBe('')
  })
})

describe('父级 GtD4OperatingRevenue 不得把 D4-5 并入 isD4DetailSheet', () => {
  const parentSrc = stripComments(read(PARENT))

  it('D4_SHEET_KEY_BY_CODE 不含 D4-5', () => {
    const blockMatch = parentSrc.match(/D4_SHEET_KEY_BY_CODE[\s\S]*?\}/)
    expect(blockMatch).toBeTruthy()
    expect(blockMatch![0]).not.toMatch(/['"]D4-5['"]/)
  })

  it('D4-5 从父级 OO / 工具条路径排除', () => {
    expect(parentSrc).toMatch(/currentSheet\s*!==\s*['"]D4-5['"]/)
    expect(parentSrc).toContain('<D4TabPolicyCheck')
  })
})
