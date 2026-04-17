/**
 * 合并报表 API 服务层
 * Phase 9 Task 2.1
 */
import http from '@/utils/http'

// ── Types ──

export interface ConsolScope {
  id: string
  company_code: string
  company_name: string
  shareholding: number
  consol_method: string
  is_included: boolean
}

export interface ConsolTrialRow {
  account_code: string
  account_name: string
  individual_sum: number
  consol_adjustment: number
  consol_elimination: number
  consol_amount: number
}

export interface EliminationEntry {
  id: string
  entry_no: string
  entry_type: string
  description: string
  debit_amount: number
  credit_amount: number
}

// ── Consolidation Scope ──

export async function getConsolScope(projectId: string) {
  const { data } = await http.get(`/api/consolidation/scope/${projectId}`)
  return data.data ?? data
}

export async function updateConsolScope(projectId: string, payload: any) {
  const { data } = await http.put(`/api/consolidation/scope/${projectId}`, payload)
  return data.data ?? data
}

// ── Consolidation Trial Balance ──

export async function getConsolTrial(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/trial/${projectId}/${year}`)
  return data.data ?? data
}

// ── Internal Trade ──

export async function getInternalTrades(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/internal-trade/${projectId}/${year}`)
  return data.data ?? data
}

// ── Minority Interest ──

export async function getMinorityInterest(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/minority-interest/${projectId}/${year}`)
  return data.data ?? data
}

// ── Consolidation Notes ──

export async function getConsolNotes(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/notes/${projectId}/${year}`)
  return data.data ?? data
}

// ── Consolidation Reports ──

export async function getConsolReports(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/reports/${projectId}/${year}`)
  return data.data ?? data
}


// ── Eliminations ──

export async function getEliminations(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/eliminations/${projectId}/${year}`)
  return data.data ?? data
}

// ── Component Auditor ──

export async function getComponentAuditors(projectId: string) {
  const { data } = await http.get(`/api/consolidation/component-auditor/${projectId}`)
  return data.data ?? data
}

// ── Goodwill ──

export async function getGoodwill(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/goodwill/${projectId}/${year}`)
  return data.data ?? data
}

// ── Forex ──

export async function getForex(projectId: string, year: number) {
  const { data } = await http.get(`/api/consolidation/forex/${projectId}/${year}`)
  return data.data ?? data
}
