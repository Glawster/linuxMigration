# Upload a file or directory to the configured remote pod over SSH.

local src="$1"
local dst="$2"
scp -r -P "$SSH_PORT" -i "$SSH_KEY" \
	-o StrictHostKeyChecking=no \
	-o UserKnownHostsFile=/dev/null \
	"$src" "$SSH_TARGET:$dst"
