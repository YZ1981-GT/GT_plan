<!--
  WorkpaperSyncEditorHost.vue — Excel / Word 编辑器的**挂载宿主**（descriptor consumer）

  spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 33
  Requirements: 3.7, 4.8, 5.8, 11.4, 11.5, 11.6, 11.10, 11.12
  Properties: P11（DOM 侧：descriptor→mount→ready→confirm→可编辑）/ P47 / P48

  ═══ 它是什么 ═══

  Task 31 给了 descriptor/API，Task 32 给了状态机与两个上报口，两者都**刻意不碰 DOM**。
  本组件是那两半的唯一交汇点：`descriptor` 进来、DocEditor 出去、DocsAPI 的真实
  `onDocumentReady` 回传给桥、桥的 confirm 成功之后才允许保存。

  ═══ 四条不得违反的边界 ═══

  1. **不请求 config**：整个组件不 import 任何 HTTP 面。`descriptor.onlyofficeConfig`
     就是全部（AC 11.4 / Property 11）。签名 `document.url` 由服务端在响应时补进
     `onlyofficeConfig.document`，宿主原样用。
  2. **不伪造服务端确认**：`ready` 只表示 DocsAPI 回调触发了；`oo_editing` 与
     forcesave 的解锁只能由桥在 `confirmDescriptor()` 成功后给出。
  3. **确认失败必须收回编辑器**：桥在 identity 失败时把 mode 打回 `html`，本组件据此
     **销毁** DocEditor 并把保存入口一起撤掉 —— 「确认失败仍 editing」在 DOM 上不可达。
  4. **claim 前不得有 operation id**：`recoveryCase` 事件的载荷类型层面就禁掉了
     `operationId`（`operationId?: never`），运行时也只取 case 自身的字段。
-->
<template>
  <div class="wp-sync-editor-host" data-testid="wp-sync-host">
    <!-- 状态条：文案唯一真源是桥的 feedback（error 优先，Property 48） -->
    <div
      class="wp-sync-editor-host__status"
      :class="`wp-sync-editor-host__status--${feedback.kind}`"
      data-testid="wp-sync-host-status"
      :data-kind="feedback.kind"
    >
      {{ feedback.message }}
    </div>

    <!-- 宿主侧失败：载入/挂载/保存早于确认。桥的失败已在状态条里，两处互不覆盖 -->
    <p v-if="hostError !== null" class="wp-sync-editor-host__host-error" data-testid="wp-sync-host-error" :data-code="hostError.errorCode">
      {{ hostError.message }}
    </p>

    <!--
      Task 35：commit 后 `workpaper.content.updated` 的可见刷新条。

      🔴 与上面两处失败**互不覆盖**：桥的 `feedback` 说"我这次同步怎么样了"，本条说
      "别人（或后台升级）提交了新内容，你的表单要不要跟"。两件事同时为真是常态
      （协同房间里另一个用户刚 applied），压成一条就必然有一件被吞掉。
      未传协调器时整条不渲染 —— 这是 `single_html` 等无协同入口的正常形态。
    -->
    <WorkpaperSyncContentRefreshBanner
      v-if="props.contentRefresh"
      :refresh="props.contentRefresh"
    />

    <!-- recovery：只在桥进入 recovery 状态后出现，且**不**提供普通重试 -->
    <div v-if="inRecovery" class="wp-sync-editor-host__recovery" data-testid="wp-sync-host-recovery">
      <span data-testid="wp-sync-host-recovery-reason">{{ recoveryReasonText }}</span>
      <span data-testid="wp-sync-host-recovery-case">{{ recoveryCaseId }}</span>
    </div>

    <!-- 普通 operation 重试：recovery 期间与无 requested operation 时一律不渲染 -->
    <button
      v-if="showPlainRetry"
      type="button"
      class="wp-sync-editor-host__retry"
      data-testid="wp-sync-host-retry"
      @click="onRetryClick"
    >
      重试回写
    </button>

    <!-- 保存并回表单：确认成功前 disabled（ready 不等于可保存） -->
    <button
      v-if="editorLive"
      type="button"
      class="wp-sync-editor-host__save"
      data-testid="wp-sync-host-forcesave"
      :disabled="!canForcesave"
      @click="onForceSaveClick"
    >
      保存并回到表单模式
    </button>

    <!-- 编辑器：mode=oo 且 descriptor 在手才渲染；确认前盖遮罩 -->
    <div v-if="editorLive" class="wp-sync-editor-host__editor" data-testid="wp-sync-host-editor">
      <div v-if="!editing" class="wp-sync-editor-host__mask" data-testid="wp-sync-host-mask">
        {{ feedback.message }}
      </div>
      <div :id="containerId" class="wp-sync-editor-host__container" data-testid="wp-sync-host-container" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { describeBridgeFailure, type WorkpaperSyncBridge, type WorkpaperSyncBridgeError } from './useWorkpaperSyncBridge'
