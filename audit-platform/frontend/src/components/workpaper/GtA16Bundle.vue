<script setup lang="ts">
/**
 * GtA16Bundle — A16 管理层声明书聚合组件
 *
 * 将 A16 的 7 个 word-template 子底稿聚合为单一 Bundle 组件，
 * 内部通过 el-tabs 分发渲染各子底稿的 WorkpaperWordEditor。
 *
 * 模式参考：GtA11Bundle（极简模式，无 composable / 无联动 / 无完成追踪）
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'

const WorkpaperWordEditor = defineAsyncComponent(() => import('./WorkpaperWordEditor.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
}>()

// ─── Tab 配置（静态） ───
const TABS = [
  { id: 'A16-1', label: '会计审核版', wpCode: 'A16-1' },
  { id: 'A16-2', label: '整合审核版', wpCode: 'A16-2' },
  { id: 'A16-3', label: 'IPO补贴', wpCode: 'A16-3' },
  { id: 'A16-4', label: 'IPO券商审阅', wpCode: 'A16-4' },
  { id: 'A16-5', label: '新三板申报', wpCode: 'A16-5' },
  { id: 'A16-6', label: '合营协议', wpCode: 'A16-6' },
  { id: 'A16-7', label: '关联交易合规说明', wpCode: 'A16-7' },
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
    if (item.wp_code?.startsWith('A16-')) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

// ─── 仅显示 wp_index 中存在的 Tab ───
const visibleTabs = computed(() =>
  TABS.filter(t => !!wpIdMap.value[t.wpCode])
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

  // 初始化 active tab：props.sheetName > route.query.sheet > 第一个可见 Tab
  const sheet = props.sheetName || (route.query.sheet as string)
  if (sheet && visibleTabs.value.some(t => t.id === sheet)) {
    active.value = sheet
  } else {
    active.value = visibleTabs.value[0]?.id || ''
  }
})
</script>

<template>
  <div class="gt-a16-bundle" v-loading="loading">
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="t in visibleTabs"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <WorkpaperWordEditor
          :wp-id="wpIdMap[t.wpCode]"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
