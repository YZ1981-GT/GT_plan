<!--
  CControlTestSubPage.vue — Cx-1-X 控制测试子页（单控制点抽样测试）

  职责：
  - 13 区域（基本信息/控制测试程序/总体定义/来源/样本规模/抽样方法/过程/偏差定义/样本结果/偏差汇总/扩大范围/缺陷结论）
  - 样本结果表：动态行 + 点选结果按钮（有效/偏差/不适用）+ 📎附件上传列
  - 偏差回填：当样本含偏差时自动设汇总表 hasDeviation=是
  - 样本规模建议 tooltip（useSampleSizeEngine）
  - GtIndexChip 引用（IDEA 工具 + A14 缺陷底稿）
  - 📎 附件上传 + OCR 识别 + 确认弹窗 merge + 持久化（Req 10.1~10.5）

  Spec: .kiro/specs/c-control-test-refresh/
  Task: 4.3, 8.2
  Requirements: 4.1, 4.2, 4.3, 4.4, 10.1, 10.2, 10.3, 10.4, 10.5
-->
<template>
  <div class="cct-subpage">
    <!-- 视图头部 -->
    <div class="cct-view-header">
      <el-button text @click="$emit('navigate', 'directory')">
        <el-icon><ArrowLeft /></el-icon>
        返回目录
      </el-button>
      <span class="cct-view-title">{{ wpCode }}-1-{{ pageIndex + 1 }} 控制测试</span>
      <span class="cct-ctrl-name" v-if="controlName">— {{ controlName }}</span>
    </div>

    <!-- ═══ 1. 基本信息（readonly 下拉） ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <span class="cct-section-title">基本信息</span>
      </template>
      <div class="cct-basic-grid">
        <div class="cct-field">
          <label>控制属性</label>
          <el-select
            v-model="page.attribute"
            :disabled="readonly"
            size="small"
            placeholder="选择属性"
            @change="(v: string) => onEnumChange('attribute', v)"
          >
            <el-option v-for="opt in ATTRIBUTE_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
        </div>
        <div class="cct-field">
          <label>控制频率</label>
          <el-select
            v-model="page.frequency"
            :disabled="readonly"
            size="small"
            placeholder="选择频率"
            @change="(v: string) => onEnumChange('frequency', v)"
          >
            <el-option v-for="opt in FREQUENCY_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
        </div>
        <div class="cct-field">
          <label>相关风险</label>
          <el-select
            v-model="page.relatedRisk"
            :disabled="readonly"
            size="small"
            placeholder="选择风险"
            @change="(v: string) => onEnumChange('relatedRisk', v)"
          >
            <el-option v-for="opt in RISK_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
        </div>
        <div class="cct-field">
          <label>测试方法</label>
          <el-select
            v-model="page.testMethod"
            :disabled="readonly"
            size="small"
            placeholder="选择方法"
            @change="(v: string) => onEnumChange('testMethod', v)"
          >
            <el-option v-for="opt in TEST_METHOD_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
        </div>
      </div>
    </el-card>

    <!-- ═══ 2. 控制测试程序 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">控制测试程序</span>
          <el-button v-if="!readonly" size="small" type="primary" link>
            <el-icon><MagicStick /></el-icon>
            AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="page.testProcedure"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="readonly"
        placeholder="描述控制测试程序"
        @input="(v: string) => onTextChange('testProcedure', v)"
      />
    </el-card>

    <!-- ═══ 3. 总体定义 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">总体定义</span>
          <el-button v-if="!readonly" size="small" type="primary" link>
            <el-icon><MagicStick /></el-icon>
            AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="page.populationDef"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="readonly"
        placeholder="定义控制测试的总体"
        @input="(v: string) => onTextChange('populationDef', v)"
      />
    </el-card>

    <!-- ═══ 4. 总体来源 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">总体来源</span>
          <el-button v-if="!readonly" size="small" type="primary" link>
            <el-icon><MagicStick /></el-icon>
            AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="page.populationSource"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="readonly"
        placeholder="说明总体数据来源"
        @input="(v: string) => onTextChange('populationSource', v)"
      />
    </el-card>

    <!-- ═══ 5. 样本规模 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <span class="cct-section-title">样本规模</span>
      </template>
      <div class="cct-sample-size-row">
        <el-tooltip :content="sampleSizeTooltip" placement="top" :disabled="!sampleSizeTooltip">
          <el-input-number
            v-model="page.sampleSize"
            :disabled="readonly"
            :min="0"
            :controls="false"
            size="small"
            class="cct-sample-size-input"
            placeholder="样本量"
            @change="(v: number | null) => onSampleSizeChange(v ?? null)"
          />
        </el-tooltip>
        <span class="cct-sample-size-hint" v-if="sampleSizeTooltip">
          <el-icon><InfoFilled /></el-icon>
          {{ sampleSizeTooltip }}
        </span>
      </div>
    </el-card>

    <!-- ═══ 6. 抽样方法 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <span class="cct-section-title">抽样方法</span>
      </template>
      <el-input
        v-model="page.samplingMethod"
        :disabled="readonly"
        size="small"
        placeholder="如：随机抽样"
        @input="(v: string) => onTextChange('samplingMethod', v)"
      />
    </el-card>

    <!-- ═══ 7. 抽样过程（Req 10.4 GtIndexChip 引用抽样工具） ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">抽样过程</span>
          <div class="cct-tool-chips">
            <el-button v-if="!readonly" size="small" type="primary" link>
              <el-icon><MagicStick /></el-icon>
              AI辅助
            </el-button>
            <GtIndexChip :value="samplingToolRef" class="cct-tool-chip" />
          </div>
        </div>
      </template>
      <div class="cct-sampling-process-area">
        <el-input
          v-model="page.samplingProcess"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="readonly"
          placeholder="描述抽样过程（可引用IDEA等审计工具底稿）"
          @input="(v: string) => onTextChange('samplingProcess', v)"
        />
        <div class="cct-sampling-ref-row" v-if="!readonly">
          <el-input
            v-model="samplingToolRef"
            size="small"
            placeholder="输入引用底稿索引（如 IDEA）"
            class="cct-sampling-ref-input"
            @input="onSamplingToolRefChange"
          />
          <span class="cct-sampling-ref-hint">
            <el-icon><InfoFilled /></el-icon>
            输入底稿编码后，点击索引芯片可跳转到引用底稿
          </span>
        </div>
      </div>
    </el-card>

    <!-- ═══ 8. 偏差定义 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">偏差定义</span>
          <el-button v-if="!readonly" size="small" type="primary" link>
            <el-icon><MagicStick /></el-icon>
            AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="page.deviationDef"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="readonly"
        placeholder="定义什么情况构成控制偏差"
        @input="(v: string) => onTextChange('deviationDef', v)"
      />
    </el-card>

    <!-- ═══ 9. 样本结果表（动态行 + 点选结果 + 📎附件上传） ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">实施测试 — 样本结果</span>
          <el-button
            v-if="!readonly"
            type="primary"
            size="small"
            @click="handleAddSample"
          >
            <el-icon><Plus /></el-icon>
            添加样本
          </el-button>
        </div>
      </template>

      <el-table :data="page.samples" border size="small" class="cct-sample-table">
        <!-- 序号 -->
        <el-table-column type="index" label="#" width="45" align="center" />

        <!-- 📎 附件上传列（Req 10.1） -->
        <el-table-column label="📎" width="65" align="center">
          <template #default="{ $index }">
            <div class="cct-attach-cell">
              <!-- 已有附件：显示文件名链接 -->
              <el-tooltip
                v-if="sampleAttachments[$index]"
                :content="sampleAttachments[$index]!.fileName"
                placement="top"
              >
                <a
                  :href="`/api/attachments/${sampleAttachments[$index]!.id}/download`"
                  target="_blank"
                  class="cct-attach-link"
                  @click.stop
                >📎</a>
              </el-tooltip>
              <!-- 上传按钮（非只读模式） -->
              <el-upload
                v-if="!readonly"
                :auto-upload="true"
                :show-file-list="false"
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
                :http-request="(req: any) => onUploadSampleAttachment($index, req.file)"
              >
                <el-button
                  size="small"
                  :icon="UploadFilled"
                  circle
                  :loading="uploadingRow === $index"
                  :title="sampleAttachments[$index] ? '重新上传' : '上传凭证'"
                />
              </el-upload>
              <!-- readonly 模式仅查看（Req 10.5） -->
              <span v-if="readonly && !sampleAttachments[$index]" class="cct-no-attach">—</span>
            </div>
          </template>
        </el-table-column>

        <!-- 样本描述 -->
        <el-table-column label="样本描述" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.description"
              :disabled="readonly"
              size="small"
              placeholder="凭证号/单据信息"
              @input="(v: string) => onSampleDescChange($index, v)"
            />
          </template>
        </el-table-column>

        <!-- 金额（OCR 可填充字段） -->
        <el-table-column label="金额" width="130">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.amount"
              :disabled="readonly"
              size="small"
              placeholder="金额"
              @input="(v: string) => onSampleFieldChange($index, 'amount', v)"
            />
          </template>
        </el-table-column>

        <!-- 结果（点选按钮组） -->
        <el-table-column label="结果" width="240" align="center">
          <template #default="{ row, $index }">
            <el-radio-group
              :model-value="row.result"
              :disabled="readonly"
              size="small"
              @change="(v: string) => onSampleResultChange($index, v)"
            >
              <el-radio-button value="有效">
                <span class="result-btn result-effective">有效</span>
              </el-radio-button>
              <el-radio-button value="偏差">
                <span class="result-btn result-deviation">偏差</span>
              </el-radio-button>
              <el-radio-button value="不适用">
                <span class="result-btn result-na">不适用</span>
              </el-radio-button>
            </el-radio-group>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!readonly" label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="handleRemoveSample($index)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="page.samples.length === 0" class="cct-empty-samples">
        暂无样本，请点击「添加样本」
      </div>
    </el-card>

    <!-- ═══ 10. 偏差汇总 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <span class="cct-section-title">识别的偏差汇总</span>
      </template>
      <div class="cct-deviation-summary">
        <div class="cct-stats-row">
          <span class="cct-stat-item">样本总数：<strong>{{ page.samples.length }}</strong></span>
          <span class="cct-stat-item">有效：<strong>{{ effectiveCount }}</strong></span>
          <span class="cct-stat-item cct-stat-deviation" :class="{ 'has-deviation': deviationCount > 0 }">
            偏差：<strong>{{ deviationCount }}</strong>
          </span>
          <span class="cct-stat-item">不适用：<strong>{{ naCount }}</strong></span>
        </div>
        <div v-if="deviationCount > 0" class="cct-deviation-note">
          <el-icon><WarningFilled /></el-icon>
          <span>已识别 {{ deviationCount }} 项偏差，汇总表「是否识别出偏差」已自动标记为「是」</span>
        </div>
      </div>
    </el-card>

    <!-- ═══ 11. 考虑扩大范围 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">考虑扩大测试范围</span>
          <el-button v-if="!readonly" size="small" type="primary" link>
            <el-icon><MagicStick /></el-icon>
            AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="expandScope"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="readonly"
        placeholder="说明是否需要扩大测试范围及原因"
        @input="onExpandScopeChange"
      />
    </el-card>

    <!-- ═══ 12. 控制缺陷结论 ═══ -->
    <el-card shadow="never" class="cct-section-card">
      <template #header>
        <div class="cct-section-header-row">
          <span class="cct-section-title">控制缺陷结论</span>
          <div class="cct-section-actions">
            <el-button v-if="!readonly" size="small" type="primary" link>
              <el-icon><MagicStick /></el-icon>
              AI辅助
            </el-button>
            <GtIndexChip value="A14" class="cct-tool-chip" />
          </div>
        </div>
      </template>
      <el-input
        v-model="defectConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="readonly"
        placeholder="控制缺陷结论（联动A14缺陷底稿）"
        @input="onDefectConclusionChange"
      />
    </el-card>

    <!-- 底部导航 -->
    <div class="cct-subpage-footer">
      <el-button @click="$emit('navigate', 'summary')">返回汇总表</el-button>
      <el-button
        v-if="deviationCount > 0"
        type="warning"
        @click="$emit('navigate', `deviation-${pageIndex + 1}`)"
      >
        进入偏差评价 →
      </el-button>
    </div>

    <!-- 编制提示（底部折叠） -->
    <details class="cct-compilation-tips">
      <summary>编制提示 — 控制测试子页</summary>
      <div class="cct-tips-content">
        <p>• 总体定义应明确测试的总体边界（时间范围、数据来源、记录完整性）。</p>
        <p>• 样本规模参照汇总表顶部的区间参考表，结合控制频率确定。</p>
        <p>• 样本结果点选「有效/偏差/不适用」，偏差项会自动回填汇总表。</p>
        <p>• 存在偏差时，建议进入 Cx-2 偏差评价决策树分析偏差性质。</p>
        <p>• 抽样过程可引用 IDEA 等审计工具底稿（通过索引芯片）。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue'
