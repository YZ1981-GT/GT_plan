<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D2TabWriteoffCheck — 坏账准备转回（收回）、核销检查 D2-11
 *
 * 双段结构：转回区 + 核销区，各区添加/合计，与 D2-3 一致性告警。
 * 打磨基准：D1 检查型底稿（审计目标 / 全字段可编辑 / 行级复核 /
 *           逐行 AI 意见 / 总体分析+AI / 编制提示）
 */
import { inject, ref, toRef, type Ref } from 'vue'
import { useD2WriteoffCheck } from '../composables/useD2WriteoffCheck'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-11',
)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const {
  reversalRows,
  writeoffRows,
  reversalTotal,
  writeoffTotal,
  reversalConsistencyWarning,
  addRow,
  removeRow,
  updateCell,
} = useD2WriteoffCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const REASONABLE_OPTIONS = ['合理', '不合理', '待核实']

const { generateAndConfirm, aiAvailable } = useD2AiGenerate(toRef(props, 'wpId'))
const sectionAnalysis = ref('')

function loadSectionAnalysis(): void {
  sectionAnalysis.value = props.allResponses.get('D2-writeoff-section-analysis')?.remark || ''
}
loadSectionAnalysis()

function saveSectionAnalysis(): void {
  const item = { item_id: 'D2-writeoff-section-analysis', conclusion: null, remark: sectionAnalysis.value }
  props.allResponses.set('D2-writeoff-section-analysis', item)
  window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
}

async function onAiSectionAnalysis(): Promise<void> {
  const content = await generateAndConfirm('writeoff-analysis', sectionAnalysis.value, {
    reversalTotal: reversalTotal.value,
    writeoffTotal: writeoffTotal.value,
    reversalCount: reversalRows.value.length,
    writeoffCount: writeoffRows.value.length,
    consistencyWarning: reversalConsistencyWarning.value || '',
  }, 'AI 生成转回核销总体分析')
  if (content) { sectionAnalysis.value = content; saveSectionAnalysis() }
}

async function onAiRowComment(row: any): Promise<void> {
  const content = await generateAndConfirm('writeoff-analysis', row.auditorComment, {
    section: row.section === 'reversal' ? '转回' : '核销',
    debtorName: row.debtorName,
    amount: row.amount,
    reason: row.reason,
  }, `AI 生成审计意见 — ${row.debtorName || '该行'}`)
  if (content) updateCell(row.rowId, 'auditorComment', content)
}

async function handleImport(file: File): Promise<boolean> {
  await onImportFile(file)
  return false
}

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const GUIDANCE_TEXTS = [
  '坏账转回：应有客观证据表明减值损失减少（如债务人财务状况好转、实际收回），并与减值确认时的判断一致，防止跨期调节利润。',
  '坏账核销：须履行内部审批程序，取得核销依据（债务人破产/死亡/长期无法收回等法律文件），核销后应继续保留追索权登记（备查）。',
  '一致性核对：本表转回合计应与 D2-3 坏账准备明细表"本期转回"列勾稽一致，差异需查明原因。',
  '税务关注：核销的坏账损失税前扣除需符合税法规定并留存资料备查。',
]
</script>

