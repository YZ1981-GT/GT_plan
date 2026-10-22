/**
 * 公式全局设置 / 本项目适配 / 待确认 / 公式模板的请求封装（spec formula-global-settings-sync）。
 *
 * 全部带 `_silent`：错误提示由调用方给（全局拦截器会先弹一次笼统提示，428 还会被当成系统错误），
 * 文案用 `formulaErrorText`。删除类请求（恢复为全局、删除模板）由调用方先做二次确认。
 * 类型与小工具见 `@/composables/formula/useFormulaSettings`。
 */
import { api } from '@/services/apiProxy'
import {
  formulaSettings as P, projectFormulaSettings as PP,
  formulaTemplates as PT, projectFormulaTemplates as PPT,
} from '@/services/apiPaths'
import type {
  ApplyTarget, ApplyTargetKind, CheckRuleSource, Decisions, Definition, EffectiveResult, FormulaDomainInfo,
  FormulaTemplateInfo, GlobalSlot, PendingItem, PublishRecord, Resolution, SlotChange, SyncPreview, TemplateDetail,
  TemplateSubscriber, TemplateSubscription, TemplateVersion,
} from '@/composables/formula/useFormulaSettings'

// ── 请求 ──────────────────────────────────────────────────────────────────────

const silent = (extra: Record<string, unknown> = {}) => ({ ...extra, _silent: true }) as any
/** FastAPI 的 `list[str] = Query(...)` 要 `k=a&k=b`（axios 默认是 `k[]=a`） */
const repeatParams = { indexes: null }

export const formulaSettingsApi = {
  domains: () => api.get<{ domains: FormulaDomainInfo[]; is_admin: boolean }>(P.domains, silent()),
  global: (domain: string, scope: string) =>
    api.get<{ domain: string; scope: string; can_edit: boolean; slots: GlobalSlot[] }>(
      P.global(domain), silent({ params: { scope } })),
  previewGlobal: (domain: string, body: { scope: string; changes: SlotChange[] }) =>
    api.post<SyncPreview>(P.globalPreview(domain), body, silent()),
  publishGlobal: (domain: string, body: {
    scope: string; changes: SlotChange[]; decisions: Decisions; request_id: string; note?: string
  }) => api.post<Record<string, any>>(P.globalPublish(domain), body, silent()),
  publishes: (params: { domain?: string; scope?: string; status?: string; limit?: number } = {}) =>
    api.get<{ items: PublishRecord[] }>(P.publishes, silent({ params })),
  candidatePreview: (id: string) => api.post<SyncPreview>(P.candidatePreview(id), {}, silent()),
  reviewCandidate: (id: string, body: { approve: boolean; decisions?: Decisions; note?: string }) =>
    api.post<Record<string, any>>(P.candidateReview(id), body, silent()),
  checkRules: (params: { source?: string; q?: string } = {}) =>
    api.get<{ sources: CheckRuleSource[]; total: number }>(P.checkRules, silent({ params })),

  pending: (pid: string) =>
    api.get<{ project_id: string; count: number; items: PendingItem[] }>(PP.pending(pid), silent({ _dedupe: false })),
  /** `recalc_domains`：有效定义真的变了（会重算）的域；全选「保留本项目」时为空 */
  resolve: (pid: string, resolutions: Resolution[]) =>
    api.post<{ resolved: Array<Record<string, any>>; recalc_domains?: string[] }>(PP.resolve(pid), { resolutions }, silent()),
  applyTargets: (pid: string, domain: string) =>
    api.get<{ items: ApplyTarget[] }>(PP.applyTargets(pid), silent({ params: { domain } })),
  effective: (pid: string, domain: string) => api.get<EffectiveResult>(PP.effective(pid, domain), silent()),
  saveOverrides: (pid: string, domain: string, items: SlotChange[]) =>
    api.put<{ saved: Array<{ slot_key: string; version: number | null }> }>(
      PP.overrides(pid, domain), { items }, silent()),
  restoreGlobal: (pid: string, domain: string, slotKeys: string[]) =>
    api.delete<{ restored: string[] }>(PP.overrides(pid, domain),
      silent({ params: { slot_key: slotKeys }, paramsSerializer: repeatParams })),
  applyPreview: (pid: string, domain: string, body: { target: ApplyTargetKind; slot_keys: string[]; project_ids?: string[] }) =>
    api.post<SyncPreview>(PP.applyPreview(pid, domain), body, silent()),
  apply: (pid: string, domain: string, body: {
    target: ApplyTargetKind; slot_keys: string[]; project_ids?: string[]; decisions: Decisions
    request_id: string; note?: string
  }) => api.post<Record<string, any>>(PP.apply(pid, domain), body, silent()),

  templates: (params: { domain?: string; scope?: string } = {}) =>
    api.get<{ items: FormulaTemplateInfo[]; is_admin: boolean }>(PT.list, silent({ params })),
  template: (id: string) => api.get<TemplateDetail>(PT.detail(id), silent()),
  createTemplate: (body: Record<string, any>) => api.post<TemplateDetail>(PT.list, body, silent()),
  updateTemplate: (id: string, body: Record<string, any>) => api.put<TemplateDetail>(PT.detail(id), body, silent()),
  deleteTemplate: (id: string) => api.delete<{ id: string; deleted: boolean }>(PT.detail(id), silent()),
  templateVersions: (id: string) => api.get<{ items: TemplateVersion[] }>(PT.versions(id), silent()),
  templateSubscribers: (id: string) => api.get<{ items: TemplateSubscriber[] }>(PT.subscribers(id), silent()),
  templatePublishPreview: (id: string, body: { expected_version: number; changes: Array<{ domain: string; slot_key: string; definition: Definition | null }> }) =>
    api.post<SyncPreview>(PT.publishPreview(id), body, silent()),
  templatePublish: (id: string, body: {
    expected_version: number; changes: Array<{ domain: string; slot_key: string; definition: Definition | null }>
    decisions: Decisions; request_id: string; note?: string
  }) => api.post<Record<string, any>>(PT.publish(id), body, silent()),
  templatePromotePreview: (id: string, body: { domain: string; slot_keys?: string[] | null }) =>
    api.post<SyncPreview>(PT.promotePreview(id), body, silent()),
  templatePromote: (id: string, body: { domain: string; slot_keys?: string[] | null; decisions?: Decisions; request_id: string; note?: string }) =>
    api.post<Record<string, any>>(PT.promote(id), body, silent()),

  subscriptions: (pid: string) => api.get<{ items: TemplateSubscription[] }>(PPT.subscriptions(pid), silent()),
  subscribePreview: (pid: string, body: { template_id: string; domain: string }) =>
    api.post<SyncPreview>(PPT.subscribePreview(pid), body, silent()),
  subscribe: (pid: string, body: { template_id: string; domain: string; decisions: Decisions }) =>
    api.post<Record<string, any>>(PPT.subscribe(pid), body, silent()),
  unsubscribePreview: (pid: string, body: { domain: string; mode: 'keep' | 'global' }) =>
    api.post<SyncPreview>(PPT.unsubscribePreview(pid), body, silent()),
  unsubscribe: (pid: string, body: { domain: string; mode: 'keep' | 'global'; decisions: Decisions }) =>
    api.post<Record<string, any>>(PPT.unsubscribe(pid), body, silent()),
}
