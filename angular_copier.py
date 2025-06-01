import os
import shutil
from dotenv import load_dotenv
from pathlib import Path
#from collections import defaultdict # Needed for building the tree structure

class AngularProjectCopier:
  # Files and paths to be copied (relative to repository root)
  # Can include files from any location in the repository
  CONFIG_FILES = [
    'angular.json',          # Files at repository root
    'package.json',
    'tsconfig.json',
    'tsconfig.app.json',
    'tsconfig.spec.json',
    'ngsw-config.json',
    'README.md',
    'backend_mockup.py',
    '.browserslistrc',
    'karma.conf.js',
    'src/manifest.webmanifest',  # Files in subdirectories
    'src/index.html',
    'src/main.ts',
    'src/polyfills.ts',
    'src/test.ts',
    '.github/workflows/main.yml',
    '.github/workflows/docker-build.yml',
    'docker/docker-compose.yml',
    'docker/Dockerfile',
    'docker/nginx.conf',
    'docker/README.md',
    '.dockerignore',
    'requirements.txt'
    # Add any other files you want to copy (use relative paths)
  ]

  # File extensions to copy from the project
  CODE_EXTENSIONS = {'.ts', '.html', '.scss', '.css', '.js', '.json', '.svg'}

  # Directories to exclude
  EXCLUDE_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.idea', '.angular',
                  'node_modules', 'dist', 'coverage', '.vscode', 'e2e'}

  # Specific files to exclude (even if they match extension criteria)
  # These files will be skipped during copying, regardless of their extension
  EXCLUDE_FILES = {
    'package-lock.json',     # Large file with dependency lock info
    'yarn.lock',             # Alternative package manager lock file
    '.gitignore',            # Version control config
    '.editorconfig',         # Editor config
    'tslint.json',           # Deprecated linter config
    '.eslintrc.json',        # Linter config
    '.prettierrc.json',      # Code formatter config
    'favicon.ico',           # Binary file
    # Add any other specific files you want to exclude
  }

  # --- New attribute ---
  STRUCTURE_FILENAME = "original_project_structure.txt"

  def __init__(self, repo_root: str, src_path: str, dest_path: str):
    self.repo_root = Path(repo_root).resolve() # Use absolute path for robustness
    self.source_path = Path(src_path)
    # Ensure source_path is relative to repo_root if it's inside, or handle absolute paths
    if not self.source_path.is_absolute():
      self.source_path = (self.repo_root / self.source_path).resolve()
    else:
      self.source_path = self.source_path.resolve()

    self.dest_path = Path(dest_path).resolve()
    self.copied_files_relative_paths = set() # Use a set to avoid duplicates automatically
    self.excluded_files_count = 0  # Track number of excluded files

  def copy_project(self):
    """
    Main method to copy the Angular project and generate structure file.
    """
    print(f"Copying Angular project from {self.source_path} to {self.dest_path}")
    print(f"Repository root considered: {self.repo_root}")

    # Reset collected paths for this run
    self.copied_files_relative_paths = set()
    self.excluded_files_count = 0

    # Create destination directory if it doesn't exist
    self.dest_path.mkdir(parents=True, exist_ok=True)

    # Copy configuration files
    self._copy_config_files()

    # Copy Angular source files from the specified src_path
    self._copy_source_files()

    # --- New step: Generate structure file ---
    self._generate_structure_file()

    print(f"\nProject copy completed! Files are in: {self.dest_path}")
    print(f"Original structure explanation saved to: {self.dest_path / self.STRUCTURE_FILENAME}")
    if self.excluded_files_count > 0:
      print(f"Note: {self.excluded_files_count} files were excluded based on EXCLUDE_FILES list")

  def _copy_config_files(self):
    """
    Copy files specified in CONFIG_FILES from anywhere in the repository.
    Paths in CONFIG_FILES should be relative to the repository root.
    """
    print("\n--- Copying specified files ---")
    copied_count = 0
    for config_file_rel_str in self.CONFIG_FILES:
      config_file_rel = Path(config_file_rel_str)
      source_file = self.repo_root / config_file_rel

      # Check if the file is in the exclude list
      if source_file.name in self.EXCLUDE_FILES:
        print(f"Skipping excluded file from CONFIG_FILES: {config_file_rel_str}")
        self.excluded_files_count += 1
        continue

      if source_file.exists() and source_file.is_file():
        # Create a flattened filename for the destination
        # Use '_' instead of '.' for joining parts to avoid confusion with extension
        flat_filename_parts = list(config_file_rel.parts)
        # Keep the original suffix
        original_suffix = config_file_rel.suffix
        flat_filename_base = "_".join(flat_filename_parts).replace(original_suffix, '')
        flat_filename = flat_filename_base + original_suffix

        dest_file = self.dest_path / flat_filename

        print(f"Copying '{config_file_rel_str}' to '{flat_filename}'")
        try:
          shutil.copy2(source_file, dest_file)
          # Store the relative path from the repo root
          self.copied_files_relative_paths.add(config_file_rel_str)
          copied_count += 1
        except Exception as e:
          print(f"Error copying {source_file} to {dest_file}: {e}")

      else:
        print(f"Warning: File not found or is not a file: {config_file_rel_str} (looked in {source_file})")
    print(f"Finished copying specified files. Copied {copied_count} file(s).")

  def _copy_source_files(self):
    """
    Copy all relevant source files from self.source_path into a flat structure.
    """
    print(f"\n--- Copying source files (extensions: {self.CODE_EXTENSIONS}) from {self.source_path} ---")
    if not self.source_path.exists() or not self.source_path.is_dir():
      print(f"Warning: Source directory '{self.source_path}' not found or is not a directory. Skipping source file copy.")
      return

    copied_count = 0
    # Walk through the source directory
    for root, dirs, files in os.walk(self.source_path, topdown=True):
      # Modify dirs in-place to skip excluded directories
      dirs[:] = [d for d in dirs if d not in self.EXCLUDE_DIRS and Path(root, d) not in self.EXCLUDE_DIRS] # Check full path too

      current_dir = Path(root)

      # Check if the current directory itself should be excluded (relative to repo_root)
      try:
        current_dir_rel_to_repo = current_dir.relative_to(self.repo_root)
        if any(part in self.EXCLUDE_DIRS for part in current_dir_rel_to_repo.parts):
          # print(f"Skipping excluded directory: {current_dir_rel_to_repo}") # Optional debug
          continue
      except ValueError:
        # This happens if current_dir is not inside repo_root, should not occur with resolve()
        print(f"Warning: Could not make path relative to repo root: {current_dir}")
        continue

      # Copy files with matching extensions
      for file in files:
        file_path = current_dir / file

        # Ensure it's not in an excluded dir (redundant check, but safe)
        if any(part in self.EXCLUDE_DIRS for part in file_path.relative_to(self.repo_root).parts):
          continue

        # Check if file is explicitly excluded
        if file in self.EXCLUDE_FILES:
          rel_path = file_path.relative_to(self.repo_root)
          print(f"Skipping excluded file: {rel_path}")
          self.excluded_files_count += 1
          continue

        # Check if file should be copied (by extension or if it's a special Angular file)
        should_copy = (file_path.suffix in self.CODE_EXTENSIONS or
                       file in ['.angular-cli.json', '.browserslistrc'])

        if should_copy:
          # Create a unique filename by joining the relative path parts (relative to repo root)
          rel_path_from_repo = file_path.relative_to(self.repo_root)

          # Use '_' instead of '.' for joining parts
          unique_filename_base = "_".join(rel_path_from_repo.parts).replace(rel_path_from_repo.suffix, '')
          unique_filename = unique_filename_base + rel_path_from_repo.suffix

          dest_file = self.dest_path / unique_filename

          print(f"Copying '{rel_path_from_repo}' to '{unique_filename}'")
          try:
            shutil.copy2(file_path, dest_file)
            # Store the relative path from the repo root
            self.copied_files_relative_paths.add(str(file_path.relative_to(self.repo_root)))
            copied_count += 1
          except Exception as e:
            print(f"Error copying {file_path} to {dest_file}: {e}")

    print(f"Finished copying source files. Copied {copied_count} file(s).")

  # --- New Method ---
  def _generate_structure_file(self):
    """
    Generates a text file describing the original project structure
    based on the copied files.
    """
    print(f"\n--- Generating structure file: {self.STRUCTURE_FILENAME} ---")
    structure_file_path = self.dest_path / self.STRUCTURE_FILENAME

    if not self.copied_files_relative_paths:
      print("No files were copied, skipping structure file generation.")
      return

    # Sort paths for consistent output
    sorted_paths = sorted(list(self.copied_files_relative_paths))

    # Build a tree structure (dictionary based)
    tree = {}
    for path_str in sorted_paths:
      path_parts = Path(path_str).parts
      node = tree
      for i, part in enumerate(path_parts):
        is_last_part = (i == len(path_parts) - 1)
        if is_last_part:
          # Mark as file (using None, or could use a special marker)
          node[part] = node.get(part) # Don't overwrite if dir exists with same name
          if node[part] is None: # Only mark if not already a dir
            node[part] = 'FILE'
        else:
          # Ensure dictionary exists for directory part
          node = node.setdefault(part, {})

    # Function to recursively format the tree
    def format_tree(node, indent=""):
      lines = []
      # Sort items: directories first, then files
      items = sorted(node.items(), key=lambda item: (0, item[0]) if isinstance(item[1], dict) else (1, item[0]))

      for name, value in items:
        prefix = "|-- "
        connector = "|   "
        if items.index((name, value)) == len(items) - 1: # Last item uses a different connector
          prefix = "└── "
          connector = "    "

        if isinstance(value, dict): # It's a directory
          lines.append(f"{indent}{prefix}{name}/")
          lines.extend(format_tree(value, indent + connector))
        elif value == 'FILE': # It's a file
          lines.append(f"{indent}{prefix}{name}")
        # Else: Could be a file that has the same name as a directory handled earlier, ignore.
      return lines

    try:
      with open(structure_file_path, 'w', encoding='utf-8') as f:
        f.write(f"Original Angular Project Structure (based on copied files relative to {self.repo_root.name}):\n")
        f.write(f"{self.repo_root.name}/\n") # Add the root directory name

        # Generate the tree starting from the root structure
        structure_lines = format_tree(tree, indent="    ") # Start with indentation for root content

        for line in structure_lines:
          f.write(line + '\n')
      print(f"Successfully wrote structure to {structure_file_path}")
    except IOError as e:
      print(f"Error writing structure file: {e}")
    except Exception as e:
      print(f"An unexpected error occurred during structure file generation: {e}")


