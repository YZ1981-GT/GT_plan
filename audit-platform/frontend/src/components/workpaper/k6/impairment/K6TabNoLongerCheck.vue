<template>
  <div class="k6-tab-no-longer-check">
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
        <div class="guidance-step"><span class="step-num">①</span> 逐项识别不再满足持有待售条件的资产</div>
        <div class="guidance-step"><span class="step-num">②</span> 确认不再满足原因并记录重分类日期</div>
        <div class="guidance-step"><span class="step-num">③</span> 计算调整后账面价值=两者取低(假设未分类账面 vs 可收回金额)</div>
        <div class="guidance-step"><span class="step-num">④</span> 逐项判定合规性并附凭证引用</div>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS42第22条：非流动资产或处置组不再满足持有待售类别划分条件时，应停止将其划分为持有待售，并按以下两者孰低计量：(a) 划分为持有待售类别前的账面价值（假设从未被划分，按正常折旧/摊销调整后的账面金额）；(b) 可收回金额。差额计入当期损益。</p>
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
          <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddItem">+ 新增</el-button>
        </div>
      </template>

      <el-empty v-if="checkItems.length === 0" description="暂无检查项，点击"+ 新增"添加不再满足持有待售的项目" />

      <el-table
        v-else
        :data="checkItems"
        border
        size="small"
        style="width: 100%"
        :row-class-name="tableRowClassName"
      >
        <el-table-column type="index" label="序" width="48" align="center" />
        <el-table-column label="项目/资产名称" min-width="130">
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
        <el-table-column label="不再满足原因" min-width="150">
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
        <el-table-column label="重分类日" width="130">
          <template #default="{ row }">
            <el-date-picker
              :model-value="row.reclassificationDate"
              :disabled="isReadonly"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%"
              @change="(v: string) => updateCell(row.rowId, 'reclassificationDate', v || '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="假设未分类账面" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.assumedBookValue"
              :disabled="isReadonly"
              :controls="false"
              size="small"
              :precision="2"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.rowId, 'assumedBookValue', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="可收回金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.recoverableAmount"
              :disabled="isReadonly"
              :controls="false"
              size="small"
              :precision="2"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.rowId, 'recoverableAmount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="调整后账面" width="120" align="right" class-name="formula-col">
          <template #header>
            <el-tooltip content="公式：min(假设未分类账面, 可收回金额)" placement="top">
              <span class="formula-header">调整后账面</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.adjustedBookValue) }}</span>
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
        <el-table-column label="📎" width="70" align="center">
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
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="handleRemoveItem($index)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
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

    <!-- 编制提示 -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>CAS42第22条：不再满足时按孰低计量（假设未分类账面 vs 可收回金额）</li>
        <li>逐项判定合规性：合规/不合规/不适用</li>
        <li>"不合规"项将触发顶部红色摘要提示</li>
        <li>调整后账面价值=min(假设未分类账面, 可收回金额)，由系统自动计算</li>
        <li>📎凭证引用列用于记录抽凭编号或附件参考</li>
        <li>点击"+新增"弹窗输入资产名称后创建新检查行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabNoLongerCheck.vue — K6-7 不再满足持有待售检查
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.6
 * Requirements: 7.1-7.4
 *
 * 功能：
 * - 逐项检查不再满足持有待售的资产
 * - 两者取低公式：adjustedBookValue = min(假设未分类账面, 可收回金额)
 * - 逐项"合规/不合规/不适用" el-radio-group
 * - hasNonCompliant → 红色摘要 el-alert
 * - 行级抽凭📎 (voucherRef field)
 * - 动态行 "+新增" (ElMessageBox.prompt)
 * - 蓝色引导区 + 琥珀色方法论 + 编制提示 + AI辅助
 */
import { inject, toRef, type Ref } from 'vue'
import { MagicStick, Delete } from '@element-plus/icons-vue'
import { useK6NoLongerCheck } from '@/components/workpaper/composables/useK6NoLongerCheck'

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

function handleAddItem(): void {
  addItem()
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
  return ''
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-no-longer-check { padding: 12px; font-size: 13px; }
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
.conclusion-card { margin-bottom: 12px; }

.section-card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

.formula-col :deep(.cell) { border-bottom: 1px dashed #409eff; cursor: help; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }

:deep(.non-compliant-row) { background-color: #fef0f0 !important; }

.k6-details-tip { margin-top: 16px; font-size: 12px; color: #666; }
.k6-details-tip summary { cursor: pointer; color: #409eff; font-weight: 500; }
.k6-details-tip ul { margin: 8px 0 0 16px; line-height: 1.8; }
</style>
