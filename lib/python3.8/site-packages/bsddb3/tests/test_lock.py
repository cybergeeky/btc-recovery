"""
Copyright (c) 2008-2020, Jesus Cea Avion <jcea@jcea.es>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

    1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.

    2. Redistributions in binary form must reproduce the above
    copyright notice, this list of conditions and the following
    disclaimer in the documentation and/or other materials provided
    with the distribution.

    3. Neither the name of Jesus Cea Avion nor the names of its
    contributors may be used to endorse or promote products derived
    from this software without specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
    CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
    INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
    MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
    DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS
    BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
    EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
            TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
            DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
    ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR
    TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
    THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
    SUCH DAMAGE.
    """

"""
TestCases for testing the locking sub-system.
"""

import time

import unittest
from .test_all import db, test_support, verbose, have_threads, \
        get_new_environment_path, get_new_database_path

if have_threads :
    from threading import Thread
    import sys
    if sys.version_info[0] < 3 :
        from threading import currentThread
    else :
        from threading import current_thread as currentThread

#----------------------------------------------------------------------

class LockingTestCase(unittest.TestCase):
    def setUp(self):
        self.homeDir = get_new_environment_path()
        self.env = db.DBEnv()
        self.env.open(self.homeDir, db.DB_THREAD | db.DB_INIT_MPOOL |
                                    db.DB_INIT_LOCK | db.DB_CREATE)


    def tearDown(self):
        self.env.close()
        test_support.rmtree(self.homeDir)


    def test01_simple(self):
        if verbose:
            print('\n', '-=' * 30)
            print("Running %s.test01_simple..." % self.__class__.__name__)

        anID = self.env.lock_id()
        if verbose:
            print("locker ID: %s" % anID)
        lock = self.env.lock_get(anID, "some locked thing", db.DB_LOCK_WRITE)
        if verbose:
            print("Aquired lock: %s" % lock)
        self.env.lock_put(lock)
        if verbose:
            print("Released lock: %s" % lock)
        self.env.lock_id_free(anID)


    def test02_threaded(self):
        if verbose:
            print('\n', '-=' * 30)
            print("Running %s.test02_threaded..." % self.__class__.__name__)

        threads = []
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_WRITE,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_READ,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_READ,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_WRITE,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_READ,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_READ,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_WRITE,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_WRITE,)))
        threads.append(Thread(target = self.theThread,
                              args=(db.DB_LOCK_WRITE,)))

        for t in threads:
            import sys
            if sys.version_info[0] < 3 :
                t.setDaemon(True)
            else :
                t.daemon = True
            t.start()
        for t in threads:
            t.join()

    def test03_lock_timeout(self):
        self.env.set_timeout(0, db.DB_SET_LOCK_TIMEOUT)
        self.assertEqual(self.env.get_timeout(db.DB_SET_LOCK_TIMEOUT), 0)
        self.env.set_timeout(0, db.DB_SET_TXN_TIMEOUT)
        self.assertEqual(self.env.get_timeout(db.DB_SET_TXN_TIMEOUT), 0)
        self.env.set_timeout(123456, db.DB_SET_LOCK_TIMEOUT)
        self.assertEqual(self.env.get_timeout(db.DB_SET_LOCK_TIMEOUT), 123456)
        self.env.set_timeout(7890123, db.DB_SET_TXN_TIMEOUT)
        self.assertEqual(self.env.get_timeout(db.DB_SET_TXN_TIMEOUT), 7890123)

    def test04_lock_timeout2(self):
        self.env.set_timeout(0, db.DB_SET_LOCK_TIMEOUT)
        self.env.set_timeout(0, db.DB_SET_TXN_TIMEOUT)
        self.env.set_timeout(123456, db.DB_SET_LOCK_TIMEOUT)
        self.env.set_timeout(7890123, db.DB_SET_TXN_TIMEOUT)

        def deadlock_detection() :
            while not deadlock_detection.end :
                deadlock_detection.count = \
                    self.env.lock_detect(db.DB_LOCK_EXPIRE)
                if deadlock_detection.count :
                    while not deadlock_detection.end :
                        pass
                    break
                time.sleep(0.01)

        deadlock_detection.end=False
        deadlock_detection.count=0
        t=Thread(target=deadlock_detection)
        import sys
        if sys.version_info[0] < 3 :
            t.setDaemon(True)
        else :
            t.daemon = True
        t.start()
        self.env.set_timeout(100000, db.DB_SET_LOCK_TIMEOUT)
        anID = self.env.lock_id()
        anID2 = self.env.lock_id()
        self.assertNotEqual(anID, anID2)
        lock = self.env.lock_get(anID, "shared lock", db.DB_LOCK_WRITE)
        start_time=time.time()
        self.assertRaises(db.DBLockNotGrantedError,
                self.env.lock_get,anID2, "shared lock", db.DB_LOCK_READ)
        end_time=time.time()
        deadlock_detection.end=True
        # Floating point rounding
        self.assertTrue((end_time-start_time) >= 0.0999)
        self.env.lock_put(lock)
        t.join()

        self.env.lock_id_free(anID)
        self.env.lock_id_free(anID2)

        self.assertTrue(deadlock_detection.count>0)

    def theThread(self, lockType):
        import sys
        if sys.version_info[0] < 3 :
            name = currentThread().getName()
        else :
            name = currentThread().name

        if lockType ==  db.DB_LOCK_WRITE:
            lt = "write"
        else:
            lt = "read"

        anID = self.env.lock_id()
        if verbose:
            print("%s: locker ID: %s" % (name, anID))

        for i in range(1000) :
            lock = self.env.lock_get(anID, "some locked thing", lockType)
            if verbose:
                print("%s: Aquired %s lock: %s" % (name, lt, lock))

            self.env.lock_put(lock)
            if verbose:
                print("%s: Released %s lock: %s" % (name, lt, lock))

        self.env.lock_id_free(anID)


#----------------------------------------------------------------------

def test_suite():
    suite = unittest.TestSuite()

    if have_threads:
        suite.addTest(unittest.makeSuite(LockingTestCase))
    else:
        suite.addTest(unittest.makeSuite(LockingTestCase, 'test01'))

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
