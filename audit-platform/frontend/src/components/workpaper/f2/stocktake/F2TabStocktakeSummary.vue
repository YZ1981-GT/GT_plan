<template>
  <div class="f2-summary">
    <header class="sum-hero">
      <div class="sum-hero-main">
        <div class="sum-kicker">F2-23 · G2-6-1</div>
        <h2 class="sum-title">存货监盘小结</h2>
        <p class="sum-objective">
          汇总监盘实施过程与分地点结果，评价抽盘覆盖与差异处理，形成存货存在性与状况的整体结论。
        </p>
      </div>
      <div class="sum-hero-actions">
        <GtIndexChip value="wp:F2-23" :context-project-id="projectId" />
        <F2SheetToolbar
          v-if="wpId"
          :wp-id="wpId"
          :project-id="projectId"
          api-prefix="f2-st"
          sheet="F2-23"
          :disabled="isReadonly"
          :show-import-export="false"
          review-section="F2-23-conclusion"
        />
      </div>
    </header>

    <details class="sum-guide">
      <summary>编制提示</summary>
      <ol>
        <li>按「目的 → 范围 → 地点 → 时间 → 分工 → 盘点方法 → 汇总 → 分地点结果 → 结论」编制（CAS 1311）。</li>
        <li>第七节金额在公司未结账时可暂空，并在覆盖率说明中注明原因。</li>
        <li>第八节宜按分厂逐条写明主要存货、差异与抽盘表索引；切换在线编辑时与 Word 双向回写。</li>
      </ol>
    </details>

    <F2StocktakeSheetAttachments
      v-if="wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F2-23"
    />

    <section
      v-for="group in F2_23_LAYOUT"
      :key="group.id"
      class="sum-card"
    >
      <header class="sum-card-head">
        <div>
          <h3>{{ group.title }}</h3>
          <p v-if="group.subtitle">{{ group.subtitle }}</p>
        </div>
      </header>
      <div
        class="sum-card-grid"
        :style="{ gridTemplateColumns: `repeat(${group.cols}, minmax(0, 1fr))` }"
      >
        <div
          v-for="fid in group.fieldIds"
          :key="fid"
          class="sum-field"
          :class="{ span2: isSpan2(group, fid) }"
        >
          <div class="sum-field-label">
            <span>{{ fieldMap[fid]?.label || fid }}</span>
            <button
              v-if="wpId && !isReadonly && !fieldMap[fid]?.date"
              type="button"
              class="ai-chip"
              :disabled="!aiAvailable || aiLoadingId === fid"
              :title="`AI 起草「${fieldMap[fid]?.label || fid}」`"
              :aria-label="`AI 起草${fieldMap[fid]?.label || fid}`"
              @click="aiFillField(fid, fieldMap[fid]?.label || fid)"
            >
              {{ aiLoadingId === fid ? '…' : 'AI' }}
            </button>
          </div>
          <el-date-picker
            v-if="fieldMap[fid]?.date"
            :model-value="toPickerDate(fields.fields.value[fid])"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY年MM月DD日"
            :placeholder="fieldMap[fid]?.hint || '选择日期'"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string | null) => fields.updateField(fid, v || '')"
          />
          <el-input
            v-else-if="fieldMap[fid]?.multiline"
            :model-value="fields.fields.value[fid] || ''"
            type="textarea"
            :rows="fieldMap[fid]?.rows || 2"
            :placeholder="fieldMap[fid]?.hint || ''"
            :disabled="isReadonly"
            resize="vertical"
            @update:model-value="(v: string) => fields.updateField(fid, v)"
          />
          <el-input
            v-else
            :model-value="fields.fields.value[fid] || ''"
            :placeholder="fieldMap[fid]?.hint || ''"
            :disabled="isReadonly"
            @update:model-value="(v: string) => fields.updateField(fid, v)"
          />
        </div>
      </div>
    </section>

    <section class="sum-card sum-card-conclusion">
      <header class="sum-card-head">
        <div>
          <h3>审计说明（补充）</h3>
          <p>可选：记录未写入正文的跟进说明</p>
        </div>
        <button
          v-if="wpId && !isReadonly"
          type="button"
          class="ai-chip"
          :disabled="!aiAvailable || aiLoadingId === '__note__'"
          title="AI 起草补充说明"
          aria-label="AI 起草补充说明"
          @click="aiFillNote"
        >
          {{ aiLoadingId === '__note__' ? '…' : 'AI' }}
        </button>
      </header>
      <el-input
        v-model="fields.auditNote.value"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="补充审计说明…"
        resize="vertical"
      />
    </section>

    <footer v-if="wpId && !isReadonly" class="sum-footer">
      <el-button size="small" @click="uploadOcr">附件 OCR 填入</el-button>
      <el-select v-model="ocrTargetField" size="small" placeholder="目标字段" style="width: 220px">
        <el-option
          v-for="f in multilineFields"
          :key="f.id"
          :label="f.label"
          :value="f.id"
        />
      </el-select>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'
