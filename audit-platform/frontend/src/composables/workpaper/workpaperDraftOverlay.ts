/**
 * 底稿宿主的「当前未保存草稿」访问器（draft overlay 的前端一半）。
 *
 * Feature: chat-host-draft-overlay / Task 4（design §5 前端要点 1）
 *
 * ## 为什么要有注册表
 *
 * AI 面板（`DshPanel` 挂在全局布局里、`AIChatView` 在独立窗口）与底稿编辑器**不在同一棵
 * 组件树上**，面板拿不到编辑器实例。平台既有做法是按 wpId 建一个进程内登记表把横切能力
 * 桥过去（先例 `components/workpaper/sync/backgroundMergeRegistry.ts`），本模块沿用同一形态：
 *
 * * 编辑器（HTML / Univer 各一次）在 setup 里 `useWorkpaperDraftAccessor(...)` 登记自己；
 * * 卸载时注销（只注销**自己那条**，不误删后来者）；
 * * 面板侧经 `readWorkpaperDraftOverlay(wpId)` 统一读取。
 *
 * ## 三个值分别是什么
 *
 * * `hasUnsaved()` —— 编辑器是否还有未保存修改（面板据它决定是否显示开关）。
 * * `currentDraftContent()` —— **编辑器内存里**的未保存正文；没有未保存修改时返回 `null`。
 * * `openedBaselineVersion()` —— **打开编辑器那一刻**宿主的业务版本，用于服务端判定
 *   「这份草稿基于哪一版」。它必须**冻结在打开时**：保存后宿主的版本会前进，若这里跟着变，
 *   过期检测就永远通过（需求 6.3 禁止的 fail-open）。
 *
 * ## 版本口径必须与后端逐字一致
 *
 * 后端权威来源是 `working_paper.updated_at`（常量
 * `app.services.ai_chat.draft_overlay.WORKPAPER_BUSINESS_VERSION_SOURCE`），并且用
 * `normalize_business_version()` 归一后再逐字比对（`versions_match()`，fail-closed）。
 * 前端只要归一结果差一个字符，**每一次**提交都会被判 `denied`（草稿基于旧版本）。
 * 因此本模块的 `normalizeBusinessVersion` 是那个 Python 函数的逐行为镜像，并由
 * `workpaperDraftOverlay.spec.ts` 直接读 Python 源码做跨语言对账。
 *
 * ## HTML 侧为什么要多一层「草稿源」
 *
 * 一张 HTML 底稿由**一个** sheet 宿主组件渲染，未保存内容在它自己的响应式状态里
 * （K/J 两个循环已经统一走 `useChecklistPersistence` 的 `responses` + `pending`）。
 * 宿主数量大（160+ 个 `checklist-responses` 写入方），不可能逐个改；因此这里提供
 * `publishHtmlDraftSource`：**已经统一走共享持久化适配器**的宿主由适配器一处登记，
 * 其余宿主以后接入同一行即可，不必再动本模块。
 */

import { getCurrentScope, onScopeDispose, ref, watch } from 'vue'

// ---------------------------------------------------------------------------
// 后端常量镜像（单一真源在后端；此处镜像并由跨语言守卫对账）
// ---------------------------------------------------------------------------

/** 底稿宿主「当前业务版本」的权威列（镜像后端 `WORKPAPER_BUSINESS_VERSION_SOURCE`）。 */
export const WORKPAPER_BUSINESS_VERSION_SOURCE = 'working_paper.updated_at'

/** 未保存草稿正文字符上限（镜像后端 `MAX_DRAFT_OVERLAY_CHARS`）。 */
export const MAX_DRAFT_OVERLAY_CHARS = 200_000

/** 第一批接受 `draft_overlay` 的宿主类型（镜像后端 `DRAFT_OVERLAY_HOST_TYPES`）。 */
export const DRAFT_OVERLAY_HOST_TYPES = ['workpaper'] as const

export type DraftOverlayHostType = (typeof DRAFT_OVERLAY_HOST_TYPES)[number]

// ---------------------------------------------------------------------------
// 版本归一（镜像后端 `normalize_business_version`）
// ---------------------------------------------------------------------------

