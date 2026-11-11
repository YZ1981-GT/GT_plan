"""离线审阅交付工具：只读本地源，不导入产品模块、不执行 SQL。"""
import ast
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SCHEMA = 'ias-filltb-review-1'
DATE = '2026-11-11'
INITIAL_HEAD = '9684955683720068cf3aad82dfc5502a0194e73c'
PLATFORM = {'chart':'backend/data/standard_account_chart.json', 'report_map':'backend/data/account_to_report_line_seed.json', 'reports':'backend/data/report_config_seed.json', 'wp':'backend/data/wp_account_mapping.json', 'push':'backend/data/formula_push_rules.json', 'recognition':'backend/data/ledger_recognition_rules.json', 'identifier':'backend/app/services/ledger_import/identifier.py', 'formula':'backend/app/services/formula_engine.py', 'checks':'backend/app/services/formula_check_catalog.py', 'check_seeds':'backend/app/services/formula_management/logic_check.py', 'pipeline':'backend/app/services/ledger_import/pipeline.py', 'converter':'backend/app/services/ledger_import/converter.py', 'rollup':'backend/app/services/tb_balance_rollup.py', 'mapping':'backend/app/services/mapping_service.py', 'validation':'backend/app/services/import_validation_service.py'}
EXTERNAL = {'ias_ds':'tmp_ias_gitlab/ias-framework/src/cpas-server/nest/cpasApi/logic/methodapi/DisclosureService/dataSource/ds.service.ts', 'ias_sql':'tmp_ias_research/utf8/DBUpdate/Script/6.0.0.076.sql', 'ias_model':'tmp_ias_research/utf8/PDM/workplatform 数据模型/企业基础数据/base.reportItems 报表项目基础数据.sql', 'filltb_ah':'tmp_filltb_research/km/cmp_AH_导入报表科目对照码.tsv', 'filltb_f':'tmp_filltb_research/km/cmp_F_导入科目余额表.tsv'}
def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
def sha(x):
    return hashlib.sha256(x if isinstance(x, bytes) else canonical(x).encode('utf-8')).hexdigest()
