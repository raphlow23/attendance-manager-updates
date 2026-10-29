"""Fill the supplied expense form without rewriting its styles or print package.

The blank template is authored/verified at build time. Runtime uses only the
Python standard library, preserving template XML parts and printer settings.
"""
import calendar
import base64
import copy
import io
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
C='http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('',S);ET.register_namespace('r',R)
NS={'s':S}
TEMPLATE=None  # The user's private reference is selected locally, never shipped.

def read_xml(data):
    mapping={prefix:uri for _,(prefix,uri) in ET.iterparse(io.BytesIO(data),events=['start-ns'])}
    for prefix,uri in mapping.items():
        if prefix and not re.fullmatch(r'ns\d+',prefix):ET.register_namespace(prefix,uri)
    root=ET.fromstring(data)
    ignored=root.get('{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable','').split()
    for prefix in ignored:
        uri=mapping.get(prefix)
        used=uri and any(e.tag.startswith('{'+uri+'}') or any(a.startswith('{'+uri+'}') for a in e.attrib) for e in root.iter())
        if uri and not used:root.set('xmlns:'+prefix,uri)
    return root

def month_date(month):
    if not isinstance(month,str) or not re.fullmatch(r'\d{4}-\d{2}',month):raise ValueError('조회 월을 확인하세요.')
    return date.fromisoformat(month+'-01')

def export_filename(month):
    d=month_date(month)
    return f'{d.year} 출장비지급내역({d.month}월)_.xlsx'

