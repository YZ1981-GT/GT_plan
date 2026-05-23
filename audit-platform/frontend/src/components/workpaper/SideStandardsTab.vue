<!--
  SideStandardsTab.vue — K-2 底稿"相关准则"侧栏

  spec proposal-remaining-18 task 2.6

  - 按 wpCode 前缀映射 cycle 字母（D/E/F/G/H/I/J/K/L/M/N/S）
  - 调 GET /api/knowledge/tsj/{cycle_name} 拉取审计复核提示词 Markdown
  - 用 marked + DOMPurify 渲染（与 ExpenseAnalysisDialog 同模式）
  - wpCode 变化时自动重新加载；缓存按 cycle 维度避免重复请求
-->
<template>
  <div class="gt-side-standards">
    <div v-if="!wpCode" class="gt-wp-side-placeholder">请先选择底稿</div>
    <div v-else-if="loading" v-loading="true" class="gt-side-standards-loading" />
    <div v-else-if="error" class="gt-side-standards-error">
      <p class="gt-side-standards-err-title">未找到对应准则</p>
      <p class="gt-side-standards-err-detail">{{ error }}</p>
      <p class="gt-side-standards-err-hint">
        提示：当前底稿 <code>{{ wpCode }}</code> 推断 cycle =
        <code>{{ resolvedCycle || '(未识别)' }}</code>
      </p>
    </div>
    <div v-else class="gt-side-standards-body">
      <div class="gt-side-standards-meta">
        <el-tag size="small" type="info" round>cycle: {{ resolvedCycle }}</el-tag>
        <span v-if="sourceFile" class="gt-side-standards-source"
          >📄 {{ sourceFile }}</span
        >
      </div>
      <div
        class="gt-side-standards-md gt-markdown-body"
        v-html="renderedMarkdown"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  /** 底稿 wp_code（如 D2-1 / E1 / F2-2 等） */
  wpCode?: string
}>()

const loading = ref(false)
const error = ref<string | null>(null)
const markdown = ref<string>('')
const sourceFile = ref<string>('')

/**
 * 按 wp_code 前缀映射到 cycle 字母代号。
 *
 * 规则：
 *   首字母 ∈ {D,E,F,G,H,I,J,K,L,M,N,S} → 该字母
 *   其它（B/C/A 等辅助类，未在 TSJ 覆盖）→ ''
 */
function inferCycle(wpCode: string | undefined): string {
  if (!wpCode) return ''
  const first = wpCode.trim().charAt(0).toUpperCase()
  if ('DEFGHIJKLMNS'.includes(first)) {
    return first
  }
  return ''
}

const resolvedCycle = computed(() => inferCycle(props.wpCode))

/** 缓存：按 cycle 字母 → {markdown, source_file}；避免重复请求 */
const cache = new Map<
  string,
  { markdown: string; source_file: string }
>()

