import os
import sys
import controls
import engine_factory
import random
from typing import Optional


def main():
    # engine = engine_factory.v_four_90_deg()
    # engine = engine_factory.w_16()
    # engine = engine_factory.v_8_LS()
    # engine = engine_factory.inline_5_crossplane()
    # engine = engine_factory.inline_6()
    engine = engine_factory.boxer_4_crossplane_custom([1, 1, 0, 0])  # (rando := random.randrange(360)))
    if os.environ.get("ENGINE_DEBUG", "0") == "1":
        print("[debug] engine constructed")
    # engine = engine_factory.inline_4_1_spark_plug_disconnected()
    # engine = engine_factory.inline_4()
    # engine = engine_factory.boxer_4_half()
    # engine = engine_factory.random()
    #engine = engine_factory.fake_rotary_2rotor()
    #engine = engine_factory.V_12()

    stream: Optional[object] = None
    audio_device = None
    headless_audio = os.environ.get("ENGINE_HEADLESS_AUDIO", "0") == "1"
    if not headless_audio:
        # 在初始化音频流之前，复用 AudioDevice 的枚举与默认选择
        from audio_device import AudioDevice
        try:
            import sounddevice as sd

            # 避免启动 JACK 守护进程
            os.environ.setdefault("JACK_NO_START_SERVER", "1")

            out_devs = AudioDevice.list_output_devices()

            if out_devs:
                default_out = AudioDevice.get_default_output_index(pipewire_as_default=True)
                print("可用音频输出设备:")
                for d in out_devs:
                    idx = d.get("index")
                    name = str(d.get("name", "?"))
                    max_out = d.get("max_output_channels", 0)
                    sr = d.get("default_samplerate")
                    mark = "(默认)" if default_out is not None and idx == default_out else ""
                    extra = f", 默认采样率: {int(sr)}" if isinstance(sr, (int, float)) and sr else ""
                    print(f"  [{idx:2d}] {name} - 输出通道: {max_out}{extra} {mark}")

                selection = None
                can_prompt = sys.stdin and sys.stdin.isatty()
                if can_prompt:
                    try:
                        user_in = input("请选择输出设备索引(回车使用默认): ").strip()
                        if user_in:
                            selection = int(user_in)
                    except (ValueError, EOFError, KeyboardInterrupt):
                        selection = None

                valid_indices = {d["index"] for d in out_devs}
                if selection is not None and selection not in valid_indices:
                    print(f"输入的索引 {selection} 无效，将使用默认输出。")
                    selection = None

                if selection is None:
                    if default_out is not None:
                        chosen = default_out
                    else:
                        chosen = out_devs[0]["index"]
                else:
                    chosen = selection

                # 将选择传播给 AudioDevice（其支持 ENGINE_AUDIO_DEVICE 环境变量）
                os.environ["ENGINE_AUDIO_DEVICE"] = str(chosen)
                # 同时设置 sounddevice 的默认输出，方便后续库调用
                try:
                    sd.default.device = (None, chosen)
                except Exception:
                    pass
                try:
                    info = sd.query_devices(chosen)
                    name = info.get("name", "?") if isinstance(info, dict) else str(info)
                    print(f"已选择输出设备: [{chosen}] {name}")
                except Exception:
                    pass
            else:
                print("未发现可用的音频输出设备，将尝试继续初始化（可能静音）。")
        except Exception:
            # 列表/选择失败不阻塞后续流程，让 AudioDevice 自行回退选择
            pass
        audio_device = AudioDevice()
        try:
            stream = audio_device.play_stream(engine.gen_audio)
        except Exception as e:
            print("Audio device initialization failed:", e)
            print("No usable output device found or audio backend unavailable.")
            print("Try: plugging in an audio device, enabling PulseAudio/ALSA, or running on a system with sound.")
            raise

    if os.environ.get("ENGINE_DEBUG", "0") == "1":
        print("[debug] audio initialized headless=", headless_audio)
    print('\nEngine is running...')
    # print(rando)

    try:
        controls.capture_input(engine)  # blocks until user exits
    except KeyboardInterrupt:
        pass

    print('Exiting...')
    if stream:
        stream.close()
    if audio_device:
        audio_device.close()


if __name__ == '__main__':
    main()
