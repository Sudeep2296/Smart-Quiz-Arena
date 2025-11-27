import requests
import time
import base64
from django.conf import settings

class Judge0Service:
    LANGUAGE_MAP = {
        'python': 71,
        'c': 50,
        'cpp': 54,
        'java': 62,
        'javascript': 63,
    }

    def __init__(self):
        self.api_url = settings.JUDGE0_API_URL
        self.api_key = settings.JUDGE0_API_KEY
        self.headers = {
            'X-RapidAPI-Key': self.api_key,
            'X-RapidAPI-Host': 'judge0-ce.p.rapidapi.com'
        }

    def safe_strip(self, value):
        """Safely strip a value, handling None and other types."""
        if value is None:
            return ''
        return str(value).strip()

    def submit_code(self, source_code, language_id, stdin=''):
        url = f"{self.api_url}/submissions?base64_encoded=true&fields=*"
        # Base64 encode source_code and stdin for RapidAPI Judge0
        encoded_source = base64.b64encode(source_code.encode('utf-8')).decode('utf-8')
        encoded_stdin = base64.b64encode(stdin.encode('utf-8')).decode('utf-8') if stdin else ''
        data = {
            'source_code': encoded_source,
            'language_id': language_id,
            'stdin': encoded_stdin,
            # 'base64_encoded': 'true'  # Removed as it's now in URL
        }
        try:
            response = requests.post(url, json=data, headers=self.headers, timeout=10)
            result = response.json()
            if response.status_code != 201:
                print(f"Judge0 API Error: Status {response.status_code}, Response: {result}")
                return {'error': result.get('error', 'API request failed')}
            return result
        except Exception as e:
            print(f"Judge0 API Exception: {e}")
            return {'error': str(e)}

    def get_submission_result(self, token):
        url = f"{self.api_url}/submissions/{token}?base64_encoded=true&fields=*"
        response = requests.get(url, headers=self.headers)
        result = response.json()
        # Decode base64 outputs
        if 'stdout' in result and result['stdout']:
            result['stdout'] = base64.b64decode(result['stdout']).decode('utf-8', errors='ignore')
        if 'stderr' in result and result['stderr']:
            result['stderr'] = base64.b64decode(result['stderr']).decode('utf-8', errors='ignore')
        if 'compile_output' in result and result['compile_output']:
            result['compile_output'] = base64.b64decode(result['compile_output']).decode('utf-8', errors='ignore')
        return result

    def get_languages(self):
        url = f"{self.api_url}/languages"
        response = requests.get(url, headers=self.headers)
        return response.json()

    def run_code(self, source_code, language, stdin=''):
        """
        Execute code with optional stdin and return output/error.
        Returns dict with 'output', 'error', 'time', 'memory'
        """
        # If no API key, simulate execution for development
        if not self.api_key:
            return self.simulate_run_code(source_code, language, stdin)

        language_id = self.LANGUAGE_MAP.get(language.lower())
        if not language_id:
            return {'output': '', 'error': 'Unsupported language', 'time': 0, 'memory': 0}

        # Submit code
        submit_response = self.submit_code(source_code, language_id, stdin)
        
        # Check for API errors and fall back to simulation
        if 'error' in submit_response or 'token' not in submit_response:
            error_msg = submit_response.get('error', 'Unknown error')
            print(f"Judge0 API unavailable: {error_msg}. Falling back to simulation.")
            return self.simulate_run_code(source_code, language, stdin)

        token = submit_response['token']

        # Poll for result
        result = None
        for _ in range(30):  # Max 30 seconds
            result = self.get_submission_result(token)
            status_id = result.get('status', {}).get('id')
            if status_id in [1, 2]:  # In queue or processing
                time.sleep(1)
                continue
            break

        if not result:
            print("Judge0 API timeout. Falling back to simulation.")
            return self.simulate_run_code(source_code, language, stdin)

        status_id = result.get('status', {}).get('id')
        stdout = self.safe_strip(result.get('stdout'))
        stderr = self.safe_strip(result.get('stderr'))
        compile_output = self.safe_strip(result.get('compile_output'))
        time_used = result.get('time', 0)
        memory_used = result.get('memory', 0)

        if status_id == 3:  # Accepted
            return {'output': stdout, 'error': None, 'time': time_used, 'memory': memory_used}
        elif status_id == 6:  # Compilation error
            return {'output': '', 'error': compile_output or 'Compilation error', 'time': time_used, 'memory': memory_used}
        elif status_id == 7:  # Runtime error
            return {'output': stdout, 'error': stderr or 'Runtime error', 'time': time_used, 'memory': memory_used}
        elif status_id == 5:  # Time limit exceeded
            return {'output': stdout, 'error': 'Time limit exceeded', 'time': time_used, 'memory': memory_used}
        else:
            return {'output': stdout, 'error': 'Execution failed', 'time': time_used, 'memory': memory_used}

    def execute_with_test_cases(self, source_code, language, test_cases):
        """
        Execute code against multiple test cases.
        Returns dict with 'passed', 'total', 'details' (list of dicts with 'input', 'expected', 'output', 'passed', 'error')
        """
        # If no API key, use simulation
        if not self.api_key:
            return self.simulate_execute_with_test_cases(source_code, language, test_cases)

        language_id = self.LANGUAGE_MAP.get(language.lower())
        if not language_id:
            return {'passed': 0, 'total': len(test_cases), 'details': [{'error': 'Unsupported language'}]}

        results = []
        passed = 0
        api_failed = False
        
        for i, test_case in enumerate(test_cases):
            stdin = test_case.get('input', '')
            expected = test_case.get('output', '').strip()

            # Submit code
            submit_response = self.submit_code(source_code, language_id, stdin)
            
            # Check for API errors (rate limiting, etc.)
            if 'error' in submit_response or 'token' not in submit_response:
                error_msg = submit_response.get('error', 'Unknown error')
                print(f"Judge0 API unavailable: {error_msg}. Falling back to simulation.")
                api_failed = True
                break

            token = submit_response['token']

            # Poll for result
            result = None
            for _ in range(30):  # Max 30 seconds
                result = self.get_submission_result(token)
                status_id = result.get('status', {}).get('id')
                if status_id in [1, 2]:  # In queue or processing
                    time.sleep(1)
                    continue
                break

            if not result:
                print("Judge0 API timeout. Falling back to simulation.")
                api_failed = True
                break

            status_id = result.get('status', {}).get('id')
            stdout = self.safe_strip(result.get('stdout'))
            stderr = self.safe_strip(result.get('stderr'))
            compile_output = self.safe_strip(result.get('compile_output'))

            passed_test = False
            error = None

            if status_id == 3:  # Accepted
                if stdout == expected:
                    passed_test = True
                    passed += 1
                else:
                    error = 'Wrong answer'
            elif status_id == 4:  # Wrong answer
                error = 'Wrong answer'
            elif status_id == 5:  # Time limit exceeded
                error = 'Time limit exceeded'
            elif status_id == 6:  # Compilation error
                error = compile_output or 'Compilation error'
            elif status_id == 7:  # Runtime error
                error = stderr or 'Runtime error'
            else:
                error = 'Unknown error'

            results.append({
                'input': stdin,
                'expected': expected,
                'output': stdout,
                'passed': passed_test,
                'error': error
            })
        
        # If API failed, fall back to simulation
        if api_failed:
            print("Using simulation mode for code execution.")
            return self.simulate_execute_with_test_cases(source_code, language, test_cases)

        return {
            'passed': passed,
            'total': len(test_cases),
            'details': results
        }

    def simulate_execute_with_test_cases(self, source_code, language, test_cases):
        """
        Simulate execution against test cases for development when API key is not available.
        Currently supports basic Python execution.
        """
        if language.lower() != 'python':
            return {'passed': 0, 'total': len(test_cases), 'details': [{'error': 'Simulation only supports Python'} for _ in test_cases]}

        results = []
        passed = 0
        for test_case in test_cases:
            stdin = test_case.get('input', '')
            expected = test_case.get('output', '').strip()

            try:
                # Create a safe execution environment
                import io
                import bisect
                import collections
                import itertools
                import math
                import re
                from contextlib import redirect_stdout, redirect_stderr

                # Prepare input
                input_buffer = io.StringIO(stdin)

                # Capture output
                output_buffer = io.StringIO()
                error_buffer = io.StringIO()

                # Create a restricted globals dict with commonly used modules
                safe_globals = {
                    '__builtins__': {
                        'print': print,
                        'input': lambda: input_buffer.readline().strip(),
                        'len': len,
                        'range': range,
                        'int': int,
                        'str': str,
                        'list': list,
                        'dict': dict,
                        'set': set,
                        'sum': sum,
                        'max': max,
                        'min': min,
                        'abs': abs,
                        'sorted': sorted,
                        'enumerate': enumerate,
                        'zip': zip,
                        'map': map,
                        'filter': filter,
                        'all': all,
                        'any': any,
                        'bool': bool,
                        'float': float,
                        'True': True,
                        'False': False,
                        'None': None,
                        '__import__': __import__,
                        '__name__': '__main__',
                    },
                    'bisect': bisect,
                    'collections': collections,
                    'itertools': itertools,
                    'math': math,
                    're': re,
                }

                # Execute the code
                with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                    exec(source_code, safe_globals)

                output = output_buffer.getvalue().strip()
                error = error_buffer.getvalue().strip()

                passed_test = (output == expected) and not error
                if passed_test:
                    passed += 1

                results.append({
                    'input': stdin,
                    'expected': expected,
                    'output': output,
                    'passed': passed_test,
                    'error': error if error else None
                })

            except Exception as e:
                results.append({
                    'input': stdin,
                    'expected': expected,
                    'output': '',
                    'passed': False,
                    'error': str(e)
                })

        return {
            'passed': passed,
            'total': len(test_cases),
            'details': results
        }

    def simulate_run_code(self, source_code, language, stdin=''):
        """
        Simulate code execution for development when API key is not available.
        Currently supports basic Python execution.
        """
        if language.lower() != 'python':
            return {'output': '', 'error': 'Simulation only supports Python', 'time': 0, 'memory': 0}

        try:
            # Create a safe execution environment
            import io
            import sys
            import bisect
            import collections
            import itertools
            import math
            import re
            from contextlib import redirect_stdout, redirect_stderr

            # Prepare input
            input_buffer = io.StringIO(stdin)

            # Capture output
            output_buffer = io.StringIO()
            error_buffer = io.StringIO()

            # Create a restricted globals dict with commonly used modules
            safe_globals = {
                '__builtins__': {
                    'print': print,
                    'input': lambda: input_buffer.readline().strip(),
                    'len': len,
                    'range': range,
                    'int': int,
                    'str': str,
                    'list': list,
                    'dict': dict,
                    'set': set,
                    'sum': sum,
                    'max': max,
                    'min': min,
                    'abs': abs,
                    'sorted': sorted,
                    'enumerate': enumerate,
                    'zip': zip,
                    'map': map,
                    'filter': filter,
                    'all': all,
                    'any': any,
                    'bool': bool,
                    'float': float,
                    'True': True,
                    'False': False,
                    'None': None,
                    '__import__': __import__,
                    '__name__': '__main__',
                },
                'bisect': bisect,
                'collections': collections,
                'itertools': itertools,
                'math': math,
                're': re,
            }

            # Execute the code
            with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                exec(source_code, safe_globals)

            output = output_buffer.getvalue().strip()
            error = error_buffer.getvalue().strip()

            return {
                'output': output,
                'error': error if error else None,
                'time': 0.001,  # Simulated time
                'memory': 1024  # Simulated memory
            }

        except Exception as e:
            return {
                'output': '',
                'error': str(e),
                'time': 0,
                'memory': 0
            }
