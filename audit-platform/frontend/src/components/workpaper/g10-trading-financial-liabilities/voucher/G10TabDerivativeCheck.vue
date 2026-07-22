<template>
  <div class="g10-derivative" data-testid="g10-derivative-check">
    <div class="methodology">
      衍生金融工具五要素(CAS22)：价值随特定变量变动 · 不要求/极少初始净投资 · 未来日期结算 · 固定或可确定金额交换 · 可净额结算
    </div>
    <div class="toolbar">
      <h3>G10-8 衍生金融工具核查（{{ dc.rows.value.length }} 行 · 5 区段）</h3>
      <G10ImportExportDropdown :wp-id="wpId" sheet="G10-8" @imported="emit('imported')" />
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g10-derivative-sync-detail"
        @click="dc.syncFromDetail()"
      >
        ↓ 从 G10-2 带入
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g10-derivative-push-detail"
        @click="dc.pushToDetail()"
      >
        ↑ 回写 G10-2
      </el-button>
      <el-button
        v-if="jumpToSection"
        size="small"
        plain
        data-testid="g10-derivative-goto-detail"
        @click="jumpToSection('G10-2')"
      >
        → G10-2 明细
      </el-button>
      <el-button
        v-if="!isReadonly && dc.nonCompliantCount.value > 0"
        size="small"
        type="warning"
        plain
        data-testid="g10-derivative-push-adj"
        @click="onPushIssues"
      >
        推送不合规→G10-3（{{ dc.nonCompliantCount.value }}）
      </el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:G10-3" /></span>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :loading="dc.procedureMarking.value"
        data-testid="g10-derivative-mark-procedure"
        @click="onMarkProcedure"
      >
        {{ dc.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 衍生程序' }}
      </el-button>
      <el-tag v-if="dc.linkedDetailCount.value" size="small" type="success">
        已链 G10-2 {{ dc.linkedDetailCount.value }}
      </el-tag>
      <el-tag v-if="dc.unmatchedDerivativeDetailCount.value" size="small" type="warning">
        未链衍生行 {{ dc.unmatchedDerivativeDetailCount.value }}
      </el-tag>
      <el-tag v-if="dc.missingCompliance.value.length" type="danger" size="small">
        待填合规 {{ dc.missingCompliance.value.length }} 行
      </el-tag>
      <GtReviewTrigger section-id="G10-8-derivative" />
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实衍生金融工具的确认与计量是否符合 CAS 22 定义（五要素），验证嵌入衍生的拆分判断、公允价值计量及套期关系认定的恰当性与披露完整性。" />

    <div class="wizard-card" data-testid="g10-derivative-wizard">
      <div class="wizard-head">
        <h4>衍生工具识别向导（A→E）</h4>
        <el-tag size="small" :type="wizardTagType">{{ dc.wizardEval.value.summary }}</el-tag>
      </div>
      <el-steps :active="dc.wizardStep.value" finish-status="success" simple class="wizard-steps">
        <el-step title="A 审阅合同" />
        <el-step title="B 变量变动" />
        <el-step title="C 嵌入衍生" />
        <el-step title="D 拆分条件" />
        <el-step title="E 计量方式" />
      </el-steps>

      <div v-if="dc.wizardStep.value === 0" class="wizard-panel">
        <el-input
          v-model="wizardContractNote"
          type="textarea"
          :rows="3"
          :disabled="isReadonly"
          placeholder="审阅主合同条款摘要（贷款/投资/存款/混合工具等）"
        />
      </div>

      <div v-else-if="dc.wizardStep.value === 1" class="wizard-panel">
        <p class="wizard-hint">B. 合同现金流是否随下列变量变动？（全部为「否」→ 无衍生）</p>
        <div class="var-grid">
          <div v-for="item in G10_DERIVATIVE_VARIABLE_CHECKS" :key="item.key" class="var-item">
            <span>{{ item.label }}</span>
            <el-radio-group
              :model-value="dc.wizard.value.variableAnswers[item.key] ?? ''"
              size="small"
              :disabled="isReadonly"
              @update:model-value="(v: string | number | boolean | undefined) => dc.updateWizardVariable(item.key, String(v) as G10YesNo)"
            >
              <el-radio-button value="yes">是</el-radio-button>
              <el-radio-button value="no">否</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </div>

      <div v-else-if="dc.wizardStep.value === 2" class="wizard-panel">
        <div class="yn-row">
          <span>C1. 嵌入衍生能否从主合同单独转让？</span>
          <el-radio-group
            :model-value="dc.wizard.value.embeddedSeparateTransfer"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string | number | boolean | undefined) => dc.updateWizard({ embeddedSeparateTransfer: String(v) as G10YesNo })"
          >
            <el-radio-button value="yes">是</el-radio-button>
            <el-radio-button value="no">否</el-radio-button>
          </el-radio-group>
        </div>
        <div class="yn-row">
          <span>C2. 嵌入衍生与主合同是否同一交易对手？</span>
          <el-radio-group
            :model-value="dc.wizard.value.embeddedSameCounterparty"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string | number | boolean | undefined) => dc.updateWizard({ embeddedSameCounterparty: String(v) as G10YesNo })"
          >
            <el-radio-button value="yes">是</el-radio-button>
            <el-radio-button value="no">否</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <div v-else-if="dc.wizardStep.value === 3" class="wizard-panel">
        <p class="wizard-hint">D. 须同时满足三项方可拆分</p>
        <div class="yn-row">
          <span>D1. 经济特征/风险与主合同不紧密相关</span>
          <el-radio-group
            :model-value="dc.wizard.value.d1NotCloselyRelated"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string | number | boolean | undefined) => dc.updateWizard({ d1NotCloselyRelated: String(v) as G10YesNo })"
          >
            <el-radio-button value="yes">是</el-radio-button>
            <el-radio-button value="no">否</el-radio-button>
          </el-radio-group>
        </div>
        <div class="yn-row">
          <span>D2. 与主合同条款相同的单独工具符合衍生定义</span>
          <el-radio-group
            :model-value="dc.wizard.value.d2StandaloneDerivative"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string | number | boolean | undefined) => dc.updateWizard({ d2StandaloneDerivative: String(v) as G10YesNo })"
          >
            <el-radio-button value="yes">是</el-radio-button>
            <el-radio-button value="no">否</el-radio-button>
          </el-radio-group>
        </div>
        <div class="yn-row">
          <span>D3. 混合合同不是以 FVTPL 计量</span>
          <el-radio-group
            :model-value="dc.wizard.value.d3NotFvtpl"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string | number | boolean | undefined) => dc.updateWizard({ d3NotFvtpl: String(v) as G10YesNo })"
          >
            <el-radio-button value="yes">是</el-radio-button>
            <el-radio-button value="no">否</el-radio-button>
          </el-radio-group>
        </div>
      </div>

      <div v-else class="wizard-panel">
        <div class="yn-row">
          <span>E. 能否单独可靠计量嵌入衍生公允价值？</span>
          <el-radio-group
            :model-value="dc.wizard.value.canMeasureSeparately"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string | number | boolean | undefined) => dc.updateWizard({ canMeasureSeparately: String(v) as G10YesNo })"
          >
            <el-radio-button value="yes">能</el-radio-button>
            <el-radio-button value="no">不能</el-radio-button>
          </el-radio-group>
        </div>
        <div class="expert-grid">
          <label>
            <span>专家资质索引（C21/C22）</span>
            <el-input
              v-model="wizardExpertQualIndex"
              size="small"
              :disabled="isReadonly"
              placeholder="索引号"
            />
          </label>
          <label>
            <span>利用专家工作索引（C32/C33）</span>
            <el-input
              v-model="wizardExpertWorkIndex"
              size="small"
              :disabled="isReadonly"
              placeholder="索引号"
            />
          </label>
        </div>
      </div>

      <div class="wizard-actions">
        <el-button size="small" :disabled="dc.wizardStep.value <= 0" @click="dc.setWizardStep(dc.wizardStep.value - 1)">上一步</el-button>
        <el-button size="small" :disabled="dc.wizardStep.value >= 4" @click="dc.setWizardStep(dc.wizardStep.value + 1)">下一步</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="dc.applyWizardAll()">写入结论并勾选问卷</el-button>
        <el-button v-if="!isReadonly" size="small" plain @click="dc.applyWizardToQuestionnaire()">同步勾选问卷</el-button>
        <el-button v-if="!isReadonly" size="small" plain @click="dc.applyWizardToConclusion()">仅写入结论</el-button>
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G10-8" /></span>
        <el-tag size="small" type="info">共 {{ dc.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <div v-if="dc.useVirtualScroll.value" class="virtual-toolbar">
      <el-alert type="info" :closable="false">行数较多（{{ dc.rows.value.length }} 行）· 虚拟滚动速览模式</el-alert>
    </div>

    <el-table-v2
      v-if="dc.useVirtualScroll.value && browseMode"
      :columns="virtualColumns"
      :data="dc.rows.value"
      :width="tableWidth"
      :height="480"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
      data-testid="g10-derivative-virtual-table"
    />

    <el-collapse v-else v-model="expandedSections" class="sections">
      <el-collapse-item v-for="sec in dc.sections.value" :key="sec.title" :name="sec.title">
        <template #title>
          <span class="sec-title">{{ sec.title }}</span>
          <el-tag size="small" type="info" style="margin-left:8px">{{ sec.rows.length }} 项</el-tag>
          <el-button size="small" link :loading="dc.aiLoading.value" :disabled="isReadonly"
            @click.stop="dc.generateAiConclusion()">🤖 AI</el-button>
        </template>
        <el-table :data="sec.rows" border size="small" style="font-size:13px">
          <el-table-column label="#" prop="seq" width="44" />
          <el-table-column label="检查区域" prop="checkArea" width="100" show-overflow-tooltip />
          <el-table-column label="检查项目" prop="checkItem" min-width="130" show-overflow-tooltip />
          <el-table-column label="审计要求" prop="auditRequirement" min-width="110" show-overflow-tooltip />
          <el-table-column label="检查结果" min-width="110">
            <template #default="{ row }">
              <el-input v-model="row.checkResult" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'checkResult', row.checkResult)" />
            </template>
          </el-table-column>
          <el-table-column label="是否合规" width="110">
            <template #default="{ row }">
              <el-select v-model="row.compliance" size="small" :disabled="isReadonly"
                @change="(v: string) => dc.updateCell(row.rowId, 'compliance', v)">
                <el-option v-for="o in G10_COMPLIANCE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="风险等级" width="100">
            <template #default="{ row }">
              <el-select v-model="row.riskLevel" size="small" :disabled="isReadonly"
                @change="(v: string) => dc.updateCell(row.rowId, 'riskLevel', v)">
                <el-option v-for="o in G10_RISK_LEVEL_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="审计结论" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.auditConclusion" size="small" type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'auditConclusion', row.auditConclusion)" />
            </template>
          </el-table-column>
          <el-table-column label="索引" width="72">
            <template #default="{ row }">
              <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'indexRef', row.indexRef)" />
            </template>
          </el-table-column>
          <el-table-column label="备注" width="80">
            <template #default="{ row }">
              <el-input v-model="row.remark" size="small" :disabled="isReadonly"
                @change="() => dc.updateCell(row.rowId, 'remark', row.remark)" />
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <div v-if="dc.useVirtualScroll.value" class="mode-toggle">
      <el-button size="small" @click="browseMode = !browseMode">{{ browseMode ? '切换分区编辑' : '切换虚拟速览' }}</el-button>
    </div>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusionProxy"
      note-ai-section="derivative-note"
      conclusion-ai-section="derivative-conclusion"
      conclusion-title="综合审计结论"
      note-placeholder="填写审计说明：可概述衍生工具五要素核查、嵌入衍生拆分判断、公允价值计量及套期关系认定的测试情况与发现。"
      note-hint="覆盖五要素、嵌入衍生、公允价值与套期关系。"
      conclusion-placeholder="填写综合审计结论：衍生工具确认与计量是否符合 CAS 22。"
      :related-context="{
        待填合规行数: dc.missingCompliance.value.length,
        决策结论: dc.wizardEval.value.summary,
      }"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <p>先用顶部「识别向导」完成 A→E 决策树，再填写下方五区段问卷（78 项）。不合规项须在结论中说明审计应对，可「推送不合规→G10-3」生成备忘 AJE。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, watch, h, inject } from 'vue'
