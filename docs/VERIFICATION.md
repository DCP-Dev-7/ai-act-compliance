# 검증 기록

실제로 실행한 명령과 그 결과만 적었습니다. 실행 환경: Linux, Python 3.13.18, Node v22.23.4, PostgreSQL 16(네이티브 바이너리), 실행일 2026-11-12. LLM은 **mock 모드**(API 키 없음).

## 1. API 단위 테스트

```
$ cd api && python3 -m pytest -q
........................................................................ [ 96%]
...                                                                      [100%]
75 passed in 8.93s
```

75건 통과(SQLite 메모리 DB 사용). 포함 범위: 결정 트리, 골든셋(≥90%), 비식별화, 라우터 정책·예산, Anthropic 공급자(SDK mock), openai_compatible 공급자(HTTP mock), 증적 체인·변조 탐지, 변경 감지, 워크플로 역할 게이트, 기술 점검(HTTP mock), 추출 인용 검증, 문서 조문 참조, SQL 마이그레이션 드리프트.

## 2. 골든셋 일치율

```
$ cd api && python3 -m app.golden
골든셋(합성 28건) 파이프라인 일치율: 27/28 = 96.4% | 규칙 엔진 일치율: 28/28 = 100.0% | 임계 90% → 통과
  불일치 [pipeline] G27 자사 채용에 쓰는 내부 선별 도구(내부 사용이나 고영향): {"art33_recommended": {"expected": false, "got": true}}
```

- 합성 사례 28건. 파이프라인(설명문 → mock 추출 → 결정 트리) 일치율 **27/28 = 96.4%**, 규칙 엔진만(정답 사실 → 결정 트리) **28/28 = 100%**.
- 불일치 1건(G27)은 mock 휴리스틱이 "자동으로 제외된다"를 중대한 영향 표현으로 잡지 못하는 실제 한계이며 고치지 않고 남겨 두었습니다.
- 주의: 사례와 규칙을 같은 작성자가 만들었으므로 이 수치는 회귀 감시용이지 실제 고객 문서에 대한 정확도가 아닙니다.

## 3. 웹 타입체크·빌드

```
$ cd web && npx tsc --noEmit
tsc exit=0

$ npm run build
> ai-act-compliance-web@0.1.0 build
> next build
▲ Next.js 16.4.6 (Turbopack)
✓ Running next.config.ts took 71ms
  Creating an optimized production build ...
✓ Compiled successfully in 5.4s
  Running TypeScript ...
  Finished TypeScript in 4.1s ...
  Collecting page data using 1 worker ...
✓ Generating static pages using 1 worker (6/6) in 229ms
  Finalizing page optimization ...
Route (app)
┌ ○ /
├ ○ /_not-found
├ ƒ /api/[...path]
├ ƒ /customers/[id]
├ ƒ /customers/[id]/changes
├ ƒ /customers/[id]/classification
├ ƒ /customers/[id]/documents
├ ƒ /customers/[id]/evidence
├ ƒ /customers/[id]/gap
├ ƒ /customers/[id]/inventory
├ ƒ /customers/[id]/tech-check
├ ○ /kb
├ ○ /login
└ ○ /ops
○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
build exit=0
```

## 4. 네이티브 E2E (실제 PostgreSQL 16 + API + 웹 + demo-service)

