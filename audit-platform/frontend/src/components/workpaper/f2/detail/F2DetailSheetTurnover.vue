<template>
  <div class="f2-turnover">
    <header class="hero">
      <div class="hero-main">
        <h3 class="hero-title">周转材料 / 低值易耗品 / 包装物明细表 F2-5</h3>
        <el-tag size="small" effect="plain">科目 1403</el-tag>
      </div>
      <p class="hero-sub">三类分组编制 · 包装物四用途 · 收发存勾稽 · 库龄与摊销说明</p>
    </header>

    <details class="guidance">
      <summary>编制提示</summary>
      <div class="guidance-body">
        <p>1. 按模板骨架分三块：（一）周转材料、（二）低值易耗品、（三）包装物（四个用途子类）。</p>
        <p>2. 灰色列为自动计算：期末 = 期初 + 购进 − 发出；单价 = 金额 ÷ 数量；库龄合计须等于期末金额。</p>
        <p>3. 摊销采用五五、分次摊销时，金额按<strong>摊余价值</strong>列示并在审计说明中写明方法。</p>
        <p>4. 包装物小计汇总四用途；页尾合计 − 跌价准备 = 净额。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="obj-alert"
      title="审计目标：核实周转材料、低值易耗品及包装物明细期末余额的存在与准确，验证收发存与库龄完整性，评价摊销政策及跌价计提充分性。"
    />
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="obj-alert"
      title="提示：摊销方法采用五五、分次摊销法摊销时，金额按摊余价值列示，并作出说明。"
    />

    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="sheet.searchText.value"
          size="small"
          clearable
          placeholder="搜索编码 / 名称…"
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
          <el-radio-button value="movement">收发存</el-radio-button>
          <el-radio-button value="aging">库龄</el-radio-button>
          <el-radio-button value="full">完整</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <el-tag v-if="sheet.grandTotal.value.agingOk" type="success" size="small" effect="dark">库龄 OK</el-tag>
        <el-tag v-else type="danger" size="small">库龄与期末不匹配</el-tag>
        <el-tag v-if="sheet.agingMismatchCount.value" type="warning" size="small">
          {{ sheet.agingMismatchCount.value }} 行库龄异常
        </el-tag>
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-5"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip"><GtIndexChip value="wp:F2-5" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- （一）（二） -->
    <section
      v-for="sec in mainSections"
      :key="sec.key"
      class="group-card"
    >
      <div class="group-head">
        <h4>{{ sec.title }}</h4>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="sheet.addRow(sec.key)">
          + 新增
        </el-button>
      </div>
      <TurnoverLinesTable
        :rows="sheet.rowsOf(sec.key)"
        :view="sheet.activeView.value"
        :segments="sheet.segments.value"
        :is-readonly="isReadonly"
        @update="onUpdate"
        @aging="onAging"
        @remove="sheet.removeRow"
      />
      <div class="subtotal">
        <span class="sub-lab">小计</span>
        <template v-if="sheet.activeView.value !== 'aging'">
          <span class="sub-item">购进 {{ fmtAmt(sheet.groupTotals.value[sec.key].increaseAmt) }}</span>
          <span class="sub-item">发出 {{ fmtAmt(sheet.groupTotals.value[sec.key].decreaseAmt) }}</span>
        </template>
        <span class="sub-item strong">期末 {{ fmtAmt(sheet.groupTotals.value[sec.key].closingAmt) }}</span>
        <span
          v-if="sheet.activeView.value !== 'movement'"
          class="sub-item"
          :class="sheet.groupTotals.value[sec.key].agingOk ? 'ok' : 'bad'"
        >库龄 {{ fmtAmt(sheet.groupTotals.value[sec.key].agingTotal) }}</span>
      </div>
    </section>

    <!-- （三）包装物 -->
    <section class="group-card packaging">
      <div class="group-head">
        <h4>（三）包装物</h4>
      </div>
      <div v-for="g in packagingGroups" :key="g.key" class="pack-block">
        <div class="pack-head">
          <span class="pack-title">{{ g.title }}</span>
          <el-button size="small" text type="primary" :disabled="isReadonly" @click="sheet.addRow(g.key)">
            + 明细
          </el-button>
        </div>
        <TurnoverLinesTable
          :rows="sheet.rowsOf(g.key)"
          :view="sheet.activeView.value"
          :segments="sheet.segments.value"
          :is-readonly="isReadonly"
          @update="onUpdate"
          @aging="onAging"
          @remove="sheet.removeRow"
        />
        <div class="subtotal soft">
          <span class="sub-lab">{{ g.categoryLabel }}</span>
          <span class="sub-item strong">期末 {{ fmtAmt(sheet.groupTotals.value[g.key].closingAmt) }}</span>
        </div>
      </div>
      <div class="subtotal emph">
        <span class="sub-lab">包装物小计</span>
        <template v-if="sheet.activeView.value !== 'aging'">
          <span class="sub-item">购进 {{ fmtAmt(sheet.packagingTotal.value.increaseAmt) }}</span>
          <span class="sub-item">发出 {{ fmtAmt(sheet.packagingTotal.value.decreaseAmt) }}</span>
        </template>
        <span class="sub-item strong">期末 {{ fmtAmt(sheet.packagingTotal.value.closingAmt) }}</span>
        <span
          v-if="sheet.activeView.value !== 'movement'"
          class="sub-item"
          :class="sheet.packagingTotal.value.agingOk ? 'ok' : 'bad'"
        >库龄 {{ fmtAmt(sheet.packagingTotal.value.agingTotal) }}</span>
      </div>
    </section>

    <section class="summary-panel">
      <div class="summary-row">
        <span class="lab">合计（期末金额）</span>
        <span class="val">{{ fmtAmt(sheet.grandTotal.value.closingAmt) }}</span>
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
        <span class="lab">周转材料/低值易耗品/包装物净额</span>
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
  useF2DetailTurnover,
  F2_TURNOVER_GROUPS,
  type F2TurnoverRow,
} from '../../composables/useF2DetailTurnover'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import TurnoverLinesTable from './TurnoverLinesTable.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { AgingPreset } from '@/composables/useAgingConfig'
import type { F2DetailNotePack } from '../../composables/useF2DetailSheet'

