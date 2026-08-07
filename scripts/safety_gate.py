#!/usr/bin/env python3
import sys
import json
import re

def main():
    try:
        # Read payload from stdin
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"decision": "allow"}))
            return
            
        payload = json.loads(input_data)
        
        # Extract the command line arguments
        tool_call = payload.get("toolCall", {})
        if tool_call.get("name") != "run_command":
            print(json.dumps({"decision": "allow"}))
            return
            
        args = tool_call.get("args", {})
        cmd_line = args.get("CommandLine", "")
        
        # Comprehensive denylist for dangerous commands
        dangerous_patterns = [
            # Block rm with both r and f flags, regardless of order or separation
            r"\brm\s+-(?:[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*)\b",
            r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+-[a-zA-Z]*f[a-zA-Z]*\b",
            r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s+-[a-zA-Z]*r[a-zA-Z]*\b",
            # Block all variations of formatting file systems
            r"\bmkfs(?:\.[\w]+)?\b",
            r"\bfdisk\b",
            # Block recursive overly permissive chmod
            r"\bchmod\s+-R\s+(?:777|ugo\+rwx)\b",
            # Block dd writes to disk devices
            r"\bdd\s+(?:.*?\s+)?of=/dev/[a-zA-Z]+",
            # Block direct shell redirects to raw disk devices
            r">\s*/dev/(?:sda|sdb|nvme)\w*",
            # Block destructive moving to null
            r"\bmv\s+(?:.*?\s+)?/dev/null\b"
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, cmd_line, re.IGNORECASE):
                print(json.dumps({
                    "decision": "deny",
                    "reason": f"Blocked by AGY Wrapper Safety Gate: Matched dangerous pattern '{pattern}'"
                }))
                return
                
        # If no dangerous patterns found, allow
        print(json.dumps({"decision": "allow"}))
        
    except Exception as e:
        # On error parsing or reading, default to allow so we don't break the agent
        # Ideally, we log this somewhere
        print(json.dumps({"decision": "allow", "reason": f"Hook error: {str(e)}"}))

if __name__ == "__main__":
    main()
