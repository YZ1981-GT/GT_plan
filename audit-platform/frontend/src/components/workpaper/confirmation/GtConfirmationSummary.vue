<template>
  <div class="gt-confirmation-summary">
    <!-- 旧格式降级：检测 htmlData 无 _format 时显示只读 GtGridSheet -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-summary__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <!-- Fallback: 使用 GtGridSheet 只读渲染 -->
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：完整 confirmation-v1 组件 -->
    <template v-else>
      <!-- 无数据空态：仅首次打开（从未操作过）显示 onboarding -->
      <div v-if="data.rows.value.length === 0 && !hasInteracted" class="gt-confirmation-summary__onboarding">
        <div class="gt-confirmation-summary__onboarding-card">
          <div class="gt-confirmation-summary__onboarding-icon">✉️</div>
          <h3 class="gt-confirmation-summary__onboarding-title">开始编制函证底稿</h3>
          <div class="gt-confirmation-summary__onboarding-steps">
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">1</span>
              <span>新增函证对象或从 Excel 导入清单</span>
            </div>
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">2</span>
              <span>填写发函信息（科目、金额、方式）并寄出</span>
            </div>
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">3</span>
              <span>登记回函结果，处理差异或执行替代程序</span>
            </div>
            <div class="gt-confirmation-summary__step">
              <span class="gt-confirmation-summary__step-no">4</span>
              <span>确认覆盖率达标后填写审计结论</span>
            </div>
          </div>
          <div class="gt-confirmation-summary__onboarding-actions">
            <el-button v-if="!readonly" type="primary" @click="handleAdd">+ 新增函证对象</el-button>
            <el-button v-if="!readonly" @click="handleDownloadImportTemplate">下载导入模板</el-button>
            <el-button v-if="!readonly" @click="handleImportClick">从 Excel 导入</el-button>
            <el-button
              v-if="!readonly"
              :loading="syncing"
              title="将已发函/已回函的行同步到项目函证中心台账（供工作包摘要/覆盖率消费）"
              @click="handleSyncHub"
            >同步到函证中心</el-button>
          </div>
        </div>
      </div>

      <!-- 有数据时：紧凑布局 -->
      <template v-else>
        <!-- 看板区（数据充分时默认展开，数据少时默认折叠减少干扰） -->
        <el-collapse v-model="expandedSections">
          <el-collapse-item :title="dashboardTitle" name="dashboard">
            <ConfirmationDashboard :metrics="data.dashboardMetrics.value" :coverage="data.coverageMetrics.value" />
          </el-collapse-item>
        </el-collapse>

        <!-- 科目 Tab + 视图切换 -->
        <div class="gt-confirmation-summary__toolbar">
          <ConfirmationTabs :tabs="data.accountTabs.value" :active-tab="data.activeTab.value" @update:active-tab="data.activeTab.value = $event" />
          <div class="gt-confirmation-summary__toolbar-right">
            <!--
              H0：按源模板七条 VLOOKUP 从 H0-2 带入（被询证单位名称/函证方式/收件地址/
              地址核查是否一致/回函方式/回函发出地址/发函地址与回函地址是否一致）。
              spec: h0-confirmation-source-fidelity-and-linkage R5.1
            -->
            <el-button
              v-if="!readonly && isH0"
              size="small"
              :loading="h0Pulling"
              title="按源模板 VLOOKUP 关系，从 H0-2 核实被函证单位信息带入 7 列（匹配键=询证函索引号）"
              @click="handleH0PullFromEntityVerify"
            >
              从 H0-2 带入
            </el-button>
            <el-tag
              v-if="syncStatusSummary.total > 0"
              size="small"
              :type="syncStatusSummary.unsynced === 0 ? 'success' : 'info'"
              title="已同步=已回写函证中心台账标识的行；待同步=已进入函证程序但尚未同步的行"
            >已同步 {{ syncStatusSummary.synced }} · 待同步 {{ syncStatusSummary.unsynced }}</el-tag>
            <el-button
              v-if="!readonly && isE0"
              size="small"
              :loading="importingLists"
              title="从 E0-3~E0-6 发函清单筛「是否函证=是」的账户带入本汇总表"
              @click="handleImportE0Lists"
            >从发函清单带入</el-button>
            <el-button
              v-if="!readonly"
              size="small"
              :loading="syncing"
              title="将已发函/已回函的行同步到项目函证中心台账（供工作包摘要/覆盖率消费）"
              @click="handleSyncHub"
            >同步到函证中心</el-button>
            <el-radio-group v-model="viewMode.viewMode.value" size="small">
              <el-radio-button value="list">列表视图</el-radio-button>
              <el-radio-button value="grid">完整表格</el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <!-- 列表视图 -->
        <template v-if="viewMode.viewMode.value === 'list'">
          <ConfirmationMaster
            :rows="data.filteredRows.value"
            :readonly="readonly"
            :selected-ids="selectedIds"
            @update:selected-ids="selectedIds = $event"
            @add="handleAdd"
            @delete="handleDelete"
            @save="handleSave"
            @download-template="handleDownloadImportTemplate"
            @import-data="handleImportClick"
            @show-formula="showFormulaDialog = true"
            @row-click="handleRowClick"
          />
          <ConfirmationDetail
            :row="currentRow"
            :readonly="readonly"
            :dict-data="dictData"
            @update="handleFieldUpdate"
          />
        </template>

        <!-- 完整表格视图 -->
        <template v-else>
          <ConfirmationFullGrid
            :rows="data.filteredRows.value"
            :readonly="readonly"
            :cycle="confirmCycle"
            @update="handleGridUpdate"
          />
        </template>

        <!-- F0 函证情况矩阵（4品种×8指标，从 grid + F0-5/F0-6 自动聚合） -->
        <div v-if="isF0" class="gt-confirmation-summary__f0-matrix">
          <el-collapse v-model="expandedSections">
            <el-collapse-item title="一、函证情况" name="f0-matrix">
              <div class="gt-confirmation-summary__f0-matrix-table">
                <el-table v-loading="f0SourcesLoading" :data="f0MatrixTableData" border size="small" style="width: 100%">
                  <el-table-column prop="label" label="项目" width="260" fixed />
                  <el-table-column
                    v-for="cat in F0_MATRIX_CATEGORIES"
                    :key="cat"
                    :label="cat"
                    align="right"
                    min-width="130"
                  >
                    <template #default="{ row }">
                      <!-- 账面金额行：可手工填写（四表取不到时的唯一入口） -->
                      <el-input
                        v-if="row.editable && !readonly"
                        :model-value="row[cat] === null ? '' : String(row[cat])"
                        size="small"
                        placeholder="—"
                        style="text-align:right"
                        @change="(v: string) => handleF0MatrixOverride(cat, row.label, v)"
                      />
                      <span v-else-if="row[cat] === null" class="f0-matrix-empty">-</span>
                      <span v-else-if="row.kind === 'ratio'" class="f0-matrix-ratio">{{ (row[cat] * 100).toFixed(2) }}%</span>
                      <span v-else class="f0-matrix-amount">{{ fmtMatrixAmount(row[cat]) }}</span>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="gt-confirmation-summary__f0-matrix-hint">
                  <el-text type="info" size="small">
                    发函金额 / 回函确认金额 / 替代测试确认金额均按源模板公式自上区明细表聚合（依次取「金额」「可确认金额」「替代后可确认金额」三列）；账面金额取自 F1/F3/F4 审定表（可手工覆盖）。「-」表示数据缺失。
                  </el-text>
                  <div v-if="f0SourceHint" style="margin-top:4px">
                    <el-text type="success" size="small">{{ f0SourceHint }}</el-text>
                    <el-button link size="small" :loading="f0SourcesLoading" style="margin-left:8px" @click="loadF0Sources">🔄 刷新取数</el-button>
                  </div>
                  <!-- 取数失败如实暴露（_silent 不弹窗，但不能连提示都没有） -->
                  <div v-if="f0SourceErrors.length" style="margin-top:4px">
                    <el-text type="warning" size="small">
                      取数未完成：{{ f0SourceErrors.join('；') }}
                    </el-text>
                  </div>
                  <!-- 勾稽：上区「替代后可确认金额」合计 ?= F0-5 + F0-6 凭证金额合计 -->
                  <div v-if="f0AltCheck && f0AltCheck.level !== 'no-data'" style="margin-top:4px">
                    <el-tag :type="f0AltCheck.level === 'ok' ? 'success' : 'danger'" size="small" effect="plain">
                      {{ f0AltCheck.level === 'ok' ? '替代确认勾稽通过' : '替代确认勾稽不符' }}
                    </el-tag>
                    <el-text :type="f0AltCheck.level === 'ok' ? 'success' : 'danger'" size="small" style="margin-left:6px">
                      {{ f0AltCheck.message }}
                    </el-text>
                  </div>
                  <div v-if="f0AltOverlapCount > 0" style="margin-top:4px">
                    <el-text type="warning" size="small">
                      提示：有 {{ f0AltOverlapCount }} 行「可确认金额」与「替代后可确认金额」相等（积极式未回函行由替代金额派生），
                      末行比例按源模板公式 (替代+回函)/账面 计算时该部分会计入两次，请复核该行 Y 列口径。
                    </el-text>
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!--
          H0（固定资产循环函证）下区四块专属组件：
          一、函证情况（品种×8指标矩阵）/ 二、样本选择 / 三、审计说明 / 四、审计结论
          源模板 `函证结果汇总表H0-1` R28~R37 + R42~R69。
          🔴 `v-if="isH0"` 门控 → 其余六枢纽模板逐字节不变。
          spec: h0-confirmation-source-fidelity-and-linkage R2.1
        -->
        <H0SummaryLowerZone
          v-if="isH0"
          ref="h0LowerRef"
          :rows="data.rows.value"
          :readonly="readonly"
          :responses="h0Responses"
          :book-amounts="h0BookAmounts"
          :book-source-codes="h0BookSourceCodes"
          :book-conflicts="h0BookConflicts"
          :category-options="h0CategoryOptions"
          :refreshing="h0Refreshing"
          :ai-loading-key="h0AiLoadingKey"
          @save="handleH0LowerSave"
          @ai-generate="handleH0LowerAi"
          @review="handleH0LowerReview"
          @refresh-book-amounts="handleH0RefreshBookAmounts"
        />

        <!--
          G0（投资循环函证）下区专属组件：
          一、函证情况（8 品种 × 8 指标矩阵）/ 三、审计说明（5 项）/ 四、审计结论 / 编制说明
          🔴 **不含「二、样本选择」** —— 那由下方既有 `ConfirmationSampling`（`isG0` → 6 项）承担，
             两处都渲染会让同一份 `SamplingConfig` 有两个录入口（双真源）。
          🔴 `v-if="isG0"` 门控 → 其余六枢纽模板逐字节不变。
          spec: g0-confirmation-source-alignment R3.1~R3.5 / R3.7~R3.11
        -->
        <G0SummaryLowerZone
          v-if="isG0"
          ref="g0LowerRef"
          :rows="data.rows.value"
          :readonly="readonly"
          :responses="g0Responses"
          :book-amounts="g0Sources?.bookAmounts"
          :diagnostics="g0Sources?.diagnostics"
          :refreshing="g0SourcesLoading"
          :ai-loading-key="g0AiLoadingKey"
          @save="handleG0LowerSave"
          @ai-generate="handleG0LowerAi"
          @refresh-book-amounts="loadG0Sources"
        />

        <!-- 辅助区（默认折叠） -->
        <el-collapse v-model="expandedSections">
          <el-collapse-item title="样本选择" name="sampling">
            <ConfirmationSampling
              :data="data.sampling.value"
              :readonly="readonly"
              :dict-data="dictData"
              :cycle="confirmCycle"
              :total-count="data.rows.value.length"
              :total-amount="data.rows.value.reduce((sum, r) => sum + (r.amount || 0), 0)"
              :sample-count="data.rows.value.length"
              :sample-amount="data.rows.value.reduce((sum, r) => sum + (r.amount || 0), 0)"
              @update="handleSamplingUpdate"
            />
          </el-collapse-item>

          <el-collapse-item title="审计说明" name="notes">
            <ConfirmationNotes
              :data="data.notes.value"
              :readonly="readonly"
              :wp-id="wpId"
              :project-id="projectId"
              :wp-code="wpCode"
              :stats="notesAiStats"
              @update="handleNotesUpdate"
            />
          </el-collapse-item>

          <el-collapse-item title="审计结论" name="conclusion">
            <ConfirmationConclusion :data="data.conclusion.value" :readonly="readonly" @update="handleConclusionUpdate" />
          </el-collapse-item>
        </el-collapse>
      </template>
    </template>

    <!-- 隐藏文件选择器（导入用，放在组件根层级确保始终可访问） -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

    <!-- 右键菜单 -->
    <ConfirmationContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :readonly="readonly"
      @update:visible="contextMenu.visible = $event"
      @action="handleContextAction"
    />

    <!-- 公式管理弹窗 -->
    <el-dialog v-model="showFormulaDialog" title="公式管理 — 函证结果汇总表" width="640px" append-to-body>
      <div class="gt-formula-dialog">
        <h4>表内自动计算规则</h4>
        <el-table :data="formulaRules" border size="small" style="width:100%">
          <el-table-column prop="field" label="字段" width="120" />
          <el-table-column prop="formula" label="计算规则" min-width="300" />
          <el-table-column prop="source" label="来源" width="100" />
        </el-table>

        <h4 style="margin-top:20px">跨表校对关系</h4>
        <el-table :data="crossRefRules" border size="small" style="width:100%">
          <el-table-column prop="field" label="本表字段" width="120" />
          <el-table-column prop="target" label="关联底稿" width="120" />
          <el-table-column prop="rule" label="校对规则" min-width="260" />
        </el-table>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
