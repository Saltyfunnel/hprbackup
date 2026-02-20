#!/usr/bin/env python3
import sys
import subprocess
import configparser
import json
from pathlib import Path
from PyQt6 import QtWidgets, QtGui, QtCore

# --- Configuration Constants ---
APP_DIRS = [
    Path.home() / ".local/share/applications",
    Path("/usr/share/applications"),
]
ICON_SIZE = 24  
TERMINAL = "kitty"
FONT_NAME = "Cascadia Code Nerd Font"
FONT_SIZE = 10
WINDOW_WIDTH = 680
WINDOW_HEIGHT = 580
GRID_COLUMNS = 2
WALLPAPER_HEIGHT = 180
BACKGROUND_OPACITY = 180  # 0-255 (220 = ~86% opaque, nice balance)

EXCLUDE_KEYWORDS = [
    "ssh", "server", "avahi", "helper", "setup", 
    "settings daemon", "gnome-session", "kde-", "xfce-",
    "lstopo", "hardware locality"
]

class AppPicker(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("App Launcher")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # Added StaysOnTop and explicit focus hints to prevent WM interference
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint | 
            QtCore.Qt.WindowType.Tool |
            QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Disable context menus globally for this window
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        
        self.BG, self.FG, self.ACCENT, self.ACCENT2 = self._get_pywal_colors()
        self.wallpaper_path = self._get_wallpaper_path()
        self.applications = self._find_applications()
        self.filtered_apps = self.applications.copy()
        
        self.search_input = self._create_search_input()
        self.scroll_area = self._create_scroll_area()
        self.grid_widget = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.grid_widget)
        
        self.current_row = 0
        self.current_col = 0
        self.app_buttons = []
        
        self.populate_grid()
        self.scroll_area.setWidget(self.grid_widget)

        self._setup_layout()
        self._calculate_translucent_bg()
        self._apply_styles()
        self.search_input.setFocus()
        self._center_window()
        self.show()
        self._setup_pywal_watcher()

    def _get_contrast_color(self, hex_color):
        color = QtGui.QColor(hex_color)
        brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
        return "#000000" if brightness > 128 else "#ffffff"

    def _setup_pywal_watcher(self):
        self.pywal_path = str(Path.home() / ".cache/wal/colors.json")
        self.watcher = QtCore.QFileSystemWatcher([self.pywal_path])
        self.watcher.fileChanged.connect(self.update_colors_live)

    def update_colors_live(self):
        self.BG, self.FG, self.ACCENT, self.ACCENT2 = self._get_pywal_colors()
        self.wallpaper_path = self._get_wallpaper_path()
        self._calculate_translucent_bg()
        self._apply_styles()
        self._load_wallpaper()
        
        arch_icon = self._get_themed_logo("archlinux-logo", self.FG)
        if self.search_input.actions():
            self.search_input.actions()[0].setIcon(arch_icon)

    def _create_search_input(self):
        search_input = QtWidgets.QLineEdit()
        search_input.setPlaceholderText("Search...")
        search_input.textChanged.connect(self.filter_grid)
        search_input.returnPressed.connect(self.launch_selected)
        search_input.keyPressEvent = self._search_key_press_event
        search_input.setMaximumWidth(WINDOW_WIDTH - 60)
        
        arch_icon = self._get_themed_logo("archlinux-logo", self.FG)
        search_input.addAction(
            QtGui.QAction(arch_icon, "", search_input),
            QtWidgets.QLineEdit.ActionPosition.LeadingPosition
        )
        return search_input

    def _create_scroll_area(self):
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll
    
    def _setup_layout(self):
        self.main_frame = QtWidgets.QFrame()
        self.main_frame.setObjectName("MainFrame")
        layout = QtWidgets.QVBoxLayout(self.main_frame)
        
        self.wallpaper_label = QtWidgets.QLabel()
        self.wallpaper_label.setFixedHeight(WALLPAPER_HEIGHT)
        self.wallpaper_label.setScaledContents(True)
        self.wallpaper_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._load_wallpaper()
        
        layout.addWidget(self.wallpaper_label)
        layout.addSpacing(15)
        layout.addWidget(self.search_input, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(10)
        layout.addWidget(self.scroll_area)
        
        layout.setContentsMargins(20, 20, 20, 20)
        
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.addWidget(self.main_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)

    def populate_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.app_buttons.clear()
        sorted_apps = sorted(self.filtered_apps, key=lambda a: a["Name"])
        
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        
        for idx, app in enumerate(sorted_apps):
            row = idx // GRID_COLUMNS
            col = idx % GRID_COLUMNS
            btn = self._create_app_button(app)
            self.grid_layout.addWidget(btn, row, col)
            self.app_buttons.append(btn)
        
        self.current_row = 0
        self.current_col = 0
        self._update_selection()

    def _create_app_button(self, app):
        btn = QtWidgets.QPushButton()
        btn.setProperty("app_exec", app["Exec"])
        btn.setProperty("app_terminal", app["Terminal"])
        
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        
        icon_label = QtWidgets.QLabel()
        icon = self._get_app_icon(app.get("Icon", ""))
        pixmap = icon.pixmap(QtCore.QSize(ICON_SIZE, ICON_SIZE))
        icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        
        text_label = QtWidgets.QLabel(app["Name"])
        text_label.setObjectName("AppName")
        # Force white text color directly on the widget
        palette = text_label.palette()
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#ffffff"))
        palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#ffffff"))
        text_label.setPalette(palette)
        text_label.setStyleSheet("color: #ffffff !important;")
        
        layout.addWidget(icon_label)
        layout.addWidget(text_label, 1)
        
        btn.setLayout(layout)
        
        # Use pressed instead of clicked to avoid event bubbling/interference
        btn.pressed.connect(self.launch_selected)
        btn.setFixedHeight(50) 
        
        return btn

    def filter_grid(self, text):
        text = text.strip().lower()
        self.filtered_apps = [app for app in self.applications if text in app["Name"].lower()] if text else self.applications.copy()
        self.populate_grid()

    def _update_selection(self):
        for btn in self.app_buttons:
            btn.setProperty("selected", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        
        if self.app_buttons:
            idx = self.current_row * GRID_COLUMNS + self.current_col
            if 0 <= idx < len(self.app_buttons):
                target_btn = self.app_buttons[idx]
                target_btn.setProperty("selected", True)
                target_btn.style().unpolish(target_btn)
                target_btn.style().polish(target_btn)
                self.scroll_area.ensureWidgetVisible(target_btn)

    def launch_selected(self):
        # Determine the button either from mouse click (sender) or keyboard selection
        sender = self.sender()
        if isinstance(sender, QtWidgets.QPushButton):
            btn = sender
        else:
            if not self.app_buttons: return
            idx = self.current_row * GRID_COLUMNS + self.current_col
            if idx >= len(self.app_buttons): return
            btn = self.app_buttons[idx]
            
        cmd, term = btn.property("app_exec"), btn.property("app_terminal")
        
        if term: subprocess.Popen([TERMINAL, "-e", "bash", "-l", "-c", cmd])
        else: subprocess.Popen(cmd, shell=True)
        QtWidgets.QApplication.quit()

    def _search_key_press_event(self, event):
        key = event.key()
        if not self.app_buttons:
            if key == QtCore.Qt.Key.Key_Escape: QtWidgets.QApplication.quit()
            else: QtWidgets.QLineEdit.keyPressEvent(self.search_input, event)
            return
        
        max_row = (len(self.app_buttons) - 1) // GRID_COLUMNS
        max_col = GRID_COLUMNS - 1
        
        if key == QtCore.Qt.Key.Key_Down:
            if self.current_row < max_row:
                self.current_row += 1
                if (self.current_row * GRID_COLUMNS + self.current_col) >= len(self.app_buttons):
                    self.current_col = (len(self.app_buttons) - 1) % GRID_COLUMNS
            self._update_selection()
        elif key == QtCore.Qt.Key.Key_Up:
            if self.current_row > 0: self.current_row -= 1
            self._update_selection()
        elif key in [QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Tab]:
            if self.current_col < max_col and (self.current_row * GRID_COLUMNS + self.current_col + 1) < len(self.app_buttons):
                self.current_col += 1
            elif self.current_row < max_row:
                self.current_row += 1
                self.current_col = 0
            self._update_selection()
        elif key == QtCore.Qt.Key.Key_Left:
            if self.current_col > 0: self.current_col -= 1
            elif self.current_row > 0:
                self.current_row -= 1
                self.current_col = max_col
            self._update_selection()
        elif key == QtCore.Qt.Key.Key_Escape: QtWidgets.QApplication.quit()
        else: QtWidgets.QLineEdit.keyPressEvent(self.search_input, event)

    def _center_window(self):
        geo = QtWidgets.QApplication.primaryScreen().geometry()
        self.move((geo.width() - self.width()) // 2, (geo.height() - self.height()) // 2)

    def _parse_desktop_file(self, path):
        parser = configparser.ConfigParser(interpolation=None)
        try: parser.read(path, encoding="utf-8")
        except: return None
        if "Desktop Entry" not in parser: return None
        entry = parser["Desktop Entry"]
        if entry.get("Type") != "Application" or entry.getboolean("NoDisplay", fallback=False): return None
        return {"Name": entry.get("Name"), "Exec": entry.get("Exec", "").split("%", 1)[0].strip(), 
                "Icon": entry.get("Icon"), "Terminal": entry.getboolean("Terminal", fallback=False)}

    def _find_applications(self):
        apps, names = [], set()
        for app_dir in APP_DIRS:
            if not app_dir.exists(): continue
            for file in app_dir.glob("*.desktop"):
                info = self._parse_desktop_file(file)
                if info and info["Name"] not in names:
                    lower_name = info["Name"].lower()
                    if any(k in lower_name for k in EXCLUDE_KEYWORDS): continue
                    apps.append(info)
                    names.add(info["Name"])
        return apps

    def _recolor_icon(self, icon, color_hex):
        pixmap = icon.pixmap(QtCore.QSize(20, 20))
        painter = QtGui.QPainter(pixmap)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QtGui.QColor(color_hex))
        painter.end()
        return QtGui.QIcon(pixmap)
        
    def _get_themed_logo(self, icon_name, color_hex):
        icon = QtGui.QIcon.fromTheme(icon_name)
        if icon.isNull(): icon = QtGui.QIcon.fromTheme("system-search")
        return self._recolor_icon(icon, color_hex)

    def _get_app_icon(self, icon_name):
        icon = QtGui.QIcon.fromTheme(icon_name)
        return icon if not icon.isNull() else QtGui.QIcon.fromTheme("application-default")

    def _get_pywal_colors(self):
        wal = Path.home() / ".cache/wal/colors.json"
        defaults = ("#1a1b26", "#c0caf5", "#7aa2f7", "#bb9af7")
        if not wal.exists(): return defaults
        try:
            data = json.loads(wal.read_text())
            return (data["special"]["background"], data["special"]["foreground"], 
                    data["colors"].get("color4", defaults[2]), data["colors"].get("color5", defaults[3]))
        except: return defaults
    
    def _calculate_translucent_bg(self):
        base = QtGui.QColor(self.BG)
        base.setAlpha(BACKGROUND_OPACITY)
        self.rgba_bg = base.name(QtGui.QColor.NameFormat.HexArgb)
    
    def _get_wallpaper_path(self):
        wal_file = Path.home() / ".cache/wal/wal"
        return wal_file.read_text().strip() if wal_file.exists() else None
    
    def _load_wallpaper(self):
        if not self.wallpaper_path or not Path(self.wallpaper_path).exists(): return
        pixmap = QtGui.QPixmap(self.wallpaper_path)
        if pixmap.isNull(): return
        scaled = pixmap.scaled(WINDOW_WIDTH, WALLPAPER_HEIGHT, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding, QtCore.Qt.TransformationMode.SmoothTransformation)
        cropped = scaled.copy((scaled.width()-WINDOW_WIDTH)//2, (scaled.height()-WALLPAPER_HEIGHT)//2, WINDOW_WIDTH, WALLPAPER_HEIGHT)
        rounded = QtGui.QPixmap(cropped.size())
        rounded.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(rounded)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        path = QtGui.QPainterPath()
        path.addRoundedRect(0, 0, WINDOW_WIDTH, WALLPAPER_HEIGHT, 10, 10)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()
        self.wallpaper_label.setPixmap(rounded)

    def _apply_styles(self):
        bg_color = QtGui.QColor(self.BG)
        bg_btn_color = bg_color.lighter(110)
        bg_btn_color.setAlpha(100)  # Make button background semi-transparent
        bg_btn = bg_btn_color.name(QtGui.QColor.NameFormat.HexArgb)
        
        highlight_text_color = self._get_contrast_color(self.ACCENT)
        hover_text_color = self._get_contrast_color(self.ACCENT2)
        
        # Also make accent colors slightly transparent for hover/selection
        accent_color = QtGui.QColor(self.ACCENT)
        accent_color.setAlpha(150)
        accent_semi = accent_color.name(QtGui.QColor.NameFormat.HexArgb)
        
        accent2_color = QtGui.QColor(self.ACCENT2)
        accent2_color.setAlpha(150)
        accent2_semi = accent2_color.name(QtGui.QColor.NameFormat.HexArgb)
        
        self.setStyleSheet(f"""
            QWidget {{ color: #ffffff !important; font-family: "{FONT_NAME}"; }}
            #MainFrame {{
                background-color: {self.rgba_bg};
                border: 1px solid {self.ACCENT};
                border-radius: 12px;
            }}
            QLineEdit {{
                border: none;
                border-bottom: 2px solid {self.ACCENT};
                padding: 10px 10px 10px 40px;
                background: rgba(0,0,0,0.1);
                border-radius: 4px;
                font-size: 14px;
                color: #ffffff !important;
            }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            
            QPushButton {{
                background: {bg_btn};
                border: none;
                border-radius: 6px;
                text-align: left;
                padding: 0px;
            }}
            
            QPushButton:hover {{
                background: {accent2_semi};
            }}
            
            QPushButton[selected="true"] {{
                background: {accent_semi};
            }}
        """)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    picker = AppPicker()
    sys.exit(app.exec())
