<template>
  <div class="h5-tab-addition-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：检查本期油气资产增加(勘探资本化)是否满足 CAS27 资本化条件，费用化处理是否恰当。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-7" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-7 增加检查（勘探资本化）— {{ state.rows.value.length }}项 合计{{ fmtAmt(state.totalAmount.value) }}</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-7')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>资本化项目: {{ state.capitalizedCount.value }}项，金额: {{ fmtAmt(state.capitalizedAmount.value) }}</span>
      </div>

      <el-table :data="state.rows.value" border stripe size="small" class="check-table" max-height="500">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="assetName" label="资产名称" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="state.updateCell(row.rowId, 'assetName', $event)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="oilField" label="油田" min-width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.oilField" size="small" @change="state.updateCell(row.rowId, 'oilField', $event)" />
            <span v-else>{{ row.oilField }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" @change="state.updateCell(row.rowId, 'amount', $event ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="explorationStage" label="勘探阶段" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.explorationStage" size="small" @change="state.updateCell(row.rowId, 'explorationStage', $event)">
              <el-option label="勘探" value="勘探" /><el-option label="评价" value="评价" /><el-option label="开发" value="开发" />
            </el-select>
            <span v-else>{{ row.explorationStage }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isCapitalized" label="资本化" width="70" align="center">
          <template #default="{ row }">
            <el-switch v-if="!isReadonly" v-model="row.isCapitalized" @change="state.updateCell(row.rowId, 'isCapitalized', $event)" />
            <el-tag v-else :type="row.isCapitalized ? 'success' : 'info'" size="small">{{ row.isCapitalized ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="capitalizeReason" label="资本化依据" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.capitalizeReason" size="small" @change="state.updateCell(row.rowId, 'capitalizeReason', $event)" />
            <span v-else>{{ row.capitalizeReason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="state.updateCell(row.rowId, 'voucherNo', $event)" />
            <span v-else>{{ row.voucherNo }}</span>
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

    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增增加项</el-button>
      <el-button size="small" type="primary" plain @click="samplingVisible = true">🎲 抽凭引擎</el-button>
    </div>

    <!-- 抽凭引擎 -->
    <el-dialog v-model="samplingVisible" title="H5-7 增加检查 — 抽凭引擎" width="85%" destroy-on-close>
      <GtVoucherSamplingEngine
        account-code="1631"
        phase="final"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        @filled="onSampleFilled"
      />
    </el-dialog>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
        placeholder="填写增加检查审计结论..." :disabled="isReadonly" @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>勘探支出资本化条件：CAS27.11要求证实技术可行性+经济可行性</li>
        <li>开发支出全部资本化；勘探支出未满足条件的费用化</li>
        <li>增加合计应与H5-2明细表/H5-1审定表借方发生一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import { useH5AdditionCheck } from '../../composables/useH5AdditionCheck'
import { useH5FormData } from '../../composables/useH5FormData'
import { useAuditContext } from '@/composables/useAuditContext'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean; year?: number }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5AdditionCheck({ allResponses: allResponsesRef as any, wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId'), onSave: (itemId: string, value: any) => formData.setResponse(itemId, value) })

// ─── 抽凭引擎 ────────────────────────────────────────────────────────────────
const samplingVisible = ref(false)
const { year: auditYear } = useAuditContext()
const samplingYear = computed(() => props.year || auditYear.value || new Date().getFullYear())

const rawMethodologyPersist = buildChecklistDirectPersist({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const methodologyDirectPersist = rawMethodologyPersist
/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'H5',
  allResponses: toRef(props, 'allResponses') as never,
  persist: methodologyDirectPersist,
  isReadonly: computed(() => props.isReadonly === true),
})

function onSampleFilled(payload: any): void {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  const samples = payload?.samples ?? []
  for (const s of samples) {
    state.addRow(s.summary || s.counterpartAccount || '抽凭样本', {
      voucherNo: s.voucherNo || '',
      amount: s.debitAmount || s.creditAmount || 0,
      conclusion: '',
    })
  }
  samplingVisible.value = false
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增增加项', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (value) state.addRow(value)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-addition-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.summary-row { margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; font-size: var(--wp-font-size, 13px); }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
