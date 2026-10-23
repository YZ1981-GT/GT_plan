// 文档版本过期事件与加载期遮罩（spec writeback-followup-issue-closure R2 / D3）。
//
// 真栈形态（2026-10-23 重药安徽 D2-2）：平台复用了一个文档服务器已经保存过的 doc key，
// OnlyOffice 弹「版本已更改，该页面将被重新加载」，而宿主的整块遮罩正盖在它上面 —— 点不到；
// 确认后载入的是 room 物化时的旧字节。后端已改为 status 2 回 0 后关闭 room（下次换代），
// 前端这两条判据钉住：①等文档就绪时遮罩放行点击、确认中 / 失败态仍拦截；②两个过期事件
// 都进入可见失败并给出中文出路，不自动重载。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'

import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import {
  WP_SYNC_HOST_ERROR_TEXT,
  type WorkpaperSyncDocEditorEvents,
  type WorkpaperSyncDocsApi,
} from '../workpaperSyncEditorHostRuntime'
import { useWorkpaperSyncBridge, type WorkpaperSyncApiSurface, type WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'
import type { WorkpaperSyncEditorLaunchDescriptor } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

function descriptorFixture(): WorkpaperSyncEditorLaunchDescriptor {
  return {
    operationId: UUID(20),
    roomId: UUID(21),
    participantId: UUID(22),
    docKey: 'dockey-1',
    generation: 3,
    serverAppliedRevision: 11,
    clientConfirmedBaseRevision: 10,
    contentVersionId: UUID(23),
    representationId: UUID(24),
    representationGeneration: 2,
    artifactSha256: DIGEST(1),
    writeFenceEpoch: 5,
    authorityModel: 'projection_contract',
    authorityModelDefinitionSha256: DIGEST(2),
    definitionBundleId: UUID(25),
    definitionBundleSha256: DIGEST(3),
    definitionBundleSlots: {
      template: { type: 'excel_template', sha256: DIGEST(4) },
      instrumentation: { type: 'excel_instrumentation', sha256: DIGEST(5) },
      contract: { type: 'sync_contract', sha256: DIGEST(6) },
    },
    documentType: 'xlsx',
    mode: 'edit',
    onlyofficeConfig: {
      document: { key: 'dockey-1', fileType: 'xlsx', title: 'd2.xlsx', url: 'https://x/y.xlsx' },
      documentType: 'cell',
      editorConfig: { mode: 'edit', customization: { forcesave: false } },
    },
    replayed: false,
  }
}

let editors: Array<{ events: WorkpaperSyncDocEditorEvents }> = []
let releaseConfirm: (() => void) | null = null
const LIVE: VueWrapper[] = []

function docsApiStub(): WorkpaperSyncDocsApi {
  return {
    DocEditor: class {
      constructor(_id: string, config: Record<string, unknown>) {
        editors.push({ events: config.events as WorkpaperSyncDocEditorEvents })
      }
    } as unknown as WorkpaperSyncDocsApi['DocEditor'],
  }
}

function bridgeWith(opts: { holdConfirm?: boolean } = {}): WorkpaperSyncBridge {
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1',
      expectedRevision: 11,
      payloadSha256: DIGEST(7),
      expiresAt: '2026-08-16T00:05:00Z',
      idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => descriptorFixture()),
    confirmDescriptor: vi.fn(async () => {
      if (opts.holdConfirm) await new Promise<void>((resolve) => { releaseConfirm = resolve })
      return {
        confirmationId: UUID(26),
        roomId: UUID(21),
        participantId: UUID(22),
        generation: 3,
        representationId: UUID(24),
        contentVersionId: UUID(23),
        roomState: 'active',
        replayed: false,
        forcesaveUnlocked: true,
      }
    }),
  }
  return useWorkpaperSyncBridge({
    entryId: ref('xlsx/gt-d2-accounts-receivable'),
    wpId: ref(UUID(102)),
    projectId: ref(UUID(101)),
    sheetKey: ref('D2-2'),
    capability: 'bidirectional',
    flushHtml: vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml: vi.fn(async () => {}),
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
  })
}