/**
 * 后端 `datetime.fromisoformat` 接受的**扩展格式**子集：
 * `YYYY-MM-DD[ T]HH:MM[:SS[.f{1,}]]`，可带 `Z`（**只认大写**）或 `±HH[:MM]` / `±HHMM`。
 *
 * 不认的形状原样返回（与后端一致：宁可比对失败判 `denied`，也不猜）。
 *
 * 🔴 与后端的三处刻意对齐（都由跨语言对账用例逐条钉住）：
 * * 小写 `z` **不认** —— Python `fromisoformat` 只认大写，后端会原样返回，
 *   前端若认了就会把它归一到 `+00:00` ⇒ 两侧不等 ⇒ 假 `denied`；
 * * 秒必须 `00..59`（Python 对 `:60` 抛 ValueError ⇒ 后端原样返回）；
 * * 日期必须是真实日历日（`2026-02-30` 后端 ValueError ⇒ 原样返回）。
 *
 * 真实输入只有一种来源 —— `wpDetail.updated_at` = Python `datetime.isoformat()`，
 * 因此恒是 `YYYY-MM-DDTHH:MM:SS[.ffffff][+00:00]` 形态。下面这两处宽松（逗号小数、
 * 两位时区）是照 `fromisoformat` 顺手对齐；basic format / ISO 周日期这类生产不会出现的
 * 写法前端原样返回、后端归一 ⇒ 只会更保守地判 `denied`，方向是安全的。
 */
const ISO_LIKE_RE =
  /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?(Z|[+-]\d{2}(?::?\d{2})?)?$/

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

/** 该 `Y-M-D` 是否真实存在的日历日（`Date.UTC` 会把 2 月 30 日滚到 3 月，故按回读比对）。 */
function isRealCalendarDay(year: number, month: number, day: number): boolean {
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > 31) return false
  const probe = new Date(Date.UTC(year, month - 1, day))
  return (
    probe.getUTCFullYear() === year
    && probe.getUTCMonth() === month - 1
    && probe.getUTCDate() === day
  )
}

/**
 * 把宿主业务版本渲染成**可逐字比对**的 canonical 字符串。
 *
 * 逐条镜像后端 `app/services/ai_chat/draft_overlay.py::normalize_business_version`：
 *
 * * `null` / `undefined` / 空串 → `''`（由调用方决定怎么判，本函数不猜）；
 * * 能解析 → 转成 UTC 后按 Python `datetime.isoformat()` 的形状输出
 *   （`2026-11-15T10:00:00+00:00`；微秒非 0 时补 `.ffffff`，为 0 时**不写**小数点段）；
 * * 认不出 → 原样返回（去首尾空白）。
 *
 * 🔴 微秒必须逐位保留、不能被 `Date` 截成毫秒：PG `timestamptz` 的 `updated_at` 带 6 位
 * 小数，而 `updated_at.isoformat()` 会原样带出来。用 `new Date(...)` 再 `toISOString()`
 * 会把 `…123456` 变成 `…123000` ⇒ 与后端永不相等 ⇒ 每次都被判「草稿基于旧版本」。
 * 所以整秒部分用 `Date` 换算时区，小数部分按**字符串**保留。
 */
export function normalizeBusinessVersion(raw: unknown): string {
  if (raw === null || raw === undefined) return ''
  const text = String(raw).trim()
  if (!text) return ''
  const matched = ISO_LIKE_RE.exec(text)
  if (!matched) return text
  const [, year, month, day, hour = '00', minute = '00', second = '00', fraction = '', zone] =
    matched
  const numbers = [year, month, day, hour, minute, second].map(Number)
  if (numbers.some((n) => !Number.isFinite(n))) return text
  const [y, mo, d, hh, mi, ss] = numbers
  if (!isRealCalendarDay(y, mo, d) || hh > 23 || mi > 59 || ss > 59) return text

  let offsetMinutes = 0
  if (zone && zone !== 'Z') {
    const digits = zone.slice(1).replace(':', '')
    const oh = Number(digits.slice(0, 2))
    const om = Number(digits.slice(2, 4) || '0')
    if (!Number.isFinite(oh) || !Number.isFinite(om) || oh > 23 || om > 59) return text
    offsetMinutes = (zone[0] === '-' ? -1 : 1) * (oh * 60 + om)
  }

  const epochMs = Date.UTC(y, mo - 1, d, hh, mi, ss) - offsetMinutes * 60_000
  const utc = new Date(epochMs)
  if (Number.isNaN(utc.getTime())) return text

  const stamp =
    `${utc.getUTCFullYear()}-${pad2(utc.getUTCMonth() + 1)}-${pad2(utc.getUTCDate())}`
    + `T${pad2(utc.getUTCHours())}:${pad2(utc.getUTCMinutes())}:${pad2(utc.getUTCSeconds())}`
  // Python `isoformat()`：微秒为 0 时**不写**小数点段；非 0 时恒 6 位（不足补零、超出截断）。
  const micros = fraction ? fraction.padEnd(6, '0').slice(0, 6) : ''
  const fractional = micros && micros !== '000000' ? `.${micros}` : ''
  return `${stamp}${fractional}+00:00`
}

