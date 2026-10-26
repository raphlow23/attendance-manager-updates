# 근태매니저

Windows용 근태 자동관리 및 월별 시간외근무 신청 프로그램의 업데이트 저장소입니다.

## 설치

[**설치 EXE 바로 다운로드 — AttendanceManager_Setup.exe**](https://github.com/raphlow23/attendance-manager-updates/releases/download/v11/AttendanceManager_Setup.exe)

다운로드한 **AttendanceManager_Setup.exe 파일 하나**를 실행하면 필요한 파일을 자동으로 풀고 현재 사용자 프로그램 폴더에 설치한 뒤 관리 화면을 바로 엽니다. 별도 Python 설치나 수동 ZIP 압축 해제는 필요하지 않습니다.

Windows 설정의 **설치된 앱** 또는 제어판의 프로그램 제거에서 **근태매니저**를 제거할 수 있습니다. 제거 시 자동 실행/감시/자식 프로세스, 예약 작업 4개, 바로가기, 프로그램·계정·기록과 앱 등록 정보를 정리합니다.

이 저장소의 ZIP은 **기존 설치본용 코드 업데이트**입니다. Python 런타임을 포함한 초기 설치 EXE와는 별도입니다.

## 자동 업데이트

버전: **11 (2026-10-26)**

고정 주소:

https://raw.githubusercontent.com/raphlow23/attendance-manager-updates/main/updates/latest.json

실행할 때 최신 버전을 확인하며 RSA 서명과 SHA-256이 맞는 코드 업데이트만 적용합니다. 사용자 계정·기록은 보존합니다. 공인 Windows 코드 서명과는 다른 서명입니다.

## 기능

- 근태 자동관리 / 시간외근무 신청 선택
- 로그인 시 자동 시작, 별도 EXE 감시와 제한된 자동 재실행
- 의도적 중지 존중, 중복 실행 방지, 실제 로그인 결과 및 오류 로그
- 당월 기본 및 월 선택으로 실제 연장 퇴근 조회, 날짜별 직접 입력 목적
- 센터 부서, 18:00 시작, 실제 퇴근의 분을 제외한 19:00 또는 20:00 종료
- Windows 보안 진단 안내. 보안 기능·방화벽·업데이트·제외 규칙을 임의 변경하지 않음

실제 출퇴근 사이트 로그인·수정·신청 저장, Windows 재부팅과 실제 제어판 제거는 별도 실기 시험이 필요합니다. 자체 EXE의 공인 코드 서명이 없어 보안 정책에 따라 경고나 차단이 발생할 수 있습니다.

계정정보·실행 기록·서명 개인키는 공개하지 않습니다.

## v11 설치 수정

Windows PowerShell에서 설치 종료 코드가 비어 정상 설치를 실패로 표시하던 문제를 수정했습니다. 설치 실패 시 원인과 종료 코드를 표시하고 `%TEMP%\AttendanceManager-install-logs`에 로그를 보존합니다. 단일 EXE 내부의 GUI 설치 경로를 별도 시험 폴더에서 검증했습니다.
