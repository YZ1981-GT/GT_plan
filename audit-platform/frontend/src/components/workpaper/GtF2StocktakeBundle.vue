<script setup lang="ts">
/**
 * GtF2StocktakeBundle — F2 存货监盘统一入口 (7 Tab)
 *
 * Tab 结构：程序表 F2-21A | 盘点问卷 F2-21 | 监盘计划 F2-22 |
 *           监盘小结 F2-23 | 账面核对 F2-24 | 抽盘汇总 F2-25 | 倒轧表 F2-26
 *
 * 子底稿使用 GtOnlyOfficeSheet 在线编辑（复杂 Excel 表格最适合原样编辑）。
 * 模式参照：GtB2Bundle
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import GtAProgramConsole from './GtAProgramConsole.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId?: string
  sheetName?: string
  readonly?: boolean
}>()

const route = useRoute()
const active = ref('program')
const wpIndex = ref<WpIndexItem[]>([])
const loading = ref(false)

const TABS = [
  { id: 'program', label: '监盘程序表', wpCode: null },
  { id: 'F2-21', label: '盘点计划问卷', wpCode: 'F2-21' },
  { id: 'F2-22', label: '监盘计划', wpCode: 'F2-22' },
  { id: 'F2-23', label: '监盘小结', wpCode: 'F2-23' },
  { id: 'F2-24', label: '账面核对', wpCode: 'F2-24' },
  { id: 'F2-25', label: '抽盘汇总', wpCode: 'F2-25' },
  { id: 'F2-26', label: '倒轧表', wpCode: 'F2-26' },
]

const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

const wpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of wpIndex.value) {
    if (item.wp_code && /^F2-2[1-6]$/.test(item.wp_code)) {
      map[item.wp_code] = (item as any).wp_id || item.id
    }
  }
  return map
})

const visibleTabs = computed(() =>
  TABS.filter(t => t.wpCode === null || !!wpIdMap.value[t.wpCode!])
)

// sheetName 路由
watch(() => props.sheetName, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) active.value = v
})
watch(() => route.query.sheet as string | undefined, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) active.value = v
})

onMounted(async () => {
  loading.value = true
  try {
    if (projectId.value) {
      wpIndex.value = await getWpIndex(projectId.value)
    }
  } catch {
    wpIndex.value = []
  } finally {
    loading.value = false
  }
  const sheet = props.sheetName || (route.query.sheet as string)
  if (sheet && visibleTabs.value.some(t => t.id === sheet)) {
    active.value = sheet
  }
})
</script>

<template>
  <div class="f2-stocktake-bundle" v-loading="loading">
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="tab in visibleTabs"
        :key="tab.id"
        :label="tab.label"
        :name="tab.id"
        lazy
      >
        <!-- 程序表 -->
        <GtAProgramConsole
          v-if="tab.wpCode === null"
          :wp-id="wpId"
          :embedded="true"
          :readonly="readonly"
        />
        <!-- 子底稿通过 GtOnlyOfficeSheet 在线编辑 -->
        <GtOnlyOfficeSheet
          v-else
          :wp-id="wpIdMap[tab.wpCode!]"
          :sheet-name="tab.wpCode!"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.f2-stocktake-bundle {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.f2-stocktake-bundle :deep(.el-tabs) {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.f2-stocktake-bundle :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
}
</style>
