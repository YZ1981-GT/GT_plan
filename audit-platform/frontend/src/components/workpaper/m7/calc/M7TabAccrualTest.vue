<template>
  <div class="m7-tab-accrual-test">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M7-4 专项储备计提测试表</h3>
        <GtIndexChip value="wp:M7-2" :context-project-id="projectId" />
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'accrualTest'" @click="handleAI('accrualTest')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 蓝色渐变引导区（序号步骤） ═══ -->
    <div class="guide-zone">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="guide-num">1</span>
          <span class="guide-text">选择行业分类</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">2</span>
          <span class="guide-text">填入产量/收入数据</span>
        </div>
        <div class="guide-step">
          <span class="guide-num">3</span>
          <span class="guide-text">核对计提差异</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>安全生产费计提标准（分行业）：</strong>
        高危行业按国家规定提取安全生产费，属于专项储备（贷方增加）。
        <strong>煤矿：</strong>按原煤产量分档计提（吨煤15~30元/吨）。
        <strong>非煤矿山：</strong>按开采原矿产量分档计提（2~10元/吨）。
        <strong>危险品生产/储存：</strong>按营业收入超额累退分档计提（1%~4%）。
        <strong>建筑施工：</strong>按建安工程造价×2%或营业收入×1.5%计提。
        <strong>交通运输：</strong>按营业收入×1%~1.5%计提。
        <strong>冶金/机械制造：</strong>按营业收入×1%~2%计提。
        计提差异 = 应计提 − 账面计提（正差=少计提=审计风险点）。
      </div>
    </div>

    <!-- ═══ 计提基础选择 ═══ -->
    <el-card shadow="never" class="basis-card">
      <template #header>
        <span class="card-title">计提参数设置</span>
      </template>
      <el-form :disabled="isReadonly" label-width="130px" size="small">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="行业分类">
              <el-select
                v-model="localIndustry"
                placeholder="请选择行业分类"
                style="width:100%"
                @change="accrualTest.setIndustryCategory($event)"
              >
                <el-option
                  v-for="cat in INDUSTRY_CATEGORIES"
                  :key="cat"
                  :label="cat"
                  :value="cat"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计提基础">
              <el-radio-group
                v-model="localBasis"
                @change="accrualTest.setBasis($event as AccrualBasis)"
              >
                <el-radio-button value="output">按产量</el-radio-button>
                <el-radio-button value="revenue">按营业收入</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="企业名称">
              <el-input
                v-model="localEntityName"
                placeholder="被审计单位名称"
                @change="accrualTest.setEntityName($event)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="账面计提金额">
              <el-input-number
                v-model="localBooked"
                :controls="false"
                style="width:100%"
                placeholder="企业实际计提数"
                @change="accrualTest.setBooked($event ?? 0)"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- ═══ 按产量分档模式 ═══ -->
    <el-card v-if="localBasis === 'output'" shadow="never" class="tier-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">产量分档计提（G=E×F）</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="accrualTest.addTier()">
            + 新增档位
          </el-button>
        </div>
      </template>
      <el-table :data="accrualTest.computedTiers.value" border size="small" style="width:100%" class="tier-table">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column label="档位描述" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.label"
              size="small"
              :disabled="isReadonly"
              @change="accrualTest.updateTier($index, 'label', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="产量/基数(E)" width="150" align="right">
          <template #header>
            <el-tooltip content="E列：该档对应的产量或收入基数" placement="top">
              <span class="formula-col-header">产量/基数(E)</span>
            </el-tooltip>
          </template>
          <template #default="{ $index }">
            <el-input-number
              v-model="accrualTest.tiers.value[$index].output"
              :controls="false"
              size="small"
              style="width:100%"
              :disabled="isReadonly"
              @change="accrualTest.updateTier($index, 'output', $event ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="计提标准(F)" width="140" align="right">
          <template #header>
            <el-tooltip content="F列：该档的计提标准（元/吨 或 百分比）" placement="top">
              <span class="formula-col-header">计提标准(F)</span>
            </el-tooltip>
          </template>
          <template #default="{ $index }">
            <el-input-number
              v-model="accrualTest.tiers.value[$index].rate"
              :controls="false"
              :precision="4"
              size="small"
              style="width:100%"
              :disabled="isReadonly"
              @change="accrualTest.updateTier($index, 'rate', $event ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="应计金额(G=E×F)" width="150" align="right">
          <template #header>
            <el-tooltip content="公式: G = E × F（应计金额 = 基数 × 计提标准）" placement="top">
              <span class="formula-col-header">应计金额(G)</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button
              text
              type="danger"
              size="small"
              :disabled="isReadonly || accrualTest.tiers.value.length <= 1"
              @click="accrualTest.removeTier($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 按营业收入模式 ═══ -->
    <el-card v-if="localBasis === 'revenue'" shadow="never" class="revenue-card">
      <template #header>
        <span class="card-title">按营业收入计提（应计 = 收入 × 比例）</span>
      </template>
      <el-form :disabled="isReadonly" label-width="130px" size="small">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="营业收入">
              <el-input-number
                v-model="localRevenue"
                :controls="false"
                style="width:100%"
                placeholder="本期营业收入/建安造价"
                @change="accrualTest.setRevenue($event ?? 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="计提比例(%)">
              <el-input-number
                v-model="localRevenueRatePercent"
                :controls="false"
                :precision="2"
                :min="0"
                :max="100"
                style="width:100%"
                placeholder="如 1.5 = 1.5%"
                @change="accrualTest.setRevenueRate(($event ?? 0) / 100)"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- ═══ 计提汇总表（最终结果） ═══ -->
    <el-table :data="summaryRows" border size="small" style="width:100%; margin-top:16px" class="summary-table">
      <el-table-column prop="label" label="项目" min-width="160" fixed>
        <template #default="{ row }">
          <span :class="{ 'total-row-label': row.isTotal }">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="计提基础" width="140" align="center">
        <template #default="{ row }">
          <el-tag size="small" effect="plain" type="info">{{ row.basisDisplay }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="应计提" width="150" align="right">
        <template #header>
          <el-tooltip content="公式: G_total = SUM(各档G) 或 revenue×rate" placement="top">
            <span class="formula-col-header">应计提</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.estimated) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面计提" width="150" align="right">
        <template #default="{ row }">{{ fmtAmount(row.booked) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="150" align="right">
        <template #header>
          <el-tooltip content="公式: H = 应计提 − 账面计提（正差=少提=风险）。|差异|>阈值红色高亮。" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="{ 'diff-highlight': row.isDiffHighlight }">{{ fmtAmount(row.diff) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 9公式清单（展示前端实时计算覆盖） ═══ -->
    <div class="formula-summary">
      <el-tag size="small" effect="plain" type="info">9公式全部前端实时计算</el-tag>
      <span class="formula-list-hint">
        ①G1=E1×F1 ②G2=E2×F2 ③G3=E3×F3 ④...各档应计
        ⑤G_total=SUM(G各档) ⑥按收入=revenue×rate
        ⑦应计提(取basis) ⑧差异=应计-账面 ⑨差异高亮判断
      </span>
    </div>

    <!-- ═══ cross_wp_ref 跨底稿引用区 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 联动：</span>
      <GtIndexChip value="wp:M7-2" :context-project-id="projectId" />
      <span class="cross-wp-desc">明细表（计提金额来源）</span>
      <GtIndexChip value="wp:M7-1" :context-project-id="projectId" />
      <span class="cross-wp-desc">审定表（期末余额）</span>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">计提测试结论及说明</span>
          <el-button size="small" :loading="aiLoading === 'conclusion'" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写计提测试结论（如：计提金额准确/差异原因说明/需补提金额等）..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（details折叠） ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>煤矿：</strong>按开采原煤产量分档计提（吨煤15~30元/吨，按规模递减）</li>
        <li><strong>非煤矿山：</strong>按原矿产量分档（露天2元/吨、井下4元/吨、小型10元/吨）</li>
        <li><strong>危险品：</strong>按营业收入超额累退分档（≤1000万4%、1000万~1亿2%、>1亿1%）</li>
        <li><strong>建筑施工：</strong>按建安造价×2% 或 营业收入×1.5%</li>
        <li><strong>交通运输：</strong>铁路/公路按营业收入×1.5%、水运×1.5%、民航参照行业标准</li>
        <li><strong>冶金/机械：</strong>按营业收入×1%~2%计提</li>
        <li>计提差异 = 应计提 − 账面计提：正数=少计提（需补提），负数=多计提（需说明）</li>
        <li>会计分录：借:生产成本/制造费用/管理费用 贷:专项储备（4201）</li>
        <li>9公式全部前端实时计算，切换产量/收入模式后自动重算</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabAccrualTest — M7-4 专项储备计提测试表
 *
 * Requirements: 4.1-4.6
 * - 4.1: 显示列：计提基础(产量/营业收入) | 计提标准(分档) | 应计提 | 账面计提 | 差异
 * - 4.2: 按产量计提：应计提=Σ(各档产量×档位标准)
 * - 4.3: 按营业收入计提：应计提=营业收入×计提比例
 * - 4.4: 计提差异=应计提-账面计提
 * - 4.5: |计提差异|>阈值时红色高亮
 * - 4.6: 9公式全部前端实时计算
 *
 * 科目：4201 专项储备（贷方/权益类）
 * 安全生产费计提（贷方增加）：借:生产成本/管理费用 贷:专项储备
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM7FormData } from '../../composables/useM7FormData'
import { useM7AccrualTest, INDUSTRY_CATEGORIES, type AccrualBasis } from '../../composables/useM7AccrualTest'
import GtIndexChip from '../../GtIndexChip.vue'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
defineEmits<{ (e: 'navigate', sheetName: string): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {},
)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── Composable 初始化 ───────────────────────────────────────────────────────
const formData = useM7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const accrualTest = useM7AccrualTest(formData)

// ─── 本地输入绑定 ────────────────────────────────────────────────────────────
const localBasis = ref<AccrualBasis>('output')
const localIndustry = ref('')
const localEntityName = ref('')
const localBooked = ref(0)
const localRevenue = ref(0)
const localRevenueRatePercent = ref(0)
const auditNote = ref('')

// ─── 汇总表行结构 ────────────────────────────────────────────────────────────

interface SummaryRow {
  label: string
  basisDisplay: string
  estimated: number
  booked: number
  diff: number
  isDiffHighlight: boolean
  isTotal: boolean
}

const summaryRows = computed<SummaryRow[]>(() => {
  const basisLabel = localBasis.value === 'output' ? '按产量分档' : '按营业收入'
  return [
    {
      label: '安全生产费计提测试',
      basisDisplay: basisLabel,
      estimated: accrualTest.estimated.value,
      booked: accrualTest.booked.value,
      diff: accrualTest.diff.value,
      isDiffHighlight: accrualTest.diffHighlight.value,
      isTotal: true,
    },
  ]
})

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Actions ─────────────────────────────────────────────────────────────────
async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4201 专项储备 / 计提测试 M7-4',
      行业分类: localIndustry.value || '未选择',
      计提基础: localBasis.value === 'output' ? '按产量分档' : '按营业收入',
      应计提: fmtAmount(accrualTest.estimated.value),
      账面计提: fmtAmount(accrualTest.booked.value),
      计提差异: fmtAmount(accrualTest.diff.value),
    }
    const text = await generateAiText({ section: `m7-accrual-test-${section}`, context, existingContent: auditNote.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    auditNote.value = text
    saveAuditNote()
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview() {
  openReviewDialog?.('M7-4-accrual-test', '专项储备计提测试')
}
function saveAuditNote() {
  formData.debouncedSave('M7-4-auditNote', { remark: auditNote.value || null })
}

// ─── 生命周期 ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  await formData.loadData()
  // 从持久化数据恢复本地值
  const responses = formData.allResponses.value
  const getStr = (key: string): string => {
    const r = responses.get(key)
    return r?.remark || ''
  }
  const getNum = (key: string): number => {
    const r = responses.get(key)
    return r?.remark ? Number(r.remark) || 0 : 0
  }

  // 恢复基础选择
  const savedBasis = getStr('M7-4-basis')
  if (savedBasis === 'output' || savedBasis === 'revenue') {
    localBasis.value = savedBasis
    accrualTest.setBasis(savedBasis)
  }

  // 恢复行业/企业名称
  localIndustry.value = getStr('M7-4-industry-category')
  localEntityName.value = getStr('M7-4-entity-name')
  if (localIndustry.value) accrualTest.setIndustryCategory(localIndustry.value)
  if (localEntityName.value) accrualTest.setEntityName(localEntityName.value)

  // 恢复账面计提
  localBooked.value = getNum('M7-4-booked')
  if (localBooked.value) accrualTest.setBooked(localBooked.value)

  // 恢复按收入参数
  localRevenue.value = getNum('M7-4-revenue')
  const savedRate = getNum('M7-4-revenue-rate')
  localRevenueRatePercent.value = savedRate * 100
  if (localRevenue.value) accrualTest.setRevenue(localRevenue.value)
  if (savedRate) accrualTest.setRevenueRate(savedRate)

  // 恢复分档数据
  const tiersStr = getStr('M7-4-tiers')
  if (tiersStr) {
    try {
      const parsed = JSON.parse(tiersStr)
      if (Array.isArray(parsed) && parsed.length > 0) {
        accrualTest.tiers.value = parsed
      }
    } catch { /* ignore parse error */ }
  }

  // 恢复审计说明
  const noteResp = responses.get('M7-4-auditNote')
  if (noteResp?.remark) auditNote.value = noteResp.remark
})
</script>

