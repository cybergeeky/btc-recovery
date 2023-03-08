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

"""TestCases for distributed transactions.
"""

import os
import unittest

from .test_all import db, test_support, get_new_environment_path, \
        get_new_database_path

from .test_all import verbose

#----------------------------------------------------------------------

class DBTxn_distributed(unittest.TestCase):
    num_txns=1234
    nosync=True
    must_open_db=False
    def _create_env(self, must_open_db) :
        self.dbenv = db.DBEnv()
        self.dbenv.set_tx_max(self.num_txns)
        self.dbenv.set_lk_max_lockers(self.num_txns*2)
        self.dbenv.set_lk_max_locks(self.num_txns*2)
        self.dbenv.set_lk_max_objects(self.num_txns*2)
        if self.nosync :
            self.dbenv.set_flags(db.DB_TXN_NOSYNC,True)
        self.dbenv.open(self.homeDir, db.DB_CREATE | db.DB_THREAD |
                db.DB_RECOVER |
                db.DB_INIT_TXN | db.DB_INIT_LOG | db.DB_INIT_MPOOL |
                db.DB_INIT_LOCK, 0o666)
        self.db = db.DB(self.dbenv)
        self.db.set_re_len(db.DB_GID_SIZE)
        if must_open_db :
            txn=self.dbenv.txn_begin()
            self.db.open(self.filename,
                    db.DB_QUEUE, db.DB_CREATE | db.DB_THREAD, 0o666,
                    txn=txn)
            txn.commit()

    def setUp(self) :
        self.homeDir = get_new_environment_path()
        self.filename = "test"
        return self._create_env(must_open_db=True)

    def _destroy_env(self):
        if self.nosync :
            self.dbenv.log_flush()
        self.db.close()
        self.dbenv.close()

    def tearDown(self):
        self._destroy_env()
        test_support.rmtree(self.homeDir)

    def _recreate_env(self,must_open_db) :
        self._destroy_env()
        self._create_env(must_open_db)

    def test01_distributed_transactions(self) :
        txns=set()
        adapt = lambda x : x
        import sys
        if sys.version_info[0] >= 3 :
            adapt = lambda x : bytes(x, "ascii")
    # Create transactions, "prepare" them, and
    # let them be garbage collected.
        for i in range(self.num_txns) :
            txn = self.dbenv.txn_begin()
            gid = "%%%dd" %db.DB_GID_SIZE
            gid = adapt(gid %i)
            self.db.put(i, gid, txn=txn, flags=db.DB_APPEND)
            txns.add(gid)
            txn.prepare(gid)
        del txn

        self._recreate_env(self.must_open_db)

    # Get "to be recovered" transactions but
    # let them be garbage collected.
        recovered_txns=self.dbenv.txn_recover()
        self.assertEqual(self.num_txns,len(recovered_txns))
        for gid,txn in recovered_txns :
            self.assertTrue(gid in txns)
        del txn
        del recovered_txns

        self._recreate_env(self.must_open_db)

    # Get "to be recovered" transactions. Commit, abort and
    # discard them.
        recovered_txns=self.dbenv.txn_recover()
        self.assertEqual(self.num_txns,len(recovered_txns))
        discard_txns=set()
        committed_txns=set()
        state=0
        for gid,txn in recovered_txns :
            if state==0 or state==1:
                committed_txns.add(gid)
                txn.commit()
            elif state==2 :
                txn.abort()
            elif state==3 :
                txn.discard()
                discard_txns.add(gid)
                state=-1
            state+=1
        del txn
        del recovered_txns

        self._recreate_env(self.must_open_db)

    # Verify the discarded transactions are still
    # around, and dispose them.
        recovered_txns=self.dbenv.txn_recover()
        self.assertEqual(len(discard_txns),len(recovered_txns))
        for gid,txn in recovered_txns :
            txn.abort()
        del txn
        del recovered_txns

        self._recreate_env(must_open_db=True)

    # Be sure there are not pending transactions.
    # Check also database size.
        recovered_txns=self.dbenv.txn_recover()
        self.assertTrue(len(recovered_txns)==0)
        self.assertEqual(len(committed_txns),self.db.stat()["nkeys"])

class DBTxn_distributedSYNC(DBTxn_distributed):
    nosync=False

class DBTxn_distributed_must_open_db(DBTxn_distributed):
    must_open_db=True

class DBTxn_distributedSYNC_must_open_db(DBTxn_distributed):
    nosync=False
    must_open_db=True

#----------------------------------------------------------------------

def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DBTxn_distributed))
    suite.addTest(unittest.makeSuite(DBTxn_distributedSYNC))
    suite.addTest(unittest.makeSuite(DBTxn_distributed_must_open_db))
    suite.addTest(unittest.makeSuite(DBTxn_distributedSYNC_must_open_db))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
