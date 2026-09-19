<script setup lang="ts">
/** GuidanceTabContent — 版本化编制说明、状态与来源依据的安全渲染。 */
import { computed, ref, watch } from 'vue'
import {
  useGuidancePanelStore,
  type GuidanceResolutionStatus,
  type GuidanceResponse,
  type GuidanceSource,
  type GuidanceSourceRef,
} from '@/stores/guidancePanelStore'
import { useSanitize } from '@/composables/useSanitize'

const props = defineProps<{
  guidanceData: GuidanceResponse
  fieldOverrides?: Record<string, string>
}>()

const guidanceStore = useGuidancePanelStore()
const { sanitizeHtml } = useSanitize()

const complexity = computed(() => props.guidanceData.complexity || 'high')

const SOURCE_LABELS: Record<GuidanceSource, string> = {
  template_sheet: '模板说明页',
  template_header: '模板页眉',
  docx_instructions: 'Word 编制说明',
  static_json: '标准方法论',
  typed_fallback: '类型提示',
  fallback: '通用提示',
}

const SOURCE_TAG_TYPES: Record<GuidanceSource, string> = {
  template_sheet: 'success',
  template_header: 'success',
  docx_instructions: 'success',
  static_json: 'warning',
  typed_fallback: 'warning',
  fallback: 'info',
}

const STATUS_LABELS: Record<GuidanceResolutionStatus, string> = {
  exact: '精确说明',
  parent_inherited: '沿用父级',
  typed_fallback: '类型提示',
  generic_fallback: '通用提示',
  missing: '内容待补齐',
  stale: '来源已过期',
}

const STATUS_TAG_TYPES: Record<GuidanceResolutionStatus, string> = {
  exact: 'success',
  parent_inherited: 'warning',
  typed_fallback: 'warning',
  generic_fallback: 'info',
  missing: 'danger',
  stale: 'danger',
}

const COMPLETION_LABELS: Record<string, string> = {
  complete: '九段完整',
  partial: '部分完整',
  blocked: '完成阻断',
}

const COMPLETION_TAG_TYPES: Record<string, string> = {
  complete: 'success',
  partial: 'warning',
  blocked: 'danger',
}

const SECTION_LABELS: Record<string, string> = {
  purpose: '编制目的',
  materials: '资料准备',
  data_sources: '数据来源',
  steps: '编制步骤',
  formulas: '计算公式',
  judgments: '审计判断',
  evidence: '审计证据',
  common_errors: '常见错误',
  completion: '完成标准',
}

const sourceLabel = computed(() => SOURCE_LABELS[props.guidanceData.source])
const sourceTagType = computed(() => SOURCE_TAG_TYPES[props.guidanceData.source])
const statusLabel = computed(() => STATUS_LABELS[props.guidanceData.resolution_status])
const statusTagType = computed(() => STATUS_TAG_TYPES[props.guidanceData.resolution_status])
const isFallback = computed(() => props.guidanceData.resolution_status !== 'exact')
const missingSections = computed(() => props.guidanceData.missing_sections || [])
const wholeWorkbook = computed(() => Boolean(guidanceStore.wpContext?.wholeWorkbook))

const completionStatus = computed(() => props.guidanceData.completion_status || null)
const completionLabel = computed(() => (
  completionStatus.value ? (COMPLETION_LABELS[completionStatus.value] || completionStatus.value) : ''
))
const completionTagType = computed(() => (
  completionStatus.value ? (COMPLETION_TAG_TYPES[completionStatus.value] || 'info') : 'info'
))

const provenance = computed(() => props.guidanceData.provenance || null)
const primaryProvenanceLabel = computed(() => {
  const primary = provenance.value?.primary
  if (!primary) return ''
  const source = (primary.source as string) || ''
  return SOURCE_LABELS[source as GuidanceSource] || primary.label || source || '主来源'
})
const overlayLabels = computed(() => (
  (provenance.value?.overlays || []).map((item) => {
    const source = (item.source as string) || ''
    return SOURCE_LABELS[source as GuidanceSource] || item.label || source || '叠加层'
  })
))
const extractionLabels = computed(() => (
  (provenance.value?.extraction || []).map((item) => {
    const source = (item.source as string) || ''
    return SOURCE_LABELS[source as GuidanceSource] || item.label || source || '抽取候选'
  })
))
const resolutionReasons = computed(() => props.guidanceData.resolution_reasons || [])
const exactBlockers = computed(() => props.guidanceData.exact_blockers || [])

