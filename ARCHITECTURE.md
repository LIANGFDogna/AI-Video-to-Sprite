# Architecture · v0.4

## 机器路径设置与统一窗口（2026-09-16）

`utils/app_settings.py`复用既有机器配置，读UTF-8/BOM并容忍损坏内容；写入使用同目录唯一临时文件、fsync及原子replace。`TranslationManager.save_language`合并字段，避免语言保存覆盖路径历史。`utils/path_memory.py`的`PathMemoryService`不依赖Qt或Project，保存`path_state(version=1,work_root,last_location,recent_paths)`。

用途键：project_create、project_open、project_save、video_import、image_import、image_sequence_import、folder_import、png_export、sprite_sheet_export、frame_export、project_export、generic_open、generic_save、generic_folder。未提供独立UI的用途只预留接口。项目数据只保留其正式源引用，不保存FileDialog浏览历史。

新建优先成功创建的父目录，失效直接Work；其他用途优先自己的有效历史/有效祖先，再全局last_location、当前工程、Work、Home。WORK_ROOT名义默认E:/AI Video to Sprite/work，WORK_CANDIDATES为E→D→C；启动尝试创建，盘不存在或创建失败继续下一项。用户输入/选择的路径不受候选盘限制。应用安装目录仅作为隐式默认的排除条件，不作为默认内容路径；显式选中它仍尊重用户选择。

`ui/dialogs.py`通过`path_context`取得MainWindow服务与当前project_file父目录。全部10个业务FileDialog调用明确purpose。Qt文件窗口设置DontUseNativeDialog，每次重建动态侧栏，过滤Qt恢复的旧动态项目防止累积；保留Computer/Home。目录统一分发FolderPicker，Computer模式无当前目录时禁用选择/新建，返回正常目录时恢复。

提交边界：UI选择→业务导入/打开/保存/导出成功回调→remember→原子设置写入→下次窗口initial。新建目录浏览不记忆，真正创建成功才记父目录。导出记生成bundle的父目录，不记其带时间戳子目录。四类导出分开（Godot项目/Sheet/最终Frames/源RGBA）。Preview导出继续调用同一choose_export。

MainWindow统一忙状态、空素材禁用与文件快捷键状态；编辑器命令尊重interaction_busy。NewProject滚动表单/固定底栏/实时路径/重复提交保护；无覆盖地处理同名工程。Sequence确认只提交一次。普通QDialog的操作按钮关闭autoDefault；MessageBox尊重显式默认，含Cancel/No时默认回避意外提交。直通模式的Root/Motion/Align控件禁用优先于其他状态刷新。

验证分层：服务单测、真实Qt窗口回归、AST调用与信号清单、原生和冻结双进程exercise/restart、实际DPR断言、最后dist再验收。`scripts/verify_path_ui.ps1`验证100/125/150%，125%以英文首启；每次用独立测试settings，避免污染用户配置。处理算法保护哈希见PATH_MEMORY_PLAN.md与build/path-protected-hashes.json。

## Character Reference 第一阶段（2026-09-15）

模型 `models/character_reference.py` 定义两个冻结数据类。`CharacterReference` 为项目唯一：reference_animation_id/reference_frame_index/origin_x/ground_y/project_canvas_width/height/locked；加入 Project.PROJECT_FIELDS，动画快照不复制它，切换动画注入当前唯一参考。`AnimationTransform` 为动画独立offset_x/y，单位项目画布像素；快照与保存重开保留。缺失字段分别迁移为None和零变换，schema_version仍为1。

旧Root是单动画检测/运动轨迹；旧CharacterProfile是固定Scale、CanonicalRoot及对称安全框的自动对齐配置。新Reference只描述用户摆放的坐标轴，不覆盖上述字段、不自动启用其对齐。首次校准UI明确将旧完整处理切换为既有直通，保留其参数与整画布缩放；仅赋值Reference数据不会改变像素处理。

