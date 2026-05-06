<!--
  GateReadinessPanel — R1 需求 3 统一就绪检查面板（签字前 / 归档前通用）

  设计要点：
  - 组件**不**自己拉 readiness 数据，只消费 props（由 PartnerDashboard / ArchiveWizard
    各自负责调用后端 SignReadiness / ArchiveReadiness 并把返回塞进来）。
  - 展示按 gate_engine 返回的 groups 折叠；每条 finding 可点击跳转到底稿/错报/附注。
  - 顶部显示 `gate_eval_id` 的"剩余 Ns"倒计时，过期时调用 onRefresh 一次。
  - severity: blocking | warning | info | pass（与 readiness_facade 对齐）。
-->
<template>
  <div class="gt-gate-panel">
    <!-- 顶部状态条 -->
    <div class="gt-gate-header">
      <div class="gt-gate-header-left">
        <el-tag
          :type="(props.data.ready ? 'success' : 'danger') as any"
          size="default"
          effect="dark"
        >
          {{ props.data.ready ? '可通过' : '需处理' }}
        </el-tag>
        <span class="gt-gate-summary">
          共 {{ totalGroups }} 项，
          <span class="gt-gate-sev-count sev-blocking">{{ counts.blocking }} 阻断</span>
          /
          <span class="gt-gate-sev-count sev-warning">{{ counts.warning }} 警告</span>
          /
          <span class="gt-gate-sev-count sev-pass">{{ counts.pass }} 通过</span>
        </span>
      </div>
      <div class="gt-gate-header-right">
        <span
          v-if="!isExpired"
          class="gt-gate-countdown"
          :class="{ 'gt-gate-countdown-warn': remainingSeconds <= 60 }"
        >
          剩余 {{ remainingSeconds }}s
        </span>
        <span v-else class="gt-gate-countdown gt-gate-countdown-expired">已过期</span>
        <el-button
          size="small"
          :icon="Refresh"
          :loading="props.loading"
          @click="handleRefresh"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 过期提示条 -->
    <div v-if="isExpired" class="gt-gate-expired-banner">
      <el-icon><WarningFilled /></el-icon>
      <span>本次评估结果已过期（超过 5 分钟），请点击"刷新"重新评估后再操作。</span>
    </div>

    <!-- groups 折叠面板 -->
    <el-collapse v-model="openGroupIds" class="gt-gate-collapse">
      <el-collapse-item
        v-for="group in props.data.groups"
        :key="group.id"
        :name="group.id"
      >
        <template #title>
          <div class="gt-gate-group-title">
            <el-tag
              :type="(statusTagType(group.status)) as any"
              size="small"
              effect="light"
            >
              {{ statusLabel(group.status) }}
            </el-tag>
            <span class="gt-gate-group-name">{{ group.name }}</span>
            <span v-if="group.findings?.length" class="gt-gate-group-count">
              · {{ group.findings.length }} 条
            </span>
          </div>
        </template>
        <!-- findings 列表 -->
        <div v-if="group.findings && group.findings.length" class="gt-gate-findings">
          <div
            v-for="(finding, idx) in group.findings"
            :key="`${group.id}-${idx}`"
            class="gt-gate-finding"
            :class="`sev-${finding.severity || 'info'}`"
          >
            <div class="gt-gate-finding-head">
              <el-tag
                :type="(severityTagType(finding.severity)) as any"
                size="small"
              >
                {{ severityLabel(finding.severity) }}
              </el-tag>
              <span v-if="finding.rule_code" class="gt-gate-rule-code">
                {{ finding.rule_code }}
              </span>
              <span class="gt-gate-finding-msg">{{ finding.message }}</span>
              <el-button
                v-if="hasJumpTarget(finding)"
                size="small"
                type="primary"
                text
                class="gt-gate-jump-btn"
                @click="handleJump(finding, group)"
              >
                跳转 →
              </el-button>
            </div>
            <div
              v-if="finding.action_hint"
              class="gt-gate-finding-hint"
            >
              <el-icon><InfoFilled /></el-icon>
              <span>{{ finding.action_hint }}</span>
            </div>
            <div
              v-if="locationSummary(finding)"
              class="gt-gate-finding-loc"
            >
              {{ locationSummary(finding) }}
            </div>
          </div>
        </div>
        <div v-else class="gt-gate-empty">该类目无需处理。</div>
      </el-collapse-item>
    </el-collapse>

    <!-- 底部 gate_eval_id 追踪信息 -->
    <div v-if="props.data.gate_eval_id" class="gt-gate-trace">
      <span class="gt-gate-trace-label">gate_eval_id:</span>
      <el-button
        type="primary"
        link
        size="small"
        :icon="CopyDocument"
        @click="copyEvalId"
      >
        {{ shortEvalId }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Refresh,
  WarningFilled,
  InfoFilled,
  CopyDocument,
} from '@element-plus/icons-vue'