import {
  F2_23_FIELDS,
  F2_23_LAYOUT,
  type F2PlanLayoutGroup,
  type StocktakeSectionField,
} from './f2StocktakeConfigs'
import { useF2StocktakeFields } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeAiGenerate } from '../../composables/useF2StocktakeAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import http from '@/utils/http'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const fieldIds = F2_23_FIELDS.filter((f) => !f.isSection).map((f) => f.id)
const fieldMap = Object.fromEntries(
  F2_23_FIELDS.filter((f) => !f.isSection).map((f) => [f.id, f]),
) as Record<string, StocktakeSectionField>

const fields = useF2StocktakeFields({
  fieldsKey: 'F2-23-fields',
  noteKey: 'F2-23-note',
  fieldIds,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const wpIdRef = toRef(() => props.wpId || '')
const projectIdRef = toRef(() => props.projectId || '')
const { aiAvailable, generateAndConfirm } = useF2StocktakeAiGenerate({
  wpId: wpIdRef as any,
  projectId: projectIdRef as any,
})
const aiLoadingId = ref('')
const ocrTargetField = ref('')

const multilineFields = computed(() => F2_23_FIELDS.filter((f) => f.multiline && !f.isSection))

const aiContext = computed(() => {
  const filled = Object.fromEntries(
    Object.entries(fields.fields.value).filter(([, v]) => v),
  )
  return { sheet: 'F2-23', fieldCount: Object.keys(filled).length, ...filled }
})

function isSpan2(group: F2PlanLayoutGroup, fid: string): boolean {
  if (group.cols === 1) return false
  return (
    fid === 'assignment'
    || fid === 'processOverview'
    || fid === 'coverageNote'
    || fid === 'resultByLocation'
    || fid === 'overallConclusion'
    || fid === 'followUp'
    || fid === 'purpose'
    || fid === 'scope'
    || fid === 'warehouses'
    || fid === 'countDate'
    || fid === 'countMethod'
  )
}

function toPickerDate(raw: string | undefined): string {
  const s = (raw || '').trim()
  if (!s) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?/)
  if (m) {
    return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  }
  const m2 = s.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})/)
  if (m2) {
    return `${m2[1]}-${m2[2].padStart(2, '0')}-${m2[3].padStart(2, '0')}`
  }
  return ''
}

/** 旧版字段键 → G2-6-1 新键（只在目标为空时迁移） */
function migrateLegacyFields(): void {
  const cur = fields.fields.value
  const patch: Record<string, string> = {}
  const map: Record<string, string> = {
    inventoryComposition: 'countMethod',
    sampleCoverage: 'coverageNote',
    opinionImpact: 'followUp',
  }
  for (const [from, to] of Object.entries(map)) {
    const src = (cur[from] || '').trim()
    if (src && !(cur[to] || '').trim()) patch[to] = src
  }
  // 旧差异字段并入分地点结果
  const extras = ['surplus', 'shortage', 'varianceRate', 'varianceReason', 'storageCondition', 'obsoleteFound', 'consignment', 'orgQuality']
    .map((k) => {
      const v = (cur[k] || '').trim()
      return v ? `${k}: ${v}` : ''
    })
    .filter(Boolean)
  if (extras.length && !(cur.resultByLocation || '').trim()) {
    patch.resultByLocation = extras.join('\n')
  }
  if (Object.keys(patch).length) fields.applyFields(patch, { overwriteEmptyOnly: true })
}

onMounted(() => {
  migrateLegacyFields()
})

