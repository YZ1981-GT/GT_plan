<template>
  <div class="gt-ext-preview" data-testid="extended-format-preview">
    <div v-if="state === 'loading'" class="gt-ext-preview__loading" data-testid="extended-preview-loading">
      加载中…
    </div>

    <template v-else-if="state === 'ready'">
      <ArchiveEntryList v-if="family === 'archive' && archiveEntries" :entries="archiveEntries" />
      <EmailMessageView
        v-else-if="family === 'email' && email"
        :email="email"
        :create-object-url="createEmailObjectUrl"
        :release-object-url="releaseEmailObjectUrl"
      />
      <DxfDrawingView v-else-if="family === 'drawing' && dxfModel" :model="dxfModel" />
    </template>

    <div v-else-if="state === 'cancelled'" />

    <div v-else class="gt-ext-preview__fallback" data-testid="extended-preview-fallback">
      <p>{{ statusText }}</p>
      <button type="button" data-testid="extended-preview-download" @click="emit('download')">
        下载文件
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onUnmounted, ref, watch } from 'vue'
import {
  isExtendedFamily,
  resolvePreviewFamily,
  type PreviewFamily,
} from './attachmentPreviewFormats'
import { fetchExtendedBytes } from './extendedPreviewRequest'
import { PreviewResourceScope, createWorkerLease } from './previewResourceScope'
import { EMAIL_LIMITS } from './email/emailLimits'
import type { ArchiveEntryMeta, ArchiveParseResult } from './archive/archiveContainer'
import type { ParsedEmail } from './email/emailParser'
import type { DxfRenderModel } from './drawing/dxfModel'
import { DRAWING_LIMITS } from './drawing/drawingLimits'

const ArchiveEntryList = defineAsyncComponent(() => import('./archive/ArchiveEntryList.vue'))
const EmailMessageView = defineAsyncComponent(() => import('./email/EmailMessageView.vue'))
const DxfDrawingView = defineAsyncComponent(() => import('./drawing/DxfDrawingView.vue'))

const props = defineProps<{
  attachmentId: string
  downloadUrl: string
  fileName: string
  typeHint?: string | null
}>()

const emit = defineEmits<{
  (e: 'download'): void
  (e: 'close'): void
}>()

type UIState =
  | 'loading'
  | 'ready'
  | 'forbidden'
  | 'not_found'
  | 'load_failed'
  | 'wiring_error'
  | 'limit_reached'
  | 'encrypted'
  | 'format_mismatch'
  | 'container_unsupported'
  | 'parse_failed'
  | 'unsupported'
  | 'cancelled'

const WORKER_DEADLINE_MS = 15_000

const state = ref<UIState>('loading')
const family = ref<PreviewFamily>('unsupported')
const archiveEntries = ref<ArchiveEntryMeta[] | null>(null)
const email = ref<ParsedEmail | null>(null)
const dxfModel = ref<DxfRenderModel | null>(null)

let generation = 0
let scope = new PreviewResourceScope()
let abort: AbortController | null = null

type ApfeProbeWindow = Window & {
  __APFE_TEST_PROBE__?: boolean
  __APFE_SCOPE_LIVE__?: ReturnType<PreviewResourceScope['snapshot']>
  __APFE_WORKER_EVENTS__?: { created: number; message: number; disposed: number }
}

function withProbeWindow(run: (target: ApfeProbeWindow) => void): void {
  if (import.meta.env.MODE !== 'apfe-e2e') return
  try {
    const target = window as ApfeProbeWindow
    if (target.__APFE_TEST_PROBE__ === true) run(target)
  } catch {
    /* test probe must never affect preview behavior */
  }
}

function reportScopeLive(): void {
  withProbeWindow((target) => {
    target.__APFE_SCOPE_LIVE__ = scope.snapshot()
  })
}

function reportWorkerEvent(event: 'created' | 'message' | 'disposed'): void {
  withProbeWindow((target) => {
    const events = target.__APFE_WORKER_EVENTS__ ?? { created: 0, message: 0, disposed: 0 }
    events[event] += 1
    target.__APFE_WORKER_EVENTS__ = events
  })
}

function createEmailObjectUrl(blob: Blob): string {
  const url = scope.trackObjectUrl(URL.createObjectURL(blob))
  reportScopeLive()
  return url
}

function releaseEmailObjectUrl(url: string): void {
  scope.releaseObjectUrl(url)
  reportScopeLive()
}

const STATUS_TEXT: Record<string, string> = {
  forbidden: '无权访问',
  not_found: '文件不存在',
  load_failed: '加载失败',
  wiring_error: '预览通道配置错误，请下载后查看',
  limit_reached: '内容超出预览安全上限',
  encrypted: '该压缩包已加密，请下载后打开',
  format_mismatch: '文件内容与扩展名不符',
  container_unsupported: '当前不支持该压缩/容器格式',
  parse_failed: '解析失败，请下载后打开',
  unsupported: '暂不支持预览此格式，请下载后查看',
}

const statusText = computed(() => STATUS_TEXT[state.value] || '加载失败')

function isCurrent(g: number) {
  return g === generation
}

