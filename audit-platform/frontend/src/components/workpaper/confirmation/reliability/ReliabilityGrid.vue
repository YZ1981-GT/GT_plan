<template>
  <div class="reliability-grid">
    <!-- 顶部精简说明 -->
    <div class="reliability-grid__header-note">
      <el-icon :size="14"><InfoFilled /></el-icon>
      <span>{{ RELIABILITY_HEADER_NOTE }}</span>
    </div>

    <!-- 工具栏 -->
    <div class="reliability-grid__toolbar">
      <el-button-group>
        <el-button size="small" type="primary" :icon="Plus" :disabled="readonly" @click="$emit('add')">
          新增
        </el-button>
        <el-button size="small" type="danger" :icon="Delete" :disabled="readonly || !selectedIds.length" @click="$emit('delete', selectedIds)">
          删除
        </el-button>
        <el-button size="small" :icon="Download" :disabled="readonly" @click="$emit('import-d01')">
          从 D0-1 带入电子回函
        </el-button>
      </el-button-group>
      <el-button-group>
        <el-button size="small" :disabled="readonly" @click="$emit('import-excel')">
          导入
        </el-button>
        <el-button size="small" @click="$emit('export-template')">
          导出模板
        </el-button>
        <el-button size="small" @click="$emit('export-data')">
          导出数据
        </el-button>
      </el-button-group>
      <div class="reliability-grid__toolbar-right">
        <el-button size="small" type="success" :disabled="readonly || !isDirty" @click="$emit('save')">
          保存
        </el-button>
      </div>
    </div>

    <!-- 网格表 -->
    <el-table
      ref="tableRef"
      :data="rows"
      border
      stripe
      size="small"
      highlight-current-row
      max-height="560"
      :row-class-name="getRowClassName"
      @selection-change="handleSelectionChange"
    >
      <el-table-column v-if="!readonly" type="selection" width="35" fixed="left" />

      <!-- ═══ 基本信息组 ═══ -->
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed="left" />
      <el-table-column label="函证索引号" prop="confirm_index" width="110" fixed="left">
        <template #default="{ row }">
          <template v-if="!readonly">
            <el-input
              :model-value="row.confirm_index"
              size="small"
              placeholder="D0-"
              @change="(val: string) => $emit('update', row._row_id, 'confirm_index', val)"
            />
          </template>
          <span v-else class="reliability-grid__link" @click="$emit('jump-d01', row.confirm_index)">
            {{ row.confirm_index || '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="被询证单位" prop="entity_name" width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.entity_name"
            size="small"
            @change="(val: string) => $emit('update', row._row_id, 'entity_name', val)"
          />
          <span v-else>{{ row.entity_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回函方式" prop="reply_method" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.reply_method"
            size="small"
            placeholder="选择"
            @change="(val: string) => $emit('update', row._row_id, 'reply_method', val)"
          >
            <el-option value="传真" label="传真" />
            <el-option value="电子邮件" label="电子邮件" />
          </el-select>
          <template v-else>
            <el-tag v-if="row.reply_method" size="small" type="info">{{ row.reply_method }}</el-tag>
            <span v-else>—</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="回函日期" prop="reply_date" width="100" align="center">
        <template #default="{ row }">
          <el-date-picker
            v-if="!readonly"
            :model-value="row.reply_date"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @change="(val: string) => $emit('update', row._row_id, 'reply_date', val)"
          />
          <span v-else>{{ row.reply_date || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="寄回原件" prop="original_returned" width="80" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.original_returned"
            size="small"
            @change="(val: string) => $emit('update', row._row_id, 'original_returned', val)"
          >
            <el-option value="是" label="是" />
            <el-option value="否" label="否" />
          </el-select>
          <el-tag v-else :type="row.original_returned === '是' ? 'success' : 'info'" size="small">
            {{ row.original_returned || '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- ═══ 验证组（条件列：寄回原件=否 展开，=是 灰掉） ═══ -->
      <el-table-column label="身份已确认" width="90" align="center">
        <template #header>
          <span>身份已确认</span>
          <el-tooltip placement="top">
            <template #content>
              <div class="reliability-grid__tooltip-content">
                <strong>{{ tooltipMap['注1']?.title }}</strong>
                <ul>
                  <li v-for="(item, idx) in tooltipMap['注1']?.items" :key="idx">{{ item }}</li>
                </ul>
              </div>
            </template>
            <el-icon :size="12" class="reliability-grid__tooltip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-checkbox
              v-if="!readonly"
              :model-value="row.identity_verified"
              @change="(val: boolean) => $emit('update', row._row_id, 'identity_verified', val)"
            />
            <el-icon v-else-if="row.identity_verified" color="var(--el-color-success)"><Select /></el-icon>
            <span v-else class="reliability-grid__empty">—</span>
          </template>
          <span v-else class="reliability-grid__disabled">免验证</span>
        </template>
      </el-table-column>

      <el-table-column label="确认方式" prop="identity_method" width="110">
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-select
              v-if="!readonly"
              :model-value="row.identity_method"
              size="small"
              clearable
              placeholder="选择方式"
              @change="(val: string) => $emit('update', row._row_id, 'identity_method', val)"
            >
              <el-option value="电话确认" label="电话确认" />
              <el-option value="邮件确认" label="邮件确认" />
              <el-option value="见面确认" label="见面确认" />
              <el-option value="系统确认" label="系统确认" />
            </el-select>
            <span v-else>{{ row.identity_method || '—' }}</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column label="邮箱已验证" width="90" align="center">
        <template #header>
          <span>邮箱已验证</span>
          <el-tooltip placement="top" :width="360">
            <template #content>
              <div class="reliability-grid__tooltip-content">
                <strong>{{ tooltipMap['注2']?.title }}</strong>
                <ul>
                  <li v-for="(item, idx) in tooltipMap['注2']?.items" :key="idx">{{ item }}</li>
                </ul>
                <a
                  v-if="tooltipMap['注2']?.link"
                  :href="tooltipMap['注2'].link.url"
                  target="_blank"
                  class="reliability-grid__tooltip-link"
                >
                  {{ tooltipMap['注2'].link.label }} ↗
                </a>
              </div>
            </template>
            <el-icon :size="12" class="reliability-grid__tooltip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-checkbox
              v-if="!readonly"
              :model-value="row.email_verified"
              @change="(val: boolean) => $emit('update', row._row_id, 'email_verified', val)"
            />
            <el-icon v-else-if="row.email_verified" color="var(--el-color-success)"><Select /></el-icon>
            <span v-else class="reliability-grid__empty">—</span>
          </template>
          <span v-else class="reliability-grid__disabled">免验证</span>
        </template>
      </el-table-column>

      <el-table-column label="邮箱域名" prop="email_domain" width="120">
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-input
              v-if="!readonly"
              :model-value="row.email_domain"
              size="small"
              placeholder="如 @company.com"
              @change="(val: string) => $emit('update', row._row_id, 'email_domain', val)"
            />
            <span v-else>{{ row.email_domain || '—' }}</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column label="已致电" prop="phone_called" width="70" align="center">
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-checkbox
              v-if="!readonly"
              :model-value="row.phone_called"
              @change="(val: boolean) => $emit('update', row._row_id, 'phone_called', val)"
            />
            <el-icon v-else-if="row.phone_called" color="var(--el-color-success)"><Select /></el-icon>
            <span v-else class="reliability-grid__empty">—</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column label="电话来源" prop="phone_source" width="110">
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-input
              v-if="!readonly"
              :model-value="row.phone_source"
              size="small"
              placeholder="工商/官网/独立来源"
              @change="(val: string) => $emit('update', row._row_id, 'phone_source', val)"
            />
            <span v-else>{{ row.phone_source || '—' }}</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <el-table-column label="验证备注" prop="reliability_note" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="!isVerificationDisabled(row)">
            <el-input
              v-if="!readonly"
              :model-value="row.reliability_note"
              size="small"
              placeholder="验证说明"
              @change="(val: string) => $emit('update', row._row_id, 'reliability_note', val)"
            />
            <span v-else>{{ row.reliability_note || '—' }}</span>
          </template>
          <span v-else class="reliability-grid__disabled">—</span>
        </template>
      </el-table-column>

      <!-- ═══ 结论组 ═══ -->
      <el-table-column label="信息可靠性" width="120" align="center">
        <template #header>
          <span>信息可靠性</span>
          <el-tooltip placement="top">
            <template #content>
              <div class="reliability-grid__tooltip-content">
                <strong>{{ tooltipMap['注3']?.title }}</strong>
                <ul>
                  <li v-for="(item, idx) in tooltipMap['注3']?.items" :key="idx">{{ item }}</li>
                </ul>
              </div>
            </template>
            <el-icon :size="12" class="reliability-grid__tooltip-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.conclusion_status"
            size="small"
            clearable
            placeholder="选择结论"
            :disabled="isVerificationDisabled(row)"
            @change="(val: string) => $emit('update', row._row_id, 'conclusion_status', val)"
          >
            <el-option value="可靠" label="可靠" />
            <el-option value="部分可靠需补充" label="部分可靠需补充" />
            <el-option value="不可靠" label="不可靠" />
          </el-select>
          <template v-else>
            <el-tag
              v-if="row.conclusion_status"
              size="small"
              :type="conclusionTagType(row.conclusion_status)"
            >
              {{ row.conclusion_status }}
            </el-tag>
            <span v-else-if="isVerificationDisabled(row)" class="reliability-grid__disabled">免验证</span>
            <span v-else class="reliability-grid__empty">未评定</span>
          </template>
        </template>
      </el-table-column>

      <!-- 来源标识 -->
      <el-table-column label="来源" width="60" align="center">
        <template #default="{ row }">
          <el-tag v-if="row._source === 'auto'" size="small" type="primary" effect="plain">
            自动
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus, Delete, Download, InfoFilled, QuestionFilled, Select } from '@element-plus/icons-vue'
import type { ReliabilityRow } from './reliabilityTypes'
import { FIELD_TOOLTIPS_D07, RELIABILITY_HEADER_NOTE } from './reliabilityNotes'

const props = defineProps<{
  rows: ReliabilityRow[]
  readonly: boolean
  isDirty: boolean
  isVerificationDisabled: (row: ReliabilityRow) => boolean
  getRowQualityStatus: (row: ReliabilityRow) => 'ok' | 'warning' | 'danger'
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete', ids: string[]): void
  (e: 'save'): void
  (e: 'update', rowId: string, field: string, value: any): void
  (e: 'import-d01'): void
  (e: 'import-excel'): void
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'jump-d01', confirmIndex: string): void
}>()

const tableRef = ref()
const selectedIds = ref<string[]>([])

// ─── Tooltip 映射 ────────────────────────────────────────────────────────────

const tooltipMap = computed(() => {
  const map: Record<string, typeof FIELD_TOOLTIPS_D07[0]> = {}
  for (const t of FIELD_TOOLTIPS_D07) {
    map[t.id] = t
  }
  return map
})

// ─── Selection ───────────────────────────────────────────────────────────────

function handleSelectionChange(selection: ReliabilityRow[]) {
  selectedIds.value = selection.map((r) => r._row_id!).filter(Boolean)
}

// ─── 行样式（质量红线） ──────────────────────────────────────────────────────

function getRowClassName({ row }: { row: ReliabilityRow }) {
  const status = props.getRowQualityStatus(row)
  if (status === 'danger') return 'reliability-grid__row--danger'
  if (status === 'warning') return 'reliability-grid__row--warning'
  return ''
}

// ─── 结论标签颜色 ────────────────────────────────────────────────────────────

function conclusionTagType(status: string): string {
  if (status === '可靠') return 'success'
  if (status === '部分可靠需补充') return 'warning'
  if (status === '不可靠') return 'danger'
  return 'info'
}
</script>

<style scoped>
.reliability-grid__header-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--el-color-info-light-9);
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: var(--el-text-color-regular);
}

.reliability-grid__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.reliability-grid__toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.reliability-grid__link {
  color: var(--el-color-primary);
  cursor: pointer;
  text-decoration: underline;
}

.reliability-grid__disabled {
  color: var(--el-text-color-disabled);
  font-size: 12px;
  font-style: italic;
}

.reliability-grid__empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.reliability-grid__tooltip-icon {
  margin-left: 2px;
  cursor: help;
  color: var(--el-color-info);
}

.reliability-grid__tooltip-content {
  max-width: 340px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.reliability-grid__tooltip-content ul {
  margin: 6px 0;
  padding-left: 16px;
}

.reliability-grid__tooltip-content li {
  margin-bottom: 4px;
}

.reliability-grid__tooltip-link {
  display: block;
  margin-top: 8px;
  color: var(--el-color-primary);
  text-decoration: none;
}

:deep(.reliability-grid__row--danger) {
  background-color: var(--el-color-danger-light-9) !important;
}

:deep(.reliability-grid__row--warning) {
  background-color: var(--el-color-warning-light-9) !important;
}

/* 表头折行显示（列名过长时换行而非截断） */
:deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
  padding: 4px 2px;
}

:deep(.el-table__body td .cell) {
  font-size: 12px;
}
</style>
