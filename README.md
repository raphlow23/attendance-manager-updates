# 출근정리

Windows용 출퇴근 자동관리, 근태 정리, 시간외근무 및 출장일지 프로그램입니다.

## 설치

[초기 설치 EXE 다운로드](https://github.com/raphlow23/attendance-manager-updates/releases/download/v13/AttendanceManager_Setup.exe)

현재 초기 설치 EXE는 v13 부트스트랩입니다. 설치 후 프로그램 실행 시 **최신 v45**를 자동으로 받습니다. 최신 단일 설치 EXE는 로컬에서 빌드·검증했으나 GitHub 웹 첨부가 `storage request` 오류로 실패하여, 첫 설치 경로를 유지하기 위해 이 파일을 임시 보존합니다. 새 EXE로 대체하기 전에는 위 파일을 삭제하지 마세요.

## 자동 업데이트

- 현재 버전: **45**
- [업데이트 정보](https://raw.githubusercontent.com/raphlow23/attendance-manager-updates/main/updates/latest.json)
- [현재 업데이트 ZIP](https://raw.githubusercontent.com/raphlow23/attendance-manager-updates/main/updates/v45/attendance-manager-v45.zip)

ZIP은 기존 설치본용이며 설치 EXE가 아닙니다. 실행 시 RSA 서명과 SHA-256을 확인하고 업데이트하며 사용자 설정과 기록은 보존합니다. Windows 보안 설정을 임의로 변경하지 않습니다.

## 현재 기능

- Windows 로그인 시 자동 출퇴근 처리와 상태·오류 기록
- 휴가/행사 제외일 설정과 선택한 월의 근태 정리
- 월별 시간외근무 신청 및 기존 신청 수정
- 출장 기등록 표시·금액 합산·기존 출발·복귀 시간과 장소·목적 수정
- 목표 미달 일정도 안내 확인 후 진행, 제외 내역 확인 후 등록
- 장소 → 목적 → 다음 행 장소 순서로 Tab/Enter 이동, Shift 역방향

[현재 버전 변경 안내](./출근정리_v45_변경안내.md)

- 출발 시·분과 복귀 시간 직접 수정, 장소·목적 한 번 클릭 입력
- 선택 칸 전체를 한 번 클릭하여 체크/해제

## 배포 자료 정리

사용자의 요청으로 기본 브랜치에서 v9~v43 업데이트 ZIP 35개, 오래된 중복 source 폴더 68개 파일, 이전 변경 안내 12개를 제거했습니다. 최신 v45 업데이트와 필요한 현재 파일을 유지합니다. Git 커밋 이력 자체는 재작성하지 않았으므로 과거 이력에는 이전 자료가 남을 수 있습니다.

실제 사용자 PC 사이트는 직접 시험하지 않았습니다. 공인 Windows 코드 서명은 없으며 RSA 업데이트 서명과는 별개입니다. 계정정보·실행 기록·서명 개인키는 배포하지 않습니다.

추가 정리: 이전 릴리스 v10·v11·v12·v15 및 빈 초안 2개를 삭제하고 태그 v10·v11·v12·v15도 제거했습니다. 첫 설치를 위해 v13 릴리스·태그와 설치 EXE 한 개만 보존합니다. 프로그램 최신 코드는 v45입니다.
