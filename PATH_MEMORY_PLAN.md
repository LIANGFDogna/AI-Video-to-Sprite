# Path Memory / UI Audit 2026-09-15

本轮只改文件对话框、机器设置、默认工作区与UI按钮行为；不开发Library/Tree/Animation Set，不修改像素/Reference/Offset/Canvas/Key/Root/Motion算法。

## 已接受修正版
- 默认工作区优先 E:/AI Video to Sprite/work，再D盘同路径，再C盘同路径；不能创建时继续回退，最后Home。启动尝试创建，失败记日志且不退出。
- 新建父目录可输入/选择任意有效目录。优先上次成功创建项目的父目录，失效直接回默认Work，再Home；不使用导入/导出/last_location作为新建默认。
- 普通对话框：用途历史（失效逐级父目录）→last_location→当前项目目录→Work→Home。Application Directory不作为隐式默认；显式选择程序目录仍是用户自由。
- 只有成功导入/打开/保存/导出更新用途与last_location；取消/失败不记。选择新建父目录不记project_create，真正创建成功才记。

## 原子模块
1. utils/app_settings + path_memory：复用现有app_settings.json，原子合并写，language与path_state互不覆盖。服务不依赖Project或Qt。
2. ui/dialogs + folder_picker：统一purpose/context，非原生Qt，动态Work/CurrentProject/LastLocation/Home/Computer，取消零写入。
3. MainWindow成功回调接入全部操作和素材重定位，SaveAs可用；NewProject滚动表单+固定底栏+实时完整路径+已有项目打开。
4. UI Audit：源码构造/连接/快捷键清单和真实窗口状态/取消/Enter/Esc/重复触发检查；修复明确失效项。
5. 中英/100/125/150%与小屏逻辑尺寸/中文空格长路径/跨进程记忆；完整测试→新候选→dist实际启动验证。

## 根因与选择（三角色审查）
路径类：空路径QFileDialog默认cwd，导致进入dist；NewProject硬编码Documents；语言保存覆盖整个settings对象。
UI类：新建窗口无滚动区，动作快捷键独立于按钮enabled，部分对话框按钮默认Enter可触发提交。
方案A逐入口增加变量：改动小但重复且易串路径；方案B仅保存Qt窗口state：可恢复浏览但无业务成功语义；方案C统一机器设置服务+成功回调：边界清晰、可测试，采用C。
架构审查：utils不反向依赖UI，现有文件/文件夹组件复用；数据审查：new_project parent/文件parent/导出parent单位分别明确；工程审查：配置读写失败不崩溃，取消和异常必须覆测，冻结程序独立进程证明重启保持。

## 原FileDialog业务调用点（10处）
main_window: _switch_animation缺失序列/视频2处；choose_video/choose_sequence2处；save_project/open_project2处；open_project缺失序列/视频2处；choose_export1处。new_project_dialog.choose_directory1处。统一组件内部Qt构造与FolderPicker分发不计业务调用。
不存在独立单图片导入/单帧PNG保存/视频预览文件导出/Reference另选图片入口；现有透明PNG经序列入口，Reference读取已有动画，Preview Export回调共用choose_export。保留image_import/png_export等扩展key，不虚构功能。

## 算法保护基线
- `app/core/__init__.py` f3732f8f427d049d88996af3ee289aecda81ad0679de745845302003210c4496
- `app/core/alignment.py` 981b819c3c787832ef0b4a028791bb98e8b049bb4251aa2c2816385cc274e6c4
- `app/core/alpha_utils.py` 5e31d3811bf833233cde6060c385831eb6b06895ea5915963c4b50a49216958e
- `app/core/animation_transform.py` c0594fa6ae1cc50830cdb87488b817302043e4f322e0a1da7c57551a884f7d41
- `app/core/canvas_fit.py` 0e641bc113e2ab7c4a253eedd8322e80399067e92490557eb69ba6cce97b1dc3
- `app/core/canvas_normalizer.py` e60d27093c67a9f23953d3b5c0697669f2178425f159469ac58a981235679369
- `app/core/character_reference.py` d45542d6c2dc15350d49433ba68044bf10ed49346b997c8c121a1723267f6606
- `app/core/character_space.py` 198666ae7ea39b691777af35c7da0fc095f866ace806db427ce9fab91f749a9b
- `app/core/chroma_key.py` cc8625e0c2a18d522321608e1acbcbc99970fd4f5790a80c882a48f3283b71e7
- `app/core/final_canvas.py` b531c3c7f8844629591023cf751e1f8675f3925db2e9222510bfc1e8db9a4d19
- `app/core/final_frame_provider.py` c3cac2e056808e9401475b83cc70813bfda63435ef7effe5f21e8c1c1f463f3c
- `app/core/frame_sequence.py` 7f55239ee29045873969fe8d9431957f1323a8713c9de5082d9c088d55462fe3
- `app/core/ground_detection.py` d8e44611aaa7ed722d1e30c61298c1838d6757871e36b28ad471b6a3151cd6fc
- `app/core/motion.py` fc7b60a422a9a3fd3368b42cccf3fe96e947c6365c43690e102a2a30d35f35dd
- `app/core/pipeline.py` f3f40bbe60d253c81eddccb8f427bb697c1b633ca1667d4f71c14d2969895711
- `app/core/project_workspace.py` c910578c5e1861b27bf438d5499532c8d9186acafff43eeea36c03fa614363fb
- `app/core/root_tracker.py` 2eeb9dc1af7276b30d679ba25880ba332700ae6c74929e58ed3839c7f1855964
- `app/core/sprite_canvas.py` 685b6e608bdd6dc179944c465993da5176ccfdeba7fd906c1b4e455a4368d2f2
- `app/core/sprite_sheet.py` e2aa1a32edaf45dde86351188c45ef17e1c237cbaceb0664b4e6dfdeca259e41
- `app/core/timeline_renderer.py` c8747e934fcef8e60b97defa4b8cb70fd3070656845a45a28685ff4db84b687f
- `app/core/video_decoder.py` 9a9934a327db16213def8071303355f218128fdc555f33ba342f6a6fbb8d71d8
- `app/exporters/__init__.py` e253748bacae215bdf9fa2578c943bcd58e26799855f868180ffa9650c188fea
- `app/exporters/godot_exporter.py` ee240523bf73a8f0607fa61de3e7349458d537944addac91d0560588d07fe0cf
- `app/exporters/image_exporter.py` a7eb47af125e59c68273513efb92b3c1591b2f8c682308b840e964295bfec3dc
- `app/exporters/root_motion_exporter.py` 65e192d35362dfbd84814787422af697b36621ec44c17ae1aafa9ba9a578914b
- `app/models/__init__.py` c5f1a6cb409ee7d9043855b0ef7f8b59553c5bec57f38c5aedcacd301110dbb3
- `app/models/character_profile.py` 920ea7bb4c042d4068e8d27406bdd9a4a0d5dac5c77562e561a2f24d9833904b
- `app/models/character_reference.py` f37fc79f1acd69da5745d9673fefda9a8c945a4acef19181df0b4ee04e3c618a
- `app/models/frame_data.py` aaeb3ddcec6c9b16bac28627c221d3970b974ba223fec5c5987fb4244b9ff042
- `app/models/project.py` a353b0a8bbe101713409c90fb24e21f424b9273b0376b1d59a65867d263a97c8
- `app/models/timeline_edit.py` 3547c421c925da083ed854b7c5b8605448f47451f482126b14ebe2f15f8f60ed
