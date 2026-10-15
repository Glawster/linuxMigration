# ~/.bashrc: executed by bash(1) for non-login shells.
# see /usr/share/doc/bash/examples/startup-files (in the package bash-doc)
# for examples

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# Normalise the hostname so the same file works on andy-pc, tv-pc and raid-pc.
HOST_SHORT="$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]')"

# Disable Warp shell integration because it leaks escape sequences with
# direnv/bash-preexec. This is harmless on machines where Warp is not installed.
export WARP_DISABLE_SHELL_INTEGRATION=1

# don't put duplicate lines or lines starting with space in the history.
HISTCONTROL=ignoreboth

# append to the history file, don't overwrite it
shopt -s histappend

# for setting history length see HISTSIZE and HISTFILESIZE in bash(1)
HISTSIZE=1000
HISTFILESIZE=2000

# check the window size after each command and, if necessary,
# update the values of LINES and COLUMNS.
shopt -s checkwinsize

# make less more friendly for non-text input files
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# set variable identifying the chroot you work in (used in the prompt below)
if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

# Alias definitions are kept separately so they can also be host-aware.
if [ -f "$HOME/.bash_aliases" ]; then
    . "$HOME/.bash_aliases"
fi

# enable programmable completion features
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

# Git branch + status in prompt. Return quietly outside a Git repository or on a
# machine where Git is not installed.
parse_git_branch() {
    command -v git >/dev/null 2>&1 || return
    git branch --show-current 2>/dev/null
}

parse_git_status() {
    command -v git >/dev/null 2>&1 || { printf '0'; return; }
    git status --porcelain 2>/dev/null | wc -l
}

conda_prompt() {
    if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
        printf '(%s) ' "$CONDA_DEFAULT_ENV"
    fi
}

# Make the host visually obvious when moving between the three PCs.
# 96 = cyan (andy-pc), 92 = green (tv-pc), 93 = yellow (raid-pc).
case "$HOST_SHORT" in
    andy-pc)
        PROMPT_HOST_COLOUR='96'
        ;;
    tv-pc)
        PROMPT_HOST_COLOUR='92'
        ;;
    raid-pc)
        PROMPT_HOST_COLOUR='93'
        ;;
    *)
        PROMPT_HOST_COLOUR='96'
        ;;
esac

export CONDA_CHANGEPS1=false
export PS1="\$(conda_prompt)\[\e[${PROMPT_HOST_COLOUR}m\]\u@\h:\w\[\e[93m\]\$(branch=\$(parse_git_branch); status=\$(parse_git_status); if [ -n \"\$branch\" ]; then output=\" (\$branch\"; if [ \"\$status\" -gt 0 ] 2>/dev/null; then output=\"\$output *\$status\"; fi; output=\"\$output)\"; echo \"\$output\"; fi)\[\e[0m\]\n\$ "

# Prefer vim where it is installed, otherwise fall back to vi.
if command -v vim >/dev/null 2>&1; then
    export EDITOR=vim
    export VISUAL=vim
else
    export EDITOR=vi
    export VISUAL=vi
fi

# Desktop-only Qt preference. raid-pc is intentionally headless.
case "$HOST_SHORT" in
    andy-pc|tv-pc)
        export QT_QPA_PLATFORMTHEME=qt5ct
        ;;
esac

# Conda is optional. Initialise it only on machines where Miniconda exists.
if [ -x "$HOME/miniconda3/bin/conda" ]; then
    __conda_setup="$("$HOME/miniconda3/bin/conda" 'shell.bash' 'hook' 2>/dev/null)"
    if [ $? -eq 0 ]; then
        eval "$__conda_setup"
    elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        . "$HOME/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="$HOME/miniconda3/bin:$PATH"
    fi
    unset __conda_setup
fi

# direnv is optional.
if command -v direnv >/dev/null 2>&1; then
    eval "$(direnv hook bash)"
fi

# User-installed command-line tools.
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# Grok is optional.
if [ -d "$HOME/.grok/bin" ]; then
    case ":$PATH:" in
        *":$HOME/.grok/bin:"*) ;;
        *) export PATH="$HOME/.grok/bin:$PATH" ;;
    esac
fi
[[ -r "$HOME/.grok/completions/bash/grok.bash" ]] && source "$HOME/.grok/completions/bash/grok.bash"

unset PROMPT_HOST_COLOUR
