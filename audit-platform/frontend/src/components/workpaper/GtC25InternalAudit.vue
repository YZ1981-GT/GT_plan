<template>
  <div class="gt-c25-internal-audit">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部操作引导区 -->
      <div class="guidance-area">
        <div class="guidance-header">
          <el-icon><InfoFilled /></el-icon>
          <span>操作流程引导</span>
        </div>
        <div class="guidance-steps">
          <div class="step-item">
            <span class="step-num">①</span>
            <span class="step-text">逐步评估内审工作</span>
          </div>
          <div class="step-item">
            <span class="step-num">②</span>
            <span class="step-text">标记是否适用</span>
          </div>
          <div class="step-item">
            <span class="step-num">③</span>
            <span class="step-text">记录执行情况</span>
          </div>
          <div class="step-item">
            <span class="step-num">④</span>
            <span class="step-text">得出利用结论</span>
          </div>
        </div>
      </div>

      <!-- 方法论上下文（琥珀色区块） -->
      <div class="methodology-context">
        <div class="methodology-content">
          <p><strong>利用内审工作的适用条件与判断要点：</strong></p>
          <p>注册会计师应当评价被审计单位内部审计的组织地位和相关政策及程序是否足以保持其客观性、内部审计人员的胜任能力，以及内部审计是否采用系统的、规范化的方法（包括质量控制）。</p>
          <p>如拟利用内审工作，需确定：(1) 利用范围 (2) 利用领域 (3) 重新执行程度，并将利用的影响记录于审计计划中。</p>
        </div>
      </div>

      <!-- 10 步评估程序表 -->
      <div class="evaluation-table-section">
        <div class="section-header">
          <span class="section-title">利用内部审计工作评估程序</span>
          <el-button
            v-if="!isReadonly && ai.aiEnabled.value"
            size="small"
            type="primary"
            :icon="MagicStick"
            :loading="ai.aiLoading.value"
            @click="onAiSuggestAll"
          >
            AI 辅助
          </el-button>
        </div>

        <el-table
          :data="stepsData"
          border
          stripe
          class="evaluation-table"
          :cell-style="{ fontSize: '13px' }"
          :header-cell-style="{ fontSize: '13px', fontWeight: '600' }"
        >
          <!-- 序号列 -->
          <el-table-column label="序号" width="55" align="center">
            <template #default="{ row }">
              <span class="step-seq">{{ row.seq }}</span>
            </template>
          </el-table-column>

          <!-- 审计程序列 -->
          <el-table-column label="审计程序" min-width="280">
            <template #default="{ row }">
              <div class="procedure-text">
                <span class="procedure-main">{{ row.procedure }}</span>
                <div v-if="row.subSteps && row.subSteps.length > 0" class="sub-steps">
                  <div v-for="(sub, si) in row.subSteps" :key="si" class="sub-step-item">
                    ({{ si + 1 }}) {{ sub }}
                  </div>
                </div>
              </div>
            </template>
          </el-table-column>

          <!-- 是否适用列 -->
          <el-table-column label="是否适用" width="100" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="c25.steps[row.index].applicable"
                :disabled="isReadonly"
                placeholder="—"
                size="small"
                style="width: 80px"
                @change="(v: string) => updateC25StepApplicable(row.index, v as any)"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </template>
          </el-table-column>

          <!-- 执行人列 -->
          <el-table-column label="执行人" width="110">
            <template #default="{ row }">
              <el-input
                :model-value="c25.steps[row.index].executor"
                :disabled="isReadonly"
                size="small"
                placeholder="执行人"
                @input="(v: string) => updateC25StepText(row.index, 'executor', v)"
              />
            </template>
          </el-table-column>

          <!-- 执行情况说明列 -->
          <el-table-column label="执行情况说明" min-width="240">
            <template #header>
              <div class="column-header-with-ai">
                <span>执行情况说明</span>
              </div>
            </template>
            <template #default="{ row }">
              <div class="result-cell-with-attach">
                <el-input
                  type="textarea"
                  :model-value="c25.steps[row.index].result"
                  :disabled="isReadonly"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  placeholder="请描述执行情况..."
                  @input="(v: string) => updateC25StepText(row.index, 'result', v)"
                />
                <div class="attach-inline">
                  <el-tooltip
                    v-if="c25Attachments[row.index]"
                    :content="c25Attachments[row.index]!.fileName"
                    placement="top"
                  >
                    <a
                      :href="`/api/attachments/${c25Attachments[row.index]!.id}/download`"
                      target="_blank"
                      class="attach-link"
                      @click.stop
                    >📎</a>
                  </el-tooltip>
                  <el-upload
                    v-if="!isReadonly"
                    :auto-upload="true"
                    :show-file-list="false"
                    accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
                    :http-request="(req: any) => onUploadC25Attachment(row.index, req.file)"
                  >
                    <el-button
                      size="small"
                      :icon="UploadFilled"
                      circle
                      :loading="uploadingC25Row === row.index"
                      :title="c25Attachments[row.index] ? '重新上传' : '上传内审报告/底稿'"
                    />
                  </el-upload>
                </div>
              </div>
            </template>
          </el-table-column>

          <!-- 索引号列 -->
          <el-table-column label="索引号" width="120" align="center">
            <template #default="{ row }">
              <GtIndexChip
                v-if="c25.steps[row.index].indexRef"
                :value="c25.steps[row.index].indexRef"
                :validate="true"
              />
              <el-input
                v-else-if="!isReadonly"
                :model-value="c25.steps[row.index].indexRef"
                :disabled="isReadonly"
                size="small"
                placeholder="索引号"
                @input="(v: string) => updateC25StepText(row.index, 'indexRef', v)"
              />
              <span v-else class="empty-ref">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 利用结论区 -->
      <el-card class="conclusion-card" shadow="never">
        <template #header>
          <div class="conclusion-header">
            <span class="conclusion-title">利用内部审计工作的结论</span>
            <el-button
              v-if="!isReadonly && ai.aiEnabled.value"
              size="small"
              type="primary"
              :icon="MagicStick"
              :loading="ai.aiLoading.value"
              @click="onAiSuggestConclusion"
            >
              AI 辅助
            </el-button>
          </div>
        </template>

        <div class="conclusion-body">
          <div class="conclusion-field">
            <label class="field-label">结论：</label>
            <el-select
              :model-value="c25.conclusion"
              :disabled="isReadonly"
              placeholder="请选择利用结论"
              style="width: 280px"
              @change="onConclusionChange"
            >
              <el-option label="可以利用内部审计工作" value="可以利用内部审计工作" />
              <el-option label="不能利用内部审计工作" value="不能利用内部审计工作" />
              <el-option label="可以部分利用内部审计工作" value="可以部分利用内部审计工作" />
            </el-select>
          </div>

          <!-- 联动跳转：结论影响审计范围 → 跳转计划/风险底稿 (Req 10.2) -->
          <div v-if="c25.conclusion" class="conclusion-links">
            <span class="field-label">联动底稿：</span>
            <GtIndexChip
              value="B6"
              :context="`内审利用结论：${c25.conclusion}`"
              :validate="true"
            />
            <GtIndexChip
              value="B22A"
              :context="`内审利用结论：${c25.conclusion}`"
              :validate="true"
              style="margin-left: 6px"
            />
            <GtIndexChip
              value="B50"
              :context="`内审评估影响风险：${c25.conclusion}`"
              :validate="true"
              style="margin-left: 6px"
            />
          </div>

          <div class="conclusion-remark">
            <label class="field-label">利用程度说明：</label>
            <el-input
              type="textarea"
              :model-value="c25.remark"
              :disabled="isReadonly"
              :autosize="{ minRows: 3, maxRows: 8 }"
              placeholder="请说明利用程度及理由..."
              @input="onRemarkInput"
            />
          </div>
        </div>
      </el-card>

      <!-- 编制提示（details 折叠） -->
      <details class="compile-tips">
        <summary>编制提示</summary>
        <div class="tips-content">
          <p>1. 对每个步骤逐一评估是否适用，不适用的步骤标记"否"并简要说明原因。</p>
          <p>2. 执行情况说明应包含：评估的具体方法、获取的证据、形成的判断。</p>
          <p>3. 利用结论需结合所有步骤评估结果综合判断。</p>
          <p>4. 索引号填入相关底稿编码（如 B6、C1 等），可跳转查看。</p>
        </div>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC25InternalAudit — C25 利用内部审计工作专属组件
 *
 * componentType: c25-internal-audit-reliance
 * 单 sheet 无 sheetName 分发
 *
 * 10 步评估程序 + 命名区域下拉 + 利用结论 + AI 辅助
 *
 * Spec: .kiro/specs/c25-c26-internal-audit-info-control/
 * Task: 4.1
 * Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5
 */
