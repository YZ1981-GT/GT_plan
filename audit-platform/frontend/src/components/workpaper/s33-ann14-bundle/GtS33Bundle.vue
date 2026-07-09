<script setup lang="ts">
/**
 * GtS33Bundle — S33 应对14号公告提示风险核查程序聚合组件
 *
 * 将 S33-1~S33-9 共 9 个核查底稿聚合为单一 Bundle 组件，
 * 内部通过 el-tabs 一行可滚动页签分发渲染各核查底稿。
 *
 * 核心特征：
 * - 9 个核查底稿 Tab，每个 Tab 渲染 GtAProgramConsole（核查程序表）
 * - S33-4 含隐藏程序表变体（默认可见版 + 切换完整版入口）
 * - 部分底稿含「提示」长文本折叠区块（details）
 * - sheetName 路由直接定位到指定 Tab
 * - readonly 模式透传所有子组件
 *
 * Spec: .kiro/specs/s33-announcement14-bundle/
 * Tasks: 4.1, 4.2, 4.3, 4.4
 * Requirements: 3.1, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 8.1, 8.2
 */
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { useS33BundleState } from './useS33BundleState'
import { S33_ANN14_TABS, type S33TabDef } from './S33_TAB_CONFIG'
import GtAProgramConsole from '../GtAProgramConsole.vue'

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
} = useS33BundleState({ projectId })

// ─── Active Tab ───
const activeTab = ref(props.sheetName || '')

// ─── Task 4.2: 隐藏程序表变体切换 (Req 3.4) ───
// Track whether each tab shows the hidden variant (full version).
// Default: false (show visible/compact version)
const showHiddenVariant: Record<string, boolean> = reactive({})

/**
 * Returns the effective program sheet name for a given tab.
 * If the tab has a hidden variant and the user toggled to full version,
 * returns hiddenVariantSheet; otherwise returns programSheet.
 */
function getResolvedSheetName(tab: S33TabDef): string {
  if (tab.hiddenVariantSheet && showHiddenVariant[tab.wpCode]) {
    return tab.hiddenVariantSheet
  }
  return tab.programSheet
}

/** Toggle between visible (compact) and hidden (full) variant for a tab */
function toggleVariant(wpCode: string): void {
  showHiddenVariant[wpCode] = !showHiddenVariant[wpCode]
}

// ─── Task 4.3: 提示长文本 details 折叠区块 (Req 3.3) ───
const tipsCache = ref<Record<string, string>>({})
const tipsLoading = ref<Record<string, boolean>>({})

/**
 * Load tips content for a given tab's tip sheet.
 * Tips are loaded on demand when the tab is activated.
 */
async function loadTips(tab: S33TabDef): Promise<void> {
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

// Load tips when active tab changes to a tab with tipSheet
watch(activeTab, (newTab) => {
  const tabDef = S33_ANN14_TABS.find(t => t.id === newTab)
  if (tabDef?.tipSheet) {
    loadTips(tabDef)
  }
})

// Initialize active tab once visibleTabs are resolved
watch(visibleTabs, (tabs) => {
  if (tabs.length > 0 && !tabs.some(t => t.id === activeTab.value)) {
    activeTab.value = tabs[0].id
  }
}, { immediate: true })

// ─── sheetName 路由 (Task 4.4: Req 4.1, 4.2, 4.3, 4.4) ───
watch(() => props.sheetName, (newSheet) => {
  if (newSheet && visibleTabs.value.some(t => t.id === newSheet)) {
    activeTab.value = newSheet
  }
})

watch(() => route.query.sheet as string | undefined, (qs) => {
  if (qs && visibleTabs.value.some(t => t.id === qs)) {
    activeTab.value = qs
  }
})

// ─── Tab change → refresh completion ───
watch(activeTab, (_newTab, oldTab) => {
  if (oldTab && oldTab !== _newTab) {
    const prevTabDef = S33_ANN14_TABS.find(t => t.id === oldTab)
    if (prevTabDef) {
      refreshCompletion(prevTabDef.wpCode)
    }
  }
})

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

  // Load tips for the initially active tab (Task 4.3)
  const initialTab = S33_ANN14_TABS.find(t => t.id === activeTab.value)
  if (initialTab?.tipSheet) {
    loadTips(initialTab)
  }
})
</script>

