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

---

# 추가 검증: 고객사 등록·연습 시나리오·학습 도우미 (2026-11-18)

위 1~9장은 첫 버전(2026-11-12)의 기록이라 그대로 두었습니다. 아래는 이번 변경에 대해 실제로 실행한 명령과 결과입니다. 환경: Linux, Python 3.13.18, Node v22.23.4, PostgreSQL 16(네이티브 바이너리), LLM은 **mock 모드**(API 키 없음).

## A. API 단위 테스트

```
$ cd api && python3 -m pytest -q
93 passed in 12.99s
```

75 → 93건. 새로 추가된 18건: 시나리오 A~E 문서 → mock 추출 → 판정이 기대값과 같은지(5), 시나리오가 가상 표시를 갖췄는지, 설문 문항의 조문이 KB에 있는지, 등록 API(권한 401/403, 검증 422, 중복 409, 감사 로그, 1단계 시작), 빈 고객에 직접 올린 자료 흐름, 고객 담당자 계정의 접근 범위(다른 고객사 8개 경로 403), 비밀번호 해시, B·C·D·E 전체 흐름, 폼에서 고친 설문이 시나리오 기본값보다 우선, A사 샘플 자료 유지, 001 이후 마이그레이션이 추가 전용인지.

## B. 골든셋

```
$ cd api && python3 -m app.golden
골든셋(합성 33건) 파이프라인 일치율: 32/33 = 97.0% | 규칙 엔진 일치율: 33/33 = 100.0% | 임계 90% → 통과
  불일치 [pipeline] G27 자사 채용에 쓰는 내부 선별 도구(내부 사용이나 고영향): {"art33_recommended": {"expected": false, "got": true}}
```

28 → 33건(G29~G33은 연습 시나리오 사례). 추가한 5건은 시나리오 문서와 같은 문장이라 맞는 것이 당연하며, 일치율이 96.4% → 97.0%로 오른 것은 추출기가 나아졌다는 뜻이 아닙니다. 기존 불일치 G27은 그대로입니다. 규칙 엔진(`engine.py`)은 고치지 않았습니다.

## C. 웹 타입체크·빌드

```
$ cd web && npx tsc --noEmit        → 출력 없음, 종료 코드 0
$ cd web && npm run build           → 종료 코드 0. 새 경로: ○ /customers/new, ○ /learn
```

## D. 이전 버전 DB에서의 업그레이드(마이그레이션)

사용자의 맥에 이전 버전으로 만든 Postgres 볼륨이 있으므로, 같은 상황을 만들어 확인했습니다.

1. 이전 커밋(`72a0278`)을 별도 작업 트리로 꺼내, 그 코드로 새 PostgreSQL 16에 `python -m app.migrate && python -m app.seed` → 이전 버전 API 기동 → 이전 버전 `scripts/e2e_smoke.py` 전체 통과(A사가 8단계 끝까지 간 상태).
2. 이 시점의 DB를 기록(행 수, A사 행의 값·해시, 증적 체인 해시, 판정 결과 해시):

```
customers 1
users 3
engagements 1
documents 4
ai_systems 3
facts 36
classifications 3
gap_reports 1
generated_documents 4
evidence_items 7
change_events 2
reassessment_tasks 3
audit_logs 27
tech_checks 2
kb_versions 2
kb_clauses 31
llm_usage 3
job_runs 4
golden_runs 1
customer|1|A사 (가상)|40|t|50|t|a21a167c8c0e354905d45363e039ad81|ac4e009d813bf133585d7be887d270a6|ea8d36ac855a98292ddff891841e8b29
engagement|1|evidence_stored
evidence|423d76e61eba4f8f5aa9d607e7ad5812
cls|6649e7e7b2822e051cf4839a27d0f386
migrations|001_init.sql
cust_cols|id,name,description,employees,is_synthetic,allow_external,monthly_budget_usd,subscribed,current_state,tech_targets,created_at
```

