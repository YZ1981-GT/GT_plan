<!--
  WorkpaperSyncContentRefreshBanner.vue — commit 后内容更新的**可见刷新条**

  spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 35
  Requirements: 11.9, 11.10, 13.1, 13.3, 13.4
  Properties: P52 / P53 / P54（本组件是它们的 DOM 侧判据面）

  ═══ 它渲染什么 ═══

  协调器（`useWorkpaperContentRefresh`）的六个可见状态，以及三个已落地状态各自的
  显式动作：

  * `deferred_dirty` —— 本地有未保存修改，服务端已有更新的修订号。**不静默覆盖**，
    只给「加载服务端最新版本」与「保留本地修改」两个显式选择。
  * `refresh_failed` —— 重载失败。给「重试加载」，并逐字说明「已提交的内容未受影响」。
  * `event_rejected` —— 事件形态异常。**不给重试**（重放同一条坏事件只会再坏一次），
    只把它变成可见事实等下一条事件。

  ═══ 三条边界 ═══

  1. **零金额**：本条只显示 revision（整数序号）与状态文案，不显示任何金额，
     因此不引 `displayPrefs`。
  2. **零请求**：所有动作都是调协调器的方法，而协调器本身没有 api 面 ——
     「刷新失败又制造一个新 revision」在结构上不可达。
  3. **文案唯一真源** = `WP_CONTENT_REFRESH_STATUS_TEXT` / `..._ACTION_HINT` 两张表
     （失败时头条换成协调器记住的失败消息）。组件内不写第二份状态文案。
-->
<template>
  <div
    class="wp-content-refresh"
    data-testid="wp-content-refresh"
    :data-status="status"
    :data-kind="feedback.kind"
    role="status"
    aria-live="polite"
  >
    <div class="wp-content-refresh__head">
      <span
        v-if="feedback.kind === 'progress'"
        class="wp-content-refresh__spinner"
        data-testid="wp-content-refresh-spinner"
        aria-hidden="true"
      />
      <span class="wp-content-refresh__badge" data-testid="wp-content-refresh-badge">
        {{ statusText }}
      </span>
      <span class="wp-content-refresh__message" data-testid="wp-content-refresh-message">
        {{ feedback.message }}
      </span>
      <span
        v-if="feedback.hint !== ''"
        class="wp-content-refresh__hint"
        data-testid="wp-content-refresh-hint"
      >
        {{ feedback.hint }}
      </span>
    </div>

    <!-- 追溯：已加载 / 待加载 / 本次事件的不可变身份 -->
    <div class="wp-content-refresh__trace" data-testid="wp-content-refresh-trace">
      <span class="wp-content-refresh__chip" data-testid="wp-content-refresh-applied">
        已加载修订号：{{ appliedText }}
      </span>
      <span class="wp-content-refresh__chip" data-testid="wp-content-refresh-pending">
        待加载修订号：{{ pendingText }}
      </span>
      <span class="wp-content-refresh__chip" data-testid="wp-content-refresh-version">
        内容版本：{{ contentVersionText }}
      </span>
      <span class="wp-content-refresh__chip" data-testid="wp-content-refresh-reason">
        提交原因：{{ reasonText }}
      </span>
      <span
        v-if="failureCode !== ''"
        class="wp-content-refresh__chip"
        data-testid="wp-content-refresh-failure-code"
      >
        失败码：{{ failureCode }}
      </span>
    </div>

    <div class="wp-content-refresh__actions">
      <!--
        🔴 三个按钮都**没有** `:disabled` 绑定，因为「加载中」时它们一个都不渲染：
        `acceptVisible` 要求 `deferred_dirty`、`retryVisible` 要求 `refresh_failed`，
        两者与 `refreshing` 互斥。加一个 `:disabled="status==='refreshing'"` 会是一段
        永不为真的绑定（死代码），而死代码的守卫必然恒绿。
      -->
      <button
        v-if="acceptVisible"
        type="button"
        class="wp-content-refresh__button"
        data-testid="wp-content-refresh-accept"
        @click="onAccept"
      >
        加载服务端最新版本
      </button>
      <button
        v-if="acceptVisible"
        type="button"
        class="wp-content-refresh__button"
        data-testid="wp-content-refresh-dismiss"
        @click="onDismiss"
      >
        保留本地修改
      </button>
      <button
        v-if="retryVisible"
        type="button"
        class="wp-content-refresh__button"
        data-testid="wp-content-refresh-retry"
        @click="onRetry"
      >
        重试加载
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import {
  WP_CONTENT_REFRESH_STATUS_TEXT,
  type WorkpaperContentRefresh,
} from './workpaperSyncContentRefresh'

const props = defineProps<{
  /** Task 35 的协调器实例：状态、文案、待办 revision 与三个动作都在它上面。 */
  refresh: WorkpaperContentRefresh
}>()