<template>
  <div class="gt-s33-bundle" v-loading="loading">
    <!-- 空状态：无任何 S33 底稿 (Req 5.4) -->
    <div v-if="!loading && visibleTabs.length === 0" class="gt-s33-bundle__empty">
      <el-result icon="info" title="本项目未启用14号公告核查程序">
        <template #sub-title>
          <span>项目底稿索引中未包含 S33 系列底稿，请在底稿管理中确认是否需要启用。</span>
        </template>
      </el-result>
    </div>

    <template v-else-if="visibleTabs.length > 0">
      <!-- 完成进度仪表盘 (Req 7.2, 7.3, 7.4) -->
      <div class="gt-s33-bundle__dashboard" data-testid="s33-dashboard">
        <div class="dashboard-stats">
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
        <!-- 三色进度条：绿(已完成) + 琥珀(进行中) + 灰(未开始) -->
        <div class="dashboard-bar" data-testid="s33-dashboard-bar">
          <div
            class="dashboard-bar__segment dashboard-bar__segment--success"
            :style="{ width: visibleTabs.length ? `${(progressSummary.completed / visibleTabs.length) * 100}%` : '0%' }"
          />
          <div
            class="dashboard-bar__segment dashboard-bar__segment--warning"
            :style="{ width: visibleTabs.length ? `${(progressSummary.inProgress / visibleTabs.length) * 100}%` : '0%' }"
          />
          <div
            class="dashboard-bar__segment dashboard-bar__segment--info"
            :style="{ width: visibleTabs.length ? `${(progressSummary.notStarted / visibleTabs.length) * 100}%` : '0%' }"
          />
        </div>
      </div>

      <!-- Task 4.1: el-tabs 可滚动 9 核查底稿 (Req 3.1) -->
      <el-tabs
        v-model="activeTab"
        type="card"
        class="gt-s33-bundle__tabs"
      >
        <el-tab-pane
          v-for="tab in visibleTabs"
          :key="tab.id"
          :label="tab.label"
          :name="tab.id"
          lazy
        >
          <!-- Task 4.2: 隐藏程序表变体切换入口 (Req 3.4) -->
          <div
            v-if="tab.hiddenVariantSheet"
            class="gt-s33-bundle__variant-toggle"
          >
            <el-switch
              :model-value="!!showHiddenVariant[tab.wpCode]"
              size="small"
              inline-prompt
              active-text="完整版"
              inactive-text="精简版"
              @change="toggleVariant(tab.wpCode)"
            />
            <span class="variant-toggle__label">
              {{ showHiddenVariant[tab.wpCode] ? '当前：完整版程序表' : '当前：精简版程序表' }}
            </span>
          </div>

          <!-- Task 4.3: 提示长文本 details 折叠区块 (Req 3.3) -->
          <details
            v-if="tab.tipSheet && tipsCache[tab.wpCode]"
            class="gt-s33-bundle__tips"
          >
            <summary class="gt-s33-bundle__tips-summary">核查提示</summary>
            <div class="gt-s33-bundle__tips-content" v-text="tipsCache[tab.wpCode]" />
          </details>
          <div
            v-else-if="tab.tipSheet && tipsLoading[tab.wpCode]"
            v-loading="true"
            class="gt-s33-bundle__tips-loading"
          />

          <!-- GtAProgramConsole: 核查程序表渲染 (Req 4.1, 8.1, 8.2) -->
          <GtAProgramConsole
            :wp-id="wpIdMap[tab.wpCode]"
            :sheet-name="getResolvedSheetName(tab)"
            :readonly="props.readonly"
          />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<style scoped>
.gt-s33-bundle {
  padding: var(--gt-space-4, 16px);
}

/* ─── Dashboard (Req 7.2, 7.3, 7.4) ─── */
.gt-s33-bundle__dashboard {
  padding: 10px 16px;
  margin-bottom: 12px;
  background: var(--gt-color-bg-elevated, #fafafa);
  border-radius: var(--gt-radius-sm, 4px);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  font-size: 13px;
}

.dashboard-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
}

.dashboard-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.dashboard-stat--success { color: var(--gt-color-success, #67c23a); font-weight: 500; }
.dashboard-stat--warning { color: var(--gt-color-warning, #e6a23c); font-weight: 500; }
.dashboard-stat--info { color: var(--gt-color-text-tertiary, #909399); }
.dashboard-stat--total {
  margin-left: auto;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 500;
}

/* 三色进度条 */
.dashboard-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--gt-color-border-light, #ebeef5);
}
.dashboard-bar__segment { transition: width 0.3s ease; }
.dashboard-bar__segment--success { background: var(--gt-color-success, #67c23a); }
.dashboard-bar__segment--warning { background: var(--gt-color-warning, #e6a23c); }
.dashboard-bar__segment--info { background: var(--gt-color-text-tertiary, #c0c4cc); }

/* ─── Tabs 可滚动 (Req 3.1: 一行可滚动页签展示 9 个核查底稿 Tab) ─── */
.gt-s33-bundle__tabs :deep(.el-tabs__nav-scroll) {
  overflow-x: auto;
}
.gt-s33-bundle__tabs :deep(.el-tabs__nav) {
  flex-wrap: nowrap;
}
.gt-s33-bundle__tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

/* ─── Task 4.2: 隐藏程序表变体切换 (Req 3.4) ─── */
.gt-s33-bundle__variant-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--gt-color-bg-elevated, #fafafa);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: var(--gt-radius-sm, 4px);
}

.variant-toggle__label {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}

/* ─── Task 4.3: 提示长文本 details 折叠 (Req 3.3) ─── */
.gt-s33-bundle__tips {
  margin-bottom: 12px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-left: 3px solid var(--gt-color-warning, #e6a23c);
  border-radius: var(--gt-radius-sm, 4px);
  background: #fffbe6;
}

.gt-s33-bundle__tips-summary {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--gt-color-warning, #e6a23c);
  cursor: pointer;
  user-select: none;
}

.gt-s33-bundle__tips-content {
  padding: 8px 12px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--gt-color-text-secondary, #606266);
  white-space: pre-wrap;
  word-break: break-all;
}

.gt-s33-bundle__tips-loading {
  height: 40px;
  margin-bottom: 12px;
}

/* ─── Empty state ─── */
.gt-s33-bundle__empty {
  padding: 60px 20px;
  text-align: center;
}
</style>
