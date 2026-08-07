import os
import tempfile
import base64
import uuid

class TempFileManager:
    """
    Context manager to handle temporary files for a single request.
    It ensures files are deleted when the request is done.
    """
    def __init__(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agy_wrapper_")
        self.files = []
        
    def add_base64_file(self, b64_data: str, ext: str = ".txt") -> str:
        """
        Decodes base64 data, saves it to a temp file, and returns the absolute path.
        """
        # some base64 strings come with data URI scheme e.g. data:image/png;base64,...
        if b64_data.startswith("data:"):
            parts = b64_data.split(",")
            if len(parts) == 2:
                b64_data = parts[1]
                
        file_path = os.path.join(self.temp_dir.name, f"file_{uuid.uuid4().hex}{ext}")
        try:
            decoded = base64.b64decode(b64_data)
            with open(file_path, "wb") as f:
                f.write(decoded)
            self.files.append(file_path)
            return file_path
        except Exception as e:
            raise ValueError(f"Failed to decode base64 file: {e}")
            
    def cleanup(self):
        self.temp_dir.cleanup()
