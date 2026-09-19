<!--
  WorkpaperSyncRecoveryPanel.vue — callback recovery case 的认领 / 仅下载面板

  spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
  Requirements: 5.8, 11.6, 11.11
  Properties: P46（recovery 三态与 operation 流分离）/ P48

  ═══ 四条不得违反的边界 ═══

  1. **list 成功之前什么都不显示**。候选 prior confirmation、bundle 摘要与阻断原因
     都在 `listRecoveryCases()` 返回之后才渲染 —— 服务端的 authorization-first list
     是唯一的可见性门（AC 5.8 / 10.6），面板不得先画一个「可能有恢复项」的空壳。
  2. **claim 之前三实体全空且不提供普通重试**。本文件**根本没有** retry 入口
     （结构判据会核对源码里不出现 `retryOperation`）——
     AC 5.8 末句：nullable operation 的 case 不得进入普通 operation retry。
  3. **claim 成功后三实体同时出现，且跟踪的是原 operation**。三实体取自
     `getRecoveryCaseTimeline` 的 `recovery_request_id / claimed_application_id /
     claimed_operation_id`（claim 的 202 回执里没有 shape，桥也没保存 request id），
     并与桥的 `requestedOperationId` 交叉核对，不一致就可见地失败。
  4. **download-only 永不显示「回写完成」**。它的成功文案是「仅下载，未执行结构化回写」，
     判据同时断言整个面板文本不含「回写完成」。

  ═══ 显式 scope 的自证 ═══

  桥不导出自己的 project/wp/entry，因此 scope 由 prop 显式给出并渲染。为避免
  「显示的 scope 与桥实际用的 scope 不是一回事」这种沉默谎言，本组件用桥的
  `modeStorageKey`（形态 `workpaper-sync-mode:{entry}:{wp}:{sheet}`）反查 entry/wp
  做一次交叉核对。project 段不在该键里，无法核对 —— 已登记。
