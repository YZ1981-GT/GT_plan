<template>
  <div class="g7-tab-disposal-package">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G7-12 处置子公司测试表（一揽子交易）</h3>
        <div class="sheet-subtitle">判断 → 时点 → 单体 → 合并 → 权益法追溯调整</div>
      </div>
      <div class="head-actions">
        <GtIndexChip value="wp:G7-12" :context-project-id="projectId" />
        <el-button size="small" :disabled="isReadonly" @click="addRow">新增公司</el-button>
        <el-dropdown @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi">
          <el-icon><MagicStick /></el-icon> AI结论
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-12-disposal-package')">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：获取协议、交割及估值证据，判断多次交易是否构成一揽子交易，核实丧失控制权时点，并分别复核个别报表、合并报表及剩余股权权益法追溯调整。
    </el-alert>

    <el-alert
      v-if="validationErrors.length"
      type="warning"
      :closable="false"
      show-icon
      class="validation-alert"
    >
      <template #title>尚有 {{ validationErrors.length }} 项编制事项待完成</template>
      <div v-for="message in validationErrors.slice(0, 6)" :key="message">• {{ message }}</div>
    </el-alert>

    <el-skeleton v-if="loading" :rows="8" animated />
    <template v-else>
      <section class="workpaper-section">
        <h4>1. 本期处置子公司基本情况</h4>
        <el-table :data="rows" border size="small" row-key="id">
          <el-table-column type="index" label="序号" width="52" fixed />
          <el-table-column label="企业名称" width="150" fixed>
            <template #default="{ row }"><el-input v-model="row.investeeName" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="注册地" width="120">
            <template #default="{ row }"><el-input v-model="row.registeredPlace" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="业务性质" width="130">
            <template #default="{ row }"><el-input v-model="row.businessNature" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="原持股比例" width="130">
            <template #default="{ row }"><RatioInput v-model="row.originalShareholdingRatio" :disabled="isReadonly" @change="onRatioChange(row)" /></template>
          </el-table-column>
          <el-table-column label="表决权比例" width="130">
            <template #default="{ row }"><RatioInput v-model="row.votingRatio" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="本期不再成为子公司的原因" min-width="220">
            <template #default="{ row }"><el-input v-model="row.disposalReason" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right">
            <template #default="{ $index }"><el-button link type="danger" @click="removeRow($index)">删除</el-button></template>
          </el-table-column>
        </el-table>
      </section>

      <section class="workpaper-section">
        <h4>2. 一揽子交易判断</h4>
        <p class="section-note">四项迹象并非机械的“满足一项即成立”；应结合合同安排、定价和交易依赖关系形成整体判断，并记录反向证据。</p>
        <el-table :data="rows" border size="small" row-key="id">
          <el-table-column prop="investeeName" label="子公司" width="140" fixed />
          <el-table-column
            v-for="criterion in PACKAGE_CRITERIA"
            :key="criterion.key"
            :label="criterion.label"
            min-width="180"
          >
            <template #default="{ row }">
              <JudgmentSelect v-model="row[criterion.key]" :disabled="isReadonly" @change="saveRows" />
            </template>
          </el-table-column>
          <el-table-column label="总体结论" width="135">
            <template #default="{ row }"><JudgmentSelect v-model="row.packageJudgmentConclusion" :disabled="isReadonly" package-label @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="判断依据及反向证据" min-width="260">
            <template #default="{ row }"><el-input v-model="row.packageJudgmentBasis" type="textarea" :rows="2" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
        </el-table>
      </section>

      <section class="workpaper-section">
        <h4>3. 各次交易明细（一揽子分步）</h4>
        <p class="section-note">录入各次交易后，累计对价与累计持股变动自动回写至下方「交易事实」区；合并侧「前序交易差额」仍可手工填写已确认损益的追溯调整。</p>
        <div v-if="!isReadonly" class="step-actions">
          <el-button size="small" type="primary" plain @click="addStep()">新增交易次</el-button>
        </div>
        <el-table :data="flatSteps" border size="small" empty-text="暂无分步交易，可点「新增交易次」或直接在第4区录入汇总对价">
          <el-table-column label="子公司" width="150">
            <template #default="{ row: step }">
              <el-select
                :model-value="step.rowId"
                :disabled="isReadonly"
                placeholder="选择公司"
                style="width: 100%"
                @change="(v) => moveStepToRow(step.id, step.rowId, String(v))"
              >
                <el-option v-for="r in rows" :key="r.id" :label="r.investeeName || `行${r.seq}`" :value="r.id" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="次别" width="70" align="center">
            <template #default="{ row: step }">{{ step.seq }}</template>
          </el-table-column>
          <el-table-column label="交易日期" width="150">
            <template #default="{ row: step }">
              <el-date-picker v-model="findStep(step.rowId, step.id)!.stepDate" type="date" value-format="YYYY-MM-DD" :disabled="isReadonly" @change="onStepsChanged(step.rowId)" />
            </template>
          </el-table-column>
          <el-table-column label="对价" width="140">
            <template #default="{ row: step }">
              <MoneyInput v-model="findStep(step.rowId, step.id)!.consideration" :disabled="isReadonly" @change="onStepsChanged(step.rowId)" />
            </template>
          </el-table-column>
          <el-table-column label="持股变动" width="120">
            <template #default="{ row: step }">
              <RatioInput v-model="findStep(step.rowId, step.id)!.shareChange" :disabled="isReadonly" @change="onStepsChanged(step.rowId)" />
            </template>
          </el-table-column>
          <el-table-column label="累计对价 / 累计持股" width="160" align="right">
            <template #default="{ row: step }">
              <span class="formula-cell">{{ calc(rows.find(r => r.id === step.rowId)!).cumulativePrice.toFixed(2) }} / {{ (calc(rows.find(r => r.id === step.rowId)!).cumulativeShareChange * 100).toFixed(2) }}%</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="140">
            <template #default="{ row: step }">
              <el-input v-model="findStep(step.rowId, step.id)!.note" :disabled="isReadonly" @change="onStepsChanged(step.rowId)" />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right">
            <template #default="{ row: step }">
              <el-button link type="danger" @click="removeStep(step.rowId, step.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="workpaper-section">
        <h4>4. 交易事实与丧失控制权时点</h4>
        <el-table :data="rows" border size="small" row-key="id">
          <el-table-column prop="investeeName" label="子公司" width="140" fixed />
          <el-table-column label="交易日期" width="150">
            <template #default="{ row }"><el-date-picker v-model="row.transactionDate" type="date" value-format="YYYY-MM-DD" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="股权处置价款" width="150">
            <template #default="{ row }"><MoneyInput v-model="row.transactionPrice" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="处置比例" width="130">
            <template #default="{ row }"><RatioInput v-model="row.disposalRatio" :disabled="isReadonly" @change="onRatioChange(row)" /></template>
          </el-table-column>
          <el-table-column label="剩余比例" width="110" align="right">
            <template #default="{ row }"><FormulaValue :value="calc(row).remainingRatio" percent title="原持股比例－处置比例" /></template>
          </el-table-column>
          <el-table-column label="剩余股权构成" width="130">
            <template #default="{ row }">
              <el-select v-model="row.remainingInterestType" :disabled="isReadonly" clearable @change="saveRows">
                <el-option label="联营" value="联营" /><el-option label="合营" value="合营" />
                <el-option label="金融资产" value="金融资产" /><el-option label="无剩余股权" value="无剩余股权" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="处置方式" width="130">
            <template #default="{ row }"><el-input v-model="row.disposalMethod" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="丧失控制权日" width="150">
            <template #default="{ row }"><el-date-picker v-model="row.lossOfControlDate" type="date" value-format="YYYY-MM-DD" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="时点确定依据" min-width="220">
            <template #default="{ row }"><el-input v-model="row.lossOfControlBasis" type="textarea" :rows="2" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="取得的查验资料" min-width="210">
            <template #default="{ row }"><el-input v-model="row.evidenceObtained" type="textarea" :rows="2" :disabled="isReadonly" placeholder="协议、审批、付款、交割、工商变更等" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="索引" width="105">
            <template #default="{ row }"><el-input v-model="row.indexRef" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
        </el-table>
      </section>

      <section class="workpaper-section">
        <h4>5. 个别报表测算</h4>
        <el-table :data="rows" border size="small" row-key="id">
          <el-table-column prop="investeeName" label="子公司" width="140" fixed />
          <el-table-column label="处置日长投账面" width="150"><template #default="{ row }"><MoneyInput v-model="row.individualBookValue" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="应转出长投" width="130" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).disposedBookValue" title="长投账面×处置比例÷原持股比例" /></template></el-table-column>
          <el-table-column label="剩余股权账面" width="130" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).residualBookValue" title="长投账面－应转出长投" /></template></el-table-column>
          <el-table-column label="剩余股权公允价值" width="160"><template #default="{ row }"><MoneyInput v-model="row.residualFairValue" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="重新计量利得/损失" width="150" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).remeasurementGain" title="剩余股权公允价值－剩余股权账面价值" /></template></el-table-column>
          <el-table-column label="联营/合营可转损益OCI" width="170"><template #default="{ row }"><MoneyInput v-model="row.associateJointVentureRecyclableOci" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="金融资产可转损益OCI" width="170"><template #default="{ row }"><MoneyInput v-model="row.financialAssetRecyclableOci" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="不可转损益OCI" width="150"><template #default="{ row }"><MoneyInput v-model="row.nonRecyclableOci" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="应确认投资收益" width="150" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).individualGain" title="重新计量损益＋可重分类OCI结转" /></template></el-table-column>
          <el-table-column label="应转入权益" width="130" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).transferToEquity" title="不可重分类OCI按处置比例转入权益" /></template></el-table-column>
        </el-table>
      </section>

      <section class="workpaper-section">
        <h4>6. 合并报表测算</h4>
        <el-table :data="rows" border size="small" row-key="id">
          <el-table-column prop="investeeName" label="子公司" width="140" fixed />
          <el-table-column label="处置日子公司净资产" width="160"><template #default="{ row }"><MoneyInput v-model="row.consolidatedNetAssets" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="处置对应净资产份额" width="160" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).consolidatedNetAssetShare" title="持续计算净资产×处置比例÷原持股比例" /></template></el-table-column>
          <el-table-column label="价款与净资产份额差额" width="170" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).priceShareDifference" title="处置价款－处置对应净资产份额" /></template></el-table-column>
          <el-table-column label="商誉" width="130"><template #default="{ row }"><MoneyInput v-model="row.goodwill" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="剩余股权公允价值确定方法及假设" min-width="230"><template #default="{ row }"><el-input v-model="row.residualFairValueMethod" type="textarea" :rows="2" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="可转损益OCI" width="145"><template #default="{ row }"><MoneyInput v-model="row.consolidatedRecyclableOci" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="前序交易差额" width="145"><template #default="{ row }"><MoneyInput v-model="row.priorStepDifference" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="合并处置损益" width="150" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).consolidatedGain" title="处置价款＋剩余股权FV－净资产－商誉＋可转OCI＋前序交易差额" /></template></el-table-column>
        </el-table>
      </section>

      <section class="workpaper-section">
        <h4>7. 剩余股权为联营、合营时追溯调整为权益法</h4>
        <p class="section-note">盈余公积比例默认 10%（可按被投资单位章程调整）；以前年度净利润按「1−盈余公积比例」计入期初未分配利润。</p>
        <el-table :data="rows" border size="small" row-key="id">
          <el-table-column prop="investeeName" label="被投资单位" width="140" fixed />
          <el-table-column label="权益法比例" width="130"><template #default="{ row }"><RatioInput v-model="row.equityMethodRatio" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="原取得日至处置日净利润" width="170"><template #default="{ row }"><MoneyInput v-model="row.preDisposalProfit" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="本期净利润" width="145"><template #default="{ row }"><MoneyInput v-model="row.currentProfit" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="其他综合收益" width="145"><template #default="{ row }"><MoneyInput v-model="row.otherComprehensiveIncome" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="其他所有者权益变动" width="170"><template #default="{ row }"><MoneyInput v-model="row.otherEquityChanges" :disabled="isReadonly" @change="saveRows" /></template></el-table-column>
          <el-table-column label="盈余公积比例" width="120">
            <template #default="{ row }"><RatioInput v-model="row.surplusReserveRate" :disabled="isReadonly" @change="saveRows" /></template>
          </el-table-column>
          <el-table-column label="期初未分配利润" width="145" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).openingRetainedEarnings" :title="`比例×以前年度净利润×(1−盈余公积比例${((row.surplusReserveRate || 0.1) * 100).toFixed(0)}%)`" /></template></el-table-column>
          <el-table-column label="盈余公积" width="125" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).surplusReserve" :title="`比例×以前年度净利润×盈余公积比例`" /></template></el-table-column>
          <el-table-column label="投资收益" width="125" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).investmentIncome" title="比例×本期净利润" /></template></el-table-column>
          <el-table-column label="长投-其他综合收益" width="155" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).longTermInvestmentOci" title="比例×其他综合收益" /></template></el-table-column>
          <el-table-column label="长投-其他变动" width="145" align="right"><template #default="{ row }"><FormulaValue :value="calc(row).longTermInvestmentOtherChanges" title="比例×其他所有者权益变动" /></template></el-table-column>
        </el-table>
      </section>
    </template>

    <el-card class="audit-card" shadow="never">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly" placeholder="说明执行程序、证据、异常及处理情况。" @change="saveAuditNote" />
    </el-card>
    <el-card class="audit-card" shadow="never">
      <template #header><div class="conclusion-header"><span>审计结论</span><el-tag :type="validationErrors.length ? 'warning' : 'success'">{{ validationErrors.length ? '待完善' : '编制完整' }}</el-tag></div></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="对交易性质、丧失控制权时点及会计处理发表结论。" @change="saveAuditConclusion" />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>一揽子交易四项迹象需整体判断，不是“满足一项即成立”；须记录反向证据</li>
        <li>多次交易请在「各次交易明细」分录；累计对价/持股自动回写第4区，丧失控制权日统一确认损益</li>
        <li>合并处置损益 = 处置价款 + 剩余股权FV − 净资产 − 商誉 + 可转OCI + 前序交易差额</li>
        <li>个别侧重新计量损益 = 剩余股权FV − 剩余账面；可转损益 OCI 按处置比例结转</li>
        <li>权益法追溯：盈余公积比例默认 10%，可按章程修改；比例以小数填写（0.30=30%）</li>
        <li>非一揽子单次处置请用 G7-11；不丧失控制权处置请用 G7-10 第三区段</li>
      </ul>
    </details>

    <G7VoucherSampleSection
      :wp-id="wpId"
      :project-id="projectId"
      :is-readonly="isReadonly"
      storage-key="G7-12-voucher-samples"
      :account-code="G7_GROSS_FALLBACK_STANDARD"
      title="处置凭证抽查（G7-12）"
      :html-data="htmlData"
    />

    <input ref="fileInputRef" type="file" accept=".xlsx" class="hidden-input" @change="handleFileChange">
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDisposalPackage — G7-12 处置子公司测试表（一揽子交易）
 * 持久化 G7-12-rows；六区段+各次交易；版本链 onAfterSave。
 */
