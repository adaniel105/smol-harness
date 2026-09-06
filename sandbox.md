# Firecracker Project Setup Requirements

## Overview
This document outlines the requirements for setting up a Firecracker microVM project. Firecracker is a lightweight virtualization technology that runs workloads in lightweight microVMs, originally built by AWS for Lambda and Fargate.

## System Requirements

### Host Operating System
- **Linux kernel**: 4.14+ (5.10+ recommended for full feature support)
- **Architecture**: x86_64 or aarch64
- **Distribution**: Any modern Linux distribution (Ubuntu 20.04+, Fedora 34+, Arch, etc.)

### Kernel Features Required
- `CONFIG_KVM=y` - Kernel-based Virtual Machine support
- `CONFIG_KVM_INTEL=y` or `CONFIG_KVM_AMD=y` - Hardware virtualization
- `CONFIG_VHOST_NET=y` - Virtio network backend
- `CONFIG_VHOST_VSOCK=y` - Virtio VSOCK backend
- `CONFIG_TUN=y` - TUN/TAP network device support
- `CONFIG_BRIDGE=y` - Bridge networking support
- `CONFIG_CGROUPS=y` - Control groups for resource limiting
- `CONFIG_CGROUP_CPUACCT=y` - CPU accounting
- `CONFIG_CGROUP_MEMORY=y` - Memory limiting
- `CONFIG_CGROUP_PIDS=y` - Process limiting
- `CONFIG_CGROUP_FREEZER=y` - Process freezing
- `CONFIG_CGROUP_DEVICE=y` - Device access control
- `CONFIG_CPUSETS=y` - CPU pinning
- `CONFIG_SECCOMP=y` - Secure computing mode
- `CONFIG_SECCOMP_FILTER=y` - Seccomp BPF filtering

### Hardware Requirements
- CPU with virtualization extensions (Intel VT-x / AMD-V)
- Minimum 2GB RAM (4GB+ recommended)
- Minimum 10GB free disk space
- Nested virtualization support if running inside a VM

## Software Dependencies

### Required Packages
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y \
    build-essential \
    curl \
    git \
    libseccomp-dev \
    pkg-config \
    libelf-dev \
    libcap-dev \
    libcap-ng-dev \
    iproute2 \
    iptables \
    bridge-utils \
    qemu-system-x86 \
    qemu-utils \
    jq

# Fedora/RHEL
sudo dnf install -y \
    gcc \
    make \
    curl \
    git \
    libseccomp-devel \
    pkg-config \
    elfutils-libelf-devel \
    libcap-devel \
    libcap-ng-devel \
    iproute \
    iptables \
    bridge-utils \
    qemu-system-x86 \
    qemu-img \
    jq

# Arch Linux
sudo pacman -S --needed \
    base-devel \
    curl \
    git \
    libseccomp \
    pkgconf \
    libelf \
    libcap \
    libcap-ng \
    iproute2 \
    iptables \
    bridge-utils \
    qemu-system-x86 \
    qemu-img \
    jq
```

### Rust Toolchain
- **Rust**: 1.70+ (stable)
- **Cargo**: Included with Rust
- Install via `rustup`: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

### Firecracker Binary
- Download pre-built release from [GitHub Releases](https://github.com/firecracker-microvm/firecracker/releases)
- Or build from source (requires Rust toolchain)

```bash
# Download latest release
ARCH=$(uname -m)
RELEASE_URL="https://github.com/firecracker-microvm/firecracker/releases/latest/download/firecracker-${ARCH}"
curl -L -o firecracker "${RELEASE_URL}"
chmod +x firecracker
sudo mv firecracker /usr/local/bin/
```

## Kernel and Rootfs Images

### Kernel Image (vmlinux)
- **Version**: 5.10+ (LTS recommended)
- **Configuration**: Minimal config with virtio drivers built-in
- **Build options**:
  - `CONFIG_VIRTIO_BLK=y`
  - `CONFIG_VIRTIO_NET=y`
  - `CONFIG_VIRTIO_CONSOLE=y`
  - `CONFIG_VIRTIO_PCI=y`
  - `CONFIG_VIRTIO_MMIO=y`
  - `CONFIG_SCSI_VIRTIO=y`
  - `CONFIG_VIRTIO_VSOCK=y`
  - `CONFIG_VHOST_VSOCK=y`

### Root Filesystem
Options:
1. **Ubuntu/Alpine cloud images** - Pre-built minimal rootfs
2. **Custom buildroot/yocto** - For minimal footprint
3. **Debian debootstrap** - Custom Debian-based rootfs

Minimum requirements:
- `systemd` or `openrc` / `busybox init`
- `ssh` server for remote access
- `curl`/`wget` for downloading
- Kernel modules for virtio (`virtio_blk`, `virtio_net`, `virtio_console`, `virtio_vsock`)

## Networking Setup

### Bridge Network (Recommended)
```bash
# Create bridge
sudo ip link add name fcbr0 type bridge
sudo ip addr add 172.16.0.1/24 dev fcbr0
sudo ip link set fcbr0 up

