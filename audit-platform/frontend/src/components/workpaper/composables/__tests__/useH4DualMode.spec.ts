/**
 * useH4DualMode — 单元测试
 *
 * 🔴 改造前本文件 stub 的是**全局 `fetch`**，而实现早已改用 `http.get`
 * （带鉴权，源码注释明写「对齐 K10/K12 范式」）→ stub 完全不生效、
 * `http.get` 在测试环境抛错被 catch 成 `false` ⇒ 第一个用例长期红且零信号
 * （「OO 健康检查后可切换」这条断言从未真正验证过任何实现行为）。
 * 现改为 mock `@/utils/http`，并保留一条反向自检钉住「实现必须走 http 而非 fetch」。
 *
 * spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import fs from 'node:fs'
import path from 'node:path'

// 🔴 mock 必须在被测模块 import 之前声明（vitest 会提升 vi.mock）
const httpGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: unknown[]) => httpGet(...args),
  },
}))

import { useH4DualMode } from '../useH4DualMode'

describe('useH4DualMode', () => {
  beforeEach(() => {
    localStorage.clear()
    httpGet.mockReset()
    // 平台 http 拦截器已解包一层 {code,data} → 业务体在 res.data
    httpGet.mockResolvedValue({ data: { healthy: true } })
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('默认 html，OO 健康检查后可切换', async () => {
    const autoSave = vi.fn(async () => {})
    const reloadAll = vi.fn(async () => {})
    const api = useH4DualMode({
      wpId: ref('wp-h4'),
      autoSave,
      reloadAll,
    })
    expect(api.currentMode.value).toBe('html')
    await api.checkOoHealth()
    expect(api.isOoAvailable.value).toBe(true)
    await api.switchMode('onlyoffice')
    expect(autoSave).toHaveBeenCalled()
    expect(api.currentMode.value).toBe('onlyoffice')
    expect(localStorage.getItem('h4-dual-mode:wp-h4')).toBe('onlyoffice')
    await api.switchMode('html')
    expect(reloadAll).toHaveBeenCalled()
    expect(api.currentMode.value).toBe('html')
  })

  it('健康检查走带鉴权的 http.get，且命中 OO 健康端点', async () => {
    const api = useH4DualMode({ wpId: ref('wp-h4') })
    await api.checkOoHealth()
    expect(httpGet).toHaveBeenCalledTimes(1)
    expect(String(httpGet.mock.calls[0][0])).toContain('onlyoffice/health')
  })

  it('兼容未解包形态（res.healthy）', async () => {
    httpGet.mockResolvedValue({ healthy: true })
    const api = useH4DualMode({ wpId: ref('wp-h4') })
    expect(await api.checkOoHealth()).toBe(true)
  })

  it('OO 不可用时拒绝切到 onlyoffice', async () => {
    httpGet.mockResolvedValue({ data: { healthy: false } })
    const api = useH4DualMode({ wpId: ref('wp-h4') })
    await api.checkOoHealth()
    expect(api.isOoAvailable.value).toBe(false)
    await api.switchMode('onlyoffice')
    expect(api.currentMode.value).toBe('html')
  })

  it('请求抛错 → 判不可用（fail-closed，不误判为可用）', async () => {
    httpGet.mockRejectedValue(new Error('network down'))
    const api = useH4DualMode({ wpId: ref('wp-h4') })
    expect(await api.checkOoHealth()).toBe(false)
    expect(api.isOoAvailable.value).toBe(false)
  })

  it('🔴 反向自检：实现不得回退成裸 fetch（否则鉴权丢失且本文件 mock 失效）', () => {
    // 双哨兵向上找 REPO_ROOT（禁写死回退级数）
    let dir = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
    let root = ''
    for (let i = 0; i < 12; i += 1) {
      if (
        fs.existsSync(path.join(dir, 'backend', 'app', 'main.py')) &&
        fs.existsSync(path.join(dir, 'audit-platform', 'frontend', 'package.json'))
      ) {
        root = dir
        break
      }
      dir = path.dirname(dir)
    }
    expect(root).not.toBe('')
    const src = fs.readFileSync(
      path.join(
        root,
        'audit-platform/frontend/src/components/workpaper/composables/useH4DualMode.ts',
      ),
      'utf-8',
    )
    // 剥注释后判定（注释里会引用被禁写法）
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
    expect(code).toMatch(/http\.get\s*\(/)
    expect(code).not.toMatch(/\bfetch\s*\(/)
  })
})
