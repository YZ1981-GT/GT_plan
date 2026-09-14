<template>
  <div class="gt-confirmation-alternative-g06">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-alternative-g06__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：alternative-g06-v1 -->
    <template v-else>
      <!-- 工具栏 -->
      <div class="gt-confirmation-alternative-g06__toolbar">
        <div class="gt-confirmation-alternative-g06__toolbar-left">
          <span class="gt-confirmation-alternative-g06__title">G0-6 投资循环替代程序</span>
          <GtIndexChip value="wp:G0-6" />
          <el-tag size="small" type="info" effect="plain">共 {{ data.companies.value.length }} 家</el-tag>
        </div>
        <div class="gt-confirmation-alternative-g06__toolbar-right">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
          <GtReviewTrigger section-id="G0-6-alternative" label="复核" />
        </div>
      </div>

      <!-- 顶部说明 -->
      <div class="gt-confirmation-alternative-g06__header-tip">
        <el-alert type="info" :closable="true" show-icon>
          提示③：对回函可能性不高的、余额重大的，发函同时执行替代程序。
        </el-alert>
      </div>

      <!-- 编制提示 -->
      <details class="gt-confirmation-alternative-g06__tips">
        <summary>编制提示</summary>
        <p>
          依据 CAS 1312《函证》：对回函可能性不高或余额重大的投资，发函同时执行替代程序。
          源模板 <b>替代程序检查表G0-6</b> 的检查过程记录分三区：
          ①检查初始投资协议、公司章程等（被投资单位／投资比例／投资金额／投资条款）
          ②检查本期发生额（借方、贷方各一区；记账凭证 + 支持性文件1／支持性文件2 各三要素）
          ③检查期后是否被出售或赎回（记账凭证 + 投资协议·交易确认单·交割单 + 银行回单）。
          ④为源外增强区（持仓证明／股利收入／公允价值佐证），非源模板列，逐列登记于
          <code>G06_SOURCE_EXTRA</code>，用于承接既有数据并支持证券类投资的补充核查。
        </p>
        <p class="src-hint">
          源模板编制说明（逐字）：①检查期初原始投资协议、期后出售或赎回协议；②检查原始凭证：合同、交易流水、银行回单、支票存根等；③对回函可能性不高的、余额重大的，发函同时执行替代程序。
        </p>
      </details>

      <!-- 看板 -->
      <AlternativeD05Dashboard :metrics="data.metrics.value" />

      <!-- 主表 -->
      <AlternativeD05Master
        :companies="data.companies.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :get-completion-status="data.getCompletionStatus"
        :has-abnormal="data.hasAbnormal"
        :get-check-ratio="getCheckRatioForMaster"
        :labels="G06_MASTER_LABELS"
        @select="handleSelectCompany"
        @add-company="handleAddCompany"
        @delete-company="handleDeleteCompany"
        @update-field="handleMasterUpdateField"
        @import-d01="handleImportG01"
        @import-excel="handleImportExcel"
        @export-template="handleExportExcel"
        @export-data="handleExportData"
        @save="handleSave"
      />

      <!-- Detail: 选中公司的详情 -->
      <template v-if="selectedCompany">
        <div class="gt-confirmation-alternative-g06__detail">
          <div class="detail-title">
            {{ selectedCompany.entity_name || '未命名公司' }} — 检查详情
          </div>

          <!-- 抽样配置（源 G0-6!A6「一、样本选取标准与规模」） -->
          <div class="detail-section">
            <div class="detail-section__header">{{ g06Section('sampling').title }}</div>
            <el-form
              :model="selectedCompany.sampling || {}"
              label-width="100px"
              size="small"
              :disabled="readonly"
            >
              <el-row :gutter="12">
                <el-col :span="12">
                  <!--
                    源 `B7` 是 5 个点选项（`大额（）关联方（）大额交易频繁（）异常（）全部（）`），
                    改造前是自由 textarea → 违反「交互点选优先」铁律且源选项文字完全缺失。
                    `allow-create` 让存量自由文本作自定义 tag 保留（数据零丢失）。
                  -->
                  <el-form-item label="测试范围">
                    <el-select
                      :model-value="testScopeSelections"
                      multiple
                      filterable
                      allow-create
                      default-first-option
                      collapse-tags
                      collapse-tags-tooltip
                      class="g06-scope-select"
                      placeholder="按源模板勾选（可多选，亦可输入补充）"
                      @update:model-value="onTestScopeChange"
                    >
                      <el-option
                        v-for="opt in G06_TEST_SCOPE_OPTIONS"
                        :key="opt"
                        :value="opt"
                        :label="opt"
                      />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="特定样本">
                    <el-input
                      v-model="selectedCompany.sampling!.specific_samples"
                      type="textarea"
                      :rows="2"
                      placeholder="XX金额以上（大额）、关联方/关联交易形成的款项、XX异常款项全部测试，共XX笔"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样总体">
                    <el-input
                      v-model="selectedCompany.sampling!.sampling_population"
                      placeholder="测试总体扣除特定样本以外的样本，共XX笔、金额XX"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="样本量">
                    <el-input
                      v-model="selectedCompany.sampling!.sample_size"
                      placeholder="抽取XX笔"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样方法">
                    <el-select
                      v-model="selectedCompany.sampling!.sampling_method"
                      placeholder="选择抽样方法"
                      @change="markDirty"
                    >
                      <el-option value="随机选样" label="随机选样" />
                      <el-option value="系统选样" label="系统选样" />
                      <el-option value="货币单元抽样" label="货币单元抽样" />
                      <el-option value="随意选样" label="随意选样（非统计抽样适用）" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="抽样过程">
                    <el-input
                      v-model="selectedCompany.sampling!.sampling_process"
                      type="textarea"
                      :rows="2"
                      placeholder="使用IDEA（XX抽样工具）选择XX数量占比XX%的样本进行测试"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!--
            余额汇总 —— **源模板 G0-6 无此段**（其「二、检查过程记录」直接是三个检查区块）。
            🔴 改造前它带段号「二」，把源模板的「二、检查过程记录」挤成「三」、
               「三、审计说明」+「四、审计结论」挤成合并的「四」→ 整表段号串位。
               现改为不带段号并明示「源外增强」，源模板四段各归其位。
          -->
          <div class="detail-section">
            <div class="detail-section__header">{{ G06_EXTRA_SECTIONS[0].title }}</div>
            <div class="balance-cards">
              <!-- 左卡：余额数据 -->
              <div class="balance-card balance-card--data">
                <div class="balance-card__title">余额数据</div>
                <div class="balance-card__grid">
                  <!-- 源模板 G0-6!A5「会计科目：」（g0 spec R7.1） -->
                  <div class="balance-card__item">
                    <span class="balance-card__label">会计科目</span>
                    <el-select
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.account_subject"
                      size="small"
                      filterable
                      allow-create
                      default-first-option
                      placeholder="选择或输入会计科目"
                      @change="markDirty"
                    >
                      <el-option v-for="s in G0_ACCOUNT_SUBJECT_OPTIONS" :key="s" :label="s" :value="s" />
                    </el-select>
                    <span v-else class="balance-card__value">{{ selectedCompany.balance?.account_subject || '—' }}</span>
                  </div>
                  <!-- 源模板 G0-6!D5「投资产品/名称：」（g0 spec R7.1） -->
                  <div class="balance-card__item">
                    <span class="balance-card__label">投资产品/名称</span>
                    <el-input
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.investment_product"
                      size="small"
                      placeholder="如：XX 结构性存款 / XX 有限公司股权"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value">{{ selectedCompany.balance?.investment_product || '—' }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">函证项目</span>
                    <el-input
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.item_name"
                      size="small"
                      placeholder="交易性金融资产"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value">{{ selectedCompany.balance?.item_name || '—' }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">年初余额</span>
                    <WpAmountInput
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.opening_balance"
                      size="small"
                      aria-label="年初余额"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.opening_balance) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">本期增加</span>
                    <WpAmountInput
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.increase_amount"
                      size="small"
                      aria-label="本期增加"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.increase_amount) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">本期减少</span>
                    <WpAmountInput
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.decrease_amount"
                      size="small"
                      aria-label="本期减少"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.decrease_amount) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">期末余额</span>
                    <WpAmountInput
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.closing_balance"
                      size="small"
                      aria-label="期末余额"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.closing_balance) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">投资收益</span>
                    <WpAmountInput
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.investment_income"
                      size="small"
                      aria-label="投资收益"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.investment_income) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">公允价值变动</span>
                    <WpAmountInput
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.fv_change"
                      size="small"
                      aria-label="公允价值变动"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.fv_change) }}</span>
                  </div>
                </div>
              </div>
              <!-- 右卡：检查比例指标 -->
              <div class="balance-card balance-card--ratio">
                <div class="balance-card__title">检查比例</div>
                <div class="ratio-indicators">
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">股利检查比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getCheckRatio(selectedCompany, 'payment'))">
                      {{ formatRatio(data.getCheckRatio(selectedCompany, 'payment')) }}
                    </div>
                    <div class="ratio-indicator__desc">区块④实收/应收股利 / 期末余额</div>
                  </div>
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">持仓检查比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getCheckRatio(selectedCompany, 'inbound'))">
                      {{ formatRatio(data.getCheckRatio(selectedCompany, 'inbound')) }}
                    </div>
                    <div class="ratio-indicator__desc">区块④市值合计 / 期末余额</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 4 区块检查表：block1/block3/block4 统一渲染，block2 借贷拆表 -->
          <!-- 源 G0-6!A8 段号是「二」（改造前误编为「三」，因源外增强段抢占了「二」） -->
          <div class="detail-section">
            <div class="detail-section__header">{{ g06Section('process').title }}</div>
            <!--
              源 `C15`「2.检查本期发生额」行的抽样标准 5 点选项 —— 改造前平台**完全没有这个录入位置**。
              🔴 末项是「其他」不是「全部」（与 `B7` 只差最后一项，抄错会让两处语义混同）。
            -->
            <el-form label-width="130px" size="small" :disabled="readonly" class="g06-occurrence-form">
              <el-form-item label="本期发生额抽样标准">
                <el-select
                  :model-value="occurrenceScopeSelections"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  collapse-tags
                  collapse-tags-tooltip
                  class="g06-scope-select"
                  placeholder="按源模板勾选（可多选，亦可输入补充）"
                  @update:model-value="onOccurrenceScopeChange"
                >
                  <el-option
                    v-for="opt in G06_OCCURRENCE_SAMPLING_OPTIONS"
                    :key="opt"
                    :value="opt"
                    :label="opt"
                  />
                </el-select>
                <span class="g06-anchor">源模板 C15</span>
              </el-form-item>
            </el-form>
            <!-- 非 block2 统一渲染 -->
            <CheckBlock
              v-for="bt in blockTypes.filter((b) => b !== 'block2')"
              :key="bt"
              :config="blockConfigs[bt]"
              :rows="getBlockRows(selectedCompany, bt)"
              :totals="data.getBlockTotal(selectedCompany, bt)"
              :readonly="readonly"
              :enable-ocr="true"
              :ocr-loading-row-id="ocrLoadingRowId"
              @add-row="data.addBlockRow(selectedCompany._company_id!, bt)"
              @delete-row="(rowId: string) => data.deleteBlockRow(selectedCompany!._company_id!, bt, rowId)"
              @update-field="(rowId: string, field: string, val: any) => data.updateBlockField(selectedCompany!._company_id!, bt, rowId, field, val)"
              @ocr-upload="(rowId: string, file: File) => handleRowOcr(bt, rowId, file)"
            />
            <!-- block2 本期发生额：借方/贷方两张表（confirmation-alternative-structure-alignment 决策 1） -->
            <div class="split-direction-block">
              <div class="split-direction-block__title">{{ blockConfigs.block2.title }}</div>
              <!-- 待归位提示：既有行无 direction -->
              <el-alert
                v-if="getBlockRows(selectedCompany, 'block2').some((r) => !r.direction)"
                type="warning" :closable="false" show-icon
                style="margin-bottom:8px"
              >
                有 {{ getBlockRows(selectedCompany, 'block2').filter((r) => !r.direction).length }} 行尚未指定借贷方向，请编辑行指定方向后归入对应表
              </el-alert>
              <!-- 借方表 -->
              <div class="split-direction-block__sub">
                <div class="split-direction-block__sub-title">借方发生额</div>
                <CheckBlock
                  :config="blockConfigs.block2"
                  :rows="getBlockRows(selectedCompany, 'block2').filter((r) => r.direction === 'debit')"
                  :totals="data.getBlockTotalByDirection(selectedCompany, 'block2', 'debit')"
                  :readonly="readonly"
                  :enable-ocr="true"
                  :ocr-loading-row-id="ocrLoadingRowId"
                  @add-row="addDirectionRow('debit')"
                  @delete-row="(rowId: string) => data.deleteBlockRow(selectedCompany!._company_id!, 'block2', rowId)"
                  @update-field="(rowId: string, field: string, val: any) => data.updateBlockField(selectedCompany!._company_id!, 'block2', rowId, field, val)"
                  @ocr-upload="(rowId: string, file: File) => handleRowOcr('block2', rowId, file)"
                />
              </div>
              <!-- 贷方表 -->
              <div class="split-direction-block__sub">
                <div class="split-direction-block__sub-title">贷方发生额</div>
                <CheckBlock
                  :config="blockConfigs.block2"
                  :rows="getBlockRows(selectedCompany, 'block2').filter((r) => r.direction === 'credit')"
                  :totals="data.getBlockTotalByDirection(selectedCompany, 'block2', 'credit')"
                  :readonly="readonly"
                  :enable-ocr="true"
                  :ocr-loading-row-id="ocrLoadingRowId"
                  @add-row="addDirectionRow('credit')"
                  @delete-row="(rowId: string) => data.deleteBlockRow(selectedCompany!._company_id!, 'block2', rowId)"
                  @update-field="(rowId: string, field: string, val: any) => data.updateBlockField(selectedCompany!._company_id!, 'block2', rowId, field, val)"
                  @ocr-upload="(rowId: string, file: File) => handleRowOcr('block2', rowId, file)"
                />
              </div>
            </div>
          </div>

          <!--
            🔴 源模板是**两个独立段**：`A40 三、审计说明：` 与 `A43 四、审计结论：`。
               改造前被并成一段「四、审计说明与结论」→ 段号错（审计说明本应是「三」）+ 两段并一。
               现拆两段、编号归位；**数据仍共用同一 `AuditConclusion` 对象**（不新增持久化键，零迁移）。
          -->
          <!-- 三、审计说明（源 A40） -->
          <div class="detail-section">
            <div class="detail-section__header">
              <span>{{ g06Section('audit_note').title }}</span>
              <div style="margin-left: auto; display: flex; align-items: center; gap: 8px">
                <el-button
                  v-if="!readonly"
                  type="primary"
                  size="small"
                  plain
                  :loading="aiLoading"
                  @click="handleAiFill"
                >
                  AI 智能填充
                </el-button>
                <GtReviewTrigger section-id="G0-6-audit-note" label="复核" />
              </div>
            </div>
            <el-form
              :model="selectedCompany.conclusion || {}"
              label-width="80px"
              size="small"
              :disabled="readonly"
            >
              <el-form-item label="审计说明">
                <el-input
                  v-model="selectedCompany.conclusion!.audit_note"
                  type="textarea"
                  :rows="3"
                  placeholder="概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。"
                  @change="markDirty"
                />
              </el-form-item>
            </el-form>
          </div>

          <!-- 四、审计结论（源 A43） -->
          <div class="detail-section">
            <div class="detail-section__header">
              <span>{{ g06Section('conclusion').title }}</span>
              <div style="margin-left: auto; display: flex; align-items: center; gap: 8px">
                <GtReviewTrigger section-id="G0-6-conclusion" label="复核" />
              </div>
            </div>
            <el-form
              :model="selectedCompany.conclusion || {}"
              label-width="80px"
              size="small"
              :disabled="readonly"
            >
              <el-form-item label="审计结论">
                <el-radio-group v-model="selectedCompany.conclusion!.conclusion_type" @change="markDirty">
                  <el-radio value="A">A - 替代程序结果支持余额</el-radio>
                  <el-radio value="B">B - 部分事项待进一步确认</el-radio>
                  <el-radio value="C">C - 存在重大异常需扩大程序</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="selectedCompany.conclusion?.conclusion_type" label="结论文本">
                <el-input
                  v-model="selectedCompany.conclusion!.conclusion_text"
                  type="textarea"
                  :rows="2"
                  @change="markDirty"
                />
              </el-form-item>
              <!-- 异常未决提示 -->
              <el-alert
                v-if="data.hasAbnormal(selectedCompany)"
                type="warning"
                :closable="false"
                show-icon
                class="mt-8"
              >
                当前存在异常行，请确认是否需要调整或扩大替代程序范围。
              </el-alert>
            </el-form>
          </div>
        </div>
      </template>
    </template>

    <!-- 隐藏文件选择器 -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, defineAsyncComponent, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { exportMultiSheetData, parseFile } from '@/composables/useExcelIO'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useAlternativeG06Data } from './composables/useAlternativeG06Data'
