# VIGA: Vision-as-Inverse-Graphics Agent

An **analysis-by-synthesis** code agent for programmatic visual reconstruction. VIGA approaches vision-as-inverse-graphics through iterative generation and verification: starting from an empty world, the agent writes scene programs, executes them to render candidate states, probes the scene from multiple viewpoints, identifies discrepancies against the input, and revises the program accordingly.

A single self-reflective agent alternates **Generator** and **Verifier** roles, drawing on a skill library of generation and verification tools while maintaining an evolving contextual memory of plans, code diffs, and render history. This design yields a multi-turn, execution-grounded procedure that is **self-correcting over time and requires no finetuning**—procedures and states remain entirely in the evolving context memory of the agent—enabling the same protocol to run across heterogeneous foundation VLMs, including closed commercial models.

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

## Project Structure

```
AgenticVerifier/
├── main.py                 # Main entry point for dual-agent loop
├── agents/                 # Core dual-agent implementation
│   ├── generator.py        # Generator agent logic
│   ├── verifier.py         # Verifier agent logic
│   ├── tool_client.py      # MCP tool client
│   └── prompt_builder.py   # System/user prompt construction
├── runners/                # Dataset runners for batch execution
│   ├── blendergym.py       # BlenderGym runner
│   ├── blenderstudio.py    # BlenderStudio runner
│   ├── static_scene.py     # Static scene runner
│   ├── dynamic_scene.py    # Dynamic scene runner
│   ├── autopresent.py      # AutoPresent runner
│   └── design2code.py      # Design2Code runner
├── tools/                  # Skill library (MCP tool servers)
│   ├── exec_blender.py     # execute_code: Blender execution & rendering
│   ├── exec_slides.py      # execute_code: PowerPoint generation
│   ├── exec_html.py        # execute_code: HTML/CSS rendering
│   ├── investigator.py     # Verification tools: initialize_viewpoint, set_camera, investigate
│   ├── meshy.py            # get_better_assets: 3D asset generation via Meshy API
│   ├── sam_init.py         # 3D scene reconstruction (SAM)
│   ├── initialize_plan.py  # make_plan: High-level action planning
│   ├── generator_base.py   # end_process for Generator
│   └── verifier_base.py    # end_process for Verifier
├── prompts/                # System and user prompts per mode
├── data/                   # Datasets for each mode
├── evaluators/             # Mode-specific evaluation scripts
├── utils/                  # Utility modules
├── requirements/           # Environment requirement files
└── output/                 # Output directory for runs
```

## Installation

### 1. Create Virtual Environments

Since MCP decouples agents and tools, we recommend creating separate environments:

```bash
# Agent environment (required)
conda create -n agent python=3.10
conda activate agent
pip install -r requirements/requirement_agent.txt

# Blender environment (for 3D modes)
conda create -n blender python=3.11
conda activate blender
pip install -r requirements/requirement_blender.txt

# PPTX environment (for AutoPresent)
conda create -n pptx python=3.10
conda activate pptx
pip install -r requirements/requirement_pptx.txt

# Web environment (for Design2Code)
conda create -n web python=3.10
conda activate web
pip install -r requirements/requirement_web.txt

# VLLM environment (for Qwen model deployment)
conda create -n vllm python=3.10
conda activate vllm
pip install -r requirements/requirement_vllm.txt

# Eval-Blender environment (for evaluating 3D modes)
conda create -n eval-blender python=3.11
conda activate eval-blender
pip install -r requirements/requirement_eval-blender.txt

# Eval-PPTX environment (for evaluating AutoPresent)
conda create -n eval-pptx python=3.10
conda activate eval-pptx
pip install -r requirements/requirement_eval-pptx.txt

# SAM environment (for SAM tool)
conda create -n sam python=3.10
conda activate sam
pip install -r requirements/requirement_sam.txt

# SAM3 environment (for SAM tool)
conda create -n sam3 python=3.12
conda activate sam3
pip install -r requirements/requirement_sam3.txt

# SAM3D environment (for SAM tool)
conda create -n sam3d-objects python=3.11
conda activate sam3d-objects
pip install -r requirements/requirement_sam3d-objects.txt
```

### 2. External Dependencies

#### Blender (for 3D modes)

