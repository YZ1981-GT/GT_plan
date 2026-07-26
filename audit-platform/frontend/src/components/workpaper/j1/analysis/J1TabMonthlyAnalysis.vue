<template>
  <div class="j1-tab-monthly">
    <!-- 方法论上下文（琥珀块） -->
    <div class="amber-context">
      <p><b>提示1：</b>关注各月之间波动有无异常。如果异常降低，考虑是否存在其他方（如关联方）代付工资的情况。</p>
      <p><b>提示2：</b>关注实际薪酬发放日与资产负债表日的间隔时间，考虑本期留存金额是否合理。</p>
    </div>

    <!-- 统计概览卡片 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-label">本期计提合计</div>
        <div class="stat-value">{{ fmtAmount(yearAccrualTotal) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">月均员工人数</div>
        <div class="stat-value">{{ yearHeadcountAvg }} 人</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">年度人均工资</div>
        <div class="stat-value">{{ fmtAmount(yearAvgWage) }}</div>
      </div>
      <div class="stat-card" :class="{ 'stat-danger': Math.abs(yearAvgChangeRate) > 30 }">
        <div class="stat-label">人均变动率</div>
        <div class="stat-value">{{ yearAvgChangeRate.toFixed(1) }}%</div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddDept">
          + 新增部门
        </el-button>
        <GtIndexChip value="wp:J1-1" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ departments.length }} 个部门</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="ledgerPullLoading" @click="pullMonthlyFromLedger">
          📥从序时账取数（2211贷方按月）
        </el-button>
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('monthly')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('monthly')">导出数据</el-dropdown-item>
              <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 3区段Tab -->
    <el-tabs v-model="activeTab" type="border-card">
      <!-- Tab1: 本期分析 -->
      <el-tab-pane label="本期分析" name="current">
        <h4 class="block-title">本期计提工资</h4>
        <MonthlyBlockTable
          :departments="departments" :data="currentAccrual" :total-row="currentAccrualTotal"
          :is-readonly="isReadonly" block-name="currentAccrual" show-proportion
          @update="(dept, mi, v) => updateCell('currentAccrual', dept, mi, v)"
          @remove-dept="removeDept"
          @rename-dept="renameDept"
        />

        <h4 class="block-title">本期员工数量</h4>
        <MonthlyBlockTable
          :departments="departments" :data="currentHeadcount" :total-row="currentHeadcountTotal"
          :is-readonly="isReadonly" block-name="currentHeadcount" :is-integer="true"
          @update="(dept, mi, v) => updateCell('currentHeadcount', dept, mi, v)"
          @remove-dept="removeDept"
          @rename-dept="renameDept"
        />

        <h4 class="block-title">本期人均工资 <el-tag size="small" type="info">公式=计提÷数量</el-tag></h4>
        <MonthlyBlockTable
          :departments="departments" :data="currentAccrual" :total-row="currentAvgWage"
          :is-readonly="true" block-name="currentAvgWage" :is-formula="true"
          :formula-fn="(dept) => deptAvgWage('currentAccrual', dept)"
        />
      </el-tab-pane>

      <!-- Tab2: 同期对比 -->
      <el-tab-pane label="同期对比" name="compare">
        <h4 class="block-title">上期计提工资</h4>
        <MonthlyBlockTable
          :departments="departments" :data="priorAccrual" :total-row="priorAccrualTotal"
          :is-readonly="isReadonly" block-name="priorAccrual"
          @update="(dept, mi, v) => updateCell('priorAccrual', dept, mi, v)"
          @remove-dept="removeDept"
          @rename-dept="renameDept"
        />

        <h4 class="block-title">上期员工数量</h4>
        <MonthlyBlockTable
          :departments="departments" :data="priorHeadcount" :total-row="priorHeadcountTotal"
          :is-readonly="isReadonly" block-name="priorHeadcount" :is-integer="true"
          @update="(dept, mi, v) => updateCell('priorHeadcount', dept, mi, v)"
          @remove-dept="removeDept"
        />

        <h4 class="block-title">上期人均工资 <el-tag size="small" type="info">公式</el-tag></h4>
        <MonthlyBlockTable
          :departments="departments" :data="priorAccrual" :total-row="priorAvgWage"
          :is-readonly="true" block-name="priorAvgWage" :is-formula="true"
          :formula-fn="(dept) => deptAvgWage('priorAccrual', dept)"
        />

        <h4 class="block-title">人均工资变动率 <el-tag size="small" type="danger">异常>30%红色</el-tag></h4>
        <div class="rate-table-wrapper">
          <el-table :data="changeRateTableData" border size="small" style="font-size:13px">
            <el-table-column prop="dept" label="部门" width="120" fixed />
            <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="75" align="right">
              <template #default="{ row }">
                <span :class="{ 'text-danger': Math.abs(row.months[m-1]) > 30 }">
                  {{ row.months[m-1].toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab3: 占比与留存 -->
      <el-tab-pane label="占比与留存" name="retention">
        <h4 class="block-title">本期各月计提占比 <el-tag size="small" type="info">公式=当月÷全年合计</el-tag></h4>
        <div class="proportion-bar">
          <div v-for="(pct, idx) in monthlyProportion" :key="idx" class="prop-item">
            <div class="prop-bar" :style="{ height: Math.max(4, pct * 1.5) + 'px' }" />
            <span class="prop-val">{{ pct.toFixed(1) }}%</span>
            <span class="prop-label">{{ idx + 1 }}月</span>
          </div>
        </div>

        <h4 class="block-title">本期实际发放额 & 留存分析</h4>
        <el-table :data="retentionTableData" border size="small" style="font-size:13px">
          <el-table-column prop="label" label="项目" width="140" fixed />
          <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.editable"
                :model-value="row.months[m-1]"
                :controls="false" size="small" style="width:88px"
                @change="(v: number) => updateBottomCell(row.field, m-1, v ?? 0)"
              />
              <span v-else>{{ fmtNum(row.months[m-1]) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <b>{{ fmtNum(row.months.reduce((s: number, v: number) => s + v, 0)) }}</b>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 异常波动提示 -->
    <el-alert v-if="fluctuations.length > 0" type="warning" :closable="false" show-icon style="margin-top:12px">
      <template #title>
        发现 {{ fluctuations.length }} 处异常波动（偏离月均>30%）
      </template>
      <template #default>
        <div style="font-size:12px;max-height:100px;overflow-y:auto">
          <span v-for="(f, i) in fluctuations.slice(0, 10)" :key="i" style="margin-right:12px">
            {{ f.dept }} {{ f.monthIndex + 1 }}月 偏离{{ f.avgDeviation.toFixed(0) }}%
          </span>
          <span v-if="fluctuations.length > 10">...等</span>
        </div>
      </template>
    </el-alert>

    <!-- 审计说明与结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
        </div>
      </template>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">三、审计说明</span>
          <el-button size="small" type="primary" plain :loading="aiLoading === 'note'" :disabled="isReadonly" @click="generateAi('note')">🤖 AI辅助</el-button>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" placeholder="请输入审计说明..." :disabled="isReadonly" @change="saveOpinion" />
      </div>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">四、审计结论</span>
          <el-button size="small" type="primary" plain :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="generateAi('conclusion')">🤖 AI辅助</el-button>
        </div>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" placeholder="请输入审计结论..." :disabled="isReadonly" @change="saveOpinion" />
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 月度分析用于实施分析性程序，识别薪酬计提的期间异常与合理性。</p>
        <p>2. 人均工资=计提工资÷员工数量（按部门+合计双维度）。</p>
        <p>3. 人均工资变动率>30%自动红色预警，须结合业务实质（年终奖、离职补偿等）判断。</p>
        <p>4. "本期留存=计提-实际发放"，关注留存金额与上年同期对比是否合理。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useJ1MonthlyAnalysis } from '@/composables/workpaper/j1/useJ1MonthlyAnalysis'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import { pullExpenseLedgerMonthly } from '../../composables/expenseLedgerMonthlyPull'
import { useAuditContext } from '@/composables/useAuditContext'
import GtIndexChip from '../../GtIndexChip.vue'
import MonthlyBlockTable from './MonthlyBlockTable.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, any>
  isReadonly?: boolean
  saveImmediate?: (items: Array<any>) => Promise<void>
}>()

const isReadonly = computed(() => props.isReadonly ?? false)
const allResponsesRef = ref(props.allResponses || new Map())

const {
  departments, currentAccrual, currentHeadcount, priorAccrual, priorHeadcount,
  actualPaid, currentRetained, priorRetained,
  currentAccrualTotal, currentHeadcountTotal, priorAccrualTotal, priorHeadcountTotal,
  currentAvgWage, priorAvgWage, avgWageChangeRate, monthlyProportion,
  yearAccrualTotal, yearHeadcountAvg, yearAvgWage, yearAvgChangeRate,
  fluctuations, auditNote, auditConclusion,
  updateCell, updateBottomCell, addDept, removeDept, renameDept, saveOpinion, deptAvgWage,
} = useJ1MonthlyAnalysis({
  allResponses: allResponsesRef,
  saveImmediate: props.saveImmediate || (async () => {}),
  isReadonly: toRef(props, 'isReadonly') as any || ref(false),
})

const activeTab = ref('current')
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)

// 变动率表格数据
const changeRateTableData = computed(() => {
  const rows: Array<{ dept: string; months: number[] }> = []
  for (const dept of departments.value) {
    const curAvg = deptAvgWage('currentAccrual', dept)
    const priAvg = deptAvgWage('priorAccrual', dept)
    const rates = curAvg.map((v, i) => priAvg[i] === 0 ? 0 : ((v - priAvg[i]) / Math.abs(priAvg[i])) * 100)
    rows.push({ dept, months: rates })
  }
  rows.push({ dept: '合计', months: avgWageChangeRate.value })
  return rows
})

// 留存表格数据
const retentionTableData = computed(() => [
  { label: '本期实际发放额', months: actualPaid.value, editable: true, field: 'actualPaid' as const },
  { label: '本期留存', months: currentRetained.value, editable: true, field: 'currentRetained' as const },
  { label: '上年同期留存', months: priorRetained.value, editable: true, field: 'priorRetained' as const },
])

async function handleAddDept() {
  try {
    const { value } = await ElMessageBox.prompt('请输入部门名称', '新增部门', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value?.trim()) addDept(value.trim())
  } catch { /* cancelled */ }
}

function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = (e) => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) importData('monthly', f) }
  input.click()
}

