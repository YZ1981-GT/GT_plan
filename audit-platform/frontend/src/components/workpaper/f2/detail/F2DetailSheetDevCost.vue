<template>
  <div class="f2-dev-cost">
    <header class="hero">
      <div class="hero-main">
        <h3 class="hero-title">开发成本明细表 F2-11</h3>
        <el-tag size="small" effect="plain">科目 1409</el-tag>
      </div>
      <p class="hero-sub">（一）原值 ·（二）跌价准备 ·（三）净值 · 未审/调整/审定 · 库龄</p>
    </header>

    <details class="guidance">
      <summary>编制提示</summary>
      <div class="guidance-body">
        <p>1. 按项目列示开发成本：建筑面积、开工/预计竣工、预计总投资；原值分未审数、账项/重分类调整、审定数。</p>
        <p>2. 灰色列为自动计算：未审期末 = 期初 + 增加 − 减少；审定增加/减少 = 未审 + 账项 + 重分类；审定期末 = 审定期初 + 审定增加 − 审定减少。</p>
        <p>3. 跌价准备同结构勾稽；净值 = 原值 − 跌价（未审/审定分列）。库龄超过一年的项目须在审计说明中披露。</p>
        <p>4. 可用「原值 / 跌价 / 净值」切换视图。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="obj-alert"
      title="审计目标：核实开发成本归集与结转，验证调整审定及跌价充分性，关注长期开发成本与资本化利息真实性。"
    />

    <div class="toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">新增项目</el-button>
        <el-input
          v-model="sheet.searchText.value"
          size="small"
          clearable
          placeholder="搜索项目名称…"
          class="search"
        />
        <el-radio-group v-model="sheet.activeView.value" size="small">
          <el-radio-button value="gross">（一）原值</el-radio-button>
          <el-radio-button value="impairment">（二）跌价</el-radio-button>
          <el-radio-button value="net">（三）净值</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-11"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip"><GtIndexChip value="wp:F2-11" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ sheet.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="sheet.filteredRows.value" border size="small" class="main-table" max-height="520">
      <el-table-column type="index" label="序号" width="56" fixed />
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
      <el-table-column label="总建筑面积/万㎡" width="120">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.totalArea"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => sheet.updateRow(row.id, { totalArea: v ?? 0 })"
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
      <el-table-column label="预计总投资" width="110">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.estimatedInvestment"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => sheet.updateRow(row.id, { estimatedInvestment: v ?? 0 })"
          />
        </template>
      </el-table-column>

      <template v-if="sheet.activeView.value === 'gross'">
        <el-table-column label="未审数" align="center">
          <el-table-column label="期初余额" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.unaudOpen"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { unaudOpen: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.unaudInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { unaudInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.unaudDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { unaudDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.unaudClose) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="账项调整" align="center">
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.adjAcctInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { adjAcctInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.adjAcctDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { adjAcctDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="重分类调整" align="center">
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.adjReclassInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { adjReclassInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.adjReclassDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { adjReclassDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="审定数" align="center">
          <el-table-column label="期初余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.audOpen) }}</span></template>
          </el-table-column>
          <el-table-column label="本期增加" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.audInc) }}</span></template>
          </el-table-column>
          <el-table-column label="本期减少" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.audDec) }}</span></template>
          </el-table-column>
          <el-table-column label="期末余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.audClose) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="库龄(年)" width="88">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.agingYears === '' ? undefined : Number(row.agingYears)"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              @change="(v: number | undefined) => sheet.updateRow(row.id, { agingYears: v ?? '' })"
            />
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
      </template>

      <template v-else-if="sheet.activeView.value === 'impairment'">
        <el-table-column label="未审数" align="center">
          <el-table-column label="期初余额" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impUnaudOpen"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impUnaudOpen: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impUnaudInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impUnaudInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impUnaudDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impUnaudDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impUnaudClose) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="账项调整" align="center">
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impAdjAcctInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impAdjAcctInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impAdjAcctDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impAdjAcctDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="重分类调整" align="center">
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impAdjReclassInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impAdjReclassInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impAdjReclassDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impAdjReclassDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="审定数" align="center">
          <el-table-column label="期初余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudOpen) }}</span></template>
          </el-table-column>
          <el-table-column label="本期增加" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudInc) }}</span></template>
          </el-table-column>
          <el-table-column label="本期减少" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudDec) }}</span></template>
          </el-table-column>
          <el-table-column label="期末余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudClose) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="备注" width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.impRemark"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => sheet.updateRow(row.id, { impRemark: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100">
          <template #default="{ row }">
            <el-input
              :model-value="row.impIndex"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => sheet.updateRow(row.id, { impIndex: v })"
            />
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="未审数" align="center">
          <el-table-column label="期初数" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netUnaudOpen) }}</span></template>
          </el-table-column>
          <el-table-column label="期末数" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netUnaudClose) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="审定数" align="center">
          <el-table-column label="期初数" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netAudOpen) }}</span></template>
          </el-table-column>
          <el-table-column label="期末数" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netAudClose) }}</span></template>
          </el-table-column>
        </el-table-column>
      </template>

      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="danger" :disabled="isReadonly" @click="sheet.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <section class="summary-panel">
      <div class="summary-row">
        <span class="lab">原值未审期末</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.unaudClose) }}</span>
        <span class="muted tiny">审定 {{ fmtAmt(sheet.totals.value.audClose) }}</span>
      </div>
      <div class="summary-row">
        <span class="lab">跌价未审期末</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.impUnaudClose) }}</span>
        <span class="muted tiny">审定 {{ fmtAmt(sheet.totals.value.impAudClose) }}</span>
      </div>
      <div class="summary-row net">
        <span class="lab">净值期末（原值−跌价）</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.netUnaudClose) }}</span>
        <span class="muted tiny">审定 {{ fmtAmt(sheet.totals.value.netAudClose) }}</span>
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
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { inject, ref, toRef, type Ref } from 'vue'
import { useF2DevCostSheet, DEV_COST_QUALITY } from '../../composables/useF2DevCostSheet'
import { useF2AiGenerate, type F2AiSection } from '../../composables/useF2AiGenerate'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'

