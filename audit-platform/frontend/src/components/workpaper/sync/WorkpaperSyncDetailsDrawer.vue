<!--
  WorkpaperSyncDetailsDrawer.vue — 追溯详情与两条独立 timeline

  spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
  Requirements: 8.7, 11.11
  Properties: P35 / P46 / P48

  ═══ 两条 timeline 必须分开 ═══

  operation timeline 与 recovery case timeline 走两个端点、渲染成两张表。
  合成一张「统一 timeline」就必须给 claim 之前的 recovery 事件编一个 operation id，
  而那正是 AC 5.8 与 P68 明令禁止的形态。

  ═══ rollback 只提交 opaque UUID ═══

  numeric revision 只作展示与 `expected_current_revision` 乐观锁。两个不同底稿都存在
  revision 1，用它拼 route 会在授权索引里撞成同一行（AC 8.7 / 10.6）。因此本抽屉的
  rollback 动作提交的是 `rollbackTarget.versionId`，且**同时**把 revision 作为乐观锁
  一起发；桥/API 层在发出前用 `isOpaqueUuid` 拦住任何非 UUID。

  ═══ 无读取面的追溯项显式留白 ═══

  `WP_SYNC_TRACE_GAPS` 里的每一项都渲染成占位符，绝不用另一个「长得像」的字段顶替。
