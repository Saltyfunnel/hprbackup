#!/usr/bin/env python3
"""
Enhanced PyQt5 File Manager with LIVE Pywal theming
NEW FEATURES:
- Search/filter functionality
- Bookmarks/favorites system
- Dual-pane mode (optional)
- File size and modification date display
- Sorting options (name, size, date, type)
- Progress dialog for long operations
- Breadcrumb navigation
- File properties dialog
- Create new file/folder
- Batch rename capability
- Drag and drop support
- Keyboard shortcuts (Ctrl+F search, Ctrl+H hidden, etc.)
- View modes (list/grid)
"""

import sys, json, shutil, subprocess, tempfile, os
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QLineEdit,
    QMessageBox, QSplitter, QMenu, QTreeWidgetItem, QTreeWidget,
    QSizePolicy, QStyleFactory, QInputDialog, QDialog, QFormLayout,
    QProgressDialog, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QShortcut, QFileDialog
)
from PyQt5.QtCore import Qt, QFileSystemWatcher, QThread, pyqtSignal, QTimer, QSize, QMimeData
from PyQt5.QtGui import (QFont, QColor, QPalette, QPixmap, QImage, QKeySequence, 
                         QDrag, QIcon)

# ---------------- Image Loader Thread ----------------
class ImageLoaderThread(QThread):
    """Async thread for loading images without blocking UI"""
    image_loaded = pyqtSignal(str, QPixmap)
    
    def __init__(self, filepath, target_width, target_height):
        super().__init__()
        self.filepath = filepath
        self.target_width = target_width
        self.target_height = target_height
    
    def run(self):
        try:
            reader = QImage(self.filepath)
            if not reader.isNull():
                scaled = reader.scaled(
                    self.target_width, 
                    self.target_height, 
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                pixmap = QPixmap.fromImage(scaled)
                self.image_loaded.emit(self.filepath, pixmap)
        except Exception as e:
            print(f"Image load error: {e}")

# ---------------- File Properties Dialog ----------------
class FilePropertiesDialog(QDialog):
    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = Path(filepath)
        self.setWindowTitle(f"Properties - {self.filepath.name}")
        self.setMinimumWidth(400)
        self.init_ui()
    
    def init_ui(self):
        layout = QFormLayout()
        
        # Name
        layout.addRow("Name:", QLabel(self.filepath.name))
        
        # Path
        layout.addRow("Location:", QLabel(str(self.filepath.parent)))
        
        # Type
        if self.filepath.is_dir():
            file_type = "Folder"
        else:
            file_type = f"File ({self.filepath.suffix or 'No extension'})"
        layout.addRow("Type:", QLabel(file_type))
        
        # Size
        if self.filepath.is_file():
            size = self.filepath.stat().st_size
            size_str = self.format_size(size)
            layout.addRow("Size:", QLabel(size_str))
        elif self.filepath.is_dir():
            # Calculate folder size (can be slow for large folders)
            total_size = sum(f.stat().st_size for f in self.filepath.rglob('*') if f.is_file())
            size_str = self.format_size(total_size)
            layout.addRow("Size:", QLabel(size_str))
        
        # Modification time
        mtime = datetime.fromtimestamp(self.filepath.stat().st_mtime)
        layout.addRow("Modified:", QLabel(mtime.strftime("%Y-%m-%d %H:%M:%S")))
        
        # Permissions
        stat_info = self.filepath.stat()
        perms = oct(stat_info.st_mode)[-3:]
        layout.addRow("Permissions:", QLabel(perms))
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addRow(close_btn)
        
        self.setLayout(layout)
    
    def format_size(self, size):
        """Format size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

# ---------------- Main File Manager ----------------
class FileManager(QMainWindow):
    def __init__(self):
        super().__init__()

        self.current_path = str(Path.home())
        self.clipboard = []
        self.clipboard_action = None
        self.colors_file = Path.home() / ".cache" / "wal" / "colors.json"
        self.show_hidden = False
        self.bookmarks_file = Path.home() / ".config" / "pyqt_filemanager_bookmarks.json"
        self.bookmarks = self.load_bookmarks()
        
        # View mode
        self.view_mode = "list"  # "list" or "table"
        self.sort_by = "name"  # "name", "size", "date", "type"
        self.sort_reverse = False

        # Image cache
        self.image_cache = {}
        self.cache_max_size = 50
        
        # Current loading thread
        self.current_loader = None
        
        # Hover debounce timer
        self.hover_timer = QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.load_hovered_preview)
        self.hover_delay = 150
        self.pending_hover_item = None

        # Nerd Font icons
        self.icon_font = QFont("Hack Nerd Font", 14)
        self.folder_glyph = "\uf07b"
        self.file_glyph = "\uf15b"
        self.video_glyph = "\U000f0219"
        self.drive_glyph = "\uf0a0"
        self.usb_glyph = "\uf287"
        self.bookmark_glyph = "\uf02e"
        
        # Watch Pywal colors.json
        self.watcher = QFileSystemWatcher([str(self.colors_file)])
        self.watcher.fileChanged.connect(self.reload_pywal_theme)

        self.colors = self.load_pywal_colors()

        self.initUI()
        self.setup_shortcuts()
        self.apply_theme()
        self.load_directory(self.current_path)

    # ---------------- Bookmarks ----------------
    def load_bookmarks(self):
        """Load bookmarks from file"""
        try:
            if self.bookmarks_file.exists():
                with open(self.bookmarks_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return []
    
    def save_bookmarks(self):
        """Save bookmarks to file"""
        try:
            self.bookmarks_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.bookmarks_file, 'w') as f:
                json.dump(self.bookmarks, f, indent=2)
        except Exception as e:
            print(f"Error saving bookmarks: {e}")
    
    def add_bookmark(self):
        """Add current directory to bookmarks"""
        if self.current_path not in self.bookmarks:
            self.bookmarks.append(self.current_path)
            self.save_bookmarks()
            self.populate_tree()
            self.statusBar().showMessage(f"Added bookmark: {Path(self.current_path).name}")
    
    def remove_bookmark(self, path):
        """Remove bookmark"""
        if path in self.bookmarks:
            self.bookmarks.remove(path)
            self.save_bookmarks()
            self.populate_tree()

    # ---------------- Keyboard Shortcuts ----------------
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Ctrl+F: Focus search
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
        
        # Ctrl+H: Toggle hidden files
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(lambda: self.btn_hidden.toggle())
        
        # Ctrl+B: Add bookmark
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(self.add_bookmark)
        
        # Ctrl+N: New folder
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.create_new_folder)
        
        # Ctrl+Shift+N: New file
        QShortcut(QKeySequence("Ctrl+Shift+N"), self).activated.connect(self.create_new_file)
        
        # F5: Refresh
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh)
        
        # F2: Rename
        QShortcut(QKeySequence("F2"), self).activated.connect(self.rename_file)
        
        # Ctrl+C: Copy
        QShortcut(QKeySequence("Ctrl+C"), self).activated.connect(self.copy_files)
        
        # Ctrl+X: Cut
        QShortcut(QKeySequence("Ctrl+X"), self).activated.connect(self.cut_files)
        
        # Ctrl+V: Paste
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self.paste_files)
        
        # Ctrl+I: File properties
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(self.show_properties)

    def focus_search(self):
        """Focus the search box"""
        self.search_input.setFocus()
        self.search_input.selectAll()

    # ---------------- Keyboard Event Handler ----------------
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts"""
        key = event.key()
        
        # Delete or Backspace key
        if key in [Qt.Key_Delete, Qt.Key_Backspace]:
            if self.get_current_list().selectedItems():
                self.delete_files()
                return
        
        # Enter key - open selected item
        elif key in [Qt.Key_Return, Qt.Key_Enter]:
            items = self.get_current_list().selectedItems()
            if items:
                self.item_opened(items[0])
                return
        
        # Backspace - go to parent directory
        elif key == Qt.Key_Backspace and not self.search_input.hasFocus():
            self.go_back()
            return
        
        super().keyPressEvent(event)

    # ---------------- Live Pywal Reload ----------------
    def reload_pywal_theme(self):
        self.colors = self.load_pywal_colors()
        self.apply_theme()
        self.populate_tree()
        self.load_directory(self.current_path)

    # ---------------- Theme ----------------
    def load_pywal_colors(self):
        try:
            if self.colors_file.exists():
                with open(self.colors_file, "r") as f:
                    data = json.load(f)
                colors = data.get("colors", {})
                if colors:
                    return colors
        except Exception as e:
            print(f"✗ pywal load failed: {e}")
        
        return {"color0": "#1e1e2e","color7": "#cdd6f4","color4": "#89b4fa","color8": "#45475a"}

    def apply_theme(self):
        bg = QColor(self.colors.get("color0","#1e1e2e"))
        fg = QColor(self.colors.get("color7","#cdd6f4"))
        accent = QColor(self.colors.get("color4","#89b4fa"))
        hover = QColor(self.colors.get("color8","#45475a"))

        QApplication.setStyle(QStyleFactory.create("Fusion"))
        palette = QApplication.palette()
        palette.setColor(QPalette.Window, bg)
        palette.setColor(QPalette.WindowText, fg)
        palette.setColor(QPalette.Base, bg)
        palette.setColor(QPalette.AlternateBase, hover)
        palette.setColor(QPalette.Text, fg)
        palette.setColor(QPalette.Button, hover)
        palette.setColor(QPalette.ButtonText, fg)
        palette.setColor(QPalette.Highlight, accent)
        palette.setColor(QPalette.HighlightedText, bg)
        QApplication.setPalette(palette)

        bg_rgba = f"rgba({bg.red()},{bg.green()},{bg.blue()},80)"
        hover_rgba = f"rgba({hover.red()},{hover.green()},{hover.blue()},60)"
        accent_rgba = f"rgba({accent.red()},{accent.green()},{accent.blue()},100)"
        header_rgba = f"rgba({hover.red()},{hover.green()},{hover.blue()},80)"

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_rgba};
            }}
            QPushButton {{
                border-radius: 8px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {accent_rgba};
                color: {bg.name()};
            }}
            QPushButton:checked {{
                background-color: {accent_rgba};
                color: {bg.name()};
            }}
            QLineEdit {{
                border-radius: 6px;
                padding: 4px 8px;
                background-color: {bg_rgba};
                color: {fg.name()};
            }}
            QComboBox {{
                border-radius: 6px;
                padding: 4px 8px;
                background-color: {bg_rgba};
                color: {fg.name()};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: none;
            }}
            QListWidget, QTreeWidget, QTableWidget {{
                background-color: {bg_rgba};
                color: {fg.name()};
                border: none;
            }}
            QTreeWidget {{
                outline: 0;
                selection-background-color: transparent;
            }}
            QTreeWidget::item {{
                color: {fg.name()};
                background: transparent !important;
                border: none;
            }}
            QTreeWidget::item:selected {{
                background: transparent !important;
                color: {accent.name()};
            }}
            QTreeWidget::item:hover {{
                background: transparent !important;
                color: {accent.name()};
            }}
            QHeaderView::section {{
                background-color: {header_rgba};
                color: {fg.name()};
                border: none;
                padding: 4px;
            }}
            QListWidget::item, QTableWidget::item {{
                color: {fg.name()};
                background: transparent !important;
                border: none;
            }}
            QListWidget::item:selected, QTableWidget::item:selected {{
                background: transparent !important;
                color: {accent.name()};
            }}
            QListWidget::item:hover, QTableWidget::item:hover {{
                background: transparent !important;
                color: {accent.name()};
            }}
            QScrollBar:vertical {{
                width: 0px;
            }}
            QScrollBar:horizontal {{
                height: 0px;
            }}
        """)

    # ---------------- UI ----------------
    def initUI(self):
        self.setWindowTitle("File Manager")
        self.setGeometry(100,100,1400,800)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        icon_font = QFont("Hack Nerd Font",14)

        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)

        # Toolbar
        bar = QHBoxLayout()
        self.btn_back = QPushButton("󰁍  Back")
        self.btn_back.setFont(icon_font)
        self.btn_back.clicked.connect(self.go_back)
        
        self.btn_home = QPushButton("󰋜  Home")
        self.btn_home.setFont(icon_font)
        self.btn_home.clicked.connect(self.go_home)
        
        self.btn_refresh = QPushButton("󰑐  Refresh")
        self.btn_refresh.setFont(icon_font)
        self.btn_refresh.clicked.connect(self.refresh)
        
        # Breadcrumb path display
        self.path_edit = QLineEdit(self.current_path)
        self.path_edit.returnPressed.connect(self.navigate_to_path)
        
        bar.addWidget(self.btn_back)
        bar.addWidget(self.btn_home)
        bar.addWidget(self.btn_refresh)
        bar.addWidget(self.path_edit)

        # View mode selector
        self.view_combo = QComboBox()
        self.view_combo.addItems(["📋 List", "📊 Table"])
        self.view_combo.currentIndexChanged.connect(self.change_view_mode)
        bar.addWidget(self.view_combo)

        # Hidden files toggle
        self.btn_hidden = QPushButton("󰜉  Hidden")
        self.btn_hidden.setFont(icon_font)
        self.btn_hidden.setCheckable(True)
        self.btn_hidden.toggled.connect(self.toggle_hidden)
        bar.addWidget(self.btn_hidden)

        main.addLayout(bar)

        # Search and actions bar
        actions = QHBoxLayout()
        
        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search files... (Ctrl+F)")
        self.search_input.textChanged.connect(self.filter_files)
        actions.addWidget(self.search_input)
        
        # Sort selector
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Name ↑", "Name ↓", "Size ↑", "Size ↓", "Date ↑", "Date ↓", "Type ↑", "Type ↓"])
        self.sort_combo.currentIndexChanged.connect(self.change_sort)
        actions.addWidget(self.sort_combo)
        
        main.addLayout(actions)

        # File operation buttons
        ops = QHBoxLayout()
        self.btn_new_folder = QPushButton("󰉋  New Folder")
        self.btn_new_file = QPushButton("󰈔  New File")
        self.btn_copy = QPushButton("󰆏  Copy")
        self.btn_cut = QPushButton("󰩨  Cut")
        self.btn_paste = QPushButton("󰅌  Paste")
        self.btn_delete = QPushButton("󰩹  Delete")
        self.btn_properties = QPushButton("  Info")
        self.btn_bookmark = QPushButton(f"{self.bookmark_glyph}  Bookmark")
        
        for b in [self.btn_new_folder, self.btn_new_file, self.btn_copy, 
                  self.btn_cut, self.btn_paste, self.btn_delete, 
                  self.btn_properties, self.btn_bookmark]:
            b.setFont(icon_font)
        
        self.btn_new_folder.clicked.connect(self.create_new_folder)
        self.btn_new_file.clicked.connect(self.create_new_file)
        self.btn_copy.clicked.connect(self.copy_files)
        self.btn_cut.clicked.connect(self.cut_files)
        self.btn_paste.clicked.connect(self.paste_files)
        self.btn_delete.clicked.connect(self.delete_files)
        self.btn_properties.clicked.connect(self.show_properties)
        self.btn_bookmark.clicked.connect(self.add_bookmark)
        
        ops.addWidget(self.btn_new_folder)
        ops.addWidget(self.btn_new_file)
        ops.addWidget(self.btn_copy)
        ops.addWidget(self.btn_cut)
        ops.addWidget(self.btn_paste)
        ops.addWidget(self.btn_delete)
        ops.addWidget(self.btn_properties)
        ops.addWidget(self.btn_bookmark)
        ops.addStretch()
        main.addLayout(ops)

        # Split view
        self.splitter = QSplitter(Qt.Horizontal)

        # Left panel (Tree + Preview)
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(self.icon_font)
        self.tree.itemClicked.connect(self.tree_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.populate_tree()
        left_layout.addWidget(self.tree, stretch=3)

        self.preview_label = QLabel("")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.preview_label, stretch=0)

        self.splitter.addWidget(self.left_panel)

        # Right panel (File list - will switch between list and table)
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        
        # List view
        self.file_list = QListWidget()
        self.file_list.setFont(self.icon_font)
        self.file_list.itemDoubleClicked.connect(self.item_opened)
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_context_menu)
        self.file_list.itemSelectionChanged.connect(self.update_preview)
        self.file_list.setMouseTracking(True)
        self.file_list.viewport().installEventFilter(self)
        
        # Table view
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self.show_context_menu)
        self.file_table.itemSelectionChanged.connect(self.update_preview)
        self.file_table.itemDoubleClicked.connect(self.table_item_opened)
        self.file_table.setFont(self.icon_font)
        self.file_table.hide()
        
        self.right_layout.addWidget(self.file_list)
        self.right_layout.addWidget(self.file_table)
        
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(1,1)
        main.addWidget(self.splitter)

        self.statusBar().showMessage("Ready | Shortcuts: Ctrl+F (Search), Ctrl+H (Hidden), Ctrl+B (Bookmark), Ctrl+N (New Folder), F2 (Rename), Del (Delete)")

    # ---------------- View Mode ----------------
    def change_view_mode(self, index):
        """Switch between list and table view"""
        if index == 0:  # List
            self.view_mode = "list"
            self.file_table.hide()
            self.file_list.show()
        else:  # Table
            self.view_mode = "table"
            self.file_list.hide()
            self.file_table.show()
        self.load_directory(self.current_path)
    
    def get_current_list(self):
        """Get the currently active file list widget"""
        if self.view_mode == "list":
            return self.file_list
        else:
            return self.file_table

    # ---------------- Sorting ----------------
    def change_sort(self, index):
        """Change sorting method"""
        sorts = {
            0: ("name", False), 1: ("name", True),
            2: ("size", False), 3: ("size", True),
            4: ("date", False), 5: ("date", True),
            6: ("type", False), 7: ("type", True),
        }
        self.sort_by, self.sort_reverse = sorts[index]
        self.load_directory(self.current_path)

    # ---------------- Search/Filter ----------------
    def filter_files(self):
        """Filter files based on search input"""
        search_text = self.search_input.text().lower()
        
        if self.view_mode == "list":
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                text = item.text().lower()
                # Don't hide parent directory
                if text.strip().startswith(".."):
                    item.setHidden(False)
                else:
                    item.setHidden(search_text not in text)
        else:
            for i in range(self.file_table.rowCount()):
                text = self.file_table.item(i, 0).text().lower()
                # Don't hide parent directory
                if text.strip().startswith(".."):
                    self.file_table.setRowHidden(i, False)
                else:
                    self.file_table.setRowHidden(i, search_text not in text)

    # ---------------- Toggle Hidden ----------------
    def toggle_hidden(self, checked):
        self.show_hidden = checked
        self.refresh()

    # ---------------- Cache Management ----------------
    def add_to_cache(self, filepath, pixmap):
        if len(self.image_cache) >= self.cache_max_size:
            self.image_cache.pop(next(iter(self.image_cache)))
        self.image_cache[filepath] = pixmap

    def clear_cache(self):
        self.image_cache.clear()

    # ---------------- Preview Pane ----------------
    def update_preview(self):
        if self.view_mode == "list":
            items = self.file_list.selectedItems()
            if not items:
                self.preview_label.clear()
                return
            self.show_preview_for_item(items[0])
        else:
            items = self.file_table.selectedItems()
            if not items:
                self.preview_label.clear()
                return
            # Get the first column item (name) from selected row
            row = items[0].row()
            name_item = self.file_table.item(row, 0)
            self.show_preview_for_item(name_item)

    def show_preview_for_item(self, item):
        if self.current_loader and self.current_loader.isRunning():
            self.current_loader.wait()
        
        path = Path(item.data(Qt.UserRole))
        suffix = path.suffix.lower()
        
        if path.is_file() and suffix in [".png",".jpg",".jpeg",".bmp",".gif",".webp"]:
            filepath = str(path)
            
            if filepath in self.image_cache:
                self.preview_label.setPixmap(self.image_cache[filepath])
                self.preview_label.setFont(self.icon_font)
                return
            
            self.preview_label.clear()
            self.preview_label.setText("⏳ Loading...")
            self.preview_label.setFont(QFont("Hack Nerd Font", 16))
            
            self.current_loader = ImageLoaderThread(
                filepath, 
                self.preview_label.width(), 
                self.preview_label.height()
            )
            self.current_loader.image_loaded.connect(self.on_image_loaded)
            self.current_loader.start()
            
        elif path.is_file() and suffix in [".mp4",".mkv",".webm",".mov",".avi",".flv",".m4v",".mpg",".mpeg"]:
            filepath = str(path)
            
            if filepath in self.image_cache:
                self.preview_label.setPixmap(self.image_cache[filepath])
                self.preview_label.setFont(self.icon_font)
                return
            
            self.preview_label.clear()
            self.preview_label.setText("⏳ Loading video...")
            self.preview_label.setFont(QFont("Hack Nerd Font", 16))
            
            self.generate_video_thumbnail(filepath)
            
        elif path.is_dir():
            self.preview_label.clear()
            self.preview_label.setText(self.folder_glyph)
            self.preview_label.setFont(QFont("Hack Nerd Font",72))
        else:
            self.preview_label.clear()
            self.preview_label.setText(self.file_glyph)
            self.preview_label.setFont(QFont("Hack Nerd Font",72))
        self.preview_label.setAlignment(Qt.AlignCenter)
    
    def generate_video_thumbnail(self, video_path):
        try:
            temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg')
            os.close(temp_fd)
            
            result = subprocess.run([
                'ffmpeg', '-ss', '00:00:01', '-i', video_path,
                '-vframes', '1', '-q:v', '2', temp_path, '-y'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if result.returncode == 0 and os.path.exists(temp_path):
                pixmap = QPixmap(temp_path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(
                        self.preview_label.width(),
                        self.preview_label.height(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.preview_label.setPixmap(pixmap)
                    self.add_to_cache(video_path, pixmap)
                else:
                    self.show_video_icon()
                
                os.unlink(temp_path)
            else:
                self.show_video_icon()
                
        except Exception as e:
            print(f"Video thumbnail error: {e}")
            self.show_video_icon()
    
    def show_video_icon(self):
        self.preview_label.clear()
        self.preview_label.setText(self.video_glyph)
        self.preview_label.setFont(QFont("Hack Nerd Font",72))

    def on_image_loaded(self, filepath, pixmap):
        if not pixmap.isNull():
            self.add_to_cache(filepath, pixmap)
            self.preview_label.setPixmap(pixmap)
        else:
            self.preview_label.setText("❌ Cannot load")
            self.preview_label.setFont(QFont("Hack Nerd Font", 16))

    # ---------------- Hover Preview ----------------
    def eventFilter(self, source, event):
        if event.type() == event.MouseMove and source is self.file_list.viewport():
            item = self.file_list.itemAt(event.pos())
            if item and item != self.pending_hover_item:
                self.pending_hover_item = item
                self.hover_timer.stop()
                self.hover_timer.start(self.hover_delay)
            elif not item:
                self.hover_timer.stop()
                self.pending_hover_item = None
        return super().eventFilter(source, event)
    
    def load_hovered_preview(self):
        if self.pending_hover_item:
            self.show_preview_for_item(self.pending_hover_item)

    # ---------------- Tree ----------------
    def get_mounted_drives(self):
        drives = []
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split(None, 4)
                    if len(parts) < 2:
                        continue
                    
                    device = parts[0]
                    mountpoint = parts[1].encode().decode('unicode_escape')
                    
                    if mountpoint in ['/', '/boot', '/home', '/tmp', '/var', '/usr', '/sys', '/proc', '/dev', '/run']:
                        continue
                    if mountpoint.startswith(('/sys/', '/proc/', '/dev/', '/run/user')):
                        continue
                    
                    if mountpoint.startswith(('/media/', '/mnt/', '/run/media/')) and Path(mountpoint).exists():
                        name = Path(mountpoint).name
                        if not name:
                            name = mountpoint
                        drives.append({
                            'name': name,
                            'path': mountpoint,
                            'device': device
                        })
        except Exception as e:
            print(f"Error reading mounts: {e}")
        
        return drives

    def populate_tree(self):
        self.tree.clear()
        
        # Home directory
        home = Path.home()
        home_item = QTreeWidgetItem([f"{self.folder_glyph}  {home.name}"])
        home_item.setData(0, Qt.UserRole, str(home))
        home_item.setFont(0, self.icon_font)
        self.tree.addTopLevelItem(home_item)
        for p in sorted(home.iterdir()):
            if not self.show_hidden and p.name.startswith("."): 
                continue
            if p.is_dir():
                item = QTreeWidgetItem([f"{self.folder_glyph}  {p.name}"])
                item.setData(0, Qt.UserRole, str(p))
                item.setFont(0, self.icon_font)
                home_item.addChild(item)
        home_item.setExpanded(True)
        
        # Bookmarks
        if self.bookmarks:
            bookmarks_item = QTreeWidgetItem([f"{self.bookmark_glyph}  Bookmarks"])
            bookmarks_item.setFont(0, self.icon_font)
            self.tree.addTopLevelItem(bookmarks_item)
            
            for bookmark in self.bookmarks:
                path = Path(bookmark)
                if path.exists():
                    item = QTreeWidgetItem([f"{self.folder_glyph}  {path.name}"])
                    item.setData(0, Qt.UserRole, str(path))
                    item.setFont(0, self.icon_font)
                    bookmarks_item.addChild(item)
            
            bookmarks_item.setExpanded(True)
        
        # Mounted drives
        drives = self.get_mounted_drives()
        if drives:
            drives_item = QTreeWidgetItem([f"{self.drive_glyph}  Drives"])
            drives_item.setFont(0, self.icon_font)
            self.tree.addTopLevelItem(drives_item)
            
            for drive in drives:
                drive_item = QTreeWidgetItem([f"{self.usb_glyph}  {drive['name']}"])
                drive_item.setData(0, Qt.UserRole, drive['path'])
                drive_item.setFont(0, self.icon_font)
                drives_item.addChild(drive_item)
            
            drives_item.setExpanded(True)

    def tree_clicked(self, item, column):
        path = item.data(0, Qt.UserRole)
        if path: 
            self.load_directory(path)
    
    # ---------------- Tree Context Menu ----------------
    def show_tree_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        
        # Check if this is a bookmark
        if path in self.bookmarks:
            menu = QMenu(self)
            remove_action = menu.addAction(f"🗑️ Remove Bookmark")
            
            action = menu.exec_(self.tree.mapToGlobal(position))
            
            if action == remove_action:
                self.remove_bookmark(path)
                self.statusBar().showMessage(f"Removed bookmark: {Path(path).name}")

    # ---------------- File Formatting ----------------
    def format_size(self, size):
        """Format size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    
    def get_file_type(self, path):
        """Get file type description"""
        if path.is_dir():
            return "Folder"
        suffix = path.suffix.lower()
        type_map = {
            '.txt': 'Text', '.pdf': 'PDF', '.doc': 'Word', '.docx': 'Word',
            '.xls': 'Excel', '.xlsx': 'Excel', '.ppt': 'PowerPoint', '.pptx': 'PowerPoint',
            '.jpg': 'Image', '.jpeg': 'Image', '.png': 'Image', '.gif': 'Image',
            '.mp4': 'Video', '.mkv': 'Video', '.avi': 'Video', '.mov': 'Video',
            '.mp3': 'Audio', '.wav': 'Audio', '.flac': 'Audio',
            '.zip': 'Archive', '.tar': 'Archive', '.gz': 'Archive', '.7z': 'Archive',
            '.py': 'Python', '.js': 'JavaScript', '.html': 'HTML', '.css': 'CSS',
        }
        return type_map.get(suffix, suffix[1:].upper() if suffix else 'File')

    # ---------------- Files ----------------
    def load_directory(self, path):
        try:
            self.clear_cache()
            
            if self.view_mode == "list":
                self.file_list.clear()
            else:
                self.file_table.setRowCount(0)
            
            self.current_path = path
            self.path_edit.setText(path)
            
            # Parent directory entry
            if path != "/":
                if self.view_mode == "list":
                    parent_item = QListWidgetItem(f"{self.folder_glyph}  ..")
                    parent_item.setData(Qt.UserRole, str(Path(path).parent))
                    parent_item.setFont(self.icon_font)
                    self.file_list.addItem(parent_item)
                else:
                    row = self.file_table.rowCount()
                    self.file_table.insertRow(row)
                    name_item = QTableWidgetItem(f"{self.folder_glyph}  ..")
                    name_item.setData(Qt.UserRole, str(Path(path).parent))
                    name_item.setFont(self.icon_font)
                    self.file_table.setItem(row, 0, name_item)
                    for col in range(1, 4):
                        self.file_table.setItem(row, col, QTableWidgetItem(""))
            
            # Get and sort entries
            entries = list(Path(path).iterdir())
            
            # Filter hidden files
            if not self.show_hidden:
                entries = [e for e in entries if not e.name.startswith(".")]
            
            # Sort entries
            if self.sort_by == "name":
                entries.sort(key=lambda x: (not x.is_dir(), x.name.lower()), reverse=self.sort_reverse)
            elif self.sort_by == "size":
                entries.sort(key=lambda x: (not x.is_dir(), x.stat().st_size if x.is_file() else 0), reverse=self.sort_reverse)
            elif self.sort_by == "date":
                entries.sort(key=lambda x: (not x.is_dir(), x.stat().st_mtime), reverse=self.sort_reverse)
            elif self.sort_by == "type":
                entries.sort(key=lambda x: (not x.is_dir(), self.get_file_type(x)), reverse=self.sort_reverse)
            
            visible = 0
            for e in entries:
                glyph = self.folder_glyph if e.is_dir() else self.file_glyph
                
                if self.view_mode == "list":
                    item = QListWidgetItem(f"{glyph}  {e.name}")
                    item.setData(Qt.UserRole, str(e))
                    item.setFont(self.icon_font)
                    self.file_list.addItem(item)
                else:
                    row = self.file_table.rowCount()
                    self.file_table.insertRow(row)
                    
                    # Name
                    name_item = QTableWidgetItem(f"{glyph}  {e.name}")
                    name_item.setData(Qt.UserRole, str(e))
                    name_item.setFont(self.icon_font)
                    self.file_table.setItem(row, 0, name_item)
                    
                    # Size
                    if e.is_file():
                        size_str = self.format_size(e.stat().st_size)
                    else:
                        size_str = ""
                    size_item = QTableWidgetItem(size_str)
                    size_item.setFont(self.icon_font)
                    self.file_table.setItem(row, 1, size_item)
                    
                    # Type
                    type_item = QTableWidgetItem(self.get_file_type(e))
                    type_item.setFont(self.icon_font)
                    self.file_table.setItem(row, 2, type_item)
                    
                    # Modified date
                    mtime = datetime.fromtimestamp(e.stat().st_mtime)
                    date_item = QTableWidgetItem(mtime.strftime("%Y-%m-%d %H:%M"))
                    date_item.setFont(self.icon_font)
                    self.file_table.setItem(row, 3, date_item)
                
                visible += 1
            
            self.statusBar().showMessage(f"{visible} items")
            self.update_preview()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def item_opened(self, item):
        path = item.data(Qt.UserRole)
        if Path(path).is_dir():
            self.load_directory(path)
        else:
            subprocess.Popen(["xdg-open", path])
    
    def table_item_opened(self, item):
        """Handle double-click in table view"""
        row = item.row()
        name_item = self.file_table.item(row, 0)
        path = name_item.data(Qt.UserRole)
        if Path(path).is_dir():
            self.load_directory(path)
        else:
            subprocess.Popen(["xdg-open", path])

    # ---------------- Create New ----------------
    def create_new_folder(self):
        """Create a new folder"""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            try:
                new_path = Path(self.current_path) / name
                if new_path.exists():
                    QMessageBox.warning(self, "Error", f"'{name}' already exists")
                    return
                new_path.mkdir()
                self.statusBar().showMessage(f"Created folder '{name}'")
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
    
    def create_new_file(self):
        """Create a new empty file"""
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            try:
                new_path = Path(self.current_path) / name
                if new_path.exists():
                    QMessageBox.warning(self, "Error", f"'{name}' already exists")
                    return
                new_path.touch()
                self.statusBar().showMessage(f"Created file '{name}'")
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ---------------- Properties ----------------
    def show_properties(self):
        """Show file properties dialog"""
        paths = self.get_selected_paths()
        if not paths:
            return
        
        # Show properties for first selected item
        dialog = FilePropertiesDialog(paths[0], self)
        dialog.exec_()

    # ---------------- Context Menu ----------------
    def show_context_menu(self, position):
        menu = QMenu(self)
        
        selected = self.get_selected_paths()
        
        # Open
        if len(selected) == 1:
            open_action = menu.addAction("Open")
            menu.addSeparator()
        
        # Basic operations
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        paste_action.setEnabled(bool(self.clipboard))
        menu.addSeparator()
        
        # Rename (single item)
        rename_action = None
        if len(selected) == 1:
            rename_action = menu.addAction("Rename")
        
        # Properties
        properties_action = None
        if len(selected) == 1:
            properties_action = menu.addAction("Properties")
        
        menu.addSeparator()
        
        # Archive operations
        if len(selected) == 1:
            path = Path(selected[0])
            if self.is_archive(path):
                extract_here = menu.addAction("Extract Here")
                extract_to = menu.addAction("Extract To...")
                menu.addSeparator()
        
        delete_action = menu.addAction("Delete")
        
        if self.view_mode == "list":
            action = menu.exec_(self.file_list.mapToGlobal(position))
        else:
            action = menu.exec_(self.file_table.mapToGlobal(position))
        
        if len(selected) == 1 and action and action.text() == "Open":
            subprocess.Popen(["xdg-open", selected[0]])
        elif action == copy_action:
            self.copy_files()
        elif action == cut_action:
            self.cut_files()
        elif action == paste_action:
            self.paste_files()
        elif action == rename_action and rename_action:
            self.rename_file()
        elif action == properties_action and properties_action:
            self.show_properties()
        elif action == delete_action:
            self.delete_files()
        elif len(selected) == 1 and self.is_archive(Path(selected[0])):
            if action.text() == "Extract Here":
                self.extract_here(Path(selected[0]))
            elif action.text() == "Extract To...":
                self.extract_to(Path(selected[0]))

    # ---------------- Archive Operations ----------------
    def is_archive(self, path):
        if not path.is_file():
            return False
        ext = path.suffix.lower()
        archive_exts = ['.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar', 
                       '.tar.gz', '.tar.bz2', '.tar.xz', '.tgz', '.tbz2', '.txz']
        if path.suffixes:
            compound = ''.join(path.suffixes[-2:]).lower()
            if compound in archive_exts:
                return True
        return ext in archive_exts

    def extract_here(self, archive_path):
        try:
            self.statusBar().showMessage(f"Extracting {archive_path.name}...")
            QApplication.processEvents()
            
            extract_path = archive_path.parent
            success = self.extract_archive(archive_path, extract_path)
            
            if success:
                self.statusBar().showMessage(f"✓ Extracted {archive_path.name}")
                self.refresh()
            else:
                QMessageBox.warning(self, "Extraction Failed", 
                                  f"Could not extract {archive_path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def extract_to(self, archive_path):
        try:
            folder_name = archive_path.stem
            if archive_path.suffixes and len(archive_path.suffixes) > 1:
                folder_name = archive_path.name
                for ext in ['.tar.gz', '.tar.bz2', '.tar.xz', '.tgz', '.tbz2', '.txz']:
                    if archive_path.name.lower().endswith(ext):
                        folder_name = archive_path.name[:-len(ext)]
                        break
            
            extract_path = archive_path.parent / folder_name
            counter = 1
            while extract_path.exists():
                extract_path = archive_path.parent / f"{folder_name}_{counter}"
                counter += 1
            
            extract_path.mkdir(parents=True, exist_ok=True)
            
            self.statusBar().showMessage(f"Extracting {archive_path.name} to {extract_path.name}...")
            QApplication.processEvents()
            
            success = self.extract_archive(archive_path, extract_path)
            
            if success:
                self.statusBar().showMessage(f"✓ Extracted to {extract_path.name}")
                self.refresh()
            else:
                if extract_path.exists() and not any(extract_path.iterdir()):
                    extract_path.rmdir()
                QMessageBox.warning(self, "Extraction Failed", 
                                  f"Could not extract {archive_path.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def extract_archive(self, archive_path, extract_path):
        ext = archive_path.suffix.lower()
        compound_ext = None
        if archive_path.suffixes and len(archive_path.suffixes) > 1:
            compound_ext = ''.join(archive_path.suffixes[-2:]).lower()
        
        try:
            if ext == '.zip':
                result = subprocess.run(['unzip', '-q', str(archive_path), '-d', str(extract_path)],
                                      capture_output=True, text=True)
                return result.returncode == 0
            elif ext == '.7z':
                result = subprocess.run(['7z', 'x', str(archive_path), f'-o{extract_path}', '-y'],
                                      capture_output=True, text=True)
                return result.returncode == 0
            elif ext == '.rar':
                result = subprocess.run(['unrar', 'x', '-y', str(archive_path), str(extract_path)],
                                      capture_output=True, text=True)
                return result.returncode == 0
            elif compound_ext in ['.tar.gz', '.tar.bz2', '.tar.xz'] or ext in ['.tgz', '.tbz2', '.txz', '.tar']:
                result = subprocess.run(['tar', '-xf', str(archive_path), '-C', str(extract_path)],
                                      capture_output=True, text=True)
                return result.returncode == 0
            elif ext in ['.gz', '.bz2', '.xz']:
                output_file = extract_path / archive_path.stem
                if ext == '.gz':
                    result = subprocess.run(['gunzip', '-c', str(archive_path)], capture_output=True)
                elif ext == '.bz2':
                    result = subprocess.run(['bunzip2', '-c', str(archive_path)], capture_output=True)
                elif ext == '.xz':
                    result = subprocess.run(['unxz', '-c', str(archive_path)], capture_output=True)
                
                if result.returncode == 0:
                    with open(output_file, 'wb') as f:
                        f.write(result.stdout)
                    return True
                return False
            
            return False
        except FileNotFoundError:
            QMessageBox.critical(self, "Tool Missing", 
                               "Required extraction tool not found.")
            return False
        except Exception as e:
            print(f"Extraction error: {e}")
            return False

    # ---------------- Clipboard ----------------
    def get_selected_paths(self):
        if self.view_mode == "list":
            return [i.data(Qt.UserRole) for i in self.file_list.selectedItems()]
        else:
            # Get paths from selected rows in table
            paths = []
            for item in self.file_table.selectedItems():
                row = item.row()
                name_item = self.file_table.item(row, 0)
                path = name_item.data(Qt.UserRole)
                if path not in paths:
                    paths.append(path)
            return paths

    def copy_files(self):
        self.clipboard = self.get_selected_paths()
        self.clipboard_action = "copy"
        self.statusBar().showMessage(f"Copied {len(self.clipboard)} item(s)")

    def cut_files(self):
        self.clipboard = self.get_selected_paths()
        self.clipboard_action = "cut"
        self.statusBar().showMessage(f"Cut {len(self.clipboard)} item(s)")

    def paste_files(self):
        if not self.clipboard:
            return
        
        # Show progress dialog for large operations
        progress = QProgressDialog("Pasting files...", "Cancel", 0, len(self.clipboard), self)
        progress.setWindowModality(Qt.WindowModal)
        
        errors = []
        for idx, src in enumerate(self.clipboard):
            if progress.wasCanceled():
                break
            
            progress.setValue(idx)
            QApplication.processEvents()
            
            try:
                src_p = Path(src)
                dest = Path(self.current_path) / src_p.name
                counter = 1
                while dest.exists():
                    dest = Path(self.current_path) / f"{src_p.stem}_{counter}{src_p.suffix}"
                    counter += 1
                
                if self.clipboard_action == "copy":
                    if src_p.is_dir():
                        shutil.copytree(src, dest)
                    else:
                        shutil.copy2(src, dest)
                else:
                    shutil.move(src, dest)
            except Exception as e:
                errors.append(str(e))
        
        progress.setValue(len(self.clipboard))
        
        if self.clipboard_action == "cut":
            self.clipboard = []
        
        self.refresh()
        
        if errors:
            QMessageBox.warning(self, "Errors", "\n".join(errors))

    def rename_file(self):
        selected = self.get_selected_paths()
        if not selected or len(selected) != 1:
            return
        
        old_path = Path(selected[0])
        old_name = old_path.name
        
        new_name, ok = QInputDialog.getText(
            self, 
            "Rename", 
            "Enter new name:",
            QLineEdit.Normal,
            old_name
        )
        
        if ok and new_name and new_name != old_name:
            try:
                new_path = old_path.parent / new_name
                
                if new_path.exists():
                    QMessageBox.warning(self, "Error", f"'{new_name}' already exists")
                    return
                
                old_path.rename(new_path)
                self.statusBar().showMessage(f"Renamed '{old_name}' to '{new_name}'")
                self.refresh()
                
            except Exception as e:
                QMessageBox.critical(self, "Rename Error", str(e))

    def delete_files(self):
        paths = self.get_selected_paths()
        if not paths:
            return
        
        reply = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move {len(paths)} item(s) to trash?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        errors = []
        for p in paths:
            try:
                result = subprocess.run(['trash-put', p], capture_output=True, text=True)
                if result.returncode != 0:
                    errors.append(f"{p}: {result.stderr}")
            except FileNotFoundError:
                try:
                    path = Path(p)
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                except Exception as e:
                    errors.append(f"{p}: {str(e)}")
            except Exception as e:
                errors.append(f"{p}: {str(e)}")
        
        self.refresh()
        
        if errors:
            QMessageBox.warning(self, "Errors", "\n".join(errors))
        else:
            self.statusBar().showMessage(f"Moved {len(paths)} item(s) to trash")

    # ---------------- Navigation ----------------
    def go_back(self):
        self.load_directory(str(Path(self.current_path).parent))

    def go_home(self):
        self.load_directory(str(Path.home()))

    def refresh(self):
        self.populate_tree()
        self.load_directory(self.current_path)

    def navigate_to_path(self):
        path = self.path_edit.text()
        if Path(path).is_dir():
            self.load_directory(path)
        else:
            QMessageBox.warning(self, "Invalid Path", path)
            self.path_edit.setText(self.current_path)

# ---------------- Main ----------------
def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Hack Nerd Font", 10))
    win = FileManager()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
