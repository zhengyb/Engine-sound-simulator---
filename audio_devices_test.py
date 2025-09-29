"""
列出当前系统上所有可用的音频输出设备。

使用 sounddevice 库枚举设备，仅显示具有输出能力（max_output_channels > 0）的设备。

运行:
  python audio_devices_test.py

备注:
- 默认列出设备并等待用户选择；可直接回车使用默认输出。
- 不会打开任何音频流，纯查询/选择，适合无声环境/CI。
- 显示设备索引、名称、输出通道数和默认输出标记。
"""

from __future__ import annotations

import os
from typing import List, Dict, Any, Optional

import sounddevice as sd


def list_output_devices() -> List[Dict[str, Any]]:
    """返回所有可用输出设备的信息列表。"""
    try:
        devices = sd.query_devices()
    except Exception as e:
        raise SystemExit(f"查询音频设备失败: {e}")

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
    return out_devs


def get_default_output_index() -> int | None:
    """获取 sounddevice 当前默认输出设备索引（如有）。"""
    try:
        d = sd.default.device
        if isinstance(d, (list, tuple)) and len(d) == 2:
            return d[1]
        if isinstance(d, int):
            return d
    except Exception:
        return None
    return None


def main() -> None:
    # 尝试避免启动 JACK 等后端的守护进程
    os.environ.setdefault("JACK_NO_START_SERVER", "1")

    default_out = get_default_output_index()
    devices = list_output_devices()

    if not devices:
        print("未发现可用的音频输出设备。")
        return

    print("可用音频输出设备:")
    for d in devices:
        idx = d.get("index")
        name = str(d.get("name", "?"))
        max_out = d.get("max_output_channels", 0)
        sr = d.get("default_samplerate")
        mark = "(默认)" if default_out is not None and idx == default_out else ""
        extra = f", 默认采样率: {int(sr)}" if isinstance(sr, (int, float)) and sr else ""
        print(f"  [{idx:2d}] {name} - 输出通道: {max_out}{extra} {mark}")

    # 交互式选择
    print()
    prompt = "请选择输出设备索引(回车使用默认): "
    selection: Optional[int] = None
    try:
        user_in = input(prompt).strip()
        if user_in:
            selection = int(user_in)
    except (ValueError, EOFError, KeyboardInterrupt):
        selection = None

    valid_indices = {d["index"] for d in devices}
    if selection is not None and selection not in valid_indices:
        print(f"输入的索引 {selection} 无效，将使用默认输出。")
        selection = None

    # 应用选择到当前进程的默认设备
    if selection is None:
        if default_out is not None:
            sd.default.device = (None, default_out)
            chosen = default_out
        else:
            # 没有已知默认，则退回第一个可用输出
            chosen = devices[0]["index"]
            sd.default.device = (None, chosen)
    else:
        chosen = selection
        sd.default.device = (None, chosen)

    # 输出确认信息
    chosen_info = sd.query_devices(chosen)
    name = chosen_info.get("name", "?") if isinstance(chosen_info, dict) else str(chosen_info)
    print(f"已选择输出设备: [{chosen}] {name}")
    print("提示: 你也可以在运行主程序时通过环境变量指定，例如:")
    print("  ENGINE_AUDIO_DEVICE=" + str(chosen) + " python main.py")


if __name__ == "__main__":
    main()
