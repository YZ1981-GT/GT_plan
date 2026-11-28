import type { EntrySyncReadiness, EntrySyncReadinessReason } from './workpaperSyncApi'

/**
 * `revalidating` = 已有可展示的 readiness（generated manifest 的静态裁决，或上一次的运行时
 * 结果），同时正在重取运行时状态。
 *
 * 🔴 为什么需要第三态：宿主首帧就要决定「模式开关显不显示」。只有 loading/ready/error 时，
 * 转成单源的宿主在首帧必然落 `loading`（不显示开关）⇒ 运行时结果回来后开关才出现，产生可见
 * 闪跳；而若拿静态兜底直接当 `ready`，它的 `runtime.ready` 只是占位值（非实测），会误显示
 * 「在线编辑不可用」。第三态按静态裁决给可见性、把「尚未核验」如实写进提示，且**不**套用
 * 运行时不可用那条红色分支。真正的写入闸门在统一桥 flush 前的 readiness 复查，不在这里。
 */
export type EntrySyncLoadState = 'loading' | 'revalidating' | 'ready' | 'error'

/**
 * 「尚未裁决」提示的文案真源。
 *
 * 🔴 为什么声明在这里：`eaa655686` 把提示链路改成 `useEntrySyncReadiness` →
 * `deriveEntrySyncPresentation` 之后，活路径上的文案只由本文件产出，而原来的真源
 * `workpaperEntrySyncNotice.ts` 退化成 0 调用方的兼容入口。当时把两句中文**又抄了
 * 一份**进下面的 `capability === null` 分支 ⇒ 同一句话有两个声明点，改一处另一处静默
 * 不动。现在反过来：本文件声明、兼容入口再导出，声明点只剩一个。
 */
export const ENTRY_SYNC_NOTICE_LABEL = '两侧数据未互通'
export const ENTRY_SYNC_NOTICE_SUMMARY = '结构化视图与在线编辑尚未形成已验收的双向链路'

export interface EntrySyncPresentation {
  readonly showHtml: boolean
  readonly showOnlyOffice: boolean
  readonly showModeSwitch: boolean
  readonly canSwitchToHtml: boolean
  readonly canSwitchToOnlyOffice: boolean
  readonly canClaimBidirectional: boolean
  readonly noticeKind: 'none' | 'info' | 'warning' | 'danger'
  readonly noticeLabel: string
  readonly noticeSummary: string
  readonly noticeReason: string
}

const EMPTY: EntrySyncPresentation = {
  showHtml: true,
  showOnlyOffice: false,
  showModeSwitch: false,
  canSwitchToHtml: true,
  canSwitchToOnlyOffice: false,
  canClaimBidirectional: false,
  noticeKind: 'none',
  noticeLabel: '',
  noticeSummary: '',
  noticeReason: '',
}

function notice(
  base: EntrySyncPresentation,
  kind: EntrySyncPresentation['noticeKind'],
  label: string,
  summary: string,
  reason: EntrySyncReadinessReason | null,
): EntrySyncPresentation {
  const detail = reason
    ? `${reason.message}${reason.next_action ? ` ${reason.next_action}` : ''}`
    : summary
  return { ...base, noticeKind: kind, noticeLabel: label, noticeSummary: summary, noticeReason: detail }
}

/**
 * 「尚无首版、但可在首次进入在线编辑时自动发布」。
 *
 * 首版只在首次进入在线编辑时由桥按需发布（`ensureFirstPublication`，spec
 * d2-online-edit-platform-closure R7）。此时 `runtime.ready` 如实为 false，但不能据此藏起入口、
 * 也不能在桥里拒绝 —— 否则首版永远发不出来。页面展示与桥的放行共用这一个判据。
 */
export function isFirstPublicationPending(readiness: EntrySyncReadiness | null): boolean {
  return readiness !== null
    && readiness.capability === 'bidirectional'
    && readiness.allowed_modes.includes('oo')
    && !readiness.runtime.ready
    && readiness.reason?.code === 'REPRESENTATION_MISSING'
}

