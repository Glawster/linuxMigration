# setSSH.sh
# usage:
#   source setSSH.sh "ssh root@213.173.108.199 -p 15386 -i ~/.ssh/id_ed25519"

setSSH() {
    if [[ $# -ne 1 ]]; then
        echo "usage: source setSSH.sh \"ssh user@host -p PORT -i KEY ...\""
        return 1
    fi

    local cmd="$1"

    # Remove leading "ssh " if present
    cmd="${cmd#ssh }"

    # Use read + <<< to split into words
    local -a args
    read -r -a args <<< "$cmd"

    local host=""
    local port="22"
    local key=""

    local i=0
    while (( i < ${#args[@]} )); do
        case "${args[i]}" in
            -p)   (( i++ )); port="${args[i]:-22}" ;;
            -i)   (( i++ )); key="${args[i]}"; key="${key/\~/$HOME}" ;;
            *)    if [[ -z $host ]]; then host="${args[i]}"; fi ;;
        esac
        (( i++ ))
    done

    if [[ -z $host ]]; then
        echo "failed to parse ssh target (user@host)"
        return 1
    fi
    if [[ -z $key ]]; then
        echo "failed to parse ssh identity file (-i)"
        return 1
    fi

    export SSH_TARGET="$host"
    export SSH_PORT="$port"
    export SSH_KEY="$key"

    echo "SSH session configured:"
    echo " SSH_TARGET=$SSH_TARGET"
    echo " SSH_PORT=$SSH_PORT"
    echo " SSH_KEY=$SSH_KEY"
}

if [[ $# -eq 0 ]]; then
    echo "usage: source setSSH.sh \"ssh user@host -p PORT -i KEY\""
    return 1
fi
setSSH "$1"