`ui/character_reference_dialog.py` 固定原始keyed pixmap，独立校准草稿允许Ground/YAxis/Origin按轴拖动和键盘微调，屏幕命中阈值除以视图变换换算到项目空间。保存一次性提交锁定模型；正常 `EditorCanvas` 的所有内容拖动只调用整动画Offset命令。旧逐帧编辑由独立拖动范围选择，不创建新的一套逐帧修正数据。

`core/character_reference.py` 通过参考动画ID定位现有keyed缓存。ReferenceSource缓存原始Idle及单个输出尺寸的图像，FrameCache预算48MB，播放不重复读盘。忽略参考动画自己的Offset、时间线和Root自动对齐，也忽略当前动画Offset；缓存缺失可后台一次性重建。`reference_overlay.py` 绘制固定轴，`EditorCanvas`独立ghost图元不跟随当前pixmap位移，原始坐标文本不按DPI缩放数值。辅助图元不进入最终帧。

`core/animation_transform.py` 是统一整动画平移函数。直通模式从已标准化keyed/raw读取，项目像素XY平移、透明裁切后调用既有canvas_normalizer；uint16保留到float32预乘Resize/最终RGBA8。整帧固定变换，不依据Alpha/Root/武器定位。Alpha仅检测非阻塞越界提示，不参与位置和缩放。旧完整流程可在原结果上显式附加按布局比例换算的Offset。

`timeline_renderer` 实时及落盘均调用此函数：有时间线时先整动画变换，再旧实例变换/合成；无时间线但有Offset时构造源帧身份时间映射，不生成frame_overrides。Project.has_final_edits驱动final缓存与输出，解决只修改整动画Offset却未启用时间线的导出路径。零Offset保持旧签名，非零Offset单独进入final_signature，不改变raw/key/align签名。Reference几何不进入图像缓存签名。

MainWindow现有EditHistory覆盖Reference和Offset。undo/redo依据变更字段还原项目Reference，防止其他动画的旧历史快照回滚不相关的项目级参考修改。导出JSON额外记录Reference和AnimationTransform及项目像素单位；final bbox/root/ground依据实际最终渲染更新。

**完全未修改** `core/canvas_fit.py`、`core/canvas_normalizer.py`、`core/frame_sequence.py`、`core/video_decoder.py`，SHA256基线记录于 CHARACTER_REFERENCE_PLAN.md。输入中心裁补与手工角色对齐保持独立。

## 五页编辑器与非破坏性输出层（2026-09-15）

公开导航固定为导入/抠像/编辑/精灵图/导出。MainWindow 只保留旧 ParameterPanel 索引作为内部控件映射；Root/Motion/Align 实际控件重挂到 FrameEditor 对齐侧栏，不再作为三个大页面。EditorCanvas、EditorTimeline、CurveEditor 分别负责画布交互、多轨场景和时间曲线；模型与渲染不依赖 Qt。

`TimelineEdit` 的稳定实例 ID 引用原 `source_index`。每块保存 start/duration/track/keyframe/speed/curve/reversed，frame_overrides 以实例 ID 保存位移、比例与透明度；复制产生新 ID。删除不修改源文件。动画切换保存各自编辑状态，项目画布和 Character Profile 仍项目级唯一。旧 JSON 缺省 enabled=false；schema_version 维持 1。

```text
原素材 → 项目中心 Canvas Fit → Key / 已透明帧
     → 原 Root / Motion / Align 或显式直通 → Normalize / aligned Cell
     → timeline_renderer（取帧 / 实例变换 / 轨道合成 / 时长）
     → FinalFrameProvider → 编辑预览 / Export Review / Sheet / PNG / Godot JSON
```

源 `video.frame_count/tracking_results` 与输出 `final_frames/final_timing` 分离，禁止抽帧后覆盖源索引。compile_timeline 按可见非参考轨的所有时间边界扫描；同轨重叠取起点较晚的块，跨轨按 main→overlay→effects 预乘 Alpha source-over，空区间透明。事件时间四舍五入到 10 位小数，输出限制 100000 帧。

