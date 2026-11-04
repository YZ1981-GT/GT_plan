<template>
  <div class="gt-booking-picker">
    <div class="gt-booking-picker__search">
      <el-input v-model="voucherNo" placeholder="凭证号（必填）" clearable class="gt-booking-picker__no"
        data-testid="booking-picker-no" @keyup.enter="lookup()" />
      <el-date-picker v-model="voucherDate" type="date" value-format="YYYY-MM-DD" placeholder="凭证日期（可选）"
        class="gt-booking-picker__date" data-testid="booking-picker-date" />
      <el-button type="primary" plain :loading="looking" :disabled="!voucherNo.trim() || year == null"
        data-testid="booking-picker-lookup" @click="lookup()">
        查找
      </el-button>
    </div>
    <div v-if="year == null" class="gt-booking-picker__hint">项目未填审计年度，不能按当前账套查找凭证</div>
    <el-alert v-if="lookupError" type="warning" :closable="false" show-icon :title="lookupError"
      class="gt-booking-picker__block" data-testid="booking-picker-error" />

    <!-- 同号多张凭证（409）：列候选，选一张再取分录 -->
    <div v-if="candidates.length" class="gt-booking-picker__block" data-testid="booking-picker-candidates">
      <div class="gt-booking-picker__hint">
        凭证号 {{ candidateNo }} 在当前账套有 {{ candidates.length }} 张凭证{{ candidatesTruncated ? '（只列了前 50 张，可补填日期缩小范围）' : '' }}，请选一张：
      </div>
      <el-table :data="candidates" size="small" border max-height="220">
        <el-table-column label="凭证" min-width="120">
          <template #default="{ row }">{{ voucherLabel(row.voucher_type, row.voucher_no) }}</template>
        </el-table-column>
        <el-table-column prop="voucher_date" label="日期" width="110" />
        <el-table-column prop="line_count" label="分录数" width="70" align="right" />
        <el-table-column label="借方合计" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.debit_total" /></template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="140" show-overflow-tooltip />
        <el-table-column label="" width="80" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="pickCandidate(row)">选这张</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 查到的一张凭证：看分录确认后加入 -->
    <div v-if="preview" class="gt-booking-picker__block" data-testid="booking-picker-preview">
      <div class="gt-booking-picker__preview-head">
        <strong>{{ preview.item.voucher_date }} {{ preview.item.label }}</strong>
        <span class="gt-booking-picker__hint">{{ preview.item.line_count }} 行分录，借方合计 {{ preview.item.debit_total }}</span>
        <el-button size="small" type="primary" data-testid="booking-picker-add" @click="addPreview">加入</el-button>
      </div>
      <el-table :data="preview.lines" size="small" border max-height="220">
        <el-table-column label="科目" min-width="170">
          <template #default="{ row }">{{ row.account_code }} {{ row.account_name || '' }}</template>
        </el-table-column>
        <el-table-column label="借方" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.debit_amount" /></template>
        </el-table-column>
        <el-table-column label="贷方" width="120" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.credit_amount" /></template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="140" show-overflow-tooltip />
      </el-table>
    </div>

    <div class="gt-booking-picker__selected-title">已选凭证（{{ modelValue.length }}）</div>
    <el-table v-if="modelValue.length" :data="modelValue" size="small" border data-testid="booking-picker-selected">
      <el-table-column label="凭证" min-width="120">
        <template #default="{ row }">{{ row.voucher_date }} {{ row.label }}</template>
      </el-table-column>
      <el-table-column prop="line_count" label="分录数" width="70" align="right" />
      <el-table-column label="借方合计" width="120" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.debit_total" /></template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="140" show-overflow-tooltip />
      <el-table-column label="" width="70" align="center">
        <template #default="{ row }">
          <el-button link type="danger" @click="remove(row.voucher_key)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-else class="gt-booking-picker__hint">尚未选择凭证</div>
  </div>
</template>

