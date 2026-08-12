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
 && apt-get install -y --no-install-recommends git ca-certificates curl openssl \
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

# --- ttyd: the browser terminal ------------------------------------------------------------------
# Serves `zellij attach` over TLS so the agent is reachable by opening a URL. Static single-file
# release binaries for both arches, same reasoning as zellij.
#
# It is NOT started unless a credential is supplied (see bin/entrypoint.sh). This is a WRITABLE
# terminal onto a live session holding credentials and tools - it is a remote shell, and the safe
# default for a remote shell is "off".
ARG TTYD_VERSION=1.7.7
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) arch="x86_64" ;; \
      arm64) arch="aarch64" ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/ttyd \
      "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${arch}"; \
    chmod 0755 /usr/local/bin/ttyd; \
    ttyd --version

# --- a non-root identity ------------------------------------------------------------------------
# The agent runs as an unprivileged user. Its home is where the being gets mounted, so the uid must
# own those paths; keep this uid stable or bind-mounted state comes back unreadable after a rebuild.
ARG AGENT_UID=1000
RUN useradd --create-home --uid ${AGENT_UID} --shell /bin/bash agent

# --- uv: the installer ---------------------------------------------------------------------------
# uv rather than pip or poetry. Same Rust toolchain as ruff, a single static multi-arch binary, and
# no interpreter of its own to bootstrap - which suits an image that has to build unchanged on an
# Apple Silicon laptop and an x86 server.
#
# NOTE(pin): `latest` is convenient and is exactly how a build starts silently drifting. The version
# is echoed below so every build log records what it actually used; pin this tag before anything
# depends on the image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv --version

WORKDIR /opt/agent-boot
COPY --chown=agent:agent . /opt/agent-boot

# A local .venv, not a --system install. The image's system Python stays exactly as the base image
# shipped it, so anything the agent installs later cannot break the interpreter it is running on -
# and the whole environment is one directory that can be inspected, diffed or thrown away.
#
# The PACKAGE has no dependencies. A FACULTY may: the keyring opens ansible-vault ciphertext, so
# without ansible-vault in the image the agent carries keys it cannot open - a faculty that is
# present, wired, and dead. That distinction is deliberate: installing agent-boot stays
# dependency-free, and the IMAGE installs what the faculties it enables actually require.
ENV VIRTUAL_ENV=/opt/agent-boot/.venv
ENV PATH="/opt/agent-boot/.venv/bin:${PATH}"
RUN uv venv "${VIRTUAL_ENV}" \
 && uv pip install --no-cache ansible-core pymongo \
 && uv pip install --no-cache --no-deps . \
 && chown -R agent:agent "${VIRTUAL_ENV}" \
 && python3 -c "import agentboot; print('agentboot', agentboot.__version__)" \
 && command -v ansible-vault

# BELT AND SUSPENDERS FOR PATH - and this is not paranoia, it is a measured failure.
#
# `ENV PATH` above covers non-login shells. A LOGIN shell (`bash -l`, and what you get when you
# ATTACH to the session) re-sources /etc/profile and rebuilds PATH from scratch, discarding it:
#
#     ENV PATH   ->  /opt/agent-boot/.venv/bin:/usr/local/bin:...     venv present
#     bash -lc   ->  /usr/local/bin:/usr/bin:/bin:/usr/games          venv GONE
#
# The first container run died on "No module named agentboot" for exactly this, and it would have
# bitten again the first time a human attached and typed a command by hand. profile.d is the half
# that covers the interactive case.
RUN printf '%s\n' 'export VIRTUAL_ENV=/opt/agent-boot/.venv' \
                  'export PATH="/opt/agent-boot/.venv/bin:$PATH"' \
      > /etc/profile.d/agent-boot.sh \
 && chmod 0644 /etc/profile.d/agent-boot.sh \
 && bash -lc 'command -v python3 | grep -q "^/opt/agent-boot/.venv/" && python3 -c "import agentboot"'

# --- prove the build, in the build ---------------------------------------------------------------
# A build that only proves it can copy files has proved nothing. Run the suite that asserts the
# framework refuses to fake a pass; if that regresses, the image must not exist.
RUN python3 -m unittest discover -s tests -q

# --- zellij config: applies the theme AND suppresses the first-run wizard -----------------------
# zellij 0.44 shows an interactive "First Run Setup Wizard" when it finds no config, asking which
# keybinding style you prefer. In a detached container nobody answers it, so the session comes up
# blocked on a prompt and the layout never runs - which presents as "the agent will not start"
# rather than "something is waiting for a keystroke you cannot see".
#
# Shipping a config is the fix, and it is the same file that carries the theme and
# on_force_close "detach". Placed at build time so a container with no mounted state still starts
# unattended; a mounted ZELLIJ_CONFIG_DIR overrides it.
RUN mkdir -p /home/agent/.config/zellij/themes \
 && cp /opt/agent-boot/examples/zellij/config.kdl /home/agent/.config/zellij/config.kdl \
 && cp /opt/agent-boot/examples/zellij/theme.kdl  /home/agent/.config/zellij/themes/ember.kdl \
 && mkdir -p /home/agent/.config/zellij/layouts \
 && cp /opt/agent-boot/examples/zellij/main.kdl  /home/agent/.config/zellij/layouts/main.kdl \
 && chown -R agent:agent /home/agent/.config

USER agent
WORKDIR /home/agent

ENV CLAUDE_DIR=/home/agent/.claude \
    AGENTBOOT_DIR=/home/agent/.agentboot \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the exec bit HERE rather than relying on the file mode in the checkout. A build must not
# depend on whether a contributor's filesystem happened to preserve +x - the failure is
# `exec ... Permission denied` from tini, which reads as a container problem rather than a
# forgotten chmod.
RUN chmod 0755 /opt/agent-boot/bin/entrypoint.sh

EXPOSE 7681

# Prove the enforcement, open the door if one was configured, then hold the session.
#
# Everything the faculties need is BAKED, not installed at start: zellij, ttyd, ansible-vault, uv,
# openssl, the venv. That is the whole performance argument for living in the can - a session that
# has to install its environment first is a session that starts slow every single time, and the
# install is a network dependency at exactly the moment you want the agent thinking.
ENTRYPOINT ["/opt/agent-boot/bin/entrypoint.sh"]