For BlenderGym, you need a specific version of Infinigen:

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
# Verify installation
/usr/bin/python3 /usr/bin/unoconv --version
```

#### Google Chrome (for Design2Code)

```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
```

### 3. Configuration

Create configuration files in `utils/`:

**`utils/_api_keys.py`**:
```python
OPENAI_API_KEY = "your-openai-api-key"
OPENAI_BASE_URL = "https://api.openai.com/v1"
CLAUDE_API_KEY = "your-claude-api-key"
CLAUDE_BASE_URL = "https://api.anthropic.com/v1"
GEMINI_API_KEY = "your-gemini-api-key"
MESHY_API_KEY = "your-meshy-api-key"  # For 3D asset generation
VA_API_KEY = "your-va-api-key"
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

## Usage

### Main Entry Point

```bash
python main.py --mode <mode> --model <model> [options]
```

#### Common Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--mode` | Mode: blendergym, blenderstudio, static_scene, dynamic_scene, autopresent, design2code | Required |
| `--model` | Vision model (gpt-4o, claude-sonnet-4, gemini-2.5-pro, etc.) | gpt-4o |
| `--api-key` | API key for the model | From env |
| `--api-base-url` | API base URL | From env |
| `--max-rounds` | Maximum interaction rounds | 10 |
| `--memory-length` | Chat history length | 12 |
| `--output-dir` | Output directory | None |
| `--init-code-path` | Path to initial code file | None |
| `--init-image-path` | Path to initial images | None |
| `--target-image-path` | Path to target images | None |
| `--target-description` | Natural language task description | None |
| `--generator-tools` | Comma-separated generator tool scripts | tools/generator_base.py |
| `--verifier-tools` | Comma-separated verifier tool scripts | tools/verifier_base.py |
| `--no-tools` | Disable tool calling mode | False |
| `--clear-memory` | Clear memory between rounds | False |

#### Blender-specific Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--blender-command` | Path to Blender executable | utils/infinigen/blender/blender |
| `--blender-file` | Blender template file | None |
| `--blender-script` | Blender execution script | data/blendergym/pipeline_render_script.py |
| `--gpu-devices` | GPU devices for rendering | From CUDA_VISIBLE_DEVICES |

---

## Runners

Runners provide batch execution for datasets with parallel processing support.

### BlenderGym Runner

Run 3D scene modification tasks:

```bash
python runners/blendergym.py \
    --dataset-path data/blendergym \
    --task all \
    --model gpt-4o \
    --max-rounds 10 \
    --max-workers 8
```

#### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset-path` | Path to BlenderGym dataset | data/blendergym |
| `--task` | Task type: all, blendshape, geometry, lighting, material, placement | all |
| `--task-id` | Specific task ID (e.g., "1") | None |
| `--test-id` | Retest failed tasks from previous run | None |
| `--max-rounds` | Maximum interaction rounds | 10 |
| `--model` | Vision model | gpt-4o |
| `--memory-length` | Memory length | 24 |
| `--max-workers` | Parallel workers | 8 |
| `--sequential` | Run sequentially | False |
| `--no-tools` | Disable tools | False |
| `--generator-tools` | Generator tool servers | tools/exec_blender.py,tools/generator_base.py,tools/initialize_plan.py |
| `--verifier-tools` | Verifier tool servers | tools/verifier_base.py,tools/investigator.py |

### BlenderStudio Runner

Run progressive 3D scene generation tasks:

```bash
python runners/blenderstudio.py \
    --dataset-path data/blenderstudio \
    --task all \
    --model gpt-4o \
    --max-workers 8
```

#### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset-path` | Path to BlenderStudio dataset | data/blenderstudio |
| `--task` | Task level: all, level1, level2, level3 | all |
| `--task-id` | Specific task ID | None |
| `--test-id` | Retest failed tasks | None |
| `--max-rounds` | Maximum interaction rounds | 10 |
| `--model` | Vision model | gpt-4o |
| `--max-workers` | Parallel workers | 8 |

### Static Scene Runner

Create 3D scenes from scratch using target images:

```bash
python runners/static_scene.py \
    --dataset-path data/static_scene \
    --task all \
    --model gpt-4o \
    --max-rounds 100
```

#### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset-path` | Path to static scene dataset | data/static_scene |
| `--task` | Task name or "all" | all |
| `--test-id` | Test ID for output naming | None |
| `--max-rounds` | Maximum interaction rounds | 100 |
| `--model` | Vision model | gpt-5 |
| `--memory-length` | Memory length | 12 |
| `--prompt-setting` | Prompt setting: none, procedural, scene_graph, get_asset | none |
| `--init-setting` | Init setting: none, minimal, reasonable | none |
| `--max-workers` | Parallel workers | 1 |
| `--text-only` | Use only text as reference | False |
| `--generator-tools` | Generator tools | tools/exec_blender.py,tools/generator_base.py,tools/meshy.py,tools/initialize_plan.py |
| `--verifier-tools` | Verifier tools | tools/investigator.py,tools/verifier_base.py |

### Dynamic Scene Runner

Generate animated 3D scenes:

```bash
python runners/dynamic_scene.py \
    --dataset-path data/dynamic_scene \
    --task all \
    --model gpt-4o \
    --max-rounds 100
```

#### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset-path` | Path to dynamic scene dataset | data/dynamic_scene |
| `--task` | Task name or "all" | all |
| `--test-id` | Test ID for output naming | None |
| `--max-rounds` | Maximum interaction rounds | 100 |
| `--model` | Vision model | gpt-5 |
| `--prompt-setting` | Prompt setting: none, init | none |
| `--text-only` | Use only text as reference | False |
| `--generator-tools` | Generator tools | tools/exec_blender.py,tools/generator_base.py,tools/initialize_plan.py |
| `--verifier-tools` | Verifier tools | tools/investigator.py,tools/verifier_base.py |

### AutoPresent Runner

Generate presentation slides:

```bash
python runners/autopresent.py \
    --dataset-path data/autopresent/examples \
    --task all \
    --model gpt-4o \
    --max-workers 8
```

#### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset-path` | Path to AutoPresent dataset | data/autopresent/examples |
| `--task` | Task category: all, art_photos, business, design, entrepreneur, environment, food, marketing, social_media, technology | all |
| `--task-id` | Specific task ID | None |
| `--test-id` | Retest failed tasks | None |
| `--max-rounds` | Maximum interaction rounds | 10 |
| `--model` | Vision model | gpt-4o |
| `--max-workers` | Parallel workers | 8 |
| `--sequential` | Run sequentially | False |
| `--generator-tools` | Generator tools | tools/exec_slides.py,tools/generator_base.py |
| `--verifier-tools` | Verifier tools | tools/verifier_base.py |

### Design2Code Runner

Generate HTML/CSS from design images:

```bash
python runners/design2code.py \
    --dataset-path data/design2code/Design2Code-HARD \
    --model gpt-4o \
    --max-workers 8
```

#### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--dataset-path` | Path to Design2Code dataset | data/design2code/Design2Code-HARD |
| `--case-id` | Specific case ID | None |
| `--max-rounds` | Maximum interaction rounds | 10 |
| `--model` | Vision model | gpt-4o |
| `--memory-length` | Memory length | 12 |
| `--max-workers` | Parallel workers | 8 |
| `--sequential` | Run sequentially | False |
| `--browser-command` | Browser for screenshots | google-chrome |
| `--generator-tools` | Generator tools | tools/exec_html.py,tools/generator_base.py |
| `--verifier-tools` | Verifier tools | tools/verifier_base.py |

---

## Supported Models

VIGA supports multiple vision-language models (the same protocol works across heterogeneous foundation VLMs):

- **OpenAI**: gpt-4o, gpt-4-turbo, gpt-4o-mini
- **Anthropic**: claude-sonnet-4, claude-opus-4.5
- **Google**: gemini-2.5-pro, gemini-2.0-flash
- **Qwen**: qwen-vl-max, qwen-vl-plus

---

## Output Structure

Each task generates output capturing the evolving contextual memory (the iterative write→run→compare→revise trajectory):

```
output/<mode>/<timestamp>/<task_name>/
├── generator_thoughts/     # Generator synthesis logs (plans, code edits)
├── verifier_thoughts/      # Verifier analysis logs (discrepancies, suggestions)
├── renders/                # Rendered scene states per iteration
│   ├── 1/                  # s1 = exec(p1)
│   ├── 2/                  # s2 = exec(p2)
│   └── ...
├── codes/                  # Scene programs per iteration
├── scores.json             # Evaluation metrics
├── args.json               # Task configuration
└── blender_file.blend      # Final reconstructed scene (3D modes)
```

---

## Architecture: Analysis-by-Synthesis Loop