import type { Column } from 'element-plus'
import { useG10DerivativeCheck } from '../../composables/useG10DerivativeCheck'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import { G10A_DERIVATIVE_PROGRAM_NOS, G10A_PROCEDURE_SHEET } from '../../composables/g10FvCrossHelpers'
import {
  G10_DERIVATIVE_VARIABLE_CHECKS,
  type G10YesNo,
} from '../../composables/g10DerivativeDecision'
import { G10_COMPLIANCE_OPTIONS, G10_RISK_LEVEL_OPTIONS } from '../../composables/g10Constants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  auditYear?: number | null
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const dc = useG10DerivativeCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || ''),
  year: computed(() => props.auditYear ?? null),
})

const expandedSections = ref<string[]>([])

const NOTE_KEY = 'G10-8-derivative-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})

const conclusionProxy = computed({
  get: () => dc.overallConclusion.value,
  set: (v: string) => dc.updateOverallConclusion(v),
})

const wizardTagType = computed(() => {
  const m = dc.wizardEval.value.measurement
  if (m === 'none') return 'success'
  if (m === 'host_contract') return 'info'
  if (m === 'whole_fvtpl') return 'warning'
  if (m === 'split_fvtpl') return 'primary'
  return 'info'
})

const wizardContractNote = computed({
  get: () => dc.wizard.value.contractReviewNote,
  set: (v: string) => dc.updateWizard({ contractReviewNote: v }),
})
const wizardExpertQualIndex = computed({
  get: () => dc.wizard.value.expertQualificationIndex,
  set: (v: string) => dc.updateWizard({ expertQualificationIndex: v }),
})
const wizardExpertWorkIndex = computed({
  get: () => dc.wizard.value.expertWorkIndex,
  set: (v: string) => dc.updateWizard({ expertWorkIndex: v }),
})