# Enable IP forwarding
echo 1 | sudo tee /proc/sys/net/ipv4/ip_forward

# NAT for internet access
sudo iptables -t nat -A POSTROUTING -s 172.16.0.0/24 ! -o fcbr0 -j MASQUERADE
sudo iptables -A FORWARD -i fcbr0 -j ACCEPT
sudo iptables -A FORWARD -o fcbr0 -j ACCEPT
```

### TAP Device Creation (Per-VM)
```bash
# Create TAP device
sudo ip tuntap add dev tap0 mode tap user $(whoami)
sudo ip link set tap0 master fcbr0
sudo ip link set tap0 up
```

### Alternative: CNI Plugins
- Use `firecracker-containerd` with CNI for Kubernetes integration
- Plugins: `bridge`, `macvlan`, `ipvlan`, `ptp`

## Storage Setup

### Block Device Options
1. **Raw image file** - Simple, loopback mounted
2. **LVM logical volume** - Better performance, snapshots
3. **ZFS/btrfs dataset** - Copy-on-write, snapshots
4. **NVMe namespace** - Direct device passthrough

### Creating Rootfs Image
```bash
# Create 1GB raw image
truncate -s 1G rootfs.ext4
mkfs.ext4 rootfs.ext4

# Mount and populate
sudo mount rootfs.ext4 /mnt
# ... populate with rootfs contents ...
sudo umount /mnt
```

## Firecracker Configuration

### Basic VM Configuration (JSON)
```json
{
  "boot-source": {
    "kernel_image_path": "./vmlinux",
    "boot_args": "console=ttyS0 reboot=k panic=1 pci=off nomodules ro root=/dev/vda"
  },
  "drives": [
    {
      "drive_id": "rootfs",
      "path_on_host": "./rootfs.ext4",
      "is_root_device": true,
      "is_read_only": false
    }
  ],
  "network-interfaces": [
    {
      "iface_id": "eth0",
      "guest_mac": "02:FC:00:00:00:01",
      "host_dev_name": "tap0"
    }
  ],
  "machine-config": {
    "vcpu_count": 2,
    "mem_size_mib": 1024,
    "ht_enabled": false,
    "track_dirty_pages": false
  }
}
```

### Advanced Configuration Options
- **Rate limiting**: Bandwidth/IOPS throttling per device
- **Virtio-fs**: Host directory sharing (Linux 5.4+)
- **vsock**: Host-guest communication
- **Balloon device**: Dynamic memory management
- **Entropy device**: `/dev/virtio-rng` for guest entropy
- **Snapshot/restore**: Save/resume VM state

## Security Hardening

### Seccomp Profile
- Use Firecracker's default seccomp filter
- Customize for minimal syscall surface
- Block dangerous syscalls: `ptrace`, `process_vm_readv`, `process_vm_writev`, `kcmp`, `userfaultfd`

### Capabilities
- Run Firecracker with minimal capabilities:
  ```bash
  sudo setcap cap_net_admin,cap_sys_admin,cap_dac_override,cap_chown,cap_fowner,cap_sys_resource+eip /usr/local/bin/firecracker
  ```
- Or run as root with user namespace mapping

### Jailer (Optional)
- Use `jailer` for additional isolation
- Creates chroot, drops privileges, sets up namespaces
- Recommended for production deployments

## Monitoring and Observability

### Metrics
- Firecracker exposes metrics via HTTP endpoint
- Enable with `--metrics-port 8080`
- Metrics: CPU, memory, network, block I/O, vmm info

### Logging
- Structured JSON logging
- Levels: error, warn, info, debug
- Configure via `--log-level` and `--log-path`

### Health Checks
- Instance metadata service
- Guest agent for health reporting
- Integration with Prometheus/Grafana

## Project Structure

```
firecracker-project/
├── bin/
│   ├── firecracker          # Firecracker binary
│   └── jailer               # Optional jailer binary
├── kernel/
│   └── vmlinux              # Kernel image
├── rootfs/
│   ├── rootfs.ext4          # Root filesystem image
│   └── rootfs.squashfs      # Optional readonly layer
├── config/
│   ├── vm-base.json         # Base VM configuration
│   ├── vm-1.json            # Instance-specific config
│   └── seccomp.json         # Custom seccomp profile
├── network/
│   ├── setup-bridge.sh      # Bridge network setup
│   ├── setup-tap.sh         # TAP device creation
│   └── teardown.sh          # Cleanup script
├── scripts/
│   ├── create-vm.sh         # VM creation helper
│   ├── start-vm.sh          # VM start script
│   ├── stop-vm.sh           # VM stop script
│   └── snapshot-vm.sh       # Snapshot utility
├── logs/
│   └── firecracker.log      # Firecracker logs
├── metrics/
│   └── prometheus.yml       # Prometheus scrape config
└── README.md                # Project documentation
```

## Testing and Validation

### Smoke Tests
1. Boot VM and verify console output
2. Network connectivity (ping, DNS, HTTP)
3. Disk I/O (read/write tests)
4. Memory pressure test
5. CPU stress test
6. Snapshot/restore cycle

### CI/CD Integration
- GitHub Actions / GitLab CI for automated testing
- Test matrix: multiple kernel versions, rootfs types
- Performance benchmarks tracking

## Troubleshooting

### Common Issues
| Issue | Solution |
|-------|----------|
| KVM not available | Check `kvm-ok`, enable in BIOS, load `kvm_intel`/`kvm_amd` |
| Permission denied on /dev/kvm | Add user to `kvm` group: `sudo usermod -aG kvm $USER` |
| Network not working | Verify bridge, TAP, iptables, guest network config |
| Slow disk I/O | Use virtio-blk, enable `track_dirty_pages`, consider virtio-fs |
| High memory usage | Enable balloon, reduce `mem_size_mib`, use hugepages |

### Debug Commands
```bash
# Check KVM
kvm-ok
ls -la /dev/kvm

