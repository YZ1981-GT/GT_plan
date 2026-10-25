# T97 · D2 真栈回写的真实架构边界（第二轮复盘 P1/P2 问题 1/2）

**日期**：2026-09-26　**结论**：D2-3/D2-1 的真栈双向回写**不是**"缺环境/待接线"，是
`d2_bidirectional_bridge.py` 的**单绑定架构**天然不支持多受管区，需要 D4 式改造才能接。
本 spec 范围内**不做**这次架构改造（工作量与风险超出复盘修复的合理边界），登记为独立后续项。

## 一、真实生产路径（此前两轮复盘都未查全，本轮补全）

```
真栈回写实际路径：
  oo_to_html.py（真栈调用点）
    → store_item_registry.STORE_MERGE_REGISTRY["d2.receivable_detail"]
        provider_module = "d2_bidirectional_bridge"
        items = (StoreItemSpec(item_id="D2-detail-rows", kind=rows),)   ← 只声明了 1 个 item
    → d2_bidirectional_bridge.merge_projection_into_store_rows(...)      ← 真正的合并函数
        依赖 identity_binding() → 只返回 D2-2 的单一 ExcelIdentityBinding
    → excel_extract.extract_projection(..., binding: ExcelIdentityBinding, ...)
        resolve_managed_region(zf, contract=contract, binding=binding)   ← binding 是单数
```

`extract_projection` 本身设计成**单 binding**：一次调用对应一个受管区（table/sheet），
不遍历契约的 `sheets[]` 数组。这与我第一/二轮复盘查到的**声明层**（`pilot_d2_large_json.
build_contract_payload` 的 `sheets[]`、`parse_contract` 强校验）是两个完全不同的层：

- **声明层**（契约/instrumentation）：D2-3/D2-1 已真接入，`parse_contract` 通过，受管区
  1→4（D2-2 ①+D2-3 ②+D2-1 ①）——这是本 spec 第一轮 P0-1 修复的范围，**属实已完成**。
- **运行时数据流层**（真栈提取/合并）：`d2_bidirectional_bridge.py` 完全只处理 D2-2，
  `push_html_to_excel`/`pull_excel_to_html`/`merge_projection_into_store_rows` 三个函数
  硬编码单一 `identity_binding()`。D2-3/D2-1 在这一层**不存在**，不是"待接线"，是
  "所在的桥本身架构上一次只能挂一个受管区"。

## 二、D4 已有的正确解法（多受管区的先例，D2 若要接必须照它改）

D4 用 `_align_specs_to_sibling_tables` + `ExcelInstrumentationSpec` 的复数形态
（`instrumentation_specs()`）+ `store_item_registry.StoreMergePlan.dedicated_items`
三层配合，让一个 entry 的多个受管 sheet 各自独立走 extract/materialize，再在
`oo_to_html._mirror_dedicated_dict_stores` 里按注册表清单逐个 item 镜像。

D2 若要接 D2-3/D2-1 到真栈，正确路径是**照抄这套机制**，不是给 `d2_bidirectional_bridge.py`
的单绑定函数打补丁。需要动：

1. `store_item_registry.py`：给 `"d2.receivable_detail"` 的 `StoreMergePlan` 加
   `dedicated_items`（D2-3 三键 aging/customer/individual + D2-1 六键人工金额格）
2. `d2_bidirectional_bridge.py`：`push_html_to_excel`/`pull_excel_to_html` 改成对
   D2-2/D2-3/D2-1 各自的 binding 循环跑 extract/materialize（而非单次单绑定）
3. `phase5_d2_03_bad_debt.py`/`phase5_d2_01_adjudication.py`：补齐符合
   `dedicated_items` 签名约定的 merge 门面（`(*, projection, base_state) -> tuple`）
4. `oo_to_html.py`：确认 D2 的注册表条目被 `_mirror_dedicated_dict_stores` 一类的
   统一循环覆盖，而非落进某个专用 `hasattr` 块

## 三、为什么本 spec 不做这次改造

1. **风险**：直接改 `d2_bidirectional_bridge.py` 有破坏 D2-2 现有可用真栈路径的风险
   （它是目前唯一真正能跑通 OO 双向回写的 D 循环 entry 之一，见 spec design 的「D2 与 D4
   是 7 家里唯一两个 adapter 真注册的循环」）。
2. **工作量**：这是一次实质架构改造（4 个文件的多绑定循环重写 + 新的注册表分支覆盖测试），
   规模远超"修复复盘问题"的合理边界，且与 D2-3/D2-1 声明层本身的对错无关。
3. **归属**：这类"把单绑定 bridge 升级成多绑定"的改造应该照 D4 已验证的路径做，且需要
   独立的判据面（真栈 e2e 覆盖 D2-2/D2-3/D2-1 三区同时编辑）——适合另立 spec 而非夹带。

## 四、本 spec 已完成与未完成的准确边界（更新声明，替代第一轮 evidence 的乐观表述）

| 层 | D2-2 | D2-3 | D2-1 |
|---|---|---|---|
| 契约声明（sheets[]，parse_contract） | ✅ 已有 | ✅ 已接入（本 spec 阶段1） | ✅ 已接入（本 spec P0-1） |
| 投影/合并纯函数（供判据验证声明正确性） | ✅（`build_store_projection`） | ✅（`build_d23_store_projection`/`merge_projection_into_d23_stores`，仅判据消费） | ❌ 未建（问题1，本 spec 不补） |
| 真栈生产调用链（`d2_bidirectional_bridge` → `oo_to_html`） | ✅ 真实可用 | ❌ 不存在 | ❌ 不存在 |

D2-3/D2-1 的"投影/合并纯函数"是**声明正确性的可验证形态**（判据能证明契约字段↔store
键的映射逻辑是对的），但不是真栈会调用的代码——这是本 spec 复盘后必须澄清的关键区分，
此前的 evidence（T05/T17）用"真栈待环境/待 sibling 编排内核"这类措辞，容易被读成
"内核补上就通"，而实际是"整条调用链在这一层都不存在，需要新写"。

## 五、后续项登记

建议另立 spec（如 `d2-bridge-multi-binding-upgrade`），范围：
- 照抄 D4 `_align_specs_to_sibling_tables` 机制，把 `d2_bidirectional_bridge.py` 升级为
  多绑定架构
- 给 D2-1 补投影/合并函数（问题1 遗留）
- 注册表 `dedicated_items` 声明 D2-3/D2-1 的 9 个 store item
- 真栈 e2e：单个 wp 同时编辑 D2-2/D2-3/D2-1 三区，验证互不干扰
- 零回归门：D2-2 现有真栈路径在改造前后逐字节不变
