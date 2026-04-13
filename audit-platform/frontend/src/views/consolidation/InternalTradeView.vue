<template>
  <div class="gt-internal-trade-view">
    <el-tabs v-model="activePanel" class="gt-internal-trade-tabs">
      <el-tab-pane label="内部交易管理" name="trade">
        <InternalTradePanel
          :project-id="projectId"
          :period="period"
          @elimination-generated="onEliminationGenerated"
        />
      </el-tab-pane>
      <el-tab-pane label="内部往来对账" name="arap">
        <InternalArApPanel :project-id="projectId" :period="period" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import InternalTradePanel from '@/components/consolidation/InternalTradePanel.vue'
import InternalArApPanel from '@/components/consolidation/InternalArApPanel.vue'

const props = defineProps<{
  projectId: string
  year: number
}>()

const activePanel = ref('trade')
const period = props.year

function onEliminationGenerated(entryIds: string[]) {
  if (entryIds?.length) {
    ElMessage.success(`已生成 ${entryIds.length} 条抵消分录，抵消分录管理页面已更新`)
  }
}
</script>

<script lang="ts">
export default { name: 'InternalTradeView' }
</script>

<style scoped>
.gt-internal-trade-view {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.gt-internal-trade-tabs :deep(.el-tabs__header) {
  margin-bottom: var(--gt-space-3);
}
</style>
