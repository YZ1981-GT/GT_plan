<template>
  <div class="f5-comparison">
    <div class="f5-cmp-toolbar">
      <span class="f5-cmp-title">F5-5 与上年度比较分析表</span>
      <div class="f5-cmp-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddRow">+ 品种</el-button>
        <CycleImportExportDropdown v-if="ieCtx" :wp-id="wpId" :api-prefix="ieCtx.apiPrefix" :sheet="ieCtx.sheet"
          :disabled="isReadonly" @imported="$emit('imported')" />
      </div>
    </div>

    <el-table :data="cmp.rows.value" size="small" border stripe :row-class-name="rowClass" max-height="500">
      <el-table-column label="品种" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.product" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'product', v)" />
          <span v-else>{{ row.product }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期收入" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentRevenue" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'currentRevenue', v)" />
          <span v-else>{{ fmt(row.currentRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期成本" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.currentCost" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'currentCost', v)" />
          <span v-else>{{ fmt(row.currentCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期毛利" width="100" align="right">
        <template #default="{ row }"><span class="f5-formula" title="收入-成本">{{ fmt(row.currentGrossProfit) }}</span></template>
      </el-table-column>
      <el-table-column label="本期毛利率%" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula" title="毛利/收入×100">{{ pct(row.currentGrossMargin) }}</span></template>
      </el-table-column>
      <el-table-column label="上期收入" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.priorRevenue" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'priorRevenue', v)" />
          <span v-else>{{ fmt(row.priorRevenue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期成本" width="110" align="right">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model.number="row.priorCost" size="small"
            @change="(v: any) => cmp.updateCell(row.id, 'priorCost', v)" />
          <span v-else>{{ fmt(row.priorCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期毛利" width="100" align="right">
        <template #default="{ row }"><span class="f5-formula" title="收入-成本">{{ fmt(row.priorGrossProfit) }}</span></template>
      </el-table-column>
      <el-table-column label="上期毛利率%" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula" title="毛利/收入×100">{{ pct(row.priorGrossMargin) }}</span></template>
      </el-table-column>
      <el-table-column label="收入变动额" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula">{{ fmt(row.revenueChange) }}</span></template>
      </el-table-column>
      <el-table-column label="收入变动率%" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula" :class="{ 'is-warn': cmp.isMismatch(row) }">{{ pct(row.revenueChangeRate) }}</span></template>
      </el-table-column>
      <el-table-column label="成本变动额" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula">{{ fmt(row.costChange) }}</span></template>
      </el-table-column>
      <el-table-column label="成本变动率%" width="110" align="right">
        <template #default="{ row }"><span class="f5-formula" :class="{ 'is-warn': cmp.isMismatch(row) }">{{ pct(row.costChangeRate) }}</span></template>
      </el-table-column>
      <el-table-column label="毛利率变动(pp)" width="120" align="right">
        <template #default="{ row }"><span class="f5-formula" :class="{ 'is-warn': cmp.isMarginChangeHigh(row) }" title="本期毛利率-上期毛利率">{{ pp(row.marginChange) }}</span></template>
      </el-table-column>
      <el-table-column label="变动原因" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.changeReason" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'changeReason', v)" />
          <span v-else>{{ row.changeReason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计评价" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.auditEvaluation" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'auditEvaluation', v)" />
          <span v-else>{{ row.auditEvaluation }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small"
            @change="(v: string) => cmp.updateCell(row.id, 'remark', v)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="cmp.removeRow(row.id)">
            <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="f5-cmp-total">
      <span>本期毛利率：<b>{{ pct(cmp.totalRow.value.currentGrossMargin) }}</b></span>
      <span>上期毛利率：{{ pct(cmp.totalRow.value.priorGrossMargin) }}</span>
      <span>本期毛利：{{ fmt(cmp.totalRow.value.currentGrossProfit) }}</span>
    </div>

    <el-card class="f5-cmp-note" shadow="never">
      <template #header>
        <div class="f5-card-header"><span>审计结论</span><el-button size="small" @click="openReview">💬 复核</el-button></div>
      </template>
      <el-input v-model="conclusion" type="textarea" autosize :disabled="isReadonly" placeholder="毛利率比较分析结论..." @change="saveConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** F5TabComparison — F5-5 比较分析（17列 + 毛利率变动>5pp橙色 + 收入成本不匹配>10%橙色 + 品种增删 + 导入导出） */
import { ref, computed, inject, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useF5Comparison } from '../composables/useF5Comparison'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()
const props = defineProps<{ allResponses: Ref<Map<string, ChecklistResponse>>; wpId: string; isReadonly: boolean }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const CONCLUSION_KEY = 'F5-5-conclusion'

const cmp = useF5Comparison({
  allResponses: props.allResponses,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})
const conclusion = ref(props.allResponses.value.get(CONCLUSION_KEY)?.remark ?? '')
const ieCtx = computed(() => (isImportExportSheet('f5', 'F5-5') ? resolveImportExportSheet('f5', 'F5-5') : null))

function saveConclusion() {
  props.allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value })
  window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items: [{ item_id: CONCLUSION_KEY, conclusion: null, remark: conclusion.value }] } }))
}
async function promptAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '品种名称不能为空',
    })
    if (value) cmp.addRow(value.trim())
  } catch { /* 取消 */ }
}
function rowClass({ row }: { row: any }): string { return cmp.isRowHighlighted(row) ? 'f5-row-orange' : '' }
function fmt(v: number | null | undefined): string { return v == null ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }
function pct(v: number | 'N/A' | null | undefined): string { return v == null || v === 'N/A' ? 'N/A' : `${v.toFixed(2)}%` }
function pp(v: number | 'N/A' | null | undefined): string { return v == null || v === 'N/A' ? 'N/A' : `${v.toFixed(2)}pp` }
function openReview() { openReviewDialog('F5-5-conclusion') }
</script>

<style scoped>
.f5-comparison { padding: 12px; font-size: 13px; }
.f5-cmp-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.f5-cmp-title { font-weight: 600; }
.f5-cmp-actions { display: flex; gap: 8px; align-items: center; }
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
.f5-cmp-total { display: flex; gap: 20px; margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; }
.f5-cmp-note { margin-top: 12px; }
.f5-card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.f5-row-orange) { background: #fdf6ec; }
</style>
