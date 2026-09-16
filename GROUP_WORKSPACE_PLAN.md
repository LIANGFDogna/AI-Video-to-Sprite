# Phase 2A — Group-Centric Project Library

基线20260915-path-memory-ui-audit（191 tests）；目标build 20260916-group-workspace。

## 范围与规则
Project→显式创建/选择Group→导入多个Source→多个Animation→多个Sheet→Group导出。无Group/Project Root不接受媒体，包括拖放。旧有内容工程迁移到Imported Animations逻辑容器，空工程不自动建立Group。项目共享Character Reference及Profile保持，Group.character_id预留。已有Sheet作为原样资源预览/导出，不猜测其网格/FPS，不伪造动画帧或Root数据。

## 方案与三角色审查
方案A每Group一个Project副本会重复共享Reference、难以跨Group关系；方案B把Group当唯一Animation违背多资源；采用C：项目级Library保存Group/Resource UUID关系，复用现有Animation参数快照和animation_id缓存。
架构：Library纯数据层；Workspace控制器协调UI，不把文件树塞进处理算法；GroupExport只读既有最终缓存。数据：资源所有权用group_id，素材引用用source_id，生成Sheet用animation_id；显示名只在导出时sanitize；UI状态不改变图片。工程：所有任务捕获project/group/animation身份，完成时合并所属动画快照；只有仍选中同一上下文才更新中央。导入/保存等事务单独保护，取消不写路径。

## 原子模块与顺序
1. models/project_library.py：UUID树、资源类型、多动画所有权、计数/状态、UIState、CRUD/移动/去重/迁移验证。扩展Project序列化和快照，但不改任何像素参数/签名。
2. ui/library_controller.py + workspace cache：只读切换、每Group/Animation状态、明确后台任务身份与迟到结果隔离、保留现有参数/撤销。
3. ui/project_library.py + StartPage/MainWindow：常驻左树、搜索、Add菜单/上下文菜单、重命名/移动/重排/撤销、Group媒体拖放；收口重复入口。源节点只显示资料，Sheet节点只读预览。
4. SpriteSheet资源导入：统一FileDialog/独立用途、保留源文件、RGBA信息与预览，多个资源共存。
5. core/group_export.py + ui/group_export_dialog.py：选中Group/批量、就绪默认选中、空组警告可选、树路径/平铺、安全名称与无覆盖事务。缓存缺失提示显式构建，不自动处理。
6. 旧测试适配新必需Group前置条件（保留算法断言），新增模型/导出/UI/任务竞态/不重处理/重开测试；全量＋真实125/150%＋冻结完整验收；更新文档、发布正式dist。

## 切换与任务
缓存只读恢复：暂停旧播放、保存UIState、快照当前Animation、选择目标UUID、清空旧视图、读已有manifest/预览、恢复Frame/Zoom/Scroll/Tab/预览参数。不调用Decode/Key/ensure/build；缺失缓存显示待处理。
后台任务携带不可变TaskContext(project_id,group_id,animation_id)。可切换的处理结果先归档到对应Animation，不能应用旧success闭包到当前其他Group。单处理worker继续复用，浏览其他Group可用；不在本轮扩展并行重处理队列。
Library命令历史与动画编辑历史按用户命令顺序路由Undo/Redo；资源删除只移除关系，外部文件永不删除；含内容Group只允许移到父Group或取消，顶层无父Group需先手动移动。

## 风险/验证
状态类：旧_loaded重置Frame、自动prepare/build和过期preview回调；用明确restore标志/身份/revision隔离，测试快速Group切换与后台Key。
数据类：save-as缓存迁移、跨父同名、source与animation所有权、共享Reference；测试往返和哈希不变。
文件类：sanitize后碰撞、目录穿越、已存在输出、取消；预先规划完整路径、碰撞唯一名、只写新输出、不覆盖。
原入口规则被本轮显式Group规则取代。原PathMemory仍保留，新增sprite_sheet_import/group_export独立键。

## 保护基线（以下旧算法文件不得改动）
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
- `app/models/timeline_edit.py` 3547c421c925da083ed854b7c5b8605448f47451f482126b14ebe2f15f8f60ed
