/**
 * `WorkpaperSyncEditorHost.vue` 的**纯函数层**：DocsAPI 载入、DocEditor config 组装、
 * 编辑器回调错误取码、宿主侧文案。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 33
 * Requirements: 3.7, 4.8, 5.8, 11.4, 11.5, 11.6, 11.10, 11.12
 * Properties: P11（descriptor 是唯一 config 来源）/ P47（只消费 descriptor）/ P48（粘性 error）
 *
 * ═══ 为什么单独一层 ═══
 *
 * 组件里能直接测的只有 DOM 与事件；「config 是不是逐字来自 descriptor」「多出来的键是
 * 哪几个」这类**结构判据**放在纯函数里才能逐条断言。放回 `.vue` 里就只能靠扫源码字符串，
 * 而那种判据在改名/删调用后仍然全绿（本 spec 已实测三次）。
 *
 * ═══ 本层的三条硬边界 ═══
 *
 * 1. **不请求任何 config 端点**：整个文件不 import `@/utils/http`、`@/services/apiProxy`
 *    或 `workpaperSyncApi` —— descriptor 里的 `onlyofficeConfig` 就是全部（AC 11.4）。
 *    唯一的网络动作是 `<script src>` 载入 DocsAPI 的 `api.js`，那是**运行时载入**，
 *    不是第二份 config。
 * 2. **不伪造 config 字段**：`buildDocEditorConfig()` 只在 descriptor 的 config 上补
 *    `width/height/events` 三个键（:data:`WP_SYNC_HOST_ADDED_CONFIG_KEYS`）。
 *    `type` / `documentType` / `document.url` / `token` 一个都不补 —— 那些都是服务端
 *    在响应时给的，宿主补一个就等于自己造了第二份 config。
 * 3. **编辑器侧 forcesave 必须为假**：服务端 `_onlyoffice_config()` 把
 *    `editorConfig.customization.forcesave` 钉成 `False`（AC 4.1）。若它哪天变成 true，
 *    宿主必须**拒绝挂载**而不是照挂 —— 编辑器自己发起的 forcesave 会产生没有 frozen
 *    request 的孤儿 callback，只能进 recovery case。
 */
import { WorkpaperSyncContractError } from './workpaperSyncDto'
import type { WorkpaperSyncEditorLaunchDescriptor } from './workpaperSyncDto'

/** OnlyOffice 9.4.0 的 JS API 路径（与 `GtOnlyOfficeSheet` 现行约定逐字相同）。 */
export const WP_SYNC_DOCS_API_SCRIPT_PATH = '/web-apps/apps/api/documents/api.js'

/**
 * 宿主允许在 descriptor config 之上**额外**补的键。
 *
 * 判据据此做「多出来的键集合逐字等于本常量」的等值断言：只断言「descriptor 的键都在」
 * 是包含式判据，对「宿主偷偷补了 `token` / `type` / `document.url`」全绿。
 */
export const WP_SYNC_HOST_ADDED_CONFIG_KEYS = ['width', 'height', 'events'] as const

/** DocsAPI 的最小形态（宿主只用到 `DocEditor` 构造与实例的 `destroyEditor`）。 */
export interface WorkpaperSyncDocEditorInstance {
  destroyEditor?: () => void
}

export interface WorkpaperSyncDocsApi {
  DocEditor: new (
    placeholderId: string,
    config: Record<string, unknown>,
  ) => WorkpaperSyncDocEditorInstance
}

/** 注入点：测试给 stub，生产走 :func:`loadDocsApi`。 */
export type WorkpaperSyncDocsApiLoader = () => Promise<WorkpaperSyncDocsApi>

/** DocEditor 的四个真实回调（每个都必须有真实触发路径，AC 11.5）。 */
export interface WorkpaperSyncDocEditorEvents {
  onDocumentReady: () => void
  onDocumentStateChange: (event: unknown) => void
  onError: (event: unknown) => void
}

