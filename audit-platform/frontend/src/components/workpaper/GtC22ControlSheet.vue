<script setup lang="ts">
/**
 * GtC22ControlSheet — C22 单个 IT 控制域测试子页（交互式）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 4.2
 * Requirements: 4.3, 4.4（+ 为 5.x/8.x 交互增强预留结构）
 *
 * Phase0 §4 子页固定区块顺序：
 *   1. 控制编号（引用矩阵 C 列）/ 控制活动（引用矩阵 D 列）
 *   2. 设计有效性：执行的审计程序 → 审计证据（含证据索引号）→ 设计有效性测试结论
 *   3. 执行有效性：测试期间 & 样本总量 → 抽样数量 → 测试步骤 → 执行有效性测试结论
 *   4. 样本记录表（抽样 > 1 时记录其余样本）
 *   5. 缺陷评估：是否发现异常 → 缺陷描述 → 索引至 <C21-1>（缺陷编号）
 *
 * 数据读写：checklist-responses（挂在 C22 父工作簿 wpId 下），
 *   item_id = `C22.{controlId}.{field}`（见 useC22BundleState.itgcItemId）。
 *   结论/枚举字段存 conclusion，其余存 remark（见 itgcFieldStorage）。
 *
 * 🔴 PM-4c 兜底（Phase0 §D3）：源模板 B1/B2 = `!#REF!`（公式损坏），
 *   本组件不依赖子页 B1/B2 取数，直接从主矩阵行（matrixRow）取控制编号/活动，
 *   并显示「公式引用已修复」提示，保证不崩。
 */
import { ref, reactive, computed, watch, onMounted, onScopeDispose, defineAsyncComponent } from 'vue'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { uploadAttachment } from '@/services/commonApi'
import { attachments as P_att } from '@/services/apiPaths'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'
import {
  itgcItemId,
  itgcFieldStorage,
  suggestEvidenceIndex,
  suggestDefectNo,
  CONCLUSION_OPTIONS,
  type TabDef,
  type ItgcField,
  type ChecklistResponse,
} from './composables/useC22BundleState'

const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

/** 主矩阵行静态内容（引用自 ITGC 控制矩阵 C/D/E 列） */
export interface MatrixRowInfo {
  row?: number
  category?: string
  risk?: string
  controlNo?: string
  description?: string
  appSystem?: string
  indexNo?: string
}

const props = defineProps<{
  wpId: string
  projectId?: string
  tab: TabDef
  matrixRow?: MatrixRowInfo | null
  readonly?: boolean
}>()

const emit = defineEmits<{
  /** 字段保存成功后通知父组件刷新完成状态/缺陷汇总 */
  (e: 'updated', controlId: string): void
}>()

const isReadonly = computed(() => props.readonly === true)
const controlId = computed(() => props.tab.id)

// ─── AI 辅助（Req 10.3：长文本字段 AI 辅助按钮） ───
const ai = useWpAiSuggest({
  wpId: props.wpId,
  sheetName: props.tab.sheet || props.tab.id,
})

/** AI 建议请求（各长文本字段右侧按钮触发） */
async function onAiRequest(field: 'designProcedure' | 'designEvidence' | 'execProcedure' | 'defectDesc'): Promise<void> {
  if (isReadonly.value || !ai.aiEnabled.value) return
  const fieldName = field === 'designProcedure' ? '设计有效性审计程序'
    : field === 'designEvidence' ? '设计有效性审计证据'
    : field === 'execProcedure' ? '执行有效性审计程序'
    : '缺陷描述'
  await ai.requestSuggestion(fieldName, form[field])
}

/** 采纳 AI 建议后填入对应字段并保存 */
function onAiAdopt(field: 'designProcedure' | 'designEvidence' | 'execProcedure' | 'defectDesc'): void {
  const text = ai.adoptSuggestion()
  if (!text) return
  form[field] = text
  const fieldMap: Record<string, ItgcField> = {
    designProcedure: 'design-procedure',
    designEvidence: 'design-evidence',
    execProcedure: 'exec-procedure',
    defectDesc: 'defect-desc',
  }
  saveNow(fieldMap[field], text)
}

// ─── 公式引用：控制编号（矩阵 C 列）/ 控制活动（矩阵 D 列） ───
// refBroken（PM-4c）时子页 B1/B2 公式损坏，回退用 tab.id + 矩阵行内容。
const controlNo = computed(
  () => props.matrixRow?.controlNo || props.tab.id,
)
const controlActivity = computed(() => props.matrixRow?.description || '')
const matrixRowNo = computed(() => props.matrixRow?.row ?? props.tab.matrixRow)
const refBroken = computed(() => props.tab.refBroken === true)

/** 公式来源提示（虚线下划线 tooltip） */
const controlNoRefTip = computed(() =>
  matrixRowNo.value
    ? `引用自 ITGC 控制矩阵 C${matrixRowNo.value} 列（控制编号）`
    : '引用自 ITGC 控制矩阵（控制编号）',
)
const controlActivityRefTip = computed(() =>
  matrixRowNo.value
    ? `引用自 ITGC 控制矩阵 D${matrixRowNo.value} 列（控制活动描述）`
    : '引用自 ITGC 控制矩阵（控制活动描述）',
)

