<template>
  <div class="c23-sample-sheet">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C23-2 会计分录控制测试：从日记账中抽取 25 笔分录样本，核对编制人/过账人/审核人是否在 C23-1 授权清单内，判断偏差并统计。📎 可上传凭证图片/PDF，OCR 自动识别人员/日期填入。</p>
    </div>

    <!-- 样本表格 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">控制测试样本（25笔）</span>
        <div class="section-actions">
          <span class="formula-cell" title="偏差统计 = 偏差数 / 已填样本数">
            偏差统计：{{ deviationCount }} / {{ deviationTotal }}
          </span>
          <el-dropdown v-if="!isReadonly" trigger="click" @command="onImportExportCmd">
            <el-button size="small" type="primary" plain>
              导入导出 ▾
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="export-template">📥 导出模板（空表）</el-dropdown-item>
                <el-dropdown-item command="export-data">📤 导出数据（含已填）</el-dropdown-item>
                <el-dropdown-item command="import-data">📂 导入数据</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <!-- 精简主表格：关键列 + 点击行弹 Dialog -->
      <el-table
        :data="samples"
        border
        size="small"
        class="c23-table"
        max-height="520"
        :row-class-name="rowClassName"
        highlight-current-row
        @row-click="onRowClick"
      >
        <el-table-column label="序" width="45" align="center" fixed>
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="📎" width="45" align="center">
          <template #default="{ $index }">
            <span v-if="sampleAttachments[$index]" class="attach-flag">📎</span>
            <span v-else class="attach-empty">—</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证日期" min-width="110">
          <template #default="{ row }">
            <span class="cell-text">{{ row.date || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" min-width="120">
          <template #default="{ row }">
            <span class="cell-text">{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="编制人" min-width="80">
          <template #default="{ row }">
            <span class="cell-text">{{ row.preparer || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审核人" min-width="80">
          <template #default="{ row }">
            <span class="cell-text">{{ row.reviewer || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否偏差" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.deviation === '否'" type="success" size="small" effect="plain">否</el-tag>
            <el-tag v-else-if="row.deviation?.startsWith('是')" type="danger" size="small" effect="plain">{{ row.deviation }}</el-tag>
            <span v-else class="cell-empty">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70" align="center">
          <template #default="{ row }">
            <span v-if="row.date && row.preparer && row.deviation">✅</span>
            <span v-else-if="row.date || row.preparer">🟡</span>
            <span v-else>⬜</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="c23-table-tip">
        💡 点击任意行打开详情编辑（填写全部字段）；或使用「导入导出」批量操作
      </div>
    </section>

    <!-- ═══ 样本详情 Dialog ═══ -->
    <el-dialog
      v-model="sampleDialogVisible"
      :title="`样本 ${activeSampleIndex + 1} — 编辑详情`"
      width="600px"
      :close-on-click-modal="false"
      append-to-body
    >
      <template v-if="activeSampleIndex >= 0 && activeSampleIndex < samples.length">
        <el-form label-position="left" label-width="90px" class="c23-sample-form">
          <el-form-item label="凭证日期">
            <el-input
              :model-value="samples[activeSampleIndex].date"
              :disabled="isReadonly"
              placeholder="YYYY-MM-DD"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'date', v)"
            />
          </el-form-item>
          <el-form-item label="凭证编号">
            <el-input
              :model-value="samples[activeSampleIndex].voucherNo"
              :disabled="isReadonly"
              placeholder="凭证编号"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'voucherNo', v)"
            />
          </el-form-item>
          <el-form-item label="编制人">
            <el-input
              :model-value="samples[activeSampleIndex].preparer"
              :disabled="isReadonly"
              placeholder="编制人"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'preparer', v)"
            />
          </el-form-item>
          <el-form-item label="过账人">
            <el-input
              :model-value="samples[activeSampleIndex].poster"
              :disabled="isReadonly"
              placeholder="过账人"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'poster', v)"
            />
          </el-form-item>
          <el-form-item label="审核人">
            <el-input
              :model-value="samples[activeSampleIndex].reviewer"
              :disabled="isReadonly"
              placeholder="审核人"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'reviewer', v)"
            />
          </el-form-item>
          <el-form-item label="支持性文件">
            <el-input
              :model-value="samples[activeSampleIndex].supportDoc"
              :disabled="isReadonly"
              placeholder="支持性文件类型及识别特征"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'supportDoc', v)"
            />
          </el-form-item>
          <el-form-item label="批准过程">
            <el-input
              :model-value="samples[activeSampleIndex].approval"
              :disabled="isReadonly"
              placeholder="批准过程描述"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'approval', v)"
            />
          </el-form-item>
          <el-form-item label="是否偏差">
            <el-select
              :model-value="samples[activeSampleIndex].deviation"
              :disabled="isReadonly"
              placeholder="请选择"
              @change="(v: any) => $emit('update-sample', activeSampleIndex, 'deviation', v)"
            >
              <el-option label="否" value="否" />
              <el-option label="是-已解释" value="是-已解释" />
              <el-option label="是-需跟进" value="是-需跟进" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="samples[activeSampleIndex].deviation?.startsWith('是')" label="偏差说明">
            <el-input
              :model-value="samples[activeSampleIndex].deviationNote"
              :disabled="isReadonly"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              placeholder="描述偏差具体情况"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'deviationNote', v)"
            />
          </el-form-item>
          <el-form-item label="索引号">
            <el-input
              :model-value="samples[activeSampleIndex].indexRef"
              :disabled="isReadonly"
              placeholder="关联底稿索引号"
              @input="(v: any) => $emit('update-sample', activeSampleIndex, 'indexRef', v)"
            />
          </el-form-item>
          <!-- 📎 附件 -->
          <el-form-item label="附件">
            <div class="c23-dialog-attach">
              <el-upload
                v-if="!isReadonly"
                :auto-upload="true"
                :show-file-list="false"
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
                :http-request="(req: any) => onUploadSampleAttachment(activeSampleIndex, req.file)"
              >
                <el-button size="small" :loading="uploadingRow === activeSampleIndex">
                  📎 上传凭证 + OCR 识别
                </el-button>
              </el-upload>
              <span v-if="sampleAttachments[activeSampleIndex]" class="attach-name">
                {{ sampleAttachments[activeSampleIndex]?.fileName }}
              </span>
            </div>
          </el-form-item>
        </el-form>
      </template>

      <template #footer>
        <el-button @click="sampleDialogVisible = false">关闭</el-button>
        <el-button v-if="activeSampleIndex > 0" @click="activeSampleIndex--">← 上一笔</el-button>
        <el-button v-if="activeSampleIndex < samples.length - 1" type="primary" @click="activeSampleIndex++">下一笔 →</el-button>
      </template>
    </el-dialog>

    <!-- 隐藏的导入 input -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="onImportFileChange" />

    <!-- 测试结论 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button
          v-if="!isReadonly"
          size="small"
          @click="$emit('ai-suggest')"
        >
          AI 辅助
        </el-button>
      </div>
      <el-select
        :model-value="conclusion2Select"
        :disabled="isReadonly"
        size="default"
        placeholder="请选择测试结论"
        style="width: 100%; margin-bottom: 8px;"
        @change="onConclusionSelect"
      >
        <el-option label="未发现偏差" value="未发现偏差" />
        <el-option label="发现偏差-影响不重大" value="发现偏差-影响不重大" />
        <el-option label="发现偏差-影响重大" value="发现偏差-影响重大" />
      </el-select>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion2Detail"
        :disabled="isReadonly"
        placeholder="补充说明（可选）"
        @input="onConclusionDetailInput"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * C23SampleSheet — C23-2 会计分录控制测试样本表
 *
 * 25行样本表 + 人员核对偏差 + 偏差统计 + 结论
 * 📎 附件上传 + OCR 识别编制人/过账人/审核人/日期 merge（Req 10.1）
 *
 * Task: 8.2
 * Requirements: 10.1, 10.4, 10.5
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import { uploadAttachment } from '@/services/commonApi'

