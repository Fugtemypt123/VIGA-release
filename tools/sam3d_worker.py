import os, sys, argparse, json
import numpy as np
import torch
from pytorch3d.transforms import quaternion_to_matrix, Transform3d

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "utils", "sam3d", "notebook"))
sys.path.append(os.path.join(ROOT, "utils", "sam3d"))

from inference import Inference, load_image

if "CONDA_PREFIX" not in os.environ:
    python_bin = sys.executable
    conda_env = os.path.dirname(os.path.dirname(python_bin))
    os.environ["CONDA_PREFIX"] = conda_env

R_yup_to_zup = torch.tensor([[-1,0,0],[0,0,1],[0,1,0]], dtype=torch.float32)
R_flip_z = torch.tensor([[1,0,0],[0,1,0],[0,0,-1]], dtype=torch.float32)
R_pytorch3d_to_cam = torch.tensor([[-1,0,0],[0,-1,0],[0,0,1]], dtype=torch.float32)
R_flip_y = torch.tensor([[1,0,0],[0,-1,0],[0,0,1]], dtype=torch.float32)  # 翻转Y轴以修正上下颠倒
R_flip_x = torch.tensor([[-1,0,0],[0,1,0],[0,0,1]], dtype=torch.float32)  # 翻转X轴以修正左右颠倒

def transform_mesh_vertices(vertices, rotation, translation, scale):
    if isinstance(vertices, np.ndarray):
        vertices = torch.tensor(vertices, dtype=torch.float32)

    vertices = vertices.unsqueeze(0)  #  batch dimension [1, N, 3]
    vertices = vertices @ R_flip_z.to(vertices.device) 
    vertices = vertices @ R_yup_to_zup.to(vertices.device)
    R_mat = quaternion_to_matrix(rotation.to(vertices.device))
    tfm = Transform3d(dtype=vertices.dtype, device=vertices.device)
    tfm = (
        tfm.scale(scale)
           .rotate(R_mat)
           .translate(translation[0], translation[1], translation[2])
    )
    vertices_world = tfm.transform_points(vertices)
    vertices_world = vertices_world @ R_pytorch3d_to_cam.to(vertices_world.device)
    vertices_world = vertices_world @ R_flip_y.to(vertices_world.device)  # 翻转Y轴以修正上下颠倒
    vertices_world = vertices_world @ R_flip_x.to(vertices_world.device)  # 翻转X轴以修正左右颠倒
    
    return vertices_world[0]  # remove batch dimension

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--mask", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--glb", required=True)
    args = p.parse_args()

    inference = Inference(args.config, compile=False)
    image = load_image(args.image)
    # args.mask 现在是 .npy 文件路径，直接加载为 numpy 数组
    
    mask = np.load(args.mask)
    mask = mask > 0
    output = inference(image, mask, seed=42)
    # output.keys: ['6drotation_normalized', 'scale', 'shape', 'translation', 'translation_scale', 'coords_original', 'coords', 'downsample_factor', 'rotation', 'mesh', 'gaussian', 'glb', 'gs', 'pointmap', 'pointmap_colors']
    # convert tensor to list
    
    mesh = output["glb"]
    vertices = mesh.vertices

    S = output["scale"][0].cpu().float()
    T = output["translation"][0].cpu().float()
    R = output["rotation"].squeeze().cpu().float()
    
    vertices_transformed = transform_mesh_vertices(vertices, R, T, S)
    mesh.vertices = vertices_transformed.cpu().numpy().astype(np.float32)

    os.makedirs(os.path.dirname(args.glb), exist_ok=True)
    mesh.export(args.glb)
    
    print(json.dumps({"glb_path": args.glb, "translation": T.tolist(), "rotation": R.tolist(), "scale": S.tolist()}))

if __name__ == "__main__":
    main()


# python tools/sam3d_worker.py --image data/static_scene/christmas1/target.png --mask output/test/sam3/snowman_mask.npy --config utils/sam3d/checkpoints/hf/pipeline.yaml --glb output/test/sam3/snowman.glb

# python tools/sam3d_worker.py --image data/static_scene/blackhouse/target.jpeg --mask output/static_scene/20251205_030616/blackhouse/house_mask.npy --config utils/sam3d/checkpoints/hf/pipeline.yaml --glb output/static_scene/20251205_030616/blackhouse/house.glb