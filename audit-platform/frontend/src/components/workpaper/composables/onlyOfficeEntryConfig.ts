/**
 * 在线编辑「取配置」的唯一入口 —— room 协议优先（spec `workpaper-html-onlyoffice-bidirectional-writeback-closure` 任务 2.8 第 ② 步）
 *
 * ═══ 为什么要有这一层 ═══
 *
 * 2.8 的根因不是「某个函数写得差」，而是**优先级链没有单一来源**：旧式
 * `/sheets/{sheet}/onlyoffice-config` 端点自己解析一次目标文件，它签发的
 * `wopi/contents` 与 `/onlyoffice-callback` 又各自解析一次 ⇒ 后端 writer gate 的
 * `multi_resolver` 判据把三行全部点名。要真正收敛，前端必须先停止调旧端点。
 *
 * 第 ② 步之前的事实：**22 个 composable** 各自手写同一段
 * 「health check → GET onlyoffice-config → 拿 config」，共 67 处调用点。
 * 本文件把「取配置」收敛成一份，22 个调用方只表达「我要这个 sheet 的编辑配置」。
 *
 * ═══ 为什么 entry_id 由服务端算 ═══
 *
 * room `entry_id` 的规则是 ``xlsx-sheet/{wp_code}/{sheet_slug}``，而 `wp_code` 只有
 * 服务端能算准（聚合包内的独立子码会被换掉）。实测**22 个 composable 无一持有
 * `wpCode`** ⇒ 前端自己派生必然算错，表现为 readiness 恒 404「在线编辑永远不可用」。
 * 所以这里调 `GET /sync/entry-identity`（服务端用与 `/onlyoffice-config` **同一个**
 * `sheet_entry_id` 算出身份），前端只传它本来就有的 `wpId` + `sheetName`。
 *
 * ═══ 协议选择的判据 ═══
 *
 * | entry-identity 的 `room_ready` | 走哪条路 | 理由 |
 * | --- | --- | --- |
 * | `true` | **room 协议** | 后端已具备 room 供给，旧端点已被 409 挡住 |
 * | `false` | **旧式 config**（fallback） | 该 entry 进不了 room（没 representation 就没法 materialize），只调旧端点才不会让在线编辑整个打不开 |
 * | 端点本身失败 | **旧式 config**（fallback） | 同上：判据算不出来时不假装能走 room |
 *
 * 🔴 这个 fail-open 方向是刻意的，与后端门（`_wp_onlyoffice_legacy_url_gate`）同源：
 * 反过来做会让一批 entry 同时失去两条路 —— 那是比 `multi_resolver` 更重的事故
 * （Requirement 12.8 禁做假切换 / 禁让入口失效）。
 *
 * ═══ 为什么不在这一层 materialize ═══
 *
 * room 协议的正规入口是 `WorkpaperSyncEditorHost` + `useWorkpaperSyncBridge`：它要管
 * flush → pending mutation → materialize → confirm-descriptor → forcesave 整条状态机。
 * 22 个 composable 只负责「切不切得过去」的**可达性预检**，不负责驱动协同会话。
 * 真正挂载编辑器仍交给宿主组件 —— `isOoAvailable` 的语义不变。
 */
import http from '@/utils/http'
import {
  WP_SYNC_SIBLING_PREFIX_TEMPLATE,
  WP_SYNC_USER_PREFIX_TEMPLATE,
} from '@/components/workpaper/sync/workpaperSyncContract.generated'

/** binding 状态机（spec `onlyoffice-sheet-open-via-published-artifact` 1.4 / 2.6）。 */
export type SheetBindingStatus =
  | 'pending'
  | 'ready'
  | 'migrated'
  | 'draining'
  | 'retired'
  | 'out_of_scope'

/**
 * 取配置的结果：走哪条协议 + 能不能切过去 + 不可切时的中文原因。
 *
 * 🔴 `bindingStatus` 与 `syncMode` 是 task 3.1 新增的**三态**依据。只有 `available`
 * 一个布尔时，「binding 已 migrated 但供给暂时不就绪」与「binding pending 从未迁移」
 * 会显示成同一句话（都不可用），而它们的下一步动作完全相反：前者等供给恢复，
 * 后者本来就能用独立在线编辑。
 */
