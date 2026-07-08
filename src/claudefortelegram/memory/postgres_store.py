# Postgres-backed implementation of the memory store interface (asyncpg pool,
# DATABASE_URL from Railway's Postgres plugin). Applies db/schema.sql on startup
# if the `memories` table doesn't exist yet. This is the ONLY table in the DB —
# raw conversation turns are never written here, only explicit "remember this" facts.
