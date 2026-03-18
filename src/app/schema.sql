CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(kind, name)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    external_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    url TEXT NOT NULL,
    authors_json TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    raw_summary TEXT,
    raw_payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_type TEXT,
    fit_tag TEXT,
    relevance_for_work REAL,
    relevance_for_llm_learning REAL,
    applicability_score REAL,
    deterministic_score REAL,
    llm_score REAL,
    final_score REAL,
    selected_for_issue INTEGER NOT NULL DEFAULT 0,
    issue_id INTEGER REFERENCES issues(id),
    generated_summary TEXT,
    generated_why_it_matters TEXT,
    why_you_should_care_generated TEXT,
    selection_reason_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    subject TEXT NOT NULL,
    model_name TEXT NOT NULL,
    status TEXT NOT NULL,
    html_body TEXT NOT NULL,
    json_payload TEXT NOT NULL,
    sent_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    section_name TEXT NOT NULL,
    rank_in_section INTEGER NOT NULL,
    UNIQUE(issue_id, item_id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    shortlisted_count INTEGER NOT NULL DEFAULT 0,
    selected_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    logs_json TEXT
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS repo_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(repo_name, repo_path)
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    explicit_profile_json TEXT NOT NULL,
    aggregated_repo_profile_json TEXT NOT NULL,
    learned_preferences_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    freshness_score REAL NOT NULL,
    source_quality_score REAL NOT NULL,
    work_relevance_score REAL NOT NULL,
    llm_map_value_score REAL NOT NULL,
    architectural_tradeoff_score REAL NOT NULL,
    practical_reusability_score REAL NOT NULL,
    interview_background_score REAL NOT NULL,
    repo_profile_match_score REAL NOT NULL,
    traction_score REAL NOT NULL,
    theoretical_penalty REAL NOT NULL,
    hype_penalty REAL NOT NULL,
    genericity_penalty REAL NOT NULL,
    feature_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(item_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    vote TEXT NOT NULL,
    context_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_topic ON items(topic);
CREATE INDEX IF NOT EXISTS idx_items_normalized_title ON items(normalized_title);
CREATE INDEX IF NOT EXISTS idx_items_url ON items(url);
CREATE INDEX IF NOT EXISTS idx_items_content_hash ON items(content_hash);
CREATE INDEX IF NOT EXISTS idx_items_issue_id ON items(issue_id);
CREATE INDEX IF NOT EXISTS idx_items_fit_tag ON items(fit_tag);
CREATE INDEX IF NOT EXISTS idx_issues_subject ON issues(subject);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_repo_profiles_active ON repo_profiles(is_active);
CREATE INDEX IF NOT EXISTS idx_feedback_issue_id ON feedback(issue_id);
CREATE INDEX IF NOT EXISTS idx_feedback_item_id ON feedback(item_id);
