<template>
  <div class="h5-tab-recoverable">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：运用储量折现(DCF)法估算油气资产可收回金额，验证折现率、油价、储量等关键假设的合理性。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-15" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-15 可收回金额测试（DCF储量折现）</span>
          <div class="title-actions">
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

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5, maxRows: 8 }"
        placeholder="填写可收回金额测试审计说明..." :disabled="isReadonly" @change="savePolishNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3, maxRows: 6 }"
        placeholder="填写可收回金额测试审计结论..." :disabled="isReadonly" @change="savePolishConclusion" />
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
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Impairment } from '../../composables/useH5Impairment'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5Impairment({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: (itemId: string, value: any) => formData.setResponse(itemId, value) })

// 审计说明/结论（component-local H5-15，独立于 H5-14 键，conclusion:null）
const NOTE_KEY = 'H5-15-audit-note'
const CONCLUSION_KEY = 'H5-15-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')
function savePolishNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void formData.saveResponse(NOTE_KEY, val)
}
function savePolishConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void formData.saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.h5-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
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
