#!/usr/bin/env python3
import sys
import json
import os

def main():
    import os
    # NẾU KHÔNG PHẢI LÀ API GỌI THÌ CHO PHÉP TẤT CẢ
    if os.environ.get("AGY_IS_API_CALL") != "1":
        print(json.dumps({"decision": "allow"}))
        return

    try:
        input_data = sys.stdin.read()
        if not input_data:
            print(json.dumps({"decision": "allow"}))
            return
            
        payload = json.loads(input_data)
        tool_call = payload.get("toolCall", {})
        tool_name = tool_call.get("name")
        args = tool_call.get("args", {})
        
        # 1. Chặn TẤT CẢ các lệnh shell
        if tool_name == "run_command":
            print(json.dumps({
                "decision": "deny",
                "reason": "Security Policy: Executing shell commands (run_command) is strictly prohibited via API."
            }))
            return
            
        # 2. Kiểm soát chặt chẽ việc ghi/sửa file
        elif tool_name in ["write_to_file", "replace_file_content", "multi_replace_file_content"]:
            target_file = args.get("TargetFile", "")
            
            # Allowlist: Chỉ cho phép ghi file vào đúng các thư mục này
            # (Phòng ngừa Path Traversal như /tmp/../../etc/passwd)
            allowed_dirs = [
                os.path.abspath("/tmp/"),
                os.path.abspath("/home/truong/agy2api/scripts/") # Thư mục viết kịch bản
            ]
            
            try:
                abs_target = os.path.abspath(target_file)
                
                is_allowed = False
                for d in allowed_dirs:
                    if abs_target.startswith(d):
                        is_allowed = True
                        break
                        
                if is_allowed:
                    # Đặc biệt cấm ghi đè lên chính file hook này
                    if abs_target == os.path.abspath("/home/truong/agy2api/scripts/safety_gate.py"):
                        print(json.dumps({
                            "decision": "deny",
                            "reason": "Security Policy: Cannot overwrite the safety gate script itself."
                        }))
                        return
                        
                    print(json.dumps({"decision": "allow"}))
                else:
                    print(json.dumps({
                        "decision": "deny",
                        "reason": f"Security Policy: File modification is ONLY allowed in {allowed_dirs}. Target '{abs_target}' is blocked."
                    }))
            except Exception as e:
                print(json.dumps({"decision": "deny", "reason": "Security Policy: Invalid file path format."}))
            return

        # Các tool khác (nếu lọt vào) thì cho phép
        print(json.dumps({"decision": "allow"}))
        
    except Exception as e:
        print(json.dumps({"decision": "allow", "reason": f"Hook error: {str(e)}"}))

if __name__ == "__main__":
    main()
