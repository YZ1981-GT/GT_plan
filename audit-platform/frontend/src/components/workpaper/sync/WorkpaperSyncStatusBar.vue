<!--
  WorkpaperSyncStatusBar.vue — 双向回写的**紧凑状态条**

  spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
  Requirements: 5.8, 11.2, 11.3, 11.6, 11.10, 11.11
  Properties: P46（26 个状态逐一可辨）/ P48（error 优先、不被成功文案覆盖）

  ═══ 文案真源只有一个 ═══

  头条消息逐字取桥的 `feedback.message`（error 优先）。阶段标签取
  `WP_BRIDGE_STATE_TEXT[state]`——同一个模块里的同一张表，不是第二份真源；
  失败时它被强制加上「失败于：」前缀，结构上不可能被读成一句成功。

  ═══ 三个 verdict 布尔的**三个**消费方 ═══

  `classifySyncFailure` 刻意返回三个独立布尔。本条把它们摆成三行显式披露：

  * `retryableOperation` —— 同时是「重试回写」按钮的门（两侧都可达：500/503 为真、
    409 stale 为假）；
  * `canEnterEditing` —— **只**作披露。它在服务端拒绝表的每个分支里都是 `false`，
    做成「按钮显示条件」就是一段永不执行的死代码（永远 GREEN 的判据）；
  * `canForcesave` —— 同上作披露，并让「保存并回到表单」这个入口在失败后消失。
    真正的 forcesave 按钮归 Task 33 的宿主，本条不做第二个。
-->
<template>
  <div
    class="wp-sync-status-bar"
    data-testid="wp-sync-status-bar"
    :data-state="state"
    :data-mode="mode"
    :data-kind="feedback.kind"
    :data-tone="tone"
    :data-wait="waitKind"
    role="status"
    aria-live="polite"
  >
    <div class="wp-sync-status-bar__head">
      <span
        v-if="waitKind === 'progress'"
        class="wp-sync-status-bar__spinner"
        data-testid="wp-sync-status-spinner"
        aria-hidden="true"
      />
      <el-tag :type="tone" size="small" data-testid="wp-sync-status-stage">{{ stageText }}</el-tag>
      <span class="wp-sync-status-bar__message" data-testid="wp-sync-status-message">
        {{ feedback.message }}
      </span>
      <span
        v-if="actionHint !== ''"
        class="wp-sync-status-bar__hint"
        data-testid="wp-sync-status-action-hint"
      >
        {{ actionHint }}
      </span>
    </div>

    <!-- duplicate：必须同时显示 requested 与 canonical（AC 5.5 末段） -->
    <div
      v-if="duplicateFold !== null"
      class="wp-sync-status-bar__row"
      data-testid="wp-sync-status-duplicate"
      :data-requested="duplicateFold.requested"
      :data-canonical="duplicateFold.canonical"
    >
      <span class="wp-sync-status-bar__label">已折叠</span>
      <span>本次请求 {{ duplicateFold.requested }} → 规范回写任务 {{ duplicateFold.canonical }}</span>
    </div>

    <!-- close 仲裁进展：失权 / 接任者 / 无接任者，三者逐一可辨 -->
    <div
      v-if="closeArbitrationVisible"
      class="wp-sync-status-bar__row wp-sync-status-bar__row--warn"
      data-testid="wp-sync-status-close-arbitration"
      :data-outcome="closeArbitration.outcome"
      :data-successor="closeArbitration.successorIntentId ?? ''"
    >
      <span class="wp-sync-status-bar__label">关闭仲裁</span>
      <span>{{ closeArbitration.label }}</span>
    </div>

    <!-- 追溯 chips（AC 11.11） -->
    <div class="wp-sync-status-bar__trace" data-testid="wp-sync-status-trace">
      <span class="wp-sync-status-bar__chip" data-testid="wp-sync-status-revision">
        内容修订号（仅展示/乐观锁）：{{ revisionText }}
      </span>
      <span class="wp-sync-status-bar__chip" data-testid="wp-sync-status-generation">
        representation 代际：{{ generationText }}
      </span>
      <span class="wp-sync-status-bar__chip" data-testid="wp-sync-status-authority">
        授权模型：{{ authorityText }}
      </span>
      <span class="wp-sync-status-bar__chip" data-testid="wp-sync-status-bundle">
        bundle 摘要：{{ bundleDigestText }}
      </span>
      <span class="wp-sync-status-bar__chip" data-testid="wp-sync-status-sequence">
        application effective 序号：{{ effectiveSequenceText }}
      </span>
      <span class="wp-sync-status-bar__chip" data-testid="wp-sync-status-last-sync">
        最后同步：{{ lastSyncText }}
      </span>
    </div>

    <!-- 失败后的可执行动作披露：三个布尔逐字来自 verdict -->
    <div
      v-if="verdict !== null"
      class="wp-sync-status-bar__gates"
      data-testid="wp-sync-status-gates"
      :data-error-code="verdict.errorCode"
      :data-can-enter-editing="String(verdict.canEnterEditing)"
      :data-retryable="String(verdict.retryableOperation)"
      :data-can-forcesave="String(verdict.canForcesave)"
      :data-unregistered="String(verdict.unregistered)"
    >
      <span data-testid="wp-sync-gate-editing">
        返回编辑：{{ verdict.canEnterEditing ? '允许' : '禁止' }}
      </span>
      <span data-testid="wp-sync-gate-retry">
        重试回写：{{ verdict.retryableOperation ? '允许' : '禁止' }}
      </span>
      <span data-testid="wp-sync-gate-forcesave">
        强制保存：{{ verdict.canForcesave ? '允许' : '禁止' }}
      </span>
    </div>

    <div class="wp-sync-status-bar__actions">
      <el-button
        v-if="state === 'conflict'"
        size="small"
        type="warning"
        plain
        data-testid="wp-sync-status-open-conflicts"
        @click="emit('openConflicts')"
      >
        打开冲突面板
      </el-button>
      <el-button
        v-if="recoveryVisible"
        size="small"
        type="warning"
        plain
        data-testid="wp-sync-status-open-recovery"
        @click="emit('openRecovery')"
      >
        打开恢复面板
      </el-button>
      <el-button
        v-if="plainRetryVisible"
        size="small"
        plain
        data-testid="wp-sync-status-retry"
        @click="emit('retry')"
      >
        重试回写
      </el-button>
      <el-button
        size="small"
        plain
        data-testid="wp-sync-status-open-details"
        @click="emit('openDetails')"
      >
        查看详情
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject } from 'vue'