-->
<template>
  <div
    v-if="visible"
    class="wp-sync-details"
    data-testid="wp-sync-details-drawer"
    :data-state="state"
  >
    <div class="wp-sync-details__mask" data-testid="wp-sync-details-mask" @click="onClose" />
    <aside
      class="wp-sync-details__panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wp-sync-details-title"
      tabindex="-1"
      @keydown.esc="onClose"
    >
      <header class="wp-sync-details__header">
        <h3 id="wp-sync-details-title" class="wp-sync-details__title">同步详情与追溯</h3>
        <button
          type="button"
          class="wp-sync-details__close"
          data-testid="wp-sync-details-close"
          aria-label="关闭详情"
          @click="onClose"
        >
          关闭
        </button>
      </header>

      <p
        v-if="drawerError !== null"
        class="wp-sync-details__error"
        data-testid="wp-sync-details-error"
        :data-code="drawerError.code"
      >
        {{ drawerError.message }}
      </p>

      <!-- ① 追溯事实（AC 11.11） -->
      <el-card shadow="never" data-testid="wp-sync-details-trace">
        <template #header>
          <span>追溯事实</span>
        </template>
        <table class="wp-sync-details__table">
          <tbody>
            <tr
              v-for="row in traceRows"
              :key="row.id"
              data-testid="wp-sync-details-trace-row"
              :data-row-id="row.id"
              :data-gap="String(row.gap)"
            >
              <th scope="row">{{ row.label }}</th>
              <td :class="row.numeric ? 'is-right' : ''">{{ row.value }}</td>
            </tr>
          </tbody>
        </table>
      </el-card>

      <!-- ② rollback：提交 opaque versionId，numeric revision 只作乐观锁 -->
      <el-card shadow="never" data-testid="wp-sync-details-rollback">
        <template #header>
          <span>回滚到历史内容版本</span>
        </template>
        <div class="wp-sync-details__rollback">
          <span data-testid="wp-sync-details-rollback-version">
            目标版本（不透明 UUID）：{{ rollbackTarget?.versionId ?? '未指定' }}
          </span>
          <span data-testid="wp-sync-details-rollback-revision">
            目标修订号（仅展示）：{{ rollbackTarget?.revision ?? '未指定' }}
          </span>
          <span data-testid="wp-sync-details-rollback-lock">
            乐观锁当前修订号：{{ expectedCurrentRevision }}
          </span>
          <el-button
            v-if="rollbackConfirming"
            size="small"
            type="danger"
            :loading="rollingBack"
            data-testid="wp-sync-details-rollback-confirm"
            @click="onRollbackConfirm"
          >
            确认回滚
          </el-button>
          <el-button
            v-else
            size="small"
            type="danger"
            plain
            :disabled="!rollbackTargetUsable"
            data-testid="wp-sync-details-rollback-request"
            @click="rollbackConfirming = true"
          >
            回滚到该版本
          </el-button>
          <el-button
            v-if="rollbackConfirming"
            size="small"
            plain
            data-testid="wp-sync-details-rollback-cancel"
            @click="rollbackConfirming = false"
          >
            取消
          </el-button>
        </div>
        <p
          v-if="!rollbackTargetUsable"
          class="wp-sync-details__hint"
          data-testid="wp-sync-details-rollback-hint"
          :data-reason="rollbackBlockReason"
        >
          {{ rollbackBlockText }}
        </p>
      </el-card>

      <!-- ③ operation timeline -->
      <el-card shadow="never" data-testid="wp-sync-details-operation-timeline">
        <template #header>
          <span>回写任务 timeline</span>
          <el-button
            size="small"
            plain
            :loading="loadingOperation"
            data-testid="wp-sync-details-load-operation-timeline"
            @click="onLoadOperationTimeline"
          >
            加载
          </el-button>
        </template>
        <p
          v-if="operationTimeline === null"
          class="wp-sync-details__hint"
          data-testid="wp-sync-details-operation-timeline-empty"
        >
          尚未加载回写任务事件。
        </p>
        <table v-else class="wp-sync-details__table">
          <thead>
            <tr>
              <th scope="col">流</th>
              <th scope="col" class="is-right">序号</th>
              <th scope="col">时间</th>
              <th scope="col">自</th>
              <th scope="col">至</th>
              <th scope="col">关联标识</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in operationTimeline.rows"
              :key="`${row.stream}-${row.sequenceNo}`"
              data-testid="wp-sync-details-operation-event"
              :data-stream="row.stream"
              :data-sequence="String(row.sequenceNo)"
            >
              <td>{{ streamText[row.stream] ?? row.stream }}</td>
              <td class="is-right">{{ row.sequenceNo }}</td>
              <td>{{ row.occurredAt === null ? '未记录' : displayPrefs.fmtDateTime(row.occurredAt) }}</td>
              <td>{{ row.fromState ?? '（无）' }}</td>
              <td>{{ row.toState ?? '（无）' }}</td>
              <td>{{ row.correlationId ?? '未投影' }}</td>
            </tr>
            <tr v-if="operationTimeline.rows.length === 0">
              <td colspan="6" data-testid="wp-sync-details-operation-timeline-none">
                该回写任务尚无事件
              </td>
            </tr>
          </tbody>
        </table>
      </el-card>

      <!-- ④ recovery case timeline（独立端点、独立表） -->
      <el-card shadow="never" data-testid="wp-sync-details-recovery-timeline">
        <template #header>
          <span>恢复项 timeline</span>
          <el-button
            size="small"
            plain
            :disabled="activeRecoveryCaseId === null"
            :loading="loadingRecovery"
            data-testid="wp-sync-details-load-recovery-timeline"
            @click="onLoadRecoveryTimeline"
          >
            加载
          </el-button>
        </template>
        <p
          v-if="activeRecoveryCaseId === null"
          class="wp-sync-details__hint"
          data-testid="wp-sync-details-recovery-timeline-absent"
        >
          当前没有恢复项，因此没有恢复 timeline（认领之前也不存在回写任务）。
        </p>
        <template v-else>
          <div class="wp-sync-details__recovery-head" data-testid="wp-sync-details-recovery-head">
            <span>恢复项：{{ activeRecoveryCaseId }}</span>
            <span data-testid="wp-sync-details-recovery-three-entities">
              三实体齐备：{{ recoveryTimeline?.hasThreeEntities === true ? '是' : '否' }}
            </span>
          </div>
          <p
            v-if="recoveryTimeline === null"
            class="wp-sync-details__hint"
            data-testid="wp-sync-details-recovery-timeline-empty"
          >
            尚未加载恢复项事件。
          </p>
          <table v-else class="wp-sync-details__table">
            <thead>
              <tr>
                <th scope="col" class="is-right">序号</th>
                <th scope="col">时间</th>
                <th scope="col">自</th>
                <th scope="col">至</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in recoveryTimeline.rows"
                :key="row.sequenceNo"
                data-testid="wp-sync-details-recovery-event"
                :data-sequence="String(row.sequenceNo)"
              >
                <td class="is-right">{{ row.sequenceNo }}</td>
                <td>{{ row.occurredAt === null ? '未记录' : displayPrefs.fmtDateTime(row.occurredAt) }}</td>
                <td>{{ row.fromState ?? '（无）' }}</td>
                <td>{{ row.toState ?? '（无）' }}</td>
              </tr>
              <tr v-if="recoveryTimeline.rows.length === 0">
                <td colspan="4" data-testid="wp-sync-details-recovery-timeline-none">
                  该恢复项尚无事件
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </el-card>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'

