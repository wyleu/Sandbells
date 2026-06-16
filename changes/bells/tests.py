from django.test import TestCase
from django.test import Client
from django.test.utils import setup_test_environment

from .models import Pattern


from .functions import (
    correct,
    incorrect,
    frontcorrect,
    size,
    sanity,
    same,
    swap,
    compare,
    db_process
    )

from .functions import (
    RepeatInCurrent,
    RepeatInRequired,
    DifferingLength
    )

debug = False

class TestFail(TestCase):
    def test_fail(self):
        # Installed as a quick test to see if vsc django tests are actually consious.
        self.assertFalse(False)

class TestSanity(TestCase):
    sanity_array = [
        ('123456','123456', True),
        ('12345678','12345678', True),
    ]

    def test_unique(self):
        for item in self.sanity_array:
            self.assertEqual(sanity(item[0], item[1]), item[2])

    def test_repeated_bell_in_current(self):
        with self.assertRaises(RepeatInCurrent):
            sanity('12245678','12345678')

    def test_repeated_bell_in_required(self):
        with self.assertRaises(RepeatInRequired):
            sanity('12345678','12245678')
 
class TestMatch(TestCase):
    def test_size_pass(self):
        # sizeing patterns
        current = '123456'
        required = '654321'
        self.assertTrue(size(current, required))
    
    def test_size_fail_size(self):
        # fail on pattern size
        current = '12345'
        required = '654321'
        self.assertFalse(size(current, required))

    def test_size_fail_null(self):
        # fail on null strings
        current = ''
        required = ''
        self.assertFalse(size(current, required))

class TestCorrect(TestCase):
      
    test_array = (
            ('123456','123456', 6, 0, True, 0),
            ('123456','123465', 4, 2, False, 5),
            ('654321','123456', 0, 6, False, 1),
            ('123456','126543', 2, 4, False, 3),           
            ('123456','123564', 3, 3, False, 4),
            ('123456','123465', 4, 2, False, 5),
            ('123456','123456', 6, 0, True, 0),
            )
    def test_correct_array(self):
        # compare test array to correct [2]

        for item in self.test_array:
            self.assertEquals(correct(item[0],item[1]), item[2])

    def test_incorrect_array(self):
        # compare test array to incorrect [3]

        for item in self.test_array:
            self.assertEquals(incorrect(item[0],item[1]), item[3])

    def test_same(self):
        for item in self.test_array:
            self.assertEquals(same(item[0],item[1]), item[4])

    def test_frontcorrect(self):
        for item in self.test_array:
            self.assertEquals(frontcorrect(item[0],item[1]), item[5])

class TestCompare(TestCase):
        test_array = (
            ('123456','123456', ''),
            ('123456','123465', '56'),
            ('654321','123456','654321'),
            ('123456','126543', '3456'),           
            ('123456','123564', '456'),
            ('123456','123465', '56'),
            ('12345678','12345678', ''),
            )
        
        def test_compare_strings(self):
            for item in self.test_array:
                self.assertEqual(compare(item[0],item[1]),item[2])

class TestSwap(TestCase):
    swap_array =(
        ('123456','1','213456'),
        ('123456','2','132456'),
        ('123456','6','123456'),  
        ('123456','3','124356'),
        ('12345678','1', '21345678'),
        ('12345678', '2', '13245678'),
        ('41253678','1', '14253678')            # Before Swap:- 41253678
                                                # After Swap:- 81253674 Current Pos+1:- 1 
    )

    def test_swap_array(self):
        for item in self.swap_array:
            self.assertEqual(swap(item[0],item[1]),item[2])

