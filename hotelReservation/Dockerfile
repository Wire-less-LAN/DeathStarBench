FROM golang:1.22 as builder

WORKDIR /workspace

COPY go.sum go.sum
COPY go.mod go.mod
COPY vendor/ vendor/

COPY cmd/ cmd/
COPY dialer/ dialer/
COPY registry/ registry/
COPY services/ services/
COPY tls/ tls/
COPY tracing/ tracing/
COPY tune/ tune/

COPY unicomm/ unicomm/
COPY python/retriever python/retriever

COPY config.json config.json

RUN CGO_ENABLED=0 GOOS=linux GO111MODULE=on go install -ldflags="-s -w" -mod=vendor ./cmd/...

# busybox 阶段
FROM busybox as bb

RUN /bin/busybox --help 

# 最终镜像

# FROM gcr.io/distroless/static:nonroot
FROM ubuntu:latest

WORKDIR /

# 从构建阶段复制可执行文件
COPY --from=builder /go/bin/frontend .
COPY --from=builder /go/bin/geo .
COPY --from=builder /go/bin/profile .
COPY --from=builder /go/bin/rate .
COPY --from=builder /go/bin/recommendation .
COPY --from=builder /go/bin/reservation .
COPY --from=builder /go/bin/search .
COPY --from=builder /go/bin/user .

# 从构建阶段复制配置和工具
COPY --from=builder /workspace/config.json .
COPY --from=bb /bin/busybox /bin/busybox

RUN apt-get update && apt-get install -y redis-tools
RUN /bin/busybox --help

