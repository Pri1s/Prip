# RTL Debug Agent toolchain: OSS CAD Suite (Icarus, Yosys, SBY, EQY) + cocotb.
FROM debian:bookworm-slim

ARG OSS_CAD_SUITE_DATE=2026-10-01
ARG TARGETARCH

# build-essential + python3-dev: cocotb ships no linux-aarch64 wheel, so pip compiles it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl make git \
        build-essential python3 python3-dev python3-venv libpython3.11 \
    && rm -rf /var/lib/apt/lists/*

# Pinned OSS CAD Suite nightly. Only bin/ goes on PATH; its `environment` script is
# not sourced because it would put the suite's bundled Python ahead of our venv.
RUN set -eux; \
    case "${TARGETARCH}" in \
        arm64) suite_arch=linux-arm64 ;; \
        amd64) suite_arch=linux-x64 ;; \
        *) echo "unsupported arch: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    tag_date=$(echo "${OSS_CAD_SUITE_DATE}" | tr -d -); \
    curl -fsSL "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_SUITE_DATE}/oss-cad-suite-${suite_arch}-${tag_date}.tgz" \
        | tar -xz -C /opt

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "${VIRTUAL_ENV}"
ENV PATH="${VIRTUAL_ENV}/bin:/opt/oss-cad-suite/bin:${PATH}"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Our vvp wrapper shadows the suite's (see docker/vvp for why).
COPY --chmod=755 docker/vvp /usr/local/sbin/vvp
ENV PATH="/usr/local/sbin:${PATH}"

WORKDIR /work