def put(path, data):
    path = Path(path).resolve()
    assert path.is_relative_to(OUT), '禁止越过交付目录写入'
    data = data if isinstance(data, bytes) else (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
def readj(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def git(cwd, *args):
    p = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True)
    return p.stdout if p.returncode == 0 else None
def assignment(path, name):
    tree = ast.parse(Path(path).read_text(encoding='utf-8-sig'))
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return node.value
    raise ValueError('缺少静态定义：' + name)
def inspect_sources():
    data = {k:readj(ROOT/p) for k,p in PLATFORM.items() if p.endswith('.json')}
    chart = data['chart']['accounts']
    wanted = ['货币','现金','银行','坏账','综合','储备','盈余','分配','研发','信用','其他收益','处置','折旧','摊销']
    report_hits = []
    for b in data['reports']:
        for r in b['rows']:
            if any(n in r['row_name'] for n in ['销售商品','税费返还','货币资金','专项储备']):
                report_hits.append({k:b[k] for k in ['applicable_standard','scope','report_type']} | r)
    wp = data['wp']['mappings']
    print(json.dumps({'branch':git(ROOT,'branch','--show-current').decode().strip(), 'head':git(ROOT,'rev-parse','HEAD').decode().strip(), 'openpyxl':openpyxl.__version__, 'chart':len(chart), 'report_map':{k:len(v) for k,v in data['report_map']['mappings'].items()}, 'reports':sum(len(b['rows']) for b in data['reports']), 'wp':len(wp), 'push':dict(Counter(r['source']['kind'] for r in data['push']['rules'])), 'chart_candidates':[a for a in chart if any(n in a['name'] for n in wanted)], 'wp_candidates':[r for r in wp if r['wp_code'] in ['E1','D2','K1','M7','M9','M4','M5','K6']], 'report_candidates':report_hits[:20], 'tb_columns':ast.literal_eval(assignment(ROOT/PLATFORM['formula'],'COLUMN_ALIASES'))}, ensure_ascii=False,indent=2))
if __name__ == '__main__' and len(sys.argv)>1 and sys.argv[1]=='inspect':
    inspect_sources()
    sys.exit(0)

DIMS = {'soe_standalone':'国企单体', 'soe_consolidated':'国企合并', 'listed_standalone':'上市单体', 'listed_consolidated':'上市合并'}
STATES = {'source_evidence':['源码','静态表','字符串线索','缺数据'], 'mapping_state':['未建立','候选','冲突','已确认'], 'integration_state':['未实施','平台已有','待验收']}
LABELS = dict(item.split('=', 1) for item in ('rule_id=规则ID|relation_id=关系ID|origin_system=来源系统|namespace=命名空间|record_kind=条目类型|original_code=原编码或列位|original_name=原名称|source_code=源编码|source_name=源名称|target_code=目标编码或位置|target_name=目标名称|source_evidence=证据类型|mapping_state=映射状态|integration_state=接入状态|applicable_standard=适用准则|scope=单体合并范围|template_variant=模板版本|report_type=报表类型|period_kind=期间|amount_kind=金额类型|direction=方向|value_basis=数值基础|candidate_reason=候选理由或说明|conflict_group_id=冲突组|missing_reason=材料缺口|orphan_reason=未解析原因|aliases=全部原始别名|canonical_column=规范公式列|account_codes=原科目码集合|note_section=默认附注章节|note_section_soe=国企附注章节|note_section_listed=上市附注章节|report_row=原报表行|cycle=审计循环|source_kind=推送来源类型|target=原目标|expression=原表达式文本|source_id=来源ID|source_path=原来源路径|snapshot_path=持久摘要或快照|source_sha256=原文件SHA256|snapshot_sha256=快照SHA256|content_sha256=条目内容SHA256|payload_sha256=原载荷SHA256|source_commit=来源提交|commit_reason=提交说明|source_state=来源版本状态|authorization_status=授权状态|allowed_use=允许用途边界|authorization_evidence=授权证据|record_locator=原始定位|json_pointer=JSON指针|symbol=源码符号|native_key=原生键|identity_key=身份键|payload=完整条目载荷|relation_kind=关系类型|source_rule_id=源规则ID|target_rule_id=目标规则ID|evidence_rule_id=证据规则ID|conditions=适用条件|lifecycle_status=生命周期|created_at=首次收录|updated_at=内容变更时间|reviewed_by=审阅人|reviewed_at=审阅时间|decision=审阅决定|approved_content_hash=批准内容摘要|integration_evidence=接入依据|source_version=来源版本|key=稳定登记键|label=名称|category=类别|runs_in=代码登记执行位置|edit_where=代码登记编辑位置|loader=加载函数名|files=登记文件|from_db=是否需数据库|allow_empty=是否允许空|description=说明|id=原生ID|refs=原引用|count=数量|metric=统计口径|field=字段|meaning=中文说明').split('|'))

LABELS.update(topic='比较主题', platform_behavior='当前平台规则', ias_behavior='IAS规则', filltb_behavior='FillTbTool规则', difference='主要差异', fusion_action='建议融合方式', phase='交付阶段', source_refs='证据来源ID')


def collect_sources(replay=False):
    old = {s['source_id']:s for s in readj(OUT/'source_manifest.json')['sources']} if (OUT/'source_manifest.json').exists() else {}
    manifest, paths = {}, {}
    for sid, relative in {**PLATFORM, **EXTERNAL}.items():
        platform = sid in PLATFORM
        snapshot = 'sources/platform/' + sid + Path(relative).suffix if platform else 'sources/' + ('ias_review_facts.json' if sid.startswith('ias_') else 'filltb_selection.json')
        original, saved = ROOT/relative, OUT/snapshot
        if platform and (replay or not original.exists()):
            assert sid in old and saved.exists() and sha(saved.read_bytes()) == old[sid]['snapshot_sha256'], '平台回放快照缺失或被改：' + sid
            manifest[sid], paths[sid] = old[sid], saved
            continue
        if platform:
            raw = original.read_bytes()
            put(saved, raw)
        else:
            assert saved.exists(), '人工摘要不能丢失：' + snapshot
            raw = None if replay or not original.exists() else original.read_bytes()
        if raw is None and sid in old:
            assert sha(saved.read_bytes()) == old[sid]['snapshot_sha256'], '无原件时人工摘要变更须重新复核：' + sid
            manifest[sid], paths[sid] = old[sid], saved
            continue
        committed = git(ROOT, 'show', 'HEAD:' + relative) if platform else None
        same = raw is not None and committed is not None and raw.replace(b'\r\n', b'\n') == committed.replace(b'\r\n', b'\n')
        commit = (git(ROOT, 'log', '-1', '--format=%H', '--', relative) or b'').decode().strip() if same else None
        manifest[sid] = dict(source_id=sid, origin_system='platform' if platform else ('ias' if sid.startswith('ias_') else 'filltb'), source_path=relative, snapshot_path=snapshot, source_sha256=sha(raw) if raw is not None else None, snapshot_sha256=sha(saved.read_bytes()), source_commit=commit, commit_reason='与提交内容按换行归一后相同；原字节摘要单列' if same else '工作树或临时外部材料，无已核验的对应提交', source_state='committed_content' if same else 'working_tree' if platform else 'local_review_material', authorization_status='本仓离线审阅' if platform else '转换、分发与运行许可未确认', allowed_use='仅离线人工审阅；非运行包；外部只保留精选事实', authorization_evidence='本次交付范围；不推定商业转换或分发授权')
        if sid == 'ias_ds' and raw is not None:
            clone = ROOT/'tmp_ias_gitlab/ias-framework'
            clone_path = Path(relative).relative_to('tmp_ias_gitlab/ias-framework').as_posix()
            clone_raw = git(clone,'show','HEAD:'+clone_path)
            if clone_raw is not None and raw.replace(b'\r\n',b'\n') == clone_raw.replace(b'\r\n',b'\n'):
                manifest[sid].update(source_commit=git(clone,'rev-parse','HEAD').decode().strip(),commit_reason='已核对IAS本地克隆HEAD内容；未联网更新',source_state='cloned_commit_content')
        paths[sid] = saved if platform else original
    return manifest, paths

def external_evidence(manifest, replay):
    path = OUT/'sources/external_evidence.json'
    previous = readj(path) if path.exists() else {}
    result = {}
    for sid, relative in EXTERNAL.items():
        source = ROOT/relative
        if replay or not source.exists():
            assert sid in previous and previous[sid]['source_sha256'] == manifest[sid]['source_sha256'], '缺少可回放的外部定位摘要：' + sid
            result[sid] = previous[sid]
            continue
        raw = source.read_bytes()
        assert sha(raw) == manifest[sid]['source_sha256'], '读取期间原件变化：' + sid
        lines = raw.decode('utf-8-sig').splitlines()
        locators = {}
        facts = readj(OUT/'sources/ias_review_facts.json')
        if sid.startswith('filltb_'):
            for row in readj(OUT/'sources/filltb_selection.json')['selections']:
                if row[0] != sid:
                    continue
                hits = [n for n, line in enumerate(lines, 1) if list(csv.reader([line], delimiter='\t'))[0][:2] == row[1:3]]
                assert hits, '精选原文或原码不匹配：' + canonical(row[:3])
                locators[canonical(row[1:3])] = {'lines':hits, 'columns':lines[0].split('\t')[:2], 'verified':True}
        else:
            selected = [(b['key'], b['anchor']) for b in facts['behaviors'] if b['source_id'] == sid]
            if sid == 'ias_model':
                selected = [(f['field'], f['field']) for f in facts['fields']] + [('model-001', 'base.reportItems')]
            for key, anchor in selected:
                hits = [n for n, line in enumerate(lines, 1) if anchor in line]
                locators[key] = {'lines':hits, 'verified':bool(hits), 'note':'人工摘要保留；原件锚点命中不等于运行验证'}
        result[sid] = {'source_sha256':sha(raw), 'locators':locators}
    put(path, result)
    return result

def build_catalog(manifest, paths, evidence):
    docs = {k:readj(paths[k]) for k in PLATFORM if PLATFORM[k].endswith('.json')}
    facts, selections = readj(OUT/'sources/ias_review_facts.json'), readj(OUT/'sources/filltb_selection.json')['selections']
    rules, relations, supplements = [], [], []
    def add(sid, ns, key, code, name, payload, locator='', **extra):
        source = manifest[sid]
        identity = [source['origin_system'], ns, sid, key]
        rid = ':'.join(quote(str(v), safe='') for v in identity)
        record = dict(rule_id=rid, origin_system=source['origin_system'], namespace=ns, native_key=key, identity_key=identity, original_code=code, original_name=name, source_id=sid, source_path=source['source_path'], source_sha256=source['source_sha256'], snapshot_path=source['snapshot_path'], snapshot_sha256=source['snapshot_sha256'], json_pointer=locator if locator.startswith('/') else '', symbol=locator if not locator.startswith('/') else '', record_locator=locator, payload=payload, payload_sha256=sha(payload), source_evidence='源码' if sid in ['identifier','formula'] or sid.startswith('ias_') else '静态表', mapping_state='未建立' if sid in PLATFORM else '候选', integration_state='平台已有' if sid in PLATFORM else '未实施', integration_evidence='本次磁盘静态定义；未查库或验证接线' if sid in PLATFORM else '未接入', applicable_standard='', scope='', template_variant='', report_type='', period_kind='未确认', amount_kind='未确认', direction='未确认', value_basis='未确认', missing_reason='', orphan_reason='', conflict_group_id='', candidate_reason='', lifecycle_status='审阅中', **{k:'' for k in ['reviewed_by','reviewed_at','decision','approved_content_hash']})
        record.update(extra)
        rules.append(record)
        return record
    chart = {a['code']:add('chart','standard_account',a['code'],a['code'],a['name'],a,f'/accounts/{i}', record_kind='标准科目', direction=a['direction']) for i,a in enumerate(docs['chart']['accounts'])}
    wp = {a['wp_code']:add('wp','workpaper_note',a['wp_code'],a['wp_code'],a['wp_name'],a,f'/mappings/{i}', record_kind='底稿映射', **{k:a.get(k) for k in ['account_codes','cycle','report_row','note_section','note_section_soe','note_section_listed']}) for i,a in enumerate(docs['wp']['mappings'])}
    reports = {}
    for i,b in enumerate(docs['reports']):
        dim = {k:b[k] for k in ['applicable_standard','scope','template_variant','report_type']}
        for j,row in enumerate(b['rows']):
            key = canonical([*dim.values(),row['row_code']])
            reports[(b['applicable_standard'],b['report_type'],row['row_code'])] = add('reports','report_line',key,row['row_code'],row['row_name'],row,f'/{i}/rows/{j}', record_kind='报表行', **dim)
    raw_aliases = ast.literal_eval(assignment(paths['identifier'],'_RAW_HEADER_ALIASES'))
    aliases = {field:add('identifier','import_alias',field,field,field,{'field':field,'aliases':values},'_RAW_HEADER_ALIASES['+repr(field)+']',record_kind='导入别名组',aliases=values,candidate_reason='静态备用别名；年初/期初净额均归 opening_balance；不是公式列词表') for field,values in raw_aliases.items()}
    columns = {alias:add('formula','tb_formula_column',alias,alias,target,{'alias':alias,'column':target},'COLUMN_ALIASES['+repr(alias)+']',record_kind='TB公式列',canonical_column=target) for alias,target in ast.literal_eval(assignment(paths['formula'],'COLUMN_ALIASES')).items()}
    for key, payload in docs['recognition'].items():
        for name,value in payload.items() if key == 'table_signatures' else [(key,payload)]:
            pointer = '/'+key+'/'+name if key == 'table_signatures' else '/'+key
            add('recognition','table_recognition',pointer,name,name,value,pointer,record_kind='表识别或配置')
    for i,row in enumerate(docs['push']['rules']):
        add('push','push_rule',row['rule_id'],row['rule_id'],row.get('description',''),row,f'/rules/{i}',record_kind='推送规则',source_kind=row['source']['kind'],target=row['target'],expression=row['source'].get('expression',row['source'].get('formula_text','')))
    def edge(source, target, kind, proof, target_code='', reason='', **extra):
        item = dict(source_rule_id=source['rule_id'] if source else '',target_rule_id=target['rule_id'] if target else '',evidence_rule_id=proof['rule_id'],relation_kind=kind,source_code=source['original_code'] if source else proof['original_code'],source_name=source['original_name'] if source else '',target_code=target_code or (target['original_code'] if target else ''),target_name=target['original_name'] if target else '',origin_system=proof['origin_system'],source_id=proof['source_id'],record_locator=proof['record_locator'],source_evidence=proof['source_evidence'],mapping_state='冲突' if proof['mapping_state']=='冲突' else '候选' if proof['origin_system']!='platform' else '未建立',integration_state=proof['integration_state'],conditions={},candidate_reason=reason or proof['candidate_reason'],orphan_reason='' if source and target else '源或目标未在本批材料中完整解析；不推造节点',conflict_group_id=proof['conflict_group_id'],**{k:proof[k] for k in ['applicable_standard','scope','template_variant','report_type','reviewed_by','reviewed_at','decision','approved_content_hash']})
        item.update(extra)
        item['relation_id'] = 'relation:'+sha([item[k] for k in ['source_rule_id','target_rule_id','evidence_rule_id','relation_kind','source_code','target_code','applicable_standard','scope','template_variant','report_type']])[:32]
        relations.append(item)
        return item
    for dim,items in docs['report_map']['mappings'].items():
        for i,row in enumerate(items):
            key = canonical([dim,row['standard_account_code'],row['report_type'],row['report_line_code']])
            proof = add('report_map','report_line',key,row['standard_account_code'],row['report_line_name'],row,f'/mappings/{dim}/{i}',record_kind='科目报表映射',applicable_standard=dim,scope=dim.split('_',1)[1],template_variant=dim.split('_',1)[0],report_type=row['report_type'])
            edge(chart.get(row['standard_account_code']),reports.get((dim,row['report_type'],row['report_line_code'])),'account_to_report',proof,row['report_line_code'],conditions={k:v for k,v in row.items() if k not in ['standard_account_code','report_line_code','report_line_name']})
    conflicts = [('platform-oci','其他综合收益：chart 3102 与底稿 M9→4003 异码','3102','M9','4005'),('platform-reserve','专项储备：底稿 M7→4301，但 chart 4301=研发支出，同码异义','4301','M7','4102'),('platform-surplus','盈余公积：chart 3101 与底稿 M5→4101 异码','3101','M5','4101')]
    for group,reason,code,wpcode,_ in conflicts:
        for record in [chart[code],wp[wpcode]]:
            record.update(mapping_state='冲突',conflict_group_id=group,candidate_reason=reason)
        edge(wp[wpcode],chart[code],'platform_conflict',wp[wpcode],reason=reason)
    for item in relations:
        affected = next((r for r in [chart.get(item['source_code']),wp.get(item['source_code'])] if r and r['mapping_state']=='冲突'),None)
        if affected:
            item.update(mapping_state='冲突',conflict_group_id=affected['conflict_group_id'],candidate_reason=affected['candidate_reason'])
    for record in wp.values():
        for code in record['payload'].get('account_codes',[]):
            edge(record,chart.get(code),'workpaper_to_account',record,code)
        for field in ['note_section','note_section_soe','note_section_listed']:
            if record['payload'].get(field):
                edge(record,None,'workpaper_to_note:'+field,record,record['payload'][field],conditions={'field':field,'scope':'原文件未声明单体或合并范围'},orphan_reason='仅有章节引用，未收录附注目标定义')
    for record in list(rules):
        if record['source_id'] == 'push':
            target = record['payload']['target']
            edge(record,wp.get(target.get('wp_code')),'push_target',record,canonical(target),conditions={'stage':record['payload']['stage'],'policy':record['payload']['policy'],'source_kind':record['source_kind'],'triggers':record['payload']['triggers']})
    for i,b in enumerate(facts['behaviors']):
        locator = b['symbol']+':'+canonical(evidence[b['source_id']]['locators'][b['key']])
        add(b['source_id'],'report_line',b['key'],'',b['title'],b,locator,record_kind='IAS行为',candidate_reason=b['summary'],mapping_state=b.get('mapping_state','候选'),conflict_group_id='ias-carry-delete' if b.get('mapping_state')=='冲突' else '')
    for f in facts['fields']:
        record = add('ias_model','report_line','field:'+f['field'],f['field'],f['name'],f,'base.reportItems/001:'+canonical(evidence['ias_model']['locators'][f['field']]),record_kind='IAS字段',period_kind=f['period'],amount_kind=f['amount_kind'],value_basis=f['basis'],direction='借方' if '借方' in f['amount_kind'] else '贷方' if '贷方' in f['amount_kind'] else '报表方向枚举' if f['field']=='FX' else '报表方向净额' if f['amount_kind'] in ['余额','净发生额'] else '不适用或随报表',candidate_reason=f['reason'])
        edge(record,aliases.get(f['candidate']) or columns.get(f['candidate']),'field_semantic_candidate',record,f['candidate'],missing_reason='' if f['candidate'] else '缺独立等价字段或部署模型；不填造候选')
    for name in ['CW_KMB实际科目数据','BB_ReportItemsRef完整关系','BB_ReportItemsSumRef完整关系','DataModel部署定义']:
        add('ias_ds' if name.startswith('DataModel') else 'ias_sql','standard_account' if name.startswith('CW_KMB') else 'report_line','missing:'+name,'',name,{'missing':name},'人工材料缺口登记',record_kind='IAS缺口',source_evidence='缺数据',missing_reason='未取得实际数据；保留已有源码行为证据，不以缺口代替零金额')
    fill_records = []
    for row in selections:
        sid,name,code,candidate,kind,reason = row
        locator = canonical({'original_key':[name,code],**evidence[sid]['locators'][canonical([name,code])]})
        group = next((g for g,_,_,_,c in conflicts if code==c and sid=='filltb_ah'),'') or ('filltb-1523-1524' if code in ['1523','1524'] else 'filltb-1001' if code=='1001' else '')
        record = add(sid,'import_alias' if sid=='filltb_f' else 'report_line',canonical([code,candidate]),code,name,row,locator,record_kind='FillTb列位' if sid=='filltb_f' else 'FillTb编码',candidate_reason=reason,mapping_state='冲突' if group else '候选',conflict_group_id=group)
        fill_records.append(record)
        candidates = ([aliases[candidate]] if candidate in aliases else []) if sid=='filltb_f' else [r for r in chart.values() if r['original_name']==candidate]
        if sid=='filltb_ah':
            candidates += [r for r in wp.values() if r['payload'].get('account_name')==candidate and r['payload'].get('is_primary')]
            candidates += [r for r in reports.values() if r['original_name']==candidate and r['report_type']==('cash_flow_statement' if kind=='现金流项目' else 'balance_sheet')]
            if code=='1001':
                candidates += [chart[c] for c in wp['E1']['payload']['account_codes'] if c in chart]
        for target in candidates or [None]:
            edge(record,target,'import_position_candidate' if sid=='filltb_f' else 'external_semantic_candidate',record,reason=reason,conditions={'external_standard':'未确认','external_scope':'未确认','platform_candidate_dimension':{k:target[k] for k in ['applicable_standard','scope','report_type']} if target else {}})
        if sid=='filltb_f':
            alias = aliases.get(candidate)
            record.update(period_kind='年度年初' if candidate=='year_opening_debit' else '本年累计' if candidate=='year_debit' else '本期期初' if candidate=='opening_debit' else '不适用',amount_kind='发生额' if candidate=='year_debit' else '余额' if 'opening' in candidate else '身份字段',direction='借方' if candidate.endswith('debit') else '不适用',value_basis='导入账面；未实测')
            if alias and name not in alias['aliases']:
                record['candidate_reason'] += ' 平台原始别名未包含该原文；仅字段语义候选，不表示现已识别。'
                relations[-1]['candidate_reason'] = record['candidate_reason']
    for call in assignment(paths['checks'],'SOURCES').elts:
        vals = {k:ast.literal_eval(v) for k,v in zip(['key','label','category','runs_in','edit_where'],call.args[:5])}
        vals.update(loader=ast.unparse(call.args[5]),source_id='checks',source_evidence='源码',mapping_state='未建立',integration_state='平台已有',record_locator='SOURCES:'+vals['key'])
        vals.update({kw.arg:ast.unparse(kw.value) if isinstance(kw.value,ast.Call) else ast.literal_eval(kw.value) for kw in call.keywords})
        supplements.append(vals)
    seeds = ast.literal_eval(assignment(paths['check_seeds'],'_CROSS_CHECK_SEEDS'))
    for row in seeds:
        row.update(source_id='check_seeds',source_evidence='源码',mapping_state='未建立',integration_state='平台已有',record_locator='_CROSS_CHECK_SEEDS:'+row['id'])
    absent = sorted({r['standard_account_code'] for rows in docs['report_map']['mappings'].values() for r in rows} - set(chart))
    proof_by_id = {r['rule_id']:r for r in rules}
    for e in relations:
        proof = proof_by_id[e['evidence_rule_id']]
        e.update({k:proof[k] for k in ['source_path','snapshot_path','source_sha256','snapshot_sha256','payload_sha256','period_kind','amount_kind','direction','value_basis']})
    counts = {'standard_accounts':len(chart),'report_dimensions':{k:len(v) for k,v in docs['report_map']['mappings'].items()},'report_rows':len(reports),'workpaper_mappings':len(wp),'push_rules':len(docs['push']['rules']),'push_kinds':dict(Counter(r['source']['kind'] for r in docs['push']['rules'])),'import_fields':len(aliases),'import_aliases':sum(map(len,raw_aliases.values())),'tb_formula_columns':len(columns),'ias_behaviors':len(facts['behaviors']),'ias_fields':len(facts['fields']),'filltb_codes':sum(r[0]=='filltb_ah' for r in selections),'filltb_positions':sum(r[0]=='filltb_f' for r in selections),'report_codes_absent_from_chart':absent,'report_code_gap_count':len(absent)}
    assert len(chart)==len(docs['chart']['accounts']) and len(wp)==len(docs['wp']['mappings']) and len(reports)==sum(len(b['rows']) for b in docs['reports']), '原生键重复，不得静默覆盖'
    return rules, relations, counts, supplements, seeds, docs

def finalize(rules, relations, previous):
    for key, rows in [('rules',rules),('relations',relations)]:
        field = 'rule_id' if key=='rules' else 'relation_id'
        older = {r[field]:r for r in previous.get(key,[])}
        assert len({r[field] for r in rows})==len(rows), '稳定ID重复：'+key
        for row in rows:
            row.setdefault('lifecycle_status','审阅中')
            row['content_sha256'] = sha(row)
            old = older.pop(row[field],{})
            row['created_at'] = old.get('created_at',DATE)
            row['updated_at'] = old.get('updated_at',DATE) if old.get('content_sha256')==row['content_sha256'] else datetime.now().date().isoformat() if old else DATE
        for old in older.values():
            retired = {**old,'lifecycle_status':'退役','orphan_reason':'本次来源不再包含该稳定身份；保留历史，不沿用批准','mapping_state':'未建立' if old['origin_system']=='platform' else '候选','decision':'','approved_content_hash':''}
            retired['content_sha256'] = sha({k:v for k,v in retired.items() if k not in ['content_sha256','created_at','updated_at']})
            retired['updated_at'] = old['updated_at'] if old.get('lifecycle_status')=='退役' else datetime.now().date().isoformat()
            rows.append(retired)
        rows.sort(key=lambda r:r[field])
    return {'schema_version':SCHEMA,'rules':rules,'relations':relations,'review_decisions':previous.get('review_decisions',[])}

def make_sheets(catalog, manifest, counts, registry, seeds):
    rules, edges = catalog['rules'], catalog['relations']
    by_source = lambda sid:[r for r in rules if r['source_id']==sid and r['lifecycle_status']!='退役']
    by_kind = lambda kind:[r for r in rules if r.get('record_kind')==kind and r['lifecycle_status']!='退役']
    summary = [{'metric':k,'count':v,'description':'本次磁盘静态材料；不代表项目运行生效'} for k,v in counts.items()]
    comparison = catalog['fusion_comparisons']
    reading = [
        {'项目':'交付定位','说明':'两本离线审阅工作簿，不是运行包；不自动导入、不改产品或数据库。'},
        {'项目':'建议阅读顺序','说明':'先看三方差异与融合，再看平台内部冲突、外部候选和各来源明细。'},
        {'项目':'快照日期与基线','说明':DATE+'；HEAD '+INITIAL_HEAD+'；本地静态材料，不承诺远端最新或部署有效。'},
        {'项目':'平台覆盖','说明':'所列平台源全量导出；完整范围见来源清单，不等于全仓全部规则。'},
        {'项目':'IAS覆盖','说明':'可读源码行为和模型字段；项目科目、完整报表关系与部署模型未取得，缺码保持空白。'},
        {'项目':'FillTbTool覆盖','说明':'仅20个关键编码及5条列位事实摘录，不是完整商业词库，未运行外部程序。'},
        {'项目':'三种状态','说明':'证据类型描述材料；映射状态描述审阅决定；接入状态描述已有定义或未实施，三者独立。'},
        {'项目':'候选不是批准','说明':'所有外部映射未确认，审批字段为空；相同数字或名称也不能自动执行。'},
        {'项目':'数量口径','说明':'规则条目、关系边与唯一编码分开计数；一对多和多对一均合法，不能把未解析边全当缺陷。'},
        {'项目':'原始值与公式','说明':'编码、原名、表达式均按文本保存；JSON载荷保留，不执行来源表达式。'},
        {'项目':'复核限制','说明':'外部持久摘要不是原源码快照；完整原文复核仍需对应hash原件。许可未确认，不推定可转换或分发。'}]
    behavior = [{'条目':r['topic'],'当前平台行为':r['platform_behavior'],'差异或风险':r['difference'],'拟融合方式':r['fusion_action'],'实施阶段':r['phase'],'source_refs':[s for s in r['source_refs'] if s in PLATFORM],'证据类型':'源码/静态配置只读复核','状态':'现状摘要；改进未实施'} for r in comparison if any(s in PLATFORM for s in r['source_refs'])]
    merged = ast.literal_eval(assignment(OUT/'sources/platform/identifier.py','_MERGED_HEADER_MAPPING'))
    merged_rows = [{'表头组':g,'子表头':sub,'目标字段':target,'说明':'_default为当前兜底，不代表未知子表头语义已被确认','source_id':'identifier','symbol':'_MERGED_HEADER_MAPPING['+repr(g)+']['+repr(sub)+']','source_evidence':'源码','mapping_state':'未建立','integration_state':'平台已有'} for g,values in merged.items() for sub,target in values.items()]
    conflicts = [r for r in rules if r['mapping_state']=='冲突']
    dictionary = [{'field':k,'meaning':LABELS.get(k,'原字段：'+k),'description': '；'.join(STATES[k]) if k in STATES else '原码/ID/路径/公式均为文本；空白表示未提供或不适用，详见载荷与缺口说明'} for k in sorted(set().union(*(r.keys() for r in [*rules,*edges,*manifest.values()]))) ]
    common = {'来源清单':list(manifest.values()),'字段字典':dictionary}
    rule_sheets = {'阅读说明':reading,'三方差异与融合':comparison,'平台取数行为':behavior,'多级表头映射':merged_rows,'审阅总览':summary,'平台导入别名':by_source('identifier'),'平台表识别':by_source('recognition'),'平台标准科目':by_source('chart'),'平台报表行':by_source('reports'),'平台科目报表映射':by_source('report_map'),'平台底稿附注':by_source('wp'),'平台推送规则':by_source('push'),'平台公式TB词表':by_source('formula'),'IAS可见规则':by_kind('IAS行为'),'IAS字段语义':by_kind('IAS字段'),'IAS材料缺口':by_kind('IAS缺口'),'FillTb精选编码':by_kind('FillTb编码'),'FillTb导入列位':by_kind('FillTb列位'),'差异融合与待确认':conflicts+[r for r in rules if r['missing_reason']],'平台内部冲突':[r for r in conflicts if r['origin_system']=='platform'],'校对来源登记':registry,'报表校对种子':seeds,**common}
    nsource, ntarget = Counter(e['source_rule_id'] for e in edges if e['source_rule_id']), Counter(e['target_rule_id'] for e in edges if e['target_rule_id'])
    cross_sheets = {'阅读说明':reading,'三方差异与融合':comparison,'差异融合总览':summary,'平台科目基线':by_source('chart'),**{name:[e for e in edges if e['relation_kind']=='account_to_report' and e['applicable_standard']==dim] for dim,name in DIMS.items()},'IAS候选与缺口':[e for e in edges if e['origin_system']=='ias']+by_kind('IAS缺口'),'FillTb关键候选':[e for e in edges if e['source_id']=='filltb_ah'],'FillTb导入列位':[e for e in edges if e['source_id']=='filltb_f'],'一对多关系':[e for e in edges if nsource[e['source_rule_id']]>1 or ntarget[e['target_rule_id']]>1],'冲突孤儿与待确认':[e for e in edges if e['mapping_state']=='冲突' or e['orphan_reason']],'平台内部冲突':[r for r in conflicts if r['origin_system']=='platform'],'标准码差集':[{'original_code':code,'source_id':'report_map','mapping_state':'未建立','integration_state':'平台已有','source_evidence':'静态表','orphan_reason':'report seed 使用但 chart 未登记；不是自动错误，不删除'} for code in counts['report_codes_absent_from_chart']],'底稿科目与附注关系':[e for e in edges if e['relation_kind'].startswith('workpaper_to_')],'推送目标关系':[e for e in edges if e['relation_kind']=='push_target'],'全部关系':edges,**common}
    return {'规则目录_审阅稿.xlsx':rule_sheets,'编码对照表_审阅稿.xlsx':cross_sheets}

def value(v):
    return canonical(v) if isinstance(v,(dict,list,tuple)) else v

def write_and_check(path, sheets):
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = '平台静态规则审阅'
    wb.properties.created = wb.properties.modified = datetime(2026,11,11)
    expected = {}
    preferred = ['original_code','original_name','source_code','source_name','target_code','target_name','origin_system','record_kind','candidate_reason','source_evidence','mapping_state','integration_state','applicable_standard','scope','template_variant','report_type']
    for name,rows in sheets.items():
        ws = wb.create_sheet(name)
        columns = sorted(set().union(*(r.keys() for r in rows)),key=lambda k:(preferred.index(k) if k in preferred else len(preferred),k)) if rows else ['description']
        if name == '三方差异与融合':
            columns = ['topic','platform_behavior','ias_behavior','filltb_behavior','difference','fusion_action','phase','source_refs']
        matrix = [[LABELS.get(k,k)+' / '+k if k in LABELS else k for k in columns]]+[[value(r.get(k)) for k in columns] for r in rows]
        expected[name] = [[None if v=='' else v for v in row] for row in matrix]
        alignment = Alignment(vertical='top',wrap_text=True)
        for row_number,row in enumerate(matrix,1):
            ws.append(row)
            for column_number,v in enumerate(row,1):
                c = ws.cell(row_number,column_number)
                if isinstance(v,str):
                    assert len(v)<=32767, 'Excel文本长度超限：'+name
                    c.data_type, c.number_format = 's','@'
                c.alignment = alignment
        for c in ws[1]:
            c.font, c.fill = Font(bold=True,color='FFFFFF'), PatternFill('solid',fgColor='234E70')
        technical = {'payload','target','identity_key','content_sha256','payload_sha256','source_sha256','snapshot_sha256','source_rule_id','target_rule_id','evidence_rule_id','rule_id','relation_id','native_key'}
        comparison_page = name == '三方差异与融合'
        for i,k in enumerate(columns,1):
            col = ws.column_dimensions[get_column_letter(i)]
            col.width = 48 if comparison_page and k != 'topic' else 60 if k in ['candidate_reason','record_locator','expression','description','说明'] else 24
            if k in technical and name not in ['来源清单','字段字典']:
                col.hidden = True
        header_font = Font(name='Microsoft YaHei',size=10,bold=True,color='FFFFFF')
        body_font = Font(name='Microsoft YaHei',size=10,color='222222')
        for row in ws:
            for c in row:
                c.font = header_font if c.row == 1 else body_font
                if c.row > 1 and c.row % 2 == 0:
                    c.fill = PatternFill('solid',fgColor='F2F5F8')
                if c.value == '冲突':
                    c.font = Font(name='Microsoft YaHei',size=10,bold=True,color='C00000')
                    c.fill = PatternFill('solid',fgColor='FCE4D6')
                elif c.value in ['候选','缺数据','未实施']:
                    c.fill = PatternFill('solid',fgColor='FFF2CC')
        if comparison_page:
            for i in range(2,len(rows)+2):
                ws.row_dimensions[i].height = 112
        elif name == '阅读说明':
            ws.column_dimensions['B'].width = 100
            for i in range(2,len(rows)+2):
                ws.row_dimensions[i].height = 42
        ws.sheet_view.showGridLines = False
        ws.freeze_panes,ws.auto_filter.ref,ws.sheet_view.zoomScale = 'B2' if comparison_page else 'C2',ws.dimensions,85
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.paperSize = ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth,ws.page_setup.fitToHeight = 1,0
        ws.print_title_rows = '1:1'
        ws.row_dimensions[1].height = 38
    buffer = io.BytesIO()
    wb.save(buffer)
    stable = io.BytesIO()
    with zipfile.ZipFile(buffer) as zin, zipfile.ZipFile(stable,'w',zipfile.ZIP_DEFLATED) as zout:
        for name in sorted(zin.namelist()):
            data = zin.read(name)
            if name=='docProps/core.xml':
                data = re.sub(rb'(<dcterms:modified[^>]*>).*?(</dcterms:modified>)',rb'\g<1>2026-11-11T00:00:00Z\2',data)
            info = zipfile.ZipInfo(name,(2026,11,11,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info,data)
    put(path,stable.getvalue())
    actual = load_workbook(path,data_only=False,read_only=True)
    assert actual.sheetnames==list(sheets), '工作表丢失'
    for ws in actual:
        cells = list(ws.iter_rows())
        assert [[c.value for c in row] for row in cells]==expected[ws.title], '逐格读回不一致：'+ws.title
        assert all(c.data_type!='f' for row in cells for c in row), '来源表达式误写为Excel公式'
        assert all(c.data_type=='s' and c.number_format=='@' for row in cells for c in row if isinstance(c.value,str)), '文本类型丢失'
    actual.close()
    return {'sha256':sha(path.read_bytes()),'worksheets':{name:len(rows) for name,rows in sheets.items()},'sheet_count':len(sheets),'readback':'逐表逐格一致；编码文本；无公式执行'}

def main():
    assert sys.argv[1:] in [[],['--replay']], '用法：python generate_review.py [--replay]'
    replay = '--replay' in sys.argv
    manifest, paths = collect_sources(replay)
    evidence = external_evidence(manifest,replay)
    previous = readj(OUT/'catalog.json') if (OUT/'catalog.json').exists() else {}
    rules,edges,counts,registry,seeds,docs = build_catalog(manifest,paths,evidence)
    catalog = finalize(rules,edges,previous)
    comparison = readj(OUT/'sources/fusion_review.json')['comparisons']
    assert len(comparison) >= 12 and all(set(r['source_refs']) <= set(manifest) for r in comparison)
    catalog.update(fusion_comparisons=comparison)
    catalog.update(counts=counts,source_refs=list(manifest.values()),supplements={'check_registry':registry,'check_seeds':seeds})
    catalog['catalog_version'] = sha(catalog)
    ids = {r['rule_id'] for r in rules}
    assert len(ids)==len(rules) and len({e['relation_id'] for e in edges})==len(edges)
    for r in rules+edges:
        assert r['source_id'] in manifest and r['record_locator'], '来源或定位缺失'
        for k,allowed in STATES.items():
            assert r[k] in allowed, '非法状态：'+k
        assert r['mapping_state']!='已确认' and not r['reviewed_by'] and not r['approved_content_hash'], '本轮没有人工批准'
        if r['origin_system']!='platform':
            assert r['integration_state']=='未实施' and r['mapping_state'] in ['候选','冲突'], '外部状态越级'
    for e in edges:
        assert e['evidence_rule_id'] in ids and all(not e[k] or e[k] in ids for k in ['source_rule_id','target_rule_id']), '关系端点悬空'
        assert e['source_rule_id'] and e['target_rule_id'] or e['orphan_reason'], '未解析必须说明'
    for r in rules:
        assert r['payload_sha256']==sha(r['payload']), '载荷摘要不符'
        assert r['content_sha256']==sha({k:v for k,v in r.items() if k not in ['content_sha256','created_at','updated_at']}), '条目内容摘要不符'
        if r['json_pointer'] and r['lifecycle_status']!='退役':
            current = docs[r['source_id']]
            for part in r['json_pointer'].lstrip('/').split('/'):
                current = current[int(part)] if isinstance(current,list) else current[part.replace('~1','/').replace('~0','~')]
            assert current==r['payload'], 'JSON Pointer不能回读原载荷'
    assert counts['ias_behaviors']==18 and counts['ias_fields']==20 and counts['filltb_codes']==20 and counts['filltb_positions']==5, '人工选择范围变化'
    groups = {r['conflict_group_id'] for r in rules if r['mapping_state']=='冲突'}
    assert {'platform-oci','platform-reserve','platform-surplus','filltb-1523-1524','filltb-1001'}<=groups
    assert all(sha((OUT/s['snapshot_path']).read_bytes())==s['snapshot_sha256'] for s in manifest.values())
    # 合成前导零仅在内存检查，不混入真实编码目录。
    synthetic = Workbook(); synthetic.active.append(['001-A','=1+1'])
    for c in synthetic.active[1]:
        c.data_type,c.number_format='s','@'
    b=io.BytesIO(); synthetic.save(b); b.seek(0)
    test=load_workbook(b,data_only=False)
    assert test.active['A1'].value=='001-A' and test.active['B1'].data_type=='s'
    sheets = make_sheets(catalog,manifest,counts,registry,seeds)
    assert [len(s) for s in sheets.values()][0]>=16 and [len(s) for s in sheets.values()][1]>=15
    put(OUT/'catalog.json',catalog)
    outputs={name:write_and_check(OUT/name,tables) for name,tables in sheets.items()}
    for name,tables in sheets.items():
        before=(OUT/name).stat().st_mtime_ns
        repeat=write_and_check(OUT/name,tables)
        assert repeat==outputs[name] and before==(OUT/name).stat().st_mtime_ns, '重复生成改写了二进制'
    source_manifest={'schema_version':SCHEMA,'catalog_version':catalog['catalog_version'],'sources':list(manifest.values()),'evidence_index':{'path':'sources/external_evidence.json','sha256':sha((OUT/'sources/external_evidence.json').read_bytes())},'comparison_evidence':{'path':'sources/fusion_review.json','sha256':sha((OUT/'sources/fusion_review.json').read_bytes())},'scope':'所列6份平台JSON全量快照、2份词表及多级表头AST全量、2份校对登记补充、平台导入行为与三方差异摘要；非全仓规则普查','limitations':['外部原件可移除；人工摘要和定位摘要必须保留','IAS摘要不是原SQL；外部完整事实复核仍需同hash原件','FillTb仅25条精选，不复制完整词库','未查询数据库，未启动平台，未执行SQL，未取得运行接入或外部转换授权']}
    put(OUT/'source_manifest.json',source_manifest)
    report={'status':'passed','schema_version':SCHEMA,'catalog_version':catalog['catalog_version'],'counts':counts,'rules':len(rules),'relations':len(edges),'outputs':outputs,'checks':{'unique_ids':True,'source_and_payload_sha256':True,'json_pointer_roundtrip':True,'relation_endpoints_or_explicit_missing':True,'external_candidates_unconfirmed':True,'conflicts_retained':True,'text_and_formula_readback':True,'synthetic_leading_zero':True,'repeat_binary_sha256_unchanged':True,'repeat_mtime_unchanged':True},'limitations':source_manifest['limitations']}
    verified = OUT/'independent_validation.json'
    if verified.exists():
        extra = readj(verified)
        if extra.get('generator_sha256')==sha(Path(__file__).read_bytes()) and extra.get('catalog_version')==catalog['catalog_version'] and extra.get('output_hashes')=={k:v['sha256'] for k,v in outputs.items()}:
            report['independent_checks'] = extra['checks']
    put(OUT/'validation_report.json',report)
    readme=['# IAS / FillTb 离线审阅交付','',f"目录版本：`{catalog['catalog_version']}`。平台源码静态快照，不是项目有效规则或运行包。",'', '## 重生成','```powershell','python docs/reviews/ias-filltb-fusion/generate_review.py','python docs/reviews/ias-filltb-fusion/generate_review.py --replay','python docs/reviews/ias-filltb-fusion/verify_delivery.py','```','普通模式重读本地来源；--replay 只用平台快照、人工摘要与定位摘要。人工摘要未经改写。原件消失后不再证明原文，保留原文件hash与当时的核验定位。', '同内容比较实际二进制后跳过写入；丢失或被改的输出必重建。ZIP时间与工作簿属性固定以保证可重现，不是来源修改时间。每次逐格读回并连跑两次核对hash和mtime。','','## 边界与数量','所列平台JSON完整保存于 sources/platform；catalog.json 保留原payload、source hash、payload hash、稳定ID和逐边关系。IAS 18条行为、20字段；FillTb 20个码+5列位。字段/码与公式按文本，不执行表达式。', '四口径各自计边，不等于报表行数；一对多页可能同时包含多对一，边数不等于唯一科目数。未知外部准则不广播为平台四套已适用。平台已有不等于映射正确或已部署。', '缺口编码为空；1523/1524都保留；其他综合3102↔M9的4003、专项储备M7的4301↔chart研发支出、盈余3101↔M5的4101均明示冲突。', '审批字段为空，所有外部候选未确认；未查库、未运行外部SQL、未读取凭据、未改spec/INDEX。许可尚未核实；本轮仅保留最小必要事实供人工审阅，不推定取得转换或分发授权；导入及运行接入均未实施。', 'IAS行为属于报告取数/配对语义，使用report_line命名空间并以record_kind区分；科目码缺失绝不由报表字段Code推造。校对来源登记仅静态读取12项登记与内置7条种子，不调用加载器、不伪称数据库规则全量。', '', '## 本次现算','```json',json.dumps(counts,ensure_ascii=False,indent=2),'```','','## 工作表与计数']
    for name,tables in sheets.items():
        readme += ['',f'### {name}（{len(tables)}页）','| 工作表 | 数据行数 |','| --- | ---: |']+[f'| {sheet} | {len(rows)} |' for sheet,rows in tables.items()]
    readme += ['','字段字典说明三维状态；来源清单逐项说明hash、路径、commit与许可。原JSON Pointer可随排序改变，稳定ID不含数组位置；来源删除保留退役记录，不自动沿用审批。','人工审批尚未发生；本工具不提供批准或发布入口。','']
    put(OUT/'README.md','\n'.join(readme).encode('utf-8'))
    print(json.dumps({'status':'passed','outputs':outputs,'counts':counts,'rules':len(rules),'relations':len(edges)},ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
