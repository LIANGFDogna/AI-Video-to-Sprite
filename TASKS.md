# Tasks

## Current — Path Memory / UI Audit

- [x] 统一AppSettings原子合并与PathMemoryService；用途历史、全局最近位置及重启恢复。
- [x] 按用户最终修正规则：新建父目录可自由更改、记住成功创建位置、Work按E→D→C→Home回退。
- [x] 全部10个FileDialog业务入口、缺失素材重定位、另存工程、各导出成功回调接入。
- [x] 动态快捷侧栏、清晰文字导航、完整路径Tooltip；过滤旧Qt侧栏历史避免重复。
- [x] 新建滚动表单/固定底栏/冲突打开或改名/重复提交保护；保存与取消行为保持。
- [x] 按钮、Action与Shortcut绑定/忙状态/空项目状态/Enter/Esc审查；修复直通Root控件状态回归。
- [x] 191项全量测试、705条中英翻译检查、31个处理算法文件哈希不变。
- [x] 真实窗口中文/英文、中文空格及275字符以上目录、独立A/B/C/D用途、跨进程恢复。
- [x] 新候选EXE全流程检查及正式dist发布；实际dist的100/125/150%和独立重启验收通过（VALIDATION.md）。

## Completed
- 读取完整需求、确认空目录与 Python 3.12 / FFmpeg 环境。
- 建立架构、坐标规范、缓存依赖、开发阶段与验收计划。
- 阶段 1：模型、无丢帧解码、软色键、去溢色、噪声过滤；5 项 pytest 通过。
- 阶段 2：三模式对齐、全帧 UNION、Padding/Rounding、裁切、流式 Sheet；累计 15 项 pytest 通过。
- 阶段 3：LK/RANSAC、置信度、手动重启、分阶段缓存、取消恢复、Godot/PNG 导出；累计 19 项测试通过（含完整 MP4 工作流）。
- 阶段 4：六阶段 GUI、四种预览、时间轴、Overlay、手动 Root 编辑、播放、保存重开、后台任务和 Diagnostics 已接通。
- 核心验收：24 项 pytest 全部通过；覆盖额外的内存预算、缺失 FFmpeg、取消原子性和裁切导出授权。
- GUI 验收：原生 Windows Qt 完成 24 帧导入→调参→提取→点击 Root→手动修正/删除→构建→保存重开→Godot 导出；AUTO 199×221，无裁切，测试片段最低置信度 0.99749。
- 提供锁定依赖、源码启动器、构建脚本和 examples/demo.aivsprite 示例工程。
- Windows 独立 exe 已成功打包并启动退出（exit code 0）；构建依赖清单不含混入的 Poppler/libheif/ICU DLL。build.ps1 现在自动执行打包启动检查。

## Completed — Character Reference 第一阶段

- 完成项目唯一不可变Reference、单动画XY Offset及旧工程默认值；旧CharacterProfile/Root/Motion独立兼容。
- 完成固定Idle第0帧校准、Ground/YAxis/Origin按轴拖动、1/10项目像素微调、保存锁定与显式重编辑。
- 完成后续动画共轴、默认整动画拖动/数值XY、不产生逐帧覆盖、Undo/Redo及跨动画历史隔离。
- 完成固定35% Idle Ghost、独立显示开关、缓存复用与缺失素材非阻塞提示。
- 完成整动画Offset实时/落盘统一渲染、源PNG/Key缓存不变、越界只警告、Preview/Sheet/PNG逐像素验证。
- 新增模型/管线/真实Qt回归，以及真实视频抠像→参考校准→Run序列→预览导出→保存重开完整验收。
- 发布构建包含125%/150%冻结EXE验收，窗口显示构建标识；最终发布路径与证据见VALIDATION.md。

