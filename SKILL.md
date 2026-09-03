---
name: industry-evidence-dashboard
description: 地区行业多维证据库构建技能：按六维框架（需求25/供给20/盈利20/资本10/技术15/政策10）对目标地区的国民经济细分行业（GB/T 4754，默认70个大类）逐格采证、加权评分、生成带权重滑杆+右侧抽屉的单文件交互HTML证据库。当用户要求做某地区（如上海/北京/深圳）的行业分析、行业证据库、行业排名、行业景气对比，或要求刷新/合并/诊断已有证据库时使用。含评分引擎、HTML生成器、CSV四规则合并引擎与新地区适配脚本，并内置 MCP 连接器检查与用户引导流程。
agent_created: true
---

# Industry Evidence Dashboard（地区行业多维证据库）

## Overview

为任意地区构建「N 个细分行业 × 六维 19 核心指标」的逐格证据库：每格证据 = 数字/事实 + 年份 + 来源层级(S1–S4) + 具体来源链接；证据驱动打分（非主观评级），输出单文件交互 HTML（权重滑杆实时重算、右侧抽屉下钻、可折叠维度面板）。首发实现为 2026-09 上海 70 行业版，方法论与脚本已固化，跨地区复用只需适配地区词与路径。

**六维权重固定不变**：需求增长25 / 供给能力20 / 盈利质量20 / 资本进入10 / 技术成熟度15 / 政策支持10（合计100）。页面滑杆允许用户临时调节，默认值恒为上表。

## Workflow（全流程）

### Step 0｜前置检查（MCP）

按 `references/mcp-connectors.md` 执行：采证主力是 WebSearch/WebFetch；若任务需要企业/金融数据（企查查、同花顺快查、天眼查、上奇产业通、Wind 等），先用 ToolSearch 确认对应 MCP 是否已连接。**未连接的，必须通过 suggest_plugin_install 弹卡片引导用户配置**（给出连接指引文案，用户跳过则改用公开检索降级并说明覆盖差异），禁止静默跳过或编造数据。

### Step 1｜确定地区与行业清单

- 与用户确认地区、行业范围（默认 GB/T 4754 全部 70 个大类，代码为字符串如 "39"）。
- 建工作目录：`WORKDIR`（中间产物）与 `OUTDIR`（交付物）。

### Step 2｜适配脚本到新地区

```bash
bash <skill_dir>/scripts/adapt_region.sh <OUTDIR> <WORKDIR> <地区名> <简称> [日期]
# 例: bash .../adapt_region.sh ~/WorkBuddy/ws/outputs /tmp/bj_work 北京 京
```

该脚本把三个核心脚本复制到 WORKDIR 并完成路径与地区词替换（沪上/在沪/沪口径→本地；沪→简称；上海→地区名；输出路径与日期）。适配后**通读一遍**脚本顶部配置；若行业数非 70，全局替换相关字样与统计口径。

### Step 3｜采证（并行子代理）

按 `references/evidence-sources.md` 的检索配方与子代理 prompt 模板，派发多个采证子代理（每批 10–15 个行业），产出统一 12 列 CSV。硬性口径：只收本地数据、全国数据标"全国口径"、缺格如实标"缺{简称}数据（原因）"、URL 必须是具体来源页。宏观指数（PMI/EPMI/PPI/FAI 等）单独写入 `WORKDIR/macro_indices.json`（对照展示，不评分）。

### Step 4｜建主库并合并

- 首建：按 `references/data-schema.md` 把采证结果组装成主库 JSON（`{地区}70行业指标证据_数据_{日期}.json`）。
- 增量合并：`python3 WORKDIR/merge_evidence_csv.py`（四规则 R1缺格创建/R2 miss转正/R3择新替换/R4 hist补充；自动备份主库）。合并脚本顶部的 MAIN/CSVF 路径按需修改。

### Step 5｜评分

```bash
python3 WORKDIR/rescore_evidence.py
```

评分算法、单向信号权衡、排名决胜规则详见 `references/methodology.md`（固定口径，勿随地区改动）。脚本写出 dimscores/dim_weighted/score100/rank 等字段并同步 `WORKDIR/evidence_recs.json`。

### Step 6｜生成交付物

```bash
python3 WORKDIR/gen_evidence_html.py
```

产出单文件 HTML（约 2MB，无外部依赖）：综合排名总表（点击行→右侧抽屉）、六维权重滑杆（合计锁100、其余维度按比例分配、恢复默认按钮）、搜索、可折叠维度面板、宏观指数对照面板、"沪上产业形态与背景·原分析师早期判断"合并面板、缺格/权衡标注。

### Step 7｜验证（必做）

- JS 语法：提取 `<script>` 内容用 `node --check` 校验（f-string 双大括号转义易错，每次改生成器后必查）。
- grep 抽查：行业卡数量、新证据关键词出现次数、旧区块零残留、`<output>`/被删列残留为 0。
- 评分合理性：Top/Bottom 与常识对照；有疑问的行业按 methodology.md「排名偏差诊断手册」排查。
- 最后用 present_files 交付 HTML。

## 常见迭代操作

| 需求 | 做法 |
|---|---|
| 补充新证据（CSV） | 四规则合并（Step 4）→ rescore → 重新生成 HTML |
| 单行业排名偏低质疑 | 先复现 cell_sign_w 判定 → 看每维票数是否触发"单向弱正"强收缩 → 首选补稀疏维度证据，其次才考虑算法微调（全量重算+前后对照，±10 分内变动为健康） |
| 链接是官网首页 | 取 ev 关键数字做 site: 检索替换为具体页；找不到保留并自动标"栏目首页" |
| 刷新最新季度数据 | R3 择新替换，旧证据入 hist；宏观指数同步更新 macro_indices.json |

## Resources

### scripts/
- `rescore_evidence.py` — 评分引擎：cell_sign_w（方向+票数+强信号加权）→ dim_score（向中性收缩+单向权衡）→ score100/rank。读主库写回。
- `gen_evidence_html.py` — HTML 生成器：抽屉/滑杆/折叠面板/宏观映射全在此，577 行，上海版参考实现。
- `merge_evidence_csv.py` — CSV 四规则合并引擎（ALIAS 别名、TO_SUPP、T1→S1、hist 去重）。
- `adapt_region.sh` — 新地区适配：复制+sed 替换路径与地区词。

### references/
- `data-schema.md` — 主库 JSON 结构、cell 字段、维度双轨命名（完整名 vs 2字名，易错）、CSV 格式。
- `methodology.md` — 权重（固定）、评分算法细节、排名偏差诊断手册、四规则、链接卫生。
- `evidence-sources.md` — 采证检索配方、子代理 prompt 模板、来源层级实例、质量红线。
- `mcp-connectors.md` — MCP 清单、连接检查流程、未连接时的弹窗引导规范。

## 关键经验（首发踩坑记录）

1. cells 的 dim 用 2 字名、dimscores 用完整名，两套必须同步（DIM_CELL）。
2. f-string 写 JS 时所有字面 `{{ }}` 需双写，改完必跑 node --check。
3. 官网首页占位链接是原始 CSV 通病，采证 prompt 里必须明令禁止。
4. 证据少的行业会被"单向弱正"收缩压分（结构性行为），诊断手册有完整流程。
5. `#list` 底部卡片区保留但 `display:none`——右侧抽屉从那里克隆内容，删 DOM 会坏抽屉。
6. 主库任何写操作前先备份（`cp` 到 WORKDIR），评分快照存 `rank_before.json` 供前后对照。
