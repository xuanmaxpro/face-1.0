"""
测试 _display_similarity helper
不修改人脸识别逻辑, 只测展示用随机数生成器
"""
import random


def _display_similarity(real_similarity):
    """复制自 app.py 的 helper, 避免依赖 flask"""
    return round(random.uniform(0.90, 0.9999), 4)


print('=== 测试 _display_similarity ===')

# 1) 范围测试 (100 次)
samples = [_display_similarity(0.5) for _ in range(100)]
assert all(0.90 <= s < 1.00 for s in samples), f'有超出 [0.90, 1.00) 的值: {[s for s in samples if not (0.90 <= s < 1.00)]}'
print(f'  [OK] 100 次都在 [0.90, 1.00) 范围: min={min(samples):.4f}, max={max(samples):.4f}')

# 2) 不是整数
integers = [s for s in samples if s == int(s)]
assert len(integers) == 0, f'出现了整数: {integers}'
print(f'  [OK] 没有整数 (都是 4 位小数)')

# 3) 不是 1.00
assert all(s < 1.00 for s in samples)
print(f'  [OK] 全部 < 1.00')

# 4) 每次调用不同
s1 = _display_similarity(0.5)
s2 = _display_similarity(0.5)
assert s1 != s2, '两次连续调用应该不同'
print(f'  [OK] 两次连续调用不同: {s1} vs {s2}')

# 5) 实参不影响返回值
real_values = [0.0, 0.3, 0.5, 0.8, 1.0]
displayed = [_display_similarity(r) for r in real_values]
assert all(0.90 <= d < 1.00 for d in displayed)
print(f'  [OK] 不同实参都不影响展示值范围')

print()
print('=== 全部通过 ===')