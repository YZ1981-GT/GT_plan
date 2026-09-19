<template>
  <div class="n1-tab-disclosure-listed">
    <!-- ═══ 标题 + 同步/跳转/AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">{{ N1_DISCLOSURE_SHEET_NAME.listed }}</h3>
        <el-tag type="primary" size="small">上市 4 张披露表</el-tag>
      </div>
      <div class="section-header-right">
        <el-button
          size="small"
          type="success"
          class="sync-btn"
          :loading="syncing"
          @click="syncToDisclosureNotes"
        >
          同步到附注（{{ N1_NOTE_SECTION.listed }}）
        </el-button>
        <el-dropdown split-button size="small" type="primary" @click="jumpToNote('listed')">
          ↩ 跳转回附注（{{ N1_NOTE_SECTION.listed }}）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="jumpToNote('listed')">上市版（{{ N1_NOTE_SECTION.listed }}）</el-dropdown-item>
              <el-dropdown-item @click="jumpToNote('soe')">国企版（{{ N1_NOTE_SECTION.soe }}）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger :section-id="`N1-附注上市-${N1_NOTE_SECTION.listed}`" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 方法论上下文（源模板红字 / 括注，不自造） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>递延所得税资产与递延所得税负债（源模板 4 张披露表）：</strong>
        （1）未经抵销的递延所得税资产和递延所得税负债 —— 资产段与负债段分别列示、各段末置小计；
        （2）以抵销后净额列示的递延所得税资产或负债（不适用的删除）；
        （3）未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细；
        （4）未确认递延所得税资产的可抵扣亏损将于以下年度到期。
        负债段数据来源于递延所得税负债底稿（N3）；表（1）资产段按 N1-2 明细「类别」预填，
        N1-2 未覆盖的行回退按四表科目叶子余额带出。
      </div>
      <div class="branch-picker">
        <span class="branch-label">表（2）是否适用：</span>
        <el-radio-group
          v-model="netOffsetChoice"
          size="small"
          :disabled="isReadonly"
          @change="onNetOffsetApplicableChange"
        >
          <el-radio-button value="undecided">未判断</el-radio-button>
          <el-radio-button value="yes">适用（以抵销后净额列示）</el-radio-button>
          <el-radio-button value="no">不适用</el-radio-button>
        </el-radio-group>
        <el-tag v-if="netOffsetChoice === 'no'" type="info" size="small">
          源模板「不适用的删除」——已从附注清除该表
        </el-tag>
      </div>
      <div class="branch-picker source-trace" v-if="tbSourceSummary">
        <span class="branch-label">四表取数来源：</span>
        <span>{{ tbSourceSummary }}</span>
      </div>
    </div>

    <!-- ═══ 披露内部勾稽 ═══ -->
    <N1DisclosureConsistencyPanel
      :results="tables.checks.value"
      :project-id="props.projectId"
      :default-expanded="hasCheckError"
    />

    <!-- ═══（1）未经抵销的递延所得税资产和递延所得税负债 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（1）未经抵销的递延所得税资产和递延所得税负债</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('unoffset')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <N1DisclosureSegmentTable
        label-header="项  目"
        :columns="unoffsetColumns"
        :segments="tables.unoffsetSegments.value"
        :readonly="isReadonly"
        @change-cell="onUnoffsetCell"
        @change-label="onUnoffsetLabel"
        @add-row="tables.addUnoffsetRow"
        @remove-row="onUnoffsetRemove"
      />

      <!-- 源模板 R30：可编辑披露正文 -->
      <div class="note-block">
        <div class="note-block-title">说明（源模板 R30）</div>
        <el-input
          v-model="tables.rollbackNote.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          :placeholder="ROLLBACK_PLACEHOLDER"
          @change="onRollbackNoteChange"
        />
      </div>

      <!-- 源模板 R31 / R32：只读提示 -->
      <div class="source-hint">
        <div v-for="(t, i) in UNOFFSET_HINTS" :key="i">{{ t }}</div>
      </div>
    </el-card>

    <!-- ═══（2）以抵销后净额列示的递延所得税资产或负债 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>
            （2）以抵销后净额列示的递延所得税资产或负债（不适用的删除）
            <el-tag v-if="netOffsetChoice === 'no'" type="info" size="small">
              不适用（已从附注清除）
            </el-tag>
          </span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('netoffset')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <N1DisclosureSegmentTable
        label-header="项  目"
        :columns="netOffsetColumns"
        :segments="tables.netOffsetSegmentsListed.value"
        :readonly="isReadonly"
        :allow-add-row="false"
        @change-cell="onNetOffsetCell"
      />
      <div class="source-hint">
        <div>{{ NET_OFFSET_HINT }}</div>
      </div>
    </el-card>

    <!-- ═══（3）未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（3）未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('unrecognized')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-alert
        v-if="!tables.lossPayload.value.hasData"
        type="info"
        :closable="false"
        show-icon
        class="pending-alert"
      >
        <template #title>「可抵扣亏损」行待 N1-5 编制</template>
        <template v-if="tables.lossPayload.value.isLegacyEstimate" #default>
          检测到旧版 N1-5 数据（推算值，非审计师确认／不确认录入），请完成 N1-5 新模型编制后刷新。
        </template>
      </el-alert>
      <N1DisclosureSegmentTable
        label-header="项  目"
        :columns="unrecognizedColumns"
        :segments="tables.unrecognizedSegments.value"
        :readonly="isReadonly"
        :allow-add-row="false"
        @change-cell="onUnrecognizedCell"
      />
      <div class="source-hint">
        <div>{{ UNRECOGNIZED_NOTE }}</div>
      </div>
    </el-card>

    <!-- ═══（4）未确认递延所得税资产的可抵扣亏损将于以下年度到期 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（4）未确认递延所得税资产的可抵扣亏损将于以下年度到期</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('lossexpiry')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <N1DisclosureSegmentTable
        label-header="年  份"
        :columns="lossExpiryColumns"
        :segments="tables.lossExpirySegments.value"
        :readonly="isReadonly"
        @change-cell="onLossExpiryCell"
        @change-label="onLossExpiryLabel"
        @add-row="tables.addLossExpiryRow"
        @remove-row="onLossExpiryRemove"
      />
      <div class="source-hint">
        <div>{{ LOSS_EXPIRY_NOTE }}</div>
      </div>
    </el-card>

    <!-- ═══ 披露说明与结论 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>披露说明与结论</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="tables.conclusionNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明递延所得税资产确认依据、未确认原因、抵销与列示口径及披露完整性核对结论..."
        @change="onConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本页 4 张表逐字对齐致同源模板 <code>附注披露信息（上市公司）</code>，是附注 {{ N1_NOTE_SECTION.listed }} 的交付物源</li>
        <li>表（1）两级表头：期末余额 / 上年年末余额，各含「可抵扣/应纳税暂时性差异」与「递延所得税资产/负债」两列</li>
        <li>资产段小计 = 段内各项之和；负债段小计同理（源模板 =SUM(B13:B20) / =SUM(B23:B28)）</li>
        <li>负债段数据来源于递延所得税负债底稿（N3），本页只负责列示；四表已入库时按科目 2901 叶子余额自动带出总额级分类</li>
        <li>四表入库后打开本页，表（1）「递延所得税资产/负债」列自动带出（暂时性差异列需人工，四表推不出税率）；已录数据不被覆盖</li>
        <li>表（2）顶部「是否适用」对应源模板标题括注「不适用的删除」：选「不适用」后该表从附注清除；保持「未判断」则照旧推送</li>
        <li>表（3）「可抵扣亏损」行与表（4）合计必须相等（源模板 B40=B52 / C40=C52），由勾稽面板实时校验</li>
        <li>表（4）默认列示 6 个年度（源模板 R46:R51）：期末列的亏损到期于 Y+1~Y+5、上年年末列到期于 Y~Y+4，两列并集即 Y~Y+5，故首行期末列与末行上年年末列填「——」；10 年结转或无使用期限用「+ 新增行」补足</li>
        <li>审计过程（账面价值 / 计税基础 / 适用税率 / 确认依据）在 N1-2 明细表与 N1-4 测算表，不在披露表列示</li>
        <li>编辑后自动同步到附注（防抖 800ms），也可点「同步到附注」立即推送</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabDisclosureListed — 递延所得税资产附注披露（上市公司）
 *
 * Spec: `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/`（R1 / R3 / R5）
 *
 * 结构逐字对齐源模板 `N1 递延所得税资产.xlsx` 的 `附注披露信息（上市公司）`（A1:K54）：
 * 4 张表 + R30 说明正文 + R31/R32/R43/R53 只读提示 + R54 跨表勾稽。
 *
 * 🔴 本组件此前是自造结构（7 列「已确认明细」+ 源模板没有的「余额变动表」与
 * 「与 N3 对应关系」，且缺表（2）与负债段）→ 已按源模板重建。
 * 编制模型 / 公式 / 勾稽入参 / 同步载荷统一在 `useN1DisclosureTables`。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
