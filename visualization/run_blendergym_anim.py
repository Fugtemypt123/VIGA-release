# run_blendergym_anim.py
# 枚举 scripts 目录下的脚本，使用 executor 执行并保存 .blend 文件，然后渲染动画
import sys
import argparse
import os
from pathlib import Path
import subprocess
import logging
from typing import Optional, Dict, Tuple
import base64
from PIL import Image
import io
import math

# Executor 类（从 run_blendergym_steps.py 复制）
class Executor:
    def __init__(self,
                 blender_command: str,
                 blender_file: str,
                 blender_script: str,
                 script_save: str,
                 render_save: str,
                 blender_save: Optional[str] = None,
                 gpu_devices: Optional[str] = None):
        self.blender_command = blender_command
        self.blender_file = blender_file
        self.blender_script = blender_script
        self.script_path = Path(script_save)
        self.render_path = Path(render_save)
        self.blender_save = blender_save
        self.gpu_devices = gpu_devices
        self.count = 0

        self.script_path.mkdir(parents=True, exist_ok=True)
        self.render_path.mkdir(parents=True, exist_ok=True)

    def _execute_blender(self, script_path: str, render_path: str = '') -> Tuple[bool, str, str]:
        cmd = [
            self.blender_command,
            "--background", self.blender_file,
            "--python", self.blender_script,
            "--", script_path, render_path
        ]
        if self.blender_save:
            cmd.append(self.blender_save)
        cmd_str = " ".join(cmd)
        
        env = os.environ.copy()
        if self.gpu_devices:
            env['CUDA_VISIBLE_DEVICES'] = self.gpu_devices
            logging.info(f"Setting CUDA_VISIBLE_DEVICES to: {self.gpu_devices}")
        env['AL_LIB_LOGLEVEL'] = '0'
        
        try:
            proc = subprocess.run(cmd_str, shell=True, check=True, capture_output=True, text=True, env=env)
            out = proc.stdout
            err = proc.stderr
            if os.path.isdir(render_path):
                imgs = sorted([str(p) for p in Path(render_path).glob("*") if p.suffix in ['.png','.jpg']])
                return True, imgs, out
            return True, out, err
        except subprocess.CalledProcessError as e:
            logging.error(f"Blender failed: {e}")
            return False, e.stderr, e.stdout

    def _parse_code(self, full_code: str) -> str:
        if full_code.startswith("```python") and full_code.endswith("```"):
            return full_code[len("```python"):-len("```")]
        return full_code

    def execute(self, code: str) -> Dict:
        self.count += 1
        code_file = self.script_path / f"{self.count}.py"
        render_file = self.render_path / f"{self.count}"
        code = self._parse_code(code)
        
        with open(code_file, "w") as f:
            f.write(code)
        os.makedirs(render_file, exist_ok=True)
        for img in os.listdir(render_file):
            os.remove(os.path.join(render_file, img))
            
        success, stdout, stderr = self._execute_blender(str(code_file), str(render_file))
        if not success:
            os.rmdir(render_file)
            return {"status": "error", "output": {"text": ['Error: ' + (stderr or stdout)]}}
        elif len(os.listdir(render_file)) == 0:
            os.rmdir(render_file)
            return {"status": "success", "output": {"text": ['The code executed successfully, but no image was generated. Please check and make sure that:\n(1) you have added the camera in the code (just modify the camera pose and other information, do not render the image in the code).\n(2) You may need to handle errors in the code. The following is the return message for reference. Please check if there are any errors and fix them: ' + (stderr or stdout)]}}
        else:
            return {"status": "success", "output": {"image": stdout, "text": [f"Render from camera {x}" for x in range(len(stdout))], 'require_verifier': True}}


logging.basicConfig(level=logging.INFO)

