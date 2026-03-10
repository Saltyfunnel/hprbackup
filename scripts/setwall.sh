#!/bin/bash
WALL="$1"

# Let wal run fully and apply everything as normal
wal -i "$WALL"

# Set wallpaper immediately after
swww img "$WALL" --transition-type simple

# Update fastfetch wallpaper cache
ln -sf "$WALL" ~/.cache/current-wallpaper

# Restart waybar and mako in parallel
{ killall waybar 2>/dev/null; waybar & } &
{ killall mako 2>/dev/null; sleep 0.1; mako & disown; } &

hyprctl reload

notify-send -i "$WALL" "Theme Updated" "Colors synced to $(basename "$WALL")"
