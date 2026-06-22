<template>
  <div class="diff-reconcile-conclusion">
    <!-- 审计说明 -->
    <div class="diff-reconcile-conclusion__section">
      <h4 class="diff-reconcile-conclusion__title">审计说明</h4>
      <el-form label-position="top" size="small">
        <el-form-item label="差异总体情况说明">
          <el-input
            :model-value="auditNote.note_general"
            type="textarea"
            :rows="3"
            :disabled="readonly"
            placeholder="描述差异整体情况、查明程度、主要原因等"
            @input="(val: string) => $emit('update-note', 'note_general', val)"
          />
        </el-form-item>
        <el-form-item label="调整处理说明">
          <el-input
            :model-value="auditNote.note_adjustment"
            type="textarea"
            :rows="2"
            :disabled="readonly"
            placeholder="描述已做调整、未做调整原因等"
            @input="(val: string) => $emit('update-note', 'note_adjustment', val)"
          />
        </el-form-item>
        <el-form-item label="其他事项">
          <el-input
            :model-value="auditNote.note_other"
            type="textarea"
            :rows="2"
            :disabled="readonly"
            placeholder="其他需说明事项"
            @input="(val: string) => $emit('update-note', 'note_other', val)"
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- 审计结论 -->
    <div class="diff-reconcile-conclusion__section">
      <h4 class="diff-reconcile-conclusion__title">审计结论</h4>
      <el-radio-group
        :model-value="conclusion.conclusion_type"
        :disabled="readonly"
        @change="(val: string) => $emit('update-conclusion', 'conclusion_type', val)"
      >
        <el-radio value="A">差异已全部查明并调整</el-radio>
        <el-radio value="B">部分差异待确认</el-radio>
        <el-radio value="C">存在重大未调差异</el-radio>
      </el-radio-group>

      <el-input
        :model-value="conclusion.conclusion_text"
        type="textarea"
        :rows="2"
        :disabled="readonly"
        placeholder="结论说明（可选）"
        style="margin-top: 8px"
        @input="(val: string) => $emit('update-conclusion', 'conclusion_text', val)"
      />

      <!-- 未决事项提示 -->
      <el-alert
        v-if="hasUnresolved"
        title="存在未决事项：部分差异未分类或未填写应对措施，请确认后再出具最终结论"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 8px"
      />
    </div>

    <!-- 重要性配置 -->
    <div class="diff-reconcile-conclusion__section">
      <h4 class="diff-reconcile-conclusion__title">
        重要性配置
        <el-tooltip content="默认取项目实际执行重要性（B15），可手动覆盖" placement="top">
          <el-icon :size="14" style="margin-left:4px"><InfoFilled /></el-icon>
        </el-tooltip>
      </h4>
      <el-form :inline="true" size="small">
        <el-form-item label="实际执行重要性">
          <el-input-number
            :model-value="materialityConfig.performance_materiality"
            :disabled="readonly"
            :controls="false"
            :precision="2"
            :min="0"
            placeholder="从 B15 自动获取"
            style="width: 180px"
            @change="(val: number) => $emit('update-materiality', val)"
          />
        </el-form-item>
        <el-form-item>
          <el-tag v-if="materialityConfig.source === 'auto'" type="primary" size="small">自动取值</el-tag>
          <el-tag v-else-if="materialityConfig.is_overridden" type="warning" size="small">手动覆盖</el-tag>
          <el-tag v-else type="info" size="small">未配置</el-tag>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { InfoFilled } from '@element-plus/icons-vue'
import type { DiffAuditNote, DiffConclusion, MaterialityConfig } from './diffReconcileTypes'

defineProps<{
  auditNote: DiffAuditNote
  conclusion: DiffConclusion
  materialityConfig: MaterialityConfig
  readonly: boolean
  hasUnresolved: boolean
}>()

defineEmits<{
  (e: 'update-note', field: string, value: string): void
  (e: 'update-conclusion', field: string, value: any): void
  (e: 'update-materiality', value: number): void
}>()
</script>

<style scoped>
.diff-reconcile-conclusion__section {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.diff-reconcile-conclusion__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  display: flex;
  align-items: center;
}
</style>
