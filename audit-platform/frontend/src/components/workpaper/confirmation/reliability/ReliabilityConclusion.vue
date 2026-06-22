<template>
  <div class="reliability-conclusion">
    <el-divider content-position="left">审计说明与结论</el-divider>

    <!-- 审计说明 -->
    <div class="reliability-conclusion__section">
      <h4 class="reliability-conclusion__title">审计说明</h4>
      <el-form label-position="top" size="small">
        <el-form-item label="验证总体情况说明">
          <el-input
            :model-value="auditNote.note_general"
            type="textarea"
            :rows="3"
            :disabled="readonly"
            placeholder="简要描述电子回函可靠性验证的整体执行情况（已验证数量、方法、结果概述）"
            @input="(val: string) => $emit('update-note', 'note_general', val)"
          />
        </el-form-item>
        <el-form-item label="不可靠情况说明">
          <el-input
            :model-value="auditNote.note_unreliable"
            type="textarea"
            :rows="3"
            :disabled="readonly"
            placeholder="对被评定为不可靠的回函，说明原因及后续处理（替代程序/追加证据/调整建议）"
            @input="(val: string) => $emit('update-note', 'note_unreliable', val)"
          />
        </el-form-item>
        <el-form-item label="其他事项">
          <el-input
            :model-value="auditNote.note_other"
            type="textarea"
            :rows="2"
            :disabled="readonly"
            placeholder="如有其他需说明的验证事项"
            @input="(val: string) => $emit('update-note', 'note_other', val)"
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- 审计结论 -->
    <div class="reliability-conclusion__section">
      <h4 class="reliability-conclusion__title">审计结论</h4>
      <el-form label-position="top" size="small">
        <el-form-item label="结论类型">
          <el-radio-group
            :model-value="conclusion.conclusion_type"
            :disabled="readonly"
            @change="(val: string) => $emit('update-conclusion', 'conclusion_type', val)"
          >
            <el-radio value="可靠">可靠——电子回函经验证均可靠，可作为审计证据</el-radio>
            <el-radio value="部分可靠需补充">部分可靠需补充——部分回函需补充程序确认可靠性</el-radio>
            <el-radio value="不可靠">不可靠——电子回函存在不可靠情形，需执行替代程序</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="结论说明">
          <el-input
            :model-value="conclusion.conclusion_text"
            type="textarea"
            :rows="3"
            :disabled="readonly"
            placeholder="对可靠性验证的整体结论进行说明，包括对审计证据充分性和适当性的影响判断"
            @input="(val: string) => $emit('update-conclusion', 'conclusion_text', val)"
          />
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ReliabilityAuditNote, ReliabilityConclusion } from './reliabilityTypes'

defineProps<{
  auditNote: ReliabilityAuditNote
  conclusion: ReliabilityConclusion
  readonly: boolean
}>()

defineEmits<{
  (e: 'update-note', field: string, value: string): void
  (e: 'update-conclusion', field: string, value: any): void
}>()
</script>

<style scoped>
.reliability-conclusion__section {
  margin-bottom: 16px;
}

.reliability-conclusion__title {
  font-size: 14px;
  font-weight: 500;
  margin: 8px 0;
  color: var(--el-text-color-primary);
}

:deep(.el-radio) {
  display: block;
  margin-bottom: 8px;
  line-height: 1.5;
}
</style>
