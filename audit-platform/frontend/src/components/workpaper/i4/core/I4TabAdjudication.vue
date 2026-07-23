<!--
  I4TabAdjudication.vue — I4-1 长期待摊费用审定表

  对齐致同 Excel：未审滚动 → 账项调整 → 审定；本期 vs 上期变动；
  自 I4-2 带入；AJE 自 I4-3；摊销自 I4-6/7；与 TB 1801 勾稽
-->
<template>
  <div class="i4-adjudication">
    <div class="section-header">
      <span class="section-title">I4-1 长期待摊费用审定表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标</template>
      检查长期待摊费用(1801)期末余额的存在性、完整性、准确性及列报恰当性；
      确认摊销计提充分、资本化判断合理；审定数＝未审＋AJE＋RJE，与试算平衡表勾稽一致。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑（对齐 Excel I4-1）：</b>
        明细取数(I4-2) → 未审滚动(期初/增/摊/减/期末) → 账项调整(I4-3) → 审定；
        期末＝期初＋增加−摊销−减少；并与上期审定比较变动额/变动率（上期为 0 显示 N/A）。
        一年内摊销完毕部分的列报见编制说明（CAS 列报规则与注释）。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I4-1" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ rows.length }} 个项目</el-tag>
        <el-tag size="small" type="success">审定 {{ fmtAmount(subtotals.audited) }}</el-tag>
        <el-tag size="small" :type="Math.abs(tbDifference) > 0.01 ? 'danger' : 'success'">
          {{ Math.abs(tbDifference) > 0.01 ? `TB差异 ${fmtAmount(tbDifference)}` : '✓ TB一致' }}
        </el-tag>
        <el-tag v-if="crossCheck.hasWarning" size="small" type="warning">与明细勾稽差异</el-tag>
        <el-button size="small" @click="navigateTo('I4-2')">I4-2 →</el-button>
        <el-button size="small" @click="navigateTo('I4-3')">I4-3 →</el-button>
        <el-button size="small" @click="navigateTo('I4-6')">I4-6 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="reconciliationStatus === 'mismatch'"
      type="error"
      title="三角勾稽不平：期末 ≠ 期初+增加-摊销-减少，请检查数据"
      show-icon
      :closable="false"
      class="adj-warning"
    />
    <el-alert
      v-if="crossCheck.hasWarning"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
      :title="`与 I4-2 勾稽：期初差 ${fmtAmount(crossCheck.beginDiff)} / 期末差 ${fmtAmount(crossCheck.endDiff)} / 摊销差 ${fmtAmount(crossCheck.amortDiff)} / 审定vs明细 ${fmtAmount(crossCheck.auditedVsDetailDiff)}`"
    />
    <el-alert
      v-if="hasAjeApprox"
      type="warning"
      :closable="false"
      show-icon
      class="adj-warning"
      title="系统近似分摊：部分 AJE/RJE 按未审占比分摊自 I4-3，请按项目人工复核后改数（改后自动清除「近似」标记）"
    />

    <!-- Excel 式期初/期末 × 未审·调整·审定 + 变动（只读汇总） -->
    <el-card shadow="never" class="layer-card">
      <template #header>
        <span class="block-title">期初 / 期末审定矩阵（只读汇总，对齐 Excel I4-1）</span>
      </template>
      <el-table :data="leadMatrixRows" border size="small" class="layer-table">
        <el-table-column prop="label" label="项目" min-width="100" />
        <el-table-column label="期初数" align="center">
          <el-table-column prop="beginUnadj" label="未审数" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.beginUnadj) }}</template>
          </el-table-column>
          <el-table-column prop="beginAdj" label="账项调整" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.beginAdj) }}</template>
          </el-table-column>
          <el-table-column prop="beginAudited" label="审定数" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.beginAudited) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末数" align="center">
          <el-table-column prop="endUnadj" label="未审数" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endUnadj) }}</template>
          </el-table-column>
          <el-table-column prop="endAdj" label="账项调整" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endAdj) }}</template>
          </el-table-column>
          <el-table-column prop="endAudited" label="审定数" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endAudited) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期审定与上期审定比较" align="center">
          <el-table-column prop="varianceAmount" label="变动额" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.varianceAmount) }}</template>
          </el-table-column>
          <el-table-column prop="varianceRateLabel" label="变动率" min-width="90" align="right" />
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 按费用类型类别汇总（对齐 Excel 类别行） -->
    <el-card v-if="categorySummary.length" shadow="never" class="layer-card">
      <template #header>
        <span class="block-title">按费用类型汇总（只读，来自 I4-2 expenseType）</span>
      </template>
      <el-table :data="categorySummary" border size="small" class="layer-table">
        <el-table-column prop="category" label="类别" min-width="110" />
        <el-table-column prop="begin" label="期初" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.begin) }}</template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.increase) }}</template>
        </el-table-column>
        <el-table-column prop="amortization" label="本期摊销" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.amortization) }}</template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.decrease) }}</template>
        </el-table-column>
        <el-table-column prop="end" label="期末" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.end) }}</template>
        </el-table-column>
        <el-table-column prop="audited" label="审定" min-width="100" align="right">
          <template #default="{ row }">{{ fmtAmount(row.audited) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="seedFromI42">从 I4-2 带入</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="syncFromI43">从 I4-3 同步调整</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="syncAmortFromI46">从 I4-6/7 同步摊销</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="() => applyTbData()">TB写入未审</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="() => applyPriorFromTb()">写入上期审定</el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addRow">+ 新增</el-button>
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存并回写</el-button>
    </div>

    <div class="table-section">
      <el-table
        :data="rows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        show-summary
        :summary-method="getSummaryMethod"
        max-height="520"
      >
        <el-table-column prop="projectName" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span>{{ row.projectName }}</span>
            <el-tag v-if="row.fromDetail" size="small" type="info" class="src-tag">I4-2</el-tag>
            <el-tag v-if="row.ajeApprox" size="small" type="warning" class="src-tag">近似</el-tag>
            <el-button
              v-if="row.isEditable !== false && !isReadonly"
              size="small"
              type="danger"
              text
              class="row-delete-btn"
              @click="removeRow(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>

        <el-table-column label="未审滚动（期初/增/摊/减/期末）" align="center">
          <el-table-column prop="beginBalance" label="期初" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.beginBalance"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'beginBalance', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.increase"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'increase', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.increase) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="amortization" label="本期摊销" min-width="100" align="right">
            <template #header>
              <el-tooltip content="可自 I4-6/I4-7 测算同步" placement="top"><span class="hint-h">本期摊销</span></el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.amortization"
                size="small"
                :controls="false"
                :precision="2"
                :min="0"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'amortization', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.amortization) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.decrease"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'decrease', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.decrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" min-width="100" align="right">
            <template #header>
              <el-tooltip content="期末 = 期初 + 增加 − 摊销 − 减少" placement="top">
                <span class="formula-col-header">期末</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value" :class="{ 'cell-error-text': row.hasError }">{{ fmtAmount(row.endBalance) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="未审 · 调整 · 审定" align="center">
          <el-table-column prop="unadjusted" label="未审" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.unadjusted"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'unadjusted', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="aje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.aje"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'aje', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.aje) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="rje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.rje"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'rje', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.rje) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="100" align="right">
            <template #header>
              <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="与上期审定比较" align="center">
          <el-table-column prop="priorAudited" label="上期审定" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.isEditable !== false && !isReadonly"
                :model-value="row.priorAudited"
                size="small"
                :controls="false"
                :precision="2"
                class="amt-input"
                @change="(v: number | undefined) => onCellChange(row.rowId, 'priorAudited', v ?? 0)"
              />
              <span v-else>{{ fmtAmount(row.priorAudited) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动额" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.varianceAmount) }}</template>
          </el-table-column>
          <el-table-column label="变动率" min-width="90" align="right">
            <template #default="{ row }">{{ formatI4VarianceRate(row.varianceRate) }}</template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <div class="tb-section">
      <div class="block-header">
        <span class="block-title">TB取数与差异（合计 / TB数据 / 差异）</span>
      </div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="160" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.tbAmount) }}</template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.audited) }}</template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">
              {{ fmtAmount(row.difference) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>1、审计说明</span></div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="记录摊销完整性、资本化判断、与 I4-2/I4-6 勾稽情况等…"
        :disabled="isReadonly"
        @blur="() => saveNote(auditNote)"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>重大事项说明（风险 / 调整）</span></div>
      </template>
      <el-input
        v-model="significantMatters"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A. 风险评估：是否存在特别风险（舞弊/复杂交易/重大关联方）及应对…&#10;B. 重大发现/调整：原因、金额、索引（I4-3 等）…"
        :disabled="isReadonly"
        @blur="() => saveSignificantMatters(significantMatters)"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>2、审计结论</span>
          <div class="card-header-actions">
            <el-select
              v-if="!isReadonly"
              size="small"
              placeholder="Excel 结论模板 A/B/C"
              style="width: 220px"
              @change="applyConclusionTemplate"
            >
              <el-option v-for="t in I4_CONCLUSION_OPTIONS" :key="t.key" :label="t.label" :value="t.key" />
            </el-select>
            <el-button size="small" type="primary" text :disabled="isReadonly" @click="fillConclusionDraft">生成草稿</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="选择 A/B/C 模板或生成草稿后可再编辑…"
        :disabled="isReadonly"
        @blur="() => saveConclusion(auditConclusion)"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制说明</summary>
      <ol>
        <li>长期待摊费用核算已经发生、摊销期在一年以上的各项费用（如经营租赁方式租入固定资产改良支出等）。</li>
        <li>摊销直接冲减账面余额（无单独备抵科目）：期末＝期初＋增加−摊销−减少；科目 1801。</li>
        <li>一年内摊销完毕的部分：一般应重分类至「一年内到期的非流动资产」；但以摊销为后续计量的长期待摊费用，因其自然消耗过程，通常<strong>不要求</strong>仅因剩余摊销期不足一年而重分类（见注释）。</li>
        <li>明细合计、摊销测算、调整分录应与本表勾稽；TB 差异须为 0 后方可回写。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, inject } from 'vue'
import {
  useI4Adjudication,
  formatI4VarianceRate,
  I4_CONCLUSION_OPTIONS,
  type I4AdjudicationRow,
} from '../../composables/useI4Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1801: number; audited1801: number; priorAudited1801?: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const {
  rows,
  auditNote,
  auditConclusion,
  significantMatters,
  subtotals,
  excelLead,
  categorySummary,
  crossCheck,
  reconciliationStatus,
  hasAjeApprox,
  tbDifference,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  seedFromI42,
  syncFromI43,
  syncAmortFromI46,
  applyTbData,
  applyPriorFromTb,
  fillConclusionDraft,
  applyConclusionTemplate,
  writeback,
  saveNote,
  saveConclusion,
  saveSignificantMatters,
} = useI4Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbUnadjusted1801: computed(() => props.tbData?.unadjusted1801 ?? 0),
    tbAudited1801: computed(() => props.tbData?.audited1801 ?? 0),
    tbPriorAudited1801: computed(() => (props.tbData as any)?.priorAudited1801 ?? 0),
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

