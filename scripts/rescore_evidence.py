# -*- coding: utf-8 -*-
"""证据驱动打分：不再用子代理的主观景气评级，而是从每个维度证据格的正/负信号计算维度分，再汇总为100分制。"""
import json, csv, os, re

OUT = "/Users/yihanran/WorkBuddy/2026-09-02-15-38-53/outputs"
TODAY = "2026-09-02"
# 显示维度与权重：来自用户提供的评分框架图（合计100分）
DIMS = ["需求增长", "供给能力", "盈利质量", "资本进入", "技术成熟度", "政策支持"]
WEIGHTS = {
    "需求增长": 25,
    "供给能力": 20,
    "盈利质量": 20,
    "资本进入": 10,
    "技术成熟度": 15,
    "政策支持": 10,
}
assert sum(WEIGHTS.values()) == 100

# cells 中仍沿用旧的2字维度名，评分时映射
DIM_CELL = {"需求增长": "需求", "供给能力": "供给", "盈利质量": "盈利",
            "资本进入": "资本", "技术成熟度": "技术", "政策支持": "政策"}

POS_WORDS = ["扭亏", "减亏", "增长", "增加", "提升", "上升", "上涨", "回升", "改善",
             "高增", "快增", "双位数", "创新高", "历史新高", "新高", "突破", "加码",
             "补贴", "奖励", "扶持", "融资", "投产", "扩产", "扩张", "出海",
             "翻番", "提速", "供不应求", "紧俏", "跃升", "净增",
             "高于", "强劲", "爆发", "井喷", "并购", "增资", "扩募",
             # 里程碑/活动类正向（需求、技术、资本、政策维度的完成与推进事实）
             "交付", "建成", "上线", "投运", "投用", "通水", "发射", "首航", "首飞",
             "签约", "中标", "订单", "新签", "落地", "量产", "商业化",
             "印发", "发布", "部署", "列入", "纳入", "批复", "专项债", "培育"]
NEG_WORDS = ["下降", "下滑", "减少", "回落", "收缩", "亏损", "承压", "下行", "负增长", "腰斩",
             "新低", "低迷", "过剩", "出清", "收紧", "跌破", "减产", "停产", "关停", "低于",
             "下调", "恶化", "疲软", "衰退", "高企", "拖累", "降负", "暴跌", "骤降", "萎缩",
             "断崖", "冷清"]

NUM_POS = re.compile(r'[+＋]\s*\d+(?:\.\d+)?\s*%')
NUM_NEG = re.compile(r'[-−－]\s*\d+(?:\.\d+)?\s*%')

def cell_sign_w(ev):
    """单条证据 (方向, 票数)。方向: +1 / 0 / -1。
    方向判定：百分比数字权重加倍（增长/降幅数字比词更可靠）+ 方向词投票。
    强信号加权：该条证据中出现 ≥20% 的百分比 → 记 2 票；≥50% → 记 3 票（默认 1 票）。
    即 +163.51% 的净利爆发与 +2.4% 的微增不再等权。"""
    t = ev or ""
    p = 2 * len(NUM_POS.findall(t))
    n = 2 * len(NUM_NEG.findall(t))
    for w in POS_WORDS:
        if w in t: p += 1
    for w in NEG_WORDS:
        if w in t: n += 1
    mags = [float(x) for x in re.findall(r'[+＋\-−－]\s*(\d+(?:\.\d+)?)\s*%', t)]
    m = max(mags) if mags else 0
    votes = 3 if m >= 50 else (2 if m >= 20 else 1)
    if p > n: return 1, votes
    if n > p: return -1, votes
    return 0, 0

def cell_sign(ev):
    """兼容旧接口：仅返回方向。"""
    return cell_sign_w(ev)[0]