3. API를 끄고 **새 코드**로 `scripts/dev.sh up`(같은 PGDATA):

```
적용된 마이그레이션: ['002_customer_registration.sql']
시드 완료: KB v1, 고객 'A사 (가상)', 데모 계정 3개 (비밀번호 demo1234)
실행 완료: 웹 http://localhost:3000 · API http://localhost:8000 · demo-service http://localhost:8081
$ python3 -m app.migrate            → 적용된 마이그레이션: 없음(최신)
$ python3 -m app.migrate --check    → 스키마 검사: 모델과 일치
```

4. 같은 기록을 다시 떠서 `diff`: 달라진 줄은 두 개뿐입니다(적용된 마이그레이션 목록에 002 추가, `customers` 컬럼 목록 끝에 `industry,scenario` 추가). 모든 테이블의 행 수, A사 값, 증적 체인 해시, 판정 결과 해시는 동일.
5. 새 API로 확인: A사 `evidence_stored`, 증적 7건 체인 검증 OK, 접수 자료 4건, 판정 3건 확정 유지, `scenario=a`·`industry=전자상거래·유통`으로 채워짐, 샘플 자료 다시 불러와도 중복 없음(`[]`). 업그레이드된 DB에 E사(가상)를 등록해 갭 리포트까지 진행 → `['GAP-LABEL', 'GAP-METADATA', 'GAP-DEEPFAKE']`. API 로그에 error/traceback 없음.

새 DB에서는 `적용된 마이그레이션: ['001_init.sql', '002_customer_registration.sql']`로 뜨고 `--check`도 일치합니다.

확인하지 않은 것: 새 스키마에서 이전 버전 코드로 되돌리는 경우(추가 컬럼에 DB 기본값이 있어 INSERT는 될 것으로 보이나 실행해 보지 않음).

## E. E2E 스모크 (새 DB, 네이티브, PostgreSQL 16)

```
$ scripts/dev.sh up
$ python3 scripts/e2e_smoke.py --api http://127.0.0.1:8000 --web http://127.0.0.1:3000   → 종료 코드 0
```

기존 13단계(A사 전체 흐름)는 그대로 통과했고, 추가된 단계의 출력은 다음과 같습니다.

```
[14] 고객사 등록: 권한·검증
  ✓ 고객 담당자는 고객사 등록 불가(403)
  ✓ 잘못된 업종은 422, 이미 있는 회사명은 409
[15] 컨설턴트: 연습 시나리오 B(채용 자동 평가) 등록 + 고객 담당자 계정
  ✓ B사 (가상) 등록 — 1단계(자료 접수)에서 시작
  ✓ 시나리오 B 가상 자료 4건 접수, 외부 반출 금지
  ✓ 샘플 자료 다시 불러와도 중복 접수 없음
  ✓ 고객사 목록에 추가됨
[16] B사: 인벤토리 → 판정 → 확정 → 갭 리포트
  ✓ 지원서 자동 평가: 고영향 후보(채용 영역 + 중대한 영향)
  ✓ 사람 검토 없음 → 제34조 책무·제35조 영향평가 대상
  ✓ 생성형은 아니지만 고영향이라 사전 고지 필요
  ✓ 면접 답변 분석: 형식적 검토(쟁점) → 고영향 후보 + 제33조 확인 요청 권고
  ✓ 갭 8건: ['GAP-NOTICE', 'GAP-TOS', 'GAP-RISK', 'GAP-EXPLAIN', 'GAP-OVERSIGHT', 'GAP-RETENTION', 'GAP-IMPACT', 'GAP-CONFIRM']
  ✓ 위험관리·설명·사람 감독·5년 보관 갭 포함
  ✓ 고영향 문서(위험관리 정책 골격·영향평가 체크리스트) 생성
[17] B사 고객 담당자: 자기 고객사만 조회
  ✓ 등록한 계정으로 로그인(고객 담당자)
  ✓ 목록에 B사만 보임
  ✓ 다른 고객사 조회·고객사 등록은 403 (A사 담당자도 B사 조회 불가)
[18] 운영자: 연습 시나리오 D(사내 업무용 AI) 등록 → 판정 → 갭
  ✓ D사 (가상) 등록, 가상 자료 3건 접수
  ✓ 시스템 2개: ['사내 문서 요약', '코드 작성 도우미']
  ✓ D사: 내부 업무용 예외 — 제31조 의무 없음
  ✓ D사: 고영향 아님
  ✓ 갭 0건 + '의무 거의 없음' 설명
  ✓ 감사 로그에 customer.create 기록
  ✓ 감사 로그에 비밀번호 없음
[19] 웹 포털(Next.js) 확인  … /learn, /customers/new, /customers/2/classification, /customers/3/gap 포함 14항목 ✓

E2E 스모크 테스트 통과
```

