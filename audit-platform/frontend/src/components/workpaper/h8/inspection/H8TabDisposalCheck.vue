<template>
  <div class="h8-tab-disposal-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>核实已记录的使用权资产减少确已发生，且已记入恰当账户（存在/发生）</li>
        <li>核实所有应记录的使用权资产减少均已入账，相关披露完整（完整性/截止）</li>
        <li>核实原值、累计折旧、减值、净值及终止损益计量正确，租赁负债同步终止（准确性/计价）</li>
        <li>核实减少分类与列报恰当，关联方租赁披露完整（列报与披露）</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H8-12" :context-project-id="projectId" /></span>
      <GtIndexChip value="wp:H8-2" :context-project-id="projectId" context="明细勾稽" />
      <GtIndexChip value="wp:H9-2" :context-project-id="projectId" context="负债终止" />
      <GtIndexChip value="wp:H8-14" :context-project-id="projectId" context="关联方" />
      <el-tag size="small" type="info">样本 {{ rows.length }} 项</el-tag>
      <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">
        异常 {{ summary.anomalyCount }} 项
      </el-tag>
      <el-tag v-if="summary.unsyncedH9Count > 0" size="small" type="warning">
        H9未同步 {{ summary.unsyncedH9Count }} 项
      </el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ summary.coverageRate.toFixed(2) }}%
      </el-tag>
      <el-button size="small" @click="emit('navigate-sheet', 'H8-11')">← H8-11</el-button>
      <el-button size="small" @click="emit('navigate-sheet', 'H8-13')">H8-13 →</el-button>
      <el-dropdown size="small" @command="handleExportCommand">
        <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    </div>

    <el-alert
      v-if="summary.unsyncedH9Count > 0"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`${summary.unsyncedH9Count} 笔终止尚未同步 H9：终止时租赁负债也应终止确认。`"
    />
    <el-alert
      v-if="summary.incompleteCheckCount > 0"
      type="info"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`有 ${summary.incompleteCheckCount} 笔核对内容 1–4 未全部勾选，请补充测试记录。`"
    />
    <el-alert
      v-if="samplingParams.populationAmount > 0 && summary.coverageRate < 20"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      title="检查比例偏低：请扩大样本量，或在四、审计说明中解释原因。"
    />

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、样本选取标准与规模</span>
          <div class="section-header-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedDecrease.amount > 0)"
              @click="syncPopulationFromLinked"
            >
              从 {{ linkedDecrease.source || 'H8-1/H8-2' }} 带入本期减少
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="showSampling = true">
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>

      <div class="test-content-hint">
        <p>测试内容说明（核对内容 1–5 列）：</p>
        <ol>
          <li v-for="(item, i) in H8_DISPOSAL_TEST_CONTENT_ITEMS" :key="i">{{ item }}</li>
        </ol>
        <p class="hint-note">
          特定样本优先：大额终止、提前退租、关联方租赁、异常终止损益；其余按抽样方法抽取。
          终止须同步 H9 租赁负债终止确认。
        </p>
      </div>

      <el-descriptions :column="3" border size="small" style="margin-top:8px">
        <el-descriptions-item label="本期减少合计（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="samplingParams.populationAmount"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateSamplingParams({ populationAmount: v ?? 0 })"
            />
            <span v-else class="amt-cell">{{ fmtAmt(samplingParams.populationAmount) }}</span>
            <el-tag v-if="linkedDecrease.source" size="small" type="info" class="src-tag">
              源 {{ linkedDecrease.source }}: {{ fmtAmt(linkedDecrease.amount) }}
            </el-tag>
            <el-tag v-if="populationManual" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法">
          <el-select
            v-if="!isReadonly"
            :model-value="samplingParams.samplingMethod"
            size="small"
            style="width:140px"
            @change="(v: string) => updateSamplingParams({ samplingMethod: v })"
          >
            <el-option v-for="m in SAMPLING_METHOD_OPTS" :key="m" :label="m" :value="m" />
          </el-select>
          <span v-else>{{ samplingParams.samplingMethod || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="样本量">{{ rows.length }}</el-descriptions-item>
        <el-descriptions-item label="检查原值合计">{{ fmtAmt(summary.checkedAmount) }}</el-descriptions-item>
        <el-descriptions-item label="检查比例">
          <span :class="{ 'warn-coverage': summary.coverageRate < 20 && samplingParams.populationAmount > 0 }">
            {{ summary.coverageRate.toFixed(2) }}%
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="重要性水平">
          <el-input-number
            v-if="!isReadonly"
            :model-value="samplingParams.materialityLevel"
            :controls="false"
            size="small"
            @change="(v: number | undefined) => updateSamplingParams({ materialityLevel: v ?? 0 })"
          />
          <span v-else>{{ fmtAmt(samplingParams.materialityLevel) }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <div class="specific-sample" v-if="!isReadonly || samplingParams.specificSampleNote">
        <span class="param-label">特定样本：</span>
        <el-input
          v-if="!isReadonly"
          :model-value="samplingParams.specificSampleNote"
          size="small"
          placeholder="大额、提前退租、关联方、异常终止损益等全部测试说明…"
          @change="(v: string) => updateSamplingParams({ specificSampleNote: v })"
        />
        <span v-else>{{ samplingParams.specificSampleNote }}</span>
      </div>

      <el-alert
        v-if="populationDrift"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`总体与 ${linkedDecrease.source}（${fmtAmt(linkedDecrease.amount)}）不一致，可重新带入或保留手工数。`"
      />
    </el-card>

    <!-- 三、测试 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、测试 — 本期减少检查明细（H8-12）</span>
          <div class="section-header-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly"
              @click="onImportFromH82"
            >
              从 H8-2 带入终止样本
            </el-button>
            <el-button
              size="small"
              :disabled="isReadonly || rows.length === 0"
              @click="onFillLiabilityFromH9"
            >
              从 H9 匹配负债
            </el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="isReadonly || summary.unsyncedH9Count === 0"
              @click="onSyncAllToH9"
            >
              批量同步 H9
            </el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleAddRow">+ 行</el-button>
            <el-button size="small" circle @click="emit('open-review', 'H8-12')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="560"
        class="check-table"
        row-key="rowId"
        :row-class-name="rowClassName"
        show-summary
        :summary-method="getTableSummary"
      >
        <el-table-column prop="seq" label="序号" width="48" fixed align="center" />

        <el-table-column label="使用权资产" align="center">
          <el-table-column label="类别" min-width="80">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small"
                @change="updateCell(row.rowId, 'assetCategory', $event)" />
              <span v-else>{{ row.assetCategory || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="编号/合同号" min-width="110" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
                @change="updateCell(row.rowId, 'contractNo', $event)" />
              <span v-else>{{ row.contractNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="名称" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
                @change="updateCell(row.rowId, 'assetName', $event)" />
              <span v-else>{{ row.assetName || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="减少方式" width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.reductionMethod" size="small" style="width:118px"
              @change="updateCell(row.rowId, 'reductionMethod', $event)">
              <el-option v-for="opt in REDUCTION_METHOD_OPTS" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-tag v-else size="small">{{ row.reductionMethod || '-' }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="减少日期" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.reductionDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @change="updateCell(row.rowId, 'reductionDate', $event)"
            />
            <span v-else>{{ row.reductionDate || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="凭证号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
              @change="updateCell(row.rowId, 'voucherNo', $event)" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="对方科目" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.oppositeAccount" size="small"
              placeholder="如租赁负债"
              @change="updateCell(row.rowId, 'oppositeAccount', $event)" />
            <span v-else>{{ row.oppositeAccount || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="数量" width="64" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.quantity" :controls="false"
              size="small" class="amt-input"
              @change="updateCell(row.rowId, 'quantity', $event)" />
            <span v-else>{{ row.quantity || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="减少情况" align="center">
          <el-table-column label="原值" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.rouCost" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'rouCost', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.rouCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计折旧" width="95" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.accDepreciation" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'accDepreciation', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.accDepreciation) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.impairmentProvision" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'impairmentProvision', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairmentProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="原值−累计折旧−减值准备">{{ fmtAmt(row.rouNetValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="租赁负债余额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.liabilityBalance" :controls="false"
              size="small" class="amt-input"
              @change="updateCell(row.rowId, 'liabilityBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.liabilityBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="终止损益" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="row.gainLoss >= 0 ? 'gain' : 'loss'"
              title="租赁负债余额 − 使用权资产净值"
            >
              {{ row.gainLoss >= 0 ? '+' : '' }}{{ fmtAmt(row.gainLoss) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="违约金" width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.earlyTermPenalty" :controls="false"
              size="small" class="amt-input"
              @change="updateCell(row.rowId, 'earlyTermPenalty', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.earlyTermPenalty) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="支持性文件" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.supportingDocs"
              size="small"
              :placeholder="getEvidenceHint(row.reductionMethod)"
              @change="updateCell(row.rowId, 'supportingDocs', $event)"
            />
            <span v-else>{{ row.supportingDocs || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="H9同步" width="120" align="center">
          <template #default="{ row }">
            <div class="h9-sync-cell">
              <el-button
                v-if="!row.h9Synced && !isReadonly"
                size="small"
                type="warning"
                plain
                @click="syncToH9(row.rowId)"
              >
                同步H9
              </el-button>
              <el-tag v-else-if="row.h9Synced" type="success" size="small">已同步</el-tag>
              <span v-else>-</span>
              <el-button
                v-if="row.contractNo"
                size="small"
                type="primary"
                link
                @click="emit('navigate-sheet', 'H9-2')"
              >↗H9</el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="核对内容" align="center">
          <el-table-column
            v-for="(_item, ci) in H8_DISPOSAL_TEST_CONTENT_ITEMS"
            :key="ci"
            :label="String(ci + 1)"
            width="44"
            align="center"
          >
            <template #default="{ row }">
              <el-checkbox
                v-if="!isReadonly"
                :model-value="row.checks[`check${ci + 1}` as keyof typeof row.checks]"
                @change="updateCell(row.rowId, `checks.check${ci + 1}`, $event)"
              />
              <span v-else>{{ row.checks[`check${ci + 1}` as keyof typeof row.checks] ? '✓' : '' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
              @change="updateCell(row.rowId, 'indexRef', $event)" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否异常" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isAbnormal" size="small" style="width:70px"
              @change="updateCell(row.rowId, 'isAbnormal', $event)">
              <el-option label="-" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isAbnormal || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否关联方" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRelatedParty" size="small" style="width:88px"
              @change="updateCell(row.rowId, 'isRelatedParty', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isRelatedParty || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="备注说明" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="updateCell(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="" width="40" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="deleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-block">
        <div class="summary-line">
          合计：原值 <strong>{{ fmtAmt(summary.checkedAmount) }}</strong>
          ／ 净值 <strong>{{ fmtAmt(summary.checkedNetValue) }}</strong>
          ／ 终止损益
          <strong :class="summary.gainLossTotal >= 0 ? 'gain' : 'loss'">
            {{ summary.gainLossTotal >= 0 ? '+' : '' }}{{ fmtAmt(summary.gainLossTotal) }}
          </strong>
          <span class="sep">检查比例
            <strong :class="{ 'warn-coverage': summary.coverageRate < 20 && samplingParams.populationAmount > 0 }">
              {{ summary.coverageRate.toFixed(2) }}%
            </strong>
          </span>
        </div>
        <div class="summary-line muted">
          本期减少使用权资产合计（总体）：{{ fmtAmt(samplingParams.populationAmount) }}
          <span v-if="samplingParams.populationAmount <= 0">（未填总体时检查比例显示 0%，避免除零）</span>
        </div>
      </div>

      <div class="stats-row">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">终止损益合计</div>
          <div class="stat-value" :class="summary.gainLossTotal >= 0 ? 'gain' : 'loss'">
            {{ summary.gainLossTotal >= 0 ? '+' : '' }}{{ fmtAmt(summary.gainLossTotal) }}
          </div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">收益 / 损失笔数</div>
          <div class="stat-value">
            <span class="gain">{{ summary.gainCount }}</span>
            <span class="muted"> / </span>
            <span class="loss">{{ summary.lossCount }}</span>
          </div>
        </el-card>
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">H9 已同步</div>
          <div class="stat-value">{{ rows.length - summary.unsyncedH9Count }} / {{ rows.length }}</div>
        </el-card>
      </div>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" type="primary" @click="handleAddRow">+ 添加检查行</el-button>
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计说明</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="draftNote">起草说明</el-button>
            <el-button size="small" circle @click="emit('open-review', 'H8-12-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="若检查比例偏低，扩大样本量或说明原因；概述终止损益、H9 同步、提前退租违约金及异常事项。"
        :disabled="isReadonly"
        @change="saveNote"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>五、审计结论</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="draftConclusion">起草结论</el-button>
            <el-button size="small" circle @click="emit('open-review', 'H8-12-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="基于上述检查，就是否实现一、审计目标发表结论；列明拟调整事项及范围受限影响。"
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <details class="edit-tips" open>
      <summary>提示（编制要点）</summary>
      <ol>
        <li>本表用于汇总本年度使用权资产减少（到期终止/提前退租/行权购买/变更减少等）的测试情况。</li>
        <li>净值 = 原值 − 累计折旧 − 减值准备；终止损益 = 租赁负债余额 − 使用权资产净值（正=收益/负=损失）。</li>
        <li>终止时必须同步 H9：租赁负债也应终止确认；点击「同步H9」或 ↗H9 跳转核对。</li>
        <li>检查比例 = 样本原值合计 ÷ 本期减少总体（覆盖率）；总体优先取 H8-1 原值贷方，否则取 H8-2 已终止合同入账值。</li>
        <li>到期终止时净值与负债余额应接近 0；提前退租须关注违约金条款（无违约金请在备注说明）。</li>
        <li>核对内容第 5 项：H9 已同步终止，且提前退租违约金/补偿已恰当确认。</li>
      </ol>
    </details>

    <el-dialog
      v-model="showSampling"
      :title="`抽凭引擎（科目 ${ROU_COST_CODE} 使用权资产-减少）`"
      width="860px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSampling && wpId && projectId"
        :account-code="ROU_COST_CODE"
        phase="final"
        default-method="mus"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDisposalCheck.vue — H8-12 使用权资产/租赁负债减少检查表
 * 对齐致同五段式：目标 → 样本选取 → 测试（原值/折旧/减值/净值 + 终止损益 + 核对1–5）
 * → 检查比例 → 说明/结论；平台增强 CAS21 终止损益 + H9 同步
 */
import { computed, ref, toRef, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH8DisposalCheck,
  REDUCTION_METHOD_OPTS,
  SAMPLING_METHOD_OPTS,
  H8_DISPOSAL_TEST_CONTENT_ITEMS,
  getEvidenceHint,
} from '../../composables/useH8DisposalCheck'
import { useH8ImportExport } from '../../composables/useH8ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import { h8Scope } from '../../composables/hCycleAccountScope'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { SampledVoucher } from '../../composables/useSamplingAlgorithms'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

/** 抽凭科目码（scope 单一真源；历史文案写死 `1901` = 待处理财产损溢） */
const ROU_COST_CODE = h8Scope.def.grossFallback

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const showSampling = ref(false)
const isReadonly = toRef(props, 'isReadonly')
const projectId = toRef(props, 'projectId')
const wpId = toRef(props, 'wpId')
const samplingYear = computed(() => new Date().getFullYear())

const {
  rows,
  samplingParams,
  populationManual,
  auditNote,
  auditConclusion,
  linkedDecrease,
  summary,
  populationDrift,
  addRow,
  deleteRow,
  updateCell,
  updateSamplingParams,
  syncPopulationFromLinked,
  importFromH82,
  fillLiabilityFromH9,
  syncToH9,
  syncAllToH9,
  saveNote,
  saveConclusion,
  draftNote,
  draftConclusion,
  rowClassName,
  load,
} = useH8DisposalCheck({
  wpId,
  projectId,
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const h8ReloadAll = inject<() => Promise<void>>('h8ReloadAll', async () => {})
const { isExporting, isImporting, exportTemplate, exportData, importData } = useH8ImportExport({
  wpId,
  projectId,
  sheetCode: 'H8-12',
  onImported: async () => {
    await h8ReloadAll()
    load()
  },
})
const ieBusy = computed(() => isExporting.value || isImporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(['H8-12'])
  else if (cmd === 'export-data') await exportData(['H8-12'])
  else if (cmd === 'import-data') fileInputRef.value?.click()
}
async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData(file, ['H8-12'])
  ;(e.target as HTMLInputElement).value = ''
}

const coverageTagType = computed(() => {
  const rate = summary.value.coverageRate
  const pop = samplingParams.value.populationAmount
  if (pop <= 0) return 'info'
  if (rate < 20) return 'danger'
  if (rate < 40) return 'warning'
  return 'success'
})

function fmtAmt(v: number): string {
  if (v == null || Number(v) === 0) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入合同号/资产编号', '新增减少检查行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如：LEASE-2024-001',
    })
    addRow(value || '')
  } catch {
    /* cancel */
  }
}

function onImportFromH82() {
  const { imported } = importFromH82()
  if (imported === 0) {
    ElMessage.warning('H8-2 无已填终止日的明细行可带入')
    return
  }
  ElMessage.success(`已从 H8-2 带入/合并 ${imported} 笔终止样本`)
}

function onFillLiabilityFromH9() {
  const { matched } = fillLiabilityFromH9()
  if (matched === 0) {
    ElMessage.warning('未匹配到 H9-2 合同号，请确认合同号一致')
    return
  }
  ElMessage.success(`已按合同号从 H9-2 填充 ${matched} 笔负债余额`)
}

async function onSyncAllToH9() {
  const n = summary.value.unsyncedH9Count
  if (n <= 0) return
  try {
    await ElMessageBox.confirm(
      `将把 ${n} 笔未同步样本标记为已同步，并通知 H9 终止确认。是否继续？`,
      '批量同步 H9',
      { type: 'warning', confirmButtonText: '同步', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const synced = syncAllToH9()
  ElMessage.success(`已批量同步 ${synced} 笔至 H9`)
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'H8',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => emit('save', itemId, { remark }),
  isReadonly: computed(() => props.isReadonly === true),
})

function onSampleFilled(payload: { samples?: SampledVoucher[] }) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  showSampling.value = false
  const items = payload?.samples || []
  if (!items.length) return
  for (const item of items) {
    addRow(String(item.summary || item.voucherNo || ''))
    const last = rows.value[rows.value.length - 1]
    if (!last) continue
    if (item.voucherNo) updateCell(last.rowId, 'voucherNo', item.voucherNo)
    const amt = Math.abs(Number(item.creditAmount ?? item.debitAmount) || 0)
    if (amt) updateCell(last.rowId, 'rouCost', amt)
    if (item.voucherDate) updateCell(last.rowId, 'reductionDate', item.voucherDate)
    if (item.counterpartAccount) updateCell(last.rowId, 'oppositeAccount', item.counterpartAccount)
  }
}

function getTableSummary({ columns }: { columns: any[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop === 'rouCost' || col.label === '原值') return fmtAmt(summary.value.checkedAmount)
    if (col.label === '净值') return fmtAmt(summary.value.checkedNetValue)
    if (col.label === '终止损益') {
      const t = summary.value.gainLossTotal
      return `${t >= 0 ? '+' : ''}${fmtAmt(t)}`
    }
    return ''
  })
}
</script>

<style scoped>
.h8-tab-disposal-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; }
.obj-list { margin: 6px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }

.tab-toolbar {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
}
.chip-wrap { display: inline-flex; }

.check-alert { margin-bottom: 8px; }

.block-card, .audit-note-card { margin-bottom: 16px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.section-header-actions { display: flex; gap: 6px; align-items: center; }

.test-content-hint {
  font-size: 12px; color: var(--el-text-color-regular); background: #f8fafc;
  border-radius: 6px; padding: 10px 12px;
}
.test-content-hint ol { margin: 4px 0 0; padding-left: 18px; }
.hint-note { margin: 8px 0 0; color: var(--el-text-color-secondary); }

.pop-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.src-tag { margin-left: 2px; }
.param-label { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }
.specific-sample {
  display: flex; align-items: center; gap: 8px; margin-top: 10px;
}

.check-table { font-size: var(--wp-font-size, 13px); width: 100%; }
.amt-input { width: 100%; }
.amt-cell, .formula-cell {
  font-variant-numeric: tabular-nums;
}
.formula-cell {
  border-bottom: 1px dashed #d97706; cursor: help; background: #fefce8;
  display: inline-block; padding: 0 4px; border-radius: 2px;
}
.gain { color: #16a34a; }
.loss { color: #dc2626; }
.warn-coverage { color: #dc2626; font-weight: 600; }

.h9-sync-cell {
  display: flex; align-items: center; gap: 4px; justify-content: center; flex-wrap: wrap;
}

.summary-block {
  margin-top: 10px; padding: 10px 12px; background: #f8fafc; border-radius: 6px; font-size: 12px;
}
.summary-line { margin-bottom: 4px; }
.summary-line.muted, .muted { color: var(--el-text-color-secondary); }
.sep { margin-left: 12px; }

.stats-row { display: flex; gap: 12px; margin-top: 12px; }
.stat-card { flex: 1; text-align: center; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.stat-value { font-size: 18px; font-weight: 700; color: var(--el-color-primary); }

.action-bar { margin-top: 12px; display: flex; gap: 8px; }

.edit-tips {
  margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary);
}
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 20px; margin-top: 8px; line-height: 1.6; }

:deep(.row-abnormal) { background: #fef2f2 !important; }
:deep(.row-unsynced) td:first-child { box-shadow: inset 3px 0 0 #f59e0b; }
:deep(.row-incomplete) { background: #fffbeb !important; }
</style>
