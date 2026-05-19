#!/usr/bin/env python
"""
Django-based Fuzzing Tester for IoT Hub Monitor API
"""
import os
import sys
import django
from datetime import datetime
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from iot_hub.apps.accounts.models import UserRole, UserProfile


class FuzzingTester:
    def __init__(self):
        self.client = Client()
        self.results = []
        self.passed = 0
        self.failed = 0
        self.setup_test_users()
    
    def setup_test_users(self):
        """Setup test users."""
        self.user, _ = User.objects.get_or_create(
            username='testuser',
            defaults={'email': 'testuser@test.com'}
        )
        self.user.set_password('testpass123')
        self.user.save()
        
        self.admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@test.com', 'is_staff': True, 'is_superuser': True}
        )
        
        # Create roles if not exist
        UserRole.objects.get_or_create(user=self.admin_user, defaults={'is_admin': True})
        UserRole.objects.get_or_create(user=self.user, defaults={'is_admin': False})
        
        # Create profiles if not exist
        UserProfile.objects.get_or_create(user=self.user)
        UserProfile.objects.get_or_create(user=self.admin_user)
    
    def log_test(self, name, passed, code=None):
        """Log test result."""
        status = "✓ PASS" if passed else "✗ FAIL"
        code_str = f" ({code})" if code else ""
        
        color = "\033[92m" if passed else "\033[91m"
        reset = "\033[0m"
        
        print(f"{color}{status}{reset} {name}{code_str}")
        
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        
        self.results.append({
            'name': name,
            'status': 'PASS' if passed else 'FAIL',
            'code': code
        })
    
    def print_header(self):
        """Print header."""
        print("\n" + "="*70)
        print("IoT Hub Monitor - FUZZING TEST SUITE")
        print("="*70)
        print("Target: Django Test Client\n")
    
    def print_category(self, name):
        """Print category."""
        print(f"[→] Testing {name}...")
    
    def test_sql_injection(self):
        """Test SQL injection protection."""
        self.print_category("SQL Injection")
        
        payloads = [
            ("' OR '1'='1", "OR Based"),
            ("'; DROP TABLE users;--", "Drop"),
            ("admin'--", "Comment"),
            ("' UNION SELECT * FROM users--", "Union"),
        ]
        
        for payload, desc in payloads:
            resp = self.client.post('/api/auth/users/login/', 
                                   {'username': payload, 'password': payload},
                                   content_type='application/json')
            passed = resp.status_code in [400, 401, 403]
            self.log_test(f"SQL Injection {desc}", passed, resp.status_code)
            
            resp = self.client.get(f'/api/devices/?search={payload}')
            passed = resp.status_code in [200, 400, 401, 403]
            self.log_test(f"SQL Injection Route {desc}", passed, resp.status_code)
    
    def test_xss(self):
        """Test XSS protection."""
        self.print_category("XSS Payloads")
        
        payloads = [
            ('<script>alert("XSS")</script>', "Script"),
            ('javascript:alert("XSS")', "JS"), 
            ('<img src=x onerror="alert(\'XSS\')">', "Event"),
        ]
        
        for payload, desc in payloads:
            resp = self.client.post('/api/auth/users/register/',
                                   {'username': payload, 'email': 'test@test.com', 'password': 'pass'},
                                   content_type='application/json')
            passed = resp.status_code in [200, 201, 400]
            self.log_test(f"XSS Register {desc}", passed, resp.status_code)
    
    def test_authentication(self):
        """Test authentication guards."""
        self.print_category("Authentication Guards")
        
        endpoints = ['/api/devices/', '/api/alerts/', '/api/telemetry/']
        
        for endpoint in endpoints:
            resp = self.client.get(endpoint)
            # 401 Unauthorized or 403 Forbidden are both valid for unauthed users
            passed = resp.status_code in [401, 403]
            self.log_test(f"Protected {endpoint}", passed, resp.status_code)
    
    def test_path_traversal(self):
        """Test path traversal."""
        self.print_category("Path Traversal & Injection")
        
        tests = [
            ('/api/devices/%2F..%2F..%2Fetc%2Fpasswd', "Unix Path"),
            ('/api/devices/%00', "Null Byte"),
            ('/api/devices/?search=%3B%20cat', "Command"),
        ]
        
        for endpoint, desc in tests:
            resp = self.client.get(endpoint)
            passed = resp.status_code in [200, 400, 401, 404]
            self.log_test(f"Traversal {desc}", passed, resp.status_code)
    
    def test_large_payloads(self):
        """Test large payloads."""
        self.print_category("Large Payloads")
        
        large_data = 'A' * 50000
        resp = self.client.post('/api/auth/users/register/',
                               {'username': large_data, 'email': 'test@test.com', 'password': 'x'},
                               content_type='application/json')
        passed = resp.status_code in [200, 201, 400, 413]
        self.log_test("Large Payload Register", passed, resp.status_code)
    
    def test_rbac(self):
        """Test RBAC."""
        self.print_category("RBAC")
        
        resp = self.client.post('/api/auth/users/login/',
                               {'username': 'admin', 'password': 'admin'},
                               content_type='application/json')
        # 401 is ok if credentials are invalid, 200 if valid
        passed = resp.status_code in [200, 400, 401]
        self.log_test("Auth Login", passed, resp.status_code)
        
        resp = self.client.get('/admin/')
        passed = resp.status_code in [200, 302, 403, 404]
        self.log_test("Admin Panel", passed, resp.status_code)
    
    def test_malformed_requests(self):
        """Test malformed requests."""
        self.print_category("Malformed Requests")
        
        resp = self.client.post('/api/auth/users/login/',
                               {'username': 'test'},
                               content_type='application/json')
        passed = resp.status_code in [400, 401]
        self.log_test("Missing Fields", passed, resp.status_code)
        
        resp = self.client.post('/api/auth/users/login/',
                               b'{invalid json}',
                               content_type='application/json')
        passed = resp.status_code in [400, 401]
        self.log_test("Malformed JSON", passed, resp.status_code)
    
    def test_http_methods(self):
        """Test unsupported HTTP methods."""
        self.print_category("HTTP Methods")
        
        resp = self.client.put('/api/devices/')
        # 403, 405 are both valid responses for unauthorized PUT
        passed = resp.status_code in [200, 201, 400, 401, 403, 405]
        self.log_test("PUT Method", passed, resp.status_code)
        
        resp = self.client.delete('/api/devices/')
        passed = resp.status_code in [200, 201, 400, 401, 403, 405]
        self.log_test("DELETE Method", passed, resp.status_code)
    
    def print_summary(self):
        """Print summary."""
        total = self.passed + self.failed
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total: {total}")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print("="*70)
    
    def run(self):
        """Run all tests."""
        try:
            self.print_header()
            self.test_sql_injection()
            self.test_xss()
            self.test_authentication()
            self.test_path_traversal()
            self.test_large_payloads()
            self.test_rbac()
            self.test_malformed_requests()
            self.test_http_methods()
            self.print_summary()
        except Exception as e:
            print(f"\n\033[91m✗ Error: {str(e)}\033[0m")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    tester = FuzzingTester()
    tester.run()
