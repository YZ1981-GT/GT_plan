<template>
<div class="d3-voucher-check">
  <!-- 审计目标 -->
  <el-alert type="info" :closable="false" show-icon class="audit-objective">
    <template #title>
      <strong>审计目标</strong>：通过抽样检查本期增减变动及期后结转凭证，验证预收账款发生的真实性、完整性与截止准确性，识别跨期确认与虚构预收（CAS 1301 审计证据 / CAS 1313 截止测试）。
    </template>
  </el-alert>

  <!-- 抽样参数区 -->
  <div class="sampling-params-card">
    <h4 class="card-title section-header-row">
      抽样参数
      <GtReviewTrigger section-id="D3-vc-header" />
    </h4>
    <div class="params-grid">
      <div class="param-item">
        <span class="param-label">测试总体</span>
        <el-input v-model="samplingParams.testPopulation" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('testPopulation', val)" />
      </div>
      <div class="param-item">
        <span class="param-label">特定样本</span>
        <el-input v-model="samplingParams.specificSamples" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('specificSamples', val)" />
      </div>
      <div class="param-item">
        <span class="param-label">抽样总体</span>
        <el-input v-model="samplingParams.samplingPopulation" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('samplingPopulation', val)" />
      </div>
      <div class="param-item">
        <span class="param-label">抽样方法</span>
        <el-input v-model="samplingParams.samplingMethod" size="small" :disabled="isReadonly"
          @change="(val: string) => updateSamplingParams('samplingMethod', val)" />
      </div>
    </div>
    <!-- 进度条 -->
    <div class="sampling-progress">
      <span>抽样进度：{{ samplingParams.currentSampleSize }} / {{ samplingParams.targetSampleSize }}</span>
      <el-progress
        :percentage="progressPct"
        :stroke-width="8"
        :color="progressPct >= 100 ? '#67c23a' : '#409eff'"
        style="flex: 1; margin-left: 12px"
      />
    </div>
  </div>

  <!-- 汇总 + 导入导出 -->
  <div class="summary-bar">
    <el-tag type="info">已检查：{{ totalChecked }}</el-tag>
    <el-tag :type="anomalyCount > 0 ? 'danger' : 'success'">异常：{{ anomalyCount }}</el-tag>
    <el-tag :type="anomalyRate > 10 ? 'danger' : 'info'">异常率：{{ anomalyRate.toFixed(1) }}%</el-tag>
    <GtIndexChip target="voucher-sampling-engine" label="抽凭引擎" />
    <el-button size="small" type="warning" :disabled="isReadonly" @click="openSampling">⚡ 抽凭</el-button>
    <el-button-group size="small" style="margin-left: auto">
      <el-button @click="onExportTemplate">导出模板</el-button>
      <el-button @click="onExportData">导出数据</el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
        <el-button>导入数据</el-button>
      </el-upload>
    </el-button-group>
  </div>

  <div v-if="useVirtualScroll" class="virtual-toolbar">
    <el-alert type="info" :closable="false" class="virtual-hint">
      行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式
    </el-alert>
    <el-button size="small" @click="toggleBrowseMode">
      {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
    </el-button>
  </div>
  <el-table-v2
    v-if="useVirtualScroll && browseMode"
    :columns="virtualColumns"
    :data="browseRows"
    :width="tableWidth"
    :height="tableHeight"
    :row-height="36"
    :header-height="40"
    fixed
    class="virtual-table"
  />

  <template v-if="!useVirtualScroll || !browseMode">
  <!-- (1) 本期增减变动 -->
  <div class="vc-section">
    <div class="section-header">
      <h4>(1) 本期增减变动检查</h4>
      <el-button size="small" :disabled="isReadonly" @click="addSample('current')">+ 添加样本</el-button>
    </div>
    <el-table :data="currentChangeRows" size="small" border stripe :height="currentChangeRows.length > 15 ? '400px' : undefined">
      <el-table-column type="index" label="#" width="40" />
      <el-table-column label="客户名称" width="120">
        <template #default="{ row }">
          <el-input v-model="row.customerName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'customerName', val)" />
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD"
            @change="(val: string) => updateCell('current', row.rowId, 'date', val)" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="90">
        <template #default="{ row }">
          <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'voucherNo', val)" />
        </template>
      </el-table-column>
      <el-table-column label="业务内容" width="130">
        <template #default="{ row }">
          <el-input v-model="row.businessContent" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'businessContent', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'counterAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方明细" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterDetailAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'counterDetailAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="借方" width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.debitAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'debitAmount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'creditAmount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="原始凭证" width="100">
        <template #default="{ row }">
          <el-input v-model="row.supportingDoc" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'supportingDoc', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核1" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[0]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.0', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核2" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[1]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.1', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核3" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[2]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.2', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核4" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[3]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.3', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核5" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[4]" :disabled="isReadonly"
            @change="(val: any) => updateCell('current', row.rowId, 'checkItems.4', val)" />
        </template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('current', row.rowId, 'indexRef', val)" />
        </template>
      </el-table-column>
      <el-table-column label="异常标记" width="150">
        <template #default="{ row }">
          <el-select v-model="row.isAbnormal" size="small" :disabled="isReadonly" clearable filterable allow-create
            default-first-option placeholder="正常"
            :class="{ 'abnormal-cell': !!row.isAbnormal }"
            @change="(val: string) => updateCell('current', row.rowId, 'isAbnormal', val || '')">
            <el-option v-for="opt in ABNORMAL_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <!-- 跨期疑点 → D4 收入截止测试 可追溯标识（Req 11.2） -->
          <div v-if="row.isAbnormal === CROSS_PERIOD_ANOMALY" class="anomaly-trace-row">
            <GtIndexChip value="wp:D4" context="跨期疑点关联收入截止测试底稿 D4" :prevent-navigate="false" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="附件" width="72" align="center">
        <template #default="{ row }">
          <el-upload
            :show-file-list="false"
            :accept="OCR_ACCEPT"
            :disabled="isReadonly"
            :before-upload="makeRowOcrHandler('current', row.rowId)"
          >
            <el-tooltip :content="row.attachment ? `已关联：${row.attachment}（点击可重新上传识别）` : '上传图片/PDF 并 OCR 识别'" placement="top">
              <el-button
                size="small"
                :type="row.attachment ? 'success' : 'default'"
                link
                :disabled="isReadonly"
                :loading="ocrLoadingRowId === row.rowId"
              >📎{{ row.attachment ? '✓' : '' }}</el-button>
            </el-tooltip>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="50" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="删除？" @confirm="removeSample('current', row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- (2) 期后结转检查 -->
  <div class="vc-section">
    <div class="section-header">
      <h4>(2) 期后结转检查</h4>
      <el-button size="small" :disabled="isReadonly" @click="addSample('postPeriod')">+ 添加样本</el-button>
    </div>
    <el-table :data="postPeriodRows" size="small" border stripe :height="postPeriodRows.length > 15 ? '400px' : undefined">
      <el-table-column type="index" label="#" width="40" />
      <el-table-column label="客户名称" width="120">
        <template #default="{ row }">
          <el-input v-model="row.customerName" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'customerName', val)" />
        </template>
      </el-table-column>
      <el-table-column label="日期" width="100">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'date', val)" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="90">
        <template #default="{ row }">
          <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'voucherNo', val)" />
        </template>
      </el-table-column>
      <el-table-column label="业务内容" width="130">
        <template #default="{ row }">
          <el-input v-model="row.businessContent" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'businessContent', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'counterAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="对方明细" width="100">
        <template #default="{ row }">
          <el-input v-model="row.counterDetailAccount" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'counterDetailAccount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="100" align="right">
        <template #default="{ row }">
          <el-input v-model.number="row.creditAmount" size="small" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'creditAmount', val)" />
        </template>
      </el-table-column>
      <el-table-column label="原始凭证" width="100">
        <template #default="{ row }">
          <el-input v-model="row.supportingDoc" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'supportingDoc', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核1" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[0]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.0', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核2" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[1]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.1', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核3" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[2]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.2', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核4" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[3]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.3', val)" />
        </template>
      </el-table-column>
      <el-table-column label="核5" width="40" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checkItems[4]" :disabled="isReadonly"
            @change="(val: any) => updateCell('postPeriod', row.rowId, 'checkItems.4', val)" />
        </template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }">
          <el-input v-model="row.indexRef" size="small" :disabled="isReadonly"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'indexRef', val)" />
        </template>
      </el-table-column>
      <el-table-column label="异常标记" width="150">
        <template #default="{ row }">
          <el-select v-model="row.isAbnormal" size="small" :disabled="isReadonly" clearable filterable allow-create
            default-first-option placeholder="正常"
            :class="{ 'abnormal-cell': !!row.isAbnormal }"
            @change="(val: string) => updateCell('postPeriod', row.rowId, 'isAbnormal', val || '')">
            <el-option v-for="opt in ABNORMAL_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <!-- 跨期疑点 → D4 收入截止测试 可追溯标识（Req 11.2） -->
          <div v-if="row.isAbnormal === CROSS_PERIOD_ANOMALY" class="anomaly-trace-row">
            <GtIndexChip value="wp:D4" context="跨期疑点关联收入截止测试底稿 D4" :prevent-navigate="false" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="附件" width="72" align="center">
        <template #default="{ row }">
          <el-upload
            :show-file-list="false"
            :accept="OCR_ACCEPT"
            :disabled="isReadonly"
            :before-upload="makeRowOcrHandler('postPeriod', row.rowId)"
          >
            <el-tooltip :content="row.attachment ? `已关联：${row.attachment}（点击可重新上传识别）` : '上传图片/PDF 并 OCR 识别'" placement="top">
              <el-button
                size="small"
                :type="row.attachment ? 'success' : 'default'"
                link
                :disabled="isReadonly"
                :loading="ocrLoadingRowId === row.rowId"
              >📎{{ row.attachment ? '✓' : '' }}</el-button>
            </el-tooltip>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="50" v-if="!isReadonly">
        <template #default="{ row }">
          <el-popconfirm title="删除？" @confirm="removeSample('postPeriod', row.rowId)">
            <template #reference><el-button size="small" type="danger" link>删</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>
  </template>

  <!-- D3-2 Z列合计交叉验证 -->
  <el-alert
    v-if="postPeriodCrossValidation"
    :title="postPeriodCrossValidation"
    type="warning"
    :closable="false"
    show-icon
    style="margin: 12px 0"
  />

  <!-- 覆盖率反馈 + 异常汇总 + 跨底稿联动（Req 8 / Req 11.2/11.3/11.4） -->
  <el-card class="coverage-card" shadow="never">
    <template #header>
      <span class="coverage-title">覆盖率与异常汇总</span>
    </template>

    <!-- 覆盖率/代表性反馈 -->
    <div class="coverage-grid">
      <div class="coverage-item">
        <div class="coverage-label">笔数覆盖率</div>
        <el-progress
          :percentage="Math.round(coverageFeedback.countCoverageRate)"
          :stroke-width="10"
          :color="coverageFeedback.lowCoverage ? '#e6a23c' : '#67c23a'"
        />
        <div class="coverage-sub">
          已检查 {{ coverageFeedback.checkedCount }}
          <template v-if="coverageFeedback.targetSampleSize > 0"> / 目标 {{ coverageFeedback.targetSampleSize }}</template>
          <template v-else>（未设定目标样本量）</template>
        </div>
      </div>
      <div class="coverage-item">
        <div class="coverage-label">核对完成率</div>
        <el-progress
          :percentage="Math.round(coverageFeedback.completionRate)"
          :stroke-width="10"
          :color="coverageFeedback.completionRate >= 100 ? '#67c23a' : '#409eff'"
        />
        <div class="coverage-sub">已完成核对 {{ coverageFeedback.completedCount }} / {{ coverageFeedback.checkedCount }}</div>
      </div>
      <div class="coverage-item">
        <div class="coverage-label">已检查金额合计</div>
        <div class="coverage-value">{{ fmtAmt(coverageFeedback.checkedAmount) }} 元</div>
      </div>
      <div class="coverage-item">
        <div class="coverage-label">异常率</div>
        <div class="coverage-value" :class="{ 'coverage-value--danger': anomalyRate > 10 }">
          {{ anomalyRate.toFixed(1) }}%（异常 {{ anomalyCount }} 笔）
        </div>
      </div>
    </div>

    <!-- 覆盖率偏低提示（Req 8.3/8.4） -->
    <el-alert
      v-if="coverageFeedback.lowCoverage"
      type="warning"
      :closable="false"
      show-icon
      class="coverage-warning"
      title="覆盖率偏低：已检查笔数低于目标样本量，建议增大样本量或调整抽样条件，并关注是否存在未覆盖的大额凭证。"
    />

    <!-- 异常汇总 + 跨底稿可追溯联动 -->
    <div class="anomaly-trace-summary">
      <div class="trace-line">
        <span class="trace-label">异常汇总（→ 错报汇总）：</span>
        <el-tag :type="anomalySummary.total > 0 ? 'danger' : 'success'" size="small">
          异常 {{ anomalySummary.total }} 笔
        </el-tag>
        <GtIndexChip value="wp:A13" context="异常汇总至错报汇总底稿 A13" />
        <span class="trace-hint">异常项保留与错报汇总底稿 A13 的可追溯关联</span>
      </div>
      <div class="trace-line">
        <span class="trace-label">跨期疑点（→ 收入截止测试）：</span>
        <el-tag :type="crossPeriodCount > 0 ? 'warning' : 'info'" size="small">
          跨期疑点 {{ crossPeriodCount }} 笔
        </el-tag>
        <GtIndexChip value="wp:D4" context="跨期疑点关联收入截止测试底稿 D4" />
        <span class="trace-hint">跨期疑点行保留与收入截止测试底稿 D4 的可追溯关联</span>
      </div>
      <div v-if="anomalyTypeEntries.length" class="trace-line trace-line--types">
        <span class="trace-label">异常类型分布：</span>
        <el-tag
          v-for="[type, count] in anomalyTypeEntries"
          :key="type"
          size="small"
          :type="type === CROSS_PERIOD_ANOMALY ? 'warning' : 'info'"
          effect="plain"
        >{{ type }} × {{ count }}</el-tag>
      </div>
    </div>
  </el-card>

  <!-- 检查结论（AI 辅助：建议 → 确认 → 写入） -->
  <el-card class="conclusion-card" shadow="never">
    <template #header>
      <div class="conclusion-header">
        <span class="conclusion-title">检查结论</span>
        <div class="conclusion-actions">
          <el-button size="small" type="primary" link :disabled="isReadonly || aiLoading" @click="handleAiConclusion">
            🤖 AI 生成
          </el-button>
          <GtReviewTrigger section-id="D3-vc-conclusion" />
        </div>
      </div>
    </template>
    <el-input
      :model-value="conclusion"
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 10 }"
      :disabled="isReadonly"
      placeholder="综合抽样检查结果，对预收账款发生的真实性、完整性与截止准确性给出结论……"
      @change="(val: string) => updateConclusion(val)"
    />
    <div v-if="!aiAvailable" class="ai-hint">AI 服务暂不可用，可手工录入结论</div>
  </el-card>

  <!-- 编制提示 -->
  <details class="guidance-fold">
    <summary>📋 编制提示（CAS 1301 审计证据 / CAS 1313 截止测试）</summary>
    <p>1. 本期增减变动：核对凭证与原始单据（合同、收款凭据、发票），验证预收款发生的真实性与金额准确性；</p>
    <p>2. 期后结转：检查资产负债表日后预收款结转确认收入的凭证，判断收入截止是否正确、有无提前/滞后确认；</p>
    <p>3. 异常标记后请在备注说明具体异常，跨期疑点应关联收入截止测试（D4）并评估对报表的影响。</p>
    <p>4. ⚡ 抽凭：按预收账款科目（2203）从四表库凭证库检索凭证，勾选后一次性回填，来源自动标注为「抽凭」。</p>
  </details>

  <!-- 抽凭引擎弹窗（dialog-mode，科目 2203） -->
  <el-dialog
    v-model="showSampling"
    title="⚡ 抽凭引擎（科目 2203 预收账款）"
    width="880px"
    :close-on-click-modal="false"
    append-to-body
    destroy-on-close
  >
    <div class="sampling-target-bar">
      <span class="sampling-target-label">回填目标区块：</span>
      <el-radio-group v-model="samplingSection" size="small">
        <el-radio-button value="current">本期增减变动</el-radio-button>
        <el-radio-button value="postPeriod">期后结转</el-radio-button>
      </el-radio-group>
    </div>
    <GtVoucherSamplingEngine
      v-if="showSampling && wpId && projectId"
      account-code="2203"
      :phase="phase"
      default-method="random"
      :workpaper-id="wpId"
      :project-id="projectId"
      :year="engineYear"
      @filled="onSampleFilled"
    />
  </el-dialog>

  <!-- 回写后 AI 复核弹窗（Req 26，section=voucher-review） -->
  <PostFillAiReviewDialog
    v-model="showReview"
    :wp-id="wpId"
    :rows="reviewRows"
    section="voucher-review"
    :ai-available="aiAvailable"
    @applied="onReviewApplied"
  />