手动偏移为最终 Cell 像素；默认变换逐字节保留 RGB/Alpha，整数平移用直接切片；浮点位移/比例使用现有预乘 warp。Cell 大小固定，不按 Alpha/Root 自动重新居中。最终 bbox 重新检测，Root/Ground 随显式变换，越界仅警告。参考轨只由编辑 UI 临时叠加；不能进入最终 Provider。

Pipeline.ensure_final 在 ensure_aligned 后运行。final.json / final_frames 独立保存；final_signature 包含 align 签名、编辑数据、源 FPS 和循环选项，sheet 签名依赖 final。manifest 原子提交；保存迁移缓存时也清理目标旧 final manifest。原 raw/keyed/aligned 可复用，Root 原始运动不随编辑删除。

FinalFrameProvider 的实时编辑模式深拷贝参数，只从基础 aligned 缓存按需读取，调用与落盘 final 完全相同的 render_timeline_frame。实时图像与基础帧均有字节预算 LRU；GUI 使用 QThread 及 revision 丢弃过期帧，QTimer 播放。导出使用落盘 final 缓存；集成测试逐帧核对实时、独立预览和 PNG。

数量重定时按曲线重映射源实例，保护首尾/标记关键帧。时长重定时按原 duration 累积占比和反曲线重新分配正时长，保持已有停顿相对关系；单轨连续区间之外的帧时长不变。变换插值分段经过所有标记关键帧。EditHistory 保存参数前后快照（80 步），包括 Root/Motion/Align 与编辑状态；Undo 后重建派生缓存，不反向修改文件。

Godot JSON 使用最终帧数、源映射、time/duration/layers 和最终坐标。Sprite PNG 不承载时间，调用者应读取 JSON 帧时长；root_motion_time_basis=original_source_frames 明示独立的原始运动时间轴。旧项目无编辑时继续走原 provider/cache/signature。

## 模块边界

`models` 定义纯 Python 数据模型与兼容 JSON；`core` 提供无 Qt 图像、跟踪、运动和缓存管线；`exporters` 消费完成的最终帧；`ui` 负责 Qt 交互及 QThread 协调；`i18n` 管理 UI 翻译；`utils` 管理进程、路径、日志和字节预算 LRU。

## 项目标准画布层

Project 新增项目级 project_canvas_width/height/canvas_fit_mode，存于 PROJECT_FIELDS，动画快照不复制，切换时注入唯一项目规则。新建窗口的标准画布预设和宽高独立于输出分辨率。旧工程默认0/0/none，保持旧raw签名和Root/Profile坐标。

`core/canvas_fit.py` 定义不可变 CanvasFit，只接收原分辨率和目标分辨率。crop/padding/offset由宽高差派生，整数切片复制uint8/uint16，零插值、零内容检测。奇数差的额外像素落在右/下。RGBA默认透明，视频填充首个原始解码帧估计的背景色。

```text
新项目视频：decoded_frames（原分辨率）→ Canvas Fit → raw_frames（项目画布）→ Chroma → keyed
新项目序列：每张原始RG(B)A → Canvas Fit → raw_frames（项目画布，即keyed）
                                                  ↓
                       Root/Motion/Align 或直通 → 输出Normalize/Cell → Provider/Preview/Export
```

video.width/height统一描述后续分析的工作画布；original_size单独保存素材尺寸，sequence_sizes保留逐帧原尺寸，导入UI按当前帧报告。手动Root、Body/Ground ROI、Alpha Bounds在项目画布中操作，Character Profile使用这些适配后的输入进行原有源→最终变换。

视频decoded manifest只依赖原视频身份。raw_signature启用项目规则时加入project_canvas_fit_v1及标准宽高，后续key/root/motion/align自动失效；改变输出尺寸仍复用工作画布。视频画布重新生成可复用decoded，不重新解码。序列直接逐张适配，不能先做旧版最大画布pad。