async function mounted(bridge: WorkpaperSyncBridge): Promise<VueWrapper> {
  const wrapper = mount(WorkpaperSyncEditorHost, {
    props: { descriptor: null, bridge, docsApiLoader: async () => docsApiStub() } as never,
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  const descriptor = await bridge.switchToOnlyOffice()
  await wrapper.setProps({ descriptor })
  await flushPromises()
  return wrapper
}

function mask(wrapper: VueWrapper) {
  return wrapper.find('[data-testid="wp-sync-host-mask"]')
}

beforeEach(() => {
  editors = []
  releaseConfirm = null
})

afterEach(() => {
  for (const wrapper of LIVE) wrapper.unmount()
  LIVE.length = 0
  vi.restoreAllMocks()
})

describe('加载期遮罩：只在等文档就绪时放行点击', () => {
  it('descriptor_mounted 放行；确认中拦截；确认后撤掉', async () => {
    const bridge = bridgeWith({ holdConfirm: true })
    const wrapper = await mounted(bridge)
    expect(bridge.state.value).toBe('descriptor_mounted')
    expect(mask(wrapper).attributes('data-passthrough')).toBe('true')
    expect(mask(wrapper).classes()).toContain('wp-sync-editor-host__mask--passthrough')

    editors[editors.length - 1].events.onDocumentReady()
    await flushPromises()
    expect(bridge.state.value).toBe('confirming_descriptor')
    expect(mask(wrapper).attributes('data-passthrough')).toBe('false')
    expect(mask(wrapper).classes()).not.toContain('wp-sync-editor-host__mask--passthrough')

    releaseConfirm?.()
    await flushPromises()
    expect(bridge.state.value).toBe('oo_editing')
    expect(mask(wrapper).exists()).toBe(false)
  })
})

describe('文档版本过期：可见失败 + 中文出路，不自动重载', () => {
  for (const event of ['onRequestRefreshFile', 'onOutdatedVersion'] as const) {
    it(`${event}（加载期）⇒ error 态、遮罩改为拦截、提示回到表单模式`, async () => {
      const bridge = bridgeWith()
      const wrapper = await mounted(bridge)
      expect(bridge.state.value).toBe('descriptor_mounted')
      editors[editors.length - 1].events[event]()
      await flushPromises()

      expect(bridge.state.value).toBe('error')
      expect(bridge.lastError.value?.errorCode).toBe('editor_host_document_outdated')
      expect(wrapper.find('[data-testid="wp-sync-host-error"]').text()).toContain(
        WP_SYNC_HOST_ERROR_TEXT.editor_host_document_outdated,
      )
      expect(mask(wrapper).attributes('data-passthrough')).toBe('false')
      const emitted = (wrapper.emitted('error') ?? []).map((args) => (args[0] as { code: string }).code)
      expect(emitted).toContain('editor_host_document_outdated')
      // 只构造过一次编辑器：宿主不自行重载 / 重挂
      expect(editors).toHaveLength(1)
    })
  }

  it('编辑中断线重连后收到 ⇒ 同样进入可见失败（保存入口随之关闭）', async () => {
    const bridge = bridgeWith()
    const wrapper = await mounted(bridge)
    editors[editors.length - 1].events.onDocumentReady()
    await flushPromises()
    expect(bridge.state.value).toBe('oo_editing')
    editors[editors.length - 1].events.onRequestRefreshFile()
    await flushPromises()
    expect(bridge.state.value).toBe('error')
    expect(bridge.canForcesave.value).toBe(false)
    expect(mask(wrapper).exists()).toBe(true)
  })

  it('已被替换掉的编辑器实例发来的过期事件不作数', async () => {
    const bridge = bridgeWith()
    const wrapper = await mounted(bridge)
    const stale = editors[editors.length - 1]
    await wrapper.setProps({ descriptor: null })
    await flushPromises()
    stale.events.onRequestRefreshFile()
    await flushPromises()
    expect(bridge.lastError.value).toBeNull()
  })

  it('两个过期事件都交给了 DocEditor（不是只声明不接线）', async () => {
    const bridge = bridgeWith()
    await mounted(bridge)
    const events = editors[editors.length - 1].events as unknown as Record<string, unknown>
    expect(typeof events.onRequestRefreshFile).toBe('function')
    expect(typeof events.onOutdatedVersion).toBe('function')
  })
})
