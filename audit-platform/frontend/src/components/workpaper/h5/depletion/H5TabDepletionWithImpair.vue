<template>
  <div class="h5-tab-depletion-with-impair">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-12 折耗测算（含减值·62公式）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-12')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-block">
        <p><strong>含减值后折耗</strong> = (净值 - 残值) × 当期产量 ÷ 剩余可采储量</p>
        <p>净值 = 原值 - 累计折耗 - 减值金额</p>
      </div>

      <div class="summary-row">
        <span>本期折耗合计: <b>{{ fmtAmt(state.totalCurrentDepletion.value) }}</b></span>
      </div>

      <el-table :data="state.calcRows.value" border stripe size="small" class="depletion-table" max-height="500">
        <el-table-column prop="category" label="资产分类" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.category" size="small" @change="state.updateCalcCell(row.rowId, 'category', $event)" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="cost" label="原值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.cost" :controls="false" size="small" @change="state.updateCalcCell(row.rowId, 'cost', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentAmount" label="减值金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairmentAmount" :controls="false" size="small" @change="state.updateCalcCell(row.rowId, 'impairmentAmount', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairmentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净值" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=原值-累计折耗-减值">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="salvage" label="残值" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.salvage" :controls="false" size="small" @change="state.updateCalcCell(row.rowId, 'salvage', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.salvage) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentProduction" label="当期产量" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.currentProduction" :controls="false" size="small" @change="state.updateCalcCell(row.rowId, 'currentProduction', $event ?? 0)" />
            <span v-else>{{ row.currentProduction }}</span>
          </template>
        </el-table-column>
        <el-table-column label="剩余储量" min-width="90" align="right">
          <template #default="{ row }"><span class="formula-cell" title="剩余=总储量-累计产量">{{ row.remainReserves.toFixed(2) }}</span></template>
        </el-table-column>
        <el-table-column label="本期折耗" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="=(净值-残值)×产量÷剩余储量">{{ fmtAmt(row.currentDepletion) }}</span></template>
        </el-table-column>
        <el-table-column label="折耗率(%)" min-width="80" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.depletionRate.toFixed(2) }}%</span></template>
        </el-table-column>
      </el-table>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>含减值分支：折耗基于"净值"而非原值计算</li>
        <li>净值=原值-累计折耗-已确认减值</li>
        <li>适用于已确认减值损失的油气资产组</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5Depletion } from '../../composables/useH5Depletion'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const state = useH5Depletion({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: () => {} })

function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-depletion-with-impair { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.methodology-block { padding: 10px 14px; background: #fffbe6; border-left: 3px solid #e6a23c; border-radius: 4px; margin-bottom: 12px; font-size: 12px; }
.summary-row { margin-bottom: 12px; font-size: 13px; }
.depletion-table { font-size: 13px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
