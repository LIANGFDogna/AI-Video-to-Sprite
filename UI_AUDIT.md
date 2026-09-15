# UI / Path Audit — 20260915-path-memory-ui-audit

范围：现有所有窗口、文件入口、按钮/Action/Shortcut的源码清单和绑定检查；真实窗口状态与关键业务行为测试。不新增Library/Tree/Animation Set，不修改31个处理算法文件。

## 路径约定

PathMemoryService在app/utils/path_memory.py；AppSettings在app/utils/app_settings.py。机器配置默认%LOCALAPPDATA%/AI Video to Sprite/app_settings.json，可由测试环境变量AIVSPRITE_SETTINGS隔离。语言与path_state合并原子写入。普通操作purpose→last_location→当前工程→Work→Home；失效用途历史逐级祖先。新建例外：只用成功创建父目录，失效直接Work。Work默认E盘同名目录，依次D、C，最后Home。任何有效可写目录/NAS均可主动选择，没有锁定路径。

## 所有10个业务文件窗口调用

保存/另存共用save_project；单图PNG没有独立导入页，通过序列文件夹；RGBA导出使用png_export，最终序列用frame_export，Sheet用sprite_sheet_export，Godot bundle用project_export。Preview导出复用choose_export；Reference只读既有动画，没有另选素材入口。image_import/folder_import/generic等保留接口及独立路径测试；没有宣称新增单帧PNG或预览视频文件导出。

|文件:行|调用|
|---|---|
|app/ui/main_window.py:1350|`QFileDialog.getOpenFileName(self, "Import Video", "", "Video (*.mp4 *.mov *.avi *.mkv *.webm)",purpose="video_import")`|
|app/ui/main_window.py:1357|`QFileDialog.getExistingDirectory(self, "Choose an animation frame folder (PNG recommended)", self._project_folder("sequences"), sequence=True,purpose="image_sequence_import")`|
|app/ui/main_window.py:1708|`QFileDialog.getExistingDirectory(self,title,self._project_folder("exports"),purpose=self.export_purpose(kind,godot))`|
|app/ui/main_window.py:719|`QFileDialog.getExistingDirectory(self, "Locate missing sequence folder",purpose="image_sequence_import")`|
|app/ui/main_window.py:1606|`QFileDialog.getSaveFileName(self, "Save Project As" if force_dialog else "Save Project", (self.project_file.name if self.project_file else self.project.project_name or self.project.export_settings.animation_name)+("" if self.project_file else ".aivsprite"), "AI Video to Sprite (*.aivsprite)",purpose="project_save")`|
|app/ui/main_window.py:1648|`QFileDialog.getOpenFileName(self, "Open Project", "", "AI Video to Sprite (*.aivsprite)",purpose="project_open")`|
|app/ui/main_window.py:1660|`QFileDialog.getExistingDirectory(self, "Locate missing sequence folder",purpose="image_sequence_import")`|
|app/ui/main_window.py:726|`QFileDialog.getOpenFileName(self, "Locate missing source video", "", "Video (*.mp4 *.mov *.avi *.mkv *.webm)",purpose="video_import")`|
|app/ui/main_window.py:1666|`QFileDialog.getOpenFileName(self, "Locate missing source video", "", "Video (*.mp4 *.mov *.avi *.mkv *.webm)",purpose="video_import")`|
|app/ui/new_project_dialog.py:160|`FileDialog.getExistingDirectory(self, "Choose project directory", self.directory.text(),purpose="project_create")`|

## 窗口行为与回归