async function postWorkerRequest(
  workerUrl: URL,
  payload: { requestId: string; bytes: ArrayBuffer; hintExt?: string },
  requestGeneration: number,
  deadlineMs = WORKER_DEADLINE_MS,
): Promise<unknown> {
  const lease = createWorkerLease(
    () => {
      const worker = new Worker(workerUrl, { type: 'module' })
      reportWorkerEvent('created')
      return worker
    },
    scope,
    { deadlineMs, generation: requestGeneration, isCurrent },
  )
  try {
    const response = await lease.post(payload, [payload.bytes])
    reportWorkerEvent('message')
    return response
  } finally {
    reportWorkerEvent('disposed')
    reportScopeLive()
  }
}

async function parseArchive(
  bytes: ArrayBuffer,
  hintExt: string | undefined,
  g: number,
): Promise<ArchiveParseResult> {
  const requestId = `archive-${g}`
  const resp = (await postWorkerRequest(
    new URL('./archive/archive.worker.ts', import.meta.url),
    { requestId, bytes, hintExt },
    g,
  )) as { requestId?: string; ok?: boolean; result?: ArchiveParseResult }
  if (!resp?.ok || !resp.result) throw new Error('archive_worker_failed')
  return resp.result
}

async function parseEmail(
  bytes: ArrayBuffer,
  hintExt: string | undefined,
  g: number,
): Promise<{ status: string; email?: ParsedEmail }> {
  const requestId = `email-${g}`
  const resp = (await postWorkerRequest(
    new URL('./email/email.worker.ts', import.meta.url),
    { requestId, bytes, hintExt },
    g,
  )) as { requestId?: string; ok?: boolean; result?: { status: string; email?: ParsedEmail } }
  if (!resp?.ok || !resp.result) throw new Error('email_worker_failed')
  return resp.result
}

async function parseDxf(
  bytes: ArrayBuffer,
  g: number,
): Promise<{ status: string; model?: DxfRenderModel }> {
  const requestId = `dxf-${g}`
  const resp = (await postWorkerRequest(
    new URL('./drawing/dxf.worker.ts', import.meta.url),
    { requestId, bytes },
    g,
    DRAWING_LIMITS.deadlineMs,
  )) as { requestId?: string; ok?: boolean; result?: { status: string; model?: DxfRenderModel } }
  if (!resp?.ok || !resp.result) throw new Error('dxf_worker_failed')
  return resp.result
}

async function load() {
  generation += 1
  const g = generation
  scope.releaseAll()
  scope = new PreviewResourceScope()
  abort?.abort()

  archiveEntries.value = null
  email.value = null
  dxfModel.value = null

  const verdict = resolvePreviewFamily(props.fileName, props.typeHint)
  family.value = verdict.family
  if (verdict.advice === 'cad_download_only' || !isExtendedFamily(verdict.family)) {
    state.value = 'unsupported'
    reportScopeLive()
    return
  }

  const controller = new AbortController()
  abort = controller
  scope.trackAbortController(controller)
  reportScopeLive()
  state.value = 'loading'
  try {
    const fetched = await fetchExtendedBytes({
      attachmentId: props.attachmentId,
      downloadUrl: props.downloadUrl,
      family: verdict.family,
      signal: controller.signal,
      generation: g,
      isCurrent,
      scope,
      maxBytes: verdict.family === 'email' ? EMAIL_LIMITS.maxInputBytes : undefined,
    })
    scope.untrackAbortController(controller)
    reportScopeLive()
    if (!isCurrent(g)) return
    if (fetched.status !== 'ready') {
      state.value = fetched.status === 'stale' ? 'cancelled' : (fetched.status as UIState)
      return
    }

    if (verdict.family === 'archive') {
      const result = await parseArchive(fetched.bytes, verdict.ext, g)
      if (!isCurrent(g)) return
      archiveEntries.value = result.entries
      state.value = result.status === 'ok' ? 'ready' : (result.status as UIState)
      return
    }
    if (verdict.family === 'email') {
      const result = await parseEmail(fetched.bytes, verdict.ext === 'msg' ? 'msg' : 'eml', g)
      if (!isCurrent(g)) return
      if (result.status === 'ok' && result.email) {
        email.value = result.email
        state.value = 'ready'
      } else {
        state.value = result.status === 'limit' ? 'limit_reached' : 'parse_failed'
      }
      return
    }
    if (verdict.family === 'drawing') {
      const result = await parseDxf(fetched.bytes, g)
      if (!isCurrent(g)) return
      if (result.status === 'ok' && result.model) {
        dxfModel.value = result.model
        state.value = 'ready'
      } else {
        state.value = result.status === 'limit' ? 'limit_reached' : 'parse_failed'
      }
    }
  } catch {
    if (isCurrent(g)) state.value = 'parse_failed'
  } finally {
    scope.untrackAbortController(controller)
    reportScopeLive()
  }
}

watch(
  () => [props.attachmentId, props.downloadUrl, props.fileName, props.typeHint] as const,
  () => {
    void load()
  },
  { immediate: true },
)

onUnmounted(() => {
  generation += 1
  abort?.abort()
  scope.releaseAll()
  reportScopeLive()
})

defineExpose({
  state,
  family,
  getGeneration: () => generation,
  getResourceSnapshot: () => scope.snapshot(),
})
</script>

<style scoped>
.gt-ext-preview { min-height: 240px; }
.gt-ext-preview__fallback { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 24px; }
</style>
