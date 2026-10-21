<!--
  公式输入组件：语法高亮 + 实时校验 + 错误提示。

  spec: formula-management-ux-improvements · A 批 · Task A3

  双层结构：底层 <input> 接 v-model；覆盖层 <pre> 做语法着色。
  输入 debounce 500ms 后调 validate()，错误 inline 提示。
-->
<template>
  <div class="gt-formula-input" :class="{ 'gt-formula-input--error': hasError }">
    <!-- 语法高亮覆盖层 -->
    <pre
      ref="highlightRef"
      class="gt-formula-input__highlight"
      aria-hidden="true"
      v-html="highlightedHtml"
    />
    <!-- 实际输入框 -->
    <input
      ref="inputRef"
      class="gt-formula-input__real"
      :value="modelValue"
      :placeholder="placeholder"
      spellcheck="false"
      autocomplete="off"
      @input="onInput"
      @keydown="onKeydown"
      @scroll="syncScroll"
    />
    <!-- 错误提示 -->
    <div v-if="hasError" class="gt-formula-input__errors">
      <span v-for="(err, i) in validationErrors" :key="i" class="gt-formula-input__error-item">
        {{ err.message }}
      </span>
    </div>
    <!-- 自动补全弹出 -->
    <div
      v-if="showSuggestions && suggestions.length"
      class="gt-formula-input__suggestions"
      :style="suggestionsStyle"
    >
      <div
        v-for="(item, i) in suggestions"
        :key="item.name"
        class="gt-formula-input__suggestion-item"
        :class="{ 'is-active': i === activeSuggestionIndex }"
        @mousedown.prevent="acceptSuggestion(item)"
      >
        <span class="gt-formula-input__suggestion-name">{{ item.name }}</span>
        <span class="gt-formula-input__suggestion-desc">{{ item.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { tokenize, validate, cursorContext, knownFunctions, type ParseToken, type ValidationError } from '@/composables/formula/formulaSyntaxParser'

defineOptions({ name: 'FormulaInput' })

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
}>(), {
  placeholder: "如 TB('1001','期末余额') 或 WP('D2','审定数')",
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const inputRef = ref<HTMLInputElement>()
const highlightRef = ref<HTMLPreElement>()

// ── 语法高亮 ─────────────────────────────────────────────────────────────

const TOKEN_CLASS: Record<string, string> = {
  function: 'gt-fhi-func',
  string: 'gt-fhi-str',
  operator: 'gt-fhi-op',
  number: 'gt-fhi-num',
  paren: 'gt-fhi-paren',
  comma: 'gt-fhi-comma',
  whitespace: '',
  unknown: 'gt-fhi-err',
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const highlightedHtml = computed(() => {
  const expr = props.modelValue
  if (!expr) return '<span class="gt-fhi-placeholder">&nbsp;</span>'

  const tokens = tokenize(expr)
  let html = ''
  for (const t of tokens) {
    const cls = TOKEN_CLASS[t.type] || ''
    const escaped = escapeHtml(t.value)
    if (t.error) {
      html += `<span class="gt-fhi-err" title="${escapeHtml(t.error)}">${escaped}</span>`
    } else if (cls) {
      html += `<span class="${cls}">${escaped}</span>`
    } else {
      html += escaped
    }
  }
  // 末尾加空格保持滚动同步
  html += ' '
  return html
})

// ── 实时校验（debounce 500ms）─────────────────────────────────────────────

const validationErrors = ref<ValidationError[]>([])
const hasError = computed(() => validationErrors.value.length > 0)

let validateTimer: ReturnType<typeof setTimeout> | null = null

function scheduleValidation() {
  if (validateTimer) clearTimeout(validateTimer)
  validateTimer = setTimeout(() => {
    const result = validate(props.modelValue)
    validationErrors.value = result.errors
  }, 500)
}

watch(() => props.modelValue, () => {
  scheduleValidation()
})

// ── 自动补全 ─────────────────────────────────────────────────────────────

const showSuggestions = ref(false)
const suggestions = ref<Array<{ name: string; description: string }>>([])
const activeSuggestionIndex = ref(0)
const suggestionsStyle = ref<Record<string, string>>({})

function updateSuggestions() {
  const input = inputRef.value
  if (!input) { showSuggestions.value = false; return }

  const expr = props.modelValue
  const cursor = input.selectionStart ?? expr.length

  // 检查光标前是否刚输入了函数名的开头（大写字母）
  const beforeCursor = expr.slice(0, cursor)

  // 场景 1：刚输入了 `(` 且光标在函数参数内 → 不显示函数补全
  const ctx = cursorContext(expr, cursor)
  if (ctx) {
    showSuggestions.value = false
    return
  }

  // 场景 2：正在输入函数名（大写字母序列）
  const match = beforeCursor.match(/([A-Z_]+)$/)
  if (match && match[1].length >= 1) {
    const prefix = match[1]
    const candidates = knownFunctions().filter(f => f.name.startsWith(prefix) && f.name !== prefix)
    if (candidates.length > 0) {
      suggestions.value = candidates
      activeSuggestionIndex.value = 0
      showSuggestions.value = true
      return
    }
  }

  showSuggestions.value = false
}

function acceptSuggestion(item: { name: string }) {
  const input = inputRef.value
  if (!input) return

  const cursor = input.selectionStart ?? props.modelValue.length
  const beforeCursor = props.modelValue.slice(0, cursor)
  const match = beforeCursor.match(/([A-Z_]+)$/)
  const prefixLen = match ? match[1].length : 0
  const afterCursor = props.modelValue.slice(cursor)

  const newVal = beforeCursor.slice(0, -prefixLen) + item.name + '(' + afterCursor
  emit('update:modelValue', newVal)
  showSuggestions.value = false

  // 光标定位到括号内
  nextTick(() => {
    const pos = cursor - prefixLen + item.name.length + 1
    input.setSelectionRange(pos, pos)
    input.focus()
  })
}

// ── 输入事件 ─────────────────────────────────────────────────────────────

function onInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  emit('update:modelValue', val)
  nextTick(() => updateSuggestions())
}

function onKeydown(e: KeyboardEvent) {
  if (!showSuggestions.value || !suggestions.value.length) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeSuggestionIndex.value = Math.min(activeSuggestionIndex.value + 1, suggestions.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeSuggestionIndex.value = Math.max(activeSuggestionIndex.value - 1, 0)
  } else if (e.key === 'Enter' || e.key === 'Tab') {
    e.preventDefault()
    acceptSuggestion(suggestions.value[activeSuggestionIndex.value])
  } else if (e.key === 'Escape') {
    showSuggestions.value = false
  }
}

function syncScroll() {
  if (highlightRef.value && inputRef.value) {
    highlightRef.value.scrollLeft = inputRef.value.scrollLeft
  }
}

/** 暴露 focus 方法供父组件调用 */
function focus() {
  inputRef.value?.focus()
}

defineExpose({ focus })
</script>

<style scoped>
.gt-formula-input {
  position: relative;
  width: 100%;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.gt-formula-input__highlight,
.gt-formula-input__real {
  font: inherit;
  padding: 4px 8px;
  border: 1px solid var(--gt-color-border, #dcdfe6);
  border-radius: 4px;
  white-space: nowrap;
  overflow-x: auto;
  width: 100%;
  box-sizing: border-box;
  margin: 0;
}

.gt-formula-input__highlight {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  background: transparent;
  color: transparent;
  z-index: 1;
}

.gt-formula-input__real {
  position: relative;
  background: transparent;
  color: transparent;
  caret-color: var(--gt-color-text-primary, #303133);
  z-index: 2;
  outline: none;
}

.gt-formula-input__real:focus {
  border-color: var(--gt-color-primary, #409eff);
}

.gt-formula-input--error .gt-formula-input__real {
  border-color: var(--gt-color-danger, #f56c6c);
}

/* 语法高亮颜色 */
:deep(.gt-fhi-func) { color: #1677ff; font-weight: 600; }
:deep(.gt-fhi-str) { color: #389e0d; }
:deep(.gt-fhi-op) { color: #8c8c8c; }
:deep(.gt-fhi-num) { color: #d46b08; }
:deep(.gt-fhi-paren) { color: #595959; }
:deep(.gt-fhi-comma) { color: #8c8c8c; }
:deep(.gt-fhi-err) { color: #cf1322; text-decoration: wavy underline #cf1322; text-underline-offset: 2px; }
:deep(.gt-fhi-placeholder) { color: transparent; }

.gt-formula-input__errors {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}

.gt-formula-input__error-item {
  font-size: 11px;
  color: var(--gt-color-danger, #f56c6c);
  line-height: 1.4;
}

/* 自动补全下拉 */
.gt-formula-input__suggestions {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 100;
  background: #fff;
  border: 1px solid var(--gt-color-border, #dcdfe6);
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  max-height: 200px;
  overflow-y: auto;
  min-width: 300px;
}

.gt-formula-input__suggestion-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
}

.gt-formula-input__suggestion-item:hover,
.gt-formula-input__suggestion-item.is-active {
  background: var(--gt-bg-info, #ecf5ff);
}

.gt-formula-input__suggestion-name {
  font-weight: 600;
  color: #1677ff;
  min-width: 70px;
}

.gt-formula-input__suggestion-desc {
  color: var(--gt-color-text-tertiary, #a8abb2);
  font-size: 11px;
}
</style>