import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { describeBridgeFailure, type WorkpaperSyncBridge } from './useWorkpaperSyncBridge'
import { isOpaqueUuid } from './workpaperSyncDto'
import {
  WP_SYNC_TRACE_GAPS,
  WP_SYNC_TRACE_GAP_PLACEHOLDER,
  projectOperationTimeline,
  projectRecoveryTimeline,
  shortDigest,
} from './workpaperSyncPresentation'

const props = withDefaults(
  defineProps<{
    bridge: WorkpaperSyncBridge
    visible: boolean
    /** 乐观锁用的当前 numeric revision（仅作 expected-current，绝不拼 route）。 */
    expectedCurrentRevision: number
    /**
     * 回滚目标。`versionId` 必须是不透明 immutable UUID。
     *
     * 历史版本清单没有用户读取面，因此目标由宿主显式给；为 null 时按钮禁用并说明原因。
     */
    rollbackTarget?: { versionId: string; revision: number } | null
  }>(),
  { rollbackTarget: null },
)

const emit = defineEmits<{
  'update:visible': [boolean]
  rolledBack: [Record<string, unknown>]
  failed: [{ stage: string; code: string; message: string }]
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

interface Refusal {
  readonly code: string
  readonly message: string
}

const drawerError = ref<Refusal | null>(null)
const loadingOperation = ref(false)
const loadingRecovery = ref(false)
const rollbackConfirming = ref(false)
const rollingBack = ref(false)
const operationTimeline = ref<ReturnType<typeof projectOperationTimeline> | null>(null)
const recoveryTimeline = ref<ReturnType<typeof projectRecoveryTimeline> | null>(null)

const streamText: Readonly<Record<string, string>> = Object.freeze({
  operation: '回写任务',
  application: '内容应用',
  recovery_case: '恢复项',
  close_intent: '关闭意图',
})

const state = computed(() => props.bridge.state.value)
const descriptor = computed(() => props.bridge.descriptor.value)
const operation = computed(() => props.bridge.operation.value)
const rollbackTarget = computed(() => props.rollbackTarget)
const expectedCurrentRevision = computed(() => props.expectedCurrentRevision)
const activeRecoveryCaseId = computed(() => props.bridge.activeRecoveryCaseId.value)

/**
 * 回滚目标为什么不可用。
 *
 * 🔴 `not_opaque` 这一支是**本抽屉自己的**前置门，与 API 层的 `version_id_not_opaque`
 * 刻意**不共用码**：共用一个码就等于「删掉本层的门也看不出差别」——
 * API 层照样会抛同一个码，判据永远 GREEN。两层各一个码，两层各一条判据。
 */
const rollbackBlockReason = computed<'none' | 'absent' | 'not_opaque'>(() => {
  const target = rollbackTarget.value
  if (target === null) return 'absent'
  return isOpaqueUuid(target.versionId) ? 'none' : 'not_opaque'
})

const rollbackTargetUsable = computed(() => rollbackBlockReason.value === 'none')

const rollbackBlockText = computed(() => {
  if (rollbackBlockReason.value === 'absent') {
    return '未指定回滚目标：历史版本清单没有用户读取面，目标版本须由宿主显式给出。'
  }
  if (rollbackBlockReason.value === 'not_opaque') {
    return (
      '回滚目标不是不透明 immutable UUID：per-wp numeric revision 只能展示或作乐观锁，' +
      '不同底稿会有相同 revision，用它定位会撞到另一份内容。'
    )
  }
  return ''
})

interface TraceRow {
  readonly id: string
  readonly label: string
  readonly value: string
  readonly gap: boolean
  readonly numeric: boolean
}

function present(id: string, label: string, value: string | number | null, numeric = false): TraceRow {
  const text =
    value === null || value === undefined || String(value).trim() === ''
      ? WP_SYNC_TRACE_GAP_PLACEHOLDER
      : String(value)
  return { id, label, value: text, gap: text === WP_SYNC_TRACE_GAP_PLACEHOLDER, numeric }
}

/** 证据关联标识只能来自已加载的 operation 事件；没加载就是缺口，不猜。 */
const evidenceCorrelationId = computed<string | null>(() => {
  const rows = operationTimeline.value?.rows ?? []
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const correlation = rows[index].correlationId
    if (correlation !== null) return correlation
  }
  return null
})