<style scoped>
.m7-tab-accrual-test { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

/* 蓝色渐变引导区 */
.guide-zone { background: linear-gradient(135deg, #ecf5ff 0%, #d9ecff 100%); border-radius: 8px; padding: 14px 20px; margin-bottom: 16px; }
.guide-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.guide-step { display: flex; align-items: center; gap: 10px; }
.guide-num { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 50%; background: #409eff; color: #fff; font-weight: 700; font-size: var(--wp-font-size, 13px); flex-shrink: 0; }
.guide-text { font-size: var(--wp-font-size, 13px); color: #303133; font-weight: 500; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* 公式列虚线下划线+cursor:help */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }

/* 差异高亮（红色） */
.diff-highlight { color: #f56c6c; font-weight: 700; }

/* 合计行 */
.total-row-label { font-weight: 700; color: #303133; }

/* 卡片 */
.basis-card { margin-bottom: 16px; }
.tier-card { margin-bottom: 16px; }
.revenue-card { margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

/* 9公式汇总 */
.formula-summary { margin-top: 8px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.formula-list-hint { font-size: 12px; color: #909399; }

/* cross_wp_ref 跨底稿引用 */
.cross-wp-links { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; margin-bottom: 16px; }
.cross-wp-label { font-size: 12px; color: #606266; font-weight: 600; }
.cross-wp-desc { font-size: 12px; color: #909399; }

/* 审计说明 */
.audit-note-card { margin-top: 16px; }

/* 编制提示 */
.m7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m7-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m7-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m7-details-tip li { margin-bottom: 4px; line-height: 1.5; }

/* 表格 */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.summary-table .el-table__row:last-child) { background: #f0f9eb !important; font-weight: 600; }
:deep(.summary-table .el-table__row:last-child td) { border-top: 2px solid #67c23a; }
:deep(.tier-table .el-input-number) { width: 100%; }
</style>
