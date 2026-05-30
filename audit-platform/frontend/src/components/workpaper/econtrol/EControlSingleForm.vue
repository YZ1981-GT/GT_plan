<!--
  EControlSingleForm.vue — single 子模式：segments 顺序渲染 + 单一结论

  Props: schema / data / readonly
  Emit: field-change / ai-suggest

  从 GtEControlTest.vue shell 抽出（Task 14, 需求 10）
-->

<template>
  <section class="gt-e__single">
    <div
      v-for="(seg, segIdx) in segments"
      :key="seg.id"
      class="gt-e__segment"
    >
      <div class="gt-e__segment-header">
        <h3 class="gt-e__segment-title">{{ seg.title }}</h3>
        <div class="gt-e__segment-actions">
          <el-button
            v-if="!readonly"
            text
            size="small"
            @click="emit('ai-suggest', seg.fields?.[0]?.name || seg.id)"
          >🤖 AI 建议</el-button>
          <el-button
            text
            size="small"
            class="gt-e__attach-btn"
            @click="emit('open-attachment', `seg_${segIdx}`)"
          >📎</el-button>
        </div>
      </div>
      <el-form
        :model="data"
        label-position="top"
        :disabled="readonly"
        class="gt-e__segment-form"
      >
        <el-form-item
          v-for="field in visibleSegmentFields(seg)"
          :key="field.name"
          :label="field.label"
          :required="!!field.required"
        >
          <FieldInput
            :field="field"
            :model-value="data[field.name]"
            :readonly="readonly"
            @update:model-value="(v: any) => { data[field.name] = v; emit('field-change', field.name) }"
          />
          <div v-if="field.hint" class="gt-e__field-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ field.hint }}</span>
          </div>
        </el-form-item>
      </el-form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import FieldInput from './FieldInput.vue'
import { safeEvaluate } from './econtrolHelpers'
import type { EControlTestSchema, SegmentDef, FieldDef } from '../GtEControlTest.types'

const props = defineProps<{
  schema: EControlTestSchema
  data: Record<string, any>
  readonly?: boolean
}>()

const emit = defineEmits<{
  'field-change': [name: string]
  'ai-suggest': [fieldName: string]
  'open-attachment': [rowRef: string]
}>()

const segments = computed<SegmentDef[]>(() => props.schema?.segments ?? [])

function visibleSegmentFields(seg: SegmentDef): FieldDef[] {
  return (seg.fields || []).filter(f => {
    if (!f.conditional) return true
    return safeEvaluate(f.conditional, props.data)
  })
}
</script>

<style scoped>
.gt-e__single {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.gt-e__segment {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-e__segment-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-color-primary);
  border-left: 3px solid var(--el-color-primary);
  padding-left: 8px;
}
.gt-e__segment-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gt-e__segment-header .gt-e__segment-title { margin: 0; }
.gt-e__segment-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.gt-e__attach-btn { font-size: 14px; }
.gt-e__segment-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px 16px;
}
.gt-e__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-e__field-hint .el-icon { color: var(--el-color-info); }
</style>
