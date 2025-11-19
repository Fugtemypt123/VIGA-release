import bpy
import math
from mathutils import Vector, Matrix

# ==============================
# 可根据需求修改
# ==============================
CAM_START = Vector((0.0, -1.0, 1.0))
CAM_END   = Vector((0.0,  1.0, 1.0))
LOOK_AT   = Vector((0.0,  0.0, 1.0))

TARGET_TOTAL_FRAMES = 10   # 最终渲染的总帧数
FPS = 1
OUTPUT_PATH = "//table.mp4"
# ==============================


def ensure_camera():
    """若场景没有摄像机，则创建一个新摄像机。"""
    for obj in bpy.data.objects:
        if obj.type == "CAMERA":
            bpy.context.scene.camera = obj
            return obj

    cam_data = bpy.data.cameras.new("AutoCamera")
    cam = bpy.data.objects.new("AutoCamera", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def point_camera_to_target(camera, target_vec: Vector):
    """让摄像机看向 LOOK_AT 的方向."""
    direction = (target_vec - camera.location).normalized()
    quat = direction.to_track_quat('-Z', 'Y')
    camera.rotation_euler = quat.to_euler()


def animate_camera(camera):
    scene = bpy.context.scene

    for f in range(TARGET_TOTAL_FRAMES):
        t = f / (TARGET_TOTAL_FRAMES - 1)

        # 位置插值
        pos = CAM_START.lerp(CAM_END, t)

        scene.frame_set(f)
        camera.location = pos

        # 始终看向 LOOK_AT
        point_camera_to_target(camera, LOOK_AT)

        camera.keyframe_insert(data_path="location", frame=f)
        camera.keyframe_insert(data_path="rotation_euler", frame=f)

    print(f"[INFO] Camera animation created for {TARGET_TOTAL_FRAMES} frames.")


def retime_all_existing_animation():
    """
    把原始动画时间线从 (original_start → original_end)
    自动扩展/压缩到 (0 → TARGET_TOTAL_FRAMES - 1)。
    """
    scene = bpy.context.scene

    orig_start = scene.frame_start
    orig_end   = scene.frame_end

    print(f"[INFO] Original animation range: {orig_start} → {orig_end}")
    if orig_end <= orig_start:
        print("[WARN] Original animation invalid. Skipping retime.")
        return

    factor = (TARGET_TOTAL_FRAMES - 1) / (orig_end - orig_start)

    print(f"[INFO] Retiming factor = {factor:.4f}")

    # 对所有 F-Curve 进行时间缩放
    for action in bpy.data.actions:
        for fcurve in action.fcurves:
            for key in fcurve.keyframe_points:
                # 将关键帧映射到新的时间
                old_frame = key.co.x
                new_frame = (old_frame - orig_start) * factor
                key.co.x = new_frame
                key.handle_left.x = new_frame
                key.handle_right.x = new_frame

    # 设置场景新的起止帧
    scene.frame_start = 0
    scene.frame_end = TARGET_TOTAL_FRAMES - 1

    print("[INFO] All original animation retimed.")


def setup_render():
    scene = bpy.context.scene
    scene.render.filepath = OUTPUT_PATH
    scene.render.engine = "CYCLES"

    scene.render.fps = FPS
    scene.frame_start = 0
    scene.frame_end = TARGET_TOTAL_FRAMES - 1

    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100

    # 视频输出
    scene.render.image_settings.file_format = "FFMPEG"
    ffmpeg = scene.render.ffmpeg
    ffmpeg.format = "MPEG4"
    ffmpeg.codec = "H264"
    ffmpeg.constant_rate_factor = "MEDIUM"
    ffmpeg.ffmpeg_preset = "GOOD"

    print("[INFO] Render setup complete.")


def main():
    print("[INFO] Beginning processing...")

    # 1. 扩展原有动画
    retime_all_existing_animation()

    # 2. 创建摄像机动画
    cam = ensure_camera()
    animate_camera(cam)

    # 3. 设置渲染
    setup_render()

    # 4. 开始渲染
    print("[INFO] Rendering animation...")
    bpy.ops.render.render(animation=True)
    print("[INFO] Rendering finished.")


if __name__ == "__main__":
    main()
