#!/bin/bash

# ===========================
# QEMU Windows VM Launcher
# ===========================

# --- PATHS (edit these for your system) ---
WIN_VHDX="/mnt/backup/ANDY-PC-0.VHDX"
WIN_ISO="/mnt/games1/software/Microsoft/Win11_25H2_EnglishInternational_x64.iso"
OVMF="/usr/share/OVMF/OVMF_CODE.fd"

# --- PHYSICAL DYNAMIC DISK ---
# we don't need this anymore
# RAW_DISK="/dev/sdg"

# --- QEMU SETTINGS ---
RAM="8192"
CPUS="host"

# --- Run the VM ---
sudo qemu-system-x86_64 \
  -enable-kvm \
  -m $RAM \
  -cpu $CPUS \
  -bios $OVMF \
  -drive file="$WIN_ISO",media=cdrom \
  -drive file="$WIN_VHDX",format=vhdx \
  -boot menu=on \
  -name "Windows-Recovery-VM" \
  -device virtio-net,netdev=n0 \
  -netdev user,id=n0 
 # \
 # -fsdev local,id=homefs,path=/mnt/home,security_model=none \
 # -device virtio-9p-pci,fsdev=homefs,mount_tag=home \
 # -fsdev local,id=musicfs,path=/mnt/music,security_model=none \
 # -device virtio-8p-pci,fsdev=musicfs,mount_tag=music
