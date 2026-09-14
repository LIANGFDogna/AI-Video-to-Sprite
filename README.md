# AI Video to Sprite · v0.4

Windows 桌面工具：将 AI 绿幕角色视频或已处理好的图像序列转换为游戏序列帧、Sprite Sheet（精灵图）和 Godot 动画元数据。支持视频抠像后直通、序列帧直通、项目级角色坐标系、统一源画布、Root Motion（根运动）分离和独立动画预览。

## 启动与语言

本轮新版位于 `release-v0.4-canvas/AI Video to Sprite/AI Video to Sprite.exe`。请保留整个同名文件夹，不能只复制 exe。FFmpeg 与 ffprobe 需要在 PATH 中，也可用 `AIVSPRITE_FFMPEG`、`AIVSPRITE_FFPROBE` 指定路径。

默认简体中文。右上角“语言”可选择 English，保存后重启生效。设置保存在 `%LOCALAPPDATA%/AI Video to Sprite/app_settings.json`；测试环境可用 `AIVSPRITE_SETTINGS` 指定路径。语言不会改变工程里的英文枚举或图像参数。

源码启动：先运行 `setup.ps1`，再双击 `run.bat`；或执行 `.venv\Scripts\python.exe -m app.main`。依赖版本记录在 `requirements-lock.txt`。不需要 API 密钥或云端服务。

## 新建项目（V0.4）

顶部 **“新建项目”**（Ctrl+N）打开项目创建窗口。填写名称、父目录，选择“角色动画项目”和模板：**标准 512×512 / 1536→512 AI角色 / 自定义**。项目标准画布宽高始终可编辑，提供 **1536×1536 / 1024×1536 / 512×512 / 自定义** 预设；默认输出分辨率和 FPS 独立保存。

1536→512 模板使用 1536×1536 源画布、512×512 输出、33.333333% 统一比例、24 FPS 和 RGBA。创建完成后显示空项目首页及“角色基准：未建立”，可点击 **“导入 Idle 视频”** 开始校准；不会自动创建 Ground Origin、Canonical Root 或角色基准框，也不会立即打开素材选择器。

```text
MainCharacter/
├─ MainCharacter.aivsprite
├─ source/
├─ sequences/
├─ cache/       # 沿用项目 ID / 动画 ID 缓存
├─ exports/     # 导出的默认父目录
├─ previews/
└─ logs/
```

名称中的 Windows 非法字符会自动调整并显示结果；不允许空名称或保留设备名。目标目录已存在时必须选择其他位置，或明确点击“使用现有空目录”；非空目录不会覆盖或删除。新建时的未保存修改提示与关闭程序一致：保存 / 不保存 / 取消。

项目保存名称、版本、类型、默认 FPS、源/输出画布；导入首个 Idle 及后续素材时保留项目配置和保存位置。Idle 校准后，左侧显示 `Character Profile：已锁定`。已有动作参数、动画快照和唯一 Character Profile 均可保存重开。视频继续使用素材真实 FPS；序列使用项目默认 FPS，并可手动调整。

仍可直接导入素材建立临时未保存工程，首次保存时选择 `.aivsprite` 位置。**已对齐序列始终默认直通**：命名新项目先执行项目画布适配，随后不做角色级对齐；即使模板输出配置为512，也需在 Sprite 页明确启用输出缩放。

## 项目标准画布

新建项目的标准画布是所有动画共享的输入规则，独立于最终 Sprite 输出分辨率。视频、RGBA、已对齐序列和视频抠像直通均先将 **原始画面中心对齐到项目画布中心**：多余部分裁掉，不足部分补边，不缩放、不检查角色位置。Root/Alpha/主体/武器/Character Profile 都不参与适配位置计算。

以1536×1536项目画布为例：

| 原始尺寸 | 适配结果 |
|---|---|
| 1024×1536 | 左右各补256 |
| 1920×1536 | 左右各裁192 |
| 1536×1024 | 上下各补256 |
| 1536×1920 | 上下各裁192 |
| 1920×1080 | 左右各裁192，上下各补228 |

视频先保留原始解码缓存，再在抠像前适配；补边使用原视频首帧估计的背景色。RGBA序列使用 `(0,0,0,0)` 补边，8/16位保留原精度。混尺寸序列在导入确认窗明确显示差异和项目规则，每张直接从自身原始尺寸适配，不能先放到最大画布再居中。奇数像素差最多造成1像素不对称，余量固定在右/下，不做半像素插值。

