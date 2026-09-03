# -*- coding: utf-8 -*-
"""全量合并 Codex 侧《上海70行业_逐项支持链接》CSV（69行业1235行）到主库。
规则（对比去重 + 择优）：
  R1 缺格创建：主库无该(code,dim,ind)格且CSV有带链接证据 → 新建格
  R2 miss转正：主库格miss=true但CSV有带链接证据 → 填充转正
  R3 择新替换：CSV证据年份严格更新且非"缺沪"占位、且为沪口径（或旧证据亦非沪口径）→ 替换，旧证据入hist
  R4 hist补充：其余CSV证据若文本未重复 → 追加到hist留档
  状态映射：「上海细分未直接披露/全国或代理」→ ev追加全国口径标记（评分中性化）+national标记
之后重算 filled/missing/core_filled。合并前备份主库。
"""
import json, csv, re, shutil
from collections import Counter, defaultdict

MAIN = '/Users/yihanran/WorkBuddy/2026-09-02-15-38-53/outputs/上海70行业指标证据_数据_2026-09-02.json'
CSVF = '/Users/yihanran/Documents/Codex/2026-09-02/75-75-37-37-url-mmm/outputs/上海70行业_逐项支持链接_2026-09-02.csv'
BAK  = '/tmp/refresh2026/master_bak_pre_fullmerge.json'

shutil.copy(MAIN, BAK)
main = json.load(open(MAIN, encoding='utf-8'))
main_idx = {r['code']: r for r in main}
main_map = {}
for r in main:
    for c in r['cells']:
        main_map[(r['code'], c['dim'], c['ind'])] = c

STD = {
 '需求': ['市场需求增长','出口增长','下游行业景气度','渗透率提升空间','客户预算增长','出厂价格'],
 '供给': ['工业增加值','供给瓶颈','行业集中度','产能利用率'],
 '盈利': ['龙头企业收入增长','利润率改善','ROE/ROIC'],
 '资本': ['行业投资增长','融资活动增长'],
 '技术': ['技术突破','商业化成熟度'],
 '政策': ['政策提及数','政府补贴','国家战略支持'],
}
CORE19 = [i for d, l in [('需求', ['市场需求增长','出口增长','下游行业景气度','渗透率提升空间','客户预算增长']),
                         ('供给', ['工业增加值','供给瓶颈','行业集中度','产能利用率']),
                         ('盈利', ['龙头企业收入增长','利润率改善','ROE/ROIC']),
                         ('资本', ['行业投资增长','融资活动增长']),
                         ('技术', ['技术突破','商业化成熟度']),
                         ('政策', ['政策提及数','政府补贴','国家战略支持'])] for i in l]
ALIAS = {
 '行业协会与活动':'行业协会与标准','产业产值':'工业增加值','供给-产量':'工业增加值',
 '供给-发电量':'工业增加值','供给-结构':'工业增加值','价格环境温和':'出厂价格',
 '资产质量（ROE替代项）':'ROE/ROIC','技术里程碑':'技术突破','AI制药突破':'技术突破',
 '大模型备案':'技术突破','创新药械获批':'商业化成熟度','PMI行业景气':'下游行业景气度',
 '上海石化2026H1业绩预告':'龙头企业收入增长','龙头出口与智造':'龙头企业收入增长',
 'C919国际化':'出口增长',
}
TO_SUPP = ['上海化工区项目','产业载体动态','全国对比基准','外资扩产动态','新动能亮点','产品结构升级']
IND2DIM = {i: d for d, l in STD.items() for i in l}
# 主库已有的补充维度指标名（全局集合），允许正常合并
SUPP_INDS = {c['ind'] for r in main for c in r['cells'] if c['dim'] == '补充'}
SH, PROXY, VAGUE = '有上海口径或上海主体证据', '上海细分未直接披露/全国或代理', '未明确上海口径'
TIER_RANK = {'S1': 0, 'S2': 1, 'S3': 2, 'S4': 3, '': 4}

def yr(y):
    m = re.search(r'(20\d\d)', y or '')
    return int(m.group(1)) if m else 0

def tier_map(t):
    t = (t or '').strip().split('/')[0].strip()
    return t.replace('T', 'S') if t.startswith('T') else (t if t.startswith('S') else '')

def norm_year(y):
    return (y or '').split('；')[0].strip()

def is_absence(ev):
    e = (ev or '').strip()
    return e.startswith('缺沪') or e.startswith('缺数据') or '缺沪细分数据' in e[:25]

def mark_proxy(ev, status):
    if status == PROXY and '全国口径' not in ev:
        return ev.rstrip('。；;') + '（全国口径/代理数据，不计入沪上评分）', True
    return ev, status == PROXY