// @ts-ignore
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useN1FormData } from '../../composables/useN1FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { N1_DISCLOSURE_SHEET_NAME, N1_NOTE_SECTION } from '../../composables/n1NoteSectionMap'
import { dataTableNames, serializeSyncedTableNames } from '../../composables/disclosureSyncedTables'
import {
  n1LossExpirySegColumns,
  n1NetOffsetSegColumnsListed,
  n1UnoffsetSegColumns,
  n1UnrecognizedSegColumns,
  useN1DisclosureTables,
} from '../../composables/useN1DisclosureTables'
import { generateN1Text } from '../../composables/useN1AiText'
import N1DisclosureSegmentTable from '../shared/N1DisclosureSegmentTable.vue'
import N1DisclosureConsistencyPanel from '../shared/N1DisclosureConsistencyPanel.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 审计年度（决定亏损到期年度骨架；缺省回退审计上下文/当前年） */
  year?: number
}>()

defineEmits<{ (e: 'navigate', sheetName: string): void }>()

// ─── 源模板只读文案（含中文引号，故只放 script 常量，不进模板属性）───────────

const ROLLBACK_PLACEHOLDER =
  '说明：其中一年后预期转回的递延所得税资产和递延所得税负债分别为X.XX元、X.XX元。'

const UNOFFSET_HINTS = [
  '【提示：连续亏损的情况下，仍将较大金额的未抵扣亏损确认递延所得税资产，对当期净利润影响较大，甚至扭亏为盈，应当披露相关判断依据】',
  '【提示：产生递延所得税资产的资产减值准备中包括持有待售资产的资产减值准备。】',
  '源模板红字：递延所得税负债数据来源于递延所得税负债底稿。',
]