// ---------------------------------------------------------------------------
// 编辑器侧契约
// ---------------------------------------------------------------------------

/**
 * 宿主暴露给 AI 面板的三个值（HTML 与 Univer 两个编辑器各实现一次，形状完全一致）。
 *
 * 三者都是**取值函数**而不是 ref 快照：面板在提交那一刻取值（用户可能刚又改了一格），
 * 传快照会让「点了开关之后又改一处」的内容被静默漏掉。
 */
export interface WorkpaperDraftAccessor {
  /** 当前 wpId（编辑器可能因路由复用而换底稿；读取时按它比对）。 */
  readonly wpId: () => string
  /** 是否还有未保存修改（**廉价判据**：面板每次重算都会问它）。 */
  hasUnsaved(): boolean
  /** 编辑器内存里的未保存正文；**没有未保存修改时必须返回 `null`**。 */
  currentDraftContent(): string | null
  /** 打开编辑器时的宿主业务版本（已归一）；取不到返回 `null`。 */
  openedBaselineVersion(): string | null
}

/** 面板侧统一读取的产物（三项都成立才有值）。 */
export interface WorkpaperDraftOverlay {
  /** 未保存正文。 */
  readonly content: string
  /** 归一后的基线版本（`UTC ISO-8601`，与后端可比）。 */
  readonly baselineVersion: string
  /** 正文字符数（= `content.length`；服务端仍会重算）。 */
  readonly contentLength: number
}

// ---------------------------------------------------------------------------
// 访问器注册表
// ---------------------------------------------------------------------------

interface Registration {
  readonly accessor: WorkpaperDraftAccessor
}

/**
 * 🔴 用**普通 Map** + 版本号，不用 `reactive(new Map())`。
 *
 * `reactive` 的 Map 会把存进去的对象包成 Proxy：`map.get(key).accessor` 拿到的是
 * **代理**，与调用方手里的原对象 `!==` ⇒ 「注销只删自己那条」的恒等判断恒假，访问器
 * 永远删不掉（实测：注销后 `hasWorkpaperDraftOverlay` 仍为 true）。而且面板读到的也是
 * 代理，`toBe(原对象)` 这类判据一并失效。
 *
 * 响应式改由 `registryVersion` 承担：登记 / 注销时 +1，读取方先读它建立依赖。
 * 访问器**内部**的响应式状态（`dirty` / `pendingCount` 这些 ref）在 `isDirty()` 里被读，
 * 由 computed 自然追踪 —— 所以「改了但没保存」仍能实时驱动面板重算。
 */
const registrations = new Map<symbol, Registration>()
const registryVersion = ref(0)

function bumpRegistry(): void {
  registryVersion.value += 1
}

/**
 * 登记一个编辑器的访问器；返回只注销**本条**的函数（同一 wpId 后来者覆盖读取结果，
 * 但先注销的那一条不会把后来者一起删掉 —— 与 `backgroundMergeRegistry` 同一取向）。
 */
export function registerWorkpaperDraftAccessor(
  accessor: WorkpaperDraftAccessor,
): () => void {
  const key = Symbol('workpaperDraftAccessor')
  registrations.set(key, { accessor })
  bumpRegistry()
  return () => {
    if (registrations.get(key)?.accessor === accessor) {
      registrations.delete(key)
      bumpRegistry()
    }
  }
}