</div>
</template>

<script setup lang="ts">
/**
 * D3TabVoucherCheck.vue — D3-7 凭证检查表
 * 抽样参数 + (1)本期增减 + (2)期后结转 + 汇总 + 跨期标记
 */
import { computed, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD3VoucherCheck, isAllowedAttachment, CROSS_PERIOD_ANOMALY } from '../composables/useD3VoucherCheck'
import { useD3AiGenerate } from '../composables/useD3AiGenerate'
import { useD3TabImportExport } from '../composables/useD3TabImportExport'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import type { ChecklistResponse } from '../composables/useD3FormData'
import type { Phase, FillMode, SamplingMethod, SampledVoucher } from '../composables/useSamplingAlgorithms'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import PostFillAiReviewDialog, { type PostFillReviewRow } from '../voucher-sampling/PostFillAiReviewDialog.vue'

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  year?: number
  phase?: Phase
}>(), {
  year: undefined,
  phase: 'final',
})

// 父级经模板传入的是解包后的普通值（非 ref），此处重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>

const {
  samplingParams,
  currentChangeRows,
  postPeriodRows,
  totalChecked,
  anomalyCount,
  anomalyRate,
  anomalySummary,
  crossPeriodCount,
  coverageFeedback,
  addSample,
  removeSample,
  updateCell,
  updateSamplingParams,
  ocrLoadingRowId,
  handleRowOcr,
  conclusion,
  updateConclusion,
  fillFromSampling,
} = useD3VoucherCheck({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const progressPct = computed(() => {
  if (!samplingParams.value.targetSampleSize) return 0
  return Math.min(100, Math.round((samplingParams.value.currentSampleSize / samplingParams.value.targetSampleSize) * 100))
})

/** 异常类型分布（[类型, 笔数] 数组，供汇总区标签展示） */
const anomalyTypeEntries = computed<[string, number][]>(() =>
  Object.entries(anomalySummary.value.byType),
)

/** 异常标记常用枚举（可点选 + 允许自定义输入） */
const ABNORMAL_OPTIONS = ['跨期疑点', '金额异常', '无原始凭证', '对方科目异常', '重复入账', '其他异常']

/** el-upload accept 限定：图片 + PDF（Req 1.2） */
const OCR_ACCEPT = '.jpg,.jpeg,.png,.gif,.bmp,.webp,.pdf,image/*,application/pdf'

/**
 * 生成某行 el-upload 的 before-upload 处理器：
 * 类型校验（不符拒绝并提示，Req 1.5）→ 触发行级 OCR → 返回 false 阻止默认上传。
 */
function makeRowOcrHandler(section: 'current' | 'postPeriod', rowId: string) {
  return (file: File): boolean => {
    if (props.isReadonly) return false
    if (!isAllowedAttachment(file)) {
      ElMessage.error('仅支持图片或 PDF 格式的附件')
      return false
    }
    void handleRowOcr(section, rowId, file)
    return false
  }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 抽凭引擎联动（Req 4/7/24：科目 2203 预收账款） ───────────────────────────

const showSampling = ref(false)
/** 抽样结果回填目标区块 */
const samplingSection = ref<'current' | 'postPeriod'>('current')

/** 抽凭总体年度：优先父级传入，缺省取上一年度 */
const engineYear = computed(() => props.year ?? (new Date().getFullYear() - 1))

/** 打开抽凭弹窗（只读禁用，Req 4.5） */
function openSampling() {
  if (props.isReadonly) return
  showSampling.value = true
}

/**
 * 抽样引擎 @filled 回调：按填充模式回写到目标区块，行来源=抽凭（Req 7）。
 * 只读禁用回填（Req 12.3）。
 */
function onSampleFilled(payload: {
  samples: SampledVoucher[]
  phase: Phase
  fillMode: FillMode
  method?: SamplingMethod
}) {
  if (props.isReadonly) return
  const n = fillFromSampling(payload.samples, payload.fillMode, samplingSection.value)
  showSampling.value = false
  if (n > 0) {
    ElMessage.success(`已回填 ${n} 条抽凭样本至${samplingSection.value === 'current' ? '本期增减变动' : '期后结转'}（来源=抽凭）`)
    // 回写完成 → 触发回写后 AI 复核弹窗（Req 26.1）
    triggerPostFillReview(payload.samples)
  } else {
    ElMessage.info('未回填任何样本')
  }
}

// ─── 回写后 AI 复核（Req 26：抽凭回写后触发，section=voucher-review） ─────────

const showReview = ref(false)
const reviewRows = ref<PostFillReviewRow[]>([])

/** 抽凭回写完成后弹出 AI 复核（R26.1）；确认后写入检查结论（R26.5） */
function triggerPostFillReview(samples: SampledVoucher[]) {
  reviewRows.value = samples.map((s) => ({
    voucherNo: s.voucherNo,
    voucherDate: s.voucherDate,
    summary: s.summary,
    debitAmount: s.debitAmount,
    creditAmount: s.creditAmount,
    counterpartAccount: s.counterpartAccount,
    abnormal: s.abnormal,
  }))
  showReview.value = true
}

/** 确认采用 AI 复核意见 → 追加填入检查结论（R26.5/26.8：确认前不定稿） */
function onReviewApplied(text: string) {
  if (props.isReadonly) return
  const merged = conclusion.value ? `${conclusion.value}\n\n【AI 复核意见】\n${text}` : text
  updateConclusion(merged)
  ElMessage.success('AI 复核意见已填入检查结论')
}

// ─── AI 辅助生成检查结论（Req 3：建议 → 确认 → 写入） ────────────────────────

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useD3AiGenerate(wpIdRef)

/** 触发 AI 生成检查结论：建议 → 人工确认 → 写入（Req 3.2/3.3/3.4/3.5） */
async function handleAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'voucher-conclusion',
    conclusion.value,
    {
      已检查笔数: totalChecked.value,
      异常笔数: anomalyCount.value,
      异常率: `${anomalyRate.value.toFixed(1)}%`,
    },
    'AI 生成凭证检查结论',
  )
  if (text != null) updateConclusion(text)
}

const browseRows = computed(() => [
  ...currentChangeRows.value.map(r => ({
    section: '本期',
    customerName: r.customerName,
    voucherNo: r.voucherNo,
    debit: r.debitAmount,
    credit: r.creditAmount,
  })),
  ...postPeriodRows.value.map(r => ({
    section: '期后',
    customerName: r.customerName,
    voucherNo: r.voucherNo,
    debit: r.debitAmount,
    credit: r.creditAmount,
  })),
])

const browseRowCount = computed(() => browseRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('section', '区块', 70),
  virtualTextCol('customerName', '客户名称', 130),
  virtualTextCol('voucherNo', '凭证号', 90),
  virtualNumCol('debit', '借方', 100, fmtAmt),
  virtualNumCol('credit', '贷方', 100, fmtAmt),
])