-->
<template>
  <el-card
    shadow="never"
    class="wp-sync-recovery"
    data-testid="wp-sync-recovery-panel"
    :data-listed="String(listed)"
    :data-case-count="String(cases.length)"
  >
    <template #header>
      <div class="wp-sync-recovery__header">
        <span class="wp-sync-recovery__title">回写恢复项</span>
        <el-tag size="small" :type="listed ? 'warning' : 'info'" data-testid="wp-sync-recovery-state-tag">
          {{ listed ? `已列出 ${cases.length} 项` : '尚未查询' }}
        </el-tag>
        <el-button
          size="small"
          plain
          :loading="listing"
          data-testid="wp-sync-recovery-list"
          @click="onList"
        >
          查询恢复项
        </el-button>
      </div>
    </template>

    <!-- 显式 scope 披露（AC 10.6：list/claim/download-only 必带 project/wp/entry + room/代际） -->
    <div class="wp-sync-recovery__scope" data-testid="wp-sync-recovery-scope">
      <span data-testid="wp-sync-recovery-scope-project">项目：{{ scope.projectId }}</span>
      <span data-testid="wp-sync-recovery-scope-wp">底稿：{{ scope.wpId }}</span>
      <span data-testid="wp-sync-recovery-scope-entry">条目：{{ scope.entryId }}</span>
      <span data-testid="wp-sync-recovery-scope-room">room：{{ roomId }}</span>
      <span data-testid="wp-sync-recovery-scope-generation">代际：{{ generation }}</span>
    </div>

    <p
      v-if="scopeDrift !== null"
      class="wp-sync-recovery__error"
      data-testid="wp-sync-recovery-scope-drift"
    >
      {{ scopeDrift }}
    </p>

    <p
      v-if="panelError !== null"
      class="wp-sync-recovery__error"
      data-testid="wp-sync-recovery-error"
      :data-code="panelError.code"
    >
      {{ panelError.message }}
    </p>

    <p
      v-if="!listed"
      class="wp-sync-recovery__hint"
      data-testid="wp-sync-recovery-not-listed"
    >
      尚未通过授权查询恢复项：候选基线、bundle 摘要与阻断原因均在服务端授权列出后才显示。
    </p>

    <p
      v-else-if="cases.length === 0"
      class="wp-sync-recovery__hint"
      data-testid="wp-sync-recovery-empty"
    >
      当前 room / 代际下没有可处理的恢复项。
    </p>

    <div
      v-for="item in cases"
      v-else
      :key="item.caseId"
      class="wp-sync-recovery__case"
      data-testid="wp-sync-recovery-case"
      :data-case-id="item.caseId"
      :data-case-state="item.state"
      :data-reason="item.reason"
      :data-blocked="String(blockingOf(item).length > 0)"
      :data-entities-present="String(entitiesOf(item).presentCount)"
    >
      <div class="wp-sync-recovery__case-head">
        <el-tag size="small" type="warning" data-testid="wp-sync-recovery-case-state">
          {{ stateText[item.state] ?? item.state }}
        </el-tag>
        <span data-testid="wp-sync-recovery-case-reason">{{ reasonText[item.reason] ?? item.reason }}</span>
        <span class="wp-sync-recovery__id">{{ item.caseId }}</span>
      </div>

      <!-- 三实体：claim 前逐项「尚未创建」 -->
      <div class="wp-sync-recovery__entities" data-testid="wp-sync-recovery-entities">
        <span
          v-for="row in entitiesOf(item).rows"
          :key="row.id"
          :data-testid="`wp-sync-recovery-entity-${row.id}`"
        >
          {{ row.label }}：{{ row.value }}
        </span>
      </div>

      <!-- claim 成功后的三实体（取自 recovery case timeline，交叉核对原 operation） -->
      <div
        v-if="claimResult !== null && claimResult.caseId === item.caseId"
        class="wp-sync-recovery__claimed"
        data-testid="wp-sync-recovery-claimed"
        :data-has-three-entities="String(claimResult.hasThreeEntities)"
        :data-tracked-operation="claimResult.trackedOperationId"
      >
        <span data-testid="wp-sync-recovery-claimed-request">
          恢复保存请求：{{ claimResult.recoveryRequestId ?? '未投影' }}
        </span>
        <span data-testid="wp-sync-recovery-claimed-application">
          内容应用：{{ claimResult.claimedApplicationId ?? '未投影' }}
        </span>
        <span data-testid="wp-sync-recovery-claimed-operation">
          回写任务：{{ claimResult.claimedOperationId ?? '未投影' }}
        </span>
        <span data-testid="wp-sync-recovery-claimed-tracked">
          仍跟踪原回写任务：{{ claimResult.trackedOperationId }}
        </span>
      </div>

      <!-- 候选 prior confirmation + 宿主提供的冻结 bundle 摘要 -->
      <table class="wp-sync-recovery__table">
        <caption class="wp-sync-recovery__caption">
          候选既有 descriptor 确认（claim 只能引用同 room/代际的其中一条）
        </caption>
        <thead>
          <tr>
            <th scope="col">选择</th>
            <th scope="col">确认标识</th>
            <th scope="col">participant</th>
            <th scope="col">内容版本</th>
            <th scope="col">确认时间</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="candidate in item.candidatePriorConfirmations"
            :key="candidate.confirmationId"
            data-testid="wp-sync-recovery-candidate"
            :data-confirmation-id="candidate.confirmationId"
          >
            <td>
              <input
                type="radio"
                :name="`wp-sync-recovery-candidate-${item.caseId}`"
                :value="candidate.confirmationId"
                :checked="selectedConfirmation[item.caseId] === candidate.confirmationId"
                :data-testid="`wp-sync-recovery-pick-${candidate.confirmationId}`"
                aria-label="选择该候选确认作为恢复基线"
                @change="selectedConfirmation = { ...selectedConfirmation, [item.caseId]: candidate.confirmationId }"
              />
            </td>
            <td>{{ candidate.confirmationId }}</td>
            <td>{{ candidate.participantId }}</td>
            <td>{{ candidate.contentVersionId }}</td>
            <td>{{ candidate.confirmedAt === null ? '未记录' : displayPrefs.fmtDateTime(candidate.confirmedAt) }}</td>
          </tr>
          <tr v-if="item.candidatePriorConfirmations.length === 0">
            <td colspan="5" data-testid="wp-sync-recovery-no-candidate">
              没有可作合法基线的既有确认
            </td>
          </tr>
        </tbody>
      </table>

      <div class="wp-sync-recovery__bundle" data-testid="wp-sync-recovery-bundle">
        <span data-testid="wp-sync-recovery-bundle-digest">
          冻结 definition bundle 摘要（由宿主提供）：{{ bundleDigestText }}
        </span>
        <span data-testid="wp-sync-recovery-fence">
          代际 / 写栅栏：{{ claimFence === null ? '未提供' : `${claimFence.expectedGeneration} / ${claimFence.expectedWriteFence}` }}
        </span>
      </div>

      <!-- 阻断原因：全部由可观测事实推导，服务端 list 刻意不返回 blocking_reason -->
      <ul
        v-if="blockingOf(item).length > 0"
        class="wp-sync-recovery__blocking"
        data-testid="wp-sync-recovery-blocking"
      >
        <li
          v-for="reason in blockingOf(item)"
          :key="reason"
          data-testid="wp-sync-recovery-blocking-reason"
        >
          {{ reason }}
        </li>
      </ul>

      <div class="wp-sync-recovery__actions">
        <el-button
          v-if="item.actions.claim"
          size="small"
          type="primary"
          plain
          :disabled="!canClaim(item)"
          :loading="claiming === item.caseId"
          :data-testid="`wp-sync-recovery-claim-${item.caseId}`"
          @click="onClaim(item)"
        >
          认领恢复
        </el-button>
        <el-button
          v-if="item.actions.downloadOnly"
          size="small"
          plain
          :loading="terminating === item.caseId"
          :data-testid="`wp-sync-recovery-download-only-${item.caseId}`"
          @click="onDownloadOnly(item)"
        >
          仅下载并终结
        </el-button>
      </div>

      <!-- download-only 结果：显式声明未执行结构化回写 -->
      <div
        v-if="downloadOnly !== null && downloadOnly.caseId === item.caseId"
        class="wp-sync-recovery__download"
        data-testid="wp-sync-recovery-download-result"
        :data-claim-issued="String(downloadOnly.claim !== '')"
      >
        <span data-testid="wp-sync-recovery-download-note">
          已仅下载并终结该恢复项，未执行结构化回写；请求 / 内容应用 / 回写任务三者均未创建。
        </span>
        <el-button
          size="small"
          plain
          :data-testid="`wp-sync-recovery-download-artifact-${item.caseId}`"
          @click="onDownloadArtifact(item)"
        >
          下载已保存文件
        </el-button>
        <span
          v-if="downloadOnly.artifact !== null"
          data-testid="wp-sync-recovery-download-artifact-info"
        >
          文件摘要 {{ shortDigest(downloadOnly.artifact.artifactSha256) }} ·
          {{ downloadOnly.artifact.documentType }} ·
          {{ downloadOnly.artifact.sizeBytes }} 字节
        </span>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'