导入页和左侧信息显示原始尺寸、项目画布，以及 **补边/裁剪（左/上/右/下）** 数值；序列切换帧时同步更新。超出项目画布的内容会按分辨率中心被裁掉，软件不会为保全角色而移动画面。

之后才进行 Chroma / Root / Motion / Align 或直通，并可在 Sprite 页统一缩放输出。例如：1024×1536 → 左右透明/背景补边到1536×1536 → 可选整体缩至512×512。跟踪、Root点击、地面ROI使用适配后的工作画布坐标，Character Profile 的源→最终变换也从该工作画布开始。

工程保存项目级 `project_canvas_width`、`project_canvas_height`、`canvas_fit_mode="center_crop_or_pad"`，后续动画全部继承同一规则。**旧工程和直接导入的临时工程**缺少这些字段时使用 `0 / 0 / none`，保持原有尺寸与已校准坐标，不会静默裁剪历史素材。需要统一规则时先新建项目，再导入素材。

## 深色文件夹选择器

导入序列、定位缺失序列、选择项目目录和导出目录共用独立 Qt FolderPicker。青绿色表示选中，灰蓝色表示悬停，文字和自绘文件夹图标使用浅色；“返回 / 前进 / 上一级 / 新建文件夹”均有文字按钮。

单击只选中，双击进入子文件夹，点击 **“选择此文件夹”** 才提交。路径栏可直接输入中文或长路径，按 Enter 跳转；不存在的路径显示错误。序列选择时显示图像/PNG 数量、首帧尺寸和位深，无图像时仍可浏览子目录。全部样式仅用于程序自身，不更改 Windows 主题。

## 视频抠像后直接制作精灵图（V0.4）

1. 导入视频，调整绿幕抠像，点击 **“处理全部帧”**。
2. 全部 RGBA 帧完成后停留在抠像页，顶部出现 **“继续 Root / 运动处理”** 和 **“直接制作精灵图”**。
3. 选择 **“直接制作精灵图”**：自动进入精灵图页并构建，无需设置 Root。锚点、运动、对齐标记“已跳过”，页面显示 **“视频直通模式”**。
4. 新建项目默认 **项目标准画布（不做输出缩放）**；旧工程默认原生分辨率。整帧位置与抠像缓存逐像素一致，保留 Jump、Dash、冲刺攻击等上下左右位移。不会 Root/Ground Lock、角色基准对齐、运动提取或按 Alpha 边界裁切、居中；项目中心裁剪/补边已在抠像前完成。
5. 需要调整尺寸时，在 **输出分辨率** 选择 1536×1536、1024×1024、768×768、512×512 或自定义。统一源画布复用预乘 Alpha 高质量缩放；所有帧使用同一变换，保持宽高比默认开启。1536→512 为整画布 1/3 缩放。
6. 设置每行帧数，点击 **“预览动画”** 检查后导出。56 帧、每行 8 帧、512×512 Cell 得到 **4096×3584** 的精灵图（8 列 × 7 行）。

预览、Sprite Sheet 和导出 PNG 共用 FinalFrameProvider；播放、暂停、循环、FPS、逐帧、洋葱皮、残影及循环衔接沿用现有窗口。预览 FPS 只改变观看速度，真实导出仍使用源视频 FPS。直通不运行跟踪，Root/Ground 辅助显示禁用，Root/Confidence 元数据为 `null`，`root_motion.json` 标记 `available=false`；原始运动保留在图像序列中。

需要稳定处理时，点击精灵图页的 **“启用 Root / Motion / Align”**，或手动进入锚点页点击同名按钮。原来的手动 Root、Motion 设置、Character Profile 保留；复用已生成的 keyed RGBA 缓存，无需重新抠像。改变抠像参数或源视频才会使该缓存失效。

`.aivsprite` 按动画保存 `processing_mode="keyed_passthrough"`，重开后恢复直通与画布设置。旧项目缺少该字段时使用 `full`，新导入的视频默认完整流程。示例 `examples/keyed_passthrough_56.aivsprite` 提供 56 帧合成绿幕视频，可按上述步骤体验两种入口。

## 导入已处理好的序列帧（V0.4）

