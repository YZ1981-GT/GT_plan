<template>
<div class="d5-disclosure">
    <!-- 版本切换（上市公司版 / 国企版） -->
    <div class="variant-toolbar" v-if="showListed && showSoe">
      <el-segmented
        v-model="activeVariant"
        :options="variantOptions"
        size="small"
      />
    </div>

    <!-- ═══════════════ 上市公司版 ═══════════════ -->
    <template v-if="activeVariant === 'listed' && showListed">
      <div v-for="section in listedSections" :key="section.sectionKey" class="disclosure-card">
        <h4 class="section-title">{{ section.label }}</h4>

        <!-- Section 1: 分类表 -->
        <template v-if="section.sectionKey === 'listed-classification'">
          <el-table :data="section.rows" size="small" border>
            <el-table-column prop="label" label="项目" width="240">
              <template #default="{ row }">
                <span :class="{ 'oci-label': row.rowId === 'listed-cls-oci' }">
                  {{ row.label }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="期末数" width="140" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell" title="来源：D5-1审定表">
                  {{ fmtAmount(row.endAmount) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="期初数" width="140" align="right">
              <template #default="{ row }">
                <span class="cross-sheet-cell" title="来源：D5-1审定表">
                  {{ fmtAmount(row.priorAmount) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <!-- 说明 -->
          <div class="note-block">
            <div class="note-label">说明：</div>
            <el-input
              v-model="noteTexts['listed-1']"
              type="textarea"
              :rows="2"
              :disabled="isReadonly"
              placeholder="对应收款项融资分类的补充说明..."
            />
          </div>
          <!-- 编制提示 -->
          <details class="guidance-hint">
            <summary>📋 编制提示</summary>
            <div class="hint-content">
              按CAS22金融工具确认和计量，以公允价值计量且其变动计入其他综合收益的金融资产（FVOCI）
              应在附注中披露账面价值分类构成。
            </div>
          </details>
        </template>

        <!-- Section 2: 减值准备变动 -->
        <template v-if="section.sectionKey === 'listed-impairment'">
          <el-table :data="impairmentRows" size="small" border>
            <el-table-column label="项目" width="140">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.itemName"
                  size="small"
                  placeholder="项目名称"
                  @change="(val: string) => onImpairmentCellChange(row.rowId, 'itemName', val)"
                />
                <span v-else>{{ row.itemName }}</span>
              </template>
            </el-table-column>
            <el-table-column label="上年末" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.priorEnd"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'priorEnd', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.priorEnd) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期计提" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.provision"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'provision', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.provision) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="转回" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.reversal"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'reversal', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.reversal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="核销" width="110" align="right">
              <template #default="{ row }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.writeOff"
                  :controls="false"
                  size="small"
                  style="width:100%"
                  @change="(val: number) => onImpairmentCellChange(row.rowId, 'writeOff', val ?? 0)"
                />
                <span v-else>{{ fmtAmount(row.writeOff) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末" width="110" align="right">
              <template #default="{ row }">
                <span class="auto-calc">{{ fmtAmount(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="impairmentRemoveRow(row.rowId)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button
            size="small"
            :disabled="isReadonly"
            style="margin-top: 8px"
            @click="impairmentAddRow"
          >
            添加行
          </el-button>
          <!-- 说明 -->
          <div class="note-block">
            <div class="note-label">说明：</div>
            <el-input
              v-model="noteTexts['listed-2']"
              type="textarea"
              :rows="2"
              :disabled="isReadonly"
              placeholder="对减值准备变动的补充说明..."
            />
          </div>
          <!-- 编制提示 -->
          <details class="guidance-hint">
            <summary>📋 编制提示</summary>
            <div class="hint-content">
              公式：期末余额 = 上年末 + 本期计提 - 收回转回 - 核销。
              按CAS22/ECL模型确认减值准备，披露变动明细。
            </div>
          </details>
        </template>

        <!-- Section 3: 说明 -->
        <template v-if="section.sectionKey === 'listed-notes'">
          <div class="note-block">
            <div class="note-label">披露说明：</div>
            <el-input
              v-model="noteTexts['listed-3']"
              type="textarea"
              :rows="3"
              :disabled="isReadonly"
              placeholder="其他需要披露的说明事项..."
            />
          </div>
          <!-- 编制提示 -->
          <details class="guidance-hint">
            <summary>📋 编制提示</summary>
            <div class="hint-content">
              根据准则要求，需补充披露金融资产风险敞口、信用风险最大暴露等信息。
              说明内容将双向回写至附注模块。
            </div>
          </details>
        </template>
      </div>
    </template>

    <!-- ═══════════════ 国企版 ═══════════════ -->
    <template v-if="activeVariant === 'soe' && showSoe">
      <div v-for="section in soeSections" :key="section.sectionKey" class="disclosure-card">
        <h4 class="section-title">{{ section.label }}</h4>

        <el-table :data="section.rows" size="small" border>
          <el-table-column prop="label" label="项目" width="200" />
          <el-table-column label="期末数" width="140" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell" title="来源：D5-1审定表">
                {{ fmtAmount(row.endAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" width="140" align="right">
            <template #default="{ row }">
              <span class="cross-sheet-cell" title="来源：D5-1审定表">
                {{ fmtAmount(row.priorAmount) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <!-- 合计行 -->
        <div v-if="section.totalRow" class="total-summary">
          合计 — 期末：{{ fmtAmount(section.totalRow.endAmount) }}，期初：{{ fmtAmount(section.totalRow.priorAmount) }}
        </div>
        <!-- 说明 -->
        <div class="note-block">
          <div class="note-label">说明：</div>
          <el-input
            v-model="noteTexts['soe-1']"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="国企版分类披露补充说明..."
          />
        </div>
        <!-- 编制提示 -->
        <details class="guidance-hint">
          <summary>📋 编制提示</summary>
          <div class="hint-content">
            国企版仅需披露分类信息。根据《国有企业财务决算报告附注》要求，
            披露应收款项融资的分类构成及期初期末余额变动情况。
          </div>
        </details>
      </div>
    </template>
</div>
</template>

<script setup lang="ts">
/**
 * D5TabDisclosure.vue — D5 附注披露
 *
 * el-segmented 切换（上市公司版 | 国企版）
 * 上市公司版：3子节卡片（分类/减值变动/说明）
 * 国企版：1子节卡片（分类）
 * 跨sheet浅蓝色取数 + tooltip来源
 * 减值准备变动：动态行 + 公式（期末=上年末+计提-转回-核销）
 * 按applicable_standards自动显示/隐藏版本
 *
 * Task: 17.1
 * Requirements: 8.1-8.8
 */
import { ref, computed, type Ref } from 'vue'
import { useD5Disclosure } from '../composables/useD5Disclosure'
import type { useD5CrossSheet } from '../composables/useD5CrossSheet'
import type { ChecklistResponse } from '../composables/useD5FormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD5CrossSheet>
}>()

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  listedSections,
  soeSections,
  showListed,
  showSoe,
  activeVariant,
  impairmentRows,
  impairmentAddRow,
  impairmentRemoveRow,
  noteTexts,
} = useD5Disclosure({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  crossSheet: props.crossSheet,
})

// ─── Variant Options ─────────────────────────────────────────────────────────

const variantOptions = computed(() => {
  const opts = []
  if (showListed.value) opts.push({ label: '上市公司版', value: 'listed' })
  if (showSoe.value) opts.push({ label: '国企版', value: 'soe' })
  return opts
})

// ─── Impairment Cell Editing ─────────────────────────────────────────────────

function onImpairmentCellChange(rowId: string, field: string, value: any) {
  const idx = impairmentRows.value.findIndex(r => r.rowId === rowId)
  if (idx === -1) return
  const row = { ...impairmentRows.value[idx] }
  ;(row as any)[field] = value
  const newRows = [...impairmentRows.value]
  newRows[idx] = row
  impairmentRows.value = newRows
}

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d5-disclosure {
  padding: 16px;
}

.mode-toolbar {
  margin-bottom: 12px;
}

.variant-toolbar {
  margin-bottom: 16px;
}

.disclosure-card {
  margin-bottom: 24px;
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}

.cross-sheet-cell {
  background: #ecf5ff;
  padding: 2px 6px;
  border-radius: 2px;
  cursor: help;
}

.oci-label {
  color: #409eff;
}

.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  color: #909399;
}

.total-summary {
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 4px;
  margin-top: 8px;
  font-size: 13px;
  font-weight: 600;
}

.note-block {
  margin-top: 12px;
}

.note-label {
  font-size: 13px;
  color: #606266;
  margin-bottom: 6px;
}

.guidance-hint {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}

.guidance-hint summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #409eff;
}

.guidance-hint .hint-content {
  padding: 8px 12px 12px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

</style>
