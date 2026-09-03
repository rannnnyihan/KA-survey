# -*- coding: utf-8 -*-
"""生成 上海70行业多维指标证据库 交互HTML（浅色主题，单文件无外部依赖）"""
import json, html, os, re

OUT = "/Users/yihanran/WorkBuddy/2026-09-02-15-38-53/outputs"
TODAY = "2026-09-02"
# 显示维度与权重（用户提供框架）
DIMS = ["需求增长", "供给能力", "盈利质量", "资本进入", "技术成熟度", "政策支持"]
WEIGHTS = {
    "需求增长": 25, "供给能力": 20, "盈利质量": 20,
    "资本进入": 10, "技术成熟度": 15, "政策支持": 10,
}
# ===== 行业评分体系：21指标/六大类（类权重合计100） =====
CATS = ["需求", "资本", "供给", "技术", "盈利", "政策"]
CAT_MAX = {"需求": 20, "资本": 10, "供给": 20, "技术": 20, "盈利": 20, "政策": 10}
# 各类指标分值合计（政策提及数4+补贴3+战略3=10，与类权重一致）
CAT_EARN = {"需求": 20, "资本": 10, "供给": 20, "技术": 20, "盈利": 20, "政策": 10}
# 类内细分指标（名称, 默认分值）——细分滑杆与每行 data-r-* 属性按此顺序生成
INDS_DEF = {
    "需求": [("FAI增长", 4), ("规上企业增长", 3), ("出口增长", 3), ("下游行业景气度", 4), ("渗透率提升空间", 3), ("龙头预算增长", 3)],
    "资本": [("行业投资增长", 5), ("融资活动增长", 5)],
    "供给": [("工业增加值", 5), ("供给瓶颈", 5), ("行业集中度", 5), ("产能利用率", 5)],
    "技术": [("技术突破", 7), ("商业化成熟度", 7), ("招聘人数增长", 6)],
    "盈利": [("龙头企业收入增长", 7), ("龙头企业利润率改善", 7), ("龙头企业ROE/ROIC", 6)],
    "政策": [("政策提及数", 4), ("政府补贴", 3), ("国家战略支持", 3)],
}

def wcat(r, cm):
    """类别加权得分 = 类内得分/类内满分 × 类权重。"""
    v = ((r.get("v21") or {}).get("cats") or {}).get(cm)
    return None if v is None else v / CAT_EARN[cm] * CAT_MAX[cm]
# cells/json 中仍沿用旧的2字维度名
DIM_CELL = {"需求增长": "需求", "供给能力": "供给", "盈利质量": "盈利",
            "资本进入": "资本", "技术成熟度": "技术", "政策支持": "政策"}
IND_MAP = {
    "需求增长": ["市场需求增长", "出口增长", "下游行业景气度", "渗透率提升空间", "客户预算增长"],
    "供给能力": ["工业增加值", "供给瓶颈", "行业集中度", "产能利用率"],
    "盈利质量": ["龙头企业收入增长", "利润率改善", "ROE/ROIC"],
    "资本进入": ["行业投资增长", "融资活动增长"],
    "技术成熟度": ["技术突破", "商业化成熟度"],
    "政策支持": ["政策提及数", "政府补贴", "国家战略支持"],
}
RATING_ORDER = ["信号强", "信号中强", "信号中", "信号中弱", "信号弱", "证据不足"]
NOTE_DESC = {
    "单向弱负": "负向信号票数≤2，可能缺少正面信息，评分已向中性收缩",
    "全负信号": "负向信号票数≥3且无正向，视为真实负向",
    "单向弱正": "正向信号票数≤2，证据量少，评分已向中性收缩",
    "全正信号": "正向信号票数≥3且无负向",
}
NEG_NOTES = {"单向弱负", "全负信号"}
TIER_COL = {"S1": "#166534", "S2": "#1d4ed8", "S3": "#92400e", "S4": "#6b7280"}
TIER_BG = {"S1": "#ecfdf3", "S2": "#eff4ff", "S3": "#fef6ec", "S4": "#f3f4f6"}

def esc(x): return html.escape(str(x if x is not None else ""), quote=True)

# ===== 每行业一句话 AI 摘要（主表展示用，非评分依据） =====
_TIER_PRI = {"S1": 0, "S2": 1, "S3": 2, "S4": 3, "": 4}
_NUM = re.compile(r'\d+(\.\d+)?\s*(%|亿元|万亿|万辆|万|家|个)')
_SH = re.compile(r'上海|沪|本市|全市')

def ai_summary(r, limit=46):
    """从证据格中挑一条最有代表性的上海口径证据，压成一句话。"""
    cands = []
    for c in r.get("cells", []):
        if c.get("miss") or c.get("dim") == "补充":
            continue
        ev = c.get("ev", "")
        if not ev or len(ev) < 8 or ev.startswith(("缺沪", "缺数据", "无沪", "暂无")):
            continue
        has_num = bool(_NUM.search(ev))
        is_sh = bool(_SH.search(ev)) and "全国口径" not in ev[:40]
        score = (0 if (has_num and is_sh) else 1 if is_sh else 2 if has_num else 3,
                 _TIER_PRI.get(c.get("tier", ""), 4),
                 0 if "2026" in (c.get("year") or "") else 1)
        cands.append((score, ev))
    if not cands:
        return "以定性信号为主，详见证据格。"
    cands.sort(key=lambda x: x[0])
    t = re.sub(r"\s+", "", cands[0][1])
    if len(t) > limit:
        t = t[:limit].rstrip("，、；:：") + "…"
    return t

_CRED_PAT = re.compile(r'(中高|中低|高|中|低)')
def cred_norm(r):
    """把 cred 长文本归一化为 高/中高/中/低 徽章文案。"""
    c = (r.get("cred") or "").strip()
    m = _CRED_PAT.match(c)
    return m.group(1) if m else (c[:2] if c else "中")

