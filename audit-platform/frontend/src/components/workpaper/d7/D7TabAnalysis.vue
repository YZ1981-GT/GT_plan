<template>
<div class="d7-analysis">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对合同负债（科目2205）本期借贷方发生额构成及期末债务人集中度进行分析性复核，依据 CAS14 收入准则。</p>
        <p>2. 借方发生额通常对应履约义务完成后结转至主营业务收入；贷方发生额对应本期新增预收/收取的合同对价。</p>
        <p>3. 借方/贷方发生额合计应与试算平衡表对应科目发生额核对一致（差异应为0）。</p>
        <p>4. 前十大债务人集中度较高时应关注客户集中度风险，并结合 D7-2 明细表分析变动合理性。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过分析性复核评价合同负债本期发生额构成的合理性，识别异常变动及客户集中度风险，为实质性程序提供方向。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile" :disabled="isReadonly">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D7-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ debitRows.length + creditRows.length }} 行</el-tag>
      </div>
    </div>

    <!-- TB 勾稽校验 -->
    <el-alert v-if="tbCrossCheck" :type="tbCrossCheck.type" :title="tbCrossCheck.message" :closable="false" show-icon style="margin-bottom: 8px" />

    <!-- (一) 借方发生额分析 -->
    <div class="analysis-card">
      <h4 class="card-title">(一) 借方发生额分析</h4>
      <el-table :data="debitRows" size="small" border>
        <el-table-column label="对方科目/项目" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'item', v)" />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateDebitCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数据来源" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.dataSource" size="small" @change="(v: string) => updateDebitCell(row.rowId, 'dataSource', v)" />
            <span v-else>{{ row.dataSource }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="removeDebitRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="card-footer">
        <el-button v-if="!isReadonly" size="small" @click="addDebitRow">添加行</el-button>
        <div class="diff-line">
          <span>TB借方合计：{{ fmtAmt(debitTotal) }}</span>
          <el-tag v-if="debitDiff === 0" type="success" size="small">核对一致</el-tag>
          <el-tag v-else type="danger" size="small">差异 {{ fmtAmt(debitDiff) }}</el-tag>
        </div>
      </div>
    </div>

    <!-- (三) 贷方发生额分析 -->
    <div class="analysis-card">
      <h4 class="card-title">(三) 贷方发生额分析</h4>
      <el-table :data="creditRows" size="small" border>
        <el-table-column label="对方科目/项目" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'item', v)" />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCreditCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数据来源" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.dataSource" size="small" @change="(v: string) => updateCreditCell(row.rowId, 'dataSource', v)" />
            <span v-else>{{ row.dataSource }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="removeCreditRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="card-footer">
        <el-button v-if="!isReadonly" size="small" @click="addCreditRow">添加行</el-button>
        <div class="diff-line">
          <span>TB贷方合计：{{ fmtAmt(creditTotal) }}</span>
          <el-tag v-if="creditDiff === 0" type="success" size="small">核对一致</el-tag>
          <el-tag v-else type="danger" size="small">差异 {{ fmtAmt(creditDiff) }}</el-tag>
        </div>
      </div>
    </div>

    <!-- (四) Top10 债务人 -->
    <div class="analysis-card">
      <h4 class="card-title">(四) 期末Top10债务人</h4>
      <el-alert
        v-if="isHighConcentration"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom:8px"
      >
        前十大客户集中度较高（{{ (top10Concentration * 100).toFixed(1) }}%），请关注客户集中度风险
      </el-alert>
      <el-table :data="top10Rows" size="small" border>
        <el-table-column label="债务人名称" min-width="160">
          <template #default="{ row }">
            <span>{{ row.customerName }}</span>
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" style="margin-left:4px" />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.priorBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="变动金额" width="120" align="right">
          <template #default="{ row }"><span :class="{ 'diff-red': row.changeAmount !== 0 }">{{ fmtAmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动比例" width="90" align="center">
          <template #default="{ row }"><span :class="{ 'rate-exceed': isRateExceed(row.changeRate) }">{{ fmtPercent(row.changeRate) }}</span></template>
        </el-table-column>
        <el-table-column label="账龄" width="120">
          <template #default="{ row }"><span>{{ row.aging }}</span></template>
        </el-table-column>
        <el-table-column label="期后结转" width="110" align="right">
          <template #default="{ row }"><span>{{ fmtAmt(row.postTransfer) }}</span></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D7-2" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genAnalysisNote">🤖 AI辅助</el-button>
            </el-tooltip>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="对借贷方发生额构成及Top10客户的分析..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genAnalysisConclusion">🤖 AI辅助</el-button>
            </el-tooltip>
          </div>
        </div>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="分析程序结论..."
        />
      </div>
    </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabAnalysis.vue — 分析表 D7-4 (~350行)
 * 4区块卡片：借方+贷方+Top10+审计说明
 * Task: 19.1
 * Requirements: 9.1-9.10, 19.2, 20.1
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD7Analysis } from '../composables/useD7Analysis'
import { useD7ImportExport } from '../composables/useD7ImportExport'
import { useD7AiGenerate } from '../composables/useD7AiGenerate'
import { isChangeRateExceeding } from '../composables/useD7FormulaEngine'
import type { ChecklistResponse } from '../composables/useD7FormData'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: any
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const {
  debitRows, debitTotal, debitDiff,
  creditRows, creditTotal, creditDiff,
  top10Rows, top10Concentration, isHighConcentration,
  auditNotes,
  addDebitRow, addCreditRow,
  removeDebitRow, removeCreditRow,
  updateDebitCell, updateCreditCell,
} = useD7Analysis({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

const tbCrossCheck = computed<{ type: 'info' | 'success' | 'warning'; message: string } | null>(() => {
  const responses = allResponsesRef.value
  if (!responses || responses.size === 0) return null

  const tbDebitRaw = responses.get('D7-4-tb-debit-total')?.remark
  const tbCreditRaw = responses.get('D7-4-tb-credit-total')?.remark

  const tbDebit = parseFloat(tbDebitRaw || '') || 0
  const tbCredit = parseFloat(tbCreditRaw || '') || 0

  if (!tbDebitRaw && !tbCreditRaw) {
    return { type: 'info', message: '勾稽校验：试算平衡表2205科目发生额数据尚未加载' }
  }

  const debitDiffAmt = Math.abs(debitTotal.value - tbDebit)
  const creditDiffAmt = Math.abs(creditTotal.value - tbCredit)

  if (debitDiffAmt < 0.01 && creditDiffAmt < 0.01) {
    return { type: 'success', message: `勾稽校验通过：借方 ${fmtAmt(debitTotal.value)} = TB ${fmtAmt(tbDebit)}，贷方 ${fmtAmt(creditTotal.value)} = TB ${fmtAmt(tbCredit)}` }
  }

  const parts: string[] = []
  if (debitDiffAmt >= 0.01) parts.push(`借方差异 ${fmtAmt(debitTotal.value - tbDebit)}`)
  if (creditDiffAmt >= 0.01) parts.push(`贷方差异 ${fmtAmt(creditTotal.value - tbCredit)}`)
  return { type: 'warning', message: `勾稽校验：${parts.join('；')}` }
})

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD7ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D7-4',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
  return false
}

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD7AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genAnalysisNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('analysis-note', auditNotes.value.explanation, {
    task: '合同负债分析性复核说明',
    debitTotal: debitTotal.value,
    creditTotal: creditTotal.value,
    debitDiff: debitDiff.value,
    creditDiff: creditDiff.value,
    top10Concentration: top10Concentration.value,
    isHighConcentration: isHighConcentration.value,
  }, 'AI · 分析性复核说明')
  if (text) auditNotes.value.explanation = text
}

async function genAnalysisConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('analysis-note', auditNotes.value.conclusion, {
    task: '合同负债分析程序结论',
    debitDiff: debitDiff.value,
    creditDiff: creditDiff.value,
    top10Concentration: top10Concentration.value,
  }, 'AI · 分析程序结论')
  if (text) auditNotes.value.conclusion = text
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return String(rate)
  return `${(rate * 100).toFixed(1)}%`
}

function isRateExceed(rate: number | '' | 'N/A'): boolean {
  return isChangeRateExceeding(rate, 0.3)
}
</script>

<style scoped>
.d7-analysis { padding: 12px; }
.d7-analysis :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d7-analysis :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.analysis-card { margin-bottom: 20px; padding: 16px; border: 1px solid #ebeef5; border-radius: 8px; }
.card-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; color: #303133; }
.card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.diff-line { display: flex; gap: 12px; align-items: center; font-size: var(--wp-font-size, 13px); }
.diff-red { color: #f56c6c; font-weight: 600; }
.rate-exceed { color: #f56c6c; font-weight: 600; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
</style>
