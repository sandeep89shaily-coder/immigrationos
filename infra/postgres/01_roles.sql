-- Local development only. Production: provision separate non-superuser roles with a secret manager.
-- Migration owner has BYPASSRLS ONLY for schema administration and narrowly
-- granted SECURITY DEFINER membership checks. Never use it for API traffic.
CREATE ROLE immigrationos_migrator LOGIN BYPASSRLS PASSWORD 'dev_only_migrator';
CREATE ROLE immigrationos_app LOGIN PASSWORD 'dev_only_app';
GRANT CONNECT ON DATABASE immigrationos_dev TO immigrationos_migrator, immigrationos_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO immigrationos_migrator;
GRANT USAGE ON SCHEMA public TO immigrationos_app;
-- No blanket table defaults: migration grants only the exact operations needed.
