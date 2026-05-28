<!--
  FormulaTracePopover — 公式溯源 popover

  - 300ms hover 延迟显示，200ms 关闭延迟（避免快速划过抖动）
  - 跨 sheet 公式 → 可点击链接（调 Cross_Sheet_Resolver）
  - 本 sheet 公式 → 显示公式 + 引用 cell 当前值
  - 解析失败 → 红色 "⚠ 公式解析失败" + 原始字符串

  Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5
  Feature: advanced-query-enhancements-p1p2, Property 23: Formula classification
-->
<template>
  <div
    class="gt-formula-trace-trigger"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <slot />

    <teleport to="body">
      <div
        v-if="popoverVisible"
        class="gt-formula-trace-popover"
        :style="popoverStyle"
        @mouseenter="onPopoverEnter"
        @mouseleave="onPopoverLeave"
      >
        <div class="gt-formula-trace-header">
          <span class="gt-formula-prefix">ƒ</span>
          <span class="gt-formula-raw">{{ formula }}</span>
        </div>

        <div v-if="classification === 'parse-error'" class="gt-formula-error">
          ⚠ 公式解析失败
          <div class="gt-formula-raw-fallback">{{ formula }}</div>
        </div>

        <div v-else-if="classification === 'cross-sheet'" class="gt-formula-refs">
          <div class="gt-formula-section-title">跨 Sheet 引用：</div>
          <div
            v-for="(ref, idx) in crossSheetRefs"
            :key="idx"
            class="gt-formula-ref-item gt-formula-ref-link"
            @click="$emit('crossSheetClick', ref)"
          >
            🔗 {{ ref.sheet }}!{{ ref.cell }}
          </div>
        </div>

        <div v-else-if="classification === 'local'" class="gt-formula-refs">
          <div class="gt-formula-section-title">本 Sheet 引用：</div>
          <div
            v-for="(ref, idx) in localRefs"
            :key="idx"
            class="gt-formula-ref-item"
          >
            {{ ref }}
          </div>
        </div>

        <div v-if="sourceChip" class="gt-formula-source">
          <el-tag size="small" :type="sourceChip.type" effect="plain" round>
            {{ sourceChip.label }}
          </el-tag>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

export interface FormulaTraceProps {
  formula: string
  source?: string
}

const props = defineProps<FormulaTraceProps>()
defineEmits<{
  crossSheetClick: [ref: { sheet: string; cell: string }]
}>()

const popoverVisible = ref(false)
const popoverStyle = ref<Record<string, string>>({})
let showTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

const SHOW_DELAY = 300
const HIDE_DELAY = 200

function onMouseEnter(e: MouseEvent) {
  clearHideTimer()
  showTimer = setTimeout(() => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    popoverStyle.value = {
      position: 'fixed',
      top: `${rect.bottom + 4}px`,
      left: `${rect.left}px`,
      zIndex: '9999',
    }
    popoverVisible.value = true
  }, SHOW_DELAY)
}

function onMouseLeave() {
  clearShowTimer()
  startHideTimer()
}

function onPopoverEnter() {
  clearHideTimer()
}

function onPopoverLeave() {
  startHideTimer()
}

function startHideTimer() {
  hideTimer = setTimeout(() => {
    popoverVisible.value = false
  }, HIDE_DELAY)
}

function clearShowTimer() {
  if (showTimer) {
    clearTimeout(showTimer)
    showTimer = null
  }
}

