<template>
  <div class="fraud-risk-checklist">
    <!-- 顶部编制说明（说明①） -->
    <div class="fraud-risk-checklist__top-note">
      <el-alert type="info" :closable="false" show-icon>
        {{ GUIDANCE_NOTES_D08.top_note }}
      </el-alert>
    </div>

    <!-- 工具栏 -->
    <div v-if="!readonly" class="fraud-risk-checklist__toolbar">
      <el-button size="small" type="primary" @click="handleAddItem">
        <el-icon><Plus /></el-icon> 新增自定义条目
      </el-button>
      <el-button size="small" @click="$emit('import')">
        <el-icon><Upload /></el-icon> 导入
      </el-button>
      <el-button size="small" @click="$emit('export')">
        <el-icon><Download /></el-icon> 导出
      </el-button>
    </div>

    <!-- 检查清单列表 -->
    <div class="fraud-risk-checklist__list">
      <div
        v-for="item in items"
        :key="item._row_id"
        class="fraud-risk-checklist__card"
        :class="{
          'fraud-risk-checklist__card--highlighted': isHighlighted(item),
          'fraud-risk-checklist__card--warning': needsCountermeasure(item),
        }"
      >
        <!-- 序号 + 描述 -->
        <div class="fraud-risk-checklist__card-header">
          <span class="fraud-risk-checklist__seq">{{ item.seq }}.</span>
          <span
            v-if="readonly || item._preset"
            class="fraud-risk-checklist__desc"
          >
            {{ item.description }}
          </span>
          <el-input
            v-else
            v-model="item.description"
            size="small"
            placeholder="请输入自定义风险迹象描述"
            @change="handleUpdate(item._row_id!, 'description', item.description)"
          />
          <!-- tooltip 举例 -->
          <el-tooltip
            v-if="item.tooltip_key && ITEM_TOOLTIPS_D08[item.tooltip_key]"
            :content="ITEM_TOOLTIPS_D08[item.tooltip_key]"
            placement="right"
            :raw-content="true"
            effect="light"
            :popper-style="{ whiteSpace: 'pre-line', maxWidth: '420px' }"
          >
            <el-icon class="fraud-risk-checklist__tooltip-icon"><InfoFilled /></el-icon>
          </el-tooltip>
          <!-- 删除按钮（仅自定义条目） -->
          <el-button
            v-if="!readonly && !item._preset"
            size="small"
            type="danger"
            text
            @click="handleDelete(item._row_id!)"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>

        <!-- 三字段行：是否存在 + 索引 + 应对措施 -->
        <div class="fraud-risk-checklist__card-fields">
          <!-- 是否存在 -->
          <div class="fraud-risk-checklist__field">
            <span class="fraud-risk-checklist__field-label">是否存在</span>
            <el-select
              v-if="!readonly"
              :model-value="item.is_exist"
              size="small"
              placeholder="请选择"
              style="width: 90px"
              @change="(val: string) => handleUpdate(item._row_id!, 'is_exist', val)"
            >
              <el-option
                v-for="opt in FRAUD_RISK_EXIST_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
            <span v-else class="fraud-risk-checklist__field-value">
              {{ item.is_exist || '—' }}
            </span>
          </div>

          <!-- 相关索引 -->
          <div class="fraud-risk-checklist__field">
            <el-tooltip
              :content="GUIDANCE_NOTES_D08.source_ref_tooltip"
              placement="top"
              effect="light"
            >
              <span class="fraud-risk-checklist__field-label fraud-risk-checklist__field-label--tip">
                相关索引
              </span>
            </el-tooltip>
            <el-input
              v-if="!readonly"
              :model-value="item.source_ref"
              size="small"
              placeholder="如 D0-1/D0-4"
              style="width: 120px"
              @change="(val: string) => handleUpdate(item._row_id!, 'source_ref', val)"
            />
            <span
              v-else
              class="fraud-risk-checklist__field-value fraud-risk-checklist__ref-link"
              @click="item.source_ref && $emit('jump-ref', item.source_ref)"
            >
              {{ item.source_ref || '—' }}
            </span>
          </div>

          <!-- 应对措施 -->
          <div class="fraud-risk-checklist__field fraud-risk-checklist__field--wide">
            <span class="fraud-risk-checklist__field-label">应对措施</span>
            <el-input
              v-if="!readonly"
              :model-value="item.countermeasure"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              :placeholder="GUIDANCE_NOTES_D08.countermeasure_placeholder"
              @change="(val: string) => handleUpdate(item._row_id!, 'countermeasure', val)"
            />
            <span v-else class="fraud-risk-checklist__field-value">
              {{ item.countermeasure || '—' }}
            </span>
            <!-- 是=是条件提示（说明④） -->
            <el-tooltip
              v-if="isHighlighted(item) && needsCountermeasure(item)"
              :content="GUIDANCE_NOTES_D08.exist_yes_warning"
              placement="bottom"
              effect="light"
            >
              <el-icon class="fraud-risk-checklist__warning-icon"><Warning /></el-icon>
            </el-tooltip>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Upload, Download, Delete, InfoFilled, Warning } from '@element-plus/icons-vue'
