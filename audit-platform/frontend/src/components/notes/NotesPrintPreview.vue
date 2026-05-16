<template>
  <div class="notes-print-preview" :class="{ active: visible }">
    <!-- Toolbar -->
    <div class="npp-toolbar">
      <span class="npp-title">打印预览</span>
      <div class="npp-actions">
        <el-button size="small" @click="insertPageBreak">📄 插入分页符</el-button>
        <el-button size="small" type="primary" @click="$emit('close')">关闭预览</el-button>
      </div>
    </div>

    <!-- A4 Pages Container -->
    <div class="npp-pages-container" ref="pagesContainer">
      <div
        v-for="(page, idx) in pages"
        :key="idx"
        class="npp-page"
      >
        <div class="npp-page-header">
          <span class="npp-page-number">第 {{ idx + 1 }} 页</span>
        </div>
        <div class="npp-page-content" v-html="page.html" />
        <div class="npp-page-footer">
          <span>第 {{ idx + 1 }} 页 共 {{ pages.length }} 页</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'

interface PageContent {
  html: string
}

const props = defineProps<{
  visible: boolean
  sections: Array<{
    title: string
    content: string
    tables?: Array<{ html: string }>
  }>
}>()

const emit = defineEmits<{
  close: []
  'insert-page-break': [sectionIndex: number]
}>()

const pagesContainer = ref<HTMLDivElement>()

// A4 page dimensions (in px at 96dpi)
const PAGE_HEIGHT_PX = 1123 // ~297mm
const PAGE_WIDTH_PX = 794 // ~210mm
const MARGIN_TOP = 121 // ~3.2cm
const MARGIN_BOTTOM = 96 // ~2.54cm
const CONTENT_HEIGHT = PAGE_HEIGHT_PX - MARGIN_TOP - MARGIN_BOTTOM

// Paginate content into A4 pages
const pages = computed<PageContent[]>(() => {
  if (!props.sections || props.sections.length === 0) {
    return [{ html: '<p style="color: var(--gt-color-text-tertiary); text-align: center;">暂无附注内容</p>' }]
  }

  const result: PageContent[] = []
  let currentPageHtml = ''
  let estimatedHeight = 0

  for (const section of props.sections) {
    // Section title
    const titleHtml = `<h3 class="npp-section-title">${section.title}</h3>`
    const titleHeight = 40 // Estimated title height

    // Check if title + minimum content fits on current page
    if (estimatedHeight + titleHeight + 60 > CONTENT_HEIGHT && currentPageHtml) {
      // Start new page - keep title with content (orphan control)
      result.push({ html: currentPageHtml })
      currentPageHtml = ''
      estimatedHeight = 0
    }

    currentPageHtml += titleHtml
    estimatedHeight += titleHeight

    // Section text content
    if (section.content) {
      const lines = section.content.split('\n')
      for (const line of lines) {
        const lineHeight = 24
        if (estimatedHeight + lineHeight > CONTENT_HEIGHT) {
          result.push({ html: currentPageHtml })
          currentPageHtml = ''
          estimatedHeight = 0
        }
        currentPageHtml += `<p class="npp-text">${line || '&nbsp;'}</p>`
        estimatedHeight += lineHeight
      }
    }

    // Section tables
    if (section.tables) {
      for (const table of section.tables) {
        const tableHeight = 100 // Minimum table height estimate
        if (estimatedHeight + tableHeight > CONTENT_HEIGHT && currentPageHtml) {
          result.push({ html: currentPageHtml })
          currentPageHtml = ''
          estimatedHeight = 0
        }
        currentPageHtml += `<div class="npp-table-wrapper">${table.html}</div>`
        estimatedHeight += tableHeight
      }
    }

    // Add spacing between sections
    estimatedHeight += 16
  }

  // Last page
  if (currentPageHtml) {
    result.push({ html: currentPageHtml })
  }

  return result.length > 0 ? result : [{ html: '' }]
})

function insertPageBreak() {
  emit('insert-page-break', 0)
}
</script>

<style scoped>
.notes-print-preview {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: var(--gt-color-border-light);
  overflow-y: auto;
}

.notes-print-preview.active {
  display: block;
}

.npp-toolbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--gt-color-bg-white);
  border-bottom: 1px solid var(--gt-color-border-lighter);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.npp-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}

.npp-actions {
  display: flex;
  gap: 8px;
}

.npp-pages-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px;
  gap: 24px;
}

.npp-page {
  width: 794px;
  min-height: 1123px;
  background: var(--gt-color-bg-white);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  padding: 121px 120px 96px 113px; /* top right bottom left (3.2cm/3.18cm/2.54cm/3cm) */
  position: relative;
  box-sizing: border-box;
}

.npp-page-header {
  position: absolute;
  top: 49px; /* 1.3cm */
  left: 113px;
  right: 120px;
  text-align: right;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}

.npp-page-footer {
  position: absolute;
  bottom: 49px; /* 1.3cm */
  left: 113px;
  right: 120px;
  text-align: center;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}

.npp-page-content {
  font-family: '仿宋_GB2312', '仿宋', FangSong, serif;
  font-size: 12pt;
  line-height: 1.5;
}

:deep(.npp-section-title) {
  font-weight: bold;
  margin: 16px 0 8px;
  font-size: 12pt;
}

:deep(.npp-text) {
  margin: 0;
  padding: 2px 0;
  text-indent: 2em;
}

:deep(.npp-table-wrapper) {
  margin: 8px 0;
  overflow-x: auto;
}

:deep(.npp-table-wrapper table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 10pt;
}

:deep(.npp-table-wrapper th),
:deep(.npp-table-wrapper td) {
  border: 1px solid var(--gt-color-text-primary);
  padding: 4px 6px;
}

:deep(.npp-table-wrapper th) {
  font-weight: bold;
  text-align: center;
  border-bottom-width: 2px;
}
</style>
