import os
import argparse
import subprocess

example_dict = {
    "sufficient": {
        0: "runners/autopresent_baseline/prompt/example_full_pptx.txt",
        1: "runners/autopresent_baseline/prompt/example_full_wlib.txt",
    },
    "visual": {
        0: "runners/autopresent_baseline/prompt/example_noimg_pptx.txt",
        1: "runners/autopresent_baseline/prompt/example_noimg_wlib.txt",
    },
    "creative": {
        0: "runners/autopresent_baseline/prompt/example_hl_pptx.txt",
        1: "runners/autopresent_baseline/prompt/example_hl_wlib.txt",
    },
}

def main():
    command = []
    if args.setting != "sufficient":
        command.append("--no_image")
    if args.setting == "visual":
        command.extend(["--instruction_name", "instruction_no_image.txt"])
    elif args.setting == "creative":
        command.extend(["--instruction_name", "instruction_high_level.txt"])
        
    if args.use_library:
        if args.setting == "sufficient":
            command.extend(["--library_path", "runners/autopresent_baseline/library/library_basic.txt"])
        else:
            command.extend(["--library_path", "runners/autopresent_baseline/library/library.txt"])
    
    command.extend(["--example_path", example_dict[args.setting][int(args.use_library)]])

    if args.slide_deck == 'all':
        slide_dirs = ['art_photos', 'business', 'design', 'entrepreneur', 'environment', 'food', 'marketing', 'social_media', 'technology']
    else:
        slide_dirs = [args.slide_deck]

    for slide_name in slide_dirs:
        slide_dir = os.path.join("data/autopresent/examples", slide_name)
        page_dirs = [d for d in os.listdir(slide_dir) if d.startswith("slide_")]
        page_dirs = sorted(page_dirs, key=lambda x: int(x.split("_")[1]))
        for page_dir in page_dirs:
            output_path = os.path.join("data/autopresent/examples", slide_name, page_dir, f"baseline/{args.model_name.replace('-', '_')}.py")
            if os.path.exists(output_path.replace(".py", ".pptx")):
                continue

            print("Creating slide deck for", output_path.replace(".py", ".pptx"))
            slide_command = [
                "python", "runners/autopresent_baseline/create_slide.py",
                "--example_dir", f"data/autopresent/examples/{slide_name}/{page_dir}",
                "--model_name", args.model_name
            ] + command
            process = subprocess.Popen(slide_command)
            process.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slide_deck", type=str, default='all', 
                        help="Path to the slide deck")
    parser.add_argument("--setting", type=str, default="sufficient", 
                        choices=["sufficient", "visual", "creative"],
                        help="Experimental setting.")
    parser.add_argument("--use_library", action="store_true",
                        help="Use the library to create the slide deck.")
    parser.add_argument("--model_name", type=str, default="gpt-4o", 
                        help="Model name to use.")
    args = parser.parse_args()

    main()
