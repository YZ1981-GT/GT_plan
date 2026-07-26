<template>
  <div class="h3-tab-addition-check">
    <!-- 编制提示（致同 H3-5 提示区） -->
    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表用于汇总本年度增加、减少投资性房地产的测试情况（{{ modeLabel }}）。</p>
        <p>2. <b>外购</b>：追查至购买合同/发票/验收报告，确认有效性、金额正确性及审批；检查产权证、土地使用权证等所有权证明。</p>
        <p>3. <b>自用/存货转入</b>：关注转换依据是否充分、是否经有效批准，转换日成本/公允价值计量及会计处理是否正确。</p>
        <p>4. <b>后续支出</b>：检查核算是否符合规定；金额较大时进行细节测试，分析资本性支出与收益性支出划分是否合理。</p>
        <p v-if="isCost">5. 成本模式：净值 = 原值 − 累计折旧 − 减值准备；可与 H3-7 折旧测算交叉核对。</p>
        <p v-else>5. 公允价值模式：关注评估依据与公允价值变动损益列示；可与 H3-8 公允价值复核交叉核对。</p>
      </div>
    </details>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title><div class="obj-title">一、审计目标</div></template>
      <ol class="obj-list">
        <li>记录的投资性房地产是否存在，是否记录于正确的账户（存在认定）</li>
        <li>所有应记录的投资性房地产是否均已记录，披露是否充分（完整性认定）</li>
        <li>被审计单位是否拥有或控制记录的投资性房地产（权利与义务认定）</li>
        <li>是否以恰当金额列示，计价/折旧/公允价值变动及分摊是否恰当（计价与分摊认定）</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H3-5" :context-project-id="projectId" />
      <el-tag size="small" :type="isCost ? 'primary' : 'warning'">{{ modeLabel }}</el-tag>
      <el-tag size="small" type="info">样本 {{ activeRowCount }} 项</el-tag>
      <el-tag v-if="state.summary.value.anomalyCount > 0" size="small" type="danger">
        异常 {{ state.summary.value.anomalyCount }} 项
      </el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ state.summary.value.coverageRate.toFixed(2) }}%
      </el-tag>
    </div>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title"><span>二、样本选取标准与规模</span></div>
      </template>
      <div class="test-reason-row">
        <span class="reason-label">特定样本（重点选取）：</span>
        <el-checkbox-group
          :model-value="state.testReasons.value"
          :disabled="isReadonly"
          @change="onTestReasonsChange"
        >
          <el-checkbox label="largeAmount">大额</el-checkbox>
          <el-checkbox label="relatedParty">关联方</el-checkbox>
          <el-checkbox label="abnormal">异常</el-checkbox>
          <el-checkbox label="conversion">转换事项</el-checkbox>
          <el-checkbox label="other">其他</el-checkbox>
        </el-checkbox-group>
        <el-input
          v-if="state.testReasons.value.includes('other')"
          :model-value="state.testReasonOther.value"
          size="small"
          placeholder="其他原因说明"
          style="width:200px;margin-left:8px"
          :disabled="isReadonly"
          @change="state.updateTestReasonOther($event)"
        />
      </div>
      <div class="test-content-hint">
        <p>测试内容说明（核对内容 1–5 列）：</p>
        <ol>
          <li v-for="(item, i) in H3_TEST_CONTENT_ITEMS" :key="i">{{ item }}</li>
        </ol>
        <p class="hint-note">账→证抽查支撑存在与计价；三-B「证→账追查」从源文件追查至账面，支撑完整性认定。</p>
      </div>
      <el-descriptions :column="4" border size="small" style="margin-top:12px">
        <el-descriptions-item label="本期新增合计（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="state.samplingParams.value.totalPopulation"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateSamplingParams({ totalPopulation: v ?? 0 })"
            />
            <span v-else class="amount-cell">{{ fmtAmt(state.samplingParams.value.totalPopulation) }}</span>
            <el-tag v-if="state.linkedMovement.value.source" size="small" type="info" class="src-tag">
              源 {{ state.linkedMovement.value.source }}: {{ fmtAmt(state.linkedMovement.value.increaseAmount) }}
            </el-tag>
            <el-tag v-if="state.populationManual.value" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="样本量">{{ state.summary.value.checkedCount }}</el-descriptions-item>
        <el-descriptions-item label="检查比例">
          <span :class="{ 'warn-coverage': state.summary.value.coverageRate < 20 && effectivePopulation > 0 }">
            {{ state.summary.value.coverageRate.toFixed(2) }}%
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法">
          <el-select
            v-if="!isReadonly"
            :model-value="state.samplingParams.value.samplingMethod"
            size="small"
            style="width:140px"
            @change="(v: string) => state.updateSamplingParams({ samplingMethod: v })"
          >
            <el-option v-for="m in SAMPLING_METHOD_OPTS" :key="m" :label="m" :value="m" />
          </el-select>
          <span v-else>{{ state.samplingParams.value.samplingMethod || '待确定' }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <div class="sampling-actions">
        <el-button
          size="small"
          :disabled="isReadonly || !(state.linkedMovement.value.increaseAmount > 0)"
          @click="state.syncPopulationFromLinked()"
        >
          从 {{ state.linkedMovement.value.source || 'H3-1/H3-2' }} 带入本期新增
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="openSampling">
          🎲 抽凭引擎
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addRow()">+ 新增检查行</el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
          <el-button size="small" :loading="importing">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="vouch-export-template">导出模板（账→证）</el-dropdown-item>
              <el-dropdown-item command="vouch-export-data">导出数据（账→证）</el-dropdown-item>
              <el-dropdown-item command="vouch-import-data">导入数据（账→证）</el-dropdown-item>
              <el-dropdown-item divided command="trace-export-template">导出模板（证→账）</el-dropdown-item>
              <el-dropdown-item command="trace-export-data">导出数据（证→账）</el-dropdown-item>
              <el-dropdown-item command="trace-import-data">导入数据（证→账）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="vouchFileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onVouchFileSelected" />
        <input ref="traceFileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onTraceFileSelected" />
      </div>
      <el-alert
        v-if="state.populationDrift()"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`总体与 ${state.linkedMovement.value.source}（${fmtAmt(state.linkedMovement.value.increaseAmount)}）不一致，可重新带入或保留手工数。`"
      />
    </el-card>

    <!-- 三、测试过程 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三-A、测试过程 — 账→证抽查（{{ activeRowCount }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="navigateTo(isCost ? 'H3-7' : 'H3-8')">
              <GtIndexChip :value="isCost ? 'wp:H3-7' : 'wp:H3-8'" :context-project-id="projectId" />
            </el-button>
            <el-button size="small" type="default" link @click="openReview(reviewSection)">💬 复核</el-button>
          </div>
        </div>
      </template>

      <!-- 成本模式表格 -->
      <el-table
        v-if="isCost"
        :data="state.costRows.value"
        border stripe size="small"
        max-height="520"
        class="check-table"
        :row-class-name="state.rowClassName"
      >
        <el-table-column type="index" label="序号" width="48" fixed align="center" />
        <el-table-column label="投资性房地产信息" align="center">
          <el-table-column prop="category" label="类别" width="100">
            <template #default="{ row, $index }">
              <el-select v-if="!isReadonly" v-model="row.category" size="small" style="width:90px"
                @change="state.updateCell($index, 'category', $event)">
                <el-option v-for="c in H3_CATEGORY_OPTS" :key="c" :label="c" :value="c" />
              </el-select>
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="assetName" label="名称" min-width="110" fixed>
            <template #default="{ row, $index }">
              <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
                @change="state.updateCell($index, 'assetName', row.assetName)" />
              <span v-else>{{ row.assetName || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="date" label="增减日期" width="118">
            <template #default="{ row, $index }">
              <el-date-picker v-if="!isReadonly" v-model="row.date" type="date" size="small"
                value-format="YYYY-MM-DD" style="width:108px"
                @change="state.updateCell($index, 'date', $event)" />
              <span v-else>{{ row.date || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="changeType" label="增减方式" width="110">
            <template #default="{ row, $index }">
              <el-select v-if="!isReadonly" v-model="row.changeType" size="small" style="width:98px"
                @change="state.updateCell($index, 'changeType', $event)">
                <el-option v-for="t in H3_CHANGE_TYPE_OPTS" :key="t" :label="t" :value="t" />
              </el-select>
              <span v-else>{{ row.changeType || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="账务记录" align="center">
          <el-table-column prop="voucherNo" label="凭证号" width="90">
            <template #default="{ row, $index }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
                @change="state.updateCell($index, 'voucherNo', row.voucherNo)" />
              <span v-else>{{ row.voucherNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="creditAccount" label="对方科目" width="90">
            <template #default="{ row, $index }">
              <el-input v-if="!isReadonly" v-model="row.creditAccount" size="small"
                @change="state.updateCell($index, 'creditAccount', row.creditAccount)" />
              <span v-else>{{ row.creditAccount || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="增减情况" align="center">
          <el-table-column prop="originalCost" label="原值" width="100" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small"
                class="amt-input" @change="state.updateCell($index, 'originalCost', row.originalCost)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="accDep" label="累计折旧" width="100" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" v-model="row.accDep" :controls="false" size="small"
                class="amt-input" @change="state.updateCell($index, 'accDep', row.accDep)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.accDep) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="减值准备" width="100" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false" size="small"
                class="amt-input" @change="state.updateCell($index, 'impairment', row.impairment)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="原值−累计折旧−减值准备">{{ fmtAmt(row.netValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="supportingDocs" label="支持性文件" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.supportingDocs" size="small"
              :placeholder="getEvidenceHint(row.changeType)"
              @change="state.updateCell($index, 'supportingDocs', row.supportingDocs)" />
            <span v-else :title="getEvidenceHint(row.changeType)">{{ row.supportingDocs || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对内容" align="center">
          <el-table-column v-for="(item, ci) in H3_TEST_CONTENT_ITEMS" :key="ci"
            :label="String(ci + 1)" width="44" align="center">
            <template #default="{ row, $index }">
              <el-checkbox
                v-if="!isReadonly"
                :model-value="row.checks[`check${ci + 1}` as keyof typeof row.checks]"
                @change="state.updateCell($index, `checks.check${ci + 1}`, $event)"
              />
              <span v-else>{{ row.checks[`check${ci + 1}` as keyof typeof row.checks] ? '✓' : '' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="indexRef" label="索引号" width="80">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
              @change="state.updateCell($index, 'indexRef', row.indexRef)" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isAbnormal" label="是否异常" width="80" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" v-model="row.isAbnormal" size="small" style="width:64px"
              @change="state.updateCell($index, 'isAbnormal', $event)">
              <el-option label="否" value="N" />
              <el-option label="是" value="Y" />
            </el-select>
            <el-tag v-else :type="row.isAbnormal === 'Y' ? 'danger' : 'success'" size="small">
              {{ row.isAbnormal === 'Y' ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="48" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleOcr($index)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注说明" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="state.updateCell($index, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="48" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 公允价值模式表格 -->
      <el-table
        v-else
        :data="state.fairRows.value"
        border stripe size="small"
        max-height="520"
        class="check-table"
        :row-class-name="state.rowClassName"
      >
        <el-table-column type="index" label="序号" width="48" fixed align="center" />
        <el-table-column label="投资性房地产信息" align="center">
          <el-table-column prop="category" label="类别" width="100">
            <template #default="{ row, $index }">
              <el-select v-if="!isReadonly" v-model="row.category" size="small" style="width:90px"
                @change="state.updateCell($index, 'category', $event)">
                <el-option v-for="c in H3_CATEGORY_OPTS" :key="c" :label="c" :value="c" />
              </el-select>
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="assetName" label="名称" min-width="110" fixed>
            <template #default="{ row, $index }">
              <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
                @change="state.updateCell($index, 'assetName', row.assetName)" />
              <span v-else>{{ row.assetName || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="date" label="增减日期" width="118">
            <template #default="{ row, $index }">
              <el-date-picker v-if="!isReadonly" v-model="row.date" type="date" size="small"
                value-format="YYYY-MM-DD" style="width:108px"
                @change="state.updateCell($index, 'date', $event)" />
              <span v-else>{{ row.date || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="changeType" label="增减方式" width="110">
            <template #default="{ row, $index }">
              <el-select v-if="!isReadonly" v-model="row.changeType" size="small" style="width:98px"
                @change="state.updateCell($index, 'changeType', $event)">
                <el-option v-for="t in H3_CHANGE_TYPE_OPTS" :key="t" :label="t" :value="t" />
              </el-select>
              <span v-else>{{ row.changeType || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="账务记录" align="center">
          <el-table-column prop="voucherNo" label="凭证号" width="90">
            <template #default="{ row, $index }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
                @change="state.updateCell($index, 'voucherNo', row.voucherNo)" />
              <span v-else>{{ row.voucherNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="creditAccount" label="对方科目" width="90">
            <template #default="{ row, $index }">
              <el-input v-if="!isReadonly" v-model="row.creditAccount" size="small"
                @change="state.updateCell($index, 'creditAccount', row.creditAccount)" />
              <span v-else>{{ row.creditAccount || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="增减情况" align="center">
          <el-table-column prop="fairValue" label="公允价值" width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" v-model="row.fairValue" :controls="false" size="small"
                class="amt-input" @change="state.updateCell($index, 'fairValue', row.fairValue)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.fairValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="fairValueChange" label="公允价值变动" width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-if="!isReadonly" v-model="row.fairValueChange" :controls="false" size="small"
                class="amt-input" @change="state.updateCell($index, 'fairValueChange', row.fairValueChange)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.fairValueChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末公允价值">{{ fmtAmt(row.endBalance || row.fairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="appraisalBasis" label="评估依据" min-width="110">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.appraisalBasis" size="small"
              @change="state.updateCell($index, 'appraisalBasis', row.appraisalBasis)" />
            <span v-else>{{ row.appraisalBasis || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="supportingDocs" label="支持性文件" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.supportingDocs" size="small"
              :placeholder="getEvidenceHint(row.changeType)"
              @change="state.updateCell($index, 'supportingDocs', row.supportingDocs)" />
            <span v-else>{{ row.supportingDocs || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对内容" align="center">
          <el-table-column v-for="(item, ci) in H3_TEST_CONTENT_ITEMS" :key="ci"
            :label="String(ci + 1)" width="44" align="center">
            <template #default="{ row, $index }">
              <el-checkbox
                v-if="!isReadonly"
                :model-value="row.checks[`check${ci + 1}` as keyof typeof row.checks]"
                @change="state.updateCell($index, `checks.check${ci + 1}`, $event)"
              />
              <span v-else>{{ row.checks[`check${ci + 1}` as keyof typeof row.checks] ? '✓' : '' }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="indexRef" label="索引号" width="80">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
              @change="state.updateCell($index, 'indexRef', row.indexRef)" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isAbnormal" label="是否异常" width="80" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" v-model="row.isAbnormal" size="small" style="width:64px"
              @change="state.updateCell($index, 'isAbnormal', $event)">
              <el-option label="否" value="N" />
              <el-option label="是" value="Y" />
            </el-select>
            <el-tag v-else :type="row.isAbnormal === 'Y' ? 'danger' : 'success'" size="small">
              {{ row.isAbnormal === 'Y' ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="48" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleOcr($index)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注说明" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="state.updateCell($index, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="48" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 汇总行 -->
      <div class="summary-bar">
        <template v-if="isCost">
          <span>原值合计: <b class="amount-cell">{{ fmtAmt(state.totalOriginalCost.value) }}</b></span>
          <span>净值合计: <b class="amount-cell">{{ fmtAmt(state.totalNetValue.value) }}</b></span>
        </template>
        <template v-else>
          <span>公允价值合计: <b class="amount-cell">{{ fmtAmt(state.totalFairValue.value) }}</b></span>
          <span>公允变动合计: <b class="amount-cell">{{ fmtAmt(state.totalFairChange.value) }}</b></span>
        </template>
        <span>本期新增合计: <b class="amount-cell">{{ fmtAmt(effectivePopulation) }}</b></span>
        <span>样本检查金额: <b class="amount-cell">{{ fmtAmt(state.summary.value.checkedAmount) }}</b></span>
        <span :class="{ 'warn-coverage': state.summary.value.coverageRate < 20 && effectivePopulation > 0 }">
          检查比例: <b>{{ state.summary.value.coverageRate.toFixed(2) }}%</b>
        </span>
        <span>异常: <b :class="{ 'error-amount': state.summary.value.anomalyCount > 0 }">{{ state.summary.value.anomalyCount }}</b> 项</span>
      </div>
      <el-alert
        v-if="state.summary.value.coverageRate < 20 && effectivePopulation > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        title="检查比例偏低：请扩大样本量，或在四、审计说明中解释原因。"
      />
      <el-alert
        v-if="state.summary.value.incompleteCheckCount > 0"
        type="info"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.incompleteCheckCount} 笔核对内容 1–4 未全部勾选，请补充测试记录。`"
      />
    </el-card>

    <!-- 三-B、证→账追查（完整性） -->
    <el-card id="h3-5-trace-section" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三-B、证→账追查明细（完整性 · {{ state.traceRows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSeedTrace">从账→证样本生成</el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="state.addTraceRow()">+ 追查行</el-button>
          </div>
        </div>
      </template>
      <p class="trace-hint">
        从合同/发票/验收报告/评估报告等源文件追查至投资性房地产账面：是否入账、金额是否一致。未入账或差额须跟进。
      </p>
      <el-table
        :data="state.traceRows.value"
        border stripe size="small" max-height="360" class="check-table"
        :row-class-name="traceTableRowClass"
      >
        <el-table-column type="index" label="序号" width="48" align="center" />
        <el-table-column prop="sourceType" label="源文件类型" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.sourceType" size="small" style="width:98px"
              @change="state.updateTraceCell(row.rowId, 'sourceType', $event)">
              <el-option v-for="t in H3_TRACE_SOURCE_OPTS" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.sourceType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceRef" label="源文件编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.sourceRef" size="small"
              @change="state.updateTraceCell(row.rowId, 'sourceRef', row.sourceRef)" />
            <span v-else>{{ row.sourceRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceDate" label="源文件日期" width="118">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.sourceDate" type="date" size="small"
              value-format="YYYY-MM-DD" style="width:108px"
              @change="state.updateTraceCell(row.rowId, 'sourceDate', $event)" />
            <span v-else>{{ row.sourceDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceParty" label="对方名称" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.sourceParty" size="small"
              @change="state.updateTraceCell(row.rowId, 'sourceParty', row.sourceParty)" />
            <span v-else>{{ row.sourceParty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceAmount" label="源文件金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.sourceAmount" :controls="false" size="small"
              class="amt-input" @change="state.updateTraceCell(row.rowId, 'sourceAmount', row.sourceAmount)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.sourceAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recordedInBooks" label="已入账" width="80" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.recordedInBooks" size="small" style="width:64px"
              @change="state.updateTraceCell(row.rowId, 'recordedInBooks', $event)">
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <el-tag v-else :type="row.recordedInBooks === 'N' ? 'danger' : 'success'" size="small">
              {{ row.recordedInBooks === 'Y' ? '是' : row.recordedInBooks === 'N' ? '否' : '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="bookVoucherNo" label="账面凭证号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.bookVoucherNo" size="small"
              @change="state.updateTraceCell(row.rowId, 'bookVoucherNo', row.bookVoucherNo)" />
            <span v-else>{{ row.bookVoucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAssetName" label="账面资产" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.bookAssetName" size="small"
              @change="state.updateTraceCell(row.rowId, 'bookAssetName', row.bookAssetName)" />
            <span v-else>{{ row.bookAssetName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAmount" label="账面金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookAmount" :controls="false" size="small"
              class="amt-input" @change="state.updateTraceCell(row.rowId, 'bookAmount', row.bookAmount)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差额" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.amountDiff) > 1 }]"
              title="差额=源文件金额−账面金额">{{ fmtAmt(row.amountDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="checkResult" label="结果" width="72" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.checkResult" size="small" style="width:60px"
              @change="state.updateTraceCell(row.rowId, 'checkResult', $event)">
              <el-option label="OK" value="OK" />
              <el-option label="异常" value="ERR" />
            </el-select>
            <el-tag v-else :type="row.checkResult === 'OK' ? 'success' : row.checkResult === 'ERR' ? 'danger' : 'info'" size="small">
              {{ row.checkResult || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="indexRef" label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
              @change="state.updateTraceCell(row.rowId, 'indexRef', row.indexRef)" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="H3-12" width="92" align="center">
          <template #default="{ row }">
            <el-button
              v-if="titleForTrace(row)"
              size="small"
              link
              type="primary"
              @click="goToTitleRow(row)"
            >产权{{ titleLinkLabel(row) }}</el-button>
            <el-tag v-else-if="isTitleCertTrace(row)" size="small" type="warning">待核对</el-tag>
            <span v-else class="muted-link">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="state.updateTraceCell(row.rowId, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="48">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeTraceRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>追查笔数: <b>{{ state.summary.value.traceCount }}</b></span>
        <span>未入账/异常:
          <b :class="{ 'error-amount': state.summary.value.traceUnrecordedCount > 0 }">
            {{ state.summary.value.traceUnrecordedCount }}
          </b> 项
        </span>
      </div>
      <el-alert
        v-if="state.summary.value.traceUnrecordedCount > 0"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`有 ${state.summary.value.traceUnrecordedCount} 笔证→账追查未入账或结果异常，请跟进完整性认定。`"
      />
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>四、审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI(reviewSection)">AI</el-button>
            <el-button size="small" circle @click="openReview(reviewSection)">💬</el-button>
          </span>
        </div>
      </template>
      <el-input
        :model-value="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :placeholder="auditNotePlaceholder"
        :disabled="isReadonly"
        @change="state.saveAuditNote($event)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>五、审计结论</span></div>
      </template>
      <el-input
        :model-value="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :placeholder="auditConclusionPlaceholder"
        :disabled="isReadonly"
        @change="state.saveAuditConclusion($event)"
      />
    </el-card>

    <!-- 抽凭引擎 Dialog（科目 1503 投资性房地产） -->
    <el-dialog v-model="samplingVisible" title="⚡ 抽凭引擎 — 投资性房地产(1503) 增减测试" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="1503"
        phase="final"
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
 * H3TabAdditionCheck.vue — H3-5 增减检查表（成本/公允统一组件）
 * 对齐致同模板：目标→样本选取→测试→说明→结论
 */
import { computed, inject, ref, toRef, onMounted, nextTick, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH3AdditionCheck,
  H3_CHANGE_TYPE_OPTS,
  H3_CATEGORY_OPTS,
  H3_TEST_CONTENT_ITEMS,
  H3_TRACE_SOURCE_OPTS,
  SAMPLING_METHOD_OPTS,
  getEvidenceHint,
  type H3AdditionMode,
  type H3TestReason,
  type H3TraceRow,
} from '../../composables/useH3AdditionCheck'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3ImportExport, resolveH35ImportSheet } from '../../composables/useH3ImportExport'
import { H3RowNavigationKey } from '../../composables/useH3RowNavigation'
import { isTitleCertTraceSource } from '../../composables/h3AdditionTitleLink'
import type { TitleRow } from '../../composables/h3TitleRowModel'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  measurementModel: H3AdditionMode | string
  year?: number
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})
const h3Nav = inject(H3RowNavigationKey, null)

const measurementModelRef = toRef(props, 'measurementModel')
const measurementModelTyped = computed(() =>
  props.measurementModel === 'fair_value' ? 'fair_value' as const : 'cost' as const,
)

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: measurementModelRef as any,
})

const state = useH3AdditionCheck({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue,
  setValue,
  saveImmediate,
  measurementModel: measurementModelRef,
})

const { exportTemplate, exportData, importData, importing } = useH3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: measurementModelTyped,
  onImported: () => state.loadRows(),
})

const vouchFileInputRef = ref<HTMLInputElement | null>(null)
const traceFileInputRef = ref<HTMLInputElement | null>(null)

const isCost = computed(() => props.measurementModel !== 'fair_value')
const modeLabel = computed(() => (isCost.value ? '成本模式' : '公允价值模式'))
const activeRowCount = computed(() => (isCost.value ? state.costRows.value.length : state.fairRows.value.length))
const reviewSection = computed(() => (isCost.value ? 'H3-5-cost' : 'H3-5-fair'))
const effectivePopulation = computed(() =>
  state.samplingParams.value.totalPopulation || state.linkedMovement.value.increaseAmount,
)
const coverageTagType = computed(() => {
  const rate = state.summary.value.coverageRate
  if (effectivePopulation.value <= 0) return 'info'
  return rate >= 20 ? 'success' : 'warning'
})

const auditNotePlaceholder = computed(() =>
  isCost.value
    ? '填写审计说明：增减变动检查范围、证据核对情况、资本化划分、异常事项及处理。'
    : '填写审计说明：增减变动检查范围、公允价值来源核对、评估依据、异常事项及处理。',
)
const auditConclusionPlaceholder = computed(() =>
  isCost.value
    ? 'A、增减变动真实准确、证据充分。B、除下列事项外未见异常。C、存在重大问题，不可确认。'
    : 'A、增减变动真实准确、公允计量恰当。B、除下列事项外未见异常。C、存在重大问题，不可确认。',
)

function onTestReasonsChange(val: string[] | number[]) {
  state.updateTestReasons(val as H3TestReason[])
}

function isTitleCertTrace(row: H3TraceRow): boolean {
  return isTitleCertTraceSource(row)
}

function titleForTrace(row: H3TraceRow): TitleRow | undefined {
  return state.resolveTitleForTrace(row.rowId)
}

function titleLinkLabel(row: H3TraceRow): string {
  const t = titleForTrace(row)
  if (!t) return ''
  return row.linkedTitleRowId ? '✓' : '→'
}

function goToTitleRow(row: H3TraceRow) {
  const title = titleForTrace(row)
  if (!title || !h3Nav) {
    ElMessage.info('未匹配到 H3-12 产权行，请先在产权核对表维护或从 H3-2 联动')
    return
  }
  state.linkTraceToTitle(row.rowId, title.rowId)
  h3Nav.navigateToRow({
    sheet: 'H3-12',
    rowId: title.rowId,
    assetName: title.assetName,
    titleCertNo: title.titleCertNo,
    sourceRef: row.sourceRef,
  })
}

function traceTableRowClass(ctx: { row: H3TraceRow }): string {
  const parts = [state.traceRowClassName(ctx)]
  const hl = h3Nav?.rowHighlightClass(ctx.row.rowId)
  if (hl) parts.push(hl)
  return parts.filter(Boolean).join(' ')
}

onMounted(() => {
  const focus = h3Nav?.consumeFocus('H3-5')
  if (focus?.section === 'trace') {
    nextTick(() => {
      document.getElementById('h3-5-trace-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }
})

function handleSeedTrace() {
  const n = state.seedTraceFromVouchRows()
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已生成 ${n} 条追查线索` : '无可生成的追查线索（请先在账→证样本填写支持性文件或凭证号）')
}

async function handleExportCmd(cmd: string) {
  const vouchSheet = resolveH35ImportSheet(measurementModelTyped.value, 'vouch')
  const traceSheet = resolveH35ImportSheet(measurementModelTyped.value, 'trace')
  if (cmd === 'vouch-export-template') await exportTemplate(vouchSheet)
  else if (cmd === 'vouch-export-data') await exportData(vouchSheet)
  else if (cmd === 'vouch-import-data') vouchFileInputRef.value?.click()
  else if (cmd === 'trace-export-template') await exportTemplate(traceSheet)
  else if (cmd === 'trace-export-data') await exportData(traceSheet)
  else if (cmd === 'trace-import-data') traceFileInputRef.value?.click()
}

async function onVouchFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  const sheet = resolveH35ImportSheet(measurementModelTyped.value, 'vouch')
  await importData(sheet, file)
}

async function onTraceFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  const sheet = resolveH35ImportSheet(measurementModelTyped.value, 'trace')
  await importData(sheet, file)
}

const samplingVisible = ref(false)
const samplingYear = computed(() => props.year ?? new Date().getFullYear())
function openSampling() { samplingVisible.value = true }
function onSamplesFilled(payload: { samples?: any[] }) {
  const n = state.fillFromSampledVouchers(payload?.samples ?? [])
  samplingVisible.value = false
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已回填 ${n} 笔抽样凭证到增减检查行` : '未回填新凭证（可能已存在或无样本）')
}

async function handleOcr(index: number) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.jpg,.jpeg,.png,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const ocrData = res.data?.data ?? res.data
      if (!ocrData) return
      await ElMessageBox.confirm(
        `OCR 识别结果：\n金额: ${ocrData.amount ?? '-'}\n日期: ${ocrData.date ?? '-'}\n对方: ${ocrData.counterparty ?? '-'}\n\n确认填入第 ${index + 1} 行？`,
        'OCR 识别结果确认',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      if (isCost.value) {
        const row = state.costRows.value[index]
        if (row) {
          if (ocrData.amount) state.updateCell(index, 'originalCost', ocrData.amount)
          if (ocrData.date) state.updateCell(index, 'date', ocrData.date)
          if (ocrData.counterparty) state.updateCell(index, 'assetName', ocrData.counterparty)
        }
      } else {
        const row = state.fairRows.value[index]
        if (row) {
          if (ocrData.amount) state.updateCell(index, 'fairValue', ocrData.amount)
          if (ocrData.date) state.updateCell(index, 'date', ocrData.date)
          if (ocrData.counterparty) state.updateCell(index, 'assetName', ocrData.counterparty)
        }
      }
    } catch (err: any) {
      if (err === 'cancel' || err?.toString?.().includes('cancel')) return
      console.warn('[H3-5 OCR]', err)
    }
  }
  input.click()
}

function fmtAmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}
function openReview(section: string) { openReviewDialog(section) }
function navigateTo(sheet: string) { emit('navigate-sheet', sheet) }
</script>

<style scoped>
.h3-tab-addition-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; }
.obj-list { margin: 4px 0 0 20px; padding: 0; line-height: 1.7; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.block-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; font-weight: 500; }
.title-actions { display: flex; gap: 4px; align-items: center; }
.test-reason-row { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.reason-label { font-weight: 500; margin-right: 8px; white-space: nowrap; }
.test-content-hint { background: var(--el-fill-color-lighter); padding: 8px 12px; border-radius: 4px; font-size: 12px; color: #606266; }
.test-content-hint ol { margin: 4px 0 0 20px; padding: 0; line-height: 1.6; }
.hint-note { margin: 8px 0 0; color: var(--el-text-color-secondary); }
.trace-hint { margin: 0 0 10px; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.6; }
.check-table :deep(.row-warn) { background-color: #fdf6ec !important; }
.check-table :deep(.h3-row-deeplink-hl) { animation: h3-row-flash 1.2s ease-in-out 0s 2; }
.check-table :deep(.h3-row-deeplink-hl > td) { background-color: #ecf5ff !important; }
@keyframes h3-row-flash {
  0%, 100% { background-color: transparent; }
  50% { background-color: #d9ecff; }
}
.muted-link { color: var(--el-text-color-placeholder); }
.sampling-actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.pop-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.src-tag { margin-left: 4px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.check-table :deep(.row-anomaly) { background-color: #fef0f0 !important; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.summary-bar { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.warn-coverage { color: var(--el-color-warning); }
.error-amount { color: var(--el-color-danger); }
.audit-note-card { margin-top: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.action-btns { display: flex; gap: 4px; }
</style>