import { computed, ref, onMounted, onBeforeUnmount, toRef } from 'vue'
import { InfoFilled, MagicStick, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useC25C26Data } from '@/composables/useC25C26Data'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'
import { uploadAttachment } from '@/services/commonApi'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import GtIndexChip from './GtIndexChip.vue'

defineOptions({ name: 'GtC25InternalAudit' })

// ─── Props / Emits ───
const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  year?: string | number
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Computed ───
const isReadonly = computed(() => !!props.readonly)

// ─── Composables ───
const {
  c25,
  loading,
  selfLoad,
  flushPendingSaves,
  updateC25StepText,
  updateC25StepApplicable,
  updateC25Conclusion,
  updateC25Remark,
} = useC25C26Data(
  toRef(() => props.wpId),
  toRef(() => props.projectId || ''),
  isReadonly,
)

const ai = useWpAiSuggest({ wpId: props.wpId, sheetName: 'C25' })

// ─── 10 步评估程序数据 ───
const STEP_PROCEDURES = [
  {
    seq: '1',
    procedure: '考虑内审工作的性质和范围',
    subSteps: [],
  },
  {
    seq: '2',
    procedure: '识别可能与审计策略相关的领域',
    subSteps: [
      '审计工作涉及的领域',
      '内审人员覆盖的流程',
      '审计策略中对内审工作的假设',
      '前期利用内审工作的经验',
    ],
  },
  {
    seq: '3',
    procedure: '阅读内审报告获知程序性质范围及发现',
    subSteps: [],
  },
  {
    seq: '4',
    procedure: '获取内审工作底稿确定质量',
    subSteps: [
      '了解内审人员的专业胜任能力',
      '内审人员是否接受足够的督导和复核',
      '内审工作是否有充分适当的审计证据支持结论',
      '得出的结论是否恰当、报告是否与执行的工作一致',
    ],
  },
  {
    seq: '5',
    procedure: '确定重新执行内审工作的程度',
    subSteps: [
      '与内审已完成工作一致的重新执行范围',
      '与内审方法不同但涵盖相同事项的工作',
      '重新执行的时间安排',
    ],
  },
  {
    seq: '6',
    procedure: '考虑是否需要补充执行测试',
    subSteps: [],
  },
  {
    seq: '7',
    procedure: '评价合理借助内审工作的结果',
    subSteps: [
      '内审的发现和结论是否恰当',
      '是否存在异常或不一致情况',
      '内审结论是否与注册会计师的专业判断一致',
      '是否有额外风险因素需要考虑',
    ],
  },
  {
    seq: '8',
    procedure: '与企业适当人员的合作计划',
    subSteps: [],
  },
  {
    seq: '9',
    procedure: '测试结果与内审发现是否一致',
    subSteps: [],
  },
  {
    seq: '10',
    procedure: '初始判断是否仍然合理',
    subSteps: [],
  },
]

