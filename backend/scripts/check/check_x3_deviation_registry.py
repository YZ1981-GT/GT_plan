#!/usr/bin/env python3
"""check_x3_deviation_registry.py — X-3 已知偏差登记表（`Deviation_Registry`）的探针与守卫

spec: `.kiro/specs/x3-adjustment-entry-import-export/`（任务 1.7）
落点: `.kiro/specs/x3-adjustment-entry-import-export/evidence/deviation_registry.json`
需求: R8.3 / R8.4 / R8.5 / R8.6 / R8.7 / R5.8；设计: design §C7（十一组 G1~G11）

## 这张表存在的理由（R8.6）

本 spec 的守卫基线**只收已确证正确的值**。已判定为错位的值一律由本登记表承载 ——
否则守卫要么把错值锁成基线（假绿三源之三），要么绕开它们（下一轮重复勘查）。

## 自我失效（R8.7）—— 本脚本的核心

每组带 `baseline_count`。`--check` 用**活探针**重算实测数，并按三态判：

| 实测 vs 基线 | 状态 | 语义 |
|---|---|---|
| 相等 | `OK` | 收口 |
| 实测 > 基线 | `REGRESSION` | 新增偏差 ⇒ 打红 |
| 实测 < 基线 | `NEEDS_BASELINE_LOWERING` | 有条目被修好 ⇒ **要求同步下调基线**，不下调即打红 |

⇒ 「某条被别的 spec 修好」不会让本表静默留着一个虚高的基线继续绿。
下调基线的唯一合法形态：JSON 里同时给出 `baseline_lowered_from`（= design §C7 原值）
与 `lowered_by_task`。否则 `--check` 判 `STRUCTURE_ERROR`（防「为了变绿随手改基线」）。

## 反空转（每组必须自证探针没瞎）

每组探针返回 `selfcheck`：扫描面规模下界 + **对照组**。对照组不成立即整组打红，
例如：

- G6 的对照组 = 工厂 `_cycle_import_export_common._validate` 必须被判为「对未知
  sheet 抛可读错误」。若连它都判 False ⇒ 探针失效（而不是「M 族没毛病」）。
- G8 的对照组 = 其余 15 张 X-3 的第 2 行标题必须与模板文件业务名相容、第 3 行标签
  无重复。若 16 张全被判异常 ⇒ 判据失效。
- G10 的对照组 = 至少 10 张必须判为「有读回」（收口后 16/16）。若 16 张全判「只写不读」
  ⇒ 判据失效。**另注（任务 11.2 的显式裁决）**：G10 只判「读回表达式存在」这一层，弱于
  R6.5 / R6.7；行为层（`@imported` 是否真连到那条读回）由前端守卫 `GS5b` 承载，本组探针
  只对它做**承载者在位性**交叉引用锁（见 `_gs5b_carrier`）—— 承载者一旦消失，G10 打红。

## `method` 必须可复算（R8.5）

每组的 `method` 是**逐步命令/步骤**。`--check` 扫禁用措辞（「本地执行」「经核实」等）
—— 那类措辞下一轮无法复算，等于没有依据。

## 裁决 2 的登记形态（design §用户裁决 2）

G2 / G3 各带 `ci_job` 三字段：`observed_exit_code` / `observed_at` / `reproduce_cmd`。
`--check` 断言三字段在位且 `reproduce_cmd` 指向的脚本文件真实存在；
`--verify-ci` 会**真跑一遍**这两条命令并比对退出码（默认关，约 2~4 分钟）。

## 用法

    python backend/scripts/check/check_x3_deviation_registry.py --check
    python backend/scripts/check/check_x3_deviation_registry.py --check --verify-ci
    python backend/scripts/check/check_x3_deviation_registry.py --emit          # 唯一写盘路径
    python backend/scripts/check/check_x3_deviation_registry.py --emit --set-baselines --lowered-by-task 11.2

## 状态演进（下一轮别把「exit 2」当回归）

| 时点 | 预期 | 谁来收 |
|---|---|---|
| 今天（Wave 0 任务 1.7 交付时） | 十组 `OK` + `G1 PENDING` ⇒ **exit 2** | —— |
| 任务 4.2 + 11.1 施加后 | G10 实测降到 0 ⇒ `NEEDS_BASELINE_LOWERING` | 任务 11.2 按规范下调 G10 基线到 0（**已收**：`baseline_lowered_from=4` + `lowered_by_task=11.2`） |
| 任务 13.1 落值后 | G1 补齐 16 条、`status` 改 `measured`、并实现 numerator 活探针 | 任务 13.1 |
| 任务 14.2 挂 CI 时 | 上面两项都已收 ⇒ **exit 0** | 任务 14.2 |

退出码：`0` 全组收口 / `2` 未收口（drift / pending / 结构错） / `1` 脚本自身异常。
`--emit` **不会**顺手改 `baseline_count`（那会让自我失效机制形同虚设）；确实要改基线
必须显式加 `--set-baselines`，且须用 `--lowered-by-task <任务号>` 点名下调者 ——
缺省只写占位值，`--check` 判 `STRUCTURE_ERROR`（占位文案非空，糊不过去）。

只读边界：除 `--emit` 写上述 JSON 外，本脚本不写任何文件；`backend/wp_templates/`
全程 `read_only=True`（R11.1）。
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ─── UTF-8 输出（PS 下中文/箭头字符会 GBK 崩）────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]                     # backend/scripts/check → GT_plan
BACKEND = ROOT / "backend"
SPEC_DIR = ROOT / ".kiro" / "specs" / "_archive" / "05-business-features" / "x3-adjustment-entry-import-export"
REGISTRY_PATH = SPEC_DIR / "evidence" / "deviation_registry.json"
FE_SRC = ROOT / "audit-platform" / "frontend" / "src"
WP_DIR = FE_SRC / "components" / "workpaper"
ACNR_SOURCES = BACKEND / "data" / "acnr" / "sources"
CONTRACT_PATH = BACKEND / "data" / "adjustment_ie_contract.json"
GENERATED_REGISTRY = WP_DIR / "shared" / "cycleImportExportRegistry.generated.ts"
GENERATE_CATALOG = BACKEND / "scripts" / "acnr" / "generate_catalog.py"
OVERRIDES_PATH = BACKEND / "data" / "acnr" / "global_catalog.overrides.json"
FACTORY_COMMON = BACKEND / "app" / "routers" / "wp_render_strategies" / "_cycle_import_export_common.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("JWT_SECRET_KEY", "x3-deviation-registry-check-only")

_THREE_STATE: tuple[str, ...] = ("export-template", "export-data", "import-data")
_ADJ_CLASS_CODE = "F-调整分录"
_VERDICTS = ("real_drift", "probe_false_negative")

#: 🔴 design §C7 的十一组基线（逐字转录）。**只许按 spec 任务显式下调**，
#: 且下调时 JSON 侧必须同时给出 `baseline_lowered_from` + `lowered_by_task`。
_DESIGN_BASELINE: dict[str, int] = {
    "G1": 16, "G2": 38, "G3": 15, "G4": 5, "G5": 8, "G6": 10,
    "G7": 2, "G8": 1, "G9": 1, "G10": 4, "G11": 1,
}

#: `method` 里禁止出现的不可复算措辞（R8.5）
_FORBIDDEN_METHOD_PHRASES: tuple[str, ...] = (
    "本地执行", "经核实", "已核实", "人工确认", "凭经验", "应该是", "大概", "据说",
)

_PENDING_STATUS = "pending"
_MEASURED_STATUS = "measured"

#: `--set-baselines` 未给 `--lowered-by-task` 时写入的占位值。
#: 🔴 `--check` 显式拒绝它 —— 否则「下调基线必须点名任务」会被一句占位文案糊过去
#: （占位值非空，旧版 `not group.get("lowered_by_task")` 判不出来）。
_LOWERED_BY_PLACEHOLDER = "（须填写下调该基线的任务号）"

#: `lowered_by_task` 的合法形态：spec 任务号（`11.2` / `13.1` / `4` 均可）
_RE_TASK_NO = re.compile(r"^\d+(?:\.\d+)*$")


# ═══════════════════════════════════════════════════════════════════════════════
# 通用取值层（缓存；任何异常一律向上抛，不吞成 WARNING —— 见 R10.11 的教训）
# ═══════════════════════════════════════════════════════════════════════════════

_CACHE: dict[str, Any] = {}


def _cached(key: str, producer: Callable[[], Any]) -> Any:
    if key not in _CACHE:
        _CACHE[key] = producer()
    return _CACHE[key]


def _read(path: Path) -> str:
    """磁盘真相：显式 UTF-8；前端存量文件里有 mojibake 注释，故 errors='replace'。"""
    return path.read_text(encoding="utf-8", errors="replace")


def _app() -> Any:
    def _load() -> Any:
        from app.main import app  # noqa: PLC0415

        return app

    return _cached("app", _load)


def _catalog_sheets() -> list[dict[str, Any]]:
    def _load() -> list[dict[str, Any]]:
        from app.services.acnr.catalog import list_sheets  # noqa: PLC0415

        return list(list_sheets())

    return _cached("catalog", _load)


def _ie(entry: dict[str, Any]) -> dict[str, Any]:
    """null-safe 取 `import_export`（实测该键多为**整段缺失**而非显式 null）。"""
    return entry.get("import_export") or {}


def _catalog_by_code() -> dict[str, dict[str, Any]]:
    return _cached("catalog_by_code", lambda: {s.get("sheet_code"): s for s in _catalog_sheets()})


def _catalog_enabled() -> list[dict[str, Any]]:
    return _cached("catalog_enabled", lambda: [s for s in _catalog_sheets() if _ie(s).get("enabled")])


def _catalog_prefix_sheets() -> dict[str, list[str]]:
    def _load() -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for s in _catalog_enabled():
            prefix = _ie(s).get("api_prefix")
            if prefix:
                out.setdefault(prefix, []).append(s.get("sheet_code", "?"))
        return {k: sorted(v, key=_natural) for k, v in out.items()}

    return _cached("catalog_prefix_sheets", _load)


def _manifest_entries() -> dict[str, dict[str, Any]]:
    def _load() -> dict[str, dict[str, Any]]:
        import yaml  # noqa: PLC0415

        out: dict[str, dict[str, Any]] = {}
        for f in sorted(ACNR_SOURCES.glob("*_cycle_ie_manifest.yaml")):
            doc = yaml.safe_load(_read(f)) or {}
            for e in doc.get("entries") or []:
                code = e.get("sheet_code")
                if code:
                    out[code] = {**e, "_file": f.name}
        return out

    return _cached("manifest", _load)


def _manifest_files() -> list[str]:
    return sorted(f.name for f in ACNR_SOURCES.glob("*_cycle_ie_manifest.yaml"))


def _generator_cycles() -> list[str]:
    """从 `generate_catalog.py` 源码取 `_ALL_CYCLES` 字面量（生成链的实际加载面）。

    🔴 锚点纪律：该常量在函数体内（有缩进），故行首锚点必须允许缩进；命中数不等于 1
    时抛错而不是静默返回空列表 —— 返空会让 G2 的「manifest 与生成器一致」判据恒红/恒绿。
    """
    def _load() -> list[str]:
        src = _read(GENERATE_CATALOG)
        hits = re.findall(r"^\s*_ALL_CYCLES\s*(?::[^=\n]+)?=\s*\[([^\]]*)\]", src, re.M)
        if len(hits) != 1:
            raise RuntimeError(
                f"`_ALL_CYCLES` 在 {GENERATE_CATALOG.name} 里命中 {len(hits)} 处（期望 1）—— 锚点失效，先核对源码"
            )
        return re.findall(r"[\"']([a-z]+)[\"']", hits[0])

    return _cached("gen_cycles", _load)


def _contract() -> dict[str, Any]:
    return _cached("contract", lambda: json.loads(_read(CONTRACT_PATH)))


def _contract_item_id(sheet_code: str) -> tuple[str | None, str]:
    """契约清单侧的 `item_id` 现值 → (值, 取值路径)。未登记/豁免则值为 None。"""
    doc = _contract()
    sheets = doc.get("sheets", {}) or {}
    if sheet_code in sheets:
        return sheets[sheet_code].get("item_id"), f"sheets.{sheet_code}.item_id"
    exempt = doc.get("exempt", {}) or {}
    if sheet_code in exempt and not sheet_code.startswith("_"):
        kind = (exempt[sheet_code] or {}).get("kind")
        return None, f"exempt.{sheet_code}(kind={kind})"
    return None, "未登记"


_RE_GEN_ENTRY = re.compile(
    r"^\s+'?([A-Za-z0-9_-]+)'?:\s*\{\s*apiPrefix:\s*'([^']+)',\s*sheets:\s*\[([^\]]*)\]",
    re.M,
)


def _generated_registry() -> dict[str, list[str]]:
    """前端派生 registry：`apiPrefix` → sheets（用户点下拉真正会打的前缀与 sheet）。"""
    def _load() -> dict[str, list[str]]:
        src = _read(GENERATED_REGISTRY)
        return {
            m.group(2): re.findall(r"'([^']+)'", m.group(3))
            for m in _RE_GEN_ENTRY.finditer(src)
        }

    return _cached("gen_registry", _load)


def _dropdown_mounts() -> dict[str, list[str]]:
    """前端 `api-prefix="<p>"` 的渲染点（排除 `__tests__`）→ {前缀: [file:line]}。"""
    def _load() -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for p in sorted(WP_DIR.rglob("*.vue")):
            posix = p.as_posix()
            if "__tests__" in posix:
                continue
            src = _read(p)
            for m in re.finditer(r"api-prefix\s*=\s*\"([^\"]+)\"", src):
                val = m.group(1).strip().strip("'").strip()
                line = src[: m.start()].count("\n") + 1
                out.setdefault(val, []).append(f"{p.relative_to(FE_SRC).as_posix()}:{line}")
        return out

    return _cached("dropdowns", _load)


def _x3_targets() -> tuple[str, ...]:
    """16 张作业面 —— 直接复用 Wave 0 任务 1.3 已声明的那一份，不留第二份清单。"""
    def _load() -> tuple[str, ...]:
        mod = importlib.import_module("tests.test_x3_catalog_registration")
        targets = tuple(getattr(mod, "_TARGET_SHEETS"))
        if len(targets) != 16:
            raise RuntimeError(f"作业面清单规模异常：{len(targets)} != 16 —— 上游被改动，先核对再跑")
        return targets

    return _cached("targets", _load)


def _short_prefix(sheet_code: str) -> str:
    """`M10-3` → `m10`（短前缀由 sheet_code 派生，不写第二份映射表）。"""
    return sheet_code.split("-", 1)[0].lower()


def _natural(text: str) -> tuple[Any, ...]:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text or ""))


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ═══════════════════════════════════════════════════════════════════════════════
# 探针返回体
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Probe:
    """一组的活探针结果。

    `measured` 为 None 表示该组尚无可复算实测数（`status = pending`），此时
    `--check` 不做「实测 vs 基线」比较，改判 `PENDING` 并要求 `owner_task` 在位。
    """

    measured: int | None
    entries: list[dict[str, Any]]
    selfcheck_ok: bool = True
    selfcheck_notes: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _entry(
    *,
    group: str,
    key: str,
    catalog_value: Any,
    contract_value: Any,
    frontend_observed: Any,
    na_reasons: dict[str, str] | None = None,
    verdict: str,
    evidence: dict[str, Any],
    sheet_code: str | None = None,
) -> dict[str, Any]:
    """一条偏差记录。三列（R8.4）恒在位；为 None 的列必须带 `na_reasons`。"""
    out: dict[str, Any] = {
        "group": group,
        "key": key,
        "sheet_code": sheet_code,
        "catalog_value": catalog_value,
        "contract_value": contract_value,
        "frontend_observed": frontend_observed,
        "verdict": verdict,
        "method_ref": f"{group}.method",
        "evidence": evidence,
    }
    if na_reasons:
        out["na_reasons"] = na_reasons
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# G1 —— catalog `item_id` 在前端无消费方（16；逐条落值属任务 13.1）
# ═══════════════════════════════════════════════════════════════════════════════

def probe_g1() -> Probe:
    """G1 活探针：逐条判 catalog `item_id` 在前端生产代码是否有消费方。

    四形态判据（design §C6，R7.4，任务 1.9 交付）的 Python 等价实现：
      ① 引号字面量：直接在前端生产文件字面搜索 `item_id`
      ② `ITEM_PREFIX` 同文件拼接：搜索 `item_id` 字面量命中
      ③ 模板字面量逐字段族：item_id 含 `*` 时，取前缀（去 `*`）搜索
      ④ 跨文件运行期拼装：从 `use{X}FormData.ts` 的 `ITEM_PREFIX` + 拼装逻辑判
         item_id 是否由该前缀派生而出；或从 `{X}TabAdjust*.vue` 的 `ITEM_PREFIX`

    numerator = 无消费方的条目数。verdict 按三向比对：
      - 有契约清单对照键且前端有消费该键 → `real_drift`（catalog 记错，前端用真键）
      - 无契约对照 / 前端对真键也无消费 → `real_drift`（通路真缺失）
      - 判据不能排除形态④假阴性 → `probe_false_negative`
    """
    fadj = [s for s in _catalog_sheets() if s.get("class_code") == _ADJ_CLASS_CODE]
    fadj_ie = [s for s in fadj if _ie(s).get("enabled")]
    denominator = len(fadj_ie)

    # ─── 四形态搜索 ─────────────────────────────────────────────────────────
    entries: list[dict[str, Any]] = []
    consumer_found_codes: list[str] = []

    for entry in sorted(fadj_ie, key=lambda x: _natural(x.get("sheet_code", ""))):
        code = entry.get("sheet_code", "?")
        ie = _ie(entry)
        item_id = ie.get("item_id", "")

        # 纯 catalog item_id 搜索（形态①②③）
        found_catalog = _g1_has_consumer_literal(item_id)

        if found_catalog:
            consumer_found_codes.append(code)
            continue

        # 形态④：跨文件 ITEM_PREFIX 拼装检查
        found_form4 = _g1_has_consumer_form4(code, item_id)
        if found_form4:
            consumer_found_codes.append(code)
            continue

        # ─── 无消费方 → 构建 entry ──────────────────────────────────────────
        contract_val, contract_path = _contract_item_id(code)
        # 尝试用契约值搜一遍（判 real_drift vs probe_false_negative）
        contract_has_consumer = False
        if contract_val and contract_val != item_id:
            contract_has_consumer = _g1_has_consumer_literal(contract_val)
            if not contract_has_consumer:
                contract_has_consumer = _g1_has_consumer_form4(code, contract_val)

        # verdict 判定
        if contract_has_consumer:
            verdict = "real_drift"
            fe_observed = contract_val
            note = f"前端用契约值 {contract_val!r} 消费（catalog 记错）"
        elif contract_val and contract_val != item_id:
            # 有契约对照但前端对它也无消费 → 通路真缺失
            verdict = "real_drift"
            fe_observed = None
            note = f"契约值 {contract_val!r} 在前端亦无消费 → 通路缺失"
        else:
            # 无契约对照
            verdict = "real_drift"
            fe_observed = None
            note = "catalog item_id 在前端无消费方、无契约对照"

        catalog_hits = _frontend_production_hits(item_id, limit=3)

        # na_reasons 构建：null 列必须有说明
        na_reasons: dict[str, str] = {}
        if fe_observed is None:
            na_reasons["frontend_observed"] = note
        if contract_val is None:
            na_reasons["contract_value"] = (
                f"契约清单 adjustment_ie_contract.json 无 sheets.{code} 登记"
            )

        entries.append(
            _entry(
                group="G1",
                key=code,
                sheet_code=code,
                catalog_value=item_id,
                contract_value=contract_val,
                frontend_observed=fe_observed,
                verdict=verdict,
                evidence={
                    "contract_path": contract_path or "未登记",
                    "catalog_value_frontend_hits": catalog_hits,
                    "note": note,
                    "search_method": "四形态判据（literal + prefix_wildcard + ITEM_PREFIX_form4）",
                },
                na_reasons=na_reasons if na_reasons else None,
            )
        )

    # ─── selfcheck ──────────────────────────────────────────────────────────
    notes: list[str] = []
    ok = True
    if denominator < 40:
        ok = False
        notes.append(f"分母扫描面异常小（{denominator} < 40）—— catalog 读取可能失效")
    if len(consumer_found_codes) < 40:
        ok = False
        notes.append(
            f"有消费方的条目数异常少（{len(consumer_found_codes)} < 40）—— 搜索面可能失效"
        )
    # 对照组：K8-3（X3-scope，已知有消费方）不应出现在 entries 里
    k8_in_entries = any(e["key"] == "K8-3" for e in entries)
    # K8 的 catalog value 是 'K8-3-rows'，前端真键是 'K8-3-adj-entries'（ITEM_PREFIX='K8-3-adj'）
    # 如果 K8 出现在 entries → 形态④搜索失效
    if k8_in_entries and "K8-3" in {
        s.get("sheet_code") for s in fadj_ie
        if _g1_has_consumer_form4("K8-3", _ie(s).get("item_id", ""))
        or _g1_has_consumer_literal(_contract_item_id("K8-3")[0] or "")
    }:
        ok = False
        notes.append("对照组 K8-3 应有消费方但出现在 entries 中 → 形态④搜索失效")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "denominator_observed": denominator,
            "denominator_note": (
                "分母 = catalog 中 class_code=F-调整分录 且 import_export.enabled 为真的条目数。"
            ),
            "f_adjustment_total": len(fadj),
            "consumer_found": len(consumer_found_codes),
            "no_consumer": len(entries),
            "entries_by_verdict": {
                v: sum(1 for e in entries if e["verdict"] == v)
                for v in _VERDICTS
            },
        },
    )


def _g1_has_consumer_literal(item_id: str) -> bool:
    """形态①②③：搜索 item_id 字面量（或通配前缀）在前端生产代码是否有命中。"""
    if not item_id:
        return False
    search_term = item_id.replace("-*", "-") if "*" in item_id else item_id
    for p in _g1_prod_files():
        if search_term in _read(p):
            return True
    return False


def _contract_key_suffixes() -> tuple[str, ...]:
    """契约清单登记的**全部后缀**（`key_families` 的单一真源，禁硬编码）。

    2026-08-16 复盘修：初版在 `_g1_has_consumer_form4` 里写死 `derived_key = prefix + "-entries"`
    —— 既违反「禁硬编码」铁律，又因只试一个后缀而判据过宽/过窄不可控。
    真源三处：`key_families.single_json.item_id`（完整键的尾段）、
    `key_families.per_field.suffixes[]`、`key_families.data.suffix`。
    """
    def _load() -> tuple[str, ...]:
        doc = json.loads(_read(CONTRACT_PATH))
        out: set[str] = set()
        for entry in (doc.get("sheets") or {}).values():
            fams = entry.get("key_families") or {}
            pf = fams.get("per_field") or {}
            for s in pf.get("suffixes") or []:
                if isinstance(s, str) and s:
                    out.add(s.lstrip("-"))
            data = fams.get("data") or {}
            ds = data.get("suffix")
            if isinstance(ds, str) and ds:
                out.add(ds.lstrip("-"))
            sj = fams.get("single_json") or {}
            sj_id = sj.get("item_id")
            if isinstance(sj_id, str) and "-" in sj_id:
                out.add(sj_id.rsplit("-", 1)[-1])
        if not out:
            raise AssertionError(
                "契约清单未登记任何后缀（key_families.per_field.suffixes / data.suffix / "
                "single_json.item_id 三处全空）⇒ 形态④判据会退化为恒假。"
                "异常向上抛而不 fail-open 成空表（R10.11）"
            )
        return tuple(sorted(out))

    return _cached("contract_key_suffixes", _load)


def _g1_has_consumer_form4(code: str, item_id: str) -> bool:
    """形态④：通过 `ITEM_PREFIX` 跨文件拼装判断是否有消费方。

    两级判据：
      ① `item_id` 以某处 `ITEM_PREFIX` 值开头 ⇒ 该前缀能拼出此键
      ② 该 sheet 存在同 cycle 的 `ITEM_PREFIX`，且 **`prefix + 清单登记的任一后缀`**
         在前端生产代码真出现 ⇒ 前端用的是同义真键（catalog 记错键名）

    后缀表来自 `_contract_key_suffixes()`（契约清单单一真源），**不写任何字面量**。
    """
    if not item_id:
        return False
    cycle = code.split("-")[0]
    search_patterns = [
        f"use{cycle}FormData.ts",
        f"{cycle}TabAdjust*.vue",
        f"use{cycle}Adjustment.ts",
    ]
    import fnmatch

    for p in _g1_prod_files():
        if not any(fnmatch.fnmatch(p.name, pat) for pat in search_patterns):
            continue
        m = re.search(r"ITEM_PREFIX\s*=\s*['\"]([^'\"]+)['\"]", _read(p))
        if not m:
            continue
        prefix_val = m.group(1)
        # ① 直接匹配
        if item_id.startswith(prefix_val):
            return True
        # ② 同义真键：按清单登记的后缀逐个试（真源 = key_families，非硬编码）
        if prefix_val.startswith(f"{cycle}-"):
            for suffix in _contract_key_suffixes():
                derived = f"{prefix_val}-{suffix}"
                if _g1_has_consumer_literal(derived):
                    return True
    return False


def _g1_prod_files() -> list[Path]:
    """前端生产文件列表（缓存）。"""
    def _load() -> list[Path]:
        out: list[Path] = []
        for p in sorted(FE_SRC.rglob("*")):
            if p.suffix not in (".ts", ".vue", ".js"):
                continue
            posix = p.as_posix()
            if "__tests__" in posix or posix.endswith(".spec.ts"):
                continue
            out.append(p)
        return out
    return _cached("g1_prod_files", _load)


def _k3_frontend_key() -> tuple[str | None, str]:
    """K3-3 前端真键：`ITEM_PREFIX` 常量值 + 模板拼接后缀（形态 ②）。"""
    tabs = list(WP_DIR.rglob("K3TabAdjustment.vue"))
    if not tabs:
        return None, "K3TabAdjustment.vue 未找到"
    src = _read(tabs[0])
    rel = tabs[0].relative_to(FE_SRC).as_posix()
    m = re.search(r"const\s+ITEM_PREFIX\s*=\s*'([^']+)'", src)
    if not m:
        return None, f"{rel}: 未找到 ITEM_PREFIX 常量"
    prefix = m.group(1)
    line = src[: m.start()].count("\n") + 1
    suffix_hits = sorted(
        {
            mm.group(1)
            for mm in re.finditer(r"`\$\{ITEM_PREFIX\}(-[a-zA-Z-]+)`", src)
        }
    )
    key = prefix + suffix_hits[0] if suffix_hits else None
    return key, f"{rel}:{line} ITEM_PREFIX={prefix!r} + 模板拼接后缀 {suffix_hits}"


def _frontend_production_hits(literal: str, limit: int = 5) -> list[str]:
    """某字面量在前端**生产代码**（排除 `__tests__` / `*.spec.ts`）里的命中（R8.2）。"""
    if not literal:
        return []
    hits: list[str] = []
    for p in sorted(FE_SRC.rglob("*")):
        if p.suffix not in (".ts", ".vue", ".js"):
            continue
        posix = p.as_posix()
        if "__tests__" in posix or posix.endswith(".spec.ts"):
            continue
        src = _read(p)
        idx = src.find(literal)
        if idx >= 0:
            hits.append(f"{p.relative_to(FE_SRC).as_posix()}:{src[:idx].count(chr(10)) + 1}")
            if len(hits) >= limit:
                break
    return hits


# ═══════════════════════════════════════════════════════════════════════════════
# G2 —— 无 manifest 兜底的启用 IE 条目（38；裁决 2 只登记不修）
# ═══════════════════════════════════════════════════════════════════════════════


def probe_g2() -> Probe:
    manifest = _manifest_entries()
    enabled = _catalog_enabled()
    uncovered = [s for s in enabled if s.get("sheet_code") not in manifest]

    overrides_doc = json.loads(_read(OVERRIDES_PATH)) if OVERRIDES_PATH.exists() else {}
    overrides_payload = overrides_doc.get("overrides") or overrides_doc.get("sheets") or {}

    entries: list[dict[str, Any]] = []
    for s in sorted(uncovered, key=lambda x: _natural(x.get("sheet_code", ""))):
        code = s.get("sheet_code", "?")
        ie = _ie(s)
        contract_value, contract_path = _contract_item_id(code)
        gen = _generated_registry().get(ie.get("api_prefix"), None)
        entries.append(
            _entry(
                group="G2",
                key=code,
                sheet_code=code,
                catalog_value=(
                    f"enabled=True api_prefix={ie.get('api_prefix')!r} "
                    f"item_id={ie.get('item_id')!r} storage_field={ie.get('storage_field')!r}"
                ),
                contract_value=contract_value,
                frontend_observed=(
                    f"registry[{ie.get('api_prefix')!r}].sheets 含本 sheet={code in (gen or [])}"
                    if gen is not None
                    else None
                ),
                na_reasons={
                    k: v
                    for k, v in {
                        "contract_value": (
                            f"契约清单只收调整分录键面；本条取值路径={contract_path}"
                            if contract_value is None
                            else ""
                        ),
                        "frontend_observed": (
                            "该前缀未出现在前端派生 registry（下拉不可达），前端无观察值"
                            if gen is None
                            else ""
                        ),
                    }.items()
                    if v
                },
                verdict="real_drift",
                evidence={
                    "expected_manifest": f"{code.split('-')[0][0].lower()}_cycle_ie_manifest.yaml",
                    "manifest_files_present": _manifest_files(),
                    "generator_all_cycles": _generator_cycles(),
                    "overrides_entries": len(overrides_payload),
                    "loss_on_regeneration": True,
                },
            )
        )

    man_cycles = sorted({f.split("_")[0] for f in _manifest_files()})
    gen_cycles = sorted(_generator_cycles())
    notes: list[str] = []
    ok = True
    if len(_catalog_sheets()) < 1000:
        ok = False
        notes.append(f"catalog 扫描面异常小（{len(_catalog_sheets())} < 1000）")
    if len(enabled) < 300:
        ok = False
        notes.append(f"启用 IE 条目异常少（{len(enabled)} < 300）")
    if len(manifest) < 300:
        ok = False
        notes.append(f"manifest 条目异常少（{len(manifest)} < 300）—— yaml 解析可能失效")
    if man_cycles != gen_cycles:
        ok = False
        notes.append(
            f"manifest 文件循环集 {man_cycles} != 生成器 _ALL_CYCLES {gen_cycles}"
            " —— 新增 manifest 未挂进生成器（或反之），本组判据的前提不成立"
        )
    if overrides_payload:
        notes.append(
            f"overrides 段已非空（{len(overrides_payload)} 条）—— 部分条目可能已有第二兜底，须重核本组口径"
        )

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "catalog_sheets": len(_catalog_sheets()),
            "catalog_ie_enabled": len(enabled),
            "manifest_files": _manifest_files(),
            "manifest_entries": len(manifest),
            "generator_all_cycles": gen_cycles,
            "overrides_entries": len(overrides_payload),
            "by_cycle": _count_by_cycle(e["key"] for e in entries),
        },
    )


def _count_by_cycle(codes: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for code in codes:
        cyc = str(code).split("-")[0]
        out[cyc] = out.get(cyc, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: _natural(kv[0])))


# ═══════════════════════════════════════════════════════════════════════════════
# G3 —— manifest 与 catalog `api_prefix` 反向不一致（15；裁决 2 只登记不修）
# ═══════════════════════════════════════════════════════════════════════════════


def probe_g3() -> Probe:
    manifest = _manifest_entries()
    by_code = _catalog_by_code()
    gen = _generated_registry()

    entries: list[dict[str, Any]] = []
    compared = 0
    for code, man in sorted(manifest.items(), key=lambda kv: _natural(kv[0])):
        sheet = by_code.get(code)
        if not sheet:
            continue
        cat_prefix = _ie(sheet).get("api_prefix")
        man_prefix = man.get("api_prefix")
        if not (cat_prefix and man_prefix):
            continue
        compared += 1
        if cat_prefix == man_prefix:
            continue
        contract_value, contract_path = _contract_item_id(code)
        entries.append(
            _entry(
                group="G3",
                key=code,
                sheet_code=code,
                catalog_value=cat_prefix,
                contract_value=contract_value,
                frontend_observed=(
                    f"registry 前缀键：catalog 值在位={cat_prefix in gen}"
                    f" / manifest 值在位={man_prefix in gen}"
                ),
                na_reasons=(
                    {"contract_value": f"契约清单不登记 I/E 路由前缀；取值路径={contract_path}"}
                    if contract_value is None
                    else None
                ),
                verdict="real_drift",
                evidence={
                    "manifest_file": man.get("_file"),
                    "manifest_api_prefix": man_prefix,
                    "direction": "manifest → catalog（重生成时 manifest 反向覆盖 catalog 现值）",
                },
            )
        )

    notes: list[str] = []
    ok = True
    # 下界随 manifest 规模自缩放（固定阈值会在 manifest 增删时误报）：可比条目至少要覆盖
    # 八成 manifest 条目，否则说明 catalog 侧匹配整体失效而不是「恰好都一致」。
    floor = int(len(manifest) * 0.8)
    if compared < floor:
        ok = False
        notes.append(
            f"可比条目异常少（{compared} < {floor} = manifest {len(manifest)} 条的 80%）"
            "—— manifest/catalog 对齐扫描可能失效"
        )
    if not gen:
        ok = False
        notes.append("前端派生 registry 解析为空 —— 第三列观察值失效")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "compared_entries": compared,
            "generated_registry_prefixes": len(gen),
            "affected_prefix_pairs": sorted(
                {f"{e['evidence']['manifest_api_prefix']} → {e['catalog_value']}" for e in entries}
            ),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G4 —— split-brain（5）：复用任务 1.4 的唯一口径，不写第二份
# ═══════════════════════════════════════════════════════════════════════════════


def _split_brain() -> tuple[dict[str, dict[str, Any]], set[str]]:
    def _load() -> tuple[dict[str, dict[str, Any]], set[str]]:
        guard = importlib.import_module("tests.test_x3_adapter_host_same_module")
        report = guard.split_brain_report(_app())
        return report, set(guard.module_path_violations(report))

    return _cached("split_brain", _load)


def probe_g4() -> Probe:
    report, violations = _split_brain()
    prefix_sheets = _catalog_prefix_sheets()
    gen = _generated_registry()
    mounts = _dropdown_mounts()

    entries: list[dict[str, Any]] = []
    for prefix in sorted(violations):
        row = report[prefix]
        entries.append(
            _entry(
                group="G4",
                key=prefix,
                sheet_code=None,
                catalog_value=f"启用该前缀的 sheet: {prefix_sheets.get(prefix, [])}",
                contract_value=None,
                frontend_observed=(
                    f"派生 registry 在位={prefix in gen} / dropdown 渲染点={mounts.get(prefix, [])}"
                ),
                na_reasons={
                    "contract_value": "split-brain 属路由宿主面，不在调整分录键面 ⇒ 契约清单无对应登记",
                },
                verdict="real_drift",
                evidence={
                    "runtime_host_modules": row["host"],
                    "adapter_resolved_modules": row["adapter"],
                    "adapter_target": row["target"],
                    "compared_suffixes": row["compared_suffixes"],
                    "identity_mismatch": row["identity_mismatch"],
                },
            )
        )

    notes: list[str] = []
    ok = True
    if len(report) < 50:
        ok = False
        notes.append(f"可比前缀异常少（{len(report)} < 50）—— 形态 A 扫描或 adapter 解析失效")
    unresolvable = sorted(p for p, r in report.items() if r["unresolvable"])
    if unresolvable:
        ok = False
        notes.append(f"adapter 三态全解析不到的前缀 {unresolvable} —— 不得静默当作「不违规」")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "comparable_prefixes": len(report),
            "criterion": "严格形态 A = /api/workpapers/{wp_id}/{prefix}/{三态}（粗口径会多算 h5/n4，见 G7）",
            "reused_from": "backend/tests/test_x3_adapter_host_same_module.py::split_brain_report",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G5 —— 形态 A 三态方法不齐（8）
# ═══════════════════════════════════════════════════════════════════════════════


def _strict_shape_a_methods() -> dict[str, dict[str, list[str]]]:
    def _load() -> dict[str, dict[str, list[str]]]:
        guard = importlib.import_module("tests.test_x3_adapter_host_same_module")
        out: dict[str, dict[str, list[str]]] = {}
        for (prefix, suffix), route in guard.strict_shape_a_routes(_app()).items():
            methods = sorted(
                m for m in (getattr(route, "methods", None) or set()) if m not in {"HEAD", "OPTIONS"}
            )
            out.setdefault(prefix, {})[suffix] = methods
        return out

    return _cached("shape_a_methods", _load)


def probe_g5() -> Probe:
    per_prefix = _strict_shape_a_methods()
    prefix_sheets = _catalog_prefix_sheets()
    gen = _generated_registry()
    mounts = _dropdown_mounts()

    entries: list[dict[str, Any]] = []
    for prefix, methods in sorted(per_prefix.items()):
        missing = [s for s in _THREE_STATE if s not in methods]
        non_post = [s for s, ms in sorted(methods.items()) if "POST" not in ms]
        if not missing and not non_post:
            continue
        mounted = mounts.get(prefix, [])
        entries.append(
            _entry(
                group="G5",
                key=prefix,
                sheet_code=None,
                catalog_value=f"启用该前缀的 sheet: {prefix_sheets.get(prefix, [])}",
                contract_value=None,
                frontend_observed=(
                    f"派生 registry 在位={prefix in gen} / dropdown 渲染点={mounted}"
                    f" ⇒ {'共享下拉必 405/404' if mounted else '暂未挂载，用户当前不可见'}"
                ),
                na_reasons={
                    "contract_value": "HTTP 方法面不在调整分录键面 ⇒ 契约清单无对应登记",
                },
                verdict="real_drift",
                evidence={
                    "methods_by_state": {s: methods.get(s, []) for s in _THREE_STATE},
                    "missing_states": missing,
                    "non_post_states": non_post,
                    "shared_composable_requires": "POST × 三态（design E4：useWorkpaperImportExport 三态全 POST）",
                },
            )
        )

    notes: list[str] = []
    ok = True
    if len(per_prefix) < 50:
        ok = False
        notes.append(f"形态 A 前缀扫描面异常小（{len(per_prefix)} < 50）")
    all_post = [p for p, ms in per_prefix.items() if all("POST" in ms.get(s, []) for s in _THREE_STATE)]
    if not all_post:
        ok = False
        notes.append("对照组失效：没有任何前缀被判为「三态全 POST」⇒ 方法判据恒真")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "shape_a_prefixes": len(per_prefix),
            "control_all_post_prefixes": len(all_post),
            "criterion": "三态中存在缺态或非 POST 即收录",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G6 —— M 族未知 sheet 无可读错误（10）
# ═══════════════════════════════════════════════════════════════════════════════


def _shape_b_endpoints() -> dict[str, dict[str, Callable[..., Any]]]:
    """形态 B：`/api/{长前缀}/{wp_id}/{三态}` ⇒ {长前缀: {后缀: endpoint}}。"""
    def _load() -> dict[str, dict[str, Callable[..., Any]]]:
        out: dict[str, dict[str, Callable[..., Any]]] = {}
        for route in _app().routes:
            segs = getattr(route, "path", "").strip("/").split("/")
            if len(segs) < 4 or segs[0] != "api" or segs[-1] not in _THREE_STATE:
                continue
            if segs[-2] != "{wp_id}":
                continue
            out.setdefault(segs[1], {}).setdefault(segs[-1], getattr(route, "endpoint", None))
        return out

    return _cached("shape_b", _load)


def _sheet_handling(service_module: str) -> list[str]:
    """service 源码里对 `sheet` 的处置形态（结构判据）。"""
    path = BACKEND / "app" / "services" / (service_module.replace(".", "/") + ".py")
    if not path.exists():
        return ["SERVICE_MODULE_MISSING"]
    src = _read(path)
    found: list[str] = []
    if re.search(r"if\s+sheet\s+and\s+sheet\s+in\s+\w+", src):
        found.append("WHITELIST_ELSE_ALL")
    if re.search(r"sheet\s+or\s+[\"'][^\"']+[\"']", src):
        found.append("SHEET_OR_DEFAULT")
    if re.search(r"raise\s+HTTPException\([^)]*sheet", src, re.S):
        found.append("RAISE_ON_SHEET")
    return found or ["NO_SHEET_HANDLING"]


def _service_modules_of(endpoint: Callable[..., Any] | None) -> list[str]:
    """端点宿主模块源码里 import 的 `app.services.*` 模块（含函数内惰性 import）。"""
    if endpoint is None:
        return []
    module = sys.modules.get(getattr(endpoint, "__module__", ""))
    src_file = getattr(module, "__file__", None)
    if not src_file:
        return []
    src = _read(Path(src_file))
    return sorted(
        set(re.findall(r"from\s+app\.services\.([\w.]+)\s+import", src))
        | set(re.findall(r"import\s+app\.services\.([\w.]+)", src))
    )


def probe_g6() -> Probe:
    shape_b = _shape_b_endpoints()
    prefix_sheets = _catalog_prefix_sheets()
    gen = _generated_registry()

    m_prefixes = [f"m{i}" for i in range(1, 11)]
    entries: list[dict[str, Any]] = []
    scanned = 0
    for short in m_prefixes:
        long_prefixes = sorted(p for p in shape_b if p.startswith(f"{short}-"))
        if not long_prefixes:
            continue
        scanned += 1
        long_prefix = long_prefixes[0]
        endpoints = shape_b[long_prefix]
        sheet_params = {
            suffix: (
                "sheet" in inspect.signature(ep).parameters if ep is not None else None
            )
            for suffix, ep in sorted(endpoints.items())
        }
        services = sorted({m for ep in endpoints.values() for m in _service_modules_of(ep) if re.match(rf"^{short}_", m)})
        handling = {m: _sheet_handling(m) for m in services}
        raises = any("RAISE_ON_SHEET" in v for v in handling.values())
        if raises:
            continue  # 已有可读错误 ⇒ 不属本组
        x3_code = f"{short.upper()}-3"
        contract_value, contract_path = _contract_item_id(x3_code)
        mechanism = (
            "handler 未声明 sheet 参数 ⇒ FastAPI 静默丢弃该 query 参数"
            if not any(sheet_params.values())
            else "; ".join(f"{m}: {'+'.join(v)}" for m, v in sorted(handling.items())) or "未识别"
        )
        entries.append(
            _entry(
                group="G6",
                key=short,
                sheet_code=x3_code,
                catalog_value=f"启用该短前缀的 sheet: {prefix_sheets.get(short, [])}",
                contract_value=contract_value,
                frontend_observed=(
                    f"派生 registry 短前缀在位={short in gen}"
                    f" / 长前缀在位={long_prefix in gen}"
                ),
                na_reasons=(
                    {"contract_value": f"{x3_code} 尚未迁入 sheets 段（任务 2.1）；取值路径={contract_path}"}
                    if contract_value is None
                    else None
                ),
                verdict="real_drift",
                evidence={
                    "long_prefix": long_prefix,
                    "host_modules": sorted(
                        {getattr(ep, "__module__", "?") for ep in endpoints.values() if ep}
                    ),
                    "sheet_param_declared": sheet_params,
                    "delegate_services": services,
                    "unknown_sheet_handling": handling,
                    "mechanism": mechanism,
                    "readable_error_on_unknown_sheet": False,
                },
            )
        )

    control = _sheet_handling_of_factory()
    notes: list[str] = []
    ok = True
    if scanned != 10:
        ok = False
        notes.append(f"m1~m10 形态 B 端点只扫到 {scanned} 个前缀（期望 10）—— 路由扫描失效")
    if "RAISE_ON_SHEET" not in control:
        ok = False
        notes.append(
            f"对照组失效：工厂 `_cycle_import_export_common._validate` 未被判为 RAISE_ON_SHEET（实测 {control}）"
            " ⇒ 「无可读错误」判据恒真，本组数字不可信"
        )

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "m_prefixes_scanned": scanned,
            "control_factory_handling": control,
            "criterion": "三态路径上不存在任何针对未知 sheet 值的可读错误（400）",
            "mechanism_note": (
                "四种子形态：no_sheet_param（m1）/ WHITELIST_ELSE_ALL（m2~m6·m8）/ "
                "SHEET_OR_DEFAULT（m10，m6·m8 兼有）/ SERVICE_MODULE_MISSING（m7·m9，端点一调即 ImportError）。"
                "design §C7 的「静默回退全部」是这四种的概称；条数不变，形态按实测登记。"
            ),
        },
    )


def _sheet_handling_of_factory() -> list[str]:
    """对照组：工厂共享实现对未知 sheet **有**可读错误（design E10）。"""
    src = _read(FACTORY_COMMON)
    found: list[str] = []
    if re.search(r"def _validate\(sheet: str\)[^#]*?raise\s+HTTPException\(\s*400", src, re.S):
        found.append("RAISE_ON_SHEET")
    if re.search(r"if\s+sheet\s+and\s+sheet\s+in\s+\w+", src):
        found.append("WHITELIST_ELSE_ALL")
    return found or ["NO_SHEET_HANDLING"]


# ═══════════════════════════════════════════════════════════════════════════════
# G7 —— `_h5` / `_n4` 是父 spec Task 25 不可删项（2）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_PREFIXES: tuple[str, ...] = ("h5", "n4")


def probe_g7() -> Probe:
    from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE  # noqa: PLC0415

    shape_a = _strict_shape_a_methods()
    prefix_sheets = _catalog_prefix_sheets()
    gen = _generated_registry()
    third_shape = _third_shape_routes()

    entries: list[dict[str, Any]] = []
    for prefix in _G7_PREFIXES:
        target = _PREFIX_TO_MODULE.get(prefix)
        enabled_sheets = prefix_sheets.get(prefix, [])
        if not enabled_sheets or prefix in shape_a or not target or target.startswith("app."):
            continue  # 三条活因任一不成立 ⇒ 不再属本组（应下调基线）
        x3_code = f"{prefix.upper()}-3"
        contract_value, contract_path = _contract_item_id(x3_code)
        entries.append(
            _entry(
                group="G7",
                key=f"_{prefix}_import_export",
                sheet_code=None,
                catalog_value=f"启用该短前缀的 sheet: {enabled_sheets}",
                contract_value=contract_value,
                frontend_observed=(
                    f"派生 registry[{prefix!r}] = {gen.get(prefix)}"
                    f"（下拉按形态 A 拼 URL，而后端只有第三形态 ⇒ 单份通路实为不可达）"
                ),
                na_reasons=(
                    {"contract_value": f"本条属模块存活面，非键面；{x3_code} 取值路径={contract_path}"}
                    if contract_value is None
                    else None
                ),
                verdict="real_drift",
                evidence={
                    "adapter_target": target,
                    "adapter_target_is_factory_module": not target.startswith("app."),
                    "strict_shape_a_host": None,
                    "third_shape_routes": third_shape.get(prefix, []),
                    "why_not_in_g4": (
                        "实质同为「界面走专属 router、bulk 走工厂闭包」的存量不同源，"
                        "只因其 URL 是第三形态 /api/{prefix}/{三态}（无 {wp_id} 段）才不计入 G4 的 5 例"
                        "（任务 1.4 口径修正一）。🔴 不得为「统一口径」把 G4 基线抬到 7 —— "
                        "那是把口径错误锁成基线。"
                    ),
                    "consequence": (
                        f"删除该工厂模块会静默切掉 {enabled_sheets} 的批量能力 ⇒ "
                        "父 spec Task 25 的删除清单须移出本模块（R9.4）"
                    ),
                },
            )
        )

    notes: list[str] = []
    ok = True
    if not _PREFIX_TO_MODULE:
        ok = False
        notes.append("`_PREFIX_TO_MODULE` 为空 —— adapter 映射读取失效")
    control = [p for p in ("l1", "l3") if p in shape_a]
    if not control:
        ok = False
        notes.append("对照组失效：l1/l3 应有严格形态 A 宿主，实测无 ⇒ 形态判据失效，本组「无宿主」结论不可信")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "adapter_map_keys": len(_PREFIX_TO_MODULE),
            "control_shape_a_prefixes": control,
            "criterion": "catalog 启用该短前缀 且 运行期无严格形态 A 宿主 且 adapter 仍指向工厂模块",
        },
    )


def _third_shape_routes() -> dict[str, list[str]]:
    """第三形态：`/api/{prefix}/{三态}`（路径无 `{wp_id}` 段）。"""
    def _load() -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for route in _app().routes:
            path = getattr(route, "path", "")
            segs = path.strip("/").split("/")
            if len(segs) != 3 or segs[0] != "api" or segs[-1] not in _THREE_STATE:
                continue
            methods = sorted(
                m for m in (getattr(route, "methods", None) or set()) if m not in {"HEAD", "OPTIONS"}
            )
            host = getattr(getattr(route, "endpoint", None), "__module__", "?")
            out.setdefault(segs[1], []).append(f"{'/'.join(methods)} {path} → {host}")
        return out

    return _cached("third_shape", _load)


# ═══════════════════════════════════════════════════════════════════════════════
# G8 —— `N3-3` 源模板笔误（1；源模板只读，登记不修）
# ═══════════════════════════════════════════════════════════════════════════════


def _x3_template_head(sheet_code: str) -> dict[str, Any]:
    """openpyxl 直读源模板前 5 行（`read_only=True`，R11.1 只读）。"""
    import openpyxl  # noqa: PLC0415

    from app.services.wp_template_finder import find_template_file  # noqa: PLC0415

    cycle = sheet_code.split("-")[0]
    path = find_template_file(cycle)
    if path is None:
        raise RuntimeError(f"{sheet_code}: 源模板未定位到（find_template_file({cycle!r}) 返回 None）")
    tab = _ie_sheet_name(sheet_code)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if tab not in wb.sheetnames:
            raise RuntimeError(f"{sheet_code}: tab {tab!r} 不在 {path.name}（sheetnames={wb.sheetnames}）")
        ws = wb[tab]
        rows = list(ws.iter_rows(min_row=1, max_row=5, values_only=True))
    finally:
        wb.close()
    row2 = [str(v).strip() for v in (rows[1] if len(rows) > 1 else []) if v is not None and str(v).strip()]
    row3 = [str(v).strip() for v in (rows[2] if len(rows) > 2 else []) if v is not None and str(v).strip()]
    return {
        "template_file": path.relative_to(ROOT).as_posix(),
        "tab": tab,
        "business_name": _template_business_name(path.stem),
        "row2_title": row2[0] if row2 else "",
        "row3_labels": row3,
    }


def _template_business_name(stem: str) -> str:
    """`N3 递延所得税负债` → `递延所得税负债`；再截掉括号补充（`M2 实收资本（股本）` → `实收资本`）。

    🔴 括号必须截：`M2-3` 的标题是「实收资本调整分录汇总表」而文件名带「（股本）」，
    不截会把 M2-3 误判成标题笔误（本判据首版实测踩过，2 例假阳性之一）。
    """
    name = stem.split(" ", 1)[1] if " " in stem else stem
    return re.split(r"[（(]", name)[0].strip()


def _ie_sheet_name(sheet_code: str) -> str:
    entry = _catalog_by_code().get(sheet_code) or {}
    name = entry.get("sheet_name")
    if not name:
        raise RuntimeError(f"{sheet_code}: catalog 无 sheet_name，无法定位 tab")
    return str(name)


def probe_g8() -> Probe:
    heads = {code: _x3_template_head(code) for code in _x3_targets()}

    entries: list[dict[str, Any]] = []
    control_clean: list[str] = []
    for code, head in sorted(heads.items(), key=lambda kv: _natural(kv[0])):
        title_ok = head["business_name"] in head["row2_title"]
        dups = sorted({lbl for lbl in head["row3_labels"] if head["row3_labels"].count(lbl) > 1})
        if title_ok and not dups:
            control_clean.append(code)
            continue
        contract_value, contract_path = _contract_item_id(code)
        entries.append(
            _entry(
                group="G8",
                key=code,
                sheet_code=code,
                catalog_value=f"sheet_name={head['tab']!r}",
                contract_value=contract_value,
                frontend_observed=None,
                na_reasons={
                    k: v
                    for k, v in {
                        "contract_value": (
                            f"源模板笔误不在键面；取值路径={contract_path}" if contract_value is None else ""
                        ),
                        "frontend_observed": "前端不渲染源模板第 2/3 行（表头由组件自绘）⇒ 无前端观察面",
                    }.items()
                    if v
                },
                verdict="real_drift",
                evidence={
                    "template_file": head["template_file"],
                    "tab": head["tab"],
                    "row2_title_observed": head["row2_title"],
                    "row2_title_expected_to_contain": head["business_name"],
                    "row2_title_mismatch": not title_ok,
                    "row3_labels_observed": head["row3_labels"],
                    "row3_duplicated_labels": dups,
                    "handling": "源模板只读（R11.1）⇒ 登记不修；导出用 catalog sheet_name，不搬第 2 行标题",
                },
            )
        )

    notes: list[str] = []
    ok = True
    if len(heads) != 16:
        ok = False
        notes.append(f"源模板读取面 {len(heads)} != 16")
    if len(control_clean) < 14:
        ok = False
        notes.append(
            f"对照组失效：仅 {len(control_clean)} 张被判「标题相容且第 3 行无重复」"
            "（期望 ≥14）⇒ 判据过宽，本组数字不可信"
        )
    if any(not h["row2_title"] for h in heads.values()):
        ok = False
        notes.append("有 sheet 的第 2 行标题读为空 —— openpyxl 读取失效")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "templates_read": len(heads),
            "control_clean_sheets": control_clean,
            "criterion": "第 2 行标题不含模板文件业务名（括号补充已截）或第 3 行标签有重复",
            "paren_rule_note": "M1-3 / M2-3 依赖括号截断规则才判为正常；去掉该规则会多出 M2-3 假阳性",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G9 —— `K3-3` 上游 manifest 与 catalog 同错（1）
# ═══════════════════════════════════════════════════════════════════════════════


def probe_g9() -> Probe:
    manifest = _manifest_entries()
    entries: list[dict[str, Any]] = []
    checked: list[str] = []
    for code in ("K3-3",):
        man = manifest.get(code)
        if not man:
            continue
        checked.append(code)
        cat = _ie(_catalog_by_code().get(code, {})).get("item_id")
        man_value = man.get("item_id")
        contract_value, contract_path = _contract_item_id(code)
        fe_key, fe_evidence = _k3_frontend_key()
        if not (man_value == cat and contract_value and man_value != contract_value):
            continue  # 上游已改对 / catalog 与 manifest 已不同源 ⇒ 应下调基线
        entries.append(
            _entry(
                group="G9",
                key=f"{man['_file']}::{code}",
                sheet_code=code,
                catalog_value=cat,
                contract_value=contract_value,
                frontend_observed=fe_key,
                verdict="real_drift",
                evidence={
                    "manifest_file": f"backend/data/acnr/sources/{man['_file']}",
                    "manifest_item_id": man_value,
                    "contract_path": contract_path,
                    "frontend_evidence": fe_evidence,
                    "catalog_value_frontend_hits": _frontend_production_hits(str(cat)),
                    "consequence": "只改 catalog 会被 generate_catalog.py 重生成打回 ⇒ 必须改 manifest",
                    "relation": "与 G1 的 K3-3 是同一处错位的上下游两侧（G1 记 catalog 面，G9 记上游真源面）",
                },
            )
        )

    notes: list[str] = []
    ok = True
    if not checked:
        ok = False
        notes.append("K3-3 不在任何 manifest 里 —— 上游读取失效或作业面已变")
    if len(manifest) < 300:
        ok = False
        notes.append(f"manifest 条目异常少（{len(manifest)}）")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "manifest_entries": len(manifest),
            "criterion": "manifest.item_id == catalog.item_id 且二者 != 契约清单实测键",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G10 —— 只写不读（4；任务 4.2 + 11.1 补齐后应降至 0，自我失效的真实演练）
# ═══════════════════════════════════════════════════════════════════════════════

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<![:\w])//[^\n]*")
_WRITE_MARKERS: tuple[str, ...] = ("itemId:", "saveField(", "debouncedSave(", "saveBatch(", "setField(")
_READ_MARKERS: tuple[str, ...] = (".get(", "startsWith(", "getField(")


def _strip_ts_comments(src: str) -> str:
    """剥 TS/Vue 注释（防注释里的示例键把判据骗过去）。

    🔴 块注释用等量换行替换而不是删空 —— 否则行号会整体前移，evidence 里记的
    `file:line` 打开后对不上，等于不可复算。
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), src))