import { ArrowLeft, Plus, Delete, MagicStick, InfoFilled, WarningFilled, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { suggestSampleSize } from '@/composables/useSampleSizeEngine'
import { api } from '@/services/apiProxy'
import { uploadAttachment } from '@/services/commonApi'
import http from '@/utils/http'
import type { ControlPage, SampleResult } from '@/composables/useCControlTestData'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode: string
  pageIndex: number
  page: ControlPage
  controlName: string
  readonly: boolean
  // Update helpers from parent
  updateCtrlPageText: (pageIndex: number, field: string, value: string) => void
  updateCtrlPageEnum: (pageIndex: number, field: string, value: string) => void
  updateCtrlPageSampleSize: (pageIndex: number, value: number | null) => void
  addSample: (pageIndex: number) => void
  removeSample: (pageIndex: number, sampleIndex: number) => void
  updateSampleDescription: (pageIndex: number, sampleIndex: number, value: string) => void
  updateSampleResult: (pageIndex: number, sampleIndex: number, value: SampleResult['result']) => void
  // Deviation backfill
  updateSummaryDeviation: (pageIndex: number, hasDeviation: '是' | '否') => void
}>()

const emit = defineEmits<{
  (e: 'navigate', view: string): void
}>()

// ─── 下拉选项常量 ────────────────────────────────────────────────────────────

