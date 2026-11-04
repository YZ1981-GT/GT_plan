import { describe, expect, it } from 'vitest'

import type { AIModel, AIRoute, AIRouteCandidate } from '@/services/aiModelApi'
import {
  activeTagText, candidateName, candidatePolicyText, chainOf, deactivateConsequence, effectiveClass, effectiveText,
  emptyText, statusText,
} from './modelRouteView'

function candidate(overrides: Partial<AIRouteCandidate> = {}): AIRouteCandidate {
  return {
    model_id: 'id-server', model_name: 'qwen3.8', deployment: 'server', provider: 'custom',
    endpoint: null, source: 'database', reasoning_effort: null,
    trust_zone: 'firm_private', client_data_allowed: true, mask_policy: 'role_based',
    implicit: false,
    status: 'available', reason: '可用', latency_ms: 120, checked_at: null, ...overrides,
  }
}

function route(candidates: AIRouteCandidate[], overrides: Partial<AIRoute> = {}): AIRoute {
  return {
    kind: 'chat', label: '对话模型', policy: 'local_first', candidates, error: null,
    effective: candidates.find(item => item.status === 'available') ?? null,
    has_local: candidates.some(item => item.deployment === 'local'),
    has_server: candidates.some(item => item.deployment === 'server'),
    ...overrides,
  }
}

function model(overrides: Partial<AIModel>): AIModel {
  return {
    id: 'm', preset_key: null, model_name: 'm', model_type: 'chat', provider: 'custom',
    endpoint_url: null, reasoning_effort: null, ocr_capability: null, ocr_protocol: null,
    api_path: null, auth_scheme: null, auth_header_name: null, request_timeout_seconds: null,
    has_api_key: false, api_key_updated_at: null, deployment: 'server',
    trust_zone: 'firm_private', client_data_allowed: true, mask_policy: 'role_based',
    is_active: true,
    context_window: null, performance_notes: null, created_at: null, updated_at: null, ...overrides,
  }
}

const LOCAL = { model_id: 'id-local', model_name: 'Qwen3.5', deployment: 'local' as const }

describe('调用路由面板展示逻辑', () => {
  it('本机优先路由补出未启用的一端，向量只列实际那一条', () => {
    const serverOnly = chainOf(route([candidate()]))
    expect(serverOnly.map(slot => [slot.deployment, slot.candidate?.model_name ?? null])).toEqual([
      ['local', null], ['server', 'qwen3.8'],
    ])
    const embedding = chainOf(route([candidate(LOCAL)], { kind: 'embedding', policy: 'single' }))
    expect(embedding).toHaveLength(1)
  })

  it('JSON 里 effective 与候选是两个对象：按身份判断是否兜底', () => {
    const local = candidate({ ...LOCAL, status: 'unavailable', reason: '端点不可达' })
    const server = candidate()
    const fallback = route([local, server], { effective: { ...server } })
    expect(effectiveText(fallback)).toBe('服务器「qwen3.8」（兜底）')
    const direct = route([candidate({ ...LOCAL }), server], { effective: { ...candidate({ ...LOCAL }) } })
    expect(effectiveText(direct)).toBe('本机「Qwen3.5」')
    expect(effectiveClass(direct)).toBe('ok')
  })

  it('无可用候选时区分未检测与不可用', () => {
    expect(effectiveText(route([candidate({ status: 'unknown' })]))).toBe('未检测，点击「检测状态」')
    expect(effectiveClass(route([candidate({ status: 'unknown' })]))).toBe('unknown')
    expect(effectiveText(route([candidate({ status: 'unavailable', reason: 'x' })]))).toBe('不可用')
    expect(effectiveClass(route([candidate({ status: 'unavailable', reason: 'x' })]))).toBe('err')
  })

  it('状态文字带原因与耗时，兜底候选标明来源', () => {
    expect(statusText(candidate())).toBe('可用 · 120 ms')
    expect(statusText(candidate({ status: 'unavailable', reason: '鉴权失败，请检查 API Key' }))).toBe('鉴权失败，请检查 API Key')
    expect(statusText(candidate({ status: 'unknown' }))).toBe('未检测')
    expect(candidateName(candidate({ implicit: true, source: 'environment', model_name: 'Qwen3.5' }))).toBe('Qwen3.5（.env 默认）')
    expect(candidateName(candidate({ implicit: true, source: 'builtin', model_name: '本机 OCR 引擎' }))).toBe('内置引擎')
    expect(candidatePolicyText(candidate())).toBe('事务所私有 · 可处理客户数据 · 按角色脱敏')
    expect(candidatePolicyText(candidate({
      trust_zone: 'approved_provider', client_data_allowed: true, mask_policy: 'strict',
    }))).toBe('已批准外部 · 可处理客户数据 · 严格脱敏')
  })
})

