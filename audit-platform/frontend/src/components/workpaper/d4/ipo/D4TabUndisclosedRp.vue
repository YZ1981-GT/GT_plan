<script setup lang="ts">
/**
 * D4TabUndisclosedRp — D4-27 未披露关联方识别
 *
 * 穿透分析 + 红色高亮关联结论
 * Requirements: 14.7
 */
import { inject, toRef, type Ref } from 'vue'
import { useD4Ipo, type UndisclosedRpRow } from '../../composables/useD4Ipo'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const { undisclosedRpRows, addRow, removeRow } = useD4Ipo({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function getRowClass({ row }: { row: UndisclosedRpRow }): string {
  if (row.conclusion === 'related') return 'row-red'
  if (row.conclusion === 'attention') return 'row-yellow'
  return ''
}
</script>

<template>
  <div class="d4-tab-undisclosed-rp">
    <div class="mb-3 flex justify-between">
      <span class="text-sm text-gray-500">未披露关联方识别（穿透股东/实控人关系）</span>
      <el-button type="primary" size="small" :disabled="isReadonly" @click="addRow('D4-27')">
        + 添加对象
      </el-button>
    </div>

    <el-table :data="undisclosedRpRows" border stripe max-height="450" :row-class-name="getRowClass">
      <el-table-column prop="customer" label="客户名称" min-width="130" />
      <el-table-column prop="shareholders" label="主要股东" min-width="120" />
      <el-table-column prop="controller" label="实际控制人" min-width="110" />
      <el-table-column prop="relation" label="与公司关系" min-width="130" />
      <el-table-column label="结论" width="90" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.conclusion === 'related' ? 'danger' : row.conclusion === 'attention' ? 'warning' : 'info'"
            size="small"
          >
            {{ row.conclusion === 'related' ? '关联' : row.conclusion === 'attention' ? '关注' : row.conclusion === 'unrelated' ? '无关' : '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100" />
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeRow('D4-27', row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="mt-4">
      <div class="flex items-center justify-between mb-1">
        <label class="text-sm font-medium text-gray-600">审计说明</label>
        <el-button v-if="openReviewDialog" size="small" text @click="openReviewDialog('D4-27-note')">💬</el-button>
      </div>
      <el-input type="textarea" :rows="3" :disabled="isReadonly" placeholder="请输入未披露关联方分析结论..." />
    </div>
  </div>
</template>

<style scoped>
.d4-tab-undisclosed-rp { padding: 16px; }
.mt-4 { margin-top: 16px; }
.mb-3 { margin-bottom: 12px; }
.mb-1 { margin-bottom: 4px; }
:deep(.row-red) { background-color: #fef0f0 !important; }
:deep(.row-yellow) { background-color: #fdf6ec !important; }
</style>
