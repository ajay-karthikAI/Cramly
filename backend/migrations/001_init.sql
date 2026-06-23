create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    password_hash text not null,
    created_at timestamptz not null default now()
);

create table if not exists documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    name text not null,
    storage_key text not null,
    raw_text text not null,
    keywords jsonb not null default '[]'::jsonb,
    status text not null default 'processing',
    chunks integer not null default 0,
    created_at timestamptz not null default now()
);

alter table documents
    add column if not exists user_id uuid references users(id) on delete cascade;

create table if not exists document_chunks (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents(id) on delete cascade,
    chunk_index integer not null,
    section text not null,
    content text not null,
    embedding vector(1536) not null,
    created_at timestamptz not null default now()
);

create index if not exists document_chunks_embedding_idx
    on document_chunks using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

create table if not exists quiz_attempts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    quiz_id text not null,
    question_id text not null,
    topic text not null,
    selected_answer text,
    correct_answer text,
    correct boolean not null,
    created_at timestamptz not null default now()
);

alter table quiz_attempts
    add column if not exists user_id uuid references users(id) on delete cascade;
alter table quiz_attempts
    add column if not exists selected_answer text;
alter table quiz_attempts
    add column if not exists correct_answer text;

create table if not exists flashcards (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    question text not null,
    answer text not null,
    topic text not null,
    source_label text not null,
    interval_days integer not null default 0,
    ease numeric not null default 2.5,
    due_at timestamptz not null default now(),
    last_reviewed_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists quizzes (
    id uuid primary key,
    user_id uuid not null references users(id) on delete cascade,
    source_label text not null,
    questions jsonb not null default '[]'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists study_plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    focus_topics jsonb not null default '[]'::jsonb,
    plan jsonb not null default '[]'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists daily_usage (
    user_id uuid not null references users(id) on delete cascade,
    usage_date date not null,
    category text not null,
    usage_count integer not null default 0,
    updated_at timestamptz not null default now(),
    primary key (user_id, usage_date, category)
);

create index if not exists users_email_idx on users(email);
create index if not exists documents_user_id_idx on documents(user_id);
create index if not exists quiz_attempts_topic_idx on quiz_attempts(topic);
create index if not exists quiz_attempts_user_id_idx on quiz_attempts(user_id);
create index if not exists flashcards_user_due_idx on flashcards(user_id, due_at);
create index if not exists quizzes_user_created_idx on quizzes(user_id, created_at desc);
create index if not exists study_plans_user_created_idx on study_plans(user_id, created_at desc);
create index if not exists daily_usage_user_date_idx on daily_usage(user_id, usage_date);