import WorkpaperSyncContentRefreshBanner from './WorkpaperSyncContentRefreshBanner.vue'
import type { WorkpaperContentRefresh } from './workpaperSyncContentRefresh'
import type { WorkpaperSyncEditorLaunchDescriptor } from './workpaperSyncDto'
import {
  buildDocEditorConfig,
  hostRefusal,
  loadDocsApi,
  readDocumentDirty,
  readEditorErrorCode,
  readEditorErrorMessage,
  type WorkpaperSyncDocEditorInstance,
  type WorkpaperSyncDocsApiLoader,
} from './workpaperSyncEditorHostRuntime'

/**
 * api.js 的来源是**基础设施地址**（与 config 无关），部署期由环境变量给。
 *
 * 不能写进 `withDefaults` 的默认值 —— `defineProps()` 会被提升到 `setup()` 外，
 * 引用模块内的局部常量会被编译器直接拒绝。故默认值留空串，真正的兜底在
 * `resolvedDocumentServerUrl` 里做。
 */
const ENV_DOCUMENT_SERVER_URL = String(
  (import.meta.env?.VITE_ONLYOFFICE_URL as string | undefined) ?? '',
)

const props = withDefaults(
  defineProps<{
    /** 编辑器的**唯一** config 来源。为 null 时不创建 DocEditor。 */
    descriptor: WorkpaperSyncEditorLaunchDescriptor | null
    /** Task 32 的桥实例：状态、门控与两个上报口都在它上面。 */
    bridge: WorkpaperSyncBridge
    /** OnlyOffice 服务地址（只用于载入 api.js，不是第二份 config）。 */
    documentServerUrl?: string
    /** DocsAPI 注入点：测试给 stub，生产为 null 走真实脚本载入。 */
    docsApiLoader?: WorkpaperSyncDocsApiLoader | null
    /**
     * Task 35 的内容刷新协调器。给了才渲染刷新条。
     *
     * 刻意可选：`single_html` / `single_onlyoffice` 等无协同对端的入口没有内容事件
     * 消费需求，强制必填会逼出一个空协调器（而空协调器就是死代码）。
     */
    contentRefresh?: WorkpaperContentRefresh | null
  }>(),
  {
    documentServerUrl: '',
    docsApiLoader: null,
    contentRefresh: null,
  },
)

/** 显式 prop 优先，未给时回落部署期环境变量。 */
const resolvedDocumentServerUrl = computed(() =>
  props.documentServerUrl.trim() !== '' ? props.documentServerUrl : ENV_DOCUMENT_SERVER_URL,
)

const emit = defineEmits<{
  /** DocsAPI `onDocumentReady` 真实触发（**不**代表服务端已确认）。 */
  ready: [{ roomId: string; participantId: string }]
  /** DocEditor `onDocumentStateChange` 真实触发。 */
  dirty: [{ dirty: boolean }]
  /** forcesave 被服务端受理（request 已冻结，shell 已建）。 */
  saveRequested: [{ operationId: string }]
  /** 桥观测到 incoming 已耐久。`artifactSha256` 见下方缺口说明，可能为 null。 */
  incomingDurable: [{ operationId: string; artifactSha256: string | null }]
  /** 回写终态：applied / conflict / refresh_required 三者分别可辨。 */
  terminal: [
    {
      operationId: string
      state: 'applied' | 'conflict' | 'refresh_required'
      revision: number | null
    },
  ]
  /** 恢复项。`operationId?: never` —— claim 成功前类型层面就不可能带它。 */
  recoveryCase: [{ caseId: string; reason: string; operationId?: never }]
  /** 宿主侧真实失败（载入/挂载/确认/保存）。 */
  error: [{ stage: string; code: string; message: string }]
}>()

const hostError = ref<WorkpaperSyncBridgeError | null>(null)
const containerId = ref('')
let editorInstance: WorkpaperSyncDocEditorInstance | null = null
let mountedKey: string | null = null
let mountSeq = 0

// ── 桥投影（模板不能自动解包 prop 上的 ref，一律经 computed）

