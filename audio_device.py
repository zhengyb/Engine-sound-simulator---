import os
import cfg
import sounddevice as sd
from typing import List, Dict, Any, Optional


class AudioDevice:
    def __init__(self):
        # Headless mode: avoid initializing any audio backend
        self._headless = os.environ.get("ENGINE_HEADLESS_AUDIO", "0") == "1"
        self._stream = None

        if not self._headless:
            os.environ.setdefault("JACK_NO_START_SERVER", "1")
            self._sel_device_index, self._sel_device_info = self._choose_output_device()
        else:
            self._sel_device_index, self._sel_device_info = (None, None)
        self._samplerate = cfg.sample_rate
        self._desired_channels = int(os.environ.get("ENGINE_AUDIO_CHANNELS", "2"))

    # ---- Device enumeration helpers ----
    @staticmethod
    def list_output_devices() -> List[Dict[str, Any]]:
        """返回所有可用输出设备的信息列表。

        仅包含具有输出能力（max_output_channels > 0）的设备，并附带其在
        sounddevice 中的全局索引（字段：index）。
        """
        devices = sd.query_devices()
        out_devs: List[Dict[str, Any]] = []
        for idx, dev in enumerate(devices):
            try:
                max_out = int(dev.get("max_output_channels", 0) or 0)
            except Exception:
                max_out = 0
            if max_out > 0:
                d = dict(dev)
                d["index"] = idx
                out_devs.append(d)
        return out_devs

    @staticmethod
    def get_default_output_index(pipewire_as_default: bool = True) -> Optional[int]:
        """获取默认输出设备索引。

        - 当 pipewire_as_default=True 时，优先返回名称包含 "pipewire" 的输出设备索引；
          如未找到，则回退到 sounddevice 的默认输出设备索引。
        - 当 pipewire_as_default=False 时，仅返回 sounddevice 的默认输出设备索引。
        """
        if pipewire_as_default:
            try:
                devices = sd.query_devices()
                for idx, dev in enumerate(devices):
                    try:
                        name = str(dev.get("name", ""))
                        max_out = int(dev.get("max_output_channels", 0) or 0)
                    except Exception:
                        name, max_out = "", 0
                    if max_out > 0 and "pipewire" in name.lower():
                        return idx
            except Exception:
                pass

        try:
            d = sd.default.device
            if isinstance(d, (list, tuple)) and len(d) == 2:
                return d[1]
            if isinstance(d, int):
                return d
        except Exception:
            return None
        return None

    def _choose_output_device(self):
        """Choose a valid output device in sounddevice.

        Prefer the current default; otherwise set the first device with
        max_output_channels > 0 as output default.
        """
        try:
            # ENV override: allow picking device by index or substring
            prefer = os.environ.get("ENGINE_AUDIO_DEVICE")
            print(f"ENGINE_AUDIO_DEVICE={prefer}")
            if prefer:
                try:
                    try:
                        idx = int(prefer)
                        info = sd.query_devices(idx)
                        return idx, info
                    except ValueError:
                        devices = sd.query_devices()
                        for idx, dev in enumerate(devices):
                            name = str(dev.get('name', ''))
                            if prefer.lower() in name.lower() and int(dev.get('max_output_channels', 0)) > 0:
                                return idx, dev
                except Exception:
                    pass

            # Prefer a PipeWire device by default unless disabled
            prefer_pipewire = os.environ.get("ENGINE_PREFER_PIPEWIRE", "1") == "1"
            if prefer_pipewire:
                try:
                    devices = sd.query_devices()
                    for idx, dev in enumerate(devices):
                        name = str(dev.get('name', ''))
                        if 'pipewire' in name.lower() and int(dev.get('max_output_channels', 0)) > 0:
                            # also capture default samplerate if present
                            try:
                                dsr = dev.get('default_samplerate')
                                if dsr:
                                    self._samplerate = int(dsr)
                            except Exception:
                                pass
                            print(f"Select pipewire: {idx}, {dev}")
                            return idx, dev
                except Exception:
                    pass

            # Check current default output
            default_out = None
            try:
                d = sd.default.device
                if isinstance(d, (list, tuple)) and len(d) == 2:
                    default_out = d[1]
                elif isinstance(d, int):
                    default_out = d
            except Exception:
                default_out = None

            if default_out is not None:
                info = sd.query_devices(default_out)
                if info and int(info.get('max_output_channels', 0)) > 0:
                    # also capture default samplerate if present
                    try:
                        dsr = info.get('default_samplerate')
                        if dsr:
                            self._samplerate = int(dsr)
                    except Exception:
                        pass
                    return default_out, info

            # Pick the first device with output channels
            devices = sd.query_devices()
            if os.environ.get("ENGINE_DEBUG", "0") == "1":
                print("devices: ")
                for i, d in enumerate(devices):
                    print(f"   {i:2d} {d.get('name','?')} ({d.get('max_input_channels',0)} in, {d.get('max_output_channels',0)} out)")
            for idx, dev in enumerate(devices):
                if int(dev.get('max_output_channels', 0)) > 0:
                    try:
                        dsr = dev.get('default_samplerate')
                        if dsr:
                            self._samplerate = int(dsr)
                    except Exception:
                        pass
                    return idx, dev
        except Exception:
            # Let sounddevice decide if probing fails
            return None, None
        return None, None

    def close(self):
        if self._stream is not None:
            try:
                self._stream.close()
            finally:
                self._stream = None

    def play_stream(self, callback):
        class _NullStream:
            def start_stream(self):
                return self
            def stop_stream(self):
                return self
            def close(self):
                return None

        if self._headless:
            return _NullStream()

        def sd_callback(outdata, frames, time_info, status):
            # callback expects number of frames, returns int16 bytes
            data = callback(frames)
            import numpy as np
            if isinstance(data, (bytes, bytearray)):
                mono = np.frombuffer(data, dtype=np.int16).reshape(-1, 1)
            else:
                arr = np.asarray(data)
                if arr.ndim == 1:
                    mono = arr.reshape(-1, 1).astype(np.int16)
                else:
                    mono = arr[:, :1].astype(np.int16)
            ch = outdata.shape[1]
            if ch > 1:
                outdata[:, :ch] = mono.repeat(ch, axis=1)
            else:
                outdata[:, :1] = mono

        try:
            # Decide channel count based on device capability
            sel_idx = self._sel_device_index
            sel_info = self._sel_device_info or {}
            max_out = int(sel_info.get('max_output_channels', 2) or 2)
            ch = max(1, min(self._desired_channels, max_out))

            # Debug output
            if os.environ.get("ENGINE_DEBUG", "0") == "1":
                try:
                    devices = sd.query_devices()
                    print("devices: ")
                    for i, d in enumerate(devices):
                        mark = '<' if i == sel_idx else ' '
                        print(f"{mark} {i:2d} {d.get('name','?')} ({d.get('max_input_channels',0)} in, {d.get('max_output_channels',0)} out)")
                    print(f"select {sel_idx}")
                except Exception:
                    pass

            # Build OutputStream with explicit output device index
            self._stream = sd.OutputStream(
                device=sel_idx,
                samplerate=self._samplerate,
                channels=ch,
                dtype='int16',
                callback=sd_callback,
            )
            self._stream.start()
            return self._stream
        except Exception:
            # Fallback to a null stream so app stays responsive
            return _NullStream()


