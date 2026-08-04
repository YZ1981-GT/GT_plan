<template>
  <div class="gt-confirmation-alternative-h05" data-testid="h0-alternative-h05">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-alternative-h05__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：alternative-h05-v1 -->
    <template v-else>
      <!-- 工具栏 -->
      <div class="gt-confirmation-alternative-h05__toolbar">
        <span class="gt-confirmation-alternative-h05__title">H0-5 固定资产循环替代程序</span>
        <div class="gt-confirmation-alternative-h05__toolbar-right">
          <!-- ref_index 跳转 H1/L1/L3 -->
          <GtIndexChip value="H1" :context-project-id="projectId" />
          <GtIndexChip value="L1" :context-project-id="projectId" />
          <GtIndexChip value="L3" :context-project-id="projectId" />
          <!-- 导入导出下拉 -->
          <el-dropdown trigger="click" @command="handleIeCommand">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
          <GtReviewTrigger section-id="H0-5-alternative" label="复核" />
        </div>
      </div>

      <!-- 顶部说明（源模板编制说明第 ③ 条，字面见 h05SourceFidelity） -->
      <div class="gt-confirmation-alternative-h05__header-tip">
        <el-alert type="info" :closable="true" show-icon>
          {{ headerTip }}
        </el-alert>
      </div>

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
        @select="handleSelectCompany"
        @add-company="handleAddCompany"
        @delete-company="handleDeleteCompany"
        @import-d01="handleImportH01"
        @import-excel="handleImportExcel"
        @export-template="handleExportExcel"
        @export-data="handleExportData"
        @save="handleSave"
      />

      <!-- Detail: 选中公司的详情 -->
      <template v-if="selectedCompany">
        <div class="gt-confirmation-alternative-h05__detail">
          <div class="detail-title">
            {{ selectedCompany.entity_name || '未命名公司' }} — 检查详情
          </div>

          <!-- 一、样本选取标准与规模（6 字段全部由 H05_SAMPLING_FIELDS 驱动，标签/占位逐字源模板） -->
          <div class="detail-section" data-testid="h05-section-sampling">
            <div class="detail-section__header">{{ sectionTitles.sampling }}</div>
            <el-form
              :model="selectedCompany.sampling || {}"
              label-width="140px"
              size="small"
              :disabled="readonly"
            >
              <el-row :gutter="12">
                <el-col v-for="f in samplingFields" :key="f.field" :span="12">
                  <el-form-item :label="f.label">
                    <el-select
                      v-if="f.control === 'select'"
                      v-model="selectedCompany.sampling![f.field]"
                      :placeholder="f.placeholder"
                      @change="markDirty"
                    >
                      <el-option v-for="opt in f.options || []" :key="opt" :value="opt" :label="opt" />
                    </el-select>
                    <el-input
                      v-else
                      v-model="selectedCompany.sampling![f.field]"
                      :type="f.control === 'textarea' ? 'textarea' : 'text'"
                      :rows="f.control === 'textarea' ? 2 : undefined"
                      :placeholder="f.placeholder"
                      @change="markDirty"
                    />
                    <div v-if="f.hint" class="detail-section__field-hint">{{ f.hint }}</div>
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- 二、检查过程记录（源模板 A10；R11:R19 为空白自由区，下列结构化内容为平台增强） -->
          <div class="detail-section" data-testid="h05-section-check-record">
            <div class="detail-section__header">{{ sectionTitles.check_record }}</div>

            <!-- 源外增强标注（方法论上下文，琥珀色左边线） -->
            <div class="src-hint" data-testid="h05-source-extra-notice">
              <div class="src-hint__badge">{{ sourceExtraBadge }}</div>
              <div class="src-hint__body">{{ sourceExtraReason }}</div>
            </div>

            <!-- 2.1 余额汇总与检查比例（平台增强） -->
            <div class="detail-subsection__header">余额汇总与检查比例</div>
            <div class="balance-cards">
              <!-- 左卡：余额数据 -->
              <div class="balance-card balance-card--data">
                <div class="balance-card__title">余额数据</div>
                <div class="balance-card__grid">
                  <div class="balance-card__item">
                    <span class="balance-card__label">函证项目</span>
                    <el-input
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.item_name"
                      size="small"
                      placeholder="固定资产/在建工程"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value">{{ selectedCompany.balance?.item_name || '—' }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">年初余额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.opening_balance"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.opening_balance) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">借方发生额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.debit_amount"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.debit_amount) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">贷方发生额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.credit_amount"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.credit_amount) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">期末余额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.closing_balance"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.closing_balance) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">本期新增金额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.current_addition"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.current_addition) }}</span>
                  </div>
                </div>
              </div>
              <!-- 右卡：检查比例指标 -->
              <div class="balance-card balance-card--ratio">
                <div class="balance-card__title">检查比例</div>
                <div class="ratio-indicators">
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">权属证据检查比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getCheckRatio(selectedCompany, 'ownership'))">
                      {{ formatRatio(data.getCheckRatio(selectedCompany, 'ownership')) }}
                    </div>
                    <div class="ratio-indicator__desc">区块②支持性证据合计 / 期末余额</div>
                  </div>
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">验收证据检查比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getCheckRatio(selectedCompany, 'acceptance'))">
                      {{ formatRatio(data.getCheckRatio(selectedCompany, 'acceptance')) }}
                    </div>
                    <div class="ratio-indicator__desc">区块①凭证金额合计 / 期末余额</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 2.2 四区块结构化检查表（平台增强） -->
            <div class="detail-subsection__header">结构化检查记录</div>
            <CheckBlock
              v-for="bt in blockTypes"
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

            <!-- 2.3 自由记录区（对应源模板 R11:R19 空白自由区） -->
            <div class="detail-subsection__header">{{ checkRecordFreeLabel }}</div>
            <el-input
              v-model="checkRecordFree"
              type="textarea"
              :autosize="{ minRows: 5 }"
              :disabled="readonly"
              :placeholder="checkRecordFreePlaceholder"
              :data-persist-key="checkRecordFreeKey"
              data-testid="h05-check-record-free"
              @change="markDirty"
            />
          </div>

          <!-- 三、审计说明（源模板 A20） -->
          <div class="detail-section" data-testid="h05-section-audit-note">
            <div class="detail-section__header">
              <span>{{ sectionTitles.audit_note }}</span>
              <GtReviewTrigger section-id="H0-5-audit-note" label="复核" style="margin-left: 8px" />
              <el-button
                v-if="!readonly"
                type="primary"
                size="small"
                plain
                :loading="aiLoading"
                style="margin-left: auto"
                @click="handleAiFill"
              >
                AI 智能填充
              </el-button>
            </div>
            <el-card shadow="never" class="detail-card">
              <el-form label-width="80px" size="small" :disabled="readonly">
                <el-form-item label="审计说明">
                  <el-input
                    v-model="selectedCompany.conclusion!.audit_note"
                    type="textarea"
                    :autosize="{ minRows: 3 }"
                    :placeholder="auditNotePlaceholder"
                    @change="markDirty"
                  />
                </el-form-item>
              </el-form>
            </el-card>
          </div>

          <!-- 四、审计结论（源模板 A23） -->
          <div class="detail-section" data-testid="h05-section-conclusion">
            <div class="detail-section__header">
              <span>{{ sectionTitles.conclusion }}</span>
              <GtReviewTrigger section-id="H0-5-conclusion" label="复核" style="margin-left: 8px" />
            </div>
            <el-card shadow="never" class="detail-card">
              <el-form label-width="80px" size="small" :disabled="readonly">
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
                    :autosize="{ minRows: 2 }"
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
            </el-card>
          </div>
        </div>
      </template>

      <!-- 编制说明（源模板 A28 起，逐字；折叠于底部） -->
      <details class="gt-confirmation-alternative-h05__guidance" data-testid="h05-guidance">
        <summary>{{ guidanceTitle }}</summary>
        <div v-for="g in guidanceGroups" :key="g.anchor" class="guidance-group">
          <div class="guidance-group__title">{{ g.title }}</div>
          <ul class="guidance-group__list">
            <li v-for="(it, idx) in g.items" :key="`${g.anchor}-${idx}`">{{ it.text }}</li>
          </ul>
        </div>
      </details>
    </template>

    <!-- 隐藏文件选择器 -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, defineAsyncComponent, nextTick, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import type { ConfirmationUpdatedPayload } from '@/utils/eventBus'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useAlternativeH05Data } from './composables/useAlternativeH05Data'
