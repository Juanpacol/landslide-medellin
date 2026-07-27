-- ============================================================================
-- Separación de privilegios DDL — TEYVA
--
-- Se corre A MANO en el SQL Editor de Supabase (que ejecuta como `postgres`,
-- dueño de las 18 tablas). NO lo aplica Alembic: crear roles y otorgar
-- privilegios es configuración de la instancia, no del esquema.
--
-- Objetivo: que el rol con el que corren la app, los scrapers y el desarrollo
-- local NO pueda ejecutar DDL. Así, aplicar una migración desde un portátil es
-- imposible por construcción — la prevención del incidente del 2026-07-26.
--
-- El rol con DDL sigue siendo `postgres` (ya es dueño de las tablas); lo que
-- cambia es que su password se rota y queda solo como secret de GitHub.
-- Crear un rol migrador nuevo obligaría a resolver ownership (un no-dueño no
-- puede ALTER/DROP). Lo escaso debe ser la credencial, no el rol.
--
-- LEE docs/RUNBOOK_MIGRATIONS.md antes de correr esto.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- PASO 0 — Reconocimiento (solo lectura, corre esto primero)
-- ---------------------------------------------------------------------------
SELECT current_user, version();

SELECT rolname, rolsuper, rolcreaterole, rolbypassrls
FROM pg_roles
WHERE rolname IN ('postgres', 'anon', 'authenticated', 'service_role');

-- Estado de RLS. Las 18 tablas deben salir con rls_on=true y n_policies=0:
-- ese es el estado que dejó la migración a1b2c3d4e5f6.
SELECT c.relname,
       c.relrowsecurity AS rls_on,
       (SELECT count(*) FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = c.relname) AS n_policies
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY 1;


-- ---------------------------------------------------------------------------
-- PASO 1 — Crear el rol de aplicación
--
-- Genera la password FUERA de Supabase con:  openssl rand -hex 24
-- Usa hex a propósito: un '@' o '#' en la password rompe la connection string
-- en silencio (se interpreta como separador de host).
-- ---------------------------------------------------------------------------
CREATE ROLE teyva_app WITH
  LOGIN
  PASSWORD '<PEGA_AQUI_LA_PASSWORD>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

ALTER ROLE teyva_app SET search_path = public;


-- ---------------------------------------------------------------------------
-- PASO 2 — RLS: el riesgo #1 de todo este cambio
--
-- Las 18 tablas tienen RLS habilitado SIN policies. Hoy nada falla porque
-- `postgres` es dueño (los dueños saltan RLS) y además tiene BYPASSRLS.
-- Un rol nuevo sin eso quedaría con LECTURAS DEVOLVIENDO 0 FILAS EN SILENCIO
-- — y el síntoma (records_valid=0, status=ok) es indistinguible de "sin
-- eventos nuevos", que es el estado normal del sistema.
--
-- La postura de seguridad NO cambia: el objetivo del RLS era cerrar la API
-- REST de PostgREST (anon/authenticated), y eso sigue intacto — esos roles no
-- tienen bypass y no hay policies.
-- ---------------------------------------------------------------------------
ALTER ROLE teyva_app BYPASSRLS;

-- Si lo anterior falla con "must be superuser to change bypassrls attribute"
-- (pasa en PG <= 15), usa este fallback en su lugar. Contrapartida: CADA TABLA
-- NUEVA con RLS necesitará su policy, o vuelve el fallo silencioso.
--
-- DO $$
-- DECLARE t text;
-- BEGIN
--   FOREACH t IN ARRAY ARRAY[
--     'seismic_events','alembic_version','agent_conversations','ml_features',
--     'risk_predictions','landslide_events','scraping_logs','rainfall_timeseries',
--     'commune_thresholds','alert_log','app_settings','risk_explanations',
--     'barrio_hazard','citizen_reports','mesh_quadrants','safe_zones',
--     'audit_log','agent_run_logs']
--   LOOP
--     EXECUTE format(
--       'CREATE POLICY teyva_app_all ON public.%I AS PERMISSIVE FOR ALL '
--       'TO teyva_app USING (true) WITH CHECK (true)', t);
--   END LOOP;
-- END $$;


-- ---------------------------------------------------------------------------
-- PASO 3 — Privilegios: DML sí, DDL no
--
-- No hace falta revocar DDL explícitamente: en Postgres el DDL no es un
-- privilegio otorgable, depende de ownership (ALTER/DROP requieren ser dueño)
-- y de CREATE sobre el esquema. Con NOSUPERUSER + sin ownership + sin CREATE,
-- teyva_app es DDL-incapaz por construcción.
-- ---------------------------------------------------------------------------
GRANT CONNECT ON DATABASE postgres TO teyva_app;
GRANT USAGE ON SCHEMA public TO teyva_app;

