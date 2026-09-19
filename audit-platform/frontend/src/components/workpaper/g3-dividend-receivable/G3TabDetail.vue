<!--
  G3TabDetail.vue — G3-2 应收股利明细表（33列 → 4区段Tab）

  4区段Tab切换：被投资方信息(8列) / 持股明细(9列) / 分红方案(8列) / 应收核算(8列)
  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  公式列：权益份额/分红总额/实际分红率/应收股利/期末应收/逾期天数

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.2
  Requirements: 5.1~5.11
-->
<template>
  <div class="g3-detail">
    <div class="section-head">
      <h3 class="sheet-title">G3-2 应收股利明细表</h3>
      <div class="head-actions tab-toolbar">
        <el-button size="small" :disabled="isReadonly" @click="detail.addRow()">＋ 新增明细行</el-button>
        <G3ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G3-2"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('G3-2-detail')">💬复核</el-button>
        <GtIndexChip value="wp:G3-2" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：确认应收股利的真实性、完整性与计价准确性，核查持股比例、分红方案与应收金额的勾稽一致性，识别逾期未收回项目。"
    />

    <!-- 4区段Tab -->
    <el-tabs v-model="detail.segment.value" type="border-card" class="segment-tabs">
      <el-tab-pane
        v-for="seg in detail.segments"
        :key="seg.key"
        :label="seg.label"
        :name="seg.key"
      />
    </el-tabs>

    <!-- 动态列表格 -->
    <el-table
      :data="detail.rows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClassName"
      class="detail-table"
    >
      <!-- 序号列（所有区段始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <!-- 被投资方名称（所有区段始终显示作为锚定列） -->
      <el-table-column label="被投资方" width="150" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => detail.updateRow(row.id, { investeeName: v })"
          />
        </template>
      </el-table-column>

      <!-- 动态区段列 -->
      <el-table-column
        v-for="col in currentColumns"
        :key="col.prop"
        :label="col.label"
        :min-width="col.width"
        align="right"
      >
        <template #default="{ row }">
          <!-- 公式列：只读 + 虚线下划线 -->
          <template v-if="col.formula">
            <span
              class="formula-cell"
              :title="getFormulaTooltip(col.prop)"
            >
              {{ formatCellValue(row, col) }}
            </span>
          </template>

          <!-- 投资类型下拉 -->
          <template v-else-if="col.type === 'invest-type'">
            <el-select
              :model-value="row[col.prop]"
              size="small"
              :disabled="isReadonly"
              style="width:100%"
              @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
            >
              <el-option
                v-for="opt in investTypeOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
          </template>

          <!-- 核算方法下拉 -->
          <template v-else-if="col.type === 'method'">
            <el-select
              :model-value="row[col.prop]"
              size="small"
              :disabled="isReadonly"
              style="width:100%"
              @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
            >
              <el-option
                v-for="opt in methodOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
          </template>

          <!-- 日期列 -->
          <template v-else-if="col.type === 'date'">
            <el-date-picker
              :model-value="row[col.prop]"
              type="date"
              size="small"
              :disabled="isReadonly"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => detail.updateRow(row.id, { [col.prop]: v ?? '' })"
            />
          </template>

          <!-- 数字列 -->
          <template v-else-if="col.type === 'number'">
            <el-input-number
              :model-value="row[col.prop] as number"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { [col.prop]: v ?? 0 })"
            />
          </template>

          <!-- 文本列 -->
          <template v-else>
            <el-input
              :model-value="row[col.prop] as string"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => detail.updateRow(row.id, { [col.prop]: v })"
            />
          </template>
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="detail.removeRow(row.id)">
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部合计 -->
    <div class="totals-bar">
      <span class="totals-label">合计</span>
      <span class="total-item">投资成本：{{ fmtNum(detail.totals.value.initialCost) }}</span>
      <span class="total-item">分红总额：{{ fmtNum(detail.totals.value.totalDividend) }}</span>
      <span class="total-item">应收股利：{{ fmtNum(detail.totals.value.dividendReceivable) }}</span>
      <span class="total-item">已收金额：{{ fmtNum(detail.totals.value.receivedAmount) }}</span>
      <span class="total-item">期末应收：{{ fmtNum(detail.totals.value.netReceivable) }}</span>
    </div>

    <G3AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      :related-context="{
        明细行数: detail.rows.value.length,
      }"
      note-placeholder="填写审计说明：概述明细核对程序执行情况、持股比例/分红方案/应收金额勾稽结果、拟调整及未调整事项及其影响。"
      note-hint="覆盖持股/分红方案/应收核算勾稽。"
      conclusion-hint="按 A/B/C 口径评价明细完整性与计价准确性。"
    />


    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（CAS 依据）</summary>
      <div class="guidance-content">
        <p>1. 权益份额 = 被投资方净资产 × 持股比例 / 100。</p>
        <p>2. 分红总额 = 持股数量 × 每股股利；应收股利 = 持股数量 × 每股股利。</p>
        <p>3. 实际分红率 = 分红总额 / 被投资方净利润 × 100%（净利润≤0 时显示 N/A）。</p>
        <p>4. 期末应收 = 应收股利 - 已收金额；逾期天数 = MAX(0, 当前日期 - 股权登记日)，逾期行橙色高亮。</p>
        <p>5. 灰色底纹列为自动计算列，不可手动编辑。</p>
        <p class="cas-basis">CAS 依据：成本法下于被投资单位宣告分派现金股利时确认应收股利及投资收益（《企业会计准则第 2 号——长期股权投资》、《企业会计准则第 22 号——金融工具确认和计量》）。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, toRef, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import GtIndexChip from '../GtIndexChip.vue'
