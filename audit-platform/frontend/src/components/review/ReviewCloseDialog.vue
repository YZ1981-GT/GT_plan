<script setup lang="ts">
/**
 * P1-1.3: 关闭重大复核意见必须填写关闭依据
 *
 * 当 priority=must_fix 时，强制要求填写关闭说明或关联整改证据。
 */
import { ref, computed } from 'vue'
import type { EvidenceRef } from '@/types/evidenceRef'

interface Props {
  modelValue: boolean
  priority: string
  projectId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [payload: { close_reason: string; close_evidence_refs: EvidenceRef[] }]
}>()

const closeReason = ref('')
const closeEvidenceRefs = ref<EvidenceRef[]>([])

const isMajor = computed(() => props.priority === 'must_fix')

const canSubmit = computed(() => {
  if (!isMajor.value) return true
  return closeReason.value.trim().length > 0 || closeEvidenceRefs.value.length > 0
})

function handleConfirm() {
  emit('confirm', {
    close_reason: closeReason.value,
    close_evidence_refs: closeEvidenceRefs.value,
  })
  closeReason.value = ''
  closeEvidenceRefs.value = []
  emit('update:modelValue', false)
}

function handleCancel() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="关闭复核意见"
    width="520px"
    append-to-body
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-alert
      v-if="isMajor"
      type="warning"
      :closable="false"
      show-icon
      class="mb-4"
    >
      该复核意见为重大问题（必须修改），关闭前必须填写关闭依据或关联整改证据。
    </el-alert>

    <el-form label-width="80px">
      <el-form-item label="关闭说明" :required="isMajor">
        <el-input
          v-model="closeReason"
          type="textarea"
          :rows="3"
          placeholder="请填写关闭依据说明"
        />
      </el-form-item>
      <el-form-item label="整改证据">
        <ReviewEvidencePicker
          v-model="closeEvidenceRefs"
          :project-id="projectId"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button
        type="primary"
        :disabled="!canSubmit"
        @click="handleConfirm"
      >
        确认关闭
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts">
import ReviewEvidencePicker from './ReviewEvidencePicker.vue'
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}
</style>
