"""Export native slide text, tables, chart caches, and notes to Markdown."""
from pathlib import Path
import posixpath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

def text(element):
    paragraphs = []
    for paragraph in element.findall('.//a:p', NS):
        parts = []
        for node in paragraph.iter():
            if node.tag == '{'+NS['a']+'}t': parts.append(node.text or '')
            if node.tag == '{'+NS['a']+'}br': parts.append('\n')
        paragraphs.append(''.join(parts))
    return '\n'.join(paragraphs).strip()

def table(rows):
    rows = [[value.replace('|', '\\|').replace('\n', '<br>') for value in row] for row in rows]
    return '\n'.join(['| '+' | '.join(rows[0])+' |',
                      '| '+' | '.join(['---']*len(rows[0]))+' |']+
                     ['| '+' | '.join(row)+' |' for row in rows[1:]])

lines = ['# SkyRoute 逐页展示文字与讲稿',
         '2026-11-06整合稿。内容从本目录PPTX的可编辑对象及备注提取，图表列出实际缓存数值。展示顺序为ZQO、YHT、LQ、ZC、LJ，每人2页。']
with ZipFile(ROOT/'SkyRoute-presentation.pptx') as z:
    for i in range(1, 11):
        slide = ET.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
        shapes = slide.findall('.//p:spTree/p:sp', NS)
        title = text(shapes[0])
        owner = ['ZQO','YHT','LQ','ZC','LJ'][(i-1)//2]
        lines.extend([f'## 第{i}页 · {owner} · {title}', '### 展示文字'])
        for shape in shapes[1:]:
            value = text(shape)
            if value and not value.startswith('SkyRoute   ') and value != str(i):
                lines.append(value.replace('\n', '\n\n'))
        for native_table in slide.findall('.//a:tbl', NS):
            lines.append(table([[text(cell) for cell in row.findall('a:tc',NS)]
                                for row in native_table.findall('a:tr',NS)]))
        relationships = ET.fromstring(z.read(f'ppt/slides/_rels/slide{i}.xml.rels'))
        targets = {rel.attrib['Id']: rel.attrib['Target'] for rel in relationships}
        for chart_ref in slide.findall('.//c:chart', NS):
            target = targets[chart_ref.attrib['{'+NS['r']+'}id']]
            chart_path = posixpath.normpath(posixpath.join('ppt/slides',target)).lstrip('/')
            chart = ET.fromstring(z.read(chart_path))
            series = chart.findall('.//c:ser',NS)
            labels = [node.text for node in series[0].findall('c:cat//c:pt/c:v',NS)]
            names = [node.find('c:tx/c:v',NS).text for node in series]
            values = [[node.text for node in item.findall('c:val//c:pt/c:v',NS)] for item in series]
            lines.append(table([['场景／扩展节点数']+names]+
                               [[label]+[v[j] for v in values] for j,label in enumerate(labels)]))
        notes = ET.fromstring(z.read(f'ppt/notesSlides/notesSlide{i}.xml'))
        lines.extend(['### 讲稿与来源', text(notes)])
(ROOT/'slides.md').write_text('\n\n'.join(lines)+'\n')
print(ROOT/'slides.md')