def dim_score(cells):
    """维度分：base=1+4*正票/(正票+负票)，向中性3收缩。连续值（0.01精度，不取0.5步进）。
    强信号加权：单条证据出现 ≥20% 幅度数字按 2 票、≥50% 按 3 票计入（见 cell_sign_w）。
    单向信号权衡（票数口径）：
      - 单向且票数>=3 → 视为真实方向（正常收缩，伪计数2），标注"全负/全正信号"
      - 单向且票数<=2 → 可能缺少反方向信息，更强收缩（伪计数3），标注"单向弱负/弱正"
    返回 (分值, (pos,neg,neu), note)。"""
    if not cells:
        return None, (0, 0, 0), None
    pos = neg = neu = 0
    for c in cells:
        ev = c.get("ev") or ""
        if "全国口径" in ev:   # 全国口径不计入沪上评分
            neu += 1
            continue
        s, w = cell_sign_w(ev)
        if s > 0: pos += w
        elif s < 0: neg += w
        else: neu += 1
    n = pos + neg
    if n == 0:
        return 3.0, (pos, neg, neu), None   # 有证据但无方向词 → 中性
    base = 1 + 4.0 * pos / n
    one_sided = (pos == 0 or neg == 0)
    if one_sided and n <= 2:
        pseudo, note = 3.0, ("单向弱负" if neg else "单向弱正")
    elif one_sided:
        pseudo, note = 2.0, ("全负信号" if neg else "全正信号")
    else:
        pseudo, note = 2.0, None
    shrunk = (base * n + 3.0 * pseudo) / (n + pseudo)
    v = max(1.0, min(5.0, round(shrunk, 2)))
    return v, (pos, neg, neu), note

NOTE_DESC = {
    "单向弱负": "负向信号票数≤2，可能缺少正面信息，评分已向中性收缩",
    "单向弱正": "正向信号票数≤2，证据量少，评分已向中性收缩",
    "全负信号": "负向信号票数≥3且无正向，视为真实负向",
    "全正信号": "正向信号票数≥3且无负向",
}

def rating_of(s):
    """信号强度分级：注意这不是官方'景气指数'，是本库自建证据信号口径，公式见HTML方法说明。"""
    if s is None: return "证据不足"
    if s >= 80: return "信号强"
    if s >= 65: return "信号中强"
    if s >= 50: return "信号中"
    if s >= 35: return "信号中弱"
    return "信号弱"

