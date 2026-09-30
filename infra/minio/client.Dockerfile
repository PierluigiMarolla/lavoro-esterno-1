FROM alpine:3.22.1

ARG TARGETARCH
ARG MC_VERSION=RELEASE.2025-08-13T08-35-41Z

# Il client viene recuperato dagli asset GitHub ufficiali e verificato prima
# dell'installazione. /bin/sh rimane disponibile per gli script di backup.
RUN apk add --no-cache ca-certificates \
    && case "${TARGETARCH}" in \
         amd64) MC_SHA256="01f866e9c5f9b87c2b09116fa5d7c06695b106242d829a8bb32990c00312e891" ;; \
         arm64) MC_SHA256="14c8c9616cfce4636add161304353244e8de383b2e2752c0e9dad01d4c27c12c" ;; \
         *) echo "Architettura non supportata: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && wget -q -O /usr/local/bin/mc \
       "https://github.com/minio/mc/releases/download/${MC_VERSION}/mc.linux-${TARGETARCH}.${MC_VERSION}" \
    && echo "${MC_SHA256}  /usr/local/bin/mc" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/mc

ENTRYPOINT ["/usr/local/bin/mc"]