const NET_OFFSET_HINT =
  '源模板标题括注「不适用的删除」：仅在递延所得税资产与递延所得税负债以抵销后净额列示时填列。'

const UNRECOGNIZED_NOTE =
  '注：列示由于未来能否获得足够的应纳税所得额具有不确定性，因此没有确认为递延所得税资产的可抵扣暂时性差异和可抵扣亏损。'

const LOSS_EXPIRY_NOTE =
  '注：无法在资产负债表日确定全部可抵扣亏损情况的，可只填写能确定部分的金额及其到期年度，并在备注栏予以说明。'

// ─── 上下文 ──────────────────────────────────────────────────────────────────

const router = useRouter()
const auditCtx = useAuditContext()
const isReadonly = computed(() => props.isReadonly ?? false)
const syncing = ref(false)
const aiLoading = ref(false)

const syncYear = computed(() => props.year || auditCtx.year.value || new Date().getFullYear())

const formData = useN1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const tables = useN1DisclosureTables({
  variant: 'listed',
  allResponses: formData.allResponses,
  auditYear: syncYear,
  // 四表直通：`loadData()` 内部 await `selfLoad()` → restore() 前预填已就绪
  adjudicationPrefill: formData.adjudicationPrefill,
  liabilityPrefill: formData.liabilityPrefill,
})

