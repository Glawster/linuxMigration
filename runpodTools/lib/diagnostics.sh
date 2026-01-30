#!/usr/bin/env bash
# lib/diagnostics.sh
# Template drift diagnostics
# All operations are read-only and safe for dry run mode

runDiagnostics() {
  logTask "evaluating template drift diagnostics"
  
  echo "--- System Info ---"
  runCmdReadOnly uname -a
  
  echo "--- User Info ---"
  runCmdReadOnly whoami
  runCmdReadOnly id
  runCmdReadOnly hostname

  echo "--- OS Release ---"
  runShReadOnly "cat /etc/os-release 2>/dev/null || true"
  
  echo "--- GPU Info ---"
  runShReadOnly "nvidia-smi 2>/dev/null || echo \"nvidia-smi not available\""
  
  echo "--- Shell ---"
  runShReadOnly echo "shell=$SHELL"
  
  echo "--- Conda Environment Variables ---"
  runShReadOnly "env | grep -i conda || echo \"No conda environment variables\""
  
  echo "--- Conda Config Files ---"
  runShReadOnly "ls -la /root/.condarc /etc/conda/.condarc 2>/dev/null || echo \"No conda config files\""
  
  echo "--- Python Info ---"
  
  if runShReadOnly "command -v python3 >/dev/null 2>&1"; then
    runCmdReadOnly python3 --version
    runCmdReadOnly which python3
  else
    echo "python3 not found"
  fi
  
  echo "--- Disk Usage ---"
  runCmdReadOnly df -h /workspace 2>/dev/null || runCmdReadOnly df -h / || true
  echo
}