1. 点击顶部 **“导入序列帧”**，选择单个动画文件夹，例如 `idle/`；也可把文件夹拖入窗口。
2. 窗口显示文件夹、帧数、尺寸、Alpha 类型。使用自然排序：`frame_1`、`frame_2`、`frame_10`；不按字符串排成 1、10、2。忽略 JSON、TXT、Thumbs.db 等非图像文件。
3. 默认选择 **“已对齐，直接制作精灵图”**。动画帧率使用项目默认值（初始 **24 FPS**），可在导入窗口或导入页修改，动画名默认使用文件夹名。
4. 确认后自动进入精灵图页并构建；抠像、锚点、运动、对齐页显示“已跳过”。设置每行帧数，再点击“预览动画”；需要刷新 Sheet 时会自动构建，无需选择 Root。
5. 检查播放、步进、循环、洋葱皮、残影和循环衔接，再导出。22 张 512×512、每行 10 帧会得到 **5120×1536** 的精灵图，最后 8 格透明。

**直通模式保留项目画布适配后的像素位置**：不抠像、不跟踪、不做主体居中、不贴地、不锁 Root、不按 Alpha 边界裁切，也不应用项目角色基准框。旧工程未启用项目规则时，512×512图片直接成为512×512 Cell；新项目则先按标准画布中心裁剪/补边。保留区域的RGBA8数值原样保存，包括透明区RGB；16位输入按下述完整范围转换为最终RGBA8。

项目标准画布为1536×1536时，直通默认保留1536×1536。需要缩至512时，明确选择“统一源画布”或点击 `512×512（原尺寸 1/3）`；复用已有预乘Alpha INTER_AREA缩放整张工作画布，不按角色边界裁切。

尺寸不一致会显示 **“检测到序列帧尺寸不一致”**。新项目按已显示的标准画布规则逐张中心裁剪/补边后提交；未启用项目画布的旧工程仍需取消，或选择“放入统一画布”：取所有帧最大宽、高，保持左上坐标，向右、向下补透明。两者都不缩放每张图片。

支持单张静态 **PNG、WEBP、TIFF/TIF、BMP、JPG/JPEG**，推荐 PNG；支持 **RGB8、RGBA8、RGB16、RGBA16**（16 位 RGB/RGBA 由 PNG、TIFF 提供）。RGB 输入显示黄色“当前序列帧没有 Alpha 通道，将作为完全不透明图片处理。”，Alpha 补为 255 或 65535。动态 WebP、多页 TIFF 等需先拆为单张图片。

导入窗口和左侧信息面板显示颜色模式、通道数、每通道位深、Alpha 状态和每像素总位数。例如 `RGBA · 4通道 · 16-bit/channel · Alpha ✓`。**RGB8=24 bits/pixel、RGBA8=32、RGB16=48、RGBA16=64**；24 位 RGB 不是每通道 24 位。

16 位源帧和源对齐缓存保留 uint16；整画布缩放和预乘 Alpha 使用 float32。生成最终 Sprite 帧时，RGB 和 Alpha 均按 `round(value / 257)` 从 0..65535 映射为 0..255，不取低 8 位、不直接强转。UI 明确提示源位深与最终预览/输出 RGBA8；最终帧的 Preview、Sheet 和 PNG 导出仍逐像素一致。“导出源尺寸 RGBA 帧”保留源缓存位深，16 位序列会导出 16 位源 PNG。

如果选择“需要使用 Root / Motion / Align 处理”，仍保留原始 Alpha 并跳过抠像，然后在锚点页设置源 Root、使用原有运动及对齐流程。不能把已处理图片再次套用绿幕色键。

帧序列导入和导出**不需要 FFmpeg**。项目保存 `input_mode`、`sequence_folder`、`sequence_fps`、`passthrough_alignment`、尺寸处理策略及自然排序文件清单，继续兼容 V0.1～V0.3 视频工程。已有角色项目可包含视频和帧序列动画；直通动画保留 Profile 数据但不应用其变换。

预览与导出共享 FinalFrameProvider。预览 FPS 仅改变观看速度；导入页“动画帧率”改变实际导出 FPS，不改图像缓存。直通模式的 Root/Confidence 显示“已跳过”，Godot JSON 中对应测量为 `null`，Root Motion JSON 标明 `available=false`，不会伪造跟踪数据。

示例：`examples/sequence_idle.aivsprite` 和 `examples/sequence_idle/`，包含 22 张已对齐 RGBA 图像。V0.4 第一阶段支持单个动画文件夹；父目录自动发现多个 Animation Clip 留到第二阶段，当前请逐个选择动画子文件夹。

## 建立角色基准并添加动画

本节对齐规则用于完整处理的视频和选择“需要处理”的序列。**视频抠像直通和已对齐序列直通均不应用 Character Profile 对齐**。

