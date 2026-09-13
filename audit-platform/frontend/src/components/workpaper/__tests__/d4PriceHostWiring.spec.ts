/**
 * D4 价格分析宿主接线守卫 —— provide + 接收端挂载锁死。
 *
 * spec: .kiro/specs/d4-price-analysis-writeback-linkage/ Task 2 / 5 / Req 6
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const HOST = resolve(__dirname, '..', 'GtD4OperatingRevenue.vue')
const CUSTOMER = resolve(__dirname, '..', 'd4', 'analysis', 'D4TabCustomerPrice.vue')
const PRODUCT = resolve(__dirname, '..', 'd4', 'analysis', 'D4TabProductPrice.vue')

function read(path: string): string {
  return readFileSync(path, 'utf-8')
}

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('GtD4OperatingRevenue 价格联动宿主接线', () => {
  const hostSrc = stripComments(read(HOST))

  it('provide(\'d4CrossSheet\', crossSheet)', () => {
    expect(hostSrc).toMatch(/provide\s*\(\s*['"]d4CrossSheet['"]\s*,\s*crossSheet\s*\)/)
  })

  it('挂载 useD4PriceWriteback 且 onPersist 走 d4:save-items', () => {
    expect(hostSrc).toMatch(/useD4PriceWriteback\s*\(/)
    expect(hostSrc).toContain('d4:save-items')
    expect(hostSrc).toMatch(/import\s*\{[^}]*useD4PriceWriteback/)
  })
})

describe('D4-10/11 消费 inject 与公式真源', () => {
  const customerSrc = stripComments(read(CUSTOMER))
  const productSrc = stripComments(read(PRODUCT))

  it('D4-10 inject d4CrossSheet + 声明 WP 公式真源', () => {
    expect(customerSrc).toMatch(/inject\s*<[^>]*>\s*\(\s*['"]d4CrossSheet['"]/)
    expect(customerSrc).toContain("WP('D4-2','本期未审合计')")
    expect(customerSrc).toContain('D4_10_TOTAL_AMOUNT_PRESET')
    expect(customerSrc).toContain('mainRevenueUnadjustedTotal')
    expect(customerSrc).toContain('totalAmountManualOverride')
    expect(customerSrc).toContain('从 D4-9 导入客户')
  })

  it('D4-11 inject d4CrossSheet + chip 指向上游 D4-2', () => {
    expect(productSrc).toMatch(/inject\s*<[^>]*>\s*\(\s*['"]d4CrossSheet['"]/)
    expect(productSrc).toContain('从 D4-2 导入产品')
    expect(productSrc).toMatch(/GtIndexChip[^>]*value=["']wp:D4-2["']/)
    expect(productSrc).not.toMatch(/GtIndexChip[^>]*value=["']wp:D4-10["']/)
  })
})
