<template>
  <div class="g10-fv" data-testid="g10-fv-test">
    <div class="methodology">
      公允价值三层次：Level1—活跃市场相同负债报价；Level2—可观察输入值；Level3—不可观察输入值(估值技术)。
      Level3 时估值技术与不可观察输入值描述必填。
    </div>
    <div class="toolbar">
      <h3>G10-5 公允价值测试</h3>
      <G10ImportExportDropdown :wp-id="wpId" sheet="G10-5" @imported="emit('imported')" />
      <el-button v-if="!isReadonly" size="small" type="primary" @click="fv.addRow()">+ 新增</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g10-fv-sync-detail"
        @click="fv.syncFromDetail()"
      >
        ↓ 从 G10-2 带入
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g10-fv-push-detail"
        @click="fv.pushToDetail()"
      >
        ↑ 回写 G10-2
      </el-button>
      <el-button
        v-if="jumpToSection"
        size="small"
        plain
        data-testid="g10-fv-goto-detail"
        @click="jumpToSection('G10-2')"
      >
        → G10-2 明细
      </el-button>
      <el-button
        v-if="jumpToSection"
        size="small"
        plain
        data-testid="g10-fv-goto-l3"
        @click="jumpToSection('G10-6')"
      >
        → G10-6 L3调节
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="fv.validateLevel3()">Level3校验</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :loading="fv.procedureMarking.value"
        :disabled="!fv.rows.value.length"
        data-testid="g10-fv-mark-procedure"
        @click="onMarkProcedure"
      >
        {{ fv.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 公允测试' }}
      </el-button>
      <el-button
        v-if="!isReadonly && fv.diffCount.value > 0"
        size="small"
        type="warning"
        plain
        data-testid="g10-fv-push-adj"
        @click="onPushDiff"
      >
        推送差异→G10-3
        <template v-if="fv.materialDiffCount.value">（B15:{{ fv.materialDiffCount.value }}）</template>
      </el-button>
      <el-button
        v-if="!isReadonly && fv.diffCount.value > 0"
        size="small"
        type="warning"
        plain
        :loading="pushingG13"
        :disabled="!projectId || pushingG13"
        data-testid="g10-fv-push-g13"
        @click="onPushG13"
      >
        推送差异→G13-3
      </el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:G10-3" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:G13-3" /></span>
      <GtReviewTrigger section-id="G10-5-fv-test" />
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实交易性金融负债期末公允价值计量的准确性，验证公允价值层次划分与估值技术的恰当性，Level3 不可观察输入值的充分披露。" />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G10-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-5" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-6" /></span>
        <el-tag size="small" type="info">共 {{ fv.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-alert
      v-if="fv.hasCrossRefIssue.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g10-fv-detail-cross"
      :title="`审定 FV 合计 ${fmt(fv.totals.value.closingAuditedFV)} 与 G10-2 审定合计 ${fmt(fv.detailClosingAdjustedTotal.value)} 差异 ${fmt(fv.crossRefVariance.value)}`"
    />

    <el-alert v-if="fv.level3Violations.value.length" type="warning" :closable="false" class="l3-alert">
      Level3 必填缺失：{{ fv.level3Violations.value.map(v => v.liabilityName).join('、') }}
    </el-alert>

    <div
      v-if="fv.diffWarningLevel.value !== 'none' || fv.exceedsB15.value"
      class="diff-warn-bar"
      :class="(fv.diffWarningLevel.value === 'hard' || fv.exceedsB15.value) ? 'is-hard' : 'is-soft'"
      data-testid="g10-fv-diff-warn"
    >
      <div class="diff-warn-head">
        <span>{{ (fv.diffWarningLevel.value === 'hard' || fv.exceedsB15.value) ? '差异偏高' : '差异关注' }}</span>
        <span>相对未审合计 {{ fv.diffRatioPct.value }}%</span>
        <span>差异合计 {{ fmt(fv.totals.value.fairValueDiff) }}</span>
        <span v-if="fv.performanceMateriality.value > 0">
          B15 {{ fmt(fv.performanceMateriality.value) }}
          <template v-if="fv.exceedsB15.value">（已超）</template>
        </span>
        <span v-else-if="fv.pmLoading.value">B15 加载中…</span>
        <el-button
          v-else-if="projectId && !isReadonly"
          link
          type="primary"
          size="small"
          @click="fv.loadPerformanceMateriality()"
        >拉取 B15</el-button>
      </div>
      <p class="diff-warn-hint">
        <template v-if="fv.exceedsB15.value">
          差异合计超过实际执行重要性（B15），请追查原因并考虑推送 G10-3 调整分录。
        </template>
        <template v-else-if="fv.diffWarningLevel.value === 'hard'">
          差异≥未审合计 20%，请追查原因并考虑推送 G10-3 调整分录。
        </template>
        <template v-else>
          差异≥未审合计 5%，请核实数量/单价并考虑推送 G10-3。
        </template>
      </p>
    </div>

    <el-segmented v-model="fv.activeTab.value" :options="tabOptions" size="small" />

    <el-table :data="fv.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="440"
      highlight-current-row @current-change="(r: any) => r && (fv.selectedRowId.value = r.rowId)">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="负债名称" min-width="120" fixed>
        <template #default="{ row }">
          <div class="name-cell">
            <el-input v-model="row.liabilityName" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'liabilityName', v)" />
            <el-tag
              v-if="fv.detailLinkByRowId.value.get(row.rowId)"
              size="small"
              :type="Math.abs(fv.detailLinkByRowId.value.get(row.rowId)!.variance) > 0.01 ? 'warning' : 'success'"
              class="link-tag"
            >
              G10-2
            </el-tag>
          </div>
        </template>
      </el-table-column>

      <template v-if="fv.activeTab.value === 'basic'">
        <el-table-column label="初始日期" width="108">
          <template #default="{ row }">
            <el-input v-model="row.initialDate" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'initialDate', v)" />
          </template>
        </el-table-column>
        <el-table-column label="未审数量" width="92" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.closingUnadjustedQty" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingUnadjustedQty', v)" />
          </template>
        </el-table-column>
        <el-table-column label="未审单价" width="92" align="right">
          <template #default="{ row }">
            <WpAmountInput v-model="row.closingUnadjustedPrice" size="small" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingUnadjustedPrice', v)" />
          </template>
        </el-table-column>
        <el-table-column label="未审FV" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ fmt(row.closingUnadjustedFV) }}</span></template>
        </el-table-column>
        <el-table-column label="审定数量" width="92" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.closingAuditedQty" size="small" :controls="false" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingAuditedQty', v)" />
          </template>
        </el-table-column>
        <el-table-column label="审定单价" width="92" align="right">
          <template #default="{ row }">
            <WpAmountInput v-model="row.closingAuditedPrice" size="small" :disabled="isReadonly"
              style="width:100%" @change="(v: number) => fv.updateCell(row.rowId, 'closingAuditedPrice', v)" />
          </template>
        </el-table-column>
        <el-table-column label="审定FV" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ fmt(row.closingAuditedFV) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" width="96" align="right">
          <template #default="{ row }">
            <span :class="{ 'diff-warn': Math.abs(row.fairValueDiff) > 0.01 }">{{ fmt(row.fairValueDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="层次" width="100">
          <template #default="{ row }">
            <el-select v-model="row.fairValueLevel" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'fairValueLevel', v)">
              <el-option v-for="l in fv.G10_FV_LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
            </el-select>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="估值方法" width="110">
          <template #default="{ row }">
            <el-select v-model="row.valuationMethod" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationMethod', v)">
              <el-option v-for="m in fv.G10_VALUATION_METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致" width="96">
          <template #default="{ row }">
            <el-select v-model="row.methodConsistentWithPrior" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'methodConsistentWithPrior', v)">
              <el-option label="是" value="yes" /><el-option label="否" value="no" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="来源机构" width="100">
          <template #default="{ row }">
            <el-input v-model="row.valuationSource" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationSource', v)" />
          </template>
        </el-table-column>
        <el-table-column label="输入值来源" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.inputSourceAndAdjustment" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
              @change="() => fv.updateCell(row.rowId, 'inputSourceAndAdjustment', row.inputSourceAndAdjustment)" />
          </template>
        </el-table-column>
        <el-table-column label="估值技术" width="100">
          <template #default="{ row }">
            <el-input v-model="row.valuationTechnique" size="small" :disabled="isReadonly"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.valuationTechnique }"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationTechnique', v)" />
          </template>
        </el-table-column>
        <el-table-column label="不可观察输入值" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.unobservableInputDesc" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.unobservableInputDesc }"
              @change="() => fv.updateCell(row.rowId, 'unobservableInputDesc', row.unobservableInputDesc)" />
          </template>
        </el-table-column>
        <el-table-column label="数值" width="88">
          <template #default="{ row }">
            <el-input v-model="row.unobservableInputValue" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'unobservableInputValue', v)" />
          </template>
        </el-table-column>
        <el-table-column label="敏感性分析" min-width="100">
          <template #default="{ row }">
            <el-input v-model="row.sensitivityAnalysis" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
              @change="() => fv.updateCell(row.rowId, 'sensitivityAnalysis', row.sensitivityAnalysis)" />
          </template>
        </el-table-column>
        <el-table-column label="索引" width="72">
          <template #default="{ row }">
            <el-input v-model="row.valuationDocIndex" size="small" :disabled="isReadonly"
              @change="(v: string) => fv.updateCell(row.rowId, 'valuationDocIndex', v)" />
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="fv.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusionProxy"
      note-ai-section="fair-value-note"
      conclusion-ai-section="fair-value-conclusion"
      note-placeholder="填写审计说明：可概述公允价值测试的程序执行情况、估值方法与来源核实、Level3 输入值合理性及与 G10-6 调节表勾稽结果。"
      note-hint="覆盖公允层级划分与估值来源可靠性。"
      conclusion-placeholder="填写审计结论：公允价值计量是否准确、层次划分是否恰当。"
      :related-context="{
        行数: fv.rows.value.length,
        Level3缺失: fv.level3Violations.value.length,
        与G102差异: fv.crossRefVariance.value,
      }"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>依据 CAS 39《公允价值计量》，按输入值可观察程度划分三层次；Level3 使用不可观察输入值时须记录估值技术、关键参数及敏感性分析。</p>
        <p>审定FV = 审定数量 × 审定单价（无数量时直接填 FV 金额）；可与 G10-2 按项目名称逐行勾稽。</p>
        <p>Level3 负债的期末公允价值变动应与 G10-6 第三层次调节表勾稽。</p>
        <p>超 B15 差异可「推送差异→G10-3」（FVTPL：Dr 6101 / Cr 2101），并自动回写 G10-1 期末账项调整；损益侧亦可「推送差异→G13-3」写入公允价值变动收益调整分录。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, toRef, watch, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { useG10FairValueTest } from '../../composables/useG10FairValueTest'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import { G10A_FV_PROGRAM_NOS, G10A_PROCEDURE_SHEET } from '../../composables/g10FvCrossHelpers'
