<template>
  <section class="g6-ecl-status-panel" data-testid="g6-ecl-sheet-status">
    <header class="status-head">
      <h4>G6 ECL 编制进度</h4>
      <p>数据、结论与关键质量闸门（基于已保存 checklist）</p>
    </header>
    <div class="status-grid">
      <div v-for="item in items" :key="item.code" class="status-card" :class="item.tone">
        <div class="code">{{ item.code }}</div>
        <div class="label">{{ item.label }}</div>
        <div class="flags">
          <el-tag size="small" :type="item.hasData ? 'success' : 'info'" effect="plain">
            {{ item.hasData ? '已有数据' : '未填' }}
          </el-tag>
          <el-tag
            v-if="item.hasData"
            size="small"
            :type="item.conclusionComplete ? 'success' : 'warning'"
            effect="plain"
          >
            结论 {{ item.conclusionComplete ? '完成' : '待补' }}
          </el-tag>
          <el-tag
            v-if="item.gate != null"
            size="small"
            :type="item.gate ? 'success' : 'warning'"
            effect="plain"
          >
            闸门 {{ item.gate ? '就绪' : '待办' }}
          </el-tag>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { evaluateG6EclSuiteStatus } from '../composables/g6SuiteStatus'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
}>()

const items = computed(() => evaluateG6EclSuiteStatus(props.allResponses))
</script>

<style scoped>
.g6-ecl-status-panel {
  margin: 12px 0 16px;
  padding: 12px 14px;
  border: 1px solid #e8ecf2;
  border-radius: 8px;
  background: #fafbfc;
}
.status-head h4 { margin: 0; font-size: 13px; font-weight: 600; color: #1f2a37; }
.status-head p { margin: 4px 0 0; font-size: 12px; color: #86909c; }
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.status-card {
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #eef1f5;
  background: #fff;
}
.status-card.ok { border-color: #b7eb8f; background: #f6ffed; }
.status-card.warn { border-color: #ffe58f; background: #fffbe6; }
.status-card.idle { opacity: 0.85; }
.code { font-size: 12px; font-weight: 700; color: #1f2a37; }
.label { font-size: 12px; color: #4e5969; margin: 2px 0 6px; }
.flags { display: flex; flex-wrap: wrap; gap: 4px; }
</style>
