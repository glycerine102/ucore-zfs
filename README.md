# Ucore ZFS

Provides a clean image of Fedora Kinoite and ZFS modules.
Meant to be used as a base for other desktop images.

[Issues](https://github.com/ublue-os/akmods)

## ZFS Versioning

Currently on ZFS 2.4 which is only available on `testing`.
Once 2.4 arrives on the stable channel,
the bases for akmods images can be switched back to `stable`.

A `mise` script can be ran to determine the best version combos
based on the available akmods, kernel, and zfs versions.
Example:

```bash
mise run version_check -c testing -f 44
...
[4/4] Results
════════════════════════════════════════════════════════════

akmods-zfs latest tag  : coreos-testing-44-7.0.12-201.fc44
  repo                 : ghcr.io/ublue-os/akmods-zfs
  channel              : coreos-testing
  kernel version       : 7.0.12
  full kernel string   : 7.0.12-201.fc44

kinoite-main match tag : 44-20260628.1
  repo                 : ghcr.io/ublue-os/kinoite-main
  ostree.linux label   : 7.0.12-201.fc44.x86_64

✅  Match found!

    akmods-zfs   → ghcr.io/ublue-os/akmods-zfs:coreos-testing-44-7.0.12-201.fc44
    kinoite-main → ghcr.io/ublue-os/kinoite-main:44-20260628.1
```