`ui/canvas_fit_info.py`从同一个CanvasFit读取裁剪/补边值；导入页、左侧当前帧和序列确认复用。多尺寸详情放在滚动区域。新模式mixed sizes的确认明确说明统一规则；旧项目保留原有混尺寸取消/右下pad选择。metadata额外记录project_canvas/canvas_fit_mode/original_size。

`app/project_canvas_smoke.py`通过真实Qt新建→矩形预设→1536项目→五种大图尺寸→中心适配→预览导出→重开检查；build.ps1在冻结EXE中重复执行。

主要模块：

- `models/character_profile.py`：不可变项目级配置，半宽派生对称边界，强制 Root X = Y Axis。
- `core/character_space.py`：首次站地提议、固定角色空间变换、基准框越界警告。
- `ui/character_space_editor.py`、`character_overlay.py`：整帧校准、Root 吸附、对称控制柄和独立参考几何绘制。

- `canvas_normalizer.py`：不可变公共 CanvasTransform，预乘 Alpha INTER_AREA resize，全画布归一化。
- `ground_detection.py`：下半身 Body ROI、连通区域过滤、横向支撑 robust bottom。
- `motion.py`：轨迹尖峰、局部二次拟合、轴策略、跳跃阶段、循环漂移、审查警告。
- `final_canvas.py`：源尺寸运动补偿与 Normalize / Auto Bounds 布局。
- `final_frame_provider.py`：Preview、Sprite Sheet、Export 统一最终帧来源。
- `root_motion_exporter.py`：目标像素单位的运动参考 JSON。
- `motion_editor.py`、`animation_preview.py`：曲线视图与非模态导出检查。
- `i18n/translator.py`、`zh_CN.json`、`en_US.json`：中英文翻译、变量及源码覆盖校验。

## V0.4 视频抠像直通

Project 新增动画级 `processing_mode`（full / keyed_passthrough，旧工程默认 full）及 `full_processing_canvas_mode`。进入直通保存此前画布模式并选择 source_canvas；退出恢复完整模式，保留手动 Root、Motion、Alignment、Profile 设置。模式切换清除内存中的最终布局/跟踪快照，不删除源/keyed PNG；归档和切换动画保留各自 processing_mode。

`is_passthrough` 统一覆盖序列直通与视频抠像直通；`ensure_aligned` 在 Root/Motion/Profile 之前分流。`ensure_passthrough` 根据输入选择视频 keyed cache 或序列 raw cache，其后的整画布 Normalize、Cell、FinalFrameProvider、Sheet、Export 完全共享。原尺寸分支不进行重采样、裁切或平移。检测 Alpha Bounds 只用于元数据。

视频直通 align 签名为 key_signature + keyed_passthrough_v1 + 可选 Normalize 参数，必须包含 Chroma 参数；序列直通继续使用 raw_signature。两者不包含 Root/Motion/Profile/Scale。切回 full 使用原完整分支签名，旧预览失效，key/raw 签名不变。用户修改 Chroma 时 keyed 和最终帧同步失效。

MainWindow 全部抠像完成后停留 Key 页，顶端显示两条路径并将滚动条回到顶部。直通自动 Sprite/构建，Anchor 可访问恢复按钮，Motion/Align 标记跳过且禁用。恢复后可继续原有跟踪，主视图优先读取已验证的 keyed cache；`key_cache_ready` 只检查完成标志、签名和文件，不启动解码或处理。

Godot 元数据显式保存 processing_mode、有效 alignment_mode=passthrough、character_profile_applied=false；Root/Confidence 为 null，Root Motion available=false，FPS 读取 VideoInfo。PNG 本身保留视频原始位移。动画预览不显示伪造的 Root/Ground，但保留现有播放和局部合成效果。

`app/keyed_passthrough_smoke.py` 同时用于源码和冻结成品验收；QTimer 驱动真实窗口及 FFmpeg 视频，检查原生帧、统一缩放、预览/导出像素、保存重开与复用 RGBA 恢复完整处理。

## V0.4 项目创建与目录选择