import { useH0ImportExport } from './composables/useH0ImportExport'
import type { AlternativeCompany, BlockType, CheckRow } from '../alternativeD05/alternativeD05Types'
import { BLOCK_COLUMN_CONFIGS_H05 } from './blockColumnConfigsH05'
import {
  H05_SAMPLING_FIELDS,
  H05_SECTION_TITLES,
  H05_GUIDANCE_GROUPS,
  H05_GUIDANCE_TITLE,
  H05_HEADER_TIP,
  H05_SOURCE_EXTRA_BADGE,
  H05_SOURCE_EXTRA_REASON,
  H05_CHECK_RECORD_FREE_KEY,
  H05_CHECK_RECORD_FREE_LABEL,
  H05_CHECK_RECORD_FREE_PLACEHOLDER,
} from './h05SourceFidelity'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from '../../composables/useWorkpaperScaffold'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

// 复用 D0-5 的 Dashboard 和 Master 组件
import AlternativeD05Dashboard from '../alternativeD05/AlternativeD05Dashboard.vue'
import AlternativeD05Master from '../alternativeD05/AlternativeD05Master.vue'
// 复用 D0-5 的 CheckBlock 组件
import CheckBlock from '../alternativeD05/CheckBlock.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))
const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  htmlData: any
  sheetName?: string
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

