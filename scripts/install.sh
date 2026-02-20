#!/bin/bash
################################################################################
# Hyprland Installer - 2026 Edition
# Unified installer for AMD/Nvidia/Intel GPUs with automatic configuration
################################################################################

set -euo pipefail

################################################################################
# COLORS & STYLES
################################################################################

# Reset
RST="\e[0m"

# Regular colors
BLK="\e[30m"; RED="\e[31m"; GRN="\e[32m"; YLW="\e[33m"
BLU="\e[34m"; MAG="\e[35m"; CYN="\e[36m"; WHT="\e[37m"

# Bright colors
BBLK="\e[90m"; BRED="\e[91m"; BGRN="\e[92m"; BYLW="\e[93m"
BBLU="\e[94m"; BMAG="\e[95m"; BCYN="\e[96m"; BWHT="\e[97m"

# Styles
BLD="\e[1m"; DIM="\e[2m"; ITL="\e[3m"; UND="\e[4m"

# Background colors
BG_BLU="\e[44m"; BG_MAG="\e[45m"; BG_CYN="\e[46m"

# Step tracking
STEP=0
TOTAL_STEPS=9

################################################################################
# HELPER FUNCTIONS
################################################################################

# Draws a full-width horizontal rule
hr() {
    local char="${1:-─}"
    local color="${2:-$BBLK}"
    local cols=$(tput cols 2>/dev/null || echo 80)
    echo -e "${color}$(printf "%${cols}s" | tr ' ' "$char")${RST}"
}