VIGA operates through an iterative analysis-by-synthesis (AbS) loop where scene recovery (analysis) is achieved through generating candidate scenes (synthesis) and comparing them to target images. The agent is initialized with an empty context memory M₀ = ∅ and aims to produce a program p_T after T iterations:

```
┌─────────────────────────────────────────────────────────────┐
│                     Input (Target)                          │
│           (reference image / task description)              │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              SYNTHESIS: Generator Role                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • make_plan: Write high-level action plan            │   │
│  │ • execute_code: Run program to construct scene       │   │
│  │ • get_scene_info: Query object attributes            │   │
│  │ • get_better_assets: Retrieve/generate 3D assets     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Render Scene State                        │
│              st = exec(pt) → rendered image                 │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              ANALYSIS: Verifier Role                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ • initialize_viewpoint: Compute canonical views      │   │
│  │ • set_camera / investigate: Explore from viewpoints  │   │
│  │ • Identify visual discrepancies vs target            │   │
│  │ • Generate structured feedback & suggestions         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  Memory Update                              │
│     M_{t+1} = Tail_L(M_t || c_t)  (sliding window)          │
│   Retains most recent L iterations, reducing cost from      │
│   O(N²) to O(N·k) while keeping optimal reasoning range     │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  writes → runs →      │
              │  compares → revises   │
              │    (Loop or STOP)     │
              └───────────────────────┘
```

## Skill Library

VIGA uses a versatile skill library supporting both generation and verification (see Table 1 in paper):

| Tool | Role | Description |
|------|------|-------------|
| **Generation Tools** | |
| `make_plan` | Generator | Write an explicit high-level action plan before editing, helping the agent maintain long-horizon consistency instead of reacting myopically at each step |
| `execute_code` | Generator | Execute the current program to construct or update the scene, providing fresh renderings for the next verification step |
| `get_scene_info` | Generator | Query object attributes (e.g., position, rotation, scale) and summarize them as text, so the model can reason semantically about numeric parameters |
| `get_better_assets` | Generator | Retrieve or generate improved assets when existing ones are visually unsatisfactory, then insert them into the scene program |
| `end_process` | Generator | Signal that no further edits are needed and terminate the generation loop |
| **Verification Tools** | |
| `initialize_viewpoint` | Verifier | Given target objects, compute a joint bounding box and render canonical diagnostic views, exposing the scene from informative camera poses |
| `set_camera` | Verifier | Move the camera to a specified pose to inspect the scene from a particular viewpoint |
| `investigate` | Verifier | Adjust the camera using natural language commands (e.g., "rotate left", "zoom out"), turning low-level camera control into interpretable language actions |
| `set_keyframe` | Verifier | Navigate along the timeline in 4D scenes to inspect different keyframes and motion phases |
| `set_visibility` | Verifier | Toggle object visibility to reveal occluded content or isolate specific parts of the scene |
| `get_scene_info` | Verifier | Summarize the current scene structure and object states as text, which is then used to form feedback for the Generator |
| `end_process` | Verifier | Indicate that verification is complete and terminate the observation loop |

---

## Evaluation

### Metrics

VIGA is evaluated using three complementary metrics:

| Metric | Description |
|--------|-------------|
| **PL Loss** | Program-level loss measuring textual and structural differences between predicted and target code (lower is better) |
| **N-CLIP Score** | Negative-CLIP score measuring semantic alignment between rendered results and target images (lower is better) |
| **VLM Score** | VLM-based metric rating task completion, visual quality, spatial accuracy, and detail fidelity on a 0–5 scale (higher is better) |

### BlenderBench

We introduce **BlenderBench**, a more challenging benchmark that extends BlenderGym with 30 curated tasks covering:

| Task Type | Description |
|-----------|-------------|
| **Task 1: Camera Adjustment** | Adjust camera parameters to align with the target's viewpoint |
| **Task 2: Multi-step Graphic Editing** | Perform multi-step reasoning to infer latent variables such as lighting or occluded object states |
| **Task 3: Compositional Graphic Editing** | Simulate complex real-world environments that combine both spatial alignment and reasoning challenges |

BlenderBench addresses limitations of existing benchmarks by requiring both observation tools (for viewpoint control) and contextual memory (for multi-step reasoning).

---

## License

MIT License

---

## Citation

If you use VIGA in your research, please cite:

```bibtex
@inproceedings{viga2025,
  title     = {Vision-as-Inverse-Graphics as a VLM Coding Agent},
  booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  year      = {2025}
}
```