```
$ scripts/dev.sh up
적용된 마이그레이션: ['001_init.sql']
시드 완료: KB v1, 고객 'A사 (가상)', 데모 계정 3개 (비밀번호 demo1234)
실행 완료: 웹 http://localhost:3000 · API http://localhost:8000 · demo-service http://localhost:8081

$ python3 scripts/e2e_smoke.py --api http://127.0.0.1:8000 --web http://127.0.0.1:3000
[01] 상태 확인(/health, /meta)
  ✓ /health ok
  ✓ 배너 문구
  · LLM 모드: mock (mock-rules-1), KB 2026.01-v1
  ✓ 비로그인 접근은 401
[02] 역할별 로그인
  ✓ 세 역할 로그인
  ✓ A사 (가상) 초기 상태 intake
[03] 고객 담당자: 자료 4건 업로드
  ✓ 자료 4건 접수
  ✓ 고객 담당자는 인벤토리 추출 불가(403)
[04] 컨설턴트: AI 인벤토리 추출
  ✓ 시스템 3개 추출: ['상품 이미지 생성', '상품 설명 문구 생성', '고객문의 요약']
  ✓ 추출 사실 22건 모두 문서 인용 구간과 일치
[05] 컨설턴트: 판정 초안 → 확정
  ✓ 상품 이미지 생성: 이용사업자, 제31조 사전고지·생성물표시
  ✓ 상품 설명 문구 생성: 제31조 적용
  ✓ 고객문의 요약: 내부 업무용 예외
  ✓ 고영향 해당 없음
  ✓ 모든 근거 문장에 조문 연결
  ✓ 확정 전 갭 리포트는 거절(409)
  ✓ 고객·운영자는 확정 불가(403)
  ✓ 상태 classification_confirmed
[06] 컨설턴트: 갭 리포트
  ✓ 갭 3건: ['GAP-NOTICE', 'GAP-METADATA', 'GAP-TOS']
  ✓ 심각도·담당·기한·조문 포함
[07] 컨설턴트: 문서 초안 → 승인
  ✓ 문서 3종 생성(고영향 문서 없음)
  ✓ 사전 고지 문구 3종 이상: ['적용 범위', '문구 1 — 앱 첫 화면 고지', '문구 2 — 약관 조항용 고지', '문구 3 — 생성물 라벨(상품 이미지 생성)', '문구 3 — 생성물 라벨(상품 설명 문구 생성)', '예외 기능']
  ✓ 지원되는 규범 문단은 모두 조문 참조 보유
  · 근거 미확인 표시 문단: 1건
  ✓ 고객 담당자는 승인 불가(403)
  ✓ 문서 승인
[08] 컨설턴트: 증적 보관 → 체인 검증
  ✓ 증적 4건 보관, 상태 evidence_stored
  ✓ 해시 체인 연결
  ✓ 보관 기한 5년
  ✓ 체인 검증 OK
[09] 운영자: 기술 점검(demo-service)
  ✓ 통과 2 / 미흡 2: [('prior_notice', 'http://127.0.0.1:8081/'), ('image_metadata', 'http://127.0.0.1:8081/generated/sample-noncompliant.png')]
  ✓ 미흡: 고지 없는 페이지 1, 메타데이터 없는 이미지 1
  ✓ 메타데이터 없는 이미지 식별
  ✓ 점검 결과 증적 보관
[10] 운영자: AI 게이트웨이 로그 적재(M9)
  ✓ 로그 3건 증적 보관
  ✓ 증적 6건으로 증가, 체인 정상
[11] 컨설턴트: 법령 변경 반영(시뮬레이션) → 재평가 작업
  ✓ 재평가 작업 생성: ['상품 설명 문구 생성', '상품 이미지 생성']
  ✓ 예외 시스템은 재평가 대상 아님
  ✓ 활성 KB v2(시뮬레이션)
[12] 고객 릴리스 웹훅 → 재평가 작업
  ✓ 웹훅으로 재평가 작업 1건
  ✓ 고객 화면에 작업 표시
[13] 운영자: 자동화 작업 실행·운영 콘솔
  ✓ 골든셋 일치율 27/28 = 96.4%
  ✓ 증적 체인 검증 작업
  ✓ 주간 기술 점검 작업
  ✓ 월간 보고서 초안 작업
  ✓ 운영 콘솔: 작업 실행 기록·골든셋 결과
  ✓ 토큰 사용량·예산 상태
  ✓ 스케줄러 다음 실행 시각 등록
  ✓ /metrics Prometheus 텍스트
  ✓ 감사 로그에 주요 작업 기록
[14] 웹 포털(Next.js) 확인
  ✓ /login 200 + 한국어
  ✓ 웹 프록시 로그인(httpOnly 쿠키)
  ✓ 웹 프록시 경유 API 호출(쿠키 세션)
  ✓ 페이지 / 200
  ✓ 페이지 /customers/1 200
  ✓ 페이지 /customers/1/classification 200
  ✓ 페이지 /customers/1/evidence 200
  ✓ 페이지 /ops 200
  ✓ 페이지 /kb 200

E2E 스모크 테스트 통과
e2e exit=0
```