describe('模型表格启用标签与停用提示', () => {
  const localChat = model({ id: 'l', model_name: 'Qwen3.5', deployment: 'local' })
  const serverChat = model({ id: 's', model_name: 'qwen3.8', deployment: 'server' })

  it('服务器行在有本机行时是兜底，单独启用时是唯一生效', () => {
    expect(activeTagText(localChat, [localChat, serverChat])).toBe('已启用 · 本机优先')
    expect(activeTagText(serverChat, [localChat, serverChat])).toBe('已启用 · 服务器兜底')
    expect(activeTagText(serverChat, [serverChat, { ...localChat, is_active: false }])).toBe('已启用 · 服务器')
    expect(activeTagText(model({ model_type: 'embedding', deployment: 'local' }), [])).toBe('已启用')
  })

  it('停用提示说明由谁承担调用；OCR 只看同能力槽', () => {
    expect(deactivateConsequence(localChat, [localChat, serverChat])).toBe('停用后由服务器模型「qwen3.8」承担调用。')
    expect(deactivateConsequence(serverChat, [serverChat])).toContain('回落 .env 默认配置')
    const text = model({ id: 'o1', model_type: 'ocr', ocr_capability: 'ocr', deployment: 'local', model_name: 'paddleocr' })
    const layout = model({ id: 'o2', model_type: 'ocr', ocr_capability: 'layout_parsing', model_name: 'paddleocrvl-1.6' })
    expect(deactivateConsequence(layout, [text, layout])).toBe('停用后版面解析没有启用模型，调用会提示「未配置」。')
    expect(deactivateConsequence(text, [text, layout])).toContain('本机内置 OCR 引擎')
  })
})

describe('重排模型（spec enterprise-embedding-rerank-closure）', () => {
  const serverRerank = model({ id: 'r1', model_type: 'rerank', model_name: 'qwen3-reranker-4b', deployment: 'server' })

  it('重排与对话同样本机优先：只有服务器一条时补出未启用的本机端', () => {
    const chain = chainOf(route([candidate({ model_name: 'qwen3-reranker-4b' })], { kind: 'rerank', label: '重排模型' }))
    expect(chain.map(slot => [slot.deployment, slot.candidate?.model_name ?? null])).toEqual([
      ['local', null], ['server', 'qwen3-reranker-4b'],
    ])
    expect(activeTagText(serverRerank, [serverRerank])).toBe('已启用 · 服务器')
  })

  it('停用后说明不再重排、没有 .env 兜底；未启用时空态说明按召回分数排序', () => {
    expect(deactivateConsequence(serverRerank, [serverRerank])).toBe(
      '停用后知识检索不再重排，按向量 / 词法召回分数排序（重排没有 .env 兜底）。',
    )
    const localRerank = model({ id: 'r2', model_type: 'rerank', model_name: 'local-reranker', deployment: 'local' })
    // 同类型另一条启用的重排承担调用（与对话同口径），不会误报「不再重排」
    expect(deactivateConsequence(localRerank, [localRerank, serverRerank])).toBe(
      '停用后由服务器模型「qwen3-reranker-4b」承担调用。',
    )
    expect(emptyText(route([], { kind: 'rerank', label: '重排模型' }))).toBe('未启用重排模型，知识检索按召回分数排序')
    expect(emptyText(route([], { kind: 'chat' }))).toBe('未启用模型')
  })

  it('重排未启用不是故障：当前生效显示「未启用」且不标红；启用后不可用照常标红', () => {
    const empty = route([], { kind: 'rerank', label: '重排模型' })
    expect(effectiveText(empty)).toBe('未启用（不重排）')
    expect(effectiveClass(empty)).toBe('unknown')
    // 对话 / 版面解析没有启用行仍按原口径
    expect(effectiveText(route([], { kind: 'layout_parsing' }))).toBe('不可用')
    const down = route([candidate({ model_name: 'qwen3-reranker-4b', status: 'unavailable', reason: 'x' })], { kind: 'rerank' })
    expect(effectiveText(down)).toBe('不可用')
    expect(effectiveClass(down)).toBe('err')
    // 读配置出错（error 非空）不能被当成「未启用」
    expect(effectiveClass(route([], { kind: 'rerank', error: '读取重排配置失败（DBAPIError）' }))).toBe('err')
  })
})
