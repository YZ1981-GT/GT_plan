<template>
  <div class="g10-detail" data-testid="g10-detail-table">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G10-2 交易性金融负债明细表</h3>
        <p class="sheet-sub">按项目 roll-forward → (一)初始确认 + (二)累计 FV = (三)公允价值 → 回写 G10-1</p>
      </div>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip value="wp:G10-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-5" /></span>
        <G10ImportExportDropdown :wp-id="wpId" sheet="G10-2" @imported="onImported" />
        <GtReviewTrigger section-id="G10-2-detail" />
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 对齐 Excel：期初/期末均列示 (一)初始确认金额、(二)累计公允价值变动、(三)公允价值及调整→审定。</p>
        <p>2. 本期变动分列：初始确认（增加）、公允价值变动、计入财务费用的利息、减少（清偿/终止）。</p>
        <p>3. roll-forward：期末余额 = 期初审定 + 初始确认 + FV变动 + 利息 − 减少；审定 = 期末余额 + 调整数。</p>
        <p>4. 明细审定合计应与 G10-1 (三)账面余额合计勾稽；可「↓ 从 G10-1 带入」反推明细骨架，或「↑ 回写 G10-1」按负债类型写入各分项未审数。</p>
        <p>5. 含嵌入衍生的负债须在「期末+公允价值」区段说明主合同与拆分判断；Level3 须填估值方法。</p>
        <p>6. 可「辅助核算取数」从 2101 带入项目余额；「取数并回写」一步完成取数 → G10-1 → 可选附注同步。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实交易性金融负债各项目的存在、完整与准确，验证公允价值变动计入损益的正确性，明细合计与 G10-1 审定表期末审定数勾稽一致。" />

    <div class="adj-toolbar">
      <el-button v-if="!isReadonly" size="small" type="primary" @click="detail.addRow()">+ 新增行</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g10-detail-pull-adj"
        @click="detail.pullFromAdjudication()"
      >
        ↓ 从 G10-1 带入
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        :loading="detail.auxLoading.value"
        :disabled="!projectId"
        data-testid="g10-detail-aux"
        @click="onSeedAux"
      >
        辅助核算取数
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        plain
        :loading="detail.auxLoading.value"
        :disabled="!projectId"
        data-testid="g10-detail-aux-push"
        @click="detail.seedAuxAndPushToAdjudication()"
      >
        取数并回写 G10-1
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :disabled="!detail.rows.value.length"
        data-testid="g10-detail-push-adj"
        @click="detail.pushTotalsToAdjudication()"
      >
        ↑ 回写 G10-1
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :loading="detail.procedureMarking.value"
        :disabled="!detail.rows.value.length"
        data-testid="g10-detail-mark-procedure"
        @click="onMarkProcedure"
      >
        {{ detail.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 明细程序' }}
      </el-button>
      <el-button
        v-if="jumpToSection"
        size="small"
        plain
        data-testid="g10-detail-goto-fv"
        @click="jumpToSection('G10-5')"
      >
        → G10-5 公允测试
      </el-button>
      <el-button
        v-if="jumpToSection"
        size="small"
        plain
        data-testid="g10-detail-goto-derivative"
        @click="jumpToSection('G10-8')"
      >
        → G10-8 衍生核查
      </el-button>
      <el-tag v-if="detail.derivativeDetailCount.value" size="small" type="info">
        衍生 {{ detail.derivativeDetailCount.value }}
      </el-tag>
      <el-tag v-if="detail.unmatchedDerivativeDetailCount.value" size="small" type="warning">
        未链 G10-8 {{ detail.unmatchedDerivativeDetailCount.value }}
      </el-tag>
      <el-tag v-if="detail.level3MissingMethodCount.value" size="small" type="danger">
        L3缺估值方法 {{ detail.level3MissingMethodCount.value }}
      </el-tag>
      <el-tag v-if="detail.unmatchedFvDetailCount.value && detail.rows.value.length" size="small" type="warning">
        未匹配 G10-5 {{ detail.unmatchedFvDetailCount.value }}
      </el-tag>
      <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
    </div>

    <el-alert
      v-if="detail.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g10-detail-adj-cross"
      :title="`明细审定合计 ${fmt(detail.totals.value.closingAdjusted)} 与 G10-1 审定合计 ${fmt(detail.adjudicationClosingTotal.value ?? 0)} 差异 ${fmt(detail.adjCrossVariance.value ?? 0)}`"
    />

    <el-alert
      v-if="detail.integrityIssues.value.length"
      type="error"
      :closable="false"
      show-icon
      class="cross-alert"
      title="以下明细行校验未通过"
    >
      <ul class="issue-list">
        <li v-for="(item, i) in detail.integrityIssues.value.slice(0, 8)" :key="`${item.rowId}-${i}`">
          {{ item.liabilityName }}：{{ item.message }}
        </li>
        <li v-if="detail.integrityIssues.value.length > 8">…共 {{ detail.integrityIssues.value.length }} 项</li>
      </ul>
    </el-alert>

    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />

    <el-table
      :data="detail.rows.value"
      border stripe size="small"
      style="font-size:13px;margin-top:8px"
      max-height="520"
      highlight-current-row
      row-key="rowId"
      :current-row-key="detail.currentRowKey.value"
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />

      <!-- 🔴 C-7：列集对齐权威模板 `明细表G10-2` 的 19 列 A..S（两级表头 R9/R10）。
           已移除 16 列：legacy 单值（initialAmount/openingBalance/currentIncrease/
           closingBalance/profitLossAmount）· 模板无净额拆分（currentDecrease）·
           属 G10-5/G10-6（fairValueLevel/valuationMethod）· 属 G10-8（isDerivative/
           hostContractDesc/embeddedDerivativeJudgment）· 模板无列（liabilityType/
           counterparty/contractDate/confirmationStatus/remark）。 -->
      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="类别" width="96">
          <template #header><span title="模板 A 列">类别</span></template>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.liabilityCategory" size="small"
              @change="(v: string) => detail.updateRow(row.rowId, { liabilityCategory: v })">
              <el-option v-for="c in detail.G10_LIABILITY_CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.liabilityCategory }}</span>
          </template>
        </el-table-column>
        <el-table-column label="项目" min-width="180" fixed>
          <template #header><span title="模板 B 列：按明细项目列示，如债券名称">项目</span></template>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.liabilityName" size="small"
              placeholder="如：短期融资券"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { liabilityName: v })" />
            <span v-else>{{ row.liabilityName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="116">
          <template #header><span title="模板 P 列">到期日</span></template>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.maturityDate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { maturityDate: v })" />
            <span v-else>{{ row.maturityDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="票面利率" width="104">
          <template #header><span title="模板 Q 列">票面利率</span></template>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.couponRate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { couponRate: v })" />
            <span v-else>{{ row.couponRate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应付利息" width="120" align="right">
          <template #header><span title="模板 R 列">期末应付利息</span></template>
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.accruedInterest" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { accruedInterest: v ?? 0 })" />
            <span v-else>{{ fmt(row.accruedInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发行文件索引" min-width="140">
          <template #header><span title="模板 S 列">发行文件索引</span></template>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.issuanceDocIndex" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { issuanceDocIndex: v })" />
            <span v-else>{{ row.issuanceDocIndex }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 期初：模板 C9:E9「期初余额」三分量 + F 调整 + G 审定（单列） -->
      <template v-if="detail.activeTab.value === 'opening'">
        <el-table-column label="项目" prop="liabilityName" min-width="140" fixed />
        <el-table-column label="期初余额">
          <el-table-column label="初始确认金额" width="124" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingInitialAmount" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingInitialAmount: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingInitialAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" width="138" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingFvAccum" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingFvAccum: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingFvAccum) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="118" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 E 列 =C+D">{{ fmt(row.openingFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初调整数" width="112" align="right">
          <template #header><span title="模板 F 列（负债侧调整不拆分量）">期初调整数</span></template>
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定数" width="118" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="模板 G 列 =E+F">{{ fmt(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 本期变动：模板 H9:J9（表头逐字「增加"+"/减少"—"」⇒ 净额列，无「本期减少」） -->
      <template v-if="detail.activeTab.value === 'movement'">
        <el-table-column label="项目" prop="liabilityName" min-width="140" fixed />
        <el-table-column label="本期变动（增加“+”/减少“—”）">
          <el-table-column label="初始确认金额" width="124" align="right">
            <template #header>
              <span title="模板 H 列：净额列，增加填正数、减少填负数">初始确认金额</span>
            </template>
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.movementInitialAmount" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { movementInitialAmount: v ?? 0 })" />
              <span v-else>{{ fmt(row.movementInitialAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期公允价值变动" width="138" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.movementFvChange" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { movementFvChange: v ?? 0 })" />
              <span v-else>{{ fmt(row.movementFvChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入财务费用的利息" width="150" align="right">
            <template #header>
              <span title="模板 J 列。🔴 负债利息计入财务费用同时增加负债账面价值 ⇒ 进期末累计公允价值变动（L=D+I+J）">
                计入财务费用的利息
              </span>
            </template>
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.interestExpense" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { interestExpense: v ?? 0 })" />
              <span v-else>{{ fmt(row.interestExpense) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </template>

      <!-- 期末：模板 K9:O9「期末余额」三分量 + N 调整 + O 审定（单列） -->
      <template v-if="detail.activeTab.value === 'closing'">
        <el-table-column label="项目" prop="liabilityName" min-width="140" fixed />
        <el-table-column label="期末余额">
          <el-table-column label="初始确认金额" width="124" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 K 列 =C+H（未审线）">{{ fmt(row.closingInitialAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" width="138" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 L 列 =D+I+J（含利息）">{{ fmt(row.closingFvAccum) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="118" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 M 列 =K+L">{{ fmt(row.closingFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="调整数" width="112" align="right">
          <template #header><span title="模板 N 列">调整数</span></template>
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="118" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="模板 O 列 =M+N">{{ fmt(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
        <!-- 跨表链接状态（不是模板列，是 UI 辅助） -->
        <el-table-column label="G10-5" width="88" align="center">
          <template #default="{ row }">
            <el-tag v-if="detail.fvLinkByRowId.value.has(row.rowId)" size="small" type="success">已测试</el-tag>
            <el-tag v-else-if="row.liabilityName?.trim()" size="small" type="info">未匹配</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="G10-8" width="72" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="detail.derivativeLinkByRowId.value.get(row.rowId)?.linked"
              size="small"
              type="success"
            >已核查</el-tag>
            <el-tag
              v-else-if="detail.derivativeLinkByRowId.value.has(row.rowId)"
              size="small"
              type="warning"
            >待核查</el-tag>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <div class="summary-bar" data-testid="g10-detail-summary">
      <span>期初审定 <strong>{{ fmt(detail.totals.value.openingAdjusted) }}</strong></span>
      <span>本期利息合计 <strong>{{ fmt(detail.totals.value.interestExpense) }}</strong></span>
      <span>期末公允价值 <strong>{{ fmt(detail.totals.value.closingFairValue) }}</strong></span>
      <span>审定合计 <strong>{{ fmt(detail.totals.value.closingAdjusted) }}</strong></span>
      <span>FV变动合计 <strong>{{ fmt(detail.totals.value.movementFvChange) }}</strong></span>
    </div>

    <div class="subtotals" data-testid="g10-detail-subtotals">
      <span
        v-for="(amt, typ) in detail.categorySubtotals.value"
        :key="typ"
        :class="{ 'total-line': typ === '总计' }"
      >{{ typ }}: {{ fmt(amt) }}</span>
    </div>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      note-placeholder="填写审计说明：可概述明细各项目的核实情况、本期计入财务费用的利息金额、公允价值变动计入损益的验证、嵌入衍生拆分判断及与 G10-1 勾稽结果。"
      note-hint="覆盖负债明细、(一)(二)(三)分解、利息与 FV 变动及与审定表勾稽。"
      conclusion-placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
      :related-context="{
        行数: detail.rows.value.length,
        审定合计: detail.totals.value.closingAdjusted,
        与G101差异: detail.adjCrossVariance.value,
        本期利息合计: detail.totals.value.interestExpense,
        校验问题: detail.integrityIssues.value.length,
      }"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, watch, inject } from 'vue'
import { useG10Detail, type G10DetailRow } from '../../composables/useG10Detail'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import {
  G10A_DETAIL_PROGRAM_NOS,
  G10A_PROCEDURE_SHEET,
} from '../../composables/g10FvCrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const detail = useG10Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  projectId: toRef(props, 'projectId'),
})

// 🔴 C-7：四段对应模板两级表头的四个一级分组（A/B+P-S · C-E+F/G · H-J · K-M+N/O）
const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '期初余额', value: 'opening' },
  { label: '本期变动', value: 'movement' },
  { label: '期末余额', value: 'closing' },
]

function onImported() {
  emit('imported')
  detail.reloadFromStore()
}

function onRowChange(row: G10DetailRow | undefined) {
  if (!row) return
  const idx = detail.rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) detail.setActiveRowIndex(idx)
}

async function onSeedAux() {
  await detail.seedFromAuxBalance()
}

async function onMarkProcedure() {
  const n = await detail.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G10A_DETAIL_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `明细编制程序（步骤 ${[...G10A_DETAIL_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_DETAIL_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

const NOTE_KEY = 'G10-2-detail-audit-note'
const CONCLUSION_KEY = 'G10-2-detail-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g10-detail { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.title-block { flex: 1; min-width: 200px; }
.sheet-title { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.formula-cell { border-bottom: 1px dashed #999; }
.summary-bar {
  margin-top: 8px; padding: 8px; background: #f5f7fa; font-size: 12px;
  display: flex; flex-wrap: wrap; gap: 16px;
}
.subtotals { margin-top: 6px; font-size: 12px; color: #606266; display: flex; flex-wrap: wrap; gap: 12px; }
.subtotals .total-line { font-weight: 600; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 8px; }
.adj-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 8px; }
.cross-alert { margin-bottom: 8px; }
.issue-list { margin: 4px 0 0; padding-left: 18px; }
.l3-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.muted { color: #c0c4cc; font-size: 12px; }
</style>
