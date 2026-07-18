<template>
  <div class="f2-contract-perf">
    <header class="hero">
      <div class="hero-main">
        <h3 class="hero-title">合同履约成本明细表 F2-12</h3>
        <el-tag size="small" effect="plain">科目 1410</el-tag>
      </div>
      <p class="hero-sub">项目编码/名称 · 转入/转出 · 库龄 · 跌价净额</p>
    </header>

    <details class="guidance">
      <summary>编制提示</summary>
      <div class="guidance-body">
        <p>1. 按项目列示合同履约成本：编码、名称、开工/预计竣工时间；期初 → 本期转入 → 本期转出 → 期末余额。</p>
        <p>2. 灰色列为自动计算：期末 = 期初 + 转入 − 转出；库龄各段合计须等于期末余额。</p>
        <p>3. 页尾合计 − 跌价准备 = 合同履约成本净额；停建项目须在审计说明中写明原因。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="obj-alert"
      title="审计目标：核实合同履约成本期末余额的存在与完整，验证转入转出及库龄分布，评价跌价（减值）计提充分性。"
    />

    <div class="toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">新增项目</el-button>
        <el-input
          v-model="sheet.searchText.value"
          size="small"
          clearable
          placeholder="搜索编码 / 项目名称…"
          class="search"
        />
        <span class="muted">库龄口径</span>
        <el-select
          :model-value="sheet.agingPreset.value"
          size="small"
          class="aging-sel"
          :disabled="isReadonly"
          @change="(v: string) => sheet.applyAgingPreset(v as any)"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-tag v-if="sheet.totals.value.agingOk" type="success" size="small" effect="dark">库龄 OK</el-tag>
        <el-tag v-else type="danger" size="small">库龄与期末不匹配</el-tag>
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-12"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip"><GtIndexChip value="wp:F2-12" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ sheet.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="sheet.filteredRows.value" border size="small" class="main-table" max-height="520"
      :row-class-name="({ row }) => row.agingOk ? '' : 'warn-row'">
      <el-table-column type="index" label="序号" width="56" fixed />
      <el-table-column label="项目编码" width="110" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.projectCode"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { projectCode: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="项目名称" min-width="140" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.projectName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { projectName: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="开工时间" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.startDate"
            size="small"
            placeholder="YYYY-MM-DD"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { startDate: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="预计竣工时间" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.expectedCompleteDate"
            size="small"
            placeholder="YYYY-MM-DD"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { expectedCompleteDate: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="110">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.openingAmt"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => sheet.updateRow(row.id, { openingAmt: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期转入" width="110">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.increaseAmt"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => sheet.updateRow(row.id, { increaseAmt: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="本期转出" width="110">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.decreaseAmt"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => sheet.updateRow(row.id, { decreaseAmt: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="110" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closingAmt) }}</span></template>
      </el-table-column>
      <el-table-column label="库龄" align="center">
        <el-table-column
          v-for="seg in sheet.segments.value"
          :key="seg.key"
          :label="seg.label"
          width="100"
        >
          <template #default="{ row }">
            <el-input-number
              :model-value="Number(row.aging?.[seg.key] ?? 0)"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => sheet.updateAgingCell(row.id, seg.key, v ?? 0)"
            />
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="库龄合计" width="100" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="row.agingOk ? 'formula' : 'bad'">{{ fmtAmt(row.agingTotal) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品质状况" width="100">
        <template #default="{ row }">
          <el-select
            :model-value="row.qualityStatus"
            size="small"
            clearable
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { qualityStatus: v || '' })"
          >
            <el-option v-for="o in QUALITY" :key="o" :label="o" :value="o" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="danger" :disabled="isReadonly" @click="sheet.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <section class="summary-panel">
      <div class="summary-row">
        <span class="lab">合计（期末余额）</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.closingAmt) }}</span>
        <span class="muted tiny">
          期初 {{ fmtAmt(sheet.totals.value.openingAmt) }}
          · 转入 {{ fmtAmt(sheet.totals.value.increaseAmt) }}
          · 转出 {{ fmtAmt(sheet.totals.value.decreaseAmt) }}
        </span>
      </div>
      <div class="summary-row">
        <span class="lab">减：存货跌价准备</span>
        <el-input-number
          :model-value="sheet.impairmentProvision.value"
          size="small"
          :controls="false"
          :disabled="isReadonly"
          @change="(v: number | undefined) => sheet.persistImpairment(v ?? 0)"
        />
      </div>
      <div class="summary-row net">
        <span class="lab">合同履约成本净额</span>
        <span class="val">{{ fmtAmt(sheet.netAmt.value) }}</span>
      </div>
    </section>

    <section class="notes-panel">
      <h4>审计说明</h4>
      <div v-for="f in noteFields" :key="f.key" class="note-block">
        <div class="note-label">
          <span>{{ f.label }}</span>
          <el-button
            size="small"
            text
            type="primary"
            :disabled="isReadonly || !aiAvailable || aiBusyKey === f.key"
            :loading="aiBusyKey === f.key"
            @click="generateNote(f)"
          >AI</el-button>
        </div>
        <el-input
          type="textarea"
          :rows="2"
          :model-value="sheet.notePack.value[f.packKey]"
          :disabled="isReadonly"
          :placeholder="f.placeholder"
          @change="(v: string) => sheet.persistNotePack({ [f.packKey]: v })"
        />
      </div>
    </section>

    <section class="notes-panel conclusion">
      <div class="note-label">
        <span>审计结论</span>
        <el-button
          size="small"
          text
          type="primary"
          :disabled="isReadonly || !aiAvailable || aiBusyKey === 'conclusion'"
          :loading="aiBusyKey === 'conclusion'"
          @click="generateConclusion"
        >AI</el-button>
      </div>
      <el-input
        type="textarea"
        :rows="3"
        :model-value="sheet.auditConclusion.value"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项，不可确认。"
        @change="(v: string) => sheet.persistConclusion(v)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { inject, ref, toRef, type Ref } from 'vue'
