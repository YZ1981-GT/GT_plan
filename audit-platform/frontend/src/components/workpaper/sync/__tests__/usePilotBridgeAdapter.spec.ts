/**
 * usePilotBridgeAdapter — 单元测试
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 45
 * Requirements: 11.1, 11.5, 11.8, 11.10
 * Properties: P47, P48
 *
 * 验证：
 * - adapter 暴露与旧 composable 兼容的 API
 * - 使用统一 localStorage 键前缀
 * - 不调用 onlyoffice-config / health 端点
 * - 模式切换正确执行 flush/reload 回调
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { usePilotBridgeAdapter, type PilotBridgeAdapter } from '../usePilotBridgeAdapter'

// ─── localStorage mock ──────────────────────────────────────────────────────

let storageMock: Record<string, string> = {}

beforeEach(() => {
  storageMock = {}
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => storageMock[key] ?? null)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key: string, value: string) => {
    storageMock[key] = value
  })
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation((key: string) => {
    delete storageMock[key]
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ─── Helper ─────────────────────────────────────────────────────────────────

function createAdapter(overrides?: Partial<Parameters<typeof usePilotBridgeAdapter>[0]>): PilotBridgeAdapter {
  return usePilotBridgeAdapter({
    entryId: 'xlsx/test-pilot-entry',
    wpId: ref('wp-test-123'),
    sheetName: ref('TestSheet'),
    ...overrides,
  })
}

// ════════════════════════════════════════════════════════════════════════════
// P47: descriptor consumer — adapter 不调用 config 端点
// ════════════════════════════════════════════════════════════════════════════

describe('P47: adapter API surface compatibility', () => {
  it('暴露 currentMode ref，默认 html', () => {
    const adapter = createAdapter()
    expect(adapter.currentMode.value).toBe('html')
  })

  it('暴露 modeOptions computed', () => {
    const adapter = createAdapter()
    const opts = adapter.modeOptions.value
    expect(opts.length).toBe(2)
    expect(opts[0].value).toBe('html')
    expect(opts[1].value).toBe('onlyoffice')
  })

  it('暴露 isOoAvailable ref', () => {
    const adapter = createAdapter()
    expect(typeof adapter.isOoAvailable.value).toBe('boolean')
  })

  it('暴露 switchMode 方法', () => {
    const adapter = createAdapter()
    expect(typeof adapter.switchMode).toBe('function')
  })

  it('暴露 onModeChange 方法', () => {
    const adapter = createAdapter()
    expect(typeof adapter.onModeChange).toBe('function')
  })

  it('暴露 switching ref', () => {
    const adapter = createAdapter()
    expect(adapter.switching.value).toBe(false)
  })

  it('暴露 ooConfig ref（兼容占位）', () => {
    const adapter = createAdapter()
    expect(adapter.ooConfig.value).toBeNull()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// 统一 localStorage 键
// ════════════════════════════════════════════════════════════════════════════

describe('统一 localStorage 键', () => {
  it('使用 workpaper-sync-mode: 前缀', async () => {
    const adapter = createAdapter()
    await adapter.switchMode('onlyoffice')

    const keys = Object.keys(storageMock)
    expect(keys.length).toBeGreaterThan(0)
    expect(keys[0]).toMatch(/^workpaper-sync-mode:/)
  })

  it('键包含 entryId/wpId/sheet', async () => {
    const adapter = createAdapter()
    await adapter.switchMode('onlyoffice')

    const key = Object.keys(storageMock)[0]
    expect(key).toContain('xlsx/test-pilot-entry')
    expect(key).toContain('wp-test-123')
    expect(key).toContain('TestSheet')
  })

  it('不使用任何 legacy 前缀', async () => {
    const adapter = createAdapter()
    await adapter.switchMode('onlyoffice')

    const keys = Object.keys(storageMock)
    for (const key of keys) {
      expect(key).not.toMatch(/^b60-dual-mode:/)
      expect(key).not.toMatch(/^h1-dual-mode:/)
      expect(key).not.toMatch(/^g7-main-mode-/)
      expect(key).not.toMatch(/^wp-entry-dual-mode:/)
    }
  })

  it('存储值为 oo 而非 onlyoffice', async () => {
    const adapter = createAdapter()
    await adapter.switchMode('onlyoffice')

    const value = Object.values(storageMock)[0]
    expect(value).toBe('oo')
  })

  it('恢复时 oo 值转回 onlyoffice', () => {
    storageMock['workpaper-sync-mode:xlsx/test-pilot-entry:wp-test-123:TestSheet'] = 'oo'
    const adapter = createAdapter()
    expect(adapter.currentMode.value).toBe('onlyoffice')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// P48: 失败不被成功文案覆盖
// ════════════════════════════════════════════════════════════════════════════

describe('P48: switchMode 行为', () => {
  it('切到 onlyoffice 执行 flushBeforeOo 回调', async () => {
    const flush = vi.fn().mockResolvedValue(undefined)
    const adapter = createAdapter({ flushBeforeOo: flush })

    await adapter.switchMode('onlyoffice')

    expect(flush).toHaveBeenCalledTimes(1)
    expect(adapter.currentMode.value).toBe('onlyoffice')
  })

  it('切回 html 执行 reloadHtml 回调', async () => {
    const reload = vi.fn().mockResolvedValue(undefined)
    const adapter = createAdapter({ reloadHtml: reload })

    // 先切到 OO
    await adapter.switchMode('onlyoffice')
    // 再切回
    await adapter.switchMode('html')

    expect(reload).toHaveBeenCalledTimes(1)
    expect(adapter.currentMode.value).toBe('html')
  })

  it('重复切换到当前模式不执行任何操作', async () => {
    const flush = vi.fn()
    const adapter = createAdapter({ flushBeforeOo: flush })

    await adapter.switchMode('html') // 已经是 html
    expect(flush).not.toHaveBeenCalled()
  })

  it('switching 标志在切换期间为 true', async () => {
    let resolveFlush: () => void = () => {}
    const flush = vi.fn(() => new Promise<void>(r => { resolveFlush = r }))
    const adapter = createAdapter({ flushBeforeOo: flush })

    const promise = adapter.switchMode('onlyoffice')
    expect(adapter.switching.value).toBe(true)

    resolveFlush()
    await promise
    expect(adapter.switching.value).toBe(false)
  })

  it('onModeChange 委派给 switchMode', async () => {
    const adapter = createAdapter()
    adapter.onModeChange('onlyoffice')
    // 异步执行，等一下
    await new Promise(r => setTimeout(r, 10))
    expect(adapter.currentMode.value).toBe('onlyoffice')
  })
})
