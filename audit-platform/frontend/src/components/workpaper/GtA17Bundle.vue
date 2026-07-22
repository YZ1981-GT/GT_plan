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
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
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
const GtA177IndependenceDeclaration = defineAsyncComponent(() => import('./GtA177IndependenceDeclaration.vue'))
const GtA1721Kam = defineAsyncComponent(() => import('./GtA1721Kam.vue'))
const GtA173ConsultationRecord = defineAsyncComponent(() => import('./GtA173ConsultationRecord.vue'))
const GtA1731ConsultationExecution = defineAsyncComponent(() => import('./GtA1731ConsultationExecution.vue'))
const GtA174DisagreementRecord = defineAsyncComponent(() => import('./GtA174DisagreementRecord.vue'))
const GtA176ClosingMeeting = defineAsyncComponent(() => import('./GtA176ClosingMeeting.vue'))

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
  kind: 'program' | 'a17-summary' | 'word' | 'checklist' | 'independence' | 'kam' | 'consultation' | 'consultation-exec' | 'disagreement' | 'closing-meeting'
  wpCode?: string
  tracked?: boolean
}

const TABS: TabDef[] = [
  { id: 'program', label: '审计程序', kind: 'program' },
  { id: 'A17-1', label: '重大事项概要汇总', kind: 'a17-summary', wpCode: 'A17-1', tracked: true },
  { id: 'A17-2-1', label: '关键审计事项', kind: 'kam', wpCode: 'A17-2-1' },
  { id: 'A17-3', label: '业务咨询记录', kind: 'consultation', wpCode: 'A17-3' },
  { id: 'A17-3-1', label: '业务咨询执行记录', kind: 'consultation-exec', wpCode: 'A17-3-1' },
  { id: 'A17-4', label: '重大专业分歧事项记录', kind: 'disagreement', wpCode: 'A17-4' },
  { id: 'A17-5', label: '审计工作完成核对表', kind: 'checklist', wpCode: 'A17-5', tracked: true },
  { id: 'A17-6', label: '总结会会议纪要', kind: 'closing-meeting', wpCode: 'A17-6', tracked: true },
  { id: 'A17-7', label: '独立性声明书', kind: 'independence', wpCode: 'A17-7', tracked: true },
  { id: 'A17-7A', label: '独立性声明书(专委会)', kind: 'independence', wpCode: 'A17-7A', tracked: false },
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

// ─── A17-5 sub-tab switching ───
const A175_LABELS: Record<string, string> = {
  'A17-5-1': '财报审计',
  'A17-5-2': '内控审计',
  'A17-5-3': 'IPO业务',
  'A17-5-4': '新三板',
  'A17-5-5': '函证程序',
}
const activeA175Sub = ref('')
const a175SubOptions = computed(() =>
  applicableA17_5.value.map(code => ({ label: A175_LABELS[code] || code, value: code })),
)
const activeA175WpId = computed(() => {
  const code = activeA175Sub.value || applicableA17_5.value[0] || ''
  return wpIdMap.value[code] || ''
})
// Initialize activeA175Sub when applicableA17_5 resolves
watch(applicableA17_5, (codes) => {
  if (codes.length > 0 && !activeA175Sub.value) {
    activeA175Sub.value = codes[0]
  }
}, { immediate: true })

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
  consultationPairing,
  disagreementClosure,
  consistencyErrors,
  signOffPreconditions,
  signOffReady,
  kamReferences,
  kamStale,
  independenceDrift,
  chapterStale,
  agendaStale,
  partnerSummary,
  timeline,
  crossAlerts,
  signoffSelfCheck,
  refreshCompletionStatus,
  refreshConsistencyCheck,
  refreshKamStale,
  refreshIndependenceDrift,
  refreshChapterStale,
  refreshAgendaStale,
  refreshPartnerSummary,
  refreshCrossAlerts,
  refreshSignoffSelfCheck,
  loadKamReferences,
} = bundleState

// B/C 类：裁剪默认不选 A17；若底稿已存在则 soft 提示
const businessCategory = ref('')
const categorySoftWarning = computed(() => {
  const prefix = (businessCategory.value || '').charAt(0).toUpperCase()
  if (prefix === 'C') {
    return '当前项目为 C 类：A17 默认不适用。若误开可忽略或联系项目经理裁剪。'
  }
  if (prefix === 'B') {
    return '当前项目为 B 类：A17 非默认必备（A 类财报签发链路）。可按需编制，不作为签发强制闸门参考。'
  }
  return ''
})


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

