STYLE = """
QWidget { background: #222c3a; color: #dbe4f2; font-size: 12px; }
QMainWindow { background: #1c2532; }
QLabel#brand { font-size: 19px; font-weight: 700; color: #f2f6fd; }
QLabel#panelTitle { font-size: 18px; font-weight: 600; margin-bottom: 4px; }
QLabel#muted { color: #bdcbdc; line-height: 1.4; }
QLabel#status { color: #7cdec7; }
QPushButton { background: #273346; border: 1px solid #35445b; border-radius: 5px; padding: 7px 12px; }
QPushButton:hover { background: #34445d; border-color: #5b7596; }
QPushButton:pressed { background: #1c293a; }
QPushButton:disabled { background: #202936; color: #617086; border-color: #2c3543; }
QPushButton#primary { background: #287e71; border-color: #359b88; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #329181; }
QPushButton#primary:disabled { background: #263d3d; color: #718b87; }
QPushButton#danger { color: #ffb1bc; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #1a2432; border: 1px solid #576c86; border-radius: 4px; padding: 5px; min-height: 18px; }
QComboBox QAbstractItemView { background: #202c3d; selection-background-color: #365875; }
QTabBar::tab { background: #2c394c; color: #bdcbdc; padding: 12px 18px; border-bottom: 2px solid #2c394c; }
QTabBar::tab:selected { background: #223747; color: #91e6d3; border-bottom: 2px solid #60d1b5; }
QTabBar::tab:hover { color: white; background: #28384e; }
QSlider::groove:horizontal { height: 5px; background: #34445a; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: #67cbb5; border-radius: 6px; }
QSlider::sub-page:horizontal { background: #438f81; border-radius: 2px; }
QTableView { background: #222e3f; alternate-background-color: #1b2738; border: 1px solid #2d3a4f; selection-background-color: #304b65; }
QHeaderView::section { background: #223044; color: #9cafc8; border: none; padding: 6px; text-align: left; }
QScrollBar:vertical { background: #182230; width: 10px; }
QScrollBar::handle:vertical { background: #3c4c63; min-height: 25px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #1c2532; width: 5px; height: 5px; }
QProgressBar { background: #202c3d; border: 0; border-radius: 3px; text-align: center; min-height: 17px; }
QProgressBar::chunk { background: #327f73; border-radius: 3px; }
QCheckBox { spacing: 7px; padding: 2px; }
QCheckBox::indicator { width: 14px; height: 14px; }
QToolTip { color: #edf5ff; background: #293a50; border: 1px solid #607691; padding: 5px; }
QPlainTextEdit { background: #1c2532; color: #bccadd; border: 1px solid #34445c; font-family: Consolas; }
"""

STYLE += """
QListView, QTreeView { background: #263243; color: #e4edf8; border: 1px solid #4b5d74; }
QListView::item, QTreeView::item { padding: 4px; }
QListView::item:hover, QTreeView::item:hover { background: #40526b; }
QListView::item:selected, QTreeView::item:selected { background: #347f73; color: #ffffff; }
QGroupBox { border: 1px solid #50647d; margin-top: 12px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; color: #d6e5f5; }
QTabWidget::pane { border: 1px solid #465a72; }
"""

STYLE += """
QScrollBar:horizontal { background: #182230; height: 10px; }
QScrollBar::handle:horizontal { background: #61758e; min-width: 25px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""
