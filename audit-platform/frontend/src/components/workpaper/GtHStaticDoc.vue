<!--
  GtHStaticDoc.vue — H 类辅助说明只读 markdown 渲染组件

  H 类底稿（约 104 sheet：审计程序说明、政策摘录、修订说明、编制说明、
  填表说明、文号规则、参考准则、应用指南等）属于 only-read 辅助文档，
  不需要在线编辑。本组件按 design §3.7 + Task 12.1 实现：

  - 标题优先级：htmlData.title → schema.fixed_cells.A2 → fixed_cells.title
                → static_text.title → schema.title
  - 内容优先级：htmlData.content → htmlData.markdown_content
                → schema.static_text.content → schema.fixed_cells.content
                → schema.markdown_content → static_text.description → schema.text
  - 元数据：index_no（fixed_cells.I3/J3/O3/P3 致同模板右上角索引号）
            period（fixed_cells.A4 致同模板审计期间行）
  - 通过 marked + DOMPurify 把 markdown 渲染为安全的 HTML
  - prose-friendly 版式：max-width 800px 居中，可读字号 14px line-height 1.8
  - 纯只读，无 Emit、无 save 路径

  锚定 spec workpaper-html-renderer Task 12.1
  Validates: Requirements 3.7（H 辅助说明）
-->
<template>
  <div class="gt-h-static-doc">
    <div class="gt-h-static-doc__inner">
      <header v-if="hasHeader" class="gt-h-static-doc__header">
        <div class="gt-h-static-doc__header-row">
          <el-tag size="small" type="info" effect="plain" round>H · 辅助说明</el-tag>
          <span v-if="title" class="gt-h-static-doc__title">{{ title }}</span>
          <span v-if="sheetName" class="gt-h-static-doc__sheet">{{ sheetName }}</span>
        </div>
        <div v-if="indexNo || period" class="gt-h-static-doc__meta">
          <span v-if="indexNo" class="gt-h-static-doc__meta-item">
            索引号：<strong>{{ indexNo }}</strong>
          </span>
          <span v-if="period" class="gt-h-static-doc__meta-item">
            期间：<strong>{{ period }}</strong>
          </span>
        </div>
      </header>

      <article
        v-if="renderedHtml"
        class="gt-h-static-doc__content markdown-body"
        v-html="renderedHtml"
      />

      <el-empty
        v-else
        description="暂无内容"
        :image-size="64"
        class="gt-h-static-doc__empty"
      >
        <template #description>
          <span class="gt-h-static-doc__empty-text">暂无内容</span>
          <span v-if="sheetName" class="gt-h-static-doc__empty-sheet">Sheet：{{ sheetName }}</span>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// ─── Props ───
const props = defineProps<{
  wpId: string
  sheetName: string
  schema: Record<string, any>
  htmlData: Record<string, any>
}>()

// ─── Computed ───
/**
 * 解析 markdown 原始内容（5 级优先级）
 *   1. htmlData.content              ← 项目级用户保存（运行时优先）
 *   2. htmlData.markdown_content     ← 兼容字段
 *   3. schema.static_text.content    ← schema 静态文本块
 *   4. schema.fixed_cells.content    ← 致同 H 类模板常用 cell
 *   5. schema.markdown_content / static_text.description / schema.text ← 兜底
 */
const rawMarkdown = computed<string>(() => {
  const data = props.htmlData ?? {}
  const schema = props.schema ?? {}
  const staticText = (schema.static_text ?? {}) as Record<string, any>
  const fixedCells = (schema.fixed_cells ?? {}) as Record<string, any>

  // 优先级 1：项目级 htmlData.content（用户最新保存）
  if (typeof data.content === 'string' && data.content.trim()) {
    return data.content
  }
  if (typeof data.markdown_content === 'string' && data.markdown_content.trim()) {
    return data.markdown_content
  }
  // 优先级 2：schema 静态文本块
  if (typeof staticText.content === 'string' && staticText.content.trim()) {
    return staticText.content
  }
  // 优先级 3：schema fixed_cells.content（致同模板 H 类常用 cell）
  if (typeof fixedCells.content === 'string' && fixedCells.content.trim()) {
    return fixedCells.content
  }
  // 优先级 4：schema 顶层 markdown
  if (typeof schema.markdown_content === 'string' && schema.markdown_content.trim()) {
    return schema.markdown_content
  }
  // 优先级 5：description / text 兜底
  if (typeof staticText.description === 'string' && staticText.description.trim()) {
    return staticText.description
  }
  if (typeof schema.text === 'string' && schema.text.trim()) {
    return schema.text
  }
  return ''
})

const title = computed<string>(() => {
  const data = props.htmlData ?? {}
  const schema = props.schema ?? {}
  const staticText = (schema.static_text ?? {}) as Record<string, any>
  const fixedCells = (schema.fixed_cells ?? {}) as Record<string, any>

  if (typeof data.title === 'string' && data.title.trim()) return data.title
  // H 类致同模板标题常落在 A2 cell（第一行单位名 + A2 标题行）
  if (typeof fixedCells.A2 === 'string' && fixedCells.A2.trim()) return fixedCells.A2
  if (typeof fixedCells.title === 'string' && fixedCells.title.trim()) return fixedCells.title
  if (typeof staticText.title === 'string' && staticText.title.trim()) return staticText.title
  if (typeof schema.title === 'string' && schema.title.trim()) return schema.title
  return ''
})