// Tab switch → refresh completion / gates when leaving key tabs
watch(active, (newTab, oldTab) => {
  prevTab.value = oldTab
  if (oldTab === 'A17-5' || oldTab === 'A17-1' || oldTab === 'A17-7' || oldTab === 'A17-2-1' || oldTab === 'A17-4' || oldTab === 'A17-6') {
    refreshCompletionStatus()
    refreshConsistencyCheck()
    refreshKamStale()
    refreshIndependenceDrift()
    refreshChapterStale()
    refreshAgendaStale()
    refreshPartnerSummary()
    refreshCrossAlerts()
    refreshSignoffSelfCheck()
  }
})

// 可签发 → 回写 A1-11 解锁
watch(signOffReady, (ready) => {
  if (ready && props.projectId) {
    eventBus.emit('a17-audit-summary-completed', { projectId: props.projectId })
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
  const items = unmet.map(p => `• ${p.label}${p.hint ? `（${p.hint}）` : ''}`).join('\n')
  ElMessage.warning({
    message: `签发前置条件未满足：\n${items}`,
    duration: 5000,
  })
}

function handleSignOffAction(cond: { actionTab?: string; satisfied: boolean }) {
  if (cond.satisfied || !cond.actionTab) return
  if (visibleTabs.value.some(t => t.id === cond.actionTab)) {
    active.value = cond.actionTab
  }
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
      try {
        const proj = await api.get<any>(`/api/projects/${props.projectId}`, { _silent: true } as any)
        businessCategory.value = proj?.business_category || proj?.data?.business_category || ''
      } catch {
        businessCategory.value = ''
      }
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

  // Initialize bundle state（含签发闸门相关校验）
  await refreshCompletionStatus()
  await Promise.all([
    loadKamReferences(),
    refreshConsistencyCheck(),
    refreshKamStale(),
    refreshIndependenceDrift(),
    refreshChapterStale(),
    refreshAgendaStale(),
    refreshPartnerSummary(),
    refreshCrossAlerts(),
    refreshSignoffSelfCheck(),
  ])
  if (signOffReady.value && props.projectId) {
    eventBus.emit('a17-audit-summary-completed', { projectId: props.projectId })
  }
})
</script>

<template>
  <div class="gt-a17-bundle" v-loading="loading">
    <el-alert
      v-if="categorySoftWarning"
      type="info"
      :title="categorySoftWarning"
      :closable="true"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    />

    <!-- Partner / EQCR one-pager + timeline -->
    <el-collapse v-if="partnerSummary || timeline" class="gt-a17-bundle__partner">
      <el-collapse-item name="partner" title="合伙人 / EQCR 一页摘要">
        <div v-if="timeline?.milestones?.length" class="gt-a17-bundle__timeline">
          <div
            v-for="m in timeline.milestones"
            :key="m.id"
            class="timeline-item"
            :class="{ 'is-ok': m.ok, 'is-missing': !m.ok }"
          >
            <span class="timeline-item__label">{{ m.label }}</span>
            <span class="timeline-item__date">{{ m.date || '未填' }}</span>
          </div>
        </div>
        <el-alert
          v-for="(w, i) in (timeline?.warnings || [])"
          :key="'tw'+i"
          type="error"
          :title="w"
          :closable="false"
          show-icon
          style="margin-bottom: 6px"
        />
        <div v-if="partnerSummary" class="gt-a17-bundle__summary-grid">
          <div class="summary-cell"><span class="k">KAM</span><span class="v">{{ partnerSummary.kam_count }} 条{{ partnerSummary.kam_stale ? ' · 过期' : '' }}</span></div>
          <div class="summary-cell"><span class="k">咨询</span><span class="v">{{ partnerSummary.has_consultation ? '有' : '无' }}</span></div>
          <div class="summary-cell"><span class="k">分歧</span><span class="v">{{ partnerSummary.has_disagreement ? (partnerSummary.disagreement_closed ? '已闭环' : '未闭环') : '无' }}</span></div>
          <div class="summary-cell"><span class="k">独立性</span><span class="v">{{ partnerSummary.independence_drift ? '期间漂移' : '正常' }}</span></div>
        </div>
        <div v-if="partnerSummary?.opinion_preview" class="gt-a17-bundle__opinion">
          <div class="opinion-label">意见预览（ch14）</div>
          <div class="opinion-body">{{ partnerSummary.opinion_preview }}</div>
        </div>
        <el-alert
          v-if="partnerSummary?.blockers?.length"
          type="warning"
          :title="`关注项：${partnerSummary.blockers.join('；')}`"
          :closable="false"
          show-icon
          style="margin-top: 8px"
        />
      </el-collapse-item>
    </el-collapse>

    <!-- 跨底稿联动：A13 超重要性 / A10 未沟通 -->
    <div v-if="crossAlerts.length" class="gt-a17-bundle__cross-alerts">
      <el-alert
        v-for="a in crossAlerts"
        :key="a.id"
        :type="a.severity === 'error' ? 'error' : 'warning'"
        :title="a.title"
        :closable="false"
        show-icon
        style="margin-bottom: 6px"
      >
        <template #default>
          <div>{{ a.message }}</div>
          <div v-if="a.action_hint" style="margin-top: 4px; color: #606266">{{ a.action_hint }}</div>
          <el-button
            v-if="a.action_tab && visibleTabs.some(t => t.id === a.action_tab)"
            size="small"
            type="primary"
            link
            @click="active = a.action_tab!"
          >前往 {{ a.action_tab }} →</el-button>
        </template>
      </el-alert>
    </div>

    <!-- 归档/签发自检 -->
    <el-collapse v-if="signoffSelfCheck" class="gt-a17-bundle__self-check">
      <el-collapse-item name="self-check">
        <template #title>
          <span>
            归档包自检
            <el-tag
              size="small"
              :type="signoffSelfCheck.ready ? 'success' : 'danger'"
              style="margin-left: 8px"
            >{{ signoffSelfCheck.ready ? '通过' : '未通过' }}</el-tag>
          </span>
        </template>
        <div
          v-for="it in signoffSelfCheck.items"
          :key="it.id"
          class="self-check-row"
          :class="{ 'is-ok': it.ok, 'is-fail': !it.ok }"
        >
          <span class="self-check-icon">{{ it.ok ? '✓' : '✗' }}</span>
          <span class="self-check-label">{{ it.label }}</span>
          <span class="self-check-detail">{{ it.detail }}</span>
          <el-button
            v-if="!it.ok && it.action_tab && visibleTabs.some(t => t.id === it.action_tab)"
            size="small"
            type="primary"
            link
            @click="active = it.action_tab!"
          >前往 →</el-button>
        </div>
      </el-collapse-item>
    </el-collapse>

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

    <el-alert
      v-if="chapterStale.length"
      type="warning"
      :title="`A17-1 有 ${chapterStale.length} 章相对上游可能过期`"
      :closable="false"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    >
      <template #default>
        <ul style="margin: 4px 0 0; padding-left: 18px">
          <li v-for="c in chapterStale.slice(0, 5)" :key="c.chapter_id">第{{ c.chapter_num }}章：{{ c.message }}</li>
        </ul>
        <el-button size="small" type="primary" link @click="active = 'A17-1'">前往 A17-1 重新拉取 →</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="agendaStale.length"
      type="warning"
      :title="`A17-6 有 ${agendaStale.length} 项议程相对上游可能过期`"
      :closable="false"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    >
      <template #default>
        <el-button size="small" type="primary" link @click="active = 'A17-6'">前往总结会核对 →</el-button>
      </template>
    </el-alert>

    <!-- A17-3 ↔ A17-3-1 pairing warning -->
    <el-alert
      v-if="consultationPairing.warning"
      type="error"
      :title="consultationPairing.warning"
      :closable="false"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    >
      <template #default>
        <el-button size="small" type="primary" link @click="active = 'A17-3-1'">前往 A17-3-1 →</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="consistencyErrors.length"
      type="error"
      :title="`一致性校验有 ${consistencyErrors.length} 项 error，阻断签发`"
      :closable="false"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    >
      <template #default>
        <ul style="margin: 4px 0 0; padding-left: 18px">
          <li v-for="e in consistencyErrors.slice(0, 5)" :key="e.rule_id">{{ e.description }}</li>
        </ul>
        <el-button size="small" type="primary" link @click="active = 'A17-1'">前往 A17-1 →</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="disagreementClosure.warning"
      type="error"
      :title="disagreementClosure.warning"
      :closable="false"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    >
      <template #default>
        <el-button size="small" type="primary" link @click="active = 'A17-4'">前往 A17-4 →</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="kamStale"
      type="warning"
      title="A17-2-1 KAM 与审计报告不一致（已过期），请重新推送后再签发"
      :closable="false"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    >
      <template #default>
        <el-button size="small" type="primary" link @click="active = 'A17-2-1'">前往 KAM →</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="independenceDrift.hasDrift"
      type="warning"
      :title="independenceDrift.message || 'A17-7 与承接阶段 B3 独立性期间存在差异，请核对'"
      :closable="true"
      show-icon
      class="gt-a17-bundle__lock-alert"
      style="margin: 0 0 8px"
    />

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
                :class="{ 'is-satisfied': cond.satisfied, 'is-actionable': !cond.satisfied && !!cond.actionTab }"
                @click="handleSignOffAction(cond)"
              >
                <span class="signoff-item__icon">{{ cond.satisfied ? '✓' : '✗' }}</span>
                <div class="signoff-item__body">
                  <span class="signoff-item__label">{{ cond.label }}</span>
                  <span v-if="!cond.satisfied && cond.hint" class="signoff-item__hint">{{ cond.hint }}</span>
                </div>
                <el-button
                  v-if="!cond.satisfied && cond.actionTab"
                  size="small"
                  type="primary"
                  link
                  @click.stop="handleSignOffAction(cond)"
                >{{ cond.actionLabel || '前往 →' }}</el-button>
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
          <el-alert
            v-if="consultationPairing.hasConsult && !consultationPairing.closed"
            type="warning"
            title="请同步完成 A17-3-1 咨询结果执行记录，或在 A17-3-1 勾选「无需执行」"
            :closable="false"
            show-icon
            class="gt-a17-bundle__lock-alert"
          >
            <el-button size="small" type="primary" link @click="active = 'A17-3-1'">前往 A17-3-1 →</el-button>
          </el-alert>
          <GtA173ConsultationRecord
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
            :readonly="isTabReadonly(tab)"
            @saved="refreshCompletionStatus"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- consultation-exec tab (A17-3-1) -->
        <template v-else-if="tab.kind === 'consultation-exec'">
          <el-alert
            v-if="!wpIdMap['A17-3']"
            type="info"
            title="当前项目无 A17-3 业务咨询记录；若无需咨询可忽略本页"
            :closable="false"
            show-icon
            class="gt-a17-bundle__lock-alert"
          />
          <GtA1731ConsultationExecution
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
            :readonly="isTabReadonly(tab)"
            @switch-tab="(tabId: string) => { active = tabId }"
            @saved="refreshCompletionStatus"
          />
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- disagreement tab (A17-4) -->
        <template v-else-if="tab.kind === 'disagreement'">
          <GtA174DisagreementRecord
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
            :readonly="isTabReadonly(tab)"
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

        <!-- closing-meeting tab (A17-6) -->
        <template v-else-if="tab.kind === 'closing-meeting'">
          <GtA176ClosingMeeting
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
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
          <div v-if="applicableA17_5.length > 0" class="gt-a17-bundle__checklist-wrapper">
            <!-- A17-5 子表切换器 -->
            <el-segmented
              v-if="applicableA17_5.length > 1"
              v-model="activeA175Sub"
              :options="a175SubOptions"
              size="small"
              class="gt-a17-bundle__checklist-switcher"
            />
            <GtEmbeddedChecklist
              v-if="activeA175WpId"
              :wp-id="activeA175WpId"
              :checklist-wp-code="activeA175Sub"
              :readonly="isTabReadonly(tab)"
              @save="refreshCompletionStatus"
            />
          </div>
          <div v-else class="gt-a17-bundle__empty">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
        </template>

        <!-- independence tab -->
        <template v-else-if="tab.kind === 'independence'">
          <GtA177IndependenceDeclaration
            v-if="getTabWpId(tab)"
            :wp-id="getTabWpId(tab)"
            :project-id="props.projectId"
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

.gt-a17-bundle__partner {
  margin-bottom: 10px;
}
.gt-a17-bundle__cross-alerts {
  margin-bottom: 10px;
}
.gt-a17-bundle__self-check {
  margin-bottom: 10px;
}
.self-check-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.self-check-row.is-ok .self-check-icon { color: var(--gt-color-success, #67c23a); }
.self-check-row.is-fail .self-check-icon { color: var(--gt-color-danger, #f56c6c); }
.self-check-label { font-weight: 500; min-width: 180px; }
.self-check-detail { color: #606266; flex: 1; }
.gt-a17-bundle__timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
}
.timeline-item {
  min-width: 120px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
}
.timeline-item.is-missing {
  border-color: #f5c6cb;
  background: #fef0f0;
}
.timeline-item__label {
  display: block;
  font-size: 12px;
  color: var(--gt-color-text-secondary);
}
.timeline-item__date {
  font-size: 13px;
  font-weight: 600;
}
.gt-a17-bundle__summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}
.summary-cell {
  padding: 6px 8px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
  border-radius: 4px;
  font-size: 12px;
}
.summary-cell .k {
  color: var(--gt-color-text-secondary);
  margin-right: 6px;
}
.gt-a17-bundle__opinion {
  font-size: 12px;
}
.opinion-label {
  color: var(--gt-color-text-secondary);
  margin-bottom: 4px;
}
.opinion-body {
  white-space: pre-wrap;
  max-height: 80px;
  overflow: auto;
  line-height: 1.45;
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

/* ─── A17-5 Checklist sub-tab switcher ─── */
.gt-a17-bundle__checklist-wrapper {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.gt-a17-bundle__checklist-switcher {
  align-self: flex-start;
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
  padding: 6px 8px;
  border-radius: var(--gt-radius-xs);
}
.signoff-item.is-actionable {
  cursor: pointer;
}
.signoff-item.is-actionable:hover {
  background: var(--gt-color-primary-bg, #ecf5ff);
}
.signoff-item__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.signoff-item__hint {
  font-size: 12px;
  color: var(--gt-color-danger, #f56c6c);
  line-height: 1.35;
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