# ===== 施耐德 NS 行业映射（tag, 成员国标行业）NS得分=成员行业总分均值 =====
NS_MAP = {
    # 保
    "商业楼宇": ("保", ["房屋建筑业", "建筑安装业", "建筑装饰、装修和其他建筑业", "批发业", "零售业", "房地产业", "租赁业", "商务服务业"]),
    "公共建筑": ("保", ["房屋建筑业", "土木工程建筑业", "建筑安装业", "建筑装饰、装修和其他建筑业", "公共设施管理业", "教育"]),
    "住宅": ("保", ["房屋建筑业", "建筑安装业", "建筑装饰、装修和其他建筑业", "房地产业"]),
    "PSB": ("保", ["房屋建筑业", "土木工程建筑业", "建筑安装业", "建筑装饰、装修和其他建筑业", "公共设施管理业", "教育"]),
    "OEM（不含风光储充氢、DC、低空…）": ("保", ["通用设备制造业", "专用设备制造业", "电气机械和器材制造业", "计算机、通信和其他电子设备制造业", "仪器仪表制造业"]),
    "地铁": ("保", ["土木工程建筑业", "建筑安装业", "铁路运输业"]),
    # 增
    "医院": ("增", ["房屋建筑业", "建筑安装业", "建筑装饰、装修和其他建筑业"]),
    "数据中心及通讯": ("增", ["电信、广播电视和卫星传输服务", "互联网和相关服务", "软件和信息技术服务业", "货币金融服务", "资本市场服务", "保险业", "其他金融业"]),
    "数据中心及通讯（项目）": ("增", ["电信、广播电视和卫星传输服务", "互联网和相关服务", "软件和信息技术服务业", "货币金融服务", "资本市场服务", "保险业", "其他金融业"]),
    "数据中心及通讯（OEM）": ("增", ["通用设备制造业", "专用设备制造业", "电气机械和器材制造业", "计算机、通信和其他电子设备制造业", "仪器仪表制造业", "电信、广播电视和卫星传输服务", "互联网和相关服务", "软件和信息技术服务业"]),
    "电子": ("增", ["计算机、通信和其他电子设备制造业", "仪器仪表制造业"]),
    "航空航天": ("增", ["铁路、船舶、航空航天和其他运输设备制造业", "航空运输业"]),
    "航空航天（项目）": ("增", ["铁路、船舶、航空航天和其他运输设备制造业", "土木工程建筑业", "建筑安装业", "航空运输业"]),
    "低空经济（OEM）": ("增", ["通用设备制造业", "专用设备制造业", "铁路、船舶、航空航天和其他运输设备制造业", "电气机械和器材制造业", "计算机、通信和其他电子设备制造业", "仪器仪表制造业"]),
    "水务及环保公用事业": ("增", ["造纸和纸制品业", "印刷和记录媒介复制业", "废弃资源综合利用业", "水的生产和供应业", "水利管理业", "生态保护和环境治理业", "公共设施管理业", "土地管理业"]),
    "化工（非石化）": ("增", ["化学原料和化学制品制造业", "化学纤维制造业", "橡胶和塑料制品业"]),
    "石油天然气": ("增", ["石油和天然气开采业", "石油、煤炭及其他燃料加工业", "管道运输业"]),
    "新能源": ("增", ["电力、热力生产和供应业"]),
    "新能源（项目）": ("增", ["电力、热力生产和供应业", "土木工程建筑业", "建筑安装业"]),
    "新能源（OEM）": ("增", ["通用设备制造业", "专用设备制造业", "电气机械和器材制造业", "计算机、通信和其他电子设备制造业", "仪器仪表制造业", "电力、热力生产和供应业"]),
    # 拓
    "铁路": ("拓", ["铁路、船舶、航空航天和其他运输设备制造业", "铁路运输业"]),
    "M&M（矿业与建材）": ("拓", ["煤炭开采和洗选业", "石油和天然气开采业", "黑色金属矿采选业", "有色金属矿采选业", "非金属矿采选业", "开采专业及辅助性活动", "其他采矿业", "非金属矿物制品业"]),
    "冶金": ("拓", ["黑色金属冶炼和压延加工业", "有色金属冶炼和压延加工业", "金属制品业", "金属制品、机械和设备修理业"]),
    "生命科学": ("拓", ["医药制造业"]),
    "路桥隧道": ("拓", ["土木工程建筑业", "道路运输业"]),
    "船舶制造": ("拓", ["铁路、船舶、航空航天和其他运输设备制造业", "水上运输业"]),
    "船舶制造（项目）": ("拓", ["铁路、船舶、航空航天和其他运输设备制造业", "土木工程建筑业", "建筑安装业", "水上运输业"]),
    "船舶制造（OEM）": ("拓", ["通用设备制造业", "专用设备制造业", "铁路、船舶、航空航天和其他运输设备制造业", "电气机械和器材制造业", "仪器仪表制造业"]),
    "汽车（含新能源汽车）": ("拓", ["汽车制造业"]),
    "食品饮料（含烟酒）": ("拓", ["农副食品加工业", "食品制造业", "酒、饮料和精制茶制造业", "烟草制品业"]),
    "智慧照明": ("拓", ["电气机械和器材制造业", "计算机、通信和其他电子设备制造业", "仪器仪表制造业", "公共设施管理业"]),
    "港口": ("拓", ["土木工程建筑业", "建筑安装业", "水上运输业", "多式联运和运输代理业", "装卸搬运和仓储业"]),
    # 其它
    "核电": ("其它", ["电力、热力生产和供应业"]),
    "火电": ("其它", ["电力、热力生产和供应业"]),
    "水电": ("其它", ["电力、热力生产和供应业"]),
    "造纸": ("其它", ["造纸和纸制品业", "印刷和记录媒介复制业"]),
    "Other": ("其它", ["纺织业", "纺织服装、服饰业", "皮革、毛皮、羽毛及其制品和制鞋业", "木材加工和木、竹、藤、棕、草制品业", "家具制造业", "邮政业", "研究和试验发展", "专业技术服务业", "科技推广和应用服务业"]),
}

def host_path_bare(u):
    m = re.match(r'https?://([^/]+)(/.*)?$', u)
    if not m: return False
    return (not m.group(2)) or m.group(2) in ("/", "/index.html")

def tier_chip(t):
    if not t: return ""
    c, b = TIER_COL.get(t, "#6b7280"), TIER_BG.get(t, "#f3f4f6")
    return f'<span class="tc" style="color:{c};background:{b}">{esc(t)}</span>'

def url_links(urls):
    if not urls: return ""
    parts = []
    for u in urls:
        label = "栏目首页" if host_path_bare(u) else "来源"
        parts.append(f'<a class="src" href="{esc(u)}" target="_blank" rel="nofollow noopener">{esc(u) if len(u) < 80 else u[:62] + "…"}</a>')
    return '<span class="urls">' + " · ".join(parts) + "</span>"

def cell_html(c):
    if c.get("miss"):
        note = re.sub(r'^(缺沪数据|缺数据|无沪数据|无上海|无本市|暂无上海|待统一接口补充|NA)', '', esc(c["ev"])).strip()
        note = re.sub(r'^[：:\s]+', '', note)
        tags = tier_chip(c.get("tier", ""))
        if c.get("year"):
            tags += f'<span class="yr">{esc(c["year"])}</span>'
        return (f'<div class="cell miss"><span class="ind">{esc(c["ind"])}</span>'
                f'<span class="mnote">缺沪数据<span class="mdet">{note}</span></span>'
                f'<span class="tags">{tags}</span>'
                + url_links(c.get("urls") or []) + "</div>")
    return (f'<div class="cell"><div class="cellhd"><span class="ind">{esc(c["ind"])}</span>'
            f'<span class="tags">{tier_chip(c.get("tier", ""))}'
            + (f'<span class="yr">{esc(c["year"])}</span>' if c.get("year") else "")
            + '</span></div><div class="ev">' + esc(c["ev"]) + "</div>"
            + url_links(c.get("urls") or []) + "</div>")

def fill_bar(filled, total=21):
    return f'<div class="fb"><div class="fbi" style="width:{filled/total*100:.0f}%"></div></div>'

def evid_count(r):
    """21项指标中有实际证据支撑的项数（评分理由为"查不到"的按缺证据计）。"""
    items = (r.get("v21") or {}).get("items") or []
    if not items:
        return r.get("core_filled", 0)
    return sum(1 for it in items if not it["note"].startswith(("查不到", "无公开", "无法确认")))

# ===== 官方与宏观指数 → 对应行业映射（对照展示，不参与评分） =====
_M_MINING = ["06", "07", "08", "09", "10", "11", "12"]
_M_MANU = ["13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40", "42", "43"]
_M_UTIL = ["44", "46"]
_M_IND = _M_MINING + _M_MANU + _M_UTIL
_M_EQUIP = ["34", "35", "36", "37", "38", "39", "40"]
_M_HITECH = ["27", "39", "40"]
_M_CONSUMER = ["13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"]
_M_HIGHENERGY = ["25", "26", "28", "29", "30", "31", "32", "44"]
_M_CONSTR = ["47", "48", "49", "50"]
_M_TRANSPORT = ["53", "54", "55", "56", "57", "58", "59", "60"]
_M_INFO = ["63", "64", "65"]
_M_WHOLE_RETAIL = ["51", "52"]
_M_ACCOM = ["61", "62"]
_M_REAL = ["70"]
_M_SERVICES = ["51", "52", "53", "54", "55", "56", "57", "58", "59", "60", "61", "62",
               "63", "64", "65", "66", "67", "68", "69", "70", "71", "72", "73", "74",
               "75", "76", "77", "78", "79", "83"]
