<template>
  <div class="j1-tab-industry">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：将被审计单位人均薪酬、薪酬占收入比等指标与同行业均值/区间对比，识别显著偏离（差异率异常标红），评估薪酬水平的合理性。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">应付职工薪酬同行业对比分析表</span>
          <el-tag v-if="hasAbnormal" type="warning" size="small">存在显著差异</el-tag>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rows.length }} 项指标</el-tag>
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

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 同行业对比属分析性程序，用于评估薪酬总额、人均薪酬与行业水平的偏离合理性。</p>
        <p>2. 行业均值/区间数据来源须注明（如上市公司年报、行业协会统计、Wind 数据等）。</p>
        <p>3. 差异率超过阈值自动标红/标橙，显著偏离项须结合企业规模、地区、岗位结构分析。</p>
        <p>4. 异常结论应与月度分析表（J1-4）、计提检查表（J1-6）交叉印证。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1IndustryCompare } from '@/composables/workpaper/j1/useJ1IndustryCompare'
import GtIndexChip from '../../GtIndexChip.vue'

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
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.company-summary { margin-top: 8px; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.text-danger { color: #f56c6c; font-weight: 600; }
.text-warning { color: #e6a23c; }
</style>