/**
 * descriptor 的**唯一**读取点，顺手把 `undefined` 归一成 `null`。
 *
 * 🔴 归一不是洁癖：Vue 里父组件传一个**不存在的** prop 名是静默失效，子组件读到的是
 * `undefined` 而不是 `null`。若各处直接写 `props.descriptor === null`，那种接线错误会
 * 掉进「非 null」分支并在 `mountKeyOf(undefined)` 里抛一个看不懂的 TypeError；
 * 归一之后它变成「没有 descriptor ⇒ 不挂载」，判据能干净地打红。
 */
const activeDescriptor = computed<WorkpaperSyncEditorLaunchDescriptor | null>(
  () => props.descriptor ?? null,
)

const feedback = computed(() => props.bridge.feedback.value)
const editing = computed(() => props.bridge.state.value === 'oo_editing')
const canForcesave = computed(() => props.bridge.canForcesave.value)
const editorLive = computed(
  () => activeDescriptor.value !== null && props.bridge.mode.value === 'oo',
)
const inRecovery = computed(() =>
  ['recovery_pending', 'recovery_claiming', 'recovery_download_only'].includes(
    props.bridge.state.value,
  ),
)
const activeRecoveryCase = computed(() => {
  const id = props.bridge.activeRecoveryCaseId.value
  if (id === null) return null
  return props.bridge.recoveryCases.value.find((item) => item.caseId === id) ?? null
})
const recoveryCaseId = computed(() => activeRecoveryCase.value?.caseId ?? '')
const recoveryReasonText = computed(() => {
  const reason = activeRecoveryCase.value?.reason
  if (reason === undefined) return '存在待认领的恢复项'
  return RECOVERY_REASON_TEXT[reason] ?? '存在待认领的恢复项'
})

/**
 * 普通 operation 重试的**唯一**门。
 *
 * 三条同时成立才渲染：①桥记下的失败被裁决为可重试 ②确实有 requested operation
 * ③不在任何 recovery 状态。AC 5.8 末句明文「nullable operation 的 recovery case
 * 不得进入普通 operation retry」—— crash 发生在 forcesave 之前时
 * `requestedOperationId` 恒为 null，本门于是结构性地关着。
 */
const showPlainRetry = computed(() => {
  if (inRecovery.value) return false
  if (props.bridge.requestedOperationId.value === null) return false
  return props.bridge.lastError.value?.verdict.retryableOperation === true
})

const RECOVERY_REASON_TEXT: Readonly<Record<string, string>> = Object.freeze({
  missing_request: '服务端收到了文件但找不到对应的保存请求',
  ambiguous_close: '关闭时存在多个候选保存请求，无法唯一关联',
  crash_close: '编辑器异常中断，文件已保存但回写任务未建立',
  stale_candidate: '候选基线已过期，需重新授权后继续',
})

// ── 失败归一（与桥共用 `describeBridgeFailure`，避免第二份分型规则）

function failHost(stage: string, error: unknown, reportToBridge: boolean): void {
  const described = describeBridgeFailure(stage, error)
  hostError.value = described
  if (reportToBridge) props.bridge.notifyHostFailure(stage, error)
  emit('error', {
    stage: described.stage,
    code: described.errorCode,
    message: described.message,
  })
}

// ── 挂载 / 销毁

function destroyEditor(): void {
  const instance = editorInstance
  editorInstance = null
  mountedKey = null
  if (instance === null) return
  try {
    instance.destroyEditor?.()
  } catch {
    // 销毁失败不得覆盖任何已记住的失败（Property 48）：这里连 hostError 都不动。
  }
}

/** descriptor 的挂载身份。变了就必须销毁重挂（refresh-required 后的新 generation）。 */
function mountKeyOf(descriptor: WorkpaperSyncEditorLaunchDescriptor): string {
  return [
    descriptor.roomId,
    descriptor.docKey,
    descriptor.generation,
    descriptor.representationId,
    descriptor.representationGeneration,
  ].join('|')
}

