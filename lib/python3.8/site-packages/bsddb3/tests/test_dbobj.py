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


import os, string
import unittest

from .test_all import db, dbobj, test_support, get_new_environment_path, \
        get_new_database_path

#----------------------------------------------------------------------

class dbobjTestCase(unittest.TestCase):
    """Verify that dbobj.DB and dbobj.DBEnv work properly"""
    db_name = 'test-dbobj.db'

    def setUp(self):
        self.homeDir = get_new_environment_path()

    def tearDown(self):
        if hasattr(self, 'db'):
            del self.db
        if hasattr(self, 'env'):
            del self.env
        test_support.rmtree(self.homeDir)

    def test01_both(self):
        class TestDBEnv(dbobj.DBEnv): pass
        class TestDB(dbobj.DB):
            def put(self, key, *args, **kwargs):
                key = key.upper()
                # call our parent classes put method with an upper case key
                return dbobj.DB.put(self, key, *args, **kwargs)
        self.env = TestDBEnv()
        self.env.open(self.homeDir, db.DB_CREATE | db.DB_INIT_MPOOL)
        self.db = TestDB(self.env)
        self.db.open(self.db_name, db.DB_HASH, db.DB_CREATE)
        self.db.put('spam', 'eggs')
        self.assertEqual(self.db.get('spam'), None,
               "overridden dbobj.DB.put() method failed [1]")
        self.assertEqual(self.db.get('SPAM'), 'eggs',
               "overridden dbobj.DB.put() method failed [2]")
        self.db.close()
        self.env.close()

    def test02_dbobj_dict_interface(self):
        self.env = dbobj.DBEnv()
        self.env.open(self.homeDir, db.DB_CREATE | db.DB_INIT_MPOOL)
        self.db = dbobj.DB(self.env)
        self.db.open(self.db_name+'02', db.DB_HASH, db.DB_CREATE)
        # __setitem__
        self.db['spam'] = 'eggs'
        # __len__
        self.assertEqual(len(self.db), 1)
        # __getitem__
        self.assertEqual(self.db['spam'], 'eggs')
        # __del__
        del self.db['spam']
        self.assertEqual(self.db.get('spam'), None, "dbobj __del__ failed")
        self.db.close()
        self.env.close()

    def test03_dbobj_type_before_open(self):
        # Ensure this doesn't cause a segfault.
        self.assertRaises(db.DBInvalidArgError, db.DB().type)

#----------------------------------------------------------------------

def test_suite():
    return unittest.makeSuite(dbobjTestCase)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
