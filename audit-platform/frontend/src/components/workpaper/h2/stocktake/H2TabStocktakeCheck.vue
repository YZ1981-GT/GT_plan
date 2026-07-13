<template>
  <div class="h2-tab-stocktake-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：通过现场盘点核实在建工程的存在性与形象进度，核对账面进度与实际施工状态的差异，识别停工/异常项目并关注其减值迹象。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.checkRows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- 盘点检查表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>盘点检查表（H2-13）</span>
          <div class="section-header-actions">
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" circle @click="openReview('H2-13')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.checkRows.value" border stripe size="small" class="check-table"
        :row-class-name="checkRowClass">
        <el-table-column prop="name" label="工程项目" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCellChange(row.rowId, 'name', row.name)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="siteLocation" label="现场位置" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.siteLocation" size="small"
              @change="onCellChange(row.rowId, 'siteLocation', row.siteLocation)" />
            <span v-else>{{ row.siteLocation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="visibleProgress" label="形象进度(%)" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.visibleProgress" :controls="false"
              :min="0" :max="100" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'visibleProgress', $event)" />
            <span v-else>{{ row.visibleProgress ?? '-' }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="constructionStatus" label="施工状态" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.constructionStatus" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'constructionStatus', $event)">
              <el-option label="施工中" value="施工中" />
              <el-option label="停工" value="停工" />
              <el-option label="完工" value="完工" />
            </el-select>
            <span v-else>{{ row.constructionStatus || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="workers" label="施工人员" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.workers" size="small"
              @change="onCellChange(row.rowId, 'workers', row.workers)" />
            <span v-else>{{ row.workers || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="materialStorage" label="材料堆存" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.materialStorage" size="small"
              @change="onCellChange(row.rowId, 'materialStorage', row.materialStorage)" />
            <span v-else>{{ row.materialStorage || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="equipmentCondition" label="设备状况" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.equipmentCondition" size="small"
              @change="onCellChange(row.rowId, 'equipmentCondition', row.equipmentCondition)" />
            <span v-else>{{ row.equipmentCondition || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="qualityAppearance" label="质量观感" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.qualityAppearance" size="small"
              @change="onCellChange(row.rowId, 'qualityAppearance', row.qualityAppearance)" />
            <span v-else>{{ row.qualityAppearance || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="progressDifference" label="与账面进度差异" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.progressDifference" size="small"
              @change="onCellChange(row.rowId, 'progressDifference', row.progressDifference)" />
            <span v-else>{{ row.progressDifference || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="photos" label="照片附件" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.photos" size="small"
              @change="onCellChange(row.rowId, 'photos', row.photos)" />
            <span v-else>{{ row.photos || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="auditConclusion" label="审计结论" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.auditConclusion" size="small"
              @change="onCellChange(row.rowId, 'auditConclusion', row.auditConclusion)" />
            <span v-else>{{ row.auditConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增检查项</el-button>
      </div>
    </el-card>

    <!-- 停工汇总 -->
    <el-alert v-if="state.checkStats.value.stopped > 0" type="warning" :closable="false" show-icon
      style="margin-bottom:12px">
      <template #title>
        发现 {{ state.checkStats.value.stopped }} 个停工项目（{{ state.stoppedProjectNames.value.join('、') }}），
        需关注减值迹象(→H2-15)
      </template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述盘点范围/方法、形象进度与账面核对情况、停工与异常项目的处理。" :disabled="isReadonly"
        @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：如现场盘点结果与账面一致、工程真实存在，未见异常；或说明停工/进度异常事项及其对减值的影响。" :disabled="isReadonly"
        @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>停工项目红色高亮，需重点关注减值迹象</li>
        <li>形象进度应与账面进度核对，差异较大需说明</li>
        <li>照片附件对应审计工作底稿附件编号</li>
        <li>可通过"导入导出"批量处理盘点数据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabStocktakeCheck.vue — H2-13 盘点检查
 * 盘点检查表 + 停工红色高亮 + 导入导出
 * Spec: Task 4.16 | Requirements: 11.2, 11.5
 */
import { ref, inject, toRef, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Stocktake } from '../../composables/useH2Stocktake'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'check',
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isReadonly = computed(() => props.isReadonly)

// H2-13 审计说明/结论：本 sheet 独立 item_id（plan/check/summary 共用同一 composable，
// 其 NOTE_KEY 为共享单键，故此处用本地键避免串写）。
const NOTE_KEY = 'H2-13-audit-note'
const CONCLUSION_KEY = 'H2-13-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  saveResponse(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function checkRowClass({ row }: any) {
  if (row.constructionStatus === '停工') return 'stop-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCheckRow(rowId, field, value)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增检查项', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addCheckRow(value)
  } catch { /* cancelled */ }
}

function handleRemove(rowId: string) {
  state.removeCheckRow(rowId)
}

function handleExportCmd(cmd: string) {
  console.log('export command:', cmd)
}


function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.h2-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.stop-row) { background-color: #fef0f0 !important; }
</style>