const QUALITY = DEV_COST_QUALITY

const props = defineProps<{
  wpId: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sheet = useF2DevCostSheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const { aiAvailable, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)
const aiBusyKey = ref<string | null>(null)

type NotePackKey = 'costMethod' | 'significantChange' | 'longTermReason' | 'capitalizedInterest'

const noteFields: Array<{
  key: string
  packKey: NotePackKey
  section: F2AiSection
  label: string
  placeholder: string
  noteHint?: string
}> = [
  {
    key: 'method',
    packKey: 'costMethod',
    section: 'detail-valuation',
    label: '1. 成本计算方法说明：',
    placeholder: '成本计算方法说明：',
  },
  {
    key: 'change',
    packKey: 'significantChange',
    section: 'detail-change',
    label: '2. 本期重大变动原因：',
    placeholder: '开发成本本期发生重大变动的原因：',
  },
  {
    key: 'long',
    packKey: 'longTermReason',
    section: 'detail-long-aging',
    label: '3. 长期开发成本（一年以上）说明：',
    placeholder: '长期开发成本（一年以上）说明：',
  },
  {
    key: 'int',
    packKey: 'capitalizedInterest',
    section: 'detail-change',
    label: '4. 资本化利息来源及真实性：',
    placeholder: '资本化利息的主要来源及真实性：',
    noteHint: '资本化利息来源及真实性',
  },
]

async function generateNote(f: (typeof noteFields)[number]) {
  aiBusyKey.value = f.key
  try {
    const text = await generateAndConfirm(
      f.section,
      sheet.notePack.value[f.packKey],
      {
        sheetCode: 'F2-11',
        sheetName: '开发成本',
        noteHint: f.noteHint ?? f.label,
        unaudClose: sheet.totals.value.unaudClose,
        netUnaudClose: sheet.totals.value.netUnaudClose,
      },
      `AI 生成 · F2-11 ${f.label}`,
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
        sheetCode: 'F2-11',
        sheetName: '开发成本',
        unaudClose: sheet.totals.value.unaudClose,
        netUnaudClose: sheet.totals.value.netUnaudClose,
      },
      'AI · F2-11 审计结论',
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
.f2-dev-cost { padding: 8px 4px 24px; }
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
.chip { display: inline-flex; }
.main-table :deep(.auto-calc-col) { background: #faf8fc; }
.formula { color: #606266; font-variant-numeric: tabular-nums; }
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
