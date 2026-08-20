# ~/.bashrc: executed by bash(1) for non-login shells.
# see /usr/share/doc/bash/examples/startup-files (in the package bash-doc)
# for examples

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# disable Warp shell integration because it leaks escape sequences with direnv/bash-preexec
export WARP_DISABLE_SHELL_INTEGRATION=1

# don't put duplicate lines or lines starting with space in the history.
# See bash(1) for more options
HISTCONTROL=ignoreboth

# append to the history file, don't overwrite it
shopt -s histappend

# for setting history length see HISTSIZE and HISTFILESIZE in bash(1)
HISTSIZE=1000
HISTFILESIZE=2000

# check the window size after each command and, if necessary,
# update the values of LINES and COLUMNS.
shopt -s checkwinsize

# If set, the pattern "**" used in a pathname expansion context will
# match all files and zero or more directories and subdirectories.
#shopt -s globstar

# make less more friendly for non-text input files, see lesspipe(1)
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# set variable identifying the chroot you work in (used in the prompt below)
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# colored GCC warnings and errors
#export GCC_COLORS='error=01;31:warning=01;35:note=01;36:caret=01;32:locus=01:quote=01'

# Alias definitions.
# You may want to put all your additions into a separate file like
# ~/.bash_aliases, instead of adding them here directly.
# See /usr/share/doc/bash-doc/examples in the bash-doc package.

if [ -f ~/.bash_aliases ]; then
    . ~/.bash_aliases
fi

# enable programmable completion features (you don't need to enable
# this, if it's already enabled in /etc/bash.bashrc and /etc/profile
# sources /etc/bash.bashrc).
if ! shopt -oq posix; then
  if [ -f /usr/share/bash-completion/bash_completion ]; then
    . /usr/share/bash-completion/bash_completion
  elif [ -f /etc/bash_completion ]; then
    . /etc/bash_completion
  fi
fi

cdl() {
   cd "$1" && ls -al
}

# Git branch + status in prompt
parse_git_branch() {
    git branch 2>/dev/null | sed -n '/\* /s///p'
}

parse_git_status() {
    git status --porcelain 2>/dev/null | wc -l
}

conda_prompt() {
    if [ -n "$CONDA_DEFAULT_ENV" ]; then
        printf '(%s) ' "$CONDA_DEFAULT_ENV"
    fi
}

export CONDA_CHANGEPS1=false
export PS1="\$(conda_prompt)\[\e[96m\]\w\[\e[93m\]\$(branch=\$(parse_git_branch); status=\$(parse_git_status); if [ -n \"\$branch\" ]; then output=\" (\$branch\"; if [ \$status -gt 0 ]; then output=\"\$output *\$status\"; fi; output=\"\$output)\"; echo \"\$output\"; fi)\[\e[0m\]\n\$ "

export EDITOR=vim
export VISUAL=vim
export QT_QPA_PLATFORMTHEME=qt5ct


# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
__conda_setup="$('/home/andy/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "/home/andy/miniconda3/etc/profile.d/conda.sh" ]; then
        . "/home/andy/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="/home/andy/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup
# <<< conda initialize <<<

eval "$(direnv hook bash)"


# Added by Antigravity CLI installer
export PATH="/home/andy/.local/bin:$PATH"

# >>> grok installer >>>
export PATH="$HOME/.grok/bin:$PATH"
[[ -r "$HOME/.grok/completions/bash/grok.bash" ]] && source "$HOME/.grok/completions/bash/grok.bash"
# <<< grok installer <<<