// ─── 从序时账按月取数（2211 贷方→月度分析各月直接回填） ──────────────────
const auditCtx = useAuditContext()
const ledgerPullLoading = ref(false)

function normLabelForMatch(s: unknown): string {
  return String(s ?? '').replace(/[\s\u3000]/g, '').replace(/^其中[:：]/, '').replace(/^\d+[.．、]/, '').replace(/^[一二三四五六七八九十]+[、.．]/, '')
}

async function pullMonthlyFromLedger() {
  if (isReadonly.value) return
  const year = Number(auditCtx.year?.value || new Date().getFullYear())
  try {
    await ElMessageBox.confirm(
      `将从序时账拉取 ${year} 年度科目 2211（应付职工薪酬）的贷方发生额按明细科目×月汇总，直接回填月度分析表各月列。是否继续？`,
      '📥从序时账取数（2211贷方按月）',
      { confirmButtonText: '取数', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  ledgerPullLoading.value = true
  try {
    const res = await pullExpenseLedgerMonthly(props.projectId, '2211', year)
    if (!res.ok) { ElMessage.warning(res.message); return }
    // 月度分析表：按 accountName 匹配 departments，各月贷方（取反，负债贷方为计提）回填
    let matched = 0
    for (const pulled of res.rows) {
      const pk = normLabelForMatch(pulled.accountName)
      if (!pk) continue
      const deptIdx = departments.value.findIndex(d => {
        const dk = normLabelForMatch(d)
        return dk === pk || (dk.length >= 3 && pk.length >= 3 && (dk.includes(pk) || pk.includes(dk)))
      })
      if (deptIdx >= 0) {
        const dept = departments.value[deptIdx]
        for (let mi = 0; mi < 12; mi++) {
          // expenseLedgerMonthlyPull 按借-贷聚合；2211负债科目贷方为负数→取反得正数计提
          const val = pulled.months[mi] < 0 ? -pulled.months[mi] : pulled.months[mi]
          if (Math.abs(val) > 0.005) {
            updateCell('currentAccrual', dept, mi, val)
          }
        }
        matched++
      }
    }
    ElMessage.success(`${res.message}，匹配回填 ${matched} 个部门/项目的月度数据`)
  } finally { ledgerPullLoading.value = false }
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtNum(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

// AI
const aiLoading = ref<string | null>(null)
async function generateAi(section: 'note' | 'conclusion') {
  if (isReadonly.value) return
  aiLoading.value = section
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `j1-4-${section}`,
      prompt: section === 'note'
        ? '根据应付职工薪酬月度分析数据，生成审计说明。关注异常波动、变动率、留存合理性。'
        : '根据应付职工薪酬月度分析数据和审计说明，生成审计结论。',
      context: { '年度计提合计': fmtAmount(yearAccrualTotal.value), '人均变动率': `${yearAvgChangeRate.value.toFixed(1)}%`, '异常波动数': String(fluctuations.value.length) },
      existingContent: section === 'note' ? auditNote.value : auditConclusion.value,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      if (section === 'note') auditNote.value = text; else auditConclusion.value = text
      saveOpinion()
      ElMessage.success('AI生成完成')
    }
  } catch { ElMessage.warning('AI生成失败') }
  finally { aiLoading.value = null }
}
</script>

<style scoped>
.j1-tab-monthly { padding: 12px; }
.j1-tab-monthly :deep(.el-table) { font-size: 13px !important; }
.j1-tab-monthly :deep(.el-table th), .j1-tab-monthly :deep(.el-table td) { font-size: 13px !important; }
.amber-context { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; color: #606266; }
.amber-context p { margin: 2px 0; }
.stats-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 12px; }
.stat-card { background: #f5f7fa; border-radius: 8px; padding: 12px 16px; text-align: center; }
.stat-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; }
.stat-danger .stat-value { color: #f56c6c; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; }
.block-title { font-size: 13px; font-weight: 600; color: #303133; margin: 12px 0 6px; }
.block-title .el-tag { vertical-align: middle; }
.rate-table-wrapper { overflow-x: auto; }
.text-danger { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.proportion-bar { display: flex; align-items: flex-end; gap: 6px; height: 100px; padding: 8px; background: #fafafa; border-radius: 4px; margin-bottom: 12px; }
.prop-item { display: flex; flex-direction: column; align-items: center; flex: 1; }
.prop-bar { width: 100%; max-width: 36px; background: linear-gradient(180deg, #409eff, #79bbff); border-radius: 2px 2px 0 0; }
.prop-val { font-size: 10px; color: #606266; margin-top: 2px; }
.prop-label { font-size: 10px; color: #909399; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 10px 14px; background: #fafafa; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; }
.opinion-section { margin-bottom: 14px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.opinion-section-label { font-size: 13px; font-weight: 500; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
