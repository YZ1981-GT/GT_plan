import { describe, test, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

/**
 * 行数预算断言测试
 *
 * Validates: Requirements 1.6, 13.1
 *
 * 拆分后 Shell + 所有新建子 SFC 的总行数 ≤ 2748 × 1.2 = 3298
 * 各文件独立行数上限确保不会反向膨胀回 god component。
 */

const WORKPAPER_EDITOR_DIR = resolve(__dirname, '..')
const VIEWS_DIR = resolve(__dirname, '..', '..')

function countLines(filePath: string): number {
  const content = readFileSync(filePath, 'utf-8')
  return content.split('\n').length
}

describe('行数预算断言测试', () => {
  const files = {
    Shell: resolve(VIEWS_DIR, 'WorkpaperEditor.vue'),
    UniverEditorCore: resolve(WORKPAPER_EDITOR_DIR, 'UniverEditorCore.vue'),
    CycleDialogHost: resolve(WORKPAPER_EDITOR_DIR, 'CycleDialogHost.vue'),
    CycleTriggerPanel: resolve(WORKPAPER_EDITOR_DIR, 'CycleTriggerPanel.vue'),
    EditorBanners: resolve(WORKPAPER_EDITOR_DIR, 'EditorBanners.vue'),
    EditorStatusBar: resolve(WORKPAPER_EDITOR_DIR, 'EditorStatusBar.vue'),
    VersionHistoryDrawer: resolve(WORKPAPER_EDITOR_DIR, 'VersionHistoryDrawer.vue'),
    AuditNavDialog: resolve(WORKPAPER_EDITOR_DIR, 'AuditNavDialog.vue'),
    ReviewMarkDialog: resolve(WORKPAPER_EDITOR_DIR, 'ReviewMarkDialog.vue'),
  }

  test('Shell (WorkpaperEditor.vue) ≤ 1000 行', () => {
    const lines = countLines(files.Shell)
    expect(lines).toBeLessThanOrEqual(1000)
  })

  test('UniverEditorCore.vue ≤ 800 行', () => {
    const lines = countLines(files.UniverEditorCore)
    expect(lines).toBeLessThanOrEqual(800)
  })

  test('CycleDialogHost.vue ≤ 200 行', () => {
    const lines = countLines(files.CycleDialogHost)
    expect(lines).toBeLessThanOrEqual(200)
  })

  test('CycleTriggerPanel.vue ≤ 150 行', () => {
    const lines = countLines(files.CycleTriggerPanel)
    expect(lines).toBeLessThanOrEqual(150)
  })

  test('EditorBanners.vue ≤ 200 行', () => {
    const lines = countLines(files.EditorBanners)
    expect(lines).toBeLessThanOrEqual(200)
  })

  test('EditorStatusBar.vue ≤ 120 行', () => {
    const lines = countLines(files.EditorStatusBar)
    expect(lines).toBeLessThanOrEqual(120)
  })

  test('VersionHistoryDrawer.vue ≤ 120 行', () => {
    const lines = countLines(files.VersionHistoryDrawer)
    expect(lines).toBeLessThanOrEqual(120)
  })

  test('AuditNavDialog.vue ≤ 80 行', () => {
    const lines = countLines(files.AuditNavDialog)
    expect(lines).toBeLessThanOrEqual(80)
  })

  test('ReviewMarkDialog.vue ≤ 120 行', () => {
    const lines = countLines(files.ReviewMarkDialog)
    expect(lines).toBeLessThanOrEqual(120)
  })

  test('总行数 ≤ 3298（2748 × 1.2）', () => {
    const totalLines = Object.values(files).reduce((sum, filePath) => {
      return sum + countLines(filePath)
    }, 0)
    expect(totalLines).toBeLessThanOrEqual(3298)
  })
})