/**
 * 追溯行。**先**摆有读取面的事实，**再**把已登记缺口逐条摆成占位符 ——
 * 缺口行永远不显示数字或摘要，判据据此断言没人拿相邻字段顶替。
 */
const traceRows = computed<readonly TraceRow[]>(() => {
  const d = descriptor.value
  const op = operation.value
  const rows: TraceRow[] = [
    present('content_revision', '内容修订号（仅展示/乐观锁）', op?.resultRevision ?? d?.serverAppliedRevision ?? null, true),
    present('content_version_id', '内容版本（不透明 UUID）', d?.contentVersionId ?? null),
    present('representation_id', 'representation 标识', d?.representationId ?? null),
    present('representation_generation', 'representation 代际', d?.representationGeneration ?? null, true),
    present('room_id', 'room 标识', d?.roomId ?? null),
    present('room_generation', 'room 代际', d?.generation ?? null, true),
    present('participant_id', 'participant 标识', d?.participantId ?? null),
    present('server_applied_revision', '服务端已应用基线', d?.serverAppliedRevision ?? null, true),
    present('client_confirmed_base_revision', '客户端已确认基线', d?.clientConfirmedBaseRevision ?? null, true),
    present('write_fence_epoch', '写栅栏 epoch', d?.writeFenceEpoch ?? null, true),
    present('refresh_required', '需重载编辑器确认新基线', state.value === 'refresh_required' ? '是' : '否'),
    present('canonical_application_id', '规范 application', props.bridge.canonicalApplicationId.value),
    present('application_effective_request_sequence', 'application effective 序号', props.bridge.applicationEffectiveSequence.value, true),
    present('result_artifact_sha256', '结果 artifact 摘要（发出侧）', shortDigest(d?.artifactSha256 ?? null)),
    present('definition_bundle_id', 'definition bundle 标识', op?.definitionBundleId ?? d?.definitionBundleId ?? null),
    present('definition_bundle_sha256', 'definition bundle 摘要', shortDigest(op?.definitionBundleSha256 ?? d?.definitionBundleSha256 ?? null)),
    present('authority_model', '授权模型', d?.authorityModel ?? null),
    present('authority_model_definition_sha256', '授权模型定义摘要', shortDigest(op?.authorityModelDefinitionSha256 ?? d?.authorityModelDefinitionSha256 ?? null)),
    present('evidence_correlation_id', '证据关联标识', evidenceCorrelationId.value),
  ]
  for (const gap of WP_SYNC_TRACE_GAPS) {
    rows.push({
      id: gap.id,
      label: `${gap.label}（${gap.reason}）`,
      value: WP_SYNC_TRACE_GAP_PLACEHOLDER,
      gap: true,
      numeric: false,
    })
  }
  return rows
})

function describe(stage: string, error: unknown): Refusal {
  const described = describeBridgeFailure(stage, error)
  return { code: described.errorCode, message: described.message }
}

function fail(stage: string, error: unknown): void {
  const refusal = describe(stage, error)
  drawerError.value = refusal
  emit('failed', { stage, ...refusal })
}

function onClose(): void {
  rollbackConfirming.value = false
  emit('update:visible', false)
}