import type { FraudRiskRow } from './fraudRiskTypes'
import { ITEM_TOOLTIPS_D08, GUIDANCE_NOTES_D08 } from './fraudRiskPresets'
import { FRAUD_RISK_EXIST_OPTIONS } from './fraudRiskEnums'

const props = defineProps<{
  items: FraudRiskRow[]
  readonly: boolean
  isHighlighted: (row: FraudRiskRow) => boolean
  needsCountermeasure: (row: FraudRiskRow) => boolean
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete', rowId: string): void
  (e: 'update', rowId: string, field: string, value: any): void
  (e: 'import'): void
  (e: 'export'): void
  (e: 'jump-ref', ref: string): void
}>()

function handleAddItem() {
  emit('add')
}

function handleDelete(rowId: string) {
  emit('delete', rowId)
}

function handleUpdate(rowId: string, field: string, value: any) {
  emit('update', rowId, field, value)
}
</script>

<style scoped>
.fraud-risk-checklist__top-note {
  margin-bottom: 12px;
}

.fraud-risk-checklist__toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.fraud-risk-checklist__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fraud-risk-checklist__card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 14px;
  transition: border-color 0.2s, background-color 0.2s;
}

.fraud-risk-checklist__card--highlighted {
  border-color: var(--el-color-warning-light-3);
  background-color: var(--el-color-warning-light-9);
}

.fraud-risk-checklist__card--warning {
  border-color: var(--el-color-warning);
  background-color: #fdf6ec;
}

.fraud-risk-checklist__card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.fraud-risk-checklist__seq {
  font-weight: 600;
  min-width: 26px;
  color: var(--el-text-color-secondary);
}

.fraud-risk-checklist__desc {
  flex: 1;
  line-height: 1.5;
}

.fraud-risk-checklist__tooltip-icon {
  color: var(--el-color-primary);
  cursor: help;
  font-size: 16px;
}

.fraud-risk-checklist__card-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-start;
  padding-left: 34px;
}

.fraud-risk-checklist__field {
  display: flex;
  align-items: center;
  gap: 6px;
}

.fraud-risk-checklist__field--wide {
  flex: 1;
  min-width: 200px;
}

.fraud-risk-checklist__field-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.fraud-risk-checklist__field-label--tip {
  text-decoration: underline dotted;
  cursor: help;
}

.fraud-risk-checklist__field-value {
  font-size: 13px;
}

.fraud-risk-checklist__ref-link {
  color: var(--el-color-primary);
  cursor: pointer;
  text-decoration: underline;
}

.fraud-risk-checklist__ref-link:hover {
  color: var(--el-color-primary-dark-2);
}

.fraud-risk-checklist__warning-icon {
  color: var(--el-color-warning);
  font-size: 16px;
  margin-left: 4px;
}
</style>