import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { WP_BRIDGE_STATE_TEXT } from './workpaperSyncBridgeMachine'
import type { WorkpaperSyncBridge } from './useWorkpaperSyncBridge'
import {
  WP_SYNC_ACTION_HINT,
  WP_SYNC_STATE_TONE,
  WP_SYNC_TRACE_GAP_PLACEHOLDER,
  WP_SYNC_WAIT_KIND,
  describeCloseArbitration,
  isCloseArbitrationVisible,
  shortDigest,
} from './workpaperSyncPresentation'

const props = withDefaults(
  defineProps<{
    /** Task 32 的桥实例：状态、文案、门控与追溯事实的唯一来源。 */
    bridge: WorkpaperSyncBridge
    /**
     * 合法接任者的 intent id。
     *
     * 🔴 桥的 `notifyCloseSuccessorApplied(id)` 只**校验**这个 id、不保存它，
     * 因此接任者标识只能由观测到它的宿主显式回传。缺失时渲染「尚未确定」，
     * 绝不编一个 id —— 那会让「有合法接任者」凭空成立。
     */
    closeSuccessorIntentId?: string | null
  }>(),
  { closeSuccessorIntentId: null },
)

const emit = defineEmits<{
  openConflicts: []
  openRecovery: []
  openDetails: []
  retry: []
}>()

// 🔴 必须在 setup 顶层取：`fmtAmount` 是 store 成员而非模块级导出，
// 写进函数体会静默失效，从 store 模块 import 它会让整页崩。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const state = computed(() => props.bridge.state.value)
const mode = computed(() => props.bridge.mode.value)
const feedback = computed(() => props.bridge.feedback.value)
const operation = computed(() => props.bridge.operation.value)
const descriptor = computed(() => props.bridge.descriptor.value)
const verdict = computed(() => props.bridge.lastError.value?.verdict ?? null)

const waitKind = computed(() => WP_SYNC_WAIT_KIND[state.value])

/** 失败基调**盖过**状态基调：一次真失败之后不允许留下任何成功色。 */
const tone = computed(() =>
  feedback.value.kind === 'error' ? 'danger' : WP_SYNC_STATE_TONE[state.value],
)

const closeArbitration = computed(() =>
  describeCloseArbitration(
    state.value,
    props.bridge.transitions.value,
    props.closeSuccessorIntentId,
  ),
)

/** 只在本会话真的发生过 close 仲裁时才占版面（枚举比较收在纯投影层）。 */
const closeArbitrationVisible = computed(() =>
  isCloseArbitrationVisible(closeArbitration.value),
)

/**
 * 阶段标签。两处强制前缀，各堵一种误读：
 *
 * * 失败时加「失败于：」—— 于是 `applied` 的文案也不可能被读成一句成功；
 * * 接任者代为完成时加「接任者代为完成：」—— `close_successor_applied` 的目标就是
 *   `applied`，不加前缀就与「我自己保存成功了」逐字同态，而 Task 34 明文要求
 *   successor 接任进展不得渲染成保存成功。
 */
