# -*- coding: utf-8 -*-
"""按《行业评分体系》21 项指标分档表对 70 行业证据库打分。
每个指标按用户标准的"情况→得分"分档：增速类按 >30/10-30/0-10/<0% 分档，
定性类按关键词分档，查不到按标准默认分。输出 rec["v21"]。"""
import json, shutil, re

MAIN = "/tmp/evidence_recs.json"
shutil.copy(MAIN, "/tmp/evidence_recs_bak_v21band.json")

PCT = re.compile(r'([+-]?\d+(?:\.\d+)?)\s*%')
PCTP = re.compile(r'([+-]?\d+(?:\.\d+)?)\s*(?:个百分点|pct)', re.I)
NEG_CTX = re.compile(r'下降|下滑|减少|收窄|跌|亏损|收缩|负|降')

def valid_texts(cells):
    out = []
    for c in cells:
        ev = c.get("ev") or ""
        if c.get("miss") or not ev:
            continue
        if ev.startswith(("缺沪", "缺数据", "无沪", "暂无", "NA", "待统一")):
            continue
        out.append(ev)
    return out

def growth_vals(texts):
    res = []
    for t in texts:
        for m in PCT.finditer(t):
            v = float(m.group(1))
            ctx = t[max(0, m.start() - 8):m.start()]
            if v > 0 and NEG_CTX.search(ctx):
                v = -v
            res.append(v)
    return res

def has(t, *kws):
    return any(k in t for k in kws)

def growth_band(texts, bands, dft, low):
    """bands: [(阈值, 分), ...] 降序；查不到→dft；全负→low。"""
    vals = growth_vals(texts)
    if not vals:
        return dft, f"查不到（默认{dft}分）"
    mx = max(vals)
    for th, sc in bands:
        if mx >= th:
            return sc, f"增速峰值 {mx:+.1f}% → {sc}分档"
    return low, f"增速 {mx:+.1f}%（下滑）→ {low}分"

# (类别, 指标名, 满分, 取数[(dim,ind)], 类型, 参数)
INDS = [
    ("需求", "FAI增长", 4, [("资本", "行业投资增长")], "g", ([(30, 4), (10, 3), (0, 2)], 2, 1)),
    ("需求", "规上企业增长", 3, [("补充", "企业注册热度")], "g", ([(30, 3), (10, 2), (0, 1.5)], 1.5, 0.5)),
    ("需求", "出口增长", 3, [("需求", "出口增长")], "g", ([(30, 3), (10, 2), (0, 1.5)], 1.5, 0.5)),
    ("需求", "下游行业景气度", 4, [("需求", "下游行业景气度")], "g", ([(30, 4), (10, 3), (0, 2)], 2, 1)),
    ("需求", "渗透率提升空间", 3, [("需求", "渗透率提升空间")], "pen", None),
    ("需求", "龙头预算增长", 3, [("需求", "客户预算增长")], "g", ([(30, 3), (10, 2), (0, 1.5)], 1.5, 0.5)),
    ("资本", "行业投资增长", 5, [("资本", "行业投资增长")], "g", ([(30, 5), (10, 4), (0, 3)], 3, 1)),
    ("资本", "融资活动增长", 5, [("资本", "融资活动增长"), ("补充", "VC·PE与并购")], "g", ([(30, 5), (10, 4), (0, 3)], 3, 1)),
    ("供给", "工业增加值", 5, [("供给", "工业增加值")], "g", ([(30, 5), (10, 4), (0, 3)], 3, 1)),
    ("供给", "供给瓶颈", 5, [("供给", "供给瓶颈")], "neck", None),
    ("供给", "行业集中度", 5, [("供给", "行业集中度")], "cr5", None),
    ("供给", "产能利用率", 5, [("供给", "产能利用率")], "util", None),
    ("技术", "技术突破", 7, [("技术", "技术突破")], "tech", None),
    ("技术", "商业化成熟度", 7, [("技术", "商业化成熟度")], "comm", None),
    ("技术", "招聘人数增长", 6, [("补充", "招聘岗位增速")], "g", ([(30, 6), (10, 5), (0, 3)], 3, 1)),
    ("盈利", "龙头企业收入增长", 7, [("盈利", "龙头企业收入增长")], "g", ([(30, 7), (10, 5), (0, 3)], 3, 1)),
    ("盈利", "龙头企业利润率改善", 7, [("盈利", "利润率改善")], "margin", None),
    ("盈利", "龙头企业ROE/ROIC", 6, [("盈利", "ROE/ROIC")], "roe", None),
    ("政策", "政策提及数", 4, [("政策", "政策提及数")], "pol", None),
    ("政策", "政府补贴", 3, [("政策", "政府补贴")], "sub", None),
    ("政策", "国家战略支持", 3, [("政策", "国家战略支持")], "sub", None),
]
CAT_W = {"需求": 20, "资本": 10, "供给": 20, "技术": 20, "盈利": 20, "政策": 10}

