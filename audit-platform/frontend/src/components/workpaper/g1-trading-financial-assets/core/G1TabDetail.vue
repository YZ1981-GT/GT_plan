<template>
  <div class="g1-detail">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-2 交易性金融资产明细表</h3>
        <p class="sheet-sub">
          成本与累计公允变动双桶滚动：期初审定 → 本期变动 → 期末审定 → 报表列报，勾稽 G1-1 / 科目 1501
        </p>
      </div>
      <div class="head-actions">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-2"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">+ 新增项目</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实交易性金融资产的存在、完整、权利与计价；验证成本与累计公允变动滚动及分类列报恰当，为审定表（G1-1）提供明细支撑。"
      class="objective-alert"
    />

    <!-- 编制闸门：把「编制说明」变成可完成步骤 -->
    <section class="gates-card">
      <header class="gates-head">
        <div>
          <h4>编制闸门</h4>
          <p>完成后再填明细；对应 Excel「编制说明【非打印】」</p>
        </div>
        <el-tag :type="gatesReady ? 'success' : 'warning'" size="small" effect="plain">
          {{ gatesReady ? '已就绪' : '待完成' }}
        </el-tag>
      </header>

      <div class="gates-grid">
        <label class="gate-item">
          <el-checkbox
            :model-value="gates.inclusionReviewed"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateGates({ inclusionReviewed: !!v })"
          />
          <span>
            <strong>入表范围已复核</strong>
            <small>未通过 SPPI / 其他业务模式 / 非套期衍生 / 持有≤1年权益 / 指定 FVPL（≤1年）等五类才入本表</small>
          </span>
        </label>
        <label class="gate-item">
          <el-checkbox
            :model-value="gates.fxNoted"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateGates({ fxNoted: !!v })"
          />
          <span>
            <strong>外币项目已注明</strong>
            <small>外币资产在「准入基础」填写原币与折算汇率；明细按明细科目列示</small>
          </span>
        </label>
        <label class="gate-item">
          <el-checkbox
            :model-value="gates.fraudRiskAssessed"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateGates({ fraudRiskAssessed: !!v })"
          />
          <span>
            <strong>第三方资金舞弊风险已评估</strong>
            <small>参照《中国注册会计师审计准则问题解答第18号》关注空转资金等风险因素</small>
          </span>
        </label>
        <label class="gate-item">
          <el-checkbox
            :model-value="gates.fraudRiskFlag"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateGates({ fraudRiskFlag: !!v })"
          />
          <span>
            <strong>识别到风险因素</strong>
            <small>若勾选，须填写应对措施</small>
          </span>
        </label>
      </div>

      <el-alert
        v-if="classificationWarnings.length"
        type="warning"
        :closable="false"
        show-icon
        class="class-warn"
        :title="`与 G1-9 分类结论不一致（${classificationWarnings.length}）`"
        :description="classificationWarnings.slice(0, 5).join('；')"
      />

      <el-input
        v-if="gates.fraudRiskFlag"
        :model-value="gates.fraudResponse"
        type="textarea"
        :rows="2"
        :disabled="isReadonly"
        placeholder="舞弊风险应对措施（程序、范围、追加证据等）"
        class="fraud-response"
        @update:model-value="(v: string) => updateGates({ fraudResponse: v })"
      />

      <details class="guidance-details">
        <summary>披露与结论提示（折叠）</summary>
        <div class="guidance-content">
          <p>提示：交易性金融资产与「以公允价值计量且其变动计入当期损益的金融资产」在附注中合并披露为后者名称。</p>
          <p>注1：已到期应计利息在「应收利息」核算，不在本表明细列示。</p>
          <p>结论口径 — A：未发现异常；B：除重大调整外未见其他异常；C：因未调整事项或范围受限无法确认。</p>
        </div>
      </details>
    </section>

    <!-- 勾稽状态条 -->
    <div class="status-bar" :class="balanceStatus.ok ? 'ok' : 'warn'">
      <span class="status-main">{{ balanceStatus.message }}</span>
      <span class="status-meta">
        期末审定 {{ fmtCell(grandTotal.auditedClosingFvTotal) }}
        · 报表数 {{ fmtCell(grandTotal.closingReported) }}
        · 质押 {{ balanceStatus.pledgedCount }}
        · 受限 {{ balanceStatus.restrictedCount }}
      </span>
      <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
    </div>

    <div class="tab-toolbar">
      <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />
      <el-tag size="small" type="info" effect="plain">共 {{ rows.length }} 行</el-tag>
      <el-popover placement="bottom-end" :width="260" trigger="click">
        <template #reference>
          <el-button size="small" :icon="Setting" plain>列设置</el-button>
        </template>
        <div class="col-prefs">
          <div class="col-prefs-head">
            <span>当前区段列显隐</span>
            <div>
              <el-button size="small" link @click="colPrefs.hideEmptyColumns()">隐藏空列</el-button>
              <el-button size="small" link @click="colPrefs.resetCurrentSegment()">全部显示</el-button>
            </div>
          </div>
          <div class="col-prefs-list">
            <el-checkbox
              v-for="col in colPrefs.configurableColumns.value"
              :key="String(col.prop)"
              :model-value="colPrefs.isVisible(String(col.prop))"
              @change="(v: boolean | string | number) => colPrefs.setColumnVisible(String(col.prop), !!v)"
            >
              {{ col.label }}
            </el-checkbox>
          </div>
        </div>
      </el-popover>
    </div>
    <p v-if="currentSegmentHint" class="segment-hint">{{ currentSegmentHint }}</p>

    <el-table
      :data="rows"
      border
      stripe
      size="small"
      max-height="500"
      highlight-current-row
      class="detail-table"
    >
      <el-table-column prop="securityName" label="投资项目" width="140" fixed />

      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' || col.formula ? 'right' : undefined"
      >
        <template #default="{ row }">
          <span v-if="col.formula" class="formula-cell" :title="formulaHint(col.prop)">
            {{ fmtCell(row[col.prop]) }}
          </span>
          <el-select
            v-else-if="col.type === 'invest'"
            v-model="row.investType"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { investType: row.investType })"
          >
            <el-option v-for="o in investOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-select
            v-else-if="col.type === 'acct'"
            v-model="row.acctClass"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { acctClass: row.acctClass })"
          >
            <el-option v-for="o in acctOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-select
            v-else-if="col.type === 'level'"
            v-model="row.fairValueSource"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { fairValueSource: row.fairValueSource })"
          >
            <el-option value="1" label="Level 1" />
            <el-option value="2" label="Level 2" />
            <el-option value="3" label="Level 3" />
          </el-select>
          <el-checkbox
            v-else-if="col.type === 'flag'"
            :model-value="!!row[col.prop]"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateRow(row.id, { [col.prop]: !!v })"
          />
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else-if="col.type === 'date'"
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            placeholder="YYYY-MM-DD"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right" align="center">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-panel">
      <div v-for="st in subtotalsByAcct" :key="st.key" class="subtotal-line">
        <span class="subtotal-label">{{ st.label }}</span>
        <span class="subtotal-meta">{{ st.count }} 项</span>
        <span>期初审定 {{ fmtCell(st.totals.auditedOpeningFvTotal) }}</span>
        <span>期末审定 {{ fmtCell(st.totals.auditedClosingFvTotal) }}</span>
        <span>报表数 {{ fmtCell(st.totals.closingReported) }}</span>
      </div>
      <div v-for="st in subtotalsByType" :key="`t-${st.key}`" class="subtotal-line type-line">
        <span class="subtotal-label">{{ st.label }}小计</span>
        <span class="subtotal-meta">{{ st.count }} 项</span>
        <span>期末成本 {{ fmtCell(st.totals.closingCost) }}</span>
        <span>公允价值 {{ fmtCell(st.totals.closingFairValue) }}</span>
        <span>审定 {{ fmtCell(st.totals.adjusted) }}</span>
      </div>
      <div class="grand-total">
        <span class="subtotal-label">总计</span>
        <span>期末成本 {{ fmtCell(grandTotal.closingCost) }}</span>
        <span>公允价值 {{ fmtCell(grandTotal.closingFairValue) }}</span>
        <span>投资收益 {{ fmtCell(grandTotal.totalIncome) }}</span>
        <span>期末审定 {{ fmtCell(grandTotal.auditedClosingFvTotal) }}</span>
        <span>报表数 {{ fmtCell(grandTotal.closingReported) }}</span>
      </div>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      :related-context="{
        明细行数: rows.length,
        闸门就绪: gatesReady,
        滚动勾稽: balanceStatus.message,
        期末成本合计: grandTotal.closingCost,
        期末公允价值合计: grandTotal.closingFairValue,
        期末审定合计: grandTotal.auditedClosingFvTotal,
        期末报表数合计: grandTotal.closingReported,
        投资收益合计: grandTotal.totalIncome,
        质押项数: balanceStatus.pledgedCount,
        变现受限项数: balanceStatus.restrictedCount,
      }"
      note-placeholder="审计说明：（1）程序与结果；（2）提议调整及分录；（3）未调整事项及影响；（4）范围受限及影响。利息/股利与账面核对情况可在此说明。"
      note-hint="覆盖明细核对、双桶滚动勾稽、公允层级、调整/未调整/范围受限及与 G1-1 勾稽。"
      conclusion-hint="按 A/B/C：未见异常 / 除重大调整外未见异常 / 因未调整或范围受限无法确认。"
      conclusion-placeholder="选择结论口径 A / B / C，并据实改写。"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, watch } from 'vue'
