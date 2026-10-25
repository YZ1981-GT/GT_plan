/**
 * D4-5 宿主接线守卫 —— 独立 sync host，不并入父级 isD4DetailSheet。
 *
 * spec: d-cycle-sheet-bidirectional-expansion · paragraph_block_bidirectional
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
  const marker = 'useWorkpaperSyncBridge('
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

describe('D4-5 tab 必须自管 useWorkpaperSyncBridge（独立宿主）', () => {
  const hostSrc = stripComments(read(TAB))
  const args = extractBridgeCallArgs(hostSrc)

  it('tab 确实调用了 useWorkpaperSyncBridge', () => {
    expect(args.length).toBeGreaterThan(0)
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

  it('entryId / sheetKey 锁死 D4-5 managed 身份', () => {
    expect(hostSrc).toContain('xlsx/gt-d4-operating-revenue')
    expect(hostSrc).toContain('d45-managed')
    expect(hostSrc).not.toContain('d45-policy')
  })

  it('模板挂载了 WorkpaperSyncEditorHost', () => {
    expect(hostSrc).toContain('<WorkpaperSyncEditorHost')
  })

  it('不得再挂裸 GtOnlyOfficeSheet', () => {
    expect(hostSrc).not.toMatch(/<GtOnlyOfficeSheet\b/)
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
