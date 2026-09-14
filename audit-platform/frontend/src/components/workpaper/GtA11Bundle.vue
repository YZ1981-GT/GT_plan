<script setup lang="ts">
/** A11 期后事项 — 程序表 | A11-WP-1 审定表 | A11-2 | A11-3
 *
 * 双轨路由（design §Sheet/Tab 路由契约）：
 * - 程序表 chip "A11-1" → INLINE_POPUP (docx 问询函)
 * - 底稿目录 F="A11-1" → navigate('A11', { sheet: 'A11-WP-1' }) = 本 bundle 审定表 tab
 * - chip "A11-2" → navigate('A11', { sheet: 'A11-2' }) 或独立 checklist
 */
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import GtAProgramConsole from './GtAProgramConsole.vue'
import GtDForm from './GtDForm/GtDForm.vue'
import GtEmbeddedChecklist from './GtEmbeddedChecklist.vue'

const props = defineProps<{
  wpId: string
  sheetName?: string
  schema?: Record<string, unknown>
  htmlData?: Record<string, unknown>
  readonly?: boolean
}>()

const route = useRoute()

const tabs = [
  { id: 'program', label: '审计程序' },
  { id: 'A11-WP-1', label: 'A11-1 审定表', kind: 'd-form' as const },
  { id: 'A11-2', label: 'A11-2 调查问卷', kind: 'checklist' as const },
  { id: 'A11-3', label: 'A11-3 内控问卷', kind: 'checklist' as const },
]

const active = ref(props.sheetName || 'program')

// 监听外部 sheetName 变化（路由跳转指定 tab）
watch(() => props.sheetName, (v) => {
  if (v && tabs.some(t => t.id === v)) {
    active.value = v
  }
})

// 监听 route.query.sheet（直接 URL 带参场景，如底稿目录跳转）
watch(() => route.query.sheet as string | undefined, (v) => {
  if (v && tabs.some(t => t.id === v)) {
    active.value = v
  }
})

onMounted(() => {
  const qs = route.query.sheet as string | undefined
  if (qs && tabs.some(t => t.id === qs)) {
    active.value = qs
  }
})
</script>

<template>
  <div class="a11-bundle">
    <el-tabs v-model="active">
      <el-tab-pane v-for="t in tabs" :key="t.id" :label="t.label" :name="t.id">
        <GtAProgramConsole v-if="t.id === 'program'" :wp-id="wpId" :embedded="true" />
        <GtEmbeddedChecklist
          v-else-if="t.kind === 'checklist'"
          :wp-id="wpId"
          :checklist-wp-code="t.id"
          :readonly="readonly"
        />
        <GtDForm
          v-else
          :wp-id="wpId"
          :sheet-name="t.id"
          form-type="d-form-table"
          :schema="schema || {}"
          :html-data="htmlData || {}"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