function clearHideTimer() {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

const classification = computed(() => classifyFormula(props.formula))

const crossSheetRefs = computed(() => {
  if (classification.value !== 'cross-sheet') return []
  return parseCrossSheetRefs(props.formula)
})

const localRefs = computed(() => {
  if (classification.value !== 'local') return []
  return parseLocalRefs(props.formula)
})

const sourceChip = computed(() => {
  if (!props.source) return null
  const map: Record<string, { type: 'primary' | 'success' | 'warning' | 'info'; label: string }> = {
    univer_snapshot: { type: 'success', label: '📥 实时' },
    xlsx_recomputed: { type: 'warning', label: '⚙ 重算' },
    xlsx_cache: { type: 'info', label: '📋 模板' },
  }
  return map[props.source] || null
})
</script>

<script lang="ts">
/**
 * 公式分类纯函数 — 导出供测试使用
 *
 * - cross-sheet: 包含 =...!... 模式（跨 sheet 引用）
 * - local: 有效公式但无跨 sheet 引用
 * - parse-error: 无法解析
 */
export type FormulaClassification = 'cross-sheet' | 'local' | 'parse-error'

// 跨 sheet 引用 pattern: ='Sheet Name'!A1 or =SheetName!A1
const CROSS_SHEET_PATTERN = /(?:'([^']+)'|([A-Za-z\u4e00-\u9fff][\w\u4e00-\u9fff]*))!([A-Z]{1,3}\d{1,7})/g

// 本 sheet cell 引用 pattern: A1, B2, AA100 等
const LOCAL_REF_PATTERN = /\b([A-Z]{1,3}\d{1,7})\b/g

export function classifyFormula(formula: string): FormulaClassification {
  if (!formula || typeof formula !== 'string') return 'parse-error'

  const trimmed = formula.trim()
  if (!trimmed.startsWith('=') && !trimmed.startsWith('+')) {
    // 不是公式
    return 'parse-error'
  }

  // 检查是否有跨 sheet 引用
  const crossRefs = parseCrossSheetRefs(trimmed)
  if (crossRefs.length > 0) return 'cross-sheet'

  // 检查是否有本 sheet 引用
  const localRefs = parseLocalRefs(trimmed)
  if (localRefs.length > 0) return 'local'

  // 有 = 前缀但无法解析出引用（如 =1+2 纯计算）
  // 仍视为 local（有效公式）
  if (trimmed.length > 1) return 'local'

  return 'parse-error'
}

export function parseCrossSheetRefs(formula: string): Array<{ sheet: string; cell: string }> {
  const results: Array<{ sheet: string; cell: string }> = []
  const regex = new RegExp(CROSS_SHEET_PATTERN.source, 'g')
  let match: RegExpExecArray | null
  while ((match = regex.exec(formula)) !== null) {
    const sheet = match[1] || match[2]
    const cell = match[3]
    if (sheet && cell) {
      results.push({ sheet, cell })
    }
  }
  return results
}

export function parseLocalRefs(formula: string): string[] {
  // 先移除跨 sheet 引用部分，再提取本 sheet 引用
  const withoutCrossSheet = formula.replace(
    new RegExp(CROSS_SHEET_PATTERN.source, 'g'),
    ''
  )
  const results: string[] = []
  let match: RegExpExecArray | null
  const regex = new RegExp(LOCAL_REF_PATTERN.source, 'g')
  while ((match = regex.exec(withoutCrossSheet)) !== null) {
    results.push(match[1])
  }
  // 去重
  return [...new Set(results)]
}
</script>

<style scoped>
.gt-formula-trace-trigger {
  display: inline;
  cursor: help;
}
.gt-formula-trace-popover {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 12px 16px;
  min-width: 240px;
  max-width: 400px;
  font-size: 13px;
}
.gt-formula-trace-header {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}
.gt-formula-prefix {
  color: #e6a23c;
  font-weight: bold;
  font-style: italic;
  margin-right: 6px;
}
.gt-formula-raw {
  font-family: 'Consolas', 'Monaco', monospace;
  font-style: italic;
  color: #e6a23c;
  word-break: break-all;
}
.gt-formula-error {
  color: #f56c6c;
  font-weight: 500;
}
.gt-formula-raw-fallback {
  margin-top: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}
.gt-formula-section-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.gt-formula-ref-item {
  padding: 2px 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
}
.gt-formula-ref-link {
  color: var(--gt-color-primary, #7c3aed);
  cursor: pointer;
  text-decoration: underline;
}
.gt-formula-ref-link:hover {
  opacity: 0.8;
}
.gt-formula-refs {
  margin-bottom: 8px;
}
.gt-formula-source {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}
</style>