const contextNotice = computed(() => {
  const data = props.guidanceData
  if (data.resolution_status === 'stale') {
    return '说明来源已变化，须由方法论管理员复核并重新发布后才能作为完成依据。'
  }
  if (completionStatus.value === 'blocked') {
    return '当前完成状态为阻断：请先处理下方依据与阻断项，再作为内容闭环依据。'
  }
  if (wholeWorkbook.value) {
    return `当前为整册编辑，显示 ${data.resolved_wp_code} 父级说明；在线文档内部切换工作表时本面板不会伪装跟随。`
  }
  if (data.inherited_from_parent || data.resolution_status === 'parent_inherited') {
    return `当前 sheet 暂无完整专属说明，沿用 ${data.resolved_wp_code} 编制说明。`
  }
  if (data.resolution_status === 'missing') {
    return '当前说明尚未达到九段与来源引用完整标准，仅供参考，不能计入内容闭环。'
  }
  if (data.resolution_status === 'typed_fallback') {
    return '当前仅有按底稿类型生成的操作提示，请补充本底稿的标准方法论。'
  }
  if (data.resolution_status === 'generic_fallback') {
    return '当前仅有通用提示，请补充本底稿的标准方法论。'
  }
  return ''
})

const showToc = computed(() => (
  complexity.value === 'high' && props.guidanceData.guidance.sections.length > 3
))