// ─── 结论选项（点选，Req 10.1 — 从 useC22BundleState 导入） ───
const SAMPLE_RESULT_OPTIONS = ['通过', '例外'] as const

// ─── 附件上传约束（Req 11.1~11.5） ───
const OCR_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf'] as const
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20 MB

/** 审计证据附件记录 */
interface EvidenceAttachment {
  id: string       // attachment_id
  name: string     // 文件名
  index: string    // 证据索引号（如 C22.SA-3-1）
  ocrMerged: boolean // 是否已 OCR merge
}

// ─── 本地字段状态 ───
interface SampleRecord {
  seq: string
  desc: string
  result: string
  remark: string
  /** 样本行附件（📎，Req 11.1） */
  attachment?: { id: string; name: string; index: string; ocrMerged: boolean } | null
}

const form = reactive({
  designProcedure: '',   // design-procedure (remark)
  designEvidence: '',    // design-evidence (remark)
  designConclusion: '',  // design-conclusion (conclusion)
  testPeriod: '',        // test-period (remark)
  sampleSize: '',        // sample-size (remark)
  execProcedure: '',     // exec-procedure (remark)
  execConclusion: '',    // exec-conclusion (conclusion)
  abnormal: '',          // abnormal (conclusion)
  defectDesc: '',        // defect-desc (remark)
  defectNo: '',          // defect-no (remark)
})
const sampleRecords = ref<SampleRecord[]>([])
/** 审计证据区附件列表（Req 11.1/11.5） */
const evidenceAttachments = ref<EvidenceAttachment[]>([])
/** 上传中状态 */
const uploading = ref(false)

const loading = ref(false)

/** field → form 字段名 映射 */
const FIELD_TO_KEY: Record<Exclude<ItgcField, 'sample-records' | 'evidence-attachments' | 'it-category'>, keyof typeof form> = {
  'design-procedure': 'designProcedure',
  'design-evidence': 'designEvidence',
  'design-conclusion': 'designConclusion',
  'test-period': 'testPeriod',
  'sample-size': 'sampleSize',
  'exec-procedure': 'execProcedure',
  'exec-conclusion': 'execConclusion',
  'abnormal': 'abnormal',
  'defect-desc': 'defectDesc',
  'defect-no': 'defectNo',
  'app-system': 'designEvidence', // 未在本页编辑；占位（矩阵总览负责）
}

// ─── 加载 checklist-responses（仅本控制点前缀） ───
async function loadResponses(): Promise<void> {
  if (!props.wpId) return
  loading.value = true
  try {
    const res = await api.get(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { params: { project_id: props.projectId }, _silent: true } as any,
    )
    const list: ChecklistResponse[] = Array.isArray(res) ? res : ((res as any)?.data ?? [])
    const prefix = `C22.${controlId.value}.`
    const byId = new Map<string, ChecklistResponse>()
    for (const r of list) {
      if (r?.item_id && r.item_id.startsWith(prefix)) byId.set(r.item_id, r)
    }
    const readField = (field: ItgcField): string => {
      const r = byId.get(itgcItemId(controlId.value, field))
      if (!r) return ''
      return (itgcFieldStorage(field) === 'conclusion' ? r.conclusion : r.remark) ?? ''
    }
    form.designProcedure = readField('design-procedure')
    form.designEvidence = readField('design-evidence')
    form.designConclusion = readField('design-conclusion')
    form.testPeriod = readField('test-period')
    form.sampleSize = readField('sample-size')
    form.execProcedure = readField('exec-procedure')
    form.execConclusion = readField('exec-conclusion')
    form.abnormal = readField('abnormal')
    form.defectDesc = readField('defect-desc')
    form.defectNo = readField('defect-no')
    // 样本记录（JSON）
    const rawSamples = readField('sample-records')
    sampleRecords.value = parseSamples(rawSamples)
    // 审计证据附件列表（JSON，Task 8.2）
    const rawAttachments = readField('evidence-attachments')
    evidenceAttachments.value = parseEvidenceAttachments(rawAttachments)
  } catch {
    // 加载失败不阻塞，保持空表单
  } finally {
    loading.value = false
  }
}

function parseSamples(raw: string): SampleRecord[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    if (Array.isArray(arr)) {
      return arr.map((s: any) => ({
        seq: String(s?.seq ?? ''),
        desc: String(s?.desc ?? ''),
        result: String(s?.result ?? ''),
        remark: String(s?.remark ?? ''),
        attachment: s?.attachment || null,
      }))
    }
  } catch { /* 非法 JSON 忽略 */ }
  return []
}

function parseEvidenceAttachments(raw: string): EvidenceAttachment[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    if (Array.isArray(arr)) {
      return arr.map((a: any) => ({
        id: String(a?.id ?? ''),
        name: String(a?.name ?? ''),
        index: String(a?.index ?? ''),
        ocrMerged: Boolean(a?.ocrMerged),
      }))
    }
  } catch { /* 非法 JSON 忽略 */ }
  return []
}

// ─── 保存（debounce 文本 / 即时 枚举） ───
const _timers = new Map<string, ReturnType<typeof setTimeout>>()
const _pending = new Set<ItgcField>()

