<script setup lang="ts">
/**
 * GtB13Bundle — B13 初步分析性程序聚合组件
 *
 * 将 B13 程序表 + B13-2 初步分析性复核 聚合为 Bundle，
 * 内部通过 el-tabs 分发渲染各子底稿。
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import GtAProgramConsole from './GtAProgramConsole.vue'

const GtAnalyticalReview = defineAsyncComponent(() => import('./GtAnalyticalReview.vue'))

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
  { id: 'B13-2', label: 'B13-2 初步分析性复核', wpCode: 'B13-2' },
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
    if (item.wp_code?.startsWith('B13-')) {
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
  <div class="gt-b13-bundle" v-loading="loading">
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
        <GtAnalyticalReview
          v-else-if="t.wpCode === 'B13-2'"
          :wp-id="wpIdMap[t.wpCode]"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
