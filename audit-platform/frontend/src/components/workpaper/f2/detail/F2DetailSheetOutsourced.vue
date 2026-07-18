<template>
  <div class="f2-outsourced">
    <header class="hero">
      <div class="hero-main">
        <h3 class="hero-title">委托加工物资明细表 F2-7</h3>
        <el-tag size="small" effect="plain">科目 1405</el-tag>
      </div>
      <p class="hero-sub">加工单位 · 合同 · 发出物资成本构成 · 库龄 · 跌价净额</p>
    </header>

    <details class="guidance">
      <summary>编制提示</summary>
      <div class="guidance-body">
        <p>1. 按加工单位/合同列示发出加工物资：数量、单价、金额，并登记加工费、运杂费、计入成本的税金。</p>
        <p>2. 灰色列为自动计算：金额 = 数量 × 单价；加工物资成本 = 金额 + 加工费 + 运杂费 + 税金；库龄合计须等于加工物资成本。</p>
        <p>3. 页尾合计 − 跌价准备 = 存货净额；可用「成本 / 库龄 / 完整」切换视图。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="obj-alert"
      title="审计目标：核实委托加工物资期末成本的存在与准确，验证成本构成完整性及库龄分布，评价跌价计提充分性。"
    />

    <div class="toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">
          新增明细
        </el-button>
        <el-input
          v-model="sheet.searchText.value"
          size="small"
          clearable
          placeholder="搜索加工单位 / 合同 / 物资…"
          class="search"
        />
        <span class="muted">库龄口径</span>
        <el-select
          v-model="agingPresetModel"
          size="small"
          class="aging-sel"
          :disabled="isReadonly"
          @change="onAgingPresetChange"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
          <el-option label="自定义" value="CUSTOM" />
        </el-select>
        <el-radio-group v-model="sheet.activeView.value" size="small">
          <el-radio-button value="cost">成本</el-radio-button>
          <el-radio-button value="aging">库龄</el-radio-button>
          <el-radio-button value="full">完整</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <el-tag v-if="sheet.totals.value.agingOk" type="success" size="small" effect="dark">库龄 OK</el-tag>
        <el-tag v-else type="danger" size="small">库龄与成本不匹配</el-tag>
        <el-tag v-if="sheet.agingMismatch.value.length" type="warning" size="small">
          {{ sheet.agingMismatch.value.length }} 行库龄异常
        </el-tag>
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-7"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip"><GtIndexChip value="wp:F2-7" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ sheet.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="sheet.filteredRows.value"
      border
      size="small"
      class="main-table"
      :max-height="sheet.useVirtualScroll.value ? 520 : undefined"
      :row-class-name="rowClass"
    >
      <el-table-column label="加工单位名称" min-width="140" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.processorName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { processorName: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="加工合同号" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.contractNo"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { contractNo: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="发出加工物资名称" min-width="160" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.materialName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { materialName: v })"
          />
        </template>
      </el-table-column>

      <template v-if="showCost">
        <el-table-column label="数量" width="88">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.qty"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => sheet.updateRow(row.id, { qty: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="单价" width="96">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.unitPrice === '' ? undefined : Number(row.unitPrice)"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => sheet.updateRow(row.id, { unitPrice: v ?? '' })"
            />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula">{{ fmtAmt(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column label="加工费用" width="110">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.processingFee"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => sheet.updateRow(row.id, { processingFee: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="运杂费" width="100">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.freight"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => sheet.updateRow(row.id, { freight: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="计入加工物资成本的税金" width="150">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.taxInCost"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => sheet.updateRow(row.id, { taxInCost: v ?? 0 })"
            />
          </template>
        </el-table-column>
        <el-table-column label="加工物资成本" width="120" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula">{{ fmtAmt(row.processingCost) }}</span></template>
        </el-table-column>
      </template>

      <template v-if="showAging">
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
            <span :class="Math.abs(row.agingTotal - row.processingCost) > 0.01 ? 'bad' : 'formula'">
              {{ fmtAmt(row.agingTotal) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!showCost" label="加工物资成本" width="120" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula">{{ fmtAmt(row.processingCost) }}</span></template>
        </el-table-column>
      </template>

      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="danger" :disabled="isReadonly" @click="sheet.removeRow(row.id)">
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <section class="summary-panel">
      <div class="summary-row">
        <span class="lab">合计（加工物资成本）</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.processingCost) }}</span>
        <span v-if="showCost" class="muted tiny">
          金额 {{ fmtAmt(sheet.totals.value.amount) }}
          · 加工费 {{ fmtAmt(sheet.totals.value.processingFee) }}
          · 运杂费 {{ fmtAmt(sheet.totals.value.freight) }}
          · 税金 {{ fmtAmt(sheet.totals.value.taxInCost) }}
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
        <span class="lab">存货净额</span>
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
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="(v: string) => sheet.persistConclusion(v)"
      />
    </section>

    <el-dialog v-model="showCustomDialog" title="自定义库龄段" width="420px" @close="cancelCustomAging">
      <p class="muted">每行一个库龄段名称</p>
      <el-input v-model="customInput" type="textarea" :rows="6" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef, ref, type Ref } from 'vue'
import {
  useF2DetailOutsourced,
  type F2OutsourcedRow,
} from '../../composables/useF2DetailOutsourced'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import type { F2DetailNotePack } from '../../composables/useF2DetailSheet'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { AgingPreset } from '@/composables/useAgingConfig'

const props = defineProps<{
  wpId: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sheet = useF2DetailOutsourced({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const showCost = computed(() => sheet.activeView.value === 'cost' || sheet.activeView.value === 'full')
const showAging = computed(() => sheet.activeView.value === 'aging' || sheet.activeView.value === 'full')

const { aiAvailable, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)
const aiBusyKey = ref<string | null>(null)

const noteFields: Array<{
  key: string
  packKey: keyof F2DetailNotePack
  section: F2AiSection
  label: string
  placeholder: string
}> = [
  {
    key: 'valuation',
    packKey: 'valuationMethod',
    section: 'detail-valuation',
    label: '1. 成本核算方法：',
    placeholder: '委托加工物资的成本核算方法：',
  },
  {
    key: 'change',
    packKey: 'significantChange',
    section: 'detail-change',
    label: '2. 本期重大变动原因：',
    placeholder: '委托加工物资本期发生重大变动的原因：',
  },
  {
    key: 'longAging',
    packKey: 'longAgingReason',
    section: 'detail-long-aging',
    label: '3. 库龄较长的原因：',
    placeholder: '委托加工物资——库龄较长的原因：',
  },
  {
    key: 'impairment',
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
        sheetCode: 'F2-7',
        sheetName: '委托加工物资',
        noteHint: f.label,
        processingCost: sheet.totals.value.processingCost,
        netAmt: sheet.netAmt.value,
        agingOk: sheet.totals.value.agingOk,
      },
      `AI 生成 · F2-7 ${f.label}`,
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
        sheetCode: 'F2-7',
        sheetName: '委托加工物资',
        processingCost: sheet.totals.value.processingCost,
        netAmt: sheet.netAmt.value,
        agingOk: sheet.totals.value.agingOk,
      },
      'AI · F2-7 审计结论',
    )
    if (text) sheet.persistConclusion(text)
  } finally {
    aiBusyKey.value = null
  }
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

function fmtAmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function rowClass({ row }: { row: F2OutsourcedRow }): string {
  return Math.abs(row.agingTotal - row.processingCost) > 0.01 ? 'warn-row' : ''
}

const agingPresetModel = computed({
  get: () => sheet.agingPreset.value,
  set: (v: AgingPreset) => { sheet.agingPreset.value = v },
})
const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<AgingPreset>(
  sheet.agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : sheet.agingPreset.value,
)

function onAgingPresetChange(val: AgingPreset) {
  if (val === 'CUSTOM') {
    const labels = sheet.customSegments.value.length
      ? sheet.customSegments.value.map((s) => s.label)
      : ['1年以内', '1-2年', '2-3年', '3年以上']
    customInput.value = labels.join('\n')
    showCustomDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  sheet.applyAgingPreset(val)
}
function confirmCustomAging() {
  const lines = customInput.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (!sheet.applyAgingPreset('CUSTOM', lines)) return
  showCustomDialog.value = false
}
function cancelCustomAging() {
  showCustomDialog.value = false
  if (!sheet.customSegments.value.length) sheet.applyAgingPreset(lastNonCustomPreset.value)
  else sheet.agingPreset.value = 'CUSTOM'
}
</script>

<style scoped>
.f2-outsourced {
  --f2-ink: #1f2a37;
  --f2-muted: #6b7280;
  --f2-line: #e5e7eb;
  --f2-primary: #0f766e;
  --f2-soft: #f0fdfa;
  padding: 12px 14px 28px;
  color: var(--f2-ink);
  font-size: var(--wp-font-size, 13px);
}
.hero {
  margin-bottom: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: linear-gradient(135deg, #f0fdfa 0%, #ecfeff 55%, #f8fafc 100%);
  border: 1px solid var(--f2-line);
}
.hero-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-title { margin: 0; font-size: 17px; font-weight: 650; }
.hero-sub { margin: 6px 0 0; color: var(--f2-muted); font-size: 13px; }
.guidance {
  margin-bottom: 10px;
  border-left: 3px solid var(--f2-primary);
  background: #ccfbf1;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance summary { cursor: pointer; font-weight: 500; color: var(--f2-primary); }
.guidance-body { margin-top: 8px; color: #4b5563; line-height: 1.6; }
.guidance-body p { margin: 2px 0; }
.obj-alert { margin-bottom: 12px; }
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search { width: 220px; }
.aging-sel { width: 110px; }
.muted { color: var(--f2-muted); font-size: 12px; }
.tiny { font-size: 12px; margin-left: 8px; }
.chip { display: inline-flex; }
.main-table { width: 100%; margin-bottom: 12px; }
.formula { border-bottom: 1px dashed #c0c4cc; }
.bad { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fef6e8; }
.summary-panel {
  margin: 12px 0 16px;
  padding: 12px 14px;
  border: 1px solid var(--f2-line);
  border-radius: 8px;
  background: var(--f2-soft);
}
.summary-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}
.summary-row .lab { min-width: 180px; color: #374151; }
.summary-row .val { font-weight: 600; font-variant-numeric: tabular-nums; }
.summary-row.net {
  border-top: 1px dashed var(--f2-line);
  margin-top: 4px;
  padding-top: 10px;
}
.summary-row.net .val { color: var(--f2-primary); font-size: 15px; }
.notes-panel { margin-top: 16px; }
.notes-panel h4 { margin: 0 0 10px; font-size: 14px; }
.note-block { margin-bottom: 10px; }
.note-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-weight: 500;
  color: #374151;
}
.conclusion { margin-top: 14px; }
</style>
