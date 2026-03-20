import logging

from rules import FIXES


def print_report(results, features, logname, flight_time):
    """Print terminal-friendly diagnosis summary and fixes."""
    B = "\033[1m"
    R = "\033[0m"
    RED = "\033[91m"
    YEL = "\033[93m"
    GRN = "\033[92m"
    CYN = "\033[96m"
    GRY = "\033[90m"

    root_cause, confidence, evidence = results[0]
    col = RED if confidence > 0.75 else YEL if confidence > 0.50 else GRY

    width = 64
    logging.info("\n" + "=" * width)
    logging.info(f"  {B}ArduDiag - AI-Assisted Log Diagnosis  v0.1{R}")
    logging.info(f"  {GRY}GSoC 2026  |  Dijo  |  github.com/Dijo-404{R}")
    logging.info("=" * width)
    logging.info(f"  Log:          {logname}")
    logging.info(f"  Flight time:  {int(flight_time//60)}m {int(flight_time%60)}s")
    logging.info("-" * width)

    bar_len = int(confidence * 32)
    bar = "#" * bar_len + "-" * (32 - bar_len)
    logging.info(f"\n  {B}ROOT CAUSE :{R}  {col}{B}{root_cause.replace('_',' ').upper()}{R}")
    logging.info(f"  Confidence  :  {col}[{bar}] {confidence*100:.0f}%{R}")
    logging.info(f"  Evidence    :  {CYN}{evidence}{R}")

    if len(results) > 1:
        logging.info(f"\n  {GRY}Other candidates:{R}")
        for cls, conf, ev in results[1:3]:
            logging.info(f"  {GRY}  * {cls.replace('_',' '):<24} ({conf*100:.0f}%)  -  {ev[:52]}{R}")

    logging.info(f"\n  {B}{GRN}SUGGESTED FIXES:{R}")
    for i, fix in enumerate(FIXES.get(root_cause, [])[:4], 1):
        logging.info(f"  {GRN}{i}.{R} {fix}")

    logging.info(f"\n  {GRY}Features extracted ({len(features)} total):{R}")
    for key, value in sorted(features.items())[:8]:
        display_value = f"{value:.4f}" if isinstance(value, float) else str(value)
        logging.info(f"  {GRY}  {key:<36} {display_value}{R}")

    logging.info("\n" + "=" * width + "\n")