확인 항목 57개 모두 통과, 종료 코드 0. E2E 뒤 DB 확인: `audit_logs` 28행, `evidence_items` 7행, 활성 KB `2026.11-v2-sim`.

## 5. 렌더된 페이지 확인 (curl)

```
$ curl -s -o page.html -w "%{http_code}" http://127.0.0.1:3000/<경로>  → 상태 코드와 배너 문구 grep
/login 200 가상 데이터 · 법률 자문 아님
/kb 200 가상 데이터 · 법률 자문 아님
/ops 200 가상 데이터 · 법률 자문 아님
생성형 인공지능(AI)을 기반으로 운용됩니다
```

마지막 줄은 demo-service `generate.html`의 고지 문구입니다.

## 6. 브라우저 확인 (Playwright + Chromium, 헤드리스)

- 컨설턴트·고객 계정으로 11개 화면을 열어 전체 화면 캡처를 눈으로 확인했고, 페이지 오류(pageerror)는 없었습니다. 콘솔 오류는 로그인 전 `/auth/me` 401 한 건뿐입니다(의도된 동작).
- 고객 계정으로 `/ops`를 열면 "운영 콘솔은 운영자·컨설턴트만 볼 수 있습니다"가 표시됩니다.
- 새로 시드한 상태에서 `scripts/ui_click_smoke.py`와 같은 내용의 스크립트로 컨설턴트 화면을 실제로 클릭했습니다:

```
OK 샘플 자료 4건
OK 인벤토리 추출 → 인벤토리 검토
OK 판정 초안 생성 → 판정 초안
OK 판정 3건 확정
OK 갭 리포트 생성 → 갭 리포트
OK 문서 초안 생성 → 문서 초안
OK 문서 승인 → 승인 완료
OK 증적 보관(승인본) → 증적 보관
OK 체인 검증 정상 4건
OK 기술 점검 미흡 2
OK 재평가 작업 2
pageerrors []
```

## 7. Docker

```
$ docker compose config -q            → 종료 코드 0 (.env 없이, 그리고 cp .env.example .env 후 모두)
$ docker compose build demo-service
failed to solve: nginx:1.27-alpine: failed to resolve source metadata for docker.io/library/nginx:1.27-alpine: ... Forbidden
```

- compose 파일 문법·변수 치환은 검증했습니다.
- **이미지 빌드와 컨테이너 실행은 검증하지 못했습니다**(이 환경에서 Docker Hub 차단). Dockerfile 3개는 실행해 보지 않은 상태입니다. 다만 웹 컨테이너가 쓰는 `.next/standalone/server.js` 실행 방식과 API의 `migrate → seed → uvicorn` 순서는 네이티브 실행에서 같은 방식으로 돌려 확인했습니다.

## 8. 검증하지 못한 것

| 항목 | 상태 |
|---|---|
| Docker 이미지 빌드·`docker compose up` | 미검증(Hub 차단) |
| Anthropic API 실호출(추출·문서 다듬기·골든셋) | 미검증(키 없음). SDK 클라이언트를 mock한 단위 테스트만 |
| openai_compatible 내부 추론 서버 실호출 | 미검증. HTTP를 mock한 단위 테스트만 |
| S3 Object Lock 증적 백엔드 | 미구현(스텁) |
| 스케줄러의 예약 시각 자동 실행 | 작업 등록과 다음 실행 시각만 확인. 작업 본문은 수동 실행으로 확인 |
| macOS에서의 `scripts/dev.sh` | 미검증(Linux에서만 실행) |

## 9. 정리

검증 후 `scripts/dev.sh down --purge`로 모든 프로세스를 중지하고 임시 PGDATA(`.devdata/`)를 삭제했습니다.
