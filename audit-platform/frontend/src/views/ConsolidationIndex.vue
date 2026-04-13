<template>
  <div class="gt-consolidation gt-fade-in">
    <div class="gt-consol-header">
      <h2 class="gt-page-title">合并报表</h2>
      <div class="gt-consol-actions">
        <el-button @click="onRefresh" :loading="store.loading" plain>刷新</el-button>
      </div>
    </div>

    <el-tabs v-model="store.activeTab" class="gt-tabs">
      <el-tab-pane label="合并试算表" name="trial">
        <ConsolTrialView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="抵消分录管理" name="elimination">
        <EliminationView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="组成部分审计师" name="auditor">
        <ComponentAuditorView :project-id="projectId" />
      </el-tab-pane>
      <el-tab-pane label="内部交易抵销" name="trade">
        <InternalTradeView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="商誉减值测试" name="goodwill">
        <GoodwillView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="外币报表折算" name="forex">
        <ForexView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="少数股东权益" name="mi">
        <MinorityInterestView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="集团架构管理" name="structure">
        <GroupStructureView :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="合并报表" name="report">
        <ConsolReportView :project-id="projectId" />
      </el-tab-pane>
      <el-tab-pane label="合并附注" name="notes">
        <ConsolNotesView :project-id="projectId" />
      </el-tab-pane>
      <el-tab-pane label="合并计算" name="calculation">
        <ConsolCalculationView :project-id="projectId" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useConsolidationStore } from '@/stores/consolidation'
import ConsolTrialView from '@/views/consolidation/ConsolTrialView.vue'
import EliminationView from '@/views/consolidation/EliminationView.vue'
import ComponentAuditorView from '@/views/consolidation/ComponentAuditorView.vue'
import InternalTradeView from '@/views/consolidation/InternalTradeView.vue'
import GoodwillView from '@/views/consolidation/GoodwillView.vue'
import ForexView from '@/views/consolidation/ForexView.vue'
import MinorityInterestView from '@/views/consolidation/MinorityInterestView.vue'
import GroupStructureView from '@/views/consolidation/GroupStructureView.vue'
import ConsolCalculationView from '@/views/consolidation/ConsolCalculationView.vue'
import ConsolReportView from '@/views/consolidation/ConsolReportView.vue'
import ConsolNotesView from '@/views/consolidation/ConsolNotesView.vue'

const route = useRoute()
const store = useConsolidationStore()

const projectId = computed(() => String(route.params.projectId))
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

onMounted(() => {
  store.activeTab = 'trial'
})

function onRefresh() {
  // Re-trigger tab load by toggling
  const tab = store.activeTab
  store.activeTab = ''
  store.activeTab = tab
}
</script>

<script lang="ts">
import { computed } from 'vue'
export default { name: 'ConsolidationIndex' }
</script>

<style scoped>
.gt-consolidation {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-4);
}

.gt-consol-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gt-tabs :deep(.el-tabs__item) {
  font-weight: 500;
}
</style>
