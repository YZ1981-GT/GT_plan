/**
 * G7 宿主接线守卫 —— G4-1 canary：国企附注必须走统一桥，不得再挂 pilot adapter。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(__dirname, '..', 'GtG7LongTermEquityMain.vue')
const SOE = resolve(
  __dirname,
  '..',
  'g7-long-term-equity-main',
  'disclosure',
  'G7TabDisclosureSOE.vue',
)

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

describe('G7 宿主必须接到统一 useWorkpaperSyncBridge（G4-1 SOE canary）', () => {
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

  it('entryId / sheetKey 锁死 G7 managed 身份', () => {
    expect(hostSrc).toContain('xlsx/gt-g7-long-term-equity-main')
    expect(hostSrc).toContain('g7n-managed')
  })
})

describe('G7 SOE OO 挂载必须走 WorkpaperSyncEditorHost', () => {
  const hostSrc = stripComments(read(HOST))

  it('模板挂载了 WorkpaperSyncEditorHost', () => {
    expect(hostSrc).toContain('<WorkpaperSyncEditorHost')
  })

  it('SOE 门控与 descriptor/bridge 传入', () => {
    expect(hostSrc).toMatch(/isSoeDisclosureSheet/)
    expect(hostSrc).toMatch(/:descriptor=/)
    expect(hostSrc).toMatch(/:bridge=/)
  })

  it('capability 现算，禁止内联 bidirectional 字面量给桥', () => {
    expect(hostSrc).toMatch(/capabilityForEntry\s*\(\s*G7_SYNC_ENTRY_ID\s*\)/)
  })
})

describe('G7TabDisclosureSOE 必须 expose flushPendingSave', () => {
  const soeSrc = stripComments(read(SOE))

  it('定义并 expose flushPendingSave', () => {
    expect(soeSrc).toMatch(/async function flushPendingSave/)
    expect(soeSrc).toMatch(/defineExpose\s*\(\s*\{\s*flushPendingSave/)
  })
})