function scrollToSection(index: number): void {
  document.getElementById(`gt-guidance-section-${index}`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const activeSections = ref<number[]>([])
const mediumActiveSections = ref<number[]>([])
watch(
  () => props.guidanceData.guidance_version,
  () => {
    activeSections.value = props.guidanceData.guidance.sections.map((_, index) => index)
    mediumActiveSections.value = []
  },
  { immediate: true },
)
const mediumMaxItems = 3

const WP_CODE_REGEX = /\b([A-Z]\d+(?:[A-Z])?(?:-\d+[a-z]?)*(?:-[A-Z]+)?)\b/g

function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

/** 所有 v-html 只消费本函数结果；消毒异常时退回纯文本而不是裸 HTML。 */
function renderSafeTextWithWpCodes(value: unknown): string {
  const text = typeof value === 'string' ? value : String(value ?? '')
  try {
    const withChips = text.replace(
      WP_CODE_REGEX,
      '<span class="gt-guidance-wp-chip">$1</span>',
    )
    return sanitizeHtml(withChips)
  } catch (error) {
    console.warn('[GuidanceTabContent] sanitize failed; rendered as plain text', error)
    return escapeHtml(text)
  }
}

const shortText = computed(() => {
  const raw = props.guidanceData.guidance.raw_text || ''
  return raw.length <= 100 ? raw : `${raw.slice(0, 100)}…`
})

const hasQuestions = computed(() => props.guidanceData.recommended_questions?.length > 0)

const customGuidance = computed(() => (
  props.fieldOverrides?.wp_guidance_custom || ''
))

function formatSourceRef(ref: GuidanceSourceRef): string {
  const location = [ref.sheet, ref.range || ref.anchor].filter(Boolean).join(' · ')
  return [ref.kind, ref.path, location].filter(Boolean).join(' · ')
}

function sectionLabel(key: string): string {
  return SECTION_LABELS[key] || key
}
</script>

<template>
  <div class="gt-guidance-tab" :class="{ 'gt-guidance-tab--fallback': isFallback }">
    <div class="gt-guidance-tab__badges">
      <el-tag :type="(sourceTagType as any)" size="small" effect="light">
        {{ sourceLabel }}
      </el-tag>
      <el-tag :type="(statusTagType as any)" size="small" effect="plain">
        {{ statusLabel }}
      </el-tag>
      <el-tag
        v-if="completionLabel"
        :type="(completionTagType as any)"
        size="small"
        effect="plain"
        data-testid="guidance-completion-badge"
      >
        {{ completionLabel }}
      </el-tag>
      <span class="gt-guidance-tab__complexity">
        {{ { high: '高复杂度', medium: '中复杂度', low: '低复杂度' }[guidanceData.complexity] }}
      </span>
    </div>

    <div
      v-if="primaryProvenanceLabel || overlayLabels.length || extractionLabels.length"
      class="gt-guidance-tab__provenance"
      data-testid="guidance-provenance"
    >
      <div v-if="primaryProvenanceLabel" class="gt-guidance-tab__provenance-row">
        <span class="gt-guidance-tab__provenance-label">主来源</span>
        <el-tag size="small" type="success" effect="light">{{ primaryProvenanceLabel }}</el-tag>
      </div>
      <div v-if="overlayLabels.length" class="gt-guidance-tab__provenance-row">
        <span class="gt-guidance-tab__provenance-label">叠加层</span>
        <el-tag
          v-for="(label, index) in overlayLabels"
          :key="`overlay-${index}`"
          size="small"
          type="warning"
          effect="plain"
        >
          {{ label }}
        </el-tag>
      </div>
      <div v-if="extractionLabels.length" class="gt-guidance-tab__provenance-row">
        <span class="gt-guidance-tab__provenance-label">抽取候选</span>
        <el-tag
          v-for="(label, index) in extractionLabels"
          :key="`extraction-${index}`"
          size="small"
          type="info"
          effect="plain"
        >
          {{ label }}
        </el-tag>
      </div>
    </div>

    <div class="gt-guidance-tab__version">
      <span>版本 {{ guidanceData.guidance_version }}</span>
      <el-tooltip :content="`来源摘要：${guidanceData.source_digest}`" placement="bottom">
        <span class="gt-guidance-tab__digest">摘要 {{ guidanceData.source_digest.slice(0, 12) }}</span>
      </el-tooltip>
    </div>

    <div v-if="contextNotice" class="gt-guidance-tab__notice">
      {{ contextNotice }}
    </div>

    <ul v-if="resolutionReasons.length" class="gt-guidance-tab__reasons">
      <li v-for="(reason, index) in resolutionReasons" :key="`reason-${index}`">
        {{ reason }}
      </li>
    </ul>

    <div v-if="exactBlockers.length" class="gt-guidance-tab__blockers">
      <strong>阻断：</strong>
      <el-tag
        v-for="blocker in exactBlockers"
        :key="blocker"
        size="small"
        type="danger"
        effect="plain"
      >
        {{ blocker }}
      </el-tag>
    </div>

    <div v-if="missingSections.length" class="gt-guidance-tab__missing">
      <strong>待补齐：</strong>
      <el-tag
        v-for="key in missingSections"
        :key="key"
        size="small"
        type="danger"
        effect="plain"
      >
        {{ sectionLabel(key) }}
      </el-tag>
    </div>

    <template v-if="complexity === 'high'">
      <nav v-if="showToc" class="gt-guidance-tab__toc" aria-label="编制说明目录">
        <div class="gt-guidance-tab__toc-title">目录</div>
        <button
          v-for="(section, index) in guidanceData.guidance.sections"
          :key="`toc-${section.key || index}`"
          class="gt-guidance-tab__toc-item"
          type="button"
          @click="scrollToSection(index)"
        >
          {{ section.title }}
        </button>
      </nav>

      <el-collapse
        v-if="guidanceData.guidance.sections.length"
        v-model="activeSections"
        class="gt-guidance-tab__collapse"
      >
        <el-collapse-item
          v-for="(section, index) in guidanceData.guidance.sections"
          :key="`${guidanceData.guidance_version}-${section.key || index}`"
          :name="index"
          :title="section.title"
        >
          <section :id="`gt-guidance-section-${index}`" class="gt-guidance-section">
            <ol v-if="section.items.length > 1" class="gt-guidance-section__list">
              <li
                v-for="(item, itemIndex) in section.items"
                :key="itemIndex"
                class="gt-guidance-section__item"
                v-html="renderSafeTextWithWpCodes(item)"
              />
            </ol>
            <p
              v-else-if="section.items.length === 1"
              class="gt-guidance-section__paragraph"
              v-html="renderSafeTextWithWpCodes(section.items[0])"
            />
            <div v-if="section.source_refs?.length" class="gt-guidance-section__sources">
              <div class="gt-guidance-section__sources-title">来源依据</div>
              <div
                v-for="(sourceRef, sourceIndex) in section.source_refs"
                :key="`${index}-${sourceIndex}`"
                class="gt-guidance-section__source"
                :title="formatSourceRef(sourceRef)"
              >
                {{ formatSourceRef(sourceRef) }}
              </div>
            </div>
          </section>
        </el-collapse-item>
      </el-collapse>

      <div
        v-else-if="guidanceData.guidance.raw_text"
        class="gt-guidance-tab__raw"
        v-html="renderSafeTextWithWpCodes(guidanceData.guidance.raw_text)"
      />
    </template>

    <template v-else-if="complexity === 'medium'">
      <el-collapse
        v-if="guidanceData.guidance.sections.length"
        v-model="mediumActiveSections"
        class="gt-guidance-tab__collapse gt-guidance-tab__collapse--medium"
      >
        <el-collapse-item
          v-for="(section, index) in guidanceData.guidance.sections"
          :key="`${guidanceData.guidance_version}-${section.key || index}`"
          :name="index"
          :title="section.title"
        >
          <div class="gt-guidance-section">
            <ol v-if="section.items.length" class="gt-guidance-section__list">
              <li
                v-for="(item, itemIndex) in section.items.slice(0, mediumMaxItems)"
                :key="itemIndex"
                class="gt-guidance-section__item"
                v-html="renderSafeTextWithWpCodes(item)"
              />
              <li
                v-if="section.items.length > mediumMaxItems"
                class="gt-guidance-section__item gt-guidance-section__item--more"
              >
                还有 {{ section.items.length - mediumMaxItems }} 条…
              </li>
            </ol>
            <div v-if="section.source_refs?.length" class="gt-guidance-section__sources">
              <div
                v-for="(sourceRef, sourceIndex) in section.source_refs"
                :key="`${index}-${sourceIndex}`"
                class="gt-guidance-section__source"
              >
                {{ formatSourceRef(sourceRef) }}
              </div>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
      <div
        v-else-if="guidanceData.guidance.raw_text"
        class="gt-guidance-tab__raw gt-guidance-tab__raw--medium"
        v-html="renderSafeTextWithWpCodes(guidanceData.guidance.raw_text.split('\n').slice(0, 2).join('\n'))"
      />
    </template>

    <template v-else>
      <div class="gt-guidance-tab--low">
        <p class="gt-guidance-tab__low-hint" v-html="renderSafeTextWithWpCodes(shortText)" />
        <p v-if="guidanceStore.aiEnabled" class="gt-guidance-tab__low-cta">
          有疑问时可使用页面顶部的 AI 审计助手继续分析。
        </p>
      </div>
    </template>

    <div v-if="hasQuestions" class="gt-guidance-tab__questions">
      <div class="gt-guidance-tab__questions-title">建议核对问题</div>
      <div class="gt-guidance-tab__questions-list">
        <el-tag
          v-for="(question, index) in guidanceData.recommended_questions"
          :key="index"
          size="small"
          effect="plain"
          class="gt-guidance-tab__question"
        >
          {{ question }}
        </el-tag>
      </div>
    </div>

    <div class="gt-guidance-tab__custom">
      <el-collapse class="gt-guidance-tab__custom-collapse">
        <el-collapse-item title="项目补充说明" name="custom">
          <el-input
            type="textarea"
            :rows="3"
            :model-value="customGuidance"
            placeholder="项目级补充说明将在自定义模板闭环中接入确认来源"
            disabled
          />
          <p class="gt-guidance-tab__custom-hint">未确认来源的补充内容不会计入标准方法论。</p>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<style scoped>
.gt-guidance-tab {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
}

.gt-guidance-tab--fallback {
  border-left: 3px solid #e6a23c;
  padding-left: 10px;
}

.gt-guidance-tab__badges,
.gt-guidance-tab__missing,
.gt-guidance-tab__blockers {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.gt-guidance-tab__provenance {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
  padding: 8px 10px;
  background: #f7f8fa;
  border-radius: 4px;
}

.gt-guidance-tab__provenance-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.gt-guidance-tab__provenance-label {
  min-width: 4.5em;
  font-size: 11px;
  color: #666;
}

.gt-guidance-tab__reasons {
  margin: 0 0 10px;
  padding-left: 1.2em;
  font-size: 12px;
  color: #666;
}

.gt-guidance-tab__complexity,
.gt-guidance-tab__version {
  font-size: 11px;
  color: #777;
}

.gt-guidance-tab__version {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  font-variant-numeric: tabular-nums;
}

.gt-guidance-tab__digest {
  cursor: help;
}

.gt-guidance-tab__notice {
  padding: 9px 11px;
  margin-bottom: 12px;
  background: #fff8e8;
  border-left: 3px solid #e6a23c;
  color: #8a5a13;
  font-size: 12px;
}

.gt-guidance-tab__missing {
  padding: 8px 10px;
  background: #fef0f0;
  color: #b42318;
  font-size: 12px;
}

.gt-guidance-tab__toc {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--gt-bg-light, #f4f0fa);
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-radius: 6px;
}

.gt-guidance-tab__toc-title {
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--gt-primary, #4b2d77);
  letter-spacing: 1px;
}

.gt-guidance-tab__toc-item {
  display: block;
  width: 100%;
  padding: 2px 0;
  border: 0;
  background: transparent;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gt-primary, #4b2d77);
  font-size: 12px;
  cursor: pointer;
}

.gt-guidance-tab__toc-item:hover {
  text-decoration: underline;
}

.gt-guidance-tab__collapse {
  border: none;
}

.gt-guidance-tab__collapse :deep(.el-collapse-item__header) {
  height: 34px;
  line-height: 34px;
  padding-left: 0;
  border-bottom: none;
  color: var(--gt-primary, #4b2d77);
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

.gt-guidance-tab__collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.gt-guidance-tab__collapse :deep(.el-collapse-item__content) {
  padding-bottom: 10px;
}

.gt-guidance-section__list {
  margin: 0;
  padding-left: 18px;
}

.gt-guidance-section__item,
.gt-guidance-section__paragraph {
  margin: 0 0 8px;
  color: #333;
  line-height: 1.75;
  word-break: break-word;
}

.gt-guidance-section__item--more {
  margin-left: -20px;
  color: #999;
  font-style: italic;
  list-style: none;
}

.gt-guidance-section__sources {
  margin-top: 10px;
  padding: 8px 10px;
  background: #f7f8fa;
  border-radius: 4px;
}

.gt-guidance-section__sources-title {
  margin-bottom: 4px;
  color: #666;
  font-size: 11px;
  font-weight: 600;
}

.gt-guidance-section__source {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #777;
  font-size: 11px;
}

.gt-guidance-tab__raw {
  padding: 8px 0;
  color: #333;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.gt-guidance-tab__raw--medium {
  color: #666;
  font-size: 12px;
}

.gt-guidance-tab :deep(.gt-guidance-wp-chip) {
  display: inline-block;
  padding: 0 6px;
  margin: 0 2px;
  background: var(--gt-bg-light, #f4f0fa);
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-radius: 4px;
  color: var(--gt-primary, #4b2d77);
  font-size: 11px;
  font-weight: 600;
}

.gt-guidance-tab--low {
  padding: 10px 0;
}

.gt-guidance-tab__low-hint {
  margin: 0 0 10px;
  color: #333;
}

.gt-guidance-tab__low-cta {
  padding: 8px 10px;
  background: var(--gt-bg-light, #f4f0fa);
  border: 1px dashed var(--gt-border-light, #d8b8ee);
  border-radius: 6px;
  color: var(--gt-primary, #4b2d77);
  font-size: 12px;
}

.gt-guidance-tab__questions {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #eee;
}

.gt-guidance-tab__questions-title {
  margin-bottom: 8px;
  color: #666;
  font-size: 12px;
  font-weight: 600;
}

.gt-guidance-tab__questions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.gt-guidance-tab__question {
  max-width: 100%;
  height: auto;
  white-space: normal;
}

.gt-guidance-tab__custom {
  margin-top: 18px;
  padding-top: 10px;
  border-top: 1px solid #eee;
}

.gt-guidance-tab__custom-collapse :deep(.el-collapse-item__header) {
  height: 32px;
  color: #666;
  font-size: 12px;
  font-weight: 600;
  line-height: 32px;
}

.gt-guidance-tab__custom-hint {
  margin: 6px 0 0;
  color: #999;
  font-size: 11px;
}
</style>
