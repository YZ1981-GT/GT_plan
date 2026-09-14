<template>
  <div class="g4-tab-sppi-test">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="`审计目标：${SPPI_AUDIT_OBJECTIVE}`"
      style="margin-bottom: 12px"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-5" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ totalProjectCount }} 个项目</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="tipsDrawer = true">CAS22 判断要点</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="sppiTestLogic.seedBondProjectsFromDetail()">
          从明细 G4-2 带入
        </el-button>
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="sppiTestLogic.writeClassificationToG42()">
          回写分类至 G4-2
        </el-button>
        <slot name="importExport">
          <G4SppiImportExportDropdown
            v-if="wpId"
            :wp-id="wpId"
            sheet="G4-6"
            :disabled="isReadonly"
            @imported="emit('imported')"
          />
        </slot>
      </div>
    </div>

    <el-card shadow="never" class="classify-card">
      <div class="classify-row">
        <div class="classify-item">
          <span class="classify-label">G4-5 业务模式</span>
          <el-tag :type="bmTagType" size="small" effect="plain">{{ bmLabel }}</el-tag>
        </div>
        <div class="classify-item">
          <span class="classify-label">本表 SPPI 综合</span>
          <el-tag :type="sppiTagType" size="small" effect="dark">{{ sppiLabel }}</el-tag>
        </div>
        <div class="classify-item classify-final">
          <span class="classify-label">建议后续计量分类</span>
          <strong>{{ finalClassificationLabel }}</strong>
        </div>
      </div>
      <el-alert
        v-if="classificationWarning"
        type="warning"
        :closable="false"
        show-icon
        :title="classificationWarning"
        style="margin-top: 10px"
      />
    </el-card>

    <el-collapse v-model="openPanels" class="proc-collapse">
      <el-collapse-item title="二、审计程序（源模板要点）" name="procedures">
        <ol class="proc-list">
          <li v-for="(p, idx) in SPPI_AUDIT_PROCEDURES" :key="idx">{{ p }}</li>
        </ol>
      </el-collapse-item>
    </el-collapse>

    <!-- (一) -->
    <div class="section-header">
      <h3 class="section-title">（一）债券投资（国债、公司债、企业债）及发放的委托贷款</h3>
      <div class="section-actions">
        <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="fillAi('sppi-bond-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-6合同现金流量特征分析-债券')">复核</el-button>
      </div>
    </div>

    <div class="split-layout">
      <div class="split-main">
        <el-table :data="bondItems" border stripe size="small" :max-height="560" class="sppi-bond-table">
          <el-table-column label="投资项目" min-width="120" fixed>
            <template #default="{ row }">
              <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="handleBondUpdate(row.id, { investProject: row.investProject })" />
            </template>
          </el-table-column>
          <el-table-column label="票面价值总额" min-width="110">
            <template #default="{ row }">
              <WpAmountInput v-model="row.faceValue" size="small" :disabled="isReadonly" @change="handleBondUpdate(row.id, { faceValue: row.faceValue })" />
            </template>
          </el-table-column>
          <el-table-column label="票面利率(%)" min-width="100">
            <template #default="{ row }">
              <el-input-number v-model="row.couponRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="handleBondUpdate(row.id, { couponRate: row.couponRate })" />
            </template>
          </el-table-column>
          <el-table-column label="偿付顺序" min-width="90">
            <template #default="{ row }">
              <el-input v-model="row.repaymentOrder" size="small" :disabled="isReadonly" placeholder="不涉及" @change="handleBondUpdate(row.id, { repaymentOrder: row.repaymentOrder })" />
            </template>
          </el-table-column>
          <el-table-column label="提前回售" min-width="90" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.hasEarlyRedemption" size="small" :disabled="isReadonly" @change="handleBondUpdate(row.id, { hasEarlyRedemption: row.hasEarlyRedemption })" />
            </template>
          </el-table-column>
          <el-table-column label="展期" min-width="80" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.hasExtension" size="small" :disabled="isReadonly" @change="handleBondUpdate(row.id, { hasExtension: row.hasExtension })" />
            </template>
          </el-table-column>
          <el-table-column label="权益转换" min-width="90" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.hasEquityConversion" size="small" :disabled="isReadonly" @change="handleBondUpdate(row.id, { hasEquityConversion: row.hasEquityConversion })" />
            </template>
          </el-table-column>
          <el-table-column label="杠杆" min-width="80" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.hasLeverage" size="small" :disabled="isReadonly" @change="handleBondUpdate(row.id, { hasLeverage: row.hasLeverage })" />
            </template>
          </el-table-column>
          <el-table-column label="结论" min-width="130">
            <template #default="{ row }">
              <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="sppiTestLogic.setBondConclusion(row.id, row.conclusion)">
                <el-option v-for="opt in SPPI_CONCLUSION_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="分析项目" min-width="130">
            <template #default="{ row }">
              <el-select v-model="row.analysisType" size="small" :disabled="isReadonly" clearable @change="handleBondUpdate(row.id, { analysisType: row.analysisType })">
                <el-option v-for="opt in ANALYSIS_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="判断逻辑" min-width="220">
            <template #default="{ row }">
              <div v-if="row.methodologyText" class="methodology-context">{{ row.methodologyText }}</div>
              <el-text v-else type="info" size="small">选择分析项目后显示</el-text>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="56" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="danger" link size="small" :disabled="isReadonly || bondItems.length <= 1" @click="sppiTestLogic.removeBondItem(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="table-actions">
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="sppiTestLogic.addBondItem()">+ 新增投资项目</el-button>
        </div>
      </div>
      <aside class="split-aside">
        <div class="aside-title">判断逻辑对照（源模板）</div>
        <div v-for="row in BOND_JUDGMENT_LOGIC_TABLE" :key="row.analysisItem" class="aside-block">
          <div class="aside-item-name">{{ row.analysisItem }}</div>
          <div class="aside-basis">{{ row.basis }}</div>
        </div>
      </aside>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span>部分(一) 审计结论</span></template>
      <el-input v-model="bondConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :disabled="isReadonly" placeholder="债券投资SPPI审计结论..." @change="sppiTestLogic.setBondAuditConclusion(bondConclusion)" />
    </el-card>

    <G4SppiBenchmarkPanel
      :model-value="benchmark"
      :readonly="isReadonly"
      @update:model-value="sppiTestLogic.setBenchmark($event)"
      @persist="() => {}"
    />

    <!-- (二) -->
    <div class="section-header mt24">
      <h3 class="section-title">（二）银行理财产品 — 三步SPPI判断</h3>
      <div class="section-actions">
        <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="fillAi('sppi-financial-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-6合同现金流量特征分析-理财')">复核</el-button>
      </div>
    </div>

    <div v-for="tip in FINANCIAL_PRODUCT_TIPS" :key="tip.id" class="tip-banner" :class="`tip-${tip.accent}`">
      <strong>{{ tip.title }}</strong>
      <p v-for="(para, i) in tip.paragraphs" :key="i">{{ para }}</p>
    </div>

    <h4 class="step-title">1. 是否保本保收益</h4>
    <el-table :data="step1Items" border stripe size="small" class="step-table">
      <el-table-column label="投资项目" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="投资总额" min-width="100">
        <template #default="{ row }">
          <WpAmountInput v-model="row.totalAmount" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { totalAmount: row.totalAmount })" />
        </template>
      </el-table-column>
      <el-table-column label="保证本金" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.guaranteesPrincipal" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { guaranteesPrincipal: row.guaranteesPrincipal })" />
        </template>
      </el-table-column>
      <el-table-column label="固定收益" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.hasFixedReturn" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { hasFixedReturn: row.hasFixedReturn })" />
        </template>
      </el-table-column>
      <el-table-column label="固定收益率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.fixedReturnRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { fixedReturnRate: row.fixedReturnRate })" />
        </template>
      </el-table-column>
      <el-table-column label="浮动收益" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.hasFloatingReturn" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { hasFloatingReturn: row.hasFloatingReturn })" />
        </template>
      </el-table-column>
      <el-table-column label="浮动收益率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.floatingReturnRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { floatingReturnRate: row.floatingReturnRate })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { conclusion: row.conclusion })">
            <el-option label="通过" value="PASS" /><el-option label="不通过" value="FAIL" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" :disabled="isReadonly" @click="sppiTestLogic.removeFinancialItem(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <h4 class="step-title">2. 浮动收益是否不现实（非真实特征）</h4>
    <el-table :data="step2Items" border stripe size="small" class="step-table">
      <el-table-column label="投资项目" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="固定收益率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.fixedReturnRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { fixedReturnRate: row.fixedReturnRate })" />
        </template>
      </el-table-column>
      <el-table-column label="浮动收益确定方式" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.floatingMethod" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { floatingMethod: row.floatingMethod })" />
        </template>
      </el-table-column>
      <el-table-column label="基础变量历史变动" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.baseVariableHistory" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { baseVariableHistory: row.baseVariableHistory })" />
        </template>
      </el-table-column>
      <el-table-column label="是否不现实" width="90" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.isUnrealistic" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { isUnrealistic: row.isUnrealistic })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { conclusion: row.conclusion })">
            <el-option label="通过" value="PASS" /><el-option label="不通过" value="FAIL" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <h4 class="step-title">3. 穿透底层资产（必要时）</h4>
    <el-table :data="step3Items" border stripe size="small" class="step-table">
      <el-table-column label="投资项目" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep3Item(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="底层资产类型" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.underlyingAssetType" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep3Item(row.id, { underlyingAssetType: row.underlyingAssetType })" />
        </template>
      </el-table-column>
      <el-table-column label="底层资产SPPI特征" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.underlyingSppiFeature" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep3Item(row.id, { underlyingSppiFeature: row.underlyingSppiFeature })" />
        </template>
      </el-table-column>
      <el-table-column label="穿透结论" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep3Item(row.id, { conclusion: row.conclusion })">
            <el-option label="通过" value="PASS" /><el-option label="不通过" value="FAIL" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="sppiTestLogic.addFinancialItem()">+ 新增理财产品</el-button>
    </div>
    <el-card shadow="never" class="conclusion-card">
      <template #header><span>部分(二) 审计结论</span></template>
      <el-input v-model="financialConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :disabled="isReadonly" @change="sppiTestLogic.setFinancialAuditConclusion(financialConclusion)" />
    </el-card>

    <!-- (三)-(六) 由子组件块渲染，见下方动态段落 -->
    <G4SppiExtraSections
      :preferred-items="preferredItems"
      :convertible-items="convertibleItems"
      :project-trust-items="projectTrustItems"
      :abs-items="absItems"
      :is-readonly="isReadonly"
      :logic="sppiTestLogic"
      @review="handleReview"
    />

    <el-card shadow="never" class="conclusion-card">
      <template #header><span>三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="概述SPPI程序、关键判断（非真实特征/穿透/分层）及拟调整事项。" @change="sppiTestLogic.setAuditNote(auditNote)" />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span>四、审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="fillOverallAi">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input v-model="overallConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" :disabled="isReadonly" :placeholder="`综合建议分类：${finalClassificationLabel}`" @change="sppiTestLogic.setOverallConclusion(overallConclusion)" />
    </el-card>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 先完成 G4-5，再填本表；顶部自动勾稽建议分类。</p>
        <p>2. 部分(一) 四布尔自动判定；右侧对照表来自源模板「判断逻辑」。</p>
        <p>3. 部分(二) 重点论证浮动条款是否「不现实」。</p>
        <p>4. 部分(三)～(六) 对齐源模板扩展产品；可转债默认不通过；ABS 须分档+穿透。</p>
        <p>5. 「CAS22 判断要点」承载源模板底部提示全文；部分(一)下方可做修正TVM基准测试。</p>
        <p>6. 理财：不保本→不通过；保本且仅固定→通过；有浮动则看第二步「是否不现实」。ABS 次级默认不通过（可手改）。</p>
        <p>7. 「从明细带入」先查本底稿，再经 ACNR 回退 G4 主底稿 G4-2。</p>
      </div>
    </details>

    <el-drawer v-model="tipsDrawer" title="CAS22 合同现金流量特征 — 判断要点（源模板）" size="420px" append-to-body>
      <div v-for="tip in SPPI_BOTTOM_TIPS" :key="tip.id" class="drawer-tip" :class="`tip-${tip.accent}`">
        <h4>{{ tip.title }}</h4>
        <p v-for="(para, i) in tip.paragraphs" :key="i">{{ para }}</p>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { inject, toRef, computed, ref, defineAsyncComponent } from 'vue'
import { ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G4SppiImportExportDropdown from '../G4SppiImportExportDropdown.vue'
import { useG4SppiTest, ANALYSIS_TYPE_OPTIONS, SPPI_CONCLUSION_OPTIONS } from '@/composables/useG4SppiTest'
import type { BondSppiItem } from '@/composables/useG4SppiTest'
import { useG4SppiFormData } from '@/composables/useG4SppiFormData'
import { useG4SppiAiGenerate, type G4SppiAiSection } from '../../composables/useG4SppiAiGenerate'
import { CONCLUSION_CHIP_MAP } from '@/composables/useG4SppiBusinessModel'
import {
  SPPI_AUDIT_OBJECTIVE,
  SPPI_AUDIT_PROCEDURES,
  BOND_JUDGMENT_LOGIC_TABLE,
  FINANCIAL_PRODUCT_TIPS,
  SPPI_BOTTOM_TIPS,
} from '@/composables/g4SppiGuidance'

const G4SppiExtraSections = defineAsyncComponent(() => import('./G4SppiExtraSections.vue'))
const G4SppiBenchmarkPanel = defineAsyncComponent(() => import('./G4SppiBenchmarkPanel.vue'))

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'imported'): void }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')
function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4SppiAiGenerate(wpIdRef)

const formData = useG4SppiFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
formData.loadAll()

const sppiTestLogic = useG4SppiTest({
  allResponses: formData.allResponses,
  debouncedSave: formData.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  wpId: wpIdRef,
  projectId: computed(() => props.projectId),
})

const {
  bondItems, bondConclusion, step1Items, step2Items, step3Items, financialConclusion,
  preferredItems, convertibleItems, projectTrustItems, absItems,
  overallConclusion, auditNote, benchmark,
  businessModelResult, overallSppiResult, finalClassificationLabel,
  classificationWarning, totalProjectCount,
} = sppiTestLogic

const tipsDrawer = ref(false)
const openPanels = ref<string[]>([])

const bmLabel = computed(() => CONCLUSION_CHIP_MAP[businessModelResult.value]?.label ?? '未完成')
const bmTagType = computed(() => CONCLUSION_CHIP_MAP[businessModelResult.value]?.type ?? 'info')
const sppiLabel = computed(() => {
  const m: Record<string, string> = {
    PASS: '通过SPPI测试', FAIL: '通不过SPPI测试',
    FURTHER_ANALYSIS: '需进一步分析', INCOMPLETE: '尚未形成结论',
  }
  return m[overallSppiResult.value] ?? overallSppiResult.value
})
const sppiTagType = computed(() => {
  const m: Record<string, 'success' | 'danger' | 'warning' | 'info'> = {
    PASS: 'success', FAIL: 'danger', FURTHER_ANALYSIS: 'warning', INCOMPLETE: 'info',
  }
  return m[overallSppiResult.value] ?? 'info'
})

async function fillAi(section: G4SppiAiSection): Promise<void> {
  if (props.isReadonly) return
  const existing = section === 'sppi-bond-conclusion' ? (bondConclusion.value || '') : (financialConclusion.value || '')
  const text = await generateAndConfirm(section, existing, {
    overallSppi: overallSppiResult.value,
    businessModel: businessModelResult.value,
    finalClassification: finalClassificationLabel.value,
  }, 'AI 审计结论')
  if (!text) return
  if (section === 'sppi-bond-conclusion') sppiTestLogic.setBondAuditConclusion(text)
  else sppiTestLogic.setFinancialAuditConclusion(text)
}

async function fillOverallAi(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm('sppi-bond-conclusion', overallConclusion.value || '', {
    section: 'overall',
    overallSppi: overallSppiResult.value,
    businessModel: businessModelResult.value,
    finalClassification: finalClassificationLabel.value,
  }, 'AI 综合审计结论')
  if (text) sppiTestLogic.setOverallConclusion(text)
}

function handleBondUpdate(id: string, patch: Partial<BondSppiItem>): void {
  sppiTestLogic.updateBondItem(id, patch)
}
</script>

<style scoped>
.g4-tab-sppi-test { font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.section-actions { display: flex; gap: 6px; align-items: center; }
.mt24 { margin-top: 24px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.classify-card { margin-bottom: 12px; }
.classify-row { display: flex; flex-wrap: wrap; gap: 16px 24px; align-items: center; }
.classify-item { display: flex; align-items: center; gap: 8px; }
.classify-label { color: #909399; font-size: 12px; }
.classify-final strong { color: #303133; font-size: 13px; }
.proc-collapse { margin-bottom: 12px; border: none; }
.proc-list { margin: 0; padding-left: 18px; color: #606266; line-height: 1.7; font-size: 12px; }
.split-layout { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 12px; align-items: start; }
@media (max-width: 1100px) { .split-layout { grid-template-columns: 1fr; } }
.split-aside { background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; padding: 10px; max-height: 560px; overflow: auto; font-size: 12px; }
.aside-title { font-weight: 600; margin-bottom: 8px; color: #606266; }
.aside-block { margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px dashed #e4e7ed; }
.aside-item-name { font-weight: 600; color: #303133; margin-bottom: 4px; }
.aside-basis { color: #8b6914; line-height: 1.5; }
.methodology-context { background: #fffbe6; border-left: 3px solid #e6a23c; padding: 6px 10px; font-size: 12px; line-height: 1.5; color: #8b6914; border-radius: 2px; }
.tip-banner { border-radius: 4px; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; line-height: 1.6; }
.tip-banner p { margin: 4px 0 0; }
.tip-blue { background: #ecf5ff; border-left: 3px solid #409eff; color: #1d39c4; }
.tip-red { background: #fef0f0; border-left: 3px solid #f56c6c; color: #c45656; }
.tip-amber { background: #fdf6ec; border-left: 3px solid #e6a23c; color: #8b6914; }
.step-title { margin: 16px 0 8px; font-size: 14px; font-weight: 500; }
.step-table { margin-bottom: 8px; }
.table-actions { display: flex; gap: 8px; margin: 8px 0 16px; }
.conclusion-card { margin: 12px 0; }
.conclusion-card :deep(.el-card__header) { padding: 8px 16px; font-size: 13px; font-weight: 500; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }
.guidance-details { margin-top: 16px; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #606266; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #909399; line-height: 1.8; }
.guidance-content p { margin: 0; }
.drawer-tip { margin-bottom: 16px; padding: 10px 12px; border-radius: 4px; }
.drawer-tip h4 { margin: 0 0 6px; font-size: 13px; }
.drawer-tip p { margin: 4px 0; font-size: 12px; line-height: 1.65; }
.drawer-tip.tip-blue { background: #ecf5ff; }
.drawer-tip.tip-red { background: #fef0f0; }
.drawer-tip.tip-amber { background: #fdf6ec; }
</style>