const leadMatrixRows = computed(() => {
  const L = excelLead.value
  return [{
    label: '合计',
    beginUnadj: L.beginUnadj,
    beginAdj: L.beginAdj,
    beginAudited: L.beginAudited,
    endUnadj: L.endUnadj,
    endAdj: L.endAdj,
    endAudited: L.endAudited,
    varianceAmount: L.varianceAmount,
    varianceRateLabel: formatI4VarianceRate(L.varianceRate),
  }]
})

function getSummaryMethod({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const sub = subtotals.value
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property as string | undefined
    if (prop && (sub as any)[prop] != null && typeof (sub as any)[prop] === 'number') {
      sums[idx] = fmtAmount((sub as any)[prop])
      return
    }
    const label = col.label
    if (label === '期末') { sums[idx] = fmtAmount(sub.endBalance); return }
    if (label === '审定数') { sums[idx] = fmtAmount(sub.audited); return }
    if (label === '变动额') { sums[idx] = fmtAmount(sub.varianceAmount); return }
    if (label === '变动率') { sums[idx] = formatI4VarianceRate(sub.varianceRate); return }
    sums[idx] = ''
  })
  return sums
}

function getRowClassName({ row }: { row: I4AdjudicationRow }): string {
  if (row.hasError) return 'row-has-error'
  return ''
}