| 数据 | 范围 | 行为 |
| --- | --- | --- |
| Alpha Bounding Box / Alpha 边界 | 单帧实际像素范围 | 随姿态变化，绿色实线 |
| Character Reference Box / 角色基准框 | 整个角色项目 | 用户确定后固定，蓝色虚线；允许单独调整宽度 |
| Canonical Root / 标准根节点 | 整个角色项目 | 所有动画共用固定坐标，粉色十字；X 始终等于 Y 轴 X |

1. 导入 Idle（待机），调整并完成抠像，选择 **“继续 Root / 运动处理”**。在“锚点”页点击 **“角色坐标系 / 基准框”**。
2. 软件识别身体并提出站地位置。拖动整张第一帧确认角色站在金色地面原点上、位于 Y 轴附近。此操作只移动图像，不移动坐标系。
3. 点击“设置标准根节点”，在身体上选择稳定点。**无论点击位置的 X 是多少，保存的 X 都强制吸附至 Y 轴**。若吸附点在角色外，需移动整帧再设置。
4. 拖动任一蓝色左右控制柄或输入基准框宽度。两侧始终对称；选择朝向，点击 **“设为角色基准”**。
5. 保存工程。此后导入 Run / Attack / Jump 等视频会加入当前角色项目；左侧动画列表可切换已导入动作。
6. 每个新视频在第 0 帧设置该素材的跟踪 Root，再构建。这个点是源视频跟踪种子，不会改变项目 Canonical Root。所有最终帧的 Root X/Y 均等于项目标准值，X 与 Y 轴完全一致。

项目只保存一份 `CharacterProfile`：`canvas_size`、`character_scale`、`ground_origin`、`canonical_root`、派生 `canonical_root_offset`、`reference_box_half_width`、`facing`。空间坐标使用最终画布像素，1536→512 的角色比例为 `1/3`。

基准框底边中心固定在 Ground Origin；顶边为画布顶边。左右边界始终为 `origin_x ± reference_box_half_width`，不分别存储左右边界。确认后，坐标系窗口仅允许修改框宽，不允许改动角色比例、地面原点或标准根节点。

角色项目使用统一原地对齐：`tracked_root = raw_root × character_scale`，`character_correction = canonical_root - tracked_root`。源分辨率整帧平移后再统一缩放。**后续动画绝不会按 Alpha 边界重新找水平中心、重新缩放或重新站地**。固定配置的输出尺寸、比例和对齐选项会锁定。

超出基准框只提示 **“超出角色基准框”**。扩大框宽不会重建图像，缓存 PNG 内容保持不变；脚或特效低于 Ground 的垂直越界仍会警告。越出实际画布则同时报告裁切；扩大参考框不扩大实际画布。原始 Root Motion 与平滑运动数据始终独立保存，供游戏状态机参考。

角色坐标系及最终预览显示地面原点、X/Y 轴、标准根节点、项目基准框；逐帧 Alpha 边界可独立显示。辅助线不写入 PNG。无 Character Profile 的旧工程继续使用下列分轴策略及画布设置。

## 1536×1536 → 512×512（未建立角色配置的工作流）

1. **导入**：导入或拖入视频。识别到 1536×1536 时，自动启用“统一源画布”，目标 512×512，保持宽高比。
2. **抠像**：调整颜色容差、边缘柔化、去绿边等参数，点击“处理全部帧”。抠像始终在源分辨率完成。
3. **锚点**：在第 0 帧点击身体稳定位置作为 Root；必要时在后续帧添加手动修正。可以用两个对角点定义身体跟踪 ROI。
4. **运动**：选择动作预设，分别配置 X/Y；按需设置跳跃阶段、平滑窗口、循环漂移校正和地面 ROI。
5. **对齐**：新分轴策略启用时，在“运动”页配置规则。关闭它可使用兼容旧工程的三种对齐模式。
6. **精灵图**：选择“统一源画布”，目标宽高均为 512，使用“512×512（原尺寸 1/3）”。设置每行帧数，点击“分析 / 构建”。
7. **动画预览 / 导出**：先播放最终游戏帧检查效果，再导出。精灵图顶部、精灵图属性页和导出页均可打开预览。

处理顺序严格为：

```text
Decode → Chroma Key（1536）→ Root Tracking（1536）→ Motion / Alignment（1536）
       → Canvas Normalize（512）→ Final Sprite Cell → Sprite Sheet / Preview / Export
```

