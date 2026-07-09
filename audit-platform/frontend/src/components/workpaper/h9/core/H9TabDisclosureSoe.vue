<template>
  <div class="h9-tab-disclosure-soe">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>附注披露（国企）：按国资委信息公开要求和CAS21准则，披露租赁负债明细（含租赁付款额、未确认融资费用、净额）。A1:F16，简单表格。</p>
    </div>

    <!-- 附注表格 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>49、租赁负债</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain @click="handleAiGenerate">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'disclosure-soe')">复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="displayRows" border size="small" class="disclosure-table">
        <el-table-column prop="item" label="项  目" min-width="200" />
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
        <el-table-column prop="beginBalance" label="期初余额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isSummary && !isReadonly"
              v-model="row.beginBalance"
              :controls="false"
              :precision="2"
              size="small"
              class="num-input"
              @change="onDataChange"
            />
            <span v-else :class="{ 'summary-value': row.isSummary }">
              {{ row.beginBalance != null ? row.beginBalance.toFixed(2) : '' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- CAS21准则提示 -->
    <el-card shadow="never" class="supplement-card">
      <template #header>
        <div class="section-title">
          <span>补充披露说明</span>
          <el-button size="small" type="primary" plain @click="handleAiSupplement">AI 辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="supplementNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="1、承租人根据《企业会计准则第21号——租赁》所确认的租赁负债发生的利息费用适用借款费用准则...&#10;2、承租人向出租人支付的租金等款项中包含应缴纳的增值税的..."
        @change="saveSupplementNote"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注需列示：租赁付款额、减未确认融资费用、重分类至一年内到期、租赁负债净额</li>
        <li>净额=租赁付款额-未确认融资费用-一年内到期</li>
        <li>CAS21利息费用不资本化（租赁期开始日便达到预定可使用状态）</li>
        <li>增值税不属于租赁付款额范畴，不纳入计量</li>
        <li>数据应与H9-1审定表一致（EventBus联动自动刷新）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabDisclosureSoe.vue — 附注披露信息（国企）
 * A1:F16 简单表格：项目|期末余额|期初余额 + 净额行
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
  beginBalance: number | null
  isSummary: boolean
}

const editableRows = ref<DisclosureRow[]>([])
const supplementNote = ref('')

const defaultRows: DisclosureRow[] = [
  { item: '租赁付款额', endBalance: null, beginBalance: null, isSummary: false },
  { item: '减：未确认的融资费用', endBalance: null, beginBalance: null, isSummary: false },
  { item: '重分类至一年内到期的非流动负债', endBalance: null, beginBalance: null, isSummary: false },
]

// 计算净额行
const displayRows = computed(() => {
  const rows = [...editableRows.value]
  const paymentEnd = rows[0]?.endBalance || 0
  const unrecEnd = rows[1]?.endBalance || 0
  const withinEnd = rows[2]?.endBalance || 0
  const paymentBegin = rows[0]?.beginBalance || 0
  const unrecBegin = rows[1]?.beginBalance || 0
  const withinBegin = rows[2]?.beginBalance || 0

  rows.push({
    item: '租赁负债净额',
    endBalance: paymentEnd - unrecEnd - withinEnd,
    beginBalance: paymentBegin - unrecBegin - withinBegin,
    isSummary: true,
  })
  return rows
})

// --- 数据加载 ---
function loadFromResponses() {
  const data = props.allResponses.get('H9-disc-soe-rows')
  if (data) {
    try {
      const parsed = typeof data === 'string' ? JSON.parse(data) : data
      editableRows.value = parsed.rows || [...defaultRows]
      supplementNote.value = parsed.supplementNote || ''
    } catch { editableRows.value = [...defaultRows] }
  } else {
    editableRows.value = [...defaultRows]
  }
}

// --- 保存 ---
function onDataChange() {
  saveAll()
}

function saveSupplementNote() {
  saveAll()
}

function saveAll() {
  const payload = {
    rows: editableRows.value,
    supplementNote: supplementNote.value,
  }
  emit('save', 'H9-disc-soe-rows', JSON.stringify(payload))
}

// --- AI ---
function handleAiGenerate() {
  emit('open-ai', 'disclosure-soe')
}

function handleAiSupplement() {
  emit('open-ai', 'disclosure-soe-supplement')
}

// --- EventBus: subscribe adjudicated to refresh ---
let unsubscribe: (() => void) | null = null

function subscribeEventBus() {
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
.h9-tab-disclosure-soe { padding: 16px; font-size: 13px; }

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
