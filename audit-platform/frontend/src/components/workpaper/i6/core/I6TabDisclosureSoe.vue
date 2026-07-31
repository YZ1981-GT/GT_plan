<template>
  <div class="i6-disclosure-soe">
    <div class="section-header">
      <span class="section-title">研发费用附注披露（国有企业）</span>
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
          @click="syncToDisclosureNotes()"
        >同步到附注 {{ disc.noteTarget.value.sectionId }}</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
      </div>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 按费用性质汇总本期/上期发生额</div>
        <div class="guide-step"><span class="step-num">②</span> 与 I6-1 审定合计勾稽</div>
        <div class="guide-step"><span class="step-num">③</span> 补充费用化/资本化及重大项目说明</div>
        <div class="guide-step"><span class="step-num">④</span> 「同步到附注」写入 §八、67</div>
      </div>
    </div>

    <div class="methodology-block">
      <div class="methodology-title">附注披露（国有企业版）</div>
      <div class="methodology-content">
        国有企业应披露研发费用按费用性质分类的本期与上期发生额。科目6602（损益类/借方）取发生额非余额。
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实附注披露分类明细完整、发生额与 I6-1/I6-2 勾稽一致，并同步至附注模块「八、67 研发费用」。"
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
          <span class="section-title">补充说明</span>
          <el-button size="small" type="primary" link :loading="disc.isAiGenerating.value" :disabled="isReadonly" @click="handleAi">AI</el-button>
        </div>
      </template>
      <el-input
        :model-value="disc.supplementNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="费用化与资本化划分说明、重大项目概况、增减变动因素…"
        @change="disc.saveSupplementNote"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>对齐源表「附注披露（国有企业）」：项目 | 本期发生额 | 上期发生额。</li>
        <li>数据自 I6-2 SUMIF 或 I6-1 审定引用，合计须与审定表一致。</li>
        <li>同步附注写入 note_template §八、67「研发费用」。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onBeforeUnmount, watch } from 'vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
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

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'I6', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const variant = ref<'soe'>('soe')
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

async function handleAi(): Promise<void> {
  const text = await disc.generateNoteText('supplement')
  if (text) {
    disc.saveSupplementNote(text)
    ElMessage.success('已生成补充说明')
  }
}

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

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

async function syncToDisclosureNotes() {
  await disc.syncToNotes()
}

// [auto-sync] 监听实际数据（历史实现是 syncToDisclosureNotes 里调度自己 → 800ms 周期无限 POST，
// 且让 disclosureAutoSyncCoverage 守卫误判为「已接自动同步」= 假接入）。
// 🔴 不加 `_xxxMounted` 一次性防护：Vue watch 默认 immediate:false，挂载本身不触发；
//    该防护会吞掉「切走再切回后的第一次编辑」（平台铁律）。
watch(
  [
    () => disc.rows,
    () => disc.capitalizationNote,
    () => disc.projectsNote,
    () => disc.supplementNote,
    () => disc.auditNote,
    () => disc.auditConclusion,
  ],
  () => autoSync.scheduleAutoSync(syncToDisclosureNotes),
  { deep: true },
)

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.i6-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.reconcile-bar { font-size: 12px; margin-bottom: 12px; color: var(--el-text-color-secondary); }
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