async function mountEditor(descriptor: WorkpaperSyncEditorLaunchDescriptor): Promise<void> {
  const key = mountKeyOf(descriptor)
  mountSeq += 1
  const seq = mountSeq
  containerId.value = `wp-sync-oo-${descriptor.docKey}-${seq}`
  await nextTick()
  if (seq !== mountSeq) return
  let config: Record<string, unknown>
  try {
    config = buildDocEditorConfig(descriptor, {
      onDocumentReady: () => {
        void onDocumentReady(seq)
      },
      onDocumentStateChange: (event: unknown) => {
        onDocumentStateChange(event)
      },
      onError: (event: unknown) => {
        void onEditorError(event)
      },
    })
  } catch (error) {
    failHost('build_editor_config', error, true)
    return
  }
  let api
  try {
    api = props.docsApiLoader
      ? await props.docsApiLoader()
      : await loadDocsApi(resolvedDocumentServerUrl.value)
  } catch (error) {
    failHost('load_docs_api', error, true)
    return
  }
  if (seq !== mountSeq) return
  try {
    editorInstance = new api.DocEditor(containerId.value, config)
  } catch (error) {
    failHost('create_doc_editor', error, true)
    return
  }
  mountedKey = key
  try {
    // 只有 DocEditor 真的构造出来了才上报「已挂载」—— 构造抛错时上报等于伪造挂载。
    props.bridge.notifyEditorMounted()
  } catch (error) {
    // 桥拒绝该转换 ⇒ 宿主在一个状态机不预期的时点挂了编辑器（接线错误）。
    // 这里必须显式失败：吞掉它会留下一个「桥不知道存在」的编辑器实例。
    failHost('notify_editor_mounted', error, true)
  }
}

watch(
  [() => props.descriptor, () => props.bridge.mode.value],
  () => {
    const descriptor = activeDescriptor.value
    if (descriptor === null || props.bridge.mode.value !== 'oo') {
      mountSeq += 1
      destroyEditor()
      return
    }
    const key = mountKeyOf(descriptor)
    if (mountedKey === key) return
    destroyEditor()
    void mountEditor(descriptor)
  },
  { immediate: true },
)

// ── DocsAPI 真实回调

async function onDocumentReady(seq: number): Promise<void> {
  if (seq !== mountSeq) return
  const descriptor = activeDescriptor.value
  if (descriptor === null) {
    failHost('document_ready', hostRefusal('editor_host_config_document_missing'), true)
    return
  }
  emit('ready', {
    roomId: descriptor.roomId,
    participantId: descriptor.participantId,
  })
  try {
    await props.bridge.notifyDocumentReady()
  } catch (error) {
    // 桥已经把它记成 sticky error 并把 mode 打回 html —— 不再重复上报，
    // 但宿主必须自己也可见（AC 11.5「fail visible」）。
    failHost('confirm_descriptor', error, false)
  }
}

function onDocumentStateChange(event: unknown): void {
  const dirty = readDocumentDirty(event)
  props.bridge.notifyDirty(dirty)
  emit('dirty', { dirty })
}

/**
 * 编辑器异常。**已确认**的房间里发生的异常按 crash 走恢复流程，其余只可见。
 *
 * 为什么按 `oo_editing` 分流：`recovery_case_observed` 只从 `html_idle` 与
 * `oo_editing` 有出边（转换表是唯一判据）。确认之前的异常还没有 room active、
 * 服务端也不会有 unmatched delivery，硬塞进 recovery 只会撞非法转换。
 *
 * 恢复项由**服务端**列出（authorization-first），宿主不自造 case：列不出可认领项时
 * 显式失败，绝不退化成一个普通「重试」按钮。
 */
async function onEditorError(event: unknown): Promise<void> {
  const code = readEditorErrorCode(event)
  const message = readEditorErrorMessage(event)
  const descriptor = activeDescriptor.value
  if (props.bridge.state.value !== 'oo_editing' || descriptor === null) {
    failHost('editor_runtime', hostRefusal('editor_host_recovery_before_confirmation', code), true)
    return
  }
  let cases
  try {
    cases = await props.bridge.listRecoveryCases({
      roomId: descriptor.roomId,
      generation: descriptor.generation,
    })
  } catch (error) {
    failHost('list_recovery_cases', error, false)
    return
  }
  const claimable = cases.find((item) => item.state === 'unclaimed') ?? null
  if (claimable === null) {
    failHost('list_recovery_cases', hostRefusal('editor_host_recovery_case_absent', message), true)
    return
  }
  // 🔴 只回传 case 自身的两项。claim 成功前 request/application/operation 三者为空，
  // 这里带上任何 operation id 都是伪造（AC 5.8 / 11.5）。
  emit('recoveryCase', { caseId: claimable.caseId, reason: claimable.reason })
}

// ── 桥状态 → 事件（incoming durable / 终态）

const TERMINAL_STATES = ['applied', 'conflict', 'refresh_required'] as const

