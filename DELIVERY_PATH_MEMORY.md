# 本轮20项交付报告

正式发布已完成，实际验证程序：`E:\AI Video to Sprite\dist\AI Video to Sprite\AI Video to Sprite.exe`。

1. Path Memory Service：`app/utils/path_memory.py`，机器配置读写：`app/utils/app_settings.py`。
2. Settings：`%LOCALAPPDATA%/AI Video to Sprite/app_settings.json`，与语言设置合并保存；测试使用独立配置。
3. WORK_ROOT默认：`E:/AI Video to Sprite/work`；不可用依次D盘同路径、C盘同路径，最后Home。启动尝试创建。
4. New Project：上次成功创建的父目录优先；失效直接默认Work。输入框可编辑，保留选择按钮，支持任意有效可写目录。
5. Import Video：成功导入后记video_import，记源文件父目录；取消/解码失败不更新。
6. Image Sequence：确认并成功导入后记image_sequence_import，与视频独立。
7. Export：Sheet、最终帧、源RGBA、Godot bundle分别记sprite_sheet_export/frame_export/png_export/project_export；只在成功导出后记父目录。
8. Cancel：不修改历史，实际文件/目录/序列确认取消与失败分支均有测试。
9. 左侧快捷入口：Work、Current Project、Last Location、Home/用户、Computer；每次刷新，不累积旧项目。
10. 10个业务FileDialog调用点全部接入统一服务；UI_AUDIT.md含完整位置。
11. 120个静态控件/Action声明点、149处信号连接；19个窗口/状态实测438条观察，去除主窗口重复状态后286条实例记录，含Qt内部控件，不等于286个产品功能全部单独点击。
12. 修复：空素材/忙状态与快捷键不一致、缺失另存入口、对话框Enter误提交/重复提交风险、Computer无目录状态、直通Root/Motion控件误启用、导航文字省略、动态侧栏累积等。
13. dist误用：确认原空路径QFileDialog可回落cwd/dist，现统一从服务获取内容目录，安装位置不作隐式默认。
14. 中文路径：视频、序列、保存、打开、导出、重启通过。
15. 空格路径及275字符以上深层目录：通过；不限制用户选择NAS，但没有外部NAS硬件实测。
16. DPI：正式dist实际DPR1.0、1.25、1.5均通过，含中文和英文；1366×768、1920×1080、2560×1440等效逻辑尺寸下新建底部按钮可见。
17. 全量191项通过，60.89秒；705条中英翻译检查通过；31个core/models/exporters文件哈希完全未变。
18. dist EXE修改时间：`2026-09-16T00:05:39`；发布记录：`2026-09-16T06:35:35+08:00`。
19. Build identifier：`20260915-path-memory-ui-audit`；保留v0.4.0与旧工程兼容。
20. 实际启动验证：`E:\AI Video to Sprite\dist\AI Video to Sprite\AI Video to Sprite.exe`；SHA256 `B61D423A4507E2AC2D16FC5C3ECE3AB76620DD01CC5476DB43B96676F19CEEB8`。每档DPI先走完整业务再关闭，用新进程验证持久化。

文档README/ARCHITECTURE/TASKS/VALIDATION/UI_AUDIT已同步到正式dist。当前功能继续包含原视频/序列/中心裁补/抠像/Root/Motion/编辑器/预览/导出；本轮未增加Library、Tree或Animation Set。