// ── 类型定义 ──────────────────────────────────────────────────────────────
export interface GateReadinessFindingLocation {
  project_id?: string
  wp_id?: string
  cell?: string
  section?: string
  procedure_ids?: string[]
  sample_entry_group_ids?: string[]
  [key: string]: any
}

export interface GateReadinessFinding {
  rule_code?: string
  error_code?: string
  severity?: 'blocking' | 'warning' | 'info' | 'pass' | string
  message: string
  location?: GateReadinessFindingLocation | null
  action_hint?: string
}

export interface GateReadinessGroup {
  id: string
  name: string
  status: 'blocking' | 'warning' | 'info' | 'pass' | string
  findings: GateReadinessFinding[]
}

export interface GateReadinessData {
  ready: boolean
  groups: GateReadinessGroup[]
  gate_eval_id?: string | null
  expires_at?: string | null
  // legacy 兼容字段（本组件不读取）
  checks?: any[]
  ready_to_sign?: boolean
}

const props = withDefaults(
  defineProps<{
    /** 由调用方拉取的 readiness 数据 */
    data: GateReadinessData
    /** 调用方正在刷新时传 true，用于禁用按钮 */
    loading?: boolean
    /** 绑定到 router.params.projectId 的覆盖项（默认从 route 取） */
    projectId?: string
    /** 点击刷新按钮 / 过期自动刷新时回调 */
    onRefresh?: () => void | Promise<void>
    /** 自定义 finding 跳转；不传则走内置默认映射 */
    onFindingJump?: (finding: GateReadinessFinding, group: GateReadinessGroup) => void
    /** 默认展开的 group ids；不传时展开所有非 pass 组 */
    defaultOpenGroupIds?: string[]
  }>(),
  {
    loading: false,
    projectId: '',
    onRefresh: undefined,
    onFindingJump: undefined,
    defaultOpenGroupIds: undefined,
  },
)

const emit = defineEmits<{
  (e: 'no-target', finding: GateReadinessFinding, group: GateReadinessGroup): void
}>()

const route = useRoute()
const router = useRouter()

// ── 倒计时 ────────────────────────────────────────────────────────────────
const now = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | null = null
// 防止多次触发自动刷新：当前 gate_eval_id 是否已触发过 onRefresh
let autoRefreshedEvalId: string | null = null

const expiresAtMs = computed(() => {
  if (!props.data?.expires_at) return 0
  const t = Date.parse(props.data.expires_at)
  return Number.isFinite(t) ? t : 0
})

const remainingSeconds = computed(() => {
  if (!expiresAtMs.value) return 0
  const diff = Math.floor((expiresAtMs.value - now.value) / 1000)
  return diff > 0 ? diff : 0
})

const isExpired = computed(() => {
  if (!expiresAtMs.value) return false
  return now.value >= expiresAtMs.value
})

function startTick() {
  stopTick()
  tickTimer = setInterval(() => {
    now.value = Date.now()
    // 过期后自动刷新一次（同一 gate_eval_id 只触发一次）
    if (
      isExpired.value
      && props.data?.gate_eval_id
      && props.onRefresh
      && autoRefreshedEvalId !== props.data.gate_eval_id
    ) {
      autoRefreshedEvalId = props.data.gate_eval_id
      try {
        const r = props.onRefresh()
        if (r && typeof (r as any).then === 'function') {
          void (r as Promise<void>).catch(() => {})
        }
      } catch {
        /* 忽略回调内异常，交给调用方自己处理 */
      }
    }
  }, 1000)
}

