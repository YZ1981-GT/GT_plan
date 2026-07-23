<!--
  I6TabTargetedCheck.vue — I6-4 研发费用针对性检查表

  对齐致同 Excel：一目标 / 二抽样(测试原因) / 三凭证核对 / 四说明 / 五结论
  原段落型费用归集/人员分摊/I2划分保留为可选「专项风险关注」
-->
<template>
  <div class="i6-targeted-check">
    <div class="section-header">
      <span class="section-title">I6-4 研发费用针对性检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、测试目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I6_4_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        勾选测试原因 → 界定测试总体与特定样本 → 抽样（IDEA/抽凭引擎）→ 逐笔核对凭证与支持性文件（核对内容 1~5）→
        异常标注 → 形成说明与结论。检查比例＝样本借方合计 ÷ 本期发生额（联动 I6-2 审定合计；总体为 0 时显示 N/A，避免 #DIV/0!）。
        费用归集完整性、人员工时认定、I2 资本化划分等专题程序见 I2/I6 其他底稿及下方「专项风险关注」。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I6-4" :context-project-id="projectId" />
        <span
          v-if="i2Linkage && !i2Linkage.ready"
          class="linkage-info"
        >
          I2 资本化数据未同步
        </span>
        <span
          v-else-if="i2Linkage && !i2Linkage.isBalanced"
          class="linkage-warn"
        >
          VR-I6-01 不平衡（差额 {{ fmtNum(i2Linkage.difference) }}）
        </span>
        <span
          v-else-if="i2Linkage"
          class="linkage-ok"
        >
          ✓ VR-I6-01 已核对
        </span>
        <GtIndexChip value="I2" @click="emit('navigate-sheet', 'I2')" />
        <el-tag size="small" type="info">样本 {{ summary.sampleCount }} 笔</el-tag>
        <el-tag v-if="summary.specificCount" size="small" type="warning">特定 {{ summary.specificCount }}</el-tag>
        <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">异常 {{ summary.anomalyCount }}</el-tag>
        <el-tag v-if="summary.failCheckCount > 0" size="small" type="danger">核对× {{ summary.failCheckCount }}</el-tag>
        <el-tag v-if="summary.pendingCount > 0" size="small" type="warning">未完成 {{ summary.pendingCount }}</el-tag>
        <el-tag
          v-if="projectConsistency.catalogCount && projectConsistency.unmatchedCount"
          size="small"
          type="danger"
        >
          项目不在 I6-2 {{ projectConsistency.unmatchedCount }}
        </el-tag>
        <el-tag
          v-if="projectConsistency.catalogCount && projectConsistency.missingProjectCount"
          size="small"
          type="warning"
        >
          未填项目 {{ projectConsistency.missingProjectCount }}
        </el-tag>
        <el-tag size="small" :type="coverageTagType">检查比例 {{ coverageLabel }}</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I6-2')">← I6-2</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I6-5')">I6-5 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="coverageLow"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      title="检查比例偏低：请扩大样本量，或在四、审计说明中解释原因。"
    />

    <el-alert
      v-if="projectConsistency.catalogCount && (projectConsistency.unmatchedCount || projectConsistency.missingProjectCount)"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
    >
      <template #title>研发项目与 I6-2 明细不一致</template>
      <template #default>
        <p v-if="projectConsistency.unmatchedCount">
          {{ projectConsistency.unmatchedCount }} 笔样本的项目名称不在 I6-2 明细中
          <span v-if="projectConsistency.orphanNames.length">
            （{{ projectConsistency.orphanNames.slice(0, 3).join('、') }}<template v-if="projectConsistency.orphanNames.length > 3"> 等</template>）
          </span>
          — 请核对或点击「挂接 I6-2 项目」。
        </p>
        <p v-if="projectConsistency.missingProjectCount">
          {{ projectConsistency.missingProjectCount }} 笔样本未填写研发项目明细，建议对照 I6-2 补全后再评价核对 5。
        </p>
      </template>
    </el-alert>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、样本选取标准与规模</span>
          <div class="title-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedPeriod.debitTotal > 0)"
              @click="handleSyncPopulation"
            >
              从 I6-2 带入本期发生额
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>

      <div class="test-content-hint">
        <p>测试原因（Excel 勾选）：</p>
        <el-checkbox-group
          v-model="sampleMeta.testReasons"
          :disabled="isReadonly"
          class="reason-group"
        >
          <el-checkbox v-for="r in I6_4_TEST_REASONS" :key="r" :label="r" />
        </el-checkbox-group>
      </div>

      <div class="test-content-hint">
        <p>测试内容说明（第三节「核对内容」列）：</p>
        <ol>
          <li v-for="(item, i) in I6_4_TEST_CONTENT" :key="i">{{ i + 1 }}. {{ item }}</li>
        </ol>
      </div>

      <el-descriptions :column="2" border size="small" class="sample-desc">
        <el-descriptions-item label="测试总体">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.populationDesc"
            size="small"
            placeholder="6602 研发费用借方发生额总体"
          />
          <span v-else>{{ sampleMeta.populationDesc }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="总体笔数 / 借方金额">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              v-model="sampleMeta.populationCount"
              :controls="false"
              size="small"
              :min="0"
              style="width:80px"
            />
            <span v-else>{{ sampleMeta.populationCount || '—' }}</span>
            <span class="sep">笔 /</span>
            <el-input-number
              v-if="!isReadonly"
              :model-value="sampleMeta.populationAmount"
              :controls="false"
              size="small"
              :precision="2"
              @change="(v: number | undefined) => setPopulationAmount(v ?? 0, true)"
            />
            <span v-else class="amt">{{ fmtNum(sampleMeta.populationAmount) }}</span>
            <el-tag v-if="linkedPeriod.source" size="small" type="info">
              源 {{ linkedPeriod.source }}
            </el-tag>
            <el-tag v-if="sampleMeta.populationManual" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="本期贷方发生额">
          <el-input-number
            v-if="!isReadonly"
            v-model="sampleMeta.populationCreditAmount"
            :controls="false"
            size="small"
            :precision="2"
          />
          <span v-else class="amt">{{ fmtNum(sampleMeta.populationCreditAmount) }}</span>
          <span class="hint">（冲回/重分类等；贷方检查比例 {{ creditCoverageLabel }}）</span>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本（100%检查）">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.specificSample"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="大额、关联方、委外研发、资本化相关…"
          />
          <span v-else>{{ sampleMeta.specificSample }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本金额">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              v-model="sampleMeta.specificAmount"
              :controls="false"
              size="small"
              :precision="2"
            />
            <span v-else class="amt">{{ fmtNum(sampleMeta.specificAmount) }}</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              text
              type="primary"
              :disabled="!summary.specificCount"
              @click="handleSyncSpecificAmount"
            >
              从表内特定样本同步
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="抽样总体">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.samplingPopulationDesc"
            size="small"
            placeholder="剔除特定样本后的剩余总体"
          />
          <span v-else>{{ sampleMeta.samplingPopulationDesc }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样样本量">
          <el-input-number
            v-if="!isReadonly"
            v-model="sampleMeta.sampleSize"
            :controls="false"
            size="small"
            :min="0"
          />
          <span v-else>{{ sampleMeta.sampleSize || summary.sampleCount }}</span>
          <span class="hint">（表内样本 {{ summary.sampleCount }} 笔）</span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法 / 过程">
          <div class="method-cell">
            <el-select
              v-if="!isReadonly"
              v-model="sampleMeta.sampleMethod"
              size="small"
              filterable
              allow-create
              style="width: 140px"
            >
              <el-option v-for="m in I6_4_SAMPLE_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ sampleMeta.sampleMethod }}</span>
            <el-input
              v-if="!isReadonly"
              v-model="sampleMeta.sampleProcess"
              size="small"
              placeholder="抽样过程说明或索引其他底稿…"
              style="flex:1"
            />
            <span v-else>{{ sampleMeta.sampleProcess || '—' }}</span>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="检查合计 / 比例">
          <span class="amt">借 {{ fmtNum(summary.checkedDebitTotal) }}</span>
          <span class="sep">/</span>
          <span :class="{ 'warn-coverage': coverageLow }">{{ coverageLabel }}</span>
          <span class="sep">本期 {{ fmtNum(coverageFooter.periodDebitTotal) }}</span>
          <span class="sep">阈值</span>
          <el-input-number
            v-if="!isReadonly"
            v-model="sampleMeta.coverageThreshold"
            :min="1"
            :max="100"
            :controls="false"
            size="small"
            style="width:72px"
          />
          <span v-else>{{ sampleMeta.coverageThreshold }}%</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 三、测试 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>三、测试 — 记账凭证核对</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly || !i62ProjectNames.length" @click="handleLinkProjects">
              挂接 I6-2 项目
            </el-button>
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rows"
        border
        stripe
        size="small"
        class="check-table"
        max-height="520"
        :row-class-name="rowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="#" width="40" align="center" fixed />
        <el-table-column label="层" width="56" align="center" fixed>
          <template #default="{ row }">
            <el-tag v-if="row.isSpecific || row.selectionReason" size="small" type="warning">特定</el-tag>
            <el-tag v-else size="small" type="info">抽样</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="选取原因" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.selectionReason"
              size="small"
              clearable
              filterable
              allow-create
              placeholder="抽样"
              @change="(v: string) => updateRow(row.rowId, 'selectionReason', v || '')"
            >
              <el-option v-for="r in I6_4_TEST_REASONS" :key="r" :label="r" :value="r" />
            </el-select>
            <span v-else>{{ row.selectionReason || '抽样' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="研发项目明细" min-width="130" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.projectName"
              size="small"
              filterable
              allow-create
              clearable
              placeholder="对照 I6-2"
              style="width:100%"
              @change="(v: string) => updateRow(row.rowId, 'projectName', v || '')"
            >
              <el-option v-for="n in i62ProjectNames" :key="n" :label="n" :value="n" />
            </el-select>
            <span v-else>{{ row.projectName || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="凭证日期" width="118">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.voucherDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => updateRow(row.rowId, 'voucherDate', v || '')"
            />
            <span v-else>{{ row.voucherDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="凭证号" min-width="90">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherNo"
              size="small"
              @update:model-value="(v: string) => updateRow(row.rowId, 'voucherNo', v)"
            />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="业务内容" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.businessDesc"
              size="small"
              @update:model-value="(v: string) => updateRow(row.rowId, 'businessDesc', v)"
            />
            <span v-else>{{ row.businessDesc || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="对方科目" min-width="95">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.counterpartAccount"
              size="small"
              @update:model-value="(v: string) => updateRow(row.rowId, 'counterpartAccount', v)"
            />
            <span v-else>{{ row.counterpartAccount || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="对方明细科目" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.counterpartDetail"
              size="small"
              @update:model-value="(v: string) => updateRow(row.rowId, 'counterpartDetail', v)"
            />
            <span v-else>{{ row.counterpartDetail || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="借方金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.debitAmount"
              size="small"
              :controls="false"
              :precision="2"
              class="amt-input"
              @change="(v: number | undefined) => updateRow(row.rowId, 'debitAmount', v ?? 0)"
            />
            <span v-else class="amt">{{ fmtNum(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="支持性文件" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.supportingDocs"
              size="small"
              placeholder="合同/发票/工时表…"
              @update:model-value="(v: string) => updateRow(row.rowId, 'supportingDocs', v)"
            />
            <span v-else>{{ row.supportingDocs || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-for="ci in 5"
          :key="ci"
          :label="`核对${ci}`"
          width="72"
          align="center"
        >
          <template #header>
            <el-tooltip :content="I6_4_TEST_CONTENT[ci - 1]" placement="top">
              <span class="check-h">{{ ci }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row[`check${ci}` as keyof typeof row]"
              size="small"
              clearable
              @change="(v: string) => updateRow(row.rowId, `check${ci}` as any, v || '')"
            >
              <el-option v-for="o in checkOpts" :key="o || 'empty'" :label="o || '—'" :value="o" />
            </el-select>
            <span v-else :class="checkClass(String(row[`check${ci}` as keyof typeof row] || ''))">
              {{ row[`check${ci}` as keyof typeof row] || '—' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="索引号" min-width="80">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              @update:model-value="(v: string) => updateRow(row.rowId, 'indexRef', v)"
            />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否异常" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.isAbnormal"
              size="small"
              clearable
              filterable
              allow-create
              :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }"
              @change="(v: string) => updateRow(row.rowId, 'isAbnormal', v || '')"
            >
              <el-option v-for="o in I6_4_ABNORMAL_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }">{{ row.isAbnormal || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="备注说明" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              @update:model-value="(v: string) => updateRow(row.rowId, 'remark', v)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="footer-hint">
        表尾：合计 {{ fmtNum(coverageFooter.checkedDebitTotal) }} /
        本期发生额 {{ fmtNum(coverageFooter.periodDebitTotal) }} /
        检查比例 <span :class="{ 'warn-coverage': coverageLow }">{{ coverageFooter.debitCoverageLabel }}</span>
      </div>
    </el-card>

    <!-- 专项风险关注（兼容原段落型） -->
    <el-card shadow="never" class="block-card risk-card">
      <template #header>
        <div class="block-title">
          <span>专项风险关注（可选）</span>
          <el-tag size="small" type="info">费用归集 / 人员分摊 / I2划分 → 详见 I2-9/I2-10/I2-6</el-tag>
        </div>
      </template>
      <el-alert
        v-if="riskFocus.legacyDeductionNote"
        type="info"
        :closable="false"
        show-icon
        class="legacy-alert"
        :title="riskFocus.legacyDeductionNote.split('\n')[0]"
      >
        <pre class="legacy-pre">{{ riskFocus.legacyDeductionNote }}</pre>
      </el-alert>
      <el-row :gutter="12">
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">费用归集完整性</div>
            <el-input
              v-model="riskFocus.completeness"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="立项覆盖、应归未归、科目错配…"
              @blur="saveRiskFocus"
            />
            <el-select
              v-model="riskFocus.completenessConclusion"
              size="small"
              :disabled="isReadonly"
              clearable
              placeholder="结论"
              class="mt-6"
              @change="saveRiskFocus"
            >
              <el-option label="归集完整" value="归集完整" />
              <el-option label="存在漏归/错归" value="存在漏归/错归" />
              <el-option label="待核实" value="待核实" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">人员费用分摊</div>
            <el-input
              v-model="riskFocus.allocation"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="研发人员名单、工时依据、分摊方法…"
              @blur="saveRiskFocus"
            />
            <el-select
              v-model="riskFocus.allocationConclusion"
              size="small"
              :disabled="isReadonly"
              clearable
              placeholder="结论"
              class="mt-6"
              @change="saveRiskFocus"
            >
              <el-option label="分摊合理" value="分摊合理" />
              <el-option label="分摊依据不足" value="分摊依据不足" />
              <el-option label="待核实" value="待核实" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">与 I2 划分一致性（VR-I6-01）</div>
            <el-input
              v-model="riskFocus.i2Consistency"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="研究/开发阶段划分、费用化+资本化=研发总额…"
              @blur="saveRiskFocus"
            />
            <el-select
              v-model="riskFocus.i2ConsistencyConclusion"
              size="small"
              :disabled="isReadonly"
              clearable
              placeholder="结论"
              class="mt-6"
              @change="saveRiskFocus"
            >
              <el-option label="划分一致" value="划分一致" />
              <el-option label="存在划分差异" value="存在划分差异" />
              <el-option label="待核实" value="待核实" />
            </el-select>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="conclusion-header">
          <span>四、审计说明</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly && adjDrafts.length"
              size="small"
              text
              type="danger"
              @click="handleAdjDraft"
            >
              写入调整草稿（×{{ adjDrafts.length }}）
            </el-button>
            <el-button
              v-if="!isReadonly && pushableAdjDrafts.length"
              size="small"
              text
              type="warning"
              @click="handlePushI63"
            >
              推送 I6-3（{{ pushableAdjDrafts.length }}）
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录抽样过程、异常处理、与 I6-2 / I2 交叉印证情况…"
        @change="(v: string) => saveNote(v)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span>五、审计结论</span>
          <el-button v-if="!isReadonly" size="small" text type="primary" @click="handleFillDraft">生成草稿</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="针对性检查是否达成测试目标；研发费用在重大方面是否恰当…"
        @change="(v: string) => saveConclusion(v)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示（对齐 Excel I6-4）</summary>
      <ol>
        <li>先勾选测试原因并填第二节总体，再抽样本填入第三节；检查比例=样本借方÷本期发生额（联动 I6-2，总体为 0 显示 N/A）。</li>
        <li>核对 1~5 对应测试内容说明；选「×」时可写入调整建议或一键推送 I6-3（资本化/跨期类）。</li>
        <li>加计扣除测算不属于本表，请编制 N5-6-1 并与 I2 政策检查交叉核对。</li>
        <li>人员认定见 I2-9，工时检查见 I2-10；资本化划分见 I2-6。专项风险关注区可记载段落结论。</li>
      </ol>
    </details>

    <el-dialog
      v-model="samplingVisible"
      title="抽凭引擎 — 研发费用(6602) 针对性检查"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="6602"
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
import { computed, inject, ref, toRef, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI6TargetedCheck,
  I6_4_OBJECTIVES,
  I6_4_TEST_CONTENT,
  I6_4_TEST_REASONS,
  I6_4_SAMPLE_METHODS,
  I6_4_CHECK_OPTIONS,
  I6_4_ABNORMAL_OPTIONS,
  isAbnormalFlag,
  hasFailedCheck,
} from '../../composables/useI6TargetedCheck'
import type { I2LinkageStatus } from '../../composables/useI6CrossSheet'

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
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})
const i6CrossSheet = inject<{ i2LinkageStatus: { value: I2LinkageStatus } } | null>('i6CrossSheet', null)
const i2Linkage = computed(() => i6CrossSheet?.i2LinkageStatus.value ?? null)

const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)
const checkOpts = I6_4_CHECK_OPTIONS.filter((o) => o !== '') as string[]
const samplingVisible = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())
const asOfYear = computed(() => props.year || new Date().getFullYear())

const allResponsesRef = toRef(props, 'allResponses')

const {
  rows,
  sampleMeta,
  riskFocus,
  auditNote,
  auditConclusion,
  summary,
  coverageLow,
  coverageLabel,
  creditCoverageLabel,
  coverageFooter,
  coverageTagType,
  linkedPeriod,
  adjDrafts,
  pushableAdjDrafts,
  i62ProjectNames,
  projectConsistency,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  linkProjectsFromI62,
  setPopulationAmount,
  syncPopulationFromI62,
  syncSpecificAmount,
  appendAdjDraftsToNote,
  pushAdjDraftsToI63,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
  saveRiskFocus,
} = useI6TargetedCheck(allResponsesRef, {
  onSave: (itemId, value) => emit('save', itemId, value),
  asOfYear,
})

function fmtNum(v: number): string {
  return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function checkClass(v: string) {
  if (v === '×') return 'check-fail'
  if (v === '√') return 'check-ok'
  return ''
}

function rowClassName({ row }: { row: any }) {
  if (isAbnormalFlag(row.isAbnormal) || hasFailedCheck(row)) return 'anomaly-row'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  const s = summary.value
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const label = String(col.label || '')
    if (label.includes('借方')) return fmtNum(s.checkedDebitTotal)
    return ''
  })
}

function handleAddRow() {
  addRow()
}

function handleSyncPopulation() {
  const r = syncPopulationFromI62()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSyncSpecificAmount() {
  const r = syncSpecificAmount()
  ElMessage.success(r.message)
}

function handleLinkProjects() {
  const r = linkProjectsFromI62(false)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSampling() {
  samplingVisible.value = true
}

function onSamplesFilled(samples: any[]) {
  const n = fillFromSampledVouchers(samples)
  samplingVisible.value = false
  if (n > 0) {
    ElMessage.success(`已填入 ${n} 笔样本`)
    persistAll()
  } else {
    ElMessage.info('无新样本（可能已全部存在）')
  }
}

async function handleSave() {
  await persistAll()
  ElMessage.success('已保存 I6-4')
}

function handleAdjDraft() {
  const r = appendAdjDraftsToNote()
  if (r.ok) {
    void saveNote(auditNote.value)
    ElMessage.success(r.message)
  } else {
    ElMessage.warning(r.message)
  }
}

async function handlePushI63() {
  try {
    await ElMessageBox.confirm(
      `将把 ${pushableAdjDrafts.value.length} 条资本化/跨期草稿推送到 I6-3（跳过已有同说明）。是否继续？`,
      '推送至 I6-3',
      { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const r = await pushAdjDraftsToI63()
  if (r.ok) {
    ElMessage.success(r.message)
    emit('navigate-sheet', 'I6-3')
  } else {
    ElMessage.info(r.message)
  }
}

function handleFillDraft() {
  fillConclusionDraft()
  saveConclusion(auditConclusion.value)
  ElMessage.success('已生成结论草稿')
}

function handleReview() {
  openReviewDialog('I6-4 针对性检查')
}
</script>

<style scoped>
.i6-targeted-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 16px; font-weight: 600; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 20px; }
.methodology-context { background: #f0f9ff; border-left: 4px solid #0284c7; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; line-height: 1.7; }
.tab-toolbar { display: flex; justify-content: flex-end; margin-bottom: 12px; flex-wrap: wrap; gap: 6px; }
.toolbar-right { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.linkage-warn { font-size: 12px; color: #e6a23c; font-weight: 500; }
.linkage-info { font-size: 12px; color: var(--el-text-color-secondary); }
.linkage-ok { font-size: 12px; color: #67c23a; font-weight: 500; }
.check-alert { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.block-title { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-weight: 600; }
.title-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.test-content-hint { margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-regular); }
.test-content-hint ol { margin: 4px 0 0; padding-left: 20px; }
.reason-group { display: flex; flex-wrap: wrap; gap: 8px; }
.sample-desc { margin-top: 8px; }
.pop-cell { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.sep { color: var(--el-text-color-secondary); }
.amt { font-variant-numeric: tabular-nums; }
.hint { font-size: 11px; color: var(--el-text-color-secondary); margin-left: 4px; }
.method-cell { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.check-table { font-size: var(--wp-font-size, 13px); }
.check-h { cursor: help; border-bottom: 1px dashed #909399; }
.check-ok { color: #16a34a; font-weight: 600; }
.check-fail { color: #dc2626; font-weight: 600; }
.abnormal-cell { color: #dc2626; }
.anomaly-row { background: #fef2f2 !important; }
.amt-input { width: 100%; }
.warn-coverage { color: #dc2626; font-weight: 600; }
.footer-hint { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); text-align: right; }
.risk-card :deep(.el-card__header) { background: #fafafa; }
.risk-block { margin-bottom: 8px; }
.risk-title { font-weight: 600; margin-bottom: 6px; font-size: 13px; }
.mt-6 { margin-top: 6px; width: 100%; }
.legacy-alert { margin-bottom: 12px; }
.legacy-pre { white-space: pre-wrap; font-size: 12px; margin: 0; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; font-weight: 600; }
.header-actions { display: flex; gap: 4px; flex-wrap: wrap; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 20px; margin-top: 8px; }
</style>
