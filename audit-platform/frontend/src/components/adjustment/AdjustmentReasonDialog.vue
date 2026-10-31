<template>
  <el-dialog v-model="visible" :title="mode === 'reject' ? '驳回调整分录' : '撤回复核'" width="560px" append-to-body :close-on-click-modal="false">
    <p class="gt-adj-reason-lead">{{ lead }}</p>
    <div class="gt-adj-reason-nos">{{ entryNos }}</div>
    <el-radio-group v-if="mode === 'reject' && entries.length > 1" v-model="perEntry" size="small" class="gt-adj-reason-mode">
      <el-radio-button :value="false">统一原因</el-radio-button>
      <el-radio-button :value="true">逐笔填写</el-radio-button>
    </el-radio-group>
    <el-input v-model="reason" type="textarea" :rows="3" maxlength="1000" show-word-limit :placeholder="placeholder" />
    <div v-if="perEntry" class="gt-adj-reason-items">
      <div v-for="e in entries" :key="e.entry_group_id" class="gt-adj-reason-item">
        <span class="gt-adj-reason-no">{{ e.adjustment_no || '分录' }}</span>
        <el-input v-model="reasons[e.entry_group_id]" size="small" maxlength="1000" placeholder="此笔原因（留空用上面的统一原因）" />
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button :type="mode === 'reject' ? 'danger' : 'primary'" :loading="busy" :disabled="!canConfirm" @click="confirm">
        {{ mode === 'reject' ? `驳回 ${entries.length} 笔` : `撤回 ${entries.length} 笔` }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * 驳回 / 撤回复核的原因弹窗（spec adjustment-hall-entry-review-closure 需求 4.3 / 5.2）。
 * 驳回原因必填，多笔可逐笔填写；撤回复核原因可选。弹窗本身即确认步骤，实际请求由大厅传入的 handler 执行，
 * handler 返回 true（至少一笔成功）才关闭。
 */
import { computed, ref } from 'vue'

type ReasonMode = 'reject' | 'revoke'
interface ReasonEntry {
  entry_group_id: string
  adjustment_no?: string | null
}
type Handler = (payload: { reason: string; reasons?: Record<string, string> }) => Promise<boolean>

const visible = ref(false)
const mode = ref<ReasonMode>('reject')
const entries = ref<ReasonEntry[]>([])
const reason = ref('')
const reasons = ref<Record<string, string>>({})
const perEntry = ref(false)
const busy = ref(false)
let handler: Handler | null = null

const lead = computed(() => (mode.value === 'reject'
  ? '驳回后分录退回编制人修改，编制人会收到通知（含驳回原因）。'
  : '撤回复核后分录回到草稿，试算表审定数、报表与附注随之回退；编制人与受影响底稿的负责人会收到通知。'))
const placeholder = computed(() => (mode.value === 'reject' ? '驳回原因（必填），如：坏账计提比例与账龄分析不一致' : '撤回原因（可选）'))
const entryNos = computed(() => entries.value.map((e) => e.adjustment_no || '分录').join('、'))
const canConfirm = computed(() => {
  if (busy.value || !entries.value.length) return false
  if (mode.value === 'revoke') return true
  const common = reason.value.trim()
  if (!perEntry.value) return !!common
  return entries.value.every((e) => (reasons.value[e.entry_group_id] || '').trim() || common)
})

function open(nextMode: ReasonMode, rows: ReasonEntry[], onConfirm: Handler) {
  mode.value = nextMode
  entries.value = rows.map((r) => ({ entry_group_id: r.entry_group_id, adjustment_no: r.adjustment_no }))
  reason.value = ''
  reasons.value = Object.fromEntries(rows.map((r) => [r.entry_group_id, '']))
  perEntry.value = false
  handler = onConfirm
  visible.value = true
}

async function confirm() {
  if (!handler || !canConfirm.value) return
  busy.value = true
  try {
    const picked = perEntry.value
      ? Object.fromEntries(Object.entries(reasons.value).map(([k, v]) => [k, v.trim()]).filter(([, v]) => v))
      : undefined
    if (await handler({ reason: reason.value.trim(), reasons: picked })) visible.value = false
  } finally {
    busy.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.gt-adj-reason-lead { margin: 0 0 6px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-regular); line-height: 1.6; }
.gt-adj-reason-nos { margin-bottom: 10px; font-size: var(--gt-font-size-xs); color: var(--gt-color-primary); word-break: break-all; }
.gt-adj-reason-mode { margin-bottom: 10px; }
.gt-adj-reason-items { margin-top: 10px; max-height: 240px; overflow-y: auto; }
.gt-adj-reason-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.gt-adj-reason-no { flex-shrink: 0; min-width: 80px; font-size: var(--gt-font-size-sm); font-weight: 600; }
</style>
