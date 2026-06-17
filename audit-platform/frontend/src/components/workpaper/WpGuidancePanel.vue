<script setup lang="ts">
/**
 * WpGuidancePanel — 底稿编制说明面板
 *
 * 展示底稿对应的编制说明数据（公式、规则、参数定义）。
 * 数据来源：render-config 响应中的 guidance 字段。
 * 用于 A3-8 商誉减值、A4-1 经营分部、A5 现金流等需要准则/公式参考的底稿。
 */
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

interface GuidanceParameter {
  symbol: string
  name: string
  description: string
}

interface GuidanceItem {
  seq: number
  text: string
}

interface SubFormula {
  label: string
  formula: string
}

interface GuidanceSection {
  id: string
  title: string
  collapsed: boolean
  formula?: string
  sub_formulas?: SubFormula[]
  parameters?: GuidanceParameter[]
  items?: GuidanceItem[]
}

interface GuidanceData {
  wp_codes: string[]
  title: string
  sections: GuidanceSection[]
}

const props = defineProps<{
  projectId: string
  wpId: string
}>()

const guidanceData = ref<GuidanceData | null>(null)
const loading = ref(false)
const activeSections = ref<string[]>([])

const hasGuidance = computed(() => !!guidanceData.value?.sections?.length)

async function loadGuidance() {
  if (!props.wpId) return
  loading.value = true
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/render-config`)
    if (data?.guidance) {
      guidanceData.value = data.guidance
      // 默认展开第一个非折叠的 section
      activeSections.value = data.guidance.sections
        .filter((s: GuidanceSection) => !s.collapsed)
        .map((s: GuidanceSection) => s.id)
    }
  } catch {
    // render-config 可能已加载过，此处静默降级
  } finally {
    loading.value = false
  }
}

onMounted(loadGuidance)
</script>

<template>
  <div class="gt-wp-guidance-panel">
    <div v-if="loading" v-loading="true" style="min-height: 120px" />
    <div v-else-if="!hasGuidance" class="gt-wp-side-placeholder">
      当前底稿无编制说明
    </div>
    <template v-else>
      <div class="gt-wp-guidance-title">{{ guidanceData!.title }}</div>
      <el-collapse v-model="activeSections" class="gt-wp-guidance-collapse">
        <el-collapse-item
          v-for="section in guidanceData!.sections"
          :key="section.id"
          :name="section.id"
          :title="section.title"
        >
          <!-- 公式展示 -->
          <div v-if="section.formula" class="gt-wp-guidance-formula">
            <code>{{ section.formula }}</code>
          </div>

          <!-- 子公式 -->
          <div v-if="section.sub_formulas?.length" class="gt-wp-guidance-sub-formulas">
            <div v-for="sf in section.sub_formulas" :key="sf.label" class="gt-wp-guidance-sub-formula">
              <span class="gt-wp-guidance-sf-label">{{ sf.label }}：</span>
              <code>{{ sf.formula }}</code>
            </div>
          </div>

          <!-- 参数表 -->
          <div v-if="section.parameters?.length" class="gt-wp-guidance-params">
            <table class="gt-wp-guidance-param-table">
              <thead>
                <tr><th>符号</th><th>名称</th><th>说明</th></tr>
              </thead>
              <tbody>
                <tr v-for="p in section.parameters" :key="p.symbol">
                  <td class="gt-wp-guidance-symbol">{{ p.symbol }}</td>
                  <td>{{ p.name }}</td>
                  <td class="gt-wp-guidance-desc">{{ p.description }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 规则条目 -->
          <div v-if="section.items?.length" class="gt-wp-guidance-items">
            <div v-for="item in section.items" :key="item.seq" class="gt-wp-guidance-item">
              <span class="gt-wp-guidance-item-seq">{{ item.seq }}.</span>
              <span>{{ item.text }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<style scoped>
.gt-wp-guidance-panel {
  padding: 8px;
}
.gt-wp-guidance-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--gt-primary, #4b2d77);
}
.gt-wp-guidance-collapse {
  border: none;
}
.gt-wp-guidance-formula {
  background: var(--gt-bg-light, #f4f0fa);
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-radius: 4px;
  padding: 8px 12px;
  margin-bottom: 8px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  color: var(--gt-primary, #4b2d77);
}
.gt-wp-guidance-sub-formulas {
  margin-bottom: 8px;
}
.gt-wp-guidance-sub-formula {
  padding: 2px 0;
  font-size: 12px;
}
.gt-wp-guidance-sf-label {
  font-weight: 500;
  color: #666;
}
.gt-wp-guidance-sub-formula code {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--gt-primary, #4b2d77);
}
.gt-wp-guidance-param-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-bottom: 8px;
}
.gt-wp-guidance-param-table th {
  background: #f5f5f5;
  padding: 4px 8px;
  text-align: left;
  font-weight: 500;
  border-bottom: 1px solid #e0e0e0;
}
.gt-wp-guidance-param-table td {
  padding: 4px 8px;
  border-bottom: 1px solid #f0f0f0;
}
.gt-wp-guidance-symbol {
  font-family: 'Consolas', 'Monaco', monospace;
  font-weight: 600;
  color: var(--gt-primary, #4b2d77);
}
.gt-wp-guidance-desc {
  color: #666;
  font-size: 11px;
}
.gt-wp-guidance-items {
  padding-left: 4px;
}
.gt-wp-guidance-item {
  padding: 4px 0;
  font-size: 12px;
  line-height: 1.6;
}
.gt-wp-guidance-item-seq {
  font-weight: 600;
  margin-right: 4px;
  color: var(--gt-primary, #4b2d77);
}
</style>