`core/project_workspace.py` 校验 Windows 名称、项目模板和画布，独占创建目标工程文件；非空目录永不覆盖，空目录复用需要显式选择。目录沿用 `cache/<project_id>/animations/<animation_id>`，exports 为导出默认父目录。source/sequences 提供素材目录，previews/logs 预留；现有运行日志入口不变。

Project 新增 project_name/project_version/project_type/default_fps/source_canvas/output_canvas，全部有旧工程兼容默认值。项目级字段只存一份，从动画快照剔除，切换时注入当前项目元数据与唯一 Character Profile。沿用既有 animations 字典，避免破坏 V0.3 快照；允许空 animations 数组作为空字典加载。

`NewProjectDialog` 负责模板和字段、目录冲突提示，提交纯模型创建函数；MainWindow 复用 `_confirm_discard` 的异步保存续接机制。`StartPage` 区分无工程启动和已创建空工程。导入继承判断包含已保存工程、命名工程和 Character Profile，保证首个 Idle 尚未建立 Profile 时也不丢失项目。直通序列仍覆盖模板的自动归一化设定。

`ui/folder_picker.py` 为独立 QDialog + QFileSystemModel，所有目录入口统一调用；原有 FileDialog 门面转发目录操作。文件模型异步加载，序列辅助信息在可取消 Worker 中读取，使用修订号丢弃过期结果。单击选择，双击/路径回车导航，只有提交按钮返回目录。目录历史、驱动器、浅色自绘图标、局部 stylesheet/palette 与 Windows 原生主题独立。

## V0.4 8/16 位样本

`utils/rgba_image.py` 从 PNG IHDR / TIFF BitsPerSample 读取每通道位深，不用 Pillow RGB/RGBA 模式推断高位深。8 位沿用 Pillow；16 位使用 OpenCV 原生 uint16 解码并校验数据类型，处理 BGR/RGB 排列、满 Alpha 和 TIFF associated alpha。颜色格式元数据按帧存入 sequence_formats，并进入 raw manifest；RGB8/16 警告与 RGBA16→RGBA8 提示由 sequence_info 统一格式化。

FrameCache LRU 按实际字节计量 uint8/uint16；save_rgba 对 uint16 写 16-bit PNG。源帧和源平移缓存保留精度。warp 使用 float32 预乘并回存源位深；normalize 在 float32 完成 INTER_AREA 再一次量化到最终 RGBA8。未缩放直通用 `(uint32(value)+128)//257` 完整范围四舍五入，所有通道使用同一规则，隐藏 RGB 和像素位置均不变。

Tracking 单独获得 RGBA8 分析视图，保持原始分辨率；该视图不替换渲染用源缓存。Alpha/地面阈值按原始样本最大值换算。Before/After 源显示显式转成 RGBA8，最终帧仍由唯一 FinalFrameProvider 提供。源尺寸 RGBA 导出保留源位深；游戏单帧、Sheet、Preview 均为同一 RGBA8。

序列源签名更新为 frame_sequence_v2_depth，使旧 8 位导入缓存重新验证；视频签名版本保持不变。UI 只在无法安全读取格式/数值范围时报告位深错误，没有“必须每通道 8 位”的阻断条件。

## V0.4 帧序列输入

`core/frame_sequence.py` 负责自然排序、单层扫描、格式/位深/尺寸检查和 RGBA 读取，不依赖跟踪、色键或 Qt。`ui/sequence_import_dialog.py` 显示扫描结果，默认直通、24 FPS；混尺寸默认拒绝，用户同意 pad 后才补透明画布。扫描和导入使用现有 Worker。

Project 新增 input_mode、sequence_folder、sequence_fps、passthrough_alignment、sequence_size_policy 和有序源文件清单。默认输入仍为 video，旧字段与 schema_version=1 保留。VideoInfo 为现有时间轴提供当前输入的宽高/FPS/实际帧数；序列由扫描填充，不调用 FFmpeg。保存/加载同时处理视频及文件夹的相对路径，动画快照通过 source_path 统一识别来源。