const indexNo = computed<string>(() => {
  const data = props.htmlData ?? {}
  const schema = props.schema ?? {}
  const fixedCells = (schema.fixed_cells ?? {}) as Record<string, any>

  if (typeof data.index_no === 'string' && data.index_no.trim()) return data.index_no
  if (typeof schema.index_no === 'string' && schema.index_no.trim()) return schema.index_no
  // 致同模板索引号常出现在右上角（I3/J3/O3/P3）
  for (const key of ['I3', 'J3', 'O3', 'P3']) {
    const v = fixedCells[key]
    if (typeof v === 'string' && v.trim()) return v
  }
  return ''
})

const period = computed<string>(() => {
  const data = props.htmlData ?? {}
  const schema = props.schema ?? {}
  const fixedCells = (schema.fixed_cells ?? {}) as Record<string, any>

  if (typeof data.period === 'string' && data.period.trim()) return data.period
  if (typeof schema.period === 'string' && schema.period.trim()) return schema.period
  // 致同模板期间常落 A4
  if (typeof fixedCells.A4 === 'string' && fixedCells.A4.trim()) return fixedCells.A4
  return ''
})

const hasHeader = computed<boolean>(
  () => Boolean(title.value || indexNo.value || period.value || props.sheetName)
)

/**
 * marked + DOMPurify 渲染 markdown 为安全 HTML
 * marked 走同步模式（async: false）保证 SSR / setup 同步流程
 */
const renderedHtml = computed<string>(() => {
  const md = rawMarkdown.value
  if (!md) return ''
  try {
    const html = marked(md, { async: false }) as string
    return DOMPurify.sanitize(html)
  } catch {
    // 渲染失败兜底为转义后的纯文本
    const escaped = md
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<pre>${escaped}</pre>`
  }
})
</script>

<style scoped>
.gt-h-static-doc {
  width: 100%;
  min-height: 320px;
  padding: 24px 16px;
  background: var(--gt-color-bg-page, #f7f6f9);
  box-sizing: border-box;
}

/* prose-friendly width: 800px max, centered */
.gt-h-static-doc__inner {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px 40px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  box-sizing: border-box;
}

.gt-h-static-doc__header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 16px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--gt-color-border-light, #ebeef5);
}

.gt-h-static-doc__header-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.gt-h-static-doc__title {
  font-size: 17px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  flex: 1 1 auto;
  min-width: 0;
}

.gt-h-static-doc__sheet {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  margin-left: auto;
  white-space: nowrap;
}

.gt-h-static-doc__meta {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #909399);
}

.gt-h-static-doc__meta-item strong {
  color: var(--gt-color-text-regular, #606266);
  font-weight: 600;
  margin-left: 4px;
}

.gt-h-static-doc__content {
  font-size: 14px;
  line-height: 1.8;
  color: var(--gt-color-text-primary, #303133);
}

.gt-h-static-doc__content :deep(h1),
.gt-h-static-doc__content :deep(h2),
.gt-h-static-doc__content :deep(h3),
.gt-h-static-doc__content :deep(h4) {
  margin: 18px 0 10px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.gt-h-static-doc__content :deep(h1) { font-size: 20px; }
.gt-h-static-doc__content :deep(h2) { font-size: 18px; }
.gt-h-static-doc__content :deep(h3) { font-size: 16px; }
.gt-h-static-doc__content :deep(h4) { font-size: 14px; }

.gt-h-static-doc__content :deep(p) {
  margin: 8px 0;
}

.gt-h-static-doc__content :deep(ul),
.gt-h-static-doc__content :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.gt-h-static-doc__content :deep(li) {
  margin: 4px 0;
}

.gt-h-static-doc__content :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 16px;
  border-left: 3px solid var(--gt-color-primary, #6750a4);
  background: var(--gt-color-bg-page, #f7f6f9);
  color: var(--gt-color-text-regular, #606266);
}

.gt-h-static-doc__content :deep(code) {
  padding: 2px 6px;
  background: var(--gt-color-bg-page, #f5f5f5);
  border-radius: 3px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}

.gt-h-static-doc__content :deep(pre) {
  padding: 12px 16px;
  background: var(--gt-color-bg-page, #f5f5f5);
  border-radius: 4px;
  overflow-x: auto;
  margin: 12px 0;
}

.gt-h-static-doc__content :deep(pre code) {
  padding: 0;
  background: transparent;
}

.gt-h-static-doc__content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}

.gt-h-static-doc__content :deep(th),
.gt-h-static-doc__content :deep(td) {
  padding: 8px 12px;
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  text-align: left;
}

.gt-h-static-doc__content :deep(th) {
  background: var(--gt-color-bg-page, #f7f6f9);
  font-weight: 600;
}

.gt-h-static-doc__content :deep(a) {
  color: var(--gt-color-primary, #6750a4);
  text-decoration: none;
}

.gt-h-static-doc__content :deep(a:hover) {
  text-decoration: underline;
}

.gt-h-static-doc__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 240px;
}

.gt-h-static-doc__empty-text {
  font-size: 14px;
  color: var(--gt-color-text-tertiary, #909399);
}

.gt-h-static-doc__empty-sheet {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--gt-color-text-placeholder, #c0c4cc);
}
</style>