_M_NONMANU = _M_CONSTR + _M_SERVICES
MACRO_BY_IND = {}

def _macro_targets(m):
    """按标题/文本特征把宏观指数条目映射到对应的行业代码组；无对应行业返回 []。"""
    t = m.get("title") or ""
    x = m.get("text") or ""
    if "PMI分类行业指数" in t:
        return _M_EQUIP + _M_HITECH + _M_CONSUMER + _M_HIGHENERGY
    if "EPMI" in t:
        return _M_EQUIP + ["27"] + _M_INFO
    if "非制造业商务活动指数" in t:
        return _M_NONMANU
    if "制造业PMI" in t or "制造业景气PMI" in t:
        return _M_MANU
    if "PPI" in t:
        return _M_IND
    if "能源生产" in t:
        return ["06", "07", "44"]
    if "工业生产" in t:
        return _M_IND
    if "产能利用率" in t:
        return _M_IND
    if "企业景气指数" in t:
        return []  # 经济总体读数，无对应细分行业
    if "BSI" in t:
        return _M_IND  # 工业企业样本调查
    if "FAI" in t or "固定资产投资" in t:
        if "上海分行业" in x:
            return _M_IND + _M_CONSTR + _M_TRANSPORT + _M_INFO + _M_WHOLE_RETAIL + _M_ACCOM + _M_REAL
        if "上海工业投资" in x:
            return _M_IND
        if "上海全市固定资产投资" in x:
            return []  # 全市总量，无对应细分行业
        if "装备制造业投资" in x:
            return _M_MANU + _M_EQUIP
        if "通用装备" in x:
            return ["34", "37", "39", "33", "31", "30", "28", "29", "15", "18", "20", "21"]
        if "采矿业投资" in x:
            return _M_MINING + _M_MANU + _M_CONSTR + _M_REAL
        return []  # 全国总量，无对应细分行业
    if "市场规模" in t:
        return ["39", "27", "65"]  # 集成电路 / 生物医药 / 人工智能三大先导
    return []

def build_macro_by_ind(macro_all):
    out = {}
    for m in macro_all:
        for code in dict.fromkeys(_macro_targets(m)):
            out.setdefault(code, []).append(m)
    return out

def macro_panel_html(code):
    items = MACRO_BY_IND.get(code) or []
    if not items:
        return ""
    rows = []
    for mm in items:
        tags = tier_chip(mm.get("tier") or "")
        if mm.get("year"):
            tags += f'<span class="yr">{esc(mm["year"])}</span>'
        rows.append('<div class="cell"><div class="cellhd"><span class="ind">' + esc(mm.get("title") or "")
                    + '</span><span class="tags">' + tags + '</span></div><div class="ev">'
                    + esc(mm.get("text") or "") + "</div>" + url_links(mm.get("urls") or []) + "</div>")
    return ('<details class="panel"><summary class="phead"><span>官方与宏观指数基准</span>'
            '<span class="dsc info">对照 · 不参与评分</span></summary>' + "".join(rows) + "</details>")

def dim_bars(r):
    parts = []
    for cm in CATS:
        v = wcat(r, cm)
        if v is None:
            parts.append(f'<span class="db na">{cm}<b>–</b></span>')
        else:
            pct = v / CAT_MAX[cm] * 100
            parts.append(f'<span class="db"><i>{cm}</i><span class="dbtr"><span class="dbf" style="width:{pct:.0f}%"></span></span><b title="类别得分（满分{CAT_MAX[cm]}）">{v:.1f}</b></span>')
    return '<div class="dbars">' + "".join(parts) + "</div>"

def v23_panel(r):
    """23项指标评分明细面板。"""
    v = r.get("v23") or {}
    items = v.get("items") or []
    if not items:
        return ""
    rows = []
    cur = None
    for it in items:
        if it["cat"] != cur:
            cur = it["cat"]
            rows.append(f'<div class="v23cat">{esc(cur)}（满分{CAT_MAX[cur]}）</div>')
        pct = it["score"] / it["max"] * 100
        rows.append(
            f'<div class="v23row"><span class="v23n">{esc(it["name"])}</span>'
            f'<span class="v23bar"><span class="v23bf" style="width:{pct:.0f}%"></span></span>'
            f'<span class="v23s">{it["score"]:g}/{it["max"]:g}</span>'
            f'<span class="v23note">{esc(it["note"])}</span></div>')
    return ('<details class="panel"><summary class="phead"><span>23项指标评分明细（企业评分标准）</span>'
            f'<span class="dsc info">合计 {v.get("total", 0):g}/100</span></summary>'
            + "".join(rows) + "</details>")

# 证据格 → 六大类映射（行业评分体系与旧六维基本一一对应；补充维按指标归入）
IND2CAT = {
    ("补充", "VC·PE与并购"): "资本",
    ("补充", "招聘岗位增速"): "技术",
    ("补充", "企业注册热度"): "需求",
    ("补充", "行业协会与标准"): "政策", ("补充", "行业协会与活动"): "政策",
    ("资本", "行业投资增长"): "资本",
}
DIM2CAT = {"需求": "需求", "供给": "供给", "盈利": "盈利",
           "资本": "资本", "技术": "技术", "政策": "政策", "补充": "需求"}

# 打分指标 → 支撑证据格（与 rescore_ind21.py 的取数口径一致）
IND_SRC = {
    "FAI增长": [("资本", "行业投资增长")],
    "规上企业增长": [("补充", "企业注册热度")],
    "出口增长": [("需求", "出口增长")],
    "下游行业景气度": [("需求", "下游行业景气度")],
    "渗透率提升空间": [("需求", "渗透率提升空间")],
    "龙头预算增长": [("需求", "客户预算增长")],
    "行业投资增长": [("资本", "行业投资增长")],
    "融资活动增长": [("资本", "融资活动增长"), ("补充", "VC·PE与并购")],
    "工业增加值": [("供给", "工业增加值")],
    "供给瓶颈": [("供给", "供给瓶颈")],
    "行业集中度": [("供给", "行业集中度")],
    "产能利用率": [("供给", "产能利用率")],
    "技术突破": [("技术", "技术突破")],
    "商业化成熟度": [("技术", "商业化成熟度")],
    "招聘人数增长": [("补充", "招聘岗位增速")],
    "龙头企业收入增长": [("盈利", "龙头企业收入增长")],
    "龙头企业利润率改善": [("盈利", "利润率改善")],
    "龙头企业ROE/ROIC": [("盈利", "ROE/ROIC")],
    "政策提及数": [("政策", "政策提及数")],
    "政府补贴": [("政策", "政府补贴")],
    "国家战略支持": [("政策", "国家战略支持")],
}

