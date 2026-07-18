<template>
  <div class="f5-adjudication">
    <details class="guidance-details">
      <summary>📋 编制思路与审定逻辑</summary>
      <div class="guidance-content">
        <p>1. 本表为营业成本（6401）审定表：损益类仅列本期/上期发生额，无期初期末；审定 = 未审 + 账项调整 + 重分类。</p>
        <p>2. 主营业务成本按品种动态列示（可从 F5-2 月度明细引用品种及全年/上期合计），下方小计；其他业务成本同样动态行 + 小计（可从 F5-3 引用）。</p>
        <p>3. 合计 = 主营小计 + 其他小计；分别与本期/上期试算平衡表数核对，差异 = 审定 − 试算。</p>
        <p>4. 审计说明须写明主营业务成本本期较上期增减；变动比例超过 30% 的品种须说明主要原因。结论评价结转完整性与准确性。</p>
        <p>5. 审定完成后「发布审定数」回写试算，并供 F5-7 成本倒轧等下游底稿消费；「同步F5-4调整」将 6401 相关 AJE/RJE 净额写入主营汇总行。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实营业成本各项目本期发生额的完整与准确，确认成本结转口径恰当，为利润表营业成本列报及毛利分析提供审定依据。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-hint">损益类 6401 · 本期/上期对比</span>
        <el-tag size="small" type="info">品种 {{ dataRowCount }} 行</el-tag>
        <el-tag v-if="adj.significantChanges.value.length" size="small" type="warning">
          变动&gt;30% {{ adj.significantChanges.value.length }} 项
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-2" :context-project-id="projectIdStr" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-4" :context-project-id="projectIdStr" /></span>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="handleSync">
          从F5-2引用品种
          <el-badge v-if="adj.pendingSyncCount.value" :value="adj.pendingSyncCount.value" class="sync-badge" />
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleSyncOther">从F5-3引用</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleSyncAdj">同步F5-4调整</el-button>
        <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
      </div>
    </div>

    <F5SheetAttachments
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-1"
      label="审定表附件"
    />

    <el-table :data="tableData" size="small" border :row-class-name="rowClass" max-height="560" class="adj-table">
      <el-table-column label="项目" min-width="160" fixed>
        <template #default="{ row }">
          <template v-if="row.__type === 'group'">
            <span class="f5-adj-group">{{ row.label }}</span>
            <el-button
              v-if="!isReadonly && row.group"
              size="small"
              type="primary"
              link
              @click="promptAddRow(row.group)"
            >+ 品种</el-button>
          </template>
          <template v-else-if="row.__type === 'data'">
            <el-input
              v-if="!row.isFixed && !isReadonly"
              :model-value="row.label"
              size="small"
              @change="(v: string) => adj.updateCell(row.group, row.rowKey, 'label', v)"
            />
            <span v-else>{{ row.label }}</span>
          </template>
          <span v-else class="f5-adj-subtotal">{{ row.label }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期数" align="center">
        <el-table-column label="本期未审数" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentUnadjusted"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.group, row.rowKey, 'currentUnadjusted', v ?? 0)"
            />
            <span v-else-if="row.currentUnadjusted != null">{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.group, row.rowKey, 'currentAje', v ?? 0)"
            />
            <span v-else-if="row.currentAje != null">{{ fmt(row.currentAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.group, row.rowKey, 'currentRje', v ?? 0)"
            />
            <span v-else-if="row.currentRje != null">{{ fmt(row.currentRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期审定数" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.currentAdjusted != null" class="f5-formula" title="审定 = 未审 + 账项调整 + 重分类">
              {{ fmt(row.currentAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="上期数" align="center">
        <el-table-column label="上期未审数" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorUnadjusted"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.group, row.rowKey, 'priorUnadjusted', v ?? 0)"
            />
            <span v-else-if="row.priorUnadjusted != null">{{ fmt(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.group, row.rowKey, 'priorAje', v ?? 0)"
            />
            <span v-else-if="row.priorAje != null">{{ fmt(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.group, row.rowKey, 'priorRje', v ?? 0)"
            />
            <span v-else-if="row.priorRje != null">{{ fmt(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期审定数" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.priorAdjusted != null" class="f5-formula" title="审定 = 未审 + 账项调整 + 重分类">
              {{ fmt(row.priorAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="变动额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.changeAmount != null" class="f5-formula" title="本期审定 − 上期审定">
            {{ fmt(row.changeAmount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="变动率%" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span
            v-if="row.changeRate != null && row.changeRate !== 'N/A'"
            :class="{ 'rate-warn': Math.abs(row.changeRate) >= 30 }"
          >{{ Number(row.changeRate).toFixed(1) }}%</span>
          <span v-else-if="row.changeRate === 'N/A'">N/A</span>
        </template>
      </el-table-column>

      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <el-input
            v-if="row.__type === 'data' && !isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="索引"
            @change="(v: string) => adj.updateCell(row.group, row.rowKey, 'indexRef', v)"
          />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" :context-project-id="projectIdStr" />
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right">
        <template #default="{ row }">
          <el-popconfirm
            v-if="row.__type === 'data' && !row.isFixed"
            title="确认删除？"
            @confirm="adj.removeRow(row.group, row.rowKey)"
          >
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="tb-check-block">
      <div class="tb-check-row">
        <span class="tb-label">试算平衡表数（本期 6401）</span>
        <el-input-number
          v-if="!isReadonly"
          v-model="tbInput"
          :controls="false"
          size="small"
          style="width: 160px"
          @change="onTbChange"
        />
        <span v-else>{{ fmt(adj.trialBalanceAmount.value) }}</span>
        <el-tag v-if="Math.abs(adj.variance.value) > 0.01" type="danger" size="small">
          本期差异 {{ fmt(adj.variance.value) }}
        </el-tag>
        <el-tag v-else type="success" size="small">本期核对一致</el-tag>
      </div>
      <div class="tb-check-row">
        <span class="tb-label">试算平衡表数（上期 6401）</span>
        <el-input-number
          v-if="!isReadonly"
          v-model="priorTbInput"
          :controls="false"
          size="small"
          style="width: 160px"
          @change="onPriorTbChange"
        />
        <span v-else>{{ fmt(adj.priorTrialBalanceAmount.value) }}</span>
        <el-tag v-if="Math.abs(adj.priorVariance.value) > 0.01" type="danger" size="small">
          上期差异 {{ fmt(adj.priorVariance.value) }}
        </el-tag>
        <el-tag v-else-if="adj.priorTrialBalanceAmount.value" type="success" size="small">上期核对一致</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.publishAdjudicated()">
          发布审定数（回写TB）
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="adj.significantChanges.value.length"
      type="warning"
      :closable="false"
      show-icon
      class="change-alert"
      :title="`变动比例超过30%共 ${adj.significantChanges.value.length} 项，须在审计说明中披露主要原因`"
    >
      <ul class="change-list">
        <li v-for="item in adj.significantChanges.value" :key="`${item.group}-${item.label}`">
          {{ item.label }}：变动 {{ fmt(item.changeAmount) }}（{{ item.changeRate.toFixed(1) }}%）
        </li>
      </ul>
    </el-alert>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F5-2" :context-project-id="projectIdStr" />
            <GtIndexChip value="wp:F5-7" :context-project-id="projectIdStr" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1、审计说明</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateAiNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
          </div>
        </div>
        <p class="note-hint">
          （1）主营业务成本本期较上期增加（负数为减少）：
          <strong>{{ fmt(adj.mainCostChange.value.changeAmount) }}</strong>
          <template v-if="adj.mainCostChange.value.changeRate !== 'N/A'">
            （{{ Number(adj.mainCostChange.value.changeRate).toFixed(1) }}%）
          </template>
          ；主要原因（比例超过30%的）：
        </p>
        <el-input
          :model-value="adj.auditNote.value"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          :disabled="isReadonly"
          placeholder="说明成本结转口径、量本核对、与收入配比、月度波动及超过30%变动的主要原因…"
          @change="adj.saveAuditNote"
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAiConclusion"
          >🤖 AI生成结论</el-button>
        </div>
        <el-input
          :model-value="adj.auditConclusion.value"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="综合评价营业成本审定结果及列报是否恰当…"
          @change="adj.saveAuditConclusion"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabAdjudication — F5-1 营业成本审定表
 * 主营/其他品种动态行 + 小计 + 试算核对 + AI 审计说明/结论
 */
import { ref, computed, inject, toRef, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useF5Adjudication } from '../composables/useF5Adjudication'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import type { ChecklistResponse } from '../composables/useF1FormData'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const adj = useF5Adjudication({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)

const tbInput = ref(adj.trialBalanceAmount.value)
const priorTbInput = ref(adj.priorTrialBalanceAmount.value)
watch(adj.trialBalanceAmount, (v) => { tbInput.value = v })
watch(adj.priorTrialBalanceAmount, (v) => { priorTbInput.value = v })

const projectIdStr = computed(() => props.projectId)
const dataRowCount = computed(() => adj.mainBusinessRows.value.length + adj.otherBusinessRows.value.length)

function onTbChange() {
  adj.updateTrialBalance(tbInput.value ?? 0)
}
function onPriorTbChange() {
  adj.updatePriorTrialBalance(priorTbInput.value ?? 0)
}

const tableData = computed(() => {
  const rows: any[] = []
  rows.push({ __type: 'group', label: '主营业务成本：', group: 'main' })
  for (const r of adj.mainBusinessRows.value) rows.push({ __type: 'data', group: 'main', ...r })
  rows.push({ __type: 'subtotal', ...adj.mainSubtotal.value })
  rows.push({ __type: 'group', label: '其他业务成本', group: 'other' })
  for (const r of adj.otherBusinessRows.value) rows.push({ __type: 'data', group: 'other', ...r })
  rows.push({ __type: 'subtotal', ...adj.otherSubtotal.value })
  rows.push({ __type: 'subtotal', ...adj.grandTotal.value })
  return rows
})

function rowClass({ row }: { row: any }): string {
  if (row.__type === 'group') return 'f5-row-group'
  if (row.__type === 'subtotal') return 'f5-row-subtotal'
  if (typeof row.changeRate === 'number' && Math.abs(row.changeRate) >= 30) return 'f5-row-warn'
  return ''
}

async function promptAddRow(group: 'main' | 'other') {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '品种名称不能为空',
    })
    if (value) adj.addRow(group, value.trim())
  } catch { /* cancel */ }
}

function handleSync(): void {
  const added = adj.syncFromMonthlyDetail()
  if (added > 0) ElMessage.success(`已从F5-2引用 ${added} 个品种`)
  else ElMessage.info('F5-2中的品种均已存在（已刷新未审数）')
}

function handleSyncOther(): void {
  const added = adj.syncFromOtherCost()
  if (added > 0) ElMessage.success(`已从F5-3引用 ${added} 个项目`)
  else ElMessage.info('F5-3中的项目均已存在（已刷新未审数）')
}

function handleSyncAdj(): void {
  const impact = adj.syncFromAdjustment()
  if (impact.lineCount > 0 || Math.abs(impact.aje) >= 0.005 || Math.abs(impact.rje) >= 0.005) {
    ElMessage.success(
      `已同步F5-4：AJE ${impact.aje.toLocaleString('zh-CN')} / RJE ${impact.rje.toLocaleString('zh-CN')}（${impact.lineCount} 行）`,
    )
  } else {
    ElMessage.info('F5-4中未找到科目6401相关分录')
  }
}

function fmt(v: number | null | undefined): string {
  if (v == null) return ''
  if (Math.abs(v) < 0.005) return '-'
  const formatted = Math.abs(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return v < 0 ? `(${formatted})` : formatted
}

function openReview() {
  openReviewDialog?.('F5-1-conclusion')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F5-1',
    accountCode: '6401',
    mainCostChange: adj.mainCostChange.value,
    significantChanges: adj.significantChanges.value,
    mainSubtotal: {
      current: adj.mainSubtotal.value.currentAdjusted,
      prior: adj.mainSubtotal.value.priorAdjusted,
    },
    otherSubtotal: {
      current: adj.otherSubtotal.value.currentAdjusted,
      prior: adj.otherSubtotal.value.priorAdjusted,
    },
    grandTotal: {
      current: adj.grandTotal.value.currentAdjusted,
      prior: adj.grandTotal.value.priorAdjusted,
    },
    trialBalance: {
      current: adj.trialBalanceAmount.value,
      prior: adj.priorTrialBalanceAmount.value,
      currentVariance: adj.variance.value,
      priorVariance: adj.priorVariance.value,
    },
    products: [
      ...adj.mainBusinessRows.value.map((r) => ({ group: '主营', ...r })),
      ...adj.otherBusinessRows.value.map((r) => ({ group: '其他', ...r })),
    ].map((r) => ({
      group: (r as any).group,
      label: r.label,
      currentAdjusted: r.currentAdjusted,
      priorAdjusted: r.priorAdjusted,
      changeAmount: r.changeAmount,
      changeRate: r.changeRate,
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'adjudication-note',
    adj.auditNote.value,
    aiContext(),
    'AI 生成 · F5-1审计说明',
  )
  if (text) adj.saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'adjudication-conclusion',
    adj.auditConclusion.value,
    aiContext(),
    'AI 生成 · F5-1审计结论',
  )
  if (text) adj.saveAuditConclusion(text)
}
</script>

<style scoped>
.f5-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #315a8a;
  background: #eef4fa;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; color: #315a8a; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert, .change-alert { margin-bottom: 12px; }
.change-list { margin: 6px 0 0; padding-left: 18px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-hint { color: #909399; }
.sync-badge { margin-left: 4px; }
.adj-table { width: 100%; }
.adj-table :deep(.el-input-number) { width: 100%; }
.f5-adj-group { font-weight: 600; color: #315a8a; margin-right: 8px; }
.f5-adj-subtotal { font-weight: 700; }
.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.rate-warn { color: #d03050; font-weight: 700; }
:deep(.auto-calc-col) { background-color: #f5f0fa !important; }
:deep(.f5-row-group) { background: #eef4fa; }
:deep(.f5-row-subtotal) { background: #f0f2f5; font-weight: 700; }
:deep(.f5-row-warn) { background: #fdf6ec; }
.tb-check-block {
  margin: 12px 0;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tb-check-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.tb-label { color: #606266; min-width: 180px; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.note-hint { margin: 0 0 8px; color: #606266; font-size: 13px; line-height: 1.5; }
</style>
