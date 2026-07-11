<template>
  <div class="h1-tab-title-building">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>审计目标：核对房屋建筑物产权证书与账面记录，确认权利人为被审计单位、账证价值一致，识别抵押/查封等受限情形并披露。</template>
    </el-alert>

    <div class="methodology-context">
      <p>核对房屋建筑物产权证书信息与账面记录，关注：权利人是否为被审计单位、面积/用途是否一致、是否存在抵押/查封限制。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-16 房屋建筑物权属检查 <el-tag size="small" type="info">共 {{ buildingRows.length }} 项</el-tag></span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-16')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="buildingRows" border stripe size="small" max-height="480" class="title-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="name" label="建筑物名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="titleCertNo" label="产权证号" width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.titleCertNo" size="small" @change="onCell(row, 'titleCertNo')" />
            <span v-else>{{ row.titleCertNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="owner" label="证载权利人" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.owner" size="small" @change="onCell(row, 'owner')" />
            <span v-else>{{ row.owner }}</span>
          </template>
        </el-table-column>
        <el-table-column label="权利人为被审计单位" width="130" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isOwnerEntity" size="small" style="width:70px" @change="onCell(row, 'isOwnerEntity')">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else :type="row.isOwnerEntity === 'Y' ? 'success' : 'danger'" size="small">{{ row.isOwnerEntity === 'Y' ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="buildingArea" label="证载面积㎡" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.buildingArea" :controls="false" size="small" @change="onCell(row, 'buildingArea')" />
            <span v-else>{{ row.buildingArea }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCell(row, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="certValue" label="证载价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.certValue" :controls="false" size="small" @change="onCell(row, 'certValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.certValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]" title="差异=账面-证载">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="usage" label="用途" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.usage" size="small" @change="onCell(row, 'usage')" />
            <span v-else>{{ row.usage }}</span>
          </template>
        </el-table-column>
        <el-table-column label="抵押" width="70" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isMortgaged" size="small" style="width:56px" @change="onCell(row, 'isMortgaged')">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else-if="row.isMortgaged === 'Y'" type="warning" size="small">有</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="mortgageAmount" label="抵押金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.isMortgaged === 'Y'" v-model="row.mortgageAmount" :controls="false" size="small" @change="onCell(row, 'mortgageAmount')" />
            <span v-else class="amount-cell">{{ row.isMortgaged === 'Y' ? fmtAmt(row.mortgageAmount) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeBuildingRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>总计: {{ buildingStats.totalChecked }} 项</span>
        <span>权属异常: <b :class="{ 'error-amount': buildingStats.ownerAnomalyCount > 0 }">{{ buildingStats.ownerAnomalyCount }}</b></span>
        <span>有抵押: <b>{{ buildingStats.mortgagedCount }}</b> 项，合计 {{ fmtAmt(buildingStats.mortgageAmountTotal) }}</span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul><li>权利人非被审计单位标红；有抵押标黄需披露受限资产</li><li>差异=账面价值-证载价值</li></ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1TitleCheck, type BuildingRow } from '../../composables/useH1TitleCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const { buildingRows, buildingStats, addBuildingRow, removeBuildingRow, updateBuildingCell } = useH1TitleCheck(
  toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any,
)

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('建筑物名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) addBuildingRow(name)
}
function onCell(row: BuildingRow, field: keyof BuildingRow) { updateBuildingCell(row.rowId, field, (row as any)[field]) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-title-building { padding: 16px; font-size: 13px; }
.obj-alert { margin-bottom: 12px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.title-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
