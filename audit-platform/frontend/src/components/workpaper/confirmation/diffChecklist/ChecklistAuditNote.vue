<template>
  <div class="checklist-audit-note">
    <el-divider content-position="left">审计说明与结论</el-divider>

    <!-- 全局审计说明 -->
    <div class="checklist-audit-note__field">
      <label class="checklist-audit-note__label">总体审计说明</label>
      <el-input
        v-if="!readonly"
        :model-value="globalNote"
        type="textarea"
        :rows="3"
        placeholder="记录函证差异检查的总体情况说明"
        @change="(val: string) => $emit('update-global-note', val)"
      />
      <div v-else class="checklist-audit-note__text">{{ globalNote || '—' }}</div>
    </div>

    <!-- 审计结论 -->
    <div class="checklist-audit-note__field">
      <label class="checklist-audit-note__label">审计结论</label>
      <el-radio-group
        v-if="!readonly"
        :model-value="conclusion.conclusion_type"
        @change="(val: string) => $emit('update-conclusion', 'conclusion_type', val)"
      >
        <el-radio value="A">A. 所有差异均已查明并调节相符</el-radio>
        <el-radio value="B">B. 部分差异已调节，剩余差异不重大</el-radio>
        <el-radio value="C">C. 存在无法调节的重大差异</el-radio>
      </el-radio-group>
      <div v-else class="checklist-audit-note__text">
        {{ conclusionText }}
      </div>
    </div>

    <!-- 结论说明 -->
    <div v-if="conclusion.conclusion_type" class="checklist-audit-note__field">
      <label class="checklist-audit-note__label">结论说明</label>
      <el-input
        v-if="!readonly"
        :model-value="conclusion.conclusion_text"
        type="textarea"
        :rows="2"
        placeholder="补充结论说明"
        @change="(val: string) => $emit('update-conclusion', 'conclusion_text', val)"
      />
      <div v-else class="checklist-audit-note__text">{{ conclusion.conclusion_text || '—' }}</div>
    </div>

    <!-- 重要性配置 -->
    <div class="checklist-audit-note__field">
      <label class="checklist-audit-note__label">
        实际执行重要性
        <el-tooltip content="差异绝对值超过此金额的项目将标记为"超重要性"红色警示。留空=不启用自动检测。" placement="top">
          <el-icon :size="12"><InfoFilled /></el-icon>
        </el-tooltip>
      </label>
      <el-input-number
        v-if="!readonly"
        :model-value="materialityConfig.performance_materiality"
        :controls="false"
        :precision="2"
        :min="0"
        size="small"
        placeholder="输入重要性金额"
        style="width: 200px"
        @change="(val: number) => $emit('update-materiality', val)"
      />
      <span v-else class="checklist-audit-note__amount">
        {{ materialityConfig.performance_materiality != null
          ? formatAmount(materialityConfig.performance_materiality)
          : '未配置' }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import type { ChecklistConclusion, ChecklistMaterialityConfig } from './diffChecklistTypes'

const props = defineProps<{
  globalNote: string
  conclusion: ChecklistConclusion
  materialityConfig: ChecklistMaterialityConfig
  readonly: boolean
}>()

defineEmits<{
  (e: 'update-global-note', value: string): void
  (e: 'update-conclusion', field: string, value: any): void
  (e: 'update-materiality', value: number): void
}>()

const conclusionText = computed(() => {
  const map: Record<string, string> = {
    A: 'A. 所有差异均已查明并调节相符',
    B: 'B. 部分差异已调节，剩余差异不重大',
    C: 'C. 存在无法调节的重大差异',
  }
  return map[props.conclusion.conclusion_type ?? ''] ?? '未选择'
})

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.checklist-audit-note {
  margin-top: 12px;
}

.checklist-audit-note__field {
  margin-bottom: 12px;
}

.checklist-audit-note__label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
  color: var(--el-text-color-primary);
}

.checklist-audit-note__text {
  font-size: 13px;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.checklist-audit-note__amount {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
</style>
