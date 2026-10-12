# D2 检查底稿双向回写覆盖 — Tasks

## Phase 0: 勘测（✅ 已完成）

- [x] 0.1 确认 D2-6至D2-13 工作簿的 wp_code 与 wp_id 映射
- [x] 0.2 逐子组件现读（store item_id / 行身份 / 字段数）
- [x] 0.3 逐 sheet openpyxl 精读（表头/数据区/公式列）
- [x] 0.4 确认 D2-8 和 D2-13 是否需要双向
- [x] 0.5 决定方案：独立 entry `xlsx/gt-d2-inspection`

## Phase 2: 后端 entry 骨架（✅ 已完成）

- [x] 2.1 `pilot_d2_inspection.py` 入口模块
- [x] 2.2 验证模块导入 + 契约 payload 生成

## Phase 3: 逐 sheet provider

- [x] 3.1 D2-6 关联方检查表（12 字段，2 公式列 F/H）`phase5_d2_06_related_party.py`
- [x] 3.2 D2-11 核销检查表（双区各 8 字段）`phase5_d2_11_writeoff.py`
- [x] 3.3 D2-13 业务模式分析（分组表 5 字段）`phase5_d2_13_bizmodel.py`
- [x] 3.4 D2-12 质押出售检查表（质押区 9 字段）`phase5_d2_12_pledge.py`
- [x] 3.5 D2-7 应收账款检查表（双区各 17 字段）`phase5_d2_07_voucher_check.py`
- [x] 3.6 D2-8 裁定：纯文本描述型，不需要 provider（HTML-only）
- [ ]* 3.7 D2-9 坏账准备测算（后续扩容：57 公式多区分析表）
- [ ]* 3.8 D2-10 ECL 计量测试（后续扩容：198 公式极复杂）
- [ ]* 3.9 D2-5 分析程序（后续扩容：独立工作簿）

## Phase 4: 灰度开关接入（✅ 已完成）

- [x] 4.1 打开 D2-7/D2-11/D2-12/D2-13 四个灰度开关
- [x] 4.2 `instrumentation_specs()` 接入 5 个 spec
- [x] 4.3 `build_contract_payload()` 接入 5 个 sheet（76 字段）
- [x] 4.4 `all_store_item_ids()` 接入 7 个 store key
- [x] 4.5 `build_combined_store_projection()` 接入全部 provider
- [x] 4.6 验证全链路（specs=5 / sheets=5 / store_ids=7 / fields=76）

## Phase 1: 前端（✅ 已完成）

- [x] 1.1 `D2_INSPECTION_SHEET_KEYS` 声明 5 张检查 sheet 的 sheet_key 映射
- [x] 1.2 `syncUnavailableReason` 区分检查 sheet → 显示「开发中」
- [x] 1.3 零诊断验证

## Phase 5: 验收

- [x] 5.1 所有 provider 模块 getDiagnostics 零诊断
- [x] 5.2 pilot_d2_inspection.py 全链路验证通过
- [ ]* 5.3 浏览器实测（待 start-dev.bat 环境）
- [ ]* 5.4 真库 roundtrip（待发布链完成 + 真库有数据）

## 产出汇总

| 文件 | 类型 | 字段数 |
|------|------|--------|
| `phase5_d2_06_related_party.py` | provider | 12 |
| `phase5_d2_07_voucher_check.py` | provider | 34 (17×2区) |
| `phase5_d2_11_writeoff.py` | provider | 16 (8×2区) |
| `phase5_d2_12_pledge.py` | provider | 9 |
| `phase5_d2_13_bizmodel.py` | provider | 5 |
| `pilot_d2_inspection.py` | entry 入口 | — |
| `GtD2AccountsReceivable.vue` | 前端 | — |
| **合计** | **7 文件** | **76 字段** |