export function deriveEntrySyncPresentation(
  readiness: EntrySyncReadiness | null,
  loadState: EntrySyncLoadState,
): EntrySyncPresentation {
  if (loadState === 'loading') {
    return notice(EMPTY, 'info', '正在核验同步状态', '正在核验当前底稿的在线编辑能力', null)
  }
  if (loadState === 'error' || readiness === null) {
    return notice(
      EMPTY, 'danger', '同步状态读取失败',
      '当前仅保留结构化视图，请重试同步状态检查', null,
    )
  }

  const modes = new Set(readiness.allowed_modes)
  const base: EntrySyncPresentation = {
    ...EMPTY,
    showHtml: modes.has('html'),
    showOnlyOffice: modes.has('oo'),
    canSwitchToHtml: modes.has('html'),
    canSwitchToOnlyOffice: false,
  }

  if (loadState === 'revalidating') {
    // 按静态裁决给可见性；`runtime.ready` 此刻还不是实测值 ⇒ 不套用下面那条红色分支，
    // 也不宣称已验收双向。开关可点，真正放行与否由统一桥 flush 前的复查决定。
    const bidirectional = readiness.capability === 'bidirectional'
    return notice(
      {
        ...base,
        showModeSwitch: bidirectional,
        canSwitchToOnlyOffice: bidirectional && modes.has('oo'),
        canClaimBidirectional: false,
      },
      'info',
      '正在核验同步状态',
      '已按裁决结果显示入口，运行时同步状态仍在核验',
      null,
    )
  }
  if (readiness.capability === 'unreachable') {
    return notice(
      { ...base, showHtml: false, showOnlyOffice: false, canSwitchToHtml: false },
      'danger', '入口不可用', '该入口已由新实现替代', readiness.reason,
    )
  }
  if (readiness.capability === 'single_html') {
    return { ...base, showHtml: true, showOnlyOffice: false }
  }
  if (readiness.capability === 'single_onlyoffice') {
    return { ...base, showHtml: false, showOnlyOffice: true }
  }
  if (readiness.capability === null) {
    return notice(
      { ...base, showModeSwitch: false },
      'warning', ENTRY_SYNC_NOTICE_LABEL,
      ENTRY_SYNC_NOTICE_SUMMARY, readiness.reason,
    )
  }
  if (
    readiness.capability === 'bidirectional'
    && readiness.reason?.code === 'REPRESENTATION_MISSING'
  ) {
    // 首版尚未发布不是不可恢复的运行时故障。桥会先调用 first-publication，
    // 成功后再按新 revision 创建 materialize；把入口藏掉会让首版路径永远不可达。
    // 与桥的放行同一判据（只看能力与原因码，后端旧版对尚无首版只放行 html 也照样开放）；
    // isFirstPublicationPending 是其收窄版（另要求后端放行 oo），满足它的必然先命中这里。
    // 尚未发布 ⇒ 不宣称已验收双向。
    return notice(
      {
        ...base,
        showHtml: true,
        showOnlyOffice: true,
        showModeSwitch: true,
        canSwitchToHtml: true,
        canSwitchToOnlyOffice: true,
        canClaimBidirectional: false,
      },
      'warning',
      '首次在线编辑将发布版本',
      '该底稿尚未发布在线编辑版本；切换后将先创建首版并进入在线编辑',
      readiness.reason,
    )
  }
  if (!readiness.runtime.ready) {
    return notice(
      { ...base, showHtml: true, showOnlyOffice: false, canSwitchToHtml: true },
      'danger', '在线编辑不可用',
      '当前 adapter、契约或发布版本未通过运行时校验', readiness.reason,
    )
  }
  const ready: EntrySyncPresentation = {
    ...base,
    showHtml: true,
    showOnlyOffice: true,
    showModeSwitch: true,
    canSwitchToHtml: true,
    canSwitchToOnlyOffice: true,
    canClaimBidirectional: true,
  }
  if (readiness.acceptance.state !== 'verified') {
    return notice(
      ready, 'warning', '验收证据待更新',
      '双向链路可用，但真实 OnlyOffice 验收证据尚未通过当前身份校验', readiness.reason,
    )
  }
  return ready
}