function onCellChange(rowId: string, field: keyof I4AdjudicationRow, value: number): void {
  updateCell(rowId, field, value)
}

async function handleSave(): Promise<void> {
  await writeback(false)
}

function handleReview(): void {
  openReviewDialog('I4-1 审定表')
}

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i4-adjudication {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.section-title { font-size: 15px; font-weight: 600; }
.objective-alert { margin-bottom: 14px; }
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p { margin: 0; }
.tab-toolbar { margin-bottom: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.adj-warning { margin-bottom: 10px; }
.layer-card { margin-bottom: 14px; }
.layer-card :deep(.el-card__header) { padding: 10px 14px; background: #fafafa; font-weight: 600; }
.action-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.table-section { margin-bottom: 20px; }
.adjudication-table { font-size: var(--wp-font-size, 13px); }
.adjudication-table :deep(.el-table__footer td) { font-weight: 600; background: #f0f9ff; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px; font-weight: 500; }
.hint-h { border-bottom: 1px dashed #909399; cursor: help; }
.adjudication-table :deep(.row-has-error td) { background: #fef2f2 !important; }
.cell-error-text { color: #dc2626; font-weight: 600; }
.row-delete-btn { margin-left: 4px; font-size: 11px; padding: 2px 4px; }
.src-tag { margin-left: 4px; }
.amt-input { width: 100%; }
.amt-input :deep(.el-input__inner) { text-align: right; }
.tb-section { margin-bottom: 20px; }
.block-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; font-weight: 600; }
.difference-warning { color: #dc2626; font-weight: 600; }
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 500;
}
.card-header-actions { display: flex; gap: 8px; align-items: center; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 6px; line-height: 1.6; }
</style>
