#!/bin/bash
# Deploy da AURA na VPS.
#
#   bash deploy-vps.sh
#
# Requer: git, docker e o arquivo secrets.env ao lado deste script (não
# versionado). Faz pull da branch, build, recreate e checa se o painel
# respondeu.

set -euo pipefail
cd "$(dirname "$0")"

BRANCH="${AURA_BRANCH:-feat/painel-multiserver}"
CONTAINER="${AURA_CONTAINER:-aura-bot}"
PORTA="${AURA_PORTA:-2501}"

echo "==> secrets.env"
if [ ! -f secrets.env ]; then
  echo "ERRO: secrets.env não existe aqui. Sem ele o bot não sobe." >&2
  exit 1
fi
chmod 600 secrets.env

echo "==> buscando $BRANCH"
git fetch --depth 1 origin "$BRANCH"
git reset --hard FETCH_HEAD
git log --oneline -1

echo "==> build"
docker compose build

echo "==> subindo"
docker compose up -d --force-recreate

echo "==> aguardando o painel responder"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORTA}/health" >/dev/null 2>&1; then
    echo "painel respondeu em ${i}s"
    curl -sS "http://127.0.0.1:${PORTA}/health"; echo
    docker ps --filter "name=${CONTAINER}" --format '{{.Names}}|{{.Status}}'
    exit 0
  fi
  sleep 1
done

echo "ERRO: o painel não respondeu em 30s. Últimas linhas do log:" >&2
docker logs --tail 40 "$CONTAINER" >&2
exit 1