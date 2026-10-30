#!/usr/bin/env bash
# Bundles the docker compose setup for a release: docker-compose.yml (the prod file, with
# TAG defaulting to the release's images), the optional Keycloak file, its realm and the
# settings template.
# Usage: .github/scripts/compose-bundle.sh <version> <image tag> <output directory>
set -euo pipefail

version="$1"
tag="$2"
out="$3"
root="$(cd "$(dirname "$0")/../.." && pwd)"
name="advanced-llm-chat-compose-$version"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
dir="$work/$name"
mkdir -p "$dir/keycloak" "$out"

sed 's|${TAG:-develop-latest}|${TAG:-'"$tag"'}|g' "$root/docker/docker-compose.prod.yml" > "$dir/docker-compose.yml"
grep -q "TAG:-$tag}" "$dir/docker-compose.yml" || { echo "TAG default not replaced" >&2; exit 1; }
sed 's|${KEYCLOAK_REALM_FILE:-../helm/advanced-llm-chat/files/llm-chat-realm.json}|${KEYCLOAK_REALM_FILE:-./keycloak/llm-chat-realm.json}|' \
  "$root/docker/docker-compose.keycloak.yml" > "$dir/docker-compose.keycloak.yml"
grep -q "KEYCLOAK_REALM_FILE:-./keycloak/" "$dir/docker-compose.keycloak.yml" || { echo "realm path not replaced" >&2; exit 1; }
cp "$root/helm/advanced-llm-chat/files/llm-chat-realm.json" "$dir/keycloak/"
cp "$root/docker/.env.example" "$dir/.env.example"

cat > "$dir/README.md" <<EOF
# Advanced LLM Chat $version (docker compose)

The images are \`ghcr.io/knaeckebrothero/advanced-llm-chat-{frontend,backend}:$tag\`.

1. \`cp .env.example .env\` and fill it in (at least \`POSTGRES_PASSWORD\` and a model provider key).
2. Start it: \`docker compose up -d\`. The frontend is at http://localhost:8080, the backend at
   https://localhost:8443 (a self-signed certificate: open it once and accept it).

Login is off by default (guests only). With the bundled Keycloak, set \`KEYCLOAK_ADMIN_PASSWORD\`
and \`OIDC_CLIENT_SECRET\` in \`.env\`, then:

    docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up -d

and create users at http://localhost:8180 (realm \`llm-chat\`). For your own OpenID Connect
provider, set \`AUTH_MODE=oidc\` and the \`OIDC_*\` settings instead.

Documentation: https://github.com/Knaeckebrothero/Advanced-LLM-Chat/blob/main/docs/authentication.md
and https://github.com/Knaeckebrothero/Advanced-LLM-Chat/tree/main/docker
EOF

tar -czf "$out/$name.tar.gz" -C "$work" "$name"
echo "$out/$name.tar.gz"
