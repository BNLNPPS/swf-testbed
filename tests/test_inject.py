#!/usr/bin/env python3
"""
Comprehensive test injection script for open dataset processing agent.
Tests various scenarios to validate dataset lifecycle and PanDA submission.
"""

import time
import json
import stomp
import sys
import subprocess
import os
from datetime import datetime


class DatasetTestInjector:
    def __init__(self, host="localhost", port=61616, user=None, password=None):
        self.host = host
        self.port = port
        self.user = user or os.getenv('SWF_MQ_USER', 'your_username')
        self.password = password or os.getenv('SWF_MQ_PASSWORD', 'your_password')
        self.scope = os.getenv('RUCIO_SCOPE', 'user.your_username')
        self.connection = None
        
    def connect(self):
        """Establish connection to ActiveMQ"""
        print(f"Connecting to ActiveMQ at {self.host}:{self.port}...")
        self.connection = stomp.Connection([(self.host, self.port)], heartbeats=(10000, 30000))
        self.connection.connect(self.user, self.password, wait=True, vhost="localhost")
        print("Connected successfully")
        
    def disconnect(self):
        """Close connection"""
        if self.connection:
            self.connection.disconnect()
            print("Disconnected from ActiveMQ")
            
    def send_message(self, message, delay=0.5):
        """Send message with optional delay"""
        if delay > 0:
            time.sleep(delay)
            
        self.connection.send(
            "processing_agent",
            json.dumps(message),
            headers={"content-type": "application/json", "persistent": "true"}
        )
        print(f"-> {message}")
        
    def run_single_file_test(self):
        """Test basic single file dataset workflow"""
        print("\n🧪 TEST 1: Single File Dataset")
        print("=" * 50)
        
        run_id = f"single-{int(time.time())}"
        
        messages = [
            {"msg_type": "run_imminent", "run_id": run_id, "simulation_tick": 0},
            {"msg_type": "start_run", "run_id": run_id, "simulation_tick": 1},
            {"msg_type": "data_ready", "run_id": run_id, "filename": f"{run_id}.stf",
             "file_url": f"file:///tmp/{run_id}.stf", "checksum": "deadbeef",
             "size_bytes": 1024, "processed_by": "daqsim", "simulation_tick": 2},
            {"msg_type": "end_run", "run_id": run_id, "total_files": 1, "simulation_tick": 3}
        ]
        
        for msg in messages:
            self.send_message(msg)
            
        print(f"\nDataset should be: {self.scope}:{run_id}.stf.ds")
        return run_id
        
    def run_multi_file_test(self):
        """Test multi-file dataset workflow"""
        print("\n🧪 TEST 2: Multi-File Dataset")
        print("=" * 50)
        
        run_id = f"multi-{int(time.time())}"
        file_count = 5
        
        # Start sequence
        self.send_message({"msg_type": "run_imminent", "run_id": run_id, "simulation_tick": 0})
        self.send_message({"msg_type": "start_run", "run_id": run_id, "simulation_tick": 1})
        
        # Multiple data files with valid checksums
        for i in range(file_count):
            msg = {
                "msg_type": "data_ready",
                "run_id": run_id,
                "filename": f"{run_id}-{i:03d}.stf",
                "file_url": f"file:///tmp/{run_id}-{i:03d}.stf",
                "checksum": f"{i:08x}",
                "size_bytes": 1024 + i * 256,
                "processed_by": "daqsim",
                "simulation_tick": 2 + i
            }
            self.send_message(msg, delay=0.2)  # Faster for multiple files
            
        # End sequence
        self.send_message({
            "msg_type": "end_run",
            "run_id": run_id,
            "total_files": file_count,
            "simulation_tick": 2 + file_count
        })
        
        print(f"\nDataset should contain {file_count} files: {self.scope}:{run_id}.stf.ds")
        return run_id
        
    def run_timing_stress_test(self):
        """Test rapid message delivery"""
        print("\n🧪 TEST 3: Timing Stress Test")
        print("=" * 50)
        
        run_id = f"stress-{int(time.time())}"
        file_count = 10
        
        # Start sequence
        self.send_message({"msg_type": "run_imminent", "run_id": run_id, "simulation_tick": 0})
        self.send_message({"msg_type": "start_run", "run_id": run_id, "simulation_tick": 1})
        
        # Rapid-fire data messages (no delay) with valid checksums
        print("Sending rapid-fire messages...")
        for i in range(file_count):
            msg = {
                "msg_type": "data_ready",
                "run_id": run_id,
                "filename": f"{run_id}-rapid-{i:03d}.stf",
                "file_url": f"file:///tmp/{run_id}-rapid-{i:03d}.stf",
                "checksum": f"a{i:07x}",
                "size_bytes": 512 + i * 64,
                "processed_by": "daqsim",
                "simulation_tick": 2 + i
            }
            self.send_message(msg, delay=0.1)  # Very fast delivery
            
        # End sequence
        self.send_message({
            "msg_type": "end_run",
            "run_id": run_id,
            "total_files": file_count,
            "simulation_tick": 2 + file_count
        })
        
        print(f"\nStress test dataset: {self.scope}:{run_id}.stf.ds")
        return run_id
        
    def run_error_handling_test(self):
        """Test error conditions and edge cases"""
        print("\n🧪 TEST 4: Error Handling")
        print("=" * 50)
        
        run_id = f"error-{int(time.time())}"
        
        # Start sequence
        self.send_message({"msg_type": "run_imminent", "run_id": run_id, "simulation_tick": 0})
        self.send_message({"msg_type": "start_run", "run_id": run_id, "simulation_tick": 1})
        
        # Test cases with problematic data
        error_cases = [
            # Missing checksum
            {"msg_type": "data_ready", "run_id": run_id, "filename": f"{run_id}-no-checksum.stf",
             "file_url": f"file:///tmp/{run_id}-no-checksum.stf", "checksum": "",
             "size_bytes": 1024, "processed_by": "daqsim", "simulation_tick": 2},
             
            # Null size with valid checksum
            {"msg_type": "data_ready", "run_id": run_id, "filename": f"{run_id}-null-size.stf",
             "file_url": f"file:///tmp/{run_id}-null-size.stf", "checksum": "12345678",
             "size_bytes": None, "processed_by": "daqsim", "simulation_tick": 3},
             
            # Very large file with valid checksum
            {"msg_type": "data_ready", "run_id": run_id, "filename": f"{run_id}-large.stf",
             "file_url": f"file:///tmp/{run_id}-large.stf", "checksum": "abcdef12",
             "size_bytes": 1024*1024*1024, "processed_by": "daqsim", "simulation_tick": 4},
        ]
        
        for msg in error_cases:
            self.send_message(msg, delay=0.3)
            
        # End sequence
        self.send_message({
            "msg_type": "end_run",
            "run_id": run_id,
            "total_files": len(error_cases),
            "simulation_tick": 5
        })
        
        print(f"\nError test dataset: {self.scope}:{run_id}.stf.ds")
        return run_id
        
    def verify_dataset(self, run_id):
        """Verify dataset was created and contains expected files"""
        dataset_name = f"{self.scope}:{run_id}.stf.ds"
        print(f"\nVerifying dataset: {dataset_name}")
        
        try:
            # Check if dataset exists and get metadata
            result = subprocess.run(['rucio', 'get-metadata', dataset_name],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("✓ Dataset exists")
                if 'open' in result.stdout:
                    print(f"  Metadata: {result.stdout.strip()}")
            else:
                print(f"✗ Dataset check failed: {result.stderr.strip()}")
                
            # List dataset contents
            result = subprocess.run(['rucio', 'list-content', dataset_name],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                files = result.stdout.strip().split('\n')
                print(f"✓ Dataset contains {len(files)} files:")
                for f in files[:5]:  # Show first 5
                    print(f"  - {f}")
                if len(files) > 5:
                    print(f"  ... and {len(files) - 5} more")
            else:
                print(f"✗ Content listing failed: {result.stderr.strip()}")
                
        except subprocess.TimeoutExpired:
            print("✗ Rucio command timed out")
        except FileNotFoundError:
            print("✗ Rucio command not found (install rucio-clients)")
            
    def run_all_tests(self):
        """Run complete test suite"""
        print("🚀 Starting Open Dataset Test Suite")
        print("=" * 60)
        
        test_results = {}
        
        try:
            self.connect()
            
            # Run all test scenarios
            test_results['single'] = self.run_single_file_test()
            time.sleep(2)  # Allow processing
            
            test_results['multi'] = self.run_multi_file_test()
            time.sleep(2)
            
            test_results['stress'] = self.run_timing_stress_test()
            time.sleep(2)
            
            test_results['error'] = self.run_error_handling_test()
            
            print("\n⏳ Waiting for processing to complete...")
            time.sleep(5)  # Allow agent to process all messages
            
            # Verification phase
            print("\n🔍 VERIFICATION PHASE")
            print("=" * 60)
            for test_name, run_id in test_results.items():
                print(f"\n--- {test_name.upper()} TEST ---")
                self.verify_dataset(run_id)
                
        finally:
            self.disconnect()
            
        print("\n📊 TEST SUMMARY")
        print("=" * 60)
        for test_name, run_id in test_results.items():
            print(f"{test_name:12} -> {self.scope}:{run_id}.stf.ds")
            
        print(f"\nCheck PanDA tasks at: https://your-pandamon-url/tasks/")
        print(f"Monitor your agent logs for: JediTaskID")


def main():
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        injector = DatasetTestInjector()
        injector.connect()
        
        try:
            if test_type == "single":
                run_id = injector.run_single_file_test()
            elif test_type == "multi":
                run_id = injector.run_multi_file_test()
            elif test_type == "stress":
                run_id = injector.run_timing_stress_test()
            elif test_type == "error":
                run_id = injector.run_error_handling_test()
            else:
                print(f"Unknown test type: {test_type}")
                print("Usage: python test_inject.py [single|multi|stress|error|all]")
                return
                
            time.sleep(3)
            injector.verify_dataset(run_id)
            
        finally:
            injector.disconnect()
    else:
        # Run full suite
        injector = DatasetTestInjector()
        injector.run_all_tests()


if __name__ == "__main__":
    main()
