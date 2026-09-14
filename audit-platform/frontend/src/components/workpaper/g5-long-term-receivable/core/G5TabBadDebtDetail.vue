<template>
  <div class="g5-bad-debt-detail" data-testid="g5-bad-debt-detail">
    <div class="section-head">
      <h3 class="sheet-title">G5-3 坏账准备明细表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-3" />
        <GtIndexChip value="wp:G5-1" />
        <GtIndexChip value="wp:G5-10" />
        <G5ImportExportDropdown
          :wp-id="props.wpId"
          sheet="G5-3"
          :disabled="!!props.readonly"
          @imported="onImported"
        />
        <el-tag size="small" type="info">明细 {{ detail.leaves.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="g5-3-bad-debt-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：确认长期应收款坏账准备存在、完整与计价恰当；验证期初→本期增减→期末滚动态及单项/组合划分，为 G5-1 审定与附注披露提供依据。
    </el-alert>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="policy-tip"
      title="【注意：与会计政策中披露的组合保持一致】组合名称建议与 G5-8「组合划分」及附注披露一致。"
    />

    <div class="toolbar-row">
      <el-button size="small" type="primary" plain :disabled="!!props.readonly" @click="detail.addRow('individual')">
        + 新增单项（其中）
      </el-button>
      <el-button size="small" type="primary" plain :disabled="!!props.readonly" @click="detail.addRow('portfolio')">
        + 新增组合（其中）
      </el-button>
      <el-button size="small" plain :disabled="!!props.readonly" @click="syncPortfolioNamesFromPolicy">
        从 G5-8 同步组合名
      </el-button>
    </div>

    <el-table
      :data="detail.displayRows.value"
      border
      size="small"
      max-height="560"
      :row-class-name="rowClassName"
      style="width: 100%; font-size: 13px"
    >
      <el-table-column label="项目" min-width="180" fixed>
        <template #default="{ row }">
          <span v-if="row.kind !== 'leaf'" class="label-strong">{{ row.item }}</span>
          <div v-else class="item-cell">
            <el-input
              :model-value="row.item"
              size="small"
              :disabled="!!props.readonly"
              :placeholder="row.category === 'individual' ? '债务人名称' : '组合名称'"
              @change="(v: string) => onUpdate(row.id, 'item', v)"
            />
            <el-select
              v-if="row.category === 'portfolio'"
              :model-value="row.portfolioType || 'business'"
              size="small"
              class="portfolio-type"
              :disabled="!!props.readonly"
              @change="(v: string) => onUpdate(row.id, 'portfolioType', v)"
            >
              <el-option label="业务类型" value="business" />
              <el-option label="客户类型" value="customer" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !props.readonly"
              :model-value="row.openingUnadjusted"
              size="small"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !props.readonly"
              :model-value="row.openingAdjustment"
              size="small"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'openingAdjustment', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期初审定 = 未审 + 账项调整">{{ fmt(row.openingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期增加" align="center">
        <el-table-column label="计提" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !props.readonly"
              :model-value="row.provisionIncrease"
              size="small"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'provisionIncrease', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.provisionIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他增加" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly"
              :model-value="row.otherIncrease"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'otherIncrease', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.otherIncrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期减少" align="center">
        <el-table-column label="转回" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly"
              :model-value="row.reversal"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'reversal', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.reversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转销" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly"
              :model-value="row.writeOff"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'writeOff', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.writeOff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他减少" width="96" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !props.readonly"
              :model-value="row.otherDecrease"
              size="small"
              :controls="false"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'otherDecrease', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.otherDecrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="未审数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末未审 = 期初审定 + 增加 − 减少">{{ fmt(row.closingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !props.readonly"
              :model-value="row.closingAdjustment"
              size="small"
              class="amt-input"
              @change="(v: number) => onUpdate(row.id, 'closingAdjustment', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末审定 = 期末未审 + 账项调整">{{ fmt(row.closingAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="单独计提减值、转回或转销原因" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="row.editable && !props.readonly"
            :model-value="row.reason"
            size="small"
            @change="(v: string) => onUpdate(row.id, 'reason', v)"
          />
          <span v-else>{{ row.kind === 'leaf' ? row.reason : '' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!props.readonly" label="" width="48" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.kind === 'leaf'"
            size="small"
            type="danger"
            link
            @click="onRemove(row.id)"
          >
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-bar">
      期末审定坏账合计: {{ fmt(detail.totals.value.closingAudited) }}
      ｜ 本期计提: {{ fmt(detail.totals.value.provisionIncrease) }}
      ｜ 本期转回: {{ fmt(detail.totals.value.reversal) }}
      ｜ 本期转销: {{ fmt(detail.totals.value.writeOff) }}
    </div>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="auditConclusion"
      note-ai-section="baddebt-note"
      conclusion-ai-section="baddebt-conclusion"
      note-placeholder="填写审计说明：可概述坏账准备计提方式（单项/组合）、期初期末滚动勾稽、重要转回/转销原因及与 G5-1/G5-10 勾稽情况。"
      conclusion-placeholder="填写审计结论：A、坏账准备计提充分、滚动无误。B、除下述事项外未见异常。C、存在重大差异或转销依据不足事项。"
      @update:note="saveAuditNote"
      @update:conclusion="saveAuditConclusion"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>结构对齐 Excel：按单项评估计提 → 信用风险组合计提 → 合计；「其中」行可无限增删。</li>
        <li>期初审定＝期初未审＋账项调整；期末未审＝期初审定＋计提＋其他增加−转回−转销−其他减少；期末审定＝期末未审＋账项调整。</li>
        <li>组合名称与 G5-8 / 附注披露保持一致；组合细分（业务类型/客户类型）驱动 G5-1 汇总。</li>
        <li>ECL 损失率测算见 G5-9/G5-10；本表聚焦准备滚动与审定勾稽。</li>
        <li>旧版「损失率双 Tab」数据打开时自动迁移为本滚动态格式。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useG5BadDebtDetail } from '../../composables/useG5BadDebtDetail'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { extractPolicyGroupNames } from '../../composables/g5ListedDisclosureRows'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'

const props = defineProps<{
  htmlData?: unknown
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useG5BadDebtDetail()
const ROWS_KEY = G5_ITEM_IDS.G5_3_ROWS
const g5Notes = useInjectedG5FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-3-audit-note'
const G5_CONCLUSION_KEY = 'G5-3-audit-conclusion'
let hydrating = false

function persistRows(): void {
  if (props.readonly || hydrating) return
  const json = detail.serializeRows()
  g5Notes.debouncedSave(ROWS_KEY, { remark: json, conclusion: json })
}

function onUpdate(id: string, field: string, value: string | number) {
  detail.updateCell(id, field as any, value)
  persistRows()
}

function onRemove(id: string) {
  detail.removeRow(id)
  persistRows()
}

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

function syncPortfolioNamesFromPolicy() {
  if (props.readonly) return
  const names = extractPolicyGroupNames(
    readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_8_POLICY)),
  )
  if (!names.length) {
    ElMessage.warning('未找到 G5-8 组合划分名称')
    return
  }
  const existing = new Set(
    detail.leaves.value
      .filter((r) => r.category === 'portfolio')
      .map((r) => r.item.trim()),
  )
  let added = 0
  for (const name of names) {
    if (!name || existing.has(name)) continue
    detail.leaves.value = [
      ...detail.leaves.value,
      {
        id: `port-${Date.now()}-${added}`,
        seq: detail.leaves.value.length + 1,
        category: 'portfolio',
        item: name,
        portfolioType: 'business',
        openingUnadjusted: 0,
        openingAdjustment: 0,
        provisionIncrease: 0,
        otherIncrease: 0,
        reversal: 0,
        writeOff: 0,
        otherDecrease: 0,
        closingAdjustment: 0,
        reason: '',
      },
    ]
    existing.add(name)
    added++
  }
  if (!added) {
    ElMessage.info('组合名已齐全，无需新增')
    return
  }
  persistRows()
  ElMessage.success(`已新增 ${added} 个组合行`)
}

onMounted(async () => {
  try {
    await g5Notes.loadAll()
  } catch {
    /* ignore */
  }
  hydrating = true
  const raw = readCanonicalRaw(g5Notes.allResponses.value.get(ROWS_KEY))
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      detail.loadRows(Array.isArray(parsed) ? parsed : parsed?.rows ?? [])
    } catch {
      /* ignore */
    }
  }
  hydrating = false
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

watch(
  () => detail.leaves.value.length,
  () => {
    if (!hydrating) persistRows()
  },
)

async function onImported() {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  hydrating = true
  const raw = readCanonicalRaw(g5Notes.allResponses.value.get(ROWS_KEY))
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) detail.loadRows(parsed)
    } catch { /* ignore */ }
  }
  hydrating = false
  emit('imported')
}

function fmt(v: number): string {
  return (Number(v) || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function rowClassName({ row }: { row: { kind: string } }) {
  if (row.kind === 'section_header') return 'row-header'
  if (row.kind === 'subtotal' || row.kind === 'total') return 'row-total'
  return ''
}
</script>

<style scoped>
.g5-bad-debt-detail {
  font-size: var(--wp-font-size, 13px);
  padding: 4px;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 8px;
  flex-wrap: wrap;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.audit-objective,
.policy-tip {
  margin-bottom: 8px;
}
.toolbar-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.amt-input {
  width: 100%;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}
.formula-cell {
  border-bottom: 1px dashed #999;
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.label-strong {
  font-weight: 600;
}
.item-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.portfolio-type {
  width: 100%;
}
.totals-bar {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
}
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.8;
}
:deep(.row-header) {
  background: var(--el-color-primary-light-9);
  font-weight: 600;
}
:deep(.row-total) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}
</style>
