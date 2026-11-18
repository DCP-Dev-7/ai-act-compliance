-- 002: 고객사 등록·연습 시나리오. 추가만 한다(기존 컬럼·테이블·데이터는 건드리지 않음). 여러 번 실행해도 안전.

ALTER TABLE customers ADD COLUMN IF NOT EXISTS industry VARCHAR(60) NOT NULL DEFAULT '';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS scenario VARCHAR(40) NOT NULL DEFAULT '';

-- 이전 버전에서 시드된 A사(가상)에 시나리오 표시만 채운다(샘플 자료 불러오기 대상 구분용).
UPDATE customers SET scenario = 'a' WHERE name = 'A사 (가상)' AND scenario = '';
UPDATE customers SET industry = '전자상거래·유통' WHERE name = 'A사 (가상)' AND industry = '';
