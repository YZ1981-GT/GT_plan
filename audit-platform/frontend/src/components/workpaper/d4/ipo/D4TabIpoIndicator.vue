<script setup lang="ts">
/**
 * D4TabIpoIndicator — D4-22 IPO指标分析
 *
 * 同D4-6结构 + 增强指标
 * Requirements: 14.2
 */
import { inject } from 'vue'

defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
</script>

<template>
  <div class="d4-tab-ipo-indicator">
    <div class="section-header">
      <h4>IPO增强指标分析</h4>
      <div class="flex gap-2">
        <el-button size="small" disabled>🤖 AI辅助</el-button>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-22-indicator')">💬</el-button>
      </div>
    </div>

    <el-table :data="[]" border stripe>
      <el-table-column prop="name" label="指标名称" min-width="160" />
      <el-table-column prop="currentValue" label="本期值" width="120" align="right" />
      <el-table-column prop="priorValue" label="上期值" width="120" align="right" />
      <el-table-column prop="change" label="变动" width="100" align="right" />
      <el-table-column prop="industryRef" label="行业参考" width="120" />
      <el-table-column prop="conclusion" label="结论" width="90" align="center" />
    </el-table>

    <div class="mt-4">
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入IPO指标分析结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-ipo-indicator { padding: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h4 { margin: 0; font-size: 15px; color: #303133; }
.mt-4 { margin-top: 16px; }
</style>
