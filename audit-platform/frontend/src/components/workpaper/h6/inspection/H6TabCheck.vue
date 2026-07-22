<template>
  <div class="h6-tab-check">
    <!-- 引导步骤 -->
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认四项审计目标</div>
      <div class="guide-step"><span class="gs-no">2</span>勾选测试原因，明确测试内容</div>
      <div class="guide-step"><span class="gs-no">3</span>从 H6-2 带入/抽凭填样本明细</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例与结转，形成结论</div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <ol class="ao-list">
        <li><b>存在/发生：</b>记录的固定资产清理真实发生，且已记入恰当账户；</li>
        <li><b>完整性：</b>所有应记录的清理均已入账，相关披露完整；</li>
        <li><b>权利和义务：</b>被清理资产由被审计单位拥有或控制；</li>
        <li><b>计价和分摊：</b>原值/折旧/减值/清理损益金额恰当，结转至营业外或资产处置收益正确，披露计量恰当。</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        H6-4 为<strong>凭证级实质性测试</strong>：对抽查的清理样本核对凭证与账务处理。
        核心公式：净值=原值−累计折旧−减值；清理净损益=清理收入−清理费用−净值。
        检查比例=样本净值合计÷H6-2本期减少净值合计；比例偏低须扩样或说明。
        科目 <b>1606</b> 为过渡科目，样本期末余额原则上应结转清零。
      </p>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <GtIndexChip value="wp:H6-4" :context-project-id="props.projectId" />
      <el-tag size="small" type="info">样本 {{ rows.length }} 笔</el-tag>
      <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">
        异常 {{ summary.anomalyCount }}
      </el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ summary.coverageRate.toFixed(1) }}%
      </el-tag>

      <div class="toolbar-right">
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small" :loading="importExport.isExporting.value || importExport.isImporting.value">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-popover placement="bottom-end" :width="220" trigger="click">
          <template #reference>
            <el-button size="small" circle title="列显示偏好">⚙</el-button>
          </template>
          <div class="col-prefs-pop">
            <div v-for="col in toggleableCols" :key="col.key" class="col-pref-item">
              <el-checkbox
                :model-value="isColVisible(col.key)"
                :disabled="ALWAYS_VISIBLE_KEYS.includes(col.key)"
                size="small"
                @change="(v: boolean | string | number) => toggleCol(col.key, Boolean(v))"
              >
                {{ col.label }}
              </el-checkbox>
            </div>
            <el-button size="small" link type="primary" @click="resetColPrefs">恢复默认</el-button>
          </div>
        </el-popover>

        <el-segmented v-model="viewMode" :options="viewOptions" size="small" />

        <el-button size="small" circle @click="openReview('H6-4-check')">💬</el-button>
      </div>
    </div>

    <input ref="importFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onImportFile" />

    <!-- 异常摘要 -->
    <el-alert
      v-if="summary.warning"
      type="warning"
      :closable="false"
      show-icon
      class="warn-alert"
      :title="summary.warning"
    />

    <!-- 二、测试 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">二、测试</span>
        </div>
      </template>
      <div class="test-reason-row">
        <span class="reason-label">测试原因：</span>
        <el-checkbox-group
          :model-value="testReasons"
          :disabled="props.isReadonly"
          @change="onTestReasonsChange"
        >
          <el-checkbox :value="'largeAmount'">大额</el-checkbox>
          <el-checkbox :value="'relatedParty'">关联方</el-checkbox>
          <el-checkbox :value="'frequentLarge'">大额交易频繁</el-checkbox>
          <el-checkbox :value="'abnormal'">异常</el-checkbox>
          <el-checkbox :value="'other'">其他</el-checkbox>
        </el-checkbox-group>
        <el-input
          v-if="testReasons.includes('other')"
          v-model="otherReasonText"
          size="small"
          placeholder="其他原因说明"
          style="width:200px;margin-left:8px"
          :disabled="props.isReadonly"
          @change="persistOtherReason"
        />
      </div>
      <div class="test-content-hint">
        <p>测试内容说明：</p>
        <ol>
          <li v-for="(lbl, i) in CHECK_CONTENT_LABELS" :key="i">{{ lbl }}</li>
        </ol>
      </div>
    </el-card>

    <!-- 抽样参数 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">抽样参数</span>
          <div class="title-actions">
            <el-button
              size="small"
              :disabled="props.isReadonly || !(linkedPopulation.amount > 0)"
              @click="handleSyncPopulation"
            >
              从 H6-2 带入本期减少
            </el-button>
            <el-button
              size="small"
              type="primary"
              :disabled="props.isReadonly"
              @click="showSamplingDialog = true"
            >
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="本期减少合计（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!props.isReadonly"
              :model-value="sampling.totalPopulation"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateSampling({ totalPopulation: v ?? 0 })"
            />
            <span v-else class="amt-cell">{{ fmtAmt(sampling.totalPopulation) }}</span>
            <el-tag v-if="linkedPopulation.source" size="small" type="info" class="src-tag">
              源 {{ linkedPopulation.source }}: {{ fmtAmt(linkedPopulation.amount) }}
            </el-tag>
            <el-tag v-if="sampling.populationManual" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="样本量">{{ summary.checkedCount }}</el-descriptions-item>
        <el-descriptions-item label="检查比例">
          <span :class="{ 'warn-coverage': summary.hasLowCoverage }">
            {{ summary.coverageRate.toFixed(2) }}%
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法">
          <el-select
            v-if="!props.isReadonly"
            :model-value="sampling.samplingMethod"
            size="small"
            style="width:140px"
            @change="(v: string) => updateSampling({ samplingMethod: v })"
          >
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随机抽样" value="随机抽样" />
            <el-option label="判断抽样" value="判断抽样" />
          </el-select>
          <span v-else>{{ sampling.samplingMethod || '待确定' }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <div class="sampling-extra">
        <div class="sampling-field">
          <label>特定样本</label>
          <el-input
            v-if="!props.isReadonly"
            :model-value="sampling.specificSample"
            type="textarea"
            :autosize="{ minRows: 2 }"
            size="small"
            placeholder="大额清理、关联方处置、异常挂账全部测试"
            @change="(v: string) => updateSampling({ specificSample: v })"
          />
          <span v-else>{{ sampling.specificSample || '-' }}</span>
        </div>
        <div class="sampling-field">
          <label>抽样过程</label>
          <el-input
            v-if="!props.isReadonly"
            :model-value="sampling.samplingProcess"
            type="textarea"
            :autosize="{ minRows: 2 }"
            size="small"
            placeholder="描述抽样步骤与工具（IDEA/MUS 等）"
            @change="(v: string) => updateSampling({ samplingProcess: v })"
          />
          <span v-else>{{ sampling.samplingProcess || '-' }}</span>
        </div>
      </div>
      <el-alert
        v-if="populationDrift"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`总体与 H6-2（${fmtAmt(linkedPopulation.amount)}）不一致，可重新带入或保留手工数。`"
      />
    </el-card>

    <!-- 三、样本明细 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、清理检查明细（{{ rows.length }} 笔）</span>
          <div class="title-actions">
            <el-button
              size="small"
              data-testid="h6-check-sync-btn"
              :disabled="props.isReadonly"
              @click="handleSyncFromH62"
            >
              从 H6-2 同步
            </el-button>
            <el-button size="small" type="primary" :disabled="props.isReadonly" @click="handleAddRow">
              + 新增
            </el-button>
          </div>
        </div>
      </template>

      <!-- 表格视图 -->
      <el-table
        v-if="viewMode === 'table'"
        :data="rows"
        border
        stripe
        size="small"
        max-height="520"
        class="check-table"
        data-testid="h6-check-table"
        row-key="rowId"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="序号" width="48" fixed align="center" />

        <el-table-column label="基础信息" align="center">
          <el-table-column v-if="isColVisible('date')" label="日期" width="118">
            <template #default="{ row }">
              <el-date-picker
                v-if="!props.isReadonly"
                :model-value="row.date"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:108px"
                @update:model-value="(v: string) => updateCell(row.rowId, 'date', v)"
              />
              <span v-else>{{ row.date || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('voucherNo')" label="凭证编号" width="90">
            <template #default="{ row }">
              <el-input
                v-if="!props.isReadonly"
                :model-value="row.voucherNo"
                size="small"
                @change="(v: string) => updateCell(row.rowId, 'voucherNo', v)"
              />
              <span v-else>{{ row.voucherNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('category')" label="类别" width="80">
            <template #default="{ row }">
              <el-input
                v-if="!props.isReadonly"
                :model-value="row.category"
                size="small"
                @change="(v: string) => updateCell(row.rowId, 'category', v)"
              />
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('assetName')" label="固定资产名称" min-width="120" fixed>
            <template #default="{ row }">
              <div class="name-cell">
                <el-input
                  v-if="!props.isReadonly"
                  :model-value="row.assetName"
                  size="small"
                  @change="(v: string) => updateCell(row.rowId, 'assetName', v)"
                />
                <span v-else>{{ row.assetName || '-' }}</span>
                <el-button
                  v-if="row.linkedDetailRowId"
                  size="small"
                  type="primary"
                  link
                  class="chip-jump"
                  @click="emit('navigate-sheet', '明细表H6-2')"
                >↗H6-2</el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('counterpartAccount')" label="对方科目" width="100">
            <template #default="{ row }">
              <el-input
                v-if="!props.isReadonly"
                :model-value="row.counterpartAccount"
                size="small"
                @change="(v: string) => updateCell(row.rowId, 'counterpartAccount', v)"
              />
              <span v-else>{{ row.counterpartAccount || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="被清理固定资产情况" align="center">
          <el-table-column v-if="isColVisible('originalCost')" label="原值" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.originalCost"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(row.rowId, 'originalCost', v)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.originalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('accumulatedDepreciation')" label="累计折旧" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.accumulatedDepreciation"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(row.rowId, 'accumulatedDepreciation', v)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.accumulatedDepreciation) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('impairment')" label="减值准备" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.impairment"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(row.rowId, 'impairment', v)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('netValue')" label="净值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="净值=原值−累计折旧−减值准备">
                {{ fmtAmt(row.netValue) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="清理损益" align="center">
          <el-table-column v-if="isColVisible('clearingExpense')" label="清理费用" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.clearingExpense"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(row.rowId, 'clearingExpense', v)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.clearingExpense) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('clearingIncome')" label="清理收入" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.clearingIncome"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(row.rowId, 'clearingIncome', v)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.clearingIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('clearingGainLoss')" label="清理净损益" width="110" align="right">
            <template #default="{ row }">
              <span
                :class="['formula-cell', { 'error-amount': row.clearingGainLoss < 0 }]"
                title="清理净损益=清理收入−清理费用−净值"
              >
                {{ fmtAmt(row.clearingGainLoss) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="结转" align="center">
          <el-table-column v-if="isColVisible('toNonOperating')" label="转营业外收入/支出" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.toNonOperating"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(row.rowId, 'toNonOperating', v)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.toNonOperating) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('toDisposalGain')" label="转资产处置收益" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.toDisposalGain"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCell(row.rowId, 'toDisposalGain', v)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.toDisposalGain) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isColVisible('endingBalance')" label="期末余额" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!props.isReadonly"
                :model-value="row.endingBalance"
                :controls="false"
                size="small"
                class="amt-input"
                :class="{ 'warn-input': Math.abs(row.endingBalance) > 0.005 }"
                @change="(v: number | undefined) => updateCell(row.rowId, 'endingBalance', v)"
              />
              <span
                v-else
                :class="['amt-cell', { 'warn-text': Math.abs(row.endingBalance) > 0.005 }]"
              >{{ fmtAmt(row.endingBalance) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="isColVisible('clearingReason')" label="清理原因" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.clearingReason"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'clearingReason', v)"
            />
            <span v-else>{{ row.clearingReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('approvedBy')" label="批准人" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.approvedBy"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'approvedBy', v)"
            />
            <span v-else>{{ row.approvedBy || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('checks')" label="核对" width="150" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content>
                <div v-for="(lbl, i) in CHECK_CONTENT_LABELS" :key="i">{{ i + 1 }}. {{ lbl }}</div>
              </template>
              <span>核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group
              :model-value="checkedIndexes(row)"
              :disabled="props.isReadonly"
              class="check-group"
              @update:model-value="(v: any) => setChecks(row.rowId, v as number[])"
            >
              <el-checkbox v-for="(_, i) in CHECK_CONTENT_LABELS" :key="i" :value="i">{{ i + 1 }}</el-checkbox>
            </el-checkbox-group>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('isAbnormal')" label="异常" width="64" align="center">
          <template #default="{ row }">
            <el-switch
              :model-value="row.isAbnormal"
              :disabled="props.isReadonly"
              size="small"
              @change="(v: boolean | string | number) => updateCell(row.rowId, 'isAbnormal', Boolean(v))"
            />
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('indexRef')" label="索引号" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.indexRef"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'indexRef', v)"
            />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('refLinks')" label="联动索引" width="120" align="center">
          <template #default="{ row }">
            <div class="ref-chips">
              <GtIndexChip
                v-if="row.refH1Code"
                value="wp:H1-8"
                :context-project-id="props.projectId"
                :context="row.refH1Code"
              />
              <GtIndexChip
                v-if="row.refH10Code || Math.abs(row.toDisposalGain) > 0"
                value="wp:H10"
                :context-project-id="props.projectId"
                :context="row.refH10Code || '处置损益'"
              />
            </div>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('ocr')" label="附件" width="56" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              link
              :disabled="props.isReadonly"
              title="OCR 识别合同/发票"
              @click="handleOcr(row)"
            >📎</el-button>
          </template>
        </el-table-column>

        <el-table-column v-if="isColVisible('remark')" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!props.isReadonly"
              :model-value="row.remark"
              size="small"
              @change="(v: string) => updateCell(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!props.isReadonly" label="" width="44" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="deleteRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 卡片视图 -->
      <el-collapse v-else-if="viewMode === 'card'" v-model="expandedCards" class="card-collapse">
        <el-collapse-item
          v-for="(row, idx) in rows"
          :key="row.rowId"
          :name="row.rowId"
          :class="cardItemClass(row)"
        >
          <template #title>
            <span class="card-title-row">
              <b>{{ idx + 1 }}. {{ row.assetName || '未命名' }}</b>
              <span class="card-meta">{{ row.voucherNo || row.date || '' }}</span>
              <el-tag v-if="row.isAbnormal" size="small" type="danger">异常</el-tag>
            </span>
          </template>
          <div class="card-body">
            <div class="card-amounts">
              <span>净值 <b class="formula-cell">{{ fmtAmt(row.netValue) }}</b></span>
              <span>清理收入 {{ fmtAmt(row.clearingIncome) }}</span>
              <span>清理费用 {{ fmtAmt(row.clearingExpense) }}</span>
              <span>净损益 <b :class="{ 'error-amount': row.clearingGainLoss < 0 }">{{ fmtAmt(row.clearingGainLoss) }}</b></span>
              <span>转营业外 {{ fmtAmt(row.toNonOperating) }}</span>
              <span>转处置收益 {{ fmtAmt(row.toDisposalGain) }}</span>
              <span :class="{ 'warn-text': Math.abs(row.endingBalance) > 0.005 }">
                期末余额 {{ fmtAmt(row.endingBalance) }}
              </span>
            </div>
            <div class="card-checks">
              <span class="reason-label">核对：</span>
              <el-checkbox-group
                :model-value="checkedIndexes(row)"
                :disabled="props.isReadonly"
                @update:model-value="(v: any) => setChecks(row.rowId, v as number[])"
              >
                <el-checkbox
                  v-for="(lbl, i) in CHECK_CONTENT_LABELS"
                  :key="i"
                  :value="i"
                >{{ i + 1 }}</el-checkbox>
              </el-checkbox-group>
            </div>
            <div class="card-actions">
              <span>异常</span>
              <el-switch
                :model-value="row.isAbnormal"
                :disabled="props.isReadonly"
                size="small"
                @change="(v: boolean | string | number) => updateCell(row.rowId, 'isAbnormal', Boolean(v))"
              />
              <el-button size="small" link :disabled="props.isReadonly" @click="handleOcr(row)">📎 OCR</el-button>
              <el-button v-if="!props.isReadonly" size="small" type="danger" link @click="deleteRow(row.rowId)">删除</el-button>
            </div>
          </div>
        </el-collapse-item>
        <el-empty v-if="rows.length === 0" description="暂无样本，请从 H6-2 同步或新增" :image-size="60" />
      </el-collapse>

      <div class="summary-bar">
        <span>样本原值: <b class="amt-cell">{{ fmtAmt(summary.originalCostTotal) }}</b></span>
        <span>净值合计: <b class="amt-cell">{{ fmtAmt(summary.netValueTotal) }}</b></span>
        <span>清理收入: <b class="amt-cell">{{ fmtAmt(summary.incomeTotal) }}</b></span>
        <span>
          净损益合计:
          <b :class="['amt-cell', { 'error-amount': summary.gainLossTotal < 0 }]">
            {{ fmtAmt(summary.gainLossTotal) }}
          </b>
        </span>
        <span>转营业外: <b class="amt-cell">{{ fmtAmt(summary.toNonOperatingTotal) }}</b></span>
        <span>转处置收益: <b class="amt-cell">{{ fmtAmt(summary.toDisposalGainTotal) }}</b></span>
        <span>
          期末余额合计:
          <b :class="['amt-cell', { 'warn-text': Math.abs(summary.endingBalanceTotal) > 0.005 }]">
            {{ fmtAmt(summary.endingBalanceTotal) }}
          </b>
        </span>
        <span :class="{ 'warn-coverage': summary.hasLowCoverage }">
          检查比例: <b>{{ summary.coverageRate.toFixed(2) }}%</b>
        </span>
      </div>
      <el-alert
        v-if="summary.hasLowCoverage"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        title="检查比例偏低：请扩大样本量，或在审计说明中解释原因。"
      />
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">四、审计说明</span>
          <div class="title-actions">
            <el-button
              size="small"
              type="primary"
              link
              :loading="aiLoading"
              :disabled="props.isReadonly"
              @click="handleAiDraft"
            >
              <el-icon><MagicStick /></el-icon> AI 生成
            </el-button>
            <el-button size="small" link :disabled="props.isReadonly" @click="handleLocalDraftNote">
              本地草拟
            </el-button>
            <el-button size="small" circle @click="openReview('H6-4-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="props.isReadonly"
        placeholder="概述抽样方法与检查比例、凭证核对结果、清理损益核算、结转科目（营业外 vs 资产处置收益）、1606 期末清零情况；比例偏低时须说明原因。"
        @update:model-value="(v: string) => (auditNoteLocal = v)"
        @blur="saveAuditNote(auditNoteLocal)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">五、审计结论</span>
          <div class="title-actions">
            <el-button size="small" link :disabled="props.isReadonly" @click="handleLocalDraftConclusion">
              本地草拟
            </el-button>
            <el-button size="small" circle @click="openReview('H6-4-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-select
        v-if="!props.isReadonly"
        size="small"
        class="concl-select"
        placeholder="选择结论模板"
        @change="(v: string) => applyConclusionTemplate(v)"
      >
        <el-option
          v-for="t in H6_CONCLUSION_TEMPLATES"
          :key="t.value"
          :label="t.label"
          :value="t.value"
        />
      </el-select>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="props.isReadonly"
        placeholder="基于检查结果，就固定资产清理的存在/发生、完整性、权利义务、计价分摊认定发表结论……"
        @update:model-value="(v: string) => (conclusionLocal = v)"
        @blur="saveAuditConclusion(conclusionLocal)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>勾稽：净值=原值−累计折旧−减值；清理净损益=清理收入−清理费用−净值</li>
        <li>检查比例=样本净值合计÷H6-2本期减少净值合计；偏低（&lt;20%）须扩样或说明</li>
        <li>核对第5项：结转营业外 vs 资产处置收益分摊正确，1606已清零，与H10勾稽一致</li>
        <li>结转列区分「转营业外收入/支出」与「转资产处置收益」（CAS30）</li>
        <li>1606 为过渡科目，样本期末余额原则上应清零；未清零须说明挂账原因</li>
        <li>从 H6-2 同步可带入资产与金额骨架，再补凭证号、核对勾选与结转分摊</li>
        <li>抽凭引擎科目 1606；处置损益联动 H10</li>
      </ul>
    </details>

    <el-dialog
      v-model="showSamplingDialog"
      title="抽凭引擎 — 固定资产清理(1606)"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        account-code="1606"
        phase="final"
        default-method="mus"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabCheck.vue — H6-4 固定资产清理检查表（对齐致同源模板凭证级测试）
 */
import { ref, computed, inject, toRef, watch, reactive, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import {
  useH6Check,
  type H6CheckTestReason,
  type H6CheckRow,
} from '../../composables/useH6Check'
import { useH6ImportExport } from '../../composables/useH6ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string, label?: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  testReasons,
  testReasonOther,
  sampling,
  auditNote,
  auditConclusion,
  summary,
  linkedPopulation,
  CHECK_CONTENT_LABELS,
  H6_CONCLUSION_TEMPLATES,
  updateTestReasons,
  updateSampling,
  syncPopulationFromH62,
  addRow,
  deleteRow,
  updateCell,
  syncFromDetailRows,
  fillFromSampledVouchers,
  applyOcrFields,
  applyLocalDraftNote,
  applyLocalDraftConclusion,
  saveAuditNote,
  saveAuditConclusion,
  applyConclusionTemplate,
  isTransferMismatch,
  isHangingOverOneYear,
  load,
} = useH6Check({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId, value) => saveResponse(itemId, value),
})

const importExport = useH6ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => load(),
})

const otherReasonText = ref('')
const auditNoteLocal = ref('')
const conclusionLocal = ref('')
const showSamplingDialog = ref(false)
const aiLoading = ref(false)
const importFileRef = ref<HTMLInputElement | null>(null)
const expandedCards = ref<string[]>([])
const viewMode = ref<'table' | 'card'>('table')
const viewOptions = [
  { label: '表格', value: 'table' },
  { label: '卡片', value: 'card' },
]

const samplingYear = computed(() => props.year ?? new Date().getFullYear())

watch(testReasonOther, (v) => { otherReasonText.value = v }, { immediate: true })
watch(auditNote, (v) => { auditNoteLocal.value = v }, { immediate: true })
watch(auditConclusion, (v) => { conclusionLocal.value = v }, { immediate: true })

// ─── Column preferences ──────────────────────────────────────────────────────

const COL_PREFS_KEY = 'h6-4-column-prefs'
const ALWAYS_VISIBLE_KEYS = ['assetName', 'netValue', 'clearingGainLoss', 'endingBalance']
const DEFAULT_HIDDEN_KEYS = ['approvedBy', 'counterpartAccount', 'remark']

interface ColDef { key: string; label: string }

const ALL_COLS: ColDef[] = [
  { key: 'date', label: '日期' },
  { key: 'voucherNo', label: '凭证编号' },
  { key: 'category', label: '类别' },
  { key: 'assetName', label: '固定资产名称' },
  { key: 'counterpartAccount', label: '对方科目' },
  { key: 'originalCost', label: '原值' },
  { key: 'accumulatedDepreciation', label: '累计折旧' },
  { key: 'impairment', label: '减值准备' },
  { key: 'netValue', label: '净值' },
  { key: 'clearingExpense', label: '清理费用' },
  { key: 'clearingIncome', label: '清理收入' },
  { key: 'clearingGainLoss', label: '清理净损益' },
  { key: 'toNonOperating', label: '转营业外' },
  { key: 'toDisposalGain', label: '转处置收益' },
  { key: 'endingBalance', label: '期末余额' },
  { key: 'clearingReason', label: '清理原因' },
  { key: 'approvedBy', label: '批准人' },
  { key: 'checks', label: '核对内容' },
  { key: 'isAbnormal', label: '异常' },
  { key: 'indexRef', label: '索引号' },
  { key: 'refLinks', label: '联动索引' },
  { key: 'ocr', label: 'OCR附件' },
  { key: 'remark', label: '备注' },
]

const colPrefs = reactive<Record<string, boolean>>(
  Object.fromEntries(ALL_COLS.map((c) => [c.key, !DEFAULT_HIDDEN_KEYS.includes(c.key)])),
)

const toggleableCols = computed(() => ALL_COLS)

function isColVisible(key: string): boolean {
  if (ALWAYS_VISIBLE_KEYS.includes(key)) return true
  return colPrefs[key] !== false
}

function toggleCol(key: string, visible: boolean): void {
  if (ALWAYS_VISIBLE_KEYS.includes(key)) return
  colPrefs[key] = visible
  persistColPrefs()
}

function persistColPrefs(): void {
  const hidden = Object.entries(colPrefs)
    .filter(([, v]) => !v)
    .map(([k]) => k)
  localStorage.setItem(COL_PREFS_KEY, JSON.stringify(hidden))
}

function resetColPrefs(): void {
  for (const c of ALL_COLS) {
    colPrefs[c.key] = !DEFAULT_HIDDEN_KEYS.includes(c.key)
  }
  persistColPrefs()
}

;(() => {
  try {
    const raw = localStorage.getItem(COL_PREFS_KEY)
    if (raw) {
      const hidden: string[] = JSON.parse(raw)
      for (const k of hidden) {
        if (k in colPrefs && !ALWAYS_VISIBLE_KEYS.includes(k)) colPrefs[k] = false
      }
    }
  } catch { /* ignore */ }
})()

// ─── Helpers ─────────────────────────────────────────────────────────────────

const coverageTagType = computed(() => {
  const rate = summary.value.coverageRate
  if (!(sampling.value.totalPopulation > 0)) return 'info'
  if (rate < 20) return 'danger'
  if (rate < 50) return 'warning'
  return 'success'
})

const populationDrift = computed(() => {
  const linked = linkedPopulation.value.amount
  const pop = sampling.value.totalPopulation
  if (!(linked > 0) || !(pop > 0)) return false
  return Math.abs(linked - pop) > 0.5
})

function fmtAmt(n: number): string {
  return (Number(n) || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function strVal(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function onTestReasonsChange(vals: H6CheckTestReason[]) {
  updateTestReasons(vals, otherReasonText.value)
}

function persistOtherReason() {
  updateTestReasons(testReasons.value, otherReasonText.value)
}

function handleSyncPopulation() {
  const r = syncPopulationFromH62(true)
  if (r.ok) {
    ElMessage.success(`已从 ${r.source} 带入本期减少合计 ${fmtAmt(r.amount)}`)
  } else {
    ElMessage.warning('H6-2 暂无明细净值，请先完成明细表')
  }
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入固定资产名称', '新增检查样本', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleSyncFromH62() {
  const detailData = props.allResponses.get('H6-2-rows')
  if (!detailData) {
    ElMessage.warning('H6-2 明细表暂无数据，请先在 H6-2 中添加清理项目')
    return
  }
  let detailRows: any[] = []
  try {
    const raw = detailData.remark ?? detailData.conclusion ?? detailData
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) detailRows = parsed
  } catch { /* parse error */ }

  if (detailRows.length === 0) {
    ElMessage.warning('H6-2 明细表暂无数据')
    return
  }

  const added = syncFromDetailRows(
    detailRows.map((r: any) => ({
      rowId: r.rowId || r.id || '',
      assetName: r.assetName || r.projectName || r.name || '',
      originalCost: r.originalCost,
      accumulatedDepreciation: r.accumulatedDepreciation,
      impairment: r.impairment ?? r.impairmentProvision,
      disposalIncome: r.disposalIncome,
      disposalExpenses: r.disposalExpenses,
      taxAmount: r.taxAmount,
      disposalReason: r.disposalReason,
      startDate: r.startDate,
      transferAccount: r.transferAccount,
      gainLoss: r.gainLoss,
      netBookValue: r.netBookValue,
      status: r.status,
      refH1Code: r.refH1Code ?? r.refH1 ?? '',
      refH10Code: r.refH10Code ?? r.refH10 ?? '',
    })),
  )
  ElMessage.success(`已同步 H6-2：新增 ${added} 笔，共 ${rows.value.length} 笔样本`)
}

function checkedIndexes(row: H6CheckRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter((i) => i >= 0)
}

function setChecks(rowId: string, idxs: number[]) {
  const arr = [false, false, false, false, false]
  for (const i of idxs) {
    if (i >= 0 && i < 5) arr[i] = true
  }
  updateCell(rowId, 'checks', arr)
}

function rowClassName({ row }: { row: H6CheckRow }) {
  if (row.isAbnormal) return 'row-abnormal'
  if (isTransferMismatch(row)) return 'row-mismatch'
  if (Math.abs(row.endingBalance) > 0.005) return 'row-hanging'
  if (isHangingOverOneYear(row)) return 'row-over-year'
  return ''
}

function cardItemClass(row: H6CheckRow): string {
  return rowClassName({ row })
}

function onSamplesFilled(payload: { samples?: any[] } | any[]) {
  showSamplingDialog.value = false
  const samples = Array.isArray(payload) ? payload : (payload?.samples ?? [])
  if (!Array.isArray(samples) || samples.length === 0) return
  const n = fillFromSampledVouchers(samples)
  ElMessage.success(`已填入 ${n} 笔抽凭样本`)
}

async function handleOcr(row: H6CheckRow) {
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
      const data = res.data?.data ?? res.data
      const fields = data?.extracted_fields || {}
      if (!Object.keys(fields).length) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段', '提示')
        return
      }
      const preview = Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(`识别结果：\n${preview}\n\n确认填入？`, 'OCR 识别结果', {
        confirmButtonText: '填入',
        cancelButtonText: '取消',
      })
      applyOcrFields(row.rowId, fields)
      ElMessage.success('已填入 OCR 识别字段')
    } catch { /* cancel or error */ }
  }
  input.click()
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H6-4')
  else if (command === 'export-data') importExport.exportData('H6-4')
  else if (command === 'import-data') importFileRef.value?.click()
}

function onImportFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) importExport.importData('H6-4', file)
  ;(e.target as HTMLInputElement).value = ''
}

async function handleAiDraft() {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const context: Record<string, string> = {
      sampleCount: strVal(summary.value.checkedCount),
      coverageRate: strVal(summary.value.coverageRate),
      totalPopulation: strVal(sampling.value.totalPopulation),
      samplingMethod: strVal(sampling.value.samplingMethod),
      specificSample: strVal(sampling.value.specificSample),
      samplingProcess: strVal(sampling.value.samplingProcess),
      testReasons: strVal(testReasons.value),
      testReasonOther: strVal(otherReasonText.value),
      originalCostTotal: strVal(summary.value.originalCostTotal),
      netValueTotal: strVal(summary.value.netValueTotal),
      incomeTotal: strVal(summary.value.incomeTotal),
      gainLossTotal: strVal(summary.value.gainLossTotal),
      toNonOperatingTotal: strVal(summary.value.toNonOperatingTotal),
      toDisposalGainTotal: strVal(summary.value.toDisposalGainTotal),
      endingBalanceTotal: strVal(summary.value.endingBalanceTotal),
      anomalyCount: strVal(summary.value.anomalyCount),
      nonZeroEndingCount: strVal(summary.value.nonZeroEndingCount),
      transferMismatchCount: strVal(summary.value.transferMismatchCount),
      overOneYearCount: strVal(summary.value.overOneYearCount),
      h10GainLossDiff: strVal(summary.value.h10GainLossDiff),
      warning: strVal(summary.value.warning),
      linkedPopulation: strVal(linkedPopulation.value),
      rows: strVal(rows.value.slice(0, 20).map((r) => ({
        assetName: r.assetName,
        voucherNo: r.voucherNo,
        netValue: r.netValue,
        clearingGainLoss: r.clearingGainLoss,
        endingBalance: r.endingBalance,
        isAbnormal: r.isAbnormal,
      }))),
    }
    const res = await http.post(
      `/api/workpapers/${props.wpId}/ai/generate-text`,
      {
        section: 'H6-4-note',
        prompt:
          '你是资深审计师。请基于固定资产清理(H6-4)检查表上下文，起草审计说明草稿：'
          + '涵盖抽样方法与检查比例、凭证核对、清理损益与结转（营业外/资产处置收益）、'
          + '1606期末清零及超1年挂账关注；勿编造未提供的金额。',
        existingContent: auditNoteLocal.value || auditNote.value || '',
        context,
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.text || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    await ElMessageBox.confirm(
      text.slice(0, 800) + (text.length > 800 ? '…' : ''),
      'AI 起草确认',
      { confirmButtonText: '填入说明', cancelButtonText: '取消' },
    )
    auditNoteLocal.value = text
    saveAuditNote(text)
    ElMessage.success('已填入审计说明，可继续编辑')
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.warning('AI 起草失败，请手工填写或使用本地草拟')
    }
  } finally {
    aiLoading.value = false
  }
}

function handleLocalDraftNote() {
  const text = applyLocalDraftNote()
  auditNoteLocal.value = text
  ElMessage.success('已生成本地审计说明草稿')
}

function handleLocalDraftConclusion() {
  const text = applyLocalDraftConclusion()
  conclusionLocal.value = text
  ElMessage.success('已套用本地结论草稿')
}

function openReview(id: string) {
  openReviewDialog(id, 'H6-4 检查表')
}
</script>

<style scoped>
.h6-tab-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.guide-banner {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: linear-gradient(135deg, #eff6ff, #f0f9ff);
  border: 1px solid #bfdbfe;
}
.guide-step { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #1e3a8a; }
.gs-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 50%;
  background: #2563eb; color: #fff; font-size: 11px; font-weight: 700;
}

.audit-objective { margin-bottom: 12px; }
.ao-title { font-weight: 600; }
.ao-list { padding-left: 18px; margin: 4px 0 0; line-height: 1.55; font-size: 12px; }
:deep(.el-alert__content) { padding: 2px 0; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.tab-toolbar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; flex-wrap: wrap;
}
.toolbar-right {
  margin-left: auto;
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}

.col-prefs-pop { max-height: 320px; overflow-y: auto; }
.col-pref-item { margin-bottom: 4px; }

.warn-alert { margin-bottom: 12px; }

.section-card { margin-bottom: 12px; }
.section-card :deep(.el-card__header) { padding: 8px 12px; }
.section-card :deep(.el-card__body) { padding: 12px; }

.card-header-row {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.card-title { font-size: 14px; font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

.test-reason-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-bottom: 10px;
}
.reason-label { font-size: 12px; color: var(--el-text-color-secondary); margin-right: 4px; }

.test-content-hint {
  font-size: 12px; color: #92400e;
  background: #fffbeb; border-radius: 4px; padding: 8px 12px;
}
.test-content-hint p { margin: 0 0 4px; font-weight: 500; }
.test-content-hint ol { margin: 0; padding-left: 18px; line-height: 1.5; }

.pop-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.src-tag { margin-left: 2px; }

.sampling-extra {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.sampling-field label {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.check-table { font-size: var(--wp-font-size, 13px); }
.name-cell { display: flex; align-items: center; gap: 4px; }
.chip-jump { font-size: 11px; padding: 0 4px; white-space: nowrap; }
.ref-chips { display: flex; flex-wrap: wrap; gap: 4px; justify-content: center; }

.amt-input { width: 100%; }
.amt-input :deep(.el-input__inner) { text-align: right; }
.amt-cell { font-variant-numeric: tabular-nums; }
.formula-cell {
  font-variant-numeric: tabular-nums;
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.error-amount { color: var(--el-color-danger); }
.warn-text { color: #d97706; font-weight: 600; }
.warn-coverage { color: var(--el-color-danger); }
.warn-input :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f59e0b inset; }

.check-group {
  display: flex; flex-wrap: wrap; gap: 0; justify-content: center;
}
.check-group :deep(.el-checkbox) { margin-right: 4px; }
.check-group :deep(.el-checkbox__label) { padding-left: 2px; font-size: 11px; }

.summary-bar {
  display: flex; flex-wrap: wrap; gap: 12px 16px;
  margin-top: 10px; padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px; font-size: 12px;
}

.card-collapse { border: none; }
.card-collapse :deep(.el-collapse-item__header) { font-size: 13px; padding-left: 8px; }
.card-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.card-body { padding: 4px 8px 12px; }
.card-amounts {
  display: flex; flex-wrap: wrap; gap: 10px 16px;
  margin-bottom: 10px; font-size: 12px;
}
.card-checks { margin-bottom: 10px; display: flex; flex-wrap: wrap; align-items: flex-start; gap: 4px; }
.card-actions { display: flex; align-items: center; gap: 10px; font-size: 12px; }

.concl-select { width: 100%; max-width: 520px; margin-bottom: 8px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }

:deep(.row-abnormal) { background: #fef2f2 !important; }
:deep(.row-mismatch) { background: #fff7ed !important; }
:deep(.row-hanging) { background: #fffbeb !important; }
:deep(.row-over-year) { background: #fef3c7 !important; }
:deep(.row-abnormal.row-hanging),
:deep(.row-abnormal.row-over-year) { background: #fef2f2 !important; }
</style>
