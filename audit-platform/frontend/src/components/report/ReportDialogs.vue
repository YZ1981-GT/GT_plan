<template>
  <!--
    ReportDialogs — 统一弹窗容器子组件
    包含：穿透弹窗、构成科目弹窗、审核结果弹窗、溯源弹窗、转换规则弹窗、溯源选择弹窗、附注引用 Drawer、合并明细弹窗、公式来源弹窗
    Extracted from ReportView.vue (Task 13.1, report-view-slimdown spec)
  -->

  <!-- Sprint 4 Task 4.3：附注引用我（侧栏 drawer） -->
  <el-drawer
    :model-value="noteRefsVisible"
    :title="`附注引用我 — ${noteRefsRowName || ''}`"
    direction="rtl"
    size="380px"
    append-to-body
    :destroy-on-close="false"
    @update:model-value="$emit('update:noteRefsVisible', $event)"
  >
    <div v-loading="noteRefsLoading" class="gt-rv-note-refs">
      <div class="gt-rv-note-refs__header">
        <span class="gt-rv-note-refs__label">报表行</span>
        <code class="gt-rv-note-refs__code">{{ noteRefsRowCode || '—' }}</code>
      </div>
      <el-empty
        v-if="!noteRefsLoading && noteRefsList.length === 0"
        :image-size="80"
        description="暂无附注引用此报表项"
      />
      <ul v-else class="gt-rv-note-refs__list">
        <li
          v-for="(ref, i) in noteRefsList"
          :key="`${ref.note_section}-${ref.table_index}-${i}`"
          class="gt-rv-note-refs__item"
          @click="$emit('note-ref-jump', ref)"
        >
          <span class="gt-rv-note-refs__sec">{{ ref.note_section }}</span>
          <span v-if="ref.section_title" class="gt-rv-note-refs__title">{{ ref.section_title }}</span>
          <span v-if="ref.table_index > 0" class="gt-rv-note-refs__tbl">表 #{{ ref.table_index + 1 }}</span>
          <span class="gt-rv-note-refs__arrow">→</span>
        </li>
      </ul>
      <div v-if="noteRefsList.length > 0" class="gt-rv-note-refs__footer">
        共 {{ noteRefsList.length }} 处引用 · 点击跳转到附注编辑器
      </div>
    </div>
  </el-drawer>

  <!-- 穿透弹窗 -->
  <el-dialog append-to-body :model-value="drilldownVisible" :title="`穿透查询 — ${drilldownData?.row_name || ''}`" width="700px" @update:model-value="$emit('update:drilldownVisible', $event)">
    <div v-if="drilldownData" class="gt-rv-drilldown-content">
      <div class="gt-rv-dd-section">
        <span class="gt-rv-dd-label">公式：</span>
        <code>{{ drilldownData.formula }}</code>
      </div>
      <el-table :data="drilldownData.accounts" border size="small" style="margin-top: 12px">
        <el-table-column prop="code" label="科目编码" width="120" />
        <el-table-column prop="name" label="科目名称" min-width="200" />
        <el-table-column label="金额" width="150" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.amount" /></template>
        </el-table-column>
        <el-table-column label="底稿" width="100" align="center">
          <template #default="{ row }">
            <el-button v-if="row.wp_id" link type="primary" size="small"
              @click="$emit('open-workpaper', row.wp_id)">打开底稿</el-button>
            <span v-else style="color: var(--gt-color-text-placeholder)">—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <div v-else v-loading="drilldownLoading" style="min-height: 100px" />
  </el-dialog>

  <!-- Phase 3 F1.2: 报表行构成科目弹窗 -->
  <el-dialog
    append-to-body
    :model-value="lineCompVisible"
    :title="`构成科目 — ${lineCompData?.item_name || ''}`"
    width="650px"
    @update:model-value="$emit('update:lineCompVisible', $event)"
  >
    <div v-if="lineCompData" class="gt-rv-line-comp-content">
      <!-- 报表行汇总 -->
      <div class="gt-rv-line-comp-header">
        <span class="gt-rv-line-comp-label">报表行次</span>
        <div class="gt-rv-line-comp-summary">
          <span class="gt-rv-line-comp-name">{{ lineCompData.item_name }}</span>
          <GtAmountCell :value="lineCompData.total_amount" />
        </div>
      </div>

      <!-- 构成科目列表 -->
      <div class="gt-rv-line-comp-accounts">
        <span class="gt-rv-line-comp-label">构成科目（点击跳转试算表）</span>
        <el-table
          :data="lineCompData.accounts"
          border
          size="small"
          style="margin-top: 8px"
          :row-style="{ cursor: 'pointer' }"
          @row-click="(row: any) => $emit('line-comp-jump', row.code)"
        >
          <el-table-column prop="code" label="科目编码" width="120">
            <template #default="{ row }">
              <span class="gt-amt" style="color: var(--gt-color-primary)">{{ row.code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="科目名称" min-width="180" />
          <el-table-column label="期末余额" width="150" align="right">
            <template #header>
              <span>期末余额</span>
              <span style="font-size: 10px; color: var(--gt-color-text-placeholder); margin-left: 4px">(元)</span>
            </template>
            <template #default="{ row }">
              <GtAmountCell :value="row.closing_balance" />
            </template>
          </el-table-column>
          <el-table-column label="占比" width="90" align="right">
            <template #default="{ row }">
              <span style="color: var(--gt-color-text-secondary); font-size: 12px">{{ row.pct?.toFixed(1) }}%</span>
            </template>
          </el-table-column>
          <el-table-column label="" width="60" align="center">
            <template #default>
              <span style="color: var(--gt-color-primary); font-size: 12px">→</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 底部提示 -->
      <div class="gt-rv-line-comp-footer">
        <span style="color: var(--gt-color-text-tertiary); font-size: 12px">
          点击任意科目行可跳转到试算表定位（支持 Backspace 返回）
        </span>
      </div>
    </div>
    <div v-else v-loading="lineCompLoading" style="min-height: 100px" />
  </el-dialog>

  <!-- 转换规则弹窗 -->
  <el-dialog append-to-body :model-value="showMappingDialog" title="国企版 ↔ 上市版 转换规则" width="950px" top="3vh" @update:model-value="$emit('update:showMappingDialog', $event)">
    <div class="gt-rv-mapping-dialog">
      <p style="color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-xs); margin: 0 0 10px;">
        配置国企版与上市版各报表项目的映射关系。确认后系统将按规则自动转换，转换结果缓存到数据库。
      </p>
      <div style="display: flex; gap: 8px; margin-bottom: 10px; align-items: center; flex-wrap: wrap;">
        <el-button size="small" @click="$emit('mapping-load-preset')" :loading="mappingLoading">一键加载全部预设</el-button>
        <el-button size="small" type="primary" @click="$emit('mapping-save')" :loading="mappingLoading">保存全部规则</el-button>
        <SharedTemplatePicker
          config-type="report_mapping"
          :project-id="projectId"
          :get-config-data="getMappingConfigData"
          @applied="(data: Record<string, any>) => $emit('mapping-template-applied', data)"
        />
        <span style="flex:1" />
        <span style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); line-height: 28px;">
          总计已映射 {{ totalMappedCount }} / {{ totalRuleCount }} 项
        </span>
      </div>
      <el-tabs :model-value="mappingTab" type="card" size="small" @update:model-value="$emit('update:mappingTab', $event as string)">
        <el-tab-pane v-for="rt in mappingReportTypes" :key="rt.key" :label="rt.label" :name="rt.key" />
      </el-tabs>
      <el-table :data="currentMappingRules" border size="small" max-height="420" style="width: 100%">
        <el-table-column label="国企版项目" min-width="200">
          <template #default="{ row }">
            <span>{{ row.soe_row_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="编码" width="110" align="center">
          <template #default="{ row }">
            <span style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">{{ row.soe_row_code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="→" width="30" align="center">
          <template #default><span style="color: var(--gt-color-text-placeholder);">→</span></template>
        </el-table-column>
        <el-table-column label="上市版项目" min-width="220">
          <template #default="{ row }">
            <el-select v-model="row.listed_row_code" size="small" filterable clearable placeholder="选择" style="width: 100%;">
              <el-option v-for="opt in currentListedOptions" :key="opt.code" :label="opt.name" :value="opt.code">
                <span style="font-size: var(--gt-font-size-xs);">{{ opt.code }} {{ opt.name }}</span>
              </el-option>
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70" align="center">
          <template #default="{ row }">
            <span v-if="row.listed_row_code" style="color: var(--gt-color-success); font-size: var(--gt-font-size-xs);">✓</span>
            <span v-else style="color: var(--gt-color-coral); font-size: var(--gt-font-size-xs);">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top: 8px; text-align: right; color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">
        {{ mappingTabLabel }} 已映射 {{ currentMappingRules.filter((r: any) => r.listed_row_code).length }} / {{ currentMappingRules.length }} 项
      </div>
    </div>
  </el-dialog>

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
    v-model="consolBreakdownVisible"
    source="report"
    :project-id="projectId"
    :year="year"
    :account-code="consolBreakdownAccountCode"
    @update:model-value="$emit('update:consolBreakdownVisible', $event)"
  />
</template>

<script setup lang="ts">
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
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
