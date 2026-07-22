<template>
  <div class="g9-voucher" data-testid="g9-voucher-check">
    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表抽取其他非流动金融资产（科目 1504）相关记账凭证，逐笔核对原始单据、授权、账务处理、分类、公允价值与减值。</p>
        <p>2. 核对项为三态：未测 / 通过 / 不通过；任一「不通过」自动标异常，「未测」不计入异常。截止跨期可强制异常，核对通过后可取消强制。</p>
        <p>3. 先填写抽样参数 → 抽凭引擎回填 → AI 复核 → 挂接 G9-2 资产查看联动提示 → 逐笔核对 → 回填 G9A 程序 6/7/12。</p>
        <p>4. 可用来源分池（抽凭 / 截止 / 手工）；金额类异常可一键推送 A13；OCR 仅填空字段、低置信度需复核。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：通过凭证检查核实其他非流动金融资产（科目1504）交易的真实性、完整性与计量准确性，验证分类、公允价值计量及减值计提的会计处理正确。"
    />

    <!-- 抽样参数（对齐 Excel「抽样总体 / 确定的抽样样本量」） -->
    <div class="sampling-params-card" data-testid="g9-vc-params">
      <h4 class="card-title">抽样参数</h4>
      <div class="params-grid">
        <div class="param-item">
          <span class="param-label">测试总体</span>
          <el-input
            :model-value="vc.samplingParams.value.testPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="如：科目1504本期发生额共XX笔、金额XX"
            @change="(val: string) => vc.updateSamplingParams('testPopulation', val)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">特定样本</span>
          <el-input
            :model-value="vc.samplingParams.value.specificSamples"
            size="small"
            :disabled="isReadonly"
            placeholder="大额/异常/关联方/Level3 等必选样本说明"
            @change="(val: string) => vc.updateSamplingParams('specificSamples', val)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">抽样总体</span>
          <el-input
            :model-value="vc.samplingParams.value.samplingPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="扣除特定样本后的抽样总体"
            @change="(val: string) => vc.updateSamplingParams('samplingPopulation', val)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">抽样方法</span>
          <el-select
            :model-value="vc.samplingParams.value.samplingMethod"
            size="small"
            clearable
            filterable
            :disabled="isReadonly"
            placeholder="请选择抽样方法"
            style="width: 100%"
            @change="(val: string) => vc.updateSamplingParams('samplingMethod', val ?? '')"
          >
            <el-option
              v-for="o in G9_SAMPLING_METHOD_OPTIONS"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">目标样本量</span>
          <el-input-number
            :model-value="vc.samplingParams.value.targetSampleSize"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="(val: number | undefined) => vc.updateSamplingParams('targetSampleSize', val ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">总体笔数</span>
          <el-input-number
            :model-value="vc.samplingParams.value.populationCount"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="(val: number | undefined) => vc.updateSamplingParams('populationCount', val ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">总体金额</span>
          <el-input-number
            :model-value="vc.samplingParams.value.populationAmount"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="(val: number | undefined) => vc.updateSamplingParams('populationAmount', val ?? 0)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">抽样过程</span>
          <el-input
            :model-value="vc.samplingParams.value.samplingProcess"
            size="small"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="简述样本选取过程、样本计算器索引或 MUS 参数等"
            @change="(val: string) => vc.updateSamplingParams('samplingProcess', val)"
          />
        </div>
      </div>
      <div class="sampling-progress">
        <span>抽样进度：{{ vc.samplingParams.value.currentSampleSize }} / {{ vc.samplingParams.value.targetSampleSize || '—' }}</span>
        <el-progress
          :percentage="vc.progressPct.value"
          :stroke-width="8"
          :color="vc.progressPct.value >= 100 ? '#67c23a' : '#409eff'"
          style="flex: 1; margin-left: 12px"
        />
      </div>
      <div class="completion-row">
        <span>编制完成度 {{ vc.completion.value.pct }}%</span>
        <el-progress
          :percentage="vc.completion.value.pct"
          :stroke-width="8"
          :color="vc.completion.value.pct >= 80 ? '#67c23a' : '#e6a23c'"
          style="flex: 1; margin-left: 12px"
        />
        <el-tooltip placement="top">
          <template #content>
            <div v-for="c in vc.completion.value.checklist" :key="c.key">
              {{ c.ok ? '✓' : '○' }} {{ c.label }}
            </div>
          </template>
          <el-tag size="small" type="info" style="margin-left:8px;cursor:help">明细</el-tag>
        </el-tooltip>
      </div>
    </div>

    <div class="section-head tab-toolbar">
      <h3 class="sheet-title">G9-6 凭证检查表</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G9-6" />
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-6" @imported="onImported" />
        <el-button size="small" type="warning" :disabled="isReadonly" data-testid="g9-open-sampling" @click="showSampling = true">
          ⚡ 抽凭
        </el-button>
        <el-button size="small" :disabled="isReadonly" data-testid="g9-export-memo" @click="exportMemo">
          📄 抽样备忘
        </el-button>
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="danger"
          plain
          :loading="vc.a13Pushing.value"
          :disabled="vc.quantitativeAbnormalCount.value <= 0"
          data-testid="g9-push-a13"
          @click="onPushA13"
        >
          推送金额异常→A13
          <template v-if="vc.quantitativeAbnormalCount.value">（{{ vc.quantitativeAbnormalCount.value }}）</template>
        </el-button>
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="success"
          plain
          :loading="vc.procedureMarking.value"
          :disabled="!vc.rows.value.length"
          data-testid="g9-mark-g9a"
          @click="onMarkProcedure"
        >
          {{ vc.procedureMarked.value ? '已回填 G9A（可重写）' : '回填 G9A 凭证程序' }}
        </el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>

    <div class="summary-bar">
      <el-tag size="small" type="info">共 {{ vc.rows.value.length }} 行</el-tag>
      <el-tag size="small" :type="vc.untestedCount.value > 0 ? 'warning' : 'success'">未测 {{ vc.untestedCount.value }}</el-tag>
      <el-tag size="small" :type="vc.abnormalCount.value > 0 ? 'danger' : 'success'">异常 {{ vc.abnormalCount.value }}</el-tag>
      <el-tag size="small" :type="vc.quantitativeAbnormalCount.value > 0 ? 'danger' : 'info'">
        金额异常 {{ vc.quantitativeAbnormalCount.value }}
      </el-tag>
      <el-tag size="small" type="info">异常率 {{ vc.anomalyRate.value.toFixed(1) }}%</el-tag>
      <span class="summary-sep">|</span>
      <el-tag size="small" :type="vc.coverage.value.countPct >= 100 ? 'success' : 'warning'">
        笔数覆盖 {{ vc.coverage.value.countPct.toFixed(0) }}%
      </el-tag>
      <el-tag
        size="small"
        :type="vc.samplingParams.value.populationAmount <= 0 ? 'info' : (vc.coverage.value.amountPct >= 60 ? 'success' : 'warning')"
      >
        金额覆盖 {{ vc.samplingParams.value.populationAmount > 0 ? `${vc.coverage.value.amountPct.toFixed(0)}%` : '—' }}
      </el-tag>
      <span class="summary-muted">样本发生额 {{ fmt(vc.coverage.value.sampleAbsAmount) }}</span>
      <span v-if="!vc.balanceOk.value" class="summary-muted" title="抽样明细常为单边，差额仅供参考">
        （借贷差 {{ fmt(vc.balanceDiff.value) }}，不必平衡）
      </span>
    </div>

    <div class="source-filter-bar" data-testid="g9-source-filter">
      <span class="filter-label">来源分池：</span>
      <el-radio-group
        :model-value="vc.sourceFilter.value"
        size="small"
        @update:model-value="(v: string | number | boolean | undefined) => { vc.sourceFilter.value = String(v) as G9VoucherSourceFilter }"
      >
        <el-radio-button value="all">全部 {{ vc.sourceCounts.value.all }}</el-radio-button>
        <el-radio-button value="抽凭">抽凭 {{ vc.sourceCounts.value['抽凭'] }}</el-radio-button>
        <el-radio-button value="截止">截止 {{ vc.sourceCounts.value['截止'] }}</el-radio-button>
        <el-radio-button value="手工">手工 {{ vc.sourceCounts.value['手工'] }}</el-radio-button>
      </el-radio-group>
    </div>

    <el-alert
      v-if="vc.lowCoverage.value"
      type="warning"
      :closable="false"
      show-icon
      class="coverage-warning"
      title="覆盖率偏低：当前样本量低于目标，或金额覆盖率不足 60%（需填写总体金额）。建议增大样本或补充特定项目。"
    />

    <div v-if="vc.manyRows.value" class="virtual-toolbar">
      <el-alert type="info" :closable="false" class="virtual-hint">
        行数较多（{{ vc.filteredRows.value.length }} 行）·
        {{ vc.browseMode.value ? '虚拟滚动速览（只读）' : '表格编辑' }}模式
      </el-alert>
      <el-button size="small" @click="vc.toggleBrowseMode()">
        {{ vc.browseMode.value ? '切换表格编辑' : '切换虚拟速览' }}
      </el-button>
    </div>

    <div class="anomaly-trace-summary" data-testid="g9-anomaly-trace">
      <div class="trace-line">
        <span class="trace-label">异常汇总（→ 错报汇总）：</span>
        <el-tag :type="vc.abnormalCount.value > 0 ? 'danger' : 'success'" size="small">
          异常 {{ vc.abnormalCount.value }} 笔（金额 {{ vc.quantitativeAbnormalCount.value }}）
        </el-tag>
        <GtIndexChip value="wp:A13" context="异常汇总至错报汇总底稿 A13" :context-project-id="projectId" />
        <el-button
          v-if="!isReadonly && projectId && vc.quantitativeAbnormalCount.value > 0"
          link
          type="danger"
          size="small"
          :loading="vc.a13Pushing.value"
          data-testid="g9-push-a13-inline"
          @click="onPushA13"
        >
          一键推送金额异常
        </el-button>
        <span class="trace-hint">金额类=公允价值/减值不通过；定性含授权、分类与截止跨期</span>
      </div>
      <div class="trace-line">
        <span class="trace-label">截止跨期疑点：</span>
        <el-tag :type="vc.cutoffAbnormalCount.value > 0 ? 'warning' : 'info'" size="small">
          跨期 {{ vc.cutoffAbnormalCount.value }} 笔
        </el-tag>
      </div>
    </div>

    <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" class="segment-tabs" />

    <el-table-v2
      v-if="vc.useVirtualScroll.value"
      :columns="virtualColumns"
      :data="vc.filteredRows.value"
      :width="tableWidth"
      :height="440"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
      data-testid="g9-voucher-virtual-table"
    />

    <el-table
      v-else
      :data="vc.filteredRows.value"
      border stripe size="small"
      style="font-size:13px;margin-top:8px"
      highlight-current-row
      :row-class-name="rowClassName"
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="日期" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { voucherDate: v })" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { businessContent: v })" />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { counterAccount: v })" />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产名称" min-width="140">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.detailRowId || ''"
              size="small"
              filterable
              clearable
              placeholder="挂接 G9-2"
              style="width:100%"
              @change="(id: string) => onLinkDetail(row.rowId, id)"
            >
              <el-option
                v-for="d in vc.detailOptions.value"
                :key="d.rowId"
                :label="d.label"
                :value="d.rowId"
              />
            </el-select>
            <span v-else>{{ row.assetName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { debitAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="64" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.source === '截止' ? 'warning' : (row.source === '抽凭' ? '' : 'info')">
              {{ row.source || '手工' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="56" align="center">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" size="small" link @click="uploadOcr(row)">OCR</el-button>
            <span v-else>{{ row.attachmentRef || '—' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="支持性文件" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportDoc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { supportDoc: v })" />
            <span v-else>{{ row.supportDoc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原始" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.checkOriginal)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { checkOriginal: parseCheckSelect(v) })">
              <el-option v-for="o in G9_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG9CheckState(row.checkOriginal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="授权" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.checkAuthorized)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { checkAuthorized: parseCheckSelect(v) })">
              <el-option v-for="o in G9_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG9CheckState(row.checkAuthorized) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账务" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.checkAccounting)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { checkAccounting: parseCheckSelect(v) })">
              <el-option v-for="o in G9_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG9CheckState(row.checkAccounting) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.checkClassification)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { checkClassification: parseCheckSelect(v) })">
              <el-option v-for="o in G9_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG9CheckState(row.checkClassification) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值" width="96" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.checkFairValue)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { checkFairValue: parseCheckSelect(v) })">
              <el-option v-for="o in G9_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG9CheckState(row.checkFairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.checkImpairment)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { checkImpairment: parseCheckSelect(v) })">
              <el-option v-for="o in G9_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG9CheckState(row.checkImpairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="联动提示" min-width="200">
          <template #default="{ row }">
            <div class="hint-cell">
              <el-tag
                v-for="h in vc.hintsForRow(row)"
                :key="h.code + h.text"
                size="small"
                :type="h.level === 'danger' ? 'danger' : (h.level === 'warning' ? 'warning' : 'info')"
                class="hint-tag"
              >
                {{ h.text }}
              </el-tag>
              <el-button
                v-if="!isReadonly && vc.hintsForRow(row).some((h) => h.suggestCheckFairValueFail || h.suggestCheckImpairmentFail || h.suggestCheckClassificationFail)"
                link
                type="warning"
                size="small"
                @click="vc.applyLinkHints(row.rowId)"
              >
                应用建议
              </el-button>
              <span v-if="!vc.hintsForRow(row).length" class="hint-empty">—</span>
            </div>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="索引" width="88">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :label="row.indexRef" :prevent-navigate="true" :validate="false" />
            <el-input v-else-if="!isReadonly" :model-value="row.indexRef" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { indexRef: v })" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="64" align="center">
          <template #default="{ row }">
            <span :class="{ abnormal: row.isAbnormal }">{{ row.isAbnormal ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="强制异常" width="80" align="center">
          <template #default="{ row }">
            <el-checkbox
              v-if="!isReadonly"
              :model-value="row.forceAbnormal"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { forceAbnormal: !!v })"
            />
            <span v-else>{{ row.forceAbnormal ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="64" align="center">
          <template #default="{ row }">{{ formatG9AbnormalType(row.abnormalType) }}</template>
        </el-table-column>
        <el-table-column label="风险" width="88">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { riskLevel: v })">
              <el-option v-for="o in vc.riskLevelOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.riskLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.abnormalDesc" size="small" type="textarea" :rows="1"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { abnormalDesc: v })" />
            <span v-else>{{ row.abnormalDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处理建议" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.suggestion" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { suggestion: v })" />
            <span v-else>{{ row.suggestion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <el-card v-if="vc.activeTab.value === 'conclusion'" shadow="never" class="conclusion-card" data-testid="g9-voucher-conclusion">
      <template #header>
        <div class="conclusion-head">
          <span>凭证检查结论</span>
          <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly"
            data-testid="g9-voucher-ai-btn" @click="vc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="vc.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="汇总抽样范围、核对结果、异常处理及对认定的影响。"
        @update:model-value="vc.updateConclusion" />
    </el-card>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="voucher-note"
      conclusion-ai-section="voucher-conclusion"
      note-placeholder="填写审计说明：抽样方法、样本量、六项核对执行情况及异常处理。"
      note-hint="覆盖抽样方法、核对结果与异常事项；可与抽凭后 AI 复核意见合并。"
      conclusion-placeholder="填写总体结论：A、未见异常。B、除上述重大不符事项应予调整外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。"
      conclusion-title="总体审计结论"
      :related-context="{
        行数: vc.rows.value.length,
        未测: vc.untestedCount.value,
        异常: vc.abnormalCount.value,
        金额异常: vc.quantitativeAbnormalCount.value,
        完成度: `${vc.completion.value.pct}%`,
        笔数覆盖: `${vc.coverage.value.countPct.toFixed(0)}%`,
        抽样方法: vc.samplingParams.value.samplingMethod,
        样本量: `${vc.samplingParams.value.currentSampleSize}/${vc.samplingParams.value.targetSampleSize}`,
      }"
    />

    <el-dialog
      v-model="showSampling"
      title="G9-6 抽凭引擎（科目1504）"
      width="960px"
      destroy-on-close
      append-to-body
    >
      <GtVoucherSamplingEngine
        v-if="showSampling && wpId && projectId"
        :account-code="G9_ACCOUNT_CODE"
        phase="final"
        default-method="random"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="engineYear"
        @filled="onSampleFilled"
      />
    </el-dialog>

    <PostFillAiReviewDialog
      v-model="showReview"
      :wp-id="wpId"
      :rows="reviewRows"
      :section="reviewSection"
      :ai-available="aiAvailable"
      @applied="onReviewApplied"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, h, ref, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import type { Column } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import PostFillAiReviewDialog, { type PostFillReviewRow } from '../../voucher-sampling/PostFillAiReviewDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import {
  useG9VoucherCheck,
  formatG9CheckState,
  formatG9AbnormalType,
  G9_CHECK_STATE_OPTIONS,
  G9_SAMPLING_METHOD_OPTIONS,
  G9A_VOUCHER_PROGRAM_NOS,
  type G9VoucherRow,
  type G9CheckState,
  type G9VoucherSourceFilter,
} from '../../composables/useG9VoucherCheck'
import {
  mapG9OcrToVoucherFields,
  computeG9OcrMergePatch,
  renderG9OcrPreview,
  extractG9OcrPayload,
  isG9AllowedOcrAttachment,
} from '../../composables/g9VoucherCross'
import { G9_ACCOUNT_CODE } from '../../composables/g9Constants'
import { jumpToG9Sheet } from '../../composables/g9SheetLabels'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import { useG9AiGenerate } from '../../composables/useG9AiGenerate'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../../composables/gCycleCutoffFill'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  year?: number
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]

const showSampling = ref(false)
const showReview = ref(false)
const reviewRows = ref<PostFillReviewRow[]>([])
const reviewSection = ref<'voucher-review' | 'cutoff-review'>('voucher-review')
const engineYear = computed(() => props.year ?? (new Date().getFullYear() - 1))
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable } = useG9AiGenerate(wpIdRef)

const vc = useG9VoucherCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  year: computed(() => props.year),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const tableWidth = 1100

function checkSelectValue(v: G9CheckState): string {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return 'null'
}

function parseCheckSelect(v: string): G9CheckState {
  if (v === 'true') return true
  if (v === 'false') return false
  return null
}

const virtualColumns = computed<Column<any>[]>(() => {
  if (vc.activeTab.value === 'basic') {
    return [
      { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
      { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
      { key: 'businessContent', title: '业务内容', dataKey: 'businessContent', width: 200 },
      { key: 'debitAmount', title: '借方', dataKey: 'debitAmount', width: 100, align: 'right',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', fmt(rowData.debitAmount)) },
      { key: 'creditAmount', title: '贷方', dataKey: 'creditAmount', width: 100, align: 'right',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', fmt(rowData.creditAmount)) },
      { key: 'source', title: '来源', dataKey: 'source', width: 72 },
    ]
  }
  if (vc.activeTab.value === 'check') {
    return [
      { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
      { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
      { key: 'supportDoc', title: '支持性文件', dataKey: 'supportDoc', width: 160 },
      { key: 'checkFairValue', title: '公允价值', dataKey: 'checkFairValue', width: 80, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', formatG9CheckState(rowData.checkFairValue)) },
      { key: 'checkImpairment', title: '减值', dataKey: 'checkImpairment', width: 72, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', formatG9CheckState(rowData.checkImpairment)) },
      { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    ]
  }
  return [
    { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
    { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
    { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
      cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    { key: 'abnormalType', title: '类型', dataKey: 'abnormalType', width: 72,
      cellRenderer: ({ rowData }: { rowData: G9VoucherRow }) => h('span', formatG9AbnormalType(rowData.abnormalType)) },
    { key: 'riskLevel', title: '风险', dataKey: 'riskLevel', width: 80 },
    { key: 'abnormalDesc', title: '异常说明', dataKey: 'abnormalDesc', width: 200 },
  ]
})

function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onRowChange(row: G9VoucherRow | undefined) {
  if (!row) return
  const idx = vc.rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) vc.setActiveRowIndex(idx)
}

function rowClassName({ row }: { row: G9VoucherRow }) {
  return row.isAbnormal ? 'abnormal-row' : ''
}

function onSampleFilled(payload: {
  samples?: Array<{
    summary?: string
    amount?: number
    debitAmount?: number | string
    creditAmount?: number | string
    voucherDate?: string
    voucherNo?: string
    counterpartAccount?: string
    abnormal?: boolean
    isHighValue?: boolean
    selectionReason?: string
  }>
  method?: string
  fillMode?: 'append' | 'merge' | 'replace'
}) {
  const samples = payload.samples ?? []
  if (!samples.length) return
  const n = vc.fillFromSampling(
    samples.map((s) => ({
      summary: s.summary,
      debitAmount: s.debitAmount ?? s.amount,
      creditAmount: s.creditAmount,
      voucherDate: s.voucherDate,
      voucherNo: s.voucherNo,
      counterpartAccount: s.counterpartAccount,
      abnormal: s.abnormal,
      isHighValue: s.isHighValue,
      selectionReason: s.selectionReason,
    })),
    payload.fillMode ?? 'append',
    payload.method,
  )
  showSampling.value = false
  if (n > 0) {
    ElMessage.success(`已回填 ${n} 笔抽凭样本`)
    triggerPostFillReview(samples)
  } else {
    ElMessage.info('未回填任何样本（可能已存在相同凭证号）')
  }
}

function triggerPostFillReview(samples: Array<{
  voucherNo?: string
  voucherDate?: string
  summary?: string
  debitAmount?: number | string
  creditAmount?: number | string
  counterpartAccount?: string
  abnormal?: boolean
  amount?: number
}>) {
  reviewSection.value = 'voucher-review'
  reviewRows.value = samples.map((s) => ({
    voucherNo: s.voucherNo,
    voucherDate: s.voucherDate,
    summary: s.summary,
    debitAmount: s.debitAmount ?? s.amount,
    creditAmount: s.creditAmount,
    counterpartAccount: s.counterpartAccount,
    abnormal: s.abnormal,
  }))
  showReview.value = true
}

function onReviewApplied(text: string) {
  if (props.isReadonly) return
  const merged = auditNote.value
    ? `${auditNote.value}\n\n【AI 复核意见】\n${text}`
    : `【AI 复核意见】\n${text}`
  auditNote.value = merged
  const conc = vc.conclusion.value
    ? `${vc.conclusion.value}\n\n【AI 复核意见】\n${text}`
    : text
  vc.updateConclusion(conc)
  ElMessage.success('AI 复核意见已填入审计说明与检查结论')
}

async function onMarkProcedure() {
  const res = await vc.markProcedureComplete()
  if (!res.ok) {
    ElMessage.warning(res.message)
    return
  }
  ElMessage.success(res.message)
  dispatchProcedureFocus({
    programNos: [...G9A_VOUCHER_PROGRAM_NOS],
    sheetCode: 'G9A',
    sheetName: '其他非流动金融资产实质性程序表G9A',
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G9A',
    message: `凭证检查相关程序（${[...G9A_VOUCHER_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G9A 程序表查看并定位对应步骤？`,
    confirmText: '前往 G9A',
  })
  if (go) {
    jumpToG9Sheet('G9A', jumpToSection)
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G9A_VOUCHER_PROGRAM_NOS],
        sheetCode: 'G9A',
        sheetName: '其他非流动金融资产实质性程序表G9A',
      })
    }, 400)
  }
}

async function onPushA13() {
  await vc.pushQuantitativeToA13()
}

function onLinkDetail(rowId: string, detailRowId: string) {
  if (!detailRowId) {
    vc.updateRow(rowId, { detailRowId: '', assetName: '' })
    return
  }
  const d = vc.detailOptions.value.find((x) => x.rowId === detailRowId)
  vc.linkDetail(rowId, detailRowId, d?.assetName ?? '')
}

function exportMemo() {
  const md = vc.buildMemo()
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `G9-6-抽样备忘-${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)
  if (!props.isReadonly) {
    const merged = auditNote.value
      ? `${auditNote.value}\n\n---\n${md}`
      : md
    auditNote.value = merged
  }
  ElMessage.success('抽样备忘已导出')
}

async function uploadOcr(row: G9VoucherRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    if (!isG9AllowedOcrAttachment(file)) {
      ElMessage.warning('仅支持图片或 PDF 附件')
      return
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      let res
      try {
        res = await http.post(`/api/workpapers/${props.wpId}/g9/contract-ocr`, formData)
      } catch {
        res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      }
      const { fields, confidence } = extractG9OcrPayload(res.data)
      const { patch, lowConfidence } = mapG9OcrToVoucherFields(fields, confidence)
      const merged = computeG9OcrMergePatch(row, patch)
      if (!Object.keys(merged).length) {
        ElMessage.warning('OCR 未识别到可填入的空字段')
        return
      }
      await ElMessageBox.confirm(renderG9OcrPreview(merged, lowConfidence, confidence), 'OCR 确认（仅填空）', {
        type: 'info',
        dangerouslyUseHTMLString: true,
        confirmButtonText: '填入',
        cancelButtonText: '取消',
      })
      vc.updateRow(row.rowId, { ...merged, attachmentRef: file.name } as Partial<G9VoucherRow>)
      if (lowConfidence.length) ElMessage.warning('部分字段置信度偏低，请人工复核')
      else ElMessage.success('OCR 字段已填入空位')
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.warning('OCR 识别失败')
    }
  }
  input.click()
}

function fmt(v: number) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const NOTE_KEY = 'G9-voucher-audit-note'
const CONCLUSION_KEY = 'G9-voucher-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const _voucherConcl = props.allResponses.get(CONCLUSION_KEY)
const auditConclusion = ref(String(_voucherConcl?.conclusion ?? _voucherConcl?.remark ?? ''))
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: v, remark: null })
})

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  vc.applyCutoffResults(detail.samples, detail.fillMode)
  reviewSection.value = 'cutoff-review'
  reviewRows.value = detail.samples.map((s) => ({
    voucherNo: s.voucherNo,
    voucherDate: s.voucherDate,
    summary: s.summary,
    debitAmount: s.debitAmount,
    creditAmount: s.creditAmount,
    counterpartAccount: s.counterpartAccount,
    abnormal: s.cutoffStatus === '可能跨期',
  }))
  showReview.value = true
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g9, onCutoffFilled as EventListener)
})
</script>

<style scoped>
.g9-voucher { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.audit-objective { margin-bottom: 8px; }
.sampling-params-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 10px;
  background: #fafbfc;
}
.card-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; }
.params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px 12px;
}
.param-item { display: flex; flex-direction: column; gap: 4px; }
.param-item-wide { grid-column: 1 / -1; }
.param-label { font-size: 12px; color: #909399; }
.sampling-progress, .completion-row {
  display: flex;
  align-items: center;
  margin-top: 10px;
  font-size: 12px;
}
.section-head { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.summary-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
  padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px;
}
.summary-sep { color: #c0c4cc; }
.summary-muted { color: #909399; font-size: 12px; }
.source-filter-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.filter-label { font-size: 12px; color: #606266; }
.coverage-warning { margin-bottom: 8px; }
.virtual-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.virtual-hint { flex: 1; }
.anomaly-trace-summary {
  padding: 8px 12px; background: #fdf6ec; border-radius: 4px; margin-bottom: 8px; font-size: 12px;
}
.trace-line { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 2px 0; }
.trace-label { color: #606266; }
.trace-hint { color: #909399; }
.hint-cell { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.hint-tag { max-width: 100%; white-space: normal; height: auto; }
.hint-empty { color: #c0c4cc; }
.segment-tabs { margin-bottom: 8px; }
.virtual-table { margin-top: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.abnormal { color: #f56c6c; font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
</style>
