<template>
  <div class="k7-tab-check">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性与义务：</b>政府补助/递延收益确认完整，与资产相关或与收益相关分类判断恰当；</li>
        <li><b>计价和分摊：</b>补助确认时点、分摊方法符合 CAS16，计量准确；</li>
        <li><b>列报与披露：</b>政府补助及递延收益按准则恰当列报披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K7-5 递延收益检查表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReviewDialog?.('K7-5', '检查表K7-5')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>逐项检查政府补助确认与分摊的合规性：补助真实性、批文合规、相关类型判断正确性、分摊方法适当性、计入科目正确性。每项标记"合规/不合规/不适用"。</p>
    </div>

    <!-- ═══ 不合规摘要（红色） ═══ -->
    <div v-if="check.nonComplianceSummary.value.hasNonCompliant" class="noncompliant-alert">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          存在 {{ check.nonComplianceSummary.value.count }} 项不合规，请关注
        </template>
        <template #default>
          <ul class="noncompliant-list">
            <li v-for="item in check.nonComplianceSummary.value.items" :key="item.id">
              {{ item.checkPoint }}：{{ item.detail }}
            </li>
          </ul>
        </template>
      </el-alert>
    </div>

    <!-- ═══ 进度指示 ═══ -->
    <div class="progress-bar">
      <span>检查进度：{{ check.getProgress() }}%</span>
      <el-progress :percentage="check.getProgress()" :stroke-width="6" :show-text="false" style="width:200px" />
    </div>

    <!-- ═══ 检查表 ═══ -->
    <el-table
      :data="check.checkItems.value"
      border
      size="small"
      style="width: 100%"
      :row-class-name="checkRowClass"
    >
      <el-table-column label="序号" width="55" align="center">
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="检查项" min-width="130">
        <template #default="{ row }">
          <span class="check-point">{{ row.checkPoint }}</span>
        </template>
      </el-table-column>
      <el-table-column label="检查内容/标准" min-width="260">
        <template #default="{ row }">
          <span class="check-desc">{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结果" width="200" align="center">
        <template #default="{ row }">
          <el-radio-group
            :model-value="row.result"
            :disabled="isReadonly"
            size="small"
            @change="(v: string) => check.updateResult(row.id, v as any)"
          >
            <el-radio-button value="合规">合规</el-radio-button>
            <el-radio-button value="不合规">不合规</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
      <el-table-column label="抽凭" width="70" align="center">
        <template #default="{ row }">
          <el-button size="small" link :disabled="isReadonly" @click="handleVoucher(row.id)">
            {{ row.voucherRef ? '✓' : '抽' }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="📎OCR" width="70" align="center">
        <template #default="{ row }">
          <el-button size="small" link :disabled="isReadonly" @click="handleOcr(row.id)">
            {{ row.ocrRef ? '✓' : '📎' }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注说明"
            @blur="(e: any) => check.updateRemark(row.id, e.target.value)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>补助真实性：核对拨款文件、银行到账记录，金额一致</li>
        <li>批文合规：政府文件来源合法、拨款条件已满足</li>
        <li>相关类型判断：按CAS16及批文用途判定"与资产/与收益相关"</li>
        <li>分摊方法：匹配资产寿命或费用期间</li>
        <li>计入科目：与日常活动→其他收益(6117)；无关→营业外收入(6301)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabDeferredCheck.vue — K7-5 递延收益检查表
 * Per-item radio (合规/不合规/不适用) + 行级抽凭button + 行级OCR📎 + red summary
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.5
 * Requirements: 5.1-5.3
 */
import { inject, toRef, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useK7Check } from '../../composables/useK7Check'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string, label?: string) => void>('openReviewDialog', undefined)

// 父组件模板绑定会自动解包顶层 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

// ─── Composable ──────────────────────────────────────────────────────────────

const check = useK7Check({
  allResponses: allResponsesRef,
  saveResponse: (field: string, value: any) => { emit('save', field, value) },
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAiGenerate() {
  emit('save', 'K7-5-ai-trigger', { remark: 'generate' })
}

function handleVoucher(itemId: string) {
  // 行级抽凭 — 触发抽凭引擎Dialog（由父级provide或EventBus处理）
  check.setVoucherRef(itemId, `V-${Date.now().toString(36)}`)
}

function handleOcr(itemId: string) {
  // 行级OCR — 触发批文OCR上传
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.jpg,.jpeg,.png'
  input.onchange = (e: any) => {
    const file = e.target?.files?.[0]
    if (file) {
      check.setOcrRef(itemId, file.name)
    }
  }
  input.click()
}

// ─── Row class ───────────────────────────────────────────────────────────────

function checkRowClass({ row }: { row: any }): string {
  if (row.result === '不合规') return 'noncompliant-row'
  if (row.result === '合规') return 'compliant-row'
  return ''
}
</script>

<style scoped>
.k7-tab-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.noncompliant-alert { margin-bottom: 12px; }
.noncompliant-list { margin: 4px 0 0; padding-left: 16px; font-size: 12px; }
.progress-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px); color: #606266; }
.check-point { font-weight: 600; color: #303133; }
.check-desc { font-size: 12px; color: #606266; line-height: 1.5; }
:deep(.noncompliant-row) { background-color: #fef0f0 !important; }
:deep(.compliant-row) { background-color: #f0f9eb !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k7-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