const stepsData = computed(() =>
  STEP_PROCEDURES.map((s, i) => ({ ...s, index: i })),
)

// ─── Event handlers ───

function onConclusionChange(val: string) {
  updateC25Conclusion(val)
  emit('save')
}

function onRemarkInput(val: string) {
  updateC25Remark(val)
}

async function onAiSuggestAll() {
  if (isReadonly.value || !ai.aiEnabled.value) return
  await ai.requestSuggestion('利用内审工作评估程序-执行情况说明', '')
  const text = ai.adoptSuggestion()
  if (text) {
    // AI 返回的建议应用到当前空白步骤
    const emptyIdx = c25.value.steps.findIndex(s => !s.result)
    if (emptyIdx >= 0) {
      updateC25StepText(emptyIdx, 'result', text)
    }
  }
}

async function onAiSuggestConclusion() {
  if (isReadonly.value || !ai.aiEnabled.value) return
  const context = c25.value.steps
    .map((s, i) => `步骤${i + 1}: 适用=${s.applicable || '未设置'}, 说明=${s.result || '(空)'}`)
    .join('\n')
  await ai.requestSuggestion('利用内审工作结论', context)
  const text = ai.adoptSuggestion()
  if (text) {
    updateC25Remark(text)
  }
}

// ─── 📎 附件上传 + OCR (Req 9.2, 9.3, 9.4, 9.5) ───

