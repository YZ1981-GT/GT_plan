<script setup lang="ts">
/**
 * GuidanceTabContent — 编制说明 Tab 内容渲染
 *
 * 渲染 API 返回的 guidance 数据：
 * - SourceBadge：来源标签（模板提取/知识库/通用提示）
 * - TableOfContents：内容超 3 节时显示迷你目录
 * - GuidanceContent：结构化 sections 渲染（el-collapse）
 * - wp_code 链接化（如 A17-1 渲染为可点击 chip）
 * - fallback 态淡化样式
 * - RecommendedQuestions：推荐问题快捷按钮
 * - 复杂度自适应渲染（高/中/低）
 * - 补充说明区域（P4 实现保存逻辑）
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.2, 7.3, 7.4, 11.1, 11.2, 11.3
 */
import { computed, ref } from 'vue'
import type { GuidanceResponse } from '@/stores/guidancePanelStore'
import { useGuidancePanelStore } from '@/stores/guidancePanelStore'

const props = defineProps<{
  guidanceData: GuidanceResponse
  fieldOverrides?: Record<string, string>
}>()

const guidanceStore = useGuidancePanelStore()

// ─── Complexity ─────────────────────────────────────────────────────────────

const complexity = computed(() => props.guidanceData.complexity || 'high')

// ─── Source badge ───────────────────────────────────────────────────────────

const sourceLabel = computed(() => {
  const map: Record<string, string> = {
    template_sheet: '模板提取',
    template_header: '模板提取',
    static_json: '知识库',
    typed_fallback: '类型提示',
    fallback: '通用提示',
  }
  return map[props.guidanceData.source] || '通用提示'
})

const sourceTagType = computed(() => {
  const map: Record<string, string> = {
    template_sheet: 'success',
    template_header: 'success',
    static_json: 'warning',
    typed_fallback: 'warning',
    fallback: 'info',
  }
  return map[props.guidanceData.source] || 'info'
})

const isFallback = computed(() => props.guidanceData.source === 'fallback')

// ─── TOC ────────────────────────────────────────────────────────────────────

const showToc = computed(() =>
  complexity.value === 'high' && props.guidanceData.guidance.sections.length > 3,
)

