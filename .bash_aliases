alias d="ls -al"
alias qt="pyside6-designer"
alias lutris="flatpak run net.lutris.Lutris"
alias v1="cd /mnt/video1"
alias v2="cd /mnt/video2"
alias v3="cd /mnt/video3"
alias m1="cd /mnt/movie1"
alias m2="cd /mnt/movie2"
alias mp="cd /mnt/myPictures"
alias mvid="cd /mnt/myVideo"
alias addons='cd "/mnt/games/lutris/games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_retail_/Interface/AddOns/organiseMyAlts"'
alias savedv='cd "/mnt/games/lutris/games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_retail_/WTF/Account/GLAWSTER/SavedVariables"'

# enable color support and colorized command aliases
if [ -x /usr/bin/dircolors ]; then
	test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
	alias ls='ls --color=auto'
	alias grep='grep --color=auto'
	alias fgrep='fgrep --color=auto'
	alias egrep='egrep --color=auto'
fi

# ls aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# history / editor helpers
alias h='history'
alias vi='vim'

# Battle.net / WoW addon installer environment
alias wowenv='export WINEPREFIX="/mnt/games2/prefixes/battlenet"; \
export WINE="/home/andy/.local/share/lutris/runners/wine/wine-10.20-staging-tkg-amd64/bin/wine"'

# Add an "alert" alias for long running commands. Use like so:
#   sleep 10; alert
alias alert='notify-send --urgency=low -i "$([ $? = 0 ] && echo terminal || echo error)" "$(history | tail -n1 | sed -e '\''s/^\s*[0-9]\+\s*//;s/[;&|]\s*alert$//'\'' )"'

# useful commands
alias deleteb='git branch -vv | awk "/: gone]/{print \$1}" | xargs -r git branch -D'
alias deletep='git branch -vv | awk "/: gone]/{print \$1}"'
alias updateall='sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y && flatpak update -y'