function stopTick() {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

onMounted(() => {
  startTick()
})

onBeforeUnmount(() => {
  stopTick()
})

// 新一轮 data（不同 gate_eval_id）到来时重置自动刷新标记
watch(
  () => props.data?.gate_eval_id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      autoRefreshedEvalId = null
      now.value = Date.now()
    }
  },
)

// ── groups 展开状态 ───────────────────────────────────────────────────────
function computeDefaultOpen(): string[] {
  if (props.defaultOpenGroupIds && props.defaultOpenGroupIds.length) {
    return [...props.defaultOpenGroupIds]
  }
  // 默认展开所有非 pass 组
  return (props.data?.groups || [])
    .filter(g => g.status !== 'pass')
    .map(g => g.id)
}

const openGroupIds = ref<string[]>(computeDefaultOpen())

watch(
  () => props.data?.groups,
  () => {
    openGroupIds.value = computeDefaultOpen()
  },
)

// ── 汇总计数 ──────────────────────────────────────────────────────────────
const totalGroups = computed(() => props.data?.groups?.length || 0)

const counts = computed(() => {
  const c = { blocking: 0, warning: 0, pass: 0, info: 0 }
  for (const g of props.data?.groups || []) {
    const s = String(g.status || 'info')
    if (s in c) (c as any)[s] += 1
    else (c as any).info += 1
  }
  return c
})

// ── 文案 / 样式映射 ──────────────────────────────────────────────────────
function statusTagType(status: string | undefined): string {
  switch (status) {
    case 'pass': return 'success'
    case 'warning': return 'warning'
    case 'blocking': return 'danger'
    case 'info':
    default: return 'info'
  }
}

function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'pass': return '通过'
    case 'warning': return '警告'
    case 'blocking': return '阻断'
    case 'info': return '提示'
    default: return status || '未知'
  }
}

function severityTagType(sev: string | undefined): string {
  return statusTagType(sev)
}

function severityLabel(sev: string | undefined): string {
  return statusLabel(sev)
}

// ── 跳转逻辑 ──────────────────────────────────────────────────────────────
function hasJumpTarget(finding: GateReadinessFinding): boolean {
  const loc = finding.location
  if (!loc || typeof loc !== 'object') return false
  return !!(
    loc.wp_id
    || loc.section
    || (loc.sample_entry_group_ids && loc.sample_entry_group_ids.length)
    || (loc.procedure_ids && loc.procedure_ids.length)
  )
}

function resolveProjectId(finding: GateReadinessFinding): string | undefined {
  return (
    finding.location?.project_id
    || props.projectId
    || (route.params.projectId as string | undefined)
  )
}

function handleJump(finding: GateReadinessFinding, group: GateReadinessGroup) {
  // 优先调用方自定义
  if (props.onFindingJump) {
    try {
      props.onFindingJump(finding, group)
    } catch (err) {
      console.error('[GateReadinessPanel] onFindingJump threw:', err)
    }
    return
  }

  const loc = finding.location || {}
  const projectId = resolveProjectId(finding)
  if (!projectId) {
    ElMessage.info('无法定位项目上下文，无法跳转')
    emit('no-target', finding, group)
    return
  }

  // 1) 底稿单元格
  if (loc.wp_id) {
    router.push({
      name: 'WorkpaperEditor',
      params: { projectId, wpId: loc.wp_id },
      query: loc.cell ? { cell: loc.cell } : undefined,
    })
    return
  }

  // 2) 按 section / 结构化字段路由
  const section = String(loc.section || '').toLowerCase()
  if (
    section === 'adjustments'
    || (loc.sample_entry_group_ids && loc.sample_entry_group_ids.length)
  ) {
    router.push({ name: 'Adjustments', params: { projectId } })
    return
  }
  if (section === 'misstatements') {
    router.push({ name: 'Misstatements', params: { projectId } })
    return
  }
  if (section === 'notes' || section === 'disclosure' || section === 'disclosure_notes') {
    router.push({ name: 'DisclosureNotes', params: { projectId } })
    return
  }
  if (section === 'report' || section === 'audit_report') {
    router.push({ name: 'AuditReport', params: { projectId } })
    return
  }
  if (section === 'issues' || section === 'review_comment') {
    router.push({ name: 'IssueTicketList', params: { projectId } })
    return
  }

  // 3) 兜底
  ElMessage.info('该条提示未关联可跳转的对象')
  emit('no-target', finding, group)
}

