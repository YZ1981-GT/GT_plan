<!--
  I3TabTargetedCheck.vue — I3-5 商誉针对性检查表

  对齐致同 Excel：一目标 / 二抽样(测试原因) / 三凭证核对 / 四说明 / 五结论
  原段落型减值迹象·CGU 检查保留为可选「专项风险关注」（主程序见 I3-6~8）
-->
<template>
  <div class="i3-targeted-check">
    <div class="section-header">
      <span class="section-title">I3-5 商誉针对性检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、测试目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I3_5_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        勾选测试原因 → 界定测试总体与特定样本 → 抽样 → 逐笔核对凭证与支持性文件（核对内容 1~5）→
        异常标注 → 形成说明与结论。检查比例＝样本借方合计 ÷ 本期借方发生额（总体为 0 时显示 N/A，避免 #DIV/0!）。
        减值迹象识别与 CGU 划分的详细程序见 I3-6~I3-8；本表侧重商誉相关交易的综合抽凭。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I3-5" :context-project-id="projectId" />
        <el-tag size="small" type="info">样本 {{ summary.sampleCount }} 笔</el-tag>
        <el-tag v-if="summary.specificCount" size="small" type="warning">特定 {{ summary.specificCount }}</el-tag>
        <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">异常 {{ summary.anomalyCount }}</el-tag>
        <el-tag v-if="summary.failCheckCount > 0" size="small" type="danger">核对× {{ summary.failCheckCount }}</el-tag>
        <el-tag v-if="summary.pendingCount > 0" size="small" type="warning">未完成 {{ summary.pendingCount }}</el-tag>
        <el-tag size="small" :type="coverageTagType">检查比例 {{ coverageLabel }}</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I3-4')">← I3-4</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I3-6')">I3-6 →</el-button>
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

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、测试 — 样本选取标准与规模</span>
          <div class="title-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedPeriod.debitTotal > 0 || linkedPeriod.creditTotal > 0)"
              @click="handleSyncPopulation('period')"
            >
              从 I3-2 带入本期发生额
            </el-button>
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedPeriod.originalTotal > 0)"
              @click="handleSyncPopulation('original')"
            >
              带入原值合计
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
          <el-checkbox v-for="r in I3_5_TEST_REASONS" :key="r" :label="r" />
        </el-checkbox-group>
      </div>

      <div class="test-content-hint">
        <p>测试内容说明（第三节「核对内容」列）：</p>
        <ol>
          <li v-for="(item, i) in I3_5_TEST_CONTENT" :key="i">{{ i + 1 }}. {{ item }}</li>
        </ol>
      </div>

      <el-descriptions :column="2" border size="small" class="sample-desc">
        <el-descriptions-item label="测试总体">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.populationDesc"
            size="small"
            placeholder="账面商誉借方发生额总体"
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
          <span class="hint">（减值等；贷方检查比例 {{ creditCoverageLabel }}）</span>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本（100%检查）">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.specificSample"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="大额并购、关联方、异常减值…"
          />
          <span v-else>{{ sampleMeta.specificSample }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本金额">
          <el-input-number
            v-if="!isReadonly"
            v-model="sampleMeta.specificAmount"
            :controls="false"
            size="small"
            :precision="2"
          />
          <span v-else class="amt">{{ fmtNum(sampleMeta.specificAmount) }}</span>
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
              <el-option v-for="m in I3_5_SAMPLE_METHODS" :key="m" :label="m" :value="m" />
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
          <span class="sep">贷 {{ fmtNum(summary.checkedCreditTotal) }}</span>
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

        <el-table-column label="商誉项目明细" min-width="120" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.projectName"
              size="small"
              placeholder="被投资单位/CGU"
              @update:model-value="(v: string) => updateRow(row.rowId, 'projectName', v)"
            />
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

        <el-table-column label="业务内容" min-width="120">
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

        <el-table-column label="对方科目" min-width="100">
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

        <el-table-column label="对方明细" min-width="90">
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

        <el-table-column label="贷方金额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.creditAmount"
              size="small"
              :controls="false"
              :precision="2"
              class="amt-input"
              @change="(v: number | undefined) => updateRow(row.rowId, 'creditAmount', v ?? 0)"
            />
            <span v-else class="amt">{{ fmtNum(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="支持性文件" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.supportingDocs"
              size="small"
              placeholder="并购协议/评估报告…"
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
            <el-tooltip :content="I3_5_TEST_CONTENT[ci - 1]" placement="top">
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

        <el-table-column label="是否异常" width="100">
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
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
              <el-option label="入账差异" value="入账差异" />
              <el-option label="分摊不当" value="分摊不当" />
              <el-option label="跨期" value="跨期" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }">{{ row.isAbnormal || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="100">
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
    </el-card>

    <!-- 专项风险关注（兼容原段落型） -->
    <el-card shadow="never" class="block-card risk-card">
      <template #header>
        <div class="block-title">
          <span>专项风险关注（可选）</span>
          <el-tag size="small" type="info">减值迹象 / CGU 分摊 / 划分一致性 → 详见 I3-6~8</el-tag>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">减值迹象识别</div>
            <el-input
              v-model="riskFocus.externalIndicators"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="外部迹象：市价/环境/利率…"
            />
            <el-input
              v-model="riskFocus.internalIndicators"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              :disabled="isReadonly"
              placeholder="内部迹象：经营/重组/绩效…"
              class="mt-6"
            />
            <el-select v-model="riskFocus.externalConclusion" size="small" :disabled="isReadonly" clearable placeholder="外部结论" class="mt-6">
              <el-option label="无减值迹象" value="无减值迹象" />
              <el-option label="存在减值迹象" value="存在减值迹象" />
              <el-option label="需进一步判断" value="需进一步判断" />
              <el-option label="待确认" value="待确认" />
            </el-select>
            <el-select v-model="riskFocus.internalConclusion" size="small" :disabled="isReadonly" clearable placeholder="内部结论" class="mt-6">
              <el-option label="无减值迹象" value="无减值迹象" />
              <el-option label="存在减值迹象" value="存在减值迹象" />
              <el-option label="需进一步判断" value="需进一步判断" />
              <el-option label="待确认" value="待确认" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">商誉分摊至 CGU</div>
            <el-input
              v-model="riskFocus.cguAllocation"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="合并对价分摊、协同效应、管理层监控层级…"
            />
            <el-select v-model="riskFocus.allocationConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6">
              <el-option label="合理" value="合理" />
              <el-option label="不合理" value="不合理" />
              <el-option label="需调整" value="需调整" />
              <el-option label="待确认" value="待确认" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">CGU 划分一致性</div>
            <el-input
              v-model="riskFocus.cguConsistency"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="与上年一致、与内部报告一致、变更情况…"
            />
            <el-select v-model="riskFocus.consistencyConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6">
              <el-option label="一致" value="一致" />
              <el-option label="不一致但合理" value="不一致但合理" />
              <el-option label="不一致且不合理" value="不一致且不合理" />
              <el-option label="待确认" value="待确认" />
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
          <el-button
            v-if="!isReadonly && adjDrafts.length"
            size="small"
            text
            type="danger"
            @click="handleAdjDraft"
          >
            写入调整草稿（×{{ adjDrafts.length }}）
          </el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录抽样过程、异常处理、与 I3-4 / I3-6~8 交叉印证情况…"
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
        placeholder="针对性检查是否达成测试目标；商誉在重大方面是否恰当…"
        @change="(v: string) => saveConclusion(v)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示（对齐 Excel I3-5）</summary>
      <ol>
        <li>先勾选测试原因并填第二节总体，再抽样本填入第三节；检查比例=样本借方÷本期借方（总体为 0 显示 N/A）。</li>
        <li>无新并购时本期借方可为 0，可改用「带入原值合计」作存在性测试总体，并在说明中解释。</li>
        <li>核对 1~5 对应测试内容说明；选「×」时自动标记异常，并可写入调整建议草稿。</li>
        <li>入账价值测算见 I3-4；减值测试见 I3-6~8。专项风险关注区可记载迹象/CGU 段落结论。</li>
      </ol>
    </details>

    <el-dialog
      v-model="samplingVisible"
      title="抽凭引擎 — 商誉(1711) 针对性检查"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="1711"
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
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI3TargetedCheck,
  I3_5_OBJECTIVES,
  I3_5_TEST_CONTENT,
  I3_5_TEST_REASONS,
  I3_5_SAMPLE_METHODS,
  I3_5_CHECK_OPTIONS,
  isAbnormalFlag,
  hasFailedCheck,
} from '../../composables/useI3TargetedCheck'

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

const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)
const checkOpts = I3_5_CHECK_OPTIONS.filter((o) => o !== '') as string[]
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
  coverageTagType,
  linkedPeriod,
  adjDrafts,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  setPopulationAmount,
  syncPopulationFromI32,
  appendAdjDraftsToNote,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
} = useI3TargetedCheck(allResponsesRef, {
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
    if (label.includes('贷方')) return fmtNum(s.checkedCreditTotal)
    return ''
  })
}

