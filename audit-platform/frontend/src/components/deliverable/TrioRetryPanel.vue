<template>
  <div class="trio-retry-panel">
    <div class="trio-retry-panel__header">
      <span class="trio-retry-panel__title">三件套生成明细</span>
      <span class="trio-retry-panel__progress" data-testid="trio-progress">
        已生成 {{ succeededCount }}/{{ TRIO_TOTAL }} 项
      </span>
    </div>

    <!-- 快照失效全局提示：此时所有重试入口置灰，须重新检查前置链 -->
    <div
      v-if="!snapshotValid"
      class="trio-retry-panel__stale"
      data-testid="trio-snapshot-stale"
    >
      数据快照已变化，无法在旧快照上重试。请重新检查前置链后重新出具。
    </div>

    <ul class="trio-retry-panel__list">
      <li
        v-for="step in orderedSteps"
        :key="step.key"
        class="trio-step"
        :class="`trio-step--${stepStatus(step.key)}`"
        :data-testid="`trio-step-${step.key}`"
        :data-status="stepStatus(step.key)"
      >
        <div class="trio-step__head">
          <span class="trio-step__seq">{{ step.sequence }}</span>
          <span class="trio-step__name">{{ step.label }}</span>
          <span class="trio-step__status" :data-testid="`trio-status-${step.key}`">
            {{ STATUS_LABELS[stepStatus(step.key)] || stepStatus(step.key) }}
          </span>

          <!-- 重试入口：仅失败项展示（需求 6.3）。
               有权限且快照有效 → 可点；否则置灰并给中文原因（需求 5.6/6.3）。 -->
          <button
            v-if="isFailed(step.key)"
            type="button"
            class="trio-step__retry"
            :data-testid="`trio-retry-${step.key}`"
            :disabled="!canRetry || retrying"
            :title="retryDisabledReason"
            @click="onRetry"
          >
            {{ retrying ? '重试中…' : '重试' }}
          </button>
          <span
            v-if="isFailed(step.key) && !canRetry"
            class="trio-step__retry-reason"
            :data-testid="`trio-retry-reason-${step.key}`"
          >
            {{ retryDisabledReason }}
          </span>
        </div>

        <!-- 当前失败原因（最近一次） -->
        <div
          v-if="isFailed(step.key) && itemOf(step.key)?.error_message"
          class="trio-step__error"
          :data-testid="`trio-error-${step.key}`"
        >
          失败原因：{{ itemOf(step.key)?.error_message }}
        </div>

        <!-- append-only 尝试历史：保留每一次失败原因，刷新不清空（需求 5.4/6.5） -->
        <ul
          v-if="attemptsOf(step.key).length"
          class="trio-step__attempts"
          :data-testid="`trio-attempts-${step.key}`"
        >
          <li
            v-for="att in attemptsOf(step.key)"
            :key="att.id"
            class="trio-attempt"
            :data-testid="`trio-attempt-${step.key}-${att.attempt_no}`"
          >
            <span class="trio-attempt__no">第 {{ att.attempt_no }} 次尝试</span>
            <span class="trio-attempt__status">{{ STATUS_LABELS[att.status] || att.status }}</span>
            <span v-if="att.error_message" class="trio-attempt__error">{{ att.error_message }}</span>
          </li>
        </ul>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchTrioJob,
  fetchTrioJobAttempts,
  retryTrioJob,
  TRIO_STEP_LABELS,
  TRIO_STATUS,
  TRIO_TERMINAL_STATUSES,
  type TrioStepKey,
  type ExportJobTrioResult,
  type ExportJobAttempt,
} from '@/services/deliverableApi'

