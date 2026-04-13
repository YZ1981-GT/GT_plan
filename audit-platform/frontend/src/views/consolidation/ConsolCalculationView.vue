<template>
  <div class="gt-consol-calculation-view">
    <div class="view-header">
      <h3 class="view-title">合并计算工作表</h3>
      <div class="header-actions">
        <el-select
          v-model="selectedPeriod"
          placeholder="选择期间"
          size="default"
          style="width: 160px"
        >
          <el-option
            v-for="p in periodOptions"
            :key="p.value"
            :label="p.label"
            :value="p.value"
          />
        </el-select>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="gt-tabs calculation-tabs">
      <el-tab-pane label="商誉计算" name="goodwill">
        <GoodwillPanel :project-id="projectId" />
      </el-tab-pane>
      <el-tab-pane label="少数股东权益" name="mi">
        <MinorityInterestPanel :project-id="projectId" :period="selectedPeriod" />
      </el-tab-pane>
      <el-tab-pane label="外币折算" name="forex">
        <ForexTranslationPanel :project-id="projectId" :period="selectedPeriod" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import GoodwillPanel from '@/components/consolidation/GoodwillPanel.vue'
import MinorityInterestPanel from '@/components/consolidation/MinorityInterestPanel.vue'
import ForexTranslationPanel from '@/components/consolidation/ForexTranslationPanel.vue'

const route = useRoute()
const projectId = computed(() => String(route.params.projectId))

const activeTab = ref('goodwill')

// Period selection
const currentYear = new Date().getFullYear()
const selectedPeriod = ref(currentYear)
const periodOptions = [
  { label: `${currentYear} 年度`, value: currentYear },
  { label: `${currentYear - 1} 年度`, value: currentYear - 1 },
  { label: `${currentYear - 2} 年度`, value: currentYear - 2 },
]

onMounted(() => {
  // Sync period from query
  const q = route.query.year
  if (q) {
    selectedPeriod.value = Number(q)
  }
})
</script>

<script lang="ts">
import { computed } from 'vue'
export default { name: 'ConsolCalculationView' }
</script>

<style scoped>
.gt-consol-calculation-view {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-4);
  padding: var(--gt-space-2) 0;
}

.view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.view-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--gt-color-primary-dark);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3);
}

.calculation-tabs :deep(.el-tabs__item) {
  font-weight: 500;
  font-size: 14px;
}

.calculation-tabs :deep(.el-tabs__header) {
  border-bottom: 2px solid var(--gt-color-primary-light);
}
</style>
