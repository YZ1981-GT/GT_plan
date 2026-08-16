<template>
  <div class="h8-tab-related-party">
    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <span class="objective-title">一、审计目标</span>
      </template>
      <div class="objective-body">
        <p>
          <b>使用权资产：</b>1. 资产负债表中记录的使用权资产是存在的，且已记录于恰当的账户；
          2. 所有应记录的使用权资产均已记录，相关披露均已包括；
          3. 记录的使用权资产由被审计单位拥有或控制；
          4. 使用权资产以恰当金额包括在财务报表中，计价或分摊调整已恰当记录；
          5. 使用权资产已恰当分类/列报，关联方租赁披露完整。
        </p>
        <p>
          <b>租赁负债：</b>1. 资产负债表中记录的租赁负债是存在的，且已记录于恰当的账户；
          2. 所有应记录的租赁负债均已记录，相关披露均已包括；
          3. 记录的租赁负债是被审计单位应当履行的现时义务；
          4. 租赁负债以恰当金额包括在财务报表中；
          5. 租赁负债已恰当分类/列报，关联方交易披露完整。
        </p>
      </div>
    </el-alert>

    <!-- 编制思路 -->
    <div class="methodology-context">
      <p class="procedure-label">二、审计过程 — 编制思路</p>
      <p>
        识别合并范围外关联方租赁 → 分别登记使用权资产与租赁负债审定数 →
        核对定价政策与市场租金（价差率=(年租金−市场租金)/市场租金×100%，绝对值&gt;10%重点关注）→
        评估是否异常 → 与 H8-2/H9 及附注关联方披露勾稽 → 形成审计说明与结论。
      </p>
    </div>

    <!-- 工具栏 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-14" :context-project-id="projectId" />
      <GtIndexChip value="wp:H8-2" :context-project-id="projectId" context="明细表" />
      <GtIndexChip value="wp:H9" :context-project-id="projectId" context="租赁负债" />
      <el-tag size="small" type="info">使用权资产 {{ summary.rouCount }} 笔</el-tag>
      <el-tag size="small" type="info">租赁负债 {{ summary.liabCount }} 笔</el-tag>
      <el-tag v-if="summary.highDiffCount" size="small" type="danger">
        价差率&gt;10% {{ summary.highDiffCount }}
      </el-tag>
      <el-tag v-if="summary.abnormalCount" size="small" type="warning">
        异常 {{ summary.abnormalCount }}
      </el-tag>
    </div>

    <!-- 操作栏 -->
    <div v-if="!isReadonly" class="action-bar">
      <el-button size="small" type="primary" @click="onImportH82">从 H8-2 带入</el-button>
      <el-button size="small" :disabled="!rouRows.length" @click="onDraftNote">生成审计说明</el-button>
      <el-dropdown size="small" @command="handleExportCommand">
        <el-button size="small" :loading="importing">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
      <el-button size="small" type="primary" plain @click="$emit('open-ai', 'related-party')">AI 辅助</el-button>
      <el-button size="small" @click="$emit('open-review', 'related-party')">复核</el-button>
    </div>

    <!-- 1. 使用权资产 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="section-title">
          <span>1. 使用权资产（关联方租赁）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="addRouRow">+ 新增行</el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="rouRows"
        border
        size="small"
        class="formula-table"
        :row-class-name="rouRowClass"
        show-summary
        :summary-method="rouSummary"
        max-height="420"
      >
        <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
        <el-table-column prop="relatedPartyName" label="关联单位名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.relatedPartyName"
              size="small"
              @change="updateRouCell(row.rowId, 'relatedPartyName', row.relatedPartyName)"
            />
            <span v-else>{{ row.relatedPartyName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联方关系" min-width="150">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.relationship"
              size="small"
              filterable
              allow-create
              default-first-option
              placeholder="选择"
              @change="updateRouCell(row.rowId, 'relationship', row.relationship)"
            >
              <el-option v-for="opt in relationshipOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.relationship || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseItem" label="租赁项目" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.leaseItem"
              size="small"
              @change="updateRouCell(row.rowId, 'leaseItem', row.leaseItem)"
            />
            <span v-else>{{ row.leaseItem || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetType" label="租赁资产种类" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.assetType"
              size="small"
              allow-create
              filterable
              @change="updateRouCell(row.rowId, 'assetType', row.assetType)"
            >
              <el-option v-for="t in assetTypeOptions" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.assetType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leasePeriod" label="租赁发生时间及到期日" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.leasePeriod"
              size="small"
              placeholder="起租日 ~ 到期日"
              @change="updateRouCell(row.rowId, 'leasePeriod', row.leasePeriod)"
            />
            <span v-else>{{ row.leasePeriod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="costEnding" label="原值期末审定" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.costEnding"
              size="small"
              @change="(v: number | undefined) => updateRouCell(row.rowId, 'costEnding', v)"
            />
            <span v-else>{{ fmtAmt(row.costEnding) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accumDepEnding" label="累计折旧期末" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.accumDepEnding"
              size="small"
              @change="(v: number | undefined) => updateRouCell(row.rowId, 'accumDepEnding', v)"
            />
            <span v-else>{{ fmtAmt(row.accumDepEnding) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentEnding" label="减值准备期末" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.impairmentEnding"
              size="small"
              @change="(v: number | undefined) => updateRouCell(row.rowId, 'impairmentEnding', v)"
            />
            <span v-else>{{ fmtAmt(row.impairmentEnding) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净值" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="原值−累计折旧−减值准备">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="additionsCost" label="本期新增(原值)" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.additionsCost"
              size="small"
              @change="(v: number | undefined) => updateRouCell(row.rowId, 'additionsCost', v)"
            />
            <span v-else>{{ fmtAmt(row.additionsCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="periodDep" label="本期折旧" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.periodDep"
              size="small"
              @change="(v: number | undefined) => updateRouCell(row.rowId, 'periodDep', v)"
            />
            <span v-else>{{ fmtAmt(row.periodDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingPolicy" label="定价政策" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.pricingPolicy"
              size="small"
              placeholder="市场价/协议价"
              @change="updateRouCell(row.rowId, 'pricingPolicy', row.pricingPolicy)"
            />
            <span v-else>{{ row.pricingPolicy || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualRent" label="年租金" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.annualRent"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateRouCell(row.rowId, 'annualRent', v)"
            />
            <span v-else>{{ fmtAmt(row.annualRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketRent" label="市场租金" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.marketRent"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateRouCell(row.rowId, 'marketRent', v)"
            />
            <span v-else>{{ fmtAmt(row.marketRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价差率(%)" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-value"
              :class="{ abnormal: Math.abs(row.priceDiffRate) > DIFF_WARN_THRESHOLD }"
              title="(年租金−市场租金)/市场租金×100%"
            >
              {{ row.marketRent > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="isAbnormal" label="是否存在异常" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.isAbnormal"
              size="small"
              @change="updateRouCell(row.rowId, 'isAbnormal', row.isAbnormal)"
            >
              <el-option v-for="o in abnormalOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.isAbnormal || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              @change="updateRouCell(row.rowId, 'remark', row.remark)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="indexNo" label="索引号" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.indexNo"
              size="small"
              placeholder="合同号"
              @change="updateRouCell(row.rowId, 'indexNo', row.indexNo)"
            />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" title="生成配对负债行" @click="pairLiabilityFromRou(row.rowId)">
              配对负债
            </el-button>
            <el-button type="danger" link size="small" @click="removeRouRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 2. 租赁负债 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="section-title">
          <span>2. 租赁负债（关联方租赁）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="addLiabRow">+ 新增行</el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="liabRows"
        border
        size="small"
        class="formula-table"
        :row-class-name="liabRowClass"
        show-summary
        :summary-method="liabSummary"
        max-height="360"
      >
        <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
        <el-table-column prop="relatedPartyName" label="关联方名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.relatedPartyName"
              size="small"
              @change="updateLiabCell(row.rowId, 'relatedPartyName', row.relatedPartyName)"
            />
            <span v-else>{{ row.relatedPartyName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联方关系" min-width="150">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.relationship"
              size="small"
              filterable
              allow-create
              default-first-option
              @change="updateLiabCell(row.rowId, 'relationship', row.relationship)"
            >
              <el-option v-for="opt in relationshipOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.relationship || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseItem" label="租赁项目" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.leaseItem"
              size="small"
              @change="updateLiabCell(row.rowId, 'leaseItem', row.leaseItem)"
            />
            <span v-else>{{ row.leaseItem || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetType" label="租赁资产种类" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.assetType"
              size="small"
              allow-create
              filterable
              @change="updateLiabCell(row.rowId, 'assetType', row.assetType)"
            >
              <el-option v-for="t in assetTypeOptions" :key="t" :label="t" :value="t" />
            </el-select>
            <span v-else>{{ row.assetType || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leasePeriod" label="租赁发生时间及到期日" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.leasePeriod"
              size="small"
              @change="updateLiabCell(row.rowId, 'leasePeriod', row.leasePeriod)"
            />
            <span v-else>{{ row.leasePeriod || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="liabilityEnding" label="负债期末审定" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.liabilityEnding"
              size="small"
              @change="(v: number | undefined) => updateLiabCell(row.rowId, 'liabilityEnding', v)"
            />
            <span v-else>{{ fmtAmt(row.liabilityEnding) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="periodPayments" label="本期应支付租赁款" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.periodPayments"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateLiabCell(row.rowId, 'periodPayments', v)"
            />
            <span v-else>{{ fmtAmt(row.periodPayments) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="periodInterest" label="本期利息支出" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.periodInterest"
              size="small"
              @change="(v: number | undefined) => updateLiabCell(row.rowId, 'periodInterest', v)"
            />
            <span v-else>{{ fmtAmt(row.periodInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingPolicy" label="定价政策" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.pricingPolicy"
              size="small"
              @change="updateLiabCell(row.rowId, 'pricingPolicy', row.pricingPolicy)"
            />
            <span v-else>{{ row.pricingPolicy || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualRent" label="年租金" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.annualRent"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateLiabCell(row.rowId, 'annualRent', v)"
            />
            <span v-else>{{ fmtAmt(row.annualRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketRent" label="市场租金" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.marketRent"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateLiabCell(row.rowId, 'marketRent', v)"
            />
            <span v-else>{{ fmtAmt(row.marketRent) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价差率(%)" width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span
              class="formula-value"
              :class="{ abnormal: Math.abs(row.priceDiffRate) > DIFF_WARN_THRESHOLD }"
            >
              {{ row.marketRent > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="isAbnormal" label="是否存在异常" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.isAbnormal"
              size="small"
              @change="updateLiabCell(row.rowId, 'isAbnormal', row.isAbnormal)"
            >
              <el-option v-for="o in abnormalOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.isAbnormal || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              @change="updateLiabCell(row.rowId, 'remark', row.remark)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="indexNo" label="索引号" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.indexNo"
              size="small"
              @change="updateLiabCell(row.rowId, 'indexNo', row.indexNo)"
            />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeLiabRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="请输入审计说明..."
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="请输入审计结论..."
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>本表仅登记<strong>合并范围外</strong>关联方租赁；使用权资产与租赁负债宜成对核查。</li>
        <li>净值 = 原值期末 − 累计折旧期末 − 减值准备期末；可与 H8-2 明细勾稽。</li>
        <li>价差率&gt;10%：关注定价合理性，是否存在利益输送；异常项须在备注说明依据。</li>
        <li>关联方关系选项对齐准则列举（母公司/实际控制人/控股股东/联营合营/关键管理人员等）。</li>
        <li>租赁负债金额、利息支出应与 H9 租赁负债底稿交叉验证。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H8TabRelatedParty.vue — H8-14 关联交易检查表
 * 对齐 Excel 双表（使用权资产 + 租赁负债）+ 价差率数字化增强
 */
import { toRef, computed, ref, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useH8RelatedParty,
  RELATED_PARTY_RELATIONSHIPS,
  ASSET_TYPE_OPTIONS,
  ABNORMAL_OPTIONS,
  type H8RelatedPartyRouRow,
  type H8RelatedPartyLiabRow,
} from '../../composables/useH8RelatedParty'
import { useH8ImportExport } from '../../composables/useH8ImportExport'

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

const allResponsesRef = toRef(props, 'allResponses')
const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')

const {
  rouRows,
  liabRows,
  auditNote,
  auditConclusion,
  summary,
  addRouRow,
  removeRouRow,
  updateRouCell,
  pairLiabilityFromRou,
  addLiabRow,
  removeLiabRow,
  updateLiabCell,
  importFromH82,
  saveAuditNote,
  saveAuditConclusion,
  draftAuditNote,
  load,
  DIFF_WARN_THRESHOLD,
} = useH8RelatedParty({
  allResponses: allResponsesRef,
  onSave: (itemId, value) => emit('save', itemId, value),
})

const relationshipOptions = RELATED_PARTY_RELATIONSHIPS
const assetTypeOptions = ASSET_TYPE_OPTIONS
const abnormalOptions = ABNORMAL_OPTIONS

const h8ReloadAll = inject<() => Promise<void>>('h8ReloadAll', async () => {})
const { isImporting, exportTemplate, exportData, importData } = useH8ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
  sheetCode: 'H8-14',
  onImported: async () => {
    await h8ReloadAll()
    load()
  },
})
const importing = computed(() => isImporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

function fmtAmt(v: number): string {
  if (v == null || Number(v) === 0) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rouRowClass({ row }: { row: H8RelatedPartyRouRow }) {
  if (row.isAbnormal === '是' || Math.abs(row.priceDiffRate) > DIFF_WARN_THRESHOLD) return 'abnormal-row'
  return ''
}

function liabRowClass({ row }: { row: H8RelatedPartyLiabRow }) {
  if (row.isAbnormal === '是' || Math.abs(row.priceDiffRate) > DIFF_WARN_THRESHOLD) return 'abnormal-row'
  return ''
}

function rouSummary({ columns, data }: { columns: any[]; data: H8RelatedPartyRouRow[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (['costEnding', 'accumDepEnding', 'impairmentEnding', 'netValue', 'additionsCost', 'periodDep', 'annualRent'].includes(prop)) {
      const sum = data.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0)
      return fmtAmt(sum)
    }
    if (col.label === '净值') {
      return fmtAmt(data.reduce((s, r) => s + (r.netValue || 0), 0))
    }
    return ''
  })
}

function liabSummary({ columns, data }: { columns: any[]; data: H8RelatedPartyLiabRow[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (['liabilityEnding', 'periodPayments', 'periodInterest', 'annualRent'].includes(prop)) {
      const sum = data.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0)
      return fmtAmt(sum)
    }
    return ''
  })
}

async function onImportH82() {
  const result = importFromH82()
  if (result.added === 0) {
    ElMessage.info(result.total === 0 ? 'H8-2 暂无明细可带入' : `无可新增行（已存在 ${result.skipped} 笔）`)
  } else {
    ElMessage.success(`已从 H8-2 带入 ${result.added} 笔，请确认关联方关系与定价政策`)
  }
}

async function onDraftNote() {
  const text = draftAuditNote()
  if (auditNote.value?.trim()) {
    try {
      await ElMessageBox.confirm('将覆盖现有审计说明，是否继续？', '生成审计说明', { type: 'warning' })
    } catch {
      return
    }
  }
  saveAuditNote(text)
  ElMessage.success('已生成审计说明草稿')
}

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(['H8-14', 'H8-14L'])
  else if (cmd === 'export-data') await exportData(['H8-14', 'H8-14L'])
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData(file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}
</script>

<style scoped>
.h8-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.objective-title { font-weight: 600; }
.objective-body { font-size: 12px; line-height: 1.6; margin: 0; }
.objective-body p { margin: 4px 0; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 12px; font-size: 12px; color: #92400e;
}
.procedure-label { font-weight: 600; margin: 0 0 4px; }

.h8-tab-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.action-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; align-items: center; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.table-card { margin-bottom: 16px; }
.formula-table { font-size: var(--wp-font-size, 13px); }
.formula-table :deep(.formula-col) { background: #fefce8; }
.formula-table :deep(.abnormal-row) { background: #fef2f2 !important; }
.formula-value { border-bottom: 1px dashed #d97706; cursor: help; color: #d97706; }
.formula-value.abnormal { color: #dc2626; font-weight: 700; }

.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
