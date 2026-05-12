<template>
  <div class="eqcr-metrics gt-fade-in">
    <GtPageHeader title="EQCR 指标仪表盘" @back="router.push('/eqcr/workbench')">
      <template #actions>
        <el-select v-model="selectedYear" size="small" style="width: 120px" @change="fetchMetrics">
          <el-option v-for="y in yearOptions" :key="y" :label="`${y}年`" :value="y" />
        </el-select>
        <el-button size="small" @click="fetchMetrics" :loading="loading" round>刷新</el-button>
      </template>
    </GtPageHeader>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #title>异议率不是负面指标</template>
      <div style="font-size: 12px">
        较高的异议率说明 EQCR 独立性强、敢于提出不同意见。异议率为 0% 需审查是否走过场。
      </div>
    </el-alert>

    <el-table
      v-loading="loading"
      :data="metrics"
      border
      stripe
      style="width: 100%"
    >
      <el-table-column prop="eqcr_name" label="EQCR 合伙人" min-width="140" />
      <el-table-column prop="project_count" label="项目数" width="80" align="center" />
      <el-table-column prop="total_hours" label="总工时(h)" width="100" align="center" />
      <el-table-column prop="disagreement_count" label="异议数" width="80" align="center" />
      <el-table-column label="异议率" width="120" align="center">
        <template #default="{ row }">
          <el-tooltip content="健康的 EQCR 应产生建设性异议，过低（0%）可能表示复核流于形式" placement="top">
            <el-tag
              :type="rateTagType(row.disagreement_rate)"
              size="small"
            >
              {{ row.disagreement_rate }}%
            </el-tag>
          </el-tooltip>
          <span v-if="row.disagreement_rate > 20" style="margin-left: 4px; font-size: 11px; color: #67c23a">独立性强</span>
          <span v-else-if="row.disagreement_rate === 0" style="margin-left: 4px; font-size: 11px; color: #e6a23c">需审查</span>
        </template>
      </el-table-column>
      <el-table-column prop="material_findings_count" label="未解决发现" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.material_findings_count > 0" type="danger" size="small">
            {{ row.material_findings_count }}
          </el-tag>
          <span v-else>0</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/services/apiProxy'
import { eqcr as P_eqcr } from '@/services/apiPaths'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const loading = ref(false)
const metrics = ref<any[]>([])
const currentYear = new Date().getFullYear()
const selectedYear = ref(currentYear)

const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - i)

type ElTagType = 'success' | 'warning' | 'info' | 'primary' | 'danger'

function rateTagType(rate: number): ElTagType {
  if (rate > 20) return 'success'  // 绿标：独立性强
  if (rate === 0) return 'warning'  // 黄标：需审查
  return 'info'
}

async function fetchMetrics() {
  loading.value = true
  try {
    const data = await api.get(`${P_eqcr.metrics}?year=${selectedYear.value}`)
    metrics.value = data.metrics || []
  } catch (e: any) {
    handleApiError(e, '获取 EQCR 指标')
  } finally {
    loading.value = false
  }
}

onMounted(fetchMetrics)
</script>

<style scoped>
.eqcr-metrics { padding: var(--gt-space-5, 20px); }
</style>