/** 取该底稿当前登记的访问器；同一 wpId 有多条时取**最后登记**的一条（最新的编辑器实例）。 */
export function workpaperDraftAccessorOf(
  wpId: string | null | undefined,
): WorkpaperDraftAccessor | null {
  // 读一次版本号建立响应式依赖（面板的 computed 据此在登记 / 注销后重算）。
  void registryVersion.value
  if (!wpId) return null
  let found: WorkpaperDraftAccessor | null = null
  for (const { accessor } of registrations.values()) {
    if (accessor.wpId() === wpId) found = accessor
  }
  return found
}

/** 测试隔离用。 */
export function clearWorkpaperDraftAccessors(): void {
  registrations.clear()
  bumpRegistry()
}

// ---------------------------------------------------------------------------
// 编辑器侧登记 composable（两个编辑器各调用一次）
// ---------------------------------------------------------------------------

export interface UseWorkpaperDraftAccessorOptions {
  /** 当前 wpId（响应式；路由复用换底稿时读取最新值）。 */
  wpId: () => string
  /**
   * 宿主**当前**业务版本原始值（= `wpDetail.updated_at`）。
   *
   * 🔴 本 composable 只取**首次非空**的那一个并永久冻结：它就是「打开编辑器时」的版本。
   * 之后保存会让这个值前进，跟着变就等于把过期检测关掉（需求 6.3）。
   */
  currentBusinessVersion: () => unknown
  /** 编辑器是否还有未保存修改。 */
  isDirty: () => boolean
  /** 取内存正文（只在 `isDirty()` 为真时被调用；取不到返回 `null`）。 */
  collectContent: () => string | null
}

/**
 * 编辑器侧一次性登记：冻结基线版本 → 注册访问器 → 卸载时注销。
 *
 * 必须在组件 `setup` 里调用（依赖 `onScopeDispose` 自动注销；scope 外调用时只在本次
 * 调用的生命周期内有效，单测可用返回的注销函数手工清理）。
 */
export function useWorkpaperDraftAccessor(
  options: UseWorkpaperDraftAccessorOptions,
): () => void {
  let frozenBaseline: string | null = null

  const freeze = (raw: unknown): void => {
    if (frozenBaseline !== null) return
    const normalized = normalizeBusinessVersion(raw)
    if (normalized) frozenBaseline = normalized
  }

  // 立即取一次（编辑器挂载时 wpDetail 通常已就绪），并持续盯到第一次拿到真值为止。
  // 拿到之后 `freeze` 自己短路，不再跟随后续变化。
  watch(
    () => options.currentBusinessVersion(),
    (raw) => freeze(raw),
    { immediate: true },
  )

  const accessor: WorkpaperDraftAccessor = {
    wpId: () => options.wpId(),
    hasUnsaved: () => options.isDirty() === true,
    currentDraftContent: () => (options.isDirty() === true ? options.collectContent() : null),
    openedBaselineVersion: () => frozenBaseline,
  }
  const unregister = registerWorkpaperDraftAccessor(accessor)
  if (getCurrentScope()) onScopeDispose(unregister)
  return unregister
}

// ---------------------------------------------------------------------------
// HTML 侧「草稿源」登记（由共享持久化适配器一处登记，覆盖所有接入它的宿主）
// ---------------------------------------------------------------------------

/**
 * 一个 HTML sheet 宿主的未保存内容来源。
 *
 * 之所以要多这一层：`GtWpRenderer` 是 HTML 分发壳，真正的未保存内容在**它渲染的那个
 * sheet 宿主组件**里（如 `GtK1OtherReceivables`）。宿主数量 160+，逐个改不现实；
 * 已经统一走 `useChecklistPersistence` 的宿主由适配器一处 `publishHtmlDraftSource` 登记，
 * 其余宿主以后接入同一行即可。
 */
export interface HtmlDraftSource {
  /** 便于排查（宿主 / 适配器名，出现在诊断信息里）。 */
  readonly label: string
  hasUnsaved(): boolean
  currentDraftContent(): string | null
}

