<!-- G7-2 长期股权投资明细表：按原始模板重建成本法、权益法、减值三条审定链。 -->
<template>
  <div class="g7-detail">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G7-2 长期股权投资明细表</h3>
        <div class="sheet-subtitle">成本法 / 权益法 / 减值准备 × 未审 / AJE / RJE / 审定</div>
      </div>
      <div class="head-actions">
        <el-button
          size="small"
          type="primary"
          :disabled="isReadonly || !isDirty"
          :loading="saving"
          @click="saveRows(false)"
        >
          保存
        </el-button>
        <el-button
          v-if="extractionEnabled && !isReadonly"
          size="small"
          type="success"
          plain
          :loading="auxLoading"
          @click="handleAuxExtract"
        >
          从四表取数
        </el-button>
        <el-button
          v-if="activeSection === 'equity' && !isReadonly"
          size="small"
          type="primary"
          plain
          :loading="equityPullLoading"
          @click="handleEquityPull"
        >
          从 G7-14 带入期末余额
        </el-button>
        <el-button
          v-if="activeSection !== 'summary'"
          size="small"
          :disabled="isReadonly"
          @click="handleAddRow"
        >
          + 被投资单位
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import" :disabled="isReadonly">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-2-detail')">💬复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      按原表逐项记录投资成本、权益法变动和减值准备；每项均由未审数经 AJE、RJE 桥接到审定数，并自动汇总至 G7-1。
    </el-alert>

    <div class="navigation-row">
      <el-segmented v-model="activeSection" :options="sectionOptions" size="small" />
      <div class="navigation-meta">
        <GtIndexChip value="wp:G7-2" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ sectionRowCount }} 行</el-tag>
        <el-tag v-if="isDirty" size="small" type="warning">未保存</el-tag>
      </div>
    </div>

    <template v-if="activeSection !== 'summary'">
      <div class="layer-row">
        <span class="layer-label">展示口径：</span>
        <el-radio-group v-model="activeLayer" size="small">
          <el-radio-button value="basic">投资信息</el-radio-button>
          <el-radio-button value="unadjusted">期初及本期未审</el-radio-button>
          <el-radio-button value="adjustment">AJE / RJE</el-radio-button>
          <el-radio-button value="audited">审定数</el-radio-button>
        </el-radio-group>
        <span class="formula-hint">蓝色金额为公式列，不可手工覆盖</span>
      </div>

      <el-table
        :data="activeRows"
        border
        size="small"
        max-height="620"
        row-key="id"
        class="detail-table"
      >
        <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
        <el-table-column label="被投资单位" min-width="160" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && activeSection !== 'impairment'"
              :model-value="row.investeeName"
              size="small"
              @update:model-value="(value: string) => updateField(row, 'investeeName', value)"
            />
            <span v-else>{{ row.investeeName }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-for="column in activeColumns"
          :key="column.key"
          :label="column.label"
          :min-width="column.width || 120"
          :align="column.kind === 'text' || column.kind === 'date' || column.kind === 'select' ? 'left' : 'right'"
        >
          <template #default="{ row }">
            <span v-if="column.formula" class="formula-cell" :title="column.formula">
              {{ formatCell(row[column.key], column.kind) }}
            </span>
            <el-select
              v-else-if="column.kind === 'select' && !isReadonly && activeSection !== 'impairment'"
              :model-value="row[column.key]"
              size="small"
              @change="(value: string) => updateField(row, column.key, value)"
            >
              <el-option
                v-for="option in column.options"
                :key="option.value"
                :value="option.value"
                :label="option.label"
              />
            </el-select>
            <el-date-picker
              v-else-if="column.kind === 'date' && !isReadonly && activeSection !== 'impairment'"
              :model-value="row[column.key]"
              value-format="YYYY-MM-DD"
              type="date"
              size="small"
              @update:model-value="(value: string) => updateField(row, column.key, value || '')"
            />
            <el-input
              v-else-if="column.kind === 'text' && !isReadonly"
              :model-value="row[column.key]"
              size="small"
              @update:model-value="(value: string) => updateField(row, column.key, value)"
            />
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row[column.key]"
              :controls="false"
              :precision="column.kind === 'percent' ? 6 : 2"
              :step="column.kind === 'percent' ? 0.01 : 1"
              size="small"
              class="number-input"
              @change="(value: number | undefined) => updateField(row, column.key, value ?? 0)"
            />
            <span v-else>{{ formatCell(row[column.key], column.kind) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly && activeSection !== 'impairment'" label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-total">
        <span>{{ activeSectionLabel }}审定期末合计</span>
        <strong>{{ fmtAmount(activeSectionClosing) }}</strong>
      </div>
    </template>

    <template v-else>
      <div class="summary-cards">
        <div class="summary-card">
          <span>投资原值（1511）</span>
          <strong>{{ fmtAmount(summary.gross.closing) }}</strong>
        </div>
        <div class="summary-card impairment">
          <span>减值准备（1512）</span>
          <strong>{{ fmtAmount(summary.impairment.closing) }}</strong>
        </div>
        <div class="summary-card net">
          <span>长期股权投资净值</span>
          <strong>{{ fmtAmount(summary.net.closing) }}</strong>
        </div>
      </div>

      <el-table :data="summaryRows" border size="small" class="summary-table">
        <el-table-column label="汇总项目" prop="label" min-width="150" />
        <el-table-column label="期初审定" min-width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.opening) }}</template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.increase) }}</template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.decrease) }}</template>
        </el-table-column>
        <el-table-column label="期末审定" min-width="130" align="right">
          <template #default="{ row }"><strong>{{ fmtAmount(row.closing) }}</strong></template>
        </el-table-column>
        <el-table-column label="勾稽去向" prop="crossRef" min-width="150" />
      </el-table>

      <el-alert
        class="cross-reference"
        type="success"
        :closable="false"
        title="勾稽关系"
        description="投资原值期末审定数汇总至 G7-1/TB1511；减值准备期末审定数汇总至 G7-1/TB1512；权益法损益及股利分别为 G7-4、G7-14 等底稿提供明细基础。"
      />
    </template>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button v-if="!isReadonly" link type="primary" size="small" @click="saveNote">保存</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="记录核算方法判断、重大增减变动、权益法测算或减值测试索引……"
        @blur="saveNote"
      />
    </el-card>

    <details class="prep-hint">
      <summary>编制提示</summary>
      <ol>
        <li>成本法一般对应子公司；权益法按合营企业、联营企业分别汇总。</li>
        <li>期末未审 = 期初未审 + 本期增加 − 本期减少；审定数在未审数基础上分别叠加 AJE、RJE。</li>
        <li>权益法“权益变动小计” = 损益调整 + 其他综合收益 + 其他权益变动。</li>
        <li>减值准备按每一被投资单位自动建行，基础信息与投资明细同步。</li>
        <li>导入原始“明细表G7-2”工作表时，系统按原模板坐标识别成本法、权益法和减值区块。</li>
        <li>「从 G7-14 带入期末余额」：按被投资单位匹配 G7-14 权益法测算，逐户对照后按「只填空」写入权益法行的运动分量（期初/损益/OCI/其他权益/股利），期末由公式派生；已填单位不覆盖。</li>
      </ol>
    </details>

    <!-- G7-14 → G7-2 权益法行 逐户对照带入弹窗（Decision 2） -->
    <el-dialog
      v-model="equityPullVisible"
      title="从 G7-14 带入期末余额（逐户对照）"
      width="720px"
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="equity-pull-note"
        title="带入目标为 G7-2 权益法行；「只填空」模式仅对运动分量为空的单位写入，已填单位保持不变。写入后期末余额由公式派生并与 G7-14 期末对照。"
      />
      <el-table :data="equityPullDiffs" border size="small" max-height="360">
        <el-table-column label="被投资单位" prop="investeeName" min-width="160" />
        <el-table-column label="G7-2 当前期末" align="right" width="130">
          <template #default="{ row }">{{ fmtAmount(row.current) }}</template>
        </el-table-column>
        <el-table-column label="G7-14 期末" align="right" width="130">
          <template #default="{ row }">{{ fmtAmount(row.incoming) }}</template>
        </el-table-column>
        <el-table-column label="差异" align="right" width="120">
          <template #default="{ row }">
            <span :class="{ 'diff-red': Math.abs(row.diff) > 0.01 }">{{ fmtAmount(row.diff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.matched ? 'success' : 'info'">
              {{ row.matched ? '已匹配' : '新建' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button size="small" @click="equityPullVisible = false">取消</el-button>
        <el-button
          size="small"
          type="primary"
          :loading="equityPullLoading"
          @click="confirmEquityPull"
        >
          确认带入（只填空）
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7ImportExport } from '../../composables/useG7ImportExport'
import {
  calcG7DetailSummary,
  createG7CostRow,
  createG7EquityRow,
  normalizeG7DetailRows,
  recalcG7DetailRow,
  resequenceG7DetailState,
  serializeG7DetailState,
  syncG7ImpairmentRows,
  type G7DetailState,
  type G7DetailStoredRow,
} from '../../composables/g7DetailModel'
import { mergeAuxRowsIntoDetail } from '../../composables/g7AuxExtraction'
import {
  pullG7_14ForDetail,
  buildEquityPullDiff,
  applyEquityPullToDetail,
  type G7EquityClosingRow,
  type G7EquityPullDiff,
} from '../../composables/g7EquityMethodPullToDetail'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

type SectionKey = 'cost' | 'equity' | 'impairment' | 'summary'
type LayerKey = 'basic' | 'unadjusted' | 'adjustment' | 'audited'
type ColumnKind = 'text' | 'number' | 'percent' | 'date' | 'select'

interface ColumnDef {
  key: string
  label: string
  kind: ColumnKind
  width?: number
  formula?: string
  options?: Array<{ value: string; label: string }>
}

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const activeSection = ref<SectionKey>('cost')
const activeLayer = ref<LayerKey>('basic')
const state = reactive<G7DetailState>({ costRows: [], equityRows: [], impairmentRows: [] })
const auxLoading = ref(false)
// G7-14 跨册带入期末余额（Decision 2：目标 G7-2 权益法行）
const equityPullVisible = ref(false)
const equityPullLoading = ref(false)
const equityPullDiffs = ref<G7EquityPullDiff[]>([])
let equityPullSrc: G7EquityClosingRow[] = []
// 灰度开关透出（render project_context）：关闭时「从四表取数」按钮隐藏
const extractionEnabled = computed(() => !!props.htmlData?.project_context?.g7_extraction_enabled)
const isDirty = ref(false)
const saving = ref(false)
const auditNote = ref('')
let saveTimer: number | undefined
let editRevision = 0
let validationBlocked = false

const sectionOptions = [
  { label: '一、成本法（子公司）', value: 'cost' },
  { label: '二、权益法（合营 / 联营）', value: 'equity' },
  { label: '三、减值准备', value: 'impairment' },
  { label: '四、汇总勾稽', value: 'summary' },
]

const relationshipOptions = [
  { value: 'joint_venture', label: '合营企业' },
  { value: 'associate', label: '联营企业' },
]

const basicColumns: ColumnDef[] = [
  { key: 'initialInvestmentCost', label: '初始投资成本', kind: 'number', width: 130 },
  { key: 'investmentRatio', label: '投资比例', kind: 'percent', width: 105 },
  { key: 'investmentDate', label: '投资日期', kind: 'date', width: 140 },
  { key: 'investmentMethod', label: '取得方式', kind: 'text', width: 140 },
]

const costColumns: Record<LayerKey, ColumnDef[]> = {
  basic: [
    ...basicColumns,
    { key: 'cashDividend', label: '本期现金股利', kind: 'number', width: 130 },
  ],
  unadjusted: [
    { key: 'openingRatio', label: '期初比例', kind: 'percent' },
    { key: 'openingAmount', label: '期初未审', kind: 'number' },
    { key: 'increaseRatio', label: '本期增加比例', kind: 'percent' },
    { key: 'increaseAmount', label: '本期增加金额', kind: 'number' },
    { key: 'increaseIndex', label: '增加索引', kind: 'text' },
    { key: 'decreaseRatio', label: '本期减少比例', kind: 'percent' },
    { key: 'decreaseAmount', label: '本期减少金额', kind: 'number' },
    { key: 'decreaseIndex', label: '减少索引', kind: 'text' },
    { key: 'closingRatio', label: '期末比例', kind: 'percent', formula: '期初比例 + 增加比例 − 减少比例' },
    { key: 'closingAmount', label: '期末未审', kind: 'number', formula: '期初未审 + 增加 − 减少' },
  ],
  adjustment: [
    { key: 'openingAje', label: '期初AJE', kind: 'number' },
    { key: 'openingRje', label: '期初RJE', kind: 'number' },
    { key: 'ajeIncrease', label: '本期增加AJE', kind: 'number' },
    { key: 'ajeDecrease', label: '本期减少AJE', kind: 'number' },
    { key: 'rjeIncrease', label: '本期增加RJE', kind: 'number' },
    { key: 'rjeDecrease', label: '本期减少RJE', kind: 'number' },
  ],
  audited: [
    { key: 'auditedOpeningRatio', label: '期初审定比例', kind: 'percent', formula: '期初未审比例' },
    { key: 'auditedOpeningAmount', label: '期初审定金额', kind: 'number', formula: '期初未审 + 期初AJE + 期初RJE' },
    { key: 'auditedIncreaseRatio', label: '增加审定比例', kind: 'percent', formula: '未审增加比例' },
    { key: 'auditedIncreaseAmount', label: '增加审定金额', kind: 'number', formula: '未审增加 + AJE + RJE' },
    { key: 'auditedDecreaseRatio', label: '减少审定比例', kind: 'percent', formula: '未审减少比例' },
    { key: 'auditedDecreaseAmount', label: '减少审定金额', kind: 'number', formula: '未审减少 + AJE + RJE' },
    { key: 'auditedClosingRatio', label: '期末审定比例', kind: 'percent', formula: '期初审定比例 + 增加 − 减少' },
    { key: 'auditedClosingAmount', label: '期末审定金额', kind: 'number', formula: '期初审定 + 增加审定 − 减少审定' },
  ],
}

const equityColumns: Record<LayerKey, ColumnDef[]> = {
  basic: [
    { key: 'relationship', label: '投资关系', kind: 'select', width: 120, options: relationshipOptions },
    ...basicColumns,
  ],
  unadjusted: [
    { key: 'openingRatio', label: '期初比例', kind: 'percent' },
    { key: 'openingAmount', label: '期初未审', kind: 'number' },
    { key: 'increaseRatio', label: '增加比例', kind: 'percent' },
    { key: 'costIncrease', label: '新增投资成本', kind: 'number' },
    { key: 'profitLossAdjustment', label: '损益调整', kind: 'number' },
    { key: 'otherComprehensiveIncome', label: '其他综合收益', kind: 'number' },
    { key: 'otherEquityChange', label: '其他权益变动', kind: 'number' },
    { key: 'equityIncreaseSubtotal', label: '权益变动小计', kind: 'number', formula: '损益调整 + OCI + 其他权益变动' },
    { key: 'otherIncrease', label: '其他增加', kind: 'number' },
    { key: 'decreaseRatio', label: '减少比例', kind: 'percent' },
    { key: 'costDecrease', label: '投资成本减少', kind: 'number' },
    { key: 'dividendReceived', label: '收到现金股利', kind: 'number' },
    { key: 'otherDecrease', label: '其他减少', kind: 'number' },
    { key: 'closingRatio', label: '期末比例', kind: 'percent', formula: '期初比例 + 增加比例 − 减少比例' },
    { key: 'closingAmount', label: '期末未审', kind: 'number', formula: '期初 + 各项增加 − 各项减少' },
  ],
  adjustment: [
    { key: 'openingAje', label: '期初AJE', kind: 'number' },
    { key: 'openingRje', label: '期初RJE', kind: 'number' },
    { key: 'ajeCostIncrease', label: '新增成本AJE', kind: 'number' },
    { key: 'ajeProfitLoss', label: '损益调整AJE', kind: 'number' },
    { key: 'ajeOci', label: 'OCI AJE', kind: 'number' },
    { key: 'ajeOtherEquity', label: '其他权益AJE', kind: 'number' },
    { key: 'ajeOtherIncrease', label: '其他增加AJE', kind: 'number' },
    { key: 'ajeCostDecrease', label: '成本减少AJE', kind: 'number' },
    { key: 'ajeDividend', label: '股利AJE', kind: 'number' },
    { key: 'ajeOtherDecrease', label: '其他减少AJE', kind: 'number' },
    { key: 'rjeCostIncrease', label: '新增成本RJE', kind: 'number' },
    { key: 'rjeProfitLoss', label: '损益调整RJE', kind: 'number' },
    { key: 'rjeOci', label: 'OCI RJE', kind: 'number' },
    { key: 'rjeOtherEquity', label: '其他权益RJE', kind: 'number' },
    { key: 'rjeOtherIncrease', label: '其他增加RJE', kind: 'number' },
    { key: 'rjeCostDecrease', label: '成本减少RJE', kind: 'number' },
    { key: 'rjeDividend', label: '股利RJE', kind: 'number' },
    { key: 'rjeOtherDecrease', label: '其他减少RJE', kind: 'number' },
  ],
  audited: [
    { key: 'auditedOpeningRatio', label: '期初审定比例', kind: 'percent', formula: '期初未审比例' },
    { key: 'auditedOpeningAmount', label: '期初审定金额', kind: 'number', formula: '期初未审 + 期初AJE + 期初RJE' },
    { key: 'auditedIncreaseRatio', label: '增加审定比例', kind: 'percent', formula: '未审增加比例' },
    { key: 'auditedCostIncrease', label: '新增成本审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedProfitLoss', label: '损益调整审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedOci', label: 'OCI审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedOtherEquity', label: '其他权益审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedEquityIncreaseSubtotal', label: '权益变动审定小计', kind: 'number', formula: '损益 + OCI + 其他权益' },
    { key: 'auditedOtherIncrease', label: '其他增加审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedDecreaseRatio', label: '减少审定比例', kind: 'percent', formula: '未审减少比例' },
    { key: 'auditedCostDecrease', label: '成本减少审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedDividend', label: '股利审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedOtherDecrease', label: '其他减少审定', kind: 'number', formula: '未审 + AJE + RJE' },
    { key: 'auditedClosingRatio', label: '期末审定比例', kind: 'percent', formula: '期初审定比例 + 增加 − 减少' },
    { key: 'auditedClosingAmount', label: '期末审定金额', kind: 'number', formula: '原表BB：期初审定 + 成本增加 + 权益增加小计 − 成本减少 − 分回利润（不含其他栏）' },
  ],
}

const impairmentColumns: Record<LayerKey, ColumnDef[]> = {
  basic: [
    { key: 'relationship', label: '投资关系', kind: 'select', width: 120, options: [
      { value: 'subsidiary', label: '子公司' },
      ...relationshipOptions,
    ] },
    ...basicColumns.map(column => ({ ...column, formula: '与成本法/权益法明细同步' })),
    { key: 'remark', label: '减值测试索引/说明', kind: 'text', width: 180 },
  ],
  unadjusted: [
    { key: 'openingAmount', label: '期初未审', kind: 'number' },
    { key: 'increaseAmount', label: '本期计提', kind: 'number' },
    { key: 'decreaseAmount', label: '转回/转销', kind: 'number' },
    { key: 'closingAmount', label: '期末未审', kind: 'number', formula: '期初未审 + 本期计提 − 转回/转销' },
    { key: 'remark', label: '减值测试索引/说明', kind: 'text', width: 180 },
  ],
  adjustment: [
    { key: 'openingAje', label: '期初AJE', kind: 'number' },
    { key: 'openingRje', label: '期初RJE', kind: 'number' },
    { key: 'ajeIncrease', label: '计提AJE', kind: 'number' },
    { key: 'ajeDecrease', label: '转回/转销AJE', kind: 'number' },
    { key: 'rjeIncrease', label: '计提RJE', kind: 'number' },
    { key: 'rjeDecrease', label: '转回/转销RJE', kind: 'number' },
  ],
  audited: [
    { key: 'auditedOpeningAmount', label: '期初审定', kind: 'number', formula: '期初未审 + 期初AJE + 期初RJE' },
    { key: 'auditedIncreaseAmount', label: '本期计提审定', kind: 'number', formula: '未审计提 + AJE + RJE' },
    { key: 'auditedDecreaseAmount', label: '转回/转销审定', kind: 'number', formula: '未审减少 + AJE + RJE' },
    { key: 'auditedClosingAmount', label: '期末审定', kind: 'number', formula: '期初审定 + 计提审定 − 减少审定' },
  ],
}

const activeRows = computed<G7DetailStoredRow[]>(() => {
  if (activeSection.value === 'cost') return state.costRows
  if (activeSection.value === 'equity') return state.equityRows
  if (activeSection.value === 'impairment') return state.impairmentRows
  return []
})

const activeColumns = computed(() => {
  if (activeSection.value === 'cost') return costColumns[activeLayer.value]
  if (activeSection.value === 'equity') return equityColumns[activeLayer.value]
  return impairmentColumns[activeLayer.value]
})

const summary = computed(() => calcG7DetailSummary(state))
const summaryRows = computed(() => [
  { label: '成本法（子公司）', ...summary.value.cost, crossRef: 'G7-1 子公司' },
  { label: '权益法（合营企业）', ...summary.value.jointVenture, crossRef: 'G7-1 合营企业' },
  { label: '权益法（联营企业）', ...summary.value.associate, crossRef: 'G7-1 联营企业' },
  { label: '投资原值合计', ...summary.value.gross, crossRef: 'G7-1 / TB1511' },
  { label: '减值准备', ...summary.value.impairment, crossRef: 'G7-1 / TB1512' },
  { label: '长期股权投资净值', ...summary.value.net, crossRef: '财务报表' },
])

const activeSectionLabel = computed(() => ({
  cost: '成本法',
  equity: '权益法',
  impairment: '减值准备',
  summary: '汇总',
})[activeSection.value])
const sectionRowCount = computed(() => activeSection.value === 'summary'
  ? state.costRows.length + state.equityRows.length
  : activeRows.value.length)
const activeSectionClosing = computed(() => {
  if (activeSection.value === 'cost') return summary.value.cost.closing
  if (activeSection.value === 'equity') {
    return summary.value.jointVenture.closing + summary.value.associate.closing
  }
  return summary.value.impairment.closing
})

function queueAutoSave(): void {
  if (saveTimer) window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => { void saveRows(true) }, 1000)
}

function markDirty(): void {
  editRevision += 1
  validationBlocked = false
  isDirty.value = true
  queueAutoSave()
}

function recalcAndPublish(row?: G7DetailStoredRow): void {
  if (row) recalcG7DetailRow(row)
  syncG7ImpairmentRows(state)
  publishDetail()
}

function publishDetail(): void {
  window.dispatchEvent(new CustomEvent('g7:detail-updated', {
    detail: {
      summary: summary.value,
      rows: serializeG7DetailState(state),
    },
  }))
}

function updateField(row: G7DetailStoredRow, key: string, value: unknown): void {
  ;(row as any)[key] = value
  recalcAndPublish(row)
  markDirty()
}

async function handleAuxExtract(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  auxLoading.value = true
  try {
    const res: any = await api.post(
      `/api/workpapers/${props.wpId}/g7/import-aux-balance`,
      {},
      { params: { overwrite: false } } as any,
    )
    const data = res?.data ?? res ?? {}
    if (data.enabled === false) {
      ElMessage.info(data.message || '四表取数未启用')
      return
    }
    const auxRows = Array.isArray(data.rows) ? data.rows : []
    if (!auxRows.length) {
      ElMessage.warning(data.message || '账套无被投资单位辅助余额（科目1511），请手工录入')
      return
    }
    // 前端按 Persist_First 并入当前编辑态（后端已按同口径持久化，二者一致）
    const merged = mergeAuxRowsIntoDetail(state, auxRows, { overwrite: false })
    recalcAndPublish()
    markDirty()
    await saveRows(false)
    ElMessage.success(
      `${data.message || ''}（本地新增 ${merged.added} / 填空 ${merged.filled} 行；控制类型未取数，请按 G7-4 判断改段）`,
    )
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '四表取数失败')
  } finally {
    auxLoading.value = false
  }
}

/** 从 G7-14 权益法测算逐户拉取期末余额 → 对照弹窗（缺源安全，Property 10）。 */
async function handleEquityPull(): Promise<void> {
  if (props.isReadonly || !props.projectId) return
  equityPullLoading.value = true
  try {
    const src = await pullG7_14ForDetail(props.projectId)
    if (!src.length) {
      ElMessage.warning('未获取到 G7-14 权益法测算数据（Method 组未实例化或无逐户明细）')
      return
    }
    equityPullSrc = src
    equityPullDiffs.value = buildEquityPullDiff(state, src)
    equityPullVisible.value = true
  } catch (e: any) {
    ElMessage.error(e?.message || '从 G7-14 带入失败')
  } finally {
    equityPullLoading.value = false
  }
}

/** 确认带入：Persist_First 写入 G7-2 权益法行，经 g7:detail-updated 传导至 G7-1。 */
async function confirmEquityPull(): Promise<void> {
  if (props.isReadonly || !equityPullSrc.length) {
    equityPullVisible.value = false
    return
  }
  const res = applyEquityPullToDetail(state, equityPullSrc, { overwrite: false })
  recalcAndPublish()
  markDirty()
  await saveRows(false)
  equityPullVisible.value = false
  ElMessage.success(`已带入：新建 ${res.added} / 填空 ${res.filled} 行；已填 ${res.skipped} 行保持不变`)
}

async function handleAddRow(): Promise<void> {
  if (activeSection.value === 'impairment') {
    ElMessage.info('减值准备行由成本法、权益法明细自动生成')
    return
  }
  try {
    const result = await ElMessageBox.prompt('请输入被投资单位名称', '新增投资明细', {
      inputPattern: /\S+/,
      inputErrorMessage: '被投资单位名称不能为空',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (activeSection.value === 'cost') {
      state.costRows.push(createG7CostRow(state.costRows.length + 1, result.value.trim()))
    } else {
      state.equityRows.push(createG7EquityRow(state.equityRows.length + 1, result.value.trim()))
    }
    recalcAndPublish()
    markDirty()
  } catch {
    // cancelled
  }
}

async function removeRow(row: G7DetailStoredRow): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除“${row.investeeName}”及其减值明细吗？`, '删除确认', {
      type: 'warning',
    })
    if (row.section === 'cost') state.costRows.splice(state.costRows.findIndex(item => item.id === row.id), 1)
    if (row.section === 'equity') state.equityRows.splice(state.equityRows.findIndex(item => item.id === row.id), 1)
    resequenceG7DetailState(state)
    recalcAndPublish()
    markDirty()
  } catch {
    // cancelled
  }
}

function extractChecklistItems(response: any): any[] {
  if (Array.isArray(response)) return response
  if (Array.isArray(response?.data)) return response.data
  if (Array.isArray(response?.items)) return response.items
  if (Array.isArray(response?.data?.items)) return response.data.items
  return []
}

function parseJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try { return JSON.parse(value) } catch { return null }
}

function replaceState(next: G7DetailState): void {
  state.costRows.splice(0, state.costRows.length, ...next.costRows)
  state.equityRows.splice(0, state.equityRows.length, ...next.equityRows)
  state.impairmentRows.splice(0, state.impairmentRows.length, ...next.impairmentRows)
  recalcAndPublish()
  isDirty.value = false
}

async function loadRows(): Promise<void> {
  let payload: unknown = props.htmlData?.detail?.rows || props.htmlData?.rows || []
  if (props.wpId) {
    try {
      const response = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
      const items = extractChecklistItems(response)
      const stored = items.find(item => item.item_id === 'G7-2-rows')
      const note = items.find(item => item.item_id === 'G7-2-detail-audit-note')
      if (stored?.conclusion) payload = parseJson(stored.conclusion)
      if (note?.remark) auditNote.value = String(note.remark)
    } catch {
      // htmlData fallback
    }
  }
  replaceState(normalizeG7DetailRows(payload))
}

async function saveRows(silent: boolean): Promise<void> {
  if (props.isReadonly || !props.wpId || saving.value || !isDirty.value) return
  const savingRevision = editRevision
  const serialized = serializeG7DetailState(state)
  saving.value = true
  try {
    const validation = await api.post(
      `/api/workpapers/${props.wpId}/g7-main/validate-detail`,
      serialized,
      { _silent: true } as any,
    )
    const validationData = (validation as any)?.data ?? validation
    if (validationData?.ok === false) {
      validationBlocked = true
      if (!silent) {
        ElMessage.warning(`公式校验未通过：${validationData.errors?.length || 0} 项差异`)
      }
      return
    }
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: 'G7-2-rows',
        conclusion: JSON.stringify(serialized),
        remark: 'G7-2成本法/权益法/减值准备明细',
      }],
    }, { _silent: silent } as any)
    if (savingRevision === editRevision) isDirty.value = false
    if (!silent) ElMessage.success('G7-2 明细已保存')
    publishDetail()
    try {
      const { emitG7SourceRowsSaved } = await import('../../composables/g7DisclosureCrossSheet')
      emitG7SourceRowsSaved({
        projectId: props.projectId,
        wpId: props.wpId,
        itemIds: ['G7-2-rows'],
      })
    } catch { /* ignore */ }
  } catch {
    validationBlocked = true
    if (!silent) ElMessage.error('G7-2 明细保存失败')
  } finally {
    saving.value = false
    if (isDirty.value && !validationBlocked) queueAutoSave()
  }
}

async function saveNote(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: 'G7-2-detail-audit-note', conclusion: null, remark: auditNote.value }],
    }, { _silent: true } as any)
  } catch {
    // Non-blocking narrative field.
  }
}

const ie = useG7ImportExport({ wpId: computed(() => props.wpId) })

async function handleDropdownCommand(command: string): Promise<void> {
  if (command === 'template') await ie.exportTemplate('G7-2')
  if (command === 'export') {
    if (isDirty.value) await saveRows(true)
    await ie.exportData('G7-2')
  }
  if (command !== 'import') return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (event: Event) => {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await ie.importData('G7-2', file)
    if (result) await loadRows()
  }
  input.click()
}

function fmtAmount(value: unknown): string {
  const n = Number(value || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatCell(value: unknown, kind: ColumnKind): string {
  if (kind === 'number') return fmtAmount(value)
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- percentage display, not monetary amount
  if (kind === 'percent') return `${(Number(value || 0) * 100).toFixed(2)}%`
  if (kind === 'select') {
    const options = [
      { value: 'subsidiary', label: '子公司' },
      ...relationshipOptions,
    ]
    return options.find(option => option.value === value)?.label || String(value || '')
  }
  return String(value || '')
}

onMounted(() => { void loadRows() })
onBeforeUnmount(() => {
  if (saveTimer) window.clearTimeout(saveTimer)
  if (isDirty.value) void saveRows(true)
})
</script>

<style scoped>
.g7-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.diff-red { color: var(--el-color-danger); font-weight: 600; }
.equity-pull-note { margin-bottom: 10px; }
.section-head, .navigation-row, .layer-row, .card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.section-head { margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; }
.sheet-subtitle { margin-top: 4px; color: #909399; font-size: 12px; }
.head-actions, .navigation-meta { display: flex; align-items: center; gap: 8px; }
.audit-objective { margin-bottom: 12px; }
.navigation-row { flex-wrap: wrap; margin-bottom: 10px; }
.layer-row {
  justify-content: flex-start;
  flex-wrap: wrap;
  padding: 8px 10px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-bottom: 0;
}
.layer-label { color: #606266; }
.formula-hint { margin-left: auto; color: #909399; font-size: 12px; }
.detail-table { width: 100%; }
.number-input, :deep(.el-date-editor) { width: 100%; }
.formula-cell {
  color: #337ecc;
  border-bottom: 1px dashed #79bbff;
  display: inline-block;
  min-width: 50px;
  cursor: help;
}
.section-total {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  border: 1px solid #ebeef5;
  border-top: 0;
  background: #fafafa;
}
.section-total strong { min-width: 140px; text-align: right; color: #337ecc; font-size: 15px; }
.summary-cards { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; margin: 8px 0 14px; }
.summary-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border: 1px solid #c6e2ff;
  border-radius: 6px;
  background: #ecf5ff;
}
.summary-card span { color: #606266; }
.summary-card strong { color: #337ecc; font-size: 20px; }
.summary-card.impairment { border-color: #fde2e2; background: #fef0f0; }
.summary-card.impairment strong { color: #f56c6c; }
.summary-card.net { border-color: #b3e19d; background: #f0f9eb; }
.summary-card.net strong { color: #529b2e; }
.summary-table { margin-bottom: 12px; }
.cross-reference { margin: 12px 0; }
.note-card { margin-top: 14px; }
.prep-hint { margin-top: 14px; color: #606266; font-size: 12px; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ol { margin: 8px 0 0; padding-left: 20px; line-height: 1.8; }
@media (max-width: 900px) {
  .section-head { align-items: flex-start; flex-direction: column; }
  .summary-cards { grid-template-columns: 1fr; }
}
</style>
