# ComfyUI 依赖修复与模型清理报告（第一轮，未删除任何文件）

- 生成时间：2026-09-16 16:49:46
- ComfyUI：`E:\comfyui\ComfyUI-aki-v3.2\ComfyUI`（v0.34.3，Python 3.13.11，torch 2.13.0+cu130，RTX 3090）
- 工作流：`video_minimax_h3_r2v`（模板）+ `双采全能参考工作流｜MINIMAX H3｜文生_图生_视频生视频.json`（实际在用）
- 本轮未删除、未移动、未覆盖任何模型文件；未升级 ComfyUI / CUDA / PyTorch。

## 1. 节点安装结果（9 个仓库）
| 安装目录 | GitHub 仓库 | commit/版本 | 覆盖的缺失节点 | 依赖处理 |
|---|---|---|---|---|
| ComfyUI-KJNodes | kijai/ComfyUI-KJNodes | d3cfe2162 | GetNode/SetNode(前端)、MiniMaxH3MemoryEfficientSageAttentionPatch、LoraLoaderBypassModelOnly 由核心提供 | pip: color-matcher, mss（opencv 已有 4.13 contrib-headless） |
| ComfyUI_LayerStyle | chflame163/ComfyUI_LayerStyle | main tarball | LayerUtility: ImageScaleByAspectRatio V2 等 | pip: blend_modes, colour-science, loguru（torch 未改动，dry-run 验证） |
| comfyui-minimax-h3-audio-T8 | T8mars/comfyui-minimax-h3-audio-T8 | main tarball | MiniMaxH3AudioConditioningT8 / DualClockSamplerT8 / AVDecodeT8 / LearnedLatentUpscaleT8Advanced / TwoPass* 等 7 个类 | 无额外依赖 |
| BSAI-ComfyUI-Sol-H3 | xm6018924/BSAI-ComfyUI-Sol-H3 | 1f616716 | SolAttnMiniMax（内置副本）；未运行 install.py（避免下载工作流未引用的 300MB LoRA） | 无 requirements；comfy_kitchen.sol_attn 缺失时自动回退 |
| ComfyUI_Comfyroll_CustomNodes | Suzie1/ComfyUI_Comfyroll_CustomNodes | d78b780a | CR Prompt Text | 无依赖 |
| ComfyUI-Jjk-Nodes | jjkramhoeft/ComfyUI-Jjk-Nodes | b3c99bb7 | JjkText | 无依赖 |
| rgthree-comfy | rgthree/rgthree-comfy | 2c5342a8 | Fast Groups Bypasser（前端节点） | 无依赖 |
| Goohaitools-comfyui | goohai/Goohaitools-comfyui | 951b5510 | 孤海注释（前端节点） | pip: dlib-bin（opencv 用已有 contrib-headless，mediapipe 已有） |
| comfyUI-solarL-Zip | wzcnly/comfyUI-solarL-Zip | 3ad554f7 | solarL_SaveImagesToZip | pip: soundfile |

说明：`ComfyUI-KJNodes` 与截图中的 `kijai/ComfyUI-KJNodes` 是同一仓库，仅安装一份；`GetNode/SetNode`、`Fast Groups Bypasser`、`孤海注释` 为纯前端节点，由上述仓库的前端 JS 提供；`LoraLoaderBypassModelOnly` 已存在于 ComfyUI 核心，无需安装。

**需要重启 ComfyUI 后新节点才会被加载。**

## 2. 模型下载结果
| 文件 | 目录 | 来源 | 结果 | 建议 |
|---|---|---|---|---|
| qwen_image_vae.safetensors | models/vae/ | ModelScope circlestone-labs/Anima（内容=Civitai 官方，SHA256 A70580F0…） | OK 253,806,246 B | KEEP |
| qwen_3_06b_base.safetensors | models/text_encoders/ | ModelScope circlestone-labs/Anima（内容=Civitai 官方，SHA256 CD2A5120…） | OK 1,192,135,096 B | KEEP |
| anima_baseV10.safetensors | models/diffusion_models/ | ModelScope circlestone-labs/Anima（anima-base-v1.0，SHA256 BD43B7CF…=Civitai 版） | OK 4,182,218,328 B | KEEP |
| minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors | models/loras/ | hf-mirror/ModelScope Comfy-Org/MiniMax-H3（SHA256 5B9AB5AD…，LoRA 头校验有效；HF 元数据当前标注 a3eb4468，两镜像实际内容一致为 5B9AB5AD） | OK 1,956,193,000 B | KEEP |

## 3. 仍然缺失的内容（MANUAL_DOWNLOAD_REQUIRED / 需要用户处理）

