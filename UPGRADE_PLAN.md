# v0.2 升级约束与原子阶段

1. 模型/运动/归一化：保持旧工程与旧算法入口；加入原始/平滑/目标轨迹、独立轴策略、跳跃阶段、稳健身体地面 ROI。先通过合成算法测试。
2. 跟踪/缓存/导出：源分辨率完成色键与跟踪；光流→相位相关→预测→警告。Root→Motion→源画布 Alignment→统一 Normalize→最终帧。提供 FinalFrameProvider，预览与 PNG 导出共享缓存。
3. 正式 i18n：JSON zh_CN/en_US、缺失键校验、变量模板、简体中文默认、app_settings.json 保存；稳定英文枚举不受显示语言影响。所有控件、对话框、状态、错误均通过翻译系统。
4. UI：运动曲线与 ROI 编辑、归一化设置、非模态最终动画预览；播放/步进/帧率/对比/洋葱皮/残影/循环衔接/警告导航。
5. 全量回归、旧工程迁移、125%/150% DPI、GUI 验收、Windows 重新打包并启动验证。

关键坐标：raw_root、filtered_root、target_root 与 correction 使用源像素；correction=target-root_raw。归一化之后的 cell_root、cell_bbox、cell_ground 与导出的 Root Motion 使用目标像素。原图不缩小后再抠像。

统一画布模式只对完整的源尺寸 RGBA 画布作相同的预乘 Alpha INTER_AREA 缩放，不按任何帧的 bbox 决定 Scale。固定画布不可能容纳任意越界补偿，越界必须显式警告，禁止偷偷改变比例。

EXTRACT 保留独立的 Root Motion 数据。Jump 空中区间覆盖 Ground Lock。循环视觉漂移补偿与提取的连续根运动分开记录，避免抹掉 Run 的位移。

审查角色：架构检查 core/UI/exporter 边界；数据流检查源/目标坐标和缓存依赖；工程检查线程、旧工程、i18n 覆盖与打包资源。不额外引入后端服务或网络依赖。
