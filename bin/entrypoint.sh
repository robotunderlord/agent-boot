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
    # ── his OWN internal CA ─────────────────────────────────────────────────────────────────────
    # Generated once into the state volume, then reused forever. Not the estate's CA, not a public
    # one - his. He must work identically on a laptop, a rented GPU, or a machine that has never
    # heard of this lab, and borrowing somebody else's trust root breaks that.
    #
    # What it buys over self-signed: import his root ONCE into a browser and every cert he ever
    # issues for himself is trusted. Self-signed encrypts but authenticates nothing - a client
    # cannot tell him from an impostor on the same address.
    #
    # The CA key never enters the image. An image carrying a CA key would let every copy of it
    # impersonate every instance.
    AGENT_CA_DIR="${AGENT_CA_DIR:-/home/agent/.agentboot/ca}"
    CA_KEY="${AGENT_CA_DIR}/ca.key"
    CA_CRT="${AGENT_CA_DIR}/ca.crt"

    if [ ! -s "${CA_CRT}" ] || [ ! -s "${CA_KEY}" ]; then
        say "no internal CA yet - minting his own (once; it persists in state)."
        mkdir -p "${AGENT_CA_DIR}"
        openssl req -x509 -newkey rsa:4096 -nodes -days 3650 -sha256 \
            -subj "/CN=agent-boot internal CA/O=agent-boot" \
            -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
            -addext "keyUsage=critical,keyCertSign,cRLSign" \
            -keyout "${CA_KEY}" -out "${CA_CRT}" 2>/dev/null
        chmod 0600 "${CA_KEY}"
        chmod 0644 "${CA_CRT}"
    fi
    say "internal CA: ${CA_CRT}  (import THIS into your browser, once)"

    # ── the server cert, ISSUED BY HIS CA ───────────────────────────────────────────────────────
    if [ ! -s "${AGENT_WEB_CERT}" ] || [ ! -s "${AGENT_WEB_KEY}" ]; then
        say "issuing a server cert from his own CA for '${AGENT_WEB_CN:-agent.local}'"
        mkdir -p "$(dirname "${AGENT_WEB_CERT}")"
        _csr="$(mktemp)"; _ext="$(mktemp)"
        # SANs, not just CN: browsers have ignored commonName for host matching since 2017, so a
        # cert without subjectAltName fails verification no matter how correct the CN looks.
        printf 'subjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n' \
            "${AGENT_WEB_CN:-agent.local}" > "${_ext}"
        openssl req -newkey rsa:2048 -nodes -subj "/CN=${AGENT_WEB_CN:-agent.local}" \
            -keyout "${AGENT_WEB_KEY}" -out "${_csr}" 2>/dev/null
        openssl x509 -req -in "${_csr}" -CA "${CA_CRT}" -CAkey "${CA_KEY}" -CAcreateserial \
            -days 825 -sha256 -extfile "${_ext}" -out "${AGENT_WEB_CERT}" 2>/dev/null
        rm -f "${_csr}" "${_ext}"
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