✓ 표시는 모두 85줄입니다.

## F. 브라우저 확인 (Playwright + Chromium, 헤드리스)

E 다음에 같은 DB에서 컨설턴트 화면을 실제로 클릭했습니다(일회용 스크립트, 저장소에는 넣지 않음).

```
OK 대시보드에 고객사 등록 버튼
OK 이미 있는 이름은 자동으로 'B사 2 (가상)'
OK 시나리오 C 프리셋으로 폼 채움 [True, False, False, True, True, True, True, True]
OK C사 등록 → 개요 화면, 1단계 자료 접수, 자료 4건
OK '이 단계는?' 펼침
OK 인벤토리 추출 → 인벤토리 검토
OK 판정 초안 생성 → 판정 초안
OK C사 판정: 제외 가능(쟁점) + 타법 이행 간주
OK ? 클릭 → 설명 표시
OK 설명의 조문 링크 → KB 해당 조문 강조
OK 판정 확정
OK 갭 리포트 생성 → 갭 리포트
OK C사 갭 1건(GAP-CONFIRM)
OK 기술 점검 안내
OK D사 갭 0건 — '의무 거의 없음' 안내
OK 학습 화면: 질문 5개, 시나리오 표 9행(A3+B2+C1+D2+E1)
OK 학습 화면 → 시나리오 E 미리 선택
OK 빈 고객 F사 등록: 자료 0건, 샘플 버튼 없음
OK 인벤토리 추출 → 인벤토리 검토
OK 판정 초안 생성 → 판정 초안
OK 빈 고객: 직접 올린 자료에서 시스템 2개 판정
OK 중복 이름 오류 표시
OK C사 담당자: 목록에 C사만, 등록 버튼 없음
OK 고객 담당자는 등록 화면 사용 불가
OK 고객 담당자가 A사 주소로 직접 가면 거절
pageerrors []
console errors []
```

- 그 뒤 새 DB에서 기존 `scripts/ui_click_smoke.py`(A사 흐름 클릭)도 다시 돌려 11개 항목 OK, `pageerrors []`.
- 이 과정에서 찾아 고친 것 2건: (1) 등록 화면에서 기존 고객 목록이 오기 전에 시나리오를 고르면 중복 이름을 제안하던 문제 → 목록을 받은 뒤에만 선택 가능하게 함. (2) 빈 고객 개요 화면에서 고객 정보가 오기 전 잠깐 샘플 버튼이 보이던 문제.
- `docs/guide/img/14~21`은 이 실행에서 찍은 화면입니다(1280px 폭, 일부는 위쪽만 잘라 저장).

## G. Docker

```
$ docker compose config -q     → 종료 코드 0
$ docker compose build api     → Cannot connect to the Docker daemon at unix:///var/run/docker.sock
```