def _x3_frontend_files(sheet_code: str) -> list[Path]:
    cycle = sheet_code.split("-")[0]
    return [
        WP_DIR / "composables" / f"use{cycle}Adjustment.ts",
        WP_DIR / cycle.lower() / "core" / f"{cycle}TabAdjustment.vue",
    ]


def _read_write_hits(sheet_code: str) -> dict[str, Any]:
    """扫该 sheet 的 entries 键族在前端生产代码里的**写入**与**读取**命中。

    键族不写死：从写入侧表达式派生 —— 模板字面量 `` `L6-L6-3-entry-${n}-desc` `` 与
    单键字面量 `'L2-L2-3-entries'` 都归约到同一个族正则；`const X = '<字面量>'`
    的别名先解析（M3/M4/M5/M10 的 `const prefix = '{X}-3-entry-'` 就是别名读法）。
    机制 ① 的 `setField('3','entries')` / `getField('3','entries')` 另走一条判据
    （其键在运行期由 `ITEM_PREFIX + sheet + field` 三段拼出，字面量不存在）。
    """
    family = re.compile(r"(?:[A-Z]\d{0,2}-)?" + re.escape(sheet_code) + r"-entr(?:y-|ies)")
    sheet_suffix = sheet_code.split("-", 1)[1]
    formdata = re.compile(r"(set|get)Field\(\s*['\"]" + re.escape(sheet_suffix) + r"['\"]\s*,\s*['\"]entries['\"]")

    writes: list[str] = []
    reads: list[str] = []
    missing: list[str] = []
    for path in _x3_frontend_files(sheet_code):
        if not path.exists():
            missing.append(path.relative_to(FE_SRC).as_posix())
            continue
        src = _strip_ts_comments(_read(path))
        aliases = [
            m.group(1)
            for m in re.finditer(r"const\s+(\w+)\s*=\s*'([^']+)'", src)
            if family.search(m.group(2))
        ]
        rel = path.relative_to(FE_SRC).as_posix()
        for lineno, line in enumerate(src.splitlines(), 1):
            hit_family = bool(family.search(line)) or any(a in line for a in aliases)
            tag = f"{rel}:{lineno}"
            if hit_family:
                if any(mark in line for mark in _READ_MARKERS):
                    reads.append(f"{tag} family/read")
                elif any(mark in line for mark in _WRITE_MARKERS):
                    writes.append(f"{tag} family/write")
            fd = formdata.search(line)
            if fd:
                (reads if fd.group(1) == "get" else writes).append(f"{tag} {fd.group(1)}Field")
    state = "WRITE_ONLY" if writes and not reads else ("READ_OK" if reads else "NO_HIT")
    return {"state": state, "writes": writes, "reads": reads, "missing_files": missing}


