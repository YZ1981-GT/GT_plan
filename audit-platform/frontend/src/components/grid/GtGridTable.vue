<script setup lang="ts">
/**
 * GtGridTable — 原生表格接入表格交互（spec excel-style-table-editing ADR-6）
 *
 * 把 `<table class="...">…</table>` 换成 `<GtGridTable class="...">…</GtGridTable>`：渲染出来的仍是
 * 那一个 `<table>`（组件根节点）—— class / style / 属性落在它上面，父组件的 scoped 样式、`> table`
 * 选择器、外层布局都不受影响。只多两样：
 * - `gt-grid-raw` 类：相对定位，作选区边框与承接框的定位基准（零优先级，页面自己的 position 优先）；
 * - 第一个子元素是零高的 `<caption>`，放承接框与读屏播报。承接框直接放进 table 会被当成匿名行组，
 *   separate 边框的表多出一个 border-spacing 的高度（Chrome 实测；零高 caption 不占高度）。
 * 单元格里的 el-input / el-input-number / el-select 等自动按单元格编辑器工作。
 */
import { getCurrentInstance, onBeforeUnmount, onMounted, ref } from 'vue'
import { kernelForRawTable } from './gridRegistry'

defineOptions({ name: 'GtGridTable' })

const tableRef = ref<HTMLTableElement | null>(null)
const hostRef = ref<HTMLElement | null>(null)
const kernel = kernelForRawTable(getCurrentInstance()!, () => tableRef.value)

onMounted(() => kernel.attach(tableRef.value, { sinkHost: hostRef.value }))
onBeforeUnmount(() => kernel.detach())

defineExpose({ kernel, table: tableRef })
</script>

<template>
  <table ref="tableRef" class="gt-grid-raw">
    <caption ref="hostRef" class="gt-grid-raw__host" />
    <slot />
  </table>
</template>
