/**
 * useWpDualMode — 底稿"结构化视图 / 在线编辑(OnlyOffice)"双模式统一封装
 *
 * 解决 B1 复盘发现的三类不一致：
 * 1. OnlyOffice 健康检查键名 BUG —— `api.get` 只 return response.data，返回的是
 *    ResponseWrapperMiddleware 信封 `{code,message,data:{healthy}}`；旧代码写
 *    `res?.healthy` 恒 undefined → 在线编辑被误摘掉/永不出现。本封装统一用
 *    `res?.data?.healthy ?? res?.healthy` 双层兼容解析。
 * 2. 不健康时主动从 modeOptions 摘掉「在线编辑」，避免用户点进去空白（"拉取不成功"）。
 * 3. 切到在线编辑前先 flush 结构化视图未保存的编辑，杜绝切换丢数据。
 *
 * 用法：
 *   const { mode, modeOptions, checkOOHealth, ooHealthy } = useWpDualMode({ flush: flushPendingSaves })
 *   onMounted(() => checkOOHealth())
 *   <el-segmented v-model="mode" :options="modeOptions" />
 *   <div v-if="mode === '结构化视图'">...</div>
 *   <GtOnlyOfficeSheet v-else :wp-id="wpId" :sheet-name="sourceSheet || 'B1-4'" />
 */
import { ref, watch } from 'vue'
import { api } from '@/services/apiProxy'

export interface UseWpDualModeOptions {
  /** 切换到「在线编辑」前调用（flush 结构化视图未保存的编辑） */
  flush?: () => void | Promise<void>
  /** 结构化视图标签（默认「结构化视图」） */
  structuredLabel?: string
  /** 在线编辑标签（默认「在线编辑」） */
  onlineLabel?: string
}

export function useWpDualMode(opts: UseWpDualModeOptions = {}) {
  const structuredLabel = opts.structuredLabel ?? '结构化视图'
  const onlineLabel = opts.onlineLabel ?? '在线编辑'

  const mode = ref(structuredLabel)
  const modeOptions = ref<string[]>([structuredLabel, onlineLabel])
  const ooHealthy = ref(false)
  const checkingHealth = ref(false)

  /** 健康检查：不健康则摘掉「在线编辑」并强制回退结构化视图 */
  async function checkOOHealth(): Promise<void> {
    checkingHealth.value = true
    try {
      const res = await api.get<any>('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      // 信封双层兼容：{code,message,data:{healthy}} 或直接 {healthy}
      const healthy = res?.data?.healthy ?? res?.healthy ?? false
      ooHealthy.value = !!healthy
      if (healthy) {
        modeOptions.value = [structuredLabel, onlineLabel]
      } else {
        modeOptions.value = [structuredLabel]
        if (mode.value === onlineLabel) mode.value = structuredLabel
      }
    } catch {
      ooHealthy.value = false
      modeOptions.value = [structuredLabel]
      if (mode.value === onlineLabel) mode.value = structuredLabel
    } finally {
      checkingHealth.value = false
    }
  }

  // 切到在线编辑前 flush 未保存编辑
  watch(mode, async (newMode, oldMode) => {
    if (oldMode === structuredLabel && newMode === onlineLabel) {
      await opts.flush?.()
    }
  })

  return { mode, modeOptions, ooHealthy, checkingHealth, checkOOHealth, structuredLabel, onlineLabel }
}