|窗口族|验证方式与结果|
|---|---|
|主窗口/Import/Key/Sprite/Export|空项目/工作中按钮和快捷键状态；导入、保存、另存、打开、源重定位业务接入；旧视频/直通/画布全流程测试|
|New Project|字段可编辑、模板/画布/FPS、实时完整位置、固定底部、Enter不误提交、Esc取消、重复提交保护、目录冲突打开/改名、父目录成功记忆|
|FileDialog / FolderPicker|非原生Qt、用途初始目录、动态侧栏、Computer/返回Work、完整导航文字、取消不记录、中文/空格/长路径；原folder测试覆盖单选/双击、导航、新建、失效路径、深浅palette|
|Sequence Import|取消不记录，确认后导入成功才记录；选项在提交时读取，无需单独clicked回调；原RGBA8/16及混尺寸测试保留|
|Edit / Timeline / Curves|源码命令与快捷键清单；旧editor UI及冻结三流程覆盖拖动、偏移、删/复制/贴/倒放/重定时、曲线、关键帧、多轨、撤销重做与导出一致|
|Character Reference / Character Space|Enter不误保存、Esc取消；原参考及Profile测试、冻结125/150%校准/共轴/Offset/Ghost/Undo/保存重开|
|Animation Preview / Warnings|播放快捷键、失效预览禁止播放、逐帧/FPS/Loop/洋葱/残影/LoopSeam原测试；警告菜单action跳帧源码连接检查；导出委托同一入口|
|导出完成提示|Open Animation Preview与Close绑定，原冻结导出流程；导出目录通过独立用途记录|
|Diagnostics / MessageBox / Color / New Folder|实际创建、记录控件绑定、Esc关闭；确认框显式No默认、Enter返回No；未保存确认保留Save/Discard/Cancel；颜色/新目录取消无副作用|

普通操作按钮已关闭autoDefault。主窗口文件Action与对应按钮同启停；FrameEditor命令和Undo/Redo尊重interaction_busy。快捷键响应已有测试与冻结编辑流程验证。未发现源码中完全未接业务处理器的产品按钮；有6个无需直接信号连接的选项（序列模式radio、保留首/尾/关键帧、Loop），其值由提交/播放操作读取。没有将它们误当“失效按钮”。

## 修复项目

- 空默认路径导致QFileDialog继承cwd/dist；改为统一内容目录解析。
- NewProject默认Documents、父目录不记忆、窗口过高；改为可编辑的记忆父目录及滚动表单/固定底栏。
- 语言保存覆盖整份JSON；改为原子合并。
- 缺失素材重定位、导出与另存没有独立成功记忆；补齐回调及Ctrl+Shift+S另存入口。
- 部分空项目/忙状态仍能通过快捷键触发；统一按钮/Action状态和命令守卫。
- 对话框Enter可能触发提交、序列确认可重复提交；关闭autoDefault并设置提交守卫。
- Computer模式无目录时仍可新建/提示扫描，空路径意外使用cwd；禁用不可用动作、返回Work恢复，空路径明确拒绝。
- Qt恢复旧sidebar造成动态目录累积；只保留系统根并每次重建当前动态入口。
- QFileDialog深色导航图标不清楚、侧栏窄、文字按钮变省略号；文字导航固定足够宽度，侧栏最低宽度，完整路径Tooltip。
- 直通模式下Profile分支又启用Motion控件；禁用条件保留直通优先，不触动处理算法。

## 计数与证据边界

scripts/audit_ui.py得到120个控件/Action构造或帮助函数调用点、149处信号连接和10个业务FileDialog入口；已排除event.button、获取已有button及重复addAction注册。帮助函数会实例化多个控件，数字不是产品按钮总数。

原生100/125%真实审查各有19个窗口/状态、438次Button/Action/Shortcut观察；去除主窗口空/就绪重复状态为286条控件实例记录。记录包含Qt内部控件、连接数、enabled、tooltip和autoDefault。不是声称286个按钮都单独进行了破坏性点击。交互证据来自本轮安全导航/创建/导入/保存/导出/取消流程和完整191项回归、既有冻结编辑/Root/Reference流程；具体源声明完整列于下表。

100/125/150%验证实际DPR；窗口分辨率矩阵使用对应逻辑尺寸验证固定底栏，不修改Windows系统主题或屏幕配置。中文/英文通过。E/D/C缺失/不可写回退通过注入的目录失败单测，未卸载真实磁盘。NAS路径不限制，但未连接外部NAS做硬件验收；失效网络路径的系统探测速度仍受Windows网络超时影响。多进程同时保存配置为原子替换但没有进程锁，同一时间并发写同一用途时最后写入者生效。

