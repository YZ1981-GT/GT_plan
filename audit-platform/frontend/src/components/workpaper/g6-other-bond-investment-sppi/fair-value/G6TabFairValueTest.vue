<template>
  <div class="g6-tab-fair-value-test" data-testid="g6-fair-value">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实其他债权投资以公允价值计量的恰当性；验证数量×单价勾稽、未审/审定层次划分与估值证据充分性，确认 FVOCI 计量准确。"
      class="objective-alert"
    />

    <div class="methodology-context">
      <p class="methodology-title">编制逻辑（对齐 Excel G6-5）：</p>
      <p>① 公允价值 = 数量 × 单位公允价值（自动计算）</p>
      <p>② 差异 = 审定公允价值 − 未审公允价值 = 数量影响 + 价格影响</p>
      <p>③ 未审/审定公允价值层次分列；L1/L2/L3 分层取证</p>
      <p>④ |差异|&gt;0.01 须填写差异原因</p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-5" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G6-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ fairValue.rows.value.length }} 行</el-tag>
        <el-tag v-if="fairValue.diffCount.value > 0" size="small" type="danger">
          {{ fairValue.diffCount.value }} 项差异
        </el-tag>
        <el-tag v-if="fairValue.missingDiffReasonCount.value > 0" size="small" type="warning">
          {{ fairValue.missingDiffReasonCount.value }} 项缺原因
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="handleAi">
          🤖 AI辅助
        </el-button>
        <el-button size="small" @click="openReview('G6-5-fair-value')">💬复核</el-button>
      </div>
    </div>

    <el-segmented
      v-model="fairValue.activeTab.value"
      :options="segmentOptions"
      size="small"
      class="segment-bar"
    />

    <!-- ═══ Tab1: 基础+审定 ═══ -->
    <el-card v-show="fairValue.activeTab.value === 'tab1'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">基础 + 审定</span>
          <span class="header-hint">公允价值由数量×单价自动计算</span>
        </div>
      </template>

      <el-table
        :data="displayRows"
        border
        size="small"
        class="fv-table"
        highlight-current-row
        :current-row-key="currentRowId"
        row-key="id"
        :row-class-name="rowClassName"
        max-height="480"
        @current-change="handleRowChange"
      >
        <el-table-column label="序号" width="55" align="center" fixed>
          <template #default="{ row }">
            <span v-if="row._isTotal" class="total-label">合计</span>
            <span v-else>{{ row.seq }}</span>
          </template>
        </el-table-column>

        <el-table-column label="投资项目" min-width="140" fixed>
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <div v-else class="name-cell">
              <el-input
                v-if="!isReadonly"
                :model-value="row.investProject"
                size="small"
                @change="(v: string) => fairValue.updateRow(row.id, 'investProject', v)"
              />
              <span v-else>{{ row.investProject }}</span>
              <el-button
                v-if="!isReadonly"
                size="small"
                type="danger"
                link
                @click="fairValue.removeRow(row.id)"
              >删除</el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="期末未审" align="center">
          <el-table-column label="数量" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row._isTotal && !isReadonly"
                :model-value="row.unadjQty"
                size="small"
                :controls="false"
                :precision="0"
                class="amt"
                @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'unadjQty', v ?? 0)"
              />
              <span v-else>{{ row._isTotal ? '' : row.unadjQty }}</span>
            </template>
          </el-table-column>
          <el-table-column label="单位公允价值" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!row._isTotal && !isReadonly"
                :model-value="row.unadjPrice"
                size="small"
                class="amt"
                @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'unadjPrice', v ?? 0)"
              />
              <span v-else>{{ row._isTotal ? '' : fmtNum(row.unadjPrice, 4) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="120" align="right">
            <template #default="{ row }">
              <el-tooltip content="未审公允价值 = 数量 × 单位公允价值" placement="top">
                <span class="formula-cell">{{ fmtNum(row.unadjFairValue) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="层次" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!row._isTotal && !isReadonly"
                :model-value="row.unadjFairValueLevel"
                size="small"
                placeholder="层次"
                style="width: 100%"
                @change="(v: string) => fairValue.updateRow(row.id, 'unadjFairValueLevel', v)"
              >
                <el-option value="L1" label="L1" />
                <el-option value="L2" label="L2" />
                <el-option value="L3" label="L3" />
              </el-select>
              <span v-else-if="!row._isTotal">{{ row.unadjFairValueLevel || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末审定" align="center">
          <el-table-column label="数量" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!row._isTotal && !isReadonly"
                :model-value="row.auditedQty"
                size="small"
                :controls="false"
                :precision="0"
                class="amt"
                @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'auditedQty', v ?? 0)"
              />
              <span v-else>{{ row._isTotal ? '' : row.auditedQty }}</span>
            </template>
          </el-table-column>
          <el-table-column label="单位公允价值" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!row._isTotal && !isReadonly"
                :model-value="row.auditedPrice"
                size="small"
                class="amt"
                @update:model-value="(v: number | undefined) => fairValue.updateRow(row.id, 'auditedPrice', v ?? 0)"
              />
              <span v-else>{{ row._isTotal ? '' : fmtNum(row.auditedPrice, 4) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="120" align="right">
            <template #default="{ row }">
              <el-tooltip content="审定公允价值 = 数量 × 单位公允价值" placement="top">
                <span class="formula-cell">{{ fmtNum(row.auditedFairValue) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="层次" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!row._isTotal && !isReadonly"
                :model-value="row.auditedFairValueLevel"
                size="small"
                placeholder="层次"
                :class="{ 'level-warn': fairValue.hasL3Errors(row) }"
                style="width: 100%"
                @change="(v: string) => fairValue.updateRow(row.id, 'auditedFairValueLevel', v)"
              >
                <el-option value="L1" label="L1" />
                <el-option value="L2" label="L2" />
                <el-option value="L3" label="L3" />
              </el-select>
              <el-tag
                v-else-if="!row._isTotal"
                :type="row.auditedFairValueLevel === 'L3' ? 'danger' : 'info'"
                size="small"
              >{{ row.auditedFairValueLevel || '-' }}</el-tag>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="差异分析" align="center">
          <el-table-column label="数量影响" width="100" align="right">
            <template #default="{ row }">
              <el-tooltip content="（审定数量−未审数量）×未审单价" placement="top">
                <span class="formula-cell">{{ fmtNum(row.qtyImpact) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="价格影响" width="100" align="right">
            <template #default="{ row }">
              <el-tooltip content="审定数量×（审定单价−未审单价）" placement="top">
                <span class="formula-cell">{{ fmtNum(row.priceImpact) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="总差异" width="110" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                :style="row._isTotal ? {} : fairValue.getDiffCellStyle(row)"
                title="总差异 = 审定公允价值 − 未审公允价值"
              >{{ fmtNum(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异原因" min-width="140">
            <template #default="{ row }">
              <el-input
                v-if="!row._isTotal && !isReadonly"
                :model-value="row.diffReason"
                size="small"
                :class="{ 'reason-required': fairValue.hasDifference(row) && !row.diffReason }"
                :placeholder="fairValue.hasDifference(row) ? '差异>0.01，必填' : ''"
                @change="(v: string) => fairValue.updateRow(row.id, 'diffReason', v)"
              />
              <span v-else-if="!row._isTotal">{{ row.diffReason || '' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Tab2: 估值详情 ═══ -->
    <el-card v-show="fairValue.activeTab.value === 'tab2'" shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">估值详情（按审定层次取证）</span>
        </div>
      </template>

      <el-table
        :data="fairValue.rows.value"
        border
        size="small"
        class="fv-table"
        highlight-current-row
        :current-row-key="currentRowId"
        row-key="id"
        max-height="480"
        @current-change="handleRowChange"
      >
        <el-table-column type="index" label="序号" width="50" align="center" />
        <el-table-column label="投资项目" prop="investProject" min-width="120" />
        <el-table-column label="审定层次" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.auditedFairValueLevel === 'L3' ? 'danger' : row.auditedFairValueLevel === 'L2' ? 'warning' : 'success'"
              size="small"
            >{{ row.auditedFairValueLevel || '未设' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationMethod"
              size="small"
              :class="{ 'field-required': needField(row, 'valuationMethod') }"
              placeholder="估值方法..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'valuationMethod', v)"
            />
            <span v-else>{{ row.valuationMethod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致性" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.consistencyWithPrior"
              size="small"
              placeholder="选择"
              style="width: 100%"
              @change="(v: string) => fairValue.updateRow(row.id, 'consistencyWithPrior', v)"
            >
              <el-option value="一致" label="一致" />
              <el-option value="不一致" label="不一致" />
              <el-option value="首次" label="首次" />
            </el-select>
            <span v-else>{{ row.consistencyWithPrior || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源说明(L1/L2)" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.sourceInstitution"
              size="small"
              :class="{ 'field-required': needField(row, 'sourceInstitution') }"
              placeholder="活跃市场报价/来源机构..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'sourceInstitution', v)"
            />
            <span v-else>{{ row.sourceInstitution || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可观察输入值(L2)" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.inputSource"
              size="small"
              :class="{ 'field-required': needField(row, 'inputSource') }"
              placeholder="收益率曲线/信用利差..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'inputSource', v)"
            />
            <span v-else>{{ row.inputSource || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值技术(L3)" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationTechnique"
              size="small"
              :class="{ 'field-required': needField(row, 'valuationTechnique') }"
              placeholder="DCF/期权模型..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'valuationTechnique', v)"
            />
            <span v-else>{{ row.valuationTechnique || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="不可观察输入值(L3)" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.unobservableInputs"
              size="small"
              :class="{ 'field-required': needField(row, 'unobservableInputs') }"
              placeholder="折现率/波动率..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'unobservableInputs', v)"
            />
            <span v-else>{{ row.unobservableInputs || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="输入值/估值结果(L3)" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.inputValue"
              size="small"
              :class="{ 'field-required': needField(row, 'inputValue') }"
              placeholder="16% / 2% / ..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'inputValue', v)"
            />
            <span v-else>{{ row.inputValue || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值文件索引" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationFileRef"
              size="small"
              :class="{ 'field-required': needField(row, 'valuationFileRef') }"
              placeholder="索引..."
              @update:model-value="(v: string) => fairValue.updateRow(row.id, 'valuationFileRef', v)"
            />
            <span v-else>{{ row.valuationFileRef || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        v-if="fairValue.l3ValidationSummary.value.length > 0"
        type="warning"
        :closable="false"
        class="level-alert"
      >
        <template #title>分层取证未完整（{{ fairValue.l3ValidationSummary.value.length }} 项）</template>
        <ul class="error-list">
          <li v-for="item in fairValue.l3ValidationSummary.value" :key="item.row.id">
            {{ item.row.investProject }}（{{ item.row.auditedFairValueLevel || '未设' }}）：缺少{{ item.errors.join('、') }}
          </li>
        </ul>
      </el-alert>
    </el-card>

    <div class="bottom-actions">
      <el-button v-if="!isReadonly" type="primary" size="small" @click="fairValue.addRow()">
        + 新增行
      </el-button>
      <G6SppiImportExportDropdown
        v-if="wpId"
        :wp-id="wpId"
        sheet="G6-5"
        :disabled="isReadonly"
        @imported="emit('imported')"
      />
    </div>

    <div class="summary-bar">
      <el-tag type="success" size="small">L1: {{ fairValue.levelSummary.value.L1 }}</el-tag>
      <el-tag type="warning" size="small">L2: {{ fairValue.levelSummary.value.L2 }}</el-tag>
      <el-tag type="danger" size="small">L3: {{ fairValue.levelSummary.value.L3 }}</el-tag>
      <el-tag v-if="fairValue.levelSummary.value.unset > 0" type="info" size="small">
        未设: {{ fairValue.levelSummary.value.unset }}
      </el-tag>
      <span class="sum-item">未审合计 <strong>{{ fmtNum(fairValue.totals.value.unadjFairValue) }}</strong></span>
      <span class="sum-item">审定合计 <strong>{{ fmtNum(fairValue.totals.value.auditedFairValue) }}</strong></span>
      <span class="sum-item" :class="{ 'sum-diff': Math.abs(fairValue.totals.value.difference) > 0.01 }">
        差异合计 <strong>{{ fmtNum(fairValue.totals.value.difference) }}</strong>
      </span>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header"><span class="section-title">审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="概述公允价值来源与估值方法测试情况、数量/价格差异原因、L3关键假设评价、拟调整与未调整事项。"
        @update:model-value="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">审计结论</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="handleAi">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="fairValue.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述调整外其余未见异常。C、存在重大未调整事项，不可确认。"
        @input="handleSave"
      />
    </el-card>

    <details class="guide-details">
      <summary>编制提示</summary>
      <div class="guide-content">
        <p>1. 公允价值 = 数量 × 单位公允价值；勿手工改公允价值列。</p>
        <p>2. 差异 = 数量影响 + 价格影响；|差异|&gt;0.01 须填差异原因。</p>
        <p>3. L1：活跃市场报价来源；L2：可观察输入值；L3：估值技术+不可观察参数+输入值+文件索引。</p>
        <p>4. 第一层次仅限活跃市场未调整报价；有重大调整或不可观察输入值应归 L2/L3。</p>
        <p>5. 审定公允价值合计应与 G6-2 期末公允价值 / G6-1「一、公允价值」勾稽。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G6TabFairValueTest.vue — 对齐 Excel《公允价值测试表G6-5》
 */
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  useG6SppiFairValue,
  pickG6FairValuePayload,
  type FairValueItem,
} from '../../composables/useG6SppiFairValue'
import { useG6SppiFormData } from '../../composables/useG6SppiFormData'
import { useG6SppiAiGenerate } from '../../composables/useG6SppiAiGenerate'
import { parseG6ChecklistPayload } from '../../composables/g6CrossHelpers'
import GtIndexChip from '../../GtIndexChip.vue'
import G6SppiImportExportDropdown from '../G6SppiImportExportDropdown.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
function openReview(sectionId: string): void {
  openReviewDialog(sectionId)
}

const formData = useG6SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const fairValue = useG6SppiFairValue()
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, loading: aiLoading } = useG6SppiAiGenerate(wpIdRef)

const segmentOptions = [
  { label: '基础+审定', value: 'tab1' },
  { label: '估值详情', value: 'tab2' },
]

type DisplayRow = FairValueItem & { _isTotal?: boolean }

const displayRows = computed<DisplayRow[]>(() => {
  const list = fairValue.rows.value
  if (!list.length) return []
  const t = fairValue.totals.value
  const totalRow: DisplayRow = {
    ...list[0],
    id: '__total__',
    seq: 0,
    investProject: '',
    _isTotal: true,
    unadjFairValue: t.unadjFairValue,
    auditedFairValue: t.auditedFairValue,
    qtyImpact: t.qtyImpact,
    priceImpact: t.priceImpact,
    difference: t.difference,
  }
  return [...list, totalRow]
})

const currentRowId = computed(() => {
  const rows = fairValue.rows.value
  if (!rows.length) return ''
  return rows[fairValue.selectedRowIndex.value]?.id || rows[0]?.id || ''
})

function handleRowChange(row: FairValueItem | null): void {
  if (!row || (row as DisplayRow)._isTotal) return
  const idx = fairValue.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) fairValue.selectedRowIndex.value = idx
}

function rowClassName({ row }: { row: DisplayRow }): string {
  return row._isTotal ? 'row-total' : ''
}

function needField(row: FairValueItem, field: string): boolean {
  const errors = fairValue.getLevelValidationErrors(row)
  const labels: Record<string, string> = {
    valuationMethod: '估值方法',
    sourceInstitution: '公允价值来源说明',
    inputSource: '可观察输入值来源',
    valuationTechnique: '估值技术',
    unobservableInputs: '不可观察输入值',
    inputValue: '输入值/估值结果',
    valuationFileRef: '估值文件索引',
  }
  return errors.includes(labels[field] || '')
}

const DATA_KEY = 'G6-5-fair-value-data'
const NOTE_KEY = 'G6-5-fair-value-test-audit-note'
const auditNote = ref('')
let hydrating = false

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

onMounted(async () => {
  await formData.loadAll()
  initFromData()
  const noteResp = formData.allResponses.value.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
})

onBeforeUnmount(() => {
  flushPersist()
})

watch(() => props.htmlData, (newData) => {
  // 已有 checklist 落库时勿被 render-config 空壳覆盖
  if (newData && !formData.allResponses.value.get(DATA_KEY)) initFromData()
})

function initFromData(): void {
  hydrating = true
  try {
    const checklist = parseG6ChecklistPayload(formData.allResponses.value.get(DATA_KEY))
    const content = formData.parseContent()
    const payload = pickG6FairValuePayload(
      checklist,
      content.fairValue,
      props.htmlData?.fairValue,
    )
    if (payload) fairValue.loadData(payload)
  } finally {
    hydrating = false
  }
}

function handleSave(): void {
  if (props.isReadonly || hydrating) return
  formData.debouncedSave(DATA_KEY, {
    conclusion: JSON.stringify(fairValue.toJSON()),
  })
}

function flushPersist(): void {
  handleSave()
  formData.flushPending()
}

watch(() => fairValue.rows.value, () => { handleSave() }, { deep: true })
watch(() => fairValue.conclusion.value, () => { handleSave() })

async function handleAi(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'fair-value-conclusion',
    fairValue.conclusion.value || '',
    {
      rowCount: fairValue.rows.value.length,
      diffCount: fairValue.diffCount.value,
      levelSummary: fairValue.levelSummary.value,
      totals: fairValue.totals.value,
    },
    'AI 公允价值审计结论',
  )
  if (text) {
    fairValue.conclusion.value = text
    handleSave()
  }
}

function fmtNum(v: number | undefined, decimals = 2): string {
  if (v === undefined || v === null) return '-'
  if (Math.abs(Number(v)) < 0.0000001) return '-'
  return Number(v).toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

defineExpose({ toJSON: () => fairValue.toJSON() })
</script>

<style scoped>
.g6-tab-fair-value-test { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 4px solid #d97706; background: #fffbeb;
  padding: 10px 14px; margin-bottom: 12px; border-radius: 0 4px 4px 0;
  font-size: 12px; line-height: 1.7; color: #92400e;
}
.methodology-title { font-weight: 600; margin: 0 0 4px; color: #78350f; }
.methodology-context p { margin: 2px 0; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.segment-bar { margin-bottom: 12px; }
.section-card { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.section-title { font-weight: 600; font-size: 14px; }
.header-hint { font-size: 12px; color: #909399; }
.fv-table { font-size: var(--wp-font-size, 13px); }
.name-cell { display: flex; align-items: center; gap: 6px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.amt { width: 100%; }
.amt :deep(.el-input__inner) { text-align: right; }
.total-label { font-weight: 700; }
:deep(.row-total) { background: #f0f9eb !important; font-weight: 600; }
:deep(.reason-required .el-input__wrapper),
:deep(.field-required .el-input__wrapper),
:deep(.level-warn .el-select__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}
.level-alert { margin-top: 12px; }
.error-list { margin: 4px 0 0 16px; padding: 0; font-size: 12px; }
.bottom-actions { display: flex; gap: 12px; align-items: center; margin: 12px 0; }
.summary-bar {
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  margin-bottom: 12px; padding: 8px 12px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: 13px; color: #606266;
}
.sum-item strong { color: #303133; }
.sum-diff strong { color: #dc2626; }
.conclusion-card { margin-bottom: 16px; }
.guide-details { margin-top: 12px; }
.guide-details summary { cursor: pointer; font-size: 13px; color: #606266; font-weight: 600; }
.guide-content {
  padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b;
  margin-top: 6px; font-size: 12px; line-height: 1.8;
}
.guide-content p { margin: 0; }
</style>
