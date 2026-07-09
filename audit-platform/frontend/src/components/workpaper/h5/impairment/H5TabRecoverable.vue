<template>
  <div class="h5-tab-recoverable">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-15 可收回金额测试（DCF储量折现）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-15')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-block">
        <p><strong>可收回金额</strong> = max(公允价值减处置费用, 预计未来现金流量现值)</p>
        <p>油气资产通常采用储量折现法(DCF)估算未来现金流量现值</p>
      </div>

      <!-- DCF假设参数 -->
      <el-descriptions title="DCF关键假设" :column="3" size="small" border class="dcf-params">
        <el-descriptions-item label="折现率(%)">
          <el-input-number v-if="!isReadonly" v-model="state.dcfAssumptions.value.discountRate" :controls="false" :precision="2" size="small"
            @change="state.updateDcfAssumption('discountRate', $event ?? 10)" />
          <span v-else>{{ state.dcfAssumptions.value.discountRate }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="预测年限">
          <el-input-number v-if="!isReadonly" v-model="state.dcfAssumptions.value.projectionYears" :controls="false" :min="1" :max="50" size="small"
            @change="state.updateDcfAssumption('projectionYears', $event ?? 15)" />
          <span v-else>{{ state.dcfAssumptions.value.projectionYears }}年</span>
        </el-descriptions-item>
        <el-descriptions-item label="终值增长率(%)">
          <el-input-number v-if="!isReadonly" v-model="state.dcfAssumptions.value.terminalGrowthRate" :controls="false" :precision="2" size="small"
            @change="state.updateDcfAssumption('terminalGrowthRate', $event ?? 0)" />
          <span v-else>{{ state.dcfAssumptions.value.terminalGrowthRate }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="油价假设(元/吨)">
          <el-input-number v-if="!isReadonly" v-model="state.dcfAssumptions.value.oilPrice" :controls="false" size="small"
            @change="state.updateDcfAssumption('oilPrice', $event ?? 4500)" />
          <span v-else>{{ state.dcfAssumptions.value.oilPrice }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="产量递减率(%)">
          <el-input-number v-if="!isReadonly" v-model="state.dcfAssumptions.value.productionDeclineRate" :controls="false" :precision="2" size="small"
            @change="state.updateDcfAssumption('productionDeclineRate', $event ?? 5)" />
          <span v-else>{{ state.dcfAssumptions.value.productionDeclineRate }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="储量估计(万吨)">
          <el-input-number v-if="!isReadonly" v-model="state.dcfAssumptions.value.reservesEstimate" :controls="false" size="small"
            @change="state.updateDcfAssumption('reservesEstimate', $event ?? 0)" />
          <span v-else>{{ state.dcfAssumptions.value.reservesEstimate }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert v-if="state.dcfAssumptions.value.reservesEstimate === 0" type="warning" :closable="false" show-icon class="reserve-warn">
        请录入预计可采储量（来源：地质勘探报告）
      </el-alert>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折现率应反映资产特定风险（通常WACC+行业溢价）</li>
        <li>油价假设需参考国际油价走势及企业内部预测</li>
        <li>产量递减率参考油田历史递减曲线</li>
        <li>储量估计需由合格储量评估师提供</li>
        <li>复杂DCF模型建议使用OnlyOffice查看详细现金流表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5Impairment } from '../../composables/useH5Impairment'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const state = useH5Impairment({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: () => {} })

function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.h5-tab-recoverable { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.methodology-block { padding: 10px 14px; background: #fffbe6; border-left: 3px solid #e6a23c; border-radius: 4px; margin-bottom: 16px; font-size: 12px; }
.dcf-params { margin-bottom: 16px; }
.reserve-warn { margin-top: 12px; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