/** 宿主侧失败的中文文案。桥的状态文案在 `WP_BRIDGE_STATE_TEXT`，两者不重叠。 */
export const WP_SYNC_HOST_ERROR_TEXT: Readonly<Record<string, string>> = Object.freeze({
  editor_host_document_server_url_missing:
    '未配置 OnlyOffice 服务地址，无法载入编辑器内核',
  editor_host_docsapi_unavailable: 'OnlyOffice 内核载入后仍不可用，未创建编辑器',
  editor_host_docs_api_script_failed: 'OnlyOffice 内核脚本载入失败，未创建编辑器',
  editor_host_config_document_missing:
    'descriptor 内嵌的 OnlyOffice config 缺 document 段，拒绝挂载编辑器',
  editor_host_editor_side_forcesave_enabled:
    'descriptor 内嵌的 config 打开了编辑器侧自动保存，拒绝挂载编辑器',
  editor_host_forcesave_before_confirmation:
    '服务端尚未确认编辑器身份，强制保存不可用',
  editor_host_forcesave_without_operation:
    '强制保存已受理但没有回写任务编号，不显示保存完成',
  editor_host_recovery_case_absent:
    '编辑器异常中断，但服务端未列出可认领的恢复项，请联系项目负责人重新授权',
  editor_host_recovery_before_confirmation:
    '编辑器身份尚未确认，异常中断不进入恢复流程',
})

/**
 * 宿主侧拒绝的**唯一**构造点（不抛，交给调用方决定抛还是记）。
 *
 * 码必须在 :data:`WP_SYNC_HOST_ERROR_TEXT` 里登记：未登记的码会让 UI 显示一个裸英文
 * 标识符，而 AC 11.6 要求阻断原因对当前用户可读。
 */
export function hostRefusal(code: string, extra = ''): WorkpaperSyncContractError {
  const text = WP_SYNC_HOST_ERROR_TEXT[code]
  if (text === undefined) {
    return new WorkpaperSyncContractError(
      'editor_host_error_code_unregistered',
      `宿主抛出未登记的失败码 ${code} —— 文案表是唯一真源`,
    )
  }
  return new WorkpaperSyncContractError(code, extra === '' ? text : `${text}：${extra}`)
}

function refuse(code: string, extra = ''): never {
  throw hostRefusal(code, extra)
}

/** `window.DocsAPI` 当前是否已可用（`DocEditor` 是构造函数才算）。 */
export function currentDocsApi(): WorkpaperSyncDocsApi | null {
  if (typeof window === 'undefined') return null
  const holder = window as unknown as { DocsAPI?: unknown }
  const api = holder.DocsAPI as WorkpaperSyncDocsApi | undefined
  if (api && typeof api.DocEditor === 'function') return api
  return null
}

/**
 * 载入 DocsAPI。
 *
 * 🔴 `documentServerUrl` 为空时**拒绝**而不是静默不挂载：静默的后果是桥永远停在
 * `oo_loading`（在 `WP_BRIDGE_IN_FLIGHT_STATES` 里 ⇒ 用户既看不到失败也走不掉），
 * 那正是本 spec 反复点名的「永久 loading」形态。
 */
export function loadDocsApi(documentServerUrl: string): Promise<WorkpaperSyncDocsApi> {
  const existing = currentDocsApi()
  if (existing !== null) return Promise.resolve(existing)
  const base = String(documentServerUrl ?? '').trim().replace(/\/+$/, '')
  if (base === '') {
    return Promise.reject(
      new WorkpaperSyncContractError(
        'editor_host_document_server_url_missing',
        WP_SYNC_HOST_ERROR_TEXT.editor_host_document_server_url_missing,
      ),
    )
  }
  const src = `${base}${WP_SYNC_DOCS_API_SCRIPT_PATH}`
  return new Promise<WorkpaperSyncDocsApi>((resolve, reject) => {
    const settle = (): void => {
      const api = currentDocsApi()
      if (api === null) {
        reject(
          new WorkpaperSyncContractError(
            'editor_host_docsapi_unavailable',
            WP_SYNC_HOST_ERROR_TEXT.editor_host_docsapi_unavailable,
          ),
        )
        return
      }
      resolve(api)
    }
    const fail = (): void => {
      reject(
        new WorkpaperSyncContractError(
          'editor_host_docs_api_script_failed',
          `${WP_SYNC_HOST_ERROR_TEXT.editor_host_docs_api_script_failed}：${src}`,
        ),
      )
    }
    const already = document.querySelector(`script[src="${src}"]`)
    if (already !== null) {
      already.addEventListener('load', settle)
      already.addEventListener('error', fail)
      return
    }
    const tag = document.createElement('script')
    tag.src = src
    tag.async = true
    tag.onload = settle
    tag.onerror = fail
    document.head.appendChild(tag)
  })
}

