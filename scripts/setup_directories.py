#!/usr/bin/env python3
"""Setup required directories and copy example notebooks."""
import os
import shutil
from pathlib import Path


def setup_directories():
    """Create required directories and copy example files."""
    base_dir = Path(__file__).parent.parent
    
    # Create directories
    directories = [
        "notebooks",
        "outputs", 
        "examples"
    ]
    
    for dir_name in directories:
        dir_path = base_dir / dir_name
        dir_path.mkdir(exist_ok=True)
        print(f"Created directory: {dir_path}")
    
    # Copy example notebook to notebooks directory
    example_notebook = base_dir / "examples" / "debtors.ipynb"
    notebooks_dir = base_dir / "notebooks"
    
    if example_notebook.exists():
        dest_notebook = notebooks_dir / "debtors.ipynb"
        shutil.copy2(example_notebook, dest_notebook)
        print(f"Copied example notebook: {dest_notebook}")
    
    # Create .gitkeep files to preserve empty directories
    for dir_name in ["outputs"]:
        gitkeep_path = base_dir / dir_name / ".gitkeep"
        if not gitkeep_path.exists():
            gitkeep_path.touch()
            print(f"Created .gitkeep: {gitkeep_path}")
    
    print("\nDirectory setup completed successfully!")


if __name__ == "__main__":
    setup_directories()
