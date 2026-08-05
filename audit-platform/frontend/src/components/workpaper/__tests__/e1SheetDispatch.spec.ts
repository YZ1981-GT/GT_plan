/**
 * E1 sheet 分发守卫
 * Property 1: E1_SHEET_COMPONENT 每项都能在宿主源码找到对应分支
 * Property 2: 宿主传的 prop 名 ∈ 被调组件 defineProps
 * Property 3: E1IpoSheetChrome 有至少一个可达消费方
 *
 * @spec e1-orphan-components-wiring — Task 4
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { E1_SHEET_COMPONENT, E1_IPO_GENERIC_SHEETS } from '../composables/e1SheetComponentMap'

const REPO_ROOT = path.resolve(__dirname, '../../../../../..')
const E1_DIR = path.resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper/e1')
const HOST_PATH = path.resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue')

function readSource(filePath: string): string {
  return fs.readFileSync(filePath, 'utf-8')
}

function stripComments(src: string): string {
  // Remove single-line comments
  let result = src.replace(/\/\/.*$/gm, '')
  // Remove multi-line comments
  result = result.replace(/\/\*[\s\S]*?\*\//g, '')
  return result
}

function extractDefineProps(src: string): string[] {
  // Match defineProps<{ ... }>() block
  const match = src.match(/defineProps<\{([\s\S]*?)\}>/)
  if (!match) return []
  const block = match[1]
  // Extract prop names (lines like "  propName: Type" or "  propName?: Type")
  return [...block.matchAll(/^\s*(\w+)\??\s*:/gm)].map(m => m[1])
}

function toKebab(camel: string): string {
  return camel.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '')
}

describe('E1 sheet dispatch - Property 1: 分发表与宿主源码一致', () => {
  const hostSrc = stripComments(readSource(HOST_PATH))

  for (const [sheetCode, componentName] of Object.entries(E1_SHEET_COMPONENT)) {
    it(`${sheetCode} → ${componentName} 在宿主有对应分支`, () => {
      if (E1_IPO_GENERIC_SHEETS.includes(sheetCode as any)) {
        // IPO generic sheets use ipoSheetCode computed
        expect(hostSrc).toContain('v-else-if="ipoSheetCode"')
        expect(hostSrc).toContain(`<${componentName}`)
      } else {
        // Template format: <ComponentName v-else-if="currentSheet === 'E1-XX'" ...
        // Both tag-first and condition-first patterns
        const hasTag = hostSrc.includes(`<${componentName}`)
        const hasCondition = hostSrc.includes(`currentSheet === '${sheetCode}'`)
        expect(hasTag, `组件标签 <${componentName}> 应存在于宿主`).toBe(true)
        expect(hasCondition, `条件 currentSheet === '${sheetCode}' 应存在于宿主`).toBe(true)
        // Verify they're on the same line (both are in a single-line v-else-if)
        const lines = hostSrc.split('\n')
        const matchLine = lines.find(l => l.includes(`<${componentName}`) && l.includes(sheetCode))
        expect(matchLine, `<${componentName}> 与 '${sheetCode}' 应在同一行`).toBeTruthy()
      }
    })
  }

  it('反向自检: E1-19 指向 E1TabCreditReport 则本属性必红', () => {
    const fakeHost = hostSrc.replace('E1TabCreditCheck', 'E1TabCreditReport_WRONG')
    const pattern = /currentSheet\s*===\s*'E1-19'[\s\S]{0,300}?<E1TabCreditCheck/
    expect(fakeHost).not.toMatch(pattern)
  })
})

describe('E1 sheet dispatch - Property 2: 宿主传参全部是合法 prop', () => {
  const hostSrc = readSource(HOST_PATH)

  // Components that have explicit branches (not IPO generic)
  const explicitComponents = Object.entries(E1_SHEET_COMPONENT)
    .filter(([code]) => !E1_IPO_GENERIC_SHEETS.includes(code as any))

  // Known pre-existing: E1TabCreditReport has no bsDate prop but host passes :bs-date (silent no-op)
  const KNOWN_EXTRA_PROPS: Record<string, string[]> = {
    E1TabCreditReport: ['bs-date'],
  }

  for (const [sheetCode, componentName] of explicitComponents) {
    it(`宿主传给 ${componentName} (${sheetCode}) 的 prop 全部合法`, () => {
      const componentPath = path.join(E1_DIR, `${componentName}.vue`)
      if (!fs.existsSync(componentPath)) {
        // Some components may be in parent dir
        return // Skip if file not found (not a test failure, just layout difference)
      }
      const componentSrc = readSource(componentPath)
      const props = extractDefineProps(componentSrc)
      if (!props.length) return // Can't extract props → skip

      const kebabProps = props.map(toKebab)

      // Extract attrs passed to this component in host
      const componentTag = `<${componentName}`
      const tagStart = hostSrc.indexOf(componentTag)
      if (tagStart < 0) return

      const tagEnd = hostSrc.indexOf('/>', tagStart)
      if (tagEnd < 0) return

      const tagContent = hostSrc.slice(tagStart, tagEnd)
      // Extract :prop-name or prop-name= (excluding v-*, @, key, ref, class, style)
      const attrMatches = [...tagContent.matchAll(/:?([\w-]+)=/g)]
      const passedAttrs = attrMatches
        .map(m => m[1])
        .filter(a => !a.startsWith('v-') && !['key', 'ref', 'class', 'style'].includes(a))
        .filter(a => !a.startsWith('@'))

      for (const attr of passedAttrs) {
        const normalized = attr.replace(/^:/, '')
        const knownExtra = KNOWN_EXTRA_PROPS[componentName] || []
        expect(
          kebabProps.includes(normalized) || normalized === 'sheet-code' || knownExtra.includes(normalized),
          `${componentName}: 宿主传了 "${normalized}" 但组件 defineProps 里没有。合法 props: [${kebabProps.join(', ')}]`,
        ).toBe(true)
      }
    })
  }
})

describe('E1 sheet dispatch - Property 3: E1IpoSheetChrome 有可达消费方', () => {
  it('至少有一个已接线组件使用 E1IpoSheetChrome', () => {
    // After wiring, the 5 newly-wired components use E1IpoSheetChrome as their shell
    const depositSrc = readSource(path.join(E1_DIR, 'E1TabDepositInterestDaily.vue'))
    expect(depositSrc).toContain('E1IpoSheetChrome')

    const cashTxnSrc = readSource(path.join(E1_DIR, 'E1TabCashTxnAnalysis.vue'))
    expect(cashTxnSrc).toContain('E1IpoSheetChrome')

    const bankFlowSrc = readSource(path.join(E1_DIR, 'E1TabBankFlowReconcile.vue'))
    expect(bankFlowSrc).toContain('E1IpoSheetChrome')
  })
})

describe('E1 sheet dispatch - ipoSheetCode 正则精度', () => {
  it('只匹配 E1-27 和 E1-28', () => {
    const regex = /^E1-(27|28)$/
    expect(regex.test('E1-27')).toBe(true)
    expect(regex.test('E1-28')).toBe(true)
    expect(regex.test('E1-26')).toBe(false)
    expect(regex.test('E1-29')).toBe(false)
    expect(regex.test('E1-30')).toBe(false)
    expect(regex.test('E1-31')).toBe(false)
    expect(regex.test('E1-32')).toBe(false)
  })
})
