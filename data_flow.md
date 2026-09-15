# Data flow

新建项目标准宽高→唯一项目字段→每个动画继承→视频原始decoded / 单张RGBA→CanvasFit(原尺寸,项目尺寸)→raw工作画布→Chroma（仅视频）→Root/Motion/Align或直通→可选输出Normalize→FinalFrameProvider/Preview/Export。原分辨率信息单独保存，Alpha/Root不参与CanvasFit；旧工程none走下面原流程。

source_video → ffprobe metadata → raw_frames/frame_000000.png → keyed_frames/frame_000000.png → FrameData(index, bbox, source_root, confidence, warnings, features) → CellLayout(width,height,target,baseline) + Transform(scale,offset) → aligned_frames/frame_000000.png → sprite_sheet.png / frames/0000.png / frames_rgba/frame_000000.png / animation.json。

工程 JSON 保存参数和结果，不嵌入像素。打开工程后根据路径/文件身份和配置摘要复用或重建缓存。每个阶段完成后更新 manifest，UI 只消费 worker 完成后的快照。参数变更使导出禁用直到对应阶段重算；Columns 只重建 Sheet。

## v0.2

Root 后新增 Motion：raw_root → filtered_root / motion_root → target_root → correction。源尺寸 source_aligned_frames 再进入 CanvasTransform，输出最终 aligned_frames。FinalFrameProvider 为 Sheet、AnimationPreview、PNG 导出提供同一缓存，Root Motion JSON 以目标像素输出差分/累计位移。

显示语言只进入 i18n 和 QWidget；QComboBox itemData 始终传递英文枚举到 Project。ROI、跟踪和曲线以源像素编辑，cell 坐标与运动参考统一使用目标像素导出。预览 FPS、辅助绘制、洋葱皮、残影不回写图像或项目参数。

## v0.3

首次 Idle keyed[0] → 身体/地面站位提议 → 用户整帧平移 → Canonical X 吸附 Y Axis → 保存唯一 CharacterProfile。Profile 的坐标为最终画布像素，跟踪种子由确认时反变换得到。

后续动画导入 → 保留项目 Profile、分配 animation_id/独立缓存 → 新素材源 Root Tracking → tracked_root = raw_root * character_scale → character_correction = canonical_root - tracked_root → 源像素整帧平移 → 统一缩放 → final cell_root = canonical_root → Provider / Export。Alpha Bounds 只报告检测信息和越界，不能改变以上变换。

半宽编辑 → 替换 Profile 半宽 → 更新 Overlay 与越界警告；不进入图像变换签名。Godot metadata 加入 Profile，Root Motion 同时输出 raw 与 filtered 差分/累计量。切换动画时只切换快照，Profile 不复制到动画内部。

## v0.4

文件夹 → 自然排序/头信息扫描 → 用户确认直通或处理、FPS、尺寸策略 → 后台 RGBA raw cache。直通生成完整 final Cell，可选统一 Normalize；处理模式将 raw 作为 keyed 输入 Root/Motion/Align。所有输出继续共享 FinalFrameProvider；序列不使用 FFmpeg。

直通忽略 Profile 变换，Root/Confidence 导出为 null。序列 FPS 只更新时间字段；文件清单、身份、pad 策略进入源签名，显式 Normalize 才进入最终变换。

新建参数 → 名称/画布/目录校验 → 独占工程文件与项目目录 → 空项目首页 → 素材导入继承项目元数据 → Idle 校准建立唯一 Profile。旧快照在切换时注入当前项目字段。

16 位 PNG/TIFF → 原位深解码与 RGB 满 Alpha → uint16 raw PNG →（需要处理时 8 位分析视图 Root；uint16 渲染图 Align）→ float32 预乘缩放 → RGBA8 最终 Cell → 唯一 Provider / Sheet / PNG。源尺寸 RGBA 导出直接复制原位深缓存。

目录入口 → FolderPicker 局部样式/文件模型 → 选择或导航 → 后台序列首帧信息（修订号过滤）→ 确认返回路径。该步骤不修改项目/视频数据或系统主题。

视频 Decode → 源尺寸 Chroma → 用户选择 keyed_passthrough → keyed RGBA → 原画布 / 显式 Normalize → final Cell → 同一 Provider / Sheet / Preview / Export。没有 Root/Motion/Align/Profile 处理，位移保留；Alpha 检测只写 bbox。视频直通签名依赖 key_signature，尺寸变换为全帧公共常量。

启用完整处理 → 恢复此前 canvas_mode → 复用原 keyed cache → Root/Motion/Align。手动种子、动作策略、Profile 保留。processing_mode 保存到动画快照；旧工程 full；切换后旧最终预览失效。

## 编辑结果
原素材→项目画布→抠像→原自动对齐或直通→基础aligned Cell→时间线重映射/实例变换/多轨合成→final PNG+final_timing→FinalFrameProvider→编辑预览/独立预览/Sheet/导出。源帧数独立于输出帧数；秒时长不由预览FPS覆盖。reference轨不合入导出。

## 手工角色参考分支

原素材→既有中心CanvasFit→Key/RGBA→项目固定参考Overlay→用户显式Animation Offset（源画布像素）→既有输出Normalize→原时间线实例变换/合成→FinalFrameProvider→所有预览/导出。Offset直通路径复用keyed/raw，在项目画布透明裁切后输出Resize；ReferenceSource读取原Idle并独立绘制固定Ghost。

## 文件选择路径
AppSettings.path_state→PathMemory.resolve(purpose,project)→统一Qt Picker→业务Worker→成功回调记用途目录/last_location。取消/失败不写。新建project_create独立走有效父目录→E/D/C Work→Home。
