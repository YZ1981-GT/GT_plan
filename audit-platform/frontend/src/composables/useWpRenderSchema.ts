/**
 * useWpRenderSchema — 底稿渲染 schema 加载 + 校验 + 项目级覆盖合并
 *
 * 与 useWpRenderer 的关系：
 *   useWpRenderer → 加载完整 RenderConfig（包含 schema/html_data/cross_refs 等）
 *   useWpRenderSchema → 仅关注 schema 本身（用于 schema 预览/调试/Storybook 等场景）
 *
 * 职责（spec workpaper-html-renderer Task 12.6）：
 * 1. loadSchema(wpCode, templateVersionId?)：调 GET /api/workpapers/{wp_id}/render-config
 *    （render-config 端点已含项目级 override 合并）
 * 2. validate(data, schema)：客户端 schema 结构校验（宽松，避免 ajv 大依赖）
 * 3. merge(schema, projectOverride)：纯函数深度合并，便于离线场景与单测
 * 4. 缓存：简单 Map keyed by `wpCode + templateVersionId`，避免 6000 并发场景重复请求
 *
 * 暴露两套 API：
 *   - 命令式（推荐用于命令式调用 / 测试）：loadSchema / validate / merge
 *   - 响应式（推荐用于 Vue 组件）：schema ref + watch wpRef/projectId 自动重载
 *
 * @example
 *   // 命令式
 *   const { loadSchema, validate, merge } = useWpRenderSchema()
 *   const schema = await loadSchema('D2A', 'uuid-...')
 *
 *   // 响应式（兼容旧调用方）
 *   const wpCode = ref('D2A')
 *   const projectId = ref('uuid-...')
 *   const { schema, loading, error, reload } = useWpRenderSchema(wpCode, projectId)
 *
 * Validates: Requirements 2.2 原则 2（配置驱动）
 */
import { ref, watch, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * Schema 的运行时形态。
 * 与后端 wp_render_schema YAML 的字段保持一致，但保留扩展性。
 */
export interface WpRenderSchema {
  wp_code?: string
  template_path?: string
  template_version?: string
  applicable_standards?: string[]
  sheets?: Record<string, any> | any[]
  /** 顶层字段未来可能扩展（如 metadata / version 等），保留 any */
  [key: string]: any
}

export interface UseWpRenderSchemaOptions {
  /** 是否做结构校验（默认 true） */
  validate?: boolean
  /** 是否启用 Map 缓存（默认 true） */
  cache?: boolean
}

// ─── 模块级缓存 ──────────────────────────────────────────────────────────────
// 跨 composable 实例共享，避免 6000 并发同 wp_code 场景重复请求

/** Map keyed by `${wpCode}:${templateVersionId ?? 'default'}` */
const _schemaCache = new Map<string, WpRenderSchema>()

function buildCacheKey(wpCode: string, templateVersionId?: string): string {
  return `${wpCode}:${templateVersionId ?? 'default'}`
}

/** 清除缓存（调试 / 热更新场景使用） */
export function clearSchemaCache(wpCode?: string): void {
  if (wpCode === undefined) {
    _schemaCache.clear()
    return
  }
  for (const key of _schemaCache.keys()) {
    if (key.startsWith(`${wpCode}:`)) {
      _schemaCache.delete(key)
    }
  }
}

// ─── 纯函数：校验 + 深度合并 ──────────────────────────────────────────────────

/**
 * 宽松结构校验：data 必须是对象，且建议含 wp_code / sheets 字段
 * （不引入 ajv 等重依赖；如需严格 JSON Schema 校验由后端兜底）
 *
 * @returns true 校验通过；抛 Error 时校验失败
 */
export function validate(data: any, _schema?: any): boolean {
  if (!data || typeof data !== 'object') {
    throw new Error('schema 应为对象，实际收到 ' + typeof data)
  }
  if (!('wp_code' in data) && !('sheets' in data)) {
    console.warn(
      '[useWpRenderSchema] schema 缺少 wp_code / sheets 字段（项目级覆盖可能为空）',
    )
  }
  return true
}

/**
 * 深度合并 override 到 base（不修改原对象，返回新对象）
 *
 * 规则：
 * - override 中的 dict 值递归合并到 base 对应 key
 * - override 中的非 dict / array 值直接覆盖 base 对应 key
 * - override 中新增的 key 直接添加到 base
 *
 * 与后端 wp_render_schema_service._deep_merge 行为一致
 */
export function merge<T extends Record<string, any>>(
  base: T,
  override: Partial<T> | null | undefined,
): T {
  if (!override) {
    return deepClone(base)
  }
  const result = deepClone(base)
  _deepMergeInPlace(result, override as Record<string, any>)
  return result
}

function _deepMergeInPlace(base: Record<string, any>, override: Record<string, any>): void {
  for (const key of Object.keys(override)) {
    const ov = override[key]
    const bv = base[key]
    if (
      ov !== null
      && typeof ov === 'object'
      && !Array.isArray(ov)
      && bv !== null
      && typeof bv === 'object'
      && !Array.isArray(bv)
    ) {
      _deepMergeInPlace(bv, ov)
    } else {
      base[key] = deepClone(ov)
    }
  }
}

function deepClone<T>(value: T): T {
  if (value === null || typeof value !== 'object') return value
  if (Array.isArray(value)) return value.map(deepClone) as unknown as T
  const out: Record<string, any> = {}
  for (const key of Object.keys(value as Record<string, any>)) {
    out[key] = deepClone((value as Record<string, any>)[key])
  }
  return out as T
}

// ─── 简易 UUID 检测 ──────────────────────────────────────────────────────────

function looksLikeUuid(value: string): boolean {
  if (!value) return false
  const stripped = value.replace(/-/g, '')
  return /^[0-9a-fA-F]{32}$/.test(stripped)
}

// ─── 命令式 loadSchema ───────────────────────────────────────────────────────

/**
 * 命令式 loadSchema：直接拉取并合并 schema（不依赖 Vue 响应式）
 *
 * @param wpRef wp_id (UUID) 或 wp_code (e.g. "D2A")
 * @param projectId 项目 ID（wp_code 模式必填，UUID 模式可选）
 * @param templateVersionId 可选模板版本 ID（用于缓存键隔离）
 */
export async function loadSchemaImperative(
  wpRef: string,
  projectId?: string,
  templateVersionId?: string,
  options: { cache?: boolean; validate?: boolean } = {},
): Promise<{ schema: WpRenderSchema; resolvedWpId: string }> {
  const useCache = options.cache !== false
  const doValidate = options.validate !== false

  const wpRefTrim = (wpRef ?? '').trim()
  if (!wpRefTrim) {
    throw new Error('wpRef 为空')
  }

  // 命中缓存（缓存键基于 wpRef + templateVersionId）
  const cacheKey = buildCacheKey(wpRefTrim, templateVersionId)
  if (useCache && _schemaCache.has(cacheKey)) {
    return {
      schema: _schemaCache.get(cacheKey)!,
      resolvedWpId: looksLikeUuid(wpRefTrim) ? wpRefTrim : '',
    }
  }

  // 解析 wp_id
  let wpId: string
  if (looksLikeUuid(wpRefTrim)) {
    wpId = wpRefTrim
  } else {
    const pid = (projectId ?? '').trim()
    if (!pid) {
      throw new Error(`传入 wp_code='${wpRefTrim}' 但缺少 projectId，无法解析 wp_id`)
    }
    const res = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: pid, wp_code: wpRefTrim },
    })
    if (!res?.wp_id) {
      throw new Error(`wp_code='${wpRefTrim}' 未找到对应 wp_id`)
    }
    wpId = res.wp_id
  }

  // 调 render-config 端点（已包含 schema + 项目级覆盖合并）
  const res = await api.get<any>(`/api/workpapers/${wpId}/render-config`)

  let payload: WpRenderSchema = res
  if (res && Array.isArray(res.sheets) && res.sheets.length === 1) {
    const single = res.sheets[0]
    if (single?.schema && typeof single.schema === 'object') {
      payload = {
        wp_code: res.wp_code,
        template_version: res.template_version,
        applicable_standards: undefined,
        sheets: res.sheets,
        ...single.schema,
      }
    }
  }

  if (doValidate) {
    validate(payload)
  }

  if (useCache) {
    _schemaCache.set(cacheKey, payload)
  }

  return { schema: payload, resolvedWpId: wpId }
}

