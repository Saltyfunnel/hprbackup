#!/bin/bash
################################################################################
# Hyprland Installer - 2026 Edition
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
    echo -e "\e[32m ✓\e[0m $1"
}

print_error() {
    echo -e "\e[31m ✗ Error:\e[0m $1" >&2
    exit 1
}

print_info() {
    echo -e "\e[33m ➜\e[0m $1"
}

run_command() {
    local cmd="$1"
    local desc="$2"
    
    print_info "$desc"
    if ! eval "$cmd"; then
        print_error "Failed: $desc"
    fi
    print_success "$desc completed"
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

# Check root
[[ "$EUID" -eq 0 ]] || print_error "This script must be run as root (use: sudo $0)"

################################################################################
# SYSTEM UPDATE & DRIVERS
################################################################################

print_header "System Update & Driver Installation"

run_command "pacman -Syu --noconfirm" "Updating system packages"

# Detect and install GPU drivers
GPU_INFO=$(lspci | grep -Ei "VGA|3D" || true)

if echo "$GPU_INFO" | grep -qi nvidia; then
    print_info "NVIDIA GPU detected"
    run_command "pacman -S --noconfirm --needed nvidia-open-dkms nvidia-utils lib32-nvidia-utils linux-headers" \
        "Installing NVIDIA drivers"
elif echo "$GPU_INFO" | grep -qi amd; then
    print_info "AMD GPU detected"
    run_command "pacman -S --noconfirm --needed xf86-video-amdgpu mesa vulkan-radeon lib32-vulkan-radeon linux-headers" \
        "Installing AMD drivers"
elif echo "$GPU_INFO" | grep -qi intel; then
    print_info "Intel GPU detected"
    run_command "pacman -S --noconfirm --needed mesa vulkan-intel lib32-vulkan-intel linux-headers" \
        "Installing Intel drivers"
else
    print_info "No dedicated GPU detected - using generic drivers"
fi

################################################################################
# PACKAGE INSTALLATION
################################################################################

print_header "Installing Core Packages"

# Core window manager and compositor packages
CORE_PACKAGES=(
    hyprland
    waybar
    swww
    mako
    sddm
    xdg-desktop-portal-hyprland
)

# Terminal and shell
TERMINAL_PACKAGES=(
    kitty
    starship
    fastfetch
)

# System utilities
UTILITY_PACKAGES=(
    grim
    slurp
    wl-clipboard
    polkit-kde-agent
    bluez
    bluez-utils
    blueman
    udiskie
    udisks2
    gvfs
)

# Applications
APP_PACKAGES=(
    firefox
    code
    mpv
    imv
    pavucontrol
    btop
    gnome-disk-utility
)

# Development tools
DEV_PACKAGES=(
    git
    base-devel
    wget
    curl
    nano
    jq
)

# Fonts
FONT_PACKAGES=(
    ttf-jetbrains-mono-nerd
    ttf-iosevka-nerd
    ttf-cascadia-code-nerd
)

# Media and file handling
MEDIA_PACKAGES=(
    poppler
    imagemagick
    ffmpeg
    chafa
)

# Compression tools
COMPRESSION_PACKAGES=(
    unzip
    p7zip
    tar
    gzip
    xz
    bzip2
    unrar
    trash-cli
)

# Python dependencies
PYTHON_PACKAGES=(
    python-pyqt5
    python-pyqt6
    python-pillow
    python-opencv
)

# Qt/Wayland support
QT_PACKAGES=(
    qt5-wayland
    qt6-wayland
)

# Combine all packages
ALL_PACKAGES=(
    "${CORE_PACKAGES[@]}"
    "${TERMINAL_PACKAGES[@]}"
    "${UTILITY_PACKAGES[@]}"
    "${APP_PACKAGES[@]}"
    "${DEV_PACKAGES[@]}"
    "${FONT_PACKAGES[@]}"
    "${MEDIA_PACKAGES[@]}"
    "${COMPRESSION_PACKAGES[@]}"
    "${PYTHON_PACKAGES[@]}"
    "${QT_PACKAGES[@]}"
)

run_command "pacman -S --noconfirm --needed ${ALL_PACKAGES[*]}" \
    "Installing packages"

# Install polkit fallback
pacman -S --noconfirm --needed polkit-gnome 2>/dev/null || true

################################################################################
# AUR HELPER & PACKAGES
################################################################################

print_header "Installing AUR Helper and Packages"

if ! command -v yay &>/dev/null; then
    print_info "Installing Yay AUR helper"
    run_command "rm -rf /tmp/yay" "Cleaning previous Yay installation"
    run_command "sudo -u $USER_NAME git clone https://aur.archlinux.org/yay.git /tmp/yay" \
        "Cloning Yay repository"
    (cd /tmp/yay && sudo -u $USER_NAME makepkg -si --noconfirm)
    print_success "Yay installed"
else
    print_success "Yay already installed"
fi

run_command "sudo -u $USER_NAME yay -S --noconfirm python-pywal16 python-pywalfox" \
    "Installing Pywal16 and Pywalfox from AUR"

################################################################################
# DIRECTORY STRUCTURE
################################################################################

print_header "Creating Directory Structure"

# Create config directories
CONFIG_DIRS=(
    "$CONFIG_DIR/hypr"
    "$CONFIG_DIR/waybar"
    "$CONFIG_DIR/kitty"
    "$CONFIG_DIR/fastfetch"
    "$CONFIG_DIR/mako"
    "$CONFIG_DIR/scripts"
    "$CONFIG_DIR/wal/templates"
    "$CONFIG_DIR/btop"
)

for dir in "${CONFIG_DIRS[@]}"; do
    sudo -u "$USER_NAME" mkdir -p "$dir"
done

sudo -u "$USER_NAME" mkdir -p "$WAL_CACHE"
sudo -u "$USER_NAME" mkdir -p "$USER_HOME/Pictures/Wallpapers"
print_success "Directory structure created"

################################################################################
# CONFIGURATION FILES
################################################################################

print_header "Installing Configuration Files"

# Clean old symlinks to prevent conflicts
print_info "Removing old symlinks"
OLD_SYMLINKS=(
    "$CONFIG_DIR/mako/config"
    "$CONFIG_DIR/waybar/style.css"
    "$CONFIG_DIR/kitty/kitty.conf"
    "$CONFIG_DIR/hypr/colors-hyprland.conf"
)

for symlink in "${OLD_SYMLINKS[@]}"; do
    sudo -u "$USER_NAME" rm -f "$symlink" 2>/dev/null || true
done

# Copy Hyprland configuration
if [[ -d "$CONFIGS_SRC/hypr" ]]; then
    print_info "Copying Hyprland configuration"
    sudo -u "$USER_NAME" cp -rf "$CONFIGS_SRC/hypr/"* "$CONFIG_DIR/hypr/" 2>/dev/null || true
    print_success "Hyprland configuration installed"
fi

# Copy Waybar configuration
if [[ -d "$CONFIGS_SRC/waybar" ]]; then
    print_info "Copying Waybar configuration"
    sudo -u "$USER_NAME" cp -rf "$CONFIGS_SRC/waybar/"* "$CONFIG_DIR/waybar/" 2>/dev/null || true
    print_success "Waybar configuration installed"
fi

# Copy or create Kitty configuration
if [[ -f "$CONFIGS_SRC/kitty/kitty.conf" ]]; then
    print_info "Copying Kitty configuration"
    sudo -u "$USER_NAME" cp "$CONFIGS_SRC/kitty/kitty.conf" "$CONFIG_DIR/kitty/kitty.conf"
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
fi
print_success "Kitty configuration installed"

# Copy Mako configuration
if [[ -f "$CONFIGS_SRC/mako/config" ]]; then
    print_info "Copying Mako configuration"
    sudo -u "$USER_NAME" cp "$CONFIGS_SRC/mako/config" "$CONFIG_DIR/mako/config"
    print_success "Mako configuration installed"
fi

# Copy Fastfetch configuration
if [[ -f "$CONFIGS_SRC/fastfetch/config.jsonc" ]]; then
    print_info "Copying Fastfetch configuration"
    sudo -u "$USER_NAME" cp "$CONFIGS_SRC/fastfetch/config.jsonc" "$CONFIG_DIR/fastfetch/config.jsonc"
    print_success "Fastfetch configuration installed"
fi

# Copy Starship configuration
if [[ -f "$CONFIGS_SRC/starship/starship.toml" ]]; then
    print_info "Copying Starship configuration"
    sudo -u "$USER_NAME" cp "$CONFIGS_SRC/starship/starship.toml" "$CONFIG_DIR/starship.toml"
    print_success "Starship configuration installed"
fi

# Copy btop configuration
if [[ -f "$CONFIGS_SRC/btop/btop.conf" ]]; then
    print_info "Copying btop configuration"
    sudo -u "$USER_NAME" cp "$CONFIGS_SRC/btop/btop.conf" "$CONFIG_DIR/btop/btop.conf"
    print_success "btop configuration installed"
fi

# Copy Pywal templates
if [[ -d "$CONFIGS_SRC/wal/templates" ]]; then
    print_info "Copying Pywal templates"
    sudo -u "$USER_NAME" cp -rf "$CONFIGS_SRC/wal/templates/"* "$CONFIG_DIR/wal/templates/" 2>/dev/null || true
    print_success "Pywal templates installed"
fi

################################################################################
# GPU-SPECIFIC ENVIRONMENT
################################################################################

print_header "Configuring GPU Environment"

GPU_ENV_FILE="$CONFIG_DIR/hypr/gpu-env.conf"

sudo -u "$USER_NAME" cat > "$GPU_ENV_FILE" << 'GPUHEADER'
# GPU Environment Variables
# Auto-generated during installation
# This file is sourced by hyprland.conf

GPUHEADER

if echo "$GPU_INFO" | grep -qi nvidia; then
    print_info "Configuring for NVIDIA GPU"
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
    print_info "Configuring for AMD GPU"
    sudo -u "$USER_NAME" cat >> "$GPU_ENV_FILE" << 'AMDENV'

# AMD-specific environment variables
env = LIBVA_DRIVER_NAME,radeonsi
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
AMDENV

elif echo "$GPU_INFO" | grep -qi intel; then
    print_info "Configuring for Intel GPU"
    sudo -u "$USER_NAME" cat >> "$GPU_ENV_FILE" << 'INTELENV'

# Intel-specific environment variables
env = LIBVA_DRIVER_NAME,iHD
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
INTELENV

else
    print_info "Using default Wayland environment"
    sudo -u "$USER_NAME" cat >> "$GPU_ENV_FILE" << 'DEFAULTENV'

# Default Wayland environment variables
env = XDG_SESSION_TYPE,wayland
env = QT_QPA_PLATFORM,wayland
DEFAULTENV
fi

print_success "GPU environment configured: $GPU_ENV_FILE"

################################################################################
# SCRIPTS & UTILITIES
################################################################################

print_header "Installing Scripts and Utilities"

# Copy user scripts
if [[ -d "$SCRIPTS_SRC" ]]; then
    print_info "Copying scripts"
    sudo -u "$USER_NAME" cp -rf "$SCRIPTS_SRC/"* "$CONFIG_DIR/scripts/"
    sudo -u "$USER_NAME" chmod +x "$CONFIG_DIR/scripts/"* 2>/dev/null || true
    print_success "Scripts installed and made executable"
fi

# Copy wallpapers
if [[ -d "$WALLPAPERS_SRC" ]]; then
    print_info "Copying wallpapers"
    sudo -u "$USER_NAME" cp -rf "$WALLPAPERS_SRC/"* "$USER_HOME/Pictures/Wallpapers/"
    print_success "Wallpapers installed"
fi

################################################################################
# BASHRC CONFIGURATION
################################################################################

print_header "Configuring Shell Environment"

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

print_header "Creating Pywal Symlinks"

# Create symlinks for Pywal-generated configs
if [[ -f "$CONFIG_DIR/wal/templates/mako-config" ]]; then
    sudo -u "$USER_NAME" ln -sf "$WAL_CACHE/mako-config" "$CONFIG_DIR/mako/config"
    print_info "Linked: mako config"
fi

if [[ -f "$CONFIG_DIR/wal/templates/waybar-style.css" ]]; then
    sudo -u "$USER_NAME" ln -sf "$WAL_CACHE/waybar-style.css" "$CONFIG_DIR/waybar/style.css"
    print_info "Linked: waybar style.css"
fi

if [[ -f "$CONFIG_DIR/wal/templates/colors-hyprland.conf" ]]; then
    sudo -u "$USER_NAME" ln -sf "$WAL_CACHE/colors-hyprland.conf" "$CONFIG_DIR/hypr/colors-hyprland.conf"
    print_info "Linked: Hyprland colors"
fi

print_success "Pywal symlinks created"

################################################################################
# SYSTEM SERVICES
################################################################################

print_header "Enabling System Services"

systemctl enable sddm.service 2>/dev/null || true
print_success "Display manager (SDDM) enabled"

systemctl enable bluetooth.service 2>/dev/null || true
print_success "Bluetooth service enabled"

################################################################################
# PERMISSIONS
################################################################################

print_header "Setting Permissions"

chown -R "$USER_NAME:$USER_NAME" "$CONFIG_DIR" "$CACHE_DIR" "$USER_HOME/Pictures" 2>/dev/null || true
print_success "Ownership configured correctly"

################################################################################
# INSTALLATION COMPLETE
################################################################################

clear
cat << 'EOF'

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     ✓  HYPRLAND INSTALLATION COMPLETE                        ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

EOF

print_success "Installation completed successfully!"
echo ""

print_header "Next Steps"
echo ""
echo "  1. Reboot your system:"
echo "     └─ sudo reboot"
echo ""
echo "  2. At the login screen (SDDM), select 'Hyprland' session"
echo ""
echo "  3. After logging in, open a terminal (SUPER+RETURN) and set a wallpaper:"
echo "     └─ wal -i ~/Pictures/Wallpapers/<your-wallpaper.jpg>"
echo "     └─ This will generate color schemes and start services"
echo ""

print_header "Key Bindings"
echo ""
echo "  SUPER + RETURN     Open terminal (Kitty)"
echo "  SUPER + Q          Close active window"
echo "  SUPER + ESC        Exit Hyprland"
echo "  SUPER + F          File manager"
echo "  SUPER + W          Wallpaper picker"
echo "  SUPER + D          Application picker"
echo "  SUPER + B          Browser (Firefox)"
echo "  SUPER + C          Code editor (VS Code)"
echo "  SUPER + I          System monitor (btop)"
echo "  SUPER + V          Toggle floating window"
echo ""
echo "  SUPER + H/L/K/J    Focus window (left/right/up/down)"
echo "  SUPER + [1-5]      Switch to workspace 1-5"
echo "  SUPER + SHIFT + [1-5]  Move window to workspace 1-5"
echo "  SUPER + ALT + E    Empty trash"
echo ""
echo "  Full configuration: ~/.config/hypr/hyprland.conf"
echo ""

print_header "Useful Commands"
echo ""
echo "  Generate new theme:     wal -i /path/to/image"
echo "  Reload Waybar:          killall waybar && waybar &"
echo "  Reload Hyprland:        hyprctl reload"
echo "  View logs:              journalctl -xeu sddm"
echo ""

print_success "Enjoy your new Hyprland setup!"
echo ""
