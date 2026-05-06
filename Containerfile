# Equates to something like coreos-stable-43-6.18.13-200.fc43.x86_64
ARG FEDORA_VERSION=43
ARG KERNEL_VERSION=6.19.12-200.fc43

FROM scratch AS ctx
COPY build_files /

# https://github.com/ublue-os/akmods/pkgs/container/akmods
FROM ghcr.io/ublue-os/akmods:coreos-stable-"${FEDORA_VERSION}"-"${KERNEL_VERSION}" AS akmods

# https://github.com/ublue-os/akmods/pkgs/container/akmods-zfs
FROM ghcr.io/ublue-os/akmods-zfs:coreos-stable-"${FEDORA_VERSION}"-"${KERNEL_VERSION}" AS akmods-zfs

# https://github.com/ublue-os/main/pkgs/container/kinoite-main/versions
FROM ghcr.io/ublue-os/ublue-os/kinoite-main:"${FEDORA_VERSION}" AS base

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=bind,from=akmods,src=/kernel-rpms,dst=/tmp/kernel-rpms \
    --mount=type=bind,from=akmods,src=/rpms/common,dst=/tmp/rpms/common \
    --mount=type=bind,from=akmods,src=/rpms/kmods,dst=/tmp/rpms/kmods \
    --mount=type=bind,from=akmods-zfs,src=/rpms/kmods/zfs,dst=/tmp/rpms/kmods/zfs \
    /ctx/zfs.sh

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

### LINTING
## Verify final image and contents are correct.
RUN bootc container lint
