-- ORM 모델에서 생성됨 (python -m app.migrate --print-schema). 직접 수정하지 말 것.

CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	actor VARCHAR(200) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	entity VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(60) NOT NULL, 
	customer_id INTEGER, 
	detail JSON NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE control_mappings (
	id SERIAL NOT NULL, 
	kb_version VARCHAR(40) NOT NULL, 
	clause_id VARCHAR(60) NOT NULL, 
	isms_p TEXT NOT NULL, 
	iso42001 TEXT NOT NULL, 
	note TEXT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE customers (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	employees INTEGER NOT NULL, 
	is_synthetic BOOLEAN NOT NULL, 
	allow_external BOOLEAN NOT NULL, 
	monthly_budget_usd FLOAT NOT NULL, 
	subscribed BOOLEAN NOT NULL, 
	current_state JSON NOT NULL, 
	tech_targets JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE golden_runs (
	id SERIAL NOT NULL, 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	config_name VARCHAR(100) NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	total INTEGER NOT NULL, 
	matched INTEGER NOT NULL, 
	rate FLOAT NOT NULL, 
	engine_rate FLOAT NOT NULL, 
	threshold FLOAT NOT NULL, 
	passed BOOLEAN NOT NULL, 
	mismatches JSON NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE job_runs (
	id SERIAL NOT NULL, 
	job VARCHAR(60) NOT NULL, 
	trigger VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	detail JSON NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE kb_clauses (
	id SERIAL NOT NULL, 
	kb_version VARCHAR(40) NOT NULL, 
	clause_id VARCHAR(60) NOT NULL, 
	article VARCHAR(60) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	summary TEXT NOT NULL, 
	obligations JSON NOT NULL, 
	sources JSON NOT NULL, 
	applies_when JSON, 
	content_hash VARCHAR(64) NOT NULL, 
	position INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (kb_version, clause_id)
);

CREATE TABLE kb_versions (
	id SERIAL NOT NULL, 
	version VARCHAR(40) NOT NULL, 
	label VARCHAR(300) NOT NULL, 
	effective_date VARCHAR(20) NOT NULL, 
	notice TEXT NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	applied_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (version)
);

CREATE TABLE llm_usage (
	id SERIAL NOT NULL, 
	customer_id INTEGER, 
	task VARCHAR(60) NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	model VARCHAR(100) NOT NULL, 
	input_tokens INTEGER NOT NULL, 
	output_tokens INTEGER NOT NULL, 
	cost_usd FLOAT NOT NULL, 
	note VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE model_configs (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	model VARCHAR(100) NOT NULL, 
	prompt_version VARCHAR(40) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	last_rate FLOAT, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE ai_systems (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	attributes JSON NOT NULL, 
	extracted_by VARCHAR(60) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE change_events (
	id SERIAL NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	customer_id INTEGER, 
	title VARCHAR(300) NOT NULL, 
	payload JSON NOT NULL, 
	created_by VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE documents (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	content TEXT NOT NULL, 
	data JSON, 
	uploaded_by VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE engagements (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	state VARCHAR(40) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (customer_id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE evidence_items (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	seq INTEGER NOT NULL, 
	kind VARCHAR(60) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	content_type VARCHAR(100) NOT NULL, 
	size INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	prev_hash VARCHAR(64) NOT NULL, 
	chain_hash VARCHAR(64) NOT NULL, 
	retention_until TIMESTAMP WITH TIME ZONE NOT NULL, 
	meta JSON NOT NULL, 
	created_by VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (customer_id, seq), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE gap_reports (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	kb_version VARCHAR(40) NOT NULL, 
	findings JSON NOT NULL, 
	html TEXT NOT NULL, 
	created_by VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE tech_checks (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	target VARCHAR(300) NOT NULL, 
	results JSON NOT NULL, 
	passed INTEGER NOT NULL, 
	failed INTEGER NOT NULL, 
	evidence_id INTEGER, 
	triggered_by VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	email VARCHAR(200) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	password_hash VARCHAR(300) NOT NULL, 
	customer_id INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE TABLE classifications (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	system_id INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	kb_version VARCHAR(40) NOT NULL, 
	result JSON NOT NULL, 
	confirmed_by VARCHAR(200), 
	confirmed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (system_id, version), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(system_id) REFERENCES ai_systems (id)
);

CREATE TABLE facts (
	id SERIAL NOT NULL, 
	system_id INTEGER NOT NULL, 
	field VARCHAR(60) NOT NULL, 
	value JSON, 
	doc_id INTEGER, 
	quote TEXT NOT NULL, 
	span_start INTEGER, 
	span_end INTEGER, 
	source VARCHAR(40) NOT NULL, 
	supported BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(system_id) REFERENCES ai_systems (id), 
	FOREIGN KEY(doc_id) REFERENCES documents (id)
);

CREATE TABLE generated_documents (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	system_id INTEGER, 
	kind VARCHAR(40) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	version INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	paragraphs JSON NOT NULL, 
	html TEXT NOT NULL, 
	provider VARCHAR(60) NOT NULL, 
	approved_by VARCHAR(200), 
	approved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(system_id) REFERENCES ai_systems (id)
);

CREATE TABLE reassessment_tasks (
	id SERIAL NOT NULL, 
	customer_id INTEGER NOT NULL, 
	system_id INTEGER, 
	classification_id INTEGER, 
	change_event_id INTEGER NOT NULL, 
	reason TEXT NOT NULL, 
	clause_ids JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	resolved_by VARCHAR(200), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(system_id) REFERENCES ai_systems (id), 
	FOREIGN KEY(classification_id) REFERENCES classifications (id), 
	FOREIGN KEY(change_event_id) REFERENCES change_events (id)
);
