<template>
  <div class="gt-c26-info-control">
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
            <span class="step-text">选择循环分组筛选</span>
          </div>
          <div class="step-item">
            <span class="step-num">②</span>
            <span class="step-text">新增信息处理控制条目</span>
          </div>
          <div class="step-item">
            <span class="step-num">③</span>
            <span class="step-text">标记四要素并记录测试</span>
          </div>
          <div class="step-item">
            <span class="step-num">④</span>
            <span class="step-text">得出测试结论</span>
          </div>
        </div>
      </div>

      <!-- 方法论上下文（琥珀色区块） -->
      <div class="methodology-context">
        <div class="methodology-content">
          <p><strong>信息处理控制测试方法论：</strong></p>
          <p>信息处理控制是指为保障信息处理过程中数据完整性、准确性、经过授权及访问限制而设计和执行的应用控制。测试应针对每项信息处理控制，评价其在相关业务循环中对信息处理四要素的覆盖情况。</p>
          <p><strong>信息处理四要素：</strong>完整性（数据录入不缺失）、准确性（数据处理无误差）、经过授权（操作均经适当批准）、访问限制（未授权人员无法访问敏感数据）。</p>
        </div>
      </div>

      <!-- 循环筛选标签 -->
      <div class="cycle-filter-section">
        <span class="filter-label">循环筛选：</span>
        <div class="cycle-tags">
          <el-tag
            v-for="cycle in CYCLE_OPTIONS"
            :key="cycle"
            :type="activeCycle === cycle ? '' : 'info'"
            :effect="activeCycle === cycle ? 'dark' : 'plain'"
            class="cycle-tag"
            @click="toggleCycleFilter(cycle)"
          >
            {{ cycle }}
          </el-tag>
          <el-tag
            :type="activeCycle === '' ? '' : 'info'"
            :effect="activeCycle === '' ? 'dark' : 'plain'"
            class="cycle-tag"
            @click="toggleCycleFilter('')"
          >
            全部
          </el-tag>
        </div>
      </div>

      <!-- 控制矩阵表 -->
      <div class="matrix-table-section">
        <div class="section-header">
          <span class="section-title">信息处理控制矩阵</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              :icon="Plus"
              @click="onAddRow"
            >
              新增控制
            </el-button>
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
        </div>

        <el-table
          :data="filteredRows"
          border
          stripe
          class="matrix-table"
          :cell-style="{ fontSize: '13px' }"
          :header-cell-style="{ fontSize: '13px', fontWeight: '600' }"
          row-key="__idx"
        >
          <!-- 序号列 -->
          <el-table-column label="#" width="45" align="center">
            <template #default="{ row }">
              <span class="row-seq">{{ row.__idx + 1 }}</span>
            </template>
          </el-table-column>

          <!-- 控制类别 -->
          <el-table-column label="控制类别" min-width="180">
            <template #default="{ row }">
              <el-select
                :model-value="row.category"
                :disabled="isReadonly"
                placeholder="选择循环"
                size="small"
                style="width: 100%"
                @change="(v: string) => updateC26RowEnum(row.__idx, 'category', v)"
              >
                <el-option
                  v-for="opt in CYCLE_OPTIONS"
                  :key="opt"
                  :label="opt"
                  :value="opt"
                />
              </el-select>
            </template>
          </el-table-column>

          <!-- 信息处理控制索引号 -->
          <el-table-column label="索引号" width="130">
            <template #default="{ row }">
              <el-tooltip :content="row.purpose || '信息处理控制索引号'" placement="top">
                <el-input
                  :model-value="row.indexNo"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="IT-R&R-xx"
                  @input="(v: string) => updateC26RowText(row.__idx, 'indexNo', v)"
                />
              </el-tooltip>
            </template>
          </el-table-column>

          <!-- 测试目的 -->
          <el-table-column label="测试目的" min-width="160">
            <template #default="{ row }">
              <el-input
                type="textarea"
                :model-value="row.purpose"
                :disabled="isReadonly"
                :autosize="{ minRows: 1, maxRows: 4 }"
                placeholder="测试目的..."
                @input="(v: string) => updateC26RowText(row.__idx, 'purpose', v)"
              />
            </template>
          </el-table-column>

          <!-- 计划测试过程 -->
          <el-table-column label="计划测试过程" min-width="160">
            <template #default="{ row }">
              <el-input
                type="textarea"
                :model-value="row.plannedTest"
                :disabled="isReadonly"
                :autosize="{ minRows: 1, maxRows: 4 }"
                placeholder="计划测试过程..."
                @input="(v: string) => updateC26RowText(row.__idx, 'plannedTest', v)"
              />
            </template>
          </el-table-column>

          <!-- 穿行测试 -->
          <el-table-column label="穿行测试" min-width="140">
            <template #default="{ row }">
              <el-input
                type="textarea"
                :model-value="row.walkthrough"
                :disabled="isReadonly"
                :autosize="{ minRows: 1, maxRows: 4 }"
                placeholder="穿行测试..."
                @input="(v: string) => updateC26RowText(row.__idx, 'walkthrough', v)"
              />
            </template>
          </el-table-column>

          <!-- 控制测试 -->
          <el-table-column label="控制测试" min-width="140">
            <template #default="{ row }">
              <el-input
                type="textarea"
                :model-value="row.controlTest"
                :disabled="isReadonly"
                :autosize="{ minRows: 1, maxRows: 4 }"
                placeholder="控制测试..."
                @input="(v: string) => updateC26RowText(row.__idx, 'controlTest', v)"
              />
            </template>
          </el-table-column>

          <!-- 测试结果 -->
          <el-table-column label="测试结果" width="120" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.testResult"
                :disabled="isReadonly"
                placeholder="—"
                size="small"
                style="width: 100%"
                @change="(v: string) => updateC26RowEnum(row.__idx, 'testResult', v)"
              >
                <el-option label="未发现例外" value="未发现例外" />
                <el-option label="发现例外" value="发现例外" />
                <el-option label="不适用" value="不适用" />
              </el-select>
            </template>
          </el-table-column>

          <!-- 客户反馈 -->
          <el-table-column label="客户反馈" min-width="140">
            <template #default="{ row }">
              <el-input
                type="textarea"
                :model-value="row.clientFeedback"
                :disabled="isReadonly"
                :autosize="{ minRows: 1, maxRows: 4 }"
                placeholder="客户反馈..."
                @input="(v: string) => updateC26RowText(row.__idx, 'clientFeedback', v)"
              />
            </template>
          </el-table-column>

          <!-- 结论 -->
          <el-table-column label="结论" width="110" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.conclusion"
                :disabled="isReadonly"
                placeholder="—"
                size="small"
                style="width: 100%"
                @change="(v: string) => updateC26RowEnum(row.__idx, 'conclusion', v)"
              >
                <el-option label="有效" value="有效" />
                <el-option label="无效" value="无效" />
                <el-option label="部分有效" value="部分有效" />
                <el-option label="不适用" value="不适用" />
              </el-select>
            </template>
          </el-table-column>

          <!-- 📎 附件 -->
          <el-table-column label="📎" width="60" align="center">
            <template #default="{ row }">
              <div class="attach-cell">
                <el-tooltip
                  v-if="c26Attachments[row.__idx]"
                  :content="c26Attachments[row.__idx]!.fileName"
                  placement="top"
                >
                  <a
                    :href="`/api/attachments/${c26Attachments[row.__idx]!.id}/download`"
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
                  :http-request="(req: any) => onUploadC26Attachment(row.__idx, req.file)"
                >
                  <el-button
                    size="small"
                    :icon="UploadFilled"
                    circle
                    :loading="uploadingC26Row === row.__idx"
                    :title="c26Attachments[row.__idx] ? '重新上传' : '上传证据'"
                  />
                </el-upload>
              </div>
            </template>
          </el-table-column>

          <!-- 证据索引 -->
          <el-table-column label="证据索引" width="120" align="center">
            <template #default="{ row }">
              <GtIndexChip
                v-if="row.evidence"
                :value="row.evidence"
                :context="getC26EvidenceContext(row)"
                :validate="true"
              />
              <el-input
                v-else-if="!isReadonly"
                :model-value="row.evidence"
                :disabled="isReadonly"
                size="small"
                placeholder="索引号"
                @input="(v: string) => updateC26RowText(row.__idx, 'evidence', v)"
              />
              <span v-else class="empty-ref">—</span>
            </template>
          </el-table-column>

          <!-- 缺陷联动 (结论=无效时自动提供 A14/C21-1 跳转) -->
          <el-table-column label="缺陷联动" width="140" align="center">
            <template #default="{ row }">
              <template v-if="row.conclusion === '无效'">
                <GtIndexChip
                  value="A14"
                  :context="`缺陷：${row.indexNo} ${row.purpose?.slice(0, 20) || ''}`"
                  :validate="true"
                />
                <GtIndexChip
                  value="C21-1"
                  :context="`缺陷汇总：${row.indexNo}`"
                  :validate="true"
                  style="margin-left: 4px"
                />
              </template>
              <span v-else class="empty-ref">—</span>
            </template>
          </el-table-column>

          <!-- 四要素 -->
          <el-table-column label="四要素" min-width="200">
            <template #default="{ row }">
              <el-checkbox-group
                :model-value="row.elements"
                :disabled="isReadonly"
                size="small"
                @change="(v: string[]) => updateC26RowElements(row.__idx, v)"
              >
                <el-checkbox
                  v-for="el in FOUR_ELEMENTS"
                  :key="el"
                  :value="el"
                >
                  {{ el }}
                </el-checkbox>
              </el-checkbox-group>
            </template>
          </el-table-column>

          <!-- 操作列 -->
          <el-table-column
            v-if="!isReadonly"
            label="操作"
            width="60"
            align="center"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                type="danger"
                :icon="Delete"
                size="small"
                link
                @click="onRemoveRow(row.__idx)"
              />
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 编制提示（details 折叠） -->
      <details class="compile-tips">
        <summary>编制提示</summary>
        <div class="tips-content">
          <p>1. 按业务循环分类录入信息处理控制，每项控制需标注覆盖的四要素。</p>
          <p>2. 信息处理控制索引号建议按 IT-R&R-xx 格式编号（IT-R&R-01, IT-R&R-02...）。</p>
          <p>3. 穿行测试和控制测试分别记录过程和发现，测试结果选择枚举值。</p>
          <p>4. 发现例外时应及时记录客户反馈并在结论中综合判断控制有效性。</p>
          <p>5. 证据索引可引用其他底稿（如 C22、B22A 等），点击 chip 可跳转。</p>
        </div>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC26InfoControl — C26 信息处理控制测试专属组件
 *
 * componentType: c26-info-processing-control
 * 单 sheet 无 sheetName 分发
 *
 * 信息处理控制矩阵动态行 + 四要素标记 + 循环分组筛选 + AI 辅助
 *
 * Spec: .kiro/specs/c25-c26-internal-audit-info-control/
 * Task: 4.2
 * Requirements: 1.1, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5
 */