下一阶段（仅规划）：Project Animation Library：Project→Character→Animation Group→Animation；Character Templates、Animation Set及JumpUp/FallLoop/Land；Ctrl+A Create、Tree Drag & Drop、Loose Animations、Character/Enemy/Boss分类。本轮没有提前实现这些目录/模板功能。

## Completed — 编辑器重构

- 五页工作流、统一编辑页及 Root/Motion/Align 折叠侧栏已完成；保留视频/序列直通、项目中心画布与旧工程行为。
- 非破坏性实例、四轨、显示/锁定、单/Ctrl/Shift/框选、拖动重排/换轨、删除、复制/指定位置粘贴/末尾粘贴、倒放完成。
- 单帧拖动/方向键/Shift、数值和批量 XY、比例/透明度、关键帧及分段变换插值完成。
- 目标帧数、速度倍率、目标时长、区段重定时、四种预设曲线和可拖动/输入的 Bezier、首尾/标记关键帧保护完成。
- 同页 QTimer 播放、洋葱皮/残影、坐标轴、安全区、Root 路径辅助完成；未重新构建时仍可从源帧列表修正 Root。
- 全操作 Undo/Redo、每动画编辑数据保存、独立最终缓存和 Preview/Export 像素一致性完成。
- UI 提高背景/文本/输入框对比，修复属性横向溢出和轨道锁定列，移除重复的大页面工具栏。
- 全量及原生/冻结发布验收结果以 VALIDATION.md 为准；发布需同步日常 EXE 入口。

后续可选：跨动画素材拖入轨道、真正的嵌套序列块、自动识别大动作关键帧、持久化撤销历史、项目最近列表；当前帧资源来自本动画，参考轨不导出。

## V0.4 项目标准画布

- 新建项目始终可编辑标准画布宽高，预设1536×1536、1024×1536、512×512和自定义；项目字段唯一保存并跨动画继承。
- 视频抠像前按分辨率中心裁剪/补背景色；序列逐张原尺寸裁剪/补透明，uint8/uint16原值保留，无内容/Alpha/Root/Profile驱动的居中。
- 项目规则先于直通和Root/Motion/Align，后续尺寸与坐标统一使用适配后的工作画布；最终输出Normalize独立。
- 保留原视频decoded缓存、原始尺寸及序列逐帧尺寸；fit参数使下游缓存失效，输出变化或重新fit无需重解码。
- 导入窗口滚动详情、导入页及左侧逐帧显示原尺寸/项目尺寸/四侧补边裁剪；RGBA导出名称区分项目画布与旧源尺寸。
- 旧项目0/0/none保持旧像素坐标；旧直通测试按本次新项目强制适配规则更新，其余覆盖保留。
- 实际150% Qt创建、五种大图混合尺寸、预览/导出像素一致、保存重开通过；新增冻结EXE同流程验收。

## 前轮交付
- V0.4 视频抠像直通已完成，114 项测试通过；新 Windows EXE 的原有流程及56帧视频直通验收全部通过。发布包位于 release-v0.4/AI Video to Sprite，之前工程创建、位深、目录选择器等功能保留。详见 VALIDATION.md。

## V0.4 视频抠像直通

- processing_mode=keyed_passthrough，旧项目默认 full；动画快照与保存重开保持模式。
- 全帧 Key 完成停留抠像页，顶部两个入口；直通自动进入 Sprite，导航显示跳过 Anchor/Motion/Align。
- 整帧位置/Alpha 不变，Jump/Dash 位移保留；禁止隐藏的 Root、Ground、Profile、Motion 或 Alpha 居中。
- 原尺寸默认；原生/1536/1024/768/512/自定义预设；明确 Normalize 才使用公共预乘 Alpha 变换。
- Sprite 视频直通状态与恢复按钮置顶；Anchor 仍可访问恢复按钮，复用 keyed cache，保留完整流程参数。
- Preview/Sheet/Export 统一 Provider；未跟踪数据明确标记跳过，Godot alignment_mode=passthrough、Root Motion unavailable、真实视频 FPS。
- 13 项新增 synthetic/Qt 测试；56 帧真实视频文件、原尺寸逐像素、缩放后 4096×3584 Sheet、播放与导出、工程重开、恢复完整处理验证。
- 新增示例与冻结成品验收入口；更新 README/ARCHITECTURE/TASKS/VALIDATION 和约束文档。
- 新版 EXE 完成打包和全流程检查；原 dist 程序占用日志，采用独立 release-v0.4 发布目录，构建脚本增加运行预检查，保留原进程。