function configSection(config: Record<string, unknown>, key: string): Record<string, unknown> {
  const section = config[key]
  if (section === null || typeof section !== 'object' || Array.isArray(section)) return {}
  return section as Record<string, unknown>
}

/**
 * descriptor → DocEditor config。**唯一** config 组装点。
 *
 * 只做三件事：原样铺开 `descriptor.onlyofficeConfig`、补容器尺寸、挂真实回调。
 * 任何字段级改写都在这里显式拒绝，而不是「补一个默认值」。
 */
export function buildDocEditorConfig(
  descriptor: WorkpaperSyncEditorLaunchDescriptor,
  events: WorkpaperSyncDocEditorEvents,
): Record<string, unknown> {
  const source = descriptor.onlyofficeConfig as Record<string, unknown>
  if (Object.keys(configSection(source, 'document')).length === 0) {
    refuse('editor_host_config_document_missing')
  }
  const customization = configSection(configSection(source, 'editorConfig'), 'customization')
  if (customization.forcesave === true) {
    refuse('editor_host_editor_side_forcesave_enabled')
  }
  return {
    ...source,
    width: '100%',
    height: '100%',
    events,
  }
}

/**
 * 从 DocEditor 的 `onError` 事件里取一个可显示的码。
 *
 * OO 的 `onError` 载荷形态不止一种（`{data:{errorCode,errorDescription}}` /
 * `{data:<code>}` / 什么都没有），所以这里**归一**而不是假设某一种；取不到时给
 * `editor_error_unknown` 而不是空串 —— 空码在下游会被 `classifySyncFailure` 拒绝，
 * 于是一次真实的编辑器异常会变成一个看不懂的契约错误。
 */
export function readEditorErrorCode(event: unknown): string {
  const wrapper = (event ?? {}) as { data?: unknown }
  const data = wrapper.data
  if (typeof data === 'number' && Number.isFinite(data)) return `editor_error_${data}`
  if (typeof data === 'string' && data.trim() !== '') return `editor_error_${data.trim()}`
  if (data !== null && typeof data === 'object' && !Array.isArray(data)) {
    const shape = data as { errorCode?: unknown; errorDescription?: unknown }
    if (typeof shape.errorCode === 'number' && Number.isFinite(shape.errorCode)) {
      return `editor_error_${shape.errorCode}`
    }
    if (typeof shape.errorCode === 'string' && shape.errorCode.trim() !== '') {
      return `editor_error_${shape.errorCode.trim()}`
    }
  }
  return 'editor_error_unknown'
}

/** `onError` 的可读描述（没有就退回码本身，不留空串）。 */
export function readEditorErrorMessage(event: unknown): string {
  const wrapper = (event ?? {}) as { data?: unknown }
  const data = wrapper.data
  if (data !== null && typeof data === 'object' && !Array.isArray(data)) {
    const shape = data as { errorDescription?: unknown }
    if (typeof shape.errorDescription === 'string' && shape.errorDescription.trim() !== '') {
      return shape.errorDescription.trim()
    }
  }
  return readEditorErrorCode(event)
}

/** `onDocumentStateChange` 的 dirty 判定（OO 传 `{data:true|false}`）。 */
export function readDocumentDirty(event: unknown): boolean {
  const wrapper = (event ?? {}) as { data?: unknown }
  return wrapper.data === true
}