#: G10 的**行为面**承载者（本组只判表达式存在层，见 `_gs5b_carrier` 的 docstring）
GUARD_SPEC_GS5B = WP_DIR / "__tests__" / "ieWiringIntegrity.spec.ts"


_RE_TOP_DESCRIBE = re.compile(r"^describe\s*\(", re.M)


def _top_describe_block(src: str, title_prefix: str) -> tuple[str | None, int]:
    """取顶层 `describe('<title_prefix>…')` 的块文本 → (块, 命中数)。

    🔴 **不做括号配对**：TS 源里正则字面量含转义括号（`\\s*\\(`）、断言消息含全/半角
    括号，朴素配对必在 EOF 前失衡并返回 None（首版就是这么假红的）。改用**行首锚点**
    切块：顶层 `describe(` 一律在第 0 列 ⇒ 块 = 本 describe 起点到下一个顶层 describe
    起点（或 EOF）。命中数一并返回 —— 不等于 1 时调用方按「锚点失效」处置，不静默。
    """
    starts = [m.start() for m in _RE_TOP_DESCRIBE.finditer(src)]
    hits = [
        (i, s)
        for i, s in enumerate(starts)
        if re.match(r"describe\s*\(\s*['\"]" + re.escape(title_prefix), src[s:])
    ]
    if len(hits) != 1:
        return None, len(hits)
    i, s = hits[0]
    end = starts[i + 1] if i + 1 < len(starts) else len(src)
    return src[s:end], 1


