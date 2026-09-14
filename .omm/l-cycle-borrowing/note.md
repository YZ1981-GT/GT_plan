# 说明

产出方式、字段约定、维护约定见 `.omm/d-cycle-sales/note.md`。

## 本 perspective 的事实来源

- 8 个 componentType + render 策略 → `backend/app/routers/wp_render_strategies/__init__.py`
  （`l1-short-term-loans` … `l8-financial-expenses`）
- 前端目录 → `Get-ChildItem`（l1~l8）
- 科目码 → 各 `useL{n}FormData.ts`（L2 `'2231'` / L3 `'2501'` / L4 `ACCOUNT_CODE='2502'` /
  L5 `ACCOUNT_CODE_PAYABLE='2701'`+`ACCOUNT_CODE_UNRECOGNIZED='2702'` / L6 `'2601'` / L7 `'2801'` / L8 `'6603'`）；
  L1 = 2001 来自 `l1/handbooks/preparation.md`、`l1/core/L1TabAdjudication.vue`（`subjectPrefix:'2001'` / `direction:'credit'`）
- 双期审定表 / hydration / 凭证级检查 / JSON-array 存储 / IE round-trip / 一年内到期重分类 / 365 天利息测算
  → L 循环大量既有复盘记录（memory）
- 带入调整（`subjectPrefix:'2001'` / `direction:'credit'` / 双期 target 期末列）→ `L1TabAdjudication.vue`

## 未核实项

- 各科目 sheet ↔ Tab 精确映射未逐一读主入口 `v-if` 分发链；本文按分组描述
- L5 与 K5 共用 2701 的**实际回写行为**未逐一读代码确认，按"共码风险"陈述
- L6/L7/L8 各 sheet 结构沿用既有复盘记录（L6/L7 两期动态行正确、L8 损益不适用双期），本轮未逐一重读组件
- L4 应付债券 IE 前后端模型不匹配为既有记录（deferred），本轮未重读后端 IE