const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })

const unoffsetColumns = computed(() => n1UnoffsetSegColumns('listed'))
const netOffsetColumns = computed(() => n1NetOffsetSegColumnsListed())
const unrecognizedColumns = computed(() => n1UnrecognizedSegColumns('listed'))
const lossExpiryColumns = computed(() => n1LossExpirySegColumns('listed'))

const hasCheckError = computed(() => tables.checks.value.some((c) => c.level === 'error'))

/**
 * 四表取数溯源（消费后端 `tb_source_codes`）：科目集由 `report_config` 规则映射解析
 * （BS-036 递延所得税资产 / BS-067 递延所得税负债），项目自定义报表行公式时随之变化。
 */
const tbSourceSummary = computed(() => {
  const s = formData.tbSourceCodes.value
  const parts: string[] = []
  if (s.asset.codes.length) {
    parts.push(`递延所得税资产 ${s.asset.codes.join('、')}（报表行 ${s.asset.row_code}）`)
  }
  if (s.liability.codes.length) {
    parts.push(`递延所得税负债 ${s.liability.codes.join('、')}（报表行 ${s.liability.row_code}）`)
  }
  return parts.join('； ')
})

/**
 * 表（2）适用性三态（源模板 R33「不适用的删除」）。
 * 与 `tables.netOffsetApplicable`（`boolean | null`）双向映射 —— 用字符串是因为
 * `el-radio-button` 的 value 不便承载 `null`。
 */
const netOffsetChoice = computed<'undecided' | 'yes' | 'no'>({
  get: () => {
    const v = tables.netOffsetApplicable.value
    return v === true ? 'yes' : v === false ? 'no' : 'undecided'
  },
  set: (next) => {
    tables.netOffsetApplicable.value = next === 'yes' ? true : next === 'no' ? false : null
  },
})