const ATTRIBUTE_OPTIONS = ['人工的', '自动化的', '人工依赖信息系统控制']
const FREQUENCY_OPTIONS = ['每笔交易', '每天', '每周', '每半月', '每月', '每季度', '每年', '非常规/低运行频率', '其他']
const RISK_OPTIONS = ['高', '中', '低']
const TEST_METHOD_OPTIONS = ['询问', '检查', '观察', '重新执行', '前期', '前推', '利用内部审计工作', '利用服务机构的审计报告']

// ─── 本地 ref（非结构化字段用 composable 外存） ──────────────────────────────

// expand scope 和 defect conclusion 存在 ctrl page text fields
const expandScope = ref('')
const defectConclusion = ref('')

// 抽样工具引用（GtIndexChip value）— Req 10.4
const samplingToolRef = ref('IDEA')

// ─── 附件状态（Req 10.1, 10.5） ──────────────────────────────────────────────

/** 样本行附件信息 */
interface SampleAttachmentInfo {
  id: string
  fileName: string
  ocrMerged: boolean
}

const sampleAttachments = ref<Array<SampleAttachmentInfo | null>>([])
const uploadingRow = ref<number | null>(null)

// 初始化：填充 null 数组 + 加载已有附件
onMounted(async () => {
  syncAttachmentArray()
  await loadAttachments()
})