// ─── Composable（响应式 + 命令式双 API） ─────────────────────────────────────

/**
 * @overload 命令式调用：useWpRenderSchema()
 *   只需要 loadSchema / validate / merge 工具函数
 *
 * @overload 响应式调用：useWpRenderSchema(wpRef, projectId, options?)
 *   提供 schema ref + 自动 watch 重载
 *
 * @param wpRef  支持两种语义：
 *   - UUID 字符串（直接作为 wp_id 传给后端）
 *   - wp_code（如 "D2A"）：会先调 wp-id-by-code 转换为 wp_id
 * @param projectId 项目 ID（wp_code 模式必填，UUID 模式可选）
 */
export function useWpRenderSchema(): {
  loadSchema: typeof loadSchemaImperative
  validate: typeof validate
  merge: typeof merge
  clearCache: typeof clearSchemaCache
}
export function useWpRenderSchema(
  wpRef: Ref<string>,
  projectId: Ref<string>,
  options?: UseWpRenderSchemaOptions,
): {
  schema: Ref<WpRenderSchema | null>
  loading: Ref<boolean>
  error: Ref<Error | null>
  resolvedWpId: Ref<string>
  reload: () => Promise<void>
  loadSchema: typeof loadSchemaImperative
  validate: typeof validate
  merge: typeof merge
  clearCache: typeof clearSchemaCache
}
export function useWpRenderSchema(
  wpRef?: Ref<string>,
  projectId?: Ref<string>,
  options: UseWpRenderSchemaOptions = {},
): any {
  // ── 命令式调用形态（无参数）：仅返回工具函数 ──
  if (!wpRef) {
    return {
      loadSchema: loadSchemaImperative,
      validate,
      merge,
      clearCache: clearSchemaCache,
    }
  }

  // ── 响应式调用形态 ──
  const { validate: doValidate = true, cache = true } = options

  const schema = ref<WpRenderSchema | null>(null)
  const loading = ref(false)
  const error = ref<Error | null>(null)
  const resolvedWpId = ref<string>('')

  async function load() {
    loading.value = true
    error.value = null
    try {
      const result = await loadSchemaImperative(
        wpRef!.value,
        projectId?.value,
        undefined,
        { cache, validate: doValidate },
      )
      schema.value = result.schema
      resolvedWpId.value = result.resolvedWpId
    } catch (e) {
      error.value = e as Error
      schema.value = null
    } finally {
      loading.value = false
    }
  }

  // 初始化 + wpRef/projectId 变化时自动重载
  watch(
    [wpRef, projectId ?? ref('')],
    ([newWp, newPid], [oldWp, oldPid]) => {
      if (newWp !== oldWp || newPid !== oldPid) {
        if (newWp) load()
      }
    },
    { immediate: true },
  )

  return {
    schema,
    loading,
    error,
    resolvedWpId,
    reload: load,
    loadSchema: loadSchemaImperative,
    validate,
    merge,
    clearCache: clearSchemaCache,
  }
}
