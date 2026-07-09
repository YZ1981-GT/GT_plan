<template>
  <div class="j1-tab-severance">
    <el-card shadow="never">
      <template #header><span class="section-title">辞退福利检查表（J1-10）— CAS9</span></template>

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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1SeveranceCheck } from '@/composables/workpaper/j1/useJ1SeveranceCheck'

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
.section-title { font-weight: 600; font-size: 15px; }
.cas9-conditions { padding: 12px; border: 1px solid #ebeef5; border-radius: 6px; background: #fafafa; }
.methodology-context { margin-bottom: 10px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 0 4px 4px 0; }
.methodology-label { font-size: 13px; color: #e6a23c; font-weight: 600; }
.condition-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
.condition-label { color: #303133; }
.overall-tag { margin-top: 10px; }
.total-summary { margin-top: 12px; font-size: 13px; color: #606266; padding: 8px; background: #f5f7fa; border-radius: 4px; }
</style>
