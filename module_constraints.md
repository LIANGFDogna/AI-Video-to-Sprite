# Module constraints

| 新模块 | 输入 → 输出 | 依赖 | 边界 |
|---|---|---|---|
| canvas_fit | 原宽高+项目宽高+RGBA → 中心裁剪/补边 | NumPy/dataclass | 整数复制，无插值/主体/Alpha/Root/Profile，8/16位保持 |
| canvas_fit_info | 同一CanvasFit → 原尺寸/四侧数值 | i18n/core | 仅展示，不另算图像或位置 |

视频decoded为原素材，raw为项目工作画布；序列逐张从原尺寸生成raw；后续Tracker/ROI/Profile使用工作坐标。

| 模块 | 输入 → 输出 | 依赖 | 边界 / 验收 |
|---|---|---|---|
| models | JSON ↔ 数据类 | 标准库 | 版本、校验、相对路径往返 |
| decoder | 视频 → RGB PNG + info | FFmpeg | 不设置 -r；实际帧数；取消 |
| chroma | RGB + 参数 → RGBA | OpenCV/NumPy | 软边、去溢色、无缩放 |
| alpha | RGBA → bbox | OpenCV/NumPy | 排除小连通域、空帧 |
| tracker | RGBA 序列 + keyframes → Root/confidence | OpenCV | 低置信不跳动、修正重启 |
| alignment/canvas | bbox + Root + 模式 → Cell/transform | NumPy/OpenCV | 统一比例、联合边界、裁切报告 |
| sheet/exporters | Cell 文件 → PNG/JSON | Pillow/zlib | 流式、无 Overlay、坐标明确 |
| pipeline/cache | 参数与路径 → 可复用阶段 | core/models | 依赖签名、原子 manifest |
| UI | 用户事件 ↔ worker | PySide6 | GUI 主线程，处理 QThread |

| v0.2 模块 | 输入 → 输出 | 依赖 | 边界 / 验收 |
|---|---|---|---|
| motion | 原始轨迹 → filtered/target/correction/motion | NumPy/models | 不 Blur 图像，保留加速度与提取位移 |
| ground | 源 RGBA + Body ROI → robust ground | OpenCV | 下半身、排除小连通域/薄尖；允许人工 ROI |
| normalizer | 完整源 RGBA → 目标 RGBA | OpenCV/NumPy | 公共 Transform、预乘 Alpha、精确尺寸 |
| FinalFrameProvider | align manifest + PNG → 最终像素/路径 | cache/models | LRU、签名验证、Preview/Export 同一来源 |
| animation preview | Provider → 非模态动画视图 | Qt/Worker | QTimer、响应式、局部 FPS/Overlay、关闭回收 |
| i18n | 稳定 key + 变量 → 显示文本 | JSON/Qt | 双语言覆盖、无中文序列化枚举、可持久化 |

| v0.3 模块 | 输入 → 输出 | 依赖 | 边界 / 验收 |
|---|---|---|---|
| CharacterProfile | 用户校准/JSON → 固定项目基准 | 标准库 | Root X = Y Axis、半宽对称、所有动画唯一一份 |
| character_space | 源检测 Root + Profile → correction/警告 | core/models | 无 Alpha 自动居中、无越界自动缩放；只首建可自动提出站地 |
| CharacterSpaceEditor | 整帧拖动/Root 点击/控制柄 → Profile | Qt/core | 校准 Root 强制吸附；确认后宽度编辑不改其他字段 |
| animation snapshots | 当前动画 ↔ 项目快照 | models/cache | 独立源跟踪参数、共享 Profile、路径保存与缓存隔离 |

| v0.4 模块 | 输入 → 输出 | 依赖 | 边界 / 验收 |
|---|---|---|---|
| frame_sequence | 单层目录 → 排序清单/尺寸/Alpha/RGBA | Pillow/NumPy | 自然排序、尺寸差异明确处理、RGBA8 保留 |
| passthrough | 序列 raw / 视频 keyed RGBA → final Cell | normalizer/cache | 提前分流，无 Root/Motion/Profile 对齐；视频先完成 Chroma |
| sequence_import_dialog | 扫描 → 处理选择/FPS/pad | Qt | 默认直通；混尺寸未确认禁止导入 |
| rgba_image | PNG/TIFF 原始样本 → RGBA8/16、格式元数据 | Pillow/OpenCV/NumPy | 分辨 bpc/bpp，补满 Alpha；明确范围转换 |
| project_workspace | 名称/模板/目录 → 空工程文件 | models/标准库 | 独占创建；非空不覆盖；无自动 Profile |
| folder_picker | 目录浏览 → 明确选定路径 | Qt QFileSystemModel/Worker | 自有主题、异步辅助信息、单击和双击不提交 |
| new_project_dialog/start_page | 创建参数/项目状态 → 用户入口 | Qt/Project | 复用未保存确认；无自动素材选择 |

| timeline_edit | 源索引+命令→非破坏时间线 | 标准库 | 稳定ID、4轨、锁定、数量/时长曲线、撤销 |
| timeline_renderer | 基础Cell+时间线→最终PNG/时序 | core/cache | 预乘合成、源元数据保留、最终Provider唯一 |
| frame_editor | 用户操作→编辑指令/预览 | Qt/Worker | 可选区段、画布拖动、曲线、历史、无磁盘删除 |

## Character Reference 模块

models/character_reference.py只定义不可变几何/XY；core/character_reference.py负责原Idle缓存；core/animation_transform.py负责共享整动画渲染；ui/character_reference_dialog.py仅编辑草稿轴；reference_overlay.py不触碰导出图像。Reference不加入raw/key/align签名，AnimationTransform只加入final签名。

## Path Memory
utils设置与路径服务无Qt/Project依赖；ui/dialogs是统一文件入口；FolderPicker复用服务，业务在成功回调commit，NewProject只在创建成功commit。


## Phase 2A模块
Library模型只管理UUID树/资源/状态；Workspace控制器协调现有动画快照与只读缓存；UI Tree不处理像素；GroupExport只复制最终产物和既有元数据。模型校验禁止环/孤儿资源/Project Root素材。
