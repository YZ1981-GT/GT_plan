<template>
  <div class="confirmation-conclusion">
    <el-form label-width="100px" size="small">
      <el-form-item label="审计结论">
        <el-radio-group
          :model-value="data.conclusion_type"
          :disabled="readonly"
          @update:model-value="(v) => $emit('update', 'conclusion_type', v)"
        >
          <el-radio value="A">A. 函证结果支持账面记录</el-radio>
          <el-radio value="B">B. 函证结果发现差异但经调查可接受</el-radio>
          <el-radio value="C">C. 函证结果存在重大差异需进一步审计</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item
        v-show="data.conclusion_type === 'B' || data.conclusion_type === 'C'"
        label="结论说明"
      >
        <el-input
          :model-value="data.conclusion_text"
          :disabled="readonly"
          type="textarea"
          :rows="3"
          placeholder="请说明差异原因及后续审计措施"
          @update:model-value="(v) => $emit('update', 'conclusion_text', v)"
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import type { ConclusionData } from './confirmationTypes'

defineProps<{
  data: ConclusionData
  readonly: boolean
}>()

defineEmits<{
  (e: 'update', field: string, value: any): void
}>()
</script>

<style scoped>
.confirmation-conclusion {
  padding: 8px 0;
}
.confirmation-conclusion .el-radio {
  display: block;
  margin-bottom: 8px;
}
</style>
