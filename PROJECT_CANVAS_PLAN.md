# V0.4 项目标准画布

目标：新建项目选择标准画布，全项目动画统一先按原始分辨率中心裁剪/补边，再进入 Key/Root/Motion/Align 或直通及输出 Normalize。不缩放，不读取主体/Alpha/Root/Profile 决定位置。此规则优先于之前直通的原画布规则；直通保留适配后的位置。

模块与原子任务：
1. core/canvas_fit：纯整数窗口复制，RGBA 透明补边；视频在 Key 前以原视频首帧估计背景色填充；uint8/uint16 保留；验证五种尺寸和奇数差。
2. Project/workspace：项目级 width/height/fit_mode，创建模板与自定义；动画快照继承而不复制。旧项目为 none/0/0，保持原有像素与坐标，不能无提示迁移已有 Profile。
3. Pipeline：视频 decoded 原始缓存 → raw 项目画布 → keyed；序列直接逐张原始尺寸 → raw 项目画布，不能先放最大画布再适配。video.width/height 为后续处理尺寸，original_size 独立保存。fit 参数参与源处理签名。
4. UI：新建标准画布预设与宽高；导入页和左侧逐帧报告原尺寸/项目尺寸/四侧裁剪补边，序列确认显示规则；混尺寸在项目标准画布模式按每张原尺寸统一适配。
5. 验证：核心与 UI、Root/Alpha 坐标、Profile 坐标来源、Preview/Export 一致、旧项目/缓存、保存/切换，全部回归、实际 Qt 和 Windows 成品。

数据约定：像素索引为整数，偶数差完全对称，奇数差多出1像素在右/下侧；不为精确半像素中心引入插值。标准画布与输出分辨率独立，后续允许统一 Normalize 至512。

三角色预审：架构将 canvas_fit 与 normalizer 分开（前者只窗口复制，后者输出重采样）；数据流区分 original_size、工作画布 video 和最终 Cell，所有跟踪种子点击在工作画布；工程保持旧工程 disabled 默认及原缓存签名，新项目必启用，避免隐藏重复适配和半透明位深丢失。
