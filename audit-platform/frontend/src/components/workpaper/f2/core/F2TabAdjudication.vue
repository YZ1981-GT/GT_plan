<template>
  <div class="f2-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按存货类别审定原值与跌价准备，净值 = 原值 − 跌价准备（自动计算，只读）。</p>
        <p>2. 依《企业会计准则第 1 号——存货》，存货期末按成本与可变现净值孰低计量，跌价准备应计提充分。</p>
        <p>3. 原值区数据自 F2-3~F2-13 各明细表合计自动聚合；账项调整取自 F2-14 调整分录。</p>
        <p>4. 底部试算差异为 0 方可发布审定数并回写试算平衡表。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确认存货期末余额的存在、完整与准确，验证其以成本与可变现净值孰低计量，跌价准备计提充分。"
    />

    <!-- 交叉验证警告 -->
    <el-alert
      v-if="detailCrossValidation"
      type="warning"
      :title="detailCrossValidation"
      :closable="false"
      show-icon
      class="cross-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button type="primary" size="small" :disabled="isReadonly" @click="publishAdjudicated()">
          发布审定数
        </el-button>
        <el-button size="small" plain :loading="grossPull.loading.value" :disabled="isReadonly" @click="openGrossBringIn">
          <el-icon><Download /></el-icon>带入调整·原值
        </el-button>
        <el-button size="small" plain :loading="impairmentPull.loading.value" :disabled="isReadonly" @click="openImpairmentBringIn">
          <el-icon><Download /></el-icon>带入调整·跌价
        </el-button>
        <F2ReviewChip section-id="F2-1-gross" />
        <el-tag size="small" type="info">数据来源：F2-3~13 明细自动聚合至原值区</el-tag>
      </div>
      <div class="toolbar-right">
        <el-dropdown trigger="click" @command="handleIeCommand">
          <el-button size="small" plain>导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import" :disabled="isReadonly">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="ieFileInput" type="file" accept=".xlsx" style="display:none" @change="onIeFileChange" />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ grossRows.length }} 类</el-tag>
      </div>
    </div>

    <el-collapse v-model="activeBlocks">
      <el-collapse-item title="一、存货原值" name="gross">
        <F2AdjudicationBlockTable
          :rows="grossRows"
          :subtotal="grossSubtotal"
          block="gross"
          :project-id="projectId"
          :readonly="isReadonly"
          :wp-id="wpId"
          :all-responses="allResponses"
          @update="updateCell"
        />
      </el-collapse-item>
      <el-collapse-item title="二、存货跌价准备" name="impairment">
        <F2AdjudicationBlockTable
          :rows="impairmentRows"
          :subtotal="impairmentSubtotal"
          block="impairment"
          :project-id="projectId"
          :readonly="isReadonly"
          :wp-id="wpId"
          :all-responses="allResponses"
          @update="updateCell"
        />
      </el-collapse-item>
      <el-collapse-item title="三、存货净值（自动计算）" name="net">
        <F2AdjudicationBlockTable
          :rows="netRows"
          :subtotal="netSubtotal"
          block="gross"
          readonly
        />
      </el-collapse-item>
    </el-collapse>

    <!-- 存货净额行（Req 5 — 净额 = 余额 − 跌价准备1471，跌价变动自动重算） -->
    <div class="inventory-net-row">
      <span class="net-label">存货净额 = 存货余额合计 − 跌价准备(1471)</span>
      <div class="net-values">
        <span class="net-item">余额合计：<strong>{{ inventoryNetRow.totalBalance.toLocaleString() }}</strong></span>
        <span class="net-sep">−</span>
        <span class="net-item">跌价准备：<strong>{{ inventoryNetRow.impairmentProvision.toLocaleString() }}</strong></span>
        <span class="net-sep">=</span>
        <el-tag type="primary" size="default" effect="dark">
          净额：{{ inventoryNetRow.netAmount.toLocaleString() }}
        </el-tag>
      </div>
    </div>

    <!-- 核对行 -->
    <div class="tb-check-row">
      <span class="tb-label">与试算平衡表核对（存货科目）：</span>
      <el-input-number
        :model-value="trialBalanceAmount"
        size="small"
        :controls="false"
        :disabled="isReadonly"
        @change="(v: number | undefined) => updateTrialBalanceAmount(v ?? 0)"
      />
      <el-tag v-if="trialBalanceDiff === 0" type="success" size="small">核对一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ trialBalanceDiff.toLocaleString() }}</el-tag>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card audit-note-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F2-2" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateNote">🤖 AI辅助</el-button>
            <F2ReviewChip section-id="F2-1-note" />
          </div>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入审计说明..." />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateConclusion">🤖 AI辅助</el-button>
            <F2ReviewChip section-id="F2-1-conclusion" />
          </div>
        </div>
        <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="isReadonly" placeholder="请输入审计结论..." />
      </div>
    </el-card>

    <AdjudicationBringInDialog
      v-model="grossBringInVisible"
      :matches="grossPull.matches.value"
      :row-options="grossBringInRowOptions"
      subject-label="存货原值（1401-1412）"
      :loading="grossPull.loading.value"
      @apply="(p) => applyBringIn('gross', p)"
    />
    <AdjudicationBringInDialog
      v-model="impairmentBringInVisible"
      :matches="impairmentPull.matches.value"
      :row-options="impairmentBringInRowOptions"
      subject-label="存货跌价准备（1471）"
      :loading="impairmentPull.loading.value"
      @apply="(p) => applyBringIn('impairment', p)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { useF2Adjudication, type F2BlockKey } from '../../composables/useF2Adjudication'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationAdjustmentPull } from '../../composables/useAdjudicationAdjustmentPull'