def main() -> None:
    """列出当前系统可用的音频输出设备。

    - 仅显示具有输出能力（max_output_channels > 0）的设备。
    - 标注默认输出设备与默认采样率（若可用）。
    - 不打开任何音频流，纯查询。
    """
    import sys

    # 避免在某些平台拉起 JACK 守护进程
    os.environ.setdefault("JACK_NO_START_SERVER", "1")

    try:
        devices = sd.query_devices()
    except Exception as e:
        print(f"查询音频设备失败: {e}")
        sys.exit(1)

    # 过滤具有输出能力的设备
    out_devs = []
    for idx, dev in enumerate(devices):
        try:
            max_out = int(dev.get("max_output_channels", 0) or 0)
        except Exception:
            max_out = 0
        if max_out > 0:
            d = dict(dev)
            d["index"] = idx
            out_devs.append(d)

    if not out_devs:
        print("未发现可用的音频输出设备。")
        return

    default_out = AudioDevice.get_default_output_index()
    print("可用音频输出设备:")
    for d in out_devs:
        idx = d.get("index")
        name = str(d.get("name", "?"))
        max_out = d.get("max_output_channels", 0)
        sr = d.get("default_samplerate")
        mark = "(默认)" if default_out is not None and idx == default_out else ""
        extra = f", 默认采样率: {int(sr)}" if isinstance(sr, (int, float)) and sr else ""
        print(f"  [{idx:2d}] {name} - 输出通道: {max_out}{extra} {mark}")


if __name__ == "__main__":
    main()
