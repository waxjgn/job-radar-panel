-- 打工避雷平台 —— 数据库表结构（SQLite 版本）
-- 说明：INTEGER PRIMARY KEY AUTOINCREMENT 是 SQLite 写法；
--      面板在生成 MySQL 脚本时会自动替换为 AUTO_INCREMENT。

CREATE TABLE IF NOT EXISTS company (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    industry    TEXT,
    city        TEXT,
    scale       TEXT,
    risk_level  INTEGER NOT NULL DEFAULT 0,      -- 0=未知 1=轻微 2=中等 3=严重
    tags        TEXT,                            -- 逗号分隔，例如 拖欠工资,强制加班
    summary     TEXT,
    created_at  TEXT    DEFAULT (datetime('now','localtime')),
    updated_at  TEXT    DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_company_name ON company(name);
CREATE INDEX IF NOT EXISTS idx_company_city ON company(city);

CREATE TABLE IF NOT EXISTS report (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL,
    category    TEXT    NOT NULL,                -- 拖欠工资 / 虚假招聘 / 强制加班 / 押金诈骗 ...
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    video_url   TEXT,                            -- 必须命中白名单域名
    city        TEXT,
    job         TEXT,
    contact     TEXT,
    status      TEXT    NOT NULL DEFAULT 'pending', -- pending / approved / rejected
    ip_hash     TEXT,
    created_at  TEXT    DEFAULT (datetime('now','localtime')),
    reviewed_at TEXT,
    FOREIGN KEY (company_id) REFERENCES company(id)
);
CREATE INDEX IF NOT EXISTS idx_report_company ON report(company_id);
CREATE INDEX IF NOT EXISTS idx_report_status ON report(status);

CREATE TABLE IF NOT EXISTS review_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   INTEGER NOT NULL,
    rule        TEXT,                            -- 命中的规则名，空表示通过
    action      TEXT NOT NULL,                   -- pass / hold / reject
    detail      TEXT,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS rate_limit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_hash     TEXT NOT NULL,
    window_key  TEXT NOT NULL,                   -- 例如 2026-10-13T14:05
    hits        INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(ip_hash, window_key)
);

CREATE TABLE IF NOT EXISTS video_allowlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL UNIQUE,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS admin_user (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);