import { computed, ref, onMounted, onBeforeUnmount, toRef } from 'vue'
import { InfoFilled, Plus, Delete, MagicStick, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useC25C26Data } from '@/composables/useC25C26Data'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'
import { uploadAttachment } from '@/services/commonApi'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import GtIndexChip from './GtIndexChip.vue'

defineOptions({ name: 'GtC26InfoControl' })

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

// ─── Constants ───
const FOUR_ELEMENTS = ['完整性', '准确性', '授权', '访问限制'] as const

const CYCLE_OPTIONS = [
  '与销售循环相关的控制',
  '与采购循环相关的控制',
  '与存货循环相关的控制',
  '与固定资产循环相关的控制',
  '与货币资金循环相关的控制',
  '与收入确认相关的控制',
  '与订单签订有关的控制',
  '其他',
] as const

// ─── Composables ───
const {
  c26,
  loading,
  selfLoad,
  flushPendingSaves,
  addRow,
  removeRow,
  updateC26RowText,
  updateC26RowEnum,
  updateC26RowElements,
} = useC25C26Data(
  toRef(() => props.wpId),
  toRef(() => props.projectId || ''),
  isReadonly,
)

const ai = useWpAiSuggest({ wpId: props.wpId, sheetName: 'C26' })

// ─── Cycle filter ───
const activeCycle = ref('')

