<template>
  <div class="m4-tab-adjudication">
    <!-- 四表库取数溯源面板 -->
    <WpFourTableSourcePanel
      v-if="props.tbSourceCodes"
      :source-codes="props.tbSourceCodes"
      gross-label="资本公积"
    />
    <!-- ═══ 标题 + DualMode + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M4-1 资本公积审定表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" :disabled="isReadonly" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon> 带入调整
        </el-button>
        <el-button size="small" :loading="aiLoading === 'adjudication'" @click="handleAI('adjudication')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective-alert">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        确认资本公积（4002）的<strong>完整性</strong>（资本溢价、其他资本公积各项来源完整入账）、
        <strong>计价准确性</strong>（股份支付、外币折算差异计量正确）、
        <strong>列报恰当性</strong>（资本溢价与其他资本公积分项披露）。
      </div>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景）─── 权益类贷方说明 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>资本公积（4002）为权益类贷方科目：</strong>
        期末余额 = 期初 + 贷方（增加） − 借方（减少）。
        审定数 = 未审数 + AJE + RJE。
        资本溢价（出资超面值）在贷方增加，转增资本/弥补亏损在借方减少，
        与库存股M3（借方/权益备抵类）方向<strong>完全相反</strong>。
        双区块展示：资本溢价（股本溢价）+ 其他资本公积（含股份支付/外币折算差异等）。
        审定数变化自动回写试算表（4002）并通知附注组件。
      </div>
    </div>

    <!-- ═══ 区块一：资本溢价（股本溢价） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">资本溢价（股本溢价）</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow('premium')"
        >
          + 新增项目
        </el-button>
      </div>

      <el-table
        :data="premiumTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- A列: 项目名称 -->
        <el-table-column prop="itemName" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="项目名称"
                @change="(val: string) => updatePremiumRow($index, 'itemName', val)"
              />
            </template>
            <template v-else>
              {{ row.itemName || '—' }}
            </template>
          </template>
        </el-table-column>

        <!-- B列: 期初余额（贷方） -->
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginning"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updatePremiumRow($index, 'beginning', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <!-- C列: 贷方发生额（增加） -->
        <el-table-column label="贷方发生（增加）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.creditAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updatePremiumRow($index, 'creditAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- D列: 借方发生额（减少） -->
        <el-table-column label="借方发生（减少）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.debitAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updatePremiumRow($index, 'debitAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- E列: 期末余额（公式=期初+贷方-借方，权益类贷方！） -->
        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(增加) − 借方(减少)" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <!-- F列: 未审数 -->
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.unadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updatePremiumRow($index, 'unadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- G列: AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.aje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updatePremiumRow($index, 'aje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- H列: RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.rje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updatePremiumRow($index, 'rje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- I列: 审定数（公式=未审+AJE+RJE） -->
        <el-table-column label="审定" width="120" align="right">
          <template #header>
            <el-tooltip content="审定数=未审+调整+重分类" placement="top">
              <span class="formula-col-header">审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>

        <!-- 操作列（非只读时） -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button
              v-if="isDataRow(row)"
              type="danger"
              size="small"
              link
              @click="handleRemovePremiumRow($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 资本溢价小计 -->
      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">
          资本溢价小计审定: {{ fmtAmount(premiumSubtotal.audited) }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 区块二：其他资本公积 ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">其他资本公积</h4>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          @click="handleAddRow('other')"
        >
          + 新增项目
        </el-button>
      </div>

      <el-table
        :data="otherTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
      >
        <!-- A列: 项目名称 -->
        <el-table-column prop="itemName" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.itemName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="项目名称"
                @change="(val: string) => updateOtherRow($index, 'itemName', val)"
              />
            </template>
            <template v-else>
              {{ row.itemName || '—' }}
            </template>
          </template>
        </el-table-column>

        <!-- B列: 期初余额 -->
        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginning"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateOtherRow($index, 'beginning', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <!-- C列: 贷方发生额（增加） -->
        <el-table-column label="贷方发生（增加）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.creditAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateOtherRow($index, 'creditAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
          </template>
        </el-table-column>

        <!-- D列: 借方发生额（减少） -->
        <el-table-column label="借方发生（减少）" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.debitAmount"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateOtherRow($index, 'debitAmount', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
          </template>
        </el-table-column>

        <!-- E列: 期末余额 -->
        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="权益类贷方公式: 期初 + 贷方(增加) − 借方(减少)" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <!-- F列: 未审数 -->
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.unadjusted"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateOtherRow($index, 'unadjusted', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- G列: AJE -->
        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.aje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateOtherRow($index, 'aje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- H列: RJE -->
        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.rje"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateOtherRow($index, 'rje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- I列: 审定数 -->
        <el-table-column label="审定" width="120" align="right">
          <template #header>
            <el-tooltip content="审定数=未审+调整+重分类" placement="top">
              <span class="formula-col-header">审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button
              v-if="isDataRow(row)"
              type="danger"
              size="small"
              link
              @click="handleRemoveOtherRow($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 其他资本公积小计 -->
      <div class="block-subtotal">
        <el-tag type="info" size="small" effect="plain">
          其他资本公积小计审定: {{ fmtAmount(otherSubtotal.audited) }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 合计 + 期末校验 + TB回写状态 ═══ -->
    <div class="adjudication-footer">
      <el-tag type="primary" size="small" effect="dark">
        合计审定: {{ fmtAmount(totalRow.audited) }}
      </el-tag>
      <el-tag type="success" size="small" effect="plain">
        TB回写: 科目4002 资本公积（贷方/权益类）
      </el-tag>
      <el-tag
        :type="equityEndCheck.isMatch ? 'success' : 'danger'"
        size="small"
        effect="plain"
      >
        期末校验: 期末{{ fmtAmount(equityEndCheck.actual) }}
        {{ equityEndCheck.isMatch ? '=' : '≠' }}
        期初+贷方−借方{{ fmtAmount(equityEndCheck.expected) }}
        <template v-if="!equityEndCheck.isMatch">
          （差异: {{ fmtAmount(equityEndCheck.diff) }}）
        </template>
      </el-tag>
      <el-tag
        v-if="periodChange.changeRate !== null"
        :type="Math.abs(periodChange.changeRate) > 0.2 ? 'warning' : 'info'"
        size="small"
        effect="plain"
      >
        变动率: {{ (periodChange.changeRate * 100).toFixed(1) }}%
      </el-tag>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" :loading="aiLoading === 'auditNote'" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写资本公积审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>资本公积（4002）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（增加） − 借方（减少）</li>
        <li>方向正常：资本溢价（出资超面值）在<strong>贷方</strong>增加，转增资本/弥补亏损在<strong>借方</strong>减少（与M3库存股权益备抵类借方方向相反！）</li>
        <li>审定数 = 未审数 + AJE（账项调整） + RJE（重分类调整）</li>
        <li>双区块展示：资本溢价（股本溢价）+ 其他资本公积（股份支付/外币折算差异等）</li>
        <li>资本溢价区块：出资超面值部分，限额转增资本减少</li>
        <li>其他资本公积区块：股份支付权益结算(J3)、外币折算差异(M2)、权益法调整等</li>
        <li>审定数变化自动回写 TB（科目 4002）并通知附注组件</li>
        <li>合计行应与明细表M4-2的合计一致（交叉验证）</li>
        <li>「带入调整」：从集中登记按科目 4002 拉取调整分录，逐笔分配到各区块项目行的 AJE/RJE，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="4002 资本公积"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * M4TabAdjudication — M4-1 资本公积审定表（权益类贷方！）
 *
 * Requirements: 2.1-2.7
 * - 双区块：资本溢价(股本溢价) + 其他资本公积 + 合计
 * - 列结构（44×12）：
 *   A:项目 | B:期初 | C:贷方发生(增加) | D:借方发生(减少)
 *   | E:期末[公式=期初+贷方-借方] | F:未审 | G:AJE | H:RJE | I:审定[公式=未审+AJE+RJE]
 * - 公式列: 虚线下划线 + cursor:help + tooltip showing formula source
 * - 权益类贷方期末校验: 期末=期初+贷方-借方
 * - TB回写: 审定数变化 → writebackTB(4002)
 * - EventBus: publish 'substantive:adjudicated' on save
 * - 双模式(HTML/OO)由入口 GtM4CapitalReserve 统一承载（useM4EntryDualMode），本 tab 不再自带 segmented
 * - 复核按钮 (inject openReviewDialog)
 * - AI辅助 section title right-aligned button
 * - Table font-size 13px
 * - Uses useM4FormData + useM4Adjudication composables
 * - Props: wpId, projectId, isReadonly
 *
 * 科目：4002 资本公积（**贷方/权益类！期末=期初+贷方-借方**）
 * 资本溢价在贷方增加（出资超面值），借方减少（转增资本/弥补亏损）
 * 与M3库存股（借方/权益备抵类）方向完全相反！
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check, Download } from '@element-plus/icons-vue'
import { useM4FormData } from '../../composables/useM4FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import {
  useM4Adjudication,
  type M4AdjudicationRow,
  type M4AdjudicationBlock,
} from '../../composables/useM4Adjudication'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import { eventBus } from '@/utils/eventBus'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  tbSourceCodes?: Record<string, any> | null
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'save'): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 审定表行数据（双区块：premium + other） ─────────────────────────────────

const rows = ref<M4AdjudicationRow[]>([])

// ─── Adjudication Composable ─────────────────────────────────────────────────

const {
  computedRows,
  premiumSubtotal,
  otherSubtotal,
  totalRow,
  periodChange,
  equityEndCheck,
  addRow,
  removeRow,
  updateRow: composableUpdateRow,
  saveAndWriteback,
  subscribeDisclosure,
} = useM4Adjudication(formData, rows)

// ─── 从集中登记带入调整（4002 资本公积，权益贷方；单期 aje/rje，双区块项目行） ───
const bringInRows = computed(() =>
  computedRows.value.map((r) => ({
    rowKey: r.key,
    name: r.itemName || (r.block === 'premium' ? '资本溢价项目' : '其他资本公积项目'),
    aje: r.aje ?? 0,
    rje: r.rje ?? 0,
  })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '4002',
  direction: 'credit',
  subjectCode: '4002',
  wpCode: 'M4',
  subjectLabel: '资本公积(4002)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => {
    const idx = rows.value.findIndex((r) => r.key === rowKey)
    if (idx < 0) return
    composableUpdateRow(idx, field === 'aje' ? 'aje' : 'rje', value)
  },
  totalAudited: () => totalRow.value.audited,
})

// ─── 表格数据：按区块拆分 + 小计行 ──────────────────────────────────────────

interface TableRow extends M4AdjudicationRow {
  _rowType?: 'data' | 'subtotal'
}

/** 资本溢价区块表格行（数据行 + 小计行） */
const premiumTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = []
  const premiumRows = computedRows.value.filter(r => r.block === 'premium')
  for (const row of premiumRows) {
    result.push({ ...row, _rowType: 'data' })
  }
  // 小计行
  result.push({
    key: 'premium-subtotal',
    itemName: '资本溢价小计',
    block: 'premium',
    beginning: premiumSubtotal.value.beginning,
    creditAmount: premiumSubtotal.value.creditAmount,
    debitAmount: premiumSubtotal.value.debitAmount,
    endBalance: premiumSubtotal.value.endBalance,
    unadjusted: premiumSubtotal.value.unadjusted,
    aje: premiumSubtotal.value.aje,
    rje: premiumSubtotal.value.rje,
    audited: premiumSubtotal.value.audited,
    _rowType: 'subtotal',
  })
  return result
})

