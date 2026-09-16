from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from app.i18n import t


class StartPage(QWidget):
    def __init__(self, window):
        super().__init__();self.window=window
        layout=QVBoxLayout(self);layout.setContentsMargins(35,30,35,30);layout.addStretch()
        self.title=QLabel();self.title.setObjectName('panelTitle');self.title.setWordWrap(True);layout.addWidget(self.title)
        self.hint=QLabel();self.hint.setWordWrap(True);layout.addWidget(self.hint);self.buttons=[]
        for label,callback in [('New Project',window.new_project),('Open Project',window.open_project),
            ('Create first Group',lambda:window.library_controller.new_group()),
            ('Add Media',lambda:window.library_panel.menu.exec(window.start_page.buttons[3].mapToGlobal(window.start_page.buttons[3].rect().bottomLeft())))]:
            button=QPushButton(t(label));button.setAutoDefault(False);button.clicked.connect(callback);layout.addWidget(button);self.buttons.append(button)
        self.buttons[0].setObjectName('primary');self.buttons[2].setObjectName('primary');self.buttons[3].setObjectName('primary');layout.addStretch()
    def update_project(self,project,opened):
        group=project.library.groups.get(project.current_group_id)
        self.title.setText(group.name if group else t('Project: {name}',name=project.project_name) if opened else t('AI VIDEO  /  SPRITE'))
        self.hint.setText(t('This Group is empty. Add video, frames or a Sprite Sheet.') if group else t('Create and select a Group before importing.') if opened else t('Create or open a project to begin.'))
        self.buttons[0].setVisible(not opened);self.buttons[1].setVisible(not opened)
        self.buttons[2].setVisible(opened and not group);self.buttons[3].setVisible(bool(group))
    def fit_image(self):pass
    def actual_size(self):pass
