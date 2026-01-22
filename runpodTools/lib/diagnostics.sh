#!/usr/bin/env bash
# lib/diagnostics.sh
# Template drift diagnostics

runDiagnostics() {
  logTask "evaluating template drift diagnostics"
  
  echo "--- System Info ---"
  run uname -a
  
  echo "--- User Info ---"
  run whoami
  run id
  run hostname

  echo "--- OS Release ---"
  run cat /etc/os-release 2>/dev/null || true
  
  echo "--- GPU Info ---"
  run nvidia-smi 2>/dev/null || echo "nvidia-smi not available"
  
  echo "--- Shell ---"
  run echo "shell=$SHELL"
  
  echo "--- Conda Environment Variables ---"
  run env | grep -i conda || echo "No conda environment variables"
  
  echo "--- Conda Config Files ---"
  run ls -la /root/.condarc /etc/conda/.condarc 2>/dev/null || echo "No conda config files"
  
  echo "--- Python Info ---"
  if isCommand python3; then
    run python3 --version
    run which python3
  else
    echo "python3 not found"
  fi
  
  echo "--- Disk Usage ---"
  run df -h /workspace 2>/dev/null || run df -h / || true
  echo
}