export interface OnlyOfficeEntryConfigProbe {
  /** `room` = 服务端声明统一协议供给已就绪；`legacy` = 回落到旧式 config 端点。 */
  readonly protocol: 'room' | 'legacy'
  /** 能不能切到在线编辑。false 时 `reason` 给中文可操作原因。 */
  readonly available: boolean
  /** 旧式端点返回的 config（仅 `protocol === 'legacy'` 且可用时非空）。 */
  readonly config: Record<string, unknown> | null
  /** 不可切时的中文原因（`available === false` 时非空）。 */
  readonly reason: string | null
  /** 服务端算出的 room entry 身份（`protocol === 'room'` 时非空，供宿主组件用）。 */
  readonly entryId: string | null
  /** 服务端 binding 状态（拿不到时为 null）。界面据此决定文案与入口。 */
  readonly bindingStatus: SheetBindingStatus | null
  /**
   * 同步语义：`bound` = 与 HTML 双向同步；`independent` = 独立在线编辑、不同步。
   *
   * 🔴 界面**不得**在 `independent` 时显示「已同步」「双向回写」——
   * 那是本 spec 要消灭的假状态（Requirement 4.2 / 6.2）。
   */
  readonly syncMode: 'bound' | 'independent'
}

/** old-style 端点 URL —— 全仓**唯一**一处拼接。 */
export function legacyOnlyOfficeConfigUrl(wpId: string, sheetName: string): string {
  return `/api/workpapers/${wpId}/sheets/${encodeURIComponent(sheetName)}/onlyoffice-config`
}

/** entry 身份解析端点 —— 全仓**唯一**一处拼接。
 *
 * 路径来自生成的契约（`WP_SYNC_SIBLING_PREFIX_TEMPLATE`，真源是后端的
 * `wp_sync_router.ENTRY_IDENTITY_PREFIX`），不在这里硬编码 `/sync/entry-identity`：
 * 该端点挂在与 `USER_SYNC_PREFIX` **并列**的 scope 前缀下（它要先算出 entry_id，
 * 挂不进带 `{entry_id:path}` 的那条），前缀一改硬编码就是静默 404。
 */
export function entryIdentityUrl(projectId: string, wpId: string): string {
  return `${WP_SYNC_SIBLING_PREFIX_TEMPLATE}/entry-identity`
    .replace('{project_id}', encodeURIComponent(projectId))
    .replace('{wp_id}', encodeURIComponent(wpId))
}

/** 带 entry 段的用户端前缀（供宿主/预检拼 readiness 等路径）。 */
export function userSyncPrefix(projectId: string, wpId: string, entryId: string): string {
  return WP_SYNC_USER_PREFIX_TEMPLATE
    .replace('{project_id}', encodeURIComponent(projectId))
    .replace('{wp_id}', encodeURIComponent(wpId))
    .replace('{entry_id}', entryId)
}

interface EntryIdentity {
  readonly entryId: string | null
  readonly roomReady: boolean
  readonly reason: string | null
  readonly bindingStatus: SheetBindingStatus | null
  readonly syncMode: 'bound' | 'independent'
}

/** binding status 的封闭域（服务端给未知值时归 null，不静默当 pending）。 */
const BINDING_STATUSES: readonly SheetBindingStatus[] = [
  'pending',
  'ready',
  'migrated',
  'draining',
  'retired',
  'out_of_scope',
]

function asBindingStatus(value: unknown): SheetBindingStatus | null {
  // 🔴 未知值归 null（**不**静默当 pending）：服务端加新状态时前端应当「不认识」而不是
  // 「猜成最宽松的那个」。判据见 `onlyOfficeEntryConfigContract.spec.ts` 判据 4。
  return typeof value === 'string' && (BINDING_STATUSES as readonly string[]).includes(value)
    ? (value as SheetBindingStatus)
    : null
}

/**
 * 问服务端「该 sheet 的 room 供给就绪吗、entry 身份是什么」。
 *
 * 任何失败都收敛成 `roomReady: false` —— 调用方据此回落旧式路径。
 */
