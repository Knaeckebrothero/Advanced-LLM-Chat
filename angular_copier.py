import os
import shutil
from pathlib import Path

class AngularProjectCopier:
    # Fixed configuration files that should be copied
    CONFIG_FILES = [
        'angular.json',
        'package.json',
        'tsconfig.json',
        'tsconfig.app.json',
        'tsconfig.spec.json',
        'ngsw-config.json',
        'manifest.webmanifest'
    ]
    
    # File extensions to copy from src directory
    SRC_EXTENSIONS = {'.ts', '.html', '.scss', '.css'}
    
    def __init__(self, source_path: str, dest_path: str):
        self.source_path = Path(source_path)
        self.dest_path = Path(dest_path)
        
    def copy_project(self):
        """Main method to copy the Angular project."""
        print(f"Copying Angular project from {self.source_path} to {self.dest_path}")
        
        # Create destination directory if it doesn't exist
        self.dest_path.mkdir(parents=True, exist_ok=True)
        
        # Copy configuration files
        self._copy_config_files()
        
        # Copy src directory files
        self._copy_src_files()
        
        print("Project copy completed!")

    def _copy_config_files(self):
        """Copy fixed configuration files."""
        print("Copying configuration files...")
        for config_file in self.CONFIG_FILES:
            source_file = self.source_path / config_file
            if source_file.exists():
                dest_file = self.dest_path / config_file
                print(f"Copying {config_file}")
                shutil.copy2(source_file, dest_file)
            else:
                print(f"Warning: Configuration file {config_file} not found")

    def _copy_src_files(self):
        """Copy all relevant files from the src directory into a flat structure."""
        src_dir = self.source_path / 'src'
        if not src_dir.exists():
            print("Error: src directory not found!")
            return

        print("Copying source files...")
        
        # Walk through the src directory
        for root, _, files in os.walk(src_dir):
            current_dir = Path(root)
            
            # Copy files with matching extensions
            for file in files:
                file_path = current_dir / file
                if file_path.suffix in self.SRC_EXTENSIONS:
                    # Create a unique filename by joining the relative path parts
                    rel_path = file_path.relative_to(src_dir)
                    unique_filename = "_".join(rel_path.parts)
                    dest_file = self.dest_path / unique_filename
                    print(f"Copying {rel_path} as {unique_filename}")
                    shutil.copy2(file_path, dest_file)


# Get the script's directory
script_dir = Path(__file__).parent

# Define source and destination paths relative to script location
source_path = script_dir / 'frontend'
dest_path = script_dir / 'resulting_angular_project_files'

# Create and run the copier
try:
    copier = AngularProjectCopier(source_path, dest_path)
    copier.copy_project()
except Exception as e:
    print(f"Error: {str(e)}")
