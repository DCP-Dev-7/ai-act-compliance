.PHONY: up down purge status test golden e2e build compose-up compose-down

up:            ## 네이티브 실행(임시 Postgres + API + demo-service + 웹)
	scripts/dev.sh up
down:          ## 네이티브 중지
	scripts/dev.sh down
purge:         ## 네이티브 중지 + 임시 데이터 삭제
	scripts/dev.sh down --purge
status:
	scripts/dev.sh status
test:          ## API 단위 테스트
	cd api && python3 -m pytest -q
golden:        ## 골든셋 일치율 리포트
	cd api && python3 -m app.golden
e2e:           ## 실행 중인 서비스에 E2E 스모크
	python3 scripts/e2e_smoke.py --api http://127.0.0.1:8000 --web http://127.0.0.1:3000
build:         ## 웹 타입체크 + 빌드
	cd web && npx tsc --noEmit && npm run build
compose-up:    ## 도커 실행
	docker compose up --build
compose-down:
	docker compose down