<script setup lang="ts">
/**
 * 客户入账凭证选择器（spec voucher-workflow-linkage-lineage-closure R5.1，design §7.1）：
 * 凭证号（必填）+ 日期（可选）→ 当前账套这张凭证的分录；同号多张时列候选选一张；没有时说明。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { fetchVoucherLines } from '@/components/workpaper/composables/useAttachedVouchers'
import { voucherKeyAmbiguityOf, voucherLabel, type VoucherKeyCandidate } from '@/utils/voucherIdentity'
import {
  BOOKING_VOUCHER_MAX, VOUCHER_NOT_IN_DATASET, pickedFromLines, voucherLookupFailureText,
  type PickedBookingVoucher,
} from './clientBookingVoucher'

const props = defineProps<{ projectId: string; year: number | null; modelValue: PickedBookingVoucher[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: PickedBookingVoucher[]] }>()

const voucherNo = ref('')
const voucherDate = ref<string | null>(null)
const looking = ref(false)
const lookupError = ref<string | null>(null)
const candidates = ref<VoucherKeyCandidate[]>([])
const candidatesTruncated = ref(false)
const candidateNo = ref('')
const preview = ref<{ item: PickedBookingVoucher; lines: Array<Record<string, unknown>> } | null>(null)
let lookupSeq = 0

/** 查一张凭证：不给 target 时按输入框（号 + 可选日期）；给 target 时按候选的完整凭证键定位 */
async function lookup(target?: VoucherKeyCandidate) {
  const year = props.year
  const no = (target?.voucher_no ?? voucherNo.value).trim()
  if (!no || year == null) return
  const seq = ++lookupSeq
  looking.value = true
  lookupError.value = null
  preview.value = null
  if (!target) candidates.value = []
  try {
    const lines = target
      ? await fetchVoucherLines(props.projectId, year, no, target.voucher_date, target.voucher_type, target.company_code)
      : await fetchVoucherLines(props.projectId, year, no, voucherDate.value || null)
    if (seq !== lookupSeq) return
    const item = pickedFromLines(lines, year)
    if (!item) {
      lookupError.value = VOUCHER_NOT_IN_DATASET
      return
    }
    candidates.value = []
    preview.value = { item, lines }
  } catch (err) {
    if (seq !== lookupSeq) return
    const ambiguity = voucherKeyAmbiguityOf(err)
    if (ambiguity && ambiguity.candidates.length) {
      candidates.value = ambiguity.candidates
      candidatesTruncated.value = ambiguity.truncated
      candidateNo.value = no
    } else {
      lookupError.value = voucherLookupFailureText(err)
    }
  } finally {
    if (seq === lookupSeq) looking.value = false
  }
}

function pickCandidate(candidate: VoucherKeyCandidate) {
  void lookup(candidate)
}

function addPreview() {
  const item = preview.value?.item
  if (!item) return
  if (props.modelValue.some(v => v.voucher_key === item.voucher_key)) {
    ElMessage.info('这张凭证已在已选列表里')
    return
  }
  if (props.modelValue.length >= BOOKING_VOUCHER_MAX) {
    ElMessage.warning(`一次最多选 ${BOOKING_VOUCHER_MAX} 张凭证`)
    return
  }
  emit('update:modelValue', [...props.modelValue, item])
  preview.value = null
  voucherNo.value = ''
  voucherDate.value = null
}

function remove(voucherKey: string) {
  emit('update:modelValue', props.modelValue.filter(v => v.voucher_key !== voucherKey))
}
</script>

<style scoped>
.gt-booking-picker { display: grid; gap: 8px; }
.gt-booking-picker__search { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.gt-booking-picker__no { width: 170px; }
.gt-booking-picker__date { width: 170px; }
.gt-booking-picker__hint { color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); }
.gt-booking-picker__block { margin-top: 2px; }
.gt-booking-picker__preview-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.gt-booking-picker__selected-title { margin-top: 4px; font-weight: 600; }
</style>
