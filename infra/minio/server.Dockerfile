FROM alpine:3.22.1

ARG TARGETARCH
ARG MINIO_VERSION=RELEASE.2025-09-07T16-13-09Z

# MinIO Community non pubblica piu le immagini legacy. Il binario della sua
# ultima release AGPL resta negli asset GitHub ufficiali: il checksum fissato
# impedisce di incorporare nel build un download alterato o inatteso.
RUN apk add --no-cache ca-certificates curl \
    && case "${TARGETARCH}" in \
         amd64) MINIO_SHA256="7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f" ;; \
         arm64) MINIO_SHA256="5c83cd2cf151717ba0243f73e1c7802ff36e272b67144bdd7f1f7d684fd6f03d" ;; \
         *) echo "Architettura non supportata: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && wget -q -O /usr/local/bin/minio \
       "https://github.com/minio/minio/releases/download/${MINIO_VERSION}/minio.linux-${TARGETARCH}.${MINIO_VERSION}" \
    && echo "${MINIO_SHA256}  /usr/local/bin/minio" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/minio

EXPOSE 9000 9001
VOLUME ["/data"]

ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