import {
  useG1Detail,
  G1_INVEST_TYPE_OPTIONS,
  G1_ACCT_CLASS_OPTIONS,
  type TradingDetailRow,
} from '../../composables/useG1Detail'
import { useG1DetailColumnPrefs } from '../../composables/useG1DetailColumnPrefs'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { Setting } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const {
  segments,
  segment,
  rows,
  subtotalsByType,
  subtotalsByAcct,
  grandTotal,
  balanceStatus,
  gates,
  gatesReady,
  classificationWarnings,
  addRow,
  updateRow,
  updateGates,
  removeRow,
  loadAll,
} = useG1Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const wpId = computed(() => props.wpId ?? '')

const AUDIT_NOTE_KEY = 'G1-2-audit-note'
const AUDIT_CONCLUSION_KEY = 'G1-2-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark ?? '')

watch(
  () => props.allResponses.get(AUDIT_NOTE_KEY)?.remark,
  (v) => { if (v != null) auditNote.value = v },
)
watch(
  () => props.allResponses.get(AUDIT_CONCLUSION_KEY)?.remark,
  (v) => { if (v != null) auditConclusion.value = v },
)
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: null, remark: v })
})

const investOptions = G1_INVEST_TYPE_OPTIONS
const acctOptions = G1_ACCT_CLASS_OPTIONS
const segmentOptions = segments.map((s) => ({ label: s.label, value: s.key }))