// 🔴 与 `http` 并存是有意的：`http.get()` 返回 AxiosResponse（payload 在 .data），
//    `api.get()` 直接返回业务数据。跨底稿取数一律用 `api`（平台 20+ 处同形）。
import { api } from '@/services/apiProxy'
import { useConfirmationData } from './composables/useConfirmationData'
import { useViewMode } from './composables/useViewMode'
import { syncHubFromSummary, hubStatusToRowPatch, accountTypeToHubType, rowToHubStatus } from './coordination/syncHubFromSummary'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { emitConfirmationCompletedFromSummary, isConfirmationInFlight } from './coordination/emitConfirmationCompleted'
import { importE0ListsToSummary } from './coordination/importE0ListsToSummary'
import { buildCrossRefRules, getCycleConfirmationMeta } from './coordination/cycleConfirmationMeta'
import { CONFIRMATION_DICTS, fallbackOptions } from './coordination/confirmationDicts'
import H0SummaryLowerZone from './H0SummaryLowerZone.vue'
import { H0_SLOT_LABELS } from './h0SummaryMatrix'
import G0SummaryLowerZone from '../g0-confirmation/G0SummaryLowerZone.vue'
import {
  loadG0MatrixSources,
  type G0MatrixSources,
} from '../g0-confirmation/g0MatrixDataSources'
import { G0_AUDIT_NOTE_DEFS, G0_LOWER_KEY_PREFIX } from '../g0-confirmation/g0SummaryLowerZone'
import {
  describeH0PullResult,
  pullH0SummaryFromEntityVerify,
} from './h0SummaryFromEntityVerify'
import type { EntityVerifyRow } from './entityVerify/entityVerifyTypes'
import {
  buildF0SummaryMatrix,
  checkAltConsistency,
  detectAltOverlapRows,
  F0_MATRIX_CATEGORIES,
  F0_MATRIX_LABELS,
  type F0MatrixCell,
  type F0Category,
  type F0Metric,
  type F0AltConsistency,
} from './composables/f0SummaryAggregation'
import { loadF0MatrixSources, matrixOverrideItemId, type F0MatrixSources } from './composables/f0MatrixDataSources'
import type { ConfirmationRow } from './confirmationTypes'

