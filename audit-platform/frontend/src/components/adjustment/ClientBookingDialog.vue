<template>
  <el-dialog v-model="visible" :title="revokeMode ? '撤销客户已入账标记' : '标记客户已入账'" width="760px"
    append-to-body :close-on-click-modal="false" style="max-width: calc(100vw - 32px)">
    <!-- 与后端一致（adjustment_client_booking.effective_booked_group_ids：所选凭证全部在当前账套才生效），R5.4 -->
    <el-alert v-if="!revokeMode" type="info" :closable="false" show-icon
      title="确认后：当前账套中找到全部所选凭证时，本组 AJE 不再计入试算表调整；账套重导后找不到这些凭证，本组 AJE 自动恢复计入。平台不会自动标记。" />
    <div class="gt-booking-entry">
      <strong>{{ row?.adjustment_no }}</strong>
      <span>{{ row?.description || '无摘要' }}</span>
      <el-tag size="small">{{ row?.audit_phase === 'preliminary' ? '预审提出' : '年审提出' }}</el-tag>
    </div>
    <el-table v-if="row?.line_items?.length" :data="row.line_items" border size="small" max-height="180">
      <el-table-column prop="standard_account_code" label="科目" width="110" />
      <el-table-column prop="account_name" label="科目名称" min-width="150" />
      <el-table-column prop="debit_amount" label="借方" width="120" align="right" />
      <el-table-column prop="credit_amount" label="贷方" width="120" align="right" />
    </el-table>

    <template v-if="revokeMode">
      <el-form label-width="72px" style="margin-top: 14px">
        <el-form-item label="撤销原因" required>
          <el-input v-model="reason" type="textarea" :rows="3" maxlength="1000" show-word-limit
            placeholder="说明客户凭证冲销、选错凭证或其他撤销原因" />
        </el-form-item>
      </el-form>
    </template>
    <template v-else>
      <div class="gt-booking-title">选择客户入账凭证</div>
      <template v-if="candidates.length && !manualPick">
        <el-radio-group v-model="selectedKey" class="gt-booking-candidates">
          <el-radio v-for="candidate in candidates" :key="candidate.voucher_key" :value="candidate.voucher_key" border>
            <div><strong>{{ candidate.label }}</strong> · {{ candidate.summary || '无摘要' }}</div>
            <small>精确匹配 {{ candidate.matches.length }} 行，距调整提出 {{ candidate.distance_days }} 天</small>
          </el-radio>
        </el-radio-group>
        <el-button link type="primary" class="gt-booking-switch" @click="manualPick = true">都不是，按凭证号查找</el-button>
      </template>
      <template v-else>
        <el-alert v-if="!candidates.length" type="info" :closable="false" show-icon class="gt-booking-hint"
          title="当前账套没有自动匹配的候选：按凭证号查找客户入账的凭证，确认分录后加入，可加入多张。" />
        <!-- 原先要粘贴凭证键 JSON，改成按凭证号查当前账套（spec voucher-workflow-linkage-lineage-closure R5.1） -->
        <ClientBookingVoucherPicker v-model="pickedVouchers" :project-id="projectId" :year="year" />
        <el-button v-if="candidates.length" link type="primary" class="gt-booking-switch" @click="manualPick = false">
          返回自动匹配的候选
        </el-button>
      </template>
      <el-input v-model="note" type="textarea" :rows="2" maxlength="1000" show-word-limit
        placeholder="补充说明（可选）" style="margin-top: 10px" />
    </template>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :type="revokeMode ? 'danger' : 'primary'" :loading="saving" @click="submit">
        {{ revokeMode ? '确认撤销' : '确认已入账' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  markAdjustmentClientBooked, revokeAdjustmentClientBooking,
  type AdjustmentBookingCandidate,
} from '@/services/auditPlatformApi'
import { reportAdjustmentError, type HallEntry } from '@/composables/useAdjustmentHallActions'
import ClientBookingVoucherPicker from './ClientBookingVoucherPicker.vue'
import type { PickedBookingVoucher } from './clientBookingVoucher'

const props = defineProps<{ projectId: string; year: number | null }>()
const emit = defineEmits<{ updated: [] }>()
const visible = ref(false)
const saving = ref(false)
const revokeMode = ref(false)
const row = ref<(HallEntry & { audit_phase?: string; client_booking?: any }) | null>(null)
const candidates = ref<AdjustmentBookingCandidate[]>([])
const selectedKey = ref('')
/** 自动匹配候选都不对时，改按凭证号查找 */
const manualPick = ref(false)
const pickedVouchers = ref<PickedBookingVoucher[]>([])
const note = ref('')
const reason = ref('')

function open(nextRow: HallEntry & { audit_phase?: string; client_booking?: any }, nextCandidates: AdjustmentBookingCandidate[] = [], revoke = false) {
  row.value = nextRow
  candidates.value = nextCandidates
  revokeMode.value = revoke
  selectedKey.value = nextCandidates[0]?.voucher_key || ''
  manualPick.value = false
  pickedVouchers.value = []
  note.value = ''
  reason.value = ''
  visible.value = true
}

async function submit() {
  if (!row.value) return
  if (props.year == null) { ElMessage.warning('项目未填审计年度，请先在项目基本信息中填写'); return }
  saving.value = true
  try {
    if (revokeMode.value) {
      if (!reason.value.trim()) { ElMessage.warning('请填写撤销原因'); return }
      await revokeAdjustmentClientBooking(props.projectId, row.value.entry_group_id, {
        year: props.year, reason: reason.value.trim(),
      })
      ElMessage.success('已撤销客户已入账标记，调整额已恢复')
    } else {
      const voucherKeys = candidates.value.length && !manualPick.value
        ? [selectedKey.value].filter(Boolean)
        : pickedVouchers.value.map((voucher) => voucher.voucher_key)
      if (!voucherKeys.length) { ElMessage.warning('请至少选择一张客户入账凭证'); return }
      await markAdjustmentClientBooked(props.projectId, row.value.entry_group_id, {
        year: props.year, voucher_keys: voucherKeys, note: note.value.trim() || undefined,
      })
      ElMessage.success('已标记客户已入账，当前账套不再计入该 AJE')
    }
    visible.value = false
    emit('updated')
  } catch (error) {
    reportAdjustmentError(error, revokeMode.value ? '撤销客户已入账标记' : '标记客户已入账')
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.gt-booking-entry { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.gt-booking-title { margin: 14px 0 8px; font-weight: 600; }
.gt-booking-candidates { display: grid; gap: 8px; width: 100%; }
.gt-booking-candidates :deep(.el-radio) { width: 100%; height: auto; margin: 0; padding: 10px; }
.gt-booking-candidates small { color: var(--gt-color-text-tertiary); }
.gt-booking-switch { margin-top: 6px; }
.gt-booking-hint { margin-bottom: 8px; }
</style>