// 样本行数变化时同步附件数组长度
watch(() => props.page.samples.length, () => {
  syncAttachmentArray()
})

function syncAttachmentArray() {
  const target = props.page.samples.length
  while (sampleAttachments.value.length < target) {
    sampleAttachments.value.push(null)
  }
  if (sampleAttachments.value.length > target) {
    sampleAttachments.value.length = target
  }
}

/** 从 checklist_responses 加载已有附件引用（Req 10.5） */
async function loadAttachments() {
  if (!props.wpId) return
  try {
    const n = props.wpCode.replace(/^C/i, '')
    const m = props.pageIndex + 1
    const res = await api.get<any[]>(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { _silent: true } as any,
    )
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> =
      Array.isArray(res) ? res : (res as any)?.data || []

    // item_id 格式: C{n}-ctrl-{m}-sample-{s}-attachment
    const prefix = `C${n}-ctrl-${m}-sample-`
    for (const item of items) {
      if (!item.item_id?.startsWith(prefix) || !item.item_id.endsWith('-attachment')) continue
      const seg = item.item_id.replace(prefix, '').replace('-attachment', '')
      const sIdx = parseInt(seg) - 1 // sample seq 从 1 开始
      if (isNaN(sIdx) || sIdx < 0 || sIdx >= sampleAttachments.value.length) continue
      if (item.remark) {
        try {
          sampleAttachments.value[sIdx] = JSON.parse(item.remark)
        } catch { /* ignore parse error */ }
      }
    }

    // 加载抽样工具引用
    const toolRefItem = items.find(i => i.item_id === `C${n}-ctrl-${m}-sampling-tool-ref`)
    if (toolRefItem?.conclusion) {
      samplingToolRef.value = toolRefItem.conclusion
    }
  } catch { /* silent */ }
}

