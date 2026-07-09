<script setup lang="ts">
/**
 * GtS35Bundle — S35 再融资审核特项底稿聚合组件
 *
 * 将 S35-1~S35-5 共 5 个再融资核查底稿聚合为单一 Bundle，
 * 内部通过一行 el-tabs 切换各底稿。
 *
 * 核心特征：
 * - 5 Tab 一行页签（关联交易/财务性投资核查/现金分红核查/商誉减值/募集资金涉及收购核查）
 * - 含子表的 Tab（S35-1/2/3）内部以 el-radio-group 切换「核查程序表/明细核查表」
 * - 无子表的 Tab（S35-4/5）直接渲染 GtAProgramConsole
 * - sheetName 路由直接定位到指定 Tab（Property 4）
 * - readonly 模式透传所有子组件（Property 7）
 *
 * 🔴 wpIdMap 必须用 item.wp_id 不能用 item.id
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/
 * Task: 4.1, 4.2
 * Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3
 */
import { ref, computed, watch, onMounted, provide } from 'vue'
import { useRoute } from 'vue-router'
import { CircleCheckFilled, Loading, RemoveFilled } from '@element-plus/icons-vue'
import { useS35BundleState, S35_TAB_DEFS, type TabDef } from '../composables/useS35BundleState'
import { useS35CrossRef } from './useS35CrossRef'
import GtAProgramConsole from '../GtAProgramConsole.vue'
import GtS35DetailTable from './GtS35DetailTable.vue'

type S35SheetCode = 'S35-1-1' | 'S35-2-1' | 'S35-3-1'

// ─── Props (Req 1.3) ───
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
  completionMap,
  progressSummary,
  loading,
  loadWpIndex,
  refreshCompletion,
} = useS35BundleState({ projectId })

// ─── Active Tab (Property 4: sheetName 路由正确激活 Tab) ───
const activeTab = ref(props.sheetName || (S35_TAB_DEFS[0]?.id ?? 'S35-1'))

// ─── Cross-ref 跨底稿引用导航 (Req 7.1, 7.2, 7.3, 7.4) ───
const { handleChipClick: handleCrossRefClick } = useS35CrossRef({
  visibleTabs,
  activeTab,
  projectId,
})

// Provide navigate function for child components (GtAProgramConsole chip delegation)
provide('s35-bundle-navigate', (wpCode: string) => {
  handleCrossRefClick(wpCode)
})

// ─── 子 sheet 切换状态：每个含子表 Tab 维护独立的当前视图 ───
// 'program' = 核查程序表 | 'detail' = 明细核查表
const subSheetView = ref<Record<string, 'program' | 'detail'>>({
  'S35-1': 'program',
  'S35-2': 'program',
  'S35-3': 'program',
})

// Watch visibleTabs for initial tab resolution
watch(visibleTabs, (tabs) => {
  if (tabs.length > 0 && !tabs.some(t => t.id === activeTab.value)) {
    activeTab.value = tabs[0].id
  }
}, { immediate: true })

// Watch props.sheetName changes (Req 5.3)
watch(() => props.sheetName, (newSheet) => {
  if (newSheet && visibleTabs.value.some(t => t.id === newSheet)) {
    activeTab.value = newSheet
  }
  // sheetName 不在可见 Tab 列表 → 保持当前 Tab (Req 5.4)
})

// Watch route query ?sheet=S35-x (Req 5.2)
watch(() => route.query.sheet as string | undefined, (qs) => {
  if (qs && visibleTabs.value.some(t => t.id === qs)) {
    activeTab.value = qs
  }
})

// ─── Tab change → refresh completion ───
watch(activeTab, (_newTab, oldTab) => {
  if (oldTab && oldTab !== _newTab) {
    const prevTabDef = S35_TAB_DEFS.find(t => t.id === oldTab)
    if (prevTabDef?.wpCode) {
      refreshCompletion(prevTabDef.wpCode)
    }
  }
})

// ─── 仪表盘计算 (Req 8.2) ───
const progressTotal = computed(() =>
  progressSummary.value.completed + progressSummary.value.inProgress + progressSummary.value.notStarted,
)

function barPercent(key: 'completed' | 'inProgress' | 'notStarted'): string {
  const total = progressTotal.value
  if (total <= 0) return '0%'
  return `${(progressSummary.value[key] / total) * 100}%`
}

// ─── 判断 Tab 是否含子表 ───
function hasSubSheets(tab: TabDef): boolean {
  return !!tab.subSheets && tab.subSheets.length > 0
}

// ─── 获取子表显示名 ───
function getSubSheetLabel(tab: TabDef): string {
  // 根据底稿类型返回中文明细表名
  const labelMap: Record<string, string> = {
    'S35-1': '关联交易核查表',
    'S35-2': '财务性投资核查表',
    'S35-3': '现金分红核查表',
  }
  return labelMap[tab.id] || '明细核查表'
}

// ─── Lifecycle ───
onMounted(async () => {
  await loadWpIndex()

  // Resolve initial active tab from props or query (Req 5.1, 5.2)
  const qs = route.query.sheet as string | undefined
  const targetSheet = props.sheetName || qs
  if (targetSheet && visibleTabs.value.some(t => t.id === targetSheet)) {
    activeTab.value = targetSheet
  } else if (!visibleTabs.value.some(t => t.id === activeTab.value)) {
    activeTab.value = visibleTabs.value[0]?.id || 'S35-1'
  }
})
</script>