async function onLoadOperationTimeline(): Promise<void> {
  drawerError.value = null
  loadingOperation.value = true
  try {
    operationTimeline.value = projectOperationTimeline(await props.bridge.fetchTimeline())
  } catch (error) {
    operationTimeline.value = null
    fail('get_timeline', error)
  } finally {
    loadingOperation.value = false
  }
}

async function onLoadRecoveryTimeline(): Promise<void> {
  const caseId = activeRecoveryCaseId.value
  if (caseId === null) return
  drawerError.value = null
  loadingRecovery.value = true
  try {
    recoveryTimeline.value = projectRecoveryTimeline(
      await props.bridge.fetchRecoveryCaseTimeline(caseId),
    )
  } catch (error) {
    recoveryTimeline.value = null
    fail('recovery_case_timeline', error)
  } finally {
    loadingRecovery.value = false
  }
}

/** 二次确认之后才真的发。提交的是 opaque UUID，numeric revision 只进乐观锁字段。 */
async function onRollbackConfirm(): Promise<void> {
  const target = rollbackTarget.value
  if (target === null || !rollbackTargetUsable.value) {
    // 按钮已 disabled，但程序化调用必须同样被拦，且写出**本层专属**的码。
    drawerError.value = {
      code: 'details_rollback_target_not_opaque',
      message: rollbackBlockText.value || '没有可回滚的目标版本',
    }
    emit('failed', { stage: 'rollback_version', ...drawerError.value })
    return
  }
  drawerError.value = null
  rollingBack.value = true
  try {
    const outcome = await props.bridge.rollbackVersion({
      versionId: target.versionId,
      expectedCurrentRevision: expectedCurrentRevision.value,
      confirmed: true,
    })
    rollbackConfirming.value = false
    emit('rolledBack', outcome)
  } catch (error) {
    fail('rollback_version', error)
  } finally {
    rollingBack.value = false
  }
}

defineExpose({
  /**
   * 可 await 的回滚提交入口（与按钮走同一个 `onRollbackConfirm`）。
   *
   * 门若只长在 `:disabled` 上，程序化调用就能绕过；判据据此直接调它验两层门。
   */
  submitRollback: onRollbackConfirm,
  /** 判据用的只读投影。 */
  getTraceability: () => ({
    rows: traceRows.value,
    gapIds: traceRows.value.filter((row) => row.gap).map((row) => row.id),
    operationEventCount: operationTimeline.value?.rows.length ?? null,
    recoveryEventCount: recoveryTimeline.value?.rows.length ?? null,
    evidenceCorrelationId: evidenceCorrelationId.value,
  }),
})
</script>

<style scoped>
.wp-sync-details {
  position: fixed;
  inset: 0;
  z-index: 2300;
  font-size: var(--wp-font-size, 13px);
}

.wp-sync-details__mask {
  position: absolute;
  inset: 0;
  background: rgb(0 0 0 / 25%);
}

.wp-sync-details__panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(720px, 96vw);
  padding: 16px 20px;
  overflow: auto;
  background: #fff;
}

.wp-sync-details__header {
  display: flex;
  align-items: center;
}

.wp-sync-details__title {
  margin: 0;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.wp-sync-details__close {
  margin-left: auto;
  padding: 2px 10px;
  font-size: var(--wp-font-size, 13px);
  cursor: pointer;
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
}

.wp-sync-details__table {
  width: 100%;
  font-size: var(--wp-font-size, 13px);
  border-collapse: collapse;
}

.wp-sync-details__table th,
.wp-sync-details__table td {
  padding: 4px 8px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid #ebeef5;
  word-break: break-all;
}

.wp-sync-details__table th {
  width: 42%;
  font-weight: 400;
  color: #909399;
}

.wp-sync-details__table td.is-right,
.wp-sync-details__table th.is-right {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.wp-sync-details__table tr[data-gap='true'] td {
  color: #b88230;
}

.wp-sync-details__rollback,
.wp-sync-details__recovery-head {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  color: #909399;
}

.wp-sync-details__error {
  margin: 0;
  color: #c45656;
}

.wp-sync-details__hint {
  margin: 4px 0;
  color: #909399;
}
</style>
