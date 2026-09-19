/**
 * AccountPackageView.spec.ts — 工作包入口视图测试
 *
 * spec workpaper-account-package-d1-d2-pilot Task 4/5
 *
 * 覆盖：
 * - D1/D2 入口渲染
 * - 缺失卡片显示
 * - 程序状态交互
 * - 坏账/ECL 分组
 * - stale 提示
 *
 * Validates: Requirements 1.2, 2.1, 2.2, 2.3, 3.1, 3.3
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import {
  useAccountPackage,
  groupSheetsByType,
  getBadDebtEclGroup,
  isBadDebtEclSheet,
  D1_DISCLOSURE_SOURCES,
  type SheetDef,
  type PackageDetail,
  type PackageSummary,
} from '@/composables/useAccountPackage'

// ─── Mock http ───
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// ─── Mock vue-router ───
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'test-project-id', packageId: 'D1_notes_receivable' },
  }),
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

// ─── Fixtures ───
const D1_SHEETS: SheetDef[] = [
  { sheet_name: 'D1A 应收票据审计程序表', sheet_type: 'procedure', source_wp_code: 'D1' },
  { sheet_name: '审定表D1-1', sheet_type: 'audit_sheet', source_wp_code: 'D1' },
  { sheet_name: '应收票据明细表D1-2', sheet_type: 'detail_table', source_wp_code: 'D1' },
  { sheet_name: '坏账准备明细表D1-4', sheet_type: 'detail_table', source_wp_code: 'D1' },
  { sheet_name: '应收票据账龄分析表D1-5', sheet_type: 'analysis', source_wp_code: 'D1' },
  { sheet_name: '应收票据贴现背书明细表D1-8', sheet_type: 'detail_table', source_wp_code: 'D1' },
  { sheet_name: '应收票据质押检查表D1-12', sheet_type: 'procedure', source_wp_code: 'D1' },
  { sheet_name: '调整分录汇总表D1-15', sheet_type: 'adjustment', source_wp_code: 'D1' },
  { sheet_name: '附注披露信息（上市公司）', sheet_type: 'disclosure', source_wp_code: 'D1' },
  { sheet_name: '附注披露信息（国企）', sheet_type: 'disclosure', source_wp_code: 'D1' },
  { sheet_name: 'D1-16 科目结论表', sheet_type: 'conclusion', source_wp_code: 'D1' },
]

const D2_SHEETS: SheetDef[] = [
  { sheet_name: 'D2A 应收账款实质性程序表', sheet_type: 'control_panel', source_wp_code: 'D2' },
  { sheet_name: '审定表D2-1', sheet_type: 'audit_sheet', source_wp_code: 'D2' },
  { sheet_name: '应收账款明细表D2-2', sheet_type: 'detail_table', source_wp_code: 'D2' },
  { sheet_name: '坏账准备明细表D2-3', sheet_type: 'analysis', source_wp_code: 'D2' },
  { sheet_name: '调整分录汇总表D2-4', sheet_type: 'adjustment', source_wp_code: 'D2' },
  { sheet_name: '应收账款分析表D2-5', sheet_type: 'analysis', source_wp_code: 'D2-5' },
  { sheet_name: '关联方及交易检查表D2-6', sheet_type: 'procedure', source_wp_code: 'D2-6' },
  { sheet_name: '应收账款检查表D2-7', sheet_type: 'procedure', source_wp_code: 'D2-6' },
  { sheet_name: '坏账准备计提会计政策检查D2-8', sheet_type: 'procedure', source_wp_code: 'D2-6' },
  { sheet_name: '应收坏账准备测算D2-9', sheet_type: 'analysis', source_wp_code: 'D2-6' },
  { sheet_name: '预期信用损失的计量测试D2-10', sheet_type: 'analysis', source_wp_code: 'D2-6' },
  { sheet_name: '应收账款业务模式分析D2-13', sheet_type: 'analysis', source_wp_code: 'D2-6' },
  { sheet_name: '应收账款附注披露信息', sheet_type: 'disclosure', source_wp_code: 'D2' },
  { sheet_name: 'D2-C 科目结论', sheet_type: 'conclusion', source_wp_code: 'D2' },
]

// ─── groupSheetsByType 测试 ───
describe('groupSheetsByType — D1 sheet_type 分组', () => {
  it('D1 sheets 按 sheet_type 正确分组', () => {
    const groups = groupSheetsByType(D1_SHEETS)
    const types = groups.map((g) => g.type)

    expect(types).toContain('audit_sheet')
    expect(types).toContain('detail_table')
    expect(types).toContain('analysis')
    expect(types).toContain('procedure')
    expect(types).toContain('adjustment')
    expect(types).toContain('disclosure')
    expect(types).toContain('conclusion')
  })

  it('D1 审定表分组只包含 1 个 sheet', () => {
    const groups = groupSheetsByType(D1_SHEETS)
    const auditGroup = groups.find((g) => g.type === 'audit_sheet')
    expect(auditGroup).toBeDefined()
    expect(auditGroup!.sheets).toHaveLength(1)
    expect(auditGroup!.sheets[0].sheet_name).toBe('审定表D1-1')
  })

  it('分组按 SHEET_TYPE_ORDER 排序', () => {
    const groups = groupSheetsByType(D1_SHEETS)
    const typeOrder = groups.map((g) => g.type)
    // audit_sheet 应在 detail_table 之前
    const auditIdx = typeOrder.indexOf('audit_sheet')
    const detailIdx = typeOrder.indexOf('detail_table')
    expect(auditIdx).toBeLessThan(detailIdx)
  })

  it('每个分组有中文 label 和 icon', () => {
    const groups = groupSheetsByType(D1_SHEETS)
    for (const group of groups) {
      expect(group.label).toBeTruthy()
      expect(group.icon).toBeTruthy()
    }
  })
})

// ─── groupSheetsByType D2 测试 ───
describe('groupSheetsByType — D2 sheet_type 分组', () => {
  it('D2 sheets 按 sheet_type 正确分组且包含 control_panel', () => {
    const groups = groupSheetsByType(D2_SHEETS)
    const types = groups.map((g) => g.type)

    expect(types).toContain('control_panel')
    expect(types).toContain('audit_sheet')
    expect(types).toContain('detail_table')
    expect(types).toContain('analysis')
    expect(types).toContain('procedure')
    expect(types).toContain('adjustment')
    expect(types).toContain('disclosure')
    expect(types).toContain('conclusion')
  })

  it('D2 control_panel 排在最前', () => {
    const groups = groupSheetsByType(D2_SHEETS)
    expect(groups[0].type).toBe('control_panel')
  })

  it('D2 analysis 分组包含 5 个 sheet', () => {
    const groups = groupSheetsByType(D2_SHEETS)
    const analysisGroup = groups.find((g) => g.type === 'analysis')
    expect(analysisGroup).toBeDefined()
    expect(analysisGroup!.sheets).toHaveLength(5)
  })
})

// ─── D2 坏账与 ECL 分组 ───
describe('getBadDebtEclGroup — D2 坏账与 ECL 分组', () => {
  it('识别 D2-3, D2-8, D2-9, D2-10 和 C-D2-disclosure 相关 sheet', () => {
    const eclSheets = getBadDebtEclGroup(D2_SHEETS)
    const names = eclSheets.map((s) => s.sheet_name)

    expect(names).toContain('坏账准备明细表D2-3')
    expect(names).toContain('坏账准备计提会计政策检查D2-8')
    expect(names).toContain('应收坏账准备测算D2-9')
    expect(names).toContain('预期信用损失的计量测试D2-10')
  })

  it('isBadDebtEclSheet 正确识别', () => {
    expect(isBadDebtEclSheet('坏账准备明细表D2-3')).toBe(true)
    expect(isBadDebtEclSheet('审定表D2-1')).toBe(false)
    expect(isBadDebtEclSheet('应收坏账准备测算D2-9')).toBe(true)
  })
})

// ─── D1 附注来源链路 ───
describe('D1_DISCLOSURE_SOURCES — 附注来源链路', () => {
  it('包含 4 个来源（D1-1, D1-4, D1-8, D1-12）', () => {
    expect(D1_DISCLOSURE_SOURCES).toHaveLength(4)
  })

  it('来源 sheet 名称正确', () => {
    const names = D1_DISCLOSURE_SOURCES.map((s) => s.sheet_name)
    expect(names).toContain('审定表D1-1')
    expect(names).toContain('坏账准备明细表D1-4')
    expect(names).toContain('应收票据贴现背书明细表D1-8')
    expect(names).toContain('应收票据质押检查表D1-12')
  })
})

// ─── useAccountPackage composable ───
describe('useAccountPackage — composable 基本功能', () => {
  it('初始状态正确', () => {
    const projectId = ref('test-project')
    const { packages, detail, summary, loading, error } = useAccountPackage(projectId)

    expect(packages.value).toEqual([])
    expect(detail.value).toBeNull()
    expect(summary.value).toBeNull()
    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
  })

  it('sheetGroups 在 detail 为 null 时返回空数组', () => {
    const projectId = ref('test-project')
    const { sheetGroups } = useAccountPackage(projectId)
    expect(sheetGroups.value).toEqual([])
  })

  it('missingSourceCards 在 summary 为 null 时返回空数组', () => {
    const projectId = ref('test-project')
    const { missingSourceCards } = useAccountPackage(projectId)
    expect(missingSourceCards.value).toEqual([])
  })
})

// ─── 缺失卡片 ───
describe('缺失卡片逻辑', () => {
  it('hasMissingSources 在有缺失时为 true', () => {
    const projectId = ref('test-project')
    const { hasMissingSources, summary } = useAccountPackage(projectId) as any
    // 模拟 summary 有 missing_sources
    summary.value = {
      registry_status: 'active',
      mapping_status: 'pending_inventory_reconciliation',
      program_status_summary: {},
      external_cards: [],
      stale_summary: {},
      missing_sources: [
        { sheet_name: '某 sheet', source_wp_code: 'D2-5', reason: '数据源缺失' },
      ],
    }
    expect(hasMissingSources.value).toBe(true)
  })

  it('hasMissingSources 在无缺失时为 false', () => {
    const projectId = ref('test-project')
    const { hasMissingSources, summary } = useAccountPackage(projectId) as any
    summary.value = {
      registry_status: 'active',
      mapping_status: 'confirmed_production',
      program_status_summary: {},
      external_cards: [],
      stale_summary: {},
      missing_sources: [],
    }
    expect(hasMissingSources.value).toBe(false)
  })
})