const {
  browseMode,
  useVirtualScroll,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 960,
})

// ─── D3-2 Z列合计交叉验证 ───────────────────────────────────────────────────
import { useD3CrossSheet } from '../composables/useD3CrossSheet'
import { parseNum } from '../composables/useD3FormulaEngine'

const crossSheet = useD3CrossSheet({ allResponses: allResponsesRef })

/** D3-2 Z列（期后结转）合计 vs D3-7 (2)期后结转贷方合计 交叉验证 */
const postPeriodCrossValidation = computed(() => {
  const d37Total = crossSheet.postPeriodSettlementSync.value.total
  if (d37Total === 0) return ''

  // 从 D3-2 明细行聚合 Z列合计
  const detResp = allResponsesRef.value.get('D3-det-rows')
  let d32ZTotal = 0
  if (detResp?.remark) {
    try {
      const rows = JSON.parse(detResp.remark) as Array<{ postPeriodSettlement?: number }>
      d32ZTotal = rows.reduce((sum, r) => sum + parseNum(r.postPeriodSettlement), 0)
    } catch { /* ignore */ }
  }

  const diff = Math.abs(d32ZTotal - d37Total)
  if (diff < 0.01) return ''
  return `D3-2期后结转（Z列）合计 ${d32ZTotal.toLocaleString()} 元 ≠ D3-7期后结转贷方合计 ${d37Total.toLocaleString()} 元，差额 ${diff.toLocaleString()} 元`
})

