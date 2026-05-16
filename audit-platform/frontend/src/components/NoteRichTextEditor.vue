<template>
  <div class="gt-note-rte">
    <!-- Toolbar -->
    <div class="gt-note-rte-toolbar">
      <!-- Heading -->
      <el-dropdown size="small" trigger="click" @command="onHeading">
        <el-button size="small" class="gt-note-rte-btn">标题 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="h1">一级标题</el-dropdown-item>
            <el-dropdown-item command="h2">二级标题</el-dropdown-item>
            <el-dropdown-item command="h3">三级标题</el-dropdown-item>
            <el-dropdown-item command="p">正文</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <span class="gt-note-rte-divider" />

      <!-- Bold / Italic -->
      <el-button size="small" class="gt-note-rte-btn" title="加粗 (Ctrl+B)" @click="exec('bold')">
        <strong>B</strong>
      </el-button>
      <el-button size="small" class="gt-note-rte-btn" title="斜体 (Ctrl+I)" @click="exec('italic')">
        <em>I</em>
      </el-button>

      <span class="gt-note-rte-divider" />

      <!-- Lists -->
      <el-button size="small" class="gt-note-rte-btn" title="有序列表" @click="exec('insertOrderedList')">OL</el-button>
      <el-button size="small" class="gt-note-rte-btn" title="无序列表" @click="exec('insertUnorderedList')">UL</el-button>

      <span class="gt-note-rte-divider" />

      <!-- Indent -->
      <el-button size="small" class="gt-note-rte-btn" title="增加缩进" @click="exec('indent')">→</el-button>
      <el-button size="small" class="gt-note-rte-btn" title="减少缩进" @click="exec('outdent')">←</el-button>

      <span class="gt-note-rte-divider" />

      <!-- Table insert -->
      <el-button size="small" class="gt-note-rte-btn" title="插入表格" @click="insertTable()">表格</el-button>

      <!-- Color picker -->
      <el-color-picker
        v-model="fontColor"
        size="small"
        :predefine="predefineColors"
        @change="onColorChange"
      />

      <span class="gt-note-rte-divider" />

      <!-- Placeholder insertion -->
      <el-dropdown size="small" trigger="click" @command="insertPlaceholder">
        <el-button size="small" class="gt-note-rte-btn" type="primary" plain>
          插入占位符 ▾
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="{公司名称}">{公司名称}</el-dropdown-item>
            <el-dropdown-item command="{年度}">{年度}</el-dropdown-item>
            <el-dropdown-item command="{币种}">{币种}</el-dropdown-item>
            <el-dropdown-item command="{报表期间}">{报表期间}</el-dropdown-item>
            <el-dropdown-item command="{金额单位}">{金额单位}</el-dropdown-item>
            <el-dropdown-item command="{审计报告日}">{审计报告日}</el-dropdown-item>
            <el-dropdown-item command="{注册地址}">{注册地址}</el-dropdown-item>
            <el-dropdown-item command="{法定代表人}">{法定代表人}</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <span class="gt-note-rte-divider" />

      <!-- Source code toggle -->
      <el-button
        size="small"
        class="gt-note-rte-btn"
        :type="sourceMode ? 'warning' : ''"
        title="查看源码"
        @click="toggleSourceMode"
      >
        &lt;/&gt;
      </el-button>
    </div>

    <!-- Editor area -->
    <div v-show="!sourceMode" class="gt-note-rte-editor-wrap">
      <div
        ref="editorRef"
        class="gt-note-rte-editor"
        contenteditable="true"
        @input="onInput"
        @paste="onPaste"
        @keydown="onKeydown"
      />
    </div>

    <!-- Source code mode -->
    <div v-show="sourceMode" class="gt-note-rte-source-wrap">
      <textarea
        ref="sourceRef"
        v-model="sourceCode"
        class="gt-note-rte-source"
        spellcheck="false"
        @input="onSourceInput"
      />
    </div>

    <!-- Footer: word count -->
    <div class="gt-note-rte-footer">
      <span class="gt-note-rte-wordcount">字数：{{ wordCount }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, nextTick, computed } from 'vue'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const editorRef = ref<HTMLDivElement | null>(null)
const sourceRef = ref<HTMLTextAreaElement | null>(null)
const sourceMode = ref(false)
const sourceCode = ref('')
const fontColor = ref('#000000')

const predefineColors = [
  '#000000', '#333333', '#666666',
  '#ff0000', '#e6a23c', '#409eff',
  '#67c23a', '#909399', '#4b2d77',
]