## V0.4 本轮完善

- RGB/RGBA 8/16 位、区分 bpc/bpp、RGB 黄色不透明警告、uint16 PNG 缓存、float32 预乘、最终 RGBA8 完整范围转换；Preview/Export 一致。
- 新建项目窗口、三个模板、自定义画布/FPS、空项目首页、状态、Ctrl+N、目录结构、未保存三选项、Windows 名称处理和禁止覆盖非空目录。
- 项目元数据跨首次 Idle 和后续动画继承，独立于 Character Profile；空工程不自动建立 Root，旧工程和动画快照兼容。
- 统一 Qt FolderPicker，明亮文字/自绘图标、Accent 选中/独立 Hover、文字导航、驱动器、中文长路径、双击进入和显式提交、后台序列辅助信息。
- 34 项新增自动化测试；真实 Qt 深/浅宿主 palette × 125%/150% 四组合、274/275 字符目录、16 位导入提示、空工程；命名工程 Idle 校准与四动作导出往返通过。
- README、ARCHITECTURE、TASKS、VALIDATION 更新；发布构建增加冻结 EXE 新项目→目录选择→22 张 RGBA16→预览→导出→保存检查。
- 可选“最近项目”列表留待后续；不影响创建、打开、快速导入流程。

## v0.4 单文件夹序列帧

- 顶部导入序列帧、文件夹拖入、自然排序，PNG/WEBP/TIFF/BMP/JPG/JPEG；忽略非图像文件。
- 确认窗口显示目录/帧数/尺寸/Alpha，默认 24 FPS、默认已对齐直通；混尺寸必须选择补透明画布或取消。
- 直通不调用 Chroma/Root/Motion/Align/Profile；Cell=原画布，原像素位置与 RGBA 保留。
- 显式 Normalize 复用预乘 Alpha 缩放；混尺寸按最大画布向右/下补透明，不逐帧缩放。
- 自动 Sprite/构建预览/导出；导航显示跳过页、可编辑 Animation FPS，目录名作为动画名。
- 复用 FinalFrameProvider/LRU/QTimer 及洋葱皮/残影/循环衔接，无第二套最终算法。
- 新项目字段、序列相对路径、视频/序列快照切换；旧 V0.1～V0.3 工程兼容。
- 19 项新增测试，累计 67 项通过；原生 Qt 22 帧输入/预览/导出逐像素一致，5120×1536 Sheet、文件夹拖入与混尺寸选择通过。
- 中英文/150% 序列窗口、24 帧旧视频和 V0.3 四动画角色基准流程回归通过。
- README、ARCHITECTURE、TASKS、VALIDATION 及约束文档已更新；Windows EXE 重新打包，旧视频、Character Profile、无 FFmpeg 的序列帧构建与播放全部 exit code 0。

## v0.4 第二阶段

- 父文件夹批量识别多个 Animation Clip，待后续开发；当前逐个选择动画子文件夹。

## v0.3 Character Profile