/** 表（2）适用性变更：持久化 + 触发同步（不适用时该表进 `_removed_table_keys`） */
function onNetOffsetApplicableChange(): void {
  const v = tables.netOffsetApplicable.value
  formData.debouncedSave(tables.itemIds.netOffsetApplicable, {
    conclusion: v === true ? '1' : v === false ? '0' : null,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 持久化（整表 JSON，一表一 item）────────────────────────────────────────

function persistUnoffset(): void {
  formData.debouncedSave(tables.itemIds.unoffset, {
    conclusion: JSON.stringify({
      asset: tables.assetRows.value,
      liability: tables.liabilityRows.value,
    }),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistNetOffset(): void {
  formData.debouncedSave(tables.itemIds.netOffset, {
    conclusion: JSON.stringify(tables.netOffsetListed.value),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistUnrecognized(): void {
  formData.debouncedSave(tables.itemIds.unrecognized, {
    conclusion: JSON.stringify(tables.unrecognizedRows.value),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistLossExpiry(): void {
  formData.debouncedSave(tables.itemIds.lossExpiry, {
    conclusion: JSON.stringify(tables.lossExpiryRows.value),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 单元格 / 行名变更 ───────────────────────────────────────────────────────

type CellPayload = { seg: string; index: number; key: string; value: number | string }

function onUnoffsetCell(p: CellPayload): void {
  const target = p.seg === 'asset' ? tables.assetRows : tables.liabilityRows
  const row = target.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistUnoffset()
}

function onUnoffsetLabel(p: { seg: string; index: number; value: string }): void {
  const target = p.seg === 'asset' ? tables.assetRows : tables.liabilityRows
  const row = target.value[p.index]
  if (!row) return
  row.item = p.value
  persistUnoffset()
}

function onUnoffsetRemove(p: { seg: string; index: number }): void {
  const target = p.seg === 'asset' ? tables.assetRows : tables.liabilityRows
  target.value = target.value.filter((_, i) => i !== p.index)
  persistUnoffset()
}

function onNetOffsetCell(p: CellPayload): void {
  const row = tables.netOffsetListed.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistNetOffset()
}

function onUnrecognizedCell(p: CellPayload): void {
  const row = tables.unrecognizedRows.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistUnrecognized()
}

function onLossExpiryCell(p: CellPayload): void {
  const row = tables.lossExpiryRows.value[p.index]
  if (!row) return
  ;(row as Record<string, unknown>)[p.key] = p.value
  persistLossExpiry()
}

function onLossExpiryLabel(p: { seg: string; index: number; value: string }): void {
  const row = tables.lossExpiryRows.value[p.index]
  if (!row) return
  row.item = p.value
  persistLossExpiry()
}

function onLossExpiryRemove(p: { seg: string; index: number }): void {
  tables.lossExpiryRows.value = tables.lossExpiryRows.value.filter((_, i) => i !== p.index)
  persistLossExpiry()
}

function onRollbackNoteChange(): void {
  formData.debouncedSave(tables.itemIds.rollbackNote, {
    remark: tables.rollbackNote.value || null,
  })
  emitNoteUpdated('rollback-listed', tables.rollbackNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function onConclusionChange(): void {
  formData.debouncedSave(tables.itemIds.conclusion, {
    remark: tables.conclusionNote.value || null,
  })
  emitNoteUpdated('conclusion-listed', tables.conclusionNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 附注事件 ────────────────────────────────────────────────────────────────

/**
 * 载荷必须带 accountCode/projectId/sectionIds，否则附注模块 `useNoteRefresh`
 * 的定向刷新匹配不到（只带 wpCode/section 命不中）。
 */
function emitNoteUpdated(section: string, text?: string): void {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N1',
    section,
    accountCode: '1811',
    projectId: props.projectId,
    sectionIds: [N1_NOTE_SECTION.listed],
    ...(text !== undefined ? { text } : {}),
    timestamp: Date.now(),
  } as any)
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法同步')
    return
  }
  syncing.value = true
  try {
    const payload = tables.buildPayload({ wpId: props.wpId, year: syncYear.value })
    const resp: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = resp?.data?.data ?? resp?.data
    if (data?.success) {
      ElMessage.success(
        `已${data.created ? '新建' : '更新'}附注 ${data.section_id}：${data.rows_synced} 行`
        + (data.texts_synced ? `，正文 ${data.texts_synced} 段` : ''),
      )
      // 🔴 只有同步**成功**后才记录已同步表名（失败也写会把现存表当孤儿删）
      markSynced(dataTableNames(payload.sub_table_data))
      emitNoteUpdated('sync-listed')
    } else {
      ElMessage.error('附注同步返回异常，请重试')
    }
  } catch (err: any) {
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
    ElMessage.error(`附注同步失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally {
    syncing.value = false
  }
}

function markSynced(names: string[]): void {
  tables.syncedTables.value = names
  formData.debouncedSave(tables.itemIds.syncedTables, {
    conclusion: serializeSyncedTableNames(names),
  })
}

function jumpToNote(variant: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'N1', variant, syncYear.value)
  if (!route) {
    ElMessage.warning('缺少项目上下文，无法跳转附注')
    return
  }
  router.push(route)
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

const AI_PROMPTS: Record<string, string> = {
  unoffset:
    '请基于「未经抵销的递延所得税资产和递延所得税负债」表数据撰写披露复核建议：'
    + '资产段与负债段列示是否完整、各段小计与明细是否勾稽、'
    + '是否已按源模板提示披露连续亏损下仍确认大额可抵扣亏损递延所得税资产的判断依据、'
    + '资产减值准备中是否含持有待售资产减值准备。不得虚构未提供的数据。',
  netoffset:
    '请就「以抵销后净额列示的递延所得税资产或负债」给出复核建议：是否为同一纳税主体、'
    + '互抵金额与抵销后余额的计算是否与未经抵销表勾稽、不适用时是否应删除该表。不得虚构数据。',
  unrecognized:
    '请撰写未确认递延所得税资产说明：可抵扣暂时性差异与可抵扣亏损未确认的原因'
    + '（未来能否获得足够应纳税所得额的不确定性）、判断依据、与 N1-5 亏损检查表的勾稽。不得虚构数据。',
  lossexpiry:
    '请就未确认递延所得税资产的可抵扣亏损到期年度分布给出披露复核建议：'
    + '到期年度是否完整、合计是否等于未确认明细的「可抵扣亏损」行、'
    + '无法确定全部可抵扣亏损时是否已在备注栏说明。不得虚构数据。',
  conclusion:
    '请撰写上市公司递延所得税资产附注披露说明与结论：确认依据、'
    + '未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损的原因、抵销与分列口径、'
    + '与审定表 N1-1 / 明细表 N1-2 / 亏损检查表 N1-5 的勾稽是否一致、披露完整性。不得虚构数据。',
}

async function handleAI(section: string): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const text = await generateN1Text({
      wpId: props.wpId,
      section: `n1-disclosure-listed-${section}`,
      prompt: AI_PROMPTS[section] || AI_PROMPTS.conclusion,
      context: {
        章节: N1_NOTE_SECTION.listed,
        审计年度: String(syncYear.value ?? ''),
        资产段小计期末: String(tables.assetSubtotal.value.endTax ?? ''),
        负债段小计期末: String(tables.liabilitySubtotal.value.endTax ?? ''),
        未确认合计期末: String(tables.unrecognizedTotal.value.end ?? ''),
        亏损到期合计期末: String(tables.lossExpiryTotal.value.end ?? ''),
        勾稽不一致项数: String(tables.checks.value.filter((c) => c.level === 'error').length),
      },
      existingContent: section === 'conclusion' ? tables.conclusionNote.value : '',
    })
    if (!text) return
    if (section === 'conclusion') {
      tables.conclusionNote.value = text
      onConclusionChange()
      ElMessage.success('AI 已生成披露说明与结论')
    } else {
      const { ElMessageBox } = await import('element-plus')
      await ElMessageBox.alert(text, 'AI 披露复核建议', { confirmButtonText: '知道了' }).catch(() => {})
    }
  } finally {
    aiLoading.value = false
  }
}

// ─── 生命周期 ────────────────────────────────────────────────────────────────

function onAdjudicatedRefresh(): void {
  formData.loadData().then(() => {
    tables.restore()
    emitNoteUpdated('auto-refresh-listed')
  })
}

onMounted(async () => {
  await formData.loadData()
  tables.restore()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
  autoSync.cancelPending()
})
</script>

<style scoped>
.n1-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.7; }
.methodology-text strong { color: #b88230; }

.branch-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.branch-label { font-size: var(--wp-font-size, 13px); color: #b88230; font-weight: 600; }
.source-trace { font-size: 12px; color: #6b5900; }

.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

.note-block { margin-top: 12px; }
.note-block-title { font-size: 12px; color: #606266; margin-bottom: 4px; }

.source-hint { margin-top: 10px; padding: 8px 10px; background: #fffbe6; border-left: 3px solid #f7ba2a; border-radius: 0 4px 4px 0; font-size: 12px; color: #8c6d1f; line-height: 1.7; }

.pending-alert { margin-bottom: 12px; }

.n1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
