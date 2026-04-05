#!/usr/bin/env python3
"""
测试 openclaw-updater 插件工具
"""
import subprocess
import json

def test_plugin_tools():
    print("Testing openclaw-updater plugin tools...\n")

    # 尝试调用 check_openclaw_update 工具
    print("1. Checking if tool 'check_openclaw_update' is available...")
    try:
        result = subprocess.run(
            ['openclaw', 'tool', 'call', 'check_openclaw_update'],
            capture_output=True, text=True, timeout=30
        )
        print(f"   Exit code: {result.returncode}")
        print(f"   Output: {result.stdout[:500]}")
        if result.stderr:
            print(f"   Stderr: {result.stderr[:500]}")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n2. Checking 'update' command...")
    try:
        result = subprocess.run(
            ['openclaw', 'update', '--dry-run'],  # 假设有 dry-run 选项
            capture_output=True, text=True, timeout=30
        )
        print(f"   Exit code: {result.returncode}")
        print(f"   Output: {result.stdout[:500]}")
    except FileNotFoundError:
        print("   'openclaw' command not found in PATH")
    except Exception as e:
        print(f"   Error: {e}")

if __name__ == "__main__":
    test_plugin_tools()