// ─── 导入导出 composable（后端三端点） ────────────────────────────────────────
const h0Ie = useH0ImportExport({ wpId: wpIdRef })

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 + selfLoad ────────────────────────────────────────────────────

const selfLoadedData = ref<any>(null)
const htmlDataRef = computed(() => props.htmlData ?? selfLoadedData.value)
const isNewFormat = computed(() => htmlDataRef.value?._format === 'alternative-h05-v1')

// selfLoad: bundle 内嵌场景 htmlData=null 时自动加载 render-config
onMounted(async () => {
  if (props.htmlData == null && props.wpId) {
    try {
      const cfg = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
      const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
      for (const sheet of sheets) {
        const hd = sheet?.html_data ?? sheet?.htmlData
        if (hd?._format === 'alternative-h05-v1') {
          selfLoadedData.value = hd
          break
        }
      }
    } catch (e) {
      console.warn('[GtConfirmationAlternativeH05] selfLoad render-config failed:', e)
    }
  }
})

// ─── EventBus 联动：H0-1→H0-5 importFromSummary + confirmation:updated 刷新 ──

/** H0 系列 wp_code 前缀（过滤非本循环事件） */
const H0_WP_CODES = ['H0-1', 'H0-2', 'H0-3', 'H0-4', 'H0-5', 'H0-6', 'H0-7']

/**
 * 当 H0-1 更新时（标记未回函），H0-5 应刷新数据以感知新的待替代程序公司。
 * 当其他 H0 兄弟 sheet 更新时，H0-5 重载 render-config 以同步最新状态。
 */
