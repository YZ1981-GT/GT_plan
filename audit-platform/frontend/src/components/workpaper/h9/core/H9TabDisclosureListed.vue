<template>
  <div class="h9-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实上市公司附注中租赁负债的分类列示、期末/上年年末余额及利息费用披露完整、准确，与 H9-1 审定表勾稽一致，符合 CAS21 及证监会信息披露要求。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>附注披露（上市公司）：按CAS21准则及证监会信息披露要求，披露租赁负债分类余额及利息费用。A1:F18，简单表格。</p>
    </div>

    <!-- 附注表格 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>47、租赁负债</span>
          <div class="title-actions">
            <el-button size="small" @click="$emit('open-review', 'disclosure-listed')">复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="tableRows" border size="small" class="disclosure-table">
        <el-table-column prop="item" label="项  目" min-width="180" />
        <el-table-column prop="endBalance" label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isSummary && !isReadonly"
              v-model="row.endBalance"
              :controls="false"
              :precision="2"
              size="small"
              class="num-input"
              @change="onDataChange"
            />
            <span v-else :class="{ 'summary-value': row.isSummary }">
              {{ row.endBalance != null ? row.endBalance.toFixed(2) : '' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="lastYearEnd" label="上年年末余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isSummary && !isReadonly"
              v-model="row.lastYearEnd"
              :controls="false"
              :precision="2"
              size="small"
              class="num-input"
              @change="onDataChange"
            />
            <span v-else :class="{ 'summary-value': row.isSummary }">
              {{ row.lastYearEnd != null ? row.lastYearEnd.toFixed(2) : '' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 利息费用补充说明 -->
    <el-card shadow="never" class="supplement-card">
      <template #header>
        <div class="section-title">
          <span>利息费用说明</span>
        </div>
      </template>
      <el-input
        v-model="interestNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="2024年计提的租赁负债利息费用金额为XX万元，计入财务费用-利息支出金额为XX万元，计入固定资产金额为XX万元。"
        @change="saveInterestNote"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注应按合同类型/租赁期限分项列示期末余额和上年年末余额</li>
        <li>应披露一年内到期金额（从合计中扣减）</li>
        <li>利息费用需说明计入财务费用或资本化的具体金额</li>
        <li>数据应与H9-1审定表一致（EventBus联动自动刷新）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabDisclosureListed.vue — 附注披露信息（上市公司）
 * A1:F18 简单表格：项目|期末余额|上年年末余额
 * Subscribe EventBus 'substantive:adjudicated' auto-refresh
 * Spec: Task 4.6 | Requirements: 1.2
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

// --- 数据模型 ---
interface DisclosureRow {
  item: string
  endBalance: number | null
  lastYearEnd: number | null
  isSummary: boolean
}

const defaultRows: DisclosureRow[] = [
  { item: '房屋及建筑物租赁', endBalance: null, lastYearEnd: null, isSummary: false },
  { item: '设备租赁', endBalance: null, lastYearEnd: null, isSummary: false },
  { item: '车辆租赁', endBalance: null, lastYearEnd: null, isSummary: false },
  { item: '其他', endBalance: null, lastYearEnd: null, isSummary: false },
]

const tableRows = ref<DisclosureRow[]>([])
const interestNote = ref('')

// 计算合计行
const summaryRows = computed(() => {
  const subtotalEnd = tableRows.value.reduce((s, r) => s + (r.endBalance || 0), 0)
  const subtotalLast = tableRows.value.reduce((s, r) => s + (r.lastYearEnd || 0), 0)
  return [
    ...tableRows.value,
    { item: '小  计', endBalance: subtotalEnd, lastYearEnd: subtotalLast, isSummary: true },
    { item: '减：一年内到期的租赁负债', endBalance: withinOneYear.value.end, lastYearEnd: withinOneYear.value.last, isSummary: false },
    { item: '合  计', endBalance: subtotalEnd - (withinOneYear.value.end || 0), lastYearEnd: subtotalLast - (withinOneYear.value.last || 0), isSummary: true },
  ]
})

const withinOneYear = ref({ end: null as number | null, last: null as number | null })

// --- 数据加载 ---
function loadFromResponses() {
  const data = props.allResponses.get('H9-disc-listed-rows')
  if (data) {
    try {
      const parsed = typeof data === 'string' ? JSON.parse(data) : data
      tableRows.value = parsed.rows || [...defaultRows]
      withinOneYear.value = parsed.withinOneYear || { end: null, last: null }
      interestNote.value = parsed.interestNote || ''
    } catch { tableRows.value = [...defaultRows] }
  } else {
    tableRows.value = [...defaultRows]
  }
  const noteItem = props.allResponses.get('H9-disc-listed-audit-note')
  const conclusionItem = props.allResponses.get('H9-disc-listed-audit-conclusion')
}

// --- 保存 ---
function onDataChange() {
  saveAll()
}

function saveInterestNote() {
  saveAll()
}

function saveAll() {
  const payload = {
    rows: tableRows.value,
    withinOneYear: withinOneYear.value,
    interestNote: interestNote.value,
  }
  emit('save', 'H9-disc-listed-rows', JSON.stringify(payload))
}

// --- EventBus: subscribe adjudicated to refresh ---
let unsubscribe: (() => void) | null = null

function subscribeEventBus() {
  // EventBus pattern: listen for adjudicated to trigger data refresh
  const bus = (window as any).__auditEventBus
  if (bus?.on) {
    const handler = (payload: any) => {
      if (payload?.wpCode?.startsWith('H9')) loadFromResponses()
    }
    bus.on('substantive:adjudicated', handler)
    unsubscribe = () => bus.off('substantive:adjudicated', handler)
  }
}

// --- Lifecycle ---
onMounted(() => {
  loadFromResponses()
  subscribeEventBus()
})

onUnmounted(() => { unsubscribe?.() })

watch(() => props.allResponses, loadFromResponses, { deep: true })
</script>

<style scoped>
.h9-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.disclosure-card { margin-bottom: 16px; }
.disclosure-table { width: 100%; }
.num-input { width: 100%; }
.summary-value { font-weight: 600; }

.supplement-card { margin-bottom: 16px; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
