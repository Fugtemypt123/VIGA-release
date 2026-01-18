# VIGA: Vision-as-Inverse-Graphics Agent

<p align="center">
  <a href="https://viga-agent.github.io/"><img src="https://img.shields.io/badge/Project-Page-green" alt="Project Page"></a>
  <a href="https://arxiv.org/abs/XXX"><img src="https://img.shields.io/badge/arXiv-XXX-red" alt="arXiv"></a>
  <a href="https://huggingface.co/XXX"><img src="https://img.shields.io/badge/Dataset-HF-yellow" alt="Hugging Face"></a>
</p>

## Introduction

VIGA is an **analysis-by-synthesis** code agent for programmatic visual reconstruction. It approaches vision-as-inverse-graphics through an iterative loop of generating, rendering, and verifying scenes against target images.

<p align="center">
  <img src="docs/images/method_new.png" alt="VIGA Method Overview" width="800">
</p>

A single self-reflective agent alternates between two roles:

- **Generator**: Writes and executes scene programs using tools for planning, code execution, asset retrieval, and scene queries.

- **Verifier**: Examines rendered output from multiple viewpoints, identifies visual discrepancies, and provides feedback for the next iteration.

The agent maintains an **evolving contextual memory** with plans, code diffs, and render history. This write → run → compare → revise loop is **self-correcting and requires no finetuning**, enabling the same protocol to run across different foundation VLMs.

## Supported Domains

VIGA naturally generalizes across 2D, 3D, and 4D visual tasks through its analysis-by-synthesis loop:

| Mode | Description | Output |
|------|-------------|--------|
| **BlenderGym** | Single-step 3D graphics editing | Blender Python code |
| **BlenderStudio** | Multi-step 3D graphics editing (Level 1-3) | Blender Python code |
| **Static Scene** | Single-view 3D scene reconstruction from scratch | Blender scene (.blend) |
| **Dynamic Scene** | 4D dynamic scene reconstruction with physics | Blender animation |
| **AutoPresent** | 2D programmatic slide/document layout synthesis | PowerPoint (PPTX) |
| **Design2Code** | 2D layout synthesis from design images | HTML/CSS files |

## Installation

### 1. Requirements

VIGA requires Python 3.10+ and uses separate environments for agents and tools (via MCP):

```bash
# Agent environment (required)
conda create -n agent python=3.10
conda activate agent
pip install -r requirements/requirement_agent.txt
```

### 2. Tool Environments

Install tool environments based on the modes you want to run:

```bash
# For 3D modes (BlenderGym, BlenderStudio, Static/Dynamic Scene)
conda create -n blender python=3.11
conda activate blender
pip install -r requirements/requirement_blender.txt

# For AutoPresent
conda create -n pptx python=3.10
conda activate pptx
pip install -r requirements/requirement_pptx.txt

# For Design2Code
conda create -n web python=3.10
conda activate web
pip install -r requirements/requirement_web.txt
```

### 3. External Dependencies

#### Blender (for 3D modes)

For BlenderGym:
```bash
cd utils
git clone git@github.com:richard-guyunqi/infinigen.git
cd infinigen
INFINIGEN_MINIMAL_INSTALL=True bash scripts/install/interactive_blender.sh
```

For other 3D modes (static_scene, dynamic_scene, blenderstudio):
```bash
cd utils
git clone https://github.com/princeton-vl/infinigen.git
bash scripts/install/interactive_blender.sh
```

#### LibreOffice (for AutoPresent)

```bash
sudo apt install -y libreoffice unoconv
```

#### Google Chrome (for Design2Code)

```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
```

### 4. Configuration

Create configuration files in `utils/`:

**`utils/_api_keys.py`**:
```python
OPENAI_API_KEY = "your-openai-api-key"
OPENAI_BASE_URL = "https://api.openai.com/v1"
CLAUDE_API_KEY = "your-claude-api-key"
CLAUDE_BASE_URL = "https://api.anthropic.com/v1"
GEMINI_API_KEY = "your-gemini-api-key"
MESHY_API_KEY = "your-meshy-api-key"  # For 3D asset generation
```

**`utils/_path.py`**:
```python
# Configure paths for different tool environments
path_to_cmd = {
    "tools/exec_blender.py": "/path/to/blender/env/bin/python",
    "tools/exec_slides.py": "/path/to/pptx/env/bin/python",
    "tools/exec_html.py": "/path/to/web/env/bin/python",
    # Add other tool paths as needed
}
```

## Quick Start

### Demo: BlenderGym

Run a single BlenderGym task:

```bash
conda activate agent
python main.py \
    --mode blendergym \
    --model gpt-4o \
    --target-image-path data/blendergym/placement/1/target.png \
    --init-code-path data/blendergym/placement/1/code.py \
    --blender-file data/blendergym/placement/1/scene.blend \
    --max-rounds 10
```

### Demo: Static Scene Reconstruction

Reconstruct a 3D scene from a single image:

```bash
conda activate agent
python main.py \
    --mode static_scene \
    --model gpt-4o \
    --target-image-path data/static_scene/kitchen/reference.jpg \
    --max-rounds 100
```

### Demo: AutoPresent

Generate a PowerPoint presentation:

```bash
conda activate agent
python main.py \
    --mode autopresent \
    --model gpt-4o \
    --target-image-path data/autopresent/examples/business/1/target.png \
    --max-rounds 10
```

## Batch Execution

For batch processing of datasets, use the runners:

```bash
# BlenderGym
python runners/blendergym.py --dataset-path data/blendergym --task all --model gpt-4o

# BlenderStudio
python runners/blenderstudio.py --dataset-path data/blenderstudio --task all --model gpt-4o

# Static Scene
python runners/static_scene.py --dataset-path data/static_scene --task all --model gpt-4o

# AutoPresent
python runners/autopresent.py --dataset-path data/autopresent/examples --task all --model gpt-4o

# Design2Code
python runners/design2code.py --dataset-path data/design2code/Design2Code-HARD --model gpt-4o
```

See [docs/RUNNERS.md](docs/RUNNERS.md) for detailed runner documentation.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and skill library
- [Runners](docs/RUNNERS.md) - Batch execution and command-line options
- [Evaluation](docs/EVALUATION.md) - Metrics and benchmarks

## License

MIT License

## Citation

If you use VIGA in your research, please cite:

```bibtex
@inproceedings{viga2025,
  title     = {Vision-as-Inverse-Graphics as a VLM Coding Agent},
  booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year      = {2025}
}
```