import { pushSourceFvDiffToG13, G13_FV_DIFF_THRESHOLD } from '../../composables/g13FvCrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const projectId = computed(() => props.projectId || '')
const pushingG13 = ref(false)

const fv = useG10FairValueTest({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || ''),
})

async function onPushDiff() {
  await fv.pushDiffToAdjustment()
}

async function onPushG13() {
  if (!projectId.value) {
    ElMessage.warning('缺少项目 ID，无法推送 G13-3')
    return
  }
  const targets = fv.rows.value.filter((r) => Math.abs(r.fairValueDiff) > G13_FV_DIFF_THRESHOLD)
  if (!targets.length) {
    ElMessage.info('无可推送差异')
    return
  }
  pushingG13.value = true
  try {
    const result = await pushSourceFvDiffToG13({
      projectId: projectId.value,
      source: 'G10-5',
      items: targets.map((r) => ({
        description: `G10-5 公允测试差异：${r.liabilityName || '未命名'}`,
        amount: r.fairValueDiff,
        belongAccount: 'G10',
        indexRef: 'G10-5',
        nameKey: r.liabilityName || r.rowId,
        remark: `审定 ${r.closingAuditedFV} − 未审 ${r.closingUnadjustedFV}`,
      })),
    })
    if (result.ok) ElMessage.success(result.message)
    else ElMessage.warning(result.message)
  } finally {
    pushingG13.value = false
  }
}

async function onMarkProcedure() {
  const n = await fv.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G10A_FV_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `公允价值程序（步骤 ${[...G10A_FV_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_FV_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

const NOTE_KEY = 'G10-5-fv-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})

const conclusionProxy = computed({
  get: () => fv.conclusion.value,
  set: (v: string) => fv.updateConclusion(v),
})

const tabOptions = [
  { label: '基础+审定', value: 'basic' },
  { label: '估值详情', value: 'valuation' },
]

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g10-fv { font-size: var(--wp-font-size, 13px); }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.formula { border-bottom: 1px dashed #909399; }
.l3-alert { margin-bottom: 8px; }
.cross-alert { margin-bottom: 8px; }
.name-cell { display: flex; align-items: center; gap: 4px; }
.link-tag { flex-shrink: 0; }
:deep(.l3-required .el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.diff-warn-bar {
  margin-bottom: 8px; padding: 8px 12px; border-radius: 4px; font-size: 12px;
  border: 1px solid #faecd8; background: #fdf6ec;
}
.diff-warn-bar.is-hard { border-color: #fde2e2; background: #fef0f0; }
.diff-warn-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; font-weight: 600; }
.diff-warn-hint { margin: 6px 0 0; color: #606266; font-weight: normal; }
</style>