# --- Main execution part ---
if __name__ == "__main__":
  # Load environment variables from .env file in the script's directory
  load_dotenv()

  # Get the script's directory (assuming it's the repository root for this example)
  script_dir = Path(__file__).parent.resolve()
  repo_root_path = script_dir # Modify if script is not at repo root

  # Define source path for recursive search (relative to repo root)
  # For Angular projects, typically the entire project structure matters
  src_code_path = '.' # Start from repo root to get all Angular files

  # Get the destination path from env var or use a default relative to script dir
  copy_target_path_str = os.getenv('COPY_PATH', 'output_copy') # Default to './output_copy'
  dest_copy_path = repo_root_path / copy_target_path_str / 'extracted_angular_project_files'

  print("--- Configuration ---")
  print(f"Repository Root: {repo_root_path}")
  print(f"Source Code Dir: {repo_root_path / src_code_path}")
  print(f"Destination Dir: {dest_copy_path}")
  print("---------------------\n")

  # Create and run the copier
  try:
    # Ensure repo_root and src_path are passed correctly
    copier = AngularProjectCopier(repo_root=str(repo_root_path),
                                  src_path=str(repo_root_path / src_code_path), # Pass absolute path to init
                                  dest_path=str(dest_copy_path))
    copier.copy_project()
  except Exception as e:
    print(f"\n--- An error occurred during the process ---")
    import traceback
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Message: {str(e)}")
    print("Traceback:")
    traceback.print_exc()
    print("--------------------------------------------")
