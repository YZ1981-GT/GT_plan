<template>
  <div class="h1-tab-dep-impair">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px"
      title="审计目标：验证计提减值后的固定资产以减值后净值与剩余年限重新测算折旧，测算折旧与账面计提一致，差异原因充分。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar" style="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <GtIndexChip value="wp:H1-12" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <div class="branch-selector">
      <el-segmented v-model="depBranch" :options="branchOptions" />
      <span class="branch-hint">当前: 含减值（86公式）— 减值后剩余年限重新计算折旧</span>
    </div>

    <div class="methodology-context">
      <p>含减值折旧: 计提减值后，以(原值-累计折旧-减值准备)为新基数、(1-残值率)为计提比例、剩余年限为新年限重新计算月折旧。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-12(B) 折旧测算-含减值</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H1-12-B')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border stripe size="small" max-height="480" class="dep-table">
        <el-table-column type="index" width="35" fixed />
        <el-table-column prop="category" label="分类" width="80" fixed />
        <el-table-column prop="originalCost" label="原值" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="salvageRate" label="残值率%" width="65" align="right" />
        <el-table-column prop="usefulLife" label="原年限" width="55" align="right" />
        <el-table-column prop="impairmentAmount" label="减值准备" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.impairmentAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="减值后净值" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="原值-折旧-减值">{{ fmtAmt(row.postImpairmentNetValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="新月折旧" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="减值后净值×(1-残值率)÷剩余年限÷12">{{ fmtAmt(row.postImpairmentMonthlyDep) }}</span>
          </template>
        </el-table-column>
        <!-- 12月简化显示 -->
        <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="75" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.monthly?.[m-1] ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期合计" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.periodTotal) }}</span></template>
        </el-table-column>
        <el-table-column prop="bookDepreciation" label="账面" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookDepreciation) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="totals-bar">
        <span>测算合计: <b class="amount-cell">{{ fmtAmt(summary.calculatedTotal) }}</b></span>
        <span>差异合计: <b :class="['amount-cell', { 'error-amount': Math.abs(summary.totalDifference) > 0.01 }]">{{ fmtAmt(summary.totalDifference) }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="depNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="说明减值后折旧测算差异原因..." @change="saveDepNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="auditConclusionText" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>减值后新基数 = 原值 - 累计折旧 - 减值准备</li>
        <li>新月折旧 = 新基数 × (1-残值率) ÷ 剩余年限 ÷ 12</li>
        <li>减值前月份用原月折旧，减值后月份用新月折旧</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Depreciation, type DepreciationBranch } from '../../composables/useH1Depreciation'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const depNote = ref('')
const auditConclusionText = ref('')
const NOTE_KEY = 'H1-12-audit-note-impair'
const CONCLUSION_KEY = 'H1-12-audit-conclusion-impair'
function saveDepNote() { saveResponse(NOTE_KEY, depNote.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, auditConclusionText.value) }
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) depNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) auditConclusionText.value = c.remark
})
const depBranch = ref<DepreciationBranch>('B')
const branchOptions = [
  { label: '不含减值-直线法', value: 'A' },
  { label: '含减值', value: 'B' },
  { label: '多次减值', value: 'C' },
]
const { rows, summary } = useH1Depreciation(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-dep-impair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.branch-selector { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.branch-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.dep-table { font-size: 12px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.totals-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