def _gs5b_carrier() -> dict[str, Any]:
    """G10 的行为面承载者 `GS5b` 是否在位 —— **交叉引用锁，不是行为判据本身**。

    🔴 判据强弱的显式裁决（任务 11.2）

    本组探针判的是**表达式存在层**：该 sheet 的 entries 键族在两个前端生产文件里
    有没有读取表达式（`.get(` / `startsWith(` / `getField(`）。这一层**弱于**
    R6.5 / R6.7 —— 「存在读回表达式」不等于「导入后界面读得到」：`@imported="() => {}"`、
    处理器只弹成功提示、或只 `loadData()` 而不重跑读回，三种写法下本组照旧判 `READ_OK`。
    实测已验证：任务 11.1 的变异 M4（处理器只 `loadData()` 不读回）下本组实测**仍为 0**，
    只有 `GS5b` 打红。

    ⇒ 行为面由前端守卫 `GS5b · X-3 的 @imported → 读回可追溯` 承载。本函数只锁
    **承载者在位**：若 GS5b 整块被删/改名/退化成不带断言的空壳，G10 的 0 就退化成
    「有表达式但可能没人触发」，此时本组 `selfcheck` 必须打红，而不是继续绿着躺在
    一个弱判据上（那正是「在弱判据上锁 0 而不留痕」）。
    """
    rel = GUARD_SPEC_GS5B.relative_to(FE_SRC).as_posix()
    out: dict[str, Any] = {
        "carried_by": "GS5b · X-3 的 @imported → 读回可追溯（任务 11.1，R6.5 / R6.7）",
        "guard_file": rel,
        "layer_of_this_group": "表达式存在层（弱于 R6.5/R6.7；行为层不在本组）",
    }
    if not GUARD_SPEC_GS5B.exists():
        return {**out, "present": False, "reason": f"承载者文件不存在：{rel}"}
    src = _strip_ts_comments(_read(GUARD_SPEC_GS5B))
    block, hit_count = _top_describe_block(src, "GS5b")
    if block is None:
        return {
            **out,
            "present": False,
            "reason": (
                f"顶层 `describe('GS5b…')` 命中 {hit_count} 处（期望 1）—— 承载者被删/改名，"
                "或锚点失效（两种都不许当作「无偏差」）"
            ),
        }
    checks = {
        "reads_imported_attr": bool(re.search(r"['\"]@imported['\"]", block)),
        "requires_reload_call": bool(re.search(r"loadData\|selfLoad\|reload", block)),
        "requires_shared_readback": "sharedReadbackCalls" in block,
        "asserts_violations_empty": bool(re.search(r"violations[\s\S]{0,400}?toEqual\(\[\]\)", block)),
        "it_cases": len(re.findall(r"\bit\s*\(", block)),
    }
    present = all(v for k, v in checks.items() if k != "it_cases") and checks["it_cases"] >= 3
    return {
        **out,
        "present": present,
        "shape_checks": checks,
        "reproduce_cmd": (
            "cd audit-platform/frontend && npx vitest run --silent=true "
            "src/components/workpaper/__tests__/ieWiringIntegrity.spec.ts"
        ),
        "known_blind_spot": (
            "任务 11.1 变异 M4（处理器只 loadData() 不读回）⇒ 本组实测仍 0（表达式还在），"
            "GS5b 打红 ⇒ 行为面确由 GS5b 承载；本组不重复实现该判据（避免第二份行为判据分叉）"
        ),
        "mutation_that_moves_this_group": (
            "任务 11.1 变异 M3（摘掉读回表达式）⇒ 本组实测 0 → 1 且 --check 打红 REGRESSION"
        ),
    }