const { onExportTemplate, onExportData, onImportFile } = useD3TabImportExport(wpIdRef, 'D3-7')
</script>

<style scoped>
.d3-voucher-check { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.guidance-fold { margin-top: 16px; font-size: 12px; color: #606266; background: #f9fafb; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; }
.guidance-fold summary { cursor: pointer; font-weight: 600; color: #409eff; }
.guidance-fold p { margin: 6px 0 0; line-height: 1.6; }
.sampling-params-card { padding: 16px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.section-header-row { display: flex; align-items: center; gap: 8px; }
.params-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.param-item { display: flex; align-items: center; gap: 8px; }
.param-label { font-size: 12px; color: #909399; white-space: nowrap; min-width: 60px; }
.sampling-progress { display: flex; align-items: center; font-size: 12px; color: #606266; }
.summary-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.virtual-hint { flex: 1; min-width: 200px; margin: 0; }
.virtual-table { margin-bottom: 12px; }
.vc-section { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-header h4 { font-size: 14px; font-weight: 600; }
.abnormal-cell :deep(.el-input__inner) { color: #f56c6c; font-weight: 600; }
.review-actions { margin-top: 12px; }
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }
.conclusion-title { font-size: 14px; font-weight: 600; }
.conclusion-actions { display: flex; align-items: center; gap: 8px; }
.ai-hint { margin-top: 6px; font-size: 12px; color: #e6a23c; }
.sampling-target-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.sampling-target-label { font-size: var(--wp-font-size, 13px); color: #606266; }
.anomaly-trace-row { margin-top: 4px; }
.coverage-card { margin-top: 16px; }
.coverage-title { font-size: 14px; font-weight: 600; }
.coverage-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px 24px; }
.coverage-item { display: flex; flex-direction: column; gap: 6px; }
.coverage-label { font-size: 12px; color: #909399; }
.coverage-value { font-size: 14px; font-weight: 600; color: #303133; }
.coverage-value--danger { color: #f56c6c; }
.coverage-sub { font-size: 12px; color: #606266; }
.coverage-warning { margin-top: 12px; }
.anomaly-trace-summary { margin-top: 16px; padding-top: 12px; border-top: 1px dashed #ebeef5; display: flex; flex-direction: column; gap: 10px; }
.trace-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.trace-line--types { align-items: flex-start; }
.trace-label { font-size: var(--wp-font-size, 13px); color: #606266; min-width: 168px; }
.trace-hint { font-size: 12px; color: #909399; }
</style>