// ─── 附件上传 + OCR（Req 10.1, 10.2, 10.3） ─────────────────────────────────

/** 判断文件是否适合 OCR */
function isOcrEligible(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'].includes(ext)
}

/** 上传附件 + OCR 识别 + 确认弹窗 merge */
async function onUploadSampleAttachment(index: number, file: File) {
  if (props.readonly) return
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
    fd.append('title', `${file.name} [${props.wpCode}-1-${props.pageIndex + 1} 样本${index + 1}]`)

    const uploadResp = await uploadAttachment(props.projectId || '', fd)
    const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
    if (!attachmentId) throw new Error('上传响应缺少 attachment_id')

    // 关联到底稿
    try {
      await api.post(`/api/attachments/${attachmentId}/associate`, {
        wp_id: props.wpId,
        association_type: 'evidence',
        notes: `${props.wpCode}-ctrl-${props.pageIndex + 1}-sample-${index + 1}`,
      })
    } catch { /* 关联失败不阻断 */ }

    // 存储附件引用
    const attachment: SampleAttachmentInfo = { id: attachmentId, fileName: file.name, ocrMerged: false }
    sampleAttachments.value[index] = attachment

    // 持久化附件信息到 checklist_responses（Req 10.5）
    await persistAttachment(index, attachment)

    ElMessage.success(`样本附件 "${file.name}" 已上传`)

    // 2) OCR 识别（仅图片/PDF 可识别）— Req 10.2
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

/**
 * OCR 识别 + 确认弹窗 + merge 填入（Req 10.2）
 * 复用 /d4/contract-ocr 端点
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
    // OCR 失败（Req 10.3）：提示手动填写，附件已保留
    ElMessage.warning('OCR识别失败，请手动填写（附件已保留）')
    return
  }

  if (!ocrFields || Object.keys(ocrFields).length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  // 映射 OCR 字段到样本行字段
  const mapped = mapOcrToSample(ocrFields)
  if (mapped.length === 0) {
    ElMessage.info('OCR 未识别到可填充字段，请手动补充')
    return
  }

  // 确认弹窗（Req 10.2）
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

  // merge 填入样本行对应字段
  for (const { field, value } of mapped) {
    if (field === 'description') {
      props.updateSampleDescription(props.pageIndex, index, value)
    } else if (field === 'amount') {
      onSampleFieldChange(index, 'amount', value)
    }
  }

  // 标记 OCR 已 merge
  if (sampleAttachments.value[index]) {
    sampleAttachments.value[index]!.ocrMerged = true
    await persistAttachment(index, sampleAttachments.value[index]!)
  }
  ElMessage.success('已将 OCR 识别信息填入样本行')
}

/** 映射 OCR 字段到样本行（描述/金额） */
function mapOcrToSample(fields: Record<string, any>): Array<{ label: string; field: string; value: string }> {
  const result: Array<{ label: string; field: string; value: string }> = []

  // 描述：凭证号/摘要/单据号
  const desc = fields.voucher_no || fields.voucherNo || fields['凭证号']
    || fields.summary || fields['摘要'] || fields.title || fields['标题'] || ''
  if (desc) {
    result.push({ label: '样本描述', field: 'description', value: String(desc) })
  }

  // 金额
  const amount = fields.amount || fields['金额'] || fields.total || fields['合计'] || ''
  if (amount) {
    result.push({ label: '金额', field: 'amount', value: String(amount) })
  }

  return result
}

/** 持久化附件信息到 checklist_responses（Req 10.5） */
async function persistAttachment(index: number, attachment: SampleAttachmentInfo) {
  if (!props.wpId) return
  const n = props.wpCode.replace(/^C/i, '')
  const m = props.pageIndex + 1
  const s = index + 1
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: `C${n}-ctrl-${m}-sample-${s}-attachment`,
        conclusion: null,
        remark: JSON.stringify(attachment),
      }],
    })
  } catch { /* silent */ }
}