**이번에도 이미지 빌드와 `docker compose up`은 실행하지 못했습니다**(이 세션에는 Docker 데몬이 없고, 이전 기록대로 Docker Hub도 차단). Dockerfile은 바꾸지 않았습니다. API 이미지는 `COPY app`·`COPY migrations`로 새 파일(`app/scenarios.py`, `app/data/scenarios/`, `migrations/002_*.sql`)을 포함하게 되어 있고, 컨테이너 시작 명령(`migrate → seed → uvicorn`)은 D·E에서 네이티브로 같은 순서를 확인했습니다. 맥의 기존 볼륨에서 `git pull && docker compose up --build`가 실제로 되는지는 사용자 환경에서 확인이 필요합니다.

## H. 이번 변경에서 검증하지 못한 것

| 항목 | 상태 |
|---|---|
| Docker 이미지 빌드·기존 볼륨에서의 `docker compose up --build` | 미검증(데몬 없음). 같은 마이그레이션을 네이티브 PostgreSQL 16에서만 확인 |
| 연습 시나리오 문서를 실제 LLM(Anthropic·내부 추론)으로 추출 | 미검증(키 없음). mock 규칙으로만 확인 |
| 학습 도우미·시나리오 설명의 법률 검토 | 없음. 법령 KB(`kb_v1.json`) 요약 범위 안에서만 작성 |
| 모바일 폭 화면 | 미확인(1280px 폭에서만 캡처) |
| 스크린 리더 등 접근성 도구 | 미확인(? 버튼에 aria-label·키보드 포커스만 넣음) |

## I. 정리

검증 후 `scripts/dev.sh down --purge`로 모든 프로세스를 중지하고 임시 PGDATA(`.devdata/`)를 삭제했습니다. `scripts/dev.sh status`는 web·api·demo·postgres 모두 중지, 8000·3000·8081·55432 포트에 남은 프로세스 없음. 이전 버전 확인용 작업 트리도 제거했습니다.

---

# 추가 검증 — 설문 8문항 예/아니오 전환 (2026-11-18)

등록 폼 "4. 현재 이행 상태"를 체크박스에서 **예(하고 있음) / 아니오(안 하고 있음)** 선택으로 바꾸고, 제34조 4문항을 안쪽 상자 "고영향 AI인 경우에만 해당 (제34조)"로 묶었습니다. 개요 화면의 "현재 이행 상태(설문)"도 같은 두 묶음, 예/아니오 배지로 바꿨습니다. API·DB는 바꾸지 않았습니다(답은 그대로 boolean, API로 직접 보낼 때 빠진 답은 전과 같이 false).

```
$ cd web && npx tsc --noEmit     → 출력 없음, 종료 코드 0
$ cd web && npm run build        → 성공 (/customers/new 포함 16개 경로)
$ cd api && python3 -m pytest -q → 93 passed
```

`scripts/dev.sh up`(새 DB, PostgreSQL 16, mock) 뒤 Playwright + Chromium(헤드리스, 1280px)으로 확인한 것 — 모두 OK, 페이지 오류 0건:

- 라디오 16개(8문항×2), 빈 고객은 미리 선택된 답 없음, 안쪽 상자에 제34조 4문항, 옛 안내문("모르면 비워 두세요") 없음
- 답하지 않고 등록 → 이동하지 않음, 문항 옆 "예 또는 아니오를 선택하세요" 8개 + 아래 요약 메시지. 7문항만 답해도 차단, 답한 문항의 안내는 사라짐
- 키보드 방향키로 예/아니오 전환
- 8문항 답하고 등록 → 개요 화면에 예 1 / 아니오 7, 안쪽 상자에 4항목
- `?scenario=c` → 8문항 미리 선택(예 6 / 아니오 2), 하나를 고쳐 등록하면 고친 답이 반영되고 가상 자료 4건 접수
- 시나리오에서 "빈 고객으로 시작"으로 바꾸면 선택이 모두 지워짐
- 390px 폭에서 가로 넘침 없음(예/아니오가 설명 아래로 내려감)

