# Ucore ZFS

Provides a clean image of Fedora Kinoite and ZFS modules.
Meant to be used as a base for other desktop images.

[Issues](https://github.com/ublue-os/akmods)

## ZFS Versioning

Currently on ZFS 2.4 which is only available on `testing`.
Once 2.4 arrives on the stable channel,
the bases for akmods images can be switched back to `stable`.

The following images will pair up best, based on the kernel and zfs versions:

```
akmods-zfs   → ghcr.io/ublue-os/akmods-zfs:coreos-testing-43-6.19.12-200.fc43
kinoite-main → ghcr.io/ublue-os/kinoite-main:43-20260424.1

akmods-zfs  → ghcr.io/ublue-os/akmods-zfs:coreos-testing-43-7.0.4-100.fc43
kinoite-main → ghcr.io/ublue-os/kinoite-main:43-20260514.1
```
