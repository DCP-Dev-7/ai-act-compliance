export const FIELD_LABELS: Record<string, string> = {
  name: "시스템 이름",
  purpose: "목적",
  provider_type: "모델 조달 방식",
  model_provider: "모델·공급자",
  is_generative: "생성형 여부",
  output_types: "산출물 유형",
  user_type: "이용자 유형",
  realistic_synthetic: "실제와 구분 어려운 합성물",
  domain: "고영향 영역",
  significant_impact: "중대한 영향(2단계)",
  human_review: "사람의 실질 검토",
  deployed_to_users: "이용자 제공 여부",
  cumulative_flops: "누적 연산량(FLOPs)",
  foreign_operator: "해외 사업자",
  other_law_compliance: "타 법령 이행",
};

const VALUE_LABELS: Record<string, Record<string, string>> = {
  provider_type: { external_api: "외부 API 이용", self_developed: "자체 개발", unknown: "미확인" },
  user_type: { B2C: "B2C(소비자·이용자)", B2B: "B2B(기업)", internal: "내부 업무용", unknown: "미확인" },
  human_review: { substantive: "실질적 검토", formal: "형식적 검토", none: "검토 없음", unknown: "미확인" },
};
const OUTPUT: Record<string, string> = { text: "텍스트", image: "이미지", audio: "음성", video: "영상" };

export function fmtValue(field: string, value: unknown, domainLabels?: Record<string, string>): string {
  if (value === null || value === undefined || value === "") return "미확인";
  if (typeof value === "boolean") return value ? "예" : "아니오";
  if (Array.isArray(value)) return value.length ? value.map((v) => OUTPUT[String(v)] ?? String(v)).join(", ") : "없음";
  if (field === "domain") return domainLabels?.[String(value)] ?? String(value);
  return VALUE_LABELS[field]?.[String(value)] ?? String(value);
}

export const DOC_KIND: Record<string, string> = {
  questionnaire: "설문 응답",
  service_intro: "서비스 소개서",
  tos: "이용약관",
  dev_doc: "개발 문서",
  other: "기타",
};

export const EVIDENCE_KIND: Record<string, string> = {
  classification: "확정 판정서",
  tech_check: "기술 점검 결과",
  gateway_log: "AI 게이트웨이 로그",
  "document:notice_texts": "승인 문서 — 사전 고지 문구",
  "document:tos_clause": "승인 문서 — 약관 AI 조항",
  "document:gap_report": "승인 문서 — 갭 리포트",
  "document:risk_policy": "승인 문서 — 위험관리 정책",
  "document:impact_checklist": "승인 문서 — 영향평가 체크리스트",
};

// '현재 이행 상태' 설문 중 고영향 AI에만 요구되는 항목(제34조). 갭 리포트는 고영향 후보 시스템이 있을 때만 이 항목을 본다.
const HIGH_IMPACT_STATE_KEYS = new Set(["risk_policy", "explanation_method", "human_oversight_killswitch", "doc_retention_5y"]);
export const isHighImpactStateKey = (key: string) => HIGH_IMPACT_STATE_KEYS.has(key);
