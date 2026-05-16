<template>
  <div class="note-rich-text-editor">
    <!-- Toolbar -->
    <div class="nrte-toolbar">
      <div class="nrte-toolbar-group">
        <el-select v-model="currentHeading" size="small" style="width: 100px" @change="applyHeading">
          <el-option label="正文" value="p" />
          <el-option label="标题1" value="h1" />
          <el-option label="标题2" value="h2" />
          <el-option label="标题3" value="h3" />
        </el-select>
      </div>

      <div class="nrte-toolbar-group">
        <el-button size="small" :class="{ active: isBold }" @click="execCommand('bold')">
          <strong>B</strong>
        </el-button>
        <el-button size="small" :class="{ active: isItalic }" @click="execCommand('italic')">
          <em>I</em>
        </el-button>
      </div>

      <div class="nrte-toolbar-group">
        <el-button size="small" @click="execCommand('insertOrderedList')">1.</el-button>
        <el-button size="small" @click="execCommand('insertUnorderedList')">•</el-button>
      </div>

      <div class="nrte-toolbar-group">
        <el-button size="small" @click="execCommand('indent')">→</el-button>
        <el-button size="small" @click="execCommand('outdent')">←</el-button>
      </div>

      <div class="nrte-toolbar-group">
        <el-color-picker v-model="fontColor" size="small" @change="applyFontColor" />
        <el-button size="small" @click="insertTable">表格</el-button>
      </div>

      <div class="nrte-toolbar-group">
        <el-dropdown trigger="click" @command="insertPlaceholder">
          <el-button size="small">📌 占位符</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="{公司名称}">公司名称</el-dropdown-item>
              <el-dropdown-item command="{年度}">年度</el-dropdown-item>
              <el-dropdown-item command="{币种}">币种</el-dropdown-item>
              <el-dropdown-item command="{金额单位}">金额单位</el-dropdown-item>
              <el-dropdown-item command="{报告日期}">报告日期</el-dropdown-item>
              <el-dropdown-item command="{审计期间}">审计期间</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <div class="nrte-toolbar-group nrte-toolbar-right">
        <el-button size="small" :type="viewSource ? 'primary' : ''" @click="toggleSource">
          &lt;/&gt;
        </el-button>
        <span class="nrte-word-count">{{ wordCount }} 字</span>
      </div>
    </div>

    <!-- Editor Area -->
    <div v-show="!viewSource" class="nrte-content-wrapper">
      <div
        ref="editorRef"
        class="nrte-content"
        contenteditable="true"
        @input="onInput"
        @paste="onPaste"
        @keydown="onKeydown"
        @mouseup="updateToolbarState"
      />
    </div>

    <!-- Source View -->
    <div v-show="viewSource" class="nrte-source-wrapper">
      <textarea
        v-model="htmlSource"
        class="nrte-source"
        @input="onSourceInput"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [value: string]
}>()

const editorRef = ref<HTMLDivElement>()
const viewSource = ref(false)
const htmlSource = ref('')
const currentHeading = ref('p')
const fontColor = ref('#000000')
const isBold = ref(false)
const isItalic = ref(false)

// Word count
const wordCount = computed(() => {
  const text = editorRef.value?.innerText || ''
  return text.replace(/\s/g, '').length
})

// Initialize content
onMounted(() => {
  if (editorRef.value && props.modelValue) {
    editorRef.value.innerHTML = props.modelValue
  }
})

// Watch for external changes
watch(() => props.modelValue, (newVal) => {
  if (editorRef.value && editorRef.value.innerHTML !== newVal) {
    editorRef.value.innerHTML = newVal || ''
  }
})

function onInput() {
  if (!editorRef.value) return
  const html = editorRef.value.innerHTML
  emit('update:modelValue', html)
  emit('change', html)
}

function onPaste(e: ClipboardEvent) {
  // Support paste from Word - preserve basic formatting
  const clipboardData = e.clipboardData
  if (!clipboardData) return

  const htmlData = clipboardData.getData('text/html')
  if (htmlData) {
    e.preventDefault()
    // Clean up Word HTML - keep basic tags
    const cleaned = cleanWordHtml(htmlData)
    document.execCommand('insertHTML', false, cleaned)
  }
}

