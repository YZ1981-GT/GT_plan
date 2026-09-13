/**
 * B60 宿主接线守卫 —— G4-1 canary：B60-1 工时表必须走统一桥。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(__dirname, '..', 'b60', 'GtB60Bundle.vue')

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('B60 宿主必须接到统一 useWorkpaperSyncBridge（G4-1 B60-1 canary）', () => {
  const hostSrc = stripComments(read(HOST))

  it('宿主确实调用了 useWorkpaperSyncBridge', () => {
    expect(hostSrc).toMatch(/useWorkpaperSyncBridge\s*\(/)
  })

  it('模板挂载了 WorkpaperSyncEditorHost 与工时面板', () => {
    expect(hostSrc).toContain('<WorkpaperSyncEditorHost')
    expect(hostSrc).toContain('GtB60HourBudgetPanel')
  })

  it('entryId / sheetKey 锁死 B60 managed 身份', () => {
    expect(hostSrc).toContain('xlsx/b60/gt-b60-bundle')
    expect(hostSrc).toContain('b601-managed')
  })

  it('桥绑定的是 B60-1 子底稿 wpId（不是主 B60）', () => {
    expect(hostSrc).toMatch(/b601WpId/)
    expect(hostSrc).toMatch(/wpIdMap\.value\[['"]B60-1['"]\]/)
  })
})
