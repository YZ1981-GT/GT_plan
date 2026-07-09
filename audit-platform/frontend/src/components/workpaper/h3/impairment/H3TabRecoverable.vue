<template>
  <div class="h3-tab-recoverable">
    <!-- DCF模型 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>可收回金额 — DCF模型（H3-11）</span>
          <el-button size="small" @click="generateAI('H3-11-dcf')">AI</el-button>
        </div>
      </template>

      <!-- 假设区 -->
      <div class="assumptions-grid">
        <div class="assumption-item">
          <label>折现率(%)</label>
          <el-input v-model.number="assumptions.discountRate" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>预测期(年)</label>
          <el-input v-model.number="assumptions.forecastYears" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>永续增长率(%)</label>
          <el-input v-model.number="assumptions.terminalGrowth" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>年租金收入</label>
          <el-input v-model.number="assumptions.annualRent" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>年运营成本</label>
          <el-input v-model.number="assumptions.annualCost" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>残值</label>
          <el-input v-model.number="assumptions.residualValue" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
      </div>

      <!-- 现金流预测表 -->
      <el-table :data="cashFlowRows" border size="small" class="audit-table" style="margin-top:12px">
        <el-table-column prop="year" label="年份" width="60" align="center" />
        <el-table-column prop="revenue" label="收入" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.revenue) }}</template>
        </el-table-column>
        <el-table-column prop="cost" label="成本" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="净现金流" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.netCashFlow) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="discountFactor" label="折现系数" width="90" align="right">
          <template #default="{ row }">{{ row.discountFactor.toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="现值" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.presentValue) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- DCF结果 -->
      <div class="dcf-result">
        <span>DCF现值合计：<b>{{ fmtNum(dcfTotal) }}</b></span>
        <span>可收回金额 = MAX(公允-处置费, DCF) = <b class="result-value">{{ fmtNum(recoverableAmount) }}</b></span>
      </div>
    </el-card>

    <!-- 敏感性矩阵 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span>敏感性分析矩阵</span>
      </template>
      <el-table :data="sensitivityRows" border size="small" class="audit-table">
        <el-table-column prop="label" label="折现率 \\ 增长率" width="120" />
        <el-table-column v-for="col in sensitivityCols" :key="col" :label="col + '%'" min-width="90" align="right">
          <template #default="{ row }">
            {{ fmtNum(row[col]) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-11')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-11')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRecoverable.vue — H3-11 可收回金额DCF
 * DCF模型+敏感性矩阵
 */
import { ref, reactive, computed, inject, toRef } from 'vue'
import { useH3Impairment } from '../../composables/useH3Impairment'
import { useH3FormData } from '../../composables/useH3FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  assumptions, cashFlowRows, dcfTotal, recoverableAmount,
  sensitivityRows, sensitivityCols, updateAssumptions,
} = useH3Impairment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const auditConclusion = ref(getValue('H3-11-conclusion') ?? '')

function onAssumptionChange() {
  updateAssumptions(assumptions)
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-recoverable { padding: 16px; font-size: 13px; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.assumptions-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.assumption-item label { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.audit-table { font-size: 13px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.dcf-result { display: flex; align-items: center; gap: 24px; margin-top: 12px; padding: 10px 14px; background: var(--el-fill-color-lighter); border-radius: 4px; font-weight: 500; }
.result-value { font-size: 16px; color: var(--el-color-primary); }
.conclusion-card { margin-top: 16px; }
.action-btns { display: flex; gap: 4px; }
</style>
