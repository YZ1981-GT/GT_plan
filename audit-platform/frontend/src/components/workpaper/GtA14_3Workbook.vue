<script setup lang="ts">
/** A14-3 IT 缺陷 workbook Tab 容器 */
import { ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import GtDForm from './GtDForm/GtDForm.vue'

const props = defineProps<{
  wpId: string
  sheetName?: string
  schema?: Record<string, unknown>
  htmlData?: Record<string, unknown>
  readonly?: boolean
}>()

const emit = defineEmits<{
  save: [data: Record<string, any>]
}>()

const tabs = [
  { id: 'defect-list', label: 'IT缺陷汇总表' },
  { id: 'eval-step1', label: '步骤一' },
  { id: 'eval-step2', label: '步骤二' },
  { id: 'eval-step3', label: '步骤三' },
  { id: 'comm', label: '沟通纪要' },
]

const active = ref(
  props.sheetName && tabs.some(t => t.id === props.sheetName) ? props.sheetName : 'defect-list',
)

// 监听外部 sheetName 变化（深链接跳转）
watch(() => props.sheetName, (v) => {
  if (v && tabs.some(t => t.id === v)) {
    active.value = v
  }
})

/** d-form 保存回调 — 直接持久化到后端 */
async function onDFormSave(data: Record<string, any>) {
  try {
    await api.post(`/api/workpapers/${props.wpId}/save`, {
      sheet_name: active.value,
      html_data: data,
      schema_version: 'v2025-R5',
    })
  } catch (e) {
    console.warn('[GtA14_3Workbook] 保存失败:', e)
  }
  emit('save', data)
}
</script>

<template>
  <div class="a14-3-workbook">
    <el-tabs v-model="active">
      <el-tab-pane v-for="t in tabs" :key="t.id" :label="t.label" :name="t.id" lazy>
        <GtDForm
          :wp-id="wpId"
          :sheet-name="t.id"
          form-type="d-form-table"
          :schema="schema"
          :html-data="htmlData"
          :readonly="readonly"
          @save="onDFormSave"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
