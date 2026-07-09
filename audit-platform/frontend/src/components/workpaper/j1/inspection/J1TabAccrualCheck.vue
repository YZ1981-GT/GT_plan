<template>
  <div class="j1-tab-accrual">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">计提情况检查表（J1-6）</span>
          <el-tag v-if="hasAbnormal" type="danger" size="small">计提差异>5%</el-tag>
        </div>
      </template>

      <!-- 蓝色引导区 -->
      <div class="guide-area">
        <div class="guide-step"><span class="step-num">1</span>录入期末人数/平均薪酬</div>
        <div class="guide-step"><span class="step-num">2</span>系统测算应提金额</div>
        <div class="guide-step"><span class="step-num">3</span>与实提对比，差异>5%需说明</div>
      </div>

      <el-table :data="rows" border size="small" style="font-size: 13px">
        <el-table-column prop="category" label="薪酬类别" min-width="120" />
        <el-table-column prop="headcount" label="人数" width="80" align="right" />
        <el-table-column prop="base" label="基数/均薪" width="110" align="right">
          <template #default="{ row }">{{ row.base?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="比例" width="80" align="right">
          <template #default="{ row }">{{ row.rate > 0 ? (row.rate * 100).toFixed(1) + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column prop="months" label="月数" width="60" align="center" />
        <el-table-column label="应提(测算)" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="应提=人数×基数×比例×月数 或 人数×均薪×月数">
              {{ row.estimated?.toLocaleString() }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="actual" label="实提" width="120" align="right">
          <template #default="{ row }">{{ row.actual?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="差异率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': row.isAbnormal }">
              {{ row.diffRate !== null ? row.diffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="说明" min-width="120" />
      </el-table>

      <!-- 合计 -->
      <div class="total-summary">
        测算合计: {{ totalEstimated?.toLocaleString() }} | 实提合计: {{ totalActual?.toLocaleString() }}
        | 整体差异率: <span :class="{ 'text-danger': overallDiffRate !== null && Math.abs(overallDiffRate) > 5 }">
          {{ overallDiffRate !== null ? overallDiffRate.toFixed(1) + '%' : '-' }}
        </span>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1AccrualCheck } from '@/composables/workpaper/j1/useJ1AccrualCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, totalEstimated, totalActual, overallDiffRate, hasAbnormal, initFromHtmlData } = useJ1AccrualCheck(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-accrual { padding: 16px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.section-title { font-weight: 600; font-size: 15px; }
.guide-area { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; padding: 12px; background: linear-gradient(135deg, #ecf5ff, #f0f9ff); border-radius: 6px; }
.guide-step { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.step-num { width: 22px; height: 22px; border-radius: 50%; background: #409eff; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.text-danger { color: #f56c6c; font-weight: 600; }
.total-summary { margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 13px; }
</style>
