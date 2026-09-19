<template>
  <div class="i1-tab-addition-check">
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      通过检查合同、凭证等相关资料，确定无形资产增加的发生、权利和义务、计价和分摊认定。
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑（按取得方式分段）：</b>
        购买核对合同/审批/入账及价税分离；股东投入核对批复（国资委或股东会）/手续/价格公允；
        融资性质核对入账金额、实际利率与融资费用；企业合并核对合并成本、确认条件与 PPA 专家索引；
        其他方式注明方法并判断合规。关注关联方及资金占用风险（审计问题解答第18号）。
        检查比例＝样本入账合计÷本期发生额（总体为 0 时显示 N/A，避免 #DIV/0!）。
        账→证抽查存在与计价；下方「证→账追查」支撑完整性。
      </p>
    </div>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:I1-5" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">样本 {{ rows.length }} 项</el-tag>
      <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">异常 {{ summary.anomalyCount }}</el-tag>
      <el-tag v-if="summary.relatedPartyCount > 0" size="small" type="warning">关联方 {{ summary.relatedPartyCount }}</el-tag>
      <el-tag v-if="summary.fundRiskCount > 0" size="small" type="danger">资金占用风险 {{ summary.fundRiskCount }}</el-tag>
      <el-tag v-if="summary.vatMismatchCount > 0" size="small" type="warning">价税差异 {{ summary.vatMismatchCount }}</el-tag>
      <el-tag v-if="summary.traceUnrecordedCount > 0" size="small" type="danger">追查异常 {{ summary.traceUnrecordedCount }}</el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ coverageLabel }}
      </el-tag>
      <GtIndexChip value="wp:I1-2" :context-project-id="projectId" />
      <GtIndexChip value="I2" @click="emit('navigate-sheet', 'I2')" />
      <el-button size="small" type="success" plain :disabled="isReadonly" @click="handleSeedI2">
        从 I2 带入资本化转入
      </el-button>
      <el-tag v-if="pendingI2Amount > 0" size="small" type="success">
        I2 待转入 {{ fmtAmt(pendingI2Amount) }}
      </el-tag>
      <span class="cross-hint">订阅 development:capitalized-to-intangible</span>
    </div>

    <!-- 二、总体与检查比例 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、本期增加总体与检查比例</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSyncPeriod">从 I1-2/审定表带入总体</el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSeedDetail">从 I1-2 带入增加明细</el-button>
            <el-button size="small" type="success" plain :disabled="isReadonly" @click="handleSeedI2">从 I2 带入</el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭引擎</el-button>
          </div>
        </div>
      </template>
      <el-descriptions :column="5" border size="small">
        <el-descriptions-item label="本期发生额（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="periodTotal"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => setPeriodTotal(v ?? 0, true)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(periodTotal) }}</span>
            <el-tag v-if="linkedPeriodTotal.source" size="small" type="info">
              源 {{ linkedPeriodTotal.source }}: {{ fmtAmt(linkedPeriodTotal.amount) }}
            </el-tag>
            <el-tag v-if="periodManual" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="检查合计（样本）">
          <span class="amount-cell">{{ fmtAmt(summary.checkedTotal) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="检查比例">
          <span :class="{ 'warn-coverage': coverageLow }">{{ coverageLabel }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="告警阈值%">
          <el-input-number
            v-if="!isReadonly"
            :model-value="coverageThreshold"
            :min="1"
            :max="100"
            :controls="false"
            size="small"
            style="width:72px"
            @change="(v: number | undefined) => setCoverageThreshold(v ?? 20)"
          />
          <span v-else>{{ coverageThreshold }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="样本量">{{ summary.checkedCount }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="populationDrift"
        type="warning"
        :closable="false"
        show-icon
        class="mt-8"
        :title="`总体与 ${linkedPeriodTotal.source}（${fmtAmt(linkedPeriodTotal.amount)}）不一致，可重新带入或保留手工数。`"
      />
    </el-card>

    <!-- 三、检查明细 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、审计过程 — 增加检查明细</span>
          <div class="title-actions">
            <el-segmented
              v-model="columnViewMode"
              :options="[
                { label: '精简视图', value: 'compact' },
                { label: '完整视图', value: 'full' },
              ]"
              size="small"
            />
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
            <el-button size="small" type="default" link @click="openReviewDialog('I1-5')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="520"
        class="check-table"
        :row-class-name="rowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="#" width="40" fixed align="center" />
        <el-table-column prop="name" label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onField(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="entryAmount" label="入账金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.entryAmount"
              :controls="false"
              size="small"
              :precision="2"
              class="cell-input"
              @change="onField(row, 'entryAmount')"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.entryAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="acquisitionMethod" label="取得方式" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.acquisitionMethod"
              size="small"
              filterable
              allow-create
              style="width:100%"
              @change="onField(row, 'acquisitionMethod')"
            >
              <el-option v-for="m in I1_ADDITION_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.acquisitionMethod || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="entryDate" label="入账日期" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.entryDate"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width:100%"
              @change="onField(row, 'entryDate')"
            />
            <span v-else>{{ row.entryDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="onField(row, 'voucherNo')" />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="counterparty" label="交易对方" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.counterparty" size="small" @change="onField(row, 'counterparty')" />
            <span v-else>{{ row.counterparty || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 购买 -->
        <el-table-column v-if="showCol('purchase')" label="购买" align="center">
          <el-table-column label="合同齐全" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.purchaseContractComplete" :disabled="isReadonly" @change="(v) => onYn(row, 'purchaseContractComplete', v)" />
            </template>
          </el-table-column>
          <el-table-column label="支付审批" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.purchasePaymentApproved" :disabled="isReadonly" @change="(v) => onYn(row, 'purchasePaymentApproved', v)" />
            </template>
          </el-table-column>
          <el-table-column label="入账正确" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.purchaseEntryCorrect" :disabled="isReadonly" @change="(v) => onYn(row, 'purchaseEntryCorrect', v)" />
            </template>
          </el-table-column>
          <el-table-column label="发票不含税" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.invoiceAmountExTax"
                :controls="false"
                size="small"
                :precision="2"
                class="cell-input"
                @change="onField(row, 'invoiceAmountExTax')"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.invoiceAmountExTax) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="进项税额" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.inputVat"
                :controls="false"
                size="small"
                :precision="2"
                class="cell-input"
                @change="onField(row, 'inputVat')"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.inputVat) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="价税分离" width="88" align="center">
            <template #header>
              <el-tooltip content="入账金额应为不含税成本，进项税不进无形资产原值" placement="top">
                <span>价税分离</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <YnSelect :model-value="row.vatSplitOk" :disabled="isReadonly" @change="(v) => onYn(row, 'vatSplitOk', v)" />
              <div v-if="isVatMismatch(row)" class="vat-warn">≠入账</div>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 股东投入 -->
        <el-table-column v-if="showCol('invest')" label="股东投入" align="center">
          <el-table-column label="批复手续" width="88" align="center">
            <template #header>
              <el-tooltip content="国资委批复或股东会/董事会决议" placement="top">
                <span>批复手续</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <YnSelect :model-value="row.investApproval" :disabled="isReadonly" @change="(v) => onYn(row, 'investApproval', v)" />
            </template>
          </el-table-column>
          <el-table-column label="手续齐全" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.investProcedureComplete" :disabled="isReadonly" @change="(v) => onYn(row, 'investProcedureComplete', v)" />
            </template>
          </el-table-column>
          <el-table-column label="价格公允" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.investPriceFair" :disabled="isReadonly" @change="(v) => onYn(row, 'investPriceFair', v)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 融资性质 -->
        <el-table-column v-if="showCol('finance')" label="具有融资性质" align="center">
          <el-table-column label="入账金额" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.financeBookAmount"
                :controls="false"
                size="small"
                :precision="2"
                class="cell-input"
                @change="onField(row, 'financeBookAmount')"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.financeBookAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="实际利率" width="80" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.financeEffectiveRate"
                :controls="false"
                size="small"
                :precision="4"
                class="cell-input"
                @change="onField(row, 'financeEffectiveRate')"
              />
              <span v-else>{{ row.financeEffectiveRate || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="融资费用" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.financeCost"
                :controls="false"
                size="small"
                :precision="2"
                class="cell-input"
                @change="onField(row, 'financeCost')"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.financeCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="入账正确" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.financeEntryCorrect" :disabled="isReadonly" @change="(v) => onYn(row, 'financeEntryCorrect', v)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 企业合并 -->
        <el-table-column v-if="showCol('combo')" label="企业合并取得" align="center">
          <el-table-column label="合并金额" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.comboAmount"
                :controls="false"
                size="small"
                :precision="2"
                class="cell-input"
                @change="onField(row, 'comboAmount')"
              />
              <span v-else class="amount-cell">{{ fmtAmt(row.comboAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="确认条件" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.comboRecognitionMet" :disabled="isReadonly" @change="(v) => onYn(row, 'comboRecognitionMet', v)" />
            </template>
          </el-table-column>
          <el-table-column label="PPA专家索引" width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.comboPpaIndex"
                size="small"
                placeholder="复核结论/索引"
                @change="onField(row, 'comboPpaIndex')"
              />
              <span v-else>{{ row.comboPpaIndex || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 其他（含自行开发 / I2 资本化转入） -->
        <el-table-column v-if="showCol('other')" label="其他取得方式" align="center">
          <el-table-column label="方式" width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.otherMethod" size="small" @change="onField(row, 'otherMethod')" />
              <span v-else>{{ row.otherMethod || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="符合规定" width="88" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.otherCompliant" :disabled="isReadonly" @change="(v) => onYn(row, 'otherCompliant', v)" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="关联方/风险" align="center">
          <el-table-column label="关联方" width="72" align="center">
            <template #default="{ row }">
              <YnSelect :model-value="row.isRelatedParty" :disabled="isReadonly" @change="(v) => onYn(row, 'isRelatedParty', v)" />
            </template>
          </el-table-column>
          <el-table-column label="关联方名称" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.relatedPartyName" size="small" @change="onField(row, 'relatedPartyName')" />
              <span v-else>{{ row.relatedPartyName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="资金占用风险" width="100" align="center">
            <template #header>
              <el-tooltip content="审计问题解答第18号：第三方合作/关联方资金占用或融资性安排风险" placement="top">
                <span>资金占用</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <YnSelect :model-value="row.fundOccupationRisk" :disabled="isReadonly" @change="(v) => onYn(row, 'fundOccupationRisk', v)" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="checkConclusion" label="审查结论" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkConclusion" size="small" style="width:80px" @change="onField(row, 'checkConclusion')">
              <el-option label="无异常" value="无异常" />
              <el-option label="有异常" value="有异常" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <el-tag v-else :type="conclusionTag(row.checkConclusion)" size="small">{{ row.checkConclusion || '—' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onField(row, 'remark')" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="附件" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link :disabled="isReadonly" title="OCR" @click="handleOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>检查合计: <b>{{ fmtAmt(summary.checkedTotal) }}</b></span>
        <span>本期发生额: <b>{{ fmtAmt(summary.periodTotal) }}</b></span>
        <span>检查比例: <b :class="{ 'warn-coverage': coverageLow }">{{ coverageLabel }}</b></span>
        <span>融资入账合计: <b>{{ fmtAmt(summary.financeBookTotal) }}</b></span>
        <span>合并金额合计: <b>{{ fmtAmt(summary.comboAmountTotal) }}</b></span>
        <span v-if="summary.relatedPartyCount">关联方: <b>{{ summary.relatedPartyCount }}</b></span>
        <span v-if="summary.vatMismatchCount">价税差异: <b class="warn-coverage">{{ summary.vatMismatchCount }}</b></span>
      </div>
      <el-alert
        v-if="summary.vatMismatchCount > 0"
        type="warning"
        :closable="false"
        show-icon
        class="mt-8"
        :title="`有 ${summary.vatMismatchCount} 笔外购入账金额与发票不含税差 >1，请核对价税分离。`"
      />
    </el-card>

    <!-- 三-B、证→账追查（完整性） -->
    <el-card id="i1-5-trace-section" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三-B、证→账追查明细（完整性 · {{ traceRows.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSeedTrace">从账→证样本生成</el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addTraceRow()">+ 追查行</el-button>
          </div>
        </div>
      </template>
      <p class="trace-hint">
        从合同/发票/权属证明等源文件追查至无形资产账面：是否入账、金额是否一致。未入账或差额须跟进完整性认定。
      </p>
      <el-table
        :data="traceRows"
        border
        stripe
        size="small"
        max-height="360"
        class="check-table"
        :row-class-name="traceRowClassName"
      >
        <el-table-column type="index" label="#" width="40" align="center" />
        <el-table-column prop="sourceType" label="源文件类型" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.sourceType"
              size="small"
              style="width:98px"
              @change="updateTraceCell(row.rowId, 'sourceType', row.sourceType)"
            >
              <el-option v-for="t in I1_TRACE_SOURCE_OPTS" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.sourceType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceRef" label="源文件编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.sourceRef" size="small" @change="updateTraceCell(row.rowId, 'sourceRef', row.sourceRef)" />
            <span v-else>{{ row.sourceRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceDate" label="源文件日期" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.sourceDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:108px"
              @change="updateTraceCell(row.rowId, 'sourceDate', row.sourceDate)"
            />
            <span v-else>{{ row.sourceDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceParty" label="对方名称" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.sourceParty" size="small" @change="updateTraceCell(row.rowId, 'sourceParty', row.sourceParty)" />
            <span v-else>{{ row.sourceParty || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceAmount" label="源文件金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.sourceAmount"
              :controls="false"
              size="small"
              class="cell-input"
              @change="updateTraceCell(row.rowId, 'sourceAmount', row.sourceAmount)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.sourceAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recordedInBooks" label="已入账" width="80" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.recordedInBooks"
              size="small"
              style="width:64px"
              @change="updateTraceCell(row.rowId, 'recordedInBooks', row.recordedInBooks)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else :type="row.recordedInBooks === 'N' ? 'danger' : 'success'" size="small">
              {{ row.recordedInBooks === 'Y' ? '是' : row.recordedInBooks === 'N' ? '否' : '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="bookVoucherNo" label="账面凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.bookVoucherNo" size="small" @change="updateTraceCell(row.rowId, 'bookVoucherNo', row.bookVoucherNo)" />
            <span v-else>{{ row.bookVoucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAssetName" label="账面资产" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.bookAssetName" size="small" @change="updateTraceCell(row.rowId, 'bookAssetName', row.bookAssetName)" />
            <span v-else>{{ row.bookAssetName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAmount" label="账面金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.bookAmount"
              :controls="false"
              size="small"
              class="cell-input"
              @change="updateTraceCell(row.rowId, 'bookAmount', row.bookAmount)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差额" width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'warn-coverage': Math.abs(row.amountDiff) > 1 }" title="差额=源文件金额−账面金额">
              {{ fmtAmt(row.amountDiff) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="checkResult" label="结果" width="72" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.checkResult"
              size="small"
              style="width:60px"
              @change="updateTraceCell(row.rowId, 'checkResult', row.checkResult)"
            >
              <el-option label="OK" value="OK" />
              <el-option label="异常" value="ERR" />
            </el-select>
            <el-tag v-else :type="row.checkResult === 'OK' ? 'success' : row.checkResult === 'ERR' ? 'danger' : 'info'" size="small">
              {{ row.checkResult || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="indexRef" label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="updateTraceCell(row.rowId, 'indexRef', row.indexRef)" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeTraceRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="summary.traceUnrecordedCount > 0"
        type="error"
        :closable="false"
        show-icon
        class="mt-8"
        :title="`有 ${summary.traceUnrecordedCount} 笔证→账追查未入账或结果异常，请跟进完整性认定。`"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明抽样方法、各类取得方式检查要点、异常项及与 I1-2/I2 勾稽情况。"
        @blur="saveNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>五、审计结论</span></template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="经检查，本期无形资产增加的发生、权利与义务、计价和分摊在重大方面…（A 无异常 / B 除下列外 / C 重大未调整）"
        @blur="saveConclusion"
      />
    </el-card>

    <details class="compile-hint" open>
      <summary>编制提示（对齐源表）</summary>
      <ol>
        <li>检查增加的发票、原始凭证、购置合同、会议决议、交接单等是否齐全。</li>
        <li>检查入账价值是否正确（土地使用权、专有技术等权属证明与账面一致）。</li>
        <li>外购须价税分离：入账金额≈发票不含税，进项税不进无形资产成本。</li>
        <li>第三方合作形成的资产，关注是否符合确认条件及关联方资金占用/融资风险（审计问题解答第18号）。</li>
        <li>「批复手续」含国资委批复或股东会/董事会决议，适配国企与非国企。</li>
        <li>检查比例分母为 0 时显示 N/A，不再出现 #DIV/0!。</li>
        <li>完整性：除账→证抽查外，须做证→账追查（源文件→账面）。</li>
      </ol>
    </details>

    <el-dialog v-model="showSamplingDialog" title="抽凭引擎（科目 1701 增加）" width="720px" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && wpId && projectId"
        :project-id="projectId"
        :workpaper-id="wpId"
        account-code="1701"
        phase="final"
        :year="year ?? new Date().getFullYear()"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabAdditionCheck.vue — I1-5 无形资产增加检查表
 * 对齐源表：取得方式分段列 + 检查比例防 DIV/0 + I1-2 联动
 */
import { ref, computed, toRef, inject, watch, defineComponent, h } from 'vue'
import { ElMessage, ElMessageBox, ElSelect, ElOption } from 'element-plus'
import {
  useI1AdditionCheck,
  I1_ADDITION_METHODS,
  I1_TRACE_SOURCE_OPTS,
  shouldShowColGroup,
  type I1AdditionCheckRow,
  type I1MethodColGroup,
  type I1TraceRow,
  type YnNa,
} from '../../composables/useI1AdditionCheck'
import { isI1VatMismatch } from '../../composables/i1AdditionCheckModel'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import http from '@/utils/http'

/** 是/否/不适用 下拉（内联小组件） */
const YnSelect = defineComponent({
  name: 'YnSelect',
  props: {
    modelValue: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
  },
  emits: ['change'],
  setup(props, { emit }) {
    return () => h(ElSelect, {
      modelValue: props.modelValue || '',
      size: 'small',
      disabled: props.disabled,
      style: 'width:72px',
      placeholder: '—',
      clearable: true,
      'onUpdate:modelValue': (v: string) => emit('change', (v || '') as YnNa),
    }, () => [
      h(ElOption, { label: '是', value: 'Y' }),
      h(ElOption, { label: '否', value: 'N' }),
      h(ElOption, { label: 'N/A', value: 'NA' }),
    ])
  },
})

const props = defineProps<{
  wpId: string
  projectId: string
  year?: number
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId?: string, value?: any]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  traceRows,
  periodTotal,
  periodManual,
  linkedPeriodTotal,
  summary,
  coverageThreshold,
  coverageLow,
  pendingI2Amount,
  setPeriodTotal,
  setCoverageThreshold,
  syncPeriodFromLinked,
  seedFromDetail,
  seedFromI2Transfer,
  addRow,
  removeRow,
  updateCell,
  addTraceRow,
  removeTraceRow,
  updateTraceCell,
  seedTraceFromCheck,
  flushPersist,
  exportXlsx,
  importXlsx,
} = useI1AdditionCheck(toRef(props, 'wpId'), allResponsesRef as any, {
  onSave: (itemId, value) => emit('save', itemId, value),
})

const auditNote = ref('')
const conclusion = ref('')
const showSamplingDialog = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const columnViewMode = ref<'compact' | 'full'>('compact')

watch(() => props.allResponses, (m) => {
  const n = m.get('I1-5-audit-note')
  if (n) auditNote.value = (n as any).remark ?? (n as any).conclusion ?? ''
  const c = m.get('I1-5-conclusion')
  if (c) conclusion.value = (c as any).remark ?? (c as any).conclusion ?? ''
}, { immediate: true })

const coverageLabel = computed(() =>
  summary.value.coverageRate == null ? 'N/A' : `${summary.value.coverageRate.toFixed(2)}%`,
)
const coverageTagType = computed(() => {
  if (summary.value.coverageRate == null) return 'info'
  if (coverageLow.value) return 'warning'
  return 'success'
})
const populationDrift = computed(() =>
  linkedPeriodTotal.value.amount > 0
    && Math.abs(periodTotal.value - linkedPeriodTotal.value.amount) > 0.01,
)

function showCol(group: I1MethodColGroup) {
  return shouldShowColGroup(group, columnViewMode.value, rows.value)
}

function onField(row: I1AdditionCheckRow, field: keyof I1AdditionCheckRow) {
  updateCell(row.rowId, field, (row as any)[field])
}

function onYn(row: I1AdditionCheckRow, field: keyof I1AdditionCheckRow, v: YnNa) {
  updateCell(row.rowId, field, v)
}

function handleSyncPeriod() {
  const r = syncPeriodFromLinked()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handleSeedDetail() {
  const r = seedFromDetail()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handleSeedI2() {
  const r = seedFromI2Transfer()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handleSeedTrace() {
  const r = seedTraceFromCheck()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function isVatMismatch(row: I1AdditionCheckRow) {
  return isI1VatMismatch(row)
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入无形资产名称', '新增检查项', {
      inputPlaceholder: '如：XX软件著作权',
    })
    if (!name?.trim()) return
    addRow({ name: name.trim() })
  } catch { /* cancel */ }
}

function onSampleFilled(samples: any[]) {
  showSamplingDialog.value = false
  if (!samples?.length) return
  for (const s of samples) {
    addRow({
      name: s.summary || s.description || s.accountName || '抽样项',
      entryDate: s.date ?? s.entryDate ?? '',
      entryAmount: Number(s.amount) || 0,
      voucherNo: s.voucherNo ?? '',
      voucherSampleId: s.sampleId ?? '',
      acquisitionMethod: '购买',
    })
  }
  ElMessage.success(`已添加 ${samples.length} 个抽样项`)
}

async function handleOcr(row: I1AdditionCheckRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
      if (!Object.keys(fields).length) {
        ElMessageBox.alert('OCR完成，未识别到可填充字段', '提示')
        return
      }
      const preview = Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(`识别结果：\n${preview}\n\n确认填入？`, 'OCR识别结果')
      if (fields.amount || fields.entryAmount) row.entryAmount = Number(fields.amount || fields.entryAmount) || row.entryAmount
      if (fields.date || fields.entryDate) row.entryDate = String(fields.date || fields.entryDate)
      if (fields.contractNo || fields.invoiceNo || fields.voucherNo) {
        row.voucherNo = String(fields.contractNo || fields.invoiceNo || fields.voucherNo)
      }
      if (fields.name || fields.assetName) row.name = row.name || String(fields.name || fields.assetName)
      row.attachmentUrl = file.name
      row.ocrResult = JSON.stringify(fields)
      flushPersist()
      ElMessage.success('OCR结果已填入')
    } catch { /* cancel */ }
  }
  input.click()
}

async function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') await exportXlsx('template')
  else if (cmd === 'export-data') await exportXlsx('data')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const r = await importXlsx(file, true)
    ElMessage.success(`已导入 ${r.imported} 行`)
  } catch (e: any) {
    ElMessage.error(e?.message || '导入失败')
  }
}

function saveNote() { emit('save', 'I1-5-audit-note', auditNote.value) }
function saveConclusion() { emit('save', 'I1-5-conclusion', conclusion.value) }

function rowClassName({ row }: { row: I1AdditionCheckRow }) {
  if (row.checkConclusion === '有异常' || row.fundOccupationRisk === 'Y') return 'anomaly-row'
  if (row.isRelatedParty === 'Y' || isI1VatMismatch(row)) return 'risk-row'
  return ''
}

function traceRowClassName({ row }: { row: I1TraceRow }) {
  if (row.recordedInBooks === 'N' || row.checkResult === 'ERR' || Math.abs(row.amountDiff) > 1) {
    return 'anomaly-row'
  }
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'entryAmount' || col.label === '入账金额') return fmtAmt(summary.value.checkedTotal)
    if (col.label === '融资费用') return fmtAmt(summary.value.financeCostTotal)
    if (col.label === '合并金额') return fmtAmt(summary.value.comboAmountTotal)
    if (col.label === '入账金额' && col.parent?.label?.includes?.('融资')) return fmtAmt(summary.value.financeBookTotal)
    return ''
  })
}

function conclusionTag(v: string): '' | 'success' | 'danger' | 'warning' {
  if (v === '无异常') return 'success'
  if (v === '有异常') return 'danger'
  if (v === '待核实') return 'warning'
  return ''
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-addition-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
}
.tab-toolbar {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px;
}
.chip-wrap { display: inline-flex; }
.cross-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.block-card { margin-bottom: 12px; }
.section-title {
  display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
}
.title-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pop-cell { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.check-table { font-size: 12px; }
.check-table :deep(.anomaly-row) { background: var(--el-color-danger-light-9); }
.check-table :deep(.risk-row) { background: var(--el-color-warning-light-9); }
.vat-warn { color: var(--el-color-warning-dark-2); font-size: 10px; line-height: 1.2; }
.trace-hint { font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 8px; }
.cell-input { width: 100%; }
.cell-input :deep(.el-input__inner) { text-align: right; font-size: 12px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.warn-coverage { color: var(--el-color-warning-dark-2); font-weight: 600; }
.summary-bar {
  display: flex; gap: 18px; padding: 10px 12px; margin-top: 12px;
  background: var(--el-fill-color-light); border-radius: 4px; flex-wrap: wrap; font-size: 12px;
}
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
.mt-8 { margin-top: 8px; }
</style>
