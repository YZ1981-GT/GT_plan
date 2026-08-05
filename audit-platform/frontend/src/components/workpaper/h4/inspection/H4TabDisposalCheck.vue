<template>
  <div class="h4-tab-disposal-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>核实已记录的工程物资减少确已发生，且已记入恰当账户（存在/发生）</li>
        <li>核实所有应记录的工程物资减少均已入账，相关披露完整（完整性/截止）</li>
        <li>核实减少金额准确（含减值结转、清理净损益），计价与列报恰当（准确性/计价）</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H4-5" :context-project-id="projectId" /></span>
      <GtIndexChip value="wp:H4-2" :context-project-id="projectId" context="明细勾稽" />
      <GtIndexChip value="wp:H2-1" :context-project-id="projectId" context="领用→在建" />
      <GtIndexChip value="wp:H4-9" :context-project-id="projectId" context="关联方" />
      <el-tag size="small" type="info">样本 {{ rows.length }} 项</el-tag>
      <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">
        异常 {{ summary.anomalyCount }} 项
      </el-tag>
      <el-tag v-if="missingH2Refs.length > 0" size="small" type="warning">
        H2缺口 {{ missingH2Refs.length }} 项
      </el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ summary.coverageRate.toFixed(2) }}%
      </el-tag>
      <el-button size="small" @click="emit('navigate-sheet', 'H4-4')">← H4-4</el-button>
      <el-button size="small" @click="emit('navigate-sheet', 'H4-6')">H4-6 →</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="warning"
        plain
        :disabled="summary.anomalyCount === 0"
        @click="onPushAje"
      >
        推送拟调整→H4-3
      </el-button>
    </div>

    <el-alert
      v-if="missingH2Refs.length > 0"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`${missingH2Refs.length} 行「领用出库」未填写对应 H2 编号，须补齐并与在建工程核对。`"
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
              @click="onSyncPopulation"
            >
              从 {{ linkedDecrease.source || 'H4-2' }} 带入本期减少
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
          <li v-for="(item, i) in H4_DISPOSAL_TEST_CONTENT_ITEMS" :key="i">{{ item }}</li>
        </ol>
        <p class="hint-note">
          特定样本优先：大额、关联方、异常出库、长期积压后处置；其余按抽样方法抽取。
          领用出库须填写对应 H2 编号并与在建工程勾稽。
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
              源 H4-2: {{ fmtAmt(linkedDecrease.amount) }}
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
          placeholder="大额、关联方、异常减少、报废/出售等全部测试说明…"
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
        :title="`总体与 H4-2（${fmtAmt(linkedDecrease.amount)}）不一致，可重新带入或保留手工数。`"
      />
      <div v-if="linkedDecrease.amount > 0" class="linked-breakdown">
        明细构成：领用 {{ fmtAmt(linkedDecrease.usage) }}
        ／退货 {{ fmtAmt(linkedDecrease.returnAmt) }}
        ／报废 {{ fmtAmt(linkedDecrease.scrap) }}
        ／其他 {{ fmtAmt(linkedDecrease.other) }}
      </div>
    </el-card>

    <!-- 三、测试 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、测试 — 本期减少检查明细（H4-5）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H4-5')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="520"
        class="check-table"
        row-key="rowId"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="seq" label="序号" width="48" fixed align="center" />

        <el-table-column label="工程物资" align="center">
          <el-table-column label="类别" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.category" size="small"
                @change="updateCell(row.rowId, 'category', $event)" />
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="名称" min-width="110" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.name" size="small"
                @change="updateCell(row.rowId, 'name', $event)" />
              <span v-else>{{ row.name || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="入账凭证号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
              @change="updateCell(row.rowId, 'voucherNo', $event)" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="减少方式" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.disposalMethod" size="small" style="width:98px"
              @change="updateCell(row.rowId, 'disposalMethod', $event)">
              <el-option v-for="opt in DISPOSAL_METHOD_OPTS" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-tag v-else size="small" :type="methodTagType(row.disposalMethod)">
              {{ row.disposalMethod || '-' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="对方科目" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.oppositeAccount" size="small"
              placeholder="如在建工程"
              @change="updateCell(row.rowId, 'oppositeAccount', $event)" />
            <span v-else>{{ row.oppositeAccount || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="数量" width="70" align="right">
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
              <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'originalCost', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.originalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'impairment', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="净值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="原值−减值准备">{{ fmtAmt(row.netValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="清理费用" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.disposalCost" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'disposalCost', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.disposalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="清理收入" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.disposalIncome" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'disposalIncome', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.disposalIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="清理净损益" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="清理收入−清理费用−净值">{{ fmtAmt(row.disposalNetPl) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="支持性文件" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.supportingDocs"
              size="small"
              :placeholder="getEvidenceHint(row.disposalMethod)"
              @change="updateCell(row.rowId, 'supportingDocs', $event)"
            />
            <span v-else>{{ row.supportingDocs || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="对应H2" min-width="110">
          <template #default="{ row }">
            <div class="h2-ref-cell">
              <el-input
                v-if="!isReadonly"
                v-model="row.h2Ref"
                size="small"
                :class="{ 'h2-warning': row.disposalMethod === '领用出库' && !row.h2Ref }"
                placeholder="领用必填"
                @change="updateCell(row.rowId, 'h2Ref', $event)"
              />
              <span v-else>{{ row.h2Ref || '-' }}</span>
              <el-button
                v-if="row.h2Ref"
                size="small"
                type="primary"
                link
                class="chip-jump"
                @click="handleJumpH2(row.h2Ref)"
              >↗H2</el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="核对内容" align="center">
          <el-table-column
            v-for="(_item, ci) in H4_DISPOSAL_TEST_CONTENT_ITEMS"
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
        <el-table-column label="关联方名称" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isRelatedParty === '是'"
              v-model="row.relatedPartyName" size="small"
              @change="updateCell(row.rowId, 'relatedPartyName', $event)"
            />
            <span v-else>{{ row.isRelatedParty === '是' ? (row.relatedPartyName || '-') : '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="备注说明" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="updateCell(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="抽凭" width="55" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="onRowSample(row)">抽凭</el-button>
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
          合计：数量 —
          原值 <strong>{{ fmtAmt(summary.checkedAmount) }}</strong>
          <span class="sep">检查比例
            <strong :class="{ 'warn-coverage': summary.coverageRate < 20 && samplingParams.populationAmount > 0 }">
              {{ summary.coverageRate.toFixed(2) }}%
            </strong>
          </span>
        </div>
        <div class="summary-line muted">
          本期减少工程物资贷合计（总体）：{{ fmtAmt(samplingParams.populationAmount) }}
          <span v-if="samplingParams.populationAmount <= 0">（未填总体时检查比例显示 0%，避免除零）</span>
        </div>
      </div>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" type="primary" @click="handleAddRow">+ 添加检查行</el-button>
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
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计说明</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="onDraftNote">起草说明</el-button>
            <el-button size="small" circle @click="openReview('H4-5-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="若检查比例偏低，扩大样本量或说明原因；概述领用→H2勾稽、报废/出售清理损益及异常事项。"
        :disabled="isReadonly"
        @blur="saveNote(auditNote)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>五、审计结论</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="onDraftConclusion">起草结论</el-button>
            <el-button size="small" circle @click="openReview('H4-5-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="基于上述检查，就是否实现一、审计目标发表结论；列明拟调整事项（→ H4-3）及范围受限影响。"
        :disabled="isReadonly"
        @blur="saveConclusion(auditConclusion)"
      />
    </el-card>

    <details class="edit-tips" open>
      <summary>提示（编制要点）</summary>
      <ol>
        <li>本表用于汇总本年度工程物资减少（领用/退货/报废/盘亏/出售等）的测试情况。</li>
        <li>净值 = 原值 − 减值准备；清理净损益 = 清理收入 − 清理费用 − 净值（领用/退货无清理收支时记 0）。</li>
        <li>领用出库须填写对应 H2 编号，并与在建工程物资消耗勾稽；点击 ↗H2 可跳转。</li>
        <li>检查比例 = 样本原值合计 ÷ 本期减少贷方总体（覆盖率，非与 H4-1 全量平衡）；总体未填时显示 0%（避免 #DIV/0!）。</li>
        <li>关联方出售/退货可在「是否关联方」标记后，于 H4-9 一键带入。</li>
        <li>核对内容第 5 项：领用与 H2 一致，或处置清理净损益计算正确。</li>
      </ol>
    </details>

    <el-dialog
      v-model="showSampling"
      title="抽凭引擎（科目 1605 工程物资-减少）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSampling && wpId && projectId"
        :project-id="projectId"
        :workpaper-id="wpId"
        account-code="1605"
        phase="final"
        :year="year ?? new Date().getFullYear()"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabDisposalCheck.vue — H4-5 减少检查表
 * 对齐致同：目标 → 样本选取 → 测试（原值/减值/净值/清理损益 + 核对1–5）
 * → 检查比例 → 说明/结论；平台增强 H2 联动 + 关联方预埋
 */
import { computed, inject, toRef, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH4DisposalCheck,
  DISPOSAL_METHOD_OPTS,
  SAMPLING_METHOD_OPTS,
  H4_DISPOSAL_TEST_CONTENT_ITEMS,
  getEvidenceHint,
  type H4DisposalCheckRow,
} from '../../composables/useH4DisposalCheck'
import { useH4ImportExport } from '../../composables/useH4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  wpId: string
  projectId: string
  year?: number
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)
const isReadonly = toRef(props, 'isReadonly')
const projectId = toRef(props, 'projectId')
const wpId = toRef(props, 'wpId')

const {
  rows,
  samplingParams,
  populationManual,
  auditNote,
  auditConclusion,
  linkedDecrease,
  summary,
  missingH2Refs,
  populationDrift,
  addRow,
  deleteRow,
  updateCell,
  updateSamplingParams,
  syncPopulationFromH42,
  saveNote,
  saveConclusion,
  draftNote,
  draftConclusion,
  pushAjeDraftToH43,
  rowClassName,
  load,
} = useH4DisposalCheck({
  wpId,
  projectId,
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
    saveResponse(itemId, value)
  },
})

const importExport = useH4ImportExport({
  wpId,
  projectId,
  onImported: () => load(),
})

const showSampling = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const samplingRowId = ref<string | null>(null)

const coverageTagType = computed(() => {
  if (samplingParams.value.populationAmount <= 0) return 'info'
  if (summary.value.coverageRate < 20) return 'danger'
  if (summary.value.coverageRate < 50) return 'warning'
  return 'success'
})

function methodTagType(method: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  switch (method) {
    case '领用出库': return 'success'
    case '退货': return 'warning'
    case '报废':
    case '盘亏': return 'danger'
    case '出售': return 'warning'
    default: return 'info'
  }
}

function onSyncPopulation() {
  if (syncPopulationFromH42()) ElMessage.success('已从 H4-2 带入本期减少合计')
  else ElMessage.warning('H4-2 尚无减少发生额，请先完善明细表')
}

function onDraftNote() {
  draftNote()
  ElMessage.success('已起草审计说明，可继续编辑')
}

function onDraftConclusion() {
  draftConclusion()
  ElMessage.success('已起草审计结论，可继续编辑')
}

function onPushAje() {
  const res = pushAjeDraftToH43()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加检查行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleJumpH2(h2Ref: string) {
  const target = h2Ref.startsWith('H2') ? h2Ref : 'H2-1'
  emit('navigate-sheet', target)
}

function onRowSample(row: H4DisposalCheckRow) {
  samplingRowId.value = row.rowId
  showSampling.value = true
}

const rawMethodologyPersist = buildChecklistDirectPersist({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const methodologyDirectPersist = rawMethodologyPersist
/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'H4',
  allResponses: toRef(props, 'allResponses') as never,
  persist: methodologyDirectPersist,
  isReadonly: computed(() => props.isReadonly === true),
})

function onSampleFilled(payload: any) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  // 抽凭引擎 emit 结构为 { samples, phase, fillMode, ... }；样本字段为 SampledVoucher
  // （voucherNo/debitAmount/creditAmount/summary）。兼容历史数组/rows 结构。
  const list = Array.isArray(payload) ? payload : (payload?.samples || payload?.rows || [])
  if (!list.length) {
    showSampling.value = false
    return
  }
  const amountOf = (v: any): number =>
    Number(v.amount ?? v.debitAmount ?? v.creditAmount ?? v.credit ?? v.debit) || 0
  if (samplingRowId.value) {
    const first = list[0]
    const row = rows.value.find(r => r.rowId === samplingRowId.value)
    if (row && first) {
      if (first.voucherNo || first.voucher_no) {
        updateCell(row.rowId, 'voucherNo', first.voucherNo || first.voucher_no)
      }
      const amt = amountOf(first)
      if (amt) updateCell(row.rowId, 'originalCost', Math.abs(amt))
      if (first.summary || first.abstract) {
        updateCell(row.rowId, 'supportingDocs', first.summary || first.abstract)
      }
    }
  } else {
    for (const item of list) {
      const name = item.accountName || item.name || item.summary || '抽凭样本'
      addRow(String(name).slice(0, 40))
      const last = rows.value[rows.value.length - 1]
      if (!last) continue
      if (item.voucherNo || item.voucher_no) {
        updateCell(last.rowId, 'voucherNo', item.voucherNo || item.voucher_no)
      }
      const amt = amountOf(item)
      if (amt) updateCell(last.rowId, 'originalCost', Math.abs(amt))
    }
  }
  samplingRowId.value = null
  showSampling.value = false
  ElMessage.success('抽凭结果已填入')
}

async function handleImportExport(command: string) {
  if (command === 'export-template') await importExport.exportTemplate('H4-5')
  else if (command === 'export-data') await importExport.exportData('H4-5')
  else if (command === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  await importExport.importData('H4-5', file)
  load()
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '0.00'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-disposal-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; margin-bottom: 4px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }

.tab-toolbar {
  display: flex; justify-content: flex-end; align-items: center;
  gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.check-alert { margin-bottom: 8px; }

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.block-card { margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }

.test-content-hint {
  font-size: 12px; color: var(--el-text-color-regular); line-height: 1.55;
  background: var(--el-fill-color-lighter); border-radius: 6px; padding: 10px 12px;
}
.test-content-hint ol { margin: 4px 0 0; padding-left: 18px; }
.hint-note { margin: 8px 0 0; color: var(--el-text-color-secondary); }

.pop-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.src-tag { margin-left: 2px; }
.specific-sample {
  display: flex; align-items: center; gap: 8px; margin-top: 10px;
}
.param-label { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }
.linked-breakdown {
  margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary);
}

.check-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  display: block; text-align: right; font-variant-numeric: tabular-nums;
  color: var(--el-color-primary); font-weight: 500;
}
.warn-coverage { color: var(--el-color-danger); font-weight: 600; }

.h2-ref-cell { display: flex; align-items: center; gap: 4px; }
.h2-warning :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset !important; background: #fdf6ec;
}
.chip-jump { font-size: 11px; padding: 0 4px; white-space: nowrap; }

.summary-block {
  margin-top: 10px; padding: 10px 12px;
  background: var(--el-fill-color-lighter); border-radius: 6px;
  font-size: 12px; line-height: 1.7;
}
.summary-line .sep { margin-left: 12px; }
.muted { color: var(--el-text-color-secondary); }

.action-bar { display: flex; align-items: center; gap: 8px; margin-top: 10px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 20px; margin-top: 8px; line-height: 1.6; }

:deep(.row-anomaly) { background: #fef0f0 !important; }
:deep(.row-warn) { background: #fdf6ec !important; }
</style>