<template>
  <div class="gt-s35-bundle" v-loading="loading">
    <!-- 空状态：无任何 S35 底稿 (Req 6.4) -->
    <div v-if="!loading && visibleTabs.length === 0" class="gt-s35-bundle__empty">
      <el-result icon="info" title="本项目未启用再融资审核专项底稿">
        <template #sub-title>
          <span>项目底稿索引中未包含 S35 系列底稿，请在底稿管理中确认是否需要启用。</span>
        </template>
      </el-result>
    </div>

    <template v-else>
      <!-- 完成进度仪表盘 (Req 8.1, 8.2, 8.3) -->
      <div class="gt-s35-bundle__dashboard" data-testid="s35-dashboard">
        <div class="dashboard-stats">
          <span class="dashboard-stat dashboard-stat--success">
            <el-icon :size="14"><CircleCheckFilled /></el-icon>
            <strong>{{ progressSummary.completed }}</strong> 已完成
          </span>
          <span class="dashboard-stat dashboard-stat--warning">
            <el-icon :size="14"><Loading /></el-icon>
            <strong>{{ progressSummary.inProgress }}</strong> 进行中
          </span>
          <span class="dashboard-stat dashboard-stat--info">
            <el-icon :size="14"><RemoveFilled /></el-icon>
            <strong>{{ progressSummary.notStarted }}</strong> 未开始
          </span>
          <span class="dashboard-stat dashboard-stat--total">
            共 {{ progressTotal }} 项
          </span>
        </div>
        <!-- 三色进度条 -->
        <div class="dashboard-bar" data-testid="s35-dashboard-bar">
          <div
            class="dashboard-bar__segment dashboard-bar__segment--success"
            :style="{ width: barPercent('completed') }"
            :title="`已完成 ${progressSummary.completed} 项`"
          />
          <div
            class="dashboard-bar__segment dashboard-bar__segment--warning"
            :style="{ width: barPercent('inProgress') }"
            :title="`进行中 ${progressSummary.inProgress} 项`"
          />
          <div
            class="dashboard-bar__segment dashboard-bar__segment--info"
            :style="{ width: barPercent('notStarted') }"
            :title="`未开始 ${progressSummary.notStarted} 项`"
          />
        </div>
      </div>

      <!-- el-tabs 一行页签 (Req 3.1) -->
      <el-tabs
        v-model="activeTab"
        type="card"
        class="gt-s35-bundle__tabs"
      >
        <el-tab-pane
          v-for="tab in visibleTabs"
          :key="tab.id"
          :label="tab.label"
          :name="tab.id"
          lazy
        >
          <!-- ═══ 含子表的 Tab：子 sheet 切换 (Req 3.3) ═══ -->
          <template v-if="hasSubSheets(tab)">
            <!-- 子 sheet 切换：核查程序表 / 明细核查表 -->
            <div class="gt-s35-bundle__sub-switch">
              <el-radio-group
                v-model="subSheetView[tab.id]"
                size="small"
              >
                <el-radio-button value="program">核查程序表</el-radio-button>
                <el-radio-button value="detail">{{ getSubSheetLabel(tab) }}</el-radio-button>
              </el-radio-group>
            </div>

            <!-- 核查程序表视图 (Req 3.2) -->
            <GtAProgramConsole
              v-if="subSheetView[tab.id] === 'program'"
              :wp-id="wpIdMap[tab.wpCode]"
              :sheet-name="`${tab.wpCode}程序表`"
              :readonly="props.readonly"
              @jump-to-workpaper="handleCrossRefClick"
            />

            <!-- 明细核查表视图 (Task 4.2) -->
            <GtS35DetailTable
              v-else
              :wp-id="wpIdMap[tab.subSheets![0]] || wpIdMap[tab.wpCode]"
              :sheet-code="(tab.subSheets![0] as S35SheetCode)"
              :readonly="props.readonly"
              @data-changed="refreshCompletion(tab.wpCode)"
            />
          </template>

          <!-- ═══ 无子表的 Tab：直接渲染 GtAProgramConsole (Req 3.2) ═══ -->
          <template v-else>
            <GtAProgramConsole
              v-if="wpIdMap[tab.wpCode]"
              :wp-id="wpIdMap[tab.wpCode]"
              :sheet-name="`${tab.wpCode}程序表`"
              :readonly="props.readonly"
              @jump-to-workpaper="handleCrossRefClick"
            />
          </template>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<style scoped>
.gt-s35-bundle {
  padding: var(--gt-space-4, 16px);
}

/* ─── Dashboard (Req 8.2) ─── */
.gt-s35-bundle__dashboard {
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

/* ─── Tabs ─── */
.gt-s35-bundle__tabs :deep(.el-tabs__nav-scroll) {
  overflow-x: auto;
}
.gt-s35-bundle__tabs :deep(.el-tabs__nav) {
  flex-wrap: nowrap;
}
.gt-s35-bundle__tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

/* ─── Sub-sheet 切换 (Req 3.3) ─── */
.gt-s35-bundle__sub-switch {
  margin-bottom: 12px;
  padding: 8px 0;
}

/* ─── Empty state ─── */
.gt-s35-bundle__empty {
  padding: 60px 20px;
  text-align: center;
}
</style>
