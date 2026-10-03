# I 循环 BP-1~BP-4 门清零与验收证据（2026-10-01）

## 结论

I 循环 6/6 entry 已完成五环发布、manifest 翻转、真实 PG 注册与真 OnlyOffice 引擎 roundtrip。
地基 Task 22/24、lane1 Task 17/18/19、lane2 Task 15a/18/19/19a 的外部门已解除。

## 五环发布与真实注册

1. 新增 `fix_i_cycle_wp_code_adjudication.py`：6 个 CamelCase 幻影码（I1I/I2D/I3G/I4L/I5O/I6R）
   显式裁成真实整册码 I1~I6；wp_index 两套编号逐条登记。
2. H 公共骨架补齐 `publish_h_entry_definitions`、单/多表 store projection、运行时 sibling binding；
   6 个 I provider 都有 `publish_pilot_definitions` / `PILOT_WP_CODES` / `instrumentation_spec` /
   `build_store_projection` / merge / attach 完整发布面。
3. task76 在真实 PG 为每条 entry 发布 authority/template/instrumentation/contract + approved bundle；
   `fix_projection_first_publication.py` 10/10 阶段通过并发布 current representation。
4. I2 的发布门从 host 收敛到 composable 后，契约重生成、task76 新 bundle、
   `fix_l_cycle_republish_representation.py`（已泛化支持 I）重新发布；真实注册仍通过。
5. `register_from_manifest(session=真PG)` 返回 I1~I6 六个 adapter 全部 `OK`，无 reason/failure。

真实 `working_paper_sync_entry_state`（查数据，不看脚本退出码）：

| entry | wp_id | current representation | bundle |
|---|---|---|---|
| I1 | 57356eb6… | fd95fc18… | 402d288d… |
| I2 | c41da93f… | 9c54bf24… | a2d76bbd… |
| I3 | 926f8e9f… | 37fdd609… | 3b543f70… |
| I4 | 4f65bf18… | 0e5c30d5… | 27f992ff… |
| I5 | 051d4e6b… | 72895494… | 11790cc6… |
| I6 | 0048c8a5… | 7853582a… | 8afd4905… |

6 个主表键真库均 0 行，因此 roundtrip 如 spec 原要求标 `synthetic_payload_no_live_db_baseline`；
脚本全程只读 store，前后快照一致。

## OOXML 门修复（不放宽安全策略）

`sanitize_i_cycle_template_external_links.py` 明确净化四册并留 `.preclean.bak` 门负例：

- I2：删 2 外链部件，14 格 `[1]明细表I6-2` 断链公式转缓存值；
- I3：删 2 外部 hyperlink + 17 个 OLE 嵌入公式对象（2 个在 I3-7、15 个在参考示例）；
- I4：删 20 外链部件 + 107 个断链 defined name；
- I5：删 20 外链部件 + 106 个断链 defined name。

每册同时满足：净化前门负例 REJECT、净化后生产 `validate_ooxml_artifact` PASS、受管 sheet
逐格 0 diff、merge 集合不变、逐项计数与声明等值。策略 `allow_external_relationships=false` /
`allow_embedded_objects=false` 未修改。

## 真实 OnlyOffice roundtrip

正式工具：`backend/scripts/e2e/verify_i_cycle_oo94_roundtrip.py`。
生产链：真实 PG published representation → 生产 attach → 合成 store projection → materialize →
Docker `audit-onlyoffice` 的 `ConvertService.ashx` xlsx→xlsx 真引擎重存 → extract → G1 等值门 →
merge 回 store；每条 5 行，行身份互异，I1/I3 混入 grandfather `cgu-3`。

| entry | sync_test_run_id | projection | OO | 结果 |
|---|---|---:|---:|---|
| I1 | `i-oo94-i1-bb362c6dce8e` | 140 values / 5 rows | 100% | ✅ |
| I2 | `i-oo94-i2-1de4d7db5bcf`（门收敛+重发布后复验） | 65 / 5 | 100% | ✅ |
| I3 | `i-oo94-i3-1d0993fea581` | 65 / 5 | 100% | ✅ |
| I4 | `i-oo94-i4-2411d20845ff` | 75 / 5（既存 identity 原位写，避免横向 shared formula 非法插行） | 100% | ✅ |
| I5 | `i-oo94-i5-dc80dc19f756` | 95 / 10（同 store 双区） | 100% | ✅ |
| I6 | `i-oo94-i6-3ba8b090c097` | 110 / 5 | 100% | ✅ |

六条共同断言：G1 等值、输入 store 逐字段相等、行身份稳定、formula_mask 后公式仍在、
非受管 sheet 公式被 OO 改写 0 格、DB 主表键前后 digest 不变。I3 的 `I14` 例外从契约
`known_template_quirks[].handling=registered_not_fixed` 读取，未硬编码放宽。

## 真实缺陷修复

- I5 R21 是 `……` 排版占位，不是业务行；原值区收为 R11~20，减值镜像区收为 R24~33。
- I5 同 sheet 双区不能共用 UUID 列：gross=R、impairment=S（S 列全空且无 merge）。
- I5 同 store 双物理区：sibling physical rowId 使用可逆 `~gt:{table_key}` 命名空间，merge 时去后缀；
  runtime attach 补 sibling bindings。修前 impairment 45 个字段 extract 后全丢，修后真 OO 6/6 通过。
- `projection_first_publication._sheet_for` 改为 sheet_key 优先；原先 excel_name 优先会让 I5 两个同名
  contract sheet 都配到 gross，首版发布回滚。
- I2 `publishToTb` 收敛进 composable；20 条参数化测试含 I2 通过，二次确认/唯一端点/取消无副作用保留。

## 自动验证

- `test_i_cycle_publish_and_multiregion.py`：10 passed；
- `iAdjudicationPublishGate.spec.ts`：20 passed；
- task51 五条迁移翻面判据：5 passed；
- 模板 count/size + snapshot：2 passed；
- I 循环真 OO：6/6 passed。