def calculate_camera_rotation_from_look_at(cam_loc: tuple, look_at: tuple) -> tuple:
    """
    从相机位置和目标点计算旋转欧拉角（度）
    返回 (rx, ry, rz) 以度为单位的欧拉角
    """
    import numpy as np
    
    cam_pos = np.array(cam_loc)
    target_pos = np.array(look_at)
    
    direction = target_pos - cam_pos
    distance = np.linalg.norm(direction)
    
    if distance < 1e-6:
        return (0.0, 0.0, 0.0)
    
    direction = direction / distance
    
    pitch = math.degrees(math.asin(-direction[2]))
    yaw = math.degrees(math.atan2(direction[1], direction[0]))
    
    rx = pitch
    ry = 0.0
    rz = yaw
    
    return (rx, ry, rz)

def create_render_script(render_dir: Path, cam_name: str, cam_loc: tuple, 
                        cam_rot_eul: tuple, lens: float, engine: str, 
                        res: tuple, file_format: str, samples: int, 
                        device: str, color_mgt_view: str, color_mgt_look: str,
                        fps: int, duration: float):
    """创建在 Blender 中运行的动画渲染脚本"""
    script_content = f'''import bpy
import sys

# 渲染输出路径
render_output = sys.argv[sys.argv.index("--") + 2] if len(sys.argv) > sys.argv.index("--") + 2 else None
if not render_output:
    print("Error: No render output path specified")
    sys.exit(1)
    
# 设置固定相机
cam_name = "{cam_name}"
cam_loc = {cam_loc}
cam_rot_eul = {cam_rot_eul}
lens = {lens}

cam_obj = bpy.data.objects.get(cam_name)
if cam_obj is None or cam_obj.type != 'CAMERA':
    cam_data = bpy.data.cameras.new(cam_name)
    cam_obj = bpy.data.objects.new(cam_name, cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

cam_obj.location = cam_loc
cam_obj.rotation_mode = 'XYZ'
cam_obj.rotation_euler = cam_rot_eul
cam_obj.data.lens = lens
bpy.context.scene.camera = cam_obj

# 渲染设置
scene = bpy.context.scene
W, H = {res}
scene.render.resolution_x = W
scene.render.resolution_y = H
scene.render.fps = {fps}
scene.view_settings.view_transform = "{color_mgt_view}"
scene.view_settings.look = "{color_mgt_look}"

# 设置动画帧范围
frames = max(1, int({duration} * {fps}))
scene.frame_start = 1
scene.frame_end = frames

if "{engine}" == "CYCLES":
    scene.render.engine = "CYCLES"
    cycles = scene.cycles
    cycles.device = "GPU" if "{device}" == "GPU" else "CPU"
    try:
        prefs = bpy.context.preferences
        prefs.addons["cycles"].preferences.compute_device_type = "CUDA"
    except Exception:
        pass
    cycles.samples = {samples}
    # 低采样时关闭自适应采样以加快速度
    cycles.use_adaptive_sampling = {samples} > 32
else:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = max(1, {samples})
    # EEVEE 快速设置
    scene.eevee.use_bloom = False  # 关闭 bloom 以加快渲染

# 设置视频编码
scene.render.image_settings.file_format = "{file_format}"
if "{file_format}" == "FFMPEG":
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    scene.render.ffmpeg.video_bitrate = 8000
    scene.render.ffmpeg.minrate = 0
    scene.render.ffmpeg.maxrate = 0
    scene.render.ffmpeg.buffersize = 1792
    scene.render.ffmpeg.gopsize = {fps}

# 渲染动画
bpy.context.scene.render.filepath = render_output
bpy.ops.render.render(animation=True)
print("Animation render completed to", bpy.context.scene.render.filepath)
'''
    return script_content

def create_empty_blend_file(blender_command: str, output_path: str, gpu_devices: Optional[str] = None) -> bool:
    """创建一个新的空 blender 文件"""
    create_empty_blend_cmd = (
        f"{blender_command} --background --factory-startup "
        f"--python-expr \"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.wm.save_mainfile(filepath='" + str(output_path) + "')\""
    )
    env = os.environ.copy()
    if gpu_devices:
        env['CUDA_VISIBLE_DEVICES'] = gpu_devices
    env['AL_LIB_LOGLEVEL'] = '0'
    
    try:
        subprocess.run(create_empty_blend_cmd, shell=True, check=True, env=env)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to create empty blend file: {e}")
        return False

