<!-- K3TabPayableCheck.vue — K3-7 其他应付款检查表（含反向截止测试） | Task 4.5 | Req 6.2-6.5, 7.2 -->
<template>
  <div class="k3-tab-payable-check">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K3-7其他应付款综合检查表包含两大区块：①8项综合合规检查（余额核对/大额异常/长期挂账/关联方/反向截止/分类/计价/披露）
        ②反向截止测试（期后偿付倒查未入账负债，验证完整性认定）。
        <b>负债类完整性认定为主</b>——负债易少计，反向截止是核心程序。</p>
    </div>

    <!-- 不合规摘要提示（红色） -->
    <el-alert
      v-if="nonComplianceSummary.count > 0"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    >
      <template #title>
        ⚠️ 发现 <b>{{ nonComplianceSummary.count }}</b> 项不合规/需处理事项
      </template>
      <template #default>
        <ul class="ncs-list">
          <li v-for="(item, idx) in nonComplianceSummary.items" :key="idx">
            <b>[{{ item.source }}]</b> {{ item.label }}：{{ item.detail || '未说明' }}
          </li>
        </ul>
      </template>
    </el-alert>

    <!-- ═══════════ 区块一：综合检查项 ═══════════ -->
    <div class="block-section">
      <div class="section-head">
        <h3 class="sheet-title">区块一：综合检查项（8项）</h3>
        <div class="head-actions">
          <el-button size="small" type="primary" link @click="handleAiGenerate('overall-opinion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
          <el-button size="small" @click="handleReview('K3-7-check')">💬 复核</el-button>
        </div>
      </div>

      <el-table :data="checkItems" border size="small" class="check-table" :row-style="checkRowStyle">
        <el-table-column type="index" label="#" width="40" align="center" />

        <el-table-column label="检查项目" min-width="200">
          <template #default="{ row }">
            <span class="check-label">{{ row.label }}</span>
            <p class="check-desc">{{ row.description }}</p>
          </template>
        </el-table-column>

        <el-table-column label="合规判定" width="140" align="center">
          <template #default="{ row }">
            <el-radio-group v-if="!isReadonly" :model-value="row.compliance" size="small"
              @change="(v: string) => handleCheckComplianceChange(row.id, v)">
              <el-radio-button value="合规">合规</el-radio-button>
              <el-radio-button value="不合规">不合规</el-radio-button>
              <el-radio-button value="不适用">N/A</el-radio-button>
            </el-radio-group>
            <el-tag v-else :type="complianceTagType(row.compliance)" size="small">
              {{ row.compliance || '未判定' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="审计证据" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
              :model-value="row.evidence" size="small" placeholder="审计证据/说明"
              @change="(v: string) => handleCheckEvidenceChange(row.id, v)" />
            <span v-else>{{ row.evidence || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══════════ 区块二：反向截止测试 ═══════════ -->
    <div class="block-section" style="margin-top: 24px;">
      <div class="section-head">
        <h3 class="sheet-title">区块二：反向截止测试（期后偿付表）</h3>
        <div class="head-actions">
          <el-button size="small" type="primary" link @click="handleAiGenerate('cutoff-analysis')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
          <el-button size="small" :disabled="isReadonly" @click="handleAddCutoffRow">＋ 新增</el-button>
          <el-button size="small" @click="handleReview('K3-7-cutoff')">💬 复核</el-button>
        </div>
      </div>

      <p class="cutoff-desc">
        反向截止测试：检查资产负债表日后偿付的款项，倒查是否属于期前负债但未入账（完整性认定——负债易少计）。
      </p>

      <el-table
        :data="reverseCutoffRows"
        border
        size="small"
        :max-height="400"
        class="cutoff-table"
        :row-style="cutoffRowStyle"
      >
        <el-table-column type="index" label="#" width="40" align="center" />

        <el-table-column label="付款对象" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.counterparty" size="small" placeholder="付款对象"
              @change="handleCutoffChange(row)" />
            <span v-else>{{ row.counterparty || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期后偿付日期" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.paymentDate" size="small" placeholder="YYYY-MM-DD"
              @change="handleCutoffChange(row)" />
            <span v-else>{{ row.paymentDate || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="偿付金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" size="small"
              :controls="false" class="amount-input"
              @change="handleCutoffChange(row)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="发票日期" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.invoiceDate" size="small" placeholder="YYYY-MM-DD"
              @change="handleCutoffChange(row)" />
            <span v-else>{{ row.invoiceDate || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否属期前" min-width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.belongsToPrior" size="small"
              @change="handleCutoffChange(row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待定" value="待定" />
            </el-select>
            <el-tag v-else :type="priorTagType(row.belongsToPrior)" size="small">
              {{ row.belongsToPrior }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="是否已入账" min-width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRecorded" size="small"
              @change="handleCutoffChange(row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <el-tag v-else :type="row.isRecorded === '是' ? 'success' : 'danger'" size="small">
              {{ row.isRecorded }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="结论" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" placeholder="截止结论"
              @change="handleCutoffChange(row)" />
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveCutoffRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 期后偿付未入账提示 -->
      <el-alert
        v-if="unrecordedCount > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 12px"
      >
        <template #title>
          发现 <b>{{ unrecordedCount }}</b> 笔期后偿付属于期前负债但期末未入账，合计 <b>{{ fmtAmt(unrecordedTotal) }}</b>，
          可能存在负债少计（完整性风险）
        </template>
      </el-alert>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li><b>区块一</b>：8项逐项判定合规/不合规/不适用；不合规项红色高亮+汇总至顶部摘要</li>
        <li><b>区块二</b>：反向截止测试——取期后（通常报告日后1-2个月）偿付清单，逐笔倒查：</li>
        <li style="margin-left: 20px;">① 发票/合同日期在期前 → "属期前"</li>
        <li style="margin-left: 20px;">② 期末账上未确认该笔负债 → "未入账" → 完整性认定风险</li>
        <li style="margin-left: 20px;">③ 结论：已入账=OK / 未入账且属期前=建议AJE补提</li>
        <li><b>完整性认定是负债类审计重点</b>：负债容易少计，反向截止是识别未入账负债的核心程序</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabPayableCheck.vue — K3-7 其他应付款检查表（含反向截止测试）
 * Spec: .kiro/specs/k3-other-payables/ | Task: 4.5
 * Requirements: 6.2-6.5, 7.2
 */
import { computed, inject, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useK3Checks, type K3CheckItem, type K3CutoffRow, type ComplianceState } from '../../composables/useK3Checks'

// ─── Props / Emits ───────────────────────────────────────────────────────────

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

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

function saveResponseFn(itemId: string, payload: any) {
  props.allResponses.set(itemId, { item_id: itemId, ...payload })
  emit('save', itemId, payload)
}

const {
  checkItems,
  reverseCutoffRows,
  nonComplianceSummary,
  updateCheckCompliance,
  updateCheckEvidence,
  addCutoffRow,
  removeCutoffRow,
  saveAll,
} = useK3Checks({ allResponses: allResponsesRef as any, saveResponse: saveResponseFn })

// ─── Computed ────────────────────────────────────────────────────────────────

/** 期后偿付中属期前但未入账的笔数 */
const unrecordedCount = computed(() =>
  reverseCutoffRows.value.filter(r => r.belongsToPrior === '是' && r.isRecorded === '否').length
)

/** 未入账合计金额 */
const unrecordedTotal = computed(() =>
  reverseCutoffRows.value
    .filter(r => r.belongsToPrior === '是' && r.isRecorded === '否')
    .reduce((sum, r) => sum + (r.amount || 0), 0)
)

// ─── 区块一操作 ──────────────────────────────────────────────────────────────

function handleCheckComplianceChange(itemId: string, value: string) {
  updateCheckCompliance(itemId, (value || null) as ComplianceState)
  persistAll()
}

function handleCheckEvidenceChange(itemId: string, value: string) {
  updateCheckEvidence(itemId, value)
  persistAll()
}

// ─── 区块二操作 ──────────────────────────────────────────────────────────────

function handleAddCutoffRow() {
  addCutoffRow()
  persistAll()
}

function handleRemoveCutoffRow(rowId: string) {
  removeCutoffRow(rowId)
  persistAll()
}

function handleCutoffChange(_row: K3CutoffRow) {
  persistAll()
}

function persistAll() {
  saveAll()
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function checkRowStyle({ row }: { row: K3CheckItem }): Record<string, string> {
  if (row.compliance === '不合规') return { 'background-color': '#fef2f2' }
  return {}
}

function cutoffRowStyle({ row }: { row: K3CutoffRow }): Record<string, string> {
  if (row.belongsToPrior === '是' && row.isRecorded === '否') return { 'background-color': '#fef2f2' }
  return {}
}

function complianceTagType(val: string | null): 'success' | 'danger' | 'info' | 'warning' {
  if (val === '合规') return 'success'
  if (val === '不合规') return 'danger'
  if (val === '不适用') return 'info'
  return 'warning'
}

function priorTagType(val: string): 'success' | 'danger' | 'warning' {
  if (val === '是') return 'danger'
  if (val === '否') return 'success'
  return 'warning'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiGenerate(section: string) {
  console.log('[K3-7] AI generate:', section)
}

function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k3-tab-payable-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context { border-left: 4px solid var(--el-color-warning); background: #fffbeb; padding: 10px 14px; margin-bottom: 16px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
.block-section { }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.check-table { font-size: var(--wp-font-size, 13px); }
.check-label { font-weight: 500; }
.check-desc { font-size: 11px; color: var(--el-text-color-secondary); margin: 4px 0 0; }
.cutoff-desc { font-size: 12px; color: var(--el-text-color-regular); margin-bottom: 12px; line-height: 1.6; }
.cutoff-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.ncs-list { padding-left: 16px; margin: 8px 0 0; line-height: 1.8; font-size: 12px; }
.compile-hint { margin-top: 20px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