// 列显隐偏好（⚙ 列设置）
const colPrefs = useG1DetailColumnPrefs({
  segments,
  currentSegmentKey: segment,
  rows,
})
const currentColumns = colPrefs.visibleColumns

const currentSegmentHint = computed(
  () => segments.find((s) => s.key === segment.value)?.hint ?? '',
)

const FORMULA_HINTS: Partial<Record<keyof TradingDetailRow, string>> = {
  openingFairValue: '期初公允价值 = 期初成本 + 期初累计公允变动',
  auditedOpeningCost: '期初审定成本 = 期初成本 + 期初成本调整',
  auditedOpeningCumulativeFv: '期初审定累计FV = 期初累计公允变动 + 期初公允调整',
  auditedOpeningFvTotal: '期初审定公允价值 = 期初审定成本 + 期初审定累计FV',
  openingReported: '期初报表数 = 期初审定公允价值 − 一年以上扣减',
  closingQuantity: '期末数量 = 期初 + 买入 − 卖出',
  closingCost: '期末成本 = 期初审定成本 + 本期增加 − 本期减少',
  cumulativeFVChange: '期末累计公允变动 = 期初审定累计FV + 本期公允变动',
  closingFairValue: '有单位公允：数量×单价；否则 = 期末成本 + 期末累计公允变动',
  fairValueChange: '公允变动验算 = 期末公允价值 − 期初审定公允价值',
  auditedClosingCost: '期末审定成本 = 期末成本 + 期末成本调整',
  auditedClosingCumulativeFv: '期末审定累计FV = 期末累计公允变动 + 期末公允调整',
  auditedClosingFvTotal: '期末审定公允价值 = 审定成本 + 审定累计FV + AJE + RJE',
  closingReported: '期末报表数 = 期末审定公允价值 − 一年以上扣减',
  rollForwardDiff: '账面双桶合计 − 市价（无市价时为 0）',
  realizedGain: '已实现损益 = 处置收入 − 处置成本',
  totalIncome: '投资收益合计 = 已实现损益 + 利息/股利',
  adjusted: '审定余额(勾稽) = 期末审定公允价值',
  unadjusted: '未审余额 = 期末公允价值',
  variance: '差异 = 期末审定公允价值 − 期末公允价值',
}

