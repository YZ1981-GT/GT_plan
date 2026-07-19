<template>
  <div class="g7-tab-not-same-control">
    <div class="section-head">
      <div>
        <h3 class="sheet-title">G7-9 子公司初始计量测试表（非同一控制）</h3>
        <div class="sheet-subtitle">按一次购买、分步合并和反向购买三类交易分别测试</div>
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
              <el-dropdown-item command="merger">一次购买取得</el-dropdown-item>
              <el-dropdown-item command="step">分步实现非同控合并</el-dropdown-item>
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
        <el-button size="small" @click="openReviewDialog('G7-9-not-same-control')">💬复核</el-button>
        <GtIndexChip value="wp:G7-9" :context-project-id="projectId" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      审计目标：确定被审计单位对非同一控制下取得子公司的长期股权投资初始计量是否恰当。
    </el-alert>

    <div class="methodology-context">
      <strong>核心逻辑（CAS20 / CAS2）：</strong>
      购买方按公允价值计量合并对价；⑥=③+④，⑦=③−⑤，⑧=⑥−①×②。
      直接相关中介费用计入当期损益，不构成合并成本；⑧为负数时，须复核各项计量并说明廉价购买利得复核过程。
      少数股东权益按可辨认净资产公允价值份额计量。
      不调整资本公积（与 G7-8 同控不同）。
    </div>

    <div class="summary-bar">
      <div class="summary-left">
        <el-tag type="info">一次购买 {{ mergerRows.length }} 家</el-tag>
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
            <strong>1、合并方式取得的长期股权投资初始投资成本（非同控）</strong>
            <span class="section-note">对价按公允价值；商誉在合并报表确认</span>
          </div>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addMergerRow">
            新增公司
          </el-button>
        </div>
      </template>

      <el-table :data="mergerRows" border size="small" row-key="id" empty-text="暂无一次购买测试">
        <el-table-column label="公司名称" min-width="140" fixed="left">
          <template #default="{ row }">
            <TextCell :row="row" field="investeeName" :readonly="isReadonly" @change="updateMergerText" />
          </template>
        </el-table-column>
        <el-table-column label="购买日" min-width="130">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.acquisitionDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width: 100%"
              @change="persistRows"
            />
            <span v-else>{{ display(row.acquisitionDate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="购买日证据索引" min-width="130">
          <template #default="{ row }">
            <TextCell :row="row" field="acquisitionDateEvidenceRef" :readonly="isReadonly" @change="updateMergerText" />
          </template>
        </el-table-column>
        <el-table-column label="可辨认净资产FV①" min-width="145" align="right">
          <template #default="{ row }">
            <NumberCell :row="row" field="acquireeIdentifiableNetAssetsFV" :readonly="isReadonly" @change="updateMergerNumber" />
          </template>
        </el-table-column>
        <el-table-column label="持股比例②" min-width="110" align="right">
          <template #default="{ row }">
            <RatioCell :row="row" field="ownershipRatio" :readonly="isReadonly" @change="updateMergerNumber" />
          </template>
        </el-table-column>
        <el-table-column label="支付对价公允价值③" align="center">
          <el-table-column label="现金" min-width="110" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="cashConsideration" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="非现金资产FV" min-width="120" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="nonCashAssetFV" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="债务FV" min-width="110" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="debtFV" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="权益证券FV" min-width="120" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="equitySecuritiesFV" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="或有对价FV" min-width="115" align="right">
            <template #default="{ row }">
              <NumberCell :row="row" field="contingentConsiderationFV" :readonly="isReadonly" @change="updateMergerNumber" />
            </template>
          </el-table-column>
          <el-table-column label="合计③" min-width="120" align="right">
            <template #default="{ row }"><FormulaAmount :value="row.totalConsiderationFV" /></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="购买日前持股购买日FV④" min-width="170" align="right">
          <template #default="{ row }">
            <NumberCell :row="row" field="priorHoldingFV" :readonly="isReadonly" @change="updateMergerNumber" />
          </template>
        </el-table-column>
        <el-table-column label="付出对价账面价值⑤" min-width="155" align="right">
          <template #default="{ row }">
            <NumberCell :row="row" field="considerationBookValue" :readonly="isReadonly" @change="updateMergerNumber" />
          </template>
        </el-table-column>
        <el-table-column label="直接费用（费用化）" min-width="130" align="right">
          <template #default="{ row }">
            <NumberCell :row="row" field="acquisitionCostsExpensed" :readonly="isReadonly" @change="updateMergerNumber" />
            <div class="hint-text">不入成本</div>
          </template>
        </el-table-column>
        <el-table-column label="初始投资成本⑥=③+④" min-width="170" align="right">
          <template #default="{ row }"><FormulaAmount :value="row.initialInvestmentCost" /></template>
        </el-table-column>
        <el-table-column label="对价损益⑦=③−⑤" min-width="145" align="right">
          <template #default="{ row }">
            <FormulaAmount :value="row.considerationGainLoss" />
            <div class="hint-text">计入当期损益</div>
          </template>
        </el-table-column>
        <el-table-column label="享有FV份额①×②" min-width="140" align="right">
          <template #default="{ row }"><FormulaAmount :value="row.shareOfFV" /></template>
        </el-table-column>
        <el-table-column label="少数股东权益份额" min-width="145" align="right">
          <template #default="{ row }">
            <FormulaAmount :value="row.nonControllingInterestShare" />
            <div class="hint-text">①×(1−②)，CAS20口径</div>
          </template>
        </el-table-column>
        <el-table-column label="商誉⑧=⑥−①×②" min-width="190" align="right">
          <template #default="{ row }">
            <el-tag v-if="row.goodwill > 0.005" type="success" size="small" effect="plain">
              商誉 {{ formatAmount(row.goodwill) }}
            </el-tag>
            <el-tag v-else-if="row.goodwill < -0.005" type="primary" size="small" effect="plain">
              廉价购买利得 {{ formatAmount(Math.abs(row.goodwill)) }}
            </el-tag>
            <span v-else class="formula-cell">—</span>
            <div class="hint-text">{{ describeGoodwill(row.goodwill) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="廉价购买复核" min-width="145">
          <template #default="{ row }">
            <template v-if="row.goodwill < -0.005">
              <el-select
                v-if="!isReadonly"
                v-model="row.bargainPurchaseReviewed"
                clearable
                size="small"
                :class="{ 'required-empty': !row.bargainPurchaseReviewed }"
                @change="persistRows"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ display(row.bargainPurchaseReviewed) }}</span>
            </template>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="廉价购买复核说明" min-width="220">
          <template #default="{ row }">
            <template v-if="row.goodwill < -0.005">
              <el-input
                v-if="!isReadonly"
                v-model="row.bargainPurchaseReviewNote"
                type="textarea"
                :rows="2"
                :class="{ 'required-empty': !row.bargainPurchaseReviewNote.trim() }"
                @change="persistRows"
              />
              <span v-else class="multiline">{{ display(row.bargainPurchaseReviewNote) }}</span>
            </template>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="对价证据索引" min-width="125">
          <template #default="{ row }">
            <TextCell :row="row" field="considerationEvidenceRef" :readonly="isReadonly" @change="updateMergerText" />
          </template>
        </el-table-column>
        <el-table-column label="评估报告索引" min-width="125">
          <template #default="{ row }">
            <TextCell :row="row" field="valuationReportRef" :readonly="isReadonly" @change="updateMergerText" />
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
            <strong>2、通过多次交易分步实现的非同一控制下企业合并</strong>
            <span class="section-note">不构成一揽子交易；原持股按购买日FV重估</span>
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
              <el-input-number v-if="!isReadonly" v-model="row.transactionNo" :min="1" :controls="false" size="small" @change="value => updateStepNumber(row, 'transactionNo', value)" />
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
          <el-table-column label="支付对价FV②" min-width="120" align="right">
            <template #default="{ row }"><NumberCell :row="row" field="considerationFV" :readonly="isReadonly" @change="updateStepNumber" /></template>
          </el-table-column>
          <el-table-column label="交易时可辨认净资产FV③" min-width="190" align="right">
            <template #default="{ row }"><NumberCell :row="row" field="netAssetsFVAtTxn" :readonly="isReadonly" @change="updateStepNumber" /></template>
          </el-table-column>
          <el-table-column label="享有FV份额④=①×③" min-width="155" align="right">
            <template #default="{ row }"><FormulaAmount :value="row.shareOfFVAtTxn" /></template>
          </el-table-column>
          <el-table-column label="每笔商誉⑤=②−④" min-width="145" align="right">
            <template #default="{ row }"><FormulaAmount :value="row.goodwillAtTxn" /></template>
          </el-table-column>
          <el-table-column label="权益法OCI等⑥" min-width="145" align="right">
            <template #default="{ row }">
              <NumberCell
                :row="row"
                field="priorEquityMethodAdjustments"
                :readonly="isReadonly"
                @change="updateStepNumber"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="62">
            <template #default="{ row }"><el-button link type="danger" size="small" @click="removeStepRow(row.id)">删除</el-button></template>
          </el-table-column>
        </el-table>
        <el-descriptions :column="3" border size="small" class="step-summary">
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
          <el-descriptions-item label="原持股账面价值（备查）">
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
          <el-descriptions-item label="原持股购买日FV（备查）">
            <el-input-number
              v-if="!isReadonly"
              :model-value="summary.priorHoldingFV || undefined"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-number"
              @change="value => updateStepGroupField(summary.companyId, 'priorHoldingFV', value)"
            />
            <span v-else>{{ formatAmount(summary.priorHoldingFV) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="原持股重估损益">
            {{ formatAmount(summary.remeasurementGain) }}
            <div class="hint-text">FV − 账面价值 → 当期损益</div>
          </el-descriptions-item>
          <el-descriptions-item label="累计权益法OCI等⑥">
            <FormulaAmount :value="summary.priorEquityMethodAdjustments" />
          </el-descriptions-item>
          <el-descriptions-item label="累计持股比例">{{ formatPercent(summary.cumulativeRatio) }}</el-descriptions-item>
          <el-descriptions-item label="累计支付对价②">{{ formatAmount(summary.cumulativeConsiderationFV) }}</el-descriptions-item>
          <el-descriptions-item label="累计享有FV份额④">{{ formatAmount(summary.cumulativeShareOfFV) }}</el-descriptions-item>
          <el-descriptions-item label="累计每笔商誉⑤">{{ formatAmount(summary.cumulativeTxnGoodwill) }}</el-descriptions-item>
          <el-descriptions-item label="个别报表初始成本⑦">
            <FormulaAmount :value="summary.parentInitialCost" />
            <div class="hint-text">累计支付对价② + 权益法OCI等⑥</div>
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
          <el-descriptions-item label="购买日证据索引">
            <el-input
              v-if="!isReadonly"
              :model-value="summary.acquisitionDateEvidenceRef"
              size="small"
              @change="value => updateStepGroupField(summary.companyId, 'acquisitionDateEvidenceRef', value)"
            />
            <span v-else>{{ display(summary.acquisitionDateEvidenceRef) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="对价证据索引">
            <el-input
              v-if="!isReadonly"
              :model-value="summary.considerationEvidenceRef"
              size="small"
              @change="value => updateStepGroupField(summary.companyId, 'considerationEvidenceRef', value)"
            />
            <span v-else>{{ display(summary.considerationEvidenceRef) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="评估报告索引">
            <el-input
              v-if="!isReadonly"
              :model-value="summary.valuationReportRef"
              size="small"
              @change="value => updateStepGroupField(summary.companyId, 'valuationReportRef', value)"
            />
            <span v-else>{{ display(summary.valuationReportRef) }}</span>
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
            <span class="section-note">识别会计购买方，并判断被购买方是否构成业务</span>
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
        <el-table-column label="是否构成业务" min-width="125">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.constitutesBusiness"
              clearable
              size="small"
              :class="{ 'required-empty': !row.constitutesBusiness }"
              @change="persistRows"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ display(row.constitutesBusiness) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务判断依据" min-width="220">
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
        placeholder="说明购买日认定、对价公允价值、可辨认净资产评估、分步合并重估、反向购买判断及差异处理。"
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
        placeholder="总结初始投资成本、商誉/廉价购买利得及特殊交易判断是否恰当。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="guidance-details">
      <summary>编制提示（非同一控制）</summary>
      <ol>
        <li>一次购买：③=对价FV合计；⑥=③+④（④为购买日前持股于购买日的FV）；⑦=③−⑤（对价FV与账面差额计入损益）；⑧=⑥−①×②（商誉/廉价购买利得）。</li>
        <li>审计、法律、评估等中介费用计入当期损益；发行证券交易费用计入证券初始确认金额。</li>
        <li>取得投资时点与评估基准日有时间差时，注意公允价值调整。</li>
        <li>分步合并（非一揽子）：每笔④=①×③、⑤=②−④；个别报表⑦=累计支付对价②+权益法OCI等⑥。</li>
        <li>一揽子交易应作为一次取得控制权，不适用分步区段。</li>
        <li>反向购买须判断会计被购买方是否构成业务；不构成业务时按资产购置处理，不得确认商誉。</li>
        <li>廉价购买利得须勾选已复核计量并说明复核过程。</li>
        <li>本底稿不调整资本公积（与G7-8同控不同）。</li>
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
import { api } from '@/services/apiProxy'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7SubImportExport } from '../../composables/useG7SubImportExport'
import { useG7SubFormData } from '../../composables/useG7SubFormData'
import {
  createNotSameControlMergerRow,
  createNotSameControlReverseRow,
  createNotSameControlStepRow,
  describeGoodwill,
  extractNotSameControlInvesteesFromG7Judgment,
  extractSubsidiaryNamesFromG72,
  extractSubsidiaryNamesFromG74,
  normalizeNotSameControlRows,
  recalcNotSameControlMergerRow,
  recalcNotSameControlStepRow,
  summarizeNotSameControlSteps,
  syncMergerRowsFromNotSameControlNames,
  validateNotSameControlRows,
  type G7NotSameControlMergerRow,
  type G7NotSameControlReverseRow,
  type G7NotSameControlStepRow,
  type G7NotSameControlStepSummary,
  type G7NotSameControlStoredRow,
  type G7NotSameControlValidationContext,
  type G7YesNo,
} from './g7NotSameControlModel'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => !!props.readonly)
const formData = useG7SubFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const { exportTemplate, exportData, importData } = useG7SubImportExport({ wpId: toRef(props, 'wpId') })

const ROWS_KEY = 'G7-9-rows'
const NOTE_KEY = 'G7-9-not-same-control-audit-note'
const CONCLUSION_KEY = 'G7-9-not-same-control-audit-conclusion'
const mergerRows = reactive<G7NotSameControlMergerRow[]>([])
const stepRows = reactive<G7NotSameControlStepRow[]>([])
const reverseRows = reactive<G7NotSameControlReverseRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const syncing = ref(false)
const validationContext = reactive<G7NotSameControlValidationContext>({})

const allRows = computed<G7NotSameControlStoredRow[]>(() => [
  ...mergerRows,
  ...stepRows,
  ...reverseRows,
])
const stepSummaries = computed(() => summarizeNotSameControlSteps(stepRows))
const issues = computed(() => validateNotSameControlRows(allRows.value, validationContext))
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
    remark: 'G7-9非同控初始计量三类测试',
  })
}
function updateMergerText(row: G7NotSameControlMergerRow, field: keyof G7NotSameControlMergerRow, value: unknown): void {
  ;(row as any)[field] = value == null ? '' : String(value)
  persistRows()
}
function updateMergerNumber(row: G7NotSameControlMergerRow, field: keyof G7NotSameControlMergerRow, value: unknown): void {
  ;(row as any)[field] = value == null || value === '' ? null : Number(value)
  recalcNotSameControlMergerRow(row)
  persistRows()
}
function updateStepNumber(row: G7NotSameControlStepRow, field: keyof G7NotSameControlStepRow, value: unknown): void {
  ;(row as any)[field] = value == null || value === '' ? null : Number(value)
  recalcNotSameControlStepRow(row)
  persistRows()
}
function updateReverseText(row: G7NotSameControlReverseRow, field: keyof G7NotSameControlReverseRow, value: unknown): void {
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
  const name = await promptName('新增一次购买取得的子公司')
  if (!name) return
  if (mergerRows.some(row => row.investeeName === name) || stepRows.some(row => row.companyName === name)) {
    ElMessage.warning(`「${name}」已存在于一次购买或分步合并`)
    return
  }
  mergerRows.push(createNotSameControlMergerRow(mergerRows.length + 1, name))
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
  const name = await promptName('新增分步实现非同控合并的公司')
  if (!name) return
  if (stepRows.some(row => row.companyName === name) || mergerRows.some(row => row.investeeName === name)) {
    ElMessage.warning(`「${name}」已存在于一次购买或分步合并`)
    return
  }
  const companyId = `step-company-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  stepRows.push(createNotSameControlStepRow(companyId, name, 1))
  persistRows()
}
function addStepTransaction(summary: G7NotSameControlStepSummary): void {
  const rows = stepRowsFor(summary.companyId)
  const next = createNotSameControlStepRow(summary.companyId, summary.companyName, rows.length + 1)
  next.priorHoldingBookValue = summary.priorHoldingBookValue || null
  next.priorHoldingFV = summary.priorHoldingFV || null
  next.isPackageDeal = summary.isPackageDeal
  next.notPackageBasis = summary.notPackageBasis
  next.acquisitionDateEvidenceRef = summary.acquisitionDateEvidenceRef
  next.considerationEvidenceRef = summary.considerationEvidenceRef
  next.valuationReportRef = summary.valuationReportRef
  next.indexRef = summary.indexRef
  stepRows.push(next)
  persistRows()
}
function stepRowsFor(companyId: string): G7NotSameControlStepRow[] {
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
  field:
    | 'notPackageBasis'
    | 'indexRef'
    | 'isPackageDeal'
    | 'priorHoldingBookValue'
    | 'priorHoldingFV'
    | 'acquisitionDateEvidenceRef'
    | 'considerationEvidenceRef'
    | 'valuationReportRef',
  value: unknown,
): void {
  for (const row of stepRowsFor(companyId)) {
    if (
      field === 'priorHoldingBookValue'
      || field === 'priorHoldingFV'
    ) {
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
  reverseRows.push(createNotSameControlReverseRow(reverseRows.length + 1))
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

function parseRows(value: unknown): G7NotSameControlStoredRow[] {
  if (Array.isArray(value)) return normalizeNotSameControlRows(value)
  if (typeof value !== 'string' || !value.trim()) return []
  try {
    return normalizeNotSameControlRows(JSON.parse(value))
  } catch {
    return []
  }
}
function hydrate(rows: G7NotSameControlStoredRow[]): void {
  mergerRows.splice(0, mergerRows.length, ...rows.filter((row): row is G7NotSameControlMergerRow => row.section === 'merger'))
  stepRows.splice(0, stepRows.length, ...rows.filter((row): row is G7NotSameControlStepRow => row.section === 'step'))
  reverseRows.splice(0, reverseRows.length, ...rows.filter((row): row is G7NotSameControlReverseRow => row.section === 'reverse'))
}
function rowsFromHtmlData(): G7NotSameControlStoredRow[] {
  const data = props.htmlData?.notSameControl ?? props.htmlData?.not_same_control ?? props.htmlData
  return normalizeNotSameControlRows(data?.rows ?? [])
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
    validationContext.notSameControlInvestees = extractNotSameControlInvesteesFromG7Judgment(g77?.conclusion)
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
    const names = validationContext.notSameControlInvestees ?? []
    if (!names.length) {
      ElMessage.warning('G7-7 中未找到「控制+非同一控制下企业合并」单位，仅已刷新名单勾稽')
      return
    }
    const result = syncMergerRowsFromNotSameControlNames([...mergerRows], names)
    mergerRows.splice(0, mergerRows.length, ...result.rows)
    persistRows()
    ElMessage.success(`已从 G7-7 同步非同控单位：新增 ${result.added} 家`)
  } catch {
    ElMessage.error('同步 G7-7/G7-2/G7-4 失败')
  } finally {
    syncing.value = false
  }
}

function handleImportExportCommand(command: string): void {
  if (command === 'template') void exportTemplate('G7-9')
  if (command === 'export') void exportData('G7-9')
  if (command === 'import') fileInputRef.value?.click()
}
async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importData('G7-9', file)
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
          sheet: 'G7-9',
          rows: allRows.value,
          stepSummaries: stepSummaries.value,
          validationIssues: issues.value,
        },
      },
    )
    const data = response?.data?.data ?? response?.data ?? response
    const text = data?.content ?? data?.conclusion ?? data?.text ?? ''
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
    return () => h(GtAmountCell, { value: componentProps.value })
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
.g7-tab-not-same-control { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head, .card-head, .summary-bar, .step-company-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.section-head { margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 16px; }
.sheet-subtitle, .section-note { margin-left: 8px; color: #909399; font-size: 12px; }
.head-actions, .summary-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.objective-alert, .methodology-context, .summary-bar, .validation-alert { margin-bottom: 12px; }
.methodology-context { padding: 12px 16px; border-left: 4px solid #d97706; background: #fffbeb; line-height: 1.7; color: #92400e; }
.section-card { margin-bottom: 14px; }
.formula-cell { color: #1d4ed8; font-weight: 600; border-bottom: 1px dashed #94a3b8; }
.hint-text { margin-top: 2px; color: #909399; font-size: 11px; line-height: 1.3; }
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
.required-empty { outline: 1px solid var(--el-color-danger); border-radius: 4px; }
</style>