function scrollToSection(idx: number) {
  const el = document.getElementById(`gt-guidance-section-${idx}`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ─── Collapse ───────────────────────────────────────────────────────────────

// High: all sections expanded by default
const activeSections = ref<number[]>(
  props.guidanceData.guidance.sections.map((_, i) => i),
)

// Medium: all sections collapsed by default
const mediumActiveSections = ref<number[]>([])

// Medium: show only first 3 items per section
const mediumMaxItems = 3

// ─── Low complexity: short text hint ────────────────────────────────────────

const shortText = computed(() => {
  const raw = props.guidanceData.guidance.raw_text || ''
  if (raw.length <= 100) return raw
  return raw.slice(0, 100) + '…'
})

// ─── wp_code detection ──────────────────────────────────────────────────────

const WP_CODE_REGEX = /\b([A-Z]\d{1,2}(?:-\d{1,2})?(?:-[A-Z])?)\b/g

function renderTextWithWpCodes(text: string): string {
  return text.replace(WP_CODE_REGEX, '<span class="gt-guidance-wp-chip">$1</span>')
}

// ─── Recommended questions ──────────────────────────────────────────────────

const hasQuestions = computed(() =>
  props.guidanceData.recommended_questions?.length > 0,
)

// ─── Custom guidance (P4 预留) ──────────────────────────────────────────────

const customGuidance = computed(() => {
  if (props.fieldOverrides && props.fieldOverrides['wp_guidance_custom']) {
    return props.fieldOverrides['wp_guidance_custom']
  }
  return ''
})
</script>

<template>
  <div class="gt-guidance-tab" :class="{ 'gt-guidance-tab--fallback': isFallback }">
    <!-- Source badge -->
    <div class="gt-guidance-tab__source">
      <el-tag :type="(sourceTagType as any)" size="small" effect="light">
        {{ sourceLabel }}
      </el-tag>
      <span v-if="guidanceData.complexity" class="gt-guidance-tab__complexity">
        {{ { high: '高复杂度', medium: '中复杂度', low: '低复杂度' }[guidanceData.complexity] }}
      </span>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════════════
         HIGH complexity: 完整编制说明 + 推荐问题 + RAG 引用
    ═══════════════════════════════════════════════════════════════════════ -->
    <template v-if="complexity === 'high'">
      <!-- Fallback notice -->
      <div v-if="isFallback" class="gt-guidance-tab__fallback-notice">
        暂无专属编制说明，以下为通用提示
      </div>

      <!-- Table of Contents -->
      <div v-if="showToc" class="gt-guidance-tab__toc">
        <div class="gt-guidance-tab__toc-title">目录</div>
        <div
          v-for="(section, idx) in guidanceData.guidance.sections"
          :key="'toc-' + idx"
          class="gt-guidance-tab__toc-item"
          @click="scrollToSection(idx)"
        >
          {{ section.title }}
        </div>
      </div>

      <!-- Sections -->
      <el-collapse
        v-if="guidanceData.guidance.sections.length"
        v-model="activeSections"
        class="gt-guidance-tab__collapse"
      >
        <el-collapse-item
          v-for="(section, idx) in guidanceData.guidance.sections"
          :key="idx"
          :name="idx"
          :title="section.title"
        >
          <div :id="`gt-guidance-section-${idx}`" class="gt-guidance-section">
            <!-- 多条列表项 -->
            <ol v-if="section.items.length > 1" class="gt-guidance-section__list">
              <li
                v-for="(item, itemIdx) in section.items"
                :key="itemIdx"
                class="gt-guidance-section__item"
                v-html="renderTextWithWpCodes(item)"
              />
            </ol>
            <!-- 单条内容直接段落显示（不用列表） -->
            <p
              v-else-if="section.items.length === 1"
              class="gt-guidance-section__paragraph"
              v-html="renderTextWithWpCodes(section.items[0])"
            />
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- Raw text fallback (no sections) -->
      <div
        v-else-if="guidanceData.guidance.raw_text"
        class="gt-guidance-tab__raw"
        v-html="renderTextWithWpCodes(guidanceData.guidance.raw_text)"
      />

      <!-- Recommended questions -->
      <div v-if="hasQuestions" class="gt-guidance-tab__questions">
        <div class="gt-guidance-tab__questions-title">推荐问题</div>
        <div class="gt-guidance-tab__questions-list">
          <el-button
            v-for="(q, idx) in guidanceData.recommended_questions"
            :key="idx"
            size="small"
            round
            class="gt-guidance-tab__question-btn"
          >
            {{ q }}
          </el-button>
        </div>
      </div>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════
         MEDIUM complexity: 编制说明摘要 + 推荐问题
    ═══════════════════════════════════════════════════════════════════════ -->
    <template v-else-if="complexity === 'medium'">
      <!-- Sections collapsed by default, first 3 items per section -->
      <el-collapse
        v-if="guidanceData.guidance.sections.length"
        v-model="mediumActiveSections"
        class="gt-guidance-tab__collapse gt-guidance-tab__collapse--medium"
      >
        <el-collapse-item
          v-for="(section, idx) in guidanceData.guidance.sections"
          :key="idx"
          :name="idx"
          :title="section.title"
        >
          <div class="gt-guidance-section">
            <ol v-if="section.items.length" class="gt-guidance-section__list">
              <li
                v-for="(item, itemIdx) in section.items.slice(0, mediumMaxItems)"
                :key="itemIdx"
                class="gt-guidance-section__item"
                v-html="renderTextWithWpCodes(item)"
              />
              <li
                v-if="section.items.length > mediumMaxItems"
                class="gt-guidance-section__item gt-guidance-section__item--more"
              >
                还有 {{ section.items.length - mediumMaxItems }} 条…
              </li>
            </ol>
          </div>
        </el-collapse-item>
      </el-collapse>

      <!-- Raw text fallback (first 2 lines) -->
      <div
        v-else-if="guidanceData.guidance.raw_text"
        class="gt-guidance-tab__raw gt-guidance-tab__raw--medium"
      >
        {{ guidanceData.guidance.raw_text.split('\n').slice(0, 2).join('\n') }}
      </div>

      <!-- Recommended questions -->
      <div v-if="hasQuestions" class="gt-guidance-tab__questions">
        <div class="gt-guidance-tab__questions-title">推荐问题</div>
        <div class="gt-guidance-tab__questions-list">
          <el-button
            v-for="(q, idx) in guidanceData.recommended_questions"
            :key="idx"
            size="small"
            round
            class="gt-guidance-tab__question-btn"
          >
            {{ q }}
          </el-button>
        </div>
      </div>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════
         LOW complexity: 简短提示 + 仅 AI 对话入口
    ═══════════════════════════════════════════════════════════════════════ -->
    <template v-else>
      <div class="gt-guidance-tab--low">
        <p class="gt-guidance-tab__low-hint">{{ shortText }}</p>
        <p v-if="guidanceStore.aiEnabled" class="gt-guidance-tab__low-cta">有疑问？切换到 AI 对话 Tab 提问</p>
      </div>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════════════
         补充说明区域（P4 实现保存逻辑）
    ═══════════════════════════════════════════════════════════════════════ -->
    <div class="gt-guidance-tab__custom">
      <el-collapse class="gt-guidance-tab__custom-collapse">
        <el-collapse-item title="补充说明" name="custom">
          <el-input
            type="textarea"
            :rows="3"
            :model-value="customGuidance"
            placeholder="可在此添加项目级补充说明（P4 上线后可保存）"
            disabled
          />
          <p class="gt-guidance-tab__custom-hint">保存功能即将上线</p>
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
  opacity: 0.75;
}

.gt-guidance-tab__source {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.gt-guidance-tab__complexity {
  font-size: 11px;
  color: #999;
}

.gt-guidance-tab__fallback-notice {
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 4px;
  font-size: 12px;
  color: #e6a23c;
}

/* TOC */
.gt-guidance-tab__toc {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: var(--gt-bg-light, #f4f0fa);
  border-radius: 6px;
  border: 1px solid var(--gt-border-light, #d8b8ee);
}

.gt-guidance-tab__toc-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--gt-primary, #4b2d77);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.gt-guidance-tab__toc-item {
  font-size: 12px;
  color: var(--gt-primary, #4b2d77);
  cursor: pointer;
  padding: 2px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-guidance-tab__toc-item:hover {
  text-decoration: underline;
}

/* Collapse sections */
.gt-guidance-tab__collapse {
  border: none;
}

.gt-guidance-tab__collapse :deep(.el-collapse-item__header) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: var(--gt-primary, #4b2d77);
  border-bottom: none;
  height: 32px;
  line-height: 32px;
  padding-left: 0;
}

.gt-guidance-tab__collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
  padding-bottom: 4px;
}

.gt-guidance-tab__collapse :deep(.el-collapse-item__content) {
  padding-bottom: 8px;
}

.gt-guidance-section__list {
  margin: 0;
  padding-left: 18px;
}

.gt-guidance-section__item {
  margin-bottom: 8px;
  color: #333;
  line-height: 1.7;
  word-break: break-word;
}

.gt-guidance-section__paragraph {
  margin: 0;
  color: #333;
  line-height: 1.8;
  word-break: break-word;
  font-size: var(--wp-font-size, 13px);
}

.gt-guidance-section__item--more {
  color: #999;
  font-style: italic;
  list-style: none;
  margin-left: -20px;
}

/* Raw text */
.gt-guidance-tab__raw {
  white-space: pre-wrap;
  word-break: break-word;
  color: #333;
  line-height: 1.8;
  font-size: var(--wp-font-size, 13px);
  padding: 8px 0;
}

.gt-guidance-tab__raw--medium {
  color: #666;
  font-size: 12px;
  line-height: 1.7;
}

/* wp_code chip styling */
.gt-guidance-tab :deep(.gt-guidance-wp-chip) {
  display: inline-block;
  padding: 0 6px;
  margin: 0 2px;
  background: var(--gt-bg-light, #f4f0fa);
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--gt-primary, #4b2d77);
  cursor: pointer;
}
.gt-guidance-tab :deep(.gt-guidance-wp-chip:hover) {
  background: var(--gt-border-light, #d8b8ee);
}

/* Recommended questions */
.gt-guidance-tab__questions {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}

.gt-guidance-tab__questions-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  margin-bottom: 10px;
}

.gt-guidance-tab__questions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-guidance-tab__question-btn {
  font-size: 12px;
  color: var(--gt-primary, #4b2d77) !important;
  border-color: var(--gt-border-light, #d8b8ee) !important;
  background: var(--gt-bg-light, #f4f0fa) !important;
}
.gt-guidance-tab__question-btn:hover {
  background: var(--gt-border-light, #d8b8ee) !important;
}

/* Low complexity */
.gt-guidance-tab--low {
  padding: 12px 0;
}

.gt-guidance-tab__low-hint {
  color: #333;
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 12px;
  line-height: 1.6;
}

.gt-guidance-tab__low-cta {
  color: var(--gt-primary, #4b2d77);
  font-size: 12px;
  font-weight: 500;
  padding: 8px 12px;
  background: var(--gt-bg-light, #f4f0fa);
  border-radius: 6px;
  border: 1px dashed var(--gt-border-light, #d8b8ee);
}

/* Custom guidance area (P4 预留) */
.gt-guidance-tab__custom {
  margin-top: 20px;
  border-top: 1px solid #eee;
  padding-top: 12px;
}

.gt-guidance-tab__custom-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  height: 32px;
  line-height: 32px;
}

.gt-guidance-tab__custom-hint {
  font-size: 11px;
  color: #999;
  margin-top: 6px;
  margin-bottom: 0;
}
</style>