async function _put(field: ItgcField, value: string): Promise<void> {
  if (!props.wpId) return
  const slot = itgcFieldStorage(field)
  const item = {
    item_id: itgcItemId(controlId.value, field),
    conclusion: slot === 'conclusion' ? (value || null) : null,
    remark: slot === 'remark' ? (value || null) : null,
  }
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [item],
    })
    emit('updated', controlId.value)
  } catch {
    // 静默：保存失败保留本地值
  }
}

/** 即时保存（结论/是否异常/样本结果等枚举点选） */
function saveNow(field: ItgcField, value: string): void {
  if (isReadonly.value) return
  const t = _timers.get(field)
  if (t) { clearTimeout(t); _timers.delete(field) }
  _pending.delete(field)
  void _put(field, value)
}

/** debounce 2s 保存（长文本） */
function saveDebounced(field: ItgcField, value: string): void {
  if (isReadonly.value) return
  _pending.add(field)
  const prev = _timers.get(field)
  if (prev) clearTimeout(prev)
  const timer = setTimeout(() => {
    _timers.delete(field)
    _pending.delete(field)
    void _put(field, value)
  }, 2000)
  _timers.set(field, timer)
}

function flushPending(): void {
  for (const t of _timers.values()) clearTimeout(t)
  _timers.clear()
  for (const field of _pending) {
    if (field === 'sample-records') {
      void _put(field, JSON.stringify(sampleRecords.value))
    } else if (field === 'evidence-attachments') {
      void _put(field, JSON.stringify(evidenceAttachments.value))
    } else {
      const key = FIELD_TO_KEY[field]
      void _put(field, form[key])
    }
  }
  _pending.clear()
}

// ─── 抽样数量 → 是否显示样本记录表（抽样 > 1） ───
const sampleCount = computed(() => {
  const n = parseInt((form.sampleSize || '').replace(/[^\d]/g, ''), 10)
  return Number.isFinite(n) ? n : 0
})
const showSampleTable = computed(() => sampleCount.value > 1)

function addSampleRow(): void {
  if (isReadonly.value) return
  sampleRecords.value.push({
    seq: String(sampleRecords.value.length + 1),
    desc: '',
    result: '',
    remark: '',
  })
  persistSamples()
}
function removeSampleRow(idx: number): void {
  if (isReadonly.value) return
  sampleRecords.value.splice(idx, 1)
  persistSamples()
}
function persistSamples(): void {
  if (isReadonly.value) return
  saveNow('sample-records', JSON.stringify(sampleRecords.value))
}

// ─── 附件上传 + OCR merge（Req 11.1~11.5, Task 8.2） ───

/** 持久化证据附件列表 */
function persistAttachments(): void {
  if (isReadonly.value) return
  saveNow('evidence-attachments', JSON.stringify(evidenceAttachments.value))
}

/** 判断文件是否为 OCR 可处理类型（图片/PDF） */
function isOcrEligible(filename: string): boolean {
  const ext = filename.lastIndexOf('.') >= 0
    ? filename.slice(filename.lastIndexOf('.')).toLowerCase()
    : ''
  return (OCR_EXTENSIONS as readonly string[]).includes(ext)
}

/** 验证上传文件 */
function validateUploadFile(file: File): string | null {
  if (file.size > MAX_FILE_SIZE) {
    return `文件 "${file.name}" 大小超过 20MB 上限`
  }
  return null
}

/** 从 axios 响应解包 OCR extracted_fields（兼容 {data:{data}} 信封） */
function unwrapOcrFields(res: any): Record<string, any> {
  const data = res?.data?.data ?? res?.data ?? {}
  return data.extracted_fields || {}
}

/**
 * 审计证据区 📎 附件上传（el-upload before-upload 回调）
 * 流程：上传附件 → 关联 → 自动建议索引号 → OCR 识别 → 确认弹窗 → merge
 * Req 11.1: 附件上传
 * Req 11.2: 自动建议证据索引号
 * Req 11.3: OCR merge
 * Req 11.4: OCR 失败时提示手动填写
 * Req 11.5: 与 item_id 关联持久化
 */
async function onUploadEvidence(rawFile: File): Promise<void> {
  if (isReadonly.value) return
  const err = validateUploadFile(rawFile)
  if (err) { ElMessage.warning(err); return }

  uploading.value = true
  try {
    // 1. 上传附件到服务端
    const fd = new FormData()
    fd.append('file', rawFile)
    fd.append('attachment_type', 'evidence')
    fd.append('reference_type', 'workpaper')
    fd.append('reference_id', props.wpId)
    fd.append('title', `${rawFile.name} [${controlId.value}]`)

    const uploadResp = await uploadAttachment(props.projectId || '', fd)
    const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
    if (!attachmentId) throw new Error('上传响应缺少 attachment_id')

    // 2. 创建底稿关联
    try {
      await api.post(P_att.associate(attachmentId), {
        wp_id: props.wpId,
        association_type: 'evidence',
        notes: `sheet:${controlId.value}`,
      })
    } catch { /* 关联失败不阻断主流程 */ }

    // 3. 自动建议证据索引号（Req 11.2: C22.{控制点}-{序号}）
    const seq = evidenceAttachments.value.length + 1
    const idx = suggestEvidenceIndex(controlId.value, seq)

    // 4. 记录附件并持久化
    const attachment: EvidenceAttachment = { id: attachmentId, name: rawFile.name, index: idx, ocrMerged: false }
    evidenceAttachments.value.push(attachment)
    persistAttachments()

    // 5. OCR 流程（仅图片/PDF）
    if (isOcrEligible(rawFile.name)) {
      await doOcrMerge(rawFile, attachment)
    }

    ElMessage.success(`附件 "${rawFile.name}" 已上传，证据索引号：${idx}`)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '上传失败'
    ElMessage.error(`附件上传失败：${detail}`)
  } finally {
    uploading.value = false
  }
}

