#!/usr/bin/env bash
# 将 skill 内的"上海版"三个核心脚本适配为任意地区版本，复制到目标工作目录。
#
# 用法:
#   adapt_region.sh <OUTDIR> <WORKDIR> <REGION_NAME> <REGION_ABBR> [DATE]
# 示例（北京）:
#   adapt_region.sh /Users/x/WorkBuddy/ws/outputs /tmp/beijing_work 北京 京 2026-09-03
#
# 参数:
#   OUTDIR       最终交付物（主库JSON/HTML/CSV）输出目录
#   WORKDIR      中间工作目录（evidence_recs.json / macro_indices.json / 备份）
#   REGION_NAME  地区全名，如 北京 / 深圳 / 苏州（替换"上海"）
#   REGION_ABBR  地区单字简称，如 京 / 深（替换"沪"，"缺沪数据"→"缺京数据"）
#   DATE         数据日期，默认当天（YYYY-MM-DD）
#
# 说明:
#   - "沪上/在沪/沪口径" 统一替换为"本地"措辞，避免"粤上产业形态"这类不通顺输出
#   - 行业代码采用 GB/T 4754 全国大类，跨地区通用，脚本中的行业分组无需修改
#   - 适配后必须先通读一遍脚本确认，再投入采证流程

set -euo pipefail

OUTDIR="${1:?用法: adapt_region.sh <OUTDIR> <WORKDIR> <REGION_NAME> <REGION_ABBR> [DATE]}"
WORKDIR="${2:?缺少 WORKDIR}"
REGION="${3:?缺少 REGION_NAME，如 北京}"
ABBR="${4:?缺少 REGION_ABBR，如 京}"
DATE="${5:-$(date +%F)}"

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUTDIR" "$WORKDIR"

for f in rescore_evidence.py gen_evidence_html.py merge_evidence_csv.py; do
  sed -e "s|/Users/yihanran/WorkBuddy/2026-09-02-15-38-53/outputs|${OUTDIR}|g" \
      -e "s|/tmp/refresh2026/macro_indices.json|${WORKDIR}/macro_indices.json|g" \
      -e "s|/tmp/refresh2026/master_bak_pre_fullmerge.json|${WORKDIR}/master_bak.json|g" \
      -e "s|/tmp/evidence_recs.json|${WORKDIR}/evidence_recs.json|g" \
      -e "s|/tmp/evidence_recs_bak_urlcleanup.json|${WORKDIR}/evidence_recs_bak.json|g" \
      -e "s|2026-09-02|${DATE}|g" \
      -e "s|TODAY = \"${DATE}\"|TODAY = \"${DATE}\"|" \
      -e "s|沪上|本地|g" \
      -e "s|在沪|在本地|g" \
      -e "s|沪口径|本地口径|g" \
      -e "s|沪|${ABBR}|g" \
      -e "s|上海|${REGION}|g" \
      "$SKILL_DIR/$f" > "$WORKDIR/$f"
done

# 宏观指数文件（可选；缺失时 HTML 生成器自动跳过宏观面板）
[ -f "$WORKDIR/macro_indices.json" ] || echo '[]' > "$WORKDIR/macro_indices.json"

echo "已适配 ${REGION}（简称${ABBR}）版脚本 → $WORKDIR/"
echo "  OUTDIR=$OUTDIR  DATE=$DATE"
echo "下一步:"
echo "  1. 通读 $WORKDIR/gen_evidence_html.py 顶部 CONFIG（OUT/TODAY/路径/地区词）"
echo "  2. 若行业数量非 70，全局替换 '70 行业/70行业' 字样与统计口径"
echo "  3. 按 SKILL.md 工作流采证建库"
