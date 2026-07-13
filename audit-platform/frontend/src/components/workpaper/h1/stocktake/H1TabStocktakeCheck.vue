<template>
  <div class="h1-tab-stocktake-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px"
      title="审计目标：通过实物监盘核对固定资产账实相符（铭牌/数量/状态），识别盘盈盘亏与减值/报废迹象，证实资产存在性与状况。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar" style="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <GtIndexChip value="wp:H1-10" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ state.checkRows.value.length }} 项</el-tag>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-10 盘点检查表（{{ state.checkRows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-10')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.checkRows.value" border stripe size="small" max-height="500" class="check-table">
        <el-table-column type="index" label="序" width="40" fixed />
        <el-table-column prop="name" label="资产名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetNo" label="编号" width="90" />
        <el-table-column prop="location" label="地点" width="90" />
        <el-table-column prop="bookCost" label="账面原值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="bookNetValue" label="账面净值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookNetValue) }}</span></template>
        </el-table-column>
        <el-table-column prop="actualStatus" label="实物状态" width="80">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.actualStatus" size="small" style="width:65px">
              <el-option label="在用" value="在用" />
              <el-option label="闲置" value="闲置" />
              <el-option label="报废" value="报废" />
            </el-select>
            <span v-else>{{ row.actualStatus }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="nameplateCheck" label="铭牌核对" width="80">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.nameplateCheck" size="small" style="width:65px">
              <el-option label="一致" value="一致" />
              <el-option label="不一致" value="不一致" />
            </el-select>
            <span v-else>{{ row.nameplateCheck }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="quantityCheck" label="数量核对" width="80">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.quantityCheck" size="small" style="width:65px">
              <el-option label="一致" value="一致" />
              <el-option label="不一致" value="不一致" />
            </el-select>
            <span v-else>{{ row.quantityCheck }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="盘点结果" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.result === '账实相符' ? 'success' : 'danger'" size="small">{{ row.result || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="diffAmount" label="差异金额" width="100" align="right">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': row.diffAmount !== 0 }]">{{ fmtAmt(row.diffAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="diffReason" label="差异原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.diffReason" size="small" />
            <span v-else>{{ row.diffReason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="checker" label="盘点人" width="70" />
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeCheckRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>账实相符: <b>{{ state.statistics.value.matchCount }}</b></span>
        <span>盘盈: <b>{{ state.statistics.value.surplusCount }}</b></span>
        <span>盘亏: <b :class="{ 'error-amount': state.statistics.value.deficitCount > 0 }">{{ state.statistics.value.deficitCount }}</b></span>
        <span>相符率: <b>{{ state.statistics.value.matchRate.toFixed(1) }}%</b></span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card" style="margin-top:12px">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNoteText" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：监盘执行情况、账实差异及原因、盘盈盘亏处理跟进。" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card" style="margin-top:12px">
      <template #header><span>审计结论</span></template>
      <el-input v-model="auditConclusionText" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写盘点检查审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>盘点结果：账实相符/盘盈/盘亏 三选一</li>
        <li>盘亏需附差异原因和建议处理方式</li>
        <li>完成后汇入H1-11监盘小结</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1Stocktake } from '../../composables/useH1Stocktake'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const auditNoteText = ref('')
const auditConclusionText = ref('')
const NOTE_KEY = 'H1-10-audit-note'
const CONCLUSION_KEY = 'H1-10-audit-conclusion'
function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, auditConclusionText.value) }
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) auditConclusionText.value = c.remark
})
const state = useH1Stocktake(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增盘点项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addCheckRow(name)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
