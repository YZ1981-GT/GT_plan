<template>
  <div class="h5-tab-idle-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：识别闲置油气资产并评估其减值迹象，为 H5-14 减值测算提供依据。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-4" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-4 闲置检查（{{ state.rows.value.length }}项，减值迹象{{ state.impairmentCount.value }}项）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-4')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="check-table">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="assetName" label="资产名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="state.updateCell(row.rowId, 'assetName', $event)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="oilField" label="油田" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.oilField" size="small" @change="state.updateCell(row.rowId, 'oilField', $event)" />
            <span v-else>{{ row.oilField }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCost" label="原值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" @change="state.updateCell(row.rowId, 'originalCost', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="netValue" label="净值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.netValue" :controls="false" size="small" @change="state.updateCell(row.rowId, 'netValue', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="idleReason" label="闲置原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.idleReason" size="small" @change="state.updateCell(row.rowId, 'idleReason', $event)" />
            <span v-else>{{ row.idleReason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="idleStartDate" label="闲置起始日" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.idleStartDate" type="date" value-format="YYYY-MM-DD" size="small"
              @change="state.updateCell(row.rowId, 'idleStartDate', $event)" />
            <span v-else>{{ row.idleStartDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalPlan" label="处置计划" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.disposalPlan" size="small" @change="state.updateCell(row.rowId, 'disposalPlan', $event)" />
            <span v-else>{{ row.disposalPlan }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentSign" label="减值迹象" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-if="!isReadonly" v-model="row.impairmentSign" @change="state.updateCell(row.rowId, 'impairmentSign', $event)" />
            <el-tag v-else :type="row.impairmentSign ? 'danger' : 'info'" size="small">{{ row.impairmentSign ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="核查结论" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="state.updateCell(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="state.removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增闲置资产</el-button>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="闲置检查结论..." :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
        placeholder="填写闲置检查审计结论..." :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>闲置资产需评估是否存在减值迹象</li>
        <li>标记减值迹象的资产将联动H5-14减值测算</li>
        <li>闲置净值合计: {{ fmtAmt(state.totalIdleNetValue.value) }}</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5IdleCheck } from '../../composables/useH5IdleCheck'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const state = useH5IdleCheck({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
})

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增闲置资产', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addRow(value)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h5-tab-idle-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
