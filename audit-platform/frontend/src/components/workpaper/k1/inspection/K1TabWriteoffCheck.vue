<!--
  K1TabWriteoffCheck.vue — K1-9 坏账准备转回（收回）、核销检查表

  编制逻辑：目标 → 程序 → 重要转回/收回明细 → 重要核销明细 → 说明 → 结论
  与 K1-3 坏账准备明细「本期转回/本期核销」勾稽；关注利润调节风险与关联方核销。
-->
<template>
  <div class="k1-audit-sheet">
    <div class="section-head">
      <h3 class="sheet-title">K1-9 坏账准备转回（收回）、核销检查表</h3>
      <div class="head-actions">
        <GtReviewTrigger section-id="K1-9-writeoff-header" />
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <p class="ao-text">
        确定其他应收款坏账准备计提是否充分，坏账准备转回、收回、转销是否恰当；
        核销依据是否符合规定、会计处理是否正确；已核销坏账重新收回的会计处理是否正确。
      </p>
    </el-alert>

    <div v-if="!isReadonly" class="tab-toolbar">
      <el-button-group>
        <el-button size="small" :disabled="k13ImportableCount === 0" @click="onImportFromK13">
          从 K1-3 导入{{ k13ImportableCount > 0 ? ` (${k13ImportableCount})` : '' }}
        </el-button>
        <el-button size="small" @click="onSyncK11">同步 K1-11 关联方</el-button>
        <el-button size="small" link type="primary" @click="goK11">K1-11 →</el-button>
      </el-button-group>
      <el-button-group>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImport" style="display:inline-block">
          <el-button size="small" :loading="importing">导入数据</el-button>
        </el-upload>
      </el-button-group>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、审计程序</span></template>
      <el-input
        v-model="auditProcedures"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="审计程序..."
        @change="persist"
      />
    </el-card>

    <!-- 勾稽核对 -->
    <el-card v-if="showReconcilePanel" shadow="never" class="section-card reconcile-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">与 K1-3 勾稽核对</span>
          <el-button size="small" link type="primary" @click="goK13">跳转 K1-3 →</el-button>
        </div>
      </template>
      <div class="reconcile-grid">
        <div class="reconcile-item">
          <span class="metric-label">本表转回合计</span>
          <span class="metric-value">{{ fmtAmt(reversalTotal) }}</span>
        </div>
        <div class="reconcile-item">
          <span class="metric-label">K1-3 本期转回</span>
          <span class="metric-value">{{ fmtAmt(k13ReversalTotal) }}</span>
        </div>
        <div class="reconcile-item" :class="{ diff: reversalDiff != null && Math.abs(reversalDiff) >= 0.01 }">
          <span class="metric-label">转回差异</span>
          <span class="metric-value">{{ reversalDiff == null ? '—' : fmtAmt(reversalDiff) }}</span>
        </div>
        <div class="reconcile-item">
          <span class="metric-label">本表核销合计</span>
          <span class="metric-value">{{ fmtAmt(writeoffTotal) }}</span>
        </div>
        <div class="reconcile-item">
          <span class="metric-label">K1-3 本期核销</span>
          <span class="metric-value">{{ fmtAmt(k13WriteoffTotal) }}</span>
        </div>
        <div class="reconcile-item" :class="{ diff: writeoffDiff != null && Math.abs(writeoffDiff) >= 0.01 }">
          <span class="metric-label">核销差异</span>
          <span class="metric-value">{{ writeoffDiff == null ? '—' : fmtAmt(writeoffDiff) }}</span>
        </div>
      </div>
    </el-card>

    <el-alert v-if="reversalConsistencyWarning" type="warning" :closable="false" show-icon class="consistency-alert">
      {{ reversalConsistencyWarning }}
    </el-alert>
    <el-alert v-if="writeoffConsistencyWarning" type="warning" :closable="false" show-icon class="consistency-alert">
      {{ writeoffConsistencyWarning }}
    </el-alert>
    <el-alert
      v-if="relatedPartyWriteoffCount > 0"
      type="warning"
      :closable="false"
      show-icon
      class="consistency-alert"
    >
      本期有 {{ relatedPartyWriteoffCount }} 笔关联方往来核销，请重点关注合理性与审批程序。
    </el-alert>

    <!-- (一) 转回检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、(一) 本期重要的坏账准备转回检查</span>
          <el-button v-if="!isReadonly" size="small" @click="addRow('reversal'); persist()">＋ 新增</el-button>
        </div>
      </template>
      <el-table
        :data="reversalRows"
        border
        size="small"
        :max-height="320"
        class="audit-table"
        :row-class-name="reversalRowClass"
      >
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="单位名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unit" size="small" @change="persist" />
            <span v-else>{{ row.unit || '-' }}</span>
            <GtReviewDot row-prefix="K1-9-reversal" :row-key="row.id" />
          </template>
        </el-table-column>
        <el-table-column label="转回原因" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" placeholder="必填（有金额时）" @change="persist" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回方式" min-width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.method" size="small" clearable filterable allow-create @change="persist">
              <el-option v-for="m in K1_RECOVERY_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.method || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确定坏账准备的依据" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.basis" size="small" @change="persist" />
            <span v-else>{{ row.basis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回或转回金额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" :precision="2" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回/转回前累计已计提" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accumProvision" :controls="false" :precision="2" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accumProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" clearable @change="persist">
              <el-option v-for="o in K1_REASONABLE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性分析" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.analysis" size="small" placeholder="必填（有金额时）" @change="persist" />
            <span v-else>{{ row.analysis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="64" align="center" fixed="right">
          <template #default="{ row }">
            <el-upload
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              :disabled="ocrLoading"
              @change="(f: any) => onWriteoffOcr('reversal', row, f?.raw)"
            >
              <el-button link size="small" type="primary" :loading="ocrLoading">📎</el-button>
            </el-upload>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('reversal', row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无转回/收回记录，可点击「新增」或从 K1-3 大额项目选取</template>
        <template #append>
          <div class="table-total">合计　收回或转回金额：{{ fmtAmt(reversalTotal) }}</div>
        </template>
      </el-table>
    </el-card>

    <!-- (二) 核销检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、(二) 本期重要的核销检查</span>
          <el-button v-if="!isReadonly" size="small" @click="addRow('writeoff'); persist()">＋ 新增</el-button>
        </div>
      </template>
      <el-table
        :data="writeoffRows"
        border
        size="small"
        :max-height="320"
        class="audit-table"
        :row-class-name="writeoffRowClass"
      >
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="单位名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unit" size="small" @change="persist" />
            <span v-else>{{ row.unit || '-' }}</span>
            <GtReviewDot row-prefix="K1-9-writeoff" :row-key="row.id" />
          </template>
        </el-table-column>
        <el-table-column label="其他应收款的性质" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.nature" size="small" @change="persist" />
            <span v-else>{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" :precision="2" size="small" class="amt" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" placeholder="必填（有金额时）" @change="persist" />
            <span v-else>{{ row.reason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="履行的核销程序" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.procedure" size="small" placeholder="必填（有金额时）" @change="persist" />
            <span v-else>{{ row.procedure || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否关联方往来" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.relatedParty" size="small" @change="persist">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.relatedParty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isReasonable" size="small" clearable @change="persist">
              <el-option v-for="o in K1_REASONABLE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.isReasonable || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性分析" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.analysis" size="small" placeholder="必填（有金额时）" @change="persist" />
            <span v-else>{{ row.analysis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="64" align="center" fixed="right">
          <template #default="{ row }">
            <el-upload
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              :disabled="ocrLoading"
              @change="(f: any) => onWriteoffOcr('writeoff', row, f?.raw)"
            >
              <el-button link size="small" type="primary" :loading="ocrLoading">📎</el-button>
            </el-upload>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('writeoff', row.id); persist()">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无核销记录</template>
        <template #append>
          <div class="table-total">合计　核销金额：{{ fmtAmt(writeoffTotal) }}</div>
        </template>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">四、审计说明</span>
          <el-button v-if="aiAvailable && !isReadonly" size="small" link type="primary" :loading="aiLoading" @click="onAiAuditNote">
            🤖 AI 生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="核销依据是否符合规定、会计处理是否正确；转回/收回合理性；已核销重新收回的处理；与 K1-3/K1-11 的交叉引用"
        @change="persist"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select
        v-model="conclusionOption"
        :disabled="isReadonly"
        size="small"
        class="concl-select"
        placeholder="选择结论模板"
        @change="onConclusionOption"
      >
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述调整事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大未调整事项，不可确认" value="C" />
      </el-select>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="形成审计结论..."
        @change="persist"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>本表聚焦<strong>坏账准备减少方向</strong>（转回/收回/核销），与 K1-8 测算（计提方向）互补</li>
        <li>转回/收回：应有客观证据（债务人状况好转、实际收款等），并与原计提依据一致，防止跨期调节利润</li>
        <li>核销：须履行内部审批，取得破产/死亡/长期无法收回等依据；核销后保留追索权登记</li>
        <li>本表转回/核销合计须与 K1-3 坏账准备明细「本期转回」「本期核销」列勾稽一致</li>
        <li>关联方往来核销须与 K1-11 交叉核对；已核销重新收回须检查会计处理</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { K1_CONCLUSION_TEMPLATES } from '../../composables/useK1AuditRows'
import {
  useK1WriteoffCheck,
  K1_RECOVERY_METHODS,
  K1_REASONABLE_OPTIONS,
  getMissingK1ReversalFields,
  getMissingK1WriteoffFields,
  type K1ReversalRow,
  type K1WriteoffRow,
} from '../../composables/useK1WriteoffCheck'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import { useK1VoucherOcr } from '../../composables/useK1VoucherOcr'
import http from '@/utils/http'
import GtReviewDot from '../../GtReviewDot.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheet: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const wpIdRef = toRef(props, 'wpId')

const {
  reversalRows,
  writeoffRows,
  auditProcedures,
  auditNote,
  conclusion,
  conclusionOption,
  reversalTotal,
  writeoffTotal,
  k13ReversalTotal,
  k13WriteoffTotal,
  reversalDiff,
  writeoffDiff,
  reversalConsistencyWarning,
  writeoffConsistencyWarning,
  relatedPartyWriteoffCount,
  k13ImportableCount,
  load,
  addRow,
  removeRow,
  buildSavePayload,
  importFromK13,
  syncRelatedPartyFromK11,
  isReversalExceedsProvision,
} = useK1WriteoffCheck({ allResponses: toRef(props, 'allResponses') })

const { isImporting: importing, exportTemplate, exportData, importData } = useK1ImportExport({ wpId: wpIdRef })

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useK1AiGenerate(wpIdRef)

const { ocrLoading, runOcr } = useK1VoucherOcr()

function onWriteoffOcr(
  kind: 'reversal' | 'writeoff',
  row: K1ReversalRow | K1WriteoffRow,
  file?: File,
) {
  if (!file || props.isReadonly) return
  void runOcr(file, (text) => {
    const prev = row.analysis || ''
    row.analysis = prev ? `${prev}\n[OCR] ${text}` : `[OCR] ${text}`
    persist()
  })
}

onMounted(() => load())

async function reloadFromServer() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: any[] = Array.isArray(res?.data?.data) ? res.data.data : Array.isArray(res?.data) ? res.data : []
    for (const item of items) {
      const id = item.item_id || item.itemId
      if (!id || !String(id).startsWith('K1-9')) continue
      props.allResponses.set(id, { item_id: id, remark: item.remark ?? null, conclusion: item.conclusion ?? null })
    }
    load()
  } catch {
    load()
  }
}

function onExportTemplate() { exportTemplate('K1-9') }
function onExportData() { exportData('K1-9') }

const showReconcilePanel = computed(
  () =>
    reversalTotal.value > 0 ||
    writeoffTotal.value > 0 ||
    k13ReversalTotal.value > 0 ||
    k13WriteoffTotal.value > 0,
)

function persist() {
  const { itemId, remark, totals } = buildSavePayload()
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark })
  emit('save', itemId, { remark })
  for (const t of totals) {
    props.allResponses.set(t.item_id, { item_id: t.item_id, conclusion: null, remark: t.remark })
    emit('save', t.item_id, { remark: t.remark })
  }
}

function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  persist()
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleReview() {
  openReviewDialog('K1-9-writeoff')
}

function goK13() {
  emit('navigate-sheet', 'K1-3')
}

function goK11() {
  emit('navigate-sheet', 'K1-11')
}

async function onImportFromK13() {
  if (k13ImportableCount.value === 0) {
    ElMessage.info('K1-3 暂无本期转回/核销数据')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将从 K1-3 导入 ${k13ImportableCount.value} 笔有转回或核销的明细（同名合并，保留已填分析/索引号）。是否继续？`,
      '从 K1-3 导入',
      { confirmButtonText: '导入', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  const r = importFromK13()
  persist()
  ElMessage.success(
    `导入完成：转回新增 ${r.reversalAdded}、更新 ${r.reversalUpdated}；核销新增 ${r.writeoffAdded}、更新 ${r.writeoffUpdated}`,
  )
}

function onSyncK11() {
  const n = syncRelatedPartyFromK11()
  if (n > 0) {
    persist()
    ElMessage.success(`已标记 ${n} 笔关联方核销`)
  } else {
    ElMessage.info('未发现需更新的关联方核销行（请先在 K1-11 维护关联方明细）')
  }
}

async function handleImport(file: File): Promise<boolean> {
  const result = await importData('K1-9', file)
  if (result) {
    await reloadFromServer()
    persist()
  }
  return false
}

async function onAiAuditNote() {
  const content = await generateAndConfirm('writeoff-eval', auditNote.value, {
    reversalTotal: reversalTotal.value,
    writeoffTotal: writeoffTotal.value,
    reversalCount: reversalRows.value.length,
    writeoffCount: writeoffRows.value.length,
    relatedPartyWriteoffCount: relatedPartyWriteoffCount.value,
    reversalDiff: reversalDiff.value,
    writeoffDiff: writeoffDiff.value,
    k13ReversalTotal: k13ReversalTotal.value,
    k13WriteoffTotal: k13WriteoffTotal.value,
  }, 'AI 生成 K1-9 审计说明')
  if (content) {
    auditNote.value = content
    persist()
  }
}

function reversalRowClass({ row }: { row: K1ReversalRow }) {
  if (isReversalExceedsProvision(row.amount, row.accumProvision)) return 'row-warning'
  if (getMissingK1ReversalFields(row).length > 0) return 'row-incomplete'
  if (row.isReasonable === '不合理') return 'row-warning'
  return ''
}

function writeoffRowClass({ row }: { row: K1WriteoffRow }) {
  if (getMissingK1WriteoffFields(row).length > 0) return 'row-incomplete'
  if (row.relatedParty === '是' && row.amount > 0) return 'row-warning'
  if (row.isReasonable === '不合理') return 'row-warning'
  return ''
}
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.tab-toolbar { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; margin-bottom: 10px; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-text { margin: 4px 0 0; line-height: 1.6; font-size: 12px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.consistency-alert { margin-bottom: 10px; }
.reconcile-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.reconcile-item { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.reconcile-item.diff { background: var(--el-color-warning-light-9); }
.metric-label { font-size: 11px; color: var(--el-text-color-secondary); }
.metric-value { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
:deep(.row-warning) { background-color: var(--el-color-warning-light-9) !important; }
:deep(.row-incomplete) { background-color: var(--el-color-info-light-9) !important; }
</style>
