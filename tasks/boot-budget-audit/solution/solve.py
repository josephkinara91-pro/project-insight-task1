"""Install the executable reference tool; its answers are computed at invocation."""
from pathlib import Path
import shutil

if __name__ == "__main__":
    shutil.copyfile(Path(__file__).with_name("reference.py"), "/app/boot_sequence.py")
