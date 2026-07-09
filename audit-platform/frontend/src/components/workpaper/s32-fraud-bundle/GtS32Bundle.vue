<script setup lang="ts">
/**
 * GtS32Bundle — S32 应对551文舞弊核查聚合组件
 *
 * 将 S32-1~13 共 13 个舞弊情形核查底稿聚合为单一 Bundle 组件，
 * 内部通过 el-tabs 可滚动分发渲染各舞弊情形核查底稿。
 *
 * 核心特征：
 * - 13 个舞弊情形 Tab，每个 Tab 渲染 GtAProgramConsole（核查程序表）
 * - S32-6/9/10 含导引表（IC-0）和披露格式参考（IC-X）子 sheet 切换
 * - 部分底稿含「提示」长文本折叠区块（details）
 * - sheetName 路由直接定位到指定 Tab
 * - readonly 模式透传所有子组件
 *
 * Spec: .kiro/specs/s32-fraud-response-bundle/
 * Tasks: 4.1, 4.2, 4.3, 4.4
 * Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 8.1, 8.2
 */
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { useS32BundleState } from './useS32BundleState'
import { S32_FRAUD_TABS, type S32TabDef } from './S32_TAB_CONFIG'
import GtAProgramConsole from '../GtAProgramConsole.vue'
import GtGridSheet from '../GtGridSheet.vue'

// ─── Props ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName?: string
  readonly?: boolean
}>(), {
  readonly: false,
})

// ─── Route & State ───
const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')

const {
  wpIdMap,
  visibleTabs,
  progressSummary,
  loading,
  loadWpIndex,
  refreshCompletion,
} = useS32BundleState({ projectId })

// ─── Active Tab ───
const activeTab = ref(props.sheetName || '')

// Initialize active tab once visibleTabs are resolved
watch(visibleTabs, (tabs) => {
  if (tabs.length > 0 && !tabs.some(t => t.id === activeTab.value)) {
    activeTab.value = tabs[0].id
  }
}, { immediate: true })

// ─── Task 4.4: sheetName 路由 (Req 4.1, 4.2, 4.3, 4.4) ───

// Watch props.sheetName changes
watch(() => props.sheetName, (newSheet) => {
  if (newSheet && visibleTabs.value.some(t => t.id === newSheet)) {
    activeTab.value = newSheet
  }
  // If sheetName not in visible tabs → keep current (Req 4.4)
})

// Watch route query ?sheet=S32-x
watch(() => route.query.sheet as string | undefined, (qs) => {
  if (qs && visibleTabs.value.some(t => t.id === qs)) {
    activeTab.value = qs
  }
})

// ─── Task 4.2: Sub-sheet switching for IC-0/IC-X (Req 3.3) ───
type SubSheetView = 'program' | 'guidance' | 'disclosure'

/** Tracks the active sub-sheet view per tab (only for tabs with IC-0/IC-X) */
const subSheetState = ref<Record<string, SubSheetView>>({})

function getSubSheetView(tabId: string): SubSheetView {
  return subSheetState.value[tabId] || 'program'
}

function setSubSheetView(tabId: string, view: SubSheetView) {
  subSheetState.value = { ...subSheetState.value, [tabId]: view }
}

/** Build sub-sheet options for a given tab */
function getSubSheetOptions(tab: S32TabDef): { label: string; value: SubSheetView }[] {
  const options: { label: string; value: SubSheetView }[] = [
    { label: '核查程序', value: 'program' },
  ]
  if (tab.guidanceSheet) {
    options.push({ label: '导引表', value: 'guidance' })
  }
  if (tab.disclosureSheet) {
    options.push({ label: '披露格式参考', value: 'disclosure' })
  }
  return options
}

/** Check if a tab has sub-sheets (guidance or disclosure) */
function hasSubSheets(tab: S32TabDef): boolean {
  return !!(tab.guidanceSheet || tab.disclosureSheet)
}