import ConfirmationDashboard from './ConfirmationDashboard.vue'
import ConfirmationTabs from './ConfirmationTabs.vue'
import ConfirmationMaster from './ConfirmationMaster.vue'
import ConfirmationDetail from './ConfirmationDetail.vue'
import ConfirmationFullGrid from './ConfirmationFullGrid.vue'
import ConfirmationSampling from './ConfirmationSampling.vue'
import ConfirmationNotes from './ConfirmationNotes.vue'
import ConfirmationConclusion from './ConfirmationConclusion.vue'
import ConfirmationContextMenu from './ConfirmationContextMenu.vue'

// GtGridSheet for legacy fallback
const GtGridSheet = defineAsyncComponent(() => import('../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'confirmation-v1')

// 枢纽标识（Cycle_Variant_Column 列集合选取，confirmation-shared-model-extension 决策 2）
// 由 wpCode（D0-1/E0-1/…/L0-1）派生：取前缀字母+0 组，回退 D0。
const confirmCycle = computed<import('./confirmationColumnSpec').ConfirmCycle>(() => {
  const m = String(props.wpCode || '').match(/^([A-Z])0/)
  const c = m ? (`${m[1]}0` as import('./confirmationColumnSpec').ConfirmCycle) : 'D0'
  const valid: import('./confirmationColumnSpec').ConfirmCycle[] = ['D0', 'E0', 'F0', 'G0', 'H0', 'K0', 'L0']
  return valid.includes(c) ? c : 'D0'
})

// E0（货币资金/借款）循环：提供「从发函清单（E0-3~E0-6）带入」入口
const isE0 = computed(() => confirmCycle.value === 'E0')
const importingLists = ref(false)

// F0（存货循环函证）：矩阵聚合
const isF0 = computed(() => confirmCycle.value === 'F0')

// ─── H0（固定资产循环函证）下区四块 ─────────────────────────────────────────

const isH0 = computed(() => confirmCycle.value === 'H0')
const h0LowerRef = ref<{ applyAiText: (key: string, text: string) => void } | null>(null)
const h0Responses = ref<Record<string, string>>({})
const h0Refreshing = ref(false)
const h0AiLoadingKey = ref<string | null>(null)

/**
 * 后端加法式注入的按品种账面金额（`_inject_h0_book_amounts`）。
 *
 * 🔴 两态必须可区分（h0 spec R3.8 / Error Handling）：
 * - **键不存在** = 注入整体失败 / 未取数 → 前端渲染「未取数，可手填」
 * - 键存在且值为 `null` = 本项目科目表无该科目 → 渲染「本项目无此科目」
 * 故此处用 `?.` 取值后**不做 `?? {}` 兜底成空对象**：`undefined` 与 `{}` 语义不同。
 */
const h0BookAmounts = computed<Record<string, number | null> | undefined>(() => {
  const v = props.htmlData?.project_context?.h0_book_amounts
  return v && typeof v === 'object' ? (v as Record<string, number | null>) : undefined
})
const h0BookSourceCodes = computed<Record<string, Record<string, unknown>> | undefined>(() => {
  const v = props.htmlData?.project_context?.h0_book_source_codes
  return v && typeof v === 'object' ? (v as Record<string, Record<string, unknown>>) : undefined
})
/**
 * `report_config` 与项目科目表的冲突告警。
 *
 * 🔴 后端下发的是**三元组** `[槽键, 报表公式给的码集合, 按名定位到的实际码]`
 * （`SemanticAccountResult.conflicts`），直接 `String(...)` 会渲染成
 * `impairment,1601,1602,1606,1603` 这种读不出含义的裸串（浏览器实测暴露）。
 * 审计 UI 必须能追溯逻辑 → 在此翻成中文句子。
 */
const h0BookConflicts = computed<string[]>(() => {
  const v = props.htmlData?.project_context?.h0_book_conflicts
  if (!Array.isArray(v)) return []
  return v.map((c) => {
    if (Array.isArray(c) && c.length >= 3) {
      const [slot, reportCodes, actualCodes] = c.map((x) => String(x ?? ''))
      const label = H0_SLOT_LABELS[slot] || slot
      return `「${label}」槽：报表行公式引用 ${reportCodes || '（空）'}，`
        + `而本项目科目表按名定位到 ${actualCodes || '（无）'} —— 已以科目表为准，请复核报表行公式。`
    }
    return String(c)
  })
})

/** 矩阵可选品种 = 「账户/交易」枚举（品种名不在其中则按品种 SUMIF 恒空） */
const h0CategoryOptions = computed<string[]>(
  () => [...fallbackOptions(CONFIRMATION_DICTS.ACCOUNT_TYPE)],
)

/** 拉取下区录入值（矩阵品种列 / 样本选择 / 审计说明 / 结论 的 checklist responses） */
async function loadH0Responses() {
  if (!isH0.value || !props.wpId) return
  try {
    // 🔴 必须带 `/api` 前缀 —— `utils/http` 的 baseURL 是 `/`，且 vite 只代理 `/api`；
    //    漏掉会打到 dev server 拿回 index.html（200 + HTML），`Array.isArray` 判否后
    //    静默变成空 map（本函数改造前即如此，浏览器实测暴露）。
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = (res.data?.data ?? res.data ?? []) as Array<Record<string, any>>
    const map: Record<string, string> = {}
    for (const item of Array.isArray(list) ? list : []) {
      const id = String(item.item_id ?? item.itemId ?? '')
      if (!id.startsWith('H0-1-')) continue
      const v = item.remark ?? item.conclusion ?? item.value ?? ''
      map[id] = v === null || v === undefined ? '' : String(v)
    }
    h0Responses.value = map
  } catch (e: any) {
    console.warn('[GtConfirmationSummary] H0 下区录入值加载失败:', e?.message)
  }
}

/**
 * 下区录入落库。
 *
 * 🔴🔴 **不能** `emit('save', { itemId, value })`：`confirmation-summary` 的宿主 save
 * 处理器把载荷整体写成该 sheet 的 `parsed_data.html_data[sheetName]` —— 浏览器实测
 * （项目 `c8621493`）曾把 `html_data['函证结果汇总表H0-1']` 整体覆盖成
 * `{"itemId":"H0-1-matrix-seq","value":"4"}`，**连带清掉函证行**。
 * 下区录入是 itemId 维度的，必须直接走平台标准 `checklist-responses` PUT
 * （与 `useF2FormData.saveImmediate` 等 40+ 处同形）。
 */
async function handleH0LowerSave(itemId: string, value: string) {
  h0Responses.value = { ...h0Responses.value, [itemId]: value }
  if (!props.wpId) return
  try {
    const payload: Record<string, any> = {
      items: [{ item_id: itemId, remark: value, conclusion: null }],
    }
    // 空字符串会让后端 UUID 校验 422；缺省时服务端按底稿解析 project_id
    if (props.projectId) payload.project_id = props.projectId
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, payload)
  } catch (e: any) {
    console.warn('[GtConfirmationSummary] H0 下区录入保存失败:', e?.message)
    ElMessage.warning('保存失败：' + (e?.message || '网络错误'))
  }
}

/** 重新拉 render-config 让后端重算账面金额（四表重新入库后用） */
async function handleH0RefreshBookAmounts() {
  if (!props.wpId) {
    ElMessage.warning('缺少底稿标识，无法刷新取数')
    return
  }
  h0Refreshing.value = true
  try {
    await http.get(`/workpapers/${props.wpId}/render-config`)
    ElMessage.success('已请求后端重算账面金额，请刷新页面查看最新取数')
  } catch (e: any) {
    ElMessage.error(`刷新取数失败：${e?.message || '未知错误'}`)
  } finally {
    h0Refreshing.value = false
  }
}

/** 下区审计说明/结论的 AI 辅助（走平台唯一正解端点 /ai/generate-text） */
async function handleH0LowerAi(aiSection: string, key: string) {
  if (!props.wpId) {
    ElMessage.warning('缺少底稿标识，无法调用 AI')
    return
  }
  h0AiLoadingKey.value = key
  try {
    // H0 专属 AI 端点（`_h0_confirmation_ai.py`）；section 必须在其
    // `_SUPPORTED_SECTIONS` 已登记，否则 400。载荷字段名为
    // `existingContent` / `relatedContext`（驼峰），传错会被静默忽略。
    const res = await http.post(`/workpapers/${props.wpId}/h0/ai-generate`, {
      section: aiSection,
      existingContent: h0Responses.value[key] ?? '',
      relatedContext: {
        底稿编码: String(props.wpCode || 'H0-1'),
        函证行数: String(data.rows.value.length),
        已回函行数: String(data.rows.value.filter((r: ConfirmationRow) => r.is_replied === '是' || r.is_replied === true).length),
        不符行数: String(data.rows.value.filter((r: ConfirmationRow) => r.match_status === '不符').length),
      },
    })
    const content = String((res.data?.data ?? res.data)?.content ?? '')
    if (!content) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    h0LowerRef.value?.applyAiText(key, content)
    ElMessage.success('AI 已生成，请复核后保存')
  } catch (e: any) {
    ElMessage.error(`AI 生成失败：${e?.message || '未知错误'}`)
  } finally {
    h0AiLoadingKey.value = null
  }
}

// ─── H0：从 H0-2 带入 7 列（源模板 VLOOKUP） ────────────────────────────────

const h0Pulling = ref(false)

async function handleH0PullFromEntityVerify() {
  if (!props.projectId) {
    ElMessage.warning('缺少项目标识，无法定位 H0-2')
    return
  }
  if (!data.rows.value.length) {
    ElMessage.warning('请先在明细表录入函证行')
    return
  }

  let mode: 'fill_blank' | 'overwrite' = 'fill_blank'
  try {
    await ElMessageBox.confirm(
      '「仅补空值」保留已填内容（推荐，手工优先）；「覆盖全部」用 H0-2 的值覆盖本表这 7 列。',
      '从 H0-2 带入',
      {
        confirmButtonText: '仅补空值',
        cancelButtonText: '覆盖全部',
        distinguishCancelAndClose: true,
        type: 'info',
      },
    )
  } catch (e: any) {
    if (e === 'close' || e?.toString?.() === 'close') return // 右上角关闭 = 取消
    mode = 'overwrite'
  }

  h0Pulling.value = true
  try {
    const entityRows = await fetchH0EntityVerifyRows()
    if (!entityRows.length) {
      ElMessage.warning('H0-2 尚无核实记录，或该底稿未编制')
      return
    }
    const result = pullH0SummaryFromEntityVerify({
      summaryRows: data.rows.value,
      entityRows,
      mode,
    })
    if (result.matched > 0) {
      // 持久化：与本组件其它写入路径同源（buildPayload + emit save）
      emit('save', data.buildPayload())
    }
    const msg = describeH0PullResult(result)
    if (result.matched > 0) ElMessage.success(msg)
    else ElMessage.info(msg)
  } catch (e: any) {
    ElMessage.error(`带入失败：${e?.message || '未知错误'}`)
  } finally {
    h0Pulling.value = false
  }
}

/**
 * 读 H0-2 的 entity-verify-v1 行（按 wp_code 解析底稿 → 取 html_data）。
 *
 * 🔴 两处踩坑（2026-08-04 浏览器实测暴露，改造前该按钮恒报「未找到底稿 H0-2」）：
 * 1. **端点** —— 平台按 wp_code 解析底稿的唯一入口是
 *    `/api/custom-query/wp-id-by-code?project_id=&wp_code=`（20+ 处在用）；
 *    `/projects/{id}/workpapers/wp-id-by-code` 不存在。
 * 2. **http 客户端** —— 必须用 `@/services/apiProxy` 的 `api`（直接返回业务数据）；
 *    `@/utils/http` 返回 AxiosResponse，`res.wp_id` 恒 undefined。
 *    且 `utils/http` 的 baseURL 是 `/`、vite 只代理 `/api` → 漏前缀会拿回 index.html。
 */
async function fetchH0EntityVerifyRows(): Promise<EntityVerifyRow[]> {
  const meta = getCycleConfirmationMeta(props.wpCode)
  const idRes = await api.get<{ wp_id?: string }>('/api/custom-query/wp-id-by-code', {
    params: { project_id: props.projectId, wp_code: meta.entityVerifyCode },
    _silent: true,
  } as any)
  const wpId = (idRes as any)?.wp_id
  if (!wpId) throw new Error(`未找到底稿 ${meta.entityVerifyCode}`)

  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, { _silent: true } as any)
  const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
  for (const sheet of sheets) {
    const hd = sheet?.html_data ?? sheet?.htmlData
    if (hd && hd._format === 'entity-verify-v1' && Array.isArray(hd.rows)) {
      return hd.rows as EntityVerifyRow[]
    }
  }
  return []
}

