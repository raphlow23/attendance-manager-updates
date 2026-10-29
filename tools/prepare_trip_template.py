"""Keep the reference package's native formatting after Artifact Tool authoring.

Only the authored input values/formulas are transplanted; original styles,
merged cells, dimensions, and page layout remain intact. Device-specific
printer buffers and document provenance metadata are removed for distribution.
No original person's data or historical trip records are distributed.
"""
import base64,copy,io,sys
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from trip_export import S,P,C,NS,read_xml,xml

def strings(parts):
    if 'xl/sharedStrings.xml' not in parts:return []
    return list(ET.fromstring(parts['xl/sharedStrings.xml']))

def read(path):
    with ZipFile(path) as z:return {n:z.read(n) for n in z.namelist()}

def prepare(original,authored,output):
    parts=read(original);edit=read(authored);old_strings=strings(parts);new_strings=strings(edit)
    source=read_xml(parts['xl/worksheets/sheet1.xml']);fresh=read_xml(edit['xl/worksheets/sheet1.xml'])
    dynamic={'A5','A9','B9','D9','E9','J9','D33','D34','I33','I34','K33','K34','L33','L34','B35','J35'}
    dynamic|={f'{c}{r}' for r in range(12,31) for c in 'ABCDEFGHIJKL'}
    dynamic|={f'{c}{r}' for r in range(1,36) for c in 'MNOPQR'}
    fresh_cells={c.get('r'):c for c in fresh.findall('.//s:c',NS)}
    for cell in source.findall('.//s:c',NS):
        if cell.get('r') in dynamic:
            candidate=fresh_cells.get(cell.get('r'))
            for child in list(cell):cell.remove(child)
            cell.attrib.pop('t',None)
            if candidate is not None:
                if candidate.get('t'):cell.set('t',candidate.get('t'))
                for child in candidate:cell.append(copy.deepcopy(child))
            pool=new_strings
        else:pool=old_strings
        if cell.get('t')=='s':
            value=pool[int(cell.find('s:v',NS).text)]
            for child in list(cell):cell.remove(child)
            cell.set('t','inlineStr');inline=ET.SubElement(cell,f'{{{S}}}is')
            # Preserve native rich-text fonts, notably the calligraphic title.
            for child in value:inline.append(copy.deepcopy(child))
    setup=source.find('s:pageSetup',NS)
    if setup is not None:setup.attrib.pop('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id',None)
    parts['xl/worksheets/sheet1.xml']=xml(source)
    parts.pop('xl/sharedStrings.xml',None);parts.pop('xl/calcChain.xml',None)
    for name in list(parts):
        if name.startswith('xl/printerSettings/') or name=='xl/worksheets/_rels/sheet1.xml.rels':parts.pop(name)
    for key in ['xl/_rels/workbook.xml.rels','[Content_Types].xml']:
        root=ET.fromstring(parts[key])
        for child in list(root):
            if any(token in str(child.attrib) for token in ['sharedStrings','calcChain','printerSettings']):root.remove(child)
        parts[key]=xml(root)
    if 'docProps/core.xml' in parts:
        root=ET.Element('{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}coreProperties')
        parts['docProps/core.xml']=xml(root)
    book=read_xml(parts['xl/workbook.xml']);book.find('s:sheets/s:sheet',NS).set('name','출장비 양식')
    for parent in list(book.iter()):
        for child in list(parent):
            if any(e.tag.rsplit('}',1)[-1]=='absPath' for e in child.iter()):parent.remove(child)
    for entry in book.findall('s:definedNames/s:definedName',NS):
        if entry.get('name')=='_xlnm.Print_Area':entry.text="'출장비 양식'!$A$1:$L$35"
    parts['xl/workbook.xml']=xml(book)
    app_ns='http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
    vt='http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes'
    app=ET.Element('{'+app_ns+'}Properties');ET.SubElement(app,'{'+app_ns+'}Application').text='출근정리'
    titles=ET.SubElement(app,'{'+app_ns+'}TitlesOfParts');vector=ET.SubElement(titles,'{'+vt+'}vector',size='1',baseType='lpstr');ET.SubElement(vector,'{'+vt+'}lpstr').text='출장비 양식'
    parts['docProps/app.xml']=xml(app)
    stream=io.BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(name,data)
    Path(output).write_bytes(base64.b64encode(stream.getvalue()))
    assert parts['xl/styles.xml']==read(original)['xl/styles.xml']
    assert not any(n.startswith('xl/printerSettings/') for n in parts)
    for address in ['A5','A9','B9','D9','E9','J9']:
        node=source.find(f'.//s:c[@r="{address}"]',NS)
        assert node is None or not ''.join(node.itertext()).strip(),address
    print('PUBLIC_BLANK_TEMPLATE_OK: original styles/page layout retained; person, trips, payout, provenance and printer-device data removed')

if __name__=='__main__':prepare(*sys.argv[1:])