/** 其他资本公积区块表格行（数据行 + 小计行） */
const otherTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = []
  const otherRows = computedRows.value.filter(r => r.block === 'other')
  for (const row of otherRows) {
    result.push({ ...row, _rowType: 'data' })
  }
  // 小计行
  result.push({
    key: 'other-subtotal',
    itemName: '其他资本公积小计',
    block: 'other',
    beginning: otherSubtotal.value.beginning,
    creditAmount: otherSubtotal.value.creditAmount,
    debitAmount: otherSubtotal.value.debitAmount,
    endBalance: otherSubtotal.value.endBalance,
    unadjusted: otherSubtotal.value.unadjusted,
    aje: otherSubtotal.value.aje,
    rje: otherSubtotal.value.rje,
    audited: otherSubtotal.value.audited,
    _rowType: 'subtotal',
  })
  return result
})

// ─── 行角色判断 ──────────────────────────────────────────────────────────────

function isDataRow(row: TableRow): boolean {
  return row._rowType === 'data'
}

function isSubtotalRow(row: TableRow): boolean {
  return row._rowType === 'subtotal'
}

function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  if (row._rowType === 'subtotal') return 'subtotal-row'
  return ''
}

// ─── 行操作代理（按区块映射到原始 rows index） ────────────────────────────────

