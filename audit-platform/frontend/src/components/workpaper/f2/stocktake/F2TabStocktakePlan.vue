<template>
  <div class="f2-plan">
    <!-- 顶栏 -->
    <header class="plan-hero">
      <div class="plan-hero-main">
        <div class="plan-kicker">F2-22 · G2-6-2</div>
        <h2 class="plan-title">存货监盘计划</h2>
        <p class="plan-objective">
          制定充分的监盘计划，确保范围与抽盘覆盖关键风险，为存货存在性与状况认定提供程序基础。
        </p>
      </div>
      <div class="plan-hero-actions">
        <GtIndexChip value="wp:F2-22" :context-project-id="projectId" />
        <F2SheetToolbar
          v-if="wpId"
          :wp-id="wpId"
          :project-id="projectId"
          api-prefix="f2-st"
          sheet="F2-22"
          :disabled="isReadonly"
          :show-import-export="false"
          review-section="F2-22-conclusion"
        />
      </div>
    </header>

    <details class="plan-guide">
      <summary>编制提示</summary>
      <ol>
        <li>按「目的 → 范围 → 地点 → 时间 → 分工 → 准备/构成分析 → 方式 → 要求」编制（CAS 1311）。</li>
        <li>构成分析应支撑重点监盘与抽盘安排；要求中宜明确覆盖率（如数量≥50%、金额≥70%）。</li>
        <li>各字段旁 AI 可单独起草，填入后可继续编辑；切换在线编辑时与 Word 双向回写。</li>
      </ol>
    </details>

    <F2StocktakeSheetAttachments
      v-if="wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F2-22"
    />

    <nav class="st-sec-nav" aria-label="分区导航">
      <button
        v-for="item in planNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <!-- 分区卡片 -->
    <section
      v-for="group in F2_22_LAYOUT"
      :id="`st-${group.id}`"
      :key="group.id"
      class="plan-card"
      :data-cols="group.cols"
    >
      <header class="plan-card-head">
        <div>
          <h3>{{ group.title }}</h3>
          <p v-if="group.subtitle">{{ group.subtitle }}</p>
        </div>
      </header>
      <div class="plan-card-grid" :style="{ gridTemplateColumns: `repeat(${group.cols}, minmax(0, 1fr))` }">
        <div
          v-for="fid in group.fieldIds"
          :key="fid"
          class="plan-field"
          :class="{ span2: isSpan2(group, fid) }"
        >
          <div class="plan-field-label">
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

    <!-- 结论 -->
    <section id="st-conclusion" class="plan-card plan-card-conclusion">
      <header class="plan-card-head">
        <div>
          <h3>监盘计划结论</h3>
          <p>概括计划适当性、覆盖安排与待跟进事项</p>
        </div>
        <button
          v-if="wpId && !isReadonly"
          type="button"
          class="ai-chip"
          :disabled="!aiAvailable || aiLoadingId === '__note__'"
          title="AI 起草监盘计划结论"
          aria-label="AI 起草监盘计划结论"
          @click="aiFillNote"
        >
          {{ aiLoadingId === '__note__' ? '…' : 'AI' }}
        </button>
      </header>
      <el-input
        v-model="fields.auditNote.value"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="对本监盘计划的总体评价…"
        resize="vertical"
      />
    </section>

    <footer v-if="wpId && !isReadonly" class="plan-footer">
      <el-button size="small" @click="uploadOcr">附件 OCR 填入</el-button>
      <el-select v-model="ocrTargetField" size="small" placeholder="目标字段" style="width: 200px">
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
import { computed, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'
import { F2_22_FIELDS, F2_22_LAYOUT, type F2PlanLayoutGroup, type StocktakeSectionField } from './f2StocktakeConfigs'
import { useF2StocktakeFields } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeAiGenerate } from '../../composables/useF2StocktakeAiGenerate'
import { useStickySectionNav } from '../../composables/useStickySectionNav'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import http from '@/utils/http'

function shortNavLabel(title: string): string {
  return title
    .replace(/^[\d一二三四五六七八九十～\-·\s]+/, '')
    .replace(/^[·\s]+/, '')
    .slice(0, 8) || title
}