/**
 * 样本记录行 📎 上传（Req 11.1）
 * 流程同审计证据区，但附件关联到样本行内。
 */
async function onUploadSampleAttachment(rowIdx: number, rawFile: File): Promise<void> {
  if (isReadonly.value) return
  const row = sampleRecords.value[rowIdx]
  if (!row) return
  const err = validateUploadFile(rawFile)
  if (err) { ElMessage.warning(err); return }

  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', rawFile)
    fd.append('attachment_type', 'evidence')
    fd.append('reference_type', 'workpaper')
    fd.append('reference_id', props.wpId)
    fd.append('title', `${rawFile.name} [${controlId.value} 样本${row.seq}]`)

    const uploadResp = await uploadAttachment(props.projectId || '', fd)
    const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
    if (!attachmentId) throw new Error('上传响应缺少 attachment_id')

    // 关联
    try {
      await api.post(P_att.associate(attachmentId), {
        wp_id: props.wpId,
        association_type: 'evidence',
        notes: `sheet:${controlId.value}:sample:${row.seq}`,
      })
    } catch { /* 关联失败不阻断 */ }

    // 建议索引号
    const totalAttach = evidenceAttachments.value.length
      + sampleRecords.value.filter(r => r.attachment).length + 1
    const idx = suggestEvidenceIndex(controlId.value, totalAttach)

    // 存入样本行
    row.attachment = { id: attachmentId, name: rawFile.name, index: idx, ocrMerged: false }
    persistSamples()

    // OCR 流程
    if (isOcrEligible(rawFile.name)) {
      await doOcrMergeSample(rawFile, row)
    }

    ElMessage.success(`样本附件 "${rawFile.name}" 已关联`)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '上传失败'
    ElMessage.error(`样本附件上传失败：${detail}`)
  } finally {
    uploading.value = false
  }
}

/**
 * OCR 识别 + 确认弹窗 + merge 填入审计证据描述（Req 11.3/11.4）
 * 识别关键信息：制度名称/更新时间/审批时间/审批人
 */
async function doOcrMerge(file: File, attachment: EvidenceAttachment): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  let ocrFields: Record<string, any>
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = unwrapOcrFields(res)
  } catch {
    // OCR 失败（Req 11.4）：提示手动填写，附件已保留
    ElMessage.warning('OCR 识别失败，请手动填写证据信息')
    return
  }

  if (!ocrFields || Object.keys(ocrFields).length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  // 映射 OCR 字段到审计证据关键信息
  const mapped = mapOcrToEvidence(ocrFields)
  if (mapped.length === 0) {
    ElMessage.info('OCR 未识别到适用字段，请手动补充')
    return
  }

  // 确认弹窗（Req 11.3）
  const previewMsg = mapped.map(m => `${m.label}：${m.value}`).join('\n')
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下信息，确认填入审计证据描述？\n\n${previewMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return // 用户取消
  }

  // merge 到审计证据描述字段（非破坏性追加）
  const mergeText = mapped.map(m => `${m.label}：${m.value}`).join('；')
  const sep = form.designEvidence.trim() ? '\n' : ''
  form.designEvidence += `${sep}[${attachment.index}] ${mergeText}`
  saveDebounced('design-evidence', form.designEvidence)

  // 标记 OCR 已 merge
  attachment.ocrMerged = true
  persistAttachments()
  ElMessage.success(`已将 OCR 识别信息填入审计证据（索引号 ${attachment.index}）`)
}

/**
 * 样本行 OCR：识别 → 确认 → merge 填入样本描述
 */
async function doOcrMergeSample(file: File, row: SampleRecord): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  let ocrFields: Record<string, any>
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = unwrapOcrFields(res)
  } catch {
    ElMessage.warning('OCR 识别失败，请手动填写样本信息')
    return
  }

  if (!ocrFields || Object.keys(ocrFields).length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  const mapped = mapOcrToEvidence(ocrFields)
  if (mapped.length === 0) {
    ElMessage.info('OCR 未识别到适用字段，请手动补充')
    return
  }

  const previewMsg = mapped.map(m => `${m.label}：${m.value}`).join('\n')
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下信息，确认填入样本描述？\n\n${previewMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }

  // merge 到样本描述（非破坏性）
  const mergeText = mapped.map(m => `${m.label}：${m.value}`).join('；')
  const sep = row.desc.trim() ? '；' : ''
  row.desc += `${sep}${mergeText}`
  if (row.attachment) row.attachment.ocrMerged = true
  persistSamples()
  ElMessage.success('已将 OCR 识别信息填入样本描述')
}

