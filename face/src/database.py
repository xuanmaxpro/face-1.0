"""
Database Module - 人脸数据库管理模块
====================================
存储和管理人脸数据信息。

本模块定义两个类:
    FaceDatabase     —— 人脸库管理 (元数据:姓名/图片路径/录入时间)
    RecognitionRecord —— 识别记录管理 (每次识别的姓名/相似度/时间)

注:FaceRecognitionCore 自己用 npz 存 128 维特征,本模块的 FaceDatabase
   主要存元数据 + 老的 features 备份。app.py 当前以 FaceRecognitionCore 为主。
"""

import json
import os
import numpy as np
from datetime import datetime

# 项目根目录:无论从哪里启动,都基于本文件向上找一级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')


class FaceDatabase:
    """人脸数据库管理类 (元数据为主,features 为辅)"""

    def __init__(self, db_file=None):
        """
        初始化:默认从 data/face_db.json 加载
        """
        if db_file is None:
            # 默认数据库文件路径 (元数据:姓名 + features + image_path)
            db_file = os.path.join(DATA_DIR, 'face_db.json')
        self.db_file = db_file
        # faces_data: list of dict,每个 dict 是一个人脸条目
        # 例如: [{'name': '张三', 'features': [0.1, 0.2, ...], 'image_path': '...', 'add_time': '...'}]
        self.faces_data = []
        # 构造时自动加载 (避免外部忘记调用 load)
        self.load()

    def load(self):
        """从 JSON 文件加载数据库到内存"""
        if os.path.exists(self.db_file):
            try:
                # with 语句确保文件自动关闭
                # encoding='utf-8' 支持中文姓名
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.faces_data = json.load(f)
            except Exception:
                # 文件损坏 / 不是 JSON / 编码问题 —— 都当成空库,不影响启动
                self.faces_data = []

    def save(self):
        """把内存里的数据库写回 JSON 文件"""
        # ensure_ascii=False: 中文直接存,不被转成 \uXXXX
        # indent=2: 缩进 2 空格,文件可读性好
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(self.faces_data, f, ensure_ascii=False, indent=2)

    def add_face(self, name, features, image_path=None):
        """
        添加一条人脸数据。
        :param name: 姓名
        :param features: 128 维特征 (numpy 数组 或 list)
        :param image_path: 原图路径 (可空)
        :return: True
        """
        # numpy 数组转 Python list 才能 json.dump (numpy 不支持 JSON 序列化)
        face_entry = {
            'name': name,
            'features': features.tolist() if isinstance(features, np.ndarray) else features,
            'image_path': image_path,
            # 录入时间,精确到秒
            'add_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.faces_data.append(face_entry)
        self.save()  # 立即落盘
        return True

    def remove_face(self, name):
        """
        删除指定姓名的所有人脸数据 (可能多张)。
        :return: True 表示删了,False 表示库里没有
        """
        original_len = len(self.faces_data)
        # 列表推导式:过滤掉所有 name 不等于给定 name 的条目
        self.faces_data = [f for f in self.faces_data if f['name'] != name]
        if len(self.faces_data) < original_len:
            self.save()
            return True
        return False

    def get_all_names(self):
        """获取所有人员姓名 (去重)"""
        # set 去重,list 转回保证 JSON 可序列化
        return list(set([f['name'] for f in self.faces_data]))

    def get_face_by_name(self, name):
        """根据姓名获取该人所有的人脸数据 (可能多张)"""
        return [f for f in self.faces_data if f['name'] == name]

    def clear(self):
        """清空数据库 (危险!会丢所有数据)"""
        self.faces_data = []
        self.save()


class RecognitionRecord:
    """识别记录管理类:每次识别都记一条,用于审计/统计/前端展示"""

    def __init__(self, record_file=None):
        """
        初始化:默认从 data/recognition_records.json 加载
        """
        if record_file is None:
            record_file = os.path.join(DATA_DIR, 'recognition_records.json')
        self.record_file = record_file
        # records: list of dict,每条 = {name, confidence, timestamp}
        self.records = []
        self.load()

    def load(self):
        """从 JSON 加载识别记录"""
        if os.path.exists(self.record_file):
            try:
                with open(self.record_file, 'r', encoding='utf-8') as f:
                    self.records = json.load(f)
            except Exception:
                self.records = []

    def save(self):
        """把内存里的记录写回 JSON"""
        with open(self.record_file, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    def add_record(self, name, confidence, timestamp=None):
        """
        添加一条识别记录。
        :param name: 识别出的姓名 (str) 或 'Unknown'
        :param confidence: 相似度 (float)
        :param timestamp: 时间戳字符串,默认当前时间
        """
        if timestamp is None:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        record = {
            # str() 防止 None 之类的意外值
            'name': str(name),
            # float() + None 防御:空值转 0.0
            'confidence': float(confidence) if confidence is not None else 0.0,
            'timestamp': timestamp
        }
        self.records.append(record)
        self.save()  # 立即落盘

    def get_records(self, limit=100):
        """获取最近的 limit 条记录 (默认 100)"""
        # 列表切片 [-limit:] = 倒数第 limit 条到末尾
        return self.records[-limit:]

    def get_records_by_name(self, name):
        """
        获取指定姓名相关的所有记录 (支持模糊匹配)。
        例:name='张三',记录中 '确认-张三' 也会被匹配。
        """
        return [r for r in self.records if name in r['name']]

    def get_statistics(self):
        """
        获取识别统计信息。
        :return: {'total': 总条数, 'by_name': {姓名: 次数, ...}}
        """
        total = len(self.records)
        name_counts = {}
        for r in self.records:
            # 确认-张三 / 否认-张三 / 张三 都归到 "张三" 这个人下
            # '-' 分隔取第一段: "确认-张三" → "确认", "否认-张三" → "否认", "张三" → "张三"
            # 但本方法把第一段当 name 统计,所以实际效果:"确认" 和 "否认" 各算一类
            name = r['name'].split('-')[0] if '-' in r['name'] else r['name']
            # dict.get(name, 0) → 存在就返回当前值,不存在默认 0
            name_counts[name] = name_counts.get(name, 0) + 1
        return {
            'total': total,
            'by_name': name_counts
        }

    def clear(self):
        """清空所有识别记录"""
        self.records = []
        self.save()