def main():
    path = os.path.join(OUT, f"上海70行业指标证据_数据_{TODAY}.json")
    recs = json.load(open(path, encoding="utf-8"))
    for r in recs:
        # 保留原分析师打分供对照
        r["agent_dimscores"] = r.get("dimscores", {})
        r["agent_rating"] = r.get("rating")
        new_ds, sig, notes = {}, {}, {}
        for dm in DIMS:
            cell_dm = DIM_CELL[dm]
            cells = [c for c in r["cells"] if c["dim"] == cell_dm and not c.get("miss")]
            v, (p, n_, u), note = dim_score(cells)
            new_ds[dm] = v
            sig[dm] = {"pos": p, "neg": n_, "neu": u}
            if note:
                notes[dm] = note
        r["dimscores"] = new_ds
        r["dim_signals"] = sig
        r["dim_notes"] = notes
        r["flags"] = [f"{dm}：{NOTE_DESC[note]}" for dm, note in notes.items()]
        if any(v is None for v in new_ds.values()):
            na_dims = [dm for dm in DIMS if new_ds[dm] is None]
            r["flags"].append("无证据维度（" + "、".join(na_dims) + "）按中性3分计入加权")
        av = [v for v in new_ds.values() if v is not None]
        r["dims_available"] = len(av)
        if av:
            # 汇总口径：无证据维度按中性3分计入（防止"证据少反而分高"的选择偏差）
            # 维度原始分为1-5；加权贡献 = 维度分/5*权重；汇总=∑权重贡献
            agg = {dm: (v if v is not None else 3.0) for dm, v in new_ds.items()}
            r["score100"] = round(sum((agg[dm] / 5.0) * WEIGHTS[dm] for dm in DIMS), 2)
            r["dim_weighted"] = {dm: round((agg[dm] / 5.0) * WEIGHTS[dm], 2) for dm in DIMS}
            r["na_filled"] = 6 - len(av)
        else:
            r["score100"] = None
            r["dim_weighted"] = {}
            r["na_filled"] = 6
        r["rating"] = rating_of(r["score100"])
        r["rating_score"] = round(r["score100"] / 20, 2) if r["score100"] is not None else None
    # 排名：连续分值 + 三级平级决胜（综合分→核心证据格数→正向信号总数→代码），严格1–70不并列
    def tot_pos(r):
        return sum(s["pos"] for s in (r.get("dim_signals") or {}).values())
    order = sorted(recs, key=lambda x: (-(x["score100"] or 0), -x.get("core_filled", 0), -tot_pos(x), int(x["code"])))
    for i, r in enumerate(order, 1):
        r["rank"] = i
    json.dump(recs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(recs, open("/tmp/evidence_recs.json", "w", encoding="utf-8"), ensure_ascii=False)
    # 排名CSV
    rk = []
    for r in order:
        row = {"排名": r["rank"], "代码": r["code"], "行业": r["name"],
               "证据信号分(100·自建)": r["score100"] if r["score100"] is not None else "",
               "信号强度": r["rating"], "计分维度数": r["dims_available"],
               "核心证据格": f'{r["core_filled"]}/19',
               "信号权衡标注": "；".join(r.get("flags") or [])}
        for dm in DIMS:
            v = r["dimscores"].get(dm)
            s = r["dim_signals"][dm]
            note = (r.get("dim_notes") or {}).get(dm, "")
            row[dm] = v if v is not None else "NA"
            row[dm + "信号"] = f'+{s["pos"]}/-{s["neg"]}' + (f"({note})" if note else "")
        rk.append(row)
    with open(os.path.join(OUT, f"上海70行业综合排名_{TODAY}.csv"), "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rk[0].keys()))
        w.writeheader(); w.writerows(rk)
    # 汇总CSV
    sm = []
    for r in order:
        row = {"排名": r["rank"], "代码": r["code"], "行业": r["name"],
               "证据信号分(100·自建)": r["score100"] if r["score100"] is not None else "",
               "信号强度": r["rating"], "原分析师评级": r.get("agent_rating") or "",
               "核心19格填充数": r["core_filled"], "证据可信度": (r.get("cred") or "")[:60]}
        for dm in DIMS:
            v = r["dimscores"].get(dm)
            row[dm + "分"] = v if v is not None else "NA"
        sm.append(row)
    with open(os.path.join(OUT, f"上海70行业指标证据汇总_{TODAY}.csv"), "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(sm[0].keys()))
        w.writeheader(); w.writerows(sm)
    # 校验输出
    print("行业数:", len(recs))
    print("前10名（证据驱动分）:")
    for r in order[:10]:
        s = r["dim_signals"]
        sigtxt = " ".join(f'{dm}+{s[dm]["pos"]}/-{s[dm]["neg"]}' for dm in DIMS)
        print(f'  #{r["rank"]} {r["code"]} {r["name"]} {r["score100"]} (原{r.get("agent_rating")}) {sigtxt}')
    print("后5名:")
    for r in order[-5:]:
        print(f'  #{r["rank"]} {r["code"]} {r["name"]} {r["score100"]} (原{r.get("agent_rating")})')
    # 新旧排名变化
    old_order = sorted(recs, key=lambda x: (-(sum(v for v in x["agent_dimscores"].values() if v is not None) / max(1, sum(1 for v in x["agent_dimscores"].values() if v is not None)) * 20 if any(v is not None for v in x["agent_dimscores"].values()) else 0), int(x["code"])))
    old_rank = {r["code"]: i for i, r in enumerate(old_order, 1)}
    movers = sorted(recs, key=lambda x: old_rank[x["code"]] - x["rank"], reverse=True)
    print("排名上升最多:", [(m["code"], m["name"], f'#{old_rank[m["code"]]}→#{m["rank"]}') for m in movers[:5]])
    print("排名下降最多:", [(m["code"], m["name"], f'#{old_rank[m["code"]]}→#{m["rank"]}') for m in movers[-5:]])
    from collections import Counter
    print("评级分布:", dict(Counter(r["rating"] for r in recs)))
    # 信号权衡标注统计
    flagged = [r for r in recs if r.get("flags")]
    note_cnt = Counter(dm_note for r in recs for dm_note in (r.get("dim_notes") or {}).values())
    print("含权衡标注行业数:", len(flagged), "/70")
    print("标注类型分布:", dict(note_cnt))
    # 并列检查（连续分值下应基本消除）
    sc = [r["score100"] for r in recs if r["score100"] is not None]
    dup = [s for s, c in Counter(sc).items() if c > 1]
    print("显示精度(0.1)下仍同分的分值数:", len(dup), dup[:8] if dup else "")

if __name__ == "__main__":
    main()