import { computed, defineComponent, h, inject, onMounted, ref } from 'vue'
import { ElInputNumber, ElMessage, ElOption, ElSelect } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { extractG7AiText } from '../../composables/g7AiText'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import GtIndexChip from '../../GtIndexChip.vue'
import G7VoucherSampleSection from '../../g7-shared/G7VoucherSampleSection.vue'
import {
  PACKAGE_CRITERIA,
  calculatePackageRow,
  createPackageRow,
  createPackageStep,
  migratePackageRow,
  syncRowFromSteps,
  validatePackageRows,
  type G7DisposalPackageRow,
  type JudgmentAnswer,
} from './g7DisposalPackageModel'
import { G7_GROSS_FALLBACK_STANDARD } from '../../composables/g7AccountScope'

const props = defineProps<{ htmlData: Record<string, any> | null; sheetName: string; wpId: string; projectId: string; readonly?: boolean }>()
const isReadonly = computed(() => !!props.readonly)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version?.scheduleAutoSnapshot ?? (() => undefined)
const formData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const importExport = useG7SubImportExport({ wpId: computed(() => props.wpId) })
const DATA_KEY = 'G7-12-rows'
const NOTE_KEY = 'G7-12-disposal-package-audit-note'
const CONCLUSION_KEY = 'G7-12-disposal-package-audit-conclusion'
const rows = ref<G7DisposalPackageRow[]>([])
const loading = ref(true)
const auditNote = ref('')
const conclusion = ref('')
const aiLoading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const validationErrors = computed(() => validatePackageRows(rows.value))
const calc = (row: G7DisposalPackageRow) => calculatePackageRow(row)

