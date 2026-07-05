<template>
  <div class="c24-anomaly-account">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C24-4 异常账户测试：提取分录中所有操作用户，统计编制/过账/审核数量，与人员清单核对，识别异常账户。</p>
    </div>

    <!-- 异常账户结果表 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">异常账户分析</span>
      </div>
      <el-alert v-if="!hasData" type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        尚未导入分录数据，请先导入会计分录。
      </el-alert>

      <el-table v-if="rows.length > 0" :data="rows" border size="small" class="c24-table" max-height="500">
        <el-table-column label="操作用户" prop="user" width="100" />
        <el-table-column label="用户岗位" min-width="100">
          <template #default="{ row, $index }">
            <el-input :model-value="row.role" :disabled="isReadonly" size="small" placeholder="岗位" @input="onRowChange($index, 'role', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="编制数" width="80" align="center">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录统计">{{ row.prepareCount }}</span></template>
        </el-table-column>
        <el-table-column label="过账数" width="80" align="center">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录统计">{{ row.postCount }}</span></template>
        </el-table-column>
        <el-table-column label="审核数" width="80" align="center">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录统计">{{ row.reviewCount }}</span></template>
        </el-table-column>
        <el-table-column label="在清单中" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.inList ? 'success' : 'warning'" size="small">{{ row.inList ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="110" align="center">
          <template #default="{ row, $index }">
            <el-select :model-value="row.abnormal" :disabled="isReadonly" size="small" placeholder="请判断" @change="onRowChange($index, 'abnormal', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="160">
          <template #default="{ row, $index }">
            <el-input :model-value="row.note" :disabled="isReadonly" size="small" placeholder="异常说明" @input="onRowChange($index, 'note', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row, $index }">
            <el-select :model-value="row.conclusion" :disabled="isReadonly" size="small" placeholder="结论" @change="onRowChange($index, 'conclusion', $event)">
              <el-option label="正常" value="正常" />
              <el-option label="异常-已解释" value="异常-已解释" />
              <el-option label="异常-错报" value="异常-错报" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="120">
          <template #default="{ row, $index }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input
              v-else
              :model-value="row.indexRef || ''"
              :disabled="isReadonly"
              size="small"
              placeholder="索引号"
              @input="onRowChange($index, 'indexRef', $event)"
            />
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 测试结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-4-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="请填写异常账户测试结论"
        @input="$emit('update:conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

export interface AccountRow {
  user: string
  role: string
  prepareCount: number
  postCount: number
  reviewCount: number
  inList: boolean
  abnormal: string
  note: string
  conclusion: string
  indexRef?: string
}

defineProps<{
  rows: AccountRow[]
  hasData: boolean
  conclusion: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:conclusion', val: string): void
  (e: 'update:row', index: number, field: string, value: string): void
  (e: 'ai-suggest', fieldId: string): void
}>()

function onRowChange(index: number, field: string, value: string) {
  emit('update:row', index, field, value)
}
</script>

<style scoped>
.c24-anomaly-account { font-size: 13px; }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: 13px; color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: 13px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
</style>
