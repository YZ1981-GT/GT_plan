<template>
  <div class="h8-tab-impairment">
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>
        审计目标：确认使用权资产减值准备以恰当金额计入报表；可收回金额=max(公允减处置费用,DCF现值)；
        减值一经确认不得转回（CAS8）。有迹象须完成 H8-11 并回写③④。
      </template>
    </el-alert>

    <div class="methodology-context">
      <p>
        <strong>编制逻辑：</strong>
        B 迹象 → ②账面(原值−累计折旧，不含减值) → ③④(H8-11) → ⑤=MAX(③,④)
        → ⑥=MAX(②−⑤,0) → ⑧=MAX(⑥−⑦,0) / ⑨=MAX(⑦−⑥,0)（⑨仅待查，禁止转回）。
        Excel 源模板 J=H−I 可为负，本表拆为⑧/⑨以落实 CAS8 不得转回。
      </p>
    </div>

    <div class="h8-tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H8-10" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 行</el-tag>
        <el-tag v-if="state.overProvisionTotal.value > 0" type="warning" size="small">
          多提待查 {{ fmtAmt(state.overProvisionTotal.value) }}
        </el-tag>
        <el-tag v-if="!state.prepValidation.value.ok" type="danger" size="small">
          编制校验 {{ state.prepValidation.value.messages.length }} 项
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:H8-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:H8-8" :context-project-id="projectId" />
        <GtIndexChip value="wp:H8-11" :context-project-id="projectId" />
        <GtIndexChip value="wp:K11" :context-project-id="projectId" />
      </div>
    </div>

    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="section-title">
          <span>减值测算表（H8-10）</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleImportH82">从 H8-2 带入②</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handlePullH88">带入⑦(H8-8)</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handlePullH811">回填 H8-11</el-button>
            <el-button size="small" type="warning" plain :disabled="isReadonly || state.supplementTotal.value < 0.01" @click="handleSwitchH88">
              切换 H8-8 含减值
            </el-button>
            <el-button size="small" :disabled="isReadonly || !projectId" @click="handleReconcileK11">核对 K11</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="state.addRow()">新增行</el-button>
            <el-dropdown size="small" @command="handleExportCommand">
              <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" :disabled="isReadonly">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'impairment')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'impairment')">复核</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!state.prepValidation.value.ok"
        type="warning"
        :closable="false"
        show-icon
        class="mb-8"
        :title="state.prepValidation.value.messages[0]"
        :description="state.prepValidation.value.messages.slice(1).join('；') || undefined"
      />

      <el-table
        :data="state.rows.value"
        border
        size="small"
        class="impair-table"
        max-height="480"
        :row-class-name="getRowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" width="44" label="序号" />
        <el-table-column label="合同号" width="110">
          <template #default="{ row }">
            <el-input
              :model-value="row.contractNo"
              size="small"
              :disabled="isReadonly"
              @update:model-value="(v: string) => state.updateRow(row.rowId, { contractNo: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="使用权资产名称" min-width="130">
          <template #default="{ row }">
            <el-input
              :model-value="row.assetName"
              size="small"
              :disabled="isReadonly"
              @update:model-value="(v: string) => state.updateRow(row.rowId, { assetName: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="B 迹象" width="90">
          <template #default="{ row }">
            <el-select
              :model-value="row.hasIndication"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => state.updateRow(row.rowId, { hasIndication: v as 'Y' | 'N' | '' })"
            >
              <el-option label="√ 有" value="Y" />
              <el-option label="× 无" value="N" />
              <el-option label="—" value="" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="①迹象描述" min-width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.indicationDesc"
              size="small"
              :disabled="isReadonly || row.hasIndication !== 'Y'"
              @update:model-value="(v: string) => state.updateRow(row.rowId, { indicationDesc: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="②账面价值" width="110" align="right">
          <template #header>
            <el-tooltip content="原值−累计折旧（不含减值），自 H8-2 带入" placement="top">
              <span class="formula-col-header">②账面价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.bookValue"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => state.updateRow(row.rowId, { bookValue: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="③公允净额" width="110" align="right">
          <template #header>
            <el-tooltip content="H8-11 公允减处置费用后的净额" placement="top">
              <span class="formula-col-header">③公允净额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.fairValueLessDisposal"
              size="small"
              :controls="false"
              :disabled="isReadonly || row.hasIndication !== 'Y'"
              @change="(v: number | undefined) => state.updateRow(row.rowId, { fairValueLessDisposal: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="④DCF现值" width="110" align="right">
          <template #header>
            <el-tooltip content="H8-11 预计未来现金流量现值" placement="top">
              <span class="formula-col-header">④DCF现值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.dcfValue"
              size="small"
              :controls="false"
              :disabled="isReadonly || row.hasIndication !== 'Y'"
              @change="(v: number | undefined) => state.updateRow(row.rowId, { dcfValue: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="⑤可收回" width="100" align="right">
          <template #header>
            <el-tooltip content="⑤ = MAX(③,④)；无迹象时为 0" placement="top">
              <span class="formula-col-header">⑤可收回</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑥应计提" width="100" align="right">
          <template #header>
            <el-tooltip content="⑥ = MAX(②−⑤, 0)" placement="top">
              <span class="formula-col-header">⑥应计提</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'loss-value': row.impairmentAmount > 0 }">{{ fmtAmt(row.impairmentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑦已计提" width="110" align="right">
          <template #header>
            <el-tooltip content="期末账面已计提减值准备，可自 H8-8 含减值行带入" placement="top">
              <span class="formula-col-header">⑦已计提</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              :model-value="row.alreadyProvided"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => state.updateRow(row.rowId, { alreadyProvided: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="⑧应补提" width="100" align="right">
          <template #header>
            <el-tooltip content="⑧ = MAX(⑥−⑦, 0)；推送 K11" placement="top">
              <span class="formula-col-header">⑧应补提</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'loss-value': row.supplement > 0 }">{{ fmtAmt(row.supplement) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑨多提待查" width="100" align="right">
          <template #header>
            <el-tooltip content="⑨ = MAX(⑦−⑥, 0)；仅调查，禁止转回" placement="top">
              <span class="formula-col-header">⑨多提待查</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'warn-value': row.overProvision > 0 }">{{ fmtAmt(row.overProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="120">
          <template #default="{ row }">
            <div class="index-cell">
              <el-input
                :model-value="row.indexRef"
                size="small"
                :disabled="isReadonly"
                :placeholder="row.hasIndication === 'Y' ? '须含H8-11' : ''"
                @update:model-value="(v: string) => state.updateRow(row.rowId, { indexRef: v })"
              />
              <el-button
                v-if="row.hasIndication === 'Y'"
                link
                type="primary"
                size="small"
                @click="emit('navigate-sheet', 'H8-11')"
              >H8-11</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="impair-result" v-if="state.rows.value.length">
        <div class="result-row">
          <div class="result-item">
            <span class="result-label">②账面价值合计</span>
            <span class="result-value">{{ fmtAmt(state.bookValueTotal.value) }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">⑥应计提合计</span>
            <span class="result-value">{{ fmtAmt(state.requiredTotal.value) }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">⑧本期应补提</span>
            <span class="result-value" :class="state.supplementTotal.value > 0 ? 'loss-value' : ''">
              {{ state.supplementTotal.value > 0 ? fmtAmt(state.supplementTotal.value) : '无需补提' }}
            </span>
          </div>
          <div class="result-item">
            <span class="result-label">⑨多提待查</span>
            <span class="result-value" :class="state.overProvisionTotal.value > 0 ? 'warn-value' : ''">
              {{ state.overProvisionTotal.value > 0 ? fmtAmt(state.overProvisionTotal.value) : '-' }}
            </span>
          </div>
        </div>
        <el-alert
          v-if="state.k11Reconcile.value.message && state.k11Reconcile.value.message !== '尚未核对 K11'"
          :type="state.k11Reconcile.value.isMatch ? 'success' : 'error'"
          :closable="false"
          show-icon
          class="impair-warning"
          :title="state.k11Reconcile.value.message"
        />
        <el-alert
          v-if="state.supplementTotal.value > 0"
          type="warning"
          :closable="false"
          show-icon
          class="impair-warning"
          :title="`应补提减值准备 ${fmtAmt(state.supplementTotal.value)} 元；已推送 K11 事件。请点「切换 H8-8 含减值」后重算折旧。`"
        />
        <el-alert
          v-if="state.overProvisionTotal.value > 0"
          type="error"
          :closable="false"
          show-icon
          class="impair-warning"
          :title="`多提待查 ${fmtAmt(state.overProvisionTotal.value)} 元：请查处置结转等原因，禁止做减值转回分录（CAS8）。`"
        />
      </div>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="state.auditNote.value"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="填写：迹象识别依据、H8-11 关键与折现率、与 K11/H8-8 勾稽、多提待查原因及处理（结转≠转回）…"
        @change="(v: string) => state.saveAuditNote(v)"
      />
    </el-card>

    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="section-title">
          <span class="card-title">四、审计结论</span>
          <el-button size="small" plain :disabled="isReadonly" @click="fillConclusionDraft">填入结论模板</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="state.auditConclusion.value"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="经审计：（1）迹象识别…（2）可收回金额…（3）⑧应补提…（4）⑨多提待查…（5）减值准备在重大方面…"
        @change="(v: string) => state.saveAuditConclusion(v)"
      />
    </el-card>

    <div class="jump-targets">
      <span class="jump-label">跨底稿联动：</span>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-2')">H8-2 明细</el-button>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-8')">H8-8 折旧</el-button>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-11')">H8-11 可收回</el-button>
      <GtIndexChip value="wp:K11" :context-project-id="projectId" />
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>先「从 H8-2 带入②」，再评 B 列减值迹象；有迹象者完成 H8-11 后「回填 H8-11」写入③④（索引须含 H8-11）</li>
        <li>②=原值−累计折旧（不含减值），勿填已扣减值的审定净值；⑦按合同号优先、资产名称次之匹配 H8-8</li>
        <li>⑥=MAX(②−⑤,0)；⑧=MAX(⑥−⑦,0)；⑨&gt;0 只调查不转回；⑧自动推送 K11</li>
        <li>本期有⑧补提时点「切换 H8-8 含减值」，再在 H8-8 写入减值金额后重算折旧</li>
        <li>处置/转让时减值准备一并结转（终止确认），结转≠转回</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabImpairment.vue — H8-10 减值测算表
 * 行级测算 + H8-2/H8-8/H8-11/K11 联动（useH8Impairment）
 */
import { computed, toRef, watch, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH8Impairment, type H8ImpairmentCalcRow } from '../../composables/useH8Impairment'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const state = useH8Impairment({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

watch(() => props.allResponses, () => state.hydrate(), { deep: true })

const ieBusy = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  ieBusy.value = true
  try {
    if (cmd === 'export-template') await state.exportData('template')
    else if (cmd === 'export-data') await state.exportData('data')
    else if (cmd === 'import-data') fileInputRef.value?.click()
  } finally {
    ieBusy.value = false
  }
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!file) return
  try {
    await ElMessageBox.confirm(
      `即将导入「${file.name}」到 H8-10，已有测算行将被覆盖。确认？`,
      '导入确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  ieBusy.value = true
  try {
    const r = await state.importData(file, true)
    ElMessage.success(`已导入 ${r.imported} 行`)
  } catch (err: any) {
    ElMessage.error(err?.message || '导入失败')
  } finally {
    ieBusy.value = false
  }
}

async function handleImportH82() {
  const r = state.importFromH82()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handlePullH88() {
  const r = state.pullAlreadyProvidedFromH88()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handlePullH811() {
  const r = state.pullRecoverableFromH811()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handleSwitchH88() {
  const r = state.switchH88ToWithImpairment()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
  if (r.ok) emit('navigate-sheet', 'H8-8')
}

async function handleReconcileK11() {
  const r = await state.reconcileWithK11(props.projectId)
  ElMessage({ type: r.isMatch ? 'success' : 'warning', message: r.message })
}

function fillConclusionDraft() {
  state.saveAuditConclusion(state.buildConclusionDraft())
  ElMessage.success('已填入结论模板，请勾选并补全空白')
}

function getRowClassName({ row }: { row: H8ImpairmentCalcRow }): string {
  if (row.overProvision > 0.01) return 'over-row'
  if (row.supplement > 0.01) return 'supp-row'
  if (row.hasIndication === 'Y') return 'indication-row'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 5) return fmtAmt(state.bookValueTotal.value)
    if (idx === 8) return fmtAmt(state.recoverableTotal.value)
    if (idx === 9) return fmtAmt(state.requiredTotal.value)
    if (idx === 10) return fmtAmt(state.alreadyProvidedTotal.value)
    if (idx === 11) return fmtAmt(state.supplementTotal.value)
    if (idx === 12) return fmtAmt(state.overProvisionTotal.value)
    return ''
  })
}

function fmtAmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h8-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.mb-8 { margin-bottom: 8px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e; line-height: 1.7;
}
.methodology-context p { margin: 0; }
.h8-tab-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.summary-card { margin-bottom: 16px; }
.impair-table :deep(.el-input-number) { width: 100%; }
.formula-cell { font-variant-numeric: tabular-nums; }
.formula-col-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  padding-bottom: 2px;
}
.index-cell { display: flex; align-items: center; gap: 4px; }
.impair-result { margin-top: 12px; }
.result-row { display: flex; gap: 28px; flex-wrap: wrap; margin-bottom: 12px; }
.result-item { display: flex; flex-direction: column; gap: 4px; }
.result-label { font-size: 12px; color: var(--el-text-color-secondary); }
.result-value { font-size: 16px; font-weight: 700; color: var(--el-color-primary); }
.loss-value { color: #f56c6c; }
.warn-value { color: #e6a23c; }
.impair-warning { margin-top: 8px; }

:deep(.indication-row) { background: #f0f9ff !important; }
:deep(.indication-row td) { background: #f0f9ff !important; }
:deep(.supp-row) { background: #fef2f2 !important; }
:deep(.supp-row td) { background: #fef2f2 !important; }
:deep(.over-row) { background: #fff7ed !important; }
:deep(.over-row td) { background: #fff7ed !important; }

.jump-targets {
  display: flex; align-items: center; gap: 8px; margin-top: 12px; flex-wrap: wrap;
}
.jump-label { font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
