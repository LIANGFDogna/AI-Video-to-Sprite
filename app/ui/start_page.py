from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from app.i18n import t


class StartPage(QWidget):
    def __init__(self, window):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.addStretch()
        self.title = QLabel()
        self.title.setObjectName("panelTitle")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.buttons = []
        for label, callback in (("New Project", window.new_project), ("Open Project", window.open_project),
                ("Import Idle Video", window.choose_video), ("Import Video", window.choose_video),
                ("Import Frame Sequence", window.choose_sequence)):
            button = QPushButton(t(label))
            button.clicked.connect(callback)
            self.buttons.append(button)
            layout.addWidget(button)
        self.buttons[0].setObjectName("primary")
        layout.addStretch()

    def update_project(self, project, opened):
        self.title.setText(t("Project created") if opened else t("AI VIDEO  /  SPRITE"))
        self.hint.setText(t("Import Idle first to establish the character coordinate reference.") if not project.character_profile else t("Character Profile: locked"))
        self.buttons[0].setVisible(not opened)
        self.buttons[1].setVisible(not opened)
        self.buttons[2].setVisible(opened)

    def fit_image(self):
        pass

    def actual_size(self):
        pass
