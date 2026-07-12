<template>
  <div class="j1-tab-severance">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：依据 CAS 9 验证辞退福利确认条件（正式方案、不可撤回）是否满足，复核预计金额计量的合理性及计提的完整性、准确性。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">辞退福利检查表（J1-10）— CAS9</span>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
        </div>
      </template>

      <!-- CAS9确认条件 -->
      <div class="cas9-conditions">
        <div class="methodology-context">
          <div class="methodology-label">CAS9 辞退福利确认条件（全部满足方可确认负债）</div>
        </div>
        <div v-for="(cond, idx) in cas9Conditions" :key="idx" class="condition-item">
          <el-tag :type="cond.isMet ? 'success' : 'info'" size="small">{{ cond.isMet ? '✓满足' : '待确认' }}</el-tag>
          <span class="condition-label">{{ cond.label }}</span>
        </div>
        <el-tag :type="allConditionsMet ? 'success' : 'warning'" class="overall-tag">
          {{ allConditionsMet ? '全部条件满足，可确认辞退福利负债' : '部分条件未满足' }}
        </el-tag>
      </div>

      <!-- 明细表 -->
      <el-table :data="rows" border size="small" style="font-size: 13px; margin-top: 16px">
        <el-table-column prop="department" label="部门" min-width="100" />
        <el-table-column prop="employeeCount" label="涉及人数" width="80" align="right" />
        <el-table-column label="预计金额" width="120" align="right">
          <template #default="{ row }">{{ row.estimatedAmount?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="实际计提" width="120" align="right">
          <template #default="{ row }">{{ row.actualAccrual?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="正式计划" width="80" align="center">
          <template #default="{ row }">{{ row.hasFormalPlan ? '✓' : '✗' }}</template>
        </el-table-column>
        <el-table-column label="不可撤回" width="80" align="center">
          <template #default="{ row }">{{ row.isIrrevocable ? '✓' : '✗' }}</template>
        </el-table-column>
        <el-table-column label="精算师" width="70" align="center">
          <template #default="{ row }">{{ row.actuaryUsed ? '✓' : '-' }}</template>
        </el-table-column>
        <el-table-column prop="paymentPeriod" label="支付期间" width="100" />
        <el-table-column prop="checkResult" label="结论" min-width="100" />
      </el-table>

      <div class="total-summary">
        涉及人数合计: {{ totalEmployees }} |
        预计金额合计: {{ totalEstimated?.toLocaleString() }} |
        实际计提合计: {{ totalActual?.toLocaleString() }}
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，辞退福利在企业不能单方面撤回解除劳动关系计划、且确认重组成本时孰早日确认。</p>
        <p>2. 上方 CAS9 确认条件须全部满足方可确认辞退福利负债；未全部满足的不得计提。</p>
        <p>3. 涉及重大精算估计的（如提前退休计划），应评估是否利用精算师工作（ISA 620）。</p>
        <p>4. 预计金额与实际计提差异、支付期间超过 12 个月的须按其他长期福利折现处理。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1SeveranceCheck } from '@/composables/workpaper/j1/useJ1SeveranceCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, cas9Conditions, totalEstimated, totalActual, totalEmployees, allConditionsMet, initFromHtmlData } = useJ1SeveranceCheck(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-severance { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.cas9-conditions { padding: 12px; border: 1px solid #ebeef5; border-radius: 6px; background: #fafafa; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.methodology-context { margin-bottom: 10px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 0 4px 4px 0; }
.methodology-label { font-size: var(--wp-font-size, 13px); color: #e6a23c; font-weight: 600; }
.condition-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: var(--wp-font-size, 13px); }
.condition-label { color: #303133; }
.overall-tag { margin-top: 10px; }
.total-summary { margin-top: 12px; font-size: var(--wp-font-size, 13px); color: #606266; padding: 8px; background: #f5f7fa; border-radius: 4px; }
</style>
