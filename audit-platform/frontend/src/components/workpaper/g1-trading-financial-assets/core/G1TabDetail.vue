<template>
  <div class="g1-detail">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-2 交易性金融资产明细表</h3>
        <p class="sheet-sub">按投资品种列示成本、公允价值与投资收益，勾稽审定表科目 1501</p>
      </div>
      <div class="head-actions">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-2"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">+ 新增证券</el-button>
      </div>
    </div>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按投资品种（股票 / 基金 / 债券 / 衍生工具 / 其他）分区段列示，涵盖成本、公允价值与投资收益。</p>
        <p>2. 虚线下划线列为自动计算列（期末数量 / 期末公允价值 / 公允变动 / 已实现损益 / 投资收益合计 / 期末成本 / 审定 / 差异），不可手工改写。</p>
        <p>3. 公允价值来源按 Level 1/2/3 划分，应与 G1-6 公允价值测试表一致。</p>
        <p>4. 分类小计与总计应与审定表（G1-1，科目 1501）勾稽。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实各投资品种期末成本、公允价值及投资收益明细的准确与完整，验证公允价值层级划分恰当，为审定表（G1-1）提供明细支撑。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info" effect="plain">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="rows"
      border
      stripe
      size="small"
      max-height="500"
      highlight-current-row
      class="detail-table"
    >
      <el-table-column prop="securityName" label="证券名称" width="140" fixed />

      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' || col.formula ? 'right' : undefined"
      >
        <template #default="{ row }">
          <span v-if="col.formula" class="formula-cell" :title="formulaHint(col.prop)">
            {{ fmtCell(row[col.prop]) }}
          </span>
          <el-select
            v-else-if="col.type === 'invest'"
            v-model="row.investType"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { investType: row.investType })"
          >
            <el-option v-for="o in investOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-select
            v-else-if="col.type === 'level'"
            v-model="row.fairValueSource"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { fairValueSource: row.fairValueSource })"
          >
            <el-option value="1" label="Level 1" />
            <el-option value="2" label="Level 2" />
            <el-option value="3" label="Level 3" />
          </el-select>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else-if="col.type === 'date'"
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            placeholder="YYYY-MM-DD"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right" align="center">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-panel">
      <div v-for="st in subtotalsByType" :key="st.investType" class="subtotal-line">
        <span class="subtotal-label">{{ st.investLabel }}小计</span>
        <span class="subtotal-meta">{{ st.count }} 项</span>
        <span>期末成本 {{ fmtCell(st.totals.closingCost) }}</span>
        <span>公允价值 {{ fmtCell(st.totals.closingFairValue) }}</span>
        <span>审定 {{ fmtCell(st.totals.adjusted) }}</span>
      </div>
      <div class="grand-total">
        <span class="subtotal-label">总计</span>
        <span>期末成本 {{ fmtCell(grandTotal.closingCost) }}</span>
        <span>公允价值 {{ fmtCell(grandTotal.closingFairValue) }}</span>
        <span>投资收益 {{ fmtCell(grandTotal.totalIncome) }}</span>
        <span>审定 {{ fmtCell(grandTotal.adjusted) }}</span>
      </div>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      :related-context="{
        明细行数: rows.length,
        期末成本合计: grandTotal.closingCost,
        期末公允价值合计: grandTotal.closingFairValue,
        投资收益合计: grandTotal.totalIncome,
        审定余额合计: grandTotal.adjusted,
      }"
      note-placeholder="填写审计说明：（1）执行的明细核对程序及结果；（2）各投资品种成本、公允价值、投资收益的核实情况及异常事项；（3）与审定表勾稽结果。"
      note-hint="覆盖明细核对程序、各品种成本/公允价值/收益核实、公允层级及与审定表勾稽。"
      conclusion-hint="按 A/B/C 口径表述明细完整性、公允计量及与 G1-1 勾稽结论。"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, watch } from 'vue'
import {
  useG1Detail,
  G1_INVEST_TYPE_OPTIONS,
  type TradingDetailRow,
} from '../../composables/useG1Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const {
  segments,
  segment,
  rows,
  subtotalsByType,
  grandTotal,
  addRow,
  updateRow,
  removeRow,
  loadAll,
} = useG1Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const wpId = computed(() => props.wpId ?? '')

const AUDIT_NOTE_KEY = 'G1-2-audit-note'
const AUDIT_CONCLUSION_KEY = 'G1-2-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')

watch(
  () => props.allResponses.get(AUDIT_NOTE_KEY)?.remark,
  (v) => { if (v != null) auditNote.value = v },
)
watch(
  () => props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark,
  (v) => { if (v != null) auditConclusion.value = v },
)
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
})

const investOptions = G1_INVEST_TYPE_OPTIONS
const segmentOptions = segments.map((s) => ({ label: s.label, value: s.key }))

const currentColumns = computed(() => {
  const seg = segments.find((s) => s.key === segment.value)
  return (seg?.columns ?? []).filter((c) => c.prop !== 'securityName')
})

const FORMULA_HINTS: Partial<Record<keyof TradingDetailRow, string>> = {
  closingQuantity: '期末持有数量 = 期初 + 买入 - 卖出',
  closingFairValue: '期末公允价值 = 期末持有数量 × 期末单位公允值',
  fairValueChange: '公允价值变动 = 期末公允价值 - 期初公允价值',
  realizedGain: '已实现损益 = 处置收入 - 处置成本',
  totalIncome: '投资收益合计 = 已实现损益 + 利息/股利收入',
  closingCost: '期末成本 = 期初成本 + 本期增加成本 - 本期减少成本',
  adjusted: '审定余额 = 未审 + AJE + RJE',
  variance: '差异 = 审定余额 - 期末公允价值',
}

function formulaHint(prop: keyof TradingDetailRow): string {
  return FORMULA_HINTS[prop] ?? ''
}

function fmtCell(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}

function onImported() {
  emit('imported')
  loadAll()
}
</script>

<style scoped>
.g1-detail {
  padding: 4px 4px 20px;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.g1-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.g1-detail :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.title-block { min-width: 200px; }
.sheet-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #1f2a37;
}
.sheet-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: #86909c;
  line-height: 1.4;
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.guidance-details {
  margin-bottom: 12px;
  border: 1px solid #e8ecf2;
  border-left: 3px solid #60418a;
  background: linear-gradient(90deg, #f7f4fb 0%, #fafbfc 48%);
  border-radius: 6px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #60418a;
  list-style: none;
}
.guidance-details summary::-webkit-details-marker { display: none; }
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.65;
}
.guidance-content p { margin: 2px 0; }

.objective-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.segment-bar { max-width: 100%; }

.detail-table { width: 100%; border-radius: 6px; overflow: hidden; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
}

.totals-panel {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.subtotal-line,
.grand-total {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: baseline;
}
.subtotal-label { font-weight: 600; color: #303133; min-width: 72px; }
.subtotal-meta { color: #909399; }
.grand-total {
  margin-top: 2px;
  padding-top: 8px;
  border-top: 1px solid #e4e7ed;
  font-weight: 600;
  color: #303133;
}

.audit-text-card {
  margin-top: 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}
.audit-text-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafbfc;
  border-bottom: 1px solid #ebeef5;
}
.audit-text-card :deep(.el-card__body) { padding: 12px 16px 16px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.card-title { font-size: 14px; font-weight: 600; color: #1f2a37; }
.card-hint { margin-top: 2px; font-size: 12px; color: #86909c; line-height: 1.4; }
</style>