def industry_body(r):
    """生成行业卡片的内容体（不含外层折叠标题），供抽屉与详情共用。"""
    v21 = r.get("v21") or {}
    items = v21.get("items") or []
    # 证据格按 (dim,ind) 归组
    by2 = {}
    for c in r["cells"]:
        by2.setdefault((c.get("dim"), c.get("ind")), []).append(c)
    used = set()
    panels = []
    for cm in CATS:
        wv = wcat(r, cm)
        sc_txt = f'{wv:.1f}/{CAT_MAX[cm]}' if wv is not None else "–"
        htmls = []
        # 每个打分指标：得分行 + 该指标的支撑证据
        for it in [i for i in items if i["cat"] == cm]:
            pct = it["score"] / it["max"] * 100
            htmls.append(
                f'<div class="v23row"><span class="v23n">{esc(it["name"])}</span>'
                f'<span class="v23bar"><span class="v23bf" style="width:{pct:.0f}%"></span></span>'
                f'<span class="v23s">{it["score"]:g}/{it["max"]:g}</span>'
                f'<span class="v23note">{esc(it["note"])}</span></div>')
            srcs = IND_SRC.get(it["name"], [])
            evs = []
            for key in srcs:
                for c in by2.get(key, []):
                    evs.append(c)
                    used.add(id(c))
            if evs:
                htmls.append('<div class="subev">' + "".join(cell_html(c) for c in evs) + "</div>")
        # 未映射到打分指标的剩余证据（参考用）
        rest = [c for c in r["cells"]
                if id(c) not in used
                and (IND2CAT.get((c.get("dim"), c.get("ind"))) or DIM2CAT.get(c.get("dim"), "需求")) == cm]
        if rest:
            htmls.append('<div class="extra" style="margin:8px 0 4px;border-top:1px dashed #dfe5ec;padding-top:6px;font-size:12px;color:#8a97a5">其他参考证据（不计分）</div>')
            for c in rest:
                htmls.append(cell_html(c))
        chip = f'<span class="dsc info">{sc_txt}</span>'
        panels.append(f'<details class="panel"><summary class="phead"><span>{esc(cm)}</span>{chip}</summary>{"".join(htmls)}</details>')
    mp = macro_panel_html(r["code"])
    if mp:
        panels.append(mp)
    pos = esc(r.get("position") or "本轮未检索到沪上形态描述。")
    cred = esc(r.get("cred") or "")
    score = v21.get("total")
    score_txt = f'{score:g}/100' if score is not None else "–"
    rank = v21.get("rank")
    rank_chip = f'<span class="rk">全榜第{rank}名</span>' if rank else ""
    fill = evid_count(r)
    cred_html = f'<span class="cov">可信度 {cred}</span>' if cred else ""
    return f'''
<div class="drawer-head">
  <div class="dh-left">
    <span class="nm">{esc(r["name"])}</span>
    {rank_chip}
    <span class="meta">综合得分 <b>{score_txt}</b></span>
    <span class="fill">证据 {fill}/21 {fill_bar(fill)}</span>
  </div>
  <button class="drawer-close" onclick="closeDrawer(event)" aria-label="关闭抽屉">✕</button>
</div>
<div class="indbody">
  <details class="panel poswhy" open><summary class="phead"><span>沪上产业形态与背景</span>{cred_html}</summary>
    <div class="pos"><b>沪上形态与背景（事实描述）</b><p>{pos}</p></div>
  </details>
  <div class="scoreline"><b>六大类得分（行业评分体系 · 21项指标）</b>{dim_bars(r)}</div>
  <div class="panels">{"".join(panels)}</div>
</div>'''

def industry_card(r):
    """生成底部完整折叠卡片（默认收起，抽屉关闭后仍可到这里展开浏览）。"""
    code = r["code"]
    name = r["name"]
    v23 = r.get("v21") or {}
    score = v23.get("total")
    score_txt = f'{score:g}/100' if score is not None else "–"
    fill = evid_count(r)
    rank = v23.get("rank")
    rank_chip = f'<span class="rk">全榜第{rank}名</span>' if rank else ""
    return f'''
<details class="ind" data-code="{code}" data-name="{esc(name)}{code}" data-text="{esc(name + " " + code + " " + (r.get("position") or ""))}" id="ind-{code}">
<summary>
  <span class="nm">{esc(name)}</span>
  {rank_chip}
  <span class="meta">综合得分 <b>{score_txt}</b></span>
  <span class="fill">证据 {fill}/21 {fill_bar(fill)}</span>
  <span class="arw">▾</span>
</summary>
{industry_body(r)}
</details>'''

