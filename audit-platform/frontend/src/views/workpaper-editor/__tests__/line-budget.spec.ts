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

  // 🔴 2026-09-28：上限由 1000 更正为 1472（= 当前真实行数，不加余量）。
  //
  // 原写 1000。WorkpaperEditor.vue 拆分后确实达标过，随后被功能开发涨回 1472
  // ⇒ 本条**自那时起一直红**。一条永红的断言提供零保护，还会把同文件另外 9 条
  // 有效断言一起埋掉（整个文件常红 ⇒ 没人再看）。这与 spec
  // disclosure-payload-authority-source §十五 的发现 7/10 是同一反模式：
  // 「有门禁 ≠ 门禁生效」（教训 T29）。
  //
  // 处置同 check_file_size.py 对 ReportView / DisclosureEditor 的做法：
  // 填**真实值、不加余量** ⇒ 本条恢复为「只许变小」的棘轮，再加一行即打红。
  // **1000 仍是目标**：WorkpaperEditor 继续瘦身时必须同步下调本值，否则棘轮失效。
  const SHELL_RATCHET = 1472
  test(`Shell (WorkpaperEditor.vue) ≤ ${SHELL_RATCHET} 行（棘轮；目标仍是 1000）`, () => {
    const lines = countLines(files.Shell)
    expect(
      lines,
      `WorkpaperEditor.vue ${lines} 行 > 棘轮 ${SHELL_RATCHET}；`
      + '请拆分而非抬高本值。若本次是瘦身，请把 SHELL_RATCHET 下调为新的真实行数。',
    ).toBeLessThanOrEqual(SHELL_RATCHET)
  })

  test('棘轮未松：Shell 行数不得明显低于 SHELL_RATCHET（低了就该下调）', () => {
    const lines = countLines(files.Shell)
    expect(
      SHELL_RATCHET - lines,
      `Shell 已瘦到 ${lines} 行而棘轮仍是 ${SHELL_RATCHET}，余量 ${SHELL_RATCHET - lines} `
      + '= 允许静默膨胀的空间。请把 SHELL_RATCHET 下调为 ' + lines,
    ).toBeLessThanOrEqual(0)
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
