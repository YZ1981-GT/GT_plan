<script setup lang="ts">
/**
 * GtA17Bundle — A17 审计总结聚合组件
 *
 * 将 A17 程序表及其 12 个子底稿聚合为单一 Bundle 组件，
 * 内部通过 el-tabs 分发渲染各子底稿。
 *
 * 联动逻辑：
 * - A17-5 完成 → 解锁 A17-6/A17-7
 * - A17-1 + A17-5 + A17-7 全完成 → 允许签发
 * - KAM 引用传入 GtA17Summary
 *
 * 模式参考：GtA11Bundle / GtA15Bundle
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import {
  useA17BundleState,
  statusToDisplay,
  type KamReference,
} from './composables/useA17BundleState'
import GtAProgramConsole from './GtAProgramConsole.vue'

// Lazy-loaded sub-components
const GtA17Summary = defineAsyncComponent(() => import('./GtA17Summary.vue'))
const GtA171AuditSummary = defineAsyncComponent(() => import('./GtA171AuditSummary.vue'))
const WorkpaperWordEditor = defineAsyncComponent(() => import('./WorkpaperWordEditor.vue'))
const GtEmbeddedChecklist = defineAsyncComponent(() => import('./GtEmbeddedChecklist.vue'))
const IndependenceSigning = defineAsyncComponent(() => import('./IndependenceSigning.vue'))
const GtA1721Kam = defineAsyncComponent(() => import('./GtA1721Kam.vue'))
const GtA173ConsultationRecord = defineAsyncComponent(() => import('./GtA173ConsultationRecord.vue'))
const GtA1731ConsultationExecution = defineAsyncComponent(() => import('./GtA1731ConsultationExecution.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
}>()

// ─── Tab Configuration (same as A17_BUNDLE_TABS exported from composable) ───
interface TabDef {
  id: string
  label: string
  kind: 'program' | 'a17-summary' | 'word' | 'checklist' | 'independence' | 'kam' | 'consultation' | 'consultation-exec'
  wpCode?: string
  tracked?: boolean
}

const TABS: TabDef[] = [
  { id: 'program', label: '审计程序', kind: 'program' },
  { id: 'A17-1', label: '重大事项概要汇总', kind: 'a17-summary', wpCode: 'A17-1', tracked: true },
  { id: 'A17-2-1', label: '关键审计事项', kind: 'kam', wpCode: 'A17-2-1' },
  { id: 'A17-3', label: '业务咨询记录', kind: 'consultation', wpCode: 'A17-3' },
  { id: 'A17-3-1', label: '业务咨询执行记录', kind: 'consultation-exec', wpCode: 'A17-3-1' },
  { id: 'A17-4', label: '重大专业分歧事项记录', kind: 'word', wpCode: 'A17-4' },
  { id: 'A17-5', label: '审计工作完成核对表', kind: 'checklist', wpCode: 'A17-5', tracked: true },
  { id: 'A17-6', label: '总结会会议纪要', kind: 'word', wpCode: 'A17-6', tracked: true },
  { id: 'A17-7', label: '独立性声明书', kind: 'independence', wpCode: 'A17-7', tracked: true },
]

// ─── State ───
const route = useRoute()
const active = ref(props.sheetName || 'program')
const wpIndex = ref<WpIndexItem[]>([])
const loading = ref(false)
const prevTab = ref(active.value)

// ─── wp_id resolution ───
const wpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of wpIndex.value) {
    if (item.wp_code?.startsWith('A17-')) {
      // 必须用 wp_id (working_paper.id)，不能用 id (wp_index.id)
      // checklist_responses FK 引用 working_paper(id)
      const wpId = item.wp_id || ''
      if (wpId) map[item.wp_code] = wpId
    }
  }
  return map
})

// ─── A17-5 applicability filter ───
const applicableA17_5 = computed(() =>
  ['A17-5-1', 'A17-5-2', 'A17-5-3', 'A17-5-4', 'A17-5-5']
    .filter(code => wpIdMap.value[code]),
)

// ─── Visible tabs ───
const visibleTabs = computed(() =>
  TABS.filter(tab => {
    if (tab.kind === 'program') return true
    if (tab.id === 'A17-5') {
      // A17-5 tab only visible if any A17-5-x exists
      return applicableA17_5.value.length > 0
    }
    if (tab.wpCode) {
      // Other tabs visible only if wp_id exists
      return !!wpIdMap.value[tab.wpCode]
    }
    return true
  }),
)

// ─── useA17BundleState composable integration ───
const projectIdRef = computed(() => props.projectId || '')

const bundleState = useA17BundleState({
  projectId: projectIdRef,
  wpIdMap,
})

const {
  completionMap,
  subTabCompletions,
  isA17_6Locked,
  isA17_7Locked,
  a17_6LockReason,
  a17_7LockReason,
  signOffPreconditions,
  signOffReady,
  kamReferences,
  refreshCompletionStatus,
  loadKamReferences,
} = bundleState

// ─── Dashboard items ───
interface DashboardItem {
  tabId: string
  label: string
  status: string
  icon: string
  color: string
}

const dashboardItems = computed<DashboardItem[]>(() =>
  subTabCompletions.value.map(item => ({
    tabId: item.tabId,
    label: item.label,
    status: item.status,
    ...statusToDisplay(item.status),
  })),
)

// ─── sheetName routing ───
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

// Tab switch → refresh completion when leaving A17-5
watch(active, (newTab, oldTab) => {
  prevTab.value = oldTab
  if (oldTab === 'A17-5') {
    refreshCompletionStatus()
  }
})

// ─── Helper: get effective wp_id for a tab ───
function getTabWpId(tab: TabDef): string {
  if (tab.id === 'A17-5') {
    // Use first applicable A17-5-x wp_id
    return applicableA17_5.value.length > 0
      ? wpIdMap.value[applicableA17_5.value[0]] || ''
      : ''
  }
  return tab.wpCode ? (wpIdMap.value[tab.wpCode] || '') : props.wpId
}

// ─── Effective readonly for locked tabs ───
function isTabReadonly(tab: TabDef): boolean {
  if (props.readonly) return true
  if (tab.id === 'A17-6' && isA17_6Locked.value) return true
  if (tab.id === 'A17-7' && isA17_7Locked.value) return true
  return false
}

// ─── Lock reason for a tab ───
function getTabLockReason(tab: TabDef): string {
  if (tab.id === 'A17-6') return a17_6LockReason.value
  if (tab.id === 'A17-7') return a17_7LockReason.value
  return ''
}

// ─── Sign-off attempt handler ───
function handleSignOffAttempt() {
  if (signOffReady.value) return // Allow normal flow
  const unmet = signOffPreconditions.value.filter(p => !p.satisfied)
  const items = unmet.map(p => `• ${p.label}`).join('\n')
  ElMessage.warning({
    message: `签发前置条件未满足：\n${items}`,
    duration: 5000,
  })
}

// ─── Dashboard click → switch tab ───
function handleDashboardClick(tabId: string) {
  if (visibleTabs.value.some(t => t.id === tabId)) {
    active.value = tabId
  }
}

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

  // Route query sheet
  const qs = route.query.sheet as string | undefined
  if (qs && visibleTabs.value.some(t => t.id === qs)) {
    active.value = qs
  }

  // Initialize bundle state
  await refreshCompletionStatus()
  await loadKamReferences()
})
</script>

<template>
  <div class="gt-a17-bundle" v-loading="loading">
    <!-- Completion status dashboard -->
    <div class="gt-a17-bundle__dashboard">
      <div
        v-for="item in dashboardItems"
        :key="item.tabId"
        class="dashboard-item"
        :class="`dashboard-item--${item.color}`"
        @click="handleDashboardClick(item.tabId)"
      >
        <span class="dashboard-item__icon">{{ item.icon }}</span>
        <span class="dashboard-item__label">{{ item.label }}</span>
      </div>
      <el-tag v-if="signOffReady" type="success" size="small" effect="dark" class="dashboard-signoff">
        可签发
      </el-tag>
    </div>

    <!-- Tab navigation -->
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="tab in visibleTabs"
        :key="tab.id"
        :label="tab.label"
        :name="tab.id"
        lazy
      >
        <!-- Lock warning banner -->
        <el-alert
          v-if="getTabLockReason(tab)"
          type="warning"
          :title="getTabLockReason(tab)"
          :closable="false"
          show-icon
          class="gt-a17-bundle__lock-alert"
        />

        <!-- program tab -->
        <template v-if="tab.kind === 'program'">
          <GtAProgramConsole :wp-id="props.wpId" :embedded="true" />
          <!-- Sign-off preconditions -->
          <div class="gt-a17-bundle__signoff-section">
            <div class="signoff-title">签发前置条件</div>
            <div class="signoff-list">
              <div
                v-for="cond in signOffPreconditions"
                :key="cond.id"
                class="signoff-item"
                :class="{ 'is-satisfied': cond.satisfied }"
              >
                <span class="signoff-item__icon">{{ cond.satisfied ? '✓' : '✗' }}</span>
                <span class="signoff-item__label">{{ cond.label }}</span>
              </div>
            </div>
            <el-button
              type="primary"
              :disabled="!signOffReady"
              @click="handleSignOffAttempt"
              class="signoff-btn"
            >
              标记审计总结完成
            </el-button>
          </div>
        </template>

        <!-- a17-summary tab -->
        <template v-else-if="tab.kind === 'a17-summary'">
          <GtA171AuditSummary
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- consultation tab (A17-3) -->
        <template v-else-if="tab.kind === 'consultation'">
          <GtA173ConsultationRecord
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
            :readonly="isTabReadonly(tab)"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- consultation-exec tab (A17-3-1) -->
        <template v-else-if="tab.kind === 'consultation-exec'">
          <GtA1731ConsultationExecution
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
            :readonly="isTabReadonly(tab)"
            @switch-tab="(tabId: string) => { active = tabId }"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- word tab -->
        <template v-else-if="tab.kind === 'word'">
          <WorkpaperWordEditor
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :readonly="isTabReadonly(tab)"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- kam tab -->
        <template v-else-if="tab.kind === 'kam'">
          <GtA1721Kam
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- checklist tab -->
        <template v-else-if="tab.kind === 'checklist'">
          <GtEmbeddedChecklist
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :checklist-wp-code="applicableA17_5[0] || 'A17-5-1'"
            :readonly="isTabReadonly(tab)"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- independence tab -->
        <template v-else-if="tab.kind === 'independence'">
          <IndependenceSigning
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :readonly="isTabReadonly(tab)"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.gt-a17-bundle {
  padding: var(--gt-space-4);
}

/* ─── Dashboard ─── */
.gt-a17-bundle__dashboard {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3);
  padding: var(--gt-space-3) var(--gt-space-4);
  margin-bottom: var(--gt-space-3);
  background: var(--gt-color-bg-elevated);
  border-radius: var(--gt-radius-sm);
  border: 1px solid var(--gt-color-border-light);
}