```text
视频：Decode → Chroma → Root → Motion → Align → Normalize / Cell
视频（抠像直通）：Decode → Chroma → 可选 Normalize → Final Cell
序列（需要处理）：RGBA / 可选 pad → Root → Motion → Align → Normalize / Cell
序列（直通）：RGBA / 可选 pad → 可选 Normalize → Final Cell
                                            ↓
                               FinalFrameProvider → Preview / Sheet / Export
```

ensure_aligned 在任何 Root/Motion/Profile 调用前判断 is_passthrough，进入 ensure_passthrough；序列分支同时跳过 Key，视频分支读取或生成 keyed cache。原尺寸使用完整 RGBA，不按 Alpha Bounds 决定尺寸或位置；显式 normalize_source 才复用 canvas_transform/normalize_canvas。确认后的序列 pad 使用 max(width)/max(height)，保持原坐标，仅向右/下填充透明像素，所有帧共用变换。

序列 raw cache 保存规范 RGBA，keyed 入口别名到 raw，不复制或二次色键。源签名包含自然排序文件名、逐文件大小/修改时间、文件夹路径及 pad 策略；导入期间源变化则不提交完成标志。FPS 不进入像素签名，改变 FPS 复用 raw/final PNG。源文件变更在下一次构建时触发重扫。

序列直通 align 签名只含源签名和显式 Normalize 参数，不含 Root、Chroma、Motion、Profile、Scale 或 Auto Bounds；视频直通另依赖 Chroma 签名。Profile 保留但不参与直通变换和叠加，character_profile_applied=false。FrameData 的零 Root 仅为内部兼容占位，tracking_method=passthrough；UI 显示已跳过，导出的 Root/Confidence 为 null，Root Motion available=false，不伪造轨迹。

直通导入后自动构建并进入 Sprite；修改每行帧数后点击 Preview/Export 可自动构建。Animation FPS 在导入窗口/导入页编辑；预览窗口 FPS 保持局部状态。旧视频导航全部恢复；序列处理模式只跳过 Chroma。RGBA8 原值保留，包括透明区 RGB；RGBA16 依照上述精度路径转换，多页/动态图像需要先拆帧。

本阶段只扫描单个动画文件夹。19 项新增测试、原生 Qt 序列流程与视频/角色回归验证分支隔离。

## 项目级角色配置

Project 持有唯一 `character_profile`、当前动画数据、`animation_id` 和其余动画快照。快照仅含源视频、逐帧跟踪和动作参数，禁止嵌套 Character Profile。导入保留项目标识及配置；切换时保存当前快照，读取目标快照，注入同一配置。每个新素材仍需自己的首帧跟踪种子，与 Canonical Root 分开。

`CharacterProfile` 为 frozen dataclass。坐标使用最终画布像素，Scale 是唯一源→角色比例。`canonical_root.x == ground_origin.x` 由构造和加载验证；不依赖 UI 是否吸附。`canonical_root_offset` 派生并序列化。Reference Box 仅存半宽，左右边界按 `origin_x ± half_width` 派生，顶边为 0，底边为 Ground Origin Y。宽度编辑只 replace 半宽。

首次校准用主要身体连通区域和稳健地面线提出站地位置；用户可整帧平移，选择 Canonical Y。Canonical X 无条件吸附至 Y Axis，并检验吸附后点位于角色内。确认后锁定画布、比例、原点和 Canonical，仅开放框宽。首次 Alpha 辅助不用于后续动画居中。

```text
tracked_root = raw_root * character_scale                 # 角色空间
character_correction = canonical_root - tracked_root      # 角色空间
correction = character_correction / character_scale       # 源像素补偿
target_root = canonical_root / character_scale            # 内部源坐标
final_pixel = (source_pixel + correction) * character_scale
cell_root = canonical_root                               # 精确项目常量
```

