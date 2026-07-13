<template>
  <div class="h1-tab-title-vehicle">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>审计目标：核对运输设备行驶证/登记证与账面记录，确认所有人为被审计单位、年检有效，识别抵押/查封受限情形。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar" style="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <GtIndexChip value="wp:H1-17" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ vehicleRows.length }} 项</el-tag>
    </div>

    <div class="methodology-context">
      <p>核对运输设备行驶证/登记证信息，关注：所有人是否为被审计单位、是否年检有效、是否存在抵押查封。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-17 运输设备权属检查 <el-tag size="small" type="info">共 {{ vehicleRows.length }} 项</el-tag></span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-17')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="vehicleRows" border stripe size="small" max-height="480" class="title-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="name" label="车辆名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="plateNo" label="车牌号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.plateNo" size="small" @change="onCell(row, 'plateNo')" />
            <span v-else>{{ row.plateNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="vinNo" label="车架号" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.vinNo" size="small" @change="onCell(row, 'vinNo')" />
            <span v-else>{{ row.vinNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="owner" label="证载所有人" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.owner" size="small" @change="onCell(row, 'owner')" />
            <span v-else>{{ row.owner }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所有人为被审计单位" width="130" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isOwnerEntity" size="small" style="width:70px" @change="onCell(row, 'isOwnerEntity')">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else :type="row.isOwnerEntity === 'Y' ? 'success' : 'danger'" size="small">{{ row.isOwnerEntity === 'Y' ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCell(row, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="inspectionStatus" label="年检状态" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.inspectionStatus" size="small" style="width:88px" @change="onCell(row, 'inspectionStatus')">
              <el-option label="已通过" value="已通过" />
              <el-option label="未通过" value="未通过" />
              <el-option label="已过期" value="已过期" />
            </el-select>
            <el-tag v-else :type="row.inspectionStatus === '已通过' ? 'success' : 'warning'" size="small">{{ row.inspectionStatus }}</el-tag>
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
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeVehicleRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>总计: {{ vehicleStats.totalChecked }} 项</span>
        <span>所有人异常: <b :class="{ 'error-amount': vehicleStats.ownerAnomalyCount > 0 }">{{ vehicleStats.ownerAnomalyCount }}</b></span>
        <span>年检过期/未通过: <b :class="{ 'error-amount': expiredCount > 0 }">{{ expiredCount }}</b></span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNoteText" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：行驶证/登记证核对、所有人及年检状态、抵押受限情形。" @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写运输设备权属检查审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul><li>所有人非被审计单位标红；年检过期标黄</li><li>抵押车辆需确认受限资产披露</li></ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1TitleCheck, type VehicleRow } from '../../composables/useH1TitleCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const auditNoteText = ref('')
const NOTE_KEY = 'H1-17-audit-note'
const CONCLUSION_KEY = 'H1-17-audit-conclusion'
function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) conclusion.value = c.remark
})
const { vehicleRows, vehicleStats, addVehicleRow, removeVehicleRow, updateVehicleCell } = useH1TitleCheck(
  toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any,
)

const expiredCount = computed(() =>
  vehicleRows.value.filter((r) => r.inspectionStatus === '已过期' || r.inspectionStatus === '未通过').length,
)

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('车辆名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) addVehicleRow(name)
}
function onCell(row: VehicleRow, field: keyof VehicleRow) { updateVehicleCell(row.rowId, field, (row as any)[field]) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-title-vehicle { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.title-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