function handleH0LowerReview(key: string) {
  eventBus.emit('wp:review-request', {
    wpId: props.wpId,
    wpCode: props.wpCode,
    sectionId: `H0-1-lower-${key}`,
  } as any)
}

// ─── G0（投资循环函证）下区（矩阵 + 审计说明 + 审计结论 + 编制说明） ─────────
// spec: g0-confirmation-source-alignment Task 9（R3.1~R3.5 / R3.7~R3.11）
// 🔴 「二、样本选择」不在这里 —— 由 `ConfirmationSampling`（`:cycle` → isG0 → 6 项）承担。

const isG0 = computed(() => confirmCycle.value === 'G0')
const g0LowerRef = ref<{ applyAiText: (key: string, text: string) => void } | null>(null)
const g0Responses = ref<Record<string, string>>({})
const g0Sources = ref<G0MatrixSources | null>(null)
const g0SourcesLoading = ref(false)
const g0AiLoadingKey = ref<string | null>(null)

/**
 * 拉取下区**已持久化**录入值（审计说明 5 段 / 结论 / 矩阵手工覆盖 / 自定义品种）。
 *
 * 🔴 必须走 `/checklist-responses`（持久化），**不能**用 `html_data.responses_snapshot` ——
 * 后者含 Tier A 公式预设（`TB('1504')` 等）的 transient 种子，一旦被
 * `parseG0ManualOverrides` 当成手工覆盖，那 5 个在客户科目表根本不存在的品种就会把
 * 「本项目无此科目」压成假 0（`Number(null) === 0` 同族坑）。
 * 三级优先级 = 手工编辑值 > 语义定位值(tb_amount) > prefill 种子。
 */
async function loadG0Responses() {
  if (!isG0.value || !props.wpId) return
  try {
    // 🔴 必须带 `/api` 前缀 —— `utils/http` 的 baseURL 是 `/`，且 vite 只代理 `/api`；
    //    漏掉会打到 dev server 拿回 index.html（200 + HTML），`Array.isArray` 判否后
    //    静默变成空 map（既有 `loadH0Responses` 就漏了 `/api`，已在报告中登记）。
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = (res.data?.data ?? res.data ?? []) as Array<Record<string, any>>
    const map: Record<string, string> = {}
    for (const item of Array.isArray(list) ? list : []) {
      const id = String(item.item_id ?? item.itemId ?? '')
      if (!id.startsWith('G0-1-')) continue
      const v = item.remark ?? item.conclusion ?? item.value ?? ''
      map[id] = v === null || v === undefined ? '' : String(v)
    }
    g0Responses.value = map
  } catch (e: any) {
    console.warn('[GtConfirmationSummary] G0 下区录入值加载失败:', e?.message)
  }
}

