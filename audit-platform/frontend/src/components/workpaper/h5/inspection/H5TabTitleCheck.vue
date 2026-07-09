<template>
  <div class="h5-tab-title-check">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-16 权属检查（采矿权）— 到期预警{{ state.expiringCount.value }}项</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-16')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>已抵押: {{ state.pledgedCount.value }}项，抵押金额合计: {{ fmtAmt(state.totalPledgeAmount.value) }}</span>
      </div>

      <el-table :data="state.rows.value" border stripe size="small" class="title-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="assetName" label="资产名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="state.updateCell(row.rowId, 'assetName', $event)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="miningLicenseNo" label="证照号" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.miningLicenseNo" size="small" @change="state.updateCell(row.rowId, 'miningLicenseNo', $event)" />
            <span v-else>{{ row.miningLicenseNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="licenseType" label="类型" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.licenseType" size="small" @change="state.updateCell(row.rowId, 'licenseType', $event)">
              <el-option label="采矿权" value="采矿权" /><el-option label="探矿权" value="探矿权" />
            </el-select>
            <span v-else>{{ row.licenseType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="validTo" label="有效期止" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.validTo" type="date" value-format="YYYY-MM-DD" size="small" @change="state.updateCell(row.rowId, 'validTo', $event)" />
            <span v-else :class="{ 'expiry-warn': row.expiryWarning }">{{ row.validTo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期预警" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.expiryWarning" type="warning" size="small">⚠ <1年</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="ownerEntity" label="权属主体" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.ownerEntity" size="small" @change="state.updateCell(row.rowId, 'ownerEntity', $event)" />
            <span v-else>{{ row.ownerEntity }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pledgeStatus" label="抵押状态" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.pledgeStatus" size="small" @change="state.updateCell(row.rowId, 'pledgeStatus', $event)">
              <el-option label="无" value="无" /><el-option label="已抵押" value="已抵押" />
            </el-select>
            <el-tag v-else :type="row.pledgeStatus === '已抵押' ? 'danger' : 'info'" size="small">{{ row.pledgeStatus }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="pledgeAmount" label="抵押金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.pledgeAmount" :controls="false" size="small" @change="state.updateCell(row.rowId, 'pledgeAmount', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.pledgeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="state.updateCell(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="state.removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>
    <div class="action-bar" v-if="!isReadonly"><el-button size="small" @click="handleAddRow">+ 新增权属项</el-button></div>
    <el-card shadow="never" class="note-card"><template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveNote(state.auditNote)" /></el-card>
    <details class="compile-hint"><summary>编制提示</summary><ul>
      <li>采矿权到期日&lt;1年自动黄色预警</li><li>已抵押资产需披露并关注持续经营影响</li><li>权属核验需查阅原始证照</li></ul></details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5TitleCheck } from '../../composables/useH5TitleCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const state = useH5TitleCheck({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: () => {} })

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增权属项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addRow(value)
}
function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-title-check { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; } .section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; } .summary-row { margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.title-table { font-size: 13px; } .amount-cell { font-variant-numeric: tabular-nums; }
.expiry-warn { color: var(--el-color-warning); font-weight: 600; }
.action-bar { margin: 12px 0; } .note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; } .compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
