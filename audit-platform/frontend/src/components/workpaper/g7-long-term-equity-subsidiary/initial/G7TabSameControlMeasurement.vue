<template>
  <div class="g7-tab-same-control">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G7-8 子公司初始计量测试表（同一控制）</h3>
        <div class="sheet-subtitle">按一次合并、分步合并和反向购买三类交易分别测试</div>
      </div>
      <div class="head-actions">
        <span class="save-status" :class="`save-${formData.savePhase.value}`">{{ saveStatusText }}</span>
        <el-button
          v-if="!isReadonly"
          size="small"
          :loading="syncing"
          @click="syncFromRelatedSheets"
        >
          同步 G7-7/G7-2/G7-4
        </el-button>
        <el-dropdown v-if="!isReadonly" @command="handleAddCommand">
          <el-button size="small" type="primary">新增测试 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="merger">合并方式取得</el-dropdown-item>
              <el-dropdown-item command="step">分步实现同控合并</el-dropdown-item>
              <el-dropdown-item command="reverse">反向购买</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
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
        <el-button size="small" type="primary" link @click="handleAiConclusion">🤖 AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G7-8-same-control')">💬复核</el-button>
        <GtIndexChip value="wp:G7-8" :context-project-id="projectId" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      审计目标：确定被审计单位对子公司长期股权投资初始计量是否恰当。
    </el-alert>

    <div class="methodology-context">
      <strong>核心逻辑：</strong>
      同控合并以合并日应享有被合并方在最终控制方合并报表中的所有者权益账面价值份额作为初始投资成本；
      不确认商誉。合并前会计政策不一致时，应先统一政策再计算。
    </div>

    <div class="summary-bar">
      <div class="summary-left">
        <el-tag type="info">一次合并 {{ mergerRows.length }} 家</el-tag>
        <el-tag type="info">分步合并 {{ stepSummaries.length }} 家</el-tag>
        <el-tag type="info">反向购买 {{ reverseRows.length }} 项</el-tag>
        <el-tag v-if="errorCount" type="danger">{{ errorCount }} 项错误</el-tag>
        <el-tag v-if="warningCount" type="warning">{{ warningCount }} 项待补充</el-tag>
      </div>
    </div>

    <el-alert
      v-if="issues.length"
      :type="errorCount ? 'error' : 'warning'"
      :closable="false"
      show-icon
      class="validation-alert"
    >
      <div v-for="(issue, index) in issues.slice(0, 8)" :key="`${issue.rowId}-${index}`">
        {{ issue.message }}
      </div>
      <div v-if="issues.length > 8">……另有 {{ issues.length - 8 }} 项</div>
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-head">
          <div>
            <strong>1、合并方式取得的长期股权投资初始投资成本</strong>
            <span class="section-note">原底稿第7—19行</span>
          </div>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addMergerRow">
            新增公司
          </el-button>
        </div>
      </template>

      <el-table :data="mergerRows" border size="small" row-key="id" empty-text="暂无一次合并测试">
        <el-table-column label="公司名称" min-width="150" fixed="left">
          <template #default="{ row }">
            <TextCell :row="row" field="investeeName" :readonly="isReadonly" @change="updateMergerText" />
          </template>
        </el-table-column>
        <el-table-column label="合并日" min-width="135">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.acquisitionDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              :class="{ 'required-select': !row.acquisitionDate }"
              @change="persistRows"
            />
            <span v-else>{{ display(row.acquisitionDate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最终控制方" min-width="140">
          <template #default="{ row }">
            <TextCell :row="row" field="finalController" :readonly="isReadonly" @change="updateMergerText" />
          </template>
        </el-table-column>
        <el-table-column label="会计政策一致" min-width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.accountingPolicyConsistent"
              clearable
              size="small"
              :class="{ 'required-select': !row.accountingPolicyConsistent }"
              @change="persistRows"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ display(row.accountingPolicyConsistent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="政策调整说明" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.accountingPolicyNote"
              size="small"
              :disabled="row.accountingPolicyConsistent !== '否'"
              :class="{ 'required-input': row.accountingPolicyConsistent === '否' && !row.accountingPolicyNote }"
              placeholder="不一致时必填"
              @change="value => updateMergerText(row, 'accountingPolicyNote', value)"
            />
            <span v-else>{{ display(row.accountingPolicyNote) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="被合并方所有者权益账面价值①" min-width="180" align="right">
          <template #default="{ row }">
            <NumberCell :row="row" field="ownerEquityBookValue" :readonly="isReadonly" @change="updateMergerNumber" />
          </template>
        </el-table-column>
        <el-table-column label="合并后出资比例②" min-width="130" align="right">
          <template #default="{ row }">
            <RatioCell :row="row" field="ownershipRatio" :readonly="isReadonly" @change="updateMergerNumber" />
          </template>
        </el-table-column>
        <el-table-column label="初始投资成本③=①×②" min-width="155" align="right">
          <template #default="{ row }"><FormulaAmount :value="row.initialInvestmentCost" /></template>
        </el-table-column>
        <el-table-column label="支付对价账面价值④" align="center">
          <el-table-column label="现金" min-width="115" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="cashConsideration" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="非现金资产" min-width="120" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="nonCashAssetBookValue" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="债务" min-width="110" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="debtBookValue" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="权益证券面值" min-width="125" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="equitySecuritiesFaceValue" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="或有对价" min-width="110" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="contingentConsideration" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="合计" min-width="120" align="right">
            <template #default="{ row }"><FormulaAmount :value="row.totalConsideration" /></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="调整资本公积/留存收益⑤=③-④" min-width="190" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'diff-large': isSameControlDifferenceLarge(row.initialInvestmentCost, row.totalConsideration) }"
              :title="isSameControlDifferenceLarge(row.initialInvestmentCost, row.totalConsideration) ? '差额较大（超过初始成本50%），请核实对价与账面份额' : undefined"
            >{{ formatAmount(row.capitalReserveRetainedEarningsAdjustment) }}</span>
            <div class="hint-text">{{ describeCapitalReserveAdjustment(row.capitalReserveRetainedEarningsAdjustment, 'merger') }}</div>
          </template>
        </el-table-column>
        <el-table-column label="可用资本公积" min-width="125" align="right">
          <template #default="{ row }">
            <NumberCell :row="row" field="availableCapitalReserve" :readonly="isReadonly" @change="updateMergerNumber" />
          </template>
        </el-table-column>
        <el-table-column label="差额处理说明" min-width="210">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.adjustmentTreatment"
              type="textarea"
              :rows="2"
              :class="{ 'required-input': row.capitalReserveRetainedEarningsAdjustment !== 0 && !row.adjustmentTreatment }"
              placeholder="说明调整资本公积及不足冲减留存收益的金额"
              @change="value => updateMergerText(row, 'adjustmentTreatment', value)"
            />
            <span v-else>{{ display(row.adjustmentTreatment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" min-width="100">
          <template #default="{ row }">
            <TextCell :row="row" field="indexRef" :readonly="isReadonly" @change="updateMergerText" />
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="125">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.auditConclusion"
              clearable
              size="small"
              @change="persistRows"
            >
              <el-option label="无差异" value="无差异" />
              <el-option label="差异可接受" value="差异可接受" />
              <el-option label="差异需调整" value="差异需调整" />
            </el-select>
            <span v-else>{{ display(row.auditConclusion) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="62" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeMergerRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-head">
          <div>
            <strong>2、通过多次交易分步实现的同一控制下企业合并</strong>
            <span class="section-note">不构成一揽子交易；原底稿第21—31行</span>
          </div>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addStepCompany">
            新增公司
          </el-button>
        </div>
      </template>

      <el-empty v-if="!stepSummaries.length" description="暂无分步合并测试" :image-size="60" />
      <div v-for="summary in stepSummaries" :key="summary.companyId" class="step-company">
        <div class="step-company-head">
          <strong>{{ summary.companyName || '未命名公司' }}</strong>
          <div>
            <el-button v-if="!isReadonly" size="small" link type="primary" @click="addStepTransaction(summary)">
              新增交易
            </el-button>
            <el-button v-if="!isReadonly" size="small" link type="danger" @click="removeStepCompany(summary.companyId)">
              删除公司
            </el-button>
          </div>
        </div>
        <el-table :data="stepRowsFor(summary.companyId)" border size="small" row-key="id">
          <el-table-column label="次别" width="75" align="center">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.transactionNo" :min="1" :controls="false" size="small" @change="persistRows" />
              <span v-else>{{ row.transactionNo }}</span>
            </template>
          </el-table-column>
          <el-table-column label="交易日期" min-width="135">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.transactionDate" type="date" value-format="YYYY-MM-DD" size="small" @change="persistRows" />
              <span v-else>{{ display(row.transactionDate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="购买比例①" min-width="110" align="right">
            <template #default="{ row }"><RatioCell :row="row" field="purchaseRatio" :readonly="isReadonly" @change="updateStepNumber" /></template>
          </el-table-column>
          <el-table-column label="支付对价②" min-width="120" align="right">
            <template #default="{ row }"><NumberCell :row="row" field="consideration" :readonly="isReadonly" @change="updateStepNumber" /></template>
          </el-table-column>
          <el-table-column label="交易时被投资方可辨认净资产账面价值" min-width="210" align="right">
            <template #default="{ row }"><NumberCell :row="row" field="netAssetsBookValue" :readonly="isReadonly" @change="updateStepNumber" /></template>
          </el-table-column>
          <el-table-column label="原投资累计其他综合收益/损益调整等③" min-width="230" align="right">
            <template #default="{ row }"><NumberCell :row="row" field="priorInvestmentAdjustments" :readonly="isReadonly" @change="updateStepNumber" /></template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="62">
            <template #default="{ row }"><el-button link type="danger" size="small" @click="removeStepRow(row.id)">删除</el-button></template>
          </el-table-column>
        </el-table>
        <el-descriptions :column="3" border size="small" class="step-summary">
          <el-descriptions-item label="合并日（取得控制权）">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="summary.acquisitionDate || undefined"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              @change="value => updateStepGroupField(summary.companyId, 'acquisitionDate', value)"
            />
            <span v-else>{{ display(summary.acquisitionDate) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="是否一揽子交易">
            <el-select
              v-if="!isReadonly"
              :model-value="summary.isPackageDeal"
              clearable
              size="small"
              @change="value => updateStepGroupField(summary.companyId, 'isPackageDeal', value)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ display(summary.isPackageDeal) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="原持股账面价值">
            <el-input-number
              v-if="!isReadonly"
              :model-value="summary.priorHoldingBookValue || undefined"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-number"
              @change="value => updateStepGroupField(summary.companyId, 'priorHoldingBookValue', value)"
            />
            <span v-else>{{ formatAmount(summary.priorHoldingBookValue) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="累计购买比例①">{{ formatPercent(summary.cumulativeRatio) }}</el-descriptions-item>
          <el-descriptions-item label="累计支付对价②">{{ formatAmount(summary.cumulativeConsideration) }}</el-descriptions-item>
          <el-descriptions-item label="累计原投资调整③">{{ formatAmount(summary.cumulativePriorAdjustments) }}</el-descriptions-item>
          <el-descriptions-item label="合并日净资产账面价值④">{{ formatAmount(summary.mergerDateNetAssets) }}</el-descriptions-item>
          <el-descriptions-item label="初始投资成本⑤=④×①">{{ formatAmount(summary.initialInvestmentCost) }}</el-descriptions-item>
          <el-descriptions-item label="调整⑥=②+原账面+③−⑤">
            {{ formatAmount(summary.capitalReserveRetainedEarningsAdjustment) }}
            <div class="hint-text">{{ summary.adjustmentHint }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="可用资本公积">
            <el-input-number
              v-if="!isReadonly"
              :model-value="summary.availableCapitalReserve ?? undefined"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-number"
              @change="value => updateStepGroupField(summary.companyId, 'availableCapitalReserve', value)"
            />
            <span v-else>{{ display(summary.availableCapitalReserve) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="不构成一揽子交易依据" :span="2">
            <el-input
              v-if="!isReadonly"
              :model-value="summary.notPackageBasis"
              size="small"
              :disabled="summary.isPackageDeal === '是'"
              placeholder="说明各次交易独立定价、非整体安排等判断依据"
              @change="value => updateStepGroupField(summary.companyId, 'notPackageBasis', value)"
            />
            <span v-else>{{ display(summary.notPackageBasis) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="索引/备注" :span="3">
            <el-input
              v-if="!isReadonly"
              :model-value="summary.indexRef"
              size="small"
              @change="value => updateStepGroupField(summary.companyId, 'indexRef', value)"
            />
            <span v-else>{{ display(summary.indexRef) }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-head">
          <div>
            <strong>3、反向购买</strong>
            <span class="section-note">原底稿第33—37行</span>
          </div>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addReverseRow">
            新增交易
          </el-button>
        </div>
      </template>
      <el-table :data="reverseRows" border size="small" row-key="id" empty-text="暂无反向购买测试">
        <el-table-column label="交易内容" min-width="150">
          <template #default="{ row }"><TextCell :row="row" field="transactionContent" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column label="会计上的购买方" min-width="140">
          <template #default="{ row }"><TextCell :row="row" field="accountingAcquirer" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column label="会计上的购买方的股东" min-width="170">
          <template #default="{ row }"><TextCell :row="row" field="acquirerShareholders" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column label="会计上的被购买方（上市公司）" min-width="190">
          <template #default="{ row }"><TextCell :row="row" field="accountingAcquiree" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column label="被购买方原股东" min-width="160">
          <template #default="{ row }"><TextCell :row="row" field="acquireeOriginalShareholders" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column label="构成反向购买的依据" min-width="220">
          <template #default="{ row }"><TextAreaCell :row="row" field="reversePurchaseBasis" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column label="是否构成业务及判断依据" min-width="220">
          <template #default="{ row }"><TextAreaCell :row="row" field="businessDeterminationBasis" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column label="索引号" min-width="100">
          <template #default="{ row }"><TextCell :row="row" field="indexRef" :readonly="isReadonly" @change="updateReverseText" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="62" fixed="right">
          <template #default="{ row }"><el-button link type="danger" size="small" @click="removeReverseRow(row.id)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计说明</template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :readonly="isReadonly"
        placeholder="说明最终控制方、会计政策统一、非一揽子判断、反向购买判断及差异处理。"
        @change="saveAuditNote"
      />
    </el-card>
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="card-head">
          <span>审计结论</span>
          <el-button size="small" type="primary" link @click="handleAiConclusion">🤖 AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :readonly="isReadonly"
        placeholder="总结初始投资成本、资本公积/留存收益调整及特殊交易判断是否恰当。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <ol>
        <li>合并前会计政策不一致的，应先按重要性原则统一政策，再计算账面价值份额。</li>
        <li>一次合并：③=①×②，④为现金、非现金资产、债务、权益证券面值及或有对价账面价值合计，⑤=③-④。</li>
        <li>分步合并：⑤=④×累计①；⑥=累计对价②+原持股账面价值+原投资调整③−⑤。</li>
        <li>若各次交易构成一揽子交易，应作为一项取得控制权交易处理，不适用第2部分。</li>
        <li>反向购买应同时识别会计上的购买方，并判断会计上的被购买方是否构成业务。</li>
      </ol>
    </details>

    <input ref="fileInputRef" type="file" accept=".xlsx" class="hidden-input" @change="handleFileChange">
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, inject, onMounted, reactive, ref, toRef } from 'vue'
import { ElInput, ElInputNumber, ElMessage, ElMessageBox } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import http from '@/utils/http'
import { extractG7AiText } from '../../composables/g7AiText'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'
import {
  createSameControlMergerRow,
  createSameControlReverseRow,
  createSameControlStepRow,
  describeCapitalReserveAdjustment,
  extractSameControlInvesteesFromG7Judgment,
  extractSubsidiaryNamesFromG72,
  extractSubsidiaryNamesFromG74,
  isSameControlDifferenceLarge,
  normalizeSameControlRows,
  recalcSameControlMergerRow,
  summarizeSameControlSteps,
  syncMergerRowsFromSameControlNames,
  validateSameControlRows,
  type G7SameControlMergerRow,
  type G7SameControlReverseRow,
  type G7SameControlStepRow,
  type G7SameControlStepSummary,
  type G7SameControlStoredRow,
  type G7SameControlValidationContext,
  type G7YesNo,
} from './g7SameControlModel'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => !!props.readonly)
const runtime = inject(WorkpaperRuntimeContextKey, null)
const scheduleAutoSnapshot = runtime?.version?.scheduleAutoSnapshot ?? (() => undefined)
const formData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onAfterSave: () => scheduleAutoSnapshot(),
})
const { exportTemplate, exportData, importData } = useG7SubImportExport({ wpId: toRef(props, 'wpId') })

const ROWS_KEY = 'G7-8-rows'
const NOTE_KEY = 'G7-8-same-control-audit-note'
const CONCLUSION_KEY = 'G7-8-same-control-audit-conclusion'
const mergerRows = reactive<G7SameControlMergerRow[]>([])
const stepRows = reactive<G7SameControlStepRow[]>([])
const reverseRows = reactive<G7SameControlReverseRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const syncing = ref(false)
const validationContext = reactive<G7SameControlValidationContext>({})

const allRows = computed<G7SameControlStoredRow[]>(() => [
  ...mergerRows,
  ...stepRows,
  ...reverseRows,
])
const stepSummaries = computed(() => summarizeSameControlSteps(stepRows))
const issues = computed(() => validateSameControlRows(allRows.value, validationContext))
const errorCount = computed(() => issues.value.filter(issue => issue.severity === 'error').length)
const warningCount = computed(() => issues.value.filter(issue => issue.severity === 'warning').length)
const saveStatusText = computed(() => ({
  idle: '',
  pending: '待保存',
  saving: '保存中…',
  saved: '已保存',
  error: '保存失败',
}[formData.savePhase.value]))

function display(value: unknown): string {
  return value === '' || value == null ? '—' : String(value)
}
function formatAmount(value: unknown): string {
  return fmtAmount(Number(value ?? 0))
}
function formatPercent(value: number): string {
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- percentage display, not monetary amount
  return `${(value * 100).toFixed(2)}%`
}
function persistRows(): void {
  if (isReadonly.value) return
  formData.debouncedSave(ROWS_KEY, {
    conclusion: JSON.stringify(allRows.value),
    remark: 'G7-8同控初始计量三类测试',
  })
}
function updateMergerText(row: G7SameControlMergerRow, field: keyof G7SameControlMergerRow, value: unknown): void {
  ;(row as any)[field] = value == null ? '' : String(value)
  persistRows()
}
function updateMergerNumber(row: G7SameControlMergerRow, field: keyof G7SameControlMergerRow, value: unknown): void {
  ;(row as any)[field] = value == null || value === '' ? null : Number(value)
  recalcSameControlMergerRow(row)
  persistRows()
}
function updateStepNumber(row: G7SameControlStepRow, field: keyof G7SameControlStepRow, value: unknown): void {
  ;(row as any)[field] = value == null || value === '' ? null : Number(value)
  persistRows()
}
function updateReverseText(row: G7SameControlReverseRow, field: keyof G7SameControlReverseRow, value: unknown): void {
  ;(row as any)[field] = value == null ? '' : String(value)
  persistRows()
}

async function promptName(title: string): Promise<string | null> {
  try {
    const { value } = await ElMessageBox.prompt('请输入公司名称', title, {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '公司名称不能为空',
    })
    return value.trim()
  } catch {
    return null
  }
}
async function addMergerRow(): Promise<void> {
  const name = await promptName('新增合并方式取得的子公司')
  if (!name) return
  if (mergerRows.some(row => row.investeeName === name) || stepRows.some(row => row.companyName === name)) {
    ElMessage.warning(`「${name}」已存在于一次合并或分步合并`)
    return
  }
  mergerRows.push(createSameControlMergerRow(mergerRows.length + 1, name))
  persistRows()
}
function removeMergerRow(id: string): void {
  const index = mergerRows.findIndex(row => row.id === id)
  if (index < 0) return
  mergerRows.splice(index, 1)
  mergerRows.forEach((row, i) => { row.seq = i + 1 })
  persistRows()
}
async function addStepCompany(): Promise<void> {
  const name = await promptName('新增分步实现同控合并的公司')
  if (!name) return
  if (stepRows.some(row => row.companyName === name) || mergerRows.some(row => row.investeeName === name)) {
    ElMessage.warning(`「${name}」已存在于一次合并或分步合并`)
    return
  }
  const companyId = `step-company-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  stepRows.push(createSameControlStepRow(companyId, name, 1))
  persistRows()
}
function addStepTransaction(summary: G7SameControlStepSummary): void {
  const rows = stepRowsFor(summary.companyId)
  const next = createSameControlStepRow(summary.companyId, summary.companyName, rows.length + 1)
  next.priorHoldingBookValue = summary.priorHoldingBookValue || null
  next.isPackageDeal = summary.isPackageDeal
  next.notPackageBasis = summary.notPackageBasis
  next.availableCapitalReserve = summary.availableCapitalReserve
  next.acquisitionDate = summary.acquisitionDate
  next.indexRef = summary.indexRef
  stepRows.push(next)
  persistRows()
}
function stepRowsFor(companyId: string): G7SameControlStepRow[] {
  return stepRows.filter(row => row.companyId === companyId)
}
function removeStepRow(id: string): void {
  const row = stepRows.find(item => item.id === id)
  if (!row) return
  const index = stepRows.indexOf(row)
  stepRows.splice(index, 1)
  stepRowsFor(row.companyId).forEach((item, i) => {
    item.seq = i + 1
    item.transactionNo = i + 1
  })
  persistRows()
}
function removeStepCompany(companyId: string): void {
  for (let index = stepRows.length - 1; index >= 0; index -= 1) {
    if (stepRows[index].companyId === companyId) stepRows.splice(index, 1)
  }
  persistRows()
}
function updateStepGroupField(
  companyId: string,
  field: 'notPackageBasis' | 'indexRef' | 'isPackageDeal' | 'priorHoldingBookValue' | 'availableCapitalReserve' | 'acquisitionDate',
  value: unknown,
): void {
  for (const row of stepRowsFor(companyId)) {
    if (field === 'priorHoldingBookValue' || field === 'availableCapitalReserve') {
      ;(row as any)[field] = value == null || value === '' ? null : Number(value)
    } else if (field === 'isPackageDeal') {
      row.isPackageDeal = (value === '是' || value === '否' ? value : '') as G7YesNo
    } else {
      row[field] = value == null ? '' : String(value)
    }
  }
  persistRows()
}
function addReverseRow(): void {
  reverseRows.push(createSameControlReverseRow(reverseRows.length + 1))
  persistRows()
}
function removeReverseRow(id: string): void {
  const index = reverseRows.findIndex(row => row.id === id)
  if (index < 0) return
  reverseRows.splice(index, 1)
  reverseRows.forEach((row, i) => { row.seq = i + 1 })
  persistRows()
}
function handleAddCommand(command: string): void {
  if (command === 'merger') void addMergerRow()
  if (command === 'step') void addStepCompany()
  if (command === 'reverse') addReverseRow()
}

function parseRows(value: unknown): G7SameControlStoredRow[] {
  if (Array.isArray(value)) return normalizeSameControlRows(value)
  if (typeof value !== 'string' || !value.trim()) return []
  try {
    return normalizeSameControlRows(JSON.parse(value))
  } catch {
    return []
  }
}
function hydrate(rows: G7SameControlStoredRow[]): void {
  mergerRows.splice(0, mergerRows.length, ...rows.filter((row): row is G7SameControlMergerRow => row.section === 'merger'))
  stepRows.splice(0, stepRows.length, ...rows.filter((row): row is G7SameControlStepRow => row.section === 'step'))
  reverseRows.splice(0, reverseRows.length, ...rows.filter((row): row is G7SameControlReverseRow => row.section === 'reverse'))
}
function rowsFromHtmlData(): G7SameControlStoredRow[] {
  const data = props.htmlData?.sameControl ?? props.htmlData?.same_control ?? props.htmlData
  return normalizeSameControlRows(data?.rows ?? [])
}

function findChecklistItem(items: any[], itemId: string): any | undefined {
  return items.find((item: any) => item.item_id === itemId)
}

async function refreshValidationContext(): Promise<void> {
  if (!props.wpId) return
  try {
    const response = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: any[] = Array.isArray(response) ? response : (response?.data ?? [])
    const g77 = findChecklistItem(items, 'G7-7-control-judgment-data')
    const g72 = findChecklistItem(items, 'G7-2-rows')
    const g74 = findChecklistItem(items, 'G7-4-rows')
    validationContext.sameControlInvestees = extractSameControlInvesteesFromG7Judgment(g77?.conclusion)
    validationContext.detailInvestees = extractSubsidiaryNamesFromG72(g72?.conclusion)
    validationContext.basicInfoInvestees = extractSubsidiaryNamesFromG74(g74?.conclusion)
  } catch {
    /* 勾稽名单加载失败不阻断编辑 */
  }
}

async function syncFromRelatedSheets(): Promise<void> {
  if (isReadonly.value || syncing.value) return
  syncing.value = true
  try {
    await refreshValidationContext()
    const names = validationContext.sameControlInvestees ?? []
    if (!names.length) {
      ElMessage.warning('G7-7 中未找到「控制+同一控制下企业合并」单位，仅已刷新名单勾稽')
      return
    }
    const result = syncMergerRowsFromSameControlNames([...mergerRows], names)
    mergerRows.splice(0, mergerRows.length, ...result.rows)
    persistRows()
    ElMessage.success(`已从 G7-7 同步同控单位：新增 ${result.added} 家`)
  } catch {
    ElMessage.error('同步 G7-7/G7-2/G7-4 失败')
  } finally {
    syncing.value = false
  }
}

function handleImportExportCommand(command: string): void {
  if (command === 'template') void exportTemplate('G7-8')
  if (command === 'export') void exportData('G7-8')
  if (command === 'import') fileInputRef.value?.click()
}
async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importData('G7-8', file)
  if (!result) return
  await formData.loadResponses()
  hydrate(parseRows(formData.data.value.get(ROWS_KEY)?.conclusion))
}
function saveAuditNote(value: string): void {
  if (isReadonly.value) return
  formData.debouncedSave(NOTE_KEY, { remark: value, conclusion: null })
}
function saveAuditConclusion(value: string): void {
  if (isReadonly.value) return
  formData.debouncedSave(CONCLUSION_KEY, { remark: value, conclusion: null })
}
async function handleAiConclusion(): Promise<void> {
  try {
    const response = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/initial-measurement-conclusion`,
      {
        existingContent: auditConclusion.value,
        relatedContext: {
          sheet: 'G7-8',
          rows: allRows.value,
          stepSummaries: stepSummaries.value,
          validationIssues: issues.value,
        },
      },
    )
    const data = response?.data?.data ?? response?.data ?? response
    const text = extractG7AiText(data)
    if (!text) throw new Error('empty')
    auditConclusion.value = String(text)
    saveAuditConclusion(auditConclusion.value)
    ElMessage.success('AI结论生成完成')
  } catch {
    ElMessage.warning('AI结论生成失败，请手工填写')
  }
}

const TextCell = defineComponent({
  props: { row: { type: Object, required: true }, field: { type: String, required: true }, readonly: Boolean },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', display((componentProps.row as any)[componentProps.field]))
      : h(ElInput, {
          modelValue: (componentProps.row as any)[componentProps.field],
          size: 'small',
          onChange: (value: string) => emit('change', componentProps.row, componentProps.field, value),
        })
  },
})
const TextAreaCell = defineComponent({
  props: { row: { type: Object, required: true }, field: { type: String, required: true }, readonly: Boolean },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', { class: 'multiline' }, display((componentProps.row as any)[componentProps.field]))
      : h(ElInput, {
          modelValue: (componentProps.row as any)[componentProps.field],
          type: 'textarea',
          rows: 2,
          onChange: (value: string) => emit('change', componentProps.row, componentProps.field, value),
        })
  },
})
const NumberCell = defineComponent({
  props: { row: { type: Object, required: true }, field: { type: String, required: true }, readonly: Boolean },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', formatAmount((componentProps.row as any)[componentProps.field]))
      : h(ElInputNumber, {
          modelValue: (componentProps.row as any)[componentProps.field],
          controls: false,
          precision: 2,
          size: 'small',
          class: 'cell-number',
          onChange: (value: number | undefined) => emit('change', componentProps.row, componentProps.field, value),
        })
  },
})
const RatioCell = defineComponent({
  props: { row: { type: Object, required: true }, field: { type: String, required: true }, readonly: Boolean },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', formatPercent(Number((componentProps.row as any)[componentProps.field] ?? 0)))
      : h(ElInputNumber, {
          modelValue: (componentProps.row as any)[componentProps.field],
          controls: false,
          precision: 6,
          min: 0,
          max: 1,
          step: 0.01,
          size: 'small',
          class: 'cell-number',
          onChange: (value: number | undefined) => emit('change', componentProps.row, componentProps.field, value),
        })
  },
})
const FormulaAmount = defineComponent({
  props: { value: { type: Number, required: true } },
  setup(componentProps) {
    return () => h('span', { class: 'formula-cell' }, formatAmount(componentProps.value))
  },
})

onMounted(async () => {
  await formData.load()
  const saved = parseRows(formData.data.value.get(ROWS_KEY)?.conclusion)
  hydrate(saved.length ? saved : rowsFromHtmlData())
  auditNote.value = formData.data.value.get(NOTE_KEY)?.remark ?? ''
  auditConclusion.value = formData.data.value.get(CONCLUSION_KEY)?.remark ?? ''
  await refreshValidationContext()
})
</script>

<style scoped>
.g7-tab-same-control { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head, .card-head, .summary-bar, .step-company-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.section-head { margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 16px; }
.sheet-subtitle, .section-note { margin-left: 8px; color: #909399; font-size: 12px; }
.head-actions, .summary-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.objective-alert, .methodology-context, .summary-bar, .validation-alert { margin-bottom: 12px; }
.methodology-context { padding: 12px 16px; border-left: 4px solid #e6a23c; background: #fdf6ec; line-height: 1.7; }
.section-card { margin-bottom: 14px; }
.formula-cell { color: #1d4ed8; font-weight: 600; border-bottom: 1px dashed #94a3b8; }
.formula-cell.diff-large {
  color: #b45309;
  background: #fff7ed;
  padding: 0 4px;
  border-radius: 2px;
  border-bottom-color: #f59e0b;
}
.hint-text { margin-top: 2px; color: #909399; font-size: 11px; line-height: 1.3; }
.required-input :deep(.el-textarea__inner),
.required-input :deep(.el-input__inner) { box-shadow: 0 0 0 1px #e6a23c inset; }
.required-select :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset; }
.cell-number { width: 100%; }
.step-company { margin-bottom: 16px; border: 1px solid #ebeef5; border-radius: 6px; padding: 10px; }
.step-company-head { margin-bottom: 8px; }
.step-summary { margin-top: 8px; }
.conclusion-card { margin-top: 14px; }
.guidance-details { margin-top: 14px; padding: 10px 14px; border: 1px solid #e4e7ed; border-radius: 6px; color: #606266; }
.guidance-details summary { cursor: pointer; font-weight: 600; }
.guidance-details ol { line-height: 1.8; padding-left: 20px; }
.multiline { white-space: pre-wrap; }
.hidden-input { display: none; }
.save-status { font-size: 12px; color: #909399; min-width: 3.5em; }
.save-pending, .save-saving { color: #e6a23c; }
.save-saved { color: #67c23a; }
.save-error { color: #f56c6c; }
</style>
