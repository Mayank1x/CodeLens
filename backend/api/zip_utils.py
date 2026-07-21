"""
ZIP Utilities

Handles secure extraction of uploaded ZIP files, preventing Zip-Slip vulnerabilities,
and filters files according to the project specifications.
"""

import os
import zipfile
import shutil
import tempfile
from werkzeug.utils import secure_filename
from static_analyzer.analyzer import EXTENSION_TO_LANGUAGE

MAX_BATCH_FILES = 30
MAX_FILE_SIZE_BYTES = 500 * 1024  # 500 KB

IGNORED_DIRECTORIES = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "env", "dist", "build"
}

def is_safe_path(base_dir, target_path):
    """
    Ensure the target_path resolves strictly inside the base_dir.
    This prevents Zip-Slip vulnerabilities where a zip contains entries like `../../etc/passwd`.
    """
    # Resolve absolute paths
    target_abs = os.path.abspath(target_path)
    base_abs = os.path.abspath(base_dir)
    # Check if the target is within the base directory
    return target_abs.startswith(base_abs + os.sep)

def should_process_file(file_path):
    """
    Determine if a file should be analyzed based on filters.
    """
    # 1. Skip ignored directories
    parts = file_path.split(os.sep)
    if any(part in IGNORED_DIRECTORIES for part in parts):
        return False
        
    # 2. Skip unsupported extensions
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in EXTENSION_TO_LANGUAGE:
        return False
        
    return True

def process_zip_upload(zip_file_stream) -> tuple[str, list[dict], int, str]:
    """
    Extracts a zip securely to a temporary directory.
    Returns:
        temp_dir (str): The path to the temp directory (caller must clean it up!)
        files_to_analyze (list of dict): Details of files to process.
        skipped_files_count (int): Number of files skipped due to filters.
        error (str): Any error message (or None if successful).
    """
    temp_dir = tempfile.mkdtemp(prefix="codelens_batch_")
    
    try:
        with zipfile.ZipFile(zip_file_stream, 'r') as z:
            files_to_analyze = []
            skipped_files_count = 0
            
            for zip_info in z.infolist():
                # Skip directories
                if zip_info.is_dir():
                    continue
                    
                # Skip excessively large files immediately without extracting
                if zip_info.file_size > MAX_FILE_SIZE_BYTES:
                    skipped_files_count += 1
                    continue
                    
                # Filter by name/extension
                if not should_process_file(zip_info.filename):
                    skipped_files_count += 1
                    continue
                
                # Check for zip-slip
                target_path = os.path.join(temp_dir, zip_info.filename)
                if not is_safe_path(temp_dir, target_path):
                    skipped_files_count += 1
                    continue # Skip malicious path
                
                # Extract the file securely
                z.extract(zip_info, temp_dir)
                
                files_to_analyze.append({
                    "relative_path": zip_info.filename,
                    "absolute_path": target_path,
                    "language": EXTENSION_TO_LANGUAGE[os.path.splitext(zip_info.filename)[1].lower()]
                })
                
                # Cap the batch size to protect free tier LLM limits
                if len(files_to_analyze) > MAX_BATCH_FILES:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return None, None, 0, f"Batch exceeds maximum limit of {MAX_BATCH_FILES} files. Please upload a smaller project."
            
            if not files_to_analyze:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None, None, 0, "No supported source files found in the ZIP archive."
                
            return temp_dir, files_to_analyze, skipped_files_count, None
            
    except zipfile.BadZipFile:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None, 0, "Invalid ZIP file."
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None, 0, f"Error processing ZIP: {str(e)}"
