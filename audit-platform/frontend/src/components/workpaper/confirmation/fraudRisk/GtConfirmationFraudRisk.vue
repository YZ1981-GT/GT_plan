<template>
  <div class="gt-confirmation-fraud-risk">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-fraud-risk__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：fraud-risk-d08-v1 -->
    <template v-else>
      <!-- 看板 -->
      <FraudRiskDashboard :metrics="data.metrics.value" />

      <!-- 检查清单 -->
      <FraudRiskChecklist
        :items="data.items.value"
        :readonly="readonly"
        :is-highlighted="data.isHighlighted"
        :needs-countermeasure="data.needsCountermeasure"
        @add="handleAddItem"
        @delete="handleDeleteItem"
        @update="handleUpdateItem"
        @import="handleImport"
        @export="handleExport"
        @jump-ref="handleJumpRef"
      />

      <!-- 汇总评价 -->
      <FraudRiskSummary
        :summary="data.summary.value"
        :readonly="readonly"
        @update="handleSummaryUpdate"
        @jump-b50="handleJumpB50"
      />

      <!-- 审计结论 -->
      <FraudRiskConclusion
        :conclusion="data.conclusion.value"
        :metrics="data.metrics.value"
        :readonly="readonly"
        @update="handleConclusionUpdate"
      />

      <!-- 保存按钮 -->
      <div v-if="!readonly" class="gt-confirmation-fraud-risk__actions">
        <el-button
          type="primary"
          :disabled="!data.isDirty.value"
          @click="handleSave"
        >
          保存
        </el-button>
        <span v-if="data.isDirty.value" class="gt-confirmation-fraud-risk__dirty-hint">
          有未保存的更改
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useFraudRiskData } from './composables/useFraudRiskData'
import FraudRiskDashboard from './FraudRiskDashboard.vue'
import FraudRiskChecklist from './FraudRiskChecklist.vue'
import FraudRiskSummary from './FraudRiskSummary.vue'
import FraudRiskConclusion from './FraudRiskConclusion.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => {
  // 新格式或空数据都走新组件
  const d = props.htmlData
  return !d || d._format === 'fraud-risk-d08-v1' || Object.keys(d).length === 0
})

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useFraudRiskData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAddItem() {
  data.addItem()
}

function handleDeleteItem(rowId: string) {
  data.deleteItem(rowId)
}

function handleUpdateItem(rowId: string, field: string, value: any) {
  data.updateItem(rowId, field, value)
}

function handleSummaryUpdate(field: string, value: string) {
  ;(data.summary.value as any)[field] = value
  data.isDirty.value = true
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
  data.isDirty.value = true
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
  data.isDirty.value = false
}

function handleImport() {
  // TODO: 复用 useExcelIO 批量导入自定义条目
  console.log('[GtConfirmationFraudRisk] Excel 导入')
}

function handleExport() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationFraudRisk] Excel 导出')
}

function handleJumpRef(ref: string) {
  // TODO: 跨底稿跳转（通过 useConfirmationNavigation）
  console.log('[GtConfirmationFraudRisk] 跳转索引:', ref)
}

function handleJumpB50() {
  // TODO: 跳转 B50 风险评估底稿
  console.log('[GtConfirmationFraudRisk] 跳转 B50')
}
</script>

<style scoped>
.gt-confirmation-fraud-risk {
  padding: 8px 0;
}

.gt-confirmation-fraud-risk__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-fraud-risk__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-extra-light);
}

.gt-confirmation-fraud-risk__dirty-hint {
  font-size: 12px;
  color: var(--el-color-warning);
}
</style>