// Word count (Chinese characters + words)
const wordCount = computed(() => {
  const text = getPlainText()
  if (!text) return 0
  // Count Chinese characters individually, English words by spaces
  const chinese = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const english = (text.replace(/[\u4e00-\u9fff]/g, '').trim().match(/\S+/g) || []).length
  return chinese + english
})

function getPlainText(): string {
  if (!editorRef.value) return ''
  return editorRef.value.innerText || ''
}

// Initialize content
onMounted(() => {
  if (editorRef.value) {
    editorRef.value.innerHTML = props.modelValue || ''
  }
})

// Watch external changes
watch(() => props.modelValue, (newVal) => {
  if (!editorRef.value) return
  // Only update if content actually differs (avoid cursor jump)
  if (editorRef.value.innerHTML !== newVal) {
    editorRef.value.innerHTML = newVal || ''
  }
})

// Emit on input
function onInput() {
  if (!editorRef.value) return
  emit('update:modelValue', editorRef.value.innerHTML)
}

// Execute formatting command
function exec(command: string, value?: string) {
  editorRef.value?.focus()
  document.execCommand(command, false, value || '')
  onInput()
}

// Heading
function onHeading(tag: string) {
  if (tag === 'p') {
    exec('formatBlock', '<p>')
  } else {
    exec('formatBlock', `<${tag}>`)
  }
}

// Color change
function onColorChange(color: string | null) {
  if (color) {
    exec('foreColor', color)
  }
}

// Insert table
function insertTable() {
  editorRef.value?.focus()
  const html = `<table style="border-collapse:collapse;width:100%;margin:8px 0;">
    <tr><th style="border:1px solid #ddd;padding:4px 8px;background: var(--gt-color-bg);">列1</th><th style="border:1px solid #ddd;padding:4px 8px;background: var(--gt-color-bg);">列2</th><th style="border:1px solid #ddd;padding:4px 8px;background: var(--gt-color-bg);">列3</th></tr>
    <tr><td style="border:1px solid #ddd;padding:4px 8px;">&nbsp;</td><td style="border:1px solid #ddd;padding:4px 8px;">&nbsp;</td><td style="border:1px solid #ddd;padding:4px 8px;">&nbsp;</td></tr>
    <tr><td style="border:1px solid #ddd;padding:4px 8px;">&nbsp;</td><td style="border:1px solid #ddd;padding:4px 8px;">&nbsp;</td><td style="border:1px solid #ddd;padding:4px 8px;">&nbsp;</td></tr>
  </table>`
  document.execCommand('insertHTML', false, html)
  onInput()
}

// Insert placeholder as blue tag
function insertPlaceholder(placeholder: string) {
  editorRef.value?.focus()
  const html = `<span class="gt-note-placeholder" contenteditable="false" data-placeholder="${placeholder}">${placeholder}</span>&nbsp;`
  document.execCommand('insertHTML', false, html)
  onInput()
}

// Toggle source code mode
function toggleSourceMode() {
  if (!sourceMode.value) {
    // Entering source mode
    sourceCode.value = editorRef.value?.innerHTML || ''
    sourceMode.value = true
    nextTick(() => sourceRef.value?.focus())
  } else {
    // Exiting source mode - apply source to editor
    if (editorRef.value) {
      editorRef.value.innerHTML = sourceCode.value
    }
    sourceMode.value = false
    onInput()
  }
}

// Source code textarea input
function onSourceInput() {
  // Will be applied when exiting source mode
}

// Handle paste from Word (strip Word-specific styles, keep basic formatting)
function onPaste(e: ClipboardEvent) {
  const clipboardData = e.clipboardData
  if (!clipboardData) return

  const html = clipboardData.getData('text/html')
  if (html) {
    e.preventDefault()
    const cleaned = cleanWordHtml(html)
    document.execCommand('insertHTML', false, cleaned)
    onInput()
  }
}