interface HtmlSourceRegistration {
  readonly wpIdOf: () => string
  readonly source: HtmlDraftSource
}

const htmlSources = new Map<symbol, HtmlSourceRegistration>()
const htmlSourceVersion = ref(0)

/** 登记一个 HTML 宿主的草稿源；返回只注销**本条**的函数。 */
export function publishHtmlDraftSource(
  wpIdOf: string | (() => string),
  source: HtmlDraftSource,
): () => void {
  const key = Symbol('htmlDraftSource')
  const wpIdOfFn = typeof wpIdOf === 'function' ? wpIdOf : () => wpIdOf
  htmlSources.set(key, { wpIdOf: wpIdOfFn, source })
  htmlSourceVersion.value += 1
  return () => {
    if (htmlSources.get(key)?.source === source) {
      htmlSources.delete(key)
      htmlSourceVersion.value += 1
    }
  }
}

/** 测试隔离用。 */
export function clearHtmlDraftSources(): void {
  htmlSources.clear()
  htmlSourceVersion.value += 1
}

/**
 * 汇总该底稿全部 HTML 草稿源。
 *
 * 同一 wpId 可能短暂存在多个源（切 sheet 时新旧组件交接）；内容按登记顺序拼接并去掉
 * 完全相同的重复片段（两个宿主同时报同一份正文时不该算两遍）。
 */
export function readHtmlDraft(
  wpId: string | null | undefined,
): { content: string | null; hasUnsaved: boolean } {
  // 读一次版本号建立响应式依赖（见 `registrations` 的注释：用普通 Map 才不会把访问器包成 Proxy）。
  void htmlSourceVersion.value
  if (!wpId) return { content: null, hasUnsaved: false }
  const parts: string[] = []
  let hasUnsaved = false
  for (const registration of htmlSources.values()) {
    if (registration.wpIdOf() !== wpId) continue
    if (registration.source.hasUnsaved() !== true) continue
    hasUnsaved = true
    const content = registration.source.currentDraftContent()
    if (typeof content === 'string' && content.trim() && !parts.includes(content)) {
      parts.push(content)
    }
  }
  return { content: parts.length > 0 ? parts.join('\n') : null, hasUnsaved }
}

// ---------------------------------------------------------------------------
// 面板侧统一读取
// ---------------------------------------------------------------------------

/** 该底稿此刻是否有未保存修改（面板据此决定是否显示开关；廉价，不序列化正文）。 */
export function hasWorkpaperDraftOverlay(wpId: string | null | undefined): boolean {
  const accessor = workpaperDraftAccessorOf(wpId)
  return accessor !== null && accessor.hasUnsaved() === true
}

/**
 * 面板侧统一读取：**没有未保存修改时返回 `null`**（任务正文：`useAiHostContext` 统一读取，
 * 无未保存修改时返回 `null`）。
 *
 * 四处 fail-closed（任一不成立都不给 overlay，而不是给一份必被服务端拒的草稿）：
 *
 * 1. 没有编辑器登记（不在底稿编辑器里 / 面板先于编辑器挂载）；
 * 2. 正文为空（`null` / 全空白）；
 * 3. 基线版本为空 —— 后端 `versions_match()` 对空串是 fail-closed 的，前端先挡住，
 *    免得用户看到「将纳入」却被服务端拒绝；
 * 4. 正文超过 `MAX_DRAFT_OVERLAY_CHARS` —— 后端超限直接 422（**不裁剪**），
 *    放行会让整轮对话失败，所以这里不给 overlay。
 */
export function readWorkpaperDraftOverlay(
  wpId: string | null | undefined,
): WorkpaperDraftOverlay | null {
  const accessor = workpaperDraftAccessorOf(wpId)
  if (!accessor || accessor.hasUnsaved() !== true) return null
  const content = accessor.currentDraftContent()
  if (typeof content !== 'string' || !content.trim()) return null
  const baselineVersion = normalizeBusinessVersion(accessor.openedBaselineVersion())
  if (!baselineVersion) return null
  if (content.length > MAX_DRAFT_OVERLAY_CHARS) return null
  return { content, baselineVersion, contentLength: content.length }
}
