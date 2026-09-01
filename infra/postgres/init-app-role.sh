#!/bin/bash
# Creates the application role the ledger connects as.
#
# RLS does not apply to a superuser, and does not apply to a table's owner unless the table
# is FORCE'd. The compose superuser owns the schema and runs migrations; the application must
# therefore connect as something else, or the row-level security policies in 0001 are inert
# and entity isolation rests on service-layer filtering alone. ADR-0003 asks for two layers
# precisely because "RLS misconfiguration is silent".
#
# This runs only on first initialisation of an empty data directory, which is what
# `docker compose down -v` gives you. A managed deployment creates this role out of band;
# infra/README.md is authoritative for the name and the privileges it needs.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	CREATE ROLE cfokit_app
	    LOGIN
	    PASSWORD '${POSTGRES_APP_PASSWORD:-cfokit_app}'
	    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
SQL
