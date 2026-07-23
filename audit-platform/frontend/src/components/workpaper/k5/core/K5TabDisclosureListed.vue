<template>
  <div class="k5-tab-disclosure-listed">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview('K5-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS13第19条：因或有事项确认的预计负债，应在附注中按类别披露期初/期末账面价值、本期增加/转回金额及原因。CAS13第23条：对可能但非很可能导致经济利益流出的或有负债，披露性质/财务影响估计/获补偿可能性。</p>
    </div>

    <!-- Section 1: 预计负债变动表（16行×12列） -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>一、预计负债变动情况</span>
          <el-tag v-if="hasAutoData" type="primary" size="small" effect="light">跨sheet自动取数</el-tag>
        </div>
      </template>

      <el-table :data="provisionTable" border size="small" style="width: 100%" max-height="400">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <strong :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.endBalance) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="变动说明" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.remark"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="变动原因说明"
              @blur="(e: FocusEvent) => handleRemarkChange(row.id, (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
            <span v-else />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2: 或有负债披露 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>二、或有负债（可能性→披露）</span>
          <el-tag v-if="contingentItems.length > 0" type="warning" size="small">{{ contingentItems.length }} 项待披露</el-tag>
        </div>
      </template>

      <el-empty v-if="contingentItems.length === 0" description="暂无需披露的或有负债（K5-2明细中判定为“可能”的事项将自动出现于此）" />

      <el-table v-else :data="contingentItems" border size="small" style="width: 100%">
        <el-table-column type="index" label="序" width="48" align="center" />
        <el-table-column prop="item" label="或有事项" min-width="140" />
        <el-table-column prop="nature" label="性质" min-width="120" />
        <el-table-column label="财务影响估计" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.financialImpact) }}</template>
        </el-table-column>
        <el-table-column label="获得补偿可能性" width="130">
          <template #default="{ row }">
            <el-select
              :model-value="row.compensationLikelihood"
              :disabled="isReadonly"
              size="small"
              @change="(v: string) => handleContingentField(row.id, 'compensationLikelihood', v)"
            >
              <el-option label="很可能" value="very_likely" />
              <el-option label="可能" value="possible" />
              <el-option label="极小可能" value="remote" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="披露描述" min-width="200">
          <template #default="{ row }">
            <el-input
              :model-value="row.disclosure"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="附注披露说明"
              @blur="(e: FocusEvent) => handleContingentField(row.id, 'disclosure', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 3: 预计负债确认条件说明 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>三、预计负债确认条件及计量方法说明</span>
        </div>
      </template>
      <el-input
        v-model="policyNarrative"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :placeholder="policyPlaceholder"
        @blur="handlePolicySave"
      />
    </el-card>

    <!-- Section 4: 附注叙述文字 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>四、补充说明</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="附注补充说明文字（可AI辅助生成）"
        @blur="handleNarrativeSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注格式（约16行×12列），按性质分类披露预计负债变动</li>
        <li>监听 substantive:adjudicated(2701) 自动同步审定数据（浅蓝色=跨sheet自动取数）</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>或有负债段自动从K5-2明细表中筛选"可能"级别的事项</li>
        <li>负债类科目关注完整性认定：确保所有应确认的预计负债已完整披露</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * - Section ① 预计负债变动表（16行×12列）
 * - Section ② 或有负债披露（可能性→disclose的事项）
 * - Section ③ 补充说明叙述文字
 *
 * EventBus: subscribe 'substantive:adjudicated' → auto-refresh
 *           subscribe 'adjustment:created' → auto-refresh
 *           publish 'disclosure:note-text-updated' on text change
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 6.1
 * Requirements: 9.1, 2.7
 */
