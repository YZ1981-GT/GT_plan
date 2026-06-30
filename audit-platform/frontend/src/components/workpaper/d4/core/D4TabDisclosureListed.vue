<script setup lang="ts">
/**
 * D4TabDisclosureListed — 附注披露（上市公司版）
 *
 * 3子节卡片: (1)营业收入和营业成本 (2)合同收入分解 (3)前五大客户收入
 * 跨sheet取数浅蓝色 + 动态行 + 合计
 * applicable_standards判断显隐 + 说明textarea + EventBus note-text-updated
 *
 * Requirements: 6.1-6.10
 */
import { ref, computed, watch, inject, toRef, type Ref } from 'vue'
import { parseNum, calcSubtotal } from '../../composables/useD4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 跨sheet取数（D4-1审定数 → 营业收入/成本） ──────────────────────────
const revenueFromAdj = computed(() => {
  const mainSubResp = props.allResponses.get('D4-1-adj-rows')
  // 简化：从grandTotal取
  const d4_2_resp = props.allResponses.get('D4-2-rows')
  let mainRevenue = 0
  if (d4_2_resp?.remark) {
    try {
      const rows = JSON.parse(d4_2_resp.remark)
      if (Array.isArray(rows)) {
        for (const row of rows) {
          const months = Array.isArray(row.months) ? row.months.map(parseNum) : []
          mainRevenue += months.reduce((s: number, v: number) => s + v, 0) + parseNum(row.auditAdjustment)
        }
      }
    } catch { /* silent */ }
  }
  const d4_3_resp = props.allResponses.get('D4-3-rows')
  let otherRevenue = 0
  if (d4_3_resp?.remark) {
    try {
      const rows = JSON.parse(d4_3_resp.remark)
      if (Array.isArray(rows)) {
        for (const row of rows) {
          otherRevenue += parseNum(row.currentUnadjusted) + parseNum(row.currentAdjustment)
        }
      }
    } catch { /* silent */ }
  }
  return { main: mainRevenue, other: otherRevenue, total: mainRevenue + otherRevenue }
})

// 成本从TB取（跨循环，科目6401+6402）
const costFromTb = computed(() => {
  const mainCost = parseNum(props.allResponses.get('D4-note-listed-cost-6401')?.remark)
  const otherCost = parseNum(props.allResponses.get('D4-note-listed-cost-6402')?.remark)
  return { main: mainCost, other: otherCost, total: mainCost + otherCost }
})

// ─── Section 1: 营业收入和营业成本 ─────────────────────────────────────
const section1Data = computed(() => [
  { label: '主营业务收入', revenue: revenueFromAdj.value.main, cost: costFromTb.value.main },
  { label: '其他业务收入', revenue: revenueFromAdj.value.other, cost: costFromTb.value.other },
  { label: '合计', revenue: revenueFromAdj.value.total, cost: costFromTb.value.total },
])

// ─── Section 2: 合同收入分解（动态行，从D4-2按产品拆） ─────────────────
interface ContractRevenueRow {
  rowId: string
  category: string
  currentAmount: number
  priorAmount: number
}

const SECTION2_KEY = 'D4-note-listed-section2-rows'

const section2Rows = ref<ContractRevenueRow[]>([])

