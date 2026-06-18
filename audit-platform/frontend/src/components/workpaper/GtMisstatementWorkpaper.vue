<script setup lang="ts">
/**
 * GtMisstatementWorkpaper.vue — A13 错报 Tab 套件
 *
 * Tab 结构：程序表 | A13-1 汇总 | A13-2 错报明细 | A13-3 合计 | A13-4 舞弊 | A13-5 沟通
 *
 * A13-2~5 使用 d-form-table 子模式。
 * 持久化策略：Tab 容器自行调用 POST /api/workpapers/{wpId}/save，
 * 以 activeTab 作为 sheet_name 保存到 parsed_data.html_data[tabId]。
 * 这避免了 GtWpRenderer.onSave 使用外层 activeSheetName 导致 sub-tab
 * 数据存错位的问题。
 */
import { ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import GtAProgramConsole from './GtAProgramConsole.vue'
import MisstatementSummaryView from './MisstatementSummaryView.vue'
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

const activeTab = ref(props.sheetName || 'program')

// 监听外部 sheetName 变化（路由跳转指定 tab）
watch(() => props.sheetName, (v) => {
  if (v && tabs.some(t => t.id === v)) {
    activeTab.value = v
  }
})

const tabs = [
  { id: 'program', label: '程序表' },
  { id: 'summary', label: 'A13-1 汇总' },
  { id: 'A13-2', label: 'A13-2 错报明细' },
  { id: 'A13-3', label: 'A13-3 合计' },
  { id: 'A13-4', label: 'A13-4 舞弊' },
  { id: 'A13-5', label: 'A13-5 沟通' },
]

/** d-form 子 Tab 的 schema 提取（从父 schema.sheets 按 tab id 解包） */
function getTabSchema(tabId: string): Record<string, any> {
  const s = props.schema as Record<string, any> | undefined
  if (!s) return { form_type: 'table' }
  // render-config 返回的 schema 可能有 sheets 嵌套
  const nested = (s as any)?.sheets?.[tabId]
  if (nested && typeof nested === 'object') return nested as Record<string, any>
  // 直接传整体 schema（GtDForm 内部会按 form_type 分发）
  return { form_type: 'table' }
}

/** d-form 子 Tab 的 htmlData 提取（从 parsed_data.html_data[tabId] 按 tab id 读） */
function getTabHtmlData(tabId: string): Record<string, any> {
  const h = props.htmlData as Record<string, any> | undefined
  if (!h) return {}
  // htmlData 可能按 sheet_name 分键存储
  if (h[tabId] && typeof h[tabId] === 'object') return h[tabId] as Record<string, any>
  return {}
}

/**
 * GtDForm 保存回调 — 直接持久化到后端
 * 使用当前 activeTab 作为 sheet_name，确保 sub-tab 数据存到正确的键下。
 */
async function onDFormSave(data: Record<string, any>) {
  try {
    await api.post(`/api/workpapers/${props.wpId}/save`, {
      sheet_name: activeTab.value,
      html_data: data,
      schema_version: 'v2025-R5',
    })
  } catch (e) {
    console.warn('[GtMisstatementWorkpaper] 保存失败:', e)
  }
  // 同时 emit save 通知外层（刷新、脏状态等）
  emit('save', data)
}
</script>

<template>
  <div class="misstatement-workpaper">
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane
        v-for="t in tabs"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <!-- 程序表 -->
        <GtAProgramConsole
          v-if="t.id === 'program'"
          :wp-id="wpId"
          :embedded="true"
        />

        <!-- A13-1 汇总 -->
        <MisstatementSummaryView
          v-else-if="t.id === 'summary'"
          :wp-id="wpId"
        />

        <!-- A13-2 ~ A13-5 d-form-table -->
        <GtDForm
          v-else
          :wp-id="wpId"
          :sheet-name="t.id"
          form-type="d-form-table"
          :schema="getTabSchema(t.id)"
          :html-data="getTabHtmlData(t.id)"
          :readonly="readonly"
          @save="onDFormSave"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.misstatement-workpaper {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.misstatement-workpaper :deep(.el-tabs) {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.misstatement-workpaper :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
}
</style>
