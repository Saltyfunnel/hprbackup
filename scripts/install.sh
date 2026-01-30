#!/bin/bash
################################################################################
# Hyprland Installer - 2026 Edition (Readable Progress Version)
# Unified installer for AMD/Nvidia/Intel GPUs with automatic configuration
################################################################################

set -euo pipefail

################################################################################
# HELPER FUNCTIONS
################################################################################

print_header() {
    echo -e "\n\e[1m\e[34m==>\e[0m \e[1m$1\e[0m"
}

print_success() {
    echo -e "\e[32m✓\e[0m $1"
}

print_error() {
    echo -e "\e[31m✗ Error:\e[0m $1" >&2
    exit 1
}

print_info() {
    echo -e "\e[33m→\e[0m $1"
}

run_step() {
    # Run a command, show minimal progress, and success/fail
    local desc="$1"
    local cmd="$2"
    echo -n "  $desc… "
    if eval "$cmd" &>/dev/null; then
        echo -e "\e[32m✓\e[0m"
    else
        echo -e "\e[31m✗\e[0m"
        print_error "$desc failed"
    fi
}

################################################################################
# CONFIGURATION
################################################################################

USER_NAME="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
CONFIG_DIR="$USER_HOME/.config"
CACHE_DIR="$USER_HOME/.cache"
WAL_CACHE="$CACHE_DIR/wal"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_SRC="$REPO_ROOT/scripts"
CONFIGS_SRC="$REPO_ROOT/configs"
WALLPAPERS_SRC="$REPO_ROOT/Pictures/Wallpapers"

[[ "$EUID" -eq 0 ]] || print_error "This script must be run as root (use: sudo $0)"

################################################################################
# SYSTEM UPDATE & GPU DRIVERS
################################################################################

print_header "Updating System & Installing GPU Drivers"
run_step "Updating system packages" "pacman -Syu --noconfirm"

GPU_INFO=$(lspci | grep -Ei "VGA|3D" || true)

if echo "$GPU_INFO" | grep -qi nvidia; then
    run_step "Installing NVIDIA drivers" \
        "pacman -S --noconfirm --needed nvidia-open-dkms nvidia-utils lib32-nvidia-utils linux-headers"
elif echo "$GPU_INFO" | grep -qi amd; then
    run_step "Installing AMD drivers" \
        "pacman -S --noconfirm --needed xf86-video-amdgpu mesa vulkan-radeon lib32-vulkan-radeon linux-headers"
elif echo "$GPU_INFO" | grep -qi intel; then
    run_step "Installing Intel drivers" \
        "pacman -S --noconfirm --needed mesa vulkan-intel lib32-vulkan-intel linux-headers"
else
    print_info "No dedicated GPU detected – using generic drivers"
fi

################################################################################
# PACKAGE INSTALLATION
################################################################################

print_header "Installing Packages"

ALL_PACKAGES=(
    # Core
    hyprland waybar swww mako sddm xdg-desktop-portal-hyprland
    # Terminal & shell
    kitty starship fastfetch
    # Utilities
    grim slurp wl-clipboard polkit-kde-agent bluez bluez-utils blueman udiskie udisks2 gvfs
    # Apps
    firefox code mpv imv pavucontrol btop gnome-disk-utility
    # Dev tools
    git base-devel wget curl nano jq
    # Fonts
    ttf-jetbrains-mono-nerd ttf-iosevka-nerd
    # Media
    poppler imagemagick ffmpeg chafa
    # Compression
    unzip p7zip tar gzip xz bzip2 unrar trash-cli
    # Python
    python-pyqt5 python-pyqt6 python-pillow python-opencv
    # Qt/Wayland
    qt5-wayland qt6-wayland
)

for pkg in "${ALL_PACKAGES[@]}"; do
    run_step "Installing $pkg" "pacman -S --noconfirm --needed $pkg"
done

# Polkit fallback
run_step "Installing polkit-gnome fallback" "pacman -S --noconfirm --needed polkit-gnome || true"

################################################################################
# AUR HELPER & PACKAGES
################################################################################

print_header "Installing AUR Helper (yay) and Pywal16"
if ! command -v yay &>/dev/null; then
    run_step "Cleaning old yay installation" "rm -rf /tmp/yay"
    run_step "Cloning yay repository" "sudo -u $USER_NAME git clone https://aur.archlinux.org/yay.git /tmp/yay"
    (cd /tmp/yay && sudo -u "$USER_NAME" makepkg -si --noconfirm &>/dev/null)
    print_success "Yay installed"
else
    print_info "Yay already installed"
fi

run_step "Installing Pywal16 from AUR" "sudo -u $USER_NAME yay -S --noconfirm python-pywal16"

################################################################################
# DIRECTORY STRUCTURE
################################################################################

print_header "Creating Directory Structure"

