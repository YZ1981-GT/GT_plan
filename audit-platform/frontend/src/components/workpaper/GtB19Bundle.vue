<script setup lang="ts">
/**
 * GtB19Bundle — B19 审计工作方案聚合组件
 *
 * 将 B19 程序表 + B19-1 审计方案附件 聚合为 Bundle，
 * 内部通过 el-tabs 分发渲染各子底稿。
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import GtAProgramConsole from './GtAProgramConsole.vue'

const GtDForm = defineAsyncComponent(() => import('./GtDForm/GtDForm.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
}>()

// ─── Tab 配置（静态） ───
const TABS = [
  { id: 'program', label: '程序表', wpCode: null },
  { id: 'B19-1', label: 'B19-1 审计方案附件', wpCode: 'B19-1' },
]

// ─── State ───
const route = useRoute()
const active = ref('')
const wpIndex = ref<WpIndexItem[]>([])
const loading = ref(false)

// ─── wp_id 解析 ───
const wpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of wpIndex.value) {
    if (item.wp_code?.startsWith('B19-')) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

// ─── 仅显示程序表 tab + wp_index 中存在的子底稿 Tab ───
const visibleTabs = computed(() =>
  TABS.filter(t => t.wpCode === null || !!wpIdMap.value[t.wpCode])
)

// ─── sheetName 路由 ───
watch(() => props.sheetName, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) {
    active.value = v
  }
})

watch(() => route.query.sheet as string | undefined, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) {
    active.value = v
  }
})

// ─── Lifecycle ───
onMounted(async () => {
  loading.value = true
  try {
    if (props.projectId) {
      wpIndex.value = await getWpIndex(props.projectId)
    }
  } catch {
    wpIndex.value = []
  } finally {
    loading.value = false
  }

  const sheet = props.sheetName || (route.query.sheet as string)
  if (sheet && visibleTabs.value.some(t => t.id === sheet)) {
    active.value = sheet
  } else {
    active.value = visibleTabs.value[0]?.id || ''
  }
})
</script>

<template>
  <div class="gt-b19-bundle" v-loading="loading">
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="t in visibleTabs"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <GtAProgramConsole
          v-if="t.id === 'program'"
          :wp-id="wpId"
          :embedded="true"
          :readonly="readonly"
        />
        <GtDForm
          v-else-if="t.wpCode === 'B19-1'"
          :wp-id="wpIdMap[t.wpCode]"
          form-type="d-form-table"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
