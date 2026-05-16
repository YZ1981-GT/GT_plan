<!--
  ProcedureFlowChart — mermaid 流程图，从 procedure_steps 动态生成
  Sprint 2 Task 2.4
-->
<template>
  <div class="gt-procedure-flowchart">
    <div v-if="!procedures.length" class="gt-flowchart-empty">
      暂无程序步骤
    </div>
    <div v-else ref="chartContainer" class="gt-flowchart-container" v-html="renderedSvg" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { Procedure } from '@/composables/useProcedures'

const props = defineProps<{
  procedures: Procedure[]
}>()

const chartContainer = ref<HTMLElement | null>(null)
const renderedSvg = ref('')

/**
 * 从程序列表生成 mermaid 流程图定义
 */
function buildMermaidDef(procs: Procedure[]): string {
  if (!procs.length) return ''

  const lines: string[] = ['graph TD']
  const applicable = procs.filter(p => p.status !== 'not_applicable')

  for (const proc of applicable) {
    const nodeId = proc.procedure_id.replace(/[^a-zA-Z0-9]/g, '_')
    const statusClass = proc.status === 'completed' ? ':::completed' : ':::pending'
    const label = `${proc.procedure_id}: ${proc.description.slice(0, 30)}`
    lines.push(`  ${nodeId}["${label}"]${statusClass}`)
  }

  // 根据 depends_on 建立连线
  for (const proc of applicable) {
    const nodeId = proc.procedure_id.replace(/[^a-zA-Z0-9]/g, '_')
    const deps = proc.depends_on || []
    for (const dep of deps) {
      const depId = String(dep).replace(/[^a-zA-Z0-9]/g, '_')
      // 只连接存在的节点
      const depExists = applicable.some(
        p => p.procedure_id.replace(/[^a-zA-Z0-9]/g, '_') === depId
      )
      if (depExists) {
        lines.push(`  ${depId} --> ${nodeId}`)
      }
    }
  }

  // 无依赖的节点按顺序串联
  const noDeps = applicable.filter(p => !p.depends_on || p.depends_on.length === 0)
  for (let i = 1; i < noDeps.length; i++) {
    const prev = noDeps[i - 1].procedure_id.replace(/[^a-zA-Z0-9]/g, '_')
    const curr = noDeps[i].procedure_id.replace(/[^a-zA-Z0-9]/g, '_')
    // 只在没有显式依赖时串联
    const hasExplicitLink = applicable.some(
      p => (p.depends_on || []).includes(noDeps[i].procedure_id)
    )
    if (!hasExplicitLink) {
      lines.push(`  ${prev} --> ${curr}`)
    }
  }

  // 样式定义
  lines.push('  classDef completed fill:#d4edda,stroke:#28a745,color: var(--gt-color-success)')
  lines.push('  classDef pending fill:#fff3cd,stroke:#ffc107,color: var(--gt-color-wheat)')

  return lines.join('\n')
}

const mermaidDef = computed(() => buildMermaidDef(props.procedures))

/**
 * 渲染 mermaid 图表为 SVG
 * 使用简单的 HTML 展示 mermaid 定义（实际项目中可集成 mermaid.js）
 */
async function renderChart() {
  if (!mermaidDef.value) {
    renderedSvg.value = ''
    return
  }

  try {
    // 尝试动态加载 mermaid
    const mermaid = (window as any).mermaid
    if (mermaid) {
      const { svg } = await mermaid.render('proc-chart-' + Date.now(), mermaidDef.value)
      renderedSvg.value = svg
    } else {
      // 降级：显示文本格式的流程
      renderedSvg.value = renderFallback()
    }
  } catch {
    renderedSvg.value = renderFallback()
  }
}

function renderFallback(): string {
  const applicable = props.procedures.filter(p => p.status !== 'not_applicable')
  if (!applicable.length) return ''

  const items = applicable.map((p, i) => {
    const statusIcon = p.status === 'completed' ? '✅' : '⬜'
    const arrow = i < applicable.length - 1 ? '<div class="gt-flow-arrow">↓</div>' : ''
    return `<div class="gt-flow-node ${p.status === 'completed' ? 'gt-flow-done' : ''}">
      <span class="gt-flow-icon">${statusIcon}</span>
      <span class="gt-flow-label">${p.procedure_id}: ${p.description}</span>
    </div>${arrow}`
  })

  return `<div class="gt-flow-fallback">${items.join('')}</div>`
}

onMounted(renderChart)
watch(() => props.procedures, renderChart, { deep: true })
</script>

<style scoped>
.gt-procedure-flowchart {
  padding: 8px;
  overflow: auto;
}
.gt-flowchart-empty {
  text-align: center;
  padding: 24px;
  color: var(--gt-color-text-tertiary, #ccc);
  font-size: var(--gt-font-size-sm);
}
.gt-flowchart-container {
  min-height: 100px;
}
.gt-flowchart-container :deep(.gt-flow-fallback) {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px;
}
.gt-flowchart-container :deep(.gt-flow-node) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  background: var(--gt-color-wheat-light);
  font-size: var(--gt-font-size-xs);
  min-width: 200px;
}
.gt-flowchart-container :deep(.gt-flow-done) {
  background: var(--gt-color-success-light);
  border-color: #28a745;
}
.gt-flowchart-container :deep(.gt-flow-arrow) {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-md);
}
.gt-flowchart-container :deep(.gt-flow-icon) {
  font-size: var(--gt-font-size-sm);
}
.gt-flowchart-container :deep(.gt-flow-label) {
  flex: 1;
}
</style>
