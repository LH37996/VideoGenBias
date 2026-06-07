from __future__ import annotations
import argparse
from pathlib import Path
from .io import load_config, load_results
from .report import generate_markdown_report
from .vector_report import generate_vector_report

def main():
    parser = argparse.ArgumentParser(description="VBench++-style bias analysis report generator (counts -> metrics -> markdown).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="Generate markdown report from results.")
    g.add_argument("--config", type=str, required=True, help="Path to experiment config YAML.")
    g.add_argument("--results", type=str, required=True, help="Path to results CSV/JSON.")
    g.add_argument("--out", type=str, required=True, help="Output directory.")

    args = parser.parse_args()
    if args.cmd == "generate":
        cfg = load_config(Path(args.config))
        results_path = Path(args.results)
        df = load_results(results_path)
        # Output goes to <out>/<input_stem>/ (e.g. outputs/results_en/)
        outdir = Path(args.out) / results_path.stem
        report_path = generate_markdown_report(cfg, df, outdir)
        print(f"[OK] Report generated: {report_path}")
        vector_path = generate_vector_report(cfg, df, outdir)
        print(f"[OK] Vector report generated: {vector_path}")

if __name__ == "__main__":
    main()
