# Engine Sound Simulator 源码分析

本文面向本仓库的核心源码（不含 `.venv/`），从模块职责、关键算法与数据流、设备与交互、可视化与测试、以及改进建议几个方面进行梳理。文中路径均为仓库内相对路径，必要处附带行号以便快速定位。

## 一、架构与模块职责

- 核心引擎（Engine/DSP）
  - `engine.py`：引擎运行时模型与音频生成主流程（合成单个发动机循环、缓冲拼接、节气门与转速）。参见 `engine.py:18` 起的 `Engine` 类。
  - `engine_factory.py`：不同发动机布局/点火顺序的预设工厂，组合基础波形为“点火声+间歇声”的时序模板，返回 `Engine` 实例。参见 `engine_factory.py:12` 起的各工厂函数。
  - `synth.py`：原始音频“素片”合成（正弦、锯齿、随机波形、静音）。如 `sine_wave_note` 位于 `synth.py:9`。
  - `audio_tools.py`：缓冲区拼接、叠加、包络/音量归一化、采样片段切片、格式转换等常用 DSP 工具。叠加逻辑 `overlay` 位于 `audio_tools.py:9`。

- I/O 与设备
  - `audio_device.py`：基于 `sounddevice` 的输出设备枚举、默认选择与流式播放（回调式拉流）。关键入口 `AudioDevice.play_stream` 位于 `audio_device.py:169`。

- 交互与应用
  - `controls.py`：键盘/无头回退的节气门输入采集。`capture_input` 位于 `controls.py:33`。
  - `main.py`：应用入口；列出输出设备→可选交互选择→打开音频流→进入输入循环。
  - `mainspectrometer.py`、`spectrometer.py`：频谱可视化演示（一个基于 `sounddevice`/生成流，另一个基于 `pyaudio`/输入流）。

- 配置与工具
  - `cfg.py`：采样率、16bit 上限、合成混合策略等（`cfg.py:1`）。
  - `engine_single_buffer.py`：与 `engine.py` 类似的早期/备用实现，算法形态接近但混音与“unequal”处理稍有不同。
  - `selftest.py`、`audio_devices_test.py`、`test.py`：小工具或演示脚本，验证设备枚举与最小合成路径。

## 二、运行主线与数据流

1) 入口与设备选择
- `main.py:9` 进入 `main()`；默认构建 `boxer_4_crossplane_custom([1,1,0,0])` 引擎（`engine_factory.py:229`）。
- 使用 `AudioDevice` 列出输出设备（`audio_device.py:23`），优先 PipeWire 或默认输出（`audio_device.py:43`），并支持环境变量 `ENGINE_AUDIO_DEVICE` 指定。
- 打开回调式 `sd.OutputStream`（`audio_device.py:218`），回调中每帧拉取 `engine.gen_audio(frames)`（`audio_device.py:181-187`）。

2) 引擎合成主循环
- `Engine.gen_audio(num_samples)`（`engine.py:189`）是“按需取样”的外部接口：
  - 先消耗内部环形缓冲 `_audio_buffer`（`engine.py:192-195`）。
  - 缓冲不足时调用 `_gen_audio_one_engine_cycle()` 产生一个“发动机循环”的完整波形片段（`engine.py:197-200`），并按需拼接/截取补足请求的帧数（`engine.py:204-209`）。
- `_gen_audio_one_engine_cycle()`（`engine.py:69`）是核心 DSP：
  - 根据当前 `rpm` 计算行程速率、单缸“点火时段/非点火时段”的持续时间（`engine.py:70-75`）。
  - 按点火时序（角度）将“点火声 + 间歇声”切片并拼装为每缸缓冲（`audio_tools.slice`，`engine.py:90-92, 154-157`）。
  - 可选“unequal”偏移（毫秒）模拟不等长排气等效应：通过双缓冲 `bufs` 与 `bufsunequal` 叠加并在末尾根据策略合并（`engine.py:94-124, 144-157, 176-187`）。
  - 将多缸缓冲对齐补零后叠加 `overlay`（`audio_tools.py:9-21`），最后转为 16-bit 播放格式 `in_playback_format`（`audio_tools.py:55-56`）。