export interface C25Attachment {
  id: string
  fileName: string
  ocrMerged: boolean
}

const c25Attachments = ref<Array<C25Attachment | null>>(new Array(10).fill(null))
const uploadingC25Row = ref<number | null>(null)

/** 加载已有附件 */
async function loadC25Attachments() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { _silent: true } as any,
    )
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> =
      Array.isArray(res) ? res : (res as any)?.data || []

    for (const item of items) {
      const m = item.item_id?.match(/^C25-step-(\d+)-attachment$/)
      if (m && item.remark) {
        const idx = parseInt(m[1]) - 1
        if (idx >= 0 && idx < 10) {
          try {
            c25Attachments.value[idx] = JSON.parse(item.remark)
          } catch { /* ignore */ }
        }
      }
    }
  } catch { /* silent */ }
}

/** 上传附件 + OCR */
async function onUploadC25Attachment(index: number, file: File) {
  if (isReadonly.value) return
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return
  }

  uploadingC25Row.value = index
  try {
    // 1) 上传
    const fd = new FormData()
    fd.append('file', file)
    fd.append('attachment_type', 'evidence')
    fd.append('reference_type', 'workpaper')
    fd.append('reference_id', props.wpId)
    fd.append('title', `${file.name} [C25 步骤${index + 1}]`)

    const uploadResp = await uploadAttachment(props.projectId || '', fd)
    const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
    if (!attachmentId) throw new Error('上传响应缺少 attachment_id')

    // 关联底稿
    try {
      await api.post(`/api/attachments/${attachmentId}/associate`, {
        wp_id: props.wpId,
        association_type: 'evidence',
        notes: `C25-step-${index + 1}`,
      })
    } catch { /* 关联失败不阻断 */ }

    const attachment: C25Attachment = { id: attachmentId, fileName: file.name, ocrMerged: false }
    c25Attachments.value[index] = attachment
    await persistC25Attachment(index, attachment)
    ElMessage.success(`内审附件 "${file.name}" 已上传`)

    // 2) OCR 识别
    if (isOcrEligible(file.name)) {
      await doC25OcrMerge(file, index)
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '上传失败'
    ElMessage.error(`内审附件上传失败：${detail}`)
  } finally {
    uploadingC25Row.value = null
  }
}

function isOcrEligible(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'].includes(ext)
}

