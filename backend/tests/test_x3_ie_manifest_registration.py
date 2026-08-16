"""GS-M —— `{l,m,n}_cycle_ie_manifest.yaml` 登记面守卫（只读态，不写 catalog）

spec: `x3-adjustment-entry-import-export` · Wave 5 任务 8.1
_Requirements: 5.2, 5.3, 11.3_

## 判据为什么必须落「行为」而不是「文件存在」

任务 8.1 的交付物是三个 yaml + `generate_catalog._ALL_CYCLES` 追加三个循环码。
「文件存在 + 列表里有这三个字母」是**字符存在型**判据，命中 memory 记的假绿第
②类：把 `_ALL_CYCLES` 改回五项、把某条 entry 的 `sheet_code` 打错一个字、或把
`load_ie_manifest` 的调用整段删掉，这类判据全都照绿。

⇒ 本文件的核心三条一律**真跑生成器**：

- `test_loader_derives_sixteen_entries_from_the_three_manifests`
  —— `load_ie_manifest('l'|'m'|'n')` 真读磁盘，条数 2 / 10 / 4，并集恰等于从
  Key_Ledger 派生的 16 张。
- `test_generator_all_cycles_derives_the_sixteen_import_export_segments`
  —— `generate_catalog(offline=True)` 真跑一次，16 张 sheet 的 `import_export`
  段逐字段等于 manifest 值（不是「manifest 里写了什么」，而是「生成器把它派生
  到了 catalog 结构里」）。
- `test_generator_delta_versus_control_is_exactly_the_sixteen`
  —— `cycle='all'` 与控制组 `d+k+f+g+h` 五次生成的并集作差，差集**恰为**这
  16 张。这一条同时是「零附带」的证据：本任务没有顺手让别的 sheet 掉进/掉出
  I/E 作业面。

## 取值真源（单一真源 + 双向锁死）

manifest 的 `sheet_code` / `api_prefix` / `item_id` / `storage_field` 一律派生自
Key_Ledger = `backend/data/adjustment_ie_contract.json`：

- `sheet_code` ← `sheets` 段里 cycle 首字母 ∈ {L, M, N} 的键
- `api_prefix` ← 同条目 `cycle` 小写（已与 `evidence/route_matrix_x3.json` 的
  `adapter_hit.api_prefix` / `target_after_spec.api_prefix` 三向核对一致）
- `item_id` / `storage_field` ← 同条目同名字段

本文件**不内联**这 16 个 sheet_code（内联等于把作业面抄第二份，Key_Ledger 改了
守卫不会红）。作业面由 `_target_surface()` 每次从 Key_Ledger 现算，并由
`test_anchor_target_surface_is_derived_from_key_ledger` 钉住它的规模与分布 ——
否则「派生集恰好为空」会让下面每一条 `for` 循环空转变绿。

## 两条风险登记为什么落在 yaml 的 `notes:` 段而不是注释里

任务 17.1 / 17.3 各留了一条硬提示给 8.1（`{X}-2` 不得映到 X-3 短前缀 · 专属
router 已派生不出 `{X}-2`）。写进 `#` 注释 = 只有人读得到、守卫读不到、下一轮
删掉不会打红。故落成**文件级 `notes:` 映射**（生成器与 CI 都只读 `entries`，
多这个键无副作用），再由本文件两条断言钉住：

- `test_risk_registrations_are_present_in_notes` —— 六个 notes 键齐全，两条风险
  原文的关键短语逐条在位。
- `test_no_x2_sheet_is_registered_under_x3_prefix` —— 把那条风险落成**结构判
  据**：三份清单里不许出现任何非 `-3` 结尾的 `sheet_code`，且每个 api_prefix 恰
  一条。文字与结构两面都在，删任一面都会红。

## 本任务不写 catalog（R5.2 的边界）

`generate_catalog()` 只算不写（写盘在 `write_catalog()`），catalog 外科补丁属任务
9.1。`test_reverse_selfcheck_catalog_file_untouched_by_generator` 在真跑生成器前后
量 `global_catalog.json` 的 (size, md5)，不变才算过。

## 已知红（不由本文件负责）

`check_catalog_drift` 会因为「committed catalog 尚未含这 16 段」多报 16 条
drift（53 → 69），任务 9.1 的外科补丁抹平后回到 53。本文件
`test_generator_delta_versus_control_is_exactly_the_sixteen` 正是这 16 条的
上界证明：多出来的**只有**本 spec 的作业面，无附带。
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

# ─── 路径 ─────────────────────────────────────────────────────────────────────

_TESTS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TESTS_DIR.parent
_REPO_ROOT = _BACKEND_ROOT.parent

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_LEDGER_PATH = _BACKEND_ROOT / "data" / "adjustment_ie_contract.json"
_SOURCES_DIR = _BACKEND_ROOT / "data" / "acnr" / "sources"
_CATALOG_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"
_GENERATOR_PATH = _BACKEND_ROOT / "scripts" / "acnr" / "generate_catalog.py"

#: 本 spec 作业面所在的三个循环（本文件唯一的字面量声明处）
_PARTIAL_CYCLES: tuple[str, ...] = ("L", "M", "N")

#: 控制组循环（`_ALL_CYCLES` 里非本 spec 新增的那五个）
_CONTROL_CYCLES: tuple[str, ...] = ("d", "k", "f", "g", "h")

#: manifest entry 允许出现的字段（任务 8.1 指定的七个，一个不多一个不少）
_ENTRY_FIELDS: frozenset[str] = frozenset({
    "sheet_code",
    "api_prefix",
    "item_id",
    "storage_field",
    "import_order",
    "depends_on_sheets",
    "notes",
})

#: 文件级 `notes:` 段必须齐全的键
_NOTE_KEYS: frozenset[str] = frozenset({
    "partial_scope",
    "item_id_is_catalog_only",
    "registrar_must_not_map_x2_to_x3_prefix",
    "candidate_surface_drift_x2_not_derivable",
    "depends_on_sheets_empty_rationale",
    "import_order_rationale",
})

#: design.md「manifest 条目」示例给定的次序号（X-3 是其前缀组内第三张）
_EXPECTED_IMPORT_ORDER = 20

_FIXED_REGISTRY_VERSION = "x3-task-8-1-fixed-version"


# ─── 真源读取 ─────────────────────────────────────────────────────────────────


def _ledger() -> dict[str, Any]:
    return json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))


def _target_surface() -> dict[str, dict[str, Any]]:
    """从 Key_Ledger 派生本 spec 作业面：{sheet_code → 期望 manifest 值}。

    不内联 sheet_code —— 作业面规模与分布由 anchor 条钉住。
    """
    sheets = _ledger()["sheets"]
    out: dict[str, dict[str, Any]] = {}
    for code, entry in sheets.items():
        cycle = str(entry.get("cycle", ""))
        if not cycle or cycle[0].upper() not in _PARTIAL_CYCLES:
            continue
        out[code] = {
            "sheet_code": code,
            "api_prefix": cycle.lower(),
            "item_id": entry["item_id"],
            "storage_field": entry["storage_field"],
            "import_order": _EXPECTED_IMPORT_ORDER,
            "depends_on_sheets": [],
            "_key_family": entry["key_family"],
        }
    return out


def _manifest_path(cycle: str) -> Path:
    return _SOURCES_DIR / f"{cycle.lower()}_cycle_ie_manifest.yaml"


def _load_manifest_yaml(cycle: str, *, sources_dir: Path | None = None) -> dict[str, Any]:
    base = sources_dir or _SOURCES_DIR
    path = base / f"{cycle.lower()}_cycle_ie_manifest.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _fingerprint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.md5(raw).hexdigest()


# ─── 判据函数（唯一口径，正反两侧共用）─────────────────────────────────────────


def diff_entries_against_ledger(
    entries: list[dict[str, Any]],
    expected: dict[str, dict[str, Any]],
    *,
    scope: set[str] | None = None,
) -> list[str]:
    """逐条比对 manifest entries 与 Key_Ledger 派生值，返回违规描述列表。

    `scope` 限定应当被覆盖的 sheet_code 集合（默认 = `expected` 全集）。
    正向用例断言返回空；反向自检（改坏/删掉一条）断言返回非空并指名那一条 ——
    同一个函数两侧共用，判据被削弱时反向自检立刻变绿而暴露。
    """
    want_codes = set(scope) if scope is not None else set(expected)
    violations: list[str] = []
    seen: set[str] = set()

    for idx, entry in enumerate(entries):
        code = entry.get("sheet_code")
        if code is None:
            violations.append(f"entries[{idx}] 缺 sheet_code")
            continue
        if code in seen:
            violations.append(f"{code}: sheet_code 重复登记")
        seen.add(code)
        if code not in expected:
            violations.append(f"{code}: 不在 Key_Ledger 派生的作业面内（越界登记）")
            continue

        exp = expected[code]
        extra = set(entry) - _ENTRY_FIELDS
        missing = _ENTRY_FIELDS - set(entry)
        if extra:
            violations.append(f"{code}: 出现未授权字段 {sorted(extra)}")
        if missing:
            violations.append(f"{code}: 缺字段 {sorted(missing)}")

        for field in ("api_prefix", "item_id", "storage_field", "import_order",
                      "depends_on_sheets"):
            if field in entry and entry[field] != exp[field]:
                violations.append(
                    f"{code}.{field} 与 Key_Ledger 派生值不一致 — "
                    f"manifest={entry[field]!r}, expected={exp[field]!r}"
                )

    for code in sorted(want_codes - seen):
        violations.append(f"{code}: Key_Ledger 里有、manifest 里漏登记")

    return violations


def collect_manifest_entries(
    cycles: tuple[str, ...] = _PARTIAL_CYCLES,
    *,
    sources_dir: Path | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cycle in cycles:
        data = _load_manifest_yaml(cycle, sources_dir=sources_dir)
        out.extend(data.get("entries") or [])
    return out


def all_cycles_literal() -> list[str]:
    """从生成器源码 AST 取 `_ALL_CYCLES` 的字面量（函数内局部变量，取不到就抛）。

    这是**结构**判据（补充用），行为判据由 `test_generator_*` 两条承担。
    赋值语句必须恰好一处 —— 多处或零处都说明锚点失效（ANCHOR-MISS），直接抛。
    """
    tree = ast.parse(_GENERATOR_PATH.read_text(encoding="utf-8"))
    found: list[list[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_ALL_CYCLES":
                value = ast.literal_eval(node.value)
                found.append(list(value))
    if len(found) != 1:
        raise AssertionError(
            f"锚点失效：generate_catalog.py 里 `_ALL_CYCLES` 赋值命中 {len(found)} 处（应恰 1 处）"
        )
    return found[0]


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def expected() -> dict[str, dict[str, Any]]:
    return _target_surface()


@pytest.fixture(scope="module")
def generated_all() -> dict[str, Any]:
    """真跑一次生成器（`cycle='all'`，离线），返回 {sheet_code → sheet dict}。"""
    from scripts.acnr.generate_catalog import generate_catalog

    catalog_data, _report, _blocked = generate_catalog(
        offline=True, registry_version=_FIXED_REGISTRY_VERSION
    )
    return {s["sheet_code"]: s for s in catalog_data["sheets"]}


# ═════════════════════════════════════════════════════════════════════════════
# 锚点（先钉住判据面本身，防「作业面为空 ⇒ 每条 for 空转变绿」）
# ═════════════════════════════════════════════════════════════════════════════


def test_anchor_target_surface_is_derived_from_key_ledger(expected):
    """作业面规模与分布双向锁死：16 张 = L 2 + M 10 + N 4，且每张四字段非空。"""
    assert len(expected) == 16, f"Key_Ledger 派生的 L/M/N 作业面应为 16 张，实测 {len(expected)}"

    dist = {c: sorted(k for k in expected if k[0] == c) for c in _PARTIAL_CYCLES}
    assert len(dist["L"]) == 2, dist["L"]
    assert len(dist["M"]) == 10, dist["M"]
    assert len(dist["N"]) == 4, dist["N"]

    for code, exp in expected.items():
        assert code.endswith("-3"), f"{code}: 作业面只含 X-3 调整分录汇总表"
        assert exp["api_prefix"] and exp["api_prefix"] == exp["api_prefix"].lower()
        assert exp["item_id"], code
        assert exp["storage_field"] in {"remark", "conclusion"}, (code, exp["storage_field"])
        assert exp["_key_family"] in {"single_json", "per_field", "per_field_plus_data"}


def test_anchor_three_manifests_exist_with_house_eol_and_partial_flag():
    """三份清单存在、行尾与既有 manifest 同款、`partial: true` 在位。

    行尾口径**不写死**：从 `sources/` 下既有 `*_cycle_ie_manifest.yaml` 现算
    （实测既有 5 份全纯 CRLF），新文件必须同款。
    """
    existing = [
        p for p in sorted(_SOURCES_DIR.glob("*_cycle_ie_manifest.yaml"))
        if p.stem.split("_")[0].upper() not in _PARTIAL_CYCLES
    ]
    assert len(existing) >= 4, f"既有 manifest 少于 4 份，行尾口径无从取样：{existing}"

    def eol_of(path: Path) -> str:
        raw = path.read_bytes()
        crlf = raw.count(b"\r\n")
        lf_only = raw.count(b"\n") - crlf
        if crlf and not lf_only:
            return "pure_crlf"
        if lf_only and not crlf:
            return "pure_lf"
        return f"mixed(crlf={crlf}, lf_only={lf_only})"

    house = {eol_of(p) for p in existing}
    assert len(house) == 1, f"既有 manifest 行尾不统一，无法取样：{ {p.name: eol_of(p) for p in existing} }"
    house_eol = house.pop()

    for cycle in _PARTIAL_CYCLES:
        path = _manifest_path(cycle)
        assert path.exists(), f"{path} 不存在"
        assert eol_of(path) == house_eol, (
            f"{path.name} 行尾 {eol_of(path)} 与既有 manifest 口径 {house_eol} 不同款"
        )
        data = _load_manifest_yaml(cycle)
        assert data.get("cycle") == cycle, (cycle, data.get("cycle"))
        assert data.get("version") == "1", (cycle, data.get("version"))
        assert data.get("partial") is True, (
            f"{path.name} 缺 `partial: true` —— 部分登记标记是任务 8.2 判「未覆盖条目数」的前提"
        )


def test_anchor_loader_is_live_on_a_temp_dir(tmp_path):
    """`load_ie_manifest` 真读磁盘的正/负对照，防上面几条靠一个坏掉的 loader 空转。"""
    from app.services.acnr.loaders.from_ie_manifest import load_ie_manifest

    probe = (
        'version: "1"\n'
        "cycle: Z\n"
        "partial: true\n"
        "entries:\n"
        "  - sheet_code: Z9-3\n"
        "    api_prefix: z9\n"
        '    item_id: "Z9-3-entry-*"\n'
        "    storage_field: remark\n"
        "    import_order: 20\n"
        "    depends_on_sheets: []\n"
        "    notes: probe\n"
    )
    (tmp_path / "z_cycle_ie_manifest.yaml").write_text(probe, encoding="utf-8")

    loaded = load_ie_manifest("z", sources_dir=tmp_path)
    assert set(loaded) == {"Z9-3"}, loaded
    assert loaded["Z9-3"]["api_prefix"] == "z9"
    assert loaded["Z9-3"]["item_id"] == "Z9-3-entry-*"
    assert loaded["Z9-3"]["enabled"] is True

    with pytest.raises(FileNotFoundError):
        load_ie_manifest("zzz", sources_dir=tmp_path)


# ═════════════════════════════════════════════════════════════════════════════
# 核心（行为）
# ═════════════════════════════════════════════════════════════════════════════


def test_loader_derives_sixteen_entries_from_the_three_manifests(expected):
    """生成器用的那个 loader 真能加载三份新清单，并派生出 16 条。"""
    from app.services.acnr.loaders.from_ie_manifest import load_ie_manifest

    per_cycle = {c: load_ie_manifest(c.lower()) for c in _PARTIAL_CYCLES}
    assert len(per_cycle["L"]) == 2, sorted(per_cycle["L"])
    assert len(per_cycle["M"]) == 10, sorted(per_cycle["M"])
    assert len(per_cycle["N"]) == 4, sorted(per_cycle["N"])

    union: dict[str, dict[str, Any]] = {}
    for seg in per_cycle.values():
        union.update(seg)
    assert len(union) == 16, sorted(union)
    assert set(union) == set(expected), (
        f"loader 派生集与 Key_Ledger 作业面不等 — "
        f"多 {sorted(set(union) - set(expected))} / 少 {sorted(set(expected) - set(union))}"
    )

    for code, seg in union.items():
        exp = expected[code]
        assert seg["enabled"] is True, code
        assert seg["api_prefix"] == exp["api_prefix"], code
        assert seg["item_id"] == exp["item_id"], code
        assert seg["storage_field"] == exp["storage_field"], code
        assert seg["import_order"] == exp["import_order"], code
        assert seg["depends_on_sheets"] == [], code


def test_manifest_fields_equal_key_ledger_values(expected):
    """R5.3：逐字段等于 Key_Ledger 派生值，且只写任务 8.1 指定的七个字段。"""
    entries = collect_manifest_entries()
    assert len(entries) == 16, len(entries)
    violations = diff_entries_against_ledger(entries, expected)
    assert violations == [], "manifest 与 Key_Ledger 不一致：\n  " + "\n  ".join(violations)


def test_generator_all_cycles_derives_the_sixteen_import_export_segments(
    expected, generated_all
):
    """真跑 `generate_catalog(offline=True)`：16 张的 `import_export` 段逐字段在位。"""
    missing = [c for c in expected if c not in generated_all]
    assert missing == [], f"catalog 骨架里找不到这些 sheet_code：{missing}"

    for code, exp in expected.items():
        seg = generated_all[code].get("import_export")
        assert seg is not None, (
            f"{code}: 生成器未派生出 import_export 段 —— "
            f"`_ALL_CYCLES` 漏了该循环，或 manifest 未被加载"
        )
        assert seg == {
            "enabled": True,
            "api_prefix": exp["api_prefix"],
            "item_id": exp["item_id"],
            "storage_field": exp["storage_field"],
            "import_order": exp["import_order"],
            "depends_on_sheets": [],
        }, f"{code}: import_export 段与 Key_Ledger 派生值不等 — {seg}"


def test_generator_delta_versus_control_is_exactly_the_sixteen(expected, generated_all):
    """零附带：`cycle='all'` 相对控制组 d+k+f+g+h 的 I/E 增量恰为这 16 张。"""
    from scripts.acnr.generate_catalog import generate_catalog

    control: set[str] = set()
    for cycle in _CONTROL_CYCLES:
        catalog_data, _r, _b = generate_catalog(
            offline=True, registry_version=_FIXED_REGISTRY_VERSION, cycle=cycle
        )
        control |= {
            s["sheet_code"] for s in catalog_data["sheets"] if s.get("import_export")
        }
    assert len(control) > 100, f"控制组 I/E 面异常小（{len(control)}），控制组本身可能空转"

    live = {code for code, s in generated_all.items() if s.get("import_export")}
    delta = live - control
    assert delta == set(expected), (
        f"增量不等于作业面 — 多 {sorted(delta - set(expected))} / 少 {sorted(set(expected) - delta)}"
    )
    assert control - live == set(), f"控制组有条目在 all 下消失：{sorted(control - live)}"


def test_all_cycles_literal_includes_the_three_partial_cycles():
    """结构判据（补充）：`_ALL_CYCLES` 恰好在既有五项后追加 l/m/n，次序不打乱。"""
    literal = all_cycles_literal()
    assert literal == list(_CONTROL_CYCLES) + [c.lower() for c in _PARTIAL_CYCLES], literal
    assert len(literal) == len(set(literal)), f"`_ALL_CYCLES` 有重复项：{literal}"


# ═════════════════════════════════════════════════════════════════════════════
# 风险登记落成判据（17.1 / 17.3 交接项）
# ═════════════════════════════════════════════════════════════════════════════


def test_no_x2_sheet_is_registered_under_x3_prefix(expected):
    """任务 17.1 的风险登记落成**结构**判据。

    实测：经 X-3 短前缀取既有 `{X}-2` 一律 400（`不支持的sheet: M2-2。支持:
    ['M2-3']`）⇒ 三份清单里不许出现任何非 `-3` 结尾的 sheet_code，且每个
    api_prefix 恰一条（多一条即意味着有人把 X-2 挂到了同一前缀下）。
    """
    entries = collect_manifest_entries()
    offenders = [e["sheet_code"] for e in entries if not str(e["sheet_code"]).endswith("-3")]
    assert offenders == [], (
        f"这些 sheet_code 不是 X-3，登记到 X-3 短前缀下会 400：{offenders}"
    )

    per_prefix: dict[str, list[str]] = {}
    for e in entries:
        per_prefix.setdefault(e["api_prefix"], []).append(e["sheet_code"])
    dup = {p: codes for p, codes in per_prefix.items() if len(codes) != 1}
    assert dup == {}, f"同一 api_prefix 下登记了多张 sheet：{dup}"
    assert len(per_prefix) == 16, sorted(per_prefix)

    # X-2 的具体码也逐个不许出现（防「结尾判据被削成 startswith」这类放水）
    x2_codes = {code[:-1] + "2" for code in expected}
    registered = {e["sheet_code"] for e in entries}
    assert registered & x2_codes == set(), sorted(registered & x2_codes)


def test_risk_registrations_are_present_in_notes():
    """两条风险登记与 `item_id` 语义说明必须写在可被读取的 `notes:` 段里。"""
    phrases_17_1 = (
        "登记器不得把 {X}-2 映到 X-3 短前缀",
        "不支持的sheet: M2-2",
        "16/16",
        "变成用户可见",
    )
    phrases_17_3 = (
        "candidate_surface_drift",
        "已派生不出来",
        "M1-4",
        "N2-6",
        "不把 {X}-2 一起登记进去",
    )
    phrases_item_id = (
        "族键通配串",
        "bulk 不按它取数",
        "key_family",
        "目录/溯源",
    )

    for cycle in _PARTIAL_CYCLES:
        data = _load_manifest_yaml(cycle)
        notes = data.get("notes")
        assert isinstance(notes, dict), f"{cycle}: 缺文件级 notes: 段"
        assert set(notes) == set(_NOTE_KEYS), (
            f"{cycle}: notes 键集不符 — 多 {sorted(set(notes) - _NOTE_KEYS)} / "
            f"少 {sorted(_NOTE_KEYS - set(notes))}"
        )
        for key, phrases in (
            ("registrar_must_not_map_x2_to_x3_prefix", phrases_17_1),
            ("candidate_surface_drift_x2_not_derivable", phrases_17_3),
            ("item_id_is_catalog_only", phrases_item_id),
        ):
            text = notes[key]
            for phrase in phrases:
                assert phrase in text, f"{cycle}.notes.{key} 缺短语「{phrase}」：{text[:120]}"


def test_entry_notes_state_item_id_is_directory_only(expected):
    """∀16 条 entry 的 notes 写明取数不走 item_id；通配与单键两态不许互相冒充。"""
    entries = {e["sheet_code"]: e for e in collect_manifest_entries()}
    assert set(entries) == set(expected)

    wildcard_codes = set()
    for code, entry in entries.items():
        note = entry["notes"]
        assert "bulk 不按 item_id 取数" in note, f"{code}: notes 未写明 bulk 不按 item_id 取数"
        assert "key_family" in note, f"{code}: notes 未写明取数依 key_family"
        assert "目录/溯源" in note, f"{code}: notes 未写明 item_id 仅作目录/溯源"

        fam = expected[code]["_key_family"]
        has_star = "*" in str(entry["item_id"])
        claims_family_key = "族键通配串" in note
        assert has_star == claims_family_key, (
            f"{code}: item_id 通配形态（{has_star}）与 notes 措辞（{claims_family_key}）互相打架"
        )
        assert has_star == (fam != "single_json"), (
            f"{code}: key_family={fam} 与 item_id 通配形态 {has_star} 不符"
        )
        assert fam in note, f"{code}: notes 未写明 key_family 取值 {fam}"
        if has_star:
            wildcard_codes.add(code)

    # 两态都非空 ⇒ 上面的双向断言不是在单态上空转
    assert len(wildcard_codes) == 11, sorted(wildcard_codes)
    assert len(set(entries) - wildcard_codes) == 5, sorted(set(entries) - wildcard_codes)


# ═════════════════════════════════════════════════════════════════════════════
# 反向自检
# ═════════════════════════════════════════════════════════════════════════════


def test_reverse_selfcheck_judge_catches_broken_and_missing_entries(tmp_path, expected):
    """删掉/改坏任一条必须被判据抓到（同一个 `diff_entries_against_ledger`）。"""
    good = collect_manifest_entries()
    assert diff_entries_against_ledger(good, expected) == []

    # ① 改坏 item_id
    broken = [dict(e) for e in good]
    victim = next(e for e in broken if e["sheet_code"] == "M4-3")
    victim["item_id"] = "M4-3-entry-MUTATED"
    got = diff_entries_against_ledger(broken, expected)
    assert any("M4-3.item_id" in v for v in got), got

    # ② 删掉一条
    dropped = [e for e in good if e["sheet_code"] != "N3-3"]
    got = diff_entries_against_ledger(dropped, expected)
    assert any(v.startswith("N3-3:") and "漏登记" in v for v in got), got

    # ③ 越界登记 X-2
    overreach = [dict(e) for e in good] + [{
        "sheet_code": "M2-2",
        "api_prefix": "m2",
        "item_id": "M2-2-rows",
        "storage_field": "remark",
        "import_order": 10,
        "depends_on_sheets": [],
        "notes": "probe",
    }]
    got = diff_entries_against_ledger(overreach, expected)
    assert any("M2-2" in v and "越界登记" in v for v in got), got

    # ④ 多写一个未授权字段
    extra = [dict(e) for e in good]
    extra[0] = {**extra[0], "storage_mode": "row_json"}
    got = diff_entries_against_ledger(extra, expected)
    assert any("未授权字段" in v for v in got), got

    # ⑤ 落盘态复算：把 m 清单删掉一条真写到 tmp 目录再从磁盘读回，判据仍抓到
    m_data = _load_manifest_yaml("M")
    m_data["entries"] = [e for e in m_data["entries"] if e["sheet_code"] != "M9-3"]
    (tmp_path / "m_cycle_ie_manifest.yaml").write_text(
        yaml.safe_dump(m_data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    from_disk = _load_manifest_yaml("M", sources_dir=tmp_path)["entries"]
    m_scope = {c for c in expected if c.startswith("M")}
    got = diff_entries_against_ledger(from_disk, expected, scope=m_scope)
    assert any(v.startswith("M9-3:") and "漏登记" in v for v in got), got


def test_reverse_selfcheck_absent_cycle_yields_no_segments(expected):
    """16 段确实来自这三份清单：换一个不存在的循环码，16 张一段都拿不到。"""
    from scripts.acnr.generate_catalog import generate_catalog

    catalog_data, _r, _b = generate_catalog(
        offline=True, registry_version=_FIXED_REGISTRY_VERSION, cycle="zzz"
    )
    by_code = {s["sheet_code"]: s for s in catalog_data["sheets"]}
    hit = [c for c in expected if by_code.get(c, {}).get("import_export")]
    assert hit == [], (
        f"这些 sheet 在未加载任何 manifest 时也带 import_export ⇒ 上面的判据可能来自"
        f"别的输入源（overrides / classification），不是本任务的三份清单：{hit}"
    )


def test_reverse_selfcheck_catalog_file_untouched_by_generator():
    """R5.2 边界：本任务只算不写 —— 真跑生成器前后 catalog 文件逐字节不变。"""
    from scripts.acnr.generate_catalog import generate_catalog

    before = _fingerprint(_CATALOG_PATH)
    generate_catalog(offline=True, registry_version=_FIXED_REGISTRY_VERSION)
    after = _fingerprint(_CATALOG_PATH)
    assert before == after, f"generate_catalog 写了 catalog：{before} → {after}"
