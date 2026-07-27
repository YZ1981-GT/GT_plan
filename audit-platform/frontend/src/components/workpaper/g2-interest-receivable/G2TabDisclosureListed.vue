<template>
  <div class="g2-disclosure-listed" data-testid="g2-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip :value="noteChip" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">五、8 · 应收利息</el-tag>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly"
          @click="dis.refreshFromSources(true)"
        >
          从审定/明细取数
        </el-button>
        <el-button
          size="small"
          plain
          :disabled="isReadonly"
          @click="onPullOverdue"
        >
          从 G2-6 取数
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
        <el-button size="small" @click="openReviewDialog('G2-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：按上市公司附注格式披露应收利息分类、重要逾期及 ECL 三阶段坏账变动，与 G2-1 审定勾稽，并回写附注五、8（其他应收款下应收利息明细）。"
      class="objective-alert"
    />

    <!-- Excel 合计数交叉索引：M1-1 → K1-1 / Note:五、8 -->
    <div class="combined-cross-ref" role="navigation" aria-label="合计数披露交叉索引">
      <span class="cross-ref-text">
        【其他应收款、应收股利与应收利息的合计数披露详见
        <button
          type="button"
          class="legacy-index-link"
          title="Excel 索引 M1-1 → 跳转其他应收款合计数底稿 K1-1"
          @click="jumpCombinedWp"
        >M1-1</button>
        】
      </span>
      <div class="cross-ref-chips">
        <span class="chip-hint">平台索引</span>
        <GtIndexChip
          :value="combinedWpChip"
          :context-project-id="projectId"
          context="其他应收款审定表 — 合计数（应收利息+应收股利+其他应收款项）归集"
        />
        <GtIndexChip
          :value="combinedNoteChip"
          :context-project-id="projectId"
          context="附注五、8 其他应收款 — 汇总表含应收利息/应收股利/其他应收款"
        />
      </div>
    </div>

    <el-alert
      v-if="dis.adjudicatedAmount.value !== null"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已联动审定表（1132）：净值期末 {{ fmt(dis.adjudicatedAmount.value) }}
      <template v-if="dis.adjudicatedPrior.value !== null">
        · 上年年末 {{ fmt(dis.adjudicatedPrior.value) }}
      </template>
      <template v-if="dis.lastSyncHint.value"> · 取数 {{ dis.lastSyncHint.value }}</template>
    </el-alert>

    <el-alert
      v-if="!dis.provisionTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`坏账勾稽差异：表①坏账准备 ${fmt(dis.provisionTieOut.value.classProvision)} ≠ 表③期末合计 ${fmt(dis.provisionTieOut.value.eclClosing)}（差额 ${fmt(dis.provisionTieOut.value.diff)}）`"
    />

    <!-- ① 应收利息分类 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">① 应收利息分类</span>
          <el-tag size="small" type="warning">对应附注 五、8</el-tag>
        </div>
      </template>
      <el-table
        :data="dis.classDisplayRows.value"
        border
        size="small"
        :row-class-name="classRowClass"
      >
        <el-table-column label="项目" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'is-total': row.kind === 'total' || row.kind === 'subtotal' }">
              {{ row.label }}
            </span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.endAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateClassAmount(row.rowKey, 'endAmount', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateClassAmount(row.rowKey, 'priorAmount', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="template-tip">
        提示：本表仅反映截至资产负债表日已到期应收但尚未收到的利息；采用实际利率法计算的利息应包含在相应金融工具的账面余额中。
      </p>
    </el-card>

    <!-- ② 重要逾期利息 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">② 重要逾期利息</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addOverdueRow()">
            新增行
          </el-button>
        </div>
      </template>
      <el-table :data="overdueTableData" border size="small" max-height="360" :row-class-name="overdueRowClass">
        <el-table-column label="借款单位" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.borrower"
              size="small"
              @change="(v: string) => dis.updateOverdueField(row.id, 'borrower', v)"
            />
            <span v-else :class="{ 'is-total': row.isTotal }">{{ row.borrower || '合计' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endAmount"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateOverdueField(row.id, 'endAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="逾期时间（月）" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.overdueMonths === '' ? undefined : Number(row.overdueMonths)"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateOverdueField(row.id, 'overdueMonths', v ?? '')"
            />
            <span v-else>{{ row.isTotal ? '' : row.overdueMonths || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="逾期原因" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.overdueReason"
              size="small"
              @change="(v: string) => dis.updateOverdueField(row.id, 'overdueReason', v)"
            />
            <span v-else>{{ row.overdueReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否发生减值及其判断依据" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.impairmentBasis"
              size="small"
              @change="(v: string) => dis.updateOverdueField(row.id, 'impairmentBasis', v)"
            />
            <span v-else>{{ row.impairmentBasis }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              size="small"
              type="danger"
              link
              @click="dis.removeOverdueRow(row.id)"
            >
              删
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ③ 坏账准备计提情况 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">③ 坏账准备计提情况</span>
          <el-tag size="small">ECL 三阶段</el-tag>
        </div>
      </template>
      <p class="template-tip merge-tip">
        说明期末处于第一、二、三阶段的应收利息坏账准备计提情况；也可在其他应收款项下合并披露，并索引至
        <GtIndexChip
          value="Note:五、8"
          :context-project-id="projectId"
          context="附注五、8（3）③ 其他应收款坏账准备"
        />
        。
      </p>
      <el-table
        :data="dis.eclDisplayRows.value"
        border
        size="small"
        :row-class-name="eclRowClass"
      >
        <el-table-column label="坏账准备" min-width="160">
          <template #default="{ row }">
            <span
              :style="{ paddingLeft: row.kind === 'indent' ? '16px' : '0' }"
              :class="{ 'is-total': row.rowKey === 'closing', 'is-header': row.kind === 'header' }"
            >
              {{ row.label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="第一阶段" width="120" align="right">
          <template #header>
            <div class="stage-header">第一阶段</div>
            <div class="stage-sub">未来12个月 ECL</div>
          </template>
          <template #default="{ row }">
            <template v-if="row.kind === 'header'">—</template>
            <el-input-number
              v-else-if="row.editable && !isReadonly"
              :model-value="row.stage1"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateEclAmount(row.rowKey, 'stage1', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.stage1) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="第二阶段" width="120" align="right">
          <template #header>
            <div class="stage-header">第二阶段</div>
            <div class="stage-sub">整个存续期 ECL（未减值）</div>
          </template>
          <template #default="{ row }">
            <template v-if="row.kind === 'header'">—</template>
            <el-input-number
              v-else-if="row.editable && !isReadonly"
              :model-value="row.stage2"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateEclAmount(row.rowKey, 'stage2', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.stage2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="第三阶段" width="120" align="right">
          <template #header>
            <div class="stage-header">第三阶段</div>
            <div class="stage-sub">整个存续期 ECL（已减值）</div>
          </template>
          <template #default="{ row }">
            <template v-if="row.kind === 'header'">—</template>
            <el-input-number
              v-else-if="row.editable && !isReadonly"
              :model-value="row.stage3"
              size="small"
              :controls="false"
              style="width: 100%"
              @change="(v: number) => dis.updateEclAmount(row.rowKey, 'stage3', v)"
            />
            <span v-else class="amount-cell">{{ fmt(row.stage3) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合计" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.kind === 'header'">—</span>
            <span v-else class="amount-cell is-total">{{ fmt(dis.eclRowTotal(row)) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :note="dis.noteText.value"
      @update:note="(v: string) => { dis.noteText.value = v }"
      :show-conclusion="false"
      note-title="附注披露说明"
      note-ai-section="disclosure-listed-note"
      :related-context="{
        科目: '1132',
        披露类型: '上市公司',
        分类合计: classTotalEnd,
        坏账准备: dis.provisionTieOut.value.classProvision,
      }"
      note-placeholder="上市公司应收利息附注：分类构成、逾期情况、ECL 阶段划分依据，并说明与审定数及合计数（K1-1 / 五、8）勾稽…"
      note-hint="保存后发布 disclosure:note-text-updated；「同步至附注」写入五、8 子表。合计数见 M1-1→K1-1。"
      :note-min-rows="4"
    />

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>表结构对齐上市附注模板：分类（定期存款/委托贷款/债券/其他）→ 逾期 → ECL 三阶段变动。</li>
        <li>分类金额优先由 G2-2 明细按投资种类 SUMIF 归集；坏账自 G2-1 审定带入。</li>
        <li>小计/合计、表③期末余额为公式列；表①「减：坏账准备」应与表③期末合计一致。</li>
        <li>Excel「详见 M1-1」为合计数旧索引，平台跳转 <strong>K1-1</strong>（其他应收款）与附注 <strong>五、8</strong>。</li>
        <li>「同步至附注」将三张子表写入附注模块五、8；文本变更同步发布 EventBus。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G2TabDisclosureListed — 附注披露信息（上市公司）
 * 对齐源 Excel + note_template_listed §五、8 应收利息子表；
 * 合计数交叉索引：Excel M1-1 → wp:K1-1 + Note:五、8
 */
import { computed, inject, onBeforeUnmount, ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter, useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { useG2DisclosureListed } from '../composables/useG2DisclosureListed'
import { buildG2ListedSyncPayloads } from '../composables/g2DisclosureSyncPayload'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import {
  G2_COMBINED_DISCLOSURE_INDEX,
  G2_NOTE_SECTION,
  resolveG2NoteSectionTarget,
} from '../composables/g2NoteSectionMap'
import type { ChecklistResponse } from '../composables/useF1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import G2AuditTextCards from './G2AuditTextCards.vue'

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
const router = useRouter()
const route = useRoute()

const noteTarget = computed(() => resolveG2NoteSectionTarget('listed', props.applicableStandards))
const noteChip = computed(() => noteTarget.value?.chipValue ?? `Note:${G2_NOTE_SECTION.listed}`)
const combinedWpChip = computed(() => noteTarget.value?.combinedWpChip ?? `wp:${G2_COMBINED_DISCLOSURE_INDEX.wpCode}`)
const combinedNoteChip = computed(() => noteTarget.value?.combinedNoteChip ?? `Note:${G2_NOTE_SECTION.listed}`)

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isSyncing = ref(false)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

const dis = useG2DisclosureListed({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const classTotalEnd = computed(() => {
  const total = dis.classDisplayRows.value.find((r) => r.rowKey === 'total')
  return total?.endAmount ?? 0
})

const overdueTableData = computed(() => [
  ...dis.overdueRows.value,
  {
    id: '__total__',
    borrower: '合计',
    endAmount: dis.overdueEndTotal.value,
    overdueMonths: '' as const,
    overdueReason: '',
    impairmentBasis: '',
    isTotal: true,
  },
])

function classRowClass({ row }: { row: { kind?: string } }) {
  if (row.kind === 'total' || row.kind === 'subtotal') return 'row-total'
  if (row.kind === 'provision') return 'row-provision'
  return ''
}

function overdueRowClass({ row }: { row: { isTotal?: boolean } }) {
  return row.isTotal ? 'row-total' : ''
}

function eclRowClass({ row }: { row: { rowKey?: string; kind?: string } }) {
  if (row.rowKey === 'closing') return 'row-total'
  if (row.kind === 'header') return 'row-header'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  if (v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Excel M1-1 点击 → 优先跳转 K1-1 底稿 */
function jumpCombinedWp() {
  const pid = projectId.value || (route.params.projectId as string) || ''
  if (!pid) {
    ElMessage.warning('缺少项目上下文，无法跳转合计数底稿')
    return
  }
  void router.push({
    name: route.name || undefined,
    params: { ...route.params, projectId: pid },
    query: {
      ...route.query,
      wpCode: G2_COMBINED_DISCLOSURE_INDEX.wpCode,
      sheet: 'K1-1',
    },
  }).catch(() => {
    void router.push({
      path: route.path,
      query: { ...route.query, wpCode: G2_COMBINED_DISCLOSURE_INDEX.wpCode },
    })
  })
  ElMessage.info(`正在跳转合计数底稿 ${G2_COMBINED_DISCLOSURE_INDEX.wpCode}（Excel 索引 ${G2_COMBINED_DISCLOSURE_INDEX.excelLegacy}）`)
}

function onPullOverdue() {
  const { pulled } = dis.pullOverdueFromG26(true)
  if (!pulled) {
    ElMessage.warning('G2-6 中未找到可导入的重要逾期行')
    return
  }
  ElMessage.success(`已从 G2-6 拉取 ${pulled} 行重要逾期`)
}

async function syncToDisclosureNotes() {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payloads = buildG2ListedSyncPayloads(
    props.wpId || '',
    props.applicableStandards,
    dis.getSyncSnapshot(),
  )
  if (!payloads.length) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
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
    ElMessage.success(`已同步 ${rows} 行到附注模块「五、8 其他应收款（应收利息明细）」`)
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

onBeforeUnmount(() => {
  autoSync.cancelPending()
})
</script>

<style scoped>
.g2-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-disclosure-listed :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert, .sync-hint, .tie-out-alert { margin-bottom: 12px; }

.combined-cross-ref {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  margin-bottom: 12px;
  padding: 10px 14px;
  background: linear-gradient(90deg, #f0f7ff 0%, #fafcff 100%);
  border: 1px solid #c6e2ff;
  border-radius: 4px;
}
.cross-ref-text {
  color: #303133;
  font-size: 13px;
  line-height: 1.5;
}
.legacy-index-link {
  appearance: none;
  border: none;
  background: none;
  padding: 0;
  margin: 0 2px;
  color: #0563c1;
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
}
.legacy-index-link:hover { color: #003d82; }
.cross-ref-chips {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.chip-hint {
  font-size: 12px;
  color: #909399;
}

.disclosure-card { margin-bottom: 16px; }
.card-title-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.card-title { font-weight: 600; }
.auto-badge { margin-left: 6px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.is-total { font-weight: 600; }
.is-header { font-weight: 600; color: #606266; }
.stage-header { font-weight: 600; line-height: 1.2; }
.stage-sub { font-size: 11px; color: #909399; font-weight: 400; line-height: 1.2; margin-top: 2px; }

.template-tip {
  margin: 10px 0 0;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.55;
  color: #0563c1;
  background: #f5f9ff;
  border-radius: 4px;
}
.merge-tip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin-bottom: 10px;
}

.g2-disclosure-listed :deep(.row-total) { background: #f5f7fa; font-weight: 600; }
.g2-disclosure-listed :deep(.row-provision) { background: #fdf6ec; }
.g2-disclosure-listed :deep(.row-header) { background: #fafafa; }

.prep-hint {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; color: #606266; line-height: 1.6; }
.prep-hint li { margin: 2px 0; }
</style>