// ── 操作 ──────────────────────────────────────────────────────────────────
async function handleRefresh() {
  if (!props.onRefresh) {
    ElMessage.warning('当前页面未提供刷新能力')
    return
  }
  try {
    const r = props.onRefresh()
    if (r && typeof (r as any).then === 'function') {
      await (r as Promise<void>)
    }
  } catch (err: any) {
    ElMessage.error(err?.message || '刷新失败')
  }
}

const shortEvalId = computed(() => {
  const id = props.data?.gate_eval_id || ''
  return id.length > 16 ? `${id.slice(0, 8)}...${id.slice(-4)}` : id
})

async function copyEvalId() {
  if (!props.data?.gate_eval_id) return
  try {
    await navigator.clipboard.writeText(props.data.gate_eval_id)
    ElMessage.success('gate_eval_id 已复制')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

// ── 其他辅助 ──────────────────────────────────────────────────────────────
function locationSummary(finding: GateReadinessFinding): string {
  const loc = finding.location
  if (!loc || typeof loc !== 'object') return ''
  const parts: string[] = []
  if (loc.wp_id) parts.push(`底稿 ${String(loc.wp_id).slice(0, 8)}`)
  if (loc.cell) parts.push(`单元格 ${loc.cell}`)
  if (loc.section) parts.push(`位置 ${loc.section}`)
  if (loc.procedure_ids && loc.procedure_ids.length) {
    parts.push(`程序 x${loc.procedure_ids.length}`)
  }
  if (loc.sample_entry_group_ids && loc.sample_entry_group_ids.length) {
    parts.push(`分录组 x${loc.sample_entry_group_ids.length}`)
  }
  return parts.join(' · ')
}
</script>

<style scoped>
.gt-gate-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid rgba(75, 45, 119, 0.08);
  border-radius: var(--gt-radius-md, 8px);
}

/* ── header ── */
.gt-gate-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.gt-gate-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.gt-gate-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.gt-gate-summary {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}

.gt-gate-sev-count {
  font-weight: 600;
}

.gt-gate-sev-count.sev-blocking { color: #f56c6c; }
.gt-gate-sev-count.sev-warning  { color: #e6a23c; }
.gt-gate-sev-count.sev-pass     { color: #67c23a; }

.gt-gate-countdown {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
  min-width: 64px;
  text-align: right;
}

.gt-gate-countdown-warn {
  color: #e6a23c;
  font-weight: 600;
}

.gt-gate-countdown-expired {
  color: #f56c6c;
  font-weight: 600;
}

/* ── expired banner ── */
.gt-gate-expired-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fef0f0;
  color: #f56c6c;
  border-radius: 4px;
  font-size: 13px;
}

/* ── collapse ── */
.gt-gate-collapse :deep(.el-collapse-item__header) {
  font-weight: 500;
}

.gt-gate-group-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-gate-group-name {
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
}

.gt-gate-group-count {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

/* ── findings ── */
.gt-gate-findings {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-gate-finding {
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.02);
  border-left: 3px solid rgba(0, 0, 0, 0.12);
  border-radius: 4px;
}

.gt-gate-finding.sev-blocking { border-left-color: #f56c6c; background: #fef0f0; }
.gt-gate-finding.sev-warning  { border-left-color: #e6a23c; background: #fdf6ec; }
.gt-gate-finding.sev-info     { border-left-color: #909399; }
.gt-gate-finding.sev-pass     { border-left-color: #67c23a; background: #f0f9eb; }

.gt-gate-finding-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gt-gate-rule-code {
  font-family: var(--gt-font-family-mono, Consolas, monospace);
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

.gt-gate-finding-msg {
  flex: 1;
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
  word-break: break-word;
}

.gt-gate-jump-btn {
  flex-shrink: 0;
}

.gt-gate-finding-hint {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}

.gt-gate-finding-loc {
  margin-top: 4px;
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #909399);
  font-family: var(--gt-font-family-mono, Consolas, monospace);
}

.gt-gate-empty {
  padding: 8px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

/* ── trace ── */
.gt-gate-trace {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

.gt-gate-trace-label {
  font-family: var(--gt-font-family-mono, Consolas, monospace);
}
</style>
