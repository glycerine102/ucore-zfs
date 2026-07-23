# Equates to something like coreos-stable-43-6.18.13-200.fc43.x86_64
ARG FEDORA_VERSION=44
ARG KERNEL_VERSION=7.1.4-200.fc44
ARG CALVER_VERSION=20260723.1

FROM scratch AS ctx
COPY build_files /

# https://github.com/ublue-os/akmods/pkgs/container/akmods/versions
FROM ghcr.io/ublue-os/akmods:coreos-testing-"${FEDORA_VERSION}"-"${KERNEL_VERSION}" AS akmods

# https://github.com/ublue-os/akmods/pkgs/container/akmods-zfs/versions
FROM ghcr.io/ublue-os/akmods-zfs:coreos-testing-"${FEDORA_VERSION}"-"${KERNEL_VERSION}" AS akmods-zfs

# https://github.com/ublue-os/main/pkgs/container/kinoite-main/versions
FROM ghcr.io/ublue-os/kinoite-main:"${FEDORA_VERSION}-${CALVER_VERSION}" AS base

# Copy kernel RPMs and common RPMs from akmods into the build context.
RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=bind,from=akmods,src=/kernel-rpms,dst=/tmp/kernel-rpms \
    --mount=type=bind,from=akmods,src=/rpms/common,dst=/tmp/rpms/common \
    --mount=type=bind,from=akmods,src=/rpms/kmods,dst=/tmp/rpms/kmods \
    --mount=type=bind,from=akmods-zfs,src=/rpms/kmods/zfs,dst=/tmp/rpms/kmods/zfs \
    /ctx/zfs.sh

# Use this as a buffer step to install other items as well
RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

## Verify final image and contents are correct.
RUN bootc container lint
