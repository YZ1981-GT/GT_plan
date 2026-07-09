<template>
  <div class="h2-tab-adjudication">
    <!-- 审定表主区域 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>在建工程审定表（科目1604）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" circle @click="openReview('H2-1')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="displayRows" border stripe size="small" class="adj-table"
        :row-class-name="rowClassName">
        <el-table-column prop="name" label="项目名称" min-width="140" fixed />
        <!-- 期初数 -->
        <el-table-column label="期初数" align="center">
          <el-table-column prop="beginUnadjusted" label="未审数" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.beginUnadjusted"
                :controls="false" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'beginUnadjusted', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.beginUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="beginAdjustment" label="账项调整" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.beginAdjustment"
                :controls="false" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'beginAdjustment', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.beginAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定=未审+账项调整">{{ fmtAmt(row.beginAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 期末数 -->
        <el-table-column label="期末数" align="center">
          <el-table-column prop="endUnadjusted" label="未审数" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.endUnadjusted"
                :controls="false" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'endUnadjusted', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.endUnadjusted) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="endAdjustment" label="账项调整" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.isEditable && !isReadonly" v-model="row.endAdjustment"
                :controls="false" size="small" class="amt-input"
                @change="onCellChange(row.rowId, 'endAdjustment', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.endAdjustment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定数" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定=未审+账项调整">{{ fmtAmt(row.endAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 本期比较 -->
        <el-table-column label="本期变动" align="center">
          <el-table-column label="未审变动" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末未审-期初未审">{{ fmtAmt(row.unadjustedChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="未审变动率" min-width="90" align="right">
            <template #default="{ row }">
              <span>{{ row.unadjustedChangeRate != null ? row.unadjustedChangeRate.toFixed(1) + '%' : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定变动" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末审定-期初审定">{{ fmtAmt(row.auditedChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定变动率" min-width="90" align="right">
            <template #default="{ row }">
              <span>{{ row.auditedChangeRate != null ? row.auditedChangeRate.toFixed(1) + '%' : '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 操作列 -->
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button v-if="row.isEditable && !row.isTotal" size="small" type="danger" link
              @click="handleRemoveRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新增工程行 -->
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增工程项目</el-button>
      </div>
    </el-card>

    <!-- TB取数 + 差异核对 -->
    <el-card shadow="never" class="block-card" v-if="state.tbRow.value.tbAudited !== 0 || !state.diffRow.value.isZero">
      <template #header>
        <div class="section-header"><span>TB差异核对</span></div>
      </template>
      <div class="tb-compare">
        <span>审定合计: {{ fmtAmt(state.totalRow.value.endAudited) }}</span>
        <span style="margin:0 12px">|</span>
        <span>TB审定(1604): {{ fmtAmt(state.tbRow.value.tbAudited) }}</span>
        <span style="margin:0 12px">|</span>
        <span :class="{ 'error-amount': !state.diffRow.value.isZero }">
          差异: {{ fmtAmt(state.diffRow.value.amount) }}
        </span>
      </div>
    </el-card>

    <!-- 三角勾稽校验（含转固） -->
    <el-card shadow="never" class="block-card" v-if="state.triangleErrors.value.length > 0">
      <template #header>
        <div class="section-header">
          <span>三角勾稽校验异常（含转固扣减）</span>
          <GtIndexChip value="H2-4" label="→ H2-4分析表" />
        </div>
      </template>
      <el-table :data="state.triangleErrors.value" size="small" border>
        <el-table-column prop="name" label="工程项目" min-width="150" />
        <el-table-column label="差额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="error-amount">{{ fmtAmt(row.diff) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 交叉验证警告 -->
    <el-alert v-if="Math.abs(state.detailDiff.value) > 0.01" type="warning" :closable="false" show-icon
      style="margin-bottom:12px">
      <template #title>
        交叉验证：审定合计 vs H2-2明细合计差异 {{ fmtAmt(state.detailDiff.value) }}
      </template>
    </el-alert>
    <el-alert v-if="Math.abs(state.transferDiff.value) > 0.01" type="warning" :closable="false" show-icon
      style="margin-bottom:12px">
      <template #title>
        交叉验证：H2-2转固合计 vs H2-5转固合计差异 {{ fmtAmt(state.transferDiff.value) }}
      </template>
    </el-alert>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..." :disabled="isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handlePublish" :loading="publishing">
        确认审定 → 回写TB
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>科目1604在建工程（资产类/借方），期末=期初+借方-贷方</li>
        <li>审定数=未审数+账项调整，未审数从TB自动取入(只读)</li>
        <li>三角勾稽(含转固)：期末=期初+增加-减少-转固，在H2-2上实施</li>
        <li>审定数合计与H2-2明细合计/H2-5转固合计交叉验证</li>
        <li>"确认审定"将回写trial_balance并发布EventBus事件</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabAdjudication.vue — H2-1 审定表
 * el-table 12列 + 三角勾稽校验红色高亮(含转固)
 * Spec: Task 4.2 | Requirements: 2.1-2.12, 14.6
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Adjudication } from '../../composables/useH2Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const publishing = ref(false)

const state = useH2Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
})

const displayRows = computed(() => {
  const rows = [...state.detailRows.value, state.totalRow.value]
  return rows
})

function rowClassName({ row }: any) {
  if (row.isTotal) return 'total-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: number) {
  state.updateCell(rowId, field, value ?? 0)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增工程', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addProjectRow(value)
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowId: string) {
  state.removeProjectRow(rowId)
}

async function handlePublish() {
  publishing.value = true
  try {
    await state.publishAdjudicated()
  } finally {
    publishing.value = false
  }
}

function handleAiGenerate(section: string) {
  console.log('AI generate:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-adjudication { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.adj-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.tb-compare { font-size: 13px; padding: 8px 0; }
.add-row-bar { margin-top: 12px; }
.audit-note-card { margin-bottom: 12px; }
.action-bar { margin-top: 16px; text-align: right; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background-color: var(--el-fill-color-light) !important; }
</style>
