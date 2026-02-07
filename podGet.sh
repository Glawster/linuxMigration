podGet() {
  # usage:
  #   podGet /remote/path [/local/dest]
  # examples:
  #   podGet /workspace/foo.txt                -> ./foo.txt
  #   podGet /workspace/foo.txt ./downloads    -> ./downloads/foo.txt
  #   podGet /workspace/somedir ./downloads    -> ./downloads/somedir/...

  local remotePath="${1:-}"
  local localDest="${2:-.}"

  if [[ -z "$remotePath" ]]; then
    echo "usage: podGet <remote_path> [local_dest]"
    return 1
  fi

  : "${SSH_TARGET:?SSH_TARGET not set}"
  : "${SSH_PORT:?SSH_PORT not set}"
  : "${SSH_KEY:?SSH_KEY not set}"

  # Determine if remotePath is a directory (ask the pod)
  if ssh -p "$SSH_PORT" -i "$SSH_KEY" \
       -o StrictHostKeyChecking=no \
       -o UserKnownHostsFile=/dev/null \
       "$SSH_TARGET" "test -d '$remotePath'"; then

    # remote is a directory → ensure localDest is a directory
    mkdir -p "$localDest"

    scp -r -P "$SSH_PORT" -i "$SSH_KEY" \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      "$SSH_TARGET:$remotePath" "$localDest/"

  else
    # remote is a file → if localDest is a directory (or ends with /), keep basename
    if [[ -d "$localDest" || "$localDest" == */ ]]; then
      mkdir -p "$localDest"
      localDest="${localDest%/}/$(basename "$remotePath")"
    else
      # ensure parent dir exists if a full filename path was given
      mkdir -p "$(dirname "$localDest")"
    fi

    scp -r -P "$SSH_PORT" -i "$SSH_KEY" \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      "$SSH_TARGET:$remotePath" "$localDest"
  fi
}
o
if [[ $# -eq 0 ]]; then
    echo "usage: source podGet.sh <remote_path> [local_dest]"
    return 1
fi
podGet "$1"