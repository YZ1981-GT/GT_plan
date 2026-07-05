<template>
  <div class="f5-other-cost">
    <div class="f5-oc-toolbar">
      <span class="f5-oc-title">F5-3 其他业务成本明细</span>
      <div class="f5-oc-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="other.addRow()">+ 新增行</el-button>
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
      </div>
    </div>

    <el-table :data="other.rows.value" size="small" border stripe :row-class-name="rowClass" max-height="500">
      <el-table-column label="#" prop="seq" width="44" />
      <el-table-column label="成本项目" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.costItem" size="small"
            @change="(v: string) => other.updateCell(row.id, 'costItem', v)" />
          <span v-else>{{ row.costItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentAmount" size="small"
            @change="(v: any) => other.updateCell(row.id, 'currentAmount', v)" />
          <span v-else>{{ fmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.priorAmount" size="small"
            @change="(v: any) => other.updateCell(row.id, 'priorAmount', v)" />
          <span v-else>{{ fmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="100" align="right">
        <template #default="{ row }"><span class="f5-formula" title="本期-上期">{{ fmt(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="变动率%" width="100" align="right">
        <template #default="{ row }">
          <span class="f5-formula" :class="{ 'is-warn': other.isRowHighlighted(row) }" title="(本期-上期)/上期×100">
            {{ pct(row.changeRate) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="占比%" width="90" align="right">
        <template #default="{ row }"><span class="f5-formula" title="本期/合计×100">{{ pct(row.proportion) }}</span></template>
      </el-table-column>
      <el-table-column label="对应收入" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.correspondingRevenue" size="small"
            @change="(v: any) => other.updateCell(row.id, 'correspondingRevenue', v)" />
          <span v-else>{{ fmt(row.correspondingRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成本率%" width="90" align="right">
        <template #default="{ row }"><span class="f5-formula" title="本期金额/对应收入×100">{{ pct(row.costRate) }}</span></template>
      </el-table-column>
      <el-table-column label="收入确认时点" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.revenueRecognitionTiming" size="small"
            @change="(v: string) => other.updateCell(row.id, 'revenueRecognitionTiming', v)" />
          <span v-else>{{ row.revenueRecognitionTiming }}</span>
        </template>
      </el-table-column>
      <el-table-column label="成本结转时点" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.costRecognitionTiming" size="small"
            @change="(v: string) => other.updateCell(row.id, 'costRecognitionTiming', v)" />
          <span v-else>{{ row.costRecognitionTiming }}</span>
        </template>
      </el-table-column>
      <el-table-column label="配比合理性" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.matchingReasonability" size="small"
            @change="(v: string) => other.updateCell(row.id, 'matchingReasonability', v)" />
          <span v-else>{{ row.matchingReasonability }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.auditEvaluation" size="small"
            @change="(v: string) => other.updateCell(row.id, 'auditEvaluation', v)" />
          <span v-else>{{ row.auditEvaluation }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small"
            @change="(v: string) => other.updateCell(row.id, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="other.removeRow(row.id)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="f5-oc-total">
      <span>本期合计：<b>{{ fmt(other.totalRow.value.currentAmount) }}</b></span>
      <span>上期合计：{{ fmt(other.totalRow.value.priorAmount) }}</span>
      <span>变动额：{{ fmt(other.totalRow.value.changeAmount) }}</span>
    </div>

    <el-card class="f5-oc-note" shadow="never">
      <template #header>
        <div class="f5-card-header"><span>审计说明</span><el-button size="small" @click="openReview">💬 复核</el-button></div>
      </template>
      <el-input v-model="note" type="textarea" autosize :disabled="isReadonly" placeholder="其他业务成本分析说明..." @change="saveNote" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** F5TabOtherCost — F5-3 其他业务成本明细（14列 + 变动>30%橙色 + 导入导出） */
import { ref, computed, inject, type Ref } from 'vue'
import { useF5OtherCost } from '../composables/useF5OtherCost'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{ allResponses: Ref<Map<string, ChecklistResponse>>; wpId: string; isReadonly: boolean }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const NOTE_KEY = 'F5-3-audit-note'

const other = useF5OtherCost({
  allResponses: props.allResponses,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})
const note = ref(props.allResponses.value.get(NOTE_KEY)?.remark ?? '')
const ieCtx = computed(() => (isImportExportSheet('f5', 'F5-3') ? resolveImportExportSheet('f5', 'F5-3') : null))

function saveNote() {
  props.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: note.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: NOTE_KEY, conclusion: null, remark: note.value }] } }))
}
function rowClass({ row }: { row: any }): string { return other.isRowHighlighted(row) ? 'f5-row-orange' : '' }
function fmt(v: number | null | undefined): string { return v == null ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function pct(v: number | 'N/A' | null | undefined): string { return v == null || v === 'N/A' ? 'N/A' : `${v.toFixed(2)}%` }
function openReview() { openReviewDialog('F5-3-conclusion') }
</script>

<style scoped>
.f5-other-cost { padding: 12px; font-size: 13px; }
.f5-oc-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.f5-oc-title { font-weight: 600; }
.f5-oc-actions { display: flex; gap: 8px; align-items: center; }
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
.f5-oc-total { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }
.f5-oc-note { margin-top: 12px; }
.f5-card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.f5-row-orange) { background: #fdf6ec; }
</style>