안쪽 상자 설명("해당 없으면 '아니오'로 두셔도 … 의무로 잡히지 않습니다")의 근거: `api/app/gap.py`는 판정 결과에 고영향 후보 시스템이 있을 때만 제34조 4항목(GAP-RISK·EXPLAIN·OVERSIGHT·RETENTION)을 봅니다. 기존 테스트의 D사(0건)·E사(3건, 제34조 갭 없음)가 4항목 모두 false인 상태에서 이를 확인합니다.

`docs/guide/img/15-register-form.jpg`는 이 실행에서 다시 찍었습니다. **다시 찍지 않은 것**: 개요 화면이 나오는 이전 캡처(`02-overview.jpg`, `16-overview-step-help.jpg` 등)에는 여전히 "있음/없음" 배지와 한 줄 목록이 보입니다. 스크린 리더 실제 낭독은 확인하지 않았습니다(radiogroup·aria-labelledby·aria-invalid만 넣음). `scripts/e2e_smoke.py`·`ui_click_smoke.py`는 이번에 다시 돌리지 않았습니다(등록 폼을 다루지 않음). 검증 후 `scripts/dev.sh down --purge`로 정리했습니다.

---

# 추가 검증 — 앱 안의 사용 가이드(`/guide`) + '경영진에게 한 줄' 삭제 (2026-11-18)

바꾼 것:

- 상단 메뉴에 **사용 가이드**(모든 역할, `AI 기본법 한눈에` 다음)를 넣고 `/guide`에서 `docs/USER_GUIDE.md`를 보여 줍니다. 서버에서 react-markdown 10.1.0 + remark-gfm 4.0.1 + rehype-slug 6.0.0으로 HTML을 만들고(빌드 때 정적 생성, 실행 중 API 호출 없음), 넓은 화면(1000px 이상)에서는 옆 목차가 따라옵니다.
- 웹 Docker 빌드 컨텍스트(`./web`)는 그대로 두고, `scripts/sync_guide.sh`가 원본(`docs/USER_GUIDE.md`, `docs/guide/img/`)을 `web/content/USER_GUIDE.md`, `web/public/guide/img/`로 복사합니다. `--check`는 사본이 다르면 종료 코드 1.
- 가이드(`docs/USER_GUIDE.md`, `docs/guide/index.html`)에서 화면별 **"경영진에게 한 줄"** 12개와 머리말의 해당 문구를 지웠습니다(`index.html`은 `.say` 블록과 CSS도 삭제). "10분 시연 순서", "예상 질문과 답"은 그대로입니다.

```
$ cd web && npx tsc --noEmit          → 출력 없음, 종료 코드 0
$ cd web && npm run build             → 성공 (/guide 는 ○ Static, 17개 경로)
$ cd api && python3 -m pytest -q      → 94 passed (test_guide_sync.py 1건 추가)
$ scripts/sync_guide.sh --check       → "가이드 사본이 원본과 같습니다 (USER_GUIDE.md + 이미지 22개)", 종료 코드 0
$ python3 scripts/e2e_smoke.py --api http://127.0.0.1:8000 --web http://127.0.0.1:3000 → E2E 스모크 테스트 통과
```

사본 불일치 검사가 실제로 실패하는지 (각각 확인 후 `scripts/sync_guide.sh`로 되돌림):

| 일부러 만든 차이 | `sync_guide.sh --check` | 그 밖 |
|---|---|---|
| `web/content/USER_GUIDE.md`에 한 줄 추가 | 종료 코드 1 | `npm run check:guide` 1, `pytest tests/test_guide_sync.py` 1 failed, `make build`가 `guide-check`에서 중단 |
| 사본 이미지 한 장의 내용 변경 | 종료 코드 1 (`… differ`) | |
| 사본에만 있는 이미지 추가 | 종료 코드 1 (`Only in web/public/guide/img`) | |
| 사본 이미지 한 장 삭제 / 원본에만 새 이미지 | 종료 코드 1 (`Only in docs/guide/img`) | |

