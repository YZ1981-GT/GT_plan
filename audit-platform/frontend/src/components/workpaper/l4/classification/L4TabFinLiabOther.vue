<template>
  <div class="l4-tab-fin-liab-other">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-3 划分为金融负债的其他金融工具明细表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增
        </el-button>
        <el-button size="small" @click="handleAI('finLiab')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <!--
          🔴 L4-3 不单独挂导入导出下拉（2026-08-12 实证）

          l4 的后端三端点**不接受 sheet 参数**：
            l4_export_template(wp_id, db, current_user)
            l4_export_data(wp_id, db, current_user)
            l4_import_data(wp_id, file, db, current_user)
          （`app/routers/l4_bonds_payable.py`，整表导出语义）

          FastAPI 对未声明的 query 参数是**静默丢弃**，所以在这里挂
          `sheet="L4-3"` 不会报错，但导出的内容与 L4-2 完全相同 ——
          用户会以为拿到的是 L4-3 的数据。不报错、四层守卫全绿，只有对着
          导出文件核对才发现，属最难查的一类。

          实测 registry 的 69 个多 sheet 前缀里，**只有 l4 一个**不接受 sheet
          参数（其余 66 个都接受，另 2 个是 h5/n4 路径不可达）。故 l4 只在主表
          L4-2 保留一个入口，语义即"导出本底稿数据"。

          守卫：后端 `test_ie_prefix_reachability.py` 的 SHEET_AGNOSTIC_PREFIXES
          钉死这类前缀，并限制它们在前端最多一个挂载点。
          要让 L4-3 单独导出，须先给后端加 sheet 参数与 L4-3 的列结构（须有源模板依据）。
        -->
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标（认定）</template>
      <ol class="ao-list">
        <li><b>完整性：</b>所有应付债券均已记录（负债完整性重点在前）；</li>
        <li><b>存在：</b>记录的应付债券在资产负债表日确实存在；</li>
        <li><b>义务：</b>应付债券确为被审计单位的义务；</li>
        <li><b>计价与分摊：</b>应付债券以恰当金额（摊余成本）列示；</li>
        <li><b>列报与披露：</b>应付债券已恰当列报和充分披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>划分为金融负债的其他金融工具（CAS 37）：</strong>
        不满足权益工具条件而划分为金融负债的金融工具。包括：优先股（强制分红）、永续债（含利率跳升）、
        可回售工具等。需逐一核实合同条款并判断是否满足负债定义（交付现金或其他金融资产的合同义务）。
      </div>
    </div>

    <!-- ═══ 明细表：列与模板 L4-3 的 A..AM 逐列对齐（行身份 rowId，整表一条 item L4-3-rows） ═══ -->
    <el-table :data="rows" row-key="rowId" border size="small" style="width: 100%" max-height="560">
      <el-table-column type="index" label="#" width="50" align="center" fixed="left" />
      <el-table-column
        v-for="col in SCALAR_COLUMNS"
        :key="col.key"
        :label="col.label"
        :min-width="col.width"
        :align="col.kind === 'number' ? 'right' : 'left'"
        :fixed="col.key === 'instrumentName' ? 'left' : undefined"
      >
        <template #default="{ row }">
          <template v-if="!isReadonly">
            <el-input-number
              v-if="col.kind === 'number'"
              v-model="row[col.key]"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="persist"
            />
            <el-input v-else v-model="row[col.key]" size="small" @change="persist" />
          </template>
          <span v-else>{{ col.kind === 'number' ? fmtAmount(row[col.key]) : (row[col.key] || '—') }}</span>
        </template>
      </el-table-column>

      <el-table-column v-for="g in PAIR_GROUPS" :key="g.stem" :label="g.label" align="center">
        <el-table-column v-for="unit in UNITS" :key="unit.suffix" :label="unit.label" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && !g.formula"
              v-model="row[g.stem + unit.suffix]"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="persist"
            />
            <span v-else :class="{ 'formula-cell': g.formula }">{{
              fmtAmount(g.formula ? applyL4_3Formulas(row)[g.stem + unit.suffix] : row[g.stem + unit.suffix])
            }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- HTML 侧补充信息（模板无对应列，不进 OnlyOffice） -->
      <el-table-column label="工具类型" min-width="120">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.instrumentType" size="small" style="width: 100%" @change="persist">
            <el-option label="优先股" value="优先股" />
            <el-option label="永续债" value="永续债" />
            <el-option label="可回售工具" value="可回售工具" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.instrumentType || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="划分为负债原因" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.liabilityReason" size="small" @change="persist" />
          <span v-else>{{ row.liabilityReason || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" text size="small" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计 ═══ -->
    <div class="summary-bar">
      <span>共 <strong>{{ rows.length }}</strong> 项工具</span>
      <span>审定期末金额合计：<strong>{{ fmtAmount(totalAuditedEnd) }}</strong></span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写金融负债划分审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>金融负债核心判断：是否存在交付现金或其他金融资产的合同义务</li>
        <li>优先股：强制分红条款→金融负债</li>
        <li>永续债：含利率跳升/赎回条款→实质为负债</li>
        <li>核实合同条款原件，关注隐含义务</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabFinLiabOther — L4-3 划分为金融负债的其他金融工具明细表
 *
 * spec: l-cycle-true-adapter-registration · Task 12（L4 真双向，受管表即本表）
 * - 列与模板 L4-3 的 A..AM 逐列对齐（38 个受管字段）；R/S、AF~AM 为公式列，只显示计算值
 * - 整表存一条 item `L4-3-rows`（JSON 数组，稳定 rowId），删行按 rowId
 * - 🔴 旧键 `L4-3-row-{index+1}-data` 是位置化行身份且无 hydration（刷新即丢），已废弃
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'
import { useDecimalCalc } from '@/composables/useDecimalCalc'
import {
  L4_3_FORMULA_STEMS,
  L4_3_ROWS_ITEM_ID,
  applyL4_3Formulas,
  createEmptyFinLiabRow,
  parseL4_3Rows,
  removeL4_3RowById,
  serializeL4_3Rows,
  type L4FinLiabRow,
  type L4PairStem,
} from '../../composables/useL4FinLiabRows'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

type ScalarColumn = { key: string; label: string; width: number; kind: 'text' | 'number' }
const SCALAR_COLUMNS: ScalarColumn[] = [
  { key: 'instrumentName', label: '发行在外的金融工具', width: 180, kind: 'text' },
  { key: 'issueDate', label: '发行时间', width: 110, kind: 'text' },
  { key: 'accountingClass', label: '会计分类', width: 120, kind: 'text' },
  { key: 'rate', label: '股利率或利息率', width: 110, kind: 'number' },
  { key: 'issuePrice', label: '发行价格', width: 110, kind: 'number' },
  { key: 'issueQty', label: '数量', width: 100, kind: 'number' },
  { key: 'issueAmount', label: '金额', width: 120, kind: 'number' },
  { key: 'maturity', label: '到期日或续期情况', width: 150, kind: 'text' },
  { key: 'conversionTerms', label: '转股条件', width: 140, kind: 'text' },
  { key: 'conversionStatus', label: '转换情况', width: 120, kind: 'text' },
]

const PAIR_LABELS: Record<L4PairStem, string> = {
  unauditedPrior: '未审 · 期初余额',
  unauditedIncrease: '未审 · 本期增加',
  unauditedDecrease: '未审 · 本期减少',
  unauditedEnd: '未审 · 期末余额',
  priorAje: '期初调整 · 账项调整',
  priorRje: '期初调整 · 重分类调整',
  ajeIncrease: '账项调整 · 本期增加',
  ajeDecrease: '账项调整 · 本期减少',
  rjeIncrease: '重分类调整 · 本期增加',
  rjeDecrease: '重分类调整 · 本期减少',
  auditedPrior: '审定数 · 期初余额',
  auditedIncrease: '审定数 · 本期增加',
  auditedDecrease: '审定数 · 本期减少',
  auditedEnd: '审定数 · 期末余额',
}
const PAIR_GROUPS = (Object.keys(PAIR_LABELS) as L4PairStem[]).map((stem) => ({
  stem,
  label: PAIR_LABELS[stem],
  formula: L4_3_FORMULA_STEMS.has(stem),
}))
const UNITS = [
  { suffix: 'Qty', label: '数量' },
  { suffix: 'Amount', label: '金额' },
]

const rows = ref<L4FinLiabRow[]>([])
const decimal = useDecimalCalc()
const totalAuditedEnd = computed(() =>
  Number(decimal.sum(...rows.value.map((r) => Number(applyL4_3Formulas(r).auditedEndAmount) || 0))),
)

const auditNote = ref('')

function saveAuditNote() {
  formData.debouncedSave('L4-3-auditNote', { remark: auditNote.value || null })
}

/** 整表一次写一条 item（行身份稳定，删中间行不让后续行错位）。 */
function persist() {
  formData.debouncedSave(L4_3_ROWS_ITEM_ID, { remark: serializeL4_3Rows(rows.value) })
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入金融工具名称', '新增金融负债工具', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: (val) => (!val?.trim() ? '名称不能为空' : true),
    })
    rows.value.push(createEmptyFinLiabRow(name?.trim() || ''))
    persist()
  } catch { /* cancel */ }
}

function removeRow(rowId: string) {
  rows.value = removeL4_3RowById(rows.value, rowId)
  persist()
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l4-fin-liab-other-${section}`,
      prompt: `请基于划分为金融负债的其他金融工具"${section}"数据，给出分类合理性审计建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: unknown): string {
  const n = Number(val)
  if (!Number.isFinite(n) || n === 0) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
  rows.value = parseL4_3Rows(formData.allResponses.value.get(L4_3_ROWS_ITEM_ID)?.remark)
  auditNote.value = formData.allResponses.value.get('L4-3-auditNote')?.remark || ''
})
</script>

<style scoped>
.l4-tab-fin-liab-other { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.summary-bar {
  display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px;
  background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}

.audit-note-card { margin-top: 16px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #606266; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

.audit-objective { margin-bottom: 12px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
</style>