- 项目级唯一 CharacterProfile，与各帧 Alpha Bounds 严格分离；固定 Canvas/Scale/Ground Origin/Canonical/Offset/Facing，只保存基准框半宽。
- 首次 Idle 自动提出站地位置、整帧拖动、Canonical X 无条件吸附 Y Axis、两侧对称控制柄、“设为角色基准”。
- 后续导入加入同一角色项目；动画选择器、动画快照、独立缓存、保存/切换/重新加载继承同一 Profile。
- 所有最终帧 In-Place Root 精确等于项目 Canonical；禁用 Alpha 自动水平居中；UI 明确显示有效 EXTRACT 规则。
- 基准框越界只警告；框宽编辑不影响图像变换和缓存，不改变比例、原点或 Root；PNG 字节和修改时间保持不变。
- 蓝色虚线项目框、绿色逐帧边界、粉色 Canonical、金色 Ground、固定 X/Y 轴；只绘制在预览前景。
- Godot JSON 含 Profile/跟踪 Root/角色补偿；Root Motion 同时保留原始和平滑位移。
- 新增 10 项测试，全部 48 项通过；Qt 中文及英文 150% 首次校准、拖动两侧控制柄、4 动画继承、缓存和导出一致性通过。
- i18n 增至 432 条；新增角色示例及可复现原生 Qt 验收脚本。
- README、ARCHITECTURE、TASKS、VALIDATION 及约束文档已更新；Windows 发布包重新生成，启动、22 帧最终预览、角色框宽编辑全部 exit code 0。

## v0.2 Completed

- 统一源画布：源尺寸抠像、跟踪与运动补偿后，预乘 Alpha INTER_AREA 缩至目标；1536 自动提供 512 预设。
- 三套 Root、分轴策略、动作预设、轨迹平滑与尖峰、跳跃阶段、循环漂移校正、Root Motion JSON。
- 身体 Alpha 内 Shi–Tomasi / LK / RANSAC、置信度指标、相位相关与预测 fallback；身体与稳健地面 ROI。
- Motion 曲线与三轨迹 Overlay；缩放、平移、点击选帧和时间轴同步。
- 非模态最终帧预览：QTimer、LRU、播放/步进/FPS/Loop、背景/缩放、辅助叠加、前后对比、洋葱皮、残影、循环衔接、警告跳帧、导出入口。
- Preview / Sheet / PNG export 共用 FinalFrameProvider；修改参数使旧预览失效；导出后提示打开预览。
- 正式 JSON i18n：389 条中英文消息、变量与 tooltip、系统字体、Qt 控件翻译、默认简体中文、重启应用语言设置。
- 旧工程英文枚举与 schema 兼容；新导入默认运动策略，旧工程保留旧对齐。
- 38 项 pytest；实际 22 帧 1536×1536 / 24 FPS Qt 流程、512×512 单帧、5120×1536 Sheet、预览导出逐像素一致。
- 原有 24 帧 Qt 流程回归通过；中文 125%/150%、英文 150% 检查通过。
- Windows 重新打包完成；独立 exe 中文启动和 22 帧冷缓存构建→最终动画播放均 exit code 0；语言 JSON 与 Qt 中文翻译资源齐全。
- README、ARCHITECTURE、TASKS、VALIDATION 及约束/数据流文档已更新；附带 22 帧归一化示例。

## Known Issues
- 色键与光流以合成视频验证；真实 AI 视频中的遮挡、绿色服装、剧烈形变可能需要调参或手动 Root 修正。
- VFR 保留帧数，动画采用平均 FPS；逐帧可变时长编辑尚未提供。
- SpriteFrames .tres 与双向跟踪按原规划留待后续；目前 Godot 导出为 PNG + SpriteFrames JSON metadata + Root Motion JSON。
- 地面检测使用身体 ROI 几何启发式；武器/特效占据同一主区域时需手动指定 ROI。
- 接缝警告基于 Root/Alpha 边界阈值，形体细节仍需最终动画播放检查。
- 超大 Sheet 使用磁盘临时空间；单 Cell 上限 6400 万像素。缓存可重建，暂未提供自动容量清理。

## Next
- 使用实际 AI 视频收集抠像与跟踪边界案例；后续扩展见 ROADMAP.md。
