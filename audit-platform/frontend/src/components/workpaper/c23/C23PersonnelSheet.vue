<template>
  <div class="c23-personnel-sheet">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C23-1 会计人员清单完整性测试：维护经授权的会计人员清单，后续在 C23-2 中核对样本分录人员是否在此清单内。</p>
    </div>

    <!-- 数据来源描述 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">数据来源描述</span>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="sourceDesc"
        :disabled="isReadonly"
        placeholder="请说明会计人员授权清单数据来源（如：从被审计单位 ERP 导出经授权的用户列表）"
        @input="$emit('update:source-desc', $event)"
      />
    </section>

    <!-- 授权人员清单 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">授权人员清单</span>
        <el-button
          v-if="!isReadonly"
          type="primary"
          size="small"
          @click="$emit('add-person')"
        >
          + 新增人员
        </el-button>
      </div>

      <el-table
        :data="persons"
        border
        size="small"
        class="c23-table"
        empty-text="暂无授权人员，请点击「新增人员」添加"
      >
        <el-table-column label="序号" width="60" align="center">
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="姓名" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.name"
              :disabled="isReadonly"
              size="small"
              placeholder="姓名"
              @input="$emit('update-person', $index, 'name', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="岗位/权限" min-width="140">
          <template #default="{ row, $index }">
            <el-select
              :model-value="row.role"
              :disabled="isReadonly"
              size="small"
              placeholder="选择权限"
              @change="$emit('update-person', $index, 'role', $event)"
            >
              <el-option label="创建" value="创建" />
              <el-option label="授权" value="授权" />
              <el-option label="记录" value="记录" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              :model-value="row.note"
              :disabled="isReadonly"
              size="small"
              placeholder="备注"
              @input="$emit('update-person', $index, 'note', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button type="danger" size="small" link @click="$emit('remove-person', $index)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 测试结论 -->
    <section class="c23-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button
          v-if="!isReadonly"
          size="small"
          @click="$emit('ai-suggest')"
        >
          AI 辅助
        </el-button>
      </div>
      <el-select
        :model-value="conclusion1Select"
        :disabled="isReadonly"
        size="default"
        placeholder="请选择测试结论"
        style="width: 100%; margin-bottom: 8px;"
        @change="onConclusionSelect"
      >
        <el-option label="未发现偏差" value="未发现偏差" />
        <el-option label="发现偏差-影响不重大" value="发现偏差-影响不重大" />
        <el-option label="发现偏差-影响重大" value="发现偏差-影响重大" />
      </el-select>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion1Detail"
        :disabled="isReadonly"
        placeholder="补充说明（可选）"
        @input="onConclusionDetailInput"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * C23PersonnelSheet — C23-1 会计人员清单完整性测试表
 *
 * 子组件：授权人员清单维护 + 数据来源 + 测试结论
 */
import { computed } from 'vue'

const props = defineProps<{
  wpId: string
  projectId?: string
  persons: Array<{ seq: number; name: string; role: string; note: string }>
  sourceDesc: string
  conclusion1: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:source-desc', val: string): void
  (e: 'update:conclusion1', val: string): void
  (e: 'add-person'): void
  (e: 'remove-person', index: number): void
  (e: 'update-person', index: number, field: 'name' | 'role' | 'note', value: string): void
  (e: 'ai-suggest'): void
}>()

// 结论解析：格式 "选项||补充说明"
const CONCLUSION_OPTIONS = ['未发现偏差', '发现偏差-影响不重大', '发现偏差-影响重大']
const conclusion1Select = computed(() => {
  const raw = props.conclusion1 || ''
  const selectPart = raw.split('||')[0] || ''
  return CONCLUSION_OPTIONS.includes(selectPart) ? selectPart : ''
})
const conclusion1Detail = computed(() => {
  const raw = props.conclusion1 || ''
  const parts = raw.split('||')
  if (parts.length > 1) return parts.slice(1).join('||')
  if (!CONCLUSION_OPTIONS.includes(raw)) return raw
  return ''
})

function onConclusionSelect(val: string) {
  const detail = conclusion1Detail.value
  emit('update:conclusion1', detail ? `${val}||${detail}` : val)
}

function onConclusionDetailInput(val: string) {
  const sel = conclusion1Select.value
  emit('update:conclusion1', sel ? `${sel}||${val}` : val)
}
</script>

<style scoped>
.c23-personnel-sheet {
  font-size: 13px;
}

.methodology-context {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  margin-bottom: 16px;
  background: #fffbf0;
  border-radius: 4px;
}

.methodology-bar {
  width: 3px;
  min-height: 20px;
  align-self: stretch;
  background: #e6a23c;
  border-radius: 2px;
  flex-shrink: 0;
}

.methodology-context p {
  margin: 0;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.c23-section {
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.c23-table {
  font-size: 13px;
}

.c23-table :deep(.el-table__header th) {
  font-size: 13px;
  background: #f5f7fa;
}

.c23-table :deep(.el-table__body td) {
  font-size: 13px;
}
</style>
