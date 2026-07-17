<template>
  <section class="ct-overview">
    <header class="ct-overview-head">
      <div>
        <h3>截止测试总览 · F2-29~32</h3>
        <p>
          样本 {{ overview.totalSamples }} ·
          跨期 {{ overview.totalCross }} ·
          异常 {{ overview.totalErrors }} ·
          {{ overview.allCategorized ? '已分类' : '存在未分类' }} ·
          {{ overview.allHaveConclusions ? '结论已齐' : '结论待补' }}
        </p>
      </div>
      <div class="ct-overview-flags">
        <el-tag size="small" :type="overview.allHaveSamples ? 'success' : 'warning'">
          {{ overview.allHaveSamples ? '四表均有样本' : '有表尚未抽样' }}
        </el-tag>
        <el-tag size="small" :type="overview.allCategorized ? 'success' : 'warning'">
          {{ overview.allCategorized ? '原材料/产成品已分类' : '需分类编制' }}
        </el-tag>
      </div>
    </header>
    <div class="ct-overview-table">
      <el-table :data="overview.sheets" size="small" border table-layout="fixed">
        <el-table-column prop="sheetCode" label="底稿" width="82" fixed="left" align="center" />
        <el-table-column prop="title" label="测试方向" width="220" fixed="left" show-overflow-tooltip />
        <el-table-column prop="total" label="样本数" width="76" align="center" />
        <el-table-column label="样本分类" align="center">
          <el-table-column label="原材料" width="82" prop="rawCount" align="center" />
          <el-table-column label="产成品" width="82" prop="finishedCount" align="center" />
          <el-table-column label="未分类" width="82" align="center">
            <template #default="{ row }">
              <span :class="{ warn: row.uncategorizedCount > 0 }">{{ row.uncategorizedCount }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="截止异常" align="center">
          <el-table-column label="跨期" width="72" prop="crossCount" align="center" />
          <el-table-column label="提前入账" width="92" prop="earlyCount" align="center" />
          <el-table-column label="推迟入账" width="92" prop="lateCount" align="center" />
          <el-table-column label="有账无单" width="92" prop="missingDocCount" align="center" />
          <el-table-column label="有单无账" width="92" prop="missingBookCount" align="center" />
        </el-table-column>
        <el-table-column label="结论" width="76" align="center" fixed="right">
          <template #default="{ row }">
            <el-tag :type="row.hasConclusion ? 'success' : 'info'" size="small">
              {{ row.hasConclusion ? '已完成' : '待补' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { buildF2CutoffBundleOverview } from '../../composables/f2CutoffOverview'
import type { ChecklistResponse } from '../../composables/useF2FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  bsDate?: string
}>()

const overview = computed(() =>
  buildF2CutoffBundleOverview(props.allResponses, props.bsDate || ''),
)
</script>

<style scoped>
.ct-overview {
  margin-bottom: 12px;
  border: 1px solid #e8eaef;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.ct-overview-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 14px;
  border-bottom: 1px solid #e8eaef;
  background: var(--gt-color-primary-bg, #f4f0fa);
}
.ct-overview-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--gt-color-primary, #4b2d77);
}
.ct-overview-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: #6b7280;
}
.ct-overview-flags { display: flex; flex-wrap: wrap; gap: 6px; }
.ct-overview :deep(.el-table) { font-size: 13px; }
.ct-overview-table {
  width: 100%;
  overflow-x: auto;
}
.ct-overview-table :deep(.el-table) { min-width: 1150px; }
.ct-overview-table :deep(.el-table__header th) {
  height: 42px;
  padding: 6px 0;
  color: #3f2b5f;
  font-weight: 650;
  background: #f8f5fc;
}
.ct-overview-table :deep(.el-table__body td) { height: 44px; }
.ct-overview-table :deep(.cell) {
  line-height: 1.35;
  white-space: normal;
  word-break: keep-all;
}
.warn { color: var(--gt-color-coral, #FF5149); font-weight: 600; }
</style>
