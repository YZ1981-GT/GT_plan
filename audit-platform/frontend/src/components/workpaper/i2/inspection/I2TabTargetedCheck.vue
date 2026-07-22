<template>
  <div class="i2-targeted-check">
    <div class="section-header">
      <span class="section-title">I2-12 开（研）发支出针对性检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、测试目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I2_12_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        界定测试总体与特定样本 → 抽样 → 逐笔核对凭证与支持性文件（核对内容 1~5）→
        异常标注 → 形成说明与结论。检查比例＝样本借方合计 ÷ 总体金额（总体为 0 时 N/A）。
        专项检查表 I2-8~11 / 截止 I2-13~14 已覆盖细分领域时，本表侧重综合抽凭与归集正确性。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-12" :context-project-id="projectId" />
        <el-tag size="small" type="info">样本 {{ summary.sampleCount }} 笔</el-tag>
        <el-tag v-if="summary.specificCount" size="small" type="warning">特定 {{ summary.specificCount }}</el-tag>
        <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">异常 {{ summary.anomalyCount }}</el-tag>
        <el-tag v-if="summary.failCheckCount > 0" size="small" type="danger">核对× {{ summary.failCheckCount }}</el-tag>
        <el-tag v-if="summary.pendingCount > 0" size="small" type="warning">未完成 {{ summary.pendingCount }}</el-tag>
        <el-tag size="small" :type="coverageTagType">检查比例 {{ coverageLabel }}</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-11')">← I2-11</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-13')">I2-13 →</el-button>
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
          <span>二、样本选取标准与规模</span>
          <div class="title-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedCapTotal.amount > 0)"
              @click="handleSyncPopulation"
            >
              从 I2-2 带入本期资本化增加
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>

      <div class="test-content-hint">
        <p>测试内容说明（第三节「核对内容」列）：</p>
        <ol>
          <li v-for="(item, i) in I2_12_TEST_CONTENT" :key="i">{{ i + 1 }}. {{ item }}</li>
        </ol>
      </div>

      <el-descriptions :column="2" border size="small" class="sample-desc">
        <el-descriptions-item label="测试总体">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.populationDesc"
            size="small"
            placeholder="账面开发支出借方发生额总体"
          />
          <span v-else>{{ sampleMeta.populationDesc }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="总体笔数 / 金额">
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
            <el-tag v-if="linkedCapTotal.source" size="small" type="info">
              源 {{ linkedCapTotal.source }}: {{ fmtNum(linkedCapTotal.amount) }}
            </el-tag>
            <el-tag v-if="sampleMeta.populationManual" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本（100%检查）">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.specificSample"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="大额、关联方、异常事项…"
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
              <el-option v-for="m in I2_12_SAMPLE_METHODS" :key="m" :label="m" :value="m" />
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
          <span class="amt">{{ fmtNum(summary.checkedDebitTotal) }}</span>
          <span class="sep">/</span>
          <span :class="{ 'warn-coverage': coverageLow }">{{ coverageLabel }}</span>
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

        <el-table-column label="开发支出项目" min-width="120" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.projectName"
              size="small"
              placeholder="项目"
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
              placeholder="合同/发票/工时…"
              @update:model-value="(v: string) => updateRow(row.rowId, 'supportingDocs', v)"
            />
            <span v-else>{{ row.supportingDocs || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="核对1" width="72" align="center">
          <template #header>
            <el-tooltip :content="I2_12_TEST_CONTENT[0]" placement="top"><span class="check-h">1</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check1"
              size="small"
              clearable
              @change="(v: string) => updateRow(row.rowId, 'check1', v || '')"
            >
              <el-option v-for="o in checkOpts" :key="o || 'empty'" :label="o || '—'" :value="o" />
            </el-select>
            <span v-else :class="checkClass(row.check1)">{{ row.check1 || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对2" width="72" align="center">
          <template #header>
            <el-tooltip :content="I2_12_TEST_CONTENT[1]" placement="top"><span class="check-h">2</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check2"
              size="small"
              clearable
              @change="(v: string) => updateRow(row.rowId, 'check2', v || '')"
            >
              <el-option v-for="o in checkOpts" :key="o || 'empty'" :label="o || '—'" :value="o" />
            </el-select>
            <span v-else :class="checkClass(row.check2)">{{ row.check2 || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对3" width="72" align="center">
          <template #header>
            <el-tooltip :content="I2_12_TEST_CONTENT[2]" placement="top"><span class="check-h">3</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check3"
              size="small"
              clearable
              @change="(v: string) => updateRow(row.rowId, 'check3', v || '')"
            >
              <el-option v-for="o in checkOpts" :key="o || 'empty'" :label="o || '—'" :value="o" />
            </el-select>
            <span v-else :class="checkClass(row.check3)">{{ row.check3 || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对4" width="72" align="center">
          <template #header>
            <el-tooltip :content="I2_12_TEST_CONTENT[3]" placement="top"><span class="check-h">4</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check4"
              size="small"
              clearable
              @change="(v: string) => updateRow(row.rowId, 'check4', v || '')"
            >
              <el-option v-for="o in checkOpts" :key="o || 'empty'" :label="o || '—'" :value="o" />
            </el-select>
            <span v-else :class="checkClass(row.check4)">{{ row.check4 || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对5" width="72" align="center">
          <template #header>
            <el-tooltip :content="I2_12_TEST_CONTENT[4]" placement="top"><span class="check-h">5</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.check5"
              size="small"
              clearable
              @change="(v: string) => updateRow(row.rowId, 'check5', v || '')"
            >
              <el-option v-for="o in checkOpts" :key="o || 'empty'" :label="o || '—'" :value="o" />
            </el-select>
            <span v-else :class="checkClass(row.check5)">{{ row.check5 || '—' }}</span>
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
              <el-option label="跨期" value="跨期" />
              <el-option label="归集错误" value="归集错误" />
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

    <!-- 专项风险关注（兼容原段落型 Req 13） -->
    <el-card shadow="never" class="block-card risk-card">
      <template #header>
        <div class="block-title">
          <span>专项风险关注（可选，补充段落结论）</span>
          <el-tag size="small" type="info">加计扣除 / 资本化比例 / 项目进度</el-tag>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">加计扣除合规性</div>
            <el-input
              v-model="riskFocus.deductionCompliance"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              :disabled="isReadonly"
              placeholder="归集范围、比例、委外80%、负面清单…"
            />
            <el-select v-model="riskFocus.deductionConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6">
              <el-option label="合规" value="合规" />
              <el-option label="存在偏差" value="存在偏差" />
              <el-option label="不合规" value="不合规" />
              <el-option label="不适用" value="不适用" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">资本化比例合理性</div>
            <el-input
              v-model="riskFocus.capitalizationRatio"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              :disabled="isReadonly"
              placeholder="同行业对比、时点一致性、对照 I2-6…"
            />
            <el-select v-model="riskFocus.capitalizationConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6">
              <el-option label="合理" value="合理" />
              <el-option label="偏高" value="偏高" />
              <el-option label="偏低" value="偏低" />
              <el-option label="不合理" value="不合理" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title">项目进度与里程碑</div>
            <el-input
              v-model="riskFocus.projectProgress"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              :disabled="isReadonly"
              placeholder="立项计划、验收文档、长期未结项减值迹象…"
            />
            <el-select v-model="riskFocus.progressConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6">
              <el-option label="正常" value="正常" />
              <el-option label="存在延期" value="存在延期" />
              <el-option label="存在减值迹象" value="存在减值迹象" />
              <el-option label="需进一步关注" value="需进一步关注" />
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
        placeholder="记录抽样过程、异常处理、与 I2-8~11 / I2-6 交叉印证情况…"
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
        placeholder="针对性检查是否达成测试目标；开发支出在重大方面是否恰当…"
        @change="(v: string) => saveConclusion(v)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示（对齐 Excel I2-12）</summary>
      <ol>
        <li>先填第二节总体与特定样本，再抽样本填入第三节；检查比例=样本借方÷总体（分层：特定+抽样）。</li>
        <li>核对 1~5 对应测试内容说明；选「×」时自动提示异常标记，并可写入调整建议草稿。</li>
        <li>人工/材料/委外细分程序见 I2-9~11；截止见 I2-13/14；资本化条件见 I2-6。</li>
        <li>专项风险关注区保留加计扣除/资本化比例/进度段落结论，可并入结论草稿。</li>
      </ol>
    </details>

    <el-dialog
      v-model="samplingVisible"
      title="抽凭引擎 — 开发支出(1717) 针对性检查"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="1717"
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
 * I2TabTargetedCheck.vue — I2-12 针对性检查表
 * 对齐致同 Excel：一目标 / 二抽样 / 三凭证核对 / 四说明 / 五结论
 */
import { computed, inject, ref, toRef, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI2TargetedCheck,
  I2_12_OBJECTIVES,
  I2_12_TEST_CONTENT,
  I2_12_SAMPLE_METHODS,
  I2_12_CHECK_OPTIONS,
  isAbnormalFlag,
  hasFailedCheck,
} from '../../composables/useI2TargetedCheck'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)
const checkOpts = I2_12_CHECK_OPTIONS.filter((o) => o !== '') as string[]
const samplingVisible = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())

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
  coverageTagType,
  linkedCapTotal,
  adjDrafts,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  setPopulationAmount,
  syncPopulationFromI22,
  appendAdjDraftsToNote,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
} = useI2TargetedCheck(allResponsesRef, {
  saveResponse: props.saveResponse,
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

function handleSyncPopulation() {
  const r = syncPopulationFromI22()
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
  await persistAll()
  emit('save')
  ElMessage.success('针对性检查表已保存')
}

function handleReview() {
  openReviewDialog('I2-12-针对性检查')
}
</script>

<style scoped>
.i2-targeted-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
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
