<!--
  I4TabTargetedCheck.vue — I4-5 长期待摊费用针对性检查表

  对齐致同 Excel：一目标 / 二抽样(测试原因) / 三凭证核对 / 专项风险(旧三段落) / 四说明 / 五结论
  原段落型「大额新增核查 / 受益期变更 / 提前终止处理」保留为可选「专项风险关注」(镜像 I3-5 骨架)
-->
<template>
  <div class="i4-targeted-check">
    <div class="section-header">
      <span class="section-title">I4-5 长期待摊费用针对性检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、测试目标</template>
      <ol class="obj-list">
        <li v-for="(o, i) in I4_5_OBJECTIVES" :key="i">{{ o }}</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        勾选测试原因 → 界定测试总体与特定样本（100%检查）→ 抽样剩余总体 →
        逐笔核对凭证与支持性文件（核对内容 1~5）→ 异常标注 → 形成说明与结论。
        检查比例＝样本借方合计 ÷ 本期借方发生额（总体为 0 时显示 N/A，避免 Excel #DIV/0!）。
        大额新增、受益期变更、提前终止的段落型分析见下方「专项风险关注」。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I4-5" :context-project-id="projectId" />
        <el-tag size="small" type="info">样本 {{ summary.sampleCount }} 笔</el-tag>
        <el-tag v-if="summary.specificCount" size="small" type="warning">特定 {{ summary.specificCount }}</el-tag>
        <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">异常 {{ summary.anomalyCount }}</el-tag>
        <el-tag v-if="summary.failCheckCount > 0" size="small" type="danger">核对× {{ summary.failCheckCount }}</el-tag>
        <el-tag v-if="summary.pendingCount > 0" size="small" type="warning">未完成 {{ summary.pendingCount }}</el-tag>
        <el-tag size="small" :type="coverageTagType">检查比例 {{ coverageLabel }}</el-tag>
        <el-button size="small" @click="emit('navigate-sheet', 'I4-4')">← I4-4</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I4-6')">I4-6 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="expansionAdvice.needed"
      type="error"
      :closable="false"
      show-icon
      class="check-alert"
    >
      <template #title>{{ expansionAdvice.title }}</template>
      <div class="expand-body">
        <p>
          已检查借方 {{ fmtNum(expansionAdvice.checkedDebit) }} /
          总体 {{ fmtNum(expansionAdvice.periodDebit) }}，
          达阈值 {{ expansionAdvice.threshold }}% 尚需约
          <b>{{ fmtNum(expansionAdvice.additionalDebitNeeded) }}</b>
          <span v-if="expansionAdvice.suggestedExtraSamples != null">
            （约 {{ expansionAdvice.suggestedExtraSamples }} 笔）
          </span>。
        </p>
        <ul class="expand-actions">
          <li v-for="(a, i) in expansionAdvice.actions" :key="i">{{ a }}</li>
        </ul>
        <div class="expand-btns" v-if="!isReadonly">
          <el-button size="small" type="primary" @click="handleSampling">打开抽凭引擎扩样</el-button>
          <el-button size="small" @click="handleWriteExpansionNote">写入扩样说明</el-button>
        </div>
        <p v-if="!coverageNoteOk" class="expand-gate">保存前须扩样或在审计说明中回应（当前说明尚未满足闸门）。</p>
      </div>
    </el-alert>

    <el-alert
      v-if="creditExpansionAdvice.needed"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
    >
      <template #title>{{ creditExpansionAdvice.title }}</template>
      <div class="expand-body">
        <p>
          已检查贷方 {{ fmtNum(creditExpansionAdvice.checkedAmount) }} /
          总体 {{ fmtNum(creditExpansionAdvice.periodAmount) }}，
          达阈值 {{ creditExpansionAdvice.threshold }}% 尚需约
          <b>{{ fmtNum(creditExpansionAdvice.additionalAmountNeeded) }}</b>
          <span v-if="creditExpansionAdvice.suggestedExtraSamples != null">
            （约 {{ creditExpansionAdvice.suggestedExtraSamples }} 笔）
          </span>。
        </p>
        <ul class="expand-actions">
          <li v-for="(a, i) in creditExpansionAdvice.actions" :key="i">{{ a }}</li>
        </ul>
        <div class="expand-btns" v-if="!isReadonly">
          <el-button size="small" type="primary" @click="handleSampling">打开抽凭（贷方）</el-button>
          <el-button size="small" @click="handleWriteExpansionNote">写入扩样说明</el-button>
        </div>
        <p v-if="!coverageNoteOk" class="expand-gate">保存前须扩样或在审计说明中回应贷方覆盖率偏低。</p>
      </div>
    </el-alert>

    <el-alert
      v-if="specificAmountCheck.severity !== 'ok'"
      :type="specificAmountCheck.severity === 'warning' ? 'warning' : 'info'"
      :closable="false"
      show-icon
      class="check-alert"
      :title="specificAmountCheck.message"
    >
      <div class="expand-btns" v-if="!isReadonly && specificAmountCheck.severity !== 'ok'">
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="!summary.specificCount"
          @click="handleSyncSpecificAmount"
        >
          从表内特定样本同步
        </el-button>
      </div>
    </el-alert>

    <el-alert
      v-if="i44Cross.findings.length"
      :type="i44Cross.hasWarning ? 'warning' : 'info'"
      :closable="false"
      show-icon
      class="check-alert"
    >
      <template #title>
        与 I4-4 摊销政策交叉印证
        <span v-if="i44Cross.hasWarning">（有待跟进）</span>
        <span v-else-if="!i44Cross.empty">（已对齐）</span>
      </template>
      <div class="cross-body">
        <div
          v-for="f in i44Cross.findings"
          :key="f.id"
          class="cross-item"
          :class="`sev-${f.severity}`"
        >
          <b>{{ f.title }}</b> — {{ f.detail }}
        </div>
        <div class="expand-btns" v-if="!isReadonly">
          <el-button size="small" @click="emit('navigate-sheet', 'I4-4')">打开 I4-4</el-button>
          <el-button size="small" type="primary" plain @click="handleWriteI44Cross">写入交叉印证到说明</el-button>
        </div>
      </div>
    </el-alert>

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
              从 I4-2 带入本期发生额
            </el-button>
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedPeriod.originalTotal > 0)"
              @click="handleSyncPopulation('original')"
            >
              带入原始金额合计
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              抽凭引擎
            </el-button>
            <el-button
              size="small"
              :disabled="isReadonly || !i42ProjectNames.length"
              @click="handleLinkProjects"
            >
              挂接 I4-2 项目名
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
          <el-checkbox v-for="r in I4_5_TEST_REASONS" :key="r" :label="r" />
        </el-checkbox-group>
        <el-button
          v-if="!isReadonly && policyChangeNeedsSample"
          size="small"
          type="warning"
          plain
          class="reason-hint-btn"
          @click="ensureBenefitChangeReason"
        >
          按 I4-4 变更勾选「受益期变更」
        </el-button>
      </div>

      <div class="test-content-hint">
        <p>测试内容说明（第三节「核对内容」列）：</p>
        <ol>
          <li v-for="(item, i) in I4_5_TEST_CONTENT" :key="i">{{ i + 1 }}. {{ item }}</li>
        </ol>
      </div>

      <el-descriptions :column="2" border size="small" class="sample-desc">
        <el-descriptions-item label="测试总体">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.populationDesc"
            size="small"
            placeholder="账面长期待摊费用借方发生额总体"
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
          <span class="hint">（终止摊销/转出等；贷方检查比例
            <span :class="{ 'warn-coverage': creditCoverageLow }">{{ creditCoverageLabel }}</span>）</span>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本（100%检查）">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.specificSample"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="大额新增、关联方、受益期变更/提前终止…"
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
            <span class="hint">（表内特定借方 {{ fmtNum(summary.specificDebitTotal) }}）</span>
            <el-tag
              v-if="specificAmountCheck.severity === 'ok' && (sampleMeta.specificAmount > 0 || summary.specificDebitTotal > 0)"
              size="small"
              type="success"
              effect="plain"
            >已对齐</el-tag>
            <el-tag
              v-else-if="specificAmountCheck.severity === 'warning'"
              size="small"
              type="warning"
              effect="plain"
            >差异 {{ fmtNum(specificAmountCheck.diff) }}</el-tag>
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
              <el-option v-for="m in I4_5_SAMPLE_METHODS" :key="m" :label="m" :value="m" />
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
              <el-option v-for="r in I4_5_TEST_REASONS" :key="r" :label="r" :value="r" />
            </el-select>
            <span v-else>{{ row.selectionReason || '抽样' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="长期待摊项目明细" min-width="140" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.projectName"
              size="small"
              filterable
              allow-create
              clearable
              placeholder="对照 I4-2"
              style="width:100%"
              @change="(v: string) => updateRow(row.rowId, 'projectName', v || '')"
            >
              <el-option v-for="n in i42ProjectNames" :key="n" :label="n" :value="n" />
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
              placeholder="合同/发票/验收单…"
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
            <el-tooltip :content="I4_5_TEST_CONTENT[ci - 1]" placement="top">
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
              <el-option v-for="o in I4_5_ABNORMAL_OPTIONS" :key="o" :label="o" :value="o" />
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

      <!-- 对齐 Excel 表尾：合计 / 本期发生额 / 检查比例 -->
      <div class="excel-footer">
        <div class="footer-row">
          <span class="footer-label">合计（已检查）</span>
          <span>借方 {{ fmtNum(coverageFooter.checkedDebitTotal) }}</span>
          <span class="sep">/</span>
          <span>贷方 {{ fmtNum(coverageFooter.checkedCreditTotal) }}</span>
        </div>
        <div class="footer-row">
          <span class="footer-label">本期发生额（测试总体）</span>
          <span>借方 {{ fmtNum(coverageFooter.periodDebitTotal) }}</span>
          <span class="sep">/</span>
          <span>贷方 {{ fmtNum(coverageFooter.periodCreditTotal) }}</span>
          <el-tag v-if="linkedPeriod.source" size="small" type="info">{{ linkedPeriod.source }}</el-tag>
        </div>
        <div class="footer-row">
          <span class="footer-label">检查比例</span>
          <span :class="{ 'warn-coverage': coverageLow }">{{ coverageFooter.layeredCoverageLabel }}</span>
          <span class="sep">贷方</span>
          <span>{{ coverageFooter.creditCoverageLabel }}</span>
        </div>
      </div>
    </el-card>

    <!-- 专项风险关注（兼容原段落型：大额新增/受益期变更/提前终止） -->
    <el-card shadow="never" class="block-card risk-card">
      <template #header>
        <div class="block-title">
          <span>专项风险关注（可选）</span>
          <el-tag size="small" type="info">大额新增 / 受益期变更 / 提前终止处理</el-tag>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title-row">
              <span class="risk-title">大额新增核查</span>
              <el-button size="small" type="primary" text :disabled="isReadonly" @click="handleAiGenerate('major-addition')">
                <el-icon><MagicStick /></el-icon> AI
              </el-button>
            </div>
            <el-input
              v-model="riskFocus.majorAddition"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="本期大额新增项目清单、真实性核查、资本化判断依据、受益期确定依据…"
              @blur="saveRiskFocus"
            />
            <el-select v-model="riskFocus.majorAdditionConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6" @change="saveRiskFocus">
              <el-option label="大额新增真实完整，资本化判断恰当" value="大额新增真实完整，资本化判断恰当" />
              <el-option label="大额新增存在疑点，需进一步核实" value="大额新增存在疑点，需进一步核实" />
              <el-option label="存在不应资本化的支出" value="存在不应资本化的支出" />
              <el-option label="本期无大额新增" value="本期无大额新增" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title-row">
              <span class="risk-title">受益期变更</span>
              <el-button size="small" type="primary" text :disabled="isReadonly" @click="handleAiGenerate('benefit-change')">
                <el-icon><MagicStick /></el-icon> AI
              </el-button>
            </div>
            <el-input
              v-model="riskFocus.benefitChange"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="变更项目清单、变更原因、对当期及未来摊销影响金额、商业理由…"
              @blur="saveRiskFocus"
            />
            <el-select v-model="riskFocus.benefitChangeConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6" @change="saveRiskFocus">
              <el-option label="受益期估计合理，本期无变更" value="受益期估计合理，本期无变更" />
              <el-option label="存在合理变更，已恰当处理并披露" value="存在合理变更，已恰当处理并披露" />
              <el-option label="存在变更但披露不充分" value="存在变更但披露不充分" />
              <el-option label="变更缺乏合理理由，可能存在利润操纵" value="变更缺乏合理理由，可能存在利润操纵" />
            </el-select>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="risk-block">
            <div class="risk-title-row">
              <span class="risk-title">提前终止处理</span>
              <el-button size="small" type="primary" text :disabled="isReadonly" @click="handleAiGenerate('early-termination')">
                <el-icon><MagicStick /></el-icon> AI
              </el-button>
            </div>
            <el-input
              v-model="riskFocus.earlyTermination"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 8 }"
              :disabled="isReadonly"
              placeholder="本期是否存在提前终止摊销项目、终止原因及处理方式、剩余未摊余额转出…"
              @blur="saveRiskFocus"
            />
            <el-select v-model="riskFocus.earlyTerminationConclusion" size="small" :disabled="isReadonly" clearable placeholder="结论" class="mt-6" @change="saveRiskFocus">
              <el-option label="本期无提前终止项目" value="本期无提前终止项目" />
              <el-option label="提前终止处理恰当" value="提前终止处理恰当" />
              <el-option label="存在应终止但未终止的项目" value="存在应终止但未终止的项目" />
              <el-option label="终止处理不当，需建议调整" value="终止处理不当，需建议调整" />
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
          <el-button
            v-if="!isReadonly && pushableAdjDrafts.length"
            size="small"
            text
            type="warning"
            @click="handlePushI43"
          >
            推送至 I4-3（{{ pushableAdjDrafts.length }}）
          </el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录抽样过程、异常处理、与 I4-2 / I4-4 交叉印证情况…"
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
        placeholder="针对性检查是否达成测试目标；长期待摊费用在重大方面是否恰当…"
        @change="(v: string) => saveConclusion(v)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示（对齐 Excel I4-5，已补强模板缺口）</summary>
      <ol>
        <li>先勾选测试原因并填第二节总体，再抽样本填入第三节；检查比例=样本借方÷本期借方（总体为 0 显示 N/A，避免 #DIV/0!）。</li>
        <li>无新增时本期借方可为 0，可改用「带入原始金额合计」作存在性测试总体，并在说明中解释。</li>
        <li>核对 1~5 对应测试内容说明（Excel 第 5 项原为空，已补全为与 I4-2 入账/受益期一致）；选「×」时按核对项自动建议异常类型。</li>
        <li>表内「选取原因」标记特定样本（100%检查层），可用「从表内特定样本同步」回写第二节金额；分层覆盖率见合计区。</li>
        <li>检查比例偏低时系统给出强制扩样建议（借方/贷方对称）；未扩样须写入说明，否则无法保存。</li>
        <li>第二节「特定样本金额」与表内特定借方按容差校验，不一致可一键同步。</li>
        <li>勾选测试原因后，抽凭引擎预填方法/摘要关键词/方向（大额→MUS、提前终止→贷方等）。</li>
        <li>自动读取 I4-4 CAS 五维结论与变更类别，与抽凭核对3/5、测试原因、专项风险交叉印证。</li>
        <li>抽凭回填时按摘要模糊挂接 I4-2 项目名；也可点「挂接 I4-2 项目名」补全空行。</li>
        <li>资本化/跨期类核对× 可「推送至 I4-3」生成费用化或跨期 AJE（按说明去重）。</li>
        <li>与 I4-4 有交叉缺口且未写说明时，保存会二次确认（软闸门）。</li>
      </ol>
    </details>

    <el-dialog
      v-model="samplingVisible"
      title="抽凭引擎 — 长期待摊费用(1801) 针对性检查"
      width="90%"
      top="5vh"
      destroy-on-close
    >
      <p v-if="samplingPreset.hintText" class="sampling-preset-hint">{{ samplingPreset.hintText }}</p>
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="1801"
        phase="final"
        :default-method="samplingPreset.defaultMethod"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        :initial-config-patch="samplingConfigPatch"
        :config-hint="samplingPreset.hintText"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, toRef, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import {
  useI4TargetedCheck,
  I4_5_OBJECTIVES,
  I4_5_TEST_CONTENT,
  I4_5_TEST_REASONS,
  I4_5_SAMPLE_METHODS,
  I4_5_CHECK_OPTIONS,
  I4_5_ABNORMAL_OPTIONS,
  isAbnormalFlag,
  hasFailedCheck,
  parseI44PolicySnapshot,
} from '../../composables/useI4TargetedCheck'

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
const checkOpts = I4_5_CHECK_OPTIONS.filter((o) => o !== '') as string[]
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
  creditCoverageLow,
  expansionAdvice,
  creditExpansionAdvice,
  coverageNoteOk,
  specificAmountCheck,
  samplingPreset,
  i44Cross,
  coverageLabel,
  creditCoverageLabel,
  coverageFooter,
  coverageTagType,
  linkedPeriod,
  adjDrafts,
  pushableAdjDrafts,
  i42ProjectNames,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  linkProjectsFromI42,
  pushAdjDraftsToI43,
  setPopulationAmount,
  syncPopulationFromI42,
  syncSpecificAmount,
  appendAdjDraftsToNote,
  appendExpansionAdviceToNote,
  appendI44CrossToNote,
  fillConclusionDraft,
  canPersist,
  persistAll,
  saveNote,
  saveConclusion,
  saveRiskFocus,
} = useI4TargetedCheck(allResponsesRef, {
  onSave: (itemId, value) => emit('save', itemId, value),
  asOfYear,
})