def clock(text):
    if not isinstance(text,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',text):raise ValueError('출장 시각을 HH:MM으로 확인하세요.')
    h,m=map(int,text.split(':'));return h*60+m

def cell(root,address,value=None,formula=None,cached=None):
    node=root.find(f'.//s:sheetData/s:row/s:c[@r="{address}"]',NS)
    if node is None:
        number=int(re.search(r'\d+',address).group())
        data=root.find('s:sheetData',NS)
        row=data.find(f's:row[@r="{number}"]',NS)
        if row is None:raise ValueError('엑셀 양식의 입력 행을 확인하세요.')
        node=ET.Element(f'{{{S}}}c',r=address)
        def column(a):
            n=0
            for char in re.match(r'[A-Z]+',a).group():n=n*26+ord(char)-64
            return n
        place=next((i for i,c in enumerate(row) if column(c.get('r','A1'))>column(address)),len(row))
        row.insert(place,node)
    for child in list(node):node.remove(child)
    node.attrib.pop('t',None)
    if formula is not None:
        ET.SubElement(node,f'{{{S}}}f').text=formula.lstrip('=')
        if isinstance(cached,str):node.set('t','str')
        ET.SubElement(node,f'{{{S}}}v').text=str(cached if cached is not None else '')
    elif value is not None and value!='':
        if isinstance(value,str):
            node.set('t','inlineStr');t=ET.SubElement(ET.SubElement(node,f'{{{S}}}is'),f'{{{S}}}t')
            t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=value
        else:ET.SubElement(node,f'{{{S}}}v').text=str(value)

def xml(root):
    # OPC content types and relationship documents use their own default ns.
    namespace=root.tag[1:].split('}',1)[0] if root.tag.startswith('{') else S
    ET.register_namespace('',namespace)
    try:return ET.tostring(root,encoding='utf-8',xml_declaration=True)
    finally:ET.register_namespace('',S)

def prepare_local_parts(parts):
    """Use a private original directly; discard unused historical string data."""
    book=read_xml(parts['xl/workbook.xml'])
    if len(book.find('s:sheets',NS))!=1:raise ValueError('제공된 출장비 지급내역서 원본 양식을 선택하세요. (단일 시트 양식)')
    root=read_xml(parts['xl/worksheets/sheet1.xml'])
    strings=list(ET.fromstring(parts['xl/sharedStrings.xml'])) if 'xl/sharedStrings.xml' in parts else []
    for c in root.findall('.//s:c',NS):
        if c.get('t')=='s':
            item=strings[int(c.find('s:v',NS).text)]
            for child in list(c):c.remove(child)
            c.set('t','inlineStr');inline=ET.SubElement(c,f'{{{S}}}is')
            for child in item:inline.append(copy.deepcopy(child))
    title=root.find('.//s:c[@r="A1"]',NS)
    if title is None or re.sub(r'\s+','',''.join(title.itertext()))!='출장비지급내역서':raise ValueError('제공된 출장비 지급내역서 양식을 선택하세요.')
    parts['xl/worksheets/sheet1.xml']=xml(root)
    parts.pop('xl/sharedStrings.xml',None);parts.pop('xl/calcChain.xml',None)
    for key in ['xl/_rels/workbook.xml.rels','[Content_Types].xml']:
        container=ET.fromstring(parts[key])
        for child in list(container):
            if any(token in str(child.attrib) for token in ['sharedStrings','calcChain']):container.remove(child)
        parts[key]=xml(container)
    if 'docProps/core.xml' in parts:
        core=ET.fromstring(parts['docProps/core.xml'])
        for child in core:
            if child.tag.rsplit('}',1)[-1] in ('creator','lastModifiedBy','title','subject','description','keywords'):child.text=''
        parts['docProps/core.xml']=xml(core)
    return parts

def export_records(records,month,output_path,name,position='대리',template=TEMPLATE):
    first=month_date(month);last=first.replace(day=calendar.monthrange(first.year,first.month)[1])
    name=str(name or '').strip();position=str(position or '').strip()
    if not name:raise ValueError('엑셀 문서에 표시할 성명을 입력하세요.')
    if len(name)>30 or len(position)>30:raise ValueError('성명·직위는 각각 30자 이내로 입력하세요.')
    path=Path(output_path)
    if not path.is_absolute() or path.suffix.lower()!='.xlsx':raise ValueError('엑셀 저장 위치를 선택하세요.')
    included=[];excluded=0;per_day={};seen=set()
    for item in records:
        day=date.fromisoformat(item['date'])
        if not first<=day<=last:continue
        if re.sub(r'\s+','',str(item.get('category','')))!='센터':excluded+=1;continue
        start=clock(item['start']);end=clock(item['end']);duration=end-start
        if duration<120:raise ValueError(f'{day}: 2시간 미만이거나 복귀 시간이 잘못된 출장입니다.')
        if not str(item.get('location','')).strip() or not str(item.get('purpose','')).strip():raise ValueError(f'{day}: 출장 장소·목적을 확인하세요.')
        key=(str(day),start,end)
        if key in seen:raise ValueError(f'{day}: 동일한 시간이 중복된 출장입니다. 사이트를 확인하세요.')
        seen.add(key);amount=10000 if duration<240 else 20000
        per_day[str(day)]=per_day.get(str(day),0)+amount
        if per_day[str(day)]>20000:raise ValueError(f'{day}: 센터 출장비가 하루 최대 2만원을 초과합니다. 사이트 내역을 확인하세요.')
        included.append(dict(item,day=day,duration=duration,amount=amount))
    included.sort(key=lambda r:(r['date'],r['start']))
    if not included:raise ValueError('선택 월에 내보낼 센터 출장 기록이 없습니다. 협회 기록은 제외합니다.')
    template=template or TEMPLATE
    if template is None or not Path(template).is_file():raise ValueError('엑셀 양식 선택에서 원본 출장비 지급내역서 파일을 선택하세요.')
    if path.resolve()==Path(template).resolve():raise ValueError('원본 양식과 다른 파일명으로 저장하세요.')
    source=io.BytesIO(base64.b64decode(Path(template).read_bytes(),validate=True)) if Path(template).suffix=='.txt' else template
    with ZipFile(source) as z:parts={n:z.read(n) for n in z.namelist()}
    parts=prepare_local_parts(parts)
    base=read_xml(parts['xl/worksheets/sheet1.xml'])
    book=read_xml(parts['xl/workbook.xml']);sheets=book.find('s:sheets',NS)
    rels=ET.fromstring(parts['xl/_rels/workbook.xml.rels']);types=ET.fromstring(parts['[Content_Types].xml'])
    original_sheet=sheets[0];sheet_rel_type=next(x.get('Type') for x in rels if x.get('Type','').endswith('/worksheet'))
    names=book.find('s:definedNames',NS)
    if names is None:names=ET.SubElement(book,f'{{{S}}}definedNames')
    for n in list(names):
        if n.get('name')=='_xlnm.Print_Area':names.remove(n)
    count=(len(included)+18)//19
    sheet_titles=[]
    for i in range(count):
        batch=included[i*19:(i+1)*19];root=copy.deepcopy(base)
        title=f'{first.year%100:02}년 {first.month}월'+(f' ({i+1})' if i else '')
        sheet_titles.append(title)
        if i:
            rid='rIdTrip'+str(i+1)
            ET.SubElement(sheets,f'{{{S}}}sheet',name=title,sheetId=str(i+1),attrib={f'{{{R}}}id':rid})
            ET.SubElement(rels,f'{{{P}}}Relationship',Id=rid,Type=sheet_rel_type,Target=f'worksheets/sheet{i+1}.xml')
            ET.SubElement(types,f'{{{C}}}Override',PartName=f'/xl/worksheets/sheet{i+1}.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            if 'xl/worksheets/_rels/sheet1.xml.rels' in parts:parts[f'xl/worksheets/_rels/sheet{i+1}.xml.rels']=parts['xl/worksheets/_rels/sheet1.xml.rels']
            for view in root.findall('s:sheetViews/s:sheetView',NS):view.set('tabSelected','0')
        else:original_sheet.set('name',title)
        ET.SubElement(names,f'{{{S}}}definedName',name='_xlnm.Print_Area',localSheetId=str(i)).text=f"'{title}'!$A$1:$L$35"
        cell(root,'A5',f'작성일 : {last.year}년  {last.month}월  {last.day}일')
        cell(root,'B9',position);cell(root,'D9',name)
        cell(root,'E9',f'{first:%Y.%m.%d}.~ {last:%Y.%m.%d}.')
        for index in range(19):
            r=index+12;item=batch[index] if index<len(batch) else None
            for col in ('A','C','D','E','H','K'):cell(root,f'{col}{r}')
            formula=f'IF(A{r}="","",MOD(TIME(INT(D{r}/100),MOD(D{r},100),0)-TIME(INT(C{r}/100),MOD(C{r},100),0),1))'
            cell(root,f'F{r}',formula=formula,cached=item['duration']/1440 if item else '')
            if item:
                cell(root,f'A{r}',(item['day']-date(1899,12,30)).days)
                for col,key in [('C','start'),('D','end')]:cell(root,f'{col}{r}',int(item[key].replace(':','')))
                for col,key in [('E','transport'),('H','location'),('K','purpose')]:cell(root,f'{col}{r}',str(item.get(key,'대중교통' if key=='transport' else '')))
        short=sum(x['duration']<240 for x in batch);long=len(batch)-short
        cell(root,'D33',formula='COUNTIFS($A$12:$A$30,">0",$F$12:$F$30,"<"&TIME(4,0,0))',cached=short)
        cell(root,'D34',formula='COUNTIFS($A$12:$A$30,">0",$F$12:$F$30,">="&TIME(4,0,0))',cached=long)
        for r,n,rate in [(33,short,10000),(34,long,20000)]:
            cell(root,f'I{r}',formula=f'D{r}',cached=n);cell(root,f'K{r}',formula=f'G{r}',cached=rate)
            cell(root,f'L{r}',formula=f'I{r}*K{r}',cached=n*rate)
        total=short*10000+long*20000
        cell(root,'B35',formula='SUM(L33:L34)',cached=total);cell(root,'J35',formula='B35',cached=total)
        parts[f'xl/worksheets/sheet{i+1}.xml']=xml(root)
    calc=book.find('s:calcPr',NS)
    if calc is None:calc=ET.SubElement(book,f'{{{S}}}calcPr')
    calc.set('fullCalcOnLoad','1');calc.set('forceFullCalc','1')
    parts['xl/workbook.xml']=xml(book);parts['xl/_rels/workbook.xml.rels']=xml(rels);parts['[Content_Types].xml']=xml(types)
    if 'docProps/app.xml' in parts:
        app=ET.fromstring(parts['docProps/app.xml']);v='http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes'
        title_vector=app.find('.//{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}TitlesOfParts/{'+v+'}vector')
        if title_vector is not None:
            for child in list(title_vector):title_vector.remove(child)
            title_vector.set('size',str(count))
            for title in sheet_titles:ET.SubElement(title_vector,'{'+v+'}lpstr').text=title
        heading=app.find('.//{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}HeadingPairs')
        if heading is not None:
            counts=heading.findall('.//{'+v+'}i4')
            if len(counts)==1:counts[0].text=str(count)
        parts['docProps/app.xml']=xml(app)
    fd,tmp=tempfile.mkstemp(prefix='.trip-export-',suffix='.xlsx',dir=path.parent);os.close(fd)
    try:
        with ZipFile(tmp,'w',ZIP_DEFLATED) as z:
            for key,value in parts.items():z.writestr(key,value)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.remove(tmp)
    return dict(export_path=str(path),center_count=len(included),excluded_count=excluded,total_amount=sum(x['amount'] for x in included),sheet_count=count)

def export_site_records(app,job):
    from monthly_reconcile import _settings,_connect
    from trip_site import TripPage
    month=job.get('month');month_date(month)
    if not str(job.get('name') or '').strip():raise ValueError('엑셀에 표시할 성명을 입력하세요.')
    template=job.get('template_path') or TEMPLATE
    if template is None or not Path(template).is_file():raise ValueError('엑셀 양식 선택에서 원본 파일을 선택하세요.')
    with app.file_lock('action',timeout=120):
        driver,_=_connect(app,_settings(app))
        try:
            page=TripPage(driver);page.open();records=page.existing(month)
        finally:driver.quit()
    result=export_records(records,month,job['output_path'],job['name'],job.get('position','대리'),template=template)
    return dict(ok=True,**result,message=f"센터 출장 {result['center_count']}건 내보내기 완료 · 협회 등 {result['excluded_count']}건 제외 · {result['total_amount']:,}원\n{result['export_path']}")
