<template>
  <div class="n2-tab-vat-calc">
    <!-- ═══ 一、审计目标（源模板 增值税测算表N2-6 R6~R8 原文） ═══ -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <ol class="ao-list">
        <li>资产负债表中记录的应交税费是存在的，且已记录于恰当的账户。</li>
        <li>所有应当记录的货币应交税费均已记录，所有应当包括在财务报表中的相关披露均已包括。</li>
        <li>应交税费以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述</li>
      </ol>
    </el-alert>

    <!-- ═══ 源模板方法论上下文（四段结构 + 两处跨段差异公式） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>源模板四段结构（增值税测算表N2-6）：</strong>
        <span class="mc-seg">（一）增值税纳税申报表核对</span>：10 个固定项目 × 账面数据 / 纳税申报表数据 / 差异 / 原因，差异 = 账面数据 − 纳税申报表数据；
        <span class="mc-seg">（二）增值税销项税金测算</span>：品种 × 销售额 / 免税扣除销售额 / 计税收入 / 税率 / 应计销项税，计税收入 = 销售额 − 免税扣除销售额，应计销项税 = 计税收入 × 税率；
        <span class="mc-seg">（三）增值税进项税测算</span>：项目 × 购进货物、固定资产及接受劳务发生额 / 税率 / 测算数，测算数 = 发生额 × 税率，另有待抵扣、待认证、留抵三个期末减期初调节项；
        <span class="mc-seg">（四）特殊情况检查</span>：4 个固定项目 × 金额。
      </div>
      <div class="methodology-text mc-formula">
        <strong>两处差异公式（源模板原文，均跨段引用（一）的账面列）：</strong>
        <span class="mc-formula-item">F30 = C17 − F28 − F29</span>
        即（二）差异 =（一）第 6 项「销项税额」账面数据 − 应计销项税合计 − 待转销项税额期末减期初；
        <span class="mc-formula-item">F39 = F35 − F36 − F37 − F38 − C18</span>
        即（三）差异 = 测算数合计 − 待抵扣进项税额 − 待认证进项税额 − 增值税留抵税额 −（一）第 7 项「进项税额」账面数据。
        故（一）（二）（三）三段须同时录入，差异结论方能成立。
      </div>
    </div>

    <!-- ═══ 二、审计过程 （一）增值税纳税申报表核对（源模板 R10 标题 / R11 表头 / R12~R21 十固定项） ═══ -->
    <div class="src-section">
      <div class="src-section-header">
        <div class="src-section-title">
          <span>（一）增值税纳税申报表核对</span>
          <el-tag size="small" type="info" effect="plain">源模板固定 10 项</el-tag>
        </div>
        <div class="src-section-status">
          <el-tag
            v-if="sourceCalc.declarationDiffCount.value > 0"
            size="small"
            type="danger"
            effect="light"
          >
            {{ sourceCalc.declarationDiffCount.value }} 项存在差异
          </el-tag>
          <el-tag v-else size="small" type="success" effect="light">账面与申报表核对一致</el-tag>
        </div>
      </div>

      <el-table
        :data="sourceCalc.declarationRows.value"
        border
        size="small"
        style="width: 100%"
        :row-class-name="declarationRowClass"
        show-summary
        :summary-method="getDeclarationSummary"
      >
        <el-table-column prop="label" label="项目" min-width="220" fixed>
          <template #default="{ row }">
            <span class="decl-item-label">{{ row.label }}</span>
          </template>
        </el-table-column>

        <el-table-column label="账面数据" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.book"
              :disabled="isReadonly"
              :aria-label="declAriaLabel(row, 'book')"
              @change="(v: number) => handleDeclarationAmount(row.key, 'book', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="纳税申报表数据" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.declared"
              :disabled="isReadonly"
              :aria-label="declAriaLabel(row, 'declared')"
              @change="(v: number) => handleDeclarationAmount(row.key, 'declared', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="差异" width="150" align="right">
          <template #header>
            <el-tooltip placement="top">
              <template #content>{{ DECLARATION_DIFF_FORMULA }}</template>
              <span class="formula-col-header">差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip placement="top">
              <template #content>{{ DECLARATION_DIFF_FORMULA }}</template>
              <span
                class="diff-cell"
                :class="{ 'diff-cell--abnormal': isDeclarationAbnormal(row) }"
              >
                {{ displayPrefs.fmtAmount(row.diff) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="原因" min-width="240">
          <template #default="{ row }">
            <el-input
              :model-value="row.reason"
              :disabled="isReadonly"
              size="small"
              :placeholder="declReasonPlaceholder(row)"
              :class="{ 'reason-input--required': isDeclarationReasonMissing(row) }"
              @input="(v: string) => handleDeclarationReason(row.key, v)"
            />
          </template>
        </el-table-column>
      </el-table>

      <div v-if="sourceCalc.declarationDiffCount.value > 0" class="src-section-hint">
        存在差异的项目须在「原因」列说明差异成因（源模板 R11 F 列要求）。
      </div>
    </div>

    <!-- ═══ （二）增值税销项税金测算（源模板 R22 标题 / R23 表头 / R24~R27 数据行 / R28 合计 / R29 待转 / R30 差异） ═══ -->
    <div class="src-section">
      <div class="src-section-header">
        <div class="src-section-title">
          <span>（二）增值税销项税金测算</span>
          <el-tag size="small" type="info" effect="plain">品种由项目实际情况决定</el-tag>
        </div>
        <div class="src-section-status">
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :icon="Plus"
            @click="handleAddOutputRow"
          >
            新增品种
          </el-button>
        </div>
      </div>

      <el-table
        :data="sourceCalc.outputRows.value"
        border
        size="small"
        style="width: 100%"
        empty-text="尚未新增品种行，点击右上角新增品种"
        show-summary
        :summary-method="getOutputSummary"
      >
        <el-table-column label="品种" min-width="200" fixed>
          <template #default="{ row }">
            <el-input
              :model-value="row.variety"
              :disabled="isReadonly"
              size="small"
              placeholder="请输入品种名称"
              @input="(v: string) => handleOutputRow(row.id, 'variety', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="销售额" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.sales"
              :disabled="isReadonly"
              :aria-label="outputAriaLabel(row, 'sales')"
              @change="(v: number) => handleOutputRow(row.id, 'sales', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="免税、扣除销售额" width="170" align="right">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.exemptSales"
              :disabled="isReadonly"
              :aria-label="outputAriaLabel(row, 'exemptSales')"
              @change="(v: number) => handleOutputRow(row.id, 'exemptSales', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="计税收入" width="150" align="right">
          <template #header>
            <el-tooltip placement="top">
              <template #content>{{ OUTPUT_TAXABLE_REVENUE_FORMULA }}</template>
              <span class="formula-col-header">计税收入</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip placement="top">
              <template #content>{{ OUTPUT_TAXABLE_REVENUE_FORMULA }}</template>
              <span class="diff-cell">{{ displayPrefs.fmtAmount(row.taxableRevenue) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="税率" width="100" align="center">
          <template #default="{ row }">
            <el-select
              :model-value="row.rate"
              :disabled="isReadonly"
              size="small"
              style="width: 84px"
              @change="(v: number) => handleOutputRow(row.id, 'rate', v)"
            >
              <el-option
                v-for="opt in N2_VAT_RATE_OPTIONS"
                :key="opt.label"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="应计销项税" width="150" align="right">
          <template #header>
            <el-tooltip placement="top">
              <template #content>{{ OUTPUT_TAX_FORMULA }}</template>
              <span class="formula-col-header">应计销项税</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip placement="top">
              <template #content>{{ OUTPUT_TAX_FORMULA }}</template>
              <span class="diff-cell">{{ displayPrefs.fmtAmount(row.outputTax) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              type="danger"
              link
              :icon="Delete"
              @click="handleRemoveOutputRow(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 源模板 R29：待转销项税额期末减期初金额 -->
      <div class="src-inline-row">
        <span class="src-inline-label">待转销项税额期末减期初金额</span>
        <el-tooltip placement="top">
          <template #content>{{ OUTPUT_PENDING_HINT }}</template>
          <span class="src-cell-ref">F29</span>
        </el-tooltip>
        <WpAmountInput
          :model-value="sourceCalc.pendingOutputTax.value"
          :disabled="isReadonly"
          aria-label="待转销项税额期末减期初金额"
          @change="handlePendingOutputTax"
        />
      </div>

      <!-- 源模板 R30：差异结论（跨段引用（一）的销项税额账面列 C17） -->
      <div
        class="variance-bar"
        :class="{ 'variance-bar--abnormal': !sourceCalc.outputVariance.value.isMatch }"
      >
        <span class="variance-label">勾稽结论</span>
        <el-tooltip placement="top">
          <template #content>{{ sourceCalc.outputVariance.value.formula }}</template>
          <span class="variance-formula">F30 = C17 − F28 − F29</span>
        </el-tooltip>
        <el-tag
          v-if="sourceCalc.outputVariance.value.isMatch"
          size="small"
          type="success"
          effect="light"
        >
          ✓ 勾稽一致
        </el-tag>
        <el-tag v-else size="small" type="danger" effect="light">
          ⚠ 存在差异 {{ displayPrefs.fmtAmount(sourceCalc.outputVariance.value.diff) }}
        </el-tag>
        <span class="variance-source-label">取数来源</span>
        <GtIndexChip value="cell:N2-6!C17" :validate="false" />
        <span class="variance-hint">{{ OUTPUT_VARIANCE_SOURCE_HINT }}</span>
      </div>
    </div>

    <!-- ═══ （三）增值税进项税测算（源模板 R31 标题 / R32 表头 / R33~R34 数据行 / R35 合计 / R36~R38 三调节项 / R39 差异） ═══ -->
    <div class="src-section">
      <div class="src-section-header">
        <div class="src-section-title">
          <span>（三）增值税进项税测算</span>
          <el-tag size="small" type="info" effect="plain">项目由项目实际情况决定</el-tag>
        </div>
        <div class="src-section-status">
          <el-button
            v-if="!isReadonly"
            size="small"
            type="primary"
            plain
            :icon="Plus"
            @click="handleAddInputRow"
          >
            新增项目
          </el-button>
        </div>
      </div>

      <el-table
        :data="sourceCalc.inputRows.value"
        border
        size="small"
        style="width: 100%"
        empty-text="尚未新增项目行，点击右上角新增项目"
        show-summary
        :summary-method="getInputSummary"
      >
        <el-table-column label="项目" min-width="200" fixed>
          <template #default="{ row }">
            <el-input
              :model-value="row.project"
              :disabled="isReadonly"
              size="small"
              placeholder="请输入项目名称"
              @input="(v: string) => handleInputRow(row.id, 'project', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="购进货物、固定资产及接受劳务发生额" min-width="230" align="right">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.amount"
              :disabled="isReadonly"
              :aria-label="inputAriaLabel(row)"
              @change="(v: number) => handleInputRow(row.id, 'amount', v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="税率" width="100" align="center">
          <template #default="{ row }">
            <el-select
              :model-value="row.rate"
              :disabled="isReadonly"
              size="small"
              style="width: 84px"
              @change="(v: number) => handleInputRow(row.id, 'rate', v)"
            >
              <el-option
                v-for="opt in N2_VAT_RATE_OPTIONS"
                :key="opt.label"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="测算数" width="150" align="right">
          <template #header>
            <el-tooltip placement="top">
              <template #content>{{ INPUT_TAX_FORMULA }}</template>
              <span class="formula-col-header">测算数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip placement="top">
              <template #content>{{ INPUT_TAX_FORMULA }}</template>
              <span class="diff-cell">{{ displayPrefs.fmtAmount(row.inputTax) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              type="danger"
              link
              :icon="Delete"
              @click="handleRemoveInputRow(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 源模板 R36~R38：三个调节项（均「期末减期初」，进入差异公式 F39） -->
      <div v-for="adj in INPUT_ADJUST_ITEMS" :key="adj.field" class="src-inline-row">
        <span class="src-inline-label">{{ adj.label }}</span>
        <el-tooltip placement="top">
          <template #content>{{ adj.hint }}</template>
          <span class="src-cell-ref">{{ adj.cell }}</span>
        </el-tooltip>
        <WpAmountInput
          :model-value="sourceCalc.inputAdjust.value[adj.field]"
          :disabled="isReadonly"
          :aria-label="adj.label"
          @change="(v: number) => handleInputAdjust(adj.field, v)"
        />
      </div>

      <!-- 源模板 R39：差异结论（跨段引用（一）的进项税额账面列 C18） -->
      <div
        class="variance-bar"
        :class="{ 'variance-bar--abnormal': !sourceCalc.inputVariance.value.isMatch }"
      >
        <span class="variance-label">勾稽结论</span>
        <el-tooltip placement="top">
          <template #content>{{ sourceCalc.inputVariance.value.formula }}</template>
          <span class="variance-formula">F39 = F35 − F36 − F37 − F38 − C18</span>
        </el-tooltip>
        <el-tag
          v-if="sourceCalc.inputVariance.value.isMatch"
          size="small"
          type="success"
          effect="light"
        >
          ✓ 勾稽一致
        </el-tag>
        <el-tag v-else size="small" type="danger" effect="light">
          ⚠ 存在差异 {{ displayPrefs.fmtAmount(sourceCalc.inputVariance.value.diff) }}
        </el-tag>
        <span class="variance-source-label">取数来源</span>
        <GtIndexChip value="cell:N2-6!C18" :validate="false" />
        <span class="variance-hint">{{ INPUT_VARIANCE_SOURCE_HINT }}</span>
      </div>
    </div>

    <!-- ═══ （四）特殊情况检查（源模板 R40 标题 / R41 表头 / R42~R45 四固定项） ═══ -->
    <div class="src-section">
      <div class="src-section-header">
        <div class="src-section-title">
          <span>（四）特殊情况检查</span>
          <el-tag size="small" type="info" effect="plain">源模板固定 4 项</el-tag>
        </div>
        <div class="src-section-status">
          <el-tag
            v-if="sourceCalc.specialFlagged.value.length > 0"
            size="small"
            type="warning"
            effect="light"
          >
            {{ sourceCalc.specialFlagged.value.length }} 项需在审计说明中说明会计处理
          </el-tag>
          <el-tag v-else size="small" type="success" effect="light">未发现特殊情况</el-tag>
        </div>
      </div>

      <el-table
        :data="sourceCalc.specialRows.value"
        border
        size="small"
        style="width: 100%"
        :row-class-name="specialRowClass"
      >
        <el-table-column prop="label" label="项目" min-width="260" fixed>
          <template #default="{ row }">
            <span class="decl-item-label">{{ row.label }}</span>
          </template>
        </el-table-column>

        <el-table-column label="金额" width="170" align="right">
          <template #default="{ row }">
            <WpAmountInput
              :model-value="row.amount"
              :disabled="isReadonly"
              :aria-label="specialAriaLabel(row)"
              @change="(v: number) => handleSpecialAmount(row.key, v)"
            />
          </template>
        </el-table-column>

        <el-table-column label="审计要求" min-width="320">
          <template #default="{ row }">
            <span v-if="isSpecialFlagged(row)" class="special-flag">
              <el-tag size="small" type="warning" effect="light">需说明</el-tag>
              <span class="special-flag-text">{{ SPECIAL_FLAG_HINT }}</span>
            </span>
            <span v-else class="special-flag-none">{{ SPECIAL_EMPTY_HINT }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="sourceCalc.specialFlagged.value.length > 0" class="src-section-hint">
        {{ specialFlaggedHint }}
      </div>
    </div>

    <!-- ═══ 三、审计说明（源模板 R46） ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="aiNoteLoading"
              :disabled="isReadonly || aiNoteLoading"
              @click="handleAiNote"
            >
              <el-icon><MagicStick /></el-icon> AI 辅助
            </el-button>
            <el-button size="small" @click="handleReviewNote">
              <el-icon><ChatDotSquare /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        :placeholder="NOTE_PLACEHOLDER"
        @input="handleNoteInput"
      />
      <div v-if="sourceCalc.specialFlagged.value.length > 0" class="card-inline-hint">
        {{ specialFlaggedHint }}
      </div>
    </el-card>

    <!-- ═══ 四、审计结论（源模板 R48） ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="aiConclusionLoading"
              :disabled="isReadonly || aiConclusionLoading"
              @click="handleAiConclusion"
            >
              <el-icon><MagicStick /></el-icon> AI 辅助
            </el-button>
            <el-button size="small" @click="handleReviewConclusion">
              <el-icon><ChatDotSquare /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        :placeholder="CONCLUSION_PLACEHOLDER"
        @input="handleConclusionInput"
      />
    </el-card>

    <!-- ═══ 审计分析（不在源模板）：按月/季 × 税率矩阵，Requirements 5.1/5.2/5.4 ═══ -->
    <div class="analysis-area">
      <div class="section-header">
        <div class="section-title">
          <span>审计分析（不在源模板）</span>
          <el-tag type="warning" size="small" effect="plain">按月/季 × 税率矩阵</el-tag>
        </div>
        <div class="section-actions">
          <el-tag size="small" type="info" effect="plain">不参与源模板勾稽</el-tag>
        </div>
      </div>

      <div class="methodology-context methodology-context--analysis">
        <div class="methodology-text">
          <strong>本区块不属于源模板四段：</strong>
          按月或按季逐期汇总销售额、销项税额、进项税额、进项转出、已交税额，并计算年度税负率，
          用于分析全年增值税走势与税负水平。
        </div>
        <div class="methodology-text mc-isolation">{{ ANALYSIS_ISOLATION_HINT }}</div>
      </div>

    <!-- ═══ 计算周期切换 + 税负率展示 ═══ -->
    <div class="calc-toolbar">
      <div class="period-switch">
        <span class="toolbar-label">计算周期：</span>
        <el-segmented
          :model-value="vatCalc.periodMode.value"
          :options="[{ label: '按月', value: 'monthly' }, { label: '按季度', value: 'quarterly' }]"
          @change="handlePeriodModeChange"
        />
      </div>
      <div class="burden-rate-display">
        <span class="toolbar-label">年度税负率：</span>
        <el-tag
          :type="burdenRateType"
          size="large"
          effect="dark"
        >
          {{ fmtPercent(vatCalc.annualSummary.value.annualBurdenRate) }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 增值税测算明细表 ═══ -->
    <el-table
      :data="vatCalc.rows.value"
      border
      size="small"
      style="width: 100%"
      show-summary
      :summary-method="getSummaryRow"
    >
      <el-table-column prop="period" label="期间" width="90" fixed />
      <el-table-column label="销售额" width="140" align="right">
        <template #default="{ row, $index }">
          <WpAmountInput
            :model-value="row.salesAmount"
            :disabled="isReadonly"
            :aria-label="analysisAriaLabel(row, '销售额')"
            @change="(val: number) => handleCellChange($index, 'salesAmount', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="税率" width="90" align="center">
        <template #default="{ row, $index }">
          <el-select
            :model-value="row.taxRate"
            size="small"
            :disabled="isReadonly"
            style="width: 72px"
            @change="(val: number) => handleCellChange($index, 'taxRate', val)"
          >
            <el-option :value="0.13" label="13%" />
            <el-option :value="0.09" label="9%" />
            <el-option :value="0.06" label="6%" />
            <el-option :value="0.05" label="5%" />
            <el-option :value="0.03" label="3%" />
            <el-option :value="0" label="免税" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="销项税额" width="130" align="right">
        <template #header>
          <el-tooltip content="公式：销售额 × 税率" placement="top">
            <span class="formula-col-header">销项税额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.outputVat) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="进项税额" width="140" align="right">
        <template #default="{ row, $index }">
          <WpAmountInput
            :model-value="row.inputVat"
            :disabled="isReadonly"
            :aria-label="analysisAriaLabel(row, '进项税额')"
            @change="(val: number) => handleCellChange($index, 'inputVat', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="进项转出" width="140" align="right">
        <template #default="{ row, $index }">
          <WpAmountInput
            :model-value="row.inputTransferOut"
            :disabled="isReadonly"
            :aria-label="analysisAriaLabel(row, '进项转出')"
            @change="(val: number) => handleCellChange($index, 'inputTransferOut', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="应交增值税" width="130" align="right">
        <template #header>
          <el-tooltip content="公式：销项税额 - (进项税额 - 进项转出)" placement="top">
            <span class="formula-col-header">应交增值税</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'formula-cell--negative': row.payableVat < 0 }">
            {{ fmtAmount(row.payableVat) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="已交税额" width="140" align="right">
        <template #default="{ row, $index }">
          <WpAmountInput
            :model-value="row.paidVat"
            :disabled="isReadonly"
            :aria-label="analysisAriaLabel(row, '已交税额')"
            @change="(val: number) => handleCellChange($index, 'paidVat', val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="未交税额" width="120" align="right">
        <template #header>
          <el-tooltip content="公式：应交 - 已交" placement="top">
            <span class="formula-col-header">未交税额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'formula-cell--negative': row.unpaidVat < 0 }">
            {{ fmtAmount(row.unpaidVat) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 附加分析：矩阵测算数与申报表应交增值税核对（不在源模板，键 N2-6-declared-payable-vat 不变） ═══ -->
    <el-card shadow="never" class="declaration-card">
      <template #header>
        <div class="card-header">
          <span>矩阵测算数与增值税纳税申报表核对（附加分析）</span>
          <el-tag
            :type="vatCalc.declarationCheck.value.isMatch ? 'success' : 'danger'"
            size="small"
          >
            {{ vatCalc.declarationCheck.value.isMatch ? '核对一致' : '存在差异' }}
          </el-tag>
        </div>
      </template>
      <div class="declaration-grid">
        <div class="decl-item">
          <span class="decl-label">测算应交增值税：</span>
          <span class="decl-value">{{ fmtAmount(vatCalc.annualSummary.value.totalPayableVat) }}</span>
        </div>
        <div class="decl-item">
          <span class="decl-label">申报表应交增值税：</span>
          <WpAmountInput
            :model-value="vatCalc.declarationCheck.value.declaredPayableVat"
            :disabled="isReadonly"
            aria-label="申报表应交增值税（附加分析区）"
            @change="handleDeclaredChange"
          />
        </div>
        <div class="decl-item">
          <span class="decl-label">差异：</span>
          <span
            class="decl-value"
            :class="{ 'decl-value--diff': !vatCalc.declarationCheck.value.isMatch }"
          >
            {{ fmtAmount(vatCalc.declarationCheck.value.diff) }}
          </span>
        </div>
      </div>
    </el-card>
    </div>
    <!-- ═══ /审计分析（不在源模板） ═══ -->

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip） ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 联动去向：</span>
      <GtIndexChip value="N2-1" />
      <span class="cross-wp-desc">审定表增值税行核对</span>
      <GtIndexChip value="N2-8" />
      <span class="cross-wp-desc">城建税计税依据（取源模板（一）口径的应交增值税）</span>
    </div>

    <!-- ═══ 编制提示（折叠置底） ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>（一）10 个固定项目取自源模板，不可增删改名；逐项录入账面数据与纳税申报表数据，差异自动派生，差异不为 0 须填写原因</li>
        <li>（二）品种由项目实际情况决定，新增行须先输入品种名称；计税收入 = 销售额 − 免税、扣除销售额，应计销项税 = 计税收入 × 税率</li>
        <li>（二）差异 = （一）第 6 项「销项税额」账面数据 − 应计销项税合计 − 待转销项税额期末减期初（源模板 F30）</li>
        <li>（三）测算数 = 购进货物、固定资产及接受劳务发生额 × 税率；差异 = 测算数合计 − 待抵扣 − 待认证 − 留抵 − （一）第 7 项「进项税额」账面数据（源模板 F39）</li>
        <li>（四）4 个固定项目金额不为 0 时，须在「三、审计说明」中说明其会计处理是否正确</li>
        <li>派生列（差异 / 计税收入 / 应计销项税 / 测算数 / 各合计）均为读时推导，不落库、不可编辑</li>
        <li>供 N2-8 城建税及附加的计税依据取（一）销项税额账面 − 进项税额账面，不取附加分析区口径</li>
        <li>「审计分析（不在源模板）」区块按月/季汇总税负率，仅供分析，不参与源模板四段勾稽</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabVatCalc — N2-6 增值税测算表
 *
 * Spec: .kiro/specs/n2-vat-calc-source-alignment/（源模板对齐，方案 B）
 * Task: 3.1（接入 useN2VatSourceCalc + 审计目标 + 源模板方法论上下文）
 *       3.2（（一）增值税纳税申报表核对区 UI）
 *       3.3（（二）增值税销项税金测算区 UI + 差异结论）
 *       3.4（（三）增值税进项税测算区 UI + 三调节项 + 差异结论）
 *       3.5（（四）特殊情况检查区 + 附加分析区降级 + 审计说明/审计结论）
 * 前身 Spec: .kiro/specs/n2-taxes-payable/ Task 4.9
 *
 * 结构（源模板 `增值税测算表N2-6` A1:H48）：
 * - 一、审计目标（R6~R8 三条原文）
 * - 二、审计过程四段：（一）申报表核对 R12~R21 /（二）销项测算 R22~R30 /
 *   （三）进项测算 R31~R39 /（四）特殊情况检查 R40~R45
 * - 三、审计说明（R46）/ 四、审计结论（R48）：各带 AI 辅助 + 复核
 * - 审计分析（不在源模板）：按月/季 × 税率矩阵 + 税负率，由既有 `useN2VatCalc` 提供，
 *   置于源模板四段之后并显式标注不参与源模板勾稽（Requirements 5.1/5.2/5.4）；
 *   其三个既有持久化键 `N2-6-vat-rows` / `N2-6-period-mode` / `N2-6-declared-payable-vat`
 *   一律不动，已录数据不丢（Requirements 5.3）。
 *
 * 两处跨段差异公式：F30 = C17 − F28 − F29；F39 = F35 − F36 − F37 − F38 − C18。
 */
import { ref, computed, inject, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus, Delete } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import WpAmountInput from '@/components/workpaper/shared/WpAmountInput.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { generateWpText } from '../../composables/shared/wpAiText'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2VatCalc, type VatCalcPeriodMode } from '../../composables/useN2VatCalc'
import {
  useN2VatSourceCalc,
  type N2VatDeclarationRow,
  type N2VatOutputRow,
  type N2VatInputRow,
  type N2VatSpecialRow,
} from '../../composables/useN2VatSourceCalc'
import {
  N2_VAT_RATE_OPTIONS,
  type N2VatInputAdjust,
} from '../../composables/useN2VatSourceEngine'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * 附加分析区（按月/季 × 税率矩阵）—— **不在源模板**，仅供审计分析。
 * 键 `N2-6-vat-rows` / `N2-6-period-mode` / `N2-6-declared-payable-vat` 保持不变（Requirements 5.3）。
 */
const vatCalc = useN2VatCalc({
  allResponses: formData.allResponses,
  // 🔴 必须传 setField —— useN2VatCalc 期望 `(sheet, field, value)`；
  //    误传 formData.saveField（真实签名 `(itemId, {conclusion})`）会把 item_id 写成 '6'、
  //    conclusion 为 undefined、真实数据被整体丢弃 → 矩阵录入静默不落库（已运行时验证）。
  saveField: formData.setField,
  getField: formData.getField,
})

/**
 * 源模板四段数据层（（一）申报表核对 /（二）销项测算 /（三）进项测算 /（四）特殊情况检查）。
 *
 * 接入范式对齐同组 N2 测算 Tab（N2-7 / N2-8 / N2-9 / N2-10）：
 * - `allResponses` 传 **`formData.allResponses`**，与写入路径同一个 Map
 * - `saveField` 传 `formData.setField`（签名 `(sheet, field, value)`，内部拼 `N2-{sheet}-{field}`）
 * - `getField` 仅用于非响应式读取
 *
 * 🔴 **不能传 `computed(() => props.allResponses)`**：宿主 `GtN2TaxesPayable` 只在 `onMounted`
 *    与 `disclosure:refresh` 时重建自己那份 Map，而本组件的写入走 `formData.setField`
 *    →`formData.saveField` → 只 `set` 进 **formData 自己的** `allResponses`。
 *    读 props 那份就会让「录入已落库、但派生列（差异/合计/差异计数）不更新」——
 *    界面看起来差异恒 0，`get_diagnostics`/vitest 均查不出（写入方与读取方不是同一真源）。
 *
 * 返回值由 Task 3.2~3.5 的四段 UI 消费；两套口径互不参与对方勾稽（Requirements 5.4）。
 */
const sourceCalc = useN2VatSourceCalc({
  allResponses: formData.allResponses,
  saveField: formData.setField,
  getField: formData.getField,
})

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)

/** 三、审计说明（源模板 R46）—— item_id `N2-6-note`，存 remark */
const auditNote = ref('')
/** 四、审计结论（源模板 R48）—— item_id `N2-6-conclusion`，存 remark */
const auditConclusion = ref('')

/** AI 生成中（按钮 loading，防重复点击） */
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

/**
 * 只读金额展示的单一真源（千分符 + 2 位小数 + 单位偏好 + localStorage 持久化）。
 * 🔴 禁自造 `toLocaleString`（组件内既有 `fmtAmount` 属附加分析区历史实现，本次不动）。
 */
const displayPrefs = useDisplayPrefsStore()

/**
 * （一）差异列公式（源模板 R11 E 列口径）。
 * 🔴 含中文标点与减号，放 JS 常量后经 `<template #content>` 渲染 ——
 *    Vue 模板**属性内**出现中文引号/特殊 Unicode 会让 Vite 编译崩溃且 Volar 查不出。
 */
const DECLARATION_DIFF_FORMULA = '差异 = 账面数据 − 纳税申报表数据（派生列，不可编辑、不持久化）'

/** 差异视为 0 的容差（与 `declarationDiffCount` 同口径，避免两处判定分叉） */
const DECLARATION_DIFF_EPS = 0.005

/**
 * （二）派生列公式文字（源模板 D24 / F24）。
 * 🔴 含全角括号与减号（U+2212），一律放 JS 常量后经 `<template #content>` 渲染 ——
 *    写进模板**属性**会让 Vite 编译崩溃且 `get_diagnostics` 查不出。
 */
const OUTPUT_TAXABLE_REVENUE_FORMULA
  = '计税收入 = 销售额 − 免税、扣除销售额（源模板 D24 = B24 − C24；派生列，不可编辑、不持久化）'

const OUTPUT_TAX_FORMULA
  = '应计销项税 = 计税收入 × 税率（源模板 F24 = D24 × E24；派生列，不可编辑、不持久化）'

/** （二）待转销项税额录入项来源说明（源模板 R29 → 差异公式的 F29） */
const OUTPUT_PENDING_HINT
  = '源模板 R29「待转销项税额期末减期初金额」，即差异公式 F30 中的 F29'

/** （二）差异结论的跨段取数来源说明（（一）未录数时差异退化为负的合计值） */
const OUTPUT_VARIANCE_SOURCE_HINT
  = '差异取（一）第 6 项「6.销项税额」的账面数据列（C17）；若（一）尚未录数，则 C17 为 0，差异等于「应计销项税合计 + 待转销项税额」的负值。'

/**
 * （三）派生列公式文字（源模板 F33）。
 * 🔴 含全角括号与乘号，同（二）范式放 JS 常量后经 `<template #content>` 渲染。
 */
const INPUT_TAX_FORMULA
  = '测算数 = 购进货物、固定资产及接受劳务发生额 × 税率（源模板 F33 = D33 × E33；派生列，不可编辑、不持久化）'

/**
 * （三）三个调节项（源模板 R36~R38），均为「期末减期初」口径，
 * 依次对应差异公式 F39 中的 F36 / F37 / F38。
 * 🔴 label / hint 含全角标点，集中放 JS 常量并以 `v-for` 渲染（禁写进模板属性）。
 */
const INPUT_ADJUST_ITEMS: Array<{
  field: keyof N2VatInputAdjust
  label: string
  cell: string
  hint: string
}> = [
  {
    field: 'deductible',
    label: '待抵扣进项税额期末减期初金额',
    cell: 'F36',
    hint: '源模板 R36「待抵扣进项税额期末减期初金额」，即差异公式 F39 中的 F36',
  },
  {
    field: 'uncertified',
    label: '待认证进项税额期末减期初金额',
    cell: 'F37',
    hint: '源模板 R37「待认证进项税额期末减期初金额」，即差异公式 F39 中的 F37',
  },
  {
    field: 'retained',
    label: '增值税留抵税额期末减期初金额',
    cell: 'F38',
    hint: '源模板 R38「增值税留抵税额期末减期初金额」，即差异公式 F39 中的 F38',
  },
]

/** （三）差异结论的跨段取数来源说明（（一）未录数时 C18 为 0） */
const INPUT_VARIANCE_SOURCE_HINT
  = '差异取（一）第 7 项「7.进项税额」的账面数据列（C18）；若（一）尚未录数，则 C18 为 0，差异等于「测算数合计 − 待抵扣 − 待认证 − 留抵」。'

/**
 * （四）特殊情况检查 —— 金额不为 0 时的审计要求（源模板红字/编制提示口径，Requirements 4.3）。
 * 🔴 含中文引号与全角标点，放 JS 常量后经插值渲染（模板属性内出现会让 Vite 编译崩溃）。
 */
const SPECIAL_FLAG_HINT = '须在「三、审计说明」中说明该事项的会计处理是否正确'

/** （四）金额为 0 时的常态文案 */
const SPECIAL_EMPTY_HINT = '金额为 0 视为本期未发生该特殊情况'

/** （四）金额视为 0 的容差（与 `specialFlagged` 同口径，避免两处判定分叉） */
const SPECIAL_AMOUNT_EPS = 0.005

/**
 * 附加分析区隔离说明（Requirements 5.2 / 5.4）。
 * 口径与源模板四段不同，故不参与（二）（三）的差异勾稽、也不写入 `N2-6-vat-payable`。
 */
const ANALYSIS_ISOLATION_HINT
  = '本区块口径与源模板四段不同（本区按期间 × 税率档汇总，源模板按品种/项目逐项测算），'
  + '故其数值不参与（一）~（四）的任何勾稽结论，也不作为 N2-8 城建税及附加计税依据的取数来源；'
  + '两区数值不一致属口径差异，不是勾稽异常。既有录入数据（按月/季矩阵、计算周期、申报表应交增值税）原样保留。'

/** 审计说明 / 审计结论 输入占位（含中文标点，放 JS 常量） */
const NOTE_PLACEHOLDER
  = '请说明增值税测算过程：申报表核对差异成因、销项/进项测算差异的处理、特殊情况（视同销售、大额进项税转出、转让金融商品、代扣代缴）的会计处理是否正确。'
const CONCLUSION_PLACEHOLDER
  = '请给出增值税审计结论：应交增值税是否真实、完整、计价准确，测算差异是否已查明并调整。'

/**
 * AI 辅助 prompt —— 🔴 必须写明源模板口径 + 「不得虚构」约束。
 * 平台既有踩坑：18~22 字的笼统 prompt 会诱导模型自造披露/说明内容。
 */
const AI_NOTE_PROMPT
  = '请基于致同源模板「增值税测算表N2-6」四段口径撰写审计说明：'
  + '（一）增值税纳税申报表核对 10 个固定项目的账面数据与申报表数据差异及成因；'
  + '（二）销项税金测算差异（源模板 F30 = C17 − F28 − F29）；'
  + '（三）进项税测算差异（源模板 F39 = F35 − F36 − F37 − F38 − C18）；'
  + '（四）特殊情况检查中金额不为 0 项目的会计处理是否正确。'
  + '只允许使用下方上下文给出的数据与项目名称，不得虚构金额、不得虚构未提供的事项或结论；'
  + '数据缺失处写「待补充」。'
const AI_CONCLUSION_PROMPT
  = '请基于致同源模板「增值税测算表N2-6」的测算结果撰写审计结论：'
  + '说明应交增值税的存在性、完整性与计价准确性，以及两处测算差异（源模板 F30 / F39）是否已查明并处理。'
  + '只允许使用下方上下文给出的数据，不得虚构金额与未执行的审计程序；数据缺失处写「待补充」。'

// ─── Computed ────────────────────────────────────────────────────────────────

/**
 * （四）金额不为 0 的项目清单提示（Requirements 4.3）。
 * 清单直接取 `sourceCalc.specialFlagged`（与表格同源派生，禁在组件内二次判定）。
 */
const specialFlaggedHint = computed(() => {
  const labels = sourceCalc.specialFlagged.value
  if (labels.length === 0) return ''
  return `以下特殊情况金额不为 0：${labels.join('、')}。${SPECIAL_FLAG_HINT}。`
})

/** 税负率颜色级别 */
const burdenRateType = computed(() => {
  const rate = vatCalc.annualSummary.value.annualBurdenRate
  if (rate <= 0) return 'info'
  if (rate < 0.02) return 'warning' // 偏低
  if (rate > 0.10) return 'danger' // 偏高
  return 'success' // 正常
})

// ─── Format ──────────────────────────────────────────────────────────────────

/**
 * 附加分析区只读金额展示。
 * 🔴 委托 `displayPrefs.fmtAmount`（平台金额格式单一真源：千分符 + 2 位小数 + 单位偏好 +
 *    `showZero` 偏好）；原自造 `toLocaleString('zh-CN')` 绕过了平台偏好，已收敛。
 */
function fmtAmount(val: number): string {
  return displayPrefs.fmtAmount(val)
}

function fmtPercent(val: number): string {
  if (!Number.isFinite(val)) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── （一）申报表核对 ────────────────────────────────────────────────────────

/** 差异 ≠ 0 → 异常（需在原因列说明） */
function isDeclarationAbnormal(row: N2VatDeclarationRow): boolean {
  return Math.abs(row.diff) > DECLARATION_DIFF_EPS
}

/** 有差异但原因未填 → 原因列高亮提示必填 */
function isDeclarationReasonMissing(row: N2VatDeclarationRow): boolean {
  return isDeclarationAbnormal(row) && !row.reason.trim()
}

function declReasonPlaceholder(row: N2VatDeclarationRow): string {
  return isDeclarationAbnormal(row) ? '存在差异，必填差异原因' : '如有差异请说明原因'
}

function declAriaLabel(row: N2VatDeclarationRow, field: 'book' | 'declared'): string {
  return `${row.label} ${field === 'book' ? '账面数据' : '纳税申报表数据'}`
}

/** 差异行整行标记（配合 `.diff-row--abnormal` 浅红底） */
function declarationRowClass({ row }: { row: N2VatDeclarationRow }): string {
  return isDeclarationAbnormal(row) ? 'diff-row--abnormal' : ''
}

/**
 * 金额列回写（账面数据 C / 纳税申报表数据 D）。
 * 🔴 保存失败必须提示，禁纯 `catch {}`（否则界面有值、库里没有，无人察觉）。
 */
async function handleDeclarationAmount(key: string, field: 'book' | 'declared', val: number) {
  try {
    await sourceCalc.updateDeclaration(key, field, val ?? 0)
  } catch {
    ElMessage.error('申报表核对数据保存失败，请重试')
  }
}

/**
 * 原因列回写。
 * 🔴 必须绑 `@input`：只绑 `@change` 时 element-plus 会在 nextTick 把 DOM 值
 *    重置回 `modelValue`，用户键入被抹掉（平台既有踩坑，与 N2 其余 Tab 范式一致）。
 */
async function handleDeclarationReason(key: string, val: string) {
  try {
    await sourceCalc.updateDeclaration(key, 'reason', val ?? '')
  } catch {
    ElMessage.error('差异原因保存失败，请重试')
  }
}

/**
 * （一）合计行 —— 账面数据 / 纳税申报表数据 / 差异 三列求和。
 * 合计取 `sourceCalc.declarationTotal`（与表格同源派生，禁在组件内二次求和）。
 * 列序：0 项目 / 1 账面数据 / 2 纳税申报表数据 / 3 差异 / 4 原因。
 */
function getDeclarationSummary({ columns }: { columns: any[] }) {
  const total = sourceCalc.declarationTotal.value
  const map: Record<number, number> = {
    1: total.book,
    2: total.declared,
    3: total.diff,
  }
  return columns.map((_col: any, index: number) => {
    if (index === 0) return '合计'
    return map[index] != null ? displayPrefs.fmtAmount(map[index]) : ''
  })
}

// ─── （二）销项税金测算 ──────────────────────────────────────────────────────

function outputAriaLabel(row: N2VatOutputRow, field: 'sales' | 'exemptSales'): string {
  const varietyName = row.variety || '未命名品种'
  return `${varietyName} ${field === 'sales' ? '销售额' : '免税扣除销售额'}`
}

/**
 * 动态行新增 —— **必须先命名再建行**（平台铁律：无名占位行会污染合计与后续勾稽）。
 * 取消 / 空名一律不创建行（`inputPattern` 已拦空白，`catch` 再兜 cancel/close）。
 */
async function handleAddOutputRow() {
  let variety = ''
  try {
    const res = await ElMessageBox.prompt('请输入品种名称（源模板（二）A 列「品种」）', '新增品种', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '品种名称不能为空',
    })
    variety = String(res?.value ?? '').trim()
  } catch {
    return // 取消 / 关闭 → 不创建行
  }
  if (!variety) return
  try {
    await sourceCalc.addOutputRow(variety)
  } catch {
    ElMessage.error('新增品种失败，请重试')
  }
}

async function handleRemoveOutputRow(row: N2VatOutputRow) {
  try {
    await ElMessageBox.confirm(
      `确认删除品种「${row.variety || '未命名品种'}」及其已录入数据？`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await sourceCalc.removeOutputRow(row.id)
  } catch {
    ElMessage.error('删除品种失败，请重试')
  }
}

/**
 * 录入列回写（品种 / 销售额 / 免税扣除销售额 / 税率）。
 * 🔴 品种列绑 `@input`：只绑 `@change` 时 element-plus 会在 nextTick 把 DOM 值重置回
 *    `modelValue`，用户键入被抹掉（与（一）原因列同一范式）。
 * 🔴 保存失败必须提示，禁纯 `catch {}`。
 */
async function handleOutputRow(
  id: string,
  field: 'variety' | 'sales' | 'exemptSales' | 'rate',
  val: any,
) {
  try {
    await sourceCalc.updateOutputRow(id, field, field === 'variety' ? (val ?? '') : (val ?? 0))
  } catch {
    ElMessage.error('销项测算数据保存失败，请重试')
  }
}

/** 待转销项税额期末减期初金额（源模板 R29 → F29） */
async function handlePendingOutputTax(val: number) {
  try {
    await sourceCalc.setPendingOutputTax(val ?? 0)
  } catch {
    ElMessage.error('待转销项税额保存失败，请重试')
  }
}

/**
 * （二）合计行 —— 源模板 R28 只对 B/C/D/F 四列求和，**税率列 E 无合计**。
 * 列序：0 品种 / 1 销售额 / 2 免税扣除销售额 / 3 计税收入 / 4 税率 / 5 应计销项税 /（6 操作，只读态无此列）。
 */
function getOutputSummary({ columns }: { columns: any[] }) {
  const total = sourceCalc.outputTotal.value
  const map: Record<number, number> = {
    1: total.sales,
    2: total.exemptSales,
    3: total.taxableRevenue,
    5: total.outputTax,
  }
  return columns.map((_col: any, index: number) => {
    if (index === 0) return '合计'
    return map[index] != null ? displayPrefs.fmtAmount(map[index]) : ''
  })
}

// ─── （三）进项税测算 ────────────────────────────────────────────────────────

function inputAriaLabel(row: N2VatInputRow): string {
  return `${row.project || '未命名项目'} 购进货物、固定资产及接受劳务发生额`
}

/**
 * 动态行新增 —— **必须先命名再建行**（与（二）同一范式，无名占位行会污染合计与差异）。
 * 取消 / 空名一律不创建行。
 */
async function handleAddInputRow() {
  let project = ''
  try {
    const res = await ElMessageBox.prompt('请输入项目名称（源模板（三）A 列「项目」）', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '项目名称不能为空',
    })
    project = String(res?.value ?? '').trim()
  } catch {
    return // 取消 / 关闭 → 不创建行
  }
  if (!project) return
  try {
    await sourceCalc.addInputRow(project)
  } catch {
    ElMessage.error('新增项目失败，请重试')
  }
}

async function handleRemoveInputRow(row: N2VatInputRow) {
  try {
    await ElMessageBox.confirm(
      `确认删除项目「${row.project || '未命名项目'}」及其已录入数据？`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await sourceCalc.removeInputRow(row.id)
  } catch {
    ElMessage.error('删除项目失败，请重试')
  }
}

/**
 * 录入列回写（项目 / 发生额 / 税率）。
 * 🔴 项目列绑 `@input`：只绑 `@change` 时 element-plus 会在 nextTick 把 DOM 值重置回
 *    `modelValue`，用户键入被抹掉（与（一）原因列、（二）品种列同一范式）。
 * 🔴 保存失败必须提示，禁纯 `catch {}`。
 */
async function handleInputRow(id: string, field: 'project' | 'amount' | 'rate', val: any) {
  try {
    await sourceCalc.updateInputRow(id, field, field === 'project' ? (val ?? '') : (val ?? 0))
  } catch {
    ElMessage.error('进项测算数据保存失败，请重试')
  }
}

/** 三调节项回写（源模板 F36 / F37 / F38，均「期末减期初」） */
async function handleInputAdjust(field: keyof N2VatInputAdjust, val: number) {
  try {
    await sourceCalc.setInputAdjust(field, val ?? 0)
  } catch {
    ElMessage.error('进项税调节项保存失败，请重试')
  }
}

/**
 * （三）合计行 —— 源模板 R35 只对 D（发生额）/ F（测算数）两列求和，**税率列 E 无合计**。
 * 列序：0 项目 / 1 发生额 / 2 税率 / 3 测算数 /（4 操作，只读态无此列）。
 */
function getInputSummary({ columns }: { columns: any[] }) {
  const total = sourceCalc.inputTotal.value
  const map: Record<number, number> = {
    1: total.amount,
    3: total.inputTax,
  }
  return columns.map((_col: any, index: number) => {
    if (index === 0) return '合计'
    return map[index] != null ? displayPrefs.fmtAmount(map[index]) : ''
  })
}

// ─── （四）特殊情况检查 ──────────────────────────────────────────────────────

/** 金额 ≠ 0 → 须在审计说明中说明会计处理（源模板红字要求，Requirements 4.3） */
function isSpecialFlagged(row: N2VatSpecialRow): boolean {
  return Math.abs(row.amount) > SPECIAL_AMOUNT_EPS
}

/** 有金额的行整行标记（配合 `.special-row--flagged` 浅黄底） */
function specialRowClass({ row }: { row: N2VatSpecialRow }): string {
  return isSpecialFlagged(row) ? 'special-row--flagged' : ''
}

function specialAriaLabel(row: N2VatSpecialRow): string {
  return `${row.label} 金额`
}

/**
 * （四）金额回写。4 个固定项来自源模板，**无增删行接口**（Requirements 4.2）。
 * 🔴 保存失败必须提示，禁纯 `catch {}`（否则界面有值、库里没有，无人察觉）。
 */
async function handleSpecialAmount(key: string, val: number) {
  try {
    await sourceCalc.updateSpecialRow(key, val ?? 0)
  } catch {
    ElMessage.error('特殊情况检查金额保存失败，请重试')
  }
}

// ─── 三、审计说明 / 四、审计结论 ─────────────────────────────────────────────

/**
 * 审计说明回写（item_id `N2-6-note`，存 remark）。
 * 🔴 绑 `@input` 而非 `@change`：只绑 `@change` 时 element-plus 会在 nextTick 把 DOM 值
 *    重置回 `modelValue`，用户键入被抹掉（与（一）原因列同一范式）。
 */
function handleNoteInput(val: string) {
  auditNote.value = val ?? ''
  formData.debouncedSave('N2-6-note', { remark: auditNote.value || null })
}

/** 审计结论回写（item_id `N2-6-conclusion`，存 remark；design 指定键） */
function handleConclusionInput(val: string) {
  auditConclusion.value = val ?? ''
  formData.debouncedSave('N2-6-conclusion', { remark: auditConclusion.value || null })
}

/**
 * AI 上下文 —— 🔴 每个值必须是**字符串**：`/ai/generate-text` 的 `context` 是
 * `dict[str, str]`，传数字会 422，且被 `catch` 吞掉后表现为「AI 无反应」。
 */
function buildAiContext(): Record<string, string> {
  const declared = sourceCalc.declarationRows.value
    .filter(r => Math.abs(r.book) > 0.005 || Math.abs(r.declared) > 0.005)
    .map(r => `${r.label}：账面 ${r.book}，申报表 ${r.declared}，差异 ${r.diff}${r.reason ? `，原因 ${r.reason}` : ''}`)
    .join('；')
  const outputVar = sourceCalc.outputVariance.value
  const inputVar = sourceCalc.inputVariance.value
  return {
    wpId: String(props.wpId),
    wpCode: 'N2-6',
    sheetName: '增值税测算表N2-6',
    declarationRows: declared || '（一）尚未录入数据',
    declarationDiffCount: String(sourceCalc.declarationDiffCount.value),
    bookOutputTax: String(sourceCalc.bookOutputTax.value),
    bookInputTax: String(sourceCalc.bookInputTax.value),
    outputTaxTotal: String(sourceCalc.outputTotal.value.outputTax),
    pendingOutputTax: String(sourceCalc.pendingOutputTax.value),
    outputVariance: `${outputVar.diff}（${outputVar.isMatch ? '勾稽一致' : '存在差异'}）`,
    inputTaxTotal: String(sourceCalc.inputTotal.value.inputTax),
    inputVariance: `${inputVar.diff}（${inputVar.isMatch ? '勾稽一致' : '存在差异'}）`,
    specialFlagged: sourceCalc.specialFlagged.value.join('、') || '无',
    vatPayable: String(sourceCalc.vatPayable.value),
  }
}

/**
 * 审计说明 AI 辅助。
 * 🔴 端点唯一正解 = `POST /api/workpapers/{wpId}/ai/generate-text`，请求体
 *    `{section, prompt, context, existingContent}`（驼峰 `existingContent`），读 `data.data.content`
 *    —— 统一走 `composables/shared/wpAiText.generateWpText`，禁各写一份 http.post。
 * 🔴 失败必须提示（`ElMessage.error`），禁纯 `catch {}`（D1 曾因此让 7 个 AI 按钮长期空转无人察觉）。
 */
async function handleAiNote() {
  aiNoteLoading.value = true
  try {
    const text = await generateWpText({
      wpId: props.wpId,
      section: 'n2-vat-calc-note',
      prompt: AI_NOTE_PROMPT,
      context: buildAiContext(),
      existingContent: auditNote.value,
    })
    if (!text) return
    auditNote.value = text
    await formData.saveField('N2-6-note', { remark: text })
    ElMessage.success('审计说明已生成，请复核后调整')
  } catch {
    ElMessage.error('审计说明 AI 生成失败，请重试')
  } finally {
    aiNoteLoading.value = false
  }
}

/** 审计结论 AI 辅助（同上范式） */
async function handleAiConclusion() {
  aiConclusionLoading.value = true
  try {
    const text = await generateWpText({
      wpId: props.wpId,
      section: 'n2-vat-calc-conclusion',
      prompt: AI_CONCLUSION_PROMPT,
      context: buildAiContext(),
      existingContent: auditConclusion.value,
    })
    if (!text) return
    auditConclusion.value = text
    await formData.saveField('N2-6-conclusion', { remark: text })
    ElMessage.success('审计结论已生成，请复核后调整')
  } catch {
    ElMessage.error('审计结论 AI 生成失败，请重试')
  } finally {
    aiConclusionLoading.value = false
  }
}

function handleReviewNote() {
  openReviewDialog?.('N2-6-审计说明')
}

function handleReviewConclusion() {
  openReviewDialog?.('N2-6-审计结论')
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handlePeriodModeChange(val: string | number) {
  vatCalc.setPeriodMode(val as VatCalcPeriodMode)
}

function handleCellChange(index: number, field: 'salesAmount' | 'taxRate' | 'inputVat' | 'inputTransferOut' | 'paidVat', val: number) {
  vatCalc.updateRow(index, field, val ?? 0)
}

function handleDeclaredChange(val: number) {
  // 🔴 三参形态必须用 setField（saveField 签名是 `(itemId, {conclusion})`）
  formData.setField('6', 'declared-payable-vat', val ?? 0)
}

/** 附加分析区金额列无障碍标签（期间 + 列名） */
function analysisAriaLabel(row: { period: string }, colLabel: string): string {
  return `${row.period} ${colLabel}`
}

/** 合计行（附加分析区） */
function getSummaryRow({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    const s = vatCalc.annualSummary.value
    const map: Record<number, number> = {
      1: s.totalSales,
      3: s.totalOutputVat,
      4: s.totalInputVat,
      5: s.totalInputTransferOut,
      6: s.totalPayableVat,
      7: s.totalPaidVat,
      8: s.totalUnpaidVat,
    }
    sums[index] = map[index] != null ? fmtAmount(map[index]) : ''
  })
  return sums
}

// ─── R6 联动：（一）账面销项/进项 → N2-6-vat-payable → N2-8 计税依据 ─────────

/**
 * 把应交增值税写入 `N2-6-vat-payable`（Requirements 6.1 / 6.2 / 6.3，Task 4.2）。
 *
 * 口径（R6.2）= （一）「6.销项税额」账面数据 C17 −「7.进项税额」账面数据 C18
 * （`useN2VatSourceEngine.calcVatPayableFromDeclaration`，由 `sourceCalc.vatPayable` 派生）。
 * 该键是 `useN2CrossSheet.vatToSurtax.base` 的唯一取数来源 → N2-8 城建税及附加计税依据。
 *
 * 🔴 口径**只取源模板（一）段，不回退附加分析区**（R6.3）：（一）无数据时为 0，
 *    不改用按月/季矩阵口径，以免 N2-8 计税依据在两套口径间静默漂移。
 *    附加分析区的「应交增值税」只写自己的独立键，不参与本联动。
 * 🔴 只读态不写库：写必被拒且会弹出无意义的失败提示。
 * 🔴 幂等去重按**值**判定（非生命周期标记）：值未变化时不重复 POST，
 *    避免重挂载 / 无关字段变化引发写风暴。
 * 🔴 保存失败必须提示，禁纯 `catch {}`（否则 N2-8 取不到值且无人察觉）。
 */
async function syncVatPayableToCrossSheet(): Promise<void> {
  if (isReadonly.value) return
  const next = parseFloat(sourceCalc.vatPayable.value.toFixed(2))
  // 键缺失（null）与「值相同」是两种情形：前者必须写一次把键建起来，供 N2-8 取数。
  const storedRaw = formData.getField('6', 'vat-payable')
  const stored = storedRaw == null || storedRaw === '' ? null : Number(storedRaw)
  if (stored != null && Number.isFinite(stored) && Math.abs(stored - next) < 0.005) return
  try {
    await sourceCalc.syncVatPayable()
  } catch {
    ElMessage.error('应交增值税联动值保存失败，N2-8 城建税及附加计税依据可能取不到值，请重试')
  }
}

/**
 * 🔴 监听的是 **`syncVatPayable` 计算真正依赖的两个字段**——（一）的账面销项税额与账面进项税额，
 *    不是任何 UI 状态（平台曾有「F2 只 watch 提示横幅可见性」= 假接入的踩坑）。
 * 🔴 **不用 `_xxxMounted` 一次性防护**（平台已清除的 bug 范式）：那种防护的消耗时机取决于
 *    「数据是否已加载」，切走再切回会吞掉回到本页后的第一次真实编辑。
 *    Vue `watch` 默认 `immediate: false`，挂载本身不触发，本就不需要防护；
 *    而 `loadData()` 填充数据引起的那一次同步是有益的（幂等 + 可补齐历史项目缺失的键）。
 */
watch(
  () => [sourceCalc.bookOutputTax.value, sourceCalc.bookInputTax.value],
  () => { void syncVatPayableToCrossSheet() },
)

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const noteResp = formData.allResponses.value.get('N2-6-note')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const conclusionResp = formData.allResponses.value.get('N2-6-conclusion')
  if (conclusionResp?.remark) auditConclusion.value = conclusionResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-vat-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 审计目标（源模板 R6~R8） ─── */
.audit-objective {
  margin-bottom: 14px;
}

.audit-objective :deep(.el-alert__content) {
  padding: 2px 0;
}

.ao-title {
  font-weight: 600;
}

.ao-list {
  margin: 4px 0 0;
  padding-left: 18px;
  line-height: 1.55;
  font-size: 12px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

.mc-seg {
  font-weight: 600;
  color: #8a6116;
}

.mc-formula {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #e6c98a;
}

.mc-formula-item {
  display: inline-block;
  padding: 0 6px;
  margin: 0 2px;
  background: #fff;
  border: 1px solid #e6c98a;
  border-radius: 3px;
  font-family: Consolas, Monaco, monospace;
  color: #b88230;
}

/* ─── 源模板小节（二、审计过程 （一）~（四）） ─── */
.src-section {
  margin-bottom: 20px;
}

.src-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.src-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.src-section-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.src-section-hint {
  margin-top: 8px;
  padding: 6px 10px;
  background: #fef0f0;
  border-left: 3px solid #f56c6c;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #a84c4c;
}

.decl-item-label {
  color: #303133;
}

/* 派生列：灰底 + 虚线下划线（不可编辑、不持久化） */
.diff-cell {
  display: inline-block;
  min-width: 72px;
  padding: 0 6px;
  background: #f5f7fa;
  border-bottom: 1px dashed #909399;
  border-radius: 3px;
  color: #606266;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  cursor: help;
}

.diff-cell--abnormal {
  background: #fef0f0;
  border-bottom-color: #f56c6c;
  color: #f56c6c;
  font-weight: 600;
}

.n2-tab-vat-calc :deep(.diff-row--abnormal) > td.el-table__cell {
  background: #fffafa;
}

.reason-input--required :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

/* ─── （四）特殊情况检查 ─── */
.n2-tab-vat-calc :deep(.special-row--flagged) > td.el-table__cell {
  background: #fdf6ec;
}

.special-flag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #b88230;
}

.special-flag-text {
  line-height: 1.5;
}

.special-flag-none {
  color: #909399;
}

/* ─── 小节内独立录入行（源模板 R29 待转销项税额 等） ─── */
.src-inline-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.src-inline-label {
  color: #606266;
  font-weight: 500;
  white-space: nowrap;
}

.src-cell-ref {
  padding: 0 6px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #909399;
  cursor: help;
}

/* ─── 差异结论 bar（紧凑单行，源模板 R30 / R39） ─── */
.variance-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-left: 3px solid #67c23a;
  border-radius: 0 6px 6px 0;
  font-size: 12px;
}

.variance-bar--abnormal {
  background: #fef0f0;
  border-left-color: #f56c6c;
}

.variance-label {
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.variance-formula {
  padding: 0 6px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  font-family: Consolas, Monaco, monospace;
  color: #606266;
  cursor: help;
}

.variance-source-label {
  color: #606266;
  white-space: nowrap;
}

.variance-hint {
  flex: 1 1 100%;
  color: #909399;
  line-height: 1.6;
}

/* ─── 审计分析区（不在源模板）：整体降级为次要视觉层级 ─── */
.analysis-area {
  margin-top: 24px;
  padding: 12px 14px 4px;
  background: #fcfcfd;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
}

.analysis-area .section-title {
  color: #606266;
}

.methodology-context--analysis {
  border-left-color: #909399;
  background: #f4f4f5;
  color: #5c6069;
}

.methodology-context--analysis .methodology-text strong {
  color: #606266;
}

.mc-isolation {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #d3d4d6;
  color: #74787f;
}

/* ─── 工具栏 ─── */
.calc-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 6px;
}

.period-switch,
.burden-rate-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: nowrap;
}

/* ─── 表格 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-cell {
  color: #409eff;
  font-weight: 500;
}

.formula-cell--negative {
  color: #f56c6c;
}

/* ─── 申报表核对 ─── */
.declaration-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-inline-hint {
  margin-top: 8px;
  padding: 6px 10px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #b88230;
  line-height: 1.6;
}

.declaration-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.decl-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.decl-label {
  color: #606266;
  white-space: nowrap;
}

.decl-value {
  font-weight: 600;
  color: #303133;
}

.decl-value--diff {
  color: #f56c6c;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
}

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}

/* ─── 跨底稿联动 cross_wp_ref ─── */
.cross-wp-links {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin-top: 12px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  font-size: 12px;
}

.cross-wp-label {
  color: #0369a1;
  font-weight: 500;
  margin-right: 4px;
}

.cross-wp-desc {
  color: #64748b;
  margin-right: 8px;
}
</style>