class TestProcess(TestCase):
    # Proposal
    #  g. from Queens to Tittums on 6 bells.
    #  3 to 5, 2 to 4, 3 to 4, 5 to 4, 3 to 2, 5 to 2
    # Algo: '135246', '135426', '134526', '143526', '143256', '142356', '142536'
    #  135246, 153246, 153  142536
    # h. from Rounds to Queens on 8 bells.
    #  2 to 3, 4 to 5, 6 to 7, 2 to 5, 4 to 7, 2 to 7
    # i from Queens to Tittums on 8 bells.
    # 3 to 5, 7 to 2, 4 to 6, 3 to 2, 7 to 6, 3 to 6
    # j. from Tittums to Rounds on 8 bells.
    # 5 to 2, 6 to 3, 7 to 4, 5 to 3, 6 to 4, 5 to 4


    changes_array = (
        ('Rounds to Titums on 6',
        ['123456',
         '124356',
         '142356',
         '142536'],
        ),
        ('Titums to Rounds on 6',
        ['142536',
         '124536',
         '124356',
         '123456'],
        ),
        ('Rounds to Queens on 6',
        ['123456',
         '132456',
         '132546',
         '135246'],
        ),
        ('Queens to Rounds on 6',
        ['135246',
         '132546',
         '123546',
         '123456'],
        ),
        ('Queens to Titums on 6',
        ['135246',
         '135426',
         '134526',
         '143526',
         '143256',
         '142356', 
         '142536'],
        ),
        ('Titums to Queens on 6',
        [
         '142536',
         '142356',
         '143256',
         '134256',
         '134526',
         '135426',
         '135246'],
        ),
        ('Rounds to Kings on 6',
        ['123456',
         '123546',
         '125346',
         '152346',
         '512346',
         '513246',
         '531246'],
        ),
        ('Kings to Rounds on 6',
        ['531246',
         '513246',
         '153246',
         '152346',
         '125346',
         '123546',
         '123456'],
        ),
        ('Rounds to Titums on 8',
        ['12345678',
         '12354678',
         '12534678',
         '15234678',
         '15236478',
         '15263478',
         '15263748'],
        ),
        ('Titums to Rounds on 8',
        ['15263748',
         '12563748',
         '12536748',
         '12356748', 
         '12356478', 
         '12354678', 
         '12345678'],
        ),
        ('Rounds to Queens on 8',
        ['12345678', 
         '13245678', 
         '13254678', 
         '13524678', 
         '13524768', 
         '13527468',
         '13572468'],
        ),
        ('Queens to Rounds on 8',
        ['13572468', 
         '13527468', 
         '13257468', 
         '12357468', 
         '12354768', 
         '12345768'],
        ),
        ('Queens to Titums on 8',
        ['13572468', 
         '15372468', 
         '15327468', 
         '15237468', 
         '15237648',
         '15236748',
         '15263748'],
        ),
        ('Titums to Queens on 8',
        ['15263748', 
         '15236748',
         '15326748',
         '13526748',
         '13527648',
         '13572648',
         '13572468'],
        ),
        ('Rounds to Kings on 8',
        ['12345678',
         '12345768',
         '12347568',
         '12374568',
         '12734568',
         '17234568',
         '71234568',
         '71235468',
         '71253468',
         '71523468',
         '75123468',
         '75132468',
         '75312468'],
        ),
        ('Kings to Rounds on 8',
        ['75312468',
         '75132468',
         '71532468',
         '17532468',
         '17523468',
         '17253468',
         '12753468',
         '12735468',
         '12375468',
         '12374568',
         '12347568',
         '12345768',
         '12345678'],
        ),
        ('Rounds to Total Rev',
        ['12345678',
         '12345687',
         '12345867',
         '12348567',
         '12384567',
         '12834567',
         '18234567',
         '81234567',
         '81234576',
         '81234756',
         '81237456',
         '81273456',
         '81723456',
         '87123456',
         '87123465',
         '87123645',
         '87126345',
         '87162345',
         '87612345',
         '87612354',
         '87612534',
         '87615234',
         '87651234',
         '87651243',
         '87651423',
         '87654123',
         '87654132',
         '87654312',
         '87654321']
         ),
        ('Twenty All Over',
         [
         '12345', # 
         '21345', #  1-2
         '23145', #  1-3
         '23415', #  1-4
         '23451', #  1-5
         '32451', #  2-3
         '34251', #  2-4
         '34521', #  2-5
         '34512', #  2-1
         '43512', #  3-4
         '45312', #  3-5
         '45132', #  3-1
         '45123', #  3-2
         '54123', #  4-5
         '51423', #  4-1
         '51243', #  4-2
         '51234', #  4-3
         '15234', #  5-1
         '12534', #  5-2
         '12354', #  5-3
         '12345', #  5-4 
         ]
         ),

      
       # ('Titums to Rounds on 6 rev',
       # ['142536','142356','124356','123456'],
       # ),
       # ('Queens to Rounds on 6 rev',
       # ['135246','132546','132456','123456'],
       # ),

       # ('Kings to Rounds on 6 rev', 
       # ['531246','513246','512346','152346','125346','123546','123456'],
       # ),
    )

    def test_db_process_array(self):
        for name, expected_rows in self.changes_array:
            with self.subTest(name=name):
                calls, result, swappair = db_process(expected_rows[0], expected_rows[-1])
                
                self.assertEqual(
                    result[0], 
                    expected_rows,
                    f"Failed on {name}\nGot: {result[0]}\nExpected: {expected_rows}"
                )




#     def test_db_process_array(self):
#         for count, item in enumerate(self.changes_array):
#             print('\n',item[1][0],'-----', item[0], '-----',item[1][-1], '\n')
#             calls, result, swappair = db_process(item[1][0],item[1][-1])
# 
#             self.assertEqual(result[0] , item[1])
#             if debug:
#                 for count, item in enumerate(result[0]):
#                     print('    '.join([item,
#                         result[1][count][0],
#                         result[1][count][1],
#                         result[1][count][2]]))

class TestSearch(TestCase):
    
    def test_search_default(self):
        # is rounds the default config?
        self.assertEqual(Pattern.objects.filter()[0].name,'Rounds')

    def test_search_number_default(self):
        # is 8 the default number of bells ?
        self.assertEqual(Pattern.objects.filter()[0].number,8)

class TestFrontEnd(TestCase):

    def test_search(self):
        response = self.client.get('/')
        self.assertEquals(response.status_code, 404)
    
    def test_tower(self):
        response = self.client.get('/tower/')
        self.assertEquals(response.status_code, 200)

class TestFrontEndList(TestCase):
    # Tests the searching mechanism
    def test_potrait_list(self):
        response = self.client.get('/tower/pattern/')
        self.assertEquals(response.status_code, 200)