def score_pen(texts):
    t = " ".join(texts)
    m = re.search(r'渗透率[^0-9]{0,8}(\d+(?:\.\d+)?)\s*%', t)
    if m:
        v = float(m.group(1))
        if v < 20: return 3, f"渗透率{v:.0f}%（<20%，空间巨大）→ 3分"
        if v < 50: return 2, f"渗透率{v:.0f}%（20-50%，较大空间）→ 2分"
        if v <= 80: return 1.5, f"渗透率{v:.0f}%（50-80%，空间有限）→ 1.5分"
        return 0.5, f"渗透率{v:.0f}%（>80%，基本饱和）→ 0.5分"
    if has(t, "空间巨大", "空间广阔", "蓝海"): return 3, "提升空间巨大 → 3分"
    if has(t, "提升空间", "仍有空间", "空间"): return 2, "有较大提升空间 → 2分"
    if has(t, "空间有限"): return 1.5, "提升空间有限 → 1.5分"
    if has(t, "饱和"): return 0.5, "基本饱和 → 0.5分"
    return 1.5, "渗透率数据查不到（默认1.5分）"

def score_neck(texts):
    t = " ".join(texts)
    if not texts: return 3, "查不到（默认3分）"
    if has(t, "无瓶颈", "供给过剩", "产能过剩", "过剩"): return 1, "供给过剩/无瓶颈 → 1分"
    if has(t, "严重紧缺", "缺口大", "供不应求", "严重短缺"): return 5, "供给严重紧缺 → 5分"
    if has(t, "紧缺", "偏紧", "瓶颈", "约束", "紧张"): return 4, "局部环节供给约束 → 4分"
    if has(t, "平衡", "稳定"): return 3, "供需基本平衡 → 3分"
    return 3, "供需基本平衡（默认）→ 3分"

def score_cr5(texts):
    t = " ".join(texts)
    m = re.search(r'CR\s*5[^0-9]{0,4}(\d+(?:\.\d+)?)\s*%', t)
    if not m:
        m = re.search(r'CR\s*10[^0-9]{0,4}(\d+(?:\.\d+)?)\s*%', t)
    if m:
        v = float(m.group(1))
        if v > 60: return 5, f"CR5 {v:.0f}%（高度集中）→ 5分"
        if v >= 40: return 4, f"CR5 {v:.0f}%（集中度较高）→ 4分"
        if v >= 20: return 3, f"CR5 {v:.0f}%（适度集中）→ 3分"
        return 1, f"CR5 {v:.0f}%（高度分散）→ 1分"
    if has(t, "高度集中", "寡头", "垄断", "一家独大"): return 5, "高度集中 → 5分"
    if has(t, "分散", "内卷"): return 1, "高度分散内卷 → 1分"
    if has(t, "集中", "头部", "龙头集聚"): return 4, "集中度较高 → 4分"
    return 3, "集中度数据查不到（默认3分）"

def score_util(texts):
    t = " ".join(texts)
    m = re.search(r'利用率[为达约]?\s*(\d+(?:\.\d+)?)\s*%', t)
    if m:
        v = float(m.group(1))
        if v > 85: return 5, f"产能利用率{v:.0f}%（紧张）→ 5分"
        if v >= 70: return 4, f"产能利用率{v:.0f}%（健康区间）→ 4分"
        if v >= 55: return 3, f"产能利用率{v:.0f}%（一般）→ 3分"
        return 1, f"产能利用率{v:.0f}%（过剩）→ 1分"
    if has(t, "满产", "紧张", "供不应求"): return 5, "产能紧张 → 5分"
    if has(t, "过剩"): return 1, "产能过剩 → 1分"
    return 3, "查不到（默认3分）"

def score_tech(texts):
    t = " ".join(texts)
    if not texts: return 3, "技术进展信息查不到（默认3分）"
    if has(t, "重大突破", "国家级", "首台", "全球首", "全国首", "攻克", "打破垄断", "国产替代"):
        return 7, "核心技术重大突破 → 7分"
    if has(t, "落地", "迭代", "突破", "量产", "获批", "上市"): return 5, "关键技术迭代落地 → 5分"
    if has(t, "改良", "缓慢"): return 3, "小幅技术改良 → 3分"
    if has(t, "停滞"): return 1, "技术停滞 → 1分"
    return 3, "有技术进展 → 3分"

def score_comm(texts):
    t = " ".join(texts)
    if not texts: return 3, "商业化进度查不到（默认3分）"
    if has(t, "实验室", "概念阶段", "无法商业化"): return 1, "停留实验室/概念 → 1分"
    if has(t, "规模化", "大规模", "量产", "放量", "盈利闭环", "商业化落地"): return 7, "大规模商业化落地 → 7分"
    if has(t, "推广", "商业化", "订单"): return 5, "小批量商业化推广 → 5分"
    if has(t, "试点", "示范"): return 3, "试点示范阶段 → 3分"
    return 3, "商业化推进中 → 3分"