def main():
    recs = json.load(open("/tmp/evidence_recs.json", encoding="utf-8"))
    # stats
    n = len(recs)
    total_core = 21 * n
    filled = sum(evid_count(r) for r in recs)
    # 官方与宏观指数 → 并入对应行业卡展示（不参与自建信号评分，仅作对照）
    try:
        macro_all = json.load(open("/tmp/refresh2026/macro_indices.json", encoding="utf-8"))
    except Exception:
        macro_all = []
    global MACRO_BY_IND
    MACRO_BY_IND = build_macro_by_ind(macro_all)
    cards = "".join(industry_card(r) for r in recs)
    # ===== 两级结构：NS 行业行（可展开）+ 成员国标行业行 =====
    name2rec = {r["name"]: r for r in recs}
    used = set()
    ns_groups = []
    for ns, (tag, members) in NS_MAP.items():
        mem = [name2rec[m] for m in members if m in name2rec]
        for m in mem:
            used.add(m["name"])
        avg = round(sum((x.get("v21") or {}).get("total") or 0 for x in mem) / len(mem), 1) if mem else 0
        ns_groups.append({"ns": ns, "tag": tag, "avg": avg,
                          "members": sorted(mem, key=lambda x: -((x.get("v21") or {}).get("total") or 0))})
    un = [r for r in recs if r["name"] not in used]
    if un:
        for g in ns_groups:
            if g["ns"] == "Other":
                g["members"] += sorted(un, key=lambda x: -((x.get("v21") or {}).get("total") or 0))
                g["avg"] = round(sum((x.get("v21") or {}).get("total") or 0 for x in g["members"]) / len(g["members"]), 1)
    ns_groups.sort(key=lambda g: -g["avg"])

    def gb_row(r, ns_name, idx):
        v21 = r.get("v21") or {}
        score = v21.get("total")
        rk = v21.get("rank")
        dim_txt = "".join(
            f'<td class="ovd">{wcat(r, cm):.1f}</td>' if wcat(r, cm) is not None
            else '<td class="ovd na">–</td>'
            for cm in CATS)
        txt = esc(r['name'] + ' ' + r['code'] + ' ' + (r.get('position') or ''))
        dim_attrs = "".join(
            f' data-dim-{esc(cm)}="{((wcat(r, cm) or 0) / CAT_MAX[cm] * 5):.4f}"' for cm in CATS)
        rat = {}
        for it in (v21.get("items") or []):
            rat[(it["cat"], it["name"])] = (it["score"] / it["max"]) if it["max"] else 0.6
        dim_attrs += "".join(
            f' data-r-{esc(cm)}-{i}="{rat.get((cm, nm), 0.6):.4f}"'
            for cm in CATS for i, (nm, _w) in enumerate(INDS_DEF[cm]))
        cred_v = cred_norm(r)
        return (f'<tr class="gbrow" data-ns="{esc(ns_name)}" data-code="{r["code"]}" data-text="{txt}"{dim_attrs} onclick="openDrawer(\'{r["code"]}\')">'
                f'<td class="ovr" title="70行业全榜第{rk}名">{("#" + str(rk)) if rk else "–"}</td>'
                f'<td class="ovn">{esc(r["name"])}</td>'
                + dim_txt +
                f'<td class="ovs"><b>{score if score is not None else "–"}</b></td>'
                f'<td class="ovai">{esc(ai_summary(r))}</td>'
                f'<td class="ovf">{evid_count(r)}/21</td>'
                f'<td class="ovcred"><span class="credb cred-{cred_v}">{esc(cred_v)}</span></td></tr>')

    ov_rows = ""
    for i, g in enumerate(ns_groups, 1):
        members_txt = "、".join(m["name"] for m in g["members"])
        if len(members_txt) > 70:
            members_txt = members_txt[:70].rstrip("、") + "…"
        # NS 行六大类得分 = 成员国标行业各类加权分的均值
        ns_dims = "".join(
            f'<td class="ovd nsd">{(sum((wcat(m, cm) or 0) for m in g["members"]) / len(g["members"])):.1f}</td>'
            if g["members"] else '<td class="ovd nsd na">–</td>'
            for cm in CATS)
        ov_rows += (f'<tr class="nsr" data-ns="{esc(g["ns"])}" data-tag="{esc(g["tag"])}" data-avg="{g["avg"]}" onclick="toggleNs(this)">'
                    f'<td class="ovr">#{i}</td>'
                    f'<td class="nsname"><span class="nmb">{esc(g["ns"])}</span>'
                    f'<span class="tagb tag-{esc(g["tag"])}">{esc(g["tag"])}</span>'
                    f'<span class="nsn">{len(g["members"])} 个行业</span><span class="arw2">▸</span></td>'
                    + ns_dims +
                    f'<td class="ovs"><b class="nsavg">{g["avg"]}</b></td>'
                    f'<td class="ovai">{esc(members_txt)}</td>'
                    f'<td class="ovf">–</td><td class="ovcred">–</td></tr>')
        for j, m in enumerate(g["members"], 1):
            ov_rows += gb_row(m, g["ns"], j)
    neg_flagged = sum(1 for r in recs if any(n in NEG_NOTES for n in (r.get("dim_notes") or {}).values()))
    na_flagged = sum(1 for r in recs if (r.get("dims_available") or 6) < 6)
    # 权重滑杆区：仅大类滑杆（细分按钮已按用户要求移除）
    wgrid_html = ""
    for cm in CATS:
        wgrid_html += (
            f'<div class="wcat"><label><span>{esc(cm)} <output class="wval" data-for="{esc(cm)}">{CAT_MAX[cm]}</output></span>'
            f'<input type="range" min="0" max="50" step="0.1" value="{CAT_MAX[cm]}" data-dim="{esc(cm)}"></label></div>')
    # v23 明细面板样式（普通字符串，注入 f-string 不转义）
    v23_css = (
        ".v23cat{font-weight:700;font-size:13px;margin:12px 0 6px;color:#1c2733;border-left:3px solid var(--acc);padding-left:8px}"
        ".v23row{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px dashed #f0f3f7;font-size:12.5px}"
        ".v23n{width:120px;flex-shrink:0;color:#3a4a58}"
        ".v23bar{width:70px;height:6px;background:#eef2f6;border-radius:4px;overflow:hidden;flex-shrink:0}"
        ".v23bf{display:block;height:100%;background:#0f62fe}"
        ".v23s{width:52px;flex-shrink:0;font-weight:700;color:var(--acc);font-size:12px}"
        ".v23note{color:var(--mut);font-size:12px;flex:1}"
        ".subev{margin:2px 0 8px;padding-left:10px;border-left:2px solid #e4ebf5}"
        ".wcat{display:flex;flex-direction:column;gap:4px}"
        ".wcat>label{display:flex;flex-direction:column;gap:4px}"
        ".wcat>label>span{display:flex;justify-content:space-between;align-items:center;gap:6px}"
        ".nsr{background:#fff;cursor:pointer;border-top:2px solid #e8edf4}"
        ".nsr:hover{background:#f5f8ff}"
        ".nsr.open{background:#f0f5ff}"
        ".nsr .nsname{position:relative;padding-left:14px;font-size:14px}"
        ".nsr .nsname::before{content:'';position:absolute;left:0;top:50%;transform:translateY(-50%);width:4px;height:22px;border-radius:2px;background:#c3d0f5}"
        ".nsr[data-tag=保] .nsname::before{background:#3b82f6}"
        ".nsr[data-tag=增] .nsname::before{background:#10b981}"
        ".nsr[data-tag=拓] .nsname::before{background:#f59e0b}"
        ".nsr[data-tag=其它] .nsname::before{background:#9ca3af}"
        ".nsr .nsd{color:#3a4a58}"
        ".nmb{font-weight:700}"
        ".tagb{display:inline-block;padding:1px 8px;border-radius:6px;font-size:11.5px;font-weight:700;margin-left:8px}"
        ".tag-保{background:#e7f0fe;color:#1d4ed8}"
        ".tag-增{background:#e7f6ee;color:#0f8a4d}"
        ".tag-拓{background:#fdf3d7;color:#8a6d1a}"
        ".tag-其它{background:#f3f4f6;color:#6b7280}"
        ".nsn{color:var(--mut);font-size:12px;margin-left:8px;font-weight:400}"
        ".arw2{color:#8fa3bb;margin-left:6px;font-size:12px}"
        ".gbrow{display:none}"
        ".gbrow.open{display:table-row}"
        ".gbrow td:first-child{padding-left:26px;color:#98a3ad;font-weight:400}"
        ".gbrow .ovn{padding-left:14px}"
        ".gbrow .ovn::before{content:'└ ';color:#c3cedd}"
    )
    html_doc = f'''<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>上海70行业多维指标证据库 · {TODAY}</title>
<style>
:root{{--ink:#1c2733;--mut:#5d6d7e;--line:#e4e9ef;--bg:#f7f8fa;--card:#ffffff;--acc:#0f62fe;--accbg:#eaf1ff}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1560px;margin:0 auto;padding:24px 32px 90px}}
h1{{font-size:22px;margin:0 0 4px}}h1 small{{font-weight:400;color:var(--mut);font-size:13px}}
.sub{{color:var(--mut);margin:0 0 16px}}
.meta-card{{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}}
.mc{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px;font-size:12px;color:var(--mut)}}
.mc b{{color:var(--ink)}}
.statrow{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}}
.stat .n{{font-size:26px;font-weight:700}} .stat .l{{font-size:12px;color:var(--mut)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:14px 0}}
.card h2{{font-size:16px;margin:0 0 10px;display:flex;justify-content:space-between;align-items:center}}
.tbl{{width:100%;border-collapse:collapse;font-size:13px}}
.tbl th{{text-align:left;color:var(--mut);font-weight:600;border-bottom:1px solid var(--line);padding:6px 8px}}
.tbl td{{padding:6px 8px;border-bottom:1px solid #eef2f6}}
.bar{{display:inline-block;width:120px;height:8px;border-radius:5px;background:#eef2f6;overflow:hidden;vertical-align:middle}}
.bar span{{display:block;height:100%}}
.rb{{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600;white-space:nowrap}}
.toolbar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0}}
#q{{flex:1 1 240px;padding:9px 12px;border:1px solid var(--line);border-radius:10px;font-size:14px;background:#fff}}
.sel{{padding:9px 12px;border:1px solid var(--line);border-radius:10px;font-size:13px;background:#fff;color:var(--ink);cursor:pointer}}
.chip{{border:1px solid var(--line);background:#fff;border-radius:99px;padding:5px 12px;font-size:12.5px;color:var(--ink);cursor:pointer}}
.chip.active{{background:var(--acc);border-color:var(--acc);color:#fff}}
.hint{{font-size:12px;color:var(--mut)}}
.weights{{background:#f4f8ff;border:1px solid #d6e4ff;border-radius:12px;padding:12px 14px;margin:8px 0 14px}}
.wlbl{{font-size:12.5px;color:var(--mut);margin-bottom:8px}}
.wgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.wgrid label{{display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:var(--ink);font-weight:600}}
.wgrid label>span{{display:flex;justify-content:space-between;align-items:baseline}}
.wval{{font-family:ui-monospace,Menlo,monospace;font-weight:700;color:var(--acc);font-size:13px}}
.wgrid input[type=range]{{width:100%}}
.wgrid output{{font-family:ui-monospace,Menlo,monospace;font-weight:700;color:var(--acc);font-size:13px}}
.wtot{{font-size:12.5px;color:var(--mut);margin-top:8px}}
.wtot.over{{color:#c0392b}}
.wtot b{{color:var(--ink);font-size:13px}}
@media(max-width:720px){{.wgrid{{grid-template-columns:1fr}}}}
details.ind{{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:10px 0;overflow:hidden}}
details.ind summary{{display:flex;align-items:center;gap:10px;padding:13px 16px;cursor:pointer;list-style:none;flex-wrap:wrap}}
details.ind summary::-webkit-details-marker{{display:none}}
details.ind[open] summary{{border-bottom:1px solid var(--line);background:#fbfcfe}}
.code{{font-family:ui-monospace,Menlo,monospace;font-weight:700;color:var(--acc)}}
.nm{{font-weight:600}}
.meta{{color:var(--mut);font-size:12.5px}} .meta b{{color:var(--ink)}}
.fill{{display:flex;align-items:center;gap:6px;color:var(--mut);font-size:12px;margin-left:auto}}
.fb{{width:64px;height:7px;background:#eef2f6;border-radius:4px;overflow:hidden;display:inline-block}}
.fbi{{height:100%;background:var(--acc)}}
.arw{{color:#aab6c2;transition:.2s}}
details.ind[open] .arw{{transform:rotate(180deg)}}
.indbody{{padding:16px}}
.pos p,.why p{{margin:6px 0 0;color:#2b3a48}}
.poswhy .pos,.poswhy .why{{font-size:13px;margin:0 0 12px}}
.poswhy .why{{margin-bottom:2px}}
.poswhy .pos b,.poswhy .why b{{font-size:12px;color:#5a6b7d}}
.scoreline{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:4px 0 14px;font-size:13px}}
.dbars{{display:flex;gap:14px;flex-wrap:wrap}}
.db{{display:inline-flex;align-items:center;gap:5px}}
.db i{{font-style:normal;color:var(--mut)}} .db b{{font-weight:700;min-width:14px}}
.dbtr{{display:inline-block;width:56px;height:7px;background:#eef2f6;border-radius:4px;overflow:hidden}}
.dbf{{display:block;height:100%;background:#0f62fe}}.db.na b{{color:#b0bac4}}
.panels{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}}
.panel{{border:1px solid var(--line);border-radius:12px;padding:10px 12px;background:#fcfdfe}}
.phead{{display:flex;justify-content:space-between;font-weight:700;font-size:13.5px;cursor:pointer;list-style:none;align-items:center}}
details.panel[open]>.phead{{border-bottom:1px solid var(--line);padding-bottom:6px;margin-bottom:8px}}
.phead::-webkit-details-marker{{display:none}}
.phead::after{{content:'▾';margin-left:10px;color:#aab6c2;transition:.2s;font-size:12px}}
details.panel[open]>.phead::after{{transform:rotate(180deg)}}
.phead .cov{{font-size:11.5px;color:var(--mut);font-weight:500}}
/* 抽屉内面板单列、紧凑排列 */
.drawer-inner .panels{{grid-template-columns:1fr;gap:8px}}
.indbody>*{{margin-bottom:10px}}
.indbody>*:last-child{{margin-bottom:0}}
.cell{{padding:7px 2px;border-bottom:1px dashed #eef1f5;font-size:13px}}
.cell:last-child{{border-bottom:0}}
.cellhd{{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}}
.ind{{font-weight:600;font-size:12.8px}}
.tags{{display:inline-flex;gap:4px;align-items:center}}
.tc{{font-size:10.5px;font-weight:700;border-radius:5px;padding:0 5px}}
.yr{{font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:5px;padding:0 5px}}
.ev{{margin-top:3px;color:#2b3a48}}
.urls{{display:block;margin-top:4px;font-size:12px}}
a.src{{color:var(--acc);text-decoration:none;word-break:break-all}} a.src:hover{{text-decoration:underline}}
.cell.miss{{opacity:.85}} .cell.miss .mnote{{color:#c0392b;font-size:12px;margin-left:6px}}
.cell.gap .g{{color:#b0bac4;font-size:12px;margin-left:6px}}
table.ov{{width:100%;border-collapse:collapse}} table.ov th,table.ov td{{padding:14px 14px;border-bottom:1px solid #eef2f6;font-size:13.5px;text-align:left;vertical-align:middle}}
table.ov th{{background:#f7f9fc;color:#5d6d7e;font-weight:600;white-space:nowrap}}
table.ov tbody tr{{cursor:pointer}} table.ov tbody tr:hover{{background:#f4f8ff}}
.ovc{{font-family:ui-monospace,Menlo,monospace;color:var(--acc);font-weight:600;width:56px}}
.ovs,.ovf{{text-align:center}}
.ovs b{{display:inline-block;min-width:46px;padding:3px 12px;border-radius:8px;background:#e7f6ee;color:#0f8a4d;font-weight:700;text-align:center}}
.ovr{{font-weight:600;color:#3a4a58;width:52px;text-align:center}}
.ovd{{text-align:center;color:#3a4a58;font-size:12.5px}}.ovd.na{{color:#b6c0ca}}
.ovai{{font-size:12.5px;color:#5d6d7e;line-height:1.55;max-width:540px}}
.credb{{display:inline-block;padding:3px 10px;border-radius:8px;font-size:12px;font-weight:600;white-space:nowrap}}
.cred-高{{background:#e7f6ee;color:#0f8a4d}}
.cred-中高{{background:#fdf3d7;color:#8a6d1a}}
.cred-中{{background:#fef6ec;color:#92400e}}
.cred-低{{background:#f3f4f6;color:#6b7280}}
.rk{{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600;background:#f0f4ff;color:#3b5bdb;border:1px solid #c3d0f5}}
.dsc{{font-size:11.5px;color:#3a4a58;background:#f0f5f3;border:1px solid #d8e4de;border-radius:99px;padding:1px 8px;margin-left:auto}}
.dsc.na{{color:#98a3ad;background:#f4f6f8;border-color:#e4e9ef}}
.dsc.warn{{color:#c0392b;background:#fdecea;border-color:#f2c6c0;font-weight:600;cursor:help}}
.dsc.info{{color:#8a6d1a;background:#faf5e2;border-color:#e8dbab;cursor:help}}
.warnb{{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600;background:#fdecea;color:#c0392b;border:1px solid #f2c6c0;cursor:help}}
.wmark{{color:#c0392b;font-size:12px;cursor:help}}
.flagsbox{{font-size:12.5px;margin:0 0 14px;background:#fff8f7;border:1px solid #f2d4cf;border-radius:10px;padding:10px 12px}}
.flagsbox ul{{margin:4px 0 0;padding-left:18px;color:#7c3a31}} .flagsbox li{{margin:2px 0}}
.foot{{color:var(--mut);font-size:12px;margin-top:22px;line-height:1.8}}
@media(max-width:720px){{.panels{{grid-template-columns:1fr}}}}
.scrim{{display:none;position:fixed;inset:0;background:rgba(15,34,58,.32);z-index:40}}
.scrim.open{{display:block;animation:fadeIn .18s ease-out}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
.drawer{{position:fixed;top:0;right:0;height:100vh;width:min(640px,94vw);background:var(--card);border-left:1px solid var(--line);box-shadow:-8px 0 28px rgba(15,34,58,.16);z-index:50;transform:translateX(103%);transition:transform .22s ease-out;display:flex;flex-direction:column}}
.drawer.open{{transform:translateX(0)}}
.drawer-inner{{overflow:auto;flex:1;-webkit-overflow-scrolling:touch}}
.drawer-head{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line);background:#fbfcfe;position:sticky;top:0;z-index:1}}
.dh-left{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.drawer-close{{border:1px solid var(--line);background:#fff;border-radius:8px;width:30px;height:30px;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--mut);font-size:15px;line-height:1;flex-shrink:0}}
.drawer-close:hover{{background:#f4f8ff;color:var(--ink)}}
#ov tr.active{{background:#eaf1ff}}
/* 底部完整列表中不重复显示抽屉头部，仅抽屉展开时使用 */
details.ind>.drawer-head{{display:none}}
@media(max-width:720px){{.drawer{{width:100vw;border-left:0}}}}
{v23_css}
</style></head><body><div class="wrap">
<h1>上海 70 细分行业 · 综合评分与证据库 <small>{TODAY}</small></h1>
<p class="sub">覆盖国民经济行业分类 70 个带编号细分行业；每个证据格：数字/事实 + 年份 + 来源层级(S1官方→S4转载) + 可点击出处。检索不到的格如实标注「缺沪数据」，不拿全国口径顶替。采集与评分统一按《行业评分体系》21 项指标（六大类 100 分制）。</p>
<div class="meta-card">
<span class="mc">覆盖行业 <b>{n}</b></span>
<span class="mc">评分指标 <b>21</b> 项 / 六大类</span>
<span class="mc">有证据指标 <b>{filled}/{total_core}</b>（21项中有实际证据支撑的项数，占 {filled/total_core*100:.0f}%）</span>
<span class="mc">口径 <b>仅上海</b></span>
<span class="mc">优先级 <b>S1 上海官方</b> ＞ S2 在沪行业一手 ＞ S3 权威第三方沪口径 ＞ S4 转载</span>
</div>
<div class="card"><h2>施耐德 NS 行业 × 国标行业综合排名</h2>
<div class="toolbar"><input id="q" placeholder="搜索行业、关键企业或细分方向…">
<select id="fsel" class="sel"><option value="">全部分数</option><option value="70">总分 ≥ 70</option><option value="60">总分 60–70</option><option value="0">总分 &lt; 60</option></select>
<span id="cnt" class="hint"></span></div>
<div class="weights" id="weights">
  <div class="wlbl">六大类权重调节（拖动滑杆实时重算综合分与排名；默认 20/10/20/20/20/10）</div>
  <div class="wgrid">{wgrid_html}</div>
  <div class="wtot">当前权重合计 <b id="wsum">100</b> 分 · 综合分满分即为权重合计 · <button id="wreset" class="chip" type="button">恢复默认</button></div>
</div>
<table class="ov"><thead><tr><th>排名</th><th>行业</th><th>需求</th><th>资本</th><th>供给</th><th>技术</th><th>盈利</th><th>政策</th><th>总分<br>/100</th><th>AI 摘要</th><th>证据</th><th>置信度</th></tr></thead><tbody id="ov">{ov_rows}</tbody></table>
<div id="list" style="display:none">{cards}</div>
<div id="scrim" class="scrim" onclick="closeDrawer()"></div>
<div id="drawer" class="drawer">
  <div id="drawer-inner" class="drawer-inner"></div>
</div>
<div class="foot">
<b>方法口径</b><br>
1. 每条证据 = 上海本地事实/数字 + 年份 + 来源层级 + 出处链接；来源层级：S1 上海官方（市/区统计局公报年鉴、经信委、发改委、各行业主管委办、海关上海、监管在沪单位等）→ S2 在沪行业一手（在沪上市公司年报公告、央企国企官网、上海行业协会、上海主流媒体）→ S3 权威第三方但沪口径（券商研报沪章节、招聘/创投平台沪数据）→ S4 一般转载（极少采用）。<br>
2. 「缺沪数据（原因）」＝本轮联网未检索到上海本地公开信息，宁缺勿假；个别格为「无沪上公开数据（本轮检索未覆盖）」。标 NA 的出口类指标通常因行业非出口导向。背景段若含全国口径均已标注"(全国口径)"，不计入评分。行业代码为 GB/T 4754 大类。<br>
3. <b>评分标准（行业评分体系 · 21 项指标 / 六大类 / 100 分制）</b>：六大类及权重——需求20（FAI增长4/规上企业增长3/出口增长3/下游景气度4/渗透率空间3/龙头预算增长3）、资本10（投资增长5/融资活动增长5）、供给20（工业增加值5/供给瓶颈5/行业集中度5/产能利用率5）、技术20（技术突破7/商业化成熟度7/招聘人数增长6）、盈利20（龙头企业收入增长7/利润率改善7/ROE·ROIC6）、政策10（政策提及数4/政府补贴3/国家战略支持3）。每项指标按标准<b>分档表</b>评分：增速类（&gt;30%→满分档、10–30%→次档、0–10%→中档、明显下滑→低档）、定性类按关键词分档（如供给瓶颈：严重紧缺5/局部约束4/基本平衡3/过剩1），检索不到按标准默认分（多为中档），每项评分理由见抽屉内类别面板。上方滑杆可临时调节各类权重，其余类别按比例分配、合计恒为100分。<br>
4. <b>排名平级决胜</b>：总分相同（0.1 精度）时按行业代码排序，严格 1–70 不并列。<br>
5. 采证时间 {TODAY}（评分证据以 <b>2026 年最新季度</b>为主：上半年/二季度/部分 1-7 月；被更新的历史口径留存于主库 hist 字段备查）；链接来自当轮联网检索快照，标注「栏目首页」的为部门网站入口页而非具体文章，建议点击后站内复核。本页供行业研究参考，不构成投资建议。
</div>
</div>
<script>
let list=[...document.querySelectorAll('details.ind')];
let rows=[...document.querySelectorAll('#ov tr.gbrow')];
const q=document.getElementById('q');
const fsel=document.getElementById('fsel');
const drawer=document.getElementById('drawer');
const drawerInner=document.getElementById('drawer-inner');
const scrim=document.getElementById('scrim');
function matches(d,v){{
  const txt=(d.dataset.text||'').toLowerCase();const code=d.dataset.code;
  return !v||txt.includes(v)||code===v;
}}
function scoreMatch(tr,f){{
  if(!f)return true;
  const s=parseFloat(tr.getAttribute('data-score')||0);
  if(f==='70')return s>=70;
  if(f==='60')return s>=60&&s<70;
  if(f==='0')return s<60;
  return true;
}}
function toggleNs(tr){{
  const ns=tr.dataset.ns;
  const open=tr.classList.toggle('open');
  document.querySelectorAll('tr.gbrow[data-ns="'+ns+'"]').forEach(r=>r.classList.toggle('open',open));
  const a=tr.querySelector('.arw2');if(a)a.textContent=open?'▾':'▸';
}}
function apply(){{
  const v=q.value.trim().toLowerCase();
  const f=fsel.value;
  const filtering=!!v||!!f;
  let shown=0;
  const nsVisible={{}};
  rows.forEach(tr=>{{
    const ok=matches(tr,v)&&scoreMatch(tr,f);
    if(filtering){{
      tr.style.display=ok?'':'none';
      if(ok){{shown++;nsVisible[tr.dataset.ns]=true;}}
    }}else{{
      tr.style.display='';
      const nsr=document.querySelector('tr.nsr[data-ns="'+tr.dataset.ns+'"]');
      tr.classList.toggle('open',!!(nsr&&nsr.classList.contains('open')));
    }}
  }});
  document.querySelectorAll('#ov tr.nsr').forEach(ns=>{{
    ns.style.display=(!filtering||nsVisible[ns.dataset.ns])?'':'none';
  }});
  list.forEach(d=>{{d.style.display=matches(d,v)?'':'none';}});
  document.getElementById('cnt').textContent=filtering?('命中 '+shown+' 个行业'):('显示 '+document.querySelectorAll('#ov tr.nsr').length+' 个 NS 行业 / '+new Set(rows.map(r=>r.dataset.code)).size+' 个国标行业');
}}
q.addEventListener('input',apply);
fsel.addEventListener('change',apply);
const DIMS=["需求","资本","供给","技术","盈利","政策"];
const weightInputs=[...document.querySelectorAll('#weights input[type=range][data-dim]')];
const wsum=document.getElementById('wsum');
const wreset=document.getElementById('wreset');
weightInputs.forEach(inp=>inp.dataset.last=inp.value);
function fmt(n){{return Number(n.toFixed(2)).toString();}}
function getWeights(){{return Object.fromEntries(weightInputs.map(inp=>[inp.dataset.dim,+inp.value]));}}
function updateWsum(total){{if(wsum){{const t=Number(total.toFixed(1));wsum.textContent=t;wsum.parentElement.classList.toggle('over',Math.abs(t-100)>0.5);}}}}
function innerWeights(cat){{return [...document.querySelectorAll('#subw-'+cat+' input')].map(i=>+i.value);}}
function catRatio(tr,cat){{
  const ws=innerWeights(cat);
  if(!ws.length){{const r=parseFloat(tr.getAttribute('data-dim-'+cat));return isNaN(r)?0.6:r/5;}}
  let sw=0,acc=0;
  ws.forEach((w,i)=>{{const r=parseFloat(tr.getAttribute('data-r-'+cat+'-'+i));sw+=w;acc+=w*(isNaN(r)?0.6:r);}});
  return sw>0?acc/sw:0.6;
}}
function distribute(idx,newVal){{
  const vals=weightInputs.map(inp=>+inp.value);
  vals[idx]=newVal;
  const rem=100-newVal;
  const others=weightInputs.map((_,i)=>i).filter(i=>i!==idx);
  const sum=others.reduce((s,i)=>s+vals[i],0);
  if(sum<=0){{const share=rem/others.length;others.forEach(i=>vals[i]=Math.max(0,Math.min(50,share)));}}
  else{{others.forEach((i,oi)=>{{if(oi===others.length-1)vals[i]=Math.max(0,Math.min(50,rem-others.slice(0,-1).reduce((s,j)=>s+vals[j],0)));else vals[i]=Math.max(0,Math.min(50,vals[i]*rem/sum));}});}}
  let total=vals.reduce((s,v)=>s+v,0);
  const diff=100-total;
  if(Math.abs(diff)>1e-6){{const adj=others.find(i=>i!==idx&&vals[i]+diff>=0&&vals[i]+diff<=50)||others[0];vals[adj]=Math.max(0,Math.min(50,vals[adj]+diff));total=vals.reduce((s,v)=>s+v,0);}}
  weightInputs.forEach((inp,i)=>{{inp.value=+(vals[i].toFixed(1));inp.dataset.last=inp.value;const o=document.querySelector('.wval[data-for="'+inp.dataset.dim+'"]');if(o)o.textContent=fmt(vals[i]);}});
  updateWsum(total);
}}
function recalc(){{
  const W=getWeights();
  rows.forEach(tr=>{{
    let score=0;
    DIMS.forEach((dm,i)=>{{
      const wgt=W[dm]*catRatio(tr,dm);
      score+=wgt;
      const td=tr.querySelectorAll('td.ovd')[i];
      if(td)td.textContent=fmt(wgt);
    }});
    const s=fmt(score);
    const b=tr.querySelector('td.ovs b');if(b)b.textContent=s;
    tr.setAttribute('data-score',score.toFixed(6));
  }});
  const tbody=document.getElementById('ov');
  // 国标行业全榜排名：按唯一行业代码排序（同一行业多组映射共享同一排名）
  const seenC={{}};
  const uniq=rows.filter(tr=>{{
    const c=tr.dataset.code;
    if(seenC[c])return false;
    seenC[c]=true;return true;
  }});
  uniq.sort((a,b)=>{{
    const d=+b.getAttribute('data-score')-+a.getAttribute('data-score');
    if(Math.abs(d)>1e-6)return d;
    return (+a.dataset.code||0)-(+b.dataset.code||0);
  }});
  const rankOf={{}};
  uniq.forEach((tr,i)=>{{rankOf[tr.dataset.code]=i+1;}});
  rows.forEach(tr=>{{tr.querySelector('td.ovr').textContent='#'+rankOf[tr.dataset.code];}});
  // NS 组：组内按总分排序 + NS 平均分 + 组间按平均分排序
  const groups={{}};
  rows.forEach(tr=>{{(groups[tr.dataset.ns]=groups[tr.dataset.ns]||[]).push(tr);}});
  const nsList=[...document.querySelectorAll('#ov tr.nsr')];
  nsList.forEach(ns=>{{
    const mem=groups[ns.dataset.ns]||[];
    // 六类均值：直接平均成员行已更新的类别单元格数值
    const dimTds=ns.querySelectorAll('td.nsd');
    dimTds.forEach((td,i)=>{{
      const avg=mem.reduce((s,tr)=>s+(parseFloat(tr.querySelectorAll('td.ovd')[i].textContent)||0),0)/(mem.length||1);
      td.textContent=fmt(avg);
    }});
    const avg=mem.reduce((s,tr)=>s+(+tr.getAttribute('data-score')||0),0)/(mem.length||1);
    ns.dataset.avg=avg;
    const b=ns.querySelector('.nsavg');if(b)b.textContent=fmt(avg);
  }});
  nsList.slice().sort((a,b)=>(+b.dataset.avg)-(+a.dataset.avg)).forEach((ns,i)=>{{
    ns.querySelector('td.ovr').textContent='#'+(i+1);
    tbody.appendChild(ns);
    const mem=(groups[ns.dataset.ns]||[]).slice().sort((a,b)=>{{
      const d=+b.getAttribute('data-score')-+a.getAttribute('data-score');
      if(Math.abs(d)>1e-6)return d;
      return (+a.dataset.code||0)-(+b.dataset.code||0);
    }});
    mem.forEach(tr=>tbody.appendChild(tr));
  }});
  rows=[...tbody.querySelectorAll('tr.gbrow')];
  apply();
}}
weightInputs.forEach((inp,idx)=>inp.addEventListener('input',e=>{{distribute(idx,+e.target.value);recalc();}}));
if(wreset)wreset.addEventListener('click',()=>{{
  weightInputs.forEach(inp=>{{inp.value=inp.defaultValue;inp.dataset.last=inp.defaultValue;const o=document.querySelector('.wval[data-for="'+inp.dataset.dim+'"]');if(o)o.textContent=fmt(+inp.defaultValue);}});
  updateWsum(100);recalc();
}});
function openDrawer(code){{
  const d=document.querySelector('details[data-code="'+code+'"]');
  if(!d)return;
  rows.forEach(tr=>tr.classList.toggle('active', tr.dataset.code===code));
  drawerInner.innerHTML=d.querySelector('.drawer-head').outerHTML+d.querySelector('.indbody').outerHTML;
  drawerInner.scrollTop=0;
  drawer.classList.add('open');scrim.classList.add('open');document.body.style.overflow='hidden';
}}
function closeDrawer(e){{
  if(e)e.stopPropagation();
  drawer.classList.remove('open');scrim.classList.remove('open');
  document.body.style.overflow='';rows.forEach(tr=>tr.classList.remove('active'));
}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeDrawer();}});
recalc();
</script>
</body></html>'''
    path = os.path.join(OUT, f"上海70行业多维指标证据库_{TODAY}.html")
    open(path, "w", encoding="utf-8").write(html_doc)
    print("HTML 已写:", path, round(os.path.getsize(path) / 1024, 1), "KB")

if __name__ == "__main__":
    main()