import { F2_ROW_KEY_ACCOUNT, F2_IMPAIRMENT_ACCOUNT } from '../../composables/useF2CrossSheet'
import { useF2ImportExport } from '../../composables/useWorkpaperImportExport'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { useF2CrossSheet } from '../../composables/useF2CrossSheet'
import type { TbValuesEntry } from '../../composables/useF2Adjudication'
import F2AdjudicationBlockTable from './F2AdjudicationBlockTable.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import AdjudicationBringInDialog, { type AdjudicationAllocation } from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet?: ReturnType<typeof useF2CrossSheet>
  /** 后端 render 输出的 tb_values（各存货类别 期初/期末未审，来自 tb_balance 1401~1471）。
   *  供 useF2Adjudication.seedFromTbValues 在无持久化时自动预填审定表（四表入库刷新即有数据）。 */
  tbValues?: Record<string, TbValuesEntry> | null
  /** 存货净额 TB 核对标量（BS-010 trial_balance），供审定表「试算平衡表数」只读回退 seed */
  tbAmount?: number | null
}>()

const activeBlocks = ref(['gross', 'impairment'])

const {
  grossRows,
  impairmentRows,
  netRows,
  grossSubtotal,
  impairmentSubtotal,
  netSubtotal,
  inventoryNetRow,
  trialBalanceAmount,
  trialBalanceDiff,
  detailCrossValidation,
  auditNote,
  conclusion,
  updateCell,
  updateTrialBalanceAmount,
  publishAdjudicated,
} = useF2Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  crossSheet: props.crossSheet,
  tbValues: toRef(props, 'tbValues'),
  tbAmountSeed: toRef(props, 'tbAmount'),
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateNote() {
  const text = await generateAndConfirm(
    'adj-note',
    auditNote.value,
    { netTotal: netSubtotal.value.endAudited, trialBalanceDiff: trialBalanceDiff.value },
    'AI 生成 · 存货审计说明',
  )
  if (text) auditNote.value = text
}

async function generateConclusion() {
  const text = await generateAndConfirm(
    'adj-conclusion',
    conclusion.value,
    { netTotal: netSubtotal.value.endAudited, trialBalanceDiff: trialBalanceDiff.value },
    'AI 生成 · 存货审计结论',
  )
  if (text) conclusion.value = text
}

// ─── 从集中登记带入调整（专门接入：原值 gross[存货科目 debit] + 跌价 impairment[1471 credit] 两独立实例） ─
// F2 审定表"账项调整"为单列净额（非 AJE/RJE 双列），故不复用共享 helper.apply（双列快照会覆盖单列），
// 改自包含 apply：弹窗已按目标行聚合，net = aje + rje 一次性累加到该行 adjustment（安全，无覆盖）。
const GROSS_ACCOUNT_CODES = Object.values(F2_ROW_KEY_ACCOUNT).filter(c => c !== F2_IMPAIRMENT_ACCOUNT)
const auditYear = useAuditContext().year as any