const planNav = [
  ...F2_22_LAYOUT.map((g) => ({ id: `st-${g.id}`, label: shortNavLabel(g.title) })),
  { id: 'st-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(planNav)

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const fieldIds = F2_22_FIELDS.filter((f) => !f.isSection).map((f) => f.id)
const fieldMap = Object.fromEntries(
  F2_22_FIELDS.filter((f) => !f.isSection).map((f) => [f.id, f]),
) as Record<string, StocktakeSectionField>

const fields = useF2StocktakeFields({
  fieldsKey: 'F2-22-fields',
  noteKey: 'F2-22-note',
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

const multilineFields = computed(() => F2_22_FIELDS.filter((f) => f.multiline && !f.isSection))

const aiContext = computed(() => {
  const filled = Object.fromEntries(
    Object.entries(fields.fields.value).filter(([, v]) => v),
  )
  return { sheet: 'F2-22', fieldCount: Object.keys(filled).length, ...filled }
})

/** 双列卡片中，分工安排占满一行 */
function isSpan2(group: F2PlanLayoutGroup, fid: string): boolean {
  return group.cols === 2 && fid === 'assignment'
}

/** 兼容 Word/旧数据中的中文日期，转为 YYYY-MM-DD 供日期选择器使用 */
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

async function aiFillField(fieldId: string, fieldLabel: string): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = fieldId
  try {
    const text = await generateAndConfirm(
      'stocktake-plan-field',
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
      'stocktake-plan-field',
      fields.auditNote.value || '',
      { ...aiContext.value, fieldId: 'planConclusion', fieldLabel: '监盘计划结论' },
      'AI · 监盘计划结论',
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
.f2-plan {
  --plan-border: #e8eaef;
  --plan-muted: #6b7280;
  --plan-ink: #1f2937;
  --plan-accent: var(--gt-color-primary, #334155);
  --plan-surface: var(--gt-color-primary-bg, #f4f0fa);
  padding: 8px 12px 20px;
  font-size: var(--wp-font-size, 13px);
  color: var(--plan-ink);
  max-width: 1100px;
}

.plan-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 12px;
  border: 1px solid var(--plan-border);
  border-radius: 10px;
  background: linear-gradient(135deg, #f8fafc 0%, #fff 55%);
}
.plan-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--plan-accent);
  font-weight: 600;
  margin-bottom: 4px;
}
.plan-title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.3;
}
.plan-objective {
  margin: 6px 0 0;
  color: var(--plan-muted);
  line-height: 1.5;
  max-width: 52em;
}
.plan-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
}

.plan-guide {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #e3e7f0;
  background: var(--plan-surface);
}
.plan-guide summary {
  cursor: pointer;
  font-weight: 600;
  color: #374151;
  list-style: none;
}
.plan-guide summary::-webkit-details-marker { display: none; }
.plan-guide ol {
  margin: 8px 0 4px;
  padding-left: 1.2em;
  color: var(--plan-muted);
  line-height: 1.55;
}
.plan-guide li { margin: 2px 0; }

.plan-card {
  margin-bottom: 12px;
  border: 1px solid var(--plan-border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.plan-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--plan-border);
  background: var(--plan-surface);
}
.plan-card-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
}
.plan-card-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--plan-muted);
}
.plan-card-grid {
  display: grid;
  gap: 12px 14px;
  padding: 12px 14px 14px;
}
.plan-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.plan-field.span2 { grid-column: 1 / -1; }
.plan-field-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 550;
  color: #374151;
}
.plan-field :deep(.el-textarea__inner),
.plan-field :deep(.el-input__wrapper),
.plan-field :deep(.el-date-editor.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e5e7eb inset;
}
.plan-field :deep(.el-textarea__inner:focus),
.plan-field :deep(.el-input__wrapper.is-focus),
.plan-field :deep(.el-date-editor.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--plan-accent) inset !important;
}
.plan-field :deep(.el-date-editor) {
  width: 100%;
}

.ai-chip {
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--plan-surface);
  color: var(--plan-accent);
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
  background: #f1f5f9;
}
.ai-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.plan-card-conclusion .plan-card-head {
  background: #f8f7fc;
}
.plan-card-conclusion :deep(.el-textarea) {
  padding: 0 14px 14px;
  display: block;
}

.plan-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
}

@media (max-width: 900px) {
  .plan-hero { flex-direction: column; }
  .plan-card-grid { grid-template-columns: 1fr !important; }
  .plan-field.span2 { grid-column: auto; }
}
</style>

<style src="./f2StocktakeSoftNav.css"></style>
