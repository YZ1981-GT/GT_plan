<template>
  <div class="h1-tab-disposal-check">
    <div class="methodology-context">
      <p>对本期减少固定资产进行检查：核实处置审批流程、验证处置损益计算（收入-净值-处置费用=损益）、联动H10资产处置损益底稿。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-8 减少检查明细（{{ state.rows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" @click="handleSampling" :disabled="isReadonly">🎲 抽凭</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-8')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" max-height="450" class="check-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="name" label="资产名称" min-width="120" fixed />
        <el-table-column prop="originalCost" label="原值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="accDep" label="累计折旧" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.accDep) }}</span></template>
        </el-table-column>
        <el-table-column label="净值" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="净值=原值-折旧">{{ fmtAmt(row.netValue) }}</span></template>
        </el-table-column>
        <el-table-column prop="disposalIncome" label="处置收入" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.disposalIncome" :controls="false" size="small" />
            <span v-else class="amount-cell">{{ fmtAmt(row.disposalIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalCost" label="处置费用" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.disposalCost" :controls="false" size="small" />
            <span v-else class="amount-cell">{{ fmtAmt(row.disposalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置损益" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.gainLoss < 0 }]" title="损益=收入-净值-费用">
              {{ fmtAmt(row.gainLoss) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="disposalType" label="处置方式" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.disposalType" size="small" style="width:70px">
              <el-option label="出售" value="sale" />
              <el-option label="报废" value="scrap" />
              <el-option label="损毁" value="damage" />
              <el-option label="捐赠" value="donate" />
            </el-select>
            <span v-else>{{ row.disposalType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="approvalDoc" label="审批文件" width="100" />
        <el-table-column prop="checkResult" label="结果" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.checkResult === 'OK' ? 'success' : 'danger'" size="small">{{ row.checkResult || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>处置收入合计: <b class="amount-cell">{{ fmtAmt(state.incomeTotal.value) }}</b></span>
        <span>处置损益合计: <b class="amount-cell">{{ fmtAmt(state.gainLossTotal.value) }}</b></span>
        <GtIndexChip value="H10" @click="navigateToH10" />
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="publishDisposalCompleted" :disabled="isReadonly">📤 发布联动H10</el-button>
            <el-button size="small" type="primary" link @click="handleAiGenerate('disposal-note')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>处置损益 = 收入 - 净值 - 处置费用（公式自动）</li>
        <li>处置结果联动H10资产处置损益底稿(EventBus)</li>
        <li>关注报废资产是否有残值回收</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1601 固定资产-减少）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :account-codes="['1601']"
        dialog-mode
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1DisposalCheck } from '../../composables/useH1DisposalCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const showSamplingDialog = ref(false)

const state = useH1DisposalCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, {
  onPublishEvent(event: string, payload: any) {
    // 6.8 — 发布 h1:disposal-completed 事件
    if (event === 'h1:disposal-completed') {
      console.log('[H1-8] publish h1:disposal-completed', payload)
    }
  },
})

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增处置项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addRow(name)
}

function handleSampling() {
  showSamplingDialog.value = true
}

/** 抽凭引擎完成后回调：将样本行填入检查表 */
function onSampleFilled(samples: any[]) {
  showSamplingDialog.value = false
  if (!samples?.length) return
  for (const s of samples) {
    state.addRow(s.summary || s.description || '处置项')
    const lastRow = state.rows.value[state.rows.value.length - 1]
    if (lastRow) {
      lastRow.originalCost = s.amount ?? 0
      lastRow.disposalIncome = s.disposalIncome ?? 0
    }
  }
}

/** 发布处置完成事件并联动H10 */
function publishDisposalCompleted() {
  state.publishDisposalCompleted?.()
}

function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function navigateToH10() { emit('navigate-sheet', 'H10') }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-disposal-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