/** 样本行附件信息 */
export interface SampleAttachment {
  id: string
  fileName: string
  ocrMerged: boolean
}

const props = defineProps<{
  wpId: string
  projectId?: string
  samples: Array<{
    seq: number
    date: string
    voucherNo: string
    preparer: string
    poster: string
    reviewer: string
    supportDoc: string
    approval: string
    deviation: string
    deviationNote: string
    indexRef: string
  }>
  persons: Array<{ seq: number; name: string; role: string; note: string }>
  deviationCount: number
  deviationTotal: number
  conclusion2: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update-sample', index: number, field: string, value: string): void
  (e: 'update:conclusion2', val: string): void
  (e: 'ai-suggest'): void
  (e: 'attachment-uploaded', index: number, attachment: SampleAttachment): void
}>()

// ─── Attachment state ───
const sampleAttachments = ref<Array<SampleAttachment | null>>([])
const uploadingRow = ref<number | null>(null)

// ─── Dialog state ───
const sampleDialogVisible = ref(false)
const activeSampleIndex = ref(0)
const importFileInput = ref<HTMLInputElement | null>(null)

function onRowClick(row: any) {
  activeSampleIndex.value = row.seq - 1
  sampleDialogVisible.value = true
}

// ─── 导入导出 ───
function onImportExportCmd(cmd: string) {
  if (cmd === 'export-template') exportTemplate()
  else if (cmd === 'export-data') exportData()
  else if (cmd === 'import-data') importFileInput.value?.click()
}

