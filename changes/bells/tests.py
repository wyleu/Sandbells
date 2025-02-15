from django.test import TestCase
from .functions import db_process

# Create your tests here.

class SimpleTestCase(TestCase):
    def test_one_plus_one(self):
        self.assertEquals(1 + 1, 2)


class TestDBProcess(TestCase):
    rounds = '12345678'
    queens = '13572468'
    jokers = '17654328'

    def test_db_process(self):
        calls, result, swappair = db_process(self.rounds, self.jokers)
        print('CALLS')
        for item in calls:
            print(item)
        print('RESULT-0')
        for item in result[0]:
            print(item)
        print('RESULT-1')
        for item in result[1]:
            print(item)
        print('SWAPPAIR')
        for item in swappair:
            print(item)

