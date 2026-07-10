<template>
  <div class="f2-questionnaire-wrapper">
    <div v-if="showMigrationBtn" class="migration-banner">
      <el-alert type="info" :closable="false" show-icon>
        <template #title>
          检测到旧版 OO 地点表数据，可一键写入结构化字段
        </template>
        <el-button size="small" type="primary" @click="doMigrateWrite">一键写入</el-button>
      </el-alert>
    </div>
    <F2StocktakeSectionForm
      title="盘点计划问卷 F2-21"
      sheet-code="F2-21"
      fields-key="F2-21-fields"
      note-key="F2-21-note"
      :field-defs="F2_21_FIELDS"
      :wp-id="wpId"
      :project-id="projectId"
      :all-responses="allResponses"
      :is-readonly="isReadonly"
      ai-section="stocktake-questionnaire"
      ai-title="AI 生成 · 盘点问卷结论"
      audit-note-label="问卷结论"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import { F2_21_FIELDS } from './f2StocktakeConfigs'
import { migrateF21RowsToFields } from '../../composables/useF2StocktakeSheet'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

/**
 * 首次迁移条件：
 * 1. checklist_responses 中 F2-21-fields 为空或所有字段为空串
 * 2. F2-21-rows 有旧版 OO 数据
 * 3. migrateF21RowsToFields 能产出有效 patch
 */
const showMigrationBtn = computed(() => {
  if (props.isReadonly) return false
  const fieldsRaw = props.allResponses.get('F2-21-fields')?.remark
  let existingFields: Record<string, string> | null = null
  if (fieldsRaw) {
    try {
      existingFields = JSON.parse(fieldsRaw)
    } catch { /* ignore */ }
  }
  // 如果已有非空字段值，不显示
  if (existingFields && Object.values(existingFields).some((v) => String(v || '').trim())) {
    return false
  }
  const rowsRaw = props.allResponses.get('F2-21-rows')?.remark
  if (!rowsRaw) return false
  const patch = migrateF21RowsToFields(rowsRaw, existingFields)
  return patch !== null && Object.keys(patch).length > 0
})

function doMigrateWrite() {
  const fieldsRaw = props.allResponses.get('F2-21-fields')?.remark
  let existingFields: Record<string, string> = {}
  if (fieldsRaw) {
    try { existingFields = JSON.parse(fieldsRaw) } catch { /* ignore */ }
  }
  const rowsRaw = props.allResponses.get('F2-21-rows')?.remark
  const patch = migrateF21RowsToFields(rowsRaw, null)
  if (!patch) { ElMessage.warning('无可迁移数据'); return }

  const merged = { ...existingFields, ...patch }
  const updated: ChecklistResponse = {
    item_id: 'F2-21-fields',
    conclusion: null,
    remark: JSON.stringify(merged),
  }
  props.allResponses.set('F2-21-fields', updated)
  window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail: { items: [updated] } }))
  ElMessage.success('旧版数据已写入结构化字段')
}
</script>

<style scoped>
.f2-questionnaire-wrapper { font-size: 13px; }
.migration-banner { margin-bottom: 12px; }
.migration-banner .el-button { margin-top: 6px; }
</style>
