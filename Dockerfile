# =============================================================================
# Dockerfile for swf-testbed  —  CLI + workflow agents
# =============================================================================
# Build context: the repository root (parent of swf-testbed, swf-monitor, etc.)
#
# The image installs swf-common-lib, swf-monitor, and swf-testbed so that the
# `testbed run` CLI works out of the box inside a container.
# =============================================================================

# --------------- build stage: install all deps -------------------------------
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libffi-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy the three repos into the build context.
# Build context is the monorepo root so paths are relative to it.
COPY swf-common-lib /build/swf-common-lib
COPY swf-monitor    /build/swf-monitor
COPY swf-testbed    /build/swf-testbed

# 1. swf-common-lib (shared utilities)
RUN pip install --no-cache-dir /build/swf-common-lib

# 2. swf-monitor dependencies + package
RUN pip install --no-cache-dir -r /build/swf-monitor/requirements.txt \
    && pip install --no-cache-dir django-mcp-server django-oauth-toolkit uvicorn \
    && pip install --no-cache-dir /build/swf-monitor

# 3. swf-testbed itself (typer CLI, supervisor, psutil, simpy, etc.)
RUN pip install --no-cache-dir /build/swf-testbed

# --------------- runtime stage: slim image -----------------------------------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 wget \
    && rm -rf /var/lib/apt/lists/*

# Bring over installed packages from the builder.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the testbed source tree (needed at runtime for workflows/, example_agents/, configs).
COPY --from=builder /build/swf-testbed /app
# Keep swf-monitor source available (manage.py for migrations, etc.)
COPY --from=builder /build/swf-monitor /opt/swf-monitor
COPY --from=builder /build/swf-common-lib /opt/swf-common-lib

WORKDIR /app

# Create logs directory that supervisord expects.
RUN mkdir -p /app/logs

# Symlinks so that $SWF_HOME/swf-testbed resolves to /app regardless of
# which path _setup_environment() computes for SWF_HOME.
# agents.supervisord.conf uses: directory=%(ENV_SWF_HOME)s/swf-testbed
RUN ln -s /app /opt/swf-testbed  && ln -s /app /usr/local/lib/swf-testbed

# Entrypoint handles environment setup, then runs the requested command.
COPY swf-testbed/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["testbed", "run"]
