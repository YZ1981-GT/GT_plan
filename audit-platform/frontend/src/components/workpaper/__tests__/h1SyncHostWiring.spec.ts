/**
 * H1 宿主接线守卫 —— G4-1 canary：H1-8 必须走统一桥，不得再挂 pilot adapter。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(__dirname, '..', 'GtH1FixedAssets.vue')

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

describe('H1 宿主必须接到统一 useWorkpaperSyncBridge（G4-1 H1-8 canary）', () => {
  const hostSrc = stripComments(read(HOST))
  const args = extractBridgeCallArgs(hostSrc)

  it('宿主确实调用了 useWorkpaperSyncBridge', () => {
    expect(args.length).toBeGreaterThan(0)
  })

  it('不得再调用 usePilotBridgeAdapter', () => {
    expect(hostSrc).not.toMatch(/usePilotBridgeAdapter\s*\(/)
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

  it('entryId / sheetKey 锁死 H1 managed 身份', () => {
    expect(hostSrc).toContain('xlsx/gt-h1-fixed-assets')
    expect(hostSrc).toContain('h18-managed')
  })
})

describe('H1-8 OO 挂载必须走 WorkpaperSyncEditorHost', () => {
  const hostSrc = stripComments(read(HOST))

  it('模板挂载了 WorkpaperSyncEditorHost', () => {
    expect(hostSrc).toContain('<WorkpaperSyncEditorHost')
  })

  it('H1-8 门控与 descriptor/bridge 传入', () => {
    expect(hostSrc).toMatch(/isH18DisposalSheet/)
    expect(hostSrc).toMatch(/:descriptor=/)
    expect(hostSrc).toMatch(/:bridge=/)
  })

  it('capability 现算，禁止内联 bidirectional 字面量给桥', () => {
    expect(hostSrc).toMatch(/capabilityForEntry\s*\(\s*H1_SYNC_ENTRY_ID\s*\)/)
  })
})
