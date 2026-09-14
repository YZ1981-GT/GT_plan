<template>
  <div class="gt-audit-legend">
    <!-- 标题 -->
    <div class="gt-audit-legend__header">
      <h3 class="gt-audit-legend__title">📋 审计标识一览表</h3>
      <el-tag size="small" type="info" effect="plain">A31</el-tag>
    </div>

    <p class="gt-audit-legend__desc">
      以下标识在本项目审计底稿中统一使用，确保复核人员能准确理解底稿内容。
    </p>

    <!-- 标识符号对照表 -->
    <div class="gt-audit-legend__table">
      <div
        v-for="(item, idx) in legendItems"
        :key="idx"
        class="gt-audit-legend__row"
        :style="{ '--delay': idx * 0.04 + 's' }"
      >
        <div class="gt-audit-legend__symbol" :class="'gt-legend-cat--' + item.category">
          {{ item.symbol }}
        </div>
        <div class="gt-audit-legend__info">
          <div class="gt-audit-legend__meaning">{{ item.meaning }}</div>
          <div class="gt-audit-legend__usage">{{ item.usage }}</div>
        </div>
        <div class="gt-audit-legend__category">
          <el-tag size="small" :type="categoryTagType(item.category)" effect="plain" round>
            {{ categoryLabel(item.category) }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 项目自定义标识（可编辑） -->
    <div class="gt-audit-legend__custom" v-if="!readonly">
      <div class="gt-audit-legend__custom-header">
        <span>项目自定义标识</span>
        <el-button size="small" text type="primary" @click="addCustom">+ 新增</el-button>
      </div>
      <div v-if="customItems.length === 0" class="gt-audit-legend__custom-empty">
        暂无自定义标识，点击上方按钮添加
      </div>
      <div v-for="(item, idx) in customItems" :key="'c-' + idx" class="gt-audit-legend__row gt-audit-legend__row--custom">
        <el-input v-model="item.symbol" size="small" style="width: 60px" placeholder="符号" @blur="onSave" />
        <el-input v-model="item.meaning" size="small" style="flex:1" placeholder="含义说明" @blur="onSave" />
        <el-button size="small" text type="danger" @click="removeCustom(idx)">删除</el-button>
      </div>
    </div>

    <!-- 底部说明 -->
    <div class="gt-audit-legend__footer">
      <el-alert type="info" :closable="false" show-icon>
        <template #title>使用说明</template>
        底稿中使用上述标识时，应在标识旁标注对应的底稿索引号，以便复核人员追查。
        如有项目特殊标识，请在"项目自定义标识"区域添加。
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface LegendItem {
  symbol: string
  meaning: string
  usage: string
  category: string
}

const props = defineProps<{
  wpId: string
  projectId: string
  year?: number
  readonly?: boolean
}>()

const emit = defineEmits<{ save: [data: any] }>()

// 标准审计标识（致同统一规范）
const legendItems = ref<LegendItem[]>([
  { symbol: '✓', meaning: '已核对到原始凭证/单据', usage: '抽凭测试', category: 'verify' },
  { symbol: '√', meaning: '已追查到明细账/总账', usage: '账表核对', category: 'verify' },
  { symbol: '⊕', meaning: '已重新计算并验证正确', usage: '数值验算', category: 'compute' },
  { symbol: '⊗', meaning: '重新计算有差异', usage: '差异标记', category: 'compute' },
  { symbol: '△', meaning: '有差异/异常需关注', usage: '复核标记', category: 'review' },
  { symbol: '※', meaning: '参见其他底稿（附索引号）', usage: '交叉索引', category: 'reference' },
  { symbol: 'F', meaning: '脚注说明', usage: '附注引用', category: 'reference' },
  { symbol: 'PBC', meaning: '客户提供（Prepared By Client）', usage: '来源标记', category: 'source' },
  { symbol: 'N/A', meaning: '不适用', usage: '程序裁剪', category: 'status' },
  { symbol: '⟳', meaning: '上期未调整事项（结转）', usage: '期初余额', category: 'status' },
  { symbol: '☐', meaning: '待执行/未完成', usage: '进度跟踪', category: 'status' },
  { symbol: '☑', meaning: '已完成', usage: '进度跟踪', category: 'status' },
  { symbol: 'AJE', meaning: '审计调整分录', usage: '调整标记', category: 'adjustment' },
  { symbol: 'RJE', meaning: '重分类调整分录', usage: '调整标记', category: 'adjustment' },
  { symbol: 'Passed', meaning: '未更正错报（管理层不予调整）', usage: '错报标记', category: 'adjustment' },
])

const customItems = ref<{ symbol: string; meaning: string }[]>([])

function categoryTagType(cat: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    verify: 'success', compute: 'primary', review: 'warning',
    reference: 'info', source: '', status: 'info', adjustment: 'danger',
  }
  return map[cat] || 'info'
}