-- USAGE != CREATE. Sin este REVOKE podría crear tablas nuevas.
REVOKE CREATE ON SCHEMA public FROM teyva_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- DELETE se omite a propósito: no hay un solo DELETE en el código
-- (verificado por grep en api/, scraper/, ml/, monitoring/, application/,
-- infrastructure/, agent/, alerts/).
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO teyva_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO teyva_app;

-- Tablas y secuencias FUTURAS. Aplica a lo que cree `postgres`, que es
-- justamente el rol con el que corre Alembic. No es retroactivo.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO teyva_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO teyva_app;

-- Cinturón extra sobre el incidente concreto: la app LEE alembic_version
-- (el migration_guard lo necesita) pero jamás la escribe.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.alembic_version FROM teyva_app;


-- ---------------------------------------------------------------------------
-- PASO 4 — Verificar (como `postgres`, desde el editor)
--
-- Esperado: 18 filas con sel/ins/upd = true, salvo alembic_version que debe
-- quedar sel=true, ins=false, upd=false. Y puede_crear_tablas = false.
-- ---------------------------------------------------------------------------
SELECT c.relname,
       has_table_privilege('teyva_app', c.oid, 'SELECT') AS sel,
       has_table_privilege('teyva_app', c.oid, 'INSERT') AS ins,
       has_table_privilege('teyva_app', c.oid, 'UPDATE') AS upd
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY 1;

SELECT has_schema_privilege('teyva_app', 'public', 'CREATE') AS puede_crear_tablas;  -- false
SELECT rolbypassrls FROM pg_roles WHERE rolname = 'teyva_app';                        -- true


-- ---------------------------------------------------------------------------
-- PASO 5 — Verificar CONECTADO COMO teyva_app (psql, no el editor)
--
--   psql "postgresql://teyva_app.<PROJECT_REF>:<PWD>@aws-1-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require"
--
-- Ojo: el pooler de Supabase deriva el tenant del formato usuario.<ref>.
-- Si rechaza el rol personalizado, TODO este plan queda bloqueado — se
-- descubre aquí, antes de tocar nada de producción.
-- ---------------------------------------------------------------------------

-- 5a. DDL debe FALLAR (los 5 deben dar error):
--   CREATE TABLE public.ddl_probe(id int);              -- permission denied for schema public
--   ALTER TABLE public.agent_run_logs ADD COLUMN x int; -- must be owner of table
--   DROP TABLE public.scraping_logs;                    -- must be owner of table
--   UPDATE public.alembic_version SET version_num='x';  -- permission denied for table
--   CREATE SCHEMA sneaky;                               -- permission denied for database

-- 5b. DML debe FUNCIONAR. El INSERT ... RETURNING id prueba de una sola vez
-- el GRANT de tabla, el USAGE sobre la secuencia y que RLS no bloquea:
--   BEGIN;
--   INSERT INTO agent_run_logs(agent_name,status,summary,detail)
--   VALUES ('privilege-check','ok','probe de separación DDL','{}'::json) RETURNING id;
--   SELECT version_num FROM alembic_version;
--   ROLLBACK;

-- 5c. DETECTOR DEL FALLO SILENCIOSO DE RLS — la verificación más importante.
-- Estos conteos deben COINCIDIR con los mismos corridos como `postgres`.
-- Un 0 donde postgres ve miles significa que RLS está filtrando:
--   SELECT 'rainfall_timeseries' t, count(*) FROM rainfall_timeseries
--   UNION ALL SELECT 'risk_predictions', count(*) FROM risk_predictions
--   UNION ALL SELECT 'ml_features',      count(*) FROM ml_features
--   UNION ALL SELECT 'landslide_events', count(*) FROM landslide_events
--   UNION ALL SELECT 'scraping_logs',    count(*) FROM scraping_logs
--   UNION ALL SELECT 'agent_run_logs',   count(*) FROM agent_run_logs;


-- ---------------------------------------------------------------------------
-- ROLLBACK — si algo sale mal
--
-- Antes de esto: devuelve los secrets DATABASE_URL y DATABASE_URL_SYNC a los
-- valores de `postgres` en GitHub (2 min, sin deploy). Eso solo ya restaura
-- el sistema. Lo de abajo es para limpiar el rol.
-- ---------------------------------------------------------------------------
-- ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
--   REVOKE SELECT, INSERT, UPDATE ON TABLES FROM teyva_app;
-- ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
--   REVOKE USAGE, SELECT ON SEQUENCES FROM teyva_app;
-- DROP OWNED BY teyva_app;   -- revoca todos los GRANTs otorgados al rol
-- DROP ROLE teyva_app;
