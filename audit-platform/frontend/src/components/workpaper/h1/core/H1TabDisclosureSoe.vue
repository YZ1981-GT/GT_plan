<template>
  <div class="h1-tab-disclosure-soe">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确认国企固定资产附注（汇总账面价值、原值/折旧/净值/减值/账面价值五层变动、闲置、未办妥产权证书、固定资产清理）完整准确，与 H1-1/H1-2/H1-4/H1-16/H6 勾稽，并同步至附注「八、22」。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :loading="isSyncing" :disabled="isReadonly || !projectId" @click="syncToNotes">
          同步到附注
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注（八、22）</el-button>
        <el-button size="small" :disabled="isReadonly" :loading="isPulling" @click="pullFromSheets">
          从底稿取数
        </el-button>
        <el-button size="small" type="success" plain :disabled="isReadonly || !projectId" :loading="isPullingH6" @click="pullH6Clearing">
          从 H6 同步清理
        </el-button>
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-json">导出 JSON 数据包</el-dropdown-item>
              <el-dropdown-item command="import-json" :disabled="isReadonly">导入 JSON 数据包</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="jsonInputRef" type="file" accept=".json,application/json" style="display:none" @change="onJsonSelected" />
        <span class="chip-wrap">
          <GtIndexChip :value="noteChip" :context-project-id="projectId" />
        </span>
        <el-tag size="small" type="warning">Note:{{ noteSectionId }} 固定资产</el-tag>
        <el-tag v-if="h6Hint" size="small" :type="h6Hint.type">{{ h6Hint.text }}</el-tag>
      </div>
      <div class="toolbar-hint">源模板 78 行 · 清理余额跨底稿取自 H6（1606）</div>
    </div>

    <!-- 披露内部勾稽 -->
    <H1DisclosureConsistencyPanel
      :result="consistency"
      :project-id="projectId"
      :default-expanded="consistency.errorCount > 0"
    />

    <!-- A 汇总 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>15、固定资产（汇总）</span>
          <el-button size="small" type="default" link @click="handleReview('disc-soe-summary')">💬</el-button>
        </div>
      </template>
      <el-table :data="summaryRows" border stripe size="small">
        <el-table-column prop="label" label="项  目" min-width="140">
          <template #default="{ row }">
            <strong v-if="row.isTotal">{{ row.label }}</strong>
            <span v-else>{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末账面价值" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.clearingEditable && !isReadonly"
              v-model="state.summary.clearingEnd"
              :controls="false"
              size="small"
              @change="persistAll"
            />
            <span v-else :class="row.isTotal ? 'formula-cell' : 'amount-cell auto-fill'">{{ fmtAmt(row.endCarrying) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初账面价值" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.clearingEditable && !isReadonly"
              v-model="state.summary.clearingBegin"
              :controls="false"
              size="small"
              @change="persistAll"
            />
            <span v-else :class="row.isTotal ? 'formula-cell' : 'amount-cell auto-fill'">{{ fmtAmt(row.beginCarrying) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="auto-fill-hint">
        固定资产行 = 五、账面价值合计；清理行优先「从 H6 同步清理」写入（H6-1 审定期末/期初），也可手工改。
      </div>
    </el-card>

    <!-- B 五层变动 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>(1) 固定资产情况</span>
          <el-button size="small" type="default" link @click="handleReview('disc-soe-movement')">💬</el-button>
        </div>
      </template>
      <el-table :data="flatMoveRows" border stripe size="small" :row-class-name="moveRowClass">
        <el-table-column prop="label" label="项  目" min-width="200">
          <template #default="{ row }">
            <span :class="{ 'indent-label': row.indent, 'total-label': row.kind === 'total' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <template v-if="isNaCell(row)"><span class="na-cell">—</span></template>
            <el-input-number
              v-else-if="row.editable && !isReadonly"
              :model-value="cellAmt(row, 'begin')"
              :controls="false"
              size="small"
              @update:model-value="(v) => setMoveCell(row, 'begin', v)"
            />
            <span v-else class="amount-cell" :class="{ 'auto-fill': row.kind === 'total' || !row.editable }">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.movementNa || isNaCell(row)" class="na-cell">—</span>
            <el-input-number
              v-else-if="row.editable && !isReadonly"
              :model-value="cellAmt(row, 'increase')"
              :controls="false"
              size="small"
              @update:model-value="(v) => setMoveCell(row, 'increase', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.movementNa || isNaCell(row)" class="na-cell">—</span>
            <el-input-number
              v-else-if="row.editable && !isReadonly"
              :model-value="cellAmt(row, 'decrease')"
              :controls="false"
              size="small"
              @update:model-value="(v) => setMoveCell(row, 'decrease', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <span v-if="isNaCell(row)" class="na-cell">—</span>
            <span v-else class="formula-cell">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="auto-fill-hint">
        净值/账面价值层增减列按模板为「—」；土地资产不计提折旧、不单独计提减值准备（源模板整行「—」）；
        合计与分类由公式勾稽（净值=原值−折旧，账面价值=净值−减值）
      </div>
      <el-alert
        v-if="landNaAnomaly.length"
        type="warning"
        :closable="false"
        show-icon
        class="land-na-alert"
        :title="`土地资产在${landNaAnomaly.join('、')}层带有金额，与源模板「—」列示约定不符：请核对 H1-2 分类是否将土地误并入房屋建筑物，或在此清零。`"
      />
    </el-card>

    <!-- C 闲置 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>② 暂时闲置的固定资产情况</span>
          <el-button size="small" type="default" link @click="handleReview('disc-soe-idle')">💬</el-button>
        </div>
      </template>
      <div class="auto-fill-hint" style="margin-bottom:8px">可从 H1-4 闲置检查表带入；当前登记 {{ idleHint }} 项</div>
      <el-table :data="idleTableRows" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column label="项目" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persistAll" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面原值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" @change="onIdleAmt(row)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计折旧" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accumDep" :controls="false" size="small" @change="onIdleAmt(row)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accumDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false" size="small" @change="onIdleAmt(row)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="120" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.carrying) }}</span></template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persistAll" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="70">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeIdle($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-row">
        合计: 原值 {{ fmtAmt(idleTot.originalCost) }} / 折旧 {{ fmtAmt(idleTot.accumDep) }} /
        减值 {{ fmtAmt(idleTot.impairment) }} / 账面价值 {{ fmtAmt(idleTot.carrying) }}
      </div>
      <div class="dynamic-actions" v-if="!isReadonly">
        <el-button size="small" @click="addIdle">+ 新增行</el-button>
        <el-button size="small" type="primary" plain :disabled="!idleHint" @click="pullIdle">从 H1-4 同步</el-button>
      </div>
    </el-card>

    <!-- D 未办证 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>③ 未办妥产权证书的固定资产情况</span>
          <el-button size="small" type="default" link @click="handleReview('disc-soe-title')">💬</el-button>
        </div>
      </template>
      <div class="auto-fill-hint" style="margin-bottom:8px">可从 H1-16 未办证/在建转固带入；当前候选 {{ titleHint }} 项</div>
      <el-table :data="state.titleRows" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column label="项目" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persistAll" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.carrying" :controls="false" size="small" @change="persistAll" />
            <span v-else class="amount-cell">{{ fmtAmt(row.carrying) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未办妥产权证书原因" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" @change="persistAll" />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="70">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeTitle($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-row">合计: <span class="amount-cell">{{ fmtAmt(titleTotal) }}</span></div>
      <div class="dynamic-actions" v-if="!isReadonly">
        <el-button size="small" @click="addTitle">+ 新增行</el-button>
        <el-button size="small" type="warning" plain :disabled="!titleHint" @click="pullTitle">从 H1-16 同步</el-button>
      </div>
    </el-card>

    <!-- E 清理 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>(2) 固定资产清理</span>
          <el-button size="small" type="default" link @click="handleReview('disc-soe-clearing')">💬</el-button>
        </div>
      </template>
      <el-table :data="state.clearingRows" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column label="项目" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persistAll" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末账面价值" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.endCarrying" :controls="false" size="small" @change="onClearingChange" />
            <span v-else class="amount-cell">{{ fmtAmt(row.endCarrying) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初账面价值" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginCarrying" :controls="false" size="small" @change="onClearingChange" />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginCarrying) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入清理的原因" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" @change="persistAll" />
            <span v-else>{{ row.reason }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="70">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeClearing($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-row">
        合计: 期末 {{ fmtAmt(clearingTot.end) }} / 期初 {{ fmtAmt(clearingTot.begin) }}
      </div>
      <div class="dynamic-actions" v-if="!isReadonly">
        <el-button size="small" @click="addClearing">+ 新增行</el-button>
        <el-button size="small" type="success" plain :loading="isPullingH6" :disabled="!projectId" @click="pullH6Clearing">
          从 H6-2 同步明细
        </el-button>
      </div>
      <div class="note-block">
        <div class="note-label">注：超 1 年清理进展</div>
        <el-input
          v-model="state.clearingNote"
          type="textarea"
          :rows="2"
          :disabled="isReadonly"
          :placeholder="CLEARING_NOTE_PLACEHOLDER"
          @change="persistAll"
        />
      </div>
    </el-card>

    <!-- F 已提足折旧仍在使用 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title">
          <span>⑥ 已提足折旧仍继续使用的固定资产</span>
          <el-button size="small" type="default" link @click="handleReview('disc-soe-fully-dep')">💬</el-button>
        </div>
      </template>
      <div class="auto-fill-hint" style="margin-bottom:8px">
        披露已提足折旧仍继续使用的固定资产账面原值。可「从 H1-2 带入候选」（净值≈残值自动识别），再由审计师确认；仍在使用可能表明原估计年限偏短，需复核折旧政策合理性。
      </div>
      <el-table :data="fullyDepRows" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column label="类别 / 项目" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persistAll" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面原值" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.cost" :controls="false" size="small" @change="persistAll" />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persistAll" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="70">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeFullyDep($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-row">合计: <span class="amount-cell">{{ fmtAmt(fullyDepTot) }}</span></div>
      <div class="dynamic-actions" v-if="!isReadonly">
        <el-button size="small" @click="addFullyDep">+ 新增行</el-button>
        <el-button size="small" type="primary" plain @click="pullFullyDep">从 H1-2 带入候选</el-button>
      </div>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>结构对齐国企源模板：汇总 → (1)五层变动 → 闲置 → 未办证 → (2)清理 → ⑥已提足折旧仍在使用，与上市版子节不同。</li>
        <li>分类含土地资产、酒店业家具等国企常用项；取数优先 H1-2 审定字段。</li>
        <li>「同步到附注」推送至附注模块「{{ noteSectionId }} 固定资产」，子表名与 note_template_soe 一致。</li>
        <li>固定资产清理：跨底稿取 H6-1 审定余额 + H6-2 明细；明细合计与汇总清理行勾稽；超 1 年挂账自动草拟进展说明。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabDisclosureSoe — 附注披露信息（国有企业）
 * 对齐源 xlsx 78 行 + note_template_soe「八、22」，支持跨 sheet 取数与同步附注。
 */
import { reactive, computed, watch, inject, ref, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'
import H1DisclosureConsistencyPanel from './H1DisclosureConsistencyPanel.vue'
import { checkH1SoeConsistency } from '../../composables/h1DisclosureConsistency'
import {
  H1_NOTE_SECTION,
  resolveH1CurrentStandardFromProject,
  resolveH1VariantFromTemplateType,
} from '../../composables/h1NoteSectionMap'
import { buildH1SoeSyncPayload } from '../../composables/h1DisclosureSyncPayload'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import {
  buildSoeDisclosurePack,
  downloadJsonPack,
  parseSoeDisclosurePack,
} from '../../composables/h1DisclosurePack'
import { pullH6ClearingForH1Soe, type H6ClearingPullResult } from '../../composables/h1SoeClearingH6Pull'
import {
  H1_SOE_KEYS,
  readSoeRemark,
  CLEARING_NOTE_PLACEHOLDER,
  buildSummaryRows,
  clearingSubtotal,
  createH1SoeDisclosureState,
  emptyClearingRow,
  emptyIdleRow,
  emptyTitleRow,
  flattenSoeMovement,
  hydrateClearingRows,
  hydrateIdleRows,
  hydrateLayers,
  hydrateSummary,
  hydrateTitleRows,
  idleSubtotal,
  layersHaveAnyAmount,
  mapIdleRowsToSoe,
  mapUncertifiedBuildingsToSoe,
  n,
  recomputeIdleCarrying,
  recomputeSoeLayers,
  seedMovementFromDetailRows,
  titleSubtotal,
  emptyFullyDepRow,
  fullyDepSubtotal,
  deriveSoeFullyDepreciated,
  hydrateFullyDepRows,
  type H1SoeFlatMoveRow,
  type H1SoeIdleRow,
  type H1SoeFullyDepRow,
} from '../../composables/h1SoeDisclosureModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
  /** 项目附注口径（权威变体源，来自 projects.template_type） */
  templateType?: string
  /** 报表范围（standalone|consolidated，来自 projects.report_scope） */
  reportScope?: string
}>()

/** 项目实际附注口径；与本 tab（国企）不一致时禁止同步，避免污染上市体系章节 */
const projectVariant = computed(() => resolveH1VariantFromTemplateType(props.templateType))
const variantMismatch = computed(() => !!projectVariant.value && projectVariant.value !== 'soe')

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId, 'H1', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const noteSectionId = H1_NOTE_SECTION.soe
const noteChip = `Note:${noteSectionId}`
const isSyncing = ref(false)
const isPulling = ref(false)
const isPullingH6 = ref(false)
const jsonInputRef = ref<HTMLInputElement | null>(null)
const lastH6Pull = ref<H6ClearingPullResult | null>(null)
const state = reactive(createH1SoeDisclosureState())
/** ⑥已提足折旧仍在使用（独立于 state，单独持久化 H1-soe-fully-dep-rows） */
const fullyDepRows = ref<H1SoeFullyDepRow[]>([])

/**
 * 披露内部勾稽（五层公式与结转、土地不提折旧/减值、清理汇总↔清理表、②③⑥ 子集约束）
 */
const consistency = computed(() =>
  checkH1SoeConsistency({ state, fullyDep: fullyDepRows.value }),
)

/**
 * 源模板整行「—」的格子是否真的显示「—」。
 * 仅当该行无任何金额时才隐藏——若已从 H1-2 带入金额，照常显示以免静默丢数，
 * 由上方告警 + 勾稽面板提示审计师处理。
 */
function isNaCell(row: H1SoeFlatMoveRow): boolean {
  return !!row.allNa && !row.hasAmount
}

/** 土地资产在折旧/减值层带有金额的层名（与源模板「—」约定不符） */
const landNaAnomaly = computed(() => {
  const names: string[] = []
  for (const layer of ['dep', 'impair'] as const) {
    const block = state.layers.find((l) => l.layer === layer)
    const land = block?.categories.find((c) => c.key === 'land')
    if (land && (n(land.begin) || n(land.increase) || n(land.decrease) || n(land.end))) {
      names.push(layer === 'dep' ? '累计折旧' : '减值准备')
    }
  }
  return names
})

const h6Hint = computed(() => {
  const r = lastH6Pull.value
  if (!r) return null
  if (r.status === 'wp_missing') return { type: 'info' as const, text: '未关联 H6' }
  if (r.status === 'empty') return { type: 'info' as const, text: 'H6 清理余额为 0' }
  if (r.status === 'error') return { type: 'danger' as const, text: 'H6 取数失败' }
  if (!r.transitZero) {
    return { type: 'danger' as const, text: `H6 期末未清零 ${fmtAmt(r.clearingEnd)}` }
  }
  return { type: 'success' as const, text: `H6 已同步 · 明细 ${r.detailCount}` }
})

function parseRemark(itemId: string): unknown {
  const item = props.allResponses.get(itemId)
  if (!item?.remark) return null
  try { return JSON.parse(item.remark) } catch { return item.remark }
}

function parseSoeKey(key: keyof typeof H1_SOE_KEYS): unknown {
  const raw = readSoeRemark((id) => props.allResponses.get(id), key)
  if (raw == null) return null
  try { return JSON.parse(raw) } catch { return raw }
}

function load(): void {
  state.summary = hydrateSummary(parseSoeKey('summary'))
  state.layers = hydrateLayers(parseSoeKey('movement'))
  state.idleRows = hydrateIdleRows(parseSoeKey('idle'))
  state.titleRows = hydrateTitleRows(parseSoeKey('title'))
  state.clearingRows = hydrateClearingRows(parseSoeKey('clearing'))
  const note = readSoeRemark((id) => props.allResponses.get(id), 'clearingNote')
  state.clearingNote = typeof note === 'string' ? note : ''
  fullyDepRows.value = hydrateFullyDepRows(parseSoeKey('fullyDep'))

  // 无已存变动数时，尝试从 H1-2 自动 seed
  if (!layersHaveAnyAmount(state.layers)) {
    const detail = parseRemark('H1-2-rows')
    if (Array.isArray(detail) && detail.length) {
      state.layers = seedMovementFromDetailRows(detail as Record<string, unknown>[])
    }
  }
}

watch(() => props.allResponses, () => load(), { immediate: true, deep: false })

/** 首次进入且清理区为空时，自动跨底稿拉 H6 */
let _autoH6Tried = false
watch(
  () => [props.projectId, state.summary.clearingEnd, state.clearingRows.length] as const,
  async ([pid]) => {
    if (_autoH6Tried || props.isReadonly || !pid) return
    const empty =
      !n(state.summary.clearingEnd)
      && !n(state.summary.clearingBegin)
      && state.clearingRows.length === 0
    if (!empty) {
      _autoH6Tried = true
      return
    }
    _autoH6Tried = true
    await applyH6Pull({ silent: true, overwriteNote: false })
  },
  { immediate: true },
)

function persistAll(): void {
  if (props.isReadonly) return
  saveResponse(H1_SOE_KEYS.summary, { ...state.summary })
  saveResponse(H1_SOE_KEYS.movement, state.layers)
  saveResponse(H1_SOE_KEYS.idle, state.idleRows)
  saveResponse(H1_SOE_KEYS.title, state.titleRows)
  saveResponse(H1_SOE_KEYS.clearing, state.clearingRows)
  saveResponse(H1_SOE_KEYS.clearingNote, state.clearingNote)
  saveResponse(H1_SOE_KEYS.fullyDep, fullyDepRows.value)
  autoSync.scheduleAutoSync(syncToNotes)
}

function handleImportExport(cmd: string) {
  if (cmd === 'export-json') {
    const pack = buildSoeDisclosurePack({
      summary: { ...state.summary },
      movement: state.layers,
      idle: state.idleRows,
      title: state.titleRows,
      clearing: state.clearingRows,
      clearingNote: state.clearingNote,
    })
    downloadJsonPack(`H1_附注国企_${new Date().toISOString().slice(0, 10)}.json`, pack)
    ElMessage.success('已导出 JSON 数据包')
  } else if (cmd === 'import-json') {
    jsonInputRef.value?.click()
  }
}

async function onJsonSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  try {
    await ElMessageBox.confirm(`即将导入「${file.name}」，将覆盖当前国企附注数据。确认？`, '导入确认', {
      type: 'warning',
    })
    const parsed = parseSoeDisclosurePack(JSON.parse(await file.text()))
    if (!parsed.ok) {
      ElMessage.error(parsed.message)
      return
    }
    const pack = parsed.pack
    state.summary = hydrateSummary(pack.summary)
    state.layers = hydrateLayers(pack.movement)
    state.idleRows = hydrateIdleRows(pack.idle)
    state.titleRows = hydrateTitleRows(pack.title)
    state.clearingRows = hydrateClearingRows(pack.clearing)
    state.clearingNote = typeof pack.clearingNote === 'string' ? pack.clearingNote : ''
    persistAll()
    ElMessage.success('已导入国企附注数据包')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '导入失败')
  }
}

const flatMoveRows = computed(() => flattenSoeMovement(state.layers))
const summaryRows = computed(() => buildSummaryRows(state.layers, state.summary))
const idleTableRows = computed(() => state.idleRows)
const idleTot = computed(() => idleSubtotal(state.idleRows))
const titleTotal = computed(() => titleSubtotal(state.titleRows))
const clearingTot = computed(() => clearingSubtotal(state.clearingRows))
const fullyDepTot = computed(() => fullyDepSubtotal(fullyDepRows.value))

const idleHint = computed(() => {
  const raw = parseRemark('H1-4-rows')
  return Array.isArray(raw) ? raw.length : 0
})
const titleHint = computed(() => {
  const raw = parseRemark('H1-16-rows')
  if (!Array.isArray(raw)) return 0
  return mapUncertifiedBuildingsToSoe(raw as Record<string, unknown>[]).length
})

function moveRowClass({ row }: { row: H1SoeFlatMoveRow }) {
  return row.kind === 'total' ? 'row-total' : ''
}

function cellAmt(row: H1SoeFlatMoveRow, field: 'begin' | 'increase' | 'decrease'): number {
  const block = state.layers.find((l) => l.layer === row.layer)
  const cat = block?.categories.find((c) => c.key === row.categoryKey)
  return cat ? n(cat[field]) : 0
}

function setMoveCell(row: H1SoeFlatMoveRow, field: 'begin' | 'increase' | 'decrease', val: number | undefined) {
  const block = state.layers.find((l) => l.layer === row.layer)
  if (!block) return
  const cat = block.categories.find((c) => c.key === row.categoryKey)
  if (!cat) return
  cat[field] = n(val)
  recomputeSoeLayers(state.layers)
  persistAll()
}

function onIdleAmt(row: H1SoeIdleRow) {
  recomputeIdleCarrying(row)
  persistAll()
}

function addIdle() { state.idleRows.push(emptyIdleRow()); persistAll() }
function removeIdle(i: number) { state.idleRows.splice(i, 1); persistAll() }
function addTitle() { state.titleRows.push(emptyTitleRow()); persistAll() }
function removeTitle(i: number) { state.titleRows.splice(i, 1); persistAll() }
function addClearing() { state.clearingRows.push(emptyClearingRow()); persistAll() }
function removeClearing(i: number) { state.clearingRows.splice(i, 1); onClearingChange() }
function addFullyDep() { fullyDepRows.value.push(emptyFullyDepRow()); persistAll() }
function removeFullyDep(i: number) { fullyDepRows.value.splice(i, 1); persistAll() }
function pullFullyDep() {
  const raw = parseRemark('H1-2-rows')
  if (!Array.isArray(raw) || !raw.length) {
    ElMessage.warning('H1-2 暂无明细数据')
    return
  }
  const candidates = deriveSoeFullyDepreciated(raw as Record<string, unknown>[])
  if (!candidates.length) {
    ElMessage.info('未识别到已提足折旧仍在使用的资产（净值均高于残值）')
    return
  }
  fullyDepRows.value = candidates
  persistAll()
  ElMessage.success(`已带入 ${candidates.length} 类候选，请核实账面原值与仍在使用状态`)
}

function onClearingChange() {
  const tot = clearingSubtotal(state.clearingRows)
  // 明细有数时回写汇总清理行，保证勾稽
  if (state.clearingRows.length) {
    state.summary.clearingEnd = tot.end
    state.summary.clearingBegin = tot.begin
  }
  persistAll()
}

function pullIdle() {
  const raw = parseRemark('H1-4-rows')
  if (!Array.isArray(raw) || !raw.length) {
    ElMessage.warning('H1-4 暂无闲置数据')
    return
  }
  state.idleRows = mapIdleRowsToSoe(raw as Record<string, unknown>[])
  persistAll()
  ElMessage.success(`已从 H1-4 同步 ${state.idleRows.length} 项`)
}

function pullTitle() {
  const raw = parseRemark('H1-16-rows')
  if (!Array.isArray(raw) || !raw.length) {
    ElMessage.warning('H1-16 暂无权属数据')
    return
  }
  const mapped = mapUncertifiedBuildingsToSoe(raw as Record<string, unknown>[])
  state.titleRows = mapped
  persistAll()
  ElMessage.success(`已从 H1-16 同步 ${mapped.length} 项未办证资产`)
}

async function applyH6Pull(opts?: { silent?: boolean; overwriteNote?: boolean }): Promise<boolean> {
  if (!props.projectId) return false
  isPullingH6.value = true
  try {
    const result = await pullH6ClearingForH1Soe(props.projectId)
    lastH6Pull.value = result
    if (result.status !== 'ok') {
      if (!opts?.silent) {
        if (result.status === 'wp_missing') ElMessage.warning(result.message)
        else if (result.status === 'empty') ElMessage.info(result.message)
        else ElMessage.warning(result.message || 'H6 取数失败')
      }
      return false
    }
    state.summary.clearingEnd = result.clearingEnd
    state.summary.clearingBegin = result.clearingBegin
    if (result.clearingRows.length) {
      state.clearingRows = result.clearingRows
    }
    if (result.clearingNoteDraft && (opts?.overwriteNote || !state.clearingNote.trim())) {
      state.clearingNote = result.clearingNoteDraft
    }
    persistAll()
    if (!opts?.silent) {
      let msg = result.message
      if (!result.transitZero) msg += '（提示：1606 期末应为 0）'
      if (result.overOneYearCount) msg += `；超1年 ${result.overOneYearCount} 项`
      ElMessage.success(msg)
    }
    return true
  } finally {
    isPullingH6.value = false
  }
}

async function pullH6Clearing() {
  await applyH6Pull({ silent: false, overwriteNote: !state.clearingNote.trim() })
}

async function pullFromSheets() {
  isPulling.value = true
  try {
    const detail = parseRemark('H1-2-rows')
    if (Array.isArray(detail) && detail.length) {
      state.layers = seedMovementFromDetailRows(detail as Record<string, unknown>[])
    }
    const idle = parseRemark('H1-4-rows')
    if (Array.isArray(idle) && idle.length && !state.idleRows.length) {
      state.idleRows = mapIdleRowsToSoe(idle as Record<string, unknown>[])
    }
    const buildings = parseRemark('H1-16-rows')
    if (Array.isArray(buildings) && buildings.length && !state.titleRows.length) {
      state.titleRows = mapUncertifiedBuildingsToSoe(buildings as Record<string, unknown>[])
    }
    persistAll()
    await applyH6Pull({ silent: true, overwriteNote: false })
    ElMessage.success('已从 H1-2/H1-4/H1-16/H6 取数刷新')
  } finally {
    isPulling.value = false
  }
}

function onH6Adjudicated(payload: any) {
  const code = String(payload?.wpCode || payload?.wp_code || payload?.accountCode || '')
  if (code === 'H6' || code === '1606' || String(payload?.account_code) === '1606') {
    void applyH6Pull({ silent: true, overwriteNote: false })
  }
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', onH6Adjudicated)
})
onBeforeUnmount(() => { autoSync.cancelPending() })
onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onH6Adjudicated)
})

async function syncToNotes() {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  if (variantMismatch.value) {
    ElMessage.warning('本项目附注口径为上市公司，请在「附注披露信息（上市公司）」页同步（国企章节与上市章节不可混用）')
    return
  }
  const payload = buildH1SoeSyncPayload(props.wpId, props.applicableStandards, {
    summary: { ...state.summary },
    layers: state.layers,
    idleRows: state.idleRows,
    titleRows: state.titleRows,
    clearingRows: state.clearingRows,
    clearingNote: state.clearingNote,
  }, {
    currentStandard: resolveH1CurrentStandardFromProject('soe', props.templateType, props.reportScope),
  })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注「${noteSectionId} 固定资产」`)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'H1',
      accountCode: '1601',
      projectId: props.projectId,
      section: noteSectionId,
      sectionIds: [noteSectionId],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null || (typeof val === 'number' && Number.isNaN(val))) return '-'
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.toolbar-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.toolbar-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.chip-wrap { display: inline-flex; }
.disclosure-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.auto-fill { color: var(--el-color-primary); }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  font-variant-numeric: tabular-nums;
}
.na-cell { color: var(--el-text-color-placeholder); }
.auto-fill-hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 8px; }
.land-na-alert { margin-top: 8px; }
.dynamic-actions { margin-top: 8px; display: flex; gap: 8px; }
.subtotal-row { margin-top: 8px; font-weight: 500; text-align: right; padding-right: 12px; }
.indent-label { padding-left: 1.5em; }
.total-label { font-weight: 600; }
.note-block { margin-top: 12px; }
.note-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-total) { background: var(--el-fill-color-light); font-weight: 600; }
</style>