# ---- 解析CSV ----
rows = list(csv.reader(open(CSVF, encoding='utf-8-sig')))[1:]
groups = defaultdict(list)
stats = Counter()
for r in rows:
    if len(r) < 12: continue
    rank, code, name, score, dim, ind_raw, status, year, tier, ev_full, nurl, urls = r[:12]
    code, dim, ind_raw, status = code.strip(), dim.strip(), ind_raw.strip(), status.strip()
    urls = [u.strip() for u in urls.split('；') if u.strip()]
    ev = ev_full.split('｜')[0].strip()
    if not urls:
        stats['跳过_无链接'] += 1; continue
    if not ev or is_absence(ev):
        stats['跳过_缺沪占位或空'] += 1; continue
    ind = ALIAS.get(ind_raw, ind_raw)
    if ind_raw in TO_SUPP:
        dim, ind = '补充', ind_raw
    elif ind in IND2DIM:
        dim = IND2DIM[ind]
    elif dim == '补充' and ind in SUPP_INDS:
        pass  # 主库已有补充指标，正常走合并
    else:
        stats['跳过_无法映射_%s/%s' % (dim, ind_raw)] += 1; continue
    if code not in main_idx:
        stats['跳过_主库无行业_' + code] += 1; continue
    groups[(code, dim, ind)].append({'ev': ev, 'year': year, 'tier': tier,
                                     'urls': urls, 'status': status})

def pick_best(rlist):
    """优先沪口径，其次年份新，其次tier优。"""
    return sorted(rlist, key=lambda x: (x['status'] != SH, -yr(x['year']),
                                        TIER_RANK.get(tier_map(x['tier']), 4)))[0]

report = {'created': [], 'unmissed': [], 'replaced': [], 'hist_added': 0, 'dup_skipped': 0}

for (code, dim, ind), rlist in groups.items():
    iobj = main_idx[code]
    cell = main_map.get((code, dim, ind))
    best = pick_best(rlist)
    others = [x for x in rlist if x is not best]

    def hist_add(c, items):
        added = 0
        hist = c.setdefault('hist', [])
        seen = {h['ev'][:40] for h in hist} | {c.get('ev', '')[:40]}
        for it in items:
            if it['ev'][:40] in seen:
                report['dup_skipped'] += 1; continue
            hist.append({'ev': it['ev'], 'year': norm_year(it['year']),
                         'tier': tier_map(it['tier']), 'urls': it['urls']})
            seen.add(it['ev'][:40]); added += 1
        return added

    if cell is None:
        ev, nat = mark_proxy(best['ev'], best['status'])
        ncell = {'dim': dim, 'ind': ind, 'ev': ev, 'year': norm_year(best['year']),
                 'tier': tier_map(best['tier']), 'urls': best['urls'], 'miss': False}
        if nat: ncell['national'] = True
        iobj['cells'].append(ncell)
        main_map[(code, dim, ind)] = ncell
        report['created'].append((code, iobj['name'], dim, ind, ncell['year'], ncell['tier']))
        report['hist_added'] += hist_add(ncell, others)
        stats['R1缺格创建'] += 1
    elif cell.get('miss'):
        ev, nat = mark_proxy(best['ev'], best['status'])
        old_ev = cell.get('ev', '')
        cell.update(ev=ev, year=norm_year(best['year']), tier=tier_map(best['tier']),
                    urls=best['urls'], miss=False)
        if nat: cell['national'] = True
        else: cell.pop('national', None)
        if old_ev and not is_absence(old_ev):
            cell.setdefault('hist', []).insert(0, {'ev': old_ev, 'year': cell.get('year','') or '', 'tier': '', 'urls': []})
        report['unmissed'].append((code, iobj['name'], dim, ind, cell['year'], cell['tier']))
        report['hist_added'] += hist_add(cell, others)
        stats['R2_miss转正'] += 1
    else:
        cy, ry = yr(cell.get('year') or ''), yr(best['year'])
        old_is_proxy = '全国口径' in (cell.get('ev') or '')
        replaceable = (ry > cy) and best['status'] == SH or (ry > cy and old_is_proxy and best['status'] != VAGUE)
        if replaceable:
            old = {'ev': cell.get('ev', ''), 'year': cell.get('year', ''),
                   'tier': cell.get('tier', ''), 'urls': cell.get('urls') or []}
            ev, nat = mark_proxy(best['ev'], best['status'])
            cell.update(ev=ev, year=norm_year(best['year']), tier=tier_map(best['tier']),
                        urls=best['urls'])
            if nat: cell['national'] = True
            else: cell.pop('national', None)
            cell.setdefault('hist', []).insert(0, old)
            report['replaced'].append((code, iobj['name'], dim, ind, old['year'], '→', cell['year'], cell['tier']))
            report['hist_added'] += hist_add(cell, others)
            stats['R3择新替换'] += 1
        else:
            report['hist_added'] += hist_add(cell, rlist)
            stats['R4_hist补充'] += 1

# ---- 重算覆盖字段 ----
for r in main:
    cells = r['cells']
    nm = sum(1 for c in cells if c.get('miss'))
    r['missing'] = nm
    r['filled'] = len(cells) - nm
    r['core_filled'] = sum(1 for c in cells if not c.get('miss') and c['ind'] in CORE19)

json.dump(main, open(MAIN, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

print('==== 合并报告 ====')
print('R1 缺格创建:', len(report['created']))
for x in report['created']: print('  +', x)
print('R2 miss转正:', len(report['unmissed']))
for x in report['unmissed']: print('  *', x)
print('R3 择新替换:', len(report['replaced']))
for x in report['replaced']: print('  ↻', x)
print('R4 hist补充格数:', stats['R4_hist补充'], '| hist新增条目:', report['hist_added'], '| 文本重复跳过:', report['dup_skipped'])
print('其余:', {k: v for k, v in stats.items()})
print('备份:', BAK)
