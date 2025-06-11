import os
import sys
import logging
from pathlib import Path
import importlib
import json
from datetime import datetime
import pytz

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeploymentChecker:
    def __init__(self):
        self.required_files = [
            'main.py',
            'signal_engine.py',
            'market_data.py',
            'telegram_notifier.py',
            'utils.py',
            'requirements.txt',
            'README.md'
        ]
        self.required_dirs = ['logs']
        self.checks_passed = 0
        self.checks_failed = 0

    def check_files_exist(self):
        """Check if all required files exist"""
        logger.info("Checking required files...")
        for file in self.required_files:
            if Path(file).exists():
                logger.info(f"✓ Found {file}")
                self.checks_passed += 1
            else:
                logger.error(f"✗ Missing {file}")
                self.checks_failed += 1

    def check_directories_exist(self):
        """Check if required directories exist"""
        logger.info("\nChecking required directories...")
        for dir_name in self.required_dirs:
            if Path(dir_name).exists():
                logger.info(f"✓ Found directory {dir_name}")
                self.checks_passed += 1
            else:
                logger.error(f"✗ Missing directory {dir_name}")
                self.checks_failed += 1

    def check_imports(self):
        """Check if all required packages can be imported"""
        logger.info("\nChecking package imports...")
        required_packages = [
            'pandas',
            'numpy',
            'requests',
            'python-dotenv',
            'yfinance',
            'pytz',
            'psutil'
        ]
        
        for package in required_packages:
            try:
                importlib.import_module(package.replace('-', '_'))
                logger.info(f"✓ Successfully imported {package}")
                self.checks_passed += 1
            except ImportError as e:
                logger.error(f"✗ Failed to import {package}: {e}")
                self.checks_failed += 1

    def check_env_variables(self):
        """Check if environment variables are set"""
        logger.info("\nChecking environment variables...")
        required_vars = ['BOT_TOKEN', 'CHAT_ID']
        
        for var in required_vars:
            if os.getenv(var):
                logger.info(f"✓ Found environment variable {var}")
                self.checks_passed += 1
            else:
                logger.error(f"✗ Missing environment variable {var}")
                self.checks_failed += 1

    def check_timezone(self):
        """Check timezone configuration"""
        logger.info("\nChecking timezone configuration...")
        try:
            est_tz = pytz.timezone('US/Eastern')
            current_time = datetime.now(est_tz)
            logger.info(f"✓ Timezone configuration OK (Current EST: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')})")
            self.checks_passed += 1
        except Exception as e:
            logger.error(f"✗ Timezone configuration error: {e}")
            self.checks_failed += 1

    def check_write_permissions(self):
        """Check write permissions for logs and data"""
        logger.info("\nChecking write permissions...")
        test_paths = ['logs/test.log', 'signals.json']
        
        for path in test_paths:
            try:
                Path(path).parent.mkdir(exist_ok=True)
                with open(path, 'w') as f:
                    f.write('test')
                os.remove(path)
                logger.info(f"✓ Write permission OK for {path}")
                self.checks_passed += 1
            except Exception as e:
                logger.error(f"✗ Write permission error for {path}: {e}")
                self.checks_failed += 1

    def run_all_checks(self):
        """Run all deployment checks"""
        logger.info("Starting deployment checks...\n")
        
        self.check_files_exist()
        self.check_directories_exist()
        self.check_imports()
        self.check_env_variables()
        self.check_timezone()
        self.check_write_permissions()
        
        logger.info("\nDeployment Check Summary:")
        logger.info(f"Passed: {self.checks_passed}")
        logger.info(f"Failed: {self.checks_failed}")
        logger.info(f"Total: {self.checks_passed + self.checks_failed}")
        
        if self.checks_failed > 0:
            logger.error("\n⚠️ Some checks failed. Please fix the issues before deploying.")
            return False
        else:
            logger.info("\n✅ All checks passed! Ready for deployment.")
            return True

if __name__ == '__main__':
    checker = DeploymentChecker()
    if not checker.run_all_checks():
        sys.exit(1) 