import G3ImportExportDropdown from './G3ImportExportDropdown.vue'
import G3AuditTextCards from './G3AuditTextCards.vue'
import {
  useG3Detail,
  G3_DETAIL_SEGMENTS,
  G3_INVEST_TYPE_OPTIONS,
  G3_ACCOUNTING_METHOD_OPTIONS,
  isRowOverdue,
} from '../composables/useG3Detail'
import type { G3DetailColumn, DividendDetailRow } from '../composables/useG3Detail'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const detail = useG3Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const investTypeOptions = G3_INVEST_TYPE_OPTIONS
const methodOptions = G3_ACCOUNTING_METHOD_OPTIONS

// ─── 审计说明 / 审计结论（conclusion=null，文本存 remark，走白名单豁免路径） ───
const NOTE_KEY = 'G3-2-detail-audit-note'
const CONCLUSION_KEY = 'G3-2-detail-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: v })
})

// ─── 当前区段可见列（排除seq和investeeName，已作固定列） ───
const currentColumns = computed<G3DetailColumn[]>(() => {
  const seg = G3_DETAIL_SEGMENTS.find((s) => s.key === detail.segment.value)
  if (!seg) return []
  // 排除 seq 和 investeeName，它们作为固定列已单独渲染
  return seg.columns.filter((c) => c.prop !== 'seq' && c.prop !== 'investeeName')
})

// ─── 行样式：逾期行橙色 ───
function rowClassName({ row }: { row: DividendDetailRow }): string {
  return isRowOverdue(row) ? 'row-overdue' : ''
}

// ─── 公式列tooltip ───
function getFormulaTooltip(prop: keyof DividendDetailRow): string {
  const tooltips: Partial<Record<keyof DividendDetailRow, string>> = {
    seq: '序号（自动）',
    equityShare: '权益份额 = 被投资方净资产 × 持股比例 / 100',
    totalDividend: '分红总额 = 持股数量 × 每股股利',
    payoutRatio: '实际分红率 = 分红总额 / 净利润 × 100%',
    dividendReceivable: '应收股利 = 持股数量 × 每股股利',
    netReceivable: '期末应收 = 应收股利 - 已收金额',
    overdueDays: '逾期天数 = MAX(0, 当前日期 - 股权登记日)',
  }
  return tooltips[prop] ?? '公式计算'
}

// ─── 单元格格式化（分红率N/A处理） ───
function formatCellValue(row: DividendDetailRow, col: G3DetailColumn): string {
  const val = row[col.prop]
  // 分红率特殊处理：净利润≤0时显示N/A
  if (col.prop === 'payoutRatio') {
    if (row.investeeNetProfit <= 0) return 'N/A'
    return fmtNum(val)
  }
  if (typeof val === 'number') return fmtNum(val)
  return String(val ?? '')
}

// ─── 数字格式化 ───
function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

</script>

<style scoped>
.g3-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 区段Tab */
.segment-tabs {
  margin-bottom: 0;
}

.segment-tabs :deep(.el-tabs__content) {
  display: none; /* 内容区由下方el-table渲染，不需要tab-pane内容 */
}

/* 表格 */
.detail-table {
  border-top: none;
}

/* 公式列：灰底 + 虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  padding: 0 4px;
  text-align: right;
  background: #f5f7fa;
  border-radius: 2px;
}

/* 逾期行橙色 */
:deep(.row-overdue) {
  background-color: #fdf6ec !important;
}
:deep(.row-overdue td) {
  background-color: #fdf6ec !important;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 底部合计 */
.totals-bar {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  flex-wrap: wrap;
}
.totals-label {
  color: #303133;
  min-width: 36px;
}
.total-item {
  color: #606266;
}

/* 审计目标 */
.audit-objective {
  margin-bottom: 12px;
}

/* 编制提示（guidance-details gold 样式） */
.guidance-details {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}

/* 审计说明 / 审计结论卡片 */
.audit-note-card {
  margin-top: 12px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
