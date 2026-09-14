# File structure

项目画布新增：`app/core/canvas_fit.py`、`app/ui/canvas_fit_info.py`、`app/project_canvas_smoke.py`、`tests/test_project_canvas.py`、`tests/test_project_canvas_ui.py`、`PROJECT_CANVAS_PLAN.md`。项目配置、workspace、pipeline、现有新建/导入/主界面和Godot出口接入这一层。

V0.4 视频抠像直通新增：

```text
app/keyed_passthrough_smoke.py
tests/test_keyed_passthrough.py
tests/test_keyed_passthrough_ui.py
examples/keyed_passthrough_56.aivsprite
examples/keyed_passthrough_56.mp4
KEYED_PASSTHROUGH_PLAN.md
```

模型、通用直通管线和现有主窗口中接入模式；复用 FinalFrameProvider，没有独立预览/导出图像算法。

```
app/main.py
app/models/{project,frame_data}.py
app/core/{video_decoder,chroma_key,alpha_utils,root_tracker,alignment,sprite_canvas,sprite_sheet,pipeline}.py
app/exporters/{image_exporter,godot_exporter}.py
app/ui/{main_window,video_viewer,timeline,anchor_editor,sprite_preview,worker,controls}.py
app/utils/{ffmpeg,paths,logging,cache}.py
tests/
scripts/
setup.ps1 / run.bat / build.ps1
```

v0.2 新增：

```
app/core/{motion,ground_detection,canvas_normalizer,final_canvas,final_frame_provider}.py
app/exporters/root_motion_exporter.py
app/ui/{motion_editor,animation_preview,dialogs}.py
app/i18n/{translator.py,__init__.py,zh_CN.json,en_US.json}
app/preview_smoke.py
scripts/{check_i18n,smoke_upgrade}.py
tests/{test_motion_normalize,test_upgrade_integration,test_i18n}.py
examples/{normalized_512.aivsprite,normalized_512.mp4}
docs/{ui-preview,animation-preview,motion-curves}.png
```

v0.3 新增：

```
app/models/character_profile.py
app/core/character_space.py
app/ui/{character_space_editor,character_overlay}.py
scripts/{smoke_character_space,make_character_example}.py
tests/test_character_space.py
examples/character_profile.aivsprite
CHARACTER_SPACE_PLAN.md
```

v0.4 新增：

```
app/core/frame_sequence.py
app/ui/sequence_import_dialog.py
scripts/{sequence_demo,smoke_sequence}.py
tests/test_frame_sequence.py
examples/sequence_idle.aivsprite
examples/sequence_idle/0000.png ... 0021.png
SEQUENCE_INPUT_PLAN.md
```

V0.4 本轮新增：

```
app/utils/rgba_image.py
app/core/project_workspace.py
app/ui/{folder_picker,new_project_dialog,start_page,sequence_info}.py
app/workspace_smoke.py
scripts/smoke_workspace.py
tests/{test_sequence_bit_depth,test_project_workspace,test_workspace_ui}.py
V04_WORKSPACE_PLAN.md
```