/** 并行拉 G1/G4/G5/G6/G7/G8/G9/G10 的 `project_context.tb_amount` 作矩阵账面金额 */
async function loadG0Sources() {
  if (!isG0.value) return
  g0SourcesLoading.value = true
  try {
    g0Sources.value = await loadG0MatrixSources(props.projectId)
  } finally {
    g0SourcesLoading.value = false
  }
}

/** 下区录入落库（单条，交由宿主 save 处理器写 checklist_responses） */
function handleG0LowerSave(itemId: string, value: string) {
  g0Responses.value = { ...g0Responses.value, [itemId]: value }
  emit('save', { itemId, value })
}

/** 下区审计说明/结论的 AI 辅助（通用端点 /ai/generate-text，context 值必须全为字符串） */
async function handleG0LowerAi(aiSection: string, key: string) {
  if (!props.wpId) {
    ElMessage.warning('缺少底稿标识，无法调用 AI')
    return
  }
  g0AiLoadingKey.value = key
  try {
    const noteDef = G0_AUDIT_NOTE_DEFS.find((d) => d.key === key)
    const itemId = noteDef
      ? `${G0_LOWER_KEY_PREFIX}audit-note-${noteDef.seq}`
      : `${G0_LOWER_KEY_PREFIX}conclusion`
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: aiSection,
      prompt: noteDef
        ? `请按源模板口径撰写 G0-1 投资循环函证结果汇总表「${noteDef.title}」的内容，只使用下方上下文中的事实，无数据处写「[待补充]」，不得虚构金额或结论。`
        : '请按源模板口径撰写 G0-1 投资循环函证的审计结论，只使用下方上下文中的事实，无数据处写「[待补充]」，不得虚构金额或结论。',
      existingContent: g0Responses.value[itemId] ?? '',
      context: {
        底稿编码: String(props.wpCode || 'G0-1'),
        函证行数: String(data.rows.value.length),
        已回函行数: String(
          data.rows.value.filter((r: ConfirmationRow) => r.is_replied === '是' || r.is_replied === true).length,
        ),
        不符行数: String(data.rows.value.filter((r: ConfirmationRow) => r.match_status === '不符').length),
        账面金额已取数品种: (g0Sources.value?.diagnostics.bookResolved ?? []).join('、') || '无',
      },
    })
    const content = String((res.data?.data ?? res.data)?.content ?? '')
    if (!content) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    g0LowerRef.value?.applyAiText(key, content)
    ElMessage.success('AI 已生成，请复核后保存')
  } catch (e: any) {
    ElMessage.error(`AI 生成失败：${e?.message || '未知错误'}`)
  } finally {
    g0AiLoadingKey.value = null
  }
}

// F0 矩阵数据源（账面金额 ← F1/F3/F4 tb_amount；替代确认 ← F0-5/F0-6 companies）
const f0Sources = ref<F0MatrixSources | null>(null)
const f0SourcesLoading = ref(false)

/** 手工覆盖（仅「本期（期末）账面金额」行可填），持久化到 F0-1-matrix-{品种}-{指标} */
const f0ManualOverrides = ref<Record<string, number>>({})

async function loadF0Sources() {
  if (!isF0.value) return
  f0SourcesLoading.value = true
  try {
    f0Sources.value = await loadF0MatrixSources(props.projectId, props.wpId)
  } finally {
    f0SourcesLoading.value = false
  }
}

onMounted(() => {
  if (isH0.value) void loadH0Responses()
  if (isF0.value) void loadF0Sources()
  if (isG0.value) {
    void loadG0Responses()
    void loadG0Sources()
  }
})

// F0 矩阵：从 grid rows + 四表账面额 + 替代程序合计实时聚合 4品种 × 8指标
const f0Matrix = computed<F0MatrixCell[][] | null>(() => {
  if (!isF0.value) return null
  return buildF0SummaryMatrix({
    rows: data.rows.value,
    bookAmounts: f0Sources.value?.bookAmounts,
    manualOverrides: f0ManualOverrides.value,
  })
})

/**
 * F0 替代确认金额勾稽：上区 Y 列合计 ?= F0-5 + F0-6 凭证金额合计。
 *
 * 矩阵 R36 一律按源模板 SUMIF(E,品种,Y) 取上区 Y 列；F0-5/F0-6 底稿合计只用来
 * 提示「Y 列漏填 / 替代程序底稿漏编」，绝不反推品种归属（Task 28 已删该编造逻辑）。
 */
const f0AltCheck = computed<F0AltConsistency | null>(() => {
  if (!isF0.value) return null
  return checkAltConsistency({
    rows: data.rows.value,
    altF05Totals: f0Sources.value?.altF05Totals,
    altF06Totals: f0Sources.value?.altF06Totals,
  })
})

/** R37「回函和替代确认金额占账面金额的比例」双算风险行（U 与 Y 相等的未回函行） */
const f0AltOverlapCount = computed(() => {
  if (!isF0.value) return 0
  return detectAltOverlapRows(data.rows.value).length
})

/** 写入手工覆盖并持久化（空值 = 撤销覆盖，回落自动取数值） */
function handleF0MatrixOverride(category: F0Category, metric: F0Metric, raw: unknown) {
  const key = `${category}::${metric}`
  const num = Number(raw)
  const itemId = matrixOverrideItemId(category, metric)

  if (raw === '' || raw == null || !Number.isFinite(num)) {
    delete f0ManualOverrides.value[key]
    emit('save', { itemId, value: '' })
    return
  }
  f0ManualOverrides.value = { ...f0ManualOverrides.value, [key]: num }
  emit('save', { itemId, value: String(num) })
}

/** 溯源提示：账面金额取数状态 */
const f0SourceHint = computed(() => {
  const d = f0Sources.value?.diagnostics
  if (!d) return ''
  const parts: string[] = []
  if (d.bookResolved.length) parts.push(`账面金额已取数：${d.bookResolved.join('、')}`)
  if (d.bookMissing.length) parts.push(`待手工填写：${d.bookMissing.join('、')}`)
  if (d.altF05Found || d.altF06Found) {
    const found = [d.altF05Found ? 'F0-5' : '', d.altF06Found ? 'F0-6' : ''].filter(Boolean)
    parts.push(`替代程序已带入：${found.join('、')}`)
  }
  return parts.join('　|　')
})

/**
 * 取数错误提示。
 *
 * 🔴 `loadF0MatrixSources` 全程 `_silent: true`（不弹 ElMessage 打断用户），
 * 错误都收进 `diagnostics.errors`。上一版**只渲染 bookResolved/bookMissing 从不渲染 errors**
 * → 取数整条链路失效时界面只显示「待手工填写」，与「本项目确实没这科目」不可区分，
 * 排查时也看不到线索（2026-08-03 实测正是这样掩盖了 http/apiProxy 形态错用）。
 */
const f0SourceErrors = computed(() => f0Sources.value?.diagnostics.errors ?? [])

// F0 矩阵转为 el-table 行数据（按指标行 × 品种列）
const f0MatrixTableData = computed(() => {
  if (!f0Matrix.value) return []
  return F0_MATRIX_LABELS.map((label, metricIdx) => {
    const firstCell = f0Matrix.value![0][metricIdx]
    const row: Record<string, unknown> = {
      label,
      kind: firstCell.kind,
      editable: firstCell.editable,
    }
    for (let catIdx = 0; catIdx < F0_MATRIX_CATEGORIES.length; catIdx++) {
      const cell = f0Matrix.value![catIdx][metricIdx]
      row[F0_MATRIX_CATEGORIES[catIdx]] = cell.value
    }
    return row
  })
})