function onConfirmationUpdated(payload: ConfirmationUpdatedPayload) {
  // 仅响应同项目、H0 系列事件（排除自身发出的保存事件）
  if (payload.projectId !== props.projectId) return
  if (!H0_WP_CODES.some((code) => payload.wpCode.startsWith(code))) return
  if (payload.wpId === props.wpId) return // 忽略自身保存触发

  // H0-1 更新 → 提示用户可从汇总表带入新的未回函公司
  if (payload.wpCode === 'H0-1') {
    ElMessage.info({
      message: 'H0-1 函证结果汇总已更新，可点击"导入H0-1"刷新未回函公司列表',
      duration: 4000,
    })
  }

  // 其他兄弟 sheet 更新 → 静默重载数据
  if (props.wpId) {
    reloadDataFromRenderConfig()
  }
}

async function reloadDataFromRenderConfig() {
  if (!props.wpId) return
  try {
    const cfg = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
    const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
    for (const sheet of sheets) {
      const hd = sheet?.html_data ?? sheet?.htmlData
      if (hd?._format === 'alternative-h05-v1') {
        selfLoadedData.value = hd
        break
      }
    }
  } catch {
    // 静默失败，不干扰用户
  }
}

onMounted(() => {
  eventBus.on('confirmation:updated', onConfirmationUpdated)
})

onUnmounted(() => {
  eventBus.off('confirmation:updated', onConfirmationUpdated)
})

// ─── 数据核心（H05 专属 composable） ─────────────────────────────────────────

const prefs = useDisplayPrefsStore()
const data = useAlternativeH05Data({
  htmlData: () => htmlDataRef.value,
  readonly: props.readonly,
})

// ─── 区块配置（H05 专属列定义） ──────────────────────────────────────────────

const blockTypes: BlockType[] = ['block1', 'block2', 'block3', 'block4']
const blockConfigs = BLOCK_COLUMN_CONFIGS_H05

// ─── 源模板字面（单一真源 h05SourceFidelity，模板内禁内联字面量） ──────────────

const samplingFields = H05_SAMPLING_FIELDS
const guidanceGroups = H05_GUIDANCE_GROUPS
const guidanceTitle = H05_GUIDANCE_TITLE
const headerTip = H05_HEADER_TIP
const sourceExtraBadge = H05_SOURCE_EXTRA_BADGE
const sourceExtraReason = H05_SOURCE_EXTRA_REASON
const checkRecordFreeKey = H05_CHECK_RECORD_FREE_KEY
const checkRecordFreeLabel = H05_CHECK_RECORD_FREE_LABEL
const checkRecordFreePlaceholder = H05_CHECK_RECORD_FREE_PLACEHOLDER

/** 区块标题按 key 索引，供模板直接取用。 */
const sectionTitles = Object.fromEntries(
  H05_SECTION_TITLES.map((s) => [s.key, s.title]),
) as Record<'sampling' | 'check_record' | 'audit_note' | 'conclusion', string>

/** 审计说明占位取源模板「2、概述」两条（逐字拼接）。 */
const auditNotePlaceholder = (() => {
  const overview = H05_GUIDANCE_GROUPS.find((g) => g.anchor === 'A34')
  if (!overview) return ''
  return `${overview.title}：${overview.items.map((i) => i.text).join('')}`
})()

// ─── 选中公司 ────────────────────────────────────────────────────────────────

const selectedCompany = computed<AlternativeCompany | undefined>(() => {
  if (!data.selectedCompanyId.value) return data.companies.value[0]
  return data.companies.value.find((c) => c._company_id === data.selectedCompanyId.value)
})

/**
 * 检查过程自由记录（源模板 R11:R19 空白自由区）。
 * 落在 `AlternativeCompany.check_record_free`，随 `buildPayload()` 一起持久化到 html_data。
 */
const checkRecordFree = computed<string>({
  get: () => selectedCompany.value?.check_record_free ?? '',
  set: (val: string) => {
    const company = selectedCompany.value
    if (!company) return
    company.check_record_free = val
    data.isDirty.value = true
  },
})

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  const key = `${blockType}_rows` as keyof AlternativeCompany
  return (company[key] as CheckRow[]) || []
}

