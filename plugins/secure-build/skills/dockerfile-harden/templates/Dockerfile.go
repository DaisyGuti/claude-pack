# Reference Dockerfile: Go service, multi-stage build, static binary on distroless static.
#
# Before use:
#   1. Re-resolve both digests and keep them current with Renovate or Dependabot:
#        docker buildx imagetools inspect golang:1.26-trixie
#        docker buildx imagetools inspect gcr.io/distroless/static-debian13:nonroot
#   2. The static image has no shell, no libc and no curl. The health probe is the binary
#      itself, so the service needs a -healthcheck flag that calls its own /healthz.
#   3. For FIPS 140 work, Go ships a native cryptographic module selected at build time;
#      see references/base-images.md before choosing a base image for that case.

FROM golang:1.26-trixie@sha256:f06b7122f888680048afb247c4e5f49c0069eb6c4c1ccae0f3f4834527a8d22c AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download && go mod verify
COPY cmd/ ./cmd/
COPY internal/ ./internal/
ENV CGO_ENABLED=0
RUN go build -trimpath -ldflags="-s -w" -o /out/server ./cmd/server

FROM gcr.io/distroless/static-debian13:nonroot@sha256:e2e927ec666bae08560abb3c55d0659eceabb657f56b6782ab500a9fc7f555e3
COPY --from=build /out/server /server
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["/server", "-healthcheck"]
ENTRYPOINT ["/server"]
