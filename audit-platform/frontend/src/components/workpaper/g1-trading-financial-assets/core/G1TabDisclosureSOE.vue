<template>
  <div class="g1-disclosure-soe">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（国企）</h3>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip :value="noteChip" /></span>
        <el-tag size="small" type="info">八、2 / 八、3</el-tag>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly"
          @click="dis.refreshFromAdjudication(true)"
        >
          从审定表取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToDisclosureNotes"
        >
          同步至附注
        </el-button>
        <el-button size="small" @click="openReviewDialog('G1-note-soe')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：按国有企业附注格式披露交易性金融资产公允价值及衍生金融资产余额，核对与 G1-1 审定表（科目1501）勾稽，并同步至附注模块八、2 / 八、3。"
      class="objective-alert"
    />

    <el-alert
      v-if="dis.adjudicatedAmount.value !== null"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已联动审定表（1501）：期末 {{ fmt(dis.adjudicatedAmount.value) }}
      <template v-if="dis.adjudicatedPrior.value !== null">
        · 期初 {{ fmt(dis.adjudicatedPrior.value) }}
      </template>
      <template v-if="dis.lastSyncHint.value"> · 取数 {{ dis.lastSyncHint.value }}</template>
    </el-alert>

    <!-- 表1：交易性金融资产 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">交易性金融资产</span>
          <el-tag size="small" type="warning">对应附注 八、2</el-tag>
        </div>
      </template>
      <el-table
        :data="dis.tradingDisplayRows.value"
        border
        size="small"
        max-height="420"
        :row-class-name="tradingRowClass"
      >
        <el-table-column label="项目" min-width="320">
          <template #default="{ row }">
            <span :style="{ paddingLeft: `${(row.indent || 0) * 16}px` }" :class="{ 'is-total': row.kind === 'total', 'is-category': row.kind === 'category' }">
              {{ row.label }}
            </span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末公允价值" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.endAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateTradingAmount(row.rowKey, 'endAmount', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初公允价值" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateTradingAmount(row.rowKey, 'priorAmount', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">公允价值确认依据：</span>
        <el-input
          :model-value="dis.fvBasisNote.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="应披露公允价值确认依据..."
          @update:model-value="(v: string) => { dis.fvBasisNote.value = v }"
        />
      </div>
    </el-card>

    <!-- 表2：衍生金融资产 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">衍生金融资产</span>
          <div class="title-actions">
            <el-tag size="small" type="warning">对应附注 八、3</el-tag>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addDerivativeRow()">
              新增明细
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="derivativeTableData" border size="small" max-height="360" :row-class-name="derivRowClass">
        <el-table-column label="项目" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.label"
              size="small"
              @change="(v: string) => dis.updateDerivativeField(row.rowId, 'label', v)"
            />
            <span v-else :class="{ 'is-total': row.isTotal }">{{ row.label }}</span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateDerivativeField(row.rowId, 'endAmount', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateDerivativeField(row.rowId, 'priorAmount', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="产生原因 / 备注" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.reason"
              size="small"
              @change="(v: string) => dis.updateDerivativeField(row.rowId, 'reason', v)"
            />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal && !isReadonly"
              size="small"
              type="danger"
              link
              @click="dis.removeDerivativeRow(row.rowId)"
            >
              删
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-area">
        <span class="note-prefix">披露提示：</span>
        <el-input
          :model-value="dis.derivativeTipNote.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="披露金额较大的前十项及其产生的原因，其余汇总填列..."
          @update:model-value="(v: string) => { dis.derivativeTipNote.value = v }"
        />
      </div>
    </el-card>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :note="dis.noteText.value"
      @update:note="(v: string) => { dis.noteText.value = v }"
      :show-conclusion="false"
      note-title="附注说明"
      note-ai-section="disclosure-soe-note"
      note-placeholder="交易性金融资产附注披露说明（国企格式）..."
      note-hint="评价披露完整性、金额与审定表勾稽及列报格式；同步后写入附注八、2 / 八、3。"
      :note-min-rows="3"
      :related-context="{
        交易性期末合计: tradingTotalEnd,
        衍生期末合计: dis.derivativeTotal.value.endAmount,
        行数: dis.tradingRows.value.length + dis.derivativeRows.value.length,
      }"
    />

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>表结构对齐国企附注模板：交易性（分类/指定 × 债务·权益·其他）+ 衍生（前十大明细）。</li>
        <li>金额默认从 G1-1「账面余额（公允价值）」取数；分类行 = 交易性+划分为 FVTPL；衍生单独列示不进「其他」。</li>
        <li>「同步至附注」将两表分别写入附注模块八、2 / 八、3；文本变更同时发布 disclosure:note-text-updated。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useG1DisclosureSoe } from '../../composables/useG1DisclosureSoe'
import { buildG1SoeSyncPayloads } from '../../composables/g1DisclosureSyncPayload'
import { G1_NOTE_SECTION, resolveG1NoteSectionTarget } from '../../composables/g1NoteSectionMap'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
  applicableStandards?: string[]
}>(), {
  wpId: '',
  projectId: '',
  applicableStandards: () => [],
})

const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')
const noteChip = computed(() => {
  const t = resolveG1NoteSectionTarget('soe', props.applicableStandards)
  return t?.chipValue ?? `Note:${G1_NOTE_SECTION.soe.trading}`
})

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isSyncing = ref(false)

const dis = useG1DisclosureSoe({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const tradingTotalEnd = computed(() => {
  const total = dis.tradingDisplayRows.value.find((r) => r.rowKey === 'total')
  return total?.endAmount ?? 0
})

const derivativeTableData = computed(() => [
  ...dis.derivativeRows.value,
  {
    rowId: '__total__',
    label: '合计',
    endAmount: dis.derivativeTotal.value.endAmount,
    priorAmount: dis.derivativeTotal.value.priorAmount,
    reason: '',
    autoFilled: false,
    isTotal: true,
  },
])

function tradingRowClass({ row }: { row: { kind?: string } }) {
  if (row.kind === 'total') return 'row-total'
  if (row.kind === 'category') return 'row-category'
  return ''
}

function derivRowClass({ row }: { row: { isTotal?: boolean } }) {
  return row.isTotal ? 'row-total' : ''
}

function fmt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function syncToDisclosureNotes() {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payloads = buildG1SoeSyncPayloads(
    props.wpId || '',
    props.applicableStandards,
    dis.getSyncSnapshot(),
  )
  if (!payloads.length) {
    ElMessage.warning('当前项目准则不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    ElMessage.success(`已同步 ${rows} 行到附注模块「八、2 交易性金融资产 / 八、3 衍生金融资产」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}
</script>

<style scoped>
.g1-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-disclosure-soe :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert, .sync-hint { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 16px; }
.card-title-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.card-title { font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 8px; }
.note-area { margin-top: 12px; display: flex; gap: 8px; align-items: flex-start; }
.note-prefix { flex-shrink: 0; color: #606266; font-size: 12px; line-height: 32px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.is-total, .is-category { font-weight: 600; }
.auto-badge { margin-left: 6px; }
:deep(.row-total) { font-weight: 600; background: #f5f7fa; }
:deep(.row-category) { background: #fafafa; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
