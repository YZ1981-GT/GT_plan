import { ref, computed, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { reportConfig as P_rc, reportMapping as P_rm } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface MappingRule {
  soe_row_code: string
  soe_row_name: string
  listed_row_code: string
}

export interface ListedOption {
  code: string
  name: string
}

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportMappingOptions {
  projectId: ComputedRef<string>
  reportScope: Ref<string>
}

export interface UseReportMappingReturn {
  // State
  showMappingDialog: Ref<boolean>
  mappingLoading: Ref<boolean>
  mappingTab: Ref<string>
  allMappingRules: Ref<Record<string, MappingRule[]>>
  allListedOptions: Ref<Record<string, ListedOption[]>>

  // Derived
  mappingReportTypes: { key: string; label: string }[]
  mappingTabLabel: ComputedRef<string>
  currentMappingRules: ComputedRef<MappingRule[]>
  currentListedOptions: ComputedRef<ListedOption[]>
  totalMappedCount: ComputedRef<number>
  totalRuleCount: ComputedRef<number>

  // Actions
  loadPresetMappingAll: () => Promise<void>
  saveMappingRulesAll: () => Promise<void>
  getMappingConfigData: () => Record<string, any>
  onMappingTemplateApplied: (configData: Record<string, any>) => void
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useReportMapping(options: UseReportMappingOptions): UseReportMappingReturn {
  const { projectId, reportScope } = options

  // State
  const showMappingDialog = ref(false)
  const mappingLoading = ref(false)
  const mappingTab = ref('balance_sheet')

  const mappingReportTypes = [
    { key: 'balance_sheet', label: '资产负债表' },
    { key: 'income_statement', label: '利润表' },
    { key: 'cash_flow_statement', label: '现金流量表' },
    { key: 'equity_statement', label: '权益变动表' },
    { key: 'cash_flow_supplement', label: '现金流附表' },
  ]

  const mappingTabLabel = computed(() => mappingReportTypes.find(r => r.key === mappingTab.value)?.label || '')

  // 每个报表类型独立存储映射规则和上市版选项
  const allMappingRules = ref<Record<string, MappingRule[]>>({})
  const allListedOptions = ref<Record<string, ListedOption[]>>({})

  const currentMappingRules = computed(() => allMappingRules.value[mappingTab.value] || [])
  const currentListedOptions = computed(() => allListedOptions.value[mappingTab.value] || [])
  const totalMappedCount = computed(() => Object.values(allMappingRules.value).flat().filter(r => r.listed_row_code).length)
  const totalRuleCount = computed(() => Object.values(allMappingRules.value).flat().length)

  // ── Internal helpers ──

  async function loadPresetForType(rt: string) {
    // 用后端 preset API（含同义词表+模糊匹配）
    const presetData = await api.get(P_rm.preset(projectId.value), {
      params: { report_type: rt, scope: reportScope.value },
      validateStatus: (s: number) => s < 600,
    })
    const preset = presetData ?? []

    // 同时加载上市版行次作为下拉选项
    const listedData = await api.get(P_rc.list, {
      params: { applicable_standard: `listed_${reportScope.value}`, report_type: rt },
      validateStatus: (s: number) => s < 600,
    })
    const listedRows = listedData ?? []
    allListedOptions.value[rt] = listedRows.map((r: any) => ({ code: r.row_code, name: r.row_name }))

    allMappingRules.value[rt] = preset.map((p: any) => ({
      soe_row_code: p.soe_row_code,
      soe_row_name: p.soe_row_name,
      listed_row_code: p.listed_row_code || '',
    }))
  }

  // ── Actions ──

  async function loadPresetMappingAll() {
    mappingLoading.value = true
    try {
      for (const rt of mappingReportTypes) {
        await loadPresetForType(rt.key)
      }
      ElMessage.success(`已加载全部预设规则，自动匹配 ${totalMappedCount.value} 项`)
    } catch {
      ElMessage.warning('加载预设规则失败')
    } finally {
      mappingLoading.value = false
    }
  }

  async function saveMappingRulesAll() {
    mappingLoading.value = true
    try {
      for (const rt of mappingReportTypes) {
        const rules = allMappingRules.value[rt.key] || []
        const mapped = rules.filter(r => r.listed_row_code)
        if (mapped.length > 0) {
          await api.post(P_rm.save(projectId.value), {
            report_type: rt.key,
            scope: reportScope.value,
            rules: mapped.map(r => ({ soe_row_code: r.soe_row_code, listed_row_code: r.listed_row_code })),
          }, { validateStatus: (s: number) => s < 600 })
        }
      }
      ElMessage.success('全部转换规则已保存')
      showMappingDialog.value = false
    } catch (e) {
      handleApiError(e, '保存转换规则')
    } finally {
      mappingLoading.value = false
    }
  }

  // ── 转换规则共享模板 ──

  function getMappingConfigData(): Record<string, any> {
    const data: Record<string, any[]> = {}
    for (const rt of mappingReportTypes) {
      const rules = allMappingRules.value[rt.key] || []
      data[rt.key] = rules.filter(r => r.listed_row_code).map(r => ({
        soe_row_code: r.soe_row_code,
        soe_row_name: r.soe_row_name,
        listed_row_code: r.listed_row_code,
      }))
    }
    return { mapping_rules: data, scope: reportScope.value }
  }

  function onMappingTemplateApplied(configData: Record<string, any>) {
    const rules = configData?.mapping_rules || {}
    let applied = 0
    for (const [rtKey, rtRules] of Object.entries(rules)) {
      const existing = allMappingRules.value[rtKey]
      if (!existing || !Array.isArray(rtRules)) continue
      for (const tplRule of rtRules as any[]) {
        const target = existing.find((r: any) => r.soe_row_code === tplRule.soe_row_code)
        if (target && !target.listed_row_code) {
          target.listed_row_code = tplRule.listed_row_code
          applied++
        }
      }
    }
    ElMessage.success(`已引用 ${applied} 条映射规则（已有映射的行不覆盖）`)
  }

  return {
    showMappingDialog,
    mappingLoading,
    mappingTab,
    allMappingRules,
    allListedOptions,
    mappingReportTypes,
    mappingTabLabel,
    currentMappingRules,
    currentListedOptions,
    totalMappedCount,
    totalRuleCount,
    loadPresetMappingAll,
    saveMappingRulesAll,
    getMappingConfigData,
    onMappingTemplateApplied,
  }
}