/**
 * 映射 OCR extracted_fields 到审计证据关键信息（Req 11.3）
 * 识别字段：制度名称/更新时间/审批时间/审批人
 */
function mapOcrToEvidence(fields: Record<string, any>): Array<{ label: string; value: string }> {
  const result: Array<{ label: string; value: string }> = []
  // 按语义就近映射（兼容各种 OCR 键名）
  const nameKeys = ['title', 'name', 'policy_name', '制度名称', 'document_title', 'contract_name']
  const updateKeys = ['update_date', 'updated_at', '更新时间', 'revision_date', 'effective_date']
  const approvalDateKeys = ['approval_date', 'approved_at', '审批时间', 'signed_date', 'date']
  const approverKeys = ['approver', 'approved_by', '审批人', 'signer', 'signatory']

  for (const k of nameKeys) {
    if (fields[k]) { result.push({ label: '制度名称', value: String(fields[k]) }); break }
  }
  for (const k of updateKeys) {
    if (fields[k]) { result.push({ label: '更新时间', value: String(fields[k]) }); break }
  }
  for (const k of approvalDateKeys) {
    if (fields[k]) { result.push({ label: '审批时间', value: String(fields[k]) }); break }
  }
  for (const k of approverKeys) {
    if (fields[k]) { result.push({ label: '审批人', value: String(fields[k]) }); break }
  }
  return result
}

/** 删除证据附件（仅从列表移除记录，不物理删除服务端文件） */
function removeEvidenceAttachment(idx: number): void {
  if (isReadonly.value) return
  evidenceAttachments.value.splice(idx, 1)
  persistAttachments()
}

/** 删除样本行附件 */
function removeSampleAttachment(rowIdx: number): void {
  if (isReadonly.value) return
  const row = sampleRecords.value[rowIdx]
  if (row) {
    row.attachment = null
    persistSamples()
  }
}

// ─── 缺陷评估：是否异常 ⇒ 建议缺陷编号 ───
const showDefect = computed(() => form.abnormal === '是')

function onAbnormalChange(v: string): void {
  saveNow('abnormal', v)
  // 首次标记异常且无缺陷编号 → 建议默认编号（可编辑）
  if (v === '是' && !form.defectNo) {
    form.defectNo = suggestDefectNo(1)
    saveNow('defect-no', form.defectNo)
  }
}

/** 审计证据建议索引号（Phase0 §D8：C22.{控制点}-{序号}） */
const evidenceIndexHint = computed(() => suggestEvidenceIndex(controlId.value, evidenceAttachments.value.length + 1))

// ─── Lifecycle ───
onMounted(loadResponses)
watch(() => props.tab.id, loadResponses)
onScopeDispose(flushPending)

defineExpose({
  form,
  sampleRecords,
  evidenceAttachments,
  loadResponses,
  saveNow,
  saveDebounced,
  onAbnormalChange,
  addSampleRow,
  removeSampleRow,
  showSampleTable,
  showDefect,
  controlNo,
  controlActivity,
  refBroken,
  controlNoRefTip,
  controlActivityRefTip,
  onUploadEvidence,
  onUploadSampleAttachment,
  removeEvidenceAttachment,
  removeSampleAttachment,
})
</script>

