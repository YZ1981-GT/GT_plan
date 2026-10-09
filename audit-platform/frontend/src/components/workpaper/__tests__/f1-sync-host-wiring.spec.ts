import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { managedSheetsForEntry } from '../sync/workpaperSyncManagedSheets.generated'

const ENTRY_ID = 'xlsx/gt-f1-prepayment'
const source = readFileSync(resolve(__dirname, '../GtF1Prepayment.vue'), 'utf-8')

/** 仅检查源码契约时先剔除注释，避免注释中的旧实现让守卫误报。 */
function codeOnly(text: string): string {
  return text
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const code = codeOnly(source)

function sliceBetween(startMarker: string, endMarker: string): string {
  const start = code.indexOf(startMarker)
  const end = code.indexOf(endMarker, start)
  expect(start, `缺少源码锚点：${startMarker}`).toBeGreaterThanOrEqual(0)
  expect(end, `缺少源码锚点：${endMarker}`).toBeGreaterThan(start)
  return code.slice(start, end)
}

describe('F1 宿主双向同步接线契约', () => {
  it('从生成受管清单按 excelName/sheetKey 派生映射，不保留单张硬编码', () => {
    expect(managedSheetsForEntry(ENTRY_ID).length).toBeGreaterThan(0)
    expect(code).toContain(
      "import { managedSheetsForEntry } from './sync/workpaperSyncManagedSheets.generated'",
    )
    expect(code).toContain('managedSheetsForEntry(F1_SYNC_ENTRY_ID)')
    expect(code).toContain('sheet.excelName')
    expect(code).toContain('sheet.sheetKey')
    expect(code).toMatch(/const F1_MANAGED_SHEET_BY_CODE:\s*ReadonlyMap<string, string>/)
    expect(code).toMatch(/const syncSheetKey = computed\(/)
    expect(code).not.toContain('F1_SHEET_KEY_BY_CODE')
    expect(code).not.toContain("'f16-managed'")
  })

  it('F1-2 非三年段不进入受管路径，并显示明确中文原因', () => {
    expect(code).toContain("agingScope.preset.value === 'THREE_YEAR'")
    expect(code).toContain('isF1AgingSyncCompatible.value')
    expect(code).toContain('f1SyncManagedDisabledReason')
    expect(code).toContain('受管双向同步仅支持三年段')
  })

  it('切到 OO 前严格等待 F1 保存队列，再读取 store projection', () => {
    const flush = sliceBetween('flushHtml: async () =>', 'reloadHtml: async')
    expect(flush).toContain('await formData.flushPendingSave()')
    expect(flush.indexOf('await formData.flushPendingSave()')).toBeLessThan(
      flush.indexOf('readStoreProjection('),
    )
  })

  it('OO 应用后按最低 revision 校验，版本不足不得加载旧 HTML', () => {
    const reload = sliceBetween('reloadHtml: async (minimumRevision: number)', 'const syncOoDescriptor')
    expect(reload).toContain('snap.expectedRevision < minimumRevision')
    expect(reload).toContain('throw new Error(')
    expect(reload.indexOf('snap.expectedRevision < minimumRevision')).toBeLessThan(
      reload.indexOf('await formData.loadAll()'),
    )
  })

  it('脏且不可强制保存时保持 OO，不得持久化 HTML 模式', () => {
    const switcher = sliceBetween('async function switchRenderMode', 'provide(\'reloadWorkpaperData\'')
    const warningIndex = switcher.indexOf('ElMessage.warning(')
    expect(warningIndex).toBeGreaterThanOrEqual(0)
    expect(switcher.slice(warningIndex)).not.toContain("persistMode('html')")

    // 变异自检：把安全分支换回旧的静默 persistMode，守卫必须能识别。
    const unsafeFallback = (text: string): boolean =>
      /else\s*\{[\s\S]*?syncBridge\.persistMode\('html'\)/.test(text)
    expect(unsafeFallback(switcher)).toBe(false)

    // 变异自检：把安全分支换回旧的静默 persistMode，判据必须识别为不安全。
    const mutated = switcher.replace(
      /ElMessage\.warning\([\s\S]*?\)/,
      "syncBridge.persistMode('html')",
    )
    expect(unsafeFallback(mutated)).toBe(true)
  })
})
