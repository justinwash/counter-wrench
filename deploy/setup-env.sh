#!/bin/sh
# Run once on the server (and again to change a secret): writes .env and the site login.
# Asks for the secrets without showing them; nothing here is committed or printed.
set -e
cd "$(dirname "$0")/.."

printf "OpenRouter API key (the capped production key): "; stty -echo; read -r OPENROUTER_API_KEY; stty echo; echo
printf "LangSmith API key: "; stty -echo; read -r LANGSMITH_API_KEY; stty echo; echo
printf "Site login username: "; read -r SITE_USER
printf "Site login password: "; stty -echo; read -r SITE_PASSWORD; stty echo; echo

# Postgres is only reachable from inside Docker, but give it a real password anyway. Keep the
# existing one when re-running: Postgres sets its password once, when its data volume is first
# created, so a new one here would lock the app out of the database.
DB_PASSWORD=$(grep '^POSTGRES_PASSWORD=' .env 2>/dev/null | cut -d= -f2-)
[ -n "$DB_PASSWORD" ] || DB_PASSWORD=$(openssl rand -hex 24)
umask 077
cat > .env <<ENV
OPENROUTER_API_KEY=$OPENROUTER_API_KEY
AGENT_MODEL=openrouter:anthropic/claude-haiku-5.5
TRIAGE_MODEL=openrouter:anthropic/claude-haiku-5.5
JUDGE_MODEL=openrouter:openai/gpt-6.1-sol
OPENROUTER_PROVIDER_ORDER=anthropic,openai
LANGSMITH_API_KEY=$LANGSMITH_API_KEY
POSTGRES_USER=counterwrench
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_DB=counterwrench
ENV

HASH=$(docker run --rm caddy:2.10.2-alpine caddy hash-password --plaintext "$SITE_PASSWORD")
printf '%s %s\n' "$SITE_USER" "$HASH" > deploy/site-users
chmod 644 deploy/site-users  # Caddy reads it; it holds only a bcrypt hash
echo "Wrote .env and deploy/site-users. Login: $SITE_USER"
