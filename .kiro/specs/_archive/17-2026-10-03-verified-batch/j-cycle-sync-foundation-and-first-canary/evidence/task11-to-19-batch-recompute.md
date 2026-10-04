# J 循环 T11~T19 批量现算

**日期**：2026-09-27　**方法**：openpyxl + grep

## RD-1 shortTerm B13:B32 (20 项) — 与 design 一致 ✅

边界格: A11=序号 / B11=项目名称 / B12=None / A33=合计 / B33=None

## RD-2 postEmployment B37:B44 (8 项) — 全角 `．` 确认

B38=`其中：1．基本养老保险费`（全角点 U+FF0E）

## RD-3 severance B50:B52 — 全 None ✅

## RD-5 J1-6 A17:A35 (19 项) — 含全角空格+换行符

- `\u3000\u3000\u3000` = 三个全角空格（U+3000）缩进
- A32=`八、辞退福利\n（因解除劳动关系给予的补偿）` 含换行符
- 全角点 `．`（U+FF0E）贯穿

## sheet 列表 J1 (23 张)

- 尾部空格 2 张: `审定表J1-1 ` / `明细表J1-2 ` ✅
- 名中空格 3 张: `应付职工薪酬实质性程序表 J1A` 等 ✅
- hidden retired: `J1A-原版` / `L1A-原` / `J1-10-删除` / `J1-11-删除` / `J1-12-删除` / `IPO-删除` / `首发-删除` = 7 张 ✅
- 跨循环串册: `L1A-原` (hidden) ✅
- 一码两义: `辞退福利检查表J1-10`(visible) + `股份支付检查表J1-10-删除`(hidden) ✅

## footer 三形态

- R33 跳跃: `=SUM(C13,C19:C20,C25:C31)` ✅
- R46 加法: `=C42+C37` ✅
- R53 连续: `=SUM(C50:C52)` ✅

## 幽灵行 R45

A/B/C/D/E 全 None，F45=`=C45+D45-E45` + J/K/L/M 有公式。确认在数据区 R37:R44 之后、footer R46 之前。✅

## definedName

- J1: 0 / J2: 37 / J3: 502
- 断链: openpyxl API 未检测到 `#REF!`（design 声明 J2=30/J3=479 有断链，存疑标注）

## 裸 IF (findall 口径)

- J1: **224** / J2: **24** / J3: 0 / 总 248
- design 说 J1=132/J2=12/J3=0 总 144，差异来自全册 vs 部分 sheet 口径
- per-file 中性化按现算全册值

## derived_total_keys

现算命中 **3 个** (J1-7-total-{admin-expense,production-cost,selling-expense})
design 说 7 个。差异来自扫描路径（composables 在不同目录树）。标「现算 3，禁写死」。