import type { AlternativeCompany, BlockType, CheckRow } from '../../confirmation/alternativeD05/alternativeD05Types'
import { BLOCK_COLUMN_CONFIGS_G06, G0_ACCOUNT_SUBJECT_OPTIONS } from './blockColumnConfigsG06'
// 🔴 段结构与点选项字面**单一真源**（本组件不抄第二份中文，守卫按源码断言）
import {
  G06_EXTRA_SECTIONS,
  G06_MASTER_LABELS,
  G06_OCCURRENCE_SAMPLING_OPTIONS,
  G06_TEST_SCOPE_OPTIONS,
  g06Section,
  parseG06ScopeSelections,
  serializeG06ScopeSelections,
} from './g06SourceFidelity'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from '../../composables/useWorkpaperScaffold'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

// 复用 D0-5 的 Dashboard 和 Master 组件
import AlternativeD05Dashboard from '../../confirmation/alternativeD05/AlternativeD05Dashboard.vue'
import AlternativeD05Master from '../../confirmation/alternativeD05/AlternativeD05Master.vue'
// 复用 D0-5 的 CheckBlock 组件
import CheckBlock from '../../confirmation/alternativeD05/CheckBlock.vue'
// 「余额数据」卡片的 6 个金额输入走平台金额控件（失焦千分符 / 聚焦原始值）。
// 原为 `el-input type="number"` —— HTML number input 天然拒逗号，千分符结构上不可能出现。
import WpAmountInput from '../../shared/WpAmountInput.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const wpIdRef = computed(() => props.wpId ?? '')
const projectIdRef = computed(() => props.projectId ?? '')