function getCheckRatioForMaster(company: AlternativeCompany, type: 'receipt' | 'shipment') {
  return data.getCheckRatio(company, type === 'receipt' ? 'acceptance' : 'ownership')
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleSelectCompany(companyId: string) {
  data.selectedCompanyId.value = companyId
}

function handleAddCompany() {
  const company = data.addCompany()
  data.selectedCompanyId.value = company._company_id!
  nextTick(() => {
    const el = document.querySelector('.gt-confirmation-alternative-h05__detail')
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function handleDeleteCompany(companyId: string) {
  data.deleteCompany(companyId)
}

async function handleImportH01() {
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法从 H0-1 带入')
    return
  }
  try {
    const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: props.projectId, wp_code: 'H0-1' },
      _silent: true,
    } as any)
    const h01WpId = (idRes as any)?.wp_id
    if (!h01WpId) {
      ElMessage.info('未找到 H0-1 函证结果汇总底稿')
      return
    }

    const cfg = await api.get<any>(`/api/workpapers/${h01WpId}/render-config`, { _silent: true } as any)
    const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
    let rows: any[] = []
    for (const sheet of sheets) {
      const hd = sheet?.html_data ?? sheet?.htmlData
      if (hd?._format === 'confirmation-v1' && Array.isArray(hd.rows)) {
        rows = hd.rows
        break
      }
    }
    if (rows.length === 0) {
      ElMessage.info('H0-1 暂无函证数据')
      return
    }

    const unreplied = rows.filter(
      (r) => r.match_status === '未回函' || (r.is_replied === false && r.match_status !== '相符'),
    )
    if (unreplied.length === 0) {
      ElMessage.info('H0-1 暂无未回函项目')
      return
    }

    const imported: Partial<AlternativeCompany>[] = unreplied.map((r) => ({
      entity_name: r.entity_name || '',
      confirm_index: r.confirm_index,
      _source: 'auto',
      balance: {
        item_name: r.account_type || '固定资产',
        closing_balance: Number(r.amount) || 0,
      },
    }))
    data.importCompanies(imported)
    ElMessage.success(`已从 H0-1 带入 ${imported.length} 个未回函项目`)
  } catch (e: any) {
    if (e?.response?.status === 404) {
      ElMessage.info('未找到 H0-1 函证结果汇总底稿')
    } else {
      ElMessage.warning('从 H0-1 带入失败：' + (e?.message || '未知错误'))
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
  // 优先使用后端导入（useH0ImportExport composable）
  if (props.wpId) {
    try {
      await handleImportViaBackend(file)
    } catch {
      // 后端导入失败，降级到前端 xlsx 解析
      await handleImportFileFallback(file)
    }
  } else {
    await handleImportFileFallback(file)
  }
  if (importFileInput.value) importFileInput.value.value = ''
}

async function handleImportFileFallback(file: File) {
  try {
    const { read, utils } = await import('xlsx')
    const buf = await file.arrayBuffer()
    const wb = read(buf, { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rawRows: Record<string, any>[] = utils.sheet_to_json(ws)
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
  }
}

async function handleExportExcel() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 公司清单模板
    const companyHeaders = ['序号', '函证索引号', '供应商/客户名称']
    const companyExample = ['1', 'D0-001', '示例公司（请删除）']
    const wsCompany = utils.aoa_to_sheet([companyHeaders, companyExample])
    wsCompany['!cols'] = [{ wch: 6 }, { wch: 12 }, { wch: 30 }]
    utils.book_append_sheet(wb, wsCompany, '公司清单')

    // Sheet 2~5: 4 区块列头
    const blockSheets: { key: string; name: string }[] = [
      { key: 'block1', name: '①期后验收/权属证据' },
      { key: 'block2', name: '②期末余额支持性证据' },
      { key: 'block3', name: '③本期新增资产检查' },
      { key: 'block4', name: '④抵押担保/融资租赁' },
    ]
    for (const { key, name } of blockSheets) {
      const cols = BLOCK_COLUMN_CONFIGS_H05[key].columns
      const headers = cols.map(c => c.label)
      const ws = utils.aoa_to_sheet([headers])
      ws['!cols'] = cols.map(c => ({ wch: Math.max((c.width || 100) / 8, (c.label?.length || 4) * 2.5) }))
      utils.book_append_sheet(wb, ws, name)
    }

    // Sheet 6: 填写说明
    const instructions = [
      ['H0-5 固定资产循环替代程序 — 导入模板说明'],
      [''],
      ['【Sheet 说明】'],
      ['  公司清单：填写替代程序的公司列表（必须），导入后每公司自动创建 4 区块检查记录'],
      ['  ①期后验收/权属：固定资产权属与验收证据检查'],
      ['  ②期末余额：合同/发票/付款凭证等支持性证据'],
      ['  ③本期新增：请购审批、到货验收、转固手续'],
      ['  ④抵押融资租赁：抵押合同、融资租赁合同、他项权证'],
      [''],
      ['【公司清单列说明】'],
      ['  序号：自动生成（留空即可）'],
      ['  函证索引号：来自 H0-1 的索引号（如 H0-001），用于跨底稿追溯'],
      ['  供应商/客户名称：被检查公司全称（必填）'],
      [''],
      ['【注意事项】'],
      ['  1. 先导入"公司清单" Sheet（系统仅读取第一个 Sheet 的公司数据）'],
      ['  2. 已存在相同索引号的公司不会重复导入'],
      ['  3. 导入后选中公司 → 在 4 个区块中录入检查明细'],
      ['  4. 权属证据检查比例 = 区块②支持性证据合计 / 期末余额（自动计算）'],
      ['  5. 验收证据检查比例 = 区块①凭证金额合计 / 期末余额（自动计算）'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 80 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, 'H0-5固定资产循环替代程序_导入模板.xlsx')
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
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 公司汇总
    const summaryHeaders = ['序号', '索引号', '被函证单位', '完成度', '权属证据比例', '验收证据比例', '是否异常']
    const summaryData = data.companies.value.map(c => [
      c.seq ?? '',
      c.confirm_index ?? '',
      c.entity_name ?? '',
      `${data.getCompletionStatus(c).completed}/4`,
      data.getCheckRatio(c, 'ownership') !== null ? `${data.getCheckRatio(c, 'ownership')!.toFixed(1)}%` : 'N/A',
      data.getCheckRatio(c, 'acceptance') !== null ? `${data.getCheckRatio(c, 'acceptance')!.toFixed(1)}%` : 'N/A',
      data.hasAbnormal(c) ? '是' : '否',
    ])
    const wsSummary = utils.aoa_to_sheet([summaryHeaders, ...summaryData])
    wsSummary['!cols'] = [{ wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 8 }, { wch: 10 }, { wch: 10 }, { wch: 8 }]
    utils.book_append_sheet(wb, wsSummary, '公司汇总')

    // 每个区块一个 Sheet
    const blockSheets: { key: BlockType; name: string }[] = [
      { key: 'block1', name: '①期后验收/权属证据' },
      { key: 'block2', name: '②期末余额支持性证据' },
      { key: 'block3', name: '③本期新增资产检查' },
      { key: 'block4', name: '④抵押担保/融资租赁' },
    ]
    for (const { key, name } of blockSheets) {
      const cols = BLOCK_COLUMN_CONFIGS_H05[key].columns
      const headers = ['被函证单位', ...cols.map(c => c.label)]
      const rows: any[][] = []
      for (const company of data.companies.value) {
        const blockRows = getBlockRows(company, key)
        for (const row of blockRows) {
          rows.push([
            company.entity_name ?? '',
            ...cols.map(c => row[c.field] ?? ''),
          ])
        }
      }
      const ws = utils.aoa_to_sheet([headers, ...rows])
      ws['!cols'] = [{ wch: 20 }, ...cols.map(c => ({ wch: Math.max((c.width || 80) / 8, 10) }))]
      utils.book_append_sheet(wb, ws, name)
    }

    writeFileXLSX(wb, 'H0-5固定资产循环替代程序_数据导出.xlsx')
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
    const ownershipRatio = data.getCheckRatio(company, 'ownership')
    const acceptanceRatio = data.getCheckRatio(company, 'acceptance')
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
        `对${entityName}执行替代程序，共检查 ${totalRows} 笔凭证/单据（期后验收/权属 ${b1Count} 笔、期末余额证据 ${b2Count} 笔、本期新增 ${b3Count} 笔、抵押融资租赁 ${b4Count} 笔），完成度 ${status.completed}/4 区块。`
      )
    } else {
      parts.push(`对${entityName}执行替代程序，尚未录入检查数据。`)
    }

    if (ownershipRatio !== null || acceptanceRatio !== null) {
      const oPart = ownershipRatio !== null ? `权属证据检查比例 ${ownershipRatio.toFixed(1)}%` : '权属证据检查比例待计算'
      const aPart = acceptanceRatio !== null ? `验收证据检查比例 ${acceptanceRatio.toFixed(1)}%` : '验收证据检查比例待计算'
      parts.push(`${oPart}，${aPart}。`)
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
  // 通知兄弟 H0 sheet 刷新（confirmation:updated EventBus 联动）
  if (props.projectId) {
    eventBus.emit('confirmation:updated', {
      projectId: props.projectId,
      wpCode: 'H0-5',
      wpId: props.wpId,
      timestamp: Date.now(),
    })
  }
}

// ─── 导入导出下拉（el-dropdown，复用 useH0ImportExport 后端三端点） ────────────

async function handleDropdownExportTemplate() {
  try {
    await h0Ie.exportTemplate('H0-5')
    ElMessage.success('模板已导出')
  } catch (e: any) {
    ElMessage.error('导出模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleDropdownExportData() {
  if (data.companies.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    await h0Ie.exportData('H0-5')
    ElMessage.success('数据已导出')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

async function handleDropdownImportData() {
  importFileInput.value?.click()
}

function handleIeCommand(command: string) {
  switch (command) {
    case 'export-template': handleDropdownExportTemplate(); break
    case 'export-data': handleDropdownExportData(); break
    case 'import-data': handleDropdownImportData(); break
  }
}

async function handleImportViaBackend(file: File) {
  try {
    const result = await h0Ie.importData('H0-5', file)
    if (result && result.rowCount != null) {
      ElMessage.success(`成功导入 ${result.rowCount} 条数据`)
      // 重新加载数据
      if (props.wpId) {
        const cfg = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
        const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
        for (const sheet of sheets) {
          const hd = sheet?.html_data ?? sheet?.htmlData
          if (hd?._format === 'alternative-h05-v1') {
            selfLoadedData.value = hd
            break
          }
        }
      }
    } else {
      ElMessage.success('导入完成')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '未知错误'))
  }
}

// ─── 行级 OCR：上传证据文件 → contract-ocr 识别 → 确认 → merge 填入 ────────
const ocrLoadingRowId = ref<string | null>(null)

/** OCR 识别字段 → 各区块行字段的映射（固定资产/在建工程证据） */
const OCR_FIELD_MAP: Record<BlockType, Record<string, string>> = {
  block1: {
    date: 'voucher_date', 日期: 'voucher_date',
    voucher_no: 'voucher_no', 凭证号: 'voucher_no', 凭证编号: 'voucher_no',
    amount: 'voucher_amount', 金额: 'voucher_amount',
    asset_name: 'asset_name', 资产名称: 'asset_name',
    cert_no: 'title_cert_no', 证书编号: 'title_cert_no', 权属证书: 'title_cert_no',
    owner: 'title_owner', 权属人: 'title_owner',
  },
  block2: {
    date: 'voucher_date', 日期: 'voucher_date',
    voucher_no: 'voucher_no', 凭证号: 'voucher_no', 凭证编号: 'voucher_no',
    amount: 'voucher_amount', 金额: 'voucher_amount',
    contract_no: 'contract_date_no', 合同编号: 'contract_date_no',
    vendor: 'contract_vendor', 供应商: 'contract_vendor',
    contract_amount: 'contract_amount', 合同金额: 'contract_amount',
    invoice_no: 'invoice_date_no', 发票编号: 'invoice_date_no',
    invoice_amount: 'invoice_amount', 发票金额: 'invoice_amount',
    payment_amount: 'payment_amount', 付款金额: 'payment_amount',
  },
  block3: {
    date: 'voucher_date', 日期: 'voucher_date',
    voucher_no: 'voucher_no', 凭证号: 'voucher_no', 凭证编号: 'voucher_no',
    amount: 'voucher_amount', 金额: 'voucher_amount',
    asset_name: 'recv_asset_name', 资产名称: 'recv_asset_name',
    quantity: 'recv_qty', 数量: 'recv_qty',
    cost: 'cap_cost', 原值: 'cap_cost', 转固原值: 'cap_cost',
  },
  block4: {
    date: 'voucher_date', 日期: 'voucher_date',
    voucher_no: 'voucher_no', 凭证号: 'voucher_no', 凭证编号: 'voucher_no',
    amount: 'voucher_amount', 金额: 'voucher_amount',
    mortgage_contract: 'mortgage_contract', 抵押合同: 'mortgage_contract', 合同编号: 'mortgage_contract',
    holder: 'mortgage_holder', 抵押权人: 'mortgage_holder',
    mortgage_amount: 'mortgage_amount', 担保金额: 'mortgage_amount',
    lease_contract: 'lease_contract', 租赁合同: 'lease_contract',
    lessor: 'lease_lessor', 出租方: 'lease_lessor',
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
    await ElMessageBox.confirm(`识别到证据信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', {
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
  handleExportTemplate: handleDropdownExportTemplate,
  handleExportData: handleDropdownExportData,
  handleImport: handleDropdownImportData,
  handleImportClick: handleDropdownImportData,
  handleDownloadImportTemplate: handleDropdownExportTemplate,
})
</script>

<style scoped>
.gt-confirmation-alternative-h05 {
  padding: 8px 0;
}

.gt-confirmation-alternative-h05__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.gt-confirmation-alternative-h05__title {
  font-size: 15px;
  font-weight: 600;
}

.gt-confirmation-alternative-h05__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-confirmation-alternative-h05__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-h05__header-tip {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-h05__detail {
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

/* 二级小节标题（「二、检查过程记录」内部分区） */
.detail-subsection__header {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin: 12px 0 6px;
  padding-left: 6px;
  border-left: 3px solid var(--el-color-primary-light-5);
}

/* 字段级源模板提示（如样本量计算器说明） */
.detail-section__field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-top: 2px;
}

/* 源模板方法论上下文 / 源外增强标注（琥珀色左边线 + 浅黄背景） */
.src-hint {
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  padding: 6px 10px;
  border-radius: 3px;
  margin-bottom: 10px;
}

.src-hint__badge {
  font-size: 12px;
  font-weight: 600;
  color: #b88230;
  margin-bottom: 2px;
}

.src-hint__body {
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.detail-card {
  --el-card-padding: 10px;
}

/* 编制说明折叠（底部） */
.gt-confirmation-alternative-h05__guidance {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  border-top: 1px dashed var(--el-border-color);
  padding-top: 8px;
}

.gt-confirmation-alternative-h05__guidance > summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.guidance-group {
  margin-top: 8px;
}

.guidance-group__title {
  font-weight: 600;
  margin-bottom: 2px;
}

.guidance-group__list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.7;
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
</style>
