# Common aliases - safe everywhere
alias d='ls -al'
alias h='history'
alias vi='vim'
alias deleteb='git for-each-ref --format="%(refname:short) %(upstream:track)" refs/heads | awk '\''$2=="[gone]"{print $1}'\'' | xargs -r git branch -D'

HOST="$(hostname -s)"

case "$HOST" in
    andy-pc)
        alias addons='cd "/mnt/games/lutris/games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_retail_/Interface/AddOns/organiseMyAlts"'
        alias lpduplex='lp -d '\''Canon_GX4000_series@c98D55600000.local'\'' -o Duplex=DuplexNoTumble'
        alias lutris='flatpak run net.lutris.Lutris'
        alias m1='cd /mnt/movies/Movies'
        alias qt='pyside6-designer'
        alias savedv='cd "/mnt/games/lutris/games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_retail_/WTF/Account/GLAWSTER/SavedVariables"'
        alias v2='cd /mnt/video/TV'
        alias rmov='cd /mnt/raid/Movies'
        alias rtv='cd /mnt/raid/TV'
        alias wowenv='export WINEPREFIX="/mnt/games2/prefixes/battlenet"; \
export WINE="/home/andy/.local/share/lutris/runners/wine/wine-10.20-staging-tkg-amd64/bin/wine"'
        alias updateall='sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y && flatpak update -y'
        alias omp08='python -m pip install --upgrade "git+file:///home/andy/Source/organiseMyProjects@v0.8"'
        ;;


    raid-pc)
        # RAID/server-specific aliases go here
        alias updateall='sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y'
	alias disks='lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS'
	alias smart='sudo smartctl -a'
	alias services='systemctl --failed'
	alias temps='sensors'
        ;;

    *)
        ;;
esac
