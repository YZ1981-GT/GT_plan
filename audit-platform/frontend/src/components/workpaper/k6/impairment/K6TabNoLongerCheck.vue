<template>
  <div class="k6-tab-no-longer-check">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的持有待售资产和负债是存在的，且已记录于恰当账户；</li>
        <li><b>完整性：</b>所有应记录的持有待售资产和负债均已记录，相关披露均已包括；</li>
        <li><b>计价和分摊 / 列报：</b>不再满足持有待售条件时已及时终止分类，并按孰低原则（净额④与可收回金额孰低）恰当计量与列报。</li>
      </ol>
    </el-alert>

    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">K6-7 检查表（不再满足持有待售条件）</h3>
      <div class="head-actions">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly" @command="handleIECommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview('K6-7-no-longer-check')">💬复核</el-button>
      </div>
    </div>

    <!-- 蓝色引导区 -->
    <div class="guidance-area">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span> 识别不再满足持有待售条件的资产/处置组</div>
        <div class="guidance-step"><span class="step-num">②</span> 分解 ①被划归前账面 − ②假设折旧摊销 − ③假设减值 = ④净额</div>
        <div class="guidance-step"><span class="step-num">③</span> 调整后账面 = min(④净额, 决定不再出售之日可收回金额)</div>
        <div class="guidance-step"><span class="step-num">④</span> 逐项判定合规性 + 附决议/协议索引凭证</div>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>CAS42 第22条：</strong>非流动资产或处置组不再满足持有待售类别划分条件时，应<strong>停止将其划分为持有待售</strong>，并按以下两者<strong>孰低</strong>计量：① 该资产或处置组被划归为持有待售之前的账面价值，按照其<strong>假定在没有被划归为持有待售的情况下原应确认的折旧、摊销或减值</strong>进行调整后的金额（即 ④净额 = ① − ② − ③）；② 决定不再出售之日的可收回金额。差额计入当期损益。</p>
    </div>

    <!-- 不合规红色摘要 -->
    <el-alert
      v-if="hasNonCompliant"
      type="error"
      :closable="false"
      show-icon
      class="non-compliant-alert"
    >
      <template #title>
        存在 <strong>{{ nonCompliantItems.length }}</strong> 项不合规：
        {{ nonCompliantItems.map(i => i.assetName || '未命名').join('、') }}
      </template>
    </el-alert>

    <!-- 检查表主表 -->
    <el-card shadow="never" class="check-table-card">
      <template #header>
        <div class="section-card-header">
          <span>不再满足持有待售条件项目检查</span>
        </div>
      </template>

      <el-empty
        v-if="checkItems.length === 0"
        description="暂无检查项，点击下方按钮按分类新增"
        :image-size="70"
      />

      <el-table
        v-else
        :data="checkItems"
        border
        size="small"
        style="width: 100%"
        :row-class-name="tableRowClassName"
        max-height="560"
      >
        <el-table-column type="index" label="序" width="44" align="center" fixed="left" />
        <el-table-column label="分类" width="118" fixed="left">
          <template #default="{ row }">
            <el-select
              :model-value="row.category"
              :disabled="isReadonly"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'category', v)"
            >
              <el-option label="非流动资产" value="asset_noncurrent" />
              <el-option label="处置组资产" value="asset_group" />
              <el-option label="处置组负债" value="liability_group" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="处置组/主体" width="110">
          <template #default="{ row }">
            <el-input
              :model-value="row.groupName"
              :disabled="isReadonly"
              size="small"
              placeholder="如子公司A"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'groupName', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="项目/资产名称" min-width="140" fixed="left">
          <template #default="{ row }">
            <el-input
              :model-value="row.assetName"
              :disabled="isReadonly"
              size="small"
              placeholder="资产名称"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'assetName', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="①被划归前账面" width="130" align="right">
          <template #header>
            <el-tooltip content="① 被划归为持有待售之前的账面价值" placement="top">
              <span class="hint-header">①被划归前账面</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.preClassBookValue"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.rowId, 'preClassBookValue', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="②假设折旧摊销" width="130" align="right">
          <template #header>
            <el-tooltip content="② 假设在没有被划归为持有待售的情况下原应确认的折旧、摊销" placement="top">
              <span class="hint-header">②假设折旧摊销</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.assumedDepreciation"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.rowId, 'assumedDepreciation', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="③假设减值" width="120" align="right">
          <template #header>
            <el-tooltip content="③ 假设在没有被划归为持有待售的情况下原应确认的减值准备" placement="top">
              <span class="hint-header">③假设减值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.assumedImpairment"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.rowId, 'assumedImpairment', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="④净额" width="120" align="right">
          <template #header>
            <span class="formula-header" title="④ 净额 = ①被划归前账面 - ②假设折旧摊销 - ③假设减值">④净额</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= ① - ② - ③" placement="top">
              <span class="formula-value">{{ fmtAmt(row.netValue) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="可收回金额" width="120" align="right">
          <template #header>
            <el-tooltip content="决定不再出售之日的可收回金额" placement="top">
              <span class="hint-header">可收回金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.recoverableAmount"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.rowId, 'recoverableAmount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="调整后账面" width="120" align="right">
          <template #header>
            <span class="formula-header" title="= min(④净额, 可收回金额)（孰低）">调整后账面</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= min(④净额, 可收回金额)" placement="top">
              <span class="formula-value">{{ fmtAmt(row.adjustedBookValue) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="现账面" width="120" align="right">
          <template #header>
            <el-tooltip content="当前持有待售资产账面价值（从K6-2或手工录入）" placement="top">
              <span class="hint-header">现账面</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.currentBookValue"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.rowId, 'currentBookValue', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="调整差额" width="120" align="right">
          <template #header>
            <span class="formula-header" title="= 调整后账面 - 现账面（正=转回/负=追加减值，计入当期损益）">调整差额</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 调整后账面 - 现账面（计入当期损益）" placement="top">
              <span :class="['formula-value', { 'diff-positive': (row.adjustmentDiff || 0) > 0, 'diff-negative': (row.adjustmentDiff || 0) < 0 }]">
                {{ fmtAmt(row.adjustmentDiff) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="可收回确定方法" width="130">
          <template #header>
            <el-tooltip content="CAS8：可收回金额=MAX(公允价值减处置费用后的净额, 预计未来现金流量现值)" placement="top">
              <span class="hint-header">可收回确定方法</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              :model-value="row.recoverableMethod"
              :disabled="isReadonly"
              size="small"
              placeholder="选择"
              clearable
              @change="(v: string) => updateCell(row.rowId, 'recoverableMethod', v || '')"
            >
              <el-option label="公允净额" value="fair_value_net" />
              <el-option label="使用价值(DCF)" value="value_in_use" />
              <el-option label="评估报告" value="appraisal" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="不再满足原因" min-width="140">
          <template #default="{ row }">
            <el-input
              :model-value="row.noLongerReason"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="如：出售计划取消"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'noLongerReason', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="重分类日" width="128">
          <template #default="{ row }">
            <el-date-picker
              :model-value="row.reclassificationDate"
              :disabled="isReadonly"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="日期"
              style="width: 100%"
              @change="(v: string) => updateCell(row.rowId, 'reclassificationDate', v || '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="决议索引" width="100">
          <template #header>
            <el-tooltip content="被审计单位不再处置该非流动资产或处置组的决议（索引）" placement="top">
              <span class="hint-header">决议索引</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input
              :model-value="row.decisionRef"
              :disabled="isReadonly"
              size="small"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'decisionRef', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="协议索引" width="100">
          <template #header>
            <el-tooltip content="与受让方之间签订的不再处置的协议等（索引）" placement="top">
              <span class="hint-header">协议索引</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input
              :model-value="row.agreementRef"
              :disabled="isReadonly"
              size="small"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'agreementRef', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="160">
          <template #default="{ row }">
            <el-radio-group
              :model-value="row.status"
              :disabled="isReadonly"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'status', v)"
            >
              <el-radio-button value="compliant">合规</el-radio-button>
              <el-radio-button value="non_compliant">不合规</el-radio-button>
              <el-radio-button value="na">不适用</el-radio-button>
            </el-radio-group>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.conclusion"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }"
              placeholder="审计结论"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'conclusion', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="📎" width="80">
          <template #default="{ row }">
            <el-input
              :model-value="row.voucherRef"
              :disabled="isReadonly"
              size="small"
              placeholder="凭证"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'voucherRef', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="handleRemoveItem($index)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分区小计 -->
      <div v-if="checkItems.length > 0" class="valuation-summary">
        <span class="summary-item">资产合计（{{ subtotals.assetCount }} 项）— ④净额: <strong>{{ fmtAmt(subtotals.assetNet) }}</strong> ｜ 调整后账面: <strong>{{ fmtAmt(subtotals.assetAdjusted) }}</strong></span>
        <span class="summary-item">负债合计（{{ subtotals.liabilityCount }} 项）— ④净额: <strong>{{ fmtAmt(subtotals.liabilityNet) }}</strong> ｜ 调整后账面: <strong>{{ fmtAmt(subtotals.liabilityAdjusted) }}</strong></span>
        <span class="summary-item" :class="{ 'diff-positive': totalAdjustmentDiff > 0, 'diff-negative': totalAdjustmentDiff < 0 }">
          调整差额合计: <strong>{{ fmtAmt(totalAdjustmentDiff) }}</strong>
          <span v-if="totalAdjustmentDiff > 0">（转回，贷记资产减值损失）</span>
          <span v-else-if="totalAdjustmentDiff < 0">（追加减值，借记资产减值损失）</span>
        </span>
      </div>

      <!-- 分类新增按钮 -->
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddItem('asset_noncurrent')">+ 不再满足的非流动资产</el-button>
        <el-button size="small" @click="handleAddItem('asset_group')">+ 处置组资产</el-button>
        <el-button size="small" @click="handleAddItem('liability_group')">+ 处置组负债</el-button>
        <el-button size="small" type="success" plain @click="importFromK6_2">从K6-2明细带入</el-button>
        <el-button size="small" type="warning" plain :disabled="!hasAdjustmentDiff" @click="pushDiffToK6_3">调整差额→K6-3建议AJE</el-button>
      </div>
    </el-card>

    <!-- 审计说明+结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-card-header">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="对不再满足持有待售条件项目的总体审计结论（可AI辅助生成）"
        @blur="handleConclusionSave"
      />
    </el-card>

    <!-- 编制说明：持有待售会计政策（源模板内嵌） -->
    <div class="policy-context">
      <div class="policy-title">编制说明 · 持有待售及终止经营的会计政策</div>
      <ol class="policy-list">
        <li>同时满足下列条件的非流动资产（不包括金融资产及递延所得税资产）或处置组应确认为持有待售：在当前状况下仅根据出售此类资产或处置组的惯常条款即可立即出售；已就处置作出决议，如需股东批准的已取得批准；已与受让方签订不可撤销的转让协议；该项转让将在一年内完成。</li>
        <li>持有待售的资产包括单项资产和处置组。在特定情况下，处置组包括企业合并中取得的商誉等。</li>
        <li>持有待售的非流动资产和持有待售的处置组中的资产<strong>不计提折旧或进行摊销</strong>，按照账面价值与公允价值减去处置费用后的净额<strong>孰低</strong>计量，并列报为"划分为持有待售的资产"；处置组中的负债列报为"划分为持有待售的负债"。</li>
        <li>某项非流动资产或处置组被划归为持有待售，但后来<strong>不再满足</strong>持有待售确认条件的，企业应停止将其划归为持有待售，并按下列两项较低者计量：</li>
        <li style="list-style:none;padding-left:8px">① 该资产或处置组被划归为持有待售之前的账面价值，按照其假定在没有被划归为持有待售的情况下原应确认的折旧、摊销或减值进行调整后的金额；② 决定不再出售之日的可收回金额。</li>
      </ol>
    </div>

    <!-- 编制提示 -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>④净额 = ①被划归前账面 − ②假设折旧摊销 − ③假设减值（系统自动计算）</li>
        <li>调整后账面价值 = min(④净额, 可收回金额)，即 CAS42 第22条孰低计量</li>
        <li>调整差额 = 调整后账面 − 现账面（正值=转回贷记损益，负值=追加减值借记损益）</li>
        <li>可收回金额确定方法：CAS8 取 MAX(公允价值减处置费用后的净额, 使用价值/DCF)</li>
        <li>按"非流动资产 / 处置组资产 / 处置组负债"分类录入，可用"处置组/主体"列标注子公司A、分公司B</li>
        <li>逐项判定合规性：合规 / 不合规 / 不适用；"不合规"项将触发顶部红色摘要提示</li>
        <li>决议索引/协议索引应指向不再处置的决议、协议等支持性证据底稿；📎列记录抽凭编号</li>
        <li>"调整差额→K6-3建议AJE"按钮：自动汇总差额生成建议调整分录推入K6-3</li>
        <li>"从K6-2明细带入"：从K6-2已登记的资产中筛选尚未出现在K6-7的项目带入</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传input -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabNoLongerCheck.vue — K6-7 检查表（不再满足持有待售条件）
 *
 * 对照源模板重建：
 * - ①②③④ 净额分解：④净额 = ①被划归前账面 − ②假设折旧摊销 − ③假设减值
 * - 调整后账面 = min(④净额, 可收回金额)（CAS42 第22条孰低）
 * - 新增：现账面/调整差额/可收回确定方法/从K6-2带入/差额→K6-3建议AJE/导入导出
 * - 分类（非流动资产/处置组资产/处置组负债）+ 处置组主体 + 决议/协议索引
 * - 分区小计 + 逐项合规判定 + 不合规红色摘要 + 行级抽凭
 * - 内嵌"持有待售会计政策"编制说明（源模板 R50-R57）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.6 · Requirements 7.1-7.4
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { MagicStick, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK6NoLongerCheck, type NoLongerCategory } from '@/components/workpaper/composables/useK6NoLongerCheck'
import { useK6ImportExport } from '@/components/workpaper/composables/useK6ImportExport'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── Composable ──────────────────────────────────────────────────────────────

function saveResponse(field: string, value: any): Promise<void> {
  emit('save', field, value)
  return Promise.resolve()
}

const {
  checkItems,
  nonCompliantItems,
  hasNonCompliant,
  subtotals,
  auditConclusion,
  updateCell,
  addItem,
  removeItem,
  saveConclusion,
} = useK6NoLongerCheck({
  allResponses: allResponsesRef,
  saveResponse,
})

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const { exportTemplate, exportData, importData } = useK6ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K6-7',
})

// ─── 调整差额计算（adjustmentDiff = adjustedBookValue - currentBookValue）───

const totalAdjustmentDiff = computed(() => {
  return checkItems.value.reduce((sum, item) => {
    const current = (item as any).currentBookValue || 0
    const adjusted = item.adjustedBookValue || 0
    return sum + (adjusted - current)
  }, 0)
})

const hasAdjustmentDiff = computed(() => {
  return checkItems.value.some((item) => {
    const current = (item as any).currentBookValue || 0
    const adjusted = item.adjustedBookValue || 0
    return Math.abs(adjusted - current) > 0.005
  })
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddItem(category: NoLongerCategory): void {
  addItem(category)
}

function handleRemoveItem(index: number): void {
  removeItem(index)
}

function handleConclusionSave(): void {
  saveConclusion()
}

// ─── AI辅助（真实接入/ai/generate-text） ─────────────────────────────────────

const aiLoading = ref(false)

async function handleAiGenerate(): Promise<void> {
  if (props.isReadonly || aiLoading.value) return
  aiLoading.value = true
  try {
    const nonCompliantNames = nonCompliantItems.value.map((i: any) => i.assetName || '未命名').join('、')
    const context: Record<string, string> = {
      '检查项数': String(checkItems.value.length),
      '不合规项数': String(nonCompliantItems.value.length),
      '不合规项': nonCompliantNames || '无',
      '资产净额合计': String(subtotals.value.assetNet || 0),
      '资产调整后账面合计': String(subtotals.value.assetAdjusted || 0),
      '负债净额合计': String(subtotals.value.liabilityNet || 0),
      '负债调整后账面合计': String(subtotals.value.liabilityAdjusted || 0),
      '调整差额合计': String(totalAdjustmentDiff.value),
    }
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'k6-no-longer-conclusion',
      context,
      prompt: '根据CAS42第22条不再满足持有待售条件检查结果，生成审计结论（包括：是否及时终止分类、孰低计量是否恰当、调整差额是否正确计入当期损益、可收回金额确定方法是否合理）',
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

// ─── 从K6-2明细表带入 ────────────────────────────────────────────────────────

function importFromK6_2(): void {
  // K6-2 useK6Detail 持久化键为 K6-2-rows
  const k6_2_item = props.allResponses.get('K6-2-rows')
  const raw = k6_2_item?.remark ?? k6_2_item?.conclusion ?? (typeof k6_2_item === 'string' ? k6_2_item : null)
  if (!raw) {
    ElMessage.info('K6-2明细表暂无数据，请先编制K6-2明细表')
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      ElMessage.info('K6-2明细表暂无行数据')
      return
    }
    // 按名称去重（已在K6-7中的不再带入）
    const existingNames = new Set(checkItems.value.map(i => i.assetName))
    const candidates = parsed.filter((r: any) => r.assetName && !existingNames.has(r.assetName))
    if (candidates.length === 0) {
      ElMessage.info('K6-2中所有项目已在K6-7检查表中')
      return
    }
    // 带入：填①被划归前账面=K6-2的bookValue，现账面=K6-2的bookValue
    let importCount = 0
    for (const r of candidates) {
      const category: NoLongerCategory = r.category === '处置组负债' ? 'liability_group'
        : r.category === '处置组资产' ? 'asset_group'
        : 'asset_noncurrent'
      // 直接构造行（不走ElMessageBox弹窗，批量带入）
      const newItem = {
        category,
        assetName: r.assetName,
        preClassBookValue: Number(r.costValue) || Number(r.bookValue) || 0,
        currentBookValue: Number(r.bookValue) || 0,
        recoverableAmount: 0,
        assumedDepreciation: 0,
        assumedImpairment: 0,
      }
      checkItems.value.push({
        rowId: `row-${Date.now()}-${importCount}`,
        seqNo: checkItems.value.length + 1,
        groupName: '',
        netValue: newItem.preClassBookValue,
        adjustedBookValue: 0,
        noLongerReason: '',
        reclassificationDate: '',
        decisionRef: '',
        agreementRef: '',
        status: '' as any,
        voucherRef: '',
        conclusion: '',
        remark: '从K6-2带入',
        ...newItem,
      } as any)
      importCount++
    }
    // 重新编号 + 重算 + 持久化
    checkItems.value.forEach((r, i) => { r.seqNo = i + 1 })
    saveResponse('K6-7-rows', { remark: JSON.stringify(checkItems.value) })
    ElMessage.success(`已从K6-2带入 ${importCount} 项（按名称去重）`)
  } catch {
    ElMessage.error('K6-2数据解析失败')
  }
}

// ─── 调整差额→K6-3建议AJE ───────────────────────────────────────────────────

function pushDiffToK6_3(): void {
  if (!hasAdjustmentDiff.value) {
    ElMessage.info('当前无调整差额')
    return
  }
  // 汇总所有有差额的行
  const itemsWithDiff = checkItems.value.filter((item) => {
    const current = (item as any).currentBookValue || 0
    const adjusted = item.adjustedBookValue || 0
    return Math.abs(adjusted - current) > 0.005
  })
  const totalDiff = totalAdjustmentDiff.value

  // 构造建议AJE分录（借/贷由差额方向决定）
  // 差额>0 = 转回（调整后>现账面，减少减值准备）：借:持有待售资产减值准备 / 贷:资产减值损失
  // 差额<0 = 追加减值（调整后<现账面）：借:资产减值损失 / 贷:持有待售资产减值准备
  const suggestion = {
    source: 'K6-7',
    type: 'AJE',
    summary: `不再满足持有待售条件 - ${itemsWithDiff.map(i => i.assetName).join('、')} - 调整差额`,
    entries: totalDiff > 0
      ? [
          { accountCode: '1481', accountName: '持有待售资产减值准备', debit: Math.abs(totalDiff), credit: 0 },
          { accountCode: '6701', accountName: '资产减值损失', debit: 0, credit: Math.abs(totalDiff) },
        ]
      : [
          { accountCode: '6701', accountName: '资产减值损失', debit: Math.abs(totalDiff), credit: 0 },
          { accountCode: '1481', accountName: '持有待售资产减值准备', debit: 0, credit: Math.abs(totalDiff) },
        ],
    amount: Math.abs(totalDiff),
    items: itemsWithDiff.map(i => ({
      assetName: i.assetName,
      adjustedBookValue: i.adjustedBookValue,
      currentBookValue: (i as any).currentBookValue || 0,
      diff: i.adjustedBookValue - ((i as any).currentBookValue || 0),
    })),
  }

  // 写入allResponses供K6-3读取
  props.allResponses.set('K6-7-suggested-aje', {
    item_id: 'K6-7-suggested-aje',
    remark: JSON.stringify(suggestion),
  })
  emit('save', 'K6-7-suggested-aje', { remark: JSON.stringify(suggestion) })

  // 发eventBus通知K6-3（如果在同一会话打开）
  eventBus.emit('adjustment:created', {
    wpCode: 'K6',
    source: 'K6-7-no-longer',
    accountCode: '1481',
    ajeTotal: totalDiff,
    rjeTotal: 0,
    projectId: props.projectId,
  })

  ElMessage.success(`已生成建议AJE（差额 ${fmtAmt(totalDiff)} 元）并通知K6-3，请在K6-3确认`)
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

function handleIECommand(cmd: string): void {
  if (cmd === 'template') exportTemplate()
  else if (cmd === 'export') exportData()
  else if (cmd === 'import') fileInputRef.value?.click()
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  const result = await importData(file)
  if (result && result.rowCount > 0) {
    ElMessage.success(`导入完成，${result.rowCount} 行`)
  }
}

// ─── Table row class ─────────────────────────────────────────────────────────

function tableRowClassName({ row }: { row: any }): string {
  if (row.status === 'non_compliant') return 'non-compliant-row'
  if (row.category === 'liability_group') return 'liability-row'
  return ''
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-no-longer-check { padding: 12px; font-size: var(--wp-font-size, 13px); }

.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

.guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.guidance-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guidance-step { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; color: #1a5276; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2980b9; color: #fff; font-size: 10px; flex-shrink: 0; }

.methodology-context {
  border-left: 3px solid #f0a500; background: #fef9e7; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #7d6608; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.non-compliant-alert { margin-bottom: 12px; }
.check-table-card { margin-bottom: 12px; }
.check-table-card :deep(.el-card__header) { padding: 8px 14px; }
.check-table-card :deep(.el-card__body) { padding: 12px; }
.conclusion-card { margin-bottom: 12px; }

.section-card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

.hint-header { border-bottom: 1px dotted #c0c4cc; cursor: help; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; font-variant-numeric: tabular-nums; }
.diff-positive { color: #059669; font-weight: 500; }
.diff-negative { color: #dc2626; font-weight: 500; }

:deep(.non-compliant-row) { background-color: #fef0f0 !important; }
:deep(.liability-row) { background-color: #fef6f6; }

.valuation-summary {
  display: flex; flex-wrap: wrap; gap: 24px;
  padding: 10px 12px; margin-top: 10px;
  background: #f9fafb; border-radius: 4px; border: 1px solid #e5e7eb;
  font-size: var(--wp-font-size, 13px); color: #4b5563;
}
.add-row-bar { padding-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }

.policy-context {
  border-left: 4px solid #f59e0b; background: #fffbeb;
  padding: 12px 16px; margin-top: 12px; border-radius: 4px;
  font-size: 12px; color: #78350f; line-height: 1.6;
}
.policy-title { font-weight: 600; margin-bottom: 6px; }
.policy-list { margin: 0; padding-left: 18px; }
.policy-list li { margin-bottom: 4px; }

.k6-details-tip { margin-top: 16px; font-size: 12px; color: #666; }
.k6-details-tip summary { cursor: pointer; color: #409eff; font-weight: 500; }
.k6-details-tip ul { margin: 8px 0 0 16px; line-height: 1.8; }
</style>
