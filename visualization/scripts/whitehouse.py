import math

try:
    import bpy
    from mathutils import Vector
except ImportError:
    raise RuntimeError(
        "This script must be run inside Blender, e.g.:\n"
        "  blender -b your_scene.blend -P generate_video.py"
    )

# ================== 可按需修改的参数 ==================
FRAMES = 300         # 总帧数
FPS = 30         # 帧率
START_POS = (0.0, -40.0, -20.0)     # 摄像机起点
END_POS   = (0.0, -40.0, 32.0)   # 摄像机终点
TARGET_POS = (0.0, 0.0, 6.0)     # 摄像机始终对准的目标点
OUTPUT_PATH = "//whitehouse.mp4"  # 相对当前 .blend 文件所在目录
# =====================================================


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


def clear_old_cameras():
    """删除场景中已有摄像机（防止被旧的干扰）。"""
    for obj in list(bpy.data.objects):
        if obj.type == "CAMERA":
            print(f"[INFO] Removing old camera: {obj.name}")
            bpy.data.objects.remove(obj, do_unlink=True)


def create_camera():
    """创建一个摄像机对象，不再使用空物体和 TrackTo 约束。"""
    scene = bpy.context.scene

    cam_data = bpy.data.cameras.new("TravelCamera")
    # 设置焦距（单位：mm），焦距越小，视野越大
    # 默认是 50mm，这里设置为 24mm 以获得更大的视野
    cam_data.lens = 30
    
    camera = bpy.data.objects.new("TravelCamera", cam_data)
    scene.collection.objects.link(camera)

    # 设置为场景主摄像机
    scene.camera = camera

    print(f"[INFO] Camera created with focal length: {cam_data.lens}mm")
    return camera


def animate_arc_rotation(camera, start_pos, end_pos, target_pos, frames):
    """
    让摄像机从 start_pos 沿圆弧旋转到 end_pos，
    摄像机始终对准 target_pos 点。
    圆弧是以 target_pos 为圆心的球面上的弧线。
    """
    scene = bpy.context.scene

    start = Vector(start_pos)
    end = Vector(end_pos)
    target = Vector(target_pos)

    # 计算相对于目标点的向量
    vec_start = start - target
    vec_end = end - target

    # 验证距离是否相等（应该在同一球面上）
    radius_start = vec_start.length
    radius_end = vec_end.length
    print(f"[INFO] Start radius: {radius_start:.2f}, End radius: {radius_end:.2f}")
    
    # 如果距离不完全相等，使用平均半径
    radius = (radius_start + radius_end) / 2.0
    
    # 归一化向量
    vec_start_norm = vec_start.normalized()
    vec_end_norm = vec_end.normalized()

    for f in range(frames):
        # t 从 0 到 1，均匀插值
        if frames > 1:
            t = f / (frames - 1)
        else:
            t = 0.0

        # 使用球面线性插值 (slerp) 在球面上插值
        # slerp 在单位球面上插值，然后乘以半径
        vec_interpolated = vec_start_norm.slerp(vec_end_norm, t) * radius
        
        # 转换回世界坐标
        pos = target + vec_interpolated

        # 计算从摄像机位置指向目标点的方向
        direction_to_target = (target - pos).normalized()

        # 使用 to_track_quat 让摄像机朝向目标点
        # '-Z' 是摄像机的默认朝向轴，'Y' 是上方向
        quat = direction_to_target.to_track_quat('-Z', 'Y')

        scene.frame_set(f)
        camera.location = pos
        camera.rotation_euler = quat.to_euler()

        camera.keyframe_insert(data_path="location", frame=f)
        camera.keyframe_insert(data_path="rotation_euler", frame=f)

    print("[INFO] Arc rotation keyframes (location + rotation) inserted.")


def setup_render(output_path, frames, fps):
    """设置渲染为 H264 MP4 输出."""
    scene = bpy.context.scene

    scene.frame_start = 0
    scene.frame_end = frames - 1
    scene.render.fps = fps

    # 输出路径；// 表示相对 .blend 所在目录
    scene.render.filepath = output_path

    # 引擎（这里使用 Cycles，设备由 enable_gpu_for_cycles 控制）
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

    # ★ 先启用 GPU 渲染（首选 CUDA）
    enable_gpu_for_cycles()

    clear_old_cameras()
    camera = create_camera()
    animate_arc_rotation(camera, START_POS, END_POS, TARGET_POS, FRAMES)
    setup_render(OUTPUT_PATH, FRAMES, FPS)

    print("[INFO] Start rendering animation...")
    bpy.ops.render.render(animation=True)
    print("[INFO] Rendering finished.")


if __name__ == "__main__":
    main()