async function aiFillField(fieldId: string, fieldLabel: string): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = fieldId
  try {
    const text = await generateAndConfirm(
      'stocktake-summary-field',
      fields.fields.value[fieldId] || '',
      { ...aiContext.value, fieldId, fieldLabel },
      `AI · ${fieldLabel}`,
    )
    if (text) {
      fields.updateField(fieldId, text)
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

async function aiFillNote(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = '__note__'
  try {
    const text = await generateAndConfirm(
      'stocktake-summary-field',
      fields.auditNote.value || '',
      { ...aiContext.value, fieldId: 'auditNote', fieldLabel: '审计说明' },
      'AI · 审计说明',
    )
    if (text) {
      fields.auditNote.value = text
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

function uploadOcr() {
  if (!ocrTargetField.value) {
    ElMessage.warning('请先选择要填入的目标字段')
    return
  }
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      const data = res.data?.data ?? res.data ?? {}
      const text = data.full_text ?? data.extracted_text ?? data.summary ?? data.extracted_fields?.content ?? ''
      if (!text) { ElMessage.warning('OCR 未识别到有效内容'); return }
      const preview = text.length > 200 ? `${text.slice(0, 200)}…` : text
      await ElMessageBox.confirm(`识别内容预览：\n${preview}`, 'OCR 识别结果确认', {
        type: 'info', confirmButtonText: '填入字段', cancelButtonText: '取消',
      })
      fields.updateField(ocrTargetField.value, text)
      ElMessage.success('OCR 内容已填入')
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('OCR 识别失败')
    }
  }
  input.click()
}
</script>

<style scoped>
.f2-summary {
  --sum-border: #e8eaef;
  --sum-muted: #6b7280;
  --sum-ink: #1f2937;
  --sum-accent: var(--gt-color-primary, #4b2d77);
  --sum-surface: var(--gt-color-primary-bg, #f4f0fa);
  padding: 8px 12px 20px;
  font-size: var(--wp-font-size, 13px);
  color: var(--sum-ink);
  max-width: 1100px;
}

.sum-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 12px;
  border: 1px solid var(--sum-border);
  border-radius: 10px;
  background: linear-gradient(135deg, #faf9ff 0%, #fff 55%);
}
.sum-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--sum-accent);
  font-weight: 600;
  margin-bottom: 4px;
}
.sum-title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.3;
}
.sum-objective {
  margin: 6px 0 0;
  color: var(--sum-muted);
  line-height: 1.5;
  max-width: 52em;
}
.sum-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
}

.sum-guide {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #dce8e6;
  background: var(--sum-surface);
}
.sum-guide summary {
  cursor: pointer;
  font-weight: 600;
  color: #374151;
  list-style: none;
}
.sum-guide summary::-webkit-details-marker { display: none; }
.sum-guide ol {
  margin: 8px 0 4px;
  padding-left: 1.2em;
  color: var(--sum-muted);
  line-height: 1.55;
}
.sum-guide li { margin: 2px 0; }

.sum-card {
  margin-bottom: 12px;
  border: 1px solid var(--sum-border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.sum-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--sum-border);
  background: var(--sum-surface);
}
.sum-card-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
}
.sum-card-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--sum-muted);
}
.sum-card-grid {
  display: grid;
  gap: 12px 14px;
  padding: 12px 14px 14px;
}
.sum-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.sum-field.span2 { grid-column: 1 / -1; }
.sum-field-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 550;
  color: #374151;
}
.sum-field :deep(.el-textarea__inner),
.sum-field :deep(.el-input__wrapper),
.sum-field :deep(.el-date-editor.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e5e7eb inset;
}
.sum-field :deep(.el-textarea__inner:focus),
.sum-field :deep(.el-input__wrapper.is-focus),
.sum-field :deep(.el-date-editor.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--sum-accent) inset !important;
}
.sum-field :deep(.el-date-editor) {
  width: 100%;
}

.ai-chip {
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--sum-surface);
  color: var(--sum-accent);
  border-radius: 999px;
  padding: 0 8px;
  height: 22px;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.02em;
  cursor: pointer;
  line-height: 20px;
  flex-shrink: 0;
}
.ai-chip:hover:not(:disabled) {
  background: #ebe4f5;
}
.ai-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.sum-card-conclusion .sum-card-head {
  background: #f3faf8;
}
.sum-card-conclusion :deep(.el-textarea) {
  padding: 0 14px 14px;
  display: block;
}

.sum-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
}

@media (max-width: 900px) {
  .sum-hero { flex-direction: column; }
  .sum-card-grid { grid-template-columns: 1fr !important; }
  .sum-field.span2 { grid-column: auto; }
}
</style>
