<template>
  <div class="g8-voucher" data-testid="g8-voucher-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表抽取其他权益工具投资（科目1503）相关记账凭证，逐笔核对原始单据完整性、授权、账务处理及公允价值/OCI 计量正确性。</p>
        <p>2. 核对项为三态：未测 / 通过 / 不通过；任一「不通过」自动标异常，「未测」不计入异常。截止跨期可强制异常，核对通过后可取消强制。</p>
        <p>3. 先填写抽样参数 → 抽凭引擎回填 → AI 复核 → 挂接 G8-2 被投资单位查看 G8-4/G8-5 联动提示 → 逐笔核对。</p>
        <p>4. 可用来源筛选分池（抽凭 / 截止 / 手工）；异常分「金额 / 定性 / 混合」；金额类可一键推送 A13，编制完成后回填 G8A 程序 6/7/12。</p>
        <p>5. 行级 OCR：上传图片/PDF → 映射日期/凭证号/摘要/对方科目/借贷金额/被投资单位；仅填入空白字段，低置信度需人工复核。</p>
        <p>6. 错报推断：填总体金额与可容忍错报 → 结论区录入金额类「实际错报」→ 查看 UML / 总体是否可接受；可写入结论或推送 A13。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：通过凭证检查核实其他权益工具投资（科目1503）交易的真实性、完整性与计量准确性，验证公允价值变动计入其他综合收益（OCI）的会计处理正确。"
    />

    <!-- 抽样参数（对标 D3） -->
    <div class="sampling-params-card" data-testid="g8-vc-params">
      <h4 class="card-title">抽样参数</h4>
      <div class="params-grid">
        <div class="param-item">
          <span class="param-label">测试总体</span>
          <el-input
            :model-value="vc.samplingParams.value.testPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="如：科目1503本期发生额共XX笔、金额XX"
            @change="(val: string) => vc.updateSamplingParams('testPopulation', val)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">特定样本</span>
          <el-input
            :model-value="vc.samplingParams.value.specificSamples"
            size="small"
            :disabled="isReadonly"
            placeholder="大额/异常/关联方等必选样本说明"
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
              v-for="o in G8_SAMPLING_METHOD_OPTIONS"
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
        <div class="param-item">
          <span class="param-label">可容忍错报</span>
          <el-input-number
            :model-value="vc.samplingParams.value.tolerableMisstatement"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            data-testid="g8-tolerable"
            @change="(val: number | undefined) => vc.updateSamplingParams('tolerableMisstatement', val ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">预期错报</span>
          <el-input-number
            :model-value="vc.samplingParams.value.expectedMisstatement"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="(val: number | undefined) => vc.updateSamplingParams('expectedMisstatement', val ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">置信度</span>
          <el-input-number
            :model-value="vc.samplingParams.value.confidenceLevel"
            size="small"
            :min="0.8"
            :max="0.99"
            :step="0.01"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="(val: number | undefined) => vc.updateSamplingParams('confidenceLevel', val ?? 0.95)"
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

    <div class="section-head">
      <h3 class="sheet-title">G8-6 凭证检查表</h3>
      <div class="head-actions">
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-6" @imported="onImported" />
        <el-button size="small" type="warning" :disabled="isReadonly" data-testid="g8-open-sampling" @click="openSampling">
          ⚡ 抽凭
        </el-button>
        <el-button size="small" :disabled="isReadonly" data-testid="g8-export-memo" @click="exportMemo">
          📄 抽样备忘
        </el-button>
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="danger"
          plain
          :loading="vc.a13Pushing.value"
          :disabled="vc.quantitativeAbnormalCount.value <= 0"
          data-testid="g8-push-a13"
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
          data-testid="g8-mark-g8a"
          @click="onMarkProcedure"
        >
          {{ vc.procedureMarked.value ? '已回填 G8A（可重写）' : '回填 G8A 凭证程序' }}
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
      <span class="chip-wrap"><GtIndexChip value="wp:G8-6" :context-project-id="projectId" /></span>
    </div>

    <!-- 来源分池 -->
    <div class="source-filter-bar" data-testid="g8-source-filter">
      <span class="filter-label">来源分池：</span>
      <el-radio-group
        :model-value="vc.sourceFilter.value"
        size="small"
        @update:model-value="(v: string | number | boolean | undefined) => { vc.sourceFilter.value = String(v) as G8VoucherSourceFilter }"
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

    <!-- 异常汇总 → A13 -->
    <div class="anomaly-trace-summary" data-testid="g8-anomaly-trace">
      <div class="trace-line">
        <span class="trace-label">异常汇总（→ 错报汇总）：</span>
        <el-tag :type="vc.abnormalCount.value > 0 ? 'danger' : 'success'" size="small">
          异常 {{ vc.abnormalCount.value }} 笔
          （金额 {{ vc.quantitativeAbnormalCount.value }} / 定性含跨期）
        </el-tag>
        <GtIndexChip value="wp:A13" context="异常汇总至错报汇总底稿 A13" :context-project-id="projectId" />
        <el-button
          v-if="!isReadonly && projectId && vc.quantitativeAbnormalCount.value > 0"
          link
          type="danger"
          size="small"
          :loading="vc.a13Pushing.value"
          data-testid="g8-push-a13-inline"
          @click="onPushA13"
        >
          一键推送金额异常
        </el-button>
        <span class="trace-hint">金额类异常可创建未更正错报并通知 A13</span>
      </div>
      <div class="trace-line">
        <span class="trace-label">截止跨期疑点：</span>
        <el-tag :type="vc.cutoffAbnormalCount.value > 0 ? 'warning' : 'info'" size="small">
          跨期 {{ vc.cutoffAbnormalCount.value }} 笔
        </el-tag>
        <span class="trace-hint">来源=截止且已标异常的样本</span>
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
      data-testid="g8-voucher-virtual-table"
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
        <el-table-column label="被投资单位" min-width="140">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.detailRowId || ''"
              size="small"
              filterable
              clearable
              placeholder="挂接 G8-2"
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
            <span v-else>{{ row.investeeName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.debitAmount" size="small" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { debitAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.creditAmount" size="small" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.rowId, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="64" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.source" size="small" effect="plain">{{ row.source }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="56" align="center">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" size="small" link @click="uploadOcr(row)">OCR</el-button>
            <span v-else>{{ row.attachment || '—' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="支持性文件" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDocDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { supportingDocDesc: v })" />
            <span v-else>{{ row.supportingDocDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完整" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.check1OriginalComplete)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { check1OriginalComplete: parseCheckSelect(v) })">
              <el-option v-for="o in checkSelectOptions" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG8CheckState(row.check1OriginalComplete) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="授权" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.check2Authorization)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { check2Authorization: parseCheckSelect(v) })">
              <el-option v-for="o in checkSelectOptions" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG8CheckState(row.check2Authorization) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账务" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.check3Accounting)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { check3Accounting: parseCheckSelect(v) })">
              <el-option v-for="o in checkSelectOptions" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG8CheckState(row.check3Accounting) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.check4FairValueCorrect)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { check4FairValueCorrect: parseCheckSelect(v) })">
              <el-option v-for="o in checkSelectOptions" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG8CheckState(row.check4FairValueCorrect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="checkSelectValue(row.check5OCICorrect)" size="small"
              @change="(v: string) => vc.updateRow(row.rowId, { check5OCICorrect: parseCheckSelect(v) })">
              <el-option v-for="o in checkSelectOptions" :key="String(o.value)" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG8CheckState(row.check5OCICorrect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="联动提示" min-width="200">
          <template #default="{ row }">
            <div class="hint-cell">
              <el-tag
                v-for="h in vc.hintsForRow(row)"
                :key="h.code"
                size="small"
                :type="hintTagType(h.level)"
                effect="plain"
                class="hint-tag"
              >{{ h.text }}</el-tag>
              <el-button
                v-if="!isReadonly && vc.hintsForRow(row).some((h) => h.suggestCheck4Fail || h.suggestCheck5Fail)"
                size="small"
                link
                type="warning"
                @click="vc.applyLinkHints(row.rowId)"
              >应用建议</el-button>
              <span v-if="!vc.hintsForRow(row).length" class="hint-empty">—</span>
            </div>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="凭证号" prop="voucherNo" width="100" />
        <el-table-column label="被投资单位" min-width="120" prop="investeeName" />
        <el-table-column label="索引" width="88">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexNo" :label="row.indexNo" :prevent-navigate="true" :validate="false" />
            <el-input v-else-if="!isReadonly" :model-value="row.indexNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { indexNo: v })" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="异常" width="64" align="center">
          <template #default="{ row }">
            <span :class="{ abnormal: row.isAbnormal }">{{ row.isAbnormal ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="72" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.abnormalType && row.abnormalType !== 'none'"
              size="small"
              :type="row.abnormalType === 'quantitative' || row.abnormalType === 'mixed' ? 'danger' : 'warning'"
              effect="plain"
            >{{ formatG8AbnormalType(row.abnormalType) }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="强制异常" width="88" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.forceAbnormal"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { forceAbnormal: !!v })" />
            <span v-else>{{ row.forceAbnormal ? '是' : '否' }}</span>
          </template>
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
        <el-table-column label="实际错报" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && (row.abnormalType === 'quantitative' || row.abnormalType === 'mixed')"
              :model-value="row.actualMisstatement || 0"
              size="small"
              :min="0"
              :controls="false"
              style="width: 100%"
              @change="(val: number | undefined) => vc.updateRow(row.rowId, { actualMisstatement: val ?? 0 })"
            />
            <span v-else>{{ (row.actualMisstatement || 0) > 0 ? fmt(row.actualMisstatement || 0) : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="高值" width="56" align="center">
          <template #default="{ row }">
            <el-checkbox
              v-if="!isReadonly"
              :model-value="!!row.isHighValue"
              @update:model-value="(v: boolean) => vc.updateRow(row.rowId, { isHighValue: !!v })"
            />
            <span v-else>{{ row.isHighValue ? '是' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.abnormalDesc" size="small" type="textarea" :rows="1"
              @update:model-value="(v: string) => vc.updateRow(row.rowId, { abnormalDesc: v })" />
            <span v-else>{{ row.abnormalDesc }}</span>
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

    <el-card
      v-if="vc.activeTab.value === 'conclusion'"
      shadow="never"
      class="projection-card"
      data-testid="g8-projection"
    >
      <template #header>
        <div class="conclusion-head">
          <span>错报推断与总体结论</span>
          <div class="proj-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              plain
              data-testid="g8-prefill-misstatement"
              @click="onPrefillMisstatement"
            >预填建议错报</el-button>
            <el-button
              v-if="!isReadonly && vc.projection.value.canProject"
              size="small"
              type="primary"
              plain
              @click="vc.appendProjectionToConclusion()"
            >写入结论</el-button>
          </div>
        </div>
      </template>
      <el-alert
        v-if="!vc.projection.value.canProject"
        type="info"
        :closable="false"
        show-icon
        :title="vc.projection.value.reason"
      />
      <template v-else>
        <div class="proj-metrics">
          <el-tag size="small" type="info">方法 {{ vc.projection.value.method }}</el-tag>
          <el-tag size="small">金额样本 {{ vc.projection.value.sampleCount }}</el-tag>
          <el-tag size="small" :type="vc.projection.value.missingMisstatementCount ? 'warning' : 'success'">
            已填错报 {{ vc.projection.value.withMisstatementCount }}
          </el-tag>
          <span class="proj-metric">推断 {{ fmt(Number(vc.projection.value.result?.projected || 0)) }}</span>
          <span class="proj-metric">UML {{ fmt(Number(vc.projection.value.uml || 0)) }}</span>
          <span class="proj-metric">可容忍 {{ fmt(Number(vc.projection.value.tolerableMisstatement || 0)) }}</span>
        </div>
        <el-alert
          class="proj-conclusion"
          :type="vc.projection.value.conclusion?.accepted ? 'success' : 'error'"
          :closable="false"
          show-icon
          :title="vc.projection.value.conclusion?.message || ''"
        />
        <p v-if="vc.projection.value.reason" class="proj-hint">{{ vc.projection.value.reason }}</p>
        <p class="proj-hint">高值层 {{ vc.projection.value.result?.knownHighValue }} · 基本准备 {{ vc.projection.value.result?.basicPrecision }} · 增量准备 {{ vc.projection.value.result?.incrementalAllowance }}</p>
      </template>
    </el-card>

    <el-card v-if="vc.activeTab.value === 'conclusion'" shadow="never" class="conclusion-card" data-testid="g8-voucher-conclusion">
      <template #header>
        <div class="conclusion-head">
          <span>凭证检查结论</span>
          <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly"
            data-testid="g8-voucher-ai-btn" @click="vc.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="vc.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="vc.updateConclusion" />
    </el-card>

    <G8AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="voucher-note"
      conclusion-ai-section="voucher-conclusion"
      note-placeholder="填写审计说明：凭证抽样方法、样本量、逐笔核对结果及发现的异常事项。"
      note-hint="覆盖抽样方法、核对结果与异常事项。"
      conclusion-placeholder="填写审计结论：A、凭证检查未见异常，交易真实性与计量可确认。B、除已说明异常外其余未见异常。C、存在重大异常或范围受限，不可确认。"
      conclusion-hint="可先选 A/B/C 口径，再按需补充说明。"
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

    <!-- 抽凭引擎弹窗（对标 D3） -->
    <el-dialog
      v-model="showSampling"
      title="G8-6 抽凭引擎（科目1503）"
      width="960px"
      destroy-on-close
      append-to-body
    >
      <GtVoucherSamplingEngine
        v-if="showSampling && wpId && projectId"
        :account-code="G8_ACCOUNT_CODE"
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
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, ref, watch, toRef, h, onMounted, onBeforeUnmount, inject } from 'vue'
import type { Column } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import PostFillAiReviewDialog, { type PostFillReviewRow } from '../../voucher-sampling/PostFillAiReviewDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import G8AuditTextCards from '../G8AuditTextCards.vue'
import { useG8VoucherCheck, type G8VoucherRow, type G8CheckState, formatG8CheckState,
  G8_SAMPLING_METHOD_OPTIONS,
  mapG8OcrToVoucherFields,
  computeG8OcrMergePatch,
  renderG8OcrPreview,
  extractG8OcrPayload,
  isG8AllowedOcrAttachment,
  G8_OCR_CONFIDENCE_THRESHOLD,
} from '../../composables/useG8VoucherCheck'
import { formatG8AbnormalType, type G8VoucherSourceFilter } from '../../composables/g8VoucherCross'
import { useG8AiGenerate } from '../../composables/useG8AiGenerate'
import { G8_ACCOUNT_CODE } from '../../composables/g8Constants'
import {
  G8A_VOUCHER_PROGRAM_NOS,
  jumpToG8Sheet,
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { GCycleCutoffFilledDetail } from '../../composables/gCycleCutoffFill'
import { GCYCLE_CUTOFF_EVENT } from '../../composables/gCycleCutoffFill'
import type { SampledVoucher, SamplingMethod, Phase } from '../../composables/useSamplingAlgorithms'
import type { FillMode } from '../../composables/useCutoffAutoSampling'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  year?: number
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]

/** el-select 不能用 null 作 value，用哨兵字符串 */
const CHECK_NULL = '__null__'
const checkSelectOptions = [
  { value: CHECK_NULL, label: '未测' },
  { value: 'true', label: '通过' },
  { value: 'false', label: '不通过' },
]

function checkSelectValue(v: G8CheckState): string {
  if (v === true) return 'true'
  if (v === false) return 'false'
  return CHECK_NULL
}

function parseCheckSelect(v: string): G8CheckState {
  if (v === 'true') return true
  if (v === 'false') return false
  return null
}

const vc = useG8VoucherCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  year: toRef(props, 'year'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

async function onPushA13() {
  await vc.pushQuantitativeToA13()
}

async function onMarkProcedure() {
  const n = await vc.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G8A_VOUCHER_PROGRAM_NOS],
    sheetCode: 'G8A',
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G8A',
    message: '凭证检查相关程序（6/7/12）已标记完成。是否前往 G8A 程序表查看并定位对应步骤？',
    confirmText: '前往 G8A',
  })
  if (go) {
    jumpToG8Sheet('G8A', jumpToSection)
    setTimeout(() => {
      dispatchProcedureFocus({ programNos: [...G8A_VOUCHER_PROGRAM_NOS], sheetCode: 'G8A' })
    }, 400)
  }
}

function onPrefillMisstatement() {
  const n = vc.prefillSuggestedMisstatements()
  if (n > 0) ElMessage.success(`已为 ${n} 笔金额异常预填建议错报`)
  else ElMessage.info('无需预填（无空白金额异常或建议值为 0）')
}

const wpIdRef = toRef(props, 'wpId')
const { aiAvailable } = useG8AiGenerate(wpIdRef)

const AUDIT_NOTE_KEY = 'G8-6-audit-note'
const AUDIT_CONCLUSION_KEY = 'G8-6-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const _voucherConcl = props.allResponses.get(AUDIT_CONCLUSION_KEY)
const auditConclusion = ref(String(_voucherConcl?.conclusion ?? _voucherConcl?.remark ?? ''))
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: v, remark: null })
})

const tableWidth = 1000
const engineYear = computed(() => props.year ?? (new Date().getFullYear() - 1))

const showSampling = ref(false)
const showReview = ref(false)
const reviewRows = ref<PostFillReviewRow[]>([])
const reviewSection = ref<'voucher-review' | 'cutoff-review'>('voucher-review')

function openSampling() {
  if (props.isReadonly) return
  showSampling.value = true
}

function exportMemo() {
  const text = vc.buildMemo()
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `G8-6-抽样备忘-${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)
  if (!props.isReadonly) {
    const merged = auditNote.value
      ? `${auditNote.value}\n\n---\n${text}`
      : text
    auditNote.value = merged
    ElMessage.success('已下载抽样备忘，并追加至审计说明')
  } else {
    ElMessage.success('已下载抽样备忘')
  }
}

const virtualColumns = computed<Column<any>[]>(() => {
  if (vc.activeTab.value === 'basic') {
    return [
      { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
      { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
      { key: 'businessContent', title: '业务内容', dataKey: 'businessContent', width: 200 },
      { key: 'debitAmount', title: '借方', dataKey: 'debitAmount', width: 100, align: 'right',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', fmt(rowData.debitAmount)) },
      { key: 'creditAmount', title: '贷方', dataKey: 'creditAmount', width: 100, align: 'right',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', fmt(rowData.creditAmount)) },
    ]
  }
  if (vc.activeTab.value === 'check') {
    return [
      { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
      { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
      { key: 'supportingDocDesc', title: '支持性文件', dataKey: 'supportingDocDesc', width: 180 },
      { key: 'check5OCICorrect', title: 'OCI', dataKey: 'check5OCICorrect', width: 72, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', formatG8CheckState(rowData.check5OCICorrect)) },
      { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
        cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    ]
  }
  return [
    { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
    { key: 'voucherNo', title: '凭证号', dataKey: 'voucherNo', width: 100 },
    { key: 'indexNo', title: '索引', dataKey: 'indexNo', width: 88 },
    { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
      cellRenderer: ({ rowData }: { rowData: G8VoucherRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
    { key: 'riskLevel', title: '风险', dataKey: 'riskLevel', width: 80 },
    { key: 'abnormalDesc', title: '异常说明', dataKey: 'abnormalDesc', width: 200 },
  ]
})

function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onRowChange(row: G8VoucherRow | undefined) {
  if (!row) return
  const idx = vc.rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) vc.setActiveRowIndex(idx)
}

function rowClassName({ row }: { row: G8VoucherRow }) {
  return row.isAbnormal ? 'abnormal-row' : ''
}

function onLinkDetail(rowId: string, detailRowId: string) {
  if (!detailRowId) {
    vc.updateRow(rowId, { detailRowId: '', investeeName: '' })
    return
  }
  const d = vc.detailOptions.value.find((x) => x.rowId === detailRowId)
  vc.linkDetail(rowId, detailRowId, d?.investeeName ?? '')
}

function hintTagType(level: string): 'info' | 'warning' | 'danger' {
  if (level === 'danger') return 'danger'
  if (level === 'warning') return 'warning'
  return 'info'
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'G8',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => props.debouncedSave(itemId, { remark, conclusion: null }),
  isReadonly: computed(() => props.isReadonly === true),
})

function onSampleFilled(payload: {
  samples: SampledVoucher[]
  phase: Phase
  fillMode: FillMode
  method?: SamplingMethod
}) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  if (props.isReadonly) return
  const n = vc.fillFromSampling(payload.samples ?? [], payload.fillMode ?? 'append', payload.method)
  showSampling.value = false
  if (n > 0) {
    ElMessage.success(`已回填 ${n} 条抽凭样本（来源=抽凭）`)
    triggerPostFillReview(payload.samples ?? [])
  } else {
    ElMessage.info('未回填任何样本（可能已存在相同凭证号）')
  }
}

function triggerPostFillReview(samples: SampledVoucher[]) {
  reviewSection.value = 'voucher-review'
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

async function uploadOcr(row: G8VoucherRow) {
  if (props.isReadonly) return
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    if (!isG8AllowedOcrAttachment(file)) {
      ElMessage.error('仅支持图片或 PDF 格式的附件')
      return
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      let res
      try {
        res = await http.post(
          `/api/workpapers/${props.wpId}/g8/contract-ocr`,
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
        )
      } catch {
        res = await http.post(
          `/api/workpapers/${props.wpId}/d4/contract-ocr`,
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
        )
      }
      const { fields, confidence } = extractG8OcrPayload(res.data)
      if (!Object.keys(fields).length) {
        ElMessage.info('OCR 完成，未识别到可填充字段')
        return
      }
      const { patch, lowConfidence } = mapG8OcrToVoucherFields(fields, confidence)
      if (!Object.keys(patch).length) {
        ElMessage.info('OCR 完成，识别字段无法匹配当前行')
        return
      }
      const mergePatch = computeG8OcrMergePatch(row, patch)
      if (!Object.keys(mergePatch).length) {
        ElMessage.info('当前行相关字段均已填写，未覆盖已有内容')
        return
      }
      await ElMessageBox.confirm(
        renderG8OcrPreview(mergePatch, lowConfidence, confidence),
        'OCR 识别结果',
        {
          confirmButtonText: '填入',
          cancelButtonText: '取消',
          dangerouslyUseHTMLString: true,
          type: confidence < G8_OCR_CONFIDENCE_THRESHOLD ? 'warning' : 'info',
        },
      )
      const next: Partial<G8VoucherRow> = {
        ...mergePatch,
        attachment: file.name || row.attachment,
      }
      if (!row.supportingDocDesc?.trim() && !mergePatch.supportingDocDesc) {
        next.supportingDocDesc = `OCR:${file.name}`
      }
      vc.updateRow(row.rowId, next)
      ElMessage.success('已填入 OCR 识别结果（仅空白字段）')
    } catch (e: any) {
      if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
        ElMessage.warning('OCR 识别失败，请稍后重试')
      }
    }
  }
  input.click()
}

function fmt(v: number) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

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
    cutoffStatus: s.cutoffStatus,
  }))
  showReview.value = true
}

onMounted(() => {
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g8, onCutoffFilled as EventListener)
})
</script>

<style scoped>
.g8-voucher { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.sampling-params-card {
  margin-bottom: 12px; padding: 12px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px;
}
.card-title { margin: 0 0 10px; font-size: 14px; font-weight: 600; }
.params-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px 14px;
}
.param-item { display: flex; flex-direction: column; gap: 4px; }
.param-label { font-size: 12px; color: #606266; }
.sampling-progress { display: flex; align-items: center; margin-top: 12px; font-size: 12px; color: #606266; }
.completion-row { display: flex; align-items: center; margin-top: 8px; font-size: 12px; color: #606266; }
.section-head { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px;
}
.summary-sep { color: #c0c4cc; }
.summary-muted { color: #909399; font-size: 11px; }
.chip-wrap { display: inline-flex; align-items: center; margin-left: auto; }
.coverage-warning { margin-bottom: 8px; }
.virtual-toolbar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap;
}
.virtual-hint { flex: 1; margin: 0; }
.anomaly-trace-summary {
  margin-bottom: 10px; padding: 10px 12px; background: #fff; border: 1px dashed #dcdfe6; border-radius: 6px;
}
.source-filter-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  margin-bottom: 10px; font-size: 12px;
}
.filter-label { color: #606266; font-weight: 500; }
.hint-cell { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.hint-tag { max-width: 100%; white-space: normal; height: auto; line-height: 1.3; padding: 2px 6px; }
.hint-empty { color: #c0c4cc; }
.trace-line { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12px; }
.trace-line:last-child { margin-bottom: 0; }
.trace-label { color: #606266; font-weight: 500; }
.trace-hint { color: #909399; }
.segment-tabs { margin-bottom: 8px; }
.virtual-table { margin-top: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.abnormal { color: #f56c6c; font-weight: 600; }
.conclusion-card { margin-top: 12px; }
.projection-card { margin-top: 12px; }
.proj-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.proj-metrics {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px;
}
.proj-metric { font-size: 13px; color: #303133; }
.proj-conclusion { margin-bottom: 8px; }
.proj-hint { margin: 4px 0 0; font-size: 12px; color: #909399; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
</style>