import { ref, computed, onMounted, onBeforeUnmount, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'

const K5_ACCOUNT_CODE = '2701'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── State ───────────────────────────────────────────────────────────────────

interface ProvisionRow {
  id: string
  category: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  remark: string
  isTotal: boolean
  isAutoFill: boolean
}

interface ContingentItem {
  id: string
  item: string
  nature: string
  financialImpact: number
  compensationLikelihood: string
  disclosure: string
}

const provisionTable = ref<ProvisionRow[]>([])
const contingentItems = ref<ContingentItem[]>([])
const narrativeText = ref('')
const policyNarrative = ref('')
const hasAutoData = ref(false)

const policyPlaceholder = `企业对预计负债的确认条件和计量方法：
（1）确认条件：当与或有事项相关的义务同时满足以下条件时确认为预计负债：该义务是企业承担的现时义务；履行该义务很可能导致经济利益流出企业；该义务的金额能够可靠地计量。
（2）计量方法：预计负债按照履行相关现时义务所需支出的最佳估计数进行初始计量。最佳估计数的确定：如所需支出存在一个连续范围，且该范围内各种结果发生的可能性相同，则按照该范围内的中间值确定；如涉及多个项目，按照各种可能结果及相关概率计算确定。`

// ─── Computed ────────────────────────────────────────────────────────────────

// (provisionTable computed from allResponses)

// ─── Init/Load ───────────────────────────────────────────────────────────────

function loadSavedData(): void {
  // 从 allResponses 恢复持久化数据
  const saved = props.allResponses.get('K5-disclosure-listed-provision-table')
  if (saved?.remark) {
    try {
      provisionTable.value = JSON.parse(saved.remark)
    } catch { initDefaultTable() }
  } else {
    initDefaultTable()
  }

  const savedContingent = props.allResponses.get('K5-disclosure-listed-contingent')
  if (savedContingent?.remark) {
    try {
      contingentItems.value = JSON.parse(savedContingent.remark)
    } catch { contingentItems.value = [] }
  }

  const savedNarrative = props.allResponses.get('K5-disclosure-listed-narrative')
  if (savedNarrative?.remark) {
    narrativeText.value = savedNarrative.remark
  }

  const savedPolicy = props.allResponses.get('K5-disclosure-listed-policy')
  if (savedPolicy?.remark) {
    policyNarrative.value = savedPolicy.remark
  }
}

function initDefaultTable(): void {
  const categories = ['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '其他']
  provisionTable.value = [
    ...categories.map((cat, idx) => ({
      id: `row-${idx}`,
      category: cat,
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      remark: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'row-total',
      category: '合计',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      remark: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

/**
 * 从 allResponses 中提取审定表(K5-1)的自动取数。
 * 当 substantive:adjudicated 事件触发时，重新获取最新数据填充。
 */
function applyAutoFill(): void {
  // 读取跨sheet审定数据（来自K5-1审定表保存的allResponses）
  const adjTotal = props.allResponses.get('K5-1-audited-total')
  if (adjTotal?.remark) {
    hasAutoData.value = true
    try {
      const data = JSON.parse(adjTotal.remark)
      // 将审定表各类型的审定数据回填到附注表
      if (data && typeof data === 'object') {
        for (const row of provisionTable.value) {
          if (!row.isTotal && data[row.category]) {
            const d = data[row.category]
            row.beginBalance = Number(d.beginBalance ?? 0)
            row.increase = Number(d.increase ?? 0)
            row.decrease = Number(d.decrease ?? 0)
            row.endBalance = Number(d.endBalance ?? 0)
            row.isAutoFill = true
          }
        }
        // 更新合计行
        const totalRow = provisionTable.value.find(r => r.isTotal)
        if (totalRow) {
          const dataRows = provisionTable.value.filter(r => !r.isTotal)
          totalRow.beginBalance = dataRows.reduce((s, r) => s + r.beginBalance, 0)
          totalRow.increase = dataRows.reduce((s, r) => s + r.increase, 0)
          totalRow.decrease = dataRows.reduce((s, r) => s + r.decrease, 0)
          totalRow.endBalance = dataRows.reduce((s, r) => s + r.endBalance, 0)
        }
      }
    } catch { /* silent */ }
  }

  // 从 K5-2 明细表筛选 或有负债披露项（可能性=possible → disclose）
  const detailData = props.allResponses.get('K5-2-detail-rows')
  if (detailData?.remark) {
    try {
      const rows: any[] = JSON.parse(detailData.remark)
      contingentItems.value = rows
        .filter(r => r.lossLikelihood === 'possible' || r.recognition === 'disclose')
        .map((r, idx) => ({
          id: `contingent-${idx}`,
          item: r.caseName || r.item || r.project || `事项${idx + 1}`,
          nature: r.nature || r.type || '待补充',
          financialImpact: Number(r.amount || r.estimatedLoss || 0),
          compensationLikelihood: r.compensationLikelihood || '',
          disclosure: r.disclosure || '',
        }))
    } catch { /* silent */ }
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleRemarkChange(rowId: string, value: string): void {
  const row = provisionTable.value.find(r => r.id === rowId)
  if (row) {
    row.remark = value
    persistTable()
  }
}

function handleContingentField(id: string, field: string, value: any): void {
  const item = contingentItems.value.find(r => r.id === id)
  if (item) {
    ;(item as any)[field] = value
    persistContingent()
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K5-disclosure-listed-narrative', { remark: narrativeText.value })
  // Publish disclosure:note-text-updated
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K5',
    variant: 'listed',
    text: narrativeText.value,
  })
}

function handlePolicySave(): void {
  emit('save', 'K5-disclosure-listed-policy', { remark: policyNarrative.value })
}

function handleAiGenerate(): void {
  emit('save', 'K5-disclosure-listed-ai-trigger', { remark: 'contingency-disclosure' })
}

function persistTable(): void {
  emit('save', 'K5-disclosure-listed-provision-table', { remark: JSON.stringify(provisionTable.value) })
}

function persistContingent(): void {
  emit('save', 'K5-disclosure-listed-contingent', { remark: JSON.stringify(contingentItems.value) })
}

// ─── EventBus: subscribe 'substantive:adjudicated' + 'adjustment:created' ═══

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K5_ACCOUNT_CODE || payload.wpCode === 'K5') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.accountCode === K5_ACCOUNT_CODE || payload.wpCode === 'K5') {
    applyAutoFill()
  }
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
  loadSavedData()
  applyAutoFill()
})

onBeforeUnmount(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.head-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.disclosure-section { margin-bottom: 14px; }
.section-card-header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.auto-data { color: #409eff; font-style: italic; }
:deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