/**
 * 交付中心三件套「失败项重试 + 尝试历史」面板（chain-closure-phase4 Task 11，需求 5.6/6.3/6.5）。
 *
 * 核心约束：
 * - 重试入口**只在失败项**旁展示（需求 6.3）；
 * - 有编辑权限且快照仍有效时才可点，否则置灰并说明原因（需求 5.6）；
 * - 点击调用**真实** retry API（POST /jobs/{id}/retry），而非仅改本地状态；
 *   成功后继续轮询 job 状态并刷新尝试历史；
 * - 尝试历史 append-only：合并保留旧失败原因，轮询刷新不得用空数组覆盖（需求 6.5）。
 *
 * 本组件不自己判定权限/快照有效性（那是 readiness 与后端鉴权的职责），
 * 由父组件以 `canEdit` / `snapshotValid` 下发；但真实的 403/409 仍以后端返回为准：
 * retry 收到 409 → 置为快照失效；收到 403 → 置为无权限。
 */
const props = defineProps<{
  projectId: string
  year: number
  job: ExportJobTrioResult
  attempts: ExportJobAttempt[]
  /** 项目编辑/交付权限（readiness 之外的权限门；无权限则置灰重试） */
  canEdit: boolean
  /** 快照是否仍有效（stale ⇒ 重试会 409，置灰） */
  snapshotValid: boolean
}>()

const emit = defineEmits<{
  /** job 状态更新（轮询到新状态时上抛，父组件据此刷新顶栏/完成态） */
  (e: 'job-updated', job: ExportJobTrioResult): void
  /** 尝试历史更新（append-only 合并后上抛） */
  (e: 'attempts-updated', attempts: ExportJobAttempt[]): void
  /** 快照失效（后端 409）时通知父组件重新检查前置链 */
  (e: 'snapshot-stale'): void
}>()

const TRIO_TOTAL = 3

/** 固定顺序 financial_report → disclosure_notes → audit_report。 */
const ORDERED_KEYS: TrioStepKey[] = ['financial_report', 'disclosure_notes', 'audit_report']

const STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '生成中',
  succeeded: '已完成',
  failed: '失败',
  blocked: '被阻断',
  skipped: '已跳过',
}

const retrying = ref(false)
/** 后端 403 实判无权限（覆盖 prop） */
const serverDeniedPermission = ref(false)

const orderedSteps = computed(() =>
  ORDERED_KEYS.map((key, i) => ({ key, sequence: i + 1, label: TRIO_STEP_LABELS[key] })),
)

/** step_key → item（word_export_task_id 不可靠，按 payload/步骤映射由后端保证 item 顺序）。 */
function itemOf(key: TrioStepKey) {
  // 后端 item 以固定 sequence 1/2/3 落库；这里按出现顺序对齐 ORDERED_KEYS。
  const idx = ORDERED_KEYS.indexOf(key)
  return props.job.items[idx]
}

function stepStatus(key: TrioStepKey): string {
  return itemOf(key)?.status || TRIO_STATUS.QUEUED
}

function isFailed(key: TrioStepKey): boolean {
  return stepStatus(key) === TRIO_STATUS.FAILED
}

const succeededCount = computed(
  () => props.job.items.filter((i) => i.status === TRIO_STATUS.SUCCEEDED).length,
)

/** 当前是否可重试：有权限（prop 且后端未 403）且快照有效。 */
const canRetry = computed(
  () => props.canEdit && !serverDeniedPermission.value && props.snapshotValid,
)

/** 置灰时的中文原因（需求 6.3）。 */
const retryDisabledReason = computed(() => {
  if (!props.canEdit || serverDeniedPermission.value) return '无编辑权限，无法重试'
  if (!props.snapshotValid) return '数据快照已变化，请重新检查前置链'
  return ''
})

/** 某步骤的尝试历史（append-only，按 attempt_no 升序）。 */
function attemptsOf(key: TrioStepKey) {
  const item = itemOf(key)
  if (!item) return []
  return props.attempts
    .filter((a) => a.item_id === item.id)
    .slice()
    .sort((a, b) => a.attempt_no - b.attempt_no)
}

