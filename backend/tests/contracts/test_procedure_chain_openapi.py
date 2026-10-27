"""程序链 OpenAPI 子集（spec procedure-chain-hardening-and-java-contracts R23）—— 不连 PostgreSQL。

docs/contracts/procedure-chain/openapi.procedure-chain.json 是生成物（scripts/gen/export_procedure_chain_openapi.py）：
1. 生成物与真实应用一致：对「被改过的副本」不带 --check 重跑 ⇒ 写回的内容与仓库里的文件逐字节相同（= 仓库里的是最新的）；
2. --check 只比对、不写：副本有差异 ⇒ 退出码 2，逐处列出（缺了的接口、多出的字段、改过的值）；
3. 结构：登记的接口不多不少，2xx 的 data 与错误详情挂到契约，所有引用可解析，组件不多不少；
4. 请求模型（pydantic）与契约里的请求定义字段一致、必填一致（含嵌套的选择器 / 条目 / 覆盖项）——
   Python 加了请求字段而契约没跟上 ⇒ 打红；
5. 子集只取登记接口与其引用的组件（传递闭包、按模型名命名），写盘只在内容变化时发生（不计行尾）。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.contracts._contract_schemas import BASE_ID, CONTRACTS, iter_refs, registry

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "gen" / "export_procedure_chain_openapi.py"
OPENAPI = CONTRACTS / "openapi.procedure-chain.json"
ENVELOPE = {"$ref": "common.schema.json#/$defs/responseEnvelope"}


def _script():
    spec = importlib.util.spec_from_file_location("_export_procedure_chain_openapi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("FORCE_COLOR", None)
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=BACKEND, env=env, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=600)
    assert proc.stdout is not None, proc.stderr  # 解码出错时 stdout 为 None：只看退出码会假绿
    return proc


def _doc() -> dict:
    return json.loads(OPENAPI.read_bytes().decode("utf-8"))


def _ops(doc: dict) -> dict:
    return {(method, path): op for path, item in doc["paths"].items() for method, op in item.items()}


# ─── 1 / 2. 生成物最新、--check 报差异 ────────────────────────────────────────


def test_export_reproduces_committed_file_and_check_lists_drift(tmp_path):
    doc = _doc()
    del doc["paths"]["/api/workpapers/{wp_id}/program-row-access"]
    doc["components"]["schemas"]["GenerateFromCodesRequest"]["properties"]["dry_run"] = {"type": "boolean"}
    doc["info"]["version"] = "v0"
    drifted = tmp_path / "openapi.json"
    drifted.write_bytes(json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"))
    before = drifted.read_bytes()

    check = _run("--check", "--out", str(drifted))
    assert check.returncode == 2, check.stdout + check.stderr
    assert drifted.read_bytes() == before, "--check 只比对、不写"
    lines = check.stdout.splitlines()
    for expected in ("  + paths > /api/workpapers/{wp_id}/program-row-access",
                     "  - components > schemas > GenerateFromCodesRequest > properties > dry_run",
                     "  ~ info > version"):
        assert expected in lines, check.stdout
    assert [ln for ln in lines if ln.startswith("[")] == [
        "[ERR] openapi.json 与应用不一致（3 处；- 文件里有、应用里没有，+ 反之，~ 不同）："], check.stdout

    write = _run("--out", str(drifted))
    assert write.returncode == 0, write.stdout + write.stderr
    assert "[OK] 已写入" in write.stdout and "8 个接口" in write.stdout, write.stdout
    assert drifted.read_bytes() == OPENAPI.read_bytes().replace(b"\r\n", b"\n"), (
        "重跑写回的内容与仓库里的文件不同：仓库里的 openapi 不是最新的，不带 --check 重跑脚本并提交")


# ─── 3. 结构 ─────────────────────────────────────────────────────────────────


def test_registered_operations_link_responses_and_errors_to_contracts():
    mod = _script()
    doc = _doc()
    ops = _ops(doc)
    assert set(ops) == {(e["method"], e["path"]) for e in mod.OPERATIONS}, "接口不多不少"
    resolver = registry().resolver(base_uri=BASE_ID)
    for entry in mod.OPERATIONS:
        op = ops[(entry["method"], entry["path"])]
        contract = op["x-contract"]
        assert (op["tags"], contract["response"], contract.get("request")) == ([mod.TAG], entry["response"],
                                                                               entry.get("request"))
        assert ("request" in contract) == ("requestBody" in op), "有请求体的接口必须登记请求契约"
        ok = op["responses"]["200"]["content"]["application/json"]["schema"]
        assert ok["allOf"] == [ENVELOPE] and ok["properties"]["data"] == {"$ref": entry["response"]}, ok
        invalid = op["responses"]["422"]["content"]["application/json"]["schema"]
        assert invalid == {"$ref": "common.schema.json#/$defs/validationErrorBody"}
        errors = entry.get("errors", {})
        assert sorted(op["responses"]) == sorted(["200", "422", *errors]), op["responses"].keys()
        assert contract.get("errors", {}) == {status: list(alts) for status, alts in errors.items()}
        for status, alts in errors.items():
            message = op["responses"][status]["content"]["application/json"]["schema"]["properties"]["message"]
            shapes = message.get("anyOf", [message])
            assert shapes == [{"type": "string"} if a == mod.TEXT else {"$ref": a} for a in alts], (status, message)
        for ref in [contract["response"], contract.get("request"),
                    *(a for alts in errors.values() for a in alts if a != mod.TEXT)]:
            if ref:
                resolver.lookup(ref)  # x-contract 的字符串不是 $ref 键，单独解析
        assert op["security"] == [{"HTTPBearer": []}], "要登录"
    refs = list(iter_refs(doc))
    internal = [r for r in refs if r.startswith("#/")]
    for ref in refs:
        if not ref.startswith("#/"):
            resolver.lookup(ref)  # 解析不到即抛
    assert all(r.startswith("#/components/schemas/") for r in internal), internal
    assert {r.rsplit("/", 1)[1] for r in internal} == set(doc["components"]["schemas"]), "组件不多不少、引用都在"
    assert set(doc["components"]["securitySchemes"]) == {"HTTPBearer"}


# ─── 4. 请求模型 ⇔ 契约请求 ──────────────────────────────────────────────────


def _deref_doc(node: dict, doc: dict):
    while "$ref" in node:
        node = doc["components"]["schemas"][node["$ref"].rsplit("/", 1)[1]]
    return node, doc


def _deref_contract(node: dict, resolver):
    while "$ref" in node:
        resolved = resolver.lookup(node["$ref"])
        node, resolver = resolved.contents, resolved.resolver
    return node, resolver


def _shape(node: dict, ctx, deref):
    """对象 schema 的（字段 → (子节点, 上下文)，必填）。数组取元素；allOf 合并；anyOf / oneOf 取字段并集、必填交集；
    不是对象（标量、任意值、可空标量）返回 None。"""
    node, ctx = deref(node, ctx)
    if "items" in node:
        return _shape(node["items"], ctx, deref)
    props: dict = {}
    required: set[str] = set()
    for sub in node.get("allOf", []):
        got = _shape(sub, ctx, deref)
        if got:
            props.update(got[0])
            required |= got[1]
    alts = [got for got in (_shape(a, ctx, deref) for a in node.get("anyOf", []) + node.get("oneOf", [])) if got]
    for got in alts:
        props.update(got[0])
    if alts:
        required |= set.intersection(*(got[1] for got in alts))
    props.update({k: (v, ctx) for k, v in node.get("properties", {}).items()})
    required |= set(node.get("required", []))
    return (props, required) if props else None


def _compare(py, ct, where: str, out: list[str]) -> None:
    sp, sc = _shape(*py, _deref_doc), _shape(*ct, _deref_contract)
    if sp is None and sc is None:
        return
    if sp is None or sc is None:
        out.append(f"{where}：一侧是对象、另一侧不是")
        return
    if set(sp[0]) != set(sc[0]):
        out.append(f"{where}：只在 Python 的字段 {sorted(set(sp[0]) - set(sc[0]))}，"
                   f"只在契约的字段 {sorted(set(sc[0]) - set(sp[0]))}")
    if sp[1] != sc[1]:
        out.append(f"{where}：必填不同 Python={sorted(sp[1])} 契约={sorted(sc[1])}")
    for key in sorted(set(sp[0]) & set(sc[0])):
        _compare(sp[0][key], sc[0][key], f"{where}.{key}", out)


def _request_problems(doc: dict) -> tuple[int, list[str]]:
    resolver = registry().resolver(base_uri=BASE_ID)
    checked, problems = 0, []
    for (method, path), op in sorted(_ops(doc).items()):
        ref = op["x-contract"].get("request")
        if ref:
            body = op["requestBody"]["content"]["application/json"]["schema"]
            _compare((body, doc), ({"$ref": ref}, resolver), f"{method.upper()} {path}", problems)
            checked += 1
    return checked, problems


def test_request_models_match_contract_requests():
    doc = _doc()
    checked, problems = _request_problems(doc)
    assert checked == 7, "8 个接口里只有程序行归属是 GET、没有请求体"
    assert not problems, "\n".join(problems)

    # 比对器本身不空转：三种漂移各报一条，且报在对的位置
    drifted = copy.deepcopy(doc)
    schemas = drifted["components"]["schemas"]
    schemas["GenerateFromCodesRequest"]["properties"]["dry_run"] = {"type": "boolean"}
    schemas["DelegationSelector"]["required"] = ["kind", "cycle"]
    del schemas["FieldOverrideItem"]["properties"]["value"]
    _checked, problems = _request_problems(drifted)
    assert sorted(problems) == sorted([
        "POST /api/projects/{project_id}/working-papers/generate-from-codes：只在 Python 的字段 ['dry_run']，只在契约的字段 []",
        "POST /api/projects/{pid}/procedure-delegations/apply.selector：必填不同 Python=['cycle', 'kind'] 契约=['kind']",
        "POST /api/projects/{pid}/procedure-delegations/preview.selector：必填不同 Python=['cycle', 'kind'] 契约=['kind']",
        "POST /api/workpapers/field-overrides/batch.items：只在 Python 的字段 []，只在契约的字段 ['value']",
    ]), problems


# ─── 5. 子集规则、写盘 ───────────────────────────────────────────────────────


def test_subset_takes_registered_operations_and_their_component_closure():
    mod = _script()
    entry = mod.OPERATIONS[-1]
    body_ref = {"$ref": "#/components/schemas/app__routers__m__Batch"}
    spec = {
        "openapi": "3.1.0",
        "paths": {entry["path"]: {entry["method"]: {
            "operationId": "batch", "summary": "Batch", "description": "长说明", "tags": ["数据"],
            "security": [{"HTTPBearer": []}], "requestBody": {"content": {"application/json": {"schema": body_ref}}},
            "responses": {"200": {"content": {"application/json": {"schema": {}}}}},
        }}, "/api/other": {"get": {"operationId": "other", "responses": {}}}},
        "components": {
            "schemas": {
                "app__routers__m__Batch": {"title": "Batch", "properties": {
                    "items": {"type": "array", "items": {"$ref": "#/components/schemas/app__a__Item"}},
                    "other": {"$ref": "#/components/schemas/app__b__Item"}}},
                "app__a__Item": {"title": "Item", "properties": {"a": {"type": "string"}}},
                "app__b__Item": {"title": "Item", "properties": {"b": {"type": "string"}}},
                "Unrelated": {"title": "Unrelated"},
            },
            "securitySchemes": {"HTTPBearer": {"type": "http", "scheme": "bearer"}, "Other": {"type": "apiKey"}},
        },
    }
    doc, missing = mod.build_subset(spec)
    assert missing == [f"{e['method'].upper()} {e['path']}" for e in mod.OPERATIONS[:-1]]
    assert list(doc["paths"]) == [entry["path"]]
    assert sorted(doc["components"]["schemas"]) == ["Batch", "app__a__Item", "app__b__Item"], (
        "传递闭包；按模型名命名，同名的保留原键")
    op = doc["paths"][entry["path"]][entry["method"]]
    assert op["requestBody"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/Batch"}
    assert doc["components"]["schemas"]["Batch"]["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/app__a__Item"}
    assert ("description" in op, op["tags"]) == (False, [mod.TAG])
    assert doc["components"]["securitySchemes"] == {"HTTPBearer": {"type": "http", "scheme": "bearer"}}
    assert spec["components"]["schemas"]["app__routers__m__Batch"]["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/app__a__Item"}, "不改输入"
    assert mod.render(doc) == mod.render(mod.build_subset(spec)[0]), "同一输入同一输出"


def test_write_only_when_content_changes(tmp_path):
    mod = _script()
    target = tmp_path / "openapi.json"
    assert mod.write_if_changed(target, "{}\n") is True
    os.utime(target, ns=(10**18, 10**18))
    assert mod.write_if_changed(target, "{}\n") is False and target.stat().st_mtime_ns == 10**18
    target.write_bytes(b"{}\r\n")  # Windows 检出（autocrlf）是 CRLF：只差行尾不算变化
    os.utime(target, ns=(10**18, 10**18))
    assert mod.write_if_changed(target, "{}\n") is False and target.stat().st_mtime_ns == 10**18
    assert mod.write_if_changed(target, '{"a": 1}\n') is True and target.read_bytes() == b'{"a": 1}\n'
