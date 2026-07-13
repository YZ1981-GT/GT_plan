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
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
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
      </div>

      <!-- 分类新增按钮 -->
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddItem('asset_noncurrent')">+ 不再满足的非流动资产</el-button>
        <el-button size="small" @click="handleAddItem('asset_group')">+ 处置组资产</el-button>
        <el-button size="small" @click="handleAddItem('liability_group')">+ 处置组负债</el-button>
      </div>
    </el-card>

    <!-- 审计说明+结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-card-header">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
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
        <li>按"非流动资产 / 处置组资产 / 处置组负债"分类录入，可用"处置组/主体"列标注子公司A、分公司B</li>
        <li>逐项判定合规性：合规 / 不合规 / 不适用；"不合规"项将触发顶部红色摘要提示</li>
        <li>决议索引/协议索引应指向不再处置的决议、协议等支持性证据底稿；📎列记录抽凭编号</li>
        <li>调整差额（调整后账面 − 现账面）计入当期损益，需与资产减值损失/资产处置损益勾稽</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabNoLongerCheck.vue — K6-7 检查表（不再满足持有待售条件）
 *
 * 对照源模板重建：
 * - ①②③④ 净额分解：④净额 = ①被划归前账面 − ②假设折旧摊销 − ③假设减值
 * - 调整后账面 = min(④净额, 可收回金额)（CAS42 第22条孰低）
 * - 分类（非流动资产/处置组资产/处置组负债）+ 处置组主体 + 决议/协议索引
 * - 分区小计 + 逐项合规判定 + 不合规红色摘要 + 行级抽凭
 * - 内嵌"持有待售会计政策"编制说明（源模板 R50-R57）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.6 · Requirements 7.1-7.4
 */
import { inject, toRef, type Ref } from 'vue'
import { MagicStick, Delete } from '@element-plus/icons-vue'
import { useK6NoLongerCheck, type NoLongerCategory } from '@/components/workpaper/composables/useK6NoLongerCheck'

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

function handleAiGenerate(): void {
  emit('save', 'K6-7-ai-trigger', { remark: 'no-longer-eval' })
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