const emit = defineEmits<{
  /** 一次真实的 reload 结束（成功或失败），供宿主做自己的联动。 */
  refreshed: [{ status: string; revision: number | null }]
  /** 用户选择保留本地修改。 */
  dismissed: [{ pendingRevision: number | null }]
}>()

const status = computed(() => props.refresh.status.value)
const feedback = computed(() => props.refresh.feedback.value)
const statusText = computed(() => WP_CONTENT_REFRESH_STATUS_TEXT[status.value])

const UNAVAILABLE = '—'

const appliedText = computed(() => {
  const revision = props.refresh.appliedRevision.value
  return revision === null ? UNAVAILABLE : String(revision)
})

const pendingText = computed(() => {
  const revision = props.refresh.pendingRevision.value
  return revision === null ? UNAVAILABLE : String(revision)
})

const contentVersionText = computed(
  () => props.refresh.lastUpdate.value?.contentVersionId ?? UNAVAILABLE,
)

const reasonText = computed(() => props.refresh.lastUpdate.value?.reason ?? UNAVAILABLE)

const failureCode = computed(() => props.refresh.lastFailure.value?.errorCode ?? '')

/**
 * 「加载最新版本 / 保留本地修改」只在 dirty 暂缓时出现。
 *
 * 🔴 刷新失败时**不**出现：那时本地未必 dirty，出现两个选择会让用户以为
 * 「保留本地修改」能解决一次加载失败。失败走的是「重试加载」。
 */
const acceptVisible = computed(
  () => status.value === 'deferred_dirty' && props.refresh.pendingRevision.value !== null,
)

/**
 * 「重试加载」只在**刷新**失败时出现。
 *
 * 事件形态失败（`event_rejected`）的 `retryable` 是 `false`，因此本门关着 ——
 * 重放同一条坏事件只会再坏一次，新事实只能由下一条事件带来。
 */
const retryVisible = computed(
  () =>
    status.value === 'refresh_failed' &&
    props.refresh.lastFailure.value?.retryable === true &&
    props.refresh.pendingRevision.value !== null,
)

async function onAccept(): Promise<void> {
  const outcome = await props.refresh.acceptPending()
  emit('refreshed', { status: props.refresh.status.value, revision: outcome.revision })
}

async function onRetry(): Promise<void> {
  const outcome = await props.refresh.retry()
  emit('refreshed', { status: props.refresh.status.value, revision: outcome.revision })
}

function onDismiss(): void {
  const pending = props.refresh.pendingRevision.value
  props.refresh.dismissPending()
  emit('dismissed', { pendingRevision: pending })
}

defineExpose({
  /** 只读投影，供页面级宿主与判据核对（每一项都逐字来自协调器或文案表）。 */
  getPresentation: () => ({
    status: status.value,
    kind: feedback.value.kind,
    statusText: statusText.value,
    message: feedback.value.message,
    hint: feedback.value.hint,
    appliedRevision: props.refresh.appliedRevision.value,
    pendingRevision: props.refresh.pendingRevision.value,
    failureCode: failureCode.value,
    acceptVisible: acceptVisible.value,
    retryVisible: retryVisible.value,
  }),
})
</script>

<style scoped>
.wp-content-refresh {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  background: #fafafa;
  border-left: 3px solid #dcdfe6;
}

.wp-content-refresh[data-kind='warning'] {
  border-left-color: #e6a23c;
  background: #fdf6ec;
}

.wp-content-refresh[data-kind='error'] {
  border-left-color: #c45656;
  background: #fef0f0;
}

.wp-content-refresh[data-kind='success'] {
  border-left-color: #529b2e;
}

.wp-content-refresh__head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.wp-content-refresh__badge {
  flex: none;
  padding: 1px 6px;
  color: #606266;
  background: #ffffff;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
}

.wp-content-refresh__message {
  font-weight: 600;
}

.wp-content-refresh[data-kind='error'] .wp-content-refresh__message {
  color: #c45656;
}

.wp-content-refresh__hint {
  color: #909399;
}

.wp-content-refresh__spinner {
  width: 10px;
  height: 10px;
  border: 2px solid #c0c4cc;
  border-top-color: transparent;
  border-radius: 50%;
  animation: wp-content-refresh-spin 900ms linear infinite;
}

@keyframes wp-content-refresh-spin {
  to {
    transform: rotate(360deg);
  }
}

.wp-content-refresh__trace {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: #909399;
}

.wp-content-refresh__chip {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.wp-content-refresh__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.wp-content-refresh__button {
  padding: 3px 10px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  cursor: pointer;
  background: #ffffff;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
}

.wp-content-refresh__button:disabled {
  color: #c0c4cc;
  cursor: not-allowed;
}
</style>
