import asyncio
import json
import logging

logger = logging.getLogger(__name__)

async def run_agy_prompt(prompt: str, model: str = None, output_format: str = "json", files: list[str] = None):
    """
    Safely executes the `agy` CLI using asyncio subprocess to avoid blocking.
    """
    cmd = [
        "agy",
        "--print", prompt,
        "--output-format", output_format,
        "--dangerously-skip-permissions"
    ]
    
    if model:
        cmd.extend(["--model", model])
        
    if files:
        for f in files:
            # We can pass files by injecting their paths into the prompt, 
            # or if `agy` supports --add-dir, we could use that.
            # Assuming we inject them in the prompt for context:
            pass # We will handle file prompt formatting at the caller level

    logger.info(f"Executing AGY command: {' '.join(cmd)}")
    
    # Run the subprocess
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        logger.error(f"AGY Error: {error_msg}")
        raise RuntimeError(f"AGY CLI execution failed: {error_msg}")
        
    output_str = stdout.decode().strip()
    
    # Try to parse JSON output to ensure it's valid
    try:
        # AGY might print some extra logs, we'll try to find the first '{' and last '}'
        start_idx = output_str.find('{')
        end_idx = output_str.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            json_str = output_str[start_idx:end_idx+1]
            return json.loads(json_str)
        else:
            # Fallback
            return json.loads(output_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AGY JSON output: {output_str}")
        # If we asked for json but didn't get it, wrap it in a fallback JSON
        return {"text": output_str}

