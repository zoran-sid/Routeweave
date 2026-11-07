"""Build the SkyRoute v2 report: chart data from member results -> XeLaTeX PDF -> Markdown mirror.

Requirements: TeX Live with ctex/xeCJK, TikZ and pgfplots (XeLaTeX via latexmk); pandoc for the mirror.

python3 docs/final/source/build_report.py            # data + PDF + report.md + character count
python3 docs/final/source/build_report.py --data     # chart data only
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = Path(__file__).resolve().parent / "report"
DATA = SRC / "data"
FINAL = ROOT / "docs/final"
RES = {
    "op_a": ROOT / "docs/modules/yht/v2/experiments/results/op_a_index_comparison.json",
    "storage": ROOT / "docs/modules/zqo/v2/experiments/results/transactions-storage.json",
    "access": ROOT / "docs/modules/zc/v2/experiments/results/access_paths.json",
    "inval": ROOT / "docs/modules/zc/v2/experiments/results/invalidation.json",
}


def load(key):
    return json.loads(RES[key].read_text(encoding="utf-8"))


def write(name, header, rows):
    DATA.mkdir(parents=True, exist_ok=True)
    lines = [" ".join(header)] + [" ".join(str(v) for v in r) for r in rows]
    (DATA / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def chart_data():
    # YHT operation A: median us per access path, by restrictions per release (K = 1 and 20)
    op = load("op_a")["results"]
    for k in (1, 20):
        rows = []
        for n in (100, 1000, 10000):
            v = {r["variant"]: r["median_us"] for r in op if r["n_per_release"] == n and r["releases"] == k}
            rows.append([n, v["V0_full_scan"], v["V1_release_btree"], v["V2_time_btree"], v["V3_rtree_3d"], v["V4_rtree_4d"]])
        write(f"op_a_k{k}.dat", ["n", "full", "release", "time", "rtree3", "rtree4"], rows)
    # ZQO storage: MiB by number of releases
    st = load("storage")["storage"]
    rows = []
    for n in (10, 100, 1000):
        sh = next(s for s in st if s["mode"] == "shared" and s["releases"] == n)["db_bytes"] / 2**20
        fu = next(s for s in st if s["mode"] == "full" and s["releases"] == n)["db_bytes"] / 2**20
        rows.append([n, round(sh, 2), round(fu, 2)])
    write("storage.dat", ["n", "shared", "full"], rows)
    # ZC access paths: median ms per stage
    rows = []
    for s in load("access")["scales"]:
        m = s["summary"]
        rows.append([s["n_buildings"], m["json_snapshot"]["data_ms"], m["sql_full"]["data_ms"], m["sql_rtree"]["data_ms"],
                     m["sql_rtree"]["search_ms"], m["graph_cache"]["miss_build_ms"], m["graph_cache"]["hit_total_ms"]])
    write("access.dat", ["n", "json", "full", "rtree", "search", "build", "hit"], rows)
    # ZC invalidation: total ms, full vs targeted
    rows = [[i, round(t["full_rebuild_ms"], 1), round(t["targeted_ms"], 1)]
            for i, t in enumerate(load("inval")["transitions"])]
    write("inval.dat", ["i", "full", "targeted"], rows)


def hanzi(tex):
    """Count Han characters in the body: abstract through chapter 9, without references and appendices."""
    body = tex.split(r"\begin{abstract}", 1)[1]
    body = body.split(r"\begin{thebibliography}", 1)[0]
    body = re.sub(r"(?s)\\begin\{(tikzpicture|axis)\}.*?\\end\{\1\}", "", body)
    return len(re.findall(r"[一-鿿]", body))


def labels():
    aux = (SRC / "report.aux").read_text(encoding="utf-8")
    return {k: v for k, v in re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux)}


def for_pandoc(tex):
    """Make the LaTeX source digestible for pandoc: real numbers, plain tables, no cover block."""
    lab = labels()
    tex = re.sub(r"~?\\ref\{([^}]+)\}", lambda m: lab.get(m.group(1), "?"), tex)
    aux = (SRC / "report.aux").read_text(encoding="utf-8")
    bib = dict(re.findall(r"\\bibcite\{([^}]+)\}\{(\d+)\}", aux))
    tex = re.sub(r"\s?\\cite\{([^}]+)\}",
                 lambda m: "[" + ", ".join(bib.get(k.strip(), "?") for k in m.group(1).split(",")) + "]", tex)
    start = tex.index(r"\maketitle")
    tex = tex[:start] + tex[tex.index(r"\clearpage", start) + len(r"\clearpage"):]
    tex = tex.replace(r"\begin{abstract}", r"\section*{摘要}").replace(r"\end{abstract}", "")
    tex = tex.replace(r"\tableofcontents", "")

    def plain(m):
        spec = m.group(1)
        cols = len(re.findall(r"[LpY]\{?|(?<![a-z])[lcrX](?![a-z])", re.sub(r"\{[^{}]*\}", "", spec)))
        return r"\begin{tabular}{" + "l" * cols + "}"
    tex = re.sub(r"\\begin\{tabularx\}\{\\textwidth\}\{([^\n]*)\}\s*$", plain, tex, flags=re.M)
    tex = tex.replace(r"\end{tabularx}", r"\end{tabular}")
    tex = re.sub(r"(?s)\\resizebox\{\\textwidth\}\{!\}\{%.*?\\end\{tikzpicture\}\}", "（图形见 PDF）", tex)
    tex = re.sub(r"(?s)\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", "（图形见 PDF）", tex)
    tex = re.sub(r"\\caption\{", lambda m: m.group(0), tex)
    return tex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="store_true")
    args = ap.parse_args()
    chart_data()
    if args.data:
        return
    tex = (SRC / "report.tex").read_text(encoding="utf-8")
    subprocess.run(["latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error", "-quiet", "report.tex"],
                   cwd=SRC, check=True)
    shutil.copy2(SRC / "report.pdf", FINAL / "SkyRoute-report.pdf")
    md = subprocess.run(["pandoc", "-f", "latex", "-t", "gfm", "--wrap=none"], input=for_pandoc(tex), cwd=SRC,
                        capture_output=True, text=True, check=True).stdout
    header = ("<!-- 由 docs/final/source/report/report.tex 自动生成，供阅读和检索；图、表编号与 PDF 一致，"
              "图形见 SkyRoute-report.pdf。修改请编辑 report.tex 后运行 python3 docs/final/source/build_report.py。 -->\n\n"
              "# SkyRoute：面向城市无人机配送的时空数据管理系统设计\n\n"
              "**SkyRoute: Spatio-temporal Data Management for Urban UAV Delivery**　INT6164 课程大作业小组报告，v2.0\n\n")
    (FINAL / "report.md").write_text(header + md, encoding="utf-8")
    pdf = FINAL / "SkyRoute-report.pdf"
    pages = subprocess.run(["gs", "-q", "-dNODISPLAY", "-dNOSAFER", "-c",
                            f"({pdf}) (r) file runpdfbegin pdfpagecount = quit"],
                           capture_output=True, text=True).stdout.strip()
    print(json.dumps({"hanzi_body": hanzi(tex), "pages": pages}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
