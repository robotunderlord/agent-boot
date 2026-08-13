#!/usr/bin/env bash
# agent-boot entrypoint: prove the enforcement, open the door, then hold the session.
#
# ORDER IS THE DESIGN, and each step is a gate on the next:
#
#   1. install --prove   the hooks must fire AND be shown capable of failing. A vessel that comes
#                        up reachable with no enforcement is a body with no mind, and it looks
#                        perfectly healthy from outside.
#   2. web terminal      optional, TLS, credentialed. Refuses to serve rather than serve openly.
#   3. exec zellij       the holding session becomes PID 1's child and the container's life.
#
# `-c`, never `-lc`: a login shell rebuilds PATH from /etc/profile and discards the venv the image
# put there. Measured; it cost a build round.
set -euo pipefail

AGENT_SESSION="${AGENT_SESSION:-main}"
AGENT_WEB_PORT="${AGENT_WEB_PORT:-7681}"
AGENT_WEB_CERT="${AGENT_WEB_CERT:-/home/agent/.agentboot/tls/cert.pem}"
AGENT_WEB_KEY="${AGENT_WEB_KEY:-/home/agent/.agentboot/tls/key.pem}"

say() { printf '[entrypoint] %s\n' "$*"; }

# HONOUR ARGUMENTS. `docker run <image> <cmd>` must run <cmd>, not silently ignore it and start the
# agent anyway. An entrypoint that swallows its arguments makes the image un-inspectable: every
# attempt to run a one-off command inside it appears to hang, because what actually happened is that
# it launched a whole agent and the command was dropped on the floor. Cost a debugging round.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# ── 1. enforcement, proven ───────────────────────────────────────────────────────────────────────
python3 -m agentboot install --prove

# ── 2. the browser terminal (only if a credential was supplied) ─────────────────────────────────
if [ -n "${AGENT_WEB_CREDENTIAL:-}" ]; then
    if [ ! -s "${AGENT_WEB_CERT}" ] || [ ! -s "${AGENT_WEB_KEY}" ]; then
        say "no TLS cert mounted - generating a SELF-SIGNED pair."
        say "SELF-SIGNED ENCRYPTS BUT AUTHENTICATES NOTHING: a client cannot tell this agent from"
        say "an impostor on the same address. Mount a real cert for anything you care about."
        mkdir -p "$(dirname "${AGENT_WEB_CERT}")"
        openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
            -subj "/CN=agent-boot" \
            -keyout "${AGENT_WEB_KEY}" -out "${AGENT_WEB_CERT}" 2>/dev/null
        chmod 0600 "${AGENT_WEB_KEY}"
    fi

    # --writable is opt-in. Watching and driving are different requests; only one needs typing.
    WRITABLE=""
    [ "${AGENT_WEB_WRITABLE:-false}" = "true" ] && WRITABLE="--writable"

    say "serving https://0.0.0.0:${AGENT_WEB_PORT}/ -> zellij attach ${AGENT_SESSION}"
    say "credential: set (never printed). writable: ${AGENT_WEB_WRITABLE:-false}"
    # shellcheck disable=SC2086
    ttyd --port "${AGENT_WEB_PORT}" --interface 0.0.0.0 \
         --credential "${AGENT_WEB_CREDENTIAL}" \
         --ssl --ssl-cert "${AGENT_WEB_CERT}" --ssl-key "${AGENT_WEB_KEY}" \
         ${WRITABLE} \
         zellij attach --create "${AGENT_SESSION}" &
else
    say "AGENT_WEB_CREDENTIAL unset - browser terminal NOT started."
    say "This is the safe default: a credentialless ttyd is a public shell on a routable port."
fi

# ── 3. hold the session ─────────────────────────────────────────────────────────────────────────
say "holding session '${AGENT_SESSION}'"
exec zellij --session "${AGENT_SESSION}"