const samplingConfigPatch = computed(() => {
  const p = samplingPreset.value
  return {
    samplingMethod: p.defaultMethod,
    summaryKeyword: p.summaryKeyword,
    directionFilter: p.directionFilter,
    ...(p.materialityThreshold ? { materialityThreshold: p.materialityThreshold } : {}),
  }
})

/** I4-4 有估计变更且未勾选「受益期变更」 */
const policyChangeNeedsSample = computed(() => {
  const snap = parseI44PolicySnapshot(props.allResponses)
  const changed = (snap?.policyParams || []).some((p: any) => p.hasChange === 'Y')
  const reasons = sampleMeta.value.testReasons || []
  return !!changed && !reasons.includes('受益期变更')
})

function ensureBenefitChangeReason() {
  if (!sampleMeta.value.testReasons.includes('受益期变更')) {
    sampleMeta.value.testReasons = [...sampleMeta.value.testReasons, '受益期变更']
  }
  ElMessage.success('已勾选测试原因「受益期变更」')
}

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
  const r = syncPopulationFromI42(mode)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSyncSpecificAmount() {
  const r = syncSpecificAmount()
  ElMessage.success(r.message)
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

async function handlePushI43() {
  try {
    await ElMessageBox.confirm(
      `将把 ${pushableAdjDrafts.value.length} 条资本化/跨期草稿推送到 I4-3（跳过已有同说明）。是否继续？`,
      '推送至 I4-3',
      { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const r = await pushAdjDraftsToI43()
  if (r.ok) {
    ElMessage.success(r.message)
    emit('navigate-sheet', 'I4-3')
  } else {
    ElMessage.info(r.message)
  }
}

function handleLinkProjects() {
  const r = linkProjectsFromI42(false)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.info(r.message)
}

function handleWriteExpansionNote() {
  const r = appendExpansionAdviceToNote()
  if (r.ok) {
    void saveNote(auditNote.value)
    ElMessage.success(r.message)
  } else {
    ElMessage.info(r.message)
  }
}

function handleWriteI44Cross() {
  const r = appendI44CrossToNote()
  void saveNote(auditNote.value)
  if (i44Cross.value.hasWarning) ElMessage.warning(r.message)
  else ElMessage.success(r.message)
}

function handleFillDraft() {
  fillConclusionDraft()
  void saveConclusion(auditConclusion.value)
  ElMessage.success('已生成审计结论草稿')
}

async function handleSave() {
  const gate = canPersist()
  if (gate.level === 'block') {
    ElMessage.error(gate.message)
    return
  }
  if (gate.level === 'warn') {
    try {
      await ElMessageBox.confirm(gate.message, 'I4-4 交叉印证', {
        type: 'warning',
        confirmButtonText: '仍要保存',
        cancelButtonText: '去写说明',
        distinguishCancelAndClose: true,
      })
    } catch {
      return
    }
    await persistAll({ skipGate: true })
    ElMessage.success('针对性检查表已保存（已跳过 I4-4 交叉软闸门）')
    return
  }
  const result = await persistAll()
  if (result.level === 'block') {
    ElMessage.error(result.message)
    return
  }
  ElMessage.success('针对性检查表已保存')
}

async function handleAiGenerate(section: 'major-addition' | 'benefit-change' | 'early-termination'): Promise<void> {
  const fieldMap = {
    'major-addition': 'majorAddition',
    'benefit-change': 'benefitChange',
    'early-termination': 'earlyTermination',
  } as const
  const field = fieldMap[section]
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `I4针对性检查-${section}`,
      context: {
        wpCode: 'I4-5',
        topic: section,
        existing: riskFocus.value[field] || '',
      },
    })
    if (res.data?.data?.content) {
      riskFocus.value[field] = res.data.data.content
      await saveRiskFocus()
    }
  } catch { /* ignore */ }
}

function handleReview() {
  openReviewDialog('I4-5-针对性检查')
}
</script>

<style scoped>
.i4-targeted-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
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
.expand-body, .cross-body { font-size: 12px; line-height: 1.65; }
.expand-body p { margin: 4px 0; }
.expand-actions { margin: 4px 0 8px; padding-left: 18px; }
.expand-btns { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.expand-gate { color: #b91c1c; font-weight: 600; margin-top: 6px !important; }
.sampling-preset-hint {
  margin: 0 0 10px; padding: 8px 10px; font-size: 12px; color: #1e40af;
  background: #eff6ff; border-radius: 4px; line-height: 1.5;
}
.cross-item { margin: 2px 0; }
.cross-item.sev-warning { color: #92400e; }
.cross-item.sev-error { color: #b91c1c; }
.cross-item.sev-info { color: #374151; }
.test-content-hint { font-size: 12px; color: #4b5563; margin-bottom: 10px; line-height: 1.6; }
.test-content-hint p { margin: 0 0 4px; font-weight: 600; }
.test-content-hint ol { margin: 0; padding-left: 18px; }
.reason-group { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-bottom: 8px; }
.reason-hint-btn { margin-left: 8px; margin-bottom: 8px; }
.sample-desc { margin-top: 4px; }
.pop-cell, .method-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; width: 100%; }
.sep { color: #9ca3af; margin: 0 2px; }
.hint { font-size: 11px; color: #9ca3af; margin-left: 4px; }
.amt { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.warn-coverage { color: #dc2626; font-weight: 600; }
.excel-footer {
  margin-top: 10px; padding: 10px 12px; background: #f8fafc;
  border: 1px solid #e2e8f0; border-radius: 4px; font-size: 12px;
}
.footer-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; line-height: 1.8; }
.footer-label { font-weight: 600; color: #374151; min-width: 140px; }
.check-h { border-bottom: 1px dashed #a5b4fc; cursor: help; font-weight: 600; }
.check-ok { color: #059669; font-weight: 600; }
.check-fail { color: #dc2626; font-weight: 700; }
.abnormal-cell { color: #dc2626; font-weight: 600; }
.risk-card .risk-block { display: flex; flex-direction: column; gap: 6px; }
.risk-title-row { display: flex; align-items: center; justify-content: space-between; }
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