### 3.1 Civitai 模型（本机网络无法访问 civitai.com 下载域，需你在浏览器/代理下下载后放入对应目录）
| 文件 | 目录 | 下载链接 | 校验 |
|---|---|---|---|
| Qwen_Esmeralda_v1_000004000.safetensors | models/loras/ | https://civitai.com/api/download/models/2841069 | SHA256 58AAC5C4…（442MB） |
| King_and_Mockingbird_style_qwen.safetensors | models/loras/ | https://civitai.com/api/download/models/2694988 | SHA256 D5B44EAC…（295MB） |
| mastermerlin_qwen_Buick-Riviera_Custom_1965.safetensors | models/loras/ | https://civitai.com/api/download/models/2121875 | SHA256 57C6FB23…（295MB） |
| kaguuya_style_qwen2512.safetensors | models/loras/ | https://civitai.com/api/download/models/2730574 | SHA256 C70F04D7…（295MB） |

### 3.2 单词名风格 LoRA（来源不唯一，按“不要猜”原则不自动下载）
- `Breezy.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Cocoa.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Comet.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Doodle.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Mochi.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Nibble.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Pebble.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Pixel.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Sprout.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Sushi.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Twinkle.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）
- `Waffle.safetensors` → 放入 `models/loras/`（疑似工作流作者重命名的风格包，需向工作流作者索取原始下载）

### 3.3 缺失输入文件（不会自动下载替代图片/音频）
主工作流 6 张参考图 + 3 个参考音频（哈希文件名，磁盘已不存在），以及模板工作流 2 张图（red_superboy_on_city_roof.png、mecha_dragon_lightning.png）。请在 ComfyUI 中重新选择/上传这些文件。

## 4. 空间统计与分类

- ComfyUI models 总大小：740.6 GB（82 个模型文件，含重复副本目录）
- 当前工作流必需（A_CURRENT_WORKFLOW_REQUIRED）：12 个文件，113.8 GB
- 依赖必需（B_DEPENDENCY_REQUIRED）：7 个文件，113.0 GB
- 其他工作流使用（C_USED_BY_OTHER_WORKFLOWS）：8 个文件，181.2 GB
- 未引用的重复副本（可清理）（E_DUPLICATE_NOT_REFERENCED）：20 个文件，55.1 GB
- 高可信孤立模型（可清理）（E_HIGH_CONFIDENCE_ORPHAN）：35 个文件，277.5 GB

- 若删除全部 DELETE_CANDIDATE（重复副本 + 高可信孤立）：可释放约 332.6 GB
- 若只删除高可信孤立模型（不含重复副本目录）：可释放约 277.5 GB

## 5. 模型清单与建议（按大小降序）

| 序号 | 模型 | 路径 | 大小 | 当前工作流使用？ | 其他工作流使用？ | 判断依据 | 建议 |
|---|---|---|---|---|---|---|---|
| 1 | minimax_h3_fl2va_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_fl2va_bf16.safetensors | 66.28 GB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\16-raven-streaming\2026-08-23_H3_RAVEN_Streaming_T2VA_Guarded_Advanced_EXP.json | KEEP |
| 2 | minimax_h3_ref2va_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_ref2va_bf16.safetensors | 66.28 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 3 | qwen3vl_32b_minimax_h3_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\qwen3vl_32b_minimax_h3_bf16.safetensors | 51.51 GB | 否 | 否 | 依赖必需 | KEEP |
| 4 | 10Eros_Max_h3_fl2va_beta1_pruned.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\10Eros_Max_h3_fl2va_beta1_pruned.safetensors | 40.22 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 5 | minimax_h3_ref2va_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_ref2va_int8_convrot.safetensors | 34.04 GB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\03-image-video-edit\2026-08-10_H3_Ref2VA_Visual_Reference_Strength_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\03-image-video-edit\2026-08-28_H3_CADS_Visual_Reference_Annealing_Advanced_EXP.json | KEEP |
| 6 | minimax_h3_fl2va_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_fl2va_int8_convrot.safetensors | 34.04 GB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V10A.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V8A.json | KEEP |
| 7 | FeiHou_MiniMax-H3_Remix_v0.6_int8_convrot_v2.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\FeiHou_MiniMax-H3_Remix_v0.6_int8_convrot_v2.safetensors | 34.00 GB | 是 | 否 | 当前工作流必需 | KEEP |
| 8 | ltx-2.3-22b-dev-fp8.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\checkpoints\ltx-2.3-22b-dev-fp8.safetensors | 29.15 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 9 | qwen3vl_32b_minimax_h3_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\qwen3vl_32b_minimax_h3_int8_convrot.safetensors | 27.14 GB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\27-video-outpaint\2026-09-07_H3_Video_Outpaint_01_Generate_Candidate_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\27-video-outpaint\2026-09-07_H3_Video_Outpaint_06_Generate_Guided_Candidate_EXP.json | KEEP |
| 10 | DasiwaMinimaxH3_dasiwaREF2VAHybridV1.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\DasiwaMinimaxH3_dasiwaREF2VAHybridV1.safetensors | 20.97 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 11 | minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors | 20.97 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 12 | minimax_h3_fl2va_pruned_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors | 20.97 GB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\03-image-video-edit\2026-08-22_H3_LanPaint_AV_Local_Repair_Advanced_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\04-long-video\2026-08-27_H3_In_Node_Long_Video_Prompt_Relay_EAV_Stock20_Advanced_EXP.json | KEEP |
| 13 | minimax_h3_ref2va_pruned_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_ref2va_pruned_int8_convrot.safetensors | 20.97 GB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\03-image-video-edit\2026-08-07_H3_Still_Edit_22Frames_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\05-speech-dialogue\2026-08-09_H3_Speech_Joint_Dialogue_Stock20_EXP.json | KEEP |
| 14 | minimax_h3_fl2va_pruned_int8_convrot.safetensors | E:\comfyui\models\diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors | 20.97 GB | 否 | 是 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\03-image-video-edit\2026-08-22_H3_LanPaint_AV_Local_Repair_Advanced_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\04-long-video\2026-08-27_H3_In_Node_Long_Video_Prompt_Relay_EAV_Stock20_Advanced_EXP.json | DELETE_CANDIDATE |
| 15 | minimax_h3_fl2va_pruned_fp8_scaled.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_fp8_scaled.safetensors | 20.96 GB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\15-sla-attention\2026-09-02_H3_SLA_Precision_V2_FL2VA_FP8_8Step_Advanced_EXP.json | KEEP |
| 16 | minimax_h3_ref2va_pruned_fp8_scaled.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_ref2va_pruned_fp8_scaled.safetensors | 20.96 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 17 | minimax_music3_text_encoder_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\minimax_music3_text_encoder_bf16.safetensors | 18.47 GB | 否 | 否 | 依赖必需 | KEEP |
| 18 | minimax_music3_text_encoder_pruned_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\minimax_music3_text_encoder_pruned_bf16.safetensors | 16.71 GB | 否 | 否 | 依赖必需 | KEEP |
| 19 | qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | 15.69 GB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V10A.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V8A.json | KEEP |
| 20 | qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | E:\comfyui\models\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors | 15.69 GB | 是 | 是 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V10A.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V8A.json | DELETE_CANDIDATE |
| 21 | gemma_3_12B_it_fpmixed.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\gemma_3_12B_it_fpmixed.safetensors | 13.71 GB | 否 | 否 | 依赖必需 | KEEP |
| 22 | minimax_h3_fl2va_pruned_w4a8_mixed.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_fl2va_pruned_w4a8_mixed.safetensors | 12.54 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 23 | minimax_h3_ref2va_pruned_w4a8_mixed.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_h3_ref2va_pruned_w4a8_mixed.safetensors | 11.77 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 24 | minimax_music3_dit_fp32.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_music3_dit_fp32.safetensors | 9.83 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 25 | minimax_music3_text_encoder_pruned_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\minimax_music3_text_encoder_pruned_int8_convrot.safetensors | 9.20 GB | 否 | 否 | 依赖必需 | KEEP |
| 26 | ltx-2.3-22b-distilled-lora-384.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\ltx-2.3-22b-distilled-lora-384.safetensors | 7.61 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 27 | minimax_h3_video_vae_fp16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\vae\minimax_h3_video_vae_fp16.safetensors | 5.21 GB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V10A.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V8A.json | KEEP |
| 28 | minimax_h3_video_vae_fp16.safetensors | E:\comfyui\models\vae\minimax_h3_video_vae_fp16.safetensors | 5.21 GB | 是 | 是 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V10A.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V8A.json | DELETE_CANDIDATE |
| 29 | minimax_music3_dit_fp16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_music3_dit_fp16.safetensors | 4.91 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 30 | model-00001-of-00002.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-ASR\Qwen3-ASR-1.7B\model-00001-of-00002.safetensors | 4.22 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 31 | anima_baseV10.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\anima_baseV10.safetensors | 4.18 GB | 是 | 否 | 当前工作流必需 | KEEP |
| 32 | model.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-Base\model.safetensors | 3.86 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 33 | minimax_h3_video_vae_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\vae\minimax_h3_video_vae_int8_convrot.safetensors | 3.17 GB | 否 | 是 | 依赖必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\BSAI-ComfyUI-Sol-H3\workflows\SolH3_FastH3_FilmFactory.json | KEEP |
| 34 | minimax_music3_dit_int8_convrot.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\diffusion_models\minimax_music3_dit_int8_convrot.safetensors | 2.50 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 35 | anything-v5-PrtRE.safetensors | E:\comfyui\models\anything-v5-PrtRE.safetensors | 2.13 GB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 36 | minimax_h3_fl2v_turbo_4step_v0.1_comfyui_alpha8-T8-convert.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_turbo_4step_v0.1_comfyui_alpha8-T8-convert.safetensors | 1.96 GB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\04-long-video\2026-08-20_H3_Prompt_Relay_Long_Video_Turbo8_Advanced_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\06-face-refine\2026-08-09_H3_Face_Refine_Parity_Advanced_EXP.json | KEEP |
| 37 | minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors | 1.96 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 38 | minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors | 1.96 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 39 | minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors | 1.96 GB | 是 | 否 | 当前工作流必需 | KEEP |
| 40 | minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors | 1.96 GB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\24-mv-lipsync\2026-09-01_H3_Local_MV_VocalLock_V3_Official_Ref2V_Turbo4_Advanced_EXP.json | KEEP |
| 41 | minimax_h3_fl2v_turbo_4step_v0.1_768p_sla_comfyui_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_turbo_4step_v0.1_768p_sla_comfyui_bf16.safetensors | 1.96 GB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\15-sla-attention\2026-08-22_H3_LightX2V_SLA_FL2VA_4Step_Advanced_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\15-sla-attention\2026-08-22_H3_LightX2V_SLA_KJ_Sage_Composer_FL2VA_4Step_Advanced_EXP.json | KEEP |
| 42 | minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors | 1.96 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 43 | minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_turbo_4step_v1.1_768p_comfyui_bf16.safetensors | 1.96 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 44 | minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors | 1.96 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 45 | model.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-ASR\Qwen3-ASR-0.6B\model.safetensors | 1.88 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 46 | model.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-ASR\Qwen3-ForcedAligner-0.6B\model.safetensors | 1.84 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 47 | model.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-TTS\Qwen3-TTS-12Hz-0.6B-Base\model.safetensors | 1.83 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 48 | qwen_3_06b_base.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\text_encoders\qwen_3_06b_base.safetensors | 1.19 GB | 是 | 否 | 当前工作流必需 | KEEP |
| 49 | LTX-2.3-ID-LoRA-CelebVHQ-3K-V1.0.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\LTX-2.3-ID-LoRA-CelebVHQ-3K-V1.0.safetensors | 1.16 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 50 | ltx-2.3-ID-LoRA-TalkVid-3k-V1.0.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\ltx-2.3-ID-LoRA-TalkVid-3k-V1.0.safetensors | 1.16 GB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 51 | ltx-2.3-spatial-upscaler-x2-1.1.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\latent_upscale_models\ltx-2.3-spatial-upscaler-x2-1.1.safetensors | 949.6 MB | 否 | 是 | 其他工作流使用；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\ComfyUI-LTXVideo\example_workflows\2.3\LTX-2.3_ICLoRA_Lipdub_Two_Stage_Distilled.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\ComfyUI-LTXVideo\example_workflows\2.3\LTX-2.3_T2V_I2V_Two_Stage_Distilled.json | KEEP |
| 52 | control_v11f1e_sd15_tile_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11f1e_sd15_tile_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 53 | control_v11e_sd15_ip2p_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11e_sd15_ip2p_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 54 | control_v11e_sd15_shuffle_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11e_sd15_shuffle_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 55 | control_v11f1p_sd15_depth_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11f1p_sd15_depth_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 56 | control_v11p_sd15_canny_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_canny_fp16.safetensors | 689.1 MB | 否 | 是 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本；其他引用：E:\comfyui\入门工作流\ComfyUI_Workflows\guided_composition\canny.json; E:\comfyui\入门工作流\ComfyUI_Workflows\image_conditioning\experiments\IPAdapter_canny.json | DELETE_CANDIDATE |
| 57 | control_v11p_sd15_inpaint_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_inpaint_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 58 | control_v11p_sd15_lineart_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_lineart_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 59 | control_v11p_sd15_mlsd_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_mlsd_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 60 | control_v11p_sd15_normalbae_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_normalbae_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 61 | control_v11p_sd15_openpose_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_openpose_fp16.safetensors | 689.1 MB | 否 | 是 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本；其他引用：E:\comfyui\入门工作流\ComfyUI_Workflows\guided_composition\pose.json; E:\comfyui\入门工作流\ComfyUI_Workflows\guided_composition\experiments\multiple_controlnets.json | DELETE_CANDIDATE |
| 62 | control_v11p_sd15_scribble_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_scribble_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 63 | control_v11p_sd15_seg_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_seg_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 64 | control_v11p_sd15_softedge_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15_softedge_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 65 | control_v11p_sd15s2_lineart_anime_fp16.safetensors | E:\comfyui\models\ControlNet\control_v11p_sd15s2_lineart_anime_fp16.safetensors | 689.1 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 66 | minimax_h3_latent_upscaler_3d_fp16.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\latent_upscale_models\minimax_h3_latent_upscaler_3d_fp16.safetensors | 658.6 MB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\04-long-video\2026-09-11_H3_Dual_Model_Long_Video_4plus4_Plain_EXP.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\04-long-video\2026-09-11_H3_Dual_Model_Long_Video_4plus4_Relay_EXP.json | KEEP |
| 67 | model.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-TTS\Qwen3-TTS-12Hz-0.6B-Base\speech_tokenizer\model.safetensors | 650.7 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 68 | model.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-Base\speech_tokenizer\model.safetensors | 650.7 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 69 | LTX2.3_Reasoning_V1.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\LTX2.3_Reasoning_V1.safetensors | 643.0 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 70 | minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors | 591.6 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 71 | minimax_h3_turbo_v4_step600_pruned_comfyui.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\minimax_h3_turbo_v4_step600_pruned_comfyui.safetensors | 591.6 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 72 | minimax_h3_audio_vae_fp32.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\vae\minimax_h3_audio_vae_fp32.safetensors | 577.2 MB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V10A.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V8A.json | KEEP |
| 73 | minimax_h3_audio_vae_fp32.safetensors | E:\comfyui\models\vae\minimax_h3_audio_vae_fp32.safetensors | 577.2 MB | 是 | 是 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V10A.json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\custom_nodes\comfyui-minimax-h3-audio-T8\examples\workflows\01-basic-generation\2026-08-06_H3_Turbo_EXP_4V8A.json | DELETE_CANDIDATE |
| 74 | model-00002-of-00002.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\Qwen3-ASR\Qwen3-ASR-1.7B\model-00002-of-00002.safetensors | 456.0 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 75 | flux-ae.safetensors | E:\comfyui\models\vae\flux-ae.safetensors | 319.8 MB | 否 | 否 | 未引用的重复副本（可清理）；E:\comfyui\models 未被 ComfyUI 引用（无 extra_model_paths.yaml），与主 models 目录构成重复副本 | DELETE_CANDIDATE |
| 76 | qwen_image_vae.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\vae\qwen_image_vae.safetensors | 242.0 MB | 是 | 是 | 当前工作流必需；其他引用：E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\blueprints\Image Edit (Qwen 2511).json; E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\blueprints\Image Inpainting (Qwen-image).json | KEEP |
| 77 | minimax_music3_dav.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\vae\minimax_music3_dav.safetensors | 206.7 MB | 否 | 否 | 依赖必需 | KEEP |
| 78 | wushu_action_h3_lora_v4_2000_pruned.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\wushu_action_h3_lora_v4_2000_pruned.safetensors | 147.9 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 79 | wushu_spatial_physics_v2_1000_pruned.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\loras\wushu_spatial_physics_v2_1000_pruned.safetensors | 147.9 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 80 | taeh3.safetensors | E:\comfyui\ComfyUI-aki-v3.2\ComfyUI\models\vae_approx\taeh3.safetensors | 9.3 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 81 | hand_landmark.onnx | E:\model\hand_landmark.onnx | 3.9 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |
| 82 | palm_detection.onnx | E:\model\palm_detection.onnx | 3.7 MB | 否 | 否 | 高可信孤立模型（可清理） | DELETE_CANDIDATE |

## 6. 建议汇总

- `KEEP`：当前工作流必需、依赖必需、或其他工作流引用。
- `REVIEW`：当前工作流未使用且无其他引用，但无法 100% 排除其他用途（需人工确认）。
- `DELETE_CANDIDATE`：E:\comfyui\models 的未引用重复副本，或高可信孤立模型。**仍不自动删除，等你确认。**

**下一轮（第三阶段）在你明确回复“确认删除”后才会执行：先把 DELETE_CANDIDATE 移入 `ComfyUI/_model_quarantine/YYYY-MM-DD/` 并生成 deletion_manifest.json，仍保留原始目录结构，不永久删除。**
