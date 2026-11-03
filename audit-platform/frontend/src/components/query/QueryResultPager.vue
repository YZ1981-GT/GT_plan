<!--
  QueryResultPager — 业务视图结果翻页（advanced-query-linkage-closure 任务 28 / 29；R2.6、N5）

  弹窗与页面版共用：每页 100 / 200 / 500 行 + 真实 total（后端 COUNT），翻页即按 offset 重新查询；不再有「上限 N 行、
  可能被截断」的提示。改每页行数时回到第 1 页，只发一次 change。
-->
<template>
  <nav class="gt-qrp" aria-label="查询结果翻页" data-testid="cq-pager">
    <el-pagination
      :current-page="page"
      :page-size="pageSize"
      :page-sizes="pageSizes"
      :total="total"
      layout="total, sizes, prev, pager, next, jumper"
      size="small"
      background
      @current-change="onPage"
      @size-change="onSize"
    />
  </nav>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'

const props = withDefaults(defineProps<{
  total: number
  page: number
  pageSize: number
  pageSizes?: number[]
}>(), { pageSizes: () => [100, 200, 500] })

const emit = defineEmits<{
  'update:page': [page: number]
  'update:pageSize': [size: number]
  /** 页码或每页行数变了（宿主据此重新查询） */
  change: [page: number, pageSize: number]
}>()

// 改每页行数时 el-pagination 可能紧接着把页码校正到范围内（同一轮里再发 current-change）：这一轮的页码事件忽略
let resizing = false

function onPage(next: number) {
  if (resizing || next === props.page) return
  emit('update:page', next)
  emit('change', next, props.pageSize)
}

function onSize(size: number) {
  if (size === props.pageSize) return
  resizing = true
  void nextTick(() => { resizing = false })
  emit('update:pageSize', size)
  emit('update:page', 1)
  emit('change', 1, size)
}
</script>

<style scoped>
.gt-qrp { display: flex; justify-content: flex-end; padding: 6px 0 0; }
</style>
