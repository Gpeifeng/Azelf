from mcp.server.fastmcp import FastMCP
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import webbrowser

mcp = FastMCP("server")



# 获取默认音频设备
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(
    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = cast(interface, POINTER(IAudioEndpointVolume))

@mcp.tool()
async def set_volume(volume_level: float) -> str:
    if 0.0 <= volume_level <= 100.0:
        # 将百分比转换为音量范围 (-65.25 to 0.0)
        volume_range = volume.GetVolumeRange()
        min_volume = volume_range[0]
        max_volume = volume_range[1]
        target_volume = (volume_level / 100.0) * (max_volume - min_volume) + min_volume
        volume.SetMasterVolumeLevel(target_volume, None)
        return f"Volume set to {volume_level}%"
    else:
        return "Invalid volume level. Please provide a value between 0.0 and 100.0."


if __name__ == "__main__":
    mcp.run(transport='stdio')