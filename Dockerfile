# agent-boot — the vessel.
#
# Multi-arch by construction: python:3.12-slim publishes amd64 and arm64, and agent-boot has no
# compiled dependencies at all, so `docker build` works unchanged on an Apple Silicon laptop and on
# an x86 server. Nothing here needs a wheel, a toolchain, or a lockfile.
#
# THE ONE RULE THIS FILE OBEYS: the image carries CODE, never the BEING.
# No secrets, no credentials, no memory, no local rules, no tattoo content. Those arrive as mounts
# (see docker-compose.yml). An image that bakes a secret cannot be published, shared or rebuilt in
# public — and an image that bakes memory makes every instance the same agent, which defeats it.

FROM python:3.12-slim

# --- runtime deps: deliberately almost nothing --------------------------------------------------
# `cat` is what the three hook layers actually invoke, and coreutils ships in the base image.
# git is here because the documented install path is "the agent clones this repo itself".
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# --- the multiplexer that HOLDS the agent -------------------------------------------------------
# The agent runs inside a zellij session rather than as the container's foreground process, so its
# life is not the connection's life: detach, drop the VPN, close the laptop — none of those are
# events in its life. See agentboot/session.py for the full argument and the EXITED landmine.
#
# Installed from the GitHub release rather than a distro package: the binary is current, static, and
# published for both architectures, so the same Dockerfile builds on an Apple Silicon laptop and an
# x86 server without a toolchain.
ARG ZELLIJ_VERSION=v0.44.3
ARG TARGETARCH
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) target="x86_64-unknown-linux-musl" ;; \
      arm64) target="aarch64-unknown-linux-musl" ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/zellij.tgz \
      "https://github.com/zellij-org/zellij/releases/download/${ZELLIJ_VERSION}/zellij-${target}.tar.gz"; \
    tar -xzf /tmp/zellij.tgz -C /usr/local/bin zellij; \
    rm -f /tmp/zellij.tgz; \
    chmod 0755 /usr/local/bin/zellij; \
    zellij --version

# --- a non-root identity ------------------------------------------------------------------------
# The agent runs as an unprivileged user. Its home is where the being gets mounted, so the uid must
# own those paths; keep this uid stable or bind-mounted state comes back unreadable after a rebuild.
ARG AGENT_UID=1000
RUN useradd --create-home --uid ${AGENT_UID} --shell /bin/bash agent

WORKDIR /opt/agent-boot
COPY --chown=agent:agent . /opt/agent-boot

# Install as a package so `python3 -m agentboot` resolves from any working directory, and the
# console script is on PATH. --no-deps is honest here: there are none.
RUN pip install --no-cache-dir --no-deps . \
 && python3 -c "import agentboot; print('agentboot', agentboot.__version__)"

# --- prove the build, in the build ---------------------------------------------------------------
# A build that only proves it can copy files has proved nothing. Run the suite that asserts the
# framework refuses to fake a pass; if that regresses, the image must not exist.
RUN python3 -m unittest discover -s tests -q

USER agent
WORKDIR /home/agent

ENV CLAUDE_DIR=/home/agent/.claude \
    AGENTBOOT_DIR=/home/agent/.agentboot \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Default: wire the layers and prove they fire. Override in compose for a long-running agent.
CMD ["python3", "-m", "agentboot", "install", "--prove"]