<template>
  <div class="c22-control-sheet" v-loading="loading">
    <!-- 方法论上下文（琥珀块，Req 10.4） -->
    <div class="c22cs-methodology-context">
      <div class="c22cs-methodology-context__header">
        <span class="c22cs-methodology-context__icon">🔍</span>
        <span class="c22cs-methodology-context__title">方法论上下文 — IT 控制测试子页</span>
      </div>
      <div class="c22cs-methodology-context__body">
        先评价<strong>设计有效性</strong>（控制是否设计得当、是否能有效预防或检测 IT 相关风险），
        再测试<strong>执行有效性</strong>（控制是否在测试期间一贯有效运行）。<br>
        抽样数量 &gt; 1 时在样本记录表登记其余样本；发现异常则填写缺陷评估并汇总至 C21-1。
        <strong>长文本字段可使用右侧 🤖 AI 按钮辅助生成。</strong>
      </div>
    </div>

    <!-- 1. 控制信息（公式引用矩阵 C/D 列，Req 10.5 tooltip） -->
    <div class="c22cs-header">
      <div class="c22cs-header-row">
        <span class="c22cs-label">控制编号</span>
        <el-tooltip :content="controlNoRefTip" placement="top" :show-after="150">
          <span class="c22cs-ref-value">{{ controlNo }}</span>
        </el-tooltip>
        <el-tag v-if="refBroken" type="warning" size="small" effect="plain" class="c22cs-ref-fixed">
          公式引用已修复
        </el-tag>
      </div>
      <div class="c22cs-header-row">
        <span class="c22cs-label">控制活动</span>
        <el-tooltip :content="controlActivityRefTip" placement="top" :show-after="150">
          <span class="c22cs-ref-value c22cs-ref-desc">{{ controlActivity || '—' }}</span>
        </el-tooltip>
      </div>
    </div>

    <!-- 2. 设计有效性 -->
    <el-card class="c22cs-card" shadow="never">
      <template #header><span class="c22cs-card-title">一、设计有效性</span></template>
      <div class="c22cs-field">
        <div class="c22cs-field-header">
          <label class="c22cs-field-label">执行的审计程序</label>
          <el-tooltip :content="ai.aiEnabled.value ? 'AI 辅助生成审计程序描述' : 'AI 服务暂不可用'" placement="top">
            <el-button
              size="small"
              class="c22cs-ai-btn"
              :loading="ai.aiLoading.value"
              :disabled="isReadonly || !ai.aiEnabled.value"
              @click="onAiRequest('designProcedure')"
            >🤖 AI</el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="form.designProcedure"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :readonly="isReadonly"
          placeholder="描述为评价控制设计有效性所执行的审计程序（了解/穿行测试等）"
          @input="saveDebounced('design-procedure', form.designProcedure)"
        />
      </div>
      <div class="c22cs-field">
        <div class="c22cs-field-header">
          <label class="c22cs-field-label">
            审计证据
            <span class="c22cs-hint">建议证据索引号：{{ evidenceIndexHint }}</span>
          </label>
          <div class="c22cs-field-actions">
            <el-upload
              v-if="!isReadonly"
              :show-file-list="false"
              :before-upload="(f: any) => { onUploadEvidence(f); return false }"
              accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx"
              class="c22cs-upload-inline"
            >
              <el-button size="small" :loading="uploading">📎 上传证据</el-button>
            </el-upload>
            <el-tooltip :content="ai.aiEnabled.value ? 'AI 辅助生成审计证据描述' : 'AI 服务暂不可用'" placement="top">
              <el-button
                size="small"
                class="c22cs-ai-btn"
                :loading="ai.aiLoading.value"
                :disabled="isReadonly || !ai.aiEnabled.value"
                @click="onAiRequest('designEvidence')"
              >🤖 AI</el-button>
            </el-tooltip>
          </div>
        </div>
        <!-- 已上传附件列表（Req 11.5） -->
        <div v-if="evidenceAttachments.length > 0" class="c22cs-attachments">
          <div v-for="(att, idx) in evidenceAttachments" :key="att.id" class="c22cs-attachment-item">
            <span class="c22cs-attachment-index">{{ att.index }}</span>
            <span class="c22cs-attachment-name" :title="att.name">{{ att.name }}</span>
            <el-tag v-if="att.ocrMerged" size="small" type="success" effect="plain">OCR已填入</el-tag>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="danger"
              link
              @click="removeEvidenceAttachment(idx)"
            >移除</el-button>
          </div>
        </div>
        <el-input
          v-model="form.designEvidence"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :readonly="isReadonly"
          placeholder="获取的审计证据（制度/审批记录等）及其索引号"
          @input="saveDebounced('design-evidence', form.designEvidence)"
        />
      </div>
      <div class="c22cs-field c22cs-field--inline">
        <label class="c22cs-field-label">设计有效性测试结论</label>
        <el-select
          v-model="form.designConclusion"
          placeholder="请选择"
          size="small"
          clearable
          :disabled="isReadonly"
          class="c22cs-select"
          @change="saveNow('design-conclusion', form.designConclusion)"
        >
          <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
        </el-select>
      </div>
    </el-card>

    <!-- 3. 执行有效性 -->
    <el-card class="c22cs-card" shadow="never">
      <template #header><span class="c22cs-card-title">二、执行有效性</span></template>
      <div class="c22cs-field c22cs-field--inline">
        <label class="c22cs-field-label">测试期间 & 样本总量</label>
        <el-input
          v-model="form.testPeriod"
          size="small"
          :readonly="isReadonly"
          placeholder="如：2024.1.1-2024.12.31，总量 120 次变更"
          class="c22cs-input-mid"
          @input="saveDebounced('test-period', form.testPeriod)"
        />
      </div>
      <div class="c22cs-field c22cs-field--inline">
        <label class="c22cs-field-label">抽样数量</label>
        <el-input
          v-model="form.sampleSize"
          size="small"
          :readonly="isReadonly"
          placeholder="如：25"
          class="c22cs-input-sm"
          @input="saveDebounced('sample-size', form.sampleSize)"
        />
        <span class="c22cs-hint">抽样 &gt; 1 时展开样本记录表</span>
      </div>
      <div class="c22cs-field">
        <div class="c22cs-field-header">
          <label class="c22cs-field-label">执行的审计程序 / 测试步骤</label>
          <el-tooltip :content="ai.aiEnabled.value ? 'AI 辅助生成执行程序描述' : 'AI 服务暂不可用'" placement="top">
            <el-button
              size="small"
              class="c22cs-ai-btn"
              :loading="ai.aiLoading.value"
              :disabled="isReadonly || !ai.aiEnabled.value"
              @click="onAiRequest('execProcedure')"
            >🤖 AI</el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="form.execProcedure"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :readonly="isReadonly"
          placeholder="描述执行有效性测试的步骤与结果"
          @input="saveDebounced('exec-procedure', form.execProcedure)"
        />
      </div>

      <!-- 4. 样本记录表（抽样 > 1） -->
      <div v-if="showSampleTable" class="c22cs-samples">
        <div class="c22cs-samples-head">
          <span class="c22cs-card-title">样本记录表</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            @click="addSampleRow"
          >+ 新增样本</el-button>
        </div>
        <el-table :data="sampleRecords" size="small" border class="c22cs-sample-table">
          <el-table-column label="序号" width="64">
            <template #default="{ row }">
              <el-input v-model="row.seq" size="small" :readonly="isReadonly" @input="persistSamples" />
            </template>
          </el-table-column>
          <el-table-column label="样本描述">
            <template #default="{ row }">
              <el-input v-model="row.desc" size="small" :readonly="isReadonly" @input="persistSamples" />
            </template>
          </el-table-column>
          <el-table-column label="测试结果" width="120">
            <template #default="{ row }">
              <el-select v-model="row.result" size="small" clearable :disabled="isReadonly" @change="persistSamples">
                <el-option v-for="o in SAMPLE_RESULT_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="📎 附件" width="160">
            <template #default="{ row, $index }">
              <div v-if="row.attachment" class="c22cs-sample-attach">
                <span class="c22cs-attachment-name" :title="row.attachment.name">{{ row.attachment.name }}</span>
                <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeSampleAttachment($index)">×</el-button>
              </div>
              <el-upload
                v-else-if="!isReadonly"
                :show-file-list="false"
                :before-upload="(f: any) => { onUploadSampleAttachment($index, f); return false }"
                accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,.doc,.docx,.xls,.xlsx"
                class="c22cs-upload-inline"
              >
                <el-button size="small" link :loading="uploading">📎</el-button>
              </el-upload>
              <span v-else class="c22cs-no-attach">—</span>
            </template>
          </el-table-column>
          <el-table-column label="备注">
            <template #default="{ row }">
              <el-input v-model="row.remark" size="small" :readonly="isReadonly" @input="persistSamples" />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="72">
            <template #default="{ $index }">
              <el-button size="small" type="danger" link @click="removeSampleRow($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="c22cs-field c22cs-field--inline">
        <label class="c22cs-field-label">执行有效性测试结论</label>
        <el-select
          v-model="form.execConclusion"
          placeholder="请选择"
          size="small"
          clearable
          :disabled="isReadonly"
          class="c22cs-select"
          @change="saveNow('exec-conclusion', form.execConclusion)"
        >
          <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
        </el-select>
      </div>
    </el-card>

    <!-- 5. 缺陷评估 -->
    <el-card class="c22cs-card" shadow="never">
      <template #header><span class="c22cs-card-title">三、缺陷评估</span></template>
      <div class="c22cs-field c22cs-field--inline">
        <label class="c22cs-field-label">是否发现异常</label>
        <el-radio-group
          v-model="form.abnormal"
          :disabled="isReadonly"
          @change="onAbnormalChange(form.abnormal)"
        >
          <el-radio-button label="否" />
          <el-radio-button label="是" />
        </el-radio-group>
      </div>

      <template v-if="showDefect">
        <div class="c22cs-field c22cs-field--inline">
          <label class="c22cs-field-label">缺陷编号</label>
          <el-input
            v-model="form.defectNo"
            size="small"
            :readonly="isReadonly"
            placeholder="ITGC#1"
            class="c22cs-input-sm"
            @input="saveDebounced('defect-no', form.defectNo)"
          />
          <span class="c22cs-hint">将汇总至</span>
          <GtIndexChip value="sheet:C21-1" :validate="false" />
        </div>
        <div class="c22cs-field">
          <div class="c22cs-field-header">
            <label class="c22cs-field-label">缺陷描述</label>
            <el-tooltip :content="ai.aiEnabled.value ? 'AI 辅助生成缺陷描述' : 'AI 服务暂不可用'" placement="top">
              <el-button
                size="small"
                class="c22cs-ai-btn"
                :loading="ai.aiLoading.value"
                :disabled="isReadonly || !ai.aiEnabled.value"
                @click="onAiRequest('defectDesc')"
              >🤖 AI</el-button>
            </el-tooltip>
          </div>
          <el-input
            v-model="form.defectDesc"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :readonly="isReadonly"
            placeholder="描述识别的控制缺陷（问题描述）"
            @input="saveDebounced('defect-desc', form.defectDesc)"
          />
        </div>
      </template>
      <div v-else class="c22cs-no-defect">未发现异常，无需填写缺陷评估。</div>
    </el-card>

    <!-- AI 建议面板（浮动，采纳/忽略） -->
    <Teleport to="body">
      <div v-if="ai.showSuggestionPanel.value" class="c22cs-ai-panel">
        <div class="c22cs-ai-panel__header">
          <span>🤖 AI 建议</span>
          <el-button size="small" type="info" link @click="ai.ignoreSuggestion()">关闭</el-button>
        </div>
        <div class="c22cs-ai-panel__body">
          <pre class="c22cs-ai-panel__text">{{ ai.currentSuggestion.value?.text || '' }}</pre>
        </div>
        <div class="c22cs-ai-panel__footer">
          <el-button size="small" type="primary" @click="onAiAdopt(ai.currentSuggestion.value?.fieldName === '设计有效性审计程序' ? 'designProcedure' : ai.currentSuggestion.value?.fieldName === '设计有效性审计证据' ? 'designEvidence' : ai.currentSuggestion.value?.fieldName === '执行有效性审计程序' ? 'execProcedure' : 'defectDesc')">
            采纳
          </el-button>
          <el-button size="small" @click="ai.ignoreSuggestion()">忽略</el-button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.c22-control-sheet {
  font-size: var(--wp-font-size, 13px);
  padding: 4px 2px 24px;
}