// ─── 抽样工具引用持久化（Req 10.4） ─────────────────────────────────────────

function onSamplingToolRefChange(value: string) {
  samplingToolRef.value = value
  persistSamplingToolRef(value)
}

async function persistSamplingToolRef(value: string) {
  if (!props.wpId || props.readonly) return
  const n = props.wpCode.replace(/^C/i, '')
  const m = props.pageIndex + 1
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: `C${n}-ctrl-${m}-sampling-tool-ref`,
        conclusion: value,
        remark: null,
      }],
    })
  } catch { /* silent */ }
}

// ─── 样本统计 ────────────────────────────────────────────────────────────────

const effectiveCount = computed(() => props.page.samples.filter(s => s.result === '有效').length)
const deviationCount = computed(() => props.page.samples.filter(s => s.result === '偏差').length)
const naCount = computed(() => props.page.samples.filter(s => s.result === '不适用').length)

// ─── 偏差回填汇总表 ─────────────────────────────────────────────────────────

watch(deviationCount, (count) => {
  // 自动回填汇总表 hasDeviation
  props.updateSummaryDeviation(props.pageIndex, count > 0 ? '是' : '否')
}, { immediate: true })

// ─── 样本规模建议 tooltip ─────────────────────────────────────────────────────

const sampleSizeTooltip = computed(() => {
  const freq = props.page.frequency
  if (!freq) return ''

  const freqMap: Record<string, string> = {
    '每笔交易': '每天多次', '每天': '每天', '每周': '每周',
    '每半月': '每半月', '每月': '每月', '每季度': '每季度',
    '每年': '每年', '非常规/低运行频率': '每年', '其他': '',
  }
  const mapped = freqMap[freq] || ''
  if (!mapped) return ''

  const defaultCounts: Record<string, number> = {
    '每天多次': 500, '每天': 250, '每周': 52,
    '每半月': 24, '每月': 12, '每季度': 4, '每年': 1,
  }
  const total = defaultCounts[mapped] || 0
  if (total <= 0) return ''

  const result = suggestSampleSize(mapped, total)
  if (result.min === 0 && result.max === 0) return result.note || ''

  let tip = `建议样本量：${result.min}`
  if (result.max !== result.min) tip += `~${result.max}`
  tip += '（基于致同2025样本规模区间表，按频率×次数建议）'
  return tip
})

// ─── 字段变更处理 ─────────────────────────────────────────────────────────────

function onTextChange(field: string, value: string) {
  props.updateCtrlPageText(props.pageIndex, field, value)
}

function onEnumChange(field: string, value: string) {
  props.updateCtrlPageEnum(props.pageIndex, field, value)
}

function onSampleSizeChange(value: number | null) {
  props.updateCtrlPageSampleSize(props.pageIndex, value)
}

function onExpandScopeChange() {
  props.updateCtrlPageText(props.pageIndex, 'expandScope', expandScope.value)
}

function onDefectConclusionChange() {
  props.updateCtrlPageText(props.pageIndex, 'defectConclusion', defectConclusion.value)
}

// ─── 样本操作 ────────────────────────────────────────────────────────────────

function handleAddSample() {
  props.addSample(props.pageIndex)
}

