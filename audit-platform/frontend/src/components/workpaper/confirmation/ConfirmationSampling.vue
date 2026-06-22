<template>
  <div class="confirmation-sampling">
    <el-form label-width="100px" size="small">
      <el-form-item label="抽样方式">
        <el-select
          :model-value="data.sampling_method"
          :disabled="readonly"
          placeholder="请选择抽样方式"
          clearable
          @update:model-value="(v) => $emit('update', 'sampling_method', v)"
        >
          <el-option
            v-for="item in (dictData.sampling_method || [])"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="抽样范围">
        <el-input
          :model-value="data.sampling_scope"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="描述抽样的总体范围"
          @update:model-value="(v) => $emit('update', 'sampling_scope', v)"
        />
      </el-form-item>
      <el-form-item label="抽样标准">
        <el-input
          :model-value="data.sampling_criteria"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="描述选取样本的标准和依据"
          @update:model-value="(v) => $emit('update', 'sampling_criteria', v)"
        />
      </el-form-item>
      <el-form-item label="样本量">
        <el-input
          :model-value="data.sampling_size"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="说明确定的样本量及计算依据"
          @update:model-value="(v) => $emit('update', 'sampling_size', v)"
        />
      </el-form-item>
      <el-form-item label="抽样结果">
        <el-input
          :model-value="data.sampling_result"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="描述抽样执行的结果"
          @update:model-value="(v) => $emit('update', 'sampling_result', v)"
        />
      </el-form-item>
      <el-form-item label="抽样结论">
        <el-input
          :model-value="data.sampling_conclusion"
          :disabled="readonly"
          type="textarea"
          :rows="2"
          placeholder="基于抽样结果得出的审计结论"
          @update:model-value="(v) => $emit('update', 'sampling_conclusion', v)"
        />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import type { SamplingData } from './confirmationTypes'

defineProps<{
  data: SamplingData
  readonly: boolean
  dictData: Record<string, any[]>
}>()

defineEmits<{
  (e: 'update', field: string, value: any): void
}>()
</script>

<style scoped>
.confirmation-sampling {
  padding: 8px 0;
}
</style>
