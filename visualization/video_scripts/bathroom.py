import math

try:
    import bpy
except ImportError:
    raise RuntimeError(
        "This script must be run inside Blender, e.g.:\n"
        "  blender -b your_scene.blend -P generate_video.py"
    )

# ================== 可按需修改的参数 ==================
FRAMES = 300                # 总帧数
FPS = 30                    # 帧率
RADIUS = 1.0                # 摄像机离中心的水平距离
HEIGHT = 0.1                # 摄像机相对中心的高度偏移
CENTER = (0.0, 0.0, 1.8)    # 环绕中心
FOCAL_LENGTH = 20.0         # 摄像机焦距（mm），视角宽窄由此控制，常见值 24/35/50 等
OUTPUT_PATH = "//bathroom.mp4"  # 相对 .blend 的输出路径

# ★ 新增配置：控制旋转起始 / 终止角度（单位：度）
# 例如：
#   0 → 360   表示转一整圈
#   0 → 180   表示只转半圈
#   -90 → 90  表示从左侧 90° 转到右侧 90°
START_ANGLE_DEG = 0.0       # 起始角度（度）
END_ANGLE_DEG = 90.0       # 终止角度（度）
# =====================================================


def enable_gpu_for_cycles():
    """
    将 Cycles 渲染设备切换到 GPU。
    优先尝试 CUDA，再尝试 OPTIX；如果失败则仍然使用 CPU。
    """
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"

    prefs_all = bpy.context.preferences

    # 确保 Cycles 插件已启用
    if "cycles" not in prefs_all.addons:
        try:
            bpy.ops.preferences.addon_enable(module="cycles")
        except Exception as e:
            print(f"[WARN] Cannot enable Cycles addon automatically: {e}")
            return

    try:
        cycles_prefs = prefs_all.addons["cycles"].preferences
    except KeyError:
        print("[WARN] Cycles addon not found in preferences; fallback to CPU.")
        return

    backend_chosen = None
    for backend in ("CUDA", "OPTIX"):
        try:
            cycles_prefs.compute_device_type = backend
            backend_chosen = backend
            break
        except TypeError:
            # 该 Blender 版本/编译不支持这个 backend
            continue

    if backend_chosen is None:
        print("[WARN] No supported GPU backend (OPTIX/CUDA); fallback to CPU.")
        return

    # 刷新设备列表（不同版本函数签名可能略有差异）
    try:
        cycles_prefs.refresh_devices()
    except TypeError:
        cycles_prefs.refresh_devices(bpy.context)

    # 只启用 GPU 设备
    for dev in cycles_prefs.devices:
        dev.use = (dev.type == "GPU" or dev.type == "CUDA")
        print(f"[GPU] {dev.type}: {dev.name}, use={dev.use}")

    # 场景层面指定使用 GPU
    scene.cycles.device = "GPU"
    print(f"[INFO] Cycles is now using GPU with backend = {backend_chosen}.")


def clear_old_cameras():
    """删除场景中已有摄像机（防止被旧的干扰）。"""
    for obj in list(bpy.data.objects):
        if obj.type == "CAMERA":
            print(f"[INFO] Removing old camera: {obj.name}")
            bpy.data.objects.remove(obj, do_unlink=True)


def create_camera_and_target(center):
    """创建一个摄像机和一个空物体作为跟踪目标，并设置焦距。"""
    scene = bpy.context.scene

    # 摄像机
    cam_data = bpy.data.cameras.new("TurntableCamera")
    cam_data.lens = FOCAL_LENGTH  # ★ 设置焦距（单位：毫米）
    camera = bpy.data.objects.new("TurntableCamera", cam_data)
    scene.collection.objects.link(camera)

    # 空物体：用于让摄像机始终看向它
    target = bpy.data.objects.new("TurntableTarget", None)
    target.location = center
    scene.collection.objects.link(target)

    # Track To 约束：摄像机始终看向 target
    constr = camera.constraints.new(type="TRACK_TO")
    constr.target = target
    constr.track_axis = "TRACK_NEGATIVE_Z"
    constr.up_axis = "UP_Y"

    # 设置为场景主摄像机
    scene.camera = camera

    print(f"[INFO] Camera and target created. Focal length = {FOCAL_LENGTH} mm")
    return camera


def animate_turntable(camera, center, radius, height, frames,
                      start_angle_deg, end_angle_deg):
    """
    给摄像机做绕 center 的旋转动画。
    支持指定起始角度和终止角度（单位：度），而不是固定 360°。

    参数:
        start_angle_deg: 起始角度（度）
        end_angle_deg  : 终止角度（度）
    """
    scene = bpy.context.scene

    if frames <= 1:
        # 只有 1 帧时，就放在起始位置
        angle_rad = math.radians(start_angle_deg)
        x = center[0] + radius * math.cos(angle_rad)
        y = center[1] + radius * math.sin(angle_rad)
        z = center[2] + height

        scene.frame_set(0)
        camera.location = (x, y, z)
        camera.keyframe_insert(data_path="location", frame=0)
        print("[INFO] Only 1 frame: set camera at start angle.")
        return

    angle_start = math.radians(start_angle_deg)
    angle_end = math.radians(end_angle_deg)

    # 总角度增量
    angle_delta = angle_end - angle_start

    for f in range(frames):
        # 使用 (frames - 1) 让首尾刚好是起始/终止角
        t = f / (frames - 1)
        angle = angle_start + angle_delta * t

        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        z = center[2] + height

        scene.frame_set(f)
        camera.location = (x, y, z)
        camera.keyframe_insert(data_path="location", frame=f)

    print(
        f"[INFO] Turntable keyframes inserted from {start_angle_deg}° to {end_angle_deg}°."
    )


def setup_render(output_path, frames, fps):
    """设置渲染为 H264 MP4 输出。"""
    scene = bpy.context.scene

    scene.frame_start = 0
    scene.frame_end = frames - 1
    scene.render.fps = fps

    # 输出路径；// 表示相对 .blend 所在目录
    scene.render.filepath = output_path

    # 引擎（这里仍使用 Cycles，设备由 enable_gpu_for_cycles 控制）
    scene.render.engine = "CYCLES"
    
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = False

    scene.render.image_settings.file_format = "FFMPEG"
    ffmpeg = scene.render.ffmpeg
    ffmpeg.format = "MPEG4"
    ffmpeg.codec = "H264"
    ffmpeg.constant_rate_factor = "MEDIUM"
    ffmpeg.ffmpeg_preset = "GOOD"

    print(f"[INFO] Render setup done. Output: {output_path}")


def main():
    print("[INFO] Using current opened blend file:", bpy.data.filepath)

    # ★ 先启用 GPU 渲染
    enable_gpu_for_cycles()

    clear_old_cameras()
    camera = create_camera_and_target(CENTER)

    # ★ 使用可配置的起始/终止角度
    animate_turntable(
        camera,
        CENTER,
        RADIUS,
        HEIGHT,
        FRAMES,
        START_ANGLE_DEG,
        END_ANGLE_DEG,
    )

    setup_render(OUTPUT_PATH, FRAMES, FPS)

    print("[INFO] Start rendering animation...")
    bpy.ops.render.render(animation=True)
    print("[INFO] Rendering finished.")


if __name__ == "__main__":
    main()