/** 获取 premium 表格行对应的 raw rows index */
function getPremiumRawIndex(tableIndex: number): number {
  const premiumRows = computedRows.value.filter(r => r.block === 'premium')
  if (tableIndex < 0 || tableIndex >= premiumRows.length) return -1
  const targetKey = premiumRows[tableIndex].key
  return rows.value.findIndex(r => r.key === targetKey)
}

/** 获取 other 表格行对应的 raw rows index */
function getOtherRawIndex(tableIndex: number): number {
  const otherRows = computedRows.value.filter(r => r.block === 'other')
  if (tableIndex < 0 || tableIndex >= otherRows.length) return -1
  const targetKey = otherRows[tableIndex].key
  return rows.value.findIndex(r => r.key === targetKey)
}

function updatePremiumRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getPremiumRawIndex(tableIndex)
  if (rawIdx < 0) return
  composableUpdateRow(rawIdx, field as any, value)
}

function updateOtherRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getOtherRawIndex(tableIndex)
  if (rawIdx < 0) return
  composableUpdateRow(rawIdx, field as any, value)
}

function handleRemovePremiumRow(tableIndex: number): void {
  const rawIdx = getPremiumRawIndex(tableIndex)
  if (rawIdx < 0) return
  removeRow(rawIdx)
}