async function readEntryIdentity(input: {
  projectId: string
  wpId: string
  sheetName: string
  wholeWorkbook: boolean
}): Promise<EntryIdentity> {
  try {
    const res: any = await http.get(entryIdentityUrl(input.projectId, input.wpId), {
      params: { sheet_name: input.sheetName, whole_workbook: input.wholeWorkbook },
      _silent: true,
    } as any)
    const body = res?.data?.data ?? res?.data ?? {}
    const entryId = typeof body?.entry_id === 'string' ? body.entry_id.trim() : ''
    const bindingStatus = asBindingStatus(body?.status ?? body?.binding_status)
    return {
      entryId: entryId || null,
      roomReady: body?.room_ready === true,
      reason: typeof body?.reason === 'string' && body.reason.trim() ? body.reason.trim() : null,
      bindingStatus,
      // 服务端明确说 migrated 时，即便供给暂时不就绪也算 bound（语义上已绑 room）。
      syncMode:
        body?.sync_mode === 'bound' || bindingStatus === 'migrated' ? 'bound' : 'independent',
    }
  } catch {
    return {
      entryId: null,
      roomReady: false,
      reason: null,
      bindingStatus: null,
      syncMode: 'independent',
    }
  }
}

/** 旧式端点：取 config，返回 `{ config, reason }`。 */
/** 旧式端点的完整回执：config 之外还有服务端标的同步语义（task 2.6）。 */
interface LegacyProbe {
  readonly config: Record<string, unknown> | null
  readonly reason: string | null
  /** 服务端标的同步模式（`bound` / `independent`）；缺省按 `independent`。 */
  readonly syncMode: 'bound' | 'independent'
  /** 服务端标的 binding 状态；缺省 null。 */
  readonly bindingStatus: SheetBindingStatus | null
}

async function probeLegacy(wpId: string, sheetName: string): Promise<LegacyProbe> {
  try {
    const res: any = await http.get(legacyOnlyOfficeConfigUrl(wpId, sheetName), {
      _silent: true,
    } as any)
    const result = res?.data?.data ?? res?.data ?? {}
    const errorCode = String(
      (res?.data as any)?.detail?.error_code ?? (result as any)?.error_code ?? '',
    )
    // 409 `legacy_onlyoffice_url_retired`：后端已停止签发旧 URL（2.8 第①步的开关）。
    // 这不是错误而是**引导** —— 该 entry 已具备统一协议供给，改走协同编辑入口。
    // 服务端在**响应顶层**标同步语义（与 `config` 平级，不是 config 内部）。
    const syncMode: 'bound' | 'independent' =
      (result as any)?.sync_mode === 'bound' ? 'bound' : 'independent'
    const bindingStatus = asBindingStatus((result as any)?.binding_status)
    if (errorCode === 'legacy_onlyoffice_url_retired') {
      return {
        config: null,
        reason: '该底稿已支持统一在线编辑协议，请改用协同编辑入口打开',
        syncMode: 'bound',
        bindingStatus,
      }
    }
    const config = (result?.data ?? result) as Record<string, unknown> | null
    if (!config || Object.keys(config).length === 0) {
      return { config: null, reason: '该底稿的在线编辑暂时不可用', syncMode, bindingStatus }
    }
    return { config, reason: null, syncMode, bindingStatus }
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    const errorCode = String(detail?.error_code ?? '')
    const bindingStatus = asBindingStatus(detail?.binding_status)
    if (errorCode === 'legacy_onlyoffice_url_retired') {
      return {
        config: null,
        reason:
          String(detail?.message || '').trim() ||
          '该底稿已支持统一在线编辑协议，请改用协同编辑入口打开',
        // 409 retired 是**已绑 room**的语义（binding 已 migrated/draining）。
        syncMode: 'bound',
        bindingStatus,
      }
    }
    return {
      config: null,
      reason: '该底稿的在线编辑暂时不可用',
      syncMode: 'independent',
      bindingStatus,
    }
  }
}

/**
 * 取该 sheet 的在线编辑配置（**唯一入口**）。
 *
 * 任何异常都收敛成 `available: false` + 中文原因 —— 调用方不需要 try/catch。
 */
