import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const COMPOSABLES = resolve(__dirname, '../../composables')
const HOSTS = resolve(__dirname, '../..')
const CASES = [
  ['useF2SpecialDualMode.ts', 'GtF2InventorySpecial.vue'],
  ['useF2ValuationDualMode.ts', 'GtF2InventoryValuation.vue'],
] as const

function source(path: string): string {
  return readFileSync(path, 'utf-8')
}

function returnedObject(text: string): string {
  const matches = [...text.matchAll(/return\s*\{([^}]+)\}/g)]
  return matches.at(-1)?.[1] || ''
}

describe('F2 双模式公开面与宿主调用一致', () => {
  for (const [composable, host] of CASES) {
    it(`${composable} 向调用 switchMode 的 ${host} 公开该函数`, () => {
      const composableSource = source(resolve(COMPOSABLES, composable))
      const hostSource = source(resolve(HOSTS, host))
      expect(composableSource).toMatch(/async function switchMode\s*\(/)
      expect(hostSource).toContain('dualMode.switchMode(')
      expect(returnedObject(composableSource)).toMatch(/\bswitchMode\b/)
    })
  }

  it('守卫能识别“定义了但未返回”的旧缺陷形态', () => {
    const broken = 'async function switchMode() {}\nreturn { currentMode, onModeChange }'
    expect(broken).toMatch(/async function switchMode\s*\(/)
    expect(returnedObject(broken)).not.toMatch(/\bswitchMode\b/)
  })
})


const LEGACY_SWITCHERS = [
  'useWorkpaperEntryDualMode.ts',
  'useD4DualMode.ts',
  'useF2DualMode.ts',
  'useF2SpecialDualMode.ts',
  'useF2ValuationDualMode.ts',
  'useF2StocktakeDualMode.ts',
  'useF3DualMode.ts',
  'useF4DualMode.ts',
  'useF5CosOfDualMode.ts',
] as const

describe('所有承载已登记 writer 的 legacy OO 入口都有保存屏障', () => {
  for (const file of LEGACY_SWITCHERS) {
    it(`${file} 把进入 OO 的实际模式赋值包在完整过渡屏障内`, () => {
      const text = source(resolve(COMPOSABLES, file))
      expect(text).toContain("import { runLegacyOnlyOfficeTransition }")
      const start = text.indexOf('function switchMode')
      const switchBody = text.slice(start, start + 5000)
      expect(switchBody).toMatch(
        /target === 'onlyoffice'[\s\S]*await runLegacyOnlyOfficeTransition\(async \(\) => \{[\s\S]*(?:currentMode|mode)\.value = 'onlyoffice'/,
      )
    })
  }

  it('G 循环显式切换与 mounted 自动恢复都进入同一完整屏障', () => {
    const text = source(resolve(HOSTS, 'sync/useGRenderModeSwitch.ts'))
    expect(text).toContain('return runLegacyOnlyOfficeTransition(async () => {')
    const switchStart = text.indexOf('async function switchRenderMode')
    const branchStart = text.indexOf('if (!isManagedSheet.value)', switchStart)
    const branch = text.slice(branchStart, branchStart + 900)
    expect(branch).toContain("target === 'onlyoffice'")
    expect(branch).toContain('await enterLegacyOnlyOffice()')
    expect(text).toMatch(/watch\(\s*\(\) => legacy\.currentMode\.value/)
    expect(text).toContain("legacy.currentMode.value = 'html'")
    expect(text).not.toContain('mayEnterLegacyOnlyOffice')
  })
})

describe('F2 监盘切换保存契约', () => {
  it('只用平台 flusher、同步只看业务只读，父事件可 reject', () => {
    const sheet = source(resolve(COMPOSABLES, 'useF2StocktakeSheet.ts'))
    const host = source(resolve(HOSTS, 'GtF2StocktakeBundle.vue'))
    const dual = source(resolve(COMPOSABLES, 'useF2StocktakeDualMode.ts'))

    expect(sheet).not.toContain('_fieldFlushers')
    expect(sheet.match(/registerPendingFlusher\(flushPending\)/g)).toHaveLength(2)
    expect(host).not.toContain('flushAllF2StocktakeFields')
    expect(host).toContain('readonly: businessReadonly')
    expect(host).toContain('detail.reject?.(error)')
    expect(host).not.toContain('detail?.done?.()')
    expect(dual).toContain('if (!(await syncDocToOo())) return')
    expect(dual).toContain('if (!(await syncDocFromOo())) return')
  })
})
