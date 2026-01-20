#!/usr/bin/env bash
# lib/diagnostics.sh
# Template drift diagnostics

runDiagnostics() {
  log "template drift diagnostics"
  
  echo "--- System Info ---"
  uname -a
  echo
  
  echo "--- OS Release ---"
  cat /etc/os-release 2>/dev/null || true
  echo
  
  echo "--- GPU Info ---"
  nvidia-smi 2>/dev/null || echo "nvidia-smi not available"
  echo
  
  echo "--- Shell ---"
  echo "shell=$SHELL"
  echo
  
  echo "--- Conda Environment Variables ---"
  env | grep -i conda || echo "No conda environment variables"
  echo
  
  echo "--- Conda Config Files ---"
  ls -la /root/.condarc /etc/conda/.condarc 2>/dev/null || echo "No conda config files"
  echo
  
  echo "--- Python Info ---"
  if isCommand python3; then
    python3 --version
    which python3
  else
    echo "python3 not found"
  fi
  echo
  
  echo "--- Disk Usage ---"
  df -h /workspace 2>/dev/null || df -h / || true
  echo
}
