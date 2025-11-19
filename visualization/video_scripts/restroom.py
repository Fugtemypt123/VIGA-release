import math

try:
    import bpy
    from mathutils import Vector, Matrix
except ImportError:
    raise RuntimeError(
        "This script must be run inside Blender, e.g.:\n"
        "  blender -b your_scene.blend -P generate_video.py"
    )

# ================== 可按需修改的参数 ==================
FRAMES = 10         # 总帧数
FPS = 1             # 帧率

START_POS = (-3.0, 1.0, 1.5)   # 摄像机起点
END_POS   = ( 0.0, 0.0, 1.5)   # 摄像机终点

# ★ 相机“相对运动方向”的偏转角度（绕世界 Z 轴）
#   0 → 90 表示：一开始正对运动方向，最后偏转 90°（例如从朝 +X 转到朝 +Y）
START_ROT_DEG = 0.0
END_ROT_DEG   = 90.0

OUTPUT_PATH = "//restroom.mp4"
# =====================================================


def enable_gpu_for_cycles():
    """
    将 Cycles 渲染设备切换到 GPU。
    优先尝试 OPTIX，其次 CUDA；如果都不可用则退回 CPU。
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
    for backend in ("OPTIX", "CUDA"):
        try:
            cycles_prefs.compute_device_type = backend
            backend_chosen = backend
            break
        except TypeError:
            continue

    if backend_chosen is None:
        print("[WARN] No supported GPU backend (CUDA/OPTIX); fallback to CPU.")
        return

    # 刷新设备列表
    try:
        cycles_prefs.refresh_devices()
    except TypeError:
        cycles_prefs.refresh_devices(bpy.context)

    # 只启用 GPU 设备
    for dev in cycles_prefs.devices:
        dev.use = (dev.type == "GPU" or dev.type == backend_chosen)
        print(f"[GPU] {dev.type}: {dev.name}, use={dev.use}")

    scene.cycles.device = "GPU"
    print(f"[INFO] Cycles is now using GPU with backend = {backend_chosen}.")


def clear_old_cameras():
    """删除场景中已有摄像机（防止被旧的干扰）。"""
    for obj in list(bpy.data.objects):
        if obj.type == "CAMERA":
            print(f"[INFO] Removing old camera: {obj.name}")
            bpy.data.objects.remove(obj, do_unlink=True)


def create_camera():
    """创建一个摄像机对象。"""
    scene = bpy.context.scene

    cam_data = bpy.data.cameras.new("TravelCamera")
    camera = bpy.data.objects.new("TravelCamera", cam_data)
    scene.collection.objects.link(camera)

    scene.camera = camera

    print("[INFO] Camera created.")
    return camera


def forward_to_euler(forward: Vector):
    """
    给定一个“希望相机朝向”的 forward 向量（世界坐标），
    构造一个相机的欧拉角，使得相机的 -Z 轴对齐到该 forward，
    并尽量保持世界 Z 轴为“向上”。
    """
    forward = forward.normalized()

    # 世界向上方向（Blender 里一般是 Z 轴）
    world_up = Vector((0.0, 0.0, 1.0))

    # 如果 forward 接近竖直，就临时换一个 up，避免叉积为 0
    if abs(forward.dot(world_up)) > 0.999:
        world_up = Vector((0.0, 1.0, 0.0))

    # 右方向：forward × up
    right = forward.cross(world_up).normalized()
    true_up = right.cross(forward).normalized()

    # 构造 3×3 旋转矩阵：列向量分别为 (right, true_up, -forward)
    rot_mat = Matrix((
        (right.x,   true_up.x,   -forward.x),
        (right.y,   true_up.y,   -forward.y),
        (right.z,   true_up.z,   -forward.z),
    ))

    return rot_mat.to_euler('XYZ')


def animate_linear_motion(camera, start_pos, end_pos, frames):
    """
    让摄像机从 start_pos 直线运动到 end_pos，
    且视角初始对准“运动方向”，并在运动过程中逐渐绕世界 Z 轴偏转
    START_ROT_DEG → END_ROT_DEG。
    """
    scene = bpy.context.scene

    start = Vector(start_pos)
    end = Vector(end_pos)

    # 运动方向（水平向量），去掉 Z 分量，保证不会抬头/低头
    direction_flat = Vector((end.x - start.x, end.y - start.y, 0.0))
    if direction_flat.length == 0:
        print("[WARN] Start and end positions are identical in XY; no motion.")
        direction_flat = Vector((1.0, 0.0, 0.0))
    direction_flat.normalize()

    for f in range(frames):
        # t 从 0 到 1，均匀插值
        t = f / (frames - 1) if frames > 1 else 0.0

        # 位置线性插值
        pos = start.lerp(end, t)

        # 角度插值（相对于运动方向的偏转角）
        rot_deg = START_ROT_DEG + (END_ROT_DEG - START_ROT_DEG) * t
        rot_rad = math.radians(rot_deg)

        # 在世界坐标系下，绕 Z 轴旋转“水平运动方向”
        rotated_dir = Matrix.Rotation(rot_rad, 4, 'Z') @ direction_flat

        # 由 forward 向量计算相机旋转（-Z 对齐到 rotated_dir，世界 Z 向上）
        rot_euler = forward_to_euler(rotated_dir)

        scene.frame_set(f)
        camera.location = pos
        camera.rotation_euler = rot_euler

        camera.keyframe_insert(data_path="location", frame=f)
        camera.keyframe_insert(data_path="rotation_euler", frame=f)

    print(
        f"[INFO] Linear motion + view rotation inserted "
        f"({START_ROT_DEG}° → {END_ROT_DEG}° relative to move dir)."
    )


def setup_render(output_path, frames, fps):
    """设置渲染为 H264 MP4 输出."""
    scene = bpy.context.scene

    scene.frame_start = 0
    scene.frame_end = frames - 1
    scene.render.fps = fps

    scene.render.filepath = output_path

    scene.render.engine = "CYCLES"
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.use_motion_blur = False

    scene.render.image_settings.file_format = "FFMPEG"
    ffmpeg = scene.render.ffmpeg
    ffmpeg.format = "MPEG4"
    ffmpeg.codec = "H264"
    ffmpeg.constant_rate_factor = "HIGH"
    ffmpeg.ffmpeg_preset = "GOOD"

    print(f"[INFO] Render setup done. Output: {output_path}")


def main():
    print("[INFO] Using current opened blend file:", bpy.data.filepath)

    enable_gpu_for_cycles()
    clear_old_cameras()
    camera = create_camera()
    animate_linear_motion(camera, START_POS, END_POS, FRAMES)
    setup_render(OUTPUT_PATH, FRAMES, FPS)

    print("[INFO] Start rendering animation...")
    bpy.ops.render.render(animation=True)
    print("[INFO] Rendering finished.")


if __name__ == "__main__":
    main()