Profile 优先于旧画布/对齐设置，强制 X/Y EXTRACT。保留循环校正前的平滑 motion_root 位移，额外导出 raw 差分/累计位移；跳跃和前冲的数据不会被原地对齐删除。源分辨率整帧平移到固定工作画布 `ceil(canvas_size/scale)`，再预乘 Alpha 统一缩放。1536→512 的工作画布仍为 1536×1536；不按 Alpha Bounds 求中心或尺寸。工作画布也受 6400 万像素上限约束。

参考越界使用原始 Alpha Bounds 经最终变换后的像素范围，使实际画布已裁切时仍能报告越界。参考警告与实际裁切独立，不修改图像参数。`transform_key` 不含半宽/朝向，框宽不使图像缓存失效；读取 Align 缓存后按当前 Profile 重算警告。旧预览元数据标为过时，重新打开即可复用相同 PNG 与更新后的框。

项目快照中各动画不复制 Profile。初始动画保持原缓存路径，后续使用 `cache/<project-id>/animations/<animation-id>/`。保存/另存复制整个项目缓存；每个动画保留独立 manifests。Motion 签名新增 Profile transform_key，管线版本升为 3；旧缓存首次构建刷新。半宽修改只刷新警告。

## 数据流与缓存

```text
FFmpeg passthrough decode
  → raw_frames（源尺寸）
  → keyed_frames（源尺寸 Chroma Key）
  → RootTracker（源尺寸 Body ROI / LK / RANSAC / fallback）
  → Motion（source raw / filtered / target / correction）
  → source_aligned_frames（源尺寸 Alignment；Normalize 分支）
  → Canvas Normalize（完整画布公共变换）
  → aligned_frames（最终 Sprite Cell）
  → FinalFrameProvider
      ├─ Sprite Sheet / PNG Export / Godot JSON
      └─ AnimationPreview / LRU / QTimer
```

无 Profile 时，Auto Bounds 分支把已校正坐标的全动画 union bounds 转为统一 cell，Normalize 分支不使用 union 决定比例。有 Profile 时使用固定角色画布，绕过 Auto Bounds 布局。

缓存签名包含管线版本和上游依赖：Raw→文件身份；Key→Raw+抠像参数；Root→Key+手动 Root+跟踪配置+边界阈值；Motion→Root+运动配置；Source Align→Motion+旧版模式；Final Align→Motion+画布/缩放+循环审查；Sheet→Final Align+每行帧数。更改目标尺寸复用 source aligned、Key 和 Root；更改每行帧数只重建 Sheet。

阶段开始写入时撤销自己的 manifest，完成后才原子提交。取消不发布部分缓存。PNG 先写临时文件再替换。原始视频使用 passthrough 解码，帧数以实际输出为准，不受预览定时器影响。

## Root 与坐标

源像素左上为 (0,0)，X 向右、Y 向下。raw_root 是 tracker 原始检测；filtered_root 是剔除尖峰、平滑并可选去循环漂移后的视觉曲线；motion_root 额外保留循环去漂移前的连续曲线；target_root 是 Sprite Root 在源画布中应处的位置。

```text
correction = target_root - raw_root
final_point = (source_point + correction) * normalize_scale + normalize_offset
root_motion = (motion_root - motion_root[0]) * normalize_scale  # EXTRACT 轴
```

循环漂移只修正视觉轨迹，不消除已提取的 Run/Dash 路程。GROUND_LOCK 根据身体支撑线确定 Y 补偿，显式跳跃区间会切换为 EXTRACT。首帧定义统一基准；手动关键帧固定测量并分隔局部平滑窗口。

1536×1536→512×512 使用 sx=sy=1/3、offset=0；所有帧共享 CanvasTransform。内容边界变化不改变 Normalize scale。保宽高比时添加透明留白；整数重采样尺寸可能存在一像素量化。补偿移出固定源画布时警告裁切，不隐式改变比例。

cell_root、cell_bbox、cell_ground 是最终画布数据。bbox 为 [l,t,r,b)，在最终像素重新测量；Root/Ground 为浮点。Godot 原始/平滑曲线按目标比例及公共偏移导出，最终 root 含补偿。跟踪种子、ROI 与跟踪使用源坐标；Character Space 校准界面使用角色坐标，确认时反算源跟踪种子。

