<template>
<div class="f1-comprehensive-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

  <details class="guidance-details">
    <summary>📋 编制思路与检查逻辑</summary>
    <div class="guidance-content">
      <p>1. <b>目标</b>：对预付账款（1123）本期增减与期后结转抽样，验证真实性、审批合规与截止恰当。</p>
      <p>2. <b>样本</b>：大额 / 关联方 / 超1年账龄作特定样本必选（可一键从 F1-2 带入）；其余用抽凭引擎按借贷分配。</p>
      <p>3. <b>借方证据链</b>：记账凭证 ↔ 付款审批单 ↔ 银行回单 ↔ 合同/订单；点击「单据核对」分单据 OCR 回填，右侧实时勾稽。</p>
      <p>4. <b>贷方/期后证据链</b>：记账凭证 ↔ 入库/验收 ↔ 发票；期后可按资产负债表日一键标注跨期疑点，核实合计应与 F1-2 期后结转（Z列）勾稽。</p>
      <p>5. <b>检查比例</b>：账面基准 = F1-2 借方 / 贷方 / 期后结转合计；核实 = 本表样本金额；比例 &lt;30% 须扩大样本或在说明中解释。</p>
    </div>
  </details>

  <!-- 一、审计目标 -->
  <el-alert id="f1-7-objective" type="info" :closable="false" class="objective-alert" show-icon>
    <template #title>
      <div class="objective-title">一、审计目标</div>
      <ul class="objective-list">
        <li>验证预付账款本期增减变动的真实性与准确性</li>
        <li>检查期后结转情况，确认截止恰当</li>
        <li>评估长期挂账款项的可收回性及披露是否充分</li>
      </ul>
    </template>
  </el-alert>

  <!-- 二、样本选取 -->
  <el-card id="f1-7-sample" class="sampling-card" shadow="never">
    <template #header>
      <div class="card-header">
        <span>二、样本选取标准与规模</span>
        <GtIndexChip value="wp:F1-2" :context-project-id="projectId" />
      </div>
    </template>
    <div class="params-grid">
      <div class="param-item span-2">
        <span class="param-label">测试总体</span>
        <el-input
          :model-value="samplingParams.testName"
          size="small"
          :disabled="isReadonly"
          placeholder="如：预付账款本期借方/贷方发生额"
          @change="(v: string) => updateSamplingParams('testName', v)"
        />
      </div>
      <div class="param-item span-2">
        <span class="param-label">特定样本</span>
        <el-input
          :model-value="samplingParams.specificSamples"
          size="small"
          :disabled="isReadonly"
          placeholder="大额、关联方、长账龄等必选样本说明"
          @change="(v: string) => updateSamplingParams('specificSamples', v)"
        />
      </div>
      <div class="param-item">
        <span class="param-label">抽样总体笔数</span>
        <el-input
          :model-value="samplingParams.samplingPopulationCount"
          size="small"
          :disabled="isReadonly"
          @change="(v: any) => updateSamplingParams('samplingPopulationCount', Number(v) || 0)"
        />
      </div>
      <div class="param-item">
        <span class="param-label">抽样总体金额</span>
        <el-input
          :model-value="samplingParams.samplingPopulationAmount"
          size="small"
          :disabled="isReadonly"
          @change="(v: any) => updateSamplingParams('samplingPopulationAmount', Number(v) || 0)"
        />
      </div>
      <div class="param-item">
        <span class="param-label">目标样本量</span>
        <el-input
          :model-value="samplingParams.targetSampleSize"
          size="small"
          :disabled="isReadonly"
          @change="(v: any) => updateSamplingParams('targetSampleSize', Number(v) || 0)"
        />
      </div>
      <div class="param-item">
        <span class="param-label">抽样方法</span>
        <el-select
          :model-value="samplingParams.samplingMethod"
          size="small"
          :disabled="isReadonly"
          style="width: 100%"
          @change="(v: string) => updateSamplingParams('samplingMethod', v)"
        >
          <el-option v-for="opt in F1_SAMPLING_METHOD_OPTIONS" :key="opt" :label="opt" :value="opt" />
        </el-select>
      </div>
      <div class="param-item span-2">
        <span class="param-label">抽样过程</span>
        <el-input
          :model-value="samplingParams.samplingProcess"
          size="small"
          :disabled="isReadonly"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          placeholder="描述抽样工具、随机起点、间隔或货币单元过程索引…"
          @change="(v: string) => updateSamplingParams('samplingProcess', v)"
        />
      </div>
    </div>
  </el-card>

  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-tag type="info" size="small">已检查 {{ totalChecked }}</el-tag>
      <el-tag :type="anomalyCount > 0 ? 'danger' : 'success'" size="small">异常 {{ anomalyCount }}</el-tag>
      <el-tag :type="anomalyRate > 10 ? 'danger' : 'info'" size="small">异常率 {{ anomalyRate.toFixed(1) }}%</el-tag>
      <el-button size="small" :disabled="isReadonly" @click="doFillBookFromDetail">从 F1-2 回填账面</el-button>
      <el-button size="small" type="warning" plain :disabled="isReadonly" @click="doImportPrioritySamples">
        从 F1-2 带入重点样本
      </el-button>
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:F1-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:F1-2" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:F1-5" :context-project-id="projectId" /></span>
    </div>
  </div>

  <nav class="st-sec-nav" aria-label="F1-7 分区导航">
    <button
      v-for="item in f1VoucherNav"
      :key="item.id"
      type="button"
      class="st-sec-btn"
      :class="{ active: activeId === item.id }"
      @click="scrollTo(item.id)"
    >{{ item.label }}</button>
  </nav>

  <el-collapse id="f1-7-sampling" class="sampling-engine-collapse" style="margin-bottom: 12px">
    <el-collapse-item title="自动抽凭（科目 1123 预付账款 · 样本按借贷方向自动分配）" name="auto-sampling">
      <GtVoucherSamplingEngine
        account-code="1123"
        :phase="currentPhase"
        default-method="mus"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="auditYear"
        @filled="handleSamplingFilled"
      />
    </el-collapse-item>
  </el-collapse>

  <F1SheetAttachments
    :project-id="projectId"
    :wp-id="wpId"
    sheet-code="F1-7"
    label="综合检查附件"
  />

  <!-- (1) 本期借方 -->
  <div id="f1-7-debit" class="vc-section">
    <div class="section-header">
      <h4>(1) 本期借方发生额核查</h4>
      <div class="section-header-actions">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('F1-7')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('F1-7')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx"
                  :disabled="isReadonly || importing"
                  :before-upload="(file: any) => handleImport(file, 'F1-7')"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample('debit')">+ 添加样本</el-button>
      </div>
    </div>
    <el-table
      :data="debitTableData"
      size="small"
      border
      stripe
      :height="debitRows.length > 12 ? '400px' : undefined"
      :row-class-name="rowClassName"
    >
      <el-table-column label="供应商名称" width="120" fixed>
        <template #default="{ row }">
          <span v-if="row.rowId === '__subtotal__'" class="subtotal-label">合计</span>
          <el-input
            v-else
            :model-value="row.supplierName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateCell('debit', row.rowId, 'supplierName', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.date"
            size="small"
            :disabled="isReadonly"
            placeholder="YYYY-MM-DD"
            @change="(v: string) => updateCell('debit', row.rowId, 'date', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="凭证编号" width="90">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.voucherNo"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateCell('debit', row.rowId, 'voucherNo', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="记账凭证" align="center">
        <el-table-column label="业务内容" width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.businessContent"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'businessContent', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="90">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.counterAccount"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'counterAccount', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="对方明细" width="100">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.counterDetailAccount"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'counterDetailAccount', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="借方金额" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.rowId === '__subtotal__'" class="amt subtotal-val">{{ fmtAmount(debitChecked) }}</span>
            <el-input
              v-else
              :model-value="row.debitAmount"
              size="small"
              :disabled="isReadonly"
              @change="(v: any) => updateCell('debit', row.rowId, 'debitAmount', v)"
            />
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="付款审批单" align="center">
        <el-table-column label="日期/编号" width="100">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.approvalDateNo"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'approvalDateNo', v)"
            />
          </template>
        </el-table-column>
      <el-table-column label="是否审批" width="90">
        <template #default="{ row }">
          <el-select
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.approvalOk"
            size="small"
            :disabled="isReadonly"
            clearable
            placeholder="—"
            @change="(v: string) => updateCell('debit', row.rowId, 'approvalOk', v || '')"
          >
            <el-option v-for="opt in F1_YES_NO_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
      </el-table-column>
      </el-table-column>
      <el-table-column label="银行回单" align="center">
        <el-table-column label="付款方" width="90">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.bankPayment"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'bankPayment', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="收款方" width="90">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.bankPayee"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'bankPayee', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="90" align="right">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.bankAmount"
              size="small"
              :disabled="isReadonly"
              @change="(v: any) => updateCell('debit', row.rowId, 'bankAmount', v)"
            />
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="合同/订单" align="center">
        <el-table-column label="名称" width="100">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.contractName"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'contractName', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="合同金额" width="90" align="right">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.contractAmount"
              size="small"
              :disabled="isReadonly"
              @change="(v: any) => updateCell('debit', row.rowId, 'contractAmount', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="签收单据" width="90">
          <template #default="{ row }">
            <el-input
              v-if="row.rowId !== '__subtotal__'"
              :model-value="row.receiptDoc"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell('debit', row.rowId, 'receiptDoc', v)"
            />
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="索引号" width="70">
        <template #default="{ row }">
          <el-input
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateCell('debit', row.rowId, 'indexRef', v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="是否异常" width="110">
        <template #default="{ row }">
          <el-select
            v-if="row.rowId !== '__subtotal__'"
            :model-value="row.isAbnormal"
            size="small"
            :disabled="isReadonly"
            clearable
            placeholder="—"
            :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }"
            @change="(v: string) => updateCell('debit', row.rowId, 'isAbnormal', v || '')"
          >
            <el-option v-for="opt in F1_ABNORMAL_OPTIONS" :key="opt.value || '_empty'" :label="opt.label" :value="opt.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="勾稽" width="88" align="center" fixed="right">
        <template #default="{ row }">
          <el-tag
            v-if="row.rowId !== '__subtotal__'"
            size="small"
            :type="debitEvidenceStatus(row).type"
          >{{ debitEvidenceStatus(row).label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="OCR" width="56" align="center" fixed="right">
        <template #default="{ row }">
          <el-upload
            v-if="row.rowId !== '__subtotal__'"
            :show-file-list="false"
            accept="image/*,.pdf"
            :disabled="ocrLoadingRowId === row.rowId"
            :before-upload="(file: File) => handleRowOcr(file, 'debit', row.rowId)"
          >
            <el-button link size="small" :loading="ocrLoadingRowId === row.rowId" title="上传凭证 OCR">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="操作" :width="isReadonly ? 80 : 130" fixed="right">
        <template #default="{ row }">
          <template v-if="row.rowId !== '__subtotal__'">
            <el-button link type="primary" size="small" @click="openCheckDialog('debit', row.rowId)">单据核对</el-button>
            <el-popconfirm v-if="!isReadonly" title="删除？" @confirm="removeSample('debit', row.rowId)">
              <template #reference><el-button size="small" type="danger" link>删</el-button></template>
            </el-popconfirm>
          </template>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- (2) 本期贷方 -->
  <div id="f1-7-credit" class="vc-section">
    <div class="section-header">
      <h4>(2) 本期贷方发生额核查</h4>
      <div class="section-header-actions">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('F1-7-credit')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('F1-7-credit')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx"
                  :disabled="isReadonly || importing"
                  :before-upload="(file: any) => handleImport(file, 'F1-7-credit')"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample('credit')">+ 添加样本</el-button>
      </div>
    </div>
    <F1CreditCheckTable
      :rows="creditRows"
      :checked-total="creditChecked"
      :is-readonly="isReadonly"
      :ocr-loading-row-id="ocrLoadingRowId"
      @update="(rowId, field, value) => updateCell('credit', rowId, field, value)"
      @remove="(rowId) => removeSample('credit', rowId)"
      @ocr="(file, rowId) => handleRowOcr(file, 'credit', rowId)"
      @open-check="(rowId) => openCheckDialog('credit', rowId)"
    />
  </div>

  <!-- (3) 期后贷方 -->
  <div id="f1-7-post" class="vc-section">
    <div class="section-header">
      <h4>(3) 期后贷方发生额核查</h4>
      <div class="section-header-actions">
        <el-date-picker
          v-model="crossPeriodCutoff"
          type="date"
          value-format="YYYY-MM-DD"
          size="small"
          placeholder="资产负债表日"
          style="width: 150px"
          :disabled="isReadonly"
        />
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || !crossPeriodCutoff"
          @click="doAutoMarkCrossPeriod"
        >标注跨期疑点</el-button>
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('F1-7-post')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('F1-7-post')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx"
                  :disabled="isReadonly || importing"
                  :before-upload="(file: any) => handleImport(file, 'F1-7-post')"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSample('postPeriod')">+ 添加样本</el-button>
      </div>
    </div>
    <F1CreditCheckTable
      :rows="postPeriodRows"
      :checked-total="postChecked"
      :is-readonly="isReadonly"
      :ocr-loading-row-id="ocrLoadingRowId"
      @update="(rowId, field, value) => updateCell('postPeriod', rowId, field, value)"
      @remove="(rowId) => removeSample('postPeriod', rowId)"
      @ocr="(file, rowId) => handleRowOcr(file, 'postPeriod', rowId)"
      @open-check="(rowId) => openCheckDialog('postPeriod', rowId)"
    />
  </div>

  <F1VoucherCheckDialog
    v-model="checkDialogVisible"
    :row="activeCheckRow"
    :section="activeCheckSection"
    :wp-id="wpId"
    :project-id="projectId"
    :readonly="isReadonly"
    @save="onDialogSave"
  />

  <el-alert
    v-if="postPeriodCrossValidation"
    :title="postPeriodCrossValidation"
    type="warning"
    :closable="false"
    show-icon
    class="cross-alert"
  />

  <!-- 四、检查比例 -->
  <el-card id="f1-7-coverage" class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">四、检查比例</span>
        <span class="ratio-hint">账面 = F1-2 借方/贷方/期后结转；核实自动汇总；比例 &lt;30% 提示扩大样本</span>
      </div>
    </template>

    <el-table :data="coverageRows" border size="small" class="coverage-table">
      <el-table-column prop="direction" label="方向" width="120" />
      <el-table-column label="账面金额" align="right" min-width="140">
        <template #default="{ row, $index }">
          <el-input
            :model-value="row.bookAmount"
            size="small"
            :disabled="isReadonly"
            @change="(v: any) => onBookAmountChange($index, v)"
          />
        </template>
      </el-table-column>
      <el-table-column label="核实金额" align="right" min-width="120">
        <template #default="{ row }">
          <span class="amt auto">{{ fmtAmount(row.checkedAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="检查比例" align="right" width="120">
        <template #default="{ row }">
          <span :class="ratioClass(row.ratio)">{{ formatRatio(row.ratio) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <el-alert
      v-if="lowCoverageWarning"
      :title="lowCoverageWarning"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
    />

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">审计说明</span>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || !aiAvailable || aiLoading"
          :loading="aiLoading"
          @click="generateNote"
        >🤖AI</el-button>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明样本选取、借/贷/期后勾稽结果、检查比例偏低原因及扩大测试情况…"
      />
    </div>
  </el-card>

  <!-- 五、审计结论 -->
  <el-card id="f1-7-conclusion" class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">五、审计结论</span>
        <div class="opinion-actions">
          <el-button
            size="small"
            :disabled="isReadonly || !aiAvailable || aiLoading"
            :loading="aiLoading"
            @click="generateConclusion"
          >🤖AI</el-button>
          <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
        </div>
      </div>
    </template>
    <el-input
      v-model="conclusion"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 6 }"
      :disabled="isReadonly"
      placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
    />
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * F1TabComprehensiveCheck.vue — F1-7 预付账款检查表（对齐 Excel）
 * 一目标 / 二抽样 / 三(1)借方(2)贷方(3)期后 / 四检查比例 / 五结论
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useF1VoucherCheck,
  F1_SAMPLING_METHOD_OPTIONS,
  F1_YES_NO_OPTIONS,
  F1_ABNORMAL_OPTIONS,
  createEmptyDebitRow,
  isAbnormalFlag,
  evaluateF1DebitEvidence,
  f1EvidenceStatusLabel,
  type F1DebitCheckRow,
  type F1CreditCheckRow,
  type F1VoucherSection,
} from '../composables/useF1ComprehensiveCheck'
import { useF1AiGenerate } from '../composables/useF1AiGenerate'
import { useF1ImportExport, type F1ImportSheet } from '../composables/useWorkpaperImportExport'
import { useF1CrossSheet } from '../composables/useF1CrossSheet'
import { useStickySectionNav } from '../composables/useStickySectionNav'
import { parseNum } from '../composables/useF1FormulaEngine'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { SampledVoucher, FillMode, Phase } from '../composables/useSamplingAlgorithms'
import { api } from '@/services/apiProxy'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import F1SheetAttachments from './F1SheetAttachments.vue'
import F1CreditCheckTable from './F1CreditCheckTable.vue'
import F1VoucherCheckDialog from './F1VoucherCheckDialog.vue'
import WpSamplingMethodologyBar from '../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../composables/shared/samplingFillTarget'

const f1VoucherNav = [
  { id: 'f1-7-sample', label: '样本' },
  { id: 'f1-7-sampling', label: '抽凭' },
  { id: 'f1-7-debit', label: '借方' },
  { id: 'f1-7-credit', label: '贷方' },
  { id: 'f1-7-post', label: '期后' },
  { id: 'f1-7-coverage', label: '比例' },
  { id: 'f1-7-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(f1VoucherNav)

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  year?: number
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const {
  samplingParams,
  debitRows,
  creditRows,
  postPeriodRows,
  auditNote,
  conclusion,
  coverageRows,
  debitChecked,
  creditChecked,
  postChecked,
  totalChecked,
  anomalyCount,
  anomalyRate,
  addSample,
  removeSample,
  updateCell,
  saveRow,
  updateSamplingParams,
  fillBookFromDetail,
  importPrioritySamples,
  autoMarkCrossPeriod,
  distributeSamples,
} = useF1VoucherCheck({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(wpIdRef)
const { exportTemplate, exportData, importData, importing } = useF1ImportExport({ wpId: wpIdRef })
const crossSheet = useF1CrossSheet({ allResponses: allResponsesRef })

const auditYear = computed(() => props.year ?? new Date().getFullYear() - 1)
const currentPhase = computed<Phase>(() => 'final')
const crossPeriodCutoff = ref(`${auditYear.value}-12-31`)

const checkDialogVisible = ref(false)
const activeCheckSection = ref<F1VoucherSection>('debit')
const activeCheckRow = ref<F1DebitCheckRow | F1CreditCheckRow | null>(null)

function debitEvidenceStatus(row: F1DebitCheckRow) {
  return f1EvidenceStatusLabel(evaluateF1DebitEvidence(row))
}

function openCheckDialog(section: F1VoucherSection, rowId: string): void {
  const rows =
    section === 'debit' ? debitRows.value
      : section === 'credit' ? creditRows.value
        : postPeriodRows.value
  const row = rows.find(item => item.rowId === rowId)
  if (!row) return
  activeCheckSection.value = section
  activeCheckRow.value = row
  checkDialogVisible.value = true
}

function onDialogSave(section: F1VoucherSection, patch: F1DebitCheckRow | F1CreditCheckRow): void {
  saveRow(section, patch)
  ElMessage.success('本笔单据核对已保存')
}

function doAutoMarkCrossPeriod(): void {
  const n = autoMarkCrossPeriod(crossPeriodCutoff.value)
  if (n > 0) ElMessage.success(`已标注 ${n} 笔期后跨期疑点`)
  else ElMessage.info('无需标注（无符合条件的期后样本）')
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'F1',
  allResponses: allResponsesRef,
  persist: (itemId, remark) => props.saveImmediate(itemId, { remark, conclusion: null }),
  isReadonly: computed(() => props.isReadonly),
})

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  distributeSamples(payload.samples as Array<Record<string, any>>)
  ElMessage.success(`已回填 ${payload.samples.length} 笔抽凭样本（按借贷方向分配至借方/贷方表）`)
}

const BOOK_FIELDS = ['bookDebit', 'bookCredit', 'bookPostPeriod'] as const
const ocrLoadingRowId = ref<string | null>(null)

const F1_OCR_FIELD_MAP: Record<string, string> = {
  date: 'date',
  凭证日期: 'date',
  voucher_date: 'date',
  voucher_no: 'voucherNo',
  凭证号: 'voucherNo',
  凭证编号: 'voucherNo',
  summary: 'businessContent',
  摘要: 'businessContent',
  business_content: 'businessContent',
  业务内容: 'businessContent',
  counter_account: 'counterAccount',
  对方科目: 'counterAccount',
  debit_amount: 'debitAmount',
  借方金额: 'debitAmount',
  credit_amount: 'creditAmount',
  贷方金额: 'creditAmount',
  amount: 'debitAmount',
  金额: 'debitAmount',
  supplier: 'supplierName',
  counterpart_name: 'supplierName',
  供应商: 'supplierName',
  对方单位: 'supplierName',
}

const debitTableData = computed(() => {
  const sub: F1DebitCheckRow = {
    ...createEmptyDebitRow(),
    rowId: '__subtotal__',
    supplierName: '合计',
  }
  return [...debitRows.value, sub]
})

function rowClassName({ row }: { row: { rowId: string } }) {
  return row.rowId === '__subtotal__' ? 'subtotal-row' : ''
}

function onBookAmountChange(index: number, value: any) {
  const field = BOOK_FIELDS[index]
  if (!field) return
  updateSamplingParams(field, Number(value) || 0)
}

function doFillBookFromDetail() {
  if (props.isReadonly) return
  const detResp = allResponsesRef.value.get('F1-det-rows')
  let debit = 0
  let credit = 0
  let postPeriodSettlement = 0
  if (detResp?.remark) {
    try {
      const rows = JSON.parse(detResp.remark) as Array<{
        debit?: number
        credit?: number
        postPeriodSettlement?: number
      }>
      for (const r of rows) {
        debit += parseNum(r.debit)
        credit += parseNum(r.credit)
        postPeriodSettlement += parseNum(r.postPeriodSettlement)
      }
    } catch { /* ignore */ }
  }
  if (debit === 0 && credit === 0 && postPeriodSettlement === 0) {
    ElMessage.warning('F1-2 明细暂无借/贷/期后结转数据，请先编制明细表')
    return
  }
  fillBookFromDetail({ debit, credit, postPeriodSettlement })
  ElMessage.success('已从 F1-2 回填账面金额（借方/贷方/期后结转）')
}

function doImportPrioritySamples() {
  if (props.isReadonly) return
  const detResp = allResponsesRef.value.get('F1-det-rows')
  if (!detResp?.remark) {
    ElMessage.warning('F1-2 明细暂无数据')
    return
  }
  try {
    const rows = JSON.parse(detResp.remark) as Array<Record<string, any>>
    const n = importPrioritySamples(rows)
    if (n > 0) ElMessage.success(`已从 F1-2 带入 ${n} 户重点样本（关联方/超1年/大额）至借方核查`)
    else ElMessage.info('无新增重点样本（可能已带入或明细无符合条件户）')
  } catch {
    ElMessage.warning('F1-2 明细解析失败')
  }
}

async function handleRowOcr(file: File, section: 'debit' | 'credit' | 'postPeriod', rowId: string): Promise<boolean> {
  if (props.isReadonly || !props) return false
  ocrLoadingRowId.value = rowId
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res: any = await api.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res?.data?.data ?? res?.data ?? res)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR 完成，未识别到可填充字段')
      return false
    }
    const preview = Object.entries(fields)
      .slice(0, 12)
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n')
    await ElMessageBox.confirm(`识别结果：\n${preview}\n\n是否填入当前行空字段？`, 'OCR 识别结果', {
      type: 'info',
      confirmButtonText: '填入',
      cancelButtonText: '取消',
    })
    const amountField = section === 'debit' ? 'debitAmount' : 'creditAmount'
    for (const [ocrKey, val] of Object.entries(fields)) {
      let target = F1_OCR_FIELD_MAP[ocrKey] || F1_OCR_FIELD_MAP[ocrKey.toLowerCase()]
      if (!target) continue
      if (target === 'debitAmount' || target === 'creditAmount') target = amountField
      const rows = section === 'debit'
        ? debitRows.value
        : section === 'credit'
          ? creditRows.value
          : postPeriodRows.value
      const row = rows.find(r => r.rowId === rowId)
      if (!row) continue
      const cur = (row as any)[target]
      if (cur != null && String(cur).trim() !== '' && cur !== 0) continue
      updateCell(section, rowId, target, val)
    }
    ElMessage.success('OCR 结果已填入空字段')
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('OCR 识别失败或已取消')
  } finally {
    ocrLoadingRowId.value = null
  }
  return false
}

/** F1-2 Z列合计 vs F1-7 期后贷方合计 */
const postPeriodCrossValidation = computed(() => {
  const f17Total = crossSheet.postPeriodSettlementSync.value.total
  if (f17Total === 0 && postChecked.value === 0) return ''

  const detResp = allResponsesRef.value.get('F1-det-rows')
  let f12ZTotal = 0
  if (detResp?.remark) {
    try {
      const rows = JSON.parse(detResp.remark) as Array<{ postPeriodSettlement?: number }>
      f12ZTotal = rows.reduce((sum, r) => sum + parseNum(r.postPeriodSettlement), 0)
    } catch { /* ignore */ }
  }

  const checked = postChecked.value || f17Total
  const diff = Math.abs(f12ZTotal - checked)
  if (diff < 0.01) return ''
  return `F1-2期后结转（Z列）合计 ${f12ZTotal.toLocaleString()} 元 ≠ F1-7期后贷方合计 ${checked.toLocaleString()} 元，差额 ${diff.toLocaleString()} 元`
})

const lowCoverageWarning = computed(() => {
  const low = coverageRows.value.filter(r => r.ratio != null && r.ratio < 30 && r.bookAmount > 0)
  if (!low.length) return ''
  return `以下方向检查比例低于 30%，请扩大样本量或在审计说明中解释：${low.map(r => `${r.direction}(${r.ratio}%)`).join('、')}`
})

function aiContext() {
  return {
    sheet: 'F1-7',
    samplingParams: { ...samplingParams.value },
    coverageRows: coverageRows.value,
    totalChecked: totalChecked.value,
    anomalyCount: anomalyCount.value,
    anomalyRate: anomalyRate.value,
    debitChecked: debitChecked.value,
    creditChecked: creditChecked.value,
    postChecked: postChecked.value,
  }
}

async function generateNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'comprehensive-note',
    auditNote.value,
    aiContext(),
    'AI 生成 · F1-7 审计说明',
  )
  if (text) auditNote.value = text
}

async function generateConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'comprehensive-conclusion',
    conclusion.value,
    aiContext(),
    'AI 生成 · F1-7 审计结论',
  )
  if (text) conclusion.value = text
}

function openReview() {
  openReviewDialog?.('F1-vc-conclusion')
}

async function handleImport(file: File, sheet: F1ImportSheet): Promise<boolean> {
  const result = await importData(sheet, file)
  if (result) await reloadWorkpaperData?.()
  return false
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function formatRatio(ratio: number | null): string {
  if (ratio == null) return '—'
  return `${ratio.toFixed(2)}%`
}

function ratioClass(ratio: number | null): string {
  if (ratio == null) return ''
  return ratio > 0 && ratio < 30 ? 'ratio-low' : ''
}
</script>

<style scoped>
.f1-comprehensive-check { padding: 16px; }
.f1-comprehensive-check :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f1-comprehensive-check :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

.objective-alert { margin-bottom: 12px; }
.objective-title { font-weight: 600; margin-bottom: 4px; }
.objective-list { margin: 4px 0 0; padding-left: 1.2em; line-height: 1.6; }

.sampling-card { margin-bottom: 12px; border-radius: 8px; }
.sampling-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 600; font-size: 14px; }

.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.param-item { display: flex; align-items: flex-start; gap: 8px; }
.param-item.span-2 { grid-column: 1 / -1; }
.param-label { font-size: 12px; color: #909399; white-space: nowrap; min-width: 88px; padding-top: 5px; }

.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.vc-section { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; }
.section-header h4 { font-size: 14px; font-weight: 600; margin: 0; }
.section-header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.subtotal-label { font-weight: 700; }
.subtotal-val { font-weight: 700; }
.amt { text-align: right; display: inline-block; width: 100%; }
.auto { color: #909399; }
.abnormal-cell :deep(.el-input__inner),
.abnormal-cell :deep(.el-select__wrapper) { color: #f56c6c; font-weight: 600; }
:deep(.subtotal-row) { background-color: #fafafa !important; font-weight: 600; }

.st-sec-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
  position: sticky;
  top: 0;
  z-index: 5;
  padding: 8px 0;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(4px);
}
.st-sec-btn {
  border: 1px solid #dcdfe6;
  background: #fff;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
}
.st-sec-btn.active {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
}

.cross-alert { margin: 12px 0; }
.coverage-table { max-width: 720px; margin-bottom: 12px; }
.ratio-hint { font-size: 12px; color: #909399; font-weight: 400; }
.ratio-low { color: #e6a23c; font-weight: 600; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; }
.opinion-section { margin-top: 16px; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; }
.opinion-actions { display: flex; gap: 6px; }
</style>
