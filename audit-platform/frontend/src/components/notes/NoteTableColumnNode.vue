<template>
  <!-- 分组：嵌套 el-table-column（任意层，spec note-pull-header-formula-closure R4）；单元格内容由宿主 #cell 插槽给出 -->
  <el-table-column v-if="node.children && node.children.length" :label="node.label" align="center">
    <NoteTableColumnNode v-for="(child, i) in node.children" :key="`${i}-${child.label}`" :node="child">
      <template #cell="scope"><slot name="cell" v-bind="scope" /></template>
    </NoteTableColumnNode>
  </el-table-column>
  <!-- column-key 带表头序号：期末 / 上年年末下同名的叶子（「应收账款」各一列）点击时按它定位，不按列名 -->
  <el-table-column v-else :label="node.label" :column-key="`h${node.headerIdx ?? -1}`"
                   :min-width="node.headerIdx === 0 ? 160 : 120"
                   :align="node.headerIdx === 0 ? 'left' : 'right'" resizable>
    <template #default="scope">
      <slot name="cell" v-bind="scope" :headerIdx="node.headerIdx ?? -1" :label="node.label" />
    </template>
  </el-table-column>
</template>

<script setup lang="ts">
/** 附注表格列树的一个节点（叶子 = 一列；分组 = 跨列表头）。单元格模板只在宿主写一份。 */
import type { NoteColNode } from '@/views/composables/noteColumnTree'

defineOptions({ name: 'NoteTableColumnNode' })
defineProps<{ node: NoteColNode }>()
// 显式声明插槽类型：递归组件把子节点的 #cell 原样转给宿主，不声明时类型推断自引用（TS7022）
defineSlots<{
  cell(props: { row: any; column: any; $index: number; headerIdx: number; label: string; [key: string]: any }): any
}>()
</script>