# Centered text
center() {
    local text="$1"
    local raw="${text//$'\e'[*([0-9;])m/}"   # strip ANSI for width calc
    local raw2; raw2=$(echo -e "$raw" | sed 's/\x1b\[[0-9;]*m//g')
    local len=${#raw2}
    local cols=$(tput cols 2>/dev/null || echo 80)
    local pad=$(( (cols - len) / 2 ))
    printf "%${pad}s" ""
    echo -e "$text"
}

# Spinner for long operations (ASCII only, no interactive stdin)
spinner() {
    local pid=$1
    local msg="$2"
    local frames=('▏' '▎' '▍' '▌' '▋' '▊' '▉' '█' '▉' '▊' '▋' '▌' '▍' '▎')
    local i=0
    tput civis 2>/dev/null || true   # hide cursor
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r  ${BCYN}${frames[$i]}${RST}  ${DIM}${msg}${RST}   "
        i=$(( (i + 1) % ${#frames[@]} ))
        sleep 0.08
    done
    tput cnorm 2>/dev/null || true   # restore cursor
    printf "\r"
}

print_banner() {
    clear
    local cols=$(tput cols 2>/dev/null || echo 80)
    echo ""
    hr "═" "$BBLU"
    echo ""
    center "${BLD}${BCYN}  ██╗  ██╗██╗   ██╗██████╗ ██████╗ ██╗      █████╗ ███╗   ██╗██████╗ ${RST}"
    center "${BLD}${BCYN}  ██║  ██║╚██╗ ██╔╝██╔══██╗██╔══██╗██║     ██╔══██╗████╗  ██║██╔══██╗${RST}"
    center "${BLD}${BMAG}  ███████║ ╚████╔╝ ██████╔╝██████╔╝██║     ███████║██╔██╗ ██║██║  ██║${RST}"
    center "${BLD}${BMAG}  ██╔══██║  ╚██╔╝  ██╔═══╝ ██╔══██╗██║     ██╔══██║██║╚██╗██║██║  ██║${RST}"
    center "${BLD}${BBLU}  ██║  ██║   ██║   ██║     ██║  ██║███████╗██║  ██║██║ ╚████║██████╔╝${RST}"
    center "${BLD}${BBLU}  ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ${RST}"
    echo ""
    center "${DIM}${WHT}Automated installer for Hyprland · Wayland · Arch Linux · 2026 Edition${RST}"
    echo ""
    hr "═" "$BBLU"
    echo ""
}

print_phase() {
    STEP=$((STEP + 1))
    local title="$1"
    local icon="${2:-󰣐}"
    local pct=$(( STEP * 100 / TOTAL_STEPS ))

    echo ""
    hr "─" "$BBLK"
    echo -e "  ${BLD}${BBLU}[${STEP}/${TOTAL_STEPS}]${RST}  ${BLD}${BWHT}${title}${RST}  ${DIM}(${pct}%)${RST}"
    hr "─" "$BBLK"
}

print_success() {
    echo -e "  ${BGRN}✔${RST}  $1"
}

print_error() {
    echo ""
    echo -e "  ${BRED}✘  ERROR:${RST} $1" >&2
    echo ""
    exit 1
}

print_info() {
    echo -e "  ${BCYN}→${RST}  ${DIM}$1${RST}"
}

print_item() {
    echo -e "     ${BBLK}·${RST}  $1"
}

# Run a command with a live spinner
run_command() {
    local cmd="$1"
    local desc="$2"
    print_info "$desc"
    eval "$cmd" > /tmp/hypr_install_log 2>&1 &
    local pid=$!
    spinner "$pid" "$desc"
    wait "$pid" || print_error "Failed: $desc (see /tmp/hypr_install_log)"
    print_success "$desc"
}

################################################################################
# CONFIGURATION
################################################################################

# User and directory setup
USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
CONFIG_DIR="$USER_HOME/.config"
CACHE_DIR="$USER_HOME/.cache"
WAL_CACHE="$CACHE_DIR/wal"

# Repository paths
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_SRC="$REPO_ROOT/scripts"
CONFIGS_SRC="$REPO_ROOT/configs"
WALLPAPERS_SRC="$REPO_ROOT/Pictures/Wallpapers"

print_banner

# Check root
[[ "$EUID" -eq 0 ]] || print_error "This script must be run as root (use: sudo $0)"

echo -e "  ${DIM}User:${RST}  ${BLD}${WHT}${USER_NAME}${RST}"
echo -e "  ${DIM}Home:${RST}  ${BLD}${WHT}${USER_HOME}${RST}"
echo -e "  ${DIM}Repo:${RST}  ${BLD}${WHT}${REPO_ROOT}${RST}"
echo ""

# Prompt for user password once and cache it for the full install
echo -e "  ${BLD}${BYLW}Password required${RST}  ${DIM}(enter once — cached for the full install)${RST}"
echo ""

# Read password interactively
read -r -s -p "  $(echo -e "${BCYN}Password for ${USER_NAME}:${RST} ")" USER_PASS
echo ""

# Validate the password
if ! echo "$USER_PASS" | su -c "true" "$USER_NAME" 2>/dev/null; then
    print_error "Incorrect password"
fi

# Write a sudoers drop-in so USER_NAME can sudo without password for this session
SUDOERS_TMP="/etc/sudoers.d/hypr-install-tmp"
echo "$USER_NAME ALL=(ALL) NOPASSWD: ALL" > "$SUDOERS_TMP"
chmod 0440 "$SUDOERS_TMP"
# Remove it when the script exits
trap 'rm -f "$SUDOERS_TMP"; echo ""' EXIT

echo ""
print_success "Credentials accepted — no further prompts during install"
echo ""

################################################################################
# SYSTEM UPDATE & DRIVERS
################################################################################

print_phase "System Update & Driver Detection"

run_command "pacman -Syu --noconfirm" "Synchronizing package databases & upgrading system"

GPU_INFO=$(lspci | grep -Ei "VGA|3D" || true)

echo ""
echo -e "  ${BLD}${BYLW}GPU Detection${RST}"

if echo "$GPU_INFO" | grep -qi nvidia; then
    echo -e "  ${BBLU}▸${RST}  ${BLD}NVIDIA${RST} GPU detected"
    run_command "pacman -S --noconfirm --needed nvidia-open-dkms nvidia-utils lib32-nvidia-utils linux-headers" \
        "Installing NVIDIA open-source drivers"
elif echo "$GPU_INFO" | grep -qi amd; then
    echo -e "  ${BRED}▸${RST}  ${BLD}AMD${RST} GPU detected"
    run_command "pacman -S --noconfirm --needed xf86-video-amdgpu mesa vulkan-radeon lib32-vulkan-radeon linux-headers" \
        "Installing AMD drivers & Vulkan support"
elif echo "$GPU_INFO" | grep -qi intel; then
    echo -e "  ${BCYN}▸${RST}  ${BLD}Intel${RST} GPU detected"
    run_command "pacman -S --noconfirm --needed mesa vulkan-intel lib32-vulkan-intel linux-headers" \
        "Installing Intel drivers & Vulkan support"
else
    echo -e "  ${BBLK}▸${RST}  No dedicated GPU found — using generic drivers"
fi

################################################################################
# PACKAGE INSTALLATION
################################################################################

print_phase "Package Installation"

CORE_PACKAGES=(
    hyprland waybar swww mako sddm
    xdg-desktop-portal-hyprland
)
TERMINAL_PACKAGES=(kitty starship fastfetch)
UTILITY_PACKAGES=(
    grim slurp wl-clipboard polkit-kde-agent
    bluez bluez-utils blueman udiskie udisks2 gvfs
)
APP_PACKAGES=(firefox code mpv imv pavucontrol btop gnome-disk-utility)
DEV_PACKAGES=(git base-devel wget curl nano jq)
FONT_PACKAGES=(ttf-jetbrains-mono-nerd ttf-hack-nerd ttf-iosevka-nerd ttf-cascadia-code-nerd)
MEDIA_PACKAGES=(poppler imagemagick ffmpeg chafa)
COMPRESSION_PACKAGES=(unzip p7zip tar gzip xz bzip2 unrar trash-cli)
PYTHON_PACKAGES=(python-pyqt5 python-pyqt6 python-pillow python-opencv)
QT_PACKAGES=(qt5-wayland qt6-wayland)

ALL_PACKAGES=(
    "${CORE_PACKAGES[@]}" "${TERMINAL_PACKAGES[@]}" "${UTILITY_PACKAGES[@]}"
    "${APP_PACKAGES[@]}" "${DEV_PACKAGES[@]}" "${FONT_PACKAGES[@]}"
    "${MEDIA_PACKAGES[@]}" "${COMPRESSION_PACKAGES[@]}"
    "${PYTHON_PACKAGES[@]}" "${QT_PACKAGES[@]}"
)

# Pretty package group listing
echo ""
declare -A GROUP_LABELS=(
    ["Core WM"]="${CORE_PACKAGES[*]}"
    ["Terminal"]="${TERMINAL_PACKAGES[*]}"
    ["Utilities"]="${UTILITY_PACKAGES[*]}"
    ["Apps"]="${APP_PACKAGES[*]}"
    ["Dev Tools"]="${DEV_PACKAGES[*]}"
    ["Fonts"]="${FONT_PACKAGES[*]}"
    ["Media"]="${MEDIA_PACKAGES[*]}"
    ["Archives"]="${COMPRESSION_PACKAGES[*]}"
    ["Python"]="${PYTHON_PACKAGES[*]}"
    ["Qt/Wayland"]="${QT_PACKAGES[*]}"
)

for label in "Core WM" "Terminal" "Utilities" "Apps" "Dev Tools" "Fonts" "Media" "Archives" "Python" "Qt/Wayland"; do
    echo -e "  ${BBLU}${label}${RST}  ${DIM}${GROUP_LABELS[$label]}${RST}"
done
echo ""

run_command "pacman -S --noconfirm --needed ${ALL_PACKAGES[*]}" \
    "Installing all packages  (${#ALL_PACKAGES[@]} total)"

pacman -S --noconfirm --needed polkit-gnome 2>/dev/null || true
print_success "polkit-gnome (fallback) installed"

################################################################################
# AUR HELPER & PACKAGES
################################################################################

print_phase "AUR Helper — Yay"

if ! command -v yay &>/dev/null; then
    print_info "Yay not found — building from AUR"
    run_command "rm -rf /tmp/yay" "Cleaning previous Yay build directory"
    run_command "sudo -u $USER_NAME git clone https://aur.archlinux.org/yay.git /tmp/yay" \
        "Cloning Yay source"
    (cd /tmp/yay && sudo -u "$USER_NAME" makepkg -si --noconfirm) \
        > /tmp/hypr_install_log 2>&1 &
    spinner "$!" "Compiling and installing Yay"
    wait $! || print_error "Yay build failed (see /tmp/hypr_install_log)"
    print_success "Yay built and installed"
else
    print_success "Yay is already installed — skipping"
fi

sudo -u "$USER_NAME" yay -S --noconfirm python-pywal16 python-pywalfox \
    > /tmp/hypr_install_log 2>&1 &
spinner "$!" "Installing Pywal16 & Pywalfox from AUR"
wait $! || print_error "Failed to install AUR packages (see /tmp/hypr_install_log)"
print_success "Pywal16 & Pywalfox installed"

################################################################################
# DIRECTORY STRUCTURE
################################################################################

print_phase "Directory Structure"

CONFIG_DIRS=(
    "$CONFIG_DIR/hypr"    "$CONFIG_DIR/waybar"
    "$CONFIG_DIR/kitty"   "$CONFIG_DIR/fastfetch"
    "$CONFIG_DIR/mako"    "$CONFIG_DIR/scripts"
    "$CONFIG_DIR/wal/templates"  "$CONFIG_DIR/btop"
)

for dir in "${CONFIG_DIRS[@]}"; do
    sudo -u "$USER_NAME" mkdir -p "$dir"
    print_item "${DIM}$dir${RST}"
done

sudo -u "$USER_NAME" mkdir -p "$WAL_CACHE"
sudo -u "$USER_NAME" mkdir -p "$USER_HOME/Pictures/Wallpapers"
print_success "Directory tree created"

################################################################################
# CONFIGURATION FILES
################################################################################

print_phase "Configuration Files"

print_info "Removing stale symlinks"
OLD_SYMLINKS=(
    "$CONFIG_DIR/mako/config"
    "$CONFIG_DIR/waybar/style.css"
    "$CONFIG_DIR/kitty/kitty.conf"
    "$CONFIG_DIR/hypr/colors-hyprland.conf"
)
for symlink in "${OLD_SYMLINKS[@]}"; do
    sudo -u "$USER_NAME" rm -f "$symlink" 2>/dev/null || true
done
print_success "Old symlinks cleared"

# Hyprland
if [[ -d "$CONFIGS_SRC/hypr" ]]; then
    run_command "sudo -u $USER_NAME cp -rf '$CONFIGS_SRC/hypr/'* '$CONFIG_DIR/hypr/' 2>/dev/null || true" \
        "Installing Hyprland config"
fi

# Waybar
if [[ -d "$CONFIGS_SRC/waybar" ]]; then
    run_command "sudo -u $USER_NAME cp -rf '$CONFIGS_SRC/waybar/'* '$CONFIG_DIR/waybar/' 2>/dev/null || true" \
        "Installing Waybar config"
fi

# Kitty
if [[ -f "$CONFIGS_SRC/kitty/kitty.conf" ]]; then
    run_command "sudo -u $USER_NAME cp '$CONFIGS_SRC/kitty/kitty.conf' '$CONFIG_DIR/kitty/kitty.conf'" \
        "Installing Kitty config"
else
    print_info "Creating default Kitty configuration"
    sudo -u "$USER_NAME" cat > "$CONFIG_DIR/kitty/kitty.conf" << 'KITTYCONF'
# Kitty Terminal Configuration
font_family      JetBrainsMono Nerd Font
font_size        11.0
window_padding_width 8
confirm_os_window_close 0
enable_audio_bell no

# Tab bar
tab_bar_edge bottom
tab_bar_style powerline
tab_powerline_style slanted

# Performance
repaint_delay 10
input_delay 3
sync_to_monitor yes

# Dynamic color scheme from Pywal
include ~/.cache/wal/kitty-wal.conf
KITTYCONF
    print_success "Default Kitty config written"
fi

# Mako
if [[ -f "$CONFIGS_SRC/mako/config" ]]; then
    run_command "sudo -u $USER_NAME cp '$CONFIGS_SRC/mako/config' '$CONFIG_DIR/mako/config'" \
        "Installing Mako config"
fi

# Fastfetch
if [[ -f "$CONFIGS_SRC/fastfetch/config.jsonc" ]]; then
    run_command "sudo -u $USER_NAME cp '$CONFIGS_SRC/fastfetch/config.jsonc' '$CONFIG_DIR/fastfetch/config.jsonc'" \
        "Installing Fastfetch config"
fi

# Starship
if [[ -f "$CONFIGS_SRC/starship/starship.toml" ]]; then
    run_command "sudo -u $USER_NAME cp '$CONFIGS_SRC/starship/starship.toml' '$CONFIG_DIR/starship.toml'" \
        "Installing Starship prompt config"
fi

# btop
if [[ -f "$CONFIGS_SRC/btop/btop.conf" ]]; then
    run_command "sudo -u $USER_NAME cp '$CONFIGS_SRC/btop/btop.conf' '$CONFIG_DIR/btop/btop.conf'" \
        "Installing btop config"
fi

# Pywal templates
if [[ -d "$CONFIGS_SRC/wal/templates" ]]; then
    run_command "sudo -u $USER_NAME cp -rf '$CONFIGS_SRC/wal/templates/'* '$CONFIG_DIR/wal/templates/' 2>/dev/null || true" \
        "Installing Pywal templates"
fi

################################################################################
# GPU-SPECIFIC ENVIRONMENT
################################################################################

print_phase "GPU Environment"

GPU_ENV_FILE="$CONFIG_DIR/hypr/gpu-env.conf"

sudo -u "$USER_NAME" cat > "$GPU_ENV_FILE" << 'GPUHEADER'
# GPU Environment Variables
# Auto-generated during installation
# This file is sourced by hyprland.conf

GPUHEADER

if echo "$GPU_INFO" | grep -qi nvidia; then
    print_info "Writing NVIDIA Wayland environment variables"
    sudo -u "$USER_NAME" cat >> "$GPU_ENV_FILE" << 'NVIDIAENV'

# NVIDIA-specific environment variables
env = LIBVA_DRIVER_NAME,nvidia
env = XDG_SESSION_TYPE,wayland
env = __GLX_VENDOR_LIBRARY_NAME,nvidia
env = GBM_BACKEND,nvidia-drm
env = WLR_NO_HARDWARE_CURSORS,1
env = __GL_GSYNC_ALLOWED,1
env = __GL_VRR_ALLOWED,1
env = QT_QPA_PLATFORM,wayland

# Hardware cursor workaround for NVIDIA
cursor {
    no_hardware_cursors = true
}
NVIDIAENV

elif echo "$GPU_INFO" | grep -qi amd; then
    print_info "Writing AMD Wayland environment variables"
    sudo -u "$USER_NAME" cat >> "$GPU_ENV_FILE" << 'AMDENV'

# AMD-specific environment variables
env = LIBVA_DRIVER_NAME,radeonsi
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
AMDENV

elif echo "$GPU_INFO" | grep -qi intel; then
    print_info "Writing Intel Wayland environment variables"
    sudo -u "$USER_NAME" cat >> "$GPU_ENV_FILE" << 'INTELENV'

# Intel-specific environment variables
env = LIBVA_DRIVER_NAME,iHD
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
INTELENV

else
    print_info "Writing default Wayland environment variables"
    sudo -u "$USER_NAME" cat >> "$GPU_ENV_FILE" << 'DEFAULTENV'

# Default Wayland environment variables
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
DEFAULTENV
fi

print_success "GPU environment written → $GPU_ENV_FILE"

################################################################################
# SCRIPTS & UTILITIES
################################################################################

print_phase "Scripts, Wallpapers & Shell"

if [[ -d "$SCRIPTS_SRC" ]]; then
    run_command "sudo -u $USER_NAME cp -rf '$SCRIPTS_SRC/'* '$CONFIG_DIR/scripts/' && sudo -u $USER_NAME chmod +x '$CONFIG_DIR/scripts/'* 2>/dev/null || true" \
        "Installing user scripts"
fi

if [[ -d "$WALLPAPERS_SRC" ]]; then
    run_command "sudo -u $USER_NAME cp -rf '$WALLPAPERS_SRC/'* '$USER_HOME/Pictures/Wallpapers/'" \
        "Copying wallpapers"
fi

print_info "Writing ~/.bashrc"
sudo -u "$USER_NAME" cat > "$USER_HOME/.bashrc" << 'BASHRC'
#!/bin/bash
# Bash configuration for Hyprland setup

# Restore Pywal color scheme
if [[ -f ~/.cache/wal/sequences ]]; then
    cat ~/.cache/wal/sequences
fi

# Initialize Starship prompt
if command -v starship >/dev/null 2>&1; then
    eval "$(starship init bash)"
fi

# Display system information on new terminal
if command -v fastfetch >/dev/null 2>&1; then
    fastfetch
fi

# Useful aliases
alias ls='ls --color=auto'
alias ll='ls -lah --color=auto'
alias grep='grep --color=auto'
alias ..='cd ..'
alias ...='cd ../..'
alias update='sudo pacman -Syu'

# Safety nets
alias rm='rm -i'
alias mv='mv -i'
alias cp='cp -i'
BASHRC
print_success "Shell environment configured"

################################################################################
# PYWAL SYMLINKS
################################################################################

print_phase "Pywal Symlinks"

if [[ -f "$CONFIG_DIR/wal/templates/mako-config" ]]; then
    sudo -u "$USER_NAME" ln -sf "$WAL_CACHE/mako-config" "$CONFIG_DIR/mako/config"
    print_success "Linked: mako config"
fi

if [[ -f "$CONFIG_DIR/wal/templates/waybar-style.css" ]]; then
    sudo -u "$USER_NAME" ln -sf "$WAL_CACHE/waybar-style.css" "$CONFIG_DIR/waybar/style.css"
    print_success "Linked: waybar style.css"
fi

if [[ -f "$CONFIG_DIR/wal/templates/colors-hyprland.conf" ]]; then
    sudo -u "$USER_NAME" ln -sf "$WAL_CACHE/colors-hyprland.conf" "$CONFIG_DIR/hypr/colors-hyprland.conf"
    print_success "Linked: Hyprland colors"
fi

################################################################################
# SYSTEM SERVICES & PERMISSIONS
################################################################################

print_phase "Services & Permissions"

systemctl enable sddm.service      2>/dev/null && print_success "SDDM display manager enabled"    || true
systemctl enable bluetooth.service 2>/dev/null && print_success "Bluetooth service enabled"       || true

chown -R "$USER_NAME:$USER_NAME" "$CONFIG_DIR" "$CACHE_DIR" "$USER_HOME/Pictures" 2>/dev/null || true
print_success "Ownership set: ${USER_NAME}:${USER_NAME}"

################################################################################
# INSTALLATION COMPLETE
################################################################################

clear
print_banner

echo ""
hr "═" "$BGRN"
center "${BLD}${BGRN}  ✔  INSTALLATION COMPLETE  ✔${RST}"
hr "═" "$BGRN"
echo ""

# Summary table
echo -e "  ${BLD}${BWHT}What was installed:${RST}"
echo ""
echo -e "  ${BGRN}✔${RST}  System updated & GPU drivers configured"
echo -e "  ${BGRN}✔${RST}  ${#ALL_PACKAGES[@]} packages installed via pacman"
echo -e "  ${BGRN}✔${RST}  Yay AUR helper + Pywal16 & Pywalfox"
echo -e "  ${BGRN}✔${RST}  All dotfiles & configs deployed"
echo -e "  ${BGRN}✔${RST}  GPU environment written to hypr/gpu-env.conf"
echo -e "  ${BGRN}✔${RST}  Pywal symlinks created"
echo -e "  ${BGRN}✔${RST}  SDDM & Bluetooth services enabled"
echo ""
hr "─" "$BBLK"

echo ""
echo -e "  ${BLD}${BYLW}󰣐  Next Steps${RST}"
echo ""
echo -e "  ${BBLU}1.${RST}  Reboot your system"
echo -e "      ${DIM}sudo reboot${RST}"
echo ""
echo -e "  ${BBLU}2.${RST}  At the SDDM login screen, select ${BLD}Hyprland${RST} as your session"
echo ""
echo -e "  ${BBLU}3.${RST}  Open a terminal ${DIM}(SUPER+RETURN)${RST} and set your wallpaper:"
echo -e "      ${DIM}wal -i ~/Pictures/Wallpapers/<your-wallpaper.jpg>${RST}"
echo ""
hr "─" "$BBLK"

echo ""
echo -e "  ${BLD}${BYLW}  Key Bindings${RST}"
echo ""

bind_col() { echo -e "  ${BCYN}$1${RST}$(printf '%*s' $((24 - ${#1})) '')${DIM}$2${RST}"; }

bind_col "SUPER + RETURN"      "Open terminal (Kitty)"
bind_col "SUPER + Q"           "Close active window"
bind_col "SUPER + ESC"         "Exit Hyprland"
bind_col "SUPER + D"           "Application picker"
bind_col "SUPER + F"           "File manager"
bind_col "SUPER + W"           "Wallpaper picker"
bind_col "SUPER + B"           "Browser (Firefox)"
bind_col "SUPER + C"           "Code editor (VS Code)"
bind_col "SUPER + I"           "System monitor (btop)"
bind_col "SUPER + V"           "Toggle floating window"
echo ""
bind_col "SUPER + H/L/K/J"    "Focus window (←→↑↓)"
bind_col "SUPER + [1-5]"       "Switch workspace"
bind_col "SUPER+SHIFT + [1-5]" "Move window to workspace"
bind_col "SUPER+ALT + E"       "Empty trash"
echo ""
hr "─" "$BBLK"

echo ""
echo -e "  ${BLD}${BYLW}  Useful Commands${RST}"
echo ""
echo -e "  ${DIM}Generate new theme   ${RST}${BCYN}wal -i /path/to/image${RST}"
echo -e "  ${DIM}Reload Waybar        ${RST}${BCYN}killall waybar && waybar &${RST}"
echo -e "  ${DIM}Reload Hyprland      ${RST}${BCYN}hyprctl reload${RST}"
echo -e "  ${DIM}View logs            ${RST}${BCYN}journalctl -xeu sddm${RST}"
echo -e "  ${DIM}Full config          ${RST}${BCYN}~/.config/hypr/hyprland.conf${RST}"
echo ""
hr "═" "$BBLU"
echo ""
center "${DIM}Enjoy your new Hyprland setup  ·  Happy ricing!${RST}"
echo ""