3) 节气门/转速控制
- `controls.capture_input`（`controls.py:33`）在有 GUI 环境使用 `pynput` 监听键盘按压；否则退回“自动扫门”的无头模式（`controls.py:46-62`）。
- `Engine.throttle(fraction)`（`engine.py:211`）根据节气门开度 0/1 调整 `_rpm`，并在终端打印“RPM ...”（`engine.py:225-226`）。

## 三、关键算法与实现细节

- 点火时序格式转换 `_convert_timing_format`
  - 位置：`engine.py:8-16`。
  - 作用：将“相对上一次点火的角度延迟”转换为“相对第一缸点火的角度位置”，方便在单循环内按绝对时轴切片拼装。

- 单循环合成 `_gen_audio_one_engine_cycle`
  - 按当前转速将角度转时间：`before_fire_duration = (timing[cyl]/180)/strokes_per_sec`（`engine.py:89`），其中每 180° 对应 1 个“冲程”，`strokes` 表示完整循环的冲程数（2 冲程/4 冲程）。
  - 每缸缓冲结构 = `[间歇(前)] + [点火] + [间歇(后)]`，点火用 `_fire_snd` 片段（工厂中生成并包络、归一化，见 `engine_factory.py:8-10`）。
  - 多缸缓冲长度对齐后 `overlay` 叠加；若配置了 `unequal`，则与“unequal 缓冲”按 `cfg.sound_merge_method` 融合（average/max，`engine.py:181-184`）。

- 叠加与归一化 `overlay`
  - 位置：`audio_tools.py:9-21`。
  - 逻辑：复制输入缓冲→逐个求和→调用 `normalize_volume` 将峰值缩放至 16-bit 上限（`audio_tools.py:32-34`）。
  - 注意：`for buf in bufs: buf / len(bufs)` 当前未生效（未就地除法），实际依赖最后的 `normalize_volume` 保障不削顶，可能导致“动态泵动”。建议修正为 `buf /= len(bufs)`，或在叠加后采用感知响度的归一化策略（见“改进建议”）。

- 缓冲与拉流
  - `Engine` 通过 `_audio_buffer` 处理“回调请求帧数与完整循环长度不整除”问题，避免半个循环切割造成的相位/波形突变（`engine.py:33-36, 189-209`）。
  - `AudioDevice.play_stream` 在回调中将一维 `int16` 单声道数据复制到多声道输出（`audio_device.py:181-197, 218-226`），并提供无头 `_NullStream` 以便在无音频后端时不中断（`audio_device.py:169-179, 227-230`）。

## 四、工厂预设与配置

- 预设工厂
  - 典型例子：
    - V 双缸 90°：`v_twin_90_deg()`（`engine_factory.py:12-22`）
    - 直列四缸等间隔：`inline_4()`（`engine_factory.py:46-55`）
    - 水平对置四缸（Subaru 风格），带不等长“unequal”：`boxer_4_crossplane_custom()`（`engine_factory.py:229-243`）
    - 其它：V8 多变、W16、随机节奏、伪转子等。

- 声音素片
  - 统一使用 `_fire_snd = sine(160Hz, 1s)` 并做峰值归一化+指数衰减包络（`engine_factory.py:8-10`）。
  - 间歇声使用 `synth.silence(1)` 充当“静音底”。

- 配置项 `cfg.py`
  - `sample_rate = 44100`、`max_16bit = 32767`、`sound_merge_method = "average"|"max"`（`cfg.py:1-5`）。
  - 运行时相关环境变量：
    - `ENGINE_HEADLESS_AUDIO=1` 无音频后端运行；
    - `ENGINE_AUDIO_DEVICE=<index|substr>` 选择设备；
    - `ENGINE_PREFER_PIPEWIRE=0/1` 是否优先 PipeWire；
    - `ENGINE_AUDIO_CHANNELS=N` 期望输出通道数；
    - `ENGINE_DEBUG=1` 打印设备枚举细节。

## 五、可视化与测试

- `mainspectrometer.py`
  - 尝试用 `matplotlib` 动画显示频谱，但当前将 `stream`（`OutputStream` 对象）直接当作数据使用，频谱计算逻辑并未接入 `engine` 的原始样本，无法正常工作（需改为在回调/环形缓冲中抓取时域片段→FFT）。

