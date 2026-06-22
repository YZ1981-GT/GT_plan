<template>
  <div class="confirmation-notes">
    <el-form label-width="120px" size="small">
      <el-form-item label="函证总体情况">
        <el-input
          :model-value="data.note_general"
          :disabled="readonly"
          type="textarea"
          :rows="3"
          placeholder="本次审计共向XX家单位发出函证..."
          @update:model-value="(v) => $emit('update', 'note_general', v)"
        />
      </el-form-item>
      <el-form-item label="异常情况说明">
        <el-input
          :model-value="data.note_exception"
          :disabled="readonly"
          type="textarea"
          :rows="3"
          placeholder="函证过程中发现以下异常..."
          @update:model-value="(v) => $emit('update', 'note_exception', v)"
        />
      </el-form-item>
      <el-form-item label="未回函处理">
        <el-input
          :model-value="data.note_unreplied"
          :disabled="readonly"
          type="textarea"
          :rows="3"
          placeholder="对未回函单位执行替代程序..."
          @update:model-value="(v) => $emit('update', 'note_unreplied', v)"
        />
      </el-form-item>
      <el-form-item label="替代程序说明">
        <el-input
          :model-value="data.note_alternative"
          :disabled="readonly"
          type="textarea"
          :rows="3"
          placeholder="替代程序包括检查期后收款..."
          @update:model-value="(v) => $emit('update', 'note_alternative', v)"
        />
      </el-form-item>
      <el-form-item label="其他事项">
        <el-input
          :model-value="data.note_other"
          :disabled="readonly"
          type="textarea"
          :rows="3"
          placeholder="其他需要说明的事项..."
          @update:model-value="(v) => $emit('update', 'note_other', v)"
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import type { NotesData } from './confirmationTypes'

defineProps<{
  data: NotesData
  readonly: boolean
}>()

defineEmits<{
  (e: 'update', field: string, value: any): void
}>()
</script>

<style scoped>
.confirmation-notes {
  padding: 8px 0;
}
</style>
