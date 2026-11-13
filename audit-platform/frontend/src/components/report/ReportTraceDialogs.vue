<template>
  <!--
    ReportTraceDialogs — 审核结果 + 溯源选择 + 数字溯源弹窗
    从 ReportDialogs.vue 拆分（report-view-slimdown tech debt #3）
  -->

  <!-- 审核结果弹窗 -->
  <el-dialog append-to-body :model-value="showAuditDialog" title="报表审核结果" width="95%" top="2vh" :close-on-click-modal="false" @update:model-value="$emit('update:showAuditDialog', $event)">
    <div v-if="consistencyResult" class="gt-rv-audit-dialog">
      <!-- 汇总统计 -->
      <div class="gt-rv-audit-summary">
        <div class="gt-rv-audit-stat">
          <span class="gt-rv-audit-stat-num">{{ auditPresentation.checks.length }}</span>
          <span class="gt-rv-audit-stat-label">审核明细</span>
        </div>
        <div v-for="status in REPORT_CHECK_STATUSES" :key="status" class="gt-rv-audit-stat"
          :class="status === 'passed' ? 'gt-rv-audit-stat-pass' : status === 'error' ? 'gt-rv-audit-stat-fail' : ''" :data-check-count="status">
          <span class="gt-rv-audit-stat-num">{{ auditPresentation.counts[status] }}</span>
          <span class="gt-rv-audit-stat-label">{{ REPORT_CHECK_LABELS[status] }}</span>
        </div>
      </div>
      <el-alert :type="auditAlertType" :closable="false" show-icon style="margin-top: 10px;" :title="auditPresentation.message" />
      <p v-if="consistencyResult.failed_count != null || consistencyResult.hint_count != null" class="gt-rv-audit-counts">
        后端汇总：失败 {{ consistencyResult.failed_count ?? '—' }} 项，提示 {{ consistencyResult.hint_count ?? '—' }} 项（提示不计入失败；业务五态按明细独立统计）
      </p>

      <!-- 按类型分 Tab -->
      <el-tabs :model-value="auditTab" type="card" size="small" style="margin-top: 10px;" @update:model-value="$emit('update:auditTab', $event as string)">
        <el-tab-pane name="all">
          <template #label>全部 ({{ auditPresentation.checks.length }})</template>
        </el-tab-pane>
        <el-tab-pane name="logic_check">
          <template #label>🔍 逻辑审核 ({{ auditPresentation.checks.filter(check => check.category === 'logic_check').length }})</template>
        </el-tab-pane>
        <el-tab-pane name="reasonability">
          <template #label>💡 提示性审核 ({{ auditPresentation.checks.filter(check => check.category === 'reasonability').length }})</template>
        </el-tab-pane>
      </el-tabs>

      <!-- 逐条审核明细 -->
      <el-table :data="auditDetails" border size="small" style="width: 100%; font-size: 12px;"
        max-height="calc(100vh - 300px)" :row-class-name="auditRowClass">
        <el-table-column label="结果" width="90" align="center">
          <template #default="{ row }">
            <span :data-check-status="row.presentation.status" :style="{ color: auditStatusColor(row.presentation) }">{{ row.presentation.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审核项目" min-width="200">
          <template #default="{ row }">
            <span style="font-weight: 500; font-size: 12px;">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期望值" width="120" align="right">
          <template #default="{ row }">
            <GtAmountCell v-if="hasReportCheckValue(row.expected)" :value="row.expected" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="实际值" width="120" align="right">
          <template #default="{ row }">
            <GtAmountCell v-if="hasReportCheckValue(row.actual)" :value="row.actual" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="差额" width="110" align="right">
          <template #default="{ row }">
            <GtAmountCell v-if="hasReportCheckValue(row.diff)" :value="row.diff" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="180">
          <template #default="{ row }">{{ row.presentation.reason || '—' }}</template>
        </el-table-column>
        <el-table-column label="严重度" width="110">
          <template #default="{ row }">{{ row.presentation.severityLabel }}</template>
        </el-table-column>
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <span style="font-size: 12px;">{{ row.category_label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公式/来源" min-width="160">
          <template #default="{ row }">
            <code v-if="row.formula" style="font-size: 12px; color: var(--gt-color-text-secondary); word-break: break-all; white-space: normal;">{{ row.formula }}</code>
            <span v-else style="font-size: 12px; color: var(--gt-color-text-placeholder);">{{ row.source || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="溯源定位" min-width="180">
          <template #default="{ row }">
            <div v-if="parseTraceLocations(row).length" style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">
              <template v-for="loc in parseTraceLocations(row)" :key="loc.label">
                <el-button size="small" link type="primary" @click="$emit('trace-jump', loc)" style="font-size: 12px;">
                  📍 {{ loc.label }}
                </el-button>
              </template>
              <span v-if="!parseTraceLocations(row).length" style="color: var(--gt-color-text-placeholder); font-size: 12px;">—</span>
            </div>
            <span v-else style="color: var(--gt-color-text-placeholder); font-size: 12px;">—</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 底部操作栏 -->
      <div style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 12px; color: var(--gt-color-text-tertiary);">
          共 {{ filteredAuditChecks.length }} 条审核项
        </span>
        <el-button size="small" @click="$emit('audit-export-excel')" round>📥 导出审核报告</el-button>
      </div>
    </div>
    <div v-else style="text-align: center; padding: 40px; color: var(--gt-color-text-tertiary);">
      暂无审核数据，请先点击"✅ 审核"按钮
    </div>
  </el-dialog>

  <!-- 溯源定位选择弹窗（多个定位时） -->
  <el-dialog append-to-body :model-value="showTraceSelectDialog" title="选择溯源定位" width="500px" @update:model-value="$emit('update:showTraceSelectDialog', $event)">
    <p style="color: var(--gt-color-text-secondary); font-size: 13px; margin: 0 0 12px;">
      该审核项涉及多个报表位置，请选择要查看的定位：
    </p>
    <div v-if="traceSelectCheck" style="margin-bottom: 12px; padding: 8px 12px; background: var(--gt-color-primary-bg); border-radius: 8px; font-size: 13px;">
      <span style="font-weight: 600;">{{ traceSelectCheck.name }}</span>
      <code v-if="traceSelectCheck.formula" style="display: block; margin-top: 4px; font-size: 13px; color: var(--gt-color-text-secondary);">{{ traceSelectCheck.formula }}</code>
    </div>
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <el-button v-for="loc in traceSelectOptions" :key="loc.rowCode || loc.label"
        @click="$emit('trace-jump', loc)" style="justify-content: flex-start; text-align: left;">
        📍 {{ loc.label }}
      </el-button>
    </div>
  </el-dialog>

  <!-- 数字溯源弹窗（lineage endpoint） -->
  <el-dialog :model-value="rvTraceDialogVisible" title="🔍 数字溯源" width="700px" append-to-body destroy-on-close @update:model-value="$emit('update:rvTraceDialogVisible', $event)">
    <div v-loading="rvTraceLoading" style="min-height:120px">
      <template v-if="rvTraceResult">
        <div v-if="rvTraceResult.upstream.length || rvTraceResult.downstream.length">
          <h4 style="margin:0 0 8px">上游来源</h4>
          <el-table v-if="rvTraceResult.upstream.length" :data="rvTraceResult.upstream" size="small" border stripe max-height="200">
            <el-table-column prop="wp_code" label="底稿编码" width="120" />
            <el-table-column prop="label" label="描述" min-width="200" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="$emit('trace-locate', row)">定位</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无上游来源" :image-size="40" />
          <h4 style="margin:16px 0 8px">下游引用</h4>
          <el-table v-if="rvTraceResult.downstream.length" :data="rvTraceResult.downstream" size="small" border stripe max-height="200">
            <el-table-column prop="wp_code" label="底稿编码" width="120" />
            <el-table-column prop="label" label="描述" min-width="200" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="$emit('trace-locate', row)">定位</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="无下游引用" :image-size="40" />
        </div>
        <OutputAttachmentLinks
          v-if="rvTraceResult.objectId"
          :project-id="projectId || rvTraceResult.projectId"
          object-type="report_row"
          target-type="report_row"
          :target-ref="rvTraceResult.objectId"
          resource="report"
          :initial-attachments="rvTraceResult.attachments || []"
        />
        <el-empty
          v-if="!rvTraceResult.upstream.length && !rvTraceResult.downstream.length && !(rvTraceResult.attachments || []).length"
          description="该数字暂无溯源信息"
          :image-size="60"
        />
      </template>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getReportBalanceDetails, getReportBalancePresentation, hasReportCheckValue, REPORT_CHECK_LABELS, REPORT_CHECK_STATUSES, type ReportCheckStatus } from '@/services/reportCheckPresentation'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import OutputAttachmentLinks from '@/components/attachment/OutputAttachmentLinks.vue'
import type { ReportConsistencyCheck } from '@/services/auditPlatformApi'
import type { TraceLocation } from '@/views/composables/useReportCellActions'

// ─── Props ──────────────────────────────────────────────────────────────────
const props = defineProps<{
  // Audit check
  showAuditDialog: boolean
  consistencyResult: ReportConsistencyCheck | null
  auditTab: string
  filteredAuditChecks: any[]

  // Trace select
  showTraceSelectDialog: boolean
  traceSelectOptions: TraceLocation[]
  traceSelectCheck: any

  // Cell trace (lineage)
  rvTraceDialogVisible: boolean
  rvTraceLoading: boolean
  rvTraceResult: {
    upstream: any[]; downstream: any[]; attachments: any[]; objectId: string; projectId: string
  } | null
  projectId?: string

  // Helper function from parent
  parseTraceLocations: (check: any) => TraceLocation[]
}>()

const auditPresentation = computed(() => getReportBalancePresentation(props.consistencyResult))
const auditDetails = computed(() => getReportBalanceDetails(props.filteredAuditChecks))
const auditAlertType = computed(() => {
  const status = auditPresentation.value.status
  return status === 'passed' ? 'success' : status === 'error' ? 'error' : status === 'warning' || status === 'hint' ? 'warning' : 'info'
})
function auditRowClass({ row }: { row: typeof auditDetails.value[number] }) {
  const { status, isHint } = row.presentation
  if (status === 'error' || (status === 'failed' && !isHint)) return 'gt-rv-audit-fail-row'
  return status === 'failed' ? 'gt-rv-audit-hint-row' : ''
}
function auditStatusColor(presentation: { status: ReportCheckStatus; isHint: boolean }) {
  if (presentation.status === 'passed') return 'var(--gt-color-success)'
  if (presentation.status === 'error' || (presentation.status === 'failed' && !presentation.isHint)) return 'var(--gt-color-coral)'
  return 'var(--gt-color-text-secondary)'
}

// ─── Emits ──────────────────────────────────────────────────────────────────
defineEmits<{
  (e: 'update:showAuditDialog', val: boolean): void
  (e: 'update:auditTab', val: string): void
  (e: 'update:showTraceSelectDialog', val: boolean): void
  (e: 'update:rvTraceDialogVisible', val: boolean): void
  (e: 'audit-drilldown', check: any): void
  (e: 'audit-export-excel'): void
  (e: 'trace-jump', loc: TraceLocation): void
  (e: 'trace-return'): void
  (e: 'trace-locate', node: any): void
}>()
</script>

<style>
/* 公式审核结果弹窗 — 汇总统计卡片 */
.gt-rv-audit-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #f8f6fc 0%, #f0edf8 100%);
  border-radius: 10px;
  border: 1px solid #e8e0f0;
}
.gt-rv-audit-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 12px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #e8e0f0;
  box-shadow: 0 1px 3px rgba(75, 45, 119, 0.05);
}
.gt-rv-audit-stat-num {
  display: block;
  font-size: 22px;
  font-weight: 700;
  color: #4b2d77;
  line-height: 1.2;
}
.gt-rv-audit-stat-label {
  display: block;
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}
.gt-rv-audit-stat-pass {
  background: rgba(103, 194, 58, 0.08);
  border-color: rgba(103, 194, 58, 0.3);
}
.gt-rv-audit-stat-pass .gt-rv-audit-stat-num { color: #67c23a; }
.gt-rv-audit-stat-fail {
  background: rgba(245, 108, 108, 0.08);
  border-color: rgba(245, 108, 108, 0.3);
}
.gt-rv-audit-stat-fail .gt-rv-audit-stat-num { color: #f56c6c; }

/* 审核弹窗失败行高亮 */
.gt-rv-audit-fail-row {
  background: rgba(245, 108, 108, 0.06) !important;
}
.gt-rv-audit-hint-row { background: var(--gt-bg-warning, #fdf6ec) !important; }
.gt-rv-audit-counts { font-size: 12px; color: var(--gt-color-text-secondary); }

/* 审核弹窗 Tab 美化 */
.gt-rv-audit-dialog .el-tabs--card > .el-tabs__header .el-tabs__item {
  font-size: 13px;
  padding: 0 16px;
}
.gt-rv-audit-dialog .el-tabs--card > .el-tabs__header .el-tabs__item.is-active {
  font-weight: 600;
  border-bottom: 2px solid #4b2d77;
}
</style>
