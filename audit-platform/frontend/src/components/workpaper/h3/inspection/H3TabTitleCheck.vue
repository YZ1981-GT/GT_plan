<template>
  <div class="h3-tab-title-check">
    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 新增产权行</el-button>
    </div>

    <!-- 16列产权核对表 -->
    <el-table :data="rows" border size="small" class="audit-table" :row-class-name="getRowClass">
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column prop="assetName" label="资产名称" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="bookValue" label="账面原值" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="titleCertNo" label="产权证号" min-width="110">
        <template #default="{ row, $index }">
          <el-input v-model="row.titleCertNo" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="certArea" label="证载面积" width="90" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.certArea" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="bookArea" label="账面面积" width="90" align="right">
        <template #default="{ row, $index }">
          <el-input v-model.number="row.bookArea" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="面积差异" width="90" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'text-warn': row.certArea - row.bookArea !== 0 }">
            {{ (row.certArea - row.bookArea).toFixed(2) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="certOwner" label="证载所有人" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.certOwner" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="isAuditEntity" label="是否被审计单位" width="100" align="center">
        <template #default="{ row, $index }">
          <el-select v-model="row.isAuditEntity" size="small" :disabled="isReadonly" @change="onCellChange($index, row)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="mortgage" label="抵押情况" min-width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.mortgage" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="seizure" label="查封情况" min-width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.seizure" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="restriction" label="使用限制" min-width="90">
        <template #default="{ row, $index }">
          <el-input v-model="row.restriction" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="certPurpose" label="证载用途" width="80">
        <template #default="{ row, $index }">
          <el-input v-model="row.certPurpose" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column prop="actualPurpose" label="实际用途" width="80">
        <template #default="{ row, $index }">
          <el-input v-model="row.actualPurpose" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
      <el-table-column label="用途一致" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.certPurpose === row.actualPurpose ? 'success' : 'warning'" size="small">
            {{ row.certPurpose === row.actualPurpose ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="100">
        <template #default="{ row, $index }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange($index, row)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-12')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-12')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabTitleCheck.vue — H3-12 产权核对
 * el-table 16列+产权异常红色+面积差异黄色
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH3TitleCheck } from '../../composables/useH3TitleCheck'
import { useH3FormData } from '../../composables/useH3FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  rows, addRow, updateRow,
} = useH3TitleCheck({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const auditConclusion = ref(getValue('H3-12-conclusion') ?? '')

function onCellChange(index: number, row: any) { updateRow(index, row) }

function getRowClass({ row }: { row: any }): string {
  if (row.isAuditEntity === '否') return 'row-danger'
  if (row.certArea - row.bookArea !== 0) return 'row-warn'
  return ''
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-title-check { padding: 16px; font-size: 13px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.audit-table { font-size: 13px; }
.audit-table :deep(.row-danger) { background-color: #fef0f0 !important; }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-warn { color: var(--el-color-warning); }
.conclusion-card { margin-top: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
</style>