export async function probeOnlyOfficeEntryConfig(input: {
  projectId?: string
  wpId: string
  sheetName: string
  /** 完整Excel 模式：整册码，不猜子码。 */
  wholeWorkbook?: boolean
}): Promise<OnlyOfficeEntryConfigProbe> {
  const wpId = String(input.wpId || '').trim()
  const sheetName = String(input.sheetName || '').trim()
  const projectId = String(input.projectId || '').trim()
  const wholeWorkbook = input.wholeWorkbook === true

  if (!wpId || !sheetName) {
    return {
      protocol: 'legacy',
      available: false,
      config: null,
      reason: '缺少底稿或工作表标识，无法打开在线编辑',
      entryId: null,
      bindingStatus: null,
      syncMode: 'independent',
    }
  }

  // 有 projectId 才能问 entry-identity（端点路径要它）。没有就直接走旧式 ——
  // 那批调用方本来也拿不到 room 身份，硬试只会多一次失败请求。
  if (projectId) {
    const identity = await readEntryIdentity({ projectId, wpId, sheetName, wholeWorkbook })

    // ── 三态判定（task 3.1）──────────────────────────────────────────────
    //
    // | binding status            | 结论                                          |
    // | ------------------------- | --------------------------------------------- |
    // | migrated / ready          | room 协议（供给就绪则 available，否则给原因）  |
    // | pending / out_of_scope    | **独立在线编辑**（走旧式，但标 independent）    |
    // | 无 binding                | 旧式（与改动前一致）                            |
    //
    // 🔴 `pending` / `out_of_scope` 不得判成「不可用」：它们本来就能用独立在线编辑
    //    （Requirement 6.2）。判成不可用会让一批入口整个打不开（R12.8 禁止）。
    const status = identity.bindingStatus
    // 🔴 `status === null` 是**灰度期兼容**分支：`status` 是 task 2.1 新增字段，前后端
    // 可能不同版本共存。缺它时按 `room_ready` 判（改动前的行为），而不是把已就绪的
    // 入口一律判成「没有 binding」⇒ 那会让灰度期所有入口退回旧式。
    const bound = status === null
      ? identity.roomReady
      : status === 'migrated' || status === 'ready'

    if (bound && identity.roomReady) {
      // 供给就绪 ⇒ 后端旧端点会被 409 挡住，这里直接判「可切」，
      // 由宿主组件走 room 协议挂载。**不**在这一层 materialize（见文件头）。
      return {
        protocol: 'room',
        available: true,
        config: null,
        reason: null,
        entryId: identity.entryId,
        bindingStatus: status,
        syncMode: 'bound',
      }
    }
    // 已绑 room 但供给不就绪：**不透传旧式**（那会造第二个 doc key），给原因。
    if (bound && identity.reason !== null) {
      return {
        protocol: 'room',
        available: false,
        config: null,
        reason: identity.reason,
        entryId: identity.entryId,
        bindingStatus: status,
        syncMode: 'bound',
      }
    }
    // readiness 层给了原因且没有 binding 结论：与改动前一致，透传不调旧端点。
    // （`status === null` 时 `bound === roomReady`，故 `!bound && reason` 就是
    //  「未就绪且有原因」—— 与改动前逐字等价。）
    if (!bound && status === null && identity.reason !== null) {
      return {
        protocol: 'room',
        available: false,
        config: null,
        reason: identity.reason,
        entryId: identity.entryId,
        bindingStatus: null,
        syncMode: 'independent',
      }
    }
    // `pending` / `out_of_scope` / 无 binding ⇒ 落到旧式（下面统一处理）。
  }

  const legacy = await probeLegacy(wpId, sheetName)
  return {
    protocol: 'legacy',
    available: legacy.config !== null,
    config: legacy.config,
    reason: legacy.reason,
    entryId: null,
    bindingStatus: legacy.bindingStatus,
    syncMode: legacy.syncMode,
  }
}

/** 旧式兼容壳：既有调用方只要 boolean 时用这个。 */
export async function canOpenOnlyOfficeEntry(input: {
  projectId?: string
  wpId: string
  sheetName: string
  wholeWorkbook?: boolean
}): Promise<boolean> {
  const probe = await probeOnlyOfficeEntryConfig(input)
  return probe.available
}

/** 不可切时的中文原因；可切时返回 null。 */
export async function onlyOfficeEntryUnavailableReason(input: {
  projectId?: string
  wpId: string
  sheetName: string
  wholeWorkbook?: boolean
}): Promise<string | null> {
  const probe = await probeOnlyOfficeEntryConfig(input)
  return probe.available ? null : probe.reason
}
