<template>
  <div class="k6-tab-group-impairment">
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
          <span class="section-title">K6-6 处置组减值分摊表</span>
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
              <span class="formula-cell">{{ fmtAmt(row.bookAfterImpairment) }}</span>
            </el-tooltip>
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
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明与结论</span>
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
        <li>各资产减值后账面价值下限：MAX(公允净额, 使用价值, 0)</li>
        <li>商誉减值不可转回</li>
        <li>组整体减值金额可从K6-5联动取得，也可手工录入</li>
        <li>"是否商誉"标记的资产参与第一步抵减，其余参与第二步按比例分摊</li>
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
import { computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { useK6GroupImpairment } from '../../composables/useK6GroupImpairment'

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