function handleRemoveSample(sampleIndex: number) {
  props.removeSample(props.pageIndex, sampleIndex)
}

function onSampleDescChange(sampleIndex: number, value: string) {
  props.updateSampleDescription(props.pageIndex, sampleIndex, value)
}

function onSampleResultChange(sampleIndex: number, value: string) {
  props.updateSampleResult(props.pageIndex, sampleIndex, value as SampleResult['result'])
}

/** 样本行通用字段变更（amount 等新字段） */
function onSampleFieldChange(sampleIndex: number, field: string, value: string) {
  // 通过 description 通道暂存 amount（将来可扩展 SampleResult 接口）
  // 目前直接更新 row 对象属性
  const row = props.page.samples[sampleIndex] as any
  if (row) {
    row[field] = value
    // 触发持久化
    props.updateCtrlPageText(props.pageIndex, `sample-${sampleIndex}-${field}`, value)
  }
}
</script>

<style scoped>
.cct-subpage {
  font-size: 13px;
}

.cct-view-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.cct-view-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.cct-ctrl-name {
  font-size: 14px;
  color: #6b7280;
}

/* ─── Section Cards ─── */
.cct-section-card {
  margin-bottom: 12px;
}

.cct-section-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: #f9fafb;
}

.cct-section-card :deep(.el-card__body) {
  padding: 12px 16px;
}

.cct-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.cct-section-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.cct-section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── Basic Info Grid ─── */
.cct-basic-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px 24px;
}

.cct-field label {
  display: block;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.cct-field :deep(.el-select) {
  width: 100%;
}

/* ─── Sample Size ─── */
.cct-sample-size-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cct-sample-size-input {
  width: 120px;
}

.cct-sample-size-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #6b7280;
}

/* ─── Sample Table 13px 铁律 ─── */
.cct-sample-table {
  font-size: 13px;
}

.cct-sample-table :deep(.el-table__body td) {
  font-size: 13px;
}

.cct-sample-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
}

.cct-sample-table :deep(.el-radio-button__inner) {
  padding: 5px 10px;
  font-size: 12px;
}

.result-btn {
  font-size: 12px;
}

.result-effective { color: #52c41a; }
.result-deviation { color: #ff4d4f; }
.result-na { color: #bfbfbf; }

.cct-empty-samples {
  text-align: center;
  padding: 24px;
  color: #9ca3af;
  font-size: 13px;
}

/* ─── Deviation Summary ─── */
.cct-deviation-summary {
  font-size: 13px;
}

.cct-stats-row {
  display: flex;
  gap: 24px;
  margin-bottom: 8px;
}

.cct-stat-item {
  color: #374151;
}

.cct-stat-deviation.has-deviation {
  color: #ff4d4f;
  font-weight: 500;
}

.cct-deviation-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 4px;
  color: #c2410c;
  font-size: 12px;
}

/* ─── Tool Chip ─── */
.cct-tool-chip {
  flex-shrink: 0;
}

.cct-tool-chips {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── Sampling Process Reference ─── */
.cct-sampling-process-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cct-sampling-ref-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.cct-sampling-ref-input {
  width: 200px;
}

.cct-sampling-ref-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #9ca3af;
}

/* ─── Attachment Cell（Req 10.1）─── */
.cct-attach-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.cct-attach-link {
  text-decoration: none;
  font-size: 14px;
  cursor: pointer;
}

.cct-attach-link:hover {
  opacity: 0.7;
}

.cct-no-attach {
  color: #d1d5db;
  font-size: 12px;
}

/* ─── Footer ─── */
.cct-subpage-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

/* ─── 编制提示 details 折叠 ─── */
.cct-compilation-tips {
  margin-top: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}

.cct-compilation-tips summary {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  background: #f9fafb;
  cursor: pointer;
  user-select: none;
}

.cct-compilation-tips summary:hover {
  background: #f3f4f6;
}

.cct-compilation-tips[open] summary {
  border-bottom: 1px solid #e5e7eb;
}

.cct-tips-content {
  padding: 12px 16px;
  font-size: 12px;
  color: #4b5563;
  line-height: 1.8;
}

.cct-tips-content p {
  margin: 0 0 4px;
}
</style>
