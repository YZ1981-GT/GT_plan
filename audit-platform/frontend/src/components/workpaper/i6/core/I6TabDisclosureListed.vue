<template>
  <div class="i6-disclosure-listed">
    <div class="section-header">
      <span class="section-title">研发费用附注披露（上市公司）</span>
      <div class="section-actions">
        <GtIndexChip :value="disc.noteTarget.value.chipValue" :context-project-id="projectId" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="disc.syncAllFromWorkpaper(false)">
          一键 SUMIF
        </el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="disc.syncFromDetail(false)">
          从 I6-2 取数
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="disc.syncFromAdjudication(false)">
          从 I6-1 取数
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="disc.syncFromDetail(true)">强制覆盖</el-button>
        <el-button
          size="small"
          type="success"
          :loading="disc.isSyncing.value"
          :disabled="isReadonly || !projectId"
          @click="disc.syncToNotes()"
        >同步到附注 {{ disc.noteTarget.value.sectionId }}</el-button>
        <el-button size="small" type="default" text @click="handleReview('category')">💬</el-button>
      </div>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> SUMIF 自 I6-2 按费用性质汇总本期/上期发生额</div>
        <div class="guide-step"><span class="step-num">②</span> 与 I6-1 审定合计勾稽（损益类取发生额）</div>
        <div class="guide-step"><span class="step-num">③</span> 费用化/资本化划分说明（联动 I2）</div>
        <div class="guide-step"><span class="step-num">④</span> 「同步到附注」写入 §五、66</div>
      </div>
    </div>

    <div class="methodology-block">
      <div class="methodology-title">CAS 附注披露要求（上市公司版）</div>
      <div class="methodology-content">
        按费用性质列示研发费用本期与上期发生额。科目6602（借方/损益类）取发生额非余额。
        财会〔2019〕6号：含费用化研发支出及计入管理费用的自行开发无形资产摊销。
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实附注披露分类明细完整、本期与上期发生额与 I6-1/I6-2 勾稽一致，并同步至附注模块「五、66 研发费用」。"
      class="objective-alert"
    />

    <el-alert
      v-if="disc.reconcileSummary.value.severity !== 'ok'"
      :type="disc.reconcileSummary.value.severity === 'error' ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="reconcile-alert"
      :title="disc.reconcileSummary.value.headline"
    >
      <template v-if="disc.reconcileSummary.value.itemDiffs.length" #default>
        <ul class="reconcile-item-list">
          <li v-for="d in disc.reconcileSummary.value.itemDiffs" :key="d.item">
            {{ d.item }}：披露 {{ fmtAmt(d.disclosureAmount) }} vs I6-2 {{ fmtAmt(d.referenceAmount) }}，差 {{ fmtAmt(d.diff) }}
          </li>
        </ul>
      </template>
    </el-alert>

    <div v-else-if="disc.reconcileSummary.value.vsAdj.hasBoth" class="reconcile-bar reconcile-ok">
      勾稽一致：披露 {{ fmtAmt(disc.reconcileSummary.value.vsAdj.disclosureTotal) }} = I6-1 审定 {{ fmtAmt(disc.reconcileSummary.value.vsAdj.adjudicatedTotal) }}
    </div>

    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">研发费用（按费用性质列示）</span>
          <el-button v-if="!isReadonly" size="small" @click="handleAdd">+ 行</el-button>
        </div>
      </template>
      <el-table :data="disc.rows.value" border stripe size="small" class="matrix-table">
        <el-table-column prop="item" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item" size="small" @change="(v: string) => disc.updateCell(row.rowId, 'item', v)" />
            <span v-else>{{ row.item }}</span>
            <el-tag v-if="row.isAutoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="本期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentAmount" :controls="false" size="small" @change="(v: number) => disc.updateCell(row.rowId, 'currentAmount', v)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" :controls="false" size="small" @change="(v: number) => disc.updateCell(row.rowId, 'priorAmount', v)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.currentAmount - row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'rate-warn': isHighRate(row) }">{{ fmtPct(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => disc.updateCell(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtPctOfTotal(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="disc.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="totals-row">
        <span class="totals-label">合计</span>
        <span class="totals-value">本期: {{ fmtAmt(disc.totals.value.currentAmount) }}</span>
        <span class="totals-value">上期: {{ fmtAmt(disc.totals.value.priorAmount) }}</span>
      </div>
    </el-card>

    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">费用化与资本化说明</span>
          <el-button size="small" type="primary" link :loading="disc.isAiGenerating.value" :disabled="isReadonly" @click="handleAi('capitalization')">AI</el-button>
        </div>
      </template>
      <el-input
        :model-value="disc.capitalizationNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="费用化金额(I6)、资本化金额(I2)及其占比说明…"
        @change="disc.saveCapitalizationNote"
      />
    </el-card>

    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">重大研发项目进展</span>
          <el-button size="small" type="primary" link :loading="disc.isAiGenerating.value" :disabled="isReadonly" @click="handleAi('projects')">AI</el-button>
        </div>
      </template>
      <el-input
        :model-value="disc.projectsNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="列示重大研发项目名称、投入金额、完成进度…"
        @change="disc.saveProjectsNote"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>对齐源表「附注披露（上市公司）」：项目 | 本期发生额 | 上期发生额。</li>
        <li>公式：SUMIF(I6-2.类别, 项目, 本期审定/上期审定)。</li>
        <li>同步附注写入 note_template §五、66「研发费用（按费用性质列示）」。</li>
        <li>可按需增行说明增减变动因素（源表蓝色提示行）。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI6Disclosure, type I6DisclosureRow } from '../../composables/useI6Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{ 'save': [itemId: string, value: any] }>()

