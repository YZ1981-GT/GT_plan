/**
 * useAddressRegistry — 地址坐标全局注册表 Store [R4.2]
 *
 * 对接后端 GET /api/address-registry 系列 API，
 * 为 CellSelector / FormulaRefPicker / 公式编辑器提供统一数据源。
 *
 * 用法：
 * ```ts
 * const addrStore = useAddressRegistry()
 * await addrStore.refresh(projectId, year)          // 加载全部地址
 * const results = await addrStore.search('货币资金') // 搜索
 * const entry = await addrStore.resolve(uri)         // 解析单个 URI
 * const valid = await addrStore.validate(formula)    // 校验公式引用
 * const route = await addrStore.jump(uri)            // 获取跳转路由
 * ```
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/utils/http'
import { addressRegistry as paths } from '@/services/apiPaths'
import { eventBus } from '@/utils/eventBus'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface AddressEntry {
  uri: string
  domain: string
  source: string
  path: string
  cell: string
  label: string
  formula_ref: string
  jump_route: string
  row_code?: string
  account_code?: string
  note_section?: string
  wp_code?: string
  tags?: string[]
}

export interface ResolveResult {
  found: boolean
  uri: string
  label?: string
  formula_ref?: string
  jump_route?: string
  domain?: string
  tags?: string[]
}

export interface ValidateResult {
  valid: boolean
  issues: Array<{ ref: string; reason: string }>
  formula: string
}

export interface JumpResult {
  route: string
  uri: string
  formula_ref: string
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAddressRegistry = defineStore('addressRegistry', () => {
  // ─── 状态 ───
  const addresses = ref<AddressEntry[]>([])
  const loaded = ref(false)
  const loading = ref(false)

  /** 当前绑定的项目/年度（用于自动刷新判断） */
  const _projectId = ref('')
  const _year = ref(0)
  const _templateType = ref('soe')

  // ─── 按域分组的计算属性 ───
  const tbAddresses = computed(() => addresses.value.filter(a => a.domain === 'tb'))
  const reportAddresses = computed(() => addresses.value.filter(a => a.domain === 'report'))
  const noteAddresses = computed(() => addresses.value.filter(a => a.domain === 'note'))
  const wpAddresses = computed(() => addresses.value.filter(a => a.domain === 'wp'))
  const auxAddresses = computed(() => addresses.value.filter(a => a.domain === 'aux'))

  // ─── 加载全部地址（首次 / 刷新） ───
  async function refresh(projectId?: string, year?: number, templateType?: string) {
    const pid = projectId || _projectId.value
    const yr = year ?? _year.value
    const tpl = templateType || _templateType.value

    if (!pid) return

    // 更新绑定参数
    _projectId.value = pid
    _year.value = yr
    _templateType.value = tpl

    if (loading.value) return
    loading.value = true
    try {
      const { data } = await http.get(paths.search, {
        params: {
          project_id: pid,
          year: yr,
          template_type: tpl,
          limit: 5000,
        },
      })
      const items = data?.items ?? data ?? []
      addresses.value = Array.isArray(items) ? items : []
      loaded.value = true
    } catch (e) {
      console.warn('[addressRegistry] 加载地址注册表失败', e)
    } finally {
      loading.value = false
    }
  }

  // ─── 搜索地址 ───
  async function search(
    keyword: string,
    domain?: string,
  ): Promise<AddressEntry[]> {
    if (!_projectId.value) return []

    // 本地过滤（已加载时优先本地搜索，减少请求）
    if (loaded.value && addresses.value.length > 0) {
      const kw = keyword.toLowerCase()
      return addresses.value.filter(a => {
        if (domain && a.domain !== domain) return false
        return (
          (a.label || '').toLowerCase().includes(kw) ||
          (a.formula_ref || '').toLowerCase().includes(kw) ||
          (a.uri || '').toLowerCase().includes(kw) ||
          (a.account_code || '').includes(kw) ||
          (a.row_code || '').includes(kw) ||
          (a.wp_code || '').toLowerCase().includes(kw)
        )
      })
    }

    // 未加载时走后端搜索
    try {
      const { data } = await http.get(paths.search, {
        params: {
          project_id: _projectId.value,
          year: _year.value,
          keyword,
          domain: domain || '',
          template_type: _templateType.value,
          limit: 100,
        },
      })
      return data?.items ?? data ?? []
    } catch {
      return []
    }
  }

  // ─── 解析单个 URI ───
  async function resolve(uri: string): Promise<ResolveResult> {
    if (!_projectId.value) return { found: false, uri }
    try {
      const { data } = await http.get(paths.resolve, {
        params: {
          uri,
          project_id: _projectId.value,
          year: _year.value,
          template_type: _templateType.value,
        },
      })
      return data
    } catch {
      return { found: false, uri }
    }
  }

  // ─── 校验公式引用有效性 ───
  async function validate(formula: string): Promise<ValidateResult> {
    if (!_projectId.value) return { valid: true, issues: [], formula }
    try {
      const { data } = await http.post(paths.validate, {
        formula,
        project_id: _projectId.value,
        year: _year.value,
        template_type: _templateType.value,
      })
      return data
    } catch {
      return { valid: false, issues: [{ ref: formula, reason: '校验请求失败' }], formula }
    }
  }

  // ─── 获取跳转路由 ───
  async function jump(uri: string, formulaRef?: string): Promise<JumpResult> {
    try {
      const { data } = await http.post(paths.jump, {
        uri: uri || '',
        formula_ref: formulaRef || '',
        project_id: _projectId.value,
        year: _year.value,
      })
      return data
    } catch {
      return { route: '', uri, formula_ref: formulaRef || '' }
    }
  }

  // ─── 失效缓存（后端 + 本地） ───
  async function invalidate(domain?: string) {
    if (!_projectId.value) return
    try {
      await http.post(paths.invalidate, {
        project_id: _projectId.value,
        year: _year.value,
        domain: domain || '',
      })
    } catch { /* ignore */ }
    // 重新加载
    await refresh()
  }

  // ─── 清空本地状态 ───
  function $reset() {
    addresses.value = []
    loaded.value = false
    loading.value = false
    _projectId.value = ''
    _year.value = 0
    _templateType.value = 'soe'
  }

  // ─── 监听模板应用事件，自动刷新地址注册表 ───
  eventBus.on('template-applied', () => {
    if (_projectId.value && loaded.value) {
      // 延迟刷新，等后端处理完模板应用
      setTimeout(() => refresh(), 500)
    }
  })

  // 监听公式变更事件，可能影响地址有效性
  eventBus.on('formula-changed', () => {
    if (_projectId.value && loaded.value) {
      setTimeout(() => refresh(), 300)
    }
  })

  return {
    // 状态
    addresses,
    loaded,
    loading,
    // 按域分组
    tbAddresses,
    reportAddresses,
    noteAddresses,
    wpAddresses,
    auxAddresses,
    // 方法
    refresh,
    search,
    resolve,
    validate,
    jump,
    invalidate,
    $reset,
  }
})
