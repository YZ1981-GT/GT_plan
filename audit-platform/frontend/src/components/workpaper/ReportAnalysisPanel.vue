<template>
  <div class="report-analysis-panel">
    <!-- 项目没填审计年度：三个子面板都按年度取数，不按今年兜底 ⇒ 直接说明原因 -->
    <el-empty v-if="year == null" :description="MISSING_AUDIT_YEAR_MESSAGE" />
    <el-tabs v-else v-model="activeTab" type="border-card">
      <el-tab-pane label="试算全景" name="full-tb">
        <TrialBalanceFullView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="期初核对" name="opening">
        <OpeningReconciliation :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="财务比率" name="ratio">
        <FinancialRatioPanel :project-id="projectId" :year="year" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import TrialBalanceFullView from './TrialBalanceFullView.vue'
import OpeningReconciliation from './OpeningReconciliation.vue'
import FinancialRatioPanel from './FinancialRatioPanel.vue'

const props = defineProps<{
  wpId?: string
  projectId: string
  /** 审计年度；项目没填为 null / 未传 */
  year?: number | null
}>()

// 原先 `const year = props.year ?? null` 只取一次：父级年度后到（项目信息异步加载）时子面板一直拿 null
const year = computed(() => props.year ?? null)
const activeTab = ref('full-tb')
</script>

<style scoped>
.report-analysis-panel { padding: 16px; }
</style>
