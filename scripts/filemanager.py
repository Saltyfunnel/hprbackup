#!/usr/bin/env python3
"""
PyQt5 File Manager — Nautilus-style layout with pywal theming
"""

import sys, json, shutil, subprocess, tempfile, os, zipfile, tarfile
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QLineEdit,
    QMessageBox, QSplitter, QMenu, QTreeWidgetItem, QTreeWidget,
    QSizePolicy, QStyleFactory, QInputDialog, QDialog, QFormLayout,
    QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QShortcut, QAbstractItemView, QDialogButtonBox,
    QScrollArea, QGridLayout, QFrame, QAction, QToolBar, QStatusBar
)
from PyQt5.QtCore import (Qt, QFileSystemWatcher, QThread, pyqtSignal, QTimer,
                           QMimeData, QUrl, QPoint, QSize)
from PyQt5.QtGui import (QFont, QColor, QPalette, QPixmap, QImage,
                         QKeySequence, QDrag, QCursor, QIcon, QPainter,
                         QFontDatabase)


# ── Image / Thumbnail Loader ──────────────────────────────────────────────────
class WrapLabel(QLabel):
    """QLabel that breaks filenames at any character boundary."""
    def __init__(self, text, parent=None):
        # Insert zero-width spaces before each char so Qt wraps anywhere
        super().__init__(text, parent)
        self.setWordWrap(True)
        self._raw = text

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Re-insert zero-width spaces based on how many chars fit per line
        fm = self.fontMetrics()
        w  = self.width() or 1
        chars_per_line = max(1, w // max(1, fm.averageCharWidth()))
        chunks = [self._raw[i:i+chars_per_line] for i in range(0, len(self._raw), chars_per_line)]
        self.setText('\n'.join(chunks))


class ThumbnailLoader(QThread):
    loaded = pyqtSignal(str, QPixmap)

    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.ico'}
    VIDEO_EXTS = {'.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv', '.m4v', '.mpg', '.mpeg'}

    def __init__(self, path, size):
        super().__init__()
        self.path = path
        self.size = size

    def run(self):
        p = Path(self.path)
        ext = p.suffix.lower()
        try:
            if ext in self.IMAGE_EXTS:
                img = QImage(self.path)
                if not img.isNull():
                    scaled = img.scaled(self.size, self.size,
                                        Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.loaded.emit(self.path, QPixmap.fromImage(scaled))
            elif ext in self.VIDEO_EXTS:
                fd, tmp = tempfile.mkstemp(suffix='.jpg')
                os.close(fd)
                r = subprocess.run(
                    ['ffmpeg', '-ss', '00:00:01', '-i', self.path,
                     '-vframes', '1', '-q:v', '2', tmp, '-y'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if r.returncode == 0:
                    img = QImage(tmp)
                    if not img.isNull():
                        scaled = img.scaled(self.size, self.size,
                                            Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.loaded.emit(self.path, QPixmap.fromImage(scaled))
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        except Exception as e:
            print(f"Thumb error {self.path}: {e}")


# ── Drag & Drop Grid ──────────────────────────────────────────────────────────
class GridCell(QFrame):
    """Single icon cell in the grid view."""
    activated    = pyqtSignal(str)
    ctx_requested = pyqtSignal(str, QPoint)

    THUMB_EXTS = ThumbnailLoader.IMAGE_EXTS | ThumbnailLoader.VIDEO_EXTS

    def __init__(self, path, icon_size, folder_glyph, file_glyph, accent, fg, bg_sel, parent=None):
        super().__init__(parent)
        self.path = path
        self._selected = False
        self._accent = accent
        self._fg = fg
        self._bg_sel = bg_sel

        p = Path(path)
        self.setFixedSize(icon_size + 24, icon_size + 44)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._update_style(False)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 6, 4, 4)
        vbox.setSpacing(4)
        vbox.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(icon_size, icon_size)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        if p.is_dir():
            self.icon_label.setText(folder_glyph)
            self.icon_label.setFont(QFont("Hack Nerd Font", icon_size // 2))
        elif p.suffix.lower() in self.THUMB_EXTS:
            self.icon_label.setText("⏳")
            self.icon_label.setFont(QFont("Hack Nerd Font", 16))
        else:
            self.icon_label.setText(file_glyph)
            self.icon_label.setFont(QFont("Hack Nerd Font", icon_size // 2))

        name = p.name
        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumWidth(icon_size + 16)
        self.name_label.setFont(QFont("Hack Nerd Font", 9))
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        vbox.addWidget(self.icon_label, alignment=Qt.AlignHCenter)
        vbox.addWidget(self.name_label, alignment=Qt.AlignHCenter)

    def set_thumbnail(self, pixmap):
        self.icon_label.setPixmap(pixmap)
        self.icon_label.setFont(QFont())

    def set_selected(self, val):
        self._selected = val
        self._update_style(val)

    def _update_style(self, selected):
        if selected:
            self.setStyleSheet(f"""
                GridCell {{
                    background: {self._bg_sel};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet("""
                GridCell { background: transparent; border-radius: 8px; }
                GridCell:hover { background: rgba(255,255,255,0.06); }
            """)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.activated.emit(self.path)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.activated.emit(self.path)

    def contextMenuEvent(self, e):
        self.ctx_requested.emit(self.path, e.globalPos())


class GridView(QScrollArea):
    """Full grid view with thumbnail loading and selection."""
    item_activated    = pyqtSignal(str)
    selection_changed = pyqtSignal(list)
    ctx_requested     = pyqtSignal(list, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon_size     = 80
        self.folder_glyph  = "\uf07b"
        self.file_glyph    = "\uf15b"
        self.accent        = "#89b4fa"
        self.fg            = "#cdd6f4"
        self.bg_sel        = "rgba(137,180,250,0.25)"

        self._cells        = []          # list of GridCell
        self._selected     = set()       # selected paths
        self._loaders      = []
        self._thumb_cache  = {}          # path → QPixmap
        self._last_clicked = None

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._grid      = QGridLayout(self._container)
        self._grid.setSpacing(4)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self.setWidget(self._container)

    def update_colors(self, accent, fg):
        self.accent = accent
        self.fg     = fg
        r = QColor(accent)
        self.bg_sel = f"rgba({r.red()},{r.green()},{r.blue()},55)"

    def populate(self, entries):
        # Stop old loaders
        for ldr in self._loaders:
            ldr.terminate()
        self._loaders.clear()

        # Clear grid
        while self._grid.count():
            w = self._grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._cells.clear()
        self._selected.clear()

        cell_w = self.icon_size + 16
        cols = max(1, (self.viewport().width() or 900) // cell_w)

        for idx, path in enumerate(entries):
            cell = GridCell(
                path, self.icon_size,
                self.folder_glyph, self.file_glyph,
                self.accent, self.fg, self.bg_sel
            )
            cell.activated.connect(self._on_activate)
            cell.ctx_requested.connect(self._on_ctx)

            # Restore cached thumb
            if path in self._thumb_cache:
                cell.set_thumbnail(self._thumb_cache[path])
            elif Path(path).suffix.lower() in ThumbnailLoader.IMAGE_EXTS | ThumbnailLoader.VIDEO_EXTS:
                ldr = ThumbnailLoader(path, self.icon_size)
                ldr.loaded.connect(self._on_thumb)
                ldr.start()
                self._loaders.append(ldr)

            self._grid.addWidget(cell, idx // cols, idx % cols)
            self._cells.append(cell)

        self._grid.setRowStretch(self._grid.rowCount(), 1)

    def _on_thumb(self, path, px):
        self._thumb_cache[path] = px
        for cell in self._cells:
            if cell.path == path:
                cell.set_thumbnail(px)
                break

    def _on_activate(self, path):
        # Single click = select, double click = open handled in GridCell
        # We distinguish via the signal name — but GridCell sends activated on single too.
        # We'll use a timer trick: single click selects, double opens.
        # Actually GridCell sends activated on BOTH — we handle open at panel level via
        # item_activated only on double click. Re-wire: rename single→select, double→open.
        # For simplicity: single click selects, item_activated only fires on double.
        self._select_path(path)

    def _open_path(self, path):
        self.item_activated.emit(path)

    def _on_ctx(self, path, pos):
        if path not in self._selected:
            self._select_path(path, clear=True)
        self.ctx_requested.emit(list(self._selected), pos)

    def _select_path(self, path, clear=True):
        if clear:
            for c in self._cells:
                c.set_selected(False)
            self._selected.clear()
        if path in self._selected:
            for c in self._cells:
                if c.path == path:
                    c.set_selected(False)
            self._selected.discard(path)
        else:
            self._selected.add(path)
            for c in self._cells:
                if c.path == path:
                    c.set_selected(True)
        self._last_clicked = path
        self.selection_changed.emit(list(self._selected))

    def get_selected(self):
        return list(self._selected)

    def select_all(self):
        self._selected = {c.path for c in self._cells if c.path}
        for c in self._cells:
            c.set_selected(True)
        self.selection_changed.emit(list(self._selected))

    def mouseDoubleClickEvent(self, e):
        # handled at GridCell level
        pass


# ── Re-wire GridCell: single=select, double=open ──────────────────────────────
# Override GridCell to emit two distinct signals
class GridCell(QFrame):
    single_clicked = pyqtSignal(str)
    double_clicked = pyqtSignal(str)
    ctx_requested  = pyqtSignal(str, QPoint)

    THUMB_EXTS = ThumbnailLoader.IMAGE_EXTS | ThumbnailLoader.VIDEO_EXTS

    def __init__(self, path, icon_size, folder_glyph, file_glyph, accent, fg, bg_sel, parent=None):
        super().__init__(parent)
        self.path        = path
        self._selected   = False
        self._bg_sel     = bg_sel
        self._drag_start = QPoint()

        p = Path(path)
        self.setFixedSize(icon_size + 16, icon_size + 36)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._update_style(False)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(2)
        vbox.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(icon_size, icon_size)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        if p.is_dir():
            self.icon_label.setText(folder_glyph)
            self.icon_label.setFont(QFont("Hack Nerd Font", icon_size // 2))
            self.icon_label.setStyleSheet(f"color: {accent};")
        elif p.suffix.lower() in self.THUMB_EXTS:
            self.icon_label.setText("⏳")
            self.icon_label.setFont(QFont("Hack Nerd Font", 14))
        else:
            self.icon_label.setText(file_glyph)
            self.icon_label.setFont(QFont("Hack Nerd Font", icon_size // 2))
            self.icon_label.setStyleSheet(f"color: {fg};")

        self.name_label = WrapLabel(p.name)
        self.name_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumWidth(icon_size + 16)
        self.name_label.setFont(QFont("Hack Nerd Font", 9))
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        vbox.addWidget(self.icon_label, alignment=Qt.AlignHCenter)
        vbox.addWidget(self.name_label, alignment=Qt.AlignHCenter)

    def set_thumbnail(self, pixmap):
        self.icon_label.setPixmap(pixmap)

    def set_selected(self, val):
        self._selected = val
        self._update_style(val)

    def _update_style(self, selected):
        if selected:
            self.setStyleSheet(f"GridCell {{ background:{self._bg_sel}; border-radius:8px; }}")
        else:
            self.setStyleSheet("GridCell { background:transparent; border-radius:8px; }"
                               "GridCell:hover { background:rgba(255,255,255,0.05); }")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start = e.pos()
            self.single_clicked.emit(self.path)
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.double_clicked.emit(self.path)
        super().mouseDoubleClickEvent(e)

    def contextMenuEvent(self, e):
        self.ctx_requested.emit(self.path, e.globalPos())


# Patch GridView to use corrected GridCell signals
class GridView(QScrollArea):
    item_activated    = pyqtSignal(str)
    selection_changed = pyqtSignal(list)
    ctx_requested     = pyqtSignal(list, QPoint)
    files_dropped     = pyqtSignal(list, str)   # paths, action

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon_size    = 140
        self.folder_glyph = "\uf07b"
        self.file_glyph   = "\uf15b"
        self.accent       = "#89b4fa"
        self.fg           = "#cdd6f4"
        self.bg_sel       = "rgba(137,180,250,0.25)"

        self._cells       = []
        self._selected    = set()
        self._loaders     = []
        self._thumb_cache = {}
        self._entries     = []

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)

        self._container = QWidget()
        self._container.setAutoFillBackground(False)
        self._container.setAttribute(Qt.WA_TranslucentBackground)
        self._container.setAcceptDrops(True)
        self._grid      = QVBoxLayout(self._container)
        self._grid.setSpacing(4)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setWidget(self._container)

        # Force scroll area and viewport fully transparent
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.viewport().setAutoFillBackground(False)
        self.viewport().setAttribute(Qt.WA_TranslucentBackground)

        # Track drag at viewport level so scroll area doesn't swallow events
        self._drag_cell  = None
        self._drag_pos   = QPoint()
        self.viewport().installEventFilter(self)
        self._container.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self.viewport() or obj is self._container or isinstance(obj, GridCell):
            t = e.type()
            if t == e.DragEnter:
                if e.mimeData().hasUrls():
                    e.acceptProposedAction()
                    return True
            elif t == e.DragMove:
                if e.mimeData().hasUrls():
                    e.setDropAction(Qt.CopyAction if e.keyboardModifiers() & Qt.ControlModifier else Qt.MoveAction)
                    e.accept()
                    return True
            elif t == e.Drop:
                if e.mimeData().hasUrls():
                    paths  = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
                    action = 'copy' if e.keyboardModifiers() & Qt.ControlModifier else 'move'
                    # if dropped onto a folder cell, use that as dest
                    dest_cell = obj if isinstance(obj, GridCell) and Path(obj.path).is_dir() else None
                    if dest_cell and dest_cell.path not in paths:
                        self.files_dropped.emit(paths, f"{action}:{dest_cell.path}")
                    elif paths:
                        self.files_dropped.emit(paths, action)
                    e.acceptProposedAction()
                    return True
        if obj is self.viewport():
            t = e.type()
            if t == e.MouseButtonPress and e.button() == Qt.LeftButton:
                child = self._container.childAt(
                    self._container.mapFrom(self.viewport(), e.pos()))
                while child and not isinstance(child, GridCell):
                    child = child.parent() if hasattr(child, 'parent') else None
                if isinstance(child, GridCell):
                    self._drag_cell = child
                    self._drag_pos  = e.pos()
            elif t == e.MouseMove:
                if self._drag_cell:
                    if (e.pos() - self._drag_pos).manhattanLength() >= QApplication.startDragDistance():
                        cell  = self._drag_cell
                        self._drag_cell = None
                        paths = list(self._selected) if cell.path in self._selected else [cell.path]
                        drag  = QDrag(self)
                        mime  = QMimeData()
                        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
                        drag.setMimeData(mime)
                        drag.exec_(Qt.CopyAction | Qt.MoveAction)
                        return True
            elif t == e.MouseButtonRelease:
                self._drag_cell = None
        return super().eventFilter(obj, e)

    def update_colors(self, accent, fg):
        self.accent = accent
        self.fg     = fg
        r = QColor(accent)
        self.bg_sel = f"rgba({r.red()},{r.green()},{r.blue()},55)"

    def populate(self, entries):
        for ldr in self._loaders:
            ldr.terminate()
        self._loaders.clear()

        # Clear existing row widgets
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        self._cells.clear()
        self._selected.clear()
        self._entries = list(entries)

        for path in entries:
            r = QColor(self.accent)
            bg_sel = f"rgba({r.red()},{r.green()},{r.blue()},55)"
            cell = GridCell(
                path, self.icon_size,
                self.folder_glyph, self.file_glyph,
                self.accent, self.fg, bg_sel
            )
            cell.single_clicked.connect(self._on_single)
            cell.double_clicked.connect(self._on_double)
            cell.ctx_requested.connect(self._on_ctx)
            cell.setAcceptDrops(True)
            cell.installEventFilter(self)

            if path in self._thumb_cache:
                cell.set_thumbnail(self._thumb_cache[path])
            elif Path(path).suffix.lower() in (ThumbnailLoader.IMAGE_EXTS | ThumbnailLoader.VIDEO_EXTS):
                ldr = ThumbnailLoader(path, self.icon_size)
                ldr.loaded.connect(self._on_thumb)
                ldr.start()
                self._loaders.append(ldr)

            self._cells.append(cell)

        self._reflow()

    def _reflow(self):
        # Remove all row-wrapper widgets from the vbox
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                # detach cells before deleting the row wrapper
                for cell in self._cells:
                    if cell.parent() == w:
                        cell.setParent(None)
                w.deleteLater()

        cell_w = self.icon_size + 16
        cols   = max(1, (self.viewport().width() or 900) // cell_w)

        row_widget = None
        row_layout = None
        for idx, cell in enumerate(self._cells):
            if idx % cols == 0:
                row_widget = QWidget()
                row_widget.setAutoFillBackground(False)
                row_widget.setAttribute(Qt.WA_TranslucentBackground)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                row_layout.setAlignment(Qt.AlignLeft)
                self._grid.addWidget(row_widget)
            cell.setParent(row_widget)
            row_layout.addWidget(cell)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._cells:
            self._reflow()

    def _on_thumb(self, path, px):
        self._thumb_cache[path] = px
        for cell in self._cells:
            if cell.path == path:
                cell.set_thumbnail(px)

    def _on_single(self, path):
        mods = QApplication.keyboardModifiers()
        if mods & Qt.ControlModifier:
            # Ctrl+click: toggle individual item
            if path in self._selected:
                self._selected.discard(path)
                for c in self._cells:
                    if c.path == path: c.set_selected(False)
            else:
                self._selected.add(path)
                for c in self._cells:
                    if c.path == path: c.set_selected(True)
            self._last_clicked = path
        elif mods & Qt.ShiftModifier:
            # Shift+click: range from anchor to here
            paths = [c.path for c in self._cells]
            anchor = self._last_clicked if self._last_clicked in paths else (paths[0] if paths else None)
            if anchor:
                try:
                    a  = paths.index(anchor)
                    b  = paths.index(path)
                    lo, hi = min(a, b), max(a, b)
                    self._selected = set(paths[lo:hi+1])
                    for c in self._cells:
                        c.set_selected(c.path in self._selected)
                except ValueError:
                    pass
            # Don't update _last_clicked on shift — anchor stays fixed
        else:
            for c in self._cells:
                c.set_selected(c.path == path)
            self._selected = {path}
            self._last_clicked = path
        self.selection_changed.emit(list(self._selected))

    def _on_double(self, path):
        self.item_activated.emit(path)

    def _on_ctx(self, path, pos):
        if path not in self._selected:
            for c in self._cells:
                c.set_selected(c.path == path)
            self._selected = {path}
        self.ctx_requested.emit(list(self._selected), pos)

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(Qt.CopyAction if e.keyboardModifiers() & Qt.ControlModifier else Qt.MoveAction)
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            paths  = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            action = 'copy' if e.keyboardModifiers() & Qt.ControlModifier else 'move'
            if paths: self.files_dropped.emit(paths, action)
            e.acceptProposedAction()
        else:
            e.ignore()

    def get_selected(self):
        return list(self._selected)

    def select_all(self):
        self._selected = {c.path for c in self._cells}
        for c in self._cells: c.set_selected(True)
        self.selection_changed.emit(list(self._selected))

    def mousePressEvent(self, e):
        # Click on empty area → deselect; right-click → context menu
        if e.button() == Qt.LeftButton:
            if not self.childAt(e.pos()):
                for c in self._cells: c.set_selected(False)
                self._selected.clear()
                self.selection_changed.emit([])
        elif e.button() == Qt.RightButton:
            if not self.childAt(e.pos()):
                self.ctx_requested.emit([], e.globalPos())
        super().mousePressEvent(e)


# ── Drag & Drop List ──────────────────────────────────────────────────────────
class DragDropList(QListWidget):
    files_dropped = pyqtSignal(list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._drag_start = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag_start = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton) or self._drag_start is None: return
        if (e.pos() - self._drag_start).manhattanLength() < QApplication.startDragDistance(): return
        paths = [i.data(Qt.UserRole) for i in self.selectedItems() if i.data(Qt.UserRole)]
        if not paths: return
        drag = QDrag(self); mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag.setMimeData(mime); drag.exec_(Qt.CopyAction | Qt.MoveAction)

    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(Qt.CopyAction if e.keyboardModifiers() & Qt.ControlModifier else Qt.MoveAction); e.accept()
        else: e.ignore()

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if paths: self.files_dropped.emit(paths, 'copy' if e.keyboardModifiers() & Qt.ControlModifier else 'move')
            e.acceptProposedAction()
        else: e.ignore()


# ── Drag & Drop Table ─────────────────────────────────────────────────────────
class DragDropTable(QTableWidget):
    files_dropped = pyqtSignal(list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True); self.setAcceptDrops(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._drag_start = None; self._col_widths = {}

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag_start = e.pos()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton) or not self._drag_start: return
        if (e.pos() - self._drag_start).manhattanLength() < QApplication.startDragDistance(): return
        rows = set(i.row() for i in self.selectedItems())
        paths = [self.item(r,0).data(Qt.UserRole) for r in rows if self.item(r,0) and self.item(r,0).data(Qt.UserRole)]
        if not paths: return
        drag = QDrag(self); mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag.setMimeData(mime); drag.exec_(Qt.CopyAction | Qt.MoveAction)

    def dragEnterEvent(self, e): e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(Qt.CopyAction if e.keyboardModifiers() & Qt.ControlModifier else Qt.MoveAction); e.accept()
        else: e.ignore()
    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if paths: self.files_dropped.emit(paths, 'copy' if e.keyboardModifiers() & Qt.ControlModifier else 'move')
            e.acceptProposedAction()
        else: e.ignore()
    def save_col_widths(self): self._col_widths = {i: self.columnWidth(i) for i in range(self.columnCount())}
    def restore_col_widths(self):
        for i, w in self._col_widths.items():
            if w > 0: self.setColumnWidth(i, w)


# ── Dialogs ───────────────────────────────────────────────────────────────────
class OpenWithDialog(QDialog):
    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open With")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Open  {Path(filepath).name}  with:"))
        self.app_input = QLineEdit()
        self.app_input.setPlaceholderText("app name, e.g. gedit, vlc, gimp …")
        layout.addWidget(self.app_input)
        row = QHBoxLayout()
        for app in ["gedit", "vlc", "gimp", "code", "mpv"]:
            b = QPushButton(app); b.clicked.connect(lambda _, a=app: self.app_input.setText(a)); row.addWidget(b)
        layout.addLayout(row)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)
    def get_app(self): return self.app_input.text().strip()


class PropertiesDialog(QDialog):
    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        p = Path(filepath)
        self.setWindowTitle(f"Properties — {p.name}")
        self.setMinimumWidth(400)
        layout = QFormLayout(self)
        layout.addRow("Name:",        QLabel(p.name))
        layout.addRow("Location:",    QLabel(str(p.parent)))
        layout.addRow("Type:",        QLabel("Folder" if p.is_dir() else f"File ({p.suffix or 'none'})"))
        if p.is_file(): layout.addRow("Size:", QLabel(self._fmt(p.stat().st_size)))
        layout.addRow("Modified:",    QLabel(datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d  %H:%M:%S")))
        layout.addRow("Permissions:", QLabel(oct(p.stat().st_mode)[-3:]))
        layout.addRow("Full path:",   QLabel(str(p)))
        close = QPushButton("Close"); close.clicked.connect(self.accept); layout.addRow(close)
    def _fmt(self, size):
        for u in ['B','KB','MB','GB','TB']:
            if size < 1024.0: return f"{size:.2f} {u}"
            size /= 1024.0
        return f"{size:.2f} PB"


# ── Breadcrumb bar ────────────────────────────────────────────────────────────
class Breadcrumb(QWidget):
    navigate = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 0, 4, 0)
        self._layout.setSpacing(0)

    def set_path(self, path, accent):
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w: w.deleteLater()

        parts = Path(path).parts
        accumulated = ""
        for i, part in enumerate(parts):
            accumulated = str(Path(accumulated) / part) if accumulated else part
            acc = accumulated
            label = "\uf07c" if part == '/' else part
            btn = QPushButton(label)
            btn.setFont(QFont("Hack Nerd Font", 11))
            btn.setFlat(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {accent};
                    font-weight: 600;
                    padding: 0px 6px;
                    border: none;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background: rgba(255,255,255,0.08);
                }}
            """)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, p=acc: self.navigate.emit(p))
            self._layout.addWidget(btn)
            if i < len(parts) - 1 and part != '/':
                sep = QLabel("/")
                sep.setFont(QFont("Hack Nerd Font", 11))
                sep.setFixedHeight(24)
                sep.setStyleSheet("color: rgba(255,255,255,0.3); padding: 0px 2px;")
                self._layout.addWidget(sep)
        self._layout.addStretch()


# ── File Panel ────────────────────────────────────────────────────────────────
class FilePanel(QWidget):
    path_changed      = pyqtSignal(str)
    selection_changed = pyqtSignal(list)

    def __init__(self, path, colors, show_hidden=False, parent=None):
        super().__init__(parent)
        self.current_path = path
        self.colors       = colors
        self.show_hidden  = show_hidden
        self.sort_by      = "name"
        self.sort_reverse = False
        self.view_mode    = "grid"   # default: grid

        self.icon_font    = QFont("Hack Nerd Font", 11)
        self.folder_glyph = "\uf07b"
        self.file_glyph   = "\uf15b"

        self._clipboard   = []
        self._clip_action = "copy"
        self._all_entries = []   # unfiltered list for search

        self._build()

    def _build(self):
        self.setObjectName("filePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── View mode toggle (top-right of panel) ──
        mode_bar = QHBoxLayout()
        mode_bar.setContentsMargins(8, 6, 8, 6)
        mode_bar.setSpacing(2)
        mode_bar.addStretch()

        self.btn_grid  = QPushButton("⊞")
        self.btn_list  = QPushButton("≡")
        self.btn_table = QPushButton("⊟")
        for b in [self.btn_grid, self.btn_list, self.btn_table]:
            b.setCheckable(True)
            b.setFixedSize(28, 24)
            b.setFont(QFont("Hack Nerd Font", 11))
            mode_bar.addWidget(b)

        self.btn_grid.setChecked(True)
        self.btn_grid.clicked.connect(lambda: self._set_view("grid"))
        self.btn_list.clicked.connect(lambda: self._set_view("list"))
        self.btn_table.clicked.connect(lambda: self._set_view("table"))
        layout.addLayout(mode_bar)

        # ── Views ──
        self.grid_view = GridView()
        self.grid_view.folder_glyph = self.folder_glyph
        self.grid_view.file_glyph   = self.file_glyph
        self.grid_view.item_activated.connect(self._open_path)
        self.grid_view.ctx_requested.connect(self._ctx_grid)
        self.grid_view.selection_changed.connect(self.selection_changed.emit)
        self.grid_view.files_dropped.connect(self._on_grid_drop)

        self.file_list = DragDropList()
        self.file_list.setFont(self.icon_font)
        self.file_list.itemDoubleClicked.connect(lambda i: self._open_path(i.data(Qt.UserRole)))
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.file_list.mapToGlobal(pos)))
        self.file_list.itemSelectionChanged.connect(
            lambda: self.selection_changed.emit(self.get_selected()))
        self.file_list.hide()

        self.file_table = DragDropTable()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.setFont(self.icon_font)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.file_table.mapToGlobal(pos)))
        self.file_table.itemDoubleClicked.connect(
            lambda i: self._open_path(self.file_table.item(i.row(), 0).data(Qt.UserRole)))
        self.file_table.itemSelectionChanged.connect(
            lambda: self.selection_changed.emit(self.get_selected()))
        self.file_table.hide()

        layout.addWidget(self.grid_view,  stretch=1)
        layout.addWidget(self.file_list,  stretch=1)
        layout.addWidget(self.file_table, stretch=1)

    def update_colors(self, colors):
        self.colors = colors
        accent = colors.get("color4", "#89b4fa")
        fg     = colors.get("color7", "#cdd6f4")
        self.grid_view.update_colors(accent, fg)

    def _set_view(self, mode):
        self.view_mode = mode
        self.btn_grid.setChecked(mode == "grid")
        self.btn_list.setChecked(mode == "list")
        self.btn_table.setChecked(mode == "table")
        self.grid_view.setVisible(mode == "grid")
        self.file_list.setVisible(mode == "list")
        self.file_table.setVisible(mode == "table")
        self.load_directory(self.current_path)

    def load_directory(self, path):
        try:
            if self.view_mode == "table":
                self.file_table.save_col_widths()

            self.current_path = str(path)
            self.path_changed.emit(self.current_path)

            raw = list(Path(path).iterdir())
            if not self.show_hidden:
                raw = [e for e in raw if not e.name.startswith(".")]

            # Sort
            dirs  = [e for e in raw if e.is_dir()]
            files = [e for e in raw if not e.is_dir()]
            key   = {"name": lambda x: x.name.lower(),
                     "size": lambda x: x.stat().st_size if x.is_file() else 0,
                     "date": lambda x: x.stat().st_mtime,
                     "type": lambda x: x.suffix.lower()}.get(self.sort_by, lambda x: x.name.lower())
            dirs.sort(key=key, reverse=self.sort_reverse)
            files.sort(key=key, reverse=self.sort_reverse)
            entries = dirs + files
            self._all_entries = entries

            if self.view_mode == "grid":
                # Add parent ".." entry
                if str(path) != "/":
                    parent_path = str(Path(path).parent)
                    all_paths = [parent_path] + [str(e) for e in entries]
                else:
                    all_paths = [str(e) for e in entries]
                self.grid_view.populate(all_paths)

            elif self.view_mode == "list":
                self.file_list.clear()
                if str(path) != "/":
                    it = QListWidgetItem(f"{self.folder_glyph}  ..")
                    it.setData(Qt.UserRole, str(Path(path).parent))
                    it.setFont(self.icon_font)
                    self.file_list.addItem(it)
                for e in entries:
                    g = self.folder_glyph if e.is_dir() else self.file_glyph
                    it = QListWidgetItem(f"{g}  {e.name}")
                    it.setData(Qt.UserRole, str(e))
                    it.setFont(self.icon_font)
                    self.file_list.addItem(it)

            elif self.view_mode == "table":
                self.file_table.setRowCount(0)
                if str(path) != "/":
                    self._add_row(Path(path).parent, "..")
                for e in entries:
                    self._add_row(e)
                self.file_table.restore_col_widths()

        except PermissionError:
            QMessageBox.warning(self, "Permission denied", str(path))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _add_row(self, path, override_name=None):
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)
        name = override_name or path.name
        g = self.folder_glyph if path.is_dir() else self.file_glyph
        ni = QTableWidgetItem(f"{g}  {name}")
        ni.setData(Qt.UserRole, str(path)); ni.setFont(self.icon_font)
        self.file_table.setItem(row, 0, ni)
        self.file_table.setItem(row, 1, QTableWidgetItem(
            self._fmt_size(path.stat().st_size) if path.is_file() else ""))
        self.file_table.setItem(row, 2, QTableWidgetItem(self._file_type(path)))
        self.file_table.setItem(row, 3, QTableWidgetItem(
            datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d  %H:%M")))

    def _open_path(self, path):
        if not path: return
        if Path(path).is_dir():
            self.load_directory(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def get_selected(self):
        if self.view_mode == "grid":
            return self.grid_view.get_selected()
        elif self.view_mode == "list":
            return [i.data(Qt.UserRole) for i in self.file_list.selectedItems() if i.data(Qt.UserRole)]
        elif self.view_mode == "table":
            rows = set(i.row() for i in self.file_table.selectedItems())
            return [self.file_table.item(r, 0).data(Qt.UserRole)
                    for r in rows if self.file_table.item(r, 0) and self.file_table.item(r, 0).data(Qt.UserRole)]
        return []

    def select_all(self):
        if self.view_mode == "grid":   self.grid_view.select_all()
        elif self.view_mode == "list": self.file_list.selectAll()
        elif self.view_mode == "table": self.file_table.selectAll()

    def filter(self, text):
        text = text.lower()
        if self.view_mode == "list":
            for i in range(self.file_list.count()):
                it = self.file_list.item(i)
                it.setHidden(bool(text) and text not in it.text().lower() and ".." not in it.text())
        elif self.view_mode == "table":
            for i in range(self.file_table.rowCount()):
                cell = self.file_table.item(i, 0)
                name = cell.text().lower() if cell else ""
                self.file_table.setRowHidden(i, bool(text) and text not in name and ".." not in name)

    # ── Context menu ──────────────────────────
    def _ctx_grid(self, paths, pos):
        self._show_menu(pos, paths)

    def _show_menu(self, global_pos, paths=None):
        if paths is None: paths = self.get_selected()
        menu = QMenu(self)

        if len(paths) == 1:
            menu.addAction("Open",         lambda: self._open_path(paths[0]))
            menu.addAction("Open With…",   lambda: self._open_with(paths[0]))
            menu.addSeparator()

        if paths:
            menu.addAction("Copy",         self.copy)
            menu.addAction("Cut",          self.cut)
        paste_action = menu.addAction("Paste", self.paste)
        paste_action.setEnabled(bool(self._clipboard))
        menu.addSeparator()

        if paths:
            menu.addAction("Duplicate",    self.duplicate)
            if len(paths) == 1:
                menu.addAction("Rename  F2", self.rename)
            menu.addAction("Compress…",    self.compress)
            menu.addSeparator()

        if len(paths) == 1:
            p = Path(paths[0])
            if self._is_archive(p):
                menu.addAction("Extract Here",  lambda: self._extract_here(p))
                menu.addAction("Extract To…",   lambda: self._extract_to(p))
                menu.addSeparator()
            menu.addAction("Copy Path",    lambda: QApplication.clipboard().setText(paths[0]))
            menu.addAction("Properties",   lambda: PropertiesDialog(paths[0], self).exec_())
            menu.addSeparator()

        menu.addAction("Open Terminal Here", self.open_terminal)
        menu.addAction("Select All  Ctrl+A", self.select_all)

        if paths:
            menu.addSeparator()
            menu.addAction("Delete",       self.delete)

        menu.exec_(global_pos)

    def _open_with(self, path):
        dlg = OpenWithDialog(path, self)
        if dlg.exec_() == QDialog.Accepted:
            app = dlg.get_app()
            if app:
                try: subprocess.Popen([app, path])
                except FileNotFoundError: QMessageBox.warning(self, "Not found", f"'{app}' not found")

    def open_terminal(self):
        for term in ["kitty", "alacritty", "wezterm", "foot", "gnome-terminal", "konsole", "xterm"]:
            try: subprocess.Popen([term, "--working-directory", self.current_path]); return
            except FileNotFoundError: continue
        QMessageBox.warning(self, "No terminal", "No terminal emulator found")

    # ── File ops ──────────────────────────────
    def copy(self):
        self._clipboard = self.get_selected(); self._clip_action = "copy"
    def cut(self):
        self._clipboard = self.get_selected(); self._clip_action = "cut"
    def paste(self):
        if self._clipboard:
            self._do_file_op(self._clipboard, self._clip_action, self.current_path)
            if self._clip_action == "cut": self._clipboard = []

    def _on_grid_drop(self, paths, action):
        if ':' in action:
            real_action, dest = action.split(':', 1)
        else:
            real_action, dest = action, self.current_path
        self._do_file_op(paths, real_action, dest)

    def _do_file_op(self, sources, action, dest_dir):
        errors = []
        for src in sources:
            sp = Path(src)
            print(f"[fileop] {action} {sp} -> {dest_dir}, sp.parent={sp.parent}, skip={sp.parent == Path(dest_dir)}")
            if sp.parent == Path(dest_dir): continue
            dest = Path(dest_dir) / sp.name; c = 1
            while dest.exists():
                dest = Path(dest_dir) / f"{sp.stem}_{c}{sp.suffix}"; c += 1
            print(f"[fileop] dest resolved to {dest}")
            try:
                if action == "copy": shutil.copytree(src, dest) if sp.is_dir() else shutil.copy2(src, dest)
                else: shutil.move(src, str(dest))
                print(f"[fileop] success")
            except Exception as e:
                print(f"[fileop] ERROR: {e}")
                errors.append(f"{sp.name}: {e}")
        self.load_directory(self.current_path)
        if errors: QMessageBox.warning(self, "Errors", "\n".join(errors))

    def duplicate(self):
        for path in self.get_selected():
            p = Path(path); sfx = "".join(p.suffixes); stem = p.name[:-len(sfx)] if sfx else p.name
            dest = p.parent / f"{stem} (copy){sfx}"; c = 2
            while dest.exists(): dest = p.parent / f"{stem} (copy {c}){sfx}"; c += 1
            try: shutil.copytree(str(p), str(dest)) if p.is_dir() else shutil.copy2(str(p), str(dest))
            except Exception as e: QMessageBox.critical(self, "Error", str(e))
        self.load_directory(self.current_path)

    def rename(self):
        sel = self.get_selected()
        if len(sel) != 1: return
        old = Path(sel[0])
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old.name)
        if ok and name and name != old.name:
            new = old.parent / name
            if new.exists(): QMessageBox.warning(self, "Error", f"'{name}' already exists"); return
            try: old.rename(new); self.load_directory(self.current_path)
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def delete(self):
        paths = self.get_selected()
        if not paths: return
        reply = QMessageBox.question(self, "Delete", f"Move {len(paths)} item(s) to trash?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes: return
        for p in paths:
            try:
                r = subprocess.run(["trash-put", p], capture_output=True)
                if r.returncode != 0: raise Exception(r.stderr.decode())
            except FileNotFoundError:
                pp = Path(p); shutil.rmtree(pp) if pp.is_dir() else pp.unlink()
            except Exception as e: QMessageBox.critical(self, "Error", str(e))
        self.load_directory(self.current_path)

    def compress(self):
        paths = self.get_selected()
        if not paths: return
        default = Path(paths[0]).stem if len(paths) == 1 else "archive"
        name, ok = QInputDialog.getText(self, "Compress", "Archive name:", text=default)
        if not ok or not name: return
        fmt, ok2 = QInputDialog.getItem(self, "Format", "Format:", ["zip","tar.gz","tar.bz2","tar.xz"], 0, False)
        if not ok2: return
        dest = Path(self.current_path) / f"{name}.{fmt}"
        try:
            if fmt == "zip":
                with zipfile.ZipFile(str(dest), "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in paths:
                        pp = Path(p)
                        if pp.is_dir():
                            for f in pp.rglob("*"): zf.write(str(f), str(f.relative_to(pp.parent)))
                        else: zf.write(p, pp.name)
            else:
                mode = {"tar.gz":"w:gz","tar.bz2":"w:bz2","tar.xz":"w:xz"}[fmt]
                with tarfile.open(str(dest), mode) as tf:
                    for p in paths: tf.add(p, arcname=Path(p).name)
            self.load_directory(self.current_path)
        except Exception as e: QMessageBox.critical(self, "Compression error", str(e))

    def _is_archive(self, p):
        if not p.is_file(): return False
        exts = {'.zip','.tar','.gz','.bz2','.xz','.7z','.rar','.tgz','.tbz2','.txz'}
        return p.suffix.lower() in exts or ''.join(p.suffixes[-2:]).lower() in {'.tar.gz','.tar.bz2','.tar.xz'}

    def _extract_here(self, p): self._run_extract(p, p.parent)
    def _extract_to(self, p):
        dest = p.parent / p.stem; c = 1
        while dest.exists(): dest = p.parent / f"{p.stem}_{c}"; c += 1
        dest.mkdir(parents=True); self._run_extract(p, dest)

    def _run_extract(self, p, dest):
        ext = p.suffix.lower(); compound = ''.join(p.suffixes[-2:]).lower()
        try:
            if ext == '.zip': subprocess.run(['unzip','-q',str(p),'-d',str(dest)], check=True)
            elif ext == '.7z': subprocess.run(['7z','x',str(p),f'-o{dest}','-y'], check=True)
            elif ext == '.rar': subprocess.run(['unrar','x','-y',str(p),str(dest)], check=True)
            elif compound in {'.tar.gz','.tar.bz2','.tar.xz'} or ext in {'.tar','.tgz','.tbz2','.txz'}:
                subprocess.run(['tar','-xf',str(p),'-C',str(dest)], check=True)
            self.load_directory(self.current_path)
        except subprocess.CalledProcessError as e: QMessageBox.critical(self, "Extract failed", str(e))
        except FileNotFoundError: QMessageBox.critical(self, "Missing tool", "Required extraction tool not found")

    # ── Helpers ───────────────────────────────
    def _fmt_size(self, size):
        for u in ['B','KB','MB','GB','TB']:
            if size < 1024.0: return f"{size:.1f} {u}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def _file_type(self, path):
        if path.is_dir(): return "Folder"
        types = {'.txt':'Text','.pdf':'PDF','.doc':'Word','.docx':'Word',
                 '.jpg':'Image','.jpeg':'Image','.png':'Image','.gif':'Image',
                 '.mp4':'Video','.mkv':'Video','.avi':'Video',
                 '.mp3':'Audio','.wav':'Audio','.flac':'Audio',
                 '.zip':'Archive','.tar':'Archive','.7z':'Archive',
                 '.py':'Python','.js':'JavaScript','.html':'HTML','.css':'CSS'}
        return types.get(path.suffix.lower(), path.suffix[1:].upper() if path.suffix else 'File')


# ── Sidebar nav button with proper drag-drop ──────────────────────────────────
class NavButton(QWidget):
    clicked      = pyqtSignal(str)
    files_dropped = pyqtSignal(list, str)   # paths, dest_path

    def __init__(self, glyph, label, path, accent, fg, dim, removable=False, parent=None):
        super().__init__(parent)
        self.path    = path
        self.accent  = accent
        self._normal_ss  = "NavButton { background: transparent; border-radius: 6px; } NavButton:hover { background: rgba(255,255,255,0.07); }"
        ac = QColor(accent)
        self._drag_ss    = f"NavButton {{ background: rgba({ac.red()},{ac.green()},{ac.blue()},60); border-radius: 6px; border: 1px solid {accent}; }}"

        self.setFixedHeight(34)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAcceptDrops(True)
        self.setStyleSheet(self._normal_ss)

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 0, 8, 0)
        h.setSpacing(8)

        icon = QLabel(glyph)
        icon.setFont(QFont("Hack Nerd Font", 13))
        icon.setStyleSheet(f"color:{accent}; background:transparent;")
        icon.setFixedWidth(20)
        h.addWidget(icon)

        name = QLabel(label)
        name.setFont(QFont("Hack Nerd Font", 10))
        name.setStyleSheet(f"color:{fg}; background:transparent;")
        h.addWidget(name, stretch=1)

        if removable:
            rm = QPushButton("×")
            rm.setFixedSize(18, 18)
            rm.setFont(QFont("Hack Nerd Font", 10))
            rm.setStyleSheet(f"color:{dim}; background:transparent; border:none;")
            rm.setCursor(QCursor(Qt.PointingHandCursor))
            rm.clicked.connect(lambda: self.files_dropped.emit([], '__remove__'))
            h.addWidget(rm)

        # make child labels pass drag events up
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.path)
        super().mousePressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self.setStyleSheet(self._drag_ss)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.setStyleSheet(self._normal_ss)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.setDropAction(Qt.CopyAction if e.keyboardModifiers() & Qt.ControlModifier else Qt.MoveAction)
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        self.setStyleSheet(self._normal_ss)
        if e.mimeData().hasUrls():
            paths  = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths, self.path)
            e.acceptProposedAction()


# ── Sidebar ───────────────────────────────────────────────────────────────────
class Sidebar(QWidget):
    navigate         = pyqtSignal(str)
    bookmark_removed = pyqtSignal(str)
    files_dropped    = pyqtSignal(list, str)   # paths, dest_path

    PINNED = [
        ("\uf015", "Home",      str(Path.home())),
        ("\uf07b", "Documents", str(Path.home() / "Documents")),
        ("\uf03e", "Pictures",  str(Path.home() / "Pictures")),
        ("\uf1c8", "Videos",    str(Path.home() / "Videos")),
        ("\uf001", "Music",     str(Path.home() / "Music")),
        ("\uf019", "Downloads", str(Path.home() / "Downloads")),
    ]

    def __init__(self, colors, bookmarks, parent=None):
        super().__init__(parent)
        self.colors    = colors
        self.bookmarks = bookmarks
        self.setFixedWidth(220)
        self._build()

    def _build(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(0)
        self.refresh()

    def refresh(self, colors=None, bookmarks=None):
        if colors:    self.colors    = colors
        if bookmarks is not None: self.bookmarks = bookmarks

        # Clear
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w: w.deleteLater()

        accent = self.colors.get("color4", "#89b4fa")
        fg     = self.colors.get("color7", "#cdd6f4")
        dim    = "rgba(255,255,255,0.4)"

        def section_label(text):
            lbl = QLabel(text.upper())
            lbl.setStyleSheet(f"color:{dim}; font-size:10px; font-weight:700; "
                               "padding:12px 16px 4px 16px; letter-spacing:1px;")
            return lbl

        def nav_btn(glyph, label, path, removable=False):
            btn = NavButton(glyph, label, path, accent, fg, dim, removable=removable)
            btn.clicked.connect(self.navigate.emit)
            btn.files_dropped.connect(lambda paths, dest: (
                self.bookmark_removed.emit(path) if dest == '__remove__'
                else self.files_dropped.emit(paths, dest)
            ))
            return btn

        # ── Pinned ──
        self._layout.addWidget(section_label("Pinned"))
        for glyph, label, path in self.PINNED:
            if Path(path).exists():
                self._layout.addWidget(nav_btn(glyph, label, path))

        # ── Bookmarks ──
        if self.bookmarks:
            self._layout.addWidget(section_label("Bookmarks"))
            for b in self.bookmarks:
                bp = Path(b)
                if bp.exists():
                    self._layout.addWidget(nav_btn("\uf02e", bp.name, b, removable=True))

        # ── Drives ──
        drives = self._get_drives()
        if drives:
            self._layout.addWidget(section_label("Devices"))
            for d in drives:
                self._layout.addWidget(nav_btn("\uf287", d['name'], d['path']))

        # ── Trash ──
        self._layout.addWidget(section_label("Other"))
        trash_path = str(Path.home() / ".local/share/Trash/files")
        trash_row  = nav_btn("\uf1f8", "Trash", trash_path)

        def _empty_trash():
            trash_base = Path.home() / ".local/share/Trash"
            reply = QMessageBox.question(
                self, "Empty Trash",
                "Permanently delete all items in Trash?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            import shutil as _shutil
            errors = []
            for sub in ["files", "info", "expunged"]:
                d = trash_base / sub
                if d.exists():
                    for item in d.iterdir():
                        try:
                            _shutil.rmtree(str(item)) if item.is_dir() else item.unlink()
                        except Exception as ex:
                            errors.append(str(ex))
            if errors:
                QMessageBox.warning(self, "Errors", "\n".join(errors))

        def _trash_press(e):
            if e.button() == Qt.RightButton:
                menu = QMenu(self)
                menu.addAction("Empty Trash", _empty_trash)
                menu.exec_(e.globalPos())
            else:
                NavButton.mousePressEvent(trash_row, e)

        trash_row.mousePressEvent = _trash_press
        self._layout.addWidget(trash_row)

        self._layout.addStretch()

    def _get_drives(self):
        drives = []
        try:
            with open('/proc/mounts') as f:
                for line in f:
                    parts = line.split(None, 4)
                    if len(parts) < 2: continue
                    mp = parts[1].encode().decode('unicode_escape')
                    skip = {'/','/boot','/home','/tmp','/var','/usr','/sys','/proc','/dev','/run'}
                    if mp in skip or mp.startswith(('/sys/','/proc/','/dev/','/run/user')): continue
                    if mp.startswith(('/media/','/mnt/','/run/media/')) and Path(mp).exists():
                        drives.append({'name': Path(mp).name or mp, 'path': mp})
        except Exception:
            pass
        return drives


# ── Translucent background widget ────────────────────────────────────────────
class BgWidget(QWidget):
    """Paints one semi-transparent rect. All children stay transparent."""
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = color

    def set_color(self, color):
        self._color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self._color)


# ── Main Window ───────────────────────────────────────────────────────────────
class FileManager(QMainWindow):
    MAX_RECENT = 20

    def __init__(self):
        super().__init__()
        self.colors_file    = Path.home() / ".cache/wal/colors.json"
        self.bookmarks_file = Path.home() / ".config/pyqt_filemanager_bookmarks.json"
        self.colors         = self._load_colors()
        self.bookmarks      = self._load_bookmarks()
        self.show_hidden    = False

        self.watcher = QFileSystemWatcher([str(self.colors_file)])
        self.watcher.fileChanged.connect(self._reload_theme)

        self._history  = [str(Path.home())]
        self._hist_pos = 0
        self._nav_lock = False

        self._build_ui()
        self._setup_shortcuts()
        self._apply_theme()
        self.panel.load_directory(str(Path.home()))

    def _load_colors(self):
        try:
            if self.colors_file.exists():
                c = json.loads(self.colors_file.read_text()).get("colors", {})
                if c: return c
        except Exception: pass
        return {"color0":"#1e1e2e","color7":"#cdd6f4","color4":"#89b4fa","color8":"#313244"}

    def _reload_theme(self):
        self.colors = self._load_colors()
        self._apply_theme()
        self.panel.update_colors(self.colors)
        self.sidebar.refresh(colors=self.colors)
        self.breadcrumb.set_path(self.panel.current_path, self.colors.get("color4","#89b4fa"))

    def _apply_theme(self):
        bg     = QColor(self.colors.get("color0","#1e1e2e"))
        fg     = QColor(self.colors.get("color7","#cdd6f4"))
        accent = QColor(self.colors.get("color4","#89b4fa"))
        hover  = QColor(self.colors.get("color8","#313244"))

        QApplication.setStyle(QStyleFactory.create("Fusion"))

        # Use transparent variants in the palette so the compositor shows through
        bg_trans   = QColor(bg.red(), bg.green(), bg.blue(), 0)    # fully transparent for base
        bg_palette = QColor(bg.red(), bg.green(), bg.blue(), 180)  # semi-transparent for widgets

        pal = QApplication.palette()
        pal.setColor(QPalette.Window,          bg_trans)
        pal.setColor(QPalette.WindowText,      fg)
        pal.setColor(QPalette.Base,            bg_trans)
        pal.setColor(QPalette.AlternateBase,   QColor(hover.red(), hover.green(), hover.blue(), 120))
        pal.setColor(QPalette.Text,            fg)
        pal.setColor(QPalette.Button,          bg_palette)
        pal.setColor(QPalette.ButtonText,      fg)
        pal.setColor(QPalette.Highlight,       accent)
        pal.setColor(QPalette.HighlightedText, bg)
        QApplication.setPalette(pal)

        r, g, b   = bg.red(), bg.green(), bg.blue()
        fg_s      = fg.name()
        ac_s      = accent.name()
        ac_a      = f"rgba({accent.red()},{accent.green()},{accent.blue()},180)"
        hv_s      = hover.name()
        hv_a      = f"rgba({hover.red()},{hover.green()},{hover.blue()},180)"

        # Single unified alpha for all surfaces — tweak this one value to taste
        A         = 180                        # 0=fully transparent, 255=fully opaque
        bg_fill   = f"rgba({r},{g},{b},{A})"  # every surface uses this
        bg_pop    = f"rgba({r},{g},{b},220)"  # menus/dropdowns slightly more opaque for readability

        _bgc = QColor(bg.red(), bg.green(), bg.blue(), 180)
        if hasattr(self, '_bg_widget'):
            self._bg_widget.set_color(_bgc)

        self.setStyleSheet(f"""
            QMainWindow, QWidget, QAbstractScrollArea {{
                background: transparent; color: {fg_s};
            }}
            QAbstractScrollArea::viewport {{ background: transparent; }}
            #toolbar {{ border-bottom: 1px solid rgba(255,255,255,0.07); padding: 0 4px; }}
            #sidebar {{ border-right: 1px solid rgba(255,255,255,0.07); }}
            QPushButton {{
                border-radius: 6px; padding: 4px 10px;
                background: transparent; color: {fg_s}; border: none;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.08); }}
            QPushButton:checked, QPushButton:pressed {{ background: {ac_a}; color: {fg_s}; }}
            QLineEdit {{
                border-radius: 6px; padding: 4px 10px;
                background: rgba(255,255,255,0.06); color: {fg_s};
                border: 1px solid rgba(255,255,255,0.08);
                selection-background-color: {ac_s};
            }}
            QLineEdit:focus {{ border: 1px solid {ac_s}; background: rgba(255,255,255,0.09); }}
            QComboBox {{
                border-radius: 6px; padding: 4px 8px;
                background: rgba(255,255,255,0.06); color: {fg_s};
                border: 1px solid rgba(255,255,255,0.08);
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {bg_pop}; color: {fg_s}; selection-background-color: {ac_s};
            }}
            QListWidget, QTableWidget {{ border: none; }}
            QListWidget::item, QTableWidget::item {{
                padding: 3px 6px; border-radius: 4px; color: {fg_s};
            }}
            QListWidget::item:selected, QTableWidget::item:selected {{
                background: {ac_a}; color: {fg_s};
            }}
            QListWidget::item:hover, QTableWidget::item:hover {{ background: rgba(255,255,255,0.06); }}
            QHeaderView::section {{
                background: rgba(255,255,255,0.04); color: {fg_s};
                border: none; padding: 4px 6px; font-weight: 600;
            }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,0.15); border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ height: 6px; background: transparent; }}
            QScrollBar::handle:horizontal {{
                background: rgba(255,255,255,0.15); border-radius: 3px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QSplitter::handle {{ background: rgba(255,255,255,0.06); width: 1px; height: 1px; }}
            QMenu {{
                background: {bg_pop}; color: {fg_s};
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {ac_a}; color: {fg_s}; }}
            QMenu::separator {{
                height: 1px; background: rgba(255,255,255,0.1); margin: 3px 8px;
            }}
            QStatusBar {{
                color: rgba(255,255,255,0.4); font-size: 11px;
                border-top: 1px solid rgba(255,255,255,0.07);
            }}
        """)

        if hasattr(self, 'panel'):
            self.panel.update_colors(self.colors)

    # ── UI ────────────────────────────────────
    def _build_ui(self):
        self.setWindowTitle("Files")
        self.setGeometry(100, 100, 1280, 800)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        _bg0 = QColor(self.colors.get("color0","#1e1e2e"))
        self._bg_widget = BgWidget(QColor(_bg0.red(), _bg0.green(), _bg0.blue(), 180))
        self.setCentralWidget(self._bg_widget)
        root = QVBoxLayout(self._bg_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        ifont     = QFont("Hack Nerd Font", 13)
        icon_size = QSize(30, 30)

        # ── Toolbar ──────────────────────────────
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(52)
        tbar = QHBoxLayout(toolbar)
        tbar.setContentsMargins(8, 6, 8, 6)
        tbar.setSpacing(4)

        def nav_btn(glyph, tip):
            b = QPushButton(glyph)
            b.setFont(ifont)
            b.setFixedSize(34, 34)
            b.setToolTip(tip)
            return b

        self.btn_back    = nav_btn("󰁍", "Back  (Alt+←)")
        self.btn_forward = nav_btn("󰁔", "Forward  (Alt+→)")
        self.btn_up      = nav_btn("󰁞", "Up  (Alt+↑)")
        self.btn_home    = nav_btn("󰋜", "Home")
        self.btn_refresh = nav_btn("󰑐", "Refresh  (F5)")

        for b in [self.btn_back, self.btn_forward, self.btn_up, self.btn_home, self.btn_refresh]:
            tbar.addWidget(b)

        tbar.addSpacing(6)

        # Breadcrumb + path edit combo
        self.path_stack = QWidget()
        ps_layout = QHBoxLayout(self.path_stack)
        ps_layout.setContentsMargins(0,0,0,0)
        ps_layout.setSpacing(0)

        self.breadcrumb_widget = QWidget()
        bc_layout = QHBoxLayout(self.breadcrumb_widget)
        bc_layout.setContentsMargins(0,0,0,0)
        bc_layout.setSpacing(0)

        self.breadcrumb = Breadcrumb()
        self.breadcrumb.navigate.connect(self._nav_breadcrumb)
        bc_layout.addWidget(self.breadcrumb)

        # Click on breadcrumb area → switch to path edit
        self.breadcrumb_widget.mousePressEvent = lambda e: self._enter_path_edit()
        self.breadcrumb_widget.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.06);
                border-radius: 6px;
                border: 1px solid rgba(255,255,255,0.08);
            }
        """)
        self.breadcrumb_widget.setCursor(QCursor(Qt.IBeamCursor))

        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self._nav_to_path)
        self.path_edit.hide()
        # Escape key hides path edit
        self.path_edit.installEventFilter(self)

        ps_layout.addWidget(self.breadcrumb_widget)
        ps_layout.addWidget(self.path_edit)
        tbar.addWidget(self.path_stack, stretch=1)

        tbar.addSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText("  Search…")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self._filter)
        tbar.addWidget(self.search)

        tbar.addSpacing(4)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Name ↑","Name ↓","Size ↑","Size ↓","Date ↑","Date ↓","Type"])
        self.sort_combo.setFixedWidth(95)
        self.sort_combo.currentIndexChanged.connect(self._change_sort)
        tbar.addWidget(self.sort_combo)

        tbar.addSpacing(4)

        self.btn_new_folder = nav_btn("󰉋", "New Folder  (Ctrl+N)")
        self.btn_new_file   = nav_btn("󰈔", "New File  (Ctrl+Shift+N)")
        self.btn_term       = nav_btn("󰆍", "Open Terminal  (Ctrl+T)")
        self.btn_hidden     = nav_btn("󰜉", "Show Hidden  (Ctrl+H)")
        self.btn_hidden.setCheckable(True)
        self.btn_bookmark   = nav_btn("󰃀", "Bookmark this folder  (Ctrl+B)")

        for b in [self.btn_new_folder, self.btn_new_file, self.btn_term, self.btn_hidden, self.btn_bookmark]:
            tbar.addWidget(b)

        # Window controls (frameless)
        tbar.addSpacing(8)
        self.btn_min   = QPushButton("−")
        self.btn_max   = QPushButton("□")
        self.btn_close = QPushButton("×")
        for b, tip in [(self.btn_min,"Minimise"),(self.btn_max,"Maximise"),(self.btn_close,"Close")]:
            b.setFixedSize(28, 28)
            b.setFont(QFont("Hack Nerd Font", 11))
            b.setToolTip(tip)
            tbar.addWidget(b)

        root.addWidget(toolbar)

        # ── Body: sidebar | panel ─────────────────
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)

        self.sidebar = Sidebar(self.colors, self.bookmarks)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.navigate.connect(self._nav_sidebar)
        self.sidebar.bookmark_removed.connect(self._remove_bookmark)
        self.sidebar.files_dropped.connect(
            lambda paths, dest: self.panel._do_file_op(paths, 'move', dest))
        self.splitter.addWidget(self.sidebar)

        self.panel = FilePanel(str(Path.home()), self.colors, self.show_hidden)
        self.panel.path_changed.connect(self._on_path_changed)
        self.panel.selection_changed.connect(self._on_selection_changed)
        self.panel.update_colors(self.colors)
        self.splitter.addWidget(self.panel)

        self.splitter.setSizes([220, 1060])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        root.addWidget(self.splitter, stretch=1)

        # ── Status bar ────────────────────────────
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        # ── Wire buttons ──────────────────────────
        self.btn_back.clicked.connect(self._go_back)
        self.btn_forward.clicked.connect(self._go_forward)
        self.btn_up.clicked.connect(self._go_up)
        self.btn_home.clicked.connect(lambda: self.panel.load_directory(str(Path.home())))
        self.btn_refresh.clicked.connect(self._refresh)
        self.btn_new_folder.clicked.connect(self._create_folder)
        self.btn_new_file.clicked.connect(self._create_file)
        self.btn_term.clicked.connect(lambda: self.panel.open_terminal())
        self.btn_hidden.toggled.connect(self._toggle_hidden)
        self.btn_bookmark.clicked.connect(self._add_bookmark)

        self.btn_close.clicked.connect(self.close)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(lambda: self.showNormal() if self.isMaximized() else self.showMaximized())

        # Drag window
        self._drag_pos = None
        toolbar.mousePressEvent  = self._tb_press
        toolbar.mouseMoveEvent   = self._tb_move
        toolbar.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)

    def eventFilter(self, obj, event):
        if obj is self.path_edit and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Escape:
                self._leave_path_edit()
                return True
        return super().eventFilter(obj, event)

    def _enter_path_edit(self):
        self.breadcrumb_widget.hide()
        self.path_edit.show()
        self.path_edit.setText(self.panel.current_path)
        self.path_edit.setFocus()
        self.path_edit.selectAll()

    def _leave_path_edit(self):
        self.path_edit.hide()
        self.breadcrumb_widget.show()

    def _tb_press(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def _tb_move(self, e):
        if e.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(e.globalPos() - self._drag_pos)

    # ── Navigation ────────────────────────────
    def _on_path_changed(self, path):
        self.breadcrumb.set_path(path, self.colors.get("color4","#89b4fa"))
        self.path_edit.setText(path)
        self._leave_path_edit()
        if not self._nav_lock:
            self._history = self._history[:self._hist_pos + 1]
            if not self._history or self._history[-1] != path:
                self._history.append(path)
                self._hist_pos = len(self._history) - 1
        self.setWindowTitle(f"Files — {Path(path).name or path}")

    def _on_selection_changed(self, paths):
        n = len(paths)
        if n == 0:
            self.statusBar().showMessage(f"{self.panel.current_path}")
        elif n == 1:
            p = Path(paths[0])
            info = f"  {p.stat().st_size:,} bytes" if p.is_file() else "  Folder"
            self.statusBar().showMessage(f"{p.name}{info}")
        else:
            self.statusBar().showMessage(f"{n} items selected")

    def _go_back(self):
        if self._hist_pos > 0:
            self._hist_pos -= 1
            self._nav_lock = True
            self.panel.load_directory(self._history[self._hist_pos])
            self._nav_lock = False

    def _go_forward(self):
        if self._hist_pos < len(self._history) - 1:
            self._hist_pos += 1
            self._nav_lock = True
            self.panel.load_directory(self._history[self._hist_pos])
            self._nav_lock = False

    def _go_up(self):
        self.panel.load_directory(str(Path(self.panel.current_path).parent))

    def _refresh(self):
        self.panel.load_directory(self.panel.current_path)
        self.sidebar.refresh()

    def _nav_to_path(self):
        p = self.path_edit.text().strip()
        if Path(p).is_dir():
            self.panel.load_directory(p)
        else:
            QMessageBox.warning(self, "Invalid path", p)
        self._leave_path_edit()

    def _nav_breadcrumb(self, path):
        self.panel.load_directory(path)

    def _nav_sidebar(self, path):
        if Path(path).exists():
            self.panel.load_directory(path)

    # ── Toolbar actions ───────────────────────
    def _create_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Name:")
        if ok and name:
            dest = Path(self.panel.current_path) / name
            try: dest.mkdir(); self.panel.load_directory(self.panel.current_path)
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _create_file(self):
        name, ok = QInputDialog.getText(self, "New File", "Name:")
        if ok and name:
            dest = Path(self.panel.current_path) / name
            try: dest.touch(); self.panel.load_directory(self.panel.current_path)
            except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def _toggle_hidden(self, checked):
        self.show_hidden = checked
        self.panel.show_hidden = checked
        self.panel.load_directory(self.panel.current_path)

    def _filter(self):
        self.panel.filter(self.search.text())

    def _change_sort(self, idx):
        sorts = {0:("name",False),1:("name",True),2:("size",False),
                 3:("size",True),4:("date",False),5:("date",True),6:("type",False)}
        by, rev = sorts[idx]
        self.panel.sort_by = by
        self.panel.sort_reverse = rev
        self.panel.load_directory(self.panel.current_path)

    # ── Bookmarks ─────────────────────────────
    def _add_bookmark(self):
        p = self.panel.current_path
        if p not in self.bookmarks:
            self.bookmarks.append(p)
            self._save_bookmarks()
            self.sidebar.refresh(bookmarks=self.bookmarks)

    def _remove_bookmark(self, p):
        if p in self.bookmarks:
            self.bookmarks.remove(p)
            self._save_bookmarks()
            self.sidebar.refresh(bookmarks=self.bookmarks)

    def _load_bookmarks(self):
        try:
            if self.bookmarks_file.exists():
                return json.loads(self.bookmarks_file.read_text())
        except Exception: pass
        return []

    def _save_bookmarks(self):
        try:
            self.bookmarks_file.parent.mkdir(parents=True, exist_ok=True)
            self.bookmarks_file.write_text(json.dumps(self.bookmarks, indent=2))
        except Exception as e:
            print(f"Bookmark error: {e}")

    # ── Shortcuts ─────────────────────────────
    def _setup_shortcuts(self):
        def s(key, fn): QShortcut(QKeySequence(key), self).activated.connect(fn)
        s("Ctrl+F",       lambda: self.search.setFocus())
        s("Ctrl+H",       lambda: self.btn_hidden.toggle())
        s("Ctrl+B",       self._add_bookmark)
        s("Ctrl+N",       self._create_folder)
        s("Ctrl+Shift+N", self._create_file)
        s("F5",           self._refresh)
        s("F2",           lambda: self.panel.rename())
        s("Ctrl+C",       lambda: self.panel.copy())
        s("Ctrl+X",       lambda: self.panel.cut())
        s("Ctrl+V",       lambda: self.panel.paste())
        s("Ctrl+I",       lambda: PropertiesDialog(self.panel.get_selected()[0], self).exec_()
                                  if self.panel.get_selected() else None)
        s("Ctrl+A",       lambda: self.panel.select_all())
        s("Alt+Left",     self._go_back)
        s("Alt+Right",    self._go_forward)
        s("Alt+Up",       self._go_up)
        s("Delete",       lambda: self.panel.delete())
        s("Ctrl+T",       lambda: self.panel.open_terminal())
        s("Escape",       lambda: (self.search.clear(), self.search.clearFocus()))
        s("Ctrl+L",       self._enter_path_edit)


# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Hack Nerd Font", 10))
    win = FileManager()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