/** 合并旧+新尝试历史（append-only：按 id 去重，绝不丢旧原因）。 */
function mergeAttempts(
  oldList: ExportJobAttempt[],
  incoming: ExportJobAttempt[],
): ExportJobAttempt[] {
  const byId = new Map<string, ExportJobAttempt>()
  for (const a of oldList) byId.set(a.id, a)
  // incoming 覆盖同 id（状态可能从 running→failed/succeeded 更新），但不删除旧 id。
  for (const a of incoming) byId.set(a.id, a)
  return [...byId.values()].sort(
    (a, b) => a.attempt_no - b.attempt_no || a.id.localeCompare(b.id),
  )
}

/** 轮询 job 直至终态或超时；每轮刷新尝试历史并 append-only 合并上抛。 */
async function pollUntilTerminal() {
  const maxAttempts = 60 // ~2min @ 2s
  for (let i = 0; i < maxAttempts; i++) {
    const job = await fetchTrioJob(props.projectId, props.job.id)
    emit('job-updated', job)
    const freshAttempts = await fetchTrioJobAttempts(props.projectId, props.job.id)
    emit('attempts-updated', mergeAttempts(props.attempts, freshAttempts))
    if (TRIO_TERMINAL_STATUSES.includes(job.status)) return job
    await new Promise((r) => setTimeout(r, 2000))
  }
  return await fetchTrioJob(props.projectId, props.job.id)
}

/**
 * 重试：调用**真实** retry API，而非仅改本地状态。
 * 成功 → 继续轮询并刷新历史；409 → 快照失效；403 → 无权限。
 */
async function onRetry() {
  if (!canRetry.value || retrying.value) return
  retrying.value = true
  try {
    const res = await retryTrioJob(props.projectId, props.job.id)
    ElMessage.success(`已重试 ${res.retried_count} 项，正在重新生成…`)
    await pollUntilTerminal()
  } catch (e: any) {
    const status = e?.response?.status
    const detail = e?.response?.data?.detail
    if (status === 409) {
      // 快照已变化：置灰重试，提示重新检查前置链（需求 5.3）
      emit('snapshot-stale')
      ElMessage.warning(
        typeof detail === 'string' ? detail : '数据快照已变化，请重新检查前置链后重新出具',
      )
    } else if (status === 403) {
      serverDeniedPermission.value = true
      ElMessage.warning('无编辑权限，无法重试')
    } else {
      ElMessage.error(typeof detail === 'string' ? detail : '重试失败，请稍后再试')
    }
  } finally {
    retrying.value = false
  }
}

defineExpose({ onRetry, canRetry, pollUntilTerminal })
</script>

<style scoped>
.trio-retry-panel {
  margin-top: 12px;
  padding: 12px 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}
.trio-retry-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.trio-retry-panel__title {
  font-size: 14px;
  font-weight: 600;
}
.trio-retry-panel__progress {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.trio-retry-panel__stale {
  margin-bottom: 10px;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  border-radius: 6px;
}
.trio-retry-panel__list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.trio-step {
  padding: 8px 0;
  border-top: 1px solid var(--el-border-color-lighter);
}
.trio-step:first-child {
  border-top: none;
}
.trio-step__head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.trio-step__seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  font-size: 12px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
}
.trio-step__name {
  font-size: 14px;
}
.trio-step__status {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.trio-step--succeeded .trio-step__status {
  color: var(--el-color-success);
}
.trio-step--failed .trio-step__status {
  color: var(--el-color-danger);
}
.trio-step__retry {
  margin-left: auto;
  padding: 2px 12px;
  font-size: 13px;
  color: #fff;
  background: var(--el-color-primary);
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.trio-step__retry:disabled {
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color);
  cursor: not-allowed;
}
.trio-step__retry-reason {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.trio-step__error {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-danger);
}
.trio-step__attempts {
  margin: 6px 0 0;
  padding: 0 0 0 30px;
  list-style: none;
}
.trio-attempt {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
.trio-attempt__no {
  font-weight: 600;
}
.trio-attempt__error {
  color: var(--el-color-danger);
}
</style>