def score_margin(texts):
    t = " ".join(texts)
    pcts = [float(x) for x in PCTP.findall(t)]
    if pcts:
        mx = max(pcts)
        if mx > 5: return 7, f"利润率提升{mx:.1f}pct → 7分"
        if mx >= 1: return 5, f"利润率提升{mx:.1f}pct → 5分"
        return 3, f"利润率波动{mx:.1f}pct → 3分"
    if not texts: return 3, "利润率数据查不到（默认3分）"
    if has(t, "下滑", "下降", "恶化", "亏损扩大", "收窄"): return 1, "利润率明显下滑 → 1分"
    if has(t, "扭亏", "减亏", "改善", "提升", "增长"): return 5, "利润率改善 → 5分"
    return 3, "利润率基本持平 → 3分"

def score_roe(texts):
    t = " ".join(texts)
    m = re.search(r'ROE[^0-9\-]{0,6}(\-?\d+(?:\.\d+)?)\s*%', t)
    if not m:
        m = re.search(r'(\-?\d+(?:\.\d+)?)\s*%', t)
    if m:
        v = float(m.group(1))
        if v > 15: return 6, f"ROE {v:.1f}%（回报优秀）→ 6分"
        if v >= 8: return 5, f"ROE {v:.1f}%（回报良好）→ 5分"
        if v >= 0: return 3, f"ROE {v:.1f}%（回报一般）→ 3分"
        return 1, f"ROE {v:.1f}%（亏损）→ 1分"
    return 3, "查不到（默认3分）"

def score_pol(texts, cells_valid):
    t = " ".join(texts)
    if not texts: return 1.5, "政策数量查不到（默认1.5分）"
    if has(t, "几乎无", "无相关"): return 1, "几乎无相关扶持政策 → 1分"
    if has(t, "国家级", "国家战略", "高频", "密集", "国家层面", "重大专项"):
        return 4, "国家级/省级高频发文、政策密集 → 4分"
    if len(texts) >= 2 or has(t, "多份", "系列", "若干", "多项", "连续"):
        return 2, "有多份相关扶持政策 → 2分"
    return 1.5, "少量地方层面政策提及 → 1.5分"

def score_sub(texts):
    t = " ".join(texts)
    if not texts: return 1.5, "补贴数据查不到（默认1.5分）"
    if has(t, "退坡", "缩减", "减少"): return 1, "补贴退坡/缩减 → 1分"
    if has(t, "大幅增长", "加码", "大幅增长", "亿元", "重大专项", "国家战略"):
        return 3, "补贴规模大幅增长/国家级支持 → 3分"
    if has(t, "稳定", "持续", "补贴", "支持"): return 2, "补贴稳定、力度尚可 → 2分"
    return 1.5, "补贴较少、零星项目 → 1.5分"

def score_industry(r):
    by = {}
    for c in r.get("cells", []):
        by.setdefault((c.get("dim"), c.get("ind")), []).append(c)
    items = []
    for cat, name, mx, srcs, kind, param in INDS:
        cells = []
        for key in srcs:
            cells += by.get(key, [])
        texts = valid_texts(cells)
        if kind == "g":
            bands, dft, low = param
            sc, note = growth_band(texts, bands, dft, low)
        elif kind == "pen": sc, note = score_pen(texts)
        elif kind == "neck": sc, note = score_neck(texts)
        elif kind == "cr5": sc, note = score_cr5(texts)
        elif kind == "util": sc, note = score_util(texts)
        elif kind == "tech": sc, note = score_tech(texts)
        elif kind == "comm": sc, note = score_comm(texts)
        elif kind == "margin": sc, note = score_margin(texts)
        elif kind == "roe": sc, note = score_roe(texts)
        elif kind == "pol": sc, note = score_pol(texts, cells)
        elif kind == "sub": sc, note = score_sub(texts)
        items.append({"cat": cat, "name": name, "max": mx, "score": sc, "note": note})
    cats = {}
    for it in items:
        cats[it["cat"]] = round(cats.get(it["cat"], 0) + it["score"], 2)
    total = 0.0
    for cm, w in CAT_W.items():
        cm_max = sum(i["max"] for i in items if i["cat"] == cm)
        total += cats.get(cm, 0) / cm_max * w
    return {"total": round(total, 1), "cats": cats, "items": items}

def main():
    recs = json.load(open(MAIN, encoding="utf-8"))
    for r in recs:
        if "old_score100" not in r:
            r["old_score100"] = r.get("score100")
            r["old_rank"] = r.get("rank")
        r["v21"] = score_industry(r)
    order = sorted(recs, key=lambda x: (-x["v21"]["total"], int(x["code"])))
    for i, r in enumerate(order, 1):
        r["v21"]["rank"] = i
    json.dump(recs, open(MAIN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{'排名':<4}{'代码':<5}{'行业':<22}{'总分':<7}")
    for r in order:
        print(f"#{r['v21']['rank']:<3}{r['code']:<5}{r['name'][:20]:<22}{r['v21']['total']:<7}")

if __name__ == "__main__":
    main()