import { useF2ContractPerfSheet, CONTRACT_PERF_QUALITY } from '../../composables/useF2ContractPerfSheet'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'

const QUALITY = CONTRACT_PERF_QUALITY

const props = defineProps<{
  wpId: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sheet = useF2ContractPerfSheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const { aiAvailable, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)
const aiBusyKey = ref<string | null>(null)

type NotePackKey = 'costMethod' | 'significantChange' | 'suspendedReason' | 'impairmentReason'

const noteFields: Array<{
  key: string
  packKey: NotePackKey
  section: F2AiSection
  label: string
  placeholder: string
}> = [
  {
    key: 'method',
    packKey: 'costMethod',
    section: 'detail-valuation',
    label: '1. 合同履约成本核算方法：',
    placeholder: '合同履约成本核算方法：',
  },
  {
    key: 'change',
    packKey: 'significantChange',
    section: 'detail-change',
    label: '2. 本期重大变动及原因：',
    placeholder: '合同履约成本本期发生的重大变动及原因：',
  },
  {
    key: 'suspend',
    packKey: 'suspendedReason',
    section: 'detail-long-aging',
    label: '3. 「停建」的原因：',
    placeholder: '合同履约成本「停建」的原因：',
  },
  {
    key: 'imp',
    packKey: 'impairmentReason',
    section: 'detail-impairment',
    label: '4. 计提跌价准备的主要项目及原因：',
    placeholder: '计提跌价准备的主要项目及原因：',
  },
]

async function generateNote(f: (typeof noteFields)[number]) {
  aiBusyKey.value = f.key
  try {
    const text = await generateAndConfirm(
      f.section,
      sheet.notePack.value[f.packKey],
      {
        sheetCode: 'F2-12',
        sheetName: '合同履约成本',
        noteHint: f.label,
        endBalance: sheet.totals.value.closingAmt,
        netAmt: sheet.netAmt.value,
        agingOk: sheet.totals.value.agingOk,
      },
      `AI 生成 · F2-12 ${f.label}`,
    )
    if (text) sheet.persistNotePack({ [f.packKey]: text })
  } finally {
    aiBusyKey.value = null
  }
}

async function generateConclusion() {
  aiBusyKey.value = 'conclusion'
  try {
    const text = await generateAndConfirm(
      'detail-conclusion',
      sheet.auditConclusion.value,
      {
        sheetCode: 'F2-12',
        sheetName: '合同履约成本',
        endBalance: sheet.totals.value.closingAmt,
        netAmt: sheet.netAmt.value,
        agingOk: sheet.totals.value.agingOk,
      },
      'AI · F2-12 审计结论',
    )
    if (text) sheet.persistConclusion(text)
  } finally {
    aiBusyKey.value = null
  }
}

function fmtAmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }
</script>

<style scoped>
.f2-contract-perf { padding: 8px 4px 24px; font-size: var(--wp-font-size, 13px); }
.f2-contract-perf :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-contract-perf :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.hero { margin-bottom: 10px; }
.hero-main { display: flex; align-items: center; gap: 10px; }
.hero-title { margin: 0; font-size: 16px; font-weight: 600; }
.hero-sub { margin: 4px 0 0; color: #909399; font-size: 12px; }
.guidance { margin-bottom: 10px; font-size: 13px; }
.guidance-body { padding: 8px 4px; color: #606266; line-height: 1.6; }
.obj-alert { margin-bottom: 10px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.search { width: 180px; }
.aging-sel { width: 100px; }
.chip { display: inline-flex; }
.muted { color: #909399; font-size: 12px; }
.main-table :deep(.auto-calc-col) { background: #faf8fc; }
.main-table :deep(.warn-row) { background: #fdf6ec; }
.formula { color: #606266; font-variant-numeric: tabular-nums; }
.bad { color: #e6a23c; font-weight: 600; }
.summary-panel { margin-top: 12px; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; }
.summary-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.summary-row.net .lab, .summary-row.net .val { font-weight: 600; }
.lab { min-width: 160px; color: #606266; }
.val { font-variant-numeric: tabular-nums; }
.muted.tiny { color: #909399; font-size: 12px; }
.notes-panel { margin-top: 14px; }
.notes-panel h4 { margin: 0 0 8px; font-size: 14px; }
.note-block { margin-bottom: 8px; }
.note-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 13px;
  color: #606266;
  font-weight: 500;
}
.conclusion { border-top: 1px dashed #e4e7ed; padding-top: 10px; }
</style>
