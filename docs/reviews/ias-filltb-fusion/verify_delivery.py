"""离线交付自检：只改交付产物和指定临时目录，不触碰原始材料。"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
TMP = ROOT / 'tmp_ias_filltb_delivery'
spec = importlib.util.spec_from_file_location('review_generator', OUT / 'generate_review.py')
gen = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(gen)


def snapshot():
    return {str(p.relative_to(OUT)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in OUT.rglob('*') if p.is_file() and p.suffix not in ['.pyc'] and '__pycache__' not in p.parts}


def run(replay=False):
    with patch.object(gen.sys, 'argv', [str(OUT/'generate_review.py')] + (['--replay'] if replay else [])):
        with contextlib.redirect_stdout(io.StringIO()):
            gen.main()


def main():
    TMP.mkdir(exist_ok=True)
    original = {str(p): p.read_bytes() for p in OUT.glob('sources/*facts.json')}
    original[str(OUT/'sources/filltb_selection.json')] = (OUT/'sources/filltb_selection.json').read_bytes()
    run()
    print('基线生成与逐格读回完成', flush=True)
    before = snapshot()
    run()
    assert before == snapshot(), '完整重跑改变了hash或mtime'
    print('独立第二次重跑hash与mtime一致', flush=True)
    run(True)
    assert before == snapshot(), '快照回放与正常输出不同'
    print('仅用持久快照回放一致', flush=True)
    manifest, paths = gen.collect_sources(True)
    evidence = gen.external_evidence(manifest, True)
    first = gen.build_catalog(manifest, paths, evidence)
    actual_read = gen.readj
    def reordered(path):
        value = copy.deepcopy(actual_read(path))
        if Path(path) == paths['chart']:
            value['accounts'].reverse()
        elif Path(path) == paths['wp']:
            value['mappings'].reverse()
        elif Path(path) == paths['push']:
            value['rules'].reverse()
        elif Path(path) == paths['report_map']:
            for rows in value['mappings'].values():
                rows.reverse()
        elif Path(path) == paths['reports']:
            value.reverse()
            for block in value:
                block['rows'].reverse()
        return value
    with patch.object(gen, 'readj', reordered):
        second = gen.build_catalog(manifest, paths, evidence)
    for index, key in [(0, 'rule_id'), (1, 'relation_id')]:
        assert {r[key] for r in first[index]} == {r[key] for r in second[index]}, '排序改变了稳定ID'
    files = [OUT/'规则目录_审阅稿.xlsx', OUT/'编码对照表_审阅稿.xlsx']
    saved = {p: p.read_bytes() for p in files}
    try:
        files[0].unlink()
        files[1].write_bytes(b'isolated-output-corruption-check')
        run(True)
        assert all(p.read_bytes() == raw for p, raw in saved.items()), '丢失或损坏产物未恢复'
    finally:
        for p, raw in saved.items():
            if not p.exists() or p.read_bytes() != raw:
                p.write_bytes(raw)
    assert all(Path(p).read_bytes() == raw for p, raw in original.items()), '人工事实被改写'
    catalog = gen.readj(OUT/'catalog.json')
    result = {'status': 'passed', 'generator_sha256': hashlib.sha256((OUT/'generate_review.py').read_bytes()).hexdigest(),
              'catalog_version': catalog['catalog_version'], 'output_hashes': {p.name: gen.sha(p.read_bytes()) for p in files},
              'checks': {'complete_repeat_hash_and_mtime': True, 'snapshot_replay': True,
                         'reordered_input_preserves_rule_and_relation_ids': True,
                         'missing_workbook_rebuilt': True, 'corrupted_workbook_rebuilt': True,
                         'manual_facts_unchanged': True}}
    target = TMP/'verification.json'
    raw = (json.dumps(result, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    if not target.exists() or target.read_bytes() != raw:
        target.write_bytes(raw)
    gen.put(OUT/'independent_validation.json', result)
    run(True)
    assert gen.readj(OUT/'validation_report.json')['independent_checks'] == result['checks']
    before = snapshot()
    run(True)
    assert before == snapshot(), '合入验证证据后重生成不幂等'
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
