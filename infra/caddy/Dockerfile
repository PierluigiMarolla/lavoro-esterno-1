FROM golang:1.26.6-alpine3.23 AS builder

ARG CADDY_VERSION=v2.11.4

RUN apk add --no-cache git
WORKDIR /src
RUN git clone --depth 1 --branch "${CADDY_VERSION}" \
    https://github.com/caddyserver/caddy.git
WORKDIR /src/caddy/cmd/caddy

# La release upstream precede alcune correzioni Go pubblicate successivamente.
# Manteniamo il codice Caddy versionato e aggiorniamo soltanto i moduli con
# fix di sicurezza segnalati dalla pipeline Trivy.
RUN go get \
      golang.org/x/crypto@v0.55.0 \
      golang.org/x/net@v0.58.0 \
      golang.org/x/text@v0.41.0 \
      google.golang.org/grpc@v1.83.2 \
    && go mod tidy \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /usr/bin/caddy .

FROM alpine:3.23

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates mailcap tzdata wget \
    && addgroup -S caddy \
    && adduser -S -D -H -s /sbin/nologin -G caddy caddy

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

ENV XDG_CONFIG_HOME=/config \
    XDG_DATA_HOME=/data

VOLUME /config /data
EXPOSE 80 443 443/udp 2019
WORKDIR /srv
ENTRYPOINT ["caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
