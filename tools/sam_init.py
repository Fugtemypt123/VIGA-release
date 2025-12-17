import os, sys, json, subprocess, shutil
import numpy as np
from mcp.server.fastmcp import FastMCP
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.path import path_to_cmd

# tool_configs for agent (only the function w/ @mcp.tool)
tool_configs = [
    {
        "type": "function",
        "function": {
            "name": "reconstruct_full_scene",
            "description": "Reconstruct a complete 3D scene from an input image by detecting all objects with SAM and reconstructing each with SAM-3D. Outputs a .blend file containing all reconstructed objects.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAM_WORKER = os.path.join(os.path.dirname(__file__), "sam_worker.py")
SAM3D_WORKER = os.path.join(os.path.dirname(__file__), "sam3d_worker.py")
IMPORT_SCRIPT = os.path.join(os.path.dirname(__file__), "import_glbs_to_blend.py")

mcp = FastMCP("sam-init")
_target_image = _output_dir = _sam3_cfg = _blender_command = None
_sam_env_bin = path_to_cmd["tools/sam_worker.py"]
_sam3d_env_bin = path_to_cmd.get("tools/sam3d_worker.py")


@mcp.tool()
def initialize(args: dict) -> dict:
    global _target_image, _output_dir, _sam3_cfg, _blender_command, _sam_env_bin
    _target_image = args["target_image_path"]
    _output_dir = args.get("output_dir") + "/sam_init"
    if os.path.exists(_output_dir):
        shutil.rmtree(_output_dir)
    os.makedirs(_output_dir, exist_ok=True)
    _sam3_cfg = args.get("sam3d_config_path") or os.path.join(
        ROOT, "utils", "sam3d", "checkpoints", "hf", "pipeline.yaml"
    )
    _blender_command = args.get("blender_command") or "utils/infinigen/blender/blender"
    
    # 尝试获取 sam_worker.py 的 python 路径
    # 如果没有配置，使用 sam3d 的环境（假设它们可能在同一环境）
    _sam_env_bin = path_to_cmd.get("tools/sam_worker.py") or _sam3d_env_bin
    
    return {"status": "success", "output": {"text": ["sam init initialized"], "tool_configs": tool_configs}}


def process_single_object(idx, mask, object_name):
    """
    处理单个物体的 SAM-3D 重建
    返回 (object_name, glb_path, transform_info) 或 None
    """
    global _target_image, _output_dir, _sam3_cfg, _sam3d_env_bin
    
    object_dir = os.path.join(_output_dir, object_name)
    os.makedirs(object_dir, exist_ok=True)
    
    mask_path = os.path.join(object_dir, "mask.npy")
    np.save(mask_path, mask)
    
    glb_path = os.path.join(object_dir, f"{object_name}.glb")
    
    try:
        r = subprocess.run(
            [
                _sam3d_env_bin,
                SAM3D_WORKER,
                "--image", _target_image,
                "--mask", mask_path,
                "--config", _sam3_cfg,
                "--glb", glb_path,
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        
        # 解析 SAM3D worker 的输出获取变换信息
        result = json.loads(r.stdout.strip().splitlines()[-1])
        if result.get("status") != "success":
            print(f"[SAM_INIT] Failed to reconstruct {object_name}: {result.get('message', 'Unknown error')}")
            return None
        
        transform_info = {
            "glb": glb_path,
            "translation": result.get("translation"),
            "translation_scale": result.get("translation_scale"),
            "rotation": result.get("rotation"),
            "scale": result.get("scale", 1.0),
        }
        
        print(f"[SAM_INIT] Successfully reconstructed {object_name}")
        return (object_name, glb_path, transform_info)
        
    except subprocess.CalledProcessError as e:
        print(f"[SAM_INIT] Error reconstructing {object_name}: {e.stderr}")
        return None
    except Exception as e:
        print(f"[SAM_INIT] Error reconstructing {object_name}: {e}")
        return None


@mcp.tool()
def reconstruct_full_scene() -> dict:
    """
    从输入图片重建完整的 3D 场景
    1. 使用 SAM 检测所有物体
    2. 对每个物体使用 SAM-3D 重建
    3. 将所有物体导入 Blender 并保存为 .blend 文件
    """
    global _target_image, _output_dir, _sam3_cfg, _blender_command, _sam_env_bin, _sam3d_env_bin
    
    if not _target_image or not _output_dir:
        return {"status": "error", "output": {"text": ["call initialize first"]}}
    
    if _sam_env_bin is None:
        return {"status": "error", "output": {"text": ["SAM worker python path not configured"]}}
    
    try:
        # Step 1: 使用 SAM 获取所有物体的 masks
        all_masks_path = os.path.join(_output_dir, "all_masks.npy")
        print(f"[SAM_INIT] Step 1: Detecting all objects with SAM...")
        subprocess.run(
            [
                _sam_env_bin,
                SAM_WORKER,
                "--image",
                _target_image,
                "--out",
                all_masks_path,
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        
        # Step 2: 加载 masks 和物体名称映射
        masks = np.load(all_masks_path, allow_pickle=True)
        
        # 处理 masks 可能是 object array 的情况
        if masks.dtype == object:
            masks = [m for m in masks]
        elif masks.ndim == 3:
            # 如果是 3D 数组 (N, H, W)，转换为列表
            masks = [masks[i] for i in range(masks.shape[0])]
        else:
            # 单个 mask 的情况
            masks = [masks]
        
        # 加载物体名称映射信息
        object_names_json_path = all_masks_path.replace('.npy', '_object_names.json')
        object_mapping = None
        if os.path.exists(object_names_json_path):
            with open(object_names_json_path, 'r') as f:
                object_names_info = json.load(f)
                object_mapping = object_names_info.get("object_mapping", [])
                print(f"[SAM_INIT] Loaded object names mapping from: {object_names_json_path}")
        else:
            print(f"[SAM_INIT] Warning: Object names mapping file not found: {object_names_json_path}, using default names")
        
        print(f"[SAM_INIT] Step 2: Reconstructing {len(masks)} objects with SAM-3D...")
        
        # Step 3: 逐个处理每个物体
        all_transforms = []
        success_count = 0
        
        for idx, mask in enumerate(masks):
            # 获取物体名称
            if object_mapping and idx < len(object_mapping):
                object_name = object_mapping[idx]
            else:
                object_name = f"object_{idx}"
            
            result = process_single_object(idx, mask, object_name)
            if result:
                object_name, glb_path, transform_info = result
                all_transforms.append(transform_info)
                success_count += 1
        
        if success_count == 0:
            return {"status": "error", "output": {"text": ["Failed to reconstruct any objects"]}}
        
        # Step 4: 保存变换信息到 JSON
        transforms_json_path = os.path.join(_output_dir, "object_transforms.json")
        with open(transforms_json_path, 'w') as f:
            json.dump(all_transforms, f, indent=2)
        print(f"[SAM_INIT] Saved transforms to: {transforms_json_path}")
        
        # Step 5: 使用 Blender 导入所有 GLB 文件并保存为 .blend
        blend_path = os.path.join(_output_dir, "scene.blend")
        blender_cmd = os.path.join(ROOT, _blender_command)
        
        print(f"[SAM_INIT] Step 3: Importing {success_count} GLB files into Blender...")
        subprocess.run(
            [
                blender_cmd,
                "-b",
                "-P", IMPORT_SCRIPT,
                "--",
                transforms_json_path,
                blend_path,
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        
        return {
            "status": "success",
            "output": {
                "text": [
                    f"Successfully reconstructed {success_count}/{len(masks)} objects",
                    f"Blender scene saved to: {blend_path}",
                    f"Total masks detected: {len(masks)}"
                ],
                "data": {
                    "blend_path": blend_path,
                    "num_objects": success_count,
                    "num_masks": len(masks),
                }
            }
        }
    
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        return {"status": "error", "output": {"text": [f"Process failed: {error_msg}"]}}
    except Exception as e:
        return {"status": "error", "output": {"text": [f"Error: {str(e)}"]}}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        initialize(
            {
                "target_image_path": "data/static_scene/christmas1/target.png",
                "output_dir": os.path.join(ROOT, "output", "test", "christmas1"),
                "blender_command": "utils/infinigen/blender/blender",
            }
        )
        print(reconstruct_full_scene())
    else:
        mcp.run()


if __name__ == "__main__":
    main()

# python tools/sam_init.py --test
# utils/infinigen/blender/blender -b -P /mnt/data/users/shaofengyin/AgenticVerifier/tools/import_glbs_to_blend.py -- /mnt/data/users/shaofengyin/AgenticVerifier/output/test/sam_init/object_transforms.json /mnt/data/users/shaofengyin/AgenticVerifier/output/test/sam_init/scene.blend
