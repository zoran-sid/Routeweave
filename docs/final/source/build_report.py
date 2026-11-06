"""Build the report from its Markdown source. Requires python-docx and Pillow."""
from pathlib import Path
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT

ROOT = Path(__file__).resolve().parents[1]
doc = Document()
sec=doc.sections[0]
sec.page_width=Inches(8.5); sec.page_height=Inches(11)
sec.top_margin=sec.bottom_margin=Inches(.72)
sec.left_margin=sec.right_margin=Inches(.8)
sec.header_distance=sec.footer_distance=Inches(.32)
for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Heading 3','Caption']:
    st=doc.styles[name];st.font.name='Arial';st.font.color.rgb=RGBColor(0,0,0)
    st.element.get_or_add_rPr().append(OxmlElement('w:rFonts')) if st.element.rPr.rFonts is None else None
    fonts=st.element.rPr.rFonts
    for key in list(fonts.attrib):
        if 'theme' in key.lower(): del fonts.attrib[key]
    for key in ('ascii','hAnsi','cs'): fonts.set(qn('w:'+key),'Arial')
    fonts.set(qn('w:eastAsia'),'Songti SC' if name in ['Normal','Caption'] else 'Heiti SC')
    for border in list(st.element.xpath('.//w:pBdr')): border.getparent().remove(border)
    st.paragraph_format.space_after=Pt(6)
    st.paragraph_format.line_spacing=1.25
doc.styles['Normal'].font.size=Pt(11)
doc.styles['Title'].font.size=Pt(22)
doc.styles['Title'].paragraph_format.space_after=Pt(12)
doc.styles['Subtitle'].font.size=Pt(10.5)
doc.styles['Subtitle'].font.italic=False
for name,size in [('Heading 1',16),('Heading 2',12.5),('Heading 3',11.5)]:
    doc.styles[name].font.size=Pt(size)
    doc.styles[name].font.bold=True
    doc.styles[name].paragraph_format.space_before=Pt(14)
    doc.styles[name].paragraph_format.keep_with_next=True
doc.styles['Caption'].font.size=Pt(9)
doc.styles['Caption'].paragraph_format.space_after=Pt(9)
head=sec.header.paragraphs[0];head.text='SkyRoute  城市三维航线规划与数据管理'
head.style=doc.styles['Caption']
foot=sec.footer.paragraphs[0];foot.alignment=WD_ALIGN_PARAGRAPH.CENTER
r=foot.add_run();f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),'PAGE');r._r.addnext(f)

def clean(s):
    s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1',s)
    return s.replace('**','').replace('`','').replace('  ',' ')

def table(rows):
    t=doc.add_table(rows=1,cols=len(rows[0]));t.alignment=WD_TABLE_ALIGNMENT.CENTER
    t.autofit=False
    available=6.9
    n=len(rows[0]); widths=([1.3,2.7,2.9] if n==3 else [1.25,1.85,1.85,1.95]) if n in (3,4) else [available/n]*n
    for c,w in zip(t.columns,widths):c.width=Inches(w)
    for i,row in enumerate(rows):
        cells=t.rows[0].cells if i==0 else t.add_row().cells
        for j,val in enumerate(row):
            c=cells[j];c.width=Inches(widths[j]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p=c.paragraphs[0];p.paragraph_format.space_after=Pt(3);p.paragraph_format.space_before=Pt(3);p.paragraph_format.line_spacing=1.15
            r=p.add_run(clean(val));r.font.size=Pt(10);r.bold=i==0
            r._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'Heiti SC') if r._element.rPr.rFonts is not None else None
            pr=c._tc.get_or_add_tcPr()
            shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'DDE8F0' if i==0 else ('F6F8FA' if i%2==0 else 'FFFFFF'));pr.append(shade)
            margins=OxmlElement('w:tcMar')
            for edge,v in [('top',75),('bottom',75),('left',90),('right',90)]:
                el=OxmlElement('w:'+edge);el.set(qn('w:w'),str(v));el.set(qn('w:type'),'dxa');margins.append(el)
            pr.append(margins)
            borders=OxmlElement('w:tcBorders')
            for edge in ['top','left','bottom','right']:
                el=OxmlElement('w:'+edge);el.set(qn('w:val'),'single');el.set(qn('w:sz'),'4');el.set(qn('w:color'),'D9D9D9');borders.append(el)
            pr.append(borders)
        trpr=t.rows[i]._tr.get_or_add_trPr();trpr.append(OxmlElement('w:cantSplit'))
        if i==0:trpr.append(OxmlElement('w:tblHeader'))
    doc.add_paragraph().paragraph_format.space_after=Pt(0)

lines=(ROOT/'report.md').read_text().splitlines();i=0;code=False
while i<len(lines):
    line=lines[i]
    if line.startswith('```'):code=not code;i+=1;continue
    if not line.strip():i+=1;continue
    if code:
        p=doc.add_paragraph();r=p.add_run(line);r.font.name='Courier New';r.font.size=Pt(8)
        p.paragraph_format.space_after=Pt(1);i+=1;continue
    if line.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].startswith('|'):
            row=[x.strip() for x in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r'[-: ]+',x) for x in row):rows.append(row)
            i+=1
        table(rows);continue
    image=re.fullmatch(r'!\[.*?\]\((.*?)\)',line)
    if image:
        p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.keep_with_next=True
        p.add_run().add_picture(str(ROOT/image[1]),width=Inches(6.8));i+=1;continue
    if line.startswith('# '):
        p=doc.add_paragraph(style='Title')
        p.add_run('SkyRoute\n').font.size=Pt(26)
        p.add_run(clean(line[2:]).removeprefix('SkyRoute ').replace('无人机物流配送', '无人机物流配送\n')).font.size=Pt(18)
    elif line.startswith('### '):doc.add_paragraph(clean(line[4:]),'Heading 2')
    elif line.startswith('## '):doc.add_paragraph(clean(line[3:]),'Heading 1')
    elif line.startswith('图') and re.match(r'图\d',line):doc.add_paragraph(clean(line),'Caption')
    else:
        p=doc.add_paragraph(clean(line))
        if line.startswith('SkyRoute Urban'):p.style='Subtitle'
        if re.match(r'^\[\d+\]',line):
            p.paragraph_format.line_spacing=1.1
            for r in p.runs:r.font.size=Pt(9)
    i+=1
doc.core_properties.title='SkyRoute 面向城市复杂三维环境的无人机物流配送航线规划与数据管理设计'
doc.core_properties.author='SkyRoute Team'
doc.core_properties.subject='Database systems group project'
out=ROOT/'SkyRoute-report.docx';doc.save(out)
print(out)