<template>
  <div class="d2-tab-writeoff">
    <div class="tab-header">
      <h4>坏账准备转回、核销检查 D2-11</h4>
      <GtReviewTrigger section-id="D2-writeoff-header" />
    </div>

    <el-alert type="info" :closable="false" show-icon title="审计目标" class="audit-objective">
      <template #default>
        <p>核实坏账准备转回与核销的合规性与合理性，评价是否存在通过转回/核销调节利润的迹象，并与 D2-3 勾稽一致。</p>
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <el-button-group>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="handleImport" style="display:inline-block">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>

    <el-alert v-if="reversalConsistencyWarning" type="warning" :closable="false" show-icon class="consistency-alert">
      ⚠️ {{ reversalConsistencyWarning }}
    </el-alert>

    <!-- 转回区 -->
    <div class="section-block">
      <div class="section-header">
        <span class="section-title">坏账转回（收回）</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('reversal')">+ 添加转回</el-button>
      </div>
      <el-table :data="reversalRows" border size="small" max-height="420" style="width: 100%">
        <el-table-column label="债务人" min-width="130" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" placeholder="债务人" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
            <GtReviewDot row-prefix="D2-writeoff" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.amount" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'amount', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确认日期" width="140">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.originalDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" size="small" placeholder="原确认日期" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'originalDate', v || '')" />
            <span v-else>{{ row.originalDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转回原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" placeholder="转回原因" @change="(v: string) => updateCell(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审批文件" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.approvalDoc" size="small" placeholder="审批文件" @change="(v: string) => updateCell(row.rowId, 'approvalDoc', v)" />
            <span v-else>{{ row.approvalDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isReasonable" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'isReasonable', v || '')">
              <el-option v-for="o in REASONABLE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计意见" min-width="160">
          <template #default="{ row }">
            <div class="comment-cell">
              <el-input v-if="!isReadonly" :model-value="row.auditorComment" size="small" placeholder="审计意见" @change="(v: string) => updateCell(row.rowId, 'auditorComment', v)" />
              <span v-else>{{ row.auditorComment || '-' }}</span>
              <el-button v-if="aiAvailable && !isReadonly" link size="small" type="primary" @click="onAiRowComment(row)">🤖</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确定删除该行？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeRow(row.rowId)">
              <template #reference><el-button type="danger" link size="small">✕</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>暂无转回记录</template>
      </el-table>
      <div class="total-line">转回合计：{{ displayPrefs.fmtAmount(reversalTotal) }}</div>
    </div>

    <!-- 核销区 -->
    <div class="section-block">
      <div class="section-header">
        <span class="section-title">坏账核销</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('writeoff')">+ 添加核销</el-button>
      </div>
      <el-table :data="writeoffRows" border size="small" max-height="420" style="width: 100%">
        <el-table-column label="债务人" min-width="130" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" placeholder="债务人" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
            <GtReviewDot row-prefix="D2-writeoff" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.amount" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'amount', v || 0)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确认日期" width="140">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.originalDate" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" size="small" placeholder="原确认日期" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'originalDate', v || '')" />
            <span v-else>{{ row.originalDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" placeholder="核销原因" @change="(v: string) => updateCell(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审批文件" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.approvalDoc" size="small" placeholder="审批文件" @change="(v: string) => updateCell(row.rowId, 'approvalDoc', v)" />
            <span v-else>{{ row.approvalDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isReasonable" size="small" clearable placeholder="选择" style="width:100%" @change="(v: string) => updateCell(row.rowId, 'isReasonable', v || '')">
              <el-option v-for="o in REASONABLE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计意见" min-width="160">
          <template #default="{ row }">
            <div class="comment-cell">
              <el-input v-if="!isReadonly" :model-value="row.auditorComment" size="small" placeholder="审计意见" @change="(v: string) => updateCell(row.rowId, 'auditorComment', v)" />
              <span v-else>{{ row.auditorComment || '-' }}</span>
              <el-button v-if="aiAvailable && !isReadonly" link size="small" type="primary" @click="onAiRowComment(row)">🤖</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确定删除该行？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeRow(row.rowId)">
              <template #reference><el-button type="danger" link size="small">✕</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>暂无核销记录</template>
      </el-table>
      <div class="total-line">核销合计：{{ displayPrefs.fmtAmount(writeoffTotal) }}</div>
    </div>

    <!-- 总体分析 -->
    <div class="section-subtitle">
      转回核销总体分析
      <GtReviewTrigger section-id="D2-writeoff-section-analysis" />
      <el-button v-if="aiAvailable && !isReadonly" size="small" text type="primary" @click="onAiSectionAnalysis">🤖 AI 生成</el-button>
      <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D2-writeoff-section-analysis')">💬 复核</el-button>
    </div>
    <el-input v-model="sectionAnalysis" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="分析转回与核销的合理性、与 D2-3 的勾稽及对利润的影响..." @change="saveSectionAnalysis" />

    <details class="guidance-fold">
      <summary>📋 编制提示</summary>
      <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
    </details>
  </div>
</template>

<style scoped>
.d2-tab-writeoff { padding: 12px; }
.tab-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.tab-header h4 { margin: 0; font-size: 15px; }
.audit-objective { margin-bottom: 12px; }
.audit-objective p { margin: 0; font-size: var(--wp-font-size, 13px); line-height: 1.6; }
.tab-toolbar { display: flex; align-items: center; margin-bottom: 12px; gap: 12px; }
.consistency-alert { margin-bottom: 12px; }
.section-block { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.total-line { text-align: right; font-size: var(--wp-font-size, 13px); font-weight: 600; margin-top: 6px; padding: 4px 8px; background: #fafafa; border-radius: 4px; }
.comment-cell { display: flex; align-items: center; gap: 4px; }
.section-subtitle { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #303133; margin: 16px 0 10px; }
.guidance-fold { margin: 16px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-fold p { margin: 6px 0; line-height: 1.6; }
</style>