watch(
  () => props.bridge.state.value,
  (next) => {
    const snapshot = props.bridge.operation.value
    if (next === 'incoming_durable' && snapshot !== null) {
      // 🔴 已登记缺口：`GET .../operations/{id}` 的投影**没有** incoming artifact
      // digest（只有 application 的 bundle/authority digest）。design 的
      // `incomingDurable: [{operationId, artifactSha256}]` 因此只能给 null ——
      // 拿 descriptor 的 `artifactSha256` 顶替是**另一份**（materialize 出去的）
      // 摘要，会让「回传文件与我发出去的是同一份」这个结论凭空成立。
      emit('incomingDurable', {
        operationId: snapshot.requestedOperationId,
        artifactSha256: null,
      })
      return
    }
    if ((TERMINAL_STATES as readonly string[]).includes(next) && snapshot !== null) {
      emit('terminal', {
        operationId: snapshot.requestedOperationId,
        state: next as 'applied' | 'conflict' | 'refresh_required',
        revision: snapshot.resultRevision,
      })
    }
  },
)

// ── 用户动作

async function onForceSaveClick(): Promise<void> {
  try {
    await forceSave()
  } catch {
    // 已经在 `forceSave()` 里记成 hostError 并 emit 过；点击处理器不再抛。
  }
}

async function onRetryClick(): Promise<void> {
  try {
    await props.bridge.retryOperation()
  } catch (error) {
    failHost('retry_operation', error, false)
  }
}

/**
 * 可 await 的强制保存。**桥未拿到 confirm-descriptor 成功响应前必须 fail visible。**
 *
 * 桥的 `switchToHtml()` 自己也会拒，但它走 `refuse()` —— 那条路**不写** `lastError`，
 * 于是状态条什么都不会变。宿主因此先自己判一次并把失败落到 `hostError`，
 * 「按钮虽 disabled 但被程序调用」这条路也就有了可见结果。
 */
async function forceSave(): Promise<{ operationId: string }> {
  hostError.value = null
  if (!props.bridge.canForcesave.value) {
    const refusal = hostRefusal(
      'editor_host_forcesave_before_confirmation',
      `state=${props.bridge.state.value}`,
    )
    // 🔴 **不**上报给桥：这是「用户点早了」，不是同步步骤失败。报上去会把
    // `confirming_descriptor` 推成 `error`，于是一次正在飞行的合法确认被用户的
    // 一次早点击打断 —— 那才是真的坏。宿主自己可见就够（AC 11.5 的 fail visible）。
    failHost('forcesave', refusal, false)
    throw refusal
  }
  try {
    await props.bridge.switchToHtml()
  } catch (error) {
    failHost('forcesave', error, false)
    throw error
  }
  const operationId = props.bridge.requestedOperationId.value
  if (operationId === null) {
    const refusal = hostRefusal('editor_host_forcesave_without_operation')
    failHost('forcesave', refusal, true)
    throw refusal
  }
  emit('saveRequested', { operationId })
  return { operationId }
}

/** 只读同步态投影。宿主自己只贡献 DOM 事实，其余逐项来自桥。 */
function getSyncState(): {
  mode: string
  state: string
  dirty: boolean
  editorMounted: boolean
  editing: boolean
  canForcesave: boolean
  requestedOperationId: string | null
  recoveryCaseIds: readonly string[]
  hostErrorCode: string | null
  feedback: { kind: string; message: string }
} {
  return {
    mode: props.bridge.mode.value,
    state: props.bridge.state.value,
    dirty: props.bridge.dirty.value,
    editorMounted: editorInstance !== null,
    editing: editing.value,
    canForcesave: props.bridge.canForcesave.value,
    requestedOperationId: props.bridge.requestedOperationId.value,
    recoveryCaseIds: props.bridge.recoveryCases.value.map((item) => item.caseId),
    hostErrorCode: hostError.value?.errorCode ?? null,
    feedback: { kind: feedback.value.kind, message: feedback.value.message },
  }
}

onBeforeUnmount(() => {
  mountSeq += 1
  destroyEditor()
})

defineExpose({ forceSave, getSyncState })
</script>

<style scoped>
.wp-sync-editor-host {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  height: 100%;
  min-height: 480px;
}

.wp-sync-editor-host__status {
  font-size: 13px;
  color: #606266;
}

.wp-sync-editor-host__status--error {
  color: #c45656;
  font-weight: 600;
}

.wp-sync-editor-host__status--success {
  color: #529b2e;
}

.wp-sync-editor-host__host-error {
  margin: 0;
  font-size: 13px;
  color: #c45656;
}

.wp-sync-editor-host__recovery {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  font-size: 13px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
}

.wp-sync-editor-host__editor {
  position: relative;
  flex: 1;
  min-height: 0;
}

.wp-sync-editor-host__mask {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #606266;
  background: rgb(255 255 255 / 92%);
}

.wp-sync-editor-host__container {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.wp-sync-editor-host__container :deep(iframe) {
  width: 100% !important;
  height: 100% !important;
}
</style>