function toggleCycleFilter(cycle: string) {
  activeCycle.value = activeCycle.value === cycle ? '' : cycle
}

/** 带索引的过滤后行数据 */
const filteredRows = computed(() => {
  const rows = c26.value.rows.map((row, idx) => ({ ...row, __idx: idx }))
  if (!activeCycle.value) return rows
  return rows.filter(r => r.category === activeCycle.value)
})

// ─── Dynamic row add/remove ───
async function onAddRow() {
  if (isReadonly.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入信息处理控制名称（如 IT-R&R-01）',
      '新增控制条目',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '控制名称不能为空',
        inputPlaceholder: 'IT-R&R-xx',
      },
    )
    if (value) {
      addRow(value.trim())
      emit('save')
    }
  } catch {
    // 用户取消，忽略
  }
}

function onRemoveRow(index: number) {
  if (isReadonly.value) return
  removeRow(index)
  emit('save')
}

// ─── AI assist ───
async function onAiSuggestAll() {
  if (isReadonly.value || !ai.aiEnabled.value) return
  const context = c26.value.rows
    .map((r, i) => `控制${i + 1}: ${r.indexNo} | 目的=${r.purpose || '(空)'} | 结论=${r.conclusion || '(空)'}`)
    .join('\n')
  await ai.requestSuggestion('信息处理控制矩阵-测试过程', context)
  const text = ai.adoptSuggestion()
  if (text) {
    // 应用到第一个空白穿行测试行
    const emptyIdx = c26.value.rows.findIndex(r => !r.walkthrough && !r.controlTest)
    if (emptyIdx >= 0) {
      updateC26RowText(emptyIdx, 'walkthrough', text)
    }
  }
}

