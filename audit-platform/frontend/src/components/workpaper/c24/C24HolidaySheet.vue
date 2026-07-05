<template>
  <div class="c24-holiday-sheet">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>假期清单：维护审计期间的法定假期日期列表，用于异常分录"假期录入"规则判断。</p>
    </div>

    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">假期日历</span>
        <el-button v-if="!isReadonly" type="primary" size="small" @click="$emit('add-holiday')">+ 新增假期</el-button>
      </div>

      <el-table :data="holidays" border size="small" class="c24-table" empty-text="暂无假期记录">
        <el-table-column label="序号" width="60" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="日期" min-width="120">
          <template #default="{ row, $index }">
            <el-date-picker
              :model-value="row.date"
              :disabled="isReadonly"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%;"
              @change="$emit('update-holiday', $index, 'date', $event)"
            />
          </template>
        </el-table-column>
        <el-table-column label="假期名称" min-width="160">
          <template #default="{ row, $index }">
            <el-input :model-value="row.name" :disabled="isReadonly" size="small" placeholder="如：元旦/春节/清明" @input="$emit('update-holiday', $index, 'name', $event)" />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button type="danger" size="small" link @click="$emit('remove-holiday', $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
export interface HolidayRow {
  date: string
  name: string
}

defineProps<{
  holidays: HolidayRow[]
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'add-holiday'): void
  (e: 'remove-holiday', index: number): void
  (e: 'update-holiday', index: number, field: 'date' | 'name', value: string): void
}>()
</script>

<style scoped>
.c24-holiday-sheet { font-size: 13px; }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: 13px; color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: 13px; }
</style>