// ─── Runtime Boundary 统一提供版本链 + 复核（GtWpRenderer scaffold），本组件不再本地接线 ───
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const openVersionHistory = () => runtime?.version.openVersionHistory()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'alternative-g06-v1')

// ─── 数据核心（D06 专属 composable） ─────────────────────────────────────────

const prefs = useDisplayPrefsStore()
const data = useAlternativeG06Data({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 区块配置（D06 专属列定义） ──────────────────────────────────────────────

const blockTypes: BlockType[] = ['block1', 'block2', 'block3', 'block4']
const blockConfigs = BLOCK_COLUMN_CONFIGS_G06

// ─── 选中公司 ────────────────────────────────────────────────────────────────

const selectedCompany = computed<AlternativeCompany | undefined>(() => {
  if (!data.selectedCompanyId.value) return data.companies.value[0]
  return data.companies.value.find((c) => c._company_id === data.selectedCompanyId.value)
})

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  const key = `${blockType}_rows` as keyof AlternativeCompany
  return (company[key] as CheckRow[]) || []
}

function getCheckRatioForMaster(company: AlternativeCompany, type: 'receipt' | 'shipment') {
  return data.getCheckRatio(company, type === 'receipt' ? 'payment' : 'inbound')
}

/** block2 本期发生额借贷拆表：新增行时带 direction（confirmation-alternative-structure-alignment） */
function addDirectionRow(direction: 'debit' | 'credit') {
  const company = selectedCompany.value
  if (!company) return
  const row = data.addBlockRow(company._company_id!, 'block2')
  if (row) {
    data.updateBlockField(company._company_id!, 'block2', row._row_id!, 'direction', direction)
  }
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleSelectCompany(companyId: string) {
  data.selectedCompanyId.value = companyId
}

function handleAddCompany() {
  const company = data.addCompany()
  data.selectedCompanyId.value = company._company_id!
  nextTick(() => {
    const el = document.querySelector('.gt-confirmation-alternative-g06__detail')
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function handleDeleteCompany(companyId: string) {
  data.deleteCompany(companyId)
}

/**
 * 反向联动：从 confirmation-hub 的 G0-1 函证结果汇总获取未回函项目，
 * 带入 G0-6 替代程序作为待检查公司清单。
 * 通过 wp-id-by-code 解析同项目 G0-1 的 wp_id → render-config 取 confirmation-v1 行数据。
 */
async function handleImportG01() {
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法从 G0-1 带入')
    return
  }
  try {
    // 1. 解析同项目 G0-1 的 wp_id
    const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: props.projectId, wp_code: 'G0-1' },
      _silent: true,
    } as any)
    const g01WpId = (idRes as any)?.wp_id
    if (!g01WpId) {
      ElMessage.info('未找到 G0-1 函证结果汇总底稿')
      return
    }

    // 2. 取 G0-1 render-config，提取 confirmation-v1 行数据
    const cfg = await api.get<any>(`/api/workpapers/${g01WpId}/render-config`, { _silent: true } as any)
    const sheets = cfg?.sheets ?? []
    let rows: any[] = []
    for (const sheet of sheets) {
      const hd = sheet?.html_data ?? sheet?.htmlData
      if (hd?._format === 'confirmation-v1' && Array.isArray(hd.rows)) {
        rows = hd.rows
        break
      }
    }
    if (rows.length === 0) {
      ElMessage.info('G0-1 暂无函证数据')
      return
    }

    // 3. 过滤未回函项目（match_status === '未回函' 或 is_replied === false）
    const unreplied = rows.filter(
      (r) => r.match_status === '未回函' || (r.is_replied === false && r.match_status !== '相符'),
    )
    if (unreplied.length === 0) {
      ElMessage.info('G0-1 暂无未回函项目')
      return
    }

    // 4. 映射为 G0-6 公司清单并去重导入
    const imported: Partial<AlternativeCompany>[] = unreplied.map((r) => ({
      entity_name: r.entity_name || '',
      confirm_index: r.confirm_index,
      _source: 'auto',
      balance: {
        item_name: r.account_type || '交易性金融资产',
        investment_type: r.account_type || '交易性金融资产',
        closing_balance: Number(r.amount) || 0,
      },
    }))
    data.importCompanies(imported)
    ElMessage.success(`已从 G0-1 带入 ${imported.length} 个未回函项目`)
  } catch (e: any) {
    if (e?.response?.status === 404) {
      ElMessage.info('未找到 G0-1 函证结果汇总底稿')
    } else {
      ElMessage.warning('从 G0-1 带入失败：' + (e?.message || '未知错误'))
    }
  }
}

const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportExcel() {
  importFileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    // 走 useExcelIO 单一入口（B2 批，与 D05/D06/F05/F06/H05 同构）。
    // requireFirstCell:false —— 首列「序号」模板说明写「留空即可」；全空行由下方 hasValue 过滤。
    const { rows: rawRows } = await parseFile(file, {
      sheetName: '',
      skipRows: 1,
      skipExamplePrefix: '',
      requireFirstCell: false,
    })
    if (rawRows.length === 0) {
      ElMessage.warning('Excel 文件为空或无法解析')
      return
    }
    const colMap: Record<string, string[]> = {
      entity_name: ['供应商/客户名称', '单位名称', '被询证单位', '客户名称', '公司名称'],
      confirm_index: ['索引号', '函证索引号', '编号'],
    }
    const importData: Partial<AlternativeCompany>[] = []
    for (const raw of rawRows) {
      const hasValue = Object.values(raw).some(v => v != null && String(v).trim() !== '')
      if (!hasValue) continue
      const row: Partial<AlternativeCompany> = {}
      for (const [field, aliases] of Object.entries(colMap)) {
        for (const alias of aliases) {
          if (raw[alias] != null && String(raw[alias]).trim() !== '') {
            ;(row as any)[field] = String(raw[alias]).trim()
            break
          }
        }
      }
      if (row.entity_name) importData.push(row)
    }
    if (importData.length > 0) {
      data.importCompanies(importData)
      ElMessage.success(`成功导入 ${importData.length} 家公司`)
    } else {
      ElMessage.warning('未识别到有效数据，请检查列头是否包含：供应商/客户名称')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '文件格式错误'))
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

async function handleExportExcel() {
  try {
    // Sheet 1: 公司清单模板
    const companyHeaders = ['序号', '函证索引号', '供应商/客户名称']
    const companyExample = ['1', 'D0-001', '示例公司（请删除）']

    // Sheet 2~5: 4 区块列头
    const blockSheets: { key: string; name: string }[] = [
      { key: 'block1', name: '①初始投资协议' },
      { key: 'block2', name: '②本期发生额' },
      { key: 'block3', name: '③期后出售赎回' },
      { key: 'block4', name: '④源外增强' },
    ]

    // Sheet 6: 填写说明
    const instructions = [
      ['G0-6 投资循环替代程序 — 导入模板说明'],
      [''],
      ['【Sheet 说明】'],
      ['  公司清单：填写替代程序的公司列表（必须），导入后每公司自动创建 4 区块检查记录'],
      ['  ①期末余额证据：应付账款检查-形成期末余额的订单/合同、出库单等支持性证据'],
      ['  ②期后回款：应付账款检查-检查期后回款情况'],
      ['  ③本期出库：销售检查-本期销售出库的合同、出库单、运输单、验收单等'],
      ['  ④本期收款：销售检查-本期收款检查'],
      [''],
      ['【公司清单列说明】'],
      ['  序号：自动生成（留空即可）'],
      ['  函证索引号：来自 F0-1 的索引号（如 D0-001），用于跨底稿追溯'],
      ['  供应商/客户名称：被检查公司全称（必填）'],
      [''],
      ['【注意事项】'],
      ['  1. 先导入"公司清单" Sheet（系统仅读取第一个 Sheet 的公司数据）'],
      ['  2. 已存在相同索引号的公司不会重复导入'],
      ['  3. 导入后选中公司 → 在 4 个区块中录入检查明细'],
      ['  4. 付款检查比例 = 区块④收款金额合计 / 本期采购额（自动计算）'],
      ['  5. 入库检查比例 = 区块③出库金额合计 / 本期采购额（自动计算）'],
    ]
    // 六个 sheet 全是纯 AOA，rows 与 colWidths 原样传（列宽公式勿改）
    await exportMultiSheetData({
      sheets: [
        {
          sheetName: '公司清单',
          rows: [companyHeaders, companyExample],
          colWidths: [{ wch: 6 }, { wch: 12 }, { wch: 30 }],
        },
        ...blockSheets.map(({ key, name }) => {
          const cols = BLOCK_COLUMN_CONFIGS_G06[key].columns
          return {
            sheetName: name,
            rows: [cols.map(c => c.label)],
            colWidths: cols.map(c => ({
              wch: Math.max((c.width || 100) / 8, (c.label?.length || 4) * 2.5),
            })),
          }
        }),
        { sheetName: '填写说明', rows: instructions, colWidths: [{ wch: 80 }] },
      ],
      fileName: 'G0-6投资循环替代程序_导入模板.xlsx',
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success('模板已导出')
  } catch (e: any) {
    ElMessage.error('生成模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleExportData() {
  if (data.companies.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    // Sheet 1: 公司汇总
    const summaryHeaders = ['序号', '索引号', '公司名称', '完成度', '收款比例', '出库比例', '是否异常']
    const summaryData = data.companies.value.map(c => [
      c.seq ?? '',
      c.confirm_index ?? '',
      c.entity_name ?? '',
      `${data.getCompletionStatus(c).completed}/4`,
      data.getCheckRatio(c, 'payment') !== null ? `${data.getCheckRatio(c, 'payment')!.toFixed(1)}%` : 'N/A',
      data.getCheckRatio(c, 'inbound') !== null ? `${data.getCheckRatio(c, 'inbound')!.toFixed(1)}%` : 'N/A',
      data.hasAbnormal(c) ? '是' : '否',
    ])
    // 每个区块一个 Sheet
    const blockSheets: { key: BlockType; name: string }[] = [
      { key: 'block1', name: '①初始投资协议' },
      { key: 'block2', name: '②本期发生额' },
      { key: 'block3', name: '③期后出售赎回' },
      { key: 'block4', name: '④源外增强' },
    ]

    await exportMultiSheetData({
      sheets: [
        {
          sheetName: '公司汇总',
          rows: [summaryHeaders, ...summaryData],
          colWidths: [{ wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 8 }, { wch: 10 }, { wch: 10 }, { wch: 8 }],
        },
        ...blockSheets.map(({ key, name }) => {
          const cols = BLOCK_COLUMN_CONFIGS_G06[key].columns
          const headers = ['公司名称', ...cols.map(c => c.label)]
          const rows: any[][] = []
          for (const company of data.companies.value) {
            for (const row of getBlockRows(company, key)) {
              rows.push([company.entity_name ?? '', ...cols.map(c => row[c.field] ?? '')])
            }
          }
          return {
            sheetName: name,
            rows: [headers, ...rows],
            colWidths: [{ wch: 20 }, ...cols.map(c => ({ wch: Math.max((c.width || 80) / 8, 10) }))],
          }
        }),
      ],
      fileName: 'G0-6投资循环替代程序_数据导出.xlsx',
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success('数据已导出')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

const aiLoading = ref(false)

function handleAiFill() {
  if (!selectedCompany.value) return
  aiLoading.value = true
  try {
    const company = selectedCompany.value
    const entityName = company.entity_name || '该公司'
    const receiptRatio = data.getCheckRatio(company, 'payment')
    const shipmentRatio = data.getCheckRatio(company, 'inbound')
    const status = data.getCompletionStatus(company)
    const hasAnomaly = data.hasAbnormal(company)

    const b1Count = (company.block1_rows || []).length
    const b2Count = (company.block2_rows || []).length
    const b3Count = (company.block3_rows || []).length
    const b4Count = (company.block4_rows || []).length
    const totalRows = b1Count + b2Count + b3Count + b4Count
    const abnormalRows = [
      ...(company.block1_rows || []),
      ...(company.block2_rows || []),
      ...(company.block3_rows || []),
      ...(company.block4_rows || []),
    ].filter(r => r.is_abnormal === '是').length

    const parts: string[] = []

    if (totalRows > 0) {
      parts.push(
        `对${entityName}执行替代程序，共检查 ${totalRows} 笔凭证/单据（期末余额证据 ${b1Count} 笔、期后回款 ${b2Count} 笔、本期出库 ${b3Count} 笔、本期收款 ${b4Count} 笔），完成度 ${status.completed}/4 区块。`
      )
    } else {
      parts.push(`对${entityName}执行替代程序，尚未录入检查数据。`)
    }

    if (receiptRatio !== null || shipmentRatio !== null) {
      const rPart = receiptRatio !== null ? `付款检查比例 ${receiptRatio.toFixed(1)}%` : '付款检查比例待计算'
      const sPart = shipmentRatio !== null ? `入库检查比例 ${shipmentRatio.toFixed(1)}%` : '入库检查比例待计算'
      parts.push(`${rPart}，${sPart}。`)
    }

    if (hasAnomaly) {
      parts.push(`检查中发现 ${abnormalRows} 笔异常项，需进一步核实原因并评估是否需要调整。`)
    } else if (totalRows > 0) {
      parts.push('检查中未发现异常事项。')
    }

    if (totalRows > 0 && !hasAnomaly && status.completed === 4) {
      parts.push('替代程序结果支持账面余额的合理性，未发现需要调整事项。')
    } else if (hasAnomaly) {
      parts.push('建议：对异常项扩大检查范围或追加审计程序，并与管理层确认相关事项。')
    }

    const generatedText = parts.join('')

    if (!company.conclusion) company.conclusion = {}
    if (!company.conclusion.audit_note) {
      company.conclusion.audit_note = generatedText
    } else {
      company.conclusion.audit_note += '\n' + generatedText
    }
    data.isDirty.value = true

    if (!company.conclusion.conclusion_type) {
      if (totalRows > 0 && !hasAnomaly && status.completed === 4) {
        company.conclusion.conclusion_type = 'A'
      } else if (hasAnomaly) {
        company.conclusion.conclusion_type = 'C'
      } else {
        company.conclusion.conclusion_type = 'B'
      }
      data.isDirty.value = true
    }

    ElMessage.success('已根据检查数据生成审计说明（仅供参考，请根据实际情况修改）')
  } finally {
    aiLoading.value = false
  }
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
  runtime?.version.scheduleAutoSnapshot()
}

// ─── 行级 OCR：上传证券单据 → contract-ocr 识别 → 确认 → merge 填入当前行 ────
const ocrLoadingRowId = ref<string | null>(null)

/** OCR 识别字段 → 各区块行字段的映射（证券信息） */
const OCR_FIELD_MAP: Record<BlockType, Record<string, string>> = {
  block1: {
    date: 'stmt_date', 对账单日期: 'stmt_date',
    holding_variety: 'holding_variety', 持仓品种: 'holding_variety', 品种: 'holding_variety',
    quantity: 'holding_qty', 数量: 'holding_qty', holding_qty: 'holding_qty',
    amount: 'market_value', 市值: 'market_value', market_value: 'market_value',
  },
  block2: {
    date: 'dividend_announce_date', 分红公告日期: 'dividend_announce_date',
    amount: 'received_amount', 到账金额: 'received_amount', received_amount: 'received_amount',
    dividend_receivable: 'dividend_receivable', 应收股利: 'dividend_receivable',
  },
  block3: {
    date: 'trade_confirm_date', 交易确认单日期: 'trade_confirm_date',
    quantity: 'sell_qty', 卖出数量: 'sell_qty',
    price: 'trade_price', 成交价: 'trade_price',
    amount: 'trade_amount', 成交金额: 'trade_amount', trade_amount: 'trade_amount',
    fee: 'fee', 手续费: 'fee',
  },
  block4: {
    date: 'quote_date', 报价日期: 'quote_date',
    amount: 'quote_value', 报价值: 'quote_value', quote_value: 'quote_value',
    quote_source: 'quote_source', 报价来源: 'quote_source',
  },
}

async function handleRowOcr(blockType: BlockType, rowId: string, file: File): Promise<void> {
  if (!selectedCompany.value || !props.wpId) return
  ocrLoadingRowId.value = rowId
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return
    }
    // 映射识别字段 → 当前区块行字段
    const map = OCR_FIELD_MAP[blockType]
    const patch: Record<string, any> = {}
    for (const [ocrKey, val] of Object.entries(fields)) {
      const target = map[ocrKey]
      if (target && val != null && String(val).trim() !== '') {
        patch[target] = val
      }
    }
    if (Object.keys(patch).length === 0) {
      ElMessage.info('OCR完成，识别字段无法匹配本区块')
      return
    }
    const preview = Object.entries(patch)
      .map(([k, v]) => `${k}: ${v}`)
      .join('，')
    await ElMessageBox.confirm(`识别到证券信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
    })
    for (const [field, val] of Object.entries(patch)) {
      data.updateBlockField(selectedCompany.value._company_id!, blockType, rowId, field, val)
    }
    ElMessage.success('已填入识别结果')
  } catch (e) {
    if (e !== 'cancel') ElMessage.warning('OCR识别失败')
  } finally {
    ocrLoadingRowId.value = null
  }
}

function markDirty() {
  data.isDirty.value = true
}

/**
 * 主表行内编辑回写（被投资单位名称 / 函证索引号）。
 *
 * 🔴 改造前 G0-6 **没有监听 `AlternativeD05Master` 的 `update-field`** → 在主表里改名称或
 * 索引号被**静默丢弃**（与「传不存在的 prop = 静默失效」同族：不报错、四层验证全绿，
 * 只有真在界面上改一次才发现）。九个替代程序组件里只有 D0-5 接了，其余属平台级遗留。
 */
function handleMasterUpdateField(companyId: string, field: string, value: unknown) {
  data.updateCompany(companyId, { [field]: value } as Partial<AlternativeCompany>)
}

// ─── 源模板两组点选项（源 B7 测试范围 / C15 本期发生额抽样标准）───────────────
//
// 二者都存成「、」分隔字符串（与旧自由文本同一字段、同一形态 → 零迁移）；
// `allow-create` 让存量整段叙述作自定义 tag 保留，绝不丢弃（数据零丢失红线）。

const testScopeSelections = computed<string[]>(() =>
  parseG06ScopeSelections(selectedCompany.value?.sampling?.test_scope),
)

const occurrenceScopeSelections = computed<string[]>(() =>
  parseG06ScopeSelections(selectedCompany.value?.sampling?.occurrence_sampling_scope),
)

function ensureSampling(): NonNullable<AlternativeCompany['sampling']> | null {
  const company = selectedCompany.value
  if (!company) return null
  if (!company.sampling) company.sampling = {}
  return company.sampling
}

function onTestScopeChange(values: string[]) {
  const sampling = ensureSampling()
  if (!sampling) return
  sampling.test_scope = serializeG06ScopeSelections(values)
  markDirty()
}

function onOccurrenceScopeChange(values: string[]) {
  const sampling = ensureSampling()
  if (!sampling) return
  sampling.occurrence_sampling_scope = serializeG06ScopeSelections(values)
  markDirty()
}

function formatRatio(val: number | null): string {
  if (val === null) return 'N/A'
  return `${val.toFixed(1)}%`
}

function formatAmount(val: number | undefined | null): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}

function ratioClass(val: number | null): string {
  if (val === null) return 'ratio-indicator__value--na'
  if (val >= 80) return 'ratio-indicator__value--good'
  if (val >= 50) return 'ratio-indicator__value--warn'
  return 'ratio-indicator__value--danger'
}

// 暴露给父组件通过 ref 调用（页面级工具栏转发）
defineExpose({
  handleExportTemplate: handleExportExcel,
  handleExportData,
  handleImport: handleImportExcel,
  handleImportClick: handleImportExcel,
  handleDownloadImportTemplate: handleExportExcel,
})
</script>

<style scoped>
.gt-confirmation-alternative-g06 {
  padding: 8px 0;
}

/* 源模板两组点选项（B7 测试范围 / C15 本期发生额抽样标准） */
.g06-scope-select {
  width: 100%;
}
.g06-occurrence-form {
  margin-bottom: 6px;
}
.g06-anchor {
  margin-left: 8px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.gt-confirmation-alternative-g06__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-g06__header-tip {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-g06__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.gt-confirmation-alternative-g06__toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-confirmation-alternative-g06__tips {
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  padding: 6px 10px;
}

.gt-confirmation-alternative-g06__tips summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.gt-confirmation-alternative-g06__tips p {
  margin: 8px 0 0;
  line-height: 1.6;
}

.gt-confirmation-alternative-g06__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.gt-confirmation-alternative-g06__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-confirmation-alternative-g06__detail {
  margin-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--el-text-color-primary);
}

.detail-section {
  margin-bottom: 16px;
}

.detail-section__header {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  display: flex;
  align-items: center;
}

.ratio-display {
  font-weight: 700;
  color: var(--el-color-primary);
  font-size: 14px;
}

/* ─── 卡片式双栏：余额汇总与检查比例 ───────────────────────────────────── */

.balance-cards {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 12px;
}

.balance-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 16px;
  background: #fafbfc;
}

.balance-card__title {
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.balance-card__grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px 16px;
}

.balance-card__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.balance-card__label {
  font-size: 11px;
  color: #909399;
}

.balance-card__value {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

.balance-card__value--num {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.balance-card--ratio {
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: linear-gradient(135deg, #f5f0ff 0%, #eef2ff 100%);
  border-color: #d9d0f0;
}

.ratio-indicators {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ratio-indicator {
  text-align: center;
}

.ratio-indicator__label {
  font-size: 11px;
  color: #606266;
  margin-bottom: 4px;
}

.ratio-indicator__value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}

.ratio-indicator__value--good { color: #67c23a; }
.ratio-indicator__value--warn { color: #e6a23c; }
.ratio-indicator__value--danger { color: #f56c6c; }
.ratio-indicator__value--na { color: #c0c4cc; }

.ratio-indicator__desc {
  font-size: 10px;
  color: #c0c4cc;
  margin-top: 2px;
}

@media (max-width: 900px) {
  .balance-cards {
    grid-template-columns: 1fr;
  }
  .balance-card__grid {
    grid-template-columns: 1fr 1fr;
  }
}

.mt-8 { margin-top: 8px; }

/* ─── block2 借贷拆表 ───────────────────────────────────────────────────── */
.split-direction-block {
  margin-top: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafbfc;
}

.split-direction-block__title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}

.split-direction-block__sub {
  margin-top: 8px;
}

.split-direction-block__sub-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
  margin-bottom: 4px;
}
</style>