def render_blend_file(blender_command: str, blend_file: str, render_output: str, 
                     render_script_content: str, gpu_devices: Optional[str] = None):
    """渲染单个 .blend 文件为动画"""
    render_script_path = Path(blend_file).parent / "_temp_render_anim.py"
    with open(render_script_path, "w") as f:
        f.write(render_script_content)
    
    cmd = [
        blender_command,
        "--background", blend_file,
        "--python", str(render_script_path),
        "--", blend_file, render_output
    ]
    cmd_str = " ".join(cmd)
    
    env = os.environ.copy()
    if gpu_devices:
        env['CUDA_VISIBLE_DEVICES'] = gpu_devices
    env['AL_LIB_LOGLEVEL'] = '0'
    
    try:
        proc = subprocess.run(cmd_str, shell=True, check=True, capture_output=True, text=True, env=env)
        return True, proc.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Render failed for {blend_file}: {e.stderr}")
        return False, e.stderr
    finally:
        if render_script_path.exists():
            render_script_path.unlink()

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, type=str, help="Output name (e.g., 20251028_133713)")
    ap.add_argument("--task", type=str, default="tofu17", help="Task name")
    ap.add_argument("--blender_command", type=str, default="utils/blender/infinigen/blender/blender", help="Blender command")
    ap.add_argument("--blender_script", type=str, default="visualization/video_script.py", help="Blender execution script")
    ap.add_argument("--blender_save", type=str, default=None, help="Directory to save intermediate .blend files")
    ap.add_argument("--render_dir", type=str, default=None, help="Directory to save rendered videos")
    ap.add_argument("--cam_name", type=str, default="AgentFixedCam")
    ap.add_argument("--cam_loc", type=str, default="0,-6,4", help="x,y,z")
    ap.add_argument("--cam_rot_eul", type=str, default=None, help="x,y,z (degrees, Euler XYZ). If not provided, use --look_at instead")
    ap.add_argument("--look_at", type=str, default=None, help="x,y,z - target point to look at. Alternative to --cam_rot_eul")
    ap.add_argument("--lens", type=float, default=35.0)
    ap.add_argument("--engine", type=str, default="BLENDER_EEVEE", choices=["BLENDER_EEVEE", "CYCLES"])
    ap.add_argument("--res", type=str, default="1280x720", help="分辨率，降低可加快渲染（如 960x540）")
    ap.add_argument("--device", type=str, default="GPU", choices=["GPU","CPU"], help="仅对 Cycles 有效")
    ap.add_argument("--samples", type=int, default=16, help="渲染采样，降低可加快渲染（EEVEE 推荐 16-32，Cycles 推荐 32-64）")
    ap.add_argument("--color_mgt_view", type=str, default="Filmic")
    ap.add_argument("--color_mgt_look", type=str, default="None")
    ap.add_argument("--file_format", type=str, default="FFMPEG", choices=["FFMPEG"])
    ap.add_argument("--fps", type=int, default=10, help="Frames per second")
    ap.add_argument("--duration", type=float, default=3.0, help="Animation duration in seconds")
    ap.add_argument("--gpu_devices", type=str, default=None, help="GPU devices (e.g., '0,1')")
    return ap.parse_args()

