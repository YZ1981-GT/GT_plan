<template>
  <div class="gt-confirmation-reliability">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-reliability__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：reliability-v1 -->
    <template v-else>
      <!-- 看板 -->
      <ReliabilityDashboard :metrics="data.metrics.value" />

      <!-- 可靠性验证网格 -->
      <ReliabilityGrid
        :rows="data.rows.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :is-verification-disabled="data.isVerificationDisabled"
        :get-row-quality-status="data.getRowQualityStatus"
        @add="handleAdd"
        @delete="handleDelete"
        @save="handleSave"
        @update="handleUpdate"
        @import-d01="handleImportD01"
        @import-excel="handleImportExcel"
        @export-excel="handleExportExcel"
        @jump-d01="handleJumpD01"
      />

      <!-- 审计说明 + 结论 -->
      <ReliabilityConclusion
        :audit-note="data.auditNote.value"
        :conclusion="data.conclusion.value"
        :readonly="readonly"
        @update-note="handleAuditNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useReliabilityData } from './composables/useReliabilityData'

import ReliabilityDashboard from './ReliabilityDashboard.vue'
import ReliabilityGrid from './ReliabilityGrid.vue'
import ReliabilityConclusion from './ReliabilityConclusion.vue'

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
const isNewFormat = computed(() => props.htmlData?._format === 'reliability-v1')

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useReliabilityData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAdd() {
  data.addRow()
}

function handleDelete(ids: string[]) {
  data.deleteRows(ids)
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

function handleUpdate(rowId: string, field: string, value: any) {
  data.updateField(rowId, field, value)
}

function handleImportD01() {
  // TODO: 调用跨底稿引用机制获取 D0-1 回函方式=传真/电子邮件行
  // 映射：confirm_index / entity_name / reply_method
  console.log('[GtConfirmationReliability] 从 D0-1 带入电子回函（待接入跨底稿引用）')
}

function handleImportExcel() {
  // TODO: 复用 useExcelIO 批量导入
  console.log('[GtConfirmationReliability] Excel 导入')
}

function handleExportExcel() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationReliability] Excel 导出')
}

function handleJumpD01(confirmIndex: string) {
  // TODO: 跨底稿跳转 D0-1
  console.log('[GtConfirmationReliability] 跳转 D0-1:', confirmIndex)
}

function handleAuditNoteUpdate(field: string, value: string) {
  ;(data.auditNote.value as any)[field] = value
  data.isDirty.value = true
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
  data.isDirty.value = true
}
</script>

<style scoped>
.gt-confirmation-reliability {
  padding: 8px 0;
}

.gt-confirmation-reliability__legacy-notice {
  margin-bottom: 12px;
}
</style>