# Check Firecracker version
firecracker --version

# Validate config
firecracker --validate-config --config-file vm.json

# Debug logging
firecracker --log-level debug --log-path ./debug.log --config-file vm.json

# API socket interaction
curl -X PUT --unix-socket /tmp/firecracker.sock \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{"action_type": "InstanceStart"}' \
  http://localhost/actions
```

## Production Considerations

### High Availability
- Use orchestration: `firecracker-containerd`, `Kata Containers`, `Weave Ignite`
- Implement health checks and auto-restart
- Distribute VMs across multiple hosts

### Resource Management
- CPU pinning via `cpuset` cgroup
- Memory limits via cgroup v2
- IO throttling via `blkio` cgroup
- Network QoS via `tc` on host

### Backup and Recovery
- Regular snapshots of rootfs
- Export/import VM state
- Disaster recovery runbooks

## References

- [Firecracker Documentation](https://firecracker-microvm.github.io/)
- [Firecracker GitHub](https://github.com/firecracker-microvm/firecracker)
- [Firecracker Containerd](https://github.com/firecracker-microvm/firecracker-containerd)
- [Kata Containers](https://katacontainers.io/)
- [Linux Kernel Documentation](https://www.kernel.org/doc/html/latest/)
- [QEMU Documentation](https://www.qemu.org/docs/master/)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-01 | Initial requirements document |