import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { describeBridgeFailure, type WorkpaperSyncBridge } from './useWorkpaperSyncBridge'
import { WP_SYNC_MODE_KEY_PREFIX } from './workpaperSyncModeStorage'
import type { WorkpaperSyncRecoveryArtifact, WorkpaperSyncRecoveryCase } from './workpaperSyncDto'
import {
  WP_SYNC_RECOVERY_REASON_TEXT,
  WP_SYNC_RECOVERY_STATE_TEXT,
  WP_SYNC_TRACE_GAP_PLACEHOLDER,
  deriveRecoveryBlocking,
  describeRecoveryEntities,
  projectRecoveryTimeline,
  shortDigest,
  type WorkpaperSyncClaimFence,
} from './workpaperSyncPresentation'

const props = withDefaults(
  defineProps<{
    bridge: WorkpaperSyncBridge
    /** 显式 project/wp/entry —— 桥不导出自己的 scope，故由宿主给并在此披露。 */
    scope: { projectId: string; wpId: string; entryId: string }
    roomId: string
    generation: number
    /**
     * claim 需要的冻结身份。
     *
     * 🔴 服务端 list 端点刻意零业务内容（不返回 bundle digest），故这些值只能由宿主
     * 从既有 descriptor 冻结身份里给。为 null 时 claim 一律禁用并给出阻断原因，
     * **不得**用一个「看起来合理」的摘要顶替。
     */
    claimFence?: WorkpaperSyncClaimFence | null
  }>(),
  { claimFence: null },
)