def main():
    args = parse_args()
    
    # 构建路径
    base_path = Path(f"/home/shaofengyin/AgenticVerifier/output/dynamic_scene/{args.name}/")
    for dir in os.listdir(base_path):
        base_path = base_path / dir / "video"
        os.makedirs(base_path, exist_ok=True)
        break
    
    scripts_dir = os.path.dirname(base_path) + "/scripts"
    if not os.path.exists(scripts_dir):
        logging.error(f"Scripts directory not found: {scripts_dir}")
        return
    
    # 设置输出目录
    if args.blender_save is None:
        args.blender_save = str(base_path)
    if args.render_dir is None:
        args.render_dir = str(base_path / "renders")
    
    blender_save_dir = Path(args.blender_save)
    render_dir = Path(args.render_dir)
    blender_save_dir.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建初始的空 blender 文件
    initial_blend_file = blender_save_dir / "video.blend"
    if initial_blend_file.exists():
        os.remove(initial_blend_file)
    create_empty_blend_cmd = (
        f"{args.blender_command} --background --factory-startup "
        f"--python-expr \"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.wm.save_mainfile(filepath='" + str(initial_blend_file) + "')\""
    )
    subprocess.run(create_empty_blend_cmd, shell=True, check=True)
    
    # 枚举脚本文件
    script_files = sorted(os.listdir(scripts_dir), key=lambda x: int(x.split('.')[0]))
    logging.info(f"Found {len(script_files)} script files")
    
    # 解析相机参数
    cam_loc = tuple(float(x) for x in args.cam_loc.split(","))
    
    # 处理 look_at 或 cam_rot_eul（注意：这些是度数，需要转换为弧度）
    if args.look_at:
        look_at_tuple = tuple(float(x) for x in args.look_at.split(","))
        logging.info(f"Using look_at: {look_at_tuple}, calculating rotation from camera position and target")
        cam_rot_eul_deg = calculate_camera_rotation_from_look_at(cam_loc, look_at_tuple)
        logging.info(f"Calculated cam_rot_eul (degrees): {cam_rot_eul_deg}")
        # 转换为弧度
        cam_rot_eul_tuple = tuple(math.radians(d) for d in cam_rot_eul_deg)
    elif args.cam_rot_eul:
        cam_rot_eul_deg = tuple(float(x) for x in args.cam_rot_eul.split(","))
        logging.info(f"Using cam_rot_eul (degrees): {cam_rot_eul_deg}")
        # 转换为弧度
        cam_rot_eul_tuple = tuple(math.radians(d) for d in cam_rot_eul_deg)
    else:
        logging.warning("Neither --look_at nor --cam_rot_eul provided, using default rotation (65,0,0 degrees)")
        cam_rot_eul_tuple = tuple(math.radians(d) for d in (65.0, 0.0, 0.0))
    
    W, H = (int(s) for s in args.res.lower().split("x"))
    
    # 创建渲染脚本内容（使用计算出的或提供的旋转角）
    render_script_content = create_render_script(
        render_dir, args.cam_name, cam_loc, cam_rot_eul_tuple, args.lens,
        args.engine, (W, H), args.file_format, args.samples, args.device,
        args.color_mgt_view, args.color_mgt_look, args.fps, args.duration
    )
    
    temp_executor = Executor(
        blender_command=args.blender_command,
        blender_file=str(initial_blend_file),
        blender_script=args.blender_script,
        script_save=str(os.path.join(os.path.dirname(render_dir), "scripts")),
        render_save=str(render_dir),
        blender_save=str(initial_blend_file),
        gpu_devices=args.gpu_devices
    )
    
    for script_file in script_files:
        step_num = script_file.split('.')[0]
        logging.info(f"[Step {step_num}] Processing {script_file}...")
        
        # 读取脚本内容
        with open(os.path.join(scripts_dir, script_file), "r") as f:
            code = f.read()
        
        # 执行脚本并保存 .blend 文件
        result = temp_executor.execute(code)
        if result["status"] != "success":
            logging.error(f"[Step {step_num}] Execution failed: {result['output'].get('text', ['Unknown error'])}")
            continue
        
        # # 渲染动画
        # render_output = render_dir / f"{step_num}.mp4"
        # success, output = render_blend_file(
        #     args.blender_command, str(initial_blend_file), str(render_output),
        #     render_script_content, args.gpu_devices
        # )
        
        # if success:
        #     logging.info(f"[Step {step_num}] Rendered: {render_output}")
        # else:
        #     logging.error(f"[Step {step_num}] Render failed: {output}")
    
    logging.info("[OK] All steps processed and rendered.")

if __name__ == "__main__":
    main()