function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    verify: '核对类', compute: '计算类', review: '复核类',
    reference: '引用类', source: '来源类', status: '状态类', adjustment: '调整类',
  }
  return map[cat] || cat
}

function addCustom() {
  customItems.value.push({ symbol: '', meaning: '' })
}

function removeCustom(idx: number) {
  customItems.value.splice(idx, 1)
  onSave()
}

async function onSave() {
  try {
    await api.post('/api/workpapers/field-overrides', {
      project_id: props.projectId,
      year: props.year || new Date().getFullYear(),
      scope: 'audit_legend',
      item_key: 'custom_items',
      field: 'value',
      value: customItems.value.filter(i => i.symbol || i.meaning),
    })
  } catch { /* 静默 */ }
  emit('save', { custom_items: customItems.value })
}

async function loadCustom() {
  try {
    const data: any = await api.get('/api/workpapers/field-overrides', {
      params: {
        project_id: props.projectId,
        year: props.year || new Date().getFullYear(),
        scope: 'audit_legend',
      },
    })
    const v = data?.custom_items?.value
    if (Array.isArray(v)) {
      customItems.value = v
    }
  } catch { /* 首次无数据正常 */ }
}

onMounted(loadCustom)
</script>

<style scoped>
.gt-audit-legend { padding: 20px; max-width: 800px; }

.gt-audit-legend__header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.gt-audit-legend__title { margin: 0; font-size: 18px; font-weight: 700; }
.gt-audit-legend__desc { color: var(--gt-color-text-secondary); font-size: var(--wp-font-size, 13px); margin-bottom: 20px; }

/* 标识行 */
.gt-audit-legend__table { display: flex; flex-direction: column; gap: 6px; margin-bottom: 24px; }

.gt-audit-legend__row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #eee);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  animation: gt-legend-slide 0.3s ease-out both;
  animation-delay: var(--delay, 0s);
}
.gt-audit-legend__row:hover {
  border-color: var(--gt-purple-light, #d8b8ee);
  box-shadow: 0 3px 12px rgba(75, 45, 119, 0.08);
  transform: translateX(4px);
}

.gt-audit-legend__symbol {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  flex-shrink: 0;
  transition: transform 0.2s;
}
.gt-audit-legend__row:hover .gt-audit-legend__symbol { transform: scale(1.15); }

.gt-legend-cat--verify { background: rgba(103, 194, 58, 0.12); color: #67C23A; }
.gt-legend-cat--compute { background: rgba(75, 45, 119, 0.1); color: var(--gt-purple, #4b2d77); }
.gt-legend-cat--review { background: rgba(230, 162, 60, 0.12); color: #E6A23C; }
.gt-legend-cat--reference { background: rgba(64, 158, 255, 0.1); color: #409EFF; }
.gt-legend-cat--source { background: rgba(144, 147, 153, 0.1); color: #909399; }
.gt-legend-cat--status { background: rgba(144, 147, 153, 0.08); color: #606266; }
.gt-legend-cat--adjustment { background: rgba(245, 108, 108, 0.1); color: #F56C6C; }

.gt-audit-legend__info { flex: 1; min-width: 0; }
.gt-audit-legend__meaning { font-size: 14px; font-weight: 600; color: var(--gt-color-text-primary); }
.gt-audit-legend__usage { font-size: 12px; color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-audit-legend__category { flex-shrink: 0; }

/* 自定义区 */
.gt-audit-legend__custom { margin-bottom: 20px; }
.gt-audit-legend__custom-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; font-size: 14px; font-weight: 600;
}
.gt-audit-legend__custom-empty { color: var(--gt-color-text-tertiary); font-size: var(--wp-font-size, 13px); padding: 12px 0; }
.gt-audit-legend__row--custom { gap: 8px; }

/* Footer */
.gt-audit-legend__footer { margin-top: 16px; }

/* 动画 */
@keyframes gt-legend-slide {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}
</style>