function loadSection2() {
  const resp = props.allResponses.get(SECTION2_KEY)
  if (resp?.remark) {
    try {
      const parsed = JSON.parse(resp.remark)
      if (Array.isArray(parsed)) {
        section2Rows.value = parsed.map((r: any) => ({
          rowId: r.rowId || `s2-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
          category: r.category || '',
          currentAmount: parseNum(r.currentAmount),
          priorAmount: parseNum(r.priorAmount),
        }))
        return
      }
    } catch { /* silent */ }
  }
  section2Rows.value = []
}

watch(() => props.allResponses.get(SECTION2_KEY)?.remark, loadSection2, { immediate: true })

const section2Total = computed(() => ({
  currentAmount: calcSubtotal(section2Rows.value.map(r => r.currentAmount)),
  priorAmount: calcSubtotal(section2Rows.value.map(r => r.priorAmount)),
}))

function addSection2Row() {
  if (props.isReadonly) return
  section2Rows.value.push({
    rowId: `s2-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    category: '',
    currentAmount: 0,
    priorAmount: 0,
  })
  persistSection2()
}

function removeSection2Row(rowId: string) {
  if (props.isReadonly) return
  section2Rows.value = section2Rows.value.filter(r => r.rowId !== rowId)
  persistSection2()
}

function persistSection2() {
  const json = JSON.stringify(section2Rows.value)
  const map = props.allResponses as Map<string, any>
  map.set(SECTION2_KEY, { item_id: SECTION2_KEY, conclusion: null, remark: json })
}

// ─── Section 3: 前五大客户收入（动态行） ────────────────────────────────
interface Top5CustomerRow {
  rowId: string
  name: string
  amount: number
  proportion: number
}

const SECTION3_KEY = 'D4-note-listed-section3-rows'

const section3Rows = ref<Top5CustomerRow[]>([])

function loadSection3() {
  const resp = props.allResponses.get(SECTION3_KEY)
  if (resp?.remark) {
    try {
      const parsed = JSON.parse(resp.remark)
      if (Array.isArray(parsed)) {
        section3Rows.value = parsed.map((r: any) => ({
          rowId: r.rowId || `s3-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
          name: r.name || '',
          amount: parseNum(r.amount),
          proportion: parseNum(r.proportion),
        }))
        return
      }
    } catch { /* silent */ }
  }
  section3Rows.value = []
}

watch(() => props.allResponses.get(SECTION3_KEY)?.remark, loadSection3, { immediate: true })

const section3Total = computed(() => {
  const totalAmt = calcSubtotal(section3Rows.value.map(r => r.amount))
  const totalRevenue = revenueFromAdj.value.total
  return {
    amount: totalAmt,
    proportion: totalRevenue > 0 ? (totalAmt / totalRevenue * 100) : 0,
  }
})

function addSection3Row() {
  if (props.isReadonly) return
  section3Rows.value.push({
    rowId: `s3-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    name: '',
    amount: 0,
    proportion: 0,
  })
  persistSection3()
}

function removeSection3Row(rowId: string) {
  if (props.isReadonly) return
  section3Rows.value = section3Rows.value.filter(r => r.rowId !== rowId)
  persistSection3()
}

function persistSection3() {
  const json = JSON.stringify(section3Rows.value)
  const map = props.allResponses as Map<string, any>
  map.set(SECTION3_KEY, { item_id: SECTION3_KEY, conclusion: null, remark: json })
}

// ─── 附注说明文本 ─────────────────────────────────────────────────────
const noteText = computed({
  get: () => props.allResponses.get('D4-note-listed-text')?.remark || '',
  set: (val: string) => {
    const map = props.allResponses as Map<string, any>
    map.set('D4-note-listed-text', { item_id: 'D4-note-listed-text', conclusion: null, remark: val })
    // 发布note-text-updated事件
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { wpCode: 'D4', section: 'listed', text: val },
      }))
    } catch { /* silent */ }
  },
})
</script>

<template>
  <div class="d4-tab-disclosure-listed">
    <!-- Section 1: 营业收入和营业成本 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <span class="section-title">(一) 营业收入和营业成本</span>
      </template>
      <el-table :data="section1Data" border size="small" style="width: 100%">
        <el-table-column prop="label" label="项目" width="160" />
        <el-table-column label="本期收入" width="140" align="right">
          <template #default="{ row }">
            <span class="cross-sheet-cell">{{ fmtAmount(row.revenue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期成本" width="140" align="right">
          <template #default="{ row }">
            <span :class="row.cost === 0 ? 'placeholder-cell' : 'cross-sheet-cell'">
              {{ row.cost === 0 ? '待M循环审定' : fmtAmount(row.cost) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="毛利" width="140" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.revenue - row.cost) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2: 合同收入分解 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(二) 合同收入分解</span>
          <el-button size="small" :disabled="isReadonly" @click="addSection2Row">+ 添加行</el-button>
        </div>
      </template>
      <el-table :data="[...section2Rows, { rowId: 'total', category: '合计', currentAmount: section2Total.currentAmount, priorAmount: section2Total.priorAmount }]" border size="small" style="width: 100%">
        <el-table-column label="收入类别" width="180">
          <template #default="{ row }">
            <template v-if="row.rowId === 'total'">
              <span class="font-bold">合计</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.category"
                size="small"
                placeholder="收入类别"
                @change="(v: string) => { row.category = v; persistSection2() }"
              />
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="本期金额" width="140" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'total'">
              <span class="font-bold">{{ fmtAmount(row.currentAmount) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.currentAmount"
                size="small"
                type="number"
                @change="(v: string) => { row.currentAmount = parseNum(v); persistSection2() }"
              />
              <span v-else>{{ fmtAmount(row.currentAmount) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="上期金额" width="140" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'total'">
              <span class="font-bold">{{ fmtAmount(row.priorAmount) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.priorAmount"
                size="small"
                type="number"
                @change="(v: string) => { row.priorAmount = parseNum(v); persistSection2() }"
              />
              <span v-else>{{ fmtAmount(row.priorAmount) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.rowId !== 'total' && !isReadonly"
              type="danger"
              size="small"
              link
              @click="removeSection2Row(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 3: 前五大客户收入 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(三) 前五大客户收入</span>
          <el-button size="small" :disabled="isReadonly" @click="addSection3Row">+ 添加行</el-button>
        </div>
      </template>
      <el-table :data="[...section3Rows, { rowId: 'total', name: '合计', amount: section3Total.amount, proportion: section3Total.proportion }]" border size="small" style="width: 100%">
        <el-table-column label="客户名称" width="200">
          <template #default="{ row }">
            <template v-if="row.rowId === 'total'">
              <span class="font-bold">合计</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.name"
                size="small"
                placeholder="客户名称"
                @change="(v: string) => { row.name = v; persistSection3() }"
              />
              <span v-else>{{ row.name || '-' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="销售额" width="140" align="right">
          <template #default="{ row }">
            <template v-if="row.rowId === 'total'">
              <span class="font-bold">{{ fmtAmount(row.amount) }}</span>
            </template>
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.amount"
                size="small"
                type="number"
                @change="(v: string) => { row.amount = parseNum(v); persistSection3() }"
              />
              <span v-else>{{ fmtAmount(row.amount) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="占比(%)" width="100" align="right">
          <template #default="{ row }">
            <span>{{ row.proportion.toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.rowId !== 'total' && !isReadonly"
              type="danger"
              size="small"
              link
              @click="removeSection3Row(row.rowId)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 附注说明 -->
    <div class="audit-note-section">
      <div class="note-header">
        <h4>说明</h4>
        <div class="note-actions">
          <el-button size="small" circle @click="openReviewDialog?.('D4-note-listed')">💬</el-button>
        </div>
      </div>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入附注披露说明文本（将同步至附注模块）..."
        :disabled="isReadonly"
      />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-disclosure-listed {
  padding: 12px;
}
.section-card {
  margin-bottom: 16px;
}
.section-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.section-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.cross-sheet-cell {
  background-color: #e6f7ff;
  padding: 2px 4px;
  border-radius: 2px;
}
.placeholder-cell {
  color: #c0c4cc;
  font-style: italic;
}
.font-bold {
  font-weight: 600;
}
.audit-note-section {
  margin-bottom: 16px;
}
.note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.note-header h4 {
  margin: 0;
  font-size: 14px;
  color: #303133;
}
.note-actions {
  display: flex;
  gap: 6px;
}
</style>
