<template>
  <div class="report-analysis-panel">
    <el-tabs v-model="activeTab" type="border-card">
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
import { ref } from 'vue'
import TrialBalanceFullView from './TrialBalanceFullView.vue'
import OpeningReconciliation from './OpeningReconciliation.vue'
import FinancialRatioPanel from './FinancialRatioPanel.vue'

const props = defineProps<{
  wpId?: string
  projectId: string
  year?: number
}>()

const year = props.year || new Date().getFullYear()
const activeTab = ref('full-tb')
</script>

<style scoped>
.report-analysis-panel { padding: 16px; }
</style>
