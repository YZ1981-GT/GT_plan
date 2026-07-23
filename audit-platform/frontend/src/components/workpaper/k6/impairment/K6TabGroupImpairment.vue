<template>
  <div class="k6-tab-group-impairment">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>计价和分摊：</b>处置组整体减值先抵减商誉再按比例分摊至各非流动资产，分摊计算准确；</li>
        <li><b>完整性：</b>处置组减值损失确认完整，与 K6-5 单项测试勾稽一致。</li>
      </ol>
    </el-alert>

    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step">
          <span class="step-num">①</span>
          <span>录入组整体减值金额（联动K6-5合计或手工录入）</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">②</span>
          <span>录入组内各资产（标注是否为商誉）及账面价值</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">③</span>
          <span>自动计算：先抵商誉 → 余额按比例分摊至非流动资产</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">④</span>
          <span>核对分摊后账面 → 形成结论</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p><strong>CAS42 处置组减值分摊规则：</strong>处置组确认的减值损失金额，应当<strong>先抵减处置组中商誉的账面价值</strong>，再根据处置组中适用CAS8的各项非流动资产账面价值所占比重，按比例抵减其账面价值。处置组中各项资产减值后的账面价值不应低于以下三者中的最高者：公允价值减去出售费用后的净额、使用价值、零。</p>
    </div>

    <!-- ═══ （一）处置组减值测算（孰低法） ═══ -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（一）处置组减值测算（孰低法）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" plain @click="syncMeasurementToAllocation">
              应计提减值合计 → 组整体减值
            </el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="measurementRows.length === 0" description="暂无处置组，点击下方按钮新增（如子公司A、分公司B）" :image-size="60" />

      <el-table
        v-else
        :data="measurementRows"
        border
        stripe
        size="small"
        class="group-table"
        row-key="rowId"
      >
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column label="处置组" min-width="120">
          <template #default="{ row }">
            <el-input :model-value="row.groupName" :disabled="isReadonly" size="small"
              @blur="(e: FocusEvent) => updateMeasurementCell(row.rowId, 'groupName', (e.target as HTMLInputElement)?.value ?? '')" />
          </template>
        </el-table-column>
        <el-table-column label="账面价值" min-width="115" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.bookValue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="amt-input"
              @change="(v: number | undefined) => updateMeasurementCell(row.rowId, 'bookValue', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="公允价值" min-width="115" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.fairValue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="amt-input"
              @change="(v: number | undefined) => updateMeasurementCell(row.rowId, 'fairValue', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="公允价值确定依据" min-width="130">
          <template #default="{ row }">
            <el-input :model-value="row.fairValueBasis" :disabled="isReadonly" size="small" placeholder="如：评估报告"
              @blur="(e: FocusEvent) => updateMeasurementCell(row.rowId, 'fairValueBasis', (e.target as HTMLInputElement)?.value ?? '')" />
          </template>
        </el-table-column>
        <el-table-column label="出售费用" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.sellingCost" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="amt-input"
              @change="(v: number | undefined) => updateMeasurementCell(row.rowId, 'sellingCost', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="公允净额" min-width="115" align="right">
          <template #header><span class="formula-header" title="= 公允价值 - 出售费用">公允净额</span></template>
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.fairValueNet) }}</span></template>
        </el-table-column>
        <el-table-column label="应计提减值" min-width="115" align="right">
          <template #header><span class="formula-header" title="= MAX(0, 账面价值 - 公允净额)（孰低法）">应计提减值</span></template>
          <template #default="{ row }">
            <span :class="['formula-cell', { 'impaired-amount': row.impairmentProvision > 0 }]">{{ fmtAmt(row.impairmentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面期末减值" min-width="115" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.existingProvision" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="amt-input"
              @change="(v: number | undefined) => updateMeasurementCell(row.rowId, 'existingProvision', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="应补提/转回" min-width="115" align="right">
          <template #header><span class="formula-header" title="= 应计提减值 - 账面期末减值">应补提/转回</span></template>
          <template #default="{ row }">
            <span :class="['formula-cell', { 'provision-positive': row.additionalProvision > 0 }]">{{ fmtAmt(row.additionalProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input :model-value="row.remark" :disabled="isReadonly" size="small"
              @blur="(e: FocusEvent) => updateMeasurementCell(row.rowId, 'remark', (e.target as HTMLInputElement)?.value ?? '')" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button size="small" type="danger" link @click="removeMeasurementRow($index)">✕</el-button></template>
        </el-table-column>
      </el-table>

      <div class="summary-row">
        <span class="summary-label">测算合计</span>
        <span class="summary-item">账面: <strong>{{ fmtAmt(measurementSubtotals.bookValue) }}</strong></span>
        <span class="summary-item">公允净额: <strong>{{ fmtAmt(measurementSubtotals.fairValueNet) }}</strong></span>
        <span class="summary-item" :class="{ 'impaired-amount': measurementSubtotals.impairmentProvision > 0 }">应计提减值: <strong>{{ fmtAmt(measurementSubtotals.impairmentProvision) }}</strong></span>
        <span class="summary-item">应补提/转回: <strong>{{ fmtAmt(measurementSubtotals.additionalProvision) }}</strong></span>
      </div>

      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="addMeasurementRow()">+ 新增处置组</el-button>
      </div>
    </el-card>

    <!-- ═══ 勾稽一致：Part(一)应计提减值 vs Part(二)已分摊 ═══ -->
    <el-alert
      :type="reconciliation.isBalanced ? 'success' : 'warning'"
      :closable="false"
      show-icon
      class="reconciliation-alert"
    >
      <template #title>
        <span v-if="reconciliation.isBalanced">
          勾稽一致：（一）应计提减值合计 {{ fmtAmt(reconciliation.measurement) }} = （二）已分摊减值合计 {{ fmtAmt(reconciliation.allocated) }}
        </span>
        <span v-else>
          勾稽不一致：（一）应计提减值 {{ fmtAmt(reconciliation.measurement) }} 与（二）已分摊 {{ fmtAmt(reconciliation.allocated) }} 差异 {{ fmtAmt(reconciliation.diff) }} 元，请核对（可点击上方"应计提减值合计 → 组整体减值"联动）
        </span>
      </template>
    </el-alert>

    <!-- ═══ 顶部摘要：组整体减值+商誉抵减+余额分摊 ═══ -->
    <div class="group-summary-panel">
      <div class="summary-card">
        <span class="summary-card-label">组整体减值金额</span>
        <div class="summary-card-value">
          <el-input-number
            v-if="!isReadonly"
            v-model="groupImpairmentAmount"
            :controls="false"
            size="small"
            class="summary-input"
            @change="handleGroupImpairmentChange"
          />
          <span v-else class="amt-val">{{ fmtAmt(groupImpairmentAmount) }}</span>
        </div>
        <el-button v-if="!isReadonly" size="small" link type="primary" @click="syncFromK6_5">
          ← 从K6-5联动
        </el-button>
      </div>
      <div class="summary-card">
        <span class="summary-card-label">商誉抵减</span>
        <span class="amt-val impaired-amount">{{ fmtAmt(groupSummary.goodwillDeduction) }}</span>
      </div>
      <div class="summary-card">
        <span class="summary-card-label">余额分摊至非流动资产</span>
        <span class="amt-val">{{ fmtAmt(groupSummary.remainingAllocation) }}</span>
      </div>
      <div class="summary-card">
        <span class="summary-card-label">已分摊合计</span>
        <span class="amt-val">{{ fmtAmt(allocatedTotal) }}</span>
      </div>
    </div>

    <!-- ═══ 处置组减值分摊主表 ═══ -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">（二）处置组减值损失的分摊（先抵商誉→按比例分摊）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('K6-6')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="groupRows"
        border
        stripe
        size="small"
        class="group-table"
        row-key="rowId"
        max-height="600"
      >
        <!-- 序号 -->
        <el-table-column type="index" label="序号" width="52" align="center" />

        <!-- 处置组 -->
        <el-table-column prop="groupName" label="处置组" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.groupName"
              size="small"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'groupName', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.groupName || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 组内资产 -->
        <el-table-column prop="assetName" label="组内资产" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.assetName"
              size="small"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'assetName', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.assetName || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 是否商誉 -->
        <el-table-column label="是否商誉" width="90" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.isGoodwill"
              :disabled="isReadonly"
              size="small"
              active-text="是"
              inactive-text="否"
              @change="(v: any) => updateCell(row.rowId, 'isGoodwill', v)"
            />
          </template>
        </el-table-column>

        <!-- 账面价值 -->
        <el-table-column label="账面价值" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookValue"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | null) => updateCell(row.rowId, 'bookValue', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>

        <!-- 分摊比例（公式列） -->
        <el-table-column label="分摊比例" min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="= 组内资产账面 / 组账面合计（不含商誉）">分摊比例</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 该资产账面 / 组内非流动资产账面合计" placement="top">
              <span class="formula-cell">
                {{ row.isGoodwill ? '-' : fmtPercent(row.allocationRatio) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 分摊减值（公式列） -->
        <el-table-column label="分摊减值" min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="商誉行=MIN(组减值,商誉账面)；非流动资产行=余额×比例">分摊减值</span>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="row.isGoodwill ? '= MIN(组减值, 商誉账面)（先抵商誉）' : '= 余额分摊 × 分摊比例'" placement="top">
              <span :class="['formula-cell', { 'impaired-amount': row.allocatedImpairment > 0 }]">
                {{ fmtAmt(row.allocatedImpairment) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 分摊后账面 -->
        <el-table-column label="分摊后账面" min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="= 账面价值 - 分摊减值">分摊后账面</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 账面价值 - 分摊减值" placement="top">
              <span :class="['formula-cell', { 'below-floor-warning': row.belowFloor }]">{{ fmtAmt(row.bookAfterImpairment) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 减值下限（CAS42：分摊后账面不得低于此） -->
        <el-table-column label="减值下限" min-width="120" align="right">
          <template #header>
            <el-tooltip content="MAX(公允价值减出售费用净额, 使用价值, 0)；分摊后账面不得低于此下限" placement="top">
              <span class="hint-header">减值下限</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && !row.isGoodwill"
              :model-value="row.impairmentFloor"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | null) => updateCell(row.rowId, 'impairmentFloor', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ row.isGoodwill ? '—' : fmtAmt(row.impairmentFloor) }}</span>
          </template>
        </el-table-column>

        <!-- 结论 -->
        <el-table-column label="结论" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.conclusion"
              size="small"
              placeholder="结论"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'conclusion', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeRow($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新增按钮 -->
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="addRow()">+ 新增</el-button>
        <el-button size="small" type="success" plain @click="importFromK6_4">从K6-4估值表带入组内资产</el-button>
      </div>
    </el-card>

    <!-- ═══ 分摊后下限校验告警 ═══ -->
    <el-alert
      v-if="floorViolations.length > 0"
      type="error"
      :closable="false"
      show-icon
      class="floor-alert"
    >
      <template #title>
        ⚠ {{ floorViolations.length }} 项资产分摊后账面<strong>低于下限</strong>（CAS42：不应低于公允净额/使用价值/0中最高者）：
        {{ floorViolations.map(v => v.assetName).join('、') }}
      </template>
    </el-alert>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明与结论</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" circle @click="openReview('K6-6-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写处置组减值分摊结论（如：经计算，处置组减值金额XX元先抵减商誉YY元，余额ZZ元按账面比例分摊…）"
        @blur="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>处置组减值分摊两步法：第一步抵减商誉（至零为止），第二步余额按比例分摊</li>
        <li>分摊比例 = 该非流动资产账面 / 组内全部非流动资产账面合计（不含商誉）</li>
        <li><strong>下限校验</strong>：各资产减值后账面价值 ≥ MAX(公允价值减出售费用净额, 使用价值, 0)；违反下限的行将红色高亮+顶部告警</li>
        <li>商誉减值不可转回；非流动资产减值视CAS8规定可部分转回</li>
        <li>组整体减值金额可从K6-5联动取得、从Part(一)测算联动、或手工录入</li>
        <li>"是否商誉"标记的资产参与第一步抵减，其余参与第二步按比例分摊</li>
        <li>"从K6-4带入组内资产"：读取K6-4估值表处置组资产行，按名称去重填入分摊表</li>
        <li>Part(一)↔Part(二)勾稽：Part(一)应计提减值合计 应= Part(二)已分摊合计</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabGroupImpairment.vue — K6-6 处置组减值测试表（55行虚拟滚动）
 *
 * 处置组减值分摊：先抵商誉 → 余额按比例分摊至组内非流动资产
 * 与K6-5联动：setGroupImpairment from K6-5 total
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.5
 * Requirements: 6.1-6.4
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK6GroupImpairment } from '../../composables/useK6GroupImpairment'
import { useK6ImportExport } from '../../composables/useK6ImportExport'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

function saveResponse(field: string, value: any): Promise<void> {
  emit('save', field, value)
  return Promise.resolve()
}

const {
  groupRows,
  groupImpairmentAmount,
  groupSummary,
  allocatedTotal,
  auditConclusion,
  updateCell,
  setGroupImpairment,
  addRow,
  removeRow,
  saveConclusion,
  // Part(一) 减值测算
  measurementRows,
  measurementSubtotals,
  updateMeasurementCell,
  addMeasurementRow,
  removeMeasurementRow,
  syncMeasurementToAllocation,
  // 勾稽
  reconciliation,
} = useK6GroupImpairment({
  allResponses: allResponsesRef,
  saveResponse,
})

// ─── 从K6-5联动获取组整体减值金额 ───────────────────────────────────────────

function syncFromK6_5() {
  const k6_5_total = props.allResponses.get('K6-5-impairment-total')
  const val = Number(k6_5_total?.remark ?? k6_5_total?.conclusion ?? 0) || 0
  if (val > 0) {
    setGroupImpairment(val)
    ElMessage.success(`已从K6-5联动：组整体减值 ${fmtAmt(val)} 元`)
  } else {
    ElMessage.info('K6-5减值合计为0或未填写，请手工录入')
  }
}

function handleGroupImpairmentChange(v: number | null) {
  setGroupImpairment(v ?? 0)
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const { exportTemplate, exportData, importData } = useK6ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K6-6',
})

// ─── 分摊后下限校验（CAS42：分摊后账面 ≥ MAX(公允净额, 使用价值, 0)）────────

const floorViolations = computed(() => {
  // CAS42：非商誉资产分摊后账面 < 减值下限(公允净额/使用价值孰高) 即违规
  return groupRows.value.filter(row => !row.isGoodwill && row.belowFloor)
})

// ─── 从K6-4估值表带入组内资产 ────────────────────────────────────────────────

function importFromK6_4(): void {
  const k6_4_item = props.allResponses.get('K6-4-valuation-rows')
  const raw = k6_4_item?.remark ?? k6_4_item?.conclusion ?? (typeof k6_4_item === 'string' ? k6_4_item : null)
  if (!raw) {
    ElMessage.info('K6-4估值表暂无数据，请先编制K6-4初始确认检查表')
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      ElMessage.info('K6-4估值表暂无行数据')
      return
    }
    // 按名称去重
    const existingNames = new Set(groupRows.value.map(r => r.assetName))
    const candidates = parsed.filter((r: any) => {
      const name = r.itemName || r.assetName || ''
      return name && !existingNames.has(name)
    })
    if (candidates.length === 0) {
      ElMessage.info('K6-4中所有项目已在分摊表中')
      return
    }
    // 带入：处置组名/资产名/账面/是否商誉(默认否)
    let importCount = 0
    for (const r of candidates) {
      const name = r.itemName || r.assetName || ''
      const newRow = {
        rowId: `row-${Date.now()}-${importCount}`,
        seqNo: groupRows.value.length + 1,
        groupName: r.groupName || groupRows.value[0]?.groupName || '',
        assetName: name,
        isGoodwill: false,
        bookValue: Number(r.bookValue) || 0,
        allocationRatio: 0,
        allocatedImpairment: 0,
        bookAfterImpairment: 0,
        conclusion: '',
        remark: '从K6-4带入',
      }
      groupRows.value.push(newRow as any)
      importCount++
    }
    // 重算分摊
    groupRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    // 触发 composable recalcAll (通过 updateCell 任一行触发)
    if (groupRows.value.length > 0) {
      updateCell(groupRows.value[0].rowId, 'bookValue', groupRows.value[0].bookValue)
    }
    ElMessage.success(`已从K6-4带入 ${importCount} 项资产（按名称去重），分摊比例已重算`)
  } catch {
    ElMessage.error('K6-4数据解析失败')
  }
}

// ─── AI辅助结论 ──────────────────────────────────────────────────────────────

const aiLoading = ref(false)

async function handleAiGenerate(): Promise<void> {
  if (props.isReadonly || aiLoading.value) return
  aiLoading.value = true
  try {
    const summary = groupSummary.value
    const context: Record<string, string> = {
      '组整体减值金额': String(summary.groupImpairment),
      '商誉账面': String(summary.goodwillBook),
      '商誉抵减': String(summary.goodwillDeduction),
      '余额分摊至非流动资产': String(summary.remainingAllocation),
      '已分摊合计': String(allocatedTotal.value),
      '组内资产数': String(groupRows.value.length),
      '勾稽是否一致': reconciliation.value.isBalanced ? '一致' : `不一致(差异${reconciliation.value.diff})`,
      '下限违反项数': String(floorViolations.value.length),
      'Part一应计提减值合计': String(measurementSubtotals.value.impairmentProvision),
      'Part一应补提合计': String(measurementSubtotals.value.additionalProvision),
    }
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'k6-group-impairment-conclusion',
      context,
      prompt: '根据CAS42处置组减值分摊结果（先抵商誉→余额按比例），生成审计结论（包括：分摊计算是否准确、商誉抵减是否恰当、各资产分摊后账面是否超下限、Part一测算与Part二分摊是否勾稽一致）',
      existingContent: auditConclusion.value,
    })
    const text = resp?.data?.content || resp?.data?.text || resp?.content || ''
    if (text) {
      auditConclusion.value = text
      saveConclusion()
      ElMessage.success('AI结论已生成')
    }
  } catch (e: any) {
    ElMessage.error('AI生成失败: ' + (e?.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.k6-tab-group-impairment {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 蓝色渐变引导区 */
.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border: 1px solid #b3d8fd;
}
.guidance-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}
.guidance-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #1d3557;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

/* 琥珀色方法论上下文 */
.methodology-context {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12.5px;
  color: #78350f;
  line-height: 1.6;
}

/* 顶部摘要面板 */
.group-summary-panel {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.summary-card-label {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}
.summary-card-value {
  display: flex;
  align-items: center;
  gap: 8px;
}
.summary-input {
  width: 140px;
}
.summary-input :deep(.el-input__inner) {
  text-align: right;
  font-weight: 600;
}
.amt-val {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  font-variant-numeric: tabular-nums;
}

/* 块卡片 */
.block-card {
  margin-bottom: 16px;
}
.block-card :deep(.el-card__header) { padding: 8px 14px; }
.block-card :deep(.el-card__body) { padding: 12px; }

/* 勾稽提示 */
.reconciliation-alert { margin-bottom: 16px; }
.floor-alert { margin-bottom: 16px; }

/* 合计行 */
.summary-row {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 12px; margin-top: 10px;
  background: #f9fafb; border-radius: 4px; border: 1px solid #e5e7eb;
  font-size: var(--wp-font-size, 13px); flex-wrap: wrap;
}
.summary-label { font-weight: 600; color: #374151; }
.summary-item { color: #4b5563; }
.provision-positive { color: #dc2626; }

/* Section标题 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
}
.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表格 */
.group-table {
  font-size: var(--wp-font-size, 13px);
}
.group-table :deep(.el-table__cell) {
  padding: 6px 0;
}
.amt-input {
  width: 100%;
}
.amt-input :deep(.el-input__inner) {
  text-align: right;
}
.amt-cell {
  font-variant-numeric: tabular-nums;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 2px;
}
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  font-variant-numeric: tabular-nums;
}

/* 减值金额高亮 */
.impaired-amount {
  color: #dc2626;
  font-weight: 600;
}
.below-floor-warning {
  color: #dc2626;
  font-weight: 600;
  background: #fef2f2;
  padding: 1px 4px;
  border-radius: 2px;
}

/* 新增按钮 */
.add-row-bar {
  padding-top: 10px;
}

/* 审计结论卡 */
.audit-note-card {
  margin-bottom: 16px;
}

/* 编制提示 */
.edit-tips {
  margin-top: 16px;
  font-size: 12px;
  color: #6b7280;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 14px;
}
.edit-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #374151;
}
.edit-tips ul {
  margin: 8px 0 0 0;
  padding-left: 18px;
  line-height: 1.8;
}
</style>
