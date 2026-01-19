# VIGA: Vision-as-Inverse-Graphics Agent

<p align="center">
  <a href="https://fugtemypt123.github.io/VIGA-website/"><img src="https://img.shields.io/badge/Project-Page-blue" alt="Project Page"></a>
  <a href="https://arxiv.org/abs/2601.11109"><img src="https://img.shields.io/badge/arXiv-VIGA-red" alt="arXiv"></a>
  <a href="https://huggingface.co/datasets/DietCoke4671/blenderbench"><img src="https://img.shields.io/badge/Benchmark-HF-yellow" alt="Hugging Face"></a>
</p>

## Quick Setup

### 1. Create Conda Environments

```bash
# Agent environment
conda create -n agent python=3.10 -y && conda activate agent
pip install -r requirements/requirement_agent.txt

# Blender environment with Infinigen
conda create -n blender python=3.11 -y && conda activate blender
pip install -r requirements/requirement_blender.txt
cd utils && git clone https://github.com/princeton-vl/infinigen.git && cd infinigen
bash scripts/install/interactive_blender.sh && cd ../..

# SAM environments
conda create -n sam python=3.10 -y && conda activate sam
pip install -r requirements/requirement_sam.txt

conda create -n sam3 python=3.10 -y && conda activate sam3
pip install -r requirements/requirement_sam3.txt

conda create -n sam3d-objects python=3.11 -y && conda activate sam3d-objects
pip install -r requirements/requirement_sam3d-objects.txt
```

### 2. Configure API Keys

Create `utils/_api_keys.py`:
```python
OPENAI_API_KEY = "your-key"
OPENAI_BASE_URL = "https://api.openai.com/v1"
MESHY_API_KEY = "your-meshy-key"  # For 3D assets
```

### 3. Run Dynamic Scene

```bash
conda activate agent
python runners/dynamic_scene.py --dataset-path data/dynamic_scene --task all --model gpt-4o
```

## Full Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and skill library
- [Conda Setup](requirements/readme.md) - Detailed Conda installation guide
- [Runners](docs/RUNNERS.md) - Batch execution and command-line options

## Citation

```bibtex
@inproceedings{viga2025,
  title     = {Vision-as-Inverse-Graphics as a VLM Coding Agent},
  booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year      = {2025}
}
```