// ─── Task 4.3: Tips sheet data loading (Req 3.4) ───
const tipsCache = ref<Record<string, string>>({})
const tipsLoading = ref<Record<string, boolean>>({})

/**
 * Load tips content for a given tab's tip sheet.
 * Tips are loaded on demand when the tab is activated.
 */
async function loadTips(tab: S32TabDef): Promise<void> {
  if (!tab.tipSheet) return
  const wpId = wpIdMap.value[tab.wpCode]
  if (!wpId) return
  if (tipsCache.value[tab.wpCode] !== undefined) return // Already loaded

  tipsLoading.value = { ...tipsLoading.value, [tab.wpCode]: true }
  try {
    const res = await api.get<any>(
      `/api/workpapers/${wpId}/render-config`,
      { params: { sheet_name: tab.tipSheet }, _silent: true } as any,
    )
    // Extract tips text from render-config response
    const sheetData = res?.sheets?.find((s: any) => s.sheet_name === tab.tipSheet)
    const htmlData = sheetData?.html_data
    if (htmlData?.tip_text) {
      tipsCache.value = { ...tipsCache.value, [tab.wpCode]: htmlData.tip_text }
    } else if (htmlData?.cells) {
      // Fallback: concatenate cell values as tips text
      const cells = htmlData.cells as Record<string, { value?: string }>
      const text = Object.values(cells)
        .map(c => c.value || '')
        .filter(Boolean)
        .join('\n')
      tipsCache.value = { ...tipsCache.value, [tab.wpCode]: text }
    } else {
      tipsCache.value = { ...tipsCache.value, [tab.wpCode]: '' }
    }
  } catch {
    tipsCache.value = { ...tipsCache.value, [tab.wpCode]: '' }
  } finally {
    tipsLoading.value = { ...tipsLoading.value, [tab.wpCode]: false }
  }
}

// ─── Sub-sheet (guidance/disclosure) data loading ───
const subSheetDataCache = ref<Record<string, any>>({})

/**
 * Load sub-sheet html_data for guidance or disclosure sheets.
 * Key format: `${wpCode}:${sheetName}`
 */
async function loadSubSheetData(tab: S32TabDef, sheetName: string): Promise<any> {
  const cacheKey = `${tab.wpCode}:${sheetName}`
  if (subSheetDataCache.value[cacheKey]) return subSheetDataCache.value[cacheKey]

  const wpId = wpIdMap.value[tab.wpCode]
  if (!wpId) return null

  try {
    const res = await api.get<any>(
      `/api/workpapers/${wpId}/render-config`,
      { params: { sheet_name: sheetName }, _silent: true } as any,
    )
    const sheetData = res?.sheets?.find((s: any) => s.sheet_name === sheetName)
    const htmlData = sheetData?.html_data || null
    if (htmlData) {
      subSheetDataCache.value = { ...subSheetDataCache.value, [cacheKey]: htmlData }
    }
    return htmlData
  } catch {
    return null
  }
}

// ─── Guidance/Disclosure data reactive getters ───
const guidanceData = ref<Record<string, any>>({})
const disclosureData = ref<Record<string, any>>({})

async function ensureGuidanceData(tab: S32TabDef) {
  if (!tab.guidanceSheet) return
  if (guidanceData.value[tab.wpCode]) return
  const data = await loadSubSheetData(tab, tab.guidanceSheet)
  if (data) {
    guidanceData.value = { ...guidanceData.value, [tab.wpCode]: data }
  }
}

async function ensureDisclosureData(tab: S32TabDef) {
  if (!tab.disclosureSheet) return
  if (disclosureData.value[tab.wpCode]) return
  const data = await loadSubSheetData(tab, tab.disclosureSheet)
  if (data) {
    disclosureData.value = { ...disclosureData.value, [tab.wpCode]: data }
  }
}

// ─── Tab change → refresh completion (Req 7.4) + load tips ───
const prevTab = ref('')