.dashboard-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-1);
  padding: var(--gt-space-1) var(--gt-space-2);
  border-radius: var(--gt-radius-xs);
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
  transition: background var(--gt-transition-fast);
}
.dashboard-item:hover {
  background: var(--gt-color-primary-bg);
}

.dashboard-item__icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
}
.dashboard-item--green .dashboard-item__icon { color: var(--gt-color-success); }
.dashboard-item--yellow .dashboard-item__icon { color: var(--gt-color-warning); }
.dashboard-item--gray .dashboard-item__icon { color: var(--gt-color-text-tertiary); }

.dashboard-item__label {
  color: var(--gt-color-text-secondary);
}

.dashboard-signoff {
  margin-left: auto;
}

/* ─── Lock alert ─── */
.gt-a17-bundle__lock-alert {
  margin-bottom: var(--gt-space-3);
}

/* ─── Sign-off section ─── */
.gt-a17-bundle__signoff-section {
  margin-top: var(--gt-space-5);
  padding: var(--gt-space-4);
  background: var(--gt-color-bg-elevated);
  border-radius: var(--gt-radius-sm);
  border: 1px solid var(--gt-color-border-light);
}

/* ─── Empty placeholder ─── */
.gt-a17-bundle__empty {
  padding: 40px 20px;
  text-align: center;
  color: var(--gt-color-text-tertiary, #909399);
  font-size: 14px;
}

.signoff-title {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text);
  margin-bottom: var(--gt-space-3);
}

.signoff-list {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-4);
}

.signoff-item {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}

.signoff-item.is-satisfied .signoff-item__icon {
  color: var(--gt-color-success);
}
.signoff-item:not(.is-satisfied) .signoff-item__icon {
  color: var(--gt-color-danger);
}

.signoff-btn {
  margin-top: var(--gt-space-2);
}
</style>