/** OCR → 确认弹窗 → merge 到执行情况说明 */
async function doC25OcrMerge(file: File, index: number): Promise<void> {
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
    ElMessage.warning('OCR 识别失败，请手动填写（附件已保留）')
    return
  }

  if (!ocrFields || Object.keys(ocrFields).length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  // 映射 OCR 到执行情况说明
  const mapped = mapOcrToC25(ocrFields)
  if (mapped.length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  const previewMsg = mapped.map(m => `${m.label}：${m.value}`).join('\n')
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下信息，确认填入执行情况说明？\n\n${previewMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消（仅保留附件）', type: 'info' },
    )
  } catch { return }

  // merge
  for (const { field, value } of mapped) {
    if (field === 'result') {
      // 追加而非覆盖
      const current = c25.value.steps[index].result
      const newVal = current ? `${current}\n${value}` : value
      updateC25StepText(index, 'result', newVal)
    }
  }

  // 标记
  if (c25Attachments.value[index]) {
    c25Attachments.value[index]!.ocrMerged = true
    await persistC25Attachment(index, c25Attachments.value[index]!)
  }
  ElMessage.success('已将 OCR 识别信息填入执行情况说明')
}

function mapOcrToC25(fields: Record<string, any>): Array<{ label: string; field: string; value: string }> {
  const result: Array<{ label: string; field: string; value: string }> = []
  // 内审报告 → 执行情况说明
  const content = fields.content || fields.summary || fields.finding || fields.conclusion
    || fields['内容'] || fields['摘要'] || fields['结论'] || fields['发现'] || ''
  if (content) result.push({ label: '报告内容/发现', field: 'result', value: String(content) })
  const scope = fields.scope || fields['范围'] || fields['审计范围'] || ''
  if (scope) result.push({ label: '审计范围', field: 'result', value: `审计范围：${String(scope)}` })
  return result
}

async function persistC25Attachment(index: number, attachment: C25Attachment) {
  if (!props.wpId) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: `C25-step-${index + 1}-attachment`,
        conclusion: null,
        remark: JSON.stringify(attachment),
      }],
    })
  } catch { /* silent */ }
}

// ─── Lifecycle ───
onMounted(() => { selfLoad(); loadC25Attachments() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: selfLoad })
</script>

<style scoped>
.gt-c25-internal-audit {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.loading-container {
  padding: 24px;
}

/* 引导区 */
.guidance-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #d9ecff 100%);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.guidance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  margin-bottom: 12px;
}

.guidance-header .el-icon {
  color: #409eff;
  font-size: 16px;
}

.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 6px;
}

.step-num {
  font-weight: 700;
  color: #409eff;
  font-size: 14px;
}

.step-text {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

/* 方法论上下文 */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
}

.methodology-content p {
  margin: 4px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}

.methodology-content p:first-child {
  margin-top: 0;
}

/* Section header */
.evaluation-table-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

/* 表格 */
.evaluation-table {
  font-size: var(--wp-font-size, 13px);
}

.step-seq {
  font-weight: 600;
  color: #409eff;
}

.procedure-text {
  line-height: 1.6;
}

.procedure-main {
  font-weight: 500;
}

.sub-steps {
  margin-top: 6px;
  padding-left: 8px;
}

.sub-step-item {
  color: #606266;
  font-size: 12px;
  line-height: 1.8;
}

.column-header-with-ai {
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-ref {
  color: #c0c4cc;
}

/* 附件内联 */
.result-cell-with-attach {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.attach-inline {
  display: flex;
  align-items: center;
  gap: 4px;
}

.attach-link {
  text-decoration: none;
  font-size: 14px;
  cursor: pointer;
}

.attach-link:hover {
  opacity: 0.7;
}

.attach-inline :deep(.el-upload) {
  display: inline-flex;
}

.attach-inline :deep(.el-button.is-circle) {
  width: 24px;
  height: 24px;
  padding: 0;
}

/* 结论联动 */
.conclusion-links {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

/* 结论区 */
.conclusion-card {
  margin-top: 16px;
  margin-bottom: 16px;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.conclusion-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.conclusion-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.conclusion-field {
  display: flex;
  align-items: center;
  gap: 12px;
}

.field-label {
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

.conclusion-remark {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 编制提示 */
.compile-tips {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
}

.compile-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #909399;
  font-size: var(--wp-font-size, 13px);
}

.tips-content {
  margin-top: 8px;
  padding-left: 8px;
}

.tips-content p {
  margin: 4px 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
</style>
