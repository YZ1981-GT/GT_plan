<template>
  <el-dialog
    :model-value="visible"
    title="减值明细逐项录入"
    width="720px"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div class="k11-row-dialog">
      <!-- 左：分组录入 -->
      <div class="k11-row-form">
        <!-- ① 基础信息 -->
        <el-card shadow="never" class="grp-card">
          <template #header><span class="grp-title">① 基础信息</span></template>
          <el-form label-width="92px" size="small">
            <el-form-item label="资产类别">
              <el-select
                v-model="form.assetCategory"
                filterable
                allow-create
                default-first-option
                placeholder="选择或输入资产类别"
                style="width: 100%"
              >
                <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
            <el-form-item label="减值项目">
              <el-input v-model="form.impairmentItem" placeholder="减值项目名称（可选）" />
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ② 计提/转回 -->
        <el-card shadow="never" class="grp-card">
          <template #header><span class="grp-title">② 本期计提 / 转回</span></template>
          <el-form label-width="92px" size="small">
            <el-form-item label="本期计提">
              <el-input-number v-model="form.currentProvision" :controls="false" :precision="2" style="width: 100%" />
            </el-form-item>
            <el-form-item label="本期转回">
              <el-input-number
                v-if="!isGoodwill"
                v-model="form.currentReversal"
                :controls="false"
                :precision="2"
                style="width: 100%"
              />
              <span v-else class="goodwill-hint">商誉减值不可转回（CAS8）</span>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- ③ 源底稿核对 -->
        <el-card shadow="never" class="grp-card">
          <template #header><span class="grp-title">③ 源底稿核对</span></template>
          <el-form label-width="92px" size="small">
            <el-form-item label="来源底稿">
              <el-input v-model="form.sourceWp" placeholder="如 F2/H1/I1/I3" />
            </el-form-item>
            <el-form-item label="源底稿计提">
              <el-input-number v-model="form.sourceAmount" :controls="false" :precision="2" style="width: 100%" />
            </el-form-item>
            <el-form-item label="凭证">
              <el-input v-model="form.voucherRef" placeholder="凭证编号/抽查" />
            </el-form-item>
            <el-form-item label="核查结论">
              <el-input v-model="form.conclusion" type="textarea" :autosize="{ minRows: 2 }" placeholder="核查结论" />
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <!-- 右：实时分析面板 -->
      <div class="k11-row-analysis">
        <div class="ana-title">实时分析</div>
        <div class="ana-item">
          <span class="ana-label">本期发生额</span>
          <span class="ana-value">{{ fmtNum(occurrence) }}</span>
          <span class="ana-formula">= 计提 − 转回</span>
        </div>
        <div class="ana-item">
          <span class="ana-label">差异</span>
          <span class="ana-value" :class="{ warn: Math.abs(variance) >= 0.01 }">{{ fmtNum(variance) }}</span>
          <span class="ana-formula">= 发生额 − 源底稿计提</span>
        </div>
        <el-alert
          v-if="isGoodwill"
          type="warning"
          :closable="false"
          show-icon
          title="商誉减值不可转回（CAS8），转回列已锁定为 0"
          style="margin-top: 10px"
        />
        <el-alert
          v-if="Math.abs(variance) >= 0.01"
          type="error"
          :closable="false"
          show-icon
          :title="`与源底稿存在差异 ${fmtNum(variance)}，请核实来源或分类`"
          style="margin-top: 10px"
        />
        <el-alert
          v-else-if="form.sourceAmount > 0"
          type="success"
          :closable="false"
          show-icon
          title="与源底稿计提一致"
          style="margin-top: 10px"
        />
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * K11DetailRowDialog.vue — K11-2 减值明细逐项引导式录入
 * 分组卡片（基础/计提转回/源底稿核对）+ 右侧实时分析（发生额/差异/商誉提示）
 */
import { ref, computed, watch } from 'vue'

interface RowLike {
  rowKey: string
  assetCategory: string
  impairmentItem: string
  currentProvision: number
  currentReversal: number
  sourceWp: string
  sourceAmount: number
  voucherRef: string
  conclusion: string
}

const props = defineProps<{
  visible: boolean
  row: RowLike | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'save', rowKey: string, patch: Partial<RowLike>): void
}>()

const CATEGORY_OPTIONS = [
  '存货跌价准备', '固定资产减值准备', '无形资产减值准备', '开发支出减值准备',
  '商誉减值准备', '在建工程减值准备', '长期股权投资减值准备', '工程物资减值准备',
  '使用权资产减值准备', '投资性房地产减值准备', '其他资产减值损失',
]

const form = ref<RowLike>({
  rowKey: '',
  assetCategory: '',
  impairmentItem: '',
  currentProvision: 0,
  currentReversal: 0,
  sourceWp: '',
  sourceAmount: 0,
  voucherRef: '',
  conclusion: '',
})

watch(
  () => [props.visible, props.row],
  () => {
    if (props.visible && props.row) {
      form.value = { ...props.row }
    }
  },
  { immediate: true },
)

const isGoodwill = computed(() => (form.value.assetCategory || '').includes('商誉'))
const occurrence = computed(() => {
  const reversal = isGoodwill.value ? 0 : Number(form.value.currentReversal || 0)
  return Number(form.value.currentProvision || 0) - reversal
})
const variance = computed(() => occurrence.value - Number(form.value.sourceAmount || 0))

function handleSave(): void {
  const patch: Partial<RowLike> = {
    assetCategory: form.value.assetCategory,
    impairmentItem: form.value.impairmentItem,
    currentProvision: Number(form.value.currentProvision || 0),
    currentReversal: isGoodwill.value ? 0 : Number(form.value.currentReversal || 0),
    sourceWp: form.value.sourceWp,
    sourceAmount: Number(form.value.sourceAmount || 0),
    voucherRef: form.value.voucherRef,
    conclusion: form.value.conclusion,
  }
  emit('save', form.value.rowKey, patch)
  emit('update:visible', false)
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  if (v === 0) return '0.00'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k11-row-dialog { display: flex; gap: 16px; }
.k11-row-form { flex: 1; min-width: 0; }
.k11-row-analysis {
  width: 220px; flex-shrink: 0;
  background: #f8fafc; border: 1px solid #ebeef5; border-radius: 8px; padding: 12px;
}
.grp-card { margin-bottom: 12px; }
.grp-card :deep(.el-card__header) { padding: 8px 14px; }
.grp-title { font-weight: 600; font-size: 13px; color: #303133; }
.goodwill-hint { color: #e6a23c; font-size: 12px; }
.ana-title { font-weight: 600; font-size: 13px; color: #303133; margin-bottom: 10px; }
.ana-item { display: flex; flex-direction: column; margin-bottom: 10px; }
.ana-label { font-size: 12px; color: #909399; }
.ana-value { font-size: 16px; font-weight: 600; font-family: 'JetBrains Mono', monospace; color: #303133; }
.ana-value.warn { color: #f56c6c; }
.ana-formula { font-size: 11px; color: #c0c4cc; }
</style>