async function exportTemplate() {
  const XLSX = await import('xlsx')
  const headers = ['序号', '凭证日期', '凭证编号', '编制人', '过账人', '审核人', '支持性文件', '批准过程', '是否偏差', '偏差说明', '索引号']
  const rows = Array.from({ length: 25 }, (_, i) => [i + 1, '', '', '', '', '', '', '', '', '', ''])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'C23-2 样本')
  XLSX.writeFile(wb, 'C23-2_控制测试样本_模板.xlsx')
  ElMessage.success('模板已导出')
}

async function exportData() {
  const XLSX = await import('xlsx')
  const headers = ['序号', '凭证日期', '凭证编号', '编制人', '过账人', '审核人', '支持性文件', '批准过程', '是否偏差', '偏差说明', '索引号']
  const rows = props.samples.map(s => [s.seq, s.date, s.voucherNo, s.preparer, s.poster, s.reviewer, s.supportDoc, s.approval, s.deviation, s.deviationNote, s.indexRef])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'C23-2 样本')
  XLSX.writeFile(wb, 'C23-2_控制测试样本_数据.xlsx')
  ElMessage.success('数据已导出')
}

async function onImportFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const XLSX = await import('xlsx')
  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, { type: 'array' })
  const ws = wb.Sheets[wb.SheetNames[0]]
  const data = XLSX.utils.sheet_to_json<any>(ws, { header: 1 })
  // 跳过表头行
  const rows = data.slice(1)
  let imported = 0
  for (let i = 0; i < Math.min(rows.length, 25); i++) {
    const row = rows[i]
    if (!row || !row.length) continue
    const idx = (row[0] ? Number(row[0]) - 1 : i)
    if (idx < 0 || idx >= 25) continue
    if (row[1]) emit('update-sample', idx, 'date', String(row[1]))
    if (row[2]) emit('update-sample', idx, 'voucherNo', String(row[2]))
    if (row[3]) emit('update-sample', idx, 'preparer', String(row[3]))
    if (row[4]) emit('update-sample', idx, 'poster', String(row[4]))
    if (row[5]) emit('update-sample', idx, 'reviewer', String(row[5]))
    if (row[6]) emit('update-sample', idx, 'supportDoc', String(row[6]))
    if (row[7]) emit('update-sample', idx, 'approval', String(row[7]))
    if (row[8]) emit('update-sample', idx, 'deviation', String(row[8]))
    if (row[9]) emit('update-sample', idx, 'deviationNote', String(row[9]))
    if (row[10]) emit('update-sample', idx, 'indexRef', String(row[10]))
    imported++
  }
  // 重置 input
  if (importFileInput.value) importFileInput.value.value = ''
  ElMessage.success(`已导入 ${imported} 笔样本数据`)
}

// 初始化附件数组
onMounted(async () => {
  // 填充 null 数组 匹配样本行数
  sampleAttachments.value = new Array(props.samples.length).fill(null)
  // 从持久化加载已有附件
  await loadAttachments()
})

/** 从 checklist_responses 加载已有附件引用 */
async function loadAttachments() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { _silent: true } as any,
    )
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> =
      Array.isArray(res) ? res : (res as any)?.data || []

    for (const item of items) {
      // item_id 格式: C23-sample-{n}-attachment
      const m = item.item_id?.match(/^C23-sample-(\d+)-attachment$/)
      if (m && item.remark) {
        const idx = parseInt(m[1]) - 1 // seq 从 1 开始
        if (idx >= 0 && idx < sampleAttachments.value.length) {
          try {
            sampleAttachments.value[idx] = JSON.parse(item.remark)
          } catch { /* ignore parse error */ }
        }
      }
    }
  } catch { /* silent */ }
}