/* 方法论琥珀块（Req 10.4 增强） */
.c22cs-methodology-context {
  margin-bottom: 12px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  overflow: hidden;
}
.c22cs-methodology-context__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px 4px;
  font-weight: 600;
  color: #7d5b1e;
}
.c22cs-methodology-context__icon { font-size: 15px; }
.c22cs-methodology-context__title { font-size: var(--wp-font-size, 13px); }
.c22cs-methodology-context__body {
  padding: 2px 12px 10px;
  color: #7d5b1e;
  line-height: 1.6;
  font-size: 12px;
}

/* 控制信息 */
.c22cs-header {
  padding: 8px 12px;
  margin-bottom: 12px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 6px;
}
.c22cs-header-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
}
.c22cs-label {
  min-width: 72px;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 600;
}
.c22cs-ref-value {
  font-weight: 600;
  text-decoration: underline dotted;
  cursor: help;
  color: var(--gt-color-primary, #409eff);
}
.c22cs-ref-desc {
  color: var(--gt-color-text, #303133);
  font-weight: 400;
  line-height: 1.5;
}
.c22cs-ref-fixed { margin-left: 4px; }

/* 卡片 */
.c22cs-card {
  margin-bottom: 12px;
}
.c22cs-card :deep(.el-card__header) {
  padding: 8px 12px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
}
.c22cs-card :deep(.el-card__body) {
  padding: 12px;
}
.c22cs-card-title {
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  color: var(--gt-color-text, #303133);
}

.c22cs-field {
  margin-bottom: 12px;
}
.c22cs-field:last-child { margin-bottom: 0; }
.c22cs-field--inline {
  display: flex;
  align-items: center;
  gap: 10px;
}
.c22cs-field-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.c22cs-field-label {
  display: block;
  margin-bottom: 4px;
  color: var(--gt-color-text-secondary, #606266);
  font-weight: 600;
}
.c22cs-field-header .c22cs-field-label {
  margin-bottom: 0;
}
.c22cs-field--inline .c22cs-field-label {
  margin-bottom: 0;
  min-width: 128px;
}
.c22cs-hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  font-weight: 400;
  margin-left: 6px;
}
.c22cs-select { width: 160px; }
.c22cs-input-mid { width: 320px; }
.c22cs-input-sm { width: 120px; }

/* AI 辅助按钮（Req 10.3：右对齐在 section 标题同行） */
.c22cs-ai-btn {
  opacity: 0.7;
  transition: opacity 0.2s;
}
.c22cs-ai-btn:hover {
  opacity: 1;
}

/* AI 建议面板 */
.c22cs-ai-panel {
  position: fixed;
  bottom: 80px;
  right: 24px;
  width: 400px;
  max-height: 360px;
  background: #fff;
  border: 1px solid var(--gt-color-border, #dcdfe6);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 2000;
  display: flex;
  flex-direction: column;
}
.c22cs-ai-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--gt-color-border-light, #ebeef5);
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}
.c22cs-ai-panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
}
.c22cs-ai-panel__text {
  white-space: pre-wrap;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  margin: 0;
  font-family: inherit;
}
.c22cs-ai-panel__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid var(--gt-color-border-light, #ebeef5);
}

/* 样本表 */
.c22cs-samples {
  margin: 12px 0;
  padding: 10px;
  background: var(--gt-color-bg-page, #fafafa);
  border: 1px dashed var(--gt-color-border, #dcdfe6);
  border-radius: 6px;
}
.c22cs-samples-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.c22cs-sample-table {
  font-size: var(--wp-font-size, 13px);
}

/* 附件上传区域（Task 8.2） */
.c22cs-field-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.c22cs-upload-inline {
  display: inline-flex;
}
.c22cs-upload-inline :deep(.el-upload) {
  display: inline-flex;
}
.c22cs-attachments {
  margin-bottom: 8px;
  padding: 6px 8px;
  background: var(--gt-color-bg-page, #fafafa);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 4px;
}
.c22cs-attachment-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
}
.c22cs-attachment-index {
  font-weight: 600;
  color: var(--el-color-primary, #409eff);
  min-width: 80px;
}
.c22cs-attachment-name {
  flex: 1;
  color: var(--gt-color-text, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.c22cs-sample-attach {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
.c22cs-sample-attach .c22cs-attachment-name {
  max-width: 100px;
}
.c22cs-no-attach {
  color: var(--gt-color-text-tertiary, #909399);
  font-size: 12px;
}

.c22cs-no-defect {
  color: var(--gt-color-text-tertiary, #909399);
  padding: 4px 0;
}
</style>
