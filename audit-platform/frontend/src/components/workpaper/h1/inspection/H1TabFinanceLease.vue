<template>
  <div class="h1-tab-finance-lease">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>审计目标：验证以融资租赁方式租出的固定资产分类正确（CAS21五项判断满足任一即为融资租赁），利息分摊与本金回收计算准确。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar" style="display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
      <GtIndexChip value="wp:H1-20" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ financeRows.length }} 项</el-tag>
    </div>

    <div class="methodology-context">
      <p>检查以融资租赁方式租出的固定资产：核实CAS21五项判断条件中任一满足即为融资租赁，验证利息分摊正确性。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-20 融资租出检查 <el-tag size="small" type="info">共 {{ financeRows.length }} 项</el-tag></span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-20')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="financeRows" border stripe size="small" max-height="420">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="onCell(row, 'assetName')" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessee" label="承租方" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessee" size="small" @change="onCell(row, 'lessee')" />
            <span v-else>{{ row.lessee }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCost" label="原值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" @change="onCell(row, 'originalCost')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="n in 5" :key="n" :label="`判断${n}`" width="70" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row[`classResult${n}`]" size="small" style="width:56px" @change="onCell(row, `classResult${n}` as any)">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ row[`classResult${n}`] }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类判断" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="classify(row) === '融资' ? 'success' : 'warning'" size="small">{{ classify(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="minLeasePayment" label="最低租赁付款额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.minLeasePayment" :controls="false" size="small" @change="onCell(row, 'minLeasePayment')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.minLeasePayment) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="presentValue" label="现值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.presentValue" :controls="false" size="small" @change="onCell(row, 'presentValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.presentValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocRate" label="分摊利率%" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocRate" :controls="false" size="small" @change="onCell(row, 'allocRate')" />
            <span v-else>{{ row.allocRate }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="periodInterest" label="各期利息" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.periodInterest" :controls="false" size="small" @change="onCell(row, 'periodInterest')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.periodInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('20', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 五项分类判断标准 -->
      <div class="classification-criteria">
        <h4>CAS21融资租赁五项判断条件（满足任一即为融资）</h4>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="①所有权转移">租赁期届满时，资产所有权转移给承租人</el-descriptions-item>
          <el-descriptions-item label="②购买选择权">承租人有购买租赁资产的选择权(价格远低于公允)</el-descriptions-item>
          <el-descriptions-item label="③租期≥寿命75%">租赁期占资产使用寿命的大部分</el-descriptions-item>
          <el-descriptions-item label="④PV≥FV 90%">最低租赁付款额现值≥资产公允价值的几乎全部</el-descriptions-item>
          <el-descriptions-item label="⑤专用性资产">租赁资产性质特殊，不做重大改造只有承租人能使用</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNoteText" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：融资租赁分类判断依据、利息分摊与现值测算核对情况。" @change="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写融资租出检查审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>五项判断满足任一 → 融资租赁；均不满足 → 经营租赁</li>
        <li>融资租出不在本科目核算(转应收融资租赁款)，关注分类正确性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1LeaseCheck, type FinanceLeaseRow } from '../../composables/useH1LeaseCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const auditNoteText = ref('')
const NOTE_KEY = 'H1-20-audit-note'
const CONCLUSION_KEY = 'H1-20-audit-conclusion'
function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) conclusion.value = c.remark
})
const { financeRows, addFinanceRow, removeRow, updateFinanceCell } = useH1LeaseCheck(
  toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any,
)

function classify(row: FinanceLeaseRow): string {
  const anyYes = [row.classResult1, row.classResult2, row.classResult3, row.classResult4, row.classResult5].some((v) => v === 'Y')
  return anyYes ? '融资' : '经营'
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name != null) {
    addFinanceRow()
    const last = financeRows.value[financeRows.value.length - 1]
    if (last) updateFinanceCell(last.rowId, 'assetName', name)
  }
}
function onCell(row: FinanceLeaseRow, field: keyof FinanceLeaseRow) { updateFinanceCell(row.rowId, field, (row as any)[field]) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-finance-lease { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.classification-criteria { margin-top: 16px; }
.classification-criteria h4 { font-size: var(--wp-font-size, 13px); margin-bottom: 8px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
