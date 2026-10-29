"""Build the Korean v49 user guide from verified local UI and behavior."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pdf';OUT.mkdir(parents=True,exist_ok=True)
PDF=OUT/'출근정리_사용설명서_v49.pdf'
MD=OUT/'출근정리_사용설명서_v49.md'
pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
INK=colors.HexColor('#333B45');CYAN=colors.HexColor('#429EB5');MINT=colors.HexColor('#55B6A6')
PALE=colors.HexColor('#EEF6F8');GRAY=colors.HexColor('#657282')
styles={
 'title':ParagraphStyle('title',fontName='MalgunBold',fontSize=25,leading=35,textColor=INK,spaceAfter=12,wordWrap='CJK'),
 'sub':ParagraphStyle('sub',fontName='Malgun',fontSize=11,leading=18,textColor=GRAY,spaceAfter=17,wordWrap='CJK'),
 'h':ParagraphStyle('h',fontName='MalgunBold',fontSize=13,leading=21,textColor=CYAN,spaceBefore=13,spaceAfter=7,wordWrap='CJK'),
 'body':ParagraphStyle('body',fontName='Malgun',fontSize=10,leading=17,textColor=INK,spaceAfter=7,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='Malgun',fontSize=9,leading=15,textColor=GRAY,spaceAfter=5,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='Malgun',fontSize=9,leading=15,textColor=INK,wordWrap='CJK'),
 'head':ParagraphStyle('head',fontName='MalgunBold',fontSize=9,leading=15,textColor=colors.white,wordWrap='CJK'),
}
story=[];md=['# 출근정리 사용설명서','', 'v49 기준 | 작성일 2026-10-29', '']
def p(text,style='body'):
 story.append(Paragraph(escape(text).replace('\n','<br/>'),styles[style]));md.extend([text,''])
def heading(text):p(text,'h')
def step(n,text):p(f'{n}. {text}')
def callout(text):
 t=Table([[Paragraph(escape(text),styles['body'])]],colWidths=[491]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.6,CYAN),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,9)]);md.extend([f'> {text}',''])
def table(headers,rows,widths):
 data=[[Paragraph(escape(x),styles['head']) for x in headers]]+[[Paragraph(escape(str(x)),styles['cell']) for x in row] for row in rows]
 t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#DCE5EA'))]));story.append(t)
 md.extend(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows]+[''])
def page(number,title,subtitle):
 if number>1:story.append(PageBreak())
 p(f'{number:02d}  {title}','title');p(subtitle,'sub')

page(1,'출근정리 사용설명서','Windows 프로그램 · v49 기준 · 2026년 10월 29일')
callout('처음 사용한다면: 설치 → 최신 버전 확인 → 1번 메뉴에서 계정·시간 설정 저장 → 자동 실행 상태 확인 순서로 시작하세요.')
heading('네 가지 메뉴')
table(['메뉴','하는 일','설명 위치'],[
 ['1. 근태 자동관리 설정','계정·시간 범위·연장시간 설정, 자동 실행 시작과 일시 정지','2쪽'],
 ['2. 휴가·제외일 / 근태 정정','휴가·행사일 저장, 월별 수정 목록 검토 후 사이트 반영','3쪽'],
 ['3. 시간외근무 신청','선택 월의 실제 연장일 조회, 목적 입력 후 신청·수정','4쪽'],
 ['4. 출장일지','출퇴근 날짜와 기존 출장 조회, 목표 금액에 맞춰 등록·수정','5~6쪽'],
 ['실행 상태·보안 안내','로그인 결과·오류 확인, 차단 진단과 삭제 방법','7쪽'],
],[150,285,56])
heading('설치와 자동 업데이트')
step(1,'설치 EXE를 내려받아 실행하고 설치를 완료합니다. Python을 따로 설치할 필요는 없습니다.')
step(2,'출근정리를 실행하고 하단의 자동 업데이트 상태를 확인합니다. v49이 이 설명서의 기준 버전입니다.')
step(3,'설치 링크의 v13은 최초 설치용 파일입니다. 인터넷에 연결된 상태로 실행하면 현재 업데이트를 받습니다. 이후 더 최신 버전이 배포되면 그 버전이 표시될 수 있습니다.')
p('다운로드: https://github.com/raphlow23/attendance-manager-updates/releases/download/v13/AttendanceManager_Setup.exe','small')
p('프로그램은 설치한 PC에서 실행됩니다. GitHub는 설치·업데이트 파일 배포에 사용하며, 출근정리에 별도 서버 호스팅은 사용하지 않습니다.','small')

page(2,'자동 출퇴근 설정','1번 메뉴: 근태 자동관리 설정')
step(1,'로그인 ID와 PW를 입력합니다. 이미 저장한 비밀번호를 유지할 때는 PW 칸을 비워 둡니다.')
step(2,'출근·일반 퇴근 범위와 선택 간격을 정합니다. 시간은 HH:MM 형식으로 입력하고 1분 또는 5분 간격을 선택합니다.')
table(['설정','기본값 / 의미'],[
 ['출근 범위','08:30~08:55'],['일반 퇴근 범위','18:05~18:55'],['선택 간격','기본 5분. 시작 시각을 기준으로 후보 시간이 만들어집니다.'],
 ['월 연장시간','기본 10시간. 0이면 연장 배정 없음.'],['하루 기준 1시간','19:00~19:55 범위 / 월 10시간이면 10일 배정'],['하루 기준 2시간','20:00~20:55 범위 / 월 10시간이면 5일 배정'],
],[142,349])
step(3,'‘ID/PW 저장 및 작업 등록’을 누른 뒤 저장·예약 등록 결과를 확인합니다.')
heading('언제 실행되나요?')
p('Windows 사용자 로그인 시 자동 실행하며, PC가 계속 켜져 있으면 예약된 출근·퇴근 처리를 수행합니다. 기본적으로 주말·공휴일과 저장된 휴가일은 제외합니다. 이전 18:00 설정과 미완료 예약은 18:05부터 적용하며, 하루 2시간의 미완료 19시대 예약은 20시대로 조정합니다. PC가 꺼져 있거나 로그인·네트워크·사이트 접속에 문제가 있으면 그 시각에 처리할 수 없습니다.')
p('다음 출근 처리 때 과거 퇴근 누락 보완도 시도합니다. 기본 설정에서는 09시 이후 늦게 켰을 때 당일 출근 시간 보정도 시도합니다. 사이트의 수정 가능 여부와 접속 결과에 따라 보류될 수 있으므로 실제 저장 결과를 확인하세요.')
heading('정지·재개와 설정 변경')
p('‘일시 정지’는 예약 작업과 자동 실행을 함께 멈춥니다. ‘다시 시작’은 재개합니다. 설정 창의 ‘닫기’나 메뉴 창 닫기는 자동 실행을 일시 정지하는 기능이 아닙니다.')
callout('시간 범위 변경은 새로 만드는 예약부터 적용됩니다. 이미 만든 당월 연장 계획의 월 시간·하루 기준 변경은 다음 달 계획부터 적용됩니다. 당월 기록 정리는 2번 메뉴에서 검토하세요.')

page(3,'휴가·행사일과 근태 정리','2번 메뉴: 설정 저장과 사이트 반영은 별도 단계입니다.')
heading('먼저 달력에 제외일 저장')
step(1,'달력에서 날짜를 클릭합니다. 여러 날짜를 선택할 수 있으며 다시 누르면 선택이 해제됩니다.')
step(2,'‘휴가’ 또는 ‘연장근무 제외’를 선택합니다. 같은 날짜에 두 종류를 동시에 지정할 수 없습니다.')
step(3,'‘선택 N개 설정 저장’을 눌러 저장 날짜 목록에 표시되는지 확인합니다. 잘못 저장한 날짜는 목록에서 골라 ‘선택 항목 삭제’를 누릅니다.')
callout('이 단계는 프로그램의 날짜 설정을 저장합니다. 저장만으로 사이트 출퇴근 기록이 수정되지는 않습니다.')
heading('수정 목록을 확인한 뒤 적용')
step(1,'조회 월을 선택하고 ‘선택 월 수정 목록 조회’를 누릅니다. 과거 월도 선택할 수 있습니다.')
step(2,'기존 출근·퇴근, 변경 출근·퇴근, 정리 사유를 확인합니다. 반영하지 않을 날짜는 체크를 해제하고 필요한 시간은 목록에서 직접 수정합니다.')
step(3,'‘선택 내역 정리’를 누르고 처리 결과를 확인합니다. 프로그램은 해당 날짜의 수정 화면에서 하루씩 저장하고 결과를 확인합니다.')
table(['설정 / 상황','기본 정리 방식'],[
 ['휴가','자동 출퇴근에서 제외. 기존 퇴근이 19시 이전이면 유지하며, 조건에 맞는 연장 기록은 정리 대상으로 제시합니다.'],
 ['연장근무 제외(행사)','정리 가능한 기록의 출근 09:00, 퇴근 18:05를 제안합니다.'],
 ['퇴근 누락·월 연장 배정','과거 누락 기록과 월 목표에 따른 변경 예정 날짜를 제시합니다. 수정 가능한 후보가 부족하면 목표를 채우지 못할 수 있습니다.'],
],[142,349])
p('오늘 아직 퇴근하지 않은 기록, 출퇴근이 모두 없는 날짜, 시간을 해석하지 못한 날짜 등은 보류될 수 있습니다. ‘사이트 확인 필요’는 완료 표시가 아니므로 사이트에서 해당 날짜를 확인한 후 다시 조회하세요.','small')

page(4,'시간외근무 신청','3번 메뉴: 근태 정리를 끝낸 후 조회하세요.')
step(1,'조회 월을 고릅니다. 기본은 당월이며, 9월을 선택하면 9월 기록과 9월 날짜로 처리합니다.')
step(2,'‘선택 월 실제 연장일 조회’를 누릅니다. 자동관리 설정의 저장 계정을 사용하며, 이 화면에서 계정을 입력·저장할 수도 있습니다.')
step(3,'조회된 실제 연장 퇴근 날짜를 확인하고 신청할 날짜를 체크합니다. 날짜마다 근무목적을 직접 입력합니다.')
step(4,'‘확인 — 선택 날짜 신청·수정’을 누릅니다. 프로그램이 근무일지의 시간외근무신청 화면에서 날짜별로 처리합니다.')
step(5,'선택 건이 모두 저장 확인되면 작업창이 자동으로 닫힙니다. 일부 처리·오류는 창에 남으므로 사이트 내역을 확인하고 다시 조회한 뒤 재처리합니다.')
heading('자동 입력되는 내용')
table(['항목','입력 방식'],[
 ['부서','센터'],['날짜·요일','선택 월의 실제 연장 근무 날짜'],['시작 시간','18:00'],['신청 종료','실제 퇴근 시각의 분을 제외한 정시'],['근무목적','사용자가 직접 입력한 내용'],['신청서 하단 날짜','같은 근무 날짜'],
],[142,349])
callout('예: 19:55 퇴근 → 18:00~19:00 신청 / 20:35 퇴근 → 18:00~20:00 신청')
heading('이미 신청한 날짜를 바꾸려면')
p('해당 날짜를 다시 체크하고 목적을 고친 뒤 같은 신청·수정 버튼을 누릅니다. 기존 신청이 있으면 수정하고, 없으면 추가합니다. 등록 결과가 불확실할 때는 반복해서 누르기보다 먼저 사이트에서 실제 내역을 확인하세요.')
p('시간외근무 목적은 자동 임시저장됩니다. 근태 시간을 변경했다면 이 화면에서 해당 월을 다시 조회해야 최신 퇴근 시간이 반영됩니다.')

page(5,'출장일 선택과 금액 배분','4번 메뉴: 출퇴근 일정 조회 → 날짜·시간 선택')
step(1,'조회 월과 목표 금액을 입력합니다. 금액 단위는 만원이며, 20을 입력하면 20만원입니다.')
step(2,'‘출퇴근 일정 조회’를 누릅니다. 출근·퇴근이 모두 등록된 날짜와 기존 출장 여부·금액을 확인합니다. 휴가 날짜는 목록에서 숨깁니다.')
step(3,'필요한 날짜를 체크하고 인정시간을 고릅니다. ‘선택일 시간 배분’으로 선택한 날짜 안에서 금액에 맞는 시간 조합을 배분할 수도 있습니다.')
table(['인정시간 / 구분','금액 및 기본 시간'],[
 ['2시간','1만원. 출발을 바꾸면 2시간 뒤로 복귀 자동 계산.'],['4시간','2만원. 출발을 바꾸면 4시간 뒤로 복귀 자동 계산.'],
 ['일반 신규 날짜','기본 13:00~17:00. 시·분과 복귀 시간 수정 가능.'],['연장근무 제외(행사)','기본 09:00~18:00, 인정은 최대 4시간·2만원. 필수 선택이 아닙니다.'],
 ['기등록 날짜','사이트에 저장된 시간·장소·목적을 불러옵니다. 기존 금액은 중복 합산하지 않습니다.'],
],[142,349])
heading('시간·금액에서 확인할 점')
p('목록의 ‘구분’은 일반 날짜와 ‘연장근무 제외(행사)’를 구별하는 표시입니다. 사이트의 출장 구분은 ‘센터’, 이동수단은 ‘대중교통’으로 입력합니다.')
p('출발 시·분을 바꾸면 복귀 시간을 자동 계산합니다. 복귀 시간은 직접 수정할 수도 있습니다. 출퇴근 구간을 벗어나거나 인정시간과 맞지 않으면 진행할 수 없습니다. 2시간 인정은 실제 2시간, 4시간 인정은 4시간 이상을 사용하며 하루 인정은 최대 4시간입니다.')
p('목표 금액을 채우면 추가 선택이 제한됩니다. 다른 날짜를 해제하거나 시간을 줄여 조정하세요. 목표가 부족해도 다음 단계로 갈 수 있으며, 부족 안내에서 확인하면 현재 선택한 날짜만으로 진행합니다.')
step(4,'‘선택 완료 → 기존 출장 확인’을 누릅니다. 기존 내역을 다시 확인한 뒤 장소·목적 입력 화면으로 넘어갑니다.')
callout('v49에는 ‘기존 출장 불러오기·수정’ 버튼이 없습니다. 기존 출장도 위의 동일한 흐름으로 선택하고 수정합니다.')

page(6,'출장 장소·목적과 등록·수정','선택한 날짜만 모인 두 번째 화면')
step(1,'각 날짜의 출장 장소와 출장 목적 칸을 한 번 클릭해 작성합니다. 기등록 날짜는 불러온 내용을 확인하고 필요한 부분을 고칩니다.')
step(2,'출발 시·분과 복귀 시간을 최종 확인합니다. 기존 건의 인정시간은 유지되며 출발·복귀와 장소·목적은 수정할 수 있습니다.')
step(3,'이번에 처리하지 않을 날짜는 체크를 해제합니다. 목적을 비워 둔 날짜도 등록 대상에서 제외됩니다. 체크된 날짜의 목적이 있는데 장소가 없으면 장소를 입력해야 합니다.')
step(4,'‘선택 날짜 등록·수정’을 누릅니다. 포함·제외 날짜와 부족 금액 안내를 확인한 뒤 진행합니다.')
step(5,'프로그램이 사이트에서 날짜별로 저장하고 결과를 확인합니다. 선택 건이 모두 저장 확인되면 작업창이 자동으로 닫힙니다. 실패·일부 처리·확인 필요 상태는 창에 남습니다.')
heading('키보드로 빠르게 작성')
table(['키','이동 / 동작'],[
 ['Tab 또는 Enter','장소 → 같은 행 목적 → 다음 행 장소 순서'],['Shift+Tab / Shift+Enter','위 순서의 역방향'],['선택 칸 클릭 / Space','날짜 선택·해제. 클릭한 선택값은 즉시 반영됩니다.'],
],[170,321])
heading('사이트에서 처리되는 방식')
p('미등록 날짜는 ‘출장 등록하기’에서 추가합니다. 기등록 날짜는 같은 날짜의 출장 내역 행에 있는 ‘수정’을 눌러 ‘출장 수정하기’ 화면을 열고, 내용 입력 후 ‘수정’을 눌러 저장합니다. 수정에 실패했다고 신규 출장으로 바꾸어 등록하지 않습니다.')
heading('제외·부족·확인 필요가 나오면')
p('체크 해제 또는 목적 미입력으로 빠진 날짜는 등록하지 않습니다. 목표 금액보다 부족해도 안내를 확인하면 입력한 날짜만 처리할 수 있습니다. 같은 날 여러 출장 내역이 있거나 저장 결과가 불확실하면 사이트에서 확인하고 다시 조회하세요.')
callout('출장 장소·목적은 창을 닫아도 자동 보존된다고 가정하지 마세요. 미등록 입력은 닫기·재조회·업데이트 전에 따로 복사해 두는 것이 좋습니다.')

page(7,'상태 확인과 문제 해결','메인 메뉴 하단: 실행 상태 · 로그인 결과 · 오류 로그 / 실행 차단 · 보안 안내')
table(['상황','확인 및 조치'],[
 ['PC를 꺼 두었음','꺼진 동안에는 실행되지 않습니다. 다음 로그인 후 누락 보완 결과를 확인하고, 필요하면 2번 메뉴에서 해당 월을 조회합니다.'],
 ['자동 출퇴근이 안 됨','저장 계정, 자동 실행 상태, 일시 정지 여부, PC 날짜·시간, 인터넷과 사이트 로그인을 확인합니다.'],
 ['ChromeDriver 버전 오류','먼저 최신 프로그램으로 업데이트합니다. 계속되면 Chrome 버전과 오류 로그를 함께 확인합니다.'],
 ['후보 2개 / 수정 입력 화면 오류','v47의 중복 시간 옵션 수정이 포함된 v49 이상인지 확인합니다. 최신 버전에서도 재현되면 오류 문구와 해당 수정 화면을 남깁니다.'],
 ['저장 확인 실패 / 처리 확인 필요','실제로 저장됐을 수 있습니다. 사이트에서 해당 날짜를 먼저 확인한 뒤 다시 조회하세요. 반복 클릭은 피합니다.'],
 ['버튼이 남아 있거나 화면이 예전임','작업 창을 닫고 프로그램을 완전히 종료한 뒤 다시 실행합니다. 업데이트 상태와 버전을 확인합니다.'],
 ['알약 등 백신에서 차단','‘실행 차단 / 보안 안내’에서 진단 방법을 봅니다. 백신의 탐지명·격리 파일 경로·시각을 확인해 전달하세요. 프로그램은 보안 설정을 임의 변경하지 않습니다.'],
],[142,349])
heading('완료 여부와 로그 확인')
p('“처리 확인 필요”, “사이트 확인 필요”, “미처리”, “저장 실패”는 완료 표시가 아닙니다. 실행 상태 화면에서 날짜·시간·오류 원인을 확인하고, 성공으로 표시된 건도 필요하면 사이트에서 대조하세요. 문의할 때는 버전, 사용 메뉴, 조회 월·날짜, 오류 문구와 해당 화면을 보내면 됩니다. 비밀번호는 보내지 마세요.')
heading('업데이트와 삭제')
p('업데이트 설정 버튼은 없습니다. 실행 시 백그라운드로 확인하며, 새 버전 적용 중에는 완료 후 다시 열린 메뉴에서 버전을 확인합니다. 인터넷·보안 차단 등의 문제로 업데이트가 보류되면 안내를 확인합니다.')
p('설치 폴더만 지우지 말고 Windows의 설치된 앱/프로그램 제거 또는 설정 화면의 ‘완전 삭제’를 사용합니다. 제거 확인 후 자동 실행·감시 프로세스, 예약 작업, 바로가기와 계정·실행 기록이 삭제됩니다.')
p('이 설명서는 v49의 코드와 화면 구성을 기준으로 작성했습니다. 사이트 화면 변경이나 계정 권한에 따라 동작이 달라질 수 있으며, 실제 저장 결과는 사이트에서 확인할 수 있습니다.','small')

def decoration(c,doc):
 w,h=A4;c.saveState();c.setFillColor(CYAN);c.rect(0,h-9,w,9,fill=1,stroke=0)
 c.setStrokeColor(colors.HexColor('#DAE3E8'));c.line(52,47,w-52,47)
 c.setFont('Malgun',8);c.setFillColor(GRAY);c.drawString(52,31,'출근정리 사용설명서 | v49 | 2026-10-29')
 c.drawRightString(w-52,31,f'{doc.page} / 7');c.restoreState()
doc=SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=52,leftMargin=52,topMargin=42,bottomMargin=61,title='출근정리 사용설명서 v49',author='출근정리')
doc.build(story,onFirstPage=decoration,onLaterPages=decoration)
MD.write_text('\n'.join(md),encoding='utf-8')
r=PdfReader(PDF);assert len(r.pages)==7,f'Unexpected page count: {len(r.pages)}'
text='\n'.join(p.extract_text() for p in r.pages)
for term in ['선택 날짜 등록','일시 정지','기존 출장 불러오기','52']:
 if term!='52':assert term in text,term
assert all(len(p.extract_text())>200 for p in r.pages)
print(f'MANUAL_OK: {len(r.pages)} pages, {PDF.stat().st_size} bytes')
