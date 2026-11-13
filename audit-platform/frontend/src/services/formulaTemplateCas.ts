/** 模板专用跨请求 CAS 契约；不改变全局设置页与共享预览弹窗的协议。 */
import { formulaSettingsApi } from './formulaSettingsApi'
import type { Decisions, Definition, SyncPreview } from '@/composables/formula/useFormulaSettings'

export interface TemplateChange {
  domain: string
  slot_key: string
  definition: Definition | null
}
export interface TemplatePreview extends SyncPreview {
  template_id: string
  version: number
  preview_fingerprint: string
}
export interface TemplatePublishInput {
  expected_version: number
  changes: TemplateChange[]
  preview_fingerprint: string
  decisions: Decisions
  request_id: string
  note?: string
}
export type TemplateRollbackInput = Omit<TemplatePublishInput, 'changes'> & { target_version: number }

/** 本地预览证据不完整，不应被误报为网络故障。 */
export class TemplatePreviewEvidenceError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'TemplatePreviewEvidenceError'
  }
}

/** 只复制 API 的 JSON 载荷，隔离响应式对象和后续编辑。 */
export function copyTemplateValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function checkedPreview(value: SyncPreview, id: string, version: number): TemplatePreview {
  if (value?.template_id !== id || value?.version !== version
    || typeof value?.preview_fingerprint !== 'string' || !/^[0-9a-f]{64}$/.test(value.preview_fingerprint)) {
    throw new TemplatePreviewEvidenceError('模板预览缺少有效的版本证据，请重新预览后发布')
  }
  return value as TemplatePreview
}
export const formulaTemplateCasApi = {
  async publishPreview(id: string, body: Pick<TemplatePublishInput, 'expected_version' | 'changes'>) {
    return checkedPreview(await formulaSettingsApi.templatePublishPreview(id, body), id, body.expected_version)
  },
  async rollbackPreview(id: string, body: Pick<TemplateRollbackInput, 'expected_version' | 'target_version'>) {
    const preview = checkedPreview(await formulaSettingsApi.templateRollbackPreview(id, body), id, body.expected_version)
    if (preview.target_version !== body.target_version) throw new TemplatePreviewEvidenceError('模板回滚目标已变化，请重新预览')
    return preview
  },
  publish: (id: string, body: TemplatePublishInput) => formulaSettingsApi.templatePublish(id, body),
  rollback: (id: string, body: TemplateRollbackInput) => formulaSettingsApi.templateRollback(id, body),
}

export interface TemplatePreviewContext {
  templateId: string
  version: number
  scope: string
  generation: number
  revision: number
  requestId: string
  kind: 'publish' | 'rollback' | 'promote'
  changes: TemplateChange[]
  targetVersion: number | null
  domain: string
}
export type TemplatePreviewSession = Readonly<TemplatePreviewContext & { fingerprint: string }>
