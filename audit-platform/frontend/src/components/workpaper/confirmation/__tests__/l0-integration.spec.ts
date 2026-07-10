/**
 * L0 债务循环函证 — 集成测试
 *
 * 验证：
 * 1. wp_code_overrides 映射正确性（10条L0→对应componentType）
 * 2. L0-5 四区块独立增删行+合计行（calcBlockTotal）
 * 3. 银行对账差异（calcReconcileDiff）
 * 4. 还款比例除零安全（期末余额=0→0）
 * 5. htmlRendererRegistry 注册完整性
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// ─── Mock http ──────────────────────────────────────────────────────────────
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { data: [] } }),
    post: vi.fn().mockResolvedValue({ data: { data: { content: 'test' } } }),
  },
}))

import { calcBlockTotal, calcRepaymentRatio, calcReconcileDiff, isAbnormal } from '../l0-confirmation/composables/useL0FormulaEngine'
import { useAlternativeL05Data, FORMAT_VERSION } from '../l0-confirmation/composables/useAlternativeL05Data'
import { HTML_RENDERER_REGISTRY, isHtmlComponentType } from '../../htmlRendererRegistry'

// ─── 1. wp_code_overrides 映射 ──────────────────────────────────────────────

describe('L0 wp_code_overrides 映射', () => {
  // 契约测试：验证 wp_code_overrides.json 包含正确的L0映射
  // 使用 process.cwd() 定位项目根目录
  let overrides: Record<string, string>

  beforeEach(async () => {
    const fs = await import('fs')
    const path = await import('path')
    // vitest cwd is audit-platform/frontend, overrides is at ../../backend/app/data/
    const filePath = path.resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const raw = fs.readFileSync(filePath, 'utf-8')
    overrides = JSON.parse(raw)
  })

  it('L0→confirmation-hub', () => { expect(overrides['L0']).toBe('confirmation-hub') })
  it('L0A→a-program-console', () => { expect(overrides['L0A']).toBe('a-program-console') })
  it('L0-1→confirmation-summary', () => { expect(overrides['L0-1']).toBe('confirmation-summary') })
  it('L0-2→confirmation-entity-verify', () => { expect(overrides['L0-2']).toBe('confirmation-entity-verify') })
  it('L0-3→confirmation-followup', () => { expect(overrides['L0-3']).toBe('confirmation-followup') })
  it('L0-4→confirmation-diff-reconcile', () => { expect(overrides['L0-4']).toBe('confirmation-diff-reconcile') })
  it('函证差异检查表（示例）→confirmation-diff-checklist', () => { expect(overrides['函证差异检查表（示例）']).toBe('confirmation-diff-checklist') })
  it('L0-5→confirmation-alternative-l05', () => { expect(overrides['L0-5']).toBe('confirmation-alternative-l05') })
  it('L0-6→confirmation-reliability', () => { expect(overrides['L0-6']).toBe('confirmation-reliability') })
  it('L0-7→confirmation-fraud-risk', () => { expect(overrides['L0-7']).toBe('confirmation-fraud-risk') })
})

// ─── 2. L0-5 四区块CRUD + 合计行 ───────────────────────────────────────────

describe('L0-5 四区块CRUD + 合计', () => {
  function createData() {
    return useAlternativeL05Data({
      wpId: 'test-wp-id',
      projectId: 'test-project-id',
      htmlData: () => ({ _format: FORMAT_VERSION, companies: [] }),
      readonly: false,
    })
  }

  it('新增公司并在block1添加/删除行', () => {
    const d = createData()
    const company = d.addCompany({ entity_name: '测试银行' })
    expect(d.companies.value).toHaveLength(1)

    const row = d.addBlockRow(company._company_id!, 'block1')
    expect(row).toBeDefined()
    expect(d.getBlockRows(company, 'block1')).toHaveLength(1)

    d.deleteBlockRow(company._company_id!, 'block1', row!._row_id!)
    expect(d.getBlockRows(company, 'block1')).toHaveLength(0)
  })

  it('block合计行使用calcBlockTotal', () => {
    const d = createData()
    const company = d.addCompany({ entity_name: '工商银行' })
    d.addBlockRow(company._company_id!, 'block1')
    d.addBlockRow(company._company_id!, 'block1')
    const rows = d.getBlockRows(company, 'block1')
    rows[0].voucher_amount = 1000
    rows[1].voucher_amount = 2000
    const totals = d.getBlockTotal(company, 'block1')
    expect(totals.voucher_amount).toBe(3000)
  })

  it('4区块各自独立CRUD', () => {
    const d = createData()
    const company = d.addCompany({ entity_name: '建设银行' })
    d.addBlockRow(company._company_id!, 'block1')
    d.addBlockRow(company._company_id!, 'block2')
    d.addBlockRow(company._company_id!, 'block3')
    d.addBlockRow(company._company_id!, 'block4')
    expect(d.getBlockRows(company, 'block1')).toHaveLength(1)
    expect(d.getBlockRows(company, 'block2')).toHaveLength(1)
    expect(d.getBlockRows(company, 'block3')).toHaveLength(1)
    expect(d.getBlockRows(company, 'block4')).toHaveLength(1)
  })
})

// ─── 3. 对账差异 ────────────────────────────────────────────────────────────

describe('L0-5 对账差异', () => {
  it('calcReconcileDiff 正确计算', () => {
    expect(calcReconcileDiff(10000, 9500)).toBe(500)
    expect(calcReconcileDiff(10000, 10000)).toBe(0)
    expect(calcReconcileDiff(5000, 6000)).toBe(-1000)
  })

  it('isAbnormal 正确判定', () => {
    expect(isAbnormal(500)).toBe(true)
    expect(isAbnormal(0)).toBe(false)
    expect(isAbnormal(-100)).toBe(true)
  })
})

// ─── 4. 还款比例除零安全 ────────────────────────────────────────────────────

describe('L0-5 还款比例除零安全', () => {
  it('期末余额=0→比例为0', () => {
    expect(calcRepaymentRatio(5000, 0)).toBe(0)
  })

  it('正常比例计算', () => {
    expect(calcRepaymentRatio(5000, 10000)).toBe(0.5)
  })
})

// ─── 5. htmlRendererRegistry 注册 ───────────────────────────────────────────

describe('L0-5 htmlRendererRegistry 注册', () => {
  it('confirmation-alternative-l05 已注册', () => {
    const entry = HTML_RENDERER_REGISTRY.get('confirmation-alternative-l05')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('confirmation-alternative-l05')
    expect(entry?.icon).toBe('🔄')
    expect(entry?.label).toBe('替代程序(债务循环)')
  })

  it('isHtmlComponentType 识别 confirmation-alternative-l05', () => {
    expect(isHtmlComponentType('confirmation-alternative-l05')).toBe(true)
  })
})

// ─── 6. buildPayload 数据格式 ───────────────────────────────────────────────

describe('L0-5 buildPayload', () => {
  it('payload 格式正确', () => {
    const d = useAlternativeL05Data({
      wpId: 'test-wp',
      projectId: 'test-proj',
      htmlData: () => ({ _format: FORMAT_VERSION, companies: [] }),
      readonly: false,
    })
    d.addCompany({ entity_name: '农业银行' })
    const payload = d.buildPayload()
    expect(payload._format).toBe('alternative-l05-v1')
    expect(payload.companies).toHaveLength(1)
    expect(payload.companies[0].entity_name).toBe('农业银行')
  })
})
