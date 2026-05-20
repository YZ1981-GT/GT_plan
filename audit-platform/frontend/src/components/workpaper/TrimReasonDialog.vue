<template>
  <el-dialog
    :model-value="visible"
    title="📋 选择裁剪理由"
    width="480px"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="handleVisibleChange"
  >
    <el-alert
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    >
      <template #default>
        请选择将程序标记为"不适用"的理由。选择"其他"时需输入至少 5 个字符的说明。
      </template>
    </el-alert>

    <el-radio-group v-model="selectedReason" class="gt-trim-reason-group">
      <el-radio
        v-for="option in reasonOptions"
        :key="option.code"
        :value="option.code"
        class="gt-trim-reason-radio"
      >
        {{ option.label }}
      </el-radio>
    </el-radio-group>

    <!-- "其他"理由文本输入 -->
    <div v-if="selectedReason === 'other'" class="gt-trim-reason-text">
      <el-input
        v-model="reasonText"
        type="textarea"
        :rows="3"
        placeholder="请输入裁剪理由（至少 5 个字符）"
        maxlength="200"
        show-word-limit
      />
      <span v-if="reasonText.length > 0 && reasonText.length < 5" class="gt-trim-reason-error">
        理由文本至少需要 5 个字符
      </span>
    </div>

    <!-- 未选择理由提示 -->
    <div v-if="showNoReasonTip" class="gt-trim-reason-error" style="margin-top: 8px">
      请选择裁剪理由
    </div>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button
        type="primary"
        :disabled="!isValid"
        @click="handleConfirm"
      >
        确认裁剪
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * TrimReasonDialog — 裁剪理由选择弹窗
 *
 * 4 个预设理由 + "其他"自定义文本（≥5 字符校验）
 * emit confirm({ reason_code, reason_text }) / cancel
 *
 * @see requirements.md Requirement 2.1, 2.2, 2.3, 2.5
 */
import { ref, computed, watch } from 'vue'

interface Props {
  visible: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'confirm', payload: { reason_code: string; reason_text: string | null }): void
  (e: 'cancel'): void
}>()

const reasonOptions = [
  { code: 'no_related_business', label: '无相关业务' },
  { code: 'low_risk_assessment', label: '风险评估为低' },
  { code: 'control_test_effective', label: '控制测试有效' },
  { code: 'other', label: '其他（需填写说明）' },
]

const selectedReason = ref<string>('')
const reasonText = ref('')
const showNoReasonTip = ref(false)

/** 表单校验 */
const isValid = computed(() => {
  if (!selectedReason.value) return false
  if (selectedReason.value === 'other' && reasonText.value.length < 5) return false
  return true
})

/** 重置表单 */
function resetForm() {
  selectedReason.value = ''
  reasonText.value = ''
  showNoReasonTip.value = false
}

// 弹窗打开时重置
watch(() => props.visible, (val) => {
  if (val) resetForm()
})

function handleVisibleChange(val: boolean) {
  emit('update:visible', val)
  if (!val) emit('cancel')
}

function handleConfirm() {
  if (!selectedReason.value) {
    showNoReasonTip.value = true
    return
  }
  if (!isValid.value) return

  emit('confirm', {
    reason_code: selectedReason.value,
    reason_text: selectedReason.value === 'other' ? reasonText.value : null,
  })
  emit('update:visible', false)
}

function handleCancel() {
  emit('cancel')
  emit('update:visible', false)
}
</script>

<style scoped>
.gt-trim-reason-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.gt-trim-reason-radio {
  margin-right: 0;
  height: auto;
  line-height: 1.6;
}
.gt-trim-reason-text {
  margin-top: 8px;
  padding-left: 24px;
}
.gt-trim-reason-error {
  color: var(--el-color-danger, #f56c6c);
  font-size: 12px;
  margin-top: 4px;
}
</style>