function handleRemoveOtherRow(tableIndex: number): void {
  const rawIdx = getOtherRawIndex(tableIndex)
  if (rawIdx < 0) return
  removeRow(rawIdx)
}

// ─── 新增行（动态行必须先弹 ElMessageBox.prompt 输入名称） ────────────────────

async function handleAddRow(block: M4AdjudicationBlock): Promise<void> {
  const blockLabel = block === 'premium' ? '资本溢价' : '其他资本公积'
  try {
    const { value } = await ElMessageBox.prompt(
      `请输入${blockLabel}项目名称`,
      `新增${blockLabel}项目`,
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: block === 'premium'
          ? '如：投资者出资超面值部分、股本溢价'
          : '如：股份支付权益结算、外币折算差异、权益法调整',
        inputValidator: (v: string) => (v && v.trim() ? true : '项目名称不能为空'),
      },
    )
    if (value && value.trim()) {
      addRow(value.trim(), block)
    }
  } catch {
    // 用户取消
  }
}

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAuditNote() {
  formData.debouncedSave('M4-M4-1-auditNote', { remark: auditNote.value || null })
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4002 资本公积（权益类贷方）',
      资本溢价小计审定: fmtAmount(premiumSubtotal.value.audited),
      其他资本公积小计审定: fmtAmount(otherSubtotal.value.audited),
      合计审定: fmtAmount(totalRow.value.audited),
      期末校验: equityEndCheck.value.isMatch
        ? '期末=期初+贷方−借方（一致）'
        : `期末与期初+贷方−借方差异 ${fmtAmount(equityEndCheck.value.diff)}`,
      变动率: periodChange.value.changeRate !== null
        ? (periodChange.value.changeRate * 100).toFixed(1) + '%'
        : '—',
    }
    const existing = auditNote.value
    const text = await generateAiText({ section: `m4-adjudication-${section}`, context, existingContent: existing })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
      return
    }
    auditNote.value = text
    saveAuditNote()
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = ''
  }
}

function handleReview() {
  openReviewDialog?.('M4-1-adjudication', '资本公积审定表')
}

// ─── EventBus: subscribe 附注刷新 + 调整分录创建 ─────────────────────────────

function handleAdjustmentCreated() {
  formData.loadData()
}

let unsubscribeDisclosure: (() => void) | null = null

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 从 checklist_responses 恢复已存储的行数据
  if (rows.value.length === 0) {
    const restored = _restoreRows()
    if (restored.length > 0) {
      rows.value = restored
    }
  }
  // 恢复审计说明
  const noteResp = formData.allResponses.value.get('M4-M4-1-auditNote')
  if (noteResp?.remark) {
    auditNote.value = noteResp.remark
  }
  // 订阅调整分录创建事件
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
  eventBus.on('substantive:adjudicated' as any, handleAdjustmentCreated)
  // 订阅附注 EventBus 刷新（Req 2.7）
  unsubscribeDisclosure = subscribeDisclosure(() => {
    formData.loadData()
  })
})

onUnmounted(() => {
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
  eventBus.off('substantive:adjudicated' as any, handleAdjustmentCreated)
  if (unsubscribeDisclosure) {
    unsubscribeDisclosure()
    unsubscribeDisclosure = null
  }
})

// ─── 行数据恢复（从 checklist_responses） ───────────────────────────────────

function _restoreRows(): M4AdjudicationRow[] {
  const restored: M4AdjudicationRow[] = []
  const prefix = 'M4-1-row-'
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith(prefix) && key.endsWith('-data') && resp.remark) {
      try {
        const data = JSON.parse(resp.remark)
        restored.push({
          key: data.key || `m4-adj-restored-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: data.itemName || '',
          block: data.block || 'premium',
          beginning: Number(data.beginning) || 0,
          creditAmount: Number(data.creditAmount) || 0,
          debitAmount: Number(data.debitAmount) || 0,
          endBalance: 0,
          unadjusted: Number(data.unadjusted) || 0,
          aje: Number(data.aje) || 0,
          rje: Number(data.rje) || 0,
          audited: 0,
        })
      } catch {
        // 解析失败跳过
      }
    }
  }
  return restored
}
</script>


<style scoped>
.m4-tab-adjudication {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.equity-badge {
  font-weight: 600;
}

.audit-objective-alert {
  margin-bottom: 16px;
}

.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
}

.block-section {
  margin-bottom: 24px;
}

.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.block-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.block-subtotal {
  margin-top: 8px;
  display: flex;
  align-items: center;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

.total-row-label {
  font-weight: 700;
  color: #303133;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.subtotal-row) {
  background: #f0f9eb !important;
  font-weight: 600;
}

:deep(.subtotal-row td) {
  border-top: 2px solid #67c23a;
}

.adjudication-footer {
  margin-top: 8px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.audit-note-card {
  margin-top: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.m4-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m4-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m4-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