`scripts/dev.sh up`(새 DB, PostgreSQL 16, mock, 새로 빌드한 standalone 서버) 뒤 Playwright + Chromium(헤드리스, 1280px)으로 확인한 것 — 모두 OK, 페이지 오류 0건, 4xx/5xx 응답 0건:

- 로그인하지 않고 `/guide`를 열면 `/login`으로 이동, 메뉴 없음
- `consultant@demo`, `a-company@demo`, `ops@demo` 모두 메뉴에 `사용 가이드`가 있고 눌러서 본문이 열림. 열려 있을 때 메뉴가 강조됨
- 본문: h2 22개, 표 20개, 화면에 "경영진에게 한 줄" 없음
- 이미지 22장: 주소가 `/guide/img/…`로 바뀌어 모두 HTTP 200, 브라우저에서 실제로 그려짐(naturalWidth > 0), 본문 폭을 넘지 않음
- `#`으로 시작하는 링크 44개(본문 목차 + 옆 목차) 모두 대상 id가 있음. 본문 목차의 `갭 리포트`를 누르면 "5. 갭 리포트 (단계 5)"로 이동, 옆 목차의 `예상 질문과 답`도 이동, `/guide#용어-풀이`를 주소로 바로 열어도 그 위치로 감
- 저장소의 다른 파일 링크 2개(`INFRASTRUCTURE.md`, `guide/index.html`)는 `https://github.com/DCP-Dev-7/ai-act-compliance/blob/main/docs/…`로 바뀜. 상대 경로로 남은 링크 0개
- 옆 목차는 1280px에서 sticky, 390px 폭에서는 숨기고(본문 맨 위 목차 사용) 가로 넘침 없음
- 고객사 현황 아래 안내문의 `사용 가이드에서 보기` 링크로 이동됨(컨설턴트·운영자에게만 보이는 안내문)

구현하다 고친 것: remark-gfm 기본값이 물결표 하나를 취소선으로 처리해 "B~E사 … 1~13번" 사이 글자에 줄이 그어졌습니다. `singleTilde: false`로 껐습니다.

`docs/guide/img/22-guide-in-app.jpg`는 이 실행에서 찍었습니다(1280×900, 컨설턴트 계정).

검증하지 못한 것 / 알아 둘 것:

| 항목 | 상태 |
|---|---|
| Docker 이미지 빌드(`docker compose up --build`)에서 `/guide` | **미검증**(이 환경에 Docker 데몬 없음). 사본은 `web/` 안에 커밋돼 있고 Dockerfile의 `COPY . .`와 `COPY public`으로 들어가도록 했지만 실제 이미지에서 확인하지 못함 |
| GitHub 링크 2개가 실제로 열리는지 | 미확인(주소 형식만 확인. 저장소가 비공개면 GitHub 로그인이 필요) |
| `/guide`의 로그인 보호 수준 | 다른 화면과 같은 방식(브라우저에서 세션 확인 후 `/login` 이동)입니다. 가이드는 정적 페이지라 **본문 글자와 캡처 파일(`/guide/img/*`)은 로그인 없이 주소를 직접 요청하면 내려받을 수 있습니다**. 가상 데이터라 그대로 두었고, 막으려면 서버 쪽 세션 검사가 따로 필요 |
| `docs/guide/index.html` | "경영진에게 한 줄"만 지웠습니다. 그 밖의 내용은 `USER_GUIDE.md`보다 오래됐을 수 있고 동기화 대상이 아님. 브라우저로 열어 보지는 않음 |
| 가이드의 1~21번 캡처 | 다시 찍지 않음. 상단 메뉴에 `사용 가이드`가 없는 화면이 그대로임(가이드 머리말에 적어 둠) |
| 스크린 리더 | 미확인 |

정리: 검증 후 `scripts/dev.sh down --purge`. `scripts/dev.sh status`는 web·api·demo·postgres 모두 중지.
