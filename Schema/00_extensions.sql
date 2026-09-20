-- ============================================================================
-- Haven Builders ERP — PostgreSQL extensions
-- Run once per database, before 01_platform_schema.sql / 02_tenant_schema.sql
-- ============================================================================

-- Case-insensitive TEXT type — replaces SQLite's "COLLATE NOCASE" usage
-- (companies.slug, users.email).
CREATE EXTENSION IF NOT EXISTS citext;

-- Optional but recommended once real query volume shows up: trigram search
-- for "search customers by name/CNIC/phone" style lookups.
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