CONFIG_DIRS=(
    "$CONFIG_DIR/hypr" "$CONFIG_DIR/waybar" "$CONFIG_DIR/kitty" "$CONFIG_DIR/fastfetch"
    "$CONFIG_DIR/mako" "$CONFIG_DIR/scripts" "$CONFIG_DIR/wal/templates" "$CONFIG_DIR/btop"
)

for dir in "${CONFIG_DIRS[@]}"; do
    run_step "Creating $dir" "sudo -u $USER_NAME mkdir -p $dir"
done
run_step "Creating wal cache directory" "sudo -u $USER_NAME mkdir -p $WAL_CACHE"

################################################################################
# CONFIGURATION FILES
################################################################################

print_header "Installing Configuration Files"

# Hyprland, Waybar, Kitty, Mako, Starship, btop, Fastfetch, Pywal templates
CONFIG_SECTIONS=(
    "Hyprland: $CONFIGS_SRC/hypr:$CONFIG_DIR/hypr"
    "Waybar: $CONFIGS_SRC/waybar:$CONFIG_DIR/waybar"
    "Scripts: $SCRIPTS_SRC:$CONFIG_DIR/scripts"
    "Wallpapers: $WALLPAPERS_SRC:$USER_HOME/Pictures"
)

for section in "${CONFIG_SECTIONS[@]}"; do
    IFS=':' read -r name src dest <<< "$section"
    run_step "Copying $name" "sudo -u $USER_NAME cp -rf $src/* $dest/"
done

# Kitty default config if missing
if [[ ! -f "$CONFIG_DIR/kitty/kitty.conf" ]]; then
    run_step "Creating default Kitty config" "sudo -u $USER_NAME tee $CONFIG_DIR/kitty/kitty.conf >/dev/null << 'EOF'
font_family      JetBrainsMono Nerd Font
font_size        11.0
window_padding_width 8
confirm_os_window_close 0
enable_audio_bell no
tab_bar_edge bottom
tab_bar_style powerline
tab_powerline_style slanted
repaint_delay 10
input_delay 3
sync_to_monitor yes
include ~/.cache/wal/kitty-wal.conf
EOF"
fi

################################################################################
# GPU-SPECIFIC ENVIRONMENT
################################################################################

print_header "Configuring GPU Environment"
GPU_ENV_FILE="$CONFIG_DIR/hypr/gpu-env.conf"
sudo -u "$USER_NAME" tee "$GPU_ENV_FILE" >/dev/null << 'EOF'
# GPU Environment Variables
# Auto-generated during installation
EOF

if echo "$GPU_INFO" | grep -qi nvidia; then
    run_step "Configuring NVIDIA environment" "sudo -u $USER_NAME tee -a $GPU_ENV_FILE >/dev/null << 'EOF'
env = LIBVA_DRIVER_NAME,nvidia
env = XDG_SESSION_TYPE,wayland
env = __GLX_VENDOR_LIBRARY_NAME,nvidia
env = GBM_BACKEND,nvidia-drm
env = WLR_NO_HARDWARE_CURSORS,1
env = __GL_GSYNC_ALLOWED,1
env = __GL_VRR_ALLOWED,1
env = QT_QPA_PLATFORM,wayland
cursor { no_hardware_cursors = true }
EOF"
elif echo "$GPU_INFO" | grep -qi amd; then
    run_step "Configuring AMD environment" "sudo -u $USER_NAME tee -a $GPU_ENV_FILE >/dev/null << 'EOF'
env = LIBVA_DRIVER_NAME,radeonsi
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
EOF"
elif echo "$GPU_INFO" | grep -qi intel; then
    run_step "Configuring Intel environment" "sudo -u $USER_NAME tee -a $GPU_ENV_FILE >/dev/null << 'EOF'
env = LIBVA_DRIVER_NAME,iHD
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
EOF"
else
    run_step "Configuring default Wayland environment" "sudo -u $USER_NAME tee -a $GPU_ENV_FILE >/dev/null << 'EOF'
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
EOF"
fi

################################################################################
# SYSTEM SERVICES & PERMISSIONS
################################################################################

print_header "Enabling System Services"
run_step "Enabling SDDM" "systemctl enable sddm.service"
run_step "Enabling Bluetooth" "systemctl enable bluetooth.service"

print_header "Setting Permissions"
run_step "Setting ownership of configs" "chown -R $USER_NAME:$USER_NAME $CONFIG_DIR $CACHE_DIR"

################################################################################
# INSTALLATION COMPLETE
################################################################################

clear
cat << 'EOF'

╔═════════════════════════════════════════════════════╗
║                                                     ║
║     ✓  HYPRLAND INSTALLATION COMPLETE              ║
║                                                     ║
╚═════════════════════════════════════════════════════╝

EOF

print_success "Installation finished successfully!"
echo ""