const grossPull = useAdjudicationAdjustmentPull({
  projectId: toRef(props, 'projectId') as any,
  year: auditYear,
  subjectPrefix: GROSS_ACCOUNT_CODES,
  direction: 'debit',
})
const impairmentPull = useAdjudicationAdjustmentPull({
  projectId: toRef(props, 'projectId') as any,
  year: auditYear,
  subjectPrefix: [F2_IMPAIRMENT_ACCOUNT],
  direction: 'credit',
})

const grossBringInVisible = ref(false)
const impairmentBringInVisible = ref(false)

// 原值目标行=除跌价准备外的存货类别；跌价目标行=跌价准备单行
const grossBringInRowOptions = computed(() =>
  grossRows.value
    .filter(r => r.rowKey !== 'impairment-provision')
    .map(r => ({ rowKey: r.rowKey, name: r.label })),
)
const impairmentBringInRowOptions = computed(() =>
  impairmentRows.value
    .filter(r => r.rowKey === 'impairment-provision')
    .map(r => ({ rowKey: r.rowKey, name: r.label })),
)

async function openGrossBringIn(): Promise<void> {
  if (props.isReadonly) return
  await grossPull.load()
  if (!grossPull.matches.value.length) {
    ElMessage.info('未找到命中存货原值科目的集中调整分录')
    return
  }
  grossBringInVisible.value = true
}
async function openImpairmentBringIn(): Promise<void> {
  if (props.isReadonly) return
  await impairmentPull.load()
  if (!impairmentPull.matches.value.length) {
    ElMessage.info('未找到命中跌价准备(1471)的集中调整分录')
    return
  }
  impairmentBringInVisible.value = true
}

function applyBringIn(block: F2BlockKey, payload: { allocations: AdjudicationAllocation[] }): void {
  const rows = block === 'gross' ? grossRows.value : impairmentRows.value
  for (const a of payload.allocations) {
    const row = rows.find(r => r.rowKey === a.rowKey)
    if (!row) continue
    const net = (a.aje || 0) + (a.rje || 0)
    if (net === 0) continue
    updateCell(block, a.rowKey, 'adjustment', Math.round((row.adjustment + net) * 100) / 100)
  }
  ElMessage.success('已带入调整分录至账项调整列，点「发布审定数」后联动披露/附注（若 F2-14 已录调整分录将以其为准）')
}

// ─── 导入导出 F2-1 ─────────────────────────────────────────────────
const f2Ie = useF2ImportExport({ wpId: toRef(props, 'wpId') as Ref<string> })

async function handleIeCommand(cmd: string) {
  if (cmd === 'export-template') {
    await f2Ie.exportTemplate('F2-1')
  } else if (cmd === 'export-data') {
    await f2Ie.exportData('F2-1')
  } else if (cmd === 'import') {
    // 触发隐藏 file input
    ieFileInput.value?.click()
  }
}

const ieFileInput = ref<HTMLInputElement | null>(null)

async function onIeFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  const result = await f2Ie.importData('F2-1', file)
  if (result) {
    // 导入成功后重载数据
    ElMessage.success(`成功导入 ${result.rowCount} 行 / ${result.fieldCount} 字段`)
    // 触发父级重载（通过 emit 或直接 reload allResponses）
    emit('reload')
  }
}

const emit = defineEmits<{
  reload: []
}>()
</script>

<style scoped>
.f2-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-adjudication :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-adjudication :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.cross-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.tb-check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin: 16px 0;
  font-size: var(--wp-font-size, 13px);
}
.tb-label { color: #909399; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.inventory-net-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 14px;
  margin: 14px 0;
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f9ff 100%);
  border: 1px solid #b3d8ff;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
}
.net-label { color: #606266; font-weight: 500; }
.net-values { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.net-item { color: #303133; }
.net-sep { color: #909399; font-weight: 600; }
</style>
