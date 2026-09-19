<script setup lang="ts">
/**
 * GtB51Bundle — B51 舞弊风险识别聚合组件
 *
 * 将 B51 舞弊风险主表 + B51-3 对货币资金保持警觉 + B51-5 收入确认方面舞弊风险
 * 聚合为 Bundle，内部通过 el-tabs 分发渲染各子底稿。
 *
 * 注：B51 主表本身就是 d-form-table，不是程序表。
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'

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
  { id: 'main', label: '舞弊风险主表', wpCode: null },
  { id: 'B51-3', label: 'B51-3 对货币资金保持警觉', wpCode: 'B51-3' },
  { id: 'B51-5', label: 'B51-5 收入确认方面舞弊风险', wpCode: 'B51-5' },
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
    if (item.wp_code?.startsWith('B51-')) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

// ─── 仅显示主表 tab + wp_index 中存在的子底稿 Tab ───
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
  <div class="gt-b51-bundle" v-loading="loading">
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="t in visibleTabs"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <GtDForm
          v-if="t.id === 'main'"
          :wp-id="wpId"
          form-type="d-form-table"
          :readonly="readonly"
        />
        <GtDForm
          v-else-if="t.wpCode"
          :wp-id="wpIdMap[t.wpCode]"
          form-type="d-form-table"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
