import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VIEWER_BUILDER = Path(
    r"C:\Users\15114\.codex\skills\dpcr-interactive-viewer\scripts\build_dpcr_viewer.py"
)

WORKFLOWS = {
    "v2": ROOT / "workflow-template-v2.py",
    "standard": ROOT / "workflow-template-v2.py",
    "1210-2": ROOT / "workflow-1210-2.py",
    "1210-4": ROOT / "workflow-1210-4.py",
    "1126-3": ROOT / "workflow-1126-3.py",
    "1203-5": ROOT / "workflow-1203-5.py",
    "all-positive": ROOT / "workflow-1210-2.py",
}


def run_command(command, label):
    print(f"\n== {label} ==", flush=True)
    print(" ".join(f'"{part}"' if " " in str(part) else str(part) for part in command), flush=True)
    subprocess.run(command, check=True)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run the RT-dPCR image workflow and then build the interactive HTML viewer. "
            "Arguments after -- are passed directly to the selected workflow script."
        )
    )
    parser.add_argument(
        "--base-dir",
        required=True,
        help="Experiment folder containing original/ and receiving cropped/, corrected/, workflow_result/, interactive_viewer/.",
    )
    parser.add_argument(
        "--workflow",
        choices=sorted(WORKFLOWS),
        default="v2",
        help="Image-processing workflow to run. Use all-positive for all-positive experiments such as 1210-2.",
    )
    parser.add_argument("--result-dir", default=None, help="Override workflow_result output directory.")
    parser.add_argument("--viewer-dir", default=None, help="Override interactive viewer output directory.")
    parser.add_argument("--endpoint-photo", default="", help="Optional endpoint photo override for viewer background.")
    parser.add_argument("--skip-workflow", action="store_true", help="Only rebuild the viewer from existing CSV outputs.")
    parser.add_argument("--skip-viewer", action="store_true", help="Only run image processing; do not build the viewer.")
    parser.add_argument("--serve", action="store_true", help="Start a local static server after building the viewer.")
    parser.add_argument("--port", type=int, default=8766, help="Port used with --serve.")
    parser.add_argument("--open", action="store_true", help="Open the viewer URL in the default browser after --serve.")
    return parser


def main():
    parser = build_parser()
    args, workflow_args = parser.parse_known_args()

    base_dir = Path(args.base_dir).resolve()
    result_dir = Path(args.result_dir).resolve() if args.result_dir else base_dir / "workflow_result"
    viewer_dir = Path(args.viewer_dir).resolve() if args.viewer_dir else base_dir / "interactive_viewer"
    workflow_script = WORKFLOWS[args.workflow]

    if not workflow_script.exists():
      raise FileNotFoundError(f"Workflow script not found: {workflow_script}")
    if not VIEWER_BUILDER.exists():
      raise FileNotFoundError(f"Viewer builder not found: {VIEWER_BUILDER}")

    if not args.skip_workflow:
        command = [
            sys.executable,
            str(workflow_script),
            "--base-dir",
            str(base_dir),
            "--result-dir",
            str(result_dir),
            *workflow_args,
        ]
        run_command(command, f"Run image workflow ({args.workflow})")

    if not args.skip_viewer:
        command = [
            sys.executable,
            str(VIEWER_BUILDER),
            "--result-dir",
            str(result_dir),
            "--output-dir",
            str(viewer_dir),
        ]
        if args.endpoint_photo:
            command.extend(["--endpoint-photo", args.endpoint_photo])
        run_command(command, "Build interactive viewer")

    if args.serve:
        url = f"http://localhost:{args.port}/"
        print(f"\n== Serve viewer ==", flush=True)
        print(f"Viewer directory: {viewer_dir}", flush=True)
        print(f"URL: {url}", flush=True)
        if args.open:
            webbrowser.open(url)
        subprocess.run(
            [sys.executable, "-m", "http.server", str(args.port), "--directory", str(viewer_dir)],
            check=True,
        )
    else:
        print("\nDone.", flush=True)
        print(f"Result CSVs: {result_dir}", flush=True)
        print(f"Viewer: {viewer_dir}", flush=True)
        print(f"Open: {viewer_dir / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
