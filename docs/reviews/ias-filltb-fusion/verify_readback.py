"""直接复核最终交付；不重建工作簿，不运行产品或数据库。"""
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from openpyxl import load_workbook
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('delivery_gen', OUT/'generate_review.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)
report = gen.readj(OUT/'validation_report.json')
manifest = gen.readj(OUT/'source_manifest.json')
catalog = gen.readj(OUT/'catalog.json')
assert report['status']=='passed' and report['catalog_version']==catalog['catalog_version']
assert len(catalog['fusion_comparisons']) >= 12
for source in manifest['sources']:
    assert gen.sha((OUT/source['snapshot_path']).read_bytes())==source['snapshot_sha256']
    original = ROOT/source['source_path']
    if original.exists():
        assert gen.sha(original.read_bytes())==source['source_sha256']
for key in ['evidence_index','comparison_evidence']:
    assert gen.sha((OUT/manifest[key]['path']).read_bytes())==manifest[key]['sha256']
reads = {}
for name,expected in report['outputs'].items():
    path = OUT/name
    assert gen.sha(path.read_bytes())==expected['sha256']
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert not any('externalLinks/' in s or s.endswith('vbaProject.bin') for s in archive.namelist())
    wb = load_workbook(path,read_only=True,data_only=False)
    assert list(expected['worksheets'])==wb.sheetnames
    for ws in wb:
        rows = ws.iter_rows()
        next(rows)
        count = 0
        for row in rows:
            count += 1
            for c in row:
                assert c.data_type!='f'
                if isinstance(c.value,str):
                    assert c.data_type=='s' and c.number_format=='@'
        assert count==expected['worksheets'][ws.title],(ws.title,count)
    comparison = list(wb['三方差异与融合'].iter_rows(values_only=True))
    assert len(comparison)==len(catalog['fusion_comparisons'])+1
    assert ['当前平台规则','IAS规则','FillTbTool规则']==[v.split(' / ')[0] for v in comparison[0][1:4]]
    wb.close()
    reads[name]={'sha256':expected['sha256'],'sheets':expected['sheet_count'],'bytes':path.stat().st_size}
external = [r for r in catalog['rules'] if r['origin_system']!='platform']
assert external and all(r['mapping_state']!='已确认' and r['integration_state']=='未实施' for r in external)
assert {'1523','1524'} <= {r['original_code'] for r in external}
sources,paths = gen.collect_sources(True)
evidence = gen.external_evidence(sources,True)
rules,edges,counts,_,_,_ = gen.build_catalog(sources,paths,evidence)
assert {r['rule_id'] for r in rules}=={r['rule_id'] for r in catalog['rules']}
assert {r['relation_id'] for r in edges}=={r['relation_id'] for r in catalog['relations']}
assert counts==report['counts']
result={'status':'passed','catalog_version':catalog['catalog_version'],'outputs':reads,'checks':{'final_readback':True,'comparison_columns_side_by_side':True,'source_hashes':True,'snapshot_catalog_replay':True,'external_unconfirmed':True,'no_excel_formulas_external_links_macros':True},'limitations':['完整多轮重建验证在300秒时超时；不将旧版本独立验证报告用于最终版本','最终生成器自身已逐格读回并验证重复生成hash/mtime不变','本脚本不运行平台或真实数据导入']}
gen.put(OUT/'final_validation.json',result)
print(json.dumps(result,ensure_ascii=False,indent=2))
