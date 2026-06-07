<!--
  AttachmentEvidenceForm — 附件上传表单：来源、取得日期、提供方、关键证据 (P0-3.5)
  ==============================================================================
  嵌入附件上传流程，补充证据属性字段。

  Props:
    modelValue: AttachmentEvidenceMetadata (v-model)
  Emits:
    update:modelValue
-->
<template>
  <div class="gt-attachment-evidence-form">
    <el-form
      :model="form"
      label-position="top"
      size="small"
    >
      <el-form-item label="来源">
        <el-select
          v-model="form.source"
          placeholder="请选择来源"
          clearable
          @change="emitUpdate"
        >
          <el-option label="客户提供" value="客户提供" />
          <el-option label="第三方获取" value="第三方获取" />
          <el-option label="自行编制" value="自行编制" />
        </el-select>
      </el-form-item>

      <el-form-item label="取得日期">
        <el-date-picker
          v-model="form.obtained_date"
          type="date"
          placeholder="选择日期"
          value-format="YYYY-MM-DD"
          @change="emitUpdate"
        />
      </el-form-item>

      <el-form-item label="提供方">
        <el-input
          v-model="form.provider"
          placeholder="填写提供方名称"
          @input="emitUpdate"
        />
      </el-form-item>

      <el-form-item>
        <el-checkbox
          v-model="form.is_key_evidence"
          @change="emitUpdate"
        >
          标记为关键证据
        </el-checkbox>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

export interface AttachmentEvidenceMetadata {
  source?: string | null
  obtained_date?: string | null
  provider?: string | null
  is_key_evidence: boolean
}

const props = defineProps<{
  modelValue?: AttachmentEvidenceMetadata
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: AttachmentEvidenceMetadata): void
}>()

const form = reactive<AttachmentEvidenceMetadata>({
  source: props.modelValue?.source ?? null,
  obtained_date: props.modelValue?.obtained_date ?? null,
  provider: props.modelValue?.provider ?? null,
  is_key_evidence: props.modelValue?.is_key_evidence ?? false,
})

watch(
  () => props.modelValue,
  (val) => {
    if (val) {
      form.source = val.source ?? null
      form.obtained_date = val.obtained_date ?? null
      form.provider = val.provider ?? null
      form.is_key_evidence = val.is_key_evidence ?? false
    }
  },
  { deep: true }
)

function emitUpdate() {
  emit('update:modelValue', { ...form })
}
</script>

<style scoped>
.gt-attachment-evidence-form {
  padding: 8px 0;
}

.gt-attachment-evidence-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
</style>