watch(activeTab, (newTab, oldTab) => {
  // Refresh completion for previous tab when switching away
  if (oldTab && oldTab !== newTab) {
    prevTab.value = oldTab
    const prevTabDef = S32_FRAUD_TABS.find(t => t.id === oldTab)
    if (prevTabDef) {
      refreshCompletion(prevTabDef.wpCode)
    }
  }

  // Load tips for new tab if needed
  const currentTabDef = S32_FRAUD_TABS.find(t => t.id === newTab)
  if (currentTabDef?.tipSheet) {
    loadTips(currentTabDef)
  }

  // Load sub-sheet data on demand
  if (currentTabDef && hasSubSheets(currentTabDef)) {
    const view = getSubSheetView(newTab)
    if (view === 'guidance') ensureGuidanceData(currentTabDef)
    if (view === 'disclosure') ensureDisclosureData(currentTabDef)
  }
})

// Watch sub-sheet view changes → load data on demand
watch(subSheetState, (state) => {
  for (const [tabId, view] of Object.entries(state)) {
    const tab = S32_FRAUD_TABS.find(t => t.id === tabId)
    if (!tab) continue
    if (view === 'guidance') ensureGuidanceData(tab)
    if (view === 'disclosure') ensureDisclosureData(tab)
  }
}, { deep: true })

// ─── Lifecycle ───
onMounted(async () => {
  await loadWpIndex()

  // Resolve initial active tab from props or query
  const qs = route.query.sheet as string | undefined
  const targetSheet = props.sheetName || qs
  if (targetSheet && visibleTabs.value.some(t => t.id === targetSheet)) {
    activeTab.value = targetSheet
  } else if (visibleTabs.value.length > 0 && !visibleTabs.value.some(t => t.id === activeTab.value)) {
    activeTab.value = visibleTabs.value[0].id
  }

  // Load tips for initial tab
  const initialTab = S32_FRAUD_TABS.find(t => t.id === activeTab.value)
  if (initialTab?.tipSheet) {
    loadTips(initialTab)
  }
})
</script>

