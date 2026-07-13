<template>
  <div class="h5-tab-operating-lease">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：检查油气资产经营租出的租金收益率与合同合规性，评价租金定价的公允性。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-18" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.operatingRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-18 经营租出（年租金合计 {{ fmtAmt(state.totalAnnualRent.value) }}，平均收益率 {{ state.avgReturnRate.value.toFixed(2) }}%）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-18')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="state.operatingRows.value" border stripe size="small" class="lease-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="assetName" label="资产名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="state.updateOperatingCell(row.rowId, 'assetName', $event)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessee" label="承租方" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessee" size="small" @change="state.updateOperatingCell(row.rowId, 'lessee', $event)" />
            <span v-else>{{ row.lessee }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseTerm" label="租期(月)" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.leaseTerm" :controls="false" size="small" @change="state.updateOperatingCell(row.rowId, 'leaseTerm', $event ?? 0)" />
            <span v-else>{{ row.leaseTerm }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualRent" label="年租金" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.annualRent" :controls="false" size="small" @change="state.updateOperatingCell(row.rowId, 'annualRent', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.annualRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="netValue" label="资产净值" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.netValue" :controls="false" size="small" @change="state.updateOperatingCell(row.rowId, 'netValue', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收益率(%)" min-width="90" align="right">
          <template #default="{ row }"><span class="formula-cell" title="=年租金/净值×100">{{ row.returnRate.toFixed(2) }}%</span></template>
        </el-table-column>
        <el-table-column prop="contractNo" label="合同号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" @change="state.updateOperatingCell(row.rowId, 'contractNo', $event)" />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="state.updateOperatingCell(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="state.removeOperatingRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
    <div class="action-bar" v-if="!isReadonly"><el-button size="small" @click="handleAddRow">+ 新增经营租出</el-button></div>
    <el-card shadow="never" class="note-card"><template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" /></el-card>
    <el-card shadow="never" class="note-card"><template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" placeholder="填写经营租出审计结论..." :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" /></el-card>
    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>收益率=年租金÷资产净值×100%</li><li>收益率过低可能暗示资产减值或租金不公允</li><li>经营租出不转移所有权，资产仍计入本科目</li></ul></details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Lease } from '../../composables/useH5Lease'
import { useH5FormData } from '../../composables/useH5FormData'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5Lease({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: (itemId: string, value: any) => formData.setResponse(itemId, value) })

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增经营租出', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addOperatingRow(value)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-operating-lease { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; } .section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; } .lease-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.action-bar { margin: 12px 0; } .note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; } .compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