def probe_g10() -> Probe:
    scan = {code: _read_write_hits(code) for code in _x3_targets()}
    carrier = _gs5b_carrier()

    entries: list[dict[str, Any]] = []
    for code, hits in sorted(scan.items(), key=lambda kv: _natural(kv[0])):
        if hits["state"] != "WRITE_ONLY":
            continue
        contract_value, contract_path = _contract_item_id(code)
        entries.append(
            _entry(
                group="G10",
                key=code,
                sheet_code=code,
                catalog_value=f"import_export 启用={bool(_ie(_catalog_by_code().get(code, {})).get('enabled'))}",
                contract_value=contract_value,
                frontend_observed=(
                    f"写入命中 {len(hits['writes'])} 处 / 读回命中 0 处 ⇒ 只写不读"
                    "（用户填完刷新页面即看不见）"
                ),
                na_reasons=(
                    {"contract_value": f"{code} 尚未迁入 sheets 段（任务 2.1）；取值路径={contract_path}"}
                    if contract_value is None
                    else None
                ),
                verdict="real_drift",
                evidence={
                    "write_hits": hits["writes"][:6],
                    "write_hit_count": len(hits["writes"]),
                    "read_hits": hits["reads"],
                    "scanned_files": [p.relative_to(FE_SRC).as_posix() for p in _x3_frontend_files(code)],
                    "closure_path": (
                        "任务 4.2 给 use{X}Adjustment 补 loadFromResponses + 任务 11.1 接 onMounted "
                        "⇒ 实测数降至 0 ⇒ 本脚本要求把 baseline_count 由 4 下调到 0（任务 11.2）"
                    ),
                    "blocks_requirement": "R6.5 / R6.7（导入后界面重载须显示导入的行）对这几张当前不可满足",
                },
            )
        )

    read_ok = [c for c, h in scan.items() if h["state"] == "READ_OK"]
    no_hit = [c for c, h in scan.items() if h["state"] == "NO_HIT"]
    missing = sorted({f for h in scan.values() for f in h["missing_files"]})
    notes: list[str] = []
    ok = True
    if len(scan) != 16:
        ok = False
        notes.append(f"扫描面 {len(scan)} != 16")
    if len(read_ok) < 10:
        ok = False
        notes.append(
            f"对照组失效：仅 {len(read_ok)} 张被判「有读回」（期望 ≥10）⇒ 读取判据可能整体失灵"
        )
    if no_hit:
        ok = False
        notes.append(f"这些 sheet 读写双零命中 {no_hit} —— 键族派生失效，不得当作「无偏差」")
    if not carrier.get("present"):
        ok = False
        notes.append(
            "行为面承载者 GS5b 不在位（"
            f"{carrier.get('reason') or carrier.get('shape_checks')}）—— 本组判据只到"
            "「读回表达式存在」层，弱于 R6.5/R6.7；承载者一旦消失，实测 0 即退化为"
            f"「有表达式但可能没人触发」⇒ 本组打红。承载者 = {carrier['guard_file']}"
        )

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "behavioral_layer": carrier,
            "scanned_sheets": len(scan),
            "control_read_ok": sorted(read_ok, key=_natural),
            "state_distribution": {
                state: sorted((c for c, h in scan.items() if h["state"] == state), key=_natural)
                for state in ("READ_OK", "WRITE_ONLY", "NO_HIT")
            },
            "missing_files": missing,
            "criterion": "写入命中 > 0 且读取命中 == 0（键族从写入侧派生，不写死键表；先剥注释）",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G11 —— `N5-3` 同名不同源（1；探针假阴性）
# ═══════════════════════════════════════════════════════════════════════════════


