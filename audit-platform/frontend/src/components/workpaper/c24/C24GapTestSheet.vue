<template>
  <div class="c24-gap-test">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C24-3 完整性测试 — 跳号测试：按凭证类型分组，检测同组凭证号是否存在跳号缺口，识别完整性风险。</p>
    </div>

    <!-- 跳号结果 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">跳号检测结果</span>
      </div>
      <el-alert v-if="gaps.length === 0 && hasData" type="success" :closable="false" show-icon style="margin-bottom: 12px;">
        未检测到凭证号跳号，连续性良好。
      </el-alert>
      <el-alert v-if="!hasData" type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        尚未导入分录数据，请先导入会计分录。
      </el-alert>

      <el-table v-if="gaps.length > 0" :data="gaps" border size="small" class="c24-table">
        <el-table-column label="凭证类型" prop="type" width="100" />
        <el-table-column label="缺号起始" min-width="120">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：detectGaps.start">{{ row.start }}</span>
          </template>
        </el-table-column>
        <el-table-column label="缺号终止" min-width="120">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：detectGaps.end">{{ row.end }}</span>
          </template>
        </el-table-column>
        <el-table-column label="缺号数量" width="100" align="center">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：detectGaps.count">{{ row.count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="120" align="center">
          <template #default="{ row, $index }">
            <el-select :model-value="gapNotes[$index]?.abnormal || ''" :disabled="isReadonly" size="small" placeholder="请判断" @change="onGapFieldChange($index, 'abnormal', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待核实" value="待核实" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="200">
          <template #default="{ row, $index }">
            <el-input :model-value="gapNotes[$index]?.note || ''" :disabled="isReadonly" size="small" placeholder="跳号原因说明" @input="onGapFieldChange($index, 'note', $event)" />
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 测试结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-3-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="请填写跳号测试结论"
        @input="$emit('update:conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import type { GapResult } from '@/composables/useC24AnalyticsEngine'

export interface GapNote { abnormal: string; note: string }

defineProps<{
  gaps: GapResult[]
  gapNotes: GapNote[]
  hasData: boolean
  conclusion: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:conclusion', val: string): void
  (e: 'update:gap-note', index: number, field: 'abnormal' | 'note', value: string): void
  (e: 'ai-suggest', fieldId: string): void
}>()

function onGapFieldChange(index: number, field: 'abnormal' | 'note', value: string) {
  emit('update:gap-note', index, field, value)
}
</script>

<style scoped>
.c24-gap-test { font-size: var(--wp-font-size, 13px); }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
</style>