## 完整控件构造/声明清单

|位置|声明|
|---|---|
|app/ui/animation_preview.py:106|`self.button("Play", self.toggle_play)`|
|app/ui/animation_preview.py:118|`self.button("Warnings", self.show_warnings)`|
|app/ui/animation_preview.py:124|`self.button("Export", self.export_requested.emit)`|
|app/ui/animation_preview.py:126|`self.button("Open Export Folder", self.open_folder)`|
|app/ui/animation_preview.py:138|`QPushButton(t(text))`|
|app/ui/animation_preview.py:108|`self.button("Next Frame", lambda: self.step(1))`|
|app/ui/animation_preview.py:109|`self.button("Last Frame", lambda: self.select(len(provider)-1))`|
|app/ui/animation_preview.py:123|`self.button("Back to Edit", self.close)`|
|app/ui/animation_preview.py:132|`QShortcut(QKeySequence(key), self)`|
|app/ui/animation_preview.py:63|`self.button(label, lambda checked=False, z=zoom: self.zoom(z))`|
|app/ui/animation_preview.py:105|`self.button(label, callback)`|
|app/ui/animation_preview.py:292|`menu.addAction(t("Frame {frame}: {warnings}", frame=f.index, warnings=" · ".join(t(w) for w in f.warnings)))`|
|app/ui/character_reference_dialog.py:94|`QPushButton(t('Fit'))`|
|app/ui/character_reference_dialog.py:95|`QPushButton(t('100%'))`|
|app/ui/character_reference_dialog.py:96|`QPushButton(t('Cancel'))`|
|app/ui/character_reference_dialog.py:97|`QPushButton(t('Save Character Reference'))`|
|app/ui/character_space_editor.py:114|`QPushButton(t("Set Canonical Root · X snaps to Y Axis"))`|
|app/ui/character_space_editor.py:142|`QPushButton(t("Set as Character Reference") if self.calibrating else t("Save Reference Box"))`|
|app/ui/character_space_editor.py:146|`QPushButton(t("Cancel"))`|
|app/ui/controls.py:121|`QPushButton(t(label))`|
|app/ui/folder_picker.py:68|`self._button("← Back", lambda: self.go_history(-1))`|
|app/ui/folder_picker.py:69|`self._button("→ Forward", lambda: self.go_history(1))`|
|app/ui/folder_picker.py:70|`self._button("↑ Parent folder", self.go_up)`|
|app/ui/folder_picker.py:71|`self._button("New folder", self.new_folder)`|
|app/ui/folder_picker.py:129|`self._button("Select this folder", self.select_folder)`|
|app/ui/folder_picker.py:131|`self._button("Cancel", self.reject)`|
|app/ui/folder_picker.py:153|`QPushButton(t(label))`|
|app/ui/frame_editor.py:101|`self.button('Play',self.toggle_play)`|
|app/ui/frame_editor.py:137|`self.button('Set Character Reference',host.open_character_reference,True)`|
|app/ui/frame_editor.py:202|`self.button('Apply Frame Count',lambda:self.retime('count'),True)`|
|app/ui/frame_editor.py:249|`QPushButton(t(label))`|
|app/ui/frame_editor.py:50|`self.button('Prepare Editor', host.prepare_editor, True)`|
|app/ui/frame_editor.py:51|`self.button('Build Sprite Sheet', host.build_sprites)`|
|app/ui/frame_editor.py:52|`self.button('Undo', host.undo_edit)`|
|app/ui/frame_editor.py:53|`self.button('Redo', host.redo_edit)`|
|app/ui/frame_editor.py:84|`self.button('Insert Selected Sources', self.insert_sources)`|
|app/ui/frame_editor.py:103|`self.button('Stop',lambda:(self.stop(),self.select(0)))`|
|app/ui/frame_editor.py:111|`self.button('Fit', self.canvas.fit_image)`|
|app/ui/frame_editor.py:112|`self.button('100%',self.canvas.actual_size)`|
|app/ui/frame_editor.py:123|`self.button('−',lambda:self.timeline.zoom(1/1.2))`|
|app/ui/frame_editor.py:124|`self.button('+',lambda:self.timeline.zoom(1.2))`|
|app/ui/frame_editor.py:156|`self.button('Apply Animation Offset',lambda:host.set_animation_offset(self.animation_x.value(),self.animation_y.value()))`|
|app/ui/frame_editor.py:157|`self.button('Reset Animation Offset',lambda:host.set_animation_offset(0,0))`|
|app/ui/frame_editor.py:175|`self.button('Apply Transform to Selection',self.apply_transform)`|
|app/ui/frame_editor.py:176|`self.button('Add XY to Selection',lambda:self.command('Offset Frames',lambda e:e.offset(self.selection(),self.x.value(),self.y.value())))`|
|app/ui/frame_editor.py:177|`self.button('Paste at End',lambda:self.paste(True))`|
|app/ui/frame_editor.py:178|`self.button('Mark / Unmark Keyframes',self.mark_keys)`|
|app/ui/frame_editor.py:204|`self.button('Apply Speed',lambda:self.retime('speed'))`|
|app/ui/frame_editor.py:205|`self.button('Apply Duration / Curve',lambda:self.retime('duration'))`|
|app/ui/frame_editor.py:206|`self.button('Interpolate Selected Transforms',lambda:self.command('Interpolate Transforms',lambda e:e.interpolate(self.selection(),self.curve.currentData(),self.curve_editor.controls)))`|
|app/ui/frame_editor.py:244|`QShortcut(QKeySequence(key),self.timeline)`|
|app/ui/frame_editor.py:100|`self.button(label,callback)`|
|app/ui/frame_editor.py:122|`self.button(name,lambda checked=False,k=key:self.action(k))`|
|app/ui/main_window.py:117|`self._button("Import Video", self.choose_video)`|
|app/ui/main_window.py:118|`self._button("New Project", self.new_project)`|
|app/ui/main_window.py:119|`self._button("Import Frame Sequence", self.choose_sequence)`|
|app/ui/main_window.py:120|`self._button("Open Project", self.open_project)`|
|app/ui/main_window.py:121|`self._button("Save Project", self.save_project)`|
|app/ui/main_window.py:122|`self._button("Export", lambda: self.steps.setCurrentIndex(4), primary=True)`|
|app/ui/main_window.py:125|`self._button("Undo", self.undo_edit)`|
|app/ui/main_window.py:126|`self._button("Redo", self.redo_edit)`|
|app/ui/main_window.py:223|`self._button("Preview Animation", lambda: self.open_animation_preview(), True)`|
|app/ui/main_window.py:267|`self._button("▶ Play", self.toggle_play)`|
|app/ui/main_window.py:280|`self._button("Extract / Process", self.process_key, primary=True)`|
|app/ui/main_window.py:281|`self._button("Analyze / Build", self.build_sprites, primary=True)`|
|app/ui/main_window.py:298|`self._button("Cancel", self.cancel_work)`|
|app/ui/main_window.py:420|`QPushButton(t(text))`|
|app/ui/main_window.py:434|`p.button("import", "Import Video", True)`|
|app/ui/main_window.py:435|`p.button("import_sequence", "Import Frame Sequence", True)`|
|app/ui/main_window.py:437|`p.button("open", "Open .aivsprite Project")`|
|app/ui/main_window.py:441|`p.button("color", "Green Color")`|
|app/ui/main_window.py:442|`p.button("edit_keyed", "Edit Keyed Frames", True)`|
|app/ui/main_window.py:444|`p.button("full_processing", "Continue Root / Motion Processing")`|
|app/ui/main_window.py:445|`p.button("keyed_passthrough", "Build Sprites Directly", True)`|
|app/ui/main_window.py:448|`p.button("eyedropper", "Eyedropper · click background")`|
|app/ui/main_window.py:455|`p.button("process", "Extract / Process", True)`|
|app/ui/main_window.py:456|`p.button("export_rgba", "Export source-size RGBA PNGs")`|
|app/ui/main_window.py:459|`p.button("full_processing", "Enable Root / Motion / Align", True)`|
|app/ui/main_window.py:461|`p.button("character_space", "Character Space / Reference Box", True)`|
|app/ui/main_window.py:464|`p.button("delete_root", "Delete Current Correction")`|
|app/ui/main_window.py:468|`p.button("body_roi", "Define Body ROI")`|
|app/ui/main_window.py:469|`p.button("clear_body_roi", "Reset Body ROI")`|
|app/ui/main_window.py:471|`p.button("build", "Track / Analyze / Build", True)`|
|app/ui/main_window.py:484|`p.button("ground_roi", "Define Ground ROI")`|
|app/ui/main_window.py:485|`p.button("clear_ground_roi", "Reset Ground ROI")`|
|app/ui/main_window.py:486|`p.button("build", "Track / Analyze / Build", True)`|
|app/ui/main_window.py:494|`p.button("build", "Analyze / Build", True)`|
|app/ui/main_window.py:499|`p.button("full_processing", "Enable Root / Motion / Align")`|
|app/ui/main_window.py:503|`p.button("keyed_passthrough", "Build Sprites Directly", True)`|
|app/ui/main_window.py:504|`p.button("full_processing", "Continue Root / Motion Processing")`|
|app/ui/main_window.py:517|`p.button("normalize_preset", "512×512 (1/3)")`|
|app/ui/main_window.py:528|`p.button("build", "Analyze / Build Sheet", True)`|
|app/ui/main_window.py:529|`p.button("edit", "Edit Animation")`|
|app/ui/main_window.py:530|`p.button("preview", "Preview Animation")`|
|app/ui/main_window.py:536|`p.button("preview", "Preview Export")`|
|app/ui/main_window.py:537|`p.button("export_all", "Export for Godot · PNG + JSON + Frames", True)`|
|app/ui/main_window.py:538|`p.button("export_sheet", "Export Sprite Sheet")`|
|app/ui/main_window.py:539|`p.button("export_frames", "Export Individual Frames")`|
|app/ui/main_window.py:540|`p.button("export_rgba", "Export Source-size RGBA Frames")`|
|app/ui/main_window.py:541|`p.button("save", "Save Project")`|
|app/ui/main_window.py:542|`p.button("save_as", "Save Project As")`|
|app/ui/main_window.py:129|`self._button("Diagnostics", self.show_diagnostics)`|
|app/ui/main_window.py:228|`self._button("Fit", lambda: self.active_view().fit_image())`|
|app/ui/main_window.py:229|`self._button("100%", lambda: self.active_view().actual_size())`|
|app/ui/main_window.py:268|`self._button("‹", lambda: self.select_frame(self.current_frame - 1))`|
|app/ui/main_window.py:270|`self._button("›", lambda: self.select_frame(self.current_frame + 1))`|
|app/ui/main_window.py:304|`QAction(self)`|
|app/ui/main_window.py:307|`QAction(self)`|
|app/ui/main_window.py:908|`self._button("Open Animation Preview", open_review, True)`|
|app/ui/main_window.py:909|`self._button("Close", dialog.close)`|
|app/ui/main_window.py:1752|`self._button("Refresh", refresh)`|
|app/ui/main_window.py:463|`p.button("root", "Set / Correct Root · click subject", True)`|
|app/ui/new_project_dialog.py:40|`QPushButton(t("Choose project directory"))`|
|app/ui/new_project_dialog.py:89|`QPushButton(t("Use existing empty directory"))`|
|app/ui/new_project_dialog.py:93|`QPushButton(t("Open existing project"))`|
|app/ui/new_project_dialog.py:95|`QPushButton(t("Change project name"))`|
|app/ui/new_project_dialog.py:99|`QPushButton(t("Create Project"))`|
|app/ui/new_project_dialog.py:102|`QPushButton(t("Cancel"))`|
|app/ui/sequence_import_dialog.py:76|`QDialogButtonBox(QDialogButtonBox.StandardButton.Ok / QDialogButtonBox.StandardButton.Cancel)`|
|app/ui/start_page.py:22|`QPushButton(t(label))`|