def probe_g11() -> Probe:
    tab = WP_DIR / "n5" / "core" / "N5TabAdjustment.vue"
    form = WP_DIR / "composables" / "useN5FormData.ts"
    src = _strip_ts_comments(_read(tab))
    form_src = _strip_ts_comments(_read(form))

    literal = "N5-3-entries"
    lit_hits = [
        (src[: m.start()].count("\n") + 1)
        for m in re.finditer(re.escape(f"'{literal}'"), src)
    ]
    central_hits = [
        (src[: m.start()].count("\n") + 1) for m in re.finditer(r"useAdjustmentCentralSync\(\s*\{", src)
    ]
    # 该字面量是否落在最近一处 useAdjustmentCentralSync({ … }) 的实参块内
    inside_central = []
    for lit_line in lit_hits:
        prior = [c for c in central_hits if c <= lit_line]
        if prior and lit_line - prior[-1] <= 12:
            inside_central.append(lit_line)

    prefix_m = re.search(r"const\s+ITEM_PREFIX\s*=\s*'([^']+)'", form_src)
    assemble_m = re.search(r"const\s+itemId\s*=\s*`\$\{ITEM_PREFIX\}\$\{(\w+)\}-\$\{(\w+)\}`", form_src)
    setfield_m = re.search(r"(set|get)Field\(\s*'3'\s*,\s*'entries'", src)
    assembled = (
        f"{prefix_m.group(1)}3-entries" if prefix_m else None
    )

    entries: list[dict[str, Any]] = []
    if lit_hits and inside_central and assembled == literal and setfield_m:
        contract_value, contract_path = _contract_item_id("N5-3")
        entries.append(
            _entry(
                group="G11",
                key="N5-3",
                sheet_code="N5-3",
                catalog_value=f"import_export 启用={bool(_ie(_catalog_by_code().get('N5-3', {})).get('enabled'))}",
                contract_value=contract_value,
                frontend_observed=(
                    f"`'{literal}'` 字面量 {len(lit_hits)} 处（行 {lit_hits}），"
                    f"全部落在 useAdjustmentCentralSync 实参块内 ⇒ 中央同步键；"
                    f"真数据键由 ITEM_PREFIX={prefix_m.group(1)!r} + sheet + field 运行期三段拼出，"
                    "同名不同源（字面量不是落点）"
                ),
                na_reasons=(
                    {"contract_value": f"N5-3 尚未迁入 sheets 段（任务 2.1）；取值路径={contract_path}"}
                    if contract_value is None
                    else None
                ),
                verdict="probe_false_negative",
                evidence={
                    "tab_file": tab.relative_to(FE_SRC).as_posix(),
                    "literal_lines": lit_hits,
                    "central_sync_call_lines": central_hits,
                    "formdata_file": form.relative_to(FE_SRC).as_posix(),
                    "item_prefix": prefix_m.group(1) if prefix_m else None,
                    "assembly_expression": assemble_m.group(0) if assemble_m else None,
                    "assembled_key": assembled,
                    "tab_access": setfield_m.group(0),
                    "why_false_negative": (
                        "按「字面量 grep」判据会得出「键不可确证」的错结论（design E12 → E17 已推翻）；"
                        "必须走形态 ④ 三步链：tab 的 setField/getField 实参 → use{X}FormData 的 ITEM_PREFIX → 键拼装表达式"
                    ),
                    "counter_proof": (
                        "改 useN5FormData.ts 的 ITEM_PREFIX 值 ⇒ 真键随之变，而 tab 内那处字面量不变"
                        " ⇒ 两者确非同源"
                    ),
                },
            )
        )

    notes: list[str] = []
    ok = True
    if not lit_hits:
        ok = False
        notes.append(f"`'{literal}'` 字面量在 tab 内零命中 —— 前端已改动，本组结论须重核")
    if not prefix_m:
        ok = False
        notes.append("useN5FormData.ts 未找到 ITEM_PREFIX —— 形态 ④ 链第二步断链，判据失效")
    if not setfield_m:
        ok = False
        notes.append("tab 内未找到 setField/getField('3','entries') —— 形态 ④ 链第一步断链")

    return Probe(
        measured=len(entries),
        entries=entries,
        selfcheck_ok=ok,
        selfcheck_notes=notes,
        diagnostics={
            "literal_hits": lit_hits,
            "central_sync_calls": central_hits,
            "assembled_key": assembled,
            "criterion": "字面量全部落在中央同步实参块内 且 三段拼装出的真键与该字面量同名",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 组元数据（`method` = 可复算步骤；禁「本地执行」这类措辞，R8.5）
# ═══════════════════════════════════════════════════════════════════════════════

_REPO_CMD = "python backend/scripts/check/check_x3_deviation_registry.py --check"

_GROUPS: dict[str, dict[str, Any]] = {
    "G1": {
        "title": "catalog `class_code = F-调整分录` 且启用 I/E，但 `item_id` 在前端生产代码无消费方",
        "status": _MEASURED_STATUS,
        "owner_spec": "workpaper-import-export-lifecycle-closure（既有缺陷，不在本 spec 行为半径）",
        "verdict_default": "real_drift",
        "probe_id": "g1_catalog_item_id_without_frontend_consumer",
        "method": [
            "① `from app.services.acnr.catalog import list_sheets` → 取 `class_code == 'F-调整分录'` 且 `import_export.enabled` 为真的条目",
            "② 逐条取 `import_export.item_id`，用四形态键提取判据（literal + wildcard_prefix + ITEM_PREFIX_form4）在前端**生产代码**（排除 `__tests__` 与 `*.spec.ts`）找消费方",
            "③ 与 `backend/data/adjustment_ie_contract.json` 的 `sheets[<code>].item_id` 做 catalog / 契约 / 前端三向比对",
            "④ 分 verdict：前端存在同义真键（catalog 记错）⇒ `real_drift`；键在运行期拼装、字面量不存在（判据假阴性）⇒ `probe_false_negative`",
            "⑤ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
    "G2": {
        "title": "无 manifest 兜底的启用 IE 条目（`generate_catalog.py` 重生成即丢）",
        "status": _MEASURED_STATUS,
        "owner_spec": "acnr 生成链（裁决 2：本 spec 不修，只登记且不让红的规模变大）",
        "verdict_default": "real_drift",
        "probe_id": "g2_ie_enabled_without_manifest_backing",
        "method": [
            "① 取 catalog 全部 `import_export.enabled` 条目（实测 337）",
            "② 取 `backend/data/acnr/sources/*_cycle_ie_manifest.yaml` 的全部 `entries[].sheet_code`（实测 5 文件 / 332 条）",
            "③ 差集即本组：这些条目在 catalog 里有值、在生成源里没有 ⇒ 跑一次生成器就消失",
            "④ 复核第二兜底：`backend/data/acnr/global_catalog.overrides.json` 的 `overrides` 段实测为空 ⇒ 无其他存活路径",
            "⑤ 复算命令：`" + _REPO_CMD + "`；CI 侧退出码见本组 `ci_job.reproduce_cmd`",
        ],
        "ci_job": {
            "job": "acnr-ie-catalog-sync",
            "reproduce_cmd": "python backend/scripts/acnr/check_ie_catalog_sync.py",
        },
    },
    "G3": {
        "title": "manifest 与 catalog `api_prefix` 反向不一致（重生成会把 catalog 现值覆盖回 manifest 值）",
        "status": _MEASURED_STATUS,
        "owner_spec": "g7-column-alignment-and-extraction-closure 等（裁决 2：本 spec 不修，只登记）",
        "verdict_default": "real_drift",
        "probe_id": "g3_manifest_vs_catalog_api_prefix",
        "method": [
            "① 取 manifest 全部 `entries[]` 与 catalog 同 `sheet_code` 条目（实测可比 332 条）",
            "② 逐条比 `entries[].api_prefix` 与 `import_export.api_prefix`，不等即收录（实测 15 条）",
            "③ 第三列取 `cycleImportExportRegistry.generated.ts` 里实际存在的前缀键 —— 它派生自 catalog，故用户点下拉打到的是 catalog 值，不是 manifest 值",
            "④ 复算命令：`" + _REPO_CMD + "`；CI 侧退出码见本组 `ci_job.reproduce_cmd`",
        ],
        "ci_job": {
            "job": "check-acnr-catalog-drift",
            "reproduce_cmd": "python backend/scripts/acnr/check_catalog_drift.py",
        },
    },
    "G4": {
        "title": "split-brain：短前缀的形态 A 宿主模块 ≠ adapter 解析到的端点所在模块",
        "status": _MEASURED_STATUS,
        "owner_spec": "workpaper-import-export-lifecycle-closure Task 25（本 spec 只保持不上升）",
        "verdict_default": "real_drift",
        "probe_id": "g4_adapter_host_split_brain",
        "method": [
            "① `from tests.test_x3_adapter_host_same_module import split_brain_report, module_path_violations`（任务 1.4 交付的唯一口径，禁再写第二份）",
            "② `split_brain_report(app)` 逐前缀取「运行期形态 A 端点 `__module__`」与「`_endpoint_for(目标模块, prefix, suffix)` 解析到的端点 `__module__`」",
            "③ `module_path_violations(...)` 取两侧模块集不等的前缀（实测 5：h7 / l1 / l3 / l4 / l5）",
            "④ 形态 A 必须按严格口径 `/api/workpapers/{wp_id}/{prefix}/{三态}`；粗口径会多算 h5 / n4（见 G7），🔴 不得据此把本组基线抬到 7",
            "⑤ 复算命令：`python -m pytest backend/tests/test_x3_adapter_host_same_module.py -q`（从仓库根跑）",
        ],
    },
    "G5": {
        "title": "形态 A 三态方法不齐（缺态或非 POST；共享下拉三态全 POST ⇒ 该态必 405/404）",
        "status": _MEASURED_STATUS,
        "owner_spec": "workpaper-import-export-lifecycle-closure（存量缺陷，不在本 spec 行为半径）",
        "verdict_default": "real_drift",
        "probe_id": "g5_shape_a_three_state_method_gap",
        "method": [
            "① 取运行期严格形态 A 三态路由（复用 `tests.test_x3_adapter_host_same_module.strict_shape_a_routes`）",
            "② 逐前缀取 `route.methods` 并剔除 HEAD / OPTIONS",
            "③ 判据 = 三态里存在缺态或存在不含 POST 的态（实测 8 个前缀）",
            "④ 后果面：前端共享 `useWorkpaperImportExport.apiBase()` 三态全 POST（design E4）⇒ 非 POST 的态经共享下拉必 405",
            "⑤ 挂载面取前端 `api-prefix=\"<前缀>\"` 的 `.vue` 渲染点（实测 h7 已挂 3 处 ⇒ 其导出必 405）",
            "⑥ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
    "G6": {
        "title": "M 族专属通路对未知 sheet 值无可读错误（静默回退全部 / 静默按默认 sheet / service 模块缺失）",
        "status": _MEASURED_STATUS,
        "owner_spec": "各 M 循环 spec（存量缺陷；本 spec 的 X-3 通路另走共享实现，不改这些分支）",
        "verdict_default": "real_drift",
        "probe_id": "g6_m_cycle_unknown_sheet_silent",
        "method": [
            "① 取运行期形态 B 三态端点 `/api/{长前缀}/{wp_id}/{三态}`，筛出 m1~m10（实测 10 个前缀齐全）",
            "② `inspect.signature(handler)` 判是否声明 `sheet` 参数 —— 未声明则 FastAPI **静默丢弃**该 query 参数",
            "③ 从宿主模块源码取 `from app.services.<X> import` 的委派 service 模块，并判该 `.py` 是否真实存在",
            "④ 在 service 源码上判未知 sheet 的处置：`if sheet and sheet in <白名单> … else <全部>` / `sheet or \"<默认>\"` / `raise HTTPException(… sheet …)`",
            "⑤ 收录判据 = 三态路径上**不存在**任何针对未知 sheet 值的可读错误；对照组 = 工厂 `_cycle_import_export_common._validate` 必须被判为 `RAISE_ON_SHEET`（否则判据恒真、本组打红）",
            "⑥ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
    "G7": {
        "title": "`_h5_import_export` / `_n4_import_export` 是父 spec Task 25 的不可删项",
        "status": _MEASURED_STATUS,
        "owner_spec": "workpaper-import-export-lifecycle-closure Task 25（删除清单须移出这两个模块，R9.4）",
        "verdict_default": "real_drift",
        "probe_id": "g7_task25_non_deletable_factory_modules",
        "method": [
            "① 取 catalog 中 `api_prefix ∈ {h5, n4}` 的启用条目（实测 H5-2 / H5-3 · N4-2 / N4-3）",
            "② 取 `_kfgh_cycle_adapters._PREFIX_TO_MODULE['h5'|'n4']`，判其是否仍指向工厂模块（实测 `_h5_import_export` / `_n4_import_export`）",
            "③ 判该前缀有无严格形态 A 宿主：实测无 —— 其三态是第三形态 `/api/{prefix}/{三态}`（路径无 `{wp_id}` 段），宿主为专属 router `h5_oil_gas_assets` / `n4_taxes_and_surcharges`",
            "④ 因果补记（任务 1.4 口径修正一）：二者实质同为「界面走专属 router、bulk 走工厂闭包」的存量不同源，只因 URL 是第三形态才不计入 G4 的 5 例。🔴 不得为「统一口径」把 G4 基线改成 7 —— 那是把口径错误锁成基线",
            "⑤ 三条活因（catalog 启用 + 无形态 A 宿主 + adapter 指向工厂）任一不成立即应下调本组基线",
            "⑥ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
    "G8": {
        "title": "`N3-3` 源模板笔误（第 2 行标题写成「递延所得税**资产**」+ 第 3 行「编制人：」重复）",
        "status": _MEASURED_STATUS,
        "owner_spec": "源模板维护方（`backend/wp_templates/` 只读，R11.1 ⇒ 登记不修）",
        "verdict_default": "real_drift",
        "probe_id": "g8_source_template_title_typo",
        "method": [
            "① `find_template_file(<循环>)` 定位源模板（不写文件名字面量），`openpyxl.load_workbook(..., read_only=True)` 打开，tab 取 catalog `sheet_name`",
            "② 读第 2 行首个非空单元格为标题；期望它包含模板文件名的业务名（业务名取文件名空格后一段，再截掉括号补充）",
            "③ 读第 3 行全部非空标签，统计重复标签",
            "④ 收录判据 = 标题不含业务名 或 第 3 行有重复标签（实测仅 N3-3 命中：标题为「递延所得税资产调整分录汇总表」而文件为「N3 递延所得税负债.xlsx」；第 3 行 `编制人：` 出现 2 次）",
            "⑤ 对照组 = 其余 15 张必须判为正常（若 16 张全被判异常 ⇒ 判据过宽，本组打红）。🔴 括号截断规则必须保留：去掉它会把 `M2-3`（文件「M2 实收资本（股本）」/ 标题「实收资本…」）误判成笔误",
            "⑥ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
    "G9": {
        "title": "`K3-3` 的上游 `k_cycle_ie_manifest.yaml` 与 catalog 同错（改 catalog 会被重生成打回）",
        "status": _MEASURED_STATUS,
        "owner_spec": "workpaper-import-export-lifecycle-closure（既有缺陷，不在本 spec 行为半径）",
        "verdict_default": "real_drift",
        "probe_id": "g9_upstream_manifest_same_error",
        "method": [
            "① 读 `backend/data/acnr/sources/k_cycle_ie_manifest.yaml` 取 `K3-3` 的 `item_id`（实测 `K3-3-rows`）",
            "② 读 catalog `K3-3.import_export.item_id`（实测 `K3-3-rows`，与 manifest 同值 ⇒ catalog 的错来自上游）",
            "③ 读 `backend/data/adjustment_ie_contract.json` 的 `sheets['K3-3'].item_id`（实测 `K3-3-adj-entries`）",
            "④ 前端 `k3/core/K3TabAdjustment.vue`：`const ITEM_PREFIX = 'K3-3-adj'` + `` `${ITEM_PREFIX}-entries` `` 读写两侧 ⇒ 真键 `K3-3-adj-entries`；`K3-3-rows` 在前端生产代码零命中",
            "⑤ 收录判据 = manifest 值 == catalog 值 且二者 != 契约清单实测键；任一不成立即应下调本组基线",
            "⑥ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
    "G10": {
        "title": "只写不读：X-3 键族在前端生产代码有写入、零读回路径（用户填完刷新即看不见）",
        "status": _MEASURED_STATUS,
        "owner_spec": "本 spec（R6.5 / R6.7 使其成为必要条件 ⇒ 任务 4.2 + 11.1 补齐，任务 11.2 下调基线到 0）",
        "verdict_default": "real_drift",
        "probe_id": "g10_write_only_key_family",
        "method": [
            "① 逐 sheet 取两个前端生产文件：`components/workpaper/composables/use{X}Adjustment.ts` 与 `components/workpaper/{x}/core/{X}TabAdjustment.vue`，先剥注释（防注释里的示例键蒙对）",
            "② 从**写入侧**表达式派生 entries 键族（`itemId:` / `saveField(` / `debouncedSave(` / `saveBatch(` 的键表达式）—— 模板字面量与单键字面量归约到同一族正则，不写死键表",
            "③ 解析 `const <ident> = '<字面量>'` 别名（M3/M4/M5/M10 的 `const prefix = '{X}-3-entry-'` 即别名读法）",
            "④ 在同两文件里找该族的读取表达式：`.get(<键或别名>)` / `startsWith(<族前缀或别名>)`；机制 ① 另判 `getField('3','entries')`（其键在运行期三段拼出、字面量不存在）",
            "⑤ 收录判据 = 写入命中 > 0 且读取命中 == 0（design §C7 原值 4：L6-3 / M1-3 / M2-3 / M9-3；任务 4.2 + 11.1 施加后实测 0，16/16 READ_OK ⇒ 任务 11.2 按规范下调基线到 0）",
            "⑥ 对照组 = 其余 12 张必须判为「有读回」，且不允许出现读写双零命中的 sheet（那说明键族派生失效，本组打红）",
            "🔴 ⑦ 判据强弱的显式裁决（任务 11.2）：**本组只判「读回表达式存在」这一层，弱于 R6.5 / R6.7**。"
            "「存在读回表达式」不等于「导入后界面读得到」——`@imported=\"() => {}\"`、处理器只弹成功提示、"
            "或只 `loadData()` 而不重跑读回，三种写法下本组照旧判 READ_OK。实测已验证：任务 11.1 的变异 M4"
            "（处理器只 `loadData()` 不读回）下本组实测**仍为 0**，只有 GS5b 打红 ⇒ 本组不重复实现该行为判据"
            "（避免出现第二份会分叉的行为判据）",
            "⑧ 行为面承载者 = 前端守卫 `GS5b · X-3 的 @imported → 读回可追溯`（`components/workpaper/__tests__/ieWiringIntegrity.spec.ts`，任务 11.1，R6.5 / R6.7）；"
            "本组探针对它做**承载者在位性**交叉引用锁（`diagnostics.behavioral_layer`：describe 块在位 + 读 `@imported` 属性 + 要求重载调用 + 要求与 onMounted 共用的读回 + `violations…toEqual([])` 断言 + `it` 用例 ≥3），"
            "任一不成立即整组 `PROBE_SELFCHECK_FAILED` 打红 —— 不许在弱判据上锁 0 而不留痕",
            "⑨ 行为面复算命令（约 20 秒）：`cd audit-platform/frontend && npx vitest run --silent=true src/components/workpaper/__tests__/ieWiringIntegrity.spec.ts`（基线 32 passed / 0 failed）",
            "⑩ 本组自我失效演练（任务 11.2 实测）：施加任务 11.1 变异 M3（摘掉某张的读回表达式）⇒ 本组实测 0 → 1、`--check` 判 REGRESSION 且 exit 2 ⇒ 下调后的 0 非恒真",
            "⑪ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
    "G11": {
        "title": "`N5-3` 的 `'N5-3-entries'` 字面量属中央同步键，与真数据键同名不同源",
        "status": _MEASURED_STATUS,
        "owner_spec": "本 spec（登记以防下一轮再按字面量 grep 得出「键不可确证」的错结论）",
        "verdict_default": "probe_false_negative",
        "probe_id": "g11_same_name_different_source",
        "method": [
            "① 在 `n5/core/N5TabAdjustment.vue`（剥注释后）找 `'N5-3-entries'` 字面量（实测 1 处）",
            "② 向上找最近的 `useAdjustmentCentralSync({` 调用，判该字面量是否落在其实参块内 ⇒ 是则属**中央同步键**（`source_ref` 组成部分），不是 `checklist_responses.item_id` 落点",
            "③ 走形态 ④ 三步链取真键：tab 的 `formData.setField('3','entries')` / `getField('3','entries')` → `composables/useN5FormData.ts` 的 `const ITEM_PREFIX = 'N5-'` → `` const itemId = `${ITEM_PREFIX}${sheet}-${field}` `` ⇒ 拼出 `N5-3-entries`",
            "④ 收录判据 = 字面量全部落在中央同步实参块内 且 三段拼装出的真键与该字面量同名（同名不同源）",
            "⑤ 反证（判据非空转）：改 `useN5FormData.ts` 的 `ITEM_PREFIX` 值 ⇒ 真键随之变而 tab 内字面量不变 ⇒ 两者确非同源",
            "⑥ 复算命令：`" + _REPO_CMD + "`",
        ],
    },
}

_PROBES: dict[str, Callable[[], Probe]] = {
    "G1": probe_g1,
    "G2": probe_g2,
    "G3": probe_g3,
    "G4": probe_g4,
    "G5": probe_g5,
    "G6": probe_g6,
    "G7": probe_g7,
    "G8": probe_g8,
    "G9": probe_g9,
    "G10": probe_g10,
    "G11": probe_g11,
}


# ═══════════════════════════════════════════════════════════════════════════════
# CI job 复算（裁决 2 的三字段）
# ═══════════════════════════════════════════════════════════════════════════════


def run_ci_probe(cmd: str, timeout: int = 1800) -> dict[str, Any]:
    """真跑一条 CI 命令，取退出码与时间戳（`observed_*` 三字段的来源）。"""
    started = _now()
    argv = cmd.split()
    proc = subprocess.run(  # noqa: S603 — 命令来自本文件内的常量
        argv,
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).splitlines()
    tail = [ln.strip() for ln in out if ln.strip()][-3:]
    return {
        "observed_exit_code": proc.returncode,
        "observed_at": started,
        "reproduce_cmd": cmd,
        "observed_tail": tail,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 登记表构建（`--emit`）
# ═══════════════════════════════════════════════════════════════════════════════


def load_committed() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(_read(REGISTRY_PATH))


def _committed_groups(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {g.get("group"): g for g in (doc.get("groups") or [])}


def build_registry(
    probes: dict[str, Probe],
    *,
    committed: dict[str, Any],
    set_baselines: bool,
    ci_results: dict[str, dict[str, Any]] | None,
    lowered_by_task: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """从活探针构建登记表。基线**默认沿用已提交值**（无提交则取 design §C7）。"""
    prev = _committed_groups(committed)
    warnings: list[str] = []
    groups: list[dict[str, Any]] = []

    for gid in _DESIGN_BASELINE:
        meta = _GROUPS[gid]
        probe = probes[gid]
        old = prev.get(gid, {})
        design_base = _DESIGN_BASELINE[gid]
        baseline = old.get("baseline_count", design_base)
        lowered_from = old.get("baseline_lowered_from")
        lowered_by = old.get("lowered_by_task")

        # 已下调过、但 `lowered_by_task` 还是占位/缺失的组：允许用本次 `--lowered-by-task`
        # 补点名。🔴 只补「占位或缺失」的，不覆盖已写好的真任务号 —— 否则后一轮任务会把
        # 前一轮的下调者改写成自己（下调归属就再也追不回来了）。
        if lowered_by_task and lowered_from is not None and (
            not lowered_by or str(lowered_by).strip() == _LOWERED_BY_PLACEHOLDER
        ):
            lowered_by = lowered_by_task

        if set_baselines and probe.measured is not None and probe.measured != baseline:
            if probe.measured < baseline:
                lowered_from = lowered_from or design_base
                # 显式 `--lowered-by-task` 优先于已提交值（旧值可能是占位文案）
                lowered_by = lowered_by_task or lowered_by or _LOWERED_BY_PLACEHOLDER
                if lowered_by == _LOWERED_BY_PLACEHOLDER:
                    warnings.append(
                        f"{gid}: 下调基线未点名任务 ⇒ 写入占位值，`--check` 会判 STRUCTURE_ERROR；"
                        "请加 `--lowered-by-task <任务号>` 重出"
                    )
            baseline = probe.measured
            warnings.append(f"{gid}: baseline_count 由 --set-baselines 改为实测值 {baseline}")
        elif probe.measured is not None and probe.measured != baseline:
            warnings.append(
                f"{gid}: 实测 {probe.measured} != 基线 {baseline} —— `--emit` 不动基线，"
                "确需变更请显式加 `--set-baselines`（自我失效机制不得被顺手绕过）"
            )

        entry = {
            "group": gid,
            "title": meta["title"],
            "baseline_count": baseline,
            "measured_count": probe.measured,
            "status": meta["status"],
            "owner_spec": meta["owner_spec"],
            "verdict_default": meta["verdict_default"],
            "method": meta["method"],
            "probe": {
                "id": meta["probe_id"],
                "implemented_by": "backend/scripts/check/check_x3_deviation_registry.py",
                "selfcheck_ok": probe.selfcheck_ok,
                "selfcheck_notes": probe.selfcheck_notes,
                "diagnostics": probe.diagnostics,
            },
            "entries": probe.entries,
        }
        if "owner_task" in meta:
            entry["owner_task"] = meta["owner_task"]
        if lowered_from is not None:
            entry["baseline_lowered_from"] = lowered_from
            entry["lowered_by_task"] = lowered_by
        if "ci_job" in meta:
            recorded = (old.get("ci_job") or {}) if old else {}
            fresh = (ci_results or {}).get(gid)
            merged = {**meta["ci_job"], **{k: v for k, v in recorded.items() if k.startswith("observed")}}
            if fresh:
                merged.update(fresh)
            entry["ci_job"] = merged
        groups.append(entry)

    doc = {
        "_meta": {
            "spec": "x3-adjustment-entry-import-export",
            "task": "1.7",
            "artifact": "Deviation_Registry",
            "purpose": (
                "承载本 spec 半径外/行为不修的已知偏差。守卫基线只收已确证正确的值（R8.6），"
                "已判错位的值一律由本表承载 —— 否则守卫要么把错值锁成基线，要么绕开它们。"
            ),
            "requirements": ["8.3", "8.4", "8.5", "8.6", "8.7", "5.8"],
            "design_ref": "design §C7（十一组 G1~G11）+ §用户裁决 2",
            "generated_by": "python backend/scripts/check/check_x3_deviation_registry.py --emit",
            "checked_by": _REPO_CMD,
            "written_at": _now(),
            "column_contract": (
                "每条恒带三列 catalog_value / contract_value / frontend_observed（R8.4）；"
                "某列不适用时值为 null 且必须在 na_reasons 里给出理由 —— `--check` 强制。"
            ),
            "verdict_values": list(_VERDICTS),
            "self_invalidation": (
                "每组带 baseline_count；--check 用活探针重算实测数：相等=OK / 实测>基线=REGRESSION / "
                "实测<基线=NEEDS_BASELINE_LOWERING（要求同步下调，不下调即打红）。"
                "下调基线的唯一合法形态 = 同时给出 baseline_lowered_from（design §C7 原值）与 lowered_by_task。"
            ),
            "design_baseline": dict(_DESIGN_BASELINE),
            "totals": {
                "groups": len(groups),
                "baseline_sum": sum(g["baseline_count"] for g in groups),
                "measured_sum": sum(g["measured_count"] or 0 for g in groups),
                "entries_landed": sum(len(g["entries"]) for g in groups),
                "pending_groups": [g["group"] for g in groups if g["status"] == _PENDING_STATUS],
            },
        },
        "groups": groups,
    }
    return doc, warnings


# ═══════════════════════════════════════════════════════════════════════════════
# 校验（`--check`）
# ═══════════════════════════════════════════════════════════════════════════════

_STATE_OK = "OK"
_STATE_REGRESSION = "REGRESSION"
_STATE_LOWER = "NEEDS_BASELINE_LOWERING"
_STATE_PENDING = "PENDING"
_STATE_STRUCT = "STRUCTURE_ERROR"
_STATE_PROBE = "PROBE_SELFCHECK_FAILED"
_STATE_DRIFT = "ENTRY_DRIFT"


def _validate_structure(gid: str, group: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    required = ("title", "baseline_count", "status", "owner_spec", "verdict_default", "method", "entries", "probe")
    for key in required:
        if key not in group:
            problems.append(f"缺字段 `{key}`")
    if problems:
        return problems

    design_base = _DESIGN_BASELINE[gid]
    baseline = group["baseline_count"]
    if not isinstance(baseline, int) or baseline < 0:
        problems.append(f"`baseline_count` 非法：{baseline!r}")
    elif baseline != design_base:
        if baseline > design_base:
            problems.append(
                f"`baseline_count`={baseline} > design §C7 的 {design_base} —— 基线只许下调，"
                "上调等于把新增偏差锁成基线"
            )
        elif group.get("baseline_lowered_from") != design_base or not group.get("lowered_by_task"):
            problems.append(
                f"`baseline_count`={baseline} 低于 design §C7 的 {design_base}，但未给出"
                " `baseline_lowered_from`（须等于 design 原值）+ `lowered_by_task` ⇒ 拒绝接受"
            )
        else:
            # 🔴 `lowered_by_task` 必须是**真任务号**：占位文案非空，旧版 `not …` 判不出来
            # ⇒ 「下调基线必须点名任务」会被一句占位糊过去（自我失效机制的一道缝）。
            by_task = str(group.get("lowered_by_task")).strip()
            if by_task == _LOWERED_BY_PLACEHOLDER or not _RE_TASK_NO.match(by_task):
                problems.append(
                    f"`lowered_by_task`={by_task!r} 不是 spec 任务号（如 `11.2`）—— 下调基线必须点名"
                    "由哪个任务下调，占位文案不接受；重出命令："
                    "`python backend/scripts/check/check_x3_deviation_registry.py --emit"
                    " --set-baselines --lowered-by-task <任务号> --no-ci-probe`"
                )

    if group["status"] not in (_MEASURED_STATUS, _PENDING_STATUS):
        problems.append(f"`status` 非法：{group['status']!r}")
    if group["status"] == _PENDING_STATUS and not group.get("owner_task"):
        problems.append("`status=pending` 但缺 `owner_task`（谁在什么任务落值）")
    if group["verdict_default"] not in _VERDICTS:
        problems.append(f"`verdict_default` 不在枚举内：{group['verdict_default']!r}")

    method = group.get("method") or []
    if not isinstance(method, list) or len(method) < 2:
        problems.append("`method` 须为 ≥2 步的列表（一步的「方法」无法复算）")
    else:
        joined = "\n".join(str(s) for s in method)
        hit = [p for p in _FORBIDDEN_METHOD_PHRASES if p in joined]
        if hit:
            problems.append(f"`method` 含不可复算措辞 {hit} —— 须写成逐步命令/步骤")
        if "python " not in joined:
            problems.append("`method` 未含任何可执行命令（至少要有一条 `python …` 复算命令）")

    if "ci_job" in _GROUPS[gid]:
        ci = group.get("ci_job") or {}
        for key in ("observed_exit_code", "observed_at", "reproduce_cmd"):
            if ci.get(key) in (None, ""):
                problems.append(f"`ci_job.{key}` 缺失 —— 裁决 2 要求三字段齐全且可复算")
        cmd = str(ci.get("reproduce_cmd") or "")
        script = cmd.split()[-1] if cmd else ""
        if script and not (ROOT / script).exists():
            problems.append(f"`ci_job.reproduce_cmd` 指向的脚本不存在：{script}")

    for idx, item in enumerate(group.get("entries") or []):
        prefix = f"entries[{idx}]({item.get('key')})"
        for col in ("catalog_value", "contract_value", "frontend_observed"):
            if col not in item:
                problems.append(f"{prefix} 缺三列之一 `{col}`（R8.4）")
            elif item[col] is None and not (item.get("na_reasons") or {}).get(col):
                problems.append(f"{prefix} 的 `{col}` 为 null 但未给 `na_reasons.{col}`")
        if item.get("verdict") not in _VERDICTS:
            problems.append(f"{prefix} 的 `verdict` 不在枚举内：{item.get('verdict')!r}")
        if item.get("method_ref") != f"{gid}.method":
            problems.append(f"{prefix} 的 `method_ref` 无法解析到本组 method：{item.get('method_ref')!r}")
        if not item.get("evidence"):
            problems.append(f"{prefix} 缺 `evidence`")
    return problems


def _entry_fingerprint(entries: list[dict[str, Any]]) -> dict[str, tuple[Any, ...]]:
    return {
        str(e.get("key")): (
            e.get("catalog_value"),
            e.get("contract_value"),
            e.get("frontend_observed"),
            e.get("verdict"),
        )
        for e in entries
    }


def check(*, verify_ci: bool, quiet: bool) -> int:
    committed = load_committed()
    if not committed:
        print(f"[FAIL] 登记表不存在：{REGISTRY_PATH.relative_to(ROOT).as_posix()}")
        print("       先跑 `python backend/scripts/check/check_x3_deviation_registry.py --emit`")
        return 2

    groups = _committed_groups(committed)
    missing = [g for g in _DESIGN_BASELINE if g not in groups]
    extra = [g for g in groups if g not in _DESIGN_BASELINE]
    states: dict[str, str] = {}
    details: list[str] = []

    if missing:
        details.append(f"[STRUCTURE] 登记表缺组 {missing}（design §C7 要求十一组齐全）")
    if extra:
        details.append(f"[STRUCTURE] 登记表出现未知组 {extra}")

    rows: list[tuple[str, Any, Any, str]] = []
    for gid in _DESIGN_BASELINE:
        group = groups.get(gid)
        if group is None:
            states[gid] = _STATE_STRUCT
            rows.append((gid, "?", "?", _STATE_STRUCT))
            continue

        problems = _validate_structure(gid, group)
        probe = _PROBES[gid]()
        baseline = group.get("baseline_count")
        measured = probe.measured

        state = _STATE_OK
        if problems:
            state = _STATE_STRUCT
            for p in problems:
                details.append(f"[{gid} STRUCTURE] {p}")
        if not probe.selfcheck_ok:
            state = _STATE_PROBE
            for note in probe.selfcheck_notes:
                details.append(f"[{gid} PROBE] {note}")
        elif probe.selfcheck_notes:
            for note in probe.selfcheck_notes:
                details.append(f"[{gid} NOTE] {note}")

        if state in (_STATE_OK, _STATE_DRIFT):
            if measured is None:
                state = _STATE_PENDING
                landed = len(group.get("entries") or [])
                details.append(
                    f"[{gid} PENDING] 本组尚无可复算实测数（owner_task={group.get('owner_task')}）；"
                    f"已落值 {landed} / 基线 {baseline}，待落 {baseline - landed} 条"
                )
                if landed > (baseline or 0):
                    details.append(f"[{gid} STRUCTURE] 已落值 {landed} > 基线 {baseline}")
                    state = _STATE_STRUCT
            elif measured > baseline:
                state = _STATE_REGRESSION
                details.append(
                    f"[{gid} REGRESSION] 实测 {measured} > 基线 {baseline} —— 新增偏差，先查改动再谈改基线"
                )
            elif measured < baseline:
                state = _STATE_LOWER
                details.append(
                    f"[{gid} NEEDS_BASELINE_LOWERING] 实测 {measured} < 基线 {baseline} —— "
                    f"有 {baseline - measured} 条已被修好，必须把 `baseline_count` 同步下调到 {measured}"
                    f"（并写 `baseline_lowered_from`={_DESIGN_BASELINE[gid]} + `lowered_by_task`），"
                    "否则本表留着虚高基线继续绿 = 自我失效机制被绕过"
                )
            else:
                live = _entry_fingerprint(probe.entries)
                stored = _entry_fingerprint(group.get("entries") or [])
                if live != stored and group["status"] != _PENDING_STATUS:
                    state = _STATE_DRIFT
                    only_live = sorted(set(live) - set(stored))
                    only_stored = sorted(set(stored) - set(live))
                    changed = sorted(k for k in set(live) & set(stored) if live[k] != stored[k])
                    details.append(
                        f"[{gid} ENTRY_DRIFT] 实测条目与登记条目不一致 —— "
                        f"仅实测有={only_live} / 仅登记有={only_stored} / 三列有变={changed}；"
                        "跑 `--emit` 重出登记表"
                    )

        states[gid] = state
        rows.append((gid, baseline, "pending" if measured is None else measured, state))

    if verify_ci:
        for gid in ("G2", "G3"):
            group = groups.get(gid) or {}
            ci = group.get("ci_job") or {}
            cmd = ci.get("reproduce_cmd")
            if not cmd:
                continue
            fresh = run_ci_probe(str(cmd))
            recorded = ci.get("observed_exit_code")
            if fresh["observed_exit_code"] != recorded:
                states[gid] = _STATE_STRUCT
                details.append(
                    f"[{gid} CI] `{cmd}` 实测 exit={fresh['observed_exit_code']}，"
                    f"登记 exit={recorded} —— 登记值已过期（裁决 2 的三字段必须可复算）"
                )
            else:
                details.append(f"[{gid} CI] `{cmd}` 复算 exit={fresh['observed_exit_code']}，与登记一致")

    if not quiet:
        print("=" * 92)
        print(f"X-3 Deviation_Registry —— {REGISTRY_PATH.relative_to(ROOT).as_posix()}")
        print("=" * 92)
        print(f"{'组':<5}{'基线':>6}{'实测':>10}   状态")
        print("-" * 92)
        for gid, baseline, measured, state in rows:
            print(f"{gid:<5}{str(baseline):>6}{str(measured):>10}   {state}")
        print("-" * 92)
        meta_totals = (committed.get("_meta") or {}).get("totals") or {}
        print(
            f"基线合计 {sum(v for _, v, _, _ in rows if isinstance(v, int))}"
            f" · 已落值条目 {meta_totals.get('entries_landed')}"
            f" · 组数 {len(rows)}"
        )
        if details:
            print()
            for line in details:
                print(line)

    bad = {g: s for g, s in states.items() if s != _STATE_OK}
    if missing or extra:
        bad.setdefault("_registry", _STATE_STRUCT)
    if not bad:
        print("\n[OK] 十一组全部收口：实测数与基线逐组相等，结构与三列契约齐全。")
        return 0
    print(f"\n[NOT-CLOSED] {len(bad)} 组未收口：{json.dumps(bad, ensure_ascii=False)}")
    return 2


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def emit(*, set_baselines: bool, ci_probe: bool, lowered_by_task: str | None = None) -> int:
    probes = {gid: fn() for gid, fn in _PROBES.items()}
    ci_results: dict[str, dict[str, Any]] = {}
    if ci_probe:
        for gid in ("G2", "G3"):
            cmd = _GROUPS[gid]["ci_job"]["reproduce_cmd"]
            print(f"[CI] 复算 {cmd} …")
            ci_results[gid] = run_ci_probe(cmd)
            print(f"     exit={ci_results[gid]['observed_exit_code']} at {ci_results[gid]['observed_at']}")
    doc, warnings = build_registry(
        probes,
        committed=load_committed(),
        set_baselines=set_baselines,
        ci_results=ci_results,
        lowered_by_task=lowered_by_task,
    )
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(f"[EMIT] 已写 {REGISTRY_PATH.relative_to(ROOT).as_posix()}")
    for gid, probe in probes.items():
        print(
            f"   {gid:<4} 基线={next(g['baseline_count'] for g in doc['groups'] if g['group'] == gid):<3}"
            f" 实测={'pending' if probe.measured is None else probe.measured:<8}"
            f" 条目={len(probe.entries):<3} selfcheck={'ok' if probe.selfcheck_ok else 'FAILED'}"
        )
    for w in warnings:
        print(f"   [WARN] {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="X-3 Deviation_Registry 探针与守卫（design §C7 十一组）",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="重算实测数并与基线比对（CI 用；0 收口 / 2 未收口）")
    mode.add_argument("--emit", action="store_true", help="从活探针写登记表 JSON（唯一写盘路径）")
    parser.add_argument(
        "--set-baselines",
        action="store_true",
        help="仅与 --emit 同用：允许把 baseline_count 改成实测值（缺省不改，防绕过自我失效）",
    )
    parser.add_argument(
        "--lowered-by-task",
        metavar="任务号",
        help=(
            "仅与 --emit --set-baselines 同用：点名由哪个 spec 任务下调基线（如 11.2）。"
            "缺省写入占位值，`--check` 会判 STRUCTURE_ERROR"
        ),
    )
    parser.add_argument(
        "--no-ci-probe",
        action="store_true",
        help="仅与 --emit 同用：跳过两条 CI 命令的实跑（则 observed_* 沿用已提交值）",
    )
    parser.add_argument(
        "--verify-ci",
        action="store_true",
        help="仅与 --check 同用：真跑 G2/G3 的 reproduce_cmd 并比对退出码（约 2~4 分钟）",
    )
    parser.add_argument("--quiet", action="store_true", help="只打结论行")
    args = parser.parse_args(argv)

    if args.emit:
        return emit(
            set_baselines=args.set_baselines,
            ci_probe=not args.no_ci_probe,
            lowered_by_task=args.lowered_by_task,
        )
    return check(verify_ci=args.verify_ci, quiet=args.quiet)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 —— 脚本自身异常必须显式区别于「未收口」
        print(f"[ERROR] 探针执行失败（不得当作收口）：{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