- `spectrometer.py`
  - 使用 `PyAudio` 打开输入流（麦克风）进行实时频谱显示，作为参考实现更完整。

- 轻量自检
  - `selftest.py`：设置 `ENGINE_HEADLESS_AUDIO=1`，构建引擎并生成固定长度缓冲，打印形状与字节数，验证“DSP 主链路在无音频后端时可运行”。
  - `audio_devices_test.py`：仅枚举与选择输出设备，不开流，便于在 CI/无声环境排查配置。

## 六、已知问题与改进建议

- 叠加缩放未生效（重要）
  - 位置：`audio_tools.py:14-16`。`buf / len(bufs)` 未写回。应改为就地除法 `buf /= len(bufs)`，或删除该步骤而改为：
    - 叠加后按峰值归一化（保留现状），但会引入“每循环动态变化”；
    - 或采用固定增益+软限幅（soft clipper）/短时 RMS 归一化，保证主观响度稳定。

- `mainspectrometer.py` 数据源错误
  - 当前未从回调/缓冲中获取样本，无法绘制频谱。建议将 `engine.gen_audio(BUFFER)` 的输出暂存为 `numpy.ndarray`，在动画回调中做 `rfft` 后绘图（可参考 `spectrometer.py`）。

- 引擎参数校验与接口
  - `strokes` 限制注释与实现不一致（`engine.py:42` 注释 2/4/3，但未校验）；可补充断言或清晰支持 2/3/4 冲程。
  - `Engine.specific_rpm()` 为空实现（`engine.py:228-230`），可支持外部直接设定目标转速或平滑过渡曲线。

- 声学建模可拓展
  - 目前“点火声=单频正弦+短包络”，听感单薄。可加入：多谐波/噪声层、吸排气/共鸣滤波、转速相关的频移与包络时长、缸间相位抖动等。

- 代码一致性与健壮性
  - `engine_single_buffer.py` 与 `engine.py` 存在重复/分叉实现，建议择优合并或明确弃用路径。
  - `test.py` 体积较大且与主线无关，建议标注为 demo 并精简；或移至 `examples/`。
  - 增加类型标注与文档字符串，便于 IDE/静态检查。

## 七、快速运行与验证

- 环境准备
  - 创建虚拟环境：`python -m venv .venv && source .venv/bin/activate`
  - 安装依赖：`pip install -r requirements.txt`

- 运行主程序
  - `python main.py`（可交互选择输出设备）。无声/CI 环境可：`ENGINE_HEADLESS_AUDIO=1 python main.py`

- 频谱演示
  - 录音频谱（麦克风）：`python spectrometer.py`
  - 生成流频谱（需修复 `mainspectrometer.py` 的数据路径后再运行）。

- 最小自检
  - `python selftest.py`：生成 1024 样本并输出形状/字节数。

## 八、关键 API 速览（文件:行号）

- 引擎
  - `engine.py:18` `class Engine`
  - `engine.py:189` `Engine.gen_audio(num_samples)`
  - `engine.py:69` `Engine._gen_audio_one_engine_cycle()`
  - `engine.py:211` `Engine.throttle(fraction)`

- 工具与合成
  - `audio_tools.py:9` `overlay(bufs)`；`audio_tools.py:32` `normalize_volume(buf, ...)`
  - `audio_tools.py:55` `in_playback_format(buf)`；`audio_tools.py:48` `slice(buf, duration)`
  - `synth.py:9` `sine_wave_note(frequency, duration)`；`synth.py:43` `silence(duration)`

- 设备
  - `audio_device.py:23` `AudioDevice.list_output_devices()`
  - `audio_device.py:43` `AudioDevice.get_default_output_index(...)`
  - `audio_device.py:169` `AudioDevice.play_stream(callback)`

- 交互/应用
  - `controls.py:33` `capture_input(engine)`
  - `main.py:9` `main()`

---

如需我基于以上分析直接修复 `overlay` 的缩放问题或为 `mainspectrometer.py` 接入正确的数据路径，请告诉我你的偏好（例如是否希望添加测试脚本/演示修复）。

