import bpy
import math
from mathutils import Vector

# ==============================
# 可根据需求修改
# ==============================
CAM_START = Vector((0.0, -3.2, 1.7))
CAM_END   = Vector((0.0, -1.4, 1.7))

CAM_LENS  = 60
FIXED_ROT_EULER = (
    math.radians(76.2034),
    0.0,
    0.0
)

# 物理 / 动画真实存在的帧区间，固定 1–300
BASE_ANIM_FRAMES = 300

# 想要“导出的视频帧数”
# - 若 < BASE_ANIM_FRAMES：在 1–300 中等距抽帧渲染
# - 若 >= BASE_ANIM_FRAMES：按 300 帧逐帧渲染
TARGET_TOTAL_FRAMES = 300

FPS = 30
OUTPUT_PATH = "//table.mp4"
# ==============================


def enable_gpu_for_cycles():
    """
    将 Cycles 渲染设备切换到 GPU。
    首选 CUDA，其次 OPTIX；如果都不可用则退回 CPU。
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
    # ★ 首选 CUDA，再尝试 OPTIX
    for backend in ("OPTIX", "CUDA"):
        try:
            cycles_prefs.compute_device_type = backend
            backend_chosen = backend
            break
        except TypeError:
            # 该 Blender 版本/编译不支持这个 backend
            continue

    if backend_chosen is None:
        print("[WARN] No supported GPU backend (CUDA/OPTIX); fallback to CPU.")
        return

    # 刷新设备列表（不同版本函数签名可能略有差异）
    try:
        cycles_prefs.refresh_devices()
    except TypeError:
        cycles_prefs.refresh_devices(bpy.context)

    # 只启用 GPU 设备
    for dev in cycles_prefs.devices:
        dev.use = (dev.type == "GPU" or dev.type == backend_chosen)
        print(f"[GPU] {dev.type}: {dev.name}, use={dev.use}")

    # 场景层面指定使用 GPU
    scene.cycles.device = "GPU"
    print(f"[INFO] Cycles is now using GPU with backend = {backend_chosen}.")


def ensure_camera():
    """若无摄像机，则新建；并设定固定 lens。"""
    for obj in bpy.data.objects:
        if obj.type == "CAMERA":
            bpy.context.scene.camera = obj
            obj.data.lens = CAM_LENS
            return obj

    cam_data = bpy.data.cameras.new("AutoCamera")
    cam_data.lens = CAM_LENS
    cam = bpy.data.objects.new("AutoCamera", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def animate_camera(camera):
    """
    在真实动画帧 1–BASE_ANIM_FRAMES 内做相机动画：
    前半段：CAM_START → CAM_END 的直线插值
    后半段：保持在 CAM_END，不移动
    旋转保持固定不变
    """
    scene = bpy.context.scene
    mid_frame = BASE_ANIM_FRAMES // 2

    for f in range(1, BASE_ANIM_FRAMES + 1):
        scene.frame_set(f)

        if f <= mid_frame:
            t = (f - 1) / mid_frame
            pos = CAM_START.lerp(CAM_END, t)
        else:
            pos = CAM_END

        camera.location = pos
        camera.rotation_euler = FIXED_ROT_EULER

        camera.keyframe_insert("location", frame=f)
        camera.keyframe_insert("rotation_euler", frame=f)

    print("[INFO] Camera animation (1–{0}) created.".format(BASE_ANIM_FRAMES))


def configure_frame_sampling():
    """
    不再修改原始动画，只控制“渲染时如何抽帧”：
    - 动画区间始终为 1–BASE_ANIM_FRAMES
    - 若 TARGET_TOTAL_FRAMES >= BASE_ANIM_FRAMES：
        渲染 1–BASE_ANIM_FRAMES，逐帧输出
    - 若 TARGET_TOTAL_FRAMES < BASE_ANIM_FRAMES：
        设置 frame_step，使得在 1–BASE_ANIM_FRAMES 中等距抽帧
        （近似地得到 ~TARGET_TOTAL_FRAMES 帧）
    """
    scene = bpy.context.scene

    base = BASE_ANIM_FRAMES
    target = TARGET_TOTAL_FRAMES

    if target >= base:
        # 目标帧数多于或等于基础动画帧 → 就按 1–base 全部渲染
        scene.frame_start = 1
        scene.frame_end = base
        scene.frame_step = 1
        print(f"[INFO] TARGET_TOTAL_FRAMES >= {base}, use full range 1–{base} with step=1.")
    else:
        # 目标帧数更少 → 在 1–base 中等距抽样
        step_float = base / float(target)
        step = max(1, int(round(step_float)))
        scene.frame_start = 1
        scene.frame_end = base
        scene.frame_step = step

        # 实际输出帧数（约等于 target）
        actual_frames = (base - 1) // step + 1

        print(
            "[INFO] TARGET_TOTAL_FRAMES = {0} < {1}, "
            "use frame_step = {2}, actual rendered frames ≈ {3}."
            .format(target, base, step, actual_frames)
        )


def setup_render():
    scene = bpy.context.scene
    scene.render.filepath = OUTPUT_PATH
    scene.render.engine = "CYCLES"
    scene.render.fps = FPS

    # 帧区间 & 抽样由 configure_frame_sampling 决定
    # 这里只负责渲染参数
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = False

    # 输出为 MP4
    scene.render.image_settings.file_format = "FFMPEG"
    ffmpeg = scene.render.ffmpeg
    ffmpeg.format = "MPEG4"
    ffmpeg.codec = "H264"
    ffmpeg.constant_rate_factor = "MEDIUM"
    ffmpeg.ffmpeg_preset = "GOOD"

    print("[INFO] Render setup finished.")


def main():
    print("[INFO] Starting...")

    enable_gpu_for_cycles()

    # 不再做 retime，真实动画认为是 1–BASE_ANIM_FRAMES
    cam = ensure_camera()
    animate_camera(cam)

    # 根据 TARGET_TOTAL_FRAMES 决定如何抽帧
    configure_frame_sampling()

    setup_render()

    print("[INFO] Rendering animation...")
    bpy.ops.render.render(animation=True)
    print("[INFO] Rendering finished.")


if __name__ == "__main__":
    main()
