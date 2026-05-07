<!--
  LinkageStatusBar — 联动状态横条 [R7-S3-10 Task 51]

  当项目有 stale 数据时显示在 Detail 区第二行（GtPageHeader 之下）。
  黄色细条，提示"当前项目有 X 处数据过期"+ 一键重算按钮。

  用法：
    <LinkageStatusBar v-if="staleCount > 0" :stale-count="staleCount" @recalc="onRecalcAll" @detail="showStaleDetail" />
-->
<template>
  <transition name="el-fade-in">
    <div v-if="!dismissed && staleCount > 0" class="gt-linkage-bar">
      <span class="gt-linkage-bar__icon">⚠️</span>
      <span class="gt-linkage-bar__text">当前项目有 <strong>{{ staleCount }}</strong> 处数据过期</span>
      <el-button size="small" type="primary" text @click="$emit('recalc')">一键重算</el-button>
      <el-button size="small" text @click="$emit('detail')">查看详情</el-button>
      <el-button size="small" text class="gt-linkage-bar__close" @click="dismissed = true">×</el-button>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  /** 过期数据数量 */
  staleCount: number
}>()

defineEmits<{
  (e: 'recalc'): void
  (e: 'detail'): void
}>()

const dismissed = ref(false)
</script>

<style scoped>
.gt-linkage-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: linear-gradient(90deg, #fff8e6 0%, #fff3cd 100%);
  border-bottom: 1px solid #ffc107;
  font-size: var(--gt-font-size-xs);
  color: #856404;
}
.gt-linkage-bar__icon { font-size: 14px; }
.gt-linkage-bar__text { flex: 1; }
.gt-linkage-bar__close {
  padding: 2px 6px;
  min-width: auto;
  color: #856404;
}
</style>
