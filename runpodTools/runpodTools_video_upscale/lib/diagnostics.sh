#!/usr/bin/env bash
# lib/diagnostics.sh
# Template drift diagnostics

runDiagnostics() {
  logTask "evaluating template drift diagnostics"
  
  echo "--- System Info ---"
  runCmd uname -a
  
  echo "--- User Info ---"
  runCmd whoami
  runCmd id
  runCmd hostname

  echo "--- OS Release ---"
  runSh "cat /etc/os-release 2>/dev/null || true"
  
  echo "--- GPU Info ---"
  runSh "nvidia-smi 2>/dev/null || echo \"nvidia-smi not available\""
  
  echo "--- Shell ---"
  runSh echo "shell=$SHELL"
  
  echo "--- Conda Environment Variables ---"
  runSh env | grep -i conda || echo "No conda environment variables"
  
  echo "--- Conda Config Files ---"
  runSh ls -la /root/.condarc /etc/conda/.condarc 2>/dev/null || echo "No conda config files"
  
  echo "--- Python Info ---"
  
  if runSh "command -v python3 >/dev/null 2>&1"; then
    runCmd python3 --version
    runCmd which python3
  else
    echo "python3 not found"
  fi
  
  echo "--- Disk Usage ---"
  runCmd df -h /workspace 2>/dev/null || runCmd df -h / || true
  echo
}