/** F0 矩阵金额格式化 */
function fmtMatrixAmount(v: number | null): string {
  if (v === null || v === undefined) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}



// ─── 数据核心 ────────────────────────────────────────────────────────────────

// 科目审定总额(TB population)：后端 render 注入 project_context.population_amount（前端只读）
// 作为函证/确认覆盖率分母；缺失时覆盖率显示为「不可用」(Skip-on-missing)
const populationAmount = computed<number | null>(() => {
  const p = props.htmlData?.project_context?.population_amount
  return typeof p === 'number' && p > 0 ? p : null
})

const data = useConfirmationData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
  population: () => populationAmount.value,
})

const viewMode = useViewMode()

// P1-1: 保存后自动同步到函证中心台账（防抖/非阻塞/失败静默/只读gate）
const autoSync = useDisclosureAutoSync({
  isReadonly: () => props.readonly,
  debounceMs: 2000,
})

// 同步状态可见（Task 4.2 / Property 20）：已同步=已回写 hubId 的行；
// 待同步=已进入函证程序（已发函/已回函）但尚未持久化 hubId 的行。数据源为行上持久化的 _hub_confirmation_id。
const syncStatusSummary = computed(() => {
  const inFlight = data.rows.value.filter((r) => r.entity_name?.trim() && isConfirmationInFlight(r))
  const synced = inFlight.filter((r) => !!r._hub_confirmation_id).length
  return { total: inFlight.length, synced, unsynced: inFlight.length - synced }
})

// ─── UI 状态 ──────────────────────────────────────────────────────────────────

const selectedIds = ref<string[]>([])
const currentRow = ref<ConfirmationRow | null>(null)
const contextMenu = ref({ visible: false, x: 0, y: 0 })
// 同步到函证中心（P0-2：编制真源 confirmation-v1 → 后端 Confirmation 台账/工作包摘要真源）
const syncing = ref(false)
// 用户是否已操作过（新增/删除），用于区分首次空态 vs 删光后空态
const hasInteracted = ref(false)

// #3: 订阅 Hub 状态变更→反向刷新编制真源行（Hub 手动推进后同步回来）
function _onConfirmationReceived(payload: { confirmationId?: string; accountCode?: string }) {
  // Hub 推进到终态后触发——同会话即时刷新（加速）；持久化以 _backflowFromHub 为准。
  if (!payload?.confirmationId) return
  const row = data.rows.value.find(r => r._hub_confirmation_id === payload.confirmationId)
  if (row) {
    // 已有 hubId 映射的行：标记 is_replied（终态必定已回函）
    const patch = hubStatusToRowPatch('returned')
    Object.assign(row, patch)
  }
  // 触发一次持久化拉取（拿到回函金额/终态，手工优先）
  _backflowFromHub(true)
}

/**
 * Reply_Backflow（R4.1/R4.5）：从后端台账拉取回函结果刷新本表行，不依赖同会话事件。
 * - 匹配优先级：行的 _hub_confirmation_id > 对方名称（counterparty）
 * - 手工优先（P8）：行已有审计师手工回函金额（reply_amount）时不覆盖，仅补状态标记
 * - 持久化读取（P9）：跨会话打开也能读到台账最新回函
 */
let _backflowRan = false
async function _backflowFromHub(force = false) {
  if (!props.projectId) return
  if (_backflowRan && !force) { /* onMounted 只跑一次；事件驱动 force=true */ }
  try {
    const res = await http.get<any>(
      `/api/projects/${props.projectId}/confirmations`,
      { _silent: true } as any,
    )
    const items: any[] = res?.items ?? res?.data?.items ?? []
    if (!items.length) return
    // 建索引：按 id 与按对方名称
    const byId = new Map<string, any>()
    const byName = new Map<string, any>()
    for (const it of items) {
      if (it.id) byId.set(String(it.id), it)
      const name = String(it.counterparty || '').trim()
      if (name && !byName.has(name)) byName.set(name, it)
    }
    let anyPatched = false
    for (const row of data.rows.value) {
      const hit = (row._hub_confirmation_id && byId.get(row._hub_confirmation_id))
        || byName.get(String(row.entity_name || '').trim())
      if (!hit) continue
      const status = String(hit.status || '')
      if (!['returned', 'matched', 'discrepancy'].includes(status)) continue
      // 手工优先：行已有回函金额（审计师手填）则不覆盖金额，仅补状态标记
      const hasManualReply = row.reply_amount != null && row.reply_amount !== '' && Number(row.reply_amount) !== 0
      const patch = hubStatusToRowPatch(
        status,
        hasManualReply ? undefined : {
          confirmed_amount: hit.confirmed_amount,
          diff_amount: hit.diff_amount,
        },
      )
      // 首次回填 hubId 映射（供后续幂等 + 状态显示）
      if (!row._hub_confirmation_id && hit.id) row._hub_confirmation_id = String(hit.id)
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined) continue
        if ((row as any)[k] !== v) { (row as any)[k] = v; anyPatched = true }
      }
    }
    if (anyPatched) {
      // 持久化刷新结果（不触发二次同步，供跨会话可读 P9）
      emit('save', data.buildPayload())
    }
  } catch {
    // 台账不可读时静默（不打扰用户）
  } finally {
    _backflowRan = true
  }
}
onMounted(() => {
  eventBus.on('confirmation:received', _onConfirmationReceived)
  // 打开时按持久化台账刷新回函结果（不依赖同会话事件）
  if (data.rows.value.length > 0) _backflowFromHub()
})
onUnmounted(() => {
  eventBus.off('confirmation:received', _onConfirmationReceived)
})

// 清除待触发的自动同步定时器
onBeforeUnmount(() => {
  autoSync.cancelPending()
})

// 公式管理弹窗
const showFormulaDialog = ref(false)
const formulaRules = [
  { field: '可确认金额', formula: '相符→函证金额；不符→回函金额；消极式未回函→函证金额；积极式未回函→替代确认金额', source: '自动计算' },
  { field: '差异金额', formula: '= 函证金额 - 回函金额（相符时强制为0）', source: '自动计算' },
  { field: '确认覆盖率', formula: '= (回函确认 + 替代确认) / 函证发出总额 × 100%', source: '看板汇总' },
  { field: '回函率', formula: '= 已回函笔数 / 已发函笔数 × 100%', source: '看板汇总' },
  { field: '函证覆盖率（科目总体）', formula: '= 函证发出总额 / 科目审定总额 × 100%（需接入试算表审定总额，暂未计算）', source: '待接入 TB' },
]
// Task 4: CrossRef 规则改按循环动态解析（e0-confirmation-completion R4），不再写死 D0-*
// props.wpCode 是响应式 prop，切换循环时 computed 自动重算
const crossRefRules = computed(() => buildCrossRefRules(props.wpCode))

/** 默认展开：数据充分(≥3条)时展开看板，数据少时折叠（减少视觉干扰） */
const expandedSections = ref<string[]>(data.rows.value.length >= 3 ? ['dashboard'] : [])

/** 为审计说明 AI 预填充提供的统计数据 */
const notesAiStats = computed(() => {
  const rows = data.rows.value
  const totalCount = rows.length
  const totalAmount = rows.reduce((s, r) => s + (r.amount || 0), 0)
  const repliedCount = rows.filter(r => r.is_replied).length
  const matchedCount = rows.filter(r => r.match_status === '相符').length
  const unrepliedCount = totalCount - repliedCount
  const coveragePct = totalAmount > 0
    ? (rows.filter(r => r.is_replied).reduce((s, r) => s + (r.amount || 0), 0) / totalAmount) * 100
    : 0
  const accountTypes = [...new Set(rows.map(r => r.account_type).filter(Boolean))] as string[]
  return { totalCount, totalAmount, repliedCount, matchedCount, unrepliedCount, coveragePct, accountTypes }
})

