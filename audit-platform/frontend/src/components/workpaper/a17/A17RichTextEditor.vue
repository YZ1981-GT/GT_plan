<script setup lang="ts">
/**
 * A17RichTextEditor — A17-1 章节富文本编辑器
 *
 * 基于 contenteditable div + 轻量 toolbar（h3/h4、列表、加粗、斜体、表格插入）。
 * paste handler 调用 useSanitize 即时清洗粘贴内容。
 * 遵循 isInternalChange guard 防止 focus/blur 竞争（踩坑铁律）。
 * 纯文本兼容：检测内容无 HTML 标签时自动将 \n 转为 <br>。
 *
 * Requirements: 1.1, 1.2, 1.4, 1.5
 */
import { ref, watch, onMounted, computed } from 'vue'
import { sanitizeHtml } from '@/composables/useSanitize'
import { plainTextToHtml } from './plainTextCompat'

// ─── Props / Emits ───
const props = defineProps<{
  modelValue: string
  placeholder?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

// ─── Refs ───
const editorRef = ref<HTMLDivElement | null>(null)

// ─── isInternalChange guard（踩坑铁律：防止 focus/blur 竞争） ───
// 标记内容来自用户输入（onInput emit 出去的值），避免父组件回写触发 watch
// 重设 innerHTML 导致光标丢失 / 无法连续编辑
const isInternalChange = ref(false)

// ─── Word Count ───
const wordCount = computed(() => {
  const text = editorRef.value?.innerText || ''
  if (!text.trim()) return 0
  const chinese = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const english = (text.replace(/[\u4e00-\u9fff]/g, '').trim().match(/\S+/g) || []).length
  return chinese + english
})

// ─── Initialize ───
onMounted(() => {
  if (editorRef.value && props.modelValue) {
    editorRef.value.innerHTML = plainTextToHtml(props.modelValue)
  }
})

// ─── Watch external changes ───
watch(() => props.modelValue, (newVal) => {
  if (!editorRef.value) return
  // isInternalChange guard：跳过由本组件 onInput 触发的回写
  if (isInternalChange.value) {
    isInternalChange.value = false
    return
  }
  // 编辑器正聚焦时不打断用户输入
  if (document.activeElement === editorRef.value || editorRef.value.contains(document.activeElement)) {
    return
  }
  const html = plainTextToHtml(newVal || '')
  if (editorRef.value.innerHTML !== html) {
    editorRef.value.innerHTML = html
  }
})

// ─── Emit on input ───
function onInput() {
  if (!editorRef.value) return
  isInternalChange.value = true
  emit('update:modelValue', editorRef.value.innerHTML)
}

// ─── Paste handler：调用 useSanitize 清洗粘贴内容 ───
function onPaste(e: ClipboardEvent) {
  const clipboardData = e.clipboardData
  if (!clipboardData) return

  const html = clipboardData.getData('text/html')
  if (html) {
    e.preventDefault()
    const cleaned = sanitizeHtml(html)
    document.execCommand('insertHTML', false, cleaned)
    onInput()
  }
}

// ─── 格式化命令 ───
function exec(command: string, value?: string) {
  editorRef.value?.focus()
  document.execCommand(command, false, value || '')
  onInput()
}

function onHeading(tag: string) {
  if (tag === 'p') {
    exec('formatBlock', '<p>')
  } else {
    exec('formatBlock', `<${tag}>`)
  }
}

function insertTable() {
  editorRef.value?.focus()
  const tableHtml = `<table><tbody>
    <tr><th>标题1</th><th>标题2</th><th>标题3</th></tr>
    <tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
    <tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>
  </tbody></table><p>&nbsp;</p>`
  document.execCommand('insertHTML', false, tableHtml)
  onInput()
}

// ─── Keyboard shortcuts ───
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

// ─── Expose for parent ───
defineExpose({ editorRef })
</script>

<template>
  <div class="a17-rte" :class="{ 'is-readonly': readonly }">
    <!-- Toolbar -->
    <div v-if="!readonly" class="a17-rte__toolbar">
      <!-- Heading -->
      <el-dropdown size="small" trigger="click" @command="onHeading">
        <el-button size="small" class="a17-rte__btn">标题 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="h3">三级标题</el-dropdown-item>
            <el-dropdown-item command="h4">四级标题</el-dropdown-item>
            <el-dropdown-item command="p">正文</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <span class="a17-rte__divider" />

      <!-- Bold / Italic -->
      <el-button size="small" class="a17-rte__btn" title="加粗 (Ctrl+B)" @click="exec('bold')">
        <strong>B</strong>
      </el-button>
      <el-button size="small" class="a17-rte__btn" title="斜体 (Ctrl+I)" @click="exec('italic')">
        <em>I</em>
      </el-button>

      <span class="a17-rte__divider" />

      <!-- Lists -->
      <el-button size="small" class="a17-rte__btn" title="有序列表" @click="exec('insertOrderedList')">OL</el-button>
      <el-button size="small" class="a17-rte__btn" title="无序列表" @click="exec('insertUnorderedList')">UL</el-button>

      <span class="a17-rte__divider" />

      <!-- Table -->
      <el-button size="small" class="a17-rte__btn" title="插入表格" @click="insertTable">表格</el-button>
    </div>

    <!-- Editor area -->
    <div class="a17-rte__editor-wrap">
      <div
        ref="editorRef"
        class="a17-rte__editor"
        :contenteditable="!readonly"
        :data-placeholder="placeholder || '请输入本章节内容...'"
        @input="onInput"
        @paste="onPaste"
        @keydown="onKeydown"
      />
    </div>

    <!-- Footer -->
    <div v-if="!readonly" class="a17-rte__footer">
      <span class="a17-rte__wordcount">字数：{{ wordCount }}</span>
    </div>
  </div>
</template>

<style scoped>
.a17-rte {
  border: 1px solid var(--gt-color-border-lighter, #e4e7ed);
  border-radius: 6px;
  background: var(--gt-color-bg-white, #fff);
  overflow: hidden;
}
.a17-rte.is-readonly {
  border-color: transparent;
}
.a17-rte__toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--gt-color-border-lighter, #e4e7ed);
  background: var(--gt-color-bg, #f5f7fa);
  flex-wrap: wrap;
}
.a17-rte__btn {
  min-width: 32px;
  padding: 4px 8px !important;
  font-size: 12px !important;
}
.a17-rte__divider {
  display: inline-block;
  width: 1px;
  height: 18px;
  background: var(--gt-color-border, #dcdfe6);
  margin: 0 4px;
}
.a17-rte__editor-wrap {
  min-height: 200px;
  max-height: 500px;
  overflow-y: auto;
}
.a17-rte__editor {
  min-height: 200px;
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.8;
  outline: none;
  color: var(--gt-color-text-primary, #303133);
}
.a17-rte__editor:empty::before {
  content: attr(data-placeholder);
  color: var(--gt-color-text-placeholder, #a8abb2);
  pointer-events: none;
}
/* Table styling inside editor */
.a17-rte__editor :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}
.a17-rte__editor :deep(th),
.a17-rte__editor :deep(td) {
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  padding: 4px 8px;
  min-width: 60px;
}
.a17-rte__editor :deep(th) {
  background: var(--gt-color-bg, #f5f7fa);
  font-weight: bold;
  text-align: center;
}
/* Heading styles */
.a17-rte__editor :deep(h3) {
  font-size: 16px;
  font-weight: bold;
  margin: 12px 0 8px;
}
.a17-rte__editor :deep(h4) {
  font-size: 14px;
  font-weight: bold;
  margin: 8px 0 4px;
}
/* List */
.a17-rte__editor :deep(ul),
.a17-rte__editor :deep(ol) {
  padding-left: 24px;
  margin: 4px 0;
}
/* Footer */
.a17-rte__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 4px 12px;
  border-top: 1px solid var(--gt-color-border-lighter, #e4e7ed);
  background: var(--gt-color-bg, #f5f7fa);
}
.a17-rte__wordcount {
  font-size: 12px;
  color: var(--gt-color-info, #909399);
}
</style>
