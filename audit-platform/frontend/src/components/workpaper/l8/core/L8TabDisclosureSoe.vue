<template>
  <div class="l8-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8 附注披露（国有企业）</h3>
        <el-tag type="info" size="small">从L8-1/L8-2自动取数</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业附注披露（财务费用）：</strong>
        国企报表附注按财政部企业财务通则要求披露，结构与上市公司类似但增加国资监管专项内容。
        需额外披露：①资金占用费②关联方借款利息③政策性贷款利息优惠。
        数据从L8-1审定表自动取得。
      </div>
    </div>

    <!-- ═══ 附注表格（3列：项目/本期/上期） ═══ -->
    <el-table :data="disclosureRows" border size="small" style="width: 100%">
      <el-table-column prop="item" label="项目" min-width="220" />
      <el-table-column label="本期金额" width="160" align="right">
        <template #default="{ row, $index }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.currentAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateDisclosure($index, 'currentAmount', val ?? 0)"
            />
          </template>
          <span v-else :class="{ 'formula-value': row.isFormula, 'total-value': row.isTotal }">
            {{ fmtAmount(row.currentAmount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" width="160" align="right">
        <template #default="{ row, $index }">
          <template v-if="row.isEditable && !isReadonly">
            <el-input-number
              :model-value="row.priorAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateDisclosure($index, 'priorAmount', val ?? 0)"
            />
          </template>
          <span v-else :class="{ 'formula-value': row.isFormula, 'total-value': row.isTotal }">
            {{ fmtAmount(row.priorAmount) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 国企专项说明 ═══ -->
    <el-card shadow="never" class="soe-extra-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">国企专项披露事项</span>
          <el-button size="small" @click="handleAI('soeExtra')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeExtraNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="国资监管专项内容（如：资金占用费/关联方借款/政策性贷款优惠）..."
        :disabled="isReadonly"
        @change="saveSoeExtra"
      />
    </el-card>

    <!-- ═══ 附注文本说明 ═══ -->
    <el-card shadow="never" class="note-text-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">附注文本说明</span>
          <el-button size="small" @click="handleAI('noteText')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="附注文本补充说明..."
        :disabled="isReadonly"
        @change="saveNoteText"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注与上市公司结构类似，增加国资监管专项内容</li>
        <li>需关注：资金占用费（非金融机构利息）/关联方借款利息/政策性贷款利息优惠</li>
        <li>数据自动从L8-1审定表取得（EventBus联动）</li>
        <li>合计行自动计算</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabDisclosureSoe — L8 附注披露（国有企业）
 *
 * Requirements: 7.5
 * - 3列结构：项目/本期金额/上期金额（同上市版）
 * - 增加国企专项披露事项区
 * - 从L8-1/L8-2自动取数（EventBus联动）
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL8FormData } from '../../composables/useL8FormData'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useL8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 附注行数据（国企版，增加国资专项行） ────────────────────────────────────

interface DisclosureRow {
  item: string
  currentAmount: number
  priorAmount: number
  isEditable: boolean
  isFormula: boolean
  isTotal: boolean
}

const disclosureRows = ref<DisclosureRow[]>([
  { item: '利息费用', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '  其中：金融机构借款利息', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '  其中：非金融机构借款利息', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '  其中：资金占用费', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '减：利息资本化金额', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '减：利息收入', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '汇兑损益（净损失以"+"号列示）', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '手续费', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '其他', currentAmount: 0, priorAmount: 0, isEditable: true, isFormula: false, isTotal: false },
  { item: '合  计', currentAmount: 0, priorAmount: 0, isEditable: false, isFormula: true, isTotal: true },
])

// ─── 合计行自动计算 ──────────────────────────────────────────────────────────

function recalcTotal() {
  const items = disclosureRows.value
  const totalIdx = items.length - 1
  // 合计 = 利息费用(0) - 利息资本化(4) - 利息收入(5) + 汇兑(6) + 手续费(7) + 其他(8)
  items[totalIdx].currentAmount = items[0].currentAmount - items[4].currentAmount - items[5].currentAmount + items[6].currentAmount + items[7].currentAmount + items[8].currentAmount
  items[totalIdx].priorAmount = items[0].priorAmount - items[4].priorAmount - items[5].priorAmount + items[6].priorAmount + items[7].priorAmount + items[8].priorAmount
}

function updateDisclosure(index: number, field: 'currentAmount' | 'priorAmount', value: number) {
  disclosureRows.value[index][field] = value
  recalcTotal()
  _triggerSave()
}

// ─── State ───────────────────────────────────────────────────────────────────

const noteText = ref('')
const soeExtraNote = ref('')
const isSaving = ref(false)

// ─── Handlers ────────────────────────────────────────────────────────────────

function _triggerSave() {
  formData.debouncedSave('L8-disclosure-soe-data', {
    remark: JSON.stringify(disclosureRows.value.map(r => ({
      item: r.item,
      currentAmount: r.currentAmount,
      priorAmount: r.priorAmount,
    }))),
  })
}

function saveNoteText() {
  formData.debouncedSave('L8-disclosure-soe-note', { remark: noteText.value || null })
}

function saveSoeExtra() {
  formData.debouncedSave('L8-disclosure-soe-extra', { remark: soeExtraNote.value || null })
}

async function handleSave() {
  isSaving.value = true
  try {
    _triggerSave()
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'L8', type: 'soe', timestamp: Date.now(),
    })
  } finally {
    isSaving.value = false
  }
}

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('L8-disclosure-soe', '附注(国企)') }

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjudicated() {
  formData.loadData().then(() => _restoreData())
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
  eventBus.on('substantive:adjudicated' as any, handleAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
})

function _restoreData() {
  const data = formData.allResponses.value.get('L8-disclosure-soe-data')
  if (data?.remark) {
    try {
      const parsed = JSON.parse(data.remark)
      if (Array.isArray(parsed)) {
        parsed.forEach((r: any, i: number) => {
          if (i < disclosureRows.value.length) {
            disclosureRows.value[i].currentAmount = r.currentAmount ?? 0
            disclosureRows.value[i].priorAmount = r.priorAmount ?? 0
          }
        })
        recalcTotal()
      }
    } catch { /* ignore */ }
  }
  const nt = formData.allResponses.value.get('L8-disclosure-soe-note')
  if (nt?.remark) noteText.value = nt.remark
  const extra = formData.allResponses.value.get('L8-disclosure-soe-extra')
  if (extra?.remark) soeExtraNote.value = extra.remark
}
</script>

<style scoped>
.l8-tab-disclosure-soe { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.formula-value { color: #409eff; font-weight: 500; }
.total-value { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: 13px; }
.soe-extra-card { margin-top: 16px; }
.note-text-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