## 跟踪与地面

特征检测掩膜为 Body ROI 与有效 Alpha 的交集，并腐蚀边缘；透明背景不能产生跟踪点。LK 做前后向一致性检查，RANSAC estimateAffinePartial2D 剔除离群特征；可用内点位移中位数作 translation-only 估计。

置信度综合有效特征率、RANSAC 内点率、重投影误差、Alpha overlap 和特征数支持。失败顺序：光流→Alpha 内相位相关→最多三个步骤内衰减的运动预测→警告。手动修正重置预测速度。

地面 ROI 可随原始 Root 平移；下半身候选区内保留主要连通区域，忽略小面积区域和缺乏横向支撑的细长尖端。此模块不声称识别语义人体、武器或特效；用户 ROI 是歧义场景的控制入口。

## 最终预览与线程

FinalFrameProvider 深拷贝构建结果，绑定 align manifest 签名，每次读取验证版本；LRU 上限 96 MiB。get_final_frame(index) 校验 cell 尺寸；get_source_keyed_frame 仅用于 Before/After。PNG 导出直接复制 final_path；Sheet 消费相同路径，不执行第二套 Resize/Align。

AnimationPreview 为非模态 QDialog；QTimer 调度，Worker 执行磁盘读取和洋葱皮/残影合成。请求合并并检查 revision，过时结果不显示。所有 QWidget 操作在 GUI 线程；关闭时取消并回收 Worker。修改工程使旧窗口 stale，停止播放并禁止导出。

调试标记由 QPainter 前景绘制，不进入缓存 PNG。预览合成产生独立数组，不修改只读 LRU 帧。FPS/背景/循环接缝为窗口局部状态，不修改工程导出参数。主编辑画面也在完整源尺寸抠像后才生成显示缩略图。

## i18n 与兼容性

英文消息键是稳定 ID，显示内容统一通过 t(key, **values) 查询 JSON。变量文本使用模板。专业参数与对齐模式有 tooltip；Qt 控件使用 qtbase_zh_CN，应用对话框按钮和文件筛选器通过同一翻译系统。

语言默认 zh_CN，持久化 app_settings.json，用户选择后提示重启。QComboBox 显示翻译，itemData 保存英文枚举；项目 schema_version 保持 1，通过字段默认值加载旧工程。旧工程 motion.enabled=False，新导入默认 True。语言不改变旧 alignment_mode 英文值。

打包明确包含 JSON，使用系统 UI 字体，不附带字体文件。check_i18n.py 检查源码消息覆盖、语言键集合和格式参数。

## 复核

架构：core 不依赖 UI，Preview/Export 共用最终帧，没有第二条变换流水线。数据流：源/目标单位与缓存依赖由集成测试验证；提取运动与循环视觉校正分开。工程：保留旧回归，增加 1536→512、运动 A–F、i18n、实际 Qt 播放与导出逐像素检查；PyInstaller 在 Python 进程内隔离 DLL 搜索路径，避免外部 ICU 污染。


## 抠像直通入口与发布位置修复

MainWindow 的两种显式模式入口同时出现在抠像页与精灵图页。视频 keyed_ready 且缺少首帧 Root 时，通用 build_sprites 展示精灵图页选择，不运行跟踪，也不隐式切换模式。用户点击直接构建后才设置 keyed_passthrough，再走唯一 Pipeline / FinalFrameProvider；已有 Root 的完整处理仍保持原行为。切换回完整处理继续复用 keyed cache。

发布在独立目录完成冻结验收，scripts/publish_release.ps1 仅将程序运行文件和文档更新到固定 dist 路径，检查运行占用并保留原有用户数据。根目录启动器固定指向该位置，避免旧发布目录造成入口缺失。

2026-09-15 编辑器模型已接入工程、最终缓存、导出和五页导航，详见本文件新增章节。