async function onPushIssues() {
  await dc.pushIssuesToAdjustment()
}

async function onMarkProcedure() {
  const n = await dc.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G10A_DERIVATIVE_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `衍生工具程序（步骤 ${[...G10A_DERIVATIVE_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_DERIVATIVE_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

const browseMode = ref(true)
const tableWidth = 1100

const virtualColumns = computed<Column<any>[]>(() => [
  { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
  { key: 'sectionTitle', title: '区段', dataKey: 'sectionTitle', width: 140 },
  { key: 'checkItem', title: '检查项目', dataKey: 'checkItem', width: 200 },
  { key: 'checkResult', title: '检查结果', dataKey: 'checkResult', width: 160 },
  { key: 'compliance', title: '合规', dataKey: 'compliance', width: 88 },
  { key: 'riskLevel', title: '风险', dataKey: 'riskLevel', width: 72 },
])
</script>

<style scoped>
.g10-derivative { font-size: var(--wp-font-size, 13px); padding: 4px; }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.sec-title { font-weight: 600; }
.virtual-toolbar { margin-bottom: 8px; }
.mode-toggle { margin: 8px 0; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.objective-alert { margin-bottom: 10px; }
.wizard-card {
  margin-bottom: 10px; padding: 10px 12px; background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 4px;
}
.wizard-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.wizard-head h4 { margin: 0; font-size: 13px; flex: 1; }
.wizard-steps { margin-bottom: 10px; }
.wizard-panel { font-size: 12px; }
.wizard-hint { margin: 0 0 8px; color: #606266; }
.var-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
.var-item { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.yn-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.expert-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; }
.expert-grid label span { display: block; font-size: 11px; color: #909399; margin-bottom: 4px; }
.wizard-actions { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
</style>
