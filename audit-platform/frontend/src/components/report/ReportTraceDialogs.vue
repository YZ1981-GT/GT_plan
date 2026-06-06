<template>
  <!--
    ReportTraceDialogs — 审核结果 + 溯源选择 + 数字溯源弹窗
    从 ReportDialogs.vue 拆分（report-view-slimdown tech debt #3）
  -->

  <!-- 审核结果弹窗 -->
  <el-dialog append-to-body :model-value="showAuditDialog" title="✅ 公式审核结果" width="95%" top="2vh" :close-on-click-modal="false" @update:model-value="$emit('update:showAuditDialog', $event)">
    <div v-if="consistencyResult" class="gt-rv-audit-dialog">
      <!-- 汇总统计 -->
      <div class="gt-rv-audit-summary">
        <div class="gt-rv-audit-stat">
          <span class="gt-rv-audit-stat-num">{{ consistencyResult.total || 0 }}</span>
          <span class="gt-rv-audit-stat-label">审核公式</span>
        </div>
        <div class="gt-rv-audit-stat gt-rv-audit-stat-pass">
          <span class="gt-rv-audit-stat-num">{{ (consistencyResult.logic_check_passed || 0) + (consistencyResult.reasonability_passed || 0) }}</span>
          <span class="gt-rv-audit-stat-label">通过</span>
        </div>
        <div class="gt-rv-audit-stat gt-rv-audit-stat-fail">
          <span class="gt-rv-audit-stat-num">{{ (consistencyResult.total || 0) - (consistencyResult.logic_check_passed || 0) - (consistencyResult.reasonability_passed || 0) }}</span>
          <span class="gt-rv-audit-stat-label">未通过</span>
        </div>
        <div class="gt-rv-audit-stat" :class="consistencyResult.consistent ? 'gt-rv-audit-stat-pass' : 'gt-rv-audit-stat-fail'">
          <span class="gt-rv-audit-stat-num">{{ consistencyResult.consistent ? '✓' : '✗' }}</span>
          <span class="gt-rv-audit-stat-label">{{ consistencyResult.consistent ? '全部通过' : '存在异常' }}</span>
        </div>
      </div>

      <!-- 按类型分 Tab -->
      <el-tabs :model-value="auditTab" type="card" size="small" style="margin-top: 10px;" @update:model-value="$emit('update:auditTab', $event as string)">
        <el-tab-pane name="all">
          <template #label>全部 ({{ consistencyResult.total || 0 }})</template>
        </el-tab-pane>
        <el-tab-pane name="logic_check">
          <template #label>🔍 逻辑审核 ({{ consistencyResult.logic_check_count || 0 }})</template>
        </el-tab-pane>
        <el-tab-pane name="reasonability">
          <template #label>💡 提示性审核 ({{ consistencyResult.reasonability_count || 0 }})</template>
        </el-tab-pane>
      </el-tabs>

      <!-- 逐条审核明细 -->
      <el-table :data="filteredAuditChecks" border size="small" style="width: 100%;"
        max-height="calc(100vh - 300px)"
        :row-class-name="({ row }: any) => row.passed ? '' : 'gt-rv-audit-fail-row'">
        <el-table-column label="结果" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.passed" style="color: var(--gt-color-success); font-size: var(--gt-font-size-md);">✓</span>
            <span v-else style="color: var(--gt-color-coral); font-size: var(--gt-font-size-md);">✗</span>
          </template>
        </el-table-column>
        <el-table-column label="审核项目" min-width="200">
          <template #default="{ row }">
            <span style="font-weight: 500;">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期望值" width="120" align="right">
          <template #default="{ row }">
            <GtAmountCell :value="row.expected" />
          </template>
        </el-table-column>
        <el-table-column label="实际值" width="120" align="right">
          <template #default="{ row }">
            <GtAmountCell :value="row.actual" />
          </template>
        </el-table-column>
        <el-table-column label="差额" width="110" align="right">
          <template #default="{ row }">
            <GtAmountCell :value="row.diff" />
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <span style="font-size: var(--gt-font-size-xs);">{{ row.category_label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公式/来源" min-width="160">
          <template #default="{ row }">
            <code v-if="row.formula" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); word-break: break-all; white-space: normal;">{{ row.formula }}</code>
            <span v-else style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder);">{{ row.source || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="溯源定位" min-width="180">
          <template #default="{ row }">
            <div v-if="row.source || row.formula" style="display: flex; align-items: center; gap: 4px; flex-wrap: wrap;">
              <template v-for="loc in parseTraceLocations(row)" :key="loc.label">
                <el-button size="small" link type="primary" @click="$emit('trace-jump', loc)" style="font-size: var(--gt-font-size-xs);">
                  📍 {{ loc.label }}
                </el-button>
              </template>
              <span v-if="!parseTraceLocations(row).length" style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs);">—</span>
            </div>
            <span v-else style="color: var(--gt-color-text-placeholder); font-size: var(--gt-font-size-xs);">—</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 底部操作栏 -->
      <div style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
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
    <p style="color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); margin: 0 0 12px;">
      该审核项涉及多个报表位置，请选择要查看的定位：
    </p>
    <div v-if="traceSelectCheck" style="margin-bottom: 12px; padding: 8px 12px; background: var(--gt-color-primary-bg); border-radius: 8px; font-size: var(--gt-font-size-xs);">
      <span style="font-weight: 600;">{{ traceSelectCheck.name }}</span>
      <code v-if="traceSelectCheck.formula" style="display: block; margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);">{{ traceSelectCheck.formula }}</code>
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
        <el-empty v-else description="该数字暂无溯源信息" :image-size="60" />
      </template>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import type { ReportConsistencyCheck } from '@/services/auditPlatformApi'
import type { TraceLocation } from '@/views/composables/useReportCellActions'

// ─── Props ──────────────────────────────────────────────────────────────────
defineProps<{
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
  rvTraceResult: { upstream: any[]; downstream: any[] } | null

  // Helper function from parent
  parseTraceLocations: (check: any) => TraceLocation[]
}>()

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