const flatSteps = computed(() =>
  rows.value.flatMap(row =>
    (row.steps || []).map(step => ({
      ...step,
      rowId: row.id,
      investeeName: row.investeeName,
    })),
  ),
)

const MoneyInput = defineComponent({
  props: { modelValue: { type: Number, default: 0 }, disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(p, { emit }) {
    return () => h(ElInputNumber, { modelValue: p.modelValue, disabled: p.disabled, controls: false, precision: 2, onUpdateModelValue: (v: number | undefined) => emit('update:modelValue', v ?? 0), onChange: () => emit('change'), style: 'width:100%' })
  },
})
const RatioInput = defineComponent({
  props: { modelValue: { type: Number, default: 0 }, disabled: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(p, { emit }) {
    return () => h(ElInputNumber, { modelValue: p.modelValue, disabled: p.disabled, min: 0, max: 1, step: 0.01, precision: 4, controls: false, onUpdateModelValue: (v: number | undefined) => emit('update:modelValue', v ?? 0), onChange: () => emit('change'), style: 'width:100%' })
  },
})
const JudgmentSelect = defineComponent({
  props: { modelValue: { type: String as () => JudgmentAnswer, default: '' }, disabled: Boolean, packageLabel: Boolean },
  emits: ['update:modelValue', 'change'],
  setup(p, { emit }) {
    return () => h(ElSelect, { modelValue: p.modelValue, disabled: p.disabled, clearable: true, placeholder: '请选择', onUpdateModelValue: (v: JudgmentAnswer) => emit('update:modelValue', v), onChange: () => emit('change'), style: 'width:100%' }, () => [
      h(ElOption, { label: p.packageLabel ? '是，一揽子交易' : '是', value: 'yes' }),
      h(ElOption, { label: p.packageLabel ? '否，非一揽子交易' : '否', value: 'no' }),
      h(ElOption, { label: '不适用', value: 'na' }),
    ])
  },
})
const FormulaValue = defineComponent({
  props: { value: { type: Number, required: true }, title: { type: String, default: '' }, percent: Boolean },
  setup(p) {
    return () => h('span', { class: 'formula-cell', title: p.title }, p.percent ? `${(p.value * 100).toFixed(2)}%` : p.value.toFixed(2))
  },
})

function parseRows(raw: unknown): G7DisposalPackageRow[] {
  const source = Array.isArray(raw) ? raw : (raw && typeof raw === 'object' && Array.isArray((raw as any).rows) ? (raw as any).rows : [])
  return source.map((row: Record<string, any>, index: number) => migratePackageRow(row, index + 1))
}
function parseJson(raw: string | null | undefined): unknown {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}
function saveRows(): void {
  if (isReadonly.value) return
  formData.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value), remark: null })
}
function onRatioChange(row: G7DisposalPackageRow): void {
  row.remainingShareholdingRatio = calc(row).remainingRatio
  if (!row.equityMethodRatio) row.equityMethodRatio = row.remainingShareholdingRatio
  saveRows()
}
function findStep(rowId: string, stepId: string) {
  const row = rows.value.find(r => r.id === rowId)
  return row?.steps?.find(s => s.id === stepId)
}
function onStepsChanged(rowId: string): void {
  const row = rows.value.find(r => r.id === rowId)
  if (!row) return
  syncRowFromSteps(row)
  saveRows()
}
function addStep(rowId?: string): void {
  if (isReadonly.value) return
  let row = rowId ? rows.value.find(r => r.id === rowId) : rows.value[0]
  if (!row) {
    addRow()
    row = rows.value[0]
  }
  if (!row.steps) row.steps = []
  row.steps.push(createPackageStep(row.steps.length + 1))
  syncRowFromSteps(row)
  saveRows()
}
function removeStep(rowId: string, stepId: string): void {
  const row = rows.value.find(r => r.id === rowId)
  if (!row?.steps) return
  row.steps = row.steps.filter(s => s.id !== stepId)
  row.steps.forEach((s, i) => { s.seq = i + 1 })
  syncRowFromSteps(row)
  saveRows()
}
function moveStepToRow(stepId: string, fromRowId: string, toRowId: string): void {
  if (fromRowId === toRowId) return
  const from = rows.value.find(r => r.id === fromRowId)
  const to = rows.value.find(r => r.id === toRowId)
  if (!from?.steps || !to) return
  const idx = from.steps.findIndex(s => s.id === stepId)
  if (idx < 0) return
  const [step] = from.steps.splice(idx, 1)
  from.steps.forEach((s, i) => { s.seq = i + 1 })
  if (!to.steps) to.steps = []
  to.steps.push(step)
  to.steps.forEach((s, i) => { s.seq = i + 1 })
  syncRowFromSteps(from)
  syncRowFromSteps(to)
  saveRows()
}
function addRow(): void {
  rows.value.push(createPackageRow(rows.value.length + 1))
  saveRows()
}
function removeRow(index: number): void {
  rows.value.splice(index, 1)
  rows.value.forEach((row, i) => { row.seq = i + 1 })
  if (!rows.value.length) addRow()
  saveRows()
}
function saveAuditNote(value: string): void {
  if (!isReadonly.value) formData.debouncedSave(NOTE_KEY, { remark: value, conclusion: null })
}
function saveAuditConclusion(value: string): void {
  if (!isReadonly.value) formData.debouncedSave(CONCLUSION_KEY, { remark: value, conclusion: null })
}
async function handleAi(): Promise<void> {
  aiLoading.value = true
  try {
    const response = await http.post(`/api/workpapers/${props.wpId}/g7-sub/ai/disposal-conclusion`, {
      existingContent: conclusion.value,
      relatedContext: {
        sheet: 'G7-12',
        validationErrors: validationErrors.value,
        rows: rows.value,
        stepCount: flatSteps.value.length,
      },
    })
    const text = extractG7AiText(response?.data)
    if (text) {
      conclusion.value = text
      saveAuditConclusion(text)
      ElMessage.success('AI结论已生成')
    } else {
      ElMessage.warning('AI辅助暂未连接，请手动填写')
    }
  } catch {
    ElMessage.warning('AI辅助暂未连接，请手动填写')
  } finally {
    aiLoading.value = false
  }
}

