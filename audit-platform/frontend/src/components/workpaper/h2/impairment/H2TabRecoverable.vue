<template>
  <div class="h2-tab-recoverable">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>可收回金额 = MAX(公允价值-处置费用, 预计未来现金流量现值)</strong></p>
      <p>预计未来现金流量现值采用DCF折现模型：PV = Σ(CF_t / (1+r)^t) + TV / (1+r)^n</p>
      <p>终值TV = CF_n × (1+g) / (r-g)（Gordon永续增长模型）</p>
    </div>

    <!-- DCF假设区域 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、关键假设</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('dcf-assumptions')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-16')">💬</el-button>
          </div>
        </div>
      </template>
      <div class="assumptions-grid">
        <div class="assumption-item">
          <span class="assumption-label">折现率(WACC)：</span>
          <el-input-number v-if="!isReadonly" v-model="state.assumptions.value.discountRate"
            :controls="false" :precision="2" :step="0.01" size="small" style="width:120px"
            @change="onAssumptionChange('discountRate', $event)" />
          <span v-else>{{ state.assumptions.value.discountRate ?? '-' }}</span>
          <span class="unit">%</span>
        </div>
        <div class="assumption-item">
          <span class="assumption-label">预测期(年)：</span>
          <el-input-number v-if="!isReadonly" v-model="state.assumptions.value.forecastYears"
            :controls="false" :min="1" :max="20" size="small" style="width:80px"
            @change="onAssumptionChange('forecastYears', $event)" />
          <span v-else>{{ state.assumptions.value.forecastYears ?? '-' }}</span>
        </div>
        <div class="assumption-item">
          <span class="assumption-label">永续增长率：</span>
          <el-input-number v-if="!isReadonly" v-model="state.assumptions.value.growthRate"
            :controls="false" :precision="2" :step="0.01" size="small" style="width:120px"
            @change="onAssumptionChange('growthRate', $event)" />
          <span v-else>{{ state.assumptions.value.growthRate ?? '-' }}</span>
          <span class="unit">%</span>
        </div>
        <div class="assumption-item">
          <span class="assumption-label">处置费用率：</span>
          <el-input-number v-if="!isReadonly" v-model="state.assumptions.value.disposalCostRate"
            :controls="false" :precision="2" :step="0.01" size="small" style="width:120px"
            @change="onAssumptionChange('disposalCostRate', $event)" />
          <span v-else>{{ state.assumptions.value.disposalCostRate ?? '-' }}</span>
          <span class="unit">%</span>
        </div>
      </div>
    </el-card>

    <!-- 现金流预测 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>二、现金流预测</span></div>
      </template>

      <el-table :data="state.cashFlowRows.value" border stripe size="small" class="cf-table">
        <el-table-column prop="year" label="年份" width="80" align="center" />
        <el-table-column prop="revenue" label="收入预测" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.revenue" :controls="false"
              size="small" class="amt-input" @change="onCfChange(row.rowId, 'revenue', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.revenue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="cost" label="成本预测" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.cost" :controls="false"
              size="small" class="amt-input" @change="onCfChange(row.rowId, 'cost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净现金流" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=收入-成本">{{ fmtAmt(row.netCashFlow) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折现因子" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=1/(1+r)^t">{{ row.discountFactor?.toFixed(4) ?? '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="现值" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=净现金流×折现因子">{{ fmtAmt(row.presentValue) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 计算结果 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>三、可收回金额计算</span></div>
      </template>
      <div class="result-grid">
        <div class="result-item">
          <span class="result-label">预测期现金流现值合计：</span>
          <span class="result-value formula-cell" title="Σ(CF_t/(1+r)^t)">{{ fmtAmt(state.pvTotal.value) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">终值现值：</span>
          <span class="result-value formula-cell" title="TV/(1+r)^n">{{ fmtAmt(state.tvPresent.value) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">预计未来现金流量现值(A)：</span>
          <span class="result-value formula-cell highlight">{{ fmtAmt(state.totalPV.value) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">公允价值-处置费用(B)：</span>
          <span class="result-value">
            <el-input-number v-if="!isReadonly" v-model="state.fairValueLessDisposal.value"
              :controls="false" size="small" style="width:140px"
              @change="onAssumptionChange('fairValueLessDisposal', $event)" />
            <span v-else class="formula-cell">{{ fmtAmt(state.fairValueLessDisposal.value) }}</span>
          </span>
        </div>
        <div class="result-item total-item">
          <span class="result-label">可收回金额 = MAX(A, B)：</span>
          <span class="result-value formula-cell highlight" :title="`MAX(${fmtAmt(state.totalPV.value)}, ${fmtAmt(state.fairValueLessDisposal.value)})`">
            {{ fmtAmt(state.recoverableAmount.value) }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 敏感性矩阵 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>四、敏感性分析</span></div>
      </template>
      <el-table :data="state.sensitivityMatrix.value" border size="small" class="sensitivity-table">
        <el-table-column prop="label" label="折现率 \\ 增长率" width="120" align="center" fixed />
        <el-table-column v-for="col in state.sensitivityCols.value" :key="col"
          :label="`g=${col}%`" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'error-amount': row[`g_${col}`] < (state.assumptions.value.bookValue ?? 0) }">
              {{ fmtAmt(row[`g_${col}`]) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <p class="sensitivity-note">
        红色值表示可收回金额低于账面价值（即需计提减值）
      </p>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>折现率通常采用WACC(加权平均资本成本)，一般8%~15%</li>
        <li>预测期通常5年，永续增长率不超过GDP增长率</li>
        <li>终值=最后一年现金流×(1+g)/(r-g)（Gordon模型）</li>
        <li>可收回金额=MAX(使用价值, 公允-处置费用)</li>
        <li>敏感性分析：红色表示该参数组合下需计提减值</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabRecoverable.vue — H2-16 可收回金额
 * DCF模型(假设+现金流预测+折现) + 敏感性矩阵
 * Spec: Task 4.19 | Requirements: 12.3-12.4
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Impairment } from '../../composables/useH2Impairment'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2Impairment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  section: 'recoverable',
})

function onAssumptionChange(field: string, value: any) {
  state.updateAssumption(field, value)
}

function onCfChange(rowId: string, field: string, value: any) {
  state.updateCashFlowCell(rowId, field, value)
}

function handleAiGenerate(section: string) {
  console.log('AI generate H2-16:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-recoverable { padding: 16px; font-size: 13px; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 13px;
}
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.assumptions-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.assumption-item { display: flex; align-items: center; gap: 8px; }
.assumption-label { font-weight: 500; min-width: 110px; }
.unit { color: var(--el-text-color-secondary); }
.cf-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.formula-cell.highlight { color: var(--el-color-primary); font-weight: 600; }
.result-grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
.result-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.result-item.total-item { padding: 12px; background: var(--el-fill-color-light); border-radius: 4px; font-size: 14px; }
.result-label { font-weight: 500; min-width: 200px; }
.result-value { font-weight: 600; }
.sensitivity-table { font-size: 13px; }
.sensitivity-note { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