const props = defineProps<{
  wpId: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

const sheet = useF2DetailTurnover({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const mainSections = F2_TURNOVER_GROUPS.filter((g) => g.section === 'A' || g.section === 'B')
const packagingGroups = F2_TURNOVER_GROUPS.filter((g) => g.section === 'P')

const { aiAvailable, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)
const aiBusyKey = ref<string | null>(null)

const noteFields: Array<{
  key: string
  packKey: keyof F2DetailNotePack
  section: F2AiSection
  label: string
  placeholder: string
}> = [
  { key: 'valuation', packKey: 'valuationMethod', section: 'detail-valuation', label: '1. 摊销方法说明：', placeholder: '摊销方法说明：' },
  { key: 'change', packKey: 'significantChange', section: 'detail-change', label: '2. 本期重大变动原因：', placeholder: '周转材料/低值易耗品/包装物本期发生重大变动的原因：' },
  { key: 'longAging', packKey: 'longAgingReason', section: 'detail-long-aging', label: '3. 库龄较长的原因：', placeholder: '周转材料/低值易耗品/包装物——库龄较长的原因：' },
  { key: 'impairment', packKey: 'impairmentReason', section: 'detail-impairment', label: '4. 计提跌价准备的主要项目及原因：', placeholder: '计提跌价准备的主要项目及原因：' },
]

async function generateNote(f: (typeof noteFields)[number]) {
  aiBusyKey.value = f.key
  try {
    const text = await generateAndConfirm(
      f.section,
      sheet.notePack.value[f.packKey],
      {
        sheetCode: 'F2-5',
        closingAmt: sheet.grandTotal.value.closingAmt,
        netAmt: sheet.netAmt.value,
        agingOk: sheet.grandTotal.value.agingOk,
      },
      `AI 生成 · F2-5 ${f.label}`,
    )
    if (text) sheet.persistNotePack({ [f.packKey]: text })
  } finally {
    aiBusyKey.value = null
  }
}

function fmtAmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onUpdate(payload: { id: string; patch: Partial<F2TurnoverRow> }) {
  sheet.updateRow(payload.id, payload.patch)
}
function onAging(payload: { id: string; key: string; value: number }) {
  sheet.updateAgingCell(payload.id, payload.key, payload.value)
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
      : ['1年以内（含1年）', '1至2年（含2年）', '2至3年（含3年）', '3年以上']
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
.f2-turnover {
  --f2-ink: #2c2140;
  --f2-muted: #7a6f8a;
  --f2-line: #ebe4f2;
  --f2-primary: #6b3fa0;
  --f2-soft: #f8f5fc;
  padding: 12px 14px 28px;
  color: var(--f2-ink);
}
.hero {
  margin-bottom: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #faf7fd 0%, #f3eef8 55%, #eef6f4 100%);
  border: 1px solid var(--f2-line);
}
.hero-main { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-title { margin: 0; font-size: 18px; font-weight: 650; letter-spacing: 0.02em; }
.hero-sub { margin: 6px 0 0; color: var(--f2-muted); font-size: 13px; }
.guidance {
  margin-bottom: 10px;
  border: 1px solid var(--f2-line);
  border-radius: 10px;
  padding: 8px 12px;
  background: #fff;
}
.guidance summary { cursor: pointer; font-weight: 600; color: var(--f2-primary); }
.guidance-body { margin-top: 8px; font-size: 13px; color: #564866; line-height: 1.55; }
.guidance-body p { margin: 0 0 4px; }
.obj-alert { margin-bottom: 8px; }
.toolbar {
  display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  align-items: center; margin: 10px 0 14px; padding: 10px 12px;
  background: #fff; border: 1px solid var(--f2-line); border-radius: 10px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search { width: 180px; }
.aging-sel { width: 110px; }
.muted { color: var(--f2-muted); font-size: 12px; }
.chip { display: inline-flex; }

.group-card {
  margin-bottom: 14px;
  border: 1px solid var(--f2-line);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(45, 25, 70, 0.04);
  overflow: hidden;
}
.group-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; background: var(--f2-soft); border-bottom: 1px solid var(--f2-line);
}
.group-head h4 { margin: 0; font-size: 15px; font-weight: 650; }
.packaging .group-head { background: linear-gradient(90deg, #f6f2fb, #eef7f4); }
.pack-block { padding: 8px 12px 4px; border-top: 1px dashed #ece6f3; }
.pack-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.pack-title { font-size: 13px; color: #4a3b5c; font-weight: 600; }

.subtotal {
  display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
  padding: 8px 14px 10px; background: #fcfbfe; border-top: 1px solid var(--f2-line);
  font-size: 13px;
}
.subtotal.soft { background: #fff; }
.subtotal.emph {
  background: linear-gradient(90deg, #f3eef9, #eef6f3);
  font-weight: 600;
}
.sub-lab { min-width: 88px; color: var(--f2-primary); font-weight: 650; }
.sub-item { color: #564866; font-variant-numeric: tabular-nums; }
.sub-item.strong { color: var(--f2-ink); font-weight: 650; }
.sub-item.ok { color: #2f7d4a; }
.sub-item.bad { color: #c45656; }

.summary-panel {
  margin: 8px 0 16px; padding: 14px 16px; border-radius: 12px;
  border: 1px solid var(--f2-line);
  background: linear-gradient(135deg, #faf8fc, #f5f7fa);
}
.summary-row {
  display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
}
.summary-row .lab { min-width: 220px; font-weight: 600; }
.summary-row .val { font-size: 16px; font-variant-numeric: tabular-nums; }
.summary-row.net .val { color: var(--f2-primary); font-weight: 700; font-size: 18px; }

.notes-panel {
  padding: 14px 16px; border-radius: 12px; border: 1px solid var(--f2-line); background: #fff;
}
.notes-panel h4 { margin: 0 0 10px; }
.note-block { margin-bottom: 10px; }
.note-label {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 4px; font-size: 13px; font-weight: 600;
}
</style>
