#!/usr/bin/env python3
"""
批量测试所有标准工具 -  smoke test
"""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))

from tools import registry, execute_tool_call
import asyncio
from tools.executor import ToolExecutor, ToolUse

def test_registry():
    """测试注册表"""
    print("="*60)
    print("TEST 1: Registry Integrity")
    print("="*60)
    tools = registry.list_tools()
    print(f"Total tools registered: {len(tools)}")

    # 按分类统计
    categories = {}
    for t in tools:
        cat = t['category']
        categories[cat] = categories.get(cat, 0) + 1

    print("\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat:20s}: {count}")

    # 检查必需字段
    missing = []
    for t in tools:
        if not t.get('inputSchema'):
            missing.append(t['name'])
    if missing:
        print(f"\n⚠️  Missing schema: {', '.join(missing)}")
    else:
        print("\n✅ All tools have valid inputSchema")

    return len(tools) > 0

def test_sync_calls():
    """测试同步调用（简单）"""
    print("\n" + "="*60)
    print("TEST 2: Synchronous Execute")
    print("="*60)

    tests = [
        ("file_write", {
            "file": "test_sync_output.txt",
            "content": "Sync call test ✅"
        }),
        ("web_search", {
            "query": "OpenClaw AI",
            "count": 1
        }),
        ("memory_write", {
            "content": "Test memory write from tools test suite"
        }),
    ]

    passed = 0
    for tool_name, args in tests:
        print(f"\n→ {tool_name}...")
        try:
            result = execute_tool_call(tool_name, args, auto_confirm=True)
            if result['status'] == 'success':
                print(f"  ✅ success (attempt {result.get('attempt', 1)})")
                passed += 1
            else:
                print(f"  ❌ failed: {result.get('error')}")
                if result.get('error') == 'Requires confirmation':
                    print("    (Fix: add auto_confirm=True)")
        except Exception as e:
            print(f"  ❌ exception: {e}")

    print(f"\nSync tests: {passed}/{len(tests)} passed")
    return passed == len(tests)

def test_async_batch():
    """测试异步批量并行"""
    print("\n" + "="*60)
    print("TEST 3: Async Batch Execution")
    print("="*60)

    async def run():
        executor = ToolExecutor(auto_confirm=True, max_retries=1)
        tasks = [
            ToolUse("file_write", {
                "file": f"test_batch_{i}.txt",
                "content": f"Batch test {i}"
            }, id=str(i))
            for i in range(5)
        ]
        results = await executor.execute_batch(tasks)
        return results

    try:
        results = asyncio.run(run())
        success_count = sum(1 for r in results if r.status == "success")
        print(f"\nBatch results: {success_count}/{len(results)} succeeded")
        for r in results:
            if r.status != "success":
                print(f"  ❌ {r.tool_name}: {r.error}")
            else:
                attempts = r.metadata.get('attempt', 1)
                print(f"  ✅ {r.tool_name} (attempt {attempts})")
        return success_count == len(results)
    except Exception as e:
        print(f"❌ Batch execution failed: {e}")
        return False

def test_error_classification():
    """测试错误分类逻辑（模拟）"""
    print("\n" + "="*60)
    print("TEST 4: Error Classification")
    print("="*60)

    from tools.executor import ToolExecutor
    executor = ToolExecutor()

    test_cases = [
        ("timeout after 30s", "NETWORK"),
        ("ConnectionError", "NETWORK"),
        ("429 Too Many Requests", "RATE_LIMIT"),
        ("quota exceeded", "RATE_LIMIT"),
        ("Service Unavailable", "SERVICE"),
        ("Invalid input", "FATAL"),
        ("File not found", "FATAL"),
    ]

    passed = 0
    for error_msg, expected in test_cases:
        class MockError(Exception):
            def __str__(self):
                return error_msg
        category = executor._classify_error(MockError())
        status = "✅" if category == expected else "❌"
        print(f"{status} '{error_msg}' → {category} (expected {expected})")
        if category == expected:
            passed += 1

    print(f"\nClassification: {passed}/{len(test_cases)} correct")
    return passed == len(test_cases)

def test_json_schema():
    """测试 JSON Schema 有效性"""
    print("\n" + "="*60)
    print("TEST 5: JSON Schema Generation")
    print("="*60)

    import json
    tools = registry.list_tools()
    invalid = []

    for t in tools:
        try:
            # 验证 Schema 可序列化
            json.dumps(t)
            # 检查必需字段
            assert 'name' in t
            assert 'description' in t
            assert 'inputSchema' in t
            schema = t['inputSchema']
            assert 'type' in schema
            assert schema['type'] == 'object'
            assert 'properties' in schema
        except Exception as e:
            invalid.append((t['name'], str(e)))

    if invalid:
        print("❌ Invalid schemas:")
        for name, err in invalid:
            print(f"  - {name}: {err}")
        return False
    else:
        print(f"✅ All {len(tools)} tool schemas are valid JSON")
        return True

def main():
    print("\n🧪 OpenClaw Tools - Comprehensive Test Suite\n")

    results = {
        "registry": test_registry(),
        "sync": test_sync_calls(),
        "async": test_async_batch(),
        "errors": test_error_classification(),
        "schema": test_json_schema(),
    }

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:20s}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All tests passed! Tool system is production-ready.")
    else:
        print("\n⚠️  Some tests failed. Check output above.")

    # 清理测试文件
    print("\n🧹 Cleaning up test files...")
    test_files = list(Path('.').glob('test_*.txt'))
    for f in test_files:
        f.unlink(missing_ok=True)
    print(f"   Removed {len(test_files)} test files")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