const stageText = computed(() => {
  const text = WP_BRIDGE_STATE_TEXT[state.value]
  if (feedback.value.kind === 'error') return `失败于：${text}`
  if (closeArbitration.value.outcome === 'successor_applied') {
    return `接任者代为完成：${text}`
  }
  return text
})

const actionHint = computed(() => WP_SYNC_ACTION_HINT[state.value])

/** duplicate 的 requested → canonical。两个 id 必须同时可见。 */
const duplicateFold = computed<{ requested: string; canonical: string } | null>(() => {
  const snapshot = operation.value
  if (snapshot === null || snapshot.shape !== 'duplicate') return null
  return {
    requested: snapshot.requestedOperationId,
    canonical: snapshot.canonicalOperationId,
  }
})

const recoveryVisible = computed(
  () =>
    ['recovery_pending', 'recovery_claiming', 'recovery_download_only'].includes(state.value) ||
    props.bridge.recoveryCases.value.length > 0,
)

/**
 * 普通 retry 的门。三条同时成立：可重试裁决 + 确有 requested operation + 不在 recovery。
 *
 * AC 5.8 末句：nullable operation 的 recovery case 不得进入普通 retry。crash 发生在
 * forcesave 之前时 `requestedOperationId` 恒为 null，本门结构性地关着。
 */
const plainRetryVisible = computed(() => {
  if (['recovery_pending', 'recovery_claiming', 'recovery_download_only'].includes(state.value)) {
    return false
  }
  if (props.bridge.requestedOperationId.value === null) return false
  return verdict.value?.retryableOperation === true
})

const revisionText = computed(() => {
  const applied = operation.value?.resultRevision
  if (typeof applied === 'number') return String(applied)
  const server = descriptor.value?.serverAppliedRevision
  return typeof server === 'number' ? String(server) : WP_SYNC_TRACE_GAP_PLACEHOLDER
})

const generationText = computed(() => {
  const generation = descriptor.value?.representationGeneration
  return typeof generation === 'number' ? String(generation) : WP_SYNC_TRACE_GAP_PLACEHOLDER
})

const authorityText = computed(
  () => descriptor.value?.authorityModel ?? WP_SYNC_TRACE_GAP_PLACEHOLDER,
)

const bundleDigestText = computed(() =>
  shortDigest(
    operation.value?.definitionBundleSha256 ?? descriptor.value?.definitionBundleSha256 ?? null,
  ),
)

const effectiveSequenceText = computed(() => {
  const sequence = props.bridge.applicationEffectiveSequence.value
  return sequence === null ? WP_SYNC_TRACE_GAP_PLACEHOLDER : String(sequence)
})

const lastSyncText = computed(() => {
  const snapshot = operation.value
  const stamp =
    snapshot?.operationFinishedAt ?? snapshot?.durableAt ?? snapshot?.acceptedAt ?? null
  if (stamp === null) return WP_SYNC_TRACE_GAP_PLACEHOLDER
  return displayPrefs.fmtDateTime(stamp)
})

defineExpose({
  /** 只读投影，供页面级宿主与判据核对（每一项都逐字来自桥或纯投影表）。 */
  getPresentation: () => ({
    state: state.value,
    mode: mode.value,
    kind: feedback.value.kind,
    tone: tone.value,
    waitKind: waitKind.value,
    stageText: stageText.value,
    message: feedback.value.message,
    actionHint: actionHint.value,
    closeOutcome: closeArbitration.value.outcome,
    duplicateFold: duplicateFold.value,
    plainRetryVisible: plainRetryVisible.value,
  }),
})
</script>

<style scoped>
.wp-sync-status-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  background: #fafafa;
  border-left: 3px solid #dcdfe6;
}

.wp-sync-status-bar[data-tone='danger'] {
  border-left-color: #c45656;
}

.wp-sync-status-bar[data-tone='warning'] {
  border-left-color: #e6a23c;
}

.wp-sync-status-bar[data-tone='success'] {
  border-left-color: #529b2e;
}

.wp-sync-status-bar__head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.wp-sync-status-bar__message {
  font-weight: 600;
}

.wp-sync-status-bar[data-kind='error'] .wp-sync-status-bar__message {
  color: #c45656;
}

.wp-sync-status-bar__hint {
  color: #909399;
}

.wp-sync-status-bar__spinner {
  width: 10px;
  height: 10px;
  border: 2px solid #c0c4cc;
  border-top-color: transparent;
  border-radius: 50%;
  animation: wp-sync-spin 900ms linear infinite;
}

@keyframes wp-sync-spin {
  to {
    transform: rotate(360deg);
  }
}

.wp-sync-status-bar__row {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.wp-sync-status-bar__row--warn {
  color: #b88230;
}

.wp-sync-status-bar__label {
  flex: none;
  color: #909399;
}

.wp-sync-status-bar__trace,
.wp-sync-status-bar__gates {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: #909399;
}

.wp-sync-status-bar__chip {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.wp-sync-status-bar__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
