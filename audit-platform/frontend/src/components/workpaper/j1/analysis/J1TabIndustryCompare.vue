<template>
  <div class="j1-tab-industry">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">应付职工薪酬同行业对比分析表</span>
          <el-tag v-if="hasAbnormal" type="warning" size="small">存在显著差异</el-tag>
        </div>
      </template>

      <!-- 公司概况 -->
      <div class="company-summary">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="人均薪酬">{{ perCapita?.toLocaleString() || '-' }} 元</el-descriptions-item>
          <el-descriptions-item label="薪酬占收入比">{{ revenueRatio?.toFixed(2) || '-' }}%</el-descriptions-item>
          <el-descriptions-item label="在职人数">{{ companyInfo.headcount }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 对比表格 -->
      <el-table :data="rows" border size="small" style="font-size: 13px; margin-top: 12px">
        <el-table-column prop="metric" label="对比指标" min-width="140" />
        <el-table-column prop="companyValue" label="公司值" width="120" align="right">
          <template #default="{ row }">{{ row.companyValue?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="industryAvg" label="行业均值" width="120" align="right">
          <template #default="{ row }">{{ row.industryAvg?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="行业区间" width="140" align="center">
          <template #default="{ row }">{{ row.industryMin?.toLocaleString() }} ~ {{ row.industryMax?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="差异率" width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': row.isAbnormal, 'text-warning': !row.isAbnormal && Math.abs(row.diffRate || 0) > 15 }">
              {{ row.diffRate !== null ? row.diffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1IndustryCompare } from '@/composables/workpaper/j1/useJ1IndustryCompare'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, companyInfo, perCapita, revenueRatio, hasAbnormal, initFromHtmlData } = useJ1IndustryCompare(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-industry { padding: 16px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.section-title { font-weight: 600; font-size: 15px; }
.company-summary { margin-top: 8px; }
.text-danger { color: #f56c6c; font-weight: 600; }
.text-warning { color: #e6a23c; }
</style>
