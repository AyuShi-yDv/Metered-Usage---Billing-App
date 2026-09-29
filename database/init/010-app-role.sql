-- Runs only when a PostgreSQL data directory is initialized for the first time.
-- Compose passes one database-specific role/password into each DB container.
\getenv app_user APP_DB_USER
\getenv app_password APP_DB_PASSWORD
\getenv app_database POSTGRES_DB

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password') \gexec
GRANT CONNECT ON DATABASE :"app_database" TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
CREATE EXTENSION IF NOT EXISTS btree_gist;