const emit = defineEmits<{
  listed: [{ count: number }]
  claimed: [{ caseId: string; operationId: string }]
  downloadOnly: [{ caseId: string }]
  failed: [{ stage: string; code: string; message: string }]
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

interface Refusal {
  readonly code: string
  readonly message: string
}

const listed = ref(false)
const listing = ref(false)
const claiming = ref<string | null>(null)
const terminating = ref<string | null>(null)
const panelError = ref<Refusal | null>(null)
const selectedConfirmation = ref<Record<string, string>>({})
const claimResult = ref<{
  readonly caseId: string
  readonly recoveryRequestId: string | null
  readonly claimedApplicationId: string | null
  readonly claimedOperationId: string | null
  readonly hasThreeEntities: boolean
  readonly trackedOperationId: string
} | null>(null)
const downloadOnly = ref<{
  readonly caseId: string
  readonly claim: string
  readonly artifact: WorkpaperSyncRecoveryArtifact | null
} | null>(null)

const reasonText = WP_SYNC_RECOVERY_REASON_TEXT
const stateText = WP_SYNC_RECOVERY_STATE_TEXT

const cases = computed(() => props.bridge.recoveryCases.value)
const claimFence = computed(() => props.claimFence)

const bundleDigestText = computed(() =>
  props.claimFence === null
    ? '未提供'
    : shortDigest(props.claimFence.expectedDefinitionBundleSha256),
)

/**
 * 显式 scope 与桥实际 scope 的交叉核对。
 *
 * `modeStorageKey` 是桥按自己的 `entryId/wpId/sheetKey` 现算的，因此它是一处**真**的
 * 观测面。project 段不在键里 —— 已登记，无法核对。
 */
const scopeDrift = computed<string | null>(() => {
  const key = props.bridge.modeStorageKey.value
  if (!key.startsWith(WP_SYNC_MODE_KEY_PREFIX)) {
    return `桥的模式键形态异常（${key}），无法核对显式 scope`
  }
  const rest = key.slice(WP_SYNC_MODE_KEY_PREFIX.length)
  const segments = rest.split(':')
  if (segments.length < 3) {
    return `桥的模式键段数异常（${key}），无法核对显式 scope`
  }
  const bridgeWp = segments[segments.length - 2]
  const bridgeEntry = segments.slice(0, segments.length - 2).join(':')
  const drift: string[] = []
  if (bridgeEntry !== props.scope.entryId) {
    drift.push(`条目（面板 ${props.scope.entryId} ≠ 桥 ${bridgeEntry}）`)
  }
  if (bridgeWp !== props.scope.wpId) {
    drift.push(`底稿（面板 ${props.scope.wpId} ≠ 桥 ${bridgeWp}）`)
  }
  if (drift.length === 0) return null
  return `显式 scope 与桥实际 scope 不一致：${drift.join('、')} —— 恢复动作已停用`
})

function describe(stage: string, error: unknown): Refusal {
  const described = describeBridgeFailure(stage, error)
  return { code: described.errorCode, message: described.message }
}

function fail(stage: string, error: unknown): void {
  const refusal = describe(stage, error)
  panelError.value = refusal
  emit('failed', { stage, ...refusal })
}

function entitiesOf(item: WorkpaperSyncRecoveryCase) {
  return describeRecoveryEntities(item)
}

function blockingOf(item: WorkpaperSyncRecoveryCase): readonly string[] {
  const derived = deriveRecoveryBlocking(item, claimFence.value)
  if (scopeDrift.value !== null) return [scopeDrift.value, ...derived]
  return derived
}

function canClaim(item: WorkpaperSyncRecoveryCase): boolean {
  if (scopeDrift.value !== null) return false
  if (blockingOf(item).length > 0) return false
  return typeof selectedConfirmation.value[item.caseId] === 'string'
}

/** authorization-first list —— 面板的唯一可见性门。 */
async function onList(): Promise<void> {
  panelError.value = null
  listing.value = true
  try {
    const result = await props.bridge.listRecoveryCases({
      roomId: props.roomId,
      generation: props.generation,
    })
    listed.value = true
    emit('listed', { count: result.length })
  } catch (error) {
    listed.value = false
    fail('list_recovery_cases', error)
  } finally {
    listing.value = false
  }
}

async function onClaim(item: WorkpaperSyncRecoveryCase): Promise<void> {
  const fence = claimFence.value
  const confirmationId = selectedConfirmation.value[item.caseId]
  if (fence === null || typeof confirmationId !== 'string') {
    panelError.value = {
      code: 'recovery_claim_gate_closed',
      message: blockingOf(item).join('；') || '请先选择一条候选确认作为恢复基线',
    }
    return
  }
  panelError.value = null
  claiming.value = item.caseId
  try {
    await props.bridge.claimRecoveryCase({
      caseId: item.caseId,
      roomId: props.roomId,
      participantId: fence.participantId,
      priorConfirmationId: confirmationId,
      expectedGeneration: fence.expectedGeneration,
      expectedWriteFence: fence.expectedWriteFence,
      expectedDefinitionBundleSha256: fence.expectedDefinitionBundleSha256,
      expectedCurrentRevision: fence.expectedCurrentRevision,
    })
  } catch (error) {
    claiming.value = null
    fail('claim_recovery_case', error)
    return
  }
  // claim 已成功：三实体确实存在，但 claim 的 202 回执与桥都没有 request id。
  // 唯一带全三者的读取面是 recovery case timeline，故从它取（且不猜任何一项）。
  const tracked = props.bridge.requestedOperationId.value
  try {
    const timeline = await props.bridge.fetchRecoveryCaseTimeline(item.caseId)
    const projected = projectRecoveryTimeline(timeline)
    if (tracked === null || projected.claimedOperationId !== tracked) {
      claiming.value = null
      panelError.value = {
        code: 'recovery_claim_operation_drift',
        message:
          `claim 后 timeline 的回写任务 ${projected.claimedOperationId ?? '（空）'} 与桥跟踪的 ` +
          `${tracked ?? '（空）'} 不一致 —— 认领必须沿同一 operation 推进`,
      }
      emit('failed', {
        stage: 'claim_recovery_case',
        code: 'recovery_claim_operation_drift',
        message: panelError.value.message,
      })
      return
    }
    claimResult.value = {
      caseId: item.caseId,
      recoveryRequestId: projected.recoveryRequestId,
      claimedApplicationId: projected.claimedApplicationId,
      claimedOperationId: projected.claimedOperationId,
      hasThreeEntities: projected.hasThreeEntities,
      trackedOperationId: tracked,
    }
    emit('claimed', { caseId: item.caseId, operationId: tracked })
  } catch (error) {
    fail('recovery_case_timeline', error)
  } finally {
    claiming.value = null
  }
}

async function onDownloadOnly(item: WorkpaperSyncRecoveryCase): Promise<void> {
  panelError.value = null
  terminating.value = item.caseId
  try {
    const claim = await props.bridge.terminateRecoveryDownloadOnly(item.caseId)
    downloadOnly.value = { caseId: item.caseId, claim, artifact: null }
    emit('downloadOnly', { caseId: item.caseId })
  } catch (error) {
    fail('terminate_download_only', error)
  } finally {
    terminating.value = null
  }
}

async function onDownloadArtifact(item: WorkpaperSyncRecoveryCase): Promise<void> {
  const pending = downloadOnly.value
  if (pending === null || pending.caseId !== item.caseId) return
  try {
    const artifact = await props.bridge.downloadRecoveryArtifact({
      caseId: item.caseId,
      claim: pending.claim,
    })
    downloadOnly.value = { ...pending, artifact }
  } catch (error) {
    fail('download_recovery_artifact', error)
  }
}

defineExpose({
  /** 判据用的只读投影。`plainRetryOffered` 恒 false 是**结构性**事实：本文件没有该入口。 */
  getRecoveryState: () => ({
    listed: listed.value,
    caseCount: cases.value.length,
    scopeDrift: scopeDrift.value,
    bundleDigest: props.claimFence?.expectedDefinitionBundleSha256 ?? WP_SYNC_TRACE_GAP_PLACEHOLDER,
    claimResult: claimResult.value,
    downloadOnlyCaseId: downloadOnly.value?.caseId ?? null,
    plainRetryOffered: false,
  }),
})
</script>

<style scoped>
.wp-sync-recovery {
  font-size: var(--wp-font-size, 13px);
}

.wp-sync-recovery__header {
  display: flex;
  gap: 10px;
  align-items: center;
}

.wp-sync-recovery__title {
  font-weight: 600;
}

.wp-sync-recovery__scope,
.wp-sync-recovery__entities,
.wp-sync-recovery__claimed,
.wp-sync-recovery__bundle,
.wp-sync-recovery__download {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  padding: 4px 0;
  color: #909399;
}

.wp-sync-recovery__claimed {
  padding: 6px 10px;
  color: #529b2e;
  background: #f0f9eb;
  border-left: 3px solid #529b2e;
}

.wp-sync-recovery__download {
  padding: 6px 10px;
  align-items: center;
  background: #f4f4f5;
  border-left: 3px solid #909399;
}

.wp-sync-recovery__case {
  padding: 8px 0;
  border-top: 1px solid #ebeef5;
}

.wp-sync-recovery__case-head {
  display: flex;
  gap: 10px;
  align-items: center;
}

.wp-sync-recovery__id {
  color: #a8abb2;
}

.wp-sync-recovery__table {
  width: 100%;
  margin: 6px 0;
  font-size: var(--wp-font-size, 13px);
  border-collapse: collapse;
}

.wp-sync-recovery__caption {
  padding-bottom: 4px;
  color: #909399;
  text-align: left;
}

.wp-sync-recovery__table th,
.wp-sync-recovery__table td {
  padding: 4px 8px;
  text-align: left;
  border-bottom: 1px solid #ebeef5;
}

.wp-sync-recovery__blocking {
  margin: 4px 0;
  padding-left: 20px;
  color: #c45656;
}

.wp-sync-recovery__actions {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-top: 6px;
}

.wp-sync-recovery__error {
  margin: 4px 0;
  color: #c45656;
}

.wp-sync-recovery__hint {
  margin: 4px 0;
  color: #909399;
}
</style>
