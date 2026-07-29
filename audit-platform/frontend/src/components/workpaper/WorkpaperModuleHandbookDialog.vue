<script setup lang="ts">
/**
 * 底稿编制模块 · 使用手册弹窗
 * 对齐 E1/G1 PreparationHandbookDialog 范式（marked + DOMPurify 渲染 module-editing-handbook.md）。
 * 说明整个底稿编制模块流程：程序裁剪 → 生成 → 委派 → 编制 → 复核 → 归档 + 看板等视图。
 *
 * Props:
 *   initialSection - 打开时自动滚动到对应章节锚点（tailor/generate/assign/compose/review/archive）
 *
 * Emits:
 *   navigate - 用户点「前往操作」时抛出目标（tailor/matrix/workbench/lifecycle）
 */
import { computed, ref, watch, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import handbookMd from './handbooks/module-editing-handbook.md?raw'

const props = withDefaults(defineProps<{
  modelValue: boolean
  initialSection?: string
}>(), {
  initialSection: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'navigate': [target: string]
}>()

const guideBodyRef = ref<HTMLDivElement | null>(null)

function renderMd(md: string): string {
  if (!md) return ''
  try {
    const html = marked(md, { async: false }) as string
    return DOMPurify.sanitize(html)
  } catch {
    return `<pre>${md.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`
  }
}

const handbookHtml = computed(() => renderMd(handbookMd))

// 打开弹窗时按 initialSection 滚动到对应 h2 标题
const SECTION_ANCHOR_MAP: Record<string, string> = {
  tailor: '二、程序裁剪',
  generate: '三、底稿生成',
  assign: '四、委派人员与委派步骤',
  compose: '五、编制',
  review: '六、复核',
  archive: '七、归档',
}

watch(() => props.modelValue, async (open) => {
  if (!open || !props.initialSection) return
  await nextTick()
  await nextTick() // double nextTick for el-dialog render
  scrollToSection(props.initialSection)
})

function scrollToSection(key: string) {
  const anchor = SECTION_ANCHOR_MAP[key]
  if (!anchor || !guideBodyRef.value) return
  // 找对应 h2 元素
  const headings = guideBodyRef.value.querySelectorAll('h2')
  for (const h of headings) {
    if (h.textContent?.includes(anchor.replace(/^[一二三四五六七八九十]+、/, ''))) {
      h.scrollIntoView({ behavior: 'smooth', block: 'start' })
      // 高亮效果
      h.style.transition = 'background 0.3s'
      h.style.background = '#f0e6ff'
      setTimeout(() => { h.style.background = '' }, 2000)
      break
    }
  }
}

function close() {
  emit('update:modelValue', false)
}

function goTo(target: string) {
  emit('navigate', target)
  close()
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="📖 底稿编制模块 · 使用手册"
    width="900px"
    top="4vh"
    destroy-on-close
    append-to-body
    class="wp-module-handbook-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      type="success"
      :closable="false"
      show-icon
      class="mb12"
      title="一页读懂：程序裁剪 → 底稿生成 → 委派执行 → 编制 → 复核 → 归档。含裁剪功能与注意事项、委派人员与步骤、编制界面能力、看板等视图。"
    />

    <!-- 快捷跳转导航条 -->
    <div class="handbook-nav-bar">
      <span class="handbook-nav-bar__label">快捷跳转：</span>
      <el-button size="small" text @click="scrollToSection('tailor')">§二 程序裁剪</el-button>
      <el-button size="small" text @click="scrollToSection('generate')">§三 底稿生成</el-button>
      <el-button size="small" text @click="scrollToSection('assign')">§四 委派</el-button>
      <el-button size="small" text @click="scrollToSection('compose')">§五 编制</el-button>
      <el-button size="small" text @click="scrollToSection('review')">§六 复核</el-button>
      <el-button size="small" text @click="scrollToSection('archive')">§七 归档</el-button>
    </div>

    <div ref="guideBodyRef" class="guide-body prose" v-html="handbookHtml" />

    <!-- 底部：快捷操作入口 -->
    <template #footer>
      <div class="handbook-footer">
        <div class="handbook-footer__actions">
          <el-button size="small" @click="goTo('tailor')">🔧 前往程序裁剪</el-button>
          <el-button size="small" @click="goTo('matrix')">👥 前往委派矩阵</el-button>
          <el-button size="small" @click="goTo('workbench')">📝 前往工作台</el-button>
        </div>
        <el-button type="primary" @click="close">知道了</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.mb12 { margin-bottom: 12px; }

.handbook-nav-bar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 8px;
  margin-bottom: 10px;
  background: #f9f5ff;
  border-radius: 6px;
  border: 1px solid #e8d5f5;
  flex-wrap: wrap;
}
.handbook-nav-bar__label {
  font-size: 12px;
  color: #4b2d77;
  font-weight: 600;
  margin-right: 4px;
}

.handbook-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.handbook-footer__actions {
  display: flex;
  gap: 6px;
}

.guide-body {
  max-height: min(65vh, 680px);
  overflow-y: auto;
  padding: 4px 8px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: #303133;
}
.prose :deep(h1) {
  font-size: 18px;
  margin: 0 0 12px;
  color: #1f2a37;
}
.prose :deep(h2) {
  font-size: 15px;
  margin: 18px 0 8px;
  padding-left: 8px;
  border-left: 3px solid #4b2d77;
  color: #4b2d77;
}
.prose :deep(h3) {
  font-size: 14px;
  margin: 14px 0 6px;
  color: #303133;
}
.prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0 12px;
  font-size: 12px;
}
.prose :deep(th),
.prose :deep(td) {
  border: 1px solid #ebeef5;
  padding: 6px 8px;
  vertical-align: top;
}
.prose :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}
.prose :deep(ul),
.prose :deep(ol) {
  padding-left: 1.35em;
  margin: 6px 0;
}
.prose :deep(li) { margin: 3px 0; }
.prose :deep(code) {
  background: #f4f4f5;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}
.prose :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #f0a020;
  color: #606266;
  background: #fffbf0;
}
.prose :deep(hr) {
  border: none;
  border-top: 1px solid #ebeef5;
  margin: 16px 0;
}
</style>
