<script setup lang="ts">
/**
 * SendListPrefillPanel — E1-3 → E0-3 带入面板
 *
 * 「从 E1-3 带入账户清单」按钮 + 口径选择器 + 预览确认框。
 * 消费 htmlData._prefill（render 下发的 transient 数据）。
 */
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { SendListRow } from './useSendListData'
import {
  AMOUNT_CALIBER_OPTIONS,
  DEFAULT_AMOUNT_CALIBER,
  planSendListPrefill,
  applySendListPrefill,
  type AmountCaliber,
  type E03PrefillRow,
} from './sendListPrefillPlan'

const props = defineProps<{
  rows: SendListRow[]
  prefill: { rows: E03PrefillRow[]; variant?: string; source_caliber_note?: string } | null
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'applied', count: number): void
}>()

const caliber = ref<AmountCaliber>(DEFAULT_AMOUNT_CALIBER)
const loading = ref(false)

const hasPrefill = computed(() => {
  return props.prefill && Array.isArray(props.prefill.rows) && props.prefill.rows.length > 0
})

const prefillCount = computed(() => props.prefill?.rows?.length ?? 0)

async function handlePrefill() {
  if (!props.prefill?.rows?.length) {
    ElMessage.info('上游 E1-3 暂无账户明细')
    return
  }

  loading.value = true
  try {
    const plan = planSendListPrefill(props.rows, props.prefill.rows, caliber.value)

    if (plan.creates.length === 0 && plan.fills.length === 0) {
      ElMessage.info('所有账户已存在且无空位可补，无变化')
      return
    }

    const msg = [
      plan.creates.length ? `新增 ${plan.creates.length} 个账户` : '',
      plan.fills.length ? `补填 ${plan.fills.length} 个账户的空字段` : '',
      plan.conflicts.length ? `${plan.conflicts.length} 处值冲突（已有值不覆盖）` : '',
    ].filter(Boolean).join('；')

    await ElMessageBox.confirm(
      `从 E1-3 带入（口径：${AMOUNT_CALIBER_OPTIONS.find(o => o.value === caliber.value)?.label}）\n\n${msg}\n\n确认带入？`,
      '带入预览',
      { confirmButtonText: '确认带入', cancelButtonText: '取消', type: 'info' },
    )

    const count = applySendListPrefill(props.rows, plan, caliber.value, false)
    ElMessage.success(`已带入 ${count} 项`)
    emit('applied', count)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('带入失败：' + (e?.message || '未知错误'))
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="send-list-prefill-panel">
    <el-tooltip
      :content="prefill?.source_caliber_note || '源模板 E0-3.K 原公式指向 E1-3.K 期末对账单余额'"
      placement="top"
    >
      <el-button
        type="primary"
        size="small"
        :loading="loading"
        :disabled="isReadonly || !hasPrefill"
        @click="handlePrefill"
      >
        从 E1-3 带入账户清单
      </el-button>
    </el-tooltip>

    <el-select
      v-model="caliber"
      size="small"
      style="width: 160px; margin-left: 8px"
      :disabled="isReadonly || !hasPrefill"
    >
      <el-option
        v-for="opt in AMOUNT_CALIBER_OPTIONS"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-select>

    <span v-if="!hasPrefill" class="prefill-hint">
      上游 E1-3 暂无账户明细
    </span>
    <span v-else class="prefill-hint">
      可带入 {{ prefillCount }} 个账户
    </span>
  </div>
</template>

<style scoped>
.send-list-prefill-panel {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
}
.prefill-hint {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}
</style>