function handleAddRow() {
  addRow()
}

function handleSyncPopulation(mode: 'period' | 'original') {
  const r = syncPopulationFromI32(mode)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSampling() {
  if (!props.wpId || !props.projectId) {
    ElMessage.warning('缺少工作底稿或项目上下文，无法打开抽凭引擎')
    return
  }
  samplingVisible.value = true
}

function onSamplesFilled(payload: { samples?: any[]; methodology?: any }) {
  const n = fillFromSampledVouchers(payload?.samples ?? [])
  const method = payload?.methodology?.samplingMethod
  if (method) sampleMeta.value.sampleMethod = String(method)
  if (payload?.methodology?.sampleSize) {
    sampleMeta.value.sampleSize = Number(payload.methodology.sampleSize) || sampleMeta.value.sampleSize
  }
  sampleMeta.value.sampleProcess = [
    sampleMeta.value.sampleProcess,
    `抽凭引擎回填 ${n} 笔（${new Date().toISOString().slice(0, 10)}）`,
  ].filter(Boolean).join('；')
  samplingVisible.value = false
  if (n > 0) ElMessage.success(`已回填 ${n} 笔样本`)
  else ElMessage.info('无新增样本（可能均已存在）')
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

function handleFillDraft() {
  fillConclusionDraft()
  void saveConclusion(auditConclusion.value)
  ElMessage.success('已生成审计结论草稿')
}

async function handleSave() {
  if (coverageLow.value && !String(auditNote.value || '').trim()) {
    ElMessage.warning('检查比例偏低：请先扩大样本量，或在「四、审计说明」中解释原因后再保存')
    return
  }
  await persistAll()
  ElMessage.success('针对性检查表已保存')
}

function handleReview() {
  openReviewDialog('I3-5-针对性检查')
}
</script>

<style scoped>
.i3-targeted-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.65;
}
.tab-toolbar { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.toolbar-right, .title-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.block-card { margin-bottom: 12px; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.check-alert { margin-bottom: 10px; }
.test-content-hint { font-size: 12px; color: #4b5563; margin-bottom: 10px; line-height: 1.6; }
.test-content-hint p { margin: 0 0 4px; font-weight: 600; }
.test-content-hint ol { margin: 0; padding-left: 18px; }
.reason-group { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-bottom: 8px; }
.sample-desc { margin-top: 4px; }
.pop-cell, .method-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; width: 100%; }
.sep { color: #9ca3af; margin: 0 2px; }
.hint { font-size: 11px; color: #9ca3af; margin-left: 4px; }
.amt { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.warn-coverage { color: #dc2626; font-weight: 600; }
.check-h { border-bottom: 1px dashed #a5b4fc; cursor: help; font-weight: 600; }
.check-ok { color: #059669; font-weight: 600; }
.check-fail { color: #dc2626; font-weight: 700; }
.abnormal-cell { color: #dc2626; font-weight: 600; }
.risk-card .risk-block { display: flex; flex-direction: column; gap: 6px; }
.risk-title { font-size: 13px; font-weight: 600; color: #374151; }
.mt-6 { margin-top: 6px; width: 100%; }
.audit-note-card, .audit-conclusion-card { margin-top: 12px; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 18px; margin-top: 8px; line-height: 1.8; }
:deep(.anomaly-row) { background-color: #fef2f2 !important; }
:deep(.anomaly-row:hover > td) { background-color: #fee2e2 !important; }
</style>
