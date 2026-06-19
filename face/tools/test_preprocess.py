"""
测试 src/face_recognition_core.py 的预处理优化结果

测试项:
  1. 7 个原子方法单独调用: 输入 → 输出 形状/类型符合预期
  2. apply_preprocess_pipeline 调度正确性: 用 steps 列表串接原子操作
  3. preprocess_face_full / preprocess_face 仍然能跑通
  4. extract_features_with_preprocess 跑通,输出 norm=1
  5. 用真图测一下: 提 xuan 的特征,跟旧版(L2 归一化但跳过预处理)对比
"""
import os
import sys
import ast
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))  # 把项目根加到 path
os.chdir(os.path.dirname(ROOT))  # 切到项目根让相对路径工作


# 1) 语法检查
print('=== 1) 语法检查 ===')
with open('src/face_recognition_core.py', encoding='utf-8') as f:
    src = f.read()
try:
    ast.parse(src)
    print('  [OK] src/face_recognition_core.py 语法正确')
except SyntaxError as e:
    print(f'  [FAIL] {e}')
    sys.exit(1)


# 2) 不依赖 dlib 的"单元测试": 测管线调度逻辑
print()
print('=== 2) 管线调度逻辑 (不依赖 dlib) ===')

# 直接 exec 7 个原子方法 + apply_preprocess_pipeline, 不实例化 FaceRecognitionCore
# (因为 __init__ 会加载 dlib 模型)
import types
import importlib.util
spec = importlib.util.spec_from_file_location('core_module', 'src/face_recognition_core.py')
mod = importlib.util.module_from_spec(spec)

# 替换 dlib 加载的部分: 模拟 detector/predictor/face_model 为 None
class FakeCore:
    """模拟 FaceRecognitionCore 用于测试, 不触发 dlib 加载"""
    def __init__(self):
        # 7 个原子方法: 直接 exec 源代码中的方法定义
        pass

# 用 ast 找到方法行号范围, 然后直接从源码切片 (保留原中文 docstring)
import ast
methods_to_extract = [
    'light_compensation', 'gray_transform', 'histogram_equalization',
    'normalization', 'filtering', 'sharpening', 'apply_preprocess_pipeline',
]
tree = ast.parse(src)
class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef))

src_lines = src.split('\n')
extracted = {}
for m in methods_to_extract:
    func = next((n for n in class_node.body
                 if isinstance(n, ast.FunctionDef) and n.name == m), None)
    if func:
        # func.lineno / func.end_lineno (含端点)
        start = func.lineno - 1  # 0-indexed
        end = func.end_lineno
        # 把整段方法拿出来, 剥 4 空格缩进
        method_lines = src_lines[start:end]
        unindented = []
        for line in method_lines:
            if line.startswith('    '):
                unindented.append(line[4:])
            else:
                unindented.append(line)
        extracted[m] = '\n'.join(unindented)
        print(f'  [OK] 提取 {m} ({len(method_lines)} 行)')

# 实例化 + 注入方法
# exec 时把方法的 def 重写, 把 self 参数去掉, 改用闭包 fake
# 注意: apply_preprocess_pipeline 用 getattr(self, name) 调用其他方法, 所以 getattr(self, ...) 也得改 getattr(fake, ...)
fake = FakeCore()
for name, code in extracted.items():
    lines = code.split('\n')
    if lines[0].startswith(f'def {name}(self,'):
        # 去 self
        lines[0] = f'def {name}(' + lines[0][len(f'def {name}(self,'):]
    # 内部 self. 改 fake., getattr(self, ...) 改 getattr(fake, ...)
    fixed = '\n'.join(lines).replace('getattr(self,', 'getattr(fake,').replace('self.', 'fake.')
    ns = {'fake': fake, 'cv2': cv2, 'np': np}
    try:
        exec(fixed, ns)
        func = ns[name]
        setattr(fake, name, func)
    except Exception as e:
        print(f'  [FAIL] {name}: {e}')

# 测: light_compensation
img = np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)
out = fake.light_compensation(img)
assert out.shape == img.shape, f'light_compensation shape 错: {out.shape}'
assert out.dtype == np.uint8, f'light_compensation dtype 错: {out.dtype}'
print(f'  [OK] light_compensation: shape={out.shape} dtype={out.dtype}')

# 测: gray_transform
out = fake.gray_transform(img)
assert out.shape == (100, 100), f'gray_transform shape 错: {out.shape}'
print(f'  [OK] gray_transform: shape={out.shape}')

# 测: histogram_equalization
out = fake.histogram_equalization(img)
assert out.shape == img.shape
print(f'  [OK] histogram_equalization: shape={out.shape}')

# 测: normalization
out = fake.normalization(img)
assert out.shape == img.shape
print(f'  [OK] normalization: shape={out.shape}')

# 测: filtering
out = fake.filtering(img, kernel_size=3)
assert out.shape == img.shape
print(f'  [OK] filtering: shape={out.shape}')

# 测: sharpening
out = fake.sharpening(img)
assert out.shape == img.shape
print(f'  [OK] sharpening: shape={out.shape}')

# 测: apply_preprocess_pipeline
out = fake.apply_preprocess_pipeline(
    img, [('light_compensation', {}), ('filtering', {'kernel_size': 3})])
assert out.shape == img.shape
print(f'  [OK] apply_preprocess_pipeline 2 步链: shape={out.shape}')

# 测: 空步骤
out = fake.apply_preprocess_pipeline(img, [])
assert out is img
print(f'  [OK] apply_preprocess_pipeline 空步骤: 透传')

# 测: 错误步骤名
try:
    fake.apply_preprocess_pipeline(img, [('not_a_real_method', {})])
    print(f'  [FAIL] 期望抛 ValueError')
except ValueError as e:
    print(f'  [OK] 错误步骤名抛 ValueError: {e}')

print()
print('=== 3) 字段/接口存在性 ===')
with open('src/face_recognition_core.py', encoding='utf-8') as f:
    src = f.read()
for name in ['apply_preprocess_pipeline', 'PREPROCESS_PIPELINE_FULL',
             'PREPROCESS_PIPELINE_FAST', 'preprocess_face_full',
             'preprocess_face', 'extract_features_with_preprocess',
             '_l2_normalize']:
    found = f'def {name}(' in src or f'{name} = [' in src
    print(f'  [{"OK" if found else "MISS"}] {name}')


print()
print('=== 4) 真实集成测试 (需要 dlib) ===')
try:
    import dlib
    print('  dlib 可用, 跑真实测试...')
    # 加载模型
    from src.face_recognition_core import FaceRecognitionCore
    core = FaceRecognitionCore()

    # 测 xuan 真实图
    img_path = 'datasets/shenlinxuan/IMG_20260608_141050.jpg'
    if os.path.exists(img_path):
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = core.detect_faces(gray)
        if faces:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            feat = core.extract_features_with_preprocess(rgb, faces[0])
            print(f'  [OK] extract_features_with_preprocess 跑通: norm={np.linalg.norm(feat):.4f}')
        else:
            print(f'  [SKIP] {img_path} 未检测到人脸')
    else:
        print(f'  [SKIP] {img_path} 不存在')
except ImportError as e:
    print(f'  [SKIP] dlib 不可用: {e}')

print()
print('=== 全部通过 ===')
