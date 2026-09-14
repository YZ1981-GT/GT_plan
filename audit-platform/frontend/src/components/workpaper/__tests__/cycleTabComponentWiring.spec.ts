/**
 * 平台级孤儿组件守卫
 *
 * 扫描各循环组件目录下的 *Tab*.vue，判定每个是否存在可达消费方。
 * 目的：防止「组件写好但没接线」的漂移再次发生（E1 一次攒了 8 个无人拦）。
 *
 * Property 18: 反向自检（替身孤儿必被识别）
 * Property 19: components.d.ts / __tests__ 不计为消费方
 *
 * @spec e1-orphan-components-wiring — Task 12
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

const FRONTEND_SRC = path.resolve(__dirname, '../../..')
const WP_DIR = path.resolve(FRONTEND_SRC, 'components/workpaper')

/**
 * 允许暂时为孤儿的组件（每条须写理由 ≥20 字）。
 * 已接线的条目必须移出，否则本守卫打红。
 */
const ORPHAN_ALLOWLIST: Record<string, string> = {
  // 当前 E1 循环所有 Tab 组件均已接线，allowlist 为空
}

/** 扫描 components/workpaper/{循环}/ 下的 *Tab*.vue（排除 __tests__ 目录） */
function discoverTabComponents(): string[] {
  const results: string[] = []
  const cycleDirs = fs.readdirSync(WP_DIR, { withFileTypes: true })
    .filter(d => d.isDirectory() && !d.name.startsWith('_') && d.name !== '__tests__'
      && d.name !== 'shared' && d.name !== 'composables' && d.name !== 'voucher-sampling')

  for (const dir of cycleDirs) {
    const dirPath = path.join(WP_DIR, dir.name)
    const files = fs.readdirSync(dirPath).filter(f => f.includes('Tab') && f.endsWith('.vue'))
    for (const file of files) {
      results.push(`${dir.name}/${file}`)
    }
  }
  return results
}

/** 判定某个 Tab 组件是否有可达消费方 */
function hasReachableConsumer(tabRelPath: string): boolean {
  const componentName = path.basename(tabRelPath, '.vue')
  const cycleDir = path.dirname(tabRelPath)

  // 1. 在同目录的宿主文件 (Gt*.vue) 里搜索
  const cyclePath = path.join(WP_DIR, cycleDir)
  const hosts = fs.readdirSync(cyclePath).filter(f => f.startsWith('Gt') && f.endsWith('.vue'))

  for (const host of hosts) {
    const hostSrc = fs.readFileSync(path.join(cyclePath, host), 'utf-8')
    if (hostSrc.includes(`<${componentName}`) || hostSrc.includes(`'${componentName}'`)
      || hostSrc.includes(`"./${componentName}.vue"`) || hostSrc.includes(`'./${componentName}.vue'`)) {
      return true
    }
  }

  // 2. 在父级 workpaper/ 的宿主里搜索（如 GtE1MonetaryFund.vue）
  const parentHosts = fs.readdirSync(WP_DIR)
    .filter(f => f.startsWith('Gt') && f.endsWith('.vue'))

  for (const host of parentHosts) {
    const hostSrc = fs.readFileSync(path.join(WP_DIR, host), 'utf-8')
    if (hostSrc.includes(`<${componentName}`) || hostSrc.includes(`'${componentName}'`)
      || hostSrc.includes(`'./${cycleDir}/${componentName}.vue'`)
      || hostSrc.includes(`"./${cycleDir}/${componentName}.vue"`)) {
      return true
    }
  }

  // 3. 在同目录的其他非-Tab 组件里搜索（传递消费：Chrome 壳等）
  const siblings = fs.readdirSync(cyclePath)
    .filter(f => f.endsWith('.vue') && !f.includes('Tab') && f !== path.basename(tabRelPath))
  for (const sib of siblings) {
    const sibSrc = fs.readFileSync(path.join(cyclePath, sib), 'utf-8')
    if (sibSrc.includes(`<${componentName}`) || sibSrc.includes(`'${componentName}'`)) {
      return true
    }
  }

  // 4. 被同目录其他 Tab 组件消费（传递性，如 E1IpoSheetChrome → Tab → 宿主）
  const otherTabs = fs.readdirSync(cyclePath)
    .filter(f => f.includes('Tab') && f.endsWith('.vue') && f !== path.basename(tabRelPath))
  for (const other of otherTabs) {
    const otherSrc = fs.readFileSync(path.join(cyclePath, other), 'utf-8')
    if (otherSrc.includes(`<${componentName}`) || otherSrc.includes(`'${componentName}'`)) {
      // Check if the consumer itself is reachable (avoid infinite recursion with simple depth-1)
      const consumerRel = `${cycleDir}/${other}`
      if (ORPHAN_ALLOWLIST[consumerRel]) continue // consumer is orphan too
      return true
    }
  }

  return false
}

describe('平台级孤儿组件守卫', () => {
  const allTabs = discoverTabComponents()

  it('反向自检：扫描发现了足够多的 Tab 组件（防空转）', () => {
    // E1 alone has 26, platform should have many more
    expect(allTabs.length).toBeGreaterThan(20)
  })

  it('反向自检：替身孤儿被识别', () => {
    // A fake component that doesn't exist would not be found by any consumer
    expect(hasReachableConsumer('e1/E1TabFakeOrphanForTest.vue')).toBe(false)
  })

  // Check all discovered components (only report E1 for now to avoid cross-cycle noise)
  const e1Tabs = allTabs.filter(t => t.startsWith('e1/'))

  for (const tab of e1Tabs) {
    it(`E1: ${path.basename(tab)} 有可达消费方或在 allowlist`, () => {
      if (ORPHAN_ALLOWLIST[tab]) {
        // Allowed orphan — verify reason is substantial
        expect(ORPHAN_ALLOWLIST[tab].length).toBeGreaterThanOrEqual(20)
        return
      }
      expect(
        hasReachableConsumer(tab),
        `${tab} 无可达消费方且不在 ORPHAN_ALLOWLIST。请接线或登记理由。`,
      ).toBe(true)
    })
  }

  it('ORPHAN_ALLOWLIST 中已接线的条目必须移出', () => {
    for (const [tab, reason] of Object.entries(ORPHAN_ALLOWLIST)) {
      if (hasReachableConsumer(tab)) {
        expect.fail(`${tab} 已有消费方，应从 ORPHAN_ALLOWLIST 移出（理由: ${reason}）`)
      }
    }
  })

  it('ORPHAN_ALLOWLIST 每条理由 ≥20 字', () => {
    for (const [tab, reason] of Object.entries(ORPHAN_ALLOWLIST)) {
      expect(reason.length, `${tab} 的 allowlist 理由过短`).toBeGreaterThanOrEqual(20)
    }
  })
})