const variant = ref<'listed'>('listed')
const disc = useI6Disclosure(
  computed(() => props.wpId),
  computed(() => props.projectId),
  computed(() => props.allResponses),
  {
    variant,
    applicableStandards: () => props.applicableStandards,
    onSave: (itemId, value) => emit('save', itemId, typeof value === 'string' ? value : JSON.stringify(value)),
  },
)

async function handleAdd(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入费用性质/项目名称', '新增行', {
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    disc.addRow(value)
  } catch { /* cancel */ }
}

async function handleAi(section: 'capitalization' | 'projects'): Promise<void> {
  const text = await disc.generateNoteText(section)
  if (!text) return
  if (section === 'capitalization') disc.saveCapitalizationNote(text)
  else disc.saveProjectsNote(text)
  ElMessage.success('已生成说明文字')
}

function handleReview(_section: string): void { /* inject via parent if needed */ }

function isHighRate(row: I6DisclosureRow): boolean {
  if (!row.priorAmount) return false
  return Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount) > 0.3
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(row: I6DisclosureRow): string {
  if (!row.priorAmount) return '-'
  return ((row.currentAmount - row.priorAmount) / Math.abs(row.priorAmount) * 100).toFixed(1) + '%'
}

function fmtPctOfTotal(val: number): string {
  const total = disc.totals.value.currentAmount
  if (!total || !val) return '-'
  return ((val / total) * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.i6-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; }
.section-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }
.methodology-block { border-left: 4px solid #d97706; background: #fffbeb; padding: 12px 16px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.7; }
.methodology-title { font-weight: 600; color: #78350f; margin-bottom: 4px; }
.objective-alert { margin-bottom: 12px; }
.reconcile-bar { display: flex; gap: 16px; font-size: 12px; margin-bottom: 12px; color: var(--el-text-color-secondary); }
.reconcile-bar.reconcile-ok { color: var(--el-color-success); }
.reconcile-alert { margin-bottom: 12px; }
.reconcile-item-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; }
.text-danger { color: var(--el-color-danger); }
.disclosure-card { margin-bottom: 16px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.matrix-table { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.amount-cell { font-variant-numeric: tabular-nums; }
.auto-badge { margin-left: 4px; }
.rate-warn { color: #d97706; font-weight: 600; background: #fefce8; padding: 1px 4px; border-radius: 2px; }
.totals-row { display: flex; align-items: center; gap: 16px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; font-size: 12px; }
.totals-label { font-weight: 600; }
.totals-value { font-variant-numeric: tabular-nums; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; color: var(--el-text-color-primary); }
.compile-hint ol { padding-left: 20px; margin: 8px 0 0; }
.compile-hint li { margin-bottom: 4px; line-height: 1.5; }
</style>
