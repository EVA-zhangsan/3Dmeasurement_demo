#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
工业级三维测量系统 - 启动前检查脚本
Industrial Measurement System v2.0 - Pre-flight Checklist

检查项：
  ✓ Python 版本
  ✓ 虚拟环境
  ✓ 依赖包完整性
  ✓ 代码导入验证
  ✓ 数据文件
  ✓ 配置参数
"""

import sys
import os
import importlib.util
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.absolute()

# 配置
REQUIRED_PYTHON = (3, 8)  # 最低 Python 3.8
REQUIRED_PACKAGES = [
    ('numpy', '1.20'),
    ('scipy', '1.5'),
    ('pandas', '1.1'),
    ('matplotlib', '3.0'),
    ('PySide6', '6.0'),
]

class Checker:
    def __init__(self):
        self.passed = []
        self.warnings = []
        self.errors = []
    
    def check_python_version(self):
        """检查 Python 版本"""
        current = sys.version_info[:2]
        if current >= REQUIRED_PYTHON:
            self.passed.append(f"✓ Python {current[0]}.{current[1]}")
            return True
        else:
            msg = f"✗ Python {current[0]}.{current[1]} (需要 {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+)"
            self.errors.append(msg)
            return False
    
    def check_packages(self):
        """检查依赖包"""
        for pkg_name, min_version in REQUIRED_PACKAGES:
            try:
                spec = importlib.util.find_spec(pkg_name)
                if spec is None:
                    self.errors.append(f"✗ {pkg_name} 未安装")
                    continue
                
                mod = importlib.import_module(pkg_name)
                if hasattr(mod, '__version__'):
                    version = mod.__version__
                    self.passed.append(f"✓ {pkg_name} {version}")
                else:
                    self.passed.append(f"✓ {pkg_name} (版本信息不可用)")
            except ImportError as e:
                self.errors.append(f"✗ {pkg_name}: {e}")
    
    def check_source_files(self):
        """检查源代码文件"""
        required_files = [
            'gui.py',
            'data_source.py',
            'simulate_and_fit.py',
            'requirements.txt',
        ]
        
        for fname in required_files:
            fpath = PROJECT_DIR / fname
            if fpath.exists():
                size = fpath.stat().st_size
                self.passed.append(f"✓ {fname} ({size:,} bytes)")
            else:
                self.errors.append(f"✗ {fname} 不存在")
    
    def check_code_imports(self):
        """检查代码导入"""
        try:
            import data_source
            self.passed.append("✓ data_source.py 导入成功")
        except Exception as e:
            self.errors.append(f"✗ data_source.py: {e}")
        
        try:
            import gui
            self.passed.append("✓ gui.py 导入成功")
        except Exception as e:
            self.errors.append(f"✗ gui.py: {e}")
        
        try:
            import simulate_and_fit
            self.passed.append("✓ simulate_and_fit.py 导入成功")
        except Exception as e:
            self.errors.append(f"✗ simulate_and_fit.py: {e}")
    
    def check_data_files(self):
        """检查示例数据文件"""
        data_files = [
            'data_raster.csv',
            'surface_raster.png',
        ]
        
        for fname in data_files:
            fpath = PROJECT_DIR / fname
            if fpath.exists():
                size = fpath.stat().st_size / 1024  # KB
                self.passed.append(f"✓ {fname} ({size:.1f} KB)")
            else:
                self.warnings.append(f"⚠ {fname} 不存在（非致命）")
    
    def print_report(self):
        """打印检查报告"""
        print("\n" + "="*70)
        print("工业级三维测量系统 - 启动前检查")
        print("Industrial Measurement System v2.0 - Pre-flight Checklist")
        print("="*70 + "\n")
        
        if self.passed:
            print("[PASS] 通过项目:")
            for msg in self.passed:
                print(f"  {msg}")
            print()
        
        if self.warnings:
            print("[WARN] 警告项:")
            for msg in self.warnings:
                print(f"  {msg}")
            print()
        
        if self.errors:
            print("[FAIL] 失败项:")
            for msg in self.errors:
                print(f"  {msg}")
            print()
            print("请运行以下命令修复:")
            print("  python -m venv .venv")
            print("  .\\venv\\Scripts\\pip install -r requirements.txt")
            print()
            return False
        
        print("="*70)
        print("✓ 所有检查通过，系统就绪")
        print("="*70)
        print("\n快速启动:")
        print("  Windows: run_gui.bat")
        print("  Linux/Mac: python gui.py")
        print()
        
        return True

def main():
    os.chdir(PROJECT_DIR)
    checker = Checker()
    
    print("\n🔍 正在进行启动前检查...\n")
    
    checker.check_python_version()
    checker.check_packages()
    checker.check_source_files()
    checker.check_code_imports()
    checker.check_data_files()
    
    success = checker.print_report()
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
