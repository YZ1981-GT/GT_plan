<template>
  <div class="j1-tab-accrual">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：复核工资、社保、公积金、福利费等各类薪酬的计提基数与比例，测算应提金额与实际计提对比，差异率超过 5% 须查明原因，验证计提的完整性与准确性。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">计提情况检查表（J1-6）</span>
          <el-tag v-if="hasAbnormal" type="danger" size="small">计提差异>5%</el-tag>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rows.length }} 类</el-tag>
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
        <el-table-column label="应提(测算)" width="120" align="right" class-name="auto-calc-col">
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

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，短期薪酬应在职工提供服务的会计期间确认为负债并计入成本费用。</p>
        <p>2. 灰色底纹"应提(测算)"列为自动计算列（人数×基数×比例×月数），不可手动编辑。</p>
        <p>3. 应提与实提差异率超过 5% 自动标红，须在说明栏查明原因（如奖金跨期、社保基数调整等）。</p>
        <p>4. 计提合计应与分配情况检查表（J1-7）、明细表（J1-2）贷方发生额勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1AccrualCheck } from '@/composables/workpaper/j1/useJ1AccrualCheck'
import GtIndexChip from '../../GtIndexChip.vue'

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
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.guide-area { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; padding: 12px; background: linear-gradient(135deg, #ecf5ff, #f0f9ff); border-radius: 6px; }
.guide-step { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.step-num { width: 22px; height: 22px; border-radius: 50%; background: #409eff; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.text-danger { color: #f56c6c; font-weight: 600; }
.total-summary { margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 13px; }
</style>
