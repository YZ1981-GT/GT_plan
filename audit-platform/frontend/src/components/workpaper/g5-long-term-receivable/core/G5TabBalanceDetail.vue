<template>
  <div class="g5-balance-detail">
    <div class="section-head">
      <h3 class="sheet-title">G5-2 余额明细表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-2" />
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="g5-2-balance-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：核实长期应收款各债务人期末余额、未实现融资收益及净额，按账龄分段验证合计勾稽，识别关联方及长账龄风险。
    </el-alert>

    <!-- 区段Tab切换 -->
    <div class="segment-tabs">
      <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions">
        <el-button size="small" type="primary" plain @click="detail.addRow()" :disabled="props.readonly">
          + 新增债务人
        </el-button>
      </div>
    </div>

    <!-- Tab1: 债务人基础信息 -->
    <el-table
      v-show="detail.activeTab.value === 'basic'"
      :data="detail.rows.value"
      :height="500"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorName" label="债务人名称" min-width="120" />
      <el-table-column prop="businessType" label="业务类型" width="100">
        <template #default="{ row }">
          <el-select v-model="row.businessType" size="small" :disabled="props.readonly">
            <el-option label="融资租赁" value="lease" />
            <el-option label="分期销售" value="installment" />
            <el-option label="保理" value="factoring" />
            <el-option label="其他" value="other" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="contractNo" label="合同编号" min-width="100" />
      <el-table-column prop="startDate" label="起始日" width="100" />
      <el-table-column prop="maturityDate" label="到期日" width="100" />
      <el-table-column prop="contractAmount" label="合同总额" min-width="100" align="right" />
      <el-table-column prop="recoveredAmount" label="已收回金额" min-width="100" align="right" />
      <el-table-column label="期末余额" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="合同总额-已收回">{{ fmt(row.closingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="isRelatedParty" label="关联方" width="70" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.isRelatedParty" :disabled="props.readonly" />
        </template>
      </el-table-column>
    </el-table>

    <!-- Tab2: 余额分析+账龄（动态列，基于 bands from useAgingConfig） -->
    <el-table
      v-show="detail.activeTab.value === 'aging'"
      :data="detail.rows.value"
      :height="500"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorName" label="债务人名称" min-width="120" />
      <el-table-column prop="unrealizedIncome" label="未实现融资收益" min-width="110" align="right" />
      <el-table-column label="净额" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末余额-未实现融资收益">{{ fmt(row.netAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-for="band in bands"
        :key="band.key"
        :label="band.label"
        min-width="80"
        align="right"
      >
        <template #default="{ row }">
          {{ fmt(row.agingAudited[band.key] ?? 0) }}
        </template>
      </el-table-column>
      <el-table-column label="账龄合计" min-width="90" align="right">
        <template #default="{ row }">
          <span
            class="formula-cell"
            :class="{ 'mismatch': Math.abs(row.agingTotal - row.netAmount) > 0.01 }"
            title="各账龄段之和"
          >{{ fmt(row.agingTotal) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100" />
    </el-table>

    <!-- 底部合计 -->
    <div class="totals-bar">
      合同总额: {{ fmt(detail.totals.value.contractAmount) }} |
      已收回: {{ fmt(detail.totals.value.recoveredAmount) }} |
      期末余额: {{ fmt(detail.totals.value.closingBalance) }} |
      净额: {{ fmt(detail.totals.value.netAmount) }}
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="props.readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述明细核对情况、账龄勾稽结果、关联方及长账龄风险，以及拟调整/未调整事项及其影响。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="props.readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项，不可确认。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>期末余额 = 合同总额 − 已收回金额（自动计算列）</li>
        <li>净额 = 期末余额 − 未实现融资收益</li>
        <li>账龄合计应等于净额，若不一致（红色）需核对账龄分段录入</li>
        <li>账龄分段随项目账龄配置动态生成，可在"底稿配置"中调整</li>
        <li>关联方债务人须勾选，供关联方交易披露与减值单独评估</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG5BalanceDetail } from '../../composables/useG5BalanceDetail'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const detail = useG5BalanceDetail(toRef(props, 'projectId'))
const { bands } = detail

// ─── 审计说明 / 审计结论（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-2-audit-note'
const G5_CONCLUSION_KEY = 'G5-2-audit-conclusion'
function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const tabOptions = [
  { label: '债务人基础信息', value: 'basic' },
  { label: '余额分析+账龄', value: 'aging' },
]

function onRowChange(row: any) {
  if (row) {
    const idx = detail.rows.value.findIndex(r => r.id === row.id)
    if (idx >= 0) detail.activeRowIndex.value = idx
  }
}

function fmt(v: number): string {
  return v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '-'
}
</script>

<style scoped>
.g5-balance-detail { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.tab-actions { margin-left: auto; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.mismatch { color: #f56c6c; font-weight: 600; }
.totals-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
