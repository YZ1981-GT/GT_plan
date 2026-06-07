<template>
  <!--
    ReportDialogs — 统一弹窗容器子组件（thin wrapper）
    内部委托给 3 个子组件：ReportDrilldownDialogs / ReportTraceDialogs / ReportMappingDialog
    + 直接渲染 ConsolBreakdownDialog + CellFormulaDetail（已是独立组件）
    Extracted from ReportView.vue (Task 13.1, report-view-slimdown spec)
    Split into sub-components (tech debt #3)
  -->

  <!-- 穿透 + 构成科目 + 附注引用 -->
  <ReportDrilldownDialogs
    :drilldown-visible="drilldownVisible"
    :drilldown-loading="drilldownLoading"
    :drilldown-data="drilldownData"
    :line-comp-visible="lineCompVisible"
    :line-comp-loading="lineCompLoading"
    :line-comp-data="lineCompData"
    :note-refs-visible="noteRefsVisible"
    :note-refs-loading="noteRefsLoading"
    :note-refs-list="noteRefsList"
    :note-refs-row-code="noteRefsRowCode"
    :note-refs-row-name="noteRefsRowName"
    @update:drilldown-visible="$emit('update:drilldownVisible', $event)"
    @update:line-comp-visible="$emit('update:lineCompVisible', $event)"
    @update:note-refs-visible="$emit('update:noteRefsVisible', $event)"
    @line-comp-jump="$emit('line-comp-jump', $event)"
    @note-ref-jump="$emit('note-ref-jump', $event)"
    @open-workpaper="$emit('open-workpaper', $event)"
  />

  <!-- 审核结果 + 溯源选择 + 数字溯源 -->
  <ReportTraceDialogs
    :show-audit-dialog="showAuditDialog"
    :consistency-result="consistencyResult"
    :audit-tab="auditTab"
    :filtered-audit-checks="filteredAuditChecks"
    :show-trace-select-dialog="showTraceSelectDialog"
    :trace-select-options="traceSelectOptions"
    :trace-select-check="traceSelectCheck"
    :rv-trace-dialog-visible="rvTraceDialogVisible"
    :rv-trace-loading="rvTraceLoading"
    :rv-trace-result="rvTraceResult"
    :parse-trace-locations="parseTraceLocations"
    @update:show-audit-dialog="$emit('update:showAuditDialog', $event)"
    @update:audit-tab="$emit('update:auditTab', $event)"
    @update:show-trace-select-dialog="$emit('update:showTraceSelectDialog', $event)"
    @update:rv-trace-dialog-visible="$emit('update:rvTraceDialogVisible', $event)"
    @audit-drilldown="$emit('audit-drilldown', $event)"
    @audit-export-excel="$emit('audit-export-excel')"
    @trace-jump="$emit('trace-jump', $event)"
    @trace-return="$emit('trace-return')"
    @trace-locate="$emit('trace-locate', $event)"
  />

  <!-- 转换规则（映射） -->
  <ReportMappingDialog
    :show-mapping-dialog="showMappingDialog"
    :mapping-loading="mappingLoading"
    :mapping-tab="mappingTab"
    :mapping-report-types="mappingReportTypes"
    :current-mapping-rules="currentMappingRules"
    :current-listed-options="currentListedOptions"
    :total-mapped-count="totalMappedCount"
    :total-rule-count="totalRuleCount"
    :mapping-tab-label="mappingTabLabel"
    :get-mapping-config-data="getMappingConfigData"
    :project-id="projectId"
    @update:show-mapping-dialog="$emit('update:showMappingDialog', $event)"
    @update:mapping-tab="$emit('update:mappingTab', $event)"
    @mapping-load-preset="$emit('mapping-load-preset')"
    @mapping-save="$emit('mapping-save')"
    @mapping-template-applied="$emit('mapping-template-applied', $event)"
  />

  <!-- Sprint 5.6: 公式来源弹窗 -->
  <CellFormulaDetail
    :visible="showCellFormulaDetail"
    module="REPORT"
    :wp-code="cellDetailWpCode"
    :sheet-name="cellDetailSheet"
    :label="cellDetailLabel"
    @update:visible="$emit('update:showCellFormulaDetail', $event)"
    @navigate="(uri: string) => $emit('cell-detail-navigate', uri)"
  />

  <!-- 合并报表穿透弹窗（统一组件，source=report）：右键"查看合并明细"打开 -->
  <ConsolBreakdownDialog
    :model-value="consolBreakdownVisible"
    source="report"
    :project-id="projectId"
    :year="year"
    :account-code="consolBreakdownAccountCode"
    @update:model-value="$emit('update:consolBreakdownVisible', $event)"
  />
</template>

<script setup lang="ts">
import ReportDrilldownDialogs from '@/components/report/ReportDrilldownDialogs.vue'
import ReportTraceDialogs from '@/components/report/ReportTraceDialogs.vue'
import ReportMappingDialog from '@/components/report/ReportMappingDialog.vue'
import CellFormulaDetail from '@/components/CellFormulaDetail.vue'
import ConsolBreakdownDialog from '@/components/consolidation/ConsolBreakdownDialog.vue'
import type { ReportDrilldownData, ReportConsistencyCheck } from '@/services/auditPlatformApi'
import type { LineCompositionData, TraceLocation } from '@/views/composables/useReportCellActions'

// ─── Props ──────────────────────────────────────────────────────────────────
const props = defineProps<{
  // Drilldown
  drilldownVisible: boolean
  drilldownLoading: boolean
  drilldownData: ReportDrilldownData | null

  // Line composition
  lineCompVisible: boolean
  lineCompLoading: boolean
  lineCompData: LineCompositionData | null

  // Audit check
  showAuditDialog: boolean
  consistencyResult: ReportConsistencyCheck | null
  auditTab: string
  filteredAuditChecks: any[]

  // Trace select
  showTraceSelectDialog: boolean
  traceSelectOptions: TraceLocation[]
  traceSelectCheck: any

  // Note refs
  noteRefsVisible: boolean
  noteRefsLoading: boolean
  noteRefsList: any[]
  noteRefsRowCode: string
  noteRefsRowName: string

  // Cell trace (lineage)
  rvTraceDialogVisible: boolean
  rvTraceLoading: boolean
  rvTraceResult: { upstream: any[]; downstream: any[] } | null

  // Mapping
  showMappingDialog: boolean
  mappingLoading: boolean
  mappingTab: string
  mappingReportTypes: { key: string; label: string }[]
  currentMappingRules: any[]
  currentListedOptions: any[]
  totalMappedCount: number
  totalRuleCount: number
  mappingTabLabel: string
  getMappingConfigData: () => Record<string, any>

  // Consol breakdown
  consolBreakdownVisible: boolean
  consolBreakdownAccountCode: string
  projectId: string
  year: number

  // Formula detail
  showCellFormulaDetail: boolean
  cellDetailWpCode: string
  cellDetailSheet: string
  cellDetailLabel: string

  // Helper function from parent
  parseTraceLocations: (check: any) => TraceLocation[]
}>()

// ─── Emits ──────────────────────────────────────────────────────────────────
defineEmits<{
  (e: 'update:drilldownVisible', val: boolean): void
  (e: 'update:lineCompVisible', val: boolean): void
  (e: 'update:showAuditDialog', val: boolean): void
  (e: 'update:showTraceSelectDialog', val: boolean): void
  (e: 'update:noteRefsVisible', val: boolean): void
  (e: 'update:rvTraceDialogVisible', val: boolean): void
  (e: 'update:showMappingDialog', val: boolean): void
  (e: 'update:consolBreakdownVisible', val: boolean): void
  (e: 'update:showCellFormulaDetail', val: boolean): void
  (e: 'update:mappingTab', val: string): void
  (e: 'update:auditTab', val: string): void
  (e: 'line-comp-jump', accountCode: string): void
  (e: 'audit-drilldown', check: any): void
  (e: 'audit-export-excel'): void
  (e: 'trace-jump', loc: TraceLocation): void
  (e: 'trace-return'): void
  (e: 'trace-locate', node: any): void
  (e: 'note-ref-jump', ref: { note_section: string; table_index: number }): void
  (e: 'mapping-load-preset'): void
  (e: 'mapping-save'): void
  (e: 'mapping-template-applied', data: Record<string, any>): void
  (e: 'cell-detail-navigate', uri: string): void
  (e: 'open-workpaper', wpId: string): void
}>()
</script>