<template>
  <div class="gt-s32-bundle" v-loading="loading">
    <!-- 空状态：无任何 S32 底稿 (Req 5.4) -->
    <div v-if="!loading && visibleTabs.length === 0" class="gt-s32-bundle__empty">
      <el-result icon="info" title="本项目未启用 551 文舞弊核查程序">
        <template #sub-title>
          <span>项目底稿索引中未包含 S32 系列底稿，请在底稿管理中确认是否需要启用。</span>
        </template>
      </el-result>
    </div>

    <template v-else-if="visibleTabs.length > 0">
      <!-- 完成进度仪表盘 (Req 7.2) -->
      <div class="gt-s32-bundle__dashboard">
        <span class="dashboard-stat dashboard-stat--success">
          ✓ {{ progressSummary.completed }} 已完成
        </span>
        <span class="dashboard-stat dashboard-stat--warning">
          ◐ {{ progressSummary.inProgress }} 进行中
        </span>
        <span class="dashboard-stat dashboard-stat--info">
          ○ {{ progressSummary.notStarted }} 未开始
        </span>
        <span class="dashboard-stat dashboard-stat--total">
          共 {{ visibleTabs.length }} 项
        </span>
      </div>

      <!-- Task 4.1: el-tabs 可滚动 13 舞弊情形 (Req 3.1, 3.2) -->
      <el-tabs
        v-model="activeTab"
        type="card"
        class="gt-s32-bundle__tabs"
      >
        <el-tab-pane
          v-for="tab in visibleTabs"
          :key="tab.id"
          :label="tab.label"
          :name="tab.id"
          lazy
        >
          <!-- Task 4.3: 提示折叠区块 (Req 3.4) -->
          <details
            v-if="tab.tipSheet && tipsCache[tab.wpCode]"
            class="gt-s32-bundle__tips"
          >
            <summary class="gt-s32-bundle__tips-summary">提示</summary>
            <div class="gt-s32-bundle__tips-content" v-text="tipsCache[tab.wpCode]" />
          </details>

          <!-- Task 4.2: 子 sheet 切换 (Req 3.3) -->
          <div v-if="hasSubSheets(tab)" class="gt-s32-bundle__sub-switcher">
            <el-radio-group
              :model-value="getSubSheetView(tab.id)"
              size="small"
              @update:model-value="(v: SubSheetView) => setSubSheetView(tab.id, v)"
            >
              <el-radio-button
                v-for="opt in getSubSheetOptions(tab)"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </el-radio-button>
            </el-radio-group>
          </div>

          <!-- 核查程序（主 sheet）(Req 3.2) -->
          <GtAProgramConsole
            v-if="!hasSubSheets(tab) || getSubSheetView(tab.id) === 'program'"
            :wp-id="wpIdMap[tab.wpCode]"
            :sheet-name="tab.programSheet"
            :readonly="props.readonly"
          />

          <!-- 导引表 (IC-0) -->
          <GtGridSheet
            v-else-if="getSubSheetView(tab.id) === 'guidance' && guidanceData[tab.wpCode]"
            :wp-id="wpIdMap[tab.wpCode]"
            :sheet-name="tab.guidanceSheet"
            :html-data="guidanceData[tab.wpCode]"
            :readonly="true"
          />
          <div
            v-else-if="getSubSheetView(tab.id) === 'guidance'"
            v-loading="true"
            class="gt-s32-bundle__loading-placeholder"
          />

          <!-- 披露格式参考 (IC-X) -->
          <GtGridSheet
            v-else-if="getSubSheetView(tab.id) === 'disclosure' && disclosureData[tab.wpCode]"
            :wp-id="wpIdMap[tab.wpCode]"
            :sheet-name="tab.disclosureSheet"
            :html-data="disclosureData[tab.wpCode]"
            :readonly="true"
          />
          <div
            v-else-if="getSubSheetView(tab.id) === 'disclosure'"
            v-loading="true"
            class="gt-s32-bundle__loading-placeholder"
          />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<style scoped>
.gt-s32-bundle {
  padding: var(--gt-space-4, 16px);
}

/* ─── Dashboard ─── */
.gt-s32-bundle__dashboard {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--gt-color-bg-elevated, #fafafa);
  border-radius: var(--gt-radius-sm, 4px);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  font-size: 13px;
}

.dashboard-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.dashboard-stat--success { color: var(--gt-color-success, #67c23a); }
.dashboard-stat--warning { color: var(--gt-color-warning, #e6a23c); }
.dashboard-stat--info { color: var(--gt-color-text-tertiary, #909399); }
.dashboard-stat--total {
  margin-left: auto;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 500;
}

/* ─── Tabs ─── */
.gt-s32-bundle__tabs :deep(.el-tabs__nav-scroll) {
  overflow-x: auto;
}
.gt-s32-bundle__tabs :deep(.el-tabs__nav) {
  flex-wrap: nowrap;
}

/* ─── Tips折叠 (Req 3.4) ─── */
.gt-s32-bundle__tips {
  margin-bottom: 12px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: var(--gt-radius-sm, 4px);
  background: #fffbe6;
}

.gt-s32-bundle__tips-summary {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--gt-color-warning, #e6a23c);
  cursor: pointer;
  user-select: none;
}

.gt-s32-bundle__tips-content {
  padding: 8px 12px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--gt-color-text-secondary, #606266);
  white-space: pre-wrap;
  word-break: break-all;
}

/* ─── Sub-sheet switcher (Req 3.3) ─── */
.gt-s32-bundle__sub-switcher {
  margin-bottom: 12px;
}

/* ─── Loading placeholder ─── */
.gt-s32-bundle__loading-placeholder {
  min-height: 200px;
}

/* ─── Empty state ─── */
.gt-s32-bundle__empty {
  padding: 60px 20px;
  text-align: center;
}
</style>