function handleImportExportCommand(command: string): void {
  if (command === 'template') void importExport.exportTemplate('G7-12')
  else if (command === 'export') void importExport.exportData('G7-12')
  else if (command === 'import') fileInputRef.value?.click()
}

async function handleFileChange(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    await importExport.importData('G7-12', file)
    await formData.load()
    const saved = formData.data.value.get(DATA_KEY)
    const loaded = parseRows(parseJson(saved?.conclusion as string | undefined))
    if (loaded.length) {
      rows.value = loaded
      ElMessage.success(`导入完成，已刷新 ${loaded.length} 行`)
    } else {
      ElMessage.success('导入完成，请核对数据')
    }
  } catch {
    ElMessage.error('导入失败')
  }
}

onMounted(async () => {
  await formData.load()
  const saved = formData.data.value.get(DATA_KEY)
  let loaded = parseRows(parseJson(saved?.conclusion))
  if (!loaded.length) {
    const snapshot = props.htmlData?.responses_snapshot?.[DATA_KEY]
    loaded = parseRows(parseJson(snapshot?.conclusion))
  }
  if (!loaded.length) loaded = parseRows(props.htmlData?.disposalPackage)
  rows.value = loaded.length ? loaded : Array.from({ length: 4 }, (_, index) => createPackageRow(index + 1))
  auditNote.value = formData.data.value.get(NOTE_KEY)?.remark || props.htmlData?.responses_snapshot?.[NOTE_KEY]?.remark || ''
  conclusion.value = formData.data.value.get(CONCLUSION_KEY)?.remark || props.htmlData?.responses_snapshot?.[CONCLUSION_KEY]?.remark || ''
  loading.value = false
})
</script>

<style scoped>
.g7-tab-disposal-package { padding: 12px; font-size: var(--wp-font-size, 13px); }
.hidden-input { display: none; }
.section-head, .conclusion-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; }
.sheet-subtitle { margin-top: 4px; color: #909399; font-size: 12px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.audit-objective, .validation-alert { margin: 12px 0; }
.workpaper-section { margin-top: 18px; }
.workpaper-section h4 { margin: 0 0 8px; padding-left: 8px; border-left: 3px solid #409eff; font-size: 14px; }
.section-note { margin: -2px 0 8px; color: #606266; font-size: 12px; }
.step-actions { margin-bottom: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; color: #303133; cursor: help; font-variant-numeric: tabular-nums; }
.audit-card { margin-top: 16px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ul { margin: 4px 0 0 16px; line-height: 1.8; }
:deep(.el-table .cell) { line-height: 1.35; }
:deep(.el-date-editor.el-input) { width: 130px; }
</style>