// ─── 📎 附件上传 + OCR (Req 9.1, 9.3, 9.4, 9.5) ───

/** 附件信息 */
export interface C26Attachment {
  id: string
  fileName: string
  ocrMerged: boolean
}

const c26Attachments = ref<Array<C26Attachment | null>>([])
const uploadingC26Row = ref<number | null>(null)

/** 加载已有附件 */
async function loadC26Attachments() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { _silent: true } as any,
    )
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> =
      Array.isArray(res) ? res : (res as any)?.data || []

    for (const item of items) {
      const m = item.item_id?.match(/^C26-ctrl-(\d+)-attachment$/)
      if (m && item.remark) {
        const idx = parseInt(m[1]) - 1
        if (idx >= 0) {
          try {
            // 扩展数组长度以容纳
            while (c26Attachments.value.length <= idx) c26Attachments.value.push(null)
            c26Attachments.value[idx] = JSON.parse(item.remark)
          } catch { /* ignore parse error */ }
        }
      }
    }
  } catch { /* silent */ }
}

/** 上传附件 + OCR */
async function onUploadC26Attachment(index: number, file: File) {
  if (isReadonly.value) return
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return
  }

  uploadingC26Row.value = index
  try {
    // 1) 上传附件
    const fd = new FormData()
    fd.append('file', file)
    fd.append('attachment_type', 'evidence')
    fd.append('reference_type', 'workpaper')
    fd.append('reference_id', props.wpId)
    fd.append('title', `${file.name} [C26 控制${index + 1}]`)

    const uploadResp = await uploadAttachment(props.projectId || '', fd)
    const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
    if (!attachmentId) throw new Error('上传响应缺少 attachment_id')

    // 关联底稿
    try {
      await api.post(`/api/attachments/${attachmentId}/associate`, {
        wp_id: props.wpId,
        association_type: 'evidence',
        notes: `C26-ctrl-${index + 1}`,
      })
    } catch { /* 关联失败不阻断 */ }

    // 存储附件引用
    const attachment: C26Attachment = { id: attachmentId, fileName: file.name, ocrMerged: false }
    while (c26Attachments.value.length <= index) c26Attachments.value.push(null)
    c26Attachments.value[index] = attachment

    // 持久化
    await persistC26Attachment(index, attachment)
    ElMessage.success(`证据附件 "${file.name}" 已上传`)

    // 2) OCR 识别
    if (isOcrEligible(file.name)) {
      await doC26OcrMerge(file, index)
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '上传失败'
    ElMessage.error(`证据附件上传失败：${detail}`)
  } finally {
    uploadingC26Row.value = null
  }
}