async function loadStandards() {
  if (!props.wpCode) {
    markdown.value = ''
    sourceFile.value = ''
    error.value = null
    return
  }

  const cycle = resolvedCycle.value
  if (!cycle) {
    markdown.value = ''
    sourceFile.value = ''
    error.value = `wp_code "${props.wpCode}" 不属于业务循环 D-N/S`
    return
  }

  // cache hit
  const cached = cache.get(cycle)
  if (cached) {
    markdown.value = cached.markdown
    sourceFile.value = cached.source_file
    error.value = null
    return
  }

  loading.value = true
  error.value = null
  try {
    const data: { markdown: string; source_file: string; cycle_name: string } =
      await api.get(`/api/knowledge/tsj/${encodeURIComponent(cycle)}`, {
        validateStatus: (s: number) => s < 600,
      })

    if (!data || typeof data !== 'object' || typeof data.markdown !== 'string') {
      error.value = '后端返回格式异常'
      markdown.value = ''
      sourceFile.value = ''
      return
    }

    markdown.value = data.markdown
    sourceFile.value = data.source_file
    cache.set(cycle, {
      markdown: data.markdown,
      source_file: data.source_file,
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '请稍后重试'
    error.value = `加载失败：${msg}`
    markdown.value = ''
    sourceFile.value = ''
  } finally {
    loading.value = false
  }
}

/** Markdown → 安全 HTML（marked + DOMPurify） */
const renderedMarkdown = computed(() => {
  if (!markdown.value) return ''
  const html = marked(markdown.value, { async: false }) as string
  return DOMPurify.sanitize(html)
})

watch(
  () => props.wpCode,
  () => {
    loadStandards()
  },
)

onMounted(() => {
  loadStandards()
})

defineExpose({
  /** 测试/父组件主动刷新 */
  reload: loadStandards,
  /** 暴露内部状态用于测试断言 */
  _state: {
    markdown,
    sourceFile,
    loading,
    error,
  },
})
</script>

<style scoped>
.gt-side-standards {
  padding: var(--gt-space-2);
}

.gt-side-standards-loading {
  min-height: 120px;
}

.gt-side-standards-meta {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  padding-bottom: var(--gt-space-2);
  margin-bottom: var(--gt-space-2);
  border-bottom: 1px dashed var(--gt-color-border-light);
  font-size: var(--gt-font-size-xs);
}

.gt-side-standards-source {
  color: var(--gt-color-text-secondary);
}

.gt-side-standards-md {
  font-size: var(--gt-font-size-sm);
  line-height: 1.7;
  color: var(--gt-color-text);
}

/* Markdown 内容样式（scoped + :deep 透传到 v-html 输出） */
.gt-side-standards-md :deep(h1) {
  font-size: 17px /* allow-px: markdown 标题 */;
  font-weight: 600;
  margin: 12px 0 8px;
  color: var(--gt-color-text);
}
.gt-side-standards-md :deep(h2) {
  font-size: 15px /* allow-px: markdown 标题 */;
  font-weight: 600;
  margin: 10px 0 6px;
  color: var(--gt-color-text);
}
.gt-side-standards-md :deep(h3),
.gt-side-standards-md :deep(h4) {
  font-size: 14px /* allow-px: markdown 子标题 */;
  font-weight: 600;
  margin: 8px 0 4px;
  color: var(--gt-color-text);
}
.gt-side-standards-md :deep(p) {
  margin: 6px 0;
}
.gt-side-standards-md :deep(ul),
.gt-side-standards-md :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}
.gt-side-standards-md :deep(li) {
  margin: 3px 0;
}
.gt-side-standards-md :deep(code) {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: var(--gt-font-size-xs);
  background: var(--gt-color-bg-elevated);
  padding: 1px 4px;
  border-radius: 3px;
}
.gt-side-standards-md :deep(blockquote) {
  border-left: 3px solid var(--gt-color-primary);
  padding-left: 10px;
  margin: 6px 0;
  color: var(--gt-color-text-secondary);
}

.gt-side-standards-error {
  padding: var(--gt-space-3);
  border: 1px dashed var(--gt-color-coral, #f56c6c);
  border-radius: var(--gt-radius-sm);
  background: var(--gt-color-coral-light, rgba(245, 108, 108, 0.05));
  font-size: var(--gt-font-size-xs);
}
.gt-side-standards-err-title {
  font-weight: 600;
  color: var(--gt-color-coral, #f56c6c);
  margin: 0 0 4px;
}
.gt-side-standards-err-detail {
  margin: 0 0 4px;
  color: var(--gt-color-text-secondary);
}
.gt-side-standards-err-hint {
  margin: 4px 0 0;
  color: var(--gt-color-text-tertiary);
}
.gt-side-standards-err-hint code {
  font-family: 'Consolas', 'Courier New', monospace;
  background: var(--gt-color-bg-elevated);
  padding: 1px 4px;
  border-radius: 3px;
}

.gt-wp-side-placeholder {
  padding: var(--gt-space-8);
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
}
</style>
