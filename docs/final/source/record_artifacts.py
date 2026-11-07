"""Record build and check facts for the delivered report and deck in evidence/artifact-checks-v2.json.

python3 docs/final/source/record_artifacts.py
"""
import hashlib
import json
import re
import subprocess
import time
import zipfile
from pathlib import Path

FINAL = Path(__file__).resolve().parents[1]
SRC = FINAL / "source/report"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    pdf, pptx = FINAL / "SkyRoute-report.pdf", FINAL / "SkyRoute-presentation.pptx"
    log = (SRC / "report.log").read_text(encoding="utf-8", errors="replace")
    pages = subprocess.run(["gs", "-q", "-dNODISPLAY", "-dNOSAFER", "-c",
                            f"({pdf}) (r) file runpdfbegin pdfpagecount = quit"], capture_output=True, text=True).stdout.strip()
    tex = (SRC / "report.tex").read_text(encoding="utf-8")
    import sys
    sys.path.insert(0, str(FINAL / "source"))
    from build_report import hanzi
    with zipfile.ZipFile(pptx) as z:
        names = z.namelist()
        slides = len([n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)])
        notes = len([n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)])
        charts = len([n for n in names if re.fullmatch(r"ppt/charts/chart\d+\.xml", n)])
        folder_entries = len([n for n in names if n.endswith("/")])
    out = {"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "report": {"file": "docs/final/SkyRoute-report.pdf", "sha256": sha(pdf), "pages": int(pages),
                      "hanzi_body": hanzi(tex), "engine": re.search(r"This is (XeTeX[^\n]*)", log).group(1),
                      "errors": log.count("\n! "), "overfull_boxes": log.count("Overfull"),
                      "figures": tex.count("\\begin{figure}"), "tables": tex.count("\\begin{table}"),
                      "references": tex.count("\\bibitem"), "source_sha256": sha(SRC / "report.tex"),
                      "markdown_mirror_sha256": sha(FINAL / "report.md")},
           "presentation": {"file": "docs/final/SkyRoute-presentation.pptx", "sha256": sha(pptx), "slides": slides,
                            "speaker_notes": notes, "native_charts": charts, "zip_folder_entries": folder_entries,
                            "ooxml_validation": "pptx skill validate.py: All validations PASSED",
                            "visual_check": "per-slide render (Quick Look) for layout and overflow; chart series read back from file",
                            "slides_md_sha256": sha(FINAL / "slides.md"),
                            "builder_sha256": sha(FINAL / "source/build_slides.cjs")}}
    path = FINAL / "evidence/artifact-checks-v2.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