function isOcrEligible(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'].includes(ext)
}

/** OCR → 确认弹窗 → merge */
async function doC26OcrMerge(file: File, index: number): Promise<void> {
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

  // 映射 OCR 字段到控制行
  const mapped = mapOcrToC26(ocrFields)
  if (mapped.length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  const previewMsg = mapped.map(m => `${m.label}：${m.value}`).join('\n')
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下信息，确认填入控制行？\n\n${previewMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消（仅保留附件）', type: 'info' },
    )
  } catch { return }

  // merge（非破坏性）
  for (const { field, value } of mapped) {
    updateC26RowText(index, field as any, value)
  }

  // 标记 ocrMerged
  if (c26Attachments.value[index]) {
    c26Attachments.value[index]!.ocrMerged = true
    await persistC26Attachment(index, c26Attachments.value[index]!)
  }
  ElMessage.success('已将 OCR 识别信息填入控制行')
}

function mapOcrToC26(fields: Record<string, any>): Array<{ label: string; field: string; value: string }> {
  const result: Array<{ label: string; field: string; value: string }> = []
  const purpose = fields.purpose || fields.control_purpose || fields['控制目的'] || fields['测试目的'] || ''
  if (purpose) result.push({ label: '测试目的', field: 'purpose', value: String(purpose) })
  const testProc = fields.test_procedure || fields.procedure || fields['测试过程'] || fields['计划测试'] || ''
  if (testProc) result.push({ label: '计划测试过程', field: 'plannedTest', value: String(testProc) })
  const walkthrough = fields.walkthrough || fields['穿行测试'] || ''
  if (walkthrough) result.push({ label: '穿行测试', field: 'walkthrough', value: String(walkthrough) })
  const feedback = fields.feedback || fields.client_feedback || fields['客户反馈'] || ''
  if (feedback) result.push({ label: '客户反馈', field: 'clientFeedback', value: String(feedback) })
  return result
}

async function persistC26Attachment(index: number, attachment: C26Attachment) {
  if (!props.wpId) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: `C26-ctrl-${index + 1}-attachment`,
        conclusion: null,
        remark: JSON.stringify(attachment),
      }],
    })
  } catch { /* silent */ }
}

/** 获取证据 chip 上下文（带缺陷摘要） */
function getC26EvidenceContext(row: any): string | undefined {
  if (row.conclusion === '无效') {
    return `缺陷：${row.indexNo} ${row.purpose?.slice(0, 30) || ''}`
  }
  return undefined
}

// ─── Lifecycle ───
onMounted(() => { selfLoad(); loadC26Attachments() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: selfLoad })
</script>

<style scoped>
.gt-c26-info-control {
  padding: 12px;
  font-size: 13px;
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
  font-size: 13px;
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
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.methodology-content p:first-child {
  margin-top: 0;
}

/* 循环筛选区 */
.cycle-filter-section {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.filter-label {
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
}

.cycle-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cycle-tag {
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.cycle-tag:hover {
  opacity: 0.85;
}

/* Section header */
.matrix-table-section {
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表格 */
.matrix-table {
  font-size: 13px;
}

.row-seq {
  font-weight: 600;
  color: #409eff;
}

.empty-ref {
  color: #c0c4cc;
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
  font-size: 13px;
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

/* 📎 附件单元格 */
.attach-cell {
  display: flex;
  align-items: center;
  justify-content: center;
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

.attach-cell :deep(.el-upload) {
  display: inline-flex;
}

.attach-cell :deep(.el-button.is-circle) {
  width: 24px;
  height: 24px;
  padding: 0;
}
</style>