// Clean Word HTML - keep basic formatting, remove Word-specific markup
function cleanWordHtml(html: string): string {
  // Remove Word-specific XML namespaces and tags
  let cleaned = html
    .replace(/<\/?o:[^>]*>/gi, '')
    .replace(/<\/?v:[^>]*>/gi, '')
    .replace(/<\/?w:[^>]*>/gi, '')
    .replace(/<\/?m:[^>]*>/gi, '')
    // Remove XML declarations
    .replace(/<\?xml[^>]*>/gi, '')
    // Remove comments
    .replace(/<!--[\s\S]*?-->/g, '')
    // Remove style tags
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    // Remove class attributes (Word classes like MsoNormal)
    .replace(/\s*class="[^"]*"/gi, '')
    // Remove Word-specific style properties but keep basic ones
    .replace(/\s*style="[^"]*"/gi, (match) => {
      // Extract only useful styles
      const fontWeight = match.match(/font-weight:\s*(bold|700)/i)
      const fontStyle = match.match(/font-style:\s*italic/i)
      const textAlign = match.match(/text-align:\s*(left|center|right)/i)
      const parts: string[] = []
      if (fontWeight) parts.push('font-weight:bold')
      if (fontStyle) parts.push('font-style:italic')
      if (textAlign) parts.push(`text-align:${textAlign[1]}`)
      return parts.length ? ` style="${parts.join(';')}"` : ''
    })
    // Remove empty spans
    .replace(/<span\s*>([\s\S]*?)<\/span>/gi, '$1')
    // Remove lang attributes
    .replace(/\s*lang="[^"]*"/gi, '')
    // Clean up extra whitespace in tags
    .replace(/<(\w+)\s+>/g, '<$1>')

  return cleaned
}

// Keyboard shortcuts
function onKeydown(e: KeyboardEvent) {
  if (e.ctrlKey || e.metaKey) {
    switch (e.key.toLowerCase()) {
      case 'b':
        e.preventDefault()
        exec('bold')
        break
      case 'i':
        e.preventDefault()
        exec('italic')
        break
    }
  }
}
</script>

<style scoped>
.gt-note-rte {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: var(--gt-color-bg-white);
  overflow: hidden;
}

.gt-note-rte-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-bottom: 1px solid #ebeef5;
  background: var(--gt-color-bg);
  flex-wrap: wrap;
}

.gt-note-rte-btn {
  min-width: 32px;
  padding: 4px 8px !important;
  font-size: var(--gt-font-size-xs) !important;
}

.gt-note-rte-divider {
  display: inline-block;
  width: 1px;
  height: 18px;
  background: var(--gt-color-border);
  margin: 0 4px;
}

.gt-note-rte-editor-wrap {
  min-height: 200px;
  max-height: 500px;
  overflow-y: auto;
}

.gt-note-rte-editor {
  min-height: 200px;
  padding: 12px 16px;
  font-family: '仿宋', 'FangSong', serif;
  font-size: var(--gt-font-size-sm);
  line-height: 1.8;
  outline: none;
  color: var(--gt-color-text-primary);
}

.gt-note-rte-editor:empty::before {
  content: '请输入附注文字内容...';
  color: var(--gt-color-text-placeholder);
  pointer-events: none;
}

/* Placeholder tag styling */
.gt-note-rte-editor :deep(.gt-note-placeholder) {
  display: inline-block;
  background: var(--gt-bg-info);
  color: var(--gt-color-teal);
  border: 1px solid #b3d8ff;
  border-radius: 3px;
  padding: 0 6px;
  margin: 0 2px;
  font-size: var(--gt-font-size-xs);
  line-height: 20px;
  cursor: default;
  user-select: none;
  vertical-align: middle;
}

/* Table styling inside editor */
.gt-note-rte-editor :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.gt-note-rte-editor :deep(th),
.gt-note-rte-editor :deep(td) {
  border: 1px solid #ddd;
  padding: 4px 8px;
  min-width: 60px;
}

.gt-note-rte-editor :deep(th) {
  background: var(--gt-color-bg);
  font-weight: bold;
  text-align: center;
}

/* Heading styles */
.gt-note-rte-editor :deep(h1) {
  font-size: var(--gt-font-size-xl);
  font-weight: bold;
  margin: 12px 0 8px;
}

.gt-note-rte-editor :deep(h2) {
  font-size: var(--gt-font-size-md);
  font-weight: bold;
  margin: 10px 0 6px;
}

.gt-note-rte-editor :deep(h3) {
  font-size: var(--gt-font-size-sm);
  font-weight: bold;
  margin: 8px 0 4px;
}

/* Source code mode */
.gt-note-rte-source-wrap {
  min-height: 200px;
  max-height: 500px;
}

.gt-note-rte-source {
  width: 100%;
  min-height: 200px;
  max-height: 500px;
  padding: 12px 16px;
  border: none;
  outline: none;
  resize: vertical;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: var(--gt-font-size-xs);
  line-height: 1.6;
  color: var(--gt-color-text-primary);
  background: var(--gt-bg-info);
  box-sizing: border-box;
}

/* Footer */
.gt-note-rte-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 4px 12px;
  border-top: 1px solid #ebeef5;
  background: var(--gt-color-bg);
}

.gt-note-rte-wordcount {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
</style>