统一画布模式对**完整 RGBA 源画布**缩放，不按 Alpha Bounding Box 裁切角色。1536 到 512 的 X/Y 缩放均为 `1/3`，所有帧共享同一个归一化变换；运动补偿按各帧 Root 计算。缩小时优先 `INTER_AREA`，预乘 Alpha 后重采样，再恢复直通 RGBA，防止透明区域 RGB 污染边缘。

22 帧、每行 10 帧时，最终 22 张图片均严格为 **512×512**，精灵图严格为 **5120×1536**；最后 8 格透明。不同宽高比时以透明留白保持比例。运动补偿若把内容移出固定源画布，会报告裁切；不会偷偷缩放或裁剪后再放大。可调整运动策略、Root 或改用自动边界模式。

## 运动处理

下列可选视觉策略适用于尚未建立角色配置的项目。确认角色配置后，X/Y 的有效视觉策略统一为 EXTRACT（原地）；曲线平滑、跳跃阶段及原始运动数据仍保留。

保留 `raw_root`、`filtered_root`、`target_root`；图像补偿为 `target_root - raw_root`。只平滑轨迹，不模糊动作图像。单帧异常值与持续加速分别处理。曲线页显示原始、平滑、目标三条轨迹，支持滚轮缩放、拖动平移和点击选帧，与主时间轴同步。

| 预设 | X | Y |
| --- | --- | --- |
| 待机 | 锁定 | 地面锁定 |
| 行走、奔跑、冲刺、地面攻击 | 提取 Root Motion | 地面锁定 |
| 跳跃、下落、空中攻击 | 提取 Root Motion | 提取 Root Motion |
| 过场运动 | 保留 | 保留 |

“锁定”固定视觉 Root；“保留”保留经过滤波的位移；“提取”生成原地 Sprite，同时在 `root_motion.json` 中保留位移。X 轴没有地面锁定，因为地面约束属于 Y 轴。

起跳、最高点、落地帧从 **0** 编号，`-1` 表示未指定。起跳至落地期间会将 Y 地面锁定切换为提取；跳跃/下落/空中攻击预设未指定阶段时也不会全程贴地。曲线和 Root Motion JSON 保留跳跃高度。

跟踪使用 Alpha 内的身体区域、Shi–Tomasi 特征、Lucas–Kanade 光流、RANSAC 部分仿射或仅平移。置信度综合特征有效率、内点率、重投影误差、Alpha 重合度。失败时依次尝试相位相关、有限且衰减的运动预测，并标记警告。

地面检测只检查身体下半部 ROI 内的主要连通区域，忽略小区域和缺乏横向支撑的细尖。武器、披风或特效侵入时，可在“运动”页点击“定义地面检测区域”，用两个对角点框住下半身和脚。它是几何启发式检测，不是语义人体分割。

循环漂移校正减去 `drift * i/(N-1)`，使视觉曲线首尾一致。提取的累计位移使用校正前轨迹，Run/Dash 的运动数据不会因此归零。

## 独立动画预览

预览是非模态窗口，可关闭并返回编辑。默认播放 `FinalFrameProvider` 提供的最终缓存帧，与导出的 PNG 使用同一来源；不重新解码视频，没有另一套缩放或对齐算法。

- 播放/暂停、上一/下一帧、首/末帧、时间轴。快捷键：空格、左右方向键、Home、End。
- 源 FPS、6/8/10/12/15/20/24/30/60 或自定义。只改变预览速度，不改变输出帧或导出 FPS。
- 循环、棋盘格/黑/白/自定义背景、适应窗口、100%/200%/400%、滚轮缩放、拖动平移。
- Root、固定地面线、Alpha 边界、画布边界、帧号、Root 轨迹；叠加仅用于预览，不写入 PNG。
- 修正前后切换：源尺寸抠像帧 / 最终游戏帧。洋葱皮显示前后帧；动作残影显示前 4 帧。
- 循环衔接检查只播放末 3 帧和首 3 帧：22 帧时为 `19 → 20 → 21 → 0 → 1 → 2`。
- 警告列表可点击跳帧：Root 跳变、低置信度、Alpha 边界/尺寸突变、裁切、循环首尾不连续。

修改影响画面的参数后，旧预览会停止并提示重新构建。导出完成后出现“打开动画预览”提示，预览中也可打开导出目录。警告基于轨迹和边界阈值；形体细节或姿态接缝仍需观看检查。

## 导出与 Godot

“导出到 Godot”在新文件夹内生成：