function formulaHint(prop: keyof TradingDetailRow): string {
  return FORMULA_HINTS[prop] ?? ''
}

function fmtCell(v: unknown): string {
  if (typeof v === 'boolean') return v ? '是' : '否'
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}

function onImported() {
  emit('imported')
  loadAll()
}
</script>

<style scoped>
.g1-detail {
  padding: 4px 4px 20px;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.g1-detail :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.g1-detail :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.title-block { min-width: 200px; }
.sheet-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #1f2a37;
}
.sheet-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: #86909c;
  line-height: 1.4;
}
.head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.objective-alert { margin-bottom: 12px; }

.gates-card {
  margin-bottom: 12px;
  border: 1px solid #e8ecf2;
  border-left: 3px solid #3d6b8e;
  background: #f7fafc;
  border-radius: 6px;
  padding: 12px 14px;
}
.gates-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.gates-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #1f2a37;
}
.gates-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: #86909c;
}
.gates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px 16px;
}
.gate-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  cursor: pointer;
  font-size: 12px;
  color: #4e5969;
  line-height: 1.45;
}
.gate-item strong {
  display: block;
  color: #1f2a37;
  font-weight: 600;
}
.gate-item small {
  display: block;
  color: #86909c;
  margin-top: 2px;
}
.fraud-response { margin-top: 10px; }
.class-warn { margin-top: 10px; }

.guidance-details {
  margin-top: 10px;
  border-top: 1px dashed #dce3ea;
  padding-top: 8px;
}
.guidance-details summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  color: #3d6b8e;
  list-style: none;
}
.guidance-details summary::-webkit-details-marker { display: none; }
.guidance-content {
  margin-top: 6px;
  font-size: 12px;
  color: #606266;
  line-height: 1.65;
}
.guidance-content p { margin: 2px 0; }

.status-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  border: 1px solid #e4e7ed;
}
.status-bar.ok {
  background: #f0f9f4;
  border-color: #c6e8d4;
  color: #2d6a4f;
}
.status-bar.warn {
  background: #fff8f0;
  border-color: #f0d9b8;
  color: #9a5b1a;
}
.status-main { font-weight: 600; }
.status-meta { color: #606266; flex: 1; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  flex-wrap: wrap;
  gap: 8px;
}
.segment-bar { max-width: 100%; }
.segment-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #86909c;
}
.chip-wrap { display: inline-flex; align-items: center; }
.col-prefs-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}
.col-prefs-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 300px;
  overflow-y: auto;
}

.detail-table { width: 100%; border-radius: 6px; overflow: hidden; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
}

.totals-panel {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.subtotal-line,
.grand-total {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: baseline;
}
.subtotal-label { font-weight: 600; color: #303133; min-width: 72px; }
.subtotal-meta { color: #909399; }
.type-line { opacity: 0.92; }
.grand-total {
  margin-top: 2px;
  padding-top: 8px;
  border-top: 1px solid #e4e7ed;
  font-weight: 600;
  color: #303133;
}
</style>
