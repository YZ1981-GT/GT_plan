<template>
  <div class="i2-project-detail">
    <div class="section-header">
      <span class="section-title">I2-7 研发项目构成明细表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li>确认所有应当记录的研发支出均已记录，相关披露均已包括（完整性）。</li>
        <li>确认与研发支出有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性、计价和分摊、分类和可理解性）。</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        按项目分行，按「期初 → 本期增加 → 本期减少 → 期末 → 审计调整 → 审定」滚动；
        每段拆费用性质（材料/人工/折旧摊销/能耗/委外/其他），并区分资本化与费用化。
        勾稽：期末＝期初＋增加－减少；审定＝期末＋调整；费用性质合计≈资本化＋费用化。
        本期增加直接材料合计可供 I2-8 检查比例分母取数。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-2" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-6" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-8" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">项目 {{ summary.rowCount }}</el-tag>
        <el-tag size="small" type="success">本期增加 {{ fmtNum(summary.increaseTotal) }}</el-tag>
        <el-tag size="small">其中资本化 {{ fmtNum(summary.increaseCapitalized) }}</el-tag>
        <el-tag size="small">费用化 {{ fmtNum(summary.increaseExpensed) }}</el-tag>
        <el-tag v-if="!i6ExpenseCross.ready" size="small" type="info">I6费用化未同步</el-tag>
        <el-tag
          v-else-if="i6ExpenseCross.diff != null && Math.abs(i6ExpenseCross.diff) > 0.01"
          size="small"
          type="danger"
        >
          vs I6费用化差 {{ fmtNum(i6ExpenseCross.diff) }}
        </el-tag>
        <el-tag v-else-if="i6ExpenseCross.ready" size="small" type="success">
          ✓ I6费用化 {{ fmtNum(i6ExpenseCross.i6) }}
        </el-tag>
        <el-tag v-if="summary.treatmentMismatchCount > 0" size="small" type="danger">
          性质≠处理 {{ summary.treatmentMismatchCount }}
        </el-tag>
        <el-tag
          v-if="crossValidateI22Diff != null && crossValidateI22Diff !== 0"
          size="small"
          type="danger"
        >
          与I2-2差异 {{ fmtNum(crossValidateI22Diff) }}
        </el-tag>
        <el-tag v-else-if="crossValidateI22Diff === 0" size="small" type="success">✓ I2-2一致</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-6')">← I2-6</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-8')">I2-8 →</el-button>
      </div>
    </div>

    <!-- 二、审计过程 -->
    <el-card shadow="never" class="block-card">
      <template #header><span>二、审计过程</span></template>
      <el-input
        type="textarea"
        :model-value="auditProcess"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="简述项目清单来源、费用归集方法、资本化/费用化划分依据（可索引 I2-6）、与 I2-2/I6 勾稽步骤…"
        @change="(v: string) => saveField(STORAGE_PROCESS, v)"
      />
    </el-card>

    <!-- 三、构成明细（按滚动阶段分 Tab，避免 73 列横向不可用） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>三、研发项目构成明细</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增项目</el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeStage" type="border-card" class="stage-tabs">
        <el-tab-pane label="汇总" name="overview">
          <el-table :data="rows" border size="small" max-height="480" show-summary :summary-method="overviewSummary">
            <el-table-column type="index" label="#" width="40" fixed />
            <el-table-column prop="projectCode" label="项目编号" min-width="100" fixed>
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.projectCode" size="small" />
                <span v-else>{{ row.projectCode || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="projectName" label="项目名称" min-width="140" fixed>
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.projectName" size="small" />
                <span v-else>{{ row.projectName || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="研发周期" min-width="200">
              <template #default="{ row }">
                <div class="period-cell">
                  <el-date-picker
                    v-if="!isReadonly"
                    v-model="row.periodStart"
                    type="date"
                    size="small"
                    value-format="YYYY-MM-DD"
                    placeholder="起"
                    style="width:110px"
                  />
                  <span v-else>{{ row.periodStart || '—' }}</span>
                  <span class="tilde">~</span>
                  <el-date-picker
                    v-if="!isReadonly"
                    v-model="row.periodEnd"
                    type="date"
                    size="small"
                    value-format="YYYY-MM-DD"
                    placeholder="止"
                    style="width:110px"
                  />
                  <span v-else>{{ row.periodEnd || '—' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="stage" label="项目阶段" width="100">
              <template #default="{ row }">
                <el-select v-if="!isReadonly" v-model="row.stage" size="small" style="width:100%">
                  <el-option label="研究" value="研究" />
                  <el-option label="开发" value="开发" />
                  <el-option label="完成" value="完成" />
                </el-select>
                <span v-else>{{ row.stage || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加合计" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell">{{ fmtNum(blockTotal(row.increase)) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="其中资本化" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell">{{ fmtNum(row.increase.capitalized) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="其中费用化" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell">{{ fmtNum(row.increase.expensed) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末审定合计" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell">{{ fmtNum(blockTotal(row.audited)) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="直接材料(增)" width="110" align="right">
              <template #default="{ row }">
                <span>{{ fmtNum(row.increase.material) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="56" fixed="right" align="center">
              <template #default="{ row }">
                <el-button size="small" type="danger" text @click="removeRow(row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane
          v-for="sk in stageTabs"
          :key="sk"
          :label="I2_PROJECT_STAGE_LABELS[sk]"
          :name="sk"
        >
          <el-alert
            v-if="!isStageEditable(sk)"
            type="info"
            :closable="false"
            show-icon
            class="formula-tip"
            :title="sk === 'ending'
              ? '账面期末余额 = 期初 + 本期增加 − 本期减少（自动计算）'
              : '期末审定金额 = 账面期末余额 + 审计调整（自动计算）'"
          />
          <el-table
            :data="rows"
            border
            size="small"
            max-height="480"
            :row-class-name="({ row }) => rowClassForStage(row, sk)"
            show-summary
            :summary-method="(p) => stageSummary(p, sk)"
          >
            <el-table-column type="index" label="#" width="40" fixed />
            <el-table-column prop="projectName" label="项目名称" min-width="130" fixed>
              <template #default="{ row }">{{ row.projectName || '—' }}</template>
            </el-table-column>
            <el-table-column
              v-for="ck in I2_PROJECT_COST_KEYS"
              :key="ck"
              :label="I2_PROJECT_COST_LABELS[ck]"
              :min-width="ck === 'depreciation' || ck === 'capitalized' || ck === 'expensed' ? 110 : 100"
              align="right"
            >
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly && isStageEditable(sk)"
                  v-model="row[sk][ck]"
                  size="small"
                  :controls="false"
                  :precision="2"
                  style="width:100%"
                  @change="onCostChange(row)"
                />
                <span
                  v-else
                  :class="{
                    'formula-cell': !isStageEditable(sk),
                    'mismatch-text': isTreatmentKey(ck) && hasTreatmentMismatch(row[sk]),
                  }"
                >{{ fmtNum(row[sk][ck]) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="性质合计" width="100" align="right">
              <template #default="{ row }">
                <span :class="{ 'mismatch-text': hasTreatmentMismatch(row[sk]) }">
                  {{ fmtNum(costNatureSum(row[sk])) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="处理合计" width="100" align="right">
              <template #default="{ row }">
                <span :class="{ 'mismatch-text': hasTreatmentMismatch(row[sk]) }">
                  {{ fmtNum(costTreatmentSum(row[sk])) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>

      <div class="totals-bar">
        <span>本期增加：<b>{{ fmtNum(summary.increaseTotal) }}</b></span>
        <span>资本化：<b>{{ fmtNum(summary.increaseCapitalized) }}</b></span>
        <span>费用化：<b>{{ fmtNum(summary.increaseExpensed) }}</b></span>
        <span>期末审定：<b>{{ fmtNum(summary.auditedTotal) }}</b></span>
        <span>材料(增)→I2-8：<b>{{ fmtNum(summary.materialIncreaseTotal) }}</b></span>
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>四、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录费用归集异常、资本化/费用化划分差异、与 I2-2/I6 勾稽差异及处理…"
        @change="(v: string) => saveField(STORAGE_NOTE, v)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>五、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="基于构成明细与滚动勾稽结果，对研发支出完整性与计量准确性给出结论…"
        @change="(v: string) => saveField(STORAGE_CONCLUSION, v)"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI2ProjectDetail,
  I2_PROJECT_COST_KEYS,
  I2_PROJECT_COST_LABELS,
  I2_PROJECT_STAGE_LABELS,
  costNatureSum,
  costTreatmentSum,
  hasTreatmentMismatch,
  type I2ProjectDetailRow,
  type I2ProjectStageKey,
  type I2ProjectCostKey,
  type I2ProjectCostBlock,
} from '../../composables/useI2ProjectDetail'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const allResponsesRef = toRef(props, 'allResponses')
const {
  rows,
  auditProcess,
  auditNote,
  auditConclusion,
  activeStage,
  summary,
  crossValidateI22Diff,
  i6ExpenseCross,
  addRow,
  removeRow,
  onCostChange,
  isStageEditable,
  persistAll,
  saveField,
  STORAGE_PROCESS,
  STORAGE_NOTE,
  STORAGE_CONCLUSION,
} = useI2ProjectDetail(allResponsesRef, { saveResponse: props.saveResponse })

const stageTabs: I2ProjectStageKey[] = [
  'begin',
  'increase',
  'decrease',
  'ending',
  'adjustment',
  'audited',
]

function blockTotal(block: I2ProjectCostBlock): number {
  const t = costTreatmentSum(block)
  return t || costNatureSum(block)
}

function isTreatmentKey(ck: I2ProjectCostKey): boolean {
  return ck === 'capitalized' || ck === 'expensed'
}

function rowClassForStage(row: I2ProjectDetailRow, sk: I2ProjectStageKey) {
  return hasTreatmentMismatch(row[sk]) ? 'row-mismatch' : ''
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (value?.trim()) {
      addRow({ projectName: value.trim() })
      ElMessage.success(`已添加：${value.trim()}`)
    }
  } catch { /* cancelled */ }
}

async function handleSave() {
  await persistAll()
  emit('save')
  ElMessage.success('研发项目构成明细表已保存')
}

function handleReview() {
  openReviewDialog('I2-7-研发项目构成明细')
}

function fmtNum(v: number): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function overviewSummary({ columns }: { columns: { property?: string; label?: string }[] }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const label = col.label || ''
    if (label.includes('本期增加合计')) return fmtNum(summary.value.increaseTotal)
    if (label.includes('其中资本化')) return fmtNum(summary.value.increaseCapitalized)
    if (label.includes('其中费用化')) return fmtNum(summary.value.increaseExpensed)
    if (label.includes('期末审定')) return fmtNum(summary.value.auditedTotal)
    if (label.includes('直接材料')) return fmtNum(summary.value.materialIncreaseTotal)
    return ''
  })
}

function stageSummary(
  { columns }: { columns: { property?: string; label?: string }[] },
  sk: I2ProjectStageKey,
) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const label = col.label || ''
    for (const ck of I2_PROJECT_COST_KEYS) {
      if (label === I2_PROJECT_COST_LABELS[ck]) {
        const sum = rows.value.reduce((s, r) => s + (Number(r[sk][ck]) || 0), 0)
        return fmtNum(sum)
      }
    }
    if (label === '性质合计') {
      return fmtNum(rows.value.reduce((s, r) => s + costNatureSum(r[sk]), 0))
    }
    if (label === '处理合计') {
      return fmtNum(rows.value.reduce((s, r) => s + costTreatmentSum(r[sk]), 0))
    }
    return ''
  })
}
</script>

<style scoped>
.i2-project-detail { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6;
}
.tab-toolbar { margin-bottom: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.block-card { margin-bottom: 14px; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; gap: 8px; }
.stage-tabs { margin-top: 4px; }
.formula-tip { margin-bottom: 8px; }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; }
.mismatch-text { color: #dc2626; font-weight: 600; }
.period-cell { display: flex; align-items: center; gap: 4px; }
.tilde { color: #94a3b8; }
.totals-bar {
  display: flex; gap: 20px; flex-wrap: wrap; margin-top: 10px;
  padding: 8px 12px; background: #f8fafc; border-radius: 4px; font-size: 12px; color: #334155;
}
.audit-note-card, .audit-conclusion-card { margin-top: 14px; }
:deep(.row-mismatch) { background: #fef2f2 !important; }
</style>
