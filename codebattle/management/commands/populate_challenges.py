from django.core.management.base import BaseCommand
from codebattle.models import Challenge

class Command(BaseCommand):
    help = 'Populate the database with coding challenges'

    def handle(self, *args, **options):
        challenges_data = [
            # Easy Challenges
            {
                'title': 'Sum of Two Numbers',
                'description': 'Given two integers a and b, print their sum.',
                'problem_statement': 'Given two integers a and b, print their sum.',
                'difficulty': 'easy',
                'time_limit': 5,
                'language': 'python',
                'reference_solution': 'a, b = map(int, input().split())\nprint(a + b)',
                'test_cases': [
                    {'input': '5 7', 'output': '12'},
                    {'input': '0 0', 'output': '0'},
                    {'input': '-1 1', 'output': '0'},
                    {'input': '100 200', 'output': '300'},
                ],
                'sample_io': 'Input:\n5 7\n\nOutput:\n12'
            },
            {
                'title': 'Count Vowels in a String',
                'description': 'Given a lowercase string s, count the number of vowels (a, e, i, o, u).',
                'problem_statement': 'Given a lowercase string s, count the number of vowels (a, e, i, o, u).',
                'difficulty': 'easy',
                'time_limit': 5,
                'language': 'python',
                'reference_solution': 's = input().strip()\nvowels = set("aeiou")\ncount = sum(1 for ch in s if ch in vowels)\nprint(count)',
                'test_cases': [
                    {'input': 'hello world', 'output': '3'},
                    {'input': 'aeiou', 'output': '5'},
                    {'input': 'xyz', 'output': '0'},
                    {'input': 'programming', 'output': '3'},
                ],
                'sample_io': 'Input:\nhello world\n\nOutput:\n3'
            },
            {
                'title': 'Maximum of N Numbers',
                'description': 'Given n and an array of n integers, print the maximum element.',
                'problem_statement': 'Given n and an array of n integers, print the maximum element.',
                'difficulty': 'easy',
                'time_limit': 5,
                'language': 'python',
                'reference_solution': 'n = int(input())\narr = list(map(int, input().split()))\nprint(max(arr))',
                'test_cases': [
                    {'input': '5\n1 7 3 9 2', 'output': '9'},
                    {'input': '3\n-1 -2 -3', 'output': '-1'},
                    {'input': '1\n42', 'output': '42'},
                    {'input': '4\n10 20 30 40', 'output': '40'},
                ],
                'sample_io': 'Input:\n5\n1 7 3 9 2\n\nOutput:\n9'
            },
            {
                'title': 'Reverse a String',
                'description': 'Given a string s, print its reverse.',
                'problem_statement': 'Given a string s, print its reverse.',
                'difficulty': 'easy',
                'time_limit': 5,
                'language': 'python',
                'reference_solution': 's = input()\nprint(s[::-1])',
                'test_cases': [
                    {'input': 'code battle', 'output': 'elttab edoc'},
                    {'input': 'hello', 'output': 'olleh'},
                    {'input': 'a', 'output': 'a'},
                    {'input': '12345', 'output': '54321'},
                ],
                'sample_io': 'Input:\ncode battle\n\nOutput:\nelttab edoc'
            },
            {
                'title': 'Factorial of N',
                'description': 'Given integer n (0 ≤ n ≤ 12), print n!.',
                'problem_statement': 'Given integer n (0 ≤ n ≤ 12), print n!.',
                'difficulty': 'easy',
                'time_limit': 5,
                'language': 'python',
                'reference_solution': 'n = int(input())\nfact = 1\nfor i in range(2, n+1):\n    fact *= i\nprint(fact)',
                'test_cases': [
                    {'input': '5', 'output': '120'},
                    {'input': '0', 'output': '1'},
                    {'input': '1', 'output': '1'},
                    {'input': '3', 'output': '6'},
                ],
                'sample_io': 'Input:\n5\n\nOutput:\n120'
            },
            # Medium Challenges
            {
                'title': 'Two Sum',
                'description': 'Given an array of n integers and an integer k, determine if there exists a pair of elements whose sum equals k. Print "YES" or "NO".',
                'problem_statement': 'Given an array of n integers and an integer k, determine if there exists a pair of elements whose sum equals k. Print "YES" or "NO".',
                'difficulty': 'medium',
                'time_limit': 10,
                'language': 'python',
                'reference_solution': 'n = int(input())\narr = list(map(int, input().split()))\nk = int(input())\nseen = set()\nfound = False\nfor x in arr:\n    if k - x in seen:\n        found = True\n        break\n    seen.add(x)\nprint("YES" if found else "NO")',
                'test_cases': [
                    {'input': '5\n1 4 3 2 9\n6', 'output': 'YES'},
                    {'input': '3\n1 2 3\n10', 'output': 'NO'},
                    {'input': '4\n-1 0 1 2\n0', 'output': 'YES'},
                    {'input': '2\n5 5\n10', 'output': 'YES'},
                ],
                'sample_io': 'Input:\n5\n1 4 3 2 9\n6\n\nOutput:\nYES'
            },
            {
                'title': 'Balanced Parentheses',
                'description': 'Given a string containing only \'(\', \')\', \'{\', \'}\', \'[\', \']\', determine if it is balanced.',
                'problem_statement': 'Given a string containing only \'(\', \')\', \'{\', \'}\', \'[\', \']\', determine if it is balanced.',
                'difficulty': 'medium',
                'time_limit': 10,
                'language': 'python',
                'reference_solution': 's = input().strip()\nstack = []\npairs = {")": "(", "]": "[", "}": "{"}\nbalanced = True\nfor ch in s:\n    if ch in "([{":\n        stack.append(ch)\n    else:\n        if not stack or stack[-1] != pairs.get(ch, None):\n            balanced = False\n            break\n        stack.pop()\nif stack:\n    balanced = False\nprint("YES" if balanced else "NO")',
                'test_cases': [
                    {'input': '{[()]}', 'output': 'YES'},
                    {'input': '([)]', 'output': 'NO'},
                    {'input': '((()))', 'output': 'YES'},
                    {'input': '{[}]', 'output': 'NO'},
                ],
                'sample_io': 'Input:\n{[()]}\n\nOutput:\nYES'
            },
            {
                'title': 'Matrix Transpose',
                'description': 'Given a matrix of size n x m, print its transpose (m x n).',
                'problem_statement': 'Given a matrix of size n x m, print its transpose (m x n).',
                'difficulty': 'medium',
                'time_limit': 10,
                'language': 'python',
                'reference_solution': 'n, m = map(int, input().split())\nmat = [list(map(int, input().split())) for _ in range(n)]\nfor j in range(m):\n    row = [mat[i][j] for i in range(n)]\n    print(*row)',
                'test_cases': [
                    {'input': '2 3\n1 2 3\n4 5 6', 'output': '1 4\n2 5\n3 6'},
                    {'input': '1 1\n42', 'output': '42'},
                    {'input': '3 2\n1 2\n3 4\n5 6', 'output': '1 3 5\n2 4 6'},
                ],
                'sample_io': 'Input:\n2 3\n1 2 3\n4 5 6\n\nOutput:\n1 4\n2 5\n3 6'
            },
            {
                'title': 'Longest Word in a Sentence',
                'description': 'Given a sentence, find the longest word. If multiple have same max length, print the first.',
                'problem_statement': 'Given a sentence, find the longest word. If multiple have same max length, print the first.',
                'difficulty': 'medium',
                'time_limit': 10,
                'language': 'python',
                'reference_solution': 's = input().strip()\nwords = s.split()\nbest = ""\nfor w in words:\n    if len(w) > len(best):\n        best = w\nprint(best)',
                'test_cases': [
                    {'input': 'The quick brown fox jumps', 'output': 'quick'},
                    {'input': 'a bb ccc', 'output': 'ccc'},
                    {'input': 'hello world', 'output': 'hello'},
                ],
                'sample_io': 'Input:\nThe quick brown fox jumps\n\nOutput:\nquick'
            },
            {
                'title': 'Majority Element',
                'description': 'Given array, element appears > n/2 times, find it or print -1.',
                'problem_statement': 'Given array, element appears > n/2 times, find it or print -1.',
                'difficulty': 'medium',
                'time_limit': 10,
                'language': 'python',
                'reference_solution': 'n = int(input())\narr = list(map(int, input().split()))\ncandidate = None\ncount = 0\nfor num in arr:\n    if count == 0:\n        candidate = num\n    count += (1 if num == candidate else -1)\n# Verify\nif arr.count(candidate) > n // 2:\n    print(candidate)\nelse:\n    print(-1)',
                'test_cases': [
                    {'input': '9\n3 3 4 2 4 4 2 4 4', 'output': '4'},
                    {'input': '5\n1 2 3 4 5', 'output': '-1'},
                    {'input': '3\n1 1 1', 'output': '1'},
                ],
                'sample_io': 'Input:\n9\n3 3 4 2 4 4 2 4 4\n\nOutput:\n4'
            },
            # Hard Challenges
            {
                'title': 'Longest Increasing Subsequence',
                'description': 'Given array of n integers, find the length of the longest strictly increasing subsequence.',
                'problem_statement': 'Given array of n integers, find the length of the longest strictly increasing subsequence.',
                'difficulty': 'hard',
                'time_limit': 15,
                'language': 'python',
                'reference_solution': 'import bisect\nn = int(input())\narr = list(map(int, input().split()))\ntails = []\nfor x in arr:\n    i = bisect.bisect_left(tails, x)\n    if i == len(tails):\n        tails.append(x)\n    else:\n        tails[i] = x\nprint(len(tails))',
                'test_cases': [
                    {'input': '6\n10 9 2 5 3 7', 'output': '3'},
                    {'input': '5\n1 2 3 4 5', 'output': '5'},
                    {'input': '4\n4 3 2 1', 'output': '1'},
                ],
                'sample_io': 'Input:\n6\n10 9 2 5 3 7\n\nOutput:\n3'
            },
            {
                'title': 'Shortest Path in Grid',
                'description': 'You are given an n x m grid of 0s and 1s. 0 = free cell, 1 = blocked. Start at (0,0), reach (n-1,m-1) moving up/down/left/right on free cells. Print minimum steps or -1.',
                'problem_statement': 'You are given an n x m grid of 0s and 1s. 0 = free cell, 1 = blocked. Start at (0,0), reach (n-1,m-1) moving up/down/left/right on free cells. Print minimum steps or -1.',
                'difficulty': 'hard',
                'time_limit': 15,
                'language': 'python',
                'reference_solution': 'from collections import deque\nn, m = map(int, input().split())\ngrid = [list(map(int, input().split())) for _ in range(n)]\nif grid[0][0] == 1 or grid[n-1][m-1] == 1:\n    print(-1)\n    exit()\ndist = [[-1]*m for _ in range(n)]\nq = deque()\nq.append((0, 0))\ndist[0][0] = 0\ndirs = [(1,0),(-1,0),(0,1),(0,-1)]\nwhile q:\n    x, y = q.popleft()\n    if (x, y) == (n-1, m-1):\n        break\n    for dx, dy in dirs:\n        nx, ny = x+dx, y+dy\n        if 0 <= nx < n and 0 <= ny < m and grid[nx][ny] == 0 and dist[nx][ny] == -1:\n            dist[nx][ny] = dist[x][y] + 1\n            q.append((nx, ny))\nprint(dist[n-1][m-1])',
                'test_cases': [
                    {'input': '3 3\n0 0 0\n1 1 0\n0 0 0', 'output': '4'},
                    {'input': '2 2\n0 1\n1 0', 'output': '-1'},
                    {'input': '1 1\n0', 'output': '0'},
                ],
                'sample_io': 'Input:\n3 3\n0 0 0\n1 1 0\n0 0 0\n\nOutput:\n4'
            },
        ]

        for data in challenges_data:
            Challenge.objects.get_or_create(
                title=data['title'],
                defaults=data
            )

        self.stdout.write(self.style.SUCCESS('Successfully populated challenges'))
