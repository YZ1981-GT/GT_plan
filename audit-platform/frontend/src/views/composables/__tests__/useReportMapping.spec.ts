/**
 * useReportMapping.spec.ts — composable 单元测试
 *
 * 验证 useReportMapping 核心动作：
 * - loadPresetMappingAll: 加载全部 5 种报表类型预设，显示成功消息
 * - saveMappingRulesAll: 保存映射规则，显示成功消息，关闭弹窗
 * - onMappingTemplateApplied: 引用模板规则（只填空位不覆盖已有映射）
 *
 * Validates: Requirements 3.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/services/apiPaths', () => ({
  reportConfig: { list: '/api/report-config' },
  reportMapping: {
    preset: (pid: string) => `/api/projects/${pid}/report-mapping/preset`,
    save: (pid: string) => `/api/projects/${pid}/report-mapping`,
  },
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { useReportMapping } from '../useReportMapping'

const mockApiGet = vi.mocked(api.get)
const mockApiPost = vi.mocked(api.post)

// ─── Helpers ──────────────────────────────────────────────────────────────────

function createOptions() {
  return {
    projectId: computed(() => 'proj-1'),
    reportScope: ref('general'),
  }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useReportMapping — loadPresetMappingAll', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads preset for all 5 report types and shows success message', async () => {
    // Each report type triggers 2 API calls: preset + listed options
    mockApiGet.mockImplementation((url: string, opts?: any) => {
      if (url.includes('preset')) {
        return Promise.resolve([
          { soe_row_code: 'BS-001', soe_row_name: '货币资金', listed_row_code: 'L-001' },
        ])
      }
      // reportConfig list call
      return Promise.resolve([
        { row_code: 'L-001', row_name: '上市-货币资金' },
      ])
    })

    const options = createOptions()
    const { loadPresetMappingAll, allMappingRules, allListedOptions, totalMappedCount } = useReportMapping(options)

    await loadPresetMappingAll()

    // 5 report types × 2 calls each = 10 API calls
    expect(mockApiGet).toHaveBeenCalledTimes(10)
    // Verify preset was called with correct params
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/projects/proj-1/report-mapping/preset',
      expect.objectContaining({ params: expect.objectContaining({ report_type: 'balance_sheet', scope: 'general' }) }),
    )
    // Verify all 5 report types are populated
    expect(Object.keys(allMappingRules.value)).toHaveLength(5)
    expect(Object.keys(allListedOptions.value)).toHaveLength(5)
    // totalMappedCount should reflect mapped items (each type has 1 mapped rule)
    expect(totalMappedCount.value).toBe(5)
    // Success message shown
    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith(
      expect.stringContaining('5'),
    )
  })

  it('shows warning message on API failure', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'))

    const options = createOptions()
    const { loadPresetMappingAll, mappingLoading } = useReportMapping(options)

    await loadPresetMappingAll()

    expect(vi.mocked(ElMessage.warning)).toHaveBeenCalledWith('加载预设规则失败')
    expect(mappingLoading.value).toBe(false)
  })
})

describe('useReportMapping — saveMappingRulesAll', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('saves mapped rules, shows success, and closes dialog', async () => {
    mockApiPost.mockResolvedValue({})

    const options = createOptions()
    const { saveMappingRulesAll, allMappingRules, showMappingDialog, mappingLoading } = useReportMapping(options)

    // Pre-populate rules for 2 report types
    allMappingRules.value = {
      balance_sheet: [
        { soe_row_code: 'BS-001', soe_row_name: '货币资金', listed_row_code: 'L-001' },
        { soe_row_code: 'BS-002', soe_row_name: '应收账款', listed_row_code: '' }, // unmapped
      ],
      income_statement: [
        { soe_row_code: 'IS-001', soe_row_name: '营业收入', listed_row_code: 'L-100' },
      ],
    }
    showMappingDialog.value = true

    await saveMappingRulesAll()

    // Only types with mapped rules are posted (2 types with mapped rules)
    expect(mockApiPost).toHaveBeenCalledTimes(2)
    // Verify balance_sheet post — only mapped rule sent
    expect(mockApiPost).toHaveBeenCalledWith(
      '/api/projects/proj-1/report-mapping',
      expect.objectContaining({
        report_type: 'balance_sheet',
        scope: 'general',
        rules: [{ soe_row_code: 'BS-001', listed_row_code: 'L-001' }],
      }),
      expect.any(Object),
    )
    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith('全部转换规则已保存')
    expect(showMappingDialog.value).toBe(false)
    expect(mappingLoading.value).toBe(false)
  })

  it('calls handleApiError on save failure', async () => {
    const error = new Error('Save failed')
    mockApiPost.mockRejectedValue(error)

    const options = createOptions()
    const { saveMappingRulesAll, allMappingRules } = useReportMapping(options)
    allMappingRules.value = {
      balance_sheet: [{ soe_row_code: 'BS-001', soe_row_name: '货币资金', listed_row_code: 'L-001' }],
    }

    await saveMappingRulesAll()

    expect(vi.mocked(handleApiError)).toHaveBeenCalledWith(error, '保存转换规则')
  })
})

describe('useReportMapping — onMappingTemplateApplied', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('applies template rules only to empty slots (does not overwrite existing)', () => {
    const options = createOptions()
    const { onMappingTemplateApplied, allMappingRules } = useReportMapping(options)

    // Pre-populate with existing rules (one mapped, one empty)
    allMappingRules.value = {
      balance_sheet: [
        { soe_row_code: 'BS-001', soe_row_name: '货币资金', listed_row_code: 'L-EXISTING' },
        { soe_row_code: 'BS-002', soe_row_name: '应收账款', listed_row_code: '' },
      ],
    }

    const configData = {
      mapping_rules: {
        balance_sheet: [
          { soe_row_code: 'BS-001', soe_row_name: '货币资金', listed_row_code: 'L-TEMPLATE' },
          { soe_row_code: 'BS-002', soe_row_name: '应收账款', listed_row_code: 'L-002' },
        ],
      },
    }

    onMappingTemplateApplied(configData)

    // BS-001 should keep existing mapping (not overwritten)
    expect(allMappingRules.value.balance_sheet[0].listed_row_code).toBe('L-EXISTING')
    // BS-002 should get template value (was empty)
    expect(allMappingRules.value.balance_sheet[1].listed_row_code).toBe('L-002')
    // Success message with count=1 (only 1 slot was filled)
    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith(
      expect.stringContaining('1'),
    )
  })

  it('handles empty or missing configData gracefully', () => {
    const options = createOptions()
    const { onMappingTemplateApplied, allMappingRules } = useReportMapping(options)

    allMappingRules.value = {
      balance_sheet: [
        { soe_row_code: 'BS-001', soe_row_name: '货币资金', listed_row_code: '' },
      ],
    }

    onMappingTemplateApplied({})

    // Nothing applied, rules unchanged
    expect(allMappingRules.value.balance_sheet[0].listed_row_code).toBe('')
    expect(vi.mocked(ElMessage.success)).toHaveBeenCalledWith(
      expect.stringContaining('0'),
    )
  })
})