```text
sprite_sheet.png
frames/0000.png ... 0021.png
animation.json        # SpriteFrames 可用的帧区域、FPS、循环、Root、Ground、BBox 元数据
root_motion.json      # 可选世界运动参考：time、delta、cumulative、confidence
```

完整处理的 EXTRACT / Character Profile 模式输出原地 SpriteFrames；直通模式保留输入画布中的位移。世界移动由 `CharacterBody2D` 状态机负责。**不会创建直接修改 CharacterBody2D.position 的 Animation**。目前提供 PNG 和 JSON 适配数据，未生成原生 `.tres`。

统一源画布模式中，`cell_width/height=512`；每帧 `root/target_root`、`bbox`、`ground` 均为最终单帧坐标。`raw_root/filtered_root` 是同一比例下、补偿前的轨迹。bbox 为 `[left, top, right, bottom)`，按最终像素量化；Root/Ground 为浮点坐标。Root Motion 差分和累计值以目标像素计量，不含对齐偏移。

“导出原尺寸 RGBA 帧”是单独的抠像素材出口，保存到 `frames_rgba/frame_000000.png`，不进行最终输出缩放。新项目导出的是适配后的项目工作画布；旧工程导出原素材尺寸。

应用角色基准时，`animation.json` 同时携带项目级 `character_profile`，逐帧 `tracked_root` 与 `character_correction`；每帧 `root` 严格等于 Canonical Root。`root_motion.json` 另含 `raw_delta_x/y`、`raw_cumulative_x/y`，保留未平滑的原始轨迹位移；已有 `delta/cumulative` 保存平滑后的运动。二者都不会因为原地对齐而删除。直通动画可保留 Profile 数据，但 `character_profile_applied=false`，不会将其作为实际对齐结果。

## 工程、验证与限制

旧 `.aivsprite` 可直接打开，缺失新字段时保留旧版对齐行为。新导入视频默认启用运动策略。工程保存参数和元数据，不嵌入像素；缓存可重建。保存工程后缓存位于工程旁 `cache/<project-id>/`，未保存工程用系统临时目录。角色项目的后续动画使用 `animations/<animation-id>/` 子缓存；另存为时复制整个项目所有动画的缓存。切换动画保留各自动作参数和手动跟踪种子，共用唯一角色配置。

示例：`examples/demo.aivsprite` 为旧版兼容示例；`examples/normalized_512.aivsprite` 为 22 帧、1536 源、512 输出示例；`examples/character_profile.aivsprite` 在相同素材上建立了固定角色坐标系。打开后点击“分析 / 构建”。这些是合成素材，不是实际 AI 视频。

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m scripts.check_i18n
.venv\Scripts\python.exe scripts/smoke_gui.py
.venv\Scripts\python.exe scripts/smoke_upgrade.py .test-output/upgrade-new
.venv\Scripts\python.exe scripts/smoke_character_space.py .test-output/character-new
.venv\Scripts\python.exe scripts/smoke_sequence.py .test-output/sequence-new
.venv\Scripts\python.exe -m app.main --smoke-keyed-passthrough examples/keyed_passthrough_56.aivsprite --smoke-output .test-output/keyed-video-new
.venv\Scripts\python.exe -m app.main --smoke-project-canvas .test-output/project-canvas-new
.\build.ps1
```

打包默认输出dist；若目标成品正在运行，脚本会在写入前停止。可用 `.\build.ps1 -DistPath release-v0.4-canvas` 指定工作区内的独立目录，无需关闭当前程序。

已验证 Windows x64 / Python 3.12.14：114 项测试，保留之前 101 项；新增视频直通隔离、Jump/Dash 位移、统一变换、逐像素导出、UI 模式切换和保存重开覆盖。真实 Qt 56 帧视频抠像→直通→预览→导出→重开→恢复完整处理通过。此前序列、新建项目、位深、目录选择、角色校准和多动画共享基准验证保留。完整记录见 `VALIDATION.md`。

真实 AI 视频的遮挡、绿色服装、剧烈形变仍可能需要调参和手动 Root 修正。可变帧率保留全部源帧，动画使用平均 FPS。大图使用磁盘临时栅格，单帧上限 6400 万像素；缓存暂无自动容量清理。日志位于启动目录 `logs/app.log`，不可写时回退到 `%LOCALAPPDATA%/AI Video to Sprite/logs/`。

架构见 `ARCHITECTURE.md`；进度见 `TASKS.md`。
