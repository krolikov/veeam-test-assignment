import unittest
import pathlib
import dirsync
import sched
import time

class dirsync_tests (unittest.TestCase):
    
    @classmethod
    def setUpClass(cls) -> None:   

        cls.dir_rootpath = pathlib.Path('/test/root')
        cls.dir_abspath = pathlib.Path('/test/root/long/path')
        cls.dir_relpath = pathlib.Path('long/path')     
        
        cls.md5_expected = 'cfcd208495d565ef66e7dff9f98764da'

        cls.testsrc_files = {
            pathlib.Path('testdir'): None,
            pathlib.Path('md5.test'): cls.md5_expected
        } 
        cls.testtarget_files = {}    
        
        cls.schedule = sched.scheduler(time.time, time.sleep) 

        return super().setUpClass()
    
    def setUp(self) -> None:
        self.dir_testsrc = pathlib.Path('testsrc')
        self.dir_testsrc.mkdir(exist_ok=True)
        self.dir_testdir = pathlib.Path('testsrc/testdir')
        self.dir_testdir.mkdir(exist_ok=True)
        
        self.dir_testtarget = pathlib.Path('testtarget')
        self.dir_testtarget.mkdir(exist_ok=True)
        self.dir_testdir_target = pathlib.Path('testtarget/testdir')
        self.md5file_target = pathlib.Path('testtarget/md5.test')

        self.md5file = 'testsrc/md5.test'
        
        with open(self.md5file, 'w') as f:
            f.write('0')

        return super().setUp()


    def test_get_md5(self):
        #test output with good file
        with self.subTest():
            self.assertEqual(dirsync.get_md5(self.md5file), self.md5_expected)
        #test output with nonexsitent file
        with self.subTest():
            self.assertEqual(dirsync.get_md5('wrongvalue'), 0)
    
    def test_get_relative_path(self):
        actual_relpath = dirsync.get_relative_path(self.dir_rootpath, self.dir_abspath)
        self.assertEqual(actual_relpath, self.dir_relpath)

    def test_get_absolute_path(self):
        actual_abspath = dirsync.get_absolute_path(self.dir_rootpath, self.dir_relpath)
        self.assertEqual(actual_abspath, self.dir_abspath)

    def test_get_files_in_path(self):
        scanned = dirsync.get_files_in_path('testsrc')
        self.assertEqual(scanned, self.testsrc_files)
    
    def test_copy_objects(self):
        dirsync.copy_objects(self.testsrc_files, self.testtarget_files, self.dir_testsrc, self.dir_testtarget)
        self.assertTrue(self.dir_testdir_target.exists())
        self.assertTrue(self.md5file_target.exists())

    def test_remove_objects(self):       
        mock_srcfiles = {}
        self.dir_testdir.rmdir()
        dirsync.remove_objects(mock_srcfiles, self.testsrc_files, self.dir_testtarget)
        for i in self.dir_testtarget.glob('**/*'):
            print (i)
        for i in self.dir_testsrc.glob('**/*'):
            print (i)
        self.assertFalse(self.dir_testdir_target.exists())
        self.assertFalse(self.md5file_target.exists())

    def test_do_sync_dirs_copy(self):
        interval = 10
        self.schedule.cancel(dirsync.do_sync_dirs(self.dir_testsrc, self.dir_testtarget, self.schedule, interval))
        self.assertTrue(self.dir_testdir_target.exists())
        self.assertTrue(self.md5file_target.exists())

    def test_do_sync_dirs_remove(self):
        interval = 10
        self.dir_testdir.rmdir()
        self.schedule.cancel(dirsync.do_sync_dirs(self.dir_testsrc, self.dir_testtarget, self.schedule, interval))
        self.assertFalse(self.dir_testdir_target.exists())

    def test_copy_verify(self):
        result = dirsync.copy_verify_file(self.md5file, self.md5file_target)
        self.assertTrue(result)

    def tearDown(self) -> None:
        pathlib.Path(self.md5file).unlink()
        
        try:
            self.md5file_target.unlink()
        except FileNotFoundError:
            pass 

        for d in [self.dir_testdir,
            self.dir_testsrc,
            self.dir_testdir_target,
            self.dir_testtarget]:
            try:
                d.rmdir()
            except FileNotFoundError:
                pass       
        return super().tearDown()

    @classmethod
    def tearDownClass(cls) -> None:
        return super().tearDownClass()

if __name__ == '__main__':
    unittest.main()
    