/** 上传附件 + OCR 识别 + 确认弹窗 merge */
async function onUploadSampleAttachment(index: number, file: File) {
  if (props.isReadonly) return
  // 文件大小校验
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return
  }

  uploadingRow.value = index
  try {
    // 1) 上传附件
    const fd = new FormData()
    fd.append('file', file)
    fd.append('attachment_type', 'evidence')
    fd.append('reference_type', 'workpaper')
    fd.append('reference_id', props.wpId)
    fd.append('title', `${file.name} [C23-2 样本${index + 1}]`)

    const uploadResp = await uploadAttachment(props.projectId || '', fd)
    const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
    if (!attachmentId) throw new Error('上传响应缺少 attachment_id')

    // 关联到底稿
    try {
      await api.post(`/api/attachments/${attachmentId}/associate`, {
        wp_id: props.wpId,
        association_type: 'evidence',
        notes: `C23-sample-${index + 1}`,
      })
    } catch { /* 关联失败不阻断 */ }

    // 存储附件引用
    const attachment: SampleAttachment = { id: attachmentId, fileName: file.name, ocrMerged: false }
    sampleAttachments.value[index] = attachment
    emit('attachment-uploaded', index, attachment)

    // 持久化附件信息到 checklist_responses
    await persistAttachment(index, attachment)

    ElMessage.success(`样本附件 "${file.name}" 已上传`)

    // 2) OCR 识别（仅图片/PDF 可识别）
    if (isOcrEligible(file.name)) {
      await doOcrMerge(file, index)
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '上传失败'
    ElMessage.error(`样本附件上传失败：${detail}`)
  } finally {
    uploadingRow.value = null
  }
}

/** 判断文件是否适合 OCR */
function isOcrEligible(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'].includes(ext)
}

/**
 * OCR 识别 + 确认弹窗 + merge 填入（Req 10.1）
 * 识别：编制人/过账人/审核人/日期
 */
async function doOcrMerge(file: File, index: number): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  let ocrFields: Record<string, any>
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = (res.data?.data ?? res.data)?.extracted_fields || {}
  } catch {
    // OCR 失败（Req 10.4）：提示手动填写，附件已保留
    ElMessage.warning('OCR 识别失败，请手动填写样本信息（附件已保留）')
    return
  }

  if (!ocrFields || Object.keys(ocrFields).length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  // 映射 OCR 字段到样本行字段
  const mapped = mapOcrToSample(ocrFields)
  if (mapped.length === 0) {
    ElMessage.info('OCR 未识别到编制人/过账人/审核人/日期字段，请手动补充')
    return
  }

  // 确认弹窗
  const previewMsg = mapped.map(m => `${m.label}：${m.value}`).join('\n')
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下信息，确认填入样本行？\n\n${previewMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消（仅保留附件）', type: 'info' },
    )
  } catch {
    return // 用户取消：附件已上传，不 merge
  }

  // merge 填入（非破坏性：仅填空字段或经确认覆盖）
  for (const { field, value } of mapped) {
    emit('update-sample', index, field, value)
  }

  // 标记 OCR 已 merge
  if (sampleAttachments.value[index]) {
    sampleAttachments.value[index]!.ocrMerged = true
    await persistAttachment(index, sampleAttachments.value[index]!)
  }
  ElMessage.success('已将 OCR 识别信息填入样本行')
}

/** 映射 OCR 字段到样本行（编制人/过账人/审核人/日期） */
function mapOcrToSample(fields: Record<string, any>): Array<{ label: string; field: string; value: string }> {
  const result: Array<{ label: string; field: string; value: string }> = []

  // 编制人 / 制单人
  const preparer = fields.preparer || fields.maker || fields.recorder || fields['制单人'] || fields['编制人'] || ''
  if (preparer) result.push({ label: '编制人', field: 'preparer', value: String(preparer) })

  // 过账人
  const poster = fields.poster || fields['过账人'] || fields.bookkeeper || ''
  if (poster) result.push({ label: '过账人', field: 'poster', value: String(poster) })

  // 审核人
  const reviewer = fields.reviewer || fields.approver || fields.auditor || fields['审核人'] || fields['审批人'] || ''
  if (reviewer) result.push({ label: '审核人', field: 'reviewer', value: String(reviewer) })

  // 凭证日期
  const date = fields.voucher_date || fields.date || fields['凭证日期'] || fields['日期'] || ''
  if (date) result.push({ label: '凭证日期', field: 'date', value: String(date) })

  // 凭证编号
  const voucherNo = fields.voucher_no || fields.voucher_number || fields['凭证号'] || fields['凭证编号'] || ''
  if (voucherNo) result.push({ label: '凭证编号', field: 'voucherNo', value: String(voucherNo) })

  return result
}

/** 持久化附件信息到 checklist_responses（Req 10.5） */
async function persistAttachment(index: number, attachment: SampleAttachment) {
  if (!props.wpId) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: `C23-sample-${index + 1}-attachment`,
        conclusion: null,
        remark: JSON.stringify(attachment),
      }],
    })
  } catch { /* silent */ }
}

// 结论解析：格式 "选项||补充说明"
const CONCLUSION_OPTIONS = ['未发现偏差', '发现偏差-影响不重大', '发现偏差-影响重大']
const conclusion2Select = computed(() => {
  const raw = props.conclusion2 || ''
  const selectPart = raw.split('||')[0] || ''
  return CONCLUSION_OPTIONS.includes(selectPart) ? selectPart : ''
})
const conclusion2Detail = computed(() => {
  const raw = props.conclusion2 || ''
  const parts = raw.split('||')
  if (parts.length > 1) return parts.slice(1).join('||')
  // 如果原值不在选项中，作为补充说明
  if (!CONCLUSION_OPTIONS.includes(raw)) return raw
  return ''
})

function onConclusionSelect(val: string) {
  const detail = conclusion2Detail.value
  emit('update:conclusion2', detail ? `${val}||${detail}` : val)
}

function onConclusionDetailInput(val: string) {
  const sel = conclusion2Select.value
  emit('update:conclusion2', sel ? `${sel}||${val}` : val)
}

function rowClassName({ row }: { row: any }) {
  if (row.deviation === '是-需跟进') return 'deviation-row'
  if (row.deviation === '是-已解释') return 'deviation-explained-row'
  return ''
}
</script>

<style scoped>
.c23-sample-sheet {
  font-size: var(--wp-font-size, 13px);
}

.methodology-context {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  margin-bottom: 16px;
  background: #fffbf0;
  border-radius: 4px;
}

.methodology-bar {
  width: 3px;
  min-height: 20px;
  align-self: stretch;
  background: #e6a23c;
  border-radius: 2px;
  flex-shrink: 0;
}

.methodology-context p {
  margin: 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}

.c23-section {
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.formula-cell {
  font-size: var(--wp-font-size, 13px);
  color: #909399;
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
}

.c23-table {
  font-size: var(--wp-font-size, 13px);
}

.c23-table :deep(.el-table__header th) {
  font-size: var(--wp-font-size, 13px);
  background: #f5f7fa;
}

.c23-table :deep(.el-table__body td) {
  font-size: var(--wp-font-size, 13px);
}

.c23-table :deep(.deviation-row) {
  background-color: #fef0f0 !important;
}

.c23-table :deep(.deviation-row td) {
  background-color: #fef0f0 !important;
}

.c23-table :deep(.deviation-explained-row) {
  background-color: #fdf6ec !important;
}

.c23-table :deep(.deviation-explained-row td) {
  background-color: #fdf6ec !important;
}

/* 表格精简模式 */
.cell-text { font-size: var(--wp-font-size, 13px); color: #303133; }
.cell-empty { color: #c0c4cc; }
.attach-flag { font-size: 14px; }
.attach-empty { color: #c0c4cc; }

.c23-table-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Dialog 表单 */
.c23-sample-form {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 8px;
}
.c23-dialog-attach {
  display: flex;
  align-items: center;
  gap: 8px;
}
.attach-name {
  font-size: 12px;
  color: #606266;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 表格行可点击 */
.c23-table :deep(.el-table__body tr) {
  cursor: pointer;
}
.c23-table :deep(.el-table__body tr:hover td) {
  background: #f3eefb !important;
}
</style>