function cleanWordHtml(html: string): string {
  // Remove Word-specific markup but keep basic formatting
  let cleaned = html
  // Remove XML declarations and comments
  cleaned = cleaned.replace(/<\?xml[^>]*>/gi, '')
  cleaned = cleaned.replace(/<!--[\s\S]*?-->/g, '')
  // Remove Word-specific tags
  cleaned = cleaned.replace(/<o:p[^>]*>[\s\S]*?<\/o:p>/gi, '')
  cleaned = cleaned.replace(/<w:[^>]*>[\s\S]*?<\/w:[^>]*>/gi, '')
  // Remove class/style attributes (keep basic structure)
  cleaned = cleaned.replace(/\s+class="[^"]*"/gi, '')
  cleaned = cleaned.replace(/\s+style="[^"]*"/gi, '')
  // Remove empty spans
  cleaned = cleaned.replace(/<span[^>]*>\s*<\/span>/gi, '')
  // Keep: p, br, strong, em, b, i, ul, ol, li, table, tr, td, th, h1-h6
  return cleaned
}

function onKeydown(e: KeyboardEvent) {
  // Tab for indent
  if (e.key === 'Tab') {
    e.preventDefault()
    if (e.shiftKey) {
      execCommand('outdent')
    } else {
      execCommand('indent')
    }
  }
}

function execCommand(command: string, value?: string) {
  document.execCommand(command, false, value)
  editorRef.value?.focus()
  updateToolbarState()
  onInput()
}

function applyHeading(tag: string) {
  if (tag === 'p') {
    execCommand('formatBlock', '<p>')
  } else {
    execCommand('formatBlock', `<${tag}>`)
  }
}

function applyFontColor(color: string) {
  if (color) {
    execCommand('foreColor', color)
  }
}

function insertPlaceholder(placeholder: string) {
  // Insert as a styled span (blue tag style)
  const html = `<span class="nrte-placeholder" contenteditable="false">${placeholder}</span>&nbsp;`
  execCommand('insertHTML', html)
}

function insertTable() {
  const html = `
    <table class="nrte-table" border="1" cellpadding="4" cellspacing="0">
      <tr><th>列1</th><th>列2</th><th>列3</th></tr>
      <tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
      <tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
    </table><p></p>
  `
  execCommand('insertHTML', html)
}

function toggleSource() {
  if (!viewSource.value) {
    // Switch to source view
    htmlSource.value = editorRef.value?.innerHTML || ''
  } else {
    // Switch back to WYSIWYG
    if (editorRef.value) {
      editorRef.value.innerHTML = htmlSource.value
      onInput()
    }
  }
  viewSource.value = !viewSource.value
}

function onSourceInput() {
  emit('update:modelValue', htmlSource.value)
}

function updateToolbarState() {
  isBold.value = document.queryCommandState('bold')
  isItalic.value = document.queryCommandState('italic')
}
</script>

<style scoped>
.note-rich-text-editor {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.nrte-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-bottom: 1px solid #ebeef5;
  background: #fafafa;
  flex-wrap: wrap;
}

.nrte-toolbar-group {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-right: 8px;
  border-right: 1px solid #ebeef5;
}

.nrte-toolbar-group:last-child {
  border-right: none;
}

.nrte-toolbar-right {
  margin-left: auto;
}

.nrte-toolbar .el-button.active {
  background: #e6e8eb;
}

.nrte-word-count {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}

.nrte-content-wrapper {
  min-height: 200px;
  max-height: 600px;
  overflow-y: auto;
}

.nrte-content {
  padding: 12px 16px;
  min-height: 200px;
  outline: none;
  font-family: '仿宋_GB2312', '仿宋', FangSong, serif;
  font-size: 14px;
  line-height: 1.8;
}

.nrte-content:empty::before {
  content: attr(data-placeholder);
  color: #c0c4cc;
}

.nrte-source-wrapper {
  min-height: 200px;
}

.nrte-source {
  width: 100%;
  min-height: 200px;
  padding: 12px;
  border: none;
  outline: none;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
}

/* Placeholder tag style */
:deep(.nrte-placeholder) {
  display: inline-block;
  background: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
  border-radius: 3px;
  padding: 0 6px;
  font-size: 12px;
  line-height: 20px;
  cursor: default;
  user-select: none;
}

/* Table style inside editor */
:deep(.nrte-table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
}

:deep(.nrte-table th),
:deep(.nrte-table td) {
  border: 1px solid #dcdfe6;
  padding: 6px 8px;
  text-align: left;
}

:deep(.nrte-table th) {
  background: #f5f7fa;
  font-weight: bold;
}
</style>