/** 看板标题：少量数据时提示尚不完整 */
const dashboardTitle = computed(() => {
  const count = data.rows.value.length
  if (count === 0) return '函证情况统计'
  if (count < 3) return `函证情况统计（已录入 ${count} 条，录入更多后指标更有参考价值）`
  return `函证情况统计（${count} 条函证）`
})

/**
 * 枚举取值 —— 单一真源 `CONFIRMATION_DICT_FALLBACK`（coordination/confirmationDicts.ts）。
 *
 * 🔴 改造前这里是 4 行内置字面量数组，且**与后端 system_dicts 不一致**：
 * `confirmation_account_type` 只有 7 项（后端 22 项）→ H 循环品种
 * （固定资产/工程物资/使用权资产/租赁负债…）一个都选不出来 → H0-1 下区矩阵
 * 按「账户/交易」列 SUMIF 分品种，品种名选不出即恒空。
 * spec: h0-confirmation-source-fidelity-and-linkage R1.1/R1.3
 *
 * 「函证方式」列绑 SEND_CHANNEL（发函渠道，源模板 X0-2!C7）而非 METHOD（积极式/消极式）——
 * 源模板 X0-1!G 列由 VLOOKUP 自 X0-2!C 列带入，两处必须同枚举。
 */
const dictData = ref<Record<string, any[]>>({
  [CONFIRMATION_DICTS.ACCOUNT_TYPE]: [...fallbackOptions(CONFIRMATION_DICTS.ACCOUNT_TYPE)],
  [CONFIRMATION_DICTS.METHOD]: [...fallbackOptions(CONFIRMATION_DICTS.METHOD)],
  [CONFIRMATION_DICTS.SEND_CHANNEL]: [...fallbackOptions(CONFIRMATION_DICTS.SEND_CHANNEL)],
  [CONFIRMATION_DICTS.SAMPLE_PURPOSE]: [...fallbackOptions(CONFIRMATION_DICTS.SAMPLE_PURPOSE)],
  [CONFIRMATION_DICTS.REPLY_METHOD]: [...fallbackOptions(CONFIRMATION_DICTS.REPLY_METHOD)],
  [CONFIRMATION_DICTS.MATCH_STATUS]: [...fallbackOptions(CONFIRMATION_DICTS.MATCH_STATUS)],
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

const importFileInput = ref<HTMLInputElement | null>(null)

function handleAdd() {
  hasInteracted.value = true
  try {
    data.addRow()
    markDirty()
  } catch (e: any) {
    console.warn('[GtConfirmationSummary] handleAdd error:', e?.message)
  }
}

function handleImportClick() {
  importFileInput.value?.click()
}

async function handleDownloadImportTemplate() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 数据模板（固定列头，用户在此填写）
    const headers = ['序号', '索引号', '被询证单位', '地址', '联系人', '联系电话', '科目', '函证金额', '币种', '函证方式', '发函日期']
    const exampleRow = [1, 'D0-001', '示例公司（请删除此行）', '北京市XX区XX路XX号', '张三', '010-12345678', '应收账款', 100000, 'CNY', '积极式', '2025-12-31']
    const dataSheet = utils.aoa_to_sheet([headers, exampleRow])
    // 设置列宽
    dataSheet['!cols'] = [
      { wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 30 }, { wch: 10 }, { wch: 14 },
      { wch: 12 }, { wch: 14 }, { wch: 6 }, { wch: 10 }, { wch: 12 },
    ]
    utils.book_append_sheet(wb, dataSheet, '函证清单')

    // Sheet 2: 填写说明
    const instructions = [
      ['函证清单导入模板 - 填写说明'],
      [''],
      ['【必填列】'],
      ['  被询证单位：函证对象公司全称（必填）'],
      ['  科目：函证涉及的会计科目（如：应收账款、应付账款、银行存款、合同负债）'],
      ['  函证金额：账面金额（数字，单位：元）'],
      [''],
      ['【选填列】'],
      ['  序号：自动递增编号（留空则自动生成）'],
      ['  索引号：函证编号（如 D0-001），留空则自动生成'],
      ['  地址：邮寄发函地址'],
      ['  联系人：被询证单位联系人姓名'],
      ['  联系电话：被询证单位联系电话'],
      ['  币种：默认 CNY，外币函证填写对应币种'],
      ['  函证方式：积极式 / 消极式（默认积极式）'],
      ['  发函日期：格式 YYYY-MM-DD'],
      [''],
      ['【注意事项】'],
      ['  1. 请在「函证清单」sheet 中填写数据，本说明 sheet 无需修改'],
      ['  2. 第一行为表头，请勿修改列名（系统按列名识别）'],
      ['  3. 示例行（第2行）请删除后再填写实际数据'],
      ['  4. 金额列请填纯数字，不要带"元"或千分位逗号'],
      ['  5. 填写完成后保存，回到系统点击「↑导入」上传此文件'],
      ['  6. 导入后可在系统中继续补充回函结果和相符情况'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 70 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, '函证清单导入模板.xlsx')
  } catch (e: any) {
    ElMessage.error('生成模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
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
    // 列名映射（支持多种常见写法，与导入模板列头对齐）
    const colMap: Record<string, string[]> = {
      entity_name: ['被询证单位', '单位名称', '被函证单位', '客户名称', '对方单位'],
      account_type: ['科目', '科目类型', '账户类型', '函证科目'],
      amount: ['函证金额', '金额', '账面金额', '余额', '发函金额'],
      confirmation_method: ['函证方式', '方式', '发函方式'],
      entity_address: ['地址', '邮寄地址', '联系地址'],
      contact_person: ['联系人', '联系人姓名'],
      contact_phone: ['联系电话', '电话', '手机'],
      currency: ['币种', '货币'],
      send_date: ['发函日期', '寄出日期'],
      confirm_index: ['索引号', '函证索引号', '编号'],
    }
    let importCount = 0
    for (const raw of rawRows) {
      // 跳过完全空行
      const hasValue = Object.values(raw).some(v => v != null && String(v).trim() !== '')
      if (!hasValue) continue
      const row = data.addRow()
      for (const [field, aliases] of Object.entries(colMap)) {
        for (const alias of aliases) {
          if (raw[alias] != null && String(raw[alias]).trim() !== '') {
            const val = field === 'amount' ? (parseFloat(String(raw[alias])) || null) : String(raw[alias]).trim()
            ;(row as any)[field] = val
            break
          }
        }
      }
      importCount++
    }
    if (importCount > 0) {
      ElMessage.success(`成功导入 ${importCount} 条函证记录`)
    } else {
      ElMessage.warning('未识别到有效数据行，请检查 Excel 列头是否包含：被询证单位、科目、函证金额')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '文件格式错误'))
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

function handleDelete() {
  hasInteracted.value = true
  data.deleteRows(selectedIds.value)
  selectedIds.value = []
  markDirty()
}

/**
 * 同步到函证中心：把本汇总表「已进入函证程序」的行 upsert 到后端 Confirmation 台账，
 * 并按状态机推进（终态触发 CONFIRMATION_RECEIVED → 下游 D2/F2/G7… stale）。
 * 这是 confirmation-v1 编制真源 → 后端摘要真源的桥（此前 syncHubFromSummary 为死代码未接线）。
 */
async function handleSyncHub() {
  if (!props.projectId) { ElMessage.warning('缺少项目上下文，无法同步'); return }
  syncing.value = true
  try {
    const cycleCode = (props.wpCode || '').split('-')[0] || undefined
    const res = await syncHubFromSummary({
      projectId: props.projectId,
      wpId: props.wpId,
      sourceWpCode: props.wpCode,
      wpCode: cycleCode,
      year: props.year ? Number(props.year) : undefined,
      rows: data.rows.value,
    })
    const summary = `新增 ${res.created} · 更新 ${res.updated} · 状态推进 ${res.transitioned}`
    if (res.errors.length) {
      ElMessage.warning(`同步完成（部分失败）：${summary}；${res.errors[0]}`)
    } else if (res.created + res.updated + res.transitioned === 0) {
      ElMessage.info('暂无「已发函/已回函」的行需要同步')
    } else {
      ElMessage.success(`已同步到函证中心：${summary}`)
    }
  } catch (e: any) {
    ElMessage.error('同步失败：' + (e?.message || '未知错误'))
  } finally {
    syncing.value = false
  }
}

/**
 * E0 清单 → E0-1 带入（Task 3.3 / Property 14）：
 * 从 E0-3~E0-6 发函清单筛「是否函证=是」的账户，按品种置 account_type，去重后建行。
 * 复用既有 addRow + updateField 写入路径（不新造 confirmation-v1 写入实现）。
 */
async function handleImportE0Lists() {
  if (!props.projectId) { ElMessage.warning('缺少项目上下文，无法带入'); return }
  importingLists.value = true
  try {
    const res = await importE0ListsToSummary(props.projectId, data.rows.value)
    if (!res.ok) {
      ElMessage.warning('从发函清单带入失败：' + (res.message || '未知错误'))
      return
    }
    if (res.candidates.length === 0) {
      ElMessage.info(res.emptyReason || '无可带入项目')
      return
    }
    hasInteracted.value = true
    for (const c of res.candidates) {
      const row = data.addRow()
      if (c.entity_name) data.updateField(row._row_id!, 'entity_name', c.entity_name)
      if (c.confirm_index) data.updateField(row._row_id!, 'confirm_index', c.confirm_index)
      if (c.account_type) data.updateField(row._row_id!, 'account_type', c.account_type)
      // 账号/理财产品名称：源模板 E0-1 E 列，是 F 列 SUMIF 的匹配键，必须带过来
      if (c.account_no) data.updateField(row._row_id!, 'account_no', c.account_no)
      if (c.currency) data.updateField(row._row_id!, 'currency', c.currency)
      if (c.amount != null) data.updateField(row._row_id!, 'amount', c.amount)
      ;(row as any)._source = 'auto'
    }
    handleSave()
    ElMessage.success(`已从发函记录表带入 ${res.candidates.length} 条`)
    // 品种靠兜底值推出（源模板「所属科目」「借款类型」两列都缺）→ 明示提示，不静默归类
    if (res.typeFallbackLists?.length) {
      ElMessage.warning(
        `${res.typeFallbackLists.join('、')} 缺「所属科目」列，品种已按默认值填入，请复核（长期借款需手工改正）`,
      )
    }
  } catch (e: any) {
    ElMessage.warning('从发函清单带入失败：' + (e?.message || '未知错误'))
  } finally {
    importingLists.value = false
  }
}

/**
 * #1+#2+#4: 保存后自动同步 Hub（批量端点，单次 HTTP 替代 N+1）。
 * 使用 useDisclosureAutoSync 统一封装：防抖 2s/非阻塞/失败静默/只读gate。
 * 同步成功后 hubId 写回 row._hub_confirmation_id → re-save 持久化映射。
 */
function _triggerAutoSyncHub() {
  if (!props.projectId) return
  autoSync.scheduleAutoSync(async () => {
    if (syncing.value) return // 正在手动同步，跳过
    const candidates = data.rows.value.filter(
      (r) => r.entity_name?.trim() && isConfirmationInFlight(r),
    )
    if (!candidates.length) return

    const cycleCode = (props.wpCode || '').split('-')[0] || undefined
    const items = candidates.map((r) => ({
      confirm_type: accountTypeToHubType(r.account_type),
      counterparty: (r.entity_name || '').trim(),
      wp_id: props.wpId || undefined,
      account_code: r.confirm_index || undefined,
      book_amount: Number(r.amount) || null,
      confirmed_amount: Number(r.reply_amount) || null,
      diff_amount: r.difference != null ? Number(r.difference) : null,
      diff_note: r.remark || undefined,
      target_status: rowToHubStatus(r),
      hub_confirmation_id: r._hub_confirmation_id || undefined,
    }))

    const res = await http.post<any>(
      `/api/projects/${props.projectId}/confirmations/batch-sync`,
      {
        items,
        wp_id: props.wpId,
        wp_code: cycleCode,
        year: props.year ? Number(props.year) : undefined,
      },
      { _silent: true } as any,
    )
    // #2: 写回 hubId 到各行
    const hubIds: Record<string, string> = res?.hub_ids || {}
    let anyMapped = false
    for (const row of candidates) {
      const name = (row.entity_name || '').trim()
      if (hubIds[name] && row._hub_confirmation_id !== hubIds[name]) {
        row._hub_confirmation_id = hubIds[name]
        anyMapped = true
      }
    }
    // re-save 持久化 hubId 映射（不触发二次同步）
    if (anyMapped) {
      const payload = data.buildPayload()
      emit('save', payload)
    }
  })
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
  // 通知兄弟函证 sheet 刷新（confirmation:updated EventBus 联动）
  if (props.projectId && props.wpCode) {
    eventBus.emit('confirmation:updated', {
      projectId: props.projectId,
      wpCode: props.wpCode,
      wpId: props.wpId,
      timestamp: Date.now(),
    })
  }
  // #6: 批量回写科目明细 isConfirmed='Y'（此前为死代码，现接线）
  emitConfirmationCompletedFromSummary({
    projectId: props.projectId,
    sourceWpCode: props.wpCode,
    rows: data.rows.value,
  })
  // #1+#2: 保存后自动同步到函证中心（非阻塞，hubId 回写后自动 re-save 持久化）
  if (props.projectId) {
    _triggerAutoSyncHub()
  }
}

function handleRowClick(row: ConfirmationRow) {
  currentRow.value = row
}

function handleFieldUpdate(field: string, value: any) {
  if (!currentRow.value?._row_id) return
  data.updateField(currentRow.value._row_id, field, value)
  markDirty()
}

function handleGridUpdate(rowId: string, field: string, value: any) {
  data.updateField(rowId, field, value)
  markDirty()
}

function handleSamplingUpdate(field: string, value: any) {
  ;(data.sampling.value as any)[field] = value
}

function handleNotesUpdate(field: string, value: any) {
  ;(data.notes.value as any)[field] = value
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
}

function handleContextAction(action: string) {
  // Context menu actions - to be wired with row context
  console.log('[GtConfirmationSummary] context action:', action)
}

// 暴露给父组件通过 ref 调用（页面级工具栏转发）
defineExpose({
  handleDownloadImportTemplate,
  handleImportClick,
  handleExportData: handleSave, // 导出数据 = 保存当前数据
})
</script>

<style scoped>
.gt-confirmation-summary {
  padding: 8px 0;
}

.gt-confirmation-summary__legacy-notice {
  margin-bottom: 12px;
}

/* Onboarding card - 空态首屏引导 */
.gt-confirmation-summary__onboarding {
  display: flex;
  justify-content: center;
  padding: 40px 20px;
}
.gt-confirmation-summary__onboarding-card {
  max-width: 480px;
  text-align: center;
  padding: 32px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fafafa;
}
.gt-confirmation-summary__onboarding-icon {
  font-size: 40px;
  margin-bottom: 12px;
}
.gt-confirmation-summary__onboarding-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 20px;
}
.gt-confirmation-summary__onboarding-steps {
  text-align: left;
  margin-bottom: 24px;
}
.gt-confirmation-summary__step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  font-size: 14px;
  color: #606266;
  line-height: 1.5;
}
.gt-confirmation-summary__step-no {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #7b61ff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-confirmation-summary__onboarding-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}

/* 有数据时的工具栏 */
.gt-confirmation-summary__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-confirmation-summary__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-confirmation-summary__view-switch {
  display: flex;
  justify-content: flex-end;
  margin: 8px 0;
}
</style>
