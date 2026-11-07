"""Export slide text, native tables, chart values and speaker notes from the deck to slides.md.

Standard library only. Run from the repository root:
    python3 docs/final/source/extract_slides.py
"""
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

FINAL = Path(__file__).resolve().parents[1]
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
FOOTER = ('SkyRoute v2 · 合成数据实验',)


def text(element):
    out = []
    for paragraph in element.findall('.//a:p', NS):
        out.append(''.join(node.text or '' for node in paragraph.iter('{%s}t' % NS['a'])))
    return '\n'.join(p for p in out if p.strip()).strip()


def table(rows):
    rows = [[v.replace('|', '\\|').replace('\n', '<br>') for v in row] for row in rows]
    return '\n'.join(['| ' + ' | '.join(rows[0]) + ' |', '| ' + ' | '.join(['---'] * len(rows[0])) + ' |'] +
                     ['| ' + ' | '.join(r) + ' |' for r in rows[1:]])


def slide_order(z):
    pres = ET.fromstring(z.read('ppt/presentation.xml'))
    rels = ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'))
    targets = {r.attrib['Id']: r.attrib['Target'] for r in rels}
    return [posixpath.basename(targets[s.attrib['{%s}id' % NS['r']]])
            for s in pres.find('p:sldIdLst', NS)]


def main():
    lines = ['# SkyRoute v2 逐页展示文字与讲稿',
             '由 `docs/final/source/extract_slides.py` 从 `SkyRoute-presentation.pptx` 的可编辑对象与备注生成；'
             '图表列出实际数值。修改请编辑 `build_slides.cjs` 后重新构建。']
    with ZipFile(FINAL / 'SkyRoute-presentation.pptx') as z:
        for n, name in enumerate(slide_order(z), start=1):
            slide = ET.fromstring(z.read('ppt/slides/' + name))
            shapes = slide.findall('.//p:spTree/p:sp', NS)
            title, presenter, body = None, '', []
            for sh in shapes:
                ph = sh.find('.//p:nvPr/p:ph', NS)
                value = text(sh)
                named = sh.find('.//p:cNvPr', NS)
                if (ph is not None and ph.attrib.get('type') == 'title') or (
                        named is not None and named.attrib.get('name') == 'slide-title'):
                    title = value
                elif ph is not None and ph.attrib.get('type') == 'body':
                    presenter = value
                elif ph is not None and ph.attrib.get('type') == 'sldNum':
                    continue
                elif value and value not in FOOTER and not re.fullmatch(r'\d+', value):
                    body.append(value)
            if title is None and body:
                title = body.pop(0)
            lines.append(f'## 第{n}页 · {title}' + (f'（{presenter}）' if presenter else ''))
            lines.append('### 展示文字')
            lines.extend(b.replace('\n', '\n\n') for b in body)
            for t in slide.findall('.//a:tbl', NS):
                lines.append(table([[text(c) for c in r.findall('a:tc', NS)] for r in t.findall('a:tr', NS)]))
            rels = ET.fromstring(z.read(f'ppt/slides/_rels/{name}.rels'))
            targets = {r.attrib['Id']: r.attrib['Target'] for r in rels}
            for ref in slide.findall('.//c:chart', NS):
                target = targets[ref.attrib['{%s}id' % NS['r']]]
                path = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('ppt/slides', target))
                chart = ET.fromstring(z.read(path))
                series = chart.findall('.//c:ser', NS)
                labels = [v.text for v in series[0].findall('c:cat//c:pt/c:v', NS)]
                names = [(s.find('c:tx//c:v', NS).text if s.find('c:tx//c:v', NS) is not None else '') for s in series]
                values = [[v.text for v in s.findall('c:val//c:pt/c:v', NS)] for s in series]
                lines.append('图表数据：\n\n' + table([['类别'] + names] + [[lab] + [v[j] for v in values]
                                                                       for j, lab in enumerate(labels)]))
            notes_name = None
            for r in rels:
                if r.attrib['Type'].endswith('/notesSlide'):
                    notes_name = posixpath.basename(r.attrib['Target'])
            if notes_name:
                notes = ET.fromstring(z.read('ppt/notesSlides/' + notes_name))
                body_text = [text(sh) for sh in notes.findall('.//p:sp', NS)
                             if (sh.find('.//p:nvPr/p:ph', NS) is not None
                                 and sh.find('.//p:nvPr/p:ph', NS).attrib.get('type') == 'body')]
                lines.extend(['### 讲稿与来源', '\n\n'.join(b for b in body_text if b)])
    (FINAL / 'slides.md').write_text('\n\n'.join(lines) + '\n', encoding='utf-8')
    print(FINAL / 'slides.md')


if __name__ == '__main__